# -*- coding: utf-8 -*-
"""Wat staat er in 'C Veel voorkomende vormen', 'D veel voorkomende lexemen' en
'E Veel voorkomende werkwoorden' dat nog niet in de app zit?

Die drie bestanden staan in de map maar zijn nooit gebruikt: bouw_hebreeuws.py pakt alleen
de genummerde lijsten 001–410. Ze hebben allemaal al een Nederlandse betekenis, dus wat
hier uit komt is geen vertaling die ik verzin maar wat er in het cursusmateriaal staat.

Draaien:  py gereedschap/peil_extra_lijsten.py
"""
import glob
import json
import os
import sys
import unicodedata

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "gereedschap"))
os.chdir(REPO)

import uitvoer

uitvoer.zet_utf8()

import bouw_hebreeuws as B

BESTANDEN = ["C Veel voorkomende vormen.docx",
             "D veel voorkomende lexemen.docx",
             "E Veel voorkomende werkwoorden.docx"]


def lees(naam):
    """De regels 'hebreeuws = nederlands' uit één bestand."""
    uit = []
    for regel in B.regels_uit_docx(os.path.join(B.MAP, naam)):
        regel = unicodedata.normalize("NFC", regel)
        if "=" not in regel or not any(B.hebreeuws(t) for t in regel):
            continue
        links, _, rechts = regel.partition("=")
        heb, ned = links.strip(), rechts.strip()
        if B.medeklinkers(heb) and ned:
            uit.append((heb, ned))
    return uit


def main():
    hebben = {}
    for w in json.load(open("hebreeuws_woorden.json", encoding="utf-8")):
        hebben[w["medeklinkers"]] = w

    for naam in BESTANDEN:
        pad = os.path.join(B.MAP, naam)
        if not os.path.exists(pad):
            print(f"{naam}: niet gevonden")
            continue
        regels = lees(naam)
        nieuw = [(h, n) for h, n in regels if B.medeklinkers(h) not in hebben]
        al = len(regels) - len(nieuw)
        print(f"\n=== {naam}")
        print(f"    {len(regels)} regels, {al} staan al in de app, {len(nieuw)} nieuw")
        for heb, ned in nieuw:
            print(f"      {heb:14s} {ned}")


if __name__ == "__main__":
    main()
