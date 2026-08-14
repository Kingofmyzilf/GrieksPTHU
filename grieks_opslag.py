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

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

# Dezelfde dertien statistiek-dicts als de Streamlit-app, in dezelfde volgorde.
SPECS = [('vocab_stats', 'v_chunks'), ('gram_stats', 'g_chunks'), ('prod_stats', 'pr_chunks'),
         ('stam_stats', 'st_chunks'), ('struct_stats', 'sr_chunks'), ('dag_stats', 'd_chunks'),
         ('verwar_stats', 'vw_chunks'), ('ui_prefs', 'ui_chunks'), ('badges', 'bd_chunks'),
         ('dagdoel', 'dd_chunks'), ('actief_stats', 'af_chunks'), ('ontleed_stats', 'on_chunks'),
         ('klank_stats', 'kl_chunks')]
MAX_LEN = 40000
SCOREBORD = "Scorebord"


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
    try:
        cred = Credentials.from_service_account_info(inlog, scopes=SCOPES)
        _client = gspread.authorize(cred)
        _sheet = _client.open_by_url(adres) if adres.startswith("http") else _client.open_by_key(adres)
    except Exception as e:
        raise OpslagFout(f"Verbinden met Google Sheets mislukte: {e}") from e
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
            uit[sleutel] = _json_of_leeg(rij.get(sleutel, "{}"))
            continue
        tekst = "".join(str(rij.get(f"{sleutel}_{i}") or "") for i in range(n))
        if not tekst:
            raise OpslagFout(
                f"'{sleutel}' zegt {n} stukken te hebben maar ze zijn leeg — "
                "opslaan afgebroken om je voortgang niet te overschrijven.")
        uit[sleutel] = _json_of_leeg(tekst, streng=True, wat=sleutel)
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


def bewaar(gebruiker, stats, pogingen=3):
    """Voortgang wegschrijven. Probeert het bij een quota-fout een paar keer opnieuw."""
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


def schrijf_scorebord(gebruiker, samenvatting):
    """Werkt de eigen regel in het gedeelde Scorebord bij; laat de rest ongemoeid."""
    tab = _tab(SCOREBORD, maak=True)
    try:
        rijen = tab.get_all_records()
    except Exception:
        rijen = []
    rijen = [r for r in rijen
             if str(r.get('gebruikersnaam', '')).strip().lower() != str(gebruiker).strip().lower()]
    rijen.append({'gebruikersnaam': gebruiker, **samenvatting})
    kolommen = sorted({k for r in rijen for k in r}, key=lambda k: (k != 'gebruikersnaam', k))
    tab.clear()
    tab.update([kolommen] + [[r.get(k, "") for k in kolommen] for r in rijen], "A1")
    return True
