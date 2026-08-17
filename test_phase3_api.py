"""
Smoke test HTTP Phase 3.

Lancez d'abord :
    uvicorn api:app --reload

Puis :
    python test_phase3_api.py

Le script maintient lui-même l'historique envoyé à /poser-question et affiche
les diagnostics conversationnels + normatifs.
"""

from __future__ import annotations

import json
import urllib.request

API = "http://localhost:8000/poser-question"


def post(question: str, historique: list[dict]) -> dict:
    payload = json.dumps(
        {
            "question": question,
            "mode": "citoyen",
            "historique": historique,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    req = urllib.request.Request(
        API,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def resume_normatif(data: dict) -> dict:
    diag = data.get("normatif") or {}
    return {
        "documents": [
            {
                "document": d.get("document"),
                "role": d.get("role"),
                "confiance": d.get("confiance"),
            }
            for d in diag.get("documents", [])
        ],
        "relations": diag.get("relations", []),
        "decisions": diag.get("decisions", []),
        "conflits_non_resolus": diag.get("conflits_non_resolus", []),
    }


def main():
    questions = [
        "Dans quelles conditions peut-on invoquer la légitime défense ?",
        "Est-ce différent si elle protège une autre personne ?",
        "Et dans ce dernier cas, la proportionnalité compte-t-elle ?",
        "Le simple fait de posséder de la pornographie enfantine est-il puni ?",
    ]

    historique: list[dict] = []

    for numero, q in enumerate(questions, start=1):
        print("\n" + "=" * 80)
        print(f"Q{numero}: {q}")

        data = post(q, historique)

        print("\nCONVERSATION:")
        print(json.dumps(data.get("conversation"), ensure_ascii=False, indent=2))

        print("\nNORMATIF:")
        print(json.dumps(resume_normatif(data), ensure_ascii=False, indent=2))

        print("\nRÉPONSE:")
        print(data.get("reponse"))

        historique.append({"role": "user", "content": q})
        historique.append(
            {"role": "assistant", "content": data.get("reponse", "")}
        )

    print("\n" + "=" * 80)
    print("À vérifier :")
    print("- Q3 : depend_historique=true ; Article 38 doit être principal.")
    print("- Q3 : Article 40 peut être complémentaire/contexte, pas fusionné avec 38.")
    print("- Q4 : depend_historique=false ; pas de contamination légitime défense.")
    print("- Q4 : Article 390 doit être principal.")


if __name__ == "__main__":
    main()
