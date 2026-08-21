# -*- coding: utf-8 -*-
"""Welke veelvoorkomende Hebreeuwse woorden staan nog niet in de app?

De cursuslijst heeft 410 woorden en dekt daarmee 70% van de Tenach. Dit script zoekt uit
wat er daarbuiten nog voor het oprapen ligt: per Strong-nummer hoe vaak het voorkomt, in
welke vorm, hoe het klinkt, en hoe de Berean Standard Bible het vertaalt — die staat in de
spreadsheet woord voor woord uitgelijnd, dus dat is geen gok maar wat er in de praktijk
staat.

Het schrijft niets weg. Wat je hiermee doet is een keuze: woorden buiten je cursuslijst
horen in een eigen lijst, niet tussen Hebreeuws 1 en 2.

Draaien:  py gereedschap/peil_ontbrekend.py [aantal]
"""
import collections
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

import uitvoer

uitvoer.zet_utf8()

SHEET = os.path.join(REPO, "hebreeuws app", "Hele bijbel.xlsx")
WOORDEN = os.path.join(REPO, "hebreeuws_woorden.json")

# Woordsoorten die je niet als losse woordenschat leert: eigennamen, en de cijfers.
NIET_LEREN = re.compile(r"\b(N-proper|Number)\b", re.IGNORECASE)
WEG = re.compile("[֑-ֽ֯־ֿ׀׃-׆]")


def schoon(vorm):
    return WEG.sub("", str(vorm or "").strip())


def main():
    hoeveel = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    if not os.path.exists(SHEET):
        sys.exit(f"{SHEET} niet gevonden — die staat niet in git (42 MB).")

    hebben = {str(w.get("strong") or "") for w in json.load(open(WOORDEN, encoding="utf-8"))}
    hebben.discard("")
    print(f"De app kent {len(hebben)} Strong-nummers. Bijbeltekst inlezen…")

    import openpyxl
    wb = openpyxl.load_workbook(SHEET, read_only=True, data_only=True)
    ws = wb["Hebreeuws"]
    telling = collections.Counter()
    vormen = collections.defaultdict(collections.Counter)
    translits = collections.defaultdict(collections.Counter)
    engels = collections.defaultdict(collections.Counter)
    soorten = collections.defaultdict(collections.Counter)
    eerste = {}
    vers = ""
    totaal = 0
    for rij in ws.iter_rows(min_row=2, values_only=True):
        vorm, translit, parsing, strong = rij[6], rij[8], rij[9], rij[11]
        verwijzing, bsb = rij[13], rij[19]
        if verwijzing and str(verwijzing).strip():
            vers = str(verwijzing).strip()
        # Alleen Hebreeuws. Ezra en Daniël bevatten Aramese stukken, en die staan in
        # hetzelfde werkblad; zonder deze regel kwamen מלכא en מן bovenaan de lijst met
        # ontbrekende woorden te staan — terecht ontbrekend, want het is een andere taal.
        if str(rij[5] or '').strip().lower() != 'hebrew':
            continue
        if not (vorm and strong):
            continue
        s = str(strong).strip()
        totaal += 1
        telling[s] += 1
        vormen[s][schoon(vorm)] += 1
        if translit:
            translits[s][schoon(translit)] += 1
        if parsing:
            soorten[s][str(parsing).split("|")[-1].strip()] += 1
        # De Engelse vertaling van dit woord: alleen als er één woord staat, anders is het
        # de vertaling van een hele woordgroep en zegt hij niets over dít woord.
        if bsb:
            woord = str(bsb).strip().strip(",.;:!?\"'()[]").lower()
            if woord and " " not in woord:
                engels[s][woord] += 1
        eerste.setdefault(s, vers)

    ontbreekt = [(n, s) for s, n in telling.items() if s not in hebben]
    ontbreekt.sort(reverse=True)
    eigennaam = [(n, s) for n, s in ontbreekt
                 if NIET_LEREN.search(" ".join(soorten[s]))]
    gewoon = [(n, s) for n, s in ontbreekt
              if not NIET_LEREN.search(" ".join(soorten[s]))]

    dek = sum(telling[s] for s in hebben if s in telling)
    print(f"{totaal} woordvormen, {len(telling)} Strong-nummers.")
    print(f"De app dekt er {dek} van ({100*dek/totaal:.1f}%).")
    print(f"{len(gewoon)} nummers ontbreken nog (plus {len(eigennaam)} eigennamen en "
          f"getallen, die je niet als woordenschat leert).")
    erbij = sum(n for n, _s in gewoon[:hoeveel])
    print(f"De eerste {hoeveel} daarvan zijn samen {erbij} vindplaatsen: "
          f"+{100*erbij/totaal:.1f}% dekking.")
    print()
    print(f"{'Strong':>7s}  {'aantal':>6s}  {'vorm':14s} {'klinkt als':16s} "
          f"{'Engels (BSB)':22s} eerst in")
    for n, s in gewoon[:hoeveel]:
        vorm = vormen[s].most_common(1)[0][0]
        tl = translits[s].most_common(1)[0][0] if translits[s] else ""
        en = ", ".join(w for w, _k in engels[s].most_common(3))
        print(f"{s:>7s}  {n:6d}  {vorm:14s} {tl:16s} {en[:22]:22s} {eerste[s]}")


if __name__ == "__main__":
    main()
