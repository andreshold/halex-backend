"""
auth_admin.py
Dépendance FastAPI réutilisable qui vérifie qu'une requête provient d'un
utilisateur authentifié avec role = 'admin' dans public.profils.
"""

import os

from dotenv import load_dotenv
from fastapi import Header, HTTPException
from supabase import create_client

load_dotenv()

# Client dédié, indépendant de celui de halex_core_supabase.py.
# Utilise la clé service_role : nécessaire pour lire le profil de
# n'importe quel utilisateur malgré la RLS sur public.profils.
_supabase_admin = create_client(
    os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
)


def verifier_admin(authorization: str | None = Header(None)) -> dict:
    """Dépendance FastAPI : lève 401 si le token Bearer est absent ou
    invalide, 403 si l'utilisateur authentifié n'a pas role='admin' dans
    public.profils. Retourne {"id": ..., "email": ...} si admin."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token d'authentification manquant")

    token = authorization.removeprefix("Bearer ").strip()

    try:
        reponse_auth = _supabase_admin.auth.get_user(token)
        utilisateur = reponse_auth.user
    except Exception:
        utilisateur = None

    if utilisateur is None:
        raise HTTPException(status_code=401, detail="Token d'authentification invalide")

    resultat_profil = (
        _supabase_admin.table("profils")
        .select("role")
        .eq("user_id", utilisateur.id)
        .execute()
    )

    lignes = resultat_profil.data or []
    role = lignes[0]["role"] if lignes else None

    if role != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")

    return {"id": utilisateur.id, "email": utilisateur.email}
