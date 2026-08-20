# -*- coding: utf-8 -*-
"""Maakt een reservekopie van alle voortgang in de Sheet, en kan die terugzetten.

Er zijn twee lagen, en die vullen elkaar aan:

  * De app maakt zelf elke dag een kopie, in het tabblad Backups van de Sheet. Dat gebeurt
    bij de eerste opslag na middernacht, door wie dan ook oefent — dus ook als jouw
    computer uit staat. Zie dagkopie() in grieks_opslag.py; veertien dagen blijven staan.
  * Dit script zet alles op je eigen schijf. Dat overleeft het ook als de spreadsheet zelf
    iets overkomt, en dat is precies wat de laag hierboven niet kan.

Google Sheets houdt zelf óók een versiegeschiedenis bij, maar die geeft je een hele werkmap
terug en geen bestand dat de app kan teruglezen. Hier staat elke gebruiker apart, in de
vorm die de app gebruikt — dus je kunt er ook uit herstellen.

De kopie wordt gemaakt met dezelfde leesregels als de app (lees_rij), dus wat hier in het
bestand staat is wat de app zou inlezen. Gaat het lezen van één tabblad mis, dan stopt het
script: een halve reservekopie die er compleet uitziet is gevaarlijker dan geen.

Draaien:

    py gereedschap/backup_sheet.py              kopie maken op deze computer
    py gereedschap/backup_sheet.py --lijst      wat er te herstellen valt, uit beide lagen
    py gereedschap/backup_sheet.py --herstel Bob_Timmer 2026-08-20
    py gereedschap/backup_sheet.py --herstel Bob_Timmer backups/2026-08-19_2007.json

Elke dag ook op deze computer, als extra bovenop wat de app al doet: Taakplanner ->
Basistaak maken -> dagelijks -> programma 'py', argument het volledige pad naar dit
bestand. Beginnen-in hoeft niet ingevuld: het script gaat zelf naar de goede map.
"""
import argparse
import datetime
import glob
import json
import os
import re
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
    """Wat er te herstellen valt, uit twee bronnen.

    De app maakt zelf elke dag een kopie in het tabblad Backups van de Sheet — die is er
    ook als je pc uit staat. Dit script maakt kopieën op je eigen schijf, en die overleven
    het ook als de spreadsheet zelf iets overkomt. Beide staan hier onder elkaar."""
    try:
        in_sheet = opslag.lees_kopieen()
    except Exception as e:
        in_sheet = []
        print(f"(de kopieën in de Sheet konden niet gelezen worden: {e})")
    if in_sheet:
        per_dag = {}
        for dag, naam, stats in in_sheet:
            v = (stats.get("vocab_stats") or {})
            per_dag.setdefault(dag, []).append(f"{naam}: {len(v)}")
        print(f"{len(per_dag)} dagen in het tabblad Backups van de Sheet "
              f"(door de app zelf gemaakt):")
        for dag in sorted(per_dag):
            print(f"  {dag}  {' · '.join(per_dag[dag])}")
        print()

    bestanden = sorted(glob.glob(os.path.join(MAP, "*.json")))
    if not bestanden:
        print("Nog geen reservekopieën op deze computer.")
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


def _uit_kopie(gebruiker, bron):
    """De stand ophalen uit een kopie. 'bron' is een datum (dan uit het tabblad Backups
    in de Sheet) of een bestandsnaam (dan van deze computer)."""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(bron).strip()):
        dag = str(bron).strip()
        treffers = [s for d, naam, s in opslag.lees_kopieen(gebruiker) if d == dag]
        if not treffers:
            dagen = sorted({d for d, _n, _s in opslag.lees_kopieen(gebruiker)})
            sys.exit(f"Geen kopie van {gebruiker} op {dag}. "
                     f"Wel: {', '.join(dagen) or '(geen)'}")
        return treffers[-1], f"de kopie van {dag} in de Sheet"
    if not os.path.exists(bron):
        sys.exit(f"{bron} bestaat niet. Een datum als 2026-08-20 mag ook: dan wordt de "
                 f"kopie uit de Sheet gebruikt.")
    with open(bron, encoding="utf-8") as f:
        inhoud = json.load(f)
    tab = opslag.werkblad_naam(gebruiker)
    if tab not in inhoud:
        sys.exit(f"{tab} staat niet in {os.path.basename(bron)}. "
                 f"Wel erin: {', '.join(inhoud)}")
    return inhoud[tab]["stats"], os.path.basename(bron)


def herstel(gebruiker, bron):
    """Eén gebruiker terugzetten uit een reservekopie.

    Bewust niet samenvoegen: als je herstelt wil je precies de oude stand terug, niet een
    mengsel met wat er nu staat. Daarom wordt er eerst een verse kopie gemaakt van hoe het
    nú is — mocht je je bedenken."""
    stats, waaruit = _uit_kopie(gebruiker, bron)
    v = stats.get("vocab_stats") or {}
    print(f"Uit {waaruit}: {len(v)} woorden.")

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
    # samenvoegen=False: herstellen betekent terugzetten, niet mengen. De vlag voor de
    # dagelijkse kopie gaat eruit, anders zou de app denken dat die vandaag al gemaakt is
    # terwijl deze stand net is overschreven.
    (stats.get("badges") or {}).pop("_backup_op", None)
    opslag.bewaar(gebruiker, stats, samenvoegen=False)
    print(f"{gebruiker} teruggezet naar {waaruit}.")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--lijst", action="store_true", help="laat zien wat er bewaard is")
    p.add_argument("--herstel", nargs=2, metavar=("GEBRUIKER", "BRON"),
                   help="zet één gebruiker terug. BRON is een bestand uit backups/ of "
                        "een datum als 2026-08-20 (dan uit het tabblad Backups)")
    args = p.parse_args()
    if args.lijst:
        lijst()
    elif args.herstel:
        herstel(args.herstel[0], args.herstel[1])
    else:
        maak_kopie()


if __name__ == "__main__":
    main()
