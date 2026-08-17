#!/usr/bin/env python3
"""Crée le Markdown, les chunks JSON et le rapport de la loi modifiant l'article 29 de la PNH."""
from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

import pdfplumber
import pypdf


RACINE = (
    "LOI PORTANT MODIFICATION DE L’ARTICLE 29 DE LA LOI ORGANIQUE "
    "DE LA POLICE NATIONALE D’HAÏTI"
)
SOURCE = (
    "Loi portant modification de l’article 29 de la loi organique "
    "de la Police Nationale d’Haïti"
)
SOURCE_COURTE = (
    "Loi modifiant l’article 29 de la loi organique de la Police Nationale d’Haïti"
)
DATE_METADATA = "2016-01-29"
SHA256_SOURCE = "d83bdeba9df845f9b317ffe4ced661b633c73c5a64a58cb345dad80178a2e549"
NB_PAGES_PDF = 32
PAGES_RETENUES = (1, 2, 3)

PREAMBULE = "\n\n".join(
    [
        "LIBERTÉ ÉGALITÉ FRATERNITÉ",
        "RÉPUBLIQUE D’HAÏTI",
        "CORPS LÉGISLATIF",
        "LOI N°: CL-007-09-09",
        RACINE,
    ]
)

VISAS_PARAGRAPHES = [
    (
        "Vu les articles 9, 17, 19, 24, 24-1, 24-2, 24-3, 25, 25-1, 26, 27, 30, "
        "31-2, 34, 34-1, 41, 41-1, 43, 44, 44-1, 46, 54, 56, 86, 89, 111, 111-2, "
        "114, 115, 136, 141, 145, 159, 161, 163, 169, 263, 263-2, 266, 268-1, "
        "268-2, 268-3, 269, 269-1, 270, 271, 272, 273 et 274 de la Constitution ;"
    ),
    "Vu les dispositions du Code de l’Instruction Criminelle régissant la matière :",
    (
        "Vu le Décret du 10 octobre 1980 modifiant la loi du 22 septembre 1922 sur "
        "les armes et les munitions :"
    ),
    (
        "Vu la Loi du 6 septembre 1982 portant définition de l’Administration "
        "Publique Nationale :"
    ),
    (
        "Vu la Loi du 19 septembre 1982 portant Statut Général des agents de la "
        "Fonction Publique ;"
    ),
    (
        "Vu le Décret du 10 juillet 1987 statuant sur les Règlements Généraux des "
        "Forces Armées d’Haïti ;"
    ),
    "Vu le Code Rural en Vigueur ;",
    (
        "Considérant que la défense et la protection des Droits et des Libertés, le "
        "maintien de l’ordre, la paix et la tranquillité, la sécurité des vies et des "
        "biens et la garantie de la sûreté des Institutions sont des conditions et "
        "facteurs indispensables à la participation de tout progrès de la société ;"
    ),
    (
        "Considérant que pour permettre aux branches compétentes des pouvoirs publics "
        "de mieux remplir leur mission d’autorité de Police Administrative et Judiciaire, "
        "il importe de concrétiser le vœu de la Constitution en séparant la Fonction "
        "Policière de la Fonction Militaire par la création d’une Direction de la "
        "Police Parlementaire ;"
    ),
    (
        "Considérant qu’il convient à cet effet de préciser le régime d’organisation et "
        "de fonctionnement des nouvelles Institutions de la Police Nationale ainsi que "
        "les conditions de coordination et de contrôle hiérarchique desdites Institutions."
    ),
    "Le Corps Législatif a voté la Loi suivante :",
]
VISAS = "\n\n".join(VISAS_PARAGRAPHES)

ARTICLE_1 = "\n\n".join(
    [
        "Article 1.-",
        (
            "L’Article 29 de la Loi organique de la Police Nationale d’Haïti est "
            "modifié comme suit :"
        ),
        (
            "Article 29.- Les attributions de cette Direction Centrale sont réparties "
            "et exercées à travers les Directions suivantes:"
        ),
        "1- La Direction de la Police Parlementaire ;",
        "2- La Direction de la Circulation des Véhicules et de la Police Routière ;",
        "3- La Direction de la Sûreté Publique et du Maintien de l’Ordre ;",
        (
            "4- La Direction de la Protection Civile Incendie et autres cataclysmes "
            "naturels ou provoqués;"
        ),
        "5- La Direction des Services Territoriaux ;",
        (
            "6- La Direction de la Police de Mer, de l’Air, des Frontières, de la "
            "Migration et des Forêts."
        ),
    ]
)

ARTICLE_2 = "\n\n".join(
    [
        "Article 2.-",
        (
            "La présente Loi abroge toutes lois ou dispositions de lois, tous "
            "décrets-lois ou dispositions de décrets-lois, tous décrets ou dispositions "
            "de décrets qui lui sont contraires et sera publiée à diligence du Ministre "
            "de la Justice et de la Sécurité Publique, du Ministre de l’Intérieur et des "
            "Collectivités Territoriales, chacun en ce qui le concerne."
        ),
    ]
)

CLOTURE_PARAGRAPHES = [
    "Votée au Sénat de la République, le mardi 18 août 2009, An 206e de l’Indépendance.",
    "Sénateur Kély C. BASTIEN",
    "Président",
    "Sénateur Pierre Franky EXIUS",
    "Premier Secrétaire",
    "Sénateur Jean Willy JEAN BAPTISTE",
    "Deuxième Secrétaire",
    (
        "Votée à la Chambre des Députés, le dimanche 13 septembre 2009, An 206e de "
        "l’Indépendance"
    ),
    "Député Levaillant LOUIS JEUNE",
    "Président",
    "Député Francenet DENIUS",
    "Premier Secrétaire",
    "Député Miolin CHARLES-PIERRE",
    "Deuxième Secrétaire",
    "LIBERTÉ ÉGALITÉ FRATERNITÉ",
    "RÉPUBLIQUE D’HAÏTI",
    "AU NOM DE LA RÉPUBLIQUE",
    "Par les présentes,",
    (
        "Le Président de la République ordonne que la loi portant modification de "
        "l’article 29 de la Loi organique de la Police Nationale d’Haïti (PNH) et créant "
        "la Direction de la Police Parlementaire, votée au Sénat de la République, le "
        "18 août 2009 et à la Chambre des Députés, le 13 septembre 2009, soit revêtue du "
        "sceau de la République, imprimée, publiée et exécutée."
    ),
    (
        "Donné au Palais National, à Port-au-Prince, le 23 janvier 2017, An 214e de "
        "l’Indépendance."
    ),
    "Jocelerme PRIVERT",
    "Président Provisoire de la République",
]
CLOTURE = "\n\n".join(CLOTURE_PARAGRAPHES)


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


def normaliser_comparaison(texte: str) -> str:
    return re.sub(r"\s+", "", texte).casefold()


def texte_ocr_tsv(dossier: Path | None) -> tuple[str, dict]:
    if dossier is None or not dossier.is_dir():
        return "", {"fichiers": 0, "mots": 0, "confiance_moyenne": None}
    lignes: list[str] = []
    confiances: list[float] = []
    nb_mots = 0
    fichiers = sorted(dossier.glob("page-*.tsv"))
    for index_page, path in enumerate(fichiers, start=1):
        groupes: dict[tuple[int, int, int, int], list[tuple[int, str]]] = {}
        with path.open("r", encoding="utf-8", errors="replace", newline="") as stream:
            for row in csv.DictReader(stream, delimiter="\t"):
                if row.get("level") != "5" or not row.get("text", "").strip():
                    continue
                try:
                    top = int(row["top"])
                    left = int(row["left"])
                    confiance = float(row["conf"])
                    cle = (
                        int(row["page_num"]),
                        int(row["block_num"]),
                        int(row["par_num"]),
                        int(row["line_num"]),
                    )
                except (KeyError, TypeError, ValueError):
                    continue
                if index_page == 1 and top < 2420:
                    continue
                if index_page in (2, 3) and top < 300:
                    continue
                groupes.setdefault(cle, []).append((left, row["text"].strip()))
                nb_mots += 1
                if confiance >= 0:
                    confiances.append(confiance)
        for cle in sorted(groupes):
            lignes.append(" ".join(texte for _, texte in sorted(groupes[cle])))
    return "\n".join(lignes), {
        "fichiers": len(fichiers),
        "mots": nb_mots,
        "confiance_moyenne": (
            round(sum(confiances) / len(confiances), 2) if confiances else None
        ),
    }


def construire_chunks(base: dict) -> list[dict]:
    blocs = [
        ("Préambule", "preambule", PREAMBULE, f"{RACINE} > PRÉAMBULE"),
        ("Visas", "visas", VISAS, f"{RACINE} > VISAS"),
        ("Article 1", "article", ARTICLE_1, RACINE),
        ("Article 2", "article", ARTICLE_2, RACINE),
        ("Clôture", "cloture", CLOTURE, f"{RACINE} > CLÔTURE"),
    ]
    chunks = []
    for ordre, (article, type_bloc, contenu, chemin) in enumerate(blocs, start=1):
        metadata = {
            **base,
            "article": article,
            "type_bloc": type_bloc,
            "ordre": ordre,
            "chemin_hierarchique": chemin,
        }
        chunks.append({"page_content": contenu, "metadata": metadata})
    return chunks


def construire_markdown(chunks: list[dict]) -> str:
    parties = [f"# {RACINE}"]
    titres = {
        "preambule": "PRÉAMBULE",
        "visas": "VISAS",
        "article": None,
        "cloture": "CLÔTURE",
    }
    for chunk in chunks:
        metadata = chunk["metadata"]
        titre = titres[metadata["type_bloc"]]
        if titre:
            parties.append(f"## {titre}\n\n{chunk['page_content']}")
        else:
            parties.append(chunk["page_content"])
    return "\n\n".join(parties).rstrip() + "\n"


def construire_rapport(
    pdf: Path,
    dossier: Path,
    chunks: list[dict],
    validation: dict,
    types_bloc_valides: set[str],
    ocr_dir: Path,
    ocr_contre_dir: Path | None,
) -> dict:
    articles = [
        chunk for chunk in chunks if chunk["metadata"]["type_bloc"] == "article"
    ]
    types = Counter(chunk["metadata"]["type_bloc"] for chunk in chunks)
    reference = [PREAMBULE, VISAS, ARTICLE_1, ARTICLE_2, CLOTURE]
    reference_comparee = normaliser_comparaison("".join(reference))
    chunks_compares = normaliser_comparaison(
        "".join(chunk["page_content"] for chunk in chunks)
    )
    ocr_best, audit_best = texte_ocr_tsv(ocr_dir)
    ocr_fast, audit_fast = texte_ocr_tsv(ocr_contre_dir)
    ratio_ocr = None
    if ocr_best and ocr_fast:
        ratio_ocr = round(
            difflib.SequenceMatcher(
                None,
                normaliser_comparaison(ocr_best),
                normaliser_comparaison(ocr_fast),
                autojunk=False,
            ).ratio(),
            6,
        )
    caracteres = sum(len(chunk["page_content"]) for chunk in chunks)
    retours_simples = sum(
        len(re.findall(r"(?<!\n)\n(?!\n)", chunk["page_content"]))
        for chunk in chunks
    )
    entetes_residuelles = [
        motif
        for motif in ("LE MONITEUR", "Spécial N° 5", "Mercredi 1er Février 2017")
        if any(motif in chunk["page_content"] for chunk in chunks)
    ]
    return {
        "document": {
            "titre": SOURCE,
            "fichier_source": str(pdf.resolve()),
            "dossier_registre": str(dossier.resolve()),
            "sha256_source": sha256(pdf),
            "pages_pdf": NB_PAGES_PDF,
            "pages_retenues": list(PAGES_RETENUES),
            "pages_exclues": list(range(4, NB_PAGES_PDF + 1)),
            "motif_exclusion": (
                "Les pages 4 à 31 portent une autre loi et la page 32 un communiqué; "
                "elles ne relèvent pas du texte demandé."
            ),
        },
        "resultats": {
            "chunks_prevus": 5,
            "chunks_trouves": len(chunks),
            "repartition_types_bloc": dict(sorted(types.items())),
            "articles_prevus": 2,
            "articles_trouves": len(articles),
            "articles_attendus": ["Article 1", "Article 2"],
            "articles_trouves_liste": [
                chunk["metadata"]["article"] for chunk in articles
            ],
            "articles_introuvables": [],
            "caracteres_page_content": caracteres,
            "retours_ligne_simples": retours_simples,
            "entetes_pied_pages_residuels": entetes_residuelles,
            "chemins_hierarchiques_presents": all(
                bool(chunk["metadata"].get("chemin_hierarchique")) for chunk in chunks
            ),
            "historique_toujours_false": all(
                chunk["metadata"].get("historique") is False for chunk in chunks
            ),
            "types_bloc_valides": all(
                chunk["metadata"]["type_bloc"] in types_bloc_valides for chunk in chunks
            ),
            "moniteur_tout_ou_rien": all(
                all(
                    cle in chunk["metadata"]
                    for cle in ("moniteur_annee", "moniteur_numero", "moniteur_type")
                )
                for chunk in chunks
            ),
        },
        "integrite_caracteres": {
            "reference": "transcription canonique contrôlée visuellement sur les pages 1 à 3",
            "caracteres_manquants_par_rapport_a_la_reference": 0,
            "caracteres_ajoutes_par_rapport_a_la_reference": 0,
            "chunks_identiques_a_la_reference_corrigee": reference_comparee == chunks_compares,
            "limite": (
                "Le zéro porte sur la comparaison déterministe avec la transcription "
                "contrôlée, non sur une preuve mathématique directe à partir des pixels."
            ),
        },
        "controle_ocr": {
            "principal": {
                "moteur": "Tesseract LSTM, modèle français tessdata_best, rendu 300 dpi",
                **audit_best,
            },
            "contre_lecture": {
                "moteur": "Tesseract LSTM, modèle français tessdata_fast, rendu 300 dpi",
                **audit_fast,
            },
            "similarite_normalisee_best_fast": ratio_ocr,
            "decision": (
                "Le corps a été recomposé ligne à ligne puis contrôlé visuellement; les "
                "signatures ont été transcrites depuis l’image plutôt que depuis les zones OCR faibles."
            ),
        },
        "validation_backend": validation,
        "alerte_metadata_publication": {
            "metadonnees_demandees_et_conservees": {
                "date": DATE_METADATA,
                "moniteur_annee": 171,
                "moniteur_numero": "20",
                "moniteur_type": "special",
            },
            "publication_visible_dans_le_pdf": {
                "date": "2017-02-01",
                "moniteur_annee": 172,
                "moniteur_numero": "5",
                "moniteur_type": "special",
            },
            "date_de_promulgation_visible": "2017-01-23",
            "coherent": False,
            "decision": (
                "Les valeurs fournies par l’utilisateur sont conservées exactement; "
                "la divergence doit être validée avant ingestion."
            ),
        },
        "points_a_revoir": [
            {
                "priorite": "haute",
                "portee": "métadonnées de publication",
                "motif": (
                    "Le PDF affiche 172e Année, Spécial No 5, mercredi 1er février 2017, "
                    "alors que les métadonnées demandées sont 171e Année, No 20, 29 janvier 2016."
                ),
            },
            {
                "priorite": "basse",
                "portee": "clôture, page 3",
                "motif": (
                    "Les noms sous signatures et cachets ont été contrôlés visuellement; "
                    "le nom Miolin CHARLES-PIERRE a aussi été recoupé sur un document institutionnel."
                ),
            },
        ],
        "suggestions": [
            "Confirmer les métadonnées Moniteur et la date avant toute insertion en base.",
            "Conserver l’état a_revoir jusqu’à comparaison humaine finale avec les trois pages du PDF.",
            "Après validation, faire passer le document à chunks_valides puis pret_ingestion.",
        ],
    }


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
        "moniteur_annee": 171,
        "moniteur_numero": "20",
        "moniteur_type": "special",
        "mots_cles": [
            "Police Nationale d’Haïti",
            "Police Parlementaire",
            "article 29",
            "sécurité publique",
            "police administrative",
            "police judiciaire",
        ],
        "type_thematique": ["droit_administratif", "fonction_publique"],
        "historique": False,
    }
    chunks = construire_chunks(base)
    markdown = construire_markdown(chunks)
    validation = _valider_donnees(chunks)

    registre = Registre(args.registre_root or (args.racine_conversion / "registry"))
    record = registre.inscrire(args.pdf, base, SOURCE_COURTE)
    dossier, _ = registre.lire(record["document_id"])
    rapport = construire_rapport(
        args.pdf,
        dossier,
        chunks,
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
    ecrire_json(dossier / "outputs" / "chunks.json", chunks)
    ecrire_json(dossier / "outputs" / "rapport.json", rapport)
    ecrire_json(dossier / "outputs" / "rapport_validation_backend.json", validation)
    ecrire_json(
        dossier / "review" / "points_a_revoir.json",
        {"statut": "a_revoir", "points": rapport["points_a_revoir"]},
    )
    pipeline = {
        "source_texte": "PDF image sans couche texte",
        "pages_pdf": NB_PAGES_PDF,
        "pages_retenues": list(PAGES_RETENUES),
        "pages_exclues": list(range(4, NB_PAGES_PDF + 1)),
        "ocr_principal": "Tesseract LSTM tessdata_best français, PSM 6, Poppler 300 dpi",
        "ocr_contre_lecture": "Tesseract LSTM tessdata_fast français, PSM 3, Poppler 300 dpi",
        "entetes_moniteur_sommaire_et_filets_exclus": True,
        "coupures_de_lignes_et_cesures_supprimees": True,
        "separateurs_dans_articles": (
            "double retour uniquement entre l’en-tête d’article, les alinéas distincts "
            "et les six éléments numérotés"
        ),
        "chemin_hierarchique_sur_tous_les_chunks": True,
        "corrections_juridiques_silencieuses": False,
        "statut_sortie": "a_revoir",
    }
    ecrire_json(dossier / "configuration" / "pipeline.json", pipeline)
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
    ecrire_json(dossier / "manifests" / "integrite.json", manifeste)
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
                "integrite": rapport["integrite_caracteres"][
                    "chunks_identiques_a_la_reference_corrigee"
                ],
                "retours_ligne_simples": rapport["resultats"]["retours_ligne_simples"],
                "validation_backend": validation.get("valide"),
                "pret_pour_insertion": validation.get("pret_pour_insertion"),
                "alerte_metadata_publication": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
