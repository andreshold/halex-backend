#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_modifications.py
=====================
Test EN ISOLATION de modifications.py, avant toute intégration au core.

Ne touche à aucun fichier protégé. Crée son propre client Supabase depuis
.env : le core n'est jamais importé, donc une erreur ici ne peut rien
casser en production.

Usage : python test_modifications.py
"""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv
from supabase import create_client

from modifications import (
    charger_registre,
    enrichir_modifications,
    formater_bloc_prompt,
)

# Les avertissements du module sont la moitié de l'information : sans
# cette ligne, un échec silencieux ressemblerait à un succès vide.
logging.basicConfig(level=logging.INFO, format="  [%(levelname)s] %(message)s")

# --- cas de test ----------------------------------------------------------
SOURCE_CODE = "Code du travail (2003)"
ARTICLE_MODIFIE = "Article 257"      # modifié par la loi de 2009
ARTICLE_TEMOIN = "Article 100"       # non modifié -> contrôle de non-régression


def client_supabase():
    load_dotenv()
    url = os.getenv("SUPABASE_URL")
    # Ordre de préférence : la clé service contourne RLS, utile pour
    # distinguer « table vide » de « lecture bloquée par RLS ».
    cle = (os.getenv("SUPABASE_SERVICE_KEY")
           or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
           or os.getenv("SUPABASE_KEY")
           or os.getenv("SUPABASE_ANON_KEY"))
    if not url or not cle:
        sys.exit("ERREUR : SUPABASE_URL / clé introuvables dans .env")
    return create_client(url, cle)


def faux_chunk(source: str, article: str) -> dict:
    """Reproduit la forme d'un chunk sorti de match_documents."""
    return {
        "page_content": f"{article}. [contenu factice pour le test]",
        "metadata": {"source": source, "article": article},
    }


def afficher(chunks: list) -> None:
    for c in chunks:
        meta = c.get("metadata", {})
        print(f"      - {meta.get('article'):<12} | {meta.get('source')}")


def main() -> None:
    client = client_supabase()

    # --- 0. Prérequis : le registre est-il lisible ? ----------------------
    print("\n[0] Registre")
    par_libelle, par_id = charger_registre(client)
    if not par_libelle:
        sys.exit(
            "      VIDE ou illisible.\n"
            "      Deux causes possibles :\n"
            "        - sources_registre n'a pas ete peuple ;\n"
            "        - RLS actif sans policy de lecture sur les deux\n"
            "          nouvelles tables (verifier avec la cle service)."
        )
    print(f"      {len(par_libelle)} source(s) enregistree(s) :")
    for libelle, slug in sorted(par_libelle.items(), key=lambda x: x[1]):
        print(f"      - {slug:<26} | {libelle}")

    if SOURCE_CODE not in par_libelle:
        sys.exit(f"      ERREUR : '{SOURCE_CODE}' absent du registre. "
                 f"Le libelle doit correspondre au caractere pres.")

    # --- 1. Article modifie ----------------------------------------------
    print(f"\n[1] {ARTICLE_MODIFIE} — attendu : 2 chunks, 1 relation")
    entree = [faux_chunk(SOURCE_CODE, ARTICLE_MODIFIE)]
    enrichis, relations = enrichir_modifications(client, entree)
    print(f"      {len(enrichis)} chunk(s), {len(relations)} relation(s)")
    afficher(enrichis)

    ok_1 = len(enrichis) == 2 and len(relations) == 1
    print("      -> OK" if ok_1 else "      -> ECHEC")

    if relations:
        print("\n      Bloc de prompt genere :")
        for ligne in formater_bloc_prompt(relations, par_id).splitlines():
            print(f"      | {ligne}")

    # --- 2. Article temoin : non-regression -------------------------------
    print(f"\n[2] {ARTICLE_TEMOIN} — attendu : 1 chunk, 0 relation, bloc vide")
    entree = [faux_chunk(SOURCE_CODE, ARTICLE_TEMOIN)]
    enrichis, relations = enrichir_modifications(client, entree)
    bloc = formater_bloc_prompt(relations, par_id)
    print(f"      {len(enrichis)} chunk(s), {len(relations)} relation(s), "
          f"bloc de {len(bloc)} caractere(s)")
    ok_2 = len(enrichis) == 1 and not relations and bloc == ""
    print("      -> OK" if ok_2 else "      -> ECHEC")

    # --- 3. Lot mixte ------------------------------------------------------
    print("\n[3] Lot mixte (temoin + modifie) — attendu : 3 chunks, "
          "ordre d'entree preserve")
    entree = [faux_chunk(SOURCE_CODE, ARTICLE_TEMOIN),
              faux_chunk(SOURCE_CODE, ARTICLE_MODIFIE)]
    enrichis, relations = enrichir_modifications(client, entree)
    print(f"      {len(enrichis)} chunk(s), {len(relations)} relation(s)")
    afficher(enrichis)
    ordre_ok = (enrichis[0]["metadata"]["article"] == ARTICLE_TEMOIN
                and enrichis[1]["metadata"]["article"] == ARTICLE_MODIFIE)
    ok_3 = len(enrichis) == 3 and ordre_ok
    print("      -> OK" if ok_3 else "      -> ECHEC")

    # --- 4. Idempotence ----------------------------------------------------
    print("\n[4] Double passage — attendu : aucun doublon ajoute")
    encore, _ = enrichir_modifications(client, enrichis)
    print(f"      {len(encore)} chunk(s) (identique a l'etape 3)")
    ok_4 = len(encore) == len(enrichis)
    print("      -> OK" if ok_4 else "      -> ECHEC")

    # --- 5. Entree vide ----------------------------------------------------
    print("\n[5] Entree vide — attendu : aucune exception")
    vide, rel_vide = enrichir_modifications(client, [])
    ok_5 = vide == [] and rel_vide == []
    print("      -> OK" if ok_5 else "      -> ECHEC")

    print("\n" + "=" * 60)
    total = [ok_1, ok_2, ok_3, ok_4, ok_5]
    print(f"{sum(total)}/{len(total)} test(s) reussi(s)")
    if not all(total):
        sys.exit("Integration au core INTERDITE tant que tout n'est pas vert.")
    print("Module valide. Integration au core possible.")


if __name__ == "__main__":
    main()
