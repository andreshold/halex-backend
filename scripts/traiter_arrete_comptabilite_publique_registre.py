#!/usr/bin/env python3
"""Convertit l'arrêté du 16 février 2005 sur la comptabilité publique."""
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


RACINE = "ARRÊTÉ PORTANT RÈGLEMENT GÉNÉRAL DE LA COMPTABILITÉ PUBLIQUE"
RE_ARTICLE = re.compile(r"^Article\s+(\d+)\.-(?:\s*(.*))?$")
RE_ENUMERATION = re.compile(r"^(?:[a-z]\)|\d+[.)]\s|-\s)", re.IGNORECASE)

# Corrections exclusivement relevées dans la couche OCR et vérifiées sur le
# rendu des pages. Les éventuelles maladresses du texte juridique imprimé ne
# sont pas corrigées.
REMPLACEMENTS_OCR = (
    ("structure:::", "structures"),
    ("1>ouanes", "Douanes"),
    ("des'lmpôts", "des Impôts"),
    ("200~", "2005"),
    ("Fit.tances", "Finances"),
    ("fol).damentales", "fondamentales"),
    ("pubHcs", "publics"),
    ("çommun", "commun"),
    ("c par les entités", "par les entités"),
    ("Comptabilité Nationale. 0", "Comptabilité Nationale."),
    ("Article7.-", "Article 7.-"),
    ("emprur.té", "emprunté"),
    ("communiqué annuellement", "communiqué annuellement."),
    ("titre HI", "titre III"),
    ("TITREI", "TITRE I"),
    ("TITREH", "TITRE II"),
    ("LESORDONNATEURSETLESCOMœTABLES", "LES ORDONNATEURS ET LES COMPTABLES"),
    ("CHAPITRE!", "CHAPITRE I"),
    ("La, tenue", "La tenue"),
    ("- . de l'autorisation", "de l'autorisation"),
    ("règlements; ·", "règlements;"),
    ("Article 27.=", "Article 27.-"),
    ("Hs sont", "Ils sont"),
    ("libératio~", "libération"),
    ("est ·mise en par", "est mise en jeu par"),
    ("manquant Les articles", "manquant. Les articles"),
    ("p•1blique", "publique"),
    ("pÙblique", "publique"),
    ("uublics", "publics"),
    ("poursuivijusqu'à", "poursuivi jusqu'à"),
    ("Article 60.·", "Article 60.-"),
    ("sont engagées et mises en", "sont engagées et mises en jeu"),
    ("obligatbns", "obligations"),
    ("internationaL", "international."),
    ("A:rticle 62.-", "Article 62.-"),
    ("frai~", "frais"),
    ("ex~cution", "exécution"),
    ("Article 7 4.-", "Article 74.-"),
    ("or1onnateur", "ordonnateur"),
    ("acqùits", "acquits"),
    ("approvisionn0ment", "approvisionnement"),
    ("des· caisses", "des caisses"),
    ("articl~s", "articles"),
    ("règlement de c~", "règlement de ce"),
    ("f~ancières", "financières"),
    ("èorrespondant", "correspondant"),
    ("comptes courants -ouverts", "comptes courants - ouverts"),
    ("finances -au nom", "finances - au nom"),
    ("d'Haïti· informe", "d'Haïti informe"),
    ("sur .le Trésor", "sur le Trésor"),
    ("del' administration", "de l'administration"),
    ("Coopéràtion", "Coopération"),
)

ARTEFACTS_A_RETIRER = {
    (2, "c"),
    (3, '("'),
    (18, "\\"),
    (19, "~"),
}

# Les tirets existent sur les pages, mais ne figurent pas dans la couche OCR.
# Ils sont rétablis uniquement pour les listes visuellement contrôlées.
DEBUTS_PUCES = {
    7: (
        "Il procède,", "Il tient une comptabilité séparée", "Il assure la comptabilisation",
        "Il concourt", "Il décrit", "Il exécute", "Il centralise", "Après avoir centralisé",
    ),
    8: (
        "la balance générale", "le développement des recettes", "le développement des dépenses",
        "le développement des opérations constatées", "une situation de la dette",
        "le développement des comptes de résultats",
    ),
    9: ("toutes les opérations rattachées", "toutes les opérations de trésorerie"),
    24: (
        "La prise en charge", "Le règlement", "La garde", "Le maniement", "La conservation",
        "La tenue",
    ),
    25: (
        "de l'autorisation", "de la mise en recouvrement", "de la qualité", "de l'exacte",
        "de la disponibilité", "de la validité", "de l'existence", "du caractère",
        "de la conservation",
    ),
    26: (
        "la justification", "l'exactitude", "l'intervention préalable", "la production",
        "l'application",
    ),
    43: ("les comptables des administrations", "les régisseurs d'avances"),
    44: ("tout encaissement de droits", "tout encaissement « au comptant »"),
    45: ("pour le comptable principal", "Pour ceux", "Le certificat de décharge doit être délivré"),
    62: (
        "les dépenses de traitements", "les rentes", "les loyers", "certaines dépenses au titre",
        "certaines dépenses pour assurer",
    ),
    68: ("soit par les ordonnateurs principaux", "soit par les ordonnateurs secondaires"),
    74: (
        "l'absence de crédits", "l'absence de justification", "le caractère non libératoire",
        "l'absence de visa",
    ),
}

# (page, ligne d'en-tête) -> (niveau, segments hiérarchiques, nombre de lignes)
STRUCTURES = {
    (2, "TITRE I"): ("titre", ["TITRE I", "DISPOSITIONS GENERALES"], 2),
    (5, "TITRE II"): ("titre", ["TITRE II", "LES ORDONNATEURS ET LES COMPTABLES"], 2),
    (5, "CHAPITRE I"): ("chapitre", ["CHAPITRE I", "LES ORDONNATEURS ET LEUR RESPONSABILITE"], 2),
    (6, "CHAPITRE II"): ("chapitre", ["CHAPITRE II", "LES COMPTABLES PUBLICS ET LEUR RESPONSABILITE"], 2),
    (10, "CHAPITRE III"): (
        "chapitre",
        ["CHAPITRE III", "LE PRINCIPE DE LA SEPARATION DES FONCTIONS D'ORDONNATEUR ET DE COMPTABLE"],
        3,
    ),
    (11, "TITRE III"): ("titre", ["TITRE III", "LES OPERATIONS D'EXECUTION DU BUDGET DE L'ETAT"], 2),
    (11, "CHAPITRE I"): ("chapitre", ["CHAPITRE I", "DISPOSITIONS GENERALES"], 2),
    (11, "CHAPITRE II"): ("chapitre", ["CHAPITRE II", "OPERATIONS DE RECETTES"], 2),
    (13, "CHAPITRE III"): ("chapitre", ["CHAPITRE III", "OPERATIONS DE DEPENSES"], 2),
    (16, "CHAPITRE IV"): ("chapitre", ["CHAPITRE IV", "OPERATIONS DE TRESORERIE"], 2),
    (17, "CHAPITRE V"): ("chapitre", ["CHAPITRE V", "AUTRES OPERATIONS"], 2),
    (17, "TITRE V"): ("titre", ["TITRE V", "LE CONTROLE DE L'EXECUTION BUDGETAIRE"], 2),
    (17, "TITRE VI"): ("titre", ["TITRE VI", "LE CAISSIER DE L'ETAT"], 2),
    (19, "TITRE VII"): ("titre", ["TITRE VII", "DISPOSITION TRANSITOIRE"], 2),
    (19, "TITRE VIII"): ("titre", ["TITRE VIII", "DISPOSITION FINALE"], 2),
}

CLOTURE_PARAGRAPHES = [
    "Donné au Palais National, à Port-au-Prince, le 16 février 2005, An 202ème de l'Indépendance.",
    "Par le Président", "Me. Boniface ALEXANDRE",
    "Le Premier Ministre", "Gérard LATORTUE",
    "Le Ministre des Affaires Etrangères et des Cultes", "pr Hérard ABRAHAM", "Magali COMEAU DENIS",
    "Le Ministre de la Justice et de la Sécurité Publique", "Bernard H. GOUSSE",
    "Le Ministre de l'Intérieur et des Collectivités Territoriales", "Georges MOISE",
    "Le Ministre de l'Économie et des Finances", "Henri BAZIN",
    "Le Ministre du Plan et de la Coopération Externe", "Roland PIERRE",
    "Le Ministre de l'Agriculture, des Ressources Naturelles et du Développement Rural", "Philippe MATHIEU",
    "Le Ministre du Commerce, de l'Industrie et du Tourisme", "Jacques Fritz KENOL",
    "Le Ministre des Travaux Publics, Transports et Communications", "Fritz ADRIEN",
    "Le Ministre de l'Education Nationale, de la Jeunesse, des Sports et de l'Education Civique", "Pierre BUTEAU",
    "Le Ministre de la Communication et de la Culture", "Magali COMEAU DENIS",
    "Le Ministre de la Santé Publique et de la Population", "Josette BIJOU",
    "Le Ministre des Affaires Sociales", "Pierre Claude CALIXTE",
    "Le Ministre à la Condition Féminine", "Adeline Magloire CHANCY",
    "Le Ministre des Haïtiens Vivant à l'Étranger", "pr Alix BAPTISTE", "Adeline Magloire CHANCY",
    "Le Ministre de l'Environnement", "Yves André WAINRIGHT",
]


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


def corriger_ocr(page: int, texte: str, audit: list[dict]) -> tuple[str | None, bool]:
    texte = nettoyer_espaces(texte)
    if (page, texte) in ARTEFACTS_A_RETIRER:
        audit.append({"page": page, "avant": texte, "apres": None, "raison": "artefact de numérisation"})
        return None, False
    original = texte
    for avant, apres in REMPLACEMENTS_OCR:
        if avant in texte:
            texte = texte.replace(avant, apres)
    # Le moteur OCR confond systématiquement le l minuscule avec le chiffre 1
    # devant une apostrophe, et une fois avec un i minuscule.
    texte = re.sub(r"\b[1i]'\s*", "l'", texte)
    texte = re.sub(r"\bl'\s+", "l'", texte)
    forcer = False
    if page in {5, 13} and texte == "n":
        texte = "Il"
        forcer = True
    if texte != original:
        audit.append({"page": page, "avant": original, "apres": texte, "raison": "correction OCR vérifiée sur le rendu"})
    return texte, forcer


def extraire_lignes(pdf: Path) -> tuple[list[Ligne], dict]:
    lignes: list[Ligne] = []
    corrections: list[dict] = []
    marges: list[dict] = []
    apres_cloture = False
    signatures_ocr_ignorees = 0
    with pdfplumber.open(pdf) as document:
        for page_numero, page in enumerate(document.pages, 1):
            for item in page.extract_text_lines():
                brut = nettoyer_espaces(item["text"])
                top = float(item["top"])
                if (page_numero == 1 and top < 445) or (page_numero > 1 and top < 70):
                    marges.append({"page": page_numero, "texte": brut, "raison": "en-tête, pagination ou sommaire"})
                    continue
                if apres_cloture:
                    signatures_ocr_ignorees += 1
                    continue
                corrige, forcer = corriger_ocr(page_numero, brut, corrections)
                if corrige is None:
                    continue
                lignes.append(Ligne(page_numero, top, float(item["x0"]), corrige, forcer))
                if corrige.startswith("Donné au Palais National"):
                    apres_cloture = True
    with pdf.open("rb") as stream:
        pages_secondaires = len(pypdf.PdfReader(stream).pages)
    return lignes, {
        "pages_pdfplumber": len({ligne.page for ligne in lignes}),
        "pages_pypdf": pages_secondaires,
        "elements_marginaux_retires": marges,
        "corrections_ocr": corrections,
        "lignes_signatures_ocr_ignorees": signatures_ocr_ignorees,
        "zone_signatures_reconstruite_depuis_le_rendu": True,
    }


def parser_article(texte: str) -> dict | None:
    match = RE_ARTICLE.match(texte)
    if not match:
        return None
    return {"numero": int(match.group(1)), "corps": nettoyer_espaces(match.group(2) or "")}


def retablir_puces(lignes: list[Ligne], audit: list[dict]) -> list[Ligne]:
    resultat: list[Ligne] = []
    article_courant: int | None = None
    for ligne in lignes:
        article = parser_article(ligne.texte)
        if article:
            article_courant = article["numero"]
        texte = ligne.texte
        if article_courant in DEBUTS_PUCES and any(texte.startswith(prefixe) for prefixe in DEBUTS_PUCES[article_courant]):
            if not texte.startswith("- "):
                audit.append({
                    "page": ligne.page,
                    "article": article_courant,
                    "avant": texte,
                    "apres": f"- {texte}",
                    "raison": "tiret de liste visible sur la page mais absent de la couche OCR",
                })
                texte = f"- {texte}"
                ligne = replace(ligne, texte=texte, forcer_paragraphe=True)
        resultat.append(ligne)
    return resultat


def construire_structures(lignes: list[Ligne], limite: int) -> list[Evenement]:
    evenements: list[Evenement] = []
    for index, ligne in enumerate(lignes[:limite]):
        definition = STRUCTURES.get((ligne.page, ligne.texte))
        if not definition:
            continue
        niveau, segments, longueur = definition
        bruts = [item.texte for item in lignes[index:index + longueur]]
        attendu_aplati = nettoyer_espaces(" ".join(segments))
        observe_aplati = nettoyer_espaces(" ".join(bruts))
        if observe_aplati != attendu_aplati:
            raise RuntimeError(f"Structure inattendue page {ligne.page}: {observe_aplati!r} != {attendu_aplati!r}")
        evenements.append(Evenement(index, index + longueur, "structure", {
            "niveau": niveau,
            "segments": segments,
            "lignes": bruts,
        }))
    if len(evenements) != 15:
        raise RuntimeError(f"15 structures attendues, {len(evenements)} trouvées")
    return evenements


def nouvelle_partie(courant: list[str], ligne: Ligne, precedente: Ligne | None) -> bool:
    if not courant or precedente is None:
        return False
    if ligne.forcer_paragraphe or RE_ENUMERATION.match(ligne.texte):
        return True
    if ligne.page == precedente.page:
        return ligne.top - precedente.top > 14.5
    return bool(re.search(r"[.;:»]$", precedente.texte))


def formater(lignes: list[Ligne], article: dict | None = None) -> str:
    if not lignes:
        raise ValueError("Bloc vide")
    travail = list(lignes)
    etiquette = ""
    if article:
        etiquette = f"Article {article['numero']}.-"
        travail[0] = replace(travail[0], texte=article["corps"])
    paragraphes: list[str] = []
    courant: list[str] = []
    precedente: Ligne | None = None
    for ligne in travail:
        if not ligne.texte:
            continue
        if nouvelle_partie(courant, ligne, precedente):
            paragraphes.append(" ".join(courant))
            courant = []
        courant.append(ligne.texte)
        precedente = ligne
    if courant:
        paragraphes.append(" ".join(courant))
    corps = "\n\n".join(paragraphe.strip() for paragraphe in paragraphes if paragraphe.strip())
    return f"{etiquette}\n\n{corps}" if etiquette else corps


def chemin_et_metadata(etat: dict) -> tuple[str, dict]:
    segments = [RACINE]
    extra: dict = {}
    for niveau in ("titre", "chapitre", "section"):
        valeurs = etat.get(niveau) or []
        if valeurs:
            segments.extend(valeurs)
            extra[niveau] = " > ".join(valeurs)
    return " > ".join(segments), extra


def construire(lignes_entree: list[Ligne], base: dict, audit_extraction: dict) -> tuple[list[dict], str, dict]:
    lignes = retablir_puces(lignes_entree, audit_extraction["corrections_ocr"])
    articles = [(index, parser_article(ligne.texte)) for index, ligne in enumerate(lignes) if parser_article(ligne.texte)]
    numeros = [article["numero"] for _, article in articles]
    if numeros != list(range(1, 103)):
        manquants = sorted(set(range(1, 103)) - set(numeros))
        doublons = sorted(numero for numero, compte in Counter(numeros).items() if compte > 1)
        raise RuntimeError(f"Articles non séquentiels; manquants={manquants}, doublons={doublons}")
    index_visas = next(i for i, ligne in enumerate(lignes) if ligne.texte.startswith("Vu les Articles 217"))
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
    for numero, position in enumerate(positions):
        event = evenements[position]
        if event.type != "structure":
            event.fin = positions[numero + 1] if numero + 1 < len(positions) else len(lignes)

    chunks: list[dict] = []
    markdown_parties: list[str] = []
    etat = {"titre": [], "chapitre": [], "section": []}
    indices_structure = {i for event in structures for i in range(event.debut, event.fin)}

    def ajouter(contenu: str, article_label: str, type_bloc: str, chemin: str, extra: dict | None = None) -> None:
        metadata = {
            **base,
            "article": article_label,
            "type_bloc": type_bloc,
            "ordre": len(chunks) + 1,
            "chemin_hierarchique": chemin,
            **(extra or {}),
        }
        chunks.append({"page_content": contenu, "metadata": metadata})
        markdown_parties.append(contenu)

    for position in positions:
        event = evenements[position]
        if event.type == "structure":
            niveau = event.donnees["niveau"]
            etat[niveau] = event.donnees["segments"]
            if niveau == "titre":
                etat["chapitre"], etat["section"] = [], []
            elif niveau == "chapitre":
                etat["section"] = []
            markdown_parties.append("\n\n".join(event.donnees["lignes"]))
            continue
        if event.type == "preambule":
            contenu = formater(lignes[event.debut:event.fin])
            ajouter(contenu, "Préambule", "preambule", f"{RACINE} > PRÉAMBULE")
        elif event.type == "visas":
            contenu = formater(lignes[event.debut:event.fin])
            ajouter(contenu, "Visas", "visas", f"{RACINE} > VISAS")
        elif event.type == "cloture":
            contenu = "\n\n".join(CLOTURE_PARAGRAPHES)
            ajouter(contenu, "Clôture", "cloture", f"{RACINE} > CLÔTURE")
        elif event.type == "article":
            article = event.donnees["article"]
            contenu = formater(lignes[event.debut:event.fin], article)
            chemin, extra = chemin_et_metadata(etat)
            ajouter(contenu, f"Article {article['numero']}", "article", chemin, extra)

    markdown = "\n\n".join(markdown_parties) + "\n"
    reference_complete = [ligne.texte for ligne in lignes[:index_cloture]] + CLOTURE_PARAGRAPHES
    reference_chunks = [ligne.texte for i, ligne in enumerate(lignes[:index_cloture]) if i not in indices_structure] + CLOTURE_PARAGRAPHES
    return chunks, markdown, {
        "articles": numeros,
        "structures": [event.donnees for event in structures],
        "indices_structure": sorted(indices_structure),
        "reference_complete": reference_complete,
        "reference_chunks": reference_chunks,
    }


def sequence_hors_espaces(textes: list[str]) -> str:
    return "".join(re.sub(r"\s+", "", texte) for texte in textes)


def construire_rapport(
    pdf: Path,
    chunks: list[dict],
    markdown: str,
    audit_extraction: dict,
    audit_structure: dict,
    validation: dict,
    dossier: Path,
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
    moniteur_complet = all(bool(chunk["metadata"].get("moniteur_publication")) for chunk in chunks)
    return {
        "statut": "conforme_techniquement_a_relecture_humaine",
        "source": {
            "pdf": str(pdf.resolve()),
            "sha256": sha256(pdf),
            "pages": 20,
            "publication": "Le Moniteur, 160ème année, No. 38, jeudi 19 mai 2005",
            "extraction_principale": f"pdfplumber {pdfplumber.__version__}, couche OCR et géométrie",
            "verification_secondaire": f"pypdf {pypdf.__version__}",
            "verification_visuelle": "20 pages rendues et contrôlées; détails à 230 dpi",
        },
        "sorties": {
            "dossier_registre": str(dossier.resolve()),
            "markdown": "outputs/document.md",
            "chunks": "outputs/chunks.json",
        },
        "chunks": {
            "prevus": 105,
            "trouves": len(chunks),
            "ecart": len(chunks) - 105,
            "par_type_bloc": dict(sorted(types.items())),
        },
        "articles": {
            "prevus": 102,
            "trouves": len(articles),
            "numeros": audit_structure["articles"],
            "articles_introuvables": sorted(set(range(1, 103)) - set(audit_structure["articles"])),
            "doublons": sorted(numero for numero, compte in Counter(audit_structure["articles"]).items() if compte > 1),
        },
        "hierarchie": {
            "groupes_structuraux": len(audit_structure["structures"]),
            "tous_chunks_avec_chemin_hierarchique": all(bool(c["metadata"].get("chemin_hierarchique")) for c in chunks),
            "exemples": {
                label: next(c["metadata"]["chemin_hierarchique"] for c in chunks if c["metadata"]["article"] == label)
                for label in ("Article 3", "Article 14", "Article 47", "Article 82", "Article 101", "Article 102")
            },
        },
        "integrite_caracteres": {
            "reference": "couche OCR corrigée uniquement après contrôle visuel; espaces et retours normalisés",
            "reference_chunks_hors_espaces": len(reference_chunks),
            "chunks_hors_espaces": len(contenu_chunks),
            "chunks_identiques": reference_chunks == contenu_chunks,
            "caracteres_manquants": 0 if reference_chunks == contenu_chunks else None,
            "caracteres_ajoutes": 0 if reference_chunks == contenu_chunks else None,
            "markdown_incluant_structure_identique": reference_complete == contenu_markdown,
            "corrections_ocr_documentees": len(audit_extraction["corrections_ocr"]),
            "details_corrections": audit_extraction["corrections_ocr"],
        },
        "mise_en_page": {
            "retours_simples_dans_les_articles": retours_simples,
            "retours_simples_attendus": 0,
            "entetes_et_sommaire_ignores": len(audit_extraction["elements_marginaux_retires"]),
            "lignes_signatures_ocr_ignorees": audit_extraction["lignes_signatures_ocr_ignorees"],
            "zone_signatures_reconstruite_depuis_le_rendu": audit_extraction["zone_signatures_reconstruite_depuis_le_rendu"],
        },
        "metadata": {
            "date_demandee_dans_le_message": "2012-06-19",
            "date_imprimee_appliquee": "2005-02-16",
            "date_publication": "2005-05-19",
            "motif_correction_date": "le PDF indique: Donné au Palais National, le 16 février 2005",
            "historique": False,
            "tous_chunks_historique_false": all(c["metadata"].get("historique") is False for c in chunks),
            "moniteur": {"annee": 160, "numero": "38", "type": "ordinaire"},
            "regle_moniteur": "trois_cles_presentes_sur_tous_les_chunks" if moniteur_complet else "non_conforme",
            "types_bloc_utilises": sorted(types),
            "types_bloc_valides_backend": sorted(types_valides),
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
            "La date 2012-06-19 fournie dans le message ne correspond pas au document; la date juridique imprimée 2005-02-16 a été appliquée.",
            "La numérotation imprimée passe du TITRE III au TITRE V; aucun TITRE IV n'a été inventé.",
            "Le texte imprimé de l'Article 46 présente une continuité grammaticale inhabituelle; il a été conservé sans correction juridique.",
            "Les noms de la clôture, partiellement masqués dans la couche OCR par les signatures, ont été retranscrits depuis le rendu des pages 19 et 20.",
        ],
        "suggestions": ["Relire prioritairement l'Article 46 et les noms des signataires avant insertion définitive."],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("racine_conversion", type=Path)
    parser.add_argument("backend", type=Path)
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
        "source": "Arrêté portant règlement général de la Comptabilité Publique",
        "source_courte": "Arrêté comptabilité publique 2005",
        "type_norme": "arrete",
        "rang": RANGS_PAR_TYPE_NORME["arrete"],
        "date": "2005-02-16",
        "date_publication": "2005-05-19",
        "statut": "en_vigueur",
        "moniteur_publication": "Le Moniteur, 160e année, Ordinaire no 38, 19 mai 2005",
        "mots_cles": ["comptabilité publique", "finances publiques", "Trésor", "comptables publics", "budget"],
        "type_thematique": ["droit_administratif", "droit_fiscal"],
        "historique": False,
        "abroge_par": None,
        "publication_abrogation": None,
        "date_abrogation": None,
    }
    registre = Registre(args.racine_conversion / "registry")
    record = registre.inscrire(args.pdf, base, "Arrêté portant règlement général de la Comptabilité Publique")
    dossier, _ = registre.lire(record["document_id"])
    lignes, audit_extraction = extraire_lignes(args.pdf)
    chunks, markdown, audit_structure = construire(lignes, base, audit_extraction)
    validation = _valider_donnees(chunks)
    rapport = construire_rapport(
        args.pdf, chunks, markdown, audit_extraction, audit_structure, validation, dossier, set(TYPES_BLOC_VALIDES)
    )

    (dossier / "outputs" / "document.md").write_text(markdown, encoding="utf-8", newline="\n")
    (dossier / "outputs" / "chunks.json").write_text(
        json.dumps(chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (dossier / "outputs" / "rapport.json").write_text(
        json.dumps(rapport, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (dossier / "outputs" / "rapport_validation_backend.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (dossier / "review" / "points_a_revoir.json").write_text(
        json.dumps({"statut": "a_revoir", "points": rapport["points_a_revoir"]}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (dossier / "configuration" / "pipeline.json").write_text(
        json.dumps({
            "extracteur_principal": f"pdfplumber {pdfplumber.__version__}",
            "verificateur": f"pypdf {pypdf.__version__}",
            "source_texte": "couche OCR intégrée au PDF",
            "controle_visuel_pages": 20,
            "rendu_detail_dpi": 230,
            "analyse_geometrique": True,
            "seuil_nouveau_paragraphe_points": 14.5,
            "entetes_moniteur_ignores": True,
            "titres_migres_vers_chemin_hierarchique": True,
            "corrections_juridiques_silencieuses": False,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
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
        json.dumps(manifeste, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    registre.changer_etat(record["document_id"], "a_revoir")
    print(json.dumps({
        "document_id": record["document_id"],
        "dossier": str(dossier),
        "chunks": len(chunks),
        "articles": sum(c["metadata"]["type_bloc"] == "article" for c in chunks),
        "validation_backend": validation.get("valide"),
        "pret_pour_insertion": validation.get("pret_pour_insertion"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
