# -*- coding: utf-8 -*-
"""Bouwt hebreeuws_klanken.json: oefenstof voor de Hebreeuwse klankregels.

De Griekse contractietrainer werkt met een regeltabel en een handvol voorbeelden uit het
boek. Voor het Hebreeuws kan het beter, want de hele Tenach staat in de repo: elke opgave
hier is een páár échte vormen van hetzelfde woord, één zonder het voorvoegsel en één met.
Dus wat je hier vormt staat ook ergens, en de vindplaats staat erbij.

Drie regels, alle drie gemeten over de hele Tenach:

  1. Lidwoord na een voorzetsel (6543 vindplaatsen)
     Na בְּ, כְּ of לְ verdwijnt de ה van het lidwoord; zijn klinker blijft.
     בְּ + הַ + יוֹם  ->  בַּיּוֹם

  2. De klinker van het lidwoord (23.000+ vindplaatsen)
     Vóór een gewone letter הַ met verdubbeling. Vóór א, ע of ר kan die verdubbeling niet
     en wordt het הָ: 99% van de 3348 gevallen bij א, 92% van 2158 bij ע, 99% van 761 bij
     ר. Vóór ה en ח blijft het הַ zonder verdubbeling (83% van 872 bij ח).

  3. Wajjiqtol (12.568 vindplaatsen)
     וְ wordt וַ en de volgende letter verdubbelt: יִקְרָא -> וַיִּקְרָא. Van alle 12.568
     wajjiqtol-vormen heeft er niet één géén dagesj.

Draaien:  py gereedschap/bouw_hebreeuws_klanken.py
"""
import collections
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

import uitvoer

uitvoer.zet_utf8()

import hebreeuws as H

UIT = os.path.join(REPO, "hebreeuws_klanken.json")
PER_GROEP = 120          # meer dan genoeg voor een ronde, en het bestand blijft klein
KEEL_LANG = "אער"        # hier kan geen dagesj op, dus het lidwoord wordt הָ
KEEL_KORT = "הח"         # hier ook niet, maar zonder verlenging: הַ blijft


def eerste_letter(tekst):
    return next((t for t in tekst if "א" <= t <= "ת"), "")


def zelfde_stam(basis, vorm, voorvoegsel_letters=1):
    """Zijn dit dezelfde medeklinkers, op het voorvoegsel na?

    Zonder deze controle komen er opgaven in die niet met de regel te maken zijn. וַיְהִי
    is de wajjiqtol van יִהְיֶה, maar hij is verkort: de laatste ה valt weg. Wie de regel
    netjes toepast maakt וַיִּהְיֶה en wordt dan fout gerekend, en dat is onredelijk. Zulke
    paren horen in een les over verkorte vormen, niet in een oefening over verdubbeling.

    Vergelijken op medeklinkers en niet op klinkers, want juist die klinkers veranderen wél
    — dat is de regel."""
    m_basis = H.medeklinkers(basis)
    m_vorm = H.medeklinkers(vorm)
    return m_vorm[voorvoegsel_letters:] == m_basis if voorvoegsel_letters \
        else m_vorm == m_basis


def klinker_van_lidwoord(vorm):
    """De klinker op de ה van het lidwoord, en de letter die erna komt."""
    rest = vorm[1:]
    klinker = ""
    for t in rest:
        if "א" <= t <= "ת":
            break
        klinker += t
    return klinker, eerste_letter(rest)


def verzamel():
    """Alle vormen langs, gesorteerd op wat we ermee kunnen.

    kaal[strong][kern_code] = een vorm zonder voorvoegsels
    met_prep_art, met_art, wajji = de vormen mét, met hun ontleding erbij
    """
    kaal = collections.defaultdict(dict)
    met_prep_art, met_art, wajji, kaal_imperf = [], [], [], {}
    for boek in H.tenach_index():
        for vers in H.laad_tenach_boek(boek["bestand"]):
            ref = f"{boek['nl']} {vers['v']}"
            for w in H.woorden_van(vers):
                vorm, parsing, strong = w["vorm"], w["parsing"], w["strong"]
                codes, kern, achter = H._codes(parsing)
                if achter or not strong:
                    continue          # met een bezittelijk achtervoegsel wordt het rommelig
                schoon = H.zonder_leesteken(vorm)[0]
                if not codes:
                    kaal[strong].setdefault(kern, schoon)
                    if "Imperf" in kern and "Consec" not in kern:
                        kaal_imperf.setdefault((strong, kern), schoon)
                    continue
                if "Art" in codes and any(c in codes for c in
                                          ("Prep-b", "Prep-k", "Prep-l")):
                    prep = next(c for c in codes if c.startswith("Prep-"))
                    if len(codes) == 2:      # alleen dit voorzetsel plus het lidwoord
                        met_prep_art.append((schoon, parsing, strong, kern, prep, ref))
                elif codes == ["Art"] and schoon.startswith("ה"):
                    met_art.append((schoon, parsing, strong, kern, ref))
                elif codes == ["Conj-w"] and "ConsecImperf" in kern:
                    wajji.append((schoon, parsing, strong, kern, ref))
    return kaal, kaal_imperf, met_prep_art, met_art, wajji


def main():
    print("de Tenach doorlopen…")
    kaal, kaal_imperf, met_prep_art, met_art, wajji = verzamel()
    print(f"  {len(kaal)} woorden met een kale vorm")
    print(f"  {len(met_prep_art)} met voorzetsel plus lidwoord")
    print(f"  {len(met_art)} met alleen het lidwoord")
    print(f"  {len(wajji)} wajjiqtol-vormen")

    groepen = []

    # ---------------------------------------------------------------- 1. prep + lidwoord
    vragen, gezien = [], set()
    for vorm, parsing, strong, kern, prep, ref in met_prep_art:
        basis = kaal.get(strong, {}).get(kern)
        if not basis or vorm in gezien or not zelfde_stam(basis, vorm, 1):
            continue
        gezien.add(vorm)
        vragen.append({"delen": [H.VOORVOEGSEL_LETTER[prep] + "ְ", "הַ",
                                 basis],
                       "woorden": [H.VOORVOEGSEL_NL[prep], "de/het"],
                       "uitkomst": vorm, "vers": ref})
        if len(vragen) >= PER_GROEP:
            break
    groepen.append({
        "sleutel": "prep_art",
        "naam": "Lidwoord na een voorzetsel",
        "uitleg": "Na בְּ, כְּ of לְ verdwijnt de ה van het lidwoord. Zijn klinker blijft "
                  "wel staan, en dat is het enige waaraan je nog ziet dat het lidwoord er "
                  "is: בְּ + הַ + יוֹם wordt בַּיּוֹם, niet בְּהַיּוֹם.",
        "vraag": "Welke vorm krijg je als je deze drie samenvoegt?",
        "vragen": vragen})

    # ---------------------------------------------------------------- 2. klinker lidwoord
    vragen, gezien = [], set()
    for vorm, parsing, strong, kern, ref in met_art:
        basis = kaal.get(strong, {}).get(kern)
        if not basis or vorm in gezien:
            continue
        klinker, letter = klinker_van_lidwoord(vorm)
        if not letter or len(klinker) != 1:
            continue
        if not zelfde_stam(basis, vorm, 1):
            continue
        gezien.add(vorm)
        # Het antwoord is hier het lidwoord en niet de hele vorm. De klinkers ín het woord
        # veranderen ook mee, en daar gaat deze regel niet over -- dan zou je iets fout
        # rekenen wat je niet gevraagd hebt.
        vragen.append({"delen": [basis], "antwoord": "ה" + klinker,
                       "woorden": ["de/het"],
                       "uitkomst": vorm, "vers": ref,
                       "letter": letter,
                       "soort": ("keelletter zonder verlenging" if letter in KEEL_KORT
                                 else "keelletter" if letter in KEEL_LANG
                                 else "gewone letter")})
        if len(vragen) >= PER_GROEP * 2:
            break
    # Zorgen dat alle drie de soorten erin zitten, en niet alleen de meest voorkomende.
    per_soort = collections.defaultdict(list)
    for v in vragen:
        per_soort[v["soort"]].append(v)
    evenwichtig = []
    for soort, rijen in per_soort.items():
        evenwichtig.extend(rijen[:PER_GROEP // max(1, len(per_soort))])
    groepen.append({
        "sleutel": "art_klinker",
        "naam": "De klinker van het lidwoord",
        "uitleg": "Het lidwoord is הַ, en de letter erna verdubbelt: הַשָּׁמַיִם. Op א, ע "
                  "en ר kan geen dagesj staan, en dan wordt de klinker lang: הָאָרֶץ, "
                  "הָעֵץ, הָרָקִיעַ. Op ה en ח kan ook geen dagesj, maar daar verlengt de "
                  "klinker niet: הַחֹשֶׁךְ blijft הַ.",
        "vraag": "Welk lidwoord krijgt dit woord?",
        "antwoordopties": ["הַ", "הָ", "הֶ"],
        "vragen": evenwichtig})

    # ---------------------------------------------------------------- 3. wajjiqtol
    vragen, gezien = [], set()
    for vorm, parsing, strong, kern, ref in wajji:
        imperf = kern.replace("ConsecImperf", "Imperf")
        basis = kaal_imperf.get((strong, imperf))
        if not basis or vorm in gezien or not zelfde_stam(basis, vorm, 1):
            continue
        # De kale vorm mag de verdubbeling niet al hebben: die is juist wat er te leren is.
        # Er staat in de tekst een enkele יִּקְרָא met dagesj zonder waw ervoor, en met die
        # als opgave is de vraag al beantwoord.
        if "ּ" in basis[:3]:
            continue
        gezien.add(vorm)
        vragen.append({"delen": ["וַ", basis],
                       "woorden": ["en toen"],
                       "uitkomst": vorm, "vers": ref})
        if len(vragen) >= PER_GROEP:
            break
    groepen.append({
        "sleutel": "wajjiqtol",
        "naam": "Wajjiqtol: en toen…",
        "uitleg": "De verhalende vorm van het Hebreeuws. Het voegwoord wordt וַ in plaats "
                  "van וְ, en de letter erna verdubbelt: יִקְרָא wordt וַיִּקְרָא. Van alle "
                  "12.568 wajjiqtol-vormen in de Tenach heeft er niet één géén dagesj.",
        "vraag": "Welke wajjiqtol-vorm hoort hierbij?",
        "vragen": vragen})

    with open(UIT, "w", encoding="utf-8") as f:
        json.dump({"groepen": groepen}, f, ensure_ascii=False, indent=1)
    print()
    for g in groepen:
        print(f"  {g['naam']:34s} {len(g['vragen']):4d} opgaven")
        for v in g["vragen"][:3]:
            print(f"      {' + '.join(v['delen'])}  ->  {v['uitkomst']}   ({v['vers']})")
    print(f"\n{UIT}: {os.path.getsize(UIT)/1024:.0f} kB")


if __name__ == "__main__":
    main()
