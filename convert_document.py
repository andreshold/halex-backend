"""
Conversion de la Constitution de 1987 (Amendée) en Markdown propre pour un usage RAG.

Stratégie : pymupdf4llm produit des <mark>, des tableaux et des <br> parasites.
On utilise donc l'extraction texte brute de PyMuPDF (fitz), puis on reconstruit
des paragraphes propres article par article avec un script de nettoyage.
"""
import re
import fitz

PDF_PATH = "documents/code_du_travail.pdf"
OUT_PATH = "documents/code_du_travail.md"

TITLE = "Le Code du Travail"

# Une ligne qui commence un nouvel article : "Article 1.-", "Article 1:", "Article 1-1:",
# "Article 190ter.5 :", etc. On tolère zero ou plusieurs espaces avant le numero pour
# rattraper les cas ou "Article" est colle au chiffre (ex: "Article265-1:").
ARTICLE_RE = re.compile(r"^Article\s*\d")

# Ligne "titre" en MAJUSCULES (TITRE I, CHAPITRE II, SECTION A, DU SENAT, ...)
def is_header_line(line: str) -> bool:
    letters = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ]", "", line)
    return bool(letters) and letters == letters.upper() and not ARTICLE_RE.match(line)


def extract_raw_lines(pdf_path: str) -> list[str]:
    doc = fitz.open(pdf_path)
    lines = []
    for page in doc:
        text = page.get_text()
        for line in text.split("\n"):
            line = line.strip()
            if line:
                lines.append(line)
    return lines


def fix_glued_words(line: str) -> str:
    # "Article111.5" / "Article265-1" -> "Article 111.5" / "Article 265-1"
    line = re.sub(r"\bArticle(?=\d)", "Article ", line)
    # Coquille du document source : "286,Atik 285" -> "286, Atik 285" (espace manquant)
    line = re.sub(r",(?=Atik)", ", ", line)
    return line


# Lignes purement decoratives (separateurs "***" du PDF source) : sans aucune
# lettre ni chiffre, elles n'apportent aucun contenu juridique et sont ignorees.
DECORATIVE_RE = re.compile(r"^[^A-Za-zÀ-ÖØ-öø-ÿ0-9]+$")


def build_paragraphs(lines: list[str]) -> list[tuple[str, str]]:
    """Retourne une liste de (type, texte) ou type est 'title', 'header' ou 'para'."""
    paragraphs: list[tuple[str, str]] = []
    buffer: list[str] = []
    buffer_type = "para"

    def flush():
        if buffer:
            text = " ".join(buffer)
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                paragraphs.append((buffer_type, text))
            buffer.clear()

    for raw_line in lines:
        if DECORATIVE_RE.match(raw_line):
            continue

        line = fix_glued_words(raw_line)

        if line == TITLE:
            flush()
            paragraphs.append(("title", TITLE))
            buffer_type = "para"
            continue

        if ARTICLE_RE.match(line):
            flush()
            buffer_type = "para"
            buffer.append(line)
            continue

        if is_header_line(line):
            flush()
            buffer_type = "header"
            buffer.append(line)
            continue

        # Ligne de continuation (corps de texte, alinea a)/b)/1)/2)... ) :
        # on la rattache au paragraphe en cours pour garder l'article
        # entier sur un seul paragraphe continu.
        buffer.append(line)

    flush()
    return paragraphs


def render_markdown(paragraphs: list[tuple[str, str]]) -> str:
    out = []
    for kind, text in paragraphs:
        if kind == "title":
            out.append(f"# {text}")
        elif kind == "header":
            out.append(f"## {text}")
        else:
            out.append(text)
    return "\n\n".join(out) + "\n"


def main():
    lines = extract_raw_lines(PDF_PATH)
    paragraphs = build_paragraphs(lines)
    markdown = render_markdown(paragraphs)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(markdown)

    nb_mark = markdown.count("<mark>")
    nb_br = markdown.count("<br>")
    nb_table_rows = sum(1 for l in markdown.split("\n") if l.strip().startswith("|"))

    print(f"Ecrit dans : {OUT_PATH}")
    print(f"Paragraphes/articles/titres : {len(paragraphs)}")
    print(f"Balises <mark> restantes    : {nb_mark} (doit etre 0)")
    print(f"Balises <br> restantes      : {nb_br} (doit etre 0)")
    print(f"Lignes de tableau restantes : {nb_table_rows} (doit etre 0)")


if __name__ == "__main__":
    main()
