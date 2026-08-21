# -*- coding: utf-8 -*-
"""Bouwt hebreeuws_ontleden.json: oefenstof om Hebreeuwse woordvormen te ontleden.

Dit verving een eerdere versie die de andere kant op werkte: die gaf je de losse delen
(כְּ + הַ + חֶסֶד) en vroeg de vorm te maken. Twee dingen waren daar mis mee.

Ten eerste is het de verkeerde richting. Het Hebreeuws is hier om te lézen, en dan kom je
een vorm tegen en moet je zien wat erin zit -- niet omgekeerd. Bij het Grieks is dat anders,
want daar hoort ook productie bij.

Ten tweede waren de afleiders te makkelijk. Bij de vraag כְּ + הַ + חֶסֶד begonnen drie van
de vier antwoorden met een ב, dus je kon hem goed hebben door naar de eerste letter te
kijken. Daarom staan de antwoordmogelijkheden nu ín dit bestand: ze worden hier gekozen en
niet in de app, zodat er over nagedacht is.

Drie soorten vragen, alle drie uit de hele Tenach:

  1. Welke woordjes zitten erin?
     בַּיּוֹם -> 'in + de/het'. Precies hier zit de klankregel: na בְּ, כְּ of לְ verdwijnt
     de ה van het lidwoord en blijft alleen zijn klinker over. Wie dat niet weet leest
     בַּיּוֹם als 'in een dag' in plaats van 'op die dag'.

  2. Welk woord is dit?
     וּבְדִבְרֵיהֶם -> דָּבָר. De vaardigheid waar het bij lezen om gaat: de aanhangsels
     wegdenken en het woord terugvinden dat je geleerd hebt.

  3. Wie doet het?
     תִּשְׁמְרוּ -> 'jullie'. Uit het voorvoegsel, de uitgang, of allebei.

Draaien:  py gereedschap/bouw_hebreeuws_ontleden.py
"""
import collections
import json
import os
import random
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

import uitvoer

uitvoer.zet_utf8()

import hebreeuws as H

UIT = os.path.join(REPO, "hebreeuws_ontleden.json")
PER_GROEP = 150
random.seed(20260821)


def nl_van_voorvoegsels(codes):
    """'Conj-w, Prep-b, Art' -> 'en + in + de/het'. Kort, want het staat op een knop."""
    kort = {"Conj-w": "en", "Art": "de/het", "Interrog": "vraagwoord?",
            "Prep-b": "in", "Prep-k": "als", "Prep-l": "voor/naar", "Prep-m": "uit/van"}
    return " + ".join(kort[c] for c in codes if c in kort)


def _klinkerdeel(woord):
    """Welk deel van de tekens een klinkerteken is.

    De cursuslijst geeft werkwoorden als kale medeklinkers (אמר, דבר) en naamwoorden mét
    klinkers (אֶרֶץ). Zet je die door elkaar in één rijtje antwoorden, dan valt het antwoord
    op door zijn vorm en niet door zijn betekenis — precies de gok die deze oefening moet
    uitsluiten."""
    tekens = [t for t in str(woord or "") if t.strip()]
    if not tekens:
        return 0.0
    return sum(1 for t in tekens if not ("א" <= t <= "ת")) / len(tekens)


def _gelijkenis(goed):
    """Hoe goed een kandidaat als afleider naast dit antwoord kan staan.

    Twee dingen tegelijk: ongeveer even lang, en ongeveer even veel klinkertekens."""
    lengte = len(H.medeklinkers(goed))
    deel = _klinkerdeel(goed)
    return lambda x: (-abs(len(H.medeklinkers(x)) - lengte)
                      - 6 * abs(_klinkerdeel(x) - deel))


def kies_afleiders(goed, alle, hoeveel=3, lijkt_op=None):
    """Afleiders die je niet kunt uitsluiten zonder de vraag te snappen.

    lijkt_op is een functie die zegt hoe goed een kandidaat op het antwoord lijkt; die
    komen eerst. Zo krijg je bij 'welk woord is dit' geen antwoord dat drie letters langer
    is dan de rest, want dan gok je op lengte.

    En daarna nog een controle die belangrijker bleek dan hij lijkt: begint het antwoord
    als enige met een andere letter, dan wijs je de vreemde eend aan zonder de vraag te
    lezen. Bij וַיַּרְא -> רָאָה stonden er drie afleiders met een א en één met een ר, en
    dan hoef je geen Hebreeuws te kennen. Er moet dus minstens één afleider zijn die met
    dezelfde letter begint als het antwoord."""
    kandidaten = [x for x in alle if x != goed]
    if not kandidaten:
        return []
    if lijkt_op:
        kandidaten.sort(key=lambda x: -lijkt_op(x))
        kandidaten = kandidaten[:max(hoeveel * 5, 16)]
    random.shuffle(kandidaten)
    gekozen = kandidaten[:hoeveel]
    if not any(str(x)[:1] == str(goed)[:1] for x in gekozen):
        # In de hele voorraad zoeken en niet alleen in de geselecteerde kandidaten: bij
        # הַחַיִּים -> חַי was er geen ander kort woord met een ח bij de beste kandidaten,
        # en dan stond het antwoord alsnog alleen.
        gelijk = [x for x in alle
                  if x != goed and str(x)[:1] == str(goed)[:1]]
        if gelijk:
            if lijkt_op:
                gelijk.sort(key=lambda x: -lijkt_op(x))
            if gekozen:
                gekozen[-1] = gelijk[0]
            else:
                gekozen = [gelijk[0]]
    return gekozen if _eerlijk(goed, gekozen) else None


def _eerlijk(goed, afleiders):
    """Is deze reeks antwoorden niet te raden zonder de vraag te lezen?

    Twee eisen die met elkaar kunnen vechten: het antwoord mag niet de enige zijn die met
    een bepaalde letter begint, en het mag er ook niet uitspringen doordat het veel langer
    of korter is. Lukt het niet om aan beide te voldoen, dan is het eerlijker de vraag te
    laten vallen dan een scheve keuze te maken -- er zijn duizenden vormen om uit te kiezen.
    """
    if not afleiders:
        return False
    alles = [str(goed)] + [str(a) for a in afleiders]
    eersten = collections.Counter(x[:1] for x in alles)
    if eersten[str(goed)[:1]] == 1 and len(eersten) == 2:
        return False
    anderen = [len(str(a)) for a in afleiders]
    eigen = len(str(goed))
    return not (eigen > max(anderen) * 1.8 or eigen * 1.8 < min(anderen))


def verzamel():
    """Alles wat we nodig hebben, in één doorloop over de Tenach."""
    lijst = {}
    for w in H.laad_woorden():
        s = str(w.get("strong") or "")
        if s and s not in lijst:
            lijst[s] = w
    vormen = []          # (vorm, parsing, strong, ref)
    voorvoegselcombis = collections.Counter()
    for boek in H.tenach_index():
        for vers in H.laad_tenach_boek(boek["bestand"]):
            ref = f"{boek['nl']} {vers['v']}"
            for w in H.woorden_van(vers):
                codes, kern, _a = H._codes(w["parsing"])
                if codes:
                    voorvoegselcombis[nl_van_voorvoegsels(codes)] += 1
                vormen.append((H.zonder_leesteken(w["vorm"])[0], w["parsing"],
                               w["strong"], ref))
    return lijst, vormen, voorvoegselcombis


def main():
    print("de Tenach doorlopen…")
    lijst, vormen, combis = verzamel()
    print(f"  {len(vormen)} woordvormen, {len(lijst)} woorden in de cursuslijst")
    print(f"  {len(combis)} verschillende combinaties van voorvoegsels")

    alle_combis = [c for c, n in combis.most_common() if c and n >= 20]
    groepen = []

    # ------------------------------------------------ 1. welke woordjes zitten erin
    # Alleen vormen waar het lidwoord verstopt zit of waar meer dan één woordje vooraan
    # staat. Bij één los voorvoegsel is er niets te ontleden.
    vragen, gezien = [], set()
    for vorm, parsing, strong, ref in vormen:
        codes, kern, _a = H._codes(parsing)
        if len(codes) < 2 or vorm in gezien:
            continue
        verstopt = ("Art" in codes and
                    any(c in codes for c in ("Prep-b", "Prep-k", "Prep-l")))
        goed = nl_van_voorvoegsels(codes)
        if not goed or " + " not in goed:
            continue
        gezien.add(vorm)
        w = lijst.get(strong)
        # Afleiders met ongeveer even veel onderdelen. Zonder dat stond er bij het antwoord
        # 'en + in + de/het' een afleider 'in', en dan is het langste antwoord het goede.
        aantal = goed.count(" + ")
        afleiders = kies_afleiders(goed, alle_combis,
                                  lijkt_op=lambda x: -abs(x.count(" + ") - aantal))
        if not afleiders:
            continue
        vragen.append({
            "vorm": vorm, "antwoord": goed,
            "opties": sorted([goed] + afleiders, key=lambda _x: random.random()),
            "vers": ref,
            "verstopt": verstopt,
            "toelichting": (H.zonder_leesteken(vorm)[0] + " = "
                            + " + ".join(t for t, _s in H.ontleed_vorm(vorm, parsing))),
            "betekenis": (w.get("nederlands", "")[:60] if w else ""),
        })
        if len(vragen) >= PER_GROEP * 3:
            break
    # De helft met een verstopt lidwoord, de helft zonder: dan blijft die regel de kern
    # zonder dat élke vraag hetzelfde is.
    met = [v for v in vragen if v["verstopt"]][:PER_GROEP // 2]
    zonder = [v for v in vragen if not v["verstopt"]][:PER_GROEP // 2]
    groepen.append({
        "sleutel": "voorvoegsels",
        "naam": "Welke woordjes zitten erin?",
        "uitleg": "Het Hebreeuws plakt zijn kleine woordjes vast aan het volgende woord. "
                  "Let op het lidwoord: na בְּ, כְּ of לְ verdwijnt de ה ervan en blijft "
                  "alleen zijn klinker over. בַּיּוֹם is dus 'in **de** dag' en niet 'in "
                  "een dag' — het enige verschil met בְּיוֹם is die ene klinker.",
        "vraag": "Welke woordjes zitten vooraan in deze vorm?",
        "vragen": met + zonder})

    # ------------------------------------------------ 2. welk woord is dit
    vragen, gezien = [], set()
    woordvormen = [w["hebreeuws"] for w in lijst.values() if w.get("hebreeuws")]
    for vorm, parsing, strong, ref in vormen:
        w = lijst.get(strong)
        codes, kern, achter = H._codes(parsing)
        if not w or vorm in gezien or not codes:
            continue          # zonder aanhangsels valt er niets weg te denken
        goed = w["hebreeuws"]
        afleiders = kies_afleiders(goed, woordvormen, lijkt_op=_gelijkenis(goed))
        if not afleiders:
            continue
        gezien.add(vorm)
        vragen.append({
            "vorm": vorm, "antwoord": goed,
            "opties": sorted([goed] + afleiders, key=lambda _x: random.random()),
            "vers": ref,
            "toelichting": " + ".join(t for t, _s in H.ontleed_vorm(vorm, parsing)),
            "betekenis": w.get("nederlands", "")[:60]})
        if len(vragen) >= PER_GROEP:
            break
    groepen.append({
        "sleutel": "welk_woord",
        "naam": "Welk woord is dit?",
        "uitleg": "De vaardigheid waar het bij lezen om gaat: de aanhangsels wegdenken en "
                  "het woord terugvinden dat je geleerd hebt. Elk antwoord staat in je "
                  "cursuslijst.",
        "vraag": "Van welk woord uit je lijst is dit een vorm?",
        "vragen": vragen})

    # ------------------------------------------------ 3. wie doet het
    # Bij de personen kan het niet met afleiders per vraag: 'hij' is het enige antwoord dat
    # met een h begint, dus wélke drie andere je ook kiest, het antwoord is de vreemde eend.
    # Daarom altijd hetzelfde rijtje, in willekeurige volgorde. Dan zegt de vórm van de
    # antwoorden niets meer en moet je naar de letter vooraan kijken.
    ALLE_PERSONEN = ["ik", "jij (m)", "jij (v)", "hij", "zij (v)", "wij",
                     "jullie (m)", "zij (m)"]
    vragen, gezien = [], set()
    for vorm, parsing, strong, ref in vormen:
        codes, kern, _a = H._codes(parsing)
        code = H.persoon_voor_code(kern)
        if not code or vorm in gezien:
            continue
        stukken = H.ontleed_vorm(vorm, parsing)
        if not any(s == "persoon_voor" for _t, s in stukken):
            continue          # de letter staat er niet, dan is de vraag niet eerlijk
        goed = H.PERSOON_VOOR_NL[code]
        if goed not in ALLE_PERSONEN:
            continue          # anders staat het antwoord niet in het vaste rijtje
        gezien.add(vorm)
        vragen.append({
            "vorm": vorm, "antwoord": goed,
            "opties": sorted(ALLE_PERSONEN, key=lambda _x: random.random()),
            "vers": ref,
            "toelichting": " + ".join(t for t, _s in stukken),
            "betekenis": (lijst.get(strong, {}).get("nederlands", "")[:60])})
        if len(vragen) >= PER_GROEP:
            break
    groepen.append({
        "sleutel": "wie_doet_het",
        "naam": "Wie doet het?",
        "uitleg": "Bij een imperfectum staat de persoon vooráán: יִכְתֹּב is 'hij zal "
                  "schrijven', תִּכְתֹּב 'jij zult schrijven'. Dat is het omgekeerde van de "
                  "perfectum, die het achteraan zet. Die ene letter vooraan is dus het hele "
                  "verschil tussen 'hij' en 'jij'.",
        "vraag": "Wie doet het, volgens de letter vooraan?",
        "vragen": vragen})

    with open(UIT, "w", encoding="utf-8") as f:
        json.dump({"groepen": groepen}, f, ensure_ascii=False, indent=1)
    print()
    for g in groepen:
        print(f"  {g['naam']:32s} {len(g['vragen']):4d} vragen")
        for v in g["vragen"][:3]:
            print(f"      {v['vorm']:16s} -> {v['antwoord']}")
            print(f"          keuzes: {' | '.join(v['opties'])}")
    print(f"\n{UIT}: {os.path.getsize(UIT)/1024:.0f} kB")


if __name__ == "__main__":
    main()
