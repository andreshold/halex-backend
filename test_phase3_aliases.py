"""
Test du correctif d'alias Phase 3 v2.
Aucun réseau.
"""

from moteur_normatif import (
    QualificationNormative,
    QualificationDocument,
    RelationSemantique,
    qualifier_documents,
)


class FakeStructured:
    def invoke(self, messages):
        parsed = QualificationNormative(
            documents=[
                QualificationDocument(
                    document="[NORMDOC: D1]",
                    role="principal",
                    raison="Répond directement à la question.",
                    confiance="haute",
                ),
                QualificationDocument(
                    document="D2",
                    role="complementaire",
                    raison="Ajoute un régime distinct.",
                    confiance="haute",
                ),
            ],
            relations=[
                RelationSemantique(
                    gauche="[NORMDOC: D1]",
                    droite="NORMDOC:D2",
                    type="complementarite",
                    raison="Les deux textes ne se contredisent pas.",
                    confiance="haute",
                )
            ],
        )
        return {"raw": None, "parsed": parsed, "parsing_error": None}


class FakeLLM:
    def with_structured_output(self, cls, include_raw=False):
        return FakeStructured()


def doc(chunk_id, article):
    return {
        "content": "Texte",
        "metadata": {
            "chunk_id": chunk_id,
            "source": "Code Pénal",
            "source_courte": "Code Pénal",
            "article": article,
            "type_norme": "code",
            "rang": 30,
            "date": "2020-06-24",
            "date_publication": "2020-06-24",
            "statut": "en_vigueur",
            "concepts_juridiques": [],
            "conditions_application": [],
            "exceptions": [],
            "circonstances": [],
            "references_articles": [],
        },
    }


def main():
    resultat = qualifier_documents(
        "Question test",
        [doc("ART38", "Article 38"), doc("ART40", "Article 40")],
        FakeLLM(),
    )

    roles = {d.document: d.role for d in resultat.documents}
    assert roles["ART38"] == "principal"
    assert roles["ART40"] == "complementaire"

    assert resultat.relations[0].gauche == "ART38"
    assert resultat.relations[0].droite == "ART40"

    print("OK — normalisation des alias Phase 3 v2")


if __name__ == "__main__":
    main()
