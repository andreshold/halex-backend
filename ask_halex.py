from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate

# ① Clé API depuis .env
load_dotenv()

# ② Recharge la carte de sens (aucun embedding d'article repayé)
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
base = FAISS.load_local(
    "faiss_index", embeddings, allow_dangerous_deserialization=True
)

# ③ Le "retriever" : le bras du cerveau qui va chercher les 4 articles
#    les plus pertinents pour chaque question
retriever = base.as_retriever(search_kwargs={"k": 4})

# ④ Les INSTRUCTIONS données au modèle — le cœur juridique de Halex.
#    C'est ici qu'on impose : réponse basée UNIQUEMENT sur les articles,
#    citations obligatoires, honnêteté si l'information manque.
prompt = ChatPromptTemplate.from_template(
    """Tu es Halex, un assistant juridique spécialisé dans le droit haïtien.
Ta mission : expliquer la loi aux citoyens en français simple et clair.

RÈGLES STRICTES :
1. Réponds UNIQUEMENT à partir des articles fournis ci-dessous.
2. Cite toujours les articles sur lesquels tu t'appuies (ex: "selon l'Article 4...").
3. Si les articles fournis ne permettent pas de répondre, dis-le honnêtement
   et suggère de consulter un professionnel du droit.
4. Ne donne jamais de conseil juridique personnalisé : tu expliques ce que dit la loi.

ARTICLES DE LA CONSTITUTION :
{contexte}

QUESTION DU CITOYEN :
{question}

RÉPONSE (en français clair, avec citations) :"""
)

# ⑤ Le modèle qui rédige (gpt-4o-mini : rapide et économique)
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# ⑥ La question de test
question = "Quel est le prix d'un passeport haïtien ?"

# ⑦ La chaîne complète : chercher → assembler → rédiger
articles = retriever.invoke(question)
contexte = "\n\n".join(
    f"[{d.metadata['article']} — {d.metadata['contexte']}]\n{d.page_content}"
    for d in articles
)
reponse = llm.invoke(prompt.format(contexte=contexte, question=question))

print(f"\nQuestion : {question}\n")
print("Réponse de Halex :\n")
print(reponse.content)
print("\n--- Articles consultés ---")
for d in articles:
    print(f"• {d.metadata['article']} ({d.metadata['contexte']})")