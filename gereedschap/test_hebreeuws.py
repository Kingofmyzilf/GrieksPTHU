# -*- coding: utf-8 -*-
"""Controleert het Hebreeuws typen tegen de echte woordenlijst.

De proef: schrijf elk van de 410 woorden in Latijnse letters volgens het schema, en kijk of
je er hetzelfde Hebreeuwse woord uit terugkrijgt. Gaat dat ergens mis, dan is het schema
dubbelzinnig — en dan zou een student een goed antwoord fout gerekend krijgen.

Draaien:  py gereedschap/test_hebreeuws.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hebreeuws as H

# Hoe wij een letter zouden opschrijven. Eén voorkeur per letter; het schema accepteert er
# meer, maar voor de proef moet er één vaste keuze zijn.
SCHRIJF = {"א": "a", "ב": "b", "ג": "g", "ד": "d", "ה": "h", "ו": "w", "ז": "z",
           "ח": "ch", "ט": "tt", "י": "j", "כ": "k", "ל": "l", "מ": "m", "נ": "n",
           "ס": "s", "ע": "e", "פ": "p", "צ": "ts", "ק": "q", "ר": "r", "ש": "sj",
           "ת": "t"}


def main():
    woorden = H.laad_woorden()
    if not woorden:
        sys.exit("hebreeuws_woorden.json niet gevonden — draai eerst bouw_hebreeuws.py")

    mis, ongedekt = [], set()
    for w in woorden:
        doel = H.medeklinkers(w["hebreeuws"])
        if not doel:
            continue
        onbekend = [t for t in doel if t not in SCHRIJF]
        if onbekend:
            ongedekt.update(onbekend)
            continue
        getypt = "".join(SCHRIJF[t] for t in doel)
        terug = H.medeklinkers(H.naar_hebreeuws(getypt))
        if terug != doel:
            mis.append((w["nummer"], w["hebreeuws"], getypt, terug, doel))

    print(f"{len(woorden)} woorden heen en weer vertaald")
    if ongedekt:
        print("letters zonder toets:", " ".join(sorted(ongedekt)))
    for nummer, heb, getypt, terug, doel in mis[:20]:
        print(f"  {nummer:3d} {heb:12s} getypt {getypt:14s} -> {terug} in plaats van {doel}")
    print(f"{len(woorden) - len(mis)} goed, {len(mis)} mis")

    # Wat de app moet accepteren als de student het Hebreeuwse toetsenbord gebruikt.
    hebreeuws_direct = sum(1 for w in woorden
                           if H.vorm_ok(w["hebreeuws"], w["hebreeuws"]))
    print(f"{hebreeuws_direct} woorden worden ook goed gerekend als je ze in het "
          f"Hebreeuws intypt")

    # Twee woorden mogen niet op elkaar uitkomen: dan is het schema dubbelzinnig.
    per_toetsen = {}
    botsingen = []
    for w in woorden:
        doel = H.medeklinkers(w["hebreeuws"])
        if not doel or any(t not in SCHRIJF for t in doel):
            continue
        getypt = "".join(SCHRIJF[t] for t in doel)
        eerder = per_toetsen.get(getypt)
        if eerder and H.medeklinkers(eerder["hebreeuws"]) != doel:
            botsingen.append((eerder, w, getypt))
        per_toetsen[getypt] = w
    if botsingen:
        print(f"\ndubbelzinnig ({len(botsingen)}):")
        for a, b, getypt in botsingen[:10]:
            print(f"  '{getypt}' geeft zowel {a['hebreeuws']} als {b['hebreeuws']}")

    if mis or ongedekt:
        sys.exit(1)
    print("GESLAAGD")


if __name__ == "__main__":
    main()
