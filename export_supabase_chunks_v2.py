"""Export des chunks Halex depuis Supabase vers des JSON éditables.

Usage:
    python export_supabase_chunks.py
    python export_supabase_chunks.py --output exports_halex
    python export_supabase_chunks.py --single-file
    python export_supabase_chunks.py --raw-backup

Variables d'environnement requises:
    SUPABASE_URL
    SUPABASE_SERVICE_KEY

Le format éditable produit est compatible avec ingestion_admin.py:
[
  {
    "page_content": "...",
    "metadata": {...}
  }
]

Par sécurité, les métadonnées générées exclusivement côté serveur
(ex. lot_ingestion, date_ingestion) sont retirées des fichiers éditables.
Aucune ligne n'est modifiée ou supprimée dans Supabase.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

TAILLE_PAGE = 1000

try:
    # Si le script est exécuté depuis le projet Halex, on réutilise la
    # définition officielle des métadonnées interdites à l'import.
    from schema_metadata import CLES_METADATA_INTERDITES  # type: ignore
except Exception:
    # Repli minimal correspondant aux champs ajoutés par ingestion_admin.py.
    CLES_METADATA_INTERDITES = {"lot_ingestion", "date_ingestion"}


def _env_obligatoire(nom: str) -> str:
    valeur = os.getenv(nom)
    if not valeur:
        raise RuntimeError(
            f"Variable d'environnement manquante: {nom}. "
            "Vérifiez votre fichier .env."
        )
    return valeur


LONGUEUR_MAX_SLUG_SOURCE = 64


def _nom_fichier_source(source: str) -> str:
    """Construit un nom de fichier court, stable et unique.

    Windows applique encore souvent une limite pratique d'environ 260
    caractères sur le chemin complet. Un libellé juridique très long peut
    donc faire échouer Path.write_text() même si le téléchargement Supabase
    a parfaitement réussi. On tronque volontairement le slug et on conserve
    un hash de 8 caractères pour éviter les collisions.
    """
    normalise = unicodedata.normalize("NFKD", source)
    ascii_texte = normalise.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", ascii_texte).strip("_").lower()
    if not slug:
        slug = "source"

    slug = slug[:LONGUEUR_MAX_SLUG_SOURCE].rstrip("_") or "source"

    # Empêche deux libellés différents, y compris avec le même début tronqué,
    # de produire le même nom de fichier.
    suffixe = hashlib.sha1(source.encode("utf-8")).hexdigest()[:8]
    return f"{slug}_{suffixe}.json"


def _metadata_editable(metadata: dict[str, Any] | None) -> dict[str, Any]:
    meta = dict(metadata or {})
    for cle in CLES_METADATA_INTERDITES:
        meta.pop(cle, None)
    return meta


def _cle_tri(row: dict[str, Any]) -> tuple:
    meta = row.get("metadata") or {}
    ordre = meta.get("ordre")
    if isinstance(ordre, int) and not isinstance(ordre, bool):
        return (0, ordre, str(meta.get("article", "")), str(row.get("id", "")))
    return (1, str(meta.get("article", "")), str(row.get("id", "")))


def _lire_documents(supabase, inclure_embedding: bool = False) -> list[dict[str, Any]]:
    colonnes = "id, content, metadata"
    if inclure_embedding:
        colonnes += ", embedding"

    lignes: list[dict[str, Any]] = []
    offset = 0

    while True:
        reponse = (
            supabase.table("documents")
            .select(colonnes)
            .order("id")
            .range(offset, offset + TAILLE_PAGE - 1)
            .execute()
        )
        lot = reponse.data or []
        lignes.extend(lot)

        print(f"Téléchargé: {len(lignes)} ligne(s)", flush=True)

        if len(lot) < TAILLE_PAGE:
            break
        offset += TAILLE_PAGE

    return lignes


def _ecrire_json(path: Path, contenu: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(contenu, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def exporter(args: argparse.Namespace) -> Path:
    url = _env_obligatoire("SUPABASE_URL")
    service_key = _env_obligatoire("SUPABASE_SERVICE_KEY")
    supabase = create_client(url, service_key)

    horodatage = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dossier = Path(args.output) / f"halex_export_{horodatage}"
    dossier.mkdir(parents=True, exist_ok=False)

    lignes = _lire_documents(supabase, inclure_embedding=args.raw_backup)
    if not lignes:
        print("La table documents est vide.")
        return dossier

    # Snapshot avec IDs pour pouvoir faire plus tard une migration metadata
    # en place sans supprimer/recréer les embeddings.
    snapshot_ids = [
        {
            "id": row.get("id"),
            "content": row.get("content"),
            "metadata": row.get("metadata") or {},
        }
        for row in lignes
    ]
    _ecrire_json(dossier / "snapshot_documents_avec_ids.json", snapshot_ids)

    if args.raw_backup:
        _ecrire_json(dossier / "raw_backup_documents.json", lignes)

    editables: list[dict[str, Any]] = []
    par_source: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in sorted(lignes, key=_cle_tri):
        meta = _metadata_editable(row.get("metadata"))
        chunk = {
            "page_content": row.get("content") or "",
            "metadata": meta,
        }
        editables.append(chunk)
        source = str(meta.get("source") or "Source_inconnue")
        par_source[source].append(chunk)

    if args.single_file:
        _ecrire_json(dossier / "chunks_editables_tous.json", editables)
    else:
        dossier_sources = dossier / "par_source"
        for source, chunks in sorted(par_source.items()):
            _ecrire_json(dossier_sources / _nom_fichier_source(source), chunks)

    manifeste = {
        "export_utc": datetime.now(timezone.utc).isoformat(),
        "table": "documents",
        "nb_documents": len(lignes),
        "nb_sources": len(par_source),
        "metadonnees_exclues_des_json_editables": sorted(CLES_METADATA_INTERDITES),
        "sources": [
            {
                "source": source,
                "nb_chunks": len(chunks),
                "fichier": (
                    "chunks_editables_tous.json"
                    if args.single_file
                    else f"par_source/{_nom_fichier_source(source)}"
                ),
            }
            for source, chunks in sorted(par_source.items())
        ],
    }
    _ecrire_json(dossier / "manifest.json", manifeste)

    print("\nExport terminé.")
    print(f"Dossier: {dossier.resolve()}")
    print(f"Documents: {len(lignes)}")
    print(f"Sources: {len(par_source)}")
    print("Aucune donnée Supabase n'a été modifiée.")
    return dossier


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Exporte les chunks de public.documents depuis Supabase."
    )
    parser.add_argument(
        "--output",
        default="exports_supabase",
        help="Dossier parent de sortie (défaut: exports_supabase)",
    )
    parser.add_argument(
        "--single-file",
        action="store_true",
        help="Produit un seul JSON éditable au lieu d'un fichier par source.",
    )
    parser.add_argument(
        "--raw-backup",
        action="store_true",
        help=(
            "Ajoute un backup brut incluant la colonne embedding. Attention: "
            "le fichier peut être très volumineux."
        ),
    )
    return parser


if __name__ == "__main__":
    try:
        exporter(_parser().parse_args())
    except KeyboardInterrupt:
        print("\nExport interrompu.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERREUR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
