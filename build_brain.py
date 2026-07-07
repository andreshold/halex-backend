import json
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

# ① Charge la clé OPENAI_API_KEY depuis le fichier .env
#    (elle n'apparaît jamais dans le code — c'est le principe du coffre-fort)
load_dotenv()

# ② Charge vos 497 articles depuis le JSON validé
with open("documents/constitution_chunks.json", encoding="utf-8") as f:
    chunks = json.load(f)

# ③ Transforme chaque article en "Document" LangChain.
#    page_content = le texte que le cerveau va "comprendre".
#    metadata = la carte d'identité de l'article, qu'on garde attachée
#    pour pouvoir CITER la source exacte dans les réponses (exigence juridique).
documents = [
    Document(
        page_content=c["texte"],
        metadata={
            "article": c["article"],
            "source": c["source"],
            "contexte": c["contexte"],
            "section": c["section"],
        },
    )
    for c in chunks
]
print(f"→ {len(documents)} articles chargés. Génération des embeddings en cours...")

# ④ Le modèle qui traduit chaque texte en "position sur la carte de sens"
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

# ⑤ Construit la carte FAISS : appelle OpenAI pour les 497 articles d'un coup
base = FAISS.from_documents(documents, embeddings)

# ⑥ Sauvegarde la carte sur le disque pour ne PAYER les embeddings qu'UNE fois
base.save_local("faiss_index")
print(f"✅ Cerveau construit et sauvegardé : {len(documents)} articles indexés.")