import pymupdf4llm

PDF_ENTREE = "documents/code_penal.pdf"   # ← mets le nom exact ici
MD_SORTIE  = "documents/code_penal.md"

md = pymupdf4llm.to_markdown(
    PDF_ENTREE,
    table_strategy=None,
    detect_bg_color=False,
)

with open(MD_SORTIE, "w", encoding="utf-8") as f:
    f.write(md)

print(f"OK — {len(md)} caractères écrits dans {MD_SORTIE}")