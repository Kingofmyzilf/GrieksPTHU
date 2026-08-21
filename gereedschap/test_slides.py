# -*- coding: utf-8 -*-
"""Controleert de overgetypte grammatica-slides en hun opmaak.

De slides worden in de app met unsafe_allow_html op het scherm gezet. Dat betekent twee
dingen die stil kunnen misgaan:

  * een tag die niet gesloten is loopt door over de rest van de pagina. Streamlit geeft
    geen fout; je ziet alleen dat de helft van het tabblad scheef staat.
  * een klasse die in de slides staat maar niet in de opmaak levert gewoon platte tekst op.
    Ook daar komt geen fout van, en juist bij deze slides is kleur betekenis: grijs wil
    zeggen 'hoeft niet geleerd te worden' (slide 63 en 65 zeggen dat er letterlijk bij).

De opmaak staat op twee plekken -- SLIDE_CSS in de app en OPMAAK in gereedschap/
proef_slides.py -- want de proefpagina moet buiten Streamlit te bekijken zijn. Die twee
kunnen uit elkaar lopen, dus wordt hier nagerekend dat beide alle gebruikte klassen kennen.

En het tabblad hangt de slides op aan de paginanummers uit grammatica_index.json
(pdf_start/pdf_eind). Ontbreekt er één slide in dat bereik, dan krijgt de student midden in
een onderwerp een leeg vak.

Draaien:  py gereedschap/test_slides.py
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

import uitvoer

uitvoer.zet_utf8()

TOTAAL = 376
LEEG = {"br", "hr", "img", "col"}
fouten = []


def kijk(goed, melding):
    if goed:
        print(f"  ok   {melding}")
    else:
        fouten.append(melding)
        print(f"  MIS  {melding}")


def klassen_uit_opmaak(tekst):
    """Alle .klassenamen die in een stukje CSS worden gedefinieerd."""
    return set(re.findall(r"\.([a-z][a-z0-9]*)\b(?=[^{}]*\{)", tekst))


def onbalans(html):
    """De eerste tag die niet klopt, of None."""
    stapel = []
    for m in re.finditer(r"<(/?)([a-z0-9]+)[^>]*?(/?)>", html):
        sluit, naam, zelf = m.group(1), m.group(2), m.group(3)
        if naam in LEEG or zelf:
            continue
        if sluit:
            if not stapel or stapel[-1] != naam:
                return f"</{naam}> zonder open tag"
            stapel.pop()
        else:
            stapel.append(naam)
    return f"niet gesloten: {', '.join(stapel)}" if stapel else None


class NepBlok:
    """st.container() / st.expander() / een kolom."""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def markdown(self, s="", **k):
        gezien.append(("markdown", s))

    def button(self, l, **k):
        gezien.append(("button", l))
        return False

    def __getattr__(self, n):
        def doe(*a, **k):
            gezien.append((n, a[0] if a else ""))
        return doe


class NepState(dict):
    def __getattr__(self, n):
        try:
            return self[n]
        except KeyError:
            raise AttributeError(n)

    def __setattr__(self, n, v):
        self[n] = v


class NepSt(NepBlok):
    """Zoveel Streamlit als dit tabblad aanraakt."""

    session_state = NepState()

    def columns(self, spec, **k):
        return [NepBlok() for _ in range(spec if isinstance(spec, int) else len(spec))]

    def container(self, **k):
        return NepBlok()

    def expander(self, l, **k):
        gezien.append(("expander", l))
        return NepBlok()

    def radio(self, l, opties, **k):
        return keuzes.get("_modus", list(opties)[0])

    def selectbox(self, l, opties, **k):
        opties = list(opties)
        i = k.get("index", 0) or 0
        return opties[min(i, len(opties) - 1)] if opties else None

    def text_input(self, l, **k):
        return keuzes.get("_zoek", "")

    def toggle(self, l, **k):
        return keuzes.get("_alles", k.get("value", False))

    def slider(self, l, a, b, c, **k):
        return c

    def dataframe(self, df, **k):
        gezien.append(("dataframe", len(df)))

    def cache_data(self, *a, **k):
        return a[0] if a and callable(a[0]) else (lambda fn: fn)


gezien = []
keuzes = {}


def tabblad_proef(app, slides):
    """Het echte tabblad uitvoeren met een nagemaakte Streamlit.

    Het tabblad zit midden in overhoring_web.py en dat bestand start bij importeren de hele
    app op (inclusief Google Sheets), dus wordt hier het blok uit de bron geknipt. Dat is
    omslachtig, maar het toetst de code die er echt staat: bij een eerdere verbouwing stond
    een scoreregel in de verkeerde tak van een if, en dat zag je niet aan de code.
    """
    import pandas as pd

    def knip(begin, eind):
        i = app.index(begin)
        return app[i:app.index(eind, i)]

    st_nep = NepSt()
    hulp = knip("# De 376 grammatica-slides stonden", "@st.cache_resource\ndef nt_index")
    hulp += ("\n\ndef laad_grammatica_db():\n"
             "    with open('grammatica_index.json', encoding='utf-8') as f:\n"
             "        return json.load(f)\n")
    omgeving = {"st": st_nep, "json": json, "os": os, "re": re, "pd": pd,
                "unicodedata": __import__("unicodedata"), "difflib": __import__("difflib")}
    exec(compile(hulp, "helpers", "exec"), omgeving)
    tab = knip('            st.subheader("📐 Grammatica")',
               "        # ==========================================\n        # TAB 9")
    tab = "\n".join(r[12:] if r.startswith(" " * 12) else r for r in tab.split("\n"))
    code = compile(tab, "tabblad", "exec")

    def draai(**kn):
        gezien.clear()
        keuzes.clear()
        keuzes.update(kn)
        st_nep.session_state.clear()
        exec(code, omgeving)
        return list(gezien)

    def getekend(rijen):
        return [t for s, t in rijen if s == "markdown" and "class='gslide'" in str(t)]

    def opmaak(rijen):
        return [t for s, t in rijen if s == "markdown" and ".gslide " in str(t)]

    r = draai(_modus="📖 Bestuderen", _alles=True)
    # G1 heeft 8 slides; het losse overzicht onderaan is de negende.
    kijk(len(getekend(r)) == 9, f"'alles achter elkaar' tekent G1 helemaal ({len(getekend(r))} van 9)")
    kijk(len(opmaak(r)) == 1, f"de opmaak gaat één keer mee, niet per slide ({len(opmaak(r))}x)")
    r = draai(_modus="📖 Bestuderen", _alles=False)
    kijk(len(getekend(r)) == 2, f"per slide staat er één slide (+overzicht) ({len(getekend(r))})")

    # Zoeken op wat er in de slides zélf staat. Dit kon met de oude OCR niet: die maakte
    # 'evayyéatov' van εὐαγγέλιον, dus een Griekse zoekterm vond nooit iets.
    for zoek, hoort in [("genitivus absolutus", 40), ("aoristus", 15),
                        ("λύω", 38), ("μὴ γένοιτο", 48), ("stoomboot", 33)]:
        r = draai(_modus="🔎 Zoeken", _zoek=zoek)
        koppen = [str(t) for s, t in r if s == "markdown" and str(t).startswith("**G")]
        eerste = koppen[0].split("·")[0].strip("* ") if koppen else "(niets)"
        kijk(eerste == f"G{hoort}", f"zoeken op '{zoek}' geeft G{hoort} bovenaan (kreeg {eerste})")
    # 'molenaar' staat op vier slides; het gaat erom dat ze allemaal gevonden worden.
    r = draai(_modus="🔎 Zoeken", _zoek="molenaar")
    koppen = [str(t) for s, t in r if s == "markdown" and str(t).startswith("**G")]
    gevonden = {k.split("·")[0].strip("* ") for k in koppen}
    kijk({"G1", "G23", "G36", "G45"} <= gevonden,
         f"'molenaar' vindt ook de verba liquida (G23/G45), niet alleen het alfabet ({sorted(gevonden)})")

    r = draai(_modus="📋 Onderwerpen")
    rijen = [t for s, t in r if s == "dataframe"]
    kijk(rijen == [50], f"de onderwerpenlijst heeft 50 regels ({rijen})")


def main():
    print("== de slides zelf ==")
    with open("grammatica_slides.json", encoding="utf-8") as f:
        slides = {int(s["nr"]): s for s in json.load(f)}
    kijk(len(slides) == TOTAAL, f"alle {TOTAAL} slides staan erin (nu {len(slides)})")
    gaten = [n for n in range(1, TOTAAL + 1) if n not in slides]
    kijk(not gaten, f"geen gaten in de nummering ({len(gaten)} ontbreken)")

    zonder = [n for n, s in slides.items() if not (s.get("html") or "").strip()]
    kijk(not zonder, f"geen lege slides ({len(zonder)}: {zonder[:6]})")
    kort = [n for n, s in slides.items() if len(s.get("tekst", "")) < 30]
    kijk(not kort, f"geen slide met bijna geen tekst ({len(kort)}: {kort[:6]})")
    zoekbaar = all("tekst" in s for s in slides.values())
    kijk(zoekbaar, "elke slide heeft een tekst-veld (daar zoekt de app op)")
    cursussen = {s.get("cursus") for s in slides.values()}
    kijk(cursussen == {1, 2, 3}, f"cursus 1, 2 en 3 zijn allemaal gezet ({sorted(c for c in cursussen if c)})")

    print("== html ==")
    stuk = [(n, onbalans(s["html"])) for n, s in sorted(slides.items())]
    stuk = [(n, r) for n, r in stuk if r]
    kijk(not stuk, f"alle tags in balans ({len(stuk)} scheef: {stuk[:3]})")

    print("== opmaak ==")
    gebruikt = set()
    for s in slides.values():
        for kl in re.findall(r"class='([^']+)'", s["html"]):
            gebruikt.update(kl.split())
    app = open("overhoring_web.py", encoding="utf-8").read()
    proef = open(os.path.join("gereedschap", "proef_slides.py"), encoding="utf-8").read()
    css_app = app[app.index("SLIDE_CSS"):]
    css_app = css_app[:css_app.index('"""', css_app.index('"""') + 3)]
    css_proef = proef[proef.index("OPMAAK"):]
    css_proef = css_proef[:css_proef.index('"""', css_proef.index('"""') + 3)]
    for naam, css in (("de app", css_app), ("de proefpagina", css_proef)):
        mist = sorted(gebruikt - klassen_uit_opmaak(css))
        kijk(not mist, f"{naam} kent alle {len(gebruikt)} gebruikte klassen (mist: {mist})")

    print("== koppeling met de onderwerpen ==")
    with open("grammatica_index.json", encoding="utf-8") as f:
        db = json.load(f)
    items = db["items"]
    mis_bereik = []
    for g, info in items.items():
        ontbreekt = [p for p in range(info["pdf_start"], info["pdf_eind"] + 1) if p not in slides]
        if ontbreekt:
            mis_bereik.append((f"G{g}", ontbreekt))
    kijk(not mis_bereik, f"elk onderwerp heeft al zijn slides ({mis_bereik[:3]})")
    # De kop van de eerste slide van een onderwerp hoort bij de titel te passen; dat is de
    # controle dat de nummering van de pdf en van het overtypen niet verschoven zijn.
    scheef = []
    for g, info in items.items():
        kop = slides.get(info["pdf_start"], {}).get("kop", "")
        if not kop.startswith(f"G{g} "):
            scheef.append((f"G{g}", kop[:30]))
    kijk(not scheef, f"de kop van elke eerste slide begint met zijn G-nummer ({scheef[:3]})")
    ov = [int(k) for k in db.get("overzichten", {})]
    kijk(all(p in slides for p in ov), f"alle {len(ov)} losse overzichten bestaan als slide")

    print("== de app zelf ==")
    kijk("def laad_grammatica_slides" in app, "laad_grammatica_slides bestaat")
    kijk("def toon_slide" in app, "toon_slide bestaat")
    for weg in ("fitz", "render_slide", "open_grammatica_pdf", "grammatica_overzicht.pdf"):
        kijk(weg not in app, f"geen spoor meer van {weg} (de pdf is eruit)")
    kijk("pymupdf" not in open("requirements.txt", encoding="utf-8").read(),
         "pymupdf staat niet meer in requirements.txt")
    kijk(not os.path.exists("grammatica_overzicht.pdf"),
         "de pdf van 22 MB staat niet meer in de map")

    print("== het tabblad zelf ==")
    tabblad_proef(app, slides)

    print()
    if fouten:
        print(f"{len(fouten)} probleem/problemen:")
        for f_ in fouten:
            print(f"  - {f_}")
        sys.exit(1)
    tekens = sum(len(s.get("tekst", "")) for s in slides.values())
    print(f"alles in orde: {len(slides)} slides, {tekens} tekens tekst, "
          f"{os.path.getsize('grammatica_slides.json')/1024:.0f} kB")


if __name__ == "__main__":
    main()
