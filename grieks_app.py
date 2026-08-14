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
                                                        stam_stats) if s.get("klaar"))
    groepen = [
        ("Woorden kennen", [
            ("Woordenschat", f"{round(100 * sam['geoefend'] / max(1, len(g.woorden)))}%",
             "/oefenen/woorden"),
        ]),
        ("Vormen beheersen", [
            ("Stamtijden", f"{round(100 * stam_klaar / max(1, len(stam_db)))}%",
             "/oefenen/stamtijden"),
            ("Actief beheersen", f"{_af_pct(g)}%", "/oefenen/actief"),
        ]),
    ]
    nog_niet = ["Structuurwoorden", "Ontleden", "Klankwetten",
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
TIJDEN = list(TIJD_KORT)

STAM_OEFENINGEN = ["Zwakste eerst", "Leerpad (per werkwoord)", "Meest voorkomend",
                   "Alleen wat ik fout deed"]
STAM_VRAAGVORM = ["Automatisch (aanbevolen)", "Alleen de tijd", "Tijd en werkwoord"]
STAM_STANDAARD = {"stam_keuze": "Zwakste eerst", "stam_aantal": 10,
                  "stam_vraagvorm": STAM_VRAAGVORM[0], "stam_kleur": True}
STAM_TYP_STREAK = 10       # vanaf hier ook het werkwoord laten typen


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
        p = {k: (g.stats.get("ui_prefs") or {}).get(f"ng_{k}", v)
             for k, v in STAM_STANDAARD.items()}
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
    sessie = StamSessie(g)
    stats = g.stats.setdefault("stam_stats", {})

    with ui.dialog() as instellingen, ui.card().style(
            f"background:{VLAK};color:{TEKST};min-width:300px;max-width:92vw"):
        ui.label("Instellingen").style("font-size:18px;font-weight:700")
        kies_oef = ui.select(STAM_OEFENINGEN, value=sessie.prefs["stam_keuze"],
                             label="Oefening").props("outlined dark").classes("w-full")
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
                                  ("stam_kleur", kies_kleur)]:
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
        g.sinds_opslag += 1
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


# ============================================================== actief beheersen
AF_OEFENINGEN = ["Zwakste eerst", "Leerpad (volgend rijtje)", "Alleen wat ik fout deed"]
AF_VRAAGVORM = ["Automatisch (aanbevolen)", "Alleen meerkeuze", "Alleen typen"]
AF_STANDAARD = {"af_keuze": "Zwakste eerst", "af_aantal": 10,
                "af_vraagvorm": AF_VRAAGVORM[0], "af_niveau": "Alles"}
AF_TYP_STREAK = 10        # vanaf hier zelf typen in plaats van aanwijzen


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


@ui.page("/oefenen/actief")
def afpagina():
    g = _bewaakt()
    if not g:
        return
    sessie = AfSessie(g)
    stats = g.stats.setdefault("actief_stats", {})
    niveaus = ["Alles"] + sorted((motor.laad_actief_beheersen_db() or {}).keys())

    with ui.dialog() as instellingen, ui.card().style(
            f"background:{VLAK};color:{TEKST};min-width:300px;max-width:92vw"):
        ui.label("Instellingen").style("font-size:18px;font-weight:700")
        k_oef = ui.select(AF_OEFENINGEN, value=sessie.prefs["af_keuze"],
                          label="Oefening").props("outlined dark").classes("w-full")
        k_niv = ui.select(niveaus, value=sessie.prefs["af_niveau"],
                          label="Niveau").props("outlined dark").classes("w-full")
        k_vorm = ui.select(AF_VRAAGVORM, value=sessie.prefs["af_vraagvorm"],
                           label="Wat wordt gevraagd").props("outlined dark").classes("w-full")
        k_aantal = ui.number("Cellen per ronde", value=int(sessie.prefs["af_aantal"]),
                             min=4, max=40, step=1).props("outlined dark").classes("w-full")
        ui.label(f"Automatisch: eerst aanwijzen uit het eigen rijtje, en vanaf streak "
                 f"{AF_TYP_STREAK} zelf typen.").style(f"color:{ZACHT};font-size:12px")

        async def bewaar_inst():
            for sleutel, veld in [("af_keuze", k_oef), ("af_niveau", k_niv),
                                  ("af_vraagvorm", k_vorm), ("af_aantal", k_aantal)]:
                g.stats.setdefault("ui_prefs", {})[f"ng_{sleutel}"] = veld.value
            instellingen.close()
            await run.io_bound(g.bewaar, True)
            ui.navigate.to("/oefenen/actief")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Annuleren", on_click=instellingen.close).props("flat").style(
                f"color:{ZACHT}")
            ui.button("Toepassen", on_click=bewaar_inst).props("unelevated").style(
                f"background:{MERK};color:{INKT};font-weight:700")

    with ui.column().classes("inhoud metbalk w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Actief beheersen").style(f"color:{ZACHT};font-size:13px")
            with ui.row().classes("items-center gap-2 no-wrap"):
                teller = ui.label().style(f"color:{ZACHT};font-size:13px")
                ui.button("⚙", on_click=instellingen.open).props("flat dense").style(
                    f"color:{ZACHT};font-size:17px;min-width:32px")
        streepjes = ui.row().classes("w-full gap-1 no-wrap")
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
            gevraagd.text = "✓"
            vraagsoort.text = f"Klaar — {sessie.goed} goed, {sessie.fout} fout."
            teller.text = ""
            invoer.set_visibility(False)
            knop.text = "Nieuwe ronde"
            teken()
            return
        sessie.vraag_typen = af_vraagt_typen(sessie.prefs["af_vraagvorm"], c["streak"])
        rijtje.text = f"{c['categorie']} · {c['paradigma']}"
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
        g.sinds_opslag += 1
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
