# -*- coding: utf-8 -*-
"""Grieks — NiceGUI-schil op grieks_motor.py, grieks_opslag.py en grieks_gebruiker.py.

Vormgeving volgt de designreview: inloggen in de hoofdkolom, Grieks in een tekstfont,
vier vaste bestemmingen onderaan, een antwoordbalk die blijft staan, en oefenbeurten
zonder paginaherlaad.

Starten:  py grieks_app.py
"""
import csv
import io
import json
import math
import os
import random
from datetime import date, timedelta
from urllib.parse import quote

from nicegui import app, run, ui

import grieks_gebruiker as gebruikers
import grieks_motor as motor
import grieks_opslag as opslag

# --- huisstijl (uit .streamlit/config.toml) ---
INKT, VLAK, RAND = "#0e1117", "#1e1e1e", "#2b3038"
TEKST, ZACHT = "#fafafa", "#9aa4ae"
MERK, GOED, FOUT = "#33ccff", "#3ddc97", "#ff6b81"
GRIEKS_FONT = "'Gentium Book Plus','Palatino Linotype',Georgia,serif"

BESTEMMINGEN = [("Vandaag", "●", "/vandaag"), ("Oefenen", "■", "/oefenen"),
                ("Lezen", "☰", "/lezen"), ("Voortgang", "▲", "/voortgang")]

ui.add_head_html(f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Gentium+Book+Plus:wght@400;700&display=swap" rel="stylesheet">
<meta name="theme-color" content="{INKT}">
<meta name="apple-mobile-web-app-capable" content="yes">
<style>
  body {{ background:{INKT}; color:{TEKST}; }}
  .grieks {{ font-family:{GRIEKS_FONT}; font-weight:400; }}
  .antwoordbalk {{ position:fixed; left:0; right:0; bottom:64px; z-index:20;
                   background:{INKT}; border-top:1px solid {RAND}; padding:10px 14px 12px; }}
  .onderbalk {{ position:fixed; left:0; right:0; bottom:0; z-index:30; height:64px;
                background:{VLAK}; border-top:1px solid {RAND}; display:flex; }}
  .onderbalk .vak {{ flex:1; display:flex; flex-direction:column; align-items:center;
                     justify-content:center; gap:3px; font-size:11px; color:{ZACHT};
                     cursor:pointer; user-select:none; text-decoration:none; }}
  .onderbalk .vak.actief {{ color:{MERK}; }}
  .inhoud {{ padding:14px 14px 96px; max-width:640px; margin:0 auto; }}
  .inhoud.metbalk {{ padding-bottom:190px; }}
  .smal {{ max-width:420px; margin:0 auto; padding:14px; }}
  .kaart {{ background:{VLAK}; border:1px solid {RAND}; border-radius:12px; padding:14px; }}
  .keuze {{ background:{VLAK}; border:1px solid {RAND}; border-radius:10px; padding:13px 14px;
            cursor:pointer; font-size:16px; text-align:left; width:100%; color:{TEKST}; }}
  .keuze:hover {{ border-color:{MERK}; }}
</style>
""", shared=True)

_DAGEN = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
_MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni",
            "juli", "augustus", "september", "oktober", "november", "december"]


_MND_KORT = ["jan", "feb", "mrt", "apr", "mei", "jun",
             "jul", "aug", "sep", "okt", "nov", "dec"]


def _kort_datum(tekst):
    """'2026-08-13' -> '13 aug'. Past in een smal vakje zonder af te breken."""
    try:
        j, m, d = str(tekst).split("-")
        return f"{int(d)} {_MND_KORT[int(m) - 1]}"
    except (ValueError, IndexError, AttributeError):
        return "nooit"


def nl_datum(d):
    """Nederlandse datum, zonder afhankelijk te zijn van de taalinstelling van de server."""
    return f"{_DAGEN[d.weekday()]} {d.day} {_MAANDEN[d.month - 1]}"


_sessies = {}

# De NT-tekst is 31 MB aan bestanden en kost 97 MB geheugen. Laat je die weg, dan
# draait de app prima door — alleen vervalt alles wat de bijbeltekst nodig heeft:
# Ontleden, de verbogen vormen uit het NT bij beheerste woorden, en het tekstfilter
# bij Stamtijden. Zo kun je een lichte versie hosten en lokaal toch alles hebben.
STREAMLIT_URL = os.environ.get(
    "GRIEKS_STREAMLIT", "https://woordengriekspthu.streamlit.app").strip().rstrip("/")


def bijbel_aanwezig():
    return any(os.path.exists(naam) for naam in
               ("bijbel_nt.json", "bijbel_nt_deel1.json", "bijbel_nt_deel2.json"))


BIJBEL = bijbel_aanwezig()


def streamlit_adres(g=None):
    """De volledige app, met je naam en codewoord erin zodat je meteen goed zit.
    De Streamlit-app leest die uit ?u= (zie main() daar). Ze staan dan wel in je
    browsergeschiedenis; dat kan hier, omdat het geen wachtwoord is — de app zegt dat
    bij het inloggen ook met zoveel woorden."""
    if not STREAMLIT_URL:
        return ""
    sleutel = getattr(g, "sleutel", "") if g is not None else ""
    return f"{STREAMLIT_URL}/?u={quote(sleutel)}" if sleutel else STREAMLIT_URL


def streamlit_link(g, tekst="Open de volledige app →"):
    adres = streamlit_adres(g)
    if adres:
        ui.html(f"<a href='{adres}' target='_blank' style='color:{MERK};font-size:14px;"
                f"text-decoration:none'>{tekst}</a>")


def naar_streamlit(g, waarvoor):
    """Kaartje dat uitlegt dat dit onderdeel in de volledige app zit."""
    with ui.element("div").classes("kaart w-full"):
        ui.label("Zit in de volledige app").style(
            f"color:{TEKST};font-size:15px;font-weight:600")
        ui.label(f"{waarvoor} werkt met de tekst van het Nieuwe Testament. Die staat niet "
                 f"in deze lichte versie; gebruik daarvoor de Streamlit-app.").style(
            f"color:{ZACHT};font-size:13px;line-height:1.5")
        streamlit_link(g)


def _huidige():
    return _sessies.get(app.storage.user.get("sleutel"))


def onderbalk(actief):
    """In één HTML-blok, zodat de vier links rechtstreeks in de flex-container zitten.
    Zet je ze los neer, dan wikkelt NiceGUI elk element in een eigen div en verdeelt
    de balk zich niet — dan vallen de tekens en de labels uit elkaar."""
    vakken = "".join(
        f"<a href='{pad}' class='vak{" actief" if naam == actief else ""}'>"
        f"<span style='font-size:17px;line-height:1'>{teken}</span>"
        f"<span>{naam}</span></a>"
        for naam, teken, pad in BESTEMMINGEN)
    ui.html(f"<div class='onderbalk'>{vakken}</div>")


def _bewaakt():
    """Geeft de ingelogde gebruiker, of stuurt naar het inlogscherm."""
    g = _huidige()
    if not g:
        ui.navigate.to("/")
        return None
    ui.query("body").style(f"background:{INKT}")
    return g


# ============================================================== inloggen
@ui.page("/")
def inlogpagina():
    if _huidige():
        ui.navigate.to("/vandaag")
        return
    ui.query("body").style(f"background:{INKT}")
    with ui.column().classes("smal w-full gap-2 items-stretch"):
        ui.html(
            f"<div style='text-align:center;padding:30px 0 2px'>"
            f"<div class='grieks' style='font-size:64px;line-height:1.1;color:{TEKST}'>λόγος</div>"
            f"<div style='font-size:22px;font-weight:600;margin-top:10px'>Grieks</div>"
            f"<div style='font-size:14px;color:{ZACHT};margin-top:2px'>"
            f"Nieuwtestamentisch Grieks · PThU</div></div>")
        ui.element("div").style("height:10px")

        # Twee gewone, zichtbare velden. Bewust géén wachtwoordveld: dat nodigt uit tot
        # het intypen van een echt wachtwoord, en deze twee woorden worden onversleuteld
        # in de Google Sheet bewaard.
        ui.html(
            f"<div class='kaart' style='font-size:13px;line-height:1.55;color:{ZACHT}'>"
            f"<b style='color:{TEKST}'>Dit is geen wachtwoord.</b><br>"
            f"Je naam en codewoord vormen samen het label waaronder je voortgang wordt "
            f"bewaard. Ze beveiligen niets en staan gewoon leesbaar in de spreadsheet — "
            f"<b style='color:{TEKST}'>vul hier dus nooit een echt wachtwoord in.</b><br>"
            f"Kies iets wat je onthoudt, bijvoorbeeld <i>zomer2026</i>.</div>")

        veld_naam = ui.input("Naam", placeholder="bijv. Bob").props(
            "outlined dark autocomplete=off").classes("w-full")
        veld_code = ui.input("Codewoord", placeholder="bijv. zomer2026").props(
            "outlined dark autocomplete=off").classes("w-full")
        melding = ui.label().style(f"color:{FOUT};font-size:13px;min-height:18px")
        knop = ui.button("Beginnen").props("unelevated").classes("w-full").style(
            f"background:{MERK};color:{INKT};font-weight:700;height:46px")
        ui.label("Gebruik je dezelfde twee woorden als in de volledige app, dan staat je "
                 "voortgang er meteen.").style(f"color:{ZACHT};font-size:12.5px;line-height:1.5")
        # Andersom verwijst de volledige app hierheen; zo weet je op elk inlogscherm
        # welke van de twee je voor je hebt.
        if STREAMLIT_URL:
            ui.html(f"<div style='color:{ZACHT};font-size:12.5px;line-height:1.6'>"
                    f"Deze app is voor snel oefenen: woorden, rijtjes en stamtijden. "
                    f"Ontleden, leesteksten en grammatica staan in de "
                    f"<a href='{STREAMLIT_URL}' style='color:{MERK};text-decoration:none'>"
                    f"volledige app</a>.</div>")

    async def probeer():
        melding.text = ""
        knop.props("loading")
        try:
            g = await run.io_bound(gebruikers.inloggen, veld_naam.value, veld_code.value)
        except opslag.OpslagFout as e:
            melding.text = str(e)
        except Exception as e:                                   # noqa: BLE001
            melding.text = f"Het lukte niet: {e}"
        else:
            _sessies[g.sleutel] = g
            app.storage.user["sleutel"] = g.sleutel
            ui.navigate.to("/vandaag")
            return
        knop.props(remove="loading")

    knop.on_click(probeer)
    veld_code.on("keydown.enter", probeer)


# ============================================================== vandaag
def klaargezet(g):
    """Wat er vandaag voor je klaarstaat, per onderdeel: naam, wat je krijgt, waar het
    staat, de dagdoel-sleutel en hoeveel je er vandaag al deed. De aantallen komen uit
    je eigen instellingen, zodat hier staat wat je straks écht voorgeschoteld krijgt."""
    def voorkeur(standaard, sleutel):
        return int((g.stats.get("ui_prefs") or {}).get(f"ng_{sleutel}", standaard[sleutel]))

    p = prefs(g)
    if p["keuze"] in PAAR_OEFENINGEN:
        woord_uitleg, woord_pad = "twee lijkende woorden tegelijk", "/oefenen/paren"
    elif p["opbouw_stijl"] == VAST:
        woord_uitleg = f"{int(p['aantal'])} kaarten · achterstallige woorden eerst"
        woord_pad = "/oefenen/woorden"
    else:
        woord_uitleg = "de app weegt wat je nodig hebt · achterstallig eerst"
        woord_pad = "/oefenen/woorden"
    log = g.daglog()
    return [
        ("Woordenschat", woord_uitleg, woord_pad, "woorden", g.woorden_vandaag()),
        ("Structuurwoorden", f"{voorkeur(SW_STANDAARD, 'sw_aantal')} woorden · zwakste eerst",
         "/oefenen/structuur", "struct", int(log.get("struct", 0) or 0)),
        ("Stamtijden", f"{voorkeur(STAM_STANDAARD, 'stam_aantal')} vormen · zwakste eerst",
         "/oefenen/stamtijden", "stam", int(log.get("stam", 0) or 0)),
        ("Actief beheersen", f"{voorkeur(AF_STANDAARD, 'af_aantal')} cellen uit de rijtjes",
         "/oefenen/actief", "actief", int(log.get("actief", 0) or 0)),
        ("Ontleden", "een vers uit het NT, woord voor woord",
         "/oefenen/ontleden", "verzen", int(log.get("verzen", 0) or 0)),
    ]


@ui.page("/vandaag")
def vandaagpagina():
    g = _bewaakt()
    if not g:
        return
    sam = g.samenvatting()
    dagen = g.stats.get("dag_stats") or {}
    # Het dagdoel dat je bij Voortgang instelt; 'woorden' telt verschillende woorden.
    doelen = g.dagdoel()
    doel = max(1, int(doelen.get("woorden", 10) or 10))
    gedaan = g.woorden_vandaag()

    with ui.column().classes("inhoud w-full gap-3"):
        ui.label("Vandaag").style("font-size:26px;font-weight:700")
        ui.label(nl_datum(date.today())).style(f"color:{ZACHT};font-size:13px")

        with ui.element("div").classes("kaart w-full"):
            with ui.row().classes("w-full items-baseline gap-2"):
                ui.label(str(gedaan)).style(
                    f"font-size:44px;font-weight:800;color:{MERK};line-height:1")
                ui.label(f"van {doel}").style(f"color:{ZACHT};font-size:15px")
            balk = min(1.0, gedaan / doel)
            ui.element("div").style(
                f"width:100%;height:6px;border-radius:3px;background:{RAND};margin:10px 0 8px")\
                .classes("relative")
            ui.html(f"<div style='margin-top:-14px;width:{balk*100:.0f}%;height:6px;"
                    f"border-radius:3px;background:{MERK}'></div>")
            resterend = max(0, doel - gedaan)
            ui.label("Je dagdoel is gehaald." if resterend == 0
                     else f"Nog {resterend} woorden voor je dagdoel.").style(
                f"color:{TEKST};font-size:14px")
            ui.label(f"{sam['dagen']} oefendagen · {sam['beheerst']} woorden beheerst").style(
                f"color:{ZACHT};font-size:12.5px")

        ui.label("Klaargezet").style("font-size:15px;font-weight:700;margin-top:6px")
        for naam, uitleg, pad, sleutel, gedaan_nu in klaargezet(g):
            doel_n = int(doelen.get(sleutel, 0) or 0)
            af = doel_n and gedaan_nu >= doel_n
            with ui.element("div").classes("kaart w-full").on(
                    "click", lambda p=pad: ui.navigate.to(p)):
                with ui.row().classes("w-full items-center justify-between no-wrap"):
                    with ui.column().classes("gap-0").style("min-width:0"):
                        ui.label(naam).style(f"color:{TEKST};font-size:16px;font-weight:600")
                        ui.label(uitleg).style(f"color:{ZACHT};font-size:12.5px")
                    with ui.row().classes("items-center gap-2 no-wrap"):
                        if doel_n:
                            ui.label(f"{'✓ ' if af else ''}{gedaan_nu}/{doel_n}").style(
                                f"color:{GOED if af else MERK};font-size:13px;"
                                f"white-space:nowrap")
                        ui.label("›").style(f"color:{ZACHT};font-size:22px")

        ui.label("Deze week").style("font-size:15px;font-weight:700;margin-top:6px")
        with ui.row().classes("w-full gap-2 no-wrap"):
            vandaag_d = date.today()
            maandag = vandaag_d - timedelta(days=vandaag_d.weekday())
            hoogste = max([1] + [int(v) for v in dagen.values()])
            for i in range(7):
                d = maandag + timedelta(days=i)
                n = int(dagen.get(d.strftime("%Y-%m-%d"), 0))
                hoog = max(4, round(46 * n / hoogste))
                kleur = MERK if n else RAND
                with ui.column().classes("items-center gap-1").style("flex:1"):
                    ui.element("div").style(
                        f"width:100%;height:{hoog}px;border-radius:3px;background:{kleur}")
                    ui.label("mdwdvzz"[i]).style(
                        f"color:{TEKST if d == vandaag_d else ZACHT};font-size:11px")
    onderbalk("Vandaag")


# ============================================================== oefenen
AUTO = "Automatisch (aanbevolen)"
VORMEN = [AUTO, "Alleen leren", "Alleen meerkeuze", "Mix (meerkeuze + typen)",
          "Alleen typen"]
_VORM_CODE = {"Alleen leren": "1", "Alleen meerkeuze": "2", "Alleen typen": "4"}

# Wat een goed antwoord aan streak oplevert per vraagvorm. Zelf typen telt zwaarder
# dan aanwijzen; in de Mix levert de meerkeuze zelf niets op maar verdubbelt hij de
# opbrengst van het typen erna — dat is de combo.
STREAK_PUNTEN = {"4": 3, "2": 1, "3_typ": 1, "3_mc": 0}
STREAK_STRAF = 2           # wat een echte misser van de streak afhaalt
STRAF_STREAK = 16          # vanaf deze streak is één misser meteen een echte misser

OEFENINGEN = ["Leerpad (levels)", "Losse lessen", "Knelpunten", "Lang niet gedaan",
              "Mastery", "Gelijkende woorden", "Mijn verwarwoorden"]

# De twee oefeningen die als paar-oefening lopen: je krijgt twee lijkende woorden
# tegelijk en geeft van allebei de betekenis. Zo leer je ze uit elkaar houden.
PAAR_OEFENINGEN = ("Gelijkende woorden", "Mijn verwarwoorden")

OUDE_STOF = {"Alleen dit level": 0, "1 oud woord": 1, "Kleine herhaalronde (5)": 5,
             "Grote herhaalronde (10)": 10}

MIX = "Automatisch (weegt je woorden)"
VAST = "Vast aantal kaarten"
ZELF = "Zelf samenstellen"
OPBOUW_STIJLEN = [MIX, VAST, ZELF]
# (pref-sleutel, naam, streakbereik, telling) — dezelfde vijf fasen als de motor gebruikt.
FASEN = [("mix_nieuw", "nieuw", "0", lambda s: s == 0),
         ("mix_incubatie", "prille start", "1–3", lambda s: 1 <= s <= 3),
         ("mix_training", "in training", "4–15", lambda s: 4 <= s <= 15),
         ("mix_beheerst", "beheerst", "16–29", lambda s: 16 <= s <= 29),
         ("mix_mastery", "mastery", "30+", lambda s: s >= 30)]
# pref-sleutel -> de naam die kies_gefaseerde_oefensessie in custom_counts verwacht
FASE_MOTOR = {"mix_nieuw": "nieuw", "mix_incubatie": "incubatie", "mix_training": "training",
              "mix_beheerst": "beheerst", "mix_mastery": "mastery"}

STANDAARD = {"keuze": "Leerpad (levels)", "lessen": [], "vorm": AUTO, "aantal": 12,
             "nieuw_mee": True, "audio": True, "opbouw": False,
             "level": 0, "oude_stof": "Kleine herhaalronde (5)", "nieuw_aantal": 3,
             "mastery_vormen": True, "verwar_mee": True, "verwar_max": 3,
             "opbouw_stijl": MIX,
             "mix_nieuw": 2, "mix_incubatie": 4, "mix_training": 6, "mix_beheerst": 2,
             "mix_mastery": 0}


def prefs(g):
    """Instellingen uit ui_prefs — hetzelfde blok dat de Streamlit-app gebruikt,
    dus wat je hier kiest komt daar ook terug."""
    p = g.stats.setdefault("ui_prefs", {})
    uit = {k: p.get(f"ng_{k}", v) for k, v in STANDAARD.items()}
    # Een sleutel die van naam veranderde of van hand is aangepast mag de sessie niet
    # laten omvallen; onbekende waarden vallen terug op de standaard.
    if uit["opbouw_stijl"] not in OPBOUW_STIJLEN:
        uit["opbouw_stijl"] = MIX
    if uit["vorm"] not in VORMEN:
        uit["vorm"] = AUTO
    return uit


def zet_pref(g, sleutel, waarde):
    g.stats.setdefault("ui_prefs", {})[f"ng_{sleutel}"] = waarde


KNELPUNT_MAX = 20        # zoveel knelpunten tegelijk; meer wordt een uitzichtloze lijst
OUD_MAX = 60


def bouw_poule(g, keuze, lessen, level=0):
    """De verzameling woorden waaruit een sessie wordt getrokken.
    De filters volgen die van de Streamlit-app, zodat dezelfde keuze daar en hier
    dezelfde woorden oplevert."""
    alles = g.woorden
    # De lessenkeuze beperkt niet alleen 'Losse lessen': ook knelpunten, lang niet
    # gedaan en gelijkende woorden zoek je binnen de lessen die je hebt aangevinkt.
    binnen = [w for w in alles if w.get("les") in lessen] if lessen else alles
    if keuze == "Losse lessen":
        return binnen
    if keuze == "Mastery":
        return [w for w in alles if int(w.get("streak", 0)) >= 30]
    if keuze == "Knelpunten":
        # Alles waar je op struikelt: fouten gemaakt, of wel goed maar nog wankel.
        knel = [w for w in binnen
                if int(w.get("score_fout", 0) or 0) > 0
                or (int(w.get("score_goed", 0) or 0) > 0
                    and int(w.get("streak", 0) or 0) <= 3)]

        def scheefheid(w):
            goed = int(w.get("score_goed", 0) or 0)
            fout = int(w.get("score_fout", 0) or 0)
            return fout / max(1, goed + fout)

        return sorted(knel, key=scheefheid, reverse=True)[:KNELPUNT_MAX]
    if keuze == "Lang niet gedaan":
        gedaan = [w for w in binnen if w.get("laatst_geoefend")]
        return sorted(gedaan, key=lambda w: w.get("laatst_geoefend", ""))[:OUD_MAX]
    if keuze == "Gelijkende woorden":
        # Alleen woorden die je al eens deed: een onbekend woord naast een ander
        # onbekend woord leert je niets over het onderscheid.
        try:
            return motor.verzamel_lookalikes(binnen, motor.laad_verwarparen_db(),
                                             alleen_geoefend=True)
        except Exception:                                        # noqa: BLE001
            return []
    if keuze == "Mijn verwarwoorden":
        # verzamel_verwarwoorden trekt de partner van elk paar erbij en laat paren
        # vallen zodra je ze allebei beheerst (streak 16+).
        try:
            return motor.verzamel_verwarwoorden(alles, g.stats.get("verwar_stats") or {})
        except Exception:                                        # noqa: BLE001
            return []
    # Leerpad: het gekozen level, of anders het eerstvolgende dat nog niet af is
    try:
        status = motor.leerpad_status(motor.bouw_leerpad_levels(alles))
        gekozen = int(level or 0)
        if gekozen:
            for st in status:
                if st.get("index") == gekozen and st.get("woorden"):
                    return list(st["woorden"])
        for st in status:
            # 'voltooid' is het ja/nee; 'klaar' is het AANTAL woorden dat al af is.
            if not st.get("voltooid") and st.get("woorden"):
                return list(st["woorden"])
    except Exception:                                            # noqa: BLE001
        pass
    return [w for w in alles if (w.get("les") or 99) <= 4] or alles


MASTERY_STREAK = 30


def bijbelvormen(w, hoeveel=6):
    """Verschillende verbogen vormen van dit woord zoals ze echt in het NT staan.
    Voor woorden die je al beheerst is de woordenboekvorm te makkelijk geworden;
    zo'n echte vorm dwingt je de uitgang te herkennen."""
    strong = str(w.get("strong", "") or "").lstrip("G").strip()
    if not strong or not BIJBEL:
        return []
    try:
        db = motor.laad_bijbel_db()
        refs = (motor._bijbel_strong_index(db) or {}).get(strong) or []
    except Exception:                                            # noqa: BLE001
        return []
    gezien, uit = set(), []
    for ref in refs[:40]:
        for x in db.get(ref, []):
            if str(x.get("strong", "")).lstrip("G").strip() != strong:
                continue
            vorm = str(x.get("grieks", "") or "").strip(" ,.;·")
            sleutel = motor.normaliseer_accent(vorm)
            if not vorm or sleutel in gezien:
                continue
            gezien.add(sleutel)
            uit.append({"vorm": vorm, "parsing": x.get("parsing_info", ""), "ref": ref})
            if len(uit) >= hoeveel:
                return uit
    return uit


def _hint(w):
    """De hint die je krijgt als je vastloopt: citatievorm, uitspraak en het
    ezelsbruggetje. Zelfde inhoud als de hint in de Streamlit-app — die helpt je het
    woord ophalen, terwijl gemaskeerde letters je alleen laten raden."""
    delen = [str(d).strip() for d in (w.get("lexeem_info") or w.get("grieks_info", ""),
                                      w.get("fonetisch", "")) if str(d or "").strip()]
    beeld = f"{w.get('anker', '') or ''} {w.get('beeld', '') or w.get('opmerking', '') or ''}".strip()
    if beeld:
        delen.append(beeld)
    return " · ".join(delen) or _letterhint(w)


def spreek_uit(tekst):
    """Laat de browser de Erasmiaanse transliteratie voorlezen. Bewust de fonetische
    spelling en geen Grieks schrift: Nieuwgriekse stemmen volgen een andere klankleer
    (η/υ/ει → 'ie') dan de uitspraak die de cursus hanteert. Zelfde aanpak als de
    uitspraakknop in de Streamlit-app."""
    if not str(tekst or "").strip():
        return
    ui.run_javascript(f"""
        (function() {{
            if (!window.speechSynthesis) return;
            var zeg = function() {{
                var u = new SpeechSynthesisUtterance({json.dumps(str(tekst))});
                u.rate = 0.85; u.lang = "nl-NL";
                var stemmen = window.speechSynthesis.getVoices() || [];
                var voorkeur = stemmen.find(function(v) {{ return /nl-|en-|de-/i.test(v.lang); }});
                if (voorkeur) u.voice = voorkeur;
                window.speechSynthesis.cancel();
                window.speechSynthesis.speak(u);
            }};
            // Stemmen laden asynchroon, vooral op mobiel; even wachten als ze er nog niet zijn.
            if ((window.speechSynthesis.getVoices() || []).length === 0) {{
                window.speechSynthesis.onvoiceschanged = zeg;
                setTimeout(zeg, 300);
            }} else {{ zeg(); }}
        }})();
    """)


def _letterhint(w):
    """Terugval als een woord geen ezelsbruggetje heeft: de eerste letter van elk
    woord plus puntjes, zodat je de vorm ziet zonder het antwoord te krijgen."""
    nl = str(w.get("nederlands", "") or "").strip()
    if not nl:
        return "geen betekenis bekend"
    eerste = nl.split(",")[0].split(";")[0].strip()
    gemaskeerd = " ".join(
        deel[0] + "·" * (len(deel) - 1) if len(deel) > 1 else deel
        for deel in eerste.split())
    extra = f"   ({nl.count(',') + nl.count(';') + 1} betekenissen)" if ("," in nl or ";" in nl) else ""
    return f"{gemaskeerd}{extra}"


def _statusrij(vakjes):
    """Rij gelijke vakjes met een waarde en een label. In één HTML-blok, anders
    wikkelt NiceGUI elk vakje in een eigen div en lopen de breedtes uiteen."""
    inhoud = "".join(
        f"<div style='flex:1;min-width:0;border:1px solid {RAND};border-radius:8px;"
        f"padding:5px 2px;text-align:center'>"
        f"<div style='color:{kleur};font-size:13px;font-weight:600;line-height:1.25;"
        f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>{waarde}</div>"
        f"<div style='color:{ZACHT};font-size:10px;line-height:1.2'>{label}</div></div>"
        for waarde, label, kleur in vakjes)
    return f"<div style='display:flex;gap:6px;width:100%'>{inhoud}</div>"


def _leerkaart(w, woordenlijst):
    """Wat je bij een nieuw woord meteen wilt zien: hoe het klinkt, waar het vandaan
    komt en wat het betekent. Zelfde inhoud als de leerkaart in de Streamlit-app."""
    delen = []
    ob = gebruikers.woord_opbouw(w.get("grieks", ""), woordenlijst)
    if ob:
        delen.append(
            f"<div style='color:{ZACHT};font-size:13.5px;margin-bottom:10px'>"
            f"🔗 {ob['voorzetsel']} <i>({ob['betekenis']})</i> + {ob['grondwoord']}"
            f" → {w.get('grieks','')}</div>")

    fonetisch = str(w.get("fonetisch", "") or "").strip()
    # 'anker' is de emoji, 'beeld' de omschrijving die erbij hoort — niet andersom.
    emoji = str(w.get("anker", "") or "").strip()
    beeld = str(w.get("beeld", "") or "").strip()
    if fonetisch or beeld:
        binnen = ""
        if fonetisch:
            binnen += (f"<div style='color:{MERK};font-size:17px;font-weight:600'>"
                       f"🔊 {fonetisch}</div>")
        if beeld:
            binnen += (f"<div style='color:{ZACHT};font-size:13.5px;line-height:1.5;"
                       f"margin-top:8px'>{emoji + ' ' if emoji else '💡 '}{beeld}</div>")
        delen.append(f"<div style='background:rgba(51,204,255,.09);"
                     f"border:1px solid {MERK}40;border-radius:12px;padding:12px 14px;"
                     f"margin-bottom:10px'>{binnen}</div>")

    delen.append(f"<div style='color:{ZACHT};font-size:12px'>betekenis</div>"
                 f"<div style='color:{TEKST};font-size:20px;line-height:1.35'>"
                 f"{w.get('nederlands','')}</div>")
    return f"<div style='width:100%;text-align:center'>{''.join(delen)}</div>"


def _feedbackblok(w, juist, sessie, woordenlijst, kop=None):
    """Hetzelfde als de groene/rode balk in de Streamlit-app: het woord, de
    woordenboekvorm mét uitgangen, de uitspraak en de volledige betekenis.
    Met een eigen `kop` dient hetzelfde blok ook als 'hier is het antwoord'."""
    kleur = MERK if kop else (GOED if juist else FOUT)
    achter = ("rgba(51,204,255,.10)" if kop else
              ("rgba(61,220,151,.10)" if juist else "rgba(255,107,129,.10)"))
    grieks = w.get("grieks", "")
    # lexeem_info is de citatievorm met genitief-uitgang en lidwoord: 'λόγος, -ου, ὁ'
    uitgangen = w.get("lexeem_info") or w.get("grieks_info") or ""
    fonetisch = w.get("fonetisch", "")
    regels = [
        f"<div style='color:{kleur};font-weight:700;font-size:16px;margin-bottom:6px'>"
        f"{kop or ('✓ Goed!' if juist else '✗ Niet goed')}</div>",
        f"<div class='grieks' style='font-size:26px;color:{TEKST};line-height:1.2'>{grieks}</div>",
    ]
    tv = getattr(sessie, "toonvorm", None)
    if tv:
        regels.append(
            f"<div style='color:{MERK};font-size:14px;margin-top:4px'>"
            f"<span class='grieks' style='font-size:19px'>{tv['vorm']}</span> — "
            f"{tv['parsing']}</div>"
            f"<div style='color:{ZACHT};font-size:12px'>{tv['ref']}</div>")
    # Bij werkwoorden is de citatievorm gelijk aan het lemma; dan niets herhalen.
    # Genormaliseerd vergelijken: dezelfde letters kunnen als NFC of NFD zijn opgeslagen.
    import unicodedata as _u
    _n = lambda t: _u.normalize("NFC", str(t or "")).strip()
    if _n(uitgangen) and _n(uitgangen) != _n(grieks):
        regels.append(f"<div class='grieks' style='color:{ZACHT};font-size:15px'>{uitgangen}</div>")
    if fonetisch:
        regels.append(f"<div style='color:{ZACHT};font-size:12.5px;font-style:italic'>{fonetisch}</div>")
    regels.append(f"<div style='color:{TEKST};font-size:16px;margin-top:6px'>"
                  f"{w.get('nederlands', '')}</div>")
    ob = gebruikers.woord_opbouw(grieks, woordenlijst)
    if ob:
        regels.append(f"<div style='color:{ZACHT};font-size:13px;margin-top:6px'>"
                      f"🔗 {ob['voorzetsel']} <i>({ob['betekenis']})</i> + {ob['grondwoord']}"
                      f" → {grieks}</div>")
    regels.append(f"<div style='color:{ZACHT};font-size:12px;margin-top:8px'>"
                  f"{sessie.goed} goed · {sessie.fout} fout in deze ronde · "
                  f"streak nu {int(w.get('streak', 0) or 0)}</div>")
    return (f"<div style='background:{achter};border:1px solid {kleur}40;border-radius:12px;"
            f"padding:14px;text-align:center;width:100%'>{''.join(regels)}</div>")


def _uitslaglijst(kop, kleur, regels):
    """Eén blok van de eindsamenvatting: een gekleurde kop met daaronder de woorden."""
    inhoud = "".join(f"<div style='font-size:13.5px;color:{TEKST};line-height:1.7'>{r}</div>"
                     for r in regels) or f"<div style='color:{ZACHT};font-size:13px'>—</div>"
    return (f"<div class='kaart' style='width:100%'>"
            f"<div style='color:{kleur};font-weight:700;font-size:14px;margin-bottom:4px'>"
            f"{kop}</div>{inhoud}</div>")


def _opbouw_tekst(w, woordenlijst):
    """Samenstelling tonen als het grondwoord zelf ook in je lijst staat."""
    ob = gebruikers.woord_opbouw(w.get("grieks", ""), woordenlijst)
    if ob:
        grond = next((x for x in woordenlijst if x.get("grieks") == ob["grondwoord"]), None)
        bet = f" ({grond.get('nederlands', '')[:34]})" if grond else ""
        return (f"{w.get('grieks','')} = {ob['voorzetsel']} + {ob['grondwoord']}\n"
                f"{ob['voorzetsel']} betekent '{ob['betekenis']}'{bet}")
    kl = motor.opb_contracta_stamklinker(w.get("grieks", ""))
    if kl:
        return f"Verbum contractum op -{kl}ω: de stamklinker {kl} versmelt met de uitgang."
    return "Dit woord is niet uit delen opgebouwd die je al kent."


def verwar_kandidaten(w, antwoord, woordenlijst):
    """Woorden die je met dit woord verward kunt hebben: woorden die precies de betekenis
    hebben die jij gaf, plus look-alikes op spelling. Er wordt niets van vastgelegd — in de
    eindsamenvatting vink je zelf aan wat écht klopte. Automatisch toevoegen vervuilde de
    lijst, want vaak hebben meerdere woorden dezelfde Nederlandse betekenis."""
    getoond = w.get("grieks", "")
    uit = {}
    try:
        for ander in motor.woorden_met_zelfde_betekenis(
                antwoord, woordenlijst, exclude_grieks=getoond, alleen_geoefend=True):
            uit[ander.get("grieks", "")] = str(ander.get("nederlands", ""))
    except Exception:                                            # noqa: BLE001
        pass
    try:
        idx = {x.get("grieks"): x for x in woordenlijst if x.get("grieks")}
        for tg in (motor.laad_verwarparen_db().get(getoond) or []):
            tw = idx.get(tg)
            if tw and motor._is_al_geoefend(tw):
                uit[tg] = str(tw.get("nederlands", ""))
            if len(uit) >= 6:
                break
    except Exception:                                            # noqa: BLE001
        pass
    uit.pop(getoond, None)
    uit.pop("", None)
    return uit


def fase_telling(poule):
    """Hoeveel woorden er in deze poule per fase klaarstaan — de 'beschikbaar'-cijfers
    bij Zelf samenstellen."""
    return {sleutel: sum(1 for w in poule if test(int(w.get("streak", 0) or 0)))
            for sleutel, _naam, _bereik, test in FASEN}


def eigen_aantallen(p):
    """De vijf fase-schuiven als custom_counts voor de motor, of None bij de aanbevolen mix.
    Staat alles op nul, dan is 'zelf samenstellen' leeg gelaten; dan toch de mix pakken,
    want een sessie van nul kaarten helpt niemand."""
    if p.get("opbouw_stijl") != ZELF:
        return None
    telling = {FASE_MOTOR[s]: max(0, int(p.get(s, 0) or 0)) for s in FASE_MOTOR}
    return telling if sum(telling.values()) else None


class Sessie:
    """Eén ronde kaarten, met oplopende moeilijkheid per woord.

    De kaarten staan in een wachtrij, niet in een vaste lijst: een woord dat je mist
    komt verderop terug (eerst overtikken, daarna nog een keer de echte vraag). Zelfde
    opzet als sessie_lijst in de Streamlit-app."""

    def __init__(self, g):
        p = prefs(g)
        self.poule = bouw_poule(g, p["keuze"], p["lessen"], p.get("level", 0)) or g.woorden
        self.nieuw_over = 0
        eigen = eigen_aantallen(p)
        # Bij deze drie zou een gloednieuw woord de bedoeling ondermijnen: je bent aan
        # het stutten of ophalen, niet aan het uitbreiden. Puur typen kan een woord dat
        # je nog nooit zag sowieso niet vragen.
        geen_nieuw = (not p["nieuw_mee"]
                      or p["keuze"] in ("Knelpunten", "Lang niet gedaan")
                      or p["vorm"] == "Alleen typen")
        if p["keuze"] == "Leerpad (levels)" and p["opbouw_stijl"] == MIX:
            gekozen = self._leerpadronde(p)
        else:
            gekozen = motor.kies_gefaseerde_oefensessie(
                self.poule, "vocab", custom_counts=eigen,
                max_nieuw=int(p.get("nieuw_aantal", 3)) if p["nieuw_mee"] else 0,
                sorteer_oudste_eerst=p["keuze"] == "Lang niet gedaan",
                verbied_nieuwe_woorden=geen_nieuw,
                totale_db=g.woorden) or self.poule
        # Automatisch en Zelf samenstellen bepalen zelf de omvang: de motor weegt hoe
        # zwaar je woorden zijn (veel wankele woorden = kortere ronde). Alleen bij een
        # vast aantal kappen we af.
        gekozen = (list(gekozen)[:int(p["aantal"])] if p["opbouw_stijl"] == VAST
                   else list(gekozen))
        if p.get("verwar_mee", True):
            gekozen = self._verwarwoorden_erbij(g, gekozen, int(p.get("verwar_max", 3) or 0))
        herhaal = OUDE_STOF.get(p.get("oude_stof", ""), 0)
        if herhaal and p["keuze"] == "Leerpad (levels)":
            try:
                gekozen = motor.voeg_herhaalwoorden_toe(gekozen, g.woorden, herhaal)
            except Exception:                                    # noqa: BLE001
                pass
        self.wachtrij = self._kaarten(gekozen, p["vorm"])
        self.begin_aantal = len(self.wachtrij)
        self.prefs = p
        self.gedaan = 0
        self.goed = 0
        self.fout = 0
        self.beoordeeld = False
        self.toonvorm = None
        self.fouten = 0            # missers op de kaart die nu voorligt
        self.gestraft = set()      # woorden waarvan je het antwoord al zag
        self.combo = {}            # Mix: had je de meerkeuze in één keer goed?
        self.bezig = False         # tegen dubbelklikken tijdens het opslaan
        # Voor de eindsamenvatting: wat ging goed, wat fout, en welke woorden zou je
        # verward kunnen hebben. Dat laatste bevestig je aan het eind zelf.
        self.gelukt = {}
        self.mislukt = {}
        self.kandidaten = {}
        self.woord = None
        self.vorm = None
        self.volgende()

    def _leerpadronde(self, p):
        """In het Leerpad ís het level de lesstof, dus daar gelden de instroomfilters niet:
        woorden waar je al mee bezig bent komen allemaal mee — die wil je afmaken — en
        gloednieuwe woorden alleen tot het ingestelde maximum, zodat het behapbaar blijft.
        Is het level helemaal af, dan haal je het gewoon nog eens op."""
        def is_nieuw(w):
            return (int(w.get("streak", 0) or 0) == 0
                    and not int(w.get("score_goed", 0) or 0)
                    and not int(w.get("score_fout", 0) or 0)
                    and not str(w.get("laatst_geoefend", "") or "").strip())

        drempel = motor.LEERPAD_DREMPEL
        bezig = [w for w in self.poule
                 if int(w.get("streak", 0) or 0) < drempel and not is_nieuw(w)]
        nieuw = [w for w in self.poule if is_nieuw(w)]
        random.shuffle(bezig)
        random.shuffle(nieuw)
        instroom = max(1, int(p.get("nieuw_aantal", 3) or 0)) if p["nieuw_mee"] else 0
        self.nieuw_over = max(0, len(nieuw) - instroom)
        return (bezig + nieuw[:instroom]) or [
            w for w in self.poule if int(w.get("streak", 0) or 0) >= drempel]

    @staticmethod
    def _kaarten(gekozen, vorm):
        vast = _VORM_CODE.get(vorm)
        if vast:
            return [(w, vast) for w in gekozen]
        if vorm.startswith("Mix"):
            # Eerst de hele ronde aanwijzen, daarna dezelfde woorden typen. Wie de
            # meerkeuze in één keer goed had, krijgt bij het typen een dubbele opbrengst.
            return ([(w, "3_mc") for w in gekozen] + [(w, "3_typ") for w in gekozen])
        return motor.leerpad_kaart_volgorde(gekozen)

    @staticmethod
    def _verwarwoorden_erbij(g, gekozen, hoeveel=3):
        """Look-alikes van de gekozen woorden mee de sessie in trekken, zodat je ze naast
        elkaar leert onderscheiden. Voegt nooit een woord toe dat je nog nooit zag."""
        if hoeveel <= 0:
            return gekozen
        try:
            gekozen = motor.voeg_verwar_twins_toe(
                gekozen, g.woorden, motor.laad_verwarparen_db(), max_twins=hoeveel)
            return motor.voeg_eigen_verwar_toe(
                gekozen, g.woorden, g.stats.get("verwar_stats") or {}, max_extra=hoeveel)
        except Exception:                                        # noqa: BLE001
            return gekozen

    # ------------------------------------------------------------ door de wachtrij
    def volgende(self):
        """Naar de volgende kaart. Leeg betekent: ronde klaar."""
        self.woord, self.vorm = self.wachtrij.pop(0) if self.wachtrij else (None, None)
        self.fouten = 0
        self.beoordeeld = False

    def opnieuw_later(self, straks=None):
        """Deze kaart nog een keer aanbieden, achteraan de wachtrij."""
        self.wachtrij.append((self.woord, straks or self.vorm))

    def eerst_overtikken(self):
        """Na een echte misser: eerst overtikken (meteen hierna), daarna nog een keer
        de gewone vraag. Zo verankert het antwoord voordat je het opnieuw ophaalt."""
        self.wachtrij.insert(0, (self.woord, "overtik"))
        self.wachtrij.append((self.woord, self.vorm))
        self.gestraft.add(self.woord.get("grieks", ""))

    @property
    def totaal(self):
        """Hoeveel kaarten de ronde nu telt — dat groeit als een woord terugkomt."""
        return max(self.begin_aantal, self.gedaan + len(self.wachtrij) + 1)

    def noteer_uitslag(self, w, juist, antwoord, woordenlijst):
        grieks = w.get("grieks", "")
        if juist:
            self.gelukt[grieks] = str(w.get("nederlands", ""))
            return
        self.mislukt[grieks] = {"nederlands": str(w.get("nederlands", "")),
                                "antwoord": str(antwoord or "")}
        kand = verwar_kandidaten(w, antwoord, woordenlijst)
        if kand:
            self.kandidaten.setdefault(grieks, {"nederlands": str(w.get("nederlands", "")),
                                                "antwoord": str(antwoord or ""),
                                                "opties": {}})["opties"].update(kand)

    def onthoud_kandidaat(self, w, antwoord, grieks, nederlands):
        """De betekenis die je aanklikte hoort bij dít woord — ook als je dat nog nooit
        geoefend hebt. Aanbieden in de eindsamenvatting, niet automatisch vastleggen."""
        if not grieks or grieks == w.get("grieks", ""):
            return
        rec = self.kandidaten.setdefault(
            w.get("grieks", ""), {"nederlands": str(w.get("nederlands", "")),
                                  "antwoord": str(antwoord or ""), "opties": {}})
        rec["opties"][grieks] = str(nederlands)


def afleiders(woord, woordenlijst, hoeveel=3):
    """Meerkeuze-opties in dezelfde volgorde als de Streamlit-app ze kiest:
    eerst de echte look-alike-twins uit verwarparen.json (die je al geoefend hebt),
    dan woorden die qua spelling op dit woord lijken binnen dezelfde woordsoort,
    dan de rest van die woordsoort, en pas daarna willekeurige woorden.

    Geeft (opties, bron) terug: bron zegt bij welk Grieks woord elke afleider hoort,
    zodat je na een misser kunt zien wat je eigenlijk hebt aangeklikt."""
    juist = str(woord.get("nederlands", "") or "")
    doel = motor.normaliseer_accent(woord.get("grieks", ""))
    soort = woord.get("woordsoort", "")
    prefix = doel[:2] if len(doel) >= 2 else ""
    stamgok = doel[1:-2] if len(doel) >= 5 else ""

    gekozen, bron = [], {}

    def voeg_toe(ander):
        ned = str(ander.get("nederlands", "") or "").strip()
        if not ned or ned == juist or ned in bron or motor.zelfde_betekenis(ned, juist):
            return False
        bron[ned] = ander
        gekozen.append(ned)
        return True

    index = {w.get("grieks"): w for w in woordenlijst if w.get("grieks")}
    try:
        twins = motor.laad_verwarparen_db().get(woord.get("grieks", "")) or []
    except Exception:                                            # noqa: BLE001
        twins = []
    for tg in twins:
        tw = index.get(tg)
        # Alleen twins die je al eens hebt gehad: een onbekend woord als afleider
        # leert je niets over het onderscheid.
        if tw and motor._is_al_geoefend(tw):
            voeg_toe(tw)
        if len(gekozen) >= 2:
            break

    lijkt_erop, zelfde_soort, rest = [], [], []
    for ander in woordenlijst:
        if ander is woord or not ander.get("grieks"):
            continue
        g_ander = motor.normaliseer_accent(ander.get("grieks", ""))
        if g_ander == doel:
            continue
        if ander.get("woordsoort") == soort:
            zelfde_soort.append(ander)
            if ((stamgok and len(stamgok) >= 3 and stamgok in g_ander)
                    or (prefix and g_ander.startswith(prefix)
                        and abs(len(g_ander) - len(doel)) <= 2)):
                lijkt_erop.append(ander)
        else:
            rest.append(ander)
    for groep in (lijkt_erop, zelfde_soort, rest):
        random.shuffle(groep)
        for ander in groep:
            if len(gekozen) >= hoeveel:
                break
            voeg_toe(ander)
        if len(gekozen) >= hoeveel:
            break
    return gekozen[:hoeveel], bron


def _ont_pct(g):
    """Accuratesse over alle ontleed-dimensies samen."""
    st = g.stats.get("ontleed_stats") or {}
    goed = sum(int(v.get("g", 0) or 0) for v in st.values() if isinstance(v, dict))
    fout = sum(int(v.get("f", 0) or 0) for v in st.values() if isinstance(v, dict))
    return f"{round(100 * goed / (goed + fout))}%" if goed + fout else "nieuw"


def _sw_pct(g):
    """Aandeel structuurwoorden met een streak van 5 of hoger."""
    w = sw_woorden(g)
    return round(100 * sum(1 for x in w if x["streak"] >= 5) / max(1, len(w)))


def _af_pct(g):
    """Aandeel cellen van Actief Beheersen dat je beheerst (streak 16 of hoger)."""
    cellen = af_cellen(g)
    if not cellen:
        return 0
    return round(100 * sum(1 for c in cellen if c["streak"] >= 16) / len(cellen))


@ui.page("/oefenen")
def oefenhub():
    """De lijst met onderdelen, gegroepeerd naar wat je ermee traint (designreview 1d)."""
    g = _bewaakt()
    if not g:
        return
    sam = g.samenvatting()
    stam_stats = g.stats.get("stam_stats") or {}
    stam_db = motor.laad_stamtijden_db()
    stam_klaar = sum(1 for s in motor.stam_level_status(motor.bouw_stam_levels(stam_db),
                                                        stam_stats) if s.get("voltooid"))
    groepen = [
        ("Woorden kennen", [
            ("Woordenschat", f"{round(100 * sam['geoefend'] / max(1, len(g.woorden)))}%",
             "/oefenen/woorden"),
            ("Structuurwoorden", f"{_sw_pct(g)}%", "/oefenen/structuur"),
        ]),
        ("Vormen beheersen", [
            ("Stamtijden", f"{round(100 * stam_klaar / max(1, len(stam_db)))}%",
             "/oefenen/stamtijden"),
            ("Actief beheersen", f"{_af_pct(g)}%", "/oefenen/actief"),
        ] + ([("Ontleden", _ont_pct(g), "/oefenen/ontleden")] if BIJBEL else [])),
    ]
    # Zonder de NT-tekst vervalt Ontleden; die staat dan bij wat in de volledige app zit.
    nog_niet = ["Klankwetten", "Nederlands → Grieks"] + ([] if BIJBEL else ["Ontleden"])

    with ui.column().classes("inhoud w-full gap-3"):
        ui.label("Oefenen").style("font-size:26px;font-weight:700")
        for kop, items in groepen:
            ui.label(kop).style(f"color:{ZACHT};font-size:13px;margin-top:6px")
            for naam, pct, pad in items:
                with ui.element("div").classes("kaart w-full").on(
                        "click", lambda p=pad: ui.navigate.to(p)):
                    with ui.row().classes("w-full items-center justify-between no-wrap"):
                        ui.label(naam).style(f"color:{TEKST};font-size:16px;font-weight:600")
                        with ui.row().classes("items-center gap-3 no-wrap"):
                            ui.label(pct).style(f"color:{MERK};font-size:14px")
                            ui.label("›").style(f"color:{ZACHT};font-size:20px")
        ui.label("In de volledige app").style(f"color:{ZACHT};font-size:13px;margin-top:10px")
        with ui.element("div").classes("kaart w-full"):
            ui.label(" · ".join(nog_niet)).style(
                f"color:{ZACHT};font-size:13px;line-height:1.6")
            ui.label("Deze onderdelen staan in de Streamlit-app.").style(
                f"color:{ZACHT};font-size:12px;margin-top:4px")
            streamlit_link(g, "Daarheen →")
    onderbalk("Oefenen")


def woord_instellingen(g):
    """De instellingen achter het tandwiel (designreview: niet vóór de oefening).
    Gedeeld door de kaartenronde en de paar-oefening; welke van de twee je krijgt hangt
    aan de gekozen oefening, dus dat bepaalt deze dialoog ook bij het toepassen."""
    with ui.dialog() as instellingen, ui.card().style(
            f"background:{VLAK};color:{TEKST};min-width:300px;max-width:92vw"):
        ui.label("Instellingen").style("font-size:18px;font-weight:700")
        p = prefs(g)
        alle_lessen = sorted({int(w["les"]) for w in g.woorden if w.get("les")})

        kies_oefening = ui.select(OEFENINGEN, value=p["keuze"], label="Oefening").props(
            "outlined dark").classes("w-full")
        ui.label("Gelijkende woorden en Mijn verwarwoorden lopen als paar-oefening: "
                 "twee lijkende woorden tegelijk.").style(
            f"color:{ZACHT};font-size:12px").bind_visibility_from(
            kies_oefening, "value", lambda v: v in PAAR_OEFENINGEN)
        kies_lessen = ui.select(alle_lessen, value=p["lessen"], label="Lessen",
                                multiple=True).props("outlined dark").classes("w-full")
        kies_lessen.bind_visibility_from(kies_oefening, "value",
                                         lambda v: v == "Losse lessen")
        # Levelkeuze: alleen de ontgrendelde levels, met hoever je bent erbij.
        _lv = motor.leerpad_status(motor.bouw_leerpad_levels(g.woorden))
        _open = {0: "Automatisch (volgend level)"}
        for _st in _lv:
            if _st.get("ontgrendeld"):
                # 'klaar' is het aantal woorden dat af is, 'totaal' hoeveel er in zitten.
                _open[_st["index"]] = (f"Level {_st['index']} · les {_st.get('les','?')} "
                                       f"({_st.get('klaar', 0)}/{_st.get('totaal', 0)})")
        _hl = int(p.get("level", 0) or 0)
        kies_level = ui.select(_open, value=_hl if _hl in _open else 0,
                               label="Level").props("outlined dark").classes("w-full")
        kies_level.bind_visibility_from(kies_oefening, "value",
                                        lambda v: v == "Leerpad (levels)")
        _hierna = next((s for s in _lv if not s.get("ontgrendeld")), None)
        if _hierna:
            ui.label(f"🔒 Hierna: level {_hierna['index']} · les "
                     f"{_hierna.get('les', '?')}").style(
                f"color:{ZACHT};font-size:12px").bind_visibility_from(
                kies_oefening, "value", lambda v: v == "Leerpad (levels)")
        _pad = ui.expansion("Toon het hele pad").props("dense").classes("w-full").style(
            f"color:{ZACHT};font-size:13px")
        _pad.bind_visibility_from(kies_oefening, "value", lambda v: v == "Leerpad (levels)")
        with _pad:
            ui.html("".join(
                f"<div style='font-size:12.5px;line-height:1.9;color:"
                f"{TEKST if s.get('ontgrendeld') else ZACHT}'>"
                f"{'✅' if s.get('voltooid') else ('▶️' if s.get('ontgrendeld') else '🔒')} "
                f"Level {s['index']} · les {s.get('les', '?')} — "
                f"{s.get('klaar', 0)}/{s.get('totaal', 0)}</div>" for s in _lv))
        kies_oude = ui.select(list(OUDE_STOF),
                              value=p.get("oude_stof", "Kleine herhaalronde (5)"),
                              label="Oude stof meenemen").props(
            "outlined dark").classes("w-full")
        kies_oude.bind_visibility_from(kies_oefening, "value",
                                       lambda v: v == "Leerpad (levels)")
        kies_nieuw_n = ui.number("Nieuwe woorden per sessie",
                                 value=int(p.get("nieuw_aantal", 3)), min=0, max=10,
                                 step=1).props("outlined dark").classes("w-full")
        kies_vorm = ui.select(VORMEN, value=p["vorm"], label="Oefenvorm").props(
            "outlined dark").classes("w-full")
        ui.label("Automatisch kiest per woord: een nieuw woord eerst als leerkaart, daarna "
                 "meerkeuze, en typen zodra het begint te zitten. Mix doet eerst de hele "
                 "ronde meerkeuze en daarna dezelfde woorden typen.").style(
            f"color:{ZACHT};font-size:12px")

        # --- sessie opbouw: de app weegt, jij zet een vast aantal, of jij vult per fase ---
        kies_stijl = ui.select(OPBOUW_STIJLEN, value=p["opbouw_stijl"],
                               label="Sessie opbouw").props("outlined dark").classes("w-full")
        ui.label("Automatisch weegt hoe zwaar je woorden nu zijn: staan er veel wankele "
                 "woorden klaar, dan wordt de ronde korter.").style(
            f"color:{ZACHT};font-size:12px").bind_visibility_from(
            kies_stijl, "value", lambda v: v == MIX)
        kies_aantal = ui.number("Kaarten per ronde", value=int(p["aantal"]),
                                min=4, max=40, step=1).props("outlined dark").classes("w-full")
        kies_aantal.bind_visibility_from(kies_stijl, "value", lambda v: v == VAST)
        eigen_vak = ui.column().classes("w-full gap-2")
        eigen_vak.bind_visibility_from(kies_stijl, "value", lambda v: v == ZELF)
        fase_velden = {}
        with eigen_vak:
            ui.label("Hoeveel woorden wil je per fase?").style(
                f"color:{ZACHT};font-size:12px")
            beschikbaar = ui.label().style(f"color:{ZACHT};font-size:12px")
            for sleutel, naam, bereik, _test in FASEN:
                fase_velden[sleutel] = ui.number(
                    f"{naam.capitalize()} (streak {bereik})", value=int(p.get(sleutel, 0) or 0),
                    min=0, max=40, step=1).props("outlined dark dense").classes("w-full")

        def tel_beschikbaar():
            """Wat er in de gekozen poule klaarstaat. Verandert mee met oefening en level,
            zodat de aantallen kloppen bij wat je op dat moment kiest."""
            poule = bouw_poule(g, kies_oefening.value, kies_lessen.value or [],
                               kies_level.value or 0) or g.woorden
            telling = fase_telling(poule)
            beschikbaar.text = "Beschikbaar: " + " · ".join(
                f"{naam} {telling[sleutel]}" for sleutel, naam, _b, _t in FASEN)

        for veld in (kies_oefening, kies_lessen, kies_level):
            veld.on_value_change(lambda _=None: tel_beschikbaar())
        tel_beschikbaar()

        kies_nieuw = ui.switch("Nieuwe woorden mee-oefenen", value=bool(p["nieuw_mee"]))
        kies_verwar = ui.switch("Verwarwoorden erbij trekken",
                                value=bool(p.get("verwar_mee", True)))
        kies_verwar_n = ui.number("Hoeveel verwarwoorden er hooguit bij mogen",
                                  value=int(p.get("verwar_max", 3) or 0), min=0, max=8,
                                  step=1).props("outlined dark dense").classes("w-full")
        kies_verwar_n.bind_visibility_from(kies_verwar, "value")
        ui.label("Heeft een gekozen woord een look-alike die je al eens deed, dan komt die "
                 "in dezelfde sessie mee — zo leer je ze onderscheiden. Nooit nieuwe woorden. "
                 "Het maximum geldt apart voor de look-alikes uit de woordenlijst en voor je "
                 "eigen verwarparen.").style(f"color:{ZACHT};font-size:12px")
        kies_audio = ui.switch("Uitspraakknop tonen", value=bool(p["audio"]))
        kies_opbouw = ui.switch("Woordopbouw tonen", value=bool(p["opbouw"]))
        kies_mv = ui.switch("Beheerste woorden als vorm uit de Bijbel",
                            value=bool(p.get("mastery_vormen", True)))
        ui.label(f"Bij streak {MASTERY_STREAK}+ krijg je een echte verbogen vorm uit "
                 f"het NT in plaats van de woordenboekvorm.").style(
            f"color:{ZACHT};font-size:12px")
        ui.label("Je keuzes worden bewaard bij je voortgang.").style(
            f"color:{ZACHT};font-size:12px")

        async def bewaar_instellingen():
            velden = [("keuze", kies_oefening), ("lessen", kies_lessen),
                      ("level", kies_level), ("oude_stof", kies_oude),
                      ("nieuw_aantal", kies_nieuw_n),
                      ("vorm", kies_vorm), ("aantal", kies_aantal),
                      ("opbouw_stijl", kies_stijl),
                      ("nieuw_mee", kies_nieuw), ("verwar_mee", kies_verwar),
                      ("verwar_max", kies_verwar_n),
                      ("audio", kies_audio), ("opbouw", kies_opbouw),
                      ("mastery_vormen", kies_mv)]
            for sleutel, veld in velden + list(fase_velden.items()):
                zet_pref(g, sleutel, veld.value)
            instellingen.close()
            await run.io_bound(g.bewaar, True)
            ui.navigate.to("/oefenen/paren" if kies_oefening.value in PAAR_OEFENINGEN
                           else "/oefenen/woorden")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Annuleren", on_click=instellingen.close).props("flat").style(
                f"color:{ZACHT}")
            ui.button("Toepassen", on_click=bewaar_instellingen).props("unelevated").style(
                f"background:{MERK};color:{INKT};font-weight:700")
    return instellingen


@ui.page("/oefenen/woorden")
def oefenpagina():
    g = _bewaakt()
    if not g:
        return
    if prefs(g)["keuze"] in PAAR_OEFENINGEN:
        ui.navigate.to("/oefenen/paren")
        return
    sessie = Sessie(g)
    instellingen = woord_instellingen(g)

    with ui.column().classes("inhoud metbalk w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label(sessie.prefs["keuze"]).style(f"color:{ZACHT};font-size:13px")
            with ui.row().classes("items-center gap-2 no-wrap"):
                teller = ui.label().style(f"color:{ZACHT};font-size:13px")
                ui.button("⚙", on_click=instellingen.open).props("flat dense").style(
                    f"color:{ZACHT};font-size:17px;min-width:32px")
        streepjes = ui.row().classes("w-full gap-1 no-wrap")
        _xp = motor.bereken_xp(g.woorden)
        _niv = motor.niveau_van_xp(_xp)
        _klaar = sum(1 for _s in motor.leerpad_status(
            motor.bouw_leerpad_levels(g.woorden)) if _s.get("voltooid"))
        ui.html(
            f"<div style='display:flex;justify-content:space-between;font-size:12px;"
            f"color:{ZACHT};padding-top:2px'>"
            f"<span>Niveau {_niv['niveau']} · <span style='color:{MERK}'>"
            f"{_niv['titel']}</span></span>"
            f"<span>{_klaar} levels af · nog "
            f"{_niv['xp_voor_volgend'] - _niv['xp_in_niveau']} XP</span></div>")
        if sessie.nieuw_over:
            ui.label(f"🌱 Nog {sessie.nieuw_over} nieuwe woorden in dit level voor een "
                     f"volgende ronde.").style(f"color:{ZACHT};font-size:12px")
        woord = ui.label().classes("grieks w-full text-center").style(
            f"font-size:58px;line-height:1.15;color:{TEKST};padding:18px 0 2px")
        lemma = ui.label().classes("w-full text-center").style(f"color:{ZACHT};font-size:14px")
        statusbalk = ui.row().classes("w-full gap-2 no-wrap justify-center").style("padding-top:2px")
        vraagsoort = ui.label().classes("w-full text-center").style(
            f"color:{ZACHT};font-size:12px")
        opties = ui.column().classes("w-full gap-2").style("padding-top:8px")
        terugkoppeling = ui.column().classes("w-full gap-1 items-center").style(
            "min-height:64px;padding-top:6px")
        hulp = ui.row().classes("w-full gap-2 no-wrap")
        opslagmelding = ui.label().style(f"color:{ZACHT};font-size:11.5px;min-height:16px")

    balk = ui.element("div").classes("antwoordbalk")
    with balk:
        with ui.row().classes("w-full gap-2 no-wrap items-center"):
            invoer = ui.input(placeholder="vertaling").props(
                "outlined dense dark autocomplete=off").classes("flex-grow")
            knop = ui.button("Nakijken").props("unelevated").style(
                f"background:{MERK};color:{INKT};font-weight:700;height:40px;min-width:108px")
        weetniet = ui.button("Ik weet het niet — toon het antwoord").props("flat dense").style(
            f"color:{ZACHT};width:100%;font-size:12px;margin-top:2px")
    onderbalk("Oefenen")

    # ---------------- hulpjes ----------------
    def teken_streepjes():
        """Eén streepje per kaart. De ronde kan groeien — een gemist woord komt terug —
        dus de streepjes lopen mee met de wachtrij."""
        streepjes.clear()
        totaal = min(40, max(1, sessie.totaal))
        with streepjes:
            for n in range(totaal):
                kleur = MERK if n < sessie.gedaan else (TEKST if n == sessie.gedaan else RAND)
                ui.element("div").style(f"flex:1;height:4px;border-radius:2px;background:{kleur}")

    def toon_hulp(soort, k):
        if soort == "Uitspraak":
            tekst = motor.fonetisch_uit_translit(k.get("fonetisch", "")) or k.get("fonetisch", "")
            spreek_uit(tekst)
        elif soort == "Hint":
            tekst = _hint(k)
        else:
            tekst = _opbouw_tekst(k, g.woorden)
        ui.notify(tekst, position="top", color="dark", multi_line=True,
                  classes="text-body2").style("max-width:88vw")

    def vier_fase(oud, nieuw, label):
        """Een schouderklopje als een woord een nieuwe fase in gaat."""
        for drempel, tekst in ((30, f"🏆 Mastery — {label} zit nu echt vast."),
                               (16, f"🎉 {label} is nu Beheerst."),
                               (1, f"🌱 {label} staat nu In training.")):
            if oud < drempel <= nieuw:
                ui.notify(tekst, position="top", color="dark")
                break

    def verwarregel(k):
        """Onder de feedback: met welke woorden zou je dit verward kunnen hebben."""
        lijkt = (sessie.kandidaten.get(k.get("grieks", "")) or {}).get("opties") or {}
        if not lijkt:
            return ""
        regels = " · ".join(f"<span class='grieks'>{cg}</span> ({cn[:26]})"
                            for cg, cn in list(lijkt.items())[:3])
        return (f"<div style='color:{ZACHT};font-size:12.5px;text-align:center;"
                f"line-height:1.5'>⚠ Lijkt op: {regels}<br>"
                f"Aan het eind van de ronde vink je zelf aan wat klopte.</div>")

    def melding(tekst, kleur):
        terugkoppeling.clear()
        with terugkoppeling:
            ui.html(f"<div style='background:{kleur}1a;border:1px solid {kleur}40;"
                    f"border-radius:12px;padding:10px 14px;text-align:center;width:100%;"
                    f"color:{TEKST};font-size:13.5px;line-height:1.6'>{tekst}</div>")

    async def opslaan(k, juist, punten=1, straf=None, scoor=True):
        opgeslagen = await run.io_bound(g.noteer, k, juist, punten, straf, scoor)
        if g.laatste_fout:
            opslagmelding.text = "⚠ Opslaan lukte niet — je voortgang staat nog in het geheugen."
            opslagmelding.style(f"color:{FOUT}")
        elif opgeslagen:
            opslagmelding.text = "Voortgang opgeslagen"
            opslagmelding.style(f"color:{ZACHT}")

    def ververs_kop(k):
        """Streak, goed/fout en het aantal kaarten lopen tijdens de beurt op; die cijfers
        moeten meteen kloppen, ook als je nog op dezelfde kaart blijft."""
        teken_status(k)
        teller.text = f"{sessie.gedaan + 1}/{sessie.totaal}"
        teken_streepjes()

    def kaart_afgerond():
        """Het antwoord staat vast: opties weg, alleen nog door naar de volgende."""
        opties.clear()
        sessie.beoordeeld = True
        invoer.set_visibility(False)
        weetniet.set_visibility(False)
        knop.set_visibility(True)
        knop.text = "Volgende"
        ververs_kop(sessie.woord)

    def volgende():
        sessie.gedaan += 1
        sessie.volgende()
        toon_kaart()

    # ---------------- een antwoord beoordelen ----------------
    async def beoordeel(k, vorm, antwoord, juist, bron=None):
        """Dezelfde regels als de Streamlit-app: de eerste misser kost je streak niets
        en je mag het nog eens proberen met een hint erbij; bij de tweede misser — of
        meteen als je het woord al beheerste — zakt de streak met twee en moet je het
        antwoord eerst overtikken voordat de kaart terugkomt."""
        grieks = k.get("grieks", "")
        # Alleen een vlekkeloze beurt levert punten op. Zag je het antwoord al (via
        # 'ik weet het niet' of een eerdere misser), dan telt de kaart niet meer mee.
        schoon = sessie.fouten == 0 and grieks not in sessie.gestraft

        if juist:
            sessie.goed += 1
            sessie.noteer_uitslag(k, True, antwoord, g.woorden)
            if sessie.fouten == 0:
                g.verzwak_verwarring(grieks)
            punten = STREAK_PUNTEN.get(vorm, 1)
            if vorm == "3_typ" and sessie.combo.get(grieks):
                punten *= 2              # meerkeuze én typen in één keer goed
            oud = int(k.get("streak", 0) or 0)
            await opslaan(k, True, punten=punten, scoor=schoon)
            if vorm == "3_mc":
                sessie.combo[grieks] = schoon
            extra = "" if schoon else (
                f"<div style='color:{ZACHT};font-size:12.5px;text-align:center'>"
                f"Geen streak-punten: je had het antwoord al gezien.</div>")
            terugkoppeling.clear()
            with terugkoppeling:
                ui.html(_feedbackblok(k, True, sessie, g.woorden))
                if extra:
                    ui.html(extra)
            vier_fase(oud, int(k.get("streak", 0) or 0), grieks)
            kaart_afgerond()
            return

        sessie.fout += 1
        sessie.fouten += 1
        sessie.noteer_uitslag(k, False, antwoord, g.woorden)
        if bron is not None:
            sessie.onthoud_kandidaat(k, antwoord, bron.get("grieks", ""),
                                     bron.get("nederlands", ""))
        if vorm == "3_mc":
            sessie.combo[grieks] = False
        # Een woord dat je al beheerste hoort er meteen uit te vallen; bij de rest krijg
        # je één herkansing voordat het streak-punten kost.
        echt_mis = int(k.get("streak", 0) or 0) >= STRAF_STREAK or sessie.fouten >= 2
        await opslaan(k, False, straf=STREAK_STRAF if echt_mis else None)

        if echt_mis:
            sessie.eerst_overtikken()
            terugkoppeling.clear()
            with terugkoppeling:
                ui.html(_feedbackblok(k, False, sessie, g.woorden))
                regel = verwarregel(k)
                if regel:
                    ui.html(regel)
                if bron is not None and bron.get("grieks"):
                    ui.html(f"<div style='color:{ZACHT};font-size:12.5px;text-align:center'>"
                            f"“{antwoord}” is de betekenis van "
                            f"<span class='grieks'>{bron['grieks']}</span>.</div>")
            kaart_afgerond()
            return

        # Bijna: het antwoord blijft verborgen, je krijgt de hint en nog een poging.
        ververs_kop(k)
        melding(f"Bijna — probeer het nog een keer.<br>"
                f"<span style='color:{MERK}'>💡 {_hint(k)}</span>", MERK)
        with terugkoppeling:
            if bron is not None and bron.get("grieks"):
                ui.html(f"<div style='color:{ZACHT};font-size:12.5px;text-align:center'>"
                        f"“{antwoord}” is de betekenis van "
                        f"<span class='grieks'>{bron['grieks']}</span>.</div>")
            # Ook bij de eerste misser al laten zien waarmee je het kunt verwarren —
            # dat is juist het moment waarop het onderscheid blijft hangen.
            regel = verwarregel(k)
            if regel:
                ui.html(regel)
        if vorm in ("4", "3_typ"):
            invoer.value = ""
            invoer.run_method("focus")

    async def kies(k, optie, bron):
        if sessie.bezig or sessie.beoordeeld:
            return
        sessie.bezig = True
        try:
            juist = (optie == k.get("nederlands", "")
                     or motor.zelfde_betekenis(optie, k.get("nederlands", "")))
            await beoordeel(k, sessie.vorm, optie, juist, None if juist else bron.get(optie))
        finally:
            sessie.bezig = False

    async def weet_niet():
        """Het antwoord tonen zonder aftrek. De kaart komt achteraan terug, maar levert
        dan geen volledige streak-punten meer op — je hebt hem immers al gezien."""
        k = sessie.woord
        if k is None or sessie.beoordeeld or sessie.bezig:
            return
        sessie.gestraft.add(k.get("grieks", ""))
        sessie.opnieuw_later()
        terugkoppeling.clear()
        with terugkoppeling:
            ui.html(_feedbackblok(k, True, sessie, g.woorden, kop="💡 Het antwoord"))
            ui.html(f"<div style='color:{ZACHT};font-size:12.5px;text-align:center'>"
                    f"Geen aftrek. Je krijgt dit woord straks nog een keer.</div>")
        kaart_afgerond()

    # ---------------- de vraagvormen ----------------
    def teken_status(k):
        """Zelfde gegevens als de caption in de Streamlit-app: fase, streak,
        goed/fout, laatst geoefend en hoeveel er nog te gaan zijn."""
        statusbalk.clear()
        if k is None:
            return
        fase = gebruikers.fase_van(k.get("streak", 0))
        vakjes = [
            (fase.replace("In training", "Training"), "fase",
             MERK if fase != "Nieuw" else ZACHT),
            (int(k.get("streak", 0) or 0), "streak", TEKST),
            (f"{int(k.get('score_goed', 0) or 0)}/{int(k.get('score_fout', 0) or 0)}",
             "goed/fout", TEKST),
            (_kort_datum(k.get("laatst_geoefend")), "laatst", ZACHT),
            (len(sessie.wachtrij), "te gaan", ZACHT),
        ]
        with statusbalk:
            ui.html(_statusrij(vakjes))

    def toon_kaart():
        for vak in (opties, terugkoppeling, hulp):
            vak.clear()
        k, vorm = sessie.woord, sessie.vorm
        balk.set_visibility(True)
        invoer.set_visibility(True)
        knop.set_visibility(True)
        weetniet.set_visibility(False)

        teken_status(k)
        if k is None:
            statusbalk.clear()
            woord.text = "✓"
            lemma.text = f"Klaar — {sessie.goed} goed, {sessie.fout} fout."
            vraagsoort.text = ""
            teller.text = ""
            invoer.set_visibility(False)
            knop.text = "Nieuwe ronde"
            teken_streepjes()
            with opties:
                toon_samenvatting()
            return

        # Beheers je dit woord, dan is de woordenboekvorm te makkelijk geworden:
        # toon een echte verbogen vorm uit het NT en laat de uitgang het werk doen.
        sessie.toonvorm = None
        if (sessie.prefs.get("mastery_vormen", True)
                and int(k.get("streak", 0) or 0) >= MASTERY_STREAK
                and vorm not in ("1", "overtik")):
            anders = [v for v in bijbelvormen(k)
                      if motor.normaliseer_accent(v["vorm"])
                      != motor.normaliseer_accent(k.get("grieks", ""))]
            if anders:
                sessie.toonvorm = random.choice(anders)
        woord.text = (sessie.toonvorm["vorm"] if sessie.toonvorm else k.get("grieks", ""))
        lemma.text = (f"vorm uit {sessie.toonvorm['ref']}" if sessie.toonvorm
                      else (k.get("grieks_info") or k.get("woordsoort", "")))
        teller.text = f"{sessie.gedaan + 1}/{sessie.totaal}"
        teken_streepjes()
        # Uitspraak en opbouw staan achter hun eigen schakelaar in de instellingen;
        # de hint is er altijd, want daar leun je juist op als je vastloopt.
        knoppen = ["Hint"]
        if sessie.prefs.get("audio", True):
            knoppen.insert(0, "Uitspraak")
        if sessie.prefs.get("opbouw", False):
            knoppen.append("Opbouw")
        with hulp:
            for label in knoppen:
                ui.button(label, on_click=lambda l=label, w=k: toon_hulp(l, w)).props(
                    "flat dense").style(
                    f"flex:1;color:{ZACHT};border:1px solid {RAND};border-radius:8px;font-size:12px")

        if vorm == "1":                                    # flashcard: eerst zien
            vraagsoort.text = "Nieuw woord — bekijk het even"
            with opties:
                ui.html(_leerkaart(k, g.woorden))
            invoer.set_visibility(False)
            knop.text = "Ik heb het bekeken"
            return

        if vorm == "overtik":                              # verankeren na een misser
            vraagsoort.text = "Typ het antwoord over — dit telt niet voor je streak"
            with opties:
                ui.html(f"<div style='text-align:center;color:{TEKST};font-size:17px;"
                        f"line-height:1.5'>{k.get('nederlands', '')}</div>")
            invoer.value = ""
            knop.text = "Bevestig"
            invoer.run_method("focus")
            return

        if vorm in ("2", "3_mc"):                          # meerkeuze
            vraagsoort.text = "Welke betekenis hoort hierbij?"
            invoer.set_visibility(False)
            knop.set_visibility(False)
            weetniet.set_visibility(True)
            keuzes, bron = afleiders(k, g.woorden)
            keuzes = keuzes + [k.get("nederlands", "")]
            random.shuffle(keuzes)
            with opties:
                for keuze in keuzes:
                    ui.html(f"<button class='keuze'>{keuze}</button>").on(
                        "click", lambda _=None, c=keuze, b=bron: kies(k, c, b))
            return

        vraagsoort.text = "Typ de betekenis"               # typen
        invoer.value = ""
        knop.text = "Nakijken"
        weetniet.set_visibility(True)
        invoer.run_method("focus")

    # ---------------- de eindsamenvatting ----------------
    def toon_samenvatting():
        """Wat ging goed, wat fout, en welke verwarring klopte écht. Dat laatste bevestig
        je zelf: meerdere woorden kunnen dezelfde Nederlandse betekenis hebben, dus
        automatisch toevoegen zou de lijst vervuilen."""
        goed_alleen = {gr: nl for gr, nl in sessie.gelukt.items() if gr not in sessie.mislukt}
        ui.html(_uitslaglijst(f"✓ Goed ({len(goed_alleen)})", GOED, [
            f"<span class='grieks'>{gr}</span> — {nl}" for gr, nl in goed_alleen.items()]))
        ui.html(_uitslaglijst(f"✗ Fout ({len(sessie.mislukt)})", FOUT, [
            f"<span class='grieks'>{gr}</span> — {d['nederlands']}"
            f"<span style='color:{ZACHT}'> (jij: {d['antwoord'] or '—'})</span>"
            for gr, d in sessie.mislukt.items()]))
        if not sessie.kandidaten:
            return
        vinkjes = {}
        with ui.element("div").classes("kaart w-full"):
            ui.label("Mogelijk verward").style(
                f"color:{TEKST};font-size:15px;font-weight:600")
            ui.label("Vaak hebben meerdere woorden dezelfde betekenis. Vink alleen aan met "
                     "welk woord je het écht door elkaar haalde — één, meer of geen.").style(
                f"color:{ZACHT};font-size:12.5px;line-height:1.5")
            for grieks, d in sessie.kandidaten.items():
                ui.html(f"<div style='margin-top:10px;font-size:13.5px;color:{TEKST}'>"
                        f"<span class='grieks' style='font-size:17px'>{grieks}</span> "
                        f"({d['nederlands']}) — jij gaf: <i>{d['antwoord'] or '—'}</i></div>")
                for cg, cn in d["opties"].items():
                    vinkjes[(grieks, cg)] = ui.checkbox(f"{cg} ({cn[:34]})").props(
                        "dense dark").classes("w-full").style("font-size:13.5px")

            async def bevestig():
                aantal = 0
                for (getoond, verward), vink in vinkjes.items():
                    if vink.value:
                        g.registreer_verwarring(getoond, verward)
                        aantal += 1
                sessie.kandidaten.clear()
                await run.io_bound(g.bewaar, True)
                ui.notify(f"{aantal} verwarpaar toegevoegd" if aantal == 1 else
                          (f"{aantal} verwarparen toegevoegd" if aantal else "Niets toegevoegd"),
                          position="top", color="dark")
                toon_kaart()

            ui.button("Toevoegen aan mijn verwarwoorden", on_click=bevestig).props(
                "unelevated").style(f"background:{MERK};color:{INKT};font-weight:700;"
                                    f"margin-top:10px;width:100%")

    async def hoofdknop():
        # Eén beurt tegelijk: tijdens het opslaan duurt een beurt even, en een tweede
        # klik of Enter zou anders de feedback meteen wegklikken.
        if sessie.bezig:
            return
        sessie.bezig = True
        try:
            k, vorm = sessie.woord, sessie.vorm
            if k is None:
                await run.io_bound(g.bewaar, True)
                ui.navigate.to("/oefenen/woorden")
                return
            if sessie.beoordeeld:
                volgende()
                return
            if vorm == "1":                                # flashcard: alleen bekeken
                await opslaan(k, True, punten=0, scoor=False)
                volgende()
                return
            if vorm == "overtik":
                if motor.check_betekenis(invoer.value or "", k.get("nederlands", "")):
                    await opslaan(k, True, punten=0, scoor=False)
                    volgende()
                    melding("Genoteerd — dit woord komt straks nog terug.", MERK)
                else:
                    melding("Nog niet exact overgetypt — kijk goed naar de betekenis.", FOUT)
                    invoer.value = ""
                    invoer.run_method("focus")
                return
            if vorm in ("2", "3_mc"):                      # daar klik je een optie aan
                return
            gegeven = invoer.value or ""
            await beoordeel(k, vorm, gegeven,
                            bool(motor.check_betekenis(gegeven, k.get("nederlands", ""))))
        finally:
            sessie.bezig = False

    knop.on_click(hoofdknop)
    weetniet.on_click(weet_niet)
    invoer.on("keydown.enter", hoofdknop)
    toon_kaart()


# ============================================================== paar-oefening
class PaarSessie:
    """Twee lijkende woorden tegelijk, van allebei de betekenis. Een deel dat al goed is
    hoef je niet opnieuw in te vullen; het paar telt pas als ze allebei kloppen."""

    def __init__(self, g):
        self.prefs = prefs(g)
        db = motor.laad_verwarparen_db()
        if self.prefs["keuze"] == "Mijn verwarwoorden":
            paren = motor.bouw_verwar_paren(g.woorden, g.stats.get("verwar_stats") or {})
        else:
            poule = motor.verzamel_lookalikes(g.woorden, db, alleen_geoefend=True)
            paren = motor.bouw_lookalike_paren(poule, db)
        random.shuffle(paren)
        self.paren = list(paren)
        self.huidig = self.paren.pop(0) if self.paren else None
        self.leeg = self.huidig is None
        self.opgelost = {"A": False, "B": False}
        self.fout = 0
        self.overtik = False
        self.af = 0

    def volgend_paar(self, opnieuw=None):
        """Naar het volgende paar. 'opnieuw' komt achteraan terug — eerst pakken, dan
        aanschuiven, anders krijg je bij het laatste paar eindeloos hetzelfde terug."""
        volgende = self.paren.pop(0) if self.paren else None
        if opnieuw:
            self.paren.append(opnieuw)
        self.huidig = volgende
        self.opgelost = {"A": False, "B": False}
        self.fout = 0
        self.overtik = False


def _paar_scoor(w, goed):
    """Score van één woord binnen de paar-oefening. Een misser telt wel als fout maar wist
    de streak níét: dit is een onderscheid-oefening, geen gewone overhoring. Het meetellen
    voor je oefenritme gebeurt apart, want dat geldt voor elke inzending."""
    if goed:
        w["streak"] = int(w.get("streak", 0)) + 1
        w["score_goed"] = int(w.get("score_goed", 0)) + 1
    else:
        w["score_fout"] = int(w.get("score_fout", 0)) + 1
        w["laatst_fout"] = gebruikers.vandaag()


@ui.page("/oefenen/paren")
def paarpagina():
    g = _bewaakt()
    if not g:
        return
    if prefs(g)["keuze"] not in PAAR_OEFENINGEN:
        ui.navigate.to("/oefenen/woorden")
        return
    sessie = PaarSessie(g)
    instellingen = woord_instellingen(g)

    with ui.column().classes("inhoud metbalk w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label(sessie.prefs["keuze"]).style(f"color:{ZACHT};font-size:13px")
            with ui.row().classes("items-center gap-2 no-wrap"):
                teller = ui.label().style(f"color:{ZACHT};font-size:13px")
                ui.button("⚙", on_click=instellingen.open).props("flat dense").style(
                    f"color:{ZACHT};font-size:17px;min-width:32px")
        woorden = ui.row().classes("w-full no-wrap items-start").style("padding:12px 0 2px")
        vraagsoort = ui.label().classes("w-full text-center").style(
            f"color:{ZACHT};font-size:12px")
        velden = ui.column().classes("w-full gap-2").style("padding-top:8px")
        terugkoppeling = ui.column().classes("w-full gap-1 items-center").style(
            "min-height:40px;padding-top:6px")
        opslagmelding = ui.label().style(f"color:{ZACHT};font-size:11.5px;min-height:16px")

    balk = ui.element("div").classes("antwoordbalk")
    with balk:
        knop = ui.button("Nakijken").props("unelevated").style(
            f"background:{MERK};color:{INKT};font-weight:700;height:40px;width:100%")
        stopknop = ui.button("Stop deze ronde").props("flat dense").style(
            f"color:{ZACHT};width:100%;font-size:12px;margin-top:2px")
    onderbalk("Oefenen")

    invoervelden = {}

    def melding(tekst, kleur):
        terugkoppeling.clear()
        with terugkoppeling:
            ui.html(f"<div style='background:{kleur}1a;border:1px solid {kleur}40;"
                    f"border-radius:12px;padding:10px 14px;text-align:center;width:100%;"
                    f"color:{TEKST};font-size:13.5px;line-height:1.6'>{tekst}</div>")

    def toon_paar(bericht=None, kleur=None):
        woorden.clear()
        velden.clear()
        invoervelden.clear()
        if bericht:
            melding(bericht, kleur or GOED)
        else:
            terugkoppeling.clear()
        stopknop.set_visibility(sessie.huidig is not None)
        if sessie.huidig is None:
            teller.text = ""
            vraagsoort.text = ""
            with woorden:
                ui.label("✓" if not sessie.leeg else "—").classes("w-full text-center").style(
                    f"font-size:46px;color:{GOED if not sessie.leeg else ZACHT}")
            with velden:
                if sessie.leeg:
                    ui.html(
                        f"<div style='text-align:center;color:{TEKST};font-size:15px;"
                        f"line-height:1.6'>Nog geen paren om te oefenen.<br>"
                        f"<span style='color:{ZACHT};font-size:13px'>Verwarparen ontstaan "
                        f"als je in een ronde twee woorden door elkaar haalt en dat in de "
                        f"eindsamenvatting bevestigt.</span></div>")

                    async def naar_kaarten():
                        zet_pref(g, "keuze", "Leerpad (levels)")
                        await run.io_bound(g.bewaar, True)
                        ui.navigate.to("/oefenen/woorden")

                    ui.button("Doe dan een gewone ronde", on_click=naar_kaarten).props(
                        "unelevated").style(f"background:{MERK};color:{INKT};"
                                            f"font-weight:700;width:100%;margin-top:10px")
                else:
                    ui.html(
                        f"<div style='text-align:center;color:{TEKST};font-size:15px;"
                        f"line-height:1.6'>Verwarparen afgerond — {sessie.af} paar in één "
                        f"keer goed.<br><span style='color:{ZACHT};font-size:13px'>Paren die "
                        f"je weer beheerst verdwijnen vanzelf uit je lijst.</span></div>")
            knop.text = "Nieuwe ronde"
            return

        wa, wb = sessie.huidig
        teller.text = f"nog {len(sessie.paren) + 1}"
        with woorden:
            for w in (wa, wb):
                ui.label(w.get("grieks", "")).classes("grieks text-center").style(
                    f"flex:1;min-width:0;font-size:34px;line-height:1.2;color:{TEKST}")
        if sessie.overtik:
            vraagsoort.text = "Overtikken — dit telt niet voor je streak"
            with velden:
                for kant, w in (("A", wa), ("B", wb)):
                    ui.html(f"<div style='color:{ZACHT};font-size:13px'>"
                            f"<span class='grieks' style='font-size:16px;color:{TEKST}'>"
                            f"{w.get('grieks','')}</span> = {w.get('nederlands','')}</div>")
                    invoervelden[kant] = ui.input(placeholder="typ over").props(
                        "outlined dense dark autocomplete=off").classes("w-full").on(
                        "keydown.enter", nakijken)
            knop.text = "Bevestig"
            return

        vraagsoort.text = "Geef van allebei de betekenis"
        with velden:
            for kant, w in (("A", wa), ("B", wb)):
                if sessie.opgelost[kant]:
                    ui.html(f"<div style='color:{GOED};font-size:13.5px'>✓ "
                            f"<span class='grieks' style='font-size:16px'>"
                            f"{w.get('grieks','')}</span> = {w.get('nederlands','')}</div>")
                    continue
                invoervelden[kant] = ui.input(
                    label=f"betekenis van {w.get('grieks','')}").props(
                    "outlined dense dark autocomplete=off").classes("w-full").on(
                    "keydown.enter", nakijken)
                # Pas na een misser hulp erbij: anders geef je het antwoord te snel weg.
                if sessie.fout >= 1:
                    tip = _hint(w)
                    if tip:
                        ui.label(f"💡 {tip}").style(f"color:{ZACHT};font-size:12px")
        knop.text = "Nakijken"
        if invoervelden:
            list(invoervelden.values())[0].run_method("focus")

    async def bewaar_stil():
        opgeslagen = await run.io_bound(g.bewaar, True)
        if g.laatste_fout:
            opslagmelding.text = "⚠ Opslaan lukte niet — je voortgang staat nog in het geheugen."
            opslagmelding.style(f"color:{FOUT}")
        elif opgeslagen:
            opslagmelding.text = "Voortgang opgeslagen"
            opslagmelding.style(f"color:{ZACHT}")

    async def nakijken():
        if sessie.huidig is None:
            ui.navigate.to("/oefenen/paren")
            return
        wa, wb = sessie.huidig
        gegeven = {kant: (veld.value or "") for kant, veld in invoervelden.items()}

        # Elke inzending telt voor allebei de woorden mee in je oefenritme, en stempelt
        # de datum. Anders zou een paar dat je pas na een misser goed krijgt eeuwig als
        # 'lang niet gedaan' bovenaan blijven staan.
        for w in (wa, wb):
            g.tel_dag(w)

        if sessie.overtik:
            if all(motor.check_betekenis(gegeven.get(kant, ""), w.get("nederlands", ""))
                   for kant, w in (("A", wa), ("B", wb))):
                sessie.volgend_paar(opnieuw=(wa, wb))
                await bewaar_stil()
                toon_paar("Genoteerd — dit paar komt straks nog terug.", MERK)
            else:
                toon_paar("Nog niet exact overgetypt — kijk goed naar de betekenissen.", FOUT)
            return

        misser = False
        for kant, w in (("A", wa), ("B", wb)):
            if sessie.opgelost[kant]:
                continue
            if motor.check_betekenis(gegeven.get(kant, ""), w.get("nederlands", "")):
                sessie.opgelost[kant] = True
            else:
                misser = True
                _paar_scoor(w, False)
        if misser:
            sessie.fout += 1

        if all(sessie.opgelost.values()):
            if sessie.fout == 0:
                for w in (wa, wb):
                    _paar_scoor(w, True)
                    g.verzwak_verwarring(w.get("grieks", ""))
                sessie.af += 1
                g.dagdoel_plus("verwar")
            uitslag = (f"✓ Allebei goed! <span class='grieks'>{wa.get('grieks','')}</span> = "
                       f"{wa.get('nederlands','')} · <span class='grieks'>"
                       f"{wb.get('grieks','')}</span> = {wb.get('nederlands','')}")
            sessie.volgend_paar()
            await bewaar_stil()
            toon_paar(uitslag, GOED)
            return

        if sessie.fout >= 2:
            # Twee keer mis: eerst verankeren door over te tikken, daarna komt het terug.
            sessie.overtik = True
            await bewaar_stil()
            toon_paar("Twee keer mis — typ de betekenissen even over.", FOUT)
            return

        nog = ", ".join(w.get("grieks", "") for kant, w in (("A", wa), ("B", wb))
                        if not sessie.opgelost[kant])
        await bewaar_stil()
        toon_paar(f"Nog te doen: {nog} — bekijk de hint.", MERK)

    async def stoppen():
        """Ronde afbreken. De half-opgeloste staat gaat mee weg, anders levert dezelfde
        kaart bij een herstart gratis streak op voor de helft die al goed stond."""
        sessie.paren = []
        sessie.huidig = None
        sessie.opgelost = {"A": False, "B": False}
        sessie.fout = 0
        sessie.overtik = False
        await run.io_bound(g.bewaar, True)
        toon_paar()

    knop.on_click(nakijken)
    stopknop.on_click(stoppen)
    toon_paar()


# ============================================================== Grieks typen
# Welke Latijnse toets welke Griekse letter geeft. motor.naar_grieks_transliteratie
# rekent je invoer hiermee om, dus dit is de sleutel bij elke vraag waar je Grieks typt.
GRIEKSE_TOETSEN = [
    ("Klinkers", [("a", "α"), ("e", "ε"), ("h", "η"), ("i", "ι"),
                  ("o", "ο"), ("u", "υ"), ("w", "ω")]),
    ("Medeklinkers", [("b", "β"), ("g", "γ"), ("d", "δ"), ("z", "ζ"), ("k", "κ"),
                      ("l", "λ"), ("m", "μ"), ("n", "ν"), ("p", "π"), ("r", "ρ"),
                      ("t", "τ")]),
    ("Bèta-code", [("q", "θ"), ("c", "ξ"), ("f", "φ"), ("x", "χ"), ("y", "ψ"),
                   ("s", "σ · aan het eind ς")]),
]


def spiekbrief():
    """Dialoog met de toetsaanslagen voor Griekse letters. Geeft de dialoog terug, zodat
    elke pagina waar je Grieks typt er een knopje voor kan neerzetten."""
    with ui.dialog() as venster, ui.card().style(
            f"background:{VLAK};color:{TEKST};min-width:290px;max-width:92vw"):
        ui.label("Grieks typen met een gewoon toetsenbord").style(
            "font-size:17px;font-weight:700")
        ui.label("Typ de Latijnse letter; de app maakt er de Griekse van. Accenten en "
                 "spiritus hoef je niet mee te typen.").style(
            f"color:{ZACHT};font-size:12.5px;line-height:1.5")
        for kop, paren in GRIEKSE_TOETSEN:
            ui.label(kop).style(f"color:{MERK};font-size:13px;font-weight:600;margin-top:8px")
            ui.html("<div style='display:grid;grid-template-columns:repeat(auto-fill,"
                    "minmax(96px,1fr));gap:4px'>" + "".join(
                        f"<div style='font-size:13.5px;color:{TEKST}'>"
                        f"<code style='background:{RAND};border-radius:4px;padding:1px 5px'>"
                        f"{toets}</code> = <span class='grieks' style='font-size:17px'>"
                        f"{letter}</span></div>" for toets, letter in paren) + "</div>")
        ui.button("Sluiten", on_click=venster.close).props("flat").style(
            f"color:{MERK};margin-top:10px;width:100%")
    return venster


def spiekknop(venster):
    """Het toetsenbord-knopje in de kop van een oefenpagina."""
    return ui.button("⌨", on_click=venster.open).props("flat dense").style(
        f"color:{ZACHT};font-size:16px;min-width:30px")


# ============================================================== stamtijden
TIJD_KORT = {"Futurum Actief/Medium": "futurum", "Aoristus Actief/Medium": "aoristus",
             "Aoristus Passief": "aoristus passief", "Perfectum Actief": "perfectum",
             "Perfectum Medium/Passief": "perfectum med./pass."}
TIJDEN = list(TIJD_KORT)

STAM_OEFENINGEN = ["Zwakste eerst", "Leerpad (per werkwoord)", "Meest voorkomend",
                   "Alleen wat ik fout deed"]
STAM_VRAAGVORM = ["Automatisch (aanbevolen)", "Alleen de tijd", "Tijd en werkwoord"]
STAM_MODI = ["Overhoren", "Leren (flashcards)"]
STAM_BRONNEN = ["Alle werkwoorden", "Losse lessen", "Uit een Bijbeltekst"]
STAM_STANDAARD = {"stam_keuze": "Zwakste eerst", "stam_aantal": 10,
                  "stam_vraagvorm": STAM_VRAAGVORM[0], "stam_kleur": True,
                  "stam_modus": STAM_MODI[0], "stam_bron": STAM_BRONNEN[0],
                  "stam_lessen": [], "stam_boek": "", "stam_hoofdstuk": ""}
STAM_TYP_STREAK = 10       # vanaf hier ook het werkwoord laten typen


def stam_prefs(g):
    return {k: (g.stats.get("ui_prefs") or {}).get(f"ng_{k}", v)
            for k, v in STAM_STANDAARD.items()}


def stam_bijbelboeken():
    """boek -> [hoofdstukken], uit de vers-referenties van het NT."""
    if not BIJBEL:
        return {}
    try:
        return {boek: sorted(hfd, key=lambda h: int(h) if str(h).isdigit() else 0)
                for boek, hfd in motor.bijbel_boek_index(motor.laad_bijbel_db()).items()}
    except Exception:                                            # noqa: BLE001
        return {}


def stam_strongs_in_tekst(boek, hoofdstuk):
    """Welke Strong-nummers er in dit hoofdstuk voorkomen — de filter voor 'oefen de
    werkwoorden die je in deze tekst tegenkomt'."""
    if not boek or not hoofdstuk:
        return set()
    try:
        db = motor.laad_bijbel_db()
    except Exception:                                            # noqa: BLE001
        return set()
    begin = f"{boek} {hoofdstuk}:"
    uit = set()
    for ref, zin in db.items():
        if ref.startswith(begin):
            for w in zin:
                if w.get("strong"):
                    uit.add(str(w["strong"]).lstrip("G").strip())
    return uit


def stam_poule(p):
    """De werkwoorden waaruit een stamtijden-ronde wordt getrokken."""
    db = motor.laad_stamtijden_db() or []
    bron = p.get("stam_bron", STAM_BRONNEN[0])
    if bron == "Losse lessen" and p.get("stam_lessen"):
        return [w for w in db if w.get("les") in p["stam_lessen"]] or db
    if bron == "Uit een Bijbeltekst":
        strongs = stam_strongs_in_tekst(p.get("stam_boek"), p.get("stam_hoofdstuk"))
        gevonden = [w for w in db
                    if str(w.get("strong_nummer", "")).lstrip("G").strip() in strongs]
        return gevonden or db
    return db


def stam_vraagt_praesens(vraagvorm, streak):
    """Bij een lage streak eerst alleen de tijd aanwijzen; het werkwoord erbij typen
    komt pas als de vorm begint te zitten. Zelfde gedachte als leerpad_kaart_volgorde
    bij de woordenschat."""
    if vraagvorm == "Alleen de tijd":
        return False
    if vraagvorm == "Tijd en werkwoord":
        return True
    return int(streak or 0) >= STAM_TYP_STREAK


class StamSessie:
    """Herkenrichting: je ziet een vorm en benoemt welke tijd het is en van welk
    werkwoord. Het zelf maken van vormen hoort bij Actief Beheersen."""

    def __init__(self, g):
        p = stam_prefs(g)
        db = stam_poule(p)
        stats = g.stats.get("stam_stats") or {}
        vragen = []
        for verb in db:
            praesens = verb.get("praesens", "")
            for tijd, vorm in (verb.get("stamtijden") or {}).items():
                if not motor._stam_vorm_ok(vorm):
                    continue
                sleutel = f"{praesens}_{vorm}"
                s = stats.get(sleutel) or {}
                vragen.append({"verb": verb, "praesens": praesens, "tijd": tijd,
                               "vorm": vorm, "sleutel": sleutel,
                               "streak": int(s.get("streak", 0) or 0),
                               "goed": int(s.get("g", 0) or 0),
                               "fout": int(s.get("f", 0) or 0)})
        keuze = p["stam_keuze"]
        if keuze == "Meest voorkomend":
            vragen.sort(key=lambda v: -int(v["verb"].get("frequentie", 0) or 0))
        elif keuze == "Alleen wat ik fout deed":
            vragen = [v for v in vragen if v["fout"] > 0] or vragen
            vragen.sort(key=lambda v: -v["fout"])
        elif keuze == "Leerpad (per werkwoord)":
            per = {}
            for v in vragen:
                per.setdefault(v["praesens"], []).append(v)
            for _pr, groep in per.items():
                if any(x["streak"] < 5 for x in groep):
                    vragen = groep
                    break
        else:
            vragen.sort(key=lambda v: (v["streak"],
                                       -int(v["verb"].get("frequentie", 0) or 0)))
        self.prefs = p
        self.vragen = vragen[:int(p["stam_aantal"])]
        self.i = 0
        self.goed = 0
        self.fout = 0
        self.beoordeeld = False
        self.tijd_keuze = None
        self.vraag_praesens = True
        self.bezig = False

    @property
    def huidig(self):
        return self.vragen[self.i] if self.i < len(self.vragen) else None


@ui.page("/oefenen/stamtijden")
def stampagina():
    g = _bewaakt()
    if not g:
        return
    if stam_prefs(g).get("stam_modus") == STAM_MODI[1]:
        ui.navigate.to("/oefenen/stamtijden/leren")
        return
    sessie = StamSessie(g)
    stats = g.stats.setdefault("stam_stats", {})
    spiek = spiekbrief()

    with ui.dialog() as instellingen, ui.card().style(
            f"background:{VLAK};color:{TEKST};min-width:300px;max-width:92vw"):
        ui.label("Instellingen").style("font-size:18px;font-weight:700")
        _mo = sessie.prefs.get("stam_modus", STAM_MODI[0])
        kies_modus = ui.select(STAM_MODI, value=_mo if _mo in STAM_MODI else STAM_MODI[0],
                               label="Wat wil je doen").props(
            "outlined dark").classes("w-full")
        ui.label("Leren toont de vorm met het antwoord erbij: je kijkt zelf of je het "
                 "wist. Overhoren stelt echte vragen en telt mee voor je streak.").style(
            f"color:{ZACHT};font-size:12px")
        kies_oef = ui.select(STAM_OEFENINGEN, value=sessie.prefs["stam_keuze"],
                             label="Oefening").props("outlined dark").classes("w-full")

        # --- waar de vormen vandaan komen ---
        # Zonder de NT-tekst valt het filter op een bijbelhoofdstuk weg.
        _bronnen = STAM_BRONNEN if BIJBEL else STAM_BRONNEN[:2]
        _br = sessie.prefs.get("stam_bron", _bronnen[0])
        kies_bron = ui.select(_bronnen, value=_br if _br in _bronnen else _bronnen[0],
                              label="Welke werkwoorden").props(
            "outlined dark").classes("w-full")
        _lessen = sorted({int(w["les"]) for w in (motor.laad_stamtijden_db() or [])
                          if w.get("les")})
        kies_lessen = ui.select(_lessen, value=list(sessie.prefs.get("stam_lessen") or []),
                                label="Lessen", multiple=True).props(
            "outlined dark").classes("w-full")
        kies_lessen.bind_visibility_from(kies_bron, "value", lambda v: v == "Losse lessen")
        _boeken = stam_bijbelboeken()
        _boeknamen = sorted(_boeken)
        _hb = sessie.prefs.get("stam_boek") or (_boeknamen[0] if _boeknamen else "")
        kies_boek = ui.select(_boeknamen, value=_hb if _hb in _boeken else
                              (_boeknamen[0] if _boeknamen else None),
                              label="Bijbelboek").props("outlined dark").classes("w-full")
        kies_hfd = ui.select(_boeken.get(kies_boek.value or "", []),
                             value=sessie.prefs.get("stam_hoofdstuk") or None,
                             label="Hoofdstuk").props("outlined dark").classes("w-full")
        for veld in (kies_boek, kies_hfd):
            veld.bind_visibility_from(kies_bron, "value",
                                      lambda v: v == "Uit een Bijbeltekst")
        _telling = ui.label().style(f"color:{ZACHT};font-size:12px")
        _telling.bind_visibility_from(kies_bron, "value",
                                      lambda v: v == "Uit een Bijbeltekst")

        def bij_boek():
            """Hoofdstukken horen bij het gekozen boek; die lijst moet dus meeveranderen."""
            hfd = _boeken.get(kies_boek.value or "", [])
            kies_hfd.set_options(hfd, value=hfd[0] if hfd else None)
            tel_werkwoorden()

        def tel_werkwoorden():
            gevonden = stam_poule({**sessie.prefs, "stam_bron": "Uit een Bijbeltekst",
                                   "stam_boek": kies_boek.value,
                                   "stam_hoofdstuk": kies_hfd.value})
            _telling.text = f"{len(gevonden)} werkwoorden uit deze tekst in de stamtijdenlijst."

        kies_boek.on_value_change(lambda _=None: bij_boek())
        kies_hfd.on_value_change(lambda _=None: tel_werkwoorden())
        tel_werkwoorden()

        kies_aantal = ui.number("Vormen per ronde", value=int(sessie.prefs["stam_aantal"]),
                                min=4, max=40, step=1).props("outlined dark").classes("w-full")
        _hv = sessie.prefs["stam_vraagvorm"]
        kies_praesens = ui.select(
            STAM_VRAAGVORM, value=_hv if _hv in STAM_VRAAGVORM else STAM_VRAAGVORM[0],
            label="Wat wordt gevraagd").props("outlined dark").classes("w-full")
        ui.label(f"Automatisch: eerst alleen de tijd aanwijzen, en vanaf streak "
                 f"{STAM_TYP_STREAK} ook het werkwoord erbij typen.").style(
            f"color:{ZACHT};font-size:12px")
        kies_kleur = ui.switch("Uitgangen kleuren",
                               value=bool(sessie.prefs.get("stam_kleur", True)))
        ui.label("Toont in het antwoord welk deel de stam is en welk deel de uitgang.").style(
            f"color:{ZACHT};font-size:12px")

        async def bewaar_inst():
            for sleutel, veld in [("stam_keuze", kies_oef), ("stam_aantal", kies_aantal),
                                  ("stam_vraagvorm", kies_praesens),
                                  ("stam_kleur", kies_kleur), ("stam_modus", kies_modus),
                                  ("stam_bron", kies_bron), ("stam_lessen", kies_lessen),
                                  ("stam_boek", kies_boek), ("stam_hoofdstuk", kies_hfd)]:
                g.stats.setdefault("ui_prefs", {})[f"ng_{sleutel}"] = veld.value
            instellingen.close()
            await run.io_bound(g.bewaar, True)
            ui.navigate.to("/oefenen/stamtijden")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Annuleren", on_click=instellingen.close).props("flat").style(
                f"color:{ZACHT}")
            ui.button("Toepassen", on_click=bewaar_inst).props("unelevated").style(
                f"background:{MERK};color:{INKT};font-weight:700")

    with ui.column().classes("inhoud metbalk w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label(f"Stamtijden · {sessie.prefs['stam_keuze']}").style(
                f"color:{ZACHT};font-size:13px")
            with ui.row().classes("items-center gap-2 no-wrap"):
                teller = ui.label().style(f"color:{ZACHT};font-size:13px")
                spiekknop(spiek)
                ui.button("⚙", on_click=instellingen.open).props("flat dense").style(
                    f"color:{ZACHT};font-size:17px;min-width:32px")
        streepjes = ui.row().classes("w-full gap-1 no-wrap")
        vormlabel = ui.label().classes("grieks w-full text-center").style(
            f"font-size:52px;line-height:1.15;color:{TEKST};padding:16px 0 2px")
        vraagsoort = ui.label().classes("w-full text-center").style(
            f"color:{ZACHT};font-size:13px")
        tijdknoppen = ui.column().classes("w-full gap-2").style("padding-top:8px")
        statusbalk = ui.row().classes("w-full").style("padding-top:6px")
        terugkoppeling = ui.column().classes("w-full items-center justify-center").style(
            "min-height:64px;padding-top:8px")
        opslagmelding = ui.label().style(f"color:{ZACHT};font-size:11.5px;min-height:16px")

    with ui.element("div").classes("antwoordbalk"):
        with ui.row().classes("w-full gap-2 no-wrap items-center"):
            invoer = ui.input(placeholder="van welk werkwoord? (x = χ, u = υ, h = η)").props(
                "outlined dense dark autocomplete=off").classes("flex-grow")
            knop = ui.button("Nakijken").props("unelevated").style(
                f"background:{MERK};color:{INKT};font-weight:700;height:40px;min-width:108px")
    onderbalk("Oefenen")

    def teken():
        streepjes.clear()
        with streepjes:
            for n in range(len(sessie.vragen)):
                kleur = MERK if n < sessie.i else (TEKST if n == sessie.i else RAND)
                ui.element("div").style(f"flex:1;height:4px;border-radius:2px;background:{kleur}")

    def teken_tijden():
        """Twee kolommen: vijf knoppen onder elkaar maakt het scherm te lang om de
        vraag en het antwoord zonder scrollen te kunnen zien."""
        tijdknoppen.clear()
        with tijdknoppen:
            for rij in (TIJDEN[:2], TIJDEN[2:4], TIJDEN[4:]):
                with ui.row().classes("w-full gap-2 no-wrap"):
                    for t in rij:
                        gekozen = sessie.tijd_keuze == t
                        rand = MERK if gekozen else RAND
                        achter = "rgba(51,204,255,.12)" if gekozen else VLAK
                        ui.html(f"<button class='keuze' style='background:{achter};"
                                f"border-color:{rand};font-size:14px;text-align:center;"
                                f"padding:11px 6px'>{TIJD_KORT[t]}</button>").on(
                            "click", lambda _=None, tt=t: kies_tijd(tt)).style("flex:1")

    def kies_tijd(t):
        if sessie.beoordeeld:
            return
        sessie.tijd_keuze = t
        teken_tijden()
        # Meteen door naar het typveld: anders moet je daar nog een keer op tikken.
        if sessie.vraag_praesens:
            invoer.run_method("focus")

    def toon():
        terugkoppeling.clear()
        statusbalk.clear()
        sessie.beoordeeld = False
        sessie.tijd_keuze = None
        v = sessie.huidig
        for vak in (tijdknoppen, statusbalk, vormlabel, vraagsoort):
            vak.set_visibility(True)
        sessie.vraag_praesens = bool(v) and stam_vraagt_praesens(
            sessie.prefs["stam_vraagvorm"], v["streak"])
        invoer.set_visibility(sessie.vraag_praesens)
        if v is None:
            vormlabel.text = "✓"
            vraagsoort.text = f"Klaar — {sessie.goed} goed, {sessie.fout} fout."
            teller.text = ""
            tijdknoppen.clear()
            invoer.set_visibility(False)
            knop.text = "Nieuwe ronde"
            teken()
            return
        vormlabel.text = v["vorm"]
        vraagsoort.text = ("Welke tijd is dit, en van welk werkwoord?"
                           if sessie.vraag_praesens else "Welke tijd is dit?")
        teller.text = f"{sessie.i + 1}/{len(sessie.vragen)}"
        knop.text = "Nakijken"
        invoer.value = ""
        teken()
        teken_tijden()
        with statusbalk:
            ui.html(_statusrij([
                (v["streak"], "streak", TEKST),
                (f"{v['goed']}/{v['fout']}", "goed/fout", TEKST),
                (v["verb"].get("morfologie", {}).get("klasse", "—"), "klasse", ZACHT),
                (len(sessie.vragen) - sessie.i - 1, "te gaan", ZACHT),
            ]))

    async def nakijken():
        # Zonder deze grendel telt een dubbele tik op Volgende als twee aanroepen:
        # de eerste schuift door en wist de staat, de tweede ziet dan geen gekozen
        # tijd meer en klaagt daarover.
        if sessie.bezig:
            return
        sessie.bezig = True
        try:
            await _nakijken()
        finally:
            sessie.bezig = False

    async def _nakijken():
        v = sessie.huidig
        if v is None:
            await run.io_bound(g.bewaar, True)
            ui.navigate.to("/oefenen/stamtijden")
            return
        if sessie.beoordeeld:
            sessie.i += 1
            toon()
            return
        if sessie.tijd_keuze is None:
            ui.notify("Kies eerst een tijd.", position="top", color="dark")
            return
        tijd_ok = sessie.tijd_keuze == v["tijd"]
        pr_ok = (not sessie.vraag_praesens
                 or bool(motor.grieks_vorm_ok(invoer.value or "", v["praesens"])))
        juist = tijd_ok and pr_ok
        sessie.beoordeeld = True
        sessie.goed += int(juist)
        sessie.fout += int(not juist)
        e = stats.setdefault(v["sleutel"], {"g": 0, "f": 0, "streak": 0})
        e["g"] = int(e.get("g", 0)) + int(juist)
        e["f"] = int(e.get("f", 0)) + int(not juist)
        e["streak"] = int(e.get("streak", 0)) + 1 if juist else 0
        g.tel_dag()
        if juist:
            g.dagdoel_plus("stam")
        opgeslagen = await run.io_bound(g.bewaar) if g.sinds_opslag >= 5 else False
        opbouw = ""
        try:
            regels = motor.deconstrueer_stamtijd_live(v["vorm"], v["tijd"], v["praesens"])
            if regels:
                # de motor geeft (stam, uitgang) terug; dat is de opbouw van de vorm
                if isinstance(regels, (tuple, list)) and len(regels) == 2 and all(
                        isinstance(x, str) for x in regels):
                    _stam, _uit = regels
                    if sessie.prefs.get("stam_kleur", True):
                        gekleurd = (f"<span class='grieks' style='color:{TEKST}'>{_stam}</span>"
                                    f"<span class='grieks' style='color:{MERK};"
                                    f"font-weight:700'>{_uit}</span>")
                        tekst = (f"<span style='color:{TEKST}'>{_stam}</span> + "
                                 f"<span style='color:{MERK};font-weight:700'>{_uit}</span>"
                                 f" = {gekleurd}")
                    else:
                        tekst = (f"opbouw: <span class='grieks'>{_stam}</span> + "
                                 f"<span class='grieks'>{_uit}</span>")
                else:
                    lijst = regels if isinstance(regels, list) else [regels]
                    tekst = "<br>".join(str(r) for r in lijst)
                opbouw = (f"<div style='color:{ZACHT};font-size:18px;margin-top:16px'>"
                          f"{tekst}</div>")
        except Exception:                                        # noqa: BLE001
            pass
        deel = ""
        if not juist:
            wat = []
            if not tijd_ok:
                wat.append(f"de tijd was <b>{TIJD_KORT[v['tijd']]}</b>")
            if not pr_ok:
                wat.append(f"het werkwoord was <b>{v['praesens']}</b>")
            deel = (f"<div style='color:{ZACHT};font-size:14px;margin-top:10px'>"
                    f"{' · '.join(wat)}</div>")
        kleur = GOED if juist else FOUT
        achter = "rgba(61,220,151,.10)" if juist else "rgba(255,107,129,.10)"
        # De feedback vervangt de vraag: vijf tijdknoppen plus een antwoordkaart
        # eronder maakt het scherm te lang voor een telefoon.
        tijdknoppen.set_visibility(False)
        statusbalk.set_visibility(False)
        vormlabel.set_visibility(False)
        vraagsoort.set_visibility(False)
        invoer.set_visibility(False)
        terugkoppeling.clear()
        with terugkoppeling:
            ui.html(
                f"<div style='background:{achter};border:1px solid {kleur}40;"
                f"border-radius:16px;padding:26px 18px;text-align:center;width:100%'>"
                f"<div style='color:{kleur};font-weight:700;font-size:19px'>"
                f"{'✓ Goed!' if juist else '✗ Niet goed'}</div>"
                f"<div class='grieks' style='font-size:44px;color:{TEKST};"
                f"margin-top:14px;line-height:1.15'>{v['vorm']}</div>"
                f"<div style='color:{TEKST};font-size:17px;margin-top:8px'>"
                f"{TIJD_KORT[v['tijd']]} van "
                f"<span class='grieks' style='font-size:20px'>{v['praesens']}</span></div>"
                f"<div style='color:{ZACHT};font-size:15px;margin-top:2px'>"
                f"{v['verb'].get('betekenis', '')}</div>"
                f"{deel}{opbouw}"
                f"<div style='color:{ZACHT};font-size:12.5px;margin-top:18px'>"
                f"{sessie.goed} goed · {sessie.fout} fout in deze ronde · "
                f"streak nu {e['streak']}</div></div>")
        if opgeslagen:
            opslagmelding.text = "Voortgang opgeslagen"
        knop.text = "Volgende"

    knop.on_click(nakijken)
    invoer.on("keydown.enter", nakijken)
    toon()


# ============================================================== stamtijden leren
class StamLeerSessie:
    """Flashcards: je ziet een vorm, benoemt in gedachten welke tijd het is en van welk
    praesens hij komt, en checkt jezelf. Geen puntendruk — wat je nog niet wist komt
    achteraan opnieuw."""

    def __init__(self, g):
        self.prefs = stam_prefs(g)
        kaarten = []
        for verb in stam_poule(self.prefs):
            praesens = verb.get("praesens", "")
            if praesens:
                kaarten.append({"verb": verb, "tijd": "Praesens", "vorm": praesens,
                                "sleutel": f"{praesens}_{praesens}"})
            for tijd, vorm in (verb.get("stamtijden") or {}).items():
                if motor._stam_vorm_ok(vorm):
                    kaarten.append({"verb": verb, "tijd": tijd, "vorm": vorm,
                                    "sleutel": f"{praesens}_{vorm}"})
        random.shuffle(kaarten)
        self.wachtrij = kaarten
        self.begin_aantal = len(kaarten)
        self.gedaan = 0
        self.wist = 0
        self.onthuld = False
        self.bezig = False
        self.huidig = self.wachtrij.pop(0) if self.wachtrij else None

    def volgende(self, opnieuw=False):
        if opnieuw and self.huidig is not None:
            self.wachtrij.append(self.huidig)
        self.gedaan += 1
        self.huidig = self.wachtrij.pop(0) if self.wachtrij else None
        self.onthuld = False


@ui.page("/oefenen/stamtijden/leren")
def stamleerpagina():
    g = _bewaakt()
    if not g:
        return
    if stam_prefs(g).get("stam_modus") != STAM_MODI[1]:
        ui.navigate.to("/oefenen/stamtijden")
        return
    sessie = StamLeerSessie(g)
    stats = g.stats.setdefault("stam_stats", {})

    with ui.column().classes("inhoud metbalk w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Stamtijden leren").style(f"color:{ZACHT};font-size:13px")
            with ui.row().classes("items-center gap-2 no-wrap"):
                teller = ui.label().style(f"color:{ZACHT};font-size:13px")
                ui.button("⚙", on_click=lambda: ui.navigate.to("/oefenen/stamtijden")).props(
                    "flat dense").style(f"color:{ZACHT};font-size:17px;min-width:32px")
        ui.label("Bekijk de vorm, benoem voor jezelf wélke tijd het is en van wélk "
                 "werkwoord, en check jezelf. Wat je nog niet wist komt achteraan terug.").style(
            f"color:{ZACHT};font-size:12.5px;line-height:1.5")
        vormlabel = ui.label().classes("grieks w-full text-center").style(
            f"font-size:52px;line-height:1.15;color:{TEKST};padding:16px 0 2px")
        antwoordvak = ui.column().classes("w-full gap-1 items-center").style(
            "min-height:120px")
        opslagmelding = ui.label().style(f"color:{ZACHT};font-size:11.5px;min-height:16px")

    balk = ui.element("div").classes("antwoordbalk")
    with balk:
        toonknop = ui.button("Toon antwoord").props("unelevated").style(
            f"background:{MERK};color:{INKT};font-weight:700;height:40px;width:100%")
        with ui.row().classes("w-full gap-2 no-wrap").style("margin-top:4px") as oordeel:
            wistknop = ui.button("✓ Wist ik").props("flat").style(
                f"flex:1;color:{GOED};border:1px solid {RAND};border-radius:8px")
            nogknop = ui.button("✗ Nog niet").props("flat").style(
                f"flex:1;color:{FOUT};border:1px solid {RAND};border-radius:8px")
    onderbalk("Oefenen")

    def toon():
        antwoordvak.clear()
        k = sessie.huidig
        if k is None:
            vormlabel.text = "✓"
            teller.text = ""
            with antwoordvak:
                ui.html(f"<div style='text-align:center;color:{TEKST};font-size:15px;"
                        f"line-height:1.6'>Alle kaarten gehad — {sessie.wist} van de "
                        f"{sessie.begin_aantal} in één keer geweten.</div>")
            toonknop.text = "Nieuwe ronde"
            toonknop.set_visibility(True)
            oordeel.set_visibility(False)
            return
        vormlabel.text = k["vorm"]
        teller.text = f"nog {len(sessie.wachtrij) + 1}"
        toonknop.set_visibility(not sessie.onthuld)
        toonknop.text = "Toon antwoord"
        oordeel.set_visibility(sessie.onthuld)
        if not sessie.onthuld:
            return
        verb = k["verb"]
        s = stats.get(k["sleutel"]) or {}
        with antwoordvak:
            ui.html(
                f"<div style='background:rgba(51,204,255,.10);border:1px solid {MERK}40;"
                f"border-radius:12px;padding:14px;text-align:center;width:100%'>"
                f"<div style='color:{MERK};font-size:14px;font-weight:600'>"
                f"{TIJD_KORT.get(k['tijd'], k['tijd'])}</div>"
                f"<div class='grieks' style='color:{TEKST};font-size:24px;margin-top:6px'>"
                f"{verb.get('praesens', '')}</div>"
                f"<div style='color:{TEKST};font-size:14px'>{verb.get('betekenis', '')}</div>"
                f"<div style='color:{ZACHT};font-size:12px;margin-top:8px'>"
                f"les {verb.get('les', '?')} · streak {int(s.get('streak', 0) or 0)} · "
                f"{int(s.get('g', 0) or 0)} goed, {int(s.get('f', 0) or 0)} fout</div></div>")

    async def onthullen():
        if sessie.huidig is None:
            ui.navigate.to("/oefenen/stamtijden/leren")
            return
        sessie.onthuld = True
        toon()

    async def oordeel_geven(wist):
        if sessie.bezig or sessie.huidig is None or not sessie.onthuld:
            return
        sessie.bezig = True
        try:
            e = stats.setdefault(sessie.huidig["sleutel"], {"g": 0, "f": 0, "streak": 0})
            if wist:
                e["g"] = int(e.get("g", 0)) + 1
                e["streak"] = int(e.get("streak", 0)) + 1
                sessie.wist += 1
                g.dagdoel_plus("stam")
            else:
                e["f"] = int(e.get("f", 0)) + 1
            g.tel_dag()
            sessie.volgende(opnieuw=not wist)
            opgeslagen = await run.io_bound(g.bewaar)
            if g.laatste_fout:
                opslagmelding.text = "⚠ Opslaan lukte niet — je voortgang staat nog in het geheugen."
                opslagmelding.style(f"color:{FOUT}")
            elif opgeslagen:
                opslagmelding.text = "Voortgang opgeslagen"
                opslagmelding.style(f"color:{ZACHT}")
            toon()
        finally:
            sessie.bezig = False

    toonknop.on_click(onthullen)
    wistknop.on_click(lambda: oordeel_geven(True))
    nogknop.on_click(lambda: oordeel_geven(False))
    toon()


# ============================================================== actief beheersen
AF_OEFENINGEN = ["Zwakste eerst", "Leerpad (volgend rijtje)", "Alleen wat ik fout deed"]
AF_VRAAGVORM = ["Automatisch (aanbevolen)", "Alleen meerkeuze", "Alleen typen"]
AF_MODI = ["Cel voor cel", "Tentamenrooster (heel rijtje)", "Alleen de uitgangen"]
AF_ROOSTER_MODI = AF_MODI[1:]      # de twee die het hele rijtje ineens vragen
AF_STANDAARD = {"af_keuze": "Zwakste eerst", "af_aantal": 10,
                "af_vraagvorm": AF_VRAAGVORM[0], "af_niveau": "Alles",
                "af_modus": AF_MODI[0], "af_rijtje": ""}
AF_TYP_STREAK = 10        # vanaf hier zelf typen in plaats van aanwijzen


def af_prefs(g):
    return {k: (g.stats.get("ui_prefs") or {}).get(f"ng_{k}", v)
            for k, v in AF_STANDAARD.items()}


def af_rijtjes(g):
    """De paradigma's, gegroepeerd zoals ze in actief_beheersen.json staan:
    'Grieks 1 · Werkwoorden · Praesens actief' -> de cellen van dat rijtje."""
    uit = {}
    for c in af_cellen(g):
        uit.setdefault(f"{c['niveau']} · {c['categorie']} · {c['paradigma']}", []).append(c)
    return uit


def af_paspoort(cellen):
    """Het rijtje om te bestuderen: de vaste stam wit, de variabele uitgang cyaan.
    Zelfde beeld als het paradigma-paspoort in de Streamlit-app."""
    return "".join(
        f"<div style='display:flex;justify-content:space-between;gap:10px;"
        f"border-top:1px solid {RAND};padding:6px 0;font-size:13px'>"
        f"<span style='color:{ZACHT}'>{c['label']}</span>"
        f"<span class='grieks' style='font-size:17px'>"
        f"<span style='color:{TEKST}'>{c.get('stam', '') or c['vorm']}</span>"
        f"<span style='color:{MERK};font-weight:700'>{c.get('uitgang', '')}</span>"
        f"</span></div>" for c in cellen)


def af_cellen(g):
    """Alle oefenbare cellen uit actief_beheersen.json, met je scores erbij."""
    db = motor.laad_actief_beheersen_db() or {}
    stats = g.stats.get("actief_stats") or {}
    uit = []
    for niveau, categorieen in db.items():
        for categorie, paradigmas in categorieen.items():
            for paradigma, cellen in paradigmas.items():
                for cel in cellen:
                    vorm = str(cel.get("vorm", "") or "").strip()
                    if not vorm or vorm in ("-", "—", "---"):
                        continue
                    s = stats.get(cel.get("id", "")) or {}
                    uit.append({
                        "niveau": niveau, "categorie": categorie, "paradigma": paradigma,
                        "label": cel.get("label", ""), "vorm": vorm,
                        "stam": cel.get("stam", ""), "uitgang": cel.get("uitgang", ""),
                        "toelichting": cel.get("toelichting", ""),
                        "id": cel.get("id", ""), "rijtje": cellen,
                        "streak": int(s.get("streak", 0) or 0),
                        "goed": int(s.get("g", 0) or 0),
                        "fout": int(s.get("f", 0) or 0)})
    return uit


def af_vraagt_typen(vraagvorm, streak):
    if vraagvorm == "Alleen meerkeuze":
        return False
    if vraagvorm == "Alleen typen":
        return True
    return int(streak or 0) >= AF_TYP_STREAK


class AfSessie:
    def __init__(self, g):
        p = {k: (g.stats.get("ui_prefs") or {}).get(f"ng_{k}", v)
             for k, v in AF_STANDAARD.items()}
        cellen = af_cellen(g)
        if p["af_niveau"] != "Alles":
            cellen = [c for c in cellen if c["niveau"] == p["af_niveau"]] or cellen
        if p["af_keuze"] == "Alleen wat ik fout deed":
            cellen = [c for c in cellen if c["fout"] > 0] or cellen
            cellen.sort(key=lambda c: -c["fout"])
        elif p["af_keuze"] == "Leerpad (volgend rijtje)":
            per = {}
            for c in cellen:
                per.setdefault((c["categorie"], c["paradigma"]), []).append(c)
            for _sleutel, groep in per.items():
                if any(x["streak"] < 5 for x in groep):
                    cellen = groep
                    break
        else:
            cellen.sort(key=lambda c: c["streak"])
        self.prefs = p
        self.vragen = cellen[:int(p["af_aantal"])]
        self.i = 0
        self.goed = 0
        self.fout = 0
        self.beoordeeld = False
        self.bezig = False
        self.vraag_typen = True

    @property
    def huidig(self):
        return self.vragen[self.i] if self.i < len(self.vragen) else None


def af_instellingen(g, sessie_prefs):
    """Instellingen van Actief Beheersen. Gedeeld door de cel-voor-cel-ronde en het
    tentamenrooster; de modus bepaalt naar welk van de twee 'Toepassen' navigeert."""
    niveaus = ["Alles"] + sorted((motor.laad_actief_beheersen_db() or {}).keys())
    with ui.dialog() as instellingen, ui.card().style(
            f"background:{VLAK};color:{TEKST};min-width:300px;max-width:92vw"):
        ui.label("Instellingen").style("font-size:18px;font-weight:700")
        _mo = sessie_prefs.get("af_modus", AF_MODI[0])
        k_modus = ui.select(AF_MODI, value=_mo if _mo in AF_MODI else AF_MODI[0],
                            label="Wat wil je doen").props("outlined dark").classes("w-full")
        ui.label("Cel voor cel bouwt op van aanwijzen naar typen. Het tentamenrooster "
                 "vraagt één heel rijtje in één keer, zoals op het tentamen. Bij 'alleen "
                 "de uitgangen' staat de stam er al en typ je alleen wat erachter komt.").style(
            f"color:{ZACHT};font-size:12px")
        _rijtjes = sorted(af_rijtjes(g))
        _hr = sessie_prefs.get("af_rijtje") or (_rijtjes[0] if _rijtjes else None)
        k_rijtje = ui.select(_rijtjes, value=_hr if _hr in _rijtjes else
                             (_rijtjes[0] if _rijtjes else None),
                             label="Welk rijtje").props("outlined dark").classes("w-full")
        k_rijtje.bind_visibility_from(k_modus, "value", lambda v: v in AF_ROOSTER_MODI)
        k_oef = ui.select(AF_OEFENINGEN, value=sessie_prefs["af_keuze"],
                          label="Oefening").props("outlined dark").classes("w-full")
        k_niv = ui.select(niveaus, value=sessie_prefs["af_niveau"],
                          label="Niveau").props("outlined dark").classes("w-full")
        k_vorm = ui.select(AF_VRAAGVORM, value=sessie_prefs["af_vraagvorm"],
                           label="Wat wordt gevraagd").props("outlined dark").classes("w-full")
        k_aantal = ui.number("Cellen per ronde", value=int(sessie_prefs["af_aantal"]),
                             min=4, max=40, step=1).props("outlined dark").classes("w-full")
        for veld in (k_oef, k_niv, k_vorm, k_aantal):
            veld.bind_visibility_from(k_modus, "value", lambda v: v == AF_MODI[0])
        ui.label(f"Automatisch: eerst aanwijzen uit het eigen rijtje, en vanaf streak "
                 f"{AF_TYP_STREAK} zelf typen.").style(
            f"color:{ZACHT};font-size:12px").bind_visibility_from(
            k_modus, "value", lambda v: v == AF_MODI[0])

        async def bewaar_inst():
            for sleutel, veld in [("af_keuze", k_oef), ("af_niveau", k_niv),
                                  ("af_vraagvorm", k_vorm), ("af_aantal", k_aantal),
                                  ("af_modus", k_modus), ("af_rijtje", k_rijtje)]:
                g.stats.setdefault("ui_prefs", {})[f"ng_{sleutel}"] = veld.value
            instellingen.close()
            await run.io_bound(g.bewaar, True)
            ui.navigate.to("/oefenen/actief/rooster" if k_modus.value in AF_ROOSTER_MODI
                           else "/oefenen/actief")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Annuleren", on_click=instellingen.close).props("flat").style(
                f"color:{ZACHT}")
            ui.button("Toepassen", on_click=bewaar_inst).props("unelevated").style(
                f"background:{MERK};color:{INKT};font-weight:700")
    return instellingen


@ui.page("/oefenen/actief/rooster")
def afroosterpagina():
    """Het hele rijtje in één keer invullen. Goede cellen worden vastgezet, foute velden
    leeggemaakt voor een nieuwe poging — zoals het tentamenrooster in de Streamlit-app."""
    g = _bewaakt()
    if not g:
        return
    p = af_prefs(g)
    if p.get("af_modus") not in AF_ROOSTER_MODI:
        ui.navigate.to("/oefenen/actief")
        return
    alleen_uitgang = p.get("af_modus") == AF_MODI[2]
    rijtjes = af_rijtjes(g)
    naam = p.get("af_rijtje") if p.get("af_rijtje") in rijtjes else (
        sorted(rijtjes)[0] if rijtjes else "")
    cellen = rijtjes.get(naam) or []
    stats = g.stats.setdefault("actief_stats", {})
    instellingen = af_instellingen(g, p)
    spiek = spiekbrief()
    velden, staat = {}, {c["id"]: False for c in cellen}

    with ui.column().classes("inhoud metbalk w-full gap-2"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Tentamenrooster").style(f"color:{ZACHT};font-size:13px")
            with ui.row().classes("items-center gap-2 no-wrap"):
                teller = ui.label().style(f"color:{ZACHT};font-size:13px")
                spiekknop(spiek)
                ui.button("⚙", on_click=instellingen.open).props("flat dense").style(
                    f"color:{ZACHT};font-size:17px;min-width:32px")
        ui.label(naam or "geen rijtje gekozen").style(
            f"color:{TEKST};font-size:16px;font-weight:600")
        ui.label(("De stam staat er al — typ alleen de uitgang. " if alleen_uitgang else
                  "Typ de volledige vormen. ")
                 + "Wat goed is blijft staan; een fout veld wordt leeggemaakt zodat je "
                   "het opnieuw kunt proberen.").style(
            f"color:{ZACHT};font-size:12.5px;line-height:1.5")
        with ui.expansion("Bekijk het rijtje").props("dense").classes("w-full").style(
                f"color:{ZACHT};font-size:13px"):
            ui.label("De vaste stam is wit, de variabele uitgang cyaan.").style(
                f"color:{ZACHT};font-size:12px")
            ui.html(af_paspoort(cellen))
        rooster = ui.column().classes("w-full gap-2").style("padding-top:6px")
        terugkoppeling = ui.column().classes("w-full items-center").style("min-height:40px")
        opslagmelding = ui.label().style(f"color:{ZACHT};font-size:11.5px;min-height:16px")

    balk = ui.element("div").classes("antwoordbalk")
    with balk:
        knop = ui.button("Nakijken").props("unelevated").style(
            f"background:{MERK};color:{INKT};font-weight:700;height:40px;width:100%")
    onderbalk("Oefenen")

    def teken():
        rooster.clear()
        velden.clear()
        af = sum(1 for c in cellen if staat[c["id"]])
        teller.text = f"{af}/{len(cellen)}"
        with rooster:
            for c in cellen:
                if staat[c["id"]]:
                    ui.html(f"<div style='display:flex;justify-content:space-between;"
                            f"gap:8px;font-size:13.5px;color:{GOED};border:1px solid "
                            f"{GOED}40;border-radius:8px;padding:7px 10px'>"
                            f"<span style='color:{ZACHT}'>{c['label']}</span>"
                            f"<span class='grieks' style='font-size:16px'>{c['vorm']}</span>"
                            f"</div>")
                elif alleen_uitgang:
                    with ui.row().classes("w-full gap-2 no-wrap items-center"):
                        ui.html(f"<span class='grieks' style='font-size:19px;color:{TEKST};"
                                f"white-space:nowrap'>{c.get('stam', '')} +</span>")
                        velden[c["id"]] = ui.input(label=c["label"]).props(
                            "outlined dense dark autocomplete=off").classes("flex-grow")
                else:
                    velden[c["id"]] = ui.input(label=c["label"]).props(
                        "outlined dense dark autocomplete=off").classes("w-full")
        if af == len(cellen) and cellen:
            knop.text = "Opnieuw"
        else:
            knop.text = "Nakijken"

    async def nakijken():
        if not cellen:
            return
        if all(staat.values()):
            for c in cellen:
                staat[c["id"]] = False
            terugkoppeling.clear()
            teken()
            return
        nieuw_goed = 0
        for c in cellen:
            if staat[c["id"]]:
                continue
            gegeven = (velden.get(c["id"]).value or "") if velden.get(c["id"]) else ""
            if alleen_uitgang:
                # Een lege uitgang is een geldig antwoord (bv. de nominatief van
                # sommige rijtjes), dus die vergelijking mag niet op 'ingevuld' hangen.
                verwacht = motor.normaliseer_accent(c.get("uitgang", "") or "")
                gedaan = motor.normaliseer_accent(
                    motor.naar_grieks_transliteratie(gegeven))
                juist = verwacht == gedaan
            else:
                juist = bool(motor.grieks_vorm_ok(gegeven, c["vorm"]))
            e = stats.setdefault(c["id"], {"g": 0, "f": 0, "streak": 0})
            e["g"] = int(e.get("g", 0)) + int(juist)
            e["f"] = int(e.get("f", 0)) + int(not juist)
            e["streak"] = int(e.get("streak", 0)) + 1 if juist else 0
            g.tel_dag()
            if juist:
                staat[c["id"]] = True
                nieuw_goed += 1
                g.dagdoel_plus("actief")
        klaar = all(staat.values())
        opgeslagen = await run.io_bound(g.bewaar, klaar)
        terugkoppeling.clear()
        with terugkoppeling:
            if klaar:
                ui.html(f"<div style='background:rgba(61,220,151,.10);border:1px solid "
                        f"{GOED}40;border-radius:12px;padding:12px;text-align:center;"
                        f"width:100%;color:{TEKST};font-size:14px'>🏆 Het hele rijtje "
                        f"foutloos gereproduceerd.</div>")
            else:
                over = sum(1 for c in cellen if not staat[c["id"]])
                ui.html(f"<div style='color:{ZACHT};font-size:13px;text-align:center'>"
                        f"{nieuw_goed} erbij · nog {over} te gaan.</div>")
        if g.laatste_fout:
            opslagmelding.text = "⚠ Opslaan lukte niet — je voortgang staat nog in het geheugen."
            opslagmelding.style(f"color:{FOUT}")
        elif opgeslagen:
            opslagmelding.text = "Voortgang opgeslagen"
            opslagmelding.style(f"color:{ZACHT}")
        teken()

    knop.on_click(nakijken)
    teken()


@ui.page("/oefenen/actief")
def afpagina():
    g = _bewaakt()
    if not g:
        return
    if af_prefs(g).get("af_modus") == AF_MODI[1]:
        ui.navigate.to("/oefenen/actief/rooster")
        return
    sessie = AfSessie(g)
    stats = g.stats.setdefault("actief_stats", {})
    instellingen = af_instellingen(g, sessie.prefs)
    spiek = spiekbrief()

    with ui.column().classes("inhoud metbalk w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Actief beheersen").style(f"color:{ZACHT};font-size:13px")
            with ui.row().classes("items-center gap-2 no-wrap"):
                teller = ui.label().style(f"color:{ZACHT};font-size:13px")
                spiekknop(spiek)
                ui.button("⚙", on_click=instellingen.open).props("flat dense").style(
                    f"color:{ZACHT};font-size:17px;min-width:32px")
        streepjes = ui.row().classes("w-full gap-1 no-wrap")
        paspoort = ui.column().classes("w-full")
        rijtje = ui.label().classes("w-full text-center").style(
            f"color:{ZACHT};font-size:13px;padding-top:4px")
        gevraagd = ui.label().classes("w-full text-center").style(
            f"color:{TEKST};font-size:30px;font-weight:700;line-height:1.2")
        vraagsoort = ui.label().classes("w-full text-center").style(
            f"color:{ZACHT};font-size:13px")
        opties = ui.column().classes("w-full gap-2").style("padding-top:6px")
        statusbalk = ui.row().classes("w-full").style("padding-top:2px")
        terugkoppeling = ui.column().classes("w-full items-center justify-center").style(
            "min-height:64px;padding-top:8px")
        opslagmelding = ui.label().style(f"color:{ZACHT};font-size:11.5px;min-height:16px")

    with ui.element("div").classes("antwoordbalk"):
        with ui.row().classes("w-full gap-2 no-wrap items-center"):
            invoer = ui.input(placeholder="typ de vorm (x = χ, u = υ, h = η)").props(
                "outlined dense dark autocomplete=off").classes("flex-grow")
            knop = ui.button("Nakijken").props("unelevated").style(
                f"background:{MERK};color:{INKT};font-weight:700;height:40px;min-width:108px")
    onderbalk("Oefenen")

    def teken():
        streepjes.clear()
        with streepjes:
            for n in range(len(sessie.vragen)):
                kleur = MERK if n < sessie.i else (TEKST if n == sessie.i else RAND)
                ui.element("div").style(f"flex:1;height:4px;border-radius:2px;background:{kleur}")

    def toon():
        for vak in (opties, terugkoppeling, statusbalk):
            vak.clear()
        sessie.beoordeeld = False
        c = sessie.huidig
        for vak in (rijtje, gevraagd, vraagsoort, opties, statusbalk):
            vak.set_visibility(True)
        if c is None:
            rijtje.text = ""
            paspoort.clear()
            gevraagd.text = "✓"
            vraagsoort.text = f"Klaar — {sessie.goed} goed, {sessie.fout} fout."
            teller.text = ""
            invoer.set_visibility(False)
            knop.text = "Nieuwe ronde"
            teken()
            return
        sessie.vraag_typen = af_vraagt_typen(sessie.prefs["af_vraagvorm"], c["streak"])
        rijtje.text = f"{c['categorie']} · {c['paradigma']}"
        # Het hele rijtje kunnen bestuderen zonder de oefening te verlaten: de vaste
        # stam wit, de variabele uitgang cyaan.
        paspoort.clear()
        with paspoort:
            with ui.expansion("Bekijk het rijtje").props("dense").classes("w-full").style(
                    f"color:{ZACHT};font-size:12.5px"):
                ui.html(af_paspoort(c["rijtje"]))
        gevraagd.text = c["label"]
        vraagsoort.text = ("Typ deze vorm" if sessie.vraag_typen
                           else "Welke vorm hoort hierbij?")
        teller.text = f"{sessie.i + 1}/{len(sessie.vragen)}"
        knop.text = "Nakijken" if sessie.vraag_typen else "Ik weet het niet"
        invoer.value = ""
        invoer.set_visibility(sessie.vraag_typen)
        teken()
        if not sessie.vraag_typen:
            # Afleiders uit hetzelfde rijtje: zo leer je de cellen onderling onderscheiden.
            anders = [x.get("vorm", "") for x in c["rijtje"]
                      if x.get("vorm") and x.get("vorm") != c["vorm"]]
            keuzes = random.sample(anders, min(3, len(anders))) + [c["vorm"]]
            random.shuffle(keuzes)
            with opties:
                for keuze in keuzes:
                    ui.html(f"<button class='keuze grieks' style='font-size:19px;"
                            f"text-align:center;padding:10px 12px'>{keuze}</button>").on(
                        "click", lambda _=None, kz=keuze: kies(kz))
        with statusbalk:
            ui.html(_statusrij([
                (c["streak"], "streak", TEKST),
                (f"{c['goed']}/{c['fout']}", "goed/fout", TEKST),
                (c["niveau"].replace("Grieks ", "G"), "niveau", ZACHT),
                (len(sessie.vragen) - sessie.i - 1, "te gaan", ZACHT),
            ]))
        if sessie.vraag_typen:
            invoer.run_method("focus")

    async def verwerk(c, juist):
        sessie.beoordeeld = True
        sessie.goed += int(juist)
        sessie.fout += int(not juist)
        e = stats.setdefault(c["id"], {"g": 0, "f": 0, "streak": 0})
        e["g"] = int(e.get("g", 0)) + int(juist)
        e["f"] = int(e.get("f", 0)) + int(not juist)
        e["streak"] = int(e.get("streak", 0)) + 1 if juist else 0
        g.tel_dag()
        if juist:
            g.dagdoel_plus("actief")
        opgeslagen = await run.io_bound(g.bewaar)
        for vak in (rijtje, gevraagd, vraagsoort, opties, statusbalk):
            vak.set_visibility(False)
        invoer.set_visibility(False)
        opbouw = ""
        if c["stam"] and c["uitgang"]:
            opbouw = (f"<div style='font-size:18px;margin-top:16px'>"
                      f"<span class='grieks' style='color:{TEKST}'>{c['stam']}</span>"
                      f"<span class='grieks' style='color:{MERK};font-weight:700'>"
                      f"{c['uitgang']}</span></div>")
        uitleg = ""
        if c["toelichting"]:
            uitleg = (f"<div style='color:{ZACHT};font-size:13px;margin-top:12px;"
                      f"line-height:1.5'>{c['toelichting']}</div>")
        kleur = GOED if juist else FOUT
        achter = "rgba(61,220,151,.10)" if juist else "rgba(255,107,129,.10)"
        terugkoppeling.clear()
        with terugkoppeling:
            ui.html(
                f"<div style='background:{achter};border:1px solid {kleur}40;"
                f"border-radius:16px;padding:26px 18px;text-align:center;width:100%'>"
                f"<div style='color:{kleur};font-weight:700;font-size:19px'>"
                f"{'✓ Goed!' if juist else '✗ Niet goed'}</div>"
                f"<div class='grieks' style='font-size:44px;color:{TEKST};"
                f"margin-top:14px;line-height:1.15'>{c['vorm']}</div>"
                f"<div style='color:{TEKST};font-size:16px;margin-top:6px'>{c['label']}</div>"
                f"<div style='color:{ZACHT};font-size:13.5px'>{c['paradigma']}</div>"
                f"{opbouw}{uitleg}"
                f"<div style='color:{ZACHT};font-size:12.5px;margin-top:18px'>"
                f"{sessie.goed} goed · {sessie.fout} fout in deze ronde · "
                f"streak nu {e['streak']}</div></div>")
        if opgeslagen:
            opslagmelding.text = "Voortgang opgeslagen"
        knop.text = "Volgende"

    async def kies(keuze):
        if sessie.beoordeeld or sessie.bezig:
            return
        sessie.bezig = True
        try:
            c = sessie.huidig
            await verwerk(c, keuze == c["vorm"])
        finally:
            sessie.bezig = False

    async def hoofdknop():
        if sessie.bezig:
            return
        sessie.bezig = True
        try:
            c = sessie.huidig
            if c is None:
                await run.io_bound(g.bewaar, True)
                ui.navigate.to("/oefenen/actief")
                return
            if sessie.beoordeeld:
                sessie.i += 1
                toon()
                return
            if sessie.vraag_typen:
                await verwerk(c, bool(motor.grieks_vorm_ok(invoer.value or "", c["vorm"])))
            else:
                await verwerk(c, False)          # 'ik weet het niet'
        finally:
            sessie.bezig = False

    knop.on_click(hoofdknop)
    invoer.on("keydown.enter", hoofdknop)
    toon()


# ============================================================== structuurwoorden
SW_OEFENINGEN = ["Zwakste eerst", "Leerpad (volgend blokje)", "Alleen wat ik fout deed",
                 "Per categorie"]
SW_VRAAGVORM = ["Automatisch (aanbevolen)", "Alleen meerkeuze", "Alleen typen"]
SW_STANDAARD = {"sw_keuze": "Zwakste eerst", "sw_aantal": 10,
                "sw_vraagvorm": SW_VRAAGVORM[0], "sw_categorie": "Alles", "sw_level": 0}
SW_TYP_STREAK = 10


def sw_woorden(g):
    """De 99 structuurwoorden met je scores erbij, op dezelfde sleutel als de
    Streamlit-app (grieks_index, met terugval op de kale vorm voor oude data)."""
    db = motor.laad_structuurwoorden_db() or []
    stats = g.stats.get("struct_stats") or {}
    uit = []
    for idx, w in enumerate(db):
        s = motor._struct_stat_lookup(stats, w, idx)
        uit.append({**w, "idx": idx, "sleutel": f"{w.get('grieks', '')}_{idx}",
                    "streak": int(s.get("streak", 0) or 0),
                    "goed": int(s.get("g", 0) or 0),
                    "fout": int(s.get("f", 0) or 0)})
    return uit


def sw_vraagt_typen(vraagvorm, streak):
    if vraagvorm == "Alleen meerkeuze":
        return False
    if vraagvorm == "Alleen typen":
        return True
    return int(streak or 0) >= SW_TYP_STREAK


def sw_levels(g):
    """De structuurwoorden in blokjes van zes, met per blokje hoever je bent.
    Zelfde indeling als de Streamlit-app: op categorie gegroepeerd, 'af' bij streak 5."""
    try:
        return motor.struct_level_status(
            motor.bouw_struct_levels(motor.laad_structuurwoorden_db() or []),
            g.stats.get("struct_stats") or {})
    except Exception:                                            # noqa: BLE001
        return []


class SwSessie:
    def __init__(self, g):
        p = {k: (g.stats.get("ui_prefs") or {}).get(f"ng_{k}", v)
             for k, v in SW_STANDAARD.items()}
        woorden = sw_woorden(g)
        self.level = None
        if p["sw_categorie"] != "Alles":
            woorden = [w for w in woorden
                       if w.get("categorie") == p["sw_categorie"]] or woorden
        if p["sw_keuze"] == "Alleen wat ik fout deed":
            woorden = [w for w in woorden if w["fout"] > 0] or woorden
            woorden.sort(key=lambda w: -w["fout"])
        elif p["sw_keuze"] == "Leerpad (volgend blokje)":
            # Het gekozen blokje, of anders het eerstvolgende dat nog niet af is.
            status = sw_levels(g)
            gekozen = int(p.get("sw_level", 0) or 0)
            doel = next((s for s in status if s["index"] == gekozen), None) if gekozen else None
            if doel is None:
                doel = next((s for s in status
                             if s.get("ontgrendeld") and not s.get("voltooid")), None)
            if doel:
                self.level = doel
                idxs = {idx for idx, _w in doel["items"]}
                woorden = [w for w in woorden if w["idx"] in idxs] or woorden
        elif p["sw_keuze"] == "Per categorie":
            woorden.sort(key=lambda w: (str(w.get("categorie", "")), w["streak"]))
        else:
            woorden.sort(key=lambda w: w["streak"])
        self.prefs = p
        self.alles = sw_woorden(g)
        self.vragen = woorden[:int(p["sw_aantal"])]
        self.i = 0
        self.goed = 0
        self.fout = 0
        self.beoordeeld = False
        self.bezig = False
        self.vraag_typen = True

    @property
    def huidig(self):
        return self.vragen[self.i] if self.i < len(self.vragen) else None


@ui.page("/oefenen/structuur")
def swpagina():
    g = _bewaakt()
    if not g:
        return
    sessie = SwSessie(g)
    stats = g.stats.setdefault("struct_stats", {})
    categorieen = ["Alles"] + sorted({str(w.get("categorie", "")) for w in sessie.alles
                                      if w.get("categorie")})

    with ui.dialog() as instellingen, ui.card().style(
            f"background:{VLAK};color:{TEKST};min-width:300px;max-width:92vw"):
        ui.label("Instellingen").style("font-size:18px;font-weight:700")
        k_oef = ui.select(SW_OEFENINGEN, value=sessie.prefs["sw_keuze"],
                          label="Oefening").props("outlined dark").classes("w-full")
        # Blokjes van zes; alleen wat je hebt ontgrendeld staat in de lijst.
        _lv = sw_levels(g)
        _open = {0: "Automatisch (volgend blokje)"}
        for _st in _lv:
            if _st.get("ontgrendeld"):
                _open[_st["index"]] = (f"Blokje {_st['index']} · {_st.get('titel', '')} "
                                       f"({_st.get('klaar', 0)}/{_st.get('totaal', 0)})")
        _hl = int(sessie.prefs.get("sw_level", 0) or 0)
        k_level = ui.select(_open, value=_hl if _hl in _open else 0,
                            label="Blokje").props("outlined dark").classes("w-full")
        k_level.bind_visibility_from(k_oef, "value",
                                     lambda v: v == "Leerpad (volgend blokje)")
        _slot = next((s for s in _lv if not s.get("ontgrendeld")), None)
        if _slot:
            ui.label(f"🔒 Hierna: blokje {_slot['index']} · {_slot.get('titel', '')}").style(
                f"color:{ZACHT};font-size:12px").bind_visibility_from(
                k_oef, "value", lambda v: v == "Leerpad (volgend blokje)")
        k_cat = ui.select(categorieen, value=sessie.prefs["sw_categorie"],
                          label="Categorie").props("outlined dark").classes("w-full")
        k_vorm = ui.select(SW_VRAAGVORM, value=sessie.prefs["sw_vraagvorm"],
                           label="Wat wordt gevraagd").props("outlined dark").classes("w-full")
        k_aantal = ui.number("Woorden per ronde", value=int(sessie.prefs["sw_aantal"]),
                             min=4, max=40, step=1).props("outlined dark").classes("w-full")
        ui.label(f"Automatisch: eerst aanwijzen, en vanaf streak {SW_TYP_STREAK} "
                 f"de betekenis zelf typen.").style(f"color:{ZACHT};font-size:12px")

        async def bewaar_inst():
            for sleutel, veld in [("sw_keuze", k_oef), ("sw_categorie", k_cat),
                                  ("sw_vraagvorm", k_vorm), ("sw_aantal", k_aantal),
                                  ("sw_level", k_level)]:
                g.stats.setdefault("ui_prefs", {})[f"ng_{sleutel}"] = veld.value
            instellingen.close()
            await run.io_bound(g.bewaar, True)
            ui.navigate.to("/oefenen/structuur")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Annuleren", on_click=instellingen.close).props("flat").style(
                f"color:{ZACHT}")
            ui.button("Toepassen", on_click=bewaar_inst).props("unelevated").style(
                f"background:{MERK};color:{INKT};font-weight:700")

    with ui.column().classes("inhoud metbalk w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Structuurwoorden").style(f"color:{ZACHT};font-size:13px")
            with ui.row().classes("items-center gap-2 no-wrap"):
                teller = ui.label().style(f"color:{ZACHT};font-size:13px")
                ui.button("⚙", on_click=instellingen.open).props("flat dense").style(
                    f"color:{ZACHT};font-size:17px;min-width:32px")
        if sessie.level:
            _xp = motor.bereken_xp_struct(g.stats.get("struct_stats") or {})
            _niv = motor.niveau_van_xp(_xp)
            _vol = sum(1 for s in sw_levels(g) if s.get("voltooid"))
            ui.html(f"<div style='display:flex;justify-content:space-between;font-size:12px;"
                    f"color:{ZACHT}'><span>Blokje {sessie.level['index']} · "
                    f"{sessie.level.get('titel', '')}</span><span>{_vol} af · niveau "
                    f"{_niv['niveau']}</span></div>")
            with ui.expansion("Leer eerst dit rijtje").props("dense").classes(
                    "w-full").style(f"color:{ZACHT};font-size:13px"):
                ui.html("".join(
                    f"<div style='font-size:13px;line-height:1.7;color:{TEKST}'>"
                    f"<span class='grieks' style='font-size:16px'>{w.get('grieks','')}</span>"
                    f" — {w.get('nederlands', '') or w.get('betekenis', '')}"
                    f"<span style='color:{ZACHT};font-size:11.5px'> · "
                    f"{w.get('categorie', '')}</span></div>"
                    for _idx, w in sessie.level["items"]))
        streepjes = ui.row().classes("w-full gap-1 no-wrap")
        woord = ui.label().classes("grieks w-full text-center").style(
            f"font-size:42px;line-height:1.1;color:{TEKST};padding:2px 0 0")
        soort = ui.label().classes("w-full text-center").style(
            f"color:{ZACHT};font-size:12.5px")
        vraagsoort = ui.label().classes("w-full text-center").style(
            f"color:{ZACHT};font-size:13px;padding-top:4px")
        opties = ui.column().classes("w-full gap-2").style("padding-top:6px")
        statusbalk = ui.row().classes("w-full").style("padding-top:2px")
        terugkoppeling = ui.column().classes("w-full items-center justify-center").style(
            "min-height:64px;padding-top:8px")
        opslagmelding = ui.label().style(f"color:{ZACHT};font-size:11.5px;min-height:16px")

    with ui.element("div").classes("antwoordbalk"):
        with ui.row().classes("w-full gap-2 no-wrap items-center"):
            invoer = ui.input(placeholder="betekenis").props(
                "outlined dense dark autocomplete=off").classes("flex-grow")
            knop = ui.button("Nakijken").props("unelevated").style(
                f"background:{MERK};color:{INKT};font-weight:700;height:40px;min-width:108px")
    onderbalk("Oefenen")

    def teken():
        streepjes.clear()
        with streepjes:
            for n in range(len(sessie.vragen)):
                kleur = MERK if n < sessie.i else (TEKST if n == sessie.i else RAND)
                ui.element("div").style(f"flex:1;height:4px;border-radius:2px;background:{kleur}")

    def toon():
        for vak in (opties, terugkoppeling, statusbalk):
            vak.clear()
        sessie.beoordeeld = False
        w = sessie.huidig
        for vak in (woord, soort, vraagsoort, opties, statusbalk):
            vak.set_visibility(True)
        if w is None:
            woord.text = "✓"
            soort.text = ""
            vraagsoort.text = f"Klaar — {sessie.goed} goed, {sessie.fout} fout."
            teller.text = ""
            invoer.set_visibility(False)
            knop.text = "Nieuwe ronde"
            teken()
            return
        sessie.vraag_typen = sw_vraagt_typen(sessie.prefs["sw_vraagvorm"], w["streak"])
        woord.text = w.get("grieks", "")
        soort.text = f"{w.get('categorie', '')} · {w.get('eigenschap', '')}".strip(" ·")
        vraagsoort.text = ("Typ de betekenis" if sessie.vraag_typen
                           else "Welke betekenis hoort hierbij?")
        teller.text = f"{sessie.i + 1}/{len(sessie.vragen)}"
        knop.text = "Nakijken" if sessie.vraag_typen else "Ik weet het niet"
        invoer.value = ""
        invoer.set_visibility(sessie.vraag_typen)
        teken()
        if not sessie.vraag_typen:
            # Afleiders het liefst uit dezelfde categorie: voorzetsels met voorzetsels.
            zelfde = [x for x in sessie.alles
                      if x is not w and x.get("categorie") == w.get("categorie")
                      and x.get("betekenis") != w.get("betekenis")]
            rest = [x for x in sessie.alles
                    if x is not w and x.get("betekenis") != w.get("betekenis")]
            bron = zelfde if len(zelfde) >= 3 else rest
            keuzes = [x.get("betekenis", "") for x in random.sample(bron, min(3, len(bron)))]
            keuzes.append(w.get("betekenis", ""))
            random.shuffle(keuzes)
            with opties:
                for keuze in keuzes:
                    ui.html(f"<button class='keuze' style='font-size:14.5px;"
                            f"padding:9px 12px;line-height:1.35'>{keuze}</button>").on(
                        "click", lambda _=None, kz=keuze: kies(kz))
        with statusbalk:
            ui.html(_statusrij([
                (w["streak"], "streak", TEKST),
                (f"{w['goed']}/{w['fout']}", "goed/fout", TEKST),
                (len(sessie.vragen) - sessie.i - 1, "te gaan", ZACHT),
            ]))
        if sessie.vraag_typen:
            invoer.run_method("focus")

    async def verwerk(w, juist):
        sessie.beoordeeld = True
        sessie.goed += int(juist)
        sessie.fout += int(not juist)
        e = stats.setdefault(w["sleutel"], {"g": 0, "f": 0, "streak": 0})
        e["g"] = int(e.get("g", 0)) + int(juist)
        e["f"] = int(e.get("f", 0)) + int(not juist)
        e["streak"] = int(e.get("streak", 0)) + 1 if juist else 0
        g.tel_dag()
        if juist:
            g.dagdoel_plus("struct")
        opgeslagen = await run.io_bound(g.bewaar)
        for vak in (woord, soort, vraagsoort, opties, statusbalk):
            vak.set_visibility(False)
        invoer.set_visibility(False)
        eig = w.get("eigenschap", "")
        regel_eig = (f"<div style='color:{MERK};font-size:15px;margin-top:6px'>{eig}</div>"
                     if eig else "")
        kleur = GOED if juist else FOUT
        achter = "rgba(61,220,151,.10)" if juist else "rgba(255,107,129,.10)"
        terugkoppeling.clear()
        with terugkoppeling:
            ui.html(
                f"<div style='background:{achter};border:1px solid {kleur}40;"
                f"border-radius:16px;padding:26px 18px;text-align:center;width:100%'>"
                f"<div style='color:{kleur};font-weight:700;font-size:19px'>"
                f"{'✓ Goed!' if juist else '✗ Niet goed'}</div>"
                f"<div class='grieks' style='font-size:44px;color:{TEKST};"
                f"margin-top:14px;line-height:1.15'>{w.get('grieks', '')}</div>"
                f"<div style='color:{TEKST};font-size:17px;margin-top:8px'>"
                f"{w.get('betekenis', '')}</div>"
                f"{regel_eig}"
                f"<div style='color:{ZACHT};font-size:13px;margin-top:4px'>"
                f"{w.get('categorie', '')}</div>"
                f"<div style='color:{ZACHT};font-size:12.5px;margin-top:18px'>"
                f"{sessie.goed} goed · {sessie.fout} fout in deze ronde · "
                f"streak nu {e['streak']}</div></div>")
        if opgeslagen:
            opslagmelding.text = "Voortgang opgeslagen"
        knop.text = "Volgende"

    async def kies(keuze):
        if sessie.beoordeeld or sessie.bezig:
            return
        sessie.bezig = True
        try:
            w = sessie.huidig
            await verwerk(w, keuze == w.get("betekenis", ""))
        finally:
            sessie.bezig = False

    async def hoofdknop():
        if sessie.bezig:
            return
        sessie.bezig = True
        try:
            w = sessie.huidig
            if w is None:
                await run.io_bound(g.bewaar, True)
                ui.navigate.to("/oefenen/structuur")
                return
            if sessie.beoordeeld:
                sessie.i += 1
                toon()
                return
            if sessie.vraag_typen:
                await verwerk(w, bool(motor.check_betekenis(invoer.value or "",
                                                            w.get("betekenis", ""))))
            else:
                await verwerk(w, False)
        finally:
            sessie.bezig = False

    knop.on_click(hoofdknop)
    invoer.on("keydown.enter", hoofdknop)
    toon()


# ============================================================== ontleden
ONT_STANDAARD = {"ont_niveau": "Grieks 1", "ont_drempel": 5, "ont_kleur": True,
                 "ont_rijtje": True, "ont_vertaalhulp": True, "ont_links": True}
ONT_NIVEAUS = ["Grieks 1", "Grieks 2", "Grieks 3"]


def ont_dims_van(info):
    """De dimensies die dit woord echt heeft. De woordsoort krijgt bewust de volledige
    lijst: de verkorte lijst uit de motor bevat bijvoorbeeld geen 'Voorzetsel', en dan
    staat het juiste antwoord er niet tussen."""
    uit = []
    for sleutel, label, opties in motor._ontleed_dims(info) or []:
        if sleutel == "woordsoort":
            opties = list(motor._ONTLEED_WS_OPTS)
        goed = [o for o in opties if motor._ontleed_deel_ok(sleutel, o, info)]
        if goed:                      # alleen vragen die te beantwoorden zijn
            uit.append((sleutel, label, opties, goed))
    return uit


def ont_kies_vers(g, niveau, drempel):
    """Een vers waarvan je de woorden kent: alle lexicale woorden minstens één keer
    geoefend, en minstens één naam- of werkwoord dat je goed beheerst."""
    bijbel = motor.laad_bijbel_db() or {}
    bekend = {w["grieks"]: int(w.get("streak", 0) or 0) for w in g.woorden}
    kandidaten = []
    for ref, woorden in bijbel.items():
        if not 4 <= len(woorden) <= 12:
            continue
        sterk = 0
        goed = True
        for w in woorden:
            info = w.get("parsing_info", "") or ""
            if not motor._ontleed_in_scope(info, niveau):
                goed = False
                break
            s = bekend.get(w.get("lemma") or w.get("grieks", ""), 0)
            if s >= drempel and ("Zelfst" in info or "Werkwoord" in info):
                sterk += 1
        if goed and sterk >= 1:
            kandidaten.append(ref)
        if len(kandidaten) >= 400:
            break
    if not kandidaten:
        kandidaten = [r for r, w in bijbel.items() if 4 <= len(w) <= 10][:200]
    ref = random.choice(kandidaten)
    return ref, bijbel[ref]


@ui.page("/oefenen/ontleden")
def ontpagina():
    g = _bewaakt()
    if not g:
        return
    if not BIJBEL:
        with ui.column().classes("inhoud w-full gap-3"):
            ui.label("Ontleden").style("font-size:26px;font-weight:700")
            naar_streamlit(g, "Ontleden")
        onderbalk("Oefenen")
        return
    p = {k: (g.stats.get("ui_prefs") or {}).get(f"ng_{k}", v)
         for k, v in ONT_STANDAARD.items()}
    stats = g.stats.setdefault("ontleed_stats", {})
    ref, woorden = ont_kies_vers(g, p["ont_niveau"], int(p["ont_drempel"]))

    # per woord de te stellen vragen; woorden zonder vragen slaan we over
    taken = []
    for wi, w in enumerate(woorden):
        for sleutel, label, opties, goed in ont_dims_van(w.get("parsing_info", "") or ""):
            taken.append({"wi": wi, "woord": w, "sleutel": sleutel, "label": label,
                          "opties": opties, "goed": goed})
    staat = {"i": 0, "goed": 0, "fout": 0, "beoordeeld": False, "bezig": False,
         "gedaan": set()}          # (woordindex, dimensie) die je beantwoord hebt

    with ui.dialog() as instellingen, ui.card().style(
            f"background:{VLAK};color:{TEKST};min-width:300px;max-width:92vw"):
        ui.label("Instellingen").style("font-size:18px;font-weight:700")
        k_niv = ui.select(ONT_NIVEAUS, value=p["ont_niveau"], label="Niveau").props(
            "outlined dark").classes("w-full")
        k_drem = ui.number("Woorden moeten streak … hebben", value=int(p["ont_drempel"]),
                           min=0, max=20, step=1).props("outlined dark").classes("w-full")
        k_kleur = ui.switch("Naamvallen kleuren in het vers", value=bool(p["ont_kleur"]))
        k_rijtje = ui.switch("Knop 'bekijk het rijtje' tonen", value=bool(p["ont_rijtje"]))
        k_vh = ui.switch("Knop 'vertaalhulp' tonen", value=bool(p["ont_vertaalhulp"]))
        k_links = ui.switch("Links naar BibleHub tonen", value=bool(p["ont_links"]))
        ui.label("Een lagere drempel geeft meer verzen om uit te kiezen.").style(
            f"color:{ZACHT};font-size:12px")

        async def bewaar_inst():
            for sleutel, veld in [("ont_niveau", k_niv), ("ont_drempel", k_drem),
                                  ("ont_kleur", k_kleur), ("ont_rijtje", k_rijtje),
                                  ("ont_vertaalhulp", k_vh), ("ont_links", k_links)]:
                g.stats.setdefault("ui_prefs", {})[f"ng_{sleutel}"] = veld.value
            instellingen.close()
            await run.io_bound(g.bewaar, True)
            ui.navigate.to("/oefenen/ontleden")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Annuleren", on_click=instellingen.close).props("flat").style(
                f"color:{ZACHT}")
            ui.button("Toepassen", on_click=bewaar_inst).props("unelevated").style(
                f"background:{MERK};color:{INKT};font-weight:700")

    with ui.column().classes("inhoud metbalk w-full gap-2"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label(f"Ontleden · {ref}").style(f"color:{ZACHT};font-size:13px")
            with ui.row().classes("items-center gap-2 no-wrap"):
                teller = ui.label().style(f"color:{ZACHT};font-size:13px")
                ui.button("⚙", on_click=instellingen.open).props("flat dense").style(
                    f"color:{ZACHT};font-size:17px;min-width:32px")
        streepjes = ui.row().classes("w-full gap-1 no-wrap")
        vers = ui.html().classes("w-full").style("padding:6px 0")
        gevraagd = ui.label().classes("w-full text-center").style(
            f"color:{MERK};font-size:17px;font-weight:600;padding-top:4px")
        opties = ui.column().classes("w-full gap-2").style("padding-top:4px")
        terugkoppeling = ui.column().classes("w-full items-center justify-center").style(
            "min-height:56px;padding-top:6px")
        hulpvak = ui.column().classes("w-full gap-1").style("padding-top:6px")

    with ui.element("div").classes("antwoordbalk"):
        knop = ui.button("Volgende").props("unelevated").classes("w-full").style(
            f"background:{MERK};color:{INKT};font-weight:700;height:42px")
    onderbalk("Oefenen")

    def teken_vers(actief_wi, toon_kleur=False):
        """Woorden die je goed hebt ontleed kleuren meteen op naamval — zo zie je de
        zinsbouw onder je handen ontstaan in plaats van pas aan het eind."""
        delen = []
        for i, w in enumerate(woorden):
            tekst = w.get("grieks", "")
            info = w.get("parsing_info", "") or ""
            stijl = "font-size:24px;padding:0 3px;"
            # De kleur hoort bij de naamval, dus hij verschijnt pas als je die
            # vraag hebt gehad — goed of fout maakt niet uit, de kleur is altijd de
            # juiste. Woorden zonder naamval lichten pas op als ze helemaal af zijn.
            heeft_nv = any(t["wi"] == i and t["sleutel"] == "naamval" for t in taken)
            if heeft_nv:
                onthuld = (i, "naamval") in staat["gedaan"]
            else:
                onthuld = all((i, t["sleutel"]) in staat["gedaan"]
                              for t in taken if t["wi"] == i)
            gekleurd = p["ont_kleur"] and (toon_kleur or onthuld)
            if i == actief_wi:
                stijl += (f"color:{INKT};background:{MERK};border-radius:5px;"
                          f"font-weight:700;")
            elif gekleurd:
                nv = next((c for c in motor._ONTLEED_KLEUR if c in info), None)
                if nv:
                    stijl += (f"color:{motor._ONTLEED_KLEUR[nv]};"
                              f"border-bottom:2px solid {motor._ONTLEED_KLEUR[nv]};")
                else:
                    stijl += f"color:{TEKST};"
            else:
                stijl += f"color:{ZACHT};"
            delen.append(f"<span class='grieks' style='{stijl}'>{tekst}</span>")
        vers.content = (f"<div style='text-align:center;line-height:1.9;background:{VLAK};"
                        f"border:1px solid {RAND};border-radius:12px;padding:12px 10px'>"
                        + " ".join(delen) + "</div>")

    def teken_streepjes():
        streepjes.clear()
        with streepjes:
            for n in range(len(taken)):
                kleur = MERK if n < staat["i"] else (TEKST if n == staat["i"] else RAND)
                ui.element("div").style(f"flex:1;height:3px;border-radius:2px;background:{kleur}")

    def toon():
        opties.clear()
        terugkoppeling.clear()
        staat["beoordeeld"] = False
        if staat["i"] >= len(taken):
            teken_vers(-1, toon_kleur=True)
            gevraagd.text = f"Klaar — {staat['goed']} goed, {staat['fout']} fout."
            teller.text = ""
            knop.text = "Nieuw vers"
            teken_streepjes()
            return
        t = taken[staat["i"]]
        teken_vers(t["wi"])
        gevraagd.text = t["label"]
        teller.text = f"{staat['i'] + 1}/{len(taken)}"
        knop.text = "Ik weet het niet"
        teken_streepjes()
        teken_hulp(t)
        with opties:
            for rij in [t["opties"][i:i + 3] for i in range(0, len(t["opties"]), 3)]:
                with ui.row().classes("w-full gap-2 no-wrap"):
                    for o in rij:
                        ui.html(f"<button class='keuze' style='font-size:14px;"
                                f"text-align:center;padding:10px 4px'>{o}</button>").on(
                            "click", lambda _=None, keuze=o: kies(keuze)).style("flex:1")

    def teken_hulp(t):
        """Dezelfde hulpmiddelen als in de Streamlit-app, ingeklapt zodat ze het
        oefenscherm niet in de weg zitten."""
        hulpvak.clear()
        w = t["woord"]
        info = w.get("parsing_info", "") or ""
        lemma = w.get("lemma") or w.get("grieks", "")
        with hulpvak:
          if p["ont_rijtje"]:
            with ui.expansion("Bekijk het rijtje (spieken)").classes("w-full").style(
                    f"background:{VLAK};border:1px solid {RAND};border-radius:10px;"
                    f"font-size:13px"):
                tabellen = []
                try:
                    tabellen = motor._ontleed_tip_tabellen(
                        info, lemma, w.get("grieks_info", "")) or []
                except Exception:                                # noqa: BLE001
                    pass
                # _ontleed_tip_tabellen geeft NAMEN terug; de rijen staan in
                # laad_gramtabellen(). De naam zelf doorgeven maakt er een tabel van
                # één letter per rij van.
                alle = motor.laad_gramtabellen() or {}
                getoond = False
                for naam in tabellen[:2]:
                    rijen = alle.get(naam)
                    if not rijen:
                        continue
                    ui.label(naam).style(f"color:{MERK};font-size:12.5px;font-weight:600")
                    try:
                        ui.html(motor._render_gramtabel_html(rijen))
                        getoond = True
                    except Exception:                            # noqa: BLE001
                        pass
                if not getoond:
                    ui.label("Voor dit woord staat geen rijtje in de tabellen.").style(
                        f"color:{ZACHT};font-size:13px")
          if p["ont_vertaalhulp"]:
            with ui.expansion("Vertaalhulp bij deze vorm").classes("w-full").style(
                    f"background:{VLAK};border:1px solid {RAND};border-radius:10px;"
                    f"font-size:13px"):
                try:
                    h = motor._ontleed_vertaalhulp(info)
                except Exception:                                # noqa: BLE001
                    h = None
                ui.html(f"<div style='color:{ZACHT};font-size:13px;line-height:1.6'>"
                        f"{h if isinstance(h, str) else ' · '.join(h or [])}</div>"
                        if h else
                        f"<div style='color:{ZACHT};font-size:13px'>Geen extra hulp "
                        f"voor deze vorm.</div>")
          if p["ont_links"]:
            _boek = ref.rsplit(" ", 1)[0].replace(" ", "_").lower()
            _hs = ref.rsplit(" ", 1)[-1].replace(":", "/")
            ui.html(
                f"<div style='color:{ZACHT};font-size:12px;padding:4px 2px'>Op BibleHub: "
                f"<a style='color:{MERK}' target='_blank' rel='noopener' "
                f"href='https://biblehub.com/interlinear/{_boek}/{_hs}.htm'>"
                f"interlinear van dit vers</a>"
                + (f" · <a style='color:{MERK}' target='_blank' rel='noopener' "
                   f"href='https://biblehub.com/greek/{w.get('strong','')}.htm'>"
                   f"lexicon van dit woord</a>" if w.get("strong") else "")
                + "</div>")

    async def verwerk(t, juist, gekozen):
        staat["beoordeeld"] = True
        staat["goed"] += int(juist)
        staat["fout"] += int(not juist)
        e = stats.setdefault(t["sleutel"], {"g": 0, "f": 0})
        e["g"] = int(e.get("g", 0)) + int(juist)
        e["f"] = int(e.get("f", 0)) + int(not juist)
        staat["gedaan"].add((t["wi"], t["sleutel"]))
        g.tel_dag()
        # Niet de hele parsing tonen zolang je van dit woord nog dimensies moet doen —
        # dan staan de antwoorden op de volgende vragen er al.
        nog = [x for x in taken[staat["i"] + 1:] if x["wi"] == t["wi"]]
        alles_af = not nog
        if juist and alles_af:
            # Het dagdoel telt woorden die je helemaal hebt ontleed, niet losse deelvragen.
            g.dagdoel_plus("verzen")
        await run.io_bound(g.bewaar)
        # Geen actief woord meer: zo laat het net beantwoorde woord zijn naamvalkleur
        # zien in plaats van de cyaan markering.
        teken_vers(-1)
        opties.clear()
        kleur = GOED if juist else FOUT
        achter = "rgba(61,220,151,.10)" if juist else "rgba(255,107,129,.10)"
        info = t["woord"].get("parsing_info", "") or ""
        gloss = t["woord"].get("vertaling_nl") or t["woord"].get("vertaling_bsb") or ""
        zichtbaar = info if alles_af else f"{t['label']}: {', '.join(t['goed'])}"
        regel_gloss = (f"<div style='color:{TEKST};font-size:13.5px;margin-top:4px'>"
                       f"{gloss}</div>") if alles_af else ""
        hulp = ""
        if alles_af:
            try:
                h = motor._ontleed_vertaalhulp(info)
                if h:
                    hulp = (f"<div style='color:{ZACHT};font-size:12.5px;margin-top:10px;"
                            f"line-height:1.5'>"
                            f"{h if isinstance(h, str) else ' · '.join(h)}</div>")
            except Exception:                                    # noqa: BLE001
                pass
        terugkoppeling.clear()
        with terugkoppeling:
            ui.html(
                f"<div style='background:{achter};border:1px solid {kleur}40;"
                f"border-radius:14px;padding:16px 14px;text-align:center;width:100%'>"
                f"<div style='color:{kleur};font-weight:700;font-size:16px'>"
                f"{'✓ Goed!' if juist else '✗ ' + t['label'] + ' is ' + ', '.join(t['goed'])}"
                f"</div>"
                f"<div class='grieks' style='font-size:30px;color:{TEKST};margin-top:8px'>"
                f"{t['woord'].get('grieks', '')}</div>"
                f"<div style='color:{ZACHT};font-size:13px'>{zichtbaar}</div>"
                f"{regel_gloss}"
                f"{hulp}</div>")
        knop.text = "Volgende"

    async def kies(keuze):
        if staat["beoordeeld"] or staat["bezig"]:
            return
        staat["bezig"] = True
        try:
            t = taken[staat["i"]]
            await verwerk(t, keuze in t["goed"], keuze)
        finally:
            staat["bezig"] = False

    async def hoofdknop():
        if staat["bezig"]:
            return
        staat["bezig"] = True
        try:
            if staat["i"] >= len(taken):
                await run.io_bound(g.bewaar, True)
                ui.navigate.to("/oefenen/ontleden")
                return
            if staat["beoordeeld"]:
                staat["i"] += 1
                toon()
                return
            await verwerk(taken[staat["i"]], False, None)
        finally:
            staat["bezig"] = False

    knop.on_click(hoofdknop)
    toon()


# ============================================================== voortgang
# (sleutel in het dagboek, kleur, naam) — de stipjes onder de dagen in de oefenkalender.
KALENDER_ONDERDELEN = [("woorden_uniek", MERK, "woorden"), ("actief", "#f6c23e", "actief"),
                       ("stam", "#b07be0", "stamtijden"), ("struct", "#f6923c", "structuur"),
                       ("verzen", GOED, "ontleden"), ("verwar", "#20c997", "verwarparen")]
# (sleutel in het dagdoel, naam, hoogste instelbare waarde)
DAGDOEL_VELDEN = [("woorden", "Woorden", 40), ("actief", "Actief beheersen", 30),
                  ("stam", "Stamtijden", 20), ("struct", "Structuurwoorden", 20),
                  ("verzen", "Woorden ontleden", 20), ("verwar", "Verwarparen", 15)]
TENTAMENS = [("Grieks 1", "les 1–6", range(1, 7)), ("Grieks 2", "les 7–12", range(7, 13)),
             ("Grieks 3", "les 13–14", range(13, 15))]
ONTLEED_DIMS = [("woordsoort", "Woordsoort"), ("naamval", "Naamval"), ("geslacht", "Geslacht"),
                ("getal", "Getal"), ("tijd", "Tijd"), ("wijs", "Wijs"),
                ("diathese", "Diathese"), ("persoon", "Persoon"), ("vertaling", "Vertaling")]


def _kalender_kleur(n):
    """Hoe voller de dag, hoe feller het groen."""
    if n <= 0:
        return "#2a2f36"
    if n < 5:
        return "#16432c"
    if n < 15:
        return "#1f7a4d"
    if n < 30:
        return "#2aa866"
    return "#39d17f"


def dagkalender_html(dagen, dagboek, doelen):
    """Vijf weken oefenritme, met per dag hoeveel je deed en een stipje per onderdeel
    waarvan je die dag het dagdoel haalde. Zelfde kalender als in de Streamlit-app."""
    vandaag_d = date.today()
    start = vandaag_d - timedelta(days=vandaag_d.weekday() + 28)   # maandag, vier weken terug
    kop = "".join(f"<div style='text-align:center;font-size:11px;color:{ZACHT}'>{d}</div>"
                  for d in ("ma", "di", "wo", "do", "vr", "za", "zo"))
    cellen = ""
    for i in range(35):
        d = start + timedelta(days=i)
        sleutel = d.strftime("%Y-%m-%d")
        n = int((dagen or {}).get(sleutel, 0) or 0)
        regel = (dagboek or {}).get(sleutel) or {}
        toekomst = d > vandaag_d
        achter = "#1a1d22" if toekomst else _kalender_kleur(n)
        rand = "2px solid #f6c23e" if d == vandaag_d else "1px solid rgba(255,255,255,.06)"
        stippen = ""
        for veld, kleur, _naam in KALENDER_ONDERDELEN:
            doel = int(doelen.get("woorden" if veld == "woorden_uniek" else veld, 0) or 0)
            if doel and int(regel.get(veld, 0) or 0) >= doel:
                stippen += (f"<span style='display:inline-block;width:9px;height:9px;"
                            f"border-radius:50%;background:{kleur};margin:0 1px'></span>")
        aantal = (f"<div style='font-size:19px;font-weight:800;color:{TEKST};line-height:1'>"
                  f"{n}</div>" if n and not toekomst else
                  f"<div style='font-size:19px;line-height:1;color:#4b525c'>·</div>")
        cellen += (
            f"<div style='background:{achter};border:{rand};border-radius:8px;height:60px;"
            f"padding:4px;position:relative;display:flex;flex-direction:column;"
            f"align-items:center;justify-content:center;gap:3px;"
            f"opacity:{'0.35' if toekomst else '1'}'>"
            f"<div style='position:absolute;top:3px;left:5px;font-size:9.5px;font-weight:600;"
            f"color:#aeb6c0;line-height:1'>{d.day}</div>{aantal}"
            f"<div style='text-align:center;min-height:9px'>{stippen}</div></div>")
    legenda = " · ".join(f"<span style='color:{kleur}'>●</span> {naam}"
                         for _v, kleur, naam in KALENDER_ONDERDELEN)
    return (f"<div style='display:grid;grid-template-columns:repeat(7,1fr);gap:4px;"
            f"margin-bottom:6px'>{kop}</div>"
            f"<div style='display:grid;grid-template-columns:repeat(7,1fr);gap:4px'>{cellen}</div>"
            f"<div style='font-size:11px;color:{ZACHT};margin-top:8px;line-height:1.8'>"
            f"Getal = geoefende items die dag · stip = dagdoel gehaald voor: {legenda}</div>")


def _meterbalk(label, gedaan, doel, kleur=MERK):
    """Balkje met 'gedaan van doel' erboven — voor dagdoelen en beheersing per onderdeel."""
    deel = min(1.0, gedaan / doel) if doel else 1.0
    return (f"<div style='margin-bottom:10px'>"
            f"<div style='display:flex;justify-content:space-between;font-size:12.5px;"
            f"color:{TEKST};gap:8px'><span>{label}</span>"
            f"<span style='color:{ZACHT};white-space:nowrap'>{gedaan}/{doel}</span></div>"
            f"<div style='width:100%;height:6px;border-radius:3px;background:{RAND};"
            f"margin-top:4px'><div style='width:{deel * 100:.0f}%;height:6px;"
            f"border-radius:3px;background:{kleur}'></div></div></div>")


def studietijd_prognose(woorden, doel_streak=16, per_dag=30, accuratesse=None):
    """Hoe lang je nog bezig bent tot deze woorden allemaal de gevraagde streak halen.
    Zelfde rekenwijze als bereken_studietijd_forecast in de Streamlit-app: de schuld is
    het aantal streak-punten dat je tekortkomt, en elke fout kost meer dan een goede
    beurt oplevert — daarom weegt je accuratesse zo zwaar."""
    schuld = sum(max(0, doel_streak - int(w.get("streak", 0) or 0)) for w in woorden)
    if not woorden or schuld <= 0:
        return {"dagen": 0, "einddatum": "Doel al bereikt", "schuld": 0, "winst": 0.0}
    if accuratesse is None:
        goed = sum(int(w.get("score_goed", 0) or 0) for w in woorden)
        fout = sum(int(w.get("score_fout", 0) or 0) for w in woorden)
        deel = goed / (goed + fout) if goed + fout > 10 else 0.75
    else:
        deel = accuratesse / 100.0
    deel = max(0.50, min(1.0, deel))
    winst = max(0.08, deel * 1.2 - (1.0 - deel) * 2.0)
    dagen = math.ceil(schuld / (max(1, per_dag) * winst))
    return {"dagen": dagen, "schuld": schuld, "winst": round(winst, 2),
            "einddatum": (date.today() + timedelta(days=dagen)).strftime("%d-%m-%Y")}


def gemiddeld_tempo(g, dagen_terug=14):
    """Gemiddeld aantal geoefende items per dag over de laatste twee weken — de
    startwaarde voor de planner, zodat de schatting bij jouw echte tempo begint."""
    dagen = g.stats.get("dag_stats") or {}
    grens = (date.today() - timedelta(days=dagen_terug - 1)).strftime("%Y-%m-%d")
    vandaag_s = date.today().strftime("%Y-%m-%d")
    totaal = sum(int(n or 0) for d, n in dagen.items() if grens <= str(d) <= vandaag_s)
    return int(round(totaal / dagen_terug))


def voortgang_cijfers(g):
    """De zware fasetellingen voor dit dashboard. Gecached op een sleutel die meebeweegt
    met je oefeningen, zodat hij vanzelf ververst zodra er iets verandert."""
    dagen = g.stats.get("dag_stats") or {}
    sleutel = f"{g.sleutel}:{sum(int(n or 0) for n in dagen.values())}"
    return motor.voortgang_kernstats(
        sleutel, g.woorden, g.stats.get("stam_stats") or {}, motor.laad_stamtijden_db(),
        g.stats.get("struct_stats") or {}, motor.laad_structuurwoorden_db())


def probleemwoorden(g):
    """Woorden die blijven haperen: minstens drie beurten, minstens twee fouten, nog niet
    boven de prille start uit en meer dan 40% fout. Dat zijn je beste kandidaten voor
    gericht oefenen — moeilijkste eerst."""
    uit = []
    for w in g.woorden:
        goed = int(w.get("score_goed", 0) or 0)
        fout = int(w.get("score_fout", 0) or 0)
        totaal = goed + fout
        if totaal >= 3 and fout >= 2 and int(w.get("streak", 0) or 0) <= 3:
            deel = fout / totaal
            if deel >= 0.4:
                uit.append((deel, fout, w))
    uit.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return uit


def badgecijfers(g, cijfers):
    """De samengevatte statistieken waar motor.badge_definities de badges uit afleidt."""
    sv, ss, sr = cijfers["stats_vocab"], cijfers["stats_stam"], cijfers["stats_str"]
    goed = cijfers["tot_goed_v"] + cijfers["tot_goed_s"] + cijfers["tot_goed_st"]
    fout = cijfers["tot_fout_v"] + cijfers["tot_fout_s"] + cijfers["tot_fout_st"]
    xp = (motor.bereken_xp(g.woorden)
          + motor.bereken_xp_stam(g.stats.get("stam_stats") or {})
          + motor.bereken_xp_struct(g.stats.get("struct_stats") or {})
          + motor.bereken_xp_actief(g.stats.get("actief_stats") or {}))
    return {
        "beoordelingen": goed + fout,
        "oefendagen": len(g.stats.get("dag_stats") or {}),
        "dagstreak": g.dagstreak(),
        "accuratesse": round(100 * goed / (goed + fout)) if goed + fout else 0,
        "beheerst": (sv["Beheerst"] + sv["Mastery"] + ss["Beheerst"] + ss["Mastery"]
                     + sr["Beheerst"] + sr["Mastery"]),
        "mastery": sv["Mastery"] + ss["Mastery"] + sr["Mastery"],
        "dekking": nt_dekking(cijfers),
        "verwar_opgelost": int((g.stats.get("badges") or {}).get("_verwar_opgelost", 0)),
        "niveau": motor.niveau_van_xp(xp)["niveau"],
        "stam_beheerst": ss["Beheerst"] + ss["Mastery"],
        "struct_beheerst": sr["Beheerst"] + sr["Mastery"],
    }


def nt_dekking(cijfers):
    """Ruwe schatting van hoeveel van het NT je zonder woordenboek leest: het aandeel van
    de tekst dat door jouw beheerste woorden wordt gedekt, afgetopt op 78% — de rest zijn
    woorden die buiten deze lijst vallen."""
    totaal = cijfers.get("totale_freq") or 0
    return int(cijfers.get("bekende_freq", 0) / totaal * 78) if totaal else 0


def scorebordregel(g):
    """Alleen cijfers voor de gedeelde ranglijst — geen voortgangsdata. Dezelfde kolommen
    als de Streamlit-app schrijft, zodat beide apps één scorebord vullen."""
    stam = g.stats.get("stam_stats") or {}
    struct = g.stats.get("struct_stats") or {}
    actief = g.stats.get("actief_stats") or {}
    xp = (motor.bereken_xp(g.woorden) + motor.bereken_xp_stam(stam)
          + motor.bereken_xp_struct(struct) + motor.bereken_xp_actief(actief))
    niv = motor.niveau_van_xp(xp)
    s_pog, s_beh = motor._beheerst_telling(stam)
    r_pog, r_beh = motor._beheerst_telling(struct)
    a_pog, a_beh = motor._beheerst_telling(actief)
    dagen = g.stats.get("dag_stats") or {}
    grens = (date.today() - timedelta(days=6)).strftime("%Y-%m-%d")
    vandaag_s = date.today().strftime("%Y-%m-%d")
    return {
        "gebruiker": g.naam,
        "xp": xp, "niveau": niv["niveau"], "titel": niv["titel"],
        "week": sum(int(n or 0) for d, n in dagen.items() if grens <= str(d) <= vandaag_s),
        "totaal": sum(int(n or 0) for n in dagen.values()),
        "badges": len([k for k in (g.stats.get("badges") or {}) if not str(k).startswith("_")]),
        "w_beh": sum(1 for w in g.woorden if int(w.get("streak", 0) or 0) >= 16),
        "w_pog": sum(int(w.get("score_goed", 0) or 0) + int(w.get("score_fout", 0) or 0)
                     for w in g.woorden),
        "a_beh": a_beh, "a_pog": a_pog, "s_beh": s_beh, "s_pog": s_pog,
        "r_beh": r_beh, "r_pog": r_pog,
    }


def _heel(rij, kolom):
    try:
        return int(float(rij.get(kolom, 0) or 0))
    except (TypeError, ValueError):
        return 0


def ranglijst(rijen):
    """De regels van het Scorebord-tabblad omzetten naar spelers, ontdubbeld op naam."""
    spelers = {}
    for r in rijen:
        naam = str(r.get("gebruiker", "")).strip()
        if not naam:
            continue
        speler = {"naam": naam, "xp": _heel(r, "xp"), "niveau": _heel(r, "niveau"),
                  "titel": str(r.get("titel", "")), "week": _heel(r, "week"),
                  "totaal": _heel(r, "totaal"), "badges": _heel(r, "badges"),
                  "beheerst": (_heel(r, "w_beh") + _heel(r, "a_beh")
                               + _heel(r, "s_beh") + _heel(r, "r_beh"))}
        if naam not in spelers or speler["xp"] > spelers[naam]["xp"]:
            spelers[naam] = speler
    return list(spelers.values())


def voortgang_csv(g):
    """Je woordenschat als CSV, met dezelfde kolommen als de download in de Streamlit-app."""
    buffer = io.StringIO()
    schrijver = csv.writer(buffer)
    schrijver.writerow(["grieks", "nederlands", "streak", "score_goed", "score_fout",
                        "laatst_geoefend"])
    for w in g.woorden:
        schrijver.writerow([w.get("grieks", ""), w.get("nederlands", ""),
                            int(w.get("streak", 0) or 0), int(w.get("score_goed", 0) or 0),
                            int(w.get("score_fout", 0) or 0), w.get("laatst_geoefend", "")])
    # utf-8-sig: anders toont Excel de Griekse letters als hiërogliefen.
    return buffer.getvalue().encode("utf-8-sig")


def _badgeraster(badges, bewaard):
    """Behaalde badges vooraan met de datum erbij, de rest gedimd met hoever je bent."""
    vakjes = ""
    for b in sorted(badges, key=lambda x: not x["behaald"]):
        rand = MERK if b["behaald"] else RAND
        kleur = TEKST if b["behaald"] else ZACHT
        datum = str(bewaard.get(b["id"], "") or "")
        onder = (_kort_datum(datum) if datum else "behaald") if b["behaald"] \
            else (b["voortgang"] or "—")
        vakjes += (f"<div title='{b['uitleg']}' style='border:1px solid {rand};"
                   f"border-radius:10px;padding:8px 4px;text-align:center;"
                   f"opacity:{'1' if b['behaald'] else '.45'}'>"
                   f"<div style='font-size:22px;line-height:1.1'>{b['icon']}</div>"
                   f"<div style='color:{kleur};font-size:11.5px;font-weight:600;"
                   f"line-height:1.3;margin-top:2px'>{b['titel']}</div>"
                   f"<div style='color:{ZACHT};font-size:10.5px'>{onder}</div></div>")
    return (f"<div style='display:grid;gap:8px;"
            f"grid-template-columns:repeat(auto-fill,minmax(92px,1fr))'>{vakjes}</div>")


def _fasen_van(streaks):
    """Vier fasen tellen uit een reeks streaks — zelfde grenzen als de rest van de app."""
    uit = {"Nieuw": 0, "In Training": 0, "Beheerst": 0, "Mastery": 0}
    for s in streaks:
        s = int(s or 0)
        if s >= 30:
            uit["Mastery"] += 1
        elif s >= 16:
            uit["Beheerst"] += 1
        elif s >= 1:
            uit["In Training"] += 1
        else:
            uit["Nieuw"] += 1
    return uit


def _onderdeelblok(g, cijfers):
    """Per onderdeel hoeveel je beheerst, met de verdeling over de vier fasen eronder."""
    modules = [("Woorden", cijfers["stats_vocab"]),
               ("Stamtijden", cijfers["stats_stam"]),
               ("Structuurwoorden", cijfers["stats_str"]),
               ("Actief beheersen", _fasen_van(c["streak"] for c in af_cellen(g)))]
    blokken = ""
    for naam, fasen in modules:
        totaal = sum(fasen.values())
        blokken += _meterbalk(naam, fasen["Beheerst"] + fasen["Mastery"], totaal)
        blokken += (f"<div style='color:{ZACHT};font-size:11.5px;margin:-6px 0 12px'>"
                    f"nieuw {fasen['Nieuw']} · training {fasen['In Training']} · "
                    f"beheerst {fasen['Beheerst']} · mastery {fasen['Mastery']}</div>")
    return blokken


def _probleemtabel(rijen):
    """Eén regel per hardnekkig woord: wat het betekent en hoe scheef het staat."""
    regels = ""
    for deel, fout, w in rijen:
        regels += (
            f"<div style='display:flex;justify-content:space-between;gap:10px;"
            f"border-top:1px solid {RAND};padding:7px 0'>"
            f"<div style='min-width:0'>"
            f"<span class='grieks' style='font-size:17px;color:{TEKST}'>{w.get('grieks','')}</span>"
            f"<div style='color:{ZACHT};font-size:12px;overflow:hidden;white-space:nowrap;"
            f"text-overflow:ellipsis'>{str(w.get('nederlands',''))[:40]}</div></div>"
            f"<div style='text-align:right;white-space:nowrap'>"
            f"<span style='color:{FOUT};font-size:13px;font-weight:600'>"
            f"{int(deel * 100)}% fout</span>"
            f"<div style='color:{ZACHT};font-size:11.5px'>"
            f"{int(w.get('score_goed', 0) or 0)} goed · {fout} fout · "
            f"streak {int(w.get('streak', 0) or 0)}</div></div></div>")
    return regels


def _prognoseblok(prognose, woorden, doel_streak):
    """De uitkomst van de planner: verdeling nu, en wanneer je klaar bent."""
    fasen = _fasen_van(w.get("streak", 0) for w in woorden)
    verdeling = (f"<div style='color:{ZACHT};font-size:12px;margin-bottom:10px'>"
                 f"{len(woorden)} woorden · nieuw {fasen['Nieuw']} · training "
                 f"{fasen['In Training']} · beheerst {fasen['Beheerst']} · mastery "
                 f"{fasen['Mastery']}</div>")
    if prognose["schuld"] <= 0:
        return (verdeling +
                f"<div style='background:rgba(61,220,151,.10);border:1px solid {GOED}40;"
                f"border-radius:12px;padding:14px;color:{TEKST};font-size:14px'>"
                f"Doel al bereikt — alles in deze selectie staat op streak "
                f"{doel_streak} of hoger.</div>")
    return (verdeling +
            f"<div style='background:{VLAK};border-left:4px solid {MERK};border-radius:10px;"
            f"padding:14px'>"
            f"<div style='color:{ZACHT};font-size:11.5px;letter-spacing:.6px;"
            f"text-transform:uppercase'>Verwachte afrondingsdatum</div>"
            f"<div style='color:{MERK};font-size:28px;font-weight:800;margin:2px 0 8px'>"
            f"{prognose['einddatum']}</div>"
            f"<div style='color:{TEKST};font-size:13.5px'>Doorlooptijd "
            f"{prognose['dagen']} dagen.</div>"
            f"<div style='color:{ZACHT};font-size:12px;margin-top:8px'>"
            f"Nog {prognose['schuld']} streak-punten te gaan · ongeveer "
            f"{prognose['winst']} punt winst per beurt. Een fout kost meer dan een goede "
            f"beurt oplevert, dus accuratesse telt zwaarder dan aantallen.</div></div>")


def _ranglijstblok(spelers, eigen_naam):
    """Podium van deze week plus de all-time stand op XP, met jouw regel gemarkeerd."""
    def naamregel(speler):
        return ("👉 " if speler["naam"] == eigen_naam else "") + speler["naam"]

    week = sorted([s for s in spelers if s["week"] > 0], key=lambda s: -s["week"])[:3]
    podium = ""
    for medaille, speler in zip(("🥇", "🥈", "🥉"), week):
        eigen = speler["naam"] == eigen_naam
        podium += (f"<div style='flex:1;text-align:center;padding:6px;border-radius:10px;"
                   f"background:{'rgba(51,204,255,.12)' if eigen else 'transparent'}'>"
                   f"<div style='font-size:26px'>{medaille}</div>"
                   f"<div style='color:{TEKST};font-size:13.5px;font-weight:600'>"
                   f"{naamregel(speler)}</div>"
                   f"<div style='color:{MERK};font-size:18px;font-weight:800'>"
                   f"{speler['week']}</div>"
                   f"<div style='color:{ZACHT};font-size:11px'>deze week</div></div>")
    kop = (f"<div style='display:flex;gap:6px;margin-bottom:10px'>{podium}</div>"
           if podium else
           f"<div style='color:{ZACHT};font-size:13px;margin-bottom:10px'>"
           f"Deze week heeft nog niemand geoefend.</div>")
    regels = ""
    alles = sorted(spelers, key=lambda s: -s["xp"])
    for plek, speler in enumerate(alles, 1):
        eigen = speler["naam"] == eigen_naam
        regels += (f"<div style='display:flex;justify-content:space-between;gap:10px;"
                   f"border-top:1px solid {RAND};padding:7px 0;"
                   f"color:{MERK if eigen else TEKST};font-size:13px'>"
                   f"<div style='min-width:0;overflow:hidden;white-space:nowrap;"
                   f"text-overflow:ellipsis'>{plek}. {naamregel(speler)}"
                   f"<div style='color:{ZACHT};font-size:11.5px'>niveau "
                   f"{speler['niveau']} · {speler['titel']}</div></div>"
                   f"<div style='text-align:right;white-space:nowrap'>{speler['xp']} XP"
                   f"<div style='color:{ZACHT};font-size:11.5px'>🏅 {speler['badges']} · "
                   f"{speler['beheerst']} beheerst</div></div></div>")
    return kop + regels


def _uitklap(titel):
    """Uitklapper in de huisstijl van de kaarten."""
    return ui.expansion(titel).classes("kaart w-full").props("dense expand-separator").style(
        f"color:{TEKST}")


@ui.page("/voortgang")
def voortgangpagina():
    g = _bewaakt()
    if not g:
        return
    sam = g.samenvatting()
    cijfers = voortgang_cijfers(g)
    xp = motor.bereken_xp(g.woorden)
    niv = motor.niveau_van_xp(xp)
    doelen = g.dagdoel()
    dagboek = (g.stats.get("dagdoel") or {}).get("log") or {}
    vandaag_log = dagboek.get(gebruikers.vandaag()) or {}

    with ui.column().classes("inhoud w-full gap-3"):
        ui.label("Voortgang").style("font-size:26px;font-weight:700")

        with ui.element("div").classes("kaart w-full"):
            ui.label(f"Niveau {niv['niveau']} · {niv['titel']}").style(
                f"color:{MERK};font-size:20px;font-weight:700")
            ui.label(f"{niv['xp_totaal']} XP · rang {niv['rang_nr']} van {niv['rang_totaal']}").style(
                f"color:{ZACHT};font-size:13px")
            deel = niv["xp_in_niveau"] / max(1, niv["xp_voor_volgend"])
            ui.html(f"<div style='width:100%;height:6px;border-radius:3px;background:{RAND};"
                    f"margin:10px 0 6px'><div style='width:{min(1, deel)*100:.0f}%;height:6px;"
                    f"border-radius:3px;background:{MERK}'></div></div>")
            ui.label(f"Nog {niv['xp_voor_volgend'] - niv['xp_in_niveau']} XP tot "
                     f"{niv['volgende_rang']}.").style(f"color:{TEKST};font-size:13px")

        tegels = [(f"{sam['accuratesse']}%", "accuratesse"), (sam["beheerst"], "beheerst"),
                  (sam["dagen"], "oefendagen"), (f"🔥 {g.dagstreak()}", "dagen op rij"),
                  (sam["vandaag"], "vandaag"), (f"~{nt_dekking(cijfers)}%", "NT-dekking")]
        for rij in (tegels[:3], tegels[3:]):
            with ui.row().classes("w-full gap-2 no-wrap"):
                for waarde, label in rij:
                    with ui.element("div").classes("kaart").style("flex:1;text-align:center"):
                        ui.label(str(waarde)).style(
                            f"font-size:24px;font-weight:800;color:{MERK};line-height:1.1")
                        ui.label(label).style(f"color:{ZACHT};font-size:11.5px")

        # --- oefenritme -------------------------------------------------------
        with ui.element("div").classes("kaart w-full"):
            ui.label("Jouw oefenritme").style(f"color:{TEKST};font-size:15px;font-weight:600")
            ui.html(dagkalender_html(g.stats.get("dag_stats") or {}, dagboek, doelen))
            if not sam["vandaag"]:
                ui.label("Nog niets gedaan vandaag — een korte ronde houdt je streaks vers.").style(
                    f"color:{ZACHT};font-size:12.5px;margin-top:6px")

        # --- dagdoel ----------------------------------------------------------
        with _uitklap("Vandaag per onderdeel"):
            ui.label("Deze tellers lopen automatisch mee zodra je goed antwoordt.").style(
                f"color:{ZACHT};font-size:12.5px;margin-bottom:8px")
            for sleutel, naam, _max in DAGDOEL_VELDEN:
                # 'Woorden' telt verschillende woorden: hetzelfde woord vaker oefenen
                # telt één keer. De andere tellers tellen elk goed antwoord.
                gedaan = (g.woorden_vandaag() if sleutel == "woorden"
                          else int(vandaag_log.get(sleutel, 0) or 0))
                ui.html(_meterbalk(naam, gedaan, int(doelen.get(sleutel, 0) or 0)))

        with _uitklap("Dagelijks doel instellen"):
            schuiven = {}
            for sleutel, naam, hoogste in DAGDOEL_VELDEN:
                schuiven[sleutel] = ui.number(
                    naam, value=int(doelen.get(sleutel, 0) or 0), min=0, max=hoogste,
                    step=1).props("outlined dark dense").classes("w-full")
            ui.label("Zet een doel op 0 om het te laten vervallen; dan verschijnt er ook "
                     "geen stipje meer in de kalender.").style(
                f"color:{ZACHT};font-size:12px;margin:6px 0")

            async def bewaar_doelen():
                g.zet_dagdoel({s: (v.value or 0) for s, v in schuiven.items()})
                await run.io_bound(g.bewaar, True)
                ui.notify("Dagdoelen opgeslagen", position="top", color="dark")
                ui.navigate.to("/voortgang")

            ui.button("Doelen opslaan", on_click=bewaar_doelen).props("unelevated").style(
                f"background:{MERK};color:{INKT};font-weight:700;width:100%")

        # --- woorden ----------------------------------------------------------
        with ui.element("div").classes("kaart w-full"):
            ui.label("Woorden").style(f"color:{TEKST};font-size:15px;font-weight:600")
            ui.label(f"{sam['geoefend']} van de {len(g.woorden)} geoefend · "
                     f"{sam['goed']} goed, {sam['fout']} fout").style(
                f"color:{ZACHT};font-size:13px")
            deel = sam["geoefend"] / max(1, len(g.woorden))
            ui.html(f"<div style='width:100%;height:6px;border-radius:3px;background:{RAND};"
                    f"margin-top:8px'><div style='width:{deel*100:.0f}%;height:6px;"
                    f"border-radius:3px;background:{MERK}'></div></div>")

        # --- badges -----------------------------------------------------------
        badges = motor.badge_definities(badgecijfers(g, cijfers))
        behaald = [b for b in badges if b["behaald"]]
        bewaard = g.stats.setdefault("badges", {})
        nieuw = [b for b in behaald if b["id"] not in bewaard]
        for b in nieuw:
            bewaard[b["id"]] = gebruikers.vandaag()
        if nieuw:
            # Meteen vastleggen wanneer je ze behaalde, anders staat er bij de volgende
            # sessie opnieuw 'nieuw' bij badges die je allang had.
            async def bewaar_badges():
                await run.io_bound(g.bewaar, True)

            ui.timer(0.2, bewaar_badges, once=True)
        with _uitklap(f"Badges — {len(behaald)} van de {len(badges)}"):
            if nieuw:
                ui.label("Nieuw: " + " · ".join(f"{b['icon']} {b['titel']}" for b in nieuw)).style(
                    f"color:{GOED};font-size:13px;margin-bottom:8px")
            ui.html(_badgeraster(badges, bewaard))

        # --- per onderdeel ----------------------------------------------------
        with _uitklap("Voortgang per onderdeel"):
            ui.html(_onderdeelblok(g, cijfers))
            lek = [w for w in g.woorden if 16 <= int(w.get("streak", 0) or 0) <= 17]
            if lek:
                ui.label(f"🪣 {len(lek)} woorden balanceren op het randje van je "
                         f"langetermijngeheugen (streak 16 of 17). Eén foutje en ze vallen "
                         f"terug. Kies 'Knelpunten' om ze te stutten.").style(
                    f"color:{TEKST};font-size:12.5px;line-height:1.6;margin-top:4px")
            else:
                ui.label("🛡️ Al je beheerste woorden staan stevig (streak 18 of hoger).").style(
                    f"color:{ZACHT};font-size:12.5px;margin-top:4px")
            ui.label("Per tentamen").style(
                f"color:{TEKST};font-size:14px;font-weight:600;margin-top:12px")
            ui.label("Een item telt als beheerst vanaf streak 16.").style(
                f"color:{ZACHT};font-size:12px;margin-bottom:6px")
            cellen = af_cellen(g)
            for naam, lessen, bereik in TENTAMENS:
                woorden = [w for w in g.woorden if motor.veilig_les_nummer(w) in bereik]
                rijtjes = [c for c in cellen if c["niveau"] == naam]
                ui.label(f"{naam} · {lessen}").style(
                    f"color:{MERK};font-size:13px;font-weight:600;margin-top:6px")
                ui.html(_meterbalk(
                    "Woordenschat",
                    sum(1 for w in woorden if int(w.get("streak", 0) or 0) >= 16), len(woorden)))
                ui.html(_meterbalk(
                    "Rijtjes", sum(1 for c in rijtjes if c["streak"] >= 16), len(rijtjes)))
            ontleed = g.stats.get("ontleed_stats") or {}
            if any((int(v.get("g", 0)) + int(v.get("f", 0))) > 0
                   for v in ontleed.values() if isinstance(v, dict)):
                ui.label("Ontleden per onderdeel").style(
                    f"color:{TEKST};font-size:14px;font-weight:600;margin-top:12px")
                ui.label("Hoe vaak je het onderdeel in één keer goed had — je tentamenmaat.").style(
                    f"color:{ZACHT};font-size:12px;margin-bottom:6px")
                for sleutel, naam in ONTLEED_DIMS:
                    e = ontleed.get(sleutel) or {}
                    totaal = int(e.get("g", 0) or 0) + int(e.get("f", 0) or 0)
                    if totaal:
                        ui.html(_meterbalk(naam, int(e.get("g", 0) or 0), totaal))

        # --- probleemwoorden ---------------------------------------------------
        lastig = probleemwoorden(g)
        with _uitklap(f"Hardnekkige probleemwoorden — {len(lastig)}"):
            ui.label("Woorden die je al vaker deed maar die blijven haperen: veel fouten en "
                     "nog een lage streak. Oefen ze gericht via 'Knelpunten'.").style(
                f"color:{ZACHT};font-size:12.5px;line-height:1.6;margin-bottom:8px")
            if not lastig:
                ui.label("Niets blijft structureel haperen. Sterk!").style(
                    f"color:{GOED};font-size:13px")
            else:
                ui.html(_probleemtabel(lastig[:25]))
                if len(lastig) > 25:
                    ui.label(f"De 25 hardnekkigste van {len(lastig)} getoond.").style(
                        f"color:{ZACHT};font-size:12px;margin-top:6px")

        # --- studieplanner -----------------------------------------------------
        with _uitklap("Studieplanner — wanneer ken ik alles?"):
            tempo = gemiddeld_tempo(g)
            kies_groep = ui.select({naam: f"{naam} · {lessen}" for naam, lessen, _b in TENTAMENS},
                                   value=TENTAMENS[0][0], label="Tentamen").props(
                "outlined dark dense").classes("w-full")
            kies_diepte = ui.number("Gewenste kennis-diepte (streak)", value=16, min=2, max=30,
                                    step=1).props("outlined dark dense").classes("w-full")
            ui.label("16 = beheerst (de norm). 8 = genoeg om te herkennen in een tekst. "
                     "30 = vloeiend.").style(f"color:{ZACHT};font-size:12px")
            kies_tempo = ui.number("Woorden per dag", value=max(5, tempo) if tempo else 30,
                                   min=5, max=500, step=5).props(
                "outlined dark dense").classes("w-full")
            if tempo:
                ui.label(f"Je tempo van de afgelopen twee weken: ongeveer {tempo} items per "
                         f"dag. Pas gerust aan.").style(f"color:{ZACHT};font-size:12px")
            kies_acc = ui.number("Verwachte accuratesse (%)", value=max(50, sam["accuratesse"]),
                                 min=50, max=100, step=1).props(
                "outlined dark dense").classes("w-full")
            uitkomst = ui.column().classes("w-full gap-1").style("margin-top:10px")

            def reken():
                bereik = next(b for naam, _l, b in TENTAMENS if naam == kies_groep.value)
                woorden = [w for w in g.woorden if motor.veilig_les_nummer(w) in bereik]
                p = studietijd_prognose(woorden, int(kies_diepte.value or 16),
                                        int(kies_tempo.value or 30), int(kies_acc.value or 78))
                uitkomst.clear()
                with uitkomst:
                    ui.html(_prognoseblok(p, woorden, int(kies_diepte.value or 16)))

            for veld in (kies_groep, kies_diepte, kies_tempo, kies_acc):
                veld.on_value_change(lambda _=None: reken())
            reken()

        # --- competitie --------------------------------------------------------
        with _uitklap("Competitie — hoe sta je erbij?") as competitie:
            ui.label("Het scorebord vergelijkt alleen cijfers: XP, niveau en hoeveel je "
                     "oefent. Klasgenoten verschijnen zodra zij hebben geoefend.").style(
                f"color:{ZACHT};font-size:12.5px;line-height:1.6")
            bord = ui.column().classes("w-full gap-2")
            geladen = {"ja": False}

            async def laad_bord():
                geladen["ja"] = True
                bord.clear()
                with bord:
                    ui.label("Bezig met ophalen…").style(f"color:{ZACHT};font-size:13px")
                try:
                    await run.io_bound(opslag.schrijf_scorebord, scorebordregel(g))
                    rijen = await run.io_bound(opslag.lees_scorebord)
                except Exception as e:                           # noqa: BLE001
                    bord.clear()
                    with bord:
                        ui.label(f"Het scorebord is nu niet bereikbaar ({e}).").style(
                            f"color:{ZACHT};font-size:13px")
                    return
                spelers = ranglijst(rijen)
                bord.clear()
                with bord:
                    if not spelers:
                        ui.label("Nog geen groepsgegevens.").style(
                            f"color:{ZACHT};font-size:13px")
                        return
                    ui.html(_ranglijstblok(spelers, g.naam))

            def bij_openen(e):
                """Pas ophalen als je de uitklapper opent — anders kost elk bezoek aan deze
                pagina een lees- en schrijfbeurt op de gedeelde Sheet."""
                if e.value and not geladen["ja"]:
                    return laad_bord()
                return None

            competitie.on_value_change(bij_openen)
            ui.button("Ranglijst verversen", on_click=laad_bord).props("flat").style(
                f"color:{MERK};border:1px solid {RAND};border-radius:8px;width:100%")

        # --- export ------------------------------------------------------------
        ui.button("Woordenschat downloaden als CSV",
                  on_click=lambda: ui.download.content(
                      voortgang_csv(g), "mijn_grieks_voortgang.csv")).props("flat").style(
            f"color:{MERK};border:1px solid {RAND};border-radius:10px")

        with ui.element("div").classes("kaart w-full"):
            ui.label("Meer overzichten").style(f"color:{TEKST};font-size:15px;font-weight:600")
            ui.label("De studieplanner per tentamen, de aartsrivalen en alle grafieken "
                     "staan in de volledige app.").style(
                f"color:{ZACHT};font-size:13px;line-height:1.5")
            streamlit_link(g)

        ui.button("Uitloggen", on_click=lambda: (
            _sessies.pop(app.storage.user.get("sleutel"), None),
            app.storage.user.clear(), ui.navigate.to("/"))).props("flat").style(
            f"color:{ZACHT};border:1px solid {RAND};border-radius:10px;margin-top:8px")
    onderbalk("Voortgang")


# ============================================================== lijst
LIJST_SOORTEN = ["Woordenschat", "Mijn verwarwoorden", "Structuurwoorden", "Stamtijden"]
LIJST_MAX = 200          # zoveel regels tegelijk; meer maakt de pagina onbruikbaar traag


def _lijstregel(links, rechts, onder="", kleur=None):
    return (f"<div style='display:flex;justify-content:space-between;gap:10px;"
            f"border-top:1px solid {RAND};padding:7px 0'>"
            f"<div style='min-width:0'>{links}"
            f"{f'<div style=\"color:{ZACHT};font-size:11.5px\">{onder}</div>' if onder else ''}"
            f"</div>"
            f"<div style='text-align:right;white-space:nowrap;font-size:12.5px;"
            f"color:{kleur or ZACHT}'>{rechts}</div></div>")


def lijst_woorden(g, zoek, alleen_geoefend):
    regels = []
    for w in g.woorden:
        grieks = str(w.get("grieks", ""))
        ned = str(w.get("nederlands", ""))
        if zoek and zoek not in grieks.lower() and zoek not in ned.lower():
            continue
        streak = int(w.get("streak", 0) or 0)
        goed = int(w.get("score_goed", 0) or 0)
        fout = int(w.get("score_fout", 0) or 0)
        if alleen_geoefend and not (goed or fout or streak):
            continue
        fase = gebruikers.fase_van(streak)
        regels.append(_lijstregel(
            f"<span class='grieks' style='font-size:17px;color:{TEKST}'>{grieks}</span>",
            f"streak {streak}", f"{ned[:44]} · les {w.get('les', '?')}",
            MERK if streak >= 16 else (TEKST if fase != "Nieuw" else ZACHT)))
    return regels


def lijst_verwarparen(g):
    try:
        paren = motor.verwar_paren_lijst(g.woorden, g.stats.get("verwar_stats") or {})
    except Exception:                                            # noqa: BLE001
        paren = []
    return [_lijstregel(
        f"<span class='grieks' style='font-size:16px;color:{TEKST}'>{p['a']}</span>"
        f" <span style='color:{ZACHT}'>↔</span> "
        f"<span class='grieks' style='font-size:16px;color:{TEKST}'>{p['b']}</span>",
        f"{p['n']}× verward",
        f"{str(p['a_ned'])[:22]} / {str(p['b_ned'])[:22]} · streak "
        f"{p['a_streak']}/{p['b_streak']}") for p in paren]


def lijst_structuur(g, zoek):
    regels = []
    for w in sw_woorden(g):
        grieks = str(w.get("grieks", ""))
        ned = str(w.get("nederlands", "") or w.get("betekenis", ""))
        if zoek and zoek not in grieks.lower() and zoek not in ned.lower():
            continue
        regels.append(_lijstregel(
            f"<span class='grieks' style='font-size:17px;color:{TEKST}'>{grieks}</span>",
            f"streak {w['streak']}", f"{ned[:44]} · {w.get('categorie', '')}",
            MERK if w["streak"] >= 16 else ZACHT))
    return regels


def _werkwoordpaspoort(verb):
    """Het morfologische paspoort: klasse, stamwortel en de mutatieregel die verklaart
    waarom de stamtijden eruitzien zoals ze eruitzien. Zelfde gegevens als het
    Werkwoordpaspoort in de Streamlit-app."""
    morf = verb.get("morfologie") or {}
    regel = morf.get("mutatieregel") or {}
    delen = []
    kop = " · ".join(x for x in (
        f"klasse {morf['klasse']}" if morf.get("klasse") else "",
        f"stamwortel {morf['stamwortel']}" if morf.get("stamwortel") else "",
        f"Strong {verb['strong_nummer']}" if verb.get("strong_nummer") else "") if x)
    if kop:
        delen.append(f"<div style='color:{MERK};font-size:11.5px'>{kop}</div>")
    if morf.get("memoriseren_vereist"):
        delen.append(f"<div style='color:{FOUT};font-size:11.5px'>🔥 onregelmatig — "
                     f"deze moet je uit je hoofd leren</div>")
    if regel.get("formule"):
        delen.append(f"<div style='color:{ZACHT};font-size:11.5px'>{regel['formule']}</div>")
    if regel.get("toelichting"):
        delen.append(f"<div style='color:{ZACHT};font-size:11.5px;font-style:italic'>"
                     f"{regel['toelichting']}</div>")
    return "".join(delen)


def lijst_stamtijden(g, zoek):
    stats = g.stats.get("stam_stats") or {}
    regels = []
    for verb in (motor.laad_stamtijden_db() or []):
        praesens = str(verb.get("praesens", ""))
        betekenis = str(verb.get("betekenis", ""))
        if zoek and zoek not in praesens.lower() and zoek not in betekenis.lower():
            continue
        vormen = []
        for tijd, vorm in (verb.get("stamtijden") or {}).items():
            if motor._stam_vorm_ok(vorm):
                s = int((stats.get(f"{praesens}_{vorm}") or {}).get("streak", 0) or 0)
                kleur = MERK if s >= 16 else (TEKST if s else ZACHT)
                vormen.append(f"<span class='grieks' style='color:{kleur}'>{vorm}</span>")
        regels.append(_lijstregel(
            f"<span class='grieks' style='font-size:17px;color:{TEKST}'>{praesens}</span>",
            f"les {verb.get('les', '?')}",
            f"{betekenis[:40]}<br>{' · '.join(vormen)}{_werkwoordpaspoort(verb)}"))
    return regels


@ui.page("/lijst")
def lijstpagina():
    """Opzoeken wat er in de lijsten staat en hoe je ervoor staat — zonder te oefenen."""
    g = _bewaakt()
    if not g:
        return
    with ui.column().classes("inhoud w-full gap-3"):
        ui.label("Lijst").style("font-size:26px;font-weight:700")
        kies = ui.select(LIJST_SOORTEN, value=LIJST_SOORTEN[0], label="Wat wil je zien").props(
            "outlined dark dense").classes("w-full")
        zoekveld = ui.input(placeholder="zoek op Grieks of Nederlands").props(
            "outlined dense dark clearable autocomplete=off").classes("w-full")
        alleen = ui.switch("Alleen wat ik al geoefend heb", value=False)
        for veld in (zoekveld, alleen):
            veld.bind_visibility_from(kies, "value", lambda v: v != "Mijn verwarwoorden")
        kop = ui.label().style(f"color:{ZACHT};font-size:12.5px")
        inhoud = ui.element("div").classes("kaart w-full")

        def teken():
            zoek = str(zoekveld.value or "").strip().lower()
            soort = kies.value
            if soort == "Mijn verwarwoorden":
                regels = lijst_verwarparen(g)
                leeg = ("Nog geen verwarparen. Die ontstaan als je in een ronde twee "
                        "woorden door elkaar haalt en dat in de eindsamenvatting bevestigt.")
            elif soort == "Structuurwoorden":
                regels, leeg = lijst_structuur(g, zoek), "Niets gevonden."
            elif soort == "Stamtijden":
                regels, leeg = lijst_stamtijden(g, zoek), "Niets gevonden."
            else:
                regels = lijst_woorden(g, zoek, bool(alleen.value))
                leeg = "Niets gevonden."
            kop.text = (f"{len(regels)} regels"
                        + (f", de eerste {LIJST_MAX} getoond" if len(regels) > LIJST_MAX else ""))
            inhoud.clear()
            with inhoud:
                ui.html("".join(regels[:LIJST_MAX]) if regels else
                        f"<div style='color:{ZACHT};font-size:13px;line-height:1.6'>{leeg}</div>")

        for veld in (kies, zoekveld, alleen):
            veld.on_value_change(lambda _=None: teken())
        teken()
        ui.label("Een vorm in de Bijbel opzoeken, of de grammatica doorzoeken? Dat doe "
                 "je in de volledige app.").style(
            f"color:{ZACHT};font-size:12.5px;line-height:1.5;margin-top:6px")
        streamlit_link(g)
    onderbalk("Lezen")


# ============================================================== lezen (nog te bouwen)
@ui.page("/lezen")
def lezenpagina():
    g = _bewaakt()
    if not g:
        return
    with ui.column().classes("inhoud w-full gap-3"):
        ui.label("Lezen").style("font-size:26px;font-weight:700")
        with ui.element("div").classes("kaart w-full").on(
                "click", lambda: ui.navigate.to("/lijst")):
            with ui.row().classes("w-full items-center justify-between no-wrap"):
                with ui.column().classes("gap-0"):
                    ui.label("Lijst").style(f"color:{TEKST};font-size:16px;font-weight:600")
                    ui.label("woordenlijst, verwarparen, structuurwoorden en stamtijden "
                             "opzoeken").style(f"color:{ZACHT};font-size:12.5px")
                ui.label("›").style(f"color:{ZACHT};font-size:22px")
        if BIJBEL:
            with ui.element("div").classes("kaart w-full").on(
                    "click", lambda: ui.navigate.to("/oefenen/ontleden")):
                with ui.row().classes("w-full items-center justify-between no-wrap"):
                    with ui.column().classes("gap-0"):
                        ui.label("Ontleden").style(
                            f"color:{TEKST};font-size:16px;font-weight:600")
                        ui.label("een vers uit het NT, woord voor woord").style(
                            f"color:{ZACHT};font-size:12.5px")
                    ui.label("›").style(f"color:{ZACHT};font-size:22px")
        with ui.element("div").classes("kaart w-full"):
            ui.label("In de volledige app").style(
                f"color:{TEKST};font-size:15px;font-weight:600")
            ui.label(("Leesteksten en Grammatica staan in de Streamlit-app."
                      if BIJBEL else
                      "Ontleden, Leesteksten, Grammatica en het opzoeken van vormen in de "
                      "Bijbel staan in de Streamlit-app. Deze versie draait zonder de "
                      "NT-tekst, en is daarmee klein genoeg om overal te draaien.")).style(
                f"color:{ZACHT};font-size:13px;line-height:1.5")
            streamlit_link(g)
    onderbalk("Lezen")


# Een hostingplatform (Render, Railway, Fly) geeft de poort mee via PORT; lokaal blijft
# het gewoon 8123. NiceGUI luistert buiten native-modus vanzelf op 0.0.0.0, dus dat hoeft
# hier niet apart. GRIEKS_ON_AIR=1 geeft een openbare URL via NiceGUI On Air — handig om
# de app even op je telefoon of op een ander netwerk te bekijken zonder te hosten.
_on_air = os.environ.get("GRIEKS_ON_AIR", "").strip()
ui.run(title="Grieks", dark=True, port=int(os.environ.get("PORT", 8123)),
       reload=False, show=False, favicon="\U0001F4D6",
       on_air=(_on_air if _on_air not in ("", "0", "1") else _on_air == "1"),
       storage_secret=os.environ.get("GRIEKS_SESSIE_SLEUTEL", "grieks-lokaal-ontwikkelen"))
