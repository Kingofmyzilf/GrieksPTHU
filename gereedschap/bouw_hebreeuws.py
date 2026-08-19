# -*- coding: utf-8 -*-
"""Pakt de Hebreeuwse woordenschat uit de cursusbestanden en schrijft hebreeuws_woorden.json.

De lijst staat in tien bestanden: 001–165 in Word, 166–410 in PDF. Elke regel is één woord:
eerst het Hebreeuws, dan de Nederlandse betekenis. Drie dingen maken dat lastiger dan het
klinkt, en die vangt dit script af:

  * Een lange betekenis loopt door op de volgende regel. Zo'n regel bevat geen Hebreeuws;
    die hoort bij het woord erboven.
  * De vocalisatie staat niet overal in dezelfde volgorde opgeslagen (אֱלהִֹים tegenover
    אֱלֹהִים). Unicode noemt dat hetzelfde woord pas na normalisatie naar NFC.
  * Waar het Hebreeuws ophoudt en het Nederlands begint is niet altijd een spatie: in de
    PDF's staat het aan elkaar geplakt, en het Nederlands kan met een haakje beginnen.

Draaien:  py gereedschap/bouw_hebreeuws.py
"""
import glob
import json
import os
import re
import sys
import unicodedata
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP = os.path.join(REPO, "hebreeuws app")
UIT = os.path.join(REPO, "hebreeuws_woorden.json")

# Slotletters terug naar hun gewone vorm, zodat כ en ך als dezelfde letter tellen.
FINAAL = {"ך": "כ", "ם": "מ", "ן": "נ",
          "ף": "פ", "ץ": "צ"}

# De stamformaties zoals de cursus ze afkort, vóór de betekenis van dat stamgebruik.
BINYAN = {"G": "Qal", "N": "Nifal", "D": "Piel", "Dp": "Pual",
          "H": "Hifil", "Hp": "Hofal", "Ht": "Hitpael"}


def hebreeuws(teken):
    return "֐" <= teken <= "׿"


def medeklinkers(tekst):
    """Alleen de letters, slotletters teruggebracht. Dit is de sleutel waarop we later
    aan de bijbeltekst koppelen — klinkertekens staan daar anders dan in een lemma."""
    return "".join(FINAAL.get(t, t) for t in str(tekst) if "א" <= t <= "ת")


def splits(regel):
    """(hebreeuws, nederlands) uit één regel.

    De betekenis begint bij de eerste Latijnse letter of cijfer. Haakjes zijn géén grens:
    een citatievorm kan er zelf mee beginnen — in leesrichting van rechts naar links komt
    'רדף (אַחַר)' er als '(אַחַר)רדף' uit. Wat er aan haakjes vóór die grens overblijft
    hoort dus bij het Hebreeuws en wordt er alleen achteraan afgehaald."""
    grens = len(regel)
    for i, teken in enumerate(regel):
        if teken.isascii() and (teken.isalpha() or teken.isdigit()):
            grens = i
            break
    heb = regel[:grens].strip(" \t,;·([{")
    # Losse klinkertekens die achter de betekenis zijn beland horen daar niet.
    ned = "".join(t for t in regel[grens:] if not ("֑" <= t <= "ׇ")).strip()
    return heb, ned


def regels_uit_docx(pad):
    with zipfile.ZipFile(pad) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    xml = re.sub(r"<w:p[ >]", "\n<w:p ", xml)
    return [r.strip() for r in re.sub(r"<[^>]+>", "", xml).split("\n") if r.strip()]


def regels_uit_pdf(pad):
    import fitz
    doc = fitz.open(pad)
    return [r.strip() for p in doc for r in p.get_text().split("\n") if r.strip()]


def bereik(naam):
    """'Woordenschat 061-120.docx' -> (61, 120); '1_...•166t200.pdf' -> (166, 200)."""
    m = re.search(r"(\d{3})\s*[-t]\s*(\d{3})", os.path.basename(naam))
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def lees_bestand(pad):
    """De woorden uit één bestand, met doorlopende regels samengevoegd."""
    regels = regels_uit_docx(pad) if pad.endswith(".docx") else regels_uit_pdf(pad)
    woorden = []
    for regel in regels:
        regel = unicodedata.normalize("NFC", regel)
        if not any(hebreeuws(t) for t in regel):
            # Geen Hebreeuws: dat is de kopregel, een paginanummer, of het vervolg van de
            # betekenis erboven. De eerste twee herhalen zich midden in de PDF's.
            rommel = (re.match(r"^(Woordenschat|Hebreeuws)\b", regel)
                      or re.fullmatch(r"[\d\s.·-]+", regel))
            if woorden and not rommel:
                woorden[-1]["nederlands"] += " " + regel
            continue
        heb, ned = splits(regel)
        # Eén letter is genoeg: בְּ, הַ, וְ, כְּ en לְ zijn de meest voorkomende woorden
        # van het Hebreeuws en die zouden er met een hogere ondergrens uit vallen.
        if not medeklinkers(heb):
            continue
        woorden.append({"hebreeuws": heb, "nederlands": ned})
    return woorden


def verrijk(woord):
    """Wat er uit de betekenis zelf af te leiden valt: varianten, geslacht, stamformaties."""
    heb, ned = woord["hebreeuws"], woord["nederlands"]
    # Een woord kan twee schrijfwijzen hebben: 'אָהֵב ,אהב' of 'אַחֲרֵי /אַחַר'.
    varianten = [v.strip() for v in re.split(r"[,/]", heb) if medeklinkers(v)]
    woord["hebreeuws"] = varianten[0]
    woord["varianten"] = varianten[1:]
    woord["medeklinkers"] = medeklinkers(varianten[0])
    # '(v)' achter een zelfstandig naamwoord betekent vrouwelijk.
    woord["geslacht"] = "v" if re.match(r"^\(v\)", ned) else ""
    # 'G eten; N gegeten worden; H voeden' — per stamformatie een eigen betekenis.
    stammen = {}
    for code, naam in BINYAN.items():
        m = re.search(rf"(?:^|[;.]\s*)\b{code}\b\s+([^;]+)", ned)
        if m:
            stammen[naam] = m.group(1).strip()
    woord["stammen"] = stammen
    woord["woordsoort"] = "ww" if stammen else ""
    return woord


def main():
    bestanden = sorted(glob.glob(os.path.join(MAP, "*.docx"))
                       + glob.glob(os.path.join(MAP, "*.pdf")),
                       key=bereik)
    bestanden = [b for b in bestanden if bereik(b) != (0, 0)]
    if not bestanden:
        sys.exit(f"Geen woordenschatbestanden gevonden in {MAP}")

    alles, klachten = [], []
    for pad in bestanden:
        van, tot = bereik(pad)
        woorden = lees_bestand(pad)
        verwacht = tot - van + 1
        if len(woorden) != verwacht:
            klachten.append(f"{os.path.basename(pad)}: {len(woorden)} gevonden, "
                            f"{verwacht} verwacht ({van}-{tot})")
        for i, w in enumerate(woorden):
            w["nummer"] = van + i
            w["les"] = 1 if tot <= 165 else 2        # THB-HEB1 of HEB2
            alles.append(verrijk(w))

    for regel in klachten:
        print("  let op:", regel)

    with open(UIT, "w", encoding="utf-8") as f:
        json.dump(alles, f, ensure_ascii=False, indent=1)

    ww = sum(1 for w in alles if w["stammen"])
    var = sum(1 for w in alles if w["varianten"])
    print(f"{len(alles)} woorden weggeschreven naar {os.path.basename(UIT)} "
          f"({ww} werkwoorden met stamformaties, {var} met een tweede schrijfwijze)")


if __name__ == "__main__":
    main()
