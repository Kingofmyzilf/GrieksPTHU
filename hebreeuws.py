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
import gzip
import json
import os

_HIER = os.path.dirname(os.path.abspath(__file__))
BESTAND = os.path.join(_HIER, "hebreeuws_woorden.json")
RIJTJES = os.path.join(_HIER, "hebreeuws_actief.json")
VERZEN = os.path.join(_HIER, "hebreeuws_lezen.json")
TENACH = os.path.join(_HIER, "tenach")

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


# --------------------------------------------------------------- voor- en achtervoegsels
# Bijna de helft van alle woordvormen in de Tenach draagt een voorvoegsel, en dat is precies
# wat een vers ondoorzichtig maakt als je het niet ziet: וְהָאָרֶץ is וְ + הָ + אָרֶץ, en pas
# als je die drie uit elkaar haalt herken je אֶרֶץ dat je gewoon geleerd hebt.
#
# De ontleedcode zegt wélke eraan zitten ('Conj-w, Art | N-fs'), maar niet waar ze ophouden.
# Dat leiden we hier af: elk voorvoegsel is één letter, en we lopen ze in volgorde af.
#
# Eén ding maakt dat lastiger dan het klinkt, en dat is de assimilerende he. Na בְּ, כְּ of
# לְ verdwijnt het lidwoord als letter en blijft alleen de klinker over: בַּיּוֹם is בְּ + הַ +
# יוֹם, met een dagesj in de jod maar zonder he. Staat er dus 'Prep-b, Art' en is er geen he
# te vinden, dan is dat geen fout maar precies wat er hoort te gebeuren.
VOORVOEGSEL_LETTER = {"Conj-w": "ו", "Art": "ה", "Interrog": "ה",
                      "Prep-b": "ב", "Prep-k": "כ", "Prep-l": "ל", "Prep-m": "מ"}
VOORVOEGSEL_NL = {"Conj-w": "en", "Art": "de/het", "Interrog": "vraagwoord",
                  "Prep-b": "in, met, door", "Prep-k": "als, zoals",
                  "Prep-l": "voor, naar, aan", "Prep-m": "uit, van, dan"}
# De persoonsaanduidingen die als achtervoegsel achter de kern kunnen staan.
ACHTERVOEGSEL_NL = {"1cs": "mijn / mij", "2ms": "jouw / jou (m)", "2fs": "jouw / jou (v)",
                    "3ms": "zijn / hem", "3fs": "haar", "1cp": "ons",
                    "2mp": "jullie (m)", "2fp": "jullie (v)", "3mp": "hun / hen (m)",
                    "3fp": "hun / hen (v)"}


def _codes(parsing):
    """De ontleedcode uit elkaar: (voorvoegsels, kern, achtervoegsel).

    Op plaats afgaan kan niet: 'N-msc | 3ms' heeft de kern vooraan en 'Conj-w | N-fs' het
    voorvoegsel. Daarom kijken we naar de code zelf."""
    voor, kern, achter = [], "", ""
    for stuk in str(parsing or "").split("|"):
        for code in stuk.split(","):
            code = code.strip()
            if not code:
                continue
            if code in VOORVOEGSEL_LETTER:
                voor.append(code)
            elif code in ACHTERVOEGSEL_NL:
                achter = code
            elif not kern:
                kern = code
    return voor, kern, achter


def splits_affixen(vorm, parsing):
    """(voorvoegsel, kern, achtervoegsel) als stukken tekst uit de vorm zelf.

    Alleen wat we met zekerheid kunnen aanwijzen wordt afgesplitst. Vinden we een
    voorvoegselletter niet waar hij hoort te staan, dan stoppen we — dan is het beter niets
    te kleuren dan het verkeerde stuk."""
    tekst = str(vorm or "")
    voor_codes, _kern, achter_code = _codes(parsing)
    i = 0
    letters = [n for n, t in enumerate(tekst) if "א" <= t <= "ת"]
    gebruikt = 0
    for code in voor_codes:
        if gebruikt >= len(letters):
            break
        plek = letters[gebruikt]
        if tekst[plek] != VOORVOEGSEL_LETTER[code]:
            # De assimilerende he: geen letter, dus niets te consumeren. Elk ánder verschil
            # betekent dat we het spoor kwijt zijn en dan splitsen we niet verder.
            if code in ("Art", "Interrog"):
                continue
            break
        gebruikt += 1
        # Alles tot en met de klinkertekens die bij deze letter horen.
        volgende = letters[gebruikt] if gebruikt < len(letters) else len(tekst)
        i = volgende
    voorvoegsel, rest = tekst[:i], tekst[i:]

    achtervoegsel = ""
    if achter_code and rest:
        for einde in ACHTERVOEGSEL_VORMEN.get(achter_code, ()):
            if rest.endswith(einde) and len(rest) > len(einde) + 1:
                achtervoegsel = einde
                rest = rest[:-len(einde)]
                break
    return voorvoegsel, rest, achtervoegsel


# Hoe een achtervoegsel geschreven wordt. Meer dan één vorm per persoon, want dat hangt af
# van wat ervoor staat: enkelvoud of meervoud, en welke klinker. Langste eerst, anders zou
# 'הוּ' al matchen op 'ו'. Wat hier niet in staat wordt niet gekleurd — liever niets dan
# het verkeerde stuk.
ACHTERVOEGSEL_VORMEN = {
    "1cs": ("ַי", "ִי", "ֵנִי", "נִי", "י"),
    "2ms": ("ֶיךָ", "ְךָ", "ֶךָ", "ָךְ", "ךָ", "ךְ"),
    "2fs": ("ַיִךְ", "ֵךְ", "ָךְ", "ךְ"),
    "3ms": ("ֵהוּ", "ָיו", "ֵימוֹ", "הוּ", "וֹ", "ו"),
    "3fs": ("ֶיהָ", "ָהּ", "הָ"),
    "1cp": ("ֵינוּ", "ֵנוּ", "נוּ"),
    "2mp": ("ֵיכֶם", "ְכֶם", "כֶם"),
    "2fp": ("ֵיכֶן", "ְכֶן", "כֶן"),
    "3mp": ("ֵיהֶם", "ֵהֶם", "ָם", "הֶם"),
    "3fp": ("ֵיהֶן", "ֵהֶן", "ָן", "הֶן"),
}


def sleutel(woord):
    """Waaronder de voortgang van dit woord wordt bewaard: lijstnummer plus medeklinkers.

    Alleen de medeklinkers is niet genoeg. Dan zouden אִם 'indien' en אֵם 'moeder' dezelfde
    sleutel krijgen, en ook עִם 'met' naast עַם 'volk', שֵׁם 'naam' naast שָׁם 'daar'. Twee en
    dertig sleutels bedienden zo vijfenzestig woorden: je zou עַם beheersen door עִם te
    oefenen. Het lijstnummer maakt ze uit elkaar.

    En andersom: alleen het nummer zou meegaan met een hernummering van de cursuslijst, en
    dan hing je voortgang stilletjes aan een ánder woord. Nu verandert de sleutel als er
    iets verschuift — je raakt dan hooguit voortgang kwijt, en dat is de goede kant om
    fout te gaan. De klinkertekens blijven er bewust buiten: die staan in de lijst niet
    overal hetzelfde genoteerd."""
    return f"{int(woord.get('nummer', 0) or 0)}:{medeklinkers(woord.get('hebreeuws', ''))}"


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


@functools.lru_cache(maxsize=1)
def tenach_index():
    """De 39 boeken: hoe ze heten, hoeveel verzen en hoeveel hoofdstukken."""
    try:
        with open(os.path.join(TENACH, "index.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


# Twee boeken tegelijk in het geheugen. Meer hoeft niet: je leest er één, en met twee kun
# je terugbladeren zonder opnieuw uit te pakken. Het grootste boek is 165 kB ingepakt en
# ongeveer 3 MB uitgepakt, dus twee is te overzien — de hele Tenach tegelijk zou dat
# vijftienvoudig doen, en op de gratis laag van Render is 512 MB alles wat er is.
@functools.lru_cache(maxsize=2)
def laad_tenach_boek(bestand):
    """De verzen van één boek: [{'v': '1:1', 'w': [[vorm, strong, parsing], …]}, …]."""
    pad = os.path.join(TENACH, os.path.basename(str(bestand)))
    try:
        with gzip.open(pad, "rt", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


@functools.lru_cache(maxsize=1)
def laad_verzen():
    """De verzen om te lezen: per vers de woorden met hun Strong-nummer en ontleding.

    Er staat geen vertaling bij, en dat is een keuze: met een vertaling ernaast lees je de
    vertaling. De betekenis van elk los woord staat in de woordenlijst, dus die kan de app
    erbij zoeken — in elkaar zetten doe je zelf. Gemaakt door bouw_hebreeuws_lezen.py."""
    try:
        with open(VERZEN, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


@functools.lru_cache(maxsize=1)
def laad_rijtjes():
    """De vervoegingsrijtjes voor Actief Beheersen, in dezelfde vorm als het Grieks:
    niveau -> categorie -> rijtje -> cellen. Gemaakt door bouw_hebreeuws_actief.py."""
    try:
        with open(RIJTJES, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def aanwezig():
    """Is de Hebreeuwse woordenlijst er? Zo niet, dan laat de app die taal niet zien."""
    return bool(laad_woorden())
