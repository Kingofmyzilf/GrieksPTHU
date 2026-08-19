# -*- coding: utf-8 -*-
"""Zet de hints uit hebreeuws_hints.tsv in hebreeuws_woorden.json.

De hints staan in een apart bestand en niet in de JSON, omdat die JSON telkens opnieuw
wordt opgebouwd uit de cursusbestanden. Zo overleven ze dat.

Dezelfde regel als bij Grieks: een icoontje en hoogstens vijf woorden. Waar het Nederlands
of een bekende naam het woord al bevat, ís dat de hint — Ben-jamin bij בֵּן, Beth-lehem bij
בַּיִת, Har-Magedon bij הַר, Immanu-el bij עִם. Bij Hebreeuws werkt dat vaak beter dan bij
Grieks, want de namen uit de Bijbel zitten vol woorden die je aan het leren bent.

Draaien:  py gereedschap/hints_hebreeuws.py     (na bouw_ en koppel_hebreeuws.py)
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HINTS = os.path.join(REPO, "gereedschap", "hebreeuws_hints.tsv")
WOORDEN = os.path.join(REPO, "hebreeuws_woorden.json")


def main():
    hints = {}
    with open(HINTS, encoding="utf-8") as f:
        for regel in f:
            if not regel.strip():
                continue
            nummer, icoon, tekst = regel.rstrip("\n").split("\t")
            hints[int(nummer)] = (icoon, tekst)

    with open(WOORDEN, encoding="utf-8") as f:
        woorden = json.load(f)

    gezet = 0
    for w in woorden:
        hint = hints.get(w["nummer"])
        if hint:
            w["anker"], w["beeld"] = hint
            gezet += 1
        else:
            w.setdefault("anker", "")
            w.setdefault("beeld", "")

    with open(WOORDEN, "w", encoding="utf-8") as f:
        json.dump(woorden, f, ensure_ascii=False, indent=1)

    zonder = [w["nummer"] for w in woorden if not w["beeld"]]
    langste = max((len(w["beeld"]) for w in woorden if w["beeld"]), default=0)
    print(f"{gezet} hints gezet, langste {langste} tekens")
    if zonder:
        print("nog zonder hint:", zonder[:20])
        sys.exit(1)


if __name__ == "__main__":
    main()
