# -*- coding: utf-8 -*-
"""Zet de hele Tenach in de repo: per boek één ingepakt bestand.

Het bronbestand 'Hele bijbel.xlsx' is 42 MB en staat daarom in .gitignore. Dat is prima om
mee te werken, maar het betekent ook dat de app alleen kan lezen wat er van tevoren uit
gehaald is — tot nu toe duizend uitgezochte verzen. Dit script haalt de héle tekst eruit,
in een vorm die wél in git kan.

Waarom per boek en niet één bestand. Gemeten:

    alles plat, zoals hebreeuws_lezen.json      12,7 MB
    alles plat, ingepakt                         2,0 MB
    met tabellen, elke vorm één keer             5,5 MB
    met tabellen, ingepakt                       1,5 MB

Eén ingepakt bestand van 1,5 MB is het kleinst, maar dan moet de app bij het openen van
één vers de hele Tenach uitpakken en in het geheugen zetten. Op de gratis laag van Render
is 512 MB alles wat er is. Per boek is samen wat groter maar laadt de app alleen wat je
leest: het grootste boek is Psalmen met 170 kB ingepakt.

Draaien:  py gereedschap/bouw_tenach.py
"""
import collections
import gzip
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
MAP = os.path.join(REPO, "tenach")

# De zangtekens en de meteg gaan eruit; klinkertekens, maqaf en sof pasuq blijven. Zelfde
# grens als in bouw_hebreeuws_lezen.py: U+05B0 en verder zijn de klinkers, en die moet je
# houden — zonder die is het geen leesbare tekst maar een rij consonanten.
WEG = set(range(0x0591, 0x05B0)) | {0x05BD}

# De boeken zoals de spreadsheet ze noemt, met de Nederlandse naam erbij. De volgorde is
# die van de Tenach zoals hij in het bestand staat.
NEDERLANDS = {
    "Genesis": "Genesis", "Exodus": "Exodus", "Leviticus": "Leviticus",
    "Numbers": "Numeri", "Deuteronomy": "Deuteronomium", "Joshua": "Jozua",
    "Judges": "Richteren", "Ruth": "Ruth", "1 Samuel": "1 Samuël",
    "2 Samuel": "2 Samuël", "1 Kings": "1 Koningen", "2 Kings": "2 Koningen",
    "1 Chronicles": "1 Kronieken", "2 Chronicles": "2 Kronieken", "Ezra": "Ezra",
    "Nehemiah": "Nehemia", "Esther": "Ester", "Job": "Job", "Psalm": "Psalmen",
    "Proverbs": "Spreuken", "Ecclesiastes": "Prediker",
    "Song of Solomon": "Hooglied", "Isaiah": "Jesaja", "Jeremiah": "Jeremia",
    "Lamentations": "Klaagliederen", "Ezekiel": "Ezechiël", "Daniel": "Daniël",
    "Hosea": "Hosea", "Joel": "Joël", "Amos": "Amos", "Obadiah": "Obadja",
    "Jonah": "Jona", "Micah": "Micha", "Nahum": "Nahum", "Habakkuk": "Habakuk",
    "Zephaniah": "Sefanja", "Haggai": "Haggai", "Zechariah": "Zacharia",
    "Malachi": "Maleachi",
}


def schoon(vorm):
    return "".join(t for t in str(vorm or "").strip() if ord(t) not in WEG)


def bestandsnaam(boek):
    """'1 Samuel' -> '1_Samuel'. Geen spaties of bijzondere tekens in bestandsnamen: die
    hebben bij de Hebreeuwse PDF's al genoeg problemen gegeven."""
    return re.sub(r"[^0-9A-Za-z]+", "_", boek).strip("_")


def main():
    if not os.path.exists(SHEET):
        sys.exit(f"{SHEET} niet gevonden — die staat niet in git (42 MB).")
    print("bijbeltekst inlezen…")
    import openpyxl
    wb = openpyxl.load_workbook(SHEET, read_only=True, data_only=True)
    ws = wb["Hebreeuws"]

    per_boek = collections.OrderedDict()
    huidig = {}
    vers = ""
    for rij in ws.iter_rows(min_row=2, values_only=True):
        if str(rij[5] or "").strip().lower() != "hebrew":
            continue
        if rij[13] and str(rij[13]).strip():
            vers = str(rij[13]).strip()
        if not rij[6]:
            continue
        boek = re.sub(r"\s+\d+:\d+$", "", vers)
        # rij[1] is 'Heb Sort'. Nodig: het bestand staat in de Engelse woordvolgorde.
        huidig.setdefault(boek, collections.OrderedDict()).setdefault(vers, []).append(
            (int(rij[1] or 0), schoon(rij[6]), str(rij[11] or "").strip(),
             str(rij[9] or "").strip()))
    per_boek = huidig

    os.makedirs(MAP, exist_ok=True)
    # Eerst opruimen: een boek dat uit de bron verdwijnt moet niet blijven rondslingeren.
    for oud in os.listdir(MAP):
        if oud.endswith(".json.gz"):
            os.remove(os.path.join(MAP, oud))

    index, totaal_groot, totaal_woorden = [], 0, 0
    for boek, verzen in per_boek.items():
        stuk = []
        for ref, woorden in verzen.items():
            woorden.sort(key=lambda w: w[0])
            stuk.append({"v": ref.rsplit(" ", 1)[-1],      # alleen 'hoofdstuk:vers'
                         "w": [[w[1], w[2], w[3]] for w in woorden]})
        naam = bestandsnaam(boek) + ".json.gz"
        pad = os.path.join(MAP, naam)
        ruw = json.dumps(stuk, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with gzip.open(pad, "wb", compresslevel=9) as f:
            f.write(ruw)
        groot = os.path.getsize(pad)
        woorden_n = sum(len(v["w"]) for v in stuk)
        totaal_groot += groot
        totaal_woorden += woorden_n
        hoofdstukken = sorted({int(v["v"].split(":")[0]) for v in stuk})
        index.append({"boek": boek, "nl": NEDERLANDS.get(boek, boek), "bestand": naam,
                      "verzen": len(stuk), "woorden": woorden_n,
                      "hoofdstukken": hoofdstukken[-1] if hoofdstukken else 0})

    with open(os.path.join(MAP, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)

    print(f"{len(index)} boeken, {sum(b['verzen'] for b in index)} verzen, "
          f"{totaal_woorden} woordvormen")
    print(f"samen {totaal_groot / 1048576:.2f} MB ingepakt")
    print("de vijf grootste:")
    for b in sorted(index, key=lambda b: -b["woorden"])[:5]:
        pad = os.path.join(MAP, b["bestand"])
        print(f"  {b['nl']:16s} {b['verzen']:5d} verzen, {b['woorden']:6d} woorden, "
              f"{os.path.getsize(pad)/1024:6.0f} kB")


if __name__ == "__main__":
    main()
