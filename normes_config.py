"""
Configuration normative centrale de Halex.

But:
- une seule source de vérité pour les rangs juridiques;
- empêcher le prompt, l'ingestion et le moteur RAG d'avoir des règles
  différentes;
- `date_publication` reste documentaire;
- `date` sert aux comparaisons chronologiques du moteur.

Convention:
- plus le rang est PETIT, plus la norme est forte;
- le rang l'emporte sur la date;
- la date ne départage que deux normes de même rang;
- le statut est vérifié avant rang/date.

Cette table reprend la convention actuellement utilisée par les chunks Halex,
notamment `code = 40`.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Any

# Source de vérité des rangs.
# IMPORTANT : toute modification doit être volontaire et testée.
RANGS_PAR_TYPE_NORME: dict[str, int] = {
    "constitution": 10,
    "convention_ratifiee": 20,
    "loi": 30,
    "code": 40,
    "decret": 50,
    "arrete": 60,
    "circulaire": 70,
}

LIBELLES_TYPE_NORME: dict[str, str] = {
    "constitution": "Constitution",
    "convention_ratifiee": "Convention internationale ratifiée",
    "loi": "Loi",
    "code": "Code",
    "decret": "Décret",
    "arrete": "Arrêté",
    "circulaire": "Circulaire",
}

# Statuts connus par le moteur normatif.
# On distingue "peut fonder une réponse" de "peut être montré à titre
# informatif". Un texte abrogé reste consultable par lookup direct, mais ne
# doit pas fonder une réponse juridique courante.
STATUTS_NORMATIFS = {
    "en_vigueur",
    "modifie",
    "adopte_mais_non_applique",
    "abroge",
}

STATUTS_APPLICABLES = {"en_vigueur", "modifie"}
STATUTS_INFORMATIFS = {"adopte_mais_non_applique", "abroge"}

# Les métadonnées produites par le serveur et qui ne doivent pas venir du JSON.
CLES_SERVEUR = {"lot_ingestion", "date_ingestion"}


def date_iso_valide(valeur: Any) -> bool:
    """YYYY-MM-DD réel, pas seulement une chaîne ressemblant à une date."""
    if not isinstance(valeur, str):
        return False
    try:
        date_type.fromisoformat(valeur)
    except ValueError:
        return False
    return len(valeur) == 10


def rang_attendu(type_norme: str) -> int | None:
    return RANGS_PAR_TYPE_NORME.get(type_norme)


def statut_applicable(statut: str | None) -> bool:
    return statut in STATUTS_APPLICABLES


def metadata_normative_valide(meta: dict) -> tuple[bool, list[str]]:
    """Validation minimale indépendante de l'ingestion complète."""
    erreurs: list[str] = []

    type_norme = meta.get("type_norme")
    rang = meta.get("rang")
    statut = meta.get("statut")
    date_juridique = meta.get("date")
    date_publication = meta.get("date_publication")

    if type_norme not in RANGS_PAR_TYPE_NORME:
        erreurs.append(f"type_norme inconnu: {type_norme!r}")
    elif rang != RANGS_PAR_TYPE_NORME[type_norme]:
        erreurs.append(
            f"rang incohérent: {rang!r} pour {type_norme!r}; "
            f"attendu {RANGS_PAR_TYPE_NORME[type_norme]}"
        )

    if statut not in STATUTS_NORMATIFS:
        erreurs.append(f"statut normatif inconnu: {statut!r}")

    if not date_iso_valide(date_juridique):
        erreurs.append(f"date juridique invalide: {date_juridique!r}")

    if not date_iso_valide(date_publication):
        erreurs.append(f"date_publication invalide: {date_publication!r}")

    return not erreurs, erreurs
