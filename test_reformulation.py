from halex_core import reformuler, _base

for requete in ["devise", "devise d'Haïti", "peine de mort", "nationalité"]:
    question = reformuler(requete)
    score = _base.similarity_search_with_score(question, k=1)[0][1]
    print(f"'{requete}' → '{question}'  (score={score:.3f})")