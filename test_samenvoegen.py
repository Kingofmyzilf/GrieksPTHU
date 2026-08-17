# -*- coding: utf-8 -*-
"""Controleert dat de Streamlit-app en de NiceGUI-app elkaars voortgang niet wissen.

Beide apps schrijven de héle rij naar hetzelfde tabblad. Zonder samenvoegen wist wie
het laatst opslaat alles wat de ander deed sinds diens inloggen. Deze test bootst dat
na met gewone dicts — er gaat geen netwerk aan te pas.

Draaien:  py test_samenvoegen.py
"""
import grieks_opslag as opslag

geslaagd, gefaald = 0, 0


def controleer(wat, gekregen, verwacht):
    global geslaagd, gefaald
    if gekregen == verwacht:
        geslaagd += 1
        print(f"  ok   {wat}")
    else:
        gefaald += 1
        print(f"  FOUT {wat}\n       gekregen : {gekregen}\n       verwacht : {verwacht}")


def leeg():
    return {s: {} for s, _ in opslag.SPECS}


print("Woorden: wie het meest geoefend heeft, wint per woord")
# Streamlit logde om 10:00 in en kent λόγος met 2 pogingen. Ondertussen oefende
# NiceGUI door tot 5 pogingen. Streamlit slaat om 10:25 op met zijn oude beeld.
in_sheet = {**leeg(), "vocab_stats": {
    "λόγος": {"streak": 5, "g": 5, "f": 0, "laatst_geoefend": "2026-08-17"},
    "θεός": {"streak": 3, "g": 3, "f": 0},
}}
streamlit_oud = {**leeg(), "vocab_stats": {
    "λόγος": {"streak": 2, "g": 2, "f": 0, "laatst_geoefend": "2026-08-16"},
    "θεός": {"streak": 3, "g": 3, "f": 0},
}}
uit = opslag.samenvoeg_stats(in_sheet, streamlit_oud)
controleer("nieuwere streak blijft staan", uit["vocab_stats"]["λόγος"]["streak"], 5)
controleer("ongewijzigd woord blijft ongewijzigd", uit["vocab_stats"]["θεός"]["g"], 3)

# En andersom: wie wél verder is, schrijft door.
in_sheet2 = {**leeg(), "vocab_stats": {"λόγος": {"streak": 2, "g": 2, "f": 0}}}
nieuw = {**leeg(), "vocab_stats": {"λόγος": {"streak": 6, "g": 5, "f": 1}}}
uit = opslag.samenvoeg_stats(in_sheet2, nieuw)
controleer("mijn nieuwere versie wint", uit["vocab_stats"]["λόγος"]["streak"], 6)

# Een woord dat de ander toevoegde en ik niet ken, blijft bestaan.
in_sheet3 = {**leeg(), "vocab_stats": {"ἀγάπη": {"streak": 1, "g": 1, "f": 0}}}
uit = opslag.samenvoeg_stats(in_sheet3, {**leeg(), "vocab_stats": {}})
controleer("woord van de andere app blijft staan", uit["vocab_stats"].get("ἀγάπη", {}).get("g"), 1)

print("\nDe andere teldicts volgen dezelfde regel")
for naam in ("stam_stats", "struct_stats", "actief_stats", "ontleed_stats"):
    uit = opslag.samenvoeg_stats(
        {**leeg(), naam: {"x": {"g": 9, "f": 1, "streak": 9}}},
        {**leeg(), naam: {"x": {"g": 1, "f": 0, "streak": 1}}})
    controleer(f"{naam}: meeste pogingen wint", uit[naam]["x"]["streak"], 9)

print("\nOefenritme: per dag het hoogste aantal")
uit = opslag.samenvoeg_stats(
    {**leeg(), "dag_stats": {"2026-08-17": 30, "2026-08-16": 12}},
    {**leeg(), "dag_stats": {"2026-08-17": 8, "2026-08-15": 4}})
controleer("hoogste dagteller wint", uit["dag_stats"]["2026-08-17"], 30)
controleer("dag van de ander blijft", uit["dag_stats"]["2026-08-16"], 12)
controleer("mijn eigen dag komt erbij", uit["dag_stats"]["2026-08-15"], 4)

print("\nVerwarparen: de laatst bijgewerkte versie wint (n kan ook dalen)")
uit = opslag.samenvoeg_stats(
    {**leeg(), "verwar_stats": {"λόγος": {"νόμος": {"n": 3, "laatst": "2026-08-16"}}}},
    {**leeg(), "verwar_stats": {"λόγος": {"νόμος": {"n": 1, "laatst": "2026-08-17"}}}})
controleer("gedempte verwarring wordt niet teruggedraaid",
           uit["verwar_stats"]["λόγος"]["νόμος"]["n"], 1)
uit = opslag.samenvoeg_stats(
    {**leeg(), "verwar_stats": {"λόγος": {"νόμος": {"n": 4, "laatst": "2026-08-18"}}}},
    {**leeg(), "verwar_stats": {"λόγος": {"νόμος": {"n": 1, "laatst": "2026-08-17"}}}})
controleer("nieuwere versie van de ander blijft",
           uit["verwar_stats"]["λόγος"]["νόμος"]["n"], 4)

print("\nInstellingen: de twee apps gebruiken eigen sleutels en botsen dus niet")
uit = opslag.samenvoeg_stats(
    {**leeg(), "ui_prefs": {"modus": "2. MC", "lessen": [1, 2]}},
    {**leeg(), "ui_prefs": {"ng_keuze": "Leerpad (levels)", "ng_aantal": 12}})
controleer("Streamlit-instelling blijft", uit["ui_prefs"]["modus"], "2. MC")
controleer("NiceGUI-instelling komt erbij", uit["ui_prefs"]["ng_aantal"], 12)

print("\nDagdoel: instelling van de nieuwste, log per dag het hoogste")
uit = opslag.samenvoeg_stats(
    {**leeg(), "dagdoel": {"config": {"woorden": 10, "klank": 5},
                           "log": {"2026-08-17": {"stam": 6, "woorden_uniek": 20}}}},
    {**leeg(), "dagdoel": {"config": {"woorden": 14},
                           "log": {"2026-08-17": {"stam": 2, "actief": 3}}}})
controleer("mijn nieuwe doel wint", uit["dagdoel"]["config"]["woorden"], 14)
controleer("doel dat alleen Streamlit kent blijft", uit["dagdoel"]["config"]["klank"], 5)
controleer("hoogste dagteller wint", uit["dagdoel"]["log"]["2026-08-17"]["stam"], 6)
controleer("teller die alleen ik heb komt erbij",
           uit["dagdoel"]["log"]["2026-08-17"]["actief"], 3)

print("\nEen lege Sheet (eerste keer opslaan) verandert niets aan mijn voortgang")
mijn = {**leeg(), "vocab_stats": {"λόγος": {"streak": 4, "g": 4, "f": 0}}}
controleer("niets in de Sheet", opslag.samenvoeg_stats(None, mijn)["vocab_stats"],
           mijn["vocab_stats"])

print("\nDe hele rondgang: schrijven, teruglezen, samenvoegen")
# Zo gaat het echt: NiceGUI schrijft een rij, Streamlit leest die terug en voegt zijn
# eigen (oudere) beeld erbij voordat het schrijft.
van_nicegui = {**leeg(),
               "vocab_stats": {"λόγος": {"streak": 7, "g": 6, "f": 1,
                                         "laatst_geoefend": "2026-08-17", "lf": "2026-08-16"}},
               "dag_stats": {"2026-08-17": 25},
               "ui_prefs": {"ng_keuze": "Leerpad (levels)"}}
rij = opslag.bouw_rij("Bob_zomer2026", van_nicegui)
terug = opslag.lees_rij(rij)
controleer("rij overleeft schrijven en teruglezen",
           terug["vocab_stats"]["λόγος"]["streak"], 7)
controleer("laatst_fout blijft bewaard", terug["vocab_stats"]["λόγος"]["lf"], "2026-08-16")

streamlit_oud = {**leeg(),
                 "vocab_stats": {"λόγος": {"streak": 3, "g": 3, "f": 0}},
                 "dag_stats": {"2026-08-17": 9},
                 "ui_prefs": {"modus": "2. MC"}}
samen = opslag.samenvoeg_stats(terug, streamlit_oud)
controleer("NiceGUI-streak overleeft de opslag van Streamlit",
           samen["vocab_stats"]["λόγος"]["streak"], 7)
controleer("dagteller wordt niet verlaagd", samen["dag_stats"]["2026-08-17"], 25)
controleer("beide instellingen blijven",
           (samen["ui_prefs"].get("ng_keuze"), samen["ui_prefs"].get("modus")),
           ("Leerpad (levels)", "2. MC"))

print("\nLege cellen uit Google (NaN)")
nan = float("nan")
# Een oude, ongechunkte kolom die leeg is: gewoon niets, geen reden tot paniek.
rij_met_nan = dict(rij)
rij_met_nan["gram_stats"] = nan
gelezen = opslag.lees_rij(rij_met_nan)
controleer("lege ongechunkte cel geeft een lege dict", gelezen["gram_stats"], {})
controleer("de rest van de rij blijft leesbaar",
           gelezen["vocab_stats"]["λόγος"]["streak"], 7)

# Maar een teller die stukken belooft die er niet zijn, is een stukke rij. Daar moet
# hij op stuiten in plaats van stilletjes een lege voortgang terug te geven.
kapot = dict(rij)
kapot["vocab_stats_0"] = nan
try:
    opslag.lees_rij(kapot)
    controleer("stukke rij wordt geweigerd", "gelezen zonder klacht", "OpslagFout")
except opslag.OpslagFout:
    controleer("stukke rij wordt geweigerd", "OpslagFout", "OpslagFout")

print(f"\n{geslaagd} geslaagd, {gefaald} gefaald")
raise SystemExit(1 if gefaald else 0)
