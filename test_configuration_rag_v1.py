"""
Tests locaux de la configuration normative Halex RAG v1.0.
Aucun appel Supabase/OpenAI.
"""

from schema_metadata import RANGS_PAR_TYPE_NORME, VERSION_SCHEMA_RAG
from resolver_normatif import comparer


def doc(type_norme, date, statut="en_vigueur", date_publication="1900-01-01"):
    return {
        "metadata": {
            "type_norme": type_norme,
            "rang": RANGS_PAR_TYPE_NORME[type_norme],
            "date": date,
            "date_publication": date_publication,
            "statut": statut,
        }
    }


def main():
    assert VERSION_SCHEMA_RAG == "rag_juridique_v1.0"
    assert RANGS_PAR_TYPE_NORME == {
        "constitution": 10,
        "convention_ratifiee": 20,
        "loi": 30,
        "code": 30,
        "decret": 30,
        "arrete": 40,
        "circulaire": 50,
    }

    constitution = doc("constitution", "1987-03-29")
    code_recent = doc("code", "2099-01-01")
    r = comparer(constitution, code_recent)
    assert r["gagnant"] is constitution and r["raison"] == "rang"

    # Loi / Code / Décret : même force dans le modèle -> date juridique
    # uniquement si la contradiction a déjà été établie par la couche amont.
    loi = doc("loi", "2020-01-01")
    code = doc("code", "2021-01-01")
    decret = doc("decret", "2022-01-01")

    r = comparer(loi, code)
    assert r["gagnant"] is code and r["raison"] == "date"

    r = comparer(code, decret)
    assert r["gagnant"] is decret and r["raison"] == "date"

    # date_publication n'entre jamais dans la primauté.
    a = doc("code", "2026-10-10", date_publication="1825-01-01")
    b = doc("decret", "2026-10-10", date_publication="2026-01-01")
    r = comparer(a, b)
    assert r["gagnant"] is None and r["raison"] == "egalite_normative"

    non_applique = doc("constitution", "2099-01-01", "adopte_non_applique")
    applicable = doc("code", "2020-01-01", "en_vigueur")
    r = comparer(non_applique, applicable)
    assert r["gagnant"] is applicable and r["raison"] == "statut"

    print("OK — configuration normative Halex RAG v1.0")
    print("Constitution 10 > Convention 20 > Loi/Code/Décret 30 > Arrêté 40 > Circulaire 50")


if __name__ == "__main__":
    main()