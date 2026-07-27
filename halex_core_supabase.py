"""
halex_core_supabase.py
Jumeau de halex_core.py : même logique, même prompt, mêmes garde-fous.
Seul le moteur de recherche change : Supabase pgvector au lieu de FAISS.
Seuils convertis mathématiquement (similarité = 1 - distance/2).
"""

import json
import logging
import os
import re
from datetime import date
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from supabase import create_client

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

# Seuils de similarité pgvector (embeddings normalisés) : sim = 1 - distance/2.
#   distance 1.25  ->  similarité 0.375
#   distance 0.9   ->  similarité 0.55
SEUIL_SIM = 0.375
SEUIL_SIM_SECONDE_CHANCE = 0.55

MODE_PAR_DEFAUT = "citoyen"

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

# Mots-clés -> valeur exacte de metadata->>'source', pour la détection de
# source dans une question (lookup direct d'article). L'ordre est important :
# "amendement" / "loi constitutionnelle" doivent être testés AVANT
# "constitution", pour qu'une question qui mentionne les deux résolve vers
# le texte d'amendement plutôt que vers la Constitution de base.
SOURCES_CORPUS: dict[str, str] = {
    "amendement": "Loi Constitutionnelle du 9 mai 2011 (amendement)",
    "loi constitutionnelle": "Loi Constitutionnelle du 9 mai 2011 (amendement)",
    "constitution": "Constitution de 1987 Amendée",
    "pénal": "Code pénal",
    "penal": "Code pénal",
}

SALUTATIONS: set[str] = {
    "bonjour", "bonsoir", "salut", "merci", "bonswa", "bonjou",
    "alo", "hello", "hi", "sak", "pase", "sak-pase", "halex",
}


def _chercher(question: str, k: int = 6) -> list[dict]:
    """Recherche par similarité dans Supabase.
    Retourne une liste de dicts : content, metadata, similarity."""
    vecteur = _embeddings.embed_query(question)
    resultat = _supabase.rpc(
        "match_documents",
        {"query_embedding": vecteur, "match_count": k},
    ).execute()
    return resultat.data


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
    """Regroupe les chunks retrouvés par (article, source), dans l'ordre de
    pertinence (le chunk le mieux classé fixe la position de son article).
    Si un même article revient sur plusieurs chunks, leurs textes sont
    concaténés dans l'ordre où ils apparaissent."""
    sources: list[dict] = []
    index: dict[tuple[str, str], dict] = {}
    for a in articles:
        article = a["metadata"].get("article", "?")
        source = a["metadata"].get("source", "?")
        cle = (article, source)
        texte = _texte_article(a)
        if cle in index:
            index[cle]["texte"] += "\n\n" + texte
        else:
            entree = {"article": article, "source": source, "texte": texte}
            index[cle] = entree
            sources.append(entree)
    return sources


def _etiquette_citation(article: str, source: str) -> str:
    """Étiquette stable et sans ambiguïté pour l'appariement citation ↔ puce.
    Doit être une copie exacte du couple (article, source) utilisé pour
    construire les puces (_construire_sources), afin que le filtrage par
    intersection puisse matcher la sortie du LLM au texte."""
    return f"[SOURCE: {article} — {source}]"


def _filtrer_sources_citees(sources: list[dict], articles_cites: list[str]) -> list[dict]:
    """Ne conserve, parmi les sources réellement récupérées, que celles dont
    l'étiquette [SOURCE: ...] figure dans articles_cites (intersection
    anti-hallucination). Ordre retenu : ordre d'apparition dans
    articles_cites, c'est-à-dire l'ordre dans lequel le LLM a cité les
    articles — plus utile pour l'utilisateur que l'ordre brut de pertinence
    du retriever."""
    index = {_etiquette_citation(s["article"], s["source"]): s for s in sources}
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
    rang   = meta.get("rang", "?")
    statut = meta.get("statut", "")
    date   = meta.get("date", "")

    parties = [source, f"rang {rang}"]
    if statut:
        parties.append(statut.replace("_", " "))
    if date and not date.startswith("XXXX"):
        parties.append(date)
    return "[" + " — ".join(str(p) for p in parties) + "]"


# --- Prompts : copies exactes de halex_core.py ---

_prompt = ChatPromptTemplate.from_template(
    """AVANT TOUTE CHOSE, vérifie : la question posée peut-elle être réellement
résolue par les articles fournis ci-dessous ? Une simple ressemblance de mots
ne suffit pas (exemple : une question sur la capitale d'un pays étranger NE
PEUT PAS être résolue par l'article sur la capitale d'Haïti). Si la réponse
est non, ta réponse entière doit être exactement : [HORS_DOMAINE]
Rien d'autre. Pas d'excuse, pas d'explication, pas de recommandation. Cette
règle prime sur toutes les instructions de style qui suivent.

Tu es Halex, un assistant juridique spécialisé dans le droit haïtien.
Ta mission : expliquer la loi aux citoyens en français simple et clair.

RÈGLES STRICTES :
1. Réponds UNIQUEMENT à partir des articles fournis ci-dessous.
2. Cite toujours les articles sur lesquels tu t'appuies (ex: "selon l'Article 4...")
   ET le texte dont ils proviennent (Constitution, Code pénal...).
3. Si les articles fournis ne permettent pas de répondre, dis-le honnêtement
   et suggère de consulter un professionnel du droit.
4. Ne donne jamais de conseil juridique personnalisé : tu expliques ce que dit la loi.
5. Dans articles_cites, liste UNIQUEMENT les étiquettes [SOURCE: ...] des articles
   que tu as effectivement utilisés pour fonder ta réponse. N'inclus pas les
   extraits consultés mais non utilisés. Recopie ces étiquettes EXACTEMENT
   telles qu'elles apparaissent ci-dessous, sans les modifier.
6. RÈGLE DE COMPLÉTUDE : Tu dois citer et utiliser TOUS les articles pertinents
   fournis dans le contexte. Le style de réponse demandé change la présentation
   et le ton, jamais la quantité d'information juridique. Omettre un article
   pertinent est une erreur grave.
7. Si tu mentionnes des étiquettes [SOURCE: ...] dans le texte de ta réponse,
   elles doivent apparaître UNIQUEMENT en toute fin de réponse, une par ligne,
   sans titre, sans puce, sans texte d'accompagnement.

COMMENT LIRE LES ARTICLES :
Chaque article est précédé de DEUX étiquettes entre crochets :
- [SOURCE: ...] l'identifie de façon stable, ex : [SOURCE: Article 8 — Constitution
  1987 Amendée]. C'est CETTE étiquette qu'il faut recopier dans articles_cites.
- une seconde étiquette donne sa source, son rang et son statut juridique.
  Exemple : [Code pénal — rang 3 — en vigueur].
- rang 1 = Constitution (loi suprême)
- rang 2-4 = étage législatif (lois, codes, décrets)
- rang 5 = actes subordonnés (arrêtés)
- statut « adopté non appliqué » = texte voté mais PAS appliqué par les tribunaux.

RÉSOLUTION DES CONTRADICTIONS (n'applique ces règles QUE si deux articles
fournis se contredisent réellement sur le même point) :

A. STATUT D'ABORD. Un article au statut « adopté non appliqué » ne l'emporte
   JAMAIS, même s'il est plus récent. Signale qu'il existe mais n'est pas
   encore appliqué, et réponds selon le texte réellement en vigueur.

B. LA CONSTITUTION EST LE PLAFOND (rang 1). Si un texte de rang inférieur
   semble la contredire, cite LES DEUX, précise que la Constitution prime
   en principe, et ajoute exactement ce message au citoyen :
   « ⚠️ Sur ce point, deux textes se contredisent. La Constitution prévaut en
   principe, car elle est la loi suprême. Il faut toutefois savoir que le
   Parlement n'est plus fonctionnel depuis le 13 janvier 2020 : l'exécutif
   adopte des décrets qui tiennent lieu de loi, sans le contrôle habituel du
   pouvoir législatif. Halex vous signale cette contradiction sans trancher à
   votre place ; pour votre situation précise, consultez un professionnel du droit. »

C. ENTRE TEXTES DE L'ÉTAGE LÉGISLATIF (lois, codes, décrets — rangs 2 à 4),
   c'est la DATE la plus récente qui l'emporte. Cite les deux et ajoute :
   « ℹ️ Deux textes traitent de cette question. Le plus récent l'emporte : la
   règle applicable est celle du texte le plus récent. »

D. TEXTES COMPLÉMENTAIRES (qui ne se contredisent pas mais se complètent) :
   cite-les ensemble, sans choisir.

Dans le doute, ne tranche pas : signale la tension et renvoie vers un
professionnel du droit.

ARTICLES DISPONIBLES :
{contexte}

QUESTION DU CITOYEN :
{question}

RÉPONSE (en français clair, avec citations de l'article ET du texte source) :

{instructions_mode}"""
)

_prompt_reformulation = ChatPromptTemplate.from_template(
    """Reformule la requête suivante en UNE seule question claire et complète,
en français, portant sur le droit haïtien (Constitution ou Code pénal).
Ne réponds PAS à la question. Renvoie UNIQUEMENT la question reformulée,
sans guillemets ni préambule.

Requête de l'utilisateur : {requete}

Question reformulée :"""
)


def reformuler(requete: str) -> str:
    return _llm.invoke(
        _prompt_reformulation.format(requete=requete)
    ).content.strip()


def _reponse_hors_domaine(methode: str = "vectorielle") -> dict:
    return {
        "reponse": (
            "Cette question semble sortir du domaine actuellement couvert par "
            "Halex (Constitution haïtienne de 1987 amendée et Code pénal). "
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
    r"(?:\barticles?\b|\bart\.?\b|\batik\b)\s*(\d+(?:-\d+)?)",
    re.IGNORECASE,
)
_RE_PREAMBULE = re.compile(r"\b(?:pr[ée]ambule|preyanbil)\b", re.IGNORECASE)


def _detecter_source_corpus(question_minuscule: str) -> str | None:
    """Première source de SOURCES_CORPUS dont le mot-clé apparaît dans la
    question (déjà en minuscules). Respecte l'ordre d'itération du dict."""
    for mot_cle, source in SOURCES_CORPUS.items():
        if mot_cle in question_minuscule:
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

_cache_sources_distinctes: list[str] | None = None


def _sources_distinctes() -> list[str]:
    """Sources distinctes présentes dans le corpus, mises en cache au niveau
    du module (un seul aller-retour Supabase par redémarrage du process)."""
    global _cache_sources_distinctes
    if _cache_sources_distinctes is not None:
        return _cache_sources_distinctes
    resultat = _supabase.table("documents").select("metadata->>source").execute()
    sources = {ligne["source"] for ligne in resultat.data if ligne.get("source")}
    _cache_sources_distinctes = sorted(sources)
    return _cache_sources_distinctes


def lookup_article(numero: str | None, source: str | None, preambule: bool = False) -> dict:
    """Requête directe (PAS match_documents) d'un article par son numéro
    (et éventuellement sa source), pour répondre exactement et sans coût de
    recherche vectorielle aux questions du type « article 4 » / « atik 12 »."""
    valeur_article = "Préambule" if preambule else f"Article {numero}"

    requete = (
        _supabase.table("documents")
        .select("content, metadata")
        .eq("metadata->>article", valeur_article)
    )
    if source:
        requete = requete.eq("metadata->>source", source)
    chunks = requete.execute().data

    if not chunks:
        sources_disponibles = _sources_distinctes()
        return {
            "reponse": (
                f"{valeur_article} n'existe pas dans les textes actuellement "
                "couverts par Halex. Les documents disponibles sont : "
                + ", ".join(sources_disponibles) + "."
            ),
            "sources": [],
            "hors_domaine": True,
            "demande_precision": False,
            "type": "reponse",
            "methode": "lookup_direct",
        }

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

    toutes_sources = _construire_sources(chunks)
    contexte = "\n\n".join(
        f"{_etiquette_citation(s['article'], s['source'])}\n{s['texte']}"
        for s in toutes_sources
    )
    prompt_final = (
        "Restitue fidèlement le texte de l'article suivant, en citant "
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


def poser_question(question: str, mode: str = MODE_PAR_DEFAUT) -> dict:
    """Même logique que halex_core.py, adaptée à la similarité pgvector.
    Conversion des seuils (embeddings normalisés) : sim = 1 - distance/2.
      distance 1.25  ->  similarité 0.375
      distance 0.9   ->  similarité 0.55
    Les comparaisons s'inversent : hors domaine si similarité < seuil.

    Ordre de résolution : salutation -> référence directe à un article ->
    mot unique -> recherche vectorielle (comportement d'origine, inchangé)."""

    instructions_mode = INSTRUCTIONS_MODES.get(mode, INSTRUCTIONS_MODES[MODE_PAR_DEFAUT])

    if detecter_salutation(question):
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

    reference = detecter_reference_article(question)
    if reference is not None:
        return lookup_article(
            reference["numero"], reference["source"], preambule=reference["preambule"]
        )

    if len(question.split()) == 1:
        return suggerer_questions_mot(question.split()[0])

    question_recherche = question

    # ① Jugement sur la requête ORIGINALE (similarité du meilleur résultat)
    meilleur = _chercher(question, k=1)
    sim_originale = meilleur[0]["similarity"] if meilleur else 0.0

    if sim_originale < SEUIL_SIM:
        # ② Seconde chance UNIQUEMENT pour les requêtes courtes (< 5 mots)
        if len(question.split()) < 5:
            question_reformulee = reformuler(question)
            resultat_reformule = _chercher(question_reformulee, k=1)
            sim_reformulee = (
                resultat_reformule[0]["similarity"] if resultat_reformule else 0.0
            )
            if sim_reformulee < SEUIL_SIM_SECONDE_CHANCE:
                return _reponse_hors_domaine()
            question_recherche = question_reformulee
        else:
            return _reponse_hors_domaine()
    elif len(question.split()) < 5:
        question_recherche = reformuler(question)

    # ③ Recherche élargie (k=6), comme dans halex_core.py
    articles = _chercher(question_recherche, k=6)

    contexte = "\n\n".join(
        f"{_etiquette_citation(a['metadata'].get('article', '?'), a['metadata'].get('source', '?'))}\n"
        f"{_etiquette(a['metadata'])} {a['metadata'].get('article', '')}\n{a['content']}"
        for a in articles
    )

    # ④ Le modèle répond à la QUESTION ORIGINALE, en sortie structurée
    # (réponse rédigée + étiquettes SOURCE réellement citées).
    prompt_final = _prompt.format(contexte=contexte, question=question, instructions_mode=instructions_mode)
    echec_technique = False
    try:
        resultat = _llm_structure.invoke(prompt_final)
        reponse_texte = resultat.reponse
        articles_cites = resultat.articles_cites
    except Exception:
        # Sortie structurée invalide/imparfaite (ex. appel de fonction raté) :
        # on retombe sur un appel texte brut pour ne jamais priver
        # l'utilisateur de réponse. Signal de citation perdu -> repli top-1
        # ci-dessous (impossible de distinguer "rien cité" de "panne").
        _logger.warning("Sortie structurée invalide pour la question %r ; repli sur réponse brute.", question)
        reponse_texte = _llm.invoke(prompt_final).content
        articles_cites = []
        echec_technique = True

    if "[HORS_DOMAINE]" in reponse_texte:
        return _reponse_hors_domaine()

    reponse_texte = _nettoyer_reponse_visible(reponse_texte)

    toutes_sources = _construire_sources(articles)
    sources_citees = _filtrer_sources_citees(toutes_sources, articles_cites)

    if not sources_citees and toutes_sources and (echec_technique or articles_cites):
        # Repli top-1 uniquement en cas de signal cassé : panne technique,
        # ou articles_cites non vide mais ne correspondant à aucune source
        # récupérée (dérive de format / incohérence). Dans ces deux cas on
        # ne peut pas faire confiance au signal -> puce sûre (top-1) plutôt
        # que les six d'origine.
        # Si articles_cites est une liste vide *valide* (le LLM a répondu
        # normalement et n'a réellement rien cité), on n'affiche aucune
        # puce : une puce hors-sujet serait plus trompeuse qu'aucune puce.
        _logger.warning(
            "Signal de citation incohérent (articles_cites=%r) pour la question %r ; repli top-1.",
            articles_cites, question,
        )
        sources_citees = toutes_sources[:1]

    return {
        "reponse": reponse_texte,
        "sources": sources_citees,
        "hors_domaine": False,
        "demande_precision": False,
        "type": "reponse",
        "methode": "vectorielle",
    }


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

    total = (
        _supabase.table("documents")
        .select("id", count="exact")
        .like("content", "Article%")
        .execute()
    )
    offset = tranche % total.count

    resultat = (
        _supabase.table("documents")
        .select("id, content, metadata")
        .like("content", "Article%")
        .order("id")
        .range(offset, offset)
        .execute()
    )
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