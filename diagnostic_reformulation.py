from halex_core import _base, reformuler

tests = [
    "Quelle est la devise nationale d'Haïti ?",
    "devise",
    "Quelle est la recette du riz collé ?",
]

for requete in tests:
    reform = reformuler(requete)
    # score de la requête ORIGINALE
    s_orig = _base.similarity_search_with_score(requete, k=1)[0]
    # score de la requête REFORMULÉE
    s_reform = _base.similarity_search_with_score(reform, k=1)[0]
    print(f"\nRequête : '{requete}'")
    print(f"  ORIGINALE  → {s_orig[0].metadata['article']:12} score={s_orig[1]:.3f}")
    print(f"  REFORMULÉE → '{reform[:60]}...'")
    print(f"               {s_reform[0].metadata['article']:12} score={s_reform[1]:.3f}")