import unittest
from unittest.mock import patch

import ingestion_admin
from schema_metadata import CLES_METADATA_OBLIGATOIRES


def chunk(article: str = "Article 1", date_publication="2025-10-18") -> dict:
    metadata = {
        "source": "Texte témoin",
        "type_norme": "loi",
        "rang": 30,
        "date": "2025-10-17",
        "date_publication": date_publication,
        "statut": "en_vigueur",
        "article": article,
        "abroge_par": None,
        "publication_abrogation": None,
        "date_abrogation": None,
        "article_modifie_par": None,
        "article_date_modification": None,
        "article_publication_modification": None,
        "moniteur_publication": None,
    }
    return {"page_content": f"{article}.- Texte.", "metadata": metadata}


class DatePublicationTests(unittest.TestCase):
    def raisons(self, item: dict) -> list[str]:
        erreurs, _, _ = ingestion_admin._valider_chunk(item, 0)
        return [erreur["raison"] for erreur in erreurs]

    def test_cle_obligatoire_et_date_valide(self):
        self.assertIn("date_publication", CLES_METADATA_OBLIGATOIRES)
        self.assertEqual(self.raisons(chunk()), [])

    def test_absence_est_rejetee(self):
        item = chunk()
        del item["metadata"]["date_publication"]
        self.assertIn(
            "Clé 'metadata.date_publication' absente", self.raisons(item)
        )

    def test_formats_et_dates_impossibles_sont_rejetes(self):
        for valeur in (None, "", "2025-1-8", "2025-02-30", 20251018, False):
            with self.subTest(valeur=valeur):
                self.assertTrue(
                    any(
                        "'metadata.date_publication' invalide" in raison
                        for raison in self.raisons(chunk(date_publication=valeur))
                    )
                )

    @patch.object(ingestion_admin, "_paires_existantes_en_base", return_value=set())
    def test_date_unique_par_source(self, _mock_base):
        donnees = [
            chunk("Article 1", "2025-10-18"),
            chunk("Article 2", "2025-10-19"),
        ]
        rapport = ingestion_admin._valider_donnees(donnees)
        self.assertFalse(rapport["valide"])
        self.assertTrue(
            any(
                "'date_publication' incohérente" in erreur["raison"]
                for erreur in rapport["erreurs"]
            )
        )

    @patch.object(ingestion_admin, "_paires_existantes_en_base", return_value=set())
    def test_resume_expose_la_date_publication(self, _mock_base):
        rapport = ingestion_admin._valider_donnees(
            [chunk("Article 1"), chunk("Article 2")]
        )
        self.assertTrue(rapport["valide"])
        self.assertEqual(
            rapport["resume_par_source"][0]["date_publication"], "2025-10-18"
        )


if __name__ == "__main__":
    unittest.main()
