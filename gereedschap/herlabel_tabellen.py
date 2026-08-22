# -*- coding: utf-8 -*-
"""Zet de G-nummers in grammatica_tabellen.json recht.

De sleutels van dat bestand zijn niet alleen sleutels: de app zet ze als kop boven het
rijtje ('bekijk het rijtje (spieken)'). Een verkeerd G-nummer stuurt je dus naar het
verkeerde hoofdstuk in het Grammatica-tabblad.

Tot voor kort was dat niet te controleren — de slides waren plaatjes. Nu ze overgetypt
zijn, is per rijtje op te zoeken waar het paradigma écht staat. Dat is gedaan door de
Griekse vormen uit elk rijtje in de slidetekst te zoeken; hieronder staat per verandering
de slide die het bewijst.

Dit script is eenmalig: het is gedraaid, en staat hier zodat te zien is wat er veranderd is
en waarom. Draaien:  py gereedschap/herlabel_tabellen.py [--proef]
"""
import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

import uitvoer

uitvoer.zet_utf8()

# oude sleutel -> (nieuwe sleutel, waarom)
HERNOEM = {
    "G25 Interrogativum": (
        "G30 Interrogativum",
        "G25 is Pronomen possessivum; het vragend/onbepaald vnw staat op slide 222 (G30)"),
    "G26 Passivum": (
        "G27 Passivum",
        "G26 is Diathese in het algemeen; deze prae./impf.-vormen staan op slide 205 (G27) "
        "— in die tempora dient het medium als passief"),
    "G30 Trappen": (
        "G43 Trappen",
        "G30 is het vragend vnw; trappen van vergelijking is G43"),
    "G33 3e Decl (Klinker)": (
        "G29 3e Decl (Klinker)",
        "G33 is de AcI; de klinkerstammen horen bij de 3e declinatie, slide 217 (G29)"),
    "G39 Part Aoristus": (
        "G38 Part Aoristus",
        "G39 gaat over bijzondere vormingswijzen; dit paradigma staat op slide 276 (G38)"),
    "G40 Part Passief": (
        "G38 Part Passief",
        "G40 is de genitivus absolutus; dit paradigma staat op slide 283 (G38)"),
    "G43 Mi-Werkwoorden": (
        "G49-G50 Mi-Werkwoorden",
        "G43 is trappen van vergelijking; δίδωμι/τίθημι/ἵστημι staan op slide 359 (G49) "
        "en 363-366 (G50)"),
    "G45 Optativus": (
        "G48 Optativus",
        "G45 gaat over de coniunctivus; de optativus staat op slide 349 (G48)"),
    "G46 Imperativus": (
        "G9-G15 Imperativus",
        "G46 is bijwoorden; imperativus praesens staat op slide 81 (G9) en aoristus op "
        "slide 113 (G15)"),
    "G50 Stamtijden": (
        "G28 Stamtijden",
        "G50 is de μι-werkwoorden op een vocaalstam; de stamtijdenlijst is G28, slide 209"),
}

# Waar de sleutels als letterlijke tekst in de code staan. Twee bestanden, want de
# Streamlit-app heeft zijn eigen kopie van de kiesfunctie.
CODE = ["grieks_motor.py", "overhoring_web.py", "grieks_app.py"]


def sorteer(naam):
    """Op het eerste G-nummer, daarna alfabetisch — zodat het bestand leesbaar blijft."""
    m = re.match(r"G(\d+)", naam)
    return (int(m.group(1)) if m else 999, naam)


def main():
    proef = "--proef" in sys.argv
    pad = os.path.join(REPO, "grammatica_tabellen.json")
    tab = json.load(io.open(pad, encoding="utf-8"))

    ontbreekt = [k for k in HERNOEM if k not in tab]
    if ontbreekt:
        sys.exit(f"deze sleutels staan niet (meer) in het bestand: {ontbreekt}")

    nieuw = {}
    for oud, rijen in tab.items():
        naam = HERNOEM.get(oud, (oud, ""))[0]
        nieuw[naam] = rijen
    nieuw = {k: nieuw[k] for k in sorted(nieuw, key=sorteer)}

    print(f"{len(HERNOEM)} van de {len(tab)} rijtjes krijgen een ander G-nummer:")
    for oud, (naar, waarom) in HERNOEM.items():
        print(f"  {oud:26} -> {naar:24} {waarom}")

    print("\nverwijzingen in de code:")
    for bestand in CODE:
        tekst = io.open(bestand, encoding="utf-8").read()
        raak = {oud: tekst.count(f'"{oud}"') for oud in HERNOEM if f'"{oud}"' in tekst}
        print(f"  {bestand:22} {sum(raak.values())} plek(ken) {list(raak)}")
        for oud, (naar, _w) in HERNOEM.items():
            tekst = tekst.replace(f'"{oud}"', f'"{naar}"')
        if not proef:
            io.open(bestand, "w", encoding="utf-8", newline="\n").write(tekst)

    if proef:
        print("\n--proef: niets geschreven")
        return
    io.open(pad, "w", encoding="utf-8", newline="\n").write(
        json.dumps(nieuw, ensure_ascii=False, indent=1) + "\n")
    print(f"\n{pad} geschreven ({os.path.getsize(pad)/1024:.0f} kB, "
          f"{len(nieuw)} rijtjes)")


if __name__ == "__main__":
    main()
