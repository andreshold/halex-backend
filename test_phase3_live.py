"""
Test live facultatif du qualificateur Phase 3.

Charge explicitement le fichier .env du backend avant d'initialiser ChatOpenAI.

Usage:
    python test_phase3_live.py
"""

from __future__ import annotations

import os
import sys

from dotenv import find_dotenv, load_dotenv
from langchain_openai import ChatOpenAI

from moteur_normatif import analyser_normativement


def _charger_configuration() -> None:
    """
    Cherche le .env depuis le répertoire courant / parents, puis le charge.

    Le moteur principal halex_core_supabase.py fait déjà load_dotenv() avant
    d'initialiser ChatOpenAI. Ce test doit reproduire le même comportement.
    """
    chemin_env = find_dotenv(usecwd=True)

    if chemin_env:
        load_dotenv(chemin_env, override=False)
        print(f"[CONFIG] .env chargé : {chemin_env}")
    else:
        # Permet aussi le cas où OPENAI_API_KEY a été définie directement
        # comme variable d'environnement Windows.
        load_dotenv(override=False)
        print("[CONFIG] Aucun .env trouvé depuis le répertoire courant.")

    if not os.getenv("OPENAI_API_KEY") and not os.getenv("OPENAI_ADMIN_KEY"):
        raise RuntimeError(
            "Clé OpenAI introuvable. Ajoutez OPENAI_API_KEY=... dans le "
            "fichier .env de halex-backend, ou définissez OPENAI_API_KEY "
            "comme variable d'environnement Windows. Ne mettez jamais la "
            "clé directement dans ce script."
        )


def main():
    _charger_configuration()

    # Même modèle que le moteur Halex actuel.
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    article38 = {
        "content": (
            "Article 38 : N’est pas pénalement responsable la personne qui, "
            "devant une atteinte injustifiée envers elle-même ou autrui, "
            "accomplit dans le même temps un acte commandé par la nécessité "
            "de la légitime défense d’elle-même ou d’autrui, sauf disproportion..."
        ),
        "metadata": {
            "chunk_id": "ART38",
            "source": "Code Pénal",
            "source_courte": "Code Pénal",
            "article": "Article 38",
            "type_norme": "code",
            "rang": 30,
            "date": "2020-06-24",
            "date_publication": "2020-06-24",
            "statut": "en_vigueur",
            "concepts_juridiques": ["légitime défense", "irresponsabilité pénale"],
            "conditions_application": [
                "défense de soi-même ou d'autrui ; nécessité ; proportionnalité"
            ],
            "exceptions": [],
            "circonstances": [],
            "references_articles": [],
        },
    }

    article40 = {
        "content": (
            "Article 40 : N’est pas pénalement responsable la personne qui, "
            "face à un danger actuel ou imminent qui menace elle-même, autrui "
            "ou un bien, accomplit un acte nécessaire à la sauvegarde de la "
            "personne ou du bien, sauf disproportion..."
        ),
        "metadata": {
            "chunk_id": "ART40",
            "source": "Code Pénal",
            "source_courte": "Code Pénal",
            "article": "Article 40",
            "type_norme": "code",
            "rang": 30,
            "date": "2020-06-24",
            "date_publication": "2020-06-24",
            "statut": "en_vigueur",
            "concepts_juridiques": ["irresponsabilité pénale"],
            "conditions_application": [],
            "exceptions": [
                "danger actuel ou imminent ; acte nécessaire ; absence de disproportion"
            ],
            "circonstances": ["danger actuel ou imminent"],
            "references_articles": [],
        },
    }

    question = (
        "Dans le cas où une personne agit en légitime défense pour protéger "
        "autrui, la proportionnalité des moyens compte-t-elle ?"
    )

    analyse = analyser_normativement(
        question,
        [article38, article40],
        llm,
    )

    print("\n=== BLOC NORMATIF ===")
    print(analyse["bloc_prompt"])

    print("\n=== DIAGNOSTIC ===")
    diagnostic = analyse["diagnostic"]
    print(diagnostic)

    roles = {
        d["document"]: d["role"]
        for d in diagnostic["documents"]
    }

    print("\n=== ASSERTIONS ===")
    print("ART38 :", roles.get("ART38"))
    print("ART40 :", roles.get("ART40"))

    assert roles.get("ART38") == "principal", (
        "Échec : ART38 devait être qualifié principal, reçu "
        f"{roles.get('ART38')!r}"
    )

    assert roles.get("ART40") in {"complementaire", "contexte"}, (
        "Échec : ART40 devait être complémentaire ou contexte, reçu "
        f"{roles.get('ART40')!r}"
    )

    print("\nOK — qualification live Phase 3")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nERREUR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise