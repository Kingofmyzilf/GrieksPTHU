# -*- coding: utf-8 -*-
"""Grieks — NiceGUI-schil op grieks_motor.py.

Proefopstelling voor de drie bevindingen die in Streamlit niet op te lossen waren:
  * vier vaste bestemmingen onderaan in plaats van twaalf tabbladen in een schuifbalk;
  * een antwoordbalk die vast onderaan blijft staan, waar de duim en het toetsenbord zijn;
  * een oefenbeurt zonder paginaherlaad — het scherm knippert niet, de scrollpositie
    blijft staan en het toetsenbord klapt niet dicht.

Starten:  py -m nicegui grieks_app.py     of     py grieks_app.py
"""
import random
from nicegui import ui, app

import grieks_motor as motor

# --- huisstijl (overgenomen uit .streamlit/config.toml) ---
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
  /* de antwoordbalk blijft staan waar de duim is */
  .antwoordbalk {{ position:fixed; left:0; right:0; bottom:64px; z-index:20;
                   background:{INKT}; border-top:1px solid {RAND}; padding:10px 14px 12px; }}
  .onderbalk {{ position:fixed; left:0; right:0; bottom:0; z-index:30; height:64px;
                background:{VLAK}; border-top:1px solid {RAND}; display:flex; }}
  .onderbalk button {{ flex:1; background:none; border:none; color:{ZACHT};
                       font-size:11px; display:flex; flex-direction:column;
                       align-items:center; justify-content:center; gap:3px; cursor:pointer; }}
  .onderbalk button.actief {{ color:{MERK}; }}
  .inhoud {{ padding:14px 14px 190px; max-width:640px; margin:0 auto; }}
  input {{ color:{TEKST} !important; }}
</style>
""", shared=True)


class Sessie:
    """Eén oefensessie: welke kaarten, waar we zijn, en hoe het gaat."""

    def __init__(self, aantal=12):
        vocab = motor.laad_vocab_db()
        geoefend = [w for w in vocab if (w.get("les") or 99) <= 4]
        self.kaarten = random.sample(geoefend, min(aantal, len(geoefend)))
        self.i = 0
        self.goed = 0
        self.fout = 0
        self.beoordeeld = False

    @property
    def kaart(self):
        return self.kaarten[self.i] if self.i < len(self.kaarten) else None

    @property
    def klaar(self):
        return self.i >= len(self.kaarten)


sessie = Sessie()


@ui.page("/")
def hoofdpagina():
    ui.query("body").style(f"background:{INKT}")

    with ui.column().classes("inhoud w-full gap-3"):
        # --- voortgang binnen de sessie: streepjes, zodat je ziet dat het eindig is ---
        kop = ui.row().classes("w-full items-center justify-between")
        with kop:
            ui.label("Woordenschat · les 4").style(f"color:{ZACHT};font-size:13px")
            teller = ui.label().style(f"color:{ZACHT};font-size:13px")
        streepjes = ui.row().classes("w-full gap-1 no-wrap")

        # --- het woord ---
        woord = ui.label().classes("grieks w-full text-center") \
            .style(f"font-size:58px;line-height:1.15;color:{TEKST};padding:26px 0 4px")
        lemma = ui.label().classes("w-full text-center").style(f"color:{ZACHT};font-size:14px")

        # --- de feedback komt hier, op de plek van het antwoord, niet bovenaan ---
        terugkoppeling = ui.column().classes("w-full gap-1 items-center") \
            .style("min-height:64px;padding-top:10px")

        hulp = ui.row().classes("w-full gap-2 no-wrap").style("padding-top:6px")

    # --- vaste antwoordbalk, direct boven de onderbalk ---
    with ui.element("div").classes("antwoordbalk"):
        with ui.row().classes("w-full gap-2 no-wrap items-center"):
            invoer = ui.input(placeholder="vertaling").props(
                "outlined dense dark autocomplete=off").classes("flex-grow")
            knop = ui.button("Nakijken").props("unelevated").style(
                f"background:{MERK};color:{INKT};font-weight:700;height:40px")

    # --- vier vaste bestemmingen ---
    with ui.element("div").classes("onderbalk"):
        for naam, teken, actief in [("Vandaag", "●", False), ("Oefenen", "■", True),
                                    ("Lezen", "☰", False), ("Voortgang", "▲", False)]:
            b = ui.html(f"<button class='{'actief' if actief else ''}'>"
                        f"<span style='font-size:17px'>{teken}</span>{naam}</button>")
            b.style("flex:1;display:flex")

    # ---------------- gedrag ----------------
    def teken_streepjes():
        streepjes.clear()
        with streepjes:
            for n in range(len(sessie.kaarten)):
                if n < sessie.i:
                    kleur = MERK
                elif n == sessie.i:
                    kleur = TEKST
                else:
                    kleur = RAND
                ui.element("div").style(
                    f"flex:1;height:4px;border-radius:2px;background:{kleur}")

    def toon_kaart():
        terugkoppeling.clear()
        hulp.clear()
        sessie.beoordeeld = False
        k = sessie.kaart
        if k is None:
            woord.text = "✓"
            lemma.text = f"Klaar. {sessie.goed} goed, {sessie.fout} fout."
            invoer.set_visibility(False)
            knop.set_visibility(False)
            teller.text = ""
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

    def toon_hulp(soort):
        k = sessie.kaart
        if k is None:
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

    def nakijken():
        """Beoordelen en doorgaan — allebei zonder de pagina te verversen."""
        k = sessie.kaart
        if k is None:
            return
        if sessie.beoordeeld:
            sessie.i += 1
            toon_kaart()
            return
        juist = motor.check_betekenis(invoer.value or "", k.get("nederlands", ""))
        sessie.beoordeeld = True
        if juist:
            sessie.goed += 1
        else:
            sessie.fout += 1
        terugkoppeling.clear()
        with terugkoppeling:
            ui.label("Goed" if juist else "Niet goed").style(
                f"color:{GOED if juist else FOUT};font-weight:700;font-size:16px")
            ui.label(k.get("nederlands", "")).style(f"color:{TEKST};font-size:15px;text-align:center")
            ui.label(f"{sessie.goed} goed · {sessie.fout} fout").style(f"color:{ZACHT};font-size:12px")
        knop.text = "Volgende"
        invoer.run_method("focus")

    knop.on_click(nakijken)
    invoer.on("keydown.enter", nakijken)
    toon_kaart()


ui.run(title="Grieks", dark=True, port=8123, reload=False, show=False,
       favicon="\U0001F4D6")
