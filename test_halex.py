"""Batterie de tests de Halex. Lancer avec : pytest -v"""
from halex_core import poser_question


# --- Famille 1 : les bonnes réponses ne doivent pas se casser ---

def test_devise_trouve_article_4():
    resultat = poser_question("Quelle est la devise nationale d'Haïti ?")
    articles = [s["article"] for s in resultat["sources"]]
    assert "Article 4" in articles
    assert resultat["hors_domaine"] is False


def test_nationalite_trouve_article_pertinent():
    resultat = poser_question("Qui peut devenir haïtien ?")
    articles = [s["article"] for s in resultat["sources"]]
    # L'un des articles sur la nationalité doit apparaître
    assert any(a in articles for a in ["Article 11", "Article 12", "Article 13"])
    assert resultat["hors_domaine"] is False


# --- Famille 2 : le garde-fou de seuil doit rejeter le hors-domaine ---

def test_question_hors_domaine_est_refusee():
    resultat = poser_question("Quelle est la recette du riz collé ?")
    assert resultat["hors_domaine"] is True
    assert resultat["sources"] == []


# --- Famille 3 : robustesse aux requêtes courtes (le bug qu'on a corrigé) ---

def test_mot_seul_demande_une_precision():
    # Décision produit : Halex n'est pas un dictionnaire. Un mot isolé
    # déclenche une demande de reformulation, pas une devinette.
    resultat = poser_question("devise")
    assert resultat["demande_precision"] is True
    assert resultat["sources"] == []

def test_intrus_court_est_refuse():
    # "riz collé" (2 mots) doit être rejeté MÊME avec la seconde chance
    resultat = poser_question("riz collé")
    assert resultat["hors_domaine"] is True


def test_legitime_limite_est_accepte():
    # "peine de mort" est le légitime au score le plus haut (0.877) : il doit passer
    resultat = poser_question("peine de mort")
    assert resultat["hors_domaine"] is False   