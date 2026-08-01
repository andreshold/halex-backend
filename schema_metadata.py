"""
schema_metadata.py
Source unique de vérité du contrat de métadonnées des chunks ingérés
(clés obligatoires/optionnelles/interdites, valeurs autorisées, formats).

Toute évolution du contrat (ajout/retrait d'une clé, changement d'une liste
de valeurs valides, etc.) doit se faire ICI, jamais dans les modules qui
consomment ces définitions (ingestion_admin.py et autres). Module d'imports
purs : aucune dépendance à FastAPI, Supabase ou OpenAI, aucun effet de bord.
"""

import re
from datetime import datetime

RANGS_PAR_TYPE_NORME = {
    "constitution": 1,
    "loi": 2,
    "code": 3,
    "décret": 4,
    "arrêté": 5,
}

STATUTS_VALIDES = {"en_vigueur", "adopté_non_appliqué"}
MONITEUR_TYPES_VALIDES = {"spécial", "ordinaire", "extraordinaire"}

CLES_METADATA_OBLIGATOIRES = {
    "source",
    "type_norme",
    "rang",
    "date",
    "statut",
    "article",
}
CLES_METADATA_OPTIONNELLES = {
    "livre",
    "titre",
    "chapitre",
    "section",
    "paragraphe",
    "moniteur_annee",
    "moniteur_numero",
    "moniteur_type",
    "source_courte",
}
CLES_METADATA_AUTORISEES = CLES_METADATA_OBLIGATOIRES | CLES_METADATA_OPTIONNELLES

# Les trois clés d'une référence Moniteur : optionnelles individuellement,
# mais soumises à une règle tout-ou-rien (fournies ensemble, ou aucune).
CLES_MONITEUR = {"moniteur_annee", "moniteur_numero", "moniteur_type"}

# Générées exclusivement côté serveur au moment de l'insertion : un fichier
# téléversé qui les contient déjà est une erreur de validation, pour les
# DEUX endpoints.
CLES_METADATA_INTERDITES = {"lot_ingestion", "date_ingestion"}

# text-embedding-3-small limite les textes à 8192 tokens. 20 000 caractères
# est une marge de sécurité pour le français (où un token vaut souvent moins
# d'un caractère qu'en anglais) : un chunk qui dépasse cette limite ferait
# échouer TOUT le lot d'embeddings avec une erreur OpenAI peu explicite,
# potentiellement après plusieurs minutes d'attente réseau.
LONGUEUR_MAX_PAGE_CONTENT = 20000

REGEX_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def date_valide(valeur: str) -> bool:
    """Format strict YYYY-MM-DD ET date calendaire réellement valide
    (rejette par exemple "2024-1-5" ou "2024-02-30")."""
    if not REGEX_DATE.match(valeur):
        return False
    try:
        datetime.strptime(valeur, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def libelle_source(metadata: dict) -> str:
    """Libellé d'affichage d'une source : source_courte si présente et non
    vide, sinon source. Règle de contrat partagée par les rapports de
    validation, les citations RAG et le frontend admin — à réutiliser telle
    quelle, ne pas la redupliquer ailleurs."""
    source_courte = metadata.get("source_courte")
    if isinstance(source_courte, str) and source_courte.strip():
        return source_courte
    return metadata.get("source", "")
