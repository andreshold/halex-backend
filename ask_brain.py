from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

# ① Charge la clé depuis .env (nécessaire : la QUESTION aussi doit être
#    traduite en position sur la carte, via OpenAI)
load_dotenv()

# ② Recharge la carte de sens depuis le disque — AUCUN nouvel embedding
#    des articles n'est payé : ils sont déjà calculés et sauvegardés.
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
base = FAISS.load_local(
    "faiss_index",
    embeddings,
    allow_dangerous_deserialization=True,  # requis pour recharger NOTRE propre fichier local (sans danger ici)
)

# ③ Votre question de test
question = "Quel est le prix d'un passeport haïtien ?"

# ④ Cherche les 3 articles les plus PROCHES de la question sur la carte
resultats = base.similarity_search(question, k=3)

# ⑤ Affiche ce que le cerveau a retrouvé, avec les métadonnées
print(f"\nQuestion : {question}\n")
for i, doc in enumerate(resultats, start=1):
    print(f"--- Résultat {i} ---")
    print(f"Article  : {doc.metadata['article']}")
    print(f"Contexte : {doc.metadata['contexte']}")
    print(f"Texte    : {doc.page_content[:200]}...")
    print()