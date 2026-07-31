#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Halex AI — Convertisseur PDF du Moniteur -> JSON (un chunk par article)

Produit un fichier JSON directement televersable dans le panneau /admin,
conforme au schema metadata valide cote serveur.

CE SCRIPT EST AUTONOME.
Il n'importe rien du projet, ne modifie aucun fichier existant, n'ecrit
jamais en base et n'appelle jamais OpenAI. Il lit un PDF, il ecrit des
fichiers a cote. Rien d'autre.

INSTALLATION
------------
    pip install pymupdf4llm          (installe PyMuPDF au passage)
    # minimum viable si pymupdf4llm pose probleme :
    pip install pymupdf

UTILISATION
-----------
    1. Remplir le bloc CONFIG ci-dessous en lisant l'en-tete du Moniteur.
    2. python convertir_moniteur.py "documents/marches_publics_2009.pdf"
    3. OUVRIR le fichier *_texte_nettoye.txt genere et le lire.
       C'est l'etape que personne ne fait et qui coute le plus cher a sauter.
    4. Si le decoupage est mauvais : corriger CONFIG ou changer --mode,
       relancer. Le script est rejouable a l'infini, il ne coute rien.
    5. Quand le rapport est vert : televerser le *_chunks.json dans /admin.

OPTIONS
-------
    --mode auto|markdown|blocs|simple   strategie d'extraction (defaut: auto)
    --sortie DOSSIER                    dossier de sortie (defaut: a cote du PDF)
    --enveloppe                         encapsule dans {"chunks": [...]}
    --pages 1-40                        ne traiter qu'une plage de pages
"""

import argparse
import json
import re
import sys
import traceback
import unicodedata
from datetime import datetime
from pathlib import Path

# ============================================================================
# CONFIG — A MODIFIER POUR CHAQUE DOCUMENT
# ============================================================================
# Le script ne DEVINE aucune metadonnee. Elles viennent toutes d'ici, et tu
# les remplis en lisant l'en-tete du journal. Une metadonnee devinee par un
# programme dans un corpus juridique est une metadonnee fausse un jour sur dix.
CONFIG = {
    # Titre du texte tel qu'il sera cite a l'utilisateur final.
    # Doit rester STABLE dans le temps : couple avec "article", c'est la cle
    # de detection des doublons cote serveur.
    "source": "Loi fixant les regles generales relatives aux marches publics "
              "et aux conventions de concession d'ouvrage de service public",

    # Un seul de : constitution | loi | code | decret | arrete
    # ATTENTION : le serveur compare en strict, avec les accents.
    # Ecris donc "décret" / "arrêté" avec accents si tu les utilises.
    "type_norme": "loi",

    # Doit correspondre au type_norme (voir TABLE_RANGS). Verifie a l'execution.
    "rang": 2,

    # Date de l'ACTE au format YYYY-MM-DD.
    # A defaut de date de signature connue, mettre la date de parution.
    "date": "2009-06-10",

    # en_vigueur | adopté_non_appliqué
    "statut": "en_vigueur",

    # --- Reference Le Moniteur (lue sur l'en-tete du journal) ---------------
    "moniteur_annee": 164,        # entier
    "moniteur_numero": "78",       # chaine : certains numeros sont "78 A", "12 bis"
    "moniteur_type": "extraordinaire",  # ordinaire | spécial

    # --- Reglages de decoupage ---------------------------------------------
    # True  : un marqueur n'est un article que s'il est suivi de .- ou . ou -
    #         (protege des renvois du type "vise a l'article 30 de la presente Loi")
    # False : a n'activer que si ton PDF ecrit "Article 12" sans ponctuation.
    "exiger_terminateur": True,

    # Longueur en caracteres en dessous / au dessus de laquelle on t'alerte.
    "longueur_min_alerte": 80,
    "longueur_max_alerte": 6000,
}

# ============================================================================
# CONSTANTES — miroir des regles du validateur serveur. NE PAS DIVERGER.
# ============================================================================
TABLE_RANGS = {
    "constitution": 1,
    "loi": 2,
    "code": 3,
    "décret": 4,
    "arrêté": 5,
}

STATUTS_VALIDES = {"en_vigueur", "adopté_non_appliqué"}
MONITEUR_TYPES_CONNUS = {"ordinaire", "spécial", "extraordinaire"}

CLES_OBLIGATOIRES = [
    "source", "type_norme", "rang", "date", "statut", "article",
    "moniteur_annee", "moniteur_numero", "moniteur_type",
]
CLES_OPTIONNELLES = ["livre", "titre", "chapitre", "section", "paragraphe"]
CLES_INTERDITES = ["lot_ingestion", "date_ingestion"]  # generees par le serveur

# ============================================================================
# 1. EXTRACTION
# ============================================================================

def _pages_demandees(arg):
    """'1-40' -> (0, 39) en index 0. None -> None."""
    if not arg:
        return None
    m = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", arg)
    if not m:
        raise ValueError("Format --pages attendu : 1-40")
    debut, fin = int(m.group(1)), int(m.group(2))
    if debut < 1 or fin < debut:
        raise ValueError("Plage de pages incoherente")
    return (debut - 1, fin - 1)


def extraire_markdown(chemin, plage):
    """pymupdf4llm : la meilleure restitution de la structure. Peut echouer."""
    import pymupdf4llm
    kwargs = {}
    if plage:
        kwargs["pages"] = list(range(plage[0], plage[1] + 1))
    return pymupdf4llm.to_markdown(str(chemin), **kwargs)


def extraire_blocs(chemin, plage):
    """
    PyMuPDF, blocs tries haut->bas puis gauche->droite.
    C'est le mode a utiliser quand le Moniteur met "Article 3.-" dans une
    colonne de gauche et le texte dans une colonne de droite : le tri
    reconstitue l'ordre de lecture au lieu de melanger les colonnes.
    """
    import fitz
    doc = fitz.open(str(chemin))
    morceaux = []
    for i, page in enumerate(doc):
        if plage and not (plage[0] <= i <= plage[1]):
            continue
        blocs = page.get_text("blocks")
        blocs.sort(key=lambda b: (round(b[1], 1), round(b[0], 1)))
        for b in blocs:
            texte = b[4].strip()
            if texte:
                morceaux.append(texte)
        morceaux.append("")  # separateur de page
    doc.close()
    return "\n".join(morceaux)


def extraire_simple(chemin, plage):
    """PyMuPDF brut. Le filet de securite : marche partout, restitue moins bien."""
    import fitz
    doc = fitz.open(str(chemin))
    morceaux = []
    for i, page in enumerate(doc):
        if plage and not (plage[0] <= i <= plage[1]):
            continue
        morceaux.append(page.get_text("text"))
    doc.close()
    return "\n".join(morceaux)


def extraire(chemin, mode, plage):
    """
    Retourne (texte, mode_reellement_utilise).
    En mode auto : markdown -> blocs -> simple, en affichant la VRAIE erreur
    a chaque echec. Pas de message generique : on veut savoir pourquoi.
    """
    strategies = {
        "markdown": extraire_markdown,
        "blocs": extraire_blocs,
        "simple": extraire_simple,
    }

    if mode != "auto":
        return strategies[mode](chemin, plage), mode

    for nom in ("markdown", "blocs", "simple"):
        try:
            texte = strategies[nom](chemin, plage)
            if texte and texte.strip():
                return texte, nom
            print(f"  [!] mode '{nom}' : texte vide, on essaie le suivant.")
        except Exception as exc:
            print(f"  [!] mode '{nom}' a echoue : {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=2)
    raise RuntimeError(
        "Aucune strategie d'extraction n'a produit de texte.\n"
        "Cause la plus frequente : le PDF est une image sans couche texte "
        "(scan sans OCR). Repasse-le dans Adobe Scan avec l'OCR francais "
        "active, ou re-exporte en 'PDF consultable'."
    )


# ============================================================================
# 2. NETTOYAGE
# ============================================================================

RE_ENTETE_MONITEUR = re.compile(r"LE\s*MONITEUR", re.IGNORECASE)
RE_PAGE_SEULE = re.compile(r"^\s*\d{1,4}\s*$")
RE_ARTEFACTS_MD = re.compile(r"(\*\*|__|^#{1,6}\s*|^\s*\|.*\|\s*$|^\s*-{3,}\s*$)",
                             re.MULTILINE)
RE_CESURE = re.compile(r"(\w)-\s*\n\s*([a-zàâäéèêëîïôöùûüç])")
RE_ESPACES = re.compile(r"[ \t\u00a0]+")
RE_LIGNES_VIDES = re.compile(r"\n{3,}")


def nettoyer(texte, config):
    """
    Supprime ce qui n'est pas du droit : entetes de journal, numeros de page,
    artefacts markdown, cesures de fin de ligne.
    """
    numero = str(config["moniteur_numero"]).strip()
    re_numero = re.compile(r"^\s*N[o°]\.?\s*" + re.escape(numero) + r"\b", re.IGNORECASE)

    lignes_gardees = []
    for ligne in texte.splitlines():
        nue = ligne.strip()
        if RE_ENTETE_MONITEUR.search(nue):      # "<< LE MONITEUR >>" + sa ligne
            continue
        if re_numero.match(nue):                # "No. 78- Mardi 28 Juillet 2009"
            continue
        if RE_PAGE_SEULE.match(nue):            # numero de page isole
            continue
        lignes_gardees.append(ligne)

    t = "\n".join(lignes_gardees)
    t = RE_ARTEFACTS_MD.sub("", t)
    t = t.replace("\u00ad", "")                 # trait d'union conditionnel
    t = RE_CESURE.sub(r"\1\2", t)               # "obliga-\ntoirement" -> "obligatoirement"
    t = RE_ESPACES.sub(" ", t)
    t = "\n".join(l.rstrip() for l in t.splitlines())
    t = RE_LIGNES_VIDES.sub("\n\n", t)
    return t.strip()


# ============================================================================
# 3. DECOUPAGE PAR ARTICLE + SUIVI DE L'ARBORESCENCE
# ============================================================================

MOTIF_ARTICLE = (
    r"^[ \t]*(?:Article|Art\.?|ARTICLE)[ \t]+"
    r"(premier|1er|\d{1,4})[ \t]*"
    r"(bis|ter|quater|quinquies)?[ \t]*"
)
TERMINATEUR = r"(?:\.\s*-|\.-|\.|-|–|—|:)"

RE_LIVRE = re.compile(r"^\s*(LIVRE\s+[^\n]{0,80})$", re.IGNORECASE | re.MULTILINE)
RE_TITRE = re.compile(r"^\s*(TITRE\s+[^\n]{0,80})$", re.IGNORECASE | re.MULTILINE)
RE_CHAPITRE = re.compile(r"^\s*(CHAPITRE\s+[^\n]{0,80})$", re.IGNORECASE | re.MULTILINE)
RE_SECTION = re.compile(r"^\s*(Section\s+[^\n]{0,80})$", re.IGNORECASE | re.MULTILINE)
RE_PARAGRAPHE = re.compile(r"^\s*((?:§|Paragraphe)\s*[^\n]{0,80})$", re.IGNORECASE | re.MULTILINE)

HIERARCHIE = [
    ("livre", RE_LIVRE),
    ("titre", RE_TITRE),
    ("chapitre", RE_CHAPITRE),
    ("section", RE_SECTION),
    ("paragraphe", RE_PARAGRAPHE),
]
# Un niveau superieur remet a zero les niveaux inferieurs.
NIVEAUX = ["livre", "titre", "chapitre", "section", "paragraphe"]


def recoller_marqueurs_orphelins(texte):
    """
    Le Moniteur imprime souvent "Article 3.-" dans une colonne de gauche.
    Certains extracteurs le rendent seul sur sa ligne. On le recolle au
    paragraphe suivant, sinon le decoupage produit des chunks vides.
    """
    re_orphelin = re.compile(
        MOTIF_ARTICLE + TERMINATEUR + r"?\s*$",
        re.MULTILINE,
    )
    lignes = texte.splitlines()
    sortie = []
    i = 0
    while i < len(lignes):
        ligne = lignes[i]
        if re_orphelin.match(ligne.strip()) and len(ligne.strip()) <= 25:
            j = i + 1
            while j < len(lignes) and not lignes[j].strip():
                j += 1
            if j < len(lignes):
                sortie.append(ligne.rstrip() + " " + lignes[j].strip())
                i = j + 1
                continue
        sortie.append(ligne)
        i += 1
    return "\n".join(sortie)


def normaliser_numero(brut, suffixe):
    """'premier' -> 1 ; renvoie (entier_pour_tri, libelle_lisible)."""
    b = brut.lower()
    n = 1 if b in ("premier", "1er") else int(b)
    libelle = f"Article {n}"
    if suffixe:
        libelle += f" {suffixe.lower()}"
    return n, libelle


def decouper(texte, config):
    """
    Retourne une liste de dicts :
      {num, suffixe, libelle, contenu, position, hierarchie{...}}
    """
    motif = MOTIF_ARTICLE + (TERMINATEUR if config["exiger_terminateur"] else TERMINATEUR + r"?")
    re_article = re.compile(motif, re.MULTILINE)

    marqueurs = list(re_article.finditer(texte))
    if not marqueurs:
        raise RuntimeError(
            "Aucun marqueur d'article trouve.\n"
            "Pistes, dans l'ordre :\n"
            "  1. Ouvre le fichier *_texte_nettoye.txt : le texte est-il lisible ?\n"
            "  2. Essaie --mode blocs (utile quand le numero d'article est en "
            "colonne de gauche).\n"
            "  3. Passe \"exiger_terminateur\" a False dans CONFIG si le PDF "
            "ecrit 'Article 12' sans ponctuation."
        )

    # Etat courant de l'arborescence, mis a jour au fil du texte.
    etat = {niveau: None for niveau in NIVEAUX}
    entetes = []
    for niveau, regex in HIERARCHIE:
        for m in regex.finditer(texte):
            entetes.append((m.start(), niveau, " ".join(m.group(1).split())))
    entetes.sort()

    articles = []
    for idx, m in enumerate(marqueurs):
        debut = m.start()
        fin = marqueurs[idx + 1].start() if idx + 1 < len(marqueurs) else len(texte)

        # Appliquer les entetes rencontres avant cet article.
        for pos, niveau, valeur in entetes:
            if pos < debut:
                etat[niveau] = valeur
                for inferieur in NIVEAUX[NIVEAUX.index(niveau) + 1:]:
                    etat[inferieur] = None

        num, libelle = normaliser_numero(m.group(1), m.group(2))
        corps = texte[debut:fin].strip()
        corps = RE_LIGNES_VIDES.sub("\n\n", corps)

        articles.append({
            "num": num,
            "suffixe": (m.group(2) or "").lower(),
            "libelle": libelle,
            "contenu": corps,
            "hierarchie": {k: v for k, v in etat.items() if v},
        })
    return articles


# ============================================================================
# 4. CONSTRUCTION DES CHUNKS
# ============================================================================

def construire_chunks(articles, config):
    chunks = []
    for a in articles:
        metadata = {
            "source": config["source"],
            "type_norme": config["type_norme"],
            "rang": config["rang"],
            "date": config["date"],
            "statut": config["statut"],
            "article": a["libelle"],
            "moniteur_annee": config["moniteur_annee"],
            "moniteur_numero": str(config["moniteur_numero"]),
            "moniteur_type": config["moniteur_type"],
        }
        metadata.update(a["hierarchie"])  # livre/titre/chapitre/section/paragraphe
        chunks.append({"page_content": a["contenu"], "metadata": metadata})
    return chunks


# ============================================================================
# 5. VALIDATION LOCALE (memes regles que le serveur)
# ============================================================================

def valider(chunks, config):
    """Retourne (erreurs, avertissements). Erreur = le serveur refusera."""
    erreurs, alertes = [], []

    # --- Coherence de la CONFIG elle-meme ---------------------------------
    tn = config["type_norme"]
    if tn not in TABLE_RANGS:
        erreurs.append(
            f"type_norme '{tn}' inconnu. Valeurs admises (accents compris) : "
            + ", ".join(TABLE_RANGS)
        )
    elif config["rang"] != TABLE_RANGS[tn]:
        erreurs.append(
            f"rang {config['rang']} incoherent : '{tn}' impose rang {TABLE_RANGS[tn]}."
        )

    if config["statut"] not in STATUTS_VALIDES:
        erreurs.append(f"statut '{config['statut']}' invalide ({', '.join(STATUTS_VALIDES)}).")

    try:
        d = datetime.strptime(config["date"], "%Y-%m-%d")
        if d.year != int(config["moniteur_annee"]):
            alertes.append(
                f"date ({d.year}) et moniteur_annee ({config['moniteur_annee']}) "
                "different. Normal si l'acte a ete signe une annee et publie la "
                "suivante — a verifier tout de meme."
            )
        if d > datetime.now():
            erreurs.append("date situee dans le futur.")
    except ValueError:
        erreurs.append(f"date '{config['date']}' : format attendu YYYY-MM-DD.")

    if config["moniteur_type"] not in MONITEUR_TYPES_CONNUS:
        alertes.append(
            f"moniteur_type '{config['moniteur_type']}' hors des valeurs "
            f"habituelles ({', '.join(MONITEUR_TYPES_CONNUS)}). Verifie ce que "
            "le validateur serveur accepte avant de televerser."
        )

    # --- Structure de chaque chunk ----------------------------------------
    vus = {}
    for i, c in enumerate(chunks, 1):
        if not isinstance(c.get("page_content"), str) or not c["page_content"].strip():
            erreurs.append(f"chunk #{i} : page_content vide.")
        meta = c.get("metadata", {})
        for cle in CLES_OBLIGATOIRES:
            if cle not in meta or meta[cle] in (None, ""):
                erreurs.append(f"chunk #{i} : cle obligatoire '{cle}' manquante.")
        for cle in CLES_INTERDITES:
            if cle in meta:
                erreurs.append(f"chunk #{i} : cle '{cle}' interdite (generee par le serveur).")
        for cle in meta:
            if cle not in CLES_OBLIGATOIRES and cle not in CLES_OPTIONNELLES \
               and cle not in CLES_INTERDITES:
                erreurs.append(f"chunk #{i} : cle '{cle}' hors schema.")

        cle_unicite = (meta.get("source"), meta.get("article"))
        if cle_unicite in vus:
            erreurs.append(
                f"doublon interne : {meta.get('article')} apparait aux chunks "
                f"#{vus[cle_unicite]} et #{i}."
            )
        else:
            vus[cle_unicite] = i

        n = len(c.get("page_content", ""))
        if 0 < n < config["longueur_min_alerte"]:
            alertes.append(f"chunk #{i} ({meta.get('article')}) : {n} caracteres seulement.")
        if n > config["longueur_max_alerte"]:
            alertes.append(
                f"chunk #{i} ({meta.get('article')}) : {n} caracteres — un "
                "marqueur d'article a probablement ete manque juste avant."
            )

    return erreurs, alertes


def detecter_trous(articles):
    """Numerotation : 1,2,3,7 -> signale 4,5,6. Un trou = une page mal OCRisee."""
    nums = sorted({a["num"] for a in articles})
    if not nums:
        return []
    manquants = [n for n in range(nums[0], nums[-1] + 1) if n not in nums]
    return manquants


# ============================================================================
# 6. MAIN
# ============================================================================

def main():
    p = argparse.ArgumentParser(description="PDF Moniteur -> JSON chunks Halex")
    p.add_argument("pdf", help="chemin du PDF")
    p.add_argument("--mode", default="auto",
                   choices=["auto", "markdown", "blocs", "simple"])
    p.add_argument("--sortie", default=None, help="dossier de sortie")
    p.add_argument("--enveloppe", action="store_true",
                   help='ecrire {"chunks": [...]} au lieu d\'une liste nue')
    p.add_argument("--pages", default=None, help="plage de pages, ex. 1-40")
    args = p.parse_args()

    chemin = Path(args.pdf)
    if not chemin.is_file():
        print(f"[ERREUR] Fichier introuvable : {chemin}")
        return 1

    dossier = Path(args.sortie) if args.sortie else chemin.parent
    dossier.mkdir(parents=True, exist_ok=True)
    base = chemin.stem

    try:
        plage = _pages_demandees(args.pages)
    except ValueError as e:
        print(f"[ERREUR] {e}")
        return 1

    print(f"\n=== {chemin.name} ===")
    print("[1/5] Extraction...")
    try:
        brut, mode_utilise = extraire(chemin, args.mode, plage)
    except ImportError as exc:
        print(f"[ERREUR] Dependance manquante : {exc}")
        print("        pip install pymupdf4llm    (ou : pip install pymupdf)")
        return 1
    except Exception as exc:
        print(f"[ERREUR] {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return 1
    print(f"      mode retenu : {mode_utilise} — {len(brut)} caracteres bruts")

    print("[2/5] Nettoyage...")
    texte = nettoyer(brut, CONFIG)
    texte = recoller_marqueurs_orphelins(texte)
    f_txt = dossier / f"{base}_texte_nettoye.txt"
    f_txt.write_text(texte, encoding="utf-8")
    print(f"      {len(texte)} caracteres -> {f_txt.name}")

    print("[3/5] Decoupage par article...")
    try:
        articles = decouper(texte, CONFIG)
    except RuntimeError as exc:
        print(f"[ERREUR] {exc}")
        return 1
    print(f"      {len(articles)} articles detectes "
          f"(du {articles[0]['libelle']} au {articles[-1]['libelle']})")

    print("[4/5] Construction des chunks...")
    chunks = construire_chunks(articles, CONFIG)

    print("[5/5] Validation locale...")
    erreurs, alertes = valider(chunks, CONFIG)
    trous = detecter_trous(articles)
    if trous:
        apercu = ", ".join(str(t) for t in trous[:20])
        suite = " ..." if len(trous) > 20 else ""
        alertes.append(f"numerotation : {len(trous)} article(s) absent(s) : {apercu}{suite}")

    print("\n" + "=" * 68)
    if alertes:
        print(f"AVERTISSEMENTS ({len(alertes)}) — a lire, pas bloquants :")
        for a in alertes:
            print("  ~ " + a)
        print()
    if erreurs:
        print(f"ERREURS ({len(erreurs)}) — le serveur refusera ce fichier :")
        for e in erreurs[:40]:
            print("  x " + e)
        if len(erreurs) > 40:
            print(f"  ... et {len(erreurs) - 40} autres.")
        print("\nAucun JSON ecrit. Corrige la CONFIG ou le decoupage, puis relance.")
        print("=" * 68)
        return 1

    charge = {"chunks": chunks} if args.enveloppe else chunks
    f_json = dossier / f"{base}_chunks.json"
    with f_json.open("w", encoding="utf-8") as f:
        json.dump(charge, f, ensure_ascii=False, indent=2)

    total = sum(len(c["page_content"]) for c in chunks)
    print(f"OK — {len(chunks)} chunks, {total} caracteres.")
    print(f"     -> {f_json}")
    print("\nAVANT DE TELEVERSER : ouvre le *_texte_nettoye.txt et relis")
    print("trois articles au hasard, dont le premier et le dernier.")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())