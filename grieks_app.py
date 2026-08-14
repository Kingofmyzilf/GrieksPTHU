# -*- coding: utf-8 -*-
"""Grieks — NiceGUI-schil op grieks_motor.py en grieks_opslag.py.

Vormgeving volgt de designreview: inloggen in de hoofdkolom, Grieks in een
tekstfont, vier vaste bestemmingen onderaan, een antwoordbalk die blijft staan,
en een oefenbeurt zonder paginaherlaad.

Starten:  py grieks_app.py
"""
import os
import random

from nicegui import app, run, ui

import grieks_gebruiker as gebruikers
import grieks_motor as motor
import grieks_opslag as opslag

# --- huisstijl (uit .streamlit/config.toml) ---
INKT, VLAK, RAND = "#0e1117", "#1e1e1e", "#2b3038"
TEKST, ZACHT = "#fafafa", "#9aa4ae"
MERK, GOED, FOUT = "#33ccff", "#3ddc97", "#ff6b81"
GRIEKS_FONT = "'Gentium Book Plus','Palatino Linotype',Georgia,serif"

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
                     cursor:pointer; user-select:none; }}
  .onderbalk .vak.actief {{ color:{MERK}; }}
  .inhoud {{ padding:14px 14px 190px; max-width:640px; margin:0 auto; }}
  .smal {{ max-width:420px; margin:0 auto; padding:14px; }}
</style>
""", shared=True)

# Ingelogde gebruikers in het geheugen van de server, op sleutel uit de cookie.
_sessies = {}


def _huidige():
    return _sessies.get(app.storage.user.get("sleutel"))


# ============================================================== inloggen
@ui.page("/")
def inlogpagina():
    if _huidige():
        ui.navigate.to("/oefenen")
        return
    ui.query("body").style(f"background:{INKT}")
    with ui.column().classes("smal w-full gap-2 items-stretch"):
        ui.html(
            f"<div style='text-align:center;padding:34px 0 2px'>"
            f"<div class='grieks' style='font-size:64px;line-height:1.1;color:{TEKST}'>λόγος</div>"
            f"<div style='font-size:22px;font-weight:600;margin-top:10px'>Grieks</div>"
            f"<div style='font-size:14px;color:{ZACHT};margin-top:2px'>"
            f"Nieuwtestamentisch Grieks · PThU</div></div>")
        ui.element("div").style("height:14px")
        veld_naam = ui.input("Naam").props("outlined dark autocomplete=username").classes("w-full")
        veld_code = ui.input("Code", password=True).props(
            "outlined dark autocomplete=current-password").classes("w-full")
        melding = ui.label().style(f"color:{FOUT};font-size:13px;min-height:18px")
        knop = ui.button("Inloggen").props("unelevated").classes("w-full").style(
            f"background:{MERK};color:{INKT};font-weight:700;height:46px")
        ui.label("Gebruik dezelfde naam en code als in je huidige app — je voortgang "
                 "staat op dezelfde plek.").style(f"color:{ZACHT};font-size:12.5px;line-height:1.5")

    async def probeer():
        melding.text = ""
        knop.props("loading")
        try:
            g = await run.io_bound(gebruikers.inloggen, veld_naam.value, veld_code.value)
        except opslag.OpslagFout as e:
            melding.text = str(e)
            knop.props(remove="loading")
            return
        except Exception as e:                                   # noqa: BLE001
            melding.text = f"Inloggen lukte niet: {e}"
            knop.props(remove="loading")
            return
        _sessies[g.sleutel] = g
        app.storage.user["sleutel"] = g.sleutel
        ui.navigate.to("/oefenen")

    knop.on_click(probeer)
    veld_code.on("keydown.enter", probeer)


# ============================================================== oefenen
class Sessie:
    def __init__(self, g, aantal=12):
        poule = [w for w in g.woorden if (w.get("les") or 99) <= 4]
        gefaseerd = motor.kies_gefaseerde_oefensessie(poule, "vocab", max_nieuw=3) or poule
        self.kaarten = list(gefaseerd)[:aantal] or random.sample(poule, min(aantal, len(poule)))
        self.i = 0
        self.goed = 0
        self.fout = 0
        self.beoordeeld = False

    @property
    def kaart(self):
        return self.kaarten[self.i] if self.i < len(self.kaarten) else None


@ui.page("/oefenen")
def oefenpagina():
    g = _huidige()
    if not g:
        ui.navigate.to("/")
        return
    ui.query("body").style(f"background:{INKT}")
    sessie = Sessie(g)
    sam = g.samenvatting()

    with ui.column().classes("inhoud w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(f"Woordenschat · {g.naam}").style(f"color:{ZACHT};font-size:13px")
            teller = ui.label().style(f"color:{ZACHT};font-size:13px")
        streepjes = ui.row().classes("w-full gap-1 no-wrap")
        ui.label(f"{sam['beheerst']} woorden beheerst · {sam['accuratesse']}% goed · "
                 f"vandaag {sam['vandaag']} geoefend").style(f"color:{ZACHT};font-size:12px")

        woord = ui.label().classes("grieks w-full text-center").style(
            f"font-size:58px;line-height:1.15;color:{TEKST};padding:20px 0 2px")
        lemma = ui.label().classes("w-full text-center").style(f"color:{ZACHT};font-size:14px")
        terugkoppeling = ui.column().classes("w-full gap-1 items-center").style(
            "min-height:70px;padding-top:8px")
        hulp = ui.row().classes("w-full gap-2 no-wrap").style("padding-top:4px")
        opslagmelding = ui.label().style(f"color:{ZACHT};font-size:11.5px;min-height:16px")

    with ui.element("div").classes("antwoordbalk"):
        with ui.row().classes("w-full gap-2 no-wrap items-center"):
            invoer = ui.input(placeholder="vertaling").props(
                "outlined dense dark autocomplete=off").classes("flex-grow")
            knop = ui.button("Nakijken").props("unelevated").style(
                f"background:{MERK};color:{INKT};font-weight:700;height:40px;min-width:104px")

    with ui.element("div").classes("onderbalk"):
        for naam, teken, actief in [("Vandaag", "●", False), ("Oefenen", "■", True),
                                    ("Lezen", "☰", False), ("Voortgang", "▲", False)]:
            merk = " actief" if actief else ""
            ui.html(f"<div class='vak{merk}'><span style='font-size:17px'>{teken}</span>{naam}</div>")

    # ---------------- gedrag ----------------
    def teken_streepjes():
        streepjes.clear()
        with streepjes:
            for n in range(len(sessie.kaarten)):
                kleur = MERK if n < sessie.i else (TEKST if n == sessie.i else RAND)
                ui.element("div").style(f"flex:1;height:4px;border-radius:2px;background:{kleur}")

    def toon_hulp(soort):
        k = sessie.kaart
        if not k:
            return
        if soort == "Uitspraak":
            tekst = motor.fonetisch_uit_translit(k.get("fonetisch", "")) or k.get("fonetisch", "")
        elif soort == "Hint":
            nl = k.get("nederlands", "")
            tekst = nl[:2] + "…" if len(nl) > 3 else nl
        else:
            seg = motor.ontleed_segmenten(k.get("grieks", ""), grieks_info=k.get("grieks_info", ""))
            tekst = " + ".join(str(s) for s in seg) if seg else "geen opbouw bekend"
        ui.notify(tekst, position="top", color="dark")

    def toon_kaart():
        terugkoppeling.clear()
        hulp.clear()
        sessie.beoordeeld = False
        k = sessie.kaart
        if k is None:
            woord.text = "✓"
            lemma.text = f"Klaar — {sessie.goed} goed, {sessie.fout} fout."
            teller.text = ""
            invoer.set_visibility(False)
            knop.text = "Nieuwe ronde"
            teken_streepjes()
            return
        woord.text = k.get("grieks", "")
        lemma.text = k.get("grieks_info") or k.get("woordsoort", "")
        teller.text = f"{sessie.i + 1}/{len(sessie.kaarten)}"
        knop.text = "Nakijken"
        invoer.value = ""
        teken_streepjes()
        with hulp:
            for label in ("Uitspraak", "Hint", "Opbouw"):
                ui.button(label, on_click=lambda l=label: toon_hulp(l)).props("flat dense").style(
                    f"flex:1;color:{ZACHT};border:1px solid {RAND};border-radius:8px;font-size:12px")
        invoer.run_method("focus")

    async def nakijken():
        k = sessie.kaart
        if k is None:
            await run.io_bound(g.bewaar, True)
            ui.notify("Voortgang opgeslagen", position="top", color="positive")
            ui.navigate.to("/oefenen")
            return
        if sessie.beoordeeld:
            sessie.i += 1
            toon_kaart()
            return
        juist = bool(motor.check_betekenis(invoer.value or "", k.get("nederlands", "")))
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
        invoer.run_method("focus")

    knop.on_click(nakijken)
    invoer.on("keydown.enter", nakijken)
    toon_kaart()


ui.run(title="Grieks", dark=True, port=8123, reload=False, show=False, favicon="\U0001F4D6",
       storage_secret=os.environ.get("GRIEKS_SESSIE_SLEUTEL", "grieks-lokaal-ontwikkelen"))
