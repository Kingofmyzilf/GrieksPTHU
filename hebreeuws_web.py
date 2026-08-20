# -*- coding: utf-8 -*-
"""Het Tenach-tabblad voor de Streamlit-app: Hebreeuws lezen op een breed scherm.

Waarom dit hier staat en niet alleen in de mobiele app: de Tenach lezen is precies waar een
breed scherm helpt. Op een telefoon tik je woord voor woord aan; hier past een hele tabel
met alle woorden van een vers ónder de tekst, en dat leest veel sneller.

Het oefenen zelf blijft in de mobiele app — daar zit de woordenschat, de rijtjes en de
voortgang. Dit tabblad is om te lézen, en om te zien welke woorden je nog mist.

Los bestand en niet in overhoring_web.py, om twee redenen. Die module wordt door
gereedschap/bouw_motor.py omgezet naar grieks_motor.py, en alles wat Streamlit aanroept
moet daar juist buiten blijven. En zo blijft het Hebreeuws bij elkaar: staat hebreeuws.py
of de map tenach/ er niet, dan verschijnt het tabblad simpelweg niet.
"""
import re

import pandas as pd
import streamlit as st

import hebreeuws

# Zelfde kleuren als de rest van de app (.streamlit/config.toml).
ZACHT, MERK, FOUT = "#9aa4ae", "#33ccff", "#ff6b81"

OPMAAK = """
<style>
  .hebtekst { direction:rtl; unicode-bidi:isolate; text-align:right;
              font-family:'Noto Serif Hebrew','David','Times New Roman',serif;
              font-size:27px; line-height:2.15; }
  .hebnr    { color:#9aa4ae; font-size:12px; vertical-align:super; }
  .hebnog   { border-bottom:2px solid #ff6b81; }
  .hebaffix { color:#33ccff; }
</style>
"""


def beschikbaar():
    """Is de Hebreeuwse tekst er? Zo niet, dan hoort het tabblad er niet te staan."""
    try:
        return bool(hebreeuws.tenach_index())
    except Exception:                                            # noqa: BLE001
        return False


def korte_betekenis(w):
    """De betekenis van een woord uit de cursuslijst, kort maar leesbaar.

    Kleine versie van heb_betekenis() uit de mobiele app: de eerste groep die echt
    betekenissen heeft, met de uitleg tussen haken en de gidstekens eruit, en de stamcodes
    vooraan eraf. Hier staat hij in een tabel en niet op een keuzeknop, dus hij mag langer
    zijn dan daar."""
    codes = {"i", "ii", "iii", "G", "N", "D", "Dp", "H", "Hp", "Ht", "tD", "R", "Rp", "en"}
    tekst = re.sub(r"^\((?:v|m)\.?\)\s*", "", str(w.get("nederlands", ""))).strip()
    for segment in tekst.split(";"):
        segment = re.sub(r"\[[^\]]*\]", " ", segment)
        segment = re.sub(r"»[^«]*«", " ", segment)
        # Woord voor woord de codes vooraan eraf. Blijft er niets over, dan stond er in dit
        # segment alleen uitleg en geen betekenis — bij אֵת is dat 'i [geeft lijdend
        # voorwerp aan]', en dan hoort de volgende groep het antwoord te leveren.
        delen = re.sub(r"\s{2,}", " ", segment).strip(" ,;.:").split(" ")
        while delen and delen[0].strip(".") in codes:
            delen.pop(0)
        schoon = " ".join(delen).strip(" ,;.:")
        if schoon:
            return schoon[:96]
    return tekst[:96]


def _woorden_op_strong():
    """Strong-nummer -> het woord uit de cursuslijst, met jouw voortgang eroverheen.

    De voortgang staat in hebr_stats, dezelfde kolom die de mobiele app vult. Deze app
    schrijft daar niets in; hij leest hem alleen om te laten zien wat je al hebt gehad."""
    scores = st.session_state.get("hebr_stats") or {}
    uit = {}
    for w in hebreeuws.laad_woorden():
        s = str(w.get("strong") or "")
        if not s or s in uit:
            continue
        e = scores.get(hebreeuws.sleutel(w)) or {}
        uit[s] = dict(w, streak=int(e.get("streak", 0) or 0),
                      gehad=bool(int(e.get("g", 0) or 0) or int(e.get("f", 0) or 0)
                                 or int(e.get("streak", 0) or 0)))
    return uit


def _affixen(parsing):
    """Wat de voor- en achtervoegsels van deze vorm betekenen, als één regel."""
    voor, _kern, achter = hebreeuws._codes(parsing)
    delen = [hebreeuws.VOORVOEGSEL_NL[c] for c in voor]
    if achter:
        delen.append(hebreeuws.ACHTERVOEGSEL_NL[achter])
    return " + ".join(delen)


def tab():
    """Het tabblad. Aanroepen binnen 'with menu[i]:'."""
    st.header("📜 Tenach")
    boeken = hebreeuws.tenach_index()
    if not boeken:
        st.info("De Hebreeuwse tekst staat niet in deze installatie.")
        return
    st.markdown(OPMAAK, unsafe_allow_html=True)
    op_naam = {b["nl"]: b for b in boeken}
    per_strong = _woorden_op_strong()

    kol1, kol2, kol3 = st.columns([2, 1, 2])
    with kol1:
        boek_naam = st.selectbox("Boek", list(op_naam), key="tenach_boek")
    boek = op_naam[boek_naam]
    with kol2:
        hoofdstuk = st.number_input("Hoofdstuk", min_value=1,
                                    max_value=max(1, int(boek["hoofdstukken"])),
                                    value=1, step=1, key="tenach_hfst")
    verzen = [v for v in hebreeuws.laad_tenach_boek(boek["bestand"])
              if v["v"].split(":")[0] == str(int(hoofdstuk))]
    if not verzen:
        st.info("Dat hoofdstuk staat niet in dit boek.")
        return
    with kol3:
        keuzes = ["Heel hoofdstuk"] + [f"vers {v['v'].split(':')[-1]}" for v in verzen]
        keuze = st.selectbox(f"{len(verzen)} verzen", keuzes, key="tenach_vers")
    gekozen = (verzen if keuze == "Heel hoofdstuk"
               else [v for v in verzen if v["v"].split(":")[-1] == keuze.split()[-1]])

    # De tekst zelf. Wat je nog niet hebt geoefend krijgt een rood streepje: zo zie je in
    # één oogopslag waar dit hoofdstuk voor jóu spannend wordt.
    regels = []
    for v in gekozen:
        stukken = [f"<span class='hebnr'>{v['v'].split(':')[-1]}</span>"]
        for vorm, strong, _parsing in v["w"]:
            w = per_strong.get(strong)
            klasse = "" if (w and w["gehad"]) else " class='hebnog'"
            stukken.append(f"<span{klasse}>{vorm}</span>")
        regels.append(" ".join(stukken))
    st.markdown(f"<div class='hebtekst'>{' '.join(regels)}</div>", unsafe_allow_html=True)

    rijen = []
    for v in gekozen:
        for vorm, strong, parsing in v["w"]:
            w = per_strong.get(strong)
            voor, kern, achter = hebreeuws.splits_affixen(vorm, parsing)
            rijen.append({
                "vers": v["v"],
                "vorm": vorm,
                "stam": kern if (voor or achter) else "",
                "betekenis": korte_betekenis(w) if w else "— niet in de cursuslijst",
                "voor/achter": _affixen(parsing),
                "ontleding": hebreeuws_ontleding(parsing),
                "streak": int(w["streak"]) if w else 0,
            })

    nog = [r for r in rijen
           if r["streak"] == 0 and not r["betekenis"].startswith("—")]
    buiten = [r for r in rijen if r["betekenis"].startswith("—")]
    st.caption(f"{len(rijen)} woorden · rood onderstreept = nog niet geoefend · "
               f"{len(nog)} staan in je lijst maar had je nog niet · "
               f"{len(buiten)} staan niet in de cursuslijst")
    st.dataframe(
        pd.DataFrame(rijen), use_container_width=True, hide_index=True,
        column_config={
            "vers": st.column_config.TextColumn("Vers", width="small"),
            "vorm": st.column_config.TextColumn("Vorm", width="small"),
            "stam": st.column_config.TextColumn("Stam", width="small"),
            "betekenis": st.column_config.TextColumn("Betekenis", width="large"),
            "voor/achter": st.column_config.TextColumn("Voor/achtervoegsel",
                                                       width="medium"),
            "ontleding": st.column_config.TextColumn("Ontleding", width="medium"),
            "streak": st.column_config.NumberColumn("Streak", width="small"),
        })
    st.caption("Oefenen doe je in de snelle app: daar kun je een hoofdstuk kiezen en de "
               "woorden die je nog mist vooraan in je woordenschat zetten.")


# De ontleedcodes in gewoon Nederlands. Dezelfde tabellen als in de mobiele app; hier
# nagemaakt zodat dit bestand op zichzelf staat en niets uit de NiceGUI-schil hoeft.
_LOS = {"Conj-w": "en", "Art": "de/het", "Prep-b": "in/met", "Prep-k": "als",
        "Prep-l": "voor/naar", "Prep-m": "uit/van", "Prep": "voorzetsel",
        "Interrog": "vraagwoord", "Adv": "bijwoord", "Conj": "voegwoord",
        "DirObjM": "lijdend voorwerp", "Adv-NegPrt": "niet",
        "N-ms": "znw m ev", "N-mp": "znw m mv", "N-fs": "znw v ev", "N-fp": "znw v mv",
        "N-msc": "znw m ev verbonden", "N-mpc": "znw m mv verbonden",
        "N-fsc": "znw v ev verbonden", "N-fpc": "znw v mv verbonden",
        "N-proper-ms": "eigennaam", "N-proper-fs": "eigennaam",
        "Adj-ms": "bnw m ev", "Adj-fs": "bnw v ev", "Adj-mp": "bnw m mv",
        "Pro-3ms": "hij", "Pro-3fs": "zij", "Pro-2ms": "jij", "Pro-1cs": "ik",
        "Pro-3mp": "zij mv", "Pro-1cp": "wij", "Pro-2mp": "jullie",
        "Pro-r": "die/dat", "Pro-ms": "deze", "Pro-fs": "deze", "Pro-cp": "deze mv"}
_STAM = {"Qal": "Qal", "Nifal": "Nifal", "Piel": "Piel", "Pual": "Pual",
         "Hifil": "Hifil", "Hofal": "Hofal", "Hitpael": "Hitpael",
         "QalPassPrtcpl": "Qal passief deelwoord"}
_TIJD = {"Perf": "perfectum", "Imperf": "imperfectum", "ConsecImperf": "wajjiqtol",
         "ConjPerf": "wegatal", "Imp": "gebiedende wijs", "Inf": "infinitief",
         "InfAbs": "infinitivus absolutus", "InfCon": "infinitivus constructus",
         "Prtcpl": "deelwoord"}
_PERSOON = {"3ms": "3e m ev", "3fs": "3e v ev", "2ms": "2e m ev", "2fs": "2e v ev",
            "1cs": "1e ev", "3mp": "3e m mv", "3fp": "3e v mv", "3cp": "3e mv",
            "2mp": "2e m mv", "2fp": "2e v mv", "1cp": "1e mv",
            "ms": "m ev", "fs": "v ev", "mp": "m mv", "fp": "v mv"}


def _werkwoord(code):
    """'V-Qal-ConsecImperf-3ms' -> 'Qal wajjiqtol 3e m ev'."""
    if not code.startswith("V-"):
        return ""
    return " ".join(_STAM.get(s) or _TIJD.get(s) or _PERSOON.get(s) or s
                    for s in code[2:].split("-"))


def hebreeuws_ontleding(parsing):
    """De hele ontleedcode leesbaar. Wat we niet kennen blijft staan — dan zie je dat er
    iets is in plaats van dat het stilletjes verdwijnt."""
    if not parsing:
        return ""
    delen = []
    for stuk in str(parsing).split("|"):
        for code in stuk.split(","):
            code = code.strip()
            if code:
                delen.append(_LOS.get(code) or _werkwoord(code) or code)
    return " · ".join(d for d in delen if d)
