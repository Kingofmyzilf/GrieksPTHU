# -*- coding: utf-8 -*-
"""Controleert dat het omzetten van de NT-tekst niets veranderd heeft behalve de omvang.

De tekst stond in twee bestanden van samen 31,5 MB en staat nu per boek ingepakt in nt/.
Bij zo'n omzetting is de enige vraag die telt of er iets verdwenen is. Deze proef legt de
oude en de nieuwe naast elkaar, vers voor vers en woord voor woord.

Draaien:  py gereedschap/test_nt.py

Zijn de oude bestanden er niet meer, dan slaat de proef zichzelf over — er is dan niets om
tegen te vergelijken, en dat is geen fout.
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

import uitvoer

uitvoer.zet_utf8()

import grieks_motor as motor

# Dit veld is bij het omzetten weggelaten omdat het nergens gelezen wordt.
WEGGELATEN = {"parsing_code"}


def main():
    oud = {}
    for naam in ("bijbel_nt.json", "bijbel_nt_deel1.json", "bijbel_nt_deel2.json"):
        if os.path.exists(naam):
            with open(naam, encoding="utf-8") as f:
                oud.update(json.load(f))
    if not oud:
        print("De oude bestanden staan er niet meer; niets om tegen te vergelijken.")
        return

    nieuw = motor.laad_bijbel_db()
    print(f"oud {len(oud)} verzen, nieuw {len(nieuw)} verzen")

    fouten = []
    if set(oud) != set(nieuw):
        alleen_oud = sorted(set(oud) - set(nieuw))[:5]
        alleen_nieuw = sorted(set(nieuw) - set(oud))[:5]
        fouten.append(f"andere verzen: alleen oud {alleen_oud}, alleen nieuw {alleen_nieuw}")

    woorden = velden_weg = 0
    for ref in oud:
        if ref not in nieuw:
            continue
        a, b = oud[ref], nieuw[ref]
        if len(a) != len(b):
            fouten.append(f"{ref}: {len(a)} woorden werd {len(b)}")
            continue
        for wa, wb in zip(a, b):
            woorden += 1
            verwacht = {k: v for k, v in wa.items() if k not in WEGGELATEN}
            velden_weg += len(wa) - len(verwacht)
            if verwacht != wb:
                anders = {k for k in set(verwacht) | set(wb)
                          if verwacht.get(k) != wb.get(k)}
                fouten.append(f"{ref} '{wa.get('grieks','')}': velden {sorted(anders)}")
                if len(fouten) > 8:
                    break
        if len(fouten) > 8:
            break

    print(f"{woorden} woorden vergeleken, {velden_weg} keer parsing_code weggelaten")
    oud_groot = sum(os.path.getsize(n) for n in
                    ("bijbel_nt.json", "bijbel_nt_deel1.json", "bijbel_nt_deel2.json")
                    if os.path.exists(n))
    nieuw_groot = sum(os.path.getsize(os.path.join("nt", f))
                      for f in os.listdir("nt")) if os.path.isdir("nt") else 0
    print(f"op schijf: {oud_groot/1048576:.1f} MB werd {nieuw_groot/1048576:.2f} MB "
          f"({oud_groot/max(1, nieuw_groot):.0f}x kleiner)")

    for f in fouten[:8]:
        print("  MIS:", f)
    if fouten:
        sys.exit(f"{len(fouten)} verschillen")
    print("GESLAAGD: dezelfde verzen, dezelfde woorden, dezelfde velden")


if __name__ == "__main__":
    main()
