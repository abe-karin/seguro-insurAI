# Relatório Técnico — D&O Shield
**Plataforma Inteligente para Análise e Comparação de Apólices D&O**
Projeto Final — InsurMinds · Instituto de Inteligência Artificial Aplicada (I2A2)

**Grupo:** InsurAi — Juan David Valle Sánchez, Rodrigo Silva Figueiredo, Isabela Del Rio, Karin Abe
**Data:** 06/10/2026
**Repositório:** https://github.com/abe-karin/seguro-insurAI
**Licença:** MIT

---

## 1. Resumo executivo

Apólices e condições gerais de seguro D&O (Directors & Officers) são documentos longos, de linguagem jurídica, e compará-los exige horas de um especialista. O **D&O Shield** é um protótipo funcional que automatiza esse trabalho com IA Generativa: recebe os documentos (PDF ou imagem), extrai o texto, estrutura uma **ficha técnica D&O de 22 tópicos**, armazena os dados, permite **consultas em linguagem natural** e **compara de duas a três apólices**, apresentando as diferenças por relevância.

O princípio de projeto é a **rastreabilidade**: toda informação extraída cita a **página** e o **trecho literal** do documento, e o sistema confere se o trecho de fato existe naquela página. Em vez de pedir ao usuário que confie no modelo, a plataforma permite que ele confira.

## 2. Problema e escopo

| Dificuldade | Como a plataforma responde |
|---|---|
| Documentos de 50 a 100+ páginas | Leitura página a página, lotes em paralelo, fusão sem duplicatas |
| Estruturas diferentes entre seguradoras | Ficha técnica com os mesmos 22 tópicos para todos os documentos, o que torna as respostas comparáveis |
| Risco de o modelo inventar informação | Cada item cita página e trecho; verificação automática do trecho (✅/⚠️) |
| Decidir o que importa nas diferenças | Análise por LLM: relevância (alta/média/baixa), apólice mais favorável e recomendação |
| Achar uma cláusula no meio do documento | Consulta em linguagem natural com resposta citando a página |

**Fora do escopo** (conforme o enunciado): produto comercial, alta disponibilidade, integração com sistemas de seguradoras e cobertura de todos os tipos de apólice. A comparação avalia condições contratuais, não preço.

## 3. Arquitetura

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

Os agentes são módulos Python independentes, cada um com uma responsabilidade, que se comunicam por objetos Pydantic. Isso permite testar cada etapa isoladamente (sem rede) e trocar uma peça (por exemplo, o provedor de LLM) sem tocar nas demais.

## 4. Agentes

### 4.1 Agente de Ingestão (`agents/ingestion_agent.py`)
Extrai o texto **por página**. Estratégia em camadas: `pdfplumber` (padrão) → `PyMuPDF` se vier pouco texto → **OCR Tesseract** se o PDF for digitalizado; imagens (PNG, JPG, TIFF) vão direto ao Tesseract (português + inglês). Localiza o binário do Tesseract automaticamente (variável `TESSERACT_CMD`, PATH e caminhos do Windows) e usa `storage/tessdata` quando existir. Falhas geram mensagens com instruções de correção.

### 4.2 Agente de Extração (`agents/extraction_agent.py`)
Envia o texto, com marcadores `[[PÁGINA n]]`, a um LLM com **saída estruturada** (schema Pydantic nativo no Gemini; JSON Schema no prompt para OpenAI/Anthropic). O resultado é pós-processado:

1. **Divisão em lotes** de ~90 mil caracteres, **apenas em fronteiras de página**, processados **em paralelo**;
2. **Fusão** dos lotes sem duplicatas (sem acentos e sem diferença de caixa);
3. **Deduplicação fuzzy de coberturas**: documentos D&O listam as extensões num resumo e depois as detalham; nomes como “Extensão de Cobertura para X” e “Extensão para X” são unidos, mantendo a descrição mais completa;
4. **Ficha completa**: os 22 tópicos sempre presentes (`null` = o documento não trata do assunto); tópicos inventados pelo modelo são descartados;
5. **Verificação de ancoragem**: para cada fonte citada, confere se o trecho aparece na página indicada (tolerando acentos e quebras de linha), corrige erros de uma página e marca o restante como não verificado.

### 4.3 Agente de Comparação (`agents/comparison_agent.py`)
Funciona em duas etapas deliberadamente separadas:

1. **Alinhamento determinístico.** Os valores de cada tópico vêm da ficha extraída — o LLM nunca “recita” valores, portanto não pode inventá-los. Calcula quais tópicos divergem.
2. **Julgamento por LLM.** Recebe apenas os tópicos divergentes e devolve a relevância, a apólice mais favorável ao segurado, um comentário prático, o resumo executivo e a recomendação.

Se o LLM falhar, a comparação continua em **modo determinístico**. Aceita de 2 a 3 apólices; para listas (coberturas, exclusões, cláusulas) aponta os itens que aparecem em apenas parte delas.

### 4.4 Agente de Consulta (`agents/query_agent.py`)
Recuperação + geração. Um índice **BM25** (sem acentos e sem palavras vazias) escolhe as páginas mais relevantes **de cada apólice** selecionada; o LLM responde somente com esses trechos e a ficha técnica, citando `[apólice, p. N]`. As citações são conferidas contra as páginas realmente recuperadas, descartando referências inventadas.

### 4.5 Agente de Relatório (`agents/report_agent.py`)
Gera Markdown e PDF. O PDF é montado direto dos objetos estruturados com a API de tabelas do `fpdf2`; o comparativo sai em paisagem, com uma coluna por apólice.

### 4.6 Cliente de LLM (`agents/llm_client.py`)
Camada única usada por todos os agentes: provedores (Gemini, OpenAI, Anthropic), saída validada por Pydantic com uma repetição se o JSON vier inválido, **tempo limite**, **retentativa** em 429/503/timeouts, **rodízio automático entre modelos** quando um está sobrecarregado ou indisponível, e detecção de resposta truncada. Toda falha vira `LLMError` — nada é engolido em silêncio.

## 5. Fluxo de processamento

1. O usuário envia um ou mais arquivos (aba **Enviar apólices**).
2. A ingestão devolve o texto de cada página.
3. A extração gera a ficha técnica, as coberturas, as exclusões e as cláusulas, com a fonte de cada item, e verifica as fontes.
4. A apólice e o texto das páginas são gravados no SQLite.
5. **Consultar**: pergunta → BM25 por apólice → LLM responde citando as páginas.
6. **Comparar**: 2 a 3 apólices → alinhamento por tópico → análise do LLM → relatório.
7. O resultado é exibido e pode ser exportado em PDF ou Markdown.

## 6. Modelo de dados

- `ApoliceExtraida`: dados da apólice e do segurado, `ficha_tecnica` (lista de `ItemFicha`: tópico, valor, `Fonte`), coberturas, exclusões, cláusulas especiais, observações, total de páginas.
- `Fonte`: página, trecho literal e `verificada` (preenchido pelo sistema, não pelo modelo).
- `RelatorioComparativo`: apólices, divergências (`DiferencaTopico`: valores por apólice com página, relevância, comentário, mais favorável), tópicos sem divergência, resumo, recomendação, modo (`llm`/`deterministico`) e modelo usado.
- Persistência (SQLite/SQLAlchemy): tabelas `policies`, `policy_pages` (texto de cada página) e `comparisons`.

### Ficha técnica D&O (22 tópicos)
Acionamento: base de acionamento, retroatividade, prazo de aviso, prazo complementar de notificação. Coberturas: pessoas seguradas, Side A, Side B, Side C, custos de defesa, multas e penalidades. Limites: limite e sublimites, franquia. Exclusões: dolo, vantagem indevida, poluição, fatos anteriores, reclamações entre segurados. Processo: escolha da defesa, mudança de controle, rateio, cancelamento, arbitragem e foro, território.

## 7. Tecnologias e justificativas

| Tecnologia | Papel | Por que |
|---|---|---|
| Python 3.11+ | Linguagem | Ecossistema de IA, OCR e dados |
| Streamlit | Interface web | Demonstração rápida de um MVP, sem front-end separado |
| Google Gemini (padrão), OpenAI, Anthropic | LLM | Provedor trocável; o Gemini tem contexto longo, saída estruturada nativa e plano gratuito |
| Pydantic v2 | Schemas e validação | Contrato explícito entre agentes; rejeita saída fora do formato |
| pdfplumber, PyMuPDF, Tesseract | Leitura e OCR | PDFs com texto embutido e digitalizados |
| BM25 próprio | Recuperação da consulta | Sem serviço extra, explicável, adequado a texto jurídico de terminologia estável |
| SQLite + SQLAlchemy | Persistência | Zero infraestrutura; troca por outro banco sem alterar os agentes |
| fpdf2 | PDF | Tabelas com quebra automática de texto, sem dependências de sistema |

## 8. Decisões arquiteturais
Resumidas abaixo; o registro completo, com os problemas da primeira versão que motivaram cada mudança, está em [`DECISOES_DE_ARQUITETURA.md`](DECISOES_DE_ARQUITETURA.md).

- **Ficha técnica com tópicos fixos** para tornar documentos heterogêneos comparáveis.
- **Fonte + verificação** para combater alucinação e permitir auditoria.
- **Lotes por página, em paralelo**, para não cortar frases e reduzir latência.
- **Comparação em duas etapas** (alinhar e depois julgar) para que o LLM não invente valores.
- **BM25 em vez de embeddings** na consulta: simples, rápido e explicável.
- **Cliente de LLM único com rodízio de modelos**, pois a disponibilidade dos modelos oscila (observamos 503 de alta demanda em vários modelos no mesmo dia).
- **Relatórios gerados dos objetos**, não de Markdown, para não perder linhas de tabela.

## 9. Resultados com documentos reais

Usamos três documentos públicos, registrados na SUSEP, de seguradoras do mercado brasileiro (listados na seção 11).

| Documento | Páginas | Caracteres | Coberturas | Exclusões | Fontes verificadas | Tempo |
|---|---|---|---|---|---|---|
| Porto Seguro | 52 | 175.120 | 34 | 28 | 103 de 103 | 207 s |
| AXA Seguros | 104 | 230.777 | 41 | 25 | 89 de 89 | 191 s |
| Allianz Seguros | 75 | 248.634 | — | — | — | em validação |

Extração com `gemini-flash-lite-latest`, em lotes paralelos. Todos os 22 tópicos da ficha técnica foram preenchidos nos dois documentos processados, cada um com página e trecho confirmados no texto original. Na Porto, a deduplicação de coberturas reduziu 52 itens brutos para 34: o documento lista as extensões num resumo inicial e as detalha nas cláusulas.

Durante os testes, a API do Gemini apresentou erros 503 (alta demanda) e, sob chamadas simultâneas, 429 (cota do plano gratuito). O rodízio de modelos e as retentativas do cliente de LLM absorveram parte disso, mas o processamento ficou estável apenas com um documento por vez.

## 10. Testes

`python -m unittest discover -s tests -t .` executa a suíte automatizada de 64 testes (sem rede e sem chave de API), que cobre: divisão e fusão de lotes, deduplicação de coberturas, verificação de ancoragem (trecho literal, inventado, página errada, acentos), comparação determinística e com LLM simulado (relevância inválida, apólice favorável inexistente, falha do LLM, 2 e 3 apólices), consulta (BM25, citações válidas e inventadas), persistência, ingestão e geração dos PDFs — incluindo um **teste de regressão que lê o PDF gerado e confere que as linhas das tabelas estão presentes** (a primeira versão exportava só os cabeçalhos).

## 11. Fontes dos documentos

Documentos públicos de seguradoras, usados somente para demonstração:

- Porto Seguro — *Condições Gerais, Seguro de Responsabilidade Civil para Administradores (D&O) — Empresas de Capital Fechado*, vigência a partir de 01/02/2022.
- AXA Seguros — *Condições Gerais, Seguro de Responsabilidade Civil de Diretores e Administradores (D&O) — Base de Reclamações com Notificação*, processo SUSEP 15414.901016/2017-01, versão 12/2025.
- Allianz Seguros — *Responsabilidade Civil de Diretores e Administradores de Empresas (D&O)*, processo SUSEP 15414.901113/2017-96, versão 12/2025.

## 12. Limitações conhecidas

- A qualidade da extração depende do modelo e da qualidade do texto; por isso cada item traz a fonte e o selo de verificação, e a conferência humana continua recomendada.
- A verificação confirma que o **trecho existe** na página, mas não garante que o **resumo** do modelo o interprete corretamente.
- A comparação avalia condições contratuais, não preço, e não substitui parecer de corretor ou jurídico.
- A consulta usa recuperação lexical; perguntas com sinônimos muito distantes do texto podem exigir reformulação.
- A disponibilidade do LLM é externa ao projeto: em dias de alta demanda o processamento de documentos grandes pode levar alguns minutos.
- O banco SQLite local é efêmero em hospedagens como o Streamlit Cloud.
- Tabelas e imagens dentro dos PDFs só são lidas se o texto estiver embutido ou via OCR.

## 13. Evolução futura

- Recuperação híbrida (BM25 + embeddings) e reordenação dos trechos.
- Verificação semântica do resumo (modelo juiz), além da verificação do trecho.
- Extração de valores monetários e prazos em campos tipados, permitindo comparações numéricas e cálculo de cobertura efetiva.
- Suporte a outros ramos (RC Profissional, Cyber) reaproveitando a arquitetura: basta trocar a lista de tópicos.
- Autenticação, múltiplos usuários, banco gerenciado e trilha de auditoria.
- Painel de portfólio: comparar muitas apólices e destacar lacunas de cobertura.
