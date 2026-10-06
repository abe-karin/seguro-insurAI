"""
D&O Shield — Interface principal Streamlit.
"""
from __future__ import annotations
import os
import sys
import logging
from pathlib import Path

# Garante que o root do projeto está no sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Carrega variáveis de ambiente
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import streamlit as st

from app.config import get_llm_config, get_ocr_engine
from app.views.upload_view import render_upload
from app.views.policies_view import render_policies
from app.views.comparison_view import render_comparison
from app.views.history_view import render_history

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ─── Configuração da página ───────────────────────────────────────────────────

st.set_page_config(
    page_title="D&O Shield",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS customizado ──────────────────────────────────────────────────────────

st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d6a9f 100%);
        color: white;
        padding: 1.5rem 2rem;
        border-radius: 10px;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background: #f7f9fc;
        border: 1px solid #e1e8f0;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
    }
    .diff-alta { color: #d73a3a; font-weight: bold; }
    .diff-media { color: #e68a00; }
    .diff-baixa { color: #2e8b57; }
    .stTabs [data-baseweb="tab"] { font-size: 0.9rem; }
</style>
""", unsafe_allow_html=True)

# ─── Cabeçalho ────────────────────────────────────────────────────────────────

st.markdown("""
<div class="main-header">
    <h1 style="margin:0; font-size:1.8rem;">🛡️ D&O Shield</h1>
    <p style="margin:0.3rem 0 0 0; opacity:0.85;">
        Plataforma Inteligente de Análise e Comparação de Apólices D&O
    </p>
</div>
""", unsafe_allow_html=True)

# ─── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.image("https://img.shields.io/badge/D%26O-Shield-1e3a5f?style=for-the-badge", width=160)
    st.markdown("---")

    st.subheader("⚙️ Configurações")
    provider = st.selectbox(
        "Provedor LLM",
        options=["openai", "anthropic", "google"],
        index=["openai", "anthropic", "google"].index(os.getenv("LLM_PROVIDER", "openai")),
        key="llm_provider",
    )

    model_defaults = {
        "openai": "gpt-4o",
        "anthropic": "claude-3-5-sonnet-20241022",
        "google": "gemini-1.5-pro",
    }
    model = st.text_input(
        "Modelo",
        value=os.getenv("LLM_MODEL", model_defaults.get(provider, "gpt-4o")),
        key="llm_model",
    )

    ocr_engine = st.selectbox(
        "Engine OCR",
        options=["pdfplumber", "pymupdf", "tesseract"],
        index=["pdfplumber", "pymupdf", "tesseract"].index(os.getenv("OCR_ENGINE", "pdfplumber")),
        key="ocr_engine",
    )

    st.markdown("---")

   # Verificação e captura de chaves API
api_key_map = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
}
env_key = api_key_map.get(provider, "OPENAI_API_KEY")

# 1. Garante que se já existe no session_state, injeta no ambiente imediatamente
if env_key in st.session_state and st.session_state[env_key]:
    os.environ[env_key] = st.session_state[env_key]

# 2. Verifica se a chave está presente (via ambiente ou session)
if os.getenv(env_key):
    st.success(f"✅ {env_key} configurada")
else:
    st.warning(f"⚠️ {env_key} não encontrada")
    
    # 3. Usa o session_state para persistir o valor inserido pelo usuário
    api_key_input = st.text_input(
        f"Insira {env_key}",
        type="password",
        key=f"input_{env_key}"
    )
    
    if api_key_input:
        st.session_state[env_key] = api_key_input
        os.environ[env_key] = api_key_input
        st.rerun()
        
    st.markdown("---")
    st.caption("**D&O Shield MVP v1.0**  \nArquitetura multi-agente  \nIBM Bob 2025")

# ─── Navegação por abas ───────────────────────────────────────────────────────

tab_upload, tab_policies, tab_compare, tab_history = st.tabs([
    "📤 Enviar Apólice",
    "📋 Apólices Extraídas",
    "⚖️ Comparar Apólices",
    "📁 Histórico",
])

with tab_upload:
    render_upload(provider=provider, model=model, ocr_engine=ocr_engine)

with tab_policies:
    render_policies()

with tab_compare:
    render_comparison(provider=provider, model=model)

with tab_history:
    render_history()
