# -*- coding: utf-8 -*-
"""Controleert de paradigma's van 'Actief beheersen' (actief_beheersen.json).

Dit bestand is de enige oefening waarin je een vorm zelf moet produceren, dus wat er staat
móet kloppen. Drie dingen zijn hier daadwerkelijk fout gegaan, en alle drie zag je ze niet:

  * Een Latijnse á in plaats van een Griekse ά, in λυσάμενος, λυσάσης en λυσάμενον. Het
    nakijken ging goed (normaliseer_accent zet een Latijnse a om naar α), dus er kwam nooit
    een klacht — maar op het scherm stond verkeerd Grieks.
  * Het lidwoord stond er twee keer in, onder 'Groep 1: Lidwoord' en onder 'Lidwoorden',
    met dezelfde vormen en andere ids. Dat komt dus dubbel zo vaak voorbij en je voortgang
    staat op twee plekken.
  * Twee paradigma's die het tentamen vraagt ontbraken: αὐτός/αὐτή/αὐτό (Grieks 1) en het
    participium praesens medium λυόμενος (Grieks 2). Zie gereedschap/vul_actief_aan.py.

De ids zijn de sleutel waaronder je voortgang in actief_stats staat. Twee cellen met
hetzelfde id delen dus je score; een id dat verandert laat je voortgang achter.

Draaien:  py gereedschap/test_actief.py
"""
import collections
import json
import os
import re
import sys
import unicodedata

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

import uitvoer

uitvoer.zet_utf8()

LATIJN = re.compile(r"[A-Za-zÀ-ÿ]")
fouten = []

# Paradigma's die twee keer voorkomen en (nog) niet zijn samengevoegd, met de reden.
# Ze worden hieronder wél afgedrukt, zodat de lijst niet stil kan groeien.
#
# Het lidwoord staat er twee keer in: als 'Groep 1: Lidwoord' tussen de declinatiegroepen,
# en als 'Lidwoorden' apart. Dezelfde acht vormen per geslacht, andere ids. Eén set
# weghalen is geen kwestie van een regel schrappen: de ids zijn de sleutel waaronder je
# voortgang in actief_stats staat, en migreer_actief_ids() is eenmalig (die zit achter de
# vlag _ids_v2, die bij bestaande gebruikers al staat). Wie de weggehaalde set heeft
# geoefend, verliest die streaks dus — bij het Demo-account zijn dat 24 cellen. Dat is een
# keuze voor Bob, niet voor deze test.
DUBBEL_MAG = {
    "Grieks 1 / Groep 1: Lidwoord / M": "lidwoord staat ook onder 'Lidwoorden'",
    "Grieks 1 / Groep 1: Lidwoord / V": "lidwoord staat ook onder 'Lidwoorden'",
    "Grieks 1 / Groep 1: Lidwoord / O": "lidwoord staat ook onder 'Lidwoorden'",
}


def kijk(goed, melding):
    if goed:
        print(f"  ok   {melding}")
    else:
        fouten.append(melding)
        print(f"  MIS  {melding}")


def cellen(ab):
    for cursus, groepen in ab.items():
        for groep, rijtjes in groepen.items():
            for rij, cel in rijtjes.items():
                for c in cel:
                    yield cursus, groep, rij, c


def main():
    with open("actief_beheersen.json", encoding="utf-8") as f:
        ab = json.load(f)

    print("== de vormen ==")
    alles = list(cellen(ab))
    kijk(len(alles) > 500, f"er zijn {len(alles)} oefenbare cellen")
    vreemd = [(f"{g}/{r}", c["label"], c["vorm"],
               [unicodedata.name(x, "?") for x in c["vorm"] if LATIJN.match(x)])
              for _cu, g, r, c in alles if LATIJN.search(c["vorm"])]
    kijk(not vreemd, f"geen Latijnse letters in een Griekse vorm ({vreemd[:2]})")
    leeg = [f"{g}/{r}/{c['label']}" for _cu, g, r, c in alles if not str(c.get("vorm", "")).strip()]
    kijk(not leeg, f"geen lege vormen ({leeg[:3]})")
    zonder_id = [f"{g}/{r}/{c['label']}" for _cu, g, r, c in alles if not c.get("id")]
    kijk(not zonder_id, f"elke cel heeft een id ({zonder_id[:3]})")

    print("== de ids ==")
    tel = collections.Counter(c["id"] for _cu, _g, _r, c in alles)
    dubbel = [(i, n) for i, n in tel.items() if n > 1]
    kijk(not dubbel, f"elk id komt één keer voor ({dubbel[:3]})")
    # Een id moet in een Sheet-cel passen en als sleutel leesbaar blijven.
    raar = [c["id"] for _cu, _g, _r, c in alles if not re.fullmatch(r"[a-z0-9_]+", c["id"])]
    kijk(not raar, f"elk id bestaat uit kleine letters, cijfers en streepjes ({raar[:3]})")

    print("== geen paradigma twee keer ==")
    # Twee rijtjes met exact dezelfde vormen zijn hetzelfde rijtje onder een andere naam.
    op_vormen = collections.defaultdict(list)
    for cursus, groepen in ab.items():
        for groep, rijtjes in groepen.items():
            for rij, cel in rijtjes.items():
                sleutel = tuple(c["vorm"] for c in cel)
                if len(sleutel) >= 4:
                    op_vormen[sleutel].append(f"{cursus} / {groep} / {rij}")
    alle_dubbel = {k: v for k, v in op_vormen.items() if len(v) > 1}
    for vormen, waar in alle_dubbel.items():
        bekend = " (bekend)" if any(m in DUBBEL_MAG for m in waar) else ""
        print(f"       {' == '.join(waar)}{bekend}  ({', '.join(vormen[:4])} …)")
    nieuw = {k: v for k, v in alle_dubbel.items()
             if not any(m in DUBBEL_MAG for m in v)}
    kijk(not nieuw, f"geen ONVERWACHT dubbel paradigma ({len(nieuw)}; "
                    f"{len(alle_dubbel)} bekend dubbel)")

    print("== vormopbouw per groep ==")
    # Na je antwoord toont de app de vorm als stam (wit) + uitgang (oranje), maar alleen
    # als bééide gevuld zijn. Een rijtje zonder uitgang laat die opbouw dus stil weg. Dat
    # mag (voornaamwoorden leer je heel), maar niet als de rest van de groep het wél heeft:
    # zo ontbrak de opbouw bij λυόμενος terwijl de vier andere participia hem hadden.
    scheef = []
    for cursus, groepen in ab.items():
        for groep, rijtjes in groepen.items():
            met = [r for r, cel in rijtjes.items() if any(c.get("uitgang") for c in cel)]
            zonder = [r for r, cel in rijtjes.items() if not any(c.get("uitgang") for c in cel)]
            if met and zonder:
                scheef.append(f"{cursus} / {groep}: {len(met)} rijtjes mét uitgang, "
                              f"zonder = {zonder}")
    for s in scheef:
        print(f"       {s}")
    kijk(not scheef, f"binnen een groep heeft elk rijtje de vormopbouw, of geen ({len(scheef)})")
    # En waar een uitgang staat, moet stam+uitgang de vorm zijn — anders toont het scherm
    # iets anders dan het antwoord.
    kapot = [f"{g}/{r}/{c['label']}: {c['stam']}+{c['uitgang']} != {c['vorm']}"
             for _cu, g, r, c in alles
             if c.get("uitgang") and c["stam"] + c["uitgang"] != c["vorm"]]
    kijk(not kapot, f"stam + uitgang is samen de vorm ({kapot[:3]})")

    print("== per cursus ==")
    for cursus, groepen in ab.items():
        n = sum(len(r) for g in groepen.values() for r in g.values())
        rijtjes = sum(len(g) for g in groepen.values())
        print(f"       {cursus}: {len(groepen)} groepen, {rijtjes} rijtjes, {n} cellen")
    kijk(set(ab) == {"Grieks 1", "Grieks 2", "Grieks 3"},
         f"de drie cursussen staan erin ({sorted(ab)})")

    print("== wat het tentamen vraagt ==")
    # De drie pdf's 'Vormleer om actief te beheersen' staan buiten de repo (Dropbox), dus
    # die kan deze test niet lezen. Wat hij wél kan: nagaan dat de paradigma's die daaruit
    # zijn nagekomen er nog staan. Zie gereedschap/vul_actief_aan.py voor de herkomst.
    moet = [("Grieks 1", "Pronomen Personale", "3e Persoon m. (hij)", "αὐτός"),
            ("Grieks 1", "Pronomen Personale", "3e Persoon v. (zij)", "αὐτή"),
            ("Grieks 1", "Pronomen Personale", "3e Persoon o. (het)", "αὐτό"),
            ("Grieks 2", "Participium (λύω)", "Praesens Medium (λυόμενος)", "λυόμενος")]
    for cursus, groep, rij, eerste in moet:
        cel = ((ab.get(cursus) or {}).get(groep) or {}).get(rij) or []
        kijk(bool(cel) and cel[0]["vorm"] == eerste,
             f"{cursus} / {rij} staat erin en begint met {eerste} "
             f"({cel[0]['vorm'] if cel else 'ontbreekt'})")

    print()
    if fouten:
        print(f"{len(fouten)} probleem/problemen:")
        for f_ in fouten:
            print(f"  - {f_}")
        sys.exit(1)
    print("alles in orde")


if __name__ == "__main__":
    main()
