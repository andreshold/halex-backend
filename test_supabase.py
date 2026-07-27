import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY")

print("URL lue :", url)
print("Clé lue :", "oui" if key else "NON")

supabase = create_client(url, key)

# On demande combien de lignes dans la table documents (vide pour l'instant)
resultat = supabase.table("documents").select("*", count="exact").execute()
print("Connexion OK — nombre d'articles dans la base :", resultat.count)