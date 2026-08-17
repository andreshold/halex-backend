"""
schema_metadata.py — contrat unique des métadonnées Halex RAG juridique v1.0.

Ce module est la SOURCE UNIQUE DE VÉRITÉ pour :
- les rangs normatifs ;
- les vocabulaires fermés ;
- les clés de métadonnées autorisées ;
- les types attendus ;
- les valeurs nullables ;
- les règles de format réutilisées par l'ingestion et le moteur.

Aucune dépendance FastAPI, Supabase ou OpenAI.
"""

from __future__ import annotations

import re
from datetime import datetime
from numbers import Real
from typing import Any

VERSION_SCHEMA_RAG = "rag_juridique_v1.0"

# Plus le nombre est PETIT, plus le rang est fort.
# IMPORTANT : `rang` encode la FORCE NORMATIVE, pas le type documentaire.
# Deux types différents peuvent donc partager le même rang.
# Les valeurs absolues n'ont pas de portée juridique : seul l'ordre relatif
# compte. Elles sont espacées pour permettre l'insertion future de nouveaux
# niveaux sans renuméroter le corpus déjà ingéré.
RANGS_PAR_TYPE_NORME = {
    "constitution":        10,
    "convention_ratifiee": 20,
    # Même étage législatif dans le modèle normatif Halex.
    # `type_norme` conserve la catégorie documentaire; `rang` encode
    # uniquement la force normative.
    "loi":                 30,
    "code":                30,
    "decret":              30,
    "arrete":              40,
    "circulaire":          50,
}

LIBELLES_TYPE_NORME = {
    "constitution":        "Constitution",
    "convention_ratifiee": "convention internationale ratifiée",
    "loi":                 "loi",
    "code":                "code",
    "decret":              "décret",
    "arrete":              "arrêté",
    "circulaire":          "circulaire",
}

LIBELLES_STATUT = {
    "en_vigueur":          "en vigueur",
    "adopte_non_applique": "adopté mais non appliqué",
    "abroge":              "abrogé",
    "modifie":             "modifié",
}
STATUTS_VALIDES = frozenset(LIBELLES_STATUT)

# Statuts utilisables pour fonder l'état courant du droit.
STATUTS_APPLICABLES = frozenset({"en_vigueur", "modifie"})
STATUTS_NON_APPLICABLES = frozenset({"adopte_non_applique", "abroge"})

LIBELLES_THEMATIQUE = {
    "droit_constitutionnel":       "droit constitutionnel",
    "droits_fondamentaux":         "droits fondamentaux",
    "droit_electoral":             "droit électoral",
    "nationalite_et_immigration":  "nationalité et immigration",
    "droit_penal":                 "droit pénal",
    "procedure_penale":            "procédure pénale",
    "procedure_civile":            "procédure civile",
    "droit_civil":                 "droit civil",
    "droit_de_la_famille":         "droit de la famille",
    "protection_de_l_enfance":     "protection de l'enfance",
    "successions_et_liberalites":  "successions et libéralités",
    "droit_commercial":            "droit commercial",
    "droit_des_societes":          "droit des sociétés",
    "droit_bancaire":              "droit bancaire",
    "droit_des_assurances":        "droit des assurances",
    "droit_fiscal":                "droit fiscal",
    "droit_douanier":              "droit douanier",
    "droit_du_travail":            "droit du travail",
    "protection_sociale":          "protection sociale",
    "droit_de_la_sante":           "droit de la santé",
    "droit_de_l_education":        "droit de l'éducation",
    "droit_administratif":         "droit administratif",
    "collectivites_territoriales": "collectivités territoriales",
    "marches_publics":             "marchés publics",
    "fonction_publique":           "fonction publique",
    "droit_foncier":               "droit foncier",
    "droit_rural":                 "droit rural",
    "droit_de_l_environnement":    "droit de l'environnement",
    "droit_minier":                "droit minier",
    "propriete_intellectuelle":    "propriété intellectuelle",
}
THEMATIQUES = frozenset(LIBELLES_THEMATIQUE)

TYPES_BLOC_VALIDES = {
    "article",
    "preambule",
    "visas",
    "cloture",
    "annexe",
}
TYPE_BLOC_PAR_DEFAUT = "article"

# Valeurs produites par le fichier RAG juridique v1.0.
# La plupart des champs sont explicitement matérialisés, même lorsqu'ils sont
# vides/null, pour rendre chaque chunk auto-descriptif et audit-able.
CLES_METADATA_OBLIGATOIRES = {
    "document_id",
    "chunk_id",
    "source",
    "source_courte",
    "type_norme",
    "rang",
    "date",
    "date_publication",
    "convention_date_adoption",
    "convention_date_ratification",
    "statut",
    "historique",
    "moniteur_publication",
    "type_bloc",
    "ordre",
    "article",
    "article_numero",
    "chemin_hierarchique",
    "hierarchie",
    "type_thematique",
    "themes_source",
    "concepts_juridiques",
    "termes_officiels",
    "actes",
    "personnes_concernees",
    "objets_concernes",
    "circonstances",
    "conditions_application",
    "exceptions",
    "sanctions",
    "peines_principales",
    "peines_complementaires",
    "duree_emprisonnement_min",
    "duree_emprisonnement_max",
    "unite_duree_emprisonnement",
    "amende_min",
    "amende_max",
    "devise",
    "references_articles",
    "references_textes",
    "mots_cles",
    "termes_recherche",
    "article_modifie_par",
    "article_date_modification",
    "article_publication_modification",
    "abroge_par",
    "date_abrogation",
    "publication_abrogation",
    "version_schema",
}

# Conservées pour compatibilité avec les imports existants.
# Le schéma v1.0 matérialise actuellement toutes ses clés : aucune optionnelle.
CLES_METADATA_OPTIONNELLES: set[str] = set()
CLES_METADATA_AUTORISEES = frozenset(CLES_METADATA_OBLIGATOIRES)

# Champs générés EXCLUSIVEMENT par le serveur à l'insertion.
CLES_METADATA_INTERDITES = frozenset({"lot_ingestion", "date_ingestion"})

CLES_CONVENTION = frozenset({
    "convention_date_adoption",
    "convention_date_ratification",
})

CLES_ABROGATION = frozenset({
    "abroge_par",
    "publication_abrogation",
    "date_abrogation",
})

CLES_MODIFICATION = frozenset({
    "article_modifie_par",
    "article_date_modification",
    "article_publication_modification",
})

CLES_PUBLICATION = frozenset({"moniteur_publication"})

CLES_METADATA_NULLABLES = frozenset({
    *CLES_CONVENTION,
    *CLES_ABROGATION,
    *CLES_MODIFICATION,
    *CLES_PUBLICATION,
    "article_numero",
    "duree_emprisonnement_min",
    "duree_emprisonnement_max",
    "unite_duree_emprisonnement",
    "amende_min",
    "amende_max",
    "devise",
})

# Compatibilité : les consommateurs historiques excluaient ces clés d'une
# boucle générique "chaîne non vide".
CLES_OPTIONNELLES_NON_TEXTUELLES = frozenset()

# Champs list[str]. Les listes peuvent être vides, mais leurs éléments ne le
# peuvent pas et les doublons sont refusés par l'ingestion.
CLES_LISTES_TEXTE = frozenset({
    "hierarchie",
    "type_thematique",
    "themes_source",
    "concepts_juridiques",
    "termes_officiels",
    "actes",
    "personnes_concernees",
    "objets_concernes",
    "circonstances",
    "conditions_application",
    "exceptions",
    "sanctions",
    "peines_principales",
    "peines_complementaires",
    "references_textes",
    "mots_cles",
    "termes_recherche",
})

# Champs list[int].
CLES_LISTES_ENTIERS = frozenset({"references_articles"})

# Champs chaîne obligatoirement non vide.
CLES_CHAINES_NON_VIDES = frozenset({
    "document_id",
    "chunk_id",
    "source",
    "source_courte",
    "type_norme",
    "date",
    "date_publication",
    "statut",
    "type_bloc",
    "article",
    "chemin_hierarchique",
    "version_schema",
})

# Champs chaîne ou null.
CLES_CHAINES_NULLABLES = frozenset({
    "convention_date_adoption",
    "convention_date_ratification",
    "moniteur_publication",
    "unite_duree_emprisonnement",
    "devise",
    "article_modifie_par",
    "article_date_modification",
    "article_publication_modification",
    "abroge_par",
    "date_abrogation",
    "publication_abrogation",
})

CLES_DATES = frozenset({
    "date",
    "date_publication",
    "convention_date_adoption",
    "convention_date_ratification",
    "article_date_modification",
    "date_abrogation",
})

CLES_ENTIERS_POSITIFS = frozenset({"ordre"})
CLES_ENTIERS_POSITIFS_NULLABLES = frozenset({"article_numero"})

# Int ou float >= 0, bool exclu.
CLES_NOMBRES_NON_NEGATIFS_NULLABLES = frozenset({
    "duree_emprisonnement_min",
    "duree_emprisonnement_max",
    "amende_min",
    "amende_max",
})

# Champs qui décrivent la source/document consolidé et doivent être constants
# dans tous ses chunks.
CLES_COHERENCE_DOCUMENT = frozenset({
    "document_id",
    "source",
    "source_courte",
    "type_norme",
    "rang",
    "date",
    "date_publication",
    "convention_date_adoption",
    "convention_date_ratification",
    "historique",
    "moniteur_publication",
    "version_schema",
})

# L'ID technique est ASCII et stable : utile pour les index, logs et exports.
REGEX_IDENTIFIANT_RAG = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,127}$")
REGEX_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# text-embedding-3-small limite l'entrée à 8192 tokens. 20k caractères est une
# garde de sécurité ; l'ingestion reste responsable du contrôle final.
LONGUEUR_MAX_PAGE_CONTENT = 20_000


def date_valide(valeur: str) -> bool:
    """YYYY-MM-DD strict et date calendaire réelle."""
    if not isinstance(valeur, str) or not REGEX_DATE.match(valeur):
        return False
    try:
        datetime.strptime(valeur, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def est_nombre_reel_non_booleen(valeur: Any) -> bool:
    return isinstance(valeur, Real) and not isinstance(valeur, bool)


def libelle_source(metadata: dict) -> str:
    source_courte = metadata.get("source_courte")
    if isinstance(source_courte, str) and source_courte.strip():
        return source_courte
    return metadata.get("source", "")


def libelle_statut(statut: str) -> str:
    return LIBELLES_STATUT.get(statut, statut)


def libelle_type_norme(type_norme: str) -> str:
    return LIBELLES_TYPE_NORME.get(type_norme, type_norme)


def libelle_thematique(slug: str) -> str:
    return LIBELLES_THEMATIQUE.get(slug, slug)


def _verifier_coherence() -> None:
    if set(RANGS_PAR_TYPE_NORME) != set(LIBELLES_TYPE_NORME):
        raise RuntimeError(
            "schema_metadata incohérent : RANGS_PAR_TYPE_NORME et "
            "LIBELLES_TYPE_NORME doivent avoir exactement les mêmes clés."
        )

    if CLES_METADATA_OBLIGATOIRES & CLES_METADATA_INTERDITES:
        raise RuntimeError(
            "schema_metadata incohérent : une clé ne peut pas être à la fois "
            "obligatoire et générée par le serveur."
        )

    groupes_types = (
        CLES_LISTES_TEXTE
        | CLES_LISTES_ENTIERS
        | CLES_CHAINES_NON_VIDES
        | CLES_CHAINES_NULLABLES
        | CLES_ENTIERS_POSITIFS
        | CLES_ENTIERS_POSITIFS_NULLABLES
        | CLES_NOMBRES_NON_NEGATIFS_NULLABLES
        | frozenset({"rang", "historique"})
    )
    inconnues = groupes_types - CLES_METADATA_AUTORISEES
    if inconnues:
        raise RuntimeError(
            f"schema_metadata incohérent : clés typées non autorisées : {sorted(inconnues)}"
        )

    if CLES_DATES - (CLES_CHAINES_NON_VIDES | CLES_CHAINES_NULLABLES):
        raise RuntimeError("schema_metadata incohérent : une date n'a pas de type chaîne déclaré.")

    if VERSION_SCHEMA_RAG != "rag_juridique_v1.0":
        raise RuntimeError("VERSION_SCHEMA_RAG inattendue.")


_verifier_coherence()