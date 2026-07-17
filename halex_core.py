from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()

# On charge le cerveau UNE SEULE FOIS au démarrage (pas à chaque question)
_embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
_base = FAISS.load_local(
    "faiss_index", _embeddings, allow_dangerous_deserialization=True
)
_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# Date charnière : dysfonctionnement du pouvoir législatif haïtien.
# Un décret publié À PARTIR de cette date porte une force législative de fait.
DATE_VIDE_LEGISLATIF = "2020-01-13"


def _etiquette(meta: dict) -> str:
    """Fabrique l'étiquette juridique d'un article à partir de ses métadonnées.
    Robuste à l'absence de champs (le Code pénal n'a pas 'contexte')."""
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


_prompt = ChatPromptTemplate.from_template(
    """Tu es Halex, un assistant juridique spécialisé dans le droit haïtien.
Ta mission : expliquer la loi aux citoyens en français simple et clair.

RÈGLES STRICTES :
1. Réponds UNIQUEMENT à partir des articles fournis ci-dessous.
2. Cite toujours les articles sur lesquels tu t'appuies (ex: "selon l'Article 4...")
   ET le texte dont ils proviennent (Constitution, Code pénal...).
3. Si les articles fournis ne permettent pas de répondre, dis-le honnêtement
   et suggère de consulter un professionnel du droit.
4. Ne donne jamais de conseil juridique personnalisé : tu expliques ce que dit la loi.

COMMENT LIRE LES ARTICLES :
Chaque article est précédé d'une étiquette entre crochets indiquant sa source,
son rang et son statut. Exemple : [Code pénal — rang 3 — en vigueur].
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

RÉPONSE (en français clair, avec citations de l'article ET du texte source) :"""
)

# Instruction dédiée à la reformulation : transformer une requête brute
# (mots-clés, question mal formée) en UNE question claire — sans y répondre.
_prompt_reformulation = ChatPromptTemplate.from_template(
    """Reformule la requête suivante en UNE seule question claire et complète,
en français, portant sur le droit haïtien (Constitution ou Code pénal).
Ne réponds PAS à la question. Renvoie UNIQUEMENT la question reformulée,
sans guillemets ni préambule.

Requête de l'utilisateur : {requete}

Question reformulée :"""
)


def reformuler(requete: str) -> str:
    """Transforme une requête brute en question nette pour améliorer la recherche."""
    question_nette = _llm.invoke(
        _prompt_reformulation.format(requete=requete)
    ).content.strip()
    return question_nette


def _reponse_hors_domaine() -> dict:
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
    }


def poser_question(question: str) -> dict:
    """Moteur de Halex — garde-fous de la Phase C :
    ⓪ un mot isolé → demande de précision (Halex n'est pas un dictionnaire) ;
    ① seuil sur la requête ORIGINALE ;
    ② si échec MAIS requête courte : seconde chance après reformulation,
       jugée avec un seuil PLUS STRICT ;
    ③ en bout de chaîne, le prompt impose l'honnêteté du modèle."""

    # ⓪ Politique produit : un mot isolé est trop ambigu pour être deviné.
    if len(question.split()) == 1:
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
        }

    SEUIL = 1.25                # calibré sur mesures (calibrer_seuil.py)
    SEUIL_SECONDE_CHANCE = 0.9  # calibré sur mesures (diagnostic_seconde_chance.py)
                                # NB : marge fine — surveillé par pytest

    question_recherche = question

    # ① Jugement sur la requête ORIGINALE
    score_original = _base.similarity_search_with_score(question, k=1)[0][1]

    if score_original > SEUIL:
        # ② Seconde chance UNIQUEMENT pour les requêtes courtes (< 5 mots)
        if len(question.split()) < 5:
            question_reformulee = reformuler(question)
            score_reformule = _base.similarity_search_with_score(
                question_reformulee, k=1
            )[0][1]
            if score_reformule > SEUIL_SECONDE_CHANCE:
                return _reponse_hors_domaine()
            question_recherche = question_reformulee
        else:
            return _reponse_hors_domaine()
    elif len(question.split()) < 5:
        question_recherche = reformuler(question)

    # ③ Recherche des articles. k élargi à 6 pour que d'éventuels textes
    #    en conflit remontent ENSEMBLE (indispensable à la résolution A-D).
    resultats = _base.similarity_search_with_score(question_recherche, k=6)
    articles = [doc for doc, score in resultats]

    # Le contexte porte désormais l'ÉTIQUETTE juridique (source, rang, statut, date)
    contexte = "\n\n".join(
        f"{_etiquette(d.metadata)} {d.metadata.get('article', '')}\n{d.page_content}"
        for d in articles
    )

    # ④ Le modèle répond à la QUESTION ORIGINALE
    reponse = _llm.invoke(_prompt.format(contexte=contexte, question=question))
    return {
        "reponse": reponse.content,
        "sources": [
            {
                "article": d.metadata.get("article", "?"),
                "source": d.metadata.get("source", "?"),
                "contexte": d.metadata.get("contexte", ""),  # bonus, vide si absent
            }
            for d in articles
        ],
        "hors_domaine": False,
        "demande_precision": False,
    }