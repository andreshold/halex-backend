"""
Tests déterministes de la Phase 3 Halex.

Aucun appel réseau, Supabase ou OpenAI.

Usage:
    python test_phase3_normatif.py
"""

from moteur_normatif import (
    RelationSemantique,
    _decision_contradiction,
    analyser_normativement,
)


def doc(
    chunk_id,
    article,
    type_norme,
    rang,
    date,
    statut="en_vigueur",
    content="Texte",
):
    return {
        "content": content,
        "metadata": {
            "chunk_id": chunk_id,
            "source": "Source Test",
            "source_courte": "Source Test",
            "article": article,
            "type_norme": type_norme,
            "rang": rang,
            "date": date,
            "date_publication": "1900-01-01",
            "statut": statut,
            "concepts_juridiques": [],
            "conditions_application": [],
            "exceptions": [],
            "circonstances": [],
            "references_articles": [],
        },
    }


class FakeStructured:
    def __init__(self, resultat):
        self.resultat = resultat

    def invoke(self, messages):
        return self.resultat


class FakeLLM:
    def __init__(self, resultat):
        self.resultat = resultat

    def with_structured_output(self, cls):
        return FakeStructured(self.resultat)


def main():
    # Statut avant tout.
    constitution_non_appliquee = doc(
        "CONST", "Article 1", "constitution", 10, "2099-01-01",
        statut="adopte_non_applique",
    )
    code = doc("CODE", "Article 1", "code", 30, "2020-01-01")

    rel = RelationSemantique(
        gauche="CONST",
        droite="CODE",
        type="contradiction",
        raison="Solutions incompatibles.",
    )
    r = _decision_contradiction(constitution_non_appliquee, code, rel)
    assert r["gagnant"] == "CODE"
    assert r["raison"] == "statut"

    # Rang avant spécialité et date.
    constitution = doc("CONST2", "Article 2", "constitution", 10, "1987-01-01")
    code_special = doc("CODE2", "Article 2", "code", 30, "2099-01-01")
    rel = RelationSemantique(
        gauche="CONST2",
        droite="CODE2",
        type="specialite",
        document_special="CODE2",
        incompatibles_sur_question=True,
        raison="Le code vise un cas plus précis.",
    )
    r = _decision_contradiction(constitution, code_special, rel)
    assert r["gagnant"] == "CONST2"
    assert r["raison"] == "rang"

    # Même rang : spécialité avant date.
    loi_generale = doc("LOI", "Article 5", "loi", 30, "2025-01-01")
    code_special_ancien = doc("SPECIAL", "Article 6", "code", 30, "2020-01-01")
    rel = RelationSemantique(
        gauche="LOI",
        droite="SPECIAL",
        type="specialite",
        document_special="SPECIAL",
        incompatibles_sur_question=True,
        raison="Le texte SPECIAL règle précisément le cas posé.",
    )
    r = _decision_contradiction(loi_generale, code_special_ancien, rel)
    assert r["gagnant"] == "SPECIAL"
    assert r["raison"] == "specialite"

    # Même rang, contradiction sans spécialité : date juridique.
    ancien = doc("A", "Article 10", "loi", 30, "2020-01-01")
    recent = doc("B", "Article 11", "decret", 30, "2022-01-01")
    rel = RelationSemantique(
        gauche="A",
        droite="B",
        type="contradiction",
        raison="Solutions incompatibles.",
    )
    r = _decision_contradiction(ancien, recent, rel)
    assert r["gagnant"] == "B"
    assert r["raison"] == "date"

    # date_publication est ignorée : dates juridiques égales -> non résolu.
    a = doc("C", "Article 12", "code", 30, "2026-01-01")
    b = doc("D", "Article 13", "decret", 30, "2026-01-01")
    a["metadata"]["date_publication"] = "1825-01-01"
    b["metadata"]["date_publication"] = "2026-01-01"
    rel = RelationSemantique(
        gauche="C",
        droite="D",
        type="contradiction",
        raison="Solutions incompatibles.",
    )
    r = _decision_contradiction(a, b, rel)
    assert r["gagnant"] is None
    assert r["raison"] == "egalite_normative"

    print("OK — moteur normatif déterministe Phase 3")


if __name__ == "__main__":
    main()