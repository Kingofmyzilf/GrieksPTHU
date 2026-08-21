# -*- coding: utf-8 -*-
"""Controleert of de tabbladen van de Streamlit-app goed aan elkaar hangen.

Dit is de plek waar een verbouwing stilletjes misgaat. De app koppelt drie dingen aan
elkaar op positie:

    TAB_KEUZE        de tabbladen in de volgorde waarin ze op het scherm staan
    _MENU_SLEUTELS   dezelfde tabbladen in de volgorde waarin de code ze afhandelt
    menu[i]/_TOON[i] de blokken zelf, die op index staan

Klopt één van die drie niet, dan komt de inhoud van het ene tabblad onder de kop van het
andere te staan, of valt de app om op een index die niet bestaat. En dat zie je niet aan de
code: het is een getal.

Draaien:  py gereedschap/test_tabbladen.py
"""
import ast
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

import uitvoer

uitvoer.zet_utf8()

BRON = os.path.join(REPO, "overhoring_web.py")
fouten = []


def kijk(goed, melding):
    if goed:
        print(f"  ok   {melding}")
    else:
        fouten.append(melding)
        print(f"  MIS  {melding}")


def lees_lijst(tekst, naam):
    """De letterlijke lijst uit de bron halen, zonder de app te starten."""
    treffer = re.search(rf"^\s*{naam}\s*=\s*\[", tekst, re.MULTILINE)
    if not treffer:
        sys.exit(f"{naam} niet gevonden in overhoring_web.py")
    begin = tekst.index("[", treffer.start())
    diepte, i = 0, begin
    while i < len(tekst):
        if tekst[i] == "[":
            diepte += 1
        elif tekst[i] == "]":
            diepte -= 1
            if diepte == 0:
                break
        i += 1
    return ast.literal_eval(tekst[begin:i + 1])


def main():
    tekst = open(BRON, encoding="utf-8").read()
    keuze = lees_lijst(tekst, "TAB_KEUZE")
    sleutels = lees_lijst(tekst, "_MENU_SLEUTELS")
    print(f"{len(keuze)} tabbladen in TAB_KEUZE, {len(sleutels)} in _MENU_SLEUTELS")

    keuze_sleutels = [s for s, _lab in keuze]
    kijk(len(keuze) == len(sleutels),
         f"beide lijsten even lang ({len(keuze)} en {len(sleutels)})")
    kijk(sorted(keuze_sleutels) == sorted(sleutels),
         "dezelfde tabbladen in beide lijsten")
    ontbreekt = set(keuze_sleutels) - set(sleutels)
    over = set(sleutels) - set(keuze_sleutels)
    if ontbreekt:
        print(f"       staat in TAB_KEUZE maar niet in _MENU_SLEUTELS: {sorted(ontbreekt)}")
    if over:
        print(f"       staat in _MENU_SLEUTELS maar niet in TAB_KEUZE: {sorted(over)}")
    kijk(len(set(keuze_sleutels)) == len(keuze_sleutels), "geen dubbele sleutels")

    # Welke indexen gebruikt de code, en passen die?
    gebruikt = {int(n) for n in re.findall(r"menu\[(\d+)\]", tekst)}
    gebruikt |= {int(n) for n in re.findall(r"_TOON\[(\d+)\]", tekst)}
    te_hoog = {n for n in gebruikt if n >= len(sleutels)}
    kijk(not te_hoog, f"geen index buiten de lijst (hoogste gebruikt: "
                      f"{max(gebruikt) if gebruikt else '-'}, lijst is {len(sleutels)} lang)")
    if te_hoog:
        print(f"       te hoog: {sorted(te_hoog)}")

    # Elk tabblad hoort ook een blok te hebben. Voortgang en Uitleg staan er altijd, de
    # rest kan uit; maar een tabblad zonder blok is altijd fout.
    zonder = [(i, s) for i, s in enumerate(sleutels) if i not in gebruikt]
    kijk(not zonder, "elk tabblad heeft een blok in de code")
    if zonder:
        for i, s in zonder:
            print(f"       geen menu[{i}] gevonden voor '{s}'")

    # En de beginstand voor een nieuwe gebruiker.
    begin = lees_lijst(tekst.replace("BEGIN_TABS = {", "BEGIN_TABS = ["), "BEGIN_TABS") \
        if "BEGIN_TABS = [" in tekst else None
    treffer = re.search(r"BEGIN_TABS = \{([^}]*)\}", tekst)
    begin = ast.literal_eval("[" + treffer.group(1) + "]") if treffer else []
    altijd = re.search(r"TAB_ALTIJD = \{([^}]*)\}", tekst)
    altijd = ast.literal_eval("[" + altijd.group(1) + "]") if altijd else []
    open_bij_start = sorted(set(begin) | set(altijd))
    kijk(all(s in keuze_sleutels for s in open_bij_start),
         f"de beginstand noemt alleen bestaande tabbladen: {open_bij_start}")
    kijk(len(open_bij_start) == 3,
         f"een nieuwe gebruiker begint met 3 tabbladen ({len(open_bij_start)}: "
         f"{open_bij_start})")

    print()
    print("de tabbalk, in de volgorde van het scherm:")
    for i, (s, lab) in enumerate(keuze):
        plek = sleutels.index(s)
        stand = "altijd aan" if s in altijd else ("aan bij start" if s in begin
                                                 else "uit bij start")
        print(f"  {i + 1:2d}. {lab:28s} menu[{plek:2d}]  {stand}")

    print()
    if fouten:
        sys.exit(f"{len(fouten)} mis")
    print("GESLAAGD")


if __name__ == "__main__":
    main()
