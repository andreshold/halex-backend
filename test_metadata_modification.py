"""Tests du statut modifié et des métadonnées de modification d'article."""

import copy
import unittest

import ingestion_admin


def chunk() -> dict:
    return {
        "page_content": "Article 257 :\n\nTexte.",
        "metadata": {
            "source": "Code du travail haïtien",
            "type_norme": "code",
            "rang": 40,
            "date": "2017-09-21",
            "date_publication": "1961-09-12",
            "statut": "en_vigueur",
            "article": "Article 257",
            "abroge_par": None,
            "publication_abrogation": None,
            "date_abrogation": None,
            "article_modifie_par": None,
            "article_date_modification": None,
            "article_publication_modification": None,
            "moniteur_publication": None,
        },
    }


class ModificationMetadataTests(unittest.TestCase):
    def setUp(self):
        ingestion_admin._paires_existantes_en_base = lambda _sources: set()

    def test_null_est_accepte(self):
        self.assertTrue(ingestion_admin._valider_donnees([chunk()])["valide"])

    def test_statut_modifie_et_valeurs_sont_acceptes(self):
        item = chunk()
        item["metadata"].update(
            statut="modifie",
            article_modifie_par="Loi no CL-05-2009-006 du 6 mai 2009",
            article_date_modification="2009-05-06",
            article_publication_modification="Le Moniteur, no 1",
        )
        self.assertTrue(ingestion_admin._valider_donnees([item])["valide"])

    def test_cles_absentes_sont_rejetees(self):
        for key in ("article_modifie_par", "article_date_modification", "article_publication_modification"):
            item = copy.deepcopy(chunk())
            del item["metadata"][key]
            self.assertFalse(ingestion_admin._valider_donnees([item])["valide"])

    def test_valeurs_exigent_le_statut_modifie(self):
        item = chunk()
        item["metadata"]["article_modifie_par"] = "Une loi"
        item["metadata"]["article_date_modification"] = "2009-05-06"
        item["metadata"]["article_publication_modification"] = "Le Moniteur"
        self.assertFalse(ingestion_admin._valider_donnees([item])["valide"])

    def test_date_invalide_est_rejetee(self):
        item = chunk()
        item["metadata"].update(
            statut="modifie",
            article_modifie_par="Une loi",
            article_date_modification="2009-02-30",
            article_publication_modification="Le Moniteur",
        )
        self.assertFalse(ingestion_admin._valider_donnees([item])["valide"])


if __name__ == "__main__":
    unittest.main()
