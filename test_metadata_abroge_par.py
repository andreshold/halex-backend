import unittest
from unittest.mock import patch

import ingestion_admin
from halex_core_supabase import _construire_sources, _etiquette
from schema_metadata import (
    CLES_METADATA_AUTORISEES,
    CLES_METADATA_NULLABLES,
    CLES_METADATA_OBLIGATOIRES,
)


def chunk(
    article: str = "Article 1",
    *,
    statut: str = "en_vigueur",
    abroge_par=None,
    publication_abrogation=None,
    date_abrogation=None,
) -> dict:
    metadata = {
        "source": "Texte témoin",
        "type_norme": "loi",
        "rang": 30,
        "date": "2025-10-17",
        "date_publication": "2025-10-18",
        "statut": statut,
        "article": article,
        "abroge_par": abroge_par,
        "publication_abrogation": publication_abrogation,
        "date_abrogation": date_abrogation,
        "article_modifie_par": None,
        "article_date_modification": None,
        "article_publication_modification": None,
        "moniteur_publication": None,
    }
    return {"page_content": f"{article}.- Texte.", "metadata": metadata}


class ContratAbrogeParTests(unittest.TestCase):
    def raisons(self, item: dict) -> list[str]:
        erreurs, _, _ = ingestion_admin._valider_chunk(item, 0)
        return [erreur["raison"] for erreur in erreurs]

    def test_cles_appartiennent_au_contrat_obligatoire_nullable(self):
        for cle in (
            "abroge_par",
            "publication_abrogation",
            "date_abrogation",
        ):
            with self.subTest(cle=cle):
                self.assertIn(cle, CLES_METADATA_OBLIGATOIRES)
                self.assertIn(cle, CLES_METADATA_AUTORISEES)
                self.assertIn(cle, CLES_METADATA_NULLABLES)

    def test_null_est_accepte(self):
        self.assertEqual(self.raisons(chunk()), [])

    def test_absence_est_rejetee_pour_chaque_cle(self):
        for cle in ("abroge_par", "publication_abrogation", "date_abrogation"):
            with self.subTest(cle=cle):
                item = chunk()
                del item["metadata"][cle]
                self.assertIn(f"Clé 'metadata.{cle}' absente", self.raisons(item))

    def test_insertion_materialise_null_sans_ecraser_une_chaine(self):
        metadata_sans_cles = chunk()["metadata"]
        for cle in ("abroge_par", "publication_abrogation", "date_abrogation"):
            del metadata_sans_cles[cle]
        sans_cle = ingestion_admin._preparer_metadata_insertion(metadata_sans_cles)
        for cle in (
            "abroge_par",
            "publication_abrogation",
            "date_abrogation",
        ):
            self.assertIn(cle, sans_cle)
            self.assertIsNone(sans_cle[cle])

        valeur = "Par la loi du 17 octobre 2025"
        avec_chaine = ingestion_admin._preparer_metadata_insertion(
            chunk(
                statut="abroge",
                abroge_par=valeur,
                publication_abrogation="Le Moniteur spécial no 7",
                date_abrogation="2025-10-17",
            )["metadata"]
        )
        self.assertEqual(avec_chaine["abroge_par"], valeur)
        self.assertEqual(
            avec_chaine["publication_abrogation"], "Le Moniteur spécial no 7"
        )
        self.assertEqual(avec_chaine["date_abrogation"], "2025-10-17")

    def test_valeurs_valides_sont_acceptees_pour_un_texte_abroge(self):
        item = chunk(
            statut="abroge",
            abroge_par="Par la loi du 17 octobre 2025",
            publication_abrogation="Le Moniteur spécial no 7",
            date_abrogation="2025-10-17",
        )
        self.assertEqual(self.raisons(item), [])

    def test_types_invalides_et_chaine_vide_sont_rejetes(self):
        for valeur in ("", "   ", 17, False, [], {}):
            with self.subTest(valeur=valeur):
                raisons = self.raisons(chunk(statut="abroge", abroge_par=valeur))
                self.assertTrue(any("null ou une chaîne non vide" in r for r in raisons))

        for valeur in ("", "   ", 17, False, [], {}):
            with self.subTest(publication_abrogation=valeur):
                raisons = self.raisons(
                    chunk(statut="abroge", publication_abrogation=valeur)
                )
                self.assertTrue(any("null ou une chaîne non vide" in r for r in raisons))

    def test_date_abrogation_invalide_est_rejetee(self):
        for valeur in ("", "2025-1-7", "2025-02-30", 20251017, False, []):
            with self.subTest(date_abrogation=valeur):
                raisons = self.raisons(
                    chunk(statut="abroge", date_abrogation=valeur)
                )
                self.assertTrue(any("date réelle" in r for r in raisons))

    def test_chaine_est_rejetee_si_le_statut_n_est_pas_abroge(self):
        raisons = self.raisons(
            chunk(
                publication_abrogation="Le Moniteur spécial no 7",
                date_abrogation="2025-10-17",
            )
        )
        self.assertTrue(any("statut' vaut 'abroge" in r for r in raisons))

    @patch.object(ingestion_admin, "_paires_existantes_en_base", return_value=set())
    def test_valeur_peut_varier_par_article(self, _mock_base):
        donnees = [
            chunk("Article 1", statut="abroge", abroge_par=None),
            chunk(
                "Article 2",
                statut="abroge",
                abroge_par="Par la loi du 17 octobre 2025",
            ),
        ]
        rapport = ingestion_admin._valider_donnees(donnees)
        self.assertTrue(rapport["valide"])

    @patch.object(ingestion_admin, "_paires_existantes_en_base", return_value=set())
    def test_publication_et_date_peuvent_varier_par_article(self, _mock_base):
        donnees = [
            chunk(
                "Article 1",
                statut="abroge",
                publication_abrogation="Le Moniteur no 7",
                date_abrogation="2025-10-17",
            ),
            chunk(
                "Article 2",
                statut="abroge",
                publication_abrogation="Le Moniteur no 8",
                date_abrogation="2025-10-18",
            ),
        ]
        rapport = ingestion_admin._valider_donnees(donnees)
        self.assertTrue(rapport["valide"])

    @patch.object(ingestion_admin, "_paires_existantes_en_base", return_value=set())
    def test_resume_expose_la_repartition_des_statuts(self, _mock_base):
        valeur = "Par la loi du 17 octobre 2025"
        donnees = [
            chunk(
                "Article 1",
                statut="abroge",
                abroge_par=valeur,
                publication_abrogation="Le Moniteur spécial no 7",
                date_abrogation="2025-10-17",
            ),
            chunk(
                "Article 2",
                statut="abroge",
                abroge_par=valeur,
                publication_abrogation="Le Moniteur spécial no 7",
                date_abrogation="2025-10-17",
            ),
        ]
        rapport = ingestion_admin._valider_donnees(donnees)
        self.assertTrue(rapport["valide"])
        self.assertEqual(rapport["resume_par_source"][0]["nb_par_statut"], {"abroge": 2})


class PropagationAbrogeParTests(unittest.TestCase):
    def test_etiquette_juridique_affiche_le_texte_abrogeant(self):
        metadata = chunk(
            statut="abroge",
            abroge_par="Par la loi du 17 octobre 2025",
            publication_abrogation="Le Moniteur spécial no 7",
            date_abrogation="2025-10-17",
        )["metadata"]
        etiquette = _etiquette(metadata)
        self.assertIn("abrogé (Par la loi du 17 octobre 2025 ;", etiquette)
        self.assertIn("publication : Le Moniteur spécial no 7", etiquette)
        self.assertIn("date d’abrogation : 2025-10-17", etiquette)

    def test_sources_api_conservent_statut_et_abroge_par(self):
        valeur = "Par la loi du 17 octobre 2025"
        item = chunk(
            statut="abroge",
            abroge_par=valeur,
            publication_abrogation="Le Moniteur spécial no 7",
            date_abrogation="2025-10-17",
        )
        article = {
            "content": item["page_content"],
            "metadata": item["metadata"],
        }
        sources = _construire_sources([article])
        self.assertEqual(sources[0]["statut"], "abroge")
        self.assertEqual(sources[0]["date"], "2025-10-17")
        self.assertEqual(sources[0]["date_publication"], "2025-10-18")
        self.assertEqual(sources[0]["abroge_par"], valeur)
        self.assertEqual(
            sources[0]["publication_abrogation"], "Le Moniteur spécial no 7"
        )
        self.assertEqual(sources[0]["date_abrogation"], "2025-10-17")


if __name__ == "__main__":
    unittest.main()
