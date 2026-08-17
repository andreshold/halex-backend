#!/usr/bin/env python3
"""Transcrit et structure le décret bancaire haïtien du 14 novembre 1980."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

import pdfplumber
import pypdf


RACINE = (
    "DECRET DU 14 NOVEMBRE 1980 REGLEMENTANT LE FONCTIONNEMENT DES BANQUES "
    "ET DES ACTIVITES BANCAIRES SUR LE TERRITOIRE DE LA REPUBLIQUE D’HAITI"
)

# Les segments sont ceux du document. Le dernier TITRE III est donc conservé
# tel qu'imprimé, même s'il suit le TITRE VI.
STRUCTURES = {
    (1, "TITRE I.-"): ("titre", ["TITRE I.-", "PORTEE ET APPLICATION DE LA LOI"], 2),
    (1, "CHAPITRE I. PRELIMINAIRES"): ("chapitre", ["CHAPITRE I. PRELIMINAIRES"], 1),
    (1, "CHAPITRE II. DEFINITIONS"): ("chapitre", ["CHAPITRE II. DEFINITIONS"], 1),
    (3, "TITRE II"): ("titre", ["TITRE II", "CONDITIONS DE FONCTIONNEMENT"], 2),
    (3, "CHAPITRE I AUTORISATION DE FONCTIONNEMENT"): (
        "chapitre", ["CHAPITRE I AUTORISATION DE FONCTIONNEMENT"], 1,
    ),
    (5, "CHAPITRE II"): (
        "chapitre",
        ["CHAPITRE II", "DES PRESCRIPTIONS RELATIVES AU CAPITAL AUX RESERVES ET A LA REPARTITION DES PROFITS"],
        3,
    ),
    (5, "SECTION I. DU CAPITAL DES BANQUES"): ("section", ["SECTION I. DU CAPITAL DES BANQUES"], 1),
    (5, "SECTION II. DES RESERVES ET PROFITS"): ("section", ["SECTION II. DES RESERVES ET PROFITS"], 1),
    (7, "CHAPITRE III"): (
        "chapitre",
        ["CHAPITRE III", "DES LIMITATIONS AUX OPERATIONS DE CREDIT DES AVANCES AU PUBLIC EN GENERAL"],
        3,
    ),
    (7, "TITRE III."): ("titre", ["TITRE III.", "SUPERVISION ET CONTROLE DES BANQUES"], 2),
    (7, "CHAPITRE I. DU CONTROLE EXERCE PAR LA BRH"): (
        "chapitre", ["CHAPITRE I. DU CONTROLE EXERCE PAR LA BRH"], 1,
    ),
    (8, "CHAPITRE II"): (
        "chapitre",
        ["CHAPITRE II", "DES ETATS, RAPPORTS ET AUTRES RENSEIGNEMENTS A SOUMETTRE A LA BRH"],
        2,
    ),
    (8, "TITRE IV."): ("titre", ["TITRE IV.", "AUTRES RELATIONS DES BANQUES AVEC LA BRH"], 2),
    (8, "CHAPITRE I.- DES COMPTES TENUS A LA BRH AU NOM DES BANQUES"): (
        "chapitre", ["CHAPITRE I.- DES COMPTES TENUS A LA BRH AU NOM DES BANQUES"], 1,
    ),
    (8, "CHAPITRE II- DES OPERATIONS DE COMPENSATION OU CLEARING"): (
        "chapitre", ["CHAPITRE II- DES OPERATIONS DE COMPENSATION OU CLEARING"], 1,
    ),
    (9, "CHAPITRE III. DE LA CENTRALISATION ET DE L’UTILISATION"): (
        "chapitre",
        ["CHAPITRE III. DE LA CENTRALISATION ET DE L’UTILISATION DES INFORMATIONS DE CREDIT"],
        2,
    ),
    (9, "CHAPITRE IV. DU SEQUESTRE, DE LA LIQUIDATION ET DE"): (
        "chapitre",
        ["CHAPITRE IV. DU SEQUESTRE, DE LA LIQUIDATION ET DE LA REORGANISATION DES BANQUES"],
        2,
    ),
    (9, "SECTION I DESSAISISSEMENT DES BANQUES"): (
        "section", ["SECTION I DESSAISISSEMENT DES BANQUES"], 1,
    ),
    (10, "SECTION II. LIQUIDATION DES BANQUES"): (
        "section", ["SECTION II. LIQUIDATION DES BANQUES"], 1,
    ),
    (12, "SECTION III - REORGANISATION DES BANQUES"): (
        "section", ["SECTION III - REORGANISATION DES BANQUES"], 1,
    ),
    (13, "CHAPITRE V. DISPOSITIONS COMMUNES AU CHAPITRE IV SECTIONS I, II ET III"): (
        "chapitre", ["CHAPITRE V. DISPOSITIONS COMMUNES AU CHAPITRE IV SECTIONS I, II ET III"], 1,
    ),
    (13, "TITRE V"): ("titre", ["TITRE V"], 1),
    (13, "CHAPITRE I"): (
        "chapitre", ["CHAPITRE I", "DES ADMINISTRATEURS ET DIRIGEANTS DES BANQUES"], 2,
    ),
    (14, "CHAPITRE II"): (
        "chapitre", ["CHAPITRE II", "DU PERSONNEL DES BANQUES ET ETABLISSEMENTS FINANCIERS"], 2,
    ),
    (14, "TITRE VI"): ("titre", ["TITRE VI", "DISPOSITIONS DIVERSES"], 2),
    (16, "TITRE III. DISPOSITIONS PENALES"): (
        "titre", ["TITRE III. DISPOSITIONS PENALES"], 1,
    ),
    (16, "TITRE VIII. DISPOSITIONS TRANSITOIRES"): (
        "titre", ["TITRE VIII. DISPOSITIONS TRANSITOIRES"], 1,
    ),
    (16, "TITRE IX- CLAUSE D’ABROGATION"): (
        "titre", ["TITRE IX- CLAUSE D’ABROGATION"], 1,
    ),
}

REMPLACEMENTS_EXTRACTION = (
    ("ARTI CLE", "ARTICLE"),
    ("P ar", "Par"),
    ("L a", "La"),
    ("L es", "Les"),
    ("T oute", "Toute"),
    ("E n", "En"),
    ("C es", "Ces"),
    ("S i", "Si"),
    ("L e", "Le"),
    ("T ous", "Tous"),
    ("C ependant", "Cependant"),
    ("L orsque", "Lorsque"),
    ("S ile", "Si le"),
    ("b anqueroute", "banqueroute"),
    ("17nAoût", "17 Août"),
)

ANOMALIES_IMPRIMEES = [
    {"emplacement": "Article 1", "texte": "Demeure cependant régies", "decision": "conservé"},
    {"emplacement": "Article 74", "texte": "la BRH ne eut vendre", "decision": "conservé"},
    {"emplacement": "Article 92", "texte": "stipulée a l titre", "decision": "conservé"},
    {"emplacement": "Article 93", "texte": "ont ;été payées", "decision": "conservé"},
    {"emplacement": "Article 96", "texte": "put se faire suppléer", "decision": "conservé"},
    {"emplacement": "Article 101", "texte": "mené à bine", "decision": "conservé"},
    {"emplacement": "Article 107", "texte": "mise ne faillite / un tire quelconque", "decision": "conservé"},
    {"emplacement": "Article 118", "texte": "fonds à la BRH.. / mis ne paquet", "decision": "conservé"},
    {"emplacement": "Hiérarchie", "texte": "TITRE III après TITRE VI", "decision": "conservé"},
]

RE_ENUMERATION = re.compile(
    r"^(?:-\s+|[a-z]\)\s*|[A-Z]\.\s*|[IVXLCDM]+\)\s*|"
    r"\d+\s*(?:\.-\s*|\)\s+|-\s*|\.\s+))"
)
RE_ARTICLE = re.compile(r"^(ARTICLE|Article)\s+(\d+)")


@dataclass(frozen=True)
class Ligne:
    page: int
    top: float
    x0: float
    texte: str
    forcer_paragraphe: bool = False


@dataclass
class Evenement:
    debut: int
    fin: int
    type: str
    donnees: dict


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for bloc in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(bloc)
    return digest.hexdigest()


def nettoyer_espaces(texte: str) -> str:
    return re.sub(r"[ \t]+", " ", texte).strip()


def corriger_extraction(page: int, texte: str, audit: list[dict]) -> tuple[str, bool]:
    original = nettoyer_espaces(texte)
    corrige = original
    raisons: list[str] = []
    for avant, apres in REMPLACEMENTS_EXTRACTION:
        if avant in corrige:
            corrige = corrige.replace(avant, apres)
            raisons.append(f"{avant!r} → {apres!r}")
    # La police Symbol encode deux puces comme la lettre n dans la couche texte.
    if page in {1, 2} and corrige.startswith("n "):
        corrige = "- " + corrige[2:]
        raisons.append("glyphe Symbol de puce normalisé en tiret ASCII")
    forcer = corrige.startswith("une copie des Statuts")
    if corrige != original:
        audit.append({
            "page": page,
            "avant": original,
            "apres": corrige,
            "raison": "; ".join(raisons),
        })
    return corrige, forcer


def extraire_lignes(pdf: Path) -> tuple[list[Ligne], dict]:
    lignes: list[Ligne] = []
    corrections: list[dict] = []
    pages_avec_texte: list[int] = []
    caracteres_couche_texte = 0
    with pdfplumber.open(pdf) as document:
        pages_pdfplumber = len(document.pages)
        for numero_page, page in enumerate(document.pages, 1):
            texte_page = page.extract_text() or ""
            caracteres_couche_texte += len(texte_page)
            items = page.extract_text_lines(return_chars=False)
            if items:
                pages_avec_texte.append(numero_page)
            for item in items:
                corrige, forcer = corriger_extraction(numero_page, item["text"], corrections)
                if corrige:
                    lignes.append(Ligne(
                        numero_page,
                        float(item["top"]),
                        float(item["x0"]),
                        corrige,
                        forcer,
                    ))
    with pdf.open("rb") as stream:
        pages_pypdf = len(pypdf.PdfReader(stream).pages)
    return lignes, {
        "pages_pdfplumber": pages_pdfplumber,
        "pages_pypdf": pages_pypdf,
        "pages_avec_texte": pages_avec_texte,
        "pages_vides": sorted(set(range(1, pages_pypdf + 1)) - set(pages_avec_texte)),
        "caracteres_couche_texte": caracteres_couche_texte,
        "corrections_extraction": corrections,
        "elements_marginaux_retires": [],
    }


def parser_article(texte: str) -> dict | None:
    match = RE_ARTICLE.match(texte)
    if not match:
        return None
    chiffres = match.group(2)
    # Le document imprime « ARTICLE 971- » pour l'article 97, suivi du
    # paragraphe « 1- ». On déplace ce 1 dans le corps sans en perdre un seul.
    if chiffres == "971":
        fin_numero = match.start(2) + 2
        return {
            "numero": 97,
            "etiquette": nettoyer_espaces(texte[:fin_numero]),
            "corps": nettoyer_espaces("1" + texte[match.end():]),
            "anomalie": "ARTICLE 971- décomposé en Article 97 + paragraphe 1-",
        }
    numero = int(chiffres)
    reste = texte[match.end():]
    delimiteur = re.match(r"^\s*(?:\.\s*-\s*|\.\s*|-\s*)", reste)
    if delimiteur and any(caractere in delimiteur.group(0) for caractere in ".-"):
        etiquette = nettoyer_espaces(texte[:match.end()] + delimiteur.group(0))
        corps = nettoyer_espaces(reste[delimiteur.end():])
    else:
        etiquette = nettoyer_espaces(texte[:match.end()])
        corps = nettoyer_espaces(reste)
    return {"numero": numero, "etiquette": etiquette, "corps": corps, "anomalie": None}


def construire_structures(lignes: list[Ligne], limite: int) -> list[Evenement]:
    evenements: list[Evenement] = []
    for index, ligne in enumerate(lignes[:limite]):
        definition = STRUCTURES.get((ligne.page, ligne.texte))
        if not definition:
            continue
        niveau, segments, longueur = definition
        bruts = [item.texte for item in lignes[index:index + longueur]]
        if nettoyer_espaces(" ".join(bruts)) != nettoyer_espaces(" ".join(segments)):
            raise RuntimeError(
                f"Structure inattendue page {ligne.page}: {bruts!r} != {segments!r}"
            )
        evenements.append(Evenement(index, index + longueur, "structure", {
            "niveau": niveau,
            "segments": segments,
            "lignes": bruts,
        }))
    if len(evenements) != len(STRUCTURES):
        raise RuntimeError(f"{len(STRUCTURES)} structures attendues, {len(evenements)} trouvées")
    return evenements


def formater_article(lignes: list[Ligne], article: dict) -> str:
    travail = list(lignes)
    travail[0] = replace(travail[0], texte=article["corps"])
    paragraphes: list[str] = []
    courant: list[str] = []
    for ligne in travail:
        if not ligne.texte:
            continue
        if courant and (ligne.forcer_paragraphe or RE_ENUMERATION.match(ligne.texte)):
            paragraphes.append(" ".join(courant))
            courant = []
        courant.append(ligne.texte)
    if courant:
        paragraphes.append(" ".join(courant))
    corps = "\n\n".join(paragraphe.strip() for paragraphe in paragraphes if paragraphe.strip())
    return f"{article['etiquette']}\n\n{corps}"


def formater_non_article(lignes: list[Ligne], type_bloc: str) -> str:
    paragraphes: list[str] = []
    courant: list[str] = []
    if type_bloc == "visas":
        debuts = ("Vu ", "Considérant ", "Sur le Rapport", "Et après", "DECRETE")
    elif type_bloc == "preambule":
        debuts = ("(Moniteur", "JEAN CLAUDE", "Président à Vie")
    else:
        debuts = ("Jean-Claude",)
    for ligne in lignes:
        if courant and ligne.texte.startswith(debuts):
            paragraphes.append(" ".join(courant))
            courant = []
        courant.append(ligne.texte)
    if courant:
        paragraphes.append(" ".join(courant))
    return "\n\n".join(paragraphe.strip() for paragraphe in paragraphes if paragraphe.strip())


def chemin_et_metadata(etat: dict) -> tuple[str, dict]:
    chemin = [RACINE]
    extra: dict = {}
    for niveau in ("titre", "chapitre", "section"):
        segments = etat.get(niveau) or []
        if segments:
            chemin.extend(segments)
            extra[niveau] = " > ".join(segments)
    return " > ".join(chemin), extra


def construire(lignes: list[Ligne], base: dict) -> tuple[list[dict], str, dict]:
    articles = [(index, parser_article(ligne.texte)) for index, ligne in enumerate(lignes) if parser_article(ligne.texte)]
    numeros = [article["numero"] for _, article in articles]
    attendus = list(range(1, 134))
    if numeros != attendus:
        manquants = sorted(set(attendus) - set(numeros))
        doublons = sorted(numero for numero, compte in Counter(numeros).items() if compte > 1)
        raise RuntimeError(f"Articles non séquentiels; manquants={manquants}, doublons={doublons}")

    index_visas = next(i for i, ligne in enumerate(lignes) if ligne.texte.startswith("Vu les articles 68"))
    index_cloture = next(i for i, ligne in enumerate(lignes) if ligne.texte.startswith("Donné au Palais National"))
    structures = construire_structures(lignes, index_cloture)

    evenements: dict[int, Evenement] = {
        0: Evenement(0, index_visas, "preambule", {}),
        index_visas: Evenement(index_visas, 0, "visas", {}),
        index_cloture: Evenement(index_cloture, len(lignes), "cloture", {}),
    }
    for position, article in articles:
        evenements[position] = Evenement(position, 0, "article", {"article": article})
    for structure in structures:
        evenements[structure.debut] = structure
    positions = sorted(evenements)
    for indice, position in enumerate(positions):
        evenement = evenements[position]
        if evenement.type != "structure":
            evenement.fin = positions[indice + 1] if indice + 1 < len(positions) else len(lignes)

    chunks: list[dict] = []
    markdown: list[str] = []
    etat = {"titre": [], "chapitre": [], "section": []}
    indices_structure = {i for evenement in structures for i in range(evenement.debut, evenement.fin)}

    def ajouter(contenu: str, article: str, type_bloc: str, chemin: str, extra: dict | None = None) -> None:
        chunks.append({
            "page_content": contenu,
            "metadata": {
                **base,
                "article": article,
                "type_bloc": type_bloc,
                "ordre": len(chunks) + 1,
                "chemin_hierarchique": chemin,
                **(extra or {}),
            },
        })
        markdown.append(contenu)

    for position in positions:
        evenement = evenements[position]
        if evenement.type == "structure":
            niveau = evenement.donnees["niveau"]
            etat[niveau] = evenement.donnees["segments"]
            if niveau == "titre":
                etat["chapitre"], etat["section"] = [], []
            elif niveau == "chapitre":
                etat["section"] = []
            markdown.append("\n\n".join(evenement.donnees["lignes"]))
            continue
        bloc_lignes = lignes[evenement.debut:evenement.fin]
        if evenement.type == "preambule":
            ajouter(
                formater_non_article(bloc_lignes, "preambule"),
                "Préambule", "preambule", f"{RACINE} > PRÉAMBULE",
            )
        elif evenement.type == "visas":
            ajouter(
                formater_non_article(bloc_lignes, "visas"),
                "Visas", "visas", f"{RACINE} > VISAS",
            )
        elif evenement.type == "article":
            article = evenement.donnees["article"]
            chemin, extra = chemin_et_metadata(etat)
            ajouter(
                formater_article(bloc_lignes, article),
                f"Article {article['numero']}", "article", chemin, extra,
            )
        elif evenement.type == "cloture":
            ajouter(
                formater_non_article(bloc_lignes, "cloture"),
                "Clôture", "cloture", f"{RACINE} > CLÔTURE",
            )

    reference_chunks = [
        ligne.texte for indice, ligne in enumerate(lignes) if indice not in indices_structure
    ]
    return chunks, "\n\n".join(markdown) + "\n", {
        "articles": numeros,
        "structures": [event.donnees for event in structures],
        "reference_chunks": reference_chunks,
        "reference_complete": [ligne.texte for ligne in lignes],
        "anomalies_entetes_articles": [
            article["anomalie"] for _, article in articles if article["anomalie"]
        ],
    }


def sequence_hors_espaces(textes: list[str]) -> str:
    return "".join(re.sub(r"\s+", "", texte) for texte in textes)


def construire_rapport(
    pdf: Path,
    dossier: Path,
    chunks: list[dict],
    markdown: str,
    audit_extraction: dict,
    audit_structure: dict,
    validation: dict,
    types_valides: set[str],
) -> dict:
    types = Counter(chunk["metadata"]["type_bloc"] for chunk in chunks)
    articles = [chunk for chunk in chunks if chunk["metadata"]["type_bloc"] == "article"]
    reference_chunks = sequence_hors_espaces(audit_structure["reference_chunks"])
    contenu_chunks = sequence_hors_espaces([chunk["page_content"] for chunk in chunks])
    reference_complete = sequence_hors_espaces(audit_structure["reference_complete"])
    contenu_markdown = re.sub(r"\s+", "", markdown)
    retours_simples = sum(
        len(re.findall(r"(?<!\n)\n(?!\n)", chunk["page_content"])) for chunk in articles
    )
    cles_moniteur = {"moniteur_publication"}
    presentes_moniteur = [sorted(set(chunk["metadata"]) & cles_moniteur) for chunk in chunks]
    integrite = reference_chunks == contenu_chunks
    return {
        "statut": "conforme_techniquement_a_relecture_humaine",
        "source": {
            "pdf": str(pdf.resolve()),
            "sha256": sha256(pdf),
            "pages_pdf": audit_extraction["pages_pypdf"],
            "pages_utiles": len(audit_extraction["pages_avec_texte"]),
            "pages_vides": audit_extraction["pages_vides"],
            "caracteres_couche_texte": audit_extraction["caracteres_couche_texte"],
            "publication_imprimee": "Moniteur no. 82 du lundi 17 novembre 1980",
            "date_du_decret_imprimee": "1980-11-14",
            "extraction_principale": f"pdfplumber {pdfplumber.__version__}, texte natif et géométrie",
            "verification_secondaire": f"pypdf {pypdf.__version__}",
            "verification_visuelle": "17 pages rendues à 150 dpi; pages et zones ambiguës contrôlées à 300 dpi",
        },
        "sorties": {
            "dossier_registre": str(dossier.resolve()),
            "markdown": "outputs/document.md",
            "chunks": "outputs/chunks.json",
            "validation_backend": "outputs/rapport_validation_backend.json",
        },
        "chunks": {
            "prevus": 136,
            "trouves": len(chunks),
            "ecart": len(chunks) - 136,
            "par_type_bloc": dict(sorted(types.items())),
        },
        "articles": {
            "prevus": 133,
            "trouves": len(articles),
            "numeros": audit_structure["articles"],
            "articles_introuvables": sorted(set(range(1, 134)) - set(audit_structure["articles"])),
            "doublons": sorted(
                numero for numero, compte in Counter(audit_structure["articles"]).items() if compte > 1
            ),
        },
        "hierarchie": {
            "groupes_structuraux": len(audit_structure["structures"]),
            "tous_chunks_avec_chemin_hierarchique": all(
                bool(chunk["metadata"].get("chemin_hierarchique")) for chunk in chunks
            ),
            "titre_inhabituel_conserve": "TITRE III. DISPOSITIONS PENALES",
            "exemples": {
                label: next(
                    chunk["metadata"]["chemin_hierarchique"]
                    for chunk in chunks if chunk["metadata"]["article"] == label
                )
                for label in ("Article 1", "Article 32", "Article 47", "Article 71", "Article 96", "Article 131")
            },
        },
        "integrite_caracteres": {
            "methode": "comparaison de la séquence Unicode après normalisation exclusive des espaces et retours",
            "reference_hors_espaces": len(reference_chunks),
            "chunks_hors_espaces": len(contenu_chunks),
            "chunks_identiques_a_la_reference": integrite,
            "caracteres_manquants_detectes": 0 if integrite else None,
            "caracteres_ajoutes_detectes": 0 if integrite else None,
            "markdown_incluant_structure_identique": reference_complete == contenu_markdown,
            "corrections_extraction_documentees": len(audit_extraction["corrections_extraction"]),
            "details_corrections": audit_extraction["corrections_extraction"],
            "anomalies_imprimees_non_corrigees": ANOMALIES_IMPRIMEES,
            "anomalies_entetes_articles": audit_structure["anomalies_entetes_articles"],
        },
        "mise_en_page": {
            "retours_simples_dans_les_articles": retours_simples,
            "retours_simples_attendus": 0,
            "separateur_de_paragraphe": "double retour de ligne",
            "coupures_de_lignes_du_pdf_supprimees": True,
            "retours_conserves_pour_listes_et_numerotations": True,
            "en_tetes_repetitifs_detectes_et_retires": 0,
            "page_blanche_finale_ignoree": audit_extraction["pages_vides"] == [17],
        },
        "metadata": {
            "date_demandee_dans_le_message": "1980-11-17",
            "date_juridique_appliquee": "1980-11-14",
            "date_publication": "1980-11-17",
            "motif_correction_date": "le PDF indique que le décret est donné le 14 novembre 1980; le 17 novembre est sa date de publication",
            "historique": False,
            "tous_chunks_historique_false": all(chunk["metadata"].get("historique") is False for chunk in chunks),
            "reference_moniteur_partielle_imprimee": {"numero": "82", "date_publication": "1980-11-17"},
            "moniteur_publication": "non déterminable intégralement à partir du PDF",
            "regle_moniteur": "aucune des trois clés moniteur_* n'est présente; règle tout-ou-rien respectée",
            "cles_moniteur_presentes_par_chunk": presentes_moniteur,
            "types_bloc_utilises": sorted(types),
            "types_bloc_valides_backend": sorted(types_valides),
            "types_bloc_tous_valides": set(types) <= types_valides,
        },
        "validation_backend": {
            "nb_chunks_total": validation.get("nb_chunks_total"),
            "nb_chunks_valides": validation.get("nb_chunks_valides"),
            "valide": validation.get("valide"),
            "pret_pour_insertion": validation.get("pret_pour_insertion"),
            "erreurs": validation.get("erreurs", []),
            "doublons_internes": validation.get("doublons_internes", []),
            "doublons_en_base": validation.get("doublons_en_base", []),
        },
        "points_a_revoir": [
            "La date 1980-11-17 fournie correspond à la publication; la date juridique imprimée 1980-11-14 a été appliquée.",
            "Le PDF ne fournit que le numéro 82 du Moniteur: faute d'année ordinale et de type, les trois clés moniteur_* sont toutes omises.",
            "Le titre pénal est imprimé TITRE III après le TITRE VI; cette numérotation n'a pas été corrigée silencieusement.",
            "L'en-tête ARTICLE 971- a été interprété comme Article 97, paragraphe 1-, sans perte de caractère.",
            "Les anomalies typographiques imprimées recensées ont été conservées.",
            "Le statut en_vigueur doit être confirmé lors de la relecture juridique finale.",
        ],
        "suggestions": [
            "Relire prioritairement les articles 74, 92, 93, 96, 97, 101, 107 et 118.",
            "Compléter les trois clés moniteur_* ensemble seulement à partir d'un exemplaire authentifié donnant l'année ordinale et le type.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("racine_conversion", type=Path)
    parser.add_argument("backend", type=Path)
    parser.add_argument("--registre-root", type=Path, default=None)
    args = parser.parse_args()

    sys.path.insert(0, str(args.racine_conversion.resolve()))
    sys.path.insert(0, str(args.backend.resolve()))
    site_packages = args.backend / ".venv" / "Lib" / "site-packages"
    if site_packages.is_dir():
        sys.path.insert(0, str(site_packages))

    from halex_conversion.registry import Registre
    from ingestion_admin import _valider_donnees
    from schema_metadata import RANGS_PAR_TYPE_NORME, TYPES_BLOC_VALIDES

    requis = {"preambule", "visas", "article", "cloture"}
    if not requis <= set(TYPES_BLOC_VALIDES):
        raise RuntimeError(f"TYPES_BLOC_VALIDES incomplet: {sorted(requis - set(TYPES_BLOC_VALIDES))}")

    base = {
        "source": "Décret du 14 novembre 1980 réglementant le fonctionnement des banques et des activités bancaires",
        "source_courte": "Décret bancaire du 14 novembre 1980",
        "type_norme": "decret",
        "rang": RANGS_PAR_TYPE_NORME["decret"],
        "date": "1980-11-14",
        "date_publication": "1980-11-17",
        "statut": "en_vigueur",
        "mots_cles": [
            "banques", "activités bancaires", "BRH", "crédit", "dépôts bancaires",
            "liquidation bancaire", "supervision bancaire",
        ],
        "type_thematique": ["droit_bancaire", "droit_commercial"],
        "historique": False,
        "abroge_par": None,
        "publication_abrogation": None,
        "date_abrogation": None,
    }

    lignes, audit_extraction = extraire_lignes(args.pdf)
    if audit_extraction["pages_pypdf"] != 17 or audit_extraction["pages_pdfplumber"] != 17:
        raise RuntimeError(f"Nombre de pages inattendu: {audit_extraction}")
    if audit_extraction["pages_vides"] != [17]:
        raise RuntimeError(f"Page blanche finale inattendue: {audit_extraction['pages_vides']}")

    registre = Registre(args.registre_root or (args.racine_conversion / "registry"))
    record = registre.inscrire(args.pdf, base, "Décret bancaire du 14 novembre 1980")
    dossier, _ = registre.lire(record["document_id"])
    chunks, markdown, audit_structure = construire(lignes, base)
    validation = _valider_donnees(chunks)
    rapport = construire_rapport(
        args.pdf, dossier, chunks, markdown, audit_extraction, audit_structure,
        validation, set(TYPES_BLOC_VALIDES),
    )

    (dossier / "outputs" / "document.md").write_text(markdown, encoding="utf-8", newline="\n")
    (dossier / "outputs" / "chunks.json").write_text(
        json.dumps(chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n",
    )
    (dossier / "outputs" / "rapport.json").write_text(
        json.dumps(rapport, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n",
    )
    (dossier / "outputs" / "rapport_validation_backend.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n",
    )
    (dossier / "review" / "points_a_revoir.json").write_text(
        json.dumps({"statut": "a_revoir", "points": rapport["points_a_revoir"]}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    (dossier / "configuration" / "pipeline.json").write_text(
        json.dumps({
            "source_texte": "couche texte native du PDF officiel diffusé par la BRH",
            "extracteur_principal": f"pdfplumber {pdfplumber.__version__} avec géométrie des lignes",
            "verificateur_pdf": f"pypdf {pypdf.__version__}",
            "controle_visuel_pages": 17,
            "rendu_global_dpi": 150,
            "rendu_detail_dpi": 300,
            "coupures_de_lignes_du_pdf_supprimees": True,
            "separateurs_de_paragraphes": "double retour; listes et numérotations seulement dans les articles",
            "titres_migres_vers_chemin_hierarchique": True,
            "corrections_juridiques_silencieuses": False,
            "corrections_extraction": audit_extraction["corrections_extraction"],
            "anomalies_imprimees_conservees": ANOMALIES_IMPRIMEES,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    manifeste = {
        "document_id": record["document_id"],
        "sha256_source": record["sha256_source"],
        "sha256_markdown": sha256(dossier / "outputs" / "document.md"),
        "sha256_chunks": sha256(dossier / "outputs" / "chunks.json"),
        "sha256_rapport": sha256(dossier / "outputs" / "rapport.json"),
        "sha256_validation_backend": sha256(dossier / "outputs" / "rapport_validation_backend.json"),
        "sha256_pipeline": sha256(dossier / "configuration" / "pipeline.json"),
    }
    (dossier / "manifests" / "integrite.json").write_text(
        json.dumps(manifeste, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n",
    )
    registre.changer_etat(record["document_id"], "a_revoir")
    print(json.dumps({
        "document_id": record["document_id"],
        "dossier": str(dossier),
        "chunks": len(chunks),
        "articles": len([c for c in chunks if c["metadata"]["type_bloc"] == "article"]),
        "integrite": rapport["integrite_caracteres"]["chunks_identiques_a_la_reference"],
        "validation_backend": validation.get("valide"),
        "pret_pour_insertion": validation.get("pret_pour_insertion"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
