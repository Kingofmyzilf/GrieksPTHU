# -*- coding: utf-8 -*-
"""Controleert wat de snelle app snel houdt: de opslag en de voorgebakken NT-gegevens.

Twee dingen waren de app kwijtgeraakt, en beide zag je niet aan de code.

1. De opslagfrequentie hing aan `1 if BIJBEL else 5`. De gedachte was 'bijbeltekst
   aanwezig = mijn eigen machine'. Toen de NT-tekst aan de deploytak werd toegevoegd
   werd BIJBEL óók op de gehoste app True, en ging die van één-op-vijf naar één-op-één.
   Eén opslag is twee netwerkrondjes naar Google: gemeten 1,9 s. Zo'n afgeleide
   schakelaar hoort niet: het interval is een keuze op zichzelf, en dat toetst dit.

2. De opslag stond op het antwoordpad, vóór het tekenen van de uitslag. Gemeten: 2155 ms
   van klik tot beeld, en 37 ms nadat het naar de achtergrond ging. Dus wordt hier
   nagerekend dat noteer() alleen rekent en niets wegschrijft, en dat de antwoordpaden
   bewaar_los gebruiken in plaats van een awaited opslag.

3. De hele NT-tekst inlezen kostte 88 MB en 420 ms (op 0,1 CPU dus ~4 s), synchroon
   terwijl je een kaart omdraaide. Wat de app er echt uit haalt staat voorgebakken in
   snel_nt.json.gz; hier wordt geteld of alle vier de onderdelen erin zitten en of de
   app nergens meer de hele tekst opent.

Draaien:  py gereedschap/test_snel.py
"""
import gzip
import inspect
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

SNEL = "snel_nt.json.gz"
fouten = []


def kijk(goed, melding):
    if goed:
        print(f"  ok   {melding}")
    else:
        fouten.append(melding)
        print(f"  MIS  {melding}")


def main():
    app = open("grieks_app.py", encoding="utf-8").read()

    print("== de opslag ==")
    kijk("OPSLAG_INTERVAL = 5" in app, "het interval staat op 5, geteld over alle oefeningen")
    kijk(not re.search(r"OPSLAG_INTERVAL\s*=.*BIJBEL", app),
         "het interval hangt niet aan de aanwezigheid van de bijbeltekst")
    kijk("def bewaar_los" in app, "bewaar_los bestaat (opslaan zonder erop te wachten)")
    kijk("background_tasks" in app, "de opslag gaat als achtergrondtaak")

    import grieks_gebruiker as gebruikers
    # Alleen de code, niet de docstring: die legt juist uit dat de opslag hier weg is.
    bron_noteer = inspect.getsource(gebruikers.Gebruiker.noteer)
    code_noteer = bron_noteer.split('"""')[2] if bron_noteer.count('"""') >= 2 else bron_noteer
    kijk("bewaar" not in code_noteer,
         "noteer() rekent alleen en schrijft niet weg (dat beslist de app)")

    # Alle awaited opslag die overblijft hoort geforceerd te zijn: einde ronde, verwarparen,
    # instellingen, uitloggen. Een niet-geforceerde awaited opslag is precies de fout die de
    # app traag maakte. In bewaar_los staat er één, en dat is de bedoeling: die zit al in
    # een achtergrondtaak.
    begin, eind = app.index("def bewaar_los"), app.index("def streamlit_adres")
    binnen_los = app[begin:eind]
    buiten_los = app[:begin] + app[eind:]
    patroon = r"await run\.io_bound\((g|gebruiker)\.bewaar\)"
    los = [r.strip() for r in buiten_los.split("\n") if re.search(patroon, r)]
    kijk(not los, f"geen niet-geforceerde opslag wordt nog afgewacht ({los[:2]})")
    # Alleen echte code: de docstring van bewaar_los noemt de oude regel ook, tussen
    # aanhaaltekens. Zonder die uitzondering telde deze controle er twee.
    echt = [r for r in binnen_los.split("\n")
            if re.search(r"^\s*\w+ = await run\.io_bound\(g\.bewaar\)\s*$", r)]
    kijk(len(echt) == 1,
         f"bewaar_los wacht zelf wél, maar dan in een achtergrondtaak ({len(echt)}x)")
    kijk(app.count("bewaar_los(g,") >= 10,
         f"de antwoordpaden gebruiken bewaar_los ({app.count('bewaar_los(g,')} plekken)")

    print("== het interval doet wat het zegt ==")
    g = gebruikers.Gebruiker("proef", "proef", interval=5)
    kijk(g.interval == 5, f"een gebruiker krijgt interval 5 mee (kreeg {g.interval})")
    w = {"grieks": "λόγος", "streak": 0}
    for n in range(1, 6):
        g.noteer(dict(w), True)
        kijk(g.sinds_opslag == n, f"na {n} beurten staat de teller op {g.sinds_opslag}")

    print("== de voorgebakken NT-gegevens ==")
    kijk(os.path.exists(SNEL), f"{SNEL} bestaat")
    if not os.path.exists(SNEL):
        klaar()
        return
    groot = os.path.getsize(SNEL)
    kijk(groot < 600 * 1024, f"{SNEL} is {groot/1024:.0f} kB (ruim onder de 600)")
    with gzip.open(SNEL, "rt", encoding="utf-8") as f:
        d = json.load(f)
    for naam, minimaal in (("vormen", 700), ("klank", 5), ("klankformules", 5),
                           ("verzen", 300), ("boeken", 27), ("hoofdstuk_strongs", 250)):
        kijk(len(d.get(naam) or {}) >= minimaal,
             f"{naam}: {len(d.get(naam) or {})} (minstens {minimaal})")
    # De verzen moeten volledig binnen de basiswoordenlijst vallen; anders vraagt het
    # ontleden je een woord te benoemen dat niet in je lijst staat.
    import grieks_motor as motor
    basis = {str(w.get("strong", "") or "").lstrip("G").strip()
             for w in (motor.laad_vocab_db() or []) if w.get("strong")}
    buiten = [r for r, ws in d["verzen"].items()
              if any(str(x.get("strong", "") or "").lstrip("G").strip() not in basis
                     for x in ws)]
    kijk(not buiten, f"elk vers valt volledig binnen de basiswoordenlijst ({buiten[:2]})")
    lengtes = [len(ws) for ws in d["verzen"].values()]
    kijk(all(4 <= n <= 12 for n in lengtes),
         f"alle verzen zijn 4-12 woorden (nu {min(lengtes)}-{max(lengtes)})")
    velden = {k for ws in list(d["verzen"].values())[:50] for w in ws for k in w}
    kijk("parsing_info" in velden and "grieks" in velden and "strong" in velden,
         f"de velden die het ontleden nodig heeft zitten erin ({sorted(velden)})")

    print("== de app opent de NT-tekst niet meer ==")
    for weg in ("laad_bijbel_db", "_bijbel_strong_index", "klankwet_index(",
                "bijbel_boek_index", "laad_bijbel_boek"):
        regels = [r.strip() for r in app.split("\n")
                  if weg in r and not r.strip().startswith("#")]
        kijk(not regels, f"geen aanroep van {weg} meer ({regels[:1]})")
    kijk("snel_nt.json.gz" in app, "de app leest snel_nt.json.gz")

    print("== staat het in de deploytak? ==")
    deploy = open(os.path.join("gereedschap", "maak_deploy.py"), encoding="utf-8").read()
    kijk('"snel_nt.json.gz"' in deploy, "snel_nt.json.gz gaat mee naar de deploytak")
    kijk('\n    "nt",' not in deploy, "de hele NT-tekst gaat niet meer mee")

    klaar()


def klaar():
    print()
    if fouten:
        print(f"{len(fouten)} probleem/problemen:")
        for f_ in fouten:
            print(f"  - {f_}")
        sys.exit(1)
    print("alles in orde")


if __name__ == "__main__":
    main()
