# -*- coding: utf-8 -*-
"""Koppelt de Hebreeuwse woordenschat aan de getagde bijbeltekst en vult
hebreeuws_woorden.json aan met Strong-nummer, frequentie en vindplaatsen.

Waarom dit niet met een simpele vergelijking kan:

  * In de tekst plakken voorvoegsels aan het woord vast — וְהָאָרֶץ is וְ + הַ + אֶרֶץ.
    Vergelijk je de kale lijstvorm met wat er in de tekst staat, dan mis je het woord.
    De parsingkolom zegt gelukkig precies welke voorvoegsels eraan zitten ('Conj-w, Art |
    N-fs'), dus we kunnen de vormen zónder voorvoegsel eruit filteren.
  * De tekst draagt cantillatietekens (de zangtekens boven en onder de letters); de
    woordenlijst niet. Die moeten eraf voordat je vergelijkt.
  * Op alleen medeklinkers vergelijken is te grof: אֶל (tot), אַל (niet) en אֵל (God) zijn
    dan één woord. Daarom eerst op de volledige vocalisatie, en pas daarna op medeklinkers
    — en dan alleen als er precies één kandidaat is.

Het Strong-nummer in de spreadsheet hoort bij het lemma, niet bij de vorm, dus zodra een
woord gekoppeld is tellen álle vormen ervan mee voor de frequentie.

Draaien:  py gereedschap/koppel_hebreeuws.py
"""
import collections
import json
import os
import re
import sys
import unicodedata

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHEET = os.path.join(REPO, "hebreeuws app", "Hele bijbel.xlsx")
WOORDEN = os.path.join(REPO, "hebreeuws_woorden.json")

FINAAL = {"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"}

# Voorvoegsels die de parsing apart benoemt. Staat er zo'n code in, dan is de vorm niet
# kaal en deugt hij niet als lemma-kandidaat.
VOORVOEGSEL = re.compile(r"\b(Conj-w|Art|Prep-[bklm]|Prep\b)", re.IGNORECASE)

# Deze zes komen nooit los voor; ze plakken altijd aan het volgende woord vast. Ze staan
# dus niet als eigen regel in de spreadsheet, maar wél als code in de parsing. Zo tellen we
# ze toch — en het zijn de meest voorkomende woorden van het Hebreeuws, dus overslaan zou
# zonde zijn. Een eigen Strong-nummer hebben ze niet.
LOSSE_VOORVOEGSELS = {"וְ": "Conj-w", "הַ": "Art", "בְּ": "Prep-b",
                      "כְּ": "Prep-k", "לְ": "Prep-l", "הֲ": "Interrog"}
VOORVOEGSEL_CODES = sorted(set(LOSSE_VOORVOEGSELS.values()))
VOORVOEGSEL_ZOEK = {c: re.compile(r"(?:^|[,|]\s*)" + re.escape(c) + r"\b")
                    for c in VOORVOEGSEL_CODES}


def kaal(tekst):
    """Zonder cantillatie, maqaf en verspunctuatie — vocalisatie blijft staan."""
    uit = []
    for t in unicodedata.normalize("NFC", str(tekst)):
        o = ord(t)
        if 0x0591 <= o <= 0x05AF:        # zangtekens
            continue
        if o in (0x05BD, 0x05BE, 0x05C0, 0x05C3, 0x05C6, 0x05F3, 0x05F4):
            continue                     # meteg, maqaf, paseq, sof pasuq, leestekens
        uit.append(t)
    return "".join(uit).strip()


def medeklinkers(tekst):
    return "".join(FINAAL.get(t, t) for t in str(tekst) if "א" <= t <= "ת")


# Elf woorden zijn niet automatisch te vinden, en dat heeft telkens een aanwijsbare reden.
# In plaats van de heuristiek nóg slimmer te maken — waarmee je stilletjes fout gaat raden —
# staan ze hier met de hand vast, elk met het bewijs uit de spreadsheet erbij. Zo is de
# keuze na te lopen en verandert er niets als het script slimmer wordt.
HANDMATIG = {
    142: ("4940", "typefout in de lijst: eindigt op een chet, moet een he zijn (303x)",
          "מִשְׁפָּחָה"),
    194: ("3559", "holle wortel: staat in de tekst als נָכוֹן, nooit als כּוּן (219x)"),
    210: ("5337", "komt alleen in Nifal/Piel/Hifil voor: מַצִּיל (213x)"),
    215: ("6430", "staat vrijwel altijd in het meervoud: פְּלִשְׁתִּים (288x)"),
    301: ("5117", "holle wortel: יָנוּחַ (141x)"),
    302: ("5127", "holle wortel: וַיָּנֻסוּ (158x)"),
    323: ("834", "korte vorm van אֲשֶׁר; plakt als שֶׁ־ aan het volgende woord en heeft "
                 "daarom geen eigen regel in de tekst"),
    341: ("2220", "de alef komt uit '(de) arm' in de lijst; het woord is זְרוֹעַ (91x)"),
    344: ("753", "beschadigd in de PDF (95x)", "אֹרֶךְ"),
    346: ("1157", "voorzetsel בַּעַד; komt vrijwel alleen met achtervoegsel voor"),
    203: ("4397", "de letters staan door elkaar in de PDF (214x)", "מַלְאָךְ"),
    406: ("7993", "alleen Hifil: וַיַּשְׁלֵךְ (125x)"),
}


KLINKERS = set(range(0x05B0, 0x05BC)) | {0x05C7}


def dubbele_klinker(vorm):
    """Twee klinkertekens op één letter — dat kan niet en wijst op een typefout."""
    op_deze_letter = 0
    for teken in vorm:
        if ord(teken) in KLINKERS:
            op_deze_letter += 1
            if op_deze_letter > 1:
                return True
        elif "א" <= teken <= "ת":
            op_deze_letter = 0
    return False


def deelrij(wortel, vorm):
    """Komen de wortelmedeklinkers in deze volgorde in de vorm voor?"""
    if not wortel or len(wortel) < 2 or len(vorm) > len(wortel) + 4:
        return False
    i = 0
    for teken in vorm:
        if i < len(wortel) and teken == wortel[i]:
            i += 1
    return i == len(wortel)


def bijna(a, b):
    """Verschillen a en b in precies één letter (vervangen, toevoegen of weglaten)?"""
    if abs(len(a) - len(b)) > 1 or a == b:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    lang, kort = (a, b) if len(a) > len(b) else (b, a)
    for i in range(len(lang)):
        if lang[:i] + lang[i + 1:] == kort:
            return True
    return False


def lees_sheet():
    """Per Strong-nummer: hoe vaak, welke kale vormen, en een paar vindplaatsen."""
    import openpyxl
    wb = openpyxl.load_workbook(SHEET, read_only=True, data_only=True)
    ws = wb["Hebreeuws"]
    telling = collections.Counter()
    werkwoord = collections.Counter()                          # hoe vaak als werkwoord getagd
    vormen = collections.defaultdict(collections.Counter)      # strong -> kale vorm -> n
    lemmas = collections.defaultdict(collections.Counter)      # strong -> vorm zónder voorvoegsel
    plaatsen = collections.defaultdict(list)
    voorvoegsels = collections.Counter()
    vers = ""
    for rij in ws.iter_rows(min_row=2, values_only=True):
        vorm, parsing, strong, verwijzing = rij[6], rij[9], rij[11], rij[13]
        if verwijzing and str(verwijzing).strip():
            vers = str(verwijzing).strip()
        p = str(parsing or "")
        for code in VOORVOEGSEL_CODES:
            if re.search(VOORVOEGSEL_ZOEK[code], p):
                voorvoegsels[code] += 1
        if not (vorm and strong):
            continue
        s = str(strong).strip()
        v = kaal(vorm)
        if not medeklinkers(v):
            continue
        telling[s] += 1
        # Alles achter de laatste | is het woord zelf; begint dat met V-, dan is het een
        # werkwoordsvorm. Dat onderscheidt דבר 'spreken' van דָּבָר 'woord'.
        if p.rsplit("|", 1)[-1].strip().startswith("V-"):
            werkwoord[s] += 1
        vormen[s][v] += 1
        if not VOORVOEGSEL.search(p):
            lemmas[s][v] += 1
        if len(plaatsen[s]) < 3:
            plaatsen[s].append({"vers": vers, "vorm": v})
    wb.close()
    return telling, werkwoord, vormen, lemmas, plaatsen, voorvoegsels


def main():
    if not os.path.exists(SHEET):
        sys.exit(f"Niet gevonden: {SHEET}\nZet 'Hele bijbel.xlsx' terug in 'hebreeuws app'.")
    with open(WOORDEN, encoding="utf-8") as f:
        woorden = json.load(f)

    print("bijbeltekst inlezen…")
    telling, werkwoord, vormen, lemmas, plaatsen, voorvoegsels = lees_sheet()
    print(f"  {sum(telling.values())} woordvormen, {len(telling)} Strong-nummers")

    # Zoeksleutels: eerst op volledige vocalisatie, daarna op medeklinkers, en dat alles
    # eerst over de kale vormen. Woorden die in de tekst altijd een voorvoegsel dragen —
    # כְּמוֹ, לְבַד, מִמַּעַל — hebben helemaal geen kale vorm, dus daarna nog een ronde over
    # álle vormen. Daar is de kans op een misser groter, dus die telt alleen als er precies
    # één kandidaat overblijft.
    op_vorm = collections.defaultdict(set)
    op_medeklinkers = collections.defaultdict(set)
    for s, teller in lemmas.items():
        for v in teller:
            op_vorm[kaal(v)].add(s)
            op_medeklinkers[medeklinkers(v)].add(s)
    alle_vorm = collections.defaultdict(set)
    alle_medeklinkers = collections.defaultdict(set)
    for s, teller in vormen.items():
        for v in teller:
            alle_vorm[kaal(v)].add(s)
            alle_medeklinkers[medeklinkers(v)].add(s)

    raak_voorv = niet = 0
    manieren = collections.Counter()
    dubbel = []
    for w in woorden:
        # Een voorvoegsel komt niet als los woord in de tekst voor; die tellen we uit de
        # parsing. Ze hebben geen Strong-nummer en dat hoeft ook niet.
        code = LOSSE_VOORVOEGSELS.get(kaal(w["hebreeuws"]))
        if code:
            w["strong"] = ""
            w["parsing_code"] = code
            w["frequentie"] = voorvoegsels[code]
            w["vindplaatsen"] = []
            raak_voorv += 1
            continue
        kandidaten = set()
        manier = ""
        # De met de hand nagelopen gevallen gaan vóór alles: die zijn geverifieerd, en een
        # automatische route zou er alleen maar naast kunnen gokken.
        if w["nummer"] in HANDMATIG:
            s, waarom, *vorm = HANDMATIG[w["nummer"]]
            if s in telling:
                kandidaten, manier = {s}, "handmatig"
                w["handmatig"] = waarom
                if vorm and vorm[0]:
                    w["lijstvorm"] = w["hebreeuws"]
                    w["hebreeuws"] = vorm[0]
                    w["medeklinkers"] = medeklinkers(vorm[0])
        for schrijfwijze in ([] if kandidaten else
                             [w["hebreeuws"]] + w.get("varianten", [])):
            k = op_vorm.get(kaal(schrijfwijze))
            if k:
                kandidaten, manier = k, "vocalisatie"
                break
        if not kandidaten:
            for schrijfwijze in [w["hebreeuws"]] + w.get("varianten", []):
                k = op_medeklinkers.get(medeklinkers(schrijfwijze))
                if k:
                    kandidaten, manier = k, "medeklinkers"
                    break
        if not kandidaten:
            # Nu ook de vormen mét voorvoegsel, maar alleen bij één kandidaat.
            for index, naam in ((alle_vorm, "vorm-met-voorvoegsel"),
                                (alle_medeklinkers, "medeklinkers-met-voorvoegsel")):
                for schrijfwijze in [w["hebreeuws"]] + w.get("varianten", []):
                    sleutel = (kaal(schrijfwijze) if index is alle_vorm
                               else medeklinkers(schrijfwijze))
                    k = index.get(sleutel)
                    if k and len(k) == 1:
                        kandidaten, manier = k, naam
                        break
                if kandidaten:
                    break
        if not kandidaten and w.get("stammen"):
            # Werkwoorden met een zwakke wortel (נוּח, נוּס, כּוּן) staan in de tekst nooit in
            # hun woordenboekvorm: de waw valt weg of er komt een stamvoorvoegsel voor.
            # Dan zoeken we de wortelmedeklinkers als deelrij in de vorm, en accepteren we
            # dat alleen als er één werkwoord uit komt.
            wortel = medeklinkers(w["hebreeuws"])
            treffers = {s for sleutel, groep in alle_medeklinkers.items()
                        if deelrij(wortel, sleutel)
                        for s in groep if werkwoord[s] > telling[s] / 2}
            if len(treffers) == 1:
                kandidaten, manier = treffers, "wortel"
        if not kandidaten:
            # Laatste redmiddel: één letter verschil. De cursuslijst bevat een enkele
            # typefout (מִשְׁפָּחָח met een chet in plaats van een he), en zo komt dat woord
            # er alsnog in. Alleen als er precies één kandidaat overblijft, anders raden we.
            doel = medeklinkers(w["hebreeuws"])
            dichtbij = {s for sleutel, groep in op_medeklinkers.items()
                        if bijna(sleutel, doel) for s in groep}
            if len(dichtbij) == 1:
                kandidaten, manier = dichtbij, "bijna"
        if not kandidaten:
            # Een paar regels komen in leesvolgorde uit de PDF in plaats van in
            # opslagvolgorde: מַלְאָךְ wordt dan ךְָמַלְא. Omgekeerd proberen dus — en alleen
            # aannemen als er precies één kandidaat uit komt, anders raden we maar wat.
            achterstevoren = w["medeklinkers"][::-1]
            k = op_medeklinkers.get(achterstevoren) or alle_medeklinkers.get(achterstevoren)
            if k and len(k) == 1:
                kandidaten, manier = k, "omgekeerd"
        if not kandidaten:
            w["strong"], w["frequentie"], w["vindplaatsen"] = "", 0, []
            niet += 1
            continue
        # Meer dan één kandidaat. Staat er in de cursuslijst een stamformatie bij, dan is
        # het een werkwoord, en kiezen we een Strong die in de tekst ook als werkwoord is
        # getagd. Anders zou דבר 'spreken' het zelfstandig naamwoord דָּבָר 'woord' worden,
        # want dat komt vaker voor.
        keuze = list(kandidaten)
        if w.get("stammen"):
            alleen_ww = [s for s in keuze if werkwoord[s] > telling[s] / 2]
            if alleen_ww:
                keuze = alleen_ww
        beste = max(keuze, key=lambda s: telling[s])
        if len(kandidaten) > 1:
            dubbel.append((w, sorted(kandidaten, key=lambda s: -telling[s])))
        w["strong"] = beste
        w["frequentie"] = telling[beste]
        w["vindplaatsen"] = plaatsen[beste]
        # De vorm uit de bijbeltekst is betrouwbaarder dan de cursuslijst; twee woorden
        # hebben daar een typefout in de vocalisatie.
        lemma = lemmas[beste].most_common(1)
        if lemma:
            w["lemma_tekst"] = lemma[0][0]
        # Staat de vorm in de lijst aantoonbaar verkeerd — omgekeerd, met een typefout, of
        # met twee klinkertekens op één letter — dan nemen we de vorm uit de bijbeltekst
        # over en bewaren we wat er in de cursuslijst stond.
        scheef = manier == "omgekeerd" or dubbele_klinker(w["hebreeuws"])
        if scheef and lemma:
            w["lijstvorm"] = w["hebreeuws"]
            w["hebreeuws"] = lemma[0][0]
            w["medeklinkers"] = medeklinkers(w["hebreeuws"])
        manieren[manier] += 1

    with open(WOORDEN, "w", encoding="utf-8") as f:
        json.dump(woorden, f, ensure_ascii=False, indent=1)

    for naam, n in manieren.most_common():
        print(f"gekoppeld via {naam:30s} {n}")
    print(f"gekoppeld via {'parsing (voorvoegsels)':30s} {raak_voorv}")
    print(f"{'niet gevonden':44s} {niet}")
    if dubbel:
        print(f"\nmeer dan één kandidaat ({len(dubbel)}) — de meest voorkomende is gekozen:")
        for w, ks in dubbel[:10]:
            uitleg = ", ".join(f"{s} ({telling[s]}x)" for s in ks[:3])
            print(f"  {w['hebreeuws']:12s} {w['nederlands'][:30]:32s} {uitleg}")
    ongekoppeld = [w for w in woorden if not w["strong"] and not w.get("parsing_code")]
    if ongekoppeld:
        print(f"\nniet gevonden ({len(ongekoppeld)}):")
        for w in ongekoppeld[:12]:
            print(f"  {w['nummer']:3d} {w['hebreeuws']:12s} {w['nederlands'][:44]}")


if __name__ == "__main__":
    main()
