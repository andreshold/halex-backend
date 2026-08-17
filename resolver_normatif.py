"""
resolver_normatif.py — résolveur déterministe Halex.

Ce module ne fait ni recherche vectorielle ni appel LLM.
Il compare uniquement des documents déjà jugés pertinents.

Ordre:
1) statut d'applicabilité;
2) rang (plus petit = plus fort);
3) date juridique `metadata.date` (plus récente seulement à rang égal).

`date_publication` n'intervient JAMAIS dans la primauté.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable

from schema_metadata import (
    RANGS_PAR_TYPE_NORME,
    STATUTS_APPLICABLES,
    STATUTS_NON_APPLICABLES,
)


class ErreurMetadataNormative(ValueError):
    pass


def _metadata(document: dict[str, Any]) -> dict[str, Any]:
    meta = document.get("metadata")
    if not isinstance(meta, dict):
        raise ErreurMetadataNormative("Document sans metadata valide")
    return meta


def _rang(meta: dict[str, Any]) -> int:
    type_norme = meta.get("type_norme")
    attendu = RANGS_PAR_TYPE_NORME.get(type_norme)
    recu = meta.get("rang")

    if attendu is None:
        raise ErreurMetadataNormative(
            f"type_norme inconnu: {type_norme!r}"
        )
    if recu != attendu:
        raise ErreurMetadataNormative(
            f"rang incohérent pour {type_norme!r}: reçu {recu!r}, attendu {attendu}"
        )
    return attendu


def _date_juridique(meta: dict[str, Any]) -> date:
    valeur = meta.get("date")
    if not isinstance(valeur, str):
        raise ErreurMetadataNormative(
            f"metadata.date absente/invalide: {valeur!r}"
        )
    try:
        return date.fromisoformat(valeur)
    except ValueError as exc:
        raise ErreurMetadataNormative(
            f"metadata.date invalide: {valeur!r}"
        ) from exc


def est_applicable(document: dict[str, Any]) -> bool:
    return _metadata(document).get("statut") in STATUTS_APPLICABLES


def est_non_applicable(document: dict[str, Any]) -> bool:
    return _metadata(document).get("statut") in STATUTS_NON_APPLICABLES


def cle_priorite(document: dict[str, Any]) -> tuple[int, int]:
    """
    Pour sorted(...):
    - rang faible en premier;
    - à rang égal, date récente en premier.
    """
    meta = _metadata(document)
    return (_rang(meta), -_date_juridique(meta).toordinal())


def trier_applicables(
    documents: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(
        (doc for doc in documents if est_applicable(doc)),
        key=cle_priorite,
    )


def comparer(
    gauche: dict[str, Any],
    droite: dict[str, Any],
) -> dict[str, Any]:
    """
    Compare deux textes que la couche amont a déjà identifiés comme
    contradictoires sur le même point.

    Cette fonction NE détecte PAS elle-même la contradiction.
    """
    mg = _metadata(gauche)
    md = _metadata(droite)

    ag = mg.get("statut") in STATUTS_APPLICABLES
    ad = md.get("statut") in STATUTS_APPLICABLES

    if ag and not ad:
        return {
            "gagnant": gauche,
            "perdant": droite,
            "raison": "statut",
        }
    if ad and not ag:
        return {
            "gagnant": droite,
            "perdant": gauche,
            "raison": "statut",
        }
    if not ag and not ad:
        return {
            "gagnant": None,
            "perdant": None,
            "raison": "aucun_applicable",
        }

    rg = _rang(mg)
    rd = _rang(md)

    if rg < rd:
        return {
            "gagnant": gauche,
            "perdant": droite,
            "raison": "rang",
        }
    if rd < rg:
        return {
            "gagnant": droite,
            "perdant": gauche,
            "raison": "rang",
        }

    dg = _date_juridique(mg)
    dd = _date_juridique(md)

    if dg > dd:
        return {
            "gagnant": gauche,
            "perdant": droite,
            "raison": "date",
        }
    if dd > dg:
        return {
            "gagnant": droite,
            "perdant": gauche,
            "raison": "date",
        }

    return {
        "gagnant": None,
        "perdant": None,
        "raison": "egalite_normative",
    }
