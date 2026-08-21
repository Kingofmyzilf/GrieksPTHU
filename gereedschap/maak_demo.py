# -*- coding: utf-8 -*-
"""Zet een demo-gebruiker in de Sheet: iemand die er al een tijd mee bezig is.

Bedoeld om de app te laten zien zonder je eigen voortgang op het scherm te hebben, en
zonder dat een demo iets in je eigen rij verandert.

De voortgang is verzonnen en niet gekopieerd. Dat is met opzet: een kopie van een echte rij
zet de voortgang van een echt mens in een demo-account, en het geeft ook geen zekerheid dat
elk tabblad iets te zien heeft. Verzonnen data laat zich juist zo zetten dat élk onderdeel
gevuld is -- woorden in alle stadia, rijtjes, stamtijden, structuurwoorden, klankwetten,
contracties, Hebreeuws en een reeks dagen achter elkaar.

Draaien:  py gereedschap/maak_demo.py             kijken wat het zou worden
          py gereedschap/maak_demo.py --schrijf   echt naar de Sheet
"""
import json
import os
import random
import sys
from datetime import date, timedelta

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

import uitvoer

uitvoer.zet_utf8()

import grieks_motor as motor
import grieks_opslag as opslag

GEBRUIKER = "Demo_app"          # naam 'Demo', codewoord 'app'
random.seed(20260821)           # zelfde uitkomst bij elke keer, dus na te rekenen

# Hoe de woorden verdeeld staan. De app kent vier fasen (nieuw, in training, beheerst,
# vast), en een demo moet ze alle vier laten zien -- anders lijkt de helft van de app leeg.
VERDELING = [
    (0.30, 20, 26),      # 30% vast: streak 20-26, dus 'beheerst' met marge
    (0.25, 16, 19),      # 25% net beheerst; hier zit ook de 'lekkende emmer' in
    (0.25, 5, 15),       # 25% in training
    (0.10, 1, 4),        # 10% net begonnen
    (0.10, 0, 0),        # 10% nog niet aangeraakt
]


def dagen_terug(n):
    return (date.today() - timedelta(days=n)).isoformat()


def verdeel(aantal):
    """Per woord een streak, volgens VERDELING."""
    uit = []
    for deel, laag, hoog in VERDELING:
        for _ in range(int(aantal * deel)):
            uit.append(random.randint(laag, hoog))
    while len(uit) < aantal:
        uit.append(random.randint(5, 15))
    random.shuffle(uit)
    return uit[:aantal]


def woordscores():
    """vocab_stats: per Grieks woord de streak, goed/fout en wanneer je het deed."""
    woorden = motor.laad_vocab_db()
    uit = {}
    for w, streak in zip(woorden, verdeel(len(woorden))):
        if not streak:
            continue
        goed = streak + random.randint(0, 4)
        fout = random.randint(0, 3) if streak < 16 else random.randint(0, 1)
        uit[w["grieks"]] = {"streak": streak, "g": goed, "f": fout,
                            "laatst_geoefend": dagen_terug(random.randint(0, 21))}
        if fout:
            uit[w["grieks"]]["lf"] = dagen_terug(random.randint(0, 40))
    return uit


def cellen(sleutels, deel_vast=0.55):
    """Een deel van deze sleutels vast, een deel onderweg, de rest nog niet.

    De sleutels moeten precies zijn zoals de app ze opzoekt, anders staat er straks een rij
    voortgang die nergens bij hoort:
        stamtijden        '<praesens>_<tijd>'
        rijtjes           het veld 'id' van de cel
        structuurwoorden  het Griekse woord
    """
    uit = {}
    for sleutel in sleutels:
        r = random.random()
        if r < deel_vast:
            streak = random.randint(6, 14)
        elif r < 0.85:
            streak = random.randint(1, 5)
        else:
            continue
        uit[sleutel] = {"streak": streak, "g": streak + random.randint(0, 3),
                        "f": random.randint(0, 2)}
    return uit


def in_levels(groepen, deel_af=0.4):
    """Voortgang die per level oploopt: de eerste levels helemaal af, dan halverwege, dan niets.

    Stamtijden en de rijtjes rekenen hun percentage op afgeronde levels: een level is af als
    élke vorm erin op streak 5 of hoger staat. Cellen willekeurig verdelen geeft dan 0% —
    je hebt overal wat, maar niets helemaal. Zo werkt leren ook niet: je gaat level voor
    level. Dus de eerste 40% af, de 25% daarna half, en de rest nog niet aangeraakt."""
    uit = {}
    n_af = int(len(groepen) * deel_af)
    n_half = int(len(groepen) * 0.25)
    for i, sleutels in enumerate(groepen):
        for sleutel in sleutels:
            if i < n_af:
                # Ruim boven de zestien: de stamtijden rekenen 'af' vanaf streak 5, maar de
                # rijtjes rekenen 'beheerst' pas vanaf 16. Met 7 tot 16 stond Actief
                # Beheersen op 4% terwijl er overal voortgang stond.
                streak = random.randint(16, 22)
            elif i < n_af + n_half:
                if random.random() < 0.5:
                    continue
                streak = random.randint(1, 6)
            else:
                continue
            uit[sleutel] = {"streak": streak, "g": streak + random.randint(0, 3),
                            "f": random.randint(0, 2)}
    return uit


def stam_groepen():
    """Per werkwoord de sleutels van zijn stamtijden: '<praesens>_<tijd>'. Eén groep is één
    level in de app, en de volgorde is die van de levels zelf."""
    levels = motor.bouw_stam_levels(motor.laad_stamtijden_db() or [])
    return [[f"{lv['verb']['praesens']}_{tijd}"
             for tijd in motor._stam_vormen(lv["verb"])] for lv in levels]


def actief_groepen():
    """Per paradigma de id's van zijn cellen. Eén paradigma is één level."""
    uit = []
    for niveau in (motor.laad_actief_db() or {}).values():
        for categorie in niveau.values():
            for paradigma in categorie.values():
                ids = [c["id"] for c in paradigma if c.get("id")]
                if ids:
                    uit.append(ids)
    return uit


def dagreeks(dagen=24):
    """(dag_stats, dagdoel) — het oefenritme van de afgelopen weken.

    Twee verschillende vormen, en dat is makkelijk mis te hebben:
        dag_stats[dag]        één geheel getal: hoeveel beurten je die dag deed
        dagdoel['log'][dag]   een dict per onderdeel: wat je die dag goed had

    De eerste keer had ik in dag_stats ook een dict gezet, en dan valt de app om op
    int(...) — precies het soort fout dat je alleen ziet door het te draaien."""
    tellers, log = {}, {}
    for n in range(dagen):
        if n and random.random() < 0.18:
            continue                       # een enkele dag overgeslagen; anders te perfect
        dag = dagen_terug(n)
        per_onderdeel = {
            "woorden": random.randint(6, 26), "woorden_uniek": random.randint(5, 20),
            "actief": random.randint(0, 9), "stam": random.randint(0, 8),
            "struct": random.randint(0, 6), "verzen": random.randint(0, 3),
            "klank": random.randint(0, 7), "hebreeuws": random.randint(0, 14),
        }
        log[dag] = per_onderdeel
        tellers[dag] = sum(v for k, v in per_onderdeel.items() if k != "woorden_uniek")
    return tellers, log


def hebreeuwse_scores():
    """hebr_stats: de Hebreeuwse woorden én de cellen van de rijtjes, in één dict."""
    import hebreeuws
    uit = {}
    woorden = hebreeuws.laad_woorden()
    for w, streak in zip(woorden, verdeel(len(woorden))):
        if not streak:
            continue
        uit[hebreeuws.sleutel(w)] = {"streak": streak, "g": streak + random.randint(0, 3),
                                     "f": random.randint(0, 2)}
    for niveaus in (hebreeuws.laad_rijtjes() or {}).values():
        for categorien in niveaus.values():
            for cellen_ in categorien.values():
                for c in cellen_:
                    if random.random() < 0.6:
                        s = random.randint(3, 12)
                        uit[c["id"]] = {"streak": s, "g": s + 1, "f": random.randint(0, 2)}
    return uit


def bouw():
    struct_db = motor.laad_structuurwoorden_db()
    klassen = list(motor._SAMENSMELT_KLASSEN)
    contr = ["σ-samensmelting (fut./aor.)", "Verba contracta (klinkers)",
             "Augment (verleden tijd)"]

    dag_tellers, dag_log = dagreeks()
    stats = {
        "vocab_stats": woordscores(),
        "dag_stats": dag_tellers,
        "stam_stats": in_levels(stam_groepen(), deel_af=0.35),
        "actief_stats": in_levels(actief_groepen(), deel_af=0.45),
        "struct_stats": cellen([w["grieks"] for w in (struct_db or []) if w.get("grieks")],
                               deel_vast=0.6),
        "klank_stats": {k: {"streak": random.randint(2, 11), "g": random.randint(4, 20),
                            "f": random.randint(1, 5)} for k in klassen},
        "gram_stats": {f"contr::{s}": {"streak": random.randint(3, 11),
                                       "g": random.randint(6, 24),
                                       "f": random.randint(1, 4)} for s in contr},
        "hebr_stats": hebreeuwse_scores(),
        "prod_stats": {}, "verwar_stats": {}, "ontleed_stats": {},
        "badges": {"_demo": "1"},
        "dagdoel": {"log": dag_log},
        # Alle tabbladen open: een demo moet alles kunnen laten zien.
        "ui_prefs": {"verborgen_tabs": [], "geavanceerd": True},
    }
    return stats


def main():
    stats = bouw()
    print(f"demo-gebruiker: {GEBRUIKER}  (naam 'Demo', codewoord 'app')")
    for sleutel, _teller in opslag.SPECS:
        n = len(stats.get(sleutel) or {})
        print(f"  {sleutel:16s} {n:6d} regels")
    v = stats["vocab_stats"]
    vast = sum(1 for e in v.values() if e["streak"] >= 16)
    print()
    print(f"  {len(v)} Griekse woorden geoefend, {vast} daarvan beheerst")
    print(f"  {len(stats['hebr_stats'])} Hebreeuwse regels")
    print(f"  {len(stats['dag_stats'])} dagen met werk erin")

    if "--schrijf" not in sys.argv:
        print()
        print("Niets weggeschreven. Draai met --schrijf om het echt te doen.")
        return
    print()
    print("wegschrijven naar de Sheet…")
    # samenvoegen=False: dit is een nieuwe rij, er is niets om mee te voegen, en zo raakt
    # het niets aan wat er al staat.
    goed = opslag.bewaar(GEBRUIKER, stats, samenvoegen=False)
    print("gelukt" if goed else "MISLUKT — de Sheet gaf een fout")
    if goed:
        terug = opslag.huidige_stats(GEBRUIKER)
        print(f"nagelezen uit de Sheet: {len(terug.get('vocab_stats') or {})} Griekse "
              f"woorden, {len(terug.get('hebr_stats') or {})} Hebreeuwse regels")


if __name__ == "__main__":
    main()
