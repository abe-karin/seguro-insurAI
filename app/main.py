"""D&O Shield — interface principal (Streamlit)."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Garante que a raiz do projeto está no sys.path (execução via `streamlit run app/main.py`).
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import streamlit as st

from app.config import API_KEY_VARS, OCR_ENGINES, PROVIDERS, api_key_var, default_model, default_provider, get_ocr_engine
from app.views.comparison_view import render_comparison
from app.views.history_view import render_history
from app.views.policies_view import render_policies
from app.views.query_view import render_query
from app.views.upload_view import render_upload

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
for ruidosa in ("httpx", "httpcore", "urllib3", "google_genai", "pdfminer", "pdfplumber", "PIL"):
    logging.getLogger(ruidosa).setLevel(logging.WARNING)

st.set_page_config(page_title="D&O Shield", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")


def _carregar_segredos() -> None:
    """No Streamlit Cloud as chaves vêm de st.secrets; localmente, do .env."""
    try:
        for var in API_KEY_VARS.values():
            if var in st.secrets and not os.getenv(var):
                os.environ[var] = str(st.secrets[var])
    except Exception:  # noqa: BLE001 — sem arquivo de secrets, segue só com o ambiente
        pass


_carregar_segredos()

st.markdown(
    """
<style>
    .main-header {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d6a9f 100%);
        color: white; padding: 1.5rem 2rem; border-radius: 10px; margin-bottom: 1.5rem;
    }
    .stTabs [data-baseweb="tab"] { font-size: 0.95rem; }
</style>
<div class="main-header">
    <h1 style="margin:0; font-size:1.8rem;">🛡️ D&O Shield</h1>
    <p style="margin:0.3rem 0 0 0; opacity:0.85;">
        Plataforma inteligente de análise e comparação de apólices D&O
    </p>
</div>
""",
    unsafe_allow_html=True,
)

# ─── Barra lateral: configuração de modelo, OCR e chave ──────────────────────

with st.sidebar:
    st.markdown("### 🛡️ D&O Shield")
    st.subheader("⚙️ Configurações")

    provider = st.selectbox("Provedor LLM", options=PROVIDERS, index=PROVIDERS.index(default_provider()), key="llm_provider")
    model = st.text_input("Modelo", value=default_model(provider), key=f"llm_model_{provider}")
    ocr_engine = st.selectbox(
        "Engine OCR", options=OCR_ENGINES, index=OCR_ENGINES.index(get_ocr_engine()), key="ocr_engine",
        help="pdfplumber e pymupdf leem PDFs com texto embutido; tesseract faz OCR de digitalizados e imagens.",
    )

    st.markdown("---")
    chave = api_key_var(provider)
    if os.getenv(chave):
        st.success(f"✅ {chave} configurada")
    else:
        st.warning(f"⚠️ {chave} não encontrada")
        digitada = st.text_input(f"Informe {chave}", type="password", key=f"input_{chave}")
        if digitada:
            os.environ[chave] = digitada
            st.rerun()

    st.markdown("---")
    st.caption("**D&O Shield** · MVP\nArquitetura multiagente · I2A2 InsurMinds")

# ─── Navegação ────────────────────────────────────────────────────────────────

aba_envio, aba_apolices, aba_comparar, aba_consulta, aba_historico = st.tabs(
    ["📤 Enviar apólices", "📋 Apólices extraídas", "⚖️ Comparar", "💬 Consultar", "📁 Histórico"]
)

with aba_envio:
    render_upload(provider=provider, model=model, ocr_engine=ocr_engine)
with aba_apolices:
    render_policies()
with aba_comparar:
    render_comparison(provider=provider, model=model)
with aba_consulta:
    render_query(provider=provider, model=model)
with aba_historico:
    render_history()
