# -*- coding: utf-8 -*-
"""Maakt een reservekopie van alle voortgang in de Sheet, en kan die terugzetten.

Google Sheets houdt zelf een versiegeschiedenis bij, en die redt je bij een ongelukje in
de spreadsheet zelf. Wat hij niet doet is je een bestand geven dat de app kan teruglezen:
je krijgt een hele werkmap terug, niet één student. Dit script zet elke gebruiker apart
weg als JSON, precies in de vorm die de app gebruikt — en kan er dus ook uit herstellen.

De kopie wordt gemaakt met dezelfde leesregels als de app (lees_rij), dus wat hier in het
bestand staat is wat de app zou inlezen. Gaat het lezen van één tabblad mis, dan stopt het
script: een halve reservekopie die er compleet uitziet is gevaarlijker dan geen.

Draaien:

    py gereedschap/backup_sheet.py                 kopie maken
    py gereedschap/backup_sheet.py --lijst         wat er bewaard is
    py gereedschap/backup_sheet.py --herstel Bob_Timmer backups/2026-08-19_1930.json

Elke dag automatisch (Windows): Taakplanner -> Basistaak maken -> dagelijks ->
programma 'py', argumenten 'gereedschap/backup_sheet.py', beginnen in de map van de repo.
"""
import argparse
import datetime
import glob
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
# Naar de map van de repo toe. De inloggegevens worden gezocht op '.streamlit/secrets.toml'
# — een pad ten opzichte van waar je stáát, niet van waar dit script staat. Vanuit een
# andere map kwam er dus 'geen inloggegevens gevonden', en een taak in de Taakplanner
# begint standaard ergens anders. Zo werkt het script van waar je hem ook aanroept.
os.chdir(REPO)

import grieks_opslag as opslag

MAP = os.path.join(REPO, "backups")
# Hoeveel kopieën we bewaren. Dertig dagelijkse kopieën is ruim een maand terug kunnen
# kijken, en het kost een paar megabyte.
BEWAREN = 30


def tabbladen():
    """De werkbladen met voortgang: de eigen tab per gebruiker, plus het oude gedeelde."""
    sheet = opslag.verbind()
    uit = []
    for ws in sheet.worksheets():
        if ws.title == opslag.SCOREBORD:
            continue
        uit.append(ws)
    return uit


def maak_kopie():
    os.makedirs(MAP, exist_ok=True)
    alles = {}
    try:
        bladen = tabbladen()
    except Exception as e:
        # Zonder verbinding is er niets te bewaren, en een traceback zegt niet wát er
        # aan de hand is. De twee dingen die het bijna altijd zijn staan er nu bij.
        sys.exit(f"Verbinden met de Sheet lukte niet:\n  {e}\n\n"
                 f"Staat er een geldige sleutel in .streamlit/secrets.toml? Vervangen "
                 f"gaat met:\n  py gereedschap/zet_sleutel.py <sleutel.json>")
    for ws in bladen:
        rijen = ws.get_all_records()
        if not rijen:
            print(f"  {ws.title}: leeg, overgeslagen")
            continue
        # lees_rij() draait het gechunkte kolomformaat terug naar de dertien dicts. Gaat
        # dat mis, dan is er iets met dit tabblad aan de hand en willen we dat wéten.
        stats = opslag.lees_rij(rijen[0])
        alles[ws.title] = {"gebruikersnaam": rijen[0].get("gebruikersnaam", ""),
                           "stats": stats}
        v = stats.get("vocab_stats") or {}
        d = stats.get("dag_stats") or {}
        print(f"  {ws.title}: {len(v)} woorden, {len(d)} oefendagen")

    if not alles:
        sys.exit("Niets gevonden om te bewaren — is de verbinding wel goed?")

    stempel = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    pad = os.path.join(MAP, f"{stempel}.json")
    with open(pad, "w", encoding="utf-8") as f:
        json.dump(alles, f, ensure_ascii=False, indent=1)
    print(f"{len(alles)} tabbladen bewaard in backups/{stempel}.json "
          f"({os.path.getsize(pad) / 1024:.0f} kB)")
    opruimen()
    return pad


def opruimen():
    """De oudste kopieën weggooien. Op naam sorteren mag: de stempel begint met het jaar."""
    bestanden = sorted(glob.glob(os.path.join(MAP, "*.json")))
    for pad in bestanden[:-BEWAREN]:
        os.remove(pad)
        print(f"  oude kopie weg: {os.path.basename(pad)}")


def lijst():
    bestanden = sorted(glob.glob(os.path.join(MAP, "*.json")))
    if not bestanden:
        print("Nog geen reservekopieën.")
        return
    print(f"{len(bestanden)} reservekopieën in backups/:")
    for pad in bestanden:
        with open(pad, encoding="utf-8") as f:
            inhoud = json.load(f)
        delen = []
        for tab, blok in inhoud.items():
            v = (blok.get("stats") or {}).get("vocab_stats") or {}
            if len(v) > 10:                      # alleen de tabbladen die er echt toe doen
                delen.append(f"{tab}: {len(v)}")
        print(f"  {os.path.basename(pad)[:-5]}  {' · '.join(delen) or '(klein)'}")


def herstel(gebruiker, pad):
    """Eén gebruiker terugzetten uit een reservekopie.

    Bewust niet samenvoegen: als je herstelt wil je precies de oude stand terug, niet een
    mengsel met wat er nu staat. Daarom wordt er eerst een verse kopie gemaakt van hoe het
    nú is — mocht je je bedenken."""
    with open(pad, encoding="utf-8") as f:
        inhoud = json.load(f)
    tab = opslag.werkblad_naam(gebruiker)
    if tab not in inhoud:
        sys.exit(f"{tab} staat niet in {os.path.basename(pad)}. "
                 f"Wel erin: {', '.join(inhoud)}")
    stats = inhoud[tab]["stats"]
    v = stats.get("vocab_stats") or {}
    print(f"Uit {os.path.basename(pad)}: {tab} met {len(v)} woorden.")

    nu = opslag.laad(gebruiker)
    nu_v = nu.get("vocab_stats") or {}
    print(f"Nu in de Sheet: {len(nu_v)} woorden.")
    print()
    antwoord = input(f"De huidige stand van {gebruiker} vervangen door die uit de kopie? "
                     f"(typ JA) ")
    if antwoord.strip() != "JA":
        sys.exit("Niets gedaan.")

    print("Eerst een verse kopie van de huidige stand…")
    maak_kopie()
    # samenvoegen=False: herstellen betekent terugzetten, niet mengen.
    opslag.bewaar(gebruiker, stats, samenvoegen=False)
    print(f"{gebruiker} teruggezet naar de stand uit {os.path.basename(pad)}.")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--lijst", action="store_true", help="laat zien wat er bewaard is")
    p.add_argument("--herstel", nargs=2, metavar=("GEBRUIKER", "BESTAND"),
                   help="zet één gebruiker terug uit een reservekopie")
    args = p.parse_args()
    if args.lijst:
        lijst()
    elif args.herstel:
        herstel(args.herstel[0], args.herstel[1])
    else:
        maak_kopie()


if __name__ == "__main__":
    main()
