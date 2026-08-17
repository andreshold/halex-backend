"""Tests du contrat unifié de publication au Moniteur."""

import unittest

import ingestion_admin
from schema_metadata import CLES_METADATA_OBLIGATOIRES, CLES_METADATA_NULLABLES


def chunk(value=None):
    return {
        "page_content": "Article 1 :\n\nTexte.",
        "metadata": {
            "source": "Texte témoin", "type_norme": "loi", "rang": 30,
            "date": "2017-09-21", "date_publication": "2017-09-21",
            "statut": "en_vigueur", "article": "Article 1",
            "abroge_par": None, "publication_abrogation": None, "date_abrogation": None,
            "article_modifie_par": None, "article_date_modification": None,
            "article_publication_modification": None,
            "moniteur_publication": value,
        },
    }


class MoniteurPublicationTests(unittest.TestCase):
    def setUp(self):
        ingestion_admin._paires_existantes_en_base = lambda _sources: set()

    def test_cle_obligatoire_nullable(self):
        self.assertIn("moniteur_publication", CLES_METADATA_OBLIGATOIRES)
        self.assertIn("moniteur_publication", CLES_METADATA_NULLABLES)
        self.assertTrue(ingestion_admin._valider_donnees([chunk()])["valide"])

    def test_reference_complete_acceptee(self):
        value = "Le Moniteur, 172e année, Spécial no 29, 21 septembre 2017"
        self.assertTrue(ingestion_admin._valider_donnees([chunk(value)])["valide"])

    def test_chaine_vide_et_anciens_champs_rejetes(self):
        self.assertFalse(ingestion_admin._valider_donnees([chunk("")])["valide"])
        item = chunk()
        item["metadata"]["moniteur_annee"] = 172
        self.assertFalse(ingestion_admin._valider_donnees([item])["valide"])


if __name__ == "__main__":
    unittest.main()
