# D&O Shield — Plataforma Inteligente de Análise e Comparação de Apólices D&O

Plataforma baseada em IA Generativa que **lê**, **estrutura**, **consulta** e **compara** apólices e condições gerais de seguro **D&O (Directors & Officers)**. Apólices são documentos longos e jurídicos (50 a 100+ páginas); comparar duas delas costuma exigir horas de um especialista. O D&O Shield reduz esse trabalho a minutos e, principalmente, **mostra de onde saiu cada informação**: toda extração cita a página e o trecho do documento, e o sistema confere se o trecho realmente existe naquela página.

> Projeto Final do curso **InsurMinds** — Instituto de Inteligência Artificial Aplicada (I2A2).

## O que a plataforma faz

| Etapa | Funcionalidade |
|---|---|
| 1. Recebimento | Upload de um ou vários arquivos PDF ou imagem (PNG, JPG, TIFF) pela interface web |
| 2. Extração | Leitura página a página (pdfplumber, PyMuPDF ou OCR Tesseract, com *fallback* automático) |
| 3. Organização | O LLM preenche uma **ficha técnica D&O** de 22 tópicos fixos (acionamento, retroatividade, prazos, Side A/B/C, defesa, exclusões…) mais coberturas, exclusões e cláusulas especiais |
| 4. Armazenamento | SQLite: apólice estruturada (JSON), texto de cada página e comparações |
| 5. Consulta | Perguntas em linguagem natural; busca BM25 recupera as páginas relevantes e o LLM responde **citando apólice e página** |
| 6. Comparação | De 2 a 3 apólices alinhadas tópico a tópico; o LLM classifica a relevância, indica a mais favorável ao segurado e redige resumo e recomendação |
| 7. Apresentação | Interface Streamlit e relatórios exportáveis em PDF e Markdown |

### Diferenciais

- **Rastreabilidade (anti-alucinação).** Cada item tem `página + trecho literal`. Um verificador confirma se o trecho aparece na página citada (✅/⚠️ na interface) e corrige páginas citadas com erro de uma unidade.
- **O LLM não "recita" valores na comparação.** Os valores vêm da ficha extraída; o modelo só julga o que diverge. Se o LLM falhar, a comparação continua em modo determinístico.
- **Resiliência.** Cliente de LLM com tempo limite, retentativa e rodízio automático entre modelos quando um está sobrecarregado ou indisponível; nada falha em silêncio.
- **Multi-provedor.** Google Gemini (padrão), OpenAI e Anthropic, escolhidos na barra lateral.
- **Documentos grandes.** Divisão em lotes sempre em fronteira de página, processados em paralelo e fundidos sem duplicatas.

## Arquitetura

```
 PDF / imagem
      │
      ▼
┌──────────────────┐  texto por página   ┌──────────────────┐
│ Agente de        │ ──────────────────▶ │ Agente de        │  ficha técnica D&O
│ Ingestão         │                     │ Extração (LLM)   │  + coberturas, exclusões
│ pdfplumber /     │                     │ lotes paralelos  │  + fonte (página/trecho)
│ PyMuPDF /        │                     │ + verificação    │
│ Tesseract        │                     │ de ancoragem     │
└──────────────────┘                     └────────┬─────────┘
                                                  │ ApoliceExtraida
                                                  ▼
                                    ┌───────────────────────────┐
                                    │ Armazenamento (SQLite)    │
                                    │ apólices · páginas ·      │
                                    │ comparações               │
                                    └─────┬───────────────┬─────┘
                                          │               │
                         ┌────────────────▼───┐     ┌─────▼────────────────┐
                         │ Agente de          │     │ Agente de Consulta   │
                         │ Comparação         │     │ BM25 + LLM, resposta │
                         │ alinhamento +      │     │ com citação de       │
                         │ análise por LLM    │     │ página               │
                         └────────┬───────────┘     └──────────────────────┘
                                  │ RelatorioComparativo
                                  ▼
                         ┌────────────────────┐        ┌────────────────────┐
                         │ Agente de          │ ─────▶ │ Interface Streamlit│
                         │ Relatório PDF / MD │        │ 5 abas             │
                         └────────────────────┘        └────────────────────┘

        Transversal: agents/llm_client.py (provedores, schema, retentativa, rodízio de modelos)
```

```
agents/      Agentes: ingestão, extração, comparação, consulta, relatório e cliente de LLM
app/         Interface Streamlit (main.py, config.py e uma tela por aba em views/)
models/      Schemas Pydantic (apólice, ficha técnica, comparação)
storage/     Persistência SQLite (SQLAlchemy)
scripts/     processar_pdfs.py (lote via terminal), seed_demo_data.py (dados de demonstração sem chave),
             validate.py, debug_pdf.py e download_tessdata.py (idioma do OCR)
tests/       Testes automatizados (sem rede e sem chave de API)
docs/        Relatório técnico e registro das decisões de arquitetura
Projeto_Final_Artefatos/   Pitch Deck, vídeo e artefatos de apoio da entrega
```

A justificativa de cada decisão está em [`docs/DECISOES_DE_ARQUITETURA.md`](docs/DECISOES_DE_ARQUITETURA.md) e a descrição completa em [`docs/relatorio_tecnico.md`](docs/relatorio_tecnico.md).

## Instalação

Requisitos: **Python 3.11+**. O Tesseract OCR é opcional (necessário apenas para imagens e PDFs digitalizados).

```bash
git clone https://github.com/abe-karin/seguro-insurai.git
cd seguro-insurai

python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/macOS

pip install -r requirements.txt
```

Configure a chave de um provedor de LLM (o Gemini tem plano gratuito em <https://aistudio.google.com/app/apikey>):

```bash
copy .env.example .env         # Windows   (Linux/macOS: cp .env.example .env)
```

```ini
# .env
GOOGLE_API_KEY=sua_chave
```

Também é possível informar a chave direto na barra lateral da interface. O `.env` está no `.gitignore` e nunca deve ser versionado.

### OCR (opcional)

```bash
winget install UB-Mannheim.TesseractOCR      # Windows (macOS: brew install tesseract tesseract-lang)
python scripts/download_tessdata.py          # pacote de idioma português, sem precisar de administrador
```

## Execução

```bash
streamlit run app/main.py
```

Fluxo de demonstração: **Enviar apólices** → conferir a ficha técnica e a verificação das fontes → repetir com uma segunda apólice → **Comparar** → **Consultar** com uma pergunta (ex.: *“Há adiantamento de custos de defesa?”*).

Sem chave de API, é possível explorar a interface com duas apólices de demonstração:

```bash
python scripts/seed_demo_data.py
```

Processamento em lote, sem interface:

```bash
python scripts/processar_pdfs.py apolice_a.pdf apolice_b.pdf --comparar --saida relatorios
```

## Testes

```bash
python -m unittest discover -s tests -t .
```

Os testes cobrem divisão e fusão de lotes, verificação de ancoragem, comparação (determinística e com LLM simulado), consulta, persistência, ingestão e geração dos PDFs. Rodam sem rede e sem chave de API.

## Tecnologias

| Camada | Tecnologia |
|---|---|
| Interface | Streamlit |
| LLM | Google Gemini (padrão), OpenAI, Anthropic — via SDK oficial de cada um |
| Saída estruturada | JSON validado por Pydantic v2 (schema nativo no Gemini) |
| Leitura / OCR | pdfplumber, PyMuPDF, Tesseract (pytesseract) |
| Recuperação | BM25 próprio (sem acentos, sem palavras vazias) |
| Persistência | SQLite + SQLAlchemy |
| Relatórios | fpdf2 e Markdown |

## Limitações conhecidas

- A qualidade da extração depende do modelo e do texto do PDF; por isso cada item traz a fonte para conferência humana.
- A comparação avalia **condições contratuais**, não preço, e não substitui parecer de corretor ou jurídico.
- A recuperação da consulta é lexical (BM25); perguntas com sinônimos muito distantes do texto podem exigir reformulação.
- O banco SQLite local é efêmero em hospedagens como o Streamlit Cloud.
- OCR de documentos digitalizados de baixa qualidade pode degradar a extração.

## Integrantes

Grupo **InsurAi** — Juan David Valle Sánchez, Rodrigo Silva Figueiredo, Isabela Del Rio e Karin Abe.

## Licença

Distribuído sob a **Licença MIT** — consulte o arquivo [LICENSE](LICENSE).
