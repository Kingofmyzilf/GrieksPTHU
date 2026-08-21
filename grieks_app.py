# -*- coding: utf-8 -*-
"""Grieks — NiceGUI-schil op grieks_motor.py, grieks_opslag.py en grieks_gebruiker.py.

Vormgeving volgt de designreview: inloggen in de hoofdkolom, Grieks in een tekstfont,
vier vaste bestemmingen onderaan, een antwoordbalk die blijft staan, en oefenbeurten
zonder paginaherlaad.

Starten:  py grieks_app.py
"""
import csv
import difflib
import io
import json
import math
import os
import random
import re
import time
from datetime import date, timedelta
from urllib.parse import quote

from fastapi.responses import JSONResponse
from nicegui import app, run, ui

import grieks_gebruiker as gebruikers
import grieks_motor as motor
import grieks_opslag as opslag
import hebreeuws

# --- huisstijl (uit .streamlit/config.toml) ---
INKT, VLAK, RAND = "#0e1117", "#1e1e1e", "#2b3038"
TEKST, ZACHT = "#fafafa", "#9aa4ae"
MERK, GOED, FOUT = "#33ccff", "#3ddc97", "#ff6b81"
# De kleuren van de Hebreeuwse woorddelen staan in hebreeuws.KLEUREN, want de uitgebreide
# app gebruikt dezelfde.
GRIEKS_FONT = "'Gentium Book Plus','Palatino Linotype',Georgia,serif"
# Hebreeuws heeft een eigen letter nodig: Gentium dekt het niet. Noto Serif Hebrew zet de
# klinkertekens onder de letter waar ze horen; David is de terugval die op Windows al staat.
HEBREEUWS_FONT = "'Noto Serif Hebrew','David','Times New Roman',serif"

# Tekstmaten. Hieronder stond van alles tussen 10 en 12px; met de telefoon in één hand
# is dat niet te lezen, en bij Grieks al helemaal niet — een spiritus of iota subscriptum
# valt dan weg. KLEIN is de ondergrens voor bijzaak (tellers, meldingen, toelichting),
# BASIS voor gewone begeleidende tekst, GRIEKS_MIN voor alles waar Grieks in staat.
KLEIN, BASIS, GRIEKS_MIN = "12.5px", "13px", "15px"
# Hebreeuws mag nog iets groter dan Grieks: de klinkertekens zijn kleine puntjes
# en streepjes ónder de letter, en die vallen eerder weg dan een spiritus.
HEBREEUWS_MIN = "17px"

BESTEMMINGEN = [("Vandaag", "●", "/vandaag"), ("Oefenen", "■", "/oefenen"),
                ("Lezen", "☰", "/lezen"), ("Voortgang", "▲", "/voortgang")]

# Zelfde tekst als op het inlogscherm van de uitgebreide app. Op je beginscherm opent
# hij zonder adresbalk, dus je hebt een schermvullende app zonder iets te installeren.
APP_OP_MOBIEL = (
    f"<div style='font-size:12.5px;line-height:1.7;color:{ZACHT}'>"
    f"<b style='color:{TEKST}'>Als app op je mobiel?</b><br>"
    f"<b>iPhone (Safari):</b> tik onderin op het vierkantje met het pijltje omhoog → "
    f"<i>Zet op beginscherm</i><br>"
    f"<b>Android (Chrome):</b> tik rechtsboven op de drie puntjes → "
    f"<i>Toevoegen aan startscherm</i></div>")

ui.add_head_html(f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Gentium+Book+Plus:wght@400;700&family=Noto+Serif+Hebrew:wght@400;700&display=swap" rel="stylesheet">
<meta name="theme-color" content="{INKT}">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/static/grieks-192.png">
<style>
  body {{ background:{INKT}; color:{TEKST}; }}
  /* Grieks nooit onder 15px, ook niet als het in een regel bijzaak staat: een spiritus
     of iota subscriptum is op 12,5px met de telefoon in één hand niet te zien. max(1em,…)
     laat het meegroeien waar de omringende tekst al groter is, en een expliciete maat op
     het element zelf (het woord op 58px) wint hier gewoon van. */
  .grieks {{ font-family:{GRIEKS_FONT}; font-weight:400;
             font-size:max(1em, {GRIEKS_MIN}); }}
  /* Hebreeuws leest van rechts naar links. `direction` regelt dat, maar het is `isolate`
     dat het werk doet: zonder dat trekt de browser de leesrichting door naar de
     Nederlandse tekst eromheen, en dan springt een komma of een cijfer naar de verkeerde
     kant van de regel. Elk stukje Hebreeuws staat dus op zichzelf.

     Gentium heeft geen Hebreeuws; Noto Serif Hebrew wel, en die zet klinkertekens en
     cantillatie netjes onder de letter in plaats van ernaast. De terugval David staat op
     vrijwel elke Windows-machine. */
  .hebreeuws {{ font-family:{HEBREEUWS_FONT}; font-weight:400;
                direction:rtl; unicode-bidi:isolate;
                font-size:max(1em, {HEBREEUWS_MIN}); }}
  /* Een hele regel die met Hebreeuws begint: dan mag de regel zelf ook rechts uitlijnen. */
  .hebrij {{ direction:rtl; unicode-bidi:isolate; text-align:right; }}
  /* Een woord in een leestekst: eigen aanraakvlak, met genoeg lucht om te mikken. */
  .leeswoord {{ font-size:27px; padding:2px 3px 1px; margin:0 2px;
                cursor:pointer; display:inline-block; }}
  /* Een versnummer om aan te tikken. Klein, maar met een aanraakvlak van 44 punten
     eromheen — anders mis je hem op een telefoon. */
  .versnr {{ color:{ZACHT}; font-size:12px; vertical-align:super; cursor:pointer;
             padding:6px 4px; margin:0 1px; position:relative; }}
  .versnr::after {{ content:''; position:absolute; left:50%; top:50%;
                    width:44px; height:44px; transform:translate(-50%, -50%); }}
  .versnr.aan {{ color:{MERK}; font-weight:700; }}
  /* De betekenissen bovenaan, naast elkaar en horizontaal te schuiven. Ze stonden eerst
     onder de tekst, en dan moet je bij een lang hoofdstuk helemaal naar beneden om te
     zien wat je net hebt aangetikt. */
  .uitlegbalk {{ position:sticky; top:0; z-index:15; background:{INKT};
                 border-bottom:1px solid {RAND}; margin:0 -14px; padding:8px 14px;
                 display:flex; gap:8px; overflow-x:auto; scrollbar-width:none; }}
  .uitlegbalk::-webkit-scrollbar {{ display:none; }}
  .uitlegkaart {{ flex:0 0 auto; max-width:74vw; background:{VLAK};
                  border:1px solid {RAND}; border-radius:10px; padding:7px 10px; }}
  /* De twee balken staan onder elkaar vast onderaan. dvh volgt het zichtbare deel van
     het scherm, zodat ze meebewegen als de adresbalk in- of uitschuift. */
  /* De drie hoogtes staan in variabelen en alles rekent ermee. Los ingevulde getallen
     liepen uit elkaar: de veilige zone stond op de balk die de onderrand niet raakt, en
     de inhoud trok er 136 af terwijl de balken samen 156 innemen — vandaar dat de laatste
     regel van de eindkaart halverwege onder de knopbalk verdween. */
  /* Quasar zet zijn eigen kleurklassen met !important op elke knop, elk pictogram en elk
     invoerveld. Een inline background verloor het dus, en de hele app stond in het
     standaardblauw #1976D2 in plaats van in het cyaan van MERK — gemeten op het scherm
     kwam de knop Nakijken eruit als rgb(88,152,212) met witte letters. Dit zet de
     huisstijl op de plek waar Quasar hem leest, in plaats van per knop te vechten. */
  :root {{ --q-primary:{MERK}; --q-secondary:{MERK}; --q-accent:{MERK};
           --q-positive:{GOED}; --q-negative:{FOUT};
           --q-dark:{VLAK}; --q-dark-page:{INKT};
           --veilig:env(safe-area-inset-bottom, 0px);
           --onderbalk:64px; --antwoordbalk:92px; }}
  .antwoordbalk {{ position:fixed; left:0; right:0; z-index:20;
                   bottom:calc(var(--onderbalk) + var(--veilig));
                   background:{INKT}; border-top:1px solid {RAND}; padding:10px 14px 12px; }}
  /* De onderbalk raakt wél de onderrand, dus hier hoort de veilige zone: op een telefoon
     met veegnavigatie valt anders de onderste strook van de vier labels achter de
     gebaarbalk. Met drieknopsnavigatie is --veilig nul en verandert er niets. */
  .onderbalk {{ position:fixed; left:0; right:0; bottom:0; z-index:30; display:flex;
                height:calc(var(--onderbalk) + var(--veilig));
                padding-bottom:var(--veilig);
                background:{VLAK}; border-top:1px solid {RAND}; }}
  /* Staat het toetsenbord open, dan zijn de vier bestemmingen dode ruimte: je bent aan
     het typen. Ze gaan weg, de antwoordbalk zakt naar de onderrand en het vraagvak krijgt
     die 64 punten erbij — precies wat er ontbrak om woord, lemma en aanwijzing samen te
     laten passen. Zie het scriptje hieronder voor wanneer dit aan gaat. */
  body.typt .onderbalk {{ display:none; }}
  body.typt .antwoordbalk {{ bottom:var(--veilig); }}
  .onderbalk .vak {{ flex:1; display:flex; flex-direction:column; align-items:center;
                     justify-content:center; gap:3px; font-size:11px; color:{ZACHT};
                     cursor:pointer; user-select:none; text-decoration:none; }}
  .onderbalk .vak.actief {{ color:{MERK}; }}
  /* NiceGUI zet zelf 16px rondom de inhoud. Daardoor begon de kolom 16px lager dan het
     scherm terwijl zijn hoogte uit de volle 100dvh werd gerekend, en viel de onderste
     16px — precies de opslagmelding — achter de vaste antwoordbalk. Je zag alleen de
     bovenkant van de letters en kon er niet bij, ook niet als het 'opslaan mislukt' was.
     .inhoud en .smal brengen hun eigen marge mee, dus deze kan weg. */
  .nicegui-content {{ padding:0; }}
  .inhoud {{ padding:14px 14px 96px; max-width:640px; margin:0 auto; }}
  /* Precies zoveel ruimte onderaan als de twee balken samen innemen, geen pixel minder:
     wat eronder valt is onbereikbaar. */
  .inhoud.metbalk {{ padding-bottom:calc(var(--onderbalk) + var(--antwoordbalk)
                                         + var(--veilig)); }}
  /* :not(.vast) moet: een vaste kolom regelt zijn ruimte met height, en zonder deze
     uitzondering won deze regel op specificiteit van de padding-bottom van 4px —
     dan kromp het vraagvak juist met 88px zodra het toetsenbord openging. */
  body.typt .inhoud.metbalk:not(.vast) {{
      padding-bottom:calc(var(--antwoordbalk) + var(--veilig)); }}
  .smal {{ max-width:420px; margin:0 auto; padding:14px; }}
  .kaart {{ background:{VLAK}; border:1px solid {RAND}; border-radius:12px; padding:14px; }}
  /* Een tikvlak van minstens 48px zonder dat de knop meer ruimte inneemt: een
     onzichtbaar laagje groeit over de knop heen. Verticale ruimte is schaars tijdens het
     oefenen, dus wat je ziet mag niet groter worden — alleen wat je kunt raken. */
  .raakbaar {{ position:relative; }}
  .raakbaar::after {{ content:''; position:absolute; left:50%; top:50%;
                      width:max(100%, 48px); height:max(100%, 48px);
                      transform:translate(-50%, -50%); }}
  /* 13px binnenruimte geeft een knop van ~50px hoog: prettig te raken met een duim.
     Dat kan sinds de hint nog maar één regel is; daarvoor moest hij krapper om vier
     opties mét hint op het scherm te houden. */
  .keuze {{ background:{VLAK}; border:1px solid {RAND}; border-radius:10px; padding:13px 14px;
            cursor:pointer; font-size:16px; text-align:left; width:100%; color:{TEKST};
            min-height:48px; }}
  .keuze:hover {{ border-color:{MERK}; }}
  /* NiceGUI zet een wikkeldiv om elke ui.html. Die krimpt mee met zijn inhoud, dus
     width:100% op de knop rekende tegen een te smalle ouder en stonden de opties
     rafelig naast elkaar (240, 198, 315, 315 gemeten). Dit zet de wikkel op volle
     breedte, zodat vier opties even breed zijn en even makkelijk te raken. */
  .keuzevak > * {{ width:100%; }}
  /* Het vraagvak is een toneel: de feedback komt eroverheen te liggen in plaats van
     eronder. Zonder dit groeide de pagina bij elk antwoord, schoven de knoppen weg en
     stond de uitslag onder de vouw zodra het toetsenbord openstond.

     De pagina is precies zo hoog als het scherm min de twee vaste balken (92 + 64), en
     het vraagvak krijgt met flex:1 wat de kop, de hulpknoppen en de rest overlaten. Dat
     rekent zichzelf uit — een vast getal klopte niet meer zodra er een regel bij kwam
     of wegviel, en dan viel de onderste antwoordknop half buiten beeld. */
  .inhoud.metbalk.vast {{ padding-bottom:4px; display:flex; flex-direction:column;
                          height:calc(100dvh - var(--onderbalk) - var(--antwoordbalk)
                                      - var(--veilig)); }}
  body.typt .inhoud.metbalk.vast {{
      height:calc(100dvh - var(--antwoordbalk) - var(--veilig)); }}
  .vraagvak {{ position:relative; flex:1 1 auto; min-height:0; overflow-y:auto; }}
  .vraagvak.vrij {{ flex:0 0 auto; }}     /* de eindsamenvatting mag wél doorlopen */
  .vraagvak > .overlay {{ position:absolute; left:0; right:0; top:0; bottom:0;
                          background:{INKT}; overflow-y:auto; }}
  .vraagvak > .overlay:empty {{ display:none; }}
</style>
<script>
  // Het toetsenbord meten in plaats van naar focus kijken: focus springt heen en weer
  // zodra je op Nakijken tikt, en dan zou de balk onder je vinger vandaan schuiven.
  // visualViewport krimpt alleen echt als er een toetsenbord staat.
  (function () {{
    var vv = window.visualViewport;
    if (!vv) return;
    var meet = function () {{
      document.body.classList.toggle('typt', vv.height < window.innerHeight * 0.75);
    }};
    vv.addEventListener('resize', meet);
    meet();
  }})();
</script>
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
    """Is de Griekse bijbeltekst er? Zonder die tekst vervallen Ontleden, de klankwetten en
    het lezen van een Griekse tekst.

    Let op de eerste regel. De tekst staat sinds de opsplitsing per boek ingepakt in nt/,
    en deze functie keek alleen naar de drie oude bestandsnamen. Die staan in .gitignore,
    dus op elke verse kloon — en dus ook op de gehoste app — was dit False en viel de halve
    app stil zonder één foutmelding. Wie hier iets verandert: zet de nieuwe plek erbij,
    haal de oude niet weg, want een oude werkkopie moet blijven werken."""
    return (os.path.exists(os.path.join("nt", "index.json"))
            or any(os.path.exists(naam) for naam in
                   ("bijbel_nt.json", "bijbel_nt_deel1.json", "bijbel_nt_deel2.json")))


BIJBEL = bijbel_aanwezig()

# Hoe vaak er naar de Sheet wordt geschreven. Lokaal na elke beurt: je raakt dan nooit
# iets kwijt en het wachten valt weg in de tijd dat je de feedback leest. Op een gehoste
# lichte versie kost elke opslag twee netwerkrondjes (lezen om samen te voegen, dan
# schrijven) op een trage machine — daar is één keer per vijf beurten prettiger. Aan het
# einde van een ronde wordt sowieso geforceerd bewaard.
OPSLAG_INTERVAL = 1 if BIJBEL else 5


def streamlit_adres(g=None):
    """De volledige app, met je naam en codewoord erin zodat je meteen goed zit.
    De Streamlit-app leest die uit ?u= (zie main() daar). Ze staan dan wel in je
    browsergeschiedenis; dat kan hier, omdat het geen wachtwoord is — de app zegt dat
    bij het inloggen ook met zoveel woorden."""
    if not STREAMLIT_URL:
        return ""
    sleutel = getattr(g, "sleutel", "") if g is not None else ""
    return f"{STREAMLIT_URL}/?u={quote(sleutel)}" if sleutel else STREAMLIT_URL


def volledige_app_blok(g=None):
    """Wat de twee apps van elkaar onderscheiden. Staat op het inlogscherm en op
    Vandaag, zodat je nooit hoeft te raden welke van de twee je voor je hebt."""
    adres = streamlit_adres(g)
    if not adres:
        return ""
    return (f"<div class='kaart' style='font-size:12.5px;line-height:1.6;color:{ZACHT}'>"
            f"<b style='color:{TEKST}'>Twee apps, dezelfde voortgang.</b><br>"
            f"Dit is de <b style='color:{TEKST}'>snelle oefen-app</b>, gemaakt voor je "
            f"telefoon: woorden, rijtjes en stamtijden.<br>Wil je ontleden, leesteksten, "
            f"grammatica of iets opzoeken in de bijbeltekst, ga dan naar de "
            f"<a href='{adres}' target='_blank' style='color:{MERK};text-decoration:none'>"
            f"uitgebreide app</a>.</div>")


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
    # display:contents haalt de wikkeldiv weg die NiceGUI om deze html zet. Die div is
    # zelf 0px hoog — de balk erin hangt vast onderaan — maar telt wél mee als flex-item
    # van de pagina, en kreeg dus de tussenruimte van 16px mee. Daardoor was de pagina
    # net iets hoger dan het scherm en kon je hem een paar pixels wegschuiven.
    ui.html(f"<div class='onderbalk'>{vakken}</div>").style("display:contents")


def woordmaat(tekst, groot=58):
    """Tekengrootte die meebeweegt met de lengte. Een lang woord als ἐπιλαμβάνομαι brak
    op 58px af en kostte dan ineens een hele regel extra; korter wordt hij pas als het
    echt moet, want groot lezen is prettiger."""
    lengte = len(str(tekst or ""))
    if lengte <= 8:
        return groot
    if lengte <= 12:
        return round(groot * 0.76)
    return round(groot * 0.6)


def te_snel(sessie, seconden=0.35):
    """Staat de uitslag er nog geen 0,35 seconde, dan negeren we de tik.

    Zonder die pauze schiet een tweede tik — of een Enter die je nét te lang indrukt —
    meteen langs het antwoord heen, en zie je alleen een flits. De grendel `bezig` dekt
    dat niet: die duurt maar zolang het opslaan loopt."""
    return (time.monotonic() - getattr(sessie, "uitslag_op", 0.0)) < seconden


def _uitslag_staat(sessie):
    """Nu staat de uitslag op het scherm; vanaf hier telt de pauze van te_snel()."""
    sessie.uitslag_op = time.monotonic()


def toch_goed_knop(vak, handelen):
    """De knop 'Ik had het goed' onder een foute uitslag.

    Bedoeld voor de oefeningen waar je Grieks typt: daar mist er nogal eens één letter
    of een uitgang terwijl je de vorm wel wist, en dat kost je streak twee stappen. Hij
    staat in de uitslagkaart en niet in de antwoordbalk, want die balk moet elke beurt
    even hoog blijven. Geen waarschuwkleur en geen bevestiging: één tik, en weg is hij.
    """
    with vak:
        ui.button("Ik had het goed", on_click=handelen, color=None).props("flat no-caps").classes(
            "raakbaar").style(f"color:{ZACHT};border:1px solid {RAND};border-radius:8px;"
                              f"font-size:13px;width:100%;margin-top:10px")


def typbalk(hint):
    """De antwoordbalk voor de oefeningen waar je iets kunt typen: veld links, knop
    rechts. Geeft (invoer, knop) terug.

    Twee dingen liggen hier vast omdat ze anders bij elke beurt verspringen. De knop
    heeft een vaste breedte, zodat 'Nakijken' en 'Nieuwe ronde' hem niet opzij duwen.
    En hij blijft rechts staan, ook als er niets te typen valt: verberg je het veld
    met set_visibility (display:none), dan schuift de knop naar de linkerkant van het
    scherm — met je duim de lastigste hoek. Gebruik daarom toon_typveld().
    """
    with ui.element("div").classes("antwoordbalk"):
        with ui.row().classes("w-full gap-2 no-wrap items-center"):
            invoer = ui.input(placeholder=hint).props(
                "outlined dense dark autocomplete=off autocapitalize=none autocorrect=off spellcheck=false enterkeyhint=done").classes("flex-grow")
            knop = ui.button("Nakijken", color=None).props("unelevated no-caps").style(
                f"background:{MERK};color:{INKT};font-weight:700;height:40px;"
                f"width:132px;min-width:132px;font-size:14px")
    return invoer, knop


def toon_typveld(invoer, aan):
    """Het veld tonen of verbergen zónder de ruimte op te geven, zodat de knop ernaast
    niet verspringt. Onzichtbaar is het ook niet aan te tikken, dus het toetsenbord
    springt niet ongevraagd open."""
    invoer.style(f"visibility:{'visible' if aan else 'hidden'}")


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
        knop = ui.button("Beginnen", color=None).props("unelevated no-caps").classes("w-full").style(
            f"background:{MERK};color:{INKT};font-weight:700;height:46px")
        ui.html(APP_OP_MOBIEL)
        # Andersom verwijst de volledige app hierheen; zo weet je op elk inlogscherm
        # welke van de twee je voor je hebt.
        if STREAMLIT_URL:
            ui.html(volledige_app_blok())

    async def probeer():
        melding.text = ""
        knop.props("loading")
        try:
            g = await run.io_bound(gebruikers.inloggen, veld_naam.value, veld_code.value,
                                   OPSLAG_INTERVAL)
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


# ============================================================== taal
# Twee talen in één app. De knop staat op Vandaag, want daar begin je: je ziet in één
# oogopslag waar de app op staat, en het is één tik om te wisselen.
#
# Wat de knop wél en niet doet, expres. Het Hebreeuws heeft een eigen woordenlijst met
# eigen voortgang (hebr_stats), en die staat naast het Grieks — je verliest dus niets
# door te wisselen, en je kunt op één dag allebei oefenen. Maar stamtijden, actief
# beheersen, structuurwoorden en ontleden hébben geen Hebreeuwse gegevens: daar zijn geen
# rijtjes of ontleedcodes voor. In plaats van lege oefeningen te tonen zegt de app dat
# gewoon, en wijst hij naar de Griekse kant.
GRIEKS, HEBREEUWS = "grieks", "hebreeuws"


def taal(g):
    """De taal waar de app op staat. Zonder woordenlijst bestaat de keuze niet."""
    gekozen = (g.stats.get("ui_prefs") or {}).get("ng_taal", GRIEKS)
    return HEBREEUWS if (gekozen == HEBREEUWS and g.hebreeuws) else GRIEKS


def taalknop(g, na="/vandaag"):
    """Grieks of Hebreeuws, als twee knoppen naast elkaar. Alleen zichtbaar als de
    Hebreeuwse lijst er is; anders is er niets te kiezen en zou de knop alleen ruimte
    kosten."""
    if not g.hebreeuws:
        return

    async def wissel(waarde):
        if taal(g) == waarde:
            return
        g.stats.setdefault("ui_prefs", {})["ng_taal"] = waarde
        await run.io_bound(g.bewaar, True)
        ui.navigate.to(na)

    huidig = taal(g)
    with ui.row().classes("gap-0 no-wrap").style(
            f"border:1px solid {RAND};border-radius:9px;overflow:hidden"):
        for waarde, label in ((GRIEKS, "Grieks"), (HEBREEUWS, "עברית")):
            aan = waarde == huidig
            knop = ui.button(label, color=None,
                             on_click=lambda _=None, w=waarde: wissel(w)).props(
                "flat dense no-caps").style(
                f"min-width:64px;height:30px;font-size:13px;border-radius:0;"
                f"background:{MERK if aan else 'transparent'};"
                f"color:{INKT if aan else ZACHT};font-weight:{700 if aan else 400}")
            if waarde == HEBREEUWS:
                knop.classes("hebreeuws")


def heb_vandaag(g):
    """Hoeveel verschillende Hebreeuwse woorden je vandaag had. Zelfde maat als bij de
    Griekse woorden, zodat het dagdoel hetzelfde betekent."""
    vd = gebruikers.vandaag()
    return sum(1 for w in g.hebreeuws if w.get("laatst_geoefend") == vd)


def heb_samenvatting(g):
    """Kort overzicht van de Hebreeuwse woordenschat: geoefend, beheerst, totaal.
    'Beheerst' gebruikt dezelfde streakgrens als het Grieks, zodat de twee getallen
    naast elkaar hetzelfde zeggen."""
    geoefend = sum(1 for w in g.hebreeuws
                   if int(w.get("score_goed", 0)) or int(w.get("score_fout", 0)))
    beheerst = sum(1 for w in g.hebreeuws if int(w.get("streak", 0)) >= 16)
    return {"totaal": len(g.hebreeuws), "geoefend": geoefend, "beheerst": beheerst}


# ============================================================== vandaag
def klaargezet(g):
    """Wat er vandaag voor je klaarstaat, per onderdeel: naam, wat je krijgt, waar het
    staat, de dagdoel-sleutel en hoeveel je er vandaag al deed. De aantallen komen uit
    je eigen instellingen, zodat hier staat wat je straks écht voorgeschoteld krijgt."""
    def voorkeur(standaard, sleutel):
        return int((g.stats.get("ui_prefs") or {}).get(f"ng_{sleutel}", standaard[sleutel]))

    if taal(g) == HEBREEUWS:
        # Woordenschat en de rijtjes; de overige oefeningen zijn Grieks (zie heb_oefenhub).
        hp = heb_prefs(g)
        log = g.daglog()
        if hp["heb_keuze"] == "Leerpad (volgend blokje)":
            _nu = next((s for s in heb_levels(g)
                        if s["ontgrendeld"] and not s["voltooid"]), None)
            _uitleg = (f"blokje {_nu['index']} · {_nu['titel']} "
                       f"({_nu['klaar']}/{_nu['totaal']})" if _nu
                       else "alle blokjes af")
        else:
            _uitleg = f"{int(hp['heb_aantal'])} woorden · {str(hp['heb_keuze']).lower()}"
        klaar = [("Hebreeuwse woorden", _uitleg,
                  "/oefenen/hebreeuws", "hebreeuws", heb_vandaag(g))]
        if hebreeuws.laad_rijtjes():
            klaar.append(("Actief beheersen",
                          f"{int(heb_af_prefs(g)['heb_af_aantal'])} cellen uit de rijtjes",
                          "/oefenen/hebreeuws/actief", "hebreeuws",
                          int(log.get("hebreeuws", 0) or 0)))
        if hebreeuws.laad_verzen():
            klaar.append(("Voor- en achtervoegsels",
                          "wat er vóór en achter het woord geplakt zit",
                          "/oefenen/hebreeuws/affixen", "hebreeuws",
                          int(log.get("hebreeuws", 0) or 0)))
        return klaar

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
    ] + ([("Ontleden", "een vers uit het NT, woord voor woord",
           "/oefenen/ontleden", "verzen", int(log.get("verzen", 0) or 0))] if BIJBEL else [])


@ui.page("/vandaag")
def vandaagpagina():
    g = _bewaakt()
    if not g:
        return
    heb = taal(g) == HEBREEUWS
    sam = heb_samenvatting(g) if heb else g.samenvatting()
    dagen = g.stats.get("dag_stats") or {}
    # Het dagdoel dat je bij Voortgang instelt; 'woorden' telt verschillende woorden.
    doelen = g.dagdoel()
    doelsleutel = "hebreeuws" if heb else "woorden"
    doel = max(1, int(doelen.get(doelsleutel, 10) or 10))
    gedaan = heb_vandaag(g) if heb else g.woorden_vandaag()

    with ui.column().classes("inhoud w-full gap-3"):
        # De taalknop staat naast de titel: zo zie je meteen waar de app op staat, en
        # kost het één tik om te wisselen.
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Vandaag").style("font-size:26px;font-weight:700")
            taalknop(g)
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
            ui.label(f"{sam['geoefend']} van {sam['totaal']} woorden gehad · "
                     f"{sam['beheerst']} beheerst" if heb
                     else f"{sam['dagen']} oefendagen · {sam['beheerst']} woorden "
                          f"beheerst").style(f"color:{ZACHT};font-size:12.5px")

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
                        f"color:{TEKST if d == vandaag_d else ZACHT};font-size:12.5px")

        blok = volledige_app_blok(g)
        if blok:
            ui.html(blok)
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
    woord ophalen, terwijl gemaskeerde letters je alleen laten raden.

    Het ezelsbruggetje is een icoontje met hoogstens vijf woorden: meestal een
    Nederlands woord dat van dit Griekse woord komt (cardioloog bij καρδία), anders
    een kort beeld. Zo past de hele hint op één regel naast de vraag."""
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


# Elke grammaticale term zijn eigen kleur.
#
# De naamvallen zijn NIET vrij te kiezen: die staan zo in de Streamlit-app (_ONTLEED_KLEUR
# in overhoring_web.py) en zijn daar gekoppeld aan het college. Blijven ze hier gelijk, dan
# betekent dezelfde kleur in beide apps hetzelfde. Verander je ze daar, verander ze hier mee.
#
# De regel waaraan die reeks is opgebouwd geldt ook voor de rest: gelijke helderheid, en
# bewust weg van rood en groen (die betekenen in deze app al "fout" en "goed") en weg van
# het merkcyaan #33ccff (dat betekent "actief"). De tijden en wijzen zijn nergens aan
# gekoppeld; die mag je omgooien als het college er iets anders van maakt.
NAAMVAL_KLEUREN = {"nominativus": "#7FB3FF", "genitivus": "#E8B44A",
                   "dativus": "#B694FF", "accusativus": "#FF8FB1",
                   "vocativus": "#5ED3C0"}
GRAM_KLEUREN = {
    **NAAMVAL_KLEUREN,
    "nom": "#7FB3FF", "gen": "#E8B44A", "dat": "#B694FF", "acc": "#FF8FB1",
    "voc": "#5ED3C0",
    # tijden
    "praesens": "#E8EAED", "imperfectum": "#8FD3E8", "futurum": "#FFB067",
    "aoristus": "#FF9BC4", "perfectum": "#C4A6FF", "plusquamperfectum": "#9B86D9",
    # wijzen — indicativus blijft rustig, dat is de gewone wijs
    "indicativus": "#B8C4CF", "coniunctivus": "#E8B44A", "optativus": "#5ED3C0",
    "imperativus": "#FFB067", "infinitivus": "#7FB3FF", "participium": "#C4A6FF",
}
_GRAM_ZOEK = re.compile("(?<![A-Za-z])(" + "|".join(
    sorted(GRAM_KLEUREN, key=len, reverse=True)) + ")(?![A-Za-z])",
                        re.IGNORECASE)


def gram_kleur(term):
    """De kleur van één term, of None als we hem niet kennen."""
    return GRAM_KLEUREN.get(str(term or "").strip().lower())


def kleur_gram(tekst):
    """Elke grammaticale term in de tekst zijn eigen kleur geven."""
    return _GRAM_ZOEK.sub(
        lambda m: f"<span style='color:{GRAM_KLEUREN[m.group(0).lower()]}'>{m.group(0)}</span>",
        str(tekst or ""))


def _goedfout(goed, fout):
    """Goed en fout als één klein blokje: het groene getal, een schuine streep, het rode.

    Als vakje met het label 'goed/fout' nam dit te veel breedte en werd het afgekapt; als
    twee gekleurde getallen lees je in één oogopslag hoe dit woord ervoor staat, zonder
    label. Nul fouten blijft grijs — dan is er niets aan de hand en hoeft het geen
    aandacht te trekken."""
    g, f = int(goed or 0), int(fout or 0)
    if not (g or f):
        return ""
    return (f"<span style='color:{GOED}'>{g}</span>"
            f"<span style='color:{ZACHT}'>/</span>"
            f"<span style='color:{FOUT if f else ZACHT}'>{f}</span>")


def _statusrij(delen):
    """Eén regel status onder de antwoordopties: waarde en label achter elkaar, met
    scheidingspunten ertussen.

    Hiervoor stonden hier vijf vakjes naast elkaar. Op 360 punten breedte paste dat
    niet: 'In training' werd 'Trai…', 'Nieuw' werd 'Nie…' en de datum '18 a…' — juist
    de fase, het enige dat je tijdens het oefenen wilt weten, viel weg. Goed/fout en
    'laatst geoefend' staan op Voortgang; naast het woord dat je leert horen ze niet.
    Past een label niet voluit, dan vervalt het liever dan dat het wordt afgekapt."""
    inhoud = f"<span style='color:{ZACHT}'> · </span>".join(
        f"<span style='color:{kleur};font-weight:600'>{waarde}</span>"
        f"<span style='color:{ZACHT}'> {label}</span>"
        for waarde, label, kleur in delen if str(waarde) != "")
    return (f"<div style='width:100%;text-align:center;font-size:{BASIS};"
            f"line-height:1.5;white-space:normal'>{inhoud}</div>")


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

    delen.append(f"<div style='color:{ZACHT};font-size:13px'>betekenis</div>"
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
            f"<div style='color:{ZACHT};font-size:13px'>{tv['ref']}</div>")
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
    regels.append(f"<div style='color:{ZACHT};font-size:13px;margin-top:8px'>"
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

    def __init__(self, g, alleen=None):
        """`alleen` is een lijst Griekse woorden: dan wordt dat de hele ronde. Zo werkt
        'Fouten herhalen' op de eindkaart — je oefent precies wat je net miste, met
        dezelfde vraagvorm-instelling als de ronde ervoor."""
        p = prefs(g)
        self.poule = bouw_poule(g, p["keuze"], p["lessen"], p.get("level", 0)) or g.woorden
        self.nieuw_over = 0
        if alleen:
            binnen = {str(x) for x in alleen}
            mis = [w for w in g.woorden if w.get("grieks") in binnen]
            if mis:
                self.wachtrij = self._kaarten(mis, p["vorm"])
                self.begin_aantal = len(self.wachtrij)
                self.prefs = p
                self._leegmaken()
                return
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
        self._leegmaken()

    def _leegmaken(self):
        """Alle tellers op nul. Staat apart omdat een herhaalronde het bouwen van de
        wachtrij overslaat maar wél schoon moet beginnen."""
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


def heb_oefenhub(g):
    """De oefenlijst als de app op Hebreeuws staat.

    Eerlijk kort: er is één oefening. Stamtijden, actief beheersen, structuurwoorden en
    ontleden vragen om rijtjes en ontleedcodes, en die zijn er voor het Hebreeuws niet.
    Een lege oefening tonen zou erger zijn dan hem niet tonen — dan klik je erheen en
    staat er niets."""
    sam = heb_samenvatting(g)
    with ui.column().classes("inhoud w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Oefenen").style("font-size:26px;font-weight:700")
            taalknop(g, "/oefenen")
        ui.label("Woorden kennen").style(f"color:{ZACHT};font-size:13px;margin-top:6px")
        with ui.element("div").classes("kaart w-full").on(
                "click", lambda: ui.navigate.to("/oefenen/hebreeuws")):
            with ui.row().classes("w-full items-center justify-between no-wrap"):
                ui.label("Hebreeuwse woorden").style(
                    f"color:{TEKST};font-size:16px;font-weight:600")
                with ui.row().classes("items-center gap-3 no-wrap"):
                    ui.label(f"{round(100 * sam['geoefend'] / max(1, sam['totaal']))}%").style(
                        f"color:{MERK};font-size:14px")
                    ui.label("›").style(f"color:{ZACHT};font-size:20px")
        with ui.element("div").classes("kaart w-full"):
            ui.label(f"{sam['totaal']} woorden uit Hebreeuws 1 en 2, met de betekenis, "
                     f"hoe het klinkt, hoe vaak het in de Tenach staat en waar je het "
                     f"voor het eerst tegenkomt.").style(
                f"color:{ZACHT};font-size:13px;line-height:1.6")
        rijtjes = hebreeuws.laad_rijtjes()
        if rijtjes:
            aantal = sum(len(paradigmas) for cats in rijtjes.values()
                         for paradigmas in cats.values())
            cellen = heb_af_cellen(g)
            gehad = sum(1 for c in cellen if c["goed"] or c["fout"])
            ui.label("Vormen beheersen").style(
                f"color:{ZACHT};font-size:13px;margin-top:6px")
            with ui.element("div").classes("kaart w-full").on(
                    "click", lambda: ui.navigate.to("/oefenen/hebreeuws/actief")):
                with ui.row().classes("w-full items-center justify-between no-wrap"):
                    ui.label("Actief beheersen").style(
                        f"color:{TEKST};font-size:16px;font-weight:600")
                    with ui.row().classes("items-center gap-3 no-wrap"):
                        ui.label(f"{round(100 * gehad / max(1, len(cellen)))}%").style(
                            f"color:{MERK};font-size:14px")
                        ui.label("›").style(f"color:{ZACHT};font-size:20px")
            with ui.element("div").classes("kaart w-full").on(
                    "click", lambda: ui.navigate.to("/oefenen/hebreeuws/affixen")):
                with ui.row().classes("w-full items-center justify-between no-wrap"):
                    with ui.column().classes("gap-0").style("min-width:0"):
                        ui.label("Voor- en achtervoegsels").style(
                            f"color:{TEKST};font-size:16px;font-weight:600")
                        ui.label("bijna de helft van alle vormen draagt er een").style(
                            f"color:{ZACHT};font-size:12.5px")
                    ui.label("›").style(f"color:{ZACHT};font-size:20px")
            with ui.element("div").classes("kaart w-full"):
                ui.label(f"{aantal} rijtjes met {len(cellen)} cellen, afgeleid uit de "
                         f"bijbeltekst zelf: elke vorm die je hier oefent staat écht "
                         f"ergens, en je ziet hoe vaak.").style(
                    f"color:{ZACHT};font-size:13px;line-height:1.6")
        ui.label("Alleen in het Grieks").style(f"color:{ZACHT};font-size:13px;margin-top:10px")
        with ui.element("div").classes("kaart w-full"):
            ui.label("Stamtijden · Structuurwoorden · Ontleden").style(
                f"color:{ZACHT};font-size:13px;line-height:1.6")
            ui.label("Die oefeningen werken op stamtijden en ontleedcodes; voor het "
                     "Hebreeuws zijn die er nog niet.").style(
                f"color:{ZACHT};font-size:13px;margin-top:4px")
    onderbalk("Oefenen")


def _klank_pct(g):
    """Hoeveel klanksoorten je vast hebt: streak 5 of hoger, van de zeven."""
    stats = g.stats.get(KLANK_SLEUTEL) or {}
    soorten = list(motor._SAMENSMELT_KLASSEN)
    vast = sum(1 for s in soorten
               if int((stats.get(s) or {}).get("streak", 0) or 0) >= 5)
    return f"{round(100 * vast / max(1, len(soorten)))}%"


def _contr_pct(g):
    """Hoeveel van de drie soorten contracties je vast hebt. Zelfde grens als de
    uitgebreide app gebruikt voor 'beheerst'."""
    stats = g.stats.get("gram_stats") or {}
    vast = sum(1 for s in CONTR_SOORTEN
               if int((stats.get(f"contr::{s}") or {}).get("streak", 0) or 0) >= 8)
    return f"{round(100 * vast / len(CONTR_SOORTEN))}%"


@ui.page("/oefenen")
def oefenhub():
    """De lijst met onderdelen, gegroepeerd naar wat je ermee traint (designreview 1d)."""
    g = _bewaakt()
    if not g:
        return
    if taal(g) == HEBREEUWS:
        heb_oefenhub(g)
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
        # Klankwetten en contracties horen bij elkaar: allebei een regel herkennen en dan
        # zelf toepassen. De klankwetten hebben de NT-tekst nodig -- die vormen komen uit
        # echte verzen -- en vervallen dus als die er niet is.
        ("Regels herkennen",
         ([("Klankwetten", _klank_pct(g), "/oefenen/klankwetten")] if BIJBEL else [])
         + [("Contracties", _contr_pct(g), "/oefenen/contracties")]),
    ]
    # Zonder de NT-tekst vervalt Ontleden en de klankwetten; die staan dan bij wat in de
    # volledige app zit.
    nog_niet = ["Nederlands → Grieks"] + ([] if BIJBEL else ["Ontleden",
                                                                 "Klankwetten"])

    with ui.column().classes("inhoud w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Oefenen").style("font-size:26px;font-weight:700")
            taalknop(g, "/oefenen")
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
                f"color:{ZACHT};font-size:13px;margin-top:4px")
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
            f"color:{ZACHT};font-size:13px").bind_visibility_from(
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
                f"color:{ZACHT};font-size:13px").bind_visibility_from(
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
            f"color:{ZACHT};font-size:13px")

        # --- sessie opbouw: de app weegt, jij zet een vast aantal, of jij vult per fase ---
        kies_stijl = ui.select(OPBOUW_STIJLEN, value=p["opbouw_stijl"],
                               label="Sessie opbouw").props("outlined dark").classes("w-full")
        ui.label("Automatisch weegt hoe zwaar je woorden nu zijn: staan er veel wankele "
                 "woorden klaar, dan wordt de ronde korter.").style(
            f"color:{ZACHT};font-size:13px").bind_visibility_from(
            kies_stijl, "value", lambda v: v == MIX)
        kies_aantal = ui.number("Kaarten per ronde", value=int(p["aantal"]),
                                min=4, max=40, step=1).props("outlined dark").classes("w-full")
        kies_aantal.bind_visibility_from(kies_stijl, "value", lambda v: v == VAST)
        eigen_vak = ui.column().classes("w-full gap-2")
        eigen_vak.bind_visibility_from(kies_stijl, "value", lambda v: v == ZELF)
        fase_velden = {}
        with eigen_vak:
            ui.label("Hoeveel woorden wil je per fase?").style(
                f"color:{ZACHT};font-size:13px")
            beschikbaar = ui.label().style(f"color:{ZACHT};font-size:13px")
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
                 "eigen verwarparen.").style(f"color:{ZACHT};font-size:13px")
        kies_audio = ui.switch("Uitspraakknop tonen", value=bool(p["audio"]))
        kies_opbouw = ui.switch("Woordopbouw tonen", value=bool(p["opbouw"]))
        # Zonder de NT-tekst valt er geen verbogen vorm op te halen, dus dan zou deze
        # schakelaar niets doen. Hij blijft wel bewaard, voor als je de tekst er ooit
        # bij zet of in de uitgebreide app oefent.
        kies_mv = ui.switch("Beheerste woorden als vorm uit de Bijbel",
                            value=bool(p.get("mastery_vormen", True)))
        _mv_uitleg = ui.label(
            f"Bij streak {MASTERY_STREAK}+ krijg je een echte verbogen vorm uit "
            f"het NT in plaats van de woordenboekvorm.").style(
            f"color:{ZACHT};font-size:13px")
        if not BIJBEL:
            kies_mv.set_visibility(False)
            _mv_uitleg.set_visibility(False)
        ui.label("Je keuzes worden bewaard bij je voortgang.").style(
            f"color:{ZACHT};font-size:13px")

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
            ui.button("Annuleren", on_click=instellingen.close, color=None).props("flat no-caps").style(
                f"color:{ZACHT}")
            ui.button("Toepassen", on_click=bewaar_instellingen, color=None).props("unelevated no-caps").style(
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
    # 'Fouten herhalen' op de eindkaart zet de gemiste woorden hier klaar; de ronde
    # daarna is weer een gewone.
    sessie = Sessie(g, app.storage.user.pop("herhaal", None))
    instellingen = woord_instellingen(g)

    # gap-2 en niet gap-3: met elf tussenruimtes scheelt dat veertig pixels, en dat is
    # net het verschil tussen wel en niet scrollen tijdens een meerkeuzevraag.
    # 'vast': de kolom is precies zo hoog als het scherm min de balken, zodat het
    # vraagvak eronder met flex:1 exact de overgebleven ruimte krijgt.
    with ui.column().classes("inhoud metbalk vast w-full gap-2") as kolom:
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label(sessie.prefs["keuze"]).style(f"color:{ZACHT};font-size:13px")
            with ui.row().classes("items-center gap-2 no-wrap"):
                # Hier stond een regel van twee tekstregels: "🌱 Nog 2 nieuwe woorden in
                # dit level voor een volgende ronde." Die kostte meer ruimte dan hij waard
                # was. Nu één blaadje met hoeveel er nog wachten; omdat er telkens een
                # blaadje bij komt zodra een nieuw woord langskomt, wijst het zichzelf uit.
                if sessie.nieuw_over:
                    ui.html(f"<span style='color:{GOED};font-size:13px;"
                            f"white-space:nowrap'>🌱 {sessie.nieuw_over}</span>")
                teller = ui.label().style(f"color:{ZACHT};font-size:13px")
                ui.button("⚙", on_click=instellingen.open, color=None).props("flat dense no-caps").classes(
                    "raakbaar").style(
                    f"color:{ZACHT};font-size:17px;min-width:32px")
        streepjes = ui.row().classes("w-full gap-1 no-wrap")
        _xp = motor.bereken_xp(g.woorden)
        _niv = motor.niveau_van_xp(_xp)
        _klaar = sum(1 for _s in motor.leerpad_status(
            motor.bouw_leerpad_levels(g.woorden)) if _s.get("voltooid"))
        # gap en wrap zijn nodig: op een smal scherm raakten de twee helften elkaar en
        # las je 'Psalmen45 levels af'. Elke helft blijft heel; ze wippen onder elkaar
        # zodra ze samen niet meer passen.
        ui.html(
            f"<div style='display:flex;justify-content:space-between;flex-wrap:wrap;"
            f"gap:2px 12px;font-size:13px;color:{ZACHT};padding-top:2px'>"
            f"<span style='white-space:nowrap'>Niveau {_niv['niveau']} · "
            f"<span style='color:{MERK}'>{_niv['titel']}</span></span>"
            f"<span style='white-space:nowrap'>{_klaar} levels af · nog "
            f"{_niv['xp_voor_volgend'] - _niv['xp_in_niveau']} XP</span></div>")

        # Eén vast toneel voor de vraag, met de feedback eroverheen in plaats van
        # eronder. Zo groeit en krimpt de pagina niet bij elk antwoord en blijven de
        # knoppen op hun plek staan — dat scheelt zoeken tijdens het oefenen.
        with ui.element("div").classes("vraagvak w-full") as vraagvak:
            with ui.column().classes("w-full gap-1 items-stretch") as vraagvlak:
                woord = ui.label().classes("grieks w-full text-center").style(
                    f"font-size:58px;line-height:1.1;color:{TEKST};padding:8px 0 2px")
                lemma = ui.label().classes("w-full text-center").style(
                    f"color:{ZACHT};font-size:14px")
                vraagsoort = ui.label().classes("w-full text-center").style(
                    f"color:{ZACHT};font-size:{BASIS}")
                opties = ui.column().classes("keuzevak w-full gap-2").style(
                    "padding-top:8px")
                # Bij een eerste misser blijft de vraag staan — je mag het nog eens
                # proberen — dus die aanwijzing hoort niet in de laag die de vraag
                # bedekt. Hij komt ná de antwoordknoppen: die blijven dan staan waar ze
                # stonden, en wat er eventueel niet meer bij past is de toelichting en
                # niet iets waarop je moet tikken.
                naastregel = ui.column().classes("w-full gap-1 items-center").style(
                    "padding-top:4px")
            terugkoppeling = ui.column().classes(
                "overlay w-full gap-1 items-center justify-center")
        # De statusregel staat búiten het vraagvak. Daarbinnen viel hij onder de vouw
        # zodra het toetsenbord openstond: je moest scrollen om je streak te zien. Hier
        # staat hij altijd in beeld, laag bij je duim, en in alle vier de modules op
        # dezelfde plek.
        statusbalk = ui.row().classes("w-full gap-2 no-wrap justify-center").style(
            "padding-top:2px")
        hulp = ui.row().classes("w-full gap-2 no-wrap")
        opslagmelding = ui.label().style(
            f"color:{ZACHT};font-size:12.5px;min-height:16px;text-align:center;width:100%")

    balk = ui.element("div").classes("antwoordbalk")
    with balk:
        with ui.row().classes("w-full gap-2 no-wrap items-center"):
            # Het veld blijft altijd staan, ook na het nakijken. Verdween het, dan
            # schoof de knop naar links en moest je elke beurt ergens anders tikken.
            invoer = ui.input(placeholder="vertaling").props(
                "outlined dense dark autocomplete=off autocapitalize=none autocorrect=off spellcheck=false enterkeyhint=done").classes("flex-grow")
            # Vaste breedte: anders schuift de knop bij elk ander opschrift een stukje
            # opzij en tik je elke beurt op een andere plek.
            knop = ui.button("Nakijken", color=None).props("unelevated no-caps").style(
                f"background:{MERK};color:{INKT};font-weight:700;height:40px;"
                f"width:132px;min-width:132px;font-size:14px")
        weetniet = ui.button("Ik weet het niet — toon het antwoord", color=None).props("flat dense no-caps").style(
            f"color:{ZACHT};width:100%;font-size:13px;margin-top:2px")
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
        """Ging dit woord een nieuwe fase in? Geeft de regel terug, of "".

        Dit stond eerst in een melding bovenaan het scherm. Die kwam over de kopregel te
        liggen — je zag "Leerpad (le…" en van "3/14" nog de helft — terwijl je duim en je
        blik onderaan zitten. Nu hoort hij in de uitslagkaart, waar je op dat moment toch
        al kijkt. ui.notify blijft voor techniek: geen verbinding, opslaan mislukt."""
        for drempel, tekst in ((30, f"🏆 Mastery — {label} zit nu echt vast."),
                               (16, f"🎉 {label} is nu Beheerst."),
                               (1, f"🌱 {label} staat nu In training.")):
            if oud < drempel <= nieuw:
                return (f"<div style='color:{GOED};font-size:{BASIS};text-align:center;"
                        f"padding-top:6px'>{tekst}</div>")
        return ""

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

    def open_uitslag():
        """Ruimte maken voor de uitslag: die komt óver de vraag te liggen, niet eronder.
        De vraag zelf gaat weg, zodat de hoogte niet verspringt."""
        terugkoppeling.clear()
        vraagvlak.set_visibility(False)
        return terugkoppeling

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

    def zet_balk(knoptekst, typen=False, weet_niet=False):
        """De antwoordbalk in één keer instellen. Alles blijft altijd staan; wat niet
        van toepassing is wordt onzichtbaar maar houdt zijn ruimte. Zo staat de knop
        elke beurt op precies dezelfde plek en hoef je niet te zoeken."""
        invoer.style(f"visibility:{'visible' if typen else 'hidden'}")
        weetniet.style(f"visibility:{'visible' if weet_niet else 'hidden'}")
        knop.text = knoptekst

    def kaart_afgerond():
        """Het antwoord staat vast: opties weg, alleen nog door naar de volgende."""
        opties.clear()
        sessie.beoordeeld = True
        zet_balk("Volgende")
        ververs_kop(sessie.woord)
        _uitslag_staat(sessie)

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
            fasemelding = vier_fase(oud, int(k.get("streak", 0) or 0), grieks)
            with open_uitslag():
                ui.html(_feedbackblok(k, True, sessie, g.woorden))
                if extra:
                    ui.html(extra)
                if fasemelding:
                    ui.html(fasemelding)
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
            with open_uitslag():
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

        # Bijna: het antwoord blijft verborgen en de vraag blijft staan, want je mag het
        # nog eens proberen. De aanwijzing komt daarom náást de vraag, niet eroverheen.
        ververs_kop(k)
        naastregel.clear()
        # Zo compact mogelijk: dit komt bovenop een vraag die blijft staan, en scrollen
        # tijdens het oefenen is precies wat we niet willen. Alles op één regel per
        # gedachte, geen kader, geen herhaling van wat er al staat.
        delen = [f"<b style='color:{MERK}'>Bijna</b> — {_hint(k)}"]
        # Alleen het meest specifieke: welk woord je antwoord wél was. De bredere
        # 'lijkt op'-lijst bewaren we voor de uitslag, die over de vraag heen mag.
        if bron is not None and bron.get("grieks"):
            delen.append(f"“{antwoord}” hoort bij "
                         f"<span class='grieks'>{bron['grieks']}</span>")
        with naastregel:
            ui.html(f"<div style='color:{ZACHT};font-size:14px;line-height:1.45;"
                    f"text-align:center;padding:2px 4px'>"
                    + "<br>".join(delen) + "</div>")
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
        with open_uitslag():
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
        with statusbalk:
            ui.html(_statusrij([
                (fase, "", MERK if fase != "Nieuw" else ZACHT),
                (int(k.get("streak", 0) or 0), "streak", TEKST),
                (_goedfout(k.get("score_goed"), k.get("score_fout")), "", TEKST),
                # Alleen dag en maand: het jaar zegt niets en de volle datum paste niet.
                (_kort_datum(k.get("laatst_geoefend"))
                 if k.get("laatst_geoefend") else "", "", ZACHT),
                (len(sessie.wachtrij), "te gaan", ZACHT),
            ]))

    def toon_kaart():
        for vak in (opties, terugkoppeling, hulp, naastregel):
            vak.clear()
        k, vorm = sessie.woord, sessie.vorm
        # De feedback lag over de vraag heen; nu de vraag weer zichtbaar maken.
        vraagvlak.set_visibility(True)
        vraagvak.classes(remove="vrij")
        kolom.classes(add="vast")

        teken_status(k)
        if k is None:
            statusbalk.clear()
            woord.text = "✓"
            lemma.text = f"Klaar — {sessie.goed} goed, {sessie.fout} fout."
            vraagsoort.text = ""
            teller.text = ""
            zet_balk("Nieuwe ronde")
            teken_streepjes()
            # De samenvatting mag zo lang zijn als hij is: het vak stopt met krimpen en de
            # kolom laat zijn vaste hoogte los, zodat de pagina hier wél kan scrollen.
            vraagvak.classes(add="vrij")
            kolom.classes(remove="vast")
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
        woord.style(f"font-size:{woordmaat(woord.text)}px")
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
                ui.button(label, on_click=lambda l=label, w=k: toon_hulp(l, w),
                          color=None).props("flat dense no-caps").classes("raakbaar").style(
                    f"flex:1;color:{ZACHT};border:1px solid {RAND};border-radius:8px;"
                    f"font-size:12.5px")

        if vorm == "1":                                    # flashcard: eerst zien
            vraagsoort.text = "Nieuw woord — bekijk het even"
            with opties:
                ui.html(_leerkaart(k, g.woorden))
            zet_balk("Bekeken")
            return

        if vorm == "overtik":                              # verankeren na een misser
            vraagsoort.text = "Typ het antwoord over — dit telt niet voor je streak"
            with opties:
                ui.html(f"<div style='text-align:center;color:{TEKST};font-size:17px;"
                        f"line-height:1.5'>{k.get('nederlands', '')}</div>")
            invoer.value = ""
            zet_balk("Bevestig", typen=True)
            invoer.run_method("focus")
            return

        if vorm in ("2", "3_mc"):                          # meerkeuze
            vraagsoort.text = "Welke betekenis hoort hierbij?"
            # Geen typveld, maar de knop blijft staan: die doet hier 'ik weet het niet'.
            zet_balk("Weet ik niet")
            keuzes, bron = afleiders(k, g.woorden)
            keuzes = keuzes + [k.get("nederlands", "")]
            random.shuffle(keuzes)
            with opties:
                for keuze in keuzes:
                    ui.html(f"<button class='keuze'>{keuze}</button>").on(
                        "click", lambda _=None, c=keuze, b=bron: kies(k, c, b))
            return

        # Bij typen geen vraagregel: het invoerveld eronder zegt het al, en met het
        # toetsenbord open is elke regel er een te veel.
        vraagsoort.text = ""                              # typen
        invoer.value = ""
        zet_balk("Nakijken", typen=True, weet_niet=True)
        invoer.run_method("focus")

    # ---------------- de eindsamenvatting ----------------
    def toon_samenvatting():
        """Wat ging goed, wat fout, en welke verwarring klopte écht. Dat laatste bevestig
        je zelf: meerdere woorden kunnen dezelfde Nederlandse betekenis hebben, dus
        automatisch toevoegen zou de lijst vervuilen."""
        goed_alleen = {gr: nl for gr, nl in sessie.gelukt.items() if gr not in sessie.mislukt}
        # De knop staat bóven de lijsten. Eronder stond hij in het scrollgebied buiten
        # beeld: je zag alleen "Nieuwe ronde" in de balk, precies op het moment dat je
        # net twee fouten had gemaakt en die wilde herhalen.
        if sessie.mislukt:
            def herhaal_fouten():
                app.storage.user["herhaal"] = list(sessie.mislukt)
                ui.navigate.to("/oefenen/woorden")

            ui.button(f"Fouten herhalen ({len(sessie.mislukt)})",
                      on_click=herhaal_fouten, color=None).props(
                "unelevated no-caps").classes("raakbaar").style(
                f"background:{MERK};color:{INKT};font-weight:700;width:100%;height:48px;"
                f"font-size:15px;margin-bottom:10px")
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

            ui.button("Toevoegen aan mijn verwarwoorden", on_click=bevestig, color=None).props(
                "unelevated no-caps").style(f"background:{MERK};color:{INKT};font-weight:700;"
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
                if te_snel(sessie):
                    return
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
                    with naastregel:
                        ui.html(f"<div style='color:{MERK};font-size:12.5px;"
                                f"text-align:center'>Genoteerd — dit woord komt straks "
                                f"nog terug.</div>")
                else:
                    naastregel.clear()
                    with naastregel:
                        ui.html(f"<div style='color:{FOUT};font-size:13px;"
                                f"text-align:center'>Nog niet exact overgetypt — kijk "
                                f"goed naar de betekenis hierboven.</div>")
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
                ui.button("⚙", on_click=instellingen.open, color=None).props("flat dense no-caps").classes(
                    "raakbaar").style(
                    f"color:{ZACHT};font-size:17px;min-width:32px")
        woorden = ui.row().classes("w-full no-wrap items-start").style("padding:12px 0 2px")
        vraagsoort = ui.label().classes("w-full text-center").style(
            f"color:{ZACHT};font-size:13px")
        velden = ui.column().classes("w-full gap-2").style("padding-top:8px")
        terugkoppeling = ui.column().classes("w-full gap-1 items-center").style(
            "min-height:40px;padding-top:6px")
        opslagmelding = ui.label().style(f"color:{ZACHT};font-size:12.5px;min-height:16px")

    balk = ui.element("div").classes("antwoordbalk")
    with balk:
        knop = ui.button("Nakijken", color=None).props("unelevated no-caps").style(
            f"background:{MERK};color:{INKT};font-weight:700;height:40px;width:100%")
        stopknop = ui.button("Stop deze ronde", color=None).props("flat dense no-caps").style(
            f"color:{ZACHT};width:100%;font-size:13px;margin-top:2px")
    onderbalk("Oefenen")

    invoervelden = {}

    def open_uitslag():
        """Ruimte maken voor de uitslag: die komt óver de vraag te liggen, niet eronder.
        De vraag zelf gaat weg, zodat de hoogte niet verspringt."""
        terugkoppeling.clear()
        vraagvlak.set_visibility(False)
        return terugkoppeling

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

                    ui.button("Doe dan een gewone ronde", on_click=naar_kaarten, color=None).props(
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
                        "outlined dense dark autocomplete=off autocapitalize=none autocorrect=off spellcheck=false enterkeyhint=done").classes("w-full").on(
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
                    "outlined dense dark autocomplete=off autocapitalize=none autocorrect=off spellcheck=false enterkeyhint=done").classes("w-full").on(
                    "keydown.enter", nakijken)
                # Pas na een misser hulp erbij: anders geef je het antwoord te snel weg.
                if sessie.fout >= 1:
                    tip = _hint(w)
                    if tip:
                        ui.label(f"💡 {tip}").style(f"color:{ZACHT};font-size:13px")
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
        ui.button("Sluiten", on_click=venster.close, color=None).props("flat no-caps").style(
            f"color:{MERK};margin-top:10px;width:100%")
    return venster


def spiekknop(venster):
    """Het toetsenbord-knopje in de kop van een oefenpagina."""
    return ui.button("⌨", on_click=venster.open, color=None).props("flat dense no-caps").classes(
        "raakbaar").style(
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
        # De selectie bepaalt wélke vormen je krijgt (zwakste eerst, meest voorkomend,
        # het rijtje van dit werkwoord); de volgorde waarin ze langskomen is daarna
        # willekeurig. Anders liep je het rijtje in vaste volgorde af en wist je de
        # volgende tijd voordat je gekeken had — precies wat deze oefening moet trainen.
        random.shuffle(self.vragen)
        self.i = 0
        self.goed = 0
        self.fout = 0
        self.beoordeeld = False
        self.tijd_keuze = None
        self.vraag_praesens = True
        self.bezig = False
        self.gezien = set()        # vormen waarvan je het antwoord al liet zien

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
            f"color:{ZACHT};font-size:13px")
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
        _telling = ui.label().style(f"color:{ZACHT};font-size:13px")
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
            f"color:{ZACHT};font-size:13px")
        kies_kleur = ui.switch("Uitgangen kleuren",
                               value=bool(sessie.prefs.get("stam_kleur", True)))
        ui.label("Toont in het antwoord welk deel de stam is en welk deel de uitgang.").style(
            f"color:{ZACHT};font-size:13px")

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
            ui.button("Annuleren", on_click=instellingen.close, color=None).props("flat no-caps").style(
                f"color:{ZACHT}")
            ui.button("Toepassen", on_click=bewaar_inst, color=None).props("unelevated no-caps").style(
                f"background:{MERK};color:{INKT};font-weight:700")

    with ui.column().classes("inhoud metbalk w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label(f"Stamtijden · {sessie.prefs['stam_keuze']}").style(
                f"color:{ZACHT};font-size:13px")
            with ui.row().classes("items-center gap-2 no-wrap"):
                teller = ui.label().style(f"color:{ZACHT};font-size:13px")
                spiekknop(spiek)
                ui.button("⚙", on_click=instellingen.open, color=None).props("flat dense no-caps").classes(
                    "raakbaar").style(
                    f"color:{ZACHT};font-size:17px;min-width:32px")
        streepjes = ui.row().classes("w-full gap-1 no-wrap")
        vormlabel = ui.label().classes("grieks w-full text-center").style(
            f"font-size:52px;line-height:1.15;color:{TEKST};padding:16px 0 2px")
        vraagsoort = ui.label().classes("w-full text-center").style(
            f"color:{ZACHT};font-size:13px")
        tijdknoppen = ui.column().classes("keuzevak w-full gap-2").style("padding-top:8px")
        statusbalk = ui.row().classes("w-full").style("padding-top:6px")
        terugkoppeling = ui.column().classes("w-full items-center justify-center").style(
            "min-height:64px;padding-top:8px")
        hulp = ui.row().classes("w-full gap-2 no-wrap")
        opslagmelding = ui.label().style(f"color:{ZACHT};font-size:12.5px;min-height:16px")

    invoer, knop = typbalk("van welk werkwoord? (x = χ, u = υ, h = η)")
    onderbalk("Oefenen")

    def teken():
        streepjes.clear()
        with streepjes:
            for n in range(len(sessie.vragen)):
                kleur = MERK if n < sessie.i else (TEKST if n == sessie.i else RAND)
                ui.element("div").style(f"flex:1;height:4px;border-radius:2px;background:{kleur}")

    def toon_hulp(soort, v):
        """Hint en Opbouw, net als bij de woordenschat — maar zo dat ze de vraag niet
        beantwoorden.

        De Hint gaat over het wérkwoord, niet over de tijd: de betekenis en de klasse
        helpen je bij 'van welk werkwoord?' zonder te verraden welke tijd dit is. De
        Opbouw laat zien waar de stam ophoudt en de uitgang begint; dat is precies wat je
        moet leren zien, en het is nog steeds aan jou om te benoemen wat die uitgang
        betekent."""
        verb = v.get("verb") or {}
        morf = verb.get("morfologie") or {}
        if soort == "Hint":
            delen = [d for d in (verb.get("betekenis", ""),
                                 f"klasse {morf['klasse']}" if morf.get("klasse") else "",
                                 "onregelmatig — uit je hoofd leren"
                                 if morf.get("memoriseren_vereist") else "") if d]
            tekst = " · ".join(delen) or "Geen aanwijzing bij dit werkwoord."
        else:
            tekst = ""
            try:
                regels = motor.deconstrueer_stamtijd_live(
                    v["vorm"], v["tijd"], v["praesens"])
                if (isinstance(regels, (tuple, list)) and len(regels) == 2
                        and all(isinstance(x, str) for x in regels)):
                    stam, uit = regels
                    tekst = (f"<span class='grieks' style='color:{TEKST}'>{stam}</span>"
                             f"<span class='grieks' style='color:{MERK};font-weight:700'>"
                             f"{uit}</span>")
            except Exception:                                    # noqa: BLE001
                pass
            tekst = tekst or "Deze vorm valt niet in stam en uitgang te splitsen."
        ui.notify(tekst, position="top", color="dark", multi_line=True,
                  classes="text-body2", html=True).style("max-width:88vw")

    def teken_hulp(v):
        hulp.clear()
        if v is None:
            return
        with hulp:
            for label in ("Hint", "Opbouw"):
                ui.button(label, on_click=lambda l=label, vv=v: toon_hulp(l, vv),
                          color=None).props("flat dense no-caps").classes(
                    "raakbaar").style(
                    f"flex:1;color:{ZACHT};border:1px solid {RAND};border-radius:8px;"
                    f"font-size:12.5px")

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
                        # De kleur van de tijd zit in de tekst, niet in het vlak: zo
                        # blijft de gekozen knop herkenbaar aan zijn rand én blijft de
                        # tijd herkenbaar aan zijn kleur.
                        ui.html(f"<button class='keuze' style='background:{achter};"
                                f"border-color:{rand};font-size:14px;text-align:center;"
                                f"padding:11px 6px'>{kleur_gram(TIJD_KORT[t])}"
                                f"</button>").on(
                            "click", lambda _=None, tt=t: kies_tijd(tt)).style("flex:1")

    async def kies_tijd(t):
        if sessie.beoordeeld or sessie.bezig:
            return
        sessie.tijd_keuze = t
        teken_tijden()
        if sessie.vraag_praesens:
            # Het antwoord is nog niet af — er hoort ook een werkwoord bij. Alvast naar
            # het typveld, anders moet je daar nog een keer op tikken.
            invoer.run_method("focus")
        else:
            # Alleen de tijd gevraagd: met je keuze is het antwoord compleet, dus kijk
            # meteen na. Net als bij de woorden, waar één tik op een optie genoeg is.
            await nakijken()

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
        toon_typveld(invoer, sessie.vraag_praesens)
        if v is None:
            vormlabel.text = "✓"
            vraagsoort.text = f"Klaar — {sessie.goed} goed, {sessie.fout} fout."
            teller.text = ""
            tijdknoppen.clear()
            hulp.clear()
            toon_typveld(invoer, False)
            knop.text = "Nieuwe ronde"
            teken()
            return
        vormlabel.text = v["vorm"]
        vormlabel.style(f"font-size:{woordmaat(vormlabel.text, 52)}px")
        vraagsoort.text = ("Welke tijd is dit, en van welk werkwoord?"
                           if sessie.vraag_praesens else "Welke tijd is dit?")
        teller.text = f"{sessie.i + 1}/{len(sessie.vragen)}"
        # Wordt alleen de tijd gevraagd, dan kijkt je tik op een tijd meteen na en houdt
        # de knop de rol die hij bij de woorden ook heeft: opgeven.
        knop.text = "Nakijken" if sessie.vraag_praesens else "Ik weet het niet"
        invoer.value = ""
        teken()
        teken_tijden()
        teken_hulp(v)
        with statusbalk:
            ui.html(_statusrij([
                (v["streak"], "streak", TEKST),
                (_goedfout(v["goed"], v["fout"]), "", TEKST),
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
            if te_snel(sessie):
                return
            sessie.i += 1
            toon()
            return
        if sessie.tijd_keuze is None and sessie.vraag_praesens:
            # Er hoort ook een werkwoord bij, dus de knop heet hier 'Nakijken'. Zonder
            # gekozen tijd valt er niets na te kijken; even zeggen wat er nog mist.
            ui.notify("Kies eerst een tijd.", position="top", color="dark")
            return
        if sessie.tijd_keuze is None:
            await weet_niet(v)
            return
        tijd_ok = sessie.tijd_keuze == v["tijd"]
        pr_ok = (not sessie.vraag_praesens
                 or bool(motor.grieks_vorm_ok(invoer.value or "", v["praesens"])))
        juist = tijd_ok and pr_ok
        sessie.beoordeeld = True
        sessie.goed += int(juist)
        sessie.fout += int(not juist)
        e = stats.setdefault(v["sleutel"], {"g": 0, "f": 0, "streak": 0})
        # De stand van vóór deze beurt, zodat 'Ik had het goed' hem kan terugzetten.
        voor = dict(e)
        e["g"] = int(e.get("g", 0)) + int(juist)
        e["f"] = int(e.get("f", 0)) + int(not juist)
        # Zag je het antwoord al via 'Ik weet het niet', dan blijft de streak staan waar
        # hij stond: goed benoemen wat je net gelezen hebt is nog geen kennis. Aftrek is
        # het ook niet — je was eerlijk.
        if not (juist and v["sleutel"] in sessie.gezien):
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
                wat.append(f"de tijd was <b>{kleur_gram(TIJD_KORT[v['tijd']])}</b>")
                # Wat je wél aanklikte, en hoe díé vorm eruit had gezien. Daar leer je van
                # onderscheiden: je ziet de twee naast elkaar in plaats van alleen te horen
                # dat je het mis had.
                gekozen = sessie.tijd_keuze
                andere = (v["verb"].get("stamtijden") or {}).get(gekozen, "")
                if gekozen and motor._stam_vorm_ok(andere):
                    wat.append(f"jij koos {kleur_gram(TIJD_KORT[gekozen])}, en dat is "
                               f"<span class='grieks'>{andere}</span>")
                elif gekozen:
                    wat.append(f"jij koos {kleur_gram(TIJD_KORT[gekozen])}; die vorm "
                               f"heeft dit werkwoord niet")
            if not pr_ok:
                wat.append(f"het werkwoord was <b>{v['praesens']}</b>")
            deel = (f"<div style='color:{ZACHT};font-size:14px;margin-top:10px;"
                    f"line-height:1.6'>{'<br>'.join(wat)}</div>")
        kleur = GOED if juist else FOUT
        achter = "rgba(61,220,151,.10)" if juist else "rgba(255,107,129,.10)"
        # De feedback vervangt de vraag: vijf tijdknoppen plus een antwoordkaart
        # eronder maakt het scherm te lang voor een telefoon.
        tijdknoppen.set_visibility(False)
        statusbalk.set_visibility(False)
        vormlabel.set_visibility(False)
        vraagsoort.set_visibility(False)
        toon_typveld(invoer, False)
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
                f"{kleur_gram(TIJD_KORT[v['tijd']])} van "
                f"<span class='grieks' style='font-size:20px'>{v['praesens']}</span></div>"
                f"<div style='color:{ZACHT};font-size:15px;margin-top:2px'>"
                f"{v['verb'].get('betekenis', '')}</div>"
                f"{deel}{opbouw}"
                f"<div style='color:{ZACHT};font-size:12.5px;margin-top:18px'>"
                f"{sessie.goed} goed · {sessie.fout} fout in deze ronde · "
                f"streak nu {e['streak']}</div></div>")
            if not juist:
                toch_goed_knop(terugkoppeling,
                               lambda _=None: toch_goed(v, e, dict(voor)))
        if opgeslagen:
            opslagmelding.text = "Voortgang opgeslagen"
        knop.text = "Volgende"
        _uitslag_staat(sessie)

    async def weet_niet(v):
        """Eerlijk zeggen dat je het niet weet kost niets.

        Hiervoor telde deze knop meteen als een volle misser: je streak ging in één klap
        naar nul terwijl je juist eerlijk was. Nu zie je het antwoord, blijft je stand
        staan, en komt de vorm achteraan in de ronde terug — dan levert hij geen
        streak-punten meer op, want je hebt hem al gezien. Zelfde afspraak als bij de
        woordenschat."""
        sessie.beoordeeld = True
        sessie.gezien.add(v["sleutel"])
        sessie.vragen.append(v)
        tijdknoppen.set_visibility(False)
        statusbalk.set_visibility(False)
        vormlabel.set_visibility(False)
        vraagsoort.set_visibility(False)
        toon_typveld(invoer, False)
        terugkoppeling.clear()
        with terugkoppeling:
            ui.html(f"<div style='background:rgba(51,204,255,.09);border:1px solid "
                    f"{MERK}40;border-radius:16px;padding:26px 18px;text-align:center;"
                    f"width:100%'><div style='color:{MERK};font-weight:700;font-size:19px'>"
                    f"💡 Het antwoord</div>"
                    f"<div class='grieks' style='font-size:44px;color:{TEKST};"
                    f"margin-top:14px;line-height:1.15'>{v['vorm']}</div>"
                    f"<div style='color:{TEKST};font-size:17px;margin-top:8px'>"
                    f"{kleur_gram(TIJD_KORT[v['tijd']])} van "
                    f"<span class='grieks' style='font-size:20px'>{v['praesens']}</span>"
                    f"</div><div style='color:{ZACHT};font-size:15px;margin-top:2px'>"
                    f"{v['verb'].get('betekenis', '')}</div>"
                    f"<div style='color:{ZACHT};font-size:12.5px;margin-top:18px'>"
                    f"Geen aftrek. Deze vorm komt straks nog een keer.</div></div>")
        knop.text = "Volgende"
        _uitslag_staat(sessie)

    async def toch_goed(v, e, voor):
        """Je typte het Grieks net naast de vorm en de app rekende het fout terwijl je hem
        wist. Zet de stand terug op die van vóór deze beurt en boek hem alsnog als goed."""
        e.clear()
        e.update(voor)
        e["g"] = int(e.get("g", 0)) + 1
        e["streak"] = int(e.get("streak", 0)) + 1
        sessie.fout = max(0, sessie.fout - 1)
        sessie.goed += 1
        g.dagdoel_plus("stam")
        terugkoppeling.clear()
        with terugkoppeling:
            ui.html(f"<div style='background:rgba(61,220,151,.10);border:1px solid "
                    f"{GOED}40;border-radius:16px;padding:26px 18px;text-align:center;"
                    f"width:100%'><div style='color:{GOED};font-weight:700;font-size:19px'>"
                    f"✓ Rechtgezet</div>"
                    f"<div class='grieks' style='font-size:44px;color:{TEKST};"
                    f"margin-top:14px;line-height:1.15'>{v['vorm']}</div>"
                    f"<div style='color:{TEKST};font-size:17px;margin-top:8px'>"
                    f"{TIJD_KORT[v['tijd']]} van "
                    f"<span class='grieks' style='font-size:20px'>{v['praesens']}</span>"
                    f"</div><div style='color:{ZACHT};font-size:12.5px;margin-top:18px'>"
                    f"{sessie.goed} goed · {sessie.fout} fout in deze ronde · "
                    f"streak nu {e['streak']}</div></div>")
        await run.io_bound(g.bewaar, True)

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
                ui.button("⚙", on_click=lambda: ui.navigate.to("/oefenen/stamtijden"), color=None).props(
                    "flat dense").style(f"color:{ZACHT};font-size:17px;min-width:32px")
        ui.label("Bekijk de vorm, benoem voor jezelf wélke tijd het is en van wélk "
                 "werkwoord, en check jezelf. Wat je nog niet wist komt achteraan terug.").style(
            f"color:{ZACHT};font-size:12.5px;line-height:1.5")
        vormlabel = ui.label().classes("grieks w-full text-center").style(
            f"font-size:52px;line-height:1.15;color:{TEKST};padding:16px 0 2px")
        antwoordvak = ui.column().classes("w-full gap-1 items-center").style(
            "min-height:120px")
        opslagmelding = ui.label().style(f"color:{ZACHT};font-size:12.5px;min-height:16px")

    balk = ui.element("div").classes("antwoordbalk")
    with balk:
        toonknop = ui.button("Toon antwoord", color=None).props("unelevated no-caps").style(
            f"background:{MERK};color:{INKT};font-weight:700;height:40px;width:100%")
        with ui.row().classes("w-full gap-2 no-wrap").style("margin-top:4px") as oordeel:
            wistknop = ui.button("✓ Wist ik", color=None).props("flat no-caps").style(
                f"flex:1;color:{GOED};border:1px solid {RAND};border-radius:8px")
            nogknop = ui.button("✗ Nog niet", color=None).props("flat no-caps").style(
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
        vormlabel.style(f"font-size:{woordmaat(vormlabel.text, 52)}px")
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
                f"<div style='color:{ZACHT};font-size:13px;margin-top:8px'>"
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
HEB_AF_OEFENINGEN = ["Zwakste eerst", "Rijtje voor rijtje", "Alleen wat ik fout deed"]
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
        f"<span style='color:{ZACHT}'>{kleur_gram(c['label'])}</span>"
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
            f"color:{ZACHT};font-size:13px")
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
            f"color:{ZACHT};font-size:13px").bind_visibility_from(
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
            ui.button("Annuleren", on_click=instellingen.close, color=None).props("flat no-caps").style(
                f"color:{ZACHT}")
            ui.button("Toepassen", on_click=bewaar_inst, color=None).props("unelevated no-caps").style(
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
                ui.button("⚙", on_click=instellingen.open, color=None).props("flat dense no-caps").classes(
                    "raakbaar").style(
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
                f"color:{ZACHT};font-size:13px")
            ui.html(af_paspoort(cellen))
        rooster = ui.column().classes("w-full gap-2").style("padding-top:6px")
        terugkoppeling = ui.column().classes("w-full items-center").style("min-height:40px")
        opslagmelding = ui.label().style(f"color:{ZACHT};font-size:12.5px;min-height:16px")

    balk = ui.element("div").classes("antwoordbalk")
    with balk:
        knop = ui.button("Nakijken", color=None).props("unelevated no-caps").style(
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
                            "outlined dense dark autocomplete=off autocapitalize=none autocorrect=off spellcheck=false enterkeyhint=done").classes("flex-grow")
                else:
                    velden[c["id"]] = ui.input(label=c["label"]).props(
                        "outlined dense dark autocomplete=off autocapitalize=none autocorrect=off spellcheck=false enterkeyhint=done").classes("w-full")
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
                ui.button("⚙", on_click=instellingen.open, color=None).props("flat dense no-caps").classes(
                    "raakbaar").style(
                    f"color:{ZACHT};font-size:17px;min-width:32px")
        streepjes = ui.row().classes("w-full gap-1 no-wrap")
        paspoort = ui.column().classes("w-full")
        rijtje = ui.html().classes("w-full text-center").style(
            f"color:{ZACHT};font-size:13px;padding-top:4px")
        gevraagd = ui.html().classes("w-full text-center").style(
            f"color:{TEKST};font-size:30px;font-weight:700;line-height:1.2")
        vraagsoort = ui.label().classes("w-full text-center").style(
            f"color:{ZACHT};font-size:13px")
        opties = ui.column().classes("keuzevak w-full gap-2").style("padding-top:6px")
        statusbalk = ui.row().classes("w-full").style("padding-top:2px")
        terugkoppeling = ui.column().classes("w-full items-center justify-center").style(
            "min-height:64px;padding-top:8px")
        opslagmelding = ui.label().style(f"color:{ZACHT};font-size:12.5px;min-height:16px")

    invoer, knop = typbalk("typ de vorm (x = χ, u = υ, h = η)")
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
            rijtje.set_content("")
            paspoort.clear()
            gevraagd.set_content("✓")
            vraagsoort.text = f"Klaar — {sessie.goed} goed, {sessie.fout} fout."
            teller.text = ""
            toon_typveld(invoer, False)
            knop.text = "Nieuwe ronde"
            teken()
            return
        sessie.vraag_typen = af_vraagt_typen(sessie.prefs["af_vraagvorm"], c["streak"])
        # Indicativus, Imperfectum en de rest krijgen hun eigen kleur, zodat je in één
        # oogopslag ziet welk soort vorm er gevraagd wordt.
        rijtje.set_content(kleur_gram(f"{c['categorie']} · {c['paradigma']}"))
        # Het hele rijtje kunnen bestuderen zonder de oefening te verlaten: de vaste
        # stam wit, de variabele uitgang cyaan.
        paspoort.clear()
        with paspoort:
            with ui.expansion("Bekijk het rijtje").props("dense").classes("w-full").style(
                    f"color:{ZACHT};font-size:12.5px"):
                ui.html(af_paspoort(c["rijtje"]))
        gevraagd.set_content(kleur_gram(c["label"]))
        vraagsoort.text = "" if sessie.vraag_typen else "Welke vorm hoort hierbij?"
        teller.text = f"{sessie.i + 1}/{len(sessie.vragen)}"
        knop.text = "Nakijken" if sessie.vraag_typen else "Ik weet het niet"
        invoer.value = ""
        toon_typveld(invoer, sessie.vraag_typen)
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
                (_goedfout(c["goed"], c["fout"]), "", TEKST),
                (c["niveau"], "", ZACHT),
                (len(sessie.vragen) - sessie.i - 1, "te gaan", ZACHT),
            ]))
        if sessie.vraag_typen:
            invoer.run_method("focus")

    async def verwerk(c, juist):
        sessie.beoordeeld = True
        sessie.goed += int(juist)
        sessie.fout += int(not juist)
        e = stats.setdefault(c["id"], {"g": 0, "f": 0, "streak": 0})
        voor = dict(e)                      # voor 'Ik had het goed'
        e["g"] = int(e.get("g", 0)) + int(juist)
        e["f"] = int(e.get("f", 0)) + int(not juist)
        e["streak"] = int(e.get("streak", 0)) + 1 if juist else 0
        g.tel_dag()
        if juist:
            g.dagdoel_plus("actief")
        opgeslagen = await run.io_bound(g.bewaar)
        for vak in (rijtje, gevraagd, vraagsoort, opties, statusbalk):
            vak.set_visibility(False)
        toon_typveld(invoer, False)
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
                f"<div style='font-size:13.5px'>{kleur_gram(c['paradigma'])}</div>"
                f"{opbouw}{uitleg}"
                f"<div style='color:{ZACHT};font-size:12.5px;margin-top:18px'>"
                f"{sessie.goed} goed · {sessie.fout} fout in deze ronde · "
                f"streak nu {e['streak']}</div></div>")
            # Alleen bij typen: bij meerkeuze klik je op een vorm, dan valt er niets
            # verkeerd te spellen en zou de knop je je fout laten wegtikken.
            if not juist and sessie.vraag_typen:
                toch_goed_knop(terugkoppeling,
                               lambda _=None: toch_goed(c, e, dict(voor)))
        if opgeslagen:
            opslagmelding.text = "Voortgang opgeslagen"
        knop.text = "Volgende"
        _uitslag_staat(sessie)

    async def toch_goed(c, e, voor):
        """Eén letter naast de gevraagde vorm terwijl je hem wist: de stand terug naar
        die van vóór deze beurt en alsnog als goed geboekt."""
        e.clear()
        e.update(voor)
        e["g"] = int(e.get("g", 0)) + 1
        e["streak"] = int(e.get("streak", 0)) + 1
        sessie.fout = max(0, sessie.fout - 1)
        sessie.goed += 1
        g.dagdoel_plus("actief")
        terugkoppeling.clear()
        with terugkoppeling:
            ui.html(f"<div style='background:rgba(61,220,151,.10);border:1px solid "
                    f"{GOED}40;border-radius:16px;padding:26px 18px;text-align:center;"
                    f"width:100%'><div style='color:{GOED};font-weight:700;font-size:19px'>"
                    f"✓ Rechtgezet</div>"
                    f"<div class='grieks' style='font-size:44px;color:{TEKST};"
                    f"margin-top:14px;line-height:1.15'>{c['vorm']}</div>"
                    f"<div style='color:{TEKST};font-size:16px;margin-top:6px'>"
                    f"{c['label']}</div>"
                    f"<div style='color:{ZACHT};font-size:12.5px;margin-top:18px'>"
                    f"{sessie.goed} goed · {sessie.fout} fout in deze ronde · "
                    f"streak nu {e['streak']}</div></div>")
        await run.io_bound(g.bewaar, True)

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
                if te_snel(sessie):
                    return
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


_SW_NAAMVAL = {"gen": "genitivus", "dat": "dativus", "acc": "accusativus"}


def sw_naamval(w):
    """'διά (met gen)' → ('διά', 'genitivus'). Hetzelfde woord met een andere naamval
    erachter betekent iets anders, en dát is wat je hier leert onderscheiden. Ze staan als
    aparte regels in de database en hebben dus elk hun eigen streak; door de naamval los
    van het Griekse woord te zetten zie je dat ook."""
    grieks = str(w.get("grieks", ""))
    match = re.match(r"^(.*?)\s*\(met (\w+)\)\s*$", grieks)
    if not match:
        return grieks, ""
    return match.group(1), _SW_NAAMVAL.get(match.group(2), match.group(2))


def sw_nieuw(w):
    """Nog nooit langsgekomen: geen goed, geen fout, geen streak."""
    return not (int(w.get("goed", 0) or 0) or int(w.get("fout", 0) or 0)
                or int(w.get("streak", 0) or 0))


def sw_rijtjeregel(w):
    """Eén regel voor 'Leer eerst dit rijtje': woord, naamval, betekenis, categorie."""
    kaal, naamval = sw_naamval(w)
    achter = (f" <span style='color:{gram_kleur(naamval) or MERK}'>+ {naamval}</span>"
              ) if naamval else ""
    return (f"<div style='font-size:13px;line-height:1.7;color:{TEKST}'>"
            f"<span class='grieks' style='font-size:16px'>{kaal}</span>{achter}"
            f" — {w.get('nederlands', '') or w.get('betekenis', '')}"
            f"<span style='color:{ZACHT};font-size:12.5px'> · "
            f"{w.get('categorie', '')}</span></div>")


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
        self.vragen = self._kaarten(woorden[:int(p["sw_aantal"])])
        self.i = 0
        self.goed = 0
        self.fout = 0
        self.beoordeeld = False
        self.bezig = False
        self.vraag_typen = True

    @staticmethod
    def _kaarten(woorden):
        """Een woord dat je nog nooit zag krijgt eerst een leerkaart: je ziet wat het
        betekent, en pas daarna de vraag. Zonder die kaart is je eerste ontmoeting met
        ἀλλά een gok uit vier opties — dat leert niets. Zo doet het Leerpad van de
        woordenschat het ook (leerpad_kaart_volgorde in de motor)."""
        kaarten = []
        for w in woorden:
            if sw_nieuw(w):
                kaarten.append((w, "leer"))
            kaarten.append((w, "vraag"))
        return kaarten

    @property
    def huidig(self):
        return self.vragen[self.i][0] if self.i < len(self.vragen) else None

    @property
    def vorm(self):
        return self.vragen[self.i][1] if self.i < len(self.vragen) else None


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
                f"color:{ZACHT};font-size:13px").bind_visibility_from(
                k_oef, "value", lambda v: v == "Leerpad (volgend blokje)")
        k_cat = ui.select(categorieen, value=sessie.prefs["sw_categorie"],
                          label="Categorie").props("outlined dark").classes("w-full")
        k_vorm = ui.select(SW_VRAAGVORM, value=sessie.prefs["sw_vraagvorm"],
                           label="Wat wordt gevraagd").props("outlined dark").classes("w-full")
        k_aantal = ui.number("Woorden per ronde", value=int(sessie.prefs["sw_aantal"]),
                             min=4, max=40, step=1).props("outlined dark").classes("w-full")
        ui.label(f"Automatisch: eerst aanwijzen, en vanaf streak {SW_TYP_STREAK} "
                 f"de betekenis zelf typen.").style(f"color:{ZACHT};font-size:13px")

        async def bewaar_inst():
            for sleutel, veld in [("sw_keuze", k_oef), ("sw_categorie", k_cat),
                                  ("sw_vraagvorm", k_vorm), ("sw_aantal", k_aantal),
                                  ("sw_level", k_level)]:
                g.stats.setdefault("ui_prefs", {})[f"ng_{sleutel}"] = veld.value
            instellingen.close()
            await run.io_bound(g.bewaar, True)
            ui.navigate.to("/oefenen/structuur")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Annuleren", on_click=instellingen.close, color=None).props("flat no-caps").style(
                f"color:{ZACHT}")
            ui.button("Toepassen", on_click=bewaar_inst, color=None).props("unelevated no-caps").style(
                f"background:{MERK};color:{INKT};font-weight:700")

    with ui.column().classes("inhoud metbalk w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Structuurwoorden").style(f"color:{ZACHT};font-size:13px")
            with ui.row().classes("items-center gap-2 no-wrap"):
                teller = ui.label().style(f"color:{ZACHT};font-size:13px")
                ui.button("⚙", on_click=instellingen.open, color=None).props("flat dense no-caps").classes(
                    "raakbaar").style(
                    f"color:{ZACHT};font-size:17px;min-width:32px")
        if sessie.level:
            _xp = motor.bereken_xp_struct(g.stats.get("struct_stats") or {})
            _niv = motor.niveau_van_xp(_xp)
            _vol = sum(1 for s in sw_levels(g) if s.get("voltooid"))
            ui.html(f"<div style='display:flex;justify-content:space-between;font-size:13px;"
                    f"color:{ZACHT}'><span>Blokje {sessie.level['index']} · "
                    f"{sessie.level.get('titel', '')}</span><span>{_vol} af · niveau "
                    f"{_niv['niveau']}</span></div>")
            with ui.expansion("Leer eerst dit rijtje").props("dense").classes(
                    "w-full").style(f"color:{ZACHT};font-size:13px"):
                ui.html("".join(sw_rijtjeregel(w) for _idx, w in sessie.level["items"]))
        streepjes = ui.row().classes("w-full gap-1 no-wrap")
        woord = ui.label().classes("grieks w-full text-center").style(
            f"font-size:42px;line-height:1.1;color:{TEKST};padding:2px 0 0")
        soort = ui.html().classes("w-full text-center")
        vraagsoort = ui.label().classes("w-full text-center").style(
            f"color:{ZACHT};font-size:13px;padding-top:4px")
        opties = ui.column().classes("keuzevak w-full gap-2").style("padding-top:6px")
        statusbalk = ui.row().classes("w-full").style("padding-top:2px")
        terugkoppeling = ui.column().classes("w-full items-center justify-center").style(
            "min-height:64px;padding-top:8px")
        hulp = ui.row().classes("w-full gap-2 no-wrap")
        opslagmelding = ui.label().style(f"color:{ZACHT};font-size:12.5px;min-height:16px")

    invoer, knop = typbalk("betekenis")
    onderbalk("Oefenen")

    def sw_hint(w):
        """De hint bij structuurwoorden zet de naamvallen tegenover elkaar.

        Bij διά, κατά, μετά, περί, ὑπέρ, ὑπό, ἐπί, παρά en πρός hangt de betekenis aan de
        naamval: 'διά + gen' is 'door heen', 'διά + acc' is 'wegens'. Ze los uit je hoofd
        leren werkt niet; je moet ze naast elkaar zien. Staat er maar één naamval, dan
        krijg je de categorie en de eigenschap als steun."""
        kaal, naamval = sw_naamval(w)
        # Bewust alle naamvallen van dit woord, ook die je nu voor je hebt: het gaat om
        # het contrast, en dat zie je pas als ze onder elkaar staan.
        anderen = [x for x in sessie.alles
                   if sw_naamval(x)[0] == kaal and sw_naamval(x)[1]]
        if naamval and len(anderen) > 1:
            regels = [f"<span class='grieks'>{kaal}</span> "
                      f"<span style='color:{gram_kleur(sw_naamval(x)[1]) or MERK}'>"
                      f"+ {sw_naamval(x)[1]}</span> — {x.get('betekenis', '')}"
                      for x in anderen]
            kop = (f"Dezelfde vorm, andere naamval, andere betekenis. "
                   f"Jij hebt nu <span style='color:"
                   f"{gram_kleur(naamval) or MERK}'>{naamval}</span>:")
            return kop + "<br>" + "<br>".join(regels)
        delen = [d for d in (w.get("categorie", ""), w.get("eigenschap", "")) if d]
        return kleur_gram(" · ".join(delen)) or "Geen aanwijzing bij dit woord."

    def teken_hulp(w):
        hulp.clear()
        if w is None:
            return
        with hulp:
            ui.button("Hint", color=None,
                      on_click=lambda _=None, ww=w: ui.notify(
                          sw_hint(ww), position="top", color="dark", multi_line=True,
                          classes="text-body2", html=True).style("max-width:88vw")
                      ).props("flat dense no-caps").classes("raakbaar").style(
                f"flex:1;color:{ZACHT};border:1px solid {RAND};border-radius:8px;"
                f"font-size:12.5px")

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
            soort.set_content("")
            vraagsoort.text = f"Klaar — {sessie.goed} goed, {sessie.fout} fout."
            teller.text = ""
            hulp.clear()
            toon_typveld(invoer, False)
            knop.text = "Nieuwe ronde"
            teken()
            return
        kaal, naamval = sw_naamval(w)
        woord.text = kaal
        woord.style(f"font-size:{woordmaat(kaal, 42)}px")
        # De naamval krijgt de merkkleur en staat vóór de categorie: bij διά, κατά, ἐπί
        # en de andere voorzetsels is juist dát het verschil tussen twee kaarten.
        # De naamval in zijn eigen kleur: bij διά, κατά en ἐπί is dát het verschil tussen
        # twee kaarten, en op kleur onthoud je dat sneller dan op het woord alleen.
        nv_kleur = gram_kleur(naamval) or MERK
        soort.set_content(
            (f"<span style='color:{nv_kleur};font-size:13px'>+ {naamval}</span>"
             f"<span style='color:{ZACHT};font-size:12.5px'> · </span>" if naamval else "")
            + f"<span style='color:{ZACHT};font-size:12.5px'>"
              f"{w.get('categorie', '')}</span>")
        teller.text = f"{sessie.i + 1}/{len(sessie.vragen)}"
        teken()
        teken_hulp(w)
        if sessie.vorm == "leer":
            # Eerste ontmoeting: laten zien in plaats van laten raden.
            sessie.vraag_typen = False
            vraagsoort.text = "Nieuw — bekijk het even"
            statusbalk.set_visibility(False)
            toon_typveld(invoer, False)
            knop.text = "Bekeken"
            with opties:
                ui.html(
                    f"<div style='background:rgba(51,204,255,.09);border:1px solid "
                    f"{MERK}40;border-radius:12px;padding:14px 16px;text-align:center'>"
                    f"<div style='color:{ZACHT};font-size:13px'>betekenis</div>"
                    f"<div style='color:{TEKST};font-size:19px;line-height:1.35;"
                    f"margin-top:2px'>{w.get('betekenis', '')}</div>"
                    + (f"<div style='color:{MERK};font-size:13px;margin-top:8px'>"
                       f"hoort bij de {naamval}</div>" if naamval else "")
                    + "</div>")
            return
        sessie.vraag_typen = sw_vraagt_typen(sessie.prefs["sw_vraagvorm"], w["streak"])
        vraagsoort.text = ("" if sessie.vraag_typen
                           else "Welke betekenis hoort hierbij?")
        knop.text = "Nakijken" if sessie.vraag_typen else "Ik weet het niet"
        invoer.value = ""
        toon_typveld(invoer, sessie.vraag_typen)
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
                (_goedfout(w["goed"], w["fout"]), "", TEKST),
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
        toon_typveld(invoer, False)
        eig = w.get("eigenschap", "")
        regel_eig = (f"<div style='color:{gram_kleur(eig) or MERK};font-size:15px;"
                     f"margin-top:6px'>{eig}</div>" if eig else "")
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
                f"margin-top:14px;line-height:1.15'>{sw_naamval(w)[0]}</div>"
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
        _uitslag_staat(sessie)

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
            if sessie.beoordeeld or sessie.vorm == "leer":
                # Een leerkaart hoef je alleen te bekijken; er valt niets na te kijken
                # en hij telt niet mee voor je score. De vraag komt hierna vanzelf.
                if sessie.beoordeeld and te_snel(sessie):
                    return
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


# ============================================================== Hebreeuws
HEB_STANDAARD = {"heb_aantal": 12, "heb_vraagvorm": AUTO, "heb_lijst": "Alles",
                 "heb_keuze": "Leerpad (volgend blokje)", "heb_level": 0}
HEB_VRAAGVORM = [AUTO, "Alleen meerkeuze", "Alleen typen"]
HEB_OEFENINGEN = ["Leerpad (volgend blokje)", "Zwakste eerst", "Meest voorkomend eerst",
                  "Alleen wat ik fout deed", "Op volgorde van de lijst"]
# Zoveel woorden per blokje. Acht is klein genoeg om in één ronde af te maken en groot
# genoeg om iets te betekenen; dezelfde gedachte als de blokjes van zes bij structuurwoorden.
HEB_BLOK = 8
# Vanaf deze streak telt een woord binnen het blokje als 'af'. Onder de typgrens, dus je
# hebt hem dan aangewezen maar nog niet zelf getypt — het blokje sluit je af met herkennen,
# en het produceren komt terug als het woord later in een gewone ronde terugkomt.
HEB_BLOK_KLAAR = 5
HEB_LIJSTEN = {"Alles": 0, "Hebreeuws 1 · woord 1–165": 1, "Hebreeuws 2 · woord 166–410": 2}
# Zoveel tekens mag een keuzeknop hebben. Boven de veertig wordt hij twee regels hoog en
# raakt de lijst van vier uit balans; dan lees je de knoppen niet meer, maar scan je ze.
HEB_KORT = 42
# De regels zijn die van de Griekse woordenschat, en dat is geen toeval: het is dezelfde
# vaardigheid. Hierboven staan STREAK_PUNTEN (typen levert 3, aanwijzen 1), STREAK_STRAF
# (een echte misser kost er 2) en STRAF_STREAK (vanaf 16 telt de eerste misser al mee).
# De grens tussen aanwijzen en typen is motor.LEERPAD_TYP_STREAK — bij het Grieks precies
# dezelfde grens, dus een woord gedraagt zich in allebei de talen hetzelfde.


def heb_levels(g):
    """De Hebreeuwse woorden in blokjes, met per blokje hoever je bent.

    De volgorde is een keuze en geen toeval. Eerst alles uit de drie losse bestanden — 'C
    Veel voorkomende vormen', 'D veel voorkomende lexemen', 'E Veel voorkomende
    werkwoorden' — want dat zijn de woorden en vormen die in élk vers staan. וַיֹּאמֶר
    ('en hij zei') komt 1950 keer voor; wie die kent leest meteen makkelijker. Daarna de
    rest van de lijst op frequentie, want dan levert elk volgend blokje het meeste op.

    Binnen die twee groepen is de volgorde ook op frequentie, en dat is meetbaar: het staat
    per woord in de lijst, geteld in de Tenach zelf."""
    basis = [w for w in g.hebreeuws if int(w.get("les", 0) or 0) == 3]
    rest = [w for w in g.hebreeuws if int(w.get("les", 0) or 0) != 3]
    op_freq = lambda w: (-int(w.get("frequentie", 0) or 0), int(w.get("nummer", 0) or 0))
    geordend = sorted(basis, key=op_freq) + sorted(rest, key=op_freq)

    levels = []
    vorige_af = True
    for n, start in enumerate(range(0, len(geordend), HEB_BLOK)):
        brok = geordend[start:start + HEB_BLOK]
        klaar = sum(1 for w in brok
                    if int(w.get("streak", 0) or 0) >= HEB_BLOK_KLAAR)
        voltooid = bool(brok) and klaar == len(brok)
        titel = ("De basis: wat in elk vers staat" if brok and
                 int(brok[0].get("les", 0) or 0) == 3 else
                 f"vanaf {int(brok[0].get('frequentie', 0) or 0)}×" if brok else "")
        levels.append({"index": n + 1, "titel": titel, "items": brok,
                       "klaar": klaar, "totaal": len(brok), "voltooid": voltooid,
                       "ontgrendeld": vorige_af})
        vorige_af = voltooid
    return levels


def heb_prefs(g):
    return {k: (g.stats.get("ui_prefs") or {}).get(f"ng_{k}", v)
            for k, v in HEB_STANDAARD.items()}


# ---------------------------------------------------------------- de betekenis uitlezen
# De Hebreeuwse woordenlijst gebruikt een andere notatie dan de Griekse, en dat is geen
# slordigheid maar een verschil tussen de twee talen. Bij het Grieks scheidt een puntkomma
# de naamvallen: 'διά (+gen.) door(heen); (+acc.) door, wegens' — dat zijn echt twee dingen.
# Bij het Hebreeuws staat de puntkomma daar waar het Grieks een komma zet: bij עַל is
# '(boven)op, over, bij; tot, tegen; wegens' één rij gelijkwaardige betekenissen.
#
# De Hebreeuwse tegenhanger van de Griekse naamval is de stamformatie, en die staat er als
# code vóór het segment: 'G eten; N gegeten worden; H voeden'. Dáár scheidt de puntkomma
# wel iets grammaticaals.
#
# Vandaar deze regel: een puntkomma begint alleen een nieuwe groep als er een stamcode of
# een romeins cijfer voor staat. Staat er niets voor, dan is het een zwaardere komma en
# horen de betekenissen bij elkaar. Zonder die regel stond er op de keuzeknop van בְּ
# alleen 'in, op, bij' en vielen 'met, door, tegen' weg — allemaal even goede antwoorden.
#
# Verder kent de lijst drie soorten toevoeging, en die betekenen alle drie iets anders:
#   [ ... ]   uitleg over de functie, geen betekenis. Bij אֵת is dat
#             '[geeft lijdend voorwerp aan]' — dat hoort niet op een keuzeknop.
#   ( ... )   een deel dat je mag weglaten: '(boven)op' is zowel 'bovenop' als 'op'.
#   » ... «   het voorwerp dat je erbij denkt: '»de hand« uitstrekken'. Voor het nakijken
#             gaat dat eruit, anders wordt 'uitstrekken' fout gerekend.
HEB_STAMCODES = {"G": "Qal", "N": "Nifal", "D": "Piel", "Dp": "Pual", "H": "Hifil",
                 "Hp": "Hofal", "Ht": "Hitpael", "tD": "Hitpael", "R": "Polel",
                 "Rp": "Polal"}
HEB_CIJFERS = {"i": "I", "ii": "II", "iii": "III"}


def _heb_haakjes_weg(tekst, ook_rond=False):
    """Toevoegingen weghalen. De vierkante haken en de gidshaken altijd; de ronde alleen
    als je de korte vorm wil ('(boven)op' -> 'op')."""
    uit = re.sub(r"\[[^\]]*\]", " ", tekst)
    uit = re.sub(r"»[^«]*«", " ", uit)
    if ook_rond:
        uit = re.sub(r"\([^)]*\)", " ", uit)
    return re.sub(r"\s{2,}", " ", uit).strip(" ,;.:")


def heb_groepen(w):
    """De betekenis uit elkaar: een lijst groepen, elk met stam, cijfer, betekenissen, uitleg.

    Een groep begint bij een stamcode of een romeins cijfer. Een segment zonder zo'n
    aanduiding hoort bij de groep ervoor — bij סבב is 'omringen' nog steeds de Qal."""
    groepen = []
    for segment in heb_uitleg(w).split(";"):
        segment = segment.strip()
        if not segment:
            continue
        stam, cijfer = "", ""
        # De codes staan vooraan, en er kunnen er twee staan: 'G en N naderen'.
        while True:
            m = re.match(r"^(i{1,3}|Rp|Dp|Hp|Ht|tD|[GNDHR])\b[\s.]*(en\s+)?", segment)
            if not m:
                break
            teken = m.group(1)
            if teken in HEB_CIJFERS:
                cijfer = HEB_CIJFERS[teken]
            elif teken in HEB_STAMCODES:
                stam = stam or HEB_STAMCODES[teken]
            segment = segment[m.end():].lstrip()
        noten = re.findall(r"\[([^\]]*)\]", segment)
        kaal = _heb_haakjes_weg(segment)
        betekenissen = [d.strip(" .:") for d in kaal.split(",") if d.strip(" .:")]
        if (stam or cijfer) or not groepen:
            groepen.append({"stam": stam, "cijfer": cijfer,
                            "betekenissen": betekenissen, "noten": list(noten)})
        else:
            # Geen aanduiding: dit hoort bij de vorige groep.
            groepen[-1]["betekenissen"].extend(betekenissen)
            groepen[-1]["noten"].extend(noten)
    return groepen


def heb_uitleg(w):
    """De volledige betekenis zoals hij in de cursuslijst staat, zonder de geslachtscode.
    Die komt op de leerkaart en op het antwoordscherm te staan: dáár heb je alles nodig."""
    return re.sub(r"^\((?:v|m)\.?\)\s*", "", str(w.get("nederlands", ""))).strip()


def heb_betekenis(w):
    """De korte betekenis: dít staat op de keuzeknoppen, en dít is het antwoord.

    De eerste groep die echt betekenissen heeft. Bij een werkwoord is dat de Qal; bij אֵת
    slaat hij de eerste groep over, want daar staat alleen '[geeft lijdend voorwerp aan]'
    en dat is uitleg. Er worden zoveel betekenissen bijgezet als er passen — afkappen gaat
    dus per betekenis en nooit midden in een woord."""
    for groep in heb_groepen(w):
        if not groep["betekenissen"]:
            continue
        uit = ""
        for deel in groep["betekenissen"]:
            kandidaat = f"{uit}, {deel}" if uit else deel
            if len(kandidaat) > HEB_KORT:
                # rstrip op de puntjes: de lijst gebruikt zelf ook '…', en dan stond er
                # bij אִם 'o, dat toch ……' met twee reeksen achter elkaar.
                kort = (uit if uit else kandidaat[:HEB_KORT].rsplit(" ", 1)[0])
                return kort.rstrip(" .…,;") + "…"
            uit = kandidaat
        return uit
    # Alleen uitleg en geen betekenis: dan is die uitleg het beste wat we hebben.
    noten = [n for g in heb_groepen(w) for n in g["noten"]]
    return (noten[0] if noten else heb_uitleg(w))[:HEB_KORT]


def heb_antwoorden(w):
    """Alles wat als getypt antwoord goed mag zijn. Elk stuk gaat apart langs
    check_betekenis(), want die knipt zelf op komma's en vergelijkt dan alleen de héle
    tekst of één zo'n stukje — een betekenis met een komma erin komt er nooit heel door.

    Alle groepen tellen mee, dus ook de andere stamformaties: wie bij אכל 'voeden'
    schrijft heeft het woord herkend, ook al is dat de Hifil. En van elke betekenis komt er
    een vorm zonder de ronde haakjes bij, zodat '(boven)op' ook op 'op' matcht."""
    uit = [heb_betekenis(w)]
    for groep in heb_groepen(w):
        for deel in groep["betekenissen"]:
            uit.append(deel)
            zonder = _heb_haakjes_weg(deel, ook_rond=True)
            if zonder and zonder != deel:
                uit.append(zonder)
            # '(boven)op' zonder haakjes is 'bovenop': ook dat is een goed antwoord.
            heel = deel.replace("(", "").replace(")", "")
            if heel != deel:
                uit.append(heel)
    return [d for d in dict.fromkeys(uit) if d]


def heb_goed(antwoord, w):
    """Is dit getypte antwoord goed? Dezelfde soepelheid als bij het Grieks: een tikfout
    of twee mag, en één van de betekenissen noemen is genoeg."""
    return any(motor.check_betekenis(antwoord, kandidaat)
               for kandidaat in heb_antwoorden(w))


def heb_volledig(w):
    """De hele betekenis om te laten zien, met de stamcodes uitgeschreven.

    Op de kaart staat 'Qal' en niet 'G'. Die code is een afkorting voor wie de lijst al
    kent; wie het woord nog aan het leren is heeft de naam nodig."""
    delen = []
    for groep in heb_groepen(w):
        kop = " ".join(x for x in (groep["cijfer"], groep["stam"]) if x)
        tekst = ", ".join(groep["betekenissen"])
        noot = "; ".join(groep["noten"])
        regel = tekst
        if kop:
            regel = f"<b>{kop}</b> {tekst}" if tekst else f"<b>{kop}</b>"
        if noot:
            regel += f" <span style='color:{ZACHT}'>[{noot}]</span>" if regel \
                else f"<span style='color:{ZACHT}'>{noot}</span>"
        if regel:
            delen.append(regel)
    return " · ".join(delen) or heb_uitleg(w)


def heb_nieuw(w):
    """Nog nooit gezien: dan eerst laten zien in plaats van laten raden."""
    return not (int(w.get("streak", 0)) or int(w.get("score_goed", 0))
                or int(w.get("score_fout", 0)))


def heb_hint(w):
    """Wat er te bieden valt zonder het antwoord weg te geven: het beeld erbij, hoe het
    klinkt, en hoe vaak het in de Tenach staat. Die frequentie is zelf een geheugensteun —
    wie weet dat een woord 2600 keer voorkomt, weet dat het geen zeldzaam woord kan zijn."""
    delen = []
    if w.get("anker") or w.get("beeld"):
        delen.append(f"{w.get('anker', '')} {w.get('beeld', '')}".strip())
    if w.get("translit"):
        delen.append(f"klinkt als <i>{w['translit']}</i>")
    if w.get("frequentie"):
        delen.append(f"{w['frequentie']}× in de Tenach")
    # De andere stamformaties horen bij de hint: wie de Qal kent heeft aan 'Hifil voeden'
    # een duw in de goede richting zonder dat het antwoord er staat.
    groepen = [g for g in heb_groepen(w) if g["stam"] and g["betekenissen"]]
    if len(groepen) > 1:
        delen.append(" · ".join(f"{g['stam']}: {', '.join(g['betekenissen'])}"
                                for g in groepen[1:]))
    return "<br>".join(delen) or "Geen aanwijzing bij dit woord."


class HebSessie:
    def __init__(self, g):
        p = heb_prefs(g)
        woorden = list(g.hebreeuws)
        les = HEB_LIJSTEN.get(p["heb_lijst"], 0)
        if les:
            woorden = [w for w in woorden if int(w.get("les", 0)) == les] or woorden
        self.level = None
        # Heb je een tekst ingesteld, dan gaan die woorden voor. Dat overrulet de volgorde
        # met opzet: je hebt dan een hoofdstuk dat je moet kennen, en dan is 'wat komt het
        # vaakst voor in de hele Tenach' niet meer de vraag die telt.
        self.tekst = ""
        self.tekst_aantal = 0
        _tekst_naam, _tekst_strongs = heb_tekst_keuze(g)
        if _tekst_strongs:
            _wil = set(_tekst_strongs)
            _uit_tekst = [w for w in woorden if str(w.get("strong") or "") in _wil]
            if _uit_tekst:
                self.tekst = _tekst_naam
                self.tekst_aantal = len(_uit_tekst)
                _uit_tekst.sort(key=lambda w: (int(w.get("streak", 0) or 0),
                                               -int(w.get("frequentie", 0) or 0)))
                woorden = _uit_tekst
        if not self.tekst and p["heb_keuze"] == "Leerpad (volgend blokje)":
            # Het gekozen blokje, of anders het eerstvolgende dat nog niet af is.
            status = heb_levels(g)
            gekozen = int(p.get("heb_level", 0) or 0)
            doel = next((s for s in status if s["index"] == gekozen), None) if gekozen else None
            if doel is None:
                doel = next((s for s in status
                             if s["ontgrendeld"] and not s["voltooid"]), None)
            if doel:
                self.level = doel
                woorden = list(doel["items"])
        elif p["heb_keuze"] == "Alleen wat ik fout deed":
            woorden = [w for w in woorden if int(w.get("score_fout", 0)) > 0] or woorden
            woorden.sort(key=lambda w: -int(w.get("score_fout", 0)))
        elif p["heb_keuze"] == "Meest voorkomend eerst":
            # De honderd meest voorkomende woorden dekken al een groot deel van de tekst;
            # wie daarmee begint kan het snelst iets lezen.
            woorden.sort(key=lambda w: (-int(w.get("frequentie", 0) or 0),
                                        int(w.get("streak", 0))))
        elif p["heb_keuze"] == "Op volgorde van de lijst":
            woorden.sort(key=lambda w: int(w.get("nummer", 0)))
        else:
            woorden.sort(key=lambda w: (int(w.get("streak", 0)),
                                        -int(w.get("frequentie", 0) or 0)))
        self.prefs = p
        self.alles = list(g.hebreeuws)
        self.vragen = self._kaarten(woorden[:max(4, int(p["heb_aantal"] or 12))])
        self.i = 0
        self.goed = 0
        self.fout = 0
        self.beoordeeld = False
        self.bezig = False
        self.vraag_typen = False
        # De paren die je deze ronde door elkaar haalde; die komen op de eindkaart.
        self.verwar = []

    @staticmethod
    def _kaarten(woorden):
        kaarten = []
        for w in woorden:
            if heb_nieuw(w):
                kaarten.append((w, "leer"))
            kaarten.append((w, "vraag"))
        return kaarten

    @property
    def huidig(self):
        return self.vragen[self.i][0] if self.i < len(self.vragen) else None

    @property
    def vorm(self):
        return self.vragen[self.i][1] if self.i < len(self.vragen) else None


def heb_spiekbrief():
    """Het schema als tabel. Zonder dit is 'schrijf מלך' een raadsel: op een Nederlands
    toetsenbord staan geen Hebreeuwse letters, en welke toets welke letter geeft moet je
    ergens kunnen opzoeken zonder de app te verlaten."""
    blokken = []
    for kop, paren in hebreeuws.SPIEKBRIEF:
        vakjes = "".join(
            f"<span style='display:inline-flex;align-items:baseline;gap:5px;"
            f"background:{VLAK};border:1px solid {RAND};border-radius:7px;"
            f"padding:3px 8px;margin:0 5px 5px 0;white-space:nowrap'>"
            f"<b style='color:{MERK};font-size:13px'>{toets}</b>"
            f"<span class='hebreeuws' style='font-size:17px'>{letter}</span></span>"
            for toets, letter in paren)
        blokken.append(f"<div style='color:{ZACHT};font-size:12px;margin:8px 0 3px'>"
                       f"{kop}</div><div>{vakjes}</div>")
    return ("<div style='color:" + TEKST + ";font-size:13px'>Je typt alléén de "
            "medeklinkers, net zoals ze in de woordenlijst staan. Slotletters gaan "
            "vanzelf goed: <b>mlk</b> wordt <span class='hebreeuws'>מלך</span>."
            "</div>" + "".join(blokken))


@ui.page("/oefenen/hebreeuws")
def hebpagina():
    g = _bewaakt()
    if not g:
        return
    if not g.hebreeuws:
        ui.navigate.to("/vandaag")
        return
    sessie = HebSessie(g)

    with ui.dialog() as instellingen, ui.card().style(
            f"background:{VLAK};color:{TEKST};min-width:300px;max-width:92vw"):
        ui.label("Instellingen").style("font-size:18px;font-weight:700")
        k_oef = ui.select(HEB_OEFENINGEN, value=sessie.prefs["heb_keuze"],
                          label="Volgorde").props("outlined dark").classes("w-full")
        # Welke blokjes je al open hebt. Alleen die staan in de lijst; het volgende komt
        # vrij zodra je het huidige af hebt.
        _lv = heb_levels(g)
        _open = {0: "Automatisch (volgend blokje)"}
        for _st in _lv:
            if _st["ontgrendeld"]:
                _open[_st["index"]] = (f"Blokje {_st['index']} · {_st['titel']} "
                                       f"({_st['klaar']}/{_st['totaal']})")
        _hl = int(sessie.prefs.get("heb_level", 0) or 0)
        k_level = ui.select(_open, value=_hl if _hl in _open else 0,
                            label="Blokje").props("outlined dark").classes("w-full")
        k_level.bind_visibility_from(k_oef, "value",
                                     lambda v: v == "Leerpad (volgend blokje)")
        k_lijst = ui.select(list(HEB_LIJSTEN), value=sessie.prefs["heb_lijst"],
                            label="Woordenlijst").props("outlined dark").classes("w-full")
        k_vorm = ui.select(HEB_VRAAGVORM, value=sessie.prefs["heb_vraagvorm"],
                           label="Wat wordt gevraagd").props("outlined dark").classes("w-full")
        k_aantal = ui.number("Woorden per ronde", value=int(sessie.prefs["heb_aantal"]),
                             min=4, max=40, step=1).props("outlined dark").classes("w-full")
        ui.label(f"Automatisch: nieuwe woorden eerst als leerkaart, daarna aanwijzen, "
                 f"en vanaf streak {motor.LEERPAD_TYP_STREAK} de betekenis zelf typen. "
                 f"Precies zoals bij de Griekse woordenschat.").style(
            f"color:{ZACHT};font-size:13px")

        async def bewaar_inst():
            for sleutel, veld in [("heb_keuze", k_oef), ("heb_lijst", k_lijst),
                                  ("heb_vraagvorm", k_vorm), ("heb_aantal", k_aantal),
                                  ("heb_level", k_level)]:
                g.stats.setdefault("ui_prefs", {})[f"ng_{sleutel}"] = veld.value
            instellingen.close()
            await run.io_bound(g.bewaar, True)
            ui.navigate.to("/oefenen/hebreeuws")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Annuleren", on_click=instellingen.close, color=None).props("flat no-caps").style(
                f"color:{ZACHT}")
            ui.button("Toepassen", on_click=bewaar_inst, color=None).props("unelevated no-caps").style(
                f"background:{MERK};color:{INKT};font-weight:700")

    with ui.column().classes("inhoud metbalk w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Hebreeuws").style(f"color:{ZACHT};font-size:13px")
            with ui.row().classes("items-center gap-2 no-wrap"):
                teller = ui.label().style(f"color:{ZACHT};font-size:13px")
                ui.button("⚙", on_click=instellingen.open, color=None).props(
                    "flat dense no-caps").classes("raakbaar").style(
                    f"color:{ZACHT};font-size:17px;min-width:32px")
        if sessie.tekst:
            ui.html(f"<div style='display:flex;justify-content:space-between;"
                    f"font-size:13px;color:{ZACHT}'><span>Tekst: "
                    f"<span style='color:{MERK}'>{sessie.tekst}</span></span>"
                    f"<span>{sessie.tekst_aantal} woorden uit die tekst</span>"
                    f"</div>")
        if sessie.level:
            _af = sum(1 for s in heb_levels(g) if s["voltooid"])
            ui.html(f"<div style='display:flex;justify-content:space-between;font-size:13px;"
                    f"color:{ZACHT}'><span>Blokje {sessie.level['index']} · "
                    f"{sessie.level['titel']}</span><span>{_af} blokjes af</span></div>")
        streepjes = ui.row().classes("w-full gap-1 no-wrap")
        woord = ui.label().classes("hebreeuws w-full text-center").style(
            f"font-size:46px;line-height:1.25;color:{TEKST};padding:2px 0 0")
        onder = ui.html().classes("w-full text-center")
        vraagsoort = ui.label().classes("w-full text-center").style(
            f"color:{ZACHT};font-size:13px;padding-top:4px")
        opties = ui.column().classes("keuzevak w-full gap-2").style("padding-top:6px")
        statusbalk = ui.row().classes("w-full").style("padding-top:2px")
        terugkoppeling = ui.column().classes("w-full items-center justify-center").style(
            "min-height:64px;padding-top:8px")
        hulp = ui.row().classes("w-full gap-2 no-wrap")
        opslagmelding = ui.label().style(f"color:{ZACHT};font-size:12.5px;min-height:16px")

    invoer, knop = typbalk("betekenis")
    onderbalk("Oefenen")

    def teken_hulp(w):
        hulp.clear()
        if w is None:
            return
        with hulp:
            ui.button("Hint", color=None,
                      on_click=lambda _=None, ww=w: ui.notify(
                          heb_hint(ww), position="top", color="dark", multi_line=True,
                          classes="text-body2", html=True).style("max-width:88vw")
                      ).props("flat dense no-caps").classes("raakbaar").style(
                f"flex:1;color:{ZACHT};border:1px solid {RAND};border-radius:8px;"
                f"font-size:12.5px")

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
        for vak in (woord, onder, vraagsoort, opties, statusbalk):
            vak.set_visibility(True)
        woord.classes(add="hebreeuws")
        if w is None:
            woord.classes(remove="hebreeuws")
            woord.text = "✓"
            woord.style("font-size:46px")
            onder.set_content("")
            vraagsoort.text = f"Klaar — {sessie.goed} goed, {sessie.fout} fout."
            teller.text = ""
            hulp.clear()
            toon_typveld(invoer, False)
            knop.text = "Nieuwe ronde"
            teken()
            # De paren die je in deze ronde door elkaar haalde, naast elkaar. Dát is waar
            # je ze van uit elkaar gaat houden.
            if sessie.verwar:
                with opties:
                    ui.html(
                        f"<div style='background:{VLAK};border:1px solid {RAND};"
                        f"border-radius:12px;padding:14px 16px'>"
                        f"<div style='color:{ZACHT};font-size:13px;margin-bottom:8px'>"
                        f"Deze haalde je door elkaar</div>"
                        + "".join(
                            f"<div style='padding:5px 0;border-top:1px solid {RAND};"
                            f"font-size:13.5px'>"
                            f"<span class='hebreeuws' style='font-size:18px;"
                            f"color:{TEKST}'>{a['hebreeuws']}</span>"
                            f"<span style='color:{ZACHT}'> {heb_betekenis(a)}</span><br>"
                            f"<span class='hebreeuws' style='font-size:18px;"
                            f"color:{TEKST}'>{b['hebreeuws']}</span>"
                            f"<span style='color:{ZACHT}'> {heb_betekenis(b)}</span></div>"
                            for a, b in sessie.verwar[:5])
                        + "</div>")
            return
        teller.text = f"{sessie.i + 1}/{len(sessie.vragen)}"
        teken()
        teken_hulp(w)
        if sessie.vorm == "leer":
            sessie.vraag_typen = False
            woord.text = w["hebreeuws"]
            woord.style(f"font-size:{woordmaat(w['hebreeuws'], 46)}px")
            onder.set_content(
                f"<span style='color:{ZACHT};font-size:13px'>{w.get('translit', '')}</span>")
            vraagsoort.text = "Nieuw — bekijk het even"
            statusbalk.set_visibility(False)
            toon_typveld(invoer, False)
            knop.text = "Bekeken"
            with opties:
                ui.html(
                    f"<div style='background:rgba(51,204,255,.09);border:1px solid "
                    f"{MERK}40;border-radius:12px;padding:14px 16px;text-align:center'>"
                    f"<div style='color:{ZACHT};font-size:13px'>betekenis</div>"
                    f"<div style='color:{TEKST};font-size:19px;line-height:1.35;"
                    f"margin-top:2px'>{heb_volledig(w)}</div>"
                    f"<div style='color:{MERK};font-size:13px;margin-top:8px'>"
                    f"{w.get('anker', '')} {w.get('beeld', '')}</div></div>")
            return
        vorm = sessie.prefs["heb_vraagvorm"]
        sessie.vraag_typen = (vorm == "Alleen typen"
                              or (vorm == AUTO and int(w.get("streak", 0))
                                  >= motor.LEERPAD_TYP_STREAK))
        invoer.value = ""
        toon_typveld(invoer, sessie.vraag_typen)
        # De vraag is altijd dezelfde kant op: het Hebreeuwse woord staat er, jij geeft de
        # betekenis. Aanwijzen of zelf typen is alleen het verschil tussen herkennen en
        # het uit je hoofd weten — zelf Hebreeuws schrijven is een ándere vaardigheid en
        # hoort niet in de woordenschat thuis.
        woord.text = w["hebreeuws"]
        woord.style(f"font-size:{woordmaat(w['hebreeuws'], 46)}px")
        onder.set_content("")
        vraagsoort.text = "Wat betekent dit?"
        if sessie.vraag_typen:
            knop.text = "Nakijken"
        else:
            knop.text = "Ik weet het niet"
            juist = heb_betekenis(w)
            anderen = [heb_betekenis(x) for x in sessie.alles
                       if x is not w and heb_betekenis(x) != juist]
            keuzes = random.sample(anderen, min(3, len(anderen))) + [juist]
            random.shuffle(keuzes)
            with opties:
                for keuze in keuzes:
                    ui.html(f"<button class='keuze' style='font-size:14.5px;"
                            f"padding:9px 12px;line-height:1.35'>{keuze}</button>").on(
                        "click", lambda _=None, kz=keuze: kies(kz))
        with statusbalk:
            ui.html(_statusrij([
                (int(w.get("streak", 0)), "streak", TEKST),
                (_goedfout(int(w.get("score_goed", 0)), int(w.get("score_fout", 0))), "",
                 TEKST),
                (len(sessie.vragen) - sessie.i - 1, "te gaan", ZACHT),
            ]))
        if sessie.vraag_typen:
            invoer.run_method("focus")

    async def verwerk(w, juist, aangeklikt=None):
        sessie.beoordeeld = True
        sessie.goed += int(juist)
        sessie.fout += int(not juist)
        if juist:
            w["score_goed"] = int(w.get("score_goed", 0)) + 1
        # Bij een misser onthouden welk woord jij bedoelde. Twee woorden die je door elkaar
        # haalt leer je alleen uit elkaar door ze naast elkaar te zien — dat is precies wat
        # de verwarparen bij het Grieks doen.
        if not juist and aangeklikt:
            verward = next((x for x in sessie.alles
                            if x is not w and heb_betekenis(x) == aangeklikt), None)
            if verward is not None:
                sessie.verwar.append((w, verward))
            # Dezelfde opbrengst als bij het Grieks: zelf typen 3, aanwijzen 1.
            w["streak"] = int(w.get("streak", 0)) + STREAK_PUNTEN["4" if sessie.vraag_typen
                                                                  else "2"]
        else:
            w["score_fout"] = int(w.get("score_fout", 0)) + 1
            w["laatst_fout"] = gebruikers.vandaag()
            # En dezelfde straf: een woord dat je al beheerste (streak 16 of hoger) valt
            # meteen twee terug. Daaronder kost een misser je streak niets — je hebt het
            # woord nog niet vast, en dan is terugzetten ontmoedigend zonder dat het leert.
            if int(w.get("streak", 0)) >= STRAF_STREAK:
                w["streak"] = max(0, int(w.get("streak", 0)) - STREAK_STRAF)
        g.tel_dag()
        w["laatst_geoefend"] = gebruikers.vandaag()
        if juist:
            g.dagdoel_plus("hebreeuws")
        opgeslagen = await run.io_bound(g.bewaar)
        for vak in (woord, onder, vraagsoort, opties, statusbalk):
            vak.set_visibility(False)
        toon_typveld(invoer, False)
        kleur = GOED if juist else FOUT
        achter = "rgba(61,220,151,.10)" if juist else "rgba(255,107,129,.10)"
        # Wat je aanklikte erbij, met het woord waar die betekenis bij hoort. Zonder dat
        # weet je alleen dát het fout was, niet wat je in gedachten had.
        gekozen = ""
        if not juist and aangeklikt:
            verward = next((x for x in sessie.alles
                            if x is not w and heb_betekenis(x) == aangeklikt), None)
            erbij = (f" — dat is <span class='hebreeuws' style='font-size:19px'>"
                     f"{verward['hebreeuws']}</span>" if verward is not None else "")
            gekozen = (f"<div style='color:{ZACHT};font-size:13px;margin-top:8px'>"
                       f"jij koos <span style='color:{FOUT}'>{aangeklikt}</span>"
                       f"{erbij}</div>")
        vindplaats = (w.get("vindplaatsen") or [{}])[0]
        regel_vind = (f"<div style='color:{ZACHT};font-size:12.5px;margin-top:10px'>"
                      f"<span class='hebreeuws'>{vindplaats.get('vorm', '')}</span> — "
                      f"{vindplaats.get('vers', '')}</div>" if vindplaats.get("vers") else "")
        terugkoppeling.clear()
        with terugkoppeling:
            ui.html(
                f"<div style='background:{achter};border:1px solid {kleur}40;"
                f"border-radius:16px;padding:22px 18px;text-align:center;width:100%'>"
                f"<div style='color:{kleur};font-weight:700;font-size:19px'>"
                f"{'✓ Goed!' if juist else '✗ Niet goed'}</div>"
                f"<div class='hebreeuws' style='font-size:40px;color:{TEKST};"
                f"margin-top:12px;line-height:1.3'>{w['hebreeuws']}</div>"
                f"<div style='color:{ZACHT};font-size:13px'>{w.get('translit', '')}</div>"
                f"<div style='color:{TEKST};font-size:17px;margin-top:6px;"
                f"line-height:1.45'>{heb_volledig(w)}</div>{gekozen}{regel_vind}"
                f"<div style='color:{ZACHT};font-size:12.5px;margin-top:14px'>"
                f"{sessie.goed} goed · {sessie.fout} fout in deze ronde · "
                f"streak nu {int(w.get('streak', 0))}</div></div>")
        if opgeslagen:
            opslagmelding.text = "Voortgang opgeslagen"
        knop.text = "Volgende"
        _uitslag_staat(sessie)

    async def kies(keuze):
        if sessie.beoordeeld or sessie.bezig:
            return
        sessie.bezig = True
        try:
            w = sessie.huidig
            await verwerk(w, keuze == heb_betekenis(w), keuze)
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
                ui.navigate.to("/oefenen/hebreeuws")
                return
            if sessie.beoordeeld or sessie.vorm == "leer":
                if sessie.beoordeeld and te_snel(sessie):
                    return
                sessie.i += 1
                toon()
                return
            if sessie.vraag_typen:
                await verwerk(w, heb_goed(invoer.value or "", w))
            else:
                await verwerk(w, False)
        finally:
            sessie.bezig = False

    knop.on_click(hoofdknop)
    invoer.on("keydown.enter", hoofdknop)
    toon()


# ============================================================== Hebreeuws · actief
# Dezelfde oefening als Actief Beheersen bij het Grieks: je krijgt de cel van een rijtje
# ('3e m ev' van het perfectum van אמר) en geeft de vorm. Onder streak 10 wijs je aan,
# daarboven schrijf je hem zelf — precies de grenzen en de punten van AF_*.
#
# Eén verschil, en dat is de taal en niet de app: het Hebreeuwse werkwoord vervoegt met
# voorvoegsels én met uitgangen. Het imperfectum doet allebei tegelijk (תֹּאמְרִי is ת +
# stam + י). Het Grieks heeft alleen een uitgang nodig; hier staan er twee, allebei in de
# merkkleur rond de witte stam.
HEB_AF_STANDAARD = {"heb_af_keuze": "Zwakste eerst", "heb_af_aantal": 10,
                    "heb_af_vraagvorm": AF_VRAAGVORM[0], "heb_af_categorie": "Alles"}


def heb_af_prefs(g):
    return {k: (g.stats.get("ui_prefs") or {}).get(f"ng_{k}", v)
            for k, v in HEB_AF_STANDAARD.items()}


def heb_af_cellen(g):
    """Alle oefenbare cellen uit hebreeuws_actief.json, met je scores erbij.

    De scores staan in hebr_stats, bij de woorden. Dat kan zonder ze door elkaar te halen:
    een cel heeft een sleutel als 'heb_559_v_qal_perf_3ms' en een woord een sleutel als
    '42:מלכ', dus de twee soorten kunnen elkaar niet overschrijven. Het scheelt een
    vijftiende kolom in de Sheet, en die zou de Streamlit-app óók moeten kennen."""
    db = hebreeuws.laad_rijtjes() or {}
    stats = g.stats.get("hebr_stats") or {}
    uit = []
    for niveau, categorieen in db.items():
        for categorie, paradigmas in categorieen.items():
            for paradigma, cellen in paradigmas.items():
                for c in cellen:
                    vorm = str(c.get("vorm", "") or "").strip()
                    if not vorm:
                        continue
                    s = stats.get(c.get("id", "")) or {}
                    uit.append({
                        "niveau": niveau, "categorie": categorie, "paradigma": paradigma,
                        "label": c.get("label", ""), "vorm": vorm,
                        "stam": c.get("stam", ""), "uitgang": c.get("uitgang", ""),
                        "voorvoegsel": c.get("voorvoegsel", ""),
                        "bijzonder": c.get("bijzonder") or [],
                        "toelichting": c.get("toelichting", ""), "vers": c.get("vers", ""),
                        "id": c.get("id", ""), "rijtje": cellen,
                        "streak": int(s.get("streak", 0) or 0),
                        "goed": int(s.get("g", 0) or 0),
                        "fout": int(s.get("f", 0) or 0)})
    return uit


def heb_af_vorm(cel, groot=True):
    """Eén vorm met zijn voorvoegsel en uitgang in de merkkleur, de stam in wit. Zo zie je
    waar de vervoeging zit zonder dat iemand het hoeft uit te leggen."""
    voor, stam, uit = cel.get("voorvoegsel", ""), cel.get("stam", ""), cel.get("uitgang", "")
    heel = cel.get("vorm", "")
    if not stam or stam not in "".join(t for t in heel if "א" <= t <= "ת"):
        return f"<span class='hebreeuws'>{heel}</span>"
    # De klinkertekens zitten tússen de medeklinkers, dus knippen op letterposities.
    posities = [i for i, t in enumerate(heel) if "א" <= t <= "ת"]
    a = posities[len(voor)] if len(voor) < len(posities) else len(heel)
    b = posities[len(voor) + len(stam)] if len(voor) + len(stam) < len(posities) else len(heel)
    maat = "font-size:17px" if not groot else ""
    return (f"<span class='hebreeuws' style='{maat}'>"
            f"<span style='color:{MERK};font-weight:700'>{heel[:a]}</span>"
            f"<span style='color:{TEKST}'>{heel[a:b]}</span>"
            f"<span style='color:{MERK};font-weight:700'>{heel[b:]}</span></span>")


def heb_af_paspoort(cellen):
    """Het hele rijtje om te bestuderen, zonder de oefening te verlaten."""
    return "".join(
        f"<div style='display:flex;justify-content:space-between;gap:10px;"
        f"border-top:1px solid {RAND};padding:6px 0;font-size:13px'>"
        f"<span style='color:{ZACHT}'>{c.get('label', '')}</span>"
        f"{heb_af_vorm(c, groot=False)}</div>" for c in cellen)


class HebAfSessie:
    def __init__(self, g):
        p = heb_af_prefs(g)
        cellen = heb_af_cellen(g)
        if p["heb_af_categorie"] != "Alles":
            cellen = [c for c in cellen
                      if c["categorie"] == p["heb_af_categorie"]] or cellen
        if p["heb_af_keuze"] == "Alleen wat ik fout deed":
            cellen = [c for c in cellen if c["fout"] > 0] or cellen
            cellen.sort(key=lambda c: -c["fout"])
        elif p["heb_af_keuze"] == "Rijtje voor rijtje":
            # Het eerstvolgende rijtje waar nog iets in zit dat je niet kent. Zo leer je een
            # rijtje als geheel in plaats van losse cellen uit tien verschillende rijtjes.
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
        self.vragen = cellen[:max(4, int(p["heb_af_aantal"] or 10))]
        self.i = 0
        self.goed = 0
        self.fout = 0
        self.beoordeeld = False
        self.bezig = False
        self.vraag_typen = True

    @property
    def huidig(self):
        return self.vragen[self.i] if self.i < len(self.vragen) else None


@ui.page("/oefenen/hebreeuws/actief")
def hebafpagina():
    g = _bewaakt()
    if not g:
        return
    if not hebreeuws.laad_rijtjes():
        ui.navigate.to("/oefenen")
        return
    sessie = HebAfSessie(g)
    stats = g.stats.setdefault("hebr_stats", {})
    categorieen = ["Alles"] + sorted({c["categorie"] for c in heb_af_cellen(g)})

    with ui.dialog() as instellingen, ui.card().style(
            f"background:{VLAK};color:{TEKST};min-width:300px;max-width:92vw"):
        ui.label("Instellingen").style("font-size:18px;font-weight:700")
        k_oef = ui.select(HEB_AF_OEFENINGEN, value=sessie.prefs["heb_af_keuze"],
                          label="Volgorde").props("outlined dark").classes("w-full")
        k_cat = ui.select(categorieen, value=sessie.prefs["heb_af_categorie"],
                          label="Categorie").props("outlined dark").classes("w-full")
        k_vorm = ui.select(AF_VRAAGVORM, value=sessie.prefs["heb_af_vraagvorm"],
                           label="Wat wordt gevraagd").props("outlined dark").classes("w-full")
        k_aantal = ui.number("Cellen per ronde", value=int(sessie.prefs["heb_af_aantal"]),
                             min=4, max=40, step=1).props("outlined dark").classes("w-full")
        ui.label(f"Automatisch: eerst aanwijzen, en vanaf streak {AF_TYP_STREAK} de vorm "
                 f"zelf schrijven. Dezelfde grens als bij het Grieks.").style(
            f"color:{ZACHT};font-size:13px")

        async def bewaar_inst():
            for sleutel, veld in [("heb_af_keuze", k_oef), ("heb_af_categorie", k_cat),
                                  ("heb_af_vraagvorm", k_vorm), ("heb_af_aantal", k_aantal)]:
                g.stats.setdefault("ui_prefs", {})[f"ng_{sleutel}"] = veld.value
            instellingen.close()
            await run.io_bound(g.bewaar, True)
            ui.navigate.to("/oefenen/hebreeuws/actief")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Annuleren", on_click=instellingen.close, color=None).props("flat no-caps").style(
                f"color:{ZACHT}")
            ui.button("Toepassen", on_click=bewaar_inst, color=None).props("unelevated no-caps").style(
                f"background:{MERK};color:{INKT};font-weight:700")

    # Hier is het spiekbriefje wél op zijn plaats: je moet Hebreeuws intypen.
    with ui.dialog() as spiek, ui.card().style(
            f"background:{VLAK};color:{TEKST};min-width:300px;max-width:92vw"):
        ui.label("Hebreeuws typen").style("font-size:18px;font-weight:700")
        ui.html(heb_spiekbrief())
        with ui.row().classes("w-full justify-end"):
            ui.button("Duidelijk", on_click=spiek.close, color=None).props(
                "unelevated no-caps").style(f"background:{MERK};color:{INKT};font-weight:700")

    with ui.column().classes("inhoud metbalk w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Actief beheersen").style(f"color:{ZACHT};font-size:13px")
            with ui.row().classes("items-center gap-2 no-wrap"):
                teller = ui.label().style(f"color:{ZACHT};font-size:13px")
                ui.button("א", on_click=spiek.open, color=None).props(
                    "flat dense no-caps").classes("raakbaar hebreeuws").style(
                    f"color:{ZACHT};font-size:17px;min-width:32px")
                ui.button("⚙", on_click=instellingen.open, color=None).props(
                    "flat dense no-caps").classes("raakbaar").style(
                    f"color:{ZACHT};font-size:17px;min-width:32px")
        streepjes = ui.row().classes("w-full gap-1 no-wrap")
        paspoort = ui.column().classes("w-full")
        rijtje = ui.html().classes("w-full text-center").style(
            f"color:{ZACHT};font-size:13px;padding-top:4px")
        gevraagd = ui.html().classes("w-full text-center").style(
            f"color:{TEKST};font-size:30px;font-weight:700;line-height:1.2")
        vraagsoort = ui.label().classes("w-full text-center").style(
            f"color:{ZACHT};font-size:13px")
        opties = ui.column().classes("keuzevak w-full gap-2").style("padding-top:6px")
        statusbalk = ui.row().classes("w-full").style("padding-top:2px")
        terugkoppeling = ui.column().classes("w-full items-center justify-center").style(
            "min-height:64px;padding-top:8px")
        opslagmelding = ui.label().style(f"color:{ZACHT};font-size:12.5px;min-height:16px")

    invoer, knop = typbalk("typ de vorm (mlk → מלך)")
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
            rijtje.set_content("")
            gevraagd.set_content("✓")
            paspoort.clear()
            vraagsoort.text = f"Klaar — {sessie.goed} goed, {sessie.fout} fout."
            teller.text = ""
            toon_typveld(invoer, False)
            knop.text = "Nieuwe ronde"
            teken()
            return
        sessie.vraag_typen = af_vraagt_typen(sessie.prefs["heb_af_vraagvorm"], c["streak"])
        # De onregelmatigheid erbij: dát is waarom dit rijtje er anders uitziet dan het
        # boekje. Zonder die uitleg blijft het stampen.
        _bijz = (f"<div style='color:{MERK};font-size:12.5px'>"
                 f"{' · '.join(c['bijzonder'])}</div>" if c.get("bijzonder") else "")
        rijtje.set_content(f"{c['categorie']} · {c['paradigma']}{_bijz}")
        paspoort.clear()
        with paspoort:
            with ui.expansion("Bekijk het rijtje").props("dense").classes("w-full").style(
                    f"color:{ZACHT};font-size:12.5px"):
                ui.html(heb_af_paspoort(c["rijtje"]))
        gevraagd.set_content(c["label"])
        vraagsoort.text = "" if sessie.vraag_typen else "Welke vorm hoort hierbij?"
        teller.text = f"{sessie.i + 1}/{len(sessie.vragen)}"
        knop.text = "Nakijken" if sessie.vraag_typen else "Ik weet het niet"
        invoer.value = ""
        toon_typveld(invoer, sessie.vraag_typen)
        teken()
        if not sessie.vraag_typen:
            # Afleiders uit hetzelfde rijtje: zo leer je de cellen onderling onderscheiden.
            anders = [x.get("vorm", "") for x in c["rijtje"]
                      if x.get("vorm") and x.get("vorm") != c["vorm"]]
            keuzes = random.sample(anders, min(3, len(anders))) + [c["vorm"]]
            random.shuffle(keuzes)
            with opties:
                for keuze in keuzes:
                    ui.html(f"<button class='keuze hebreeuws' style='font-size:20px;"
                            f"text-align:center;padding:10px 12px'>{keuze}</button>").on(
                        "click", lambda _=None, kz=keuze: kies(kz))
        with statusbalk:
            ui.html(_statusrij([
                (c["streak"], "streak", TEKST),
                (_goedfout(c["goed"], c["fout"]), "", TEKST),
                (c["niveau"], "", ZACHT),
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
        c["streak"] = e["streak"]
        g.tel_dag()
        if juist:
            g.dagdoel_plus("hebreeuws")
        opgeslagen = await run.io_bound(g.bewaar)
        for vak in (rijtje, gevraagd, vraagsoort, opties, statusbalk):
            vak.set_visibility(False)
        toon_typveld(invoer, False)
        vind = (f"<div style='color:{ZACHT};font-size:12.5px;margin-top:10px'>"
                f"{c['toelichting']}"
                + (f" · voor het eerst in {c['vers']}" if c["vers"] else "")
                + "</div>") if c["toelichting"] else ""
        kleur = GOED if juist else FOUT
        achter = "rgba(61,220,151,.10)" if juist else "rgba(255,107,129,.10)"
        terugkoppeling.clear()
        with terugkoppeling:
            ui.html(
                f"<div style='background:{achter};border:1px solid {kleur}40;"
                f"border-radius:16px;padding:24px 18px;text-align:center;width:100%'>"
                f"<div style='color:{kleur};font-weight:700;font-size:19px'>"
                f"{'✓ Goed!' if juist else '✗ Niet goed'}</div>"
                f"<div style='font-size:40px;margin-top:12px;line-height:1.3'>"
                f"{heb_af_vorm(c)}</div>"
                f"<div style='color:{ZACHT};font-size:13px;margin-top:6px'>"
                f"{c['paradigma']} · {c['label']}</div>{vind}"
                f"<div style='color:{ZACHT};font-size:12.5px;margin-top:14px'>"
                f"{sessie.goed} goed · {sessie.fout} fout in deze ronde · "
                f"streak nu {e['streak']}</div></div>")
        if opgeslagen:
            opslagmelding.text = "Voortgang opgeslagen"
        knop.text = "Volgende"
        _uitslag_staat(sessie)

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
                ui.navigate.to("/oefenen/hebreeuws/actief")
                return
            if sessie.beoordeeld:
                if te_snel(sessie):
                    return
                sessie.i += 1
                toon()
                return
            if sessie.vraag_typen:
                await verwerk(c, hebreeuws.vorm_ok(invoer.value or "", c["vorm"]))
            else:
                await verwerk(c, False)
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
            f"color:{ZACHT};font-size:13px")

        async def bewaar_inst():
            for sleutel, veld in [("ont_niveau", k_niv), ("ont_drempel", k_drem),
                                  ("ont_kleur", k_kleur), ("ont_rijtje", k_rijtje),
                                  ("ont_vertaalhulp", k_vh), ("ont_links", k_links)]:
                g.stats.setdefault("ui_prefs", {})[f"ng_{sleutel}"] = veld.value
            instellingen.close()
            await run.io_bound(g.bewaar, True)
            ui.navigate.to("/oefenen/ontleden")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Annuleren", on_click=instellingen.close, color=None).props("flat no-caps").style(
                f"color:{ZACHT}")
            ui.button("Toepassen", on_click=bewaar_inst, color=None).props("unelevated no-caps").style(
                f"background:{MERK};color:{INKT};font-weight:700")

    with ui.column().classes("inhoud metbalk w-full gap-2"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label(f"Ontleden · {ref}").style(f"color:{ZACHT};font-size:13px")
            with ui.row().classes("items-center gap-2 no-wrap"):
                teller = ui.label().style(f"color:{ZACHT};font-size:13px")
                ui.button("⚙", on_click=instellingen.open, color=None).props("flat dense no-caps").classes(
                    "raakbaar").style(
                    f"color:{ZACHT};font-size:17px;min-width:32px")
        streepjes = ui.row().classes("w-full gap-1 no-wrap")
        vers = ui.html().classes("w-full").style("padding:6px 0")
        gevraagd = ui.label().classes("w-full text-center").style(
            f"color:{MERK};font-size:17px;font-weight:600;padding-top:4px")
        opties = ui.column().classes("keuzevak w-full gap-2").style("padding-top:4px")
        terugkoppeling = ui.column().classes("w-full items-center justify-center").style(
            "min-height:56px;padding-top:6px")
        hulpvak = ui.column().classes("w-full gap-1").style("padding-top:6px")

    with ui.element("div").classes("antwoordbalk"):
        knop = ui.button("Volgende", color=None).props("unelevated no-caps").classes("w-full").style(
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
                f"<div style='color:{ZACHT};font-size:13px;padding:4px 2px'>Op BibleHub: "
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
# Zonder de NT-tekst kun je niet ontleden, dus dan hoort 'verzen' ook nergens meer
# in beeld: niet als stip in de kalender en niet als doel dat je kunt instellen.
KALENDER_ONDERDELEN = ([("woorden_uniek", MERK, "woorden"), ("actief", "#f6c23e", "actief"),
                        ("stam", "#b07be0", "stamtijden"), ("struct", "#f6923c", "structuur")]
                       + ([("verzen", GOED, "ontleden")] if BIJBEL else [])
                       + [("verwar", "#20c997", "verwarparen")])
# (sleutel in het dagdoel, naam, hoogste instelbare waarde)
DAGDOEL_VELDEN = ([("woorden", "Woorden", 40), ("actief", "Actief beheersen", 30),
                   ("stam", "Stamtijden", 20), ("struct", "Structuurwoorden", 20)]
                  + ([("verzen", "Woorden ontleden", 20)] if BIJBEL else [])
                  + [("verwar", "Verwarparen", 15)])
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
    kop = "".join(f"<div style='text-align:center;font-size:12.5px;color:{ZACHT}'>{d}</div>"
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
            f"<div style='position:absolute;top:3px;left:5px;font-size:12.5px;font-weight:600;"
            f"color:#aeb6c0;line-height:1'>{d.day}</div>{aantal}"
            f"<div style='text-align:center;min-height:9px'>{stippen}</div></div>")
    legenda = " · ".join(f"<span style='color:{kleur}'>●</span> {naam}"
                         for _v, kleur, naam in KALENDER_ONDERDELEN)
    return (f"<div style='display:grid;grid-template-columns:repeat(7,1fr);gap:4px;"
            f"margin-bottom:6px'>{kop}</div>"
            f"<div style='display:grid;grid-template-columns:repeat(7,1fr);gap:4px'>{cellen}</div>"
            f"<div style='font-size:12.5px;color:{ZACHT};margin-top:8px;line-height:1.8'>"
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
    """De regels van het Scorebord-tabblad omzetten naar spelers.

    Ontdubbelen gaat op de naam zónder hoofdletters: wie zich de ene keer als 'Bob' en
    de andere keer als 'bob' aanmeldde stond anders twee keer in de lijst. Van elk paar
    houden we de regel met de meeste XP — dat is de verste voortgang."""
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
        sleutel = naam.lower()
        if sleutel not in spelers or speler["xp"] > spelers[sleutel]["xp"]:
            spelers[sleutel] = speler
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
                   f"<div style='color:{kleur};font-size:12.5px;font-weight:600;"
                   f"line-height:1.3;margin-top:2px'>{b['titel']}</div>"
                   f"<div style='color:{ZACHT};font-size:12.5px'>{onder}</div></div>")
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
        blokken += (f"<div style='color:{ZACHT};font-size:12.5px;margin:-6px 0 12px'>"
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
            f"<div style='color:{ZACHT};font-size:13px;overflow:hidden;white-space:nowrap;"
            f"text-overflow:ellipsis'>{str(w.get('nederlands',''))[:40]}</div></div>"
            f"<div style='text-align:right;white-space:nowrap'>"
            f"<span style='color:{FOUT};font-size:13px;font-weight:600'>"
            f"{int(deel * 100)}% fout</span>"
            f"<div style='color:{ZACHT};font-size:12.5px'>"
            f"{int(w.get('score_goed', 0) or 0)} goed · {fout} fout · "
            f"streak {int(w.get('streak', 0) or 0)}</div></div></div>")
    return regels


def _prognoseblok(prognose, woorden, doel_streak):
    """De uitkomst van de planner: verdeling nu, en wanneer je klaar bent."""
    fasen = _fasen_van(w.get("streak", 0) for w in woorden)
    verdeling = (f"<div style='color:{ZACHT};font-size:13px;margin-bottom:10px'>"
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
            f"<div style='color:{ZACHT};font-size:12.5px;letter-spacing:.6px;"
            f"text-transform:uppercase'>Verwachte afrondingsdatum</div>"
            f"<div style='color:{MERK};font-size:28px;font-weight:800;margin:2px 0 8px'>"
            f"{prognose['einddatum']}</div>"
            f"<div style='color:{TEKST};font-size:13.5px'>Doorlooptijd "
            f"{prognose['dagen']} dagen.</div>"
            f"<div style='color:{ZACHT};font-size:13px;margin-top:8px'>"
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
                   f"<div style='color:{ZACHT};font-size:12.5px'>deze week</div></div>")
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
                   f"<div style='color:{ZACHT};font-size:12.5px'>niveau "
                   f"{speler['niveau']} · {speler['titel']}</div></div>"
                   f"<div style='text-align:right;white-space:nowrap'>{speler['xp']} XP"
                   f"<div style='color:{ZACHT};font-size:12.5px'>🏅 {speler['badges']} · "
                   f"{speler['beheerst']} beheerst</div></div></div>")
    return kop + regels


def _uitklap(titel):
    """Uitklapper in de huisstijl van de kaarten."""
    return ui.expansion(titel).classes("kaart w-full").props("dense expand-separator").style(
        f"color:{TEKST}")


def heb_voortgangpagina(g):
    """Voortgang als de app op Hebreeuws staat.

    Bewust een eigen pagina en niet de Griekse met andere getallen erin: het Grieks heeft
    XP, levels en een leerpad, en die bestaan hier niet. Wat hier wél is en bij het Grieks
    niet, is precies hoe vaak elk woord in de Tenach staat — en dat maakt één getal
    mogelijk dat alle andere overtreft: hoeveel van de tekst je nu kunt lezen."""
    sam = heb_samenvatting(g)
    pct = hebreeuws.dekking(g.hebreeuws)
    doelen = g.dagdoel()
    fasen = {"Nieuw": 0, "In training": 0, "Beheerst": 0, "Mastery": 0}
    for w in g.hebreeuws:
        fasen[gebruikers.fase_van(w.get("streak", 0))] += 1
    per_les = {}
    for w in g.hebreeuws:
        les = int(w.get("les", 0) or 0)
        vak = per_les.setdefault(les, {"totaal": 0, "geoefend": 0, "beheerst": 0})
        vak["totaal"] += 1
        if int(w.get("score_goed", 0)) or int(w.get("score_fout", 0)):
            vak["geoefend"] += 1
        if int(w.get("streak", 0)) >= 16:
            vak["beheerst"] += 1

    with ui.column().classes("inhoud w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Voortgang").style("font-size:26px;font-weight:700")
            taalknop(g, "/voortgang")

        with ui.element("div").classes("kaart w-full"):
            ui.label(f"{pct}% van de Tenach").style(
                f"color:{MERK};font-size:24px;font-weight:700")
            ui.label("Zoveel van alle woorden in de Hebreeuwse bijbel ken je nu — "
                     "geteld naar hoe vaak ze er staan, niet hoeveel het er zijn.").style(
                f"color:{ZACHT};font-size:13px;line-height:1.5")
            # De hele lijst dekt zeventig procent; dat is dus de bovengrens van deze balk,
            # en zo blijft het eerlijk: honderd procent haal je met deze 410 woorden niet.
            deel = min(1.0, pct / 70.1)
            ui.html(f"<div style='width:100%;height:6px;border-radius:3px;background:{RAND};"
                    f"margin:10px 0 6px'><div style='width:{deel*100:.0f}%;height:6px;"
                    f"border-radius:3px;background:{MERK}'></div></div>")
            ui.label(f"De hele lijst van {sam['totaal']} woorden brengt je op 70%.").style(
                f"color:{TEKST};font-size:13px")

        tegels = [(sam["geoefend"], "gehad"), (sam["beheerst"], "beheerst"),
                  (heb_vandaag(g), "vandaag"),
                  (f"{int(doelen.get('hebreeuws', 10) or 10)}", "dagdoel")]
        with ui.row().classes("w-full gap-2 no-wrap"):
            for waarde, label in tegels:
                with ui.element("div").classes("kaart").style("flex:1;padding:10px 6px"):
                    ui.label(str(waarde)).style(
                        f"color:{MERK};font-size:19px;font-weight:700;text-align:center")
                    ui.label(label).style(
                        f"color:{ZACHT};font-size:11.5px;text-align:center")

        ui.label("Hoe ver elk woord is").style("font-size:15px;font-weight:700;margin-top:6px")
        with ui.element("div").classes("kaart w-full"):
            for naam, aantal in fasen.items():
                breed = 100 * aantal / max(1, sam["totaal"])
                ui.html(
                    f"<div style='display:flex;justify-content:space-between;font-size:13px;"
                    f"color:{TEKST}'><span>{naam}</span><span style='color:{ZACHT}'>"
                    f"{aantal}</span></div>"
                    f"<div style='width:100%;height:5px;border-radius:3px;background:{RAND};"
                    f"margin:3px 0 9px'><div style='width:{breed:.0f}%;height:5px;"
                    f"border-radius:3px;background:{MERK}'></div></div>")

        cellen = heb_af_cellen(g) if hebreeuws.laad_rijtjes() else []
        if cellen:
            af_gehad = sum(1 for c in cellen if c["goed"] or c["fout"])
            af_vast = sum(1 for c in cellen if c["streak"] >= 5)
            rijtjes = {(c["categorie"], c["paradigma"]) for c in cellen}
            ui.label("Rijtjes").style("font-size:15px;font-weight:700;margin-top:6px")
            with ui.element("div").classes("kaart w-full").on(
                    "click", lambda: ui.navigate.to("/oefenen/hebreeuws/actief")):
                with ui.row().classes("w-full items-center justify-between no-wrap"):
                    ui.label(f"{len(rijtjes)} rijtjes · {len(cellen)} cellen").style(
                        f"color:{TEKST};font-size:14px")
                    ui.label(f"{af_gehad} gehad").style(f"color:{MERK};font-size:13px")
                ui.label(f"{af_vast} cellen zitten vast (streak 5 of hoger).").style(
                    f"color:{ZACHT};font-size:12.5px")

        ui.label("Per woordenlijst").style("font-size:15px;font-weight:700;margin-top:6px")
        for les in sorted(per_les):
            vak = per_les[les]
            naam = {1: "Hebreeuws 1 · woord 1–165",
                    2: "Hebreeuws 2 · woord 166–410"}.get(les, f"Lijst {les}")
            with ui.element("div").classes("kaart w-full"):
                with ui.row().classes("w-full items-center justify-between no-wrap"):
                    ui.label(naam).style(f"color:{TEKST};font-size:14px")
                    ui.label(f"{vak['geoefend']}/{vak['totaal']}").style(
                        f"color:{MERK};font-size:13px")
                ui.label(f"{vak['beheerst']} beheerst").style(
                    f"color:{ZACHT};font-size:12.5px")

        # De woorden waar je het vaakst op struikelt, maar alleen als je ze ook echt hebt
        # gehad: een lijst met woorden die je nog nooit zag zegt niets over je zwakke plek.
        zwak = sorted((w for w in g.hebreeuws if int(w.get("score_fout", 0))),
                      key=lambda w: (-int(w.get("score_fout", 0)), int(w.get("streak", 0))))[:8]
        if zwak:
            ui.label("Waar het misgaat").style("font-size:15px;font-weight:700;margin-top:6px")
            with ui.element("div").classes("kaart w-full"):
                ui.html("".join(
                    f"<div style='display:flex;justify-content:space-between;gap:10px;"
                    f"padding:3px 0;font-size:13.5px'>"
                    f"<span><span class='hebreeuws' style='font-size:18px'>"
                    f"{w['hebreeuws']}</span> <span style='color:{ZACHT}'>"
                    f"{heb_betekenis(w)}</span></span>"
                    f"<span style='color:{FOUT};white-space:nowrap'>"
                    f"{int(w.get('score_fout', 0))}×</span></div>" for w in zwak))
    onderbalk("Voortgang")


@ui.page("/voortgang")
def voortgangpagina():
    g = _bewaakt()
    if not g:
        return
    if taal(g) == HEBREEUWS:
        heb_voortgangpagina(g)
        return
    sam = g.samenvatting()
    cijfers = voortgang_cijfers(g)
    xp = motor.bereken_xp(g.woorden)
    niv = motor.niveau_van_xp(xp)
    doelen = g.dagdoel()
    dagboek = (g.stats.get("dagdoel") or {}).get("log") or {}
    vandaag_log = dagboek.get(gebruikers.vandaag()) or {}

    with ui.column().classes("inhoud w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Voortgang").style("font-size:26px;font-weight:700")
            taalknop(g, "/voortgang")

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
                        ui.label(label).style(f"color:{ZACHT};font-size:12.5px")

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
                f"color:{ZACHT};font-size:13px;margin:6px 0")

            async def bewaar_doelen():
                g.zet_dagdoel({s: (v.value or 0) for s, v in schuiven.items()})
                await run.io_bound(g.bewaar, True)
                ui.notify("Dagdoelen opgeslagen", position="top", color="dark")
                ui.navigate.to("/voortgang")

            ui.button("Doelen opslaan", on_click=bewaar_doelen, color=None).props("unelevated no-caps").style(
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

        # De lichte versie houdt Voortgang kort: hoeveel je hebt geoefend, en de
        # competitie. Badges, voortgang per onderdeel, probleemwoorden, de
        # studieplanner en de export staan in de uitgebreide app, die daar de ruimte
        # voor heeft. Zo blijft dit scherm op een telefoon te overzien.
        if BIJBEL:
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
                    f"color:{ZACHT};font-size:13px;margin-bottom:6px")
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
                        f"color:{ZACHT};font-size:13px;margin-bottom:6px")
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
                            f"color:{ZACHT};font-size:13px;margin-top:6px")

            # --- studieplanner -----------------------------------------------------
            with _uitklap("Studieplanner — wanneer ken ik alles?"):
                tempo = gemiddeld_tempo(g)
                kies_groep = ui.select({naam: f"{naam} · {lessen}" for naam, lessen, _b in TENTAMENS},
                                       value=TENTAMENS[0][0], label="Tentamen").props(
                    "outlined dark dense").classes("w-full")
                kies_diepte = ui.number("Gewenste kennis-diepte (streak)", value=16, min=2, max=30,
                                        step=1).props("outlined dark dense").classes("w-full")
                ui.label("16 = beheerst (de norm). 8 = genoeg om te herkennen in een tekst. "
                         "30 = vloeiend.").style(f"color:{ZACHT};font-size:13px")
                kies_tempo = ui.number("Woorden per dag", value=max(5, tempo) if tempo else 30,
                                       min=5, max=500, step=5).props(
                    "outlined dark dense").classes("w-full")
                if tempo:
                    ui.label(f"Je tempo van de afgelopen twee weken: ongeveer {tempo} items per "
                             f"dag. Pas gerust aan.").style(f"color:{ZACHT};font-size:13px")
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
            ui.button("Ranglijst verversen", on_click=laad_bord, color=None).props("flat no-caps").style(
                f"color:{MERK};border:1px solid {RAND};border-radius:8px;width:100%")

        if not BIJBEL:
            # In de lichte versie is dit het enige uitklapblok op een korte pagina, dus
            # daar mag hij meteen openstaan en zichzelf ophalen.
            competitie.value = True
            ui.timer(0.2, laad_bord, once=True)

        if BIJBEL:
            # --- export ------------------------------------------------------------
            ui.button("Woordenschat downloaden als CSV",
                      on_click=lambda: ui.download.content(
                          voortgang_csv(g), "mijn_grieks_voortgang.csv"), color=None).props("flat no-caps").style(
                f"color:{MERK};border:1px solid {RAND};border-radius:10px")

        else:
            with ui.element("div").classes("kaart w-full"):
                ui.label("Meer overzichten").style(f"color:{TEKST};font-size:15px;font-weight:600")
                ui.label("De studieplanner per tentamen, de aartsrivalen en alle grafieken "
                         "staan in de volledige app.").style(
                    f"color:{ZACHT};font-size:13px;line-height:1.5")
                streamlit_link(g)

        ui.button("Uitloggen", on_click=lambda: (
            _sessies.pop(app.storage.user.get("sleutel"), None),
            app.storage.user.clear(), ui.navigate.to("/")), color=None).props("flat no-caps").style(
            f"color:{ZACHT};border:1px solid {RAND};border-radius:10px;margin-top:8px")
    onderbalk("Voortgang")


# ============================================================== lijst
LIJST_SOORTEN = ["Woordenschat", "Mijn verwarwoorden", "Structuurwoorden", "Stamtijden"]
# Staat de app op Hebreeuws, dan hoort de Griekse woordenschat hier niet: die lijsten gaan
# over de andere taal. Wat blijft is de Hebreeuwse woordenlijst en de rijtjes.
LIJST_SOORTEN_HEB = ["Hebreeuwse woorden", "Rijtjes"]
LIJST_MAX = 200          # zoveel regels tegelijk; meer maakt de pagina onbruikbaar traag


def _lijstregel(links, rechts, onder="", kleur=None):
    return (f"<div style='display:flex;justify-content:space-between;gap:10px;"
            f"border-top:1px solid {RAND};padding:7px 0'>"
            f"<div style='min-width:0'>{links}"
            f"{f'<div style=\"color:{ZACHT};font-size:12.5px\">{onder}</div>' if onder else ''}"
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


def lijst_heb_rijtjes(g, zoek):
    """De vervoegingsrijtjes om op te zoeken: per rijtje één regel met hoeveel cellen je
    al vast hebt."""
    per = {}
    for c in heb_af_cellen(g):
        per.setdefault((c["categorie"], c["paradigma"]), []).append(c)
    regels = []
    for (categorie, paradigma), cellen in per.items():
        if zoek and zoek not in paradigma.lower() and zoek not in categorie.lower() \
                and zoek not in paradigma:
            continue
        vast = sum(1 for c in cellen if c["streak"] >= 5)
        regels.append(_lijstregel(
            f"<span class='hebreeuws' style='font-size:17px;color:{TEKST}'>"
            f"{paradigma.split(' — ')[0]}</span>"
            f"<span style='color:{ZACHT};font-size:13px'> "
            f"{paradigma.split(' — ')[-1]}</span>",
            f"{vast}/{len(cellen)}", categorie,
            MERK if vast == len(cellen) else (TEKST if vast else ZACHT)))
    return regels


def lijst_hebreeuws(g, zoek, alleen_geoefend):
    """De Hebreeuwse woorden om op te zoeken. Zelfde opmaak als de Griekse lijst, maar met
    de frequentie erbij: bij het Hebreeuws is dat het getal dat zegt hoe hard een woord
    loont om te kennen."""
    regels = []
    for w in g.hebreeuws:
        heb = str(w.get("hebreeuws", ""))
        ned = heb_uitleg(w)
        if zoek and zoek not in heb and zoek not in ned.lower() \
                and zoek not in str(w.get("translit", "")).lower():
            continue
        streak = int(w.get("streak", 0) or 0)
        goed = int(w.get("score_goed", 0) or 0)
        fout = int(w.get("score_fout", 0) or 0)
        if alleen_geoefend and not (goed or fout or streak):
            continue
        fase = gebruikers.fase_van(streak)
        freq = int(w.get("frequentie", 0) or 0)
        onder = f"{heb_betekenis(w)} · lijst {w.get('les', '?')}"
        if freq:
            onder += f" · {freq}×"
        regels.append(_lijstregel(
            f"<span class='hebreeuws' style='font-size:19px;color:{TEKST}'>{heb}</span>",
            f"streak {streak}", onder,
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
        kaal, naamval = sw_naamval(w)
        grieks = kaal + (f" <span style='color:{MERK};font-size:13px'>+ {naamval}</span>"
                         if naamval else "")
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
        delen.append(f"<div style='color:{MERK};font-size:12.5px'>{kop}</div>")
    if morf.get("memoriseren_vereist"):
        delen.append(f"<div style='color:{FOUT};font-size:12.5px'>🔥 onregelmatig — "
                     f"deze moet je uit je hoofd leren</div>")
    if regel.get("formule"):
        delen.append(f"<div style='color:{ZACHT};font-size:12.5px'>{regel['formule']}</div>")
    if regel.get("toelichting"):
        delen.append(f"<div style='color:{ZACHT};font-size:12.5px;font-style:italic'>"
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
        heb = taal(g) == HEBREEUWS
        soorten = LIJST_SOORTEN_HEB if heb else LIJST_SOORTEN
        kies = ui.select(soorten, value=soorten[0], label="Wat wil je zien").props(
            "outlined dark dense").classes("w-full")
        zoekveld = ui.input(placeholder="zoek op Hebreeuws of Nederlands" if heb
                            else "zoek op Grieks of Nederlands").props(
            "outlined dense dark clearable autocomplete=off").classes("w-full")
        alleen = ui.switch("Alleen wat ik al geoefend heb", value=False)
        for veld in (zoekveld, alleen):
            veld.bind_visibility_from(kies, "value", lambda v: v != "Mijn verwarwoorden")
        kop = ui.label().style(f"color:{ZACHT};font-size:12.5px")
        inhoud = ui.element("div").classes("kaart w-full")

        def teken():
            zoek = str(zoekveld.value or "").strip().lower()
            soort = kies.value
            if soort == "Hebreeuwse woorden":
                regels = lijst_hebreeuws(g, zoek, bool(alleen.value))
                leeg = "Niets gevonden."
            elif soort == "Rijtjes":
                regels, leeg = lijst_heb_rijtjes(g, zoek), "Niets gevonden."
            elif soort == "Mijn verwarwoorden":
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


# ============================================================== Hebreeuws · voor/achtervoegsels
# Bijna de helft van alle woordvormen in de Tenach draagt een voorvoegsel. Wie die niet
# herkent, ziet in וְהָאָרֶץ een woord dat hij nooit geleerd heeft — terwijl er gewoon אֶרֶץ
# staat met 'en' en 'de' ervoor. Daarom een eigen oefening.
#
# Herkennen, niet produceren: je krijgt een echte vorm uit de bijbeltekst en zegt wat het
# voor- of achtervoegsel betekent. Zelf zo'n vorm bouwen is een andere vaardigheid, en die
# hoort bij Actief Beheersen.
#
# De vragen komen uit de verzen die er al zijn — geen nieuw bestand, en elke vorm die je
# krijgt staat écht ergens. De score gaat per soort voorvoegsel: er zijn er zeventien in
# totaal, dus dan zie je precies welke je nog niet vast hebt.
AF_STANDAARD_HEB = {"heb_af2_aantal": 12, "heb_af2_soort": "Allebei"}
HEB_AFFIX_SOORT = ["Allebei", "Alleen voorvoegsels", "Alleen achtervoegsels"]
HEB_AFFIX_SLEUTEL = "affix:"


def heb_affix_vragen(g, hoeveel, soort):
    """Vormen uit de verzen die een voor- of achtervoegsel hebben, zwakste soort eerst.

    Per soort houden we de score bij, en de soorten die je het slechtst kent komen als
    eerste aan de beurt — zo besteed je je tijd waar het nodig is."""
    verzen = hebreeuws.laad_verzen()
    if not verzen:
        return []
    stats = g.stats.get("hebr_stats") or {}

    def streak(code):
        return int((stats.get(HEB_AFFIX_SLEUTEL + code) or {}).get("streak", 0) or 0)

    per_code = {}
    for vers in verzen:
        for wv in hebreeuws.woorden_van(vers):
            vorm, parsing = wv["vorm"], wv["parsing"]
            voor_codes, _kern, achter = hebreeuws._codes(parsing)
            voorvoegsel, kern, achtervoegsel = hebreeuws.splits_affixen(vorm, parsing)
            if soort != "Alleen achtervoegsels" and voor_codes and voorvoegsel:
                # Alleen het eerste voorvoegsel bevragen: bij twee tegelijk weet je niet
                # welke van de twee de vraag bedoelt.
                if len(voor_codes) == 1:
                    per_code.setdefault(voor_codes[0], []).append(
                        (vorm, parsing, vers["vers"], voor_codes[0], "voor"))
            if soort != "Alleen voorvoegsels" and achter and achtervoegsel:
                per_code.setdefault(achter, []).append(
                    (vorm, parsing, vers["vers"], achter, "achter"))
    if not per_code:
        return []
    # Eén vraag per soort per ronde, en de zwakste soorten eerst. Anders krijg je twaalf
    # keer een waw, want die is verreweg het talrijkst.
    volgorde = sorted(per_code, key=lambda c: (streak(c), -len(per_code[c])))
    vragen = []
    ronde = 0
    while len(vragen) < hoeveel and ronde < 6:
        for code in volgorde:
            if len(vragen) >= hoeveel:
                break
            if len(per_code[code]) > ronde:
                vragen.append(random.choice(per_code[code]))
        ronde += 1
    return vragen[:hoeveel]


def heb_affix_betekenis(code):
    return (hebreeuws.VOORVOEGSEL_NL.get(code)
            or hebreeuws.ACHTERVOEGSEL_NL.get(code) or code)


class HebAffixSessie:
    def __init__(self, g):
        p = {k: (g.stats.get("ui_prefs") or {}).get(f"ng_{k}", v)
             for k, v in AF_STANDAARD_HEB.items()}
        self.prefs = p
        self.vragen = heb_affix_vragen(g, max(4, int(p["heb_af2_aantal"] or 12)),
                                       p["heb_af2_soort"])
        self.i = 0
        self.goed = 0
        self.fout = 0
        self.beoordeeld = False
        self.bezig = False

    @property
    def huidig(self):
        return self.vragen[self.i] if self.i < len(self.vragen) else None


@ui.page("/oefenen/hebreeuws/affixen")
def hebaffixpagina():
    g = _bewaakt()
    if not g:
        return
    sessie = HebAffixSessie(g)
    if not sessie.vragen:
        ui.navigate.to("/oefenen")
        return
    stats = g.stats.setdefault("hebr_stats", {})

    with ui.dialog() as instellingen, ui.card().style(
            f"background:{VLAK};color:{TEKST};min-width:300px;max-width:92vw"):
        ui.label("Instellingen").style("font-size:18px;font-weight:700")
        k_soort = ui.select(HEB_AFFIX_SOORT, value=sessie.prefs["heb_af2_soort"],
                            label="Wat wil je oefenen").props(
            "outlined dark").classes("w-full")
        k_aantal = ui.number("Vragen per ronde", value=int(sessie.prefs["heb_af2_aantal"]),
                             min=4, max=40, step=1).props("outlined dark").classes("w-full")
        ui.label("Elke vorm komt uit een vers dat in de app staat, dus wat je hier ziet "
                 "staat écht ergens.").style(f"color:{ZACHT};font-size:13px")

        async def bewaar_inst():
            for sleutel, veld in [("heb_af2_soort", k_soort), ("heb_af2_aantal", k_aantal)]:
                g.stats.setdefault("ui_prefs", {})[f"ng_{sleutel}"] = veld.value
            instellingen.close()
            await run.io_bound(g.bewaar, True)
            ui.navigate.to("/oefenen/hebreeuws/affixen")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Annuleren", on_click=instellingen.close, color=None).props(
                "flat no-caps").style(f"color:{ZACHT}")
            ui.button("Toepassen", on_click=bewaar_inst, color=None).props(
                "unelevated no-caps").style(
                f"background:{MERK};color:{INKT};font-weight:700")

    with ui.column().classes("inhoud metbalk w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Voor- en achtervoegsels").style(f"color:{ZACHT};font-size:13px")
            with ui.row().classes("items-center gap-2 no-wrap"):
                teller = ui.label().style(f"color:{ZACHT};font-size:13px")
                ui.button("⚙", on_click=instellingen.open, color=None).props(
                    "flat dense no-caps").classes("raakbaar").style(
                    f"color:{ZACHT};font-size:17px;min-width:32px")
        streepjes = ui.row().classes("w-full gap-1 no-wrap")
        woord = ui.html().classes("w-full text-center").style("padding:8px 0 2px")
        herkomst = ui.label().classes("w-full text-center").style(
            f"color:{ZACHT};font-size:12.5px")
        vraagsoort = ui.label().classes("w-full text-center").style(
            f"color:{ZACHT};font-size:13px;padding-top:6px")
        opties = ui.column().classes("keuzevak w-full gap-2").style("padding-top:6px")
        statusbalk = ui.row().classes("w-full").style("padding-top:2px")
        terugkoppeling = ui.column().classes("w-full items-center justify-center").style(
            "min-height:64px;padding-top:8px")
        opslagmelding = ui.label().style(f"color:{ZACHT};font-size:12.5px;min-height:16px")

    balkje = ui.element("div").classes("antwoordbalk")
    with balkje:
        with ui.row().classes("w-full gap-2 no-wrap items-center justify-end"):
            knop = ui.button("Ik weet het niet", color=None).props(
                "unelevated no-caps").style(
                f"background:{MERK};color:{INKT};font-weight:700;height:40px;"
                f"width:132px;min-width:132px;font-size:14px")
    onderbalk("Oefenen")

    def teken():
        streepjes.clear()
        with streepjes:
            for n in range(len(sessie.vragen)):
                kleur = MERK if n < sessie.i else (TEKST if n == sessie.i else RAND)
                ui.element("div").style(
                    f"flex:1;height:4px;border-radius:2px;background:{kleur}")

    def toon():
        for vak in (opties, terugkoppeling, statusbalk):
            vak.clear()
        sessie.beoordeeld = False
        vraag = sessie.huidig
        for vak in (woord, herkomst, vraagsoort, opties, statusbalk):
            vak.set_visibility(True)
        if vraag is None:
            woord.set_content(f"<span style='font-size:46px;color:{TEKST}'>✓</span>")
            herkomst.text = ""
            vraagsoort.text = f"Klaar — {sessie.goed} goed, {sessie.fout} fout."
            teller.text = ""
            knop.text = "Nieuwe ronde"
            teken()
            return
        vorm, parsing, vers, code, soort = vraag
        # De vorm mét kleur: het stuk waar de vraag over gaat is meteen aangewezen. Dat is
        # de bedoeling — je moet niet zoeken wélke letter, maar weten wát hij doet.
        woord.set_content(heb_gekleurd(vorm, parsing, maat=44))
        herkomst.text = vers
        vraagsoort.text = ("Wat betekent het gekleurde voorvoegsel?" if soort == "voor"
                           else "Wat betekent het gekleurde achtervoegsel?")
        teller.text = f"{sessie.i + 1}/{len(sessie.vragen)}"
        knop.text = "Ik weet het niet"
        teken()
        juist = heb_affix_betekenis(code)
        bron = (hebreeuws.VOORVOEGSEL_NL if soort == "voor"
                else hebreeuws.ACHTERVOEGSEL_NL)
        anderen = [v for k, v in bron.items() if v != juist]
        keuzes = random.sample(anderen, min(3, len(anderen))) + [juist]
        random.shuffle(keuzes)
        with opties:
            for keuze in keuzes:
                ui.html(f"<button class='keuze' style='font-size:14.5px;"
                        f"padding:9px 12px;line-height:1.35'>{keuze}</button>").on(
                    "click", lambda _=None, kz=keuze: kies(kz))
        e = stats.get(HEB_AFFIX_SLEUTEL + code) or {}
        with statusbalk:
            ui.html(_statusrij([
                (int(e.get("streak", 0) or 0), "streak", TEKST),
                (_goedfout(int(e.get("g", 0) or 0), int(e.get("f", 0) or 0)), "", TEKST),
                (len(sessie.vragen) - sessie.i - 1, "te gaan", ZACHT),
            ]))

    async def verwerk(juist, aangeklikt=None):
        vorm, parsing, vers, code, soort = sessie.huidig
        sessie.beoordeeld = True
        sessie.goed += int(juist)
        sessie.fout += int(not juist)
        e = stats.setdefault(HEB_AFFIX_SLEUTEL + code, {"g": 0, "f": 0, "streak": 0})
        e["g"] = int(e.get("g", 0)) + int(juist)
        e["f"] = int(e.get("f", 0)) + int(not juist)
        e["streak"] = int(e.get("streak", 0)) + 1 if juist else 0
        g.tel_dag()
        if juist:
            g.dagdoel_plus("hebreeuws")
        opgeslagen = await run.io_bound(g.bewaar)
        for vak in (woord, herkomst, vraagsoort, opties, statusbalk):
            vak.set_visibility(False)
        letter = (hebreeuws.VOORVOEGSEL_LETTER.get(code, "") if soort == "voor" else "")
        kleur = GOED if juist else FOUT
        achter = "rgba(61,220,151,.10)" if juist else "rgba(255,107,129,.10)"
        gekozen = (f"<div style='color:{ZACHT};font-size:13px;margin-top:8px'>"
                   f"jij koos <span style='color:{FOUT}'>{aangeklikt}</span></div>"
                   if not juist and aangeklikt else "")
        terugkoppeling.clear()
        with terugkoppeling:
            ui.html(
                f"<div style='background:{achter};border:1px solid {kleur}40;"
                f"border-radius:16px;padding:22px 18px;text-align:center;width:100%'>"
                f"<div style='color:{kleur};font-weight:700;font-size:19px'>"
                f"{'✓ Goed!' if juist else '✗ Niet goed'}</div>"
                f"<div style='font-size:38px;margin-top:12px;line-height:1.3'>"
                f"{heb_gekleurd(vorm, parsing)}</div>"
                + (f"<div class='hebreeuws' style='color:{MERK};font-size:24px;"
                   f"margin-top:6px'>{letter}</div>" if letter else "")
                + f"<div style='color:{TEKST};font-size:17px;margin-top:4px'>"
                  f"{heb_affix_betekenis(code)}</div>"
                  f"<div style='color:{ZACHT};font-size:12.5px;margin-top:6px'>{vers}</div>"
                + gekozen
                + f"<div style='color:{ZACHT};font-size:12.5px;margin-top:14px'>"
                  f"{sessie.goed} goed · {sessie.fout} fout in deze ronde · "
                  f"streak nu {e['streak']}</div></div>")
        if opgeslagen:
            opslagmelding.text = "Voortgang opgeslagen"
        knop.text = "Volgende"
        _uitslag_staat(sessie)

    async def kies(keuze):
        if sessie.beoordeeld or sessie.bezig:
            return
        sessie.bezig = True
        try:
            _v, _p, _r, code, _s = sessie.huidig
            await verwerk(keuze == heb_affix_betekenis(code), keuze)
        finally:
            sessie.bezig = False

    async def hoofdknop():
        if sessie.bezig:
            return
        sessie.bezig = True
        try:
            if sessie.huidig is None:
                await run.io_bound(g.bewaar, True)
                ui.navigate.to("/oefenen/hebreeuws/affixen")
                return
            if sessie.beoordeeld:
                if te_snel(sessie):
                    return
                sessie.i += 1
                toon()
                return
            await verwerk(False)
        finally:
            sessie.bezig = False

    knop.on_click(hoofdknop)
    toon()


# ============================================================== Tenach · een tekst oefenen
# Andersom werken dan de woordenlijst. Niet 'leer deze 428 woorden en dan kun je lezen',
# maar: kies het hoofdstuk dat je aanstaande week moet kennen, en de app zoekt uit welke
# woorden daarin nog niet zitten. Die zet hij vooraan in je woordenschat.
#
# Dat kan omdat elk woord in de tekst zijn Strong-nummer bij zich heeft en de woordenlijst
# ook. Wat overblijft na het aftrekken is precies wat je nog mist — en met de frequentie
# erbij weet je meteen welke daarvan het hardst lonen.
#
# De gekozen woorden komen in ui_prefs terecht en niet in de statistieken: het is een
# keuze, geen voortgang. Zo staat hij ook in de Streamlit-app als je daar inlogt.
TEKST_SLEUTEL = "ng_heb_tekst"          # welk hoofdstuk je hebt gekozen
TEKST_WOORDEN = "ng_heb_tekstwoorden"   # de Strong-nummers eruit die je wil leren


def heb_tekst_keuze(g):
    """Wat er nu gekozen staat: (beschrijving, lijst met Strong-nummers)."""
    p = g.stats.get("ui_prefs") or {}
    woorden = p.get(TEKST_WOORDEN) or []
    return str(p.get(TEKST_SLEUTEL, "") or ""), [str(s) for s in woorden]


def heb_tekst_analyse(g, boek, hoofdstuk):
    """Wat staat er in dit hoofdstuk, en wat ken je ervan?

    Geeft per Strong-nummer terug hoe vaak het in dít hoofdstuk staat, met het woord uit de
    lijst erbij als het erin staat. Zo is in één oogopslag te zien wat je mist."""
    verzen = [v for v in hebreeuws.laad_tenach_boek(boek["bestand"])
              if v["v"].split(":")[0] == str(hoofdstuk)]
    info = heb_woordinfo(g)
    hier = {}
    for v in verzen:
        for w in hebreeuws.woorden_van(v):
            strong = w["strong"]
            if not strong:
                continue
            vak = hier.setdefault(strong, {"aantal": 0, "woord": info.get(strong)})
            vak["aantal"] += 1
    kent, mist = [], []
    for strong, vak in hier.items():
        w = vak["woord"]
        if w is not None and (int(w.get("streak", 0) or 0)
                              or int(w.get("score_goed", 0) or 0)):
            kent.append((strong, vak))
        else:
            mist.append((strong, vak))
    # Wat je mist, eerst de woorden die je vaker in dit hoofdstuk tegenkomt: die leveren
    # het meeste op voor deze tekst.
    mist.sort(key=lambda p: (-p[1]["aantal"],
                             -int((p[1]["woord"] or {}).get("frequentie", 0) or 0)))
    return verzen, kent, mist


@ui.page("/tenach/oefenen")
def tenachoefenpagina():
    g = _bewaakt()
    if not g:
        return
    boeken = hebreeuws.tenach_index()
    if not boeken:
        ui.navigate.to("/lezen")
        return
    op_naam = {b["nl"]: b for b in boeken}
    gekozen_naam, _woorden = heb_tekst_keuze(g)
    staat = {"boek": boeken[0]["nl"], "hoofdstuk": 1}

    with ui.column().classes("inhoud w-full gap-2"):
        ui.label("Een tekst oefenen").style("font-size:26px;font-weight:700")
        ui.label("Kies het hoofdstuk dat je moet kennen. De app zoekt uit welke woorden "
                 "daarin nog niet in je woordenschat zitten en zet die vooraan.").style(
            f"color:{ZACHT};font-size:13px;line-height:1.5")
        if gekozen_naam:
            with ui.element("div").classes("kaart w-full"):
                ui.label(f"Nu ingesteld: {gekozen_naam}").style(
                    f"color:{MERK};font-size:14px;font-weight:600")
                ui.label(f"{len(_woorden)} woorden uit die tekst staan vooraan in je "
                         f"woordenschat.").style(f"color:{ZACHT};font-size:12.5px")
                ui.button("Weer alle woorden", color=None,
                          on_click=lambda: wis()).props("flat dense no-caps").style(
                    f"color:{ZACHT};font-size:12.5px;padding:0")
        with ui.row().classes("w-full gap-2 no-wrap"):
            kies_boek = ui.select(list(op_naam), value=staat["boek"], label="Boek",
                                  with_input=True).props(
                "outlined dense dark").classes("flex-grow")
            kies_hfst = ui.select([1], value=1, label="Hoofdstuk").props(
                "outlined dense dark").style("width:116px;min-width:116px")
        overzicht = ui.column().classes("w-full gap-2")
    onderbalk("Lezen")

    async def wis():
        p = g.stats.setdefault("ui_prefs", {})
        p.pop(TEKST_SLEUTEL, None)
        p.pop(TEKST_WOORDEN, None)
        await run.io_bound(g.bewaar, True)
        ui.navigate.to("/tenach/oefenen")

    async def instellen(naam, strongs):
        p = g.stats.setdefault("ui_prefs", {})
        p[TEKST_SLEUTEL] = naam
        p[TEKST_WOORDEN] = strongs
        # De woordenschat werkt op blokjes; met een tekst ingesteld nemen we die volgorde
        # over, dus zet de oefening op 'Zwakste eerst' — anders zou het leerpad hem
        # overrulen en krijg je alsnog blokje 1.
        p["ng_heb_keuze"] = "Zwakste eerst"
        await run.io_bound(g.bewaar, True)
        ui.notify(f"{naam} ingesteld — {len(strongs)} woorden staan nu vooraan",
                  position="top", color="dark")
        ui.navigate.to("/oefenen/hebreeuws")

    def teken():
        overzicht.clear()
        boek = op_naam[staat["boek"]]
        verzen, kent, mist = heb_tekst_analyse(g, boek, staat["hoofdstuk"])
        naam = f"{staat['boek']} {staat['hoofdstuk']}"
        with overzicht:
            if not verzen:
                ui.label("Dat hoofdstuk bestaat niet in dit boek.").style(
                    f"color:{ZACHT};font-size:13px")
                return
            totaal = len(kent) + len(mist)
            in_lijst = [p for p in mist if p[1]["woord"] is not None]
            buiten = len(mist) - len(in_lijst)
            with ui.element("div").classes("kaart w-full"):
                ui.label(f"{naam}: {len(verzen)} verzen, {totaal} verschillende woorden").style(
                    f"color:{TEKST};font-size:14px;font-weight:600")
                ui.html(
                    f"<div style='font-size:13px;line-height:1.7;margin-top:4px'>"
                    f"<span style='color:{GOED}'>{len(kent)} ken je al</span> · "
                    f"<span style='color:{MERK}'>{len(in_lijst)} staan in je lijst maar "
                    f"heb je nog niet gehad</span> · "
                    f"<span style='color:{ZACHT}'>{buiten} staan niet in de lijst</span>"
                    f"</div>")
                if in_lijst:
                    ui.button(f"Deze {len(in_lijst)} vooraan zetten", color=None,
                              on_click=lambda: instellen(
                                  naam, [s for s, _v in in_lijst])).props(
                        "unelevated no-caps").style(
                        f"background:{MERK};color:{INKT};font-weight:700;"
                        f"margin-top:8px")
                else:
                    ui.label("Je hebt alle woorden uit dit hoofdstuk die in de lijst "
                             "staan al gehad.").style(f"color:{GOED};font-size:13px")
            if in_lijst:
                with ui.element("div").classes("kaart w-full"):
                    ui.label("Wat je nog niet had").style(
                        f"color:{ZACHT};font-size:12.5px;margin-bottom:4px")
                    ui.html("".join(
                        f"<div style='display:flex;justify-content:space-between;gap:10px;"
                        f"border-top:1px solid {RAND};padding:4px 0;font-size:13.5px'>"
                        f"<span><span class='hebreeuws' style='font-size:18px;"
                        f"color:{TEKST}'>{v['woord']['hebreeuws']}</span> "
                        f"<span style='color:{ZACHT}'>"
                        f"{heb_betekenis(v['woord'])}</span></span>"
                        f"<span style='color:{MERK};white-space:nowrap'>"
                        f"{v['aantal']}× hier</span></div>"
                        for _s, v in in_lijst[:30]))
                    if len(in_lijst) > 30:
                        ui.label(f"…en nog {len(in_lijst) - 30}.").style(
                            f"color:{ZACHT};font-size:12.5px")
            if buiten:
                with ui.element("div").classes("kaart w-full"):
                    ui.label(f"{buiten} woorden in dit hoofdstuk staan niet in de "
                             f"cursuslijst. Die kun je hier niet oefenen, maar bij het "
                             f"lezen zie je wel dat ze er zijn.").style(
                        f"color:{ZACHT};font-size:12.5px;line-height:1.5")

    def zet_hoofdstukken():
        boek = op_naam[staat["boek"]]
        kies_hfst.options = list(range(1, int(boek["hoofdstukken"]) + 1)) or [1]
        kies_hfst.update()

    def boek_gewisseld():
        staat["boek"] = kies_boek.value
        staat["hoofdstuk"] = 1
        zet_hoofdstukken()
        kies_hfst.value = 1
        teken()

    def hoofdstuk_gewisseld():
        staat["hoofdstuk"] = int(kies_hfst.value or 1)
        teken()

    kies_boek.on_value_change(lambda _=None: boek_gewisseld())
    kies_hfst.on_value_change(lambda _=None: hoofdstuk_gewisseld())
    zet_hoofdstukken()
    teken()


# ============================================================== Tenach doorbladeren
# De hele Hebreeuwse bijbel, 22.877 verzen: kies een boek en een hoofdstuk en lees. Elk
# woord is aan te tikken voor de betekenis, de ontleding en zijn voor- en achtervoegsels —
# dezelfde bouwstenen als bij het losse leesvers, maar dan met de tekst zelf als bron.
#
# Per boek één ingepakt bestand, en er worden er hoogstens twee tegelijk geladen. Gemeten:
# Psalmen is het grootste en kost 6,4 MB uitgepakt, twee boeken samen 12,7 MB. Alles
# tegelijk zou rond de 100 MB liggen, en op de gratis laag van Render is 512 MB alles wat
# er is — dus dat scheelt de app het verschil tussen werken en omvallen.
TENACH_MAX_VERZEN = 40      # zoveel verzen tegelijk; Psalm 119 heeft er 176


@ui.page("/tenach")
def tenachpagina():
    g = _bewaakt()
    if not g:
        return
    boeken = hebreeuws.tenach_index()
    if not boeken:
        ui.navigate.to("/lezen")
        return
    info = heb_woordinfo(g)
    op_naam = {b["nl"]: b for b in boeken}
    staat = {"boek": boeken[0]["nl"], "hoofdstuk": 1, "vanaf": 0, "open": set(),
             "verzen_aan": set(), "beurt": 0}
    # In welke volgorde de kaartjes staan: het laatst aangetikte woord vooraan. Zonder een
    # eigen teller zou het op vers-en-woordnummer gaan, en dan verschuift het kaartje dat
    # je net opende naar het midden.
    volgorde = {}

    def _leesorde(sleutel):
        return volgorde.get(sleutel, 0)

    with ui.column().classes("inhoud w-full gap-2"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Tenach").style("font-size:26px;font-weight:700")
            ui.label(f"{sum(b['verzen'] for b in boeken)} verzen").style(
                f"color:{ZACHT};font-size:12.5px")
        with ui.row().classes("w-full gap-2 no-wrap"):
            kies_boek = ui.select(list(op_naam), value=staat["boek"], label="Boek",
                                  with_input=True).props(
                "outlined dense dark").classes("flex-grow")
            kies_hfst = ui.select([1], value=1, label="Hoofdstuk").props(
                "outlined dense dark").style("width:116px;min-width:116px")
        kop = ui.label().style(f"color:{ZACHT};font-size:12.5px")
        # De betekenissen staan bovenaan en blijven staan bij het schuiven: bij een
        # hoofdstuk van veertig verzen wil je niet naar beneden hoeven om te zien wat je
        # net hebt aangetikt.
        uitleg = ui.html()
        tekst = ui.html().classes("hebrij w-full").style(
            "padding:4px 0 2px;line-height:2.15")
        meer = ui.row().classes("w-full justify-center")
    onderbalk("Lezen")

    def verzen_van_hoofdstuk():
        boek = op_naam[staat["boek"]]
        alles = hebreeuws.laad_tenach_boek(boek["bestand"])
        return [v for v in alles
                if v["v"].split(":")[0] == str(staat["hoofdstuk"])]

    def teken():
        verzen = verzen_van_hoofdstuk()
        vanaf = staat["vanaf"]
        stuk = verzen[vanaf:vanaf + TENACH_MAX_VERZEN]
        kop.text = (f"{staat['boek']} {staat['hoofdstuk']} · {len(verzen)} verzen"
                    + (f" · nu {vanaf + 1}–{vanaf + len(stuk)}"
                       if len(verzen) > TENACH_MAX_VERZEN else ""))
        regels = []
        for v in stuk:
            nummer = v["v"].split(":")[-1]
            heel_aan = v["v"] in staat["verzen_aan"]
            # Het versnummer is zelf een knop: één tik zet alle woorden van dat vers open,
            # nog een tik doet ze weer dicht. Zo hoef je er niet twaalf los aan te tikken.
            vakjes = [f"<span class='versnr{' aan' if heel_aan else ''}' "
                      f"data-v='{v['v']}'>{nummer}</span>"]
            for n, w in enumerate(hebreeuws.woorden_van(v)):
                vorm, parsing = w["vorm"], w["parsing"]
                sleutel = f"{v['v']}#{n}"
                aan = sleutel in staat["open"]
                binnen = (heb_gekleurd(vorm, parsing) if aan
                          else f"<span class='hebreeuws'>{vorm}</span>")
                vakjes.append(f"<span class='leeswoord' data-w='{sleutel}' "
                              f"style='color:{MERK if aan else TEKST}'>{binnen}</span>")
            regels.append(" ".join(vakjes))
        tekst.set_content(" ".join(regels) or "Geen tekst gevonden.")
        meer.clear()
        if len(verzen) > TENACH_MAX_VERZEN:
            with meer:
                if vanaf:
                    ui.button("← eerder", on_click=lambda: blader(-1), color=None).props(
                        "flat dense no-caps").style(f"color:{MERK};font-size:13px")
                if vanaf + TENACH_MAX_VERZEN < len(verzen):
                    ui.button("verder →", on_click=lambda: blader(1), color=None).props(
                        "flat dense no-caps").style(f"color:{MERK};font-size:13px")

    def blader(richting):
        staat["vanaf"] = max(0, staat["vanaf"] + richting * TENACH_MAX_VERZEN)
        staat["open"].clear()
        staat["verzen_aan"].clear()
        teken()
        teken_uitleg()

    def teken_uitleg():
        """De aangetikte woorden als kaartjes naast elkaar, bovenaan.

        Nieuwste vooraan: wat je net aantikte staat links en is meteen te zien zonder te
        schuiven. Eerst stonden ze onder de tekst en onder elkaar, en dan moest je bij
        veertig verzen helemaal naar beneden."""
        if not staat["open"]:
            uitleg.set_content("")
            return
        alles = {v["v"]: v for v in verzen_van_hoofdstuk()}
        kaartjes = []
        for sleutel in sorted(staat["open"], key=_leesorde, reverse=True):
            ref, _, n = sleutel.rpartition("#")
            v = alles.get(ref)
            if not v:
                continue
            woorden = hebreeuws.woorden_van(v)
            if int(n) >= len(woorden):
                continue
            kaartjes.append(heb_leeskaart(woorden[int(n)], info, ref))
        uitleg.set_content(f"<div class='uitlegbalk'>{''.join(kaartjes)}</div>")

    def tik(sleutel):
        if sleutel in staat["open"]:
            staat["open"].discard(sleutel)
        else:
            staat["beurt"] += 1
            volgorde[sleutel] = staat["beurt"]
            staat["open"].add(sleutel)
        teken()
        teken_uitleg()

    def tik_vers(ref):
        """Een heel vers open of dicht. Sneller dan twaalf woorden los aantikken."""
        alles = {v["v"]: v for v in verzen_van_hoofdstuk()}
        v = alles.get(ref)
        if not v:
            return
        sleutels = [f"{ref}#{n}" for n in range(len(v["w"]))]
        if ref in staat["verzen_aan"]:
            staat["verzen_aan"].discard(ref)
            staat["open"].difference_update(sleutels)
        else:
            staat["verzen_aan"].add(ref)
            for s in sleutels:
                staat["beurt"] += 1
                volgorde[s] = staat["beurt"]
            staat["open"].update(sleutels)
        teken()
        teken_uitleg()

    def zet_hoofdstukken():
        boek = op_naam[staat["boek"]]
        kies_hfst.options = list(range(1, int(boek["hoofdstukken"]) + 1)) or [1]
        kies_hfst.update()

    def boek_gewisseld():
        staat["boek"] = kies_boek.value
        staat["hoofdstuk"] = 1
        staat["vanaf"] = 0
        staat["open"].clear()
        staat["verzen_aan"].clear()
        zet_hoofdstukken()
        kies_hfst.value = 1
        teken()
        teken_uitleg()

    def hoofdstuk_gewisseld():
        staat["hoofdstuk"] = int(kies_hfst.value or 1)
        staat["vanaf"] = 0
        staat["open"].clear()
        staat["verzen_aan"].clear()
        teken()
        teken_uitleg()

    ui.on("leeswoord", lambda e: tik(str(e.args)))
    ui.on("leesvers", lambda e: tik_vers(str(e.args)))
    kies_boek.on_value_change(lambda _=None: boek_gewisseld())
    kies_hfst.on_value_change(lambda _=None: hoofdstuk_gewisseld())
    zet_hoofdstukken()
    teken()


# ============================================================== Hebreeuws · lezen
# Waar het hele woordenleren voor bedoeld is: een vers openslaan en het snappen. Er staat
# geen vertaling bij, en dat is een keuze — met een vertaling ernaast lees je de vertaling.
# Elk woord is aan te tikken en dan zie je wat het betekent en hoe het ontleed is; in
# elkaar zetten doe je zelf. Zo werkt Ontleden bij het Grieks ook.
#
# Welk vers je krijgt hangt af van wat jíj kent. Van de duizend verzen in het bestand komen
# alleen die in aanmerking waarvan je genoeg woorden al eens hebt geoefend; daarbinnen eerst
# de kortste die je nog niet hebt gelezen. Zo begin je bij een vers van vier woorden en niet
# bij een van veertien.
LEES_SLEUTEL = "lees:"          # zo staan gelezen verzen in hebr_stats
# Zoveel van de woorden moet je al eens geoefend hebben voordat een vers meedoet. Onder de
# helft is het geen lezen maar puzzelen.
LEES_DREMPEL = 0.6


# Voor- en achtervoegsels krijgen de merkkleur, de kern blijft wit. Dezelfde taal als bij
# de rijtjes, waar de uitgang ook cyaan is: wat wisselt is gekleurd, wat vastligt is wit.
# Zo zie je in וְהָאָרֶץ meteen dat er maar één woord in zit dat je hoeft te kennen.
def heb_gekleurd(vorm, parsing, maat=None, aan=None):
    """De vorm in stukken, elk in zijn eigen kleur. Zie hebreeuws.SOORTEN en .KLEUREN.

    Vijf kleuren en niet één, omdat het vijf verschillende dingen zijn. Een voorvoegsel is
    een woord op zichzelf ('en', 'de', 'in'), een persoonsvoorvoegsel zegt wie het doet, een
    uitgang zegt of het enkelvoud of meervoud is, een persoonsuitgang zegt weer wie het
    doet, en een bezittelijk achtervoegsel van wie het is. תִּשְׁמְרוּ is תִּ + שְׁמְר + וּ:
    'jullie' plus de stam plus 'meervoud'.

    Met 'aan' kun je een verzameling soorten meegeven die gekleurd mogen worden; de rest
    krijgt de kleur van de stam. Zonder 'aan' wordt alles gekleurd.

    Lukt het splitsen niet, dan komt dat stuk ongekleurd terug. Liever geen kleur dan de
    verkeerde letters aanwijzen; daar leer je iets verkeerds van."""
    stijl = f"font-size:{maat}px" if maat else ""
    stukken = []
    for tekst, soort in hebreeuws.ontleed_vorm(vorm, parsing):
        kleur = hebreeuws.KLEUREN.get(soort, TEKST)
        if aan is not None and soort not in aan:
            kleur = TEKST
        stukken.append(f"<span style='color:{kleur}'>{tekst}</span>")
    return f"<span class='hebreeuws' style='{stijl}'>" + "".join(stukken) + "</span>"


def heb_affix_uitleg(parsing, vorm=""):
    """Wat elk gekleurd stuk van deze vorm betekent: [(regel, kleur), …].

    Alleen wat er ook echt gekleurd staat. Anders komt er 'mannelijk meervoud' bij een woord
    waar niets is aangewezen, en dan zoek je naar iets wat er niet staat. Daarvoor is de
    vorm nodig; zonder vorm blijft het bij de voorvoegsels uit de code."""
    if not vorm:
        voor_codes, _kern, _achter = hebreeuws._codes(parsing)
        return [(f"{hebreeuws.VOORVOEGSEL_LETTER[c]} = {hebreeuws.VOORVOEGSEL_NL[c]}",
                 hebreeuws.KLEUREN["voor"]) for c in voor_codes]
    return [(f"{tekst} = {uitleg}", hebreeuws.KLEUREN.get(soort, ZACHT))
            for tekst, soort, uitleg in hebreeuws.uitleg_stukken(vorm, parsing)]


def heb_leeskaart(wv, info, ref=""):
    """Eén kaartje voor een aangetikt woord: wat het betekent en hoe het in elkaar zit.

    Zowel de Lezen-pagina met de duizend uitgezochte verzen als het doorbladeren van de
    Tenach gebruiken dit, zodat een woord er overal hetzelfde uitziet.

    De betekenis komt uit je cursuslijst als het woord erin staat. Zo niet, dan uit de
    Engelse vertaling die bij dít woord in de tekst hoort — van de 300.670 woordvormen in
    de Tenach staan er 410 in de lijst, dus zonder dat Engels is de rest een woord zonder
    betekenis. Staat er wél Nederlands, dan komt het Engels eronder als houvast; dat is
    hoe de Griekse leestekst het ook doet."""
    vorm, parsing = wv["vorm"], wv["parsing"]
    w = info.get(wv["strong"])
    betekenis, engels = (heb_betekenis(w) if w else ""), wv["engels"]
    if not betekenis:
        betekenis, engels = engels or "staat niet in je woordenlijst", ""
    # Het Engels alleen erbij als het iets toevoegt: bij אֱלֹהִים stond er anders 'God'
    # en daaronder nog eens 'EN: God'.
    elif engels and engels.lower().strip(" .,;") in betekenis.lower():
        engels = ""
    affixen = heb_affix_uitleg(parsing, vorm)
    ontleed = heb_ontleding(parsing)
    return (
        f"<div class='uitlegkaart'>"
        f"<div style='display:flex;align-items:baseline;gap:6px'>"
        f"{heb_gekleurd(vorm, parsing, maat=19)}"
        + (f"<span style='color:{ZACHT};font-size:11px'>{ref}</span>" if ref else "")
        + "</div>"
        f"<div style='color:{TEKST};font-size:13.5px;line-height:1.35'>{betekenis}</div>"
        + (f"<div style='color:{ZACHT};font-size:11px;font-style:italic'>"
           f"{wv['translit']}</div>" if wv["translit"] else "")
        + (f"<div style='color:{ZACHT};font-size:11.5px'>EN: {engels}</div>"
           if engels else "")
        # Elk stukje in de kleur waarin het ook in het woord staat: cyaan voor de
        # voor- en achtervoegsels, amber voor de uitgang. Anders moet je gokken welke
        # regel bij welke gekleurde letter hoort.
        + "".join(f"<div style='color:{kleur};font-size:11.5px'>{regel}</div>"
                  for regel, kleur in affixen)
        + (f"<div style='color:{ZACHT};font-size:11.5px'>{ontleed}</div>"
           if ontleed else "")
        + "</div>")


def heb_woordinfo(g):
    """Strong-nummer -> het woord uit de lijst. Om bij een vorm in de tekst de betekenis
    te kunnen opzoeken."""
    uit = {}
    for w in g.hebreeuws:
        s = str(w.get("strong") or "")
        if s and s not in uit:
            uit[s] = w
    return uit


def heb_gelezen(g):
    """De verzen die je al hebt gelezen."""
    stats = g.stats.get("hebr_stats") or {}
    return {k[len(LEES_SLEUTEL):] for k in stats if str(k).startswith(LEES_SLEUTEL)}


def heb_kies_vers(g):
    """Het volgende vers om te lezen, of None als er niets past.

    Eerst de verzen die je nog niet had, en daarbinnen de kortste met het hoogste aandeel
    bekende woorden. Heb je alles gehad, dan begint hij opnieuw — herlezen is geen straf."""
    verzen = hebreeuws.laad_verzen()
    if not verzen:
        return None
    info = heb_woordinfo(g)
    geoefend = {s for s, w in info.items()
                if int(w.get("score_goed", 0)) or int(w.get("score_fout", 0))
                or int(w.get("streak", 0))}
    gelezen = heb_gelezen(g)

    geschikt = []
    for vers in verzen:
        woorden = hebreeuws.woorden_van(vers)
        if not woorden:
            continue
        bekend = sum(1 for w in woorden if w["strong"] in geoefend)
        deel = bekend / len(woorden)
        if deel < LEES_DREMPEL:
            continue
        geschikt.append((vers["vers"] in gelezen, -deel, len(woorden), vers))
    if not geschikt:
        # Nog niets geoefend: dan de kortste verzen waarvan élk woord in de lijst staat.
        # Beter iets te lezen geven dan een leeg scherm met 'oefen eerst maar wat'.
        geschikt = [(vers["vers"] in gelezen, 0, len(vers["woorden"]), vers)
                    for vers in verzen
                    if all(w["strong"] in info
                           for w in hebreeuws.woorden_van(vers))]
    if not geschikt:
        return None
    geschikt.sort(key=lambda k: k[:3])
    # Niet altijd exact hetzelfde vers: uit de tien makkelijkste er één, zodat het niet
    # elke keer bij hetzelfde blijft hangen als je iets niet afmaakt.
    return random.choice(geschikt[:10])[3]


def heb_ontleding(parsing):
    """De ontleedcode leesbaar maken: 'Conj-w | V-Qal-ConsecImperf-3ms' wordt
    'en · Qal wajjiqtol 3e m ev'. Wat we niet kennen laten we staan — dan zie je dat er
    iets is in plaats van dat het verdwijnt."""
    if not parsing:
        return ""
    delen = []
    for stuk in str(parsing).split("|"):
        for code in stuk.split(","):
            code = code.strip()
            if not code:
                continue
            delen.append(HEB_ONTLEED.get(code) or _heb_ontleed_werkwoord(code) or code)
    return " · ".join(d for d in delen if d)


# De codes die de WLC gebruikt, in gewoon Nederlands. Alleen wat er echt in voorkomt.
HEB_ONTLEED = {
    "Conj-w": "en", "Art": "de/het", "Prep-b": "in/met", "Prep-k": "als",
    "Prep-l": "voor/naar", "Prep-m": "uit/van", "Prep": "voorzetsel",
    "Interrog": "vraagwoord", "Adv": "bijwoord", "Conj": "voegwoord",
    "N-ms": "znw m ev", "N-mp": "znw m mv", "N-fs": "znw v ev", "N-fp": "znw v mv",
    "N-msc": "znw m ev verbonden", "N-mpc": "znw m mv verbonden",
    "N-fsc": "znw v ev verbonden", "N-fpc": "znw v mv verbonden",
    "N-proper-ms": "eigennaam", "N-proper-fs": "eigennaam",
    "Adj-ms": "bnw m ev", "Adj-fs": "bnw v ev", "Adj-mp": "bnw m mv",
    "Pro-3ms": "hij", "Pro-3fs": "zij", "Pro-2ms": "jij", "Pro-1cs": "ik",
    "Pro-3mp": "zij mv", "Pro-1cp": "wij", "Pro-2mp": "jullie", "Pro-r": "die/dat",
    "Pro-ms": "deze", "Pro-fs": "deze", "Pro-cp": "deze mv",
    "DirObjM": "lijdend voorwerp", "Adv-NegPrt": "niet",
}
# De stukjes waaruit een werkwoordcode is opgebouwd.
HEB_STAM_NL = {"Qal": "Qal", "Nifal": "Nifal", "Piel": "Piel", "Pual": "Pual",
               "Hifil": "Hifil", "Hofal": "Hofal", "Hitpael": "Hitpael",
               "QalPassPrtcpl": "Qal passief deelwoord"}
HEB_TIJD_NL = {"Perf": "perfectum", "Imperf": "imperfectum",
               "ConsecImperf": "wajjiqtol", "ConjPerf": "wegatal",
               "Imp": "gebiedende wijs", "Inf": "infinitief",
               "InfAbs": "infinitivus absolutus", "InfCon": "infinitivus constructus",
               "Prtcpl": "deelwoord"}
HEB_PERSOON_NL = {"3ms": "3e m ev", "3fs": "3e v ev", "2ms": "2e m ev", "2fs": "2e v ev",
                  "1cs": "1e ev", "3mp": "3e m mv", "3fp": "3e v mv", "3cp": "3e mv",
                  "2mp": "2e m mv", "2fp": "2e v mv", "1cp": "1e mv",
                  "ms": "m ev", "fs": "v ev", "mp": "m mv", "fp": "v mv"}


def _heb_ontleed_werkwoord(code):
    """'V-Qal-ConsecImperf-3ms' -> 'Qal wajjiqtol 3e m ev'."""
    if not code.startswith("V-"):
        return ""
    delen = []
    for stuk in code[2:].split("-"):
        delen.append(HEB_STAM_NL.get(stuk) or HEB_TIJD_NL.get(stuk)
                     or HEB_PERSOON_NL.get(stuk) or stuk)
    return " ".join(delen)


# ============================================================== Klankwetten
# Waarom dit hier kan en niet zwaar is: de klankwet-index wordt opgebouwd uit de NT-tekst,
# en die staat al in het geheugen voor ontleden en de leesteksten. Gemeten kost de index er
# 6 MB en een halve seconde bovenop, eenmalig, en alleen als je deze pagina opent.
#
# De oefening zelf is dezelfde als in de uitgebreide app: een echte vorm uit het NT, en de
# vraag is welke klankwet daar aan het werk is. De afleiders komen eerst uit dezelfde
# klanksoort, want kappa, gamma en chi door elkaar halen is de klassieke fout.
KLANK_SLEUTEL = "klank_stats"
KLANK_STANDAARD = {"kl_aantal": 12, "kl_drempel": 1}


def klank_bron(g):
    """Strong-nummer -> het woord uit je lijst. Nodig om de vormen te kunnen uitleggen."""
    uit = {}
    for w in g.woorden:
        s = str(w.get("strong") or "")
        if s and s not in uit:
            uit[s] = w
    return uit


def klank_voorraad(g, drempel):
    """De vormen waarmee je kunt oefenen: alleen woorden die je al kent.

    Zonder die grens krijg je klankwetten te zien op woorden die je nooit gezien hebt, en
    dan oefen je twee dingen tegelijk. Hetzelfde uitgangspunt als in de uitgebreide app."""
    if not BIJBEL:
        return []
    bron = klank_bron(g)
    streak = {s: int(w.get("streak", 0) or 0) for s, w in bron.items()}
    try:
        index = motor.klankwet_index(motor.laad_bijbel_db(), bron)
    except Exception:                                            # noqa: BLE001
        return []
    uit = []
    for sleutel, rijen in index.items():
        for (vorm, lemma, info, ref, strong) in rijen:
            if streak.get(strong, 0) < drempel:
                continue
            uit.append((sleutel, vorm, lemma, info, ref, strong))
    return uit


class KlankSessie:
    def __init__(self, g):
        self.prefs = {k: (g.stats.get("ui_prefs") or {}).get(f"ng_{k}", v)
                      for k, v in KLANK_STANDAARD.items()}
        drempel = max(0, int(self.prefs["kl_drempel"] or 0))
        voorraad = klank_voorraad(g, drempel)
        stats = g.stats.get(KLANK_SLEUTEL) or {}
        # Klanksoorten die je vaker fout doet komen vaker aan de beurt.
        gewicht = []
        for rij in voorraad:
            e = stats.get(rij[0]) or {}
            fout, goed = int(e.get("f", 0) or 0), int(e.get("g", 0) or 0)
            gewicht.append(1 + min(6, 2 * fout) + (2 if goed + fout == 0 else 0))
        aantal = max(4, int(self.prefs["kl_aantal"] or 12))
        self.vragen = []
        if voorraad:
            gekozen = random.choices(voorraad, weights=gewicht,
                                     k=min(aantal, len(voorraad) * 2))
            gezien = set()
            for rij in gekozen:
                if rij[1] in gezien:
                    continue
                gezien.add(rij[1])
                self.vragen.append(rij)
        self.i = 0
        self.goed = 0
        self.fout = 0
        self.beoordeeld = False
        self.bezig = False

    @property
    def huidig(self):
        return self.vragen[self.i] if self.i < len(self.vragen) else None


def klank_analyse(g, vorm, lemma, info, strong, sleutel):
    """(de klankwet van deze vraag, de andere klankwetten in dezelfde vorm)."""
    w = klank_bron(g).get(strong) or {}
    alles = motor.samensmeltingen_alle(
        vorm, lemma, info, grieks_info=str(w.get("grieks_info", "") or ""),
        corpus_stam=motor.corpus_stam_van(strong, info))
    deze = next((a for a in alles if a.get("sleutel") == sleutel), None)
    if deze is None:
        deze = alles[0] if alles else {}
    return deze, [a for a in alles if a is not deze]


@ui.page("/oefenen/klankwetten")
def klankpagina():
    g = _bewaakt()
    if not g:
        return
    sessie = KlankSessie(g)
    stats = g.stats.setdefault(KLANK_SLEUTEL, {})
    try:
        formules = motor.klankwet_formule_index(motor.laad_bijbel_db(), klank_bron(g))
    except Exception:                                            # noqa: BLE001
        formules = {}

    with ui.dialog() as instellingen, ui.card().style(
            f"background:{VLAK};color:{TEKST};min-width:300px;max-width:92vw"):
        ui.label("Instellingen").style("font-size:18px;font-weight:700")
        k_aantal = ui.number("Vragen per ronde", value=int(sessie.prefs["kl_aantal"]),
                             min=4, max=40, step=1).props("outlined dark").classes("w-full")
        k_drempel = ui.number("Alleen woorden met streak vanaf",
                              value=int(sessie.prefs["kl_drempel"]), min=0, max=16,
                              step=1).props("outlined dark").classes("w-full")
        ui.label("Je oefent met vormen van woorden die je al kent. Zet de drempel op 0 om "
                 "alles mee te nemen.").style(f"color:{ZACHT};font-size:13px")

        async def bewaar_inst():
            for sleutel, veld in [("kl_aantal", k_aantal), ("kl_drempel", k_drempel)]:
                g.stats.setdefault("ui_prefs", {})[f"ng_{sleutel}"] = veld.value
            instellingen.close()
            await run.io_bound(g.bewaar, True)
            ui.navigate.to("/oefenen/klankwetten")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Annuleren", on_click=instellingen.close, color=None).props(
                "flat no-caps").style(f"color:{ZACHT}")
            ui.button("Toepassen", on_click=bewaar_inst, color=None).props(
                "unelevated no-caps").style(
                f"background:{MERK};color:{INKT};font-weight:700")

    with ui.column().classes("inhoud metbalk w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Klankwetten").style(f"color:{ZACHT};font-size:13px")
            with ui.row().classes("items-center gap-2 no-wrap"):
                teller = ui.label().style(f"color:{ZACHT};font-size:13px")
                ui.button("⚙", on_click=instellingen.open, color=None).props(
                    "flat dense no-caps").classes("raakbaar").style(
                    f"color:{ZACHT};font-size:17px;min-width:32px")
        streepjes = ui.row().classes("w-full gap-1 no-wrap")
        woord = ui.html().classes("w-full text-center").style("padding:8px 0 2px")
        herkomst = ui.label().classes("w-full text-center").style(
            f"color:{ZACHT};font-size:12.5px")
        vraagsoort = ui.label().classes("w-full text-center").style(
            f"color:{ZACHT};font-size:13px;padding-top:6px")
        opties = ui.column().classes("keuzevak w-full gap-2").style("padding-top:6px")
        statusbalk = ui.row().classes("w-full").style("padding-top:2px")
        terugkoppeling = ui.column().classes("w-full items-center justify-center").style(
            "min-height:64px;padding-top:8px")
        opslagmelding = ui.label().style(f"color:{ZACHT};font-size:12.5px;min-height:16px")

    with ui.element("div").classes("antwoordbalk"):
        with ui.row().classes("w-full gap-2 no-wrap items-center justify-end"):
            knop = ui.button("Ik weet het niet", color=None).props(
                "unelevated no-caps").style(
                f"background:{MERK};color:{INKT};font-weight:700;height:40px;"
                f"width:132px;min-width:132px;font-size:14px")
    onderbalk("Oefenen")

    if not sessie.vragen:
        woord.set_content(f"<span style='font-size:34px;color:{TEKST}'>—</span>")
        vraagsoort.text = ("Nog geen oefenvormen. Oefen eerst wat woorden, of zet de "
                           "streak-drempel lager bij ⚙."
                           if BIJBEL else "Hiervoor is de NT-tekst nodig.")
        knop.text = "Terug"
        knop.on_click(lambda: ui.navigate.to("/oefenen"))
        return

    def teken():
        streepjes.clear()
        with streepjes:
            for n in range(len(sessie.vragen)):
                kleur = MERK if n < sessie.i else (TEKST if n == sessie.i else RAND)
                ui.element("div").style(
                    f"flex:1;height:4px;border-radius:2px;background:{kleur}")

    def toon():
        for vak in (opties, terugkoppeling, statusbalk):
            vak.clear()
        sessie.beoordeeld = False
        vraag = sessie.huidig
        for vak in (woord, herkomst, vraagsoort, opties, statusbalk):
            vak.set_visibility(True)
        if vraag is None:
            woord.set_content(f"<span style='font-size:46px;color:{TEKST}'>✓</span>")
            herkomst.text = ""
            vraagsoort.text = f"Klaar — {sessie.goed} goed, {sessie.fout} fout."
            teller.text = ""
            knop.text = "Nieuwe ronde"
            teken()
            return
        sleutel, vorm, lemma, info, ref, strong = vraag
        woord.set_content(f"<span class='grieks' style='font-size:40px;color:{TEKST}'>"
                          f"{vorm}</span>")
        herkomst.text = f"{ref} · van {lemma}"
        vraagsoort.text = "Welke klankwet is hier aan het werk?"
        teller.text = f"{sessie.i + 1}/{len(sessie.vragen)}"
        knop.text = "Ik weet het niet"
        teken()
        deze, _rest = klank_analyse(g, vorm, lemma, info, strong, sleutel)
        juist = deze.get("formule", "")
        afleiders = motor.klank_afleiders(sleutel, juist, formules, random, aantal=3)
        keuzes = [juist] + list(afleiders)
        random.shuffle(keuzes)
        with opties:
            for keuze in keuzes:
                ui.html(f"<button class='keuze grieks' style='font-size:15px;"
                        f"padding:9px 12px;line-height:1.35'>{keuze}</button>").on(
                    "click", lambda _=None, kz=keuze: kies(kz))
        e = stats.get(sleutel) or {}
        with statusbalk:
            ui.html(_statusrij([
                (int(e.get("streak", 0) or 0), "streak", TEKST),
                (_goedfout(int(e.get("g", 0) or 0), int(e.get("f", 0) or 0)), "", TEKST),
                (len(sessie.vragen) - sessie.i - 1, "te gaan", ZACHT),
            ]))

    async def verwerk(juist, aangeklikt=None):
        sleutel, vorm, lemma, info, ref, strong = sessie.huidig
        sessie.beoordeeld = True
        sessie.goed += int(juist)
        sessie.fout += int(not juist)
        e = stats.setdefault(sleutel, {"g": 0, "f": 0, "streak": 0})
        e["g"] = int(e.get("g", 0)) + int(juist)
        e["f"] = int(e.get("f", 0)) + int(not juist)
        e["streak"] = int(e.get("streak", 0)) + 1 if juist else 0
        g.tel_dag()
        opgeslagen = await run.io_bound(g.bewaar)
        for vak in (woord, herkomst, vraagsoort, opties, statusbalk):
            vak.set_visibility(False)
        deze, rest = klank_analyse(g, vorm, lemma, info, strong, sleutel)
        kleur = GOED if juist else FOUT
        achter = "rgba(61,220,151,.10)" if juist else "rgba(255,107,129,.10)"
        naam = motor._SAMENSMELT_KLASSEN.get(sleutel, (sleutel, ""))[0]
        gekozen = (f"<div style='color:{ZACHT};font-size:13px;margin-top:8px'>"
                   f"jij koos <span style='color:{FOUT}'>{aangeklikt}</span></div>"
                   if not juist and aangeklikt else "")
        erbij = (f"<div style='color:{ZACHT};font-size:12.5px;margin-top:8px'>"
                 f"in deze vorm zit ook: "
                 f"{' · '.join(a.get('formule', '') for a in rest)}</div>"
                 if rest else "")
        terugkoppeling.clear()
        with terugkoppeling:
            ui.html(
                f"<div style='background:{achter};border:1px solid {kleur}40;"
                f"border-radius:16px;padding:22px 18px;text-align:center;width:100%'>"
                f"<div style='color:{kleur};font-weight:700;font-size:19px'>"
                f"{'✓ Goed!' if juist else '✗ Niet goed'}</div>"
                f"<div class='grieks' style='font-size:34px;margin-top:12px;"
                f"line-height:1.3;color:{TEKST}'>{vorm}</div>"
                f"<div class='grieks' style='color:{MERK};font-size:20px;margin-top:6px'>"
                f"{deze.get('formule', '')}</div>"
                f"<div style='color:{TEKST};font-size:15px;margin-top:4px'>{naam}</div>"
                + (f"<div style='color:{ZACHT};font-size:13.5px;margin-top:6px'>"
                   f"{_streepjes_naar_html(deze.get('uitleg', ''))}</div>"
                   if deze.get("uitleg") else "")
                + f"<div style='color:{ZACHT};font-size:12.5px;margin-top:6px'>"
                  f"{ref} · van {lemma}</div>"
                + gekozen + erbij
                + f"<div style='color:{ZACHT};font-size:12.5px;margin-top:14px'>"
                  f"{sessie.goed} goed · {sessie.fout} fout in deze ronde · "
                  f"streak nu {e['streak']}</div></div>")
        if opgeslagen:
            opslagmelding.text = "Voortgang opgeslagen"
        knop.text = "Volgende"
        _uitslag_staat(sessie)

    async def kies(keuze):
        if sessie.beoordeeld or sessie.bezig:
            return
        sessie.bezig = True
        try:
            sleutel, vorm, lemma, info, _ref, strong = sessie.huidig
            deze, _rest = klank_analyse(g, vorm, lemma, info, strong, sleutel)
            await verwerk(keuze == deze.get("formule", ""), keuze)
        finally:
            sessie.bezig = False

    async def hoofdknop():
        if sessie.bezig:
            return
        sessie.bezig = True
        try:
            if sessie.huidig is None:
                await run.io_bound(g.bewaar, True)
                ui.navigate.to("/oefenen/klankwetten")
                return
            if sessie.beoordeeld:
                if te_snel(sessie):
                    return
                sessie.i += 1
                toon()
                return
            await verwerk(False)
        finally:
            sessie.bezig = False

    knop.on_click(hoofdknop)
    toon()


# ============================================================== Contractietrainer
# Drie niveaus, oplopend: eerst de regel herkennen, dan de uitkomst voorspellen, dan zelf
# typen. Dezelfde opzet en dezelfde voortgang als in de uitgebreide app -- de sleutels in
# gram_stats zijn gelijk ('contr::<soort>'), dus wat je hier doet zie je daar ook.
CONTR_SOORTEN = ["σ-samensmelting (fut./aor.)", "Verba contracta (klinkers)",
                 "Augment (verleden tijd)"]
# Twee niveaus, allebei productie. 'Herken de regel' zat er ook in, maar dat doet het
# Klankwetten-tabblad al — en daar gebeurt het op echte vormen uit het NT in plaats van op
# voorbeelden uit een tabel. Zo is de verdeling scherp: klankwetten om te herkennen in de
# tekst, contracties om zelf te vormen.
CONTR_NIVEAUS = ["Voorspel de uitkomst", "Vorm zelf (typen)"]
CONTR_STANDAARD = {"co_soort": CONTR_SOORTEN[0], "co_niveau": CONTR_NIVEAUS[0],
                   "co_aantal": 12}


def contr_opgaven(cdb, soort):
    """De opgaven voor deze soort. De hint bevat nooit het antwoord."""
    uit = []
    if soort.startswith("σ"):
        for regel in cdb.get("sigma", []):
            for (van, naar, bet) in regel["vb"]:
                uit.append({"van": van, "naar": naar, "hint": bet,
                            "klasse": regel["klasse"], "regel": regel["regel"],
                            "uitkomst": regel["uitkomst"]})
    elif soort.startswith("Verba"):
        for regel in cdb.get("contracta", []):
            uit.append({"van": regel["combo"], "naar": regel["uitkomst"],
                        "hint": f"stam op -{regel['stam']}",
                        "klasse": f"stam op -{regel['stam']}",
                        "regel": f"{regel['combo']} → {regel['uitkomst']}",
                        "uitkomst": regel["uitkomst"]})
    else:
        for regel in cdb.get("augment", []):
            for (van, naar) in regel["vb"]:
                uit.append({"van": van, "naar": naar,
                            "hint": f"begint met {regel['begin']}",
                            "klasse": f"begint met {regel['begin']}",
                            "regel": regel["regel"], "uitkomst": naar})
    return uit


class ContrSessie:
    def __init__(self, g):
        self.prefs = {k: (g.stats.get("ui_prefs") or {}).get(f"ng_{k}", v)
                      for k, v in CONTR_STANDAARD.items()}
        self.soort = self.prefs["co_soort"] if self.prefs["co_soort"] in CONTR_SOORTEN \
            else CONTR_SOORTEN[0]
        self.niveau = self.prefs["co_niveau"] if self.prefs["co_niveau"] in CONTR_NIVEAUS \
            else CONTR_NIVEAUS[0]
        self.cdb = motor.laad_contractie_db() or {}
        alles = contr_opgaven(self.cdb, self.soort)
        aantal = max(4, int(self.prefs["co_aantal"] or 12))
        self.alles = alles
        self.vragen = random.sample(alles, min(aantal, len(alles))) if alles else []
        self.i = 0
        self.goed = 0
        self.fout = 0
        self.beoordeeld = False
        self.bezig = False

    @property
    def huidig(self):
        return self.vragen[self.i] if self.i < len(self.vragen) else None


@ui.page("/oefenen/contracties")
def contractiepagina():
    g = _bewaakt()
    if not g:
        return
    sessie = ContrSessie(g)
    stats = g.stats.setdefault("gram_stats", {})
    typen = sessie.niveau.startswith("Vorm")

    with ui.dialog() as instellingen, ui.card().style(
            f"background:{VLAK};color:{TEKST};min-width:300px;max-width:92vw"):
        ui.label("Instellingen").style("font-size:18px;font-weight:700")
        k_soort = ui.select(CONTR_SOORTEN, value=sessie.soort,
                            label="Oefenstof").props("outlined dark").classes("w-full")
        k_niveau = ui.select(CONTR_NIVEAUS, value=sessie.niveau,
                             label="Niveau").props("outlined dark").classes("w-full")
        k_aantal = ui.number("Vragen per ronde", value=int(sessie.prefs["co_aantal"]),
                             min=4, max=40, step=1).props("outlined dark").classes("w-full")
        ui.label("Hier vorm je zelf: eerst de uitkomst voorspellen, daarna hem typen. "
                 "Een klankwet herkennen in een echte vorm uit het NT doe je bij "
                 "Klankwetten.").style(f"color:{ZACHT};font-size:13px")

        async def bewaar_inst():
            for sleutel, veld in [("co_soort", k_soort), ("co_niveau", k_niveau),
                                  ("co_aantal", k_aantal)]:
                g.stats.setdefault("ui_prefs", {})[f"ng_{sleutel}"] = veld.value
            instellingen.close()
            await run.io_bound(g.bewaar, True)
            ui.navigate.to("/oefenen/contracties")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Annuleren", on_click=instellingen.close, color=None).props(
                "flat no-caps").style(f"color:{ZACHT}")
            ui.button("Toepassen", on_click=bewaar_inst, color=None).props(
                "unelevated no-caps").style(
                f"background:{MERK};color:{INKT};font-weight:700")

    with ui.column().classes("inhoud metbalk w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label(sessie.soort).style(f"color:{ZACHT};font-size:13px")
            with ui.row().classes("items-center gap-2 no-wrap"):
                teller = ui.label().style(f"color:{ZACHT};font-size:13px")
                ui.button("⚙", on_click=instellingen.open, color=None).props(
                    "flat dense no-caps").classes("raakbaar").style(
                    f"color:{ZACHT};font-size:17px;min-width:32px")
        streepjes = ui.row().classes("w-full gap-1 no-wrap")
        woord = ui.html().classes("w-full text-center").style("padding:8px 0 2px")
        herkomst = ui.label().classes("w-full text-center").style(
            f"color:{ZACHT};font-size:12.5px")
        vraagsoort = ui.label().classes("w-full text-center").style(
            f"color:{ZACHT};font-size:13px;padding-top:6px")
        opties = ui.column().classes("keuzevak w-full gap-2").style("padding-top:6px")
        statusbalk = ui.row().classes("w-full").style("padding-top:2px")
        terugkoppeling = ui.column().classes("w-full items-center justify-center").style(
            "min-height:64px;padding-top:8px")
        opslagmelding = ui.label().style(f"color:{ZACHT};font-size:12.5px;min-height:16px")

    with ui.element("div").classes("antwoordbalk"):
        with ui.row().classes("w-full gap-2 no-wrap items-center"):
            invoer = ui.input(placeholder="de gevormde vorm").props(
                "outlined dense dark autocomplete=off").classes("flex-grow")
            invoer.set_visibility(typen)
            knop = ui.button("Nakijken" if typen else "Ik weet het niet",
                             color=None).props("unelevated no-caps").style(
                f"background:{MERK};color:{INKT};font-weight:700;height:40px;"
                f"width:132px;min-width:132px;font-size:14px")
    onderbalk("Oefenen")

    if not sessie.vragen:
        woord.set_content(f"<span style='font-size:34px;color:{TEKST}'>—</span>")
        vraagsoort.text = "Het bestand contractie_data.json ontbreekt."
        knop.text = "Terug"
        knop.on_click(lambda: ui.navigate.to("/oefenen"))
        return

    def teken():
        streepjes.clear()
        with streepjes:
            for n in range(len(sessie.vragen)):
                kleur = MERK if n < sessie.i else (TEKST if n == sessie.i else RAND)
                ui.element("div").style(
                    f"flex:1;height:4px;border-radius:2px;background:{kleur}")

    def juist_antwoord(opg):
        """Wat er goed is. Beide niveaus vragen de vorm; het verschil is meerkeuze of typen."""
        return opg["naar"]

    def keuzelijst(opg):
        goed = juist_antwoord(opg)
        alle = list({o["naar"] for o in sessie.alles})
        afleiders = [x for x in alle if x != goed]
        random.shuffle(afleiders)
        keuzes = afleiders[:3] + [goed]
        random.shuffle(keuzes)
        return keuzes

    def toon():
        for vak in (opties, terugkoppeling, statusbalk):
            vak.clear()
        sessie.beoordeeld = False
        opg = sessie.huidig
        for vak in (woord, herkomst, vraagsoort, opties, statusbalk):
            vak.set_visibility(True)
        invoer.set_visibility(typen)
        if opg is None:
            woord.set_content(f"<span style='font-size:46px;color:{TEKST}'>✓</span>")
            herkomst.text = ""
            vraagsoort.text = f"Klaar — {sessie.goed} goed, {sessie.fout} fout."
            teller.text = ""
            invoer.set_visibility(False)
            knop.text = "Nieuwe ronde"
            teken()
            return
        woord.set_content(f"<span class='grieks' style='font-size:38px;color:{TEKST}'>"
                          f"{opg['van']}</span>"
                          f"<span style='color:{ZACHT};font-size:30px'> → ?</span>")
        herkomst.text = opg["hint"]
        vraagsoort.text = ("Welke vorm ontstaat er?" if not typen
                           else "Typ de gevormde vorm.")
        teller.text = f"{sessie.i + 1}/{len(sessie.vragen)}"
        knop.text = "Nakijken" if typen else "Ik weet het niet"
        invoer.value = ""
        teken()
        if not typen:
            with opties:
                for keuze in keuzelijst(opg):
                    ui.html(f"<button class='keuze grieks' style='font-size:16px;"
                            f"padding:9px 12px;line-height:1.35'>{keuze}</button>").on(
                        "click", lambda _=None, kz=keuze: kies(kz))
        else:
            invoer.run_method("focus")
        e = stats.get(f"contr::{sessie.soort}") or {}
        with statusbalk:
            ui.html(_statusrij([
                (int(e.get("streak", 0) or 0), "streak", TEKST),
                (_goedfout(int(e.get("g", 0) or 0), int(e.get("f", 0) or 0)), "", TEKST),
                (len(sessie.vragen) - sessie.i - 1, "te gaan", ZACHT),
            ]))

    async def verwerk(juist, aangeklikt=None):
        opg = sessie.huidig
        sessie.beoordeeld = True
        sessie.goed += int(juist)
        sessie.fout += int(not juist)
        # Dezelfde sleutel als de uitgebreide app, zodat het één voortgang is.
        e = stats.setdefault(f"contr::{sessie.soort}", {"g": 0, "f": 0, "streak": 0})
        e["g"] = int(e.get("g", 0)) + int(juist)
        e["f"] = int(e.get("f", 0)) + int(not juist)
        e["streak"] = int(e.get("streak", 0)) + 1 if juist else 0
        g.tel_dag()
        opgeslagen = await run.io_bound(g.bewaar)
        for vak in (woord, herkomst, vraagsoort, opties, statusbalk):
            vak.set_visibility(False)
        invoer.set_visibility(False)
        kleur = GOED if juist else FOUT
        achter = "rgba(61,220,151,.10)" if juist else "rgba(255,107,129,.10)"
        gekozen = (f"<div style='color:{ZACHT};font-size:13px;margin-top:8px'>"
                   f"jij koos <span style='color:{FOUT}'>{aangeklikt}</span></div>"
                   if not juist and aangeklikt else "")
        terugkoppeling.clear()
        with terugkoppeling:
            ui.html(
                f"<div style='background:{achter};border:1px solid {kleur}40;"
                f"border-radius:16px;padding:22px 18px;text-align:center;width:100%'>"
                f"<div style='color:{kleur};font-weight:700;font-size:19px'>"
                f"{'✓ Goed!' if juist else '✗ Niet goed'}</div>"
                f"<div class='grieks' style='font-size:32px;margin-top:12px;"
                f"line-height:1.3;color:{TEKST}'>{opg['van']} → {opg['naar']}</div>"
                f"<div style='color:{MERK};font-size:16px;margin-top:6px'>"
                f"{opg['regel']}</div>"
                + gekozen
                + f"<div style='color:{ZACHT};font-size:12.5px;margin-top:14px'>"
                  f"{sessie.goed} goed · {sessie.fout} fout in deze ronde · "
                  f"streak nu {e['streak']}</div></div>")
        if opgeslagen:
            opslagmelding.text = "Voortgang opgeslagen"
        knop.text = "Volgende"
        _uitslag_staat(sessie)

    async def kies(keuze):
        if sessie.beoordeeld or sessie.bezig:
            return
        sessie.bezig = True
        try:
            await verwerk(keuze == juist_antwoord(sessie.huidig), keuze)
        finally:
            sessie.bezig = False

    async def hoofdknop():
        if sessie.bezig:
            return
        sessie.bezig = True
        try:
            if sessie.huidig is None:
                await run.io_bound(g.bewaar, True)
                ui.navigate.to("/oefenen/contracties")
                return
            if sessie.beoordeeld:
                if te_snel(sessie):
                    return
                sessie.i += 1
                toon()
                return
            if typen:
                gegeven = str(invoer.value or "").strip()
                if not gegeven:
                    await verwerk(False)
                    return
                await verwerk(motor.check_betekenis(gegeven, sessie.huidig["naar"])
                              or _grieks_gelijk(gegeven, sessie.huidig["naar"]), gegeven)
                return
            await verwerk(False)
        finally:
            sessie.bezig = False

    knop.on_click(hoofdknop)
    invoer.on("keydown.enter", hoofdknop)
    toon()


def _streepjes_naar_html(tekst):
    """**dik** en *schuin* omzetten naar html.

    De uitleg bij een klankwet komt uit dezelfde functie die de Streamlit-app gebruikt, en
    daar gaat hij door st.markdown. Hier niet, dus zonder dit staat er letterlijk
    'op **-ε**' op het scherm."""
    tekst = str(tekst or "")
    tekst = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", tekst)
    return re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", tekst)


def _grieks_gelijk(gegeven, doel):
    """Twee Griekse vormen vergelijken zonder op accenten te vallen.

    Accenten typen op een gewoon toetsenbord is niet te doen, en het gaat hier om de
    klankverandering en niet om de klemtoon. Zelfde soepelheid als niveau 3 in de
    uitgebreide app."""
    kaal = lambda s: motor.normaliseer_accent(str(s or "").strip().lower())
    if kaal(gegeven) == kaal(doel):
        return True
    return difflib.SequenceMatcher(None, kaal(gegeven), kaal(doel)).ratio() > 0.85


@ui.page("/lezen/hebreeuws")
def heblezenpagina():
    g = _bewaakt()
    if not g:
        return
    if not hebreeuws.laad_verzen():
        ui.navigate.to("/lezen")
        return
    vers = heb_kies_vers(g)
    if vers is None:
        ui.navigate.to("/lezen")
        return
    info = heb_woordinfo(g)
    # Welke woorden je al hebt aangetikt. Dat blijft binnen dit ene vers.
    open_gezet = set()
    # In welke volgorde: het laatst aangetikte woord staat vooraan in de balk.
    beurt = {}

    with ui.column().classes("inhoud metbalk w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Lezen").style(f"color:{ZACHT};font-size:13px")
            verwijzing = ui.label().style(f"color:{ZACHT};font-size:13px")
        # Het vers zelf, van rechts naar links, met elk woord als eigen vakje.
        # Zelfde keuze als bij het doorbladeren: de betekenissen bovenaan en naast
        # elkaar, niet eronder en onder elkaar.
        uitleg = ui.html()
        tekst = ui.html().classes("hebrij w-full").style(
            "padding:6px 0 2px;line-height:2.1")
        teller = ui.label().classes("w-full").style(f"color:{ZACHT};font-size:12.5px")
        opslagmelding = ui.label().style(f"color:{ZACHT};font-size:12.5px;min-height:16px")

    balk = ui.row()
    with ui.element("div").classes("antwoordbalk"):
        with ui.row().classes("w-full gap-2 no-wrap items-center"):
            alles_knop = ui.button("Alles tonen", color=None).props(
                "flat no-caps").style(
                f"flex:1;color:{ZACHT};border:1px solid {RAND};border-radius:8px;"
                f"height:40px;font-size:13px")
            volgende = ui.button("Gelezen", color=None).props("unelevated no-caps").style(
                f"background:{MERK};color:{INKT};font-weight:700;height:40px;"
                f"width:132px;min-width:132px;font-size:14px")
    onderbalk("Lezen")

    def teken():
        verwijzing.text = vers["vers"]
        vakjes = []
        for n, wv in enumerate(hebreeuws.woorden_van(vers)):
            vorm, strong, _parsing = wv["vorm"], wv["strong"], wv["parsing"]
            w = info.get(strong)
            gekend = w is not None and (int(w.get("streak", 0) or 0)
                                        or int(w.get("score_goed", 0) or 0))
            if n in open_gezet:
                kleur, rand = MERK, MERK
            elif w is None:
                kleur, rand = ZACHT, RAND        # niet in de lijst: dat woord krijg je erbij
            else:
                kleur, rand = TEKST, (RAND if gekend else FOUT)
            # Het woord met zijn voorvoegsels in kleur — maar alleen als je hem al hebt
            # aangetikt of als je 'alles tonen' aan hebt. Anders geeft de kleur het al weg
            # en valt er niets meer te herkennen.
            binnen = (heb_gekleurd(vorm, _parsing) if n in open_gezet
                      else f"<span class='hebreeuws'>{vorm}</span>")
            vakjes.append(
                f"<span class='leeswoord' data-n='{n}' "
                f"style='color:{kleur};border-bottom:2px solid {rand}'>{binnen}</span>")
        tekst.set_content(" ".join(vakjes))
        bekend = sum(1 for w in hebreeuws.woorden_van(vers)
                     if (info.get(w["strong"]) or {}).get("streak", 0)
                     or (info.get(w["strong"]) or {}).get("score_goed", 0))
        teller.text = (f"{bekend} van de {len(vers['woorden'])} woorden heb je geoefend · "
                       f"tik een woord aan voor de betekenis")

    def teken_uitleg():
        if not open_gezet:
            uitleg.set_content("")
            return
        woorden = hebreeuws.woorden_van(vers)
        kaartjes = [heb_leeskaart(woorden[n], info)
                    for n in sorted(open_gezet, key=lambda k: -beurt.get(k, 0))
                    if n < len(woorden)]
        uitleg.set_content(f"<div class='uitlegbalk'>{''.join(kaartjes)}</div>")

    def tik(n):
        if n in open_gezet:
            open_gezet.discard(n)
        else:
            beurt["nu"] = beurt.get("nu", 0) + 1
            beurt[n] = beurt["nu"]
            open_gezet.add(n)
        teken()
        teken_uitleg()

    def alles():
        if len(open_gezet) == len(vers["woorden"]):
            open_gezet.clear()
        else:
            for n in range(len(vers["woorden"])):
                beurt["nu"] = beurt.get("nu", 0) + 1
                beurt[n] = beurt["nu"]
            open_gezet.update(range(len(vers["woorden"])))
        teken()
        teken_uitleg()

    async def gelezen():
        stats = g.stats.setdefault("hebr_stats", {})
        e = stats.setdefault(LEES_SLEUTEL + vers["vers"], {"g": 0, "f": 0})
        e["g"] = int(e.get("g", 0)) + 1
        g.tel_dag()
        g.dagdoel_plus("hebreeuws")
        opgeslagen = await run.io_bound(g.bewaar)
        if opgeslagen:
            opslagmelding.text = "Voortgang opgeslagen"
        ui.navigate.to("/lezen/hebreeuws")

    ui.on("leeswoord", lambda e: tik(int(e.args)))

    alles_knop.on_click(alles)
    volgende.on_click(gelezen)
    teken()


# ============================================================== lezen (nog te bouwen)
@ui.page("/lezen")
def lezenpagina():
    g = _bewaakt()
    if not g:
        return
    heb = taal(g) == HEBREEUWS
    with ui.column().classes("inhoud w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Lezen").style("font-size:26px;font-weight:700")
            taalknop(g, "/lezen")
        if heb and hebreeuws.tenach_index():
            _boeken = hebreeuws.tenach_index()
            with ui.element("div").classes("kaart w-full").on(
                    "click", lambda: ui.navigate.to("/tenach")):
                with ui.row().classes("w-full items-center justify-between no-wrap"):
                    with ui.column().classes("gap-0").style("min-width:0"):
                        ui.label("Tenach doorbladeren").style(
                            f"color:{TEKST};font-size:16px;font-weight:600")
                        ui.label(f"de hele tekst — {len(_boeken)} boeken, "
                                 f"{sum(b['verzen'] for b in _boeken)} verzen").style(
                            f"color:{ZACHT};font-size:12.5px")
                    ui.label("›").style(f"color:{ZACHT};font-size:22px")
        if heb and hebreeuws.tenach_index():
            _naam, _strongs = heb_tekst_keuze(g)
            with ui.element("div").classes("kaart w-full").on(
                    "click", lambda: ui.navigate.to("/tenach/oefenen")):
                with ui.row().classes("w-full items-center justify-between no-wrap"):
                    with ui.column().classes("gap-0").style("min-width:0"):
                        ui.label("Een tekst oefenen").style(
                            f"color:{TEKST};font-size:16px;font-weight:600")
                        ui.label(f"nu: {_naam} · {len(_strongs)} woorden vooraan" if _naam
                                 else "kies een hoofdstuk; de app haalt de woorden eruit "
                                      "die je nog mist").style(
                            f"color:{ZACHT};font-size:12.5px")
                    ui.label("›").style(f"color:{ZACHT};font-size:22px")
        if heb and hebreeuws.laad_verzen():
            verzen = hebreeuws.laad_verzen()
            gelezen = heb_gelezen(g)
            with ui.element("div").classes("kaart w-full").on(
                    "click", lambda: ui.navigate.to("/lezen/hebreeuws")):
                with ui.row().classes("w-full items-center justify-between no-wrap"):
                    with ui.column().classes("gap-0"):
                        ui.label("Een vers lezen").style(
                            f"color:{TEKST};font-size:16px;font-weight:600")
                        ui.label(f"{len(verzen)} verzen uit de Tenach die je met deze "
                                 f"woordenschat aankan").style(
                            f"color:{ZACHT};font-size:12.5px")
                    with ui.row().classes("items-center gap-2 no-wrap"):
                        ui.label(f"{len(gelezen)} gelezen").style(
                            f"color:{MERK};font-size:13px;white-space:nowrap")
                        ui.label("›").style(f"color:{ZACHT};font-size:22px")
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


# Zonder manifest maakt Chrome van 'Toevoegen aan startscherm' een snelkoppeling met een
# letter als icoon; mét manifest een echte installatie met eigen icoon en naam. Dat de app
# nu al schermvullend opent komt van de apple-regel hierboven, die Chrome ook honoreert —
# dat is een oude gunst waar je niet op moet bouwen.
app.add_static_files("/static", "static")

MANIFEST = {
    "name": "Grieks — PThU",
    "short_name": "Grieks",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "orientation": "portrait",
    "background_color": INKT,
    "theme_color": INKT,
    "lang": "nl",
    "icons": [
        {"src": "/static/grieks-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/static/grieks-512.png", "sizes": "512x512", "type": "image/png"},
        {"src": "/static/grieks-512-maskable.png", "sizes": "512x512",
         "type": "image/png", "purpose": "maskable"},
    ],
}


# Eén klikafhandelaar voor alle leeswoorden, op de pagina als geheel. NiceGUI kan geen
# klik aan een los stukje html hangen, dus we vangen hem op en geven door wat er in het
# data-attribuut staat: een nummer bij het losse leesvers, een verwijzing bij de Tenach.
ui.add_body_html("""
<script>
  document.addEventListener('click', function (e) {
    const nr = e.target.closest('.versnr');
    if (nr) { emitEvent('leesvers', nr.dataset.v); return; }
    const el = e.target.closest('.leeswoord');
    if (!el) return;
    emitEvent('leeswoord', el.dataset.w !== undefined
                           ? el.dataset.w : parseInt(el.dataset.n, 10));
  });
</script>""", shared=True)


@app.get("/manifest.webmanifest")
def manifest():
    # Het eigen mediatype moet: met application/json slaat Chrome het manifest over.
    return JSONResponse(MANIFEST, media_type="application/manifest+json")


@app.on_disconnect
async def bewaar_bij_vertrek():
    """Sluit je de app of leg je hem weg, dan gaat wat er nog niet geschreven was alsnog
    naar de Sheet. Zonder dit kon je in de lichte versie tot vier antwoorden kwijtraken:
    daar wordt pas na elke vijfde beurt geschreven. bewaar() doet niets als er niets te
    schrijven valt, dus het kost geen extra schrijfbeurten."""
    for gebruiker in list(_sessies.values()):
        if gebruiker.sinds_opslag:
            try:
                await run.io_bound(gebruiker.bewaar, True)
            except Exception:                                    # noqa: BLE001
                pass          # lukt het niet, dan staat het nog in het geheugen


# Een hostingplatform (Render, Railway, Fly) geeft de poort mee via PORT; lokaal blijft
# het gewoon 8123. NiceGUI luistert buiten native-modus vanzelf op 0.0.0.0, dus dat hoeft
# hier niet apart. GRIEKS_ON_AIR=1 geeft een openbare URL via NiceGUI On Air — handig om
# de app even op je telefoon of op een ander netwerk te bekijken zonder te hosten.
_on_air = os.environ.get("GRIEKS_ON_AIR", "").strip()
# interactive-widget=resizes-content: klapt het toetsenbord open, dan krimpt de pagina
# zelf in plaats van dat het toetsenbord er overheen schuift. Zonder dit blijft de
# antwoordbalk op zijn oude plek staan en lijkt hij midden op het scherm te zweven.
# Het moet hier en niet in add_head_html: dan staan er twee viewport-regels in de kop
# en is het aan de browser welke wint.
ui.run(title="Grieks", dark=True, port=int(os.environ.get("PORT", 8123)),
       viewport="width=device-width, initial-scale=1, viewport-fit=cover, "
                "interactive-widget=resizes-content",
       reload=False, show=False, favicon="\U0001F4D6",
       on_air=(_on_air if _on_air not in ("", "0", "1") else _on_air == "1"),
       storage_secret=os.environ.get("GRIEKS_SESSIE_SLEUTEL", "grieks-lokaal-ontwikkelen"))
