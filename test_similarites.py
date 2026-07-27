from halex_core_supabase import _chercher

for mot in ["vol", "bitcoin", "meurtre", "drapeau", "football"]:
    resultats = _chercher(mot, k=3)
    print(f"\n=== {mot} ===")
    for r in resultats:
        print(f"  {r['similarity']:.3f}  {r['metadata'].get('article')}  {r['metadata'].get('source')}")