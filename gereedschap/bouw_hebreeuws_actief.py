# -*- coding: utf-8 -*-
"""Bouwt hebreeuws_actief.json: de rijtjes voor Actief Beheersen, uit de bijbeltekst zelf.

Voor het Grieks staat er een handgemaakte actief_beheersen.json in de repo. Voor het
Hebreeuws bestaat zoiets niet, en die met de hand overtypen zou betekenen dat ik
cursusmateriaal ga verzinnen. Dat hoeft ook niet: de WLC-tekst in 'Hele bijbel.xlsx' geeft
van élke woordvorm de ontleding, dus de rijtjes zijn eruit af te leiden. Wat je hier
oefent staat dus écht ergens, en bij elke cel weten we hoe vaak.

Drie dingen maken dat lastiger dan het klinkt:

  * De vormen in de tekst dragen cantillatietekens. אָמַ֣ר, אָמַר֙ en אָמַ֥ר zijn hetzelfde
    woord met drie verschillende melodie-accenten. Die horen bij de plaats in het vers,
    niet bij het rijtje, dus ze gaan eruit. De klinkertekens blijven staan — zónder die
    zou het perfectum niet van het participium te onderscheiden zijn.
  * Een vorm in de tekst kan er voorvoegsels bij hebben ('en hij zei'). De parsingkolom
    zegt dat met een pipe: 'Conj-w | V-Qal-Perf-3ms'. Alleen regels zonder pipe geven de
    kale vorm.
  * Niet elke cel van een rijtje staat in de bijbel. Een rijtje met gaten is nog steeds
    een goed rijtje om te leren, maar een rijtje met twéé cellen is dat niet; daar geldt
    een ondergrens voor.

Draaien:  py gereedschap/bouw_hebreeuws_actief.py
"""
import collections
import json
import os
import re
import sys
import unicodedata

import uitvoer

# Vóór de eerste print: anders valt Grieks of Hebreeuws om zodra de uitvoer
# naar een bestand of een pijp gaat in plaats van naar het scherm.
uitvoer.zet_utf8()

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHEET = os.path.join(REPO, "hebreeuws app", "Hele bijbel.xlsx")
WOORDEN = os.path.join(REPO, "hebreeuws_woorden.json")
UIT = os.path.join(REPO, "hebreeuws_actief.json")

# Wat er van een woordvorm overblijft. Klinkertekens (U+05B0–U+05BC) en de punten van
# sjin en sin (U+05C1–U+05C2) horen bij het woord; cantillatie (U+0591–U+05AF), de metheg
# (U+05BD) en het koppelteken maqqef (U+05BE) horen bij de voordracht van het vers.
WEG = re.compile("[֑-ֽ֯־ֿ׀׃-׆]")


def schoon(vorm):
    return unicodedata.normalize("NFC", WEG.sub("", str(vorm or "").strip()))


# De cellen van een rijtje, in de volgorde waarin je ze leert: eerst de derde persoon,
# want die is de kortste en de meest voorkomende, dan de tweede, dan de eerste.
PERSONEN = [("3ms", "3e m ev"), ("3fs", "3e v ev"), ("2ms", "2e m ev"), ("2fs", "2e v ev"),
            ("1cs", "1e ev"),
            ("3mp", "3e m mv"), ("3fp", "3e v mv"), ("3cp", "3e mv"),
            ("2mp", "2e m mv"), ("2fp", "2e v mv"), ("1cp", "1e mv")]

# Welke rijtjes we per werkwoord maken. De naam is wat de student erover leert; de code is
# hoe de WLC het tagt. ConsecImperf staat er bewust bij: de wajjiqtol is dé verhalende vorm
# van het Oude Testament en komt vaker voor dan het gewone imperfectum.
WW_RIJTJES = [
    ("Perfectum", "V-{stam}-Perf-{p}", PERSONEN),
    ("Imperfectum", "V-{stam}-Imperf-{p}", PERSONEN),
    # De wajjiqtol staat er als 'Conj-w | V-Qal-ConsecImperf-3ms' en niet zonder pipe: die
    # vorm bestáát niet zonder de ו ervoor. Bij de andere rijtjes is een voorvoegsel iets
    # wat erbij komt; hier hoort het erbij. Vandaar dat deze de pipe wél mag hebben.
    ("Imperfectum consecutivum (wajjiqtol)", "Conj-w | V-{stam}-ConsecImperf-{p}", PERSONEN),
    ("Imperativus", "V-{stam}-Imp-{p}",
     [("ms", "m ev"), ("fs", "v ev"), ("mp", "m mv"), ("fp", "v mv")]),
    ("Participium", "V-{stam}-Prtcpl-{p}",
     [("ms", "m ev"), ("fs", "v ev"), ("mp", "m mv"), ("fp", "v mv")]),
]

# De losse rijtjes die niet aan één werkwoord hangen. Per cel het label en de ontleedcode;
# de vorm halen we uit de tekst, net als bij de werkwoorden.
VASTE_RIJTJES = [
    ("Voornaamwoorden", "Persoonlijk voornaamwoord",
     [("1e ev", "Pro-1cs"), ("2e m ev", "Pro-2ms"), ("2e v ev", "Pro-2fs"),
      ("3e m ev", "Pro-3ms"), ("3e v ev", "Pro-3fs"),
      ("1e mv", "Pro-1cp"), ("2e m mv", "Pro-2mp"), ("2e v mv", "Pro-2fp"),
      ("3e m mv", "Pro-3mp"), ("3e v mv", "Pro-3fp")]),
    ("Voornaamwoorden", "Aanwijzend voornaamwoord",
     [("m ev", "Pro-ms"), ("v ev", "Pro-fs"), ("mv", "Pro-cp")]),
]

# Hoeveel cellen een rijtje minstens moet hebben om te oefenen. Onder de vier leer je geen
# rijtje maar een handvol losse vormen, en daar is de woordenschat voor.
MINIMUM = 4
# Hoe vaak een vorm minstens in de tekst moet staan om als de vorm van die cel te gelden.
# Eén losse plaats kan een schrijffout of een uitzondering zijn.
DREMPEL = 2


def lees_vormen():
    """strong -> ontleedcode -> vorm -> hoe vaak, plus waar hij voor het eerst staat."""
    import openpyxl
    wb = openpyxl.load_workbook(SHEET, read_only=True, data_only=True)
    ws = wb["Hebreeuws"]
    per = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    los = collections.defaultdict(collections.Counter)
    plaats = {}
    vers = ""
    for rij in ws.iter_rows(min_row=2, values_only=True):
        vorm, parsing, strong, verwijzing = rij[6], rij[9], rij[11], rij[13]
        if verwijzing and str(verwijzing).strip():
            vers = str(verwijzing).strip()
        if not (vorm and parsing):
            continue
        code = str(parsing).strip()
        # Een pipe betekent dat er voorvoegsels aan zitten; dan is dit niet de kale vorm.
        # De wajjiqtol is de uitzondering: die bestáát alleen mét de ו, dus die code laten
        # we heel en slaan we op zoals hij is.
        if "|" in code and "ConsecImperf" not in code:
            continue
        v = schoon(vorm)
        if not v:
            continue
        plaats.setdefault((code, v), vers)
        los[code][v] += 1
        if strong:
            per[str(strong).strip()][code][v] += 1
    return per, los, plaats


def cel(label, vorm, aantal, sleutel, vers, toelichting):
    return {"label": label, "vorm": vorm, "id": sleutel, "stam": "", "uitgang": "",
            "aantal": aantal, "vers": vers, "toelichting": toelichting}


def _slug(tekst):
    return re.sub(r"[^0-9a-z]+", "_", str(tekst).lower()).strip("_")


def affixen(cellen):
    """Per cel het voorvoegsel en de uitgang, gemeten tegen de rest van het rijtje.

    Het Hebreeuwse werkwoord vervoegt met voorvoegsels én met uitgangen — het imperfectum
    doet allebei tegelijk (תִּכְתְּבִי is ת + stam + י). Het Grieks heeft daar alleen een
    uitgang voor nodig; hier zijn het er twee, en dat is geen afwijking maar de taal.

    Wat het rijtje deelt is de stam. Die vinden we als het langste stuk dat in elke vorm
    voorkomt op dezelfde manier: eerst het gemeenschappelijke begin eraf, dan het
    gemeenschappelijke eind, en wat dan bij elke cel overblijft is het affix."""
    vormen = [c["vorm"] for c in cellen]
    if len(vormen) < 2:
        return
    # De medeklinkers zijn de stam; klinkertekens veranderen juist per cel.
    def med(t):
        return "".join(x for x in t if "א" <= x <= "ת")

    kernen = [med(v) for v in vormen]
    # het langste stuk dat in alle kernen zit
    kort = min(kernen, key=len)
    stam = ""
    for lengte in range(len(kort), 1, -1):
        for start in range(0, len(kort) - lengte + 1):
            kandidaat = kort[start:start + lengte]
            if all(kandidaat in k for k in kernen):
                stam = kandidaat
                break
        if stam:
            break
    if not stam:
        return
    for c in cellen:
        kern = med(c["vorm"])
        i = kern.find(stam)
        c["stam"] = stam
        c["voorvoegsel"] = kern[:i]
        c["uitgang"] = kern[i + len(stam):]


def bouw():
    if not os.path.exists(SHEET):
        sys.exit(f"{SHEET} niet gevonden — die staat niet in git (42 MB).")
    woorden = json.load(open(WOORDEN, encoding="utf-8"))
    print("bijbeltekst inlezen…")
    per, los, plaats = lees_vormen()

    db = {}
    tel = collections.Counter()

    def zet(niveau, categorie, paradigma, cellen, minimum=MINIMUM):
        if len(cellen) < minimum:
            tel["te klein"] += 1
            return
        affixen(cellen)
        db.setdefault(niveau, {}).setdefault(categorie, {})[paradigma] = cellen
        tel["rijtjes"] += 1
        tel["cellen"] += len(cellen)

    # ---------------------------------------------------------------- werkwoorden
    stamnamen = {"Qal": "Qal", "Nifal": "Nifal", "Piel": "Piel",
                 "Hifil": "Hifil", "Hitpael": "Hitpael"}
    for w in sorted(woorden, key=lambda x: -(x.get("frequentie") or 0)):
        strong = str(w.get("strong") or "")
        if not strong or not w.get("stammen"):
            continue
        niveau = f"Hebreeuws {int(w.get('les', 1) or 1)}"
        for naam_stam in w["stammen"]:
            code_stam = stamnamen.get(naam_stam)
            if not code_stam:
                continue
            for rijtje, sjabloon, personen in WW_RIJTJES:
                cellen = []
                for p, label in personen:
                    code = sjabloon.format(stam=code_stam, p=p)
                    keuzes = per[strong].get(code) or {}
                    if not keuzes:
                        continue
                    vorm, aantal = keuzes.most_common(1)[0]
                    if aantal < DREMPEL:
                        continue
                    cellen.append(cel(
                        label, vorm, aantal, f"heb_{strong}_{_slug(code)}",
                        plaats.get((code, vorm), ""),
                        f"{aantal}× in de Tenach"))
                zet(niveau, f"Werkwoord ({naam_stam})",
                    f"{w['hebreeuws']} — {rijtje}", cellen)

    # ---------------------------------------------------------------- vaste rijtjes
    for categorie, paradigma, regels in VASTE_RIJTJES:
        cellen = []
        for label, code in regels:
            keuzes = los.get(code) or {}
            if not keuzes:
                continue
            vorm, aantal = keuzes.most_common(1)[0]
            if aantal < DREMPEL:
                continue
            cellen.append(cel(label, vorm, aantal, f"heb_{_slug(code)}",
                              plaats.get((code, vorm), ""), f"{aantal}× in de Tenach"))
        # Deze rijtjes staan bovenaan met de hand opgeschreven, dus hun lengte is een keuze
        # en geen toeval: het aanwijzend voornaamwoord heeft er nu eenmaal drie.
        zet("Hebreeuws 1", categorie, paradigma, cellen, minimum=3)

    with open(UIT, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=1)
    print(f"{tel['rijtjes']} rijtjes met {tel['cellen']} cellen naar "
          f"{os.path.basename(UIT)} ({tel['te klein']} rijtjes te klein, minder dan "
          f"{MINIMUM} cellen)")
    for niveau, categorieen in db.items():
        for categorie, paradigmas in categorieen.items():
            print(f"  {niveau} · {categorie}: {len(paradigmas)} rijtjes")


if __name__ == "__main__":
    bouw()
