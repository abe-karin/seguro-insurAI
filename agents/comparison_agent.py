"""
Agente de Comparação — analisa diferenças entre duas apólices D&O.
"""
from __future__ import annotations
import json
import logging
import os

from models.schemas import ApoliceExtraida, RelatorioComparativo, DiferencaCobertura

logger = logging.getLogger(__name__)

COMPARISON_SYSTEM_PROMPT = """Você é um especialista em seguros D&O com expertise em análise comparativa de apólices.

Sua tarefa é comparar duas apólices D&O estruturadas e identificar diferenças relevantes para tomada de decisão.

INSTRUÇÕES:
1. Compare sistematicamente todos os campos: dados cadastrais, coberturas, exclusões e limites.
2. Classifique a relevância de cada diferença como: "alta" (impacto direto na cobertura/custo), "media" (relevante mas não crítica), "baixa" (diferença formal/administrativa).
3. Para diferenças em coberturas: avalie qual apólice oferece proteção mais ampla.
4. Para diferenças em exclusões: uma exclusão adicional na apólice A em relação à B é desvantagem para A.
5. Produza um resumo executivo claro e uma recomendação técnica.
6. Retorne APENAS JSON válido seguindo o schema fornecido.
"""

COMPARISON_USER_TEMPLATE = """Compare as duas apólices D&O abaixo e retorne um JSON estruturado com as diferenças.

SCHEMA ESPERADO:
{{
  "apolice_a": "identificador",
  "apolice_b": "identificador",
  "diferencas_cadastrais": [
    {{"campo": "string", "valor_a": "string|null", "valor_b": "string|null", "relevancia": "alta|media|baixa", "comentario": "string"}}
  ],
  "diferencas_coberturas": [...],
  "diferencas_exclusoes": [...],
  "diferencas_limites": [...],
  "resumo_executivo": "string",
  "recomendacao": "string"
}}

APÓLICE A — {nome_a}:
{json_a}

APÓLICE B — {nome_b}:
{json_b}
"""


def _get_llm_response(prompt_system: str, prompt_user: str, provider: str, model: str) -> str:
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


def _apolice_to_summary_json(apolice: ApoliceExtraida) -> str:
    """Serializa a apólice para JSON resumido (sem texto_bruto) para envio ao LLM."""
    data = apolice.model_dump(exclude={"texto_bruto"})
    return json.dumps(data, ensure_ascii=False, indent=2)


def _build_simple_diff(a: ApoliceExtraida, b: ApoliceExtraida) -> RelatorioComparativo:
    """
    Fallback: gera comparação determinística simples sem LLM.
    Usado quando o LLM falha ou não está configurado.
    """
    diffs_cadastrais = []

    def compare_field(campo: str, val_a, val_b, relevancia: str = "media"):
        va = str(val_a) if val_a else None
        vb = str(val_b) if val_b else None
        if va != vb:
            diffs_cadastrais.append(DiferencaCobertura(
                campo=campo,
                valor_a=va,
                valor_b=vb,
                relevancia=relevancia,
                comentario=f"Campo '{campo}' difere entre as apólices."
            ))

    da = a.dados_apolice
    db = b.dados_apolice
    compare_field("seguradora", da.seguradora, db.seguradora, "alta")
    compare_field("limite_global", da.limite_global, db.limite_global, "alta")
    compare_field("premio", da.premio, db.premio, "alta")
    compare_field("base_acionamento", da.base_acionamento, db.base_acionamento, "alta")
    compare_field("vigencia_inicio", da.vigencia_inicio, db.vigencia_inicio, "media")
    compare_field("vigencia_fim", da.vigencia_fim, db.vigencia_fim, "media")

    nomes_cob_a = {c.nome for c in a.coberturas}
    nomes_cob_b = {c.nome for c in b.coberturas}
    diffs_cob = []
    for nome in nomes_cob_a - nomes_cob_b:
        diffs_cob.append(DiferencaCobertura(
            campo=f"Cobertura: {nome}",
            valor_a="Presente",
            valor_b="Ausente",
            relevancia="alta",
            comentario=f"Cobertura '{nome}' existe na apólice A mas não na B."
        ))
    for nome in nomes_cob_b - nomes_cob_a:
        diffs_cob.append(DiferencaCobertura(
            campo=f"Cobertura: {nome}",
            valor_a="Ausente",
            valor_b="Presente",
            relevancia="alta",
            comentario=f"Cobertura '{nome}' existe na apólice B mas não na A."
        ))

    cats_exc_a = {e.categoria for e in a.exclusoes}
    cats_exc_b = {e.categoria for e in b.exclusoes}
    diffs_exc = []
    for cat in cats_exc_a - cats_exc_b:
        diffs_exc.append(DiferencaCobertura(
            campo=f"Exclusão: {cat}",
            valor_a="Presente",
            valor_b="Ausente",
            relevancia="media",
            comentario=f"Exclusão '{cat}' presente na apólice A mas não na B."
        ))
    for cat in cats_exc_b - cats_exc_a:
        diffs_exc.append(DiferencaCobertura(
            campo=f"Exclusão: {cat}",
            valor_a="Ausente",
            valor_b="Presente",
            relevancia="media",
            comentario=f"Exclusão '{cat}' presente na apólice B mas não na A."
        ))

    return RelatorioComparativo(
        apolice_a=a.nome_arquivo or "Apólice A",
        apolice_b=b.nome_arquivo or "Apólice B",
        diferencas_cadastrais=diffs_cadastrais,
        diferencas_coberturas=diffs_cob,
        diferencas_exclusoes=diffs_exc,
        diferencas_limites=[],
        resumo_executivo=(
            f"Comparação simplificada entre {a.nome_arquivo or 'Apólice A'} e "
            f"{b.nome_arquivo or 'Apólice B'}. Foram identificadas "
            f"{len(diffs_cadastrais)} diferenças cadastrais, "
            f"{len(diffs_cob)} diferenças em coberturas e "
            f"{len(diffs_exc)} diferenças em exclusões."
        ),
        recomendacao="Análise gerada em modo simplificado. Configure um LLM para obter recomendação detalhada."
    )


def compare_policies(
    apolice_a: ApoliceExtraida,
    apolice_b: ApoliceExtraida,
    provider: str = "openai",
    model: str = "gpt-4o",
    use_llm: bool = True,
) -> RelatorioComparativo:
    """
    Compara duas apólices D&O e retorna um relatório de diferenças.

    Args:
        apolice_a: Primeira apólice extraída.
        apolice_b: Segunda apólice extraída.
        provider: Provedor LLM.
        model: Modelo LLM.
        use_llm: Se False, usa comparação determinística sem LLM.

    Returns:
        RelatorioComparativo com todas as diferenças identificadas.
    """
    if not use_llm:
        return _build_simple_diff(apolice_a, apolice_b)

    nome_a = apolice_a.nome_arquivo or "Apólice A"
    nome_b = apolice_b.nome_arquivo or "Apólice B"

    json_a = _apolice_to_summary_json(apolice_a)
    json_b = _apolice_to_summary_json(apolice_b)

    prompt_user = COMPARISON_USER_TEMPLATE.format(
        nome_a=nome_a,
        nome_b=nome_b,
        json_a=json_a,
        json_b=json_b,
    )

    try:
        raw_json = _get_llm_response(COMPARISON_SYSTEM_PROMPT, prompt_user, provider, model)
        data = json.loads(raw_json)
        relatorio = RelatorioComparativo.model_validate(data)
        logger.info(f"Comparação LLM concluída: {len(relatorio.diferencas_coberturas)} diffs de cobertura")
        return relatorio
    except Exception as e:
        logger.error(f"Falha na comparação LLM, usando fallback determinístico: {e}")
        return _build_simple_diff(apolice_a, apolice_b)
