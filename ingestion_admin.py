"""
ingestion_admin.py
Bloc 3, étape 2/2 : validation ET insertion réelle d'un fichier JSON de
chunks déjà découpés par les scripts locaux (decoupeur_unifie.py etc.,
HORS de l'application).

/admin/validation valide uniquement — aucune écriture en base, aucun appel
OpenAI. Rejouable à l'infini.

/admin/insertion revalide intégralement (aucune confiance dans une
validation antérieure côté client), génère tous les embeddings AVANT toute
écriture, puis insère par lots. Les deux endpoints partagent la même
logique de validation (_valider_donnees) pour garantir un comportement
strictement identique.
"""

import json
import os
import unicodedata
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from langchain_openai import OpenAIEmbeddings
from supabase import create_client

import halex_core_supabase
from auth_admin import verifier_admin
from schema_metadata import (
    CLES_METADATA_AUTORISEES,
    CLES_METADATA_INTERDITES,
    CLES_METADATA_OPTIONNELLES,
    CLES_MONITEUR,
    LONGUEUR_MAX_PAGE_CONTENT,
    MONITEUR_TYPES_VALIDES,
    RANGS_PAR_TYPE_NORME,
    STATUTS_VALIDES,
    date_valide,
)

load_dotenv()

router = APIRouter()

# Client dédié, indépendant de celui de halex_core_supabase.py et de celui
# d'auth_admin.py. Utilise la clé service_role pour lire ET écrire dans la
# table documents malgré la RLS (lecture pour /admin/validation et la
# détection de doublons, écriture pour /admin/insertion).
_supabase_ingestion = create_client(
    os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
)

# Instance dédiée, indépendante de celle de halex_core_supabase.py — même
# modèle que la recherche RAG (1536 dimensions), utilisée ici uniquement
# pour générer les embeddings des chunks insérés.
_embeddings_ingestion = OpenAIEmbeddings(model="text-embedding-3-small")

TAILLE_MAX_OCTETS = 10 * 1024 * 1024  # 10 Mo
TAILLE_PAGE_SUPABASE = 1000  # limite PostgREST par requête
TAILLE_LOT_EMBEDDINGS = 100  # textes par appel OpenAI
TAILLE_LOT_INSERTION = 100  # lignes par appel Supabase

# Sentinelle pour distinguer "clé absente" de "clé présente avec valeur None".
_ABSENT = object()


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
    elif len(page_content) > LONGUEUR_MAX_PAGE_CONTENT:
        raisons.append(
            f"'page_content' trop long : {len(page_content)} caractères (maximum "
            f"{LONGUEUR_MAX_PAGE_CONTENT}). text-embedding-3-small limite les textes à 8192 "
            "tokens ; un chunk trop long ferait échouer tout le lot d'embeddings au moment de "
            "l'insertion. Découpez ce chunk en plusieurs plus petits."
        )

    metadata = item.get("metadata", _ABSENT)
    if metadata is _ABSENT:
        raisons.append("Clé 'metadata' absente")
        return _emballer(raisons, index, None), None, None
    if not isinstance(metadata, dict):
        raisons.append(f"'metadata' doit être un objet JSON, reçu : {type(metadata).__name__}")
        return _emballer(raisons, index, None), None, None

    # Clés interdites : générées exclusivement côté serveur, jamais admises en entrée
    cles_interdites_presentes = sorted(set(metadata.keys()) & CLES_METADATA_INTERDITES)
    for cle in cles_interdites_presentes:
        raisons.append(
            f"Clé 'metadata.{cle}' interdite : générée exclusivement par le serveur lors de "
            f"l'insertion, elle ne doit jamais figurer dans le fichier téléversé (valeur reçue : "
            f"{metadata[cle]!r})"
        )

    # Clés inconnues (protection contre les fautes de frappe type "articl")
    cles_inconnues = sorted(set(metadata.keys()) - CLES_METADATA_AUTORISEES - CLES_METADATA_INTERDITES)
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
    elif not isinstance(date_brut, str) or not date_valide(date_brut):
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

    # moniteur_annee / moniteur_numero / moniteur_type : chacune optionnelle
    # individuellement (aucune erreur si absente), mais soumises ensemble à
    # une règle tout-ou-rien vérifiée juste après.
    if "moniteur_annee" in metadata:
        moniteur_annee_brut = metadata["moniteur_annee"]
        if (
            not isinstance(moniteur_annee_brut, int)
            or isinstance(moniteur_annee_brut, bool)
            or moniteur_annee_brut <= 0
        ):
            raisons.append(f"'metadata.moniteur_annee' doit être un entier positif, reçu : {moniteur_annee_brut!r}")

    if "moniteur_numero" in metadata:
        moniteur_numero_brut = metadata["moniteur_numero"]
        if not isinstance(moniteur_numero_brut, str) or not moniteur_numero_brut.strip():
            raisons.append(f"'metadata.moniteur_numero' doit être une chaîne non vide, reçu : {moniteur_numero_brut!r}")

    if "moniteur_type" in metadata:
        moniteur_type_brut = metadata["moniteur_type"]
        if moniteur_type_brut not in MONITEUR_TYPES_VALIDES:
            raisons.append(
                f"'metadata.moniteur_type' invalide, reçu : {moniteur_type_brut!r}. "
                f"Valeurs acceptées : {', '.join(sorted(MONITEUR_TYPES_VALIDES))}"
            )

    # Règle tout-ou-rien : les trois clés moniteur_* doivent être fournies
    # ensemble, ou aucune — une référence Moniteur partielle est inexploitable.
    presentes_moniteur = set(metadata) & CLES_MONITEUR
    if 0 < len(presentes_moniteur) < len(CLES_MONITEUR):
        manquantes_moniteur = CLES_MONITEUR - presentes_moniteur
        raisons.append(
            f"Référence Moniteur incomplète : clés présentes {presentes_moniteur}, manquantes "
            f"{manquantes_moniteur}. Les trois clés moniteur_* doivent être fournies ensemble, "
            "ou aucune."
        )

    # mots_cles : optionnelle, mais si présente doit être une liste non vide
    # de chaînes non vides (exclue de la boucle générique ci-dessous, qui ne
    # s'applique qu'aux clés optionnelles de type chaîne).
    if "mots_cles" in metadata:
        mots_cles_brut = metadata["mots_cles"]
        if not isinstance(mots_cles_brut, list) or not mots_cles_brut:
            raisons.append(f"'metadata.mots_cles' doit être une liste non vide, reçu : {mots_cles_brut!r}")
        elif not all(isinstance(m, str) and m.strip() for m in mots_cles_brut):
            raisons.append(f"'metadata.mots_cles' doit être une liste de chaînes non vides, reçu : {mots_cles_brut!r}")

    # Clés optionnelles restantes : string non vide si présentes (les trois
    # clés moniteur_* et mots_cles ont chacune leur propre contrôle de type
    # ci-dessus, elles ne sont pas toutes des chaînes).
    for cle in sorted(CLES_METADATA_OPTIONNELLES - CLES_MONITEUR - {"mots_cles"}):
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


async def _lire_et_parser_fichier(fichier: UploadFile) -> list:
    """Lit, décode et parse le fichier téléversé. Lève une HTTPException
    explicite à la première étape défaillante (extension, taille, encodage,
    JSON, forme). Commune à /admin/validation et /admin/insertion."""
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

    # Normalisation Unicode NFC : un fichier produit par OCR ou passé par un
    # système de fichiers macOS peut arriver en NFD (accent combinant séparé
    # de la lettre), visuellement identique mais différent en comparaison de
    # chaînes — un "spécial" NFD serait rejeté par MONITEUR_TYPES_VALIDES
    # sans que repr() ne le distingue du NFC accepté. Normaliser ici, avant
    # le parsing JSON, couvre les deux endpoints et le contenu inséré en
    # base (donc aussi les embeddings et les lookups par article).
    texte = unicodedata.normalize("NFC", texte)

    try:
        donnees = json.loads(texte)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"JSON invalide : {exc}")

    if not isinstance(donnees, list):
        raise HTTPException(
            status_code=400,
            detail=f"Le fichier doit contenir une liste JSON d'objets, reçu : {type(donnees).__name__}",
        )

    return donnees


def _valider_donnees(donnees: list) -> dict:
    """Valide une liste de chunks déjà parsée (chaque erreur, doublon interne
    et doublon en base). Aucune écriture, aucun appel OpenAI. Commune à
    /admin/validation et /admin/insertion — la revalidation faite par ce
    dernier n'a AUCUNE confiance dans une validation antérieure côté client."""
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
                    "source_courte": meta.get("source_courte"),
                    "type_norme": meta["type_norme"],
                    "rang": meta["rang"],
                    "nb_chunks": 0,
                    # Signal d'information uniquement : n'influence ni
                    # `valide` ni `pret_pour_insertion`.
                    "nb_chunks_sans_moniteur": 0,
                },
            )
            info["nb_chunks"] += 1
            if not (set(meta) & CLES_MONITEUR):
                info["nb_chunks_sans_moniteur"] += 1

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


def _generer_embeddings(textes: list[str]) -> list[list[float]]:
    """Génère tous les embeddings AVANT toute écriture, par lots (un seul
    appel OpenAI par lot, jamais un appel par chunk). Si un lot échoue
    (réseau, quota, timeout) ou renvoie un nombre de vecteurs différent du
    nombre de textes envoyés, abandonne tout immédiatement : un décalage
    d'index associerait silencieusement le mauvais vecteur au mauvais
    article, ce que rien ne détecterait ensuite côté RAG."""
    vecteurs: list[list[float]] = []

    for debut in range(0, len(textes), TAILLE_LOT_EMBEDDINGS):
        lot = textes[debut : debut + TAILLE_LOT_EMBEDDINGS]
        try:
            vecteurs_lot = _embeddings_ingestion.embed_documents(lot)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Échec de génération des embeddings (lot {debut}-{debut + len(lot) - 1} sur "
                    f"{len(textes)} chunks) : {type(exc).__name__} — {exc}. Aucune donnée n'a été "
                    "écrite en base. Réessayez le téléversement."
                ),
            ) from exc

        if len(vecteurs_lot) != len(lot):
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Incohérence dans la réponse d'embeddings (lot {debut}-{debut + len(lot) - 1}) : "
                    f"{len(vecteurs_lot)} vecteur(s) reçu(s) pour {len(lot)} chunk(s) envoyé(s). "
                    "Abandon par sécurité pour éviter d'associer un vecteur au mauvais article. "
                    "Aucune donnée n'a été écrite en base."
                ),
            )
        vecteurs.extend(vecteurs_lot)

    if len(vecteurs) != len(textes):
        raise HTTPException(
            status_code=502,
            detail=(
                f"Incohérence globale : {len(vecteurs)} vecteur(s) obtenu(s) pour {len(textes)} "
                "chunk(s) au total. Abandon par sécurité. Aucune donnée n'a été écrite en base."
            ),
        )

    return vecteurs


def _inserer_documents(lignes: list[dict], lot_ingestion: str) -> int:
    """Insère les lignes par lots dans documents. Si un lot échoue en cours
    de route, tente de supprimer les lignes déjà écrites pour ce
    lot_ingestion, vérifie le nombre réellement supprimé, et lève une
    HTTPException 500 indiquant clairement si le nettoyage a réussi ou s'il
    reste des lignes orphelines à traiter à la main."""
    inseres = 0
    try:
        for debut in range(0, len(lignes), TAILLE_LOT_INSERTION):
            lot = lignes[debut : debut + TAILLE_LOT_INSERTION]
            _supabase_ingestion.table("documents").insert(lot).execute()
            inseres += len(lot)
    except Exception as exc:
        try:
            suppression = (
                _supabase_ingestion.table("documents")
                .delete()
                .eq("metadata->>lot_ingestion", lot_ingestion)
                .execute()
            )
            nb_supprimees = len(suppression.data or [])
        except Exception:
            nb_supprimees = None

        if nb_supprimees is None:
            message_nettoyage = (
                "Le nettoyage automatique a lui-même échoué : impossible de confirmer si des "
                "lignes orphelines subsistent."
            )
        elif nb_supprimees == inseres:
            message_nettoyage = f"Nettoyage automatique réussi : {nb_supprimees} ligne(s) supprimée(s)."
        else:
            message_nettoyage = (
                f"ATTENTION, nettoyage incomplet : {nb_supprimees} ligne(s) supprimée(s) alors que "
                f"{inseres} avaient été insérées avec ce lot_ingestion. Des lignes orphelines "
                "peuvent subsister."
            )

        raise HTTPException(
            status_code=500,
            detail=(
                f"Échec d'écriture en base après {inseres} chunk(s) inséré(s) sur {len(lignes)} "
                f"({type(exc).__name__} — {exc}). {message_nettoyage} Vérifiez manuellement la "
                f"table documents pour lot_ingestion = '{lot_ingestion}'."
            ),
        ) from exc

    return inseres


@router.post("/admin/validation")
async def endpoint_validation(
    fichier: UploadFile = File(...),
    admin: dict = Depends(verifier_admin),
):
    """Valide un fichier JSON de chunks (liste d'objets page_content/metadata)
    sans jamais écrire en base ni appeler OpenAI. Rejouable à l'infini."""
    donnees = await _lire_et_parser_fichier(fichier)
    return _valider_donnees(donnees)


@router.post("/admin/insertion")
async def endpoint_insertion(
    fichier: UploadFile = File(...),
    admin: dict = Depends(verifier_admin),
):
    """Revalide intégralement le fichier (aucune confiance dans une
    validation antérieure côté client), génère tous les embeddings AVANT
    toute écriture, puis insère en base par lots avec un lot_ingestion
    commun. N'écrit rien si la validation ou la génération d'embeddings
    échoue."""
    donnees = await _lire_et_parser_fichier(fichier)
    rapport = _valider_donnees(donnees)

    if not rapport["pret_pour_insertion"]:
        raise HTTPException(status_code=409, detail=rapport)

    textes = [item["page_content"] for item in donnees]
    vecteurs = _generer_embeddings(textes)

    lot_ingestion = str(uuid.uuid4())
    date_ingestion = datetime.now(timezone.utc).isoformat()

    lignes = []
    for item, vecteur in zip(donnees, vecteurs):
        metadata = dict(item["metadata"])
        metadata["lot_ingestion"] = lot_ingestion
        metadata["date_ingestion"] = date_ingestion
        lignes.append(
            {
                "content": item["page_content"],
                "metadata": metadata,
                "embedding": vecteur,
            }
        )

    nb_chunks_inseres = _inserer_documents(lignes, lot_ingestion)

    # Le corpus vient de changer : force la relecture des caches module-level
    # de halex_core_supabase (sources distinctes, mapping mots-clés, libellés)
    # au prochain appel plutôt que de servir des valeurs pré-ingestion.
    halex_core_supabase.invalider_caches()

    return {
        "succes": True,
        "lot_ingestion": lot_ingestion,
        "date_ingestion": date_ingestion,
        "nb_chunks_inseres": nb_chunks_inseres,
        "resume_par_source": rapport["resume_par_source"],
        "commande_annulation": (
            f"DELETE FROM documents WHERE metadata->>'lot_ingestion' = '{lot_ingestion}';"
        ),
    }
