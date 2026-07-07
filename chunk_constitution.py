"""
Découpage de documents/constitution_clean.md en articles individuels pour un
système RAG juridique haïtien.

Chaque article devient un chunk INTÈGRE (jamais coupé en deux) car il sera
cité tel quel à des citoyens. Voir documents/constitution_chunks.json pour
le résultat et le message de conversation associé pour le détail des choix
(gestion des deux formats d'articles, reconstruction du contexte TITRE/
CHAPITRE/SECTION, cas particuliers rencontrés dans le texte source).
"""
import json
import re

IN_PATH = "documents/constitution_clean.md"
OUT_PATH = "documents/constitution_chunks.json"

SOURCE_CONSTITUTION = "Constitution de 1987 Amendée"
SOURCE_AMENDEMENT = "Loi Constitutionnelle du 9 mai 2011 (amendement)"

# Numéro d'article toléré : "1", "1-1", "8-1", "121.5", "134 bis", "190bis",
# "190bis.1", "190ter.10", "258.2", etc.
NUM_RE = r"\d+(?:\s?(?:bis|ter))?(?:[.\-]\d+)*"
ARTICLE_START_RE = re.compile(rf"^Article\s+({NUM_RE})(.*)$")

UPPER_START_RE = re.compile(r"^[A-ZÀ-Ý]")


def parse_article_header(line: str):
    """Retourne (numero, texte) si la ligne démarre bien un article, sinon None.

    Distingue un vrai en-tête ("Article 8-1:", "Article 1.-", "Article 87
    L'Exécutif...") d'une simple mention d'articles dans une phrase
    ("Article 111.5, 111.6 et 111.7 de la Constitution de 1987 sont abrogés."),
    qui doit rester rattachée à l'article précédent plutôt que de créer un
    faux chunk.
    """
    m = ARTICLE_START_RE.match(line)
    if not m:
        return None
    num, rest = m.group(1), m.group(2)

    # Format loi d'amendement : "Article 1.- Texte..."
    m2 = re.match(r"^\.\-\s*(.*)$", rest)
    if m2:
        return num, m2.group(1), "dotdash"

    # Format standard avec deux-points, espace(s) tolérés avant : "Article 8-1: ..."
    m2 = re.match(r"^\s*:\s*(.*)$", rest)
    if m2:
        return num, m2.group(1), "colon"

    # Deux-points manquant dans la source, mais suivi directement d'une
    # majuscule qui démarre la phrase : "Article 87 L'Exécutif est assisté..."
    m2 = re.match(r"^\s+(.*)$", rest)
    if m2 and UPPER_START_RE.match(m2.group(1)):
        return num, m2.group(1), "space"

    return None


def clean_heading_text(text: str) -> str:
    """Certaines lignes de titre du document source sont polluées par du texte
    d'abrogation qui s'est retrouvé collé dessus, ex:
    '## DE LA COMMISSION DE CONCILIATION Les articles 206 et 206-1 ... abrogés.'
    On coupe à 'Les articles' pour ne garder que le vrai titre.
    """
    idx = text.find(" Les articles ")
    if idx != -1:
        return text[:idx].strip()
    return text


def build_contexte(titre, chapitre, section, subtitle_parts):
    subtitle = " ".join(subtitle_parts).strip()
    parts = [p for p in [titre, chapitre, section, subtitle] if p]
    return " > ".join(parts)


PREFIXES = ("TITRE", "CHAPITRE", "SECTION")


def tokenize(raw_lines):
    """Regroupe les lignes en blocs : ('run', [lignes de titre]) ou
    ('article', ligne). Un run se termine dès qu'un article apparaît."""
    blocks = []
    current_run = []
    for line in raw_lines:
        if not line:
            continue
        if line.startswith("# ") and not line.startswith("## "):
            if current_run:
                blocks.append(("run", current_run))
                current_run = []
            continue
        if line.startswith("## "):
            current_run.append(clean_heading_text(line[3:].strip()))
            continue
        if current_run:
            blocks.append(("run", current_run))
            current_run = []
        blocks.append(("article", line))
    if current_run:
        blocks.append(("run", current_run))
    return blocks


def main():
    with open(IN_PATH, encoding="utf-8") as f:
        raw_lines = [l.strip() for l in f]

    chunks = []

    titre = None
    chapitre = None
    section = None
    subtitle_parts = []

    last_constitution_chunk = None  # pour rattacher les fausses mentions d'article

    for kind, payload in tokenize(raw_lines):
        if kind == "run":
            run_lines = payload
            has_prefixed = any(t.startswith(PREFIXES) for t in run_lines)
            for i, text in enumerate(run_lines):
                if text.startswith("TITRE"):
                    titre, chapitre, section, subtitle_parts = text, None, None, []
                elif text.startswith("CHAPITRE"):
                    chapitre, section, subtitle_parts = text, None, []
                elif text.startswith("SECTION"):
                    section, subtitle_parts = text, []
                elif i == 0 and not has_prefixed:
                    # Titre "orphelin" (ex: "DE LA FONCTION PUBLIQUE") qui ne
                    # porte pas le mot TITRE/CHAPITRE/SECTION mais démarre à
                    # lui seul une nouvelle grande section (aucun autre titre
                    # ne suit dans ce même bloc). On le traite comme un
                    # nouveau niveau TITRE. Voir cas "DE LA COMMISSION DE
                    # CONCILIATION" (a un vrai CHAPITRE juste après dans son
                    # bloc) pour le cas où cette règle NE doit PAS s'appliquer.
                    titre, chapitre, section, subtitle_parts = text, None, None, []
                else:
                    subtitle_parts.append(text)
            continue

        line = payload
        parsed = parse_article_header(line)
        if parsed is None:
            # Ni un titre, ni un article : rattachement à l'article précédent
            # (ex: "Article 111.5, 111.6 et 111.7 de la Constitution de 1987
            # sont abrogés." isolé entre deux vrais articles).
            if last_constitution_chunk is not None:
                last_constitution_chunk["texte"] += " " + line
            continue

        num, texte, fmt = parsed
        article_label = f"Article {num}"

        is_amendment_closing = (
            fmt == "colon"
            and "Journal Officiel" in texte
            and "entre en vigueur" in texte
        )

        if fmt == "dotdash" or is_amendment_closing:
            chunks.append({
                "article": article_label,
                "texte": texte,
                "source": SOURCE_AMENDEMENT,
                "contexte": "Loi d'amendement",
                "section": "loi_amendement",
            })
            last_constitution_chunk = None
            continue

        chunk = {
            "article": article_label,
            "texte": texte,
            "source": SOURCE_CONSTITUTION,
            "contexte": build_contexte(titre, chapitre, section, subtitle_parts),
            "section": "constitution",
        }
        chunks.append(chunk)
        last_constitution_chunk = chunk

        # Défaut connu de la source : le titre "TITRE VIII - DE L'ECONOMIE, DE
        # L'AGRICULTURE ET DE L'ENVIRONNEMENT" n'existe pas comme ligne "## "
        # séparée, il a été collé à la fin du texte de l'Article 244. On le
        # détache et on s'en sert comme nouveau niveau TITRE pour la suite.
        m = re.search(r"\s+De l’ECONOMIE, de l’AGRICULTURE et de l’ENVIRONNEMENT$", chunk["texte"])
        if m:
            chunk["texte"] = chunk["texte"][:m.start()].strip()
            titre = "DE L’ECONOMIE, DE L’AGRICULTURE ET DE L’ENVIRONNEMENT"
            chapitre, section, subtitle_parts = None, None, []

    # Chunk spécial "Préambule" : le vrai texte du préambule est imbriqué dans
    # l'Article 2.- de la loi d'amendement ("Le préambule de la Constitution
    # se lit désormais comme suit : ...").
    article_2 = next(c for c in chunks if c["section"] == "loi_amendement" and c["article"] == "Article 2")
    marker = "Le Peuple Haïtien proclame la présente Constitution"
    idx = article_2["texte"].find(marker)
    if idx == -1:
        raise RuntimeError("Marqueur du préambule introuvable dans l'Article 2 — vérifier le texte source.")
    preambule_texte = article_2["texte"][idx:].strip()
    preambule_chunk = {
        "article": "Préambule",
        "texte": preambule_texte,
        "source": SOURCE_CONSTITUTION,
        "contexte": "Préambule",
        "section": "constitution",
    }
    # Inséré en tête, à sa place logique dans le document.
    chunks.insert(0, preambule_chunk)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    # --- Vérifications ---
    print(f"Total chunks extraits : {len(chunks)}")

    print("\n-- 2 premiers chunks --")
    for c in chunks[:2]:
        print(json.dumps(c, ensure_ascii=False, indent=2))

    mid = len(chunks) // 2
    print("\n-- 2 chunks du milieu --")
    for c in chunks[mid:mid + 2]:
        print(json.dumps(c, ensure_ascii=False, indent=2))

    print("\n-- 2 derniers chunks --")
    for c in chunks[-2:]:
        print(json.dumps(c, ensure_ascii=False, indent=2))

    print("\n-- Articles suspects (texte < 20 caractères) --")
    suspects = [c for c in chunks if len(c["texte"]) < 20]
    if suspects:
        for c in suspects:
            print(f"  {c['article']!r} ({c['section']}): {c['texte']!r}")
    else:
        print("  Aucun.")

    # Détection de doublons de numéro d'article (numéros réutilisés entre
    # sections différentes, ou coquilles du document source).
    from collections import Counter
    counts = Counter((c["article"], c["section"]) for c in chunks)
    dups = [k for k, v in counts.items() if v > 1]
    print("\n-- Doublons (même article + même section) --")
    if dups:
        for k in dups:
            print(f"  {k}")
    else:
        print("  Aucun.")


if __name__ == "__main__":
    main()
