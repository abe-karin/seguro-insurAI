import sys
sys.path.insert(0, '.')
from fpdf import FPDF

def safe_text(text):
    import unicodedata
    result = []
    for ch in text:
        try:
            ch.encode("latin-1")
            result.append(ch)
        except (UnicodeEncodeError, ValueError):
            normalized = unicodedata.normalize("NFD", ch)
            ascii_ch = normalized.encode("ascii", "ignore").decode("ascii")
            result.append(ascii_ch if ascii_ch else "?")
    return "".join(result)

safe_title = safe_text("Relatorio D&O")

class PDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(60, 60, 60)
        self.cell(0, 8, safe_title, new_x="LMARGIN", new_y="NEXT", align="C")
        self.set_draw_color(180, 180, 180)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"D&O Shield - Pag. {self.page_no()}", align="C")

pdf = PDF()
pdf.set_margins(15, 20, 15)
pdf.set_auto_page_break(auto=True, margin=20)
pdf.add_page()

sample_md = """# Relatorio de Apolice

## 1. Dados da Apolice

| Campo | Valor |
|-------|-------|
| Seguradora | AIG Seguros |
| Premio | R$ 210.000 |

## 2. Coberturas

- Side A: protecao individual
- Side B: reembolso empresa

## 3. Exclusoes

- Fraude dolosa
- Proveito ilicito
"""

for line in sample_md.split("\n"):
    stripped = safe_text(line.strip())
    try:
        if stripped.startswith("# "):
            pdf.set_font("Helvetica", "B", 16)
            pdf.set_text_color(30, 60, 120)
            pdf.multi_cell(0, 10, stripped[2:])
            pdf.ln(2)
        elif stripped.startswith("## "):
            pdf.set_font("Helvetica", "B", 13)
            pdf.set_text_color(50, 80, 150)
            pdf.multi_cell(0, 8, stripped[3:])
            pdf.ln(1)
        elif stripped.startswith("| ") and "|" in stripped:
            cells = [c.strip() for c in stripped.split("|") if c.strip()]
            if cells and not all(c.startswith("-") for c in cells):
                pdf.set_font("Helvetica", size=7)
                pdf.set_text_color(40, 40, 40)
                truncated = [c[:35] for c in cells[:4]]
                row_text = " | ".join(truncated)
                pdf.multi_cell(0, 5, row_text)
        elif stripped.startswith("- "):
            pdf.set_font("Helvetica", size=10)
            pdf.set_text_color(40, 40, 40)
            pdf.multi_cell(0, 6, "  * " + stripped[2:])
        elif stripped:
            pdf.set_font("Helvetica", size=10)
            pdf.set_text_color(40, 40, 40)
            pdf.multi_cell(0, 6, stripped)
        else:
            pdf.ln(2)
    except Exception as e:
        print(f"ERROR on line '{stripped}': {e}")

result = bytes(pdf.output())
print(f"PDF generated: {len(result)} bytes")
with open("storage/test_output.pdf", "wb") as f:
    f.write(result)
print("Saved to storage/test_output.pdf")
