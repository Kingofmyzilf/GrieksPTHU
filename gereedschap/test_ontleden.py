# -*- coding: utf-8 -*-
"""Controleert de oefenstof van 🔍 Hebreeuws ontleden.

Deze proef bestaat omdat de eerste versie van die oefening te raden was. Bij de vraag
כְּ + הַ + חֶסֶד begonnen drie van de vier antwoorden met een ב en één met een כ; je wees
de vreemde eend aan en had hem goed zonder één woord Hebreeuws te kennen. Dat is precies
wat je niet wil in een oefening die herkennen moet trainen.

Dus wordt hier nagerekend of een vraag te beantwoorden is zonder hem te lezen:

  * staat het goede antwoord tussen de keuzes;
  * zijn er genoeg keuzes;
  * begint het antwoord als enige met een andere letter (de vreemde eend);
  * is het antwoord veel korter of langer dan de rest;
  * en is elke vorm terug te vinden in de Tenach zoals hij er staat.

Draaien:  py gereedschap/test_ontleden.py
"""
import collections
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

import uitvoer

uitvoer.zet_utf8()

import hebreeuws as H

BESTAND = os.path.join(REPO, "hebreeuws_ontleden.json")
fouten = []


def kijk(goed, melding):
    if goed:
        print(f"  ok   {melding}")
    else:
        fouten.append(melding)
        print(f"  MIS  {melding}")


def main():
    if not os.path.exists(BESTAND):
        sys.exit("hebreeuws_ontleden.json niet gevonden — draai "
                 "gereedschap/bouw_hebreeuws_ontleden.py")
    with open(BESTAND, encoding="utf-8") as f:
        groepen = json.load(f)["groepen"]
    print(f"{len(groepen)} groepen, samen {sum(len(g['vragen']) for g in groepen)} vragen")
    print()

    for groep in groepen:
        vragen = groep["vragen"]
        print(f"--- {groep['naam']} ({len(vragen)} vragen) ---")
        kijk(len(vragen) >= 20, f"{len(vragen)} vragen (minstens 20)")

        zonder = [v for v in vragen if v["antwoord"] not in v["opties"]]
        kijk(not zonder, f"het goede antwoord staat altijd tussen de keuzes "
                         f"({len(zonder)} keer niet)")

        te_weinig = [v for v in vragen if len(set(v["opties"])) < 3]
        kijk(not te_weinig, f"altijd minstens drie keuzes ({len(te_weinig)} keer niet)")

        # De vreemde eend: begint het antwoord als enige met een andere letter?
        eend = []
        for v in vragen:
            eersten = collections.Counter(str(o)[:1] for o in v["opties"])
            if eersten[str(v["antwoord"])[:1]] == 1 and len(eersten) == 2:
                eend.append(v["vorm"])
        kijk(not eend, f"nooit te raden op de eerste letter ({len(eend)} keer wel"
                       + (f", bijv. {eend[0]}" if eend else "") + ")")

        # Lengte: het antwoord mag er niet uitspringen doordat het veel korter of langer is.
        lang = []
        for v in vragen:
            lengtes = [len(str(o)) for o in v["opties"]]
            eigen = len(str(v["antwoord"]))
            anderen = [n for o, n in zip(v["opties"], lengtes) if o != v["antwoord"]]
            if anderen and (eigen > max(anderen) * 1.8 or eigen * 1.8 < min(anderen)):
                lang.append(v["vorm"])
        kijk(not lang, f"het antwoord springt niet uit door zijn lengte "
                       f"({len(lang)} keer wel)")

        leeg = [v for v in vragen if not str(v.get("vers", "")).strip()]
        kijk(not leeg, f"bij elke vraag staat een vindplaats ({len(leeg)} keer niet)")

    # En de vormen moeten echt in de Tenach staan, precies zo.
    print()
    print("--- staan de vormen echt in de Tenach? ---")
    alle_vormen = set()
    for boek in H.tenach_index():
        for vers in H.laad_tenach_boek(boek["bestand"]):
            for w in H.woorden_van(vers):
                alle_vormen.add(H.zonder_leesteken(w["vorm"])[0])
    onbekend = []
    for groep in groepen:
        for v in groep["vragen"]:
            if v["vorm"] not in alle_vormen:
                onbekend.append((groep["naam"], v["vorm"]))
    kijk(not onbekend, f"elke vorm komt in de Tenach voor ({len(onbekend)} niet"
                       + (f", bijv. {onbekend[0][1]!r}" if onbekend else "") + ")")

    print()
    if fouten:
        sys.exit(f"{len(fouten)} mis")
    print("GESLAAGD")


if __name__ == "__main__":
    main()
