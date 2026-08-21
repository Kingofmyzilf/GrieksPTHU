# -*- coding: utf-8 -*-
"""Zet het Engels en de uitspraak ook in hebreeuws_lezen.json.

Dat bestand heeft de duizend uitgezochte verzen voor de Lezen-pagina van de snelle app, en
had per woord alleen de vorm, het Strong-nummer en de ontleedcode. Sinds bouw_tenach.py de
hele Tenach met vijf velden wegschrijft is de aanvulling er al: dit script zoekt elk vers
op in tenach/ en neemt de twee ontbrekende velden over.

Waarom niet opnieuw uit de spreadsheet: de keuze van welke duizend verzen het zijn zit in
bouw_hebreeuws_lezen.py en hangt af van de woordenlijst zoals die toen was. Opnieuw bouwen
zou dus een andere selectie geven. Overnemen uit tenach/ verandert alleen wat er per woord
bij staat, en laat de verzen zelf ongemoeid.

Draaien:  py gereedschap/vul_lezen_aan.py
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

import uitvoer

uitvoer.zet_utf8()

import hebreeuws

LEZEN = os.path.join(REPO, "hebreeuws_lezen.json")


def main():
    with open(LEZEN, encoding="utf-8") as f:
        verzen = json.load(f)
    print(f"{len(verzen)} verzen in hebreeuws_lezen.json")

    # Per boeknaam het bestand uit tenach/, en per boek de verzen op 'hoofdstuk:vers'.
    bestand_van = {b["boek"]: b["bestand"] for b in hebreeuws.tenach_index()}
    if not bestand_van:
        sys.exit("tenach/ is niet gevonden — draai eerst bouw_tenach.py.")

    kaart = {}

    def zoek(boek, ref):
        """Het vers uit tenach/, of None. Onthoudt het boek, want uitpakken kost tijd."""
        if boek not in kaart:
            bestand = bestand_van.get(boek)
            kaart[boek] = ({v["v"]: v for v in hebreeuws.laad_tenach_boek(bestand)}
                           if bestand else {})
        return kaart[boek].get(ref)

    aangevuld = geen_boek = geen_vers = anders = 0
    n_engels = n_translit = n_woorden = 0
    for vers in verzen:
        boek = re.sub(r"\s+\d+:\d+$", "", str(vers.get("vers", "")))
        ref = str(vers.get("vers", "")).rsplit(" ", 1)[-1]
        if boek not in bestand_van:
            geen_boek += 1
            continue
        bron = zoek(boek, ref)
        if bron is None:
            geen_vers += 1
            continue
        uit_tenach = hebreeuws.woorden_van(bron)
        eigen = vers.get("woorden") or []
        # Alleen overnemen als het écht hetzelfde vers is: even veel woorden, en dezelfde
        # vormen. Anders zou het Engels bij het verkeerde woord komen te staan, en dat is
        # erger dan geen Engels.
        if len(uit_tenach) != len(eigen) or any(
                a[0] != b["vorm"] for a, b in zip(eigen, uit_tenach)):
            anders += 1
            continue
        vers["woorden"] = [[b["vorm"], b["strong"], b["parsing"], b["translit"],
                            b["engels"]] for b in uit_tenach]
        aangevuld += 1
        for b in uit_tenach:
            n_woorden += 1
            n_engels += bool(b["engels"])
            n_translit += bool(b["translit"])

    print(f"{aangevuld} verzen aangevuld")
    if geen_boek:
        print(f"  {geen_boek} verzen met een boek dat niet in tenach/ staat")
    if geen_vers:
        print(f"  {geen_vers} verzen niet gevonden in hun boek")
    if anders:
        print(f"  {anders} verzen met andere woorden — met opzet overgeslagen")
    print(f"{n_woorden} woorden: {n_engels} met Engels ({100*n_engels/max(1,n_woorden):.1f}%), "
          f"{n_translit} met uitspraak ({100*n_translit/max(1,n_woorden):.1f}%)")

    voor = os.path.getsize(LEZEN)
    with open(LEZEN, "w", encoding="utf-8") as f:
        json.dump(verzen, f, ensure_ascii=False, separators=(",", ":"))
    na = os.path.getsize(LEZEN)
    print(f"{voor/1024:.0f} kB werd {na/1024:.0f} kB")


if __name__ == "__main__":
    main()
