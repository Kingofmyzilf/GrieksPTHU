# -*- coding: utf-8 -*-
"""Controleert de scoreregels van het Hebreeuwse woorden-tabblad in Streamlit.

Deze proef bestaat om een reden. In de snelle app stond de streak-verhoging een tijd in de
verkeerde tak van een if: een fout antwoord gaf streak, een goed antwoord werd als fout
geteld. De code ernaast zag er goed uit, want beide takken bestonden nog en deden ieder iets
plausibels. Alleen door de score na te méten kwam het boven.

Dus wordt hier nagerekend wat er met de streak gebeurt:

    goed bij meerkeuze (streak 0)   ->  1     aanwijzen levert een punt
    fout bij meerkeuze (streak 0)   ->  0     onder de 16 kost een misser niets
    goed bij typen (streak 3)       ->  6     typen levert er drie
    fout bij streak 20              ->  18    wie het al beheerste valt twee terug
    fout bij streak 10              ->  10

Streamlit wordt daarvoor nagemaakt: het tabblad wordt aangeroepen met een knop die
'ingedrukt' is. Dat is omslachtiger dan een gewone unittest, maar het toetst de echte
functie in plaats van een kopie van de regels.

Draaien:  py gereedschap/test_woordtab.py
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uitvoer

uitvoer.zet_utf8()

uitvoer = []
knoppen = {}          # welke knop 'ingedrukt' moet zijn


class NepKolom:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def button(self, label, **k):
        uitvoer.append(("button", label))
        return knoppen.get(k.get("key") or label, False)

    def form_submit_button(self, label, **k):
        uitvoer.append(("submit", label))
        return knoppen.get(label, False)

    def __getattr__(self, naam):
        def doe(*a, **k):
            uitvoer.append((naam, a[0] if a else ""))
            return None
        return doe


class NepVorm(NepKolom):
    def text_input(self, label, **k):
        uitvoer.append(("text_input", label))
        return knoppen.get("_getypt", "")


class Rerun(Exception):
    pass


class NepSt:
    session_state = {}

    def __getattr__(self, naam):
        def doe(*a, **k):
            uitvoer.append((naam, a[0] if a else ""))
            return None
        return doe

    def columns(self, spec, **k):
        n = spec if isinstance(spec, int) else len(spec)
        return [NepKolom() for _ in range(n)]

    def radio(self, label, opties, **k):
        opties = list(opties)
        uitvoer.append(("radio", f"{label} -> {opties}"))
        if k.get("index", 0) is None:
            return knoppen.get("_gekozen")
        return opties[0] if opties else None

    def selectbox(self, label, opties, **k):
        opties = list(opties)
        uitvoer.append(("selectbox", f"{label} -> {len(opties)} keuzes"))
        i = k.get("index", 0) or 0
        return opties[min(i, len(opties) - 1)] if opties else None

    def text_input(self, label, **k):
        uitvoer.append(("text_input", label))
        # Twee tekstvelden in dit tabblad: het antwoord bij het oefenen en het zoekveld in
        # de lijst. Ze door elkaar halen geeft een leeg antwoord en dus geen score -- dat
        # zag eruit als een fout in de app terwijl het er een in deze proef was.
        return knoppen.get("_getypt" if "etekenis" in label else "_zoek", "")

    def button(self, label, **k):
        uitvoer.append(("button", label))
        return knoppen.get(k.get("key") or label, False)

    def form(self, sleutel, **k):
        return NepVorm()

    def expander(self, label, **k):
        uitvoer.append(("expander", label))
        return NepKolom()

    def dataframe(self, df, **k):
        uitvoer.append(("dataframe", f"{len(df)} rijen"))

    def rerun(self):
        raise Rerun()

    def cache_data(self, *a, **k):
        def wrap(fn):
            return fn
        return wrap(a[0]) if a and callable(a[0]) else wrap


nep = NepSt()
sys.modules["streamlit"] = nep
import hebreeuws_web as hw
import hebreeuws as H

hw.st = nep


def ronde(stats, gekozen=None, getypt=None, knop=None):
    """Eén beurt: het tabblad tekenen met een 'ingedrukte' knop."""
    knoppen.clear()
    nep.session_state = {k: v for k, v in nep.session_state.items()}
    nep.session_state["hebr_stats"] = stats
    if gekozen is not None:
        knoppen["_gekozen"] = gekozen
    if getypt is not None:
        knoppen["_getypt"] = getypt
    if knop:
        knoppen[knop] = True
    uitvoer.clear()
    try:
        hw.tab_woorden(lambda *a: None, lambda *a: None, _gelijk)
    except Rerun:
        return True
    return False


def _gelijk(gegeven, doel):
    """Zoals check_betekenis, maar kort: gelijk of een deel van de opsomming."""
    g = str(gegeven or "").strip().lower()
    d = str(doel or "").lower()
    return bool(g) and (g == d.strip()
                        or any(g == deel.strip()
                               for deel in d.replace(";", ",").replace("/", ",").split(",")))


print("=== het tabblad tekenen ===")
stats = {}
ronde(stats)
for soort, inhoud in uitvoer[:14]:
    tekst = re.sub(r"<[^>]+>", " ", str(inhoud))
    print(f"  {soort:12s} {re.sub(r'[ ]+', ' ', tekst).strip()[:100]}")

# Welk woord staat er als eerste, en wat is het goede antwoord?
woorden = hw.woorden_met_scores(0)
blok = hw.woord_blokjes(woorden)[0]
eerste = blok["items"][0]
sleutel = H.sleutel(eerste)
goed_antwoord = H.heb_betekenis(eerste)
print()
print(f"eerste woord: {eerste['hebreeuws']} -> {goed_antwoord!r}  (streak "
      f"{eerste['streak']}, sleutel {sleutel!r})")

print()
print("=== wat doet de streak? ===")
fouten = []


def kijk(wat, gekregen, verwacht):
    if gekregen == verwacht:
        print(f"  ok   {wat}: {gekregen}")
    else:
        fouten.append(f"{wat}: kreeg {gekregen}, verwacht {verwacht}")
        print(f"  MIS  {wat}: kreeg {gekregen}, verwacht {verwacht}")


# 1. Nieuw woord (streak 0) -> meerkeuze. Goed antwoord = +1.
stats = {}
nep.session_state = {}
ronde(stats)                                   # eerst tekenen, dan de keuzes kennen
staat = next(v for k, v in nep.session_state.items() if str(k).startswith("hw_staat_"))
keuzes = staat["keuzes"]
assert goed_antwoord in keuzes, (goed_antwoord, keuzes)
ronde(stats, gekozen=goed_antwoord, knop=f"hw_chk_{sleutel}_0")
kijk("goed bij meerkeuze (streak 0)", stats.get(sleutel, {}).get("streak"), 1)

# 2. Fout antwoord op een nieuw woord: streak blijft 0.
stats = {}
nep.session_state = {}
ronde(stats)
staat = next(v for k, v in nep.session_state.items() if str(k).startswith("hw_staat_"))
fout = next(k for k in staat["keuzes"] if k != goed_antwoord)
ronde(stats, gekozen=fout, knop=f"hw_chk_{sleutel}_0")
kijk("fout bij meerkeuze (streak 0)", stats.get(sleutel, {}).get("streak"), 0)
kijk("  en als fout geteld", stats.get(sleutel, {}).get("f"), 1)

# 3. Typen (streak 3): goed = +3.
stats = {sleutel: {"g": 1, "f": 0, "streak": 3}}
nep.session_state = {}
ronde(stats, getypt=goed_antwoord.split(",")[0], knop="✓ Nakijken")
kijk("goed bij typen (streak 3)", stats[sleutel]["streak"], 6)

# 4. Typen, fout, streak 20: twee eraf.
stats = {sleutel: {"g": 9, "f": 0, "streak": 20}}
nep.session_state = {}
ronde(stats, getypt="volstrekt onjuist", knop="✓ Nakijken")
kijk("fout bij streak 20", stats[sleutel]["streak"], 18)

# 5. Typen, fout, streak 10: niets eraf.
stats = {sleutel: {"g": 4, "f": 0, "streak": 10}}
nep.session_state = {}
ronde(stats, getypt="volstrekt onjuist", knop="✓ Nakijken")
kijk("fout bij streak 10", stats[sleutel]["streak"], 10)

print()
print("=== dezelfde sleutel als de snelle app? ===")
kijk("sleutel is <nummer>:<medeklinkers>", bool(re.match(r"^\d+:[\u0590-\u05ff]+$", sleutel)),
     True)

print()
if fouten:
    sys.exit(f"{len(fouten)} mis")
print("GESLAAGD")
