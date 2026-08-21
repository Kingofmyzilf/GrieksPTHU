# -*- coding: utf-8 -*-
"""Zet een reeks grammatica-slides als plaatje klaar om te lezen.

Bedoeld om de slides over te typen naar tekst.

De fotostroken links en rechts eraf snijden zou schelen, maar dat is één keer geprobeerd en
toen verdwenen de G-nummers uit de eerste kolom: de kolommen waar de achtergrond overal
gelijk is, waren gemeten in het ingebedde plaatje en niet in de pagina zelf, en die twee
liggen niet op elkaar. De winst was twee kilobyte per slide en het risico is dat er tekst
wegvalt zonder dat je het ziet. Dus de hele pagina.

Alle 376 slides staan inmiddels overgetypt in grammatica_slides.json, dus dit script is er
nu voor nakijken en niet meer voor het overtypen zelf. De pdf staat daarom niet meer in de
repo; haal hem eerst terug als je hem nodig hebt:

    git show 2af3a4a:grammatica_overzicht.pdf > grammatica_overzicht.pdf

Draaien:  py gereedschap/slides_beelden.py <van> <tot> [map]

Bijvoorbeeld 'py gereedschap/slides_beelden.py 41 50' zet slide 41 tot en met 50 klaar.
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

import uitvoer

uitvoer.zet_utf8()

PDF = os.path.join(REPO, "grammatica_overzicht.pdf")
DPI = 96          # hierbij zijn de accenten en de spiritus goed te zien


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    van, tot = int(sys.argv[1]), int(sys.argv[2])
    map_uit = sys.argv[3] if len(sys.argv) > 3 else os.path.join(REPO, "slides_werk",
                                                                 "beelden")
    os.makedirs(map_uit, exist_ok=True)
    for oud in os.listdir(map_uit):
        if oud.endswith(".png"):
            os.remove(os.path.join(map_uit, oud))

    if not os.path.exists(PDF):
        sys.exit(f"{PDF} staat niet in de repo (zie de kop van dit bestand).")
    import fitz
    doc = fitz.open(PDF)
    for n in range(van, min(tot, doc.page_count) + 1):
        pad = os.path.join(map_uit, f"s{n:03d}.png")
        doc[n - 1].get_pixmap(dpi=DPI).save(pad)
    print(f"slide {van} t/m {min(tot, doc.page_count)} klaar in {map_uit}")


if __name__ == "__main__":
    main()
