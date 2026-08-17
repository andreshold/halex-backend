"""
moteur_normatif.py — Phase 3 Halex.

But
---
Intercaler un moteur normatif ENTRE le retrieval et le LLM de rédaction.

Le LLM peut qualifier la relation sémantique entre des textes déjà récupérés
(principal, complémentaire, spécial, contradictoire...), mais il ne décide
JAMAIS quel texte prévaut.

La décision de priorité est déterministe :
1. applicabilité / statut ;
2. relation juridique explicite déjà enrichie en amont ;
3. rang normatif ;
4. spécialité, uniquement à rang égal et si la qualification est explicite ;
5. date juridique `metadata.date`, uniquement à rang égal ;
6. complémentarité ou conflit non résolu.

`date_publication` ne participe JAMAIS à la primauté.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from schema_metadata import (
    RANGS_PAR_TYPE_NORME,
    STATUTS_APPLICABLES,
    STATUTS_NON_APPLICABLES,
    libelle_source,
)

_logger = logging.getLogger(__name__)

RoleDocument = Literal[
    "principal",
    "complementaire",
    "contexte",
    "non_pertinent",
]

TypeRelation = Literal[
    "complementarite",
    "specialite",
    "contradiction",
    "meme_regime",
    "independant",
    "incertain",
]

Confiance = Literal["haute", "moyenne", "faible"]


class QualificationDocument(BaseModel):
    document: str = Field(
        description=(
            "Alias court du document, par exemple D1 ou D2. "
            "Retourner UNIQUEMENT l'alias, sans crochets et sans préfixe NORMDOC."
        )
    )
    role: RoleDocument
    raison: str = Field(
        description="Raison courte strictement fondée sur le texte/métadonnées fournis."
    )
    confiance: Confiance = "haute"


class RelationSemantique(BaseModel):
    gauche: str = Field(
        description="Alias court du document gauche, par exemple D1."
    )
    droite: str = Field(
        description="Alias court du document droit, par exemple D2."
    )
    type: TypeRelation
    document_special: str | None = Field(
        default=None,
        description=(
            "Uniquement pour type=specialite : alias court (ex. D2) du texte "
            "dont le champ d'application est plus précis pour la question."
        ),
    )
    incompatibles_sur_question: bool = Field(
        default=False,
        description=(
            "True seulement si les deux règles ne peuvent pas produire "
            "simultanément la même solution sur le point précis posé. "
            "Permet de distinguer spécialité complémentaire et spécialité "
            "qui doit réellement départager deux règles."
        ),
    )
    raison: str
    confiance: Confiance = "haute"


class QualificationNormative(BaseModel):
    documents: list[QualificationDocument] = Field(default_factory=list)
    relations: list[RelationSemantique] = Field(default_factory=list)
    remarque: str | None = None


_PROMPT_QUALIFICATION = """Tu es le QUALIFICATEUR NORMATIF interne de Halex.

Tu reçois :
- UNE question juridique ;
- plusieurs textes juridiques déjà récupérés par le moteur de recherche ;
- leurs métadonnées.

Ta seule mission est de CLASSER leur rôle et leurs relations.
Tu ne rédiges pas la réponse finale et tu ne décides JAMAIS quel texte prévaut.

RÈGLES ABSOLUES :
1. Utilise uniquement les textes et métadonnées fournis. Pas de connaissance
   juridique externe.
2. Pour chaque document, choisis :
   - principal : répond directement au cœur de la question ;
   - complementaire : ajoute une condition, exception, conséquence, peine ou
     régime distinct nécessaire pour compléter la réponse ;
   - contexte : lié au sujet mais pas nécessaire pour répondre ;
   - non_pertinent : ne répond pas réellement à la question.
3. Relations :
   - complementarite : les deux règles peuvent s'appliquer ensemble sans se
     contredire ;
   - specialite : l'un traite un cas plus précis inclus dans le champ plus
     général de l'autre ET la question vise ce cas plus précis. Mets
     incompatibles_sur_question=true seulement si les deux règles donneraient
     des solutions incompatibles sur le point posé ;
   - contradiction : appliqués aux mêmes faits et au même point juridique,
     les deux textes imposeraient des conséquences incompatibles ;
   - meme_regime : ils expriment ou précisent le même régime ;
   - independant : sujets voisins mais juridiquement distincts ;
   - incertain : impossible de qualifier de façon sûre à partir des seuls textes.
4. Ne qualifie JAMAIS de contradiction une simple différence de thème,
   d'exception, de peine ou de condition.
   Si l'un est réellement spécial par rapport à l'autre ET que les solutions
   sont incompatibles sur la question, utilise type=specialite avec
   incompatibles_sur_question=true plutôt que type=contradiction.
5. Ne qualifie JAMAIS de specialite seulement parce qu'un article est plus long,
   plus récent, ou numéroté différemment.
6. Pour specialite, document_special doit être recopié exactement.
   Une spécialité peut être complémentaire : dans ce cas
   incompatibles_sur_question=false.
7. Ne compare PAS rangs, dates ou statuts pour choisir un gagnant : cette
   décision appartient au moteur déterministe.
8. Si un article parle de légitime défense et un autre d'un danger
   actuel/imminent avec acte de sauvegarde, ne les fusionne pas artificiellement :
   ils peuvent être complémentaires ou indépendants selon la question.
9. Chaque document porte un alias comme [NORMDOC: D1].
   Dans les champs `document`, `gauche`, `droite` et `document_special`,
   retourne UNIQUEMENT D1, D2, etc. Ne retourne jamais "[NORMDOC: D1]".
10. Chaque document fourni doit recevoir exactement un rôle dans `documents`.
"""


def _meta(document: dict[str, Any]) -> dict[str, Any]:
    meta = document.get("metadata")
    if not isinstance(meta, dict):
        return {}
    return meta


def identifiant_document(document: dict[str, Any]) -> str:
    meta = _meta(document)
    chunk_id = meta.get("chunk_id")
    if isinstance(chunk_id, str) and chunk_id.strip():
        return chunk_id.strip()

    source = meta.get("source") or "Source inconnue"
    article = meta.get("article") or "Article inconnu"
    return f"{source}::{article}"


def _date_juridique(meta: dict[str, Any]) -> date | None:
    valeur = meta.get("date")
    if not isinstance(valeur, str):
        return None
    try:
        return date.fromisoformat(valeur)
    except ValueError:
        return None


def _rang(meta: dict[str, Any]) -> int | None:
    type_norme = meta.get("type_norme")
    attendu = RANGS_PAR_TYPE_NORME.get(type_norme)
    recu = meta.get("rang")
    if attendu is None or recu != attendu:
        return None
    return attendu


def _statut(meta: dict[str, Any]) -> str:
    valeur = meta.get("statut")
    return valeur if isinstance(valeur, str) else ""


def _applicable(document: dict[str, Any]) -> bool:
    return _statut(_meta(document)) in STATUTS_APPLICABLES


def _resume_document_pour_llm(
    document: dict[str, Any],
    alias: str,
) -> str:
    meta = _meta(document)

    def liste(cle: str, limite: int = 6) -> str:
        valeurs = meta.get(cle)
        if not isinstance(valeurs, list):
            return "[]"
        utiles = [str(v) for v in valeurs[:limite]]
        return "[" + " ; ".join(utiles) + "]"

    champs = [
        f"[NORMDOC: {alias}]",
        f"source={libelle_source(meta) or meta.get('source', '?')}",
        f"article={meta.get('article', '?')}",
        f"type_norme={meta.get('type_norme', '?')}",
        f"rang={meta.get('rang', '?')}",
        f"statut={meta.get('statut', '?')}",
        f"date={meta.get('date', '?')}",
        f"concepts={liste('concepts_juridiques')}",
        f"conditions={liste('conditions_application', 4)}",
        f"exceptions={liste('exceptions', 4)}",
        f"circonstances={liste('circonstances', 4)}",
        f"references_articles={liste('references_articles', 8)}",
        "TEXTE:",
        str(document.get("content") or "")[:5000],
    ]
    return "\n".join(champs)


def _qualification_fallback(
    documents: list[dict[str, Any]],
) -> QualificationNormative:
    """
    Dégradation conservatrice en cas d'échec du LLM de qualification.

    On ne fabrique aucune contradiction/spécialité. Le meilleur résultat
    applicable reste principal et les autres applicables restent contexte.
    """
    qualifications: list[QualificationDocument] = []
    principal_attribue = False

    for doc in documents:
        ident = identifiant_document(doc)
        if _applicable(doc) and not principal_attribue:
            role: RoleDocument = "principal"
            principal_attribue = True
        elif _applicable(doc):
            role = "contexte"
        else:
            role = "contexte"

        qualifications.append(
            QualificationDocument(
                document=ident,
                role=role,
                raison="Repli conservateur : qualification sémantique indisponible.",
                confiance="faible",
            )
        )

    return QualificationNormative(
        documents=qualifications,
        relations=[],
        remarque="Qualification sémantique indisponible ; aucune contradiction n'a été inférée.",
    )



_RE_ALIAS = re.compile(r"^\s*(?:\[?\s*NORMDOC\s*:\s*)?(D\d+)\s*\]?\s*$", re.IGNORECASE)


def _normaliser_alias(
    valeur: str | None,
    alias_vers_ident: dict[str, str],
    ident_vers_alias: dict[str, str],
) -> str | None:
    """Accepte D1, [NORMDOC: D1], NORMDOC:D1 ou même l'id réel.

    Le prompt demande D1, mais cette tolérance empêche qu'une variation de
    format du modèle fasse disparaître silencieusement tous les documents.
    """
    if not isinstance(valeur, str):
        return None

    brut = valeur.strip()
    if brut in ident_vers_alias:
        return ident_vers_alias[brut]

    m = _RE_ALIAS.match(brut)
    if not m:
        return None

    alias = m.group(1).upper()
    return alias if alias in alias_vers_ident else None


def qualifier_documents(
    question: str,
    documents: list[dict[str, Any]],
    llm: Any,
    limite: int = 10,
) -> QualificationNormative:
    if not documents:
        return QualificationNormative()

    candidats = documents[:limite]

    # Aliases courts D1/D2/... : le LLM n'a plus à recopier des chunk_id
    # longs et ne peut plus confondre la valeur avec le label [NORMDOC: ...].
    alias_vers_ident = {
        f"D{i}": identifiant_document(doc)
        for i, doc in enumerate(candidats, start=1)
    }
    ident_vers_alias = {
        ident: alias for alias, ident in alias_vers_ident.items()
    }

    contexte = "\n\n".join(
        _resume_document_pour_llm(doc, f"D{i}")
        for i, doc in enumerate(candidats, start=1)
    )
    message = f"QUESTION:\n{question}\n\nDOCUMENTS:\n{contexte}"

    try:
        # include_raw=True rend les échecs de parsing observables au lieu de
        # les transformer en comportement mystérieux.
        structure = llm.with_structured_output(
            QualificationNormative,
            include_raw=True,
        )
        paquet = structure.invoke(
            [
                {"role": "system", "content": _PROMPT_QUALIFICATION},
                {"role": "user", "content": message},
            ]
        )

        if isinstance(paquet, dict) and "parsed" in paquet:
            erreur_parse = paquet.get("parsing_error")
            resultat = paquet.get("parsed")
            if erreur_parse is not None:
                _logger.warning(
                    "Parsing structured output du qualificateur échoué: %s",
                    erreur_parse,
                )
            if resultat is None:
                raise ValueError(
                    "Le qualificateur n'a produit aucun objet structuré parsé."
                )
        else:
            # Compatibilité avec versions LangChain qui renverraient
            # directement le modèle malgré include_raw.
            resultat = paquet

    except Exception as exc:
        _logger.warning("Échec qualification normative: %s", exc)
        return _qualification_fallback(candidats)

    if not isinstance(resultat, QualificationNormative):
        _logger.warning(
            "Type inattendu du qualificateur: %s",
            type(resultat).__name__,
        )
        return _qualification_fallback(candidats)

    # Normalisation des alias retournés.
    docs_normalises: list[QualificationDocument] = []
    vus: set[str] = set()

    for q in resultat.documents:
        alias = _normaliser_alias(
            q.document,
            alias_vers_ident,
            ident_vers_alias,
        )
        if alias is None:
            _logger.warning(
                "Alias document inconnu retourné par le qualificateur: %r",
                q.document,
            )
            continue

        ident_reel = alias_vers_ident[alias]
        if ident_reel in vus:
            continue
        vus.add(ident_reel)

        docs_normalises.append(
            QualificationDocument(
                document=ident_reel,
                role=q.role,
                raison=q.raison,
                confiance=q.confiance,
            )
        )

    relations_normalisees: list[RelationSemantique] = []

    for r in resultat.relations:
        ag = _normaliser_alias(
            r.gauche,
            alias_vers_ident,
            ident_vers_alias,
        )
        ad = _normaliser_alias(
            r.droite,
            alias_vers_ident,
            ident_vers_alias,
        )
        if ag is None or ad is None or ag == ad:
            _logger.warning(
                "Relation ignorée, alias invalides: gauche=%r droite=%r",
                r.gauche,
                r.droite,
            )
            continue

        special_alias = None
        if r.document_special is not None:
            special_alias = _normaliser_alias(
                r.document_special,
                alias_vers_ident,
                ident_vers_alias,
            )
            if special_alias is None:
                _logger.warning(
                    "document_special invalide ignoré: %r",
                    r.document_special,
                )

        relations_normalisees.append(
            RelationSemantique(
                gauche=alias_vers_ident[ag],
                droite=alias_vers_ident[ad],
                type=r.type,
                document_special=(
                    alias_vers_ident[special_alias]
                    if special_alias is not None
                    else None
                ),
                incompatibles_sur_question=r.incompatibles_sur_question,
                raison=r.raison,
                confiance=r.confiance,
            )
        )

    # Si le LLM omet un document, on ne le supprime pas : on le garde comme
    # contexte faible. Mais si TOUS les documents sont omis, c'est un signal
    # d'anomalie de qualification, pas une qualification "réussie".
    if not docs_normalises:
        _logger.warning(
            "Le qualificateur n'a classé aucun document valide. "
            "Repli conservateur."
        )
        return _qualification_fallback(candidats)

    for doc in candidats:
        ident = identifiant_document(doc)
        if ident not in vus:
            docs_normalises.append(
                QualificationDocument(
                    document=ident,
                    role="contexte",
                    raison=(
                        "Document récupéré non classé explicitement par "
                        "le qualificateur."
                    ),
                    confiance="faible",
                )
            )

    return QualificationNormative(
        documents=docs_normalises,
        relations=relations_normalisees,
        remarque=resultat.remarque,
    )


def _decision_contradiction(
    doc_g: dict[str, Any],
    doc_d: dict[str, Any],
    relation: RelationSemantique,
) -> dict[str, Any]:
    """
    Résolution DÉTERMINISTE d'une contradiction déjà qualifiée.

    La spécialité n'est examinée qu'à rang égal. Un texte spécial de rang
    inférieur ne peut pas renverser une norme supérieure.
    """
    mg = _meta(doc_g)
    md = _meta(doc_d)
    ig = identifiant_document(doc_g)
    id_ = identifiant_document(doc_d)

    ag = _statut(mg) in STATUTS_APPLICABLES
    ad = _statut(md) in STATUTS_APPLICABLES

    if ag and not ad:
        return {
            "gagnant": ig,
            "perdant": id_,
            "raison": "statut",
            "resolu": True,
        }
    if ad and not ag:
        return {
            "gagnant": id_,
            "perdant": ig,
            "raison": "statut",
            "resolu": True,
        }
    if not ag and not ad:
        return {
            "gagnant": None,
            "perdant": None,
            "raison": "aucun_applicable",
            "resolu": False,
        }

    rg = _rang(mg)
    rd = _rang(md)
    if rg is None or rd is None:
        return {
            "gagnant": None,
            "perdant": None,
            "raison": "metadata_normative_invalide",
            "resolu": False,
        }

    if rg < rd:
        return {
            "gagnant": ig,
            "perdant": id_,
            "raison": "rang",
            "resolu": True,
        }
    if rd < rg:
        return {
            "gagnant": id_,
            "perdant": ig,
            "raison": "rang",
            "resolu": True,
        }

    # Même rang : la spécialité peut intervenir AVANT la date si elle a été
    # qualifiée explicitement et avec confiance suffisante.
    if (
        relation.type == "specialite"
        and relation.incompatibles_sur_question
        and relation.document_special in {ig, id_}
        and relation.confiance in {"haute", "moyenne"}
    ):
        special = relation.document_special
        autre = id_ if special == ig else ig
        return {
            "gagnant": special,
            "perdant": autre,
            "raison": "specialite",
            "resolu": True,
        }

    dg = _date_juridique(mg)
    dd = _date_juridique(md)
    if dg is None or dd is None:
        return {
            "gagnant": None,
            "perdant": None,
            "raison": "date_juridique_invalide",
            "resolu": False,
        }

    if dg > dd:
        return {
            "gagnant": ig,
            "perdant": id_,
            "raison": "date",
            "resolu": True,
        }
    if dd > dg:
        return {
            "gagnant": id_,
            "perdant": ig,
            "raison": "date",
            "resolu": True,
        }

    return {
        "gagnant": None,
        "perdant": None,
        "raison": "egalite_normative",
        "resolu": False,
    }


def analyser_normativement(
    question: str,
    documents: list[dict[str, Any]],
    llm: Any,
) -> dict[str, Any]:
    """
    Produit :
    - documents ordonnés pour le prompt final ;
    - bloc normatif à injecter ;
    - diagnostic sérialisable pour les logs/API.

    Aucun gagnant n'est choisi en dehors d'une relation de contradiction
    explicitement qualifiée.
    """
    if not documents:
        return {
            "documents": [],
            "bloc_prompt": "",
            "diagnostic": {
                "qualification_disponible": False,
                "documents": [],
                "relations": [],
                "decisions": [],
                "conflits_non_resolus": [],
            },
        }

    qualification = qualifier_documents(question, documents, llm)
    index_docs = {identifiant_document(d): d for d in documents}
    roles = {q.document: q for q in qualification.documents}

    decisions: list[dict[str, Any]] = []
    conflits_non_resolus: list[dict[str, Any]] = []

    for relation in qualification.relations:
        # Décision de priorité uniquement si une incompatibilité a été
        # explicitement qualifiée :
        # - contradiction directe ;
        # - spécialité avec incompatibles_sur_question=true.
        doit_departager = (
            relation.type == "contradiction"
            or (
                relation.type == "specialite"
                and relation.incompatibles_sur_question
            )
        )
        if doit_departager:
            g = index_docs.get(relation.gauche)
            d = index_docs.get(relation.droite)
            if not g or not d:
                continue
            decision = _decision_contradiction(g, d, relation)
            decision.update(
                {
                    "gauche": relation.gauche,
                    "droite": relation.droite,
                    "type_relation": relation.type,
                    "raison_relation": relation.raison,
                }
            )
            decisions.append(decision)
            if not decision["resolu"]:
                conflits_non_resolus.append(decision)

    # Une spécialité non contradictoire sert à mettre le texte spécial avant
    # le texte général, mais pas à supprimer le général.
    special_ids = {
        r.document_special
        for r in qualification.relations
        if r.type == "specialite"
        and r.document_special
        and r.confiance in {"haute", "moyenne"}
    }

    ordre_role = {
        "principal": 0,
        "complementaire": 1,
        "contexte": 2,
        "non_pertinent": 3,
    }

    def cle_ordre(doc: dict[str, Any]) -> tuple[int, int, int]:
        ident = identifiant_document(doc)
        q = roles.get(ident)
        role = q.role if q else "contexte"
        meta = _meta(doc)
        applicable = 0 if _statut(meta) in STATUTS_APPLICABLES else 1
        special = 0 if ident in special_ids else 1
        return (ordre_role[role], applicable, special)

    ordonnes = sorted(documents, key=cle_ordre)

    # On retire les documents explicitement non pertinents, sauf si cela
    # viderait entièrement le contexte : dans ce cas, on garde les 2 premiers
    # pour que le prompt final puisse encore conclure [HORS_DOMAINE].
    utiles = [
        d for d in ordonnes
        if (roles.get(identifiant_document(d)) is None
            or roles[identifiant_document(d)].role != "non_pertinent")
    ]
    if not utiles:
        utiles = ordonnes[:2]

    lignes = [
        "=== ANALYSE NORMATIVE HALEX — À RESPECTER ===",
        "Cette analyse a été calculée avant la rédaction.",
        "`date_publication` est informative et n'a pas été utilisée pour la primauté.",
        "",
        "RÔLE DES DOCUMENTS :",
    ]

    for doc in utiles:
        ident = identifiant_document(doc)
        meta = _meta(doc)
        q = roles.get(ident)
        role = q.role if q else "contexte"
        raison = q.raison if q else "Non classé."
        lignes.append(
            f"- [NORMDOC: {ident}] {meta.get('article', '?')} — "
            f"rôle={role} ; statut={meta.get('statut', '?')} ; "
            f"rang={meta.get('rang', '?')} ; date={meta.get('date', '?')} ; "
            f"raison={raison}"
        )

    if qualification.relations:
        lignes.extend(["", "RELATIONS QUALIFIÉES :"])
        for r in qualification.relations:
            special = (
                f" ; texte spécial={r.document_special}"
                if r.document_special
                else ""
            )
            incompat = (
                " ; incompatibles_sur_question=true"
                if r.incompatibles_sur_question
                else ""
            )
            lignes.append(
                f"- {r.gauche} ↔ {r.droite} : {r.type}"
                f"{special}{incompat} ; confiance={r.confiance} ; {r.raison}"
            )

    if decisions:
        lignes.extend(["", "DÉCISIONS DÉTERMINISTES SUR CONTRADICTIONS :"])
        for d in decisions:
            if d["resolu"]:
                lignes.append(
                    f"- {d['gauche']} / {d['droite']} : "
                    f"priorité à {d['gagnant']} par {d['raison']}."
                )
            else:
                lignes.append(
                    f"- {d['gauche']} / {d['droite']} : "
                    f"CONFLIT NON RÉSOLU ({d['raison']})."
                )

    lignes.extend([
        "",
        "INSTRUCTIONS AU RÉDACTEUR :",
        "- Utilise d'abord les documents rôle=principal.",
        "- Utilise les documents rôle=complementaire seulement pour ajouter leur régime distinct, condition, exception ou conséquence.",
        "- Ne fusionne pas deux régimes distincts en une seule règle.",
        "- Un document statut=abroge ou adopte_non_applique ne fonde pas l'état courant du droit.",
        "- Si une décision déterministe de priorité est indiquée, ne la renverse jamais.",
        "- Si un conflit est marqué NON RÉSOLU, signale la tension sans inventer de solution.",
        "- Une relation de complémentarité ne comporte aucun gagnant : cite les deux si les deux sont nécessaires.",
        "- Ne transforme jamais une simple proximité thématique en contradiction.",
    ])

    diagnostic = {
        "qualification_disponible": True,
        "documents": [q.model_dump() for q in qualification.documents],
        "relations": [r.model_dump() for r in qualification.relations],
        "decisions": decisions,
        "conflits_non_resolus": conflits_non_resolus,
        "remarque": qualification.remarque,
    }

    return {
        "documents": utiles,
        "bloc_prompt": "\n".join(lignes),
        "diagnostic": diagnostic,
    }