from halex_core_supabase import poser_question

for q in [
    "Quelle est la devise nationale d'Haïti ?",
    "Que dit le Code pénal sur le vol ?",
    "Quelle est la recette du griot ?",   # doit sortir : hors domaine
]:
    r = poser_question(q)
    print("=" * 60)
    print("Q :", q)
    print("Hors domaine :", r["hors_domaine"])
    print(r["reponse"][:400])
    print()