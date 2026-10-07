# Projeto_Final_Artefatos

Artefatos de entrega do Projeto Final (InsurMinds / I2A2).

| Arquivo | Conteúdo |
|---|---|
| `InsurMinds_Projeto_Final.pptx` | Pitch Deck do projeto 
[`InsurMinds_Projeto_Final.pdf`](InsurMinds_Projeto_Final.pdf)|
| `InsurMinds_Projeto_Final.mp4` | Vídeo de apresentação (máximo de 5 minutos) [InsurMinds_Projeto_Final](https://youtu.be/ERLBlxEzZ6Y)](https://youtu.be/ERLBlxEzZ6Y)|
| `relatorio_tecnico.pdf` | Relatório técnico (mesmo conteúdo de [`docs/relatorio_tecnico.md`](../docs/relatorio_tecnico.md)) |
| `exemplos/` | Relatórios gerados pela própria plataforma a partir de documentos reais (ficha técnica de cada apólice e comparativo) |

Os exemplos são reproduzíveis com:

```bash
python scripts/processar_pdfs.py <apolice_a.pdf> <apolice_b.pdf> --comparar --saida Projeto_Final_Artefatos/exemplos
```
