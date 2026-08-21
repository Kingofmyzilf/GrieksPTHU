# -*- coding: utf-8 -*-
"""Het Tenach-tabblad voor de Streamlit-app: Hebreeuws lezen op een breed scherm.

Gebouwd als tegenhanger van 📝 Leesteksten, met dezelfde onderdelen:

    Grieks                              Hebreeuws
    ---------------------------------   ---------------------------------
    boek / hoofdstuk / meerdere verzen   idem
    Scavenger Hunt (zwakke woorden)      Zoek een vers met je zwakke woorden
    Autonome leestekst (100% bekend)     idem
    🎨 markeer naamvallen                 🎨 markeer woordsoorten
    🔗 markeer voegwoorden                🔗 markeer voor/achtervoegsels en uitgang
    ⚛️ markeer stamtijden                 ⚛️ markeer stamformaties
    zwevende tooltip per woord           idem
    vertaling_nl, met EN: als anker      idem, met de BSB uit de spreadsheet

Twee dingen zijn met opzet anders, omdat de talen verschillen.

De naamval is bij het Grieks wat een woord in de zin doet, en dat kleurt daar. Het
Hebreeuws heeft geen naamvallen; wat er die rol speelt zijn de voor- en achtervoegsels —
וְהָאָרֶץ is וְ + הָ + אָרֶץ — en dát is hier dus de kleuring die ertoe doet.

En het oefenen zit hier niet in. De Griekse leestekst heeft vier methodes (lezen,
meerkeuze, typen, ontleden); voor het Hebreeuws blijft dat in de snelle app, waar de
woordenschat en je voortgang staan. Dit tabblad is om te lézen.

De tooltip gebruikt .mobile-tooltip uit overhoring_web.py, dezelfde als bij het Grieks:
zichtbaar bij muis eroverheen, en op een telefoon bij aanraken (tabindex + :focus).
"""
import random
import re

import pandas as pd
import streamlit as st

import hebreeuws

# ---------------------------------------------------------------- kleuren
# Zelfde gedachte als _ONTLEED_KLEUR en _GRAM_KLEUR in de Griekse app: één vaste kleur per
# term, gelijke helderheid, weg van rood en groen (die betekenen 'fout' en 'goed') en weg
# van het merkcyaan. Anders dan bij het Grieks hangt deze reeks nergens aan vast.
WOORDSOORT_KLEUR = {
    "werkwoord": "#FF9BC4", "naamwoord": "#7FB3FF", "bijv. naamwoord": "#E8B44A",
    "voornaamwoord": "#B694FF", "voorzetsel": "#5ED3C0", "bijwoord": "#C7B7A3",
    "voegwoord": "#FFD700", "lidwoord": "#9AA4AE", "telwoord": "#8FD3E8",
    "eigennaam": "#D0D0D0",
}
STAM_KLEUR = {
    "Qal": "#E8EAED", "Nifal": "#8FD3E8", "Piel": "#FFB067", "Pual": "#FF9BC4",
    "Hifil": "#C4A6FF", "Hofal": "#9B86D9", "Hitpael": "#5ED3C0",
}
# De kleuren van de woorddelen staan in hebreeuws.KLEUREN, want de snelle app gebruikt
# dezelfde: een uitgang die daar amber is en hier roze maakt het kleuren waardeloos.

OPMAAK = """
<style>
  .hebtekst { direction:rtl; unicode-bidi:isolate; text-align:right;
              font-family:'Noto Serif Hebrew','David','Times New Roman',serif;
              font-size:30px; line-height:2.3; padding:14px; }
  .hebnr    { color:#9aa4ae; font-size:13px; vertical-align:super;
              font-family:system-ui,sans-serif; }
  .hebwoord { border-bottom:1px dotted #555; }
  /* Nog niet geoefend: een rode streep eronder, net als bij het Grieks.
     Let op de dubbele klasse in de selector. Met alleen '.hebnog' werkte dit niet: elk
     woord heeft óók .hebwoord, die staat hierboven met dezelfde specificiteit, en dan wint
     de laatste regel — dus overschreef de grijze stippellijn de rode streep en was er
     nooit iets onderstreept. Zo is het onafhankelijk van de volgorde. */
  .hebwoord.hebnog { border-bottom:2px solid #ff6b81; }
  /* De tooltip staat links-naar-rechts, ook boven Hebreeuwse tekst. */
  .hebtekst .tooltiptext { direction:ltr; text-align:left;
                           font-family:system-ui,sans-serif; font-size:15px; }
</style>
"""


def beschikbaar():
    """Is de Hebreeuwse tekst er? Zo niet, dan hoort het tabblad er niet te staan."""
    try:
        return bool(hebreeuws.tenach_index())
    except Exception:                                            # noqa: BLE001
        return False


# ---------------------------------------------------------------- ontleedcodes lezen
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


def ontleding(parsing):
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


def woordsoort(parsing):
    """De woordsoort van de kern, in gewoon Nederlands. Voor de kleuring."""
    _voor, kern, _achter = hebreeuws._codes(parsing)
    if not kern:
        return ""
    if kern.startswith("V-"):
        return "werkwoord"
    if kern.startswith("N-proper"):
        return "eigennaam"
    if kern.startswith("N-"):
        return "naamwoord"
    if kern.startswith("Adj"):
        return "bijv. naamwoord"
    if kern.startswith("Pro"):
        return "voornaamwoord"
    if kern.startswith("Prep"):
        return "voorzetsel"
    if kern.startswith("Adv"):
        return "bijwoord"
    if kern.startswith("Conj"):
        return "voegwoord"
    if kern.startswith("Art"):
        return "lidwoord"
    if kern.startswith("Number"):
        return "telwoord"
    return ""


def stamformatie(parsing):
    """Qal, Nifal, Piel … van een werkwoordsvorm, of leeg."""
    _voor, kern, _achter = hebreeuws._codes(parsing)
    if not kern.startswith("V-"):
        return ""
    for stuk in kern.split("-"):
        if stuk in STAM_KLEUR:
            return stuk
    return ""


def korte_betekenis(w):
    """De betekenis van een woord uit de cursuslijst, kort maar leesbaar.

    Kleine versie van heb_betekenis() uit de snelle app: de eerste groep die echt
    betekenissen heeft, met de uitleg tussen haken en de gidstekens eruit, en de stamcodes
    vooraan eraf. Blijft er in een groep niets over, dan stond daar alleen uitleg — bij אֵת
    is dat 'i [geeft lijdend voorwerp aan]' — en levert de volgende groep het antwoord."""
    codes = {"i", "ii", "iii", "G", "N", "D", "Dp", "H", "Hp", "Ht", "tD", "R", "Rp", "en"}
    tekst = re.sub(r"^\((?:v|m)\.?\)\s*", "", str(w.get("nederlands", ""))).strip()
    for segment in tekst.split(";"):
        segment = re.sub(r"\[[^\]]*\]", " ", segment)
        segment = re.sub(r"»[^«]*«", " ", segment)
        delen = re.sub(r"\s{2,}", " ", segment).strip(" ,;.:").split(" ")
        while delen and delen[0].strip(".") in codes:
            delen.pop(0)
        schoon = " ".join(delen).strip(" ,;.:")
        if schoon:
            return schoon[:96]
    return tekst[:96]


def _affixen_kort(parsing, vorm=""):
    """Wat elk gekleurd woorddeel betekent, als één regel.

    Alleen wat er ook echt gekleurd staat; anders staat er 'mannelijk meervoud' bij een
    woord waar niets is aangewezen. Daarvoor is de vorm nodig."""
    if not vorm:
        voor, _kern, _achter = hebreeuws._codes(parsing)
        return " · ".join(f"{hebreeuws.VOORVOEGSEL_LETTER[c]} = "
                          f"{hebreeuws.VOORVOEGSEL_NL[c]}" for c in voor)
    return " · ".join(f"{tekst} = {uitleg}"
                      for tekst, _soort, uitleg in hebreeuws.uitleg_stukken(vorm, parsing))


@st.cache_data(show_spinner=False)
def _lijst_op_strong():
    """Strong-nummer -> woord uit de cursuslijst. Gecached: dit verandert niet."""
    uit = {}
    for w in hebreeuws.laad_woorden():
        s = str(w.get("strong") or "")
        if s and s not in uit:
            uit[s] = w
    return uit


def _voortgang():
    """Strong-nummer -> (streak, gehad). Uit hebr_stats, dezelfde kolom die de snelle app
    vult. Deze app schrijft daar niets in; hij leest alleen."""
    scores = st.session_state.get("hebr_stats") or {}
    uit = {}
    for w in hebreeuws.laad_woorden():
        s = str(w.get("strong") or "")
        if not s:
            continue
        e = scores.get(hebreeuws.sleutel(w)) or {}
        streak = int(e.get("streak", 0) or 0)
        gehad = bool(streak or int(e.get("g", 0) or 0) or int(e.get("f", 0) or 0))
        # Eén Strong kan bij twee lijstwoorden horen; de hoogste stand wint.
        oud = uit.get(s)
        if oud is None or streak > oud[0]:
            uit[s] = (streak, gehad or (oud[1] if oud else False))
    return uit


def legenda(kleuren, kop):
    """Eén legenda voor alle plekken, opgebouwd uit de kleurtabel zelf zodat kleur en
    legenda niet uit elkaar kunnen lopen. Zelfde aanpak als naamval_legenda() bij Grieks."""
    sp = " · ".join(f"<span style='color:{k}'>{n}</span>" for n, k in kleuren.items())
    return f"<div style='font-size:14px; margin-bottom:4px; opacity:.9'>{kop}: {sp}</div>"


def _woord_html(wv, lijst, stand, opties):
    """Eén woord als span, met tooltip en de gekozen markeringen.

    wv is een dict van hebreeuws.woorden_van(): vorm, strong, parsing, translit, engels."""
    vorm, strong, parsing = wv["vorm"], wv["strong"], wv["parsing"]
    w = lijst.get(strong)
    streak, gehad = stand.get(strong, (0, False))

    # ---- de tooltip: alles wat je over dit woord wil weten
    #
    # De eerste regel geeft altijd antwoord op 'wat betekent dit woord'. Uit je cursuslijst
    # als het erin staat, en anders uit de Engelse vertaling die in de spreadsheet naast
    # dít woord staat (de Berean Standard Bible, dezelfde bron als vertaling_bsb bij het
    # Grieks). Dat maakt het verschil tussen 410 woorden met een betekenis en 300.670.
    regels = []
    nederlands = korte_betekenis(w) if w else ""
    engels = wv["engels"]
    regels.append(f"{vorm} → {nederlands or engels or '?'}")
    if wv["translit"]:
        regels.append(f"klinkt als {wv['translit']}")
    # Het Engels alleen als anker erbij als het iets toevoegt: bij אֱלֹהִים stond er
    # anders 'God' en daaronder 'EN: God'.
    if nederlands and engels and engels.lower().strip(" .,;") not in nederlands.lower():
        regels.append(f"EN: {engels}")
    if w:
        if w.get("frequentie"):
            regels.append(f"{w['frequentie']}× in de Tenach · lijst {w.get('les', '?')}")
        regels.append(f"streak {streak}" if gehad else "nog niet geoefend")
    else:
        regels.append("Engels uit de BSB · niet in de cursuslijst" if engels
                      else "staat niet in de cursuslijst")
    ont = ontleding(parsing)
    if ont:
        regels.append(ont)
    aff = _affixen_kort(parsing, vorm)
    if aff:
        regels.append(aff)
    tooltip = "\n".join(regels).replace("'", "&#39;").replace('"', "&quot;")

    # ---- de kleur van het woord zelf
    stijl = "color:#888888;"
    if opties["woordsoort"]:
        soort = woordsoort(parsing)
        if soort in WOORDSOORT_KLEUR:
            stijl = f"color:{WOORDSOORT_KLEUR[soort]};"
    if opties["stammen"]:
        stam = stamformatie(parsing)
        if stam:
            stijl = f"color:{STAM_KLEUR[stam]};font-weight:600;"

    klassen = "mobile-tooltip hebwoord"
    if opties["nognietgehad"] and not gehad and w is not None:
        klassen += " hebnog"

    # ---- het woord in stukken kleuren. Wat niet aangevinkt staat krijgt de kleur van de
    #      stam, dus die van het woord zelf volgens de andere markeringen.
    aan = opties["delen"]
    if aan:
        binnen = "".join(
            f"<span style='color:{hebreeuws.KLEUREN[soort]}'>{tekst}</span>"
            if soort in aan else f"<span style='{stijl}'>{tekst}</span>"
            for tekst, soort in hebreeuws.ontleed_vorm(vorm, parsing))
    else:
        binnen = f"<span style='{stijl}'>{vorm}</span>"

    return (f"<span class='{klassen}' tabindex='0'>{binnen}"
            f"<span class='tooltiptext'>{tooltip}</span></span> ")


# ---------------------------------------------------------------- verzen zoeken
def _alle_verzen_van(boek):
    return hebreeuws.laad_tenach_boek(boek["bestand"])


def _zoek_bekend(boeken, stand, alles_bekend, hoeveel=1):
    """Verzen waarvan je (bijna) elk woord kent. De Hebreeuwse tegenhanger van de
    'Autonome Leestekst' bij het Grieks.

    Doorzoekt niet de hele Tenach maar een handvol boeken per keer: alle 39 inlezen kost
    honderd megabyte, en met een steekproef vind je binnen een seconde genoeg."""
    kandidaten = []
    for boek in random.sample(boeken, min(6, len(boeken))):
        for v in _alle_verzen_van(boek):
            if not 4 <= len(v["w"]) <= 16:
                continue
            # rij[1] is het Strong-nummer. Hier met de hand geïndexeerd en niet via
            # woorden_van(): dit loopt over tienduizenden verzen, en dan is het zonde om
            # voor elk woord een dict te bouwen dat je daarna weggooit.
            gehad = sum(1 for rij in v["w"] if stand.get(rij[1], (0, False))[1])
            deel = gehad / len(v["w"])
            if (alles_bekend and deel < 1.0) or (not alles_bekend and deel < 0.6):
                continue
            kandidaten.append((deel, boek, v))
    if not kandidaten:
        return []
    kandidaten.sort(key=lambda k: -k[0])
    return random.sample(kandidaten[:40], min(hoeveel, len(kandidaten[:40])))


def _zoek_zwak(boeken, stand, lijst, hoeveel=1):
    """Een vers dat veel woorden bevat die je nog niet vast hebt. De tegenhanger van de
    Scavenger Hunt: oefenen waar het pijn doet, maar wel in een vers dat je aankunt."""
    kandidaten = []
    for boek in random.sample(boeken, min(6, len(boeken))):
        for v in _alle_verzen_van(boek):
            if not 4 <= len(v["w"]) <= 16:
                continue
            in_lijst = [rij[1] for rij in v["w"] if rij[1] in lijst]
            if len(in_lijst) < 3:
                continue
            zwak = sum(1 for s in in_lijst if stand.get(s, (0, False))[0] < 5)
            if not zwak:
                continue
            kandidaten.append((zwak, boek, v))
    if not kandidaten:
        return []
    kandidaten.sort(key=lambda k: -k[0])
    return random.sample(kandidaten[:40], min(hoeveel, len(kandidaten[:40])))


# ---------------------------------------------------------------- het tabblad
def tab():
    """Het tabblad. Aanroepen binnen 'with menu[i]:'."""
    st.subheader("📜 Tenach — lezen met betekenis")
    boeken = hebreeuws.tenach_index()
    if not boeken:
        st.info("De Hebreeuwse tekst staat niet in deze installatie.")
        return
    st.markdown(OPMAAK, unsafe_allow_html=True)
    st.caption("Ga met je muis over een woord (of tik het aan) voor de betekenis, de "
               "ontleding en de voor- en achtervoegsels.")

    lijst = _lijst_op_strong()
    stand = _voortgang()
    op_naam = {b["nl"]: b for b in boeken}

    # ---- weergave-opties, zoals de vinkjes bij de Griekse leestekst
    v1, v2, v3 = st.columns(3)
    with v1:
        kleur_soort = st.checkbox("🎨 Markeer woordsoorten", key="heb_kl_soort")
    with v2:
        kleur_stam = st.checkbox("⚛️ Markeer stamformaties", key="heb_kl_stam")
    with v3:
        markeer_nieuw = st.checkbox("❗ Nog niet geoefend", value=True, key="heb_kl_nieuw")

    # Welke woorddelen je gekleurd wil zien. Een keuzelijst en niet vijf vinkjes: het zijn
    # er te veel voor een rij, en zo kun je ook één ding tegelijk aanzetten — alleen de
    # persoonsvoorvoegsels bijvoorbeeld, als je daar even op wil letten.
    delen = st.multiselect(
        "🔗 Welke woorddelen kleuren?", list(hebreeuws.KLEUREN),
        default=list(hebreeuws.KLEUREN),
        format_func=lambda s: hebreeuws.SOORTEN[s].split(" (")[0].split(":")[0],
        key="heb_kl_delen",
        help="De stam blijft altijd in de kleur van het woord staan. Zet een deel uit als "
             "je even alleen op iets anders wil letten.")
    opties = {"woordsoort": kleur_soort, "delen": set(delen),
              "stammen": kleur_stam, "nognietgehad": markeer_nieuw}

    st.write("---")
    modus = st.radio("Hoe wil je de tekst kiezen?",
                     ["Kies vers(zen)", "Zoek een vers met mijn zwakke woorden",
                      "🛡️ Alleen woorden die ik ken"],
                     horizontal=True, key="heb_leesmodus")

    gekozen, verwijzing = [], ""
    if modus == "Kies vers(zen)":
        k1, k2, k3 = st.columns([2, 1, 3])
        with k1:
            boek_naam = st.selectbox("Boek", list(op_naam), key="heb_boek")
        boek = op_naam[boek_naam]
        with k2:
            hoofdstuk = st.number_input("Hoofdstuk", min_value=1,
                                        max_value=max(1, int(boek["hoofdstukken"])),
                                        value=1, step=1, key="heb_hfst")
        verzen = [v for v in _alle_verzen_van(boek)
                  if v["v"].split(":")[0] == str(int(hoofdstuk))]
        if not verzen:
            st.info("Dat hoofdstuk staat niet in dit boek.")
            return
        nummers = [v["v"].split(":")[-1] for v in verzen]
        with k3:
            keuze = st.multiselect(f"Vers(zen) — {len(verzen)} beschikbaar", nummers,
                                   default=nummers[:1], key="heb_verzen")
        gekozen = [v for v in verzen if v["v"].split(":")[-1] in keuze] or verzen[:1]
        verwijzing = f"{boek_naam} {int(hoofdstuk)}:{', '.join(keuze) or nummers[0]}"

    elif modus == "Zoek een vers met mijn zwakke woorden":
        st.caption("Zoekt in een steekproef van zes boeken naar een vers met veel woorden "
                   "waarvan je streak nog onder de 5 staat.")
        if st.button("Zoek een vers", key="heb_zoek_zwak"):
            st.session_state["heb_gevonden"] = _zoek_zwak(boeken, stand, lijst)
        gevonden = st.session_state.get("heb_gevonden") or []
        if gevonden:
            _n, boek, v = gevonden[0]
            gekozen, verwijzing = [v], f"{boek['nl']} {v['v']}"
    else:
        st.caption("Zoekt verzen waarvan je élk woord al eens hebt geoefend — de "
                   "Hebreeuwse tegenhanger van de autonome leestekst bij het Grieks.")
        if st.button("Zoek een vers dat ik helemaal ken", key="heb_zoek_bekend"):
            st.session_state["heb_gevonden2"] = _zoek_bekend(boeken, stand, True)
            if not st.session_state["heb_gevonden2"]:
                st.session_state["heb_gevonden2"] = _zoek_bekend(boeken, stand, False)
                st.info("Geen vers gevonden waarvan je élk woord kent; hier is er een "
                        "waarvan je het meeste kent.")
        gevonden = st.session_state.get("heb_gevonden2") or []
        if gevonden:
            _n, boek, v = gevonden[0]
            gekozen, verwijzing = [v], f"{boek['nl']} {v['v']}"

    if not gekozen:
        st.info("Kies een vers, of laat de app er een zoeken.")
        return

    # ---- de tekst
    if kleur_soort:
        st.markdown(legenda(WOORDSOORT_KLEUR, "Woordsoorten"), unsafe_allow_html=True)
    if kleur_stam:
        st.markdown(legenda(STAM_KLEUR, "Stamformaties"), unsafe_allow_html=True)
    if opties["delen"]:
        # De legenda uit dezelfde tabel als de kleuring, zodat ze niet uit elkaar kunnen
        # lopen — en alleen de delen die je hebt aangevinkt.
        st.markdown(legenda({hebreeuws.SOORTEN[s]: hebreeuws.KLEUREN[s]
                             for s in hebreeuws.KLEUREN if s in opties["delen"]},
                            "Woorddelen"), unsafe_allow_html=True)

    st.markdown(f"<div style='font-size:14px;color:#f6c23e;margin-bottom:4px'>"
                f"📖 {verwijzing}</div>", unsafe_allow_html=True)
    regels = []
    for v in gekozen:
        stukken = [f"<span class='hebnr'>{v['v'].split(':')[-1]}</span> "]
        for wv in hebreeuws.woorden_van(v):
            stukken.append(_woord_html(wv, lijst, stand, opties))
        regels.append("".join(stukken))
    st.markdown(f"<div class='hebtekst'>{' '.join(regels)}</div>", unsafe_allow_html=True)

    # ---- de cijfers eronder
    alle = [wv for v in gekozen for wv in hebreeuws.woorden_van(v)]
    in_lijst = [x for x in alle if x["strong"] in lijst]
    gehad = [x for x in in_lijst if stand.get(x["strong"], (0, False))[1]]
    met_engels = [x for x in alle if x["engels"]]
    kol = st.columns(5)
    kol[0].metric("Woorden", len(alle))
    kol[1].metric("In je lijst", len(in_lijst))
    kol[2].metric("Al geoefend", len(gehad))
    kol[3].metric("Nog niet", len(in_lijst) - len(gehad))
    kol[4].metric("Met Engels", len(met_engels))

    with st.expander("📋 Alle woorden op een rij", expanded=False):
        rijen = []
        for v in gekozen:
            for wv in hebreeuws.woorden_van(v):
                vorm, strong, parsing = wv["vorm"], wv["strong"], wv["parsing"]
                w = lijst.get(strong)
                voor, kern, achter = hebreeuws.splits_affixen(vorm, parsing)
                streak, _gehad = stand.get(strong, (0, False))
                rijen.append({
                    "vers": v["v"], "vorm": vorm,
                    "klinkt": wv["translit"],
                    "stam": kern if (voor or achter) else "",
                    "betekenis": korte_betekenis(w) if w else "— niet in de cursuslijst",
                    "engels": wv["engels"],
                    "voor/achter": _affixen_kort(parsing, vorm),
                    "woordsoort": woordsoort(parsing),
                    "ontleding": ontleding(parsing),
                    "streak": streak,
                })
        st.dataframe(
            pd.DataFrame(rijen), use_container_width=True, hide_index=True,
            column_config={
                "vers": st.column_config.TextColumn("Vers", width="small"),
                "vorm": st.column_config.TextColumn("Vorm", width="small"),
                "klinkt": st.column_config.TextColumn("Klinkt als", width="small"),
                "stam": st.column_config.TextColumn("Stam", width="small"),
                "betekenis": st.column_config.TextColumn("Betekenis", width="medium"),
                "engels": st.column_config.TextColumn("Engels (BSB)", width="medium"),
                "voor/achter": st.column_config.TextColumn("Voor/achtervoegsel · uitgang",
                                                           width="medium"),
                "woordsoort": st.column_config.TextColumn("Soort", width="small"),
                "ontleding": st.column_config.TextColumn("Ontleding", width="medium"),
                "streak": st.column_config.NumberColumn("Streak", width="small"),
            })
    st.caption("Oefenen doe je in de snelle app: daar kun je een hoofdstuk kiezen en de "
               "woorden die je nog mist vooraan in je woordenschat zetten.")


# ============================================================== Hebreeuwse klankregels
# De tegenhanger van de Griekse contractietrainer, en met dezelfde afspraak: hier vórm je
# zelf. Herkennen doe je bij het lezen, waar de woorddelen gekleurd staan.
#
# Wat het beter maakt dan de Griekse: die werkt met een regeltabel en een handvol
# voorbeelden uit het boek. Hier is elke opgave een páár échte vormen van hetzelfde woord
# uit de Tenach -- één zonder het voorvoegsel en één met -- en de vindplaats staat erbij.
# Gemaakt door gereedschap/bouw_hebreeuws_klanken.py.
KLANK_BESTAND = "hebreeuws_klanken.json"
KLANK_SLEUTEL = "klank::"          # in hebr_stats, naast de woorden en de rijtjes


@st.cache_data(show_spinner=False)
def laad_klanken():
    """De oefenstof. Leeg als het bestand er niet is; dan verschijnt het tabblad niet."""
    import json
    import os
    try:
        with open(KLANK_BESTAND, encoding="utf-8") as f:
            return json.load(f).get("groepen") or []
    except (OSError, ValueError):
        return []


def klanken_beschikbaar():
    return bool(laad_klanken())


def _klank_stats():
    """De voortgang, in dezelfde dict die de snelle app gebruikt."""
    s = st.session_state.get("hebr_stats")
    if not isinstance(s, dict):
        s = {}
        st.session_state.hebr_stats = s
    return s


def _klank_opties(groep, opgave, hoeveel=4):
    """De keuzemogelijkheden: het goede antwoord plus afleiders uit dezelfde groep.

    Afleiders uit dezelfde groep en niet verzonnen: dan zijn het allemaal vormen die echt
    bestaan, en moet je op de regel letten in plaats van op wat er vreemd uitziet."""
    goed = opgave.get("antwoord") or opgave["uitkomst"]
    vast = groep.get("antwoordopties")
    if vast:
        return list(vast)
    alle = {v.get("antwoord") or v["uitkomst"] for v in groep["vragen"]}
    afleiders = [x for x in alle if x != goed]
    random.shuffle(afleiders)
    keuzes = afleiders[:hoeveel - 1] + [goed]
    random.shuffle(keuzes)
    return keuzes


def tab_klanken(registreer=None, bewaar=None):
    """Het tabblad. Aanroepen binnen 'with menu[i]:'.

    registreer en bewaar komen uit overhoring_web (registreer_oefening en trigger_save).
    Meegeven en niet importeren: dat zou een kringetje worden, want overhoring_web importeert
    deze module."""
    st.subheader("🔀 Hebreeuwse klankregels")
    groepen = laad_klanken()
    if not groepen:
        st.info("Het bestand hebreeuws_klanken.json staat niet in deze installatie.")
        return
    st.caption("Hier vórm je zelf. Elke opgave is een paar echte vormen uit de Tenach: één "
               "zonder het voorvoegsel en één met. Herkennen wat er in een woord zit doe je "
               "bij 📜 Tenach, waar de woorddelen gekleurd staan.")

    op_naam = {g["naam"]: g for g in groepen}
    k1, k2 = st.columns([3, 2])
    with k1:
        keuze = st.radio("Regel", list(op_naam), key="hkl_groep")
    groep = op_naam[keuze]
    with k2:
        niveau = st.radio("Hoe wil je antwoorden?",
                          ["Kies uit een rijtje", "Zelf typen"], key="hkl_niveau")
    typen = niveau.startswith("Zelf")

    st.info(groep["uitleg"])
    st.write("---")

    stats = _klank_stats()
    sleutel = KLANK_SLEUTEL + groep["sleutel"]
    staat_sleutel = f"hkl_staat_{groep['sleutel']}_{typen}"
    if staat_sleutel not in st.session_state:
        st.session_state[staat_sleutel] = {
            "i": random.randrange(len(groep["vragen"])), "goed": 0, "totaal": 0,
            "melding": None, "opties": None, "voor": None}
    staat = st.session_state[staat_sleutel]
    opgave = groep["vragen"][staat["i"]]
    goed_antwoord = opgave.get("antwoord") or opgave["uitkomst"]

    # De melding van de vórige opgave bovenaan, zodat je hem leest voordat je verder gaat.
    if staat.get("melding"):
        soort, tekst = staat["melding"]
        (st.success if soort == "goed" else st.error)(tekst)
        staat["melding"] = None
    if staat["totaal"]:
        st.caption(f"Deze ronde: {staat['goed']}/{staat['totaal']} goed")

    def volgende(goed, melding):
        staat["totaal"] += 1
        staat["goed"] += int(goed)
        staat["melding"] = ("goed" if goed else "fout", melding)
        staat["i"] = random.randrange(len(groep["vragen"]))
        staat["opties"] = None
        rec = stats.setdefault(sleutel, {"g": 0, "f": 0, "streak": 0})
        rec["g"] = int(rec.get("g", 0)) + int(goed)
        rec["f"] = int(rec.get("f", 0)) + int(not goed)
        rec["streak"] = int(rec.get("streak", 0)) + 1 if goed else 0
        if registreer:
            registreer()
        if bewaar:
            bewaar()
        st.rerun()

    # ---- de opgave
    delen = " + ".join(opgave["delen"])
    woorden = " + ".join(opgave.get("woorden") or [])
    st.markdown(f"<div class='hebtekst' style='font-size:34px;padding:6px 14px'>"
                f"{delen}</div>", unsafe_allow_html=True)
    if woorden:
        st.caption(f"{woorden} + de stam")
    st.markdown(f"**{groep['vraag']}**")

    if typen:
        with st.form(f"hkl_form_{staat['i']}_{groep['sleutel']}"):
            antwoord = st.text_input("Jouw vorm — Hebreeuws of in gewone letters getypt",
                                     key=f"hkl_in_{staat['i']}_{groep['sleutel']}")
            verzonden = st.form_submit_button("✓ Nakijken", type="primary")
        if verzonden:
            if not str(antwoord or "").strip():
                st.warning("Typ eerst een vorm.")
            else:
                # Vergelijken op medeklinkers: klinkertekens typen op een gewoon toetsenbord
                # is niet te doen, en de klankregel zit in de klinker die je niet kúnt typen.
                # Zelfde soepelheid als de woordenschat in de snelle app.
                goed = hebreeuws.vorm_ok(antwoord, goed_antwoord)
                volgende(goed, (f"✅ Juist! {delen} → **{opgave['uitkomst']}** "
                                f"({opgave['vers']})" if goed else
                                f"❌ Het was **{goed_antwoord}**. {delen} → "
                                f"{opgave['uitkomst']} ({opgave['vers']})"))
    else:
        if staat.get("voor") != staat["i"]:
            staat["opties"] = _klank_opties(groep, opgave)
            staat["voor"] = staat["i"]
        gekozen = st.radio("Kies", staat["opties"], index=None,
                           key=f"hkl_kies_{staat['i']}_{groep['sleutel']}")
        if st.button("✓ Nakijken", key=f"hkl_chk_{staat['i']}_{groep['sleutel']}",
                     type="primary"):
            if gekozen is None:
                st.warning("Kies eerst een optie.")
            else:
                goed = gekozen == goed_antwoord
                volgende(goed, (f"✅ Juist! {delen} → **{opgave['uitkomst']}** "
                                f"({opgave['vers']})" if goed else
                                f"❌ Het was **{goed_antwoord}**. {delen} → "
                                f"{opgave['uitkomst']} ({opgave['vers']})"))

    rec = stats.get(sleutel) or {}
    if rec:
        st.caption(f"In totaal: {rec.get('g', 0)} goed, {rec.get('f', 0)} fout · "
                   f"streak {rec.get('streak', 0)}")
    with st.expander("📋 Alle opgaven van deze regel", expanded=False):
        st.caption(f"{len(groep['vragen'])} opgaven, allemaal uit de Tenach.")
        st.dataframe(pd.DataFrame([
            {"opbouw": " + ".join(v["delen"]),
             "wordt": v["uitkomst"],
             "antwoord": v.get("antwoord") or v["uitkomst"],
             "vindplaats": v["vers"]} for v in groep["vragen"]]),
            use_container_width=True, hide_index=True)
