# -*- coding: utf-8 -*-
"""Controleert hoe de Hebreeuwse betekenissen worden uitgelezen.

De gevallen hieronder komen allemaal uit de app zelf: dit zijn de keuzeknoppen en
antwoorden waarvan bleek dat ze iets weglieten of iets fout rekenden. De regels die eruit
volgden staan bij heb_groepen() in grieks_app.py.

Draaien:  py gereedschap/test_betekenis.py
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uitvoer

uitvoer.zet_utf8()

import grieks_motor as motor

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Deze functies stonden eerst in grieks_app.py, en dan moest dit bestand het stuk broncode
# eruit knippen en uitvoeren -- de app start namelijk de server zodra je hem importeert.
# Sinds de Streamlit-app ze ook nodig heeft staan ze in hebreeuws.py en kan het gewoon met
# een import. heb_goed krijgt de Nederlandse vergelijking van de motor mee.
import hebreeuws as H

NS = {
    "heb_uitleg": H.heb_uitleg,
    "heb_groepen": H.heb_groepen,
    "heb_betekenis": H.heb_betekenis,
    "heb_antwoorden": H.heb_antwoorden,
    "heb_volledig": H.heb_volledig,
    "heb_goed": lambda antwoord, w: H.heb_goed(antwoord, w, motor.check_betekenis),
}

# Wat er op de keuzeknop moet staan. Per woord: het nummer in de lijst, en wat we
# verwachten. Alle zeven kwamen naar boven door ze in de app tegen te komen.
KNOPPEN = [
    # בְּ — geen stamcode, dus de puntkomma scheidt hier niets grammaticaals: alles hoort
    # bij elkaar. Eerst stond er alleen 'in, op, bij'.
    (13, "in, op, bij, met, door, tegen"),
    # עַל — zelfde geval, drie segmenten die één rij betekenissen zijn. Het '(boven)' mag
    # blijven staan: dat vertelt je dat het zowel 'bovenop' als 'op' kan zijn. Voor het
    # nakijken gaat het eruit, voor het lezen niet.
    (49, "(boven)op, over, bij, tot, tegen, wegens"),
    # אֵת — de eerste groep is alleen uitleg tussen vierkante haken; die hoort niet op een
    # knop. De betekenis staat achter 'ii'.
    (6, "met, bij"),
    # אֲשֶׁר — de uitleg tussen haken eruit, de betekenissen erin.
    (3, "dat, toen, omdat, opdat, dat"),
    # אכל — hier scheidt de puntkomma wél iets: de stammen. De knop hoort de Qal te zijn.
    (11, "eten"),
]

# Wat er als getypt antwoord goed moet zijn. 'naar' bij לְ was fout omdat »iets toe«
# ertussen stond; 'op' bij עַל omdat het als '(boven)op' in de lijst staat.
ANTWOORDEN = [
    (38, "naar", True), (38, "tot", True), (38, "voor", True), (38, "zeggen", False),
    (49, "op", True), (49, "bovenop", True), (49, "wegens", True), (49, "onder", False),
    (13, "met", True), (13, "door", True), (13, "tegen", True), (13, "boven", False),
    (6, "met", True), (6, "bij", True),
    (11, "eten", True), (11, "voeden", True), (11, "gegeten worden", True),
    (12, "zeggen", True), (12, "denken", True), (12, "verklaren", True),
    (12, "gezegd worden", True), (12, "lopen", False),
    (3, "dat", True), (3, "omdat", True), (3, "opdat", True),
]

fouten = []


def kijk(wat, gekregen, verwacht):
    if gekregen != verwacht:
        fouten.append(wat)
        print(f"  MIS  {wat}\n       kreeg    {gekregen!r}\n       verwacht {verwacht!r}")
    else:
        print(f"  ok   {wat}")


def main():
    woorden = {w["nummer"]: w
               for w in json.load(open(os.path.join(REPO, "hebreeuws_woorden.json"),
                                       encoding="utf-8"))}

    print("--- wat er op de keuzeknop staat ---")
    for nummer, verwacht in KNOPPEN:
        w = woorden.get(nummer)
        if not w:
            fouten.append(f"woord {nummer} niet gevonden")
            continue
        kijk(f"{w['hebreeuws']}", NS["heb_betekenis"](w), verwacht)

    print("\n--- wat er als antwoord goed is ---")
    for nummer, antwoord, verwacht in ANTWOORDEN:
        w = woorden.get(nummer)
        if not w:
            continue
        kijk(f"{w['hebreeuws']:10s} '{antwoord}'", NS["heb_goed"](antwoord, w), verwacht)

    print("\n--- de hele lijst ---")
    leeg = [w for w in woorden.values() if not NS["heb_betekenis"](w)]
    print(f"  zonder betekenis:            {len(leeg)}")
    for w in leeg[:5]:
        print(f"    {w['nummer']} {w['hebreeuws']} | {w['nederlands'][:60]}")
    telang = [w for w in woorden.values() if len(NS["heb_betekenis"](w)) > 44]
    print(f"  knop langer dan 44 tekens:   {len(telang)}")
    for w in telang[:5]:
        print(f"    {w['nummer']} {w['hebreeuws']} | {NS['heb_betekenis'](w)}")
    haken = [w for w in woorden.values()
             if re.search(r"[\[\]»«]", NS["heb_betekenis"](w))]
    print(f"  nog haken op de knop:        {len(haken)}")
    for w in haken[:5]:
        print(f"    {w['nummer']} {w['hebreeuws']} | {NS['heb_betekenis'](w)}")
    codes = [w for w in woorden.values()
             if re.match(r"^(i{1,3}|G|N|D|Dp|H|Hp|Ht|tD|R|Rp)\b", NS["heb_betekenis"](w))]
    print(f"  nog een stamcode op de knop: {len(codes)}")
    for w in codes[:5]:
        print(f"    {w['nummer']} {w['hebreeuws']} | {NS['heb_betekenis'](w)}")
    eigen = [w for w in woorden.values()
             if not NS["heb_goed"](NS["heb_betekenis"](w), w)]
    print(f"  eigen knop niet goedgekeurd: {len(eigen)}")
    for w in eigen[:5]:
        print(f"    {w['nummer']} {w['hebreeuws']} | {NS['heb_betekenis'](w)}")

    fouten.extend(f"woord {w['nummer']} zonder betekenis" for w in leeg)
    fouten.extend(f"woord {w['nummer']} met haken op de knop" for w in haken)
    fouten.extend(f"woord {w['nummer']} met een code op de knop" for w in codes)
    fouten.extend(f"woord {w['nummer']} keurt eigen knop af" for w in eigen)

    print()
    if fouten:
        sys.exit(f"{len(fouten)} mis")
    print("GESLAAGD")


if __name__ == "__main__":
    main()
