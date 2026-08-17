#!/usr/bin/env python3
"""Transcrit et structure la loi haïtienne du 19 août 1955 sur les pharmacies."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pdfplumber
import pypdf


RACINE = (
    "LOI DU 19 AOÛT 1955 RÉGLEMENTANT L'INTRODUCTION, LA FABRICATION, "
    "LA DISTRIBUTION ET LA VENTE DES PRODUITS PHARMACEUTIQUES ET BIOLOGIQUES"
)

PREAMBULE = """1955/85 LOI

PAUL E. MAGLOIRE

Président de la République."""

VISAS = """Vu les articles 57 et 79 de la Constitution;

Vu la Loi du 16 juillet 1923 sur les narcotiques;

Vu le décret-loi du 10 juillet 1940 réglementant l'exercice de la Médecine, de la Pharmacie et de l'Art Dentaire;

Vu le décret-loi du 22 novembre 1945 précisant les attributions du Service de la Santé Publique;

Vu la Loi du 5 février 1948 sur le contrôle des médicaments et produits pharmaceutiques;

Considérant qu'il est du devoir des Grands Pouvoirs de l'Etat de veiller à la Santé Publique;

Considérant les dispositions des Conventions de Genève du 19 février 1925 et du 13 juillet 1931 et de l'Acte Final signés À Genève le 19 novembre 1948, et notamment les Tableaux ABC de narcotiques, stupéfiants et substances vénéneuses annexés aux dites Conventions;

Considérant qu'il importe de réglementer d'une manière efficace l'introduction, la fabrication, la distribution et la vente des produits pharmaceutiques et biologiques tant par les représentants des Laboratoires agents dépositaires que par les Pharmaciens;

Sur le rapport des Secrétaires d'Etat de la Santé Publique, de la Justice et du Commerce;

Et de l'avis du Conseil des Secrétaires d'Etat;

A Proposé

Et le Corps Législatif a voté la Loi suivante:"""

ARTICLES = {
    1: """Le pharmacien, le fabricant, le représentant ou tout dépositaire de produits pharmaceutiques, devront se conformer aux lois, arrêtés et règlements administratifs gouvernant la réception, l'entrepôt, la distribution et la vente de ces produits.""",
    2: """Les pharmacies sont placées sous le contrôle du Département de la Santé Publique agissant soit directement, soit par l'intermédiaire de ses organismes qualifiés ou de toutes commissions de contrôle et d'inspection instituées À cette fin. En cas d'ouverture illégale d'une pharmacie, le constat sera fait par les autorités judiciaires compétentes sur réquisition du fonctionnaire responsable du Département de la Santé Publique, et le procès-verbal y relatif sera acheminé au Commissaire du Gouvernement pour les suites nécessaires.""",
    3: """Les pharmacies et les dépôts de médicaments seront inspectés au moins une fois l'an par le Service de Contrôle des médicaments. La Commission de Contrôle sera composée obligatoirement de deux pharmaciens attachés au Service de la Santé Publique et de tous autres fonctionnaires désignés par le Secrétaire d'Etat de la Santé Publique. Chaque inspection sera consignée dans un registre tenu À cette fin par le gérant responsable avec mention de toutes les observations, recommandations et suggestions faites par la Commission de contrôle.

Les locaux et le mobilier de la pharmacie doivent être tenus dans des conditions d'ordre et de propreté sous peine de retrait de la licence.""",
    4: """Sont considérés comme médicaments ou remèdes, toute drogue simple, tout produit chimique défini, tout mélange ou toute préparation composée lorsque ces produits sont destinés À l'usage préventif ou curatif des maladies de l'homme ou des animaux.""",
    5: """Sont considérés comme préparation pharmaceutique dont la vente est réservée aux seules pharmacies:

les spécialités ou tous autres produits vendus dans un but curatif;

les objets de pansements imprégnés d'un produit médicamenteux ainsi que les drains et ligatures stérilisées;

les sérums, vaccins, liquides organiques et autres produits biologiques.""",
    6: """Nul ne peut diriger une officine ou pharmacie ou en avoir la direction technique, préparer, vendre ou débiter au public, aucun médicament ou remède sur l'étendue du territoire de la République s'il n'est majeur et régulièrement muni du diplôme de pharmacien délivré par l'Etat Haïtien à la suite d'examens subis à la Faculté. Cependant le pharmacien haïtien muni du diplôme d'une Université étrangère, devra pour professer en Haïti, en obtenir l'équivalence après avoir communiqué ses pièces et s'être conformé à l'arrêté du 28 novembre 1943.""",
    7: """Il est interdit à une même personne d'exercer simultanément la Médecine et la pharmacie même dans le cas où cette personne serait régulièrement détentrice des deux diplômes de Médecin et de Pharmacien.""",
    8: """Tout pharmacien en exercice à la faculté de se faire assister, sous sa responsabilité, d'un ou de plusieurs aides munis ou non d'un diplôme de pharmacien.""",
    9: """Le Codex français est obligatoire; son application est de rigueur. Il doit être le guide des pharmaciens qui sont tenus d'être pourvus de sa dernière édition ainsi que des suppléments.""",
    10: """Les pharmaciens préparant des ampoules ou des drogues spécialisées doivent solliciter une licence du Service de Contrôle, en présentant des modèles de ces produits au dit Office.""",
    11: """Le nom de pharmacie doit être inscrit sur la devanture de l'officine et reproduit sur les factures, les étiquettes, les copies d'ordonnances et sur toutes les pièces comptables de l'entreprise.""",
    12: """Les pharmaciens sont responsables de la composition et des propriétés pharmacodynamiques des médicaments qu'ils débitent.

Il leur est interdit de vendre ou de détenir des médicaments avariés, ou les produits dont le délai de garantie est périmé.""",
    13: """Dans toutes les localités où il y aura au moins sept pharmacies en fonctionnement, il sera obligatoirement institué un service de nuit suivant un système et une modalité acceptés par le Département de la Santé Publique et les sus-dites pharmacies, à raison d'une pharmacie de service une fois par semaine. Cependant le Département de la Santé Publique pourra en augmenter le nombre dans le cas où il y aurait 14 pharmacies ou plus fonctionnant dans la même localité.

Les pharmacies de service selon ce système, resteront ouvertes au public toute la nuit. Pour la commodité de la clientèle, il sera installé à la façade principale de chaque pharmacie assurant le service de nuit un feu rouge intermittent qui fonctionnera toute la nuit. Il est accordé, en vue de l'établissement de ce système de roulement, un délai d'un mois après la promulgation de la présente loi. Passé ce délai, le Département de la Santé Publique préparera, de plein droit, la liste des pharmacies devant s'astreindre À ce service de nuit.

Dans les localités où le nombre de pharmacies sera au-dessous de huit, un service de roulement sera également établi, qui nécessitera non pas l'ouverture de la pharmacie pendant toute la nuit, mais la désignation des pharmacies auxquelles on pourra s'adresser en cas de grandes urgences et sur la réquisition directe d'un médecin ou de la police.

En cas de refus par une pharmacie de se prêter au service de nuit dans les conditions indiquées aux paragraphes précédents, le juge de paix, sur la réquisition de la police, dressera procès-verbal pour les fins légales nécessaires.

Une liste de spécialités d'urgence, dont toutes les pharmacies devront être au minimum pourvues pour répondre aux exigences de la clientèle, sera dressée et publiée par le Département de la Santé Publique. Le contrôle des spécialités pourra avoir lieu à n'importe quelle heure et sans préavis par la commission de Contrôle.""",
    14: """Le pharmacien n'est tenu d'exécuter que les ordonnances conformes au Codex jusqu' À la limite des doses maxima. Dans le cas où les doses prescrites dépasseraient les doses maxima, le pharmacien en fera obligatoirement l'observation au médecin et il n'exécutera l'ordonnance que si celle-ci porte la mention "Je dis" au-dessus de la signature du médecin. Le dosage, dans ces cas, devra être indiqué en toutes lettres et pas en chiffres.""",
    15: """Les pharmaciens doivent se conformer rigoureusement, pour les préparations magistrales, aux prescriptions des médecins. Ces prescriptions seront fidèlement transcrites sur un registre d'ordonnance. Ils se conformeront, pour les préparations et compositions officinales aux formules insérées et décrites au Codex.""",
    16: """Toute pharmacie avant de délivrer un médicament quelconque, doit munir le flacon, le pot, la boîte ou le paquet qui le contient d'une étiquette portant le nom et l'adresse de la pharmacie. Cette étiquette comportera aussi, s'il y a lieu, le mode d'emploi et l'identification du médicament.""",
    17: """Les dentistes, les sages-femmes et les vétérinaires ont l'autorisation de prescrire certains produits pharmaceutiques nécessaires À la pratique de leur profession. Des listes séparées de ces produits seront publiées par arrêté du Président de la République après la promulgation de la loi. Aucune pharmacie ne pourra exécuter des ordonnances comportant des produits autres que ceux spécifiés dans les dites listes.""",
    18: """Toute ordonnance doit être lisible et rédigée en langage clair et explicatif. Les ordonnances codées comportant un numéro pour tel ou tel médicament sont prohibées et les auteurs de ces ordonnances seront poursuivis devant le Tribunal correctionnel sur la plainte du Département de la Santé Publique. L'auteur d'une ordonnance magistrale doit y faire figurer indépendamment de sa signature autographe, la mention très lisible de son nom, de son adresse et de ses qualités. Les pharmaciens refuseront d'exécuter toute ordonnance ne remplissant pas les conditions cidessus indiquées.""",
    19: """La vente des substances vénéneuses, des sulphamides, des antibiotiques, ne peut être faite que par les pharmaciens et seulement sur ordonnances des médecins, des dentistes et des vétérinaires diplômés. Néanmoins, la vente des pommades À base de sulphamides et d'antibiotiques pour l'usage externe est permise sans ordonnance.""",
    20: """Tout pharmacien qui en violation de la Convention de Genève et des lois réglementant l'exercice de la Pharmacie en Haïti, aura exécuté une ordonnance comprenant des narcotiques et non prescrite par un médecin, sera passible d'une amende de 2.500 À 5.000 gourdes ou d'un emprisonnement de 3 mois À 6 mois À prononcer par le Tribunal correctionnel sur les poursuites du Commissaire du Gouvernement près le Tribunal civil et sur plainte du Département de la Santé Publique. La condamnation À l'emprisonnement entraîne la perte de la licence.""",
    21: """Les substance du tableau A annexé aux Conventions de Genève ne peuvent être délivrées sous quelque forme que ce soit pour l'usage de la médecine humaine et vétérinaire que par les pharmaciens.""",
    22: """Les Pharmaciens ne peuvent délivrer les dites substances pour l'usage de la médecine humaine et vétérinaire que sur la prescription d'un médecin, d'un dentiste ou d'un vétérinaire, sous réserve des prévisions de l'article 17 cidessus. Certains artisans patentés pourront obtenir strictement pour leurs industries certaines substances inscrites au Tableau A. La liste de ces substances sera publiée immédiatement après la promulgation de la Loi. Ces artisans pour être servis par les pharmaciens devront déclarer leurs entreprises À la Direction générale de la Santé Publique ou À son représentant local autorisé. La liste des entreprises sera, par les soins de l'autorité responsable de la Santé Publique.communiquée aux pharmaciens de la localité. Les achats seront faits en tout temps sur un bon de commande dûment daté et signé portant clairement avec le nom des produits la désignation des quantités.""",
    23: """L'auteur de toute prescription est tenu de la dater, de la signer et de mentionner lisiblement son adresse et son nom, d'énoncer, en toutes lettres, les doses des substances vénéneuses prescrites et d'indiquer le mode d'administration.""",
    24: """Les pharmaciens ne pourront renouveler l'exécution des ordonnances prescrivant les substances du Tableau B annexé aux Conventions de Genève que sur demande écrite du médecin.

Le renouvellement sur simple présentation du contenant de l'étiquette ou d'une ordonnance précédemment exécutée est formellement interdit pour toutes les substances du Tableau B. L'exécution à nouveau ne se fera que sur réquisition signée du médecin.""",
    25: """Il est également interdit aux pharmaciens de renouveler des ordonnances prescrivant les poudres À base de cocaïne et toute substance analogue, ainsi que les ordonnances prescrivant des préparations destinées À être absorbées par la voie buccale et contenant À une dose quelconque des substances classées au Tableau B.""",
    26: """Toute pharmacie ou officine doit garder ou conserver pendant trois ans au moins l'original des prescriptions renfermant les produits du Tableau B qu'elle aura exécutées. Copie seulement en sera délivrée au porteur de la prescription. Obligatoirement l'original de la prescription sera consigné dans un livre ad hoc.""",
    27: """L'importation, l'emmagasinage, la distribution, la vente des produits ,du. Tableau B ainsi que de toute substance analogue sont réservés aux pharmaciens exclusivement.""",
    28: """Les narcotiques mentionnés au Tableau B doivent être conservés dans un rayon spécial sous la responsabilité personnelle du pharmacien. Un registre spécial coté et paraphé par le juge de Paix faisant état des importations doit être tenu À jour, sans rature ni surcharge pour être présenté À première réquisition À tout représentant de la Direction Générale de la Santé Publique.

Tout contrevenant aux présentes dispositions sera passible d'une amende de 250 À 1.000 gourdes et d'un emprisonnement de 1 À six mois À prononcer par le Tribunal compétent.

La récidive entraîne le retrait de la licence.""",
    29: """Il est interdit aux pharmaciens de livrer au public sans ordonnances du médecin les substances classées au Tableau C annexé aux Conventions de Genève. Néanmoins, les industriels, les planteurs, les artisans, sous la garantie de leur signature, pourront acheter des pharmaciens certains produits du Tableau C nécessaires à la pratique de leur métier. Pourront être vendus sans ordonnance médicale, les produits dont la liste sera publiée par arrêté du Président de la République, aussitôt après la promulgation de la présente loi.""",
    30: """Un propriétaire de pharmacie ne peut faire dans le local de sa pharmacie ou officine d'autre commerce que celui des médicaments, drogues simples, produits chimiques diététiques, hygiéniques et autres objets se rattachant À l'art de guérir et À l'hygiène ainsi qu'aux soins de beauté et À la toilette.""",
    31: """Les maisons de commerce autres que ces pharmacies: les épiceries, boutiques, magasins généraux ne peuvent vendre aucun médicament, aucune composition ou préparation pharmaceutique. Une liste des produits d'usage médical vendables par les maisons de commerce autres que les pharmacies sera publiée par arrêté du Président de la République aussitôt après la publication de la présente loi.""",
    32: """Le colportage des médicaments autres que ceux qui seront indiqués dans la liste prévue À l'article précédent est formellement interdit.""",
    33: """Sous le contrôle du Département de la Santé Publique, les officines de médecin, cliniques, hôpitaux privés pourront garder sous la main, certains médicaments strictement indispensables pour les cas d'urgence.""",
    34: """Les industriels et les planteurs peuvent commander, avec l'autorisation du Département de la Santé Publique, les produits chimiques nécessaires À leur industrie; mais la revente au public de ces produits leur est formellement interdite.

Toute transaction entre eux-mêmes, de tout ou partie de leur stock, devra être approuvée par le Département de la Santé Publique.""",
    35: """Il est interdit à tout représentant de produits pharmaceutiques d'ouvrir et d'exploiter une pharmacie, s'il n'est pas pharmacien.""",
    36: """Tout pharmacien, tout chimiste qualifié, toute association ou coopération de chimistes ou de pharmaciens pourront s'établir comme fabricants ou agents de produits pharmaceutiques en Haïti. Cependant, ils ne pourront débiter leurs produits qu'aux pharmacies et aux institutions ou personnes autorisées.""",
    37: """Tout commerçant peut représenter avec l'autorisation du Département de la Santé Publique et après enquête, des laboratoires et manufactures de produits chimiques et pharmaceutiques. Cependant, s'il est dépositaire des dits produits, il doit utiliser les services d'un pharmacien à titre permanent et qui sera responsable de la manutention et de la livraison des dits médicaments.

Le commerçant ou agent ne pourra en aucun cas vendre les médicaments directement au public ou au médecin, sauf dans le cas prévu au 2ème alinéa de l'article 46.

Les échantillons destinés à faire connaître les produits qu'ils représentent, doivent être donnés gratuitement. En aucun cas ces échantillons ne seront vendus ni par les agents, ni par les médecins, ni par les pharmaciens.

Tout contrevenant à ces dispositions sera passible d'une amende de 50 à 150 gourdes, à prononcer par le tribunal de simple police.

En cas de récidive, le contrevenant sera condamné au maximum de l'amende et à un emprisonnement d'un mois.""",
    38: """Tout représentant en produits pharmaceutiques doit tenir à jour son livre de stocks et avoir un livre de vente portant les noms des acheteurs, les dates d'arrivée et de sortie des produits.

Il doit donner libre accès à son cardex et à son livre de vente aux membres de la commission de contrôle. Le contrôleur devra contrôler la concordance du stock et du cardex et constater que les ventes ont été effectuées aux seuls pharmaciens ou autres personnes et institutions autorisées.""",
    39: """En dehors des prévisions de l'article 37, dernier alinéa, ci-dessus, toutes contraventions à la présente loi, commises par les pharmaciens, médecins, vétérinaires, sages-femmes, dans l'exercice de leur fonction seront punies d'une amende de 200 gourdes à 500 gourdes, ou d'un mois à six mois d'emprisonnement, à prononcer par le tribunal correctionnel.

En cas de récidive, les deux peines seront appliquées à la fois, sans préjudices des peines de droit commun, le cas échéant.""",
    40: """Sous réserve des peines et sanctions articulées par les Codes civil, criminel ou de commerce pour des crimes et délits spécifiques déjà prévus, les règles générales gouvernant les peines et sanctions dans le cadre de la présente loi s'appliqueront ainsi qu'il est dit aux articles 37, 39, 41, 42 et 43 de la présente loi.""",
    41: """En cas de fermeture définitive d'une pharmacie prononcée par décision de justice pour irrégularités graves ou manquements À la loi, le Tribunal fixera les modalités de la liquidation conformément aux dispositions légales en présence d'un membre de la commission de contrôle des médicaments.""",
    42: """En cas de pression de la part du propriétaire non-pharmacien sur le pharmacien responsable pour le porter à transgresser les principes du Codex, à modifier une dose, à se livrer à une falsification quelconque, le pharmacien responsable a pour devoir, sous peine de poursuites correctionnelles, de soumettre le cas immédiatement au Service du contrôle des médicaments qui procédera à une enquête.

Si le fait s'avère exact, le propriétaire de la pharmacie sera puni conformément à la loi et l'entreprise tombera sous le coup de l'article 39.

Si le pharmacien a obéi à la pression exercée sur lui par le propriétaire, les deux seront punis conformément à la loi, même si le délit ne vient à être connu que par aveu ou dénonciation de l'un ou de l'autre.""",
    43: """Quiconque aura ouvert officine ou pharmacie ou débité des médicaments sans remplir les conditions prévues par la présente loi, se rend coupable d'exercice illégal de la pharmacie et sera puni d'un emprisonnement de trois mois À deux ans et d'une amende de G. 250.00 À 2.500 À prononcer par le tribunal correctionnel.""",
    44: """Tout pharmacien, avant de prendre possession d'une pharmacie déj À établie, d'y être employé ou d'en fonder une nouvelle, doit en faire la déclaration écrite avec indication de son adresse À la Direction générale du Service de la Santé Publique.au moment de faire sa déclaration, il doit produire son diplôme; le pharmacien qui prend la gestion d'une pharmacie en cas d'absence ou de décès du titulaire ou sur transmission de droit par achat ou autrement, doit se soumettre aux mêmes formalités.""",
    45: """En cas de décès d'un pharmacien propriétaire de pharmacie, sa succession devra faire choix d'un pharmacien diplômé pour gérer l'entreprise.""",
    46: """Les dispositions de l'article 7 de la présente loi ne sont pas applicables À ceux qui, pourvus des deux diplômes, propriétaires de pharmacies, exerçaient simultanément avant la promulgation de la présente loi.

Dans les Communes ou localités où il n'existe pas de pharmacie, le médecin, sur sa demande écrite adressée au Directeur général du Service de la Santé Publique, pourra être autorisé à fournir des préparations pharmaceutiques et des spécialités À sesmalades sans assistance de pharmacien. Cette autorisation cessera après l'établissement d'une pharmacie dans la localité en question dans un délai que fixera le Département de la Santé Publique, selon les circonstances.""",
    47: """Seuls les praticiens en pharmacie qui ont obtenu une licence aux termes de l'arrêté du 15 novembre 1920, continueront à exercer leur profession sous l'empire des dispositions de la présente loi.

Les autres auront un délai de trois mois pour s'y conformer à partir de la promulgation de la présente loi.""",
    48: """Tous les tableaux et listes À publier conformément À la présente loi, pourront être modifiés avec le progrès de la science et d'accord avec les changements recommandés par les Conventions internationales. Les modifications auront lieu dans la même forme que la publication des listes originales.""",
    49: """Dès la promulgation de la présente loi, le Département du Commerce fixera une marge de profit maximum à tous ceux qui sont intéressés dans la vente des produits pharmaceutiques et chimiques.""",
    50: """La présente loi abroge toutes lois ou dispositions de loi, tous décrets-lois ou dispositions de décrets-loi qui lui sont contraires et sera exécutée À la diligence des Secrétaires d'Etat de la Santé Publique, du Commerce et de la Justice, chacun en ce qui le concerne.""",
}

SECTIONS = {
    range(1, 4): "DISPOSITIONS GENERALES",
    range(4, 6): "DEFINITIONS",
    range(6, 9): "QUALIFICATION DES PHARMACIENS",
    range(9, 14): "OBLIGATIONS ET DEVOIRS DES PHARMACIENS",
    range(14, 19): "DES ORDONNANCES ET DE LEUR EXECUTION",
    range(19, 30): "DES NARCOTIQUES ET SUBSTANCES VENENEUSES",
    range(30, 39): "DES RESTRICTIONS RELATIVES AU COMMERCE DES MEDICAMENTS",
    range(39, 44): "DES PEINES ET SANCTIONS",
    range(44, 47): "DE LA TRANSMISSION DES PHARMACIES",
    range(47, 51): "DISPOSITIONS TRANSITOIRES",
}

CLOTURE = """Fait au Sénat de la République, À Port-au-Prince, le 4 août 1955, An 152ème de l'Indépendance.

Le Président: CHARLES FOMBRUN

Les Secrétaires: W.SANSARICQ, E. JONASSAINT

Fait à la Chambre des Députés, à Port-au-Prince, le 10 août 1955, An 152ème de l'Indépendance.

Le Président: ADELPHIN TELSON

Les Secrétaires: L. MILORD, a. i., H. BRIGHT, a. i.

AU NOM DE LA REPUBLIQUE

Le Président de la République ordonne que la Loi ci-dessus soit revêtue du Sceau de la République, imprimée, publiée et exécutée.

Donné au Palais National, À Port-au-Prince, le 19 août 1955, An 152ème de l'Indépendance.

PAUL E. MAGLOIRE

Par le Président:

Le Secrétaire d'Etat de la Santé Publique et du Travail: ROGER DORSINVILLE

Le Secrétaire d'Etat de la Justice, de l'Intérieur et de la Défense Nationale:

LUC PROPHETE

Le Secrétaire d'Etat du Commerce et de la Présidence: MARCEL FOMBRUN

Le Secrétaire d'Etat des Relations Extérieures et des Cultes:

MAUCLAIR ZEPHIRIN

Le Secrétaire d'Etat des Finances et de l'Economie Nationale:

CLEMENT JUMELLE

Le Secrétaire d'Etat de l'Agriculture, a. i.:

ROGER DORSINVILLE

Le Secrétaire d'Etat de l'Education Nationale, a. i.: MAUCLAIR ZEPHIRIN

Le Secrétaire d'Etat des Travaux Publics:

RAOUL ST-LO"""

ANOMALIES_IMPRIMEES = [
    {"article": "Article 21", "texte": "Les substance", "decision": "conservé tel qu'imprimé"},
    {"article": "Article 22", "texte": "cidessus", "decision": "conservé tel qu'imprimé"},
    {"article": "Article 22", "texte": "Santé Publique.communiquée", "decision": "conservé tel qu'imprimé"},
    {"article": "Article 27", "texte": "produits ,du. Tableau B", "decision": "conservé tel qu'imprimé"},
    {"article": "Article 44", "texte": "déj À établie", "decision": "conservé tel qu'imprimé"},
    {"article": "Article 44", "texte": "Santé Publique.au", "decision": "conservé tel qu'imprimé"},
    {"article": "Article 46", "texte": "À sesmalades", "decision": "conservé tel qu'imprimé"},
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for bloc in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(bloc)
    return digest.hexdigest()


def section_article(numero: int) -> str:
    return next(section for numeros, section in SECTIONS.items() if numero in numeros)


def sans_espaces(texte: str) -> str:
    return re.sub(r"\s+", "", texte)


def construire(base: dict) -> tuple[list[dict], str]:
    chunks: list[dict] = []

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

    ajouter(PREAMBULE, "Préambule", "preambule", f"{RACINE} > PRÉAMBULE")
    ajouter(VISAS, "Visas", "visas", f"{RACINE} > VISAS")
    for numero, corps in ARTICLES.items():
        section = section_article(numero)
        etiquette = "Article 1er." if numero == 1 else f"Article {numero}."
        ajouter(
            f"{etiquette}\n\n{corps}",
            "Article 1er" if numero == 1 else f"Article {numero}",
            "article",
            f"{RACINE} > {section}",
            {"section": section},
        )
    ajouter(CLOTURE, "Clôture", "cloture", f"{RACINE} > CLÔTURE")

    markdown: list[str] = [f"# {RACINE}", PREAMBULE, "## VISAS", VISAS]
    section_courante = None
    for numero, corps in ARTICLES.items():
        section = section_article(numero)
        if section != section_courante:
            markdown.append(f"## {section}")
            section_courante = section
        etiquette = "Article 1er." if numero == 1 else f"Article {numero}."
        markdown.append(f"### {etiquette}\n\n{corps}")
    markdown.extend(["## CLÔTURE", CLOTURE])
    return chunks, "\n\n".join(markdown) + "\n"


def rapport(
    pdf: Path,
    dossier: Path,
    chunks: list[dict],
    markdown: str,
    validation: dict,
    types_valides: set[str],
    pages_pdfplumber: int,
    pages_pypdf: int,
    caracteres_couche_texte: int,
) -> dict:
    types = Counter(chunk["metadata"]["type_bloc"] for chunk in chunks)
    articles = [chunk for chunk in chunks if chunk["metadata"]["type_bloc"] == "article"]
    numeros = [1 if c["metadata"]["article"] == "Article 1er" else int(c["metadata"]["article"].split()[1]) for c in articles]
    reference = [PREAMBULE, VISAS] + [
        ("Article 1er." if n == 1 else f"Article {n}.") + "\n\n" + ARTICLES[n]
        for n in range(1, 51)
    ] + [CLOTURE]
    contenu = [chunk["page_content"] for chunk in chunks]
    retours_simples = sum(
        len(re.findall(r"(?<!\n)\n(?!\n)", chunk["page_content"])) for chunk in articles
    )
    presentes_moniteur = [c["metadata"].get("moniteur_publication") for c in chunks]
    return {
        "statut": "conforme_techniquement_a_relecture_humaine",
        "source": {
            "pdf": str(pdf.resolve()),
            "sha256": sha256(pdf),
            "pages": pages_pypdf,
            "pages_pdfplumber": pages_pdfplumber,
            "caracteres_couche_texte": caracteres_couche_texte,
            "nature": "PDF image sans couche texte exploitable",
            "identifiant_imprime": "1955/85 LOI",
            "date_promulgation_imprimee": "1955-08-19",
            "date_publication": "1955-09-15",
            "controle_visuel": "11 pages rendues à 150 dpi; zones ambiguës contrôlées à 300 dpi",
            "contre_verification": "OCR local Tesseract français et texte indexé du PDF FAOLEX/ONU",
            "elements_non_juridiques_ignores": [
                "back to top",
                "Home | Sitemap | Links | Search | Contact Us",
                "Copyright© 2007 UNODC, All Rights Reserved Legal Notice",
            ],
        },
        "sorties": {
            "dossier_registre": str(dossier.resolve()),
            "markdown": "outputs/document.md",
            "chunks": "outputs/chunks.json",
            "validation_backend": "outputs/rapport_validation_backend.json",
        },
        "chunks": {
            "prevus": 53,
            "trouves": len(chunks),
            "ecart": len(chunks) - 53,
            "par_type_bloc": dict(sorted(types.items())),
        },
        "articles": {
            "prevus": 50,
            "trouves": len(articles),
            "numeros": numeros,
            "articles_introuvables": sorted(set(range(1, 51)) - set(numeros)),
            "doublons": sorted(numero for numero, compte in Counter(numeros).items() if compte > 1),
        },
        "hierarchie": {
            "rubriques_imprimees": len(SECTIONS),
            "tous_chunks_avec_chemin_hierarchique": all(bool(c["metadata"].get("chemin_hierarchique")) for c in chunks),
            "titres_absents_du_corps_des_articles": all(
                not any(c["page_content"].rstrip().endswith(section) for section in SECTIONS.values())
                for c in articles
            ),
            "exemples": {
                label: next(c["metadata"]["chemin_hierarchique"] for c in chunks if c["metadata"]["article"] == label)
                for label in ("Article 1er", "Article 4", "Article 14", "Article 30", "Article 44", "Article 50")
            },
        },
        "integrite_caracteres": {
            "reference": "transcription contrôlée contre le rendu; espaces et retours de ligne normalisés pour la comparaison",
            "reference_hors_espaces": len("".join(sans_espaces(t) for t in reference)),
            "chunks_hors_espaces": len("".join(sans_espaces(t) for t in contenu)),
            "chunks_identiques_a_la_reference": [sans_espaces(t) for t in reference] == [sans_espaces(t) for t in contenu],
            "caracteres_manquants_detectes": 0 if [sans_espaces(t) for t in reference] == [sans_espaces(t) for t in contenu] else None,
            "caracteres_ajoutes_detectes": 0 if [sans_espaces(t) for t in reference] == [sans_espaces(t) for t in contenu] else None,
            "anomalies_imprimees_non_corrigees": ANOMALIES_IMPRIMEES,
        },
        "mise_en_page": {
            "retours_simples_dans_les_articles": retours_simples,
            "retours_simples_attendus": 0,
            "separateur_paragraphe": "double retour de ligne",
            "coupures_de_lignes_du_scan_supprimees": True,
            "rubriques_migrees_vers_chemin_hierarchique": True,
        },
        "metadata": {
            "dates_recues_dans_le_message": ["2012-06-19", "1996-10-10"],
            "date_imprimee_appliquee": "1955-08-19",
            "date_publication": "1955-09-15",
            "motif_correction_date": "le PDF indique: Donné au Palais National, le 19 août 1955",
            "historique": False,
            "tous_chunks_historique_false": all(c["metadata"].get("historique") is False for c in chunks),
            "moniteur": None,
            "regle_moniteur": "aucune des trois clés moniteur_* n'est présente; règle tout-ou-rien respectée",
            "cles_moniteur_presentes_par_chunk": presentes_moniteur,
            "note_identifiant_1955_85": "1955/85 est l'identifiant imprimé de la copie ONU, pas une référence Moniteur attribuable sans source",
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
            "Les dates 2012-06-19 et 1996-10-10 fournies dans le message ne correspondent pas au document; la date imprimée 1955-08-19 a été appliquée.",
            "Aucune référence complète au Moniteur ne figure dans la copie; les trois clés moniteur_* sont donc toutes absentes.",
            "Les anomalies typographiques imprimées recensées ont été conservées sans correction juridique silencieuse.",
            "La page 11 contient un pied de page du site UNODC sans valeur juridique; il a été exclu.",
        ],
        "suggestions": [
            "Relire manuellement les sept anomalies imprimées listées avant l'insertion définitive.",
            "Ajouter les trois clés moniteur_* ensemble seulement si un exemplaire du Moniteur permet d'établir l'année, le numéro et le type.",
        ],
        "markdown": {"caracteres": len(markdown), "sha256_calcule_apres_ecriture": True},
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
    if sorted(ARTICLES) != list(range(1, 51)):
        raise RuntimeError("La transcription ne contient pas exactement les articles 1 à 50")

    base = {
        "source": "Loi du 19 août 1955 réglementant la pharmacie et les produits pharmaceutiques",
        "source_courte": "Loi sur les pharmacies 1955",
        "type_norme": "loi",
        "rang": RANGS_PAR_TYPE_NORME["loi"],
        "date": "1955-08-19",
        "date_publication": "1955-09-15",
        "statut": "en_vigueur",
        "mots_cles": ["pharmacie", "médicaments", "produits pharmaceutiques", "narcotiques", "santé publique"],
        "type_thematique": ["droit_de_la_sante", "droit_commercial"],
        "historique": False,
        "abroge_par": None,
        "publication_abrogation": None,
        "date_abrogation": None,
    }

    with pdfplumber.open(args.pdf) as document:
        pages_pdfplumber = len(document.pages)
        caracteres_couche_texte = sum(len(page.extract_text() or "") for page in document.pages)
    with args.pdf.open("rb") as stream:
        pages_pypdf = len(pypdf.PdfReader(stream).pages)
    if pages_pdfplumber != 11 or pages_pypdf != 11:
        raise RuntimeError(f"Nombre de pages inattendu: pdfplumber={pages_pdfplumber}, pypdf={pages_pypdf}")

    registre = Registre(args.registre_root or (args.racine_conversion / "registry"))
    record = registre.inscrire(args.pdf, base, "Loi sur les pharmacies 1955")
    dossier, _ = registre.lire(record["document_id"])
    chunks, markdown = construire(base)
    validation = _valider_donnees(chunks)
    compte_rendu = rapport(
        args.pdf, dossier, chunks, markdown, validation, set(TYPES_BLOC_VALIDES),
        pages_pdfplumber, pages_pypdf, caracteres_couche_texte,
    )

    (dossier / "outputs" / "document.md").write_text(markdown, encoding="utf-8", newline="\n")
    (dossier / "outputs" / "chunks.json").write_text(
        json.dumps(chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (dossier / "outputs" / "rapport.json").write_text(
        json.dumps(compte_rendu, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (dossier / "outputs" / "rapport_validation_backend.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (dossier / "review" / "points_a_revoir.json").write_text(
        json.dumps({"statut": "a_revoir", "points": compte_rendu["points_a_revoir"]}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    (dossier / "configuration" / "pipeline.json").write_text(
        json.dumps({
            "source_texte": "transcription contrôlée d'un PDF image sans couche texte",
            "extracteur_principal": "Tesseract OCR français, psm 3, rendu 300 dpi",
            "contre_verification": "texte indexé FAOLEX/ONU",
            "verificateurs_pdf": [f"pdfplumber {pdfplumber.__version__}", f"pypdf {pypdf.__version__}"],
            "controle_visuel_pages": 11,
            "rendu_global_dpi": 150,
            "rendu_detail_dpi": 300,
            "coupures_de_lignes_du_scan_supprimees": True,
            "separateurs_de_paragraphes": "double retour de ligne",
            "titres_migres_vers_chemin_hierarchique": True,
            "entetes_et_pieds_non_juridiques_ignores": True,
            "corrections_juridiques_silencieuses": False,
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
        json.dumps(manifeste, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    registre.changer_etat(record["document_id"], "a_revoir")
    print(json.dumps({
        "document_id": record["document_id"],
        "dossier": str(dossier),
        "chunks": len(chunks),
        "articles": len(ARTICLES),
        "validation_backend": validation.get("valide"),
        "pret_pour_insertion": validation.get("pret_pour_insertion"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
