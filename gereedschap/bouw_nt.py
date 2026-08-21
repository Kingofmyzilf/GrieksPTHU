# -*- coding: utf-8 -*-
"""Zet de Griekse bijbeltekst om naar één ingepakt bestand per boek.

De tekst stond in twee bestanden van 15,7 en 15,8 MB. Dat is niet nodig, en het maakt het
klonen van de repo zwaar. Gemeten:

    twee losse bestanden, zoals ze waren        31,5 MB
    zonder het ongebruikte veld parsing_code    30,4 MB
    één bestand, zonder witruimte               29,4 MB
    één bestand, ingepakt                        3,2 MB
    per boek ingepakt, bij elkaar                3,2 MB

Per boek is even groot als één bestand, maar het laat de app in de toekomst één boek
inlezen in plaats van alle 27 — het grootste is Lucas met 473 kB.

Wat eruit gaat is 'parsing_code'. Dat veld staat in geen enkel python-bestand van de repo,
en de leesbare tegenhanger 'parsing_info' wordt juist overal gebruikt. Van de 686 codes
hebben er precies twee meer dan één uitleg, dus het is ook niets dat je nodig zou hebben om
die uitleg terug te vinden.

Draaien:  py gereedschap/bouw_nt.py

Daarna kunnen bijbel_nt_deel1.json en bijbel_nt_deel2.json uit git; laad_bijbel_db() leest
ze nog wel als ze er staan, zodat een oude werkkopie blijft werken.
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

BRONNEN = ["bijbel_nt.json", "bijbel_nt_deel1.json", "bijbel_nt_deel2.json"]
MAP = os.path.join(REPO, "nt")
# Dit veld gaat eruit: het wordt nergens gelezen.
WEG = ("parsing_code",)


def boek_van(ref):
    """'Matthew 1:1' -> 'Matthew'. Een cijfer vooraan hoort bij de naam (1 Corinthians)."""
    return re.sub(r"\s*\d+[:.]\d+\s*$", "", str(ref)).strip()


def bestandsnaam(boek):
    return re.sub(r"[^0-9A-Za-z]+", "_", boek).strip("_")


def main():
    bijbel = {}
    gelezen = []
    for naam in BRONNEN:
        pad = os.path.join(REPO, naam)
        if os.path.exists(pad):
            with open(pad, encoding="utf-8") as f:
                bijbel.update(json.load(f))
            gelezen.append(naam)
    if not bijbel:
        sys.exit("Geen bijbel_nt*.json gevonden om uit te lezen.")
    print(f"{len(bijbel)} verzen gelezen uit {', '.join(gelezen)}")

    per_boek = collections.OrderedDict()
    weggelaten = 0
    for ref, woorden in bijbel.items():
        schoon = []
        for w in woorden:
            nieuw = {k: v for k, v in w.items() if k not in WEG}
            weggelaten += len(w) - len(nieuw)
            schoon.append(nieuw)
        per_boek.setdefault(boek_van(ref), {})[ref] = schoon
    print(f"{weggelaten} keer het veld {WEG[0]} weggelaten")

    os.makedirs(MAP, exist_ok=True)
    for oud in os.listdir(MAP):
        if oud.endswith(".json.gz"):
            os.remove(os.path.join(MAP, oud))

    index, totaal = [], 0
    for boek, verzen in per_boek.items():
        naam = bestandsnaam(boek) + ".json.gz"
        ruw = json.dumps(verzen, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
        with gzip.open(os.path.join(MAP, naam), "wb", compresslevel=9) as f:
            f.write(ruw)
        groot = os.path.getsize(os.path.join(MAP, naam))
        totaal += groot
        index.append({"boek": boek, "bestand": naam, "verzen": len(verzen),
                      "woorden": sum(len(w) for w in verzen.values())})

    with open(os.path.join(MAP, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)

    print(f"{len(index)} boeken naar nt/, samen {totaal / 1048576:.2f} MB ingepakt")
    for b in sorted(index, key=lambda b: -b["woorden"])[:5]:
        pad = os.path.join(MAP, b["bestand"])
        print(f"  {b['boek']:16s} {b['verzen']:5d} verzen, {b['woorden']:6d} woorden, "
              f"{os.path.getsize(pad)/1024:6.0f} kB")


if __name__ == "__main__":
    main()
