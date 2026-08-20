# -*- coding: utf-8 -*-
"""Bouwt hebreeuws_lezen.json: verzen uit de Tenach die je met deze woordenschat kunt lezen.

Het punt van 428 woorden leren is dat je een vers openslaat en het snapt. Dit script zoekt
uit welke verzen dat zijn en zet ze klaar, woord voor woord, met bij elk woord het
Strong-nummer — dan kan de app de betekenis erbij zoeken uit de woordenlijst die je al hebt.

Er komt geen vertaling van het vers in. Dat is een keuze: met een vertaling ernaast lees je
de vertaling. Zonder vertaling, maar met de betekenis van elk woord binnen handbereik, moet
je het zelf in elkaar zetten — en dat is precies de vaardigheid. Zo doet Ontleden het bij
het Grieks ook.

Wat er gemeten is voordat dit gebouwd werd, over 22.877 verzen:

    van élk woord de betekenis           874 verzen
    90–99% van de woorden                1395
    80–89%                               4738

Alles meenemen zou 2 MB kosten en de deploytak is nu 1,7 MB in totaal. Daarom een selectie:
de verzen waar je élk woord kent, en daarna de bijna-volledige, verdeeld over de boeken —
zodat het niet alleen Psalmen wordt.

Draaien:  py gereedschap/bouw_hebreeuws_lezen.py
"""
import collections
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

import uitvoer

uitvoer.zet_utf8()

SHEET = os.path.join(REPO, "hebreeuws app", "Hele bijbel.xlsx")
WOORDEN = os.path.join(REPO, "hebreeuws_woorden.json")
UIT = os.path.join(REPO, "hebreeuws_lezen.json")

# Zoveel verzen nemen we mee. Bij duizend verzen is het bestand ongeveer een halve
# megabyte, en dat is te verantwoorden naast de 1,7 MB die de app nu weegt.
HOEVEEL = 1000
# Korter dan vier woorden is geen vers om te lezen; langer dan veertien past niet op een
# telefoonscherm zonder dat je moet schuiven.
KORT, LANG = 4, 14
# Zoveel verzen per bijbelboek, zodat het niet allemaal Psalmen wordt: daar staan de
# kortste verzen, dus die zouden de hele lijst opeten.
PER_BOEK = 60

# De zangtekens gaan eruit: die horen bij de voordracht en maken het lezen op een klein
# scherm alleen onrustiger. De klinkertekens blijven staan — zonder die is het geen
# leesbare tekst maar een rij consonanten.
#
# Let op de grens. U+0591 t/m U+05AF zijn de zangtekens; U+05B0 t/m U+05BC zijn juist de
# klinkers en de dagesj. Een bereik dat tot U+05BD doorloopt haalt dus precies weg wat je
# wilde houden — en dat deed het hier ook: het eerste vers kwam er als 'כל עדת ישׂראל' uit
# in plaats van 'כָּל־עֲדַת יִשְׂרָאֵל'.
def zonder_zangtekens(vorm):
    """Alleen de cantillatie en de meteg eraf. Maqaf en sof pasuq blijven: die horen bij
    de tekst zoals je hem leest."""
    return "".join(t for t in str(vorm or "").strip()
                   if not (0x0591 <= ord(t) <= 0x05AF or ord(t) == 0x05BD))


def boek(ref):
    """'Genesis 1:1' -> 'Genesis'. Een cijfer vooraan hoort bij de naam (1 Samuel)."""
    return re.sub(r"\s+\d+:\d+$", "", str(ref)).strip()


def lees_verzen():
    """Per vers de woorden: (vorm, strong, parsing)."""
    import openpyxl
    wb = openpyxl.load_workbook(SHEET, read_only=True, data_only=True)
    ws = wb["Hebreeuws"]
    verzen = collections.OrderedDict()
    vers = ""
    for rij in ws.iter_rows(min_row=2, values_only=True):
        if str(rij[5] or "").strip().lower() != "hebrew":
            continue
        if rij[13] and str(rij[13]).strip():
            vers = str(rij[13]).strip()
        vorm, parsing, strong = rij[6], rij[9], rij[11]
        if not vorm:
            continue
        # rij[1] is 'Heb Sort'. Nodig, en niet vanzelfsprekend: het bestand staat in de
        # Engelse woordvolgorde. 2 Samuel 22:4 komt er dan als 'אֶקְרָא יְהוָה מְהֻלָּל' uit
        # terwijl de Hebreeuwse tekst met מְהֻלָּל begint. Een vers in de verkeerde volgorde
        # is erger dan geen vers.
        verzen.setdefault(vers, []).append(
            (int(rij[1] or 0),
             [zonder_zangtekens(vorm),
              str(strong or "").strip(),
              str(parsing or "").strip()]))
    return {ref: [w for _sorteer, w in sorted(woorden, key=lambda p: p[0])]
            for ref, woorden in verzen.items()}


def main():
    if not os.path.exists(SHEET):
        sys.exit(f"{SHEET} niet gevonden — die staat niet in git (42 MB).")
    ken = {str(w.get("strong") or "") for w in json.load(open(WOORDEN, encoding="utf-8"))}
    ken.discard("")
    print(f"{len(ken)} Strong-nummers in de woordenlijst. Bijbeltekst inlezen…")
    verzen = lees_verzen()
    print(f"{len(verzen)} verzen gelezen.")

    kandidaten = []
    for ref, woorden in verzen.items():
        if not KORT <= len(woorden) <= LANG:
            continue
        bekend = sum(1 for _v, s, _p in woorden if s in ken)
        deel = bekend / len(woorden)
        if deel < 0.9:
            continue
        # Sorteren op: eerst de volledige, dan de kortste. Zo begint de app met het
        # makkelijkste vers dat er is.
        kandidaten.append((-deel, len(woorden), ref, woorden))
    kandidaten.sort(key=lambda k: (k[0], k[1], k[2]))
    print(f"{len(kandidaten)} verzen met minstens 90% bekend en {KORT}–{LANG} woorden.")

    gekozen, per_boek = [], collections.Counter()
    for _min_deel, _n, ref, woorden in kandidaten:
        b = boek(ref)
        if per_boek[b] >= PER_BOEK:
            continue
        per_boek[b] += 1
        gekozen.append({"vers": ref, "woorden": woorden})
        if len(gekozen) >= HOEVEEL:
            break

    with open(UIT, "w", encoding="utf-8") as f:
        json.dump(gekozen, f, ensure_ascii=False, separators=(",", ":"))
    groot = os.path.getsize(UIT) / 1024
    volledig = sum(1 for v in gekozen
                   if all(w[1] in ken for w in v["woorden"]))
    print(f"{len(gekozen)} verzen naar {os.path.basename(UIT)} ({groot:.0f} kB), "
          f"waarvan {volledig} waar élk woord in de lijst staat.")
    print(f"verdeeld over {len(per_boek)} boeken; de vijf grootste: "
          + ", ".join(f"{b} {n}" for b, n in per_boek.most_common(5)))


if __name__ == "__main__":
    main()
