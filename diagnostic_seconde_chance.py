from halex_core import _base, reformuler

# Requêtes courtes LÉGITIMES (doivent finir acceptées)
# vs Requêtes courtes INTRUSES (doivent finir rejetées)
courtes = [
    ("devise", "legitime"),
    ("nationalité", "legitime"),
    ("peine de mort", "legitime"),
    ("drapeau", "legitime"),
    ("riz collé", "intrus"),
    ("football", "intrus"),
    ("météo demain", "intrus"),
]

print(f"{'requête':<18} {'type':<10} {'score orig':<12} {'score reform':<12}")
print("-" * 55)
for requete, typ in courtes:
    s_orig = _base.similarity_search_with_score(requete, k=1)[0][1]
    s_reform = _base.similarity_search_with_score(reformuler(requete), k=1)[0][1]
    print(f"{requete:<18} {typ:<10} {s_orig:<12.3f} {s_reform:<12.3f}")