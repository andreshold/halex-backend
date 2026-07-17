"""
decoupeur_unifie.py
Découpe un texte de loi (Markdown) en un chunk par article + métadonnées.
Réutilisable ; ici configuré pour le Code pénal.
"""

import re
import json
from pathlib import Path

# ── 1. CONFIGURATION DU DOCUMENT ──────────────────────────────
#    (seul bloc à modifier pour un autre texte)
FICHIER_MD     = "documents/code_penal.md"
FICHIER_SORTIE = "documents/code_penal_chunks.json"

METADONNEES = {
    "source":     "Code pénal",
    "type_norme": "code",
    "rang":       3,
    "date":       "1835-01-01",   # ← à remplir (voir note en fin de message)
    "statut":     "en_vigueur",   # ancien code, réellement appliqué
}

# ── 2. DÉTECTION DES EN-TÊTES D'ARTICLES ──────────────────────
# Variantes réelles observées :
#   **Art 1** .-      (pas de point après Art)
#   **Art. 2** .-     (point + espace)
#   **Art. 9**.-      (pas d'espace avant .-)
#   **Art. 19** .- Bis (D. ...)   (article « bis »)
EN_TETE_ARTICLE = re.compile(
    r'\*\*\s*Art(?:icle)?\.?\s*'   # **Art / **Art. / **Article
    r'(\d+)'                       # numéro principal
    r'\s*\*\*'                     # fin du gras
    r'\s*\.?\s*-?\s*'              # séparateur .- / .- / .
    r'(bis|ter|quater)?',          # suffixe éventuel
    re.IGNORECASE,
)


def label(num: str, suffixe: str | None) -> str:
    return f"Article {num}" + (f" {suffixe.lower()}" if suffixe else "")


def decouper(texte_md: str, meta_base: dict) -> list[dict]:
    reperes = list(EN_TETE_ARTICLE.finditer(texte_md))
    if not reperes:
        print("ATTENTION — aucun article détecté : le motif ne correspond pas.")
        return []

    articles = []
    for i, m in enumerate(reperes):
        art = label(m.group(1), m.group(2))
        debut = m.end()
        fin   = reperes[i + 1].start() if i + 1 < len(reperes) else len(texte_md)
        corps = texte_md[debut:fin].strip()
        if not corps:                      # en-tête vide → artefact
            continue
        meta = dict(meta_base)
        meta["article"] = art
        articles.append({
            "page_content": f"{art}.- {corps}",
            "metadata": meta,
        })
    return articles


def diagnostics(articles: list[dict]) -> None:
    labels = [a["metadata"]["article"] for a in articles]
    print(f"OK — {len(articles)} articles découpés.")

    # vrais doublons (label identique, Bis inclus)
    doublons = sorted({l for l in labels if labels.count(l) > 1})
    print(f"Doublons : {doublons[:20] if doublons else 'aucun'}")

    # trous dans la numérotation
    nums = sorted({int(re.match(r'Article (\d+)', l).group(1)) for l in labels})
    if nums:
        manquants = sorted(set(range(nums[0], nums[-1] + 1)) - set(nums))
        print(f"Plage : Article {nums[0]} → Article {nums[-1]}")
        print(f"Numéros absents : {manquants[:30] if manquants else 'aucun'}")

    if articles:
        print("\n--- Premier article ---")
        print(articles[0]["page_content"][:180], "...")
        print("\n--- Dernier article ---")
        print(articles[-1]["page_content"][:180], "...")


def main():
    chemin = Path(FICHIER_MD)
    if not chemin.exists():
        print(f"ERREUR — fichier introuvable : {chemin}")
        return
    articles = decouper(chemin.read_text(encoding="utf-8"), METADONNEES)
    diagnostics(articles)
    Path(FICHIER_SORTIE).write_text(
        json.dumps(articles, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nSauvegardé dans {FICHIER_SORTIE}")


if __name__ == "__main__":
    main()