"""
ingestion_admin.py — ingestion Halex RAG juridique v1.0.

Principes de sécurité :
- /admin/validation : lecture + validation uniquement, jamais OpenAI/écriture ;
- /admin/insertion : revalidation complète, puis TOUS les embeddings avant
  la première écriture ;
- rollback automatique par lot_ingestion si une écriture échoue ;
- `schema_metadata.py` est l'unique source de vérité du contrat metadata ;
- unicité technique par `chunk_id` (pas par source/article), afin d'autoriser
  plusieurs chunks pour un même article à l'avenir.
"""

from __future__ import annotations

import difflib
import json
import os
import unicodedata
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from langchain_openai import OpenAIEmbeddings
from supabase import create_client

import halex_core_supabase
from auth_admin import verifier_admin
from schema_metadata import (
    CLES_ABROGATION,
    CLES_CHAINES_NON_VIDES,
    CLES_CHAINES_NULLABLES,
    CLES_COHERENCE_DOCUMENT,
    CLES_CONVENTION,
    CLES_DATES,
    CLES_ENTIERS_POSITIFS,
    CLES_ENTIERS_POSITIFS_NULLABLES,
    CLES_LISTES_ENTIERS,
    CLES_LISTES_TEXTE,
    CLES_METADATA_AUTORISEES,
    CLES_METADATA_INTERDITES,
    CLES_METADATA_NULLABLES,
    CLES_METADATA_OBLIGATOIRES,
    CLES_MODIFICATION,
    CLES_NOMBRES_NON_NEGATIFS_NULLABLES,
    LONGUEUR_MAX_PAGE_CONTENT,
    RANGS_PAR_TYPE_NORME,
    REGEX_IDENTIFIANT_RAG,
    STATUTS_VALIDES,
    THEMATIQUES,
    TYPES_BLOC_VALIDES,
    VERSION_SCHEMA_RAG,
    date_valide,
    est_nombre_reel_non_booleen,
)

load_dotenv()

router = APIRouter()

_supabase_ingestion = create_client(
    os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
)

_embeddings_ingestion = OpenAIEmbeddings(model="text-embedding-3-small")

TAILLE_MAX_OCTETS = 20 * 1024 * 1024
TAILLE_PAGE_SUPABASE = 1000
TAILLE_LOT_EMBEDDINGS = 100
TAILLE_LOT_INSERTION = 100
TAILLE_LOT_RECHERCHE_IDS = 100

_ABSENT = object()

# Listes qui doivent réellement apporter un signal dans chaque chunk.
_LISTES_NON_VIDES = {
    "hierarchie",
    "type_thematique",
    "themes_source",
    "mots_cles",
}


def _suggerer(valeur: Any, valides: set[str] | frozenset[str]) -> str:
    if not isinstance(valeur, str):
        return ""
    proches = difflib.get_close_matches(
        valeur, sorted(valides), n=2, cutoff=0.6
    )
    if not proches:
        return ""
    return " Vouliez-vous dire : " + " ou ".join(repr(p) for p in proches) + " ?"


def _emballer(
    raisons: list[str], index: int, article_label: str | None
) -> list[dict]:
    return [
        {"index": index, "article": article_label, "raison": raison}
        for raison in raisons
    ]


def _erreur_fichier(raison: str) -> dict:
    return {"index": None, "article": None, "raison": raison}


def _chaine_non_vide(valeur: Any) -> bool:
    return isinstance(valeur, str) and bool(valeur.strip())


def _valider_liste_texte(
    metadata: dict,
    cle: str,
    raisons: list[str],
) -> None:
    valeur = metadata.get(cle, _ABSENT)
    if valeur is _ABSENT:
        return  # l'absence est déjà signalée par le contrôle des obligatoires

    if not isinstance(valeur, list):
        raisons.append(
            f"'metadata.{cle}' doit être une liste, reçu : {valeur!r}"
        )
        return

    if cle in _LISTES_NON_VIDES and not valeur:
        raisons.append(f"'metadata.{cle}' ne peut pas être une liste vide")
        return

    mauvais = [
        (i, item)
        for i, item in enumerate(valeur)
        if not isinstance(item, str) or not item.strip()
    ]
    if mauvais:
        raisons.append(
            f"'metadata.{cle}' doit contenir uniquement des chaînes non vides; "
            f"éléments invalides : {mauvais[:10]!r}"
        )
        return

    doublons = sorted(
        item for item, n in Counter(valeur).items() if n > 1
    )
    if doublons:
        raisons.append(
            f"'metadata.{cle}' contient des doublons : {doublons[:20]!r}"
        )


def _valider_liste_entiers(
    metadata: dict,
    cle: str,
    raisons: list[str],
) -> None:
    valeur = metadata.get(cle, _ABSENT)
    if valeur is _ABSENT:
        return

    if not isinstance(valeur, list):
        raisons.append(
            f"'metadata.{cle}' doit être une liste, reçu : {valeur!r}"
        )
        return

    mauvais = [
        (i, item)
        for i, item in enumerate(valeur)
        if not isinstance(item, int)
        or isinstance(item, bool)
        or item <= 0
    ]
    if mauvais:
        raisons.append(
            f"'metadata.{cle}' doit contenir uniquement des entiers positifs; "
            f"éléments invalides : {mauvais[:10]!r}"
        )
        return

    doublons = sorted(
        item for item, n in Counter(valeur).items() if n > 1
    )
    if doublons:
        raisons.append(
            f"'metadata.{cle}' contient des doublons : {doublons[:20]!r}"
        )


def _valider_chunk(
    item: Any,
    index: int,
) -> tuple[list[dict], str | None, str | None, str | None, str | None]:
    """
    Retourne :
      (erreurs, article, source, document_id, chunk_id)
    """
    raisons: list[str] = []

    if not isinstance(item, dict):
        raisons.append(
            f"L'élément doit être un objet JSON, reçu : {type(item).__name__}"
        )
        return _emballer(raisons, index, None), None, None, None, None

    # Forme racine stricte : aucune clé parasite autour de page_content/metadata.
    cles_racine = set(item)
    inconnues_racine = sorted(cles_racine - {"page_content", "metadata"})
    if inconnues_racine:
        raisons.append(
            f"Clé(s) inconnue(s) au niveau du chunk : {inconnues_racine}"
        )

    page_content = item.get("page_content", _ABSENT)
    if page_content is _ABSENT:
        raisons.append("Clé 'page_content' absente")
    elif not isinstance(page_content, str):
        raisons.append(
            "'page_content' doit être une chaîne de caractères, "
            f"reçu : {page_content!r}"
        )
    elif not page_content.strip():
        raisons.append("'page_content' est vide")
    elif len(page_content) > LONGUEUR_MAX_PAGE_CONTENT:
        raisons.append(
            f"'page_content' trop long : {len(page_content)} caractères "
            f"(maximum {LONGUEUR_MAX_PAGE_CONTENT})"
        )

    metadata = item.get("metadata", _ABSENT)
    if metadata is _ABSENT:
        raisons.append("Clé 'metadata' absente")
        return _emballer(raisons, index, None), None, None, None, None
    if not isinstance(metadata, dict):
        raisons.append(
            f"'metadata' doit être un objet JSON, reçu : {type(metadata).__name__}"
        )
        return _emballer(raisons, index, None), None, None, None, None

    article = (
        metadata.get("article")
        if _chaine_non_vide(metadata.get("article"))
        else None
    )
    source = (
        metadata.get("source")
        if _chaine_non_vide(metadata.get("source"))
        else None
    )
    document_id = (
        metadata.get("document_id")
        if _chaine_non_vide(metadata.get("document_id"))
        else None
    )
    chunk_id = (
        metadata.get("chunk_id")
        if _chaine_non_vide(metadata.get("chunk_id"))
        else None
    )

    interdites = sorted(set(metadata) & CLES_METADATA_INTERDITES)
    for cle in interdites:
        raisons.append(
            f"Clé 'metadata.{cle}' interdite : elle est générée exclusivement "
            "par le serveur lors de l'insertion"
        )

    inconnues = sorted(
        set(metadata) - CLES_METADATA_AUTORISEES - CLES_METADATA_INTERDITES
    )
    for cle in inconnues:
        raisons.append(
            f"Clé 'metadata.{cle}' inconnue (valeur : {metadata[cle]!r})"
        )

    manquantes = sorted(CLES_METADATA_OBLIGATOIRES - set(metadata))
    for cle in manquantes:
        raisons.append(f"Clé 'metadata.{cle}' absente")

    # Chaînes obligatoirement non vides.
    for cle in sorted(CLES_CHAINES_NON_VIDES):
        if cle not in metadata:
            continue
        valeur = metadata[cle]
        if not _chaine_non_vide(valeur):
            raisons.append(
                f"'metadata.{cle}' doit être une chaîne non vide, reçu : {valeur!r}"
            )

    # Chaînes explicitement nullables.
    for cle in sorted(CLES_CHAINES_NULLABLES):
        if cle not in metadata:
            continue
        valeur = metadata[cle]
        if valeur is not None and not _chaine_non_vide(valeur):
            raisons.append(
                f"'metadata.{cle}' doit être null ou une chaîne non vide, "
                f"reçu : {valeur!r}"
            )

    # IDs techniques.
    for cle in ("document_id", "chunk_id"):
        valeur = metadata.get(cle)
        if isinstance(valeur, str) and valeur.strip():
            if not REGEX_IDENTIFIANT_RAG.fullmatch(valeur):
                raisons.append(
                    f"'metadata.{cle}' invalide : {valeur!r}. "
                    "Format attendu : majuscules ASCII, chiffres, '_' ou '-'."
                )

    # Version contractuelle.
    version = metadata.get("version_schema")
    if isinstance(version, str) and version != VERSION_SCHEMA_RAG:
        raisons.append(
            f"'metadata.version_schema'={version!r}; attendu "
            f"{VERSION_SCHEMA_RAG!r}"
        )

    # type_norme / rang.
    type_norme = metadata.get("type_norme")
    rang = metadata.get("rang")
    if type_norme not in RANGS_PAR_TYPE_NORME:
        if "type_norme" in metadata:
            raisons.append(
                f"'metadata.type_norme' invalide : {type_norme!r}. "
                f"Valeurs : {', '.join(sorted(RANGS_PAR_TYPE_NORME))}."
                + _suggerer(type_norme, set(RANGS_PAR_TYPE_NORME))
            )
    elif (
        not isinstance(rang, int)
        or isinstance(rang, bool)
        or rang != RANGS_PAR_TYPE_NORME[type_norme]
    ):
        raisons.append(
            f"'metadata.rang' incohérent : reçu {rang!r} pour "
            f"{type_norme!r}, attendu {RANGS_PAR_TYPE_NORME[type_norme]}"
        )

    # Dates.
    for cle in sorted(CLES_DATES):
        if cle not in metadata:
            continue
        valeur = metadata[cle]
        if valeur is None and cle in CLES_METADATA_NULLABLES:
            continue
        if not isinstance(valeur, str) or not date_valide(valeur):
            raisons.append(
                f"'metadata.{cle}' doit être "
                + ("null ou " if cle in CLES_METADATA_NULLABLES else "")
                + f"une date réelle YYYY-MM-DD, reçu : {valeur!r}"
            )

    # Convention : champs matérialisés partout, mais non nuls uniquement sur
    # une convention ratifiée.
    adoption = metadata.get("convention_date_adoption")
    ratification = metadata.get("convention_date_ratification")
    if type_norme == "convention_ratifiee":
        if not isinstance(adoption, str) or not date_valide(adoption):
            raisons.append(
                "'metadata.convention_date_adoption' est obligatoire et non "
                "nulle pour une convention_ratifiee"
            )
        if not isinstance(ratification, str) or not date_valide(ratification):
            raisons.append(
                "'metadata.convention_date_ratification' est obligatoire et "
                "non nulle pour une convention_ratifiee"
            )
        if (
            isinstance(adoption, str)
            and date_valide(adoption)
            and isinstance(ratification, str)
            and date_valide(ratification)
            and ratification < adoption
        ):
            raisons.append(
                "La date de ratification ne peut pas précéder la date d'adoption"
            )
    elif type_norme in RANGS_PAR_TYPE_NORME:
        for cle in CLES_CONVENTION:
            if metadata.get(cle) is not None:
                raisons.append(
                    f"'metadata.{cle}' doit être null pour type_norme={type_norme!r}"
                )

    # Statut.
    statut = metadata.get("statut")
    if statut not in STATUTS_VALIDES and "statut" in metadata:
        raisons.append(
            f"'metadata.statut' invalide : {statut!r}. "
            f"Valeurs : {', '.join(sorted(STATUTS_VALIDES))}."
            + _suggerer(statut, set(STATUTS_VALIDES))
        )

    # Booléen.
    historique = metadata.get("historique")
    if "historique" in metadata and not isinstance(historique, bool):
        raisons.append(
            f"'metadata.historique' doit être true/false, reçu : {historique!r}"
        )

    # type_bloc.
    type_bloc = metadata.get("type_bloc")
    if type_bloc not in TYPES_BLOC_VALIDES and "type_bloc" in metadata:
        raisons.append(
            f"'metadata.type_bloc' invalide : {type_bloc!r}. "
            f"Valeurs : {', '.join(sorted(TYPES_BLOC_VALIDES))}"
        )

    # Entiers positifs et article_numero.
    for cle in CLES_ENTIERS_POSITIFS:
        if cle not in metadata:
            continue
        valeur = metadata[cle]
        if (
            not isinstance(valeur, int)
            or isinstance(valeur, bool)
            or valeur <= 0
        ):
            raisons.append(
                f"'metadata.{cle}' doit être un entier strictement positif, "
                f"reçu : {valeur!r}"
            )

    for cle in CLES_ENTIERS_POSITIFS_NULLABLES:
        if cle not in metadata:
            continue
        valeur = metadata[cle]
        if valeur is not None and (
            not isinstance(valeur, int)
            or isinstance(valeur, bool)
            or valeur <= 0
        ):
            raisons.append(
                f"'metadata.{cle}' doit être null ou un entier strictement "
                f"positif, reçu : {valeur!r}"
            )

    if type_bloc == "article":
        numero = metadata.get("article_numero")
        if (
            not isinstance(numero, int)
            or isinstance(numero, bool)
            or numero <= 0
        ):
            raisons.append(
                "'metadata.article_numero' doit être un entier positif pour "
                "type_bloc='article'"
            )
    elif type_bloc in TYPES_BLOC_VALIDES:
        if metadata.get("article_numero") is not None:
            raisons.append(
                "'metadata.article_numero' doit être null pour un bloc "
                f"{type_bloc!r}"
            )

    # Listes.
    for cle in sorted(CLES_LISTES_TEXTE):
        _valider_liste_texte(metadata, cle, raisons)

    for cle in sorted(CLES_LISTES_ENTIERS):
        _valider_liste_entiers(metadata, cle, raisons)

    # Thématiques fermées.
    thematiques = metadata.get("type_thematique")
    if isinstance(thematiques, list) and all(isinstance(x, str) for x in thematiques):
        inconnues_thematiques = sorted(set(thematiques) - THEMATIQUES)
        if inconnues_thematiques:
            raisons.append(
                "'metadata.type_thematique' contient des valeurs inconnues : "
                f"{inconnues_thematiques}"
            )

    # Nombres nullable/non négatifs.
    for cle in CLES_NOMBRES_NON_NEGATIFS_NULLABLES:
        if cle not in metadata:
            continue
        valeur = metadata[cle]
        if valeur is not None and (
            not est_nombre_reel_non_booleen(valeur) or valeur < 0
        ):
            raisons.append(
                f"'metadata.{cle}' doit être null ou un nombre >= 0, "
                f"reçu : {valeur!r}"
            )

    dmin = metadata.get("duree_emprisonnement_min")
    dmax = metadata.get("duree_emprisonnement_max")
    if (
        est_nombre_reel_non_booleen(dmin)
        and est_nombre_reel_non_booleen(dmax)
        and dmin > dmax
    ):
        raisons.append(
            "'metadata.duree_emprisonnement_min' ne peut pas dépasser "
            "'metadata.duree_emprisonnement_max'"
        )

    if (dmin is not None or dmax is not None) and not _chaine_non_vide(
        metadata.get("unite_duree_emprisonnement")
    ):
        raisons.append(
            "'metadata.unite_duree_emprisonnement' doit être renseignée "
            "lorsqu'une durée d'emprisonnement est renseignée"
        )

    amin = metadata.get("amende_min")
    amax = metadata.get("amende_max")
    if (
        est_nombre_reel_non_booleen(amin)
        and est_nombre_reel_non_booleen(amax)
        and amin > amax
    ):
        raisons.append(
            "'metadata.amende_min' ne peut pas dépasser 'metadata.amende_max'"
        )

    if (amin is not None or amax is not None) and not _chaine_non_vide(
        metadata.get("devise")
    ):
        raisons.append(
            "'metadata.devise' doit être renseignée lorsqu'un montant "
            "d'amende est renseigné"
        )

    # Abrogation : valeurs non nulles uniquement sur statut=abroge.
    valeurs_abrogation = {
        cle: metadata.get(cle)
        for cle in CLES_ABROGATION
        if metadata.get(cle) is not None
    }
    if valeurs_abrogation and statut in STATUTS_VALIDES and statut != "abroge":
        raisons.append(
            "Les métadonnées d'abrogation ne peuvent être renseignées que "
            f"pour statut='abroge' : {valeurs_abrogation!r}"
        )
    if statut == "abroge" and not _chaine_non_vide(metadata.get("abroge_par")):
        raisons.append(
            "Un chunk au statut 'abroge' doit renseigner 'metadata.abroge_par'"
        )

    # Modification : valeurs non nulles uniquement sur statut=modifie.
    valeurs_modification = {
        cle: metadata.get(cle)
        for cle in CLES_MODIFICATION
        if metadata.get(cle) is not None
    }
    if valeurs_modification and statut in STATUTS_VALIDES and statut != "modifie":
        raisons.append(
            "Les métadonnées de modification ne peuvent être renseignées que "
            f"pour statut='modifie' : {valeurs_modification!r}"
        )
    if statut == "modifie":
        if not _chaine_non_vide(metadata.get("article_modifie_par")):
            raisons.append(
                "Un chunk au statut 'modifie' doit renseigner "
                "'metadata.article_modifie_par'"
            )
        valeur_date_modif = metadata.get("article_date_modification")
        if not isinstance(valeur_date_modif, str) or not date_valide(
            valeur_date_modif
        ):
            raisons.append(
                "Un chunk au statut 'modifie' doit renseigner une "
                "'metadata.article_date_modification' valide"
            )

    return (
        _emballer(raisons, index, article),
        article,
        source,
        document_id,
        chunk_id,
    )


def _chunk_ids_existants_en_base(document_ids: list[str]) -> set[str]:
    """
    Lit seulement les documents des document_id concernés.
    Batching des filtres IN + pagination explicite pour rester robuste lorsque
    plusieurs documents sont téléversés dans un même fichier.
    """
    if not document_ids:
        return set()

    existants: set[str] = set()

    for debut in range(0, len(document_ids), TAILLE_LOT_RECHERCHE_IDS):
        ids_lot = document_ids[
            debut : debut + TAILLE_LOT_RECHERCHE_IDS
        ]
        offset = 0

        for _ in range(1000):
            lot = (
                _supabase_ingestion.table("documents")
                .select("chunk_id:metadata->>chunk_id")
                .in_("metadata->>document_id", ids_lot)
                .range(offset, offset + TAILLE_PAGE_SUPABASE - 1)
                .execute()
            )
            lignes = lot.data or []

            for ligne in lignes:
                valeur = ligne.get("chunk_id")
                if isinstance(valeur, str):
                    existants.add(valeur)

            if len(lignes) < TAILLE_PAGE_SUPABASE:
                break

            offset += TAILLE_PAGE_SUPABASE
        else:
            raise RuntimeError(
                "Garde-fou pagination atteint pendant la détection des "
                "chunk_id existants (> 1 000 000 lignes pour un lot)."
            )

    return existants


def _valider_donnees(donnees: list) -> dict:
    erreurs: list[dict] = []

    info_par_index: dict[int, dict[str, str]] = {}
    chunks_par_id: dict[str, list[int]] = defaultdict(list)
    indices_par_document: dict[str, list[int]] = defaultdict(list)

    resume: dict[str, dict] = {}

    for index, item in enumerate(donnees):
        (
            erreurs_item,
            article,
            source,
            document_id,
            chunk_id,
        ) = _valider_chunk(item, index)
        erreurs.extend(erreurs_item)

        # Les contrôles fichier exploitent les identifiants individuellement
        # valides même si une autre clé du même chunk est erronée.
        if document_id:
            indices_par_document[document_id].append(index)
        if chunk_id:
            chunks_par_id[chunk_id].append(index)

        if (
            not erreurs_item
            and source
            and article
            and document_id
            and chunk_id
        ):
            info_par_index[index] = {
                "source": source,
                "article": article,
                "document_id": document_id,
                "chunk_id": chunk_id,
            }
            meta = item["metadata"]
            info = resume.setdefault(
                document_id,
                {
                    "document_id": document_id,
                    "source": source,
                    "source_courte": meta["source_courte"],
                    "type_norme": meta["type_norme"],
                    "rang": meta["rang"],
                    "date": meta["date"],
                    "date_publication": meta["date_publication"],
                    "version_schema": meta["version_schema"],
                    "nb_chunks": 0,
                    "nb_par_type_bloc": {},
                    "nb_par_statut": {},
                    "thematiques": set(),
                },
            )
            info["nb_chunks"] += 1
            tb = meta["type_bloc"]
            info["nb_par_type_bloc"][tb] = (
                info["nb_par_type_bloc"].get(tb, 0) + 1
            )
            statut = meta["statut"]
            info["nb_par_statut"][statut] = (
                info["nb_par_statut"].get(statut, 0) + 1
            )
            info["thematiques"].update(meta["type_thematique"])

    # Unicité chunk_id dans le fichier.
    doublons_internes = [
        {"chunk_id": chunk_id, "indices": sorted(indices)}
        for chunk_id, indices in sorted(chunks_par_id.items())
        if len(indices) > 1
    ]

    # Cohérence document-wide.
    for document_id, indices in sorted(indices_par_document.items()):
        metas = [
            donnees[i].get("metadata")
            for i in indices
            if isinstance(donnees[i], dict)
            and isinstance(donnees[i].get("metadata"), dict)
        ]

        for cle in sorted(CLES_COHERENCE_DOCUMENT):
            valeurs: dict[str, list[int]] = defaultdict(list)
            for i in indices:
                item = donnees[i]
                if not isinstance(item, dict) or not isinstance(
                    item.get("metadata"), dict
                ):
                    continue
                meta = item["metadata"]
                # json.dumps permet de comparer proprement null/bool/int/str.
                repr_valeur = json.dumps(
                    meta.get(cle, _ABSENT if cle not in meta else None),
                    ensure_ascii=False,
                    sort_keys=True,
                    default=lambda _: "<ABSENT>",
                )
                valeurs[repr_valeur].append(i)

            if len(valeurs) > 1:
                repartition = [
                    {"valeur": valeur, "indices": idxs[:30], "nb": len(idxs)}
                    for valeur, idxs in sorted(valeurs.items())
                ]
                erreurs.append(
                    _erreur_fichier(
                        f"Document {document_id!r} : '{cle}' incohérent entre "
                        f"les chunks — {repartition}"
                    )
                )

        # ordre unique par document.
        ordre_par_index = {}
        for i in indices:
            meta = donnees[i].get("metadata") if isinstance(donnees[i], dict) else None
            if isinstance(meta, dict):
                ordre = meta.get("ordre")
                if isinstance(ordre, int) and not isinstance(ordre, bool):
                    ordre_par_index[i] = ordre

        compte = Counter(ordre_par_index.values())
        dup_ordre = sorted(v for v, n in compte.items() if n > 1)
        if dup_ordre:
            detail = {
                v: sorted(i for i, ov in ordre_par_index.items() if ov == v)
                for v in dup_ordre
            }
            erreurs.append(
                _erreur_fichier(
                    f"Document {document_id!r} : valeurs 'ordre' dupliquées : "
                    f"{detail}"
                )
            )

        # Signal de contiguïté dans le résumé, non bloquant.
        if document_id in resume and ordre_par_index:
            valeurs = sorted(set(ordre_par_index.values()))
            resume[document_id]["ordre_min"] = valeurs[0]
            resume[document_id]["ordre_max"] = valeurs[-1]
            resume[document_id]["ordre_contigu"] = (
                len(valeurs) == len(ordre_par_index)
                and valeurs[-1] - valeurs[0] + 1 == len(valeurs)
            )

    # Cohérence chunk_id -> document_id.
    for chunk_id, indices in chunks_par_id.items():
        document_ids = {
            donnees[i]["metadata"].get("document_id")
            for i in indices
            if isinstance(donnees[i], dict)
            and isinstance(donnees[i].get("metadata"), dict)
        }
        if len(document_ids) > 1:
            erreurs.append(
                _erreur_fichier(
                    f"chunk_id {chunk_id!r} apparaît avec plusieurs "
                    f"document_id : {sorted(map(str, document_ids))}"
                )
            )

    # Doublons en base.
    document_ids_valides = sorted({
        info["document_id"] for info in info_par_index.values()
    })
    chunk_ids_fichier = {
        info["chunk_id"] for info in info_par_index.values()
    }
    chunk_ids_base = _chunk_ids_existants_en_base(document_ids_valides)
    doublons_en_base = sorted(chunk_ids_fichier & chunk_ids_base)

    for info in resume.values():
        info["thematiques"] = sorted(info["thematiques"])
        info.setdefault("ordre_min", None)
        info.setdefault("ordre_max", None)
        info.setdefault("ordre_contigu", None)

    nb_total = len(donnees)
    indices_erreur = {
        e["index"] for e in erreurs if e["index"] is not None
    }
    nb_valides = nb_total - len(indices_erreur)

    valide = len(erreurs) == 0
    pret = valide and not doublons_internes and not doublons_en_base

    return {
        "version_schema_attendue": VERSION_SCHEMA_RAG,
        "nb_chunks_total": nb_total,
        "nb_chunks_valides": nb_valides,
        "valide": valide,
        "pret_pour_insertion": pret,
        "erreurs": erreurs,
        "doublons_internes": doublons_internes,
        "doublons_en_base": [
            {"chunk_id": chunk_id} for chunk_id in doublons_en_base
        ],
        "resume_par_source": list(resume.values()),
    }


async def _lire_et_parser_fichier(fichier: UploadFile) -> list:
    nom = fichier.filename or ""
    if not nom.lower().endswith(".json"):
        raise HTTPException(
            status_code=400,
            detail=f"Extension invalide : {nom!r}; .json requis",
        )

    contenu = await fichier.read()

    if len(contenu) > TAILLE_MAX_OCTETS:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Fichier trop volumineux : {len(contenu)} octets "
                f"(maximum {TAILLE_MAX_OCTETS})"
            ),
        )

    try:
        texte = contenu.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"UTF-8 strict requis : {exc}",
        ) from exc

    # Neutralise BOM éventuel puis normalise les accents en NFC.
    texte = texte.lstrip("\ufeff")
    texte = unicodedata.normalize("NFC", texte)

    try:
        donnees = json.loads(texte)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"JSON invalide : {exc}",
        ) from exc

    if not isinstance(donnees, list):
        raise HTTPException(
            status_code=400,
            detail=(
                "La racine du fichier doit être une liste JSON; reçu : "
                f"{type(donnees).__name__}"
            ),
        )

    if not donnees:
        raise HTTPException(
            status_code=400,
            detail="Le fichier JSON ne contient aucun chunk",
        )

    return donnees


def _preparer_metadata_insertion(metadata: dict) -> dict:
    # Copie défensive : l'objet parsé ne doit jamais être modifié en place.
    preparees = dict(metadata)
    for cle in CLES_METADATA_NULLABLES:
        preparees.setdefault(cle, None)
    return preparees


def _generer_embeddings(textes: list[str]) -> list[list[float]]:
    """
    IMPORTANT : l'embedding reste calculé sur page_content uniquement.
    On conserve ainsi la sémantique et les seuils existants. Les nouvelles
    métadonnées RAG seront exploitées séparément par le retrieval/reranking.
    """
    vecteurs: list[list[float]] = []

    for debut in range(0, len(textes), TAILLE_LOT_EMBEDDINGS):
        lot = textes[debut : debut + TAILLE_LOT_EMBEDDINGS]
        try:
            vecteurs_lot = _embeddings_ingestion.embed_documents(lot)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=(
                    "Échec embeddings pour le lot "
                    f"{debut}-{debut + len(lot) - 1}/{len(textes) - 1} : "
                    f"{type(exc).__name__} — {exc}. "
                    "Aucune donnée n'a été écrite."
                ),
            ) from exc

        if len(vecteurs_lot) != len(lot):
            raise HTTPException(
                status_code=502,
                detail=(
                    f"{len(vecteurs_lot)} vecteur(s) reçu(s) pour "
                    f"{len(lot)} texte(s). Aucune donnée n'a été écrite."
                ),
            )

        vecteurs.extend(vecteurs_lot)

    if len(vecteurs) != len(textes):
        raise HTTPException(
            status_code=502,
            detail=(
                f"Incohérence globale embeddings : {len(vecteurs)} vecteurs "
                f"pour {len(textes)} textes"
            ),
        )

    return vecteurs


def _inserer_documents(lignes: list[dict], lot_ingestion: str) -> int:
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
            nettoyage = (
                "Le rollback automatique a échoué; vérification manuelle requise."
            )
        elif nb_supprimees == inseres:
            nettoyage = (
                f"Rollback automatique réussi : {nb_supprimees} ligne(s) supprimée(s)."
            )
        else:
            nettoyage = (
                f"Rollback incomplet : {nb_supprimees}/{inseres} ligne(s) supprimée(s)."
            )

        raise HTTPException(
            status_code=500,
            detail=(
                f"Échec d'insertion après {inseres}/{len(lignes)} chunks : "
                f"{type(exc).__name__} — {exc}. {nettoyage} "
                f"lot_ingestion={lot_ingestion}"
            ),
        ) from exc

    return inseres


@router.post("/admin/validation")
async def endpoint_validation(
    fichier: UploadFile = File(...),
    admin: dict = Depends(verifier_admin),
):
    donnees = await _lire_et_parser_fichier(fichier)
    return _valider_donnees(donnees)


@router.post("/admin/insertion")
async def endpoint_insertion(
    fichier: UploadFile = File(...),
    admin: dict = Depends(verifier_admin),
):
    donnees = await _lire_et_parser_fichier(fichier)
    rapport = _valider_donnees(donnees)

    if not rapport["pret_pour_insertion"]:
        raise HTTPException(status_code=409, detail=rapport)

    # On génère les embeddings avant la première écriture.
    textes = [item["page_content"] for item in donnees]
    vecteurs = _generer_embeddings(textes)

    lot_ingestion = str(uuid.uuid4())
    date_ingestion = datetime.now(timezone.utc).isoformat()

    lignes = []
    for item, vecteur in zip(donnees, vecteurs):
        metadata = _preparer_metadata_insertion(item["metadata"])
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

    halex_core_supabase.invalider_caches()

    return {
        "succes": True,
        "version_schema": VERSION_SCHEMA_RAG,
        "lot_ingestion": lot_ingestion,
        "date_ingestion": date_ingestion,
        "nb_chunks_inseres": nb_chunks_inseres,
        "resume_par_source": rapport["resume_par_source"],
        "commande_annulation": (
            "DELETE FROM documents "
            f"WHERE metadata->>'lot_ingestion' = '{lot_ingestion}';"
        ),
    }