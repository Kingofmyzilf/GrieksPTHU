# -*- coding: utf-8 -*-
"""Voegt de overgetypte slides samen tot grammatica_slides.json.

De 376 grammatica-slides stonden als plaatjes in een pdf van 22 MB. Elke pagina was één
jpeg; er zat geen tekstlaag in, en de zoekindex was een oude OCR die het Grieks vermorzelde
('evayyéatov' voor εὐαγγέλιον). Daarom zijn ze overgetypt naar tekst.

Wat dat oplost, behalve 22 MB:
  * zoeken werkt, want er staat echte tekst in plaats van losse OCR-woorden;
  * op een telefoon is het te lezen -- een plaatje van een slide van 40 cm breed is dat
    niet, tekst loopt gewoon door;
  * de opmaak zit in de app en niet in het plaatje, dus kleuren en lettergrootte zijn
    achteraf nog te veranderen.

Het werk staat per stuk in slides_werk/*.json, zodat het in stukjes kan en niets kwijtraakt.
Elk bestand is een lijst met {"nr", "kop", "html"} en eventueel "cursus" en "sub".

Draaien:  py gereedschap/bouw_grammatica_slides.py          samenvoegen en tekortkomingen
          py gereedschap/bouw_grammatica_slides.py --gaten  alleen zeggen wat er nog mist
"""
import glob
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

WERK = os.path.join(REPO, "slides_werk")
UIT = os.path.join(REPO, "grammatica_slides.json")
TOTAAL = 376


def lees_werk():
    """Alle stukjes bij elkaar, op slidenummer. Een later stuk overschrijft een eerder."""
    slides = {}
    for pad in sorted(glob.glob(os.path.join(WERK, "*.json"))):
        with open(pad, encoding="utf-8") as f:
            for slide in json.load(f):
                slides[int(slide["nr"])] = slide
    return slides


def plat(html):
    """De tekst zonder opmaak, om op te zoeken."""
    tekst = re.sub(r"<[^>]+>", " ", str(html or ""))
    tekst = (tekst.replace("&nbsp;", " ").replace("&amp;", "&")
             .replace("&lt;", "<").replace("&gt;", ">"))
    return re.sub(r"\s+", " ", tekst).strip()


def main():
    slides = lees_werk()
    gaten = [n for n in range(1, TOTAAL + 1) if n not in slides]
    print(f"{len(slides)} van de {TOTAAL} slides overgetypt")
    if gaten:
        # Aaneengesloten reeksen samenvatten, anders is het een muur van getallen.
        reeksen, begin = [], gaten[0]
        for vorige, nu in zip(gaten, gaten[1:] + [None]):
            if nu != vorige + 1:
                reeksen.append(f"{begin}" if begin == vorige else f"{begin}-{vorige}")
                begin = nu
        print(f"nog te doen ({len(gaten)}): {', '.join(reeksen)}")
    else:
        print("alles compleet")
    if "--gaten" in sys.argv:
        return

    uit = []
    for n in sorted(slides):
        slide = dict(slides[n])
        slide["nr"] = n
        slide["tekst"] = plat(slide.get("html", ""))
        uit.append(slide)
    with open(UIT, "w", encoding="utf-8") as f:
        json.dump(uit, f, ensure_ascii=False, separators=(",", ":"))
    groot = os.path.getsize(UIT)
    tekens = sum(len(s["tekst"]) for s in uit)
    print(f"{UIT}: {groot/1024:.0f} kB, {tekens} tekens tekst "
          f"({tekens/max(1,len(uit)):.0f} per slide)")
    pdf = os.path.join(REPO, "grammatica_overzicht.pdf")
    if os.path.exists(pdf):
        print(f"de pdf is {os.path.getsize(pdf)/1048576:.1f} MB — "
              f"dit is {100*groot/os.path.getsize(pdf):.1f}% daarvan")


if __name__ == "__main__":
    main()
