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
    if "--alles" in sys.argv:
        heel_de_tenach()
    print("\nGESLAAGD")


def heel_de_tenach():
    """Dezelfde controle over alle 300.670 woordvormen, plus de andere kant op.

    Duurt een paar minuten en staat daarom achter --alles. Meer dekking is makkelijk als je
    te gretig knipt, dus hier wordt ook gekeken of er niets wordt afgesplitst waar de
    ontleding géén achtervoegsel noemt, en of er een woord overblijft."""
    print("\n=== alle woordvormen van de Tenach ===")
    n = kapot = zonder_code = korte_stam = met_code = gesplitst = 0
    u_met_code = u_gesplitst = u_kort = 0
    per_code = collections.Counter()
    u_per_code = collections.Counter()
    voorbeelden = []
    for boek in H.tenach_index():
        for vers in H.laad_tenach_boek(boek["bestand"]):
            for w in H.woorden_van(vers):
                vorm, parsing = w["vorm"], w["parsing"]
                voor, kern, achter = H.splits_affixen(vorm, parsing)
                n += 1
                if voor + kern + achter != vorm:
                    kapot += 1
                    if len(voorbeelden) < 5:
                        voorbeelden.append(f"telt niet op: {vorm!r} -> "
                                           f"{voor!r}+{kern!r}+{achter!r}")
                # --- alle stukken samen: voorvoegsel, persoonsvoorvoegsel, stam, uitgang,
                #     bezittelijk achtervoegsel. Die moeten samen het woord vormen.
                _v, kern_code, _a = H._codes(parsing)
                stukken = H.ontleed_vorm(vorm, parsing)
                if "".join(t for t, _s in stukken) != vorm:
                    kapot += 1
                    if len(voorbeelden) < 8:
                        voorbeelden.append(f"stukken vormen niet het woord: {vorm!r} -> "
                                           f"{stukken}")
                stam = "".join(t for t, s in stukken if s == "stam")
                uitgang = "".join(t for t, s in stukken if s.startswith("uitgang"))
                if H.uitgang_code(kern_code) and not achter:
                    u_met_code += 1
                    if uitgang:
                        u_gesplitst += 1
                        u_per_code[H.uitgang_code(kern_code)] += 1
                # Er moet altijd een medeklinker als stam overblijven. Twee was veiliger,
                # maar dan bleef מַיִם ('water', altijd meervoud) ongekleurd en juist daar
                # wil je die יִם zien.
                if uitgang and not any("א" <= t <= "ת" for t in stam):
                    u_kort += 1
                    if len(voorbeelden) < 12:
                        voorbeelden.append(f"stam zonder medeklinker na de uitgang: "
                                           f"{vorm!r} -> {stam!r} + {uitgang!r}")
                _v, _k, code = H._codes(parsing)
                if code:
                    met_code += 1
                    if achter:
                        gesplitst += 1
                        per_code[code] += 1
                elif achter:
                    zonder_code += 1
                    if len(voorbeelden) < 10:
                        voorbeelden.append(f"achtervoegsel zonder code: {vorm!r} -> "
                                           f"{achter!r} ({parsing})")
                if achter and not any("א" <= t <= "ת" for t in kern):
                    korte_stam += 1
                    if len(voorbeelden) < 15:
                        voorbeelden.append(f"stam zonder medeklinker: {vorm!r} -> {kern!r}")

    print(f"  {n} woordvormen")
    print(f"  stukken tellen niet op tot de vorm      {kapot:6d}")
    print(f"  achtervoegsel zonder code in de ontleding {zonder_code:6d}")
    print(f"  stam zonder medeklinker                 {korte_stam:6d}")
    print(f"  {gesplitst} van de {met_code} achtervoegsels afgesplitst "
          f"({100 * gesplitst / max(1, met_code):.1f}%)")
    print("  per persoon:")
    for code, aantal in sorted(per_code.items()):
        print(f"    {code:5s} {aantal:7d}  {H.ACHTERVOEGSEL_NL[code]}")
    print()
    print(f"  uitgangen: {u_gesplitst} van de {u_met_code} met een uitgangscode gekleurd "
          f"({100 * u_gesplitst / max(1, u_met_code):.1f}%)")
    print(f"  stam te kort na de uitgang               {u_kort:6d}")
    for code, aantal in sorted(u_per_code.items(), key=lambda k: -k[1])[:8]:
        print(f"    {code:5s} {aantal:7d}  {H.UITGANG_NL.get(code, '')}")
    for regel in voorbeelden:
        print(f"    MIS {regel}")
    if kapot or zonder_code or korte_stam or u_kort:
        sys.exit(f"{kapot + zonder_code + korte_stam + u_kort} echte fouten "
                 f"over de hele Tenach")
    # Niet alles heeft een uitgang die te zien is: veel naamwoorden zijn mannelijk
    # enkelvoud en dan is er niets, en een imperfectum draagt zijn persoon vooraan. Onder
    # de helft is er echter iets stuk.
    if u_met_code and u_gesplitst < u_met_code * 0.5:
        sys.exit(f"maar {100 * u_gesplitst / u_met_code:.1f}% van de uitgangen gekleurd")
    # Onder deze grens is er iets stuk. De rest die niet lukt is vrijwel alleen de
    # richtings-he, die dit bestand dezelfde code 3fs geeft als het echte achtervoegsel.
    if met_code and gesplitst < met_code * 0.9:
        sys.exit(f"maar {100 * gesplitst / met_code:.1f}% afgesplitst — te weinig")


if __name__ == "__main__":
    main()
