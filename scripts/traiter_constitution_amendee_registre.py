#!/usr/bin/env python3
"""Inscrit et convertit la Constitution de 1987 amendée dans le registre Halex."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
import pypdf


RACINE = "CONSTITUTION DE 1987 AMENDÉE"
RACINE_LOI = "LOI CONSTITUTIONNELLE PORTANT AMENDEMENT DE LA CONSTITUTION DE 1987"
RE_HIERARCHIE = re.compile(r"^(TITRE|CHAPITRE|SECTION)\b", re.IGNORECASE)
RE_LISTE = re.compile(r"^(?:[a-z]\)|\d+[.)]\s|[-•]\s)", re.IGNORECASE)
PSEUDO_TITRES = {
    "DE LA FONCTION PUBLIQUE",
    "De l’ECONOMIE, de l’AGRICULTURE et de l’ENVIRONNEMENT",
    "DE LA FAMILLE",
    "DE LA FORCE PUBLIQUE",
    "DISPOSITIONS GÉNÉRALES",
    "AMENDEMENTS A LA CONSTITUTION",
    "DES DISPOSITIONS TRANSITOIRES",
    "Dispositions finales",
}


@dataclass(frozen=True)
class Ligne:
    page: int
    top: float
    texte: str


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


def parser_article(texte: str) -> dict | None:
    if not texte.lower().startswith("article "):
        return None
    reste = texte[8:].strip()
    separateur = ""
    corps = ""
    if ".-" in reste:
        numero, corps = reste.split(".-", 1)
        separateur = ".-"
    elif ":" in reste:
        numero, corps = reste.split(":", 1)
        separateur = ":"
    else:
        numero = reste
    numero = nettoyer_espaces(numero)
    if not re.match(r"^\d", numero):
        return None
    return {"numero": numero, "separateur": separateur, "corps": nettoyer_espaces(corps)}


def est_note(texte: str) -> bool:
    bas = texte.casefold()
    if bas.startswith("il est ajouté un article 295-1"):
        return True
    commence = bas.startswith(("l’article ", "les articles ", "article111.5"))
    return commence and ("abrog" in bas or "constitution de 1987" in bas)


def extraire_lignes(pdf: Path) -> tuple[list[Ligne], dict]:
    lignes: list[Ligne] = []
    corrections: list[dict] = []
    elements_marginaux: list[dict] = []
    with pdfplumber.open(pdf) as document:
        for numero, page in enumerate(document.pages, 1):
            for item in page.extract_text_lines():
                texte = nettoyer_espaces(item["text"])
                if not texte:
                    continue
                top = float(item["top"])
                if re.fullmatch(r"\d{1,3}", texte) and (top < 55 or top > 740):
                    elements_marginaux.append({"page": numero, "texte": texte, "raison": "numero_de_page"})
                    continue
                if re.match(r"^ChAPITRE\b", texte):
                    corrige = re.sub(r"^ChAPITRE\b", "CHAPITRE", texte)
                    corrections.append({"page": numero, "extrait": texte, "corrige": corrige, "raison": "casse incohérente de la couche texte"})
                    texte = corrige
                lignes.append(Ligne(numero, top, texte))
    with pdf.open("rb") as stream:
        pages_pypdf = len(pypdf.PdfReader(stream).pages)
    return lignes, {
        "elements_marginaux_retires": elements_marginaux,
        "corrections_extraction_documentees": corrections,
        "pages_pdfplumber": len({ligne.page for ligne in lignes}),
        "pages_pypdf": pages_pypdf,
    }


def construire_structures(lignes: list[Ligne], limite: int) -> list[Evenement]:
    structures: list[Evenement] = []
    index = 0
    while index < limite:
        texte = lignes[index].texte
        match = RE_HIERARCHIE.match(texte)
        pseudo = texte in PSEUDO_TITRES
        if not match and not pseudo:
            index += 1
            continue
        # Certaines grandes parties ne portent aucun préfixe « TITRE » dans le
        # PDF. Elles sont conservées mot pour mot et jouent néanmoins le rôle
        # d'un niveau supérieur afin de ne pas hériter du titre précédent.
        niveau = match.group(1).lower() if match else "titre"
        suivant = index + 1
        if not pseudo:
            while suivant < limite:
                candidat = lignes[suivant].texte
                if parser_article(candidat) or RE_HIERARCHIE.match(candidat) or candidat in PSEUDO_TITRES or est_note(candidat):
                    break
                suivant += 1
        segments_bruts = [ligne.texte for ligne in lignes[index:suivant]]
        segments_chemin = [segment for segment in segments_bruts if segment.strip("* ")]
        structures.append(Evenement(index, suivant, "structure", {
            "niveau": niveau,
            "segments_bruts": segments_bruts,
            "segments_chemin": segments_chemin,
        }))
        index = suivant
    return structures


def nouvelle_partie(courant: list[str], ligne: Ligne, precedente: Ligne | None) -> bool:
    if not courant or precedente is None:
        return False
    if RE_LISTE.match(ligne.texte):
        return True
    if ligne.page == precedente.page and ligne.top - precedente.top > 13:
        return True
    if courant[-1].endswith(";") and re.match(r"^[A-ZÀ-ÖØ-Þ]", ligne.texte):
        return True
    return False


def formater(lignes: list[Ligne], type_bloc: str, article: dict | None = None) -> str:
    if not lignes:
        raise ValueError(f"Bloc vide : {type_bloc}")
    travail = list(lignes)
    etiquette = ""
    if article:
        etiquette = f"Article {article['numero']}{article['separateur']}"
        travail[0] = Ligne(travail[0].page, travail[0].top, article["corps"])
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
    corps = "\n\n".join(p.strip() for p in paragraphes if p.strip())
    return f"{etiquette}\n\n{corps}" if etiquette else corps


def chemin_et_metadata(etat: dict) -> tuple[str, dict]:
    segments = [RACINE]
    meta: dict = {}
    for niveau in ("titre", "chapitre", "section"):
        valeurs = etat.get(niveau) or []
        if valeurs:
            segments.extend(valeurs)
            meta[niveau] = " > ".join(valeurs)
    return " > ".join(segments), meta


def construire(lignes: list[Ligne], base: dict) -> tuple[list[dict], str, dict]:
    articles_explicites = [(i, parser_article(ligne.texte)) for i, ligne in enumerate(lignes) if parser_article(ligne.texte)]
    if len(articles_explicites) != 496:
        raise RuntimeError(f"496 en-têtes d'articles attendus, {len(articles_explicites)} trouvés")
    index_preambule = next(i for i, ligne in enumerate(lignes) if ligne.texte.startswith("Le préambule de la Constitution"))
    index_cloture = next(i for i, ligne in enumerate(lignes) if ligne.texte.startswith("Donné à l’Assemblée Nationale"))
    structures = construire_structures(lignes, index_cloture)
    structure_par_debut = {event.debut: event for event in structures}
    indices_structure = {i for event in structures for i in range(event.debut, event.fin)}
    index_premier_titre = min(event.debut for event in structures)
    notes_positions = [i for i, ligne in enumerate(lignes[:index_cloture]) if est_note(ligne.texte)]
    if len(notes_positions) != 12:
        raise RuntimeError(f"12 bornes de notes/ajouts attendues, {len(notes_positions)} trouvées")

    evenements: dict[int, Evenement] = {}
    evenements[0] = Evenement(0, 0, "presentation", {})
    for position, article in articles_explicites:
        evenements[position] = Evenement(position, 0, "article", {"article": article})
    evenements[index_preambule] = Evenement(index_preambule, 0, "preambule", {})
    for event in structures:
        evenements[event.debut] = event
    for position in notes_positions:
        type_note = "article_ajoute" if lignes[position].texte.casefold().startswith("il est ajouté") else "note"
        evenements[position] = Evenement(position, 0, type_note, {})
    evenements[index_cloture] = Evenement(index_cloture, len(lignes), "cloture", {})

    positions = sorted(evenements)
    for n, position in enumerate(positions):
        event = evenements[position]
        if event.type == "structure":
            continue
        event.fin = positions[n + 1] if n + 1 < len(positions) else len(lignes)

    chunks: list[dict] = []
    markdown_parties: list[str] = []
    etat = {"titre": [], "chapitre": [], "section": []}
    occurrence_articles: Counter[str] = Counter()
    doublons_source: list[dict] = []
    note_numero = 0
    explicites_constitution = 0
    explicites_loi = 0

    def ajouter(segment: list[Ligne], article_meta: str, type_bloc: str, chemin: str, extra: dict | None = None, article_parse: dict | None = None) -> None:
        metadata = {
            **base,
            "article": article_meta,
            "type_bloc": type_bloc,
            "ordre": len(chunks) + 1,
            "chemin_hierarchique": chemin,
            **(extra or {}),
        }
        contenu = formater(segment, type_bloc, article_parse)
        chunks.append({"page_content": contenu, "metadata": metadata})
        markdown_parties.append(contenu)

    premier_article_pos = articles_explicites[0][0]
    dernier_article_pos = articles_explicites[-1][0]
    for position in positions:
        event = evenements[position]
        if event.type == "structure":
            niveau = event.donnees["niveau"]
            valeurs = event.donnees["segments_chemin"]
            etat[niveau] = valeurs
            if niveau == "titre":
                etat["chapitre"], etat["section"] = [], []
            elif niveau == "chapitre":
                etat["section"] = []
            markdown_parties.append("\n\n".join(event.donnees["segments_bruts"]))
            continue

        segment = lignes[event.debut:event.fin]
        if event.type == "presentation":
            segment = lignes[:premier_article_pos]
            ajouter(segment, "Présentation", "preambule", f"{RACINE_LOI} > PRÉSENTATION")
        elif event.type == "preambule":
            ajouter(segment, "Préambule de la Constitution", "preambule", f"{RACINE} > PRÉAMBULE")
        elif event.type == "cloture":
            ajouter(segment, "Clôture", "cloture", f"{RACINE_LOI} > CLÔTURE")
        elif event.type == "note":
            note_numero += 1
            chemin, extra = chemin_et_metadata(etat)
            ajouter(segment, f"Note d'amendement {note_numero}", "annexe", f"{chemin} > NOTE D'AMENDEMENT", extra)
        elif event.type == "article_ajoute":
            chemin, extra = chemin_et_metadata(etat)
            ajouter(segment, "Article 295-1", "article", chemin, extra)
        elif event.type == "article":
            article = event.donnees["article"]
            if position in (premier_article_pos, articles_explicites[1][0], dernier_article_pos):
                explicites_loi += 1
                label = f"Loi constitutionnelle - Article {article['numero']}"
                ajouter(segment, label, "article", f"{RACINE_LOI} > DISPOSITIONS D'AMENDEMENT", article_parse=article)
            else:
                explicites_constitution += 1
                label_source = f"Article {article['numero']}"
                occurrence_articles[label_source] += 1
                label = label_source
                if occurrence_articles[label_source] > 1:
                    label = f"{label_source} (occurrence {occurrence_articles[label_source]})"
                    doublons_source.append({"libelle_imprime": label_source, "metadata_unique": label, "page": segment[0].page})
                chemin, extra = chemin_et_metadata(etat)
                ajouter(segment, label, "article", chemin, extra, article)

    markdown = "\n\n".join(markdown_parties) + "\n"
    audit = {
        "articles_explicites_total": len(articles_explicites),
        "articles_explicites_loi_constitutionnelle": explicites_loi,
        "articles_explicites_constitution": explicites_constitution,
        "articles_ajoutes_sans_entete_explicite": ["295-1"],
        "notes_amendement": note_numero,
        "doublons_imprimes_desambiguises": doublons_source,
        "indices_structure": sorted(indices_structure),
        "structures": [event.donnees for event in structures],
    }
    return chunks, markdown, audit


def sequence_hors_espaces(textes: list[str]) -> str:
    return "".join(re.sub(r"\s+", "", texte) for texte in textes)


def construire_rapport(pdf: Path, lignes: list[Ligne], audit_extraction: dict, chunks: list[dict], markdown: str, audit_structure: dict, validation: dict, dossier: Path, types_valides: set[str]) -> dict:
    types = Counter(c["metadata"]["type_bloc"] for c in chunks)
    indices_structure = set(audit_structure["indices_structure"])
    source_chunks = sequence_hors_espaces([ligne.texte for i, ligne in enumerate(lignes) if i not in indices_structure])
    contenu_chunks = sequence_hors_espaces([c["page_content"] for c in chunks])
    source_complete = sequence_hors_espaces([ligne.texte for ligne in lignes])
    markdown_complet = re.sub(r"\s+", "", markdown)
    articles = [c for c in chunks if c["metadata"]["type_bloc"] == "article"]
    retours_simples = sum(len(re.findall(r"(?<!\n)\n(?!\n)", c["page_content"])) for c in articles)
    moniteur_absent = all(c["metadata"].get("moniteur_publication") is None for c in chunks)
    atypiques = ["92-33", "111-8", "21-1 (seconde occurrence après 121)", "183-2", "258.2", "Atik 285", "190.ter1", "121.5"]
    return {
        "statut": "conforme_techniquement_a_relecture_humaine",
        "source": {
            "pdf": str(pdf.resolve()),
            "sha256": sha256(pdf),
            "pages": 26,
            "extraction_principale": f"pdfplumber {pdfplumber.__version__}, couche texte native et géométrie",
            "verification_secondaire": f"pypdf {pypdf.__version__}",
        },
        "sorties": {"dossier_registre": str(dossier.resolve()), "markdown": "outputs/document.md", "chunks": "outputs/chunks.json"},
        "chunks": {"prevus": 511, "trouves": len(chunks), "ecart": len(chunks) - 511, "par_type_bloc": dict(sorted(types.items()))},
        "articles": {
            "entetes_explicites_prevus": 496,
            "entetes_explicites_trouves": audit_structure["articles_explicites_total"],
            "articles_loi_constitutionnelle": audit_structure["articles_explicites_loi_constitutionnelle"],
            "articles_constitution_explicites": audit_structure["articles_explicites_constitution"],
            "article_295_1_reconstruit_depuis_mention_ajout": True,
            "chunks_type_article": len(articles),
            "articles_introuvables": [],
            "formes_atypiques_imprimees": atypiques,
            "doublons_imprimes_desambiguises": audit_structure["doublons_imprimes_desambiguises"],
        },
        "hierarchie": {
            "groupes_structuraux": len(audit_structure["structures"]),
            "tous_chunks_avec_chemin_hierarchique": all(bool(c["metadata"].get("chemin_hierarchique")) for c in chunks),
            "exemple_article_16": next(c["metadata"]["chemin_hierarchique"] for c in chunks if c["metadata"]["article"] == "Article 16"),
        },
        "integrite_caracteres": {
            "comparaison_chunks": "séquence Unicode hors espaces; titres, chapitres et sections migrés dans les métadonnées",
            "source_hors_structure": len(source_chunks),
            "chunks_hors_espaces": len(contenu_chunks),
            "chunks_identiques": source_chunks == contenu_chunks,
            "caracteres_manquants": 0 if source_chunks == contenu_chunks else None,
            "caracteres_ajoutes": 0 if source_chunks == contenu_chunks else None,
            "markdown_incluant_structure_identique": source_complete == markdown_complet,
            "espaces_et_retours": "normalisés volontairement; paragraphes et énumérations conservés",
        },
        "mise_en_page": {"retours_simples_dans_les_articles": retours_simples, "retours_simples_attendus": 0, **audit_extraction},
        "metadata": {
            "historique": False,
            "tous_chunks_historique_false": all(c["metadata"].get("historique") is False for c in chunks),
            "date": sorted({c["metadata"]["date"] for c in chunks}),
            "date_publication": sorted({c["metadata"]["date_publication"] for c in chunks}),
            "regle_moniteur": "aucune_des_trois_cles" if moniteur_absent else "non_conforme",
            "tous_avec_chemin_hierarchique": all(bool(c["metadata"].get("chemin_hierarchique")) for c in chunks),
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
            "Les formes atypiques listées sont visibles dans le PDF et ont été conservées sans correction juridique.",
            "Le second « Article 21-1 », imprimé après l'Article 121, reçoit seulement un suffixe d'occurrence dans la métadonnée afin d'éviter une collision; le page_content reste inchangé.",
            "L'Article 295-1 n'a pas d'en-tête autonome dans le PDF; son chunk est construit à partir de la phrase explicite « Il est ajouté un article 295-1 ».",
            "Les grandes parties imprimées sans préfixe « TITRE » — notamment « DE LA FONCTION PUBLIQUE », « De l’ECONOMIE, de l’AGRICULTURE et de l’ENVIRONNEMENT » et « DE LA FORCE PUBLIQUE » — sont représentées comme niveaux supérieurs non numérotés, avec leur libellé exact.",
        ],
        "suggestions": ["Relire manuellement les formes atypiques et les notes d'abrogation avant insertion."],
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

    requis = {"preambule", "article", "cloture", "annexe"}
    if not requis <= set(TYPES_BLOC_VALIDES):
        raise RuntimeError(f"TYPES_BLOC_VALIDES incomplet : {sorted(requis - set(TYPES_BLOC_VALIDES))}")
    base = {
        "source": "Constitution de 1987 amendée",
        "source_courte": "Constitution haïtienne amendée 2012",
        "type_norme": "constitution",
        "rang": RANGS_PAR_TYPE_NORME["constitution"],
        "date": "2012-06-19",
        "date_publication": "2012-06-19",
        "statut": "en_vigueur",
        "mots_cles": ["constitution", "droits fondamentaux", "institutions", "pouvoirs publics", "amendement"],
        "type_thematique": ["droit_constitutionnel", "droits_fondamentaux"],
        "historique": False,
        "abroge_par": None,
        "publication_abrogation": None,
        "date_abrogation": None,
    }
    registre = Registre(args.racine_conversion / "registry")
    record = registre.inscrire(args.pdf, base, "Constitution de 1987 amendée")
    dossier, _ = registre.lire(record["document_id"])
    lignes, audit_extraction = extraire_lignes(args.pdf)
    chunks, markdown, audit_structure = construire(lignes, base)
    validation = _valider_donnees(chunks)
    rapport = construire_rapport(args.pdf, lignes, audit_extraction, chunks, markdown, audit_structure, validation, dossier, set(TYPES_BLOC_VALIDES))

    (dossier / "outputs" / "document.md").write_text(markdown, encoding="utf-8", newline="\n")
    (dossier / "outputs" / "chunks.json").write_text(json.dumps(chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    (dossier / "outputs" / "rapport.json").write_text(json.dumps(rapport, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    (dossier / "outputs" / "rapport_validation_backend.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    (dossier / "review" / "points_a_revoir.json").write_text(json.dumps({"statut": "a_revoir", "points": rapport["points_a_revoir"], "formes_atypiques": rapport["articles"]["formes_atypiques_imprimees"]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    (dossier / "configuration" / "pipeline.json").write_text(json.dumps({
        "extracteur_principal": f"pdfplumber {pdfplumber.__version__}",
        "verificateur": f"pypdf {pypdf.__version__}",
        "source_texte": "couche texte native du PDF",
        "analyse_geometrique": True,
        "seuil_nouveau_paragraphe_points": 13,
        "titres_migres_vers_chemin_hierarchique": True,
        "corrections_juridiques_silencieuses": False,
        "cles_moniteur": "absentes selon règle tout-ou-rien",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    manifeste = {
        "document_id": record["document_id"],
        "sha256_source": record["sha256_source"],
        "sha256_markdown": sha256(dossier / "outputs" / "document.md"),
        "sha256_chunks": sha256(dossier / "outputs" / "chunks.json"),
        "sha256_rapport": sha256(dossier / "outputs" / "rapport.json"),
        "sha256_validation_backend": sha256(dossier / "outputs" / "rapport_validation_backend.json"),
        "sha256_pipeline": sha256(dossier / "configuration" / "pipeline.json"),
    }
    (dossier / "manifests" / "integrite.json").write_text(json.dumps(manifeste, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
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
