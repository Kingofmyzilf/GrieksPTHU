# -*- coding: utf-8 -*-
"""Controleert het afsplitsen van voor- en achtervoegsels op echte woordvormen.

Kleuren mag alleen als het splitsen klopt: een verkeerd gekleurd voorvoegsel leert je iets
verkeerds, en dat is erger dan geen kleur. Deze proef draait over alle vormen uit
hebreeuws_lezen.json en kijkt drie dingen na:

  * De drie stukken samen moeten weer precies de oorspronkelijke vorm zijn. Er mag geen
    letter verdwijnen of bijkomen.
  * Een afgesplitst voorvoegsel moet beginnen met de letter die de ontleedcode noemt.
  * Zegt de code dat er een voorvoegsel is, dan hoort er ook een gevonden te worden — op
    de assimilerende he na, want die is er als klinker maar niet als letter.

Draaien:  py gereedschap/test_affixen.py
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uitvoer

uitvoer.zet_utf8()

import hebreeuws as H

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    pad = os.path.join(REPO, "hebreeuws_lezen.json")
    if not os.path.exists(pad):
        sys.exit("hebreeuws_lezen.json niet gevonden — draai bouw_hebreeuws_lezen.py")
    verzen = json.load(open(pad, encoding="utf-8"))

    totaal = met_voor = met_achter = gesplitst_voor = gesplitst_achter = 0
    kapot, gemist, verkeerd = [], [], []
    per_code = collections.Counter()
    for vers in verzen:
        for w in H.woorden_van(vers):
            vorm, parsing = w["vorm"], w["parsing"]
            totaal += 1
            voor_codes, _kern, achter_code = H._codes(parsing)
            voorvoegsel, kern, achtervoegsel = H.splits_affixen(vorm, parsing)

            if voorvoegsel + kern + achtervoegsel != vorm:
                kapot.append((vorm, parsing, voorvoegsel, kern, achtervoegsel))
            if voor_codes:
                met_voor += 1
                if voorvoegsel:
                    gesplitst_voor += 1
                    eerste = next((t for t in voorvoegsel if "א" <= t <= "ת"), "")
                    if eerste != H.VOORVOEGSEL_LETTER[voor_codes[0]]:
                        verkeerd.append((vorm, parsing, voorvoegsel))
                    for c in voor_codes:
                        per_code[c] += 1
                elif not all(c in ("Art", "Interrog") for c in voor_codes):
                    gemist.append((vorm, parsing))
            if achter_code:
                met_achter += 1
                if achtervoegsel:
                    gesplitst_achter += 1

    print(f"{totaal} woordvormen uit {len(verzen)} verzen\n")
    print(f"  met een voorvoegsel volgens de code   {met_voor:6d}")
    print(f"  daarvan afgesplitst                   {gesplitst_voor:6d} "
          f"({100*gesplitst_voor/max(1, met_voor):.0f}%)")
    print(f"  met een achtervoegsel volgens de code {met_achter:6d}")
    print(f"  daarvan afgesplitst                   {gesplitst_achter:6d} "
          f"({100*gesplitst_achter/max(1, met_achter):.0f}%)")
    print()
    print(f"  stukken tellen niet op tot de vorm    {len(kapot):6d}")
    print(f"  voorvoegsel begint met de verkeerde letter {len(verkeerd):6d}")
    print(f"  voorvoegsel niet gevonden terwijl het er hoort {len(gemist):6d}")

    for wat, lijst in (("TELT NIET OP", kapot), ("VERKEERDE LETTER", verkeerd)):
        for regel in lijst[:6]:
            print(f"    {wat}: {regel}")

    if gemist:
        print("\n  niet gevonden, de eerste acht:")
        for vorm, parsing in gemist[:8]:
            print(f"    {vorm:16s} {parsing}")

    print("\n  afgesplitst per soort voorvoegsel:")
    for code, n in per_code.most_common():
        print(f"    {code:10s} {n:6d}  = {H.VOORVOEGSEL_NL.get(code, '')}")

    # Kapotte splitsingen en verkeerde letters zijn echte fouten. Een gemist voorvoegsel is
    # een gemiste kans en geen fout — er wordt dan gewoon niets gekleurd — maar boven de
    # tien procent is er iets structureels aan de hand.
    if kapot or verkeerd:
        sys.exit(f"{len(kapot) + len(verkeerd)} echte fouten")
    if met_voor and len(gemist) > met_voor * 0.1:
        sys.exit(f"{len(gemist)} van de {met_voor} voorvoegsels niet gevonden — te veel")
    print("\nGESLAAGD")


if __name__ == "__main__":
    main()
