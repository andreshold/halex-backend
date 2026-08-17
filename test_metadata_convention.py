import unittest
import ingestion_admin


def chunk(type_norme="convention_ratifiee"):
    meta = {
        "source": "Pacte témoin", "type_norme": type_norme,
        "rang": 20 if type_norme == "convention_ratifiee" else 30,
        "date": "1991-01-07", "date_publication": "1966-12-15",
        "statut": "en_vigueur", "article": "Article 1",
        "abroge_par": None, "publication_abrogation": None, "date_abrogation": None,
        "article_modifie_par": None, "article_date_modification": None,
        "article_publication_modification": None, "moniteur_publication": None,
        "convention_date_adoption": "1966-12-15",
        "convention_date_ratification": "1991-01-07",
    }
    return {"page_content": "Article 1 :\n\nTexte.", "metadata": meta}


class ConventionMetadataTests(unittest.TestCase):
    def setUp(self): ingestion_admin._paires_existantes_en_base = lambda _: set()

    def test_dates_obligatoires_non_nulles(self):
        self.assertTrue(ingestion_admin._valider_donnees([chunk()])["valide"])
        for key in ("convention_date_adoption", "convention_date_ratification"):
            item = chunk(); item["metadata"][key] = None
            self.assertFalse(ingestion_admin._valider_donnees([item])["valide"])

    def test_interdites_aux_autres_normes(self):
        self.assertFalse(ingestion_admin._valider_donnees([chunk("loi")])["valide"])


if __name__ == "__main__": unittest.main()
