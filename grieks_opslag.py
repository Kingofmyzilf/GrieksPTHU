# -*- coding: utf-8 -*-
"""Opslag naar Google Sheets, zonder Streamlit.

Schrijft exact hetzelfde formaat als overhoring_web.py, zodat beide apps op dezelfde
Sheet werken en je heen en weer kunt zonder je voortgang te verliezen:

    werkblad  u_<schone_naam>     één rij per gebruiker
    kolommen  gebruikersnaam, <dict>_0, <dict>_1, ..., <dict>_chunks-teller

Inloggegevens komen uit dezelfde bron als bij Streamlit — een Google Cloud
service-account. Ze worden gezocht in deze volgorde:

  1. omgevingsvariabele GSHEETS_CREDENTIALS  (de service-account-JSON als tekst)
     plus GSHEETS_SPREADSHEET (de URL of sleutel van de Sheet)   -> voor online hosting
  2. .streamlit/secrets.toml, sectie [connections.gsheets]        -> voor lokaal draaien

Die tweede is precies het bestand dat Streamlit ook leest, dus lokaal hoef je niets
te veranderen. Zet dat bestand nooit in git (staat in .gitignore).
"""
import json
import os
import re
import time

try:
    # Virusscanners die https meelezen (Norton, ESET, Kaspersky) vervangen het certificaat
    # door een eigen exemplaar. Dat staat wél in de certificaatopslag van Windows, maar niet
    # in die van Python — vandaar 'CERTIFICATE_VERIFY_FAILED'. truststore laat Python de
    # opslag van het besturingssysteem gebruiken. Verificatie blijft dus gewoon aan staan.
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

# gspread is alleen nodig om écht met de Sheet te praten. De Streamlit-app importeert
# dit bestand voor samenvoeg_stats() en praat zelf via st-gsheets-connection; die mag
# hier niet op stuklopen als gspread er niet is.
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_ER = True
except ImportError:
    gspread = None
    Credentials = None
    GSPREAD_ER = False

SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

# Dezelfde veertien statistiek-dicts als de Streamlit-app, in dezelfde volgorde.
# Die volgorde en die namen moeten daar gelijk aan blijven: allebei de apps schrijven de
# héle rij weg, dus een sleutel die de ander niet kent wordt bij het volgende opslaan
# uitgewist. 'hebr_stats' is er als laatste bij gekomen voor de Hebreeuwse woordenschat;
# de Streamlit-app doet er niets mee maar draagt hem wel netjes door.
SPECS = [('vocab_stats', 'v_chunks'), ('gram_stats', 'g_chunks'), ('prod_stats', 'pr_chunks'),
         ('stam_stats', 'st_chunks'), ('struct_stats', 'sr_chunks'), ('dag_stats', 'd_chunks'),
         ('verwar_stats', 'vw_chunks'), ('ui_prefs', 'ui_chunks'), ('badges', 'bd_chunks'),
         ('dagdoel', 'dd_chunks'), ('actief_stats', 'af_chunks'), ('ontleed_stats', 'on_chunks'),
         ('klank_stats', 'kl_chunks'), ('hebr_stats', 'hb_chunks')]
MAX_LEN = 40000
SCOREBORD = "Scorebord"

# Statistieken waarvan de waarden de vorm {sleutel: {'g':.., 'f':.., 'streak':..}} hebben.
# Voor die vorm geldt de tel-regel bij het samenvoegen (zie samenvoeg_stats).
TELDICTS = {"vocab_stats", "stam_stats", "struct_stats", "actief_stats",
            "gram_stats", "prod_stats", "klank_stats", "ontleed_stats", "hebr_stats"}


class OpslagFout(Exception):
    """Opslaan of laden mislukte. De aanroeper beslist wat de gebruiker te zien krijgt."""


# --------------------------------------------------------------------------- inloggegevens
def _uit_secrets_toml(pad=".streamlit/secrets.toml"):
    if not os.path.exists(pad):
        return None, None
    try:
        import tomllib
    except ImportError:                                    # Python < 3.11
        return None, None
    with open(pad, "rb") as f:
        cfg = tomllib.load(f)
    blok = (cfg.get("connections", {}) or {}).get("gsheets") or cfg.get("gsheets")
    if not blok:
        return None, None
    sheet = blok.get("spreadsheet") or blok.get("url") or ""
    inlog = {k: v for k, v in blok.items() if k not in ("spreadsheet", "url", "worksheet")}
    return (inlog or None), sheet


def _uit_omgeving():
    ruw = os.environ.get("GSHEETS_CREDENTIALS")
    sheet = os.environ.get("GSHEETS_SPREADSHEET", "")
    if not ruw:
        return None, sheet
    try:
        return json.loads(ruw), sheet
    except json.JSONDecodeError as e:
        raise OpslagFout(f"GSHEETS_CREDENTIALS is geen geldige JSON: {e}") from e


_client = None
_sheet = None


def verbind(verplicht=True):
    """Maakt (eenmalig) verbinding. Geeft None als er geen gegevens zijn en verplicht=False."""
    global _client, _sheet
    if _sheet is not None:
        return _sheet
    if not GSPREAD_ER:
        if verplicht:
            raise OpslagFout("gspread is niet geïnstalleerd; zonder die module kan deze "
                             "app niet zelf met Google Sheets praten.")
        return None
    inlog, adres = _uit_omgeving()
    if not inlog:
        inlog, adres = _uit_secrets_toml()
    if not inlog:
        if verplicht:
            raise OpslagFout(
                "Geen Google-inloggegevens gevonden. Zet ze in .streamlit/secrets.toml "
                "onder [connections.gsheets], of in de omgevingsvariabelen "
                "GSHEETS_CREDENTIALS en GSHEETS_SPREADSHEET.")
        return None
    # De private key staat in TOML vaak met letterlijke \n erin.
    if isinstance(inlog.get("private_key"), str):
        inlog["private_key"] = inlog["private_key"].replace("\\n", "\n")
    adres = str(adres or "").strip().strip('"').strip("'")
    if not adres:
        raise OpslagFout(
            "De inloggegevens zijn er wel, maar er staat geen Sheet bij. Zet de URL of "
            "de sleutel van je Google Sheet in GSHEETS_SPREADSHEET (of in "
            "secrets.toml onder [connections.gsheets] als 'spreadsheet').")
    try:
        cred = Credentials.from_service_account_info(inlog, scopes=SCOPES)
        _client = gspread.authorize(cred)
        _sheet = _client.open_by_url(adres) if adres.startswith("http") else _client.open_by_key(adres)
    except Exception as e:
        # Kaal '<Response [404]>' zegt niets. Vertel wat er is geprobeerd — zonder de
        # sleutel zelf te tonen, want die melding komt op het scherm van de student.
        soort = "URL" if adres.startswith("http") else "sleutel"
        hint = ""
        if "404" in str(e):
            hint = (" Google vindt die Sheet niet. Klopt de waarde, en heb je de Sheet "
                    f"gedeeld met {inlog.get('client_email', 'het service-account')}?")
        elif "403" in str(e):
            hint = (" Google weigert de toegang. Deel de Sheet met "
                    f"{inlog.get('client_email', 'het service-account')} als bewerker.")
        raise OpslagFout(
            f"Verbinden met Google Sheets mislukte ({e}). Opgegeven als {soort} van "
            f"{len(adres)} tekens, beginnend met '{adres[:24]}'.{hint}") from e
    return _sheet


# --------------------------------------------------------------------------- rij <-> stats
def werkblad_naam(naam):
    """Zelfde regel als _ws_naam in overhoring_web.py — moet identiek blijven."""
    schoon = re.sub(r'[^0-9A-Za-z_]', '_', str(naam or ''))
    return ("u_" + schoon)[:95]


def bouw_rij(gebruiker, stats):
    """Statistiek-dicts -> één rij in het gechunkte kolomformaat."""
    rij = {'gebruikersnaam': gebruiker}
    for sleutel, teller in SPECS:
        tekst = json.dumps(stats.get(sleutel, {}) or {}, ensure_ascii=False)
        stukken = [tekst[i:i + MAX_LEN] for i in range(0, len(tekst), MAX_LEN)] or [""]
        for i, s in enumerate(stukken):
            rij[f"{sleutel}_{i}"] = s
        rij[teller] = len(stukken)
    return rij


def _json_of_leeg(tekst, streng=False, wat=""):
    """Leest JSON. Leeg is een geldige uitkomst; onleesbare inhoud waar wél iets staat
    is dat niet — dan zou doorgaan met een lege staat je voortgang overschrijven."""
    tekst = str(tekst or "").strip()
    if not tekst or tekst in ("{}", "nan", "None"):
        return {}
    try:
        gelezen = json.loads(tekst)
    except json.JSONDecodeError as e:
        if streng:
            raise OpslagFout(f"'{wat}' staat er onleesbaar in ({e}) — opslaan afgebroken "
                             "om je voortgang niet te overschrijven.") from e
        return {}
    return gelezen if isinstance(gelezen, dict) else {}


def _cel(rij, kolom):
    """Celtekst, met lege cellen als lege tekst. Een DataFrame-rij geeft een lege cel
    terug als NaN, en NaN is waar in een or-uitdrukking — zonder deze controle sluipt
    de tekst 'nan' midden in de JSON en is de hele rij onleesbaar."""
    waarde = rij.get(kolom)
    if waarde is None or waarde != waarde:          # NaN is ongelijk aan zichzelf
        return ""
    return str(waarde)


def lees_rij(rij):
    """Eén rij uit de Sheet -> statistiek-dicts. Verdraagt ontbrekende of stukke velden."""
    uit = {}
    for sleutel, teller in SPECS:
        try:
            # Google geeft een getalcel soms terug als '3.0' — net als de Streamlit-app
            # moeten we daar doorheen kijken, anders lezen we nul stukken en lijkt de
            # voortgang leeg (wat hem bij de eerstvolgende opslag zou wissen).
            n = int(float(rij.get(teller) or 0))
        except (TypeError, ValueError):
            n = 0
        if n <= 0:
            # Terugval op een ongechunkte kolom, zoals de oude opslag die kende.
            uit[sleutel] = _json_of_leeg(_cel(rij, sleutel) or "{}")
            continue
        tekst = "".join(_cel(rij, f"{sleutel}_{i}") for i in range(n))
        if not tekst:
            raise OpslagFout(
                f"'{sleutel}' zegt {n} stukken te hebben maar ze zijn leeg — "
                "opslaan afgebroken om je voortgang niet te overschrijven.")
        uit[sleutel] = _json_of_leeg(tekst, streng=True, wat=sleutel)
    return uit


# --------------------------------------------------------------------------- samenvoegen
def _pogingen(entry):
    """Hoe vaak dit item al is overhoord. Goed en fout tellen alleen maar op, dus dit
    getal loopt nooit terug — daarmee weet je welke van twee versies de nieuwste is."""
    if not isinstance(entry, dict):
        return -1
    try:
        return int(entry.get("g", 0) or 0) + int(entry.get("f", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _voeg_teldict_samen(oud, mijn):
    """Per item de versie met de meeste pogingen. Bij gelijkspel wint die van mij:
    dan heeft de ander niets aan dit item gedaan sinds ik inlogde."""
    uit = dict(oud or {})
    for sleutel, entry in (mijn or {}).items():
        if _pogingen(entry) >= _pogingen(uit.get(sleutel)):
            uit[sleutel] = entry
    return uit


def _voeg_dagstats_samen(oud, mijn):
    """Per dag het hoogste aantal. Een dagteller loopt alleen op."""
    uit = dict(oud or {})
    for dag, aantal in (mijn or {}).items():
        try:
            uit[dag] = max(int(uit.get(dag, 0) or 0), int(aantal or 0))
        except (TypeError, ValueError):
            uit[dag] = aantal
    return uit


def _voeg_verwar_samen(oud, mijn):
    """Verwarparen: {getoond: {verward: {n, laatst}}}. Anders dan de rest kan 'n' hier
    ook omlaag (een goed antwoord dempt de verwarring), dus tellen helpt niet. De regel
    is: de laatst bijgewerkte versie wint."""
    uit = {a: dict(b) for a, b in (oud or {}).items() if isinstance(b, dict)}
    for getoond, paren in (mijn or {}).items():
        if not isinstance(paren, dict):
            continue
        bestaand = uit.setdefault(getoond, {})
        for verward, rec in paren.items():
            ander = bestaand.get(verward) or {}
            if str(rec.get("laatst", "")) >= str(ander.get("laatst", "")):
                bestaand[verward] = rec
    return {a: b for a, b in uit.items() if b}


def _voeg_dagdoel_samen(oud, mijn):
    """Dagdoel heeft twee delen: 'config' (jouw instelling — de nieuwste wint per
    sleutel) en 'log' (wat je per dag deed — het hoogste aantal wint)."""
    uit = dict(oud or {})
    mijn = mijn or {}
    config = dict((uit.get("config") or {}))
    config.update(mijn.get("config") or {})
    log = {d: dict(v) for d, v in (uit.get("log") or {}).items() if isinstance(v, dict)}
    for dag, regel in (mijn.get("log") or {}).items():
        if not isinstance(regel, dict):
            continue
        samen = log.setdefault(dag, {})
        for soort, waarde in regel.items():
            try:
                samen[soort] = max(int(samen.get(soort, 0) or 0), int(waarde or 0))
            except (TypeError, ValueError):
                samen[soort] = waarde
    if config:
        uit["config"] = config
    if log:
        uit["log"] = log
    return uit


def samenvoeg_stats(in_sheet, van_mij):
    """Voegt mijn voortgang samen met wat er nu in de Sheet staat.

    Nodig omdat de Streamlit-app en de NiceGUI-app allebei de héle rij wegschrijven.
    Zonder samenvoegen wist wie het laatst opslaat alles wat de ander deed sinds diens
    inloggen — precies het geval waarin een streak 'niet opgeslagen' lijkt.

    De regels leunen erop dat de tellers alleen maar oplopen; zie de losse functies.
    Voor alles waar geen regel voor is (instellingen, badges) wint mijn versie per
    sleutel, en blijft staan wat ik niet ken.
    """
    uit = {}
    for sleutel, _teller in SPECS:
        oud, mijn = (in_sheet or {}).get(sleutel) or {}, (van_mij or {}).get(sleutel) or {}
        if not isinstance(oud, dict) or not isinstance(mijn, dict):
            uit[sleutel] = mijn or oud
        elif sleutel in TELDICTS:
            uit[sleutel] = _voeg_teldict_samen(oud, mijn)
        elif sleutel == "dag_stats":
            uit[sleutel] = _voeg_dagstats_samen(oud, mijn)
        elif sleutel == "verwar_stats":
            uit[sleutel] = _voeg_verwar_samen(oud, mijn)
        elif sleutel == "dagdoel":
            uit[sleutel] = _voeg_dagdoel_samen(oud, mijn)
        else:
            samen = dict(oud)
            samen.update(mijn)
            uit[sleutel] = samen
    return uit


# --------------------------------------------------------------------------- lezen/schrijven
def _tab(naam, maak=False):
    sheet = verbind()
    try:
        return sheet.worksheet(naam)
    except gspread.WorksheetNotFound:
        if not maak:
            return None
        return sheet.add_worksheet(title=naam, rows=4, cols=60)


def laad(gebruiker):
    """Voortgang van één gebruiker. Lege dicts als er nog niets staat."""
    tab = _tab(werkblad_naam(gebruiker))
    if tab is None:
        return {s: {} for s, _ in SPECS}
    try:
        rijen = tab.get_all_records()
    except Exception as e:
        raise OpslagFout(f"Lezen mislukte: {e}") from e
    if not rijen:
        return {s: {} for s, _ in SPECS}
    eigen = [r for r in rijen
             if str(r.get('gebruikersnaam', '')).strip().lower() == str(gebruiker).strip().lower()]
    return lees_rij(eigen[0] if eigen else rijen[0])


def huidige_stats(gebruiker):
    """Wat er op dit moment in de Sheet staat, of None als er niets bruikbaars staat.

    Twee soorten problemen, met een verschillende afloop:
      * het ophalen zelf mislukt (netwerk, quota) — dan wérpen we. Je weet niet wat er
        staat, dus schrijven zou de ander kunnen wissen. De voortgang blijft in het
        geheugen en de volgende beurt probeert het opnieuw.
      * de rij is er wél maar is onleesbaar — dan geven we None terug. Er valt niets te
        behouden, en gewoon schrijven maakt de rij weer heel. Voor eeuwig weigeren te
        bewaren zou hier de slechtste uitkomst zijn.
    """
    tab = _tab(werkblad_naam(gebruiker))
    if tab is None:
        return None
    try:
        rijen = tab.get_all_records()
    except Exception as e:
        raise OpslagFout(f"Lezen voor het samenvoegen mislukte: {e}") from e
    if not rijen:
        return None
    eigen = [r for r in rijen
             if str(r.get('gebruikersnaam', '')).strip().lower() == str(gebruiker).strip().lower()]
    try:
        return lees_rij(eigen[0] if eigen else rijen[0])
    except OpslagFout:
        return None


def bewaar(gebruiker, stats, pogingen=3, samenvoegen=True):
    """Voortgang wegschrijven. Probeert het bij een quota-fout een paar keer opnieuw.

    Eerst lezen, dan samenvoegen, dan schrijven. Dat moet, omdat de Streamlit-app op
    dezelfde rij werkt: zonder samenvoegen wist wie het laatst opslaat de voortgang van
    de ander sinds diens inloggen. Lukt het lezen niet, dan schrijven we niet — je
    voortgang blijft dan in het geheugen staan en de volgende beurt probeert het weer.
    """
    if samenvoegen:
        stats = samenvoeg_stats(huidige_stats(gebruiker), stats)
    rij = bouw_rij(gebruiker, stats)
    kolommen = list(rij)
    tab = _tab(werkblad_naam(gebruiker), maak=True)
    laatste = None
    for poging in range(pogingen):
        try:
            tab.clear()
            tab.update([kolommen, [rij[k] for k in kolommen]], "A1")
            return True
        except Exception as e:
            laatste = e
            if any(t in str(e) for t in ("429", "RESOURCE_EXHAUSTED", "Quota")):
                time.sleep(2 ** poging)      # even wachten en opnieuw
                continue
            break
    raise OpslagFout(f"Opslaan mislukte: {laatste}")


def lees_scorebord():
    """Het gedeelde Scorebord-tabblad voor de competitie. Lege lijst als het er niet is."""
    tab = _tab(SCOREBORD)
    if tab is None:
        return []
    try:
        return tab.get_all_records()
    except Exception:
        return []


def schrijf_scorebord(samenvatting):
    """Werkt de eigen regel in het gedeelde Scorebord bij en laat de rest ongemoeid.
    De sleutelkolom heet 'gebruiker', net als in de Streamlit-app, zodat beide apps
    dezelfde ranglijst vullen in plaats van twee halve."""
    naam = str(samenvatting.get('gebruiker', '')).strip()
    if not naam:
        return False
    sheet = verbind()
    try:
        tab = sheet.worksheet(SCOREBORD)
    except gspread.WorksheetNotFound:
        tab = sheet.add_worksheet(title=SCOREBORD, rows=100, cols=30)
        rijen = []
    else:
        try:
            rijen = tab.get_all_records()
        except Exception as e:
            # Niet schrijven op een blad dat we niet konden lezen: dan zouden we alle
            # klasgenoten uit de ranglijst gooien om er zelf één regel voor terug te zetten.
            raise OpslagFout(f"Scorebord lezen mislukte: {e}") from e
    rijen = [r for r in rijen
             if str(r.get('gebruiker', '')).strip().lower() != naam.lower()]
    rijen.append(dict(samenvatting))
    kolommen = sorted({k for r in rijen for k in r}, key=lambda k: (k != 'gebruiker', k))
    tab.clear()
    tab.update([kolommen] + [[r.get(k, "") for k in kolommen] for r in rijen], "A1")
    return True
