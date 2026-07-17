"""
migrer_constitution.py
Convertit les chunks Constitution (ancien format) vers le schéma unifié,
identique à celui du Code pénal. Non destructif : écrit un nouveau fichier.
"""

import json
from pathlib import Path

FICHIER_ENTREE = "documents/constitution_chunks.json"
FICHIER_SORTIE = "documents/constitution_chunks_unifie.json"

# Date de la version amendée — À CONFIRMER (voir note en fin de message).
# Ne bloque pas la suite : ne sert qu'à la résolution de conflits, dormante.
DATE_CONSTITUTION = "2011-05-09"


def migrer():
    chunks = json.loads(Path(FICHIER_ENTREE).read_text(encoding="utf-8"))
    resultats = []

    for c in chunks:
        article = c["article"]
        texte   = c["texte"]

        meta = {
            # champs du schéma unifié (partagés avec le Code pénal)
            "source":     c.get("source", "Constitution de 1987 (amendée)"),
            "type_norme": "constitution",
            "rang":       1,
            "date":       DATE_CONSTITUTION,
            "statut":     "en_vigueur",
            "article":    article,
            # champs préservés de l'ancien découpage (utiles, sans risque) :
            # 'section' distingue loi d'amendement vs corps de la Constitution
            "contexte":   c.get("contexte", ""),
            "section":    c.get("section", ""),
        }

        resultats.append({
            "page_content": f"{article}.- {texte}",   # même forme que le pénal
            "metadata": meta,
        })

    Path(FICHIER_SORTIE).write_text(
        json.dumps(resultats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"OK — {len(resultats)} articles migrés vers le schéma unifié.")
    print(f"Sauvegardé dans {FICHIER_SORTIE}\n")

    print("--- Premier chunk migré ---")
    print(json.dumps(resultats[0], ensure_ascii=False, indent=2)[:400], "...")


if __name__ == "__main__":
    migrer()