#!/usr/bin/env python3
"""Convertit le Code civil LexHaïti en Markdown et chunks JSON auditables."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pdfplumber
import pypdf


RACINE = "CODE CIVIL D’HAÏTI"
SOURCE = "Code civil d’Haïti"
DATE_METADATA = "2023-01-01"
DATE_PUBLICATION = "1825-03-27"
PREMIERE_PAGE_JURIDIQUE = 7
DERNIERE_PAGE_ARTICLES = 302
PAGE_CLOTURE = 303
NB_PAGES_ATTENDU = 303
NB_ARTICLES_ATTENDU = 2047
NB_STRUCTURES_FORMELLES_ATTENDU = 318

RE_ARTICLE = re.compile(r"^Article (Premier|\d+)$")
RE_STRUCTURE = re.compile(r"^(LIVRE|TITRE|CHAPITRE|SECTION|SOUS-SECTION)\b")
RE_ENUMERATION = re.compile(
    r"^(?:\d+\s*[°º]\s+|\d+\s*[.)-]\s+|[a-zA-Z]\)\s+|"
    r"[IVXLCDM]+[.)]\s+|[-–—•]\s+)",
    re.IGNORECASE,
)
RE_MINUSCULE = re.compile(r"^[a-zà-öø-ÿœæ]")


# Ces sous-divisions existent visuellement dans le document, mais sont rendues
# dans la même police que le corps. Elles sont donc promues explicitement dans
# la hiérarchie sans corriger leurs caractères parfois dégradés dans la source.
PROMOTIONS_AVANT_ARTICLE: dict[int, list[str]] = {
    260: [
        "section ni.",
        "Des Fins de non-recevoir contre V action en divorce pour cause déterminée.",
    ],
    605: [
        "section ni.",
        "Des Successions déférées aux Descendants, soit légitimes, soit naturels.",
    ],
    1007: ["s i.", "Des Effets de l'Obligation divisible."],
    1009: ["S n. Des Effets de l'Obligation indivisible."],
    1035: ["S ii. Du Payement avec subrogation."],
    1039: ["S mDe l'Imputation des Payements."],
    1107: ["De l'Acte sous seing privé."],
    1122: ["s*. Des Actes récognitifs et confirrnatifs."],
    1135: ["Des Présomptions établies par la loi."],
    1152: ["S n. Du Serment déféré d'office."],
    1186: ["PREMIÈRE PARTIE. De la Communauté légale."],
    1194: [
        "SuDu Passif de la Communauté, et des Actions qui en résultent contre la Communauté."
    ],
    1253: ["Si. Du Partage de V Actif."],
    1312: ["Dispositions communes aux huit Sections ci-dessus."],
    1315: ["s h,", "De la Clause portant que les Époux se marient sans Communauté."],
    1321: ["Sn. De la Clause de séparation de biens."],
    1411: ["De la Garantie en cas d'éviction."],
    1426: ["Sn. De la Garantie des défauts de la chose vendue."],
    1444: ["De la Faculté de rachat."],
    1642: ["Dispositions relatives aux Sociétés de Commerce,"],
    2047: ["Dispositions générales."],
}


ARTEFACTS_SOURCE_RECHERCHES = (
    "pension aliet mentaire",
    "V action en divorce",
    "unimmeuble",
    "obstac\\e",
    "comp-| table",
    "primogénilure",
    "[demande en divorce",
    "31. Pour faire une donation",
    "an 23 e en:",
)


# En-têtes et numéros de pages de l'édition ancienne injectés au milieu de la
# couche texte LexHaïti. Leur retrait est demandé explicitement par l'utilisateur.
RETRAITS_MARGINAUX_INTERNES = {
    (44, "i"),
    (44, "46 ÉTAT ET CAPACITÉ DES PERSONNES."),
    (53, "."),
    (59, "."),
    (59, "62 ÉTAT ET CAPACITÉ DES PERSONNES."),
    (97, "1 10 MANIÈRES D'ACQUÉRIR LA PROPRIÉTÉ."),
    (99, "IIS MANIÈRES D'ACQUÉRIR LA PROPRIETE."),
    (190, "2^0 MANIÈRES DACQUÉR1R LA PROPRIÉTÉ."),
    (195, ","),
    (195, "226 MANIÈRES D'ACQUÉRIR LA PROPRIÉTÉ."),
    (199, "."),
    (199, "230 MANIÈRES D'ACQUÉRIR LA PROPRIÉTÉ."),
    (208, "L0[ 22. DE LA VENTE. 241"),
}

REMPLACEMENTS_MARGINAUX_INTERNES = {
    (
        53,
        "56 ÉTAT ET CAPACITÉ DES PERSONNES. l'émancipation qui pourrait avoir lieu avant l'âge de vingt-un",
    ): "l'émancipation qui pourrait avoir lieu avant l'âge de vingt-un",
}


@dataclass(frozen=True)
class Ligne:
    ordre: int
    page: int
    top: float
    texte: str
    type: str
    police: str
    taille: float
    origine: str = "couche_texte_native"


@dataclass(frozen=True)
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
    return unicodedata.normalize("NFC", re.sub(r"[ \t]+", " ", texte).strip())


def police_dominante(chars: list[dict]) -> tuple[str, float]:
    if not chars:
        return "", 0.0
    compte = Counter(
        (str(char.get("fontname") or ""), round(float(char.get("size") or 0.0), 1))
        for char in chars
        if (char.get("text") or "").strip()
    )
    return compte.most_common(1)[0][0] if compte else ("", 0.0)


def classifier(texte: str, police: str, taille: float, page: int) -> str:
    if page == PAGE_CLOTURE:
        return "cloture"
    if RE_ARTICLE.fullmatch(texte) and "Ultra-Bold" in police and 9.0 <= taille <= 10.0:
        return "article"
    if RE_STRUCTURE.match(texte) and "DM-Sans-Bold" in police and 7.5 <= taille <= 8.5:
        return "structure_label"
    if "Source-Serif-4-Bold" in police and 15.0 <= taille <= 16.5:
        return "structure_title"
    return "corps"


def extraire_lignes(pdf: Path) -> tuple[list[Ligne], dict]:
    lignes: list[Ligne] = []
    exclusions = Counter()
    exemples_exclus: dict[str, list[dict]] = {}
    coupures_documentees: list[dict] = []
    retraits_marginaux_internes: list[dict] = []
    ordre = 0

    def exclure(raison: str, page: int, top: float, texte: str) -> None:
        exclusions[raison] += 1
        exemples_exclus.setdefault(raison, [])
        if len(exemples_exclus[raison]) < 3:
            exemples_exclus[raison].append(
                {"page": page, "top": round(top, 1), "texte": texte}
            )

    with pdfplumber.open(pdf) as document:
        if len(document.pages) != NB_PAGES_ATTENDU:
            raise RuntimeError(
                f"{NB_PAGES_ATTENDU} pages attendues, {len(document.pages)} trouvées"
            )
        for page_numero, page in enumerate(document.pages, 1):
            items = page.extract_text_lines(layout=False, strip=True, return_chars=True)
            for item in items:
                top = float(item["top"])
                texte = nettoyer_espaces(item["text"])
                if not texte:
                    continue
                if page_numero < PREMIERE_PAGE_JURIDIQUE:
                    exclure("couverture_et_table_des_matieres", page_numero, top, texte)
                    continue
                if top <= 50:
                    exclure("entete_repetitif_lexhaiti", page_numero, top, texte)
                    continue
                if top >= 780:
                    raison = (
                        "source_lexhaiti_et_pagination"
                        if "https://lexhaiti.org/loi/code-civil" in texte
                        else "pied_de_page"
                    )
                    exclure(raison, page_numero, top, texte)
                    continue
                if (page_numero, texte) in RETRAITS_MARGINAUX_INTERNES:
                    exclure("ancien_entete_ou_numero_page_integre", page_numero, top, texte)
                    retraits_marginaux_internes.append(
                        {
                            "page": page_numero,
                            "avant": texte,
                            "apres": None,
                            "raison": "ancien en-tête, numéro ou séparateur de page, contrôlé visuellement",
                        }
                    )
                    continue
                remplacement_marginal = REMPLACEMENTS_MARGINAUX_INTERNES.get(
                    (page_numero, texte)
                )
                if remplacement_marginal is not None:
                    retraits_marginaux_internes.append(
                        {
                            "page": page_numero,
                            "avant": texte,
                            "apres": remplacement_marginal,
                            "raison": "préfixe d'ancien en-tête de page retiré; texte juridique conservé",
                        }
                    )
                    texte = remplacement_marginal

                police, taille = police_dominante(item.get("chars") or [])
                type_ligne = classifier(texte, police, taille, page_numero)

                # Une seule ligne fusionne la fin de l'article 1320 et le sous-titre
                # suivant. La séparation ne modifie aucun caractère non blanc.
                fusion = "l'autorisation de la justice. Sn. De la Clause de séparation de biens."
                if texte == fusion:
                    morceaux = (
                        ("l'autorisation de la justice.", "corps"),
                        ("Sn. De la Clause de séparation de biens.", "corps"),
                    )
                    for decalage, (morceau, type_morceau) in enumerate(morceaux):
                        lignes.append(
                            Ligne(
                                ordre, page_numero, top + decalage / 1000,
                                morceau, type_morceau, police, taille,
                                "ligne_source_scindee_sans_changement_de_caracteres",
                            )
                        )
                        ordre += 1
                    coupures_documentees.append(
                        {
                            "page": page_numero,
                            "avant": fusion,
                            "apres": [morceau for morceau, _ in morceaux],
                            "caracteres_non_blancs_identiques": True,
                            "raison": "fin de l'article 1320 et sous-titre de l'article 1321 fusionnés",
                        }
                    )
                    continue

                lignes.append(
                    Ligne(ordre, page_numero, top, texte, type_ligne, police, taille)
                )
                ordre += 1

    with pdf.open("rb") as stream:
        lecteur = pypdf.PdfReader(stream)
        pages_pypdf = len(lecteur.pages)
        metadonnees_pdf = {
            str(cle).lstrip("/"): str(valeur)
            for cle, valeur in (lecteur.metadata or {}).items()
            if valeur is not None
        }
        texte_couverture = lecteur.pages[0].extract_text() or ""

    return lignes, {
        "pages_pdfplumber": NB_PAGES_ATTENDU,
        "pages_pypdf": pages_pypdf,
        "pages_juridiques_retenues": [PREMIERE_PAGE_JURIDIQUE, PAGE_CLOTURE],
        "pages_couverture_sommaire_exclues": [1, 6],
        "lignes_retenues": len(lignes),
        "lignes_exclues_par_raison": dict(sorted(exclusions.items())),
        "exemples_exclus": exemples_exclus,
        "scissions_documentees": coupures_documentees,
        "retraits_marginaux_internes_documentes": retraits_marginaux_internes,
        "metadata_pdf": metadonnees_pdf,
        "version_affichee": "25 mai 2026" if "25 mai 2026" in texte_couverture else None,
        "generation_affichee": "5 août 2026" if "5 août 2026" in texte_couverture else None,
        "ocr_requis": False,
    }


def numero_article(texte: str) -> int | None:
    match = RE_ARTICLE.fullmatch(texte)
    if not match:
        return None
    return 1 if match.group(1) == "Premier" else int(match.group(1))


def construire_evenements(lignes: list[Ligne]) -> tuple[list[Evenement], dict]:
    evenements: list[Evenement] = []
    structure_indices: set[int] = set()
    compte_formel = Counter()

    index = 0
    while index < len(lignes):
        ligne = lignes[index]
        if ligne.type == "structure_label":
            match = RE_STRUCTURE.match(ligne.texte)
            if not match:
                raise RuntimeError(f"Structure illisible à la ligne {index}: {ligne.texte}")
            niveau_source = match.group(1)
            fin = index + 1
            while fin < len(lignes) and lignes[fin].type == "structure_title":
                fin += 1
            if fin == index + 1:
                raise RuntimeError(f"Titre structurel absent après {ligne.texte!r}")
            segments_source = [element.texte for element in lignes[index:fin]]
            titres_fusionnes: list[str] = []
            cesures_structure = 0
            for titre in segments_source[1:]:
                if titres_fusionnes and titres_fusionnes[-1].endswith("-") and RE_MINUSCULE.match(titre):
                    titres_fusionnes[-1] = titres_fusionnes[-1][:-1] + titre
                    cesures_structure += 1
                else:
                    titres_fusionnes.append(titre)
            segments = [segments_source[0], *titres_fusionnes]
            niveau = {
                "LIVRE": "livre",
                "TITRE": "titre",
                "CHAPITRE": "chapitre",
                "SECTION": "section",
                "SOUS-SECTION": "paragraphe",
            }[niveau_source]
            evenements.append(
                Evenement(
                    index,
                    fin,
                    "structure",
                    {
                        "niveau": niveau,
                        "niveau_source": niveau_source,
                        "segments": segments,
                        "valeur": f"{segments[0]} — {' '.join(segments[1:])}",
                        "origine": "typographie_pdf",
                        "cesures_supprimees": cesures_structure,
                    },
                )
            )
            structure_indices.update(range(index, fin))
            compte_formel[niveau_source] += 1
            index = fin
            continue
        index += 1

    articles_par_numero: dict[int, int] = {}
    for index, ligne in enumerate(lignes):
        if ligne.type != "article":
            continue
        numero = numero_article(ligne.texte)
        if numero is None or numero in articles_par_numero:
            raise RuntimeError(f"Article invalide ou dupliqué: {ligne.texte!r}")
        articles_par_numero[numero] = index

    trouves = sorted(articles_par_numero)
    attendus = list(range(1, NB_ARTICLES_ATTENDU + 1))
    if trouves != attendus:
        manquants = sorted(set(attendus) - set(trouves))
        inattendus = sorted(set(trouves) - set(attendus))
        raise RuntimeError(
            f"Séquence d'articles incohérente; manquants={manquants}, inattendus={inattendus}"
        )

    promotions: list[dict] = []
    for article, segments in PROMOTIONS_AVANT_ARTICLE.items():
        article_index = articles_par_numero[article]
        debut = article_index - len(segments)
        if debut < 0:
            raise RuntimeError(f"Position impossible pour le sous-titre avant l'article {article}")
        reels = [ligne.texte for ligne in lignes[debut:article_index]]
        if reels != segments:
            raise RuntimeError(
                f"Sous-titre non confirmé avant l'article {article}: attendu={segments!r}, trouvé={reels!r}"
            )
        if any(position in structure_indices for position in range(debut, article_index)):
            raise RuntimeError(f"Chevauchement structurel avant l'article {article}")
        valeur = segments[0] if len(segments) == 1 else f"{segments[0]} — {' '.join(segments[1:])}"
        evenements.append(
            Evenement(
                debut,
                article_index,
                "structure",
                {
                    "niveau": "paragraphe",
                    "niveau_source": "SOUS-DIVISION NON STYLÉE",
                    "segments": segments,
                    "valeur": valeur,
                    "origine": "promotion_apres_controle_visuel",
                    "cesures_supprimees": 0,
                },
            )
        )
        structure_indices.update(range(debut, article_index))
        promotions.append(
            {
                "article_cible": f"Article {article}",
                "page": lignes[debut].page,
                "segments": segments,
                "valeur_hierarchique": valeur,
            }
        )

    for numero, article_index in sorted(articles_par_numero.items()):
        evenements.append(
            Evenement(
                article_index,
                article_index + 1,
                "article",
                {"numero": numero, "etiquette": lignes[article_index].texte},
            )
        )

    cloture_indices = [
        index for index, ligne in enumerate(lignes) if ligne.page == PAGE_CLOTURE
    ]
    if not cloture_indices:
        raise RuntimeError("Clôture de la page 303 absente")
    debut_cloture, fin_cloture = min(cloture_indices), max(cloture_indices) + 1
    if cloture_indices != list(range(debut_cloture, fin_cloture)):
        raise RuntimeError("Lignes de clôture non contiguës")
    evenements.append(
        Evenement(debut_cloture, fin_cloture, "cloture", {"etiquette": "Clôture"})
    )

    evenements.sort(key=lambda event: (event.debut, 0 if event.type == "structure" else 1))
    debuts = [event.debut for event in evenements]
    if len(debuts) != len(set(debuts)):
        doubles = [position for position, nombre in Counter(debuts).items() if nombre > 1]
        raise RuntimeError(f"Événements en conflit aux positions {doubles}")

    if sum(compte_formel.values()) != NB_STRUCTURES_FORMELLES_ATTENDU:
        raise RuntimeError(
            f"{NB_STRUCTURES_FORMELLES_ATTENDU} structures formelles attendues, "
            f"{sum(compte_formel.values())} trouvées: {dict(compte_formel)}"
        )

    return evenements, {
        "compte_formel": dict(sorted(compte_formel.items())),
        "nb_structures_formelles": sum(compte_formel.values()),
        "nb_sous_divisions_promues": len(promotions),
        "sous_divisions_promues": promotions,
        "indices_structure": sorted(structure_indices),
    }


def appliquer_cesures(textes: Iterable[str]) -> tuple[list[str], int]:
    resultat: list[str] = []
    cesures = 0
    for texte in textes:
        if resultat and resultat[-1].endswith("-") and RE_MINUSCULE.match(texte):
            resultat[-1] = resultat[-1][:-1] + texte
            cesures += 1
        else:
            resultat.append(texte)
    return resultat, cesures


def formater_lignes(lignes: list[Ligne], listes: bool) -> tuple[str, int]:
    if not lignes:
        return "", 0
    paragraphes: list[list[str]] = [[]]
    for ligne in lignes:
        if listes and paragraphes[-1] and RE_ENUMERATION.match(ligne.texte):
            paragraphes.append([])
        paragraphes[-1].append(ligne.texte)

    rendus: list[str] = []
    total_cesures = 0
    for paragraphe in paragraphes:
        fusionnes, cesures = appliquer_cesures(paragraphe)
        total_cesures += cesures
        rendus.append(" ".join(fusionnes))
    return "\n\n".join(rendus), total_cesures


def prochain_debut(evenements: list[Evenement], position: int, limite: int) -> int:
    return min((event.debut for event in evenements if event.debut > position), default=limite)


def construire_chunks_et_markdown(
    lignes: list[Ligne], evenements: list[Evenement], base: dict
) -> tuple[list[dict], str, dict]:
    chunks: list[dict] = []
    markdown: list[str] = []
    hierarchie: dict[str, str | None] = {
        "livre": None,
        "titre": None,
        "chapitre": None,
        "section": None,
        "paragraphe": None,
    }
    ordre_niveaux = ["livre", "titre", "chapitre", "section", "paragraphe"]
    lignes_structure: set[int] = set()
    lignes_chunks: set[int] = set()
    cesures_supprimees = 0

    for event in evenements:
        if event.type == "structure":
            niveau = event.donnees["niveau"]
            hierarchie[niveau] = event.donnees["valeur"]
            position_niveau = ordre_niveaux.index(niveau)
            for enfant in ordre_niveaux[position_niveau + 1 :]:
                hierarchie[enfant] = None
            markdown.append("\n\n".join(event.donnees["segments"]))
            cesures_supprimees += event.donnees.get("cesures_supprimees", 0)
            lignes_structure.update(range(event.debut, event.fin))
            continue

        if event.type == "article":
            fin = prochain_debut(evenements, event.debut, len(lignes))
            corps_indices = [
                index
                for index in range(event.fin, fin)
                if index not in lignes_structure
            ]
            corps_lignes = [lignes[index] for index in corps_indices]
            corps, cesures = formater_lignes(corps_lignes, listes=True)
            cesures_supprimees += cesures
            if not corps:
                raise RuntimeError(f"Corps vide pour {event.donnees['etiquette']}")
            page_content = f"{event.donnees['etiquette']}\n\n{corps}"
            article_indices = [event.debut, *corps_indices]
            lignes_chunks.update(article_indices)
            article_label = event.donnees["etiquette"]
            metadata = {
                **base,
                "article": article_label,
                "type_bloc": "article",
                "ordre": len(chunks) + 1,
            }
            segments_chemin = [RACINE]
            for niveau in ordre_niveaux:
                valeur = hierarchie[niveau]
                if valeur:
                    metadata[niveau] = valeur
                    segments_chemin.append(valeur)
            metadata["chemin_hierarchique"] = " > ".join(segments_chemin)
            chunks.append({"page_content": page_content, "metadata": metadata})
            markdown.append(page_content)
            continue

        if event.type == "cloture":
            segment = lignes[event.debut:event.fin]
            page_content = "\n\n".join(ligne.texte for ligne in segment)
            lignes_chunks.update(range(event.debut, event.fin))
            metadata = {
                **base,
                "article": "Clôture",
                "type_bloc": "cloture",
                "ordre": len(chunks) + 1,
                "chemin_hierarchique": f"{RACINE} > CLÔTURE",
            }
            chunks.append({"page_content": page_content, "metadata": metadata})
            markdown.append(page_content)
            continue

        raise RuntimeError(f"Type d'événement inconnu: {event.type}")

    couverture = lignes_structure | lignes_chunks
    non_affectees = sorted(set(range(len(lignes))) - couverture)
    if non_affectees:
        apercu = [
            {"index": index, "page": lignes[index].page, "texte": lignes[index].texte}
            for index in non_affectees[:20]
        ]
        raise RuntimeError(f"Lignes retenues non affectées: {apercu}")

    return chunks, "\n\n".join(markdown) + "\n", {
        "indices_structure": sorted(lignes_structure),
        "indices_chunks": sorted(lignes_chunks),
        "lignes_non_affectees": non_affectees,
        "cesures_typographiques_supprimees": cesures_supprimees,
    }


def sequence_non_blanche(texte: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", texte))


def reference_depuis_lignes(lignes: list[Ligne], indices: Iterable[int]) -> tuple[str, int]:
    selection = [lignes[index].texte for index in sorted(indices)]
    fusionnes, cesures = appliquer_cesures(selection)
    return sequence_non_blanche(" ".join(fusionnes)), cesures


def trouver_artefacts(lignes: list[Ligne]) -> list[dict]:
    trouves: list[dict] = []
    deja: set[tuple[int, str]] = set()
    lignes_signalees: set[int] = set()
    for ligne in lignes:
        for motif in ARTEFACTS_SOURCE_RECHERCHES:
            if motif in ligne.texte and (ligne.page, motif) not in deja:
                deja.add((ligne.page, motif))
                lignes_signalees.add(ligne.ordre)
                trouves.append(
                    {
                        "page": ligne.page,
                        "motif": motif,
                        "ligne_source": ligne.texte,
                        "action": "conservé exactement; relecture humaine recommandée",
                    }
                )
        if (
            ligne.ordre not in lignes_signalees
            and re.search(r"[\\|\[\]]", ligne.texte)
            and (ligne.page, ligne.texte) not in deja
        ):
            deja.add((ligne.page, ligne.texte))
            trouves.append(
                {
                    "page": ligne.page,
                    "motif": "glyphe OCR inhabituel (crochet, barre verticale ou barre oblique inverse)",
                    "ligne_source": ligne.texte,
                    "action": "conservé exactement; correction interdite sans source juridique de comparaison",
                }
            )
    return trouves


def construire_rapport(
    pdf: Path,
    dossier: Path,
    lignes: list[Ligne],
    chunks: list[dict],
    markdown: str,
    audit_extraction: dict,
    audit_structure: dict,
    audit_construction: dict,
    validation: dict,
    types_valides: set[str],
) -> dict:
    articles = [chunk for chunk in chunks if chunk["metadata"]["type_bloc"] == "article"]
    numeros = [numero_article(chunk["metadata"]["article"]) for chunk in articles]
    attendus = set(range(1, NB_ARTICLES_ATTENDU + 1))
    trouves = {numero for numero in numeros if numero is not None}
    types = Counter(chunk["metadata"]["type_bloc"] for chunk in chunks)

    indices_chunks = audit_construction["indices_chunks"]
    indices_tous = range(len(lignes))
    source_chunks, cesures_reference_chunks = reference_depuis_lignes(lignes, indices_chunks)
    chunks_sequence = sequence_non_blanche(
        " ".join(chunk["page_content"] for chunk in chunks)
    )
    source_markdown, cesures_reference_markdown = reference_depuis_lignes(lignes, indices_tous)
    markdown_sequence = sequence_non_blanche(markdown)
    identique_chunks = source_chunks == chunks_sequence
    identique_markdown = source_markdown == markdown_sequence
    simples = sum(
        len(re.findall(r"(?<!\n)\n(?!\n)", chunk["page_content"]))
        for chunk in chunks
    )
    artefacts = trouver_artefacts(lignes)
    cles_moniteur = {"moniteur_publication"}

    return {
        "statut": "conforme_techniquement_a_relecture_humaine",
        "source": {
            "pdf": str(pdf.resolve()),
            "sha256": sha256(pdf),
            "octets": pdf.stat().st_size,
            "pages": NB_PAGES_ATTENDU,
            "pages_juridiques_traitees": "7-303",
            "pages_exclues": "1-6 (couverture et sommaire)",
            "date_metadata_demandee": DATE_METADATA,
            "date_promulgation_affichee_dans_le_pdf": "1825-03-27",
            "date_publication_affichee_dans_le_pdf": DATE_PUBLICATION,
            "version_affichee_dans_le_pdf": audit_extraction["version_affichee"],
            "document_genere_affiche": audit_extraction["generation_affichee"],
            "extraction": f"pdfplumber {pdfplumber.__version__}, couche texte native et géométrie",
            "contre_verification": f"pypdf {pypdf.__version__}",
            "ocr_requis": False,
        },
        "sorties": {
            "dossier_registre": str(dossier.resolve()),
            "markdown": "outputs/document.md",
            "chunks": "outputs/chunks.json",
            "rapport_validation_backend": "outputs/rapport_validation_backend.json",
            "extraction_auditable": "extraction/lignes_pdf.json",
            "points_a_revoir": "review/points_a_revoir.json",
        },
        "chunks": {
            "prevus": NB_ARTICLES_ATTENDU + 1,
            "trouves": len(chunks),
            "ecart": len(chunks) - (NB_ARTICLES_ATTENDU + 1),
            "par_type_bloc": dict(sorted(types.items())),
            "types_bloc_non_valides": sorted(set(types) - types_valides),
        },
        "articles": {
            "prevus": NB_ARTICLES_ATTENDU,
            "trouves": len(articles),
            "premier": articles[0]["metadata"]["article"] if articles else None,
            "dernier": articles[-1]["metadata"]["article"] if articles else None,
            "articles_introuvables": sorted(attendus - trouves),
            "articles_inattendus": sorted(trouves - attendus),
            "articles_dupliques": sorted(
                numero for numero, nombre in Counter(numeros).items() if nombre > 1
            ),
            "sequence_1_a_2047_continue": numeros == list(range(1, NB_ARTICLES_ATTENDU + 1)),
        },
        "hierarchie": {
            "racine": RACINE,
            "structures_formelles_prevues": NB_STRUCTURES_FORMELLES_ATTENDU,
            "structures_formelles_trouvees": audit_structure["nb_structures_formelles"],
            "structures_par_type": audit_structure["compte_formel"],
            "sous_divisions_non_stylees_promues": audit_structure["nb_sous_divisions_promues"],
            "articles_avec_chemin_hierarchique": sum(
                bool(chunk["metadata"].get("chemin_hierarchique")) for chunk in articles
            ),
            "articles_sans_chemin_hierarchique": [
                chunk["metadata"]["article"]
                for chunk in articles
                if not chunk["metadata"].get("chemin_hierarchique")
            ],
            "details_promotions": audit_structure["sous_divisions_promues"],
        },
        "integrite_caracteres": {
            "regle": (
                "comparaison Unicode NFC hors espaces; seules les césures typographiques de fin "
                "de ligne ont été ressoudées lorsque la ligne suivante commence par une minuscule"
            ),
            "source_chunks_non_blanche": len(source_chunks),
            "sortie_chunks_non_blanche": len(chunks_sequence),
            "chunks_identiques_a_la_source": identique_chunks,
            "caracteres_manquants": 0 if identique_chunks else None,
            "caracteres_ajoutes": 0 if identique_chunks else None,
            "markdown_incluant_structures_identique_a_la_source": identique_markdown,
            "cesures_reference_chunks": cesures_reference_chunks,
            "cesures_reference_markdown": cesures_reference_markdown,
            "cesures_sortie": audit_construction["cesures_typographiques_supprimees"],
            "lignes_retenues_non_affectees": audit_construction["lignes_non_affectees"],
        },
        "mise_en_page": {
            "retours_simples_dans_page_content": simples,
            "retours_simples_attendus": 0,
            "separateur_paragraphe": "deux retours; article/corps, énumérations et signatures seulement",
            "entetes_repetitifs_ignores": audit_extraction["lignes_exclues_par_raison"].get(
                "entete_repetitif_lexhaiti", 0
            ),
            "pieds_source_et_pagination_ignores": audit_extraction[
                "lignes_exclues_par_raison"
            ].get("source_lexhaiti_et_pagination", 0),
            "anciens_entetes_et_numeros_integres_ignores": audit_extraction[
                "lignes_exclues_par_raison"
            ].get("ancien_entete_ou_numero_page_integre", 0),
            "url_source_presente_dans_page_content": any(
                "https://lexhaiti.org/loi/code-civil" in chunk["page_content"]
                for chunk in chunks
            ),
        },
        "metadata": {
            "date": sorted({chunk["metadata"]["date"] for chunk in chunks}),
            "date_publication": sorted({chunk["metadata"]["date_publication"] for chunk in chunks}),
            "historique": sorted({chunk["metadata"]["historique"] for chunk in chunks}),
            "tous_chunks_historique_false": all(
                chunk["metadata"]["historique"] is False for chunk in chunks
            ),
            "abroge_par": list(dict.fromkeys(
                chunk["metadata"].get("abroge_par") for chunk in chunks
            )),
            "publication_abrogation": list(dict.fromkeys(
                chunk["metadata"].get("publication_abrogation") for chunk in chunks
            )),
            "date_abrogation": list(dict.fromkeys(
                chunk["metadata"].get("date_abrogation") for chunk in chunks
            )),
            "tous_chunks_abrogation_non_renseignee": all(
                chunk["metadata"].get(cle) is None
                for chunk in chunks
                for cle in (
                    "abroge_par", "publication_abrogation", "date_abrogation"
                )
            ),
            "chunks_avec_une_cle_moniteur": sum(
                bool(set(chunk["metadata"]) & cles_moniteur) for chunk in chunks
            ),
            "regle_moniteur_tout_ou_rien": "respectée: aucune des trois clés n'est fournie",
            "tous_chunks_avec_chemin_hierarchique": all(
                bool(chunk["metadata"].get("chemin_hierarchique")) for chunk in chunks
            ),
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
        "controle_qualite": {
            "pages_controlees_visuellement": "1-303",
            "planches_contact_controlees": 19,
            "pages_plein_format_echantillonnees": [
                43, 95, 150, 151, 154, 155, 165, 168, 170, 173, 178, 179,
                189, 199, 200, 201, 212, 214, 216, 242, 302, 303,
            ],
            "artefacts_deja_presents_dans_la_source": artefacts,
            "nombre_artefacts_reperes": len(artefacts),
            "corrections_silencieuses": False,
        },
        "suggestions": [
            "Relire les sous-divisions non stylées et les artefacts signalés avant insertion.",
            "Comparer les passages dégradés à une édition officielle ou à un fac-similé de 1825; la couche texte LexHaïti contient des défauts hérités qui ont été conservés.",
            "Conserver le statut a_revoir jusqu'à la validation manuelle demandée.",
        ],
        "audit_extraction": audit_extraction,
    }


def serialiser_lignes(lignes: list[Ligne]) -> list[dict]:
    return [
        {
            "ordre": ligne.ordre,
            "page": ligne.page,
            "top": round(ligne.top, 3),
            "type": ligne.type,
            "texte": ligne.texte,
            "police": ligne.police,
            "taille": ligne.taille,
            "origine": ligne.origine,
        }
        for ligne in lignes
    ]


def ecrire_json(path: Path, donnees: object) -> None:
    path.write_text(
        json.dumps(donnees, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("racine_conversion", type=Path)
    parser.add_argument("backend", type=Path)
    parser.add_argument(
        "--registry-root",
        type=Path,
        help="Registre de sortie alternatif pour les essais isolés",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(args.racine_conversion.resolve()))
    sys.path.insert(0, str(args.backend.resolve()))
    site_packages = args.backend / ".venv" / "Lib" / "site-packages"
    if site_packages.is_dir():
        sys.path.insert(0, str(site_packages))

    from halex_conversion.registry import Registre
    from ingestion_admin import _valider_donnees
    from schema_metadata import RANGS_PAR_TYPE_NORME, TYPES_BLOC_VALIDES

    requis = {"article", "cloture"}
    if not requis <= set(TYPES_BLOC_VALIDES):
        raise RuntimeError(
            f"TYPES_BLOC_VALIDES incomplet: {sorted(requis - set(TYPES_BLOC_VALIDES))}"
        )

    base = {
        "source": SOURCE,
        "source_courte": SOURCE,
        "type_norme": "code",
        "rang": RANGS_PAR_TYPE_NORME["code"],
        "date": DATE_METADATA,
        "date_publication": DATE_PUBLICATION,
        "statut": "en_vigueur",
        "mots_cles": [
            "code civil", "personnes", "famille", "biens", "obligations",
            "contrats", "successions",
        ],
        "type_thematique": [
            "droit_civil", "droit_de_la_famille", "successions_et_liberalites",
            "droit_foncier", "droit_des_societes",
        ],
        "historique": False,
        "abroge_par": None,
        "publication_abrogation": None,
        "date_abrogation": None,
    }

    registre = Registre(args.registry_root or (args.racine_conversion / "registry"))
    record = registre.inscrire(args.pdf, base, SOURCE)
    dossier, _ = registre.lire(record["document_id"])
    # Une reconstruction peut viser un dossier déjà inscrit. Le registre ne
    # remplace pas automatiquement metadata.json dans ce cas; on le remet ici
    # en phase avec le contrat courant avant de calculer le manifeste.
    ecrire_json(dossier / "configuration" / "metadata.json", base)

    lignes, audit_extraction = extraire_lignes(args.pdf)
    evenements, audit_structure = construire_evenements(lignes)
    chunks, markdown, audit_construction = construire_chunks_et_markdown(
        lignes, evenements, base
    )
    validation = _valider_donnees(chunks)
    rapport = construire_rapport(
        args.pdf,
        dossier,
        lignes,
        chunks,
        markdown,
        audit_extraction,
        audit_structure,
        audit_construction,
        validation,
        set(TYPES_BLOC_VALIDES),
    )

    (dossier / "outputs" / "document.md").write_text(
        markdown, encoding="utf-8", newline="\n"
    )
    ecrire_json(dossier / "outputs" / "chunks.json", chunks)
    ecrire_json(dossier / "outputs" / "rapport.json", rapport)
    ecrire_json(dossier / "outputs" / "rapport_validation_backend.json", validation)
    ecrire_json(dossier / "extraction" / "lignes_pdf.json", serialiser_lignes(lignes))
    ecrire_json(
        dossier / "review" / "points_a_revoir.json",
        {
            "statut": "a_revoir",
            "raison": "validation humaine demandée avant ingestion",
            "sous_divisions_non_stylees": audit_structure["sous_divisions_promues"],
            "artefacts_source": rapport["controle_qualite"][
                "artefacts_deja_presents_dans_la_source"
            ],
            "suggestions": rapport["suggestions"],
        },
    )
    ecrire_json(
        dossier / "configuration" / "pipeline.json",
        {
            "script": "traiter_code_civil_lexhaiti_registre.py",
            "extracteur_principal": f"pdfplumber {pdfplumber.__version__}",
            "verificateur": f"pypdf {pypdf.__version__}",
            "source_texte": "couche texte native du PDF",
            "analyse_geometrique_et_typographique": True,
            "pages_exclues": [1, 6],
            "zone_verticale_retenue_points": {"min_exclusif": 50, "max_exclusif": 780},
            "entete_ignore": "LEXHAÏTI / Code civil d'Haïti",
            "pied_ignore": "Source : https://lexhaiti.org/loi/code-civil et pagination",
            "corrections_silencieuses": False,
            "metadonnees_abrogation": {
                "abroge_par": None,
                "publication_abrogation": None,
                "date_abrogation": None,
            },
            "normalisations": [
                "Unicode NFC",
                "espaces de mise en page fusionnés",
                "césures typographiques ressoudées devant une minuscule",
                "double retour uniquement pour article/corps, énumérations et signatures",
            ],
        },
    )

    fichiers_manifeste = {
        "source": dossier / "source" / "original.pdf",
        "markdown": dossier / "outputs" / "document.md",
        "chunks": dossier / "outputs" / "chunks.json",
        "rapport": dossier / "outputs" / "rapport.json",
        "validation_backend": dossier / "outputs" / "rapport_validation_backend.json",
        "extraction": dossier / "extraction" / "lignes_pdf.json",
        "points_a_revoir": dossier / "review" / "points_a_revoir.json",
        "pipeline": dossier / "configuration" / "pipeline.json",
        "metadata": dossier / "configuration" / "metadata.json",
    }
    ecrire_json(
        dossier / "manifests" / "integrite.json",
        {
            "document_id": record["document_id"],
            "sha256": {nom: sha256(path) for nom, path in fichiers_manifeste.items()},
        },
    )
    registre.changer_etat(record["document_id"], "a_revoir")

    print(
        json.dumps(
            {
                "document_id": record["document_id"],
                "dossier": str(dossier),
                "chunks": len(chunks),
                "articles": len(
                    [
                        chunk
                        for chunk in chunks
                        if chunk["metadata"]["type_bloc"] == "article"
                    ]
                ),
                "clotures": len(
                    [
                        chunk
                        for chunk in chunks
                        if chunk["metadata"]["type_bloc"] == "cloture"
                    ]
                ),
                "integrite_chunks": rapport["integrite_caracteres"][
                    "chunks_identiques_a_la_source"
                ],
                "integrite_markdown": rapport["integrite_caracteres"][
                    "markdown_incluant_structures_identique_a_la_source"
                ],
                "validation_backend": validation.get("valide"),
                "pret_pour_insertion": validation.get("pret_pour_insertion"),
                "etat": "a_revoir",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
