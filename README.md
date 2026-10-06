# D&O Shield — Plataforma Inteligente de Análise de Apólices D&O

MVP de plataforma baseada em IA Generativa para leitura, extração, estruturação e comparação de apólices de seguro **Directors & Officers (D&O)**.

## Funcionalidades

- 📄 Leitura de apólices em PDF ou imagem (PNG, JPG, TIFF)
- 🔍 Extração automática de cláusulas, coberturas, exclusões e dados cadastrais via LLM
- ⚖️ Comparação lado a lado entre duas ou mais apólices
- 📊 Relatório estruturado exportável
- 🤖 Arquitetura multi-agente especializada

## Arquitetura

```
docs/           → Apólices enviadas pelo usuário
agents/         → Agentes especializados (OCR, extração, comparação, relatório)
models/         → Schemas Pydantic para estruturação de dados
storage/        → Persistência SQLite + JSON
app/            → Interface Streamlit
utils/          → Helpers (PDF split, imagem, logger)
```

## Instalação

```bash
pip install -r requirements.txt
```

Crie o arquivo `.env` com sua chave de API:

```
OPENAI_API_KEY=sk-...
# ou
ANTHROPIC_API_KEY=...
# ou
GOOGLE_API_KEY=...
```

## Execução

```bash
streamlit run app/main.py
```

## Tecnologias

| Camada | Tecnologia |
|--------|-----------|
| Interface | Streamlit |
| LLM | OpenAI GPT-4o / Gemini / Anthropic Claude |
| OCR | pdfplumber + pytesseract / Google Vision |
| Extração | LangChain + Pydantic |
| Persistência | SQLite + JSON |
| Relatório | FPDF2 / Markdown |
