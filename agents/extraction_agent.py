"""
Agente de Extração — usa LLM para estruturar informações de apólices D&O.
Suporta: OpenAI, Anthropic Claude, Google Gemini.
"""
from __future__ import annotations
import json
import logging
import os
from typing import Optional

from models.schemas import ApoliceExtraida

logger = logging.getLogger(__name__)

# ─── Prompt de extração ──────────────────────────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """Você é um especialista sênior em seguros D&O (Directors & Officers) com profundo conhecimento em análise de apólices, regulamentação SUSEP e práticas de mercado brasileiro.

Sua tarefa é extrair e estruturar informações de apólices D&O a partir do texto fornecido.

INSTRUÇÕES:
1. Extraia TODOS os campos disponíveis no texto — não invente informações ausentes.
2. Para campos não encontrados, use null.
3. Seja preciso com valores numéricos (prêmios, limites, franquias).
4. Identifique a base de acionamento: "claims made" (reclamação feita) ou "ocorrência".
5. Liste TODAS as coberturas, incluindo: Side A (diretores), Side B (reembolso empresa), Side C (entidade).
6. Liste TODAS as exclusões relevantes.
7. Identifique cláusulas especiais como: "advance payment", "run-off", "discovery period", "severabilidade".
8. Retorne APENAS um JSON válido seguindo o schema fornecido. Sem texto adicional.
"""

EXTRACTION_USER_TEMPLATE = """Extraia as informações da seguinte apólice D&O e retorne um JSON estruturado.

SCHEMA ESPERADO:
{{
  "dados_apolice": {{
    "numero_apolice": "string ou null",
    "seguradora": "string ou null",
    "vigencia_inicio": "string ou null",
    "vigencia_fim": "string ou null",
    "premio": "string ou null",
    "limite_global": "string ou null",
    "base_acionamento": "string ou null"
  }},
  "segurado": {{
    "nome_segurado": "string ou null",
    "cnpj": "string ou null",
    "setor": "string ou null"
  }},
  "coberturas": [
    {{
      "nome": "string",
      "descricao": "string",
      "limite": "string ou null",
      "franquia": "string ou null",
      "retroatividade": "string ou null"
    }}
  ],
  "exclusoes": [
    {{
      "categoria": "string",
      "descricao": "string"
    }}
  ],
  "clausulas_especiais": ["string"],
  "observacoes": "string ou null"
}}

TEXTO DA APÓLICE:
{texto}
"""


# ─── Factory de LLM ──────────────────────────────────────────────────────────

def _get_llm_response(prompt_system: str, prompt_user: str, provider: str, model: str) -> str:
    """Chama o LLM configurado e retorna a resposta como string."""

    if provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": prompt_user},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        return response.choices[0].message.content

    elif provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        message = client.messages.create(
            model=model,
            max_tokens=4096,
            system=prompt_system,
            messages=[{"role": "user", "content": prompt_user}],
        )
        return message.content[0].text

    elif provider == "google":
        import google.generativeai as genai
        genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
        llm = genai.GenerativeModel(
            model_name=model,
            system_instruction=prompt_system,
            generation_config={"response_mime_type": "application/json"},
        )
        response = llm.generate_content(prompt_user)
        return response.text

    else:
        raise ValueError(f"Provedor LLM desconhecido: {provider}")


# ─── Chunking para textos longos ─────────────────────────────────────────────

MAX_CHARS = 60_000  # ~15k tokens, seguro para GPT-4o


def _chunk_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Divide o texto em blocos menores se necessário."""
    if len(text) <= max_chars:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:max_chars])
        text = text[max_chars:]
    return chunks


def _merge_extractions(extractions: list[dict]) -> dict:
    """Mescla múltiplas extrações de chunks em uma única."""
    if len(extractions) == 1:
        return extractions[0]

    merged = extractions[0].copy()
    for ext in extractions[1:]:
        # Mescla coberturas e exclusões de todos os chunks
        for lista in ("coberturas", "exclusoes", "clausulas_especiais"):
            existing = merged.get(lista, [])
            new_items = ext.get(lista, [])
            merged[lista] = existing + new_items

        # Preenche campos nulos do primeiro chunk com dados dos seguintes
        for key in ("dados_apolice", "segurado"):
            if key in ext:
                for subkey, val in (ext[key] or {}).items():
                    if val and not (merged.get(key) or {}).get(subkey):
                        if merged.get(key) is None:
                            merged[key] = {}
                        merged[key][subkey] = val

    return merged


# ─── Agente principal ─────────────────────────────────────────────────────────

def extract_policy(
    text: str,
    filename: str = "apolice.pdf",
    provider: str = "openai",
    model: str = "gpt-4o",
) -> ApoliceExtraida:
    """
    Extrai estrutura de uma apólice D&O a partir do texto bruto.

    Args:
        text: Texto extraído do documento pelo agente de ingestão.
        filename: Nome do arquivo original (para rastreabilidade).
        provider: 'openai' | 'anthropic' | 'google'
        model: Nome do modelo LLM.

    Returns:
        ApoliceExtraida com todos os campos estruturados.
    """
    chunks = _chunk_text(text)
    logger.info(f"Extraindo apólice '{filename}' em {len(chunks)} chunk(s) via {provider}/{model}")

    extractions = []
    for i, chunk in enumerate(chunks):
        prompt_user = EXTRACTION_USER_TEMPLATE.format(texto=chunk)
        try:
            raw_json = _get_llm_response(EXTRACTION_SYSTEM_PROMPT, prompt_user, provider, model)
            parsed = json.loads(raw_json)
            extractions.append(parsed)
            logger.info(f"  Chunk {i+1}/{len(chunks)} extraído com sucesso")
        except json.JSONDecodeError as e:
            logger.error(f"  Falha ao parsear JSON do chunk {i+1}: {e}")
            extractions.append({})

    merged = _merge_extractions(extractions)

    # Garante campos obrigatórios com defaults
    merged.setdefault("dados_apolice", {})
    merged.setdefault("segurado", {})
    merged.setdefault("coberturas", [])
    merged.setdefault("exclusoes", [])
    merged.setdefault("clausulas_especiais", [])

    apolice = ApoliceExtraida.model_validate(merged)
    apolice.texto_bruto = text
    apolice.nome_arquivo = filename

    logger.info(f"Extração concluída: {len(apolice.coberturas)} coberturas, {len(apolice.exclusoes)} exclusões")
    return apolice
