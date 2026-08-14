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


def nl_datum(d):
    """Nederlandse datum, zonder afhankelijk te zijn van de taalinstelling van de server."""
    return f"{_DAGEN[d.weekday()]} {d.day} {_MAANDEN[d.month - 1]}"


_sessies = {}


def _huidige():
    return _sessies.get(app.storage.user.get("sleutel"))


def onderbalk(actief):
    with ui.element("div").classes("onderbalk"):
        for naam, teken, pad in BESTEMMINGEN:
            merk = " actief" if naam == actief else ""
            ui.html(f"<a href='{pad}' class='vak{merk}'>"
                    f"<span style='font-size:17px'>{teken}</span>{naam}</a>")


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
        with ui.element("div").classes("kaart w-full").on("click", lambda: ui.navigate.to("/oefenen")):
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
class Sessie:
    """Eén ronde kaarten, met oplopende moeilijkheid per woord."""

    def __init__(self, g, aantal=12):
        poule = [w for w in g.woorden if (w.get("les") or 99) <= 4]
        gekozen = motor.kies_gefaseerde_oefensessie(poule, "vocab", max_nieuw=3) or poule
        self.kaarten = motor.leerpad_kaart_volgorde(list(gekozen)[:aantal])
        self.poule = poule
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
def oefenpagina():
    g = _bewaakt()
    if not g:
        return
    sessie = Sessie(g)

    with ui.column().classes("inhoud metbalk w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Woordenschat").style(f"color:{ZACHT};font-size:13px")
            teller = ui.label().style(f"color:{ZACHT};font-size:13px")
        streepjes = ui.row().classes("w-full gap-1 no-wrap")
        woord = ui.label().classes("grieks w-full text-center").style(
            f"font-size:58px;line-height:1.15;color:{TEKST};padding:18px 0 2px")
        lemma = ui.label().classes("w-full text-center").style(f"color:{ZACHT};font-size:14px")
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
            nl = k.get("nederlands", "")
            tekst = nl[:2] + "…" if len(nl) > 3 else nl
        else:
            seg = motor.ontleed_segmenten(k.get("grieks", ""), grieks_info=k.get("grieks_info", ""))
            tekst = " + ".join(str(s) for s in seg) if seg else "geen opbouw bekend"
        ui.notify(tekst, position="top", color="dark")

    async def verwerk(k, juist):
        sessie.beoordeeld = True
        sessie.goed += int(juist)
        sessie.fout += int(not juist)
        opgeslagen = await run.io_bound(g.noteer, k, juist)
        terugkoppeling.clear()
        with terugkoppeling:
            ui.label("Goed" if juist else "Niet goed").style(
                f"color:{GOED if juist else FOUT};font-weight:700;font-size:16px")
            ui.label(k.get("nederlands", "")).style(
                f"color:{TEKST};font-size:15px;text-align:center")
            ui.label(f"{sessie.goed} goed · {sessie.fout} fout · streak {k.get('streak', 0)}").style(
                f"color:{ZACHT};font-size:12px")
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
    def toon_kaart():
        for vak in (opties, terugkoppeling, hulp):
            vak.clear()
        sessie.beoordeeld = False
        k, vorm = sessie.huidig
        balk.set_visibility(True)
        invoer.set_visibility(True)

        if k is None:
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
                ui.label(k.get("nederlands", "")).style(
                    f"color:{TEKST};font-size:19px;text-align:center;padding:6px 0")
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
            ui.navigate.to("/oefenen")
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
