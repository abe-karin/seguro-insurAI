# Relatório Técnico — D&O Shield
## Plataforma Inteligente de Análise de Apólices D&O

**Versão:** 1.0  
**Data:** Outubro de 2026  
**Categoria:** MVP — Prova de Conceito Técnica  
**Autor:** insurAI Team

---

## 1. Resumo Executivo

O **D&O Shield** é um MVP de plataforma baseada em Inteligência Artificial Generativa desenvolvido para automatizar a leitura, extração estruturada e comparação de apólices de seguro **Directors & Officers (D&O)**. A solução adota uma arquitetura multi-agente especializada, onde cada agente é responsável por uma etapa distinta do pipeline de processamento, promovendo modularidade, testabilidade e clareza arquitetural.

O projeto responde diretamente às necessidades do mercado de seguros D&O no Brasil, onde a análise manual de apólices é laboriosa, propensa a erros e demanda expertise técnica especializada para identificar diferenças em coberturas, exclusões e condições gerais entre ofertas de diferentes seguradoras.

---

## 2. Contexto e Justificativa

### 2.1 O Seguro D&O no Brasil

O seguro D&O (Directors & Officers Liability) protege administradores de empresas contra reclamações decorrentes do exercício de suas funções. No Brasil, o produto é regulamentado pela **SUSEP** (Superintendência de Seguros Privados) e segue diretrizes da **Circular SUSEP nº 541/2016** e atualizações posteriores.

As principais coberturas típicas incluem:
- **Side A**: proteção individual de diretores/conselheiros quando a empresa não pode ou não quer indenizá-los
- **Side B**: reembolso à empresa pelos valores pagos em defesa dos administradores
- **Side C**: proteção da entidade em ações de valores mobiliários

### 2.2 Problema Identificado

A análise de apólices D&O apresenta desafios específicos:
1. Documentos extensos (30–120 páginas) com linguagem jurídico-securitária densa
2. Necessidade de identificar cláusulas críticas distribuídas ao longo do texto
3. Comparação entre ofertas de seguradoras distintas com estruturas documentais heterogêneas
4. Risco elevado de erro humano na extração manual de dados

### 2.3 Oportunidade

Modelos de linguagem de grande escala (LLMs) como GPT-4o demonstram capacidade superior na interpretação de documentos jurídicos e securitários, permitindo extração estruturada confiável e análise comparativa inteligente.

---

## 3. Arquitetura da Solução

### 3.1 Visão Geral

```
┌─────────────────────────────────────────────────────────────────┐
│                        INTERFACE (Streamlit)                     │
│    Upload │ Visualização │ Comparação │ Relatórios │ Histórico   │
└─────────────────────┬───────────────────────────────────────────┘
                      │
         ┌────────────▼────────────┐
         │   ORQUESTRADOR DE        │
         │   PIPELINE               │
         └────┬──────┬──────┬──────┘
              │      │      │
    ┌─────────▼─┐ ┌──▼────┐ ┌▼──────────┐
    │  AGENTE   │ │AGENTE │ │  AGENTE   │
    │ INGESTÃO  │ │EXTRAÇÃO│ │COMPARAÇÃO │
    │ (OCR/PDF) │ │ (LLM) │ │  (LLM)   │
    └─────────┬─┘ └──┬────┘ └▼──────────┘
              │      │      ┌▼──────────┐
              │      │      │  AGENTE   │
              │      │      │ RELATÓRIO │
              │      │      └───────────┘
              │      │
         ┌────▼──────▼────────────┐
         │   CAMADA DE DADOS       │
         │  SQLite + JSON (SQLAlch) │
         └─────────────────────────┘
```

### 3.2 Componentes Principais

| Componente | Arquivo | Responsabilidade |
|-----------|---------|-----------------|
| Agente de Ingestão | `agents/ingestion_agent.py` | Extração de texto de PDFs e imagens |
| Agente de Extração | `agents/extraction_agent.py` | Estruturação via LLM (schema Pydantic) |
| Agente de Comparação | `agents/comparison_agent.py` | Análise diferencial entre apólices |
| Agente de Relatório | `agents/report_agent.py` | Geração de PDF e Markdown |
| Schemas de Dados | `models/schemas.py` | Tipagem forte com Pydantic v2 |
| Persistência | `storage/database.py` | SQLAlchemy + SQLite |
| Interface | `app/` | Streamlit multi-view |

---

## 4. Fluxo de Processamento

### 4.1 Pipeline Completo

```
DOCUMENTO (PDF/IMG)
        │
        ▼
┌──────────────────┐
│  AGENTE INGESTÃO │
│ ─────────────── │
│ 1. Detecta tipo  │
│ 2. pdfplumber →  │
│    PyMuPDF →     │
│    Tesseract OCR │
│ 3. Retorna texto │
└────────┬─────────┘
         │ texto bruto
         ▼
┌──────────────────┐
│ AGENTE EXTRAÇÃO  │
│ ─────────────── │
│ 1. Chunking      │
│    (>60k chars)  │
│ 2. Prompt LLM    │
│    estruturado   │
│ 3. Parse JSON →  │
│    Pydantic      │
│ 4. Merge chunks  │
└────────┬─────────┘
         │ ApoliceExtraida
         ▼
┌──────────────────┐    ┌──────────────────┐
│    STORAGE       │    │ AGENTE COMPARAÇÃO│
│ ─────────────── │    │ ─────────────── │
│ SQLite via       │    │ 1. Serializa A+B │
│ SQLAlchemy       │    │ 2. Prompt LLM    │
│ JSON para        │    │ 3. Parse JSON →  │
│ dados completos  │    │    Pydantic      │
└──────────────────┘    │ 4. Fallback det. │
                        └────────┬─────────┘
                                 │ RelatorioComparativo
                                 ▼
                        ┌──────────────────┐
                        │ AGENTE RELATÓRIO │
                        │ ─────────────── │
                        │ Markdown + PDF   │
                        │ (FPDF2)          │
                        └──────────────────┘
```

### 4.2 Estratégia de OCR em Camadas

O Agente de Ingestão implementa uma estratégia de fallback progressivo:

1. **pdfplumber** (padrão): biblioteca Python pura, ideal para PDFs com texto embutido. Rápido e sem dependências externas.
2. **PyMuPDF (fitz)**: usado quando pdfplumber retorna texto insuficiente (<100 chars). Melhor desempenho em PDFs com layout complexo.
3. **Tesseract OCR**: ativado automaticamente para PDFs digitalizados (sem texto embutido). As páginas são convertidas em imagens via PyMuPDF antes do OCR, com zoom 2x para melhor qualidade.

Para imagens diretas (PNG, JPG, TIFF): Tesseract com idiomas `por+eng`.

### 4.3 Engenharia de Prompts

O Agente de Extração utiliza um **system prompt especializado** que instrui o LLM a:
- Identificar as três Sides da apólice D&O (A, B, C)
- Distinguir entre coberturas principais e sublimites
- Capturar cláusulas especiais (advance payment, run-off, severabilidade)
- Retornar **exclusivamente JSON válido** conformante ao schema Pydantic

O **response_format: json_object** (OpenAI) garante que o modelo nunca produza texto fora do JSON, eliminando erros de parse.

Para documentos longos (>60.000 caracteres / ~15k tokens), o texto é dividido em chunks e os resultados são mesclados inteligentemente, priorizando dados não-nulos.

---

## 5. Tecnologias Utilizadas

### 5.1 Stack Principal

| Tecnologia | Versão | Justificativa |
|-----------|--------|--------------|
| Python | 3.11+ | Ecossistema LLM maduro, tipagem, async |
| Streamlit | ≥1.35 | Interface rápida para protótipos de dados/IA |
| OpenAI GPT-4o | API | Melhor modelo para extração JSON estruturada |
| Anthropic Claude 3.5 | API | Alternativa com contexto 200k tokens |
| Google Gemini 1.5 Pro | API | Alternativa com suporte nativo a PDF |
| pdfplumber | ≥0.11 | Extração confiável de texto de PDFs |
| PyMuPDF | ≥1.24 | OCR de PDFs digitalizados |
| pytesseract | ≥0.3 | OCR open-source para imagens |
| Pydantic v2 | ≥2.7 | Schema validation, serialização JSON |
| SQLAlchemy | ≥2.0 | ORM tipado, abstração de banco |
| SQLite | embutido | Persistência local sem servidor |
| FPDF2 | ≥2.7 | Geração de PDF nativo em Python |
| python-dotenv | ≥1.0 | Gerenciamento de segredos |

### 5.2 Provedor LLM — Decisão Técnica

O sistema suporta **três provedores** configuráveis via variável de ambiente:

**OpenAI GPT-4o** (padrão recomendado):
- Suporte nativo a `response_format: json_object`
- Excelente desempenho em extração estruturada
- Latência média ~3–8s por extração

**Anthropic Claude 3.5 Sonnet**:
- Janela de contexto de 200k tokens (ideal para apólices extensas)
- Raciocínio superior em linguagem jurídica
- Sem suporte nativo a JSON mode (parsing manual)

**Google Gemini 1.5 Pro**:
- Capacidade nativa de processar PDFs diretamente (extensível)
- `response_mime_type: application/json` nativo
- Bom custo-benefício

---

## 6. Modelo de Dados

### 6.1 Schema Principal (Pydantic v2)

```
ApoliceExtraida
├── dados_apolice: DadosApolice
│   ├── numero_apolice: str?
│   ├── seguradora: str?
│   ├── vigencia_inicio: str?
│   ├── vigencia_fim: str?
│   ├── premio: str?
│   ├── limite_global: str?
│   └── base_acionamento: str?
├── segurado: DadosSegurado
│   ├── nome_segurado: str?
│   ├── cnpj: str?
│   └── setor: str?
├── coberturas: list[CoberturaPrincipal]
│   └── {nome, descricao, limite, franquia, retroatividade}
├── exclusoes: list[Exclusao]
│   └── {categoria, descricao}
├── clausulas_especiais: list[str]
├── observacoes: str?
├── texto_bruto: str?  [excluído da persistência]
└── nome_arquivo: str?
```

### 6.2 Schema Comparativo

```
RelatorioComparativo
├── apolice_a: str
├── apolice_b: str
├── diferencas_cadastrais: list[DiferencaCobertura]
├── diferencas_coberturas: list[DiferencaCobertura]
├── diferencas_exclusoes: list[DiferencaCobertura]
├── diferencas_limites: list[DiferencaCobertura]
├── resumo_executivo: str
└── recomendacao: str

DiferencaCobertura
├── campo: str
├── valor_a: str?
├── valor_b: str?
├── relevancia: "alta" | "media" | "baixa"
└── comentario: str
```

### 6.3 Persistência (SQLite)

Tabela **policies**: armazena metadados indexáveis (seguradora, número, segurado, vigência, limite) + JSON completo da apólice.

Tabela **comparisons**: armazena referências às apólices comparadas + JSON do relatório completo.

---

## 7. Interface do Usuário

A interface Streamlit é organizada em **4 abas funcionais**:

| Aba | Função |
|-----|--------|
| 📤 Enviar Apólice | Upload de arquivo, acionamento do pipeline, visualização do resultado |
| 📋 Apólices Extraídas | Listagem tabular, visualização detalhada, download de relatórios |
| ⚖️ Comparar Apólices | Seleção de par de apólices, execução da comparação, visualização de diffs |
| 📁 Histórico | Histórico completo de apólices e comparações salvas |

A **sidebar** permite configuração dinâmica de:
- Provedor LLM (OpenAI / Anthropic / Google)
- Modelo específico
- Engine OCR (pdfplumber / PyMuPDF / Tesseract)
- Inserção de chave de API em runtime

---

## 8. Decisões Arquiteturais

### 8.1 Arquitetura Multi-Agente

A opção por agentes especializados e desacoplados traz benefícios diretos:

- **Substituição independente**: o Agente de Ingestão pode ser trocado por Google Vision sem impacto nos demais
- **Testabilidade**: cada agente pode ser testado unitariamente com mocks
- **Escalabilidade futura**: agentes podem ser convertidos em microsserviços ou funções assíncronas
- **Clareza de responsabilidade**: cada agente tem uma única função bem definida (SRP)

### 8.2 Fallback Determinístico na Comparação

O Agente de Comparação implementa um **fallback determinístico** que opera sem LLM quando:
- A chave de API não está configurada
- O LLM retorna resposta inválida
- O usuário desativa explicitamente o uso do LLM

O fallback realiza comparação por conjuntos (set operations) sobre nomes de coberturas e categorias de exclusões, garantindo funcionamento mesmo offline.

### 8.3 Chunking Inteligente

Apólices D&O extensas (100+ páginas) podem ultrapassar os limites de contexto dos LLMs. O sistema divide o texto em chunks de 60.000 caracteres (~15k tokens) e mescla os resultados, priorizando:
1. Dados do primeiro chunk para informações cadastrais (número, seguradora, vigência)
2. Concatenação de coberturas e exclusões de todos os chunks

### 8.4 Segurança de Dados

- Chaves de API gerenciadas via variáveis de ambiente (`.env`)
- Texto bruto das apólices **não** é persistido no banco (excluído do `model_dump_json`)
- Banco SQLite local — dados não saem da máquina do usuário
- Suporte a múltiplos provedores permite uso de LLMs on-premises no futuro

---

## 9. Limitações Conhecidas e Evolução

### 9.1 Limitações do MVP

| Limitação | Impacto | Mitigação |
|-----------|---------|-----------|
| OCR de PDFs digitalizados com baixa qualidade | Extração incorreta | Pré-processamento de imagem (aumento de contraste) |
| LLM pode alucinar campos não presentes | Dados incorretos | Validação cruzada + interface humano-no-loop |
| Sem autenticação de usuários | Uso compartilhado inseguro | Integrar com sistema de autenticação |
| Processamento síncrono | Travamento da UI em PDFs longos | Filas async (Celery / asyncio) |
| Sem suporte multilíngue | Apólices em inglês podem ter menor qualidade | Fine-tuning ou instruções adicionais |

### 9.2 Roadmap Sugerido

**Fase 2 — Robustez:**
- Processamento assíncrono com barra de progresso em tempo real
- Pipeline de validação humana (human-in-the-loop)
- Suporte a Google Vision API para OCR de alta qualidade
- Testes unitários e de integração

**Fase 3 — Inteligência:**
- Agente de Recomendação: sugere melhorias de cobertura baseado em perfil de risco
- Integração com base pública SUSEP (consulta de seguradoras e produtos registrados)
- Fine-tuning de modelo especializado em documentos D&O brasileiros
- Análise de tendências de mercado a partir do banco acumulado

**Fase 4 — Produção:**
- API REST (FastAPI) para integração com sistemas de gestão de seguros
- Autenticação e multi-tenancy
- Deploy em cloud (AWS/GCP/Azure) com banco PostgreSQL
- Auditoria e rastreabilidade de todas as análises

---

## 10. Como Executar

### 10.1 Pré-requisitos

```bash
Python 3.11+
pip install -r requirements.txt
```

Para OCR com Tesseract (imagens e PDFs digitalizados):
```bash
# Windows
winget install UB-Mannheim.TesseractOCR
# Ubuntu/Debian
sudo apt install tesseract-ocr tesseract-ocr-por
# macOS
brew install tesseract tesseract-lang
```

### 10.2 Configuração

```bash
cp .env.example .env
# Edite .env e insira sua OPENAI_API_KEY (ou chave Anthropic/Google)
```

### 10.3 Execução

```bash
# Populando dados demo (sem precisar de PDF):
python scripts/seed_demo_data.py

# Iniciando a interface:
streamlit run app/main.py
```

Acesse em: http://localhost:8501

---

## 11. Estrutura de Arquivos

```
seguros/
├── app/
│   ├── main.py                  # Entrypoint Streamlit
│   ├── config.py                # Configurações centrais
│   └── views/
│       ├── upload_view.py       # Aba de upload
│       ├── policies_view.py     # Aba de apólices
│       ├── comparison_view.py   # Aba de comparação
│       └── history_view.py      # Aba de histórico
├── agents/
│   ├── ingestion_agent.py       # Agente OCR/PDF
│   ├── extraction_agent.py      # Agente LLM de extração
│   ├── comparison_agent.py      # Agente LLM de comparação
│   └── report_agent.py          # Agente de geração de relatórios
├── models/
│   └── schemas.py               # Schemas Pydantic v2
├── storage/
│   └── database.py              # SQLAlchemy + SQLite
├── scripts/
│   └── seed_demo_data.py        # Dados demo sintéticos
├── docs/                        # Apólices carregadas (auto-criado)
├── storage/                     # Banco de dados (auto-criado)
│   └── doshield.db
├── requirements.txt
├── .env.example
└── README.md
```

---

## 12. Conformidade com SUSEP

A plataforma foi desenvolvida considerando as principais diretrizes regulatórias da SUSEP para seguros D&O:

- **Circular SUSEP nº 541/2016**: estrutura básica das coberturas D&O no Brasil
- **Resolução CNSP nº 382/2020**: regras gerais de contratação de seguros
- **Nota Técnica Atuarial**: o sistema captura os limites máximos de garantia e franquias conforme exigido pela regulação

Os campos extraídos cobrem todos os elementos obrigatórios previstos nas condições gerais padronizadas pela SUSEP, incluindo base de acionamento, período de retroatividade e período de descoberta.

---

*D&O Shield — Plataforma MVP v1.0 | Junho 2025*
