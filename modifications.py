#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
modifications.py
================
Enrichissement des chunks récupérés par les textes qui les MODIFIENT.

PRINCIPE
--------
Un chunk décrit ce qu'un texte EST. La relation « ce texte en modifie un
autre » vit dans la table `relations_normatives`, jamais dans les
métadonnées. Ce module fait le pont entre les deux, EN AVAL de la
récupération.

Position dans le pipeline (halex_core_supabase.py) :

    detecter_reference_article()  ─┐
    recherche vectorielle         ─┤
                                   ▼
                     [flux de clarification]
                                   ▼
                     enrichir_modifications()   ← ICI
                                   ▼
                        assemblage du prompt

APRÈS la clarification, jamais avant : enrichir des chunks encore ambigus
multiplierait les branches à désambiguïser.

GARANTIE DE NON-RÉGRESSION
--------------------------
Ce module est ADDITIF. En cas d'erreur (table absente, réseau, libellé
introuvable), il retourne les chunks d'entrée INCHANGÉS et journalise un
avertissement. Une panne ici ne doit jamais empêcher Halex de répondre.

DÉPENDANCES : le client Supabase déjà instancié par le core. Ce module ne
crée aucune connexion et ne lit aucune variable d'environnement.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# ==========================================================================
# 1. CONFIGURATION
# ==========================================================================

TABLE_CHUNKS = "documents"
TABLE_REGISTRE = "sources_registre"
TABLE_RELATIONS = "relations_normatives"

# Colonnes possibles du texte selon la couche d'accès (LangChain expose
# `page_content`, la table stocke `content`). Les deux sont tolérées.
CLES_CONTENU = ("page_content", "content")

# Profondeur maximale de chaînage : une loi modificatrice peut elle-même
# avoir été modifiée. Au-delà de 2 niveaux, le contexte devient illisible
# pour le citoyen et coûteux en tokens. Un garde-fou anti-boucle
# (ensemble `deja_vus`) empêche de toute façon la récursion infinie.
PROFONDEUR_MAX = 2

# Nombre maximal de chunks modificateurs ajoutés par requête. Protège la
# fenêtre de contexte si un article venait à être modifié dix fois.
LIMITE_AJOUTS = 6


# ==========================================================================
# 2. BLOC DE PROMPT
# ==========================================================================
#
# À insérer AVANT les règles d'arbitrage (rang / récence / statut), pas
# après : `gpt-4o-mini` suit plus fidèlement une règle placée en amont.
#
# Sans ce bloc, l'arbitrage générique ferait gagner la loi (rang 2, date
# postérieure) et ÉCARTERAIT l'article d'origine — réponse fausse : le
# citoyen doit recevoir l'article TEL QUE MODIFIÉ, pas la seule loi
# modificatrice.
#
# À n'injecter QUE si `relations` est non vide (voir formater_bloc_prompt).

BLOC_PROMPT_MODIFICATIONS = """\
RÈGLE DE MODIFICATION (prioritaire sur les règles d'arbitrage ci-dessous)

Le contexte contient un article ET un texte qui le modifie. Ce n'est PAS
un conflit de normes : n'applique pas l'arbitrage par rang ou par date,
et n'écarte aucun des deux textes.

Structure ta réponse ainsi :
1. L'état actuellement en vigueur de l'article (texte d'origine tel que
   modifié) — c'est la réponse à la question posée.
2. Une mention brève de la modification : quel texte, quelle date, ce qui
   a changé.

Cite OBLIGATOIREMENT les deux sources avec leurs étiquettes
[SOURCE: ...] : l'article d'origine ET le texte modificateur.

Relations présentes dans ce contexte :
{lignes}
"""


# ==========================================================================
# 3. ACCÈS AUX CHUNKS (agnostique de la couche : dict ou Document)
# ==========================================================================

def _metadata(chunk: Any) -> dict:
    if isinstance(chunk, dict):
        return chunk.get("metadata") or {}
    return getattr(chunk, "metadata", {}) or {}


def _contenu(chunk: Any) -> str:
    if isinstance(chunk, dict):
        for cle in CLES_CONTENU:
            if cle in chunk:
                return chunk[cle] or ""
        return ""
    for cle in CLES_CONTENU:
        valeur = getattr(chunk, cle, None)
        if valeur is not None:
            return valeur
    return ""


def _fabriquer(modele: Any, contenu: str, metadata: dict) -> Any:
    """
    Produit un chunk du MÊME type que ceux déjà en circulation. Sans cela,
    un dict injecté dans une liste de Document (ou l'inverse) casserait
    l'assemblage du prompte en aval.
    """
    if isinstance(modele, dict):
        cle = next((c for c in CLES_CONTENU if c in modele), "page_content")
        return {cle: contenu, "metadata": metadata}
    return type(modele)(page_content=contenu, metadata=metadata)


def _identite(chunk: Any) -> tuple[str, str]:
    """Couple (source, article) — clé de déduplication et de jointure."""
    meta = _metadata(chunk)
    return (meta.get("source") or "", meta.get("article") or "")


# ==========================================================================
# 4. REGISTRE DES SOURCES
# ==========================================================================

_cache_registre: tuple[dict[str, str], dict[str, str]] | None = None


def invalider_cache_registre() -> None:
    """À appeler après toute ingestion réussie, en même temps que les
    caches du core (mapping mots-clés, libellés)."""
    global _cache_registre
    _cache_registre = None


def charger_registre(client) -> tuple[dict[str, str], dict[str, str]]:
    """
    Retourne (libelle -> id, id -> libelle).

    Le registre fait le pont entre les chunks (libellé littéral dans
    `metadata.source`) et les relations (slug stable). Corriger un libellé
    se fait ICI, sans toucher aux relations.

    Mis en cache au niveau du module : la table ne change qu'à l'ingestion.
    Un cache vide n'est jamais mémorisé — une lecture ratée doit pouvoir
    réussir à la requête suivante, pas désactiver la fonction jusqu'au
    prochain redémarrage.
    """
    global _cache_registre
    if _cache_registre is not None:
        return _cache_registre

    reponse = client.table(TABLE_REGISTRE).select("id, libelle").execute()
    lignes = reponse.data or []
    if not lignes:
        return {}, {}
    par_libelle = {l["libelle"]: l["id"] for l in lignes}
    par_id = {l["id"]: l["libelle"] for l in lignes}
    _cache_registre = (par_libelle, par_id)
    return _cache_registre


# ==========================================================================
# 5. ENRICHISSEMENT
# ==========================================================================

def _chercher_relations(client, cibles: list[tuple[str, str]]) -> list[dict]:
    """
    Une seule requête pour tout le lot. On surfiltre côté serveur (deux
    `in_` indépendants), puis on retient les couples EXACTS côté Python :
    `in_` sur deux colonnes ferait un produit cartésien qui remonterait
    (source A, article de B).
    """
    if not cibles:
        return []
    ids = sorted({c[0] for c in cibles})
    articles = sorted({c[1] for c in cibles})

    reponse = (
        client.table(TABLE_RELATIONS)
        .select("source_modifiante, article_modifiant, "
                "source_modifiee, article_modifie, "
                "type_relation, date_effet, note")
        .in_("source_modifiee", ids)
        .in_("article_modifie", articles)
        .execute()
    )
    voulus = set(cibles)
    return [
        r for r in (reponse.data or [])
        if (r["source_modifiee"], r["article_modifie"]) in voulus
    ]


def _recuperer_chunks(client, besoins: list[tuple[str, str]]) -> list[dict]:
    """Chunks modificateurs, par (libellé de source, libellé d'article)."""
    if not besoins:
        return []
    sources = sorted({b[0] for b in besoins})
    articles = sorted({b[1] for b in besoins})

    reponse = (
        client.table(TABLE_CHUNKS)
        .select("content, metadata")
        .in_("metadata->>source", sources)
        .in_("metadata->>article", articles)
        .execute()
    )
    voulus = set(besoins)
    return [
        r for r in (reponse.data or [])
        if ((r.get("metadata") or {}).get("source"),
            (r.get("metadata") or {}).get("article")) in voulus
    ]


def _enrichir_depuis_metadata(client, chunks: list[Any]) -> tuple[list[Any], list[dict]]:
    """Repli article -> source modificatrice déclaré dans les métadonnées.

    `article_modifie_par` désigne une source, pas nécessairement un article
    précis. On récupère donc les chunks de cette source dans leur ordre et on
    laisse le moteur sélectionner les passages modificatifs, avec une limite
    stricte pour protéger la fenêtre de contexte.
    """
    sources = sorted({
        valeur.strip()
        for chunk in chunks
        if _metadata(chunk).get("statut") == "modifie"
        and isinstance((valeur := _metadata(chunk).get("article_modifie_par")), str)
        and valeur.strip()
    })
    if not sources:
        return chunks, []

    reponse = (
        client.table(TABLE_CHUNKS)
        .select("content, metadata")
        .in_("metadata->>source", sources)
        .order("metadata->>ordre")
        .limit(LIMITE_AJOUTS)
        .execute()
    )
    lignes = list(reponse.data or [])

    # Les références officielles sont parfois stockées dans
    # `article_modifie_par` alors que metadata.source contient un titre.
    # Exemple réel : « Loi no CL-05-2009-006... » versus « Loi modifiant
    # l'article 257... ». Si l'égalité de source ne donne rien, le numéro
    # officiel permet d'identifier un chunk, puis son libellé de source.
    if not lignes:
        numeros = sorted({
            match.group(0)
            for source in sources
            if (match := re.search(r"CL-\d{2}-\d{4}-\d{3}", source, re.I))
        })
        sources_resolues: set[str] = set()
        for numero in numeros:
            candidats = (
                client.table(TABLE_CHUNKS)
                .select("content, metadata")
                .ilike("content", f"%{numero}%")
                .limit(1)
                .execute()
            )
            for candidat in candidats.data or []:
                libelle = (candidat.get("metadata") or {}).get("source")
                if libelle:
                    sources_resolues.add(libelle)
        if sources_resolues:
            lignes = list((
                client.table(TABLE_CHUNKS)
                .select("content, metadata")
                .in_("metadata->>source", sorted(sources_resolues))
                .order("metadata->>ordre")
                .limit(LIMITE_AJOUTS)
                .execute()
            ).data or [])
    deja = {_identite(chunk) for chunk in chunks}
    ajouts: list[Any] = []
    relations: list[dict] = []
    for ligne in lignes:
        meta = ligne.get("metadata") or {}
        identite = (meta.get("source") or "", meta.get("article") or "")
        if identite in deja:
            continue
        deja.add(identite)
        ajouts.append(_fabriquer(chunks[0], ligne.get("content") or "", meta))
    for chunk in chunks:
        meta = _metadata(chunk)
        source_modifiante = meta.get("article_modifie_par")
        if meta.get("statut") == "modifie" and source_modifiante:
            relations.append({
                "source_modifiante": source_modifiante,
                "article_modifiant": "article(s) de modification",
                "source_modifiee": meta.get("source", ""),
                "article_modifie": meta.get("article", ""),
                "type_relation": "modifie",
                "date_effet": meta.get("article_date_modification") or "date non renseignée",
                "note": meta.get("article_publication_modification"),
            })
    return chunks + ajouts, relations


def enrichir_modifications(
    client, chunks: Iterable[Any]
) -> tuple[list[Any], list[dict]]:
    """
    Ajoute aux chunks récupérés les textes qui les modifient.

    Retourne (chunks_enrichis, relations_appliquees).
      * chunks_enrichis : liste d'entrée + ajouts, ORDRE D'ENTRÉE PRÉSERVÉ
        (les ajouts sont concaténés à la fin, jamais intercalés : l'ordre
        de pertinence issu de la recherche vectorielle reste lisible).
      * relations_appliquees : à passer à formater_bloc_prompt(). Vide =>
        n'injecter aucun bloc de prompt.

    Ne lève jamais : en cas d'échec, retourne (chunks d'entrée, []).
    """
    chunks = list(chunks)
    if not chunks:
        return chunks, []

    try:
        chunks, relations_metadata = _enrichir_depuis_metadata(client, chunks)
    except Exception as erreur:                       # noqa: BLE001
        logger.warning("modifications : repli metadata interrompu (%s).", erreur)
        relations_metadata = []

    try:
        par_libelle, par_id = charger_registre(client)
    except Exception as erreur:                       # noqa: BLE001
        logger.warning("modifications : registre illisible (%s) — "
                       "enrichissement ignoré.", erreur)
        return chunks, relations_metadata

    if not par_libelle:
        logger.warning("modifications : `%s` est vide. Le peuplement du "
                       "registre est un prérequis.", TABLE_REGISTRE)
        return chunks, relations_metadata

    ajouts: list[Any] = []
    relations_vues: list[dict] = list(relations_metadata)
    deja_vus: set[tuple[str, str]] = {_identite(c) for c in chunks}
    front = list(chunks)

    try:
        for _ in range(PROFONDEUR_MAX):
            if not front or len(ajouts) >= LIMITE_AJOUTS:
                break

            # (slug, article) des chunks du front présents au registre.
            cibles: list[tuple[str, str]] = []
            for chunk in front:
                source, article = _identite(chunk)
                slug = par_libelle.get(source)
                if slug and article:
                    cibles.append((slug, article))
            cibles = sorted(set(cibles))

            relations = _chercher_relations(client, cibles)
            if not relations:
                break

            # Résolution slug -> libellé, en écartant ce qui est déjà là.
            besoins: list[tuple[str, str]] = []
            for rel in relations:
                libelle = par_id.get(rel["source_modifiante"])
                if not libelle:
                    logger.warning("modifications : slug '%s' absent du "
                                   "registre.", rel["source_modifiante"])
                    continue
                cle = (libelle, rel["article_modifiant"])
                if cle not in deja_vus:
                    besoins.append(cle)
                relations_vues.append(rel)

            besoins = sorted(set(besoins))
            if not besoins:
                break

            nouveaux = _recuperer_chunks(client, besoins)
            front = []
            for ligne in nouveaux:
                meta = ligne.get("metadata") or {}
                cle = (meta.get("source"), meta.get("article"))
                if cle in deja_vus or len(ajouts) >= LIMITE_AJOUTS:
                    continue
                deja_vus.add(cle)
                chunk = _fabriquer(chunks[0], ligne.get("content") or "", meta)
                ajouts.append(chunk)
                front.append(chunk)

            manquants = set(besoins) - deja_vus
            if manquants:
                # Relation déclarée mais chunk absent : incohérence entre la
                # table et le corpus (texte désingéré, libellé d'article
                # divergent). Signalée, jamais fatale.
                logger.warning("modifications : relation(s) sans chunk "
                               "correspondant : %s", sorted(manquants))

    except Exception as erreur:                       # noqa: BLE001
        logger.warning("modifications : enrichissement interrompu (%s) — "
                       "réponse produite sans les textes modificateurs.",
                       erreur)
        return chunks, []

    if ajouts:
        logger.info("modifications : %d chunk(s) modificateur(s) ajouté(s).",
                    len(ajouts))
    return chunks + ajouts, relations_vues


# ==========================================================================
# 6. BLOC DE PROMPT
# ==========================================================================

def formater_bloc_prompt(relations: list[dict], par_id: dict[str, str] | None = None) -> str:
    """
    Rend le bloc à injecter, ou "" si aucune relation — dans ce cas AUCUN
    texte ne doit être ajouté au prompt : une règle sans objet dilue les
    autres et coûte des tokens sur chaque requête.
    """
    if not relations:
        return ""
    par_id = par_id or {}
    lignes = []
    for rel in relations:
        modifiante = par_id.get(rel["source_modifiante"],
                                rel["source_modifiante"])
        modifiee = par_id.get(rel["source_modifiee"], rel["source_modifiee"])
        lignes.append(
            f"- {modifiee}, {rel['article_modifie']} : "
            f"{rel['type_relation']} par {modifiante}, "
            f"{rel['article_modifiant']} (effet : {rel['date_effet']})"
        )
    return BLOC_PROMPT_MODIFICATIONS.format(lignes="\n".join(lignes))
