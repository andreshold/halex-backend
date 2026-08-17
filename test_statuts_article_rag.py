"""Non-régression : statuts d'article et résolution des modifications."""

import unittest

from modifications import _enrichir_depuis_metadata


class Query:
    def __init__(self, rows): self.rows = rows
    def select(self, *_args): return self
    def in_(self, *_args): return self
    def ilike(self, *_args): return self
    def order(self, *_args): return self
    def limit(self, *_args): return self
    def execute(self): return type("Response", (), {"data": self.rows})()


class Client:
    def __init__(self, rows): self.rows = rows
    def table(self, _name): return Query(self.rows)


class StatutArticleRagTests(unittest.TestCase):
    def test_article_modifie_charge_sa_source_modificatrice(self):
        original = {
            "content": "Article 257.- Texte ancien.",
            "metadata": {
                "source": "Code du Travail", "article": "Article 257",
                "statut": "modifie",
                "article_modifie_par": "Loi no CL-05-2009-006 du 6 mai 2009",
                "article_date_modification": "2009-05-06",
                "article_publication_modification": None,
            },
        }
        modification = {
            "content": "Article 1.- L'article 257 est modifié.",
            "metadata": {
                "source": "Loi no CL-05-2009-006 du 6 mai 2009",
                "article": "Article 1", "statut": "en_vigueur",
            },
        }
        enrichis, relations = _enrichir_depuis_metadata(Client([modification]), [original])
        self.assertEqual(len(enrichis), 2)
        self.assertEqual(enrichis[1]["metadata"]["source"], original["metadata"]["article_modifie_par"])
        self.assertEqual(relations[0]["article_modifie"], "Article 257")

    def test_article_non_modifie_ne_declenche_aucune_recherche(self):
        original = {"content": "Texte", "metadata": {"source": "Code", "article": "Article 1", "statut": "en_vigueur"}}
        enrichis, relations = _enrichir_depuis_metadata(Client([]), [original])
        self.assertEqual(enrichis, [original])
        self.assertEqual(relations, [])


if __name__ == "__main__":
    unittest.main()
