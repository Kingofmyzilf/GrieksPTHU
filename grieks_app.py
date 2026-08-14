# -*- coding: utf-8 -*-
"""Grieks — NiceGUI-schil op grieks_motor.py, grieks_opslag.py en grieks_gebruiker.py.

Vormgeving volgt de designreview: inloggen in de hoofdkolom, Grieks in een tekstfont,
vier vaste bestemmingen onderaan, een antwoordbalk die blijft staan, en oefenbeurten
zonder paginaherlaad.

Starten:  py grieks_app.py
"""
import os
import random
from datetime import date, timedelta

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
        ui.label("Gebruik je dezelfde twee woorden als in je huidige app, dan staat je "
                 "voortgang er meteen.").style(f"color:{ZACHT};font-size:12.5px;line-height:1.5")

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
@ui.page("/vandaag")
def vandaagpagina():
    g = _bewaakt()
    if not g:
        return
    sam = g.samenvatting()
    dagen = g.stats.get("dag_stats") or {}
    doel = 25

    with ui.column().classes("inhoud w-full gap-3"):
        ui.label("Vandaag").style("font-size:26px;font-weight:700")
        ui.label(nl_datum(date.today())).style(f"color:{ZACHT};font-size:13px")

        with ui.element("div").classes("kaart w-full"):
            with ui.row().classes("w-full items-baseline gap-2"):
                ui.label(str(sam["vandaag"])).style(
                    f"font-size:44px;font-weight:800;color:{MERK};line-height:1")
                ui.label(f"van {doel}").style(f"color:{ZACHT};font-size:15px")
            balk = min(1.0, sam["vandaag"] / doel)
            ui.element("div").style(
                f"width:100%;height:6px;border-radius:3px;background:{RAND};margin:10px 0 8px")\
                .classes("relative")
            ui.html(f"<div style='margin-top:-14px;width:{balk*100:.0f}%;height:6px;"
                    f"border-radius:3px;background:{MERK}'></div>")
            resterend = max(0, doel - sam["vandaag"])
            ui.label("Je dagdoel is gehaald." if resterend == 0
                     else f"Nog {resterend} woorden voor je dagdoel.").style(
                f"color:{TEKST};font-size:14px")
            ui.label(f"{sam['dagen']} oefendagen · {sam['beheerst']} woorden beheerst").style(
                f"color:{ZACHT};font-size:12.5px")

        ui.label("Klaargezet").style("font-size:15px;font-weight:700;margin-top:6px")
        with ui.element("div").classes("kaart w-full").on("click", lambda: ui.navigate.to("/oefenen/woorden")):
            with ui.row().classes("w-full items-center justify-between no-wrap"):
                with ui.column().classes("gap-0"):
                    ui.label("Woordenschat").style(f"color:{TEKST};font-size:16px;font-weight:600")
                    ui.label("12 kaarten · jouw achterstallige woorden eerst").style(
                        f"color:{ZACHT};font-size:12.5px")
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
VORMEN = [AUTO, "Alleen leren", "Alleen meerkeuze", "Mix", "Alleen typen"]
_VORM_CODE = {"Alleen leren": "1", "Alleen meerkeuze": "2", "Alleen typen": "4"}

OEFENINGEN = ["Leerpad (levels)", "Losse lessen", "Knelpunten", "Lang niet gedaan",
              "Mastery", "Gelijkende woorden", "Mijn verwarwoorden"]

STANDAARD = {"keuze": "Leerpad (levels)", "lessen": [], "vorm": AUTO, "aantal": 12,
             "nieuw_mee": True, "audio": True, "opbouw": False}


def prefs(g):
    """Instellingen uit ui_prefs — hetzelfde blok dat de Streamlit-app gebruikt,
    dus wat je hier kiest komt daar ook terug."""
    p = g.stats.setdefault("ui_prefs", {})
    return {k: p.get(f"ng_{k}", v) for k, v in STANDAARD.items()}


def zet_pref(g, sleutel, waarde):
    g.stats.setdefault("ui_prefs", {})[f"ng_{sleutel}"] = waarde


def bouw_poule(g, keuze, lessen):
    """De verzameling woorden waaruit een sessie wordt getrokken."""
    alles = g.woorden
    if keuze == "Losse lessen" and lessen:
        return [w for w in alles if w.get("les") in lessen]
    if keuze == "Mastery":
        return [w for w in alles if int(w.get("streak", 0)) >= 30]
    if keuze == "Knelpunten":
        fout = [w for w in alles if int(w.get("score_fout", 0)) > 0]
        return sorted(fout, key=lambda w: -int(w.get("score_fout", 0)))[:60]
    if keuze == "Lang niet gedaan":
        gedaan = [w for w in alles if w.get("laatst_geoefend")]
        return sorted(gedaan, key=lambda w: w.get("laatst_geoefend", ""))[:60]
    if keuze == "Gelijkende woorden":
        try:
            paren = motor.bouw_lookalike_paren(alles, motor.laad_verwarparen_db())
        except Exception:                                        # noqa: BLE001
            paren = []
        uit = [w for paar in paren for w in paar]
        return uit or alles
    if keuze == "Mijn verwarwoorden":
        eigen = set()
        for sleutel in (g.stats.get("verwar_stats") or {}):
            eigen.update(str(sleutel).split("||"))
        uit = [w for w in alles if w.get("grieks") in eigen]
        return uit or alles
    # Leerpad: het eerstvolgende niet-afgeronde level
    try:
        levels = motor.bouw_leerpad_levels(alles)
        status = motor.leerpad_status(levels)
        for lvl, st in zip(levels, status):
            klaar = st.get("klaar") if isinstance(st, dict) else None
            if not klaar:
                woorden = lvl.get("woorden") if isinstance(lvl, dict) else lvl
                if woorden:
                    return list(woorden)
    except Exception:                                            # noqa: BLE001
        pass
    return [w for w in alles if (w.get("les") or 99) <= 4] or alles


def _hint(w):
    """Een bruikbare hint: eerste letter van elk woord plus streepjes voor de rest,
    zodat je de vorm ziet zonder het antwoord te krijgen."""
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


def _feedbackblok(w, juist, sessie, woordenlijst):
    """Hetzelfde als de groene/rode balk in de Streamlit-app: het woord, de
    woordenboekvorm mét uitgangen, de uitspraak en de volledige betekenis."""
    kleur = GOED if juist else FOUT
    achter = "rgba(61,220,151,.10)" if juist else "rgba(255,107,129,.10)"
    grieks = w.get("grieks", "")
    # lexeem_info is de citatievorm met genitief-uitgang en lidwoord: 'λόγος, -ου, ὁ'
    uitgangen = w.get("lexeem_info") or w.get("grieks_info") or ""
    fonetisch = w.get("fonetisch", "")
    regels = [
        f"<div style='color:{kleur};font-weight:700;font-size:16px;margin-bottom:6px'>"
        f"{'✓ Goed!' if juist else '✗ Niet goed'}</div>",
        f"<div class='grieks' style='font-size:26px;color:{TEKST};line-height:1.2'>{grieks}</div>",
    ]
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


class Sessie:
    """Eén ronde kaarten, met oplopende moeilijkheid per woord."""

    def __init__(self, g):
        p = prefs(g)
        self.poule = bouw_poule(g, p["keuze"], p["lessen"]) or g.woorden
        gekozen = motor.kies_gefaseerde_oefensessie(
            self.poule, "vocab", max_nieuw=3 if p["nieuw_mee"] else 0,
            verbied_nieuwe_woorden=not p["nieuw_mee"]) or self.poule
        gekozen = list(gekozen)[:int(p["aantal"])]
        vast = _VORM_CODE.get(p["vorm"])
        if vast:
            self.kaarten = [(w, vast) for w in gekozen]
        elif p["vorm"] == "Mix":
            self.kaarten = [(w, random.choice(("2", "4"))) for w in gekozen]
        else:
            self.kaarten = motor.leerpad_kaart_volgorde(gekozen)
        self.prefs = p
        self.i = 0
        self.goed = 0
        self.fout = 0
        self.beoordeeld = False

    @property
    def huidig(self):
        return self.kaarten[self.i] if self.i < len(self.kaarten) else (None, None)


def _afleiders(woord, poule, hoeveel=3):
    """Meerkeuze-opties: plausibel maar niet synoniem met het goede antwoord."""
    juist = woord.get("nederlands", "")
    zelfde_soort = [w for w in poule
                    if w is not woord and w.get("woordsoort") == woord.get("woordsoort")
                    and not motor.zelfde_betekenis(w.get("nederlands", ""), juist)]
    rest = [w for w in poule
            if w is not woord and not motor.zelfde_betekenis(w.get("nederlands", ""), juist)]
    bron = zelfde_soort if len(zelfde_soort) >= hoeveel else rest
    return [w.get("nederlands", "") for w in random.sample(bron, min(hoeveel, len(bron)))]


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
                                                        stam_stats) if s.get("klaar"))
    groepen = [
        ("Woorden kennen", [
            ("Woordenschat", f"{round(100 * sam['geoefend'] / max(1, len(g.woorden)))}%",
             "/oefenen/woorden"),
        ]),
        ("Vormen beheersen", [
            ("Stamtijden", f"{round(100 * stam_klaar / max(1, len(stam_db)))}%",
             "/oefenen/stamtijden"),
        ]),
    ]
    nog_niet = ["Actief beheersen", "Structuurwoorden", "Ontleden", "Klankwetten",
                "Nederlands → Grieks", "Verwarwoorden"]

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
        ui.label("Nog niet overgezet").style(f"color:{ZACHT};font-size:13px;margin-top:10px")
        with ui.element("div").classes("kaart w-full"):
            ui.label(" · ".join(nog_niet)).style(
                f"color:{ZACHT};font-size:13px;line-height:1.6")
            ui.label("Deze staan nog in de Streamlit-app.").style(
                f"color:{ZACHT};font-size:12px;margin-top:4px")
    onderbalk("Oefenen")


@ui.page("/oefenen/woorden")
def oefenpagina():
    g = _bewaakt()
    if not g:
        return
    sessie = Sessie(g)

    # --- instellingen achter het tandwiel (designreview: niet vóór de oefening) ---
    with ui.dialog() as instellingen, ui.card().style(
            f"background:{VLAK};color:{TEKST};min-width:300px;max-width:92vw"):
        ui.label("Instellingen").style("font-size:18px;font-weight:700")
        p = prefs(g)
        alle_lessen = sorted({int(w["les"]) for w in g.woorden if w.get("les")})

        kies_oefening = ui.select(OEFENINGEN, value=p["keuze"], label="Oefening").props(
            "outlined dark").classes("w-full")
        kies_lessen = ui.select(alle_lessen, value=p["lessen"], label="Lessen",
                                multiple=True).props("outlined dark").classes("w-full")
        kies_lessen.bind_visibility_from(kies_oefening, "value",
                                         lambda v: v == "Losse lessen")
        kies_vorm = ui.select(VORMEN, value=p["vorm"], label="Oefenvorm").props(
            "outlined dark").classes("w-full")
        kies_aantal = ui.number("Kaarten per ronde", value=int(p["aantal"]),
                                min=4, max=40, step=1).props("outlined dark").classes("w-full")
        kies_nieuw = ui.switch("Nieuwe woorden mee-oefenen", value=bool(p["nieuw_mee"]))
        kies_audio = ui.switch("Uitspraakknop tonen", value=bool(p["audio"]))
        kies_opbouw = ui.switch("Woordopbouw tonen", value=bool(p["opbouw"]))
        ui.label("Je keuzes worden bewaard bij je voortgang.").style(
            f"color:{ZACHT};font-size:12px")

        async def bewaar_instellingen():
            for sleutel, veld in [("keuze", kies_oefening), ("lessen", kies_lessen),
                                  ("vorm", kies_vorm), ("aantal", kies_aantal),
                                  ("nieuw_mee", kies_nieuw), ("audio", kies_audio),
                                  ("opbouw", kies_opbouw)]:
                zet_pref(g, sleutel, veld.value)
            instellingen.close()
            await run.io_bound(g.bewaar, True)
            ui.navigate.to("/oefenen/woorden")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Annuleren", on_click=instellingen.close).props("flat").style(
                f"color:{ZACHT}")
            ui.button("Toepassen", on_click=bewaar_instellingen).props("unelevated").style(
                f"background:{MERK};color:{INKT};font-weight:700")

    with ui.column().classes("inhoud metbalk w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label(sessie.prefs["keuze"]).style(f"color:{ZACHT};font-size:13px")
            with ui.row().classes("items-center gap-2 no-wrap"):
                teller = ui.label().style(f"color:{ZACHT};font-size:13px")
                ui.button("⚙", on_click=instellingen.open).props("flat dense").style(
                    f"color:{ZACHT};font-size:17px;min-width:32px")
        streepjes = ui.row().classes("w-full gap-1 no-wrap")
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
    onderbalk("Oefenen")

    # ---------------- hulpjes ----------------
    def teken_streepjes():
        streepjes.clear()
        with streepjes:
            for n in range(len(sessie.kaarten)):
                kleur = MERK if n < sessie.i else (TEKST if n == sessie.i else RAND)
                ui.element("div").style(f"flex:1;height:4px;border-radius:2px;background:{kleur}")

    def toon_hulp(soort, k):
        if soort == "Uitspraak":
            tekst = motor.fonetisch_uit_translit(k.get("fonetisch", "")) or k.get("fonetisch", "")
        elif soort == "Hint":
            tekst = _hint(k)
        else:
            tekst = _opbouw_tekst(k, g.woorden)
        ui.notify(tekst, position="top", color="dark", multi_line=True,
                  classes="text-body2").style("max-width:88vw")

    async def verwerk(k, juist):
        sessie.beoordeeld = True
        sessie.goed += int(juist)
        sessie.fout += int(not juist)
        opgeslagen = await run.io_bound(g.noteer, k, juist)
        terugkoppeling.clear()
        with terugkoppeling:
            ui.html(_feedbackblok(k, juist, sessie, g.woorden))
        if g.laatste_fout:
            opslagmelding.text = "⚠ Opslaan lukte niet — je voortgang staat nog in het geheugen."
            opslagmelding.style(f"color:{FOUT}")
        elif opgeslagen:
            opslagmelding.text = "Voortgang opgeslagen"
            opslagmelding.style(f"color:{ZACHT}")
        knop.text = "Volgende"
        balk.set_visibility(True)
        invoer.set_visibility(False)

    def volgende():
        sessie.i += 1
        toon_kaart()

    # ---------------- de drie vraagvormen ----------------
    def teken_status(k):
        """Zelfde gegevens als de caption in de Streamlit-app: fase, streak,
        goed/fout, laatst geoefend en hoeveel er nog te gaan zijn."""
        statusbalk.clear()
        if k is None:
            return
        fase = gebruikers.fase_van(k.get("streak", 0))
        resterend = len(sessie.kaarten) - sessie.i - 1
        vakjes = [
            (fase.replace("In training", "Training"), "fase",
             MERK if fase != "Nieuw" else ZACHT),
            (int(k.get("streak", 0) or 0), "streak", TEKST),
            (f"{int(k.get('score_goed', 0) or 0)}/{int(k.get('score_fout', 0) or 0)}",
             "goed/fout", TEKST),
            (_kort_datum(k.get("laatst_geoefend")), "laatst", ZACHT),
            (resterend, "te gaan", ZACHT),
        ]
        with statusbalk:
            ui.html(_statusrij(vakjes))

    def toon_kaart():
        for vak in (opties, terugkoppeling, hulp):
            vak.clear()
        sessie.beoordeeld = False
        k, vorm = sessie.huidig
        balk.set_visibility(True)
        invoer.set_visibility(True)

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
            return

        woord.text = k.get("grieks", "")
        lemma.text = k.get("grieks_info") or k.get("woordsoort", "")
        teller.text = f"{sessie.i + 1}/{len(sessie.kaarten)}"
        teken_streepjes()
        with hulp:
            for label in ("Uitspraak", "Hint", "Opbouw"):
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

        if vorm == "2":                                    # meerkeuze
            vraagsoort.text = "Welke betekenis hoort hierbij?"
            invoer.set_visibility(False)
            knop.text = "Ik weet het niet"
            keuzes = _afleiders(k, sessie.poule) + [k.get("nederlands", "")]
            random.shuffle(keuzes)
            with opties:
                for keuze in keuzes:
                    ui.html(f"<button class='keuze'>{keuze}</button>").on(
                        "click", lambda _=None, c=keuze: kies(k, c))
            return

        vraagsoort.text = "Typ de betekenis"               # typen
        invoer.value = ""
        knop.text = "Nakijken"
        invoer.run_method("focus")

    async def kies(k, keuze):
        if sessie.beoordeeld:
            return
        juist = keuze == k.get("nederlands", "") or motor.zelfde_betekenis(
            keuze, k.get("nederlands", ""))
        opties.clear()
        await verwerk(k, juist)

    async def hoofdknop():
        k, vorm = sessie.huidig
        if k is None:
            await run.io_bound(g.bewaar, True)
            ui.navigate.to("/oefenen/woorden")
            return
        if sessie.beoordeeld:
            volgende()
            return
        if vorm == "1":                                    # flashcard telt niet als beurt
            volgende()
            return
        if vorm == "2":                                    # 'ik weet het niet'
            opties.clear()
            await verwerk(k, False)
            return
        await verwerk(k, bool(motor.check_betekenis(invoer.value or "",
                                                    k.get("nederlands", ""))))

    knop.on_click(hoofdknop)
    invoer.on("keydown.enter", hoofdknop)
    toon_kaart()


# ============================================================== stamtijden
TIJD_KORT = {"Futurum Actief/Medium": "futurum", "Aoristus Actief/Medium": "aoristus",
             "Aoristus Passief": "aoristus passief", "Perfectum Actief": "perfectum",
             "Perfectum Medium/Passief": "perfectum med./pass."}


class StamSessie:
    """Productierichting: je krijgt het praesens plus een tijd, en typt de vorm.
    Dat is de kant die bij een tentamen wordt gevraagd."""

    def __init__(self, g, aantal=10):
        db = motor.laad_stamtijden_db()
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
        # zwakste eerst, daarna op frequentie — zo oefen je wat nog niet zit
        vragen.sort(key=lambda v: (v["streak"], -int(v["verb"].get("frequentie", 0) or 0)))
        self.vragen = vragen[:aantal]
        self.i = 0
        self.goed = 0
        self.fout = 0
        self.beoordeeld = False

    @property
    def huidig(self):
        return self.vragen[self.i] if self.i < len(self.vragen) else None


@ui.page("/oefenen/stamtijden")
def stampagina():
    g = _bewaakt()
    if not g:
        return
    sessie = StamSessie(g)
    stats = g.stats.setdefault("stam_stats", {})

    with ui.column().classes("inhoud metbalk w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Stamtijden").style(f"color:{ZACHT};font-size:13px")
            teller = ui.label().style(f"color:{ZACHT};font-size:13px")
        streepjes = ui.row().classes("w-full gap-1 no-wrap")
        praesens = ui.label().classes("grieks w-full text-center").style(
            f"font-size:46px;line-height:1.15;color:{TEKST};padding:16px 0 0")
        betekenis = ui.label().classes("w-full text-center").style(
            f"color:{ZACHT};font-size:14px")
        gevraagd = ui.label().classes("w-full text-center").style(
            f"color:{MERK};font-size:17px;font-weight:600;padding-top:10px")
        statusbalk = ui.row().classes("w-full").style("padding-top:8px")
        terugkoppeling = ui.column().classes("w-full items-center").style(
            "min-height:64px;padding-top:8px")
        opslagmelding = ui.label().style(f"color:{ZACHT};font-size:11.5px;min-height:16px")

    with ui.element("div").classes("antwoordbalk"):
        with ui.row().classes("w-full gap-2 no-wrap items-center"):
            invoer = ui.input(placeholder="typ de vorm (Latijnse toetsen mag)").props(
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
        terugkoppeling.clear()
        statusbalk.clear()
        sessie.beoordeeld = False
        v = sessie.huidig
        invoer.set_visibility(True)
        if v is None:
            praesens.text = "✓"
            betekenis.text = f"Klaar — {sessie.goed} goed, {sessie.fout} fout."
            gevraagd.text = ""
            teller.text = ""
            invoer.set_visibility(False)
            knop.text = "Nieuwe ronde"
            teken()
            return
        praesens.text = v["praesens"]
        betekenis.text = v["verb"].get("betekenis", "")
        gevraagd.text = TIJD_KORT.get(v["tijd"], v["tijd"])
        teller.text = f"{sessie.i + 1}/{len(sessie.vragen)}"
        knop.text = "Nakijken"
        invoer.value = ""
        teken()
        with statusbalk:
            ui.html(_statusrij([
                (v["streak"], "streak", TEKST),
                (f"{v['goed']}/{v['fout']}", "goed/fout", TEKST),
                (v["verb"].get("morfologie", {}).get("klasse", "—"), "klasse", ZACHT),
                (len(sessie.vragen) - sessie.i - 1, "te gaan", ZACHT),
            ]))
        invoer.run_method("focus")

    async def nakijken():
        v = sessie.huidig
        if v is None:
            await run.io_bound(g.bewaar, True)
            ui.navigate.to("/oefenen/stamtijden")
            return
        if sessie.beoordeeld:
            sessie.i += 1
            toon()
            return
        juist = bool(motor.grieks_vorm_ok(invoer.value or "", v["vorm"]))
        sessie.beoordeeld = True
        sessie.goed += int(juist)
        sessie.fout += int(not juist)
        e = stats.setdefault(v["sleutel"], {"g": 0, "f": 0, "streak": 0})
        e["g"] = int(e.get("g", 0)) + int(juist)
        e["f"] = int(e.get("f", 0)) + int(not juist)
        e["streak"] = int(e.get("streak", 0)) + 1 if juist else 0
        g.sinds_opslag += 1
        opgeslagen = await run.io_bound(g.bewaar) if g.sinds_opslag >= 5 else False
        opbouw = ""
        try:
            regels = motor.deconstrueer_stamtijd_live(v["vorm"], v["tijd"], v["praesens"])
            if regels:
                opbouw = ("<div style='color:" + ZACHT + ";font-size:13px;margin-top:8px'>"
                          + "<br>".join(str(r) for r in (regels if isinstance(regels, list)
                                                         else [regels])) + "</div>")
        except Exception:                                        # noqa: BLE001
            pass
        kleur = GOED if juist else FOUT
        achter = "rgba(61,220,151,.10)" if juist else "rgba(255,107,129,.10)"
        terugkoppeling.clear()
        with terugkoppeling:
            ui.html(
                f"<div style='background:{achter};border:1px solid {kleur}40;border-radius:12px;"
                f"padding:14px;text-align:center;width:100%'>"
                f"<div style='color:{kleur};font-weight:700;font-size:16px'>"
                f"{'✓ Goed!' if juist else '✗ Niet goed'}</div>"
                f"<div class='grieks' style='font-size:30px;color:{TEKST};margin-top:6px'>"
                f"{v['vorm']}</div>"
                f"<div style='color:{ZACHT};font-size:13.5px'>"
                f"{TIJD_KORT.get(v['tijd'], v['tijd'])} van {v['praesens']}</div>"
                f"{opbouw}"
                f"<div style='color:{ZACHT};font-size:12px;margin-top:8px'>"
                f"{sessie.goed} goed · {sessie.fout} fout in deze ronde · "
                f"streak nu {e['streak']}</div></div>")
        if opgeslagen:
            opslagmelding.text = "Voortgang opgeslagen"
        knop.text = "Volgende"

    knop.on_click(nakijken)
    invoer.on("keydown.enter", nakijken)
    toon()


# ============================================================== voortgang
@ui.page("/voortgang")
def voortgangpagina():
    g = _bewaakt()
    if not g:
        return
    sam = g.samenvatting()
    xp = motor.bereken_xp(g.woorden)
    niv = motor.niveau_van_xp(xp)

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

        with ui.row().classes("w-full gap-2 no-wrap"):
            for waarde, label in [(f"{sam['accuratesse']}%", "accuratesse"),
                                  (sam["beheerst"], "beheerst"),
                                  (sam["dagen"], "oefendagen")]:
                with ui.element("div").classes("kaart").style("flex:1;text-align:center"):
                    ui.label(str(waarde)).style(
                        f"font-size:26px;font-weight:800;color:{MERK};line-height:1.1")
                    ui.label(label).style(f"color:{ZACHT};font-size:11.5px")

        with ui.element("div").classes("kaart w-full"):
            ui.label("Woorden").style(f"color:{TEKST};font-size:15px;font-weight:600")
            ui.label(f"{sam['geoefend']} van de {len(g.woorden)} geoefend · "
                     f"{sam['goed']} goed, {sam['fout']} fout").style(
                f"color:{ZACHT};font-size:13px")
            deel = sam["geoefend"] / max(1, len(g.woorden))
            ui.html(f"<div style='width:100%;height:6px;border-radius:3px;background:{RAND};"
                    f"margin-top:8px'><div style='width:{deel*100:.0f}%;height:6px;"
                    f"border-radius:3px;background:{MERK}'></div></div>")

        ui.button("Uitloggen", on_click=lambda: (
            _sessies.pop(app.storage.user.get("sleutel"), None),
            app.storage.user.clear(), ui.navigate.to("/"))).props("flat").style(
            f"color:{ZACHT};border:1px solid {RAND};border-radius:10px;margin-top:8px")
    onderbalk("Voortgang")


# ============================================================== lezen (nog te bouwen)
@ui.page("/lezen")
def lezenpagina():
    g = _bewaakt()
    if not g:
        return
    with ui.column().classes("inhoud w-full gap-3"):
        ui.label("Lezen").style("font-size:26px;font-weight:700")
        with ui.element("div").classes("kaart w-full"):
            ui.label("Nog niet overgezet").style(f"color:{TEKST};font-size:15px;font-weight:600")
            ui.label("Leesteksten, Ontleden en Grammatica staan nog in de Streamlit-app. "
                     "Die blijft gewoon werken zolang dit onderdeel hier ontbreekt.").style(
                f"color:{ZACHT};font-size:13px;line-height:1.5")
    onderbalk("Lezen")


ui.run(title="Grieks", dark=True, port=8123, reload=False, show=False, favicon="\U0001F4D6",
       storage_secret=os.environ.get("GRIEKS_SESSIE_SLEUTEL", "grieks-lokaal-ontwikkelen"))
