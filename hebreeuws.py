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
import re
import unicodedata

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
    voor_codes, kern_code, achter_code = _codes(parsing)
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
        # De leestekens gaan er eerst af en daarna weer aan. Zonder dit mislukte het bij
        # het laatste woord van élk vers: לְפָנֶיךָ splitst wel en לְפָנֶיךָ׃ niet, en
        # dat is de helft van alle mislukkingen.
        romp, staart = zonder_leesteken(rest)
        # Vergelijken op de genormaliseerde vorm. De klinkertekens staan in de tekst niet
        # altijd in dezelfde volgorde als hoe ik ze hier intyp — in אַרְאֶךָּ staat het
        # dagesj vóór de qamats — en dan mislukt een vergelijking teken voor teken zonder
        # dat je ziet waarom. NFC zet ze bij allebei in dezelfde volgorde en verandert de
        # lengte niet, dus het afsnijden mag daarna op de oorspronkelijke tekst.
        plat = _canon(romp)
        werkwoord = str(kern_code).startswith("V-")
        for einde in ACHTERVOEGSEL_VORMEN.get(achter_code, ()):
            # De energieke nun hoort bij werkwoorden: יַהַרְגֵנִי is 'hij zal mij doden'.
            # Op een naamwoord is die nun deel van de stam — בְּנִי is בֵּן plus 'mijn' en
            # niet בְּ plus 'nî'. Zonder deze regel bleef er van 'mijn zoon' een losse בְּ
            # over, en bij בֵּינִי ('tussen mij') een בֵּי.
            if einde in ALLEEN_BIJ_WERKWOORD.get(achter_code, ()) and not werkwoord:
                continue
            if not plat.endswith(_canon(einde)):
                continue
            stam = romp[:len(romp) - len(einde)]
            # Er moet een woord overblijven, en dat betekent minstens één medeklinker.
            # Eén is genoeg: לוֹ is het voorzetsel ל plus 'hem', en dat is echt zo.
            if not any("א" <= t <= "ת" for t in stam):
                continue
            achtervoegsel = romp[len(stam):] + staart
            rest = stam
            break
    return voorvoegsel, rest, achtervoegsel


# --------------------------------------------------------------------------- de uitgang
# Wat een woord over zichzelf zegt: mannelijk of vrouwelijk, enkelvoud of meervoud, en bij
# een werkwoord wie het doet. Dat staat in de laatste een tot drie tekens, en dat is precies
# wat je bij het lezen moet leren zien — הַשָּׁמַיִם is הַ + שָּׁמַ + יִם, en die יִם vertelt
# je dat het meervoud is.
#
# De tabel komt uit de tekst zelf en niet uit een grammatica. Geteld over de hele Tenach
# eindigt N-mpc 2287 keer op נֵי, 675 op רֵי, 440 op הֵי — allemaal op ֵי, dus dát is de
# uitgang. Wat niet vaak genoeg voorkomt staat er niet in: liever geen kleur dan de
# verkeerde letters aanwijzen.
#
# Twee dingen staan er met opzet níet in.
#
# De persoonsvoorvoegsels van de imperfectum (יִכְתֹּב, תִּכְתֹּב) zijn geen uitgang maar een
# voorvoegsel, en ze staan op dezelfde plaats als de voorzetsels. Die uit elkaar houden
# vraagt een eigen ronde.
#
# En een uitgang die het hele woord zou opeten. מַיִם is 'water' en staat altijd in het
# meervoud; splits je יִם eraf dan houd je één letter over. De eis is daarom dat er
# minstens twee medeklinkers overblijven — een Hebreeuwse stam heeft er in de regel drie.
UITGANG_VORMEN = {
    # naamwoorden en bijvoeglijke naamwoorden, los
    "mp": ("ִים", "יִם"), "md": ("ַיִם", "יִם"), "cd": ("ַיִם", "יִם"),
    "fs": ("ִית", "ָה", "ֶת", "ַת"), "fp": ("וֹת", "ִים"), "fd": ("ַיִם", "יִם"),
    # verbonden (constructus): het meervoud wordt ֵי, het vrouwelijk enkelvoud ַת
    "mpc": ("ֵי",), "cpc": ("ֵי",), "cdc": ("ֵי",), "mdc": ("ֵי",), "fdc": ("ֵי",),
    "fpc": ("וֹת", "ֵי"), "fsc": ("ִית", "ַת", "ֶת"),
    # werkwoorden: de persoonsuitgangen die duidelijk aan het eind staan
    "3cp": ("וּ",), "3mp": ("וּ",), "2mp": ("תֶּם", "וּ"), "3fp": ("נָה",),
    "2fp": ("נָה",), "3fs": ("ָה", "ַת"), "1cs": ("תִּי",), "2ms": ("תָּ",),
    "2fs": ("תְּ", "ִי"), "1cp": ("נוּ",),
}
UITGANG_VORMEN = {code: tuple(sorted(set(v), key=len, reverse=True))
                  for code, v in UITGANG_VORMEN.items()}

# Wat de uitgang betekent, in gewone woorden.
UITGANG_NL = {
    "mp": "mannelijk meervoud", "md": "mannelijk tweevoud",
    "cd": "tweevoud", "fd": "vrouwelijk tweevoud",
    "fs": "vrouwelijk enkelvoud", "fp": "vrouwelijk meervoud",
    "mpc": "mannelijk meervoud, verbonden", "cpc": "meervoud, verbonden",
    "cdc": "tweevoud, verbonden", "mdc": "mannelijk tweevoud, verbonden",
    "fdc": "vrouwelijk tweevoud, verbonden",
    "fpc": "vrouwelijk meervoud, verbonden", "fsc": "vrouwelijk enkelvoud, verbonden",
    "3cp": "3e persoon meervoud", "3mp": "3e persoon mannelijk meervoud",
    "2mp": "2e persoon mannelijk meervoud", "3fp": "3e persoon vrouwelijk meervoud",
    "2fp": "2e persoon vrouwelijk meervoud", "3fs": "3e persoon vrouwelijk enkelvoud",
    "1cs": "1e persoon enkelvoud", "2ms": "2e persoon mannelijk enkelvoud",
    "2fs": "2e persoon vrouwelijk enkelvoud", "1cp": "1e persoon meervoud",
}

# Welke woordsoorten een uitgang krijgen. Een voorzetsel of een voegwoord heeft er geen,
# ook al eindigt het toevallig op dezelfde letters.
_MET_UITGANG = ("N-", "Adj", "V-", "Number", "Pro-")


def uitgang_code(kern_code):
    """Het stukje van de ontleedcode dat over geslacht, getal of persoon gaat.

    'N-mpc' -> 'mpc', 'V-Qal-Perf-3cp' -> '3cp', 'Prep' -> ''. Eigennamen krijgen niets:
    Jeruzalem eindigt op iets dat op een meervoud lijkt, maar dat is de naam."""
    code = str(kern_code or "")
    if not code.startswith(_MET_UITGANG) or "proper" in code:
        return ""
    staart = code.split("-")[-1]
    return staart if staart in UITGANG_VORMEN else ""


def splits_uitgang(stam, kern_code, al_achtervoegsel=False):
    """(stam, uitgang) — de uitgang van geslacht, getal of persoon van de stam afhalen.

    Aanroepen op wat splits_affixen() als kern teruggeeft.

    Ook als er al een bezittelijk achtervoegsel staat. Dat leverde eerst niets op omdat de
    meervoudsuitgang vaak ín dat achtervoegsel zit — אֲבֹתֶיךָ is 'jouw vaders' en de jod
    van het meervoud staat in ֶיךָ. Maar niet altijd: בְּנוֹתָיו is 'zijn dochters' en daar
    staat de vrouwelijke meervoudsuitgang וֹת er los voor. Die hoort dus gekleurd.

    Er moet minstens één medeklinker overblijven. Twee was veiliger, maar dan bleef מַיִם
    ('water', altijd meervoud) ongekleurd, en juist bij zo'n woord wil je zien dat die
    יִם het meervoud is."""
    stam = str(stam or "")
    code = uitgang_code(kern_code)
    if not code:
        return stam, ""
    romp, staart = zonder_leesteken(stam)
    plat = _canon(romp)
    for einde in UITGANG_VORMEN[code]:
        if not plat.endswith(_canon(einde)):
            continue
        rest = romp[:len(romp) - len(einde)]
        if not any("א" <= t <= "ת" for t in rest):
            continue
        return rest, romp[len(rest):] + staart
    return stam, ""


# --------------------------------------------------------- het persoonsvoorvoegsel
# De imperfectum zet vooraan wie het doet, waar de perfectum dat achteraan doet: כָּתַב is
# 'hij schreef' en יִכְתֹּב 'hij zal schrijven'. Die ene letter vooraan is dus geen los
# woordje maar de persoon, en hij staat op dezelfde plaats als de voorzetsels — daarom
# krijgt hij een eigen kleur en een eigen vinkje.
#
# Ook de wajjiqtol hoort erbij: וַיֹּאמֶר is וַ ('en') plus יֹּאמֶר, en die jod is de
# persoon. Het voegwoord is er dan al af voordat we hier komen.
PERSOON_VOOR_LETTER = {"1cs": "א", "1cp": "נ", "3ms": "י", "3mp": "י",
                       "2ms": "ת", "2fs": "ת", "2mp": "ת", "2fp": "ת",
                       "3fs": "ת", "3fp": "ת"}
PERSOON_VOOR_NL = {"1cs": "ik", "1cp": "wij", "3ms": "hij", "3mp": "zij (m)",
                   "2ms": "jij (m)", "2fs": "jij (v)", "2mp": "jullie (m)",
                   "2fp": "jullie (v)", "3fs": "zij (v)", "3fp": "zij (v, mv)"}


def persoon_voor_code(kern_code):
    """De persoon van een imperfectum, of ''. Alleen bij de imperfectum en de wajjiqtol:
    de perfectum en de gebiedende wijs hebben geen letter vooraan."""
    code = str(kern_code or "")
    if not code.startswith("V-") or "Imperf" not in code:
        return ""
    staart = code.split("-")[-1]
    return staart if staart in PERSOON_VOOR_LETTER else ""


def splits_persoon_voor(stam, kern_code):
    """(persoonsvoorvoegsel, rest). Alleen als de letter er ook echt staat."""
    stam = str(stam or "")
    code = persoon_voor_code(kern_code)
    if not code:
        return "", stam
    letters = [n for n, t in enumerate(stam) if "א" <= t <= "ת"]
    if not letters or stam[letters[0]] != PERSOON_VOOR_LETTER[code]:
        return "", stam
    # Er moet een stam overblijven met minstens twee medeklinkers: een werkwoordstam heeft
    # er drie, en zonder deze eis zou תֵּת ('geven') zijn eigen stam opeten.
    if len(letters) < 3:
        return "", stam
    grens = letters[1]
    return stam[:grens], stam[grens:]


# De stukken waaruit een vorm bestaat, met wat ze vertellen. Beide apps kleuren hiermee, en
# de namen hier zijn dus ook de namen van de vinkjes en van de legenda.
SOORTEN = {
    "voor": "los woordje vooraan (en, de, in, als, naar, uit)",
    "persoon_voor": "wie het doet, vooraan (imperfectum)",
    "stam": "de stam: het woord uit je woordenlijst",
    "uitgang_getal": "geslacht en getal (m/v, enkelvoud/meervoud)",
    "uitgang_persoon": "wie het doet, achteraan (perfectum)",
    "bezit": "van wie: mijn, jouw, zijn, haar",
    "leesteken": "sof pasuq, maqaf of paseq — hoort bij geen enkel stuk",
}

# De kleur per soort. Die staat hier en niet in de apps, omdat beide apps hem moeten delen:
# een uitgang die in de snelle app amber is en in de uitgebreide roze maakt het kleuren
# waardeloos. Vijf kleuren, want een woord kan alle vijf de stukken tegelijk hebben.
#
# Weg van rood en groen (die betekenen fout en goed) en onderling ver genoeg uit elkaar. De
# twee die het meest op elkaar lijken, cyaan en turkoois, staan aan weerszijden van het
# woord — een voorvoegsel vooraan en een bezittelijk achtervoegsel achteraan — dus die zijn
# ook aan hun plaats te herkennen.
KLEUREN = {
    "voor": "#33ccff",             # cyaan   los woordje vooraan
    "persoon_voor": "#b98cff",     # paars   wie het doet, vooraan
    "uitgang_getal": "#f6c23e",    # amber   geslacht en getal
    "uitgang_persoon": "#ff8fb3",  # roze    wie het doet, achteraan
    "bezit": "#43d9c0",            # turkoois  van wie
}


def ontleed_vorm(vorm, parsing):
    """De vorm in stukken: [(tekst, soort), …], samen precies het hele woord.

    De soorten staan in SOORTEN, in de volgorde waarin ze in een woord voorkomen. De
    uitgang is in twee soorten gesplitst omdat het twee verschillende dingen zijn: een
    werkwoord zegt met zijn uitgang wie het doet, een naamwoord wat voor woord het is.

    Wat niet met zekerheid aan te wijzen is komt in 'stam' terecht. Liever een stuk te
    weinig kleuren dan de verkeerde letters aanwijzen."""
    voor, kern, bezit = splits_affixen(vorm, parsing)
    _v, kern_code, _a = _codes(parsing)
    persoon_voor, kern = splits_persoon_voor(kern, kern_code)
    stam, uitgang = splits_uitgang(kern, kern_code)
    u_soort = f"uitgang_{uitgang_soort(kern_code) or 'getal'}"
    # Zit het meervoud in het achtervoegsel, haal het er dan uit: ֵיהֶם is ֵי plus הֶם.
    if bezit and not uitgang:
        uitgang, bezit = splits_meervoud_uit_bezit(bezit, kern_code)

    stukken = []
    for tekst, soort in ((voor, "voor"), (persoon_voor, "persoon_voor"),
                         (stam, "stam"), (uitgang, u_soort), (bezit, "bezit")):
        if not tekst:
            continue
        romp, staart = zonder_leesteken(tekst)
        if romp:
            stukken.append((romp, soort))
        if staart:
            stukken.append((staart, "leesteken"))
    return stukken


def uitleg_stukken(vorm, parsing):
    """Wat elk gekleurd stuk betekent: [(tekst, soort, uitleg), …].

    Alleen wat er ook echt gekleurd staat. Anders komt er 'mannelijk meervoud' bij een woord
    waar niets is aangewezen, en dan zoek je naar iets wat er niet staat."""
    voor_codes, kern_code, bezit_code = _codes(parsing)
    uit = []
    for tekst, soort in ontleed_vorm(vorm, parsing):
        if soort == "voor":
            uit.append((tekst, soort, " + ".join(VOORVOEGSEL_NL[c] for c in voor_codes)))
        elif soort == "persoon_voor":
            code = persoon_voor_code(kern_code)
            uit.append((tekst, soort, PERSOON_VOOR_NL.get(code, code)))
        elif soort.startswith("uitgang"):
            code = uitgang_code(kern_code)
            uit.append((tekst, soort, UITGANG_NL.get(code, code)))
        elif soort == "bezit":
            uit.append((tekst, soort, ACHTERVOEGSEL_NL.get(bezit_code, bezit_code)))
    return uit


def splits_meervoud_uit_bezit(bezit, kern_code):
    """(meervoudsuitgang, bezittelijk deel) — de jod van het meervoud uit een achtervoegsel.

    De lange achtervoegselvormen bestaan uit twee dingen. In דִּבְרֵיהֶם ('hun woorden') is
    ֵי het meervoud en הֶם 'hun'; in דְּבָרָיו ('zijn woorden') is ָי het meervoud en ו
    'zijn'. Dat zijn twee verschillende dingen en dus twee kleuren.

    Alleen als de ontleding ook echt meervoud zegt. אָבִיו is 'zijn vader', enkelvoud, met
    een jod die er historisch bij hoort — die mag niet als meervoud gekleurd worden."""
    bezit = str(bezit or "")
    code = uitgang_code(kern_code)
    if not code or code[:1].isdigit() or not any(t in code for t in ("p", "d")):
        return "", bezit          # geen meervoud of tweevoud in de kern
    # Het meervoud is een klinkerteken plus een jod, aan het begin van het achtervoegsel.
    letters = [n for n, t in enumerate(bezit) if "א" <= t <= "ת"]
    if len(letters) < 2 or bezit[letters[0]] != "י":
        return "", bezit
    grens = letters[1]
    return bezit[:grens], bezit[grens:]


def uitgang_soort(kern_code):
    """Waar de uitgang over gaat: 'persoon' of 'getal'.

    Een werkwoord zegt met zijn uitgang wie het doet, een naamwoord wat voor woord het is.
    De code verraadt het: die van een persoon begint met een cijfer (3cp, 1cs), die van
    geslacht en getal niet (mp, fsc). Een deelwoord hoort bij de tweede groep, en dat is
    ook zo — כֹּתְבִים is 'schrijvende' in het mannelijk meervoud."""
    code = uitgang_code(kern_code)
    if not code:
        return ""
    return "persoon" if code[:1].isdigit() else "getal"


# Sof pasuq (het dubbelpuntje aan het eind van een vers), de maqaf en de paseq (het streepje
# dat woorden scheidt). De letters פ en ס die een alinea afsluiten staan altijd ná een sof
# pasuq — los zijn het gewone letters, dus die mogen alleen in dat gezelschap weg.
_LEESTEKEN = re.compile(r"(׃[פס]*|[־׀])$")


def zonder_leesteken(tekst):
    """('לְפָנֶיךָ׃') -> ('לְפָנֶיךָ', '׃'). Wat eraf ging komt er ongewijzigd bij terug,
    zodat de drie stukken samen nog steeds het hele woord zijn."""
    treffer = _LEESTEKEN.search(str(tekst or ""))
    if not treffer:
        return tekst, ""
    return tekst[:treffer.start()], treffer.group()


def _canon(tekst):
    """Klinkertekens in vaste volgorde, zodat vergelijken werkt. Zie splits_affixen()."""
    return unicodedata.normalize("NFC", str(tekst or ""))


# Hoe een achtervoegsel geschreven wordt. Meer dan één vorm per persoon, want dat hangt af
# van wat ervoor staat: enkelvoud of meervoud, en welke klinker. De reeks wordt hieronder
# op lengte gesorteerd, want anders zou 'ִי' al matchen binnen 'ֵנִי' en bleef er een losse
# nun achter. Wat hier niet in staat wordt niet gekleurd — liever niets dan het verkeerde
# stuk.
#
# De laatste in elke reeks is de kale medeklinker. Die mag zo kaal, want we komen hier
# alleen als de ontleding al zegt dát er een achtervoegsel van deze persoon staat; dan is
# de laatste medeklinker van het woord die van het achtervoegsel. Bij מְאַסְתִּים ('ik
# verwierp hen') is dat gewoon de ם.
#
# Eén ontbreekt met opzet: de kale ה voor 3fs. Dit bestand geeft de richtings-he dezelfde
# code als het bezittelijke achtervoegsel — סְדֹמָה staat er als 'N-proper-fs | 3fs' maar
# betekent 'naar Sodom' en niet 'haar Sodom'. Wat ze in de tekst onderscheidt is het puntje
# in de ה: הּ is 'haar', ה niet. Vandaar wel 'ָהּ' en niet 'ָה'.
ACHTERVOEGSEL_VORMEN = {
    "1cs": ("ֵנִי", "ַנִי", "נִּי", "נִי", "ַי", "ָי", "ִי", "י"),
    "2ms": ("ֶיךָ", "ֵיךָ", "ְךָ", "ֶךָ", "ָךְ", "כָּה", "כָה", "ךָּ", "ךָ", "ךְ", "ך"),
    "2fs": ("ַיִךְ", "ֵךְ", "ָךְ", "ֵךָ", "ךְ", "ך"),
    # 'ֹה' is de oude spelling van 'zijn': אָהֳלֹה naast אָהֳלוֹ.
    "3ms": ("ֵימוֹ", "ֶנּוּ", "ַנּוּ", "ֵהוּ", "ָיו", "ִיו", "הוּ", "נּוּ", "וֹ", "ֹה", "ו"),
    "3fs": ("ֶיהָ", "ָיהָ", "ֶנָּה", "ַנָּה", "נָּה", "ָהּ", "הּ", "הָ"),
    "1cp": ("ֵינוּ", "ֶנּוּ", "ַנּוּ", "ֵנוּ", "נּוּ", "נוּ"),
    "2mp": ("ֵיכֶם", "ְכֶם", "כֶּם", "כֶם"),
    "2fp": ("ֵיכֶן", "ְכֶן", "כֶּן", "כֶן"),
    "3mp": ("ֵיהֶם", "ֵהֶם", "ָמוֹ", "הֶם", "מוֹ", "ָם", "ם"),
    "3fp": ("ֵיהֶן", "ֵהֶן", "ָנָה", "הֶן", "ָן", "ן"),
}
# Langste eerst. Handmatig op orde houden gaat een keer mis, dus dat doet de computer.
ACHTERVOEGSEL_VORMEN = {code: tuple(sorted(set(vormen), key=len, reverse=True))
                        for code, vormen in ACHTERVOEGSEL_VORMEN.items()}

# Deze spellingen mogen alleen bij een werkwoord: het is de energieke nun, die tussen een
# werkwoord en zijn lijdend voorwerp komt. Zonder dagesj, want 'נִּי' (מִמֶּנִּי, 'van mij')
# kan wel overal.
ALLEEN_BIJ_WERKWOORD = {"1cs": ("ֵנִי", "ַנִי", "נִי")}


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
    """De verzen van één boek: [{'v': '1:1', 'w': [[vorm, strong, parsing, …], …]}, …].

    Pak de woorden uit met woorden_van(); dan hoeft niemand te weten hoeveel velden er in
    een lijstje staan."""
    pad = os.path.join(TENACH, os.path.basename(str(bestand)))
    try:
        with gzip.open(pad, "rt", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


# De velden van één woord, in de volgorde waarin bouw_tenach.py ze wegschrijft.
TENACH_VELDEN = ("vorm", "strong", "parsing", "translit", "engels")


def woorden_van(vers):
    """De woorden van één vers als dicts, met altijd alle velden.

    In het bestand staat elk woord als een lijstje en niet als een dict: de veldnamen
    zouden er 300.670 keer bij staan, en dat is bijna de helft van het bestand. Hier gaan
    ze weer aan, zodat de app w['engels'] kan schrijven in plaats van w[4].

    Werkt op beide leesbestanden: de boeken uit tenach/ noemen het veld 'w', en de duizend
    uitgezochte verzen in hebreeuws_lezen.json noemen het 'woorden'.

    Een bestand dat nog van vóór het Engels is heeft maar drie velden. Die krijgen hier een
    leeg veld, zodat een oude werkkopie blijft werken in plaats van om te vallen op een
    'not enough values to unpack'."""
    rijen = vers.get("w")
    if rijen is None:
        rijen = vers.get("woorden")
    uit = []
    for rij in rijen or ():
        rij = list(rij) + [""] * (len(TENACH_VELDEN) - len(rij))
        uit.append(dict(zip(TENACH_VELDEN, rij)))
    return uit


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
