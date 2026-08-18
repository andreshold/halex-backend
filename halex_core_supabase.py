"""
halex_core_supabase.py
Moteur RAG Halex sur Supabase/pgvector.

Phase 4 :
- résolution conversationnelle avant retrieval ;
- enrichissement des références explicites ;
- qualification normative avant rédaction ;
- priorité déterministe (statut/rang/spécialité/date) uniquement lorsqu'une
  contradiction a été qualifiée ;
- sélection déterministe de la version juridique applicable avant rédaction.

La RPC Supabase renvoie une similarité cosinus : 1 - cosine_distance.
"""

import json
import logging
import os
import re
import unicodedata
from datetime import date
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from supabase import create_client

from schema_metadata import (
    STATUTS_APPLICABLES,
    libelle_source,
    libelle_statut,
    libelle_type_norme,
)

from conversation_context import resoudre_question_conversationnelle
from moteur_normatif import analyser_normativement

from modifications import (
    charger_registre,
    enrichir_modifications,
    formater_bloc_prompt,
    invalider_cache_registre,
)

load_dotenv()

_logger = logging.getLogger(__name__)

_embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
_llm_json = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    model_kwargs={"response_format": {"type": "json_object"}},
)
_supabase = create_client(
    os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
)


class ReponseGeneree(BaseModel):
    """Sortie structurée du LLM : réponse rédigée + étiquettes SOURCE citées."""

    reponse: str = Field(
        description=(
            "La réponse rédigée pour l'utilisateur, en français clair, "
            "avec citations de l'article ET du texte source."
        )
    )
    articles_cites: list[str] = Field(
        default_factory=list,
        description=(
            "Liste des étiquettes [SOURCE: ...] réellement utilisées pour "
            "fonder la réponse. Recopier ces étiquettes EXACTEMENT telles "
            "qu'elles apparaissent dans le contexte fourni. Ne pas inclure "
            "les extraits consultés mais non utilisés dans la réponse."
        ),
    )


_llm_structure = _llm.with_structured_output(ReponseGeneree)

DATE_VIDE_LEGISLATIF = "2020-01-13"

# Seuils historiques de similarité cosinus (RPC match_documents :
# similarity = 1 - cosine_distance). Ils sont conservés pour compatibilité
# comportementale et devront être recalibrés empiriquement sur un jeu de
# questions de référence lorsque plusieurs corpus seront chargés.
SEUIL_SIM = 0.375
SEUIL_SIM_SECONDE_CHANCE = 0.55

MODE_PAR_DEFAUT = "citoyen"


def _numero_version(meta: dict) -> int:
    valeur = meta.get("version_numero", 1)
    if isinstance(valeur, int) and not isinstance(valeur, bool) and valeur > 0:
        return valeur
    return 1


def _date_debut_version(meta: dict) -> str:
    valeur = meta.get("date_debut_effet")
    if isinstance(valeur, str) and valeur:
        return valeur
    valeur = meta.get("date")
    return valeur if isinstance(valeur, str) else ""


def _version_applicable(meta: dict, date_cible: str | None = None) -> bool:
    """True si le chunk peut fonder l'état du droit à la date cible.

    `date_fin_effet` est l'autorité temporelle de la version. `historique`
    reste un indicateur documentaire hérité et n'est pas utilisé comme filtre
    dur afin de conserver la compatibilité avec le corpus v1.0 migré.
    """
    if meta.get("statut") not in STATUTS_APPLICABLES:
        return False

    cible = date_cible or date.today().isoformat()
    debut = _date_debut_version(meta)
    fin = meta.get("date_fin_effet")

    if isinstance(debut, str) and debut and debut > cible:
        return False
    if isinstance(fin, str) and fin and fin < cible:
        return False
    return True


def _selectionner_versions_applicables(
    documents: list[dict],
    date_cible: str | None = None,
) -> list[dict]:
    """Conserve seulement la version applicable la plus récente de chaque
    (document_id, article), tout en gardant tous les chunks d'une même version
    lorsqu'un article est segmenté.
    """
    applicables = [
        d
        for d in documents
        if _version_applicable(d.get("metadata") or {}, date_cible)
    ]
    if not applicables:
        return []

    max_version: dict[tuple[str, str], int] = {}
    for doc in applicables:
        meta = doc.get("metadata") or {}
        identite = str(meta.get("document_id") or meta.get("source") or "?")
        article = str(meta.get("article") or "?")
        cle = (identite, article)
        max_version[cle] = max(
            max_version.get(cle, 0),
            _numero_version(meta),
        )

    resultat: list[dict] = []
    for doc in applicables:
        meta = doc.get("metadata") or {}
        identite = str(meta.get("document_id") or meta.get("source") or "?")
        article = str(meta.get("article") or "?")
        cle = (identite, article)
        if _numero_version(meta) == max_version[cle]:
            resultat.append(doc)
    return resultat


def _selectionner_derniere_version(documents: list[dict]) -> list[dict]:
    """Repli historique pour un article qui n'a plus de version applicable.

    Sert notamment au lookup direct d'un article abrogé : on montre sa dernière
    version en avertissant explicitement qu'elle n'est plus en vigueur.
    """
    if not documents:
        return []

    max_version: dict[tuple[str, str], int] = {}
    for doc in documents:
        meta = doc.get("metadata") or {}
        identite = str(meta.get("document_id") or meta.get("source") or "?")
        article = str(meta.get("article") or "?")
        cle = (identite, article)
        max_version[cle] = max(
            max_version.get(cle, 0),
            _numero_version(meta),
        )

    return [
        doc
        for doc in documents
        if _numero_version(doc.get("metadata") or {})
        == max_version[
            (
                str((doc.get("metadata") or {}).get("document_id")
                    or (doc.get("metadata") or {}).get("source")
                    or "?"),
                str((doc.get("metadata") or {}).get("article") or "?"),
            )
        ]
    ]


def _necessite_enrichissement_modifications(documents: list[dict]) -> bool:
    """Le registre textuel reste un filet de compatibilité pour les anciens
    chunks `modifie`. Une version consolidée matérialisée ne doit pas être
    recombinée par le LLM avec son acte modificatif.
    """
    return any(
        (d.get("metadata") or {}).get("statut") == "modifie"
        and (d.get("metadata") or {}).get("version_consolidee") is not True
        for d in documents
    )


INSTRUCTIONS_MODES = {
    "citoyen": """STYLE DE RÉPONSE — MODE CITOYEN (défaut) :
- Oriente ta réponse vers l'ACTION : que peut faire la personne, quelles
  démarches concrètes, auprès de quelle institution.
- Langage simple et direct, phrases courtes. Évite le jargon ; si un terme
  juridique est indispensable, explique-le en une phrase.
- Structure : d'abord la réponse pratique, ensuite la base légale (articles
  cités).
- Termine si pertinent par les étapes concrètes à suivre.""",

    "educatif": """STYLE DE RÉPONSE — MODE ÉDUCATIF :
- Objectif : faire COMPRENDRE le droit, pas seulement l'énoncer.
- Explique le principe juridique, son origine et sa logique, avec pédagogie.
- Illustre systématiquement avec un exemple concret de la vie courante en
  Haïti.
- Définis chaque terme juridique rencontré.
- Structure progressive : du principe général vers le cas particulier.""",

    "judiciaire": """STYLE DE RÉPONSE — MODE JUDICIAIRE / PROFESSIONNEL :
- Public : avocats, notaires, greffiers, magistrats.
- Terminologie juridique exacte, sans vulgarisation ni définitions de base.
- Cite les articles avec précision maximale : numéro, texte source, alinéa
  si applicable.
- Mentionne explicitement la position du texte dans la hiérarchie des normes
  et son statut d'application.
- Format dense et technique, sans détour pédagogique.""",

}

SALUTATIONS: set[str] = {
    "bonjour", "bonsoir", "salut", "merci", "bonswa", "bonjou",
    "alo", "hello", "hi", "sak", "pase", "sak-pase", "halex",
}


def _chercher(question: str, k: int = 6) -> list[dict]:
    """Recherche vectorielle puis sélection de la version applicable.

    La RPC peut encore renvoyer des versions historiques. On demande donc une
    fenêtre plus large et le backend choisit ensuite, de façon déterministe,
    la version courante la plus récente de chaque article.
    """
    vecteur = _embeddings.embed_query(question)
    resultat = _supabase.rpc(
        "match_documents",
        {"query_embedding": vecteur, "match_count": k * 8},
    ).execute()
    versions = _selectionner_versions_applicables(resultat.data or [])
    return versions[:k]



def _enrichir_references_articles(
    documents: list[dict],
    limite_documents_sources: int = 4,
    limite_references: int = 8,
) -> list[dict]:
    """Ajoute conservativement les articles explicitement référencés.

    Utilise `metadata.references_articles` du nouveau schéma RAG.
    Cette expansion est DÉTERMINISTE : aucun LLM et aucune similarité.
    Elle ne signifie pas que l'article référencé est nécessaire à la réponse ;
    le moteur normatif le qualifiera ensuite (complémentaire/contexte/etc.).

    Les références sont recherchées dans la même `metadata.source` que le
    document qui les cite. Les textes abrogés ne sont pas ajoutés à l'état
    courant du droit.
    """
    if not documents:
        return documents

    existants = {
        (
            (d.get("metadata") or {}).get("source"),
            (d.get("metadata") or {}).get("article"),
        )
        for d in documents
    }

    par_source: dict[str, list[str]] = {}
    total = 0

    for doc in documents[:limite_documents_sources]:
        meta = doc.get("metadata") or {}
        source = meta.get("source")
        refs = meta.get("references_articles")
        if not isinstance(source, str) or not isinstance(refs, list):
            continue

        for numero in refs:
            if total >= limite_references:
                break
            if isinstance(numero, bool) or not isinstance(numero, (int, str)):
                continue
            numero_texte = str(numero).strip()
            if not numero_texte:
                continue

            if numero_texte.lower().startswith("article "):
                article_principal = (
                    "Article " + numero_texte.split(None, 1)[1]
                )
                numero_brut = numero_texte.split(None, 1)[1]
            else:
                article_principal = f"Article {numero_texte}"
                numero_brut = numero_texte

            candidats = [article_principal]
            if numero_brut == "1":
                candidats.append("Article 1er")

            for article in candidats:
                if total >= limite_references:
                    break
                if (source, article) in existants:
                    continue
                par_source.setdefault(source, [])
                if article not in par_source[source]:
                    par_source[source].append(article)
                    total += 1

    if not par_source:
        return documents

    ajoutes: list[dict] = []
    for source, articles in par_source.items():
        try:
            resultat = (
                _supabase.table("documents")
                .select("id, content, metadata")
                .eq("metadata->>source", source)
                .in_("metadata->>article", articles)
                .neq("metadata->>statut", "abroge")
                .eq("metadata->>type_bloc", "article")
                .execute()
            )
        except Exception as exc:
            _logger.warning(
                "Échec expansion references_articles pour %r / %r : %s",
                source,
                articles,
                exc,
            )
            continue

        lignes_applicables = _selectionner_versions_applicables(
            resultat.data or []
        )
        for ligne in lignes_applicables:
            meta = ligne.get("metadata") or {}
            cle = (meta.get("source"), meta.get("article"))
            if cle in existants:
                continue
            existants.add(cle)
            # Les lookups table n'ont pas de score vectoriel : score neutre.
            ligne["similarity"] = None
            ajoutes.append(ligne)

    if ajoutes:
        _logger.info(
            "Expansion références explicites : %d document(s) ajouté(s).",
            len(ajoutes),
        )

    return documents + ajoutes


def _texte_article(a: dict) -> str:
    """Texte intégral de l'article (sans le préfixe '{article}.- ', déjà
    affiché séparément dans la puce et l'en-tête de la modale)."""
    article = a["metadata"].get("article", "")
    contenu = a["content"]
    prefixe = f"{article}.-"
    if contenu.startswith(prefixe):
        return contenu[len(prefixe):].strip()
    return contenu.strip()


def _construire_sources(articles: list[dict]) -> list[dict]:
    """Regroupe les morceaux d'une MÊME version d'article.

    La clé inclut document_id et version_numero : deux versions juridiques
    successives ne sont jamais concaténées accidentellement.
    """
    sources: list[dict] = []
    index: dict[tuple[str, str, int], dict] = {}
    for a in articles:
        meta = a["metadata"]
        article = meta.get("article", "?")
        source = meta.get("source", "?")
        document_id = str(meta.get("document_id") or source)
        version_numero = _numero_version(meta)
        cle = (document_id, article, version_numero)
        texte = _texte_article(a)
        if cle in index:
            index[cle]["texte"] += "\n\n" + texte
        else:
            entree = {
                "article": article,
                "source": source,
                "source_courte": meta.get("source_courte"),
                "document_id": meta.get("document_id"),
                "chunk_id": meta.get("chunk_id"),
                "version_numero": version_numero,
                "version_consolidee": meta.get("version_consolidee", False),
                "date_debut_effet": meta.get("date_debut_effet"),
                "date_fin_effet": meta.get("date_fin_effet"),
                "chemin_hierarchique": meta.get("chemin_hierarchique"),
                "date": meta.get("date"),
                "date_publication": meta.get("date_publication"),
                "statut": meta.get("statut"),
                "abroge_par": meta.get("abroge_par"),
                "publication_abrogation": meta.get("publication_abrogation"),
                "date_abrogation": meta.get("date_abrogation"),
                "texte": texte,
            }
            index[cle] = entree
            sources.append(entree)
    return sources


def _etiquette_citation(article: str, libelle: str) -> str:
    """Étiquette stable et sans ambiguïté pour l'appariement citation ↔ puce.
    `libelle` doit être calculé avec libelle_source() à partir des MÊMES
    champs metadata (source/source_courte) des deux côtés — construction du
    contexte (poser_question, lookup_article) et filtrage
    (_filtrer_sources_citees) — sinon l'intersection anti-hallucination ne
    matche plus rien."""
    return f"[SOURCE: {article} — {libelle}]"


def _filtrer_sources_citees(sources: list[dict], articles_cites: list[str]) -> list[dict]:
    """Ne conserve, parmi les sources réellement récupérées, que celles dont
    l'étiquette [SOURCE: ...] figure dans articles_cites (intersection
    anti-hallucination). Ordre retenu : ordre d'apparition dans
    articles_cites, c'est-à-dire l'ordre dans lequel le LLM a cité les
    articles — plus utile pour l'utilisateur que l'ordre brut de pertinence
    du retriever."""
    index = {_etiquette_citation(s["article"], libelle_source(s)): s for s in sources}
    vues: set[str] = set()
    resultat: list[dict] = []
    for etiquette in articles_cites:
        cle = etiquette.strip()
        if cle in index and cle not in vues:
            resultat.append(index[cle])
            vues.add(cle)
    return resultat


_RE_LIGNE_SOURCE = re.compile(r"^[\s*_>•\-\d.)]*\[SOURCE:.*\]\s*$", re.IGNORECASE)
_RE_TITRE_CITATIONS = re.compile(
    r"^[\s*_>#]*(articles?|sources?)\s+cit[ée]e?s?\s*:?[\s*_]*$", re.IGNORECASE
)


def _nettoyer_reponse_visible(texte: str) -> str:
    """Retire du texte visible toute ligne contenant une balise [SOURCE: ...],
    quel que soit son habillage (puce, gras, indentation), ainsi qu'un titre
    orphelin (ex. « Articles cités ») qui précéderait immédiatement ces
    lignes. N'affecte jamais `sources` : ce champ est construit à partir de
    articles_cites et des documents récupérés (_construire_sources,
    _filtrer_sources_citees), jamais en lisant reponse_texte."""
    gardees: list[str] = []
    for ligne in texte.split("\n"):
        if _RE_LIGNE_SOURCE.match(ligne):
            while gardees and not gardees[-1].strip():
                gardees.pop()
            if gardees and _RE_TITRE_CITATIONS.match(gardees[-1]):
                gardees.pop()
            continue
        gardees.append(ligne)
    return "\n".join(gardees).rstrip()


def _etiquette(meta: dict) -> str:
    """Identique à halex_core.py."""
    source = meta.get("source", "Source inconnue")
    statut = meta.get("statut", "")
    date   = meta.get("date", "")
    date_publication = meta.get("date_publication", "")
    abroge_par = meta.get("abroge_par")
    publication_abrogation = meta.get("publication_abrogation")
    date_abrogation = meta.get("date_abrogation")
    article_modifie_par = meta.get("article_modifie_par")
    article_date_modification = meta.get("article_date_modification")
    article_publication_modification = meta.get("article_publication_modification")
    version_numero = _numero_version(meta)
    version_consolidee = meta.get("version_consolidee") is True
    date_debut_effet = meta.get("date_debut_effet")
    date_fin_effet = meta.get("date_fin_effet")

    parties = [source, libelle_type_norme(meta.get("type_norme", ""))]
    if statut:
        libelle = libelle_statut(statut)
        details_abrogation = []
        if statut == "abroge":
            if isinstance(abroge_par, str) and abroge_par.strip():
                details_abrogation.append(abroge_par.strip())
            if (
                isinstance(publication_abrogation, str)
                and publication_abrogation.strip()
            ):
                details_abrogation.append(
                    f"publication : {publication_abrogation.strip()}"
                )
            if isinstance(date_abrogation, str) and date_abrogation.strip():
                details_abrogation.append(
                    f"date d’abrogation : {date_abrogation.strip()}"
                )
        elif statut == "modifie":
            for valeur, prefixe in (
                (article_modifie_par, "par"),
                (article_date_modification, "date de modification :"),
                (article_publication_modification, "publication :"),
            ):
                if isinstance(valeur, str) and valeur.strip():
                    details_abrogation.append(f"{prefixe} {valeur.strip()}")
        if details_abrogation:
            libelle += " (" + " ; ".join(details_abrogation) + ")"
        parties.append(libelle)
    if version_numero > 1 or version_consolidee:
        libelle_version = f"version {version_numero}"
        if version_consolidee:
            libelle_version += " consolidée"
        parties.append(libelle_version)
    if isinstance(date_debut_effet, str) and date_debut_effet:
        if isinstance(date_fin_effet, str) and date_fin_effet:
            parties.append(
                f"applicable du {date_debut_effet} au {date_fin_effet}"
            )
        else:
            parties.append(f"applicable depuis le {date_debut_effet}")
    if meta.get("historique"):
        parties.append("texte historique")
    if date and not date.startswith("XXXX"):
        parties.append(date)
    if date_publication and date_publication != date:
        parties.append(f"publication : {date_publication}")
    if meta.get("moniteur_publication"):
        parties.append(meta["moniteur_publication"])
    return "[" + " — ".join(str(p) for p in parties) + "]"


# --- Prompts : copies exactes de halex_core.py ---

_prompt = ChatPromptTemplate.from_template(
    """AVANT TOUTE CHOSE, vérifie : la question posée peut-elle être réellement
résolue par les textes fournis ci-dessous ? Une simple proximité de mots ne
suffit pas. Si la réponse est non, ta réponse entière doit être exactement :
[HORS_DOMAINE]
Rien d'autre.

Tu es Halex, un assistant juridique spécialisé dans le droit haïtien.
Tu expliques uniquement les textes fournis ; tu n'ajoutes pas de droit externe.

RELATIONS EXPLICITES DE MODIFICATION / ABROGATION DÉJÀ ENRICHIES :
{bloc_modifications}

ANALYSE NORMATIVE CALCULÉE AVANT RÉDACTION :
{bloc_normatif}

RÈGLES STRICTES :
1. Réponds UNIQUEMENT à partir des ARTICLES DISPONIBLES ci-dessous.
2. L'analyse normative ci-dessus est CONTRAIGNANTE pour la rédaction.
   Tu ne peux pas inverser une priorité déjà calculée ni inventer une nouvelle
   contradiction.
3. Les relations explicites de modification/abrogation priment sur une simple
   ressemblance sémantique.
4. Utilise d'abord tous les documents marqués rôle=principal.
5. Utilise les documents rôle=complementaire lorsqu'ils ajoutent une condition,
   exception, conséquence, peine ou régime distinct nécessaire.
6. Ne fusionne jamais deux régimes distincts en une seule règle. Présente-les
   séparément s'ils sont complémentaires.
7. Un texte `abroge` ou `adopte_non_applique` ne fonde pas l'état courant du
   droit. Il peut seulement être signalé si l'analyse normative le demande.
8. Si un conflit est marqué NON RÉSOLU, indique clairement qu'une tension
   subsiste. Ne choisis pas toi-même un gagnant.
9. `date_publication` est documentaire : ne l'utilise jamais pour décider quel
   texte prévaut.
10. Cite toujours le numéro d'article ET le texte source.
11. Ne donne pas de conseil juridique personnalisé : explique ce que disent les
    textes.
12. Dans `articles_cites`, liste UNIQUEMENT les étiquettes [SOURCE: ...] des
    articles réellement utilisés dans la réponse. Recopie-les EXACTEMENT.
13. Si tu mentionnes des étiquettes [SOURCE: ...] dans `reponse`, elles doivent
    apparaître uniquement à la toute fin, une par ligne. Le frontend les
    retirera du texte visible.
14. Si un article est seulement marqué `contexte`, ne le force pas dans la
    réponse s'il n'est pas nécessaire.

COMMENT LIRE CHAQUE ARTICLE :
- [SOURCE: ...] = identifiant stable à recopier dans `articles_cites`.
- la deuxième étiquette décrit source, type de norme, statut et dates.
- les métadonnées et l'analyse normative servent à distinguer les rôles des
  textes ; le texte intégral reste la base du contenu juridique.

ARTICLES DISPONIBLES :
{contexte}

QUESTION :
{question}

STYLE :
{instructions_mode}

RÉPONSE :
"""
)


_prompt_reformulation = ChatPromptTemplate.from_template(
    """Reformule la requête suivante en UNE seule question claire et complète,
en français, portant sur le droit haïtien ({libelles_corpus}).
Ne réponds PAS à la question. Renvoie UNIQUEMENT la question reformulée,
sans guillemets ni préambule.

Requête de l'utilisateur : {requete}

Question reformulée :"""
)


def reformuler(requete: str) -> str:
    return _llm.invoke(
        _prompt_reformulation.format(requete=requete, libelles_corpus=_libelles_corpus_texte())
    ).content.strip()


def _reponse_hors_domaine(methode: str = "vectorielle") -> dict:
    return {
        "reponse": (
            "Cette question semble sortir du domaine actuellement couvert par "
            f"Halex ({_libelles_corpus_texte()}). "
            "Je ne peux pas y répondre de façon fiable. Pour votre situation, "
            "consultez un professionnel du droit ou l'autorité compétente."
        ),
        "sources": [],
        "hors_domaine": True,
        "demande_precision": False,
        "type": "reponse",
        "methode": methode,
    }


# --- Salutations ---


def detecter_salutation(question: str) -> bool:
    """True si la question n'est composée QUE de mots de salutation/politesse
    (après normalisation : minuscules, ponctuation retirée). Une question
    vide ne compte pas comme salutation."""
    normalise = re.sub(r"[^\w\s-]", "", question.lower(), flags=re.UNICODE)
    tokens = normalise.split()
    if not tokens:
        return False
    return all(token in SALUTATIONS for token in tokens)


# --- Détection de référence directe à un article ---

_RE_ARTICLE = re.compile(
    r"(?:\barticles?\b|\bart\.?\b|\batik\b)\s*(\d+(?:[.-]\d+)*)",
    re.IGNORECASE,
)
_RE_PREAMBULE = re.compile(r"\b(?:pr[ée]ambule|preyanbil)\b", re.IGNORECASE)


_cache_mapping_mots_cles: dict[str, str] | None = None


def _construire_sources_corpus() -> dict[str, str]:
    """Mot-clé -> valeur exacte de metadata->>'source', construit depuis le
    corpus réel (mots_cles + source_courte de chaque document, minuscules,
    NFC). Chaque élément de mots_cles est utilisé tel quel comme clé, jamais
    découpé par espaces (permet des expressions à mots multiples, ex.
    "loi constitutionnelle"). Trié par longueur de clé décroissante : le
    mot-clé le plus spécifique gagne — remplace l'ordre manuel de l'ancien
    SOURCES_CORPUS, qui testait "amendement" avant "constitution".
    Mis en cache au niveau du module ; invalidé par invalider_caches()."""
    global _cache_mapping_mots_cles
    if _cache_mapping_mots_cles is not None:
        return _cache_mapping_mots_cles

    resultat = (
        _supabase.table("documents")
        .select("metadata->>source, metadata->>source_courte, metadata->mots_cles")
        .execute()
    )

    paires: dict[str, str] = {}
    for ligne in resultat.data:
        source = ligne.get("source")
        if not source:
            continue
        candidats = list(ligne.get("mots_cles") or [])
        source_courte = ligne.get("source_courte")
        if source_courte:
            candidats.append(source_courte)
        for mot in candidats:
            if isinstance(mot, str) and mot.strip():
                cle = unicodedata.normalize("NFC", mot.strip().lower())
                paires[cle] = source

    _cache_mapping_mots_cles = dict(
        sorted(paires.items(), key=lambda item: len(item[0]), reverse=True)
    )
    return _cache_mapping_mots_cles


_cache_libelles_corpus: str | None = None


def _libelles_corpus_texte() -> str:
    """Phrase française listant les libellés (libelle_source) des sources
    distinctes du corpus réel, ex. "Constitution de 1987 Amendée et Code
    pénal". Texte neutre si le corpus est vide (table documents non encore
    peuplée). Mis en cache au niveau du module ; invalidé par
    invalider_caches()."""
    global _cache_libelles_corpus
    if _cache_libelles_corpus is not None:
        return _cache_libelles_corpus

    resultat = (
        _supabase.table("documents")
        .select("metadata->>source, metadata->>source_courte")
        .execute()
    )
    libelles = sorted({
        libelle_source({"source": ligne["source"], "source_courte": ligne.get("source_courte")})
        for ligne in resultat.data
        if ligne.get("source")
    })

    if not libelles:
        texte = "les textes actuellement couverts par Halex"
    elif len(libelles) == 1:
        texte = libelles[0]
    else:
        texte = ", ".join(libelles[:-1]) + " et " + libelles[-1]

    _cache_libelles_corpus = texte
    return _cache_libelles_corpus


def invalider_caches() -> None:
    """Invalide les caches module-level construits depuis le corpus (mapping
    mots-clés, libellés). À appeler après toute ingestion réussie pour que
    le prochain appel relise le corpus à jour plutôt que de servir des
    valeurs pré-ingestion."""
    global _cache_mapping_mots_cles, _cache_libelles_corpus
    _cache_mapping_mots_cles = None
    _cache_libelles_corpus = None
    invalider_cache_registre()


def _detecter_source_corpus(question_minuscule: str) -> str | None:
    """Première source du mapping construit par _construire_sources_corpus()
    dont le mot-clé apparaît dans la question (déjà en minuscules). La
    question est normalisée en NFC, symétriquement à la normalisation NFC
    appliquée aux fichiers de chunks à l'ingestion (_lire_et_parser_fichier
    dans ingestion_admin.py) — sans cette symétrie, un mot-clé et une
    question visuellement identiques mais en formes Unicode différentes ne
    matcheraient pas. Respecte l'ordre d'itération du dict (longueur
    décroissante)."""
    question_normalisee = unicodedata.normalize("NFC", question_minuscule)
    for mot_cle, source in _construire_sources_corpus().items():
        if mot_cle in question_normalisee:
            return source
    return None


def detecter_reference_article(question: str) -> dict | None:
    """Détecte une référence directe à un article (« article 4 », « art. 12 »,
    « atik 3 ») ou au préambule seul, avec la source visée si elle est
    nommée dans la question. Analyse de texte pure, aucun appel réseau."""
    question_min = question.lower()
    source = _detecter_source_corpus(question_min)

    match = _RE_ARTICLE.search(question)
    if match:
        return {"preambule": False, "numero": match.group(1), "source": source}

    if _RE_PREAMBULE.search(question):
        return {"preambule": True, "numero": None, "source": source}

    return None


# --- Lookup direct d'article (sans recherche vectorielle) ---


def lookup_article(numero: str | None, source: str | None, preambule: bool = False) -> dict:
    """Requête directe (PAS match_documents) d'un article par son numéro
    (et éventuellement sa source), pour répondre exactement et sans coût de
    recherche vectorielle aux questions du type « article 4 » / « atik 12 »."""
    valeur_article = "Préambule" if preambule else f"Article {numero}"
    valeurs_article = [valeur_article]
    if not preambule and str(numero) == "1":
        valeurs_article.append("Article 1er")

    requete = (
        _supabase.table("documents")
        .select("content, metadata")
        .in_("metadata->>article", valeurs_article)
    )
    if source:
        requete = requete.eq("metadata->>source", source)
    chunks_tous = requete.execute().data or []

    if not chunks_tous:
        return {
            "reponse": (
                f"{valeur_article} n'existe pas dans les textes actuellement "
                f"couverts par Halex ({_libelles_corpus_texte()})."
            ),
            "sources": [],
            "hors_domaine": True,
            "demande_precision": False,
            "type": "reponse",
            "methode": "lookup_direct",
        }

    chunks_applicables = _selectionner_versions_applicables(chunks_tous)
    chunks = (
        chunks_applicables
        if chunks_applicables
        else _selectionner_derniere_version(chunks_tous)
    )

    sources_trouvees = sorted({c["metadata"].get("source", "?") for c in chunks})

    if len(sources_trouvees) > 1:
        sujet = f"L'article {numero}" if numero else "Le préambule"
        return {
            "reponse": (
                f"{sujet} existe dans plusieurs documents de la législation "
                "haïtienne. Lequel vous intéresse ?"
            ),
            "sources": [],
            "hors_domaine": False,
            "demande_precision": True,
            "type": "clarification",
            "methode": "lookup_direct",
            "options": sources_trouvees,
            "autre_autorise": True,
            "contexte_clarification": {"type_lookup": "article", "numero": numero},
        }

    # Une version consolidée matérialisée est déjà le texte applicable :
    # on ne demande plus au LLM de recomposer l'ancien article et son acte
    # modificatif. L'enrichissement historique reste un filet de compatibilité
    # pour les anciens chunks `modifie` non consolidés.
    if _necessite_enrichissement_modifications(chunks):
        chunks, relations = enrichir_modifications(_supabase, chunks)
        _, registre_par_id = charger_registre(_supabase)
    else:
        relations = []
        registre_par_id = {}

    toutes_sources = _construire_sources(chunks)
    contexte = "\n\n".join(
        f"{_etiquette_citation(s['article'], libelle_source(s))}\n{s['texte']}"
        for s in toutes_sources
    )

    if relations:
        # Cette branche n'est PAS une simple restitution : le texte demandé
        # a été modifié. Restituer l'article seul serait donner au citoyen
        # un état du droit périmé.
        prompt_final = (
            formater_bloc_prompt(relations, registre_par_id)
            + "\nRestitue le texte de l'article demandé, puis la "
            "modification qui lui a été apportée. Ne résume pas : les deux "
            "textes doivent apparaître intégralement, dans cet ordre.\n\n"
            f"TEXTES :\n{contexte}\n\n"
            f"DEMANDE : {valeur_article}"
        )
    else:
        # lookup_article contourne match_documents : le filtre statut de la
        # Phase 3 ne s'applique pas ici. Restituer un article abrogé sans le
        # dire donnerait au citoyen un état du droit périmé.
        est_abroge = any(c["metadata"].get("statut") == "abroge" for c in chunks)
        textes_abrogation = sorted({
            valeur.strip()
            for c in chunks
            if isinstance((valeur := c["metadata"].get("abroge_par")), str)
            and valeur.strip()
        })
        publications_abrogation = sorted({
            valeur.strip()
            for c in chunks
            if isinstance(
                (valeur := c["metadata"].get("publication_abrogation")), str
            )
            and valeur.strip()
        })
        dates_abrogation = sorted({
            valeur.strip()
            for c in chunks
            if isinstance((valeur := c["metadata"].get("date_abrogation")), str)
            and valeur.strip()
        })
        indications_abrogation = (
            textes_abrogation
            + [f"publication : {v}" for v in publications_abrogation]
            + [f"date d’abrogation : {v}" for v in dates_abrogation]
        )
        detail_abrogation = (
            " Indications enregistrées : "
            + " ; ".join(indications_abrogation)
            + "."
            if indications_abrogation
            else ""
        )
        avertissement = (
            "AVERTISSEMENT OBLIGATOIRE : ce texte est ABROGÉ."
            + detail_abrogation
            + " Commence ta "
            "réponse par une phrase indiquant clairement qu'il n'est plus en "
            "vigueur, puis restitue son texte.\n\n"
            if est_abroge else ""
        )
        prompt_final = (
            avertissement
            + "Restitue fidèlement le texte de l'article suivant, en citant "
            "clairement son numéro d'article et sa source. Ne reformule pas le "
            "fond et ne résume pas : restitue le texte intégral fourni.\n\n"
            f"ARTICLE(S) :\n{contexte}\n\n"
            f"DEMANDE : {valeur_article}"
        )
    reponse_texte = _llm.invoke(prompt_final).content

    return {
        "reponse": reponse_texte,
        "sources": toutes_sources,
        "hors_domaine": False,
        "demande_precision": False,
        "type": "reponse",
        "methode": "lookup_direct",
    }


# --- Suggestion de questions pour une requête à un seul mot ---

def _prompt_systeme_suggestion_mot(mot: str) -> str:
    return (
        f'Tu vérifies d\'abord si ces extraits juridiques traitent réellement '
        f'de "{mot}". S\'ils n\'en traitent pas directement (simple proximité '
        'de thème sans lien juridique réel), réponds '
        '{"pertinent": false, "questions": []}. S\'ils en traitent, réponds '
        '{"pertinent": true, "questions": [...]} avec exactement 2 questions '
        f'juridiques courtes et naturelles qu\'un citoyen pourrait poser sur '
        f'"{mot}", strictement répondables à partir de ces extraits. '
        'Réponds UNIQUEMENT en JSON valide, exactement au format : '
        '{"pertinent": true, "questions": ["...", "..."]} ou '
        '{"pertinent": false, "questions": []}.'
    )


_MESSAGE_CLARIFICATION_MOT_COURT = {
    "fr": (
        "Votre message est un peu court pour que je réponde avec précision. "
        "Voici deux questions que vous vouliez peut-être poser :"
    ),
    "ht": (
        "Mesaj ou a yon ti jan kout pou m ka reponn avèk presizyon. Men de "
        "kesyon ou ta ka vle poze :"
    ),
}


def suggerer_questions_mot(mot: str, lang: str = "fr") -> dict:
    """Remplace l'ancien message générique pour une requête à un seul mot :
    propose 2 questions concrètes dérivées des chunks les plus proches,
    plutôt que de simplement demander de reformuler."""
    question_enrichie = reformuler(mot)
    resultats = _chercher(question_enrichie, k=3)
    meilleure_similarite = resultats[0]["similarity"] if resultats else 0.0

    if not resultats or meilleure_similarite < SEUIL_SIM_SECONDE_CHANCE:
        return _reponse_hors_domaine(methode="suggestion_mot")

    contexte = "\n\n".join(r["content"] for r in resultats)
    message_utilisateur = f"Mot : {mot}\nExtraits :\n{contexte}"

    try:
        reponse = _llm_json.invoke(
            [
                {"role": "system", "content": _prompt_systeme_suggestion_mot(mot)},
                {"role": "user", "content": message_utilisateur},
            ]
        )
        donnees = json.loads(reponse.content)
        pertinent = donnees["pertinent"]
        questions = donnees["questions"]
        questions_valides = [
            q for q in questions if isinstance(q, str) and q.strip()
        ]

        if not pertinent or len(questions_valides) != 2:
            return _reponse_hors_domaine(methode="suggestion_mot")

        return {
            "reponse": _MESSAGE_CLARIFICATION_MOT_COURT.get(
                lang, _MESSAGE_CLARIFICATION_MOT_COURT["fr"]
            ),
            "sources": [],
            "hors_domaine": False,
            "demande_precision": True,
            "type": "clarification",
            "methode": "suggestion_mot",
            "options": questions,
            "autre_autorise": True,
            "contexte_clarification": None,
        }
    except Exception as exc:
        _logger.warning("Echec suggestion_mot pour %r : %s", mot, exc)
        _logger.warning(
            "Échec génération de suggestions pour le mot %r ; repli sur message générique.",
            mot,
        )
        return {
            "reponse": (
                "Votre demande est très courte et je préfère ne pas deviner. "
                "Pouvez-vous la formuler en une question complète ? "
                "Par exemple : « Quelle est la devise nationale d'Haïti ? » "
                "ou « Que dit le Code pénal sur le vol ? »"
            ),
            "sources": [],
            "hors_domaine": False,
            "demande_precision": True,
            "type": "reponse",
            "methode": "suggestion_mot",
        }


def poser_question(
    question: str,
    mode: str = MODE_PAR_DEFAUT,
    historique: list[dict] | None = None,
) -> dict:
    """Point d'entrée RAG avec résolution conversationnelle.

    Ordre :
      1. salutation ;
      2. référence directe explicite dans la question originale ;
      3. contextualisation linguistique -> question autonome ;
      4. clarification si référent ambigu ;
      5. nouvelle détection de référence directe après contextualisation ;
      6. mot unique / retrieval vectoriel ;
      7. références explicites / modifications ;
      8. moteur normatif ;
      9. rédaction LLM.

    L'historique ne fonde JAMAIS la réponse juridique. Il sert seulement à
    produire `question_autonome`, qui est ensuite traitée comme une nouvelle
    requête indépendante.
    """

    question_originale = " ".join(question.split()).strip()
    instructions_mode = INSTRUCTIONS_MODES.get(
        mode, INSTRUCTIONS_MODES[MODE_PAR_DEFAUT]
    )

    if detecter_salutation(question_originale):
        return {
            "reponse": (
                "Bonjour ! Je suis Halex, votre assistant sur le droit "
                "haïtien. Posez-moi une question sur la loi — par exemple "
                "sur la Constitution ou le Code pénal."
            ),
            "sources": [],
            "hors_domaine": False,
            "demande_precision": False,
            "type": "reponse",
            "methode": "salutation",
        }

    # Une référence explicite ("article 38", "préambule") doit gagner sur tout
    # l'historique. Elle reste autonome même après une longue conversation.
    reference = detecter_reference_article(question_originale)
    if reference is not None:
        return lookup_article(
            reference["numero"],
            reference["source"],
            preambule=reference["preambule"],
        )

    resolution = resoudre_question_conversationnelle(
        question_originale,
        historique,
        _llm,
    )

    _logger.info(
        "Résolution conversationnelle: depend=%s ambigu=%s confiance=%s "
        "originale=%r autonome=%r",
        resolution.depend_historique,
        resolution.ambigu,
        resolution.confiance,
        question_originale,
        resolution.question_autonome,
    )

    if resolution.ambigu:
        return {
            "reponse": resolution.question_clarification
            or "Pouvez-vous préciser votre question ?",
            "sources": [],
            "hors_domaine": False,
            "demande_precision": True,
            "type": "clarification",
            "methode": "clarification_conversationnelle",
            "options": [],
            "autre_autorise": True,
            "contexte_clarification": {
                "type_lookup": "conversation",
                "question_originale": question_originale,
            },
        }

    question_autonome = resolution.question_autonome.strip() or question_originale

    # La contextualisation peut résoudre "Et le précédent ?" en une référence
    # explicite. On bénéficie alors du lookup direct au lieu du vectoriel.
    reference = detecter_reference_article(question_autonome)
    if reference is not None:
        resultat = lookup_article(
            reference["numero"],
            reference["source"],
            preambule=reference["preambule"],
        )
        resultat["methode_conversationnelle"] = (
            "contextualisee" if resolution.depend_historique else "autonome"
        )
        return resultat

    if len(question_autonome.split()) == 1:
        return suggerer_questions_mot(question_autonome.split()[0])

    question_recherche = question_autonome

    # ① Le seuil de domaine porte désormais sur la QUESTION AUTONOME.
    # Une ellipse conversationnelle ne doit jamais être vectorisée telle quelle.
    meilleur = _chercher(question_autonome, k=1)
    sim_originale = meilleur[0]["similarity"] if meilleur else 0.0

    if sim_originale < SEUIL_SIM:
        # ② Seconde chance uniquement pour les requêtes autonomes encore très
        # courtes. La reformulation n'a plus à deviner le contexte : celui-ci
        # a déjà été résolu en amont.
        if len(question_autonome.split()) < 5:
            question_reformulee = reformuler(question_autonome)
            resultat_reformule = _chercher(question_reformulee, k=1)
            sim_reformulee = (
                resultat_reformule[0]["similarity"]
                if resultat_reformule
                else 0.0
            )
            if sim_reformulee < SEUIL_SIM_SECONDE_CHANCE:
                return _reponse_hors_domaine(
                    methode="vectorielle_contextualisee"
                    if resolution.depend_historique
                    else "vectorielle"
                )
            question_recherche = question_reformulee
        else:
            return _reponse_hors_domaine(
                methode="vectorielle_contextualisee"
                if resolution.depend_historique
                else "vectorielle"
            )
    elif len(question_autonome.split()) < 5:
        question_recherche = reformuler(question_autonome)

    # ③ Recherche élargie.
    articles = _chercher(question_recherche, k=6)

    # ③bis Expansion des références juridiques explicites encodées dans les
    # métadonnées (ex. un article qui renvoie expressément à l'article 84).
    articles = _enrichir_references_articles(articles)

    # ③ter Enrichissement de compatibilité. Les versions consolidées
    # matérialisées n'ont plus besoin d'être recomposées par le LLM.
    if _necessite_enrichissement_modifications(articles):
        articles, relations = enrichir_modifications(_supabase, articles)
        _, registre_par_id = charger_registre(_supabase)
        bloc_modifications = formater_bloc_prompt(relations, registre_par_id)
    else:
        relations = []
        bloc_modifications = "(aucune relation supplémentaire à recomposer)"

    # ④ Phase 3 : qualification sémantique + résolution normative
    # déterministe. Le qualificateur peut dire "complémentaire",
    # "contradiction", "spécialité", etc., mais il ne choisit jamais la norme
    # gagnante. Ce choix est fait dans moteur_normatif.py.
    analyse_normative = analyser_normativement(
        question_autonome,
        articles,
        _llm,
    )
    articles = analyse_normative["documents"]
    bloc_normatif = analyse_normative["bloc_prompt"]

    contexte = "\n\n".join(
        f"{_etiquette_citation(a['metadata'].get('article', '?'), libelle_source(a['metadata']))}\n"
        f"{_etiquette(a['metadata'])} {a['metadata'].get('article', '')}\n{a['content']}"
        for a in articles
    )

    # Le LLM reçoit la question AUTONOME et l'analyse normative, mais jamais
    # l'historique brut.
    prompt_final = _prompt.format(
        contexte=contexte,
        question=question_autonome,
        instructions_mode=instructions_mode,
        bloc_modifications=bloc_modifications,
        bloc_normatif=bloc_normatif,
    )

    echec_technique = False
    try:
        resultat = _llm_structure.invoke(prompt_final)
        reponse_texte = resultat.reponse
        articles_cites = resultat.articles_cites
    except Exception:
        _logger.warning(
            "Sortie structurée invalide pour la question autonome %r ; "
            "repli sur réponse brute.",
            question_autonome,
        )
        reponse_texte = _llm.invoke(prompt_final).content
        articles_cites = []
        echec_technique = True

    if "[HORS_DOMAINE]" in reponse_texte:
        return _reponse_hors_domaine(
            methode="vectorielle_contextualisee"
            if resolution.depend_historique
            else "vectorielle"
        )

    reponse_texte = _nettoyer_reponse_visible(reponse_texte)

    toutes_sources = _construire_sources(articles)
    sources_citees = _filtrer_sources_citees(toutes_sources, articles_cites)

    if not sources_citees and toutes_sources and (
        echec_technique or articles_cites
    ):
        _logger.warning(
            "Signal de citation incohérent (articles_cites=%r) pour la "
            "question autonome %r ; repli top-1.",
            articles_cites,
            question_autonome,
        )
        sources_citees = toutes_sources[:1]

    reponse = {
        "reponse": reponse_texte,
        "sources": sources_citees,
        "hors_domaine": False,
        "demande_precision": False,
        "type": "reponse",
        "methode": (
            "vectorielle_contextualisee"
            if resolution.depend_historique
            else "vectorielle"
        ),
    }

    # Trace légère, utile au frontend/logs pour diagnostiquer le retrieval.
    # Aucun historique complet n'est renvoyé.
    reponse["conversation"] = {
        "depend_historique": resolution.depend_historique,
        "question_originale": question_originale,
        "question_autonome": question_autonome,
        "confiance": resolution.confiance,
    }
    reponse["normatif"] = analyse_normative["diagnostic"]
    return reponse


# --- Article du jour : sélection déterministe par jour calendaire, sans cron ---


def tronquer(texte: str, limite: int = 200) -> str:
    """Coupe au dernier espace avant la limite (jamais en plein mot) et
    ajoute une ellipse. Renvoie le texte tel quel s'il tient déjà dans la
    limite."""
    if len(texte) <= limite:
        return texte
    coupe = texte[:limite]
    dernier_espace = coupe.rfind(" ")
    if dernier_espace != -1:
        coupe = coupe[:dernier_espace]
    return coupe.rstrip(" ,;:.") + "…"


_PROMPT_SYSTEME_ARTICLE_DU_JOUR = (
    "Explique cet article en langage simple, uniquement à partir du texte "
    "fourni, sans ajouter de contenu juridique externe. Réponds en JSON : "
    '{"explication_fr": "...", "explication_ht": "...", "tags": ["...", "...", "..."]}'
)


def _generer_explication_article(article: str, source: str, texte: str) -> dict:
    """Un seul appel LLM : explication FR + HT + tags, à partir du texte
    de l'article uniquement (mode JSON forcé, pas de parsing fragile)."""
    message_utilisateur = f"Article : {article}\nSource : {source}\nTexte :\n{texte}"
    reponse = _llm_json.invoke(
        [
            {"role": "system", "content": _PROMPT_SYSTEME_ARTICLE_DU_JOUR},
            {"role": "user", "content": message_utilisateur},
        ]
    )
    return json.loads(reponse.content)


def article_du_jour() -> dict:
    """Article vedette du jour calendaire courant, identique pour tous les
    utilisateurs. Le jour détermine à la fois quel article est choisi
    (offset déterministe) et si le cache est encore valide : pas de cron,
    juste une lecture/écriture paresseuse dans article_du_jour_cache."""
    tranche = date.today().toordinal()

    cache = (
        _supabase.table("article_du_jour_cache")
        .select("titre, extrait, texte_complet, explication_fr, explication_ht, tags")
        .eq("tranche", tranche)
        .execute()
    )
    if cache.data:
        return cache.data[0]

    aujourd_hui = date.today().isoformat()
    total = (
        _supabase.table("documents")
        .select("id", count="exact")
        .like("content", "Article%")
        .in_("metadata->>statut", list(STATUTS_APPLICABLES))
        .is_("metadata->>date_fin_effet", "null")
        .lte("metadata->>date_debut_effet", aujourd_hui)
        .execute()
    )
    if not total.count:
        return {
            "indisponible": True,
            "message": "Aucun article disponible pour le moment.",
        }
    offset = tranche % total.count

    resultat = (
        _supabase.table("documents")
        .select("id, content, metadata")
        .like("content", "Article%")
        .in_("metadata->>statut", list(STATUTS_APPLICABLES))
        .is_("metadata->>date_fin_effet", "null")
        .lte("metadata->>date_debut_effet", aujourd_hui)
        .order("id")
        .range(offset, offset)
        .execute()
    )
    if not resultat.data:
        # Ne devrait jamais arriver : les filtres de comptage et de sélection
        # sont identiques. Si cela se produit, ils ont divergé.
        return {
            "indisponible": True,
            "message": "Aucun article disponible pour le moment.",
        }
    doc = resultat.data[0]
    article = doc["metadata"].get("article", "?")
    source = doc["metadata"].get("source", "?")
    contenu = doc["content"]

    genere = _generer_explication_article(article, source, contenu)

    ligne = {
        "tranche": tranche,
        "document_id": doc["id"],
        "titre": f"{source} — {article}",
        "extrait": tronquer(contenu),
        "texte_complet": contenu,
        "explication_fr": genere["explication_fr"],
        "explication_ht": genere["explication_ht"],
        "tags": genere.get("tags", []),
    }
    _supabase.table("article_du_jour_cache").insert(ligne).execute()

    return {
        "titre": ligne["titre"],
        "extrait": ligne["extrait"],
        "texte_complet": ligne["texte_complet"],
        "explication_fr": ligne["explication_fr"],
        "explication_ht": ligne["explication_ht"],
        "tags": ligne["tags"],
    }


def archives_article_du_jour(limite: int = 30) -> list[dict]:
    """Historique des articles du jour déjà générés, du plus récent au plus
    ancien (lecture seule du cache, aucun nouvel appel LLM)."""
    resultat = (
        _supabase.table("article_du_jour_cache")
        .select("titre, extrait, texte_complet, explication_fr, explication_ht, tags, created_at, tranche")
        .order("created_at", desc=True)
        .limit(limite)
        .execute()
    )
    return resultat.data