from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

load_dotenv()
emb = OpenAIEmbeddings(model="text-embedding-3-small")
base = FAISS.load_local("faiss_index", emb, allow_dangerous_deserialization=True)

# Des questions DANS le domaine (doivent avoir un petit score)
# et HORS domaine (doivent avoir un grand score)
questions = [
    "Quelle est la devise nationale d'Haïti ?",  # phrase complète
    "devise d'Haïti",                            # mots-clés courts
    "devise",                                    # un seul mot
    "Qui peut devenir haïtien ?",                # phrase complète
    "nationalité haïtienne",                     # mots-clés courts
    "peine de mort",                             # mots-clés courts
]

for q in questions:
    meilleur = base.similarity_search_with_score(q, k=1)[0]
    score = meilleur[1]
    article = meilleur[0].metadata["article"]
    print(f"score={score:.3f}  | {q}  → {article}")