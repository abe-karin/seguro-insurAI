import sys
sys.path.insert(0, '.')
from storage.database import list_policies, load_policy
from agents.comparison_agent import compare_policies
from agents.report_agent import generate_policy_pdf, generate_comparison_pdf, generate_policy_markdown

policies = list_policies()
print("Policies in DB:", len(policies))
for p in policies:
    pid = p["id"]
    fn = p["filename"]
    seg = p["seguradora"]
    print(f"  ID={pid}: {fn} / {seg}")

a1 = load_policy(policies[-2]["id"])
a2 = load_policy(policies[-1]["id"])
print("Loaded a1:", a1.nome_arquivo, "coberturas=", len(a1.coberturas), "exclusoes=", len(a1.exclusoes))
print("Loaded a2:", a2.nome_arquivo, "coberturas=", len(a2.coberturas), "exclusoes=", len(a2.exclusoes))

md = generate_policy_markdown(a1)
print("Markdown chars:", len(md))

pdf_bytes = generate_policy_pdf(a1)
print("Policy PDF bytes:", len(pdf_bytes))

rel = compare_policies(a1, a2, use_llm=False)
grupos = rel.por_categoria()
print("Comparison diffs - coberturas:", len(grupos.get("cobertura", [])), "exclusoes:", len(grupos.get("exclusao", [])))
print("Resumo:", rel.resumo_executivo[:100])

cmp_pdf = generate_comparison_pdf(rel)
print("Comparison PDF bytes:", len(cmp_pdf))
print("ALL TESTS PASSED")
