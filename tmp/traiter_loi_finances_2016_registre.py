#!/usr/bin/env python3
"""Structure la loi haïtienne sur l'élaboration et l'exécution des lois de finances."""
from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path

import pdfplumber
import pypdf


RACINE = (
    "LOI REMPLAÇANT LE DÉCRET DU 16 FÉVRIER 2005 SUR LE PROCESSUS "
    "D’ÉLABORATION ET D’EXÉCUTION DES LOIS DE FINANCES"
)
SOURCE = (
    "Loi remplaçant le décret du 16 février 2005 sur le processus "
    "d’élaboration et d’exécution des lois de finances"
)
SOURCE_COURTE = "Loi sur l’élaboration et l’exécution des lois de finances"
DATE_METADATA = "2017-02-01"
SHA256_SOURCE = "d83bdeba9df845f9b317ffe4ced661b633c73c5a64a58cb345dad80178a2e549"
NB_PAGES_PDF = 32
PAGES_LOI = tuple(range(4, 32))

ARTICLES_ATTENDUS = (
    [str(numero) for numero in range(1, 69)]
    + ["68.1", "68.2"]
    + [str(numero) for numero in range(69, 97)]
    + ["96.1"]
    + [str(numero) for numero in range(97, 118)]
)

STRUCTURES = {
    (5, "TITRE PREMIER"): (
        "titre", ["TITRE PREMIER", "DES PRINCIPES ET DÉFINITIONS"], 2,
    ),
    (5, "CHAPITRE I"): (
        "chapitre", ["CHAPITRE I", "DES DÉFINITIONS ET CONTENU DES LOIS DE FINANCES"], 2,
    ),
    (6, "CHAPITRE II"): (
        "chapitre", ["CHAPITRE II", "DES DISPOSITIONS GÉNÉRALES SUR LE BUDGET DE L’ÉTAT"], 2,
    ),
    (6, "Section 1 - Des dispositions du Budget Général"): (
        "section", ["Section 1 - Des dispositions du Budget Général"], 1,
    ),
    (6, "Section 2 - Des dispositions des Budgets Annexes"): (
        "section", ["Section 2 - Des dispositions des Budgets Annexes"], 1,
    ),
    (6, "Section 3 - Des dispositions des Comptes Spéciaux du Trésor"): (
        "section", ["Section 3 - Des dispositions des Comptes Spéciaux du Trésor"], 1,
    ),
    (7, "CHAPITRE III"): (
        "chapitre", ["CHAPITRE III", "DES RESSOURCES DE L’ÉTAT"], 2,
    ),
    (7, "Section 1 - Des dispositions générales"): (
        "section", ["Section 1 - Des dispositions générales"], 1,
    ),
    (9, "Section 2 - Des ressources affectées"): (
        "section", ["Section 2 - Des ressources affectées"], 1,
    ),
    (9, "CHAPITRE IV"): (
        "chapitre", ["CHAPITRE IV", "DES CHARGES DE L’ÉTAT"], 2,
    ),
    (9, "Section 1 - Des charges budgétaires"): (
        "section", ["Section 1 - Des charges budgétaires"], 1,
    ),
    (13, "Section 2 - Des charges de trésorerie"): (
        "section", ["Section 2 - Des charges de trésorerie"], 1,
    ),
    (13, "TITRE SECOND"): (
        "titre", ["TITRE SECOND", "DE L’IMPLÉMENTATION DES LOIS DE FINANCES"], 2,
    ),
    (13, "CHAPITRE V"): (
        "chapitre", ["CHAPITRE V", "DE L’ÉLABORATION ET DU VOTE DES LOIS DE FINANCES"], 2,
    ),
    (13, "Section 1 - De l’élaboration des lois de finances"): (
        "section", ["Section 1 - De l’élaboration des lois de finances"], 1,
    ),
    (16, "Section 2 - De l’examen et du vote des lois de finances"): (
        "section", ["Section 2 - De l’examen et du vote des lois de finances"], 1,
    ),
    (17, "Section 3 - Des lois de finances rectificatives"): (
        "section", ["Section 3 - Des lois de finances rectificatives"], 1,
    ),
    (17, "Section 4 - Des lois de règlement"): (
        "section", ["Section 4 - Des lois de règlement"], 1,
    ),
    (19, "CHAPITRE VI"): (
        "chapitre", ["CHAPITRE VI", "DE L’EXÉCUTION DES OPÉRATIONS BUDGÉTAIRES DE L’ÉTAT"], 2,
    ),
    (19, "Section 1 - De la régulation budgétaire"): (
        "section", ["Section 1 - De la régulation budgétaire"], 1,
    ),
    (20, "Section 2 - De l’exécution des recettes et des dépenses"): (
        "section", ["Section 2 - De l’exécution des recettes et des dépenses"], 1,
    ),
    (22, "Section 3 - De la prescription"): (
        "section", ["Section 3 - De la prescription"], 1,
    ),
    (23, "CHAPITRE VII"): (
        "chapitre", ["CHAPITRE VII", "DU CONTRÔLE DE L’EXÉCUTION DES LOIS DE FINANCES"], 2,
    ),
    (23, "Section 1 - Du contrôle interne par des organes administratifs"): (
        "section", ["Section 1 - Du contrôle interne par des organes administratifs"], 1,
    ),
    (24, "Section 2 - Du contrôle administratif et juridictionnel de la Cour Supérieure des Comptes et du Contentieux"): (
        "section",
        [
            "Section 2 - Du contrôle administratif et juridictionnel de la Cour Supérieure des Comptes et du Contentieux",
            "Administratif",
        ],
        2,
    ),
    (25, "Section 3 - Du contrôle parlementaire"): (
        "section", ["Section 3 - Du contrôle parlementaire"], 1,
    ),
    (25, "CHAPITRE VIII"): (
        "chapitre", ["CHAPITRE VIII", "DES RESPONSABILITÉS EN MATIÈRE D’EXÉCUTION DES BUDGETS PUBLICS"], 2,
    ),
    (25, "Section 1 - Des responsabilités générales"): (
        "section", ["Section 1 - Des responsabilités générales"], 1,
    ),
    (26, "Section 2 - De la responsabilité des ordonnateurs"): (
        "section", ["Section 2 - De la responsabilité des ordonnateurs"], 1,
    ),
    (28, "Section 3 - De la responsabilité des contrôleurs financiers"): (
        "section", ["Section 3 - De la responsabilité des contrôleurs financiers"], 1,
    ),
    (28, "Section 4 - De la responsabilité des comptables publics"): (
        "section", ["Section 4 - De la responsabilité des comptables publics"], 1,
    ),
    (30, "CHAPITRE IX"): (
        "chapitre", ["CHAPITRE IX", "DES DISPOSITIONS TRANSITOIRES ET FINALES"], 2,
    ),
}

# Les libellés structuraux sont imposés uniquement dans les zones contrôlées
# sur les rendus 300 dpi. Le corps juridique reste issu de l'OCR corrigé.
STRUCTURES_PAR_ZONE = {
    (5, 1190, 1240): "TITRE PREMIER",
    (5, 1260, 1310): "DES PRINCIPES ET DÉFINITIONS",
    (5, 1360, 1410): "CHAPITRE I",
    (5, 1430, 1480): "DES DÉFINITIONS ET CONTENU DES LOIS DE FINANCES",
    (6, 1240, 1290): "CHAPITRE II",
    (6, 1330, 1380): "DES DISPOSITIONS GÉNÉRALES SUR LE BUDGET DE L’ÉTAT",
    (6, 1440, 1490): "Section 1 - Des dispositions du Budget Général",
    (6, 1670, 1720): "Section 2 - Des dispositions des Budgets Annexes",
    (6, 2070, 2120): "Section 3 - Des dispositions des Comptes Spéciaux du Trésor",
    (7, 1060, 1110): "CHAPITRE III",
    (7, 1150, 1200): "DES RESSOURCES DE L’ÉTAT",
    (7, 1260, 1305): "Section 1 - Des dispositions générales",
    (9, 320, 370): "Section 2 - Des ressources affectées",
    (9, 1900, 1960): "CHAPITRE IV",
    (9, 1990, 2045): "DES CHARGES DE L’ÉTAT",
    (9, 2110, 2165): "Section 1 - Des charges budgétaires",
    (13, 330, 380): "Section 2 - Des charges de trésorerie",
    (13, 820, 875): "TITRE SECOND",
    (13, 895, 950): "DE L’IMPLÉMENTATION DES LOIS DE FINANCES",
    (13, 1005, 1055): "CHAPITRE V",
    (13, 1080, 1135): "DE L’ÉLABORATION ET DU VOTE DES LOIS DE FINANCES",
    (13, 1185, 1240): "Section 1 - De l’élaboration des lois de finances",
    (16, 1070, 1125): "Section 2 - De l’examen et du vote des lois de finances",
    (17, 1330, 1380): "Section 3 - Des lois de finances rectificatives",
    (17, 1900, 1950): "Section 4 - Des lois de règlement",
    (19, 1230, 1280): "CHAPITRE VI",
    (19, 1315, 1370): "DE L’EXÉCUTION DES OPÉRATIONS BUDGÉTAIRES DE L’ÉTAT",
    (19, 1425, 1480): "Section 1 - De la régulation budgétaire",
    (20, 320, 370): "Section 2 - De l’exécution des recettes et des dépenses",
    (22, 870, 925): "Section 3 - De la prescription",
    (23, 300, 350): "CHAPITRE VII",
    (23, 390, 440): "DU CONTRÔLE DE L’EXÉCUTION DES LOIS DE FINANCES",
    (23, 1175, 1230): "Section 1 - Du contrôle interne par des organes administratifs",
    (24, 980, 1035): "Section 2 - Du contrôle administratif et juridictionnel de la Cour Supérieure des Comptes et du Contentieux",
    (24, 1035, 1090): "Administratif",
    (25, 850, 905): "Section 3 - Du contrôle parlementaire",
    (25, 2080, 2135): "CHAPITRE VIII",
    (25, 2150, 2205): "DES RESPONSABILITÉS EN MATIÈRE D’EXÉCUTION DES BUDGETS PUBLICS",
    (25, 2265, 2320): "Section 1 - Des responsabilités générales",
    (26, 1695, 1750): "Section 2 - De la responsabilité des ordonnateurs",
    (28, 1650, 1705): "Section 3 - De la responsabilité des contrôleurs financiers",
    (28, 2205, 2260): "Section 4 - De la responsabilité des comptables publics",
    (30, 1080, 1135): "CHAPITRE IX",
    (30, 1190, 1245): "DES DISPOSITIONS TRANSITOIRES ET FINALES",
}

REMPLACEMENTS_OCR = (
    ("Article L7.-", "Article 17.-"),
    ("Article 68.1. |", "Article 68.1.-"),
    ("Article 101.- |", "Article 101.-"),
    ("Article 102.- |", "Article 102.-"),
    ("Article 112. |", "Article 112.-"),
    ("Article 113.- |", "Article 113.-"),
    ("Article 116.- |", "Article 116.-"),
    ("Laloi", "La loi"),
    ("Is sont présentés", "Ils sont présentés"),
    ("Is sont pris", "Ils sont pris"),
    ("I! s’assure", "Il s’assure"),
    ("finances. II", "finances. Il"),
    ("Être engagées", "être engagées"),
    (". de justice,", "de justice,"),
    ("mise enjeu", "mise en jeu"),
    ("uncadre budgétaire", "un cadre budgétaire"),
    ("n’auraiènt", "n’auraient"),
    ("1‘ mai", "1er mai"),
    ("1“ novembre", "1er novembre"),
    ("I” juin", "1er juin"),
    ("2°\"lundi", "2ème lundi"),
    ("Promuigation", "Promulgation"),
    ("l’article 41.\"", "l’article 41."),
    ("Dès contrôles de la performance", "Des contrôles de la performance"),
    ("finances. II assure", "finances. Il assure"),
    ("branches du Parlement, le contrôle", "branches du Parlement, le contrôle"),
    ("publiques. II est en droit", "publiques. Il est en droit"),
    ("cumptable entrant", "comptable entrant"),
    ("Ministre chargé des Financés", "Ministre chargé des Finances"),
    ("l’ Administration", "l’Administration"),
)

RE_ARTICLE = re.compile(r"^Article\s+(\d+(?:\.\d+)?)\.-(?:\s*(.*))?$")
RE_ENUMERATION = re.compile(
    r"^(?:•\s+|\d+\s*(?:[.)-])\s+|[a-zA-Z]\)\s+|[IVXLCDM]+\)\s+|-\s+)"
)
RE_CALENDRIER = re.compile(
    r"^(?:Premier lundi|Au plus(?: tard| le)?\b|Du\s+\d|\d+(?:er|ème)?\s+(?:avril|mai)|"
    r"Quatrième lundi|15 février|Entre le\s+)"
)
RE_DEBUT_VISA = re.compile(r"^(?:Vu\s|Considérant\s|Sur proposition\s)")

CLOTURE_PARAGRAPHES = [
    "Donnée au Sénat de la République le mercredi 12 mai 2014, An 211e de l’Indépendance.",
    "Ronald LARECHEY",
    "Président a.i du Sénat",
    "François Lucas SAINVIL",
    "Premier Secrétaire",
    "Steven Irvenson BENOIT",
    "Deuxième Secrétaire",
    "Donnée à la Chambre des Députés le mercredi 4 mai 2016, An 213ème de l’Indépendance.",
    "Cholzer CHANCY",
    "Président",
    "Abel DESCOLLINES",
    "Premier Secrétaire",
    "Hermano EXINORD",
    "Deuxième Secrétaire",
    "LIBERTÉ ÉGALITÉ FRATERNITÉ",
    "RÉPUBLIQUE D’HAÏTI",
    "AU NOM DE LA RÉPUBLIQUE",
    "Par les présentes,",
    (
        "Le Président de la République ordonne que la loi remplaçant le décret du 16 février 2005 "
        "sur le processus d’élaboration et d’exécution des lois de finances, votée au Sénat de la "
        "République, le 12 mai 2014 et à la Chambre des Députés le 4 mai 2016, soit revêtue du sceau "
        "de la République, imprimée, publiée et exécutée."
    ),
    "Donné au Palais National, à Port-au-Prince, le 23 janvier 2017, An 214e de l’Indépendance.",
    "Jocelerme PRIVERT",
    "Président Provisoire de la République",
]


@dataclass(frozen=True)
class Segment:
    top: int
    bottom: int
    x0: int
    x1: int
    confiance: float
    texte: str

    @property
    def centre(self) -> float:
        return (self.top + self.bottom) / 2


@dataclass(frozen=True)
class Ligne:
    page: int
    top: int
    x0: int
    confiance: float
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


def sha256_dossier(dossier: Path, motif: str) -> str:
    digest = hashlib.sha256()
    for path in sorted(dossier.glob(motif)):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def nettoyer_espaces(texte: str) -> str:
    return re.sub(r"[ \t]+", " ", texte).strip()


def charger_segments(path: Path) -> list[Segment]:
    groupes: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    with path.open("r", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if row.get("level") != "5" or not (row.get("text") or "").strip():
                continue
            groupes[(row["block_num"], row["par_num"], row["line_num"])].append(row)
    segments: list[Segment] = []
    for mots in groupes.values():
        mots.sort(key=lambda row: int(row["left"]))
        top = min(int(row["top"]) for row in mots)
        bottom = max(int(row["top"]) + int(row["height"]) for row in mots)
        x0 = min(int(row["left"]) for row in mots)
        x1 = max(int(row["left"]) + int(row["width"]) for row in mots)
        confiance = sum(float(row["conf"]) for row in mots) / len(mots)
        texte = nettoyer_espaces(" ".join(row["text"] for row in mots))
        segments.append(Segment(top, bottom, x0, x1, confiance, texte))
    return sorted(segments, key=lambda item: (item.centre, item.x0))


def fusionner_segments(page: int, segments: list[Segment]) -> list[Ligne]:
    groupes: list[list[Segment]] = []
    for segment in segments:
        if groupes:
            centre = sum(item.centre for item in groupes[-1]) / len(groupes[-1])
            if abs(segment.centre - centre) <= 17:
                groupes[-1].append(segment)
                continue
        groupes.append([segment])
    lignes: list[Ligne] = []
    for groupe in groupes:
        groupe.sort(key=lambda item: item.x0)
        lignes.append(
            Ligne(
                page=page,
                top=min(item.top for item in groupe),
                x0=min(item.x0 for item in groupe),
                confiance=sum(item.confiance for item in groupe) / len(groupe),
                texte=nettoyer_espaces(" ".join(item.texte for item in groupe)),
            )
        )
    return lignes


def corriger_ligne(ligne: Ligne, audit: list[dict]) -> Ligne | None:
    # Les en-têtes du Moniteur et leur filet décoratif occupent les 300 premiers
    # pixels de chaque rendu 300 dpi. Le corps commence au plus tôt à y=309.
    if ligne.top < 300:
        return None
    original = ligne.texte
    texte = original
    for (page, minimum, maximum), impose in STRUCTURES_PAR_ZONE.items():
        if ligne.page == page and minimum <= ligne.top <= maximum:
            texte = impose
            break
    for avant, apres in REMPLACEMENTS_OCR:
        if avant in texte:
            texte = texte.replace(avant, apres)
    # Les puces rondes sont confondues par l'OCR avec e, «, », + ou *.
    texte = re.sub(r"^(?:e|«|»|\+|\*)\s+", "• ", texte)
    texte = nettoyer_espaces(texte)
    if texte != original:
        audit.append(
            {
                "page_pdf": ligne.page,
                "top_300dpi": ligne.top,
                "avant": original,
                "apres": texte,
                "raison": "correction OCR ou libellé structural vérifié sur le rendu 300 dpi",
            }
        )
    return replace(
        ligne,
        texte=texte,
        forcer_paragraphe=bool(RE_ENUMERATION.match(texte) or RE_CALENDRIER.match(texte)),
    )


def charger_lignes(ocr_dir: Path) -> tuple[list[Ligne], dict]:
    fichiers = sorted(ocr_dir.glob("page-*.tsv"))
    if len(fichiers) != len(PAGES_LOI):
        raise RuntimeError(f"{len(PAGES_LOI)} TSV OCR attendus, {len(fichiers)} trouvés")
    pages = [int(re.search(r"(\d+)$", path.stem).group(1)) for path in fichiers]
    if pages != list(PAGES_LOI):
        raise RuntimeError(f"Pages OCR inattendues: {pages}")
    lignes: list[Ligne] = []
    corrections: list[dict] = []
    lignes_brutes = 0
    lignes_exclues = 0
    faibles: list[dict] = []
    for path, page in zip(fichiers, pages):
        page_lignes = fusionner_segments(page, charger_segments(path))
        lignes_brutes += len(page_lignes)
        for ligne in page_lignes:
            corrigee = corriger_ligne(ligne, corrections)
            if corrigee is None:
                lignes_exclues += 1
                continue
            lignes.append(corrigee)
            if corrigee.confiance < 80 and not corrigee.texte.startswith(("TITRE", "CHAPITRE")):
                faibles.append(
                    {
                        "page_pdf": page,
                        "top_300dpi": ligne.top,
                        "confiance": round(corrigee.confiance, 2),
                        "texte": corrigee.texte,
                    }
                )
    return lignes, {
        "fichiers_tsv": len(fichiers),
        "pages": pages,
        "lignes_brutes": lignes_brutes,
        "lignes_retenues": len(lignes),
        "lignes_entete_et_filet_exclues": lignes_exclues,
        "corrections": corrections,
        "lignes_faible_confiance_retenues": faibles,
        "sha256_tsv": sha256_dossier(ocr_dir, "page-*.tsv"),
    }


def parser_article(texte: str) -> dict | None:
    match = RE_ARTICLE.match(texte)
    if not match:
        return None
    return {
        "numero": match.group(1),
        "etiquette": f"Article {match.group(1)}.-",
        "corps": nettoyer_espaces(match.group(2) or ""),
    }


def construire_structures(lignes: list[Ligne], limite: int) -> list[Evenement]:
    evenements: list[Evenement] = []
    for index, ligne in enumerate(lignes[:limite]):
        definition = STRUCTURES.get((ligne.page, ligne.texte))
        if not definition:
            continue
        niveau, segments, longueur = definition
        observees = [item.texte for item in lignes[index : index + longueur]]
        if observees != segments:
            raise RuntimeError(
                f"Structure inattendue page {ligne.page}: {observees!r} != {segments!r}"
            )
        evenements.append(
            Evenement(index, index + longueur, "structure", {
                "niveau": niveau,
                "segments": segments,
                "lignes": observees,
                "page_pdf": ligne.page,
            })
        )
    if len(evenements) != len(STRUCTURES):
        trouvees = [(event.donnees["page_pdf"], event.donnees["segments"]) for event in evenements]
        raise RuntimeError(
            f"{len(STRUCTURES)} structures attendues, {len(evenements)} trouvées: {trouvees}"
        )
    return evenements


def ajouter_fragment(courant: list[str], texte: str) -> None:
    if not texte:
        return
    if courant and courant[-1].endswith("-") and re.match(r"^[a-zàâçéèêëîïôùûüœ]", texte):
        courant[-1] = courant[-1][:-1] + texte
    else:
        courant.append(texte)


def formater_lignes(
    lignes: list[Ligne],
    article: dict | None = None,
    type_bloc: str = "article",
) -> str:
    travail = list(lignes)
    etiquette = ""
    if article:
        etiquette = article["etiquette"]
        travail[0] = replace(travail[0], texte=article["corps"])
    paragraphes: list[str] = []
    courant: list[str] = []
    precedente: Ligne | None = None
    for ligne in travail:
        texte = ligne.texte
        if not texte:
            continue
        nouveau = False
        if courant:
            if type_bloc == "article":
                ecart = (
                    ligne.top - precedente.top
                    if precedente is not None and ligne.page == precedente.page
                    else 0
                )
                nouveau = bool(ligne.forcer_paragraphe or ecart >= 75)
            elif type_bloc == "visas":
                nouveau = bool(RE_DEBUT_VISA.match(texte))
            elif type_bloc in {"preambule", "cloture"}:
                nouveau = True
            incomplet_calendrier = (
                (" ".join(courant) == "Au plus tard" and texte.startswith("premier lundi"))
                or (
                    " ".join(courant) == "Au plus tard le troisième"
                    and texte.startswith("vendredi")
                )
            )
            if incomplet_calendrier:
                nouveau = False
        if nouveau:
            paragraphes.append(" ".join(courant))
            courant = []
        ajouter_fragment(courant, texte)
        precedente = ligne
    if courant:
        paragraphes.append(" ".join(courant))
    corps = "\n\n".join(paragraphe.strip() for paragraphe in paragraphes if paragraphe.strip())
    return f"{etiquette}\n\n{corps}" if etiquette else corps


def chemin_et_metadata(etat: dict) -> tuple[str, dict]:
    chemin = [RACINE]
    extra: dict = {}
    for niveau in ("titre", "chapitre", "section"):
        segments = etat.get(niveau) or []
        if segments:
            chemin.extend(segments)
            extra[niveau] = " > ".join(segments)
    return " > ".join(chemin), extra


def sequence_reference(lignes: list[str]) -> str:
    fragments: list[str] = []
    for texte in lignes:
        if fragments and fragments[-1].endswith("-") and re.match(r"^[a-zàâçéèêëîïôùûüœ]", texte):
            fragments[-1] = fragments[-1][:-1] + texte
        else:
            fragments.append(texte)
    return re.sub(r"\s+", "", " ".join(fragments))


def construire(lignes: list[Ligne], base: dict) -> tuple[list[dict], str, dict]:
    articles = [
        (index, parser_article(ligne.texte))
        for index, ligne in enumerate(lignes)
        if parser_article(ligne.texte)
    ]
    numeros = [article["numero"] for _, article in articles]
    if numeros != ARTICLES_ATTENDUS:
        manquants = [numero for numero in ARTICLES_ATTENDUS if numero not in numeros]
        inattendus = [numero for numero in numeros if numero not in ARTICLES_ATTENDUS]
        raise RuntimeError(
            f"Articles inattendus; trouvés={numeros}, manquants={manquants}, inattendus={inattendus}"
        )
    index_preambule = next(
        i for i, ligne in enumerate(lignes)
        if ligne.page == 4 and ligne.texte == "LIBERTÉ ÉGALITÉ FRATERNITÉ"
    )
    index_visas = next(i for i, ligne in enumerate(lignes) if ligne.texte.startswith("Vu les articles 217"))
    index_cloture = next(i for i, ligne in enumerate(lignes) if ligne.texte.startswith("Donnée au Sénat"))
    structures = construire_structures(lignes, index_cloture)

    evenements: dict[int, Evenement] = {
        index_preambule: Evenement(index_preambule, index_visas, "preambule", {}),
        index_visas: Evenement(index_visas, 0, "visas", {}),
        index_cloture: Evenement(index_cloture, len(lignes), "cloture", {}),
    }
    for position, article in articles:
        evenements[position] = Evenement(position, 0, "article", {"article": article})
    for structure in structures:
        evenements[structure.debut] = structure
    positions = sorted(evenements)
    for index, position in enumerate(positions):
        evenement = evenements[position]
        if evenement.type != "structure":
            evenement.fin = positions[index + 1] if index + 1 < len(positions) else len(lignes)

    chunks: list[dict] = []
    markdown: list[str] = []
    etat = {"titre": [], "chapitre": [], "section": []}
    indices_structure = {
        index
        for evenement in structures
        for index in range(evenement.debut, evenement.fin)
    }

    def ajouter(
        contenu: str,
        article: str,
        type_bloc: str,
        chemin: str,
        extra: dict | None = None,
    ) -> None:
        chunks.append(
            {
                "page_content": contenu,
                "metadata": {
                    **base,
                    "article": article,
                    "type_bloc": type_bloc,
                    "ordre": len(chunks) + 1,
                    "chemin_hierarchique": chemin,
                    **(extra or {}),
                },
            }
        )
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
        bloc = lignes[evenement.debut : evenement.fin]
        if evenement.type == "preambule":
            ajouter(
                formater_lignes(bloc, type_bloc="preambule"),
                "Préambule",
                "preambule",
                f"{RACINE} > PRÉAMBULE",
            )
        elif evenement.type == "visas":
            ajouter(
                formater_lignes(bloc, type_bloc="visas"),
                "Visas",
                "visas",
                f"{RACINE} > VISAS",
            )
        elif evenement.type == "article":
            article = evenement.donnees["article"]
            chemin, extra = chemin_et_metadata(etat)
            ajouter(
                formater_lignes(bloc, article=article, type_bloc="article"),
                f"Article {article['numero']}",
                "article",
                chemin,
                extra,
            )
        elif evenement.type == "cloture":
            contenu = "\n\n".join(CLOTURE_PARAGRAPHES)
            ajouter(contenu, "Clôture", "cloture", f"{RACINE} > CLÔTURE")

    reference = [
        ligne.texte
        for index, ligne in enumerate(lignes[index_preambule:index_cloture], index_preambule)
        if index not in indices_structure
    ] + CLOTURE_PARAGRAPHES
    reference_complete = [
        ligne.texte for ligne in lignes[index_preambule:index_cloture]
    ] + CLOTURE_PARAGRAPHES
    return chunks, "\n\n".join(markdown) + "\n", {
        "articles": numeros,
        "structures": [event.donnees for event in structures],
        "reference_chunks": reference,
        "reference_complete": reference_complete,
    }


def sequence_ocr_dossier(dossier: Path) -> str:
    textes: list[str] = []
    for path in sorted(dossier.glob("page-*.tsv")):
        with path.open("r", encoding="utf-8", newline="") as stream:
            textes.extend(
                row["text"]
                for row in csv.DictReader(stream, delimiter="\t")
                if row.get("level") == "5" and (row.get("text") or "").strip()
            )
    return re.sub(r"\s+", "", "".join(textes))


def construire_rapport(
    pdf: Path,
    dossier: Path,
    chunks: list[dict],
    markdown: str,
    audit_ocr: dict,
    audit_structure: dict,
    validation: dict,
    types_valides: set[str],
    ocr_dir: Path,
    contre_ocr_dir: Path | None,
) -> dict:
    types = Counter(chunk["metadata"]["type_bloc"] for chunk in chunks)
    articles = [chunk for chunk in chunks if chunk["metadata"]["type_bloc"] == "article"]
    reference = sequence_reference(audit_structure["reference_chunks"])
    contenu = re.sub(r"\s+", "", "".join(chunk["page_content"] for chunk in chunks))
    reference_markdown = sequence_reference(audit_structure["reference_complete"])
    contenu_markdown = re.sub(r"\s+", "", markdown)
    integrite = reference == contenu
    retours_simples = sum(
        len(re.findall(r"(?<!\n)\n(?!\n)", chunk["page_content"]))
        for chunk in articles
    )
    comparaison_ocr = None
    if contre_ocr_dir and contre_ocr_dir.is_dir():
        principal = sequence_ocr_dossier(ocr_dir)
        secondaire = sequence_ocr_dossier(contre_ocr_dir)
        comparaison_ocr = {
            "modele_principal": "Tesseract tessdata_best français, PSM 6",
            "modele_secondaire": "Tesseract tessdata_fast français, PSM 3",
            "similarite_sequence": round(
                difflib.SequenceMatcher(None, principal, secondaire).ratio(), 6
            ),
            "sha256_tsv_secondaire": sha256_dossier(contre_ocr_dir, "page-*.tsv"),
        }
    articles_introuvables = [
        numero for numero in ARTICLES_ATTENDUS if numero not in audit_structure["articles"]
    ]
    doublons = sorted(
        numero
        for numero, compte in Counter(audit_structure["articles"]).items()
        if compte > 1
    )
    return {
        "statut": "conforme_techniquement_a_relecture_humaine",
        "source": {
            "pdf": str(pdf.resolve()),
            "sha256": sha256(pdf),
            "pages_pdf": NB_PAGES_PDF,
            "pages_retenues": "pages PDF 4 à 31",
            "pages_exclues": {
                "1_a_3": "autre loi du même numéro du Moniteur: modification de l’article 29 de la loi organique de la Police nationale d’Haïti",
                "32": "communiqué conjoint MPCE, MICT et MAE, étranger à la loi traitée",
            },
            "couche_texte_native": False,
            "publication": "Le Moniteur, 172e Année, Spécial No 5, mercredi 1er février 2017",
            "vote_chambre_deputes": "2016-05-04",
            "promulgation": "2017-01-23",
            "date_metadata_imposee": DATE_METADATA,
            "verification_visuelle": "32 pages contrôlées sur planches-contact; pages 4 à 31 contrôlées sur rendus 300 dpi pour la structure et les zones ambiguës",
            "ocr": {
                "principal": "Tesseract LSTM tessdata_best français sur rendu Poppler 300 dpi",
                "contre_lecture": comparaison_ocr,
                "fichiers_tsv": audit_ocr["fichiers_tsv"],
                "lignes_faible_confiance_retenues": audit_ocr["lignes_faible_confiance_retenues"],
            },
        },
        "sorties": {
            "dossier_registre": str(dossier.resolve()),
            "markdown": "outputs/document.md",
            "chunks": "outputs/chunks.json",
            "rapport_validation_backend": "outputs/rapport_validation_backend.json",
        },
        "chunks": {
            "prevus": 123,
            "trouves": len(chunks),
            "ecart": len(chunks) - 123,
            "par_type_bloc": dict(sorted(types.items())),
        },
        "articles": {
            "prevus": len(ARTICLES_ATTENDUS),
            "trouves": len(articles),
            "numeros": audit_structure["articles"],
            "articles_introuvables": articles_introuvables,
            "doublons": doublons,
            "articles_decimaux": ["68.1", "68.2", "96.1"],
        },
        "hierarchie": {
            "groupes_structuraux_prevus": len(STRUCTURES),
            "groupes_structuraux_trouves": len(audit_structure["structures"]),
            "tous_chunks_avec_chemin_hierarchique": all(
                bool(chunk["metadata"].get("chemin_hierarchique")) for chunk in chunks
            ),
            "niveaux": dict(
                Counter(item["niveau"] for item in audit_structure["structures"])
            ),
            "exemples": {
                label: next(
                    chunk["metadata"]["chemin_hierarchique"]
                    for chunk in chunks
                    if chunk["metadata"]["article"] == label
                )
                for label in ("Article 1", "Article 17", "Article 42", "Article 68.1", "Article 96.1", "Article 117")
            },
        },
        "integrite_caracteres": {
            "methode": "comparaison de séquence entre l’OCR principal corrigé et les chunks; seuls espaces, retours de ligne et césures typographiques sont neutralisés",
            "reference_corrigee_hors_espaces": len(reference),
            "chunks_hors_espaces": len(contenu),
            "chunks_identiques_a_la_reference_corrigee": integrite,
            "caracteres_manquants_detectes_par_la_comparaison": 0 if integrite else None,
            "caracteres_ajoutes_detectes_par_la_comparaison": 0 if integrite else None,
            "markdown_incluant_structures_identique": reference_markdown == contenu_markdown,
            "limite": "le PDF est une image; l’égalité est établie contre la transcription OCR corrigée, pas contre une couche texte native inexistante",
        },
        "mise_en_page": {
            "retours_ligne_simples_dans_articles": retours_simples,
            "regle": "aucun retour simple; doubles retours uniquement pour alinéas, listes, numérotations et tableaux calendaires",
        },
        "metadata": {
            "historique_false_partout": all(
                chunk["metadata"].get("historique") is False for chunk in chunks
            ),
            "moniteur_tout_ou_rien": all(
                all(cle in chunk["metadata"] for cle in ("moniteur_annee", "moniteur_numero", "moniteur_type"))
                for chunk in chunks
            ),
            "moniteur_annee": 172,
            "moniteur_numero": "5",
            "moniteur_type": "special",
            "date": DATE_METADATA,
            "types_bloc_valides_backend": sorted(types_valides),
            "types_bloc_produits_tous_valides": set(types) <= types_valides,
        },
        "validation_backend": validation,
        "audit_ocr": {
            "lignes_brutes": audit_ocr["lignes_brutes"],
            "lignes_retenues": audit_ocr["lignes_retenues"],
            "lignes_entete_et_filet_exclues": audit_ocr["lignes_entete_et_filet_exclues"],
            "corrections_documentees": audit_ocr["corrections"],
        },
        "points_a_revoir": [
            {
                "priorite": "haute",
                "portee": "ensemble des pages 4 à 31",
                "motif": "PDF image sans couche texte; une relecture humaine caractère par caractère reste nécessaire avant insertion définitive",
            },
            {
                "priorite": "moyenne",
                "portee": "page PDF 31",
                "motif": "noms et qualités des six signataires législatifs ont été rétablis après contrôle visuel du rendu 300 dpi",
            },
            {
                "priorite": "moyenne",
                "portee": "articles 44 et 58",
                "motif": "calendriers convertis en paragraphes structurés; vérifier la correspondance visuelle des libellés et échéances",
            },
            {
                "priorite": "basse",
                "portee": "pages PDF 1 à 3 et 32",
                "motif": "contenus étrangers à la loi ciblée exclus intentionnellement et consignés dans le rapport",
            },
        ],
        "suggestions": [
            "Relire prioritairement les lignes signalées à faible confiance et les tableaux calendaires des articles 44 et 58.",
            "Conserver l’état a_revoir jusqu’à validation humaine du Markdown et du JSON côte à côte avec le PDF.",
            "Après validation humaine, faire passer le document à chunks_valides puis pret_ingestion dans le registre.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("racine_conversion", type=Path)
    parser.add_argument("backend", type=Path)
    parser.add_argument("--ocr-dir", type=Path, required=True)
    parser.add_argument("--ocr-contre-dir", type=Path, default=None)
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
        raise RuntimeError(
            f"TYPES_BLOC_VALIDES incomplet: {sorted(requis - set(TYPES_BLOC_VALIDES))}"
        )
    if sha256(args.pdf) != SHA256_SOURCE:
        raise RuntimeError("Empreinte SHA-256 du PDF inattendue")
    with args.pdf.open("rb") as stream:
        pages_pypdf = len(pypdf.PdfReader(stream).pages)
    with pdfplumber.open(args.pdf) as document:
        pages_pdfplumber = len(document.pages)
        caracteres_natifs = sum(len(page.extract_text() or "") for page in document.pages)
    if (
        pages_pypdf != NB_PAGES_PDF
        or pages_pdfplumber != NB_PAGES_PDF
        or caracteres_natifs != 0
    ):
        raise RuntimeError(
            "Source PDF inattendue: "
            f"pypdf={pages_pypdf}, pdfplumber={pages_pdfplumber}, texte={caracteres_natifs}"
        )

    base = {
        "source": SOURCE,
        "source_courte": SOURCE_COURTE,
        "type_norme": "loi",
        "rang": RANGS_PAR_TYPE_NORME["loi"],
        "date": DATE_METADATA,
        "statut": "en_vigueur",
        "moniteur_annee": 172,
        "moniteur_numero": "5",
        "moniteur_type": "special",
        "mots_cles": [
            "lois de finances",
            "budget de l’État",
            "finances publiques",
            "exécution budgétaire",
            "contrôle parlementaire",
            "comptabilité publique",
            "Cour Supérieure des Comptes et du Contentieux Administratif",
        ],
        "type_thematique": ["droit_fiscal", "droit_administratif", "marches_publics"],
        "historique": False,
    }

    lignes, audit_ocr = charger_lignes(args.ocr_dir)
    chunks, markdown, audit_structure = construire(lignes, base)
    validation = _valider_donnees(chunks)
    registre = Registre(args.registre_root or (args.racine_conversion / "registry"))
    record = registre.inscrire(args.pdf, base, SOURCE_COURTE)
    dossier, _ = registre.lire(record["document_id"])
    rapport = construire_rapport(
        args.pdf,
        dossier,
        chunks,
        markdown,
        audit_ocr,
        audit_structure,
        validation,
        set(TYPES_BLOC_VALIDES),
        args.ocr_dir,
        args.ocr_contre_dir,
    )

    extraction_principale = dossier / "extraction" / "ocr_best_tsv"
    extraction_principale.mkdir(parents=True, exist_ok=True)
    for path in sorted(args.ocr_dir.glob("page-*.tsv")):
        shutil.copy2(path, extraction_principale / path.name)
    if args.ocr_contre_dir and args.ocr_contre_dir.is_dir():
        extraction_secondaire = dossier / "extraction" / "ocr_fast_tsv"
        extraction_secondaire.mkdir(parents=True, exist_ok=True)
        for path in sorted(args.ocr_contre_dir.glob("page-*.tsv")):
            shutil.copy2(path, extraction_secondaire / path.name)

    (dossier / "outputs" / "document.md").write_text(
        markdown, encoding="utf-8", newline="\n"
    )
    (dossier / "outputs" / "chunks.json").write_text(
        json.dumps(chunks, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (dossier / "outputs" / "rapport.json").write_text(
        json.dumps(rapport, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (dossier / "outputs" / "rapport_validation_backend.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (dossier / "review" / "points_a_revoir.json").write_text(
        json.dumps(
            {"statut": "a_revoir", "points": rapport["points_a_revoir"]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (dossier / "configuration" / "pipeline.json").write_text(
        json.dumps(
            {
                "source_texte": "PDF image sans couche texte",
                "pages_pdf": NB_PAGES_PDF,
                "pages_retenues": list(PAGES_LOI),
                "pages_exclues": [1, 2, 3, 32],
                "ocr_principal": "Tesseract LSTM tessdata_best français, PSM 6, rendu Poppler 300 dpi",
                "ocr_contre_lecture": "Tesseract LSTM tessdata_fast français, PSM 3, même rendu",
                "rendu_global_dpi": 150,
                "rendu_ocr_et_detail_dpi": 300,
                "entetes_moniteur_et_filets_exclus": True,
                "coupures_de_lignes_et_cesures_supprimees": True,
                "separateurs_dans_articles": "double retour pour alinéas, listes, numérotations et tableaux calendaires",
                "titres_migres_vers_chemin_hierarchique": True,
                "corrections_juridiques_silencieuses": False,
                "corrections_ocr": audit_ocr["corrections"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    manifeste = {
        "document_id": record["document_id"],
        "sha256_source": record["sha256_source"],
        "sha256_ocr_best_tsv": sha256_dossier(extraction_principale, "page-*.tsv"),
        "sha256_markdown": sha256(dossier / "outputs" / "document.md"),
        "sha256_chunks": sha256(dossier / "outputs" / "chunks.json"),
        "sha256_rapport": sha256(dossier / "outputs" / "rapport.json"),
        "sha256_validation_backend": sha256(
            dossier / "outputs" / "rapport_validation_backend.json"
        ),
        "sha256_pipeline": sha256(dossier / "configuration" / "pipeline.json"),
    }
    (dossier / "manifests" / "integrite.json").write_text(
        json.dumps(manifeste, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    registre.changer_etat(record["document_id"], "a_revoir")
    print(
        json.dumps(
            {
                "document_id": record["document_id"],
                "dossier": str(dossier),
                "chunks": len(chunks),
                "articles": len(articles := [
                    chunk
                    for chunk in chunks
                    if chunk["metadata"]["type_bloc"] == "article"
                ]),
                "articles_premier_et_dernier": [
                    articles[0]["metadata"]["article"],
                    articles[-1]["metadata"]["article"],
                ],
                "integrite": rapport["integrite_caracteres"][
                    "chunks_identiques_a_la_reference_corrigee"
                ],
                "validation_backend": validation.get("valide"),
                "pret_pour_insertion": validation.get("pret_pour_insertion"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
