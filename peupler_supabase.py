"""
peupler_supabase.py
Transfère le contenu de l'index FAISS (textes, métadonnées, embeddings)
vers la table 'documents' de Supabase. Non destructif : FAISS reste intact.
Aucun appel OpenAI : les embeddings existants sont réutilisés.
"""

import os
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from supabase import create_client

load_dotenv()

# 1. Charger le cerveau FAISS existant
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
base = FAISS.load_local(
    "faiss_index", embeddings, allow_dangerous_deserialization=True
)

# 2. Connexion Supabase
supabase = create_client(
    os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
)

# 3. Extraire chaque article + son vecteur déjà calculé
lignes = []
for position, doc_id in base.index_to_docstore_id.items():
    doc = base.docstore.search(doc_id)
    vecteur = base.index.reconstruct(int(position))  # embedding existant
    lignes.append({
        "content": doc.page_content,
        "metadata": doc.metadata,
        "embedding": vecteur.tolist(),
    })

print(f"{len(lignes)} articles extraits de FAISS.")

# 4. Insérer par paquets de 50 (évite les requêtes trop lourdes)
TAILLE_PAQUET = 50
for i in range(0, len(lignes), TAILLE_PAQUET):
    paquet = lignes[i : i + TAILLE_PAQUET]
    supabase.table("documents").insert(paquet).execute()
    print(f"  Insérés : {min(i + TAILLE_PAQUET, len(lignes))}/{len(lignes)}")

print("Terminé — vérification…")
total = supabase.table("documents").select("*", count="exact").execute()
print(f"La table Supabase contient maintenant {total.count} articles.")