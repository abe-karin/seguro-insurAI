"""
Cliente único de LLM usado por todos os agentes.

Concentra o que antes estava duplicado nos agentes de extração e comparação:
seleção de provedor, saída estruturada (JSON validado por Pydantic), retentativa
com espera quando o provedor limita a taxa de requisições e detecção de resposta
truncada. Os agentes só dependem de `generate_json` e `generate_text`.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import api_key_var

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Esperas (segundos) entre tentativas quando o provedor responde 429/503.
RETRY_DELAYS = (3,)

# Quantas voltas completas pela lista de modelos antes de desistir, e a pausa entre elas.
RODADAS = 2
PAUSA_ENTRE_RODADAS = 12

# Tempo máximo total de uma chamada (somando retentativas e trocas de modelo). Sem esse teto,
# o pior caso de retentativas deixaria a interface bloqueada por quase uma hora.
TEMPO_MAXIMO_S = 600

# Limite de tokens de saída aceito por cada provedor. O gpt-4o aceita no máximo 16.384;
# no SDK da Anthropic, chamadas sem streaming acima de ~21 mil tokens são recusadas.
MAX_TOKENS_PROVEDOR = {"google": 32000, "openai": 16000, "anthropic": 16000}

# Modelos alternativos, usados em ordem quando o escolhido está sobrecarregado,
# sem cota ou indisponível na conta. Evita que a demonstração dependa de um único modelo.
FALLBACK_MODELS = {
    "google": ("gemini-3.6-flash", "gemini-flash-latest", "gemini-3.1-flash-lite"),
    "openai": ("gpt-4o-mini",),
    "anthropic": (),
}


class LLMError(RuntimeError):
    """Falha ao obter uma resposta utilizável do modelo."""


class LLMTruncatedError(LLMError):
    """A resposta atingiu o limite de tokens de saída e veio incompleta."""


_TRANSITORIO = re.compile(
    r"\b(429|500|503|504)\b|RESOURCE_EXHAUSTED|UNAVAILABLE|DEADLINE_EXCEEDED|overloaded|rate[ _-]?limit",
    re.IGNORECASE,
)


def _is_transient(error: Exception) -> bool:
    """Erros em que vale repetir a chamada no mesmo modelo (sobrecarga ou limite de taxa)."""
    return bool(_TRANSITORIO.search(str(error)))


def _is_timeout(error: Exception) -> bool:
    texto = str(error).lower()
    return "timeout" in texto or "timed out" in texto


def _with_retries(call, provider: str):
    last: Optional[Exception] = None
    for attempt, delay in enumerate((0,) + RETRY_DELAYS):
        if delay:
            logger.warning("%s indisponível/limitado; nova tentativa em %ss", provider, delay)
            time.sleep(delay)
        try:
            return call()
        except LLMTruncatedError:
            raise
        except Exception as exc:  # noqa: BLE001 — classificamos abaixo
            last = exc
            # Tempo esgotado não se repete no mesmo modelo: passa direto ao próximo da lista.
            if _is_timeout(exc) or not _is_transient(exc):
                break
    raise LLMError(f"Falha ao consultar {provider}: {last}") from last


def _require_key(provider: str) -> str:
    var = api_key_var(provider)
    key = os.environ.get(var)
    if not key:
        raise LLMError(f"A variável {var} não está configurada.")
    return key


# ─── Provedores ──────────────────────────────────────────────────────────────

def _thinking_kwargs(model: str) -> dict:
    """
    Limita o "raciocínio" interno do Gemini. Extração e comparação são tarefas guiadas
    por schema; sem esse limite os modelos 3.x chegaram a levar minutos numa chamada curta.
    """
    from google.genai import types

    if "flash-lite" in model or "pro" in model:
        return {}  # flash-lite já não raciocina por padrão; modelos pro não permitem desligar
    if model.startswith("gemini-3") or "latest" in model:
        return {"thinking_config": types.ThinkingConfig(thinking_level="low")}
    return {"thinking_config": types.ThinkingConfig(thinking_budget=0)}


def _google(system: str, user: str, model: str, max_tokens: int, schema: Optional[Type[BaseModel]]) -> str:
    from google import genai
    from google.genai import types

    # Sem tempo limite, uma chamada a um modelo sobrecarregado pode ficar pendurada por minutos.
    # O limite cresce com o tamanho do documento e a retentativa fica a cargo deste módulo.
    timeout_ms = int(min(420, 150 + len(user) / 1500) * 1000)
    client = genai.Client(
        api_key=_require_key("google"),
        http_options=types.HttpOptions(timeout=timeout_ms, retry_options=types.HttpRetryOptions(attempts=1)),
    )
    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=0.0,
        max_output_tokens=max_tokens,
        **_thinking_kwargs(model),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        **(
            {"response_mime_type": "application/json", "response_schema": schema}
            if schema is not None
            else {}
        ),
    )
    response = client.models.generate_content(model=model, contents=user, config=config)
    candidates = getattr(response, "candidates", None) or []
    if candidates and str(getattr(candidates[0], "finish_reason", "")).endswith("MAX_TOKENS"):
        raise LLMTruncatedError("Resposta truncada pelo limite de tokens de saída.")
    return (response.text or "").strip()


def _openai(system: str, user: str, model: str, max_tokens: int, schema: Optional[Type[BaseModel]]) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=_require_key("openai"))
    kwargs = {"response_format": {"type": "json_object"}} if schema is not None else {}
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.0,
        max_tokens=max_tokens,
        **kwargs,
    )
    if response.choices[0].finish_reason == "length":
        raise LLMTruncatedError("Resposta truncada pelo limite de tokens de saída.")
    return (response.choices[0].message.content or "").strip()


def _anthropic(system: str, user: str, model: str, max_tokens: int, schema: Optional[Type[BaseModel]]) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=_require_key("anthropic"))
    # Sem `temperature`: as versões atuais do SDK não aceitam mais esse parâmetro.
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    if message.stop_reason == "max_tokens":
        raise LLMTruncatedError("Resposta truncada pelo limite de tokens de saída.")
    return "".join(block.text for block in message.content if getattr(block, "type", "") == "text").strip()


_PROVIDERS = {"google": _google, "openai": _openai, "anthropic": _anthropic}


def _dispatch(system, user, provider, model, max_tokens, schema) -> tuple[str, str]:
    """Chama o provedor e devolve (texto, modelo que de fato respondeu)."""
    if provider not in _PROVIDERS:
        raise LLMError(f"Provedor LLM desconhecido: {provider}")
    fn = _PROVIDERS[provider]
    max_tokens = min(max_tokens, MAX_TOKENS_PROVEDOR.get(provider, max_tokens))

    candidatos = [model] + [m for m in FALLBACK_MODELS.get(provider, ()) if m != model]
    ultimo: Optional[Exception] = None
    inicio = time.monotonic()
    for rodada in range(RODADAS):
        if rodada:
            logger.warning("Todos os modelos falharam; nova rodada em %ss.", PAUSA_ENTRE_RODADAS)
            time.sleep(PAUSA_ENTRE_RODADAS)
        for candidato in candidatos:
            if time.monotonic() - inicio > TEMPO_MAXIMO_S:
                raise LLMError(f"Tempo máximo de {TEMPO_MAXIMO_S}s esgotado. Último erro: {ultimo}") from ultimo
            try:
                return _with_retries(lambda: fn(system, user, candidato, max_tokens, schema), provider), candidato
            except LLMTruncatedError:
                raise
            except LLMError as exc:
                ultimo = exc
                logger.warning("Modelo '%s' falhou (%s); tentando o próximo da lista.", candidato, str(exc)[:140])
    raise LLMError(f"Todos os modelos falharam. Último erro: {ultimo}") from ultimo


# ─── API pública ─────────────────────────────────────────────────────────────

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def _parse_json(raw: str) -> dict:
    """Converte a resposta em dict, tolerando cercas de código e texto ao redor."""
    cleaned = _FENCE.sub("", raw.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def generate_json_ex(
    system: str,
    user: str,
    schema: Type[T],
    provider: str,
    model: str,
    max_tokens: int = 16000,
) -> tuple[T, str]:
    """
    Gera uma resposta estruturada, a valida contra `schema` e devolve (objeto, modelo usado).

    Para provedores sem modo de schema nativo, o JSON Schema é anexado ao prompt.
    Em caso de JSON inválido repete uma vez antes de falhar — nunca devolve um
    resultado vazio em silêncio.
    """
    if provider != "google":
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        user = f"{user}\n\nRetorne APENAS um JSON válido que siga este JSON Schema:\n{schema_json}"

    last: Optional[Exception] = None
    for attempt in (1, 2):
        raw, usado = _dispatch(system, user, provider, model, max_tokens, schema)
        try:
            return schema.model_validate(_parse_json(raw)), usado
        except (json.JSONDecodeError, ValidationError) as exc:
            last = exc
            logger.warning("Resposta fora do schema (tentativa %s/2): %s", attempt, exc)
    raise LLMError(f"O modelo não devolveu um JSON válido: {last}")


def generate_json(system: str, user: str, schema: Type[T], provider: str, model: str, max_tokens: int = 16000) -> T:
    """Versão de `generate_json_ex` que devolve só o objeto."""
    return generate_json_ex(system, user, schema, provider, model, max_tokens)[0]


def generate_text_ex(system: str, user: str, provider: str, model: str, max_tokens: int = 4000) -> tuple[str, str]:
    """Gera texto livre (usado pelo agente de consulta) e devolve (texto, modelo usado)."""
    text, usado = _dispatch(system, user, provider, model, max_tokens, None)
    if not text:
        raise LLMError("O modelo devolveu uma resposta vazia.")
    return text, usado


def generate_text(system: str, user: str, provider: str, model: str, max_tokens: int = 4000) -> str:
    return generate_text_ex(system, user, provider, model, max_tokens)[0]
