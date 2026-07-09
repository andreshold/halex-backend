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

_prompt = ChatPromptTemplate.from_template(
    """Tu es Halex, un assistant juridique spécialisé dans le droit haïtien.
Ta mission : expliquer la loi aux citoyens en français simple et clair.

RÈGLES STRICTES :
1. Réponds UNIQUEMENT à partir des articles fournis ci-dessous.
2. Cite toujours les articles sur lesquels tu t'appuies (ex: "selon l'Article 4...").
3. Si les articles fournis ne permettent pas de répondre, dis-le honnêtement
   et suggère de consulter un professionnel du droit.
4. Ne donne jamais de conseil juridique personnalisé : tu expliques ce que dit la loi.

ARTICLES DE LA CONSTITUTION :
{contexte}

QUESTION DU CITOYEN :
{question}

RÉPONSE (en français clair, avec citations) :"""
)

# Instruction dédiée à la reformulation : transformer une requête brute
# (mots-clés, question mal formée) en UNE question claire — sans y répondre.
_prompt_reformulation = ChatPromptTemplate.from_template(
    """Reformule la requête suivante en UNE seule question claire et complète,
en français, portant sur le droit constitutionnel haïtien.
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
            "Cette question semble sortir du domaine couvert par la "
            "Constitution haïtienne de 1987. Je ne peux pas y répondre "
            "de façon fiable. Pour votre situation, consultez un "
            "professionnel du droit ou l'autorité compétente."
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
    #    Plutôt que de deviner, on demande une vraie question.
    if len(question.split()) == 1:
        return {
            "reponse": (
                "Votre demande est très courte et je préfère ne pas deviner. "
                "Pouvez-vous la formuler en une question complète ? "
                "Par exemple : « Quelle est la devise nationale d'Haïti ? » "
                "ou « Que dit la Constitution sur la nationalité ? »"
            ),
            "sources": [],
            "hors_domaine": False,
            "demande_precision": True,
        }

    SEUIL = 1.25                # calibré sur mesures (calibrer_seuil.py)
    SEUIL_SECONDE_CHANCE = 0.9  # calibré sur mesures (diagnostic_seconde_chance.py)
                                # NB : marge fine (0.877 vs 0.909) — surveillé par pytest

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
            # La seconde chance a réussi : on cherchera avec la version reformulée
            question_recherche = question_reformulee
        else:
            return _reponse_hors_domaine()
    elif len(question.split()) < 5:
        # Requête courte qui passe déjà le seuil : on reformule quand même
        # pour AMÉLIORER la recherche (ex: "nationalité" 1.052 → 0.399)
        question_recherche = reformuler(question)

    # ③ Recherche des 4 articles
    resultats = _base.similarity_search_with_score(question_recherche, k=4)
    articles = [doc for doc, score in resultats]
    contexte = "\n\n".join(
        f"[{d.metadata['article']} — {d.metadata['contexte']}]\n{d.page_content}"
        for d in articles
    )

    # ④ Le modèle répond à la QUESTION ORIGINALE
    reponse = _llm.invoke(_prompt.format(contexte=contexte, question=question))
    return {
        "reponse": reponse.content,
        "sources": [
            {"article": d.metadata["article"], "contexte": d.metadata["contexte"]}
            for d in articles
        ],
        "hors_domaine": False,
        "demande_precision": False,
    }