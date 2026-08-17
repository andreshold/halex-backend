"""
Validation locale rapide d'un fichier JSON Halex avant upload.

Ce script vérifie uniquement les règles normatives centrales et la cohérence
par source. Il ne remplace pas /admin/validation, qui reste l'autorité finale.

Usage:
    python verifier_json_halex.py code-penal.json
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from normes_config import metadata_normative_valide


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("fichier")
    args = parser.parse_args()

    path = Path(args.fichier)
    texte = unicodedata.normalize("NFC", path.read_text(encoding="utf-8"))
    data = json.loads(texte)

    if not isinstance(data, list):
        raise ValueError("La racine JSON doit être une liste")

    erreurs: list[str] = []
    par_source: dict[str, list[tuple[int, dict]]] = defaultdict(list)

    for i, item in enumerate(data):
        if not isinstance(item, dict):
            erreurs.append(f"[{i}] objet JSON attendu")
            continue

        content = item.get("page_content")
        meta = item.get("metadata")

        if not isinstance(content, str) or not content.strip():
            erreurs.append(f"[{i}] page_content vide/invalide")

        if not isinstance(meta, dict):
            erreurs.append(f"[{i}] metadata absente/invalide")
            continue

        ok, errs = metadata_normative_valide(meta)
        for err in errs:
            erreurs.append(
                f"[{i}] {meta.get('source')} / {meta.get('article')}: {err}"
            )

        source = meta.get("source")
        if isinstance(source, str) and source.strip():
            par_source[source].append((i, meta))
        else:
            erreurs.append(f"[{i}] metadata.source absente/invalide")

    # Cohérence des valeurs qui décrivent la source consolidée.
    champs_uniques = (
        "source_courte",
        "type_norme",
        "rang",
        "date",
        "date_publication",
        "historique",
    )

    for source, rows in sorted(par_source.items()):
        for champ in champs_uniques:
            valeurs = {json.dumps(meta.get(champ), ensure_ascii=False, sort_keys=True)
                       for _, meta in rows}
            if len(valeurs) > 1:
                erreurs.append(
                    f"Source {source!r}: {champ!r} possède plusieurs valeurs: "
                    + ", ".join(sorted(valeurs))
                )

    if erreurs:
        print(f"ÉCHEC — {len(erreurs)} erreur(s):")
        for err in erreurs[:200]:
            print(" -", err)
        if len(erreurs) > 200:
            print(f" ... {len(erreurs) - 200} erreur(s) supplémentaire(s)")
        raise SystemExit(1)

    print("OK — validation normative locale réussie.")
    print(f"Chunks: {len(data)}")
    print(f"Sources: {len(par_source)}")
    for source, rows in sorted(par_source.items()):
        meta = rows[0][1]
        print(
            f" - {source}: {len(rows)} chunks | "
            f"type={meta.get('type_norme')} | rang={meta.get('rang')} | "
            f"date={meta.get('date')} | publication={meta.get('date_publication')}"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERREUR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
