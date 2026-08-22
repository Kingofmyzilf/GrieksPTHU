# -*- coding: utf-8 -*-
"""Rekent de scoreregels van de snelle app na.

Deze test bestaat om een reden. In de woordenschat van de snelle app stond de
streak-verhoging een tijd in de verkeerde tak van een if: een fout antwoord gaf streak, een
goed antwoord werd als fout geteld. De code ernaast zag er goed uit, want beide takken
bestonden nog en deden ieder iets plausibels. Alleen door de score na te méten kwam het
boven.

Wat hier wordt nagerekend:

    goed, schoon                 streak gaat omhoog met de punten van die vraagvorm
    goed, antwoord al gezien     geen punten, maar ook geen aftrek
    fout, eerste misser          streak blijft staan (je mag het nog eens proberen)
    fout, tweede misser          streak -2
    fout vanaf streak 16         meteen -2, want dat woord beheerste je al
    goed, bronwoord gespiekt     geen punten, maar ook geen aftrek: je hébt de vorm goed
                                 vertaald, het ging alleen met het lemma erbij
    fout, bronwoord gespiekt     -2 en geen herkansing: met het lemma erbij was het al
                                 makkelijker

Draaien:  py gereedschap/test_scoren.py
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

import uitvoer

uitvoer.zet_utf8()

import grieks_gebruiker as gebruikers

STREAK_STRAF = 2
fouten = []


def kijk(goed, melding):
    if goed:
        print(f"  ok   {melding}")
    else:
        fouten.append(melding)
        print(f"  MIS  {melding}")


def beurt(streak, goed, punten=1, straf=None, scoor=True):
    """Eén beurt op een woord met deze streak; geeft (streak, goed, fout) terug."""
    g = gebruikers.Gebruiker("proef", "proef", interval=99)
    w = {"grieks": "λόγος", "streak": streak, "score_goed": 0, "score_fout": 0}
    g.noteer(w, goed, punten, straf, scoor)
    return (int(w["streak"]), int(w["score_goed"]), int(w["score_fout"]))


def main():
    print("== de gewone gevallen ==")
    kijk(beurt(5, True, punten=3) == (8, 1, 0),
         f"goed met typen (+3): {beurt(5, True, punten=3)}")
    kijk(beurt(5, True, punten=1) == (6, 1, 0),
         f"goed met aanwijzen (+1): {beurt(5, True, punten=1)}")
    kijk(beurt(5, True, punten=3, scoor=False) == (5, 0, 0),
         f"goed maar antwoord al gezien: niets erbij, niets eraf: {beurt(5, True, punten=3, scoor=False)}")
    kijk(beurt(5, False, straf=None) == (5, 0, 1),
         f"eerste misser: streak blijft staan: {beurt(5, False, straf=None)}")
    kijk(beurt(5, False, straf=STREAK_STRAF) == (3, 0, 1),
         f"tweede misser: -2: {beurt(5, False, straf=STREAK_STRAF)}")
    kijk(beurt(1, False, straf=STREAK_STRAF) == (0, 0, 1),
         f"streak kan niet onder nul: {beurt(1, False, straf=STREAK_STRAF)}")

    print("== bronwoord gespiekt bij een NT-vorm ==")
    # Hier ging het één keer mis in de bouw: er werd afgetrokken bij een goed antwoord.
    # Dat is niet de bedoeling — je hébt de vorm dan vertaald, het ging alleen met het
    # lemma erbij. Dat levert geen punten op en verder niets.
    goed_na = beurt(32, True, punten=3, scoor=False)
    kijk(goed_na == (32, 0, 0),
         f"goed mét bronwoord: geen punten, maar ook geen aftrek: {goed_na}")
    kijk(goed_na[0] == 32, "een goed antwoord kost nooit streak, ook niet na spieken")
    fout_na = beurt(32, False, straf=STREAK_STRAF)
    kijk(fout_na == (30, 0, 1),
         f"fout mét bronwoord: -2, meteen een echte misser: {fout_na}")

    print("== staat het ook zo in de app? ==")
    app = open("grieks_app.py", encoding="utf-8").read()
    kijk("bron_gespiekt" in app, "de sessie houdt bij of je het bronwoord opvroeg")
    kijk('knoppen.append("Bronwoord")' in app, "de knop Bronwoord bestaat")
    # De knop mag alleen bij een NT-vorm: bij de woordenboekvorm zou hij het antwoord zijn.
    blok = app[app.index('knoppen.append("Bronwoord")') - 400:
               app.index('knoppen.append("Bronwoord")')]
    kijk("if sessie.toonvorm" in blok, "de knop staat er alleen bij een NT-vorm")
    kijk(re.search(r"straf=STREAK_STRAF if gespiekt", app) is None,
         "een goed antwoord na spieken krijgt GEEN aftrek mee")
    kijk("or gespiekt" in app, "na spieken is een misser meteen een echte misser")
    # De aftrek hoort binnen de fout-tak van noteer. Dat is geen stijlkwestie: staat hij
    # erbuiten, dan kan een verkeerd doorgegeven `straf` streak kosten bij een goed
    # antwoord — precies de fout die hier gemaakt is.
    import inspect
    bron = inspect.getsource(gebruikers.Gebruiker.noteer)
    code = bron.split('"""')[2]
    regels = [r for r in code.split("\n") if "straf is not None" in r]
    kijk(len(regels) == 1 and regels[0].startswith(" " * 12),
         f"de aftrek staat binnen de fout-tak ({[r.strip() for r in regels]})")

    print("== de vormopbouw bij het ontleden ==")
    kijk("def ont_opbouw_html" in app, "ont_opbouw_html bestaat")
    kijk("ont_opbouw" in app and '"ont_opbouw": True' in app,
         "de schakelaar staat in de instellingen en staat standaard aan")
    # Alleen als alle vragen over dat woord af zijn: een gekleurde uitgang verraadt anders
    # de naamval die je nog moet benoemen.
    # De regel staat binnen het blok dat met 'if alles_af:' begint. Zoek dus vanaf die
    # regel terug tot de eerstvolgende if, in plaats van een vast aantal tekens.
    i = app.index("opbouw = ont_opbouw_html")
    voor = app[:i].rsplit("if alles_af:", 1)
    kijk(len(voor) == 2 and "terugkoppeling.clear()" not in voor[1],
         "de opbouw komt pas als alle vragen over dat woord af zijn")

    print()
    if fouten:
        print(f"{len(fouten)} probleem/problemen:")
        for f_ in fouten:
            print(f"  - {f_}")
        sys.exit(1)
    print("alles in orde")


if __name__ == "__main__":
    main()
