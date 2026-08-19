# -*- coding: utf-8 -*-
"""Hebreeuws voor de oefen-app: typen met een gewoon toetsenbord, vergelijken, en laden.

Dit staat apart van grieks_motor.py omdat die uit overhoring_web.py wordt gegenereerd; met
de hand aanpassen zou bij de volgende generatie verdwijnen.

Twee dingen liggen hier vast, en die bepalen hoe het oefenen voelt:

  * Je typt alléén medeklinkers. Dat is geen versimpeling maar hoe de taal werkt: de
    cursuslijst geeft een werkwoord ook als אכל, en de klinkertekens zijn later bedacht.
    Wie מלך wil schrijven typt 'mlk'. Dat scheelt de student een berg gepriegel met
    tekens die op een Nederlands toetsenbord niet bestaan.
  * Slotletters komen er vanzelf uit. Wie 'mlk' typt krijgt מלך met een slot-kaf, want in
    het Hebreeuws verandert kaf, mem, noen, pe en tsade van vorm aan het eind van een
    woord. Precies zoals de slot-sigma bij Grieks.
"""
import functools
import json
import os

BESTAND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hebreeuws_woorden.json")

# Welke Latijnse letters welke Hebreeuwse letter geven. Ruim opgezet: waar twee
# schrijfwijzen voor de hand liggen worden ze allebei geaccepteerd, want fout rekenen op
# een toetsaanslag die je zelf niet hebt uitgelegd is onredelijk. De tweetekencombinaties
# staan bovenaan omdat ze vóór de losse letters gezocht moeten worden.
# Let op wat híér niet staat: kh, th en sh. Die leken handige alternatieven voor ח, ט en
# ש, maar ze botsen met een gewone letter gevolgd door ה — en dat is juist de meest
# voorkomende uitgang van het Hebreeuws. Met die drie erbij werd כֹּה 'zo' een chet, בָּכָה
# 'wenen' werd בח en מַמְלָכָה 'koninkrijk' werd ממלח. Tien van de 410 woorden waren zo niet
# te typen. Vier tweetekencombinaties blijven over, en die zijn nagelopen op de hele lijst.
TOETSEN = [
    ("ch", "ח"),
    ("tt", "ט"),
    ("ts", "צ"), ("tz", "צ"),
    ("sj", "ש"),
    ("a", "א"), ("'", "א"),
    ("b", "ב"), ("v", "ב"),
    ("g", "ג"),
    ("d", "ד"),
    ("h", "ה"),
    ("w", "ו"), ("u", "ו"), ("o", "ו"),
    ("z", "ז"),
    ("x", "ח"),
    ("j", "י"), ("y", "י"), ("i", "י"),
    ("k", "כ"),
    ("l", "ל"),
    ("m", "מ"),
    ("n", "נ"),
    ("s", "ס"),
    ("e", "ע"), ("`", "ע"),
    ("p", "פ"), ("f", "פ"),
    ("c", "צ"),
    ("q", "ק"),
    ("r", "ר"),
    ("t", "ת"),
]

# Aan het eind van een woord krijgen deze vijf een andere vorm.
SLOTLETTERS = {"כ": "ך", "מ": "ם", "נ": "ן", "פ": "ף", "צ": "ץ"}
TERUG = {v: k for k, v in SLOTLETTERS.items()}

# Voor het spiekbriefje in de app: per groep de toetsaanslag en wat eruit komt.
SPIEKBRIEF = [
    ("Stil of bijna stil", [("a", "א alef"), ("e", "ע ajin"), ("h", "ה he")]),
    ("Gewoon wat je hoort", [("b", "ב"), ("g", "ג"), ("d", "ד"), ("w", "ו"), ("z", "ז"),
                             ("j", "י"), ("k", "כ"), ("l", "ל"), ("m", "מ"), ("n", "נ"),
                             ("s", "ס"), ("p", "פ"), ("q", "ק"), ("r", "ר"), ("t", "ת")]),
    ("Twee tekens samen", [("ch", "ח chet"), ("tt", "ט tet"), ("ts", "צ tsade"),
                           ("sj", "ש sjin")]),
]


def naar_hebreeuws(tekst):
    """Latijnse letters omzetten naar Hebreeuwse medeklinkers.

    Loopt van links naar rechts en probeert eerst de langste combinatie; anders zou 'sj'
    een samech plus jod worden in plaats van een sjin. Wat we niet kennen blijft staan,
    zodat je ziet dat er iets niet klopt in plaats van dat het stilletjes verdwijnt."""
    bron = str(tekst or "").lower().strip()
    uit = []
    i = 0
    while i < len(bron):
        for latijn, hebreeuws in TOETSEN:
            if bron.startswith(latijn, i):
                uit.append(hebreeuws)
                i += len(latijn)
                break
        else:
            uit.append(bron[i])
            i += 1
    return _slotvormen("".join(uit))


def _slotvormen(woorden):
    """De laatste letter van elk woord in zijn slotvorm zetten."""
    uit = []
    for woord in woorden.split(" "):
        if woord and woord[-1] in SLOTLETTERS:
            woord = woord[:-1] + SLOTLETTERS[woord[-1]]
        uit.append(woord)
    return " ".join(uit)


@functools.lru_cache(maxsize=100000)
def medeklinkers(tekst):
    """Alleen de letters, slotvormen teruggebracht. Hierop wordt vergeleken: klinkertekens
    en cantillatie horen bij de tekst, niet bij wat je moet kunnen schrijven."""
    return "".join(TERUG.get(t, t) for t in str(tekst) if "א" <= t <= "ת")


def vorm_ok(gegeven, doel):
    """Klopt wat er getypt is? Vergelijkt op medeklinkers, en accepteert zowel Hebreeuws
    als de Latijnse omzetting ervan — wie het Hebreeuwse toetsenbord aan heeft staan
    hoeft niet eerst iets uit te zetten."""
    gegeven = str(gegeven or "").strip()
    if not gegeven:
        return False
    doel_med = medeklinkers(doel)
    if not doel_med:
        return False
    if medeklinkers(gegeven) == doel_med:
        return True
    return medeklinkers(naar_hebreeuws(gegeven)) == doel_med


# Zoveel Hebreeuwse woordvormen staan er in de Tenach. Geteld in 'Hele bijbel.xlsx' (de
# WLC-tekst met parsing): 300.670 Hebreeuwse plus 4.826 Aramese vormen. De Aramese delen
# van Daniël en Ezra tellen niet mee — die staan niet in deze woordenlijst, en ze in de
# noemer stoppen zou de dekking laten lijken op iets wat je met deze woorden nooit haalt.
TENACH_WOORDEN = 300670


def dekking(woorden, drempel=16):
    """Welk deel van de Tenach je met deze woorden kunt lezen, in procenten.

    Niet hoevéél woorden je kent, maar hoe vaak ze er staan — en dat verschilt enorm. Tien
    woorden dekken al 11% van de tekst, honderd woorden 48%, en de hele lijst van 410 komt
    op 70%. Dat is het getal dat vooruitgang zichtbaar maakt: bij Grieks is dat de
    NT-dekking, hier de Tenach.

    Eén Strong-nummer telt één keer, ook als het in de lijst twee keer voorkomt (een
    werkwoord en het zelfstandig naamwoord ernaast delen soms hun nummer). Zonder dat komt
    de som boven de honderd procent uit."""
    per_strong = {}
    for w in woorden:
        streak = int(w.get("streak", 0) or 0)
        strong = str(w.get("strong") or "")
        if strong and streak >= drempel:
            per_strong[strong] = int(w.get("frequentie") or 0)
    return round(100 * sum(per_strong.values()) / TENACH_WOORDEN, 1)


@functools.lru_cache(maxsize=1)
def laad_woorden():
    """De 410 woorden met hun betekenis, hint, frequentie en vindplaatsen."""
    try:
        with open(BESTAND, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def aanwezig():
    """Is de Hebreeuwse woordenlijst er? Zo niet, dan laat de app die taal niet zien."""
    return bool(laad_woorden())
