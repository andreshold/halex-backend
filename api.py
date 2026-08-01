"""
api.py
Porte d'entrée HTTP de Halex : expose le moteur (halex_core_supabase)
sous forme d'API REST. C'est ce que le frontend Next.js appellera.
"""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from auth_admin import verifier_admin
from halex_core_supabase import (
    poser_question,
    lookup_article,
    article_du_jour,
    archives_article_du_jour,
    MODE_PAR_DEFAUT,
    INSTRUCTIONS_MODES,
)
from ingestion_admin import router as ingestion_router

app = FastAPI(
    title="Halex API",
    description="Assistant juridique haïtien",
    version="1.0.0",
)

# CORS : autorise le frontend (autre domaine) à appeler cette API.
# Pour l'instant ouvert à tous ("*") pour le développement ;
# on restreindra au domaine réel du frontend avant la mise en production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingestion_router)


class Question(BaseModel):
    """Format attendu dans le corps de la requête. numero_article et
    source_choisie sont optionnels : quand les deux sont fournis (ex. suite
    à une clarification de lookup direct), l'article est recherché
    directement sans repasser par la détection sur le texte de la question."""
    question: str
    numero_article: str | None = None
    source_choisie: str | None = None
    mode: str = "citoyen"

    @field_validator("mode")
    @classmethod
    def _mode_valide(cls, valeur: str) -> str:
        """Dégradation silencieuse vers le mode par défaut : jamais de 422
        pour un mode inconnu (ex. valeur obsolète côté frontend)."""
        return valeur if valeur in INSTRUCTIONS_MODES else MODE_PAR_DEFAUT


class SourceItem(BaseModel):
    """Un article cité, tel qu'affiché dans une puce de source côté frontend."""
    article: str
    source: str
    source_courte: str | None = None
    texte: str


class ReponseHalex(BaseModel):
    """Format de réponse de l'endpoint /poser-question. Champs communs à
    toutes les réponses : reponse, sources, hors_domaine, demande_precision,
    type, methode. Champs présents uniquement quand type == "clarification" :
    options, autre_autorise, contexte_clarification."""
    reponse: str
    sources: list[SourceItem] = []
    hors_domaine: bool = False
    demande_precision: bool = False
    type: str
    methode: str
    options: list[str] | None = None
    autre_autorise: bool | None = None
    contexte_clarification: dict | None = None


class ArticleDuJour(BaseModel):
    """Format de réponse de l'endpoint /article-du-jour. Champs optionnels
    car indisponible=True (corpus vide) ne renvoie que indisponible/message ;
    cas nominal inchangé (tous les champs texte sont renseignés)."""
    titre: str | None = None
    extrait: str | None = None
    texte_complet: str | None = None
    explication_fr: str | None = None
    explication_ht: str | None = None
    tags: list[str] = []
    indisponible: bool = False
    message: str | None = None


class ArchiveItem(BaseModel):
    """Une entrée de l'endpoint /article-du-jour/archives."""
    titre: str
    extrait: str
    texte_complet: str
    explication_fr: str
    explication_ht: str
    tags: list[str] = []
    created_at: str
    tranche: int


@app.get("/")
def accueil():
    """Vérification rapide que l'API est en vie."""
    return {"service": "Halex API", "statut": "en ligne"}


@app.post("/poser-question", response_model=ReponseHalex)
def endpoint_question(q: Question):
    """Reçoit une question, renvoie la réponse du moteur en JSON. Si
    numero_article ET source_choisie sont fournis, on saute la détection et
    on va droit au lookup (cas d'une clarification déjà résolue côté
    utilisateur)."""
    if q.numero_article and q.source_choisie:
        return lookup_article(q.numero_article, q.source_choisie)
    return poser_question(q.question, mode=q.mode)


@app.get("/article-du-jour", response_model=ArticleDuJour)
def endpoint_article_du_jour():
    """Article vedette du jour calendaire courant, identique pour tous les
    utilisateurs."""
    return article_du_jour()


@app.get("/article-du-jour/archives", response_model=list[ArchiveItem])
def endpoint_archives_article_du_jour():
    """Historique des articles du jour déjà générés (30 plus récents)."""
    return archives_article_du_jour()


@app.get("/admin/ping")
def endpoint_admin_ping(admin: dict = Depends(verifier_admin)):
    """Endpoint de test temporaire pour valider la dépendance verifier_admin."""
    return {"status": "ok", "admin": admin["email"]}