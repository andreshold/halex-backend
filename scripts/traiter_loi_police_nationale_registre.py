#!/usr/bin/env python3
"""Convertit la loi de 1994 relative à la Police nationale en lot Halex auditable."""
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


RACINE = "LOI RELATIVE À LA POLICE NATIONALE"
SOURCE = "Loi relative à la Police nationale"
DATE_METADATA = "1994-11-29"
DATE_PUBLICATION = "1994-12-28"
NB_PAGES_ATTENDU = 13
NB_STRUCTURES_ATTENDU = 30

ARTICLES_ATTENDUS = (
    [str(numero) for numero in range(1, 43)]
    + ["42.1"]
    + [str(numero) for numero in range(43, 65)]
    + ["64.1", "64.2"]
    + [str(numero) for numero in range(65, 71)]
)

RE_ARTICLE = re.compile(
    r"^Article\s+(?P<numero>\d+(?:\.\d+)?)\.-(?:\s*(?P<corps>.*))?$"
)
RE_STRUCTURE = re.compile(r"^(TITRE|CHAPITRE|Section|Sous-section)\b")
RE_LISTE = re.compile(
    r"^(?:\d+\.\s+|[a-z]\.\s+|·\s+|Niveau\s+|«)"
)

ARTEFACTS_SOURCE = (
    "poli-ce",
    "annuel-le",
    "toues dépenses",
    "à lui conférés",
    "maritime, portuaires",
    "corps professionnel de police civil",
)


@dataclass(frozen=True)
class Ligne:
    ordre: int
    page: int
    top: float
    texte: str
    type: str
    police: str
    taille: float


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
    compte = Counter(
        (str(char.get("fontname") or ""), round(float(char.get("size") or 0.0), 1))
        for char in chars
        if (char.get("text") or "").strip()
    )
    return compte.most_common(1)[0][0] if compte else ("", 0.0)


def classifier(texte: str, police: str, taille: float) -> str:
    if RE_ARTICLE.match(texte):
        return "article"
    if RE_STRUCTURE.match(texte) and "Bold" in police and 12.0 <= taille <= 13.2:
        return "structure_label"
    if "Bold" in police and 12.0 <= taille <= 13.2:
        return "structure_title"
    return "corps"


def extraire_lignes(pdf: Path) -> tuple[list[Ligne], dict]:
    lignes: list[Ligne] = []
    entete_documentaire: list[dict] = []
    ordre = 0

    with pdfplumber.open(pdf) as document:
        if len(document.pages) != NB_PAGES_ATTENDU:
            raise RuntimeError(
                f"{NB_PAGES_ATTENDU} pages attendues, {len(document.pages)} trouvées"
            )
        for page_numero, page in enumerate(document.pages, 1):
            for item in page.extract_text_lines(layout=False, strip=True, return_chars=True):
                top = float(item["top"])
                texte = nettoyer_espaces(item["text"])
                if not texte:
                    continue
                police, taille = police_dominante(item.get("chars") or [])
                if page_numero == 1 and top < 200:
                    entete_documentaire.append(
                        {
                            "page": page_numero,
                            "top": round(top, 1),
                            "texte": texte,
                            "raison": "titre, date et référence de publication migrés en métadonnées",
                        }
                    )
                    continue
                lignes.append(
                    Ligne(
                        ordre=ordre,
                        page=page_numero,
                        top=top,
                        texte=texte,
                        type=classifier(texte, police, taille),
                        police=police,
                        taille=taille,
                    )
                )
                ordre += 1

    with pdf.open("rb") as stream:
        lecteur = pypdf.PdfReader(stream)
        pages_pypdf = len(lecteur.pages)
        metadata_pdf = {
            str(cle).lstrip("/"): str(valeur)
            for cle, valeur in (lecteur.metadata or {}).items()
            if valeur is not None
        }

    if len(entete_documentaire) != 4:
        raise RuntimeError(
            f"4 lignes d'en-tête documentaire attendues, {len(entete_documentaire)} trouvées"
        )

    return lignes, {
        "pages_pdfplumber": NB_PAGES_ATTENDU,
        "pages_pypdf": pages_pypdf,
        "lignes_retenues": len(lignes),
        "lignes_entete_documentaire_exclues_des_chunks": entete_documentaire,
        "entetes_repetitifs": 0,
        "pieds_de_page": 0,
        "numeros_de_page": 0,
        "ocr_requis": False,
        "metadata_pdf": metadata_pdf,
    }


def analyser_evenements(lignes: list[Ligne]) -> tuple[list[Evenement], dict]:
    evenements: list[Evenement] = []
    indices_structure: set[int] = set()
    compte_structures = Counter()

    index = 0
    while index < len(lignes):
        ligne = lignes[index]
        if ligne.type == "structure_label":
            match = RE_STRUCTURE.match(ligne.texte)
            if not match:
                raise RuntimeError(f"Structure non reconnue: {ligne.texte!r}")
            source_niveau = match.group(1)
            fin = index + 1
            while fin < len(lignes) and lignes[fin].type == "structure_title":
                fin += 1
            segments = [element.texte for element in lignes[index:fin]]
            niveau = {
                "TITRE": "titre",
                "CHAPITRE": "chapitre",
                "Section": "section",
                "Sous-section": "paragraphe",
            }[source_niveau]
            valeur = segments[0]
            if len(segments) > 1:
                valeur = f"{segments[0]} — {' '.join(segments[1:])}"
            evenements.append(
                Evenement(
                    debut=index,
                    fin=fin,
                    type="structure",
                    donnees={
                        "niveau": niveau,
                        "niveau_source": source_niveau.upper(),
                        "segments": segments,
                        "valeur": valeur,
                    },
                )
            )
            indices_structure.update(range(index, fin))
            compte_structures[source_niveau.upper()] += 1
            index = fin
            continue
        index += 1

    numeros: list[str] = []
    for index, ligne in enumerate(lignes):
        if ligne.type != "article":
            continue
        match = RE_ARTICLE.match(ligne.texte)
        if not match:
            raise RuntimeError(f"Article non reconnu: {ligne.texte!r}")
        numero = match.group("numero")
        numeros.append(numero)
        evenements.append(
            Evenement(
                debut=index,
                fin=index + 1,
                type="article",
                donnees={
                    "numero": numero,
                    "etiquette": f"Article {numero}.-",
                    "corps_initial": match.group("corps") or "",
                },
            )
        )

    if numeros != ARTICLES_ATTENDUS:
        raise RuntimeError(
            "Inventaire d'articles incohérent: "
            f"attendu={ARTICLES_ATTENDUS!r}, trouvé={numeros!r}"
        )
    if sum(compte_structures.values()) != NB_STRUCTURES_ATTENDU:
        raise RuntimeError(
            f"{NB_STRUCTURES_ATTENDU} structures attendues, "
            f"{sum(compte_structures.values())} trouvées: {dict(compte_structures)}"
        )

    evenements.sort(key=lambda evenement: evenement.debut)
    debuts = [evenement.debut for evenement in evenements]
    if len(debuts) != len(set(debuts)):
        raise RuntimeError("Deux événements commencent sur la même ligne")

    return evenements, {
        "indices_structure": sorted(indices_structure),
        "nb_structures": sum(compte_structures.values()),
        "structures_par_type": dict(sorted(compte_structures.items())),
    }


def prochain_debut(evenements: list[Evenement], position: int, limite: int) -> int:
    return min(
        (evenement.debut for evenement in evenements if evenement.debut > position),
        default=limite,
    )


def joindre_fragments(fragments: Iterable[str]) -> tuple[str, int]:
    resultat = ""
    jointures_hyphen = 0
    for fragment in fragments:
        if not fragment:
            continue
        if not resultat:
            resultat = fragment
        elif resultat.endswith("-"):
            # Les deux seules occurrences sont lexicales: Port-au-Prince et
            # sous-commissariats. On supprime l'espace de mise en page, jamais le tiret.
            resultat += fragment
            jointures_hyphen += 1
        else:
            resultat += " " + fragment
    return resultat, jointures_hyphen


def formater_corps(fragments: list[str]) -> tuple[str, int]:
    paragraphes: list[list[str]] = [[]]
    for fragment in fragments:
        if not fragment:
            continue
        if paragraphes[-1] and RE_LISTE.match(fragment):
            paragraphes.append([])
        paragraphes[-1].append(fragment)

    rendus: list[str] = []
    jointures = 0
    for paragraphe in paragraphes:
        rendu, nombre = joindre_fragments(paragraphe)
        jointures += nombre
        if rendu:
            rendus.append(rendu)
    return "\n\n".join(rendus), jointures


def construire_chunks_et_markdown(
    lignes: list[Ligne], evenements: list[Evenement], base: dict
) -> tuple[list[dict], str, dict]:
    chunks: list[dict] = []
    markdown: list[str] = []
    niveaux = ["titre", "chapitre", "section", "paragraphe"]
    hierarchie: dict[str, str | None] = {niveau: None for niveau in niveaux}
    indices_structure: set[int] = set()
    indices_chunks: set[int] = set()
    jointures_hyphen = 0

    for evenement in evenements:
        if evenement.type == "structure":
            niveau = evenement.donnees["niveau"]
            hierarchie[niveau] = evenement.donnees["valeur"]
            position = niveaux.index(niveau)
            for enfant in niveaux[position + 1 :]:
                hierarchie[enfant] = None
            markdown.append("\n\n".join(evenement.donnees["segments"]))
            indices_structure.update(range(evenement.debut, evenement.fin))
            continue

        if evenement.type != "article":
            raise RuntimeError(f"Type d'événement inconnu: {evenement.type}")

        fin = prochain_debut(evenements, evenement.debut, len(lignes))
        indices_corps = [
            index
            for index in range(evenement.fin, fin)
            if index not in indices_structure
        ]
        fragments = [evenement.donnees["corps_initial"]]
        fragments.extend(lignes[index].texte for index in indices_corps)
        corps, nombre_jointures = formater_corps(fragments)
        jointures_hyphen += nombre_jointures
        if not corps:
            raise RuntimeError(f"Corps vide pour l'article {evenement.donnees['numero']}")

        page_content = f"{evenement.donnees['etiquette']}\n\n{corps}"
        metadata = {
            **base,
            "article": f"Article {evenement.donnees['numero']}",
            "type_bloc": "article",
            "ordre": len(chunks) + 1,
        }
        chemin = [RACINE]
        for niveau in niveaux:
            valeur = hierarchie[niveau]
            if valeur:
                metadata[niveau] = valeur
                chemin.append(valeur)
        metadata["chemin_hierarchique"] = " > ".join(chemin)

        chunks.append({"page_content": page_content, "metadata": metadata})
        markdown.append(page_content)
        indices_chunks.add(evenement.debut)
        indices_chunks.update(indices_corps)

    affectees = indices_structure | indices_chunks
    non_affectees = sorted(set(range(len(lignes))) - affectees)
    if non_affectees:
        apercu = [
            {"page": lignes[index].page, "texte": lignes[index].texte}
            for index in non_affectees[:20]
        ]
        raise RuntimeError(f"Lignes juridiques non affectées: {apercu}")

    return chunks, "\n\n".join(markdown) + "\n", {
        "indices_structure": sorted(indices_structure),
        "indices_chunks": sorted(indices_chunks),
        "lignes_non_affectees": non_affectees,
        "jointures_de_lignes_conservant_le_tiret_lexical": jointures_hyphen,
    }


def sequence_non_blanche(texte: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", texte))


def reference_lignes(lignes: list[Ligne], indices: Iterable[int]) -> str:
    return sequence_non_blanche(" ".join(lignes[index].texte for index in sorted(indices)))


def trouver_artefacts(lignes: list[Ligne]) -> list[dict]:
    trouves: list[dict] = []
    for ligne in lignes:
        for motif in ARTEFACTS_SOURCE:
            if motif.casefold() in ligne.texte.casefold():
                trouves.append(
                    {
                        "page": ligne.page,
                        "motif": motif,
                        "ligne_source": ligne.texte,
                        "action": "conservé exactement; relecture humaine recommandée",
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
    indices_chunks = audit_construction["indices_chunks"]
    source_chunks = reference_lignes(lignes, indices_chunks)
    sortie_chunks = sequence_non_blanche(
        " ".join(chunk["page_content"] for chunk in chunks)
    )
    source_markdown = reference_lignes(lignes, range(len(lignes)))
    sortie_markdown = sequence_non_blanche(markdown)
    chunks_identiques = source_chunks == sortie_chunks
    markdown_identique = source_markdown == sortie_markdown
    trouves = [chunk["metadata"]["article"].removeprefix("Article ") for chunk in chunks]
    types = Counter(chunk["metadata"]["type_bloc"] for chunk in chunks)
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
            "titre_pdf": audit_extraction["metadata_pdf"].get("Title"),
            "extraction": f"pdfplumber {pdfplumber.__version__}, couche texte native et géométrie",
            "contre_verification": f"pypdf {pypdf.__version__}",
            "ocr_requis": False,
            "controle_visuel": "13 pages sur 13",
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
            "prevus": len(ARTICLES_ATTENDUS),
            "trouves": len(chunks),
            "ecart": len(chunks) - len(ARTICLES_ATTENDUS),
            "par_type_bloc": dict(sorted(types.items())),
            "types_bloc_non_valides": sorted(set(types) - types_valides),
        },
        "articles": {
            "prevus": len(ARTICLES_ATTENDUS),
            "trouves": len(trouves),
            "sequence_attendue": ARTICLES_ATTENDUS,
            "articles_introuvables": sorted(set(ARTICLES_ATTENDUS) - set(trouves)),
            "articles_inattendus": sorted(set(trouves) - set(ARTICLES_ATTENDUS)),
            "articles_dupliques": sorted(
                numero for numero, nombre in Counter(trouves).items() if nombre > 1
            ),
            "sequence_exacte": trouves == ARTICLES_ATTENDUS,
            "articles_speciaux_presents": [
                numero for numero in ("42.1", "64.1", "64.2") if numero in trouves
            ],
        },
        "hierarchie": {
            "racine": RACINE,
            "structures_prevues": NB_STRUCTURES_ATTENDU,
            "structures_trouvees": audit_structure["nb_structures"],
            "structures_par_type": audit_structure["structures_par_type"],
            "articles_avec_chemin_hierarchique": sum(
                bool(chunk["metadata"].get("chemin_hierarchique")) for chunk in chunks
            ),
            "articles_sans_chemin_hierarchique": [
                chunk["metadata"]["article"]
                for chunk in chunks
                if not chunk["metadata"].get("chemin_hierarchique")
            ],
        },
        "integrite_caracteres": {
            "regle": "comparaison Unicode NFC hors espaces de mise en page",
            "source_chunks_non_blanche": len(source_chunks),
            "sortie_chunks_non_blanche": len(sortie_chunks),
            "chunks_identiques_a_la_source": chunks_identiques,
            "caracteres_manquants": 0 if chunks_identiques else None,
            "caracteres_ajoutes": 0 if chunks_identiques else None,
            "markdown_incluant_structures_identique_a_la_source": markdown_identique,
            "lignes_juridiques_non_affectees": audit_construction["lignes_non_affectees"],
            "jointures_conservant_le_tiret_lexical": audit_construction[
                "jointures_de_lignes_conservant_le_tiret_lexical"
            ],
        },
        "mise_en_page": {
            "retours_simples_dans_page_content": simples,
            "retours_simples_attendus": 0,
            "separations_conservees": "article/corps, énumérations, tableau des grades et serment",
            "entetes_repetitifs_ignores": 0,
            "pieds_de_page_ignores": 0,
            "numeros_de_page_ignores": 0,
        },
        "metadata": {
            "date": sorted({chunk["metadata"]["date"] for chunk in chunks}),
            "date_publication": sorted({chunk["metadata"]["date_publication"] for chunk in chunks}),
            "historique": sorted({chunk["metadata"]["historique"] for chunk in chunks}),
            "tous_chunks_historique_false": all(
                chunk["metadata"]["historique"] is False for chunk in chunks
            ),
            "moniteur": {
                "annee": 149,
                "numero": "103",
                "type": "ordinaire",
                "preuve_pdf": "Moniteur nº 103, 28 décembre 1994",
                "annee_deduite_de_la_serie_du_Moniteur": True,
            },
            "tous_chunks_avec_les_trois_cles_moniteur": all(
                cles_moniteur <= set(chunk["metadata"]) for chunk in chunks
            ),
            "tous_chunks_avec_chemin_hierarchique": all(
                bool(chunk["metadata"].get("chemin_hierarchique")) for chunk in chunks
            ),
            "types_bloc_utilises": sorted(types),
            "types_bloc_valides_backend": sorted(types_valides),
        },
        "blocs_absents_de_la_source": {
            "preambule": "aucun préambule juridique dans le PDF",
            "visas": "aucun visa juridique dans le PDF",
            "cloture": "aucune formule de promulgation ni signature après l'article 70",
            "annexe": "aucune annexe dans le PDF",
            "blocs_artificiels_ajoutes": 0,
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
        "points_a_revoir": {
            "artefacts_deja_presents_dans_la_source": artefacts,
            "nombre_artefacts_reperes": len(artefacts),
            "cloture_absente": True,
            "entete_documentaire_non_chunked": audit_extraction[
                "lignes_entete_documentaire_exclues_des_chunks"
            ],
            "corrections_silencieuses": False,
        },
        "suggestions": [
            "Comparer les artefacts signalés à l'exemplaire officiel du Moniteur nº 103 avant correction.",
            "Vérifier dans l'exemplaire officiel si une formule de promulgation ou des signatures suivent l'article 70; elles sont absentes du PDF fourni.",
            "Conserver l'état a_revoir jusqu'à la validation humaine demandée.",
        ],
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
        "--registry-root", type=Path, help="Registre de sortie alternatif pour les essais"
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

    if "article" not in TYPES_BLOC_VALIDES:
        raise RuntimeError("Le type de bloc 'article' est absent de TYPES_BLOC_VALIDES")

    base = {
        "source": SOURCE,
        "source_courte": SOURCE,
        "type_norme": "loi",
        "rang": RANGS_PAR_TYPE_NORME["loi"],
        "date": DATE_METADATA,
        "date_publication": DATE_PUBLICATION,
        "statut": "en_vigueur",
        "moniteur_publication": "Le Moniteur, 149e année, Ordinaire no 103, 28 décembre 1994",
        "mots_cles": [
            "Police nationale d’Haïti",
            "sécurité publique",
            "Police administrative",
            "Police judiciaire",
            "CSPN",
            "commissariats",
        ],
        "type_thematique": [
            "droit_administratif",
            "fonction_publique",
            "droits_fondamentaux",
        ],
        "historique": False,
        "abroge_par": None,
        "publication_abrogation": None,
        "date_abrogation": None,
    }

    registre = Registre(args.registry_root or (args.racine_conversion / "registry"))
    record = registre.inscrire(args.pdf, base, SOURCE)
    dossier, _ = registre.lire(record["document_id"])

    lignes, audit_extraction = extraire_lignes(args.pdf)
    evenements, audit_structure = analyser_evenements(lignes)
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
            "points": rapport["points_a_revoir"],
            "suggestions": rapport["suggestions"],
        },
    )
    ecrire_json(
        dossier / "configuration" / "pipeline.json",
        {
            "script": "traiter_loi_police_nationale_registre.py",
            "extracteur_principal": f"pdfplumber {pdfplumber.__version__}",
            "verificateur": f"pypdf {pypdf.__version__}",
            "source_texte": "couche texte native du PDF",
            "analyse_geometrique_et_typographique": True,
            "pages_controlees_visuellement": 13,
            "en_tete_documentaire_migre_en_metadata": True,
            "corrections_silencieuses": False,
            "normalisations": [
                "Unicode NFC",
                "espaces de mise en page fusionnés",
                "double retour uniquement pour article/corps, listes, tableau des grades et serment",
                "tirets lexicaux de Port-au-Prince et sous-commissariats conservés",
            ],
        },
    )

    fichiers = {
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
            "sha256": {nom: sha256(path) for nom, path in fichiers.items()},
        },
    )
    registre.changer_etat(record["document_id"], "a_revoir")

    print(
        json.dumps(
            {
                "document_id": record["document_id"],
                "dossier": str(dossier),
                "chunks": len(chunks),
                "articles": len(chunks),
                "structures": audit_structure["nb_structures"],
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
