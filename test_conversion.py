import pymupdf4llm

texte_markdown = pymupdf4llm.to_markdown(
    "documents/la_constitution_de_1987_amendee.pdf",   # ← METTEZ le nom EXACT de votre PDF
    table_strategy=None,       # désactive les tableaux parasites
    detect_bg_color=False,     # supprime les balises <mark>
)

# On écrit dans un NOUVEAU fichier pour ne pas confondre avec l'ancien
with open("documents/constitution_clean.md", "w", encoding="utf-8") as f:
    f.write(texte_markdown)

# Auto-vérification : ces deux compteurs DOIVENT être à 0 si la correction a pris
nb_tableaux = texte_markdown.count("|---|")
nb_marks = texte_markdown.count("<mark>")
print("Ecrit dans : documents/constitution_clean.md")
print(f"Lignes de tableau restantes : {nb_tableaux}  (doit etre 0)")
print(f"Balises <mark> restantes    : {nb_marks}  (doit etre 0)")