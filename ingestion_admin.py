"""
ingestion_admin.py
Bloc 3, étape 1/2 : validation d'un fichier JSON de chunks déjà découpés
par les scripts locaux (decoupeur_unifie.py etc., HORS de l'application).
Cet endpoint VALIDE uniquement — aucune écriture en base, aucun appel
OpenAI. L'insertion sera un endpoint séparé, construit après validation
de celui-ci.
"""

import json
import os
import re
from collections import defaultdict
from datetime import datetime

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from supabase import create_client

from auth_admin import verifier_admin

load_dotenv()

router = APIRouter()

# Client dédié en lecture seule, indépendant de celui de halex_core_supabase.py
# et de celui d'auth_admin.py. Utilise la clé service_role pour lire la table
# documents malgré la RLS.
_supabase_ingestion = create_client(
    os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
)

TAILLE_MAX_OCTETS = 10 * 1024 * 1024  # 10 Mo
TAILLE_PAGE_SUPABASE = 1000  # limite PostgREST par requête

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
    "moniteur_annee",
    "moniteur_numero",
    "moniteur_type",
}
CLES_METADATA_OPTIONNELLES = {"livre", "titre", "chapitre", "section", "paragraphe"}
CLES_METADATA_AUTORISEES = CLES_METADATA_OBLIGATOIRES | CLES_METADATA_OPTIONNELLES

REGEX_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Sentinelle pour distinguer "clé absente" de "clé présente avec valeur None".
_ABSENT = object()


def _date_valide(valeur: str) -> bool:
    """Format strict YYYY-MM-DD ET date calendaire réellement valide
    (rejette par exemple "2024-1-5" ou "2024-02-30")."""
    if not REGEX_DATE.match(valeur):
        return False
    try:
        datetime.strptime(valeur, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _emballer(raisons: list[str], index: int, article_label: str | None) -> list[dict]:
    return [{"index": index, "article": article_label, "raison": r} for r in raisons]


def _valider_chunk(item, index: int) -> tuple[list[dict], str | None, str | None]:
    """Valide un élément de la liste. Retourne (erreurs, article, source) —
    article/source ne sont renseignés que s'ils sont individuellement
    valides, indépendamment des autres erreurs du même chunk."""
    raisons: list[str] = []

    if not isinstance(item, dict):
        raisons.append(f"L'élément doit être un objet JSON, reçu : {type(item).__name__}")
        return _emballer(raisons, index, None), None, None

    # page_content
    page_content = item.get("page_content", _ABSENT)
    if page_content is _ABSENT:
        raisons.append("Clé 'page_content' absente")
    elif not isinstance(page_content, str):
        raisons.append(f"'page_content' doit être une chaîne de caractères, reçu : {page_content!r}")
    elif not page_content.strip():
        raisons.append("'page_content' est vide ou ne contient que des espaces")

    metadata = item.get("metadata", _ABSENT)
    if metadata is _ABSENT:
        raisons.append("Clé 'metadata' absente")
        return _emballer(raisons, index, None), None, None
    if not isinstance(metadata, dict):
        raisons.append(f"'metadata' doit être un objet JSON, reçu : {type(metadata).__name__}")
        return _emballer(raisons, index, None), None, None

    # Clés inconnues (protection contre les fautes de frappe type "articl")
    cles_inconnues = sorted(set(metadata.keys()) - CLES_METADATA_AUTORISEES)
    for cle in cles_inconnues:
        raisons.append(f"Clé 'metadata.{cle}' inconnue (valeur reçue : {metadata[cle]!r})")

    # source
    source_brut = metadata.get("source", _ABSENT)
    source_label: str | None = None
    if source_brut is _ABSENT:
        raisons.append("Clé 'metadata.source' absente")
    elif not isinstance(source_brut, str) or not source_brut.strip():
        raisons.append(f"'metadata.source' doit être une chaîne non vide, reçu : {source_brut!r}")
    else:
        source_label = source_brut

    # type_norme + rang (corrélés)
    type_norme_brut = metadata.get("type_norme", _ABSENT)
    rang_brut = metadata.get("rang", _ABSENT)
    type_norme_valide: str | None = None

    if type_norme_brut is _ABSENT:
        raisons.append("Clé 'metadata.type_norme' absente")
    elif type_norme_brut not in RANGS_PAR_TYPE_NORME:
        raisons.append(
            f"'metadata.type_norme' invalide, reçu : {type_norme_brut!r}. "
            f"Valeurs acceptées : {', '.join(sorted(RANGS_PAR_TYPE_NORME))}"
        )
    else:
        type_norme_valide = type_norme_brut

    if rang_brut is _ABSENT:
        raisons.append("Clé 'metadata.rang' absente")
    elif not isinstance(rang_brut, int) or isinstance(rang_brut, bool):
        raisons.append(f"'metadata.rang' doit être un entier, reçu : {rang_brut!r}")
    elif type_norme_valide is not None and rang_brut != RANGS_PAR_TYPE_NORME[type_norme_valide]:
        raisons.append(
            f"'metadata.rang' incohérent : reçu {rang_brut} pour type_norme "
            f"{type_norme_valide!r}, attendu {RANGS_PAR_TYPE_NORME[type_norme_valide]}"
        )

    # date
    date_brut = metadata.get("date", _ABSENT)
    if date_brut is _ABSENT:
        raisons.append("Clé 'metadata.date' absente")
    elif not isinstance(date_brut, str) or not _date_valide(date_brut):
        raisons.append(f"'metadata.date' invalide, reçu : {date_brut!r}. Format attendu : YYYY-MM-DD (date réelle)")

    # statut
    statut_brut = metadata.get("statut", _ABSENT)
    if statut_brut is _ABSENT:
        raisons.append("Clé 'metadata.statut' absente")
    elif statut_brut not in STATUTS_VALIDES:
        raisons.append(
            f"'metadata.statut' invalide, reçu : {statut_brut!r}. "
            f"Valeurs acceptées : {', '.join(sorted(STATUTS_VALIDES))}"
        )

    # article
    article_brut = metadata.get("article", _ABSENT)
    article_label: str | None = None
    if article_brut is _ABSENT:
        raisons.append("Clé 'metadata.article' absente")
    elif not isinstance(article_brut, str) or not article_brut.strip():
        raisons.append(f"'metadata.article' doit être une chaîne non vide, reçu : {article_brut!r}")
    else:
        article_label = article_brut

    # moniteur_annee
    moniteur_annee_brut = metadata.get("moniteur_annee", _ABSENT)
    if moniteur_annee_brut is _ABSENT:
        raisons.append("Clé 'metadata.moniteur_annee' absente")
    elif (
        not isinstance(moniteur_annee_brut, int)
        or isinstance(moniteur_annee_brut, bool)
        or moniteur_annee_brut <= 0
    ):
        raisons.append(f"'metadata.moniteur_annee' doit être un entier positif, reçu : {moniteur_annee_brut!r}")

    # moniteur_numero
    moniteur_numero_brut = metadata.get("moniteur_numero", _ABSENT)
    if moniteur_numero_brut is _ABSENT:
        raisons.append("Clé 'metadata.moniteur_numero' absente")
    elif not isinstance(moniteur_numero_brut, str) or not moniteur_numero_brut.strip():
        raisons.append(f"'metadata.moniteur_numero' doit être une chaîne non vide, reçu : {moniteur_numero_brut!r}")

    # moniteur_type
    moniteur_type_brut = metadata.get("moniteur_type", _ABSENT)
    if moniteur_type_brut is _ABSENT:
        raisons.append("Clé 'metadata.moniteur_type' absente")
    elif moniteur_type_brut not in MONITEUR_TYPES_VALIDES:
        raisons.append(
            f"'metadata.moniteur_type' invalide, reçu : {moniteur_type_brut!r}. "
            f"Valeurs acceptées : {', '.join(sorted(MONITEUR_TYPES_VALIDES))}"
        )

    # Clés optionnelles : string non vide si présentes
    for cle in sorted(CLES_METADATA_OPTIONNELLES):
        if cle in metadata:
            valeur = metadata[cle]
            if not isinstance(valeur, str) or not valeur.strip():
                raisons.append(f"'metadata.{cle}' doit être une chaîne non vide si présente, reçu : {valeur!r}")

    return _emballer(raisons, index, article_label), article_label, source_label


def _paires_existantes_en_base(sources: list[str]) -> set[tuple[str, str]]:
    """Paires (source, article) déjà présentes dans documents pour les
    sources données, lues en base avec pagination explicite (la limite
    PostgREST est de 1000 lignes par requête — indispensable dès qu'un
    corpus dépasse ce seuil, sinon des doublons passeraient inaperçus).
    Retourne un ensemble vide si la table est vide ou si sources est vide."""
    if not sources:
        return set()

    paires: set[tuple[str, str]] = set()
    offset = 0

    for _ in range(1000):  # garde-fou : jusqu'à 1 000 000 de lignes
        lot = (
            _supabase_ingestion.table("documents")
            .select("source:metadata->>source, article:metadata->>article")
            .in_("metadata->>source", sources)
            .range(offset, offset + TAILLE_PAGE_SUPABASE - 1)
            .execute()
        )
        lignes = lot.data or []
        for ligne in lignes:
            if ligne.get("source") is not None and ligne.get("article") is not None:
                paires.add((ligne["source"], ligne["article"]))
        if len(lignes) < TAILLE_PAGE_SUPABASE:
            return paires
        offset += TAILLE_PAGE_SUPABASE

    raise RuntimeError(
        "Garde-fou de pagination atteint lors de la recherche des doublons en "
        "base (plus d'un million de lignes lues) — vérifier la table documents."
    )


@router.post("/admin/validation")
async def endpoint_validation(
    fichier: UploadFile = File(...),
    admin: dict = Depends(verifier_admin),
):
    """Valide un fichier JSON de chunks (liste d'objets page_content/metadata)
    sans jamais écrire en base ni appeler OpenAI. Rejouable à l'infini."""
    nom = fichier.filename or ""
    if not nom.lower().endswith(".json"):
        raise HTTPException(
            status_code=400,
            detail=f"Extension de fichier invalide : '{nom}'. Seuls les fichiers .json sont acceptés",
        )

    contenu = await fichier.read()

    if len(contenu) > TAILLE_MAX_OCTETS:
        raise HTTPException(
            status_code=413,
            detail=f"Fichier trop volumineux : {len(contenu)} octets (maximum {TAILLE_MAX_OCTETS} octets)",
        )

    try:
        texte = contenu.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "Le fichier n'est pas encodé en UTF-8 (encodage strict requis) : "
                f"{exc}. Ré-enregistrez-le en UTF-8 (sans BOM) avant de le "
                "téléverser — un export depuis un script Windows produit souvent "
                "du cp1252/latin-1 par défaut."
            ),
        )

    try:
        donnees = json.loads(texte)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"JSON invalide : {exc}")

    if not isinstance(donnees, list):
        raise HTTPException(
            status_code=400,
            detail=f"Le fichier doit contenir une liste JSON d'objets, reçu : {type(donnees).__name__}",
        )

    erreurs: list[dict] = []
    pairs_par_index: dict[int, tuple[str, str]] = {}
    resume: dict[str, dict] = {}

    for index, item in enumerate(donnees):
        erreurs_item, article_label, source_label = _valider_chunk(item, index)
        erreurs.extend(erreurs_item)

        if not erreurs_item and source_label and article_label:
            pairs_par_index[index] = (source_label, article_label)
            meta = item["metadata"]
            info = resume.setdefault(
                source_label,
                {
                    "source": source_label,
                    "type_norme": meta["type_norme"],
                    "rang": meta["rang"],
                    "nb_chunks": 0,
                },
            )
            info["nb_chunks"] += 1

    # Doublons internes au fichier
    indices_par_pair: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, pair in pairs_par_index.items():
        indices_par_pair[pair].append(index)

    doublons_internes = [
        {"source": source, "article": article, "indices": sorted(indices)}
        for (source, article), indices in sorted(indices_par_pair.items())
        if len(indices) > 1
    ]

    # Doublons en base (lecture seule, paginée)
    sources_uniques = sorted({source for source, _ in pairs_par_index.values()})
    paires_en_base = _paires_existantes_en_base(sources_uniques)
    paires_uniques_fichier = set(pairs_par_index.values())
    doublons_en_base = [
        {"source": source, "article": article}
        for source, article in sorted(paires_uniques_fichier & paires_en_base)
    ]

    nb_chunks_total = len(donnees)
    indices_en_erreur = {e["index"] for e in erreurs}
    nb_chunks_valides = nb_chunks_total - len(indices_en_erreur)
    valide = len(erreurs) == 0

    return {
        "nb_chunks_total": nb_chunks_total,
        "nb_chunks_valides": nb_chunks_valides,
        "valide": valide,
        "pret_pour_insertion": valide and not doublons_internes and not doublons_en_base,
        "erreurs": erreurs,
        "doublons_internes": doublons_internes,
        "doublons_en_base": doublons_en_base,
        "resume_par_source": list(resume.values()),
    }
