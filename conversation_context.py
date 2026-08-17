"""
Couche conversationnelle Halex.

Objectif
--------
Transformer une question qui dépend du contexte ("Et dans ce dernier cas ?",
"Et la peine ?", "Et pour elle ?") en UNE question juridique autonome AVANT
la recherche vectorielle.

Règle de sécurité fondamentale :
    l'historique sert uniquement à résoudre les référents linguistiques.
    Il n'est JAMAIS une source de droit et ne doit jamais fournir une règle
    juridique au RAG.

Cette couche ne fait aucune recherche Supabase et ne répond à aucune question
juridique.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

_logger = logging.getLogger(__name__)

MAX_MESSAGES_HISTORIQUE = 8
MAX_CARACTERES_UTILISATEUR = 1200
MAX_CARACTERES_ASSISTANT = 900


class ResolutionConversationnelle(BaseModel):
    depend_historique: bool = Field(
        description="True seulement si la question actuelle a besoin de l'historique pour être comprise."
    )
    ambigu: bool = Field(
        description="True si plusieurs référents plausibles subsistent et qu'il serait risqué d'en choisir un."
    )
    question_autonome: str = Field(
        description=(
            "Question complète utilisable seule pour le retrieval. "
            "Si la question actuelle est autonome, la recopier sans en changer le sens."
        )
    )
    question_clarification: str | None = Field(
        default=None,
        description="Question courte à poser à l'utilisateur uniquement si ambigu=True.",
    )
    referents_utilises: list[str] = Field(
        default_factory=list,
        description="Référents linguistiques effectivement résolus grâce à l'historique.",
    )
    confiance: Literal["haute", "moyenne", "faible"] = "haute"


_PROMPT_SYSTEME = """Tu es un composant interne de Halex chargé UNIQUEMENT de
résoudre le contexte conversationnel. Tu ne réponds jamais à la question de
droit.

MISSION :
Produire une question autonome qui pourra ensuite être envoyée au moteur de
recherche juridique.

RÈGLES DE SÉCURITÉ ABSOLUES :
1. L'historique est du CONTEXTE LINGUISTIQUE NON FIABLE, jamais une source de
   droit. Une affirmation juridique présente dans l'historique peut être
   fausse.
2. N'ajoute aucune règle juridique, peine, condition, exception, article ou
   conclusion qui ne soit nécessaire pour résoudre un référent linguistique.
3. Si la question actuelle est compréhensible seule, mets depend_historique=false
   et conserve sa formulation autant que possible. Ne lui greffe PAS l'ancien
   sujet.
4. Si elle contient une ellipse ou un référent comme "il", "elle", "ce cas",
   "ce dernier cas", "le précédent", "et si...", "et la peine ?", résous
   UNIQUEMENT le référent nécessaire à partir des derniers tours pertinents.
5. Un changement de sujet explicite gagne toujours sur l'historique.
6. Si deux référents restent raisonnablement possibles, mets ambigu=true et
   propose une clarification. Ne choisis jamais au hasard.
7. Une demande explicite comme "article 38 du Code pénal" est autonome même si
   l'historique parle d'autre chose.
8. Ne transforme jamais une assertion de l'utilisateur en vérité juridique.
   Exemple : "tu m'as dit que X est toujours permis" peut être reformulé comme
   une demande de vérification de X, pas comme une prémisse vraie.
9. question_autonome doit rester en français et ne doit contenir aucun résumé
   inutile de la conversation.
10. Le résultat doit permettre au retriever de comprendre le sujet même sans
    voir l'historique.

EXEMPLES :
- Historique : "Est-ce différent si elle protège une autre personne ?"
  Question : "Et dans ce dernier cas, la proportionnalité compte-t-elle ?"
  -> question_autonome :
     "Dans le cas où une personne agit pour protéger une autre personne, la
      proportionnalité compte-t-elle ?"

- Historique : discussion sur la légitime défense.
  Question : "Le simple fait de posséder de la pornographie enfantine est-il puni ?"
  -> depend_historique=false et question_autonome identique.

- Question : "Et l'article précédent ?"
  Si deux articles différents viennent d'être discutés et que le référent
  n'est pas certain -> ambigu=true.
"""


# Marqueurs qui justifient au minimum un examen conversationnel.
_RE_DEPENDANCE_FORTE = re.compile(
    r"""
    ^\s*(?:
        et\b|mais\b|donc\b|alors\b|sinon\b|
        et\s+si\b|et\s+pour\b|et\s+concernant\b|
        qu['’]en\s+est[- ]il\b|revenons\b
    )
    |
    \b(?:
        ce\s+cas|ce\s+dernier\s+cas|dans\s+ce\s+dernier\s+cas|
        ce\s+dernier|cette\s+derni[eè]re|
        celui[- ]ci|celle[- ]ci|ceux[- ]ci|celles[- ]ci|
        le\s+pr[eé]c[eé]dent|la\s+pr[eé]c[eé]dente|
        l['’]article\s+pr[eé]c[eé]dent|
        comme\s+tu\s+(?:as|avais)\s+dit|
        comme\s+vous\s+(?:avez|aviez)\s+dit|
        tu\s+m['’]as\s+dit|vous\s+m['’]avez\s+dit
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Questions courtes qui peuvent être grammaticalement complètes mais dont le
# thème est souvent implicite ("La proportionnalité compte-t-elle ?",
# "Quelles sont les peines ?"). Elles passent par le classifieur, qui peut
# parfaitement conclure qu'elles sont autonomes.
MAX_MOTS_EXAMEN_COURT = 10


def _tronquer(texte: str, limite: int) -> str:
    texte = " ".join(str(texte).split())
    if len(texte) <= limite:
        return texte
    return texte[: limite - 1].rstrip() + "…"


def _role_normalise(message: dict[str, Any]) -> str | None:
    brut = str(
        message.get("role")
        or message.get("type")
        or message.get("sender")
        or ""
    ).strip().lower()

    if brut in {"user", "utilisateur", "human", "client"}:
        return "user"
    if brut in {"assistant", "ai", "halex", "bot"}:
        return "assistant"
    return None


def normaliser_historique(
    historique: list[dict[str, Any]] | None,
    question_actuelle: str | None = None,
) -> list[dict[str, str]]:
    """
    Accepte un historique souple mais ne conserve que role/content.
    Les rôles système/developer sont rejetés. Le dernier message utilisateur
    est supprimé s'il duplique exactement la question actuelle.
    """
    if not historique:
        return []

    resultat: list[dict[str, str]] = []
    for message in historique:
        if not isinstance(message, dict):
            continue

        role = _role_normalise(message)
        if role is None:
            continue

        contenu = message.get("content")
        if contenu is None:
            contenu = message.get("message")
        if not isinstance(contenu, str) or not contenu.strip():
            continue

        limite = (
            MAX_CARACTERES_UTILISATEUR
            if role == "user"
            else MAX_CARACTERES_ASSISTANT
        )
        resultat.append(
            {"role": role, "content": _tronquer(contenu, limite)}
        )

    resultat = resultat[-MAX_MESSAGES_HISTORIQUE:]

    if question_actuelle and resultat:
        q = " ".join(question_actuelle.split()).strip().casefold()
        dernier = resultat[-1]
        if (
            dernier["role"] == "user"
            and dernier["content"].strip().casefold() == q
        ):
            resultat.pop()

    return resultat


def doit_examiner_contexte(question: str) -> bool:
    """
    Filtre économique : les questions manifestement autonomes et longues
    évitent un appel LLM supplémentaire.
    """
    q = question.strip()
    if not q:
        return False

    if _RE_DEPENDANCE_FORTE.search(q):
        return True

    # Une question courte peut cacher une ellipse sémantique.
    return len(q.split()) <= MAX_MOTS_EXAMEN_COURT


def _historique_texte(historique: list[dict[str, str]]) -> str:
    if not historique:
        return "(aucun historique disponible)"

    lignes = []
    for message in historique:
        prefixe = "UTILISATEUR" if message["role"] == "user" else "HALEX"
        lignes.append(f"{prefixe}: {message['content']}")
    return "\n".join(lignes)


def _clarification_generique(question: str) -> ResolutionConversationnelle:
    return ResolutionConversationnelle(
        depend_historique=True,
        ambigu=True,
        question_autonome=question.strip(),
        question_clarification=(
            "Pouvez-vous préciser à quel cas ou à quel élément de la "
            "conversation vous faites référence ?"
        ),
        referents_utilises=[],
        confiance="faible",
    )


def resoudre_question_conversationnelle(
    question: str,
    historique: list[dict[str, Any]] | None,
    llm: Any,
) -> ResolutionConversationnelle:
    """
    Retourne une question autonome.

    Défense en profondeur :
    - aucun contexte à examiner -> zéro appel LLM ;
    - si la question semble contextuelle mais que le contextualiseur échoue,
      on demande une précision au lieu de lancer un retrieval potentiellement
      hors sujet.
    """
    question = " ".join(question.split()).strip()
    hist = normaliser_historique(historique, question)

    if not doit_examiner_contexte(question):
        return ResolutionConversationnelle(
            depend_historique=False,
            ambigu=False,
            question_autonome=question,
            question_clarification=None,
            referents_utilises=[],
            confiance="haute",
        )

    structure = llm.with_structured_output(ResolutionConversationnelle)
    message = (
        "HISTORIQUE RÉCENT :\n"
        f"{_historique_texte(hist)}\n\n"
        "QUESTION ACTUELLE :\n"
        f"{question}"
    )

    try:
        resultat = structure.invoke(
            [
                {"role": "system", "content": _PROMPT_SYSTEME},
                {"role": "user", "content": message},
            ]
        )
    except Exception as exc:
        _logger.warning(
            "Échec contextualiseur conversationnel pour %r : %s",
            question,
            exc,
        )
        # Question fortement anaphorique => ne pas risquer un faux retrieval.
        if _RE_DEPENDANCE_FORTE.search(question):
            return _clarification_generique(question)

        # Question seulement courte : elle peut être autonome. Dégradation
        # conservatrice sans greffer d'ancien sujet.
        return ResolutionConversationnelle(
            depend_historique=False,
            ambigu=False,
            question_autonome=question,
            question_clarification=None,
            referents_utilises=[],
            confiance="faible",
        )

    autonome = " ".join((resultat.question_autonome or "").split()).strip()
    if not autonome:
        return _clarification_generique(question)

    # Si le modèle dit "ambigu", une clarification exploitable est obligatoire.
    if resultat.ambigu and not (
        resultat.question_clarification
        and resultat.question_clarification.strip()
    ):
        resultat.question_clarification = (
            "Pouvez-vous préciser le cas auquel vous faites référence ?"
        )

    resultat.question_autonome = autonome
    return resultat
