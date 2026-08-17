"""
Audit en lecture seule des métadonnées de public.documents dans Supabase.

Aucune donnée n'est modifiée.

Usage:
    python audit_supabase_metadata.py
    python audit_supabase_metadata.py --output audit_halex

Variables d'environnement:
    SUPABASE_URL
    SUPABASE_SERVICE_KEY
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

TAILLE_PAGE = 1000

# Champs qui, dans le nouveau modèle Halex, doivent être cohérents pour
# l'ensemble des chunks d'une même source consolidée.
CHAMPS_SOURCE_UNIQUES = (
    "source_courte",
    "type_norme",
    "rang",
    "date",
    "date_publication",
    "historique",
)

# Champs clés attendus sur chaque document. Le script ne bloque rien : il
# signale seulement les absences pour préparer la migration.
CHAMPS_ATTENDUS = (
    "source",
    "source_courte",
    "type_norme",
    "rang",
    "date",
    "date_publication",
    "statut",
    "article",
)

try:
    from schema_metadata import RANGS_PAR_TYPE_NORME  # type: ignore
except Exception:
    RANGS_PAR_TYPE_NORME = {}


def _env_obligatoire(nom: str) -> str:
    valeur = os.getenv(nom)
    if not valeur:
        raise RuntimeError(
            f"Variable d'environnement manquante: {nom}. Vérifiez votre .env."
        )
    return valeur


def _lire_documents(supabase) -> list[dict[str, Any]]:
    lignes: list[dict[str, Any]] = []
    offset = 0
    while True:
        lot = (
            supabase.table("documents")
            .select("id, content, metadata")
            .order("id")
            .range(offset, offset + TAILLE_PAGE - 1)
            .execute()
        ).data or []
        lignes.extend(lot)
        print(f"Lu: {len(lignes)} document(s)", flush=True)
        if len(lot) < TAILLE_PAGE:
            break
        offset += TAILLE_PAGE
    return lignes


def _repr_valeur(v: Any) -> str:
    if v is None:
        return "<null/absent>"
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, sort_keys=True)
    return str(v)


def auditer(lignes: list[dict[str, Any]]) -> dict[str, Any]:
    par_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    erreurs_documents: list[dict[str, Any]] = []

    for row in lignes:
        meta = row.get("metadata") or {}
        source = meta.get("source") or "<source_absente>"
        par_source[str(source)].append(row)

        manquants = [
            cle for cle in CHAMPS_ATTENDUS
            if cle not in meta or meta.get(cle) in ("", None)
        ]
        if manquants:
            erreurs_documents.append(
                {
                    "id": row.get("id"),
                    "source": meta.get("source"),
                    "article": meta.get("article"),
                    "type": "champs_manquants",
                    "detail": manquants,
                }
            )

        type_norme = meta.get("type_norme")
        rang = meta.get("rang")
        if (
            RANGS_PAR_TYPE_NORME
            and type_norme in RANGS_PAR_TYPE_NORME
            and rang != RANGS_PAR_TYPE_NORME[type_norme]
        ):
            erreurs_documents.append(
                {
                    "id": row.get("id"),
                    "source": meta.get("source"),
                    "article": meta.get("article"),
                    "type": "rang_incoherent",
                    "detail": {
                        "type_norme": type_norme,
                        "rang_recu": rang,
                        "rang_attendu": RANGS_PAR_TYPE_NORME[type_norme],
                    },
                }
            )

    resume_sources: list[dict[str, Any]] = []
    incoherences_sources: list[dict[str, Any]] = []

    for source, rows in sorted(par_source.items()):
        metas = [r.get("metadata") or {} for r in rows]
        resume = {
            "source": source,
            "nb_chunks": len(rows),
            "nb_par_statut": dict(
                sorted(Counter(str(m.get("statut")) for m in metas).items())
            ),
        }

        for champ in CHAMPS_SOURCE_UNIQUES:
            valeurs = {_repr_valeur(m.get(champ)) for m in metas}
            resume[champ] = next(iter(valeurs)) if len(valeurs) == 1 else None
            resume[f"{champ}_nb_valeurs"] = len(valeurs)
            if len(valeurs) > 1:
                detail = []
                for valeur in sorted(valeurs):
                    ids = [
                        str(r.get("id"))
                        for r in rows
                        if _repr_valeur((r.get("metadata") or {}).get(champ)) == valeur
                    ]
                    detail.append({"valeur": valeur, "ids": ids[:20], "nb": len(ids)})
                incoherences_sources.append(
                    {
                        "source": source,
                        "champ": champ,
                        "valeurs": detail,
                    }
                )

        resume_sources.append(resume)

    return {
        "genere_utc": datetime.now(timezone.utc).isoformat(),
        "nb_documents": len(lignes),
        "nb_sources": len(par_source),
        "nb_erreurs_documents": len(erreurs_documents),
        "nb_incoherences_sources": len(incoherences_sources),
        "erreurs_documents": erreurs_documents,
        "incoherences_sources": incoherences_sources,
        "resume_sources": resume_sources,
    }


def _ecrire_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _ecrire_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    champs = [
        "source", "nb_chunks", "source_courte", "type_norme", "rang",
        "date", "date_publication", "historique", "nb_par_statut",
        "source_courte_nb_valeurs", "type_norme_nb_valeurs",
        "rang_nb_valeurs", "date_nb_valeurs",
        "date_publication_nb_valeurs", "historique_nb_valeurs",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=champs, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            copie = dict(row)
            copie["nb_par_statut"] = json.dumps(
                copie.get("nb_par_statut", {}), ensure_ascii=False
            )
            writer.writerow(copie)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="audit_halex")
    args = parser.parse_args()

    supabase = create_client(
        _env_obligatoire("SUPABASE_URL"),
        _env_obligatoire("SUPABASE_SERVICE_KEY"),
    )

    lignes = _lire_documents(supabase)
    rapport = auditer(lignes)

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    _ecrire_json(out / "audit_metadata.json", rapport)
    _ecrire_csv(out / "resume_sources.csv", rapport["resume_sources"])

    print("\nAudit terminé — aucune donnée Supabase modifiée.")
    print(f"Documents: {rapport['nb_documents']}")
    print(f"Sources: {rapport['nb_sources']}")
    print(f"Erreurs document: {rapport['nb_erreurs_documents']}")
    print(f"Incohérences source: {rapport['nb_incoherences_sources']}")
    print(f"Rapport: {(out / 'audit_metadata.json').resolve()}")
    print(f"CSV: {(out / 'resume_sources.csv').resolve()}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAudit interrompu.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERREUR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
