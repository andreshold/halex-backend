"""
lancer_validation.py
Exécute les 9 fichiers de la checklist à travers exactement le même pipeline
que /admin/validation (décodage UTF-8, normalisation NFC, parsing JSON, puis
_valider_donnees) — sans passer par FastAPI/HTTPBearer, faute de jeton admin
Supabase disponible dans cet environnement. _valider_donnees interroge la
table `documents` en lecture seule (recherche de doublons en base) ; aucune
écriture n'a lieu, exactement comme le endpoint réel.
"""

import json
import unicodedata
from pathlib import Path

from ingestion_admin import _valider_donnees

DOSSIER = Path(__file__).parent

FICHIERS = [
    "01_avec_moniteur.json",
    "02_sans_moniteur.json",
    "03_moniteur_incomplet.json",
    "04_moniteur_typo.json",
    "05_cle_inconnue.json",
    "06_source_courte_ok.json",
    "07_source_courte_vide.json",
    "08_nfd.json",
    "09_mixte.json",
]


def lire_comme_le_endpoint(chemin: Path) -> list:
    """Reproduit _lire_et_parser_fichier : décodage UTF-8 strict puis
    normalisation NFC AVANT le parsing JSON (c'est cette étape qui rend le
    fichier 08_nfd.json valide malgré son moniteur_type en forme NFD)."""
    contenu = chemin.read_bytes()
    texte = contenu.decode("utf-8", errors="strict")
    texte = unicodedata.normalize("NFC", texte)
    return json.loads(texte)


def main():
    for nom in FICHIERS:
        chemin = DOSSIER / nom
        donnees = lire_comme_le_endpoint(chemin)
        rapport = _valider_donnees(donnees)

        print("=" * 70)
        print(nom)
        print(f"  valide              : {rapport['valide']}")
        print(f"  pret_pour_insertion : {rapport['pret_pour_insertion']}")
        print(f"  nb_chunks_total     : {rapport['nb_chunks_total']}")
        print(f"  nb_chunks_valides   : {rapport['nb_chunks_valides']}")
        if rapport["erreurs"]:
            print("  erreurs :")
            for e in rapport["erreurs"]:
                print(f"    - [{e['index']}] {e['article']!r} : {e['raison']}")
        if rapport["doublons_internes"]:
            print("  doublons_internes :", rapport["doublons_internes"])
        if rapport["doublons_en_base"]:
            print("  doublons_en_base :", rapport["doublons_en_base"])
        for resume in rapport["resume_par_source"]:
            print(
                "  resume_par_source   : nb_chunks="
                f"{resume['nb_chunks']}, nb_chunks_sans_moniteur="
                f"{resume['nb_chunks_sans_moniteur']}, source_courte="
                f"{resume['source_courte']!r}"
            )
    print("=" * 70)


if __name__ == "__main__":
    main()
