"""
test_recherche_supabase.py
Vérifie que la recherche par similarité fonctionne dans Supabase :
embed d'une question réelle, appel de match_documents, affichage des résultats.
"""

import os
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from supabase import create_client

load_dotenv()

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
supabase = create_client(
    os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
)

question = "Quelle est la devise nationale d'Haïti ?"
vecteur = embeddings.embed_query(question)

resultat = supabase.rpc(
    "match_documents",
    {"query_embedding": vecteur, "match_count": 3},
).execute()

print(f"Question : {question}\n")
for ligne in resultat.data:
    meta = ligne["metadata"]
    print(f"— {meta.get('source', '?')} | {meta.get('article', '?')} "
          f"| similarité : {ligne['similarity']:.3f}")
    print(f"  {ligne['content'][:150]}...\n")