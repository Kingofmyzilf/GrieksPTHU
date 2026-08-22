# -*- coding: utf-8 -*-
"""Vult actief_beheersen.json aan met de paradigma's die het tentamen vraagt maar die er
niet in stonden.

De drie pdf's 'Vormleer om actief te beheersen' (Grieks 1, 2 en 3) zijn een selectie uit
dezelfde grammatica-slides: precies wat je voor opgave 3 van het tentamen moet kunnen
reproduceren. Door de Griekse vormen per pdf-pagina in de overgetypte slides te zoeken is
elke pagina aan een slide te koppelen, en dus na te rekenen of de oefening precies dat
oefent. Twee paradigma's ontbraken:

    Grieks 1, pdf p7  -> slide 117  αὐτός / αὐτή / αὐτό (pers. vnw. 3e persoon)
                                    de oefening had alleen de 1e en 2e persoon
    Grieks 2, pdf p15 -> slide 278  λυόμενος (participium praesens medium)
                                    de oefening had 4 van de 5 participia

De vormen komen uit de slides zelf, niet uit een tweede keer overtypen. Dat is de winst van
het overtypen: de slides zijn nu de bron waar de oefening tegen te controleren is.

Dit script is eenmalig en staat hier zodat te zien is wat er is bijgekomen en waarom.
Draaien:  py gereedschap/vul_actief_aan.py [--proef]
"""
import io
import json
import os
import re
import sys
import unicodedata

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

import uitvoer

uitvoer.zet_utf8()

NAAMVALLEN = ["Nom ev", "Gen ev", "Dat ev", "Acc ev", "Nom mv", "Gen mv", "Dat mv", "Acc mv"]
VAST = "Onregelmatig of vast paradigma. Leer deze vorm visueel in zijn geheel."
UITGANG = "Vaste persoons- of participiumuitgang toegevoegd aan de stam."


def sleutel(*delen):
    """Dezelfde vorm van id als de rest van het bestand: kleine letters, streepjes."""
    t = "_".join(str(d) for d in delen).lower()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9]+", "_", t)
    return re.sub(r"_+", "_", t).strip("_")


def uit_slide(nr, kolommen):
    """De cellen van een paradigmatabel op een slide, per kolom.

    De slides bewaren een rijtje als <table> met <th> voor het naamvallabel en <td> per
    geslacht; het vet in de cel markeert de uitgang. Hier wordt de tabel uitgelezen zoals
    hij er staat, zodat er niets opnieuw wordt ingetypt.
    """
    with open("grammatica_slides.json", encoding="utf-8") as f:
        slide = next(s for s in json.load(f) if int(s["nr"]) == nr)
    html = slide["html"]
    tabel = re.search(r"<table[^>]*>(.*?)</table>", html, re.S).group(1)
    rijen = []
    for rij in re.findall(r"<tr>(.*?)</tr>", tabel, re.S):
        cellen = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", rij, re.S)
        rijen.append(cellen)
    uit = {k: [] for k in kolommen}
    naamval = 0
    for cellen in rijen:
        if len(cellen) < len(kolommen) + 1:
            continue                       # kopregel
        label = re.sub(r"<[^>]+>", "", cellen[0]).strip()
        if not any(n.split()[0].lower() in label.lower() for n in ("nom", "gen", "dat", "acc")):
            continue
        for i, kolom in enumerate(kolommen):
            ruw = cellen[i + 1]
            # het vet in de cel is de uitgang; de rest is de stam
            vet = "".join(re.findall(r"<b>(.*?)</b>", ruw, re.S))
            heel = re.sub(r"<[^>]+>", "", ruw).strip()
            stam = heel[:len(heel) - len(re.sub(r"<[^>]+>", "", vet))] if vet else heel
            uit[kolom].append((NAAMVALLEN[naamval], heel,
                               stam, re.sub(r"<[^>]+>", "", vet)))
        naamval += 1
        if naamval >= len(NAAMVALLEN):
            break
    return uit


def main():
    proef = "--proef" in sys.argv
    pad = os.path.join(REPO, "actief_beheersen.json")
    ab = json.load(io.open(pad, encoding="utf-8"))
    erbij = []

    # --- Grieks 1: αὐτός / αὐτή / αὐτό, uit slide 117 -------------------------------
    kolommen = ["3e p. man.", "3e p. vro.", "3e p. onz."]
    # slide 117 heeft vijf kolommen: 1e, 2e, 3e man., 3e vro., 3e onz.
    heel = uit_slide(117, ["1e persoon", "2e persoon"] + kolommen)
    groep = ab["Grieks 1"]["Pronomen Personale"]
    for kolom, naam in zip(kolommen, ["3e Persoon m. (hij)", "3e Persoon v. (zij)",
                                      "3e Persoon o. (het)"]):
        if naam in groep:
            print(f"  {naam} stond er al — overgeslagen")
            continue
        cellen = []
        for label, vorm, _stam, _uit in heel[kolom]:
            cellen.append({"label": label, "vorm": vorm,
                           "id": sleutel("grieks_1_pronomen_personale", naam, label),
                           "stam": vorm, "uitgang": "", "toelichting": VAST})
        groep[naam] = cellen
        erbij.append(f"Grieks 1 / Pronomen Personale / {naam}: {len(cellen)} cellen "
                     f"({', '.join(c['vorm'] for c in cellen[:4])} …)")

    # --- Grieks 2: participium praesens medium, uit slide 278 -----------------------
    # Slide 278 zet de uitgangen niet in vet (anders dan de meeste paradigmaslides), dus
    # daar valt niets uit te lezen. Knippen gebeurt hier op de verbale stam λυ, precies
    # zoals de vier participia die er al stonden: λύ+ων, λύ+ουσα, λυ+ούσης. Zonder dit
    # knippen blijft 'uitgang' leeg, en dan slaat de app de vormopbouw na het antwoord
    # stil over — het enige rijtje in zijn groep zonder die gekleurde uitgang.
    STAM = "λυ"
    heel = uit_slide(278, ["Mannelijk", "Vrouwelijk", "Onzijdig"])
    groep = ab["Grieks 2"]["Participium (λύω)"]
    naam = "Praesens Medium (λυόμενος)"
    if naam in groep:
        print(f"  {naam} stond er al — overgeslagen")
    else:
        cellen = []
        # dezelfde volgorde als de andere participia: per naamval de drie geslachten
        for i, nv in enumerate(NAAMVALLEN):
            for gesl, kort in (("Mannelijk", "M"), ("Vrouwelijk", "V"), ("Onzijdig", "O")):
                nv_lab, vorm, stam, uitg = heel[gesl][i]
                label = f"Participium {nv.replace(' ', '. ')}. {kort}"
                if not uitg:                       # slide 278 heeft geen vet: zelf knippen
                    stam, uitg = vorm[:len(STAM)], vorm[len(STAM):]
                cellen.append({
                    "label": label, "vorm": vorm,
                    "id": sleutel("grieks_2_participium_luo", naam, label),
                    "stam": stam, "uitgang": uitg, "toelichting": UITGANG})
        groep[naam] = cellen
        erbij.append(f"Grieks 2 / Participium (λύω) / {naam}: {len(cellen)} cellen "
                     f"({', '.join(c['vorm'] for c in cellen[:3])} …)")

    print("\nerbij gekomen:")
    for r in erbij:
        print("  " + r)
    if not erbij:
        print("  (niets — alles stond er al)")
        return
    if proef:
        print("\n--proef: niets geschreven")
        return
    io.open(pad, "w", encoding="utf-8", newline="\n").write(
        json.dumps(ab, ensure_ascii=False, indent=1) + "\n")
    cellen = sum(len(r) for c in ab.values() for g in c.values() for r in g.values())
    print(f"\n{pad} geschreven ({os.path.getsize(pad)/1024:.0f} kB, {cellen} cellen)")


if __name__ == "__main__":
    main()
