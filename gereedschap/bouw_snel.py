# -*- coding: utf-8 -*-
"""Bakt snel_nt.json: wat de snelle app uit de NT-tekst nodig heeft, en niets meer.

De snelle app laadde de hele NT-tekst in. Op schijf is dat 2,9 MB, maar in het geheugen
88 MB, en het inlezen kostte gemeten 420 ms op een SSD — op Render's gratis laag (0,1 CPU)
dus ruwweg vier seconden. Dat gebeurde synchroon terwijl je een kaart omdraaide: bij een
woord met streak >= 30 haalt de app een echte NT-vorm op, en dan stond de app stil. Met 130
mastery-woorden in één lijst merk je dat.

Wat de app er echt uit haalt is vier dingen, en die passen samen in ruim een megabyte:

    vormen        per Strong-nummer een handvol verbogen vormen zoals ze in het NT staan
                  (voor de mastery-kaarten)
    klank         de klankwetvormen, met hun formules (de klankwetten-oefening)
    verzen        korte verzen die volledig binnen de basiswoordenlijst vallen (ontleden)
    hoofdstukken  per boek de hoofdstukken, en per hoofdstuk welke Strong-nummers erin
                  staan (de filter 'oefen de werkwoorden uit deze tekst')

Het zware werk blijft in de Streamlit-app: daar staat de hele tekst, en daar hoort hij ook.
Deze app is voor woorden en rijtjes op je telefoon.

Het bestand gaat ingepakt (snel_nt.json.gz): 1,6 MB tekst wordt 231 kB, en uitpakken kost
gemeten minder dan de tijd die je met het downloaden wint. Net als de NT-tekst zelf, die
per boek ingepakt in nt/ staat.

Opnieuw bakken (bijvoorbeeld om een andere set verzen te trekken):

    py gereedschap/bouw_snel.py [--verzen N] [--vormen N]
"""
import gzip
import json
import os
import random
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

import uitvoer

uitvoer.zet_utf8()

import grieks_motor as motor

UIT = os.path.join(REPO, "snel_nt.json.gz")
# Wat er per woord in een vers bewaard blijft. 'transliteratie' en 'interpunctie' gaan eruit:
# de snelle app leest ze nergens (nagekeken met grep), en samen zijn ze 200 kB.
VERS_VELDEN = ("grieks", "parsing_info", "strong", "vertaling_nl", "vertaling_bsb")
# Zoveel vormen per woord. Vijf tot acht is genoeg om een uitgang te laten herkennen zonder
# dat je steeds dezelfde vorm krijgt; meer maakt het bestand alleen groter.
VORMEN_PER_WOORD = 8
# De verzen voor het ontleden. 490 is precies het aantal korte verzen (4-12 woorden) dat
# volledig binnen de basiswoordenlijst valt — daar zit dus geen keuze in tenzij je minder
# wil. Ze spreiden van 1 Korintiërs 10:12 tot Romeinen 8:8.
VERZEN = 0                 # 0 = alle verzen die volledig binnen de lijst vallen
# Het NT gebruikt het teken ’ ook als apostrof; die tekens strippen we van een losse vorm.
RAFEL = " ,.;·:!?"


def basiswoorden():
    """Strong-nummer -> woord uit de basislijst. Voor iedereen hetzelfde: de voortgang van
    een gebruiker zit er niet in, alleen het lemma en de citatievorm."""
    uit = {}
    for w in (motor.laad_vocab_db() or []):
        s = str(w.get("strong", "") or "").lstrip("G").strip()
        if s and s not in uit:
            uit[s] = w
    return uit


def maak_vormen(db, basis, hoeveel):
    """Per Strong-nummer een paar verschillende verbogen vormen uit het NT."""
    index = motor._bijbel_strong_index(db) or {}
    uit = {}
    for strong in basis:
        gezien, vormen = set(), []
        for ref in (index.get(strong) or [])[:80]:
            for x in db.get(ref, []):
                if str(x.get("strong", "") or "").lstrip("G").strip() != strong:
                    continue
                vorm = str(x.get("grieks", "") or "").strip(RAFEL)
                sleutel = motor.normaliseer_accent(vorm)
                if not vorm or sleutel in gezien:
                    continue
                gezien.add(sleutel)
                vormen.append({"v": vorm, "p": x.get("parsing_info", ""), "r": ref})
                if len(vormen) >= hoeveel:
                    break
            if len(vormen) >= hoeveel:
                break
        if vormen:
            uit[strong] = vormen
    return uit


def maak_klank(db, basis):
    """De klankwetvormen en hun formules.

    klankwet_index krijgt normaal de woordenlijst van de ingelogde gebruiker mee, maar
    gebruikt daar alleen het lemma en de citatievorm uit — en die zijn voor iedereen
    gelijk. Wat per gebruiker verschilt is het filteren op streak, en dat doet de app
    daarna zelf op het Strong-nummer.
    """
    index = motor.klankwet_index(db, basis) or {}
    # tuples worden in json lijsten; de app leest ze als (vorm, lemma, info, ref, strong)
    return ({k: [list(r) for r in v] for k, v in index.items()},
            motor.klankwet_formule_index(db, basis) or {})


def maak_verzen(db, basis, hoeveel):
    """Korte verzen waarvan élk woord in de basislijst staat.

    Waarom die eis: het ontleden vraagt je de woorden te benoemen, en dat kan niet bij een
    woord dat niet in je lijst zit. De app filtert daarna nog op wat jíj kent (streak), dus
    de pot moet ruim zijn en van makkelijk tot moeilijk lopen.
    """
    kandidaten = []
    for ref, woorden in db.items():
        if not 4 <= len(woorden) <= 12:
            continue
        if all(str(x.get("strong", "") or "").lstrip("G").strip() in basis for x in woorden):
            kandidaten.append(ref)
    kandidaten.sort()
    if hoeveel and hoeveel < len(kandidaten):
        # Vast zaad: opnieuw bakken zonder --verzen geeft dezelfde set, zodat een
        # herbouw niet ongemerkt de hele oefenpot omgooit.
        random.seed(20260822)
        kandidaten = sorted(random.sample(kandidaten, hoeveel))
    return {ref: [{k: w[k] for k in VERS_VELDEN if w.get(k)} for w in db[ref]]
            for ref in kandidaten}


def maak_hoofdstukken(db):
    """boek -> hoofdstukken, en 'boek hoofdstuk' -> de Strong-nummers die erin staan.

    Dat tweede is de filter 'oefen de werkwoorden die je in deze tekst tegenkomt' bij de
    stamtijden. Alleen de nummers, niet de tekst: dat is een fractie van de verzen zelf en
    de oefening heeft niet meer nodig.
    """
    boeken, strongs = {}, {}
    for ref, zin in db.items():
        boek, _, rest = ref.rpartition(" ")
        hfd = rest.split(":")[0]
        boeken.setdefault(boek, set()).add(hfd)
        sleutel = f"{boek} {hfd}"
        doel = strongs.setdefault(sleutel, set())
        for w in zin:
            s = str(w.get("strong", "") or "").lstrip("G").strip()
            if s:
                doel.add(s)
    return ({b: sorted(h, key=lambda x: int(x) if x.isdigit() else 0)
             for b, h in boeken.items()},
            {k: sorted(v, key=lambda x: int(x) if x.isdigit() else 0)
             for k, v in strongs.items()})


def main():
    vormen_n = VORMEN_PER_WOORD
    verzen_n = VERZEN
    for i, arg in enumerate(sys.argv):
        if arg == "--vormen" and i + 1 < len(sys.argv):
            vormen_n = int(sys.argv[i + 1])
        if arg == "--verzen" and i + 1 < len(sys.argv):
            verzen_n = int(sys.argv[i + 1])

    t = time.perf_counter()
    db = motor.laad_bijbel_db()
    if not db:
        sys.exit("Geen NT-tekst gevonden. Deze bouwer heeft nt/ nodig (zie "
                 "gereedschap/bouw_nt.py); de app zelf niet meer.")
    basis = basiswoorden()
    print(f"NT: {len(db)} verzen · basislijst: {len(basis)} woorden "
          f"({time.perf_counter()-t:.1f} s)")

    vormen = maak_vormen(db, basis, vormen_n)
    print(f"  vormen        {len(vormen)} woorden, max {vormen_n} vormen elk")
    klank, formules = maak_klank(db, basis)
    print(f"  klank         {len(klank)} klankwetten, "
          f"{sum(len(v) for v in klank.values())} vormen, {len(formules)} formules")
    verzen = maak_verzen(db, basis, verzen_n)
    print(f"  verzen        {len(verzen)} verzen van 4-12 woorden, volledig in de lijst")
    boeken, kap_strongs = maak_hoofdstukken(db)
    print(f"  hoofdstukken  {len(boeken)} boeken, {len(kap_strongs)} hoofdstukken")

    data = {"gemaakt": time.strftime("%Y-%m-%d"),
            "vormen": vormen, "klank": klank, "klankformules": formules,
            "verzen": verzen, "boeken": boeken, "hoofdstuk_strongs": kap_strongs}
    tekst = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    with gzip.open(UIT, "wb", compresslevel=9) as f:
        f.write(tekst)

    groot = os.path.getsize(UIT)
    print(f"\n{UIT}: {groot/1024:.0f} kB ingepakt ({len(tekst)/1024:.0f} kB tekst)")
    for naam in ("vormen", "klank", "klankformules", "verzen", "boeken",
                 "hoofdstuk_strongs"):
        deel = len(json.dumps(data[naam], ensure_ascii=False,
                              separators=(",", ":")).encode())
        print(f"  {naam:18} {deel/1024:7.0f} kB")
    nt = sum(os.path.getsize(os.path.join("nt", n)) for n in os.listdir("nt"))
    print(f"\nnt/ was {nt/1048576:.1f} MB op schijf en 88 MB in het geheugen; "
          f"dit is {groot/1024:.0f} kB.")


if __name__ == "__main__":
    main()
