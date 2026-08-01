"""
generer_fichiers_checklist.py
Génère les 9 fichiers JSON de la checklist manuelle de validation des
métadonnées Moniteur (règle tout-ou-rien) et de source_courte, dans
tests_ingestion/checklist/. Aucune dépendance à FastAPI/Supabase/OpenAI.
"""

import json
import unicodedata
from pathlib import Path

DOSSIER = Path(__file__).parent


def base_metadata(article="Article 42-1"):
    return {
        "source": "Loi fixant les règles générales relatives aux marchés publics...",
        "type_norme": "loi",
        "rang": 2,
        "date": "2009-07-28",
        "statut": "en_vigueur",
        "article": article,
        "titre": "Titre III",
        "chapitre": "Chapitre 2",
        "section": "Section 1",
    }


def chunk(article="Article 42-1", metadata_extra=None):
    metadata = base_metadata(article)
    if metadata_extra:
        metadata.update(metadata_extra)
    return {
        "page_content": f"Contenu de test pour {article}.",
        "metadata": metadata,
    }


def ecrire(nom, donnees):
    chemin = DOSSIER / nom
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(donnees, f, ensure_ascii=False, indent=2)
    print(f"Écrit : {chemin}")


def main():
    # 1. Moniteur complet
    ecrire("01_avec_moniteur.json", [
        chunk("Article 42-1", {
            "moniteur_annee": 2009,
            "moniteur_numero": "78",
            "moniteur_type": "extraordinaire",
        })
    ])

    # 2. Sans aucune clé moniteur_*
    ecrire("02_sans_moniteur.json", [
        chunk("Article 42-1")
    ])

    # 3. Moniteur incomplet (moniteur_annee seul)
    ecrire("03_moniteur_incomplet.json", [
        chunk("Article 42-1", {
            "moniteur_annee": 2009,
        })
    ])

    # 4. Typo sur moniteur_type (espace final)
    ecrire("04_moniteur_typo.json", [
        chunk("Article 42-1", {
            "moniteur_annee": 2009,
            "moniteur_numero": "78",
            "moniteur_type": "spécial ",
        })
    ])

    # 5. Clé inconnue "contexte"
    ecrire("05_cle_inconnue.json", [
        chunk("Article 42-1", {
            "moniteur_annee": 2009,
            "moniteur_numero": "78",
            "moniteur_type": "extraordinaire",
            "contexte": "TITRE III",
        })
    ])

    # 6. source_courte renseignée
    ecrire("06_source_courte_ok.json", [
        chunk("Article 42-1", {
            "moniteur_annee": 2009,
            "moniteur_numero": "78",
            "moniteur_type": "extraordinaire",
            "source_courte": "Loi sur les marchés publics (2009)",
        })
    ])

    # 7. source_courte vide
    ecrire("07_source_courte_vide.json", [
        chunk("Article 42-1", {
            "moniteur_annee": 2009,
            "moniteur_numero": "78",
            "moniteur_type": "extraordinaire",
            "source_courte": "",
        })
    ])

    # 8. moniteur_type en forme NFD (unicode)
    ecrire("08_nfd.json", [
        chunk("Article 42-1", {
            "moniteur_annee": 2009,
            "moniteur_numero": "78",
            "moniteur_type": unicodedata.normalize("NFD", "spécial"),
        })
    ])

    # 9. Liste mixte de 3 chunks : deux avec moniteur complet (articles
    # différents), un sans aucune clé moniteur -> nb_chunks_sans_moniteur == 1
    ecrire("09_mixte.json", [
        chunk("Article 42-1", {
            "moniteur_annee": 2009,
            "moniteur_numero": "78",
            "moniteur_type": "extraordinaire",
        }),
        chunk("Article 42-2", {
            "moniteur_annee": 2009,
            "moniteur_numero": "78",
            "moniteur_type": "extraordinaire",
        }),
        chunk("Article 42-3"),
    ])


if __name__ == "__main__":
    main()
