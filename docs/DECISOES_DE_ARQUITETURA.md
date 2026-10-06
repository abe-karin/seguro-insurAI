# Decisões de arquitetura e motivos da refatoração

Este documento registra **o que mudou em relação à primeira versão do MVP** (commits `projeto final` e
`ativar tesseract no streamlit cloud`) e **por quê**. A base (agentes especializados, Streamlit, SQLite,
schemas Pydantic) foi mantida; mudou o miolo, depois de testar a primeira versão com três documentos reais
do mercado (condições gerais D&O da Porto, AXA e Allianz, de 52 a 104 páginas e 175 mil a 250 mil caracteres).

## O que a primeira versão fazia e onde falhava

| # | Problema observado | Efeito |
|---|---|---|
| 1 | O texto era cortado a cada 60.000 caracteres, no meio de frases, e as listas dos lotes eram apenas concatenadas | Em documentos reais, 2 a 4 cortes mal posicionados e a mesma cobertura repetida 3 ou 4 vezes |
| 2 | Resposta inválida ou truncada do LLM virava `{}` sem aviso | O usuário via uma apólice "vazia" sem saber que a extração falhou |
| 3 | O PDF do comparativo saía só com os cabeçalhos das tabelas (linhas descartadas por um `try/except` silencioso) e com `**` soltos | Exportação inutilizável |
| 4 | A comparação sem LLM comparava nomes de cobertura por igualdade exata | Com texto livre, tudo aparecia como "diferente" |
| 5 | Nada indicava de onde cada dado saiu | Impossível conferir uma extração; risco de alucinação sem detecção |
| 6 | Não havia consulta às informações (etapa 5 do enunciado) | Requisito não atendido |
| 7 | Chamada ao LLM duplicada em dois agentes, com SDK e modelos desatualizados (`google-generativeai` descontinuado; modelos que retornam 404) | Falhas em produção e manutenção em dobro |
| 8 | README citava LangChain, Google Vision e uma pasta `utils/` inexistentes; faltavam LICENSE, testes e pasta de artefatos | Documentação desalinhada do código; requisitos de entrega ausentes |
| 9 | Bloco de chave de API fora da barra lateral (erro de indentação) | Interface com elementos fora do lugar |

## Decisões

### D1. Ficha técnica D&O com tópicos fixos
Os 22 tópicos (base de acionamento, retroatividade, prazos de aviso, Side A/B/C, custos de defesa,
exclusões-chave, mudança de controle…) são perguntados **a todos os documentos**. Assim as respostas ficam
alinhadas e a comparação deixa de depender de nomes livres. Os documentos de teste são *condições gerais*, sem
prêmio ou segurado; por isso o valor está nas cláusulas, não nos campos cadastrais.

### D2. Toda informação cita página e trecho, e o trecho é verificado
O modelo devolve `página + trecho literal` por item. O sistema confere se o trecho existe na página (com
tolerância a acentos e quebras de linha), corrige erro de uma página e marca o restante como não verificado.
É a defesa prática contra alucinação e o que permite ao usuário auditar o resultado.

### D3. Lotes por página, em paralelo
Documentos grandes são divididos **apenas em fronteiras de página** (lotes de ~90 mil caracteres), processados em
paralelo e fundidos com remoção de duplicatas (sem acentos e sem diferença de caixa). Resolve o corte no meio de
frase e reduz a latência e os estouros de tempo limite. A fusão preserva a ordem das páginas.

### D4. Comparação em duas etapas: alinhar e julgar
1. **Alinhamento determinístico**: os valores de cada tópico vêm da ficha extraída, nunca do LLM.
2. **Julgamento pelo LLM**: recebe só os tópicos divergentes e devolve relevância, apólice mais favorável,
   resumo e recomendação.

O modelo não pode inventar valores; se falhar, a comparação segue em modo determinístico. Passou a aceitar 2 a 3
apólices.

### D5. Consulta com recuperação lexical (BM25) + citação
Para "consultar as informações" usamos BM25 por página (por apólice, para que todas fiquem representadas) e o LLM
responde só com os trechos recuperados, citando `[apólice, p. N]`. Escolhemos BM25 em vez de embeddings porque
não exige serviço adicional, é explicável e funciona bem em texto jurídico com terminologia estável.

### D6. Um único cliente de LLM
`agents/llm_client.py` concentra provedores, saída estruturada, tempo limite, retentativa em 429/503 e **rodízio
entre modelos** quando um está sobrecarregado ou indisponível. Falhas viram `LLMError`; nada é engolido. Para o
Gemini 3.x o raciocínio interno é limitado (`thinking_level=low`), pois em tarefas guiadas por schema chamadas
curtas chegaram a levar minutos sem esse limite.

### D7. Armazenamento guarda o texto de cada página
A consulta e a conferência de fontes precisam do texto original, que antes era descartado. Nova tabela
`policy_pages`; a conexão é criada sob demanda para permitir testes e deploy em outro diretório.

### D8. PDFs gerados direto dos objetos
O relatório é montado com a API de tabelas do `fpdf2` a partir dos dados estruturados, e não convertendo
Markdown linha a linha. O comparativo sai em paisagem, com uma coluna por apólice. Um teste de regressão lê o PDF
de volta e confere que as linhas estão presentes.

### D9. Compatibilidade e limpeza
Os scripts da primeira versão (`seed_demo_data.py`, `validate.py`, `debug_pdf.py`) foram mantidos e continuam
funcionando; o `seed_demo_data.py` permite demonstrar a interface sem chave de API. O banco passou a se chamar
`doshield_v2.db`, porque um `doshield.db` com o schema antigo derrubaria o app. A descrição de coberturas e exclusões
é opcional, já que o modelo às vezes a omite. Removidas as dependências sem uso (`langchain*`, `google-generativeai`)
e adicionados `LICENSE` (MIT), `.env.example`, testes, `scripts/processar_pdfs.py` e `Projeto_Final_Artefatos/`.

## Preservado da primeira versão
Estratégia de OCR em camadas e localização do Tesseract (incluindo `storage/tessdata`), a separação em agentes,
as telas de apólices e histórico, a identidade visual e o ajuste de Linux/Streamlit Cloud (`packages.txt`).
