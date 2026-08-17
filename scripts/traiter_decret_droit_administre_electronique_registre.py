#!/usr/bin/env python3
"""Structure le décret haïtien du 6 janvier 2016 sur l'administration électronique."""
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
    "DÉCRET RECONNAISSANT LE DROIT DE TOUT ADMINISTRÉ À S’ADRESSER À "
    "L’ADMINISTRATION PUBLIQUE PAR DES MOYENS ÉLECTRONIQUES"
)

STRUCTURES = {
    (3, "TITRE PREMIER"): ("titre", ["TITRE PREMIER", "DISPOSITIONS PRÉLIMINAIRES"], 2),
    (3, "CHAPITRE PREMIER"): (
        "chapitre", ["CHAPITRE PREMIER", "OBJET, CHAMP D’APPLICATION ET OBJECTIFS"], 2,
    ),
    (3, "Section 1re.- Objet"): ("section", ["Section 1re.- Objet"], 1),
    (3, "Section 2.- Champ d’application"): ("section", ["Section 2.- Champ d’application"], 1),
    (3, "Section 3.- Objectifs"): ("section", ["Section 3.- Objectifs"], 1),
    (4, "CHAPITRE II"): (
        "chapitre", ["CHAPITRE II", "PRINCIPES GÉNÉRAUX ET DÉFINITIONS"], 2,
    ),
    (4, "Section 1re.- Principes généraux"): (
        "section", ["Section 1re.- Principes généraux"], 1,
    ),
    (5, "Section 2.- Définitions"): ("section", ["Section 2.- Définitions"], 1),
    (7, "TITRE II"): (
        "titre",
        [
            "TITRE II",
            "DU DROIT DES ADMINISTRÉS À UTILISER LES MOYENS ÉLECTRONIQUES",
            "DANS LEURS RAPPORTS AVEC L’ADMINISTRATION PUBLIQUE",
        ],
        3,
    ),
    (9, "TITRE III"): (
        "titre", ["TITRE III", "DU RÉGIME JURIDIQUE DE L’ADMINISTRATION ÉLECTRONIQUE"], 2,
    ),
    (9, "CHAPITRE PREMIER"): (
        "chapitre", ["CHAPITRE PREMIER", "DU SITE ÉLECTRONIQUE"], 2,
    ),
    (9, "CHAPITRE II"): (
        "chapitre", ["CHAPITRE II", "DE L’IDENTIFICATION ET DE L’AUTHENTIFICATION"], 2,
    ),
    (9, "Section 1re.- Dispositions communes"): (
        "section", ["Section 1re.- Dispositions communes"], 1,
    ),
    (10, "Section 2.- Identification des administrés et authentification de leurs démarches"): (
        "section", ["Section 2.- Identification des administrés et authentification de leurs démarches"], 1,
    ),
    (11, "Section 3.- Identification électronique des entités administratives"): (
        "section", ["Section 3.- Identification électronique des entités administratives"], 1,
    ),
    (11, "Section 4.- De l’interopérabilité, de l’accréditation et de la représentation des administrés"): (
        "section", ["Section 4.- De l’interopérabilité, de l’accréditation et de la représentation des administrés"], 1,
    ),
    (12, "CHAPITRE III"): (
        "chapitre", ["CHAPITRE III", "DES REGISTRES, COMMUNICATIONS ET NOTIFICATIONS ÉLECTRONIQUES"], 2,
    ),
    (12, "Section 1re.- Des registres"): ("section", ["Section 1re.- Des registres"], 1),
    (13, "Section 2.- Des communications et notifications électroniques"): (
        "section", ["Section 2.- Des communications et notifications électroniques"], 1,
    ),
    (14, "CHAPITRE IV"): (
        "chapitre", ["CHAPITRE IV", "DES DOCUMENTS ET ARCHIVES ÉLECTRONIQUES"], 2,
    ),
    (15, "TITRE IV"): (
        "titre", ["TITRE IV", "DE LA GESTION ÉLECTRONIQUE DES PROCÉDURES"], 2,
    ),
    (15, "CHAPITRE PREMIER"): (
        "chapitre", ["CHAPITRE PREMIER", "DISPOSITIONS COMMUNES"], 2,
    ),
    (16, "CHAPITRE II"): (
        "chapitre",
        ["CHAPITRE II", "L’UTILISATION DES MOYENS ÉLECTRONIQUES", "DANS LE DÉROULEMENT DES PROCÉDURES"],
        3,
    ),
    (17, "TITRE V"): (
        "titre",
        [
            "TITRE V",
            "COOPÉRATION ENTRE ENTITÉS ADMINISTRATIVES POUR LA MISE EN",
            "ŒUVRE DE L’ADMINISTRATION ÉLECTRONIQUE",
        ],
        3,
    ),
    (17, "CHAPITRE PREMIER"): (
        "chapitre",
        [
            "CHAPITRE PREMIER",
            "CHAMP INSTITUTIONNEL DE COOPÉRATION EN MATIÈRE",
            "D’ADMINISTRATION ÉLECTRONIQUE",
        ],
        3,
    ),
    (17, "CHAPITRE II"): (
        "chapitre",
        ["CHAPITRE II", "COOPÉRATION EN MATIÈRE D’INTEROPÉRABILITÉ", "DES SYSTÈMES ET APPLICATIONS"],
        3,
    ),
    (18, "CHAPITRE III"): (
        "chapitre", ["CHAPITRE III", "RÉUTILISATION D’APPLICATIONS ET TRANSFERT DE TECHNOLOGIES"], 2,
    ),
    (18, "TITRE VI"): ("titre", ["TITRE VI", "DISPOSITIONS FINALES"], 2),
}

# Libellés structuraux contrôlés sur les rendus 300 dpi. Leur remplacement
# n'altère pas le corps juridique et corrige les hésitations typiques de l'OCR
# sur les exposants, les chiffres romains et les apostrophes.
STRUCTURES_PAR_ZONE = {
    (3, 430, 490): "TITRE PREMIER",
    (3, 490, 550): "DISPOSITIONS PRÉLIMINAIRES",
    (3, 580, 640): "CHAPITRE PREMIER",
    (3, 640, 700): "OBJET, CHAMP D’APPLICATION ET OBJECTIFS",
    (3, 730, 810): "Section 1re.- Objet",
    (3, 1390, 1480): "Section 2.- Champ d’application",
    (3, 2040, 2130): "Section 3.- Objectifs",
    (4, 630, 690): "CHAPITRE II",
    (4, 690, 750): "PRINCIPES GÉNÉRAUX ET DÉFINITIONS",
    (4, 790, 860): "Section 1re.- Principes généraux",
    (5, 1410, 1500): "Section 2.- Définitions",
    (7, 1070, 1130): "TITRE II",
    (7, 1130, 1180): "DU DROIT DES ADMINISTRÉS À UTILISER LES MOYENS ÉLECTRONIQUES",
    (7, 1180, 1240): "DANS LEURS RAPPORTS AVEC L’ADMINISTRATION PUBLIQUE",
    (9, 750, 810): "TITRE III",
    (9, 810, 860): "DU RÉGIME JURIDIQUE DE L’ADMINISTRATION ÉLECTRONIQUE",
    (9, 900, 980): "CHAPITRE PREMIER",
    (9, 990, 1070): "DU SITE ÉLECTRONIQUE",
    (9, 2690, 2770): "CHAPITRE II",
    (9, 2770, 2840): "DE L’IDENTIFICATION ET DE L’AUTHENTIFICATION",
    (9, 2850, 2940): "Section 1re.- Dispositions communes",
    (10, 1520, 1610): "Section 2.- Identification des administrés et authentification de leurs démarches",
    (11, 310, 390): "Section 3.- Identification électronique des entités administratives",
    (11, 2810, 2900): "Section 4.- De l’interopérabilité, de l’accréditation et de la représentation des administrés",
    (12, 1680, 1760): "CHAPITRE III",
    (12, 1750, 1820): "DES REGISTRES, COMMUNICATIONS ET NOTIFICATIONS ÉLECTRONIQUES",
    (12, 1830, 1920): "Section 1re.- Des registres",
    (13, 1770, 1860): "Section 2.- Des communications et notifications électroniques",
    (14, 1550, 1620): "CHAPITRE IV",
    (14, 1620, 1680): "DES DOCUMENTS ET ARCHIVES ÉLECTRONIQUES",
    (15, 1660, 1740): "TITRE IV",
    (15, 1730, 1800): "DE LA GESTION ÉLECTRONIQUE DES PROCÉDURES",
    (15, 1820, 1900): "CHAPITRE PREMIER",
    (15, 1920, 2000): "DISPOSITIONS COMMUNES",
    (16, 310, 380): "CHAPITRE II",
    (16, 370, 430): "L’UTILISATION DES MOYENS ÉLECTRONIQUES",
    (16, 420, 490): "DANS LE DÉROULEMENT DES PROCÉDURES",
    (17, 540, 620): "TITRE V",
    (17, 610, 660): "COOPÉRATION ENTRE ENTITÉS ADMINISTRATIVES POUR LA MISE EN",
    (17, 650, 720): "ŒUVRE DE L’ADMINISTRATION ÉLECTRONIQUE",
    (17, 750, 830): "CHAPITRE PREMIER",
    (17, 840, 910): "CHAMP INSTITUTIONNEL DE COOPÉRATION EN MATIÈRE",
    (17, 900, 970): "D’ADMINISTRATION ÉLECTRONIQUE",
    (17, 1820, 1900): "CHAPITRE II",
    (17, 1910, 1980): "COOPÉRATION EN MATIÈRE D’INTEROPÉRABILITÉ",
    (17, 1980, 2050): "DES SYSTÈMES ET APPLICATIONS",
    (18, 1000, 1080): "CHAPITRE III",
    (18, 1090, 1170): "RÉUTILISATION D’APPLICATIONS ET TRANSFERT DE TECHNOLOGIES",
    (18, 2020, 2100): "TITRE VI",
    (18, 2090, 2160): "DISPOSITIONS FINALES",
}

REMPLACEMENTS_OCR = (
    ("MICHEL J OSEPH", "MICHEL JOSEPH"),
    ("PRESIDENT", "PRÉSIDENT"),
    ("1°” juin", "1er juin"),
    ("1°\" juin", "1er juin"),
    ("Article 1°\".-", "Article 1er.-"),
    ("Article 1°”.-", "Article 1er.-"),
    ("[1 est reconnu", "Il est reconnu"),
    ("certi fication", "certification"),
    ("l’ Arrêté", "l’Arrêté"),
    ("I. Qu'il", "1. Qu'il"),
    ("N'’avoir", "N’avoir"),
    ("deux qui sont utilisés", "ceux qui sont utilisés"),
    ("accorc", "accord"),
    ("l’article 1% du Code Civil", "l’article 1er du Code Civil"),
    ("l’ identification", "l’identification"),
    ("ciaprès", "ci-après"),
    ("Fonction Publiques", "Fonction Publique"),
    ("mentiomiés", "mentionnés"),
    ("format orignal", "format original"),
    ("dans le cadre l'Administration Centrale", "dans le cadre de l’Administration Centrale"),
    ("l’administration électronique:", "l’administration électronique ;"),
    ("Laprévision", "La prévision"),
    ("qui y sont contenues,", "qui y sont contenues."),
    ("de son code source,", "de son code source."),
    ("accorc spécifique", "accord spécifique"),
    ("services de certificatio électronique", "services de certification électronique"),
    ("de la Lc sur la signature", "de la Loi sur la signature"),
    ("des Télécommunication Une fois", "des Télécommunications ; Une fois"),
    ("de la Car! d’Identification", "de la Carte d’Identification"),
    ("humaines po l’incorporation", "humaines pour l’incorporation"),
    ("pour s'identifier et authentif leurs documents", "pour s'identifier et authentifier leurs documents"),
    ("délivré par prestataire", "délivré par un prestataire"),
    ("des données et intérêts cause", "des données et intérêts en cause"),
    ("systèmes de signat électronique", "systèmes de signature électronique"),
    ("ou d’au! systèmes", "ou d’autres systèmes"),
    ("un proje document", "un projet de document"),
    ("de l’intégrité e l’acceptation", "de l’intégrité et de l’acceptation"),
    ("du contenu formalités", "du contenu des formalités"),
    ("moyens d’identifice et d’authentification", "moyens d’identification et d’authentification"),
    ("sans préjudicie du droit", "sans préjudice du droit"),
    ("Article 18. Pour", "Article 18.- Pour"),
    ("Article 49,-", "Article 49.-"),
    ("D'’", "D’"),
)

RE_ARTICLE = re.compile(r"^(Article)\s+(\d+)(er)?\.-(?:\s*(.*))?$")
RE_ENUMERATION = re.compile(
    r"^(?:[a-z]\)\s+|[A-Z]\)\s+|\d+\s*(?:[.)-])\s+|[IVXLCDM]+\)\s+|-\s+)"
)
RE_ENTETE = re.compile(r"(?:LE MONITEUR|Vendredi 29 Janvier 2016|^No\.\s*20|^\d+$)", re.IGNORECASE)


CLOTURE_PARAGRAPHES = [
    "Donné au Palais National, à Port-au-Prince, le 6 Janvier 2016, An 213e de l’Indépendance.",
    "Par:",
    "Le Président", "Michel Joseph MARTELLY",
    "Le Premier Ministre", "Evans PAUL",
    "Le Ministre de la Planification et de la Coopération Externe :", "Yves Germain JOSEPH",
    "Le Ministre a.i. des Affaires Étrangères et des Cultes", "Lener RENAULD",
    "Le Ministre de la Justice et de la Sécurité Publique", "Pierre Richard CASIMIR",
    "Le Ministre de l’Économie et des Finances", "Wilson LALEAU",
    "Le Ministre des Travaux Publics, Transports et Communications", "pr Jacques ROUSSEAU",
    "Le Ministre de l’Agriculture, des Ressources Naturelles et du Développement Rural", "Lyonel VALBRUN",
    "La Ministre du Tourisme et des Industries Créatives", "Stéphanie BALMIR VILLEDROUIN",
    "Le Ministre de l’Éducation Nationale et de la Formation Professionnelle", "pr Nesmy MANIGAT",
    "La Ministre de la Santé Publique et de la Population", "Florence DUPERVAL GUILLAUME",
    "Le Ministre des Affaires Sociales et du Travail", "Ariel HENRY",
    "Le Ministre de l’Intérieur et des Collectivités Territoriales", "Ardouin ZEPHIRIN",
    "Le Ministre du Commerce et de l’Industrie", "Hervey DAY",
    "La Ministre de la Culture", "Dithny Joan RATON",
    "Le Ministre de la Communication", "Jean Mario DUPUY",
    "La Ministre à la Condition Féminine et aux Droits des Femmes", "Gabrielle HYACINTHE",
    "Le Ministre de la Défense", "Lener RENAULD",
    "Le Ministre des Haïtiens Vivant à l’Étranger", "Robert LABROUSSE",
    "Le Ministre Délégué auprès du Premier Ministre, Chargé des Questions Électorales", "Jean Fritz JEAN-LOUIS",
    "Le Ministre de l’Environnement", "Dominique PIERRE",
    "Le Ministre de la Jeunesse, des Sports et de l’Action Civique", "Jimmy ALBERT",
    "Le Ministre Délégué auprès du Premier Ministre, Chargé des Programmes sociaux, des Projets et Chantiers du Gouvernement",
    "Edouard JULES",
]


@dataclass(frozen=True)
class Ligne:
    page: int
    top: float
    x0: float
    texte: str
    forcer_paragraphe: bool = False


@dataclass
class Segment:
    top: float
    bottom: float
    x0: float
    x1: float
    texte: str

    @property
    def centre(self) -> float:
        return (self.top + self.bottom) / 2


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


def sha256_dossier(dossier: Path, motif: str = "*.tsv") -> str:
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
        segments.append(Segment(top, bottom, x0, x1, nettoyer_espaces(" ".join(row["text"] for row in mots))))
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
        texte = nettoyer_espaces(" ".join(item.texte for item in groupe))
        lignes.append(Ligne(page, min(item.top for item in groupe), min(item.x0 for item in groupe), texte))
    return lignes


def corriger_ligne(ligne: Ligne, audit: list[dict]) -> Ligne | None:
    if ligne.page == 1 or ligne.page >= 20:
        return None
    texte = ligne.texte
    if ligne.top < 300 and RE_ENTETE.search(texte):
        return None
    original = texte
    for (page, minimum, maximum), impose in STRUCTURES_PAR_ZONE.items():
        if ligne.page == page and minimum <= ligne.top <= maximum:
            texte = impose
            break
    for avant, apres in REMPLACEMENTS_OCR:
        if avant in texte:
            texte = texte.replace(avant, apres)
    # La marge droite de la page 10 est rognée dans le scan. Les finales ci-dessous
    # sont rétablies après comparaison des deux OCR et lecture du rendu 300 dpi.
    if ligne.page == 10:
        remplacements_marge = (
            ("de la Lc", "de la Loi"),
            ("des Télécommunication", "des Télécommunications."),
            ("de la Car!", "de la Carte"),
            ("humaines po", "humaines pour"),
            ("pour s'identifier et authentif", "pour s'identifier et authentifier"),
            ("délivré par", "délivré par un"),
            ("des données et intérêts", "des données et intérêts en"),
            ("ou d’au!", "ou d’autres"),
            ("un proje", "un projet de"),
            ("de l’intégrité e", "de l’intégrité et de"),
            ("du contenu", "du contenu des"),
            ("moyens d’identifice", "moyens d’identification"),
        )
        for avant, apres in remplacements_marge:
            if avant in texte:
                texte = texte.replace(avant, apres)
        if texte.endswith("services de certificatio"):
            texte += "n"
        if texte.endswith("systèmes de signat"):
            texte += "ure"
    if ligne.page == 19 and texte.endswith("dans le cadre"):
        texte += " de"
    # Deux entrées alphabétiques des définitions sont confondues avec des chiffres.
    if ligne.page == 6 and texte.startswith("1) Dispositif sécurisé"):
        texte = "l)" + texte[2:]
    if ligne.page == 6 and texte.startswith("0) Document électronique"):
        texte = "o)" + texte[2:]
    # L'exposant de l'article premier est très dégradé dans les deux OCR.
    if texte.startswith("Article 1") and ligne.page == 3:
        texte = re.sub(r"^Article\s+1[^-]*-\s*", "Article 1er.- ", texte, count=1)
    texte = nettoyer_espaces(texte)
    if texte != original:
        audit.append({
            "page": ligne.page,
            "top": round(ligne.top, 1),
            "avant": original,
            "apres": texte,
            "raison": "correction OCR ou structure vérifiée sur le rendu 300 dpi",
        })
    return replace(ligne, texte=texte, forcer_paragraphe=bool(RE_ENUMERATION.match(texte)))


def charger_lignes(ocr_dir: Path) -> tuple[list[Ligne], dict]:
    fichiers = sorted(ocr_dir.glob("page-*.tsv"))
    if len(fichiers) != 22:
        raise RuntimeError(f"22 TSV OCR attendus dans {ocr_dir}, {len(fichiers)} trouvés")
    audit: list[dict] = []
    lignes: list[Ligne] = []
    brutes = 0
    entetes = 0
    for path in fichiers:
        match = re.search(r"(\d+)$", path.stem)
        if not match:
            continue
        page = int(match.group(1))
        page_lignes = fusionner_segments(page, charger_segments(path))
        brutes += len(page_lignes)
        for ligne in page_lignes:
            corrigee = corriger_ligne(ligne, audit)
            if corrigee is None:
                entetes += 1
            else:
                lignes.append(corrigee)
    return lignes, {
        "fichiers_tsv": len(fichiers),
        "lignes_brutes": brutes,
        "lignes_retenues": len(lignes),
        "lignes_exclues": entetes,
        "corrections": audit,
        "sha256_tsv": sha256_dossier(ocr_dir),
    }


def parser_article(texte: str) -> dict | None:
    match = RE_ARTICLE.match(texte)
    if not match:
        return None
    numero = int(match.group(2))
    etiquette = texte[:match.end(3) if match.group(3) else match.end(2)] + ".-"
    # Le motif a déjà consommé « .- »; on reconstruit l'étiquette sans changer
    # sa séquence utile et récupère le texte suivant le séparateur.
    separateur = texte.find(".-", match.start(2))
    etiquette = texte[:separateur + 2]
    corps = nettoyer_espaces(texte[separateur + 2:])
    return {"numero": numero, "etiquette": etiquette, "corps": corps}


def construire_structures(lignes: list[Ligne], limite: int) -> list[Evenement]:
    evenements: list[Evenement] = []
    for index, ligne in enumerate(lignes[:limite]):
        definition = STRUCTURES.get((ligne.page, ligne.texte))
        if not definition:
            continue
        niveau, segments, longueur = definition
        observees = [item.texte for item in lignes[index:index + longueur]]
        if nettoyer_espaces(" ".join(observees)) != nettoyer_espaces(" ".join(segments)):
            raise RuntimeError(f"Structure inattendue page {ligne.page}: {observees!r} != {segments!r}")
        evenements.append(Evenement(index, index + longueur, "structure", {
            "niveau": niveau,
            "segments": segments,
            "lignes": observees,
        }))
    if len(evenements) != len(STRUCTURES):
        trouvees = [(e.donnees["niveau"], e.donnees["segments"]) for e in evenements]
        raise RuntimeError(f"{len(STRUCTURES)} structures attendues, {len(evenements)} trouvées: {trouvees}")
    return evenements


def ajouter_fragment(courant: list[str], texte: str) -> None:
    if not texte:
        return
    if courant and courant[-1].endswith("-") and re.match(r"^[a-zàâçéèêëîïôùûüœ]", texte):
        # « ci-après » est un mot composé, pas une césure typographique.
        courant[-1] = courant[-1] + texte if courant[-1].endswith("ci-") else courant[-1][:-1] + texte
    else:
        courant.append(texte)


def formater_lignes(lignes: list[Ligne], article: dict | None = None, type_bloc: str = "article") -> str:
    travail = list(lignes)
    etiquette = ""
    if article:
        etiquette = article["etiquette"]
        travail[0] = replace(travail[0], texte=article["corps"])
    paragraphes: list[str] = []
    courant: list[str] = []
    debuts_non_article = ("Vu ", "Considérant ", "Sur le rapport", "Et après", "DÉCRÈTE")
    for ligne in travail:
        texte = ligne.texte
        if not texte:
            continue
        nouveau = False
        if courant:
            if type_bloc == "article":
                nouveau = bool(ligne.forcer_paragraphe or RE_ENUMERATION.match(texte))
            elif type_bloc == "visas":
                nouveau = texte.startswith(debuts_non_article)
            elif type_bloc == "preambule":
                nouveau = True
        if nouveau:
            paragraphes.append(" ".join(courant))
            courant = []
        ajouter_fragment(courant, texte)
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
            fragments[-1] = fragments[-1] + texte if fragments[-1].endswith("ci-") else fragments[-1][:-1] + texte
        else:
            fragments.append(texte)
    return re.sub(r"\s+", "", " ".join(fragments))


def construire(lignes: list[Ligne], base: dict) -> tuple[list[dict], str, dict]:
    articles = [(index, parser_article(ligne.texte)) for index, ligne in enumerate(lignes) if parser_article(ligne.texte)]
    numeros = [article["numero"] for _, article in articles]
    if numeros != list(range(1, 52)):
        manquants = sorted(set(range(1, 52)) - set(numeros))
        doublons = sorted(numero for numero, compte in Counter(numeros).items() if compte > 1)
        raise RuntimeError(f"Articles non séquentiels; trouvés={numeros}, manquants={manquants}, doublons={doublons}")
    index_visas = next(i for i, ligne in enumerate(lignes) if ligne.texte.startswith("Vu la Constitution"))
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
    for index, position in enumerate(positions):
        evenement = evenements[position]
        if evenement.type != "structure":
            evenement.fin = positions[index + 1] if index + 1 < len(positions) else len(lignes)

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
        bloc = lignes[evenement.debut:evenement.fin]
        if evenement.type == "preambule":
            ajouter(formater_lignes(bloc, type_bloc="preambule"), "Préambule", "preambule", f"{RACINE} > PRÉAMBULE")
        elif evenement.type == "visas":
            ajouter(formater_lignes(bloc, type_bloc="visas"), "Visas", "visas", f"{RACINE} > VISAS")
        elif evenement.type == "article":
            article = evenement.donnees["article"]
            chemin, extra = chemin_et_metadata(etat)
            ajouter(
                formater_lignes(bloc, article=article, type_bloc="article"),
                "Article 1er" if article["numero"] == 1 else f"Article {article['numero']}",
                "article", chemin, extra,
            )
        elif evenement.type == "cloture":
            ajouter("\n\n".join(CLOTURE_PARAGRAPHES), "Clôture", "cloture", f"{RACINE} > CLÔTURE")

    reference = [ligne.texte for i, ligne in enumerate(lignes[:index_cloture]) if i not in indices_structure]
    reference.extend(CLOTURE_PARAGRAPHES)
    reference_complete = [ligne.texte for ligne in lignes[:index_cloture]] + CLOTURE_PARAGRAPHES
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
            textes.extend(row["text"] for row in csv.DictReader(stream, delimiter="\t") if row.get("level") == "5")
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
        len(re.findall(r"(?<!\n)\n(?!\n)", chunk["page_content"])) for chunk in articles
    )
    comparaison_ocr = None
    if contre_ocr_dir and contre_ocr_dir.is_dir():
        principal = sequence_ocr_dossier(ocr_dir)
        secondaire = sequence_ocr_dossier(contre_ocr_dir)
        comparaison_ocr = {
            "modele_principal": "Tesseract tessdata_best français",
            "modele_secondaire": "Tesseract tessdata_fast français",
            "similarite_sequence": round(difflib.SequenceMatcher(None, principal, secondaire).ratio(), 6),
            "sha256_tsv_secondaire": sha256_dossier(contre_ocr_dir),
        }
    return {
        "statut": "conforme_techniquement_a_relecture_humaine",
        "source": {
            "pdf": str(pdf.resolve()),
            "sha256": sha256(pdf),
            "pages_pdf": 22,
            "pages_du_decret": "pages PDF 2 à 22; pages imprimées 11 à 31",
            "page_exclue": "page PDF 1: couverture générale et fin du décret précédent",
            "couche_texte_native": False,
            "publication": "Le Moniteur, 171e Année, No. 20, vendredi 29 janvier 2016",
            "date_du_decret": "2016-01-06",
            "verification_visuelle": "22 pages rendues à 150 dpi; texte et zones ambiguës contrôlés sur les rendus 300 dpi",
            "ocr": {
                "principal": "Tesseract LSTM, modèle officiel tessdata_best français, rendu 300 dpi",
                "contre_lecture": comparaison_ocr,
                "fichiers_tsv": audit_ocr["fichiers_tsv"],
            },
        },
        "sorties": {
            "dossier_registre": str(dossier.resolve()),
            "markdown": "outputs/document.md",
            "chunks": "outputs/chunks.json",
            "validation_backend": "outputs/rapport_validation_backend.json",
        },
        "chunks": {
            "prevus": 54,
            "trouves": len(chunks),
            "ecart": len(chunks) - 54,
            "par_type_bloc": dict(sorted(types.items())),
        },
        "articles": {
            "prevus": 51,
            "trouves": len(articles),
            "numeros": audit_structure["articles"],
            "articles_introuvables": sorted(set(range(1, 52)) - set(audit_structure["articles"])),
            "doublons": sorted(numero for numero, compte in Counter(audit_structure["articles"]).items() if compte > 1),
        },
        "hierarchie": {
            "groupes_structuraux": len(audit_structure["structures"]),
            "tous_chunks_avec_chemin_hierarchique": all(
                bool(chunk["metadata"].get("chemin_hierarchique")) for chunk in chunks
            ),
            "exemples": {
                label: next(
                    chunk["metadata"]["chemin_hierarchique"]
                    for chunk in chunks if chunk["metadata"]["article"] == label
                )
                for label in ("Article 1er", "Article 6", "Article 13", "Article 29", "Article 40", "Article 47")
            },
        },
        "integrite_caracteres": {
            "methode": "comparaison entre l'OCR haute précision corrigé et les chunks; seuls espaces, retours et césures typographiques sont normalisés",
            "reference_hors_espaces": len(reference),
            "chunks_hors_espaces": len(contenu),
            "chunks_identiques_a_la_reference": integrite,
            "caracteres_manquants_detectes": 0 if integrite else None,
            "caracteres_ajoutes_detectes": 0 if integrite else None,
            "markdown_incluant_structure_identique": reference_markdown == contenu_markdown,
            "corrections_ocr_documentees": len(audit_ocr["corrections"]),
            "details_corrections": audit_ocr["corrections"],
            "signatures_retranscrites_depuis_le_rendu": True,
        },
        "mise_en_page": {
            "retours_simples_dans_les_articles": retours_simples,
            "retours_simples_attendus": 0,
            "separateur_de_paragraphe": "double retour de ligne",
            "coupures_de_lignes_et_cesures_du_scan_supprimees": True,
            "retours_conserves_pour_listes_et_numerotations": True,
            "entetes_repetitifs_et_pagination_ignores": audit_ocr["lignes_exclues"],
        },
        "metadata": {
            "dates_recues_dans_le_message": ["1980-11-17", "1996-10-10"],
            "date_juridique_appliquee": "2016-01-06",
            "date_publication": "2016-01-29",
            "motif_correction_date": "la clôture imprimée indique: Donné au Palais National, le 6 janvier 2016",
            "historique": False,
            "tous_chunks_historique_false": all(chunk["metadata"].get("historique") is False for chunk in chunks),
            "moniteur": {"annee": 171, "numero": "20", "type": "ordinaire"},
            "motif_moniteur_type": "la couverture est libellée 171e Année No. 20 sans mention Spécial",
            "regle_moniteur": "les trois clés moniteur_* sont présentes sur tous les chunks",
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
            "Les dates 1980-11-17 et 1996-10-10 ne correspondent pas au document; la date imprimée 2016-01-06 a été appliquée.",
            "La couverture indique une édition ordinaire 171e Année No. 20; la valeur spécial de l'ancien bloc n'a pas été reprise.",
            "La page PDF 1 contient la couverture et la fin du décret sur la signature électronique; elle a été exclue du contenu de ce décret.",
            "Quelques fins de lignes rognées dans le scan ont été restaurées après double OCR et contrôle visuel; toutes les corrections figurent dans le rapport.",
            "Le statut en_vigueur doit être confirmé lors de la relecture juridique finale.",
        ],
        "suggestions": [
            "Relire en priorité les articles 14 à 16, dont la marge droite est légèrement rognée dans le scan.",
            "Comparer la clôture et les noms des signataires avec un second exemplaire matériel du Moniteur si disponible.",
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
        raise RuntimeError(f"TYPES_BLOC_VALIDES incomplet: {sorted(requis - set(TYPES_BLOC_VALIDES))}")
    with args.pdf.open("rb") as stream:
        pages_pypdf = len(pypdf.PdfReader(stream).pages)
    with pdfplumber.open(args.pdf) as document:
        pages_pdfplumber = len(document.pages)
        caracteres_nat = sum(len(page.extract_text() or "") for page in document.pages)
    if pages_pypdf != 22 or pages_pdfplumber != 22 or caracteres_nat != 0:
        raise RuntimeError(
            f"Source PDF inattendue: pypdf={pages_pypdf}, pdfplumber={pages_pdfplumber}, texte={caracteres_nat}"
        )

    base = {
        "source": "Décret du 6 janvier 2016 reconnaissant le droit de tout administré à s’adresser à l’Administration Publique par des moyens électroniques",
        "source_courte": "Décret sur l’administration électronique 2016",
        "type_norme": "decret",
        "rang": RANGS_PAR_TYPE_NORME["decret"],
        "date": "2016-01-06",
        "date_publication": "2016-01-29",
        "statut": "en_vigueur",
        "moniteur_publication": "Le Moniteur, 171e année, Ordinaire no 20, 29 janvier 2016",
        "mots_cles": [
            "administration électronique", "services publics", "procédures électroniques",
            "administrés", "interopérabilité", "documents électroniques",
        ],
        "type_thematique": ["droit_administratif", "droits_fondamentaux"],
        "historique": False,
        "abroge_par": None,
        "publication_abrogation": None,
        "date_abrogation": None,
    }

    lignes, audit_ocr = charger_lignes(args.ocr_dir)
    chunks, markdown, audit_structure = construire(lignes, base)
    validation = _valider_donnees(chunks)
    registre = Registre(args.registre_root or (args.racine_conversion / "registry"))
    record = registre.inscrire(args.pdf, base, "Décret sur l'administration électronique 2016")
    dossier, _ = registre.lire(record["document_id"])
    rapport = construire_rapport(
        args.pdf, dossier, chunks, markdown, audit_ocr, audit_structure, validation,
        set(TYPES_BLOC_VALIDES), args.ocr_dir, args.ocr_contre_dir,
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
            "source_texte": "PDF image sans couche texte",
            "ocr_principal": "Tesseract LSTM tessdata_best français sur rendu Poppler 300 dpi",
            "ocr_contre_lecture": "Tesseract LSTM tessdata_fast français sur le même rendu",
            "controle_visuel_pages": 22,
            "rendu_global_dpi": 150,
            "rendu_ocr_et_detail_dpi": 300,
            "page_editoriale_et_decret_precedent_exclus": 1,
            "coupures_de_lignes_et_cesures_supprimees": True,
            "separateurs_dans_articles": "double retour pour listes et numérotations seulement",
            "titres_migres_vers_chemin_hierarchique": True,
            "corrections_juridiques_silencieuses": False,
            "corrections_ocr": audit_ocr["corrections"],
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    manifeste = {
        "document_id": record["document_id"],
        "sha256_source": record["sha256_source"],
        "sha256_ocr_best_tsv": sha256_dossier(extraction_principale),
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
