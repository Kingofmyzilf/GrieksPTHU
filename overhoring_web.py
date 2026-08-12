import streamlit as st
import streamlit.components.v1 as components
from streamlit_gsheets import GSheetsConnection
import json
import pandas as pd
import random as r_engine
import re
import math
import os
import unicodedata
import difflib
import functools
from datetime import datetime

# De app draait in de cloud op UTC-servers, terwijl de gebruiker in Nederland zit. Zonder deze
# omzetting liep alles 1-2 uur achter: 'vandaag' klapte te laat om, oefeningen van net na
# middernacht werden op de vorige dag geboekt en de dag-streak kon daardoor breken.
try:
    from zoneinfo import ZoneInfo
    _TIJDZONE = ZoneInfo("Europe/Amsterdam")
except Exception:
    _TIJDZONE = None

def _nu():
    """Huidige datum/tijd in de Nederlandse tijdzone (zonder tzinfo, zodat rekenen simpel blijft)."""
    if _TIJDZONE is not None:
        try:
            return datetime.now(_TIJDZONE).replace(tzinfo=None)
        except Exception:
            pass
    return datetime.now()

try:
    import fitz  # PyMuPDF: rendert de grammatica-slides
    FITZ_BESCHIKBAAR = True
except Exception:
    FITZ_BESCHIKBAAR = False

# --- CONFIGURATIE ---
st.set_page_config(page_title="Grieks Cloud Tutor", layout="wide")
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("Kan niet verbinden met Google Sheets.")

st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 10px; height: 3em; font-weight: bold; }
    .stTextInput>div>div>input { font-size: 20px; text-align: center; }
    .grieks-woord { font-size: 50px; font-weight: bold; color: #33ccff; text-align: center; padding: 20px; }
    .grieks-zin { font-size: 28px; line-height: 1.8; color: #ffffff; padding: 20px; background-color: #1e1e1e; border-radius: 10px; }
    .woord-bekend { color: #00ffff; font-weight: bold; border-bottom: 2px solid #00ffff; padding: 0 4px; }
    .woord-stamtijd { color: #d63384; font-weight: bold; border-bottom: 2px solid #d63384; padding: 0 4px; }
    .woord-onbekend { color: #aaaaaa; padding: 0 2px; }
    .grid-label { font-weight: bold; color: #33ccff; margin-bottom: 5px; }
    .rooster-input>div>div>input { font-size: 16px; padding: 5px; }
    
    .mobile-tooltip {
        position: relative;
        display: inline-block;
        cursor: pointer;
        outline: none;
    }
    .mobile-tooltip .tooltiptext {
        visibility: hidden;
        width: max-content;
        max-width: 240px;
        background-color: #2b2b2b;
        color: #f8f9fa;
        text-align: center;
        border-radius: 8px;
        padding: 8px 12px;
        position: absolute;
        z-index: 9999;
        bottom: 125%;
        left: 50%;
        transform: translateX(-50%);
        opacity: 0;
        transition: opacity 0.2s;
        font-size: 16px;
        font-weight: normal;
        line-height: 1.4;
        box-shadow: 0px 4px 12px rgba(0,0,0,0.5);
        pointer-events: none; 
        white-space: pre-wrap;
    }
    .mobile-tooltip .tooltiptext::after {
        content: "";
        position: absolute;
        top: 100%;
        left: 50%;
        margin-left: -6px;
        border-width: 6px;
        border-style: solid;
        border-color: #2b2b2b transparent transparent transparent;
    }
    .mobile-tooltip:hover .tooltiptext,
    .mobile-tooltip:focus .tooltiptext,
    .mobile-tooltip:active .tooltiptext {
        visibility: visible;
        opacity: 1;
    }
    </style>
    """, unsafe_allow_html=True)

# --- HELPER FUNCTIES ---
def forceer_focus():
    components.html(
        """
        <script>
        setTimeout(function() {
            const inputs = window.parent.document.querySelectorAll('.stTextInput input');
            if (inputs.length > 0) {
                inputs[0].focus();
            }
        }, 100);
        </script>
        """, height=0
    )

def spring_naar_tab(zoekterm):
    """Klikt via JS het tabblad aan waarvan de titel 'zoekterm' bevat (Streamlit kan niet zelf
    programmatisch van tab wisselen). Gebruikt voor het dagblok: automatisch naar de oefening."""
    veilig = json.dumps(str(zoekterm))
    components.html(
        "<script>(function(){var d=window.parent.document;"
        "function k(){var t=d.querySelectorAll('button[role=\"tab\"]');"
        "for(var i=0;i<t.length;i++){if((t[i].innerText||'').indexOf(" + veilig + ")>-1){t[i].click();return true;}}"
        "return false;}"
        "if(!k()){setTimeout(k,250);setTimeout(k,600);}})();</script>",
        height=0,
    )

def audio_knop(fonetisch, key=""):
    """Spreekt de Erasmiaanse transliteratie uit via de browser (Web Speech API).
    We gebruiken bewust de fonetische spelling (bv. 'logos', 'houtos') i.p.v. het Griekse
    schrift: Modern-Griekse TTS-stemmen volgen de Nieuwgriekse klankleer (η/υ/ει → 'ie'),
    wat botst met de Erasmiaanse uitspraak die de cursus hanteert."""
    if not fonetisch:
        return
    veilig = (str(fonetisch).replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
              .replace("\n", " ").replace("\r", " "))
    components.html(
        f"""
        <button id="_btn_{key}" onclick="_spreek_{key}()" style="
            background:#0e5a8a; color:#fff; border:none; border-radius:6px;
            padding:6px 14px; font-size:15px; cursor:pointer; margin-top:4px;">
            🔊 Uitspraak
        </button>
        <script>
        // Stemmen laden asynchroon (vooral op mobiel) — vast alvast aanzwengelen.
        try {{ if (window.speechSynthesis) window.speechSynthesis.getVoices(); }} catch (e) {{}}
        function _spreek_{key}() {{
            try {{
                if (!window.speechSynthesis) {{ alert("Uitspraak wordt niet ondersteund in deze browser."); return; }}
                var tekst = "{veilig}";
                var gedaan = false;
                var zeg = function() {{
                    if (gedaan) return; gedaan = true;
                    var u = new SpeechSynthesisUtterance(tekst);
                    u.rate = 0.85; u.pitch = 1.0; u.lang = "nl-NL";
                    var stemmen = window.speechSynthesis.getVoices() || [];
                    // neutrale (niet-nieuwgriekse) stem kiezen als die er is
                    var voorkeur = stemmen.find(function(v) {{ return /en-|nl-|de-/i.test(v.lang); }});
                    if (voorkeur) u.voice = voorkeur;
                    window.speechSynthesis.cancel();
                    window.speechSynthesis.speak(u);
                }};
                var stemmen = window.speechSynthesis.getVoices();
                if (!stemmen || stemmen.length === 0) {{
                    // wacht tot de stemmen geladen zijn; met een tijd-fallback als het event niet vuurt
                    window.speechSynthesis.onvoiceschanged = zeg;
                    setTimeout(zeg, 300);
                }} else {{
                    zeg();
                }}
            }} catch (e) {{ console.log("TTS niet beschikbaar:", e); }}
        }}
        </script>
        """, height=44
    )

def fonetisch_uit_translit(tekst):
    """Maakt van de academische transliteratie (Iēsou, Christou, huiou) een leesregel die een
    Nederlandse/Engelse/Duitse TTS-stem zo Erasmiaans mogelijk uitspreekt: macrons/streepjes weg
    (ē→e, ō→o) en 'ch' → 'kh' zodat de χ niet als het Engelse 'ch' (church) klinkt."""
    s = unicodedata.normalize('NFD', str(tekst or ''))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')  # macrons + accenten weg
    return s.replace('ch', 'kh').replace('Ch', 'Kh')

def bijbelzin_fonetisch(zin):
    """Fonetische leesregel voor een hele Bijbelzin (lijst van woord-dicts met 'transliteratie')."""
    delen = [fonetisch_uit_translit(w.get('transliteratie', '')) for w in (zin or [])
             if str(w.get('transliteratie', '') or '').strip()]
    return " ".join(delen).strip()

def veilig_les_nummer(item):
    try: return int(item.get('les', 1))
    except: return 1

def vier_fase_overgang(oude_streak, nieuwe_streak, label):
    """Toont een felicitatie-toast wanneer een item een nieuwe leerfase-drempel passeert.
    Drempels: 1 (in training), 16 (beheerst), 30 (mastery)."""
    try:
        for drempel, boodschap, icoon in [
            (30, f"🏆 Mastery! {label} zit nu écht vast.", "🏆"),
            (16, f"🎉 {label} is nu Beheerst!", "🎉"),
            (1,  f"🌱 {label} staat nu In Training.", "🌱"),
        ]:
            if oude_streak < drempel <= nieuwe_streak:
                st.toast(boodschap, icon=icoon)
                if drempel == 30:
                    st.balloons()
                break
    except Exception:
        pass

def naar_grieks_transliteratie(tekst):
    mapping = { 'a': 'α', 'b': 'β', 'g': 'γ', 'd': 'δ', 'e': 'ε', 'z': 'ζ', 'h': 'η', 'q': 'θ', 'i': 'ι', 'k': 'κ', 'l': 'λ', 'm': 'μ', 'n': 'ν', 'c': 'ξ', 'o': 'ο', 'p': 'π', 'r': 'ρ', 's': 'σ', 't': 'τ', 'u': 'υ', 'f': 'φ', 'x': 'χ', 'y': 'ψ', 'w': 'ω' }
    res = ""
    tekst = str(tekst).lower().strip()
    for char in tekst: res += mapping.get(char, char)
    # Alleen de LAATSTE sigma wordt een slot-sigma (ς); interne sigma's blijven σ.
    if res.endswith('σ'):
        res = res[:-1] + 'ς'
    return res

@functools.lru_cache(maxsize=200000)
def normaliseer_accent(woord):
    if pd.notna(woord) and str(woord).strip() != "":
        w = str(woord).strip().lower()
        w = ''.join(c for c in unicodedata.normalize('NFD', w) if unicodedata.category(c) != 'Mn')
        w = w.replace('a', 'α').replace('e', 'ε').replace('i', 'ι').replace('o', 'ο').replace('u', 'υ')
        w = w.replace('(ν)', '').replace('(ν', '').replace('ν)', '')
        return w.strip()
    return ""

def grieks_vorm_ok(typed, correct):
    """Tolerante vergelijking van een Griekse vorm: accenten/leestekens genegeerd, Latijnse óf Griekse
    invoer, en elk deel van een 'x / y'-vorm (gescheiden door / , of ;) telt als goed."""
    t_lat = normaliseer_accent(naar_grieks_transliteratie(str(typed)))
    t_gr = normaliseer_accent(str(typed))
    if not t_lat and not t_gr:
        return False
    for deel in re.split(r'[\/,;]', str(correct)):
        d = normaliseer_accent(deel.strip())
        if d and (d == t_lat or d == t_gr):
            return True
    return False

def deconstrueer_stamtijd_live(vorm, tijd_diathese, praesens=None):
    """Splitst een stamtijdvorm in (stam, uitgang).

    Mét de praesensvorm erbij wordt de stamgrens bepaald door de échte overeenkomst met de
    praesensstam (na aftrek van het augment) — dat is veel betrouwbaarder dan achteraan een
    uitgang wegknippen. Zonder praesens (of als de stammen niet op elkaar lijken, zoals bij
    suppletie) valt hij terug op de oude uitgangenlijst."""
    if not vorm or vorm in ["n.v.t.", "---", "-"]: return "", ""
    # BELANGRIJK: een deel van de data staat in NFD (losse accenttekens). Zonder deze normalisatie
    # mislukt elke vergelijking met de NFC-uitgangen hieronder en krijg je een onzinnige opsplitsing.
    v_schoon = unicodedata.normalize('NFC', str(vorm).strip())
    if praesens:
        try:
            v_nfc = v_schoon
            vk, pk = _opb_kaal(v_nfc), _opb_kaal(praesens)
            rest, _aug = _opb_zonder_augment(vk, pk)
            pstam = pk[:-4] if pk.endswith("ομαι") else (pk[:-1] if pk.endswith("ω") else pk)
            n = _opb_prefix_len(rest, pstam)
            # Alleen gebruiken als de stam echt herkenbaar is én er een uitgang overblijft.
            if n >= 2 and len(vk) == len(v_nfc):
                grens = (len(vk) - len(rest)) + n
                if 0 < grens < len(v_nfc):
                    return v_nfc[:grens], v_nfc[grens:]
        except Exception:
            pass
    if tijd_diathese == "Futurum Actief/Medium": uitgangen = ["θήσομαι", "ήσομαι", "σομαι", "οῦμαι", "ομαι", "σω", "ψω", "ξω", "ῶ", "ω"]
    elif tijd_diathese == "Aoristus Actief/Medium": uitgangen = ["σάμην", "άμην", "όμην", "σα", "ψα", "ξα", "ον", "αν", "ην", "α", "ν"]
    elif tijd_diathese == "Aoristus Passief": uitgangen = ["θην", "ην"]
    elif tijd_diathese == "Perfectum Actief": uitgangen = ["κα", "α"]
    elif tijd_diathese == "Perfectum Medium/Passief": uitgangen = ["σμαι", "μμαι", "γμαι", "ημαι", "ειμαι", "ωμαι", "αμαι", "μαι"]
    else: return v_schoon, ""

    for u in uitgangen:
        u = unicodedata.normalize('NFC', u)
        if v_schoon.endswith(u):
            knip = len(v_schoon) - len(u)
            stam = v_schoon[:knip]
            uitgang = v_schoon[knip:]
            if len(stam) > 0: return stam, uitgang
    return v_schoon, ""
    
def levenshtein(s1, s2):
    if len(s1) < len(s2): return levenshtein(s2, s1)
    if len(s2) == 0: return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]

def check_betekenis(ingevuld, correcte_zin):
    ingevuld = str(ingevuld).lower().strip()
    correcte_zin = str(correcte_zin).lower().strip()
    if not ingevuld: return False

    def is_match(user_input, target):
        u = user_input.strip()
        t = target.strip()
        if not u or not t: return False
        if u == t: return True
        if len(t) > 4 and levenshtein(u, t) <= 1: return True
        if len(t) > 8 and levenshtein(u, t) <= 2: return True
        return False

    if is_match(ingevuld, correcte_zin): return True

    # HIER IS DE SLASH TOEGEVOEGD: / en ; worden direct synoniem aan een komma
    correcte_zin_genormaliseerd = correcte_zin.replace(';', ',').replace('/', ',')

    delen_ruw = [d.strip() for d in correcte_zin_genormaliseerd.split(',')]
    for d in delen_ruw:
        if is_match(ingevuld, d): return True

    schoon = re.sub(r'\([^)]*\)', '', correcte_zin_genormaliseerd)
    schoon = re.sub(r'\[[^\]]*\]', '', schoon)
    schoon = re.sub(r'\{[^}]*\}', '', schoon)
    schoon = schoon.replace('=', '').replace('*', '').replace('+', '')

    delen_schoon = [d.strip() for d in schoon.split(',') if d.strip()]
    for d in delen_schoon:
        if is_match(ingevuld, d): return True

    ingevuld_puur = re.sub(r'[^\w\s]', '', ingevuld).strip()
    for d in delen_schoon:
        d_puur = re.sub(r'[^\w\s]', '', d).strip()
        if d_puur and is_match(ingevuld_puur, d_puur): return True

    return False

def check_bijbel_parsing_uitgebreid(p_soort, p_naam, p_get, p_ges, p_tijd, p_wijs, p_diat, p_pers, bsb_info):
    info = bsb_info 
    if p_soort:
        if p_soort == "Overig":
            if any(x in info for x in ["Zelfst. nw.", "Werkwoord", "Bijv. nw.", "Lidwoord", "Voornaamwoord"]): return False
        elif p_soort not in info: return False
    
    gt_map = {"ev": "ev", "mv": "mv"}
    gs_map = {"M": "mannelijk", "V": "vrouwelijk", "O": "onzijdig"}
    
    if p_soort in ["Zelfst. nw.", "Bijv. nw.", "Lidwoord", "Voornaamwoord"]:
        if p_naam and p_naam not in info and p_naam != "N.v.t.": return False
        if p_ges and p_ges != "N.v.t." and gs_map.get(p_ges, "") not in info: return False
        if p_get and p_get != "N.v.t." and gt_map.get(p_get, "") not in info: return False
    elif p_soort == "Werkwoord":
        if p_tijd and p_tijd not in info: return False
        if p_wijs and p_wijs not in info: return False
        if p_diat:
            if p_diat == "Medium/Passief":
                if "Medium" not in info and "Passief" not in info: return False
            elif p_diat not in info: return False
        if p_wijs == "Participium":
            if p_naam and p_naam not in info and p_naam != "N.v.t.": return False
            if p_ges and p_ges != "N.v.t." and gs_map.get(p_ges, "") not in info: return False
            if p_get and p_get != "N.v.t." and gt_map.get(p_get, "") not in info: return False
        else:
            pers_map = {"1e": "1e pers.", "2e": "2e pers.", "3e": "3e pers."}
            if p_pers and p_pers != "N.v.t." and pers_map.get(p_pers, "") not in info: return False
            if p_get and p_get != "N.v.t." and gt_map.get(p_get, "") not in info: return False
    return True

# --- ONTLEED-TRAINER: helpers ---
_ONTLEED_KLEUR = {"Nom": "#33ccff", "Gen": "#28a745", "Dat": "#6f42c1", "Acc": "#dc3545", "Voc": "#fd7e14"}
_ONTLEED_GES = {"M": "mannelijk", "V": "vrouwelijk", "O": "onzijdig"}
_ONTLEED_STEUN = {
    # Naamvallen — functie + vertaling (uit 'functies van naamvallen')
    "Nom": "**Nominativus** — onderwerp of naamwoordelijk deel van het gezegde: 'de/het …'.",
    "Gen": "**Genitivus** — bijvoeglijke bepaling (zegt iets over een naamwoord): vaak 'van …'.",
    "Dat": "**Dativus** — meewerkend voorwerp ('aan/voor …') óf bijwoordelijke bepaling ('met/door …').",
    "Acc": "**Accusativus** — lijdend voorwerp (object); ook bijw. bepaling van tijdsduur/lengte.",
    "Voc": "**Vocativus** — aanspreekvorm: 'o …!'.",
    # Tempora — aspect + Nederlandse tijd (uit 'aspecten tempora')
    "Praesens": "**Praesens** — onvoltooid/duratief in het heden → **o.t.t.** (kan verteltijd zijn: praesens historicum → o.v.t.).",
    "Imperfectum": "**Imperfectum** — onvoltooid/duratief/herhaald in verleden of achtergrond → **o.v.t.**",
    "Futurum": "**Futurum** — toekomst → 'zal/zullen …'.",
    "Aoristus": "**Aoristus** — voltooid/punctueel/eenmalig in verleden → **o.v.t.** (soms ingressief of gnomisch → o.t.t.).",
    "Perfectum": "**Perfectum** — verleden met resultaat in het heden → **v.t.t.** (nadruk kan op verleden (o.v.t.) of heden (o.t.t.) liggen).",
    "Plusquamperfectum": "**Plusquamperfectum** — verder verleden met resultaat in verleden → **v.v.t.**",
    # Diathese
    "Actief": "**Actief** — onderwerp doet de handeling.",
    "Passief": "**Passief** — onderwerp ondergáát de handeling: 'wordt/werd ge…'.",
    "Medium": "**Medium** — handeling terug op het onderwerp zelf / in eigen belang ('(voor) zichzelf').",
    # Wijzen / constructies
    "Participium": "**Participium** — deelwoord; vertaal vaak met een bijzin ('terwijl/nadat/omdat …'). Participium in de genitief + naamwoord in de genitief = **genitivus absolutus** (bijzin, ingeleid door voegwoord).",
    "Infinitivus": "**Infinitivus** — 'te doen / het doen'. Gesubstantiveerd + voorzetsel wordt een bijzin: διά+acc='omdat', εἰς+acc='om te/zodat', ἐν+dat='terwijl/toen', πρό+gen='voordat', μετά+acc='nadat', πρός+acc='om te'.",
    "Conjunctivus": "**Conjunctivus** — aansporing/doel/mogelijkheid: 'laten we …' (adhortativus), 'opdat …' (finalis, na ἵνα/ὅπως/ὡς), verbod met μή. Met ἄν: generalis/futuralis.",
    "Imperativus": "**Imperativus** — gebiedende wijs: 'doe!'.",
    "Optativus": "**Optativus** — wens of (met ἄν) mogelijkheid: 'moge …' / 'zou(den) kunnen/willen'.",
    "Indicativus": "**Indicativus** — de 'gewone' mededelende wijs.",
}

# Vertaling per tempus+diathese van het participium (nom. mann. ev.), uit G38.
_ONTLEED_PTC_VERT = {
    ("Praesens", "Actief"): "λύων → 'losmakend'",
    ("Futurum", "Actief"): "λύσων → 'zullende losmaken'",
    ("Aoristus", "Actief"): "λύσας → 'losmakend' / 'hebbende losgemaakt'",
    ("Perfectum", "Actief"): "λελυκώς → 'hebbende losgemaakt'",
    ("Praesens", "Medium"): "λυόμενος → '(voor) zichzelf losmakend' / 'wordende losgemaakt'",
    ("Aoristus", "Passief"): "λυθείς → 'wordende/zijnde losgemaakt'",
    ("Futurum", "Passief"): "λυθησόμενος → 'zullende losgemaakt worden'",
}

def _ontleed_type(info):
    """Woordtype voor de ontleed-trainer: alleen werkwoorden en naamwoorden zijn oefenbaar."""
    info = info or ""
    if "Werkwoord" in info:
        return "ptc" if "Participium" in info else "ww"
    if any(x in info for x in ["Zelfst.", "Bijv.", "Voornaamwoord"]):
        return "naam"
    return None

def _ontleed_vertaalhulp(info):
    """Alleen de relevante vertaalregels voor dit woord: naamval-functie, óf (bij een werkwoord)
    wijs/tijd/diathese (+ voorbeeld-vertaling van het participium)."""
    info = info or ""
    regels = []
    nv = _ontleed_deel_correct('naamval', info)
    if "Werkwoord" in info:
        for dim in ('wijs', 'tijd', 'diathese'):
            w = _ontleed_deel_correct(dim, info)
            if w in _ONTLEED_STEUN and _ONTLEED_STEUN[w] not in regels:
                regels.append(_ONTLEED_STEUN[w])
        if "Participium" in info:
            _v = _ONTLEED_PTC_VERT.get((_ontleed_deel_correct('tijd', info), _ontleed_deel_correct('diathese', info)))
            if _v:
                regels.append(f"**Voorbeeld (participium):** {_v}")
            if nv in _ONTLEED_STEUN:
                regels.append(_ONTLEED_STEUN[nv])
    elif nv in _ONTLEED_STEUN:
        regels.append(_ONTLEED_STEUN[nv])
    return regels

# ==========================================================================================
# OPBOUW & SAMENTREKKINGEN — legt bij élke vorm uit wat er met de klanken gebeurd is
# (verba contracta volgens G20, σ-samensmelting, augment, 3e-declinatie-stam).
# Uitgangspunt: liever zwijgen dan iets beweren dat niet klopt. Elke bewering wordt eerst
# getoetst aan de vorm zelf (staat de verlengde klinker/de ψ/ξ er ook echt?).
# ==========================================================================================

# Accenten strippen MAAR de iota subscriptum (U+0345) behouden — ᾳ ≠ α in de G20-tabel.
_OPB_ACCENTEN = {'́', '̀', '͂', '̓', '̔', '̈', '̄', '̆'}

def _opb_norm(s):
    """Kleine letters, accenten/spiritus weg, maar de iota subscriptum blijft staan."""
    s = unicodedata.normalize('NFD', str(s or '').strip().lower())
    s = ''.join(c for c in s if c not in _OPB_ACCENTEN)
    return unicodedata.normalize('NFC', s).replace('(ν)', '').strip()

def _opb_kaal(s):
    """Álle diakritiek weg, ook de iota subscriptum — voor stam-vergelijkingen."""
    s = unicodedata.normalize('NFD', str(s or '').strip().lower())
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn')

# G20 Verba contracta — de volledige samentrekkingstabel, inclusief de η-kolom.
G20_CONTRACTA = {
    'ε': [("ε + ε", "ει"), ("ε + ει", "ει"), ("ε + η", "η"), ("ε + ο", "ου"), ("ε + ου", "ου"), ("ε + ω", "ω")],
    'α': [("α + ε", "α"), ("α + ει", "ᾳ"), ("α + η", "ᾳ"), ("α + ο", "ω"), ("α + ου", "ω"), ("α + ω", "ω")],
    'ο': [("ο + ε", "ου"), ("ο + ει", "οι"), ("ο + η", "οι"), ("ο + ο", "ου"), ("ο + ου", "ου"), ("ο + ω", "ω")],
    'η': [("η + ε", "η"), ("η + ει", "ῃ"), ("η + η", "ῃ"), ("η + ο", "ω"), ("η + ου", "ω"), ("η + ω", "ω")],
}
# De infinitief laat de vier stammen mooi naast elkaar zien.
G20_INFINITIEF = {'α': "τιμα + εν → τιμᾶν", 'ε': "φιλε + εν → φιλεῖν",
                  'ο': "δηλο + εν → δηλοῦν", 'η': "ζη + εν → ζῆν"}
# Werkwoorden op -άω die tóch naar η samentrekken.
_ETA_CONTRACTA = {"ζαω", "πειναω", "διψαω", "χραομαι"}

_OPB_VOORVOEGSELS = ["προσ", "παρα", "περι", "κατα", "μετα", "ἀνα", "ἀπο", "ἐπι", "ὑπερ", "ὑπο",
                     "δια", "συν", "ἐκ", "ἐν", "εἰς", "προ", "ἀντι", "ἀμφι", "ἀφ", "ἀπ", "ἐξ",
                     "καθ", "μεθ", "παρ", "ἐπ", "ὑπ", "ἀν", "συγ", "συμ", "ἐγ", "ἐμ"]
_OPB_TIJD_MET_AUGMENT = ("Imperfectum", "Aoristus", "Plusquamperfectum")

# Voorzetsel-voorvoegsels met hun weergave en kernbetekenis, voor de woordopbouw bij de
# woordenschat (samengestelde woorden). Sleutels zijn accent-loos (zoals _opb_kaal ze maakt).
_VOORZETSEL_INFO = {
    "απο": ("ἀπό", "van(af), weg"), "απ": ("ἀπό", "van(af), weg"), "αφ": ("ἀπό", "van(af), weg"),
    "εκ": ("ἐκ", "uit"), "εξ": ("ἐκ", "uit"),
    "εισ": ("εἰς", "in, naar"),
    "εν": ("ἐν", "in"), "εγ": ("ἐν", "in"), "εμ": ("ἐν", "in"),
    "προσ": ("πρός", "naar…toe, bij"),
    "προ": ("πρό", "voor(af)"),
    "παρα": ("παρά", "naast, langs, bij"), "παρ": ("παρά", "naast, langs, bij"),
    "περι": ("περί", "rondom, over"),
    "κατα": ("κατά", "neer, tegen, volgens"), "καθ": ("κατά", "neer, tegen, volgens"),
    "μετα": ("μετά", "met, na"), "μεθ": ("μετά", "met, na"),
    "ανα": ("ἀνά", "omhoog, opnieuw"),
    "επι": ("ἐπί", "op, bij, tegen"), "επ": ("ἐπί", "op, bij, tegen"), "εφ": ("ἐπί", "op, bij, tegen"),
    "υπερ": ("ὑπέρ", "boven, voor"),
    "υπο": ("ὑπό", "onder"), "υπ": ("ὑπό", "onder"), "υφ": ("ὑπό", "onder"),
    "δια": ("διά", "door(heen), uiteen"),
    "συν": ("σύν", "samen, met"), "συγ": ("σύν", "samen, met"), "συμ": ("σύν", "samen, met"),
    "αντι": ("ἀντί", "tegen(over), in plaats van"),
    "αμφι": ("ἀμφί", "aan beide kanten"),
}

def woord_opbouw(lemma):
    """Ontleedt een woordenboekvorm in voorzetsel-voorvoegsel + grondwoord — MAAR alleen als dat
    grondwoord zelf ook in de woordenlijst staat (bv. εἰσέρχομαι = εἰς + ἔρχομαι). Zo zie je het
    verband met een woord dat je al kent, zonder dat de app een etymologie verzint.

    Geeft een dict {voorzetsel, betekenis, grondwoord} terug, of None."""
    lk = _opb_kaal(lemma)
    if len(lk) < 5:
        return None
    data = st.session_state.get('data') or []
    idx = st.session_state.get('_lemma_kaal_idx')
    if not isinstance(idx, dict) or idx.get('_n') != len(data):
        idx = {'_n': len(data)}
        for w in data:
            g = str(w.get('grieks', '') or '')
            if g:
                idx.setdefault(_opb_kaal(g), g)
        st.session_state._lemma_kaal_idx = idx
    for p in sorted(_VOORZETSEL_INFO, key=len, reverse=True):
        if not lk.startswith(p) or len(lk) - len(p) < 3:
            continue
        rest = lk[len(p):]
        # Het grondwoord moet exact een ander bekend woord zijn (geen verzonnen stam).
        grond = idx.get(rest)
        if grond and _opb_kaal(grond) != lk:
            weer, bet = _VOORZETSEL_INFO[p]
            return {"voorzetsel": weer, "betekenis": bet, "grondwoord": grond}
    return None

def _opb_prefix_len(a, b):
    n = 0
    while n < len(a) and n < len(b) and a[n] == b[n]:
        n += 1
    return n

def _opb_split_voorvoegsel(lemma_kaal):
    """(voorvoegsel, rest) als het lemma met een voorzetsel-voorvoegsel begint."""
    for p in sorted(_OPB_VOORVOEGSELS, key=len, reverse=True):
        pk = _opb_kaal(p)
        if lemma_kaal.startswith(pk) and len(lemma_kaal) > len(pk) + 2:
            return pk, lemma_kaal[len(pk):]
    return "", lemma_kaal

def opb_contracta_stamklinker(lemma):
    """'α'/'ε'/'ο'/'η' als dit lemma een verbum contractum is, anders None."""
    lk = _opb_kaal(lemma)
    if not lk.endswith("ω") and not lk.endswith("ομαι"):
        return None
    if lk in _ETA_CONTRACTA:
        return 'η'
    kern = lk[:-4] + "ω" if lk.endswith("ομαι") else lk
    if kern.endswith("αω"): return 'α'
    if kern.endswith("εω"): return 'ε'
    if kern.endswith("οω"): return 'ο'
    return None

def _opb_zonder_augment(vormk, lemmak):
    """Haalt (indien herkenbaar) het augment van een vorm af → (rest, uitleg|None)."""
    vf, lf = vormk, lemmak
    pre_l, rest_l = _opb_split_voorvoegsel(lf)
    if pre_l:
        # Samengesteld werkwoord: het augment zit ná het voorvoegsel (ἀπο + ἐ + θαν → ἀπέθανον).
        kand = [pre_l] + ([pre_l[:-1]] if len(pre_l) > 2 and pre_l[-1] in "οαε" else [])
        for pv in kand:
            if pv and vf.startswith(pv):
                staart = vf[len(pv):]
                if staart.startswith("ε") and not rest_l.startswith("ε"):
                    return pv + staart[1:], (f"samengesteld werkwoord: het augment **ε-** staat *ná* het "
                                             f"voorvoegsel (**{pre_l}-** + **ἐ-** + stam)")
                if staart and rest_l and staart[0] in "ηω" and rest_l[0] in "αεο":
                    return pv + rest_l[0] + staart[1:], (f"samengesteld werkwoord: de beginklinker van de stam is "
                                                         f"verlengd als augment (**{rest_l[0]} → {staart[0]}**), "
                                                         f"ná het voorvoegsel **{pre_l}-**")
    if vf.startswith("ε") and not lf.startswith("ε"):
        return vf[1:], "de **ε-** vooraan is het augment van de verleden tijd"
    for van, naar in (("αι", "ῃ"), ("ει", "ῃ"), ("αυ", "ηυ"), ("α", "η"), ("ε", "η"), ("ο", "ω")):
        if lf.startswith(van) and vf.startswith(_opb_kaal(naar)):
            return van + vf[len(_opb_kaal(naar)):], f"de beginklinker is verlengd als augment: **{van} → {naar}**"
    return vf, None

def opb_analyse_contractie(vorm, lemma, parsing_info=""):
    """(stamklinker, [passende G20-combo's], losse_uitleg) voor een verbum contractum."""
    sk = opb_contracta_stamklinker(lemma)
    if not sk:
        return None, [], None
    info = parsing_info or ""
    tijd = next((t for t in ["Praesens", "Imperfectum", "Futurum", "Aoristus", "Perfectum",
                             "Plusquamperfectum"] if t in info), "")
    lk = _opb_kaal(lemma)
    stam = lk[:-1] if lk.endswith("ω") else (lk[:-4] if lk.endswith("ομαι") else lk)
    stam_zk = stam[:-1] if stam and stam[-1] in "αεοη" else stam
    vkaal = _opb_kaal(vorm)
    rest_k, _aug = _opb_zonder_augment(vkaal, lk)
    if tijd and tijd not in ("Praesens", "Imperfectum"):
        # Buiten de praesensstam trekt er niets samen: de stamklinker rékt. Alleen beweren als die
        # verlengde klinker er ook echt staat (anders: eigen stam/suppletie). Géén stamklinker
        # teruggeven, want dan zou de G20-tabel getoond worden terwijl die hier niet speelt.
        lang = {'α': 'η', 'ε': 'η', 'ο': 'ω', 'η': 'η'}[sk]
        kort = 'α' if sk == 'η' else sk
        if not rest_k.startswith(stam_zk + lang):
            return None, [], None
        return None, [], (f"Hier trekt niets samen: buiten praesens/imperfectum **rekt** de stamklinker in de "
                          f"{tijd.lower()} (**{kort} → {lang}**), zoals *ποιέω → ποιήσω*.")
    n = _opb_prefix_len(rest_k, stam_zk)
    if n < max(1, len(stam_zk) - 1):
        return sk, [], None  # stam matcht niet → niets beweren
    staart = _opb_norm(vorm)[len(vkaal) - len(rest_k) + n:] if len(vkaal) >= len(rest_k) else _opb_norm(vorm)[n:]
    langste = max((len(u) for _c, u in G20_CONTRACTA[sk] if staart.startswith(u)), default=0)
    treffers = [c for c, u in G20_CONTRACTA[sk] if staart.startswith(u) and len(u) == langste] if langste else []
    return sk, treffers, None

_OPB_SIGMA = [
    ("labialen", "ψ", "π/β/φ + σ versmelt tot **ψ**", "πβφ"),
    ("gutturalen", "ξ", "κ/γ/χ + σ versmelt tot **ξ**", "κγχ"),
    ("dentalen", "σ", "τ/δ/θ/ζ **vallen weg** vóór de σ", "τδθζ"),
    ("liquidae", "—", "λ/μ/ν/ρ stoten de σ af", "λμνρ"),
]

def _plek(vorm_kaal, rest, n, teken):
    """Index van de samengesmolten letter in de vorm zelf, of -1 als we het niet zeker weten.
    (rest is de vorm zonder augment; de lengtes kunnen verschillen, dus we controleren het.)"""
    i = n + (len(vorm_kaal) - len(rest))
    return i if 0 <= i < len(vorm_kaal) and vorm_kaal[i] == teken else -1

def _sigma_treffer(vorm, lemma, parsing_info=""):
    """Structureel resultaat van de σ-analyse: (naam, botsende medeklinker, uitkomst, regel) — of None.
    Eén bron van waarheid: zowel de opbouw-uitleg als de samensmeltings-oefening gebruiken dit."""
    info = parsing_info or ""
    if not any(t in info for t in ("Futurum", "Aoristus")):
        return None
    lk, vk = _opb_kaal(lemma), _opb_kaal(vorm)
    stam = lk[:-1] if lk.endswith("ω") else (lk[:-4] if lk.endswith("ομαι") else lk)
    if not stam:
        return None
    # Bij een verbum contractum hoort de stamklinker niet bij de botsende medeklinker (δοκέω → δοκ + σ).
    kandidaten = [stam] + ([stam[:-1]] if stam[-1] in "αεο" and len(stam) > 2 else [])
    rest, _aug = _opb_zonder_augment(vk, lk)
    for st in kandidaten:
        n = _opb_prefix_len(rest, st)
        if n < max(1, len(st) - 1):
            continue
        # De botsende medeklinker: het eerste stamteken dat de vorm niet overnam (βάλλω: λ),
        # of — als de stam helemaal meeging — het laatste stamteken zelf (μένω → μενῶ: ν).
        slot = st[n] if n < len(st) else (st[-1] if st else "")
        na = rest[n:n + 1]
        for naam, uit, regel, letters in _OPB_SIGMA:
            if not slot or slot not in letters:
                continue
            if naam == "liquidae":
                # Alleen het futurum trekt samen; een aoristus II heeft met de σ niets te maken.
                if "Futurum" not in info or na not in ("ω", "ο", "ε"):
                    continue
                if opb_contracta_stamklinker(lemma):
                    continue  # contracta vormen hun futurum met rekking + σ (καλέω → καλέσω)
                if rest[n - 1:n] not in ("λ", "μ", "ν", "ρ"):
                    continue  # de vloeiklank moet er ook echt staan (πίνω → πίομαι heeft geen ν)
                return (naam, slot, "—", regel, _plek(vk, rest, n, na))
            if uit != "—" and na == uit:
                return (naam, slot, uit, regel, _plek(vk, rest, n, na))
            if naam == "dentalen" and na == "σ":
                return (naam, slot, "σ", regel, _plek(vk, rest, n, na))
    return None

def opb_analyse_sigma(vorm, lemma, parsing_info=""):
    """Verklaart een ψ/ξ/σ (of het ontbreken daarvan) op de stamgrens — alleen als dat klopt."""
    treffer = _sigma_treffer(vorm, lemma, parsing_info)
    if not treffer:
        return None
    naam, slot, uit, regel, _p = treffer
    if naam == "liquidae":
        return (f"**Vloeiklank-futurum ({slot}):** {regel}; de stam krijgt een **-ε-** die samentrekt "
                f"volgens G20 (*ε + ω → ῶ*) — vandaar de circumflexus.")
    return f"**σ-samensmelting ({naam}):** {regel} — *{slot} + σ → {uit}*."

# ============================================================================================
# SAMENSMELTINGEN — structurele analyse voor de oefen-tab '🔊 Klankwetten'. Geeft per vorm terug
# wélke klankwet er speelt (klasse + formule 'κ + σ → ξ'), zodat je kunt oefenen met herkennen.
# Streng: alleen wat de app aantoonbaar kan verklaren, anders None (liever niets dan een verzonnen
# regel) — zelfde principe als bij de morfologische ontleder.
# ============================================================================================
_SAMENSMELT_KLASSEN = {
    "labialen":   ("Labialen", "π, β, φ"),
    "gutturalen": ("Gutturalen (keelklanken)", "κ, γ, χ"),
    "dentalen":   ("Dentalen", "τ, δ, θ, ζ"),
    "liquidae":   ("Liquidae (vloeiklanken)", "λ, μ, ν, ρ"),
    "contracta":  ("Contracta (klinkersamentrekking)", "α, ε, ο, η"),
    "augment":    ("Augment (klinkerverlenging)", "α, ε, ο, αι, ει, αυ"),
}
# Langere tweeklanken eerst, anders matcht 'ο' al vóór 'οι' (οἰκοδομέω → ᾠκοδόμησεν).
_AUG_TEMPOREEL = [("αι", "ῃ"), ("ει", "ῃ"), ("οι", "ῳ"), ("αυ", "ηυ"), ("ευ", "ηυ"),
                  ("α", "η"), ("ε", "η"), ("ο", "ω")]

def _augment_treffer(vorm, lemma, parsing_info=""):
    """(van, naar) bij een TEMPOREEL augment (beginklinker verlengd), of None. Het syllabische
    augment (ἐ- ervóór) is geen samensmelting en telt hier dus niet mee.

    Streng: ná de verlengde klinker moet de rest van de vorm ook echt de stam van het lemma zijn.
    Anders zou een onregelmatige/suppletieve vorm (εἰμί → ἦν, ἔρχομαι → ἦλθον) ten onrechte als
    'ει → ῃ' of 'ε → η' worden uitgelegd."""
    info = parsing_info or ""
    if not any(t in info for t in _OPB_TIJD_MET_AUGMENT) or "Indicativus" not in info:
        return None
    lk, vk = _opb_kaal(lemma), _opb_kaal(vorm)
    if _opb_split_voorvoegsel(lk)[0]:
        return None      # samengesteld werkwoord: augment zit binnenin → hier overslaan
    if not (lk.endswith("ω") or lk.endswith("ομαι")):
        return None      # athematische -μι-werkwoorden (εἰμί, δίδωμι…) zijn onregelmatig → zwijgen
    stam = lk[:-1] if lk.endswith("ω") else (lk[:-4] if lk.endswith("ομαι") else lk)
    for van, naar in _AUG_TEMPOREEL:
        if not (lk.startswith(van) and vk.startswith(_opb_kaal(naar))):
            continue
        kern = stam[len(van):]                    # de stam zonder de beginklinker
        rest = vk[len(_opb_kaal(naar)):]          # de vorm zonder het augment
        if kern and _opb_prefix_len(rest, kern) < max(1, len(kern) - 1):
            continue                              # stam matcht niet → geen bewering doen
        return (van, naar)
    return None

def _naam_klank_treffer(vorm, grieks_info="", parsing_info="", corpus_stam=""):
    """Klankwet bij een naamwoord/bijv. naamwoord van de 3e declinatie: (klasse, formule, stam).

    Alleen in de nominativus ev en de dativus mv botst de stam met een σ. We VOORSPELLEN de vorm
    uit de stam + de sandhi-regel en accepteren alleen als die voorspelling exact uitkomt — zo
    kan er geen verzonnen regel bij een onregelmatige vorm terechtkomen."""
    info = parsing_info or ""
    if "Werkwoord" in info or not any(x in info for x in ("Zelfst.", "Bijv.")):
        return None
    nv = next((k.lower() for k in ("Nom", "Gen", "Dat", "Acc", "Voc") if k in info), None)
    getal = "mv" if "mv" in info else ("ev" if "ev" in info else None)
    if nv not in ("nom", "dat") or not getal:
        return None
    stam = _naam3_stam_kaal(grieks_info) or _opb_kaal(corpus_stam or "")
    if not stam or len(stam) < 2:
        return None
    vk = _opb_kaal(vorm)
    eind = stam[-1]
    kandidaten = []
    if nv == "nom" and getal == "ev":
        if eind in "κγχ":
            kandidaten.append((stam[:-1] + "ξ", "gutturalen", f"{eind} + ς → ξ"))
        if eind in "πβφ":
            kandidaten.append((stam[:-1] + "ψ", "labialen", f"{eind} + ς → ψ"))
        if eind in "τδθ":
            kandidaten.append((stam[:-1] + "ς", "dentalen", f"{eind} + ς → ς"))
        if stam.endswith("ντ"):
            kandidaten.append((stam[:-2] + "ς", "dentalen", "ντ + ς → ς"))
    elif nv == "dat" and getal == "mv":
        for suf in ("σι", "σιν"):
            rest = suf[1:]
            if eind in "κγχ":
                kandidaten.append((stam[:-1] + "ξ" + rest, "gutturalen", f"{eind} + σι → ξι"))
            if eind in "πβφ":
                kandidaten.append((stam[:-1] + "ψ" + rest, "labialen", f"{eind} + σι → ψι"))
            if eind in "τδθ":
                kandidaten.append((stam[:-1] + suf, "dentalen", f"{eind} + σι → σι"))
            if stam.endswith("ντ"):
                kandidaten.append((stam[:-2] + suf, "dentalen", "ντ + σι → σι"))
    for voorspeld, klasse, formule in kandidaten:
        if voorspeld == vk:
            return (klasse, formule, stam)
    return None

def _contractie_plek(vorm, lemma, parsing_info=""):
    """(index, lengte) van de samengetrokken klinker in de vorm, of (-1, 0) als we het niet zeker
    weten. Zelfde rekenwijze als opb_analyse_contractie, zodat beide altijd hetzelfde aanwijzen."""
    sk = opb_contracta_stamklinker(lemma)
    if not sk:
        return (-1, 0)
    info = parsing_info or ""
    tijd = next((t for t in ["Praesens", "Imperfectum", "Futurum", "Aoristus", "Perfectum",
                             "Plusquamperfectum"] if t in info), "")
    if tijd and tijd not in ("Praesens", "Imperfectum"):
        return (-1, 0)
    lk = _opb_kaal(lemma)
    stam = lk[:-1] if lk.endswith("ω") else (lk[:-4] if lk.endswith("ομαι") else lk)
    stam_zk = stam[:-1] if stam and stam[-1] in "αεοη" else stam
    vkaal = _opb_kaal(vorm)
    rest_k, _aug = _opb_zonder_augment(vkaal, lk)
    n = _opb_prefix_len(rest_k, stam_zk)
    if n < max(1, len(stam_zk) - 1):
        return (-1, 0)
    i = len(vkaal) - len(rest_k) + n
    if not (0 <= i < len(vorm)) or len(vkaal) != len(vorm):
        return (-1, 0)
    staart = _opb_norm(vorm)[i:]
    langste = max((len(u) for _c, u in G20_CONTRACTA[sk] if staart.startswith(u)), default=0)
    if not langste or i + langste > len(vorm):
        return (-1, 0)
    return (i, langste)

def samensmeltingen_alle(vorm, lemma="", parsing_info="", grieks_info="", corpus_stam=""):
    """ALLE klankwetten die in deze vorm te zien zijn, op volgorde van voor naar achter in het woord.

    Een vorm kan er meer dan één hebben: bij ἠγαπᾶτε (< ἀγαπάω) is vooraan de beginklinker verlengd
    als augment (α → η) én trekt achteraan de stamklinker samen met de uitgang (α + ε → ᾱ). Alleen
    één ervan tonen zou een half verhaal zijn."""
    uit = []
    if not vorm:
        return uit
    info = parsing_info or ""

    if "Werkwoord" not in info:
        # Naamwoorden/bijv. naamwoorden (3e declinatie): nominativus ev en dativus mv botsen met σ.
        nt = _naam_klank_treffer(vorm, grieks_info, info, corpus_stam)
        if nt:
            klasse_s, formule, stam = nt
            klasse, letters = _SAMENSMELT_KLASSEN[klasse_s]
            _links = formule.split(" +")[0]
            _hint = _naam3_klankhint(stam).replace(" — ", "")
            uit.append({"sleutel": klasse_s, "klasse": klasse, "letters": letters, "links": _links,
                        "rechts": "ς / σι", "resultaat": formule.split("→")[-1].strip(),
                        "formule": formule, "stam": stam, "plek": "stamgrens",
                        "uitleg": (f"3e declinatie: de echte stam is **{stam}-** (zie de genitivus). "
                                   + (_hint[0].upper() + _hint[1:] + "." if _hint else
                                      f"Op de stamgrens botst **{_links}** met de σ van de uitgang."))})
        return uit
    if not lemma:
        return uit

    # 1. Vooraan: temporeel augment — de beginklinker is verlengd (ἀγαπάω → ἠγάπων).
    aug = _augment_treffer(vorm, lemma, info)
    if aug:
        van, naar = aug
        klasse, letters = _SAMENSMELT_KLASSEN["augment"]
        uit.append({"sleutel": "augment", "klasse": klasse, "letters": letters, "links": van,
                    "rechts": "ε- (augment)", "resultaat": naar, "formule": f"{van} → {naar}",
                    "plek": "vooraan",
                    "uitleg": f"Verleden tijd: de beginklinker **{van}** is verlengd tot **{naar}** "
                              f"(temporeel augment)."})

    # 2. Op de stamgrens: σ-samensmelting (futurum/aoristus).
    treffer = _sigma_treffer(vorm, lemma, info)
    if treffer:
        naam, slot, uitk, _regel, _pos = treffer
        klasse, letters = _SAMENSMELT_KLASSEN[naam]
        if naam == "liquidae":
            uit.append({"sleutel": naam, "klasse": klasse, "letters": letters, "links": slot,
                        "rechts": "σ", "resultaat": "(σ valt weg)", "formule": f"{slot} + σ → σ valt weg",
                        # Geen plek: bij een vloeiklank VERDWIJNT de σ juist — er is geen letter die
                        # 'het resultaat' is, dus markeren zou een verkeerd beeld geven.
                        "plek": "stamgrens", "pos": -1,
                        "uitleg": "Een vloeiklank (λ/μ/ν/ρ) stoot de σ van het futurum af; de stam krijgt "
                                  "een **-ε-** die samentrekt (*ε + ω → ῶ*) — vandaar de circumflexus."})
        elif naam == "dentalen":
            uit.append({"sleutel": naam, "klasse": klasse, "letters": letters, "links": slot,
                        "rechts": "σ", "resultaat": "σ", "formule": f"{slot} + σ → σ", "plek": "stamgrens", "pos": _pos,
                        "uitleg": f"Een dentaal (**{slot}**) valt weg vóór de σ."})
        else:
            uit.append({"sleutel": naam, "klasse": klasse, "letters": letters, "links": slot,
                        "rechts": "σ", "resultaat": uitk, "formule": f"{slot} + σ → {uitk}",
                        "plek": "stamgrens", "pos": _pos,
                        "uitleg": f"**{slot} + σ** versmelt tot **{uitk}**."})
    else:
        # 3. Of: verbum contractum — stamklinker + uitgang trekken samen (G20).
        sk, treffers, _los = opb_analyse_contractie(vorm, lemma, info)
        if sk and treffers:
            combo = treffers[0]
            uitk = next((u for c, u in G20_CONTRACTA[sk] if c == combo), "")
            delen = [d.strip() for d in combo.split("+")]
            if uitk and len(delen) == 2:
                klasse, letters = _SAMENSMELT_KLASSEN["contracta"]
                _cp, _cl = _contractie_plek(vorm, lemma, info)
                uit.append({"sleutel": "contracta", "klasse": klasse, "letters": letters,
                            "links": delen[0], "rechts": delen[1], "resultaat": uitk,
                            "formule": f"{combo} → {uitk}", "plek": "stamgrens",
                            "pos": _cp, "lengte": _cl,
                            "uitleg": f"Verbum contractum op **-{sk}**: de stamklinker versmelt met de "
                                      f"uitgang (*{combo} → {uitk}*)."})
    return uit

def samensmelting_analyse(vorm, lemma="", parsing_info="", grieks_info="", corpus_stam=""):
    """De belangrijkste klankwet van deze vorm (die op de stamgrens gaat vóór het augment), of None.
    Wil je ze allemaal, gebruik dan samensmeltingen_alle()."""
    alle = samensmeltingen_alle(vorm, lemma, parsing_info, grieks_info, corpus_stam)
    if not alle:
        return None
    return next((a for a in alle if a.get("plek") == "stamgrens"), alle[0])


@st.cache_resource(show_spinner=False)
def klankwet_index(_bijbel_db, _woord_van_strong):
    """{klasse-sleutel: [(vorm, lemma, parsing_info, ref, strong)]} — alle NT-vormen waarin de app
    aantoonbaar een klankwet herkent (werkwoorden én 3e-declinatie-naamwoorden). Wordt een keer
    opgebouwd; filteren op 'woorden die jij al kent' en op lesnummer gebeurt in de tab zelf."""
    uit = {}
    gezien = set()
    for ref, zin in (_bijbel_db or {}).items():
        for w in zin:
            info = w.get('parsing_info', '') or ''
            if not ("Werkwoord" in info or any(x in info for x in ("Zelfst.", "Bijv."))):
                continue
            strong = str(w.get('strong', '') or '').strip()
            bron = (_woord_van_strong or {}).get(strong) or {}
            lemma = str(bron.get('grieks', '') or '')
            vorm = str(w.get('grieks', '') or '')
            if not lemma or not vorm:
                continue
            sleutel = (vorm, lemma, info)
            if sleutel in gezien:
                continue
            gezien.add(sleutel)
            for analyse in samensmeltingen_alle(vorm, lemma, info,
                                                grieks_info=str(bron.get('grieks_info', '') or ''),
                                                corpus_stam=corpus_stam_van(strong, info)):
                # Eén vorm kan meer dan één klankwet laten zien; elke wet wordt een eigen kaart.
                uit.setdefault(analyse['sleutel'], []).append((vorm, lemma, info, ref, strong))
    return uit

def klank_opbouw_regels(vorm, analyse, segmenten=None):
    """Markdown-regels die laten zien hoe de vorm is opgebouwd — met kleur: stam blauw,
    uitgang oranje, en groen wat er uit de samensmelting komt."""
    regels = []
    if segmenten:
        _stam = "".join(t for t, srt in segmenten if srt != "uitgang")
        _uitg = "".join(t for t, srt in segmenten if srt == "uitgang")
        if _stam and _uitg:
            regels.append(f"🧩 **Zo is de vorm opgebouwd:**  :blue[{_stam}] + :orange[{_uitg}]"
                          f"  →  **{vorm}**   *(:blue[stam] + :orange[uitgang])*")
    links = str(analyse.get("links", "") or "")
    rechts = str(analyse.get("rechts", "") or "")
    pos = analyse.get("pos", -1)
    try:
        pos = int(pos)
    except (TypeError, ValueError):
        pos = -1
    lengte = analyse.get("lengte", 1)
    try:
        lengte = max(1, int(lengte))
    except (TypeError, ValueError):
        lengte = 1
    if (pos >= 0 and pos + lengte <= len(vorm) and links and rechts
            and "/" not in rechts and "(" not in rechts):
        # De spelling zoals hij zou zijn zonder de samensmelting: stam met zijn eigen letter,
        # uitgang nog met de zijne (κ + σουσιν, of α + ομενον bij een contractum).
        regels.append(f"🔧 **Zonder de samensmelting zou het zijn:**  :blue[{vorm[:pos]}{links}]"
                      f" + :orange[{rechts}{vorm[pos + lengte:]}]")
    if links:
        regels.append(f"⚡ **Wat er samensmelt:**  :blue[{links}] + :orange[{rechts}]  →  "
                      f":green[{analyse.get('resultaat', '')}]   ·  {analyse.get('klasse', '')}")
    return regels

def klank_vorm_gemarkeerd(vorm, analyse, kleur="#39d17f"):
    """De vorm als HTML, met de samengesmolten letter in een eigen kleur — helpt bij het zoeken."""
    pos = analyse.get("pos", -1) if isinstance(analyse, dict) else -1
    try:
        pos = int(pos)
    except (TypeError, ValueError):
        pos = -1
    lengte = analyse.get("lengte", 1) if isinstance(analyse, dict) else 1
    try:
        lengte = max(1, int(lengte))
    except (TypeError, ValueError):
        lengte = 1
    if pos < 0 or pos >= len(vorm) or pos + lengte > len(vorm):
        return vorm
    return (f"{vorm[:pos]}<span style='color:{kleur};text-decoration:underline;"
            f"text-underline-offset:6px'>{vorm[pos:pos + lengte]}</span>{vorm[pos + lengte:]}")

@st.cache_resource(show_spinner=False)
def klankwet_formule_index(_bijbel_db, _woord_van_strong):
    """{klasse-sleutel: [formule, ...]} — de klankwet-formules die in het NT echt voorkomen.
    Gebruikt om zinnige afleiders te kiezen in plaats van willekeurige."""
    uit = {}
    for sleutel, rijen in klankwet_index(_bijbel_db, _woord_van_strong).items():
        gezien = []
        for (vorm, lemma, info, _ref, strong) in rijen:
            bron = (_woord_van_strong or {}).get(strong) or {}
            for a in samensmeltingen_alle(vorm, lemma, info,
                                          grieks_info=str(bron.get('grieks_info', '') or ''),
                                          corpus_stam=corpus_stam_van(strong, info)):
                if a['sleutel'] == sleutel and a['formule'] not in gezien:
                    gezien.append(a['formule'])
        uit[sleutel] = gezien
    return uit

def klank_afleiders(sleutel, juist, formule_idx, rng, aantal=3):
    """Afleiders die écht iets toetsen: eerst andere regels uit DEZELFDE klanksoort (κ/γ/χ door
    elkaar halen is de klassieke fout), daarna regels uit andere klanksoorten."""
    zelfde = [f for f in (formule_idx.get(sleutel) or []) if f != juist]
    anders = [f for s2, fs in formule_idx.items() if s2 != sleutel
              for f in fs if f != juist]
    rng.shuffle(zelfde); rng.shuffle(anders)
    uit = []
    for f in zelfde[:2] + anders + zelfde[2:]:
        if len(uit) >= aantal:
            break
        if f not in uit:
            uit.append(f)
    return uit

def samensmeltingen_in_zin(zin, woord_van_strong):
    """[(vorm, formule, klasse)] voor elk woord in de zin waar een klankwet speelt — gebruikt door
    het schuifje 'Toon samensmeltingen' bij het ontleden."""
    uit = []
    for w in (zin or []):
        info = w.get('parsing_info', '') or ''
        vorm = str(w.get('grieks', '') or '')
        strong = str(w.get('strong', '') or '').strip()
        bron = (woord_van_strong or {}).get(strong) or {}
        lemma = str(bron.get('grieks', '') or '')
        if not vorm or not lemma:
            continue
        for a in samensmeltingen_alle(vorm, lemma, info,
                                      grieks_info=str(bron.get('grieks_info', '') or ''),
                                      corpus_stam=corpus_stam_van(strong, info)):
            uit.append((vorm, a['formule'], a['klasse']))
    return uit

def opb_analyse_augment(vorm, lemma, parsing_info=""):
    info = parsing_info or ""
    if not any(t in info for t in _OPB_TIJD_MET_AUGMENT):
        return None
    # Het augment staat ALLEEN in de indicativus; een aoristus-imperativus/-infinitivus/-participium
    # heeft er geen (προσένεγκον is dus géén augmentvorm).
    if "Indicativus" not in info:
        return None
    _rest, uitleg = _opb_zonder_augment(_opb_kaal(vorm), _opb_kaal(lemma))
    return f"**Augment:** {uitleg}." if uitleg else None

def opb_analyse_reduplicatie(vorm, lemma, parsing_info=""):
    """Het perfectum verdubbelt de beginmedeklinker met -ε- (λύω → λέλυκα). Alleen beweren
    als die verdubbeling er ook echt staat."""
    if "Perfectum" not in (parsing_info or ""):
        return None
    vk, lk = _opb_kaal(vorm), _opb_kaal(lemma)
    _pre, kern = _opb_split_voorvoegsel(lk)
    vkern = vk[len(_pre):] if _pre and vk.startswith(_pre) else vk
    if len(vkern) < 3 or not kern:
        return None
    c = kern[0]
    if c in "αεηιοωυ":
        return None
    # φ/θ/χ redupliceren met hun 'harde' tegenhanger (φιλέω → πεφίληκα).
    hard = {"φ": "π", "θ": "τ", "χ": "κ"}.get(c, c)
    if vkern[0] in (c, hard) and vkern[1] == "ε" and vkern[2:3] == c:
        return (f"**Reduplicatie:** het perfectum verdubbelt de beginmedeklinker met **-ε-** "
                f"(**{vkern[0]}ε-** + stam), zoals *λύω → λέλυκα*.")
    return None

def _naam3_klankhint(stam_k):
    """De klankwet-toelichting op basis van de laatste medeklinker(s) van de 3e-declinatie-stam."""
    if stam_k.endswith("ντ"):
        return " — **ντ** valt weg vóór de σ, met **compensatorische rekking** van de klinker ervoor"
    if stam_k.endswith(("τ", "δ", "θ")):
        return " — de **τ/δ/θ** valt weg vóór de σ van de uitgang en aan het woordeinde"
    if stam_k.endswith(("κ", "γ", "χ")):
        return " — in de nominativus versmelt **κ/γ/χ + σ** tot **ξ**"
    if stam_k.endswith(("π", "β", "φ")):
        return " — in de nominativus versmelt **π/β/φ + σ** tot **ψ**"
    return ""

def opb_analyse_naamwoord(vorm, grieks_info="", parsing_info="", corpus_stam=""):
    """Bij een 3e-declinatie-woord: de échte stam (νύξ → νυκτ-, πᾶς → παντ-) verklaart de 'rare'
    nominativus. Stam uit de genitivus in grieks_info, of — als die er niet is — uit het corpus."""
    if "Werkwoord" in (parsing_info or ""):
        return None
    ruw = [d.strip() for d in str(grieks_info or "").replace(';', ',').split(',') if d.strip()]
    nom = ruw[0] if ruw else ""
    # 1) Stam uit de citatie-genitivus (voluit, niet afgekort) — de bestaande, precieze weg.
    if len(ruw) >= 2 and not (ruw[1].startswith('-') or ruw[1].startswith('‑')):
        gen = ruw[1]
        gk, nk = _opb_kaal(gen), _opb_kaal(nom)
        if gk.endswith("ος") and not gk.endswith("ους") and _opb_prefix_len(gk, nk) >= 2:
            stam = gen[:-2] if len(gen) > 2 else gen
            stam_k = _opb_kaal(stam)
            if stam_k and stam_k != nk:
                return (f"**3e declinatie:** de echte stam zie je in de genitivus: **{stam}-** "
                        f"(nom. *{nom}*, gen. *{gen}*){_naam3_klankhint(stam_k)}.")
    # 2) Geen bruikbare genitivus (adjectief/voornaamwoord): val terug op de corpus-stam, maar
    #    alléén als de nominativus écht gefuseerd is (πᾶς←παντ) — zo blijft αὐτός e.d. buiten schot.
    cs = _opb_kaal(corpus_stam or "")
    if cs and len(cs) >= 2 and cs[-1] not in "αεηιουω" and nom:
        nk = _opb_kaal(nom)
        if not nk.startswith(cs):
            hint = _naam3_klankhint(cs)
            if hint:
                return f"**3e declinatie:** de echte stam is **{cs}-** (nom. *{nom}*){hint}."
    return None

# ============================================================================================
# MORFOLOGISCHE ONTLEDER — splitst een vorm in (augment) + stam + uitgang, voor 'kleur uitgangen'
# en de opbouw-uitleg. Conservatief: alleen betrouwbare splitsingen (1e/2e declinatie, thematische
# werkwoorden). 3e declinatie / onregelmatig / voornaamwoorden → None (geen valse splitsing).
# ============================================================================================
# Standaard naamwoorduitgangen per verbuigingsklasse (accent-loos), per (naamval, getal).
_NAAM_UITG = {
    "o_mv": {("nom","ev"):["ος"],("gen","ev"):["ου"],("dat","ev"):["ω"],("acc","ev"):["ον"],("voc","ev"):["ε"],
             ("nom","mv"):["οι"],("gen","mv"):["ων"],("dat","mv"):["οις"],("acc","mv"):["ους"],("voc","mv"):["οι"]},
    "o_o":  {("nom","ev"):["ον"],("gen","ev"):["ου"],("dat","ev"):["ω"],("acc","ev"):["ον"],("voc","ev"):["ον"],
             ("nom","mv"):["α"],("gen","mv"):["ων"],("dat","mv"):["οις"],("acc","mv"):["α"],("voc","mv"):["α"]},
    "a_eta":{("nom","ev"):["η"],("gen","ev"):["ης"],("dat","ev"):["η"],("acc","ev"):["ην"],("voc","ev"):["η"],
             ("nom","mv"):["αι"],("gen","mv"):["ων"],("dat","mv"):["αις"],("acc","mv"):["ας"],("voc","mv"):["αι"]},
    "a_alpha":{("nom","ev"):["α"],("gen","ev"):["ας"],("dat","ev"):["α"],("acc","ev"):["αν"],("voc","ev"):["α"],
               ("nom","mv"):["αι"],("gen","mv"):["ων"],("dat","mv"):["αις"],("acc","mv"):["ας"],("voc","mv"):["αι"]},
    "a_impuur":{("nom","ev"):["α"],("gen","ev"):["ης"],("dat","ev"):["η"],("acc","ev"):["αν"],("voc","ev"):["α"],
                ("nom","mv"):["αι"],("gen","mv"):["ων"],("dat","mv"):["αις"],("acc","mv"):["ας"],("voc","mv"):["αι"]},
    "a_ees":{("nom","ev"):["ης"],("gen","ev"):["ου"],("dat","ev"):["η"],("acc","ev"):["ην"],("voc","ev"):["α","η"],
             ("nom","mv"):["αι"],("gen","mv"):["ων"],("dat","mv"):["αις"],("acc","mv"):["ας"],("voc","mv"):["αι"]},
    "a_aas":{("nom","ev"):["ας"],("gen","ev"):["ου"],("dat","ev"):["α"],("acc","ev"):["αν"],("voc","ev"):["α"],
             ("nom","mv"):["αι"],("gen","mv"):["ων"],("dat","mv"):["αις"],("acc","mv"):["ας"],("voc","mv"):["αι"]},
}
_WW_UITG = ["θησονται","θησεται","θησομαι","θησαν","θητε","θημεν","θηναι","θεντες","θεντος","θεντα","θεις","θεισα","θεν","θην","θης","θῃ","θη",
            "κασιν","καμεν","κατε","κασι","κοτες","κοτος","κως","κας","κε","κα",
            "σαμεθα","σαμεν","σαντων","σαντες","σαντος","σαντα","σασιν","σασα","σατε","σας","σαι","σεν","σε","σα","σω","σεις","σει","σομεν","σετε","σουσιν","σουσι","σῃς","σῃ",
            "ωμεθα","ωνται","ωμεν","ωσιν","ωσι","ηται","ησθε","ωμαι","ητε","ῃς","ῃ","οιμι","οις","οι",
            "ομεθα","εσθε","ονται","εται","ομαι","ομην","οντο","ετο","ου",
            "ομεν","ετε","ουσιν","ουσι","οντες","οντος","οντα","οντων","ουσα","ουσης",
            "εις","ει","εν","ες","ον","ω","ειν","μαι","σθε","ται","το","θι","τω","σον"]

def _naam_klasse(grieks_info, geslacht):
    gi = _opb_kaal(grieks_info)
    delen = [d.strip().lstrip('-').lstrip('‑') for d in gi.replace(';', ',').split(',') if d.strip()]
    if len(delen) < 2:
        return None
    nom, gen = delen[0], delen[1]
    if gen.endswith("ου"):
        if geslacht == "O" or nom.endswith("ον"): return "o_o"
        if nom.endswith("ης"): return "a_ees"
        if nom.endswith("ας"): return "a_aas"
        return "o_mv"
    if gen.endswith("ης"):
        return "a_impuur" if nom.endswith("α") else "a_eta"
    if gen.endswith("ας"):
        return "a_alpha"
    return None

# 3e-declinatie-uitgangen (accent-loos), per (naamval, getal). Alleen de oblique vormen waar de
# echte stam (uit de genitivus) schóón vooraan in het woord zit. Nominativus ev / vocativus en de
# sandhi-vormen (dat. mv, στ+σι → ...) slaan we over: daar wisselt de stam, dus dan zwijgen we.
_NAAM3_UITG = {
    ("gen", "ev"): {"ος"}, ("dat", "ev"): {"ι"}, ("acc", "ev"): {"α"},
    ("nom", "mv"): {"ες", "α"}, ("gen", "mv"): {"ων"}, ("acc", "mv"): {"ας", "α"},
    ("dat", "mv"): {"σι", "σιν"},
}

def _naam3_stam_kaal(grieks_info):
    """Leidt de accent-loze 3e-declinatie-stam af uit nominativus + genitivus in grieks_info
    (bv. 'σῶμα, -τος' → 'σωματ', 'νύξ, νυκτός' → 'νυκτ'). De genitivus mag afgekort zijn: dan
    plakken we hem met maximale overlap aan de nominativus. None als er geen schone stam is."""
    ruw = [d.strip() for d in str(grieks_info or "").replace(';', ',').split(',') if d.strip()]
    if len(ruw) < 2:
        return None
    nom, gen = ruw[0], ruw[1]
    a = _opb_kaal(gen).lstrip('-').lstrip('‑')
    if not a.endswith("ος") or a.endswith("ους"):
        return None   # geen schone 3e-declinatie-genitivus (2e decl. -ου, contractum -ους, …)
    if gen.strip().startswith('-') or gen.strip().startswith('‑'):
        nomk = _opb_kaal(nom)
        vol = None
        for k in range(min(len(nomk), len(a)), 0, -1):
            if nomk[-k:] == a[:k]:
                vol = nomk + a[k:]; break
        a = vol if vol is not None else nomk + a
    stam = a[:-2]
    return stam if len(stam) >= 2 else None

def _splits_naamwoord_3e(grieks, grieks_info, nv, getal):
    """3e declinatie: splits alleen als de vorm exact begint met de uit de genitivus afgeleide
    stam én de rest een erkende 3e-declinatie-uitgang is. Zo blijft de splitsing altijd exact
    reconstrueerbaar en vallen onregelmatige/sandhi-vormen vanzelf weg (geen valse splitsing)."""
    stam_k = _naam3_stam_kaal(grieks_info)
    if not stam_k:
        return None
    gk = _opb_kaal(grieks)
    if len(gk) != len(grieks) or not gk.startswith(stam_k):
        return None
    rest = gk[len(stam_k):]
    if rest not in _NAAM3_UITG.get((nv, getal), ()):
        return None
    n = len(stam_k)
    return [(grieks[:n], "stam"), (grieks[n:], "uitgang")]

def _splits_naamwoord(grieks, grieks_info, info):
    nv = next((k.lower() for k in ("Nom","Gen","Dat","Acc","Voc") if k in info), None)
    getal = "mv" if "mv" in info else ("ev" if "ev" in info else None)
    ges = "M" if "mannelijk" in info else ("V" if "vrouwelijk" in info else ("O" if "onzijdig" in info else None))
    if not nv or not getal:
        return None
    kl = _naam_klasse(grieks_info, ges)
    if kl:
        for u in sorted(_NAAM_UITG[kl].get((nv, getal), []), key=len, reverse=True):
            gk = _opb_kaal(grieks)
            if gk.endswith(u) and len(gk) - len(u) >= 2:
                n = len(grieks) - len(u)   # accent-loos en met accent even lang (geen combining chars)
                return [(grieks[:n], "stam"), (grieks[n:], "uitgang")]
    # 1e/2e declinatie gaf niets → probeer 3e declinatie (stam uit de genitivus).
    return _splits_naamwoord_3e(grieks, grieks_info, nv, getal)

def _splits_werkwoord(grieks, lemma, info):
    gk, lk = _opb_kaal(grieks), _opb_kaal(lemma)
    if len(gk) != len(grieks) or len(gk) < 4:
        return None   # combining chars → posities kloppen niet; sla over
    aug = 0
    verleden = any(t in info for t in ("Imperfectum", "Aoristus", "Plusquamperfectum"))
    if verleden and not _opb_split_voorvoegsel(lk)[0]:
        l0 = lk[0] if lk else ""
        if gk.startswith("ε") and l0 != "ε": aug = 1
        elif gk.startswith("η") and l0 in ("α", "ε"): aug = 1
        elif gk.startswith("ω") and l0 == "ο": aug = 1
        elif gk.startswith("ηυ") and l0 in ("α", "ε"): aug = 2
    for u in sorted(_WW_UITG, key=len, reverse=True):
        if gk.endswith(u):
            stamlen = len(gk) - len(u)
            if stamlen - aug >= 2:
                delen = []
                if aug: delen.append((grieks[:aug], "augment"))
                delen.append((grieks[aug:stamlen], "stam"))
                delen.append((grieks[stamlen:], "uitgang"))
                return delen
    return None

# ---- Corpus-stam: voor woorden zonder bruikbare genitivus in grieks_info (bijv. naamwoorden,
# voornaamwoorden, en 3e-declinatie zonder citatie-genitivus) leiden we de verbuigingsstam af uit
# ÁLLE vormen in het NT. Per (strong, geslacht): strip de genitivus-uitgang, en vertrouw de stam
# alleen als élke verbogen vorm netjes = stam + canonieke uitgang is. Onregelmatige/suppletieve
# paradigma's (Ἰησοῦς, οὗτος) vallen zo vanzelf weg — geen valse splitsing.
_CORPUS_UITG = {"ος","ου","ω","ον","ε","η","ης","ην","α","ας","αν","ι","ο",
                "οι","ων","οις","ους","αι","αις","ες","υς","ις","εις"}
_CORPUS_UITG_VALID = _CORPUS_UITG | {""}

def _corpus_gen_stam(gen_kaal):
    for e, cut in (("ους", 3), ("ου", 2), ("ος", 2), ("ης", 2), ("ας", 2), ("ως", 2)):
        if gen_kaal.endswith(e):
            return gen_kaal[:-cut]
    return None

def _corpus_nv_getal(info):
    nv = next((k.lower() for k in ("Nom","Gen","Dat","Acc","Voc") if k in info), None)
    return nv, ("mv" if "mv" in info else ("ev" if "ev" in info else None))

def _corpus_geslacht(info):
    return ("mannelijk" if "mannelijk" in info else
            ("vrouwelijk" if "vrouwelijk" in info else ("onzijdig" if "onzijdig" in info else "")))

def _is_nominaal(info):
    return any(k in info for k in ("Zelfst.", "Bijv.", "Lidwoord", "Voornaamwoord"))

@st.cache_resource
def morf_stam_index(_bijbel_db):
    """{(strong, geslacht): stam_kaal} — de verbuigingsstam per woord+geslacht, afgeleid uit de
    NT-vormen. Alleen regelmatige paradigma's; onregelmatige (Ἰησοῦς, οὗτος) blijven eruit."""
    from collections import defaultdict, Counter
    gennen = defaultdict(Counter)   # (strong,ges) -> Counter(stam uit gen.ev)
    allen = defaultdict(list)       # (strong,ges) -> [kaal-vorm]  (schuine vormen, ter controle)
    for _ref, zin in (_bijbel_db or {}).items():
        for w in zin:
            info = w.get('parsing_info', '') or ''
            if "Werkwoord" in info or not _is_nominaal(info):
                continue
            nv, getal = _corpus_nv_getal(info)
            if not nv or not getal:
                continue
            strong = str(w.get('strong', '') or '').strip()
            g = str(w.get('grieks', '') or '')
            if not strong or not g:
                continue
            key = (strong, _corpus_geslacht(info))
            gk = _opb_kaal(g)
            if nv == "gen" and getal == "ev":
                st_ = _corpus_gen_stam(gk)
                if st_ and len(st_) >= 2:
                    gennen[key][st_] += 1
            # Niet meenemen in de controle: nom./voc.ev (kaal), dat.mv (sandhi) en de acc.ev van
            # onzijdige woorden (die is gelijk aan de kale nominativus, bv. σῶμα, niet stam+uitgang).
            _kaal_onz_acc = (nv == "acc" and getal == "ev" and _corpus_geslacht(info) == "onzijdig")
            if (not (nv in ("nom", "voc") and getal == "ev")
                    and not (nv == "dat" and getal == "mv") and not _kaal_onz_acc):
                allen[key].append(gk)
    tabel = {}
    for key, teller in gennen.items():
        stam = teller.most_common(1)[0][0]
        if len(stam) < 2:
            continue
        if all(f.startswith(stam) and f[len(stam):] in _CORPUS_UITG_VALID for f in allen.get(key, [])):
            tabel[key] = stam
    return tabel

def corpus_stam_van(strong, parsing_info):
    """De verbuigingsstam voor dit woord+geslacht uit het corpus (of '' als onbekend/onbetrouwbaar)."""
    if not strong:
        return ""
    try:
        tabel = morf_stam_index(laad_bijbel_db())
    except Exception:
        return ""
    ges = _corpus_geslacht(parsing_info or "")
    return tabel.get((str(strong), ges)) or tabel.get((str(strong), "")) or ""

def _splits_via_corpusstam(grieks, corpus_stam, info):
    """Splits met de corpus-stam: stam + uitgang, alleen als de vorm exact op stam + een erkende
    uitgang uitkomt. Reconstructie is per constructie exact; onregelmatige vormen vallen weg."""
    if not corpus_stam or len(corpus_stam) < 2:
        return None
    nv, getal = _corpus_nv_getal(info)
    if not nv or not getal:
        return None
    gk = _opb_kaal(grieks)
    if len(gk) != len(grieks) or not gk.startswith(corpus_stam):
        return None
    rest = gk[len(corpus_stam):]
    if not rest or rest not in _CORPUS_UITG:
        return None
    n = len(corpus_stam)
    return [(grieks[:n], "stam"), (grieks[n:], "uitgang")]

def ontleed_segmenten(grieks, lemma="", grieks_info="", parsing_info="", corpus_stam=""):
    """Splitst een vorm in [(deel, soort)] met soort ∈ {augment, stam, uitgang} — of None als er
    geen betrouwbare splitsing is (onregelmatige/athematische werkwoorden, suppletieve vnw).
    corpus_stam (optioneel) = de uit het NT afgeleide verbuigingsstam, voor adjectieven/vnw/3e decl."""
    info = parsing_info or ""
    g = unicodedata.normalize('NFC', str(grieks or ""))
    if not g:
        return None
    if "Werkwoord" in info:
        return _splits_werkwoord(g, lemma, info)
    if "Zelfst." in info or "Bijv." in info:
        r = _splits_naamwoord(g, grieks_info, info)
        if r:
            return r
    # Adjectieven/voornaamwoorden/lidwoorden en 3e-declinatie zonder citatie-genitivus: corpus-stam.
    if corpus_stam and _is_nominaal(info):
        return _splits_via_corpusstam(g, corpus_stam, info)
    return None

_SEGMENT_KLEUR = {"augment": "#56b4e9", "stam": "#e8eaed", "uitgang": "#ff9d5c"}

def kleur_uitgangen_html(grieks, lemma="", grieks_info="", parsing_info="", basis_stijl="", strong=None):
    """HTML van een woord met gekleurde stam/uitgang/augment — of None als er geen splitsing is."""
    seg = ontleed_segmenten(grieks, lemma, grieks_info, parsing_info,
                            corpus_stam=corpus_stam_van(strong, parsing_info))
    if not seg:
        return None
    return "".join(f"<span style='color:{_SEGMENT_KLEUR.get(s, '#e8eaed')};font-weight:700'>{t}</span>" for t, s in seg)

def opbouw_formule(vorm, lemma="", parsing_info=""):
    """Bouwt de vorm zichtbaar op met plustekens, zoals in de slides:
    'ἐ + πε + φαν + μεθα  >  ἐπεφαμμεθα'.

    Alleen de onderdelen die we aantoonbaar kunnen herkennen (voorvoegsel, augment, reduplicatie,
    stam, uitgang). Lukt dat niet, dan geven we niets terug in plaats van iets te verzinnen."""
    if not lemma or "Werkwoord" not in (parsing_info or ""):
        return None
    v_nfc = unicodedata.normalize('NFC', str(vorm).strip())
    vk, lk = _opb_kaal(v_nfc), _opb_kaal(lemma)
    if len(vk) != len(v_nfc) or len(vk) < 3:
        return None
    delen = []            # (tekst, label)
    pos = 0

    pre, kern = _opb_split_voorvoegsel(lk)
    if pre and vk.startswith(pre[:len(pre) - 1] if pre[-1] in "οαε" else pre):
        _p = pre if vk.startswith(pre) else pre[:len(pre) - 1]
        delen.append((v_nfc[:len(_p)], "voorvoegsel")); pos = len(_p)
    else:
        kern = lk

    rest_na_pre = vk[pos:]
    _rest, aug_uitleg = _opb_zonder_augment(vk, lk)
    if aug_uitleg and 'augment' in aug_uitleg and rest_na_pre.startswith("ε") and not kern.startswith("ε"):
        delen.append((v_nfc[pos:pos + 1], "augment")); pos += 1
        rest_na_pre = vk[pos:]

    # reduplicatie van het perfectum (C + ε)
    if "Perfectum" in parsing_info and len(rest_na_pre) > 3 and kern:
        c = kern[0]
        hard = {"φ": "π", "θ": "τ", "χ": "κ"}.get(c, c)
        if rest_na_pre[0] in (c, hard) and rest_na_pre[1] == "ε" and rest_na_pre[2:3] == c:
            delen.append((v_nfc[pos:pos + 2], "reduplicatie")); pos += 2
            rest_na_pre = vk[pos:]

    # stam: zo ver als de vorm met de lemmastam meeloopt
    lemstam = kern[:-1] if kern.endswith("ω") else (kern[:-4] if kern.endswith("ομαι") else kern)
    n = _opb_prefix_len(rest_na_pre, lemstam)
    if n < 2:
        return None                      # stam niet herkenbaar (bv. suppletie) → niets beweren
    delen.append((v_nfc[pos:pos + n], "stam")); pos += n
    if pos >= len(v_nfc):
        return None                      # geen uitgang over → weinig te tonen
    delen.append((v_nfc[pos:], "uitgang"))

    if len(delen) < 2:
        return None
    # Platte markdown (geen HTML): zo werkt de regel ook binnen een opsomming of st.info.
    _stukken = " + ".join(f"**{t}**" for t, _lab in delen)
    _benoemd = " + ".join(lab for _t, lab in delen)
    return f"**Opbouw:** {_stukken} → **{v_nfc}**  ({_benoemd})"

def opbouw_regels(vorm, lemma="", parsing_info="", grieks_info="", corpus_stam=""):
    """(regels, stamklinker, treffers) — alle klankwetten die aantoonbaar op deze vorm slaan."""
    regels = []
    nw = opb_analyse_naamwoord(vorm, grieks_info, parsing_info, corpus_stam)
    if nw:
        regels.append(nw)
    aug = opb_analyse_augment(vorm, lemma, parsing_info)
    if aug:
        regels.append(aug)
    red = opb_analyse_reduplicatie(vorm, lemma, parsing_info)
    if red:
        regels.append(red)
    sig = opb_analyse_sigma(vorm, lemma, parsing_info)
    if sig:
        regels.append(sig)
    sk, treffers, los = opb_analyse_contractie(vorm, lemma, parsing_info)
    if los:
        regels.append(los)
    elif sk and treffers:
        _uit = next(u for c, u in G20_CONTRACTA[sk] if c == treffers[0])
        regels.append(f"**Verbum contractum (stam op -{sk}):** hier trekt **{' of '.join(treffers)}** samen tot **{_uit}**.")
    elif sk:
        regels.append(f"**Verbum contractum (stam op -{sk}):** de stamklinker **{sk}** versmelt met de uitgang "
                      f"(zie de regels hieronder).")
    return regels, sk, treffers

def g20_tabel_html(stamklinker, treffers=None):
    """De G20-kolom van deze stamklinker, met de toepasselijke regel(s) gemarkeerd."""
    if stamklinker not in G20_CONTRACTA:
        return ""
    treffers = set(treffers or [])
    rijen = ""
    for combo, uit in G20_CONTRACTA[stamklinker]:
        raak = combo in treffers
        stijl = ("background:rgba(255,215,0,.28);border:2px solid #ffd700;font-weight:800;"
                 if raak else "border:1px solid #444;")
        rijen += (f"<tr><td style='padding:3px 12px;{stijl}'>{'▶ ' if raak else ''}{combo}</td>"
                  f"<td style='padding:3px 12px;{stijl}'>&gt; <span style='color:#ff9d5c;font-weight:800'>{uit}</span></td></tr>")
    inf = G20_INFINITIEF.get(stamklinker, "")
    return (f"<div style='overflow-x:auto'><table style='border-collapse:collapse;font-size:16px'>"
            f"<tr><td colspan='2' style='padding:4px 12px;border:1px solid #444;background:#2b6f8a;"
            f"font-weight:700;color:#fff'>G20 · stam op -{stamklinker}</td></tr>{rijen}</table></div>"
            + (f"<div style='font-size:12px;color:#9aa3af;margin-top:6px'>Infinitivus: <b>{inf}</b> "
               f"&nbsp;·&nbsp; de η in de derde regel is die van de coniunctivus.</div>" if inf else ""))

_STAM_PSEUDO_INFO = {
    "Futurum Actief/Medium": "Werkwoord - Futurum Indicativus Actief - 1e pers. ev",
    "Aoristus Actief/Medium": "Werkwoord - Aoristus Indicativus Actief - 1e pers. ev",
    "Aoristus Passief": "Werkwoord - Aoristus Indicativus Passief - 1e pers. ev",
    "Perfectum Actief": "Werkwoord - Perfectum Indicativus Actief - 1e pers. ev",
    "Perfectum Medium/Passief": "Werkwoord - Perfectum Indicativus Medium - 1e pers. ev",
}

def stamtijd_opbouw_regels(vorm, tijd_diathese, basis):
    """Uitleg bij één stamtijdvorm, afgeleid uit de vórm zelf (augment/reduplicatie, σ-samensmelting,
    klinkerrekking) in plaats van uit de opgeslagen vuistregel — die klopt niet bij elk werkwoord.
    Bij echte suppletie valt hij terug op de toelichting uit de database."""
    praesens = str((basis or {}).get('praesens', ''))
    info = _STAM_PSEUDO_INFO.get(tijd_diathese, "Werkwoord - Indicativus Actief")
    regels, _sk, _tr = opbouw_regels(vorm, praesens, info)
    _f = opbouw_formule(vorm, praesens, info)
    if _f:
        regels.insert(0, _f)
    morf = (basis or {}).get('morfologie', {}) or {}
    if morf.get('memoriseren_vereist'):
        _t = str((morf.get('mutatieregel') or {}).get('toelichting', '')).strip()
        regels.append(("⚠️ " if _t.startswith("Suppletie") else "⚠️ **Suppletie:** ")
                      + (_t or "Deze stamtijd komt van een andere stam — puur memoriseren."))
    elif not regels:
        regels.append("Deze vorm volgt geen aparte klankwet — stam + uitgang, gewoon inprenten.")
    return regels

def toon_vertaalhulp(parsing_info, sleutel="", uitgeklapt=False):
    """Vertaalregels voor déze vorm — ALTIJD achter een uitklapmenu.

    De tekst noemt de naamval/tijd bij naam ('Genitivus — bijvoeglijke bepaling …') en zou het
    antwoord dus weggeven als hij open zou staan terwijl je die vraag nog moet beantwoorden."""
    regels = _ontleed_vertaalhulp(parsing_info)
    if not regels:
        return False
    with st.expander("💡 Hoe vertaal je deze vorm? (verklapt de ontleding)", expanded=uitgeklapt):
        for r in regels:
            st.markdown("- " + r)
    return True

def toon_rijtje_hulp(parsing_info, lemma="", grieks_info="", sleutel="", uitgeklapt=False):
    """Spiek-expander met de paradigma-tabel(len) die bij deze vorm horen, met het exacte vakje
    gemarkeerd. Geeft True terug als er iets getoond is."""
    tabellen = ontleed_alle_tabellen()
    if not tabellen:
        return False
    tips = [t for t in _ontleed_tip_tabellen(parsing_info, lemma, grieks_info) if t in tabellen]
    if not tips:
        # Van sommige woordsoorten (bv. ἐγώ, σύ, αὐτός) staat er geen rijtje in de slides.
        # Dat eerlijk melden is beter dan een tabel van een ánder woord tonen.
        st.caption("📋 Van dit woord staat geen rijtje in de grammatica-tabellen — het heeft een eigen, vaste vervoeging.")
        return False
    with st.expander("📋 Bekijk het rijtje (spieken)", expanded=uitgeklapt):
        alle = list(tabellen.keys())
        # De key hangt óók van het woord af: anders houdt de keuzelijst (met een vaste key) de tabel
        # van het vórige woord vast en wordt de juiste standaardtabel (index=) genegeerd — daardoor
        # kreeg bv. een werkwoord de naamwoordentabel van het vorige woord te zien.
        _wsig = re.sub(r'\W', '', (str(parsing_info)[:50] + str(lemma)))[:48]
        keuze = st.selectbox("Tabel:", alle, index=alle.index(tips[0]), key=f"rijtje_tab_{sleutel}_{_wsig}")
        ktarget = _noun_g6_target(grieks_info) if keuze == "G6 Naamwoorden" else None
        mrow, mcol = _ontleed_doelcel(parsing_info)
        st.caption("De uitgangen zijn oranje; jouw vorm heeft een ▶ en een gouden kader."
                   + (" Alleen jouw kolom wordt getoond." if ktarget else ""))
        st.markdown(_render_gramtabel_html(tabellen.get(keuze, []), ktarget, mrow, mcol), unsafe_allow_html=True)
    return True

@st.cache_data(show_spinner=False)
def _stam_index():
    """Genormaliseerde praesens → stamtijden-database-entry."""
    return {normaliseer_accent(v.get('praesens', '')): v for v in (laad_stamtijden_db() or []) if v.get('praesens')}

def _stamtijd_sleutel(info):
    """Welke stamtijd hoort bij deze werkwoordsvorm? (None = presentstam / het lemma zelf)."""
    info = info or ""
    if "Praesens" in info or "Imperfectum" in info:
        return None
    if "Aoristus" in info and "Passief" in info:
        return "Aoristus Passief"
    if "Aoristus" in info:
        return "Aoristus Actief/Medium"
    if "Futurum" in info:
        return "Futurum Actief/Medium"
    if "Perfectum" in info or "Plusquamperfectum" in info:
        return "Perfectum Medium/Passief" if ("Medium" in info or "Passief" in info) else "Perfectum Actief"
    return None

_STAMTIJD_LABEL = {"Futurum Actief/Medium": "futurum", "Aoristus Actief/Medium": "aoristus",
                   "Aoristus Passief": "aoristus passief", "Perfectum Actief": "perfectum",
                   "Perfectum Medium/Passief": "perfectum medium/passief"}

def stamtijd_opbouw(lemma, parsing_info):
    """(regel, extra_uitleg) over de stamtijd waar een werkwoordsvorm van komt — of (None, None).

    Zo zie je bv. dat ἐκλήθη hoort bij de aoristus passief ἐκλήθην van καλέω, i.p.v. te proberen de
    onregelmatige stam uit het praesens af te leiden."""
    if "Werkwoord" not in (parsing_info or "") or not lemma:
        return None, None
    sleutel = _stamtijd_sleutel(parsing_info)
    if not sleutel:
        return None, None
    v = _stam_index().get(normaliseer_accent(lemma))
    if not v:
        return None, None
    vorm = (v.get('stamtijden') or {}).get(sleutel)
    if not _stam_vorm_ok(vorm):
        return None, None
    label = _STAMTIJD_LABEL.get(sleutel, sleutel.lower())
    regel = f"📖 **Stamtijd:** deze vorm komt van de **{label}** van *{lemma}* — die luidt **{vorm}**."
    extra = None
    _morf = v.get('morfologie', {}) or {}
    if _morf.get('memoriseren_vereist'):
        _t = str((_morf.get('mutatieregel') or {}).get('toelichting', '')).strip()
        extra = "⚠️ " + (_t or "Onregelmatige stamtijd — puur memoriseren.")
    return regel, extra

def toon_opbouw_hulp(vorm, lemma="", parsing_info="", grieks_info="", sleutel="", uitgeklapt=False, strong=None):
    """Rendert (indien er iets te melden valt) de samentrekkings-/klankwethulp bij deze vorm.
    Geeft True terug als er iets getoond is."""
    _cs = corpus_stam_van(strong, parsing_info)
    regels, sk, treffers = opbouw_regels(vorm, lemma, parsing_info, grieks_info, corpus_stam=_cs)
    _stamregel, _stamextra = stamtijd_opbouw(lemma, parsing_info)
    _seg = ontleed_segmenten(vorm, lemma, grieks_info, parsing_info, corpus_stam=_cs)   # stam + uitgang
    if not regels and not sk and not _stamregel and not _seg:
        return False
    with st.expander("🔗 Zo is deze vorm opgebouwd (samentrekkingen & klankwetten)", expanded=uitgeklapt):
        if _stamregel:
            st.markdown(_stamregel)
            if _stamextra:
                st.markdown("- " + _stamextra)
        if _seg:
            _stukken = " + ".join(f"**{t}**" for t, _s in _seg)
            _labels = " + ".join(s for _t, s in _seg)
            st.markdown(f"**Opbouw:** {_stukken} → **{vorm}**  ({_labels})")
        _formule = opbouw_formule(vorm, lemma, parsing_info)
        if _formule and not _seg:
            st.markdown(_formule)
        for r in regels:
            st.markdown("- " + r)
        if sk:
            st.markdown(g20_tabel_html(sk, treffers), unsafe_allow_html=True)
            st.caption("Oranje = het resultaat van de samentrekking; het gouden vakje is de regel die hier speelt.")
    return True

def _ontleed_dims(info):
    """(key, label, opties) per te ontleden dimensie — INFO-gestuurd: alleen dimensies die dit woord
    daadwerkelijk heeft (bv. ἐγώ heeft geen geslacht → geen Geslacht-rij, anders is die onwinbaar)."""
    info = info or ""
    t = _ontleed_type(info)
    def _heeft(dim):
        return _ontleed_deel_correct(dim, info) != "—"
    dims = [("woordsoort", "Woordsoort", ["Zelfst. nw.", "Werkwoord", "Bijv. nw.", "Voornaamwoord", "Lidwoord"])]
    if t in ("ww", "ptc"):
        # Vaste werkwoord-volgorde: Wijs → Tijd → Diathese → (Persoon/Getal onderaan).
        if _heeft("wijs"): dims.append(("wijs", "Wijs", ["Indicativus", "Conjunctivus", "Optativus", "Imperativus", "Infinitivus", "Participium"]))
        if _heeft("tijd"): dims.append(("tijd", "Tijd", ["Praesens", "Imperfectum", "Futurum", "Aoristus", "Perfectum", "Plusquamperfectum"]))
        if _heeft("diathese"): dims.append(("diathese", "Diathese", ["Actief", "Medium", "Passief"]))
    if _heeft("naamval"): dims.append(("naamval", "Naamval", ["Nom", "Gen", "Dat", "Acc", "Voc"]))
    if _heeft("geslacht"): dims.append(("geslacht", "Geslacht", ["M", "V", "O"]))
    if _heeft("persoon"): dims.append(("persoon", "Persoon", ["1e pers.", "2e pers.", "3e pers."]))
    if _heeft("getal"): dims.append(("getal", "Getal", ["Ev", "Mv"]))
    return dims

def _ontleed_deel_ok(dim, keuze, info):
    """Is de gekozen waarde voor deze dimensie correct volgens parsing_info?"""
    info = info or ""
    if not keuze:
        return False
    if dim == "woordsoort":
        return keuze == _woordsoort_van(info)   # via de mapping, zodat ἀμήν e.d. ook kloppen
    if dim in ("naamval", "tijd", "wijs", "persoon"):
        return keuze in info
    if dim == "geslacht":
        return _ONTLEED_GES.get(keuze, keuze) in info
    if dim == "getal":
        return {"Ev": "ev", "Mv": "mv"}.get(keuze, keuze) in info
    if dim == "diathese":
        if keuze == "Medium/Passief":
            return ("Medium" in info) or ("Passief" in info)
        return keuze in info
    return False

def _ontleed_deel_correct(dim, info):
    """De correcte waarde voor een dimensie (voor 'Toon antwoord' en het inkleuren)."""
    info = info or ""
    if dim == "woordsoort":
        return _woordsoort_van(info)
    tabel = {
        "naamval": ["Nom", "Gen", "Dat", "Acc", "Voc"],
        "tijd": ["Praesens", "Imperfectum", "Futurum", "Aoristus", "Perfectum", "Plusquamperfectum"],
        "wijs": ["Indicativus", "Conjunctivus", "Optativus", "Imperativus", "Infinitivus", "Participium"],
        "diathese": ["Actief", "Medium", "Passief"],
        "persoon": ["1e pers.", "2e pers.", "3e pers."],
    }
    if dim in tabel:
        for w in tabel[dim]:
            if w in info:
                return w
        return "—"
    if dim == "geslacht":
        for k, v in _ONTLEED_GES.items():
            if v in info:
                return k
        return "—"
    if dim == "getal":
        if "mv" in info: return "Mv"
        if "ev" in info: return "Ev"
        return "—"
    return "—"

def vorm_ontledingen(bijbel_db, grieks_vorm, strong=None):
    """Alle verschillende ontledingen (parsing_info) die deze exacte vorm in het NT heeft — dus alle
    'mogelijke opties' bij een dubbelzinnige vorm. Optioneel beperkt tot één woord (strong)."""
    rows = bijbel_vorm_index(bijbel_db).get(normaliseer_accent(grieks_vorm), [])
    out = []
    for _g, _pi, _strong, _ref, _n, _tr in rows:
        if strong is not None and str(_strong) != str(strong):
            continue
        if _pi and _pi not in out:
            out.append(_pi)
    return out

def alternatieve_ontleding(bijbel_db, grieks_vorm, strong, keuzes, correct_info, dims):
    """Als de gegeven keuzes niet bij correct_info passen, maar wél volledig bij een ánder attested
    ontleding van dezelfde vorm (zelfde woord), geef die alt parsing_info terug — anders None.

    Zo weet de app: 'je antwoord beschrijft een echte, maar hier verkeerde, vorm van dit woord.'"""
    if not strong or not grieks_vorm:
        return None
    beantwoord = [(k, keuzes.get(k)) for k, _lab, _opt in dims if keuzes.get(k) is not None]
    if not beantwoord:
        return None
    for alt in vorm_ontledingen(bijbel_db, grieks_vorm, strong):
        if alt == correct_info:
            continue
        if all(_ontleed_deel_ok(k, v, alt) for k, v in beantwoord):
            return alt
    return None

def ambiguiteit_regel(bijbel_db, grieks_vorm, strong, keuzes, correct_info, dims):
    """Waarschuwingsregel (of ''): jouw ontleding beschrijft een échte, maar hier verkeerde, vorm
    van dit woord — de context bepaalt welke het is, dus je zou het verkeerd vertalen."""
    alt = alternatieve_ontleding(bijbel_db, grieks_vorm, strong, keuzes, correct_info, dims)
    if not alt:
        return ""
    _alt_v = alt.split(' - ', 1)[1] if ' - ' in alt else alt
    _cor_v = correct_info.split(' - ', 1)[1] if ' - ' in correct_info else correct_info
    return (f"- ⚠️ **Let op:** deze vorm **kán** ook *{_alt_v}* zijn — dan zou jouw ontleding kloppen! "
            f"Maar in **déze zin** is het *{_cor_v}*. Zo'n vorm is dubbelzinnig; de context beslist. "
            f"Met jouw keuze zou je het verkeerd vertalen.")

_ONTLEED_WS_OPTS = ["Zelfst. nw.", "Werkwoord", "Bijv. nw.", "Voornaamwoord", "Lidwoord", "Voegwoord", "Voorzetsel", "Bijwoord", "Partikel"]

def _woordsoort_van(info):
    """Canonieke woordsoort uit parsing_info (of '—' als echt onbepaald).

    Vangt ook de afwijkende koppen in de NT-data op, die anders een onwinbare '—' gaven. Op
    verzoek vallen die allemaal onder 'Partikel': 'Hebrew Word' (ἀμήν, ἀλληλουϊά),
    'Tussenwerpsel' (ἰδού, οὐαί), 'IntPrtcl' (μήτι, οὐχί) en 'Indec' (ἄν)."""
    info = info or ""
    for w in _ONTLEED_WS_OPTS:
        if w in info:
            return w
    if any(k in info for k in ("Hebrew Word", "Tussenwerpsel", "IntPrtcl", "Indec")):
        return "Partikel"
    return "—"

def _ontleed_dims_zonder_ws(info):
    """De ontleed-dimensies zonder de Woordsoort-rij (die wordt in ronde 1 al gedaan)."""
    return [d for d in _ontleed_dims(info) if d[0] != "woordsoort"]

def _ontleed_in_scope(info, niveau):
    """Valt dit woord binnen de tentamenstof van het gekozen niveau? (parsing_info-gebaseerd,
    zelfde geest als de Masterclass in Leesteksten). Bepaalt of een woord in ronde 2 ontleed wordt."""
    info = info or ""
    is_ww = "Werkwoord" in info
    if niveau == "Grieks 3":
        return True
    if niveau == "Grieks 2":
        if is_ww and any(x in info for x in ["Conjunctivus", "Optativus"]):
            return False
        return True
    # Grieks 1: werkwoorden alleen actief-indicatief-achtig (geen participium/conj./opt.)
    if is_ww:
        return ("Actief" in info) and not any(x in info for x in ["Participium", "Conjunctivus", "Optativus"])
    return True

@st.cache_data(show_spinner=False)
def laad_gramtabellen():
    """Paradigma-tabellen uit de slides (grammatica_tabellen.json) — voor de 'toon het rijtje'-hulp."""
    try:
        with open("grammatica_tabellen.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

# Vaste αὐτός-tabel (3e-persoons persoonlijk vnw) — declineert als ος/η/ο, staat niet in de slides.
_AUTOS_TABEL = [
    ["", "Mannelijk", "Vrouwelijk", "Onzijdig"],
    ["Nom sg", "αὐτός", "αὐτή", "αὐτό"],
    ["Gen sg", "αὐτοῦ", "αὐτῆς", "αὐτοῦ"],
    ["Dat sg", "αὐτῷ", "αὐτῇ", "αὐτῷ"],
    ["Acc sg", "αὐτόν", "αὐτήν", "αὐτό"],
    ["Nom pl", "αὐτοί", "αὐταί", "αὐτά"],
    ["Gen pl", "αὐτῶν", "αὐτῶν", "αὐτῶν"],
    ["Dat pl", "αὐτοῖς", "αὐταῖς", "αὐτοῖς"],
    ["Acc pl", "αὐτούς", "αὐτάς", "αὐτά"],
]

def pronomen_tabellen():
    """Bouwt de persoonlijk-vnw-tabellen: 1e/2e persoon uit Actief Beheersen, 3e persoon (αὐτός)
    vast. Zo krijgen ἐγώ/σύ/αὐτός in de ontleed-hulp tóch een rijtje (die staan niet in de slides)."""
    uit = {"Persoonlijk vnw αὐτός (3e)": _AUTOS_TABEL}
    try:
        ab = laad_actief_db()
        def _cellen(sub_bevat):
            for _niv, _cats in (ab or {}).items():
                for _cat, _paras in _cats.items():
                    if "Personale" not in _cat and "persoon" not in _cat.lower():
                        continue
                    for _sub, _cel in _paras.items():
                        if sub_bevat in _sub:
                            return {c.get('label', ''): c.get('vorm', '') for c in _cel}
            return {}
        _p1 = _cellen("1e Persoon"); _p2 = _cellen("2e Persoon")
        if _p1 and _p2:
            rijen = [["", "1e (ik/wij)", "2e (jij/jullie)"]]
            for _lab in ["Nom ev", "Gen ev", "Dat ev", "Acc ev", "Nom mv", "Gen mv", "Dat mv", "Acc mv"]:
                _rlab = _lab.replace("ev", "sg").replace("mv", "pl")
                rijen.append([_rlab, _p1.get(_lab, ""), _p2.get(_lab, "")])
            uit["Persoonlijk vnw (ik/jij)"] = rijen
    except Exception:
        pass
    return uit

@st.cache_data(show_spinner=False)
def ontleed_alle_tabellen():
    """De slide-tabellen plus de zelf opgebouwde persoonlijk-vnw-tabellen (één bron voor de hulp)."""
    t = dict(laad_gramtabellen())
    t.update(pronomen_tabellen())
    return t

def _noun_declinatie(grieks_info):
    """Declinatie-tabel van een naamwoord uit de woordenboekvorm (bv. 'θεός, -οῦ, ὁ').
    De genitief-uitgang verraadt de declinatie: -ου = 2e, -ης/-ας = 1e, -ος = 3e, -εως = 3e klinker."""
    gi = normaliseer_accent(str(grieks_info or ""))
    delen = [d.strip().lstrip('-') for d in gi.replace(';', ',').split(',') if d.strip()]
    if len(delen) < 2:
        return None
    gen = delen[1]
    if gen.endswith('εως'):
        return "G33 3e Decl (Klinker)"
    if gen.endswith('ος') and not gen.endswith('ους'):
        return "G29 3e Declinatie"
    return "G6 Naamwoorden"  # 1e/2e declinatie (gen -ου / -ης / -ας)

def _ontleed_tip_tabellen(info, lemma="", grieks_info=""):
    """Welke paradigma-tabel(len) horen (vermoedelijk) bij dit woord — beste gok eerst."""
    info = info or ""
    lemma = normaliseer_accent(lemma or "")
    tabs = []
    if "Werkwoord" in info:
        if lemma == "ειμι":
            tabs.append("G12 Werkwoord Zijn")
        if "Participium" in info:
            if "Aoristus" in info: tabs.append("G39 Part Aoristus")
            elif "Passief" in info: tabs.append("G40 Part Passief")
            else: tabs.append("G38 Part Praesens")
        if "Conjunctivus" in info: tabs.append("G44 Coniunctivus")
        if "Optativus" in info: tabs.append("G45 Optativus")
        if "Imperativus" in info: tabs.append("G46 Imperativus")
        if "Aoristus" in info and "Passief" in info: tabs.append("G35 Aoristus Passief")
        if "Perfectum" in info and ("Medium" in info or "Passief" in info): tabs.append("G36 Perfectum Med")
        elif "Perfectum" in info: tabs.append("G18 Perfectum")
        if "Aoristus" in info: tabs += ["G15 Aoristus", "G24 Aoristus II"]
        if "Passief" in info: tabs.append("G26 Passivum")
        if any(t in info for t in ["Praesens", "Imperfectum", "Futurum"]): tabs.append("G9-G10 Werkwoorden")
        if lemma.endswith("μι") and lemma != "ειμι": tabs.append("G43 Mi-Werkwoorden")
        tabs.append("G50 Stamtijden")
    elif "Bijv." in info:
        # 1e/2e declinatie (μικρός, -ά, -όν) of 3e declinatie (πᾶς, ἀληθής)? Dat verraadt de
        # uitgang van het lemma: alleen -ος volgt het μικρός-rijtje.
        if lemma.endswith("ος"):
            tabs += ["G14 Adjectiva", "G34 Adj 3e Decl"]
        elif lemma.endswith(("ης", "ες", "υς", "ας", "ς")):
            tabs += ["G34 Adj 3e Decl", "G14 Adjectiva"]
        else:
            tabs += ["G14 Adjectiva", "G34 Adj 3e Decl"]
        tabs.append("G30 Trappen")
    elif "Voornaamwoord" in info:
        # Kies de tabel op het subtype uit parsing_info. Let op de volgorde: 'Personal / Relative'
        # bevat óók 'Personal', dus de specifieke subtypes moeten eerst gecontroleerd worden.
        # Voor persoonlijke/bezittelijke en reciproke voornaamwoorden (ἐγώ, σύ, αὐτός, ἀλλήλων)
        # bestaat er GEEN rijtje in de slides. Dan liever niets tonen dan een tabel van een ander
        # woordsoort — eerder kreeg ἐγώ het demonstrativa-rijtje (οὗτος) te zien.
        if "Relative" in info: tabs.append("G21 Relativum")
        elif "Demonstrative" in info: tabs.append("G19 Demonstrativa")
        elif "Interrogative" in info or "Indefinite" in info: tabs.append("G25 Interrogativum")
        elif "Reflexive" in info: tabs.append("G22 Reflexiva")
        elif "Correlative" in info: tabs.append("G37 Correlativa")
        # Persoonlijke voornaamwoorden: rijtjes uit Actief Beheersen (1e/2e) resp. de αὐτός-tabel (3e).
        elif "3e pers." in info: tabs.append("Persoonlijk vnw αὐτός (3e)")
        elif "1e pers." in info or "2e pers." in info: tabs.append("Persoonlijk vnw (ik/jij)")
    elif "Zelfst." in info:  # zelfstandig naamwoord: declinatie uit de woordenboekvorm (grieks_info)
        _decl = _noun_declinatie(grieks_info)
        if _decl:
            tabs.append(_decl)
        tabs += ["G6 Naamwoorden", "G29 3e Declinatie", "G33 3e Decl (Klinker)"]
    # Overige woordsoorten (voorzetsel, voegwoord, bijwoord, partikel, lidwoord) verbuigen niet
    # of hebben geen rijtje in de slides → géén tabel (voorheen kreeg εἰς onterecht G6).
    _seen = set(); _uit = []
    for t in tabs:
        if t not in _seen:
            _seen.add(t); _uit.append(t)
    return _uit

_GRIEKS_RE = re.compile(r'[Ͱ-Ͽἀ-῿]')

def _is_grieks(s):
    return bool(_GRIEKS_RE.search(str(s)))

def _strip_acc(s):
    return ''.join(c for c in unicodedata.normalize('NFD', str(s)) if unicodedata.category(c) != 'Mn')

def _stam_lengte(vormen):
    """Lengte van de gemeenschappelijke stam binnen één declinatie-/vervoegingskolom
    (accent-ongevoelig), zodat we de uitgang erna kunnen inkleuren."""
    vg = [str(v) for v in vormen if v and _is_grieks(v)]
    if len(vg) < 2:
        return 0
    stripped = [_strip_acc(v) for v in vg]
    p = stripped[0]
    for s in stripped[1:]:
        while p and not s.startswith(p):
            p = p[:-1]
    return len(p)

def _kleur_vorm(vorm, stamlen):
    """Kleur de uitgang (alles na de gemeenschappelijke stam) van een Griekse vorm."""
    vorm = str(vorm)
    if stamlen and _is_grieks(vorm) and len(vorm) > stamlen:
        return f"{vorm[:stamlen]}<span style='color:#ff9d5c;font-weight:800'>{vorm[stamlen:]}</span>"
    return vorm

def _noun_g6_target(grieks_info):
    """(genus-woord, nom-uitgang) om binnen G6 de relevante kolom te vinden, uit de woordenboekvorm."""
    gi = str(grieks_info or "")
    delen = [d.strip() for d in gi.replace(';', ',').split(',') if d.strip()]
    if len(delen) < 2:
        return None
    nom = _strip_acc(delen[0]); art = _strip_acc(delen[-1]) if len(delen) >= 3 else ""
    genus = {"ο": "Mannelijk", "η": "Vrouwelijk", "το": "Onzijdig"}.get(art, "")
    if not genus:
        return None
    for e in ["ους", "ουν", "ος", "ον", "ης", "ας", "η", "α"]:
        if nom.endswith(e):
            return (genus, e)
    return None

def _ontleed_doelcel(info):
    """(rij-label, kolom-zoekterm) van de specifieke vorm in een paradigma-tabel, uit parsing_info.
    Naamwoord/participium → rij 'Nom sg' + kolom geslacht; werkwoord → rij '1 sg' + kolom tijd."""
    info = info or ""
    getal = 'pl' if 'mv' in info else 'sg'
    nv = _ontleed_deel_correct('naamval', info)
    if nv != '—':
        ges = {'M': 'mannelijk', 'V': 'vrouwelijk', 'O': 'onzijdig'}.get(_ontleed_deel_correct('geslacht', info), '')
        return (f"{nv} {getal}".lower(), ges)
    pers = _ontleed_deel_correct('persoon', info)
    if pers != '—':
        tijd = _ontleed_deel_correct('tijd', info)
        return (f"{pers[0]} {getal}".lower(), tijd.lower() if tijd != '—' else '')
    return (None, None)

def _render_gramtabel_html(rows, kolom_target=None, mark_row=None, mark_col=None):
    """Render een paradigma-tabel met gekleurde uitgangen. Als kolom_target=(genus, uitgang) is
    opgegeven (voor naamwoorden), toont hij alleen de bijpassende kolom. mark_row/mark_col markeren
    het exacte vakje van de gevraagde vorm (met een pijltje + gouden kader)."""
    if not rows:
        return ""
    # In blokken splitsen op lege rijen (sommige sheets stapelen meerdere tabellen).
    blokken = []; cur = []
    for r in rows:
        if not any(str(c).strip() for c in r):
            if cur:
                blokken.append(cur); cur = []
        else:
            cur.append(r)
    if cur:
        blokken.append(cur)

    def _vind_kolom(header):
        if not kolom_target:
            return None
        _gen, _uit = kolom_target
        for c in range(1, len(header)):
            hc = _strip_acc(header[c]).lower()
            if _gen.lower() in hc and f"-{_uit}" in hc:
                return c
        return None

    _cel = "padding:3px 10px;border:1px solid #444;"
    _lbl = _cel + "font-weight:700;color:#f6c23e;"
    html = "<div style='overflow-x:auto'>"; getoond = False
    for blok in blokken:
        header = blok[0]
        doel_c = _vind_kolom(header)
        if kolom_target and doel_c is None:
            continue  # dit sub-blok bevat de gezochte kolom niet
        cols = [doel_c] if doel_c else list(range(1, len(header)))
        stam = {c: _stam_lengte([blok[i][c] if c < len(blok[i]) else "" for i in range(1, len(blok))]) for c in cols}
        html += "<table style='border-collapse:collapse;font-size:15px;margin-bottom:10px'>"
        html += f"<tr><td style='{_lbl}'>{header[0] if header else ''}</td>"
        for c in cols:
            html += f"<td style='{_cel}font-weight:700'>{header[c] if c < len(header) else ''}</td>"
        html += "</tr>"
        for i in range(1, len(blok)):
            rij = blok[i]
            _rij0 = str(rij[0]) if rij else ""
            _is_mrow = bool(mark_row) and mark_row in _strip_acc(_rij0).lower()
            _lbl_i = _lbl + ("background:rgba(255,215,0,.18);" if _is_mrow else "")
            html += f"<tr><td style='{_lbl_i}'>{('▶ ' if _is_mrow else '') + _rij0}</td>"
            for c in cols:
                v = rij[c] if c < len(rij) else ""
                _hc = _strip_acc(header[c]).lower() if c < len(header) else ""
                _is_mcol = (mark_col == '' ) or (bool(mark_col) and mark_col in _hc)
                _highlight = _is_mrow and _is_mcol and bool(mark_row)
                _cs = _cel + ("background:rgba(255,215,0,.28);border:2px solid #ffd700;" if _highlight else "")
                html += f"<td style='{_cs}'>{_kleur_vorm(v, stam[c])}</td>"
            html += "</tr>"
        html += "</table>"; getoond = True
    html += "</div>"
    if kolom_target and not getoond:
        return _render_gramtabel_html(rows)  # kolom niet gevonden → toch de hele tabel tonen
    return html

def _pref_keuze(widget_fn, label, opties, pref_key, default=None, **kw):
    """radio/selectbox met keuze onthouden in ui_prefs (over sessies heen), met veilige terugval.
    pref_key = de ui_prefs-sleutel; een eventuele widget-`key=` gaat via **kw (mag niet botsen)."""
    p = st.session_state.get('ui_prefs')
    if not isinstance(p, dict):
        p = {}; st.session_state.ui_prefs = p
    opties = list(opties)
    d = default if default is not None else (opties[0] if opties else None)
    v = p.get(pref_key, d)
    try:
        idx = opties.index(v)
    except (ValueError, TypeError):
        idx = 0
    keuze = widget_fn(label, opties, index=idx, **kw)
    p[pref_key] = keuze
    return keuze

def _pref_bool(widget_fn, label, pref_key, default=False, **kw):
    """checkbox/toggle met stand onthouden in ui_prefs (over sessies heen)."""
    p = st.session_state.get('ui_prefs')
    if not isinstance(p, dict):
        p = {}; st.session_state.ui_prefs = p
    val = widget_fn(label, value=bool(p.get(pref_key, default)), **kw)
    p[pref_key] = bool(val)
    return val

@st.cache_data(show_spinner=False)
def bijbel_boek_index(_bijbel_db):
    """boek → hoofdstuk → [(volgnr, vers, referentie)] uit de vers-referenties.

    Gecached: dit ontleedt ~8.000 referenties met regex. Streamlit rendert álle tabbladen bij
    elke rerun, dus zonder cache draaide dit bij iedere klik ergens in de app opnieuw."""
    parsed = {}
    for ref in (_bijbel_db or {}).keys():
        match = re.match(r"^(.+)\s+(\d+):(\d+[a-zA-Z]?)$", ref)
        if match:
            b, c, v = match.group(1), match.group(2), match.group(3)
        else:
            parts = ref.split(" ")
            if len(parts) >= 2 and ":" in parts[-1]:
                cv = parts[-1].split(":"); b, c, v = " ".join(parts[:-1]), cv[0], cv[1]
            else:
                b, c, v = ref, "1", "1"
        _cijfers = re.sub(r"\D", "", v)
        parsed.setdefault(b, {}).setdefault(c, []).append((int(_cijfers) if _cijfers.isdigit() else 0, v, ref))
    for b in parsed:
        for c in parsed[b]:
            parsed[b][c].sort(key=lambda x: x[0])
    return parsed

@st.cache_resource(show_spinner=False)
def bijbel_vorm_index(_bijbel_db):
    """Index: genormaliseerde Griekse vorm → lijst van unieke ontledingen die die vorm in het NT
    kan zijn. Elk item: (grieks, parsing_info, strong, voorbeeld-ref, aantal keer, transliteratie).
    Voor de Zoeken-functie: typ een vorm en zie meteen alle mogelijke ontledingen."""
    idx = {}
    for ref, zin in (_bijbel_db or {}).items():
        for w in zin:
            g = str(w.get('grieks', '') or '')
            key = normaliseer_accent(g)
            if not key:
                continue
            sub = idx.setdefault(key, {})
            pk = (w.get('parsing_info', '') or '', str(w.get('strong', '') or ''))
            if pk in sub:
                _g, _r, _n, _tr = sub[pk]
                sub[pk] = (_g, _r, _n + 1, _tr)
            else:
                sub[pk] = (g, ref, 1, str(w.get('transliteratie', '') or ''))
    # per vorm omzetten naar een lijst, meest voorkomende ontleding eerst
    uit = {}
    for key, sub in idx.items():
        rijen = [(g, pi, strong, ref, n, tr) for (pi, strong), (g, ref, n, tr) in sub.items()]
        rijen.sort(key=lambda r: r[4], reverse=True)
        uit[key] = rijen
    return uit

@st.cache_resource(show_spinner=False)
def _zoek_vormen(_bijbel_db):
    """(genormaliseerde vorm, weergavevorm-met-accenten, totaal aantal) voor de zoeksuggesties."""
    out = []
    for k, rijen in bijbel_vorm_index(_bijbel_db).items():
        out.append((k, rijen[0][0], sum(r[4] for r in rijen)))
    return out

@st.cache_resource(show_spinner=False)
def _struct_vorm_posities(_bijbel_db):
    """{genormaliseerde vorm (ς→σ) → [(ref, woord-index)]} — zodat de Structuurwoorden-tab een
    voorbeeldvers via een dict-lookup vindt i.p.v. het hele NT te scannen bij elke rerun."""
    idx = {}
    for ref, zin in (_bijbel_db or {}).items():
        for iw, w in enumerate(zin):
            key = normaliseer_accent(w.get('grieks', '')).replace('ς', 'σ')
            if key:
                idx.setdefault(key, []).append((ref, iw))
    return idx

def zoek_suggesties(bijbel_db, term, maxn=8):
    """Vergelijkbare Griekse vormen bij een (mogelijk verkeerd getypte) zoekterm: eerst vormen die
    met de invoer beginnen, dan vormen op kleine typ-afstand. → lijst van weergavevormen."""
    key = normaliseer_accent(naar_grieks_transliteratie(str(term or "")))
    if len(key) < 2:
        return []
    prefix, dichtbij, gezien = [], [], set()
    for k, disp, n in _zoek_vormen(bijbel_db):
        if k == key or k in gezien:
            continue
        if k.startswith(key):
            prefix.append((-n, disp)); gezien.add(k)
        elif len(key) >= 3 and abs(len(k) - len(key)) <= 2:
            d = levenshtein(k, key)
            if d <= (1 if len(key) <= 4 else 2):
                dichtbij.append((d, -n, disp)); gezien.add(k)
    prefix.sort(); dichtbij.sort()
    uit = [disp for _s, disp in prefix][:maxn]
    for _d, _s, disp in dichtbij:
        if len(uit) >= maxn:
            break
        if disp not in uit:
            uit.append(disp)
    return uit

@st.cache_resource(show_spinner=False)
def _bijbel_strong_index(_bijbel_db):
    """Index strong-nummer → lijst van vers-referenties (in db-volgorde). Wordt één keer opgebouwd
    en gecached; zonder deze index scande zoek_context_zin bij elk getoond woord de héle NT-database
    lineair. De db is een singleton, dus het onderstreepte argument hoeft niet gehasht te worden."""
    idx = {}
    for ref, zin in (_bijbel_db or {}).items():
        gezien = set()
        for w in zin:
            s = str(w.get('strong', ''))
            if s and s not in gezien:
                gezien.add(s)
                idx.setdefault(s, []).append(ref)
    return idx

def bsb_glosse(en):
    """De Engelse BSB-glosse, of '' als het een placeholder is (bv. 'vvv', '. . .', leeg of alleen
    leestekens). Zo'n placeholder betekent dat de BSB dat woord in een zinsdeel vertaalt in plaats
    van met één los Engels woord — die horen niet in de vertaling-verdeling thuis."""
    s = str(en or "").strip()
    if not s or s.lower() == "vvv":
        return ""
    if not re.search(r"[A-Za-z]", s):   # alleen puntjes/leestekens/cijfers → geen echte glosse
        return ""
    return s

def tel_glossen(glossen):
    """Telt Engelse glossen, hoofdletter-ongevoelig samengevoegd ('All' + 'all' → één; hoofdletters
    zijn later toegevoegd). De vaakst voorkomende schrijfwijze wordt het label. → [(label, aantal)]."""
    import collections as _c
    per_low = _c.defaultdict(_c.Counter)
    for g in glossen:
        if g:
            per_low[g.lower()][g] += 1
    uit = [(cas.most_common(1)[0][0], sum(cas.values())) for cas in per_low.values()]
    uit.sort(key=lambda x: x[1], reverse=True)
    return uit

@st.cache_data(show_spinner=False)
def zoek_vindplaatsen(_bijbel_db, norm_vorm):
    """Alle vindplaatsen van één (genormaliseerde) vorm in het NT: (ref, grieks, parsing_info,
    engelse glosse). Gecached per opgezochte vorm."""
    uit = []
    for ref, zin in (_bijbel_db or {}).items():
        for w in zin:
            if normaliseer_accent(w.get('grieks', '')) == norm_vorm:
                uit.append((ref, str(w.get('grieks', '')), str(w.get('parsing_info', '')),
                            str(w.get('vertaling_bsb', '') or '')))
    return uit

_TIJD_VOLGORDE = ["Praesens", "Imperfectum", "Futurum", "Aoristus", "Perfectum", "Plusquamperfectum"]

@st.cache_data(show_spinner=False)
def werkwoord_vertaling_per_tijd(_bijbel_db, strong):
    """Voor één werkwoord (strong-nummer): per tijd een teller van de Engelse (BSB) vertalingen,
    zodat je ziet hoe de Bijbel bv. de aoristus anders vertaalt dan het perfectum."""
    import collections as _coll
    per = _coll.defaultdict(_coll.Counter)
    strong = str(strong)
    # Alleen de verzen die dit strong-nummer bevatten (via de index) i.p.v. het hele NT scannen.
    for _ref in _bijbel_strong_index(_bijbel_db).get(strong, []):
        for w in (_bijbel_db.get(_ref) or []):
            if str(w.get('strong', '')) != strong:
                continue
            info = w.get('parsing_info', '') or ''
            if "Werkwoord" not in info:
                continue
            tijd = next((t for t in _TIJD_VOLGORDE if t in info), None)
            en = bsb_glosse(w.get('vertaling_bsb', ''))
            if tijd and en:
                per[tijd][en] += 1
    return {t: per[t] for t in _TIJD_VOLGORDE if per.get(t)}

_NAAMVAL_VOLGORDE = [("Nom", "Nominativus"), ("Gen", "Genitivus"), ("Dat", "Dativus"),
                     ("Acc", "Accusativus"), ("Voc", "Vocativus")]

@st.cache_data(show_spinner=False)
def naamwoord_vertaling_per_naamval(_bijbel_db, strong):
    """Voor één naamwoord (strong-nummer): per naamval een teller van de Engelse (BSB) vertalingen,
    zodat je ziet hoe de Bijbel de nominativus anders vertaalt dan bv. de genitivus of dativus."""
    import collections as _coll
    per = _coll.defaultdict(_coll.Counter)
    strong = str(strong)
    for _ref in _bijbel_strong_index(_bijbel_db).get(strong, []):
        for w in (_bijbel_db.get(_ref) or []):
            if str(w.get('strong', '')) != strong:
                continue
            info = w.get('parsing_info', '') or ''
            if "Werkwoord" in info:      # werkwoorden (incl. participia) gaan via per-tijd
                continue
            nv = next((vol for kort, vol in _NAAMVAL_VOLGORDE if kort in info), None)
            en = bsb_glosse(w.get('vertaling_bsb', ''))
            if nv and en:
                per[nv][en] += 1
    return {vol: per[vol] for _k, vol in _NAAMVAL_VOLGORDE if per.get(vol)}

def _regels_per_tijd(per_tijd, max_glossen=4):
    """Markdown-regels: per tijd/naamval de meest voorkomende Engelse vertalingen met aantallen."""
    regels = []
    for sleutel, teller in per_tijd.items():
        top = tel_glossen(teller.elements())[:max_glossen]   # hoofdletter-ongevoelig samengevoegd
        glossen = ", ".join(f"“{g}” ({n}×)" for g, n in top)
        regels.append(f"- **{sleutel}** ({sum(teller.values())}×): {glossen}")
    return regels

_PIE_KLEUREN = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#F0E442", "#999999"]

def cirkeldiagram_html(paren, grootte=170):
    """Kleurenblind-vriendelijk cirkeldiagram (conic-gradient) + legenda met percentages.
    `paren` = [(label, aantal), ...]. Toont de grootste segmenten, rest als 'overig'."""
    paren = [(str(l), int(n)) for l, n in paren if int(n) > 0]
    if not paren:
        return ""
    paren.sort(key=lambda x: x[1], reverse=True)
    if len(paren) > 7:
        rest = sum(n for _l, n in paren[7:])
        paren = paren[:7] + [("overig", rest)]
    totaal = sum(n for _l, n in paren) or 1
    segs, legenda, loop = [], [], 0.0
    for i, (lab, n) in enumerate(paren):
        kl = _PIE_KLEUREN[i % len(_PIE_KLEUREN)]
        pct = n / totaal * 100
        segs.append(f"{kl} {loop:.2f}% {loop + pct:.2f}%")
        loop += pct
        legenda.append(
            f"<div style='display:flex;align-items:center;gap:6px;margin:2px 0;font-size:13px'>"
            f"<span style='width:12px;height:12px;border-radius:3px;background:{kl};display:inline-block'></span>"
            f"<span>{lab} — <b>{n}</b> ({pct:.0f}%)</span></div>")
    return (f"<div style='display:flex;gap:18px;align-items:center;flex-wrap:wrap'>"
            f"<div style='width:{grootte}px;height:{grootte}px;border-radius:50%;flex:0 0 auto;"
            f"background:conic-gradient({', '.join(segs)})'></div>"
            f"<div style='min-width:180px'>{''.join(legenda)}</div></div>")

def toon_engels_diagram(grieks_vorm, bijbel_db, sleutel="", strong=None, parsing_info="", uitgeklapt=False):
    """Uitklapbaar overzicht: hoe wordt déze vorm in het NT in het Engels (BSB) vertaald? Bij een
    werkwoord ook een uitsplitsing per tijd (zo leer je hoe de Bijbel de vormen vertaalt).
    Geeft True terug als er iets te tonen viel."""
    import collections as _coll
    if not bijbel_db:
        return False
    _vp = zoek_vindplaatsen(bijbel_db, normaliseer_accent(grieks_vorm)) if grieks_vorm else []
    _paren = tel_glossen(bsb_glosse(v[3]) for v in _vp)
    _zonder = len(_vp) - sum(n for _l, n in _paren)   # plekken zonder aparte Engelse glosse
    _is_ww = bool(strong) and "Werkwoord" in (parsing_info or "")
    _per_tijd = werkwoord_vertaling_per_tijd(bijbel_db, strong) if _is_ww else {}
    _per_nv = naamwoord_vertaling_per_naamval(bijbel_db, strong) if (strong and not _is_ww) else {}
    if len(_paren) < 2 and not _per_tijd and not _per_nv:
        return False
    with st.expander(f"🇬🇧 Zo vertaalt de Bijbel deze vorm in het Engels ({len(_vp)} vindplaatsen)", expanded=uitgeklapt):
        if len(_paren) >= 2:
            if _per_tijd or _per_nv:
                st.caption("Déze vorm:")
            st.markdown(cirkeldiagram_html(_paren), unsafe_allow_html=True)
            if _zonder:
                st.caption(f"ℹ️ {_zonder} van de {len(_vp)} plekken zijn in een zinsdeel vertaald "
                           "(geen los Engels woord in de BSB).")
        if _per_tijd:
            st.markdown("**Per tijd — zo vertaalt de Bijbel de vormen van dit werkwoord:**")
            for _r in _regels_per_tijd(_per_tijd):
                st.markdown(_r)
        if _per_nv:
            st.markdown("**Per naamval — zo vertaalt de Bijbel de vormen van dit woord:**")
            for _r in _regels_per_tijd(_per_nv):
                st.markdown(_r)
        st.caption("Engelse vertaling per plek (BSB). Alle vindplaatsen zie je in de **🔍 Zoeken**-modus.")
    return True

def biblehub_vers_url(ref):
    """https://biblehub.com/interlinear/<boek>/<hfd>-<vers>.htm voor een referentie als 'Matthew 1:1'."""
    m = re.match(r"^(.*?)\s+(\d+):(\d+)", str(ref or ""))
    if not m:
        return None
    boek = m.group(1).strip().lower().replace(" ", "_")
    return f"https://biblehub.com/interlinear/{boek}/{m.group(2)}-{m.group(3)}.htm"

def biblehub_woord_url(strong):
    """https://biblehub.com/greek/<strong>.htm — de lexicon-pagina van dit woord."""
    s = re.sub(r"\D", "", str(strong or ""))
    return f"https://biblehub.com/greek/{s}.htm" if s else None

def biblehub_regel(ref="", strong=""):
    """Markdown-regel met doorklik-links naar BibleHub (interlinear van het vers + lexicon van het woord)."""
    delen = []
    _vu = biblehub_vers_url(ref)
    if _vu:
        delen.append(f"[interlinear van dit vers]({_vu})")
    _wu = biblehub_woord_url(strong)
    if _wu:
        delen.append(f"[lexicon van dit woord]({_wu})")
    return ("🔗 Op BibleHub: " + " · ".join(delen)) if delen else ""

def zoek_context_zin(strong_nr, woordsoort, bijbel_db, anti_spiek=False, specifieke_vorm=None, bekende_vocab=None, strikte_dekking=False, vastgezet_vers_ref=None, kleur_aan=True, co_doel_strongs=None):
    if not strong_nr or not bijbel_db: return None
    if co_doel_strongs is None: co_doel_strongs = set()
    
    is_specifieke_vervoeging = False
    if specifieke_vorm and bekende_vocab and str(strong_nr) in bekende_vocab:
        lemma_norm = normaliseer_accent(bekende_vocab[str(strong_nr)].get('grieks', ''))
        if normaliseer_accent(specifieke_vorm) != lemma_norm:
            is_specifieke_vervoeging = True
    elif specifieke_vorm and not bekende_vocab:
        is_specifieke_vervoeging = True

    doel_vorm_check = normaliseer_accent(specifieke_vorm) if is_specifieke_vervoeging else None

    if vastgezet_vers_ref and vastgezet_vers_ref in bijbel_db:
        keuze = (vastgezet_vers_ref, bijbel_db[vastgezet_vers_ref])
    else:
        beste_zin = None; fallback_zin = None

        # Alleen de verzen die dit strong-nummer bevatten (via de gecachte index) i.p.v. de hele NT.
        for ref in _bijbel_strong_index(bijbel_db).get(str(strong_nr), []):
            zin = bijbel_db.get(ref)
            if not zin:
                continue
            if strikte_dekking and bekende_vocab:
                lex_items = [w for w in zin if w.get('strong')]
                if len(lex_items) < 3 or any((str(w['strong']) not in bekende_vocab and str(w['strong']) != str(strong_nr)) for w in lex_items):
                    continue

            for w in zin:
                if str(w.get('strong', '')) == str(strong_nr):
                    if doel_vorm_check:
                        if normaliseer_accent(w['grieks']) == doel_vorm_check: beste_zin = (ref, zin); break
                    else:
                        if not fallback_zin: fallback_zin = (ref, zin)
                        p = w.get('parsing_info', '')
                        is_dict_form = False
                        if woordsoort == 'ww' or "Werkwoord" in p:
                            if "1e pers." in p and "ev" in p and "Indicativus" in p: is_dict_form = True
                        elif woordsoort in ['znw', 'bnw', 'lidw'] or any(x in p for x in ["Zelfst.", "Bijv.", "Lidw"]):
                            if "Nom" in p and "ev" in p: is_dict_form = True
                        else: is_dict_form = True 

                        if is_dict_form: beste_zin = (ref, zin); break
            if beste_zin: break
            
        keuze = beste_zin if beste_zin else fallback_zin

    if keuze:
        ref, zin = keuze
        html_zin = ""; grieks_puur = ""; engels_puur = ""
        for zw in zin:
            g_woord = zw['grieks']
            interp = zw.get('interpunctie', '')
            grieks_puur += f"{g_woord}{interp} "
            # Nederlandse glosse als primaire vertaling; val terug op BSB als er geen NL is
            _nl = zw.get('vertaling_nl', '') or zw.get('vertaling_bsb', '')
            engels_puur += f"{_nl} "
            
            is_doelwoord = (str(zw.get('strong', '')) == str(strong_nr)) and (not doel_vorm_check or normaliseer_accent(g_woord) == doel_vorm_check)
            is_sessie_genoot = (str(zw.get('strong', '')) in co_doel_strongs) and not is_doelwoord

            s_id = str(zw.get('strong', ''))
            known_item = bekende_vocab.get(s_id) if bekende_vocab else None

            _nl_glosse = zw.get('vertaling_nl', '')
            _bsb = zw.get('vertaling_bsb', '')
            _parsing = zw.get('parsing_info', '')
            # BSB alleen tonen als er iets zinnigs staat (na opschoning kan hij leeg zijn)
            _anker = f"\nEN: {_bsb}" if _bsb.strip() else ""

            if is_sessie_genoot:
                # Voorkomt dat de zwevende tooltip het antwoord van een komend oefenwoord weggeeft
                tooltip = f"❓ [Oefenwoord in deze vertaalsessie]\n{_parsing}"
            elif known_item and not is_doelwoord:
                nl_t = known_item.get('nederlands', '')
                lem = known_item.get('grieks', '')
                les = known_item.get('les', '?')
                tooltip = f"Les {les} | {lem} → {nl_t}\n{_parsing}{_anker}"
            else:
                # Woord buiten je leslijst: toon de volledige NL-glosse + naamval + BSB-anker
                _kop = _nl_glosse if _nl_glosse else _bsb
                tooltip = f"{_kop}\n{_parsing}{_anker}"

            tooltip = tooltip.replace("'", "&#39;").replace('"', "&quot;")
            
            p_info = zw.get('parsing_info', '')
            kleur_stijl = ""
            if kleur_aan:
                if "Nom" in p_info: kleur_stijl += "color: #33ccff;"
                elif "Gen" in p_info: kleur_stijl += "color: #28a745;"
                elif "Dat" in p_info: kleur_stijl += "color: #6f42c1;"
                elif "Acc" in p_info: kleur_stijl += "color: #dc3545;"
                elif "Voc" in p_info: kleur_stijl += "color: #fd7e14;"
                elif not anti_spiek and ("Voegwoord" in p_info or "Conjunction" in p_info):
                    kleur_stijl += "background-color: #ffd700; color: #000; padding: 0 4px; border-radius: 4px;"
                else: kleur_stijl += "color: #888888;"
            else:
                kleur_stijl = "color: #888888;"
            
            if is_doelwoord:
                # Actieve vraag: Helder wit font met een oplichttend cyaanblauw kader
                w_style = "color: #ffffff; font-weight: 900; background-color: rgba(51, 204, 255, 0.3); border: 2px solid #33ccff; border-bottom: 4px solid #33ccff; padding: 1px 8px; border-radius: 6px; box-shadow: 0 0 10px rgba(51,204,255,0.4);"
                if anti_spiek: html_zin += f"<span tabindex='0' style='{w_style}'>{g_woord}</span>{interp} "
                else: html_zin += f"<span class='mobile-tooltip' tabindex='0' style='{w_style}'>{g_woord}<span class='tooltiptext'>{tooltip}</span></span>{interp} "
            elif is_sessie_genoot:
                # Co-doelwoord binnen hetzelfde vers: permanent helder wit opgelicht met streeplijn
                w_style = "color: #ffffff; font-weight: bold; background-color: rgba(255, 255, 255, 0.1); border-bottom: 2px dashed #ffffff; padding: 1px 5px; border-radius: 4px;"
                html_zin += f"<span class='mobile-tooltip' tabindex='0' style='{w_style}'>{g_woord}<span class='tooltiptext'>{tooltip}</span></span>{interp} "
            else: 
                html_zin += f"<span class='mobile-tooltip' tabindex='0' style='{kleur_stijl} border-bottom: 1px dotted #555;'>{g_woord}<span class='tooltiptext'>{tooltip}</span></span>{interp} "
                
        html_weergave = f"<div style='font-size: 14px; margin-bottom: 5px; color: #f6c23e;'>📖 Context: {ref}</div><div class='grieks-zin' style='font-size: 24px; padding: 15px; margin-bottom: 15px;'>{html_zin.strip()}</div>"
        return {"html": html_weergave, "ref": ref, "grieks_puur": grieks_puur.strip(), "engels_puur": engels_puur.strip()}
    return None

def veilige_json_load(data_str):
    s = str(data_str).strip()
    if not s or s.lower() == 'nan': return {}
    # Eerst als ÉCHTE JSON proberen — zo blijven apostrofs in waarden (bv. "'s avonds") heel.
    try:
        return json.loads(s)
    except Exception:
        pass
    # Terugval voor oude/afwijkende data met slimme aanhalingstekens of enkele quotes.
    try:
        return json.loads(s.replace('“', '"').replace('”', '"').replace("'", '"'))
    except Exception:
        return {}

# --- ALGORITMES & TRACKING ---
def bereken_studietijd_forecast(items_lijst, module_naam, doel_streak=16, dagelijkse_oefeningen=30, sim_accuratesse=None):
    """Berekent de verwachte doorlooptijd op basis van actuele streak-schuld en historische fouten-frictie."""
    if not items_lijst or not st.session_state.get('data'):
        return None
        
    user_woorden = {}
    if isinstance(st.session_state.get('data'), list):
        for w in st.session_state.data:
            if isinstance(w, dict) and 'grieks' in w:
                user_woorden[w['grieks']] = w

    totale_schuld = 0
    tot_goed = 0
    tot_fout = 0
    
    for item in items_lijst:
        if not isinstance(item, dict): continue
        
        grieks_key = item.get('grieks', '')
        w_data = user_woorden.get(grieks_key, {})
        
        try: huidige_streak = int(w_data.get('streak', 0))
        except (ValueError, TypeError): huidige_streak = 0
            
        try: g = int(w_data.get('score_goed', 0))
        except (ValueError, TypeError): g = 0
            
        try: f = int(w_data.get('score_fout', 0))
        except (ValueError, TypeError): f = 0
            
        totale_schuld += max(0, doel_streak - huidige_streak)
        tot_goed += g
        tot_fout += f

    if totale_schuld == 0:
        return {
            "dagen": 0, 
            "einddatum": "Doel al bereikt!", 
            "accuratesse": sim_accuratesse if sim_accuratesse is not None else 100, 
            "netto_winst": 0, 
            "schuld": 0
        }

    if sim_accuratesse is not None:
        accuratesse = sim_accuratesse / 100.0
    else:
        totaal_pogingen = tot_goed + tot_fout
        accuratesse = (tot_goed / totaal_pogingen) if totaal_pogingen > 10 else 0.75
        accuratesse = max(0.50, min(1.0, accuratesse))

    netto_winst_per_oefening = (accuratesse * 1.2) - ((1.0 - accuratesse) * 2.0)
    netto_winst_per_oefening = max(0.08, netto_winst_per_oefening)

    netto_punten_per_dag = max(1, dagelijkse_oefeningen) * netto_winst_per_oefening
    benodigde_dagen = math.ceil(totale_schuld / netto_punten_per_dag)
    
    try:
        eind_datum = _nu() + pd.Timedelta(days=benodigde_dagen)
        datum_str = eind_datum.strftime("%d-%m-%Y")
    except Exception:
        datum_str = f"+{benodigde_dagen} dagen"
    
    return {
        "dagen": benodigde_dagen,
        "einddatum": datum_str,
        "accuratesse": int(accuratesse * 100),
        "netto_winst": round(netto_winst_per_oefening, 2),
        "schuld": totale_schuld
    }
    
def woorden_vandaag_uniek():
    """Hoeveel VERSCHILLENDE woorden je vandaag hebt overhoord (elk woord telt één keer per dag).
    Afgeleid uit 'laatst_geoefend', dus ook na opnieuw inloggen nog kloppend."""
    vandaag = _vandaag_str()
    return sum(1 for w in (st.session_state.get('data') or [])
               if isinstance(w, dict) and str(w.get('laatst_geoefend', '')) == vandaag)

def registreer_oefening(item=None):
    vandaag = str(_nu().date())
    if 'dag_stats' not in st.session_state: st.session_state.dag_stats = {}
    st.session_state.dag_stats[vandaag] = st.session_state.dag_stats.get(vandaag, 0) + 1
    if item is not None:
        item['laatst_geoefend'] = vandaag
        # Het aantal unieke woorden van vandaag meteen in het dagboek zetten, zodat de kalender
        # het later ook voor voorbije dagen kan tonen (laatst_geoefend bewaart maar één datum).
        try:
            dagdoel_log_vandaag()['woorden_uniek'] = woorden_vandaag_uniek()
        except Exception:
            pass

def krijg_streak(item, module):
    return int(item.get('streak', 0))

def vocab_streak_van(grieks_woord, bron=None):
    """Streak van een basiswoord opzoeken, ongeacht Unicode-normalisatie.

    Noodzakelijk omdat stamtijden.json grotendeels in NFD staat en de woordenlijst in NFC:
    een directe `dict.get(praesens)` mist daardoor 36 van de 80 werkwoorden, waardoor die
    stamtijden nooit ontgrendelden."""
    if bron is None:
        bron = st.session_state.get('vocab_stats') or {}
    sleutel = str(grieks_woord or '')
    waarde = bron.get(sleutel)
    if waarde is None:
        # Zelfde woord, andere schrijfwijze: vergelijk accent-ongevoelig.
        doel = normaliseer_accent(sleutel)
        if not doel:
            return 0
        idx = st.session_state.get('_vocab_streak_idx')
        if not isinstance(idx, dict) or idx.get('_bron_n') != len(bron):
            idx = {'_bron_n': len(bron)}
            for k, v in bron.items():
                idx.setdefault(normaliseer_accent(k), v)
            st.session_state._vocab_streak_idx = idx
        waarde = idx.get(doel)
    if isinstance(waarde, dict):
        return int(waarde.get('streak', 0))
    try:
        return int(waarde or 0)
    except (TypeError, ValueError):
        return 0

def _herhaal_interval(streak):
    """Spaced-repetition-interval (in dagen) op basis van de streak: hoe beter je een woord kent,
    hoe langer het wegblijft. Een woord is 'due' zodra er minstens dit aantal dagen voorbij is
    sinds je het laatst oefende. Zo komt beheerste stof niet onnodig vaak terug en nieuwe/zwakke
    stof juist snel."""
    s = int(streak)
    if s <= 1: return 0     # nieuw / net begonnen → elke sessie
    if s <= 3: return 1     # ~dagelijks
    if s <= 7: return 2
    if s <= 15: return 4
    if s <= 29: return 10   # beheerst → ~anderhalve week rust
    return 25               # mastery → ~maandelijks opfrissen

def kies_gefaseerde_oefensessie(doel_lijst, module, custom_counts=None, max_nieuw=2, sorteer_oudste_eerst=False, verbied_nieuwe_woorden=False, totale_db=None):
    nieuw_herstel, nieuw_vers, incubatie, training, beheerst, mastery = [], [], [], [], [], []
    
    for item in doel_lijst:
        s = krijg_streak(item, module)
        if s == 0:
            g = int(item.get('score_goed', 0))
            f = int(item.get('score_fout', 0))
            l = str(item.get('laatst_geoefend', '')).strip()
            # Splitsing tussen gesneuvelde soldaten en maagdelijke woorden
            if g > 0 or f > 0 or l != '':
                nieuw_herstel.append(item)
            else:
                nieuw_vers.append(item)
        elif 1 <= s <= 3: incubatie.append(item)
        elif 4 <= s <= 15: training.append(item)
        elif 16 <= s <= 29: beheerst.append(item)
        else: mastery.append(item)
    
    vandaag_d = _nu().date()

    def dagen_geleden(x):
        d_str = x.get('laatst_geoefend', '')
        if not d_str:
            return 9999  # nooit gedaan telt als 'heel lang geleden'
        try:
            return (vandaag_d - datetime.strptime(d_str, '%Y-%m-%d').date()).days
        except:
            return 9999

    def _fout_dagen_geleden(x):
        d_str = str(x.get('laatst_fout', '') or '').strip()
        if not d_str:
            return None
        try:
            return (vandaag_d - datetime.strptime(d_str, '%Y-%m-%d').date()).days
        except Exception:
            return None

    def struggle_bonus(x):
        # Lichte, schema-vrije 'worstel-score': hardnekkig-foute woorden komen eerder terug.
        # Uitgedrukt in dag-equivalenten zodat het naadloos optelt bij 'dagen geleden'.
        g = int(x.get('score_goed', 0)); f = int(x.get('score_fout', 0))
        streak = int(x.get('streak', 0))
        totaal = g + f
        if totaal == 0:
            return 0
        fout_ratio = f / totaal                     # 0..1: aandeel fouten over de hele historie
        bonus = fout_ratio * 8                       # tot ~8 'extra dagen' voor een altijd-foute
        if streak == 0 and f > 0:
            bonus += 4                               # recent teruggevallen / net fout: extra prioriteit
        bonus -= min(streak, 10) * 0.3               # stevige streak dempt de urgentie licht
        # Spaced repetition op fouten: wat je gisteren/eergisteren fout had, krijgt een flinke
        # voorrang-boost bij je volgende sessie (zolang het nog niet beheerst is).
        fdg = _fout_dagen_geleden(x)
        if fdg is not None and 1 <= fdg <= 3 and streak < 16:
            bonus += (12 if fdg <= 2 else 6)
        return max(0, bonus)

    def _overdue(x):
        # Hoeveel dagen het woord al 'due' is: dagen sinds laatst geoefend minus het
        # spaced-repetition-interval voor zijn streak. Positief = achterstallig (moet terugkomen),
        # negatief = nog netjes op schema (mag even rusten en zakt zo onderaan de rij).
        return dagen_geleden(x) - _herhaal_interval(krijg_streak(x, module))

    # Achterstallige + worstelende woorden bovenaan; woorden die nog op schema liggen onderaan.
    def sorteer_key(x):
        return -(_overdue(x) + struggle_bonus(x))

    incubatie.sort(key=sorteer_key); training.sort(key=sorteer_key); beheerst.sort(key=sorteer_key); mastery.sort(key=sorteer_key)
    
    if sorteer_oudste_eerst: 
        nieuw_herstel.sort(key=sorteer_key)
        nieuw_vers.sort(key=sorteer_key)
    else: 
        r_engine.shuffle(nieuw_herstel)
        r_engine.shuffle(nieuw_vers)
        
    # --- DE ABSOLUTE PRIORITEITSREGEL ---
    # De blokkade treft uitsluitend de onbekende (vers) woorden. 
    # De herstelwoorden staan altijd vooraan in de rij en mogen altijd door de poort.
    actieve_nieuw = nieuw_herstel + ([] if verbied_nieuwe_woorden else nieuw_vers)
    sessie = []

    # ROUTE 1: ZELF SAMENSTELLEN (Strikt binnen de geselecteerde lescriteria)
    if custom_counts is not None:
        c_n = custom_counts.get('nieuw', 0)
        sessie.extend(actieve_nieuw[:c_n])
        sessie.extend(incubatie[:custom_counts.get('incubatie', 0)])
        sessie.extend(training[:custom_counts.get('training', 0)])
        sessie.extend(beheerst[:custom_counts.get('beheerst', 0)])
        sessie.extend(mastery[:custom_counts.get('mastery', 0)])
        r_engine.shuffle(sessie)
        return sessie

    # --- ISOLATIE VAN HET OVERKOEPELENDE HERHALINGSWOORD (Alle eerdere lessen) ---
    extern_herhalingswoord = None
    if totale_db and module == 'vocab':
        doel_grieks = {w.get('grieks') for w in doel_lijst if isinstance(w, dict)}
        geoefend_buiten_selectie = [
            w for w in totale_db 
            if isinstance(w, dict) 
            and w.get('grieks') not in doel_grieks 
            and (int(w.get('streak', 0)) >= 1 or str(w.get('laatst_geoefend', '') or '').strip() != '')
        ]
        if geoefend_buiten_selectie:
            geoefend_buiten_selectie.sort(key=sorteer_key)
            extern_herhalingswoord = geoefend_buiten_selectie[0]

    # ROUTE 2: DE AUTOMATISCHE, GEWICHTS-BEWUSTE MENTOR
    poule_n = actieve_nieuw[:max_nieuw]
    sessie.extend(poule_n)

    if not verbied_nieuwe_woorden:
        poule_inc = incubatie[:3]
        sessie.extend(poule_inc)
        
        ruimte_train = min(len(training), 8 - (len(poule_n) + len(poule_inc)))
        poule_t = training[:ruimte_train]
        sessie.extend(poule_t)
        
        if extern_herhalingswoord: sessie.append(extern_herhalingswoord)
        elif mastery: sessie.append(mastery[0])
        elif beheerst: sessie.append(beheerst[0])
        
        frictie_som = sum(max(0, 16 - krijg_streak(w, module)) for w in (poule_inc + poule_t))
        aanvulling = 1 if frictie_som > 50 else (2 if frictie_som > 25 else 4)
        
        sessie.extend(beheerst[:aanvulling])
    else:
        poule_inc = incubatie[:4]
        sessie.extend(poule_inc)
        
        ruimte_train = min(len(training), 8 - (len(poule_n) + len(poule_inc)))
        poule_t = training[:ruimte_train]
        sessie.extend(poule_t)
        
        if extern_herhalingswoord:
            sessie.append(extern_herhalingswoord)
            if mastery: sessie.append(mastery[0])
        else:
            sessie.extend(mastery[:2])
        
        frictie_som = sum(max(0, 16 - krijg_streak(w, module)) for w in (poule_inc + poule_t))
        aanvulling = 2 if frictie_som > 40 else 4
        
        rest_pool = [w for w in (beheerst + mastery) if w not in sessie]
        sessie.extend(rest_pool[:aanvulling])

    # --- HET KNELPUNTEN VANGNET ---
    # Als de sessie door strenge modus-filters (zoals Knelpunten) nog niet de 10 kaarten haalt, 
    # vullen we agressief aan met alle restanten uit je actieve doel-selectie.
    if len(sessie) < 10:
        rest_alles = [w for w in (actieve_nieuw + incubatie + training + beheerst + mastery) if w not in sessie]
        sessie.extend(rest_alles[:10 - len(sessie)])

    r_engine.shuffle(sessie)
    return sessie
    
def bereken_gewicht(item):
    gewicht = 1.0
    freq = int(item.get('frequentie_nt', 0))
    if freq > 0: gewicht += math.log10(freq + 1)
    gewicht += (int(item.get('score_fout', 0)) * 1.5)
    gewicht -= (int(item.get('score_goed', 0)) * 0.1)
    streak = int(item.get('streak', 0))
    gewicht -= (streak * 0.5)
    if streak >= 30: gewicht *= 0.1 
    return max(0.1, gewicht)

def _is_al_geoefend(w):
    """Een woord telt als 'al geoefend' zodra er ooit een poging op is gedaan."""
    return (int(w.get('streak', 0)) > 0
            or int(w.get('score_goed', 0)) > 0
            or int(w.get('score_fout', 0)) > 0
            or str(w.get('laatst_geoefend', '') or '').strip() != '')

def voeg_verwar_twins_toe(sampled, alle_data, twins_map, max_twins=3):
    """Trekt look-alike twins van reeds-gekozen woorden in dezelfde sessie, zodat de
    student ze naast elkaar leert onderscheiden. Voegt NOOIT nieuwe (ongeoefende) woorden toe."""
    if not twins_map:
        return sampled
    grieks_index = {w.get('grieks'): w for w in alle_data if isinstance(w, dict) and w.get('grieks')}
    al_in_sessie = {w.get('grieks') for w in sampled if isinstance(w, dict)}
    toegevoegd = []
    for w in list(sampled):
        if len(toegevoegd) >= max_twins:
            break
        for twin_grieks in twins_map.get(w.get('grieks', ''), []):
            if len(toegevoegd) >= max_twins:
                break
            if twin_grieks in al_in_sessie:
                continue  # twin zit al in de sessie
            twin_w = grieks_index.get(twin_grieks)
            if twin_w and _is_al_geoefend(twin_w):  # harde eis: nooit een nieuw woord
                toegevoegd.append(twin_w)
                al_in_sessie.add(twin_grieks)
    if toegevoegd:
        sampled = sampled + toegevoegd
        r_engine.shuffle(sampled)  # twins verspreiden i.p.v. achteraan plakken
    return sampled

def voeg_herhaalwoorden_toe(sampled, alle_data, aantal=1):
    """Voegt tot 'aantal' al-geoefende woorden met de OUDSTE laatst_geoefend-datum toe die nog niet
    in de sessie zitten. Zo neemt het Leerpad altijd wat oude stof mee (geheugen-onderhoud)."""
    if aantal <= 0:
        return sampled
    in_sessie = {w.get('grieks') for w in sampled if isinstance(w, dict)}
    kandidaten = [w for w in alle_data
                  if isinstance(w, dict) and w.get('grieks') not in in_sessie and _is_al_geoefend(w)]
    def _sleutel(w):
        d = str(w.get('laatst_geoefend', '') or '').strip()
        return d if d else '0000-00-00'  # nooit gedateerd telt als heel oud
    kandidaten.sort(key=_sleutel)  # oudste datum eerst
    toevoegen = kandidaten[:aantal]
    if toevoegen:
        sampled = list(sampled) + toevoegen
        r_engine.shuffle(sampled)
    return sampled

# --- VERWARWOORDEN: DETECTIE, TRACKING & SELECTIE ---
def _betekenis_delen(ned):
    """Splitst een Nederlandse glosse in losse, genormaliseerde betekenis-delen. Gebruikt voor de
    reverse-lookup: hier willen we LETTERLIJKE overeenkomst, geen typo-marge (Levenshtein)."""
    s = str(ned).lower().strip()
    s = s.replace(';', ',').replace('/', ',')
    s = re.sub(r'\([^)]*\)', '', s)
    s = re.sub(r'\[[^\]]*\]', '', s)
    s = re.sub(r'\{[^}]*\}', '', s)
    s = s.replace('=', ' ').replace('*', ' ').replace('+', ' ')
    delen = set()
    for d in s.split(','):
        d = re.sub(r'^[^\wα-ωά-ώϊϋΐΰ]+|[^\wα-ωά-ώϊϋΐΰ]+$', '', d.strip()).strip()
        if d:
            delen.add(d)
    return delen

_LEIDWOORDEN = ("de ", "het ", "een ", "te ", "'t ")
def _kern(s):
    """Strip een eventueel lidwoord/infinitief-marker vooraan, zodat 'het leven' == 'leven'."""
    s = s.strip()
    for a in _LEIDWOORDEN:
        if s.startswith(a):
            return s[len(a):].strip()
    return s

def betekenis_exact(typed, ned):
    """True als het getypte antwoord LETTERLIJK één van de betekenis-delen is (lidwoord genegeerd).
    Geen Levenshtein — anders matcht 'zeven' op 'geven'/'leven' en krijg je willekeurige treffers."""
    t = re.sub(r'^[^\wα-ωά-ώϊϋΐΰ]+|[^\wα-ωά-ώϊϋΐΰ]+$', '', str(typed).lower().strip()).strip()
    if not t:
        return False
    delen = _betekenis_delen(ned)
    kernen = {_kern(d) for d in delen}
    return t in delen or t in kernen or _kern(t) in delen or _kern(t) in kernen

def zelfde_betekenis(a, b):
    """True als twee glosses écht synoniem zijn: dezelfde set deel-betekenissen, ongeacht volgorde
    ('meteen, onmiddellijk' == 'onmiddellijk, meteen'). Bewust streng: gedeeltelijke overlap
    ('meteen, snel' vs 'meteen, onmiddellijk') telt NIET als hetzelfde. Kleine typo's per deel mogen."""
    da = {_kern(d) for d in _betekenis_delen(a)}
    db = {_kern(d) for d in _betekenis_delen(b)}
    if not da or not db or len(da) != len(db):
        return False
    if da == db:
        return True
    rest = set(db)
    for x in da:
        gevonden = None
        for y in rest:
            if x == y or (len(y) > 4 and levenshtein(x, y) <= 1) or (len(y) > 8 and levenshtein(x, y) <= 2):
                gevonden = y; break
        if gevonden is None:
            return False
        rest.discard(gevonden)
    return not rest

def woorden_met_zelfde_betekenis(typed, alle_data, exclude_grieks=None, alleen_geoefend=True, max_n=5):
    """Reverse-lookup: geeft de woorden terug waarvan de betekenis LETTERLIJK overeenkomt met wat de
    student typte/koos. Zo zie je met welk (al geoefend) woord je het mogelijk verwarde.
    Standaard alleen woorden die minstens één keer goed óf fout zijn gedaan."""
    typed = str(typed).strip()
    if not typed:
        return []
    treffers = []
    for w in alle_data:
        if not isinstance(w, dict):
            continue
        g = w.get('grieks', '')
        if not g or g == exclude_grieks:
            continue
        if alleen_geoefend and not _is_al_geoefend(w):
            continue
        ned = str(w.get('nederlands', '')).strip()
        if not ned:
            continue
        if betekenis_exact(typed, ned):
            treffers.append(w)
        if len(treffers) >= max_n:
            break
    return treffers

def registreer_verwarring(getoond_grieks, verward_grieks):
    """Legt vast dat de student, bij het overhoren van 'getoond', het antwoord van 'verward' gaf.
    Slaat een teller + datum op in verwar_stats (later te oefenen via 'Mijn verwarwoorden')."""
    if not getoond_grieks or not verward_grieks or getoond_grieks == verward_grieks:
        return
    vs = st.session_state.get('verwar_stats')
    if not isinstance(vs, dict):
        vs = {}
        st.session_state.verwar_stats = vs
    try:
        vandaag = str(_nu().date())
    except Exception:
        vandaag = ""
    entry = vs.setdefault(getoond_grieks, {})
    rec = entry.setdefault(verward_grieks, {"n": 0, "laatst": ""})
    rec["n"] = int(rec.get("n", 0)) + 1
    rec["laatst"] = vandaag

def verzwak_verwarring(getoond_grieks):
    """Een goed antwoord dempt de geregistreerde verwarringen van dit woord; op nul verdwijnt het
    paar. Zo verlaten woorden vanzelf de 'Mijn verwarwoorden'-lijst zodra ze weer goed gaan."""
    vs = st.session_state.get('verwar_stats', {})
    if not isinstance(vs, dict) or getoond_grieks not in vs:
        return
    entry = vs[getoond_grieks]
    for k in list(entry.keys()):
        entry[k]["n"] = int(entry[k].get("n", 0)) - 1
        if entry[k]["n"] <= 0:
            del entry[k]
            # cumulatieve teller voor de 'Ontward'-badge (opgeloste verwarringen)
            _bd = st.session_state.get('badges')
            if isinstance(_bd, dict):
                _bd['_verwar_opgelost'] = int(_bd.get('_verwar_opgelost', 0)) + 1
    if not entry:
        del vs[getoond_grieks]

def _onthoud_verwar_kandidaten(getoond, getoond_ned, typed, kandidaten):
    """Bewaart mogelijke-verwar-kandidaten van de huidige sessie, zodat de student ze aan het eind
    zélf kan bevestigen (i.p.v. ze automatisch toe te voegen — dat vervuilde de lijst)."""
    if not kandidaten:
        return
    acc = st.session_state.get('sessie_verwar_kandidaten')
    if not isinstance(acc, dict):
        acc = {}
        st.session_state.sessie_verwar_kandidaten = acc
    rec = acc.setdefault(getoond, {"nederlands": getoond_ned, "antwoord": "", "kandidaten": {}})
    rec["nederlands"] = getoond_ned
    rec["antwoord"] = str(typed)
    rec["kandidaten"].update(kandidaten)

def bouw_verwar_melding(item, typed, alle_data, twins_map, onthoud=True):
    """Bouwt de 'let op — mogelijk verward'-melding op basis van (a) betekenis-overlap met wat je
    typte/koos en (b) look-alikes op spelling. Voegt NIETS automatisch toe aan verwar_stats, maar
    onthoudt de kandidaten voor de eindsamenvatting (waar je zelf bevestigt wat klopte)."""
    getoond = item.get('grieks', '')
    delen = []
    kandidaten = {}  # grieks -> nederlands
    zelfde = woorden_met_zelfde_betekenis(typed, alle_data, exclude_grieks=getoond, alleen_geoefend=True)
    if zelfde:
        labels = [f"**{w.get('grieks','')}** ({str(w.get('nederlands',''))[:30]})" for w in zelfde]
        delen.append(f"Je gaf *“{str(typed).strip()}”* — dat is de betekenis van: " + "; ".join(labels))
        for w in zelfde:
            kandidaten[w.get('grieks', '')] = str(w.get('nederlands', ''))
    idx = {w.get('grieks'): w for w in alle_data if isinstance(w, dict) and w.get('grieks')}
    tw_labels = []
    for tg in (twins_map.get(getoond, []) if twins_map else []):
        tw = idx.get(tg)
        if tw and _is_al_geoefend(tw):
            tw_labels.append(f"**{tg}** ({str(tw.get('nederlands',''))[:25]})")
            kandidaten[tg] = str(tw.get('nederlands', ''))
        if len(tw_labels) >= 3:
            break
    if tw_labels:
        delen.append("Lijkt qua vorm op: " + "; ".join(tw_labels))
    if onthoud:
        _onthoud_verwar_kandidaten(getoond, str(item.get('nederlands', '')), typed, kandidaten)
    if not delen:
        return ""
    return "\n\n⚠️ **Let op — mogelijk verward:**\n\n- " + "\n- ".join(delen)

def _sessie_noteer_goed(item):
    """Registreert (in-memory) dat dit woord in de huidige sessie goed ging — voor de eindsamenvatting."""
    d = st.session_state.get('sessie_goed')
    if not isinstance(d, dict):
        d = {}
        st.session_state.sessie_goed = d
    d[item.get('grieks', '')] = str(item.get('nederlands', ''))

def _sessie_noteer_fout(item, antwoord):
    """Registreert (in-memory) dat dit woord in de huidige sessie fout ging, met het gegeven antwoord.
    Stempelt ook de fout-datum (voor spaced repetition: gisteren-fout komt morgen weer bovenaan)."""
    d = st.session_state.get('sessie_fout')
    if not isinstance(d, dict):
        d = {}
        st.session_state.sessie_fout = d
    d[item.get('grieks', '')] = {"nederlands": str(item.get('nederlands', '')), "antwoord": str(antwoord)}
    try:
        item['laatst_fout'] = str(_nu().date())
    except Exception:
        pass

def _sessie_reset_samenvatting():
    """Leegt de sessie-accumulatoren voor de eindsamenvatting."""
    st.session_state.sessie_goed = {}
    st.session_state.sessie_fout = {}
    st.session_state.sessie_verwar_kandidaten = {}

def _is_geoefend(w):
    """Woord is al eens overhoord (heeft een goed/fout-score)."""
    try:
        return (int(w.get('score_goed', 0)) + int(w.get('score_fout', 0))) > 0
    except (ValueError, TypeError):
        return False

def verzamel_lookalikes(poule, twins_map, alleen_geoefend=True):
    """Doel-lijst voor 'Gelijkende woorden': woorden binnen de selectie die een look-alike-twin
    (op spelling) hebben, plus de twin-partners die ook in de selectie zitten. Standaard alleen
    woorden die je al eens hebt geoefend (een goed/fout-score hebben) — geen ongeziene woorden."""
    if not twins_map:
        return []
    _pool = [w for w in poule if isinstance(w, dict) and w.get('grieks')
             and (not alleen_geoefend or _is_geoefend(w))]
    idx = {w.get('grieks'): w for w in _pool}
    doel = {}
    for w in _pool:
        g = w.get('grieks', '')
        if not twins_map.get(g):
            continue
        # alleen een paar als óók de twin in de (geoefende) selectie zit
        _twins_in = [tg for tg in twins_map.get(g, []) if tg in idx]
        if not _twins_in:
            continue
        doel[g] = w
        for tg in _twins_in:
            if tg not in doel:
                doel[tg] = idx[tg]
    return list(doel.values())

def verzamel_verwarwoorden(alle_data, verwar_stats):
    """Doel-lijst voor 'Mijn verwarwoorden': woorden die je aantoonbaar verwart en die je nog
    niet beheerst (streak < 16). Beheerste woorden vallen vanzelf uit de lijst."""
    idx = {w.get('grieks'): w for w in alle_data if isinstance(w, dict) and w.get('grieks')}
    gekozen = {}
    for getoond, entry in (verwar_stats or {}).items():
        w_g = idx.get(getoond)
        if not w_g:
            continue
        actief = {k: v for k, v in entry.items() if int(v.get('n', 0)) > 0}
        if not actief:
            continue
        if int(w_g.get('streak', 0)) >= 16:  # onder de knie → uit de oefenlijst
            continue
        gekozen[getoond] = w_g
        for verward in actief:
            w_v = idx.get(verward)
            if w_v and verward not in gekozen:
                gekozen[verward] = w_v
    return list(gekozen.values())

def verwar_paren_lijst(alle_data, verwar_stats):
    """Unieke (ongeordende) verwarparen met teller + datum — voor het overzicht én de paar-oefening."""
    idx = {w.get('grieks'): w for w in alle_data if isinstance(w, dict) and w.get('grieks')}
    seen = {}
    for a, entry in (verwar_stats or {}).items():
        for b, rec in (entry or {}).items():
            if int(rec.get('n', 0)) <= 0 or a not in idx or b not in idx:
                continue
            key = tuple(sorted((a, b)))
            n = int(rec.get('n', 0)); laatst = str(rec.get('laatst', ''))
            if key in seen:
                seen[key]['n'] += n
                seen[key]['laatst'] = max(seen[key]['laatst'], laatst)
            else:
                seen[key] = {'a': key[0], 'b': key[1], 'n': n, 'laatst': laatst}
    paren = list(seen.values())
    for p in paren:
        p['a_ned'] = str(idx[p['a']].get('nederlands', ''))
        p['b_ned'] = str(idx[p['b']].get('nederlands', ''))
        p['a_streak'] = int(idx[p['a']].get('streak', 0))
        p['b_streak'] = int(idx[p['b']].get('streak', 0))
    paren.sort(key=lambda p: (p['n'], p['laatst']), reverse=True)
    return paren

def voeg_eigen_verwar_toe(sampled, alle_data, verwar_stats, max_extra=3):
    """Trekt bij woorden in de sessie de eigen-verwarde partners (uit verwar_stats) erbij, zolang het
    paar nog actief is — zo blijf je ze samen zien tot je ze allebei beheerst (en het paar wegvalt)."""
    if not verwar_stats:
        return sampled
    idx = {w.get('grieks'): w for w in alle_data if isinstance(w, dict) and w.get('grieks')}
    in_sessie = {w.get('grieks') for w in sampled if isinstance(w, dict)}
    toegevoegd = []
    for w in list(sampled):
        if len(toegevoegd) >= max_extra:
            break
        for pg, rec in (verwar_stats.get(w.get('grieks', ''), {}) or {}).items():
            if len(toegevoegd) >= max_extra:
                break
            if int(rec.get('n', 0)) <= 0 or pg in in_sessie:
                continue
            pw = idx.get(pg)
            if pw:
                toegevoegd.append(pw)
                in_sessie.add(pg)
    if toegevoegd:
        sampled = sampled + toegevoegd
        r_engine.shuffle(sampled)
    return sampled

def bouw_verwar_paren(alle_data, verwar_stats):
    """Lijst van (woordA, woordB)-paren voor de paar-oefening, meest-verward eerst."""
    idx = {w.get('grieks'): w for w in alle_data if isinstance(w, dict) and w.get('grieks')}
    paren = []
    for p in verwar_paren_lijst(alle_data, verwar_stats):
        wa, wb = idx.get(p['a']), idx.get(p['b'])
        if wa and wb:
            paren.append((wa, wb))
    return paren

def bouw_lookalike_paren(poule, twins_map, rng=None, doel_lengte=16):
    """(woordA, woordB)-paren van spelling-gelijkende woorden, voor de paar-oefening ('Gelijkende
    woorden'). Bouwt een GEWOGEN mix i.p.v. álle paren: paren met woorden die je vaak fout doet
    komen vaker terug, makkelijke minder — en de sessie wordt begrensd op ~doel_lengte paren."""
    if not twins_map:
        return []
    rng = rng or r_engine
    idx = {w.get('grieks'): w for w in poule if isinstance(w, dict) and w.get('grieks')}
    seen = set()
    paren = []
    for w in poule:
        if not isinstance(w, dict):
            continue
        g = w.get('grieks', '')
        for tg in (twins_map.get(g) or []):
            wb = idx.get(tg)
            if not wb:
                continue
            sleutel = tuple(sorted([g, tg]))
            if sleutel in seen:
                continue
            seen.add(sleutel)
            paren.append((w, wb))
    if not paren:
        return []

    def _druk(w):
        # Foutdruk: meer fouten en een lage streak → zwaarder gewicht (vaker vragen).
        try:
            f = int(w.get('score_fout', 0)); s = int(w.get('streak', 0))
        except (ValueError, TypeError):
            f, s = 0, 0
        return 1 + 2 * f + (1 if s <= 3 else 0)

    gewichten = [_druk(a) + _druk(b) for a, b in paren]
    if len(paren) <= doel_lengte:
        # Weinig paren: elk paar minstens één keer (dekking), daarna gewogen aanvullen.
        queue = list(paren)
        extra = doel_lengte - len(queue)
        if extra > 0 and sum(gewichten) > 0:
            queue += rng.choices(paren, weights=gewichten, k=extra)
    else:
        # Veel paren: gewogen selectie i.p.v. alles — de lastige komen vaker, makkelijke soms niet.
        queue = rng.choices(paren, weights=gewichten, k=doel_lengte)
    rng.shuffle(queue)
    return queue

# --- BADGES / ACHIEVEMENTS ---
def badge_definities(m):
    """Bouwt de lijst met badges op basis van samengevatte statistieken (m). Puur afgeleid van
    bestaande cijfers; alleen de 'eerste keer behaald'-datum wordt apart bewaard in badges-dict."""
    B = []
    _ROM = ["I", "II", "III", "IV", "V", "VI", "VII"]
    def add(bid, icon, titel, uitleg, behaald, voortgang=""):
        B.append({"id": bid, "icon": icon, "titel": titel, "uitleg": uitleg,
                  "behaald": bool(behaald), "voortgang": voortgang})

    def trap(basis_id, icon, naam, eenheid, waarde, drempels):
        """Voegt een oplopende reeks (I, II, III, ...) badges toe voor één statistiek."""
        for i, dr in enumerate(drempels):
            add(f"{basis_id}{i+1}", icon, f"{naam} {_ROM[i]}", f"{dr} {eenheid}.",
                waarde >= dr, f"{min(waarde, dr)}/{dr}")

    beo = int(m.get('beoordelingen', 0))
    add("start", "🌱", "Eerste stappen", "Je allereerste woord geoefend.", beo >= 1)
    trap("vlijt", "📚", "Vlijt", "beoordelingen", beo, [100, 500, 1500, 5000, 12000])

    dagen = int(m.get('oefendagen', 0))
    trap("trouw", "📅", "Trouw", "oefendagen", dagen, [3, 7, 30, 100])

    ds = int(m.get('dagstreak', 0))
    trap("vuur", "🔥", "Vuur", "dagen op rij", ds, [3, 7, 14, 30])

    beh = int(m.get('beheerst', 0))
    add("eerste_beh", "🛡️", "Eerste beheersing", "Je eerste woord beheerst (streak ≥ 16).", beh >= 1)
    trap("beheer", "🏛️", "Beheersing", "woorden beheerst", beh, [25, 100, 250, 500])

    mast = int(m.get('mastery', 0))
    add("mast1", "⭐", "Mastery-starter", "Je eerste woord op Mastery (streak ≥ 30).", mast >= 1)
    trap("meester", "🌟", "Meesterschap", "woorden op mastery", mast, [10, 50, 150])

    acc = int(m.get('accuratesse', 0))
    add("prec1", "🎯", "Precisie I", "80% accuratesse (min. 50 beoordelingen).", acc >= 80 and beo >= 50, f"{acc}%")
    add("prec2", "🎯", "Precisie II", "90% accuratesse (min. 100 beoordelingen).", acc >= 90 and beo >= 100, f"{acc}%")
    add("prec3", "🏹", "Precisie III", "95% accuratesse (min. 200 beoordelingen).", acc >= 95 and beo >= 200, f"{acc}%")

    dek = int(m.get('dekking', 0))
    trap("lezer", "🌍", "NT-lezer", "% NT-dekking", dek, [10, 25, 50, 75])

    opg = int(m.get('verwar_opgelost', 0))
    trap("ontward", "🧩", "Ontward", "verwarringen opgelost", opg, [5, 25, 75])

    sb = int(m.get('stam_beheerst', 0))
    add("stam_start", "⏳", "Stamtijd-starter", "Je eerste stamtijd-vorm beheerst (streak ≥ 16).", sb >= 1)
    trap("stamvorm", "🏺", "Stamtijden", "stamtijd-vormen beheerst", sb, [10, 40, 100])

    sc = int(m.get('struct_beheerst', 0))
    add("struct_start", "🧱", "Structuur-starter", "Je eerste structuurwoord beheerst (streak ≥ 16).", sc >= 1)
    trap("structw", "🏗️", "Structuurwoorden", "structuurwoorden beheerst", sc, [10, 40, 90])

    niv = int(m.get('niveau', 0))
    if niv >= 1:
        trap("rang", "🎖️", "Rang", "leerpad-niveau bereikt", niv, [5, 10, 20, 35, 50])
    return B

# --- LEERPAD (levels + XP, Duolingo-stijl) ---
LEERPAD_CHUNK = 7      # aantal woorden per level
LEERPAD_DREMPEL = 5    # streak waarop een woord binnen het pad als 'af' telt
LEERPAD_TYP_STREAK = 3 # vanaf deze streak oefen je het woord door te TYPEN; moet < LEERPAD_DREMPEL
                       # blijven, anders is een level 'af' vóórdat de typ-fase ooit begint.

def bereken_xp(alle_data):
    """XP is puur opbouwend (kan niet dalen): elke goede beurt telt, plus bonus per mijlpaal."""
    xp = 0
    for w in alle_data:
        if not isinstance(w, dict):
            continue
        xp += int(w.get('score_goed', 0)) * 10
        s = int(w.get('streak', 0))
        if s >= 5: xp += 10
        if s >= 16: xp += 25
        if s >= 30: xp += 50
    return xp

# Je rang is een Bijbelboek: je begint bij Genesis en werkt je door de hele Bijbel heen naar
# Openbaring. Hoe verder het boek, hoe meer je kent — en er is dus altijd nog een volgend boek.
_RANG_TITELS = [
    "Genesis", "Exodus", "Leviticus", "Numeri", "Deuteronomium", "Jozua", "Richteren", "Ruth",
    "1 Samuël", "2 Samuël", "1 Koningen", "2 Koningen", "1 Kronieken", "2 Kronieken", "Ezra",
    "Nehemia", "Ester", "Job", "Psalmen", "Spreuken", "Prediker", "Hooglied", "Jesaja", "Jeremia",
    "Klaagliederen", "Ezechiël", "Daniël", "Hosea", "Joël", "Amos", "Obadja", "Jona", "Micha",
    "Nahum", "Habakuk", "Sefanja", "Haggai", "Zacharia", "Maleachi",
    "Matteüs", "Marcus", "Lucas", "Johannes", "Handelingen", "Romeinen", "1 Korintiërs",
    "2 Korintiërs", "Galaten", "Efeziërs", "Filippenzen", "Kolossenzen", "1 Tessalonicenzen",
    "2 Tessalonicenzen", "1 Timoteüs", "2 Timoteüs", "Titus", "Filemon", "Hebreeën", "Jakobus",
    "1 Petrus", "2 Petrus", "1 Johannes", "2 Johannes", "3 Johannes", "Judas", "Openbaring",
]
RANG_UITLEG = ("📖 Je rang is een Bijbelboek: je begint bij **Genesis** en leest je een weg naar "
               "**Openbaring**. Hoe verder in de Bijbel, hoe meer Grieks je kent — "
               f"{len(_RANG_TITELS)} rangen in totaal, dus er is altijd een volgend boek te halen.")

def niveau_van_xp(xp):
    """Zet XP om in een oplopend niveau; de benodigde XP per niveau groeit gestaag (100, 175, 250, ...)."""
    niveau = 0
    nodig = 100
    rest = int(xp)
    while rest >= nodig:
        rest -= nodig
        niveau += 1
        nodig += 75
    _ri = min(niveau // 2, len(_RANG_TITELS) - 1)
    titel = _RANG_TITELS[_ri]
    _volgend = _RANG_TITELS[_ri + 1] if _ri + 1 < len(_RANG_TITELS) else None
    return {"niveau": niveau, "titel": titel, "xp_totaal": int(xp),
            "xp_in_niveau": rest, "xp_voor_volgend": nodig,
            "rang_nr": _ri + 1, "rang_totaal": len(_RANG_TITELS), "volgende_rang": _volgend}

def bouw_leerpad_levels(alle_data, chunk=LEERPAD_CHUNK):
    """Deelt de woordenschat op in kleine levels in les-volgorde; elk level ≈ chunk woorden."""
    per_les = {}
    for w in alle_data:
        if isinstance(w, dict) and w.get('grieks'):
            per_les.setdefault(veilig_les_nummer(w), []).append(w)
    levels = []
    idx = 0
    for les in sorted(per_les.keys()):
        woorden = sorted(per_les[les], key=lambda w: str(w.get('grieks', '')))
        for start in range(0, len(woorden), chunk):
            idx += 1
            levels.append({"index": idx, "les": les,
                           "titel": f"Les {les} · deel {(start // chunk) + 1}",
                           "woorden": woorden[start:start + chunk]})
    return levels

def leerpad_status(levels, drempel=LEERPAD_DREMPEL):
    """Per level: hoeveel woorden 'af' zijn, of het voltooid is en of het ontgrendeld is
    (het eerste level altijd; elk volgend level zodra het vorige voltooid is)."""
    status = []
    vorige_voltooid = True
    for lv in levels:
        totaal = len(lv["woorden"])
        klaar = sum(1 for w in lv["woorden"] if int(w.get('streak', 0)) >= drempel)
        voltooid = totaal > 0 and klaar == totaal
        status.append({**lv, "klaar": klaar, "totaal": totaal,
                       "voltooid": voltooid, "ontgrendeld": vorige_voltooid})
        vorige_voltooid = voltooid
    return status

# Vaste volgorde voor grammaticale invoer (overal dezelfde dropdown-opties).
NAAMVAL_OPTIES = ["Nom", "Gen", "Dat", "Acc"]
GESLACHT_OPTIES = ["M", "V", "O"]
GETAL_OPTIES = ["Ev", "Mv"]

def sorteer_grammaticaal(opties):
    """Zet grammaticale MC-opties in vaste didactische volgorde: naamval (Nom, Gen, Dat, Acc, Voc),
    dan getal (Ev, Mv), dan geslacht/persoon (M, V, O, 1e, 2e, 3e). Niet-grammaticale termen komen
    daarna, alfabetisch. Zo staan de keuzes altijd in dezelfde volgorde i.p.v. gehusseld."""
    _nv = {"nom": 0, "nominativus": 0, "gen": 1, "genitivus": 1, "dat": 2, "dativus": 2,
           "acc": 3, "accusativus": 3, "voc": 4, "vocativus": 4}
    _gt = {"ev": 0, "mv": 1}
    _gs = {"m": 0, "v": 1, "o": 2, "1e": 3, "2e": 4, "3e": 5}
    def _sleutel(opt):
        toks = re.findall(r"[a-zà-ÿ0-9]+", str(opt).lower())
        r_nv = min([_nv[t] for t in toks if t in _nv], default=9)
        r_gt = min([_gt[t] for t in toks if t in _gt], default=9)
        r_gs = min([_gs[t] for t in toks if t in _gs], default=9)
        return (0 if r_nv < 9 else 1, r_nv, r_gt, r_gs, str(opt).lower())
    return sorted(opties, key=_sleutel)

def leerpad_kaart_volgorde(sampled):
    """Bouwt de Leerpad-oefenkaarten met oplopende moeilijkheid: nieuwe woorden eerst als flashcard
    (Leer: zie het antwoord, klik 'Volgende' als je klaar bent) + een eerste meerkeuze; woorden in
    training via meerkeuze; en pas bij een stevige streak via typen."""
    kaarten = []
    for w in sampled:
        s = int(w.get('streak', 0))
        if s <= 0:
            kaarten.append((w, '1'))   # flashcard / leren
            kaarten.append((w, '2'))   # meteen een eerste meerkeuze
        elif s < LEERPAD_TYP_STREAK:
            kaarten.append((w, '2'))   # meerkeuze
        else:
            kaarten.append((w, '4'))   # typen
    return kaarten

# --- DAGELIJKS DOEL ---
# Label voor "de app kiest de oefenvorm zelf" - overal hetzelfde in de app.
_NR = chr(10) + chr(10)   # lege regel in markdown-tekst
AUTO_VORM = "🤖 Automatisch (aanbevolen)"
_STAM_VORMEN = [AUTO_VORM, "🔢 MC", "🔀 Mix (MC + Typen)", "⌨️ Typen"]
_STRUCT_VORMEN = [AUTO_VORM, "1. MC", "2. Mix (MC + Typen)", "3. Typen"]

# --- Welke tabbladen wil je zien? (aan/uit in ℹ️ Uitleg & Hulp) ---
# De volgorde hier is ook de volgorde in de tabbalk.
TAB_KEUZE = [
    ("woorden", "🚀 Woordenschat"), ("ontleden", "🔎 Ontleden"), ("actief", "🎓 Actief Beheersen"),
    ("stam", "⏳ Stamtijden"), ("lezen", "📝 Leesteksten"), ("klank", "🔊 Klankwetten"),
    ("struct", "🧱 Structuurwoorden"), ("voortgang", "📊 Voortgang"), ("lijst", "📖 Lijst"),
    ("gram", "📐 Grammatica"), ("uitleg", "ℹ️ Uitleg & Hulp"), ("nlgr", "✍️ NL → Grieks (productie)"),
]
# Deze twee blijven altijd staan: via Uitleg zet je tabbladen weer aan, en Voortgang is je overzicht.
TAB_ALTIJD = {"uitleg", "voortgang"}

def nieuwe_gebruiker():
    """True zolang er nog nooit iets geoefend is. De app opent dan op ℹ️ Uitleg & Hulp, zodat je
    eerst ziet hoe alles werkt in plaats van meteen in een overhoring te vallen."""
    if st.session_state.get('dag_stats') or {}:
        return False
    for w in (st.session_state.get('data') or []):
        if not isinstance(w, dict):
            continue
        try:
            if int(w.get('streak', 0) or 0) or int(w.get('score_goed', 0) or 0) or int(w.get('score_fout', 0) or 0):
                return False
        except (TypeError, ValueError):
            return False
        if str(w.get('laatst_geoefend', '') or '').strip():
            return False
    return True

def tab_zichtbaar(sleutel):
    if sleutel in TAB_ALTIJD:
        return True
    _p = st.session_state.get('ui_prefs')
    _uit = (_p or {}).get('verborgen_tabs') or []
    return sleutel not in _uit

DAGDOEL_STANDAARD = {'woorden': 10, 'verwar': 3, 'knelpunt': 5, 'actief': 5, 'stam': 5, 'struct': 5,
                     'verzen': 2, 'klank': 5}

def dagdoel_config():
    cfg = (st.session_state.get('dagdoel') or {}).get('config') or {}
    return {k: int(cfg.get(k, v)) for k, v in DAGDOEL_STANDAARD.items()}

def _vandaag_str():
    try:
        return str(_nu().date())
    except Exception:
        return ""

def dagdoel_log_vandaag():
    d = st.session_state.get('dagdoel')
    if not isinstance(d, dict):
        d = {}
        st.session_state.dagdoel = d
    return d.setdefault('log', {}).setdefault(_vandaag_str(), {})

def dagdoel_plus(soort, n=1):
    lg = dagdoel_log_vandaag()
    lg[soort] = int(lg.get(soort, 0)) + n

def dagdoel_woordblok_af():
    dagdoel_log_vandaag()['woordblok'] = True

def dagdoel_streak():
    """Aantal dagen op rij dat je iets hebt geoefend (wat dan ook telt mee).

    Vandaag telt alleen mee als je vandaag al iets deed; heb je vandaag nog niets gedaan,
    dan blijft de streak van gisteren staan zolang je hem vandaag nog kunt voortzetten."""
    stats = st.session_state.get('dag_stats') or {}
    log = (st.session_state.get('dagdoel') or {}).get('log', {})

    def _geoefend(d):
        if int(stats.get(d, 0)) > 0:
            return True
        # Vangnet voor oude data van vóór deze telling: een ingevuld dagdoel-log telt ook.
        _lg = log.get(d)
        return bool(_lg) if isinstance(_lg, dict) else False

    streak = 0
    try:
        cur = pd.Timestamp(_nu().date())
        if not _geoefend(str(cur.date())):
            cur -= pd.Timedelta(days=1)  # vandaag nog niets: kijk of de reeks t/m gisteren loopt
        while _geoefend(str(cur.date())):
            streak += 1
            cur -= pd.Timedelta(days=1)
    except Exception:
        pass
    return streak

def bouw_dagblok(alle_data, verwar_stats, cfg):
    """Bouwt het woord-dagblok: knelpunten + due/nieuwe woorden (oplopend flashcard→MC→typen),
    plus de verwarparen die als paar-oefening áchter de woorden komen."""
    knel = []
    for w in alle_data:
        if not isinstance(w, dict):
            continue
        g = int(w.get('score_goed', 0)); f = int(w.get('score_fout', 0)); s = int(w.get('streak', 0))
        if f > 0 or (g > 0 and s <= 3):
            knel.append(w)
    knel.sort(key=lambda w: int(w.get('score_fout', 0)), reverse=True)
    knel = knel[:max(0, cfg.get('knelpunt', 0))]
    sampled = kies_gefaseerde_oefensessie(alle_data, module='vocab', totale_db=alle_data)
    knel_ids = {id(k) for k in knel}
    woorden = [w for w in sampled if id(w) not in knel_ids][:max(0, cfg.get('woorden', 0))]
    combined = woorden + knel
    kaarten = leerpad_kaart_volgorde(combined)
    paren = bouw_verwar_paren(alle_data, verwar_stats)[:max(0, cfg.get('verwar', 0))]
    return kaarten, paren

def _scaffold_kaarten(sampled):
    """Zet gesamplede items om in (item, sub_modus)-kaarten: nieuw → Leer+MC, training → MC, sterk → Typen."""
    kaarten = []
    for v in sampled:
        _s = int(v.get('streak', 0))
        if _s <= 0:
            kaarten.append((v, "Leer")); kaarten.append((v, "MC"))
        elif _s < LEERPAD_TYP_STREAK:
            kaarten.append((v, "MC"))
        else:
            kaarten.append((v, "Typen"))
    return kaarten

def dagblok_arm_stam():
    """Zet het stamtijden-Leerpad (huidige level) klaar zodat het meteen speelt bij openen van het tabblad."""
    db = laad_stamtijden_db()
    if not db:
        return
    levels = stam_level_status(bouw_stam_levels(db), st.session_state.stam_stats)
    ontgr = [l for l in levels if l['ontgrendeld']]
    if not ontgr:
        return
    cur = next((l for l in levels if l['ontgrendeld'] and not l['voltooid']), ontgr[-1])
    w = cur['verb']
    doel = []
    for t in _STAM_TIJDEN:
        vorm = w.get('stamtijden', {}).get(t)
        if not _stam_vorm_ok(vorm):
            continue
        vid = f"{w['praesens']}_{vorm}"
        s = st.session_state.stam_stats.get(vid, {'g': 0, 'f': 0, 'streak': 0})
        doel.append({"basis": w, "vraag_vorm": {"tijd_diathese": t, "vorm": vorm},
                     "score_goed": s.get('g', 0), "score_fout": s.get('f', 0), "streak": s.get('streak', 0), "vid": vid})
    if not doel:
        return
    st.session_state.gestrafte_woorden_stam = set()
    st.session_state.stam_sessie_lijst = _scaffold_kaarten(kies_gefaseerde_oefensessie(doel, 'stam'))
    laad_volgend_stam_woord()

def dagblok_arm_struct():
    """Zet het structuurwoorden-Leerpad (huidige level) klaar zodat het meteen speelt bij openen."""
    db = laad_structuurwoorden_db()
    if not db:
        return
    levels = struct_level_status(bouw_struct_levels(db), st.session_state.struct_stats)
    ontgr = [l for l in levels if l['ontgrendeld']]
    if not ontgr:
        return
    cur = next((l for l in levels if l['ontgrendeld'] and not l['voltooid']), ontgr[-1])
    doel = []
    for idx, w in cur['items']:
        vid = f"{w['grieks']}_{idx}"
        s = st.session_state.struct_stats.get(vid) or st.session_state.struct_stats.get(w['grieks']) or {'g': 0, 'f': 0, 'streak': 0}
        w2 = dict(w); w2['vid'] = vid; w2['streak'] = s.get('streak', 0); w2['score_goed'] = s.get('g', 0); w2['score_fout'] = s.get('f', 0)
        doel.append(w2)
    if not doel:
        return
    st.session_state.gestrafte_woorden_struct = set()
    st.session_state.struct_sessie_lijst = _scaffold_kaarten(kies_gefaseerde_oefensessie(doel, module='struct'))
    laad_volgend_struct_woord()

def dagkalender_html(dag_stats, log):
    """5-weekse heatmap-kalender: kleurintensiteit = hoeveel je die dag oefende, plus een gekleurd
    stipje per onderdeel waarvan je die dag het DAGDOEL hebt gehaald."""
    try:
        v = pd.Timestamp(_nu().date())
    except Exception:
        return ""
    start = v - pd.Timedelta(days=int(v.weekday()) + 28)  # maandag, 4 weken terug
    # (log-sleutel, kleur, naam) — 'woorden_uniek' = aantal verschillende woorden die dag.
    onderdelen = [("woorden_uniek", "#33ccff", "woorden"), ("actief", "#f6c23e", "actief"),
                  ("stam", "#b07be0", "stamtijden"), ("struct", "#f6923c", "structuur"),
                  ("verzen", "#3fb27f", "verzen"), ("klank", "#20c997", "klankwetten")]
    _doelen = dagdoel_config()
    dag_stats = dag_stats or {}
    log = log if isinstance(log, dict) else {}
    def _bg(n):
        if n <= 0: return "#2a2f36"
        if n < 5: return "#16432c"
        if n < 15: return "#1f7a4d"
        if n < 30: return "#2aa866"
        return "#39d17f"
    kop = "".join(f"<div style='text-align:center;font-size:11px;color:#8a93a0'>{d}</div>"
                  for d in ["ma", "di", "wo", "do", "vr", "za", "zo"])
    cellen = ""
    for i in range(35):
        ts = start + pd.Timedelta(days=i)
        key = str(ts.date())
        n = int(dag_stats.get(key, 0))
        lg = log.get(key, {}) if isinstance(log.get(key, {}), dict) else {}
        toekomst = ts.date() > v.date()
        rand = "2px solid #f6c23e" if key == str(v.date()) else "1px solid rgba(255,255,255,.06)"
        stip = ""
        for sl, kl, _naam in onderdelen:
            _val = lg.get(sl)
            _doel = int(_doelen.get('woorden' if sl == 'woorden_uniek' else sl, 0) or 0)
            if sl == "woorden_uniek" and _val is None and lg.get("woordblok") is True:
                _gehaald = True          # oude data: de vlag van het afgeronde dagblok telt nog mee
            elif isinstance(_val, (int, float)):
                _gehaald = _doel > 0 and _val >= _doel
            else:
                _gehaald = _val is True
            if _gehaald:
                stip += f"<span style='display:inline-block;width:11px;height:11px;border-radius:50%;background:{kl};margin:0 2px'></span>"
        bg = "#1a1d22" if toekomst else _bg(n)
        # aantal geoefende items groot in het midden; datum klein in de hoek; stipjes onderaan
        aantal = (f"<div style='font-size:20px;font-weight:800;color:#ffffff;line-height:1;text-align:center'>{n}</div>"
                  if (n > 0 and not toekomst)
                  else "<div style='font-size:20px;line-height:1;color:#4b525c'>·</div>")
        cellen += (f"<div style='background:{bg};border:{rand};border-radius:8px;height:66px;padding:4px;position:relative;"
                   f"display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;opacity:{'0.35' if toekomst else '1'}'>"
                   f"<div style='position:absolute;top:3px;left:5px;font-size:10px;font-weight:600;color:#aeb6c0;line-height:1'>{ts.day}</div>"
                   f"{aantal}"
                   f"<div style='text-align:center;min-height:11px'>{stip}</div></div>")
    legenda = " &nbsp; ".join(f"<span style='color:{kl}'>●</span> {naam}" for _sl, kl, naam in onderdelen)
    return (f"<div style='display:grid;grid-template-columns:repeat(7,1fr);gap:4px;margin-bottom:6px'>{kop}</div>"
            f"<div style='display:grid;grid-template-columns:repeat(7,1fr);gap:4px'>{cellen}</div>"
            f"<div style='font-size:11px;color:#9aa3af;margin-top:8px'>Groot getal = aantal geoefende items die dag · "
            f"fellere groen = meer · een stip = <b>dagdoel gehaald</b> voor: {legenda}</div>")

# --- LEERPAD voor STAMTIJDEN (elk werkwoord = één level) ---
_STAM_TIJDEN = ["Futurum Actief/Medium", "Aoristus Actief/Medium", "Aoristus Passief", "Perfectum Actief", "Perfectum Medium/Passief"]

def _stam_vorm_ok(v):
    """True als een stamtijd-vorm écht bestaat. Niet elk werkwoord heeft elke stamtijd
    (bv. ἔρχομαι heeft geen aoristus passief / perfectum medium); die staan in de data als
    leeg, '-', '---' of 'n.v.t.' en moeten NIET geoefend worden."""
    s = str(v or "").strip()
    if not s or s in ("n.v.t.", "-", "--", "---"):
        return False
    return any(ch.isalpha() for ch in s)  # alleen streepjes/gedachtestreepjes = geen echte vorm

def bereken_xp_stam(stam_stats):
    """XP voor de stamtijden-rang, puur opbouwend uit stam_stats."""
    xp = 0
    for _vid, s in (stam_stats or {}).items():
        xp += int(s.get('g', 0)) * 8
        strk = int(s.get('streak', 0))
        if strk >= 5: xp += 8
        if strk >= 16: xp += 20
    return xp

def _stam_vormen(w):
    return [v for v in (w.get('stamtijden', {}).get(t) for t in _STAM_TIJDEN) if _stam_vorm_ok(v)]

def bouw_stam_levels(stamtijden_db):
    """Elk werkwoord = één level (al zijn stamtijden), in les-volgorde, frequentst eerst."""
    ww = [w for w in stamtijden_db if isinstance(w, dict) and w.get('praesens')]
    ww.sort(key=lambda w: (w.get('les', 0) or 0, -int(w.get('frequentie', 0)), w.get('praesens', '')))
    return [{"index": i + 1, "titel": f"Les {w.get('les', '?')} · {w['praesens']}", "verb": w} for i, w in enumerate(ww)]

def stam_level_status(levels, stam_stats, drempel=5):
    """Per werkwoord-level: hoeveel vormen 'af' (streak≥drempel), voltooid, ontgrendeld."""
    status = []
    vorige = True
    for lv in levels:
        w = lv["verb"]
        vormen = _stam_vormen(w)
        totaal = len(vormen)
        klaar = sum(1 for v in vormen if int(stam_stats.get(f"{w['praesens']}_{v}", {}).get('streak', 0)) >= drempel)
        voltooid = totaal > 0 and klaar == totaal
        status.append({**lv, "klaar": klaar, "totaal": totaal, "voltooid": voltooid, "ontgrendeld": vorige})
        vorige = voltooid
    return status

def stam_herhaalvormen(stamtijden_db, stam_stats, huidige_praesens, aantal):
    """Kies 'aantal' al-geoefende stamtijd-vormen van ANDERE werkwoorden (laagste streak eerst),
    zodat een Leerpad-sessie af en toe oude stof ophaalt."""
    if aantal <= 0:
        return []
    kand = []
    for w in stamtijden_db:
        if w.get('praesens') == huidige_praesens:
            continue
        for t in _STAM_TIJDEN:
            v = w.get('stamtijden', {}).get(t)
            if not _stam_vorm_ok(v):
                continue
            vid = f"{w['praesens']}_{v}"
            s = stam_stats.get(vid)
            if s and (int(s.get('g', 0)) > 0 or int(s.get('f', 0)) > 0 or int(s.get('streak', 0)) > 0):
                kand.append({"basis": w, "vraag_vorm": {"tijd_diathese": t, "vorm": v},
                             "score_goed": s.get('g', 0), "score_fout": s.get('f', 0),
                             "streak": s.get('streak', 0), "vid": vid})
    kand.sort(key=lambda x: int(x["streak"]))
    return kand[:aantal]

# --- LEERPAD voor STRUCTUURWOORDEN (chunks, per categorie gegroepeerd) ---
def bereken_xp_struct(struct_stats):
    """XP voor de structuurwoorden-rang (benaderend, puur opbouwend)."""
    xp = 0
    for _k, s in (struct_stats or {}).items():
        if not isinstance(s, dict):
            continue
        xp += int(s.get('g', 0)) * 8
        strk = int(s.get('streak', 0))
        if strk >= 5: xp += 8
        if strk >= 16: xp += 20
    return xp

def _struct_streak(struct_stats, grieks, idx):
    s = struct_stats.get(f"{grieks}_{idx}") or struct_stats.get(grieks) or {}
    return int(s.get('streak', 0)) if isinstance(s, dict) else 0

def bouw_struct_levels(struct_db, chunk=6):
    """Deelt de structuurwoorden op in kleine levels (in DB-volgorde, per categorie gegroepeerd)."""
    geordend = sorted(list(enumerate(struct_db)), key=lambda p: (str(p[1].get('categorie', '')), p[0]))
    levels = []
    for n, start in enumerate(range(0, len(geordend), chunk)):
        brok = geordend[start:start + chunk]
        cats = [w.get('categorie', '') for _i, w in brok]
        lab = max(set(cats), key=cats.count) if cats else "Structuurwoorden"
        levels.append({"index": n + 1, "titel": lab, "items": brok})
    return levels

def struct_level_status(levels, struct_stats, drempel=5):
    """Per level: hoeveel woorden 'af' (streak≥drempel), voltooid, ontgrendeld."""
    status = []
    vorige = True
    for lv in levels:
        totaal = len(lv["items"])
        klaar = sum(1 for idx, w in lv["items"] if _struct_streak(struct_stats, w['grieks'], idx) >= drempel)
        voltooid = totaal > 0 and klaar == totaal
        status.append({**lv, "klaar": klaar, "totaal": totaal, "voltooid": voltooid, "ontgrendeld": vorige})
        vorige = voltooid
    return status

# --- LEERPAD voor ACTIEF BEHEERSEN (elk paradigma/rijtje = één level) ---
def bouw_actief_levels(actief_db):
    """Elk paradigma (rijtje) = één level, in vaste volgorde over niveaus → categorieën → rijtjes."""
    levels = []
    idx = 0
    for niv in actief_db.keys():
        for cat in actief_db[niv].keys():
            for sub in actief_db[niv][cat].keys():
                cellen = actief_db[niv][cat][sub]
                ids = [c.get('id') for c in cellen if isinstance(c, dict) and c.get('id')]
                idx += 1
                levels.append({"index": idx, "niveau": niv, "categorie": cat, "sub": sub,
                               "titel": f"{niv} · {sub}", "ids": ids})
    return levels

ACTIEF_BEHEERST = 16   # streak waarop een cel als 'beheerst' geldt (één bron van waarheid)

def migreer_actief_ids(actief_db, stats):
    """Verhuist bestaande voortgang naar de nieuwe, unieke cel-ids.

    Vroeger viel een Griekse paradigmanaam ('-η (κώμη)') uit het id weg, waardoor κώμη, θύρα en
    ἄκανθα exact dezelfde cel-ids deelden en hun streaks door elkaar liepen. Elke cel heeft nu een
    eigen id; het vorige id staat in de database als 'oud_id'.

    Waar één oud id door meerdere paradigma's werd gedeeld, gaat de voortgang naar het EERSTE
    paradigma. De andere beginnen bewust op nul: die heb je nooit apart geoefend, en juist daarom
    wil je ze nu wél los kunnen oefenen."""
    if not isinstance(stats, dict) or stats.get('_ids_v2'):
        return 0
    doel = {}   # oud_id -> eerste nieuwe id (in databasevolgorde)
    for _cats in (actief_db or {}).values():
        for _paras in _cats.values():
            for _cellen in _paras.values():
                for _c in _cellen:
                    _oud = _c.get('oud_id')
                    if _oud and _oud not in doel:
                        doel[_oud] = _c.get('id')
    verhuisd = 0
    for oud, nieuw in doel.items():
        if oud in stats and nieuw and nieuw not in stats:
            stats[nieuw] = stats[oud]
            verhuisd += 1
    for oud in doel:
        stats.pop(oud, None)
    stats['_ids_v2'] = True
    return verhuisd

def actief_level_status(levels, actief_stats, drempel=ACTIEF_BEHEERST):
    status = []
    vorige = True
    for lv in levels:
        totaal = len(lv["ids"])
        klaar = sum(1 for i in lv["ids"] if int((actief_stats.get(i) or {}).get('streak', 0)) >= drempel)
        voltooid = totaal > 0 and klaar == totaal
        status.append({**lv, "klaar": klaar, "totaal": totaal, "voltooid": voltooid, "ontgrendeld": vorige})
        vorige = voltooid
    return status

def bereken_xp_actief(actief_stats):
    xp = 0
    for _i, s in (actief_stats or {}).items():
        if isinstance(s, dict):
            xp += int(s.get('g', 0)) * 5
            if int(s.get('streak', 0)) >= 16:
                xp += 15
    return xp

# --- COMPETITIE: samenvatting per gebruiker (voor het Scorebord-tabblad) ---
def _streak_uit_entry(v):
    """Streak uit een stats-entry; ondersteunt zowel 'streak' als de oude m1-m4-telling."""
    if 'm4' in v or 'm1' in v:
        return int(v.get('m2', 0)) * 1 + int(v.get('m3', 0)) * 2 + int(v.get('m4', 0)) * 4
    return int(v.get('streak', 0))

def _beheerst_telling(d, drempel=16):
    """(pogingen, beheerst) uit een g/f/streak-dict."""
    pog = beh = 0
    for _k, v in (d or {}).items():
        if not isinstance(v, dict):
            continue
        pog += int(v.get('g', 0)) + int(v.get('f', 0))
        if _streak_uit_entry(v) >= drempel:
            beh += 1
    return pog, beh

def _struct_stat_lookup(struct_stats, w, idx):
    """Structuurwoord-stat ophalen met dezelfde sleutel als bij het opslaan (`grieks_index`),
    met terugval op de kale grieks-sleutel voor oude data. Zonder deze terugval lazen de
    voortgang- en aartsrivalen-overzichten op de verkeerde sleutel en bleef alles op 0 staan."""
    g = w.get('grieks', '')
    ss = struct_stats or {}
    return ss.get(f"{g}_{idx}") or ss.get(g) or {'g': 0, 'f': 0, 'streak': 0}

@st.cache_data(show_spinner=False)
def voortgang_kernstats(cache_key, _data, _stam_stats, _stamtijden_db, _struct_stats, _struct_db):
    """Zware fase-tellingen voor het Voortgang-dashboard, gecached. Het Voortgang-tabblad draait
    (net als alle tabs) bij ELKE rerun; zonder cache telde dit de hele database opnieuw bij elk
    antwoord in een ander tabblad. De onderstreepte params worden NIET gehasht (Streamlit-conventie);
    alleen `cache_key` (gebruiker + handmatige versie) stuurt de herberekening. De versie wijzigt
    uitsluitend als de student op 'Ververs' drukt → tijdens het oefenen wordt er nooit herberekend."""
    sv = {'Nieuw': 0, 'In Training': 0, 'Beheerst': 0, 'Mastery': 0}
    tgv = tfv = bekende_freq = totale_freq = 0
    vocab_streaks = {}
    for w in (_data or []):
        g = w.get('grieks', ''); strk = int(w.get('streak', 0)); vocab_streaks[g] = strk
        freq = int(w.get('frequentie', w.get('frequentie_nt', 1))); totale_freq += freq
        tgv += int(w.get('score_goed', 0)); tfv += int(w.get('score_fout', 0))
        if strk >= 30: sv['Mastery'] += 1; bekende_freq += freq
        elif strk >= 16: sv['Beheerst'] += 1; bekende_freq += freq
        elif strk >= 1: sv['In Training'] += 1
        else: sv['Nieuw'] += 1
    ss = {'Nieuw': 0, 'In Training': 0, 'Beheerst': 0, 'Mastery': 0}; tgs = tfs = 0
    for w in (_stamtijden_db or []):
        for t_d, vorm in w.get('stamtijden', {}).items():
            s = (_stam_stats or {}).get(f"{w['praesens']}_{vorm}", {'g': 0, 'f': 0, 'streak': 0})
            tgs += s.get('g', 0); tfs += s.get('f', 0); k = s.get('streak', 0)
            if k >= 30: ss['Mastery'] += 1
            elif k >= 16: ss['Beheerst'] += 1
            elif k >= 1: ss['In Training'] += 1
            else: ss['Nieuw'] += 1
    sr = {'Nieuw': 0, 'In Training': 0, 'Beheerst': 0, 'Mastery': 0}; tgr = tfr = 0
    for idx_w, w in enumerate(_struct_db or []):
        s = _struct_stat_lookup(_struct_stats, w, idx_w)
        tgr += s.get('g', 0); tfr += s.get('f', 0); k = s.get('streak', 0)
        if k >= 30: sr['Mastery'] += 1
        elif k >= 16: sr['Beheerst'] += 1
        elif k >= 1: sr['In Training'] += 1
        else: sr['Nieuw'] += 1
    return {'stats_vocab': sv, 'tot_goed_v': tgv, 'tot_fout_v': tfv, 'vocab_streaks': vocab_streaks,
            'bekende_freq': bekende_freq, 'totale_freq': totale_freq,
            'stats_stam': ss, 'tot_goed_s': tgs, 'tot_fout_s': tfs,
            'stats_str': sr, 'tot_goed_st': tgr, 'tot_fout_st': tfr}

def _actief_noteer(cid, goed):
    """Werk actief_stats bij voor één paradigma-cel. Gebruikt door ALLE Actief-modi (focus,
    tentamenrooster, flashcards), zodat oefening buiten het Leerpad ook meetelt en wordt bewaard."""
    if not cid:
        return
    if not isinstance(st.session_state.get('actief_stats'), dict):
        st.session_state.actief_stats = {}
    rec = st.session_state.actief_stats.setdefault(cid, {'g': 0, 'f': 0, 'streak': 0})
    if goed:
        rec['g'] = int(rec.get('g', 0)) + 1
        rec['streak'] = int(rec.get('streak', 0)) + 1
    else:
        rec['f'] = int(rec.get('f', 0)) + 1
        rec['streak'] = max(0, int(rec.get('streak', 0)) - 1)

def _kolom_index(idx, totaal):
    """Kolom-major indeling voor paradigma-roosters: eerste helft (ev-rijtje) links, tweede helft
    (mv-rijtje) rechts, elk in standaardvolgorde (Nom, Gen, Dat, Acc). Zo loopt tabben netjes
    Nom ev → Gen ev → Dat ev → Acc ev in de linkerkolom, daarna het mv-rijtje rechts."""
    helft = (int(totaal) + 1) // 2
    return 0 if idx < helft else 1

def markeer_actief_paradigma(cellen):
    """Zet de cellen van een paradigma op 'beheerst' (streak ≥16) na een foutloos rooster.
    Telt zelf géén 'g' op — dat gebeurt al per opgeloste cel via _actief_noteer, anders zou
    het volledige rooster dubbel tellen."""
    ast = st.session_state.get('actief_stats')
    if not isinstance(ast, dict):
        ast = {}; st.session_state.actief_stats = ast
    for c in cellen:
        cid = c.get('id')
        if not cid:
            continue
        rec = ast.setdefault(cid, {'g': 0, 'f': 0, 'streak': 0})
        rec['streak'] = max(int(rec.get('streak', 0)), ACTIEF_BEHEERST)

# --- DATABASE FUNCTIES ---
@st.cache_data
def laad_actief_beheersen_db():
    if os.path.exists("actief_beheersen.json"):
        with open("actief_beheersen.json", "r", encoding="utf-8") as f: return json.load(f)
    return None
    
@st.cache_data
def laad_vocab_db():
    bestand = "basis_woorden_verrijkt.json" if os.path.exists("basis_woorden_verrijkt.json") else "basis_woorden.json"
    if os.path.exists(bestand):
        with open(bestand, "r", encoding="utf-8") as f: return json.load(f)
    return []
    
@st.cache_data
def laad_actief_db():
    try:
        with open("actief_beheersen.json", "r", encoding="utf-8") as f: return json.load(f)
    except FileNotFoundError: return None
        
@st.cache_data
def laad_stamtijden_db():
    if os.path.exists("stamtijden.json"):
        with open("stamtijden.json", "r", encoding="utf-8") as f: return json.load(f)
    return None

@st.cache_data(show_spinner=False)
def stamtijd_vormen_set():
    """Alle (genormaliseerde) stamtijd-vormen uit de database — voor het inkleuren van stamtijden."""
    s = set()
    for w in (laad_stamtijden_db() or []):
        for _td, vorm in (w.get('stamtijden') or {}).items():
            if _stam_vorm_ok(vorm):
                s.add(normaliseer_accent(vorm))
    return s

def ontleed_kleur_stijl(info, grieks, kleur_nv, kleur_vw, kleur_st, stamset):
    """CSS-stijl voor het inkleuren van een woord (naamval/voegwoord/stamtijd), of None. Wordt
    NIET op het doelwoord toegepast — dat regelt de aanroeper, zodat de kleur het antwoord niet
    verraadt."""
    info = info or ""
    if kleur_nv:
        nv = _ontleed_deel_correct('naamval', info)
        if nv in _ONTLEED_KLEUR:
            return f"color:{_ONTLEED_KLEUR[nv]};font-weight:600"
    if kleur_vw and ("Voegwoord" in info or "Voegw" in info):
        return "background:#ffd700;color:#000;padding:0 3px;border-radius:4px"
    if kleur_st and stamset and normaliseer_accent(grieks) in stamset:
        return "color:#d63384;font-weight:600"
    return None

@st.cache_data
def laad_structuurwoorden_db():
    if os.path.exists("structuurwoorden.json"):
        with open("structuurwoorden.json", "r", encoding="utf-8") as f: return json.load(f)
    return None

@st.cache_data
def laad_verwarparen_db():
    """Laadt de map grieks_woord -> lijst van look-alike twins (op gelijkenis gesorteerd)."""
    if os.path.exists("verwarparen.json"):
        with open("verwarparen.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("twins", {})
    return {}

@st.cache_data
def laad_grammatica_db():
    if os.path.exists("grammatica_index.json"):
        with open("grammatica_index.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return None

@st.cache_data
def laad_contractie_db():
    if os.path.exists("contractie_data.json"):
        with open("contractie_data.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return None

GRAMMATICA_PDF = "grammatica_overzicht.pdf"

@st.cache_resource
def open_grammatica_pdf():
    if FITZ_BESCHIKBAAR and os.path.exists(GRAMMATICA_PDF):
        try:
            return fitz.open(GRAMMATICA_PDF)
        except Exception:
            return None
    return None

@st.cache_data(show_spinner=False)
def render_slide(paginanummer, dpi=120):
    doc = open_grammatica_pdf()
    if doc is None:
        return None
    idx = paginanummer - 1
    if idx < 0 or idx >= doc.page_count:
        return None
    try:
        return doc[idx].get_pixmap(dpi=dpi).tobytes("png")
    except Exception:
        return None

# cache_resource i.p.v. cache_data: de db wordt alleen gelezen, en cache_data zou de
# 19,5 MB bij elke aanroep opnieuw unpicklen (~0,13 s x 6 aanroepen per rerun).
@st.cache_resource
def laad_bijbel_db():
    bijbel = {}
    if os.path.exists("bijbel_nt.json"):
        with open("bijbel_nt.json", "r", encoding="utf-8") as f: bijbel = json.load(f)
    else:
        if os.path.exists("bijbel_nt_deel1.json"):
            with open("bijbel_nt_deel1.json", "r", encoding="utf-8") as f: bijbel.update(json.load(f))
        if os.path.exists("bijbel_nt_deel2.json"):
            with open("bijbel_nt_deel2.json", "r", encoding="utf-8") as f: bijbel.update(json.load(f))
    return bijbel

def laad_gebruiker_data(naam):
    try:
        bestand = "basis_woorden_verrijkt.json" if os.path.exists("basis_woorden_verrijkt.json") else "basis_woorden.json"
        if not os.path.exists(bestand): return None
        with open(bestand, "r", encoding="utf-8") as f: basis = json.load(f)

        ws = _ws_naam(naam)
        row = None
        migreren = False
        # 1) Eigen tabblad (per gebruiker → geen kruis-overschrijving).
        try:
            dfu = conn.read(worksheet=ws, ttl=0)
            if dfu is not None and not getattr(dfu, 'empty', True):
                if 'gebruikersnaam' in dfu.columns:
                    _r = dfu[dfu['gebruikersnaam'] == naam]
                    if _r.empty:
                        # Verdraagzame vergelijking: dit tabblad is al van jou alleen (u_<naam>),
                        # dus kleine verschillen in hoofdletters of spaties mogen niet betekenen
                        # dat je niet meer bij je eigen voortgang kunt. Een écht andere naam wél.
                        _doel = str(naam).strip().lower()
                        _r = dfu[dfu['gebruikersnaam'].astype(str).str.strip().str.lower() == _doel]
                    row = _r.iloc[0] if not _r.empty else None
                else:
                    row = dfu.iloc[0]
            _eigen_read_ok = True
        except Exception:
            # Hier weten we nog NIET of het tabblad simpelweg niet bestaat (normaal bij een nieuwe
            # gebruiker) of dat de verbinding hapert. Dat verschil is cruciaal: bij een leesfout
            # doorgaan als 'nieuwe gebruiker' zou je bestaande voortgang met leegte overschrijven.
            # We stellen de beslissing uit tot na de leesactie hieronder, die als test dient.
            row = None
            _eigen_read_ok = False

        # 2) Terugval: oud gedeeld werkblad. Deze leesactie is tegelijk de proef of de verbinding
        #    het überhaupt doet. Lukt die wél, dan bestond je eigen tabblad gewoon nog niet.
        if row is None:
            try:
                df = conn.read(ttl=0)
            except Exception:
                if not _eigen_read_ok:
                    # Beide leesacties mislukt → het is de verbinding, niet een ontbrekend tabblad.
                    st.session_state.laad_fout = ("De verbinding met de cloud lukte even niet. Je voortgang is "
                                                  "NIET gewijzigd — wacht een halve minuut en log opnieuw in.")
                    return None
                df = None
            if df is not None and 'gebruikersnaam' in getattr(df, 'columns', []):
                _r = df[df['gebruikersnaam'] == naam]
                if not _r.empty:
                    row = _r.iloc[0]; migreren = True

        if row is None:
            # Nieuwe gebruiker: alleen in het geheugen initialiseren; de eigen tab ontstaat bij de
            # eerste echte opslag. Zo kan een tijdelijke leesfout nooit je voortgang overschrijven.
            st.session_state.vocab_stats = {}; st.session_state.gram_stats = {}; st.session_state.stam_stats = {}; st.session_state.struct_stats = {}; st.session_state.dag_stats = {}; st.session_state.prod_stats = {}
            st.session_state.verwar_stats = {}; st.session_state.ui_prefs = {}; st.session_state.badges = {}; st.session_state.dagdoel = {}; st.session_state.actief_stats = {}; st.session_state.ontleed_stats = {}; st.session_state.klank_stats = {}
        else:
            def reassemble_chunks(prefix, count_col):
                """Zet de in stukken opgeslagen JSON weer in elkaar.

                Een leeg resultaat is een geldige uitkomst: categorieën waarin je nog niets hebt
                gedaan staan als '{}' opgeslagen, en lege cellen komen als NaN terug. Alleen als er
                écht inhoud staat die niet te lezen is, breken we af (dan zou doorgaan met een lege
                staat je voortgang bij de eerstvolgende opslag overschrijven)."""
                if count_col not in row or pd.isna(row[count_col]):
                    return veilige_json_load(row.get(prefix, '{}'))
                try:
                    count = int(float(row[count_col]))   # cel kan als '3.0' terugkomen
                except (TypeError, ValueError):
                    count = 0
                delen = []
                for i in range(count):
                    kol = f"{prefix}_{i}"
                    if kol not in row:
                        continue
                    cel = row[kol]
                    try:
                        if cel is None or pd.isna(cel):
                            continue
                    except (TypeError, ValueError):
                        pass
                    tekst = str(cel)
                    if tekst.strip().lower() == 'nan':
                        continue
                    delen.append(tekst)
                s = "".join(delen).strip()
                if len(s) <= 2:
                    return {}            # leeg, '{}' of '[]' → gewoon nog niets gedaan
                uit = veilige_json_load(s)
                if not uit:
                    raise ValueError(f"kon {prefix} niet ontcijferen ({len(s)} tekens)")
                return uit

            st.session_state.vocab_stats = reassemble_chunks('vocab_stats', 'v_chunks')
            st.session_state.gram_stats = reassemble_chunks('gram_stats', 'g_chunks')
            st.session_state.prod_stats = reassemble_chunks('prod_stats', 'pr_chunks')
            st.session_state.stam_stats = reassemble_chunks('stam_stats', 'st_chunks')
            st.session_state.struct_stats = reassemble_chunks('struct_stats', 'sr_chunks')
            st.session_state.dag_stats = reassemble_chunks('dag_stats', 'd_chunks')
            st.session_state.verwar_stats = reassemble_chunks('verwar_stats', 'vw_chunks')
            st.session_state.ui_prefs = reassemble_chunks('ui_prefs', 'ui_chunks')
            st.session_state.badges = reassemble_chunks('badges', 'bd_chunks')
            st.session_state.dagdoel = reassemble_chunks('dagdoel', 'dd_chunks')
            st.session_state.actief_stats = reassemble_chunks('actief_stats', 'af_chunks')
            st.session_state.ontleed_stats = reassemble_chunks('ontleed_stats', 'on_chunks')
            st.session_state.klank_stats = reassemble_chunks('klank_stats', 'kl_chunks')

        # Eenmalige verhuizing naar de nieuwe, unieke cel-ids van Actief Beheersen.
        try:
            migreer_actief_ids(laad_actief_db(), st.session_state.actief_stats)
        except Exception:
            pass   # nooit het inloggen laten stranden op een migratie

        for r in basis:
            stats = st.session_state.vocab_stats.get(r['grieks'], {})
            if 'm4' in stats or 'm1' in stats:
                m1 = stats.get('m1', 0); m2 = stats.get('m2', 0); m3 = stats.get('m3', 0); m4 = stats.get('m4', 0)
                r['streak'] = (m1 * 0) + (m2 * 1) + (m3 * 2) + (m4 * 4)
            else: r['streak'] = stats.get('streak', 0)
            
            r['score_goed'] = stats.get('g', 0)
            r['score_fout'] = stats.get('f', 0)
            r['laatst_geoefend'] = stats.get('laatst_geoefend', "")
            r['laatst_fout'] = stats.get('lf', "")
            if 'lexeem_info' not in r or not r['lexeem_info']: r['lexeem_info'] = r.get('grieks_info', '')
        st.session_state.laad_fout = None  # succesvol geladen
        # Migratie: stond je data nog in het oude gedeelde werkblad, zet 'm nu over naar je eigen tab.
        if migreren:
            st.session_state.last_user = naam
            try: opslaan_naar_cloud()
            except Exception: pass
        return basis
    except Exception as _e:
        # Niet stil None teruggeven: onthoud dat het laden misging, zodat de login-UI het meldt
        # (en de gebruiker weet dat zijn voortgang NIET is aangeraakt).
        st.session_state.laad_fout = str(_e)
        return None

def _ws_naam(naam):
    """Werkbladnaam (tab) voor één gebruiker. Elke student z'n eigen tab → een opslag van de één
    kan die van een ander nooit overschrijven."""
    schoon = re.sub(r'[^0-9A-Za-z_]', '_', str(naam or ''))
    return ("u_" + schoon)[:95]

def _bouw_rij_dict():
    """Zet alle voortgang uit het geheugen om in één (gechunkte) rij, klaar voor de Sheet."""
    def get_chunks(data_dict, prefix, max_len=40000):
        s = json.dumps(data_dict, ensure_ascii=False)
        chunks = [s[i:i+max_len] for i in range(0, len(s), max_len)]
        return {f"{prefix}_{i}": c for i, c in enumerate(chunks)}, len(chunks)
    specs = [('vocab_stats', 'v_chunks'), ('gram_stats', 'g_chunks'), ('prod_stats', 'pr_chunks'),
             ('stam_stats', 'st_chunks'), ('struct_stats', 'sr_chunks'), ('dag_stats', 'd_chunks'),
             ('verwar_stats', 'vw_chunks'), ('ui_prefs', 'ui_chunks'), ('badges', 'bd_chunks'),
             ('dagdoel', 'dd_chunks'), ('actief_stats', 'af_chunks'), ('ontleed_stats', 'on_chunks'),
             ('klank_stats', 'kl_chunks')]
    rij = {'gebruikersnaam': st.session_state.last_user}
    for dictkey, countcol in specs:
        ch, n = get_chunks(st.session_state.get(dictkey, {}) or {}, dictkey)
        rij.update(ch); rij[countcol] = n
    return rij

def _opslaan_legacy(rij):
    """Laatste terugval: schrijf naar het oude gedeelde 'Woordenlijst'-werkblad (huidige methode)."""
    df = conn.read(ttl=10)
    if 'gebruikersnaam' not in df.columns: df['gebruikersnaam'] = ""
    df_andere = df[df['gebruikersnaam'] != st.session_state.last_user]
    conn.update(data=pd.concat([df_andere, pd.DataFrame([rij])], ignore_index=True))

def _eigen_samenvatting():
    """Bondige samenvatting van de eigen voortgang voor het gedeelde Scorebord-tabblad."""
    data = st.session_state.get('data') or []
    stam = st.session_state.get('stam_stats', {}) or {}
    struct = st.session_state.get('struct_stats', {}) or {}
    actief = st.session_state.get('actief_stats', {}) or {}
    xp = bereken_xp(data) + bereken_xp_stam(stam) + bereken_xp_struct(struct) + bereken_xp_actief(actief)
    niv = niveau_van_xp(xp)
    w_beh = sum(1 for w in data if int(w.get('streak', 0)) >= 16)
    w_pog = sum(int(w.get('score_goed', 0)) + int(w.get('score_fout', 0)) for w in data)
    s_pog, s_beh = _beheerst_telling(stam); r_pog, r_beh = _beheerst_telling(struct); a_pog, a_beh = _beheerst_telling(actief)
    dag = st.session_state.get('dag_stats') or {}
    week = tot = 0
    try:
        vandaag = _nu().date(); wk = vandaag - pd.Timedelta(days=6)
    except Exception:
        vandaag = None; wk = None
    for ds, n in dag.items():
        try:
            n = int(n); tot += n
            if vandaag is not None:
                d = datetime.strptime(str(ds), '%Y-%m-%d').date()
                if wk <= d <= vandaag: week += n
        except Exception:
            pass
    badges = len([k for k in (st.session_state.get('badges') or {}) if not str(k).startswith('_')])
    return {'gebruiker': str(st.session_state.last_user).split('_')[0], 'xp': xp,
            'niveau': niv['niveau'], 'titel': niv['titel'], 'week': week, 'totaal': tot, 'badges': badges,
            'w_beh': w_beh, 'w_pog': w_pog, 'a_beh': a_beh, 'a_pog': a_pog,
            's_beh': s_beh, 's_pog': s_pog, 'r_beh': r_beh, 'r_pog': r_pog}

def _update_scorebord():
    """Werk het gedeelde 'Scorebord'-tabblad bij met alleen de eigen samenvatting (voor de competitie).
    Bevat geen echte voortgangsdata; een botsing hier kost hooguit een verouderd ranglijst-getal."""
    sm = _eigen_samenvatting()
    bestaat = True
    try:
        df = conn.read(worksheet="Scorebord", ttl=0)
    except Exception as _e:
        df = None
        # Alleen bij een écht ontbrekend tabblad opnieuw opbouwen. Bij een gewone leesfout
        # (quota/timeout) NIETS schrijven: anders vervangen we het hele gedeelde scorebord
        # door één rij en verdwijnen alle klasgenoten uit de ranglijst.
        _fout = type(_e).__name__.lower()
        if 'worksheetnotfound' not in _fout and 'notfound' not in _fout:
            return
        bestaat = False
    if df is None or 'gebruiker' not in getattr(df, 'columns', []):
        if bestaat:
            return  # blad gelezen maar onverwachte inhoud → niet overschrijven
        df = pd.DataFrame(columns=list(sm.keys()))
    df = df[df['gebruiker'] != sm['gebruiker']]
    nieuw = pd.concat([df, pd.DataFrame([sm])], ignore_index=True)
    if bestaat:
        try: conn.update(worksheet="Scorebord", data=nieuw)
        except Exception: pass   # niet forceren met create: dat wist het bestaande blad
    else:
        try: conn.create(worksheet="Scorebord", data=nieuw)
        except Exception: pass

@st.cache_data(ttl=120, show_spinner=False)
def lees_scorebord(cache_key):
    """Lees het Scorebord-tabblad en bouw de competitie-metrics. Gecached (2 min) zodat de
    competitie-tab het niet bij elke rerun opnieuw ophaalt; met 'Ververs' direct te verversen."""
    try:
        df = conn.read(worksheet="Scorebord", ttl=0)
    except Exception:
        return []
    if df is None or 'gebruiker' not in getattr(df, 'columns', []):
        return []
    _labels = {'woorden': '📘 Woorden', 'actief': '🎓 Actief', 'stam': '⏳ Stamtijden', 'struct': '🧱 Structuur'}
    out = []
    for _, r in df.iterrows():
        naam = str(r.get('gebruiker', '')).strip()
        if not naam:
            continue
        def _i(k):
            try: return int(float(r.get(k, 0)))
            except Exception: return 0
        ond = {'woorden': {'beh': _i('w_beh'), 'pog': _i('w_pog')}, 'actief': {'beh': _i('a_beh'), 'pog': _i('a_pog')},
               'stam': {'beh': _i('s_beh'), 'pog': _i('s_pog')}, 'struct': {'beh': _i('r_beh'), 'pog': _i('r_pog')}}
        gedaan = [_labels[k] for k in ['woorden', 'actief', 'stam', 'struct'] if ond[k]['pog'] > 0]
        out.append({'naam': naam, 'xp': _i('xp'), 'niveau': _i('niveau'), 'titel': str(r.get('titel', '')),
                    'week': _i('week'), 'totaal': _i('totaal'), 'badges': _i('badges'),
                    'onderdelen': ond, 'gedaan': gedaan})
    return out

def opslaan_naar_cloud(update_scorebord=True):
    if not st.session_state.get('last_user'): return
    try:
        rij = _bouw_rij_dict()
        df_row = pd.DataFrame([rij])
        ws = _ws_naam(st.session_state.last_user)
        # Schrijf naar het EIGEN tabblad (geen kruis-overschrijving). Bestaat de tab nog niet →
        # aanmaken. Lukt beide niet → terugval op de oude gedeelde methode (app blijft werken).
        try:
            conn.update(worksheet=ws, data=df_row)
        except Exception:
            try:
                conn.create(worksheet=ws, data=df_row)
            except Exception:
                _opslaan_legacy(rij)
        if update_scorebord:
            try:
                _update_scorebord()
            except Exception:
                pass
        st.session_state['_opslag_mislukt'] = None   # geslaagd → eventuele waarschuwing weg
        try:
            st.toast("💾 Voortgang opgeslagen", icon="✅")
        except Exception:
            pass
    except Exception as e:
        # 429/quota: niet dramatisch — je voortgang staat veilig in het geheugen en wordt straks
        # opnieuw geprobeerd. Toon een rustige melding i.p.v. een grote rode foutbalk.
        _msg = str(e)
        if "429" in _msg or "RESOURCE_EXHAUSTED" in _msg or "Quota" in _msg:
            try: st.toast("⏳ Even te druk met opslaan — je voortgang wordt zo automatisch opgeslagen.", icon="⏳")
            except Exception: pass
        else:
            # Echte opslagfout: onthoud dit zodat we het blijvend (niet alleen als vluchtige toast)
            # boven de tabbladen kunnen tonen — anders denkt de student dat het is opgeslagen.
            st.session_state['_opslag_mislukt'] = _msg[:120]
            try: st.toast(f"⚠️ Opslaan lukte niet: {_msg[:80]}", icon="⚠️")
            except Exception: pass

def trigger_save(forceer=False):
    if not st.session_state.get('last_user') or not st.session_state.get('data'): return
    nieuwe_vocab_stats = {}
    for word in st.session_state.data:
        s = int(word.get('streak', 0)); g = int(word.get('score_goed', 0)); f = int(word.get('score_fout', 0)); l = word.get('laatst_geoefend', "")
        lf = word.get('laatst_fout', "")
        if s > 0 or g > 0 or f > 0 or l != "":
            entry = {'streak': s, 'g': g, 'f': f}
            if l: entry['laatst_geoefend'] = l
            if lf: entry['lf'] = lf
            nieuwe_vocab_stats[word['grieks']] = entry

    st.session_state.vocab_stats = nieuwe_vocab_stats
    # De accent-ongevoelige streak-index is afgeleid van vocab_stats; hier bevat vocab_stats
    # verse dict-objecten, dus de index moet opnieuw worden opgebouwd (anders stale streaks).
    st.session_state._vocab_streak_idx = None

    # --- GEBATCHTE CLOUD-OPSLAG ---
    # De in-memory stats hierboven zijn altijd up-to-date (instant). Het trage deel is het
    # wegschrijven naar Google Sheets (read + update = twee netwerkrondjes). Dat doen we niet
    # meer op élk antwoord, maar elke 5 antwoorden — plus altijd geforceerd bij einde/uitloggen.
    st.session_state.save_teller = st.session_state.get('save_teller', 0) + 1
    if forceer or st.session_state.save_teller >= 5:
        st.session_state.save_teller = 0
        # Het scorebord (competitie) alleen bijwerken bij een geforceerde opslag (einde sessie /
        # uitloggen), niet elke 5 beurten — zo blijft de reguliere opslag licht (alleen je eigen tab).
        opslaan_naar_cloud(update_scorebord=forceer)

# --- INITIALISATIE ---
for key in ['data', 'sessie_lijst', 'huidig_item', 'huidige_sub_modus', 'huidige_vorm_data', 'feedback', 
            'fouten_huidig_woord', 'huidige_opties', 'last_user', 'huidig_vers', 'huidige_vers_referentie', 'geziene_verzen',
            'actief_flashcard_huidig', 'actief_nakijk_resultaten', 'mix_combo', 'dag_stats',
            'stam_sessie_lijst', 'stam_huidig', 'stam_sub_modus', 'stam_fouten', 'stam_feedback', 'stam_opties_gram', 'stam_opties_praesens', 'stam_mc_solved',
            'struct_sessie_lijst', 'struct_huidig', 'struct_sub_modus', 'struct_fouten', 'struct_feedback', 'struct_opties_cat', 'struct_opties_eig', 'struct_opties_bet', 'struct_mc_solved',
            'gestrafte_woorden_vocab', 'gestrafte_woorden_stam', 'gestrafte_woorden_struct', 'actieve_sessie_vast_vers', 'gekozen_autonoom_vers']:
    if key not in st.session_state: st.session_state[key] = None

if st.session_state.stam_sessie_lijst is None: st.session_state.stam_sessie_lijst = []
if st.session_state.struct_sessie_lijst is None: st.session_state.struct_sessie_lijst = []
if st.session_state.geziene_verzen is None: st.session_state.geziene_verzen = []
if st.session_state.mix_combo is None: st.session_state.mix_combo = {}
if st.session_state.dag_stats is None: st.session_state.dag_stats = {}
if st.session_state.get('prod_stats') is None: st.session_state.prod_stats = {}
if st.session_state.get('verwar_stats') is None: st.session_state.verwar_stats = {}
if st.session_state.get('ui_prefs') is None: st.session_state.ui_prefs = {}
if st.session_state.get('badges') is None: st.session_state.badges = {}
if st.session_state.get('dagdoel') is None: st.session_state.dagdoel = {}
if st.session_state.get('actief_stats') is None: st.session_state.actief_stats = {}
if st.session_state.get('ontleed_stats') is None: st.session_state.ontleed_stats = {}
if st.session_state.get('klank_stats') is None: st.session_state.klank_stats = {}
if st.session_state.get('dagblok_actief') is None: st.session_state.dagblok_actief = False
if st.session_state.get('dagblok_paar_wacht') is None: st.session_state.dagblok_paar_wacht = None
if st.session_state.get('dagblok_bezig') is None: st.session_state.dagblok_bezig = False
if st.session_state.get('dagblok_spring') is None: st.session_state.dagblok_spring = None
if st.session_state.get('sessie_goed') is None: st.session_state.sessie_goed = {}
if st.session_state.get('sessie_fout') is None: st.session_state.sessie_fout = {}
if st.session_state.get('sessie_verwar_kandidaten') is None: st.session_state.sessie_verwar_kandidaten = {}
if st.session_state.get('paar_lijst') is None: st.session_state.paar_lijst = []
if st.session_state.get('paar_huidig') is None: st.session_state.paar_huidig = None
if st.session_state.get('paar_fout') is None: st.session_state.paar_fout = 0
if st.session_state.get('paar_feedback') is None: st.session_state.paar_feedback = None
if st.session_state.get('paar_klaar') is None: st.session_state.paar_klaar = False
if st.session_state.get('paar_solved') is None: st.session_state.paar_solved = {'A': False, 'B': False}
if st.session_state.get('paar_solved_voor') is None: st.session_state.paar_solved_voor = None
if st.session_state.get('paar_overtik') is None: st.session_state.paar_overtik = False
if st.session_state.get('save_teller') is None: st.session_state.save_teller = 0
if st.session_state.get('sessie_net_klaar') is None: st.session_state.sessie_net_klaar = False
if st.session_state.gestrafte_woorden_vocab is None: st.session_state.gestrafte_woorden_vocab = set()
if st.session_state.gestrafte_woorden_stam is None: st.session_state.gestrafte_woorden_stam = set()
if st.session_state.gestrafte_woorden_struct is None: st.session_state.gestrafte_woorden_struct = set()

def laad_volgend_woord():
    if st.session_state.sessie_lijst:
        volgend = st.session_state.sessie_lijst.pop(0)
        st.session_state.huidig_item = volgend[0]
        st.session_state.huidige_sub_modus = volgend[1]
    else:
        # Dagblok: als het woord-deel klaar is, markeer het en ga (indien er paren zijn) naadloos
        # door naar de verwarparen-oefening.
        if st.session_state.get('dagblok_actief'):
            st.session_state.dagblok_actief = False
            dagdoel_woordblok_af()
            _paren = st.session_state.get('dagblok_paar_wacht') or []
            st.session_state.dagblok_paar_wacht = None
            if _paren:
                st.session_state.paar_lijst = _paren
                st.session_state.paar_klaar = False
                st.session_state.paar_overtik = False
                st.session_state.paar_solved_voor = None
                st.session_state.paar_fout = 0
                st.session_state.paar_huidig = _paren.pop(0)
                st.session_state.huidig_item = None; st.session_state.huidige_sub_modus = None
                st.session_state.fouten_huidig_woord = 0
                st.session_state.huidige_opties = []; st.session_state.huidige_vorm_data = None
                trigger_save(forceer=True)
                return
        # sessie liep leeg: markeer als 'net klaar' als er daadwerkelijk geoefend was
        if st.session_state.get('huidig_item') is not None:
            st.session_state.sessie_net_klaar = True
        st.session_state.huidig_item = None; st.session_state.huidige_sub_modus = None
        trigger_save(forceer=True)  # einde sessie: laatste antwoorden zeker wegschrijven
    st.session_state.fouten_huidig_woord = 0
    st.session_state.huidige_opties = []; st.session_state.huidige_vorm_data = None

def laad_volgend_stam_woord():
    if st.session_state.stam_sessie_lijst:
        volgend = st.session_state.stam_sessie_lijst.pop(0)
        st.session_state.stam_huidig = volgend[0]
        st.session_state.stam_sub_modus = volgend[1]
    else:
        st.session_state.stam_huidig = None; st.session_state.stam_sub_modus = None
        trigger_save(forceer=True)
    st.session_state.stam_fouten = 0
    st.session_state.stam_opties_gram = []; st.session_state.stam_opties_praesens = []
    st.session_state.stam_mc_solved = {"gram": False, "praesens": False}

def laad_volgend_struct_woord():
    if st.session_state.struct_sessie_lijst:
        volgend = st.session_state.struct_sessie_lijst.pop(0)
        st.session_state.struct_huidig = volgend[0]
        st.session_state.struct_sub_modus = volgend[1]
    else:
        st.session_state.struct_huidig = None; st.session_state.struct_sub_modus = None
        trigger_save(forceer=True)
    st.session_state.struct_fouten = 0
    st.session_state.struct_opties_cat = []; st.session_state.struct_opties_eig = []; st.session_state.struct_opties_bet = []
    st.session_state.struct_mc_solved = {"cat": False, "eig": False, "bet": False}

# ==========================================
# MAIN APP FUNCTIE
# ==========================================
def main():
    if "u" in st.query_params:
        auto_user = st.query_params["u"]
        if st.session_state.data is None or st.session_state.last_user != auto_user:
            st.session_state.last_user = auto_user
            st.session_state.data = laad_gebruiker_data(auto_user)

    with st.sidebar:
        if st.session_state.data is None:
            if st.session_state.get('laad_fout'):
                st.error("⚠️ Kon je gegevens nu even niet laden (mogelijk te druk of geen verbinding). "
                         "Je voortgang is **niet** gewijzigd — wacht een halve minuut en log opnieuw in.")
            st.header("👤 Inloggen")
            st.caption("ℹ️ Kies een unieke naam en code (bijv. 'zomer2026').")
            col_u, col_p = st.columns(2)
            with col_u: u_naam = st.text_input("Naam", key="inp_naam").strip()
            with col_p: u_code = st.text_input("Code", type="password", key="inp_code").strip()
            
            if st.button("Inloggen", type="primary"):
                if u_naam and u_code:
                    user_input = f"{u_naam}_{u_code}"
                    st.query_params["u"] = user_input
                    st.session_state.data = laad_gebruiker_data(user_input)
                    st.session_state.last_user = user_input
                    st.rerun()
                else: st.warning("Vul beide velden in.")
        else:
            st.success(f"👋 Welkom, {st.session_state.last_user.split('_')[0]}!")
            if st.button("🚪 Uitloggen"): 
                trigger_save(forceer=True); st.session_state.data = None; st.session_state.last_user = None
                if "u" in st.query_params: del st.query_params["u"]
                st.rerun()
            
            st.write("---")
            with st.expander("⚙️ Backup Herstellen"):
                backup_input = st.text_area("JSON Backup", label_visibility="collapsed")
                if st.button("Herstel"):
                    if backup_input:
                        try:
                            schoon_input = backup_input.strip().replace('“', '"').replace('”', '"').replace("'", '"')
                            nieuwe_data = json.loads(schoon_input)
                            for w in st.session_state.data:
                                if w['grieks'] in nieuwe_data:
                                    b = nieuwe_data[w['grieks']]
                                    w['streak'] = b.get('streak', 0); w['score_goed'] = b.get('g', 0); w['score_fout'] = b.get('f', 0); w['laatst_geoefend'] = b.get('laatst_geoefend', "")
                            trigger_save()
                            st.success("Succesvol hersteld!")
                        except Exception as e: st.error(f"Fout: {e}")

    if st.session_state.data:
        if st.session_state.get('_opslag_mislukt'):
            st.error("⚠️ Je laatste opslag lukte niet — je voortgang staat nog in het geheugen (nog niet in de cloud). "
                     "Blijf even oefenen (dan probeert de app het vanzelf opnieuw) of log uit en weer in. "
                     f"\n\n*Technische melding: {st.session_state['_opslag_mislukt']}*")
        # Weergavevolgorde: eerst het dagblok, dan de oefen-tabbladen in leervolgorde, dan de rest.
        # Weergavevolgorde van de tabbladen (Dagelijks doel zit nu ín Voortgang).
        # Alleen de tabbladen die je aan hebt staan worden aangemaakt. Wat je uitzet bestaat deze
        # sessie simpelweg niet: het content-blok wordt overgeslagen (zie de _TOON-guards hieronder),
        # dus er is ook geen 'app in de app' met verborgen tabjes.
        _MENU_SLEUTELS = ["woorden", "lijst", "voortgang", "actief", "stam", "struct",
                          "lezen", "gram", "uitleg", "nlgr", "ontleden", "klank"]
        _volgorde = list(TAB_KEUZE)
        if nieuwe_gebruiker():
            # Nog niets geoefend? Begin bij de uitleg — Streamlit opent altijd het eerste tabblad.
            _volgorde.sort(key=lambda t: 0 if t[0] == "uitleg" else 1)
        _zichtbaar = [(_sl, _lab) for _sl, _lab in _volgorde if tab_zichtbaar(_sl)]
        _tabs_z = st.tabs([_lab for _sl, _lab in _zichtbaar])
        _tab_van_sleutel = {_sl: _tabs_z[_i] for _i, (_sl, _lab) in enumerate(_zichtbaar)}
        # menu[i] = het content-blok zoals het in de code staat; None (en overgeslagen) als het uit staat.
        menu = [_tab_van_sleutel.get(_s) for _s in _MENU_SLEUTELS]
        _TOON = [tab_zichtbaar(_s) for _s in _MENU_SLEUTELS]

        # Eenvoud-modus: standaard alleen de basis-opties; aan te zetten in ℹ️ Uitleg & Hulp.
        _geav = bool(st.session_state.get('ui_geavanceerd',
                     (st.session_state.get('ui_prefs') or {}).get('geavanceerd', False)))
        if not _geav:
            st.info("🧭 Je zit in de **eenvoudige modus** — alleen het belangrijkste is zichtbaar. Zet *‘Geavanceerde opties tonen’* aan in het **ℹ️ Uitleg & Hulp**-tabblad voor alle mogelijkheden.")

       # ==========================================
        # TAB 1: WOORDENSCHAT
        # ==========================================
        if _TOON[0]:
         with menu[0]:
            if 'vocab_sessie_verzen' not in st.session_state: st.session_state.vocab_sessie_verzen = {}
            if 'vocab_cluster_strongs' not in st.session_state: st.session_state.vocab_cluster_strongs = {}
            
            col1, col2 = st.columns([1, 2])
            with col1:
                # --- Wens 7: herstel eerder gekozen instellingen als default (uit ui_prefs) ---
                _prefs = st.session_state.get('ui_prefs', {}) or {}

                # De oefenvorm staat niet meer bovenaan: standaard kiest de app hem zelf per woord
                # (flashcard, dan meerkeuze, dan typen) net als in het Leerpad. Zelf kiezen kan
                # onder "Extra instellingen".
                _modus_opts = [AUTO_VORM, "1. Leer", "2. MC", "3. Mix (MC + Typen)", "4. Typen"]
                modus = _prefs.get('modus') if _prefs.get('modus') in _modus_opts else AUTO_VORM

                _alle_keuze = ["Lessen", "🎮 Leerpad (levels)", "Mastery", "Knelpunten (Gericht Oefenen)", "Lang niet gedaan (Geheugen-onderhoud)", "Gelijkende woorden (look-alikes)", "Mijn verwarwoorden"]
                _keuze_opts = _alle_keuze if _geav else ["🎮 Leerpad (levels)", "Mijn verwarwoorden"]
                _keuze_idx = _keuze_opts.index(_prefs['keuze']) if _prefs.get('keuze') in _keuze_opts else 0
                keuze = st.selectbox("Oefening:", _keuze_opts, index=_keuze_idx)
                doel = []
                gekozen = list(_prefs.get('lessen') or [])
                lp_herhaal_aantal = 0  # aantal 'oude woorden' dat het Leerpad meeneemt (0 = uit)

                # --- GECOMBINEERDE LES-, KNELPUNT- EN ONDERHOUDSFILTER ---
                if keuze in ["Lessen", "Knelpunten (Gericht Oefenen)", "Lang niet gedaan (Geheugen-onderhoud)", "Gelijkende woorden (look-alikes)"]:
                    alle_lessen = sorted(list(set(veilig_les_nummer(i) for i in st.session_state.data)))
                    _saved_lessen = [l for l in gekozen if l in alle_lessen]
                    _default_lessen = _saved_lessen if _saved_lessen else (alle_lessen[:3] if alle_lessen else [])
                    gekozen = st.multiselect("Kies lessen", alle_lessen, default=_default_lessen)
                    poule_lessen = [word for word in st.session_state.data if veilig_les_nummer(word) in gekozen]

                    if "Lang niet gedaan" in keuze:
                        doel = [w for w in poule_lessen if str(w.get('laatst_geoefend', '') or '').strip() != '']

                    elif "Knelpunten" in keuze:
                        knel_kandidaten = []
                        for w in poule_lessen:
                            g = int(w.get('score_goed', 0)); f = int(w.get('score_fout', 0)); s = int(w.get('streak', 0))

                            # Realistische drempel: elke gemaakte fout óf een lage retentie ondanks oefenen
                            if f > 0 or (g > 0 and s <= 3):
                                ratio = f / max(1, (g + f))
                                knel_kandidaten.append((w, ratio, f))

                        # Sorteer primair op hoogste fout-ratio, secundair op absolute fouten
                        knel_kandidaten.sort(key=lambda x: (x[1], x[2]), reverse=True)
                        doel = [x[0] for x in knel_kandidaten[:20]]

                    elif "Gelijkende woorden" in keuze:
                        # Wens 3: al geoefende woorden binnen de selectie die qua spelling op elkaar lijken
                        # (verwarparen.json). De sessie wordt een gewogen mix — vaak-fout vaker.
                        doel = verzamel_lookalikes(poule_lessen, laad_verwarparen_db(), alleen_geoefend=True)
                        if doel:
                            st.caption(f"🔀 {len(doel)} geoefende look-alike-woorden. De sessie wordt een gewogen mix: "
                                       "woorden die je vaker fout doet komen vaker terug.")
                        else:
                            st.caption("ℹ️ Nog geen geoefende look-alikes in deze lessen. Oefen de woorden eerst "
                                       "gewoon, of kies meer/andere lessen.")

                    else:
                        doel = poule_lessen

                elif keuze == "Mastery":
                    doel = [word for word in st.session_state.data if int(word.get('streak', 0)) >= 30]

                elif keuze == "Mijn verwarwoorden":
                    # Wens 4: woorden die je aantoonbaar verwart (uit verwar_stats), over alle lessen heen.
                    doel = verzamel_verwarwoorden(st.session_state.data, st.session_state.get('verwar_stats', {}))
                    if doel:
                        st.caption(f"🧩 {len(doel)} woorden in je persoonlijke verwar-lijst. Ze vallen vanzelf af zodra je ze weer beheerst.")
                    else:
                        st.caption("✅ Nog geen verwarwoorden geregistreerd — die verschijnen hier zodra je in een sessie twee woorden door elkaar haalt.")

                elif keuze == "🎮 Leerpad (levels)":
                    # Duolingo-stijl: XP + oplopende rang, en een pad van levels die je vrijspeelt.
                    _xp = bereken_xp(st.session_state.data)
                    _niv = niveau_van_xp(_xp)
                    st.markdown(f"#### 🎮 Niveau {_niv['niveau']} · 📖 {_niv['titel']}")
                    st.progress(_niv['xp_in_niveau'] / max(1, _niv['xp_voor_volgend']))
                    st.caption(f"⭐ {_niv['xp_totaal']} XP — nog {_niv['xp_voor_volgend'] - _niv['xp_in_niveau']} XP tot niveau {_niv['niveau'] + 1}."
                               + (f" Rang {_niv['rang_nr']}/{_niv['rang_totaal']}; hierna **{_niv['volgende_rang']}**."
                                  if _niv.get('volgende_rang') else " Je hebt de laatste rang bereikt!"))
                    with st.expander("📖 Hoe werken de rangen?", expanded=False):
                        st.markdown(RANG_UITLEG)

                    _levels = leerpad_status(bouw_leerpad_levels(st.session_state.data))
                    _ontgrendeld = [l for l in _levels if l['ontgrendeld']]
                    _voltooid_n = sum(1 for l in _levels if l['voltooid'])
                    st.caption(f"🏁 {_voltooid_n}/{len(_levels)} levels voltooid · een woord telt als 'af' bij streak ≥ {LEERPAD_DREMPEL}.")
                    st.caption("🧭 In het Leerpad bepaalt de app de oefenvorm: nieuwe woorden eerst als **flashcard**, daarna **meerkeuze**, en bij een stevige streak **typen**.")

                    if _ontgrendeld:
                        _huidig = next((l for l in _levels if l['ontgrendeld'] and not l['voltooid']), _ontgrendeld[-1])
                        _labels = [f"{'✅' if l['voltooid'] else '▶️'} Level {l['index']} · {l['titel']} ({l['klaar']}/{l['totaal']})" for l in _ontgrendeld]
                        _def_idx = _ontgrendeld.index(_huidig) if _huidig in _ontgrendeld else 0
                        _sel = st.selectbox("Kies een ontgrendeld level:", _labels, index=_def_idx)
                        _gekozen_level = _ontgrendeld[_labels.index(_sel)]
                        doel = list(_gekozen_level['woorden'])
                        _volgend_slot = next((l for l in _levels if not l['ontgrendeld']), None)
                        if _volgend_slot:
                            st.caption(f"🔒 Hierna: Level {_volgend_slot['index']} — {_volgend_slot['titel']}. Rond eerst het huidige level af.")
                    else:
                        doel = []

                    # Oude stof meenemen: standaard een kleine herhaalronde (min. 5 oude woorden erbij).
                    _lp_opts = {
                        "Kleine herhaalronde (5 oude woorden) (aanrader)": 5,
                        "1 oud woord meenemen": 1,
                        "Grote herhaalronde (10 oude woorden)": 10,
                        "Alleen dit level": 0,
                    }
                    _lp_c1, _lp_c2 = st.columns(2)
                    _lp_keuze = _lp_c1.selectbox("🔁 Oude stof meenemen:", list(_lp_opts.keys()), index=0,
                                                 help="Naast de woorden van dit level worden ook je langst-niet-geoefende woorden meegenomen (oudste datum eerst), zodat je oude stof niet vergeet.")
                    lp_herhaal_aantal = _lp_opts[_lp_keuze]
                    # Hoeveel gloednieuwe woorden je per sessie aandurft. Woorden waar je al mee
                    # bezig bent komen áltijd mee — die wil je juist afmaken.
                    lp_nieuw_max = _lp_c2.slider("🌱 Nieuwe woorden per sessie:", 1, 7,
                                                 int(_prefs.get('lp_nieuw_max', 3)), key="lp_nieuw_max_s",
                                                 help="Alleen woorden die je nog nooit hebt gezien. Woorden waar je al aan begonnen bent tellen hier niet in mee.")
                    _prefs_nu = st.session_state.get('ui_prefs')
                    if isinstance(_prefs_nu, dict):
                        _prefs_nu['lp_nieuw_max'] = int(lp_nieuw_max)

                    with st.expander("🗺️ Toon het hele pad", expanded=False):
                        for l in _levels:
                            _ico = "✅" if l['voltooid'] else ("▶️" if l['ontgrendeld'] else "🔒")
                            st.markdown(f"{_ico} **Level {l['index']}** · {l['titel']} — {l['klaar']}/{l['totaal']}")

                st.write("---")
                if _geav:
                    # Wens 6: alle extra opties achter een uitklap-menu zodat het scherm niet meteen vol staat.
                    with st.expander("⚙️ Extra instellingen", expanded=False):
                        optie_context = st.checkbox("📖 Toon woorden áltijd in Bijbelcontext", key="optie_context", value=_prefs.get('optie_context', False))
                        optie_cluster = st.checkbox("🛡️ Groep kaartenbak-selectie rondom gedeelde Bijbelverzen", key="optie_cluster_vocab", value=_prefs.get('optie_cluster_vocab', False))
                        optie_kleur_nv = st.checkbox("🎨 Markeer Naamvallen in zin (Kleur)", key="optie_kleur_nv_vocab", value=_prefs.get('optie_kleur_nv_vocab', True))
                        optie_nieuw_mee = st.checkbox("🌱 Nieuwe woorden mee-oefenen (Instroom)", key="optie_nieuw_mee_vocab", value=_prefs.get('optie_nieuw_mee_vocab', True))
                        optie_verwar = st.checkbox("⚠️ Verwarwoorden er samen bij trekken (discrimineren)", key="optie_verwarparen", value=_prefs.get('optie_verwarparen', True), help="Als een gekozen woord een look-alike heeft die je al eens hebt geoefend, komt die twin in dezelfde sessie mee — zo leer je ze onderscheiden. Voegt nooit nieuwe woorden toe.")
                        optie_mastery_context = st.checkbox("🏆 Mastery-woorden in Bijbelcontext tonen", key="optie_mastery_context", value=_prefs.get('optie_mastery_context', False), help="Vink aan om woorden met streak ≥ 30 in een echte Bijbelzin te oefenen (extra invulvelden). Staat dit uit, dan overhoor je ook mastery-woorden gewoon los, zodat de flow snel blijft.")
                        optie_audio = st.checkbox("🔊 Uitspraak-knop tonen", key="optie_audio", value=_prefs.get('optie_audio', True), help="Toont een knop die het woord voorleest volgens de Erasmiaanse uitspraak (via de fonetische spelling).")
                        optie_opbouw = st.checkbox("🔗 Toon woordopbouw (samenstellingen)", key="optie_opbouw_vocab", value=_prefs.get('optie_opbouw_vocab', False), help="Toont bij samengestelde woorden het voorzetsel + het grondwoord dat je al kent, bv. εἰσέρχομαι = εἰς + ἔρχομαι. Zo zie je de verbanden sneller.")
                        st.write("")
                        modus = st.radio("Oefenvorm:", _modus_opts, key="vocab_oefenvorm",
                                         index=_modus_opts.index(modus),
                                         help="Automatisch = de app kiest per woord: een nieuw woord eerst als flashcard, daarna meerkeuze, en typen zodra je het kent. Kies je zelf een vorm, dan krijgt elk woord die vorm.")
                    _stijl_opts = ["🤖 Aanbevolen Mix", "🎛️ Zelf Samenstellen"]
                    _stijl_idx = _stijl_opts.index(_prefs['oefen_stijl']) if _prefs.get('oefen_stijl') in _stijl_opts else 0
                    oefen_stijl = st.radio("Sessie opbouw:", _stijl_opts, index=_stijl_idx)
                else:
                    # eenvoudige modus: nette standaardwaarden, opties niet tonen
                    optie_context = _prefs.get('optie_context', False)
                    optie_cluster = _prefs.get('optie_cluster_vocab', False)
                    optie_kleur_nv = _prefs.get('optie_kleur_nv_vocab', True)
                    optie_nieuw_mee = _prefs.get('optie_nieuw_mee_vocab', True)
                    optie_verwar = _prefs.get('optie_verwarparen', True)
                    optie_mastery_context = _prefs.get('optie_mastery_context', False)
                    optie_audio = _prefs.get('optie_audio', True)
                    optie_opbouw = _prefs.get('optie_opbouw_vocab', False)
                    oefen_stijl = "🤖 Aanbevolen Mix"

                # Wens 7: onthoud de actuele keuzes in-memory; ze worden meegeschreven bij de eerstvolgende
                # cloud-opslag. BELANGRIJK: bijwerken (merge), niet de hele dict vervangen — anders wissen
                # we de instellingen van álle andere tabbladen (die ook in ui_prefs worden bewaard).
                _ui_now = st.session_state.get('ui_prefs')
                if not isinstance(_ui_now, dict):
                    _ui_now = {}
                _ui_now.update({
                    'lessen': gekozen,
                    'optie_context': optie_context, 'optie_cluster_vocab': optie_cluster,
                    'optie_kleur_nv_vocab': optie_kleur_nv, 'optie_nieuw_mee_vocab': optie_nieuw_mee,
                    'optie_verwarparen': optie_verwar, 'optie_mastery_context': optie_mastery_context,
                    'optie_audio': optie_audio, 'optie_opbouw_vocab': optie_opbouw,
                    'geavanceerd': _geav,
                })
                if _geav:
                    # Alleen in de geavanceerde modus zijn dit échte keuzes. In de eenvoudige modus
                    # staan ze vast op een standaardwaarde; die zou anders je gekozen instellingen
                    # overschrijven zodra je één keer in eenvoudige modus komt.
                    _ui_now.update({'modus': modus, 'keuze': keuze, 'oefen_stijl': oefen_stijl})
                st.session_state.ui_prefs = _ui_now

                custom_counts = None
                if oefen_stijl == "🎛️ Zelf Samenstellen" and doel:
                    c_nieuw = len([w for w in doel if krijg_streak(w, 'vocab') == 0])
                    c_inc = len([w for w in doel if 1 <= krijg_streak(w, 'vocab') <= 3])
                    c_train = len([w for w in doel if 4 <= krijg_streak(w, 'vocab') <= 15])
                    c_beheer = len([w for w in doel if 16 <= krijg_streak(w, 'vocab') <= 29])
                    c_mast = len([w for w in doel if krijg_streak(w, 'vocab') >= 30])
                    
                    st.caption("Kies exact hoeveel woorden je per fase wilt oefenen:")
                    
                    if 'v_sl_nieuw' not in st.session_state: st.session_state.v_sl_nieuw = 0
                    if 'v_sl_inc' not in st.session_state: st.session_state.v_sl_inc = 0
                    if 'v_sl_train' not in st.session_state: st.session_state.v_sl_train = 0
                    if 'v_sl_beheer' not in st.session_state: st.session_state.v_sl_beheer = 0
                    if 'v_sl_mast' not in st.session_state: st.session_state.v_sl_mast = 0

                    d_n = min(st.session_state.v_sl_nieuw, c_nieuw); d_i = min(st.session_state.v_sl_inc, c_inc)
                    d_t = min(st.session_state.v_sl_train, c_train); d_b = min(st.session_state.v_sl_beheer, c_beheer); d_m = min(st.session_state.v_sl_mast, c_mast)

                    val_n = st.slider(f"🌱 Nieuw (0) — Beschikbaar: {c_nieuw}", 0, max(1, min(20, c_nieuw)), d_n, key="v_sl_nieuw")
                    val_i = st.slider(f"🐣 Prille start (1-3) — Beschikbaar: {c_inc}", 0, max(1, min(20, c_inc)), d_i, key="v_sl_inc")
                    val_t = st.slider(f"🏃 In Training (4-15) — Beschikbaar: {c_train}", 0, max(1, min(20, c_train)), d_t, key="v_sl_train")
                    val_b = st.slider(f"🛡️ Beheerst (16-29) — Beschikbaar: {c_beheer}", 0, max(1, min(20, c_beheer)), d_b, key="v_sl_beheer")
                    val_m = st.slider(f"🏆 Mastery (30+) — Beschikbaar: {c_mast}", 0, max(1, min(20, c_mast)), d_m, key="v_sl_mast")
                    
                    custom_counts = {'nieuw': val_n, 'incubatie': val_i, 'training': val_t, 'beheerst': val_b, 'mastery': val_m}
                
                if st.button("Start Sessie", type="primary"):
                    if doel:
                        st.session_state.gestrafte_woorden_vocab = set()
                        # Vangnet: punten van een eventueel afgebroken vorige sessie alsnog boeken
                                # Eindsamenvatting-accumulatoren voor de nieuwe sessie leegmaken
                        _sessie_reset_samenvatting()
                        st.session_state.sessie_net_klaar = False
                        st.session_state._ballonnen_getoond = False

                        # Mijn verwarwoorden én Gelijkende woorden → paar-oefening: twee (lijkende) woorden
                        # tegelijk, van allebei de betekenis geven, per deel goedgekeurd.
                        _paar_bron = None
                        if keuze == "Mijn verwarwoorden":
                            _paar_bron = bouw_verwar_paren(st.session_state.data, st.session_state.get('verwar_stats', {}))
                        elif "Gelijkende woorden" in keuze:
                            _paar_bron = bouw_lookalike_paren(doel, laad_verwarparen_db())
                        if _paar_bron:
                            r_engine.shuffle(_paar_bron)
                            st.session_state.paar_lijst = _paar_bron
                            st.session_state.paar_klaar = False
                            st.session_state.huidig_item = None
                            st.session_state.sessie_lijst = []
                            st.session_state.paar_huidig = st.session_state.paar_lijst.pop(0)
                            st.session_state.paar_fout = 0
                            st.session_state.paar_feedback = None
                            st.rerun()

                        modus_id = str(modus[0])
                        
                        is_lang_geleden = ("Lang niet gedaan" in keuze)
                        is_knelpunten = ("Knelpunten" in keuze)
                        is_puur_typen = (modus_id == "4")
                        is_leerpad = (keuze == "🎮 Leerpad (levels)")

                        # Bij knelpunten vriest de instroom van gloednieuwe woorden dicht:
                        mag_geen_nieuw = is_lang_geleden or is_knelpunten or is_puur_typen or (not optie_nieuw_mee)

                        if is_leerpad:
                            # In het Leerpad IS het level de lesstof, dus de instroom-filters gelden hier
                            # niet (anders krijg je nooit de nieuwe woorden van je level). Wél gedoseerd:
                            # woorden waar je al mee bezig bent komen allemaal mee — die wil je afmaken —
                            # maar gloednieuwe woorden alleen tot het ingestelde maximum, zodat een
                            # sessie behapbaar blijft.
                            def _is_nieuw(w):
                                return (int(w.get('streak', 0)) == 0 and int(w.get('score_goed', 0)) == 0
                                        and int(w.get('score_fout', 0)) == 0
                                        and not str(w.get('laatst_geoefend', '') or '').strip())
                            _bezig = [w for w in doel if int(w.get('streak', 0)) < LEERPAD_DREMPEL and not _is_nieuw(w)]
                            _nieuw = [w for w in doel if _is_nieuw(w)]
                            _al_af = [w for w in doel if int(w.get('streak', 0)) >= LEERPAD_DREMPEL]
                            r_engine.shuffle(_bezig); r_engine.shuffle(_nieuw)
                            sampled = _bezig + _nieuw[:max(1, int(lp_nieuw_max))]
                            if not sampled:
                                sampled = list(_al_af)          # level helemaal af? dan opfrissen
                            elif _nieuw:
                                _rest = len(_nieuw) - max(1, int(lp_nieuw_max))
                                if _rest > 0:
                                    st.caption(f"🌱 {min(len(_nieuw), int(lp_nieuw_max))} nieuwe woorden deze sessie; "
                                               f"nog {_rest} nieuw in dit level voor een volgende ronde.")
                        else:
                            sampled = kies_gefaseerde_oefensessie(
                                doel,
                                module='vocab',
                                custom_counts=custom_counts,
                                sorteer_oudste_eerst=is_lang_geleden,
                                verbied_nieuwe_woorden=mag_geen_nieuw,
                                totale_db=st.session_state.data
                            )

                        # Verwar-twins van gekozen woorden erbij trekken (alleen al-geoefende woorden),
                        # zodat look-alikes in dezelfde sessie naast elkaar geoefend worden.
                        if sampled and st.session_state.get('optie_verwarparen', True):
                            sampled = voeg_verwar_twins_toe(
                                sampled, st.session_state.data, laad_verwarparen_db(), max_twins=3
                            )
                            # Ook je EIGEN verwarparen (uit verwar_stats) blijven meekomen bij het
                            # betreffende woord, tot je ze allebei beheerst.
                            sampled = voeg_eigen_verwar_toe(
                                sampled, st.session_state.data, st.session_state.get('verwar_stats', {}), max_extra=3
                            )

                        # Leerpad: neem oude stof mee (langst niet geoefend, oudste datum eerst).
                        if sampled and lp_herhaal_aantal > 0:
                            sampled = voeg_herhaalwoorden_toe(sampled, st.session_state.data, lp_herhaal_aantal)

                        if not sampled: st.warning("⚠️ 0 woorden geselecteerd voor deze criteria.")
                        else:
                            if st.session_state.get('optie_cluster_vocab', False):
                                b_db_temp = laad_bijbel_db()
                                from collections import defaultdict
                                s_map = defaultdict(list)
                                for w in sampled:
                                    if w.get('strong'): s_map[str(w['strong'])].append(w['grieks'])
                                    
                                ongetoetst = set(s_map.keys()); v_map = {}; cluster_strongs = defaultdict(set)
                                
                                while len(ongetoetst) >= 2:
                                    beste_ref = None; beste_hits = set()
                                    for ref, zin in b_db_temp.items():
                                        zs = {str(z.get('strong', '')) for z in zin if z.get('strong')}
                                        ov = ongetoetst.intersection(zs)
                                        if len(ov) > len(beste_hits):
                                            beste_hits = ov; beste_ref = ref
                                            if len(beste_hits) >= 4: break
                                    
                                    if beste_ref and len(beste_hits) >= 2:
                                        for s in beste_hits:
                                            for k in s_map[s]: v_map[k] = beste_ref; cluster_strongs[beste_ref].add(s)
                                            ongetoetst.remove(s)
                                    else: break
                                    
                                for s in ongetoetst:
                                    for k in s_map[s]: v_map[k] = None
                                    
                                st.session_state.vocab_sessie_verzen = v_map; st.session_state.vocab_cluster_strongs = dict(cluster_strongs)
                                pos_map = {}
                                for w in sampled:
                                    grieks_k = w['grieks']; ref = v_map.get(grieks_k); pos = 999
                                    if ref and ref in b_db_temp:
                                        target_s = str(w.get('strong', ''))
                                        for idx_zw, zw in enumerate(b_db_temp[ref]):
                                            if str(zw.get('strong', '')) == target_s: pos = idx_zw; break
                                    pos_map[grieks_k] = pos
                                    
                                sampled.sort(key=lambda w: (str(v_map.get(w['grieks']) or 'zzz_solo'), pos_map.get(w['grieks'], 999)))
                            else: st.session_state.vocab_sessie_verzen = {}; st.session_state.vocab_cluster_strongs = {}

                            st.session_state.modus_actief = modus_id
                            if modus == AUTO_VORM or keuze == "🎮 Leerpad (levels)":
                                # Automatisch (standaard): de app kiest de oefenvorm per woord - flashcard,
                                # dan meerkeuze, dan typen. Dit geldt nu ook buiten het Leerpad.
                                st.session_state.sessie_lijst = leerpad_kaart_volgorde(sampled)
                            elif modus_id == "3":
                                st.session_state.sessie_lijst = [(w, "3_mc") for w in sampled] + [(w, "3_typ") for w in sampled]
                                st.session_state.mix_combo = {w['grieks']: False for w in sampled}
                            else: st.session_state.sessie_lijst = [(w, modus_id) for w in sampled]
                            laad_volgend_woord(); st.rerun()
                    else: st.warning("⚠️ Geen knelpunten of oefenwoorden gevonden in de geselecteerde lessen.")

            with col2:
                if st.session_state.get('paar_huidig'):
                    # === VERWARPAREN-OEFENING: beide woorden tegelijk; een goed deel wordt onthouden ===
                    wA, wB = st.session_state.paar_huidig
                    _pkey = (wA['grieks'], wB['grieks'])
                    if st.session_state.get('paar_solved_voor') != _pkey:
                        st.session_state.paar_solved = {'A': False, 'B': False}
                        st.session_state.paar_solved_voor = _pkey
                    solved = st.session_state.paar_solved

                    st.caption("🧩 Verwarparen — geef van BEIDE woorden de betekenis. Een deel dat al goed is, hoef je niet opnieuw in te vullen.")
                    _pc1, _pc2 = st.columns(2)
                    _pc1.markdown(f"<div class='grieks-woord' style='font-size:40px;'>{wA['grieks']}</div>", unsafe_allow_html=True)
                    _pc2.markdown(f"<div class='grieks-woord' style='font-size:40px;'>{wB['grieks']}</div>", unsafe_allow_html=True)

                    if st.session_state.get('paar_feedback'):
                        _fb = st.session_state.paar_feedback
                        {"success": st.success, "warning": st.warning}.get(_fb["type"], st.error)(_fb["msg"])
                        st.session_state.paar_feedback = None

                    if st.session_state.get('paar_overtik'):
                        # Na 2 fouten: overtypen om te verankeren (telt niet voor de streak).
                        st.warning("⚠️ Overtikken: typ beide betekenissen exact over om verder te gaan. Dit telt niet voor je streak.")
                        st.info(f"**{wA['grieks']}** = {wA['nederlands']}  ·  **{wB['grieks']}** = {wB['nederlands']}")
                        forceer_focus()
                        with st.form(f"paar_ov_{wA['grieks']}_{wB['grieks']}", clear_on_submit=True):
                            _ovA = st.text_input(f"Typ de betekenis van {wA['grieks']} over:")
                            _ovB = st.text_input(f"Typ de betekenis van {wB['grieks']} over:")
                            _ovsub = st.form_submit_button("Bevestig", type="primary")
                        if _ovsub:
                            # met item, zodat 'laatst_geoefend' wordt gestempeld en deze woorden
                            # niet eeuwig als 'achterstallig' bovenaan blijven staan
                            registreer_oefening(wA); registreer_oefening(wB)
                            if check_betekenis(_ovA or "", wA.get('nederlands', '')) and check_betekenis(_ovB or "", wB.get('nederlands', '')):
                                _lijst = st.session_state.get('paar_lijst', [])
                                # Eerst het volgende paar pakken en pas daarna dit paar achteraan
                                # zetten — andersom krijg je bij het laatste paar hetzelfde paar
                                # eindeloos terug en verschijnt het afrondscherm nooit.
                                _volgende = _lijst.pop(0) if _lijst else None
                                _lijst.append((wA, wB))  # komt later nog een keer terug
                                st.session_state.paar_lijst = _lijst
                                st.session_state.paar_huidig = _volgende
                                st.session_state.paar_fout = 0
                                st.session_state.paar_overtik = False
                                st.session_state.paar_solved_voor = None
                                if st.session_state.paar_huidig is None:
                                    st.session_state.paar_klaar = True
                                st.session_state.paar_feedback = {"type": "success", "msg": "Genoteerd! Dit paar komt straks nog terug."}
                                trigger_save(); st.rerun()
                            else:
                                st.error("Nog niet exact overgetypt — kijk goed naar de betekenissen hierboven.")
                    else:
                        def _woord_hint(_w):
                            _delen = [d for d in [_w.get('lexeem_info', '') or _w.get('grieks_info', ''), _w.get('fonetisch', '')] if d]
                            _ez = f"{_w.get('anker', '')} {_w.get('beeld', _w.get('associatie', _w.get('opmerking', '')))}".strip()
                            if _ez: _delen.append(_ez)
                            return " | ".join(_delen)

                        # Zodra je een fout hebt gemaakt op dit paar: hint van de nog-open woorden erbij.
                        if int(st.session_state.get('paar_fout', 0)) >= 1:
                            for _w, _k in [(wA, 'A'), (wB, 'B')]:
                                if not solved[_k]:
                                    _h = _woord_hint(_w)
                                    if _h:
                                        st.info(f"💡 **{_w['grieks']}**: {_h}")

                        with st.form(f"paar_form_{wA['grieks']}_{wB['grieks']}", clear_on_submit=True):
                            if solved['A']:
                                st.success(f"✓ {wA['grieks']} = {wA['nederlands']}"); _inA = None
                            else:
                                _inA = st.text_input(f"Betekenis van {wA['grieks']}:")
                            if solved['B']:
                                st.success(f"✓ {wB['grieks']} = {wB['nederlands']}"); _inB = None
                            else:
                                _inB = st.text_input(f"Betekenis van {wB['grieks']}:")
                            _sub = st.form_submit_button("✓ Nakijken", type="primary")

                        if _sub:
                            registreer_oefening(wA); registreer_oefening(wB)
                            _fout_deze = False
                            if not solved['A']:
                                if check_betekenis(_inA or "", wA.get('nederlands', '')):
                                    solved['A'] = True
                                else:
                                    _fout_deze = True; wA['score_fout'] = int(wA.get('score_fout', 0)) + 1
                            if not solved['B']:
                                if check_betekenis(_inB or "", wB.get('nederlands', '')):
                                    solved['B'] = True
                                else:
                                    _fout_deze = True; wB['score_fout'] = int(wB.get('score_fout', 0)) + 1
                            if _fout_deze:
                                st.session_state.paar_fout = int(st.session_state.get('paar_fout', 0)) + 1

                            _lijst = st.session_state.get('paar_lijst', [])
                            if solved['A'] and solved['B']:
                                if int(st.session_state.get('paar_fout', 0)) == 0:
                                    for _w in (wA, wB):
                                        _w['score_goed'] = int(_w.get('score_goed', 0)) + 1
                                        _w['streak'] = int(_w.get('streak', 0)) + 1
                                    verzwak_verwarring(wA['grieks']); verzwak_verwarring(wB['grieks'])
                                st.session_state.paar_feedback = {"type": "success", "msg": f"✓ Allebei goed! **{wA['grieks']}** = {wA['nederlands']} · **{wB['grieks']}** = {wB['nederlands']}"}
                                st.session_state.paar_huidig = _lijst.pop(0) if _lijst else None
                                st.session_state.paar_fout = 0; st.session_state.paar_solved_voor = None
                                if st.session_state.paar_huidig is None:
                                    st.session_state.paar_klaar = True
                                trigger_save(); st.rerun()
                            elif int(st.session_state.get('paar_fout', 0)) >= 2:
                                # Na 2 fouten: eerst overtypen (geen streak), dan komt het paar later terug.
                                st.session_state.paar_feedback = {"type": "error", "msg": f"Het was: **{wA['grieks']}** = {wA['nederlands']} · **{wB['grieks']}** = {wB['nederlands']}. Typ het even over."}
                                st.session_state.paar_overtik = True
                                trigger_save(); st.rerun()
                            else:
                                _rest = [w['grieks'] for w, k in [(wA, 'A'), (wB, 'B')] if not solved[k]]
                                st.session_state.paar_feedback = {"type": "warning", "msg": f"Nog te doen: {', '.join(_rest)} — bekijk de hint."}
                                st.rerun()

                    st.write("---")
                    st.caption(f"Nog {len(st.session_state.get('paar_lijst', []))} paar te gaan.")
                    if st.button("⏹️ Stop paar-sessie"):
                        st.session_state.paar_huidig = None; st.session_state.paar_lijst = []
                        st.session_state.paar_klaar = False; st.session_state.paar_overtik = False
                        # ook de half-opgeloste staat wissen, anders levert een herstart van
                        # hetzelfde paar gratis streak op voor de al goede helft
                        st.session_state.paar_solved = {}; st.session_state.paar_solved_voor = None
                        st.session_state.paar_fout = 0
                        st.rerun()

                elif st.session_state.get('paar_klaar'):
                    st.balloons()
                    st.success("🎉 Verwar-paren afgerond! Goed bezig met discrimineren. Paren die je weer beheerst, verdwijnen vanzelf uit je lijst.")
                    st.session_state.paar_klaar = False

                elif st.session_state.huidig_item:
                    item = st.session_state.huidig_item
                    huidige_sub_modus = st.session_state.huidige_sub_modus
                    # Mastery-in-context (Bijbelzin + vormvragen) alleen als de gebruiker dat aanvinkt;
                    # anders wordt ook een streak>=30 woord gewoon los overhoord (flow blijft snel).
                    is_mastery = int(item.get('streak', 0)) >= 30 and st.session_state.get('optie_mastery_context', False)
                    heeft_vormen = 'vormen_data' in item and isinstance(item['vormen_data'], list) and len(item['vormen_data']) > 0
                    
                    if st.session_state.huidige_vorm_data is None:
                        if is_mastery and heeft_vormen: st.session_state.huidige_vorm_data = r_engine.choice(item['vormen_data'])
                        else: st.session_state.huidige_vorm_data = {"vorm": item.get('grieks', 'Onbekend'), "parsing": "basis"}

                    huidige_vorm = str(st.session_state.huidige_vorm_data.get('vorm', item.get('grieks')))
                    huidige_parsing = str(st.session_state.huidige_vorm_data.get('parsing', 'basis'))
                    extra_info = item.get('lexeem_info', '') or item.get('grieks_info', '')
                    
                    hint_delen = [d for d in [extra_info, item.get('fonetisch', '')] if d]
                    ezelsbrug = f"{item.get('anker', '')} {item.get('beeld', item.get('associatie', item.get('opmerking', '')))}".strip()
                    if ezelsbrug: hint_delen.append(ezelsbrug)
                    actuele_hint = "💡 " + " | ".join(hint_delen)

                    if st.session_state.feedback:
                        if st.session_state.feedback["type"] == "success": st.success(st.session_state.feedback["msg"])
                        elif st.session_state.feedback["type"] == "warning": st.warning(st.session_state.feedback["msg"])
                        elif st.session_state.feedback["type"] == "info": st.info(st.session_state.feedback["msg"])
                        else: st.error(st.session_state.feedback["msg"])
                        st.session_state.feedback = None

                    zin_data = None
                    is_context_gewenst = (is_mastery and huidige_sub_modus != '1') or st.session_state.get('optie_context', False) or st.session_state.get('optie_cluster_vocab', False)
                    
                    if is_context_gewenst:
                        st.caption(f"{'🏆 Mastery Modus' if (is_mastery and huidige_sub_modus != '1') else '📖 Leren in Context'}. (Basis: **{item.get('grieks')}**)")
                        bijbel_db = laad_bijbel_db()
                        user_vocab_map = {str(w['strong']): w for w in st.session_state.data if w.get('strong')}
                        actief_vers_ref = st.session_state.vocab_sessie_verzen.get(item['grieks'])
                        co_strongs = st.session_state.vocab_cluster_strongs.get(actief_vers_ref, set()) if actief_vers_ref else set()
                        
                        zin_data = zoek_context_zin(
                            item.get('strong'), 
                            item.get('woordsoort', ''), 
                            bijbel_db, 
                            anti_spiek=(huidige_sub_modus != '1'), 
                            specifieke_vorm=huidige_vorm,
                            bekende_vocab=user_vocab_map,
                            vastgezet_vers_ref=actief_vers_ref,
                            kleur_aan=st.session_state.get('optie_kleur_nv_vocab', True),
                            co_doel_strongs=co_strongs
                        )
                        if zin_data: 
                            st.markdown(zin_data["html"], unsafe_allow_html=True)
                            if st.session_state.get('optie_kleur_nv_vocab', True):
                                st.markdown("<div style='font-size:14px; margin-bottom:4px;'><b>Legenda:</b> <span style='color:#33ccff'>Nom</span> | <span style='color:#28a745'>Gen</span> | <span style='color:#6f42c1'>Dat</span> | <span style='color:#dc3545'>Acc</span> | <span style='color:#fd7e14'>Voc</span></div>", unsafe_allow_html=True)
                            st.markdown(f"<div class='grieks-woord' style='font-size: 42px; padding: 10px; margin-top: -10px;'>{huidige_vorm}</div>", unsafe_allow_html=True)
                        else: st.markdown(f"<div class='grieks-woord'>{huidige_vorm}</div>", unsafe_allow_html=True)
                    else: st.markdown(f"<div class='grieks-woord'>{huidige_vorm}</div>", unsafe_allow_html=True)

                    if st.session_state.get('optie_audio', True):
                        audio_knop(item.get('fonetisch', ''), key="vocab")

                    # Woordopbouw: bij een samengesteld woord het voorzetsel + grondwoord tonen,
                    # zodat je het verband met een woord dat je al kent snel ziet.
                    if st.session_state.get('optie_opbouw_vocab', False):
                        _ob = woord_opbouw(item.get('grieks', ''))
                        if _ob:
                            st.caption(f"🔗 Opbouw: **{_ob['voorzetsel']}** (*{_ob['betekenis']}*) + "
                                       f"**{_ob['grondwoord']}** → **{item.get('grieks','')}**")

                    correct_antw = str(item.get('nederlands', ''))
                    fout_msg_volledig = f"**{item.get('grieks')}** ({extra_info}) — {item.get('fonetisch', '')} — **{correct_antw}**"
                    if is_mastery and heeft_vormen: fout_msg_volledig += f" ({huidige_parsing})"

                    if huidige_sub_modus == 'overtik':
                        st.warning("⚠️ Overtikken: Typ de betekenis exact over om door te gaan.")
                        st.info(f"Het juiste antwoord is: **{correct_antw}**")
                        forceer_focus()
                        with st.form(key=f"form_overtik_{item.get('grieks')}", clear_on_submit=True):
                            inp = st.text_input("Typ over:").lower().strip()
                            if st.form_submit_button("Bevestig"):
                                registreer_oefening(item)
                                if check_betekenis(inp, correct_antw):
                                    st.session_state.feedback = {"type": "success", "msg": "Genoteerd! Komt straks terug."}
                                    laad_volgend_woord(); st.rerun()
                                else: st.error("Niet correct overgetypt.")

                    elif huidige_sub_modus == '1':
                        st.info(actuele_hint)
                        st.write(f"Betekenis: **{correct_antw}**")
                        if st.button("Volgende"):
                            registreer_oefening(item)   # ook flashcards tellen mee voor je oefen-streak
                            laad_volgend_woord(); st.rerun()

                    elif huidige_sub_modus in ['4', '3_typ']:
                        if st.session_state.fouten_huidig_woord >= 1: 
                            st.info(actuele_hint)
                        forceer_focus()
                        with st.form(key=f"form_vocab_{item.get('grieks')}", clear_on_submit=True):
                            inp = st.text_input("Vertaling:").lower().strip()
                            # De vorm-vraag (naamval/getal/geslacht) alleen stellen als het écht een
                            # naamwoord-vorm is. Heeft de parsing tijd/persoon/wijs (werkwoordvormen),
                            # dan is die vraag met alleen naamval/getal/geslacht onbeantwoordbaar → sla 'm
                            # over en toets alleen de vertaling (anders eindeloze 'bijna'-lus).
                            _pl_mv = str(huidige_parsing or "").lower()
                            _heeft_nv = any(x in _pl_mv for x in ('nom', 'gen', 'dat', 'acc', 'voc'))
                            _heeft_ww = any(x in _pl_mv for x in ('praes', 'imperf', 'fut', 'aor', 'perf', 'plqp',
                                                                   'pers', '1e', '2e', '3e', 'ind', 'conj', 'optat',
                                                                   'imperat', 'infin', 'partic'))
                            vorm_getoetst = is_mastery and heeft_vormen and _heeft_nv and not _heeft_ww
                            if vorm_getoetst:
                                _vc1, _vc2, _vc3 = st.columns(3)
                                _nv = _vc1.selectbox("Naamval", [""] + NAAMVAL_OPTIES, key=f"mvorm_nv_{item.get('grieks')}")
                                _gt = _vc2.selectbox("Getal", [""] + GETAL_OPTIES, key=f"mvorm_gt_{item.get('grieks')}")
                                _gs = _vc3.selectbox("Geslacht", [""] + GESLACHT_OPTIES, key=f"mvorm_gs_{item.get('grieks')}")
                                p_vorm = f"{_nv} {_gt} {_gs}".lower().strip()
                            else:
                                p_vorm = huidige_parsing.lower().strip()

                            if st.form_submit_button("✓ Nakijken"):
                                registreer_oefening(item)
                                
                                # Ontkoppelde semantische en syntactische evaluatie
                                vertaling_correct = check_betekenis(inp, correct_antw)
                                
                                def norm_p(p_str):
                                    s = str(p_str).lower().replace('.', ' ').strip()
                                    s = re.sub(r'\s+', ' ', s)
                                    s = s.replace('accusativus', 'acc').replace('accusatief', 'acc').replace('genitivus', 'gen').replace('genitief', 'gen')
                                    s = s.replace('dativus', 'dat').replace('datief', 'dat').replace('nominativus', 'nom').replace('nominatief', 'nom').replace('vocativus', 'voc').replace('vocatief', 'voc')
                                    s = s.replace('enkelvoud', 'ev').replace('meervoud', 'mv').replace('singularis', 'ev').replace('pluralis', 'mv').replace('sg', 'ev').replace('pl', 'mv')
                                    s = s.replace('mannelijk', 'm').replace('vrouwelijk', 'v').replace('onzijdig', 'o').replace('fem', 'v').replace('masc', 'm').replace('neut', 'o')
                                    return re.sub(r'[^\w]', '', s)

                                vorm_correct = (norm_p(p_vorm) == norm_p(huidige_parsing)) if vorm_getoetst else True

                                if vertaling_correct and vorm_correct:
                                    _oude_streak = int(item.get('streak', 0))
                                    if st.session_state.fouten_huidig_woord == 0 and item['grieks'] not in st.session_state.gestrafte_woorden_vocab:
                                        item['score_goed'] = int(item.get('score_goed', 0)) + 1
                                        if huidige_sub_modus == '4': item['streak'] = int(item.get('streak', 0)) + 3
                                        elif huidige_sub_modus == '3_typ': item['streak'] = int(item.get('streak', 0)) + (2 if st.session_state.mix_combo.get(item['grieks'], False) else 1)
                                        dagdoel_plus('woorden')
                                    vier_fase_overgang(_oude_streak, int(item.get('streak', 0)), item.get('grieks', ''))
                                    if st.session_state.fouten_huidig_woord == 0:
                                        verzwak_verwarring(item.get('grieks', ''))
                                    _sessie_noteer_goed(item)

                                    success_msg = f"✓ Goed! **{huidige_vorm}** = {correct_antw}"
                                    if item['grieks'] in st.session_state.gestrafte_woorden_vocab: success_msg += " *(Geen streak-punten: je zag het antwoord al eerder bij dit woord)*"
                                    elif zin_data: success_msg += f"\n\n📖 **{zin_data['ref']}**: {zin_data['grieks_puur']}\n\n🇬🇧 *{zin_data['engels_puur']}*"
                                    
                                    st.session_state.feedback = {"type": "success", "msg": success_msg}
                                    trigger_save(); laad_volgend_woord(); st.rerun()
                                    
                                elif vertaling_correct and not vorm_correct:
                                    # Genuanceerde opvang: vertaling wél snappen, grammaticale duiding afwijken
                                    st.session_state.fouten_huidig_woord += 1
                                    item['score_fout'] = int(item.get('score_fout', 0)) + 1
                                    st.session_state.feedback = {
                                        "type": "warning", 
                                        "msg": f"Inhoudelijk juist (**{inp}**)! Alleen de ontleding (*{p_vorm if p_vorm else 'leeg'}*) week af — het juiste is: **{huidige_parsing}**."
                                    }
                                    st.rerun()
                                    
                                else:
                                    if huidige_sub_modus == '3_typ': st.session_state.mix_combo[item['grieks']] = False
                                    st.session_state.fouten_huidig_woord += 1
                                    huidige_streak = int(item.get('streak', 0))

                                    # Wens 1+2: al bij de eerste fout tonen met welk (al geoefend) woord je het
                                    # mogelijk verwart. Kandidaten worden onthouden voor de eindsamenvatting
                                    # (waar je zélf bevestigt) — niet meer automatisch toegevoegd.
                                    _sessie_noteer_fout(item, inp)
                                    _verwar_note = bouw_verwar_melding(item, inp, st.session_state.data, laad_verwarparen_db())

                                    if huidige_streak >= 16 or st.session_state.fouten_huidig_woord >= 2:
                                        item['score_fout'] = int(item.get('score_fout', 0)) + 1
                                        item['streak'] = max(0, huidige_streak - 2); st.session_state.gestrafte_woorden_vocab.add(item['grieks'])
                                        st.session_state.sessie_lijst.insert(0, (item, 'overtik')); st.session_state.sessie_lijst.append((item, huidige_sub_modus))
                                        st.session_state.feedback = {"type": "error", "msg": f"✗ Fout. Het was: {fout_msg_volledig}{_verwar_note}"}
                                        trigger_save(); laad_volgend_woord()
                                    else:
                                        item['score_fout'] = int(item.get('score_fout', 0)) + 1
                                        st.session_state.feedback = {"type": "warning", "msg": f"Bijna! Bekijk de hint.{_verwar_note}"}
                                    st.rerun()
                    else:
                        if st.session_state.fouten_huidig_woord >= 1: 
                            st.info(actuele_hint)
                        correct_optie = f"{correct_antw} ({huidige_parsing})" if (is_mastery and heeft_vormen) else correct_antw
                        
                        if not st.session_state.huidige_opties:
                            afleiders = []
                            gekozen_betekenissen = {correct_optie}
                            import random as rnd
                            
                            if is_mastery and heeft_vormen:
                                andere_parsings = list(set([str(v.get('parsing', '')) for v in item.get('vormen_data', []) if str(v.get('parsing', '')) != str(huidige_parsing)]))
                                rnd.shuffle(andere_parsings)
                                for p in andere_parsings:
                                    optie = f"{correct_antw} ({p})"
                                    if optie not in gekozen_betekenissen: afleiders.append(optie); gekozen_betekenissen.add(optie)
                                    if len(afleiders) >= 3: break
                                
                                if len(afleiders) < 3:
                                    pool = [w for w in st.session_state.data if w.get('woordsoort') == item.get('woordsoort') and 'vormen_data' in w]
                                    rnd.shuffle(pool)
                                    for w in pool:
                                        for v in w.get('vormen_data', []):
                                            optie = f"{correct_antw} ({v.get('parsing', '')})" 
                                            if optie not in gekozen_betekenissen: afleiders.append(optie); gekozen_betekenissen.add(optie)
                                            if len(afleiders) >= 3: break
                                        if len(afleiders) >= 3: break
                            else:
                                huidige_w_soort = item.get('woordsoort', '')
                                grieks_doel = normaliseer_accent(item.get('grieks', ''))
                                prefix_2 = grieks_doel[:2] if len(grieks_doel)>=2 else ''
                                stam_gok = grieks_doel[1:-2] if len(grieks_doel)>=5 else ''
                                
                                lookalikes_ned = []
                                pool_ws = []

                                # PRIO 1: de precieze look-alike twin(s) uit verwarparen.json als afleider,
                                # maar alleen woorden die de student al eens geoefend heeft.
                                _twins_map = laad_verwarparen_db()
                                _grieks_idx = {w.get('grieks'): w for w in st.session_state.data if w.get('grieks')}
                                for _twin_g in _twins_map.get(item.get('grieks', ''), []):
                                    _tw = _grieks_idx.get(_twin_g)
                                    if _tw and _is_al_geoefend(_tw):
                                        _tw_ned = str(_tw.get('nederlands', '')).strip()
                                        if _tw_ned and _tw_ned not in gekozen_betekenissen:
                                            afleiders.append(_tw_ned); gekozen_betekenissen.add(_tw_ned)
                                    if len(afleiders) >= 2:  # laat ruimte voor variatie
                                        break

                                for w in st.session_state.data:
                                    g_ander = normaliseer_accent(w.get('grieks', ''))
                                    n_ander = str(w.get('nederlands', '')).strip()
                                    if not g_ander or not n_ander or n_ander in gekozen_betekenissen or g_ander == grieks_doel: continue
                                    
                                    if w.get('woordsoort') == huidige_w_soort:
                                        pool_ws.append(n_ander)
                                        verwant_stam = (stam_gok and len(stam_gok)>=3 and stam_gok in g_ander)
                                        verwant_prefix = (prefix_2 and g_ander.startswith(prefix_2) and abs(len(g_ander)-len(grieks_doel))<=2)
                                        if verwant_stam or verwant_prefix: lookalikes_ned.append(n_ander)

                                rnd.shuffle(lookalikes_ned)
                                for ned in lookalikes_ned:
                                    if ned not in gekozen_betekenissen: afleiders.append(ned); gekozen_betekenissen.add(ned)
                                    if len(afleiders) >= 3: break
                                    
                                if len(afleiders) < 3:
                                    rnd.shuffle(pool_ws)
                                    for ned in pool_ws:
                                        if ned not in gekozen_betekenissen: afleiders.append(ned); gekozen_betekenissen.add(ned)
                                        if len(afleiders) >= 3: break
                                        
                                if len(afleiders) < 3:
                                    rest_pool = [w.get('nederlands','') for w in st.session_state.data if w.get('nederlands') not in gekozen_betekenissen and w.get('nederlands')]
                                    rnd.shuffle(rest_pool)
                                    for ned in rest_pool:
                                        if ned not in gekozen_betekenissen: afleiders.append(ned); gekozen_betekenissen.add(ned)
                                        if len(afleiders) >= 3: break

                            # Nooit een afleider tonen die exact dezelfde betekenis heeft als het juiste
                            # antwoord (bv. εὐθέως 'onmiddellijk, meteen' vs εὐθύς 'meteen, onmiddellijk').
                            # Dat maakt de vraag onwinbaar. Bij mastery-vormen NIET filteren: daar verschillen
                            # de opties juist alleen in de parsing tussen haakjes.
                            if not (is_mastery and heeft_vormen):
                                afleiders = [a for a in afleiders if not zelfde_betekenis(a, correct_optie)]

                            st.session_state.huidige_opties = [correct_optie] + afleiders[:3]
                            rnd.shuffle(st.session_state.huidige_opties)

                            # Onthoud bij welk Grieks woord elke afleider-betekenis hoort, zodat we bij
                            # een foute klik meteen kunnen tonen "die betekenis hoort bij X" (ook als je
                            # X nog nooit oefende) en X als verwar-kandidaat kunnen aanbieden.
                            _ned_bron = {}
                            for _w in st.session_state.data:
                                _nb = str(_w.get('nederlands', '')).strip()
                                if _nb and _nb not in _ned_bron:
                                    _ned_bron[_nb] = {'grieks': _w.get('grieks', ''), 'nederlands': _nb}
                            st.session_state.huidige_optie_bron = {
                                _opt: _ned_bron.get(_opt) for _opt in st.session_state.huidige_opties if _opt != correct_optie}

                        cols = st.columns(2)
                        for idx, optie in enumerate(st.session_state.huidige_opties):
                            if cols[idx % 2].button(optie, key=f"btn_{idx}_{item.get('grieks')}"):
                                registreer_oefening(item)
                                # Vangnet: keur ook goed als de gekozen optie qua betekenis identiek is aan
                                # het juiste antwoord (echte synoniemen). Bij mastery telt de parsing wél mee.
                                _optie_goed = (optie == correct_optie) or (
                                    not (is_mastery and heeft_vormen) and zelfde_betekenis(optie, correct_optie))
                                if _optie_goed:
                                    _oude_streak_mc = int(item.get('streak', 0))
                                    if st.session_state.fouten_huidig_woord == 0 and item['grieks'] not in st.session_state.gestrafte_woorden_vocab:
                                        item['score_goed'] = int(item.get('score_goed', 0)) + 1
                                        if huidige_sub_modus == '2': item['streak'] = int(item.get('streak', 0)) + 1
                                        elif huidige_sub_modus == '3_mc': st.session_state.mix_combo[item['grieks']] = True
                                        dagdoel_plus('woorden')
                                    vier_fase_overgang(_oude_streak_mc, int(item.get('streak', 0)), item.get('grieks', ''))
                                    if st.session_state.fouten_huidig_woord == 0:
                                        verzwak_verwarring(item.get('grieks', ''))
                                    _sessie_noteer_goed(item)

                                    success_msg = f"✓ Juist! {fout_msg_volledig}"
                                    if item['grieks'] in st.session_state.gestrafte_woorden_vocab: success_msg += " *(Geen streak-punten: je zag het antwoord al eerder bij dit woord)*"
                                    elif zin_data: success_msg += f"\n\n📖 **{zin_data['ref']}**: {zin_data['grieks_puur']}\n\n🇬🇧 *{zin_data['engels_puur']}*"
                                        
                                    st.session_state.feedback = {"type": "success", "msg": success_msg}
                                    trigger_save(); laad_volgend_woord(); st.rerun()
                                else:
                                    if huidige_sub_modus == '3_mc': st.session_state.mix_combo[item['grieks']] = False
                                    st.session_state.fouten_huidig_woord += 1
                                    huidige_streak = int(item.get('streak', 0))

                                    # Wens 1+2: welk (al geoefend) woord hoort bij de betekenis die je koos?
                                    # Kandidaten worden onthouden voor de eindsamenvatting (zelf bevestigen).
                                    _sessie_noteer_fout(item, optie)
                                    _verwar_note = bouw_verwar_melding(item, optie, st.session_state.data, laad_verwarparen_db())

                                    # Toon expliciet welk woord bij de aangeklikte (foute) betekenis hoort —
                                    # ook als dat woord nog niet geoefend is — en bied het aan de eind-
                                    # samenvatting aan als verwar-kandidaat (zelf te bevestigen).
                                    _bron = (st.session_state.get('huidige_optie_bron') or {}).get(optie)
                                    if _bron and _bron.get('grieks') and _bron.get('grieks') != item.get('grieks'):
                                        _bg = _bron['grieks']; _bn = str(_bron.get('nederlands', ''))
                                        _onthoud_verwar_kandidaten(item.get('grieks', ''), str(item.get('nederlands', '')), optie, {_bg: _bn})
                                        _extra = f"\n\n👉 *“{optie}”* is de betekenis van **{_bg}** ({_bn[:30]})."
                                        if not _verwar_note:
                                            _verwar_note = "\n\n⚠️ **Let op — mogelijk verward:**"
                                        if _extra not in _verwar_note:
                                            _verwar_note += _extra

                                    if huidige_streak >= 16 or st.session_state.fouten_huidig_woord >= 2:
                                        item['score_fout'] = int(item.get('score_fout', 0)) + 1
                                        item['streak'] = max(0, huidige_streak - 2); st.session_state.gestrafte_woorden_vocab.add(item['grieks'])
                                        st.session_state.sessie_lijst.insert(0, (item, 'overtik')); st.session_state.sessie_lijst.append((item, huidige_sub_modus))
                                        st.session_state.feedback = {"type": "error", "msg": f"✗ Fout. Je koos '{optie}'. Het was: {fout_msg_volledig}{_verwar_note}"}
                                        trigger_save(); laad_volgend_woord()
                                    else:
                                        item['score_fout'] = int(item.get('score_fout', 0)) + 1
                                        st.session_state.feedback = {"type": "warning", "msg": f"Onjuist. Bekijk de hint!{_verwar_note}"}
                                    st.rerun()

                    if huidige_sub_modus in ['2', '3_mc', '4', '3_typ']:
                        if st.button("🤔 Ik weet het niet — toon het antwoord", key=f"weetniet_{item.get('grieks')}"):
                            st.session_state.feedback = {"type": "info", "msg": f"💡 **{item.get('grieks')}** = {correct_antw}. Geen aftrek, maar ook geen streak-punten meer voor dit woord — je krijgt hem straks nog een keer, puur om hem echt op te halen."}
                            # Wel markeren als 'gestraft': het antwoord is getoond, dus als de kaart
                            # straks terugkomt levert hij geen volledige streak-punten meer op.
                            st.session_state.gestrafte_woorden_vocab.add(item.get('grieks'))
                            st.session_state.sessie_lijst.append((item, huidige_sub_modus))
                            laad_volgend_woord(); st.rerun()

                    if huidige_sub_modus != 'overtik':
                        st.write("---")
                        _resterend = len(st.session_state.get('sessie_lijst') or [])
                        fase = 'Nieuw' if int(item.get('streak', 0))==0 else ('In Training' if int(item.get('streak', 0))<=15 else ('Beheerst' if int(item.get('streak', 0))<=29 else 'Mastery'))
                        st.caption(f"🔢 Nog {_resterend} te gaan | Fase: {fase} | Streak: {item.get('streak', 0)} | Goed/Fout: {item.get('score_goed', 0)}/{item.get('score_fout', 0)} | Laatst: {item.get('laatst_geoefend', 'Nooit')}")

                elif st.session_state.get('sessie_net_klaar'):
                    if not st.session_state.get('_ballonnen_getoond'):
                        st.balloons()
                        st.session_state._ballonnen_getoond = True
                    st.success("🎉 **Sessie voltooid!** Je voortgang is opgeslagen.")

                    _s_goed = st.session_state.get('sessie_goed') or {}
                    _s_fout = st.session_state.get('sessie_fout') or {}
                    _s_kand = st.session_state.get('sessie_verwar_kandidaten') or {}
                    _fout_griekse = set(_s_fout.keys())
                    _goed_only = {g: n for g, n in _s_goed.items() if g not in _fout_griekse}

                    _c_ok, _c_no = st.columns(2)
                    with _c_ok:
                        st.markdown(f"#### ✅ Goed ({len(_goed_only)})")
                        if _goed_only:
                            for _g, _n in list(_goed_only.items()):
                                st.markdown(f"- **{_g}** — {_n}")
                        else:
                            st.caption("—")
                    with _c_no:
                        st.markdown(f"#### ❌ Fout ({len(_s_fout)})")
                        if _s_fout:
                            for _g, _info in _s_fout.items():
                                st.markdown(
                                    f"- **{_g}** — {_info.get('nederlands','')}  "
                                    f"<span style='color:#aaa;font-size:12px;'>(jij: {_info.get('antwoord','')})</span>",
                                    unsafe_allow_html=True)
                        else:
                            st.caption("—")

                    # --- ⚠️ Zelf bevestigen welke verwarring écht klopte ---
                    _te_bevestigen = {g: d for g, d in _s_kand.items() if d.get('kandidaten')}
                    if _te_bevestigen:
                        st.write("---")
                        st.markdown("#### ⚠️ Mogelijk verward — vink aan wat écht klopte")
                        st.caption("Er zijn vaak meerdere woorden met dezelfde betekenis. Vink alleen aan met welk woord je het echt door elkaar haalde (één, meer of geen). Alleen die worden aan **Mijn verwarwoorden** toegevoegd.")
                        with st.form("verwar_bevestig_form", clear_on_submit=True):
                            for _g, _d in _te_bevestigen.items():
                                st.markdown(f"**{_g}** ({_d.get('nederlands','')}) — jij gaf: *{_d.get('antwoord','')}*")
                                for _cg, _cn in _d.get('kandidaten', {}).items():
                                    st.checkbox(f"↔️ ik verwarde het met **{_cg}** ({_cn})", key=f"vc_{_g}__{_cg}")
                            _bevestig = st.form_submit_button("✅ Toevoegen aan Mijn verwarwoorden", type="primary")
                        if _bevestig:
                            _toegevoegd = 0
                            for _g, _d in _te_bevestigen.items():
                                for _cg in _d.get('kandidaten', {}):
                                    if st.session_state.get(f"vc_{_g}__{_cg}"):
                                        registreer_verwarring(_g, _cg)
                                        _toegevoegd += 1
                            trigger_save(forceer=True)
                            _sessie_reset_samenvatting()
                            st.session_state.sessie_net_klaar = False
                            st.session_state._ballonnen_getoond = False
                            try:
                                st.toast(f"🧩 {_toegevoegd} verwarpaar(en) toegevoegd" if _toegevoegd else "Niets toegevoegd", icon="🧩")
                            except Exception:
                                pass
                            st.rerun()

                    st.write("---")
                    if st.button("✔️ Overzicht sluiten"):
                        _sessie_reset_samenvatting()
                        st.session_state.sessie_net_klaar = False
                        st.session_state._ballonnen_getoond = False
                        st.rerun()
                    st.caption("Klik links op **Start Sessie** voor een nieuwe ronde, of bekijk je voortgang in het 📊-tabblad.")

        # ==========================================
        # TAB 2: LIJST
        # ==========================================
        if _TOON[1]:
         with menu[1]:
            st.subheader("📖 Database & Lijsten")
            weergave = st.selectbox("Wat wil je bekijken?", ["Vocabulaire", "🧩 Mijn verwarwoorden", "Actief Beheersen (Rijtjes)", "Stamtijden", "Structuurwoorden"])

            if weergave == "🧩 Mijn verwarwoorden":
                _paren = verwar_paren_lijst(st.session_state.data or [], st.session_state.get('verwar_stats', {}))
                st.caption("Woordparen die je met elkaar hebt verward (door jou bevestigd). Een paar verdwijnt zodra je beide woorden weer beheerst (streak ≥ 16).")
                if _paren:
                    _rijen = []
                    for p in _paren:
                        _rijen.append({
                            "Woord A": p['a'], "betekenis A": p['a_ned'][:30],
                            "Woord B": p['b'], "betekenis B": p['b_ned'][:30],
                            "Keer verward": p['n'],
                            "Streak A/B": f"{p['a_streak']}/{p['b_streak']}",
                            "Laatst": p['laatst'] or "—",
                        })
                    st.dataframe(pd.DataFrame(_rijen), use_container_width=True, hide_index=True)
                    st.caption(f"Totaal **{len(_paren)}** actieve verwarparen. Oefen ze gericht via *Tabblad 1 → Oefening → Mijn verwarwoorden*.")
                else:
                    st.info("Nog geen verwarparen. Die ontstaan als je in een sessie twee woorden door elkaar haalt en dat in de eindsamenvatting bevestigt.")

            elif weergave == "Vocabulaire" and st.session_state.data:
                alle_lessen = sorted(list(set(veilig_les_nummer(i) for i in st.session_state.data)))
                les_filter = st.selectbox("Bekijk les:", alle_lessen)
                df_vocab = pd.DataFrame([i for i in st.session_state.data if veilig_les_nummer(i) == les_filter])
                if not df_vocab.empty: st.dataframe(df_vocab[[c for c in ['grieks', 'nederlands', 'streak', 'score_goed', 'score_fout', 'laatst_geoefend', 'woordsoort', 'lexeem_info'] if c in df_vocab.columns]], width='stretch')
            elif weergave == "Actief Beheersen (Rijtjes)": st.info("De scores voor actieve rijtjes worden per specifieke cel bijgehouden in je profiel.")
            elif weergave == "Stamtijden":
                stamtijden_db = laad_stamtijden_db()
                if stamtijden_db:
                    stam_lijst = []
                    for w in stamtijden_db:
                        for t_d, vorm in w['stamtijden'].items():
                            s = st.session_state.stam_stats.get(f"{w['praesens']}_{vorm}", {'g': 0, 'f': 0, 'streak': 0})
                            stam_lijst.append({"Les": w.get('les', 0), "Praesens": w['praesens'], "Tijd/Diathese": t_d, "Vorm": vorm, "Betekenis": w['betekenis'], "Streak": s.get('streak', 0), "Goed": s.get('g', 0), "Fout": s.get('f', 0)})
                    st.dataframe(pd.DataFrame(stam_lijst), width='stretch')
            elif weergave == "Structuurwoorden":
                struct_db = laad_structuurwoorden_db()
                if struct_db:
                    str_lijst = []
                    for idx_w, w in enumerate(struct_db):
                        s = _struct_stat_lookup(st.session_state.struct_stats, w, idx_w)
                        str_lijst.append({"Woord": w['grieks'], "Categorie": w['categorie'], "Eigenschap": w['eigenschap'], "Betekenis": w['betekenis'], "Streak": s.get('streak', 0), "Goed": s.get('g', 0), "Fout": s.get('f', 0)})
                    st.dataframe(pd.DataFrame(str_lijst), width='stretch')
        
        # ==========================================
        # TAB 3: VOORTGANG & DASHBOARD
        # ==========================================
        if _TOON[2]:
         with menu[2]:
            st.subheader("📊 Mijn voortgang")
            
            vocab_db = laad_vocab_db()
            actief_db = laad_actief_db()
            stamtijden_db = laad_stamtijden_db()
            str_db = laad_structuurwoorden_db()

            if "actief_stats" not in st.session_state:
                st.session_state.actief_stats = {}

            def toon_meting(label, beheerst, totaal):
                pct = int((beheerst / totaal) * 100) if totaal > 0 else 0
                st.markdown(f"**{label}** (`{beheerst}/{totaal}` — **{pct}%**)")
                st.progress(beheerst / totaal if totaal > 0 else 0.0)

            # --- STATISTIEKEN BEREKENEN (gecached: alleen herberekend bij een druk op 'Ververs') ---
            if 'vg_laatst' not in st.session_state:
                try: st.session_state.vg_laatst = _nu().strftime('%d-%m %H:%M')
                except Exception: st.session_state.vg_laatst = ""
            _vg_versie = int(st.session_state.get('vg_versie', 0))
            _vg_ck = f"{st.session_state.get('last_user', '')}|{_vg_versie}"
            _cvg1, _cvg2 = st.columns([3, 1])
            _cvg1.caption(f"📊 De cijfers hieronder worden **alleen bijgewerkt als je op Ververs drukt** — zo blijft de app snel tijdens het oefenen. Laatst bijgewerkt: {st.session_state.get('vg_laatst') or '—'}.")
            if _cvg2.button("🔄 Ververs", key="vg_ververs"):
                st.session_state.vg_versie = _vg_versie + 1
                # De cache echt leeggooien. De versieteller begint bij elke nieuwe browsersessie
                # weer op 0, terwijl de cache op de server blijft staan; zonder dit kreeg je na
                # een herlaadactie gewoon de oude cijfers terug — vandaar dat de knop 'niets deed'.
                try: voortgang_kernstats.clear()
                except Exception: pass
                try: st.session_state.vg_laatst = _nu().strftime('%d-%m %H:%M')
                except Exception: pass
                st.rerun()
            _vg = voortgang_kernstats(_vg_ck, st.session_state.data,
                                      st.session_state.get('stam_stats', {}), stamtijden_db,
                                      st.session_state.get('struct_stats', {}), str_db)
            stats_vocab = _vg['stats_vocab']; tot_goed_v = _vg['tot_goed_v']; tot_fout_v = _vg['tot_fout_v']
            vocab_streaks = _vg['vocab_streaks']; bekende_freq = _vg['bekende_freq']; totale_freq = _vg['totale_freq']
            stats_stam = _vg['stats_stam']; tot_goed_s = _vg['tot_goed_s']; tot_fout_s = _vg['tot_fout_s']
            stats_str = _vg['stats_str']; tot_goed_st = _vg['tot_goed_st']; tot_fout_st = _vg['tot_fout_st']

            # --- TOP METRICS & BAROMETER ---
            c_met1, c_met2, c_met3, c_met4 = st.columns(4)
            tot_g = tot_goed_v + tot_goed_s + tot_goed_st
            tot_f = tot_fout_v + tot_fout_s + tot_fout_st
            acc = int((tot_g / (tot_g + tot_f) * 100)) if (tot_g + tot_f) > 0 else 0
            
            dekking_pct = int((bekende_freq / max(1, totale_freq)) * 78) if totale_freq else 0
            
            c_met1.metric("Totale Accuratesse", f"{acc}%")
            c_met2.metric("Items op 'Mastery'", stats_vocab['Mastery'] + stats_stam['Mastery'] + stats_str['Mastery'])
            c_met3.metric("Beoordelingen", tot_g + tot_f)
            c_met4.metric("🌍 NT Exegese-Dekking", f"~{dekking_pct}%", help="Geschat percentage van het Nieuwe Testament dat je nu zónder woordenboek kunt lezen op basis van de theologische frequentie van jouw beheerste woorden.")

            st.write("---")

            # --- 🏅 BADGES / ACHIEVEMENTS (Wens 5) ---
            _dagen_set = {str(d) for d in (st.session_state.dag_stats or {}).keys()}
            _oefendagen = len(_dagen_set)
            _dagstreak = 0
            try:
                _cur = pd.Timestamp(_nu().date())
                while str(_cur.date()) in _dagen_set:
                    _dagstreak += 1
                    _cur -= pd.Timedelta(days=1)
            except Exception:
                _dagstreak = 0

            _beh_tot = (stats_vocab['Beheerst'] + stats_vocab['Mastery']
                        + stats_stam['Beheerst'] + stats_stam['Mastery']
                        + stats_str['Beheerst'] + stats_str['Mastery'])
            _mast_tot = stats_vocab['Mastery'] + stats_stam['Mastery'] + stats_str['Mastery']
            # Niveau over ALLE onderdelen samen (woorden + stamtijden + structuur + actief),
            # net als in het competitie-dashboard — zodat "Niveau" overal hetzelfde betekent.
            _xp_totaal = (bereken_xp(st.session_state.data)
                          + bereken_xp_stam(st.session_state.get('stam_stats', {}))
                          + bereken_xp_struct(st.session_state.get('struct_stats', {}))
                          + bereken_xp_actief(st.session_state.get('actief_stats', {})))
            _niv_info = niveau_van_xp(_xp_totaal)
            _badge_stats = {
                'beoordelingen': tot_g + tot_f,
                'oefendagen': _oefendagen,
                'dagstreak': _dagstreak,
                'accuratesse': acc,
                'beheerst': _beh_tot,
                'mastery': _mast_tot,
                'dekking': dekking_pct,
                'verwar_opgelost': int((st.session_state.get('badges') or {}).get('_verwar_opgelost', 0)),
                'niveau': _niv_info['niveau'],
                'stam_beheerst': stats_stam['Beheerst'] + stats_stam['Mastery'],
                'struct_beheerst': stats_str['Beheerst'] + stats_str['Mastery'],
            }
            _badges = badge_definities(_badge_stats)
            if not isinstance(st.session_state.get('badges'), dict):
                st.session_state.badges = {}
            _reeds = {k for k in st.session_state.badges.keys() if not str(k).startswith('_')}
            _behaald_nu = {b['id'] for b in _badges if b['behaald']}
            _nieuw = _behaald_nu - _reeds
            try:
                _vandaag = str(_nu().date())
            except Exception:
                _vandaag = ""
            for _bid in _nieuw:
                st.session_state.badges[_bid] = _vandaag

            # Altijd zichtbaar (motiverend), rest achter een dropdown:
            st.markdown(f"**🏅 Badges: {len(_behaald_nu)}/{len(_badges)} behaald**  ·  🎮 Niveau {_niv_info['niveau']} — {_niv_info['titel']} ({_niv_info['xp_totaal']} XP, over alle onderdelen)")
            with st.expander("🏅 Bekijk al je badges", expanded=False):
                st.caption("Verzamel badges door te oefenen, woorden te beheersen, verwarringen op te lossen en niveaus te halen. Behaalde badges staan bovenaan.")
                _gesorteerd = sorted(_badges, key=lambda b: (not b['behaald']))
                _kols = st.columns(4)
                for _i, _b in enumerate(_gesorteerd):
                    _behaald = _b['behaald']
                    _earned_date = st.session_state.badges.get(_b['id'], "")
                    _rand = "#f6c23e" if _behaald else "#333"
                    _bg = "rgba(246,194,62,0.12)" if _behaald else "rgba(255,255,255,0.03)"
                    _op = "1" if _behaald else "0.45"
                    if _behaald:
                        _status = "✓ behaald" + (f" · {_earned_date}" if _earned_date else "")
                        _status_kleur = "#f6c23e"
                    else:
                        _status = f"🔒 {_b['voortgang']}" if _b['voortgang'] else "🔒"
                        _status_kleur = "#888"
                    with _kols[_i % 4]:
                        st.markdown(f"""
                        <div style="border:2px solid {_rand}; background:{_bg}; border-radius:12px; padding:12px; margin-bottom:10px; text-align:center; opacity:{_op};">
                            <div style="font-size:34px; line-height:1;">{_b['icon']}</div>
                            <div style="font-weight:700; color:#fff; margin-top:6px;">{_b['titel']}</div>
                            <div style="font-size:12px; color:#bbb; margin:4px 0; min-height:32px;">{_b['uitleg']}</div>
                            <div style="font-size:12px; color:{_status_kleur};">{_status}</div>
                        </div>
                        """, unsafe_allow_html=True)

            if _nieuw:
                for _bid in _nieuw:
                    _bdef = next((x for x in _badges if x['id'] == _bid), None)
                    if _bdef:
                        try: st.toast(f"{_bdef['icon']} Badge behaald: {_bdef['titel']}!", icon="🏅")
                        except Exception: pass
                trigger_save(forceer=True)

            # --- 🔎 ONTLEED-ACCURATESSE (uit de Ontleden-tab) ---
            _osa = st.session_state.get('ontleed_stats') or {}
            if any((v.get('g', 0) + v.get('f', 0)) > 0 for v in _osa.values() if isinstance(v, dict)):
                with st.expander("🔎 Ontleed-accuratesse per onderdeel", expanded=False):
                    st.caption("Hoe vaak je in de 🔎 Ontleden-tab het onderdeel in één keer goed had — je tentamenmaat.")
                    _dimlabels = {"woordsoort": "Woordsoort", "naamval": "Naamval", "geslacht": "Geslacht",
                                  "getal": "Getal", "tijd": "Tijd", "wijs": "Wijs", "diathese": "Diathese",
                                  "persoon": "Persoon", "vertaling": "Vertaling"}
                    for _k, _lab in _dimlabels.items():
                        _v = _osa.get(_k) or {}
                        _t = int(_v.get('g', 0)) + int(_v.get('f', 0))
                        if _t > 0:
                            _pct = int(100 * int(_v.get('g', 0)) / _t)
                            st.progress(_pct / 100, text=f"{_lab}: {_pct}% goed ({_v.get('g', 0)}/{_t})")

            # --- 🔊 KLANKWETTEN: eigen lijst, uitgesplitst per klanksoort ---
            _ksa = st.session_state.get('klank_stats') or {}
            if any((v.get('g', 0) + v.get('f', 0)) > 0 for v in _ksa.values() if isinstance(v, dict)):
                with st.expander("🔊 Klankwetten per klanksoort", expanded=False):
                    st.caption("Hoe vaak je in de 🔊 Klankwetten-tab de juiste samensmelting aanwees. "
                               "Zo zie je meteen welke klanksoort nog aandacht nodig heeft.")
                    _krijen = []
                    for _ks, (_knaam, _kletters) in _SAMENSMELT_KLASSEN.items():
                        _kv = _ksa.get(_ks) or {}
                        _kt = int(_kv.get('g', 0)) + int(_kv.get('f', 0))
                        if _kt > 0:
                            _krijen.append((int(100 * int(_kv.get('g', 0)) / _kt), _knaam, _kletters,
                                            int(_kv.get('g', 0)), _kt))
                    for _pct2, _knaam, _kletters, _kg, _kt in sorted(_krijen):
                        st.progress(_pct2 / 100, text=f"{_knaam} ({_kletters}): {_pct2}% goed ({_kg}/{_kt})")
                    _kb = _ksa.get('basiswoord') or {}
                    _kbt = int(_kb.get('g', 0)) + int(_kb.get('f', 0))
                    if _kbt:
                        _pb = int(100 * int(_kb.get('g', 0)) / _kbt)
                        st.progress(_pb / 100, text=f"Basiswoord herkennen: {_pb}% goed ({_kb.get('g', 0)}/{_kbt})")
                    if _krijen:
                        _zwak = sorted(_krijen)[0]
                        if _zwak[0] < 70:
                            st.info(f"💡 **{_zwak[1]}** gaat nog het minst goed ({_zwak[0]}%). Zet in de "
                                    "🔊 Klankwetten-tab alleen die klanksoort aan om er gericht mee te oefenen.")

            st.write("---")

            with st.expander("📉 Gedetailleerde voortgang per onderdeel (uitklappen)", expanded=False):
                # --- DE LEKKENDE EMMER ---
                lekkende_woorden = [w for w in st.session_state.data if 16 <= int(w.get('streak', 0)) <= 17]
                if lekkende_woorden:
                    st.warning(f"🪣 **De Lekkende Emmer:** Je hebt momenteel **{len(lekkende_woorden)} woorden** die balanceren op het randje van je langetermijngeheugen (Streak 16 of 17). Eén foutje en ze vallen terug naar 'In Training'. Ga naar *Tabblad 1* en kies *'Knelpunten'* om deze te stutten!")
                else:
                    st.success("🛡️ **Geen Lekkende Emmer:** Al jouw beheerste woorden staan momenteel stevig in de steigers (Streak 18+).")

                st.write("---")

                # --- VOORTGANG PER VAK ---
                st.markdown("### 🏛️ Voortgang per Verplicht Onderdeel")
                st.caption("Norm: Een item telt als 'Beheerst' zodra het een universele streak van 16 of hoger heeft bereikt.")

                v_g1 = [w for w in vocab_db if 1 <= w.get('les', 0) <= 6]
                v_g2 = [w for w in vocab_db if 7 <= w.get('les', 0) <= 12]
                v_g3 = [w for w in vocab_db if 13 <= w.get('les', 0) <= 14]

                def tel_vocab_beh(lijst):
                    return sum(1 for w in lijst if vocab_streak_van(w.get('grieks', w.get('praesens', '')), vocab_streaks) >= 16)

                v_g1_beh, v_g2_beh, v_g3_beh = tel_vocab_beh(v_g1), tel_vocab_beh(v_g2), tel_vocab_beh(v_g3)

                def tel_paradigma_items(vak_key):
                    tot = 0; beh = 0
                    if actief_db and vak_key in actief_db:
                        for cat, subcats in actief_db[vak_key].items():
                            for sub, items in subcats.items():
                                for item in items:
                                    tot += 1
                                    if st.session_state.actief_stats.get(item['id'], {}).get('streak', 0) >= 16:
                                        beh += 1
                    return tot, beh

                p_g1_tot, p_g1_beh = tel_paradigma_items("Grieks 1")
                p_g2_tot, p_g2_beh = tel_paradigma_items("Grieks 2")
                p_g3_tot, p_g3_beh = tel_paradigma_items("Grieks 3")

                c_g1, c_g2, c_g3 = st.columns(3)
                with c_g1:
                    st.markdown("#### 📘 Grieks 1")
                    toon_meting("Woordenschat (Les 1–6)", v_g1_beh, len(v_g1))
                    st.write("")
                    toon_meting("Paradigma's / Rijtjes", p_g1_beh, p_g1_tot)

                with c_g2:
                    st.markdown("#### 📗 Grieks 2")
                    toon_meting("Woordenschat (Les 7–12)", v_g2_beh, len(v_g2))
                    st.write("")
                    toon_meting("Paradigma's / Rijtjes", p_g2_beh, p_g2_tot)

                with c_g3:
                    st.markdown("#### 📙 Grieks 3")
                    toon_meting("Woordenschat (Les 13–14)", v_g3_beh, len(v_g3))
                    st.write("")
                    toon_meting("Paradigma's / Rijtjes", p_g3_beh, p_g3_tot)

                st.write("---")

                # --- DE MORFOLOGISCHE HORIZON (Interactieve Studieplanner 2.1) ---
                st.markdown("### 🧭 Studieplanner — wanneer ken ik alles?")
                st.caption("Stel je doel, je tempo en je accuratesse in, dan schat de app hoe lang je er nog over doet.")

                fc_c1, fc_c2 = st.columns([1.1, 1.9])
            
                with fc_c1:
                    st.write("**1. Kies je tentamengroep:**")
                    sim_doel_groep = st.selectbox(
                        "Onderdeel:", 
                        ["Tentamen Grieks 1 (Les 1–6)", "Tentamen Grieks 2 (Les 7–12)", "Tentamen Grieks 3 (Les 13–14)"], 
                        label_visibility="collapsed"
                    )
                
                    # De gecorrigeerde, strikte controle op de groepsnaam
                    if "Grieks 1" in sim_doel_groep: fc_pool = v_g1
                    elif "Grieks 2" in sim_doel_groep: fc_pool = v_g2
                    else: fc_pool = v_g3

                    sub_g, sub_f = 0, 0
                    if st.session_state.get('data'):
                        gekozen_lessen = [1,2,3,4,5,6] if "Grieks 1" in sim_doel_groep else ([7,8,9,10,11,12] if "Grieks 2" in sim_doel_groep else [13,14])
                        for w in st.session_state.data:
                            if veilig_les_nummer(w) in gekozen_lessen:
                                try: sub_g += int(w.get('score_goed', 0))
                                except (ValueError, TypeError): pass
                                try: sub_f += int(w.get('score_fout', 0))
                                except (ValueError, TypeError): pass

                    echte_hist_acc = int((sub_g / (sub_g + sub_f)) * 100) if (sub_g + sub_f) > 0 else 78
                    echte_hist_acc = max(50, min(100, echte_hist_acc))

                    # Dynamisch tempo: gemiddeld aantal geoefende items per dag over de afgelopen 2 weken.
                    _recent_pace = 0
                    _ds_pace = st.session_state.get('dag_stats') or {}
                    if _ds_pace:
                        try:
                            _vd = _nu().date(); _grens14 = _vd - pd.Timedelta(days=13)
                            _rtot = 0
                            for _d, _n in _ds_pace.items():
                                try:
                                    _dd = datetime.strptime(str(_d), '%Y-%m-%d').date()
                                    if _grens14 <= _dd <= _vd: _rtot += int(_n)
                                except Exception: pass
                            _recent_pace = int(round(_rtot / 14))
                        except Exception: _recent_pace = 0
                    _pace_default = min(500, max(5, _recent_pace)) if _recent_pace else 30

                    st.write("**2. Bepaal je parameters:**")
                    sim_doel_streak = st.slider("Gewenste Kennis-diepte (Streak):", min_value=2, max_value=30, value=16, help="16 = Beheerst (Standaard PThU norm). 8 = Voldoende om passief te herkennen in een tekst. 30 = Vloeiende Mastery.")
                    if _recent_pace:
                        st.caption(f"⚡ Je tempo van de afgelopen 2 weken: **~{_recent_pace} items/dag** (de schuif staat daarop; pas gerust aan).")
                    sim_dag_vocab = st.number_input("Woorden oefenen per dag:", min_value=5, max_value=1000,
                                                    value=int(_pace_default), step=5,
                                                    help="Typ een getal of gebruik +/−. Je mag ruim boven de 100.")
                    sim_acc_override = st.slider(f"Verwachte Accuratesse (Jouw praktijk is ~{echte_hist_acc}%):", min_value=50, max_value=100, value=echte_hist_acc, step=1)

                with fc_c2:
                    # --- LIVE TELLING PER CATEGORIE VOOR DE GEKOZEN GROEP ---
                    fase_telling = {'Nieuw': 0, 'Training': 0, 'Beheerst': 0, 'Mastery': 0}
                    actuele_dict = {w['grieks']: w for w in st.session_state.get('data', []) if isinstance(w, dict) and 'grieks' in w}
                
                    for w in fc_pool:
                        key = w.get('grieks', '')
                        live_w = actuele_dict.get(key, {})
                        try: strk = int(live_w.get('streak', 0))
                        except (ValueError, TypeError): strk = 0
                        
                        if strk == 0: fase_telling['Nieuw'] += 1
                        elif 1 <= strk <= 15: fase_telling['Training'] += 1
                        elif 16 <= strk <= 29: fase_telling['Beheerst'] += 1
                        else: fase_telling['Mastery'] += 1

                    label_groep = f"{sim_doel_groep.split(' ')[1]} {sim_doel_groep.split(' ')[2]}"
                    st.write(f"**Huidige verdeling van {label_groep}:**")
                
                    c_f1, c_f2, c_f3, c_f4 = st.columns(4)
                    c_f1.metric("Nieuw (0)", fase_telling['Nieuw'])
                    c_f2.metric("In Training (1–15)", fase_telling['Training'])
                    c_f3.metric("Beheerst (16–29)", fase_telling['Beheerst'])
                    c_f4.metric("Mastery (30+)", fase_telling['Mastery'])
                
                    st.write("") # Visuele ademruimte

                    prognose = bereken_studietijd_forecast(fc_pool, 'vocab', doel_streak=sim_doel_streak, dagelijkse_oefeningen=sim_dag_vocab, sim_accuratesse=sim_acc_override)
                
                    if prognose and prognose.get("schuld", 0) == 0:
                        st.success(f"✓ **Doel al bereikt!** Alle woorden binnen deze selectie hebben de door jou ingestelde drempelwaarde van **streak {sim_doel_streak}** al behaald.")
                    elif prognose:
                        min_per_dag = max(3, int(sim_dag_vocab * 0.22))
                    
                        st.markdown(f"""
                        <div style="background-color: #1a1a1a; padding: 22px; border-radius: 12px; border-left: 6px solid #33ccff; box-shadow: 0 4px 15px rgba(0,0,0,0.3);">
                            <div style="font-size: 14px; color: #888; text-transform: uppercase; letter-spacing: 1px;">Verwachte afrondingsdatum</div>
                            <div style="font-size: 34px; font-weight: 800; color: #33ccff; margin: 4px 0 10px 0;">{prognose['einddatum']}</div>
                            <div style="font-size: 15px; color: #ddd; margin-bottom: 16px;">Doorlooptijd: <strong>{prognose['dagen']} dagen</strong> bij circa {min_per_dag} minuten studie per dag.</div>
                            <div style="display: flex; justify-content: space-between; border-top: 1px solid #333; padding-top: 14px;">
                                <div>
                                    <span style="font-size: 20px; font-weight: bold; color: #fff;">{prognose['schuld']} pt</span><br>
                                    <span style="font-size: 12px; color: #aaa;">Nog te leren (streak-punten)</span>
                                </div>
                                <div>
                                    <span style="font-size: 20px; font-weight: bold; color: #f6c23e;">~{prognose['netto_winst']} pt</span><br>
                                    <span style="font-size: 12px; color: #aaa;">Winst per oefening</span>
                                </div>
                                <div>
                                    <span style="font-size: 20px; font-weight: bold; color: #28a745;">{sim_acc_override}%</span><br>
                                    <span style="font-size: 12px; color: #aaa;">Ingevoerde Focus</span>
                                </div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                        # --- GECOMBINEERD DIDACTISCH ADVIESPANEEL ---
                        st.write("") # Visuele ademruimte
                    
                        advies_box = "**💡 Strategische knoppen voor jouw planning:**\n\n"
                    
                        # Hefboom 1: De Modus-keuze (Jouw nieuwe inzicht)
                        advies_box += "1. **Kies de Typ-modus:** Dit model rekent met een standaard mix-sessie. Omdat actieve reproductie bij *Typen* (+3 streak-punten) een aanzienlijk zwaarder beroep doet op je geheugen dan herkenning bij *Meerkeuze* (+1 punt), beloont de motor dit: overschakelen naar de Typ-modus verkort de berekende doorlooptijd in de praktijk fors.\n"
                    
                        # Hefboom 2: De Accuratesse-hefboom
                        winst_bij_plus5 = bereken_studietijd_forecast(fc_pool, 'vocab', doel_streak=sim_doel_streak, dagelijkse_oefeningen=sim_dag_vocab, sim_accuratesse=min(100, sim_acc_override + 5))
                        if winst_bij_plus5:
                            dagen_bespaard = prognose["dagen"] - winst_bij_plus5["dagen"]
                            if dagen_bespaard > 1 and sim_acc_override < 95:
                                advies_box += f"2. **Nauwkeuriger oefenen loont:** Als je je accuratesse van {sim_acc_override}% naar **{sim_acc_override + 5}%** tilt (bijvoorbeeld door bij twijfel de hint te openen in plaats van te gokken), ben je **{dagen_bespaard} dagen** eerder klaar."
                            
                        st.info(advies_box)

                st.write("---")

                # --- 🎮 LEERPAD-INSCHATTING: hoeveel automatische rondes tot alles 'af' is ---
                st.markdown("### 🎮 Leerpad-inschatting")
                st.caption("Kijkt naar het **Leerpad** (Woordenschat → 🎮 Leerpad): een woord telt als 'af' bij "
                           f"streak ≥ {LEERPAD_DREMPEL}. **Ook je beheersingsniveau telt mee** — een woord dat al half "
                           "op streek is heeft minder te gaan, en beheerste woorden tellen als klaar. Het gebruikt "
                           "hetzelfde **woorden-per-dag** en dezelfde **accuratesse** die je hierboven instelde.")
                _lp_pool = [w for w in (fc_pool or st.session_state.get('data') or []) if isinstance(w, dict)]
                _lp_open = [w for w in _lp_pool if int(w.get('streak', 0) or 0) < LEERPAD_DREMPEL]
                _lp_schuld = sum(max(0, LEERPAD_DREMPEL - int(w.get('streak', 0) or 0)) for w in _lp_pool)
                if _lp_schuld <= 0:
                    st.success(f"🎉 Alle woorden in deze selectie hebben al streak ≥ {LEERPAD_DREMPEL} — je leerpad is hier klaar!")
                else:
                    _woorden_ronde = st.number_input("Woorden per Leerpad-ronde:", min_value=1, max_value=60,
                                                     value=12, step=1, key="lp_woorden_ronde",
                                                     help=f"Eén automatische ronde ≈ dit aantal woorden. Een level is {LEERPAD_CHUNK} "
                                                          "nieuwe woorden, maar met 'oude stof meenemen' erbij zijn het er vaak meer.")
                    _acc_lp = (sim_acc_override or 78) / 100.0
                    _netto_lp = max(0.08, (_acc_lp * 1.2) - ((1.0 - _acc_lp) * 2.0))   # netto streak-winst per oefening
                    _oefeningen_totaal = math.ceil(_lp_schuld / _netto_lp)              # aantal woord-beurten te gaan
                    _wpd = max(1, int(sim_dag_vocab))                                   # gelinkt aan 'woorden oefenen per dag'
                    _dagen_lp = math.ceil(_oefeningen_totaal / _wpd)
                    _rondes_dag = max(1, round(_wpd / max(1, int(_woorden_ronde))))     # rondes/dag volgt uit woorden/dag
                    _rondes_totaal = math.ceil(_oefeningen_totaal / max(1, int(_woorden_ronde)))
                    try:
                        _einddat_lp = (_nu() + pd.Timedelta(days=_dagen_lp)).strftime("%d-%m-%Y")
                    except Exception:
                        _einddat_lp = "—"
                    _lpc1, _lpc2, _lpc3 = st.columns(3)
                    _lpc1.metric("Woorden nog niet 'af'", f"{len(_lp_open)}/{len(_lp_pool)}")
                    _lpc2.metric("Rondes te gaan", f"~{_rondes_totaal}")
                    _lpc3.metric("Klaar over", f"~{_dagen_lp} dagen")
                    st.caption(f"📅 Met jouw **{_wpd} woorden/dag** (≈ **{_rondes_dag} automatische ronde(s)/dag** van "
                               f"{int(_woorden_ronde)} woorden) ben je rond **{_einddat_lp}** door je leerpad, bij ~{sim_acc_override}% accuratesse.")
                    # --- Motiverend: past dit binnen de cursus-vensters? (Grieks 1 ~3mnd, 2 ~3mnd, 3 ~1,5mnd) ---
                    _gnaam = "Grieks 1" if "Grieks 1" in sim_doel_groep else ("Grieks 3" if "Grieks 3" in sim_doel_groep else "Grieks 2")
                    _venster = 45 if _gnaam == "Grieks 3" else 90
                    _venstertekst = "±6 weken" if _venster == 45 else "±3 maanden"
                    _nodig_wpd = max(1, math.ceil(_oefeningen_totaal / _venster))       # woorden/dag om binnen het venster klaar te zijn
                    _nodig_rondes = max(1, round(_nodig_wpd / max(1, int(_woorden_ronde))))
                    if _dagen_lp <= _venster:
                        st.success(f"🎉 Ruim op schema! Voor **{_gnaam}** heb je {_venstertekst}, en zo ben je al na ~{_dagen_lp} dagen rond. "
                                   f"Eigenlijk is **~{_nodig_wpd} woorden/dag** (≈ {_nodig_rondes} ronde(s)) al genoeg voor dat venster — dit ga je makkelijk redden! 💪")
                    else:
                        st.info(f"💡 Voor **{_gnaam}** heb je {_venstertekst}. Om alles binnen dat venster te kennen doe je "
                                f"**~{_nodig_wpd} woorden/dag** (≈ {_nodig_rondes} ronde(s)/dag). Nu staat 'ie op {_wpd}/dag — "
                                "zet 'm hierboven een tandje hoger en je ligt op schema! 🚀")

                st.write("---")

                # --- DE STAMTIJDEN SLUIS ---
                st.markdown("### ⏳ De Stamtijden-Sluis")
                tot_stam_ww = len(stamtijden_db) if stamtijden_db else 0
                ontgrendeld_stam_ww = sum(1 for w in stamtijden_db if vocab_streak_van(w['praesens'], vocab_streaks) >= 5) if stamtijden_db else 0

                c_sluis1, c_sluis2 = st.columns([2, 1])
                with c_sluis1:
                    st.write("Werkwoorden waarvan de stamtijden-training is ontgrendeld (vereist een Vocab-streak van ≥ 5):")
                    toon_meting("Ontgrendelde Stam-funderingen", ontgrendeld_stam_ww, tot_stam_ww)
                with c_sluis2:
                    nog_te_gaan = tot_stam_ww - ontgrendeld_stam_ww
                    st.info(f"🔒 Nog **{nog_te_gaan}** werkwoorden te ontgrendelen via het Woorden-tabblad.")

                st.write("---")

                # --- FASERING LEERLIJNEN GRAFIEK ---
                st.markdown("### 📈 Fasering Leerlijnen")
            
                df_plot = pd.DataFrame({
                    'Module': ['Vocabulaire', 'Stamtijden', 'Structuurwoorden'],
                    'Nieuw (0)': [stats_vocab['Nieuw'], stats_stam['Nieuw'], stats_str['Nieuw']],
                    'In Training (1-15)': [stats_vocab['In Training'], stats_stam['In Training'], stats_str['In Training']],
                    'Beheerst (16-29)': [stats_vocab['Beheerst'], stats_stam['Beheerst'], stats_str['Beheerst']],
                    'Mastery (30+)': [stats_vocab['Mastery'], stats_stam['Mastery'], stats_str['Mastery']]
                }).set_index('Module')
                try:
                    st.bar_chart(
                        df_plot,
                        color=['#e0e0e0', '#f6c23e', '#28a745', '#33ccff'],
                        stack=True,
                        height=340,
                    )
                except TypeError:
                    # oudere Streamlit zonder 'stack'-parameter: stapelt standaard al
                    st.bar_chart(df_plot, color=['#e0e0e0', '#f6c23e', '#28a745', '#33ccff'], height=340)
            
                st.write("---")

            # --- JOUW OEFENRITME (kalender-heatmap) ---
            st.subheader("📅 Jouw oefenritme")

            vandaag_str = str(_nu().date())
            vandaag_aantal = int(st.session_state.dag_stats.get(vandaag_str, 0)) if st.session_state.dag_stats else 0
            beheerst_nu = stats_vocab['Beheerst'] + stats_vocab['Mastery']
            in_training_nu = stats_vocab['In Training']
            cs1, cs2, cs3 = st.columns(3)
            cs1.metric("Vandaag geoefend", vandaag_aantal)
            cs2.metric("Woorden 'Beheerst' (streak ≥ 16)", beheerst_nu)
            cs3.metric("Woorden 'In Training'", in_training_nu)
            if vandaag_aantal == 0:
                st.caption("Nog niets geoefend vandaag — een korte sessie houdt je streaks vers.")

            st.markdown(dagkalender_html(st.session_state.get('dag_stats') or {},
                                         (st.session_state.get('dagdoel') or {}).get('log', {})), unsafe_allow_html=True)
            if st.session_state.dag_stats:
                st.metric("Totaal geoefend (All-time)", sum(st.session_state.dag_stats.values()))
            else:
                st.caption("Nog geen oefenhistorie opgebouwd. Begin vandaag!")

            st.write("---")

            # --- COMPETITIE DASHBOARD ---
            st.subheader("🏆 Competitie Dashboard")
            st.caption("Meet je met de groep — **deze week** (wie oefent het hardst?) én **all-time** (wie staat op het hoogste niveau?). Filter op onderdeel om te zien wie waar sterk in is.")
            _ccol1, _ccol2 = st.columns([3, 1])
            _ccol1.caption("Het scorebord ververst automatisch elke ~2 minuten. Klik op *Ververs* voor de allerlaatste stand. Klasgenoten verschijnen zodra zij een keer hebben geoefend en opgeslagen.")
            if _ccol2.button("🔄 Ververs", key="comp_ververs"):
                lees_scorebord.clear()
                st.rerun()
            try:
                # Leest het gedeelde 'Scorebord'-tabblad (samenvattingen per persoon), 2 min gecached.
                _alle = lees_scorebord("scorebord")
                eigen_naam = str(st.session_state.last_user).split('_')[0]
                if _alle:
                    # ontdubbel op naam: houd het profiel met de meeste XP aan
                    _per_naam = {}
                    for _m in _alle:
                        if _m['naam'] not in _per_naam or _m['xp'] > _per_naam[_m['naam']]['xp']:
                            _per_naam[_m['naam']] = _m
                    metrics = list(_per_naam.values())

                    def _mknaam(m):
                        return ("👉 " if m['naam'] == eigen_naam else "") + m['naam']

                    def _podium(lijst, waarde_fn, sub_label):
                        top = lijst[:3]
                        if not top:
                            return
                        med = ["🥇", "🥈", "🥉"]
                        cols = st.columns(len(top))
                        for i, (c, m) in enumerate(zip(cols, top)):
                            ik = (m['naam'] == eigen_naam)
                            c.markdown(
                                f"<div style='text-align:center;padding:6px;border-radius:12px;"
                                f"background:{'rgba(51,204,255,.12)' if ik else 'transparent'}'>"
                                f"<div style='font-size:34px'>{med[i]}</div>"
                                f"<div style='font-weight:700;font-size:17px'>{_mknaam(m)}</div>"
                                f"<div style='color:#33ccff;font-size:22px;font-weight:800'>{waarde_fn(m)}</div>"
                                f"<div style='opacity:.65;font-size:12px'>{sub_label}</div></div>",
                                unsafe_allow_html=True)

                    if metrics:
                        tab_week, tab_all = st.tabs(["📅 Deze week", "🏆 All-time (niveau)"])

                        with tab_week:
                            st.caption("Wie oefende de afgelopen 7 dagen het meest?")
                            wl = sorted([m for m in metrics if m['week'] > 0], key=lambda m: m['week'], reverse=True)
                            if wl:
                                _podium(wl, lambda m: m['week'], "items deze week")
                                st.write("")
                                st.dataframe(pd.DataFrame([
                                    {"#": i, "Speler": _mknaam(m), "Deze week": m['week'],
                                     "Niveau": m['niveau'], "Rang": m['titel']}
                                    for i, m in enumerate(wl, 1)]), width='stretch', hide_index=True)
                            else:
                                st.info("Nog niemand heeft deze week geoefend — wees de eerste! 💪")

                        with tab_all:
                            _ond_opties = {
                                "🏅 Totaal (niveau + XP)": None,
                                "📘 Woorden": "woorden",
                                "🎓 Actief Beheersen": "actief",
                                "⏳ Stamtijden": "stam",
                                "🧱 Structuurwoorden": "struct",
                            }
                            _keuze = st.selectbox("Waarop vergelijken?", list(_ond_opties.keys()), key="comp_onderdeel")
                            _ond = _ond_opties[_keuze]
                            if _ond is None:
                                al = sorted(metrics, key=lambda m: m['xp'], reverse=True)
                                _podium(al, lambda m: f"Lvl {m['niveau']}", "niveau")
                                st.write("")
                                st.dataframe(pd.DataFrame([
                                    {"#": i, "Speler": _mknaam(m), "Niveau": m['niveau'], "Rang": m['titel'],
                                     "XP": m['xp'], "🏅 Badges": m['badges'],
                                     "Actief in": " · ".join(m['gedaan']) or "—"}
                                    for i, m in enumerate(al, 1)]), width='stretch', hide_index=True)
                            else:
                                al = sorted(metrics, key=lambda m: (m['onderdelen'][_ond]['beh'], m['onderdelen'][_ond]['pog']), reverse=True)
                                _podium(al, lambda m: m['onderdelen'][_ond]['beh'], "beheerst")
                                st.write("")
                                st.dataframe(pd.DataFrame([
                                    {"#": i, "Speler": _mknaam(m), "Beheerst": m['onderdelen'][_ond]['beh'],
                                     "Pogingen": m['onderdelen'][_ond]['pog'],
                                     "Niveau": m['niveau'], "Rang": m['titel']}
                                    for i, m in enumerate(al, 1)]), width='stretch', hide_index=True)

                        _mij = next((m for m in metrics if m['naam'] == eigen_naam), None)
                        if _mij:
                            _all_sorted = sorted(metrics, key=lambda m: m['xp'], reverse=True)
                            _pos = [m['naam'] for m in _all_sorted].index(eigen_naam) + 1
                            st.success(
                                f"👉 Jij bent **{eigen_naam}** — Niveau **{_mij['niveau']}** ({_mij['titel']}), "
                                f"**{_mij['xp']} XP**, plek **#{_pos} van {len(metrics)}** all-time · 🏅 {_mij['badges']} badges.")
                    else:
                        st.caption("Nog geen groepsdata om mee te vergelijken. Het scorebord vult zich zodra er is geoefend.")
            except Exception:
                st.caption("Kon de competitiegegevens momenteel niet synchroniseren.")
            
            st.write("---")

            # --- AARTSRIVALEN TOP 5 (Nemesis Tracker) ---
            st.subheader("🐛 Woorden die ik het vaakst fout doe")
            st.caption("Dit zijn de items over álle vakken heen (Woorden, Stamtijden & Structuur) waar je structureel de meeste moeite mee hebt.")
            nemesissen = []
            
            for w in st.session_state.data:
                g = int(w.get('score_goed', 0)); f = int(w.get('score_fout', 0))
                if (g + f) >= 3 and f > 0:
                    nemesissen.append({"Type": "Woord", "Item": w['grieks'], "Betekenis": w['nederlands'], "Fout-ratio": f / (g + f), "Fouten": f})
                    
            if stamtijden_db:
                for w in stamtijden_db:
                    for t_d, vorm in w.get('stamtijden', {}).items():
                        s = st.session_state.stam_stats.get(f"{w['praesens']}_{vorm}", {'g': 0, 'f': 0, 'streak': 0})
                        g, f = s.get('g', 0), s.get('f', 0)
                        if (g + f) >= 3 and f > 0:
                            nemesissen.append({"Type": "Stamtijd", "Item": vorm, "Betekenis": f"{t_d} van {w['praesens']}", "Fout-ratio": f / (g + f), "Fouten": f})

            if str_db:
                for idx_w, w in enumerate(str_db):
                    s = _struct_stat_lookup(st.session_state.struct_stats, w, idx_w)
                    g, f = s.get('g', 0), s.get('f', 0)
                    if (g + f) >= 3 and f > 0:
                        nemesissen.append({"Type": "Structuur", "Item": w['grieks'], "Betekenis": w['betekenis'], "Fout-ratio": f / (g + f), "Fouten": f})
                        
            if nemesissen:
                nemesissen.sort(key=lambda x: (x["Fouten"], x["Fout-ratio"]), reverse=True)
                df_nemesis = pd.DataFrame(nemesissen[:5])
                df_nemesis["Fout-ratio"] = df_nemesis["Fout-ratio"].apply(lambda x: f"{int(x*100)}%")
                st.dataframe(df_nemesis, width='stretch')
                st.error("💡 **Exegese Tip:** Schrijf deze 5 aartsrivalen op een geeltje en plak die op je beeldscherm. Als je déze temt, schiet je totaalscore omhoog!")
            else:
                st.success("🎉 Je hebt op dit moment geen structurele aartsrivalen. Alles loopt op rolletjes!")
                
            st.write("---")

            # --- HARDNEKKIGE PROBLEEMWOORDEN (LEECHES) ---
            st.subheader("🐛 Hardnekkige probleemwoorden")
            st.caption("Woorden die je al meerdere keren hebt geoefend maar die telkens blijven haperen — hoge fout-verhouding én lage streak. Dit zijn je beste kandidaten voor gericht oefenen.")

            leeches = []
            if st.session_state.data:
                for w in st.session_state.data:
                    g = int(w.get('score_goed', 0)); f = int(w.get('score_fout', 0)); s = int(w.get('streak', 0))
                    totaal = g + f
                    # leech-criterium: minstens 3 pogingen, minstens 2 fouten, nog niet 'in training' ontstegen
                    if totaal >= 3 and f >= 2 and s <= 3:
                        ratio = f / totaal
                        if ratio >= 0.4:
                            leeches.append((ratio, f, w))
            leeches.sort(key=lambda x: (x[0], x[1]), reverse=True)

            if leeches:
                st.warning(f"Je hebt **{len(leeches)}** hardnekkige woorden. Kies in *Tabblad 1 → 'Knelpunten (Gericht Oefenen)'* dezelfde lessen om ze gericht te stutten.")
                leech_rijen = []
                for ratio, f, w in leeches[:25]:
                    leech_rijen.append({
                        "Grieks": w.get('grieks', ''),
                        "Betekenis": str(w.get('nederlands', ''))[:35],
                        "Les": w.get('les', ''),
                        "Goed": int(w.get('score_goed', 0)),
                        "Fout": int(w.get('score_fout', 0)),
                        "Streak": int(w.get('streak', 0)),
                        "Fout-%": f"{int(ratio*100)}%",
                    })
                st.dataframe(pd.DataFrame(leech_rijen), use_container_width=True, hide_index=True)
                if len(leeches) > 25:
                    st.caption(f"(Top 25 van {len(leeches)} getoond, gesorteerd op hardnekkigheid.)")
            else:
                st.success("🎉 Geen hardnekkige probleemwoorden — niets blijft structureel haperen. Sterk!")

            st.write("---")

            # --- EXPORTEREN ---
            st.subheader("💾 Exporteer je data")
            df_export = pd.DataFrame(st.session_state.data)[['grieks', 'nederlands', 'streak', 'score_goed', 'score_fout', 'laatst_geoefend']]
            csv = df_export.to_csv(index=False).encode('utf-8')
            st.download_button(label="📥 Download woordenschat als CSV", data=csv, file_name="mijn_grieks_voortgang.csv", mime="text/csv")
            
        # ==========================================
        # TAB 4: ACTIEF BEHEERSEN (PARADIGMA'S)
        # ==========================================
        if _TOON[3]:
         with menu[3]:
            actief_db = laad_actief_db()
            if not actief_db:
                st.warning("Bestand 'actief_beheersen.json' ontbreekt of is niet ingeladen.")
            else:
                with st.expander("⌨️ Spiekbrief: Hoe typ ik Grieks? (Latijnse toetsen)"):
                    sc1, sc2, sc3 = st.columns(3)
                    sc1.markdown("**Klinkers:**\n* `a` = α\n* `e` = ε\n* `h` = η\n* `i` = ι\n* `o` = ο\n* `u` = υ\n* `w` = ω")
                    sc2.markdown("**Medeklinkers:**\n* `b`=β, `g`=γ, `d`=δ, `z`=ζ\n* `k`=κ, `l`=λ, `m`=μ, `n`=ν\n* `p`=π, `r`=ρ, `t`=τ")
                    sc3.markdown("**Bèta-code:**\n* `q` = θ (thèta)\n* `c` = ξ (xi)\n* `f` = φ (phi)\n* `x` = χ (chi)\n* `y` = ψ (psi)\n* `s` = σ (wordt aan het eind ς!)")

                st.subheader("📝 Paradigma's: Analyseren & Reproduceren")

                _af_modi = (["🎮 Leerpad (levels)", "📖 0. Paradigma-paspoort (Bestuderen)", "🎯 1. Focus op Uitgangen", "📝 2. Volledig Tentamenrooster", "⚡ 3. Flashcards (Zwakke plekken)"]
                            if _geav else ["🎮 Leerpad (levels)", "📖 0. Paradigma-paspoort (Bestuderen)"])
                actief_modus = _pref_keuze(st.selectbox, "Oefening:", _af_modi, 'actief_modus')
                st.write("---")

                with st.expander("📂 Kies niveau · categorie · paradigma", expanded=False):
                    niveaus = list(actief_db.keys())
                    gekozen_niv = st.selectbox("Niveau / Boek:", niveaus)
                    categorieen = list(actief_db[gekozen_niv].keys())
                    gekozen_cat = st.selectbox("Categorie:", categorieen)
                    subcats = list(actief_db[gekozen_niv][gekozen_cat].keys())
                    gekozen_sub = st.selectbox("Paradigma:", subcats)

                huidig_paradigma = actief_db[gekozen_niv][gekozen_cat][gekozen_sub]
                st.write("---")

                if "0." in actief_modus:
                    st.markdown(f"### {gekozen_sub}")
                    st.info("💡 **Bestudeer de structuur:** De vaste stam is wit, de variabele uitgang is blauw gekleurd.")
                    
                    cols = st.columns(2)
                    for idx, item in enumerate(huidig_paradigma):
                        with cols[_kolom_index(idx, len(huidig_paradigma))]:
                            stam_html = item.get("stam", "")
                            uitgang_html = f"<span style='color:#33ccff'>{item.get('uitgang', '')}</span>"
                            toelichting = item.get("toelichting", "")
                            
                            st.markdown(f"**{item['label']}**")
                            st.markdown(f"<div style='font-size:24px; font-weight:bold; background-color:#222; padding:10px; border-radius:6px; margin-bottom:5px;'>{stam_html}{uitgang_html}</div>", unsafe_allow_html=True)
                            if toelichting: st.caption(f"_{toelichting}_")
                            st.write("")

                elif "1." in actief_modus:
                    st.markdown(f"### {gekozen_sub} (Alleen uitgangen)")
                    st.write("De stam is al voor je ingevuld. Typ uitsluitend de juiste uitgang!")
                    
                    with st.form("form_focus_uitgangen"):
                        inputs = {}
                        cols = st.columns(2)
                        for idx, item in enumerate(huidig_paradigma):
                            stam = item.get("stam", "")
                            with cols[_kolom_index(idx, len(huidig_paradigma))]:
                                st.markdown(f"**{item['label']}**")
                                c_stam, c_in = st.columns([1, 2])
                                c_stam.markdown(f"<div style='font-size:22px; text-align:right; padding-top:4px;'>{stam} + </div>", unsafe_allow_html=True)
                                inputs[item["id"]] = c_in.text_input("Uitgang", key=f"foc_{item['id']}", label_visibility="collapsed")
                        
                        st.write("")
                        if st.form_submit_button("✓ Nakijken", type="primary"):
                            score = 0; fouten = []
                            for item in huidig_paradigma:
                                verwacht = normaliseer_accent(item.get("uitgang", ""))
                                ingevuld = normaliseer_accent(naar_grieks_transliteratie(inputs[item["id"]]))
                                stam = item.get("stam", "")
                                _goed = (verwacht == ingevuld or (verwacht == "" and ingevuld == ""))
                                _actief_noteer(item.get("id"), _goed)
                                if _goed: score += 1
                                else: fouten.append(f"**{item['label']}:** Verwacht: `{stam}` + `{item.get('uitgang', '')}`, jij typte: `{stam}` + `{ingevuld}`")

                            if score == len(huidig_paradigma):
                                st.success(f"🎉 Perfect! Je hebt alle {score} uitgangen correct!"); st.balloons()
                            else:
                                st.error(f"Je had er {score} van de {len(huidig_paradigma)} goed. Kijk naar je fouten:")
                                for f in fouten: st.write("-", f)
                            trigger_save()

                elif "2." in actief_modus:
                    st.markdown(f"### {gekozen_sub} (Tentamen)")
                    st.write("Typ de volledige vormen. Goede antwoorden worden vastgezet, foute velden worden leeggemaakt voor een nieuwe poging.")
                    
                    if "tent_state" not in st.session_state: st.session_state.tent_state = {}
                    _tent_key = f"{gekozen_niv}|{gekozen_cat}|{gekozen_sub}"
                    if st.session_state.get("tent_para") != _tent_key:
                        st.session_state.tent_state = {item["id"]: {"correct": False, "value": ""} for item in huidig_paradigma}
                        st.session_state.tent_para = _tent_key

                    cols = st.columns(2)
                    huidige_inputs = {}
                    
                    for idx, item in enumerate(huidig_paradigma):
                        with cols[_kolom_index(idx, len(huidig_paradigma))]:
                            i_id = item["id"]
                            state = st.session_state.tent_state.get(i_id, {"correct": False, "value": ""})
                            if state["correct"]: st.success(f"**{item['label']}:** {item['vorm']}")
                            else: huidige_inputs[i_id] = st.text_input(f"**{item['label']}**", value=state["value"], key=f"tent_{i_id}")

                    st.write("")
                    if not all(s["correct"] for s in st.session_state.tent_state.values()):
                        if st.button("✓ Nakijken", type="primary"):
                            for item in huidig_paradigma:
                                i_id = item["id"]
                                if not st.session_state.tent_state[i_id]["correct"]:
                                    ingevuld = normaliseer_accent(naar_grieks_transliteratie(huidige_inputs.get(i_id, "")))
                                    verwacht = normaliseer_accent(item["vorm"])
                                    if ingevuld == verwacht:
                                        st.session_state.tent_state[i_id]["correct"] = True; st.session_state.tent_state[i_id]["value"] = item["vorm"]
                                        _actief_noteer(i_id, True)
                                    else:
                                        st.session_state.tent_state[i_id]["value"] = ""
                                        _actief_noteer(i_id, False)
                            # Volledig foutloos rooster → paradigma als beheerst markeren + zeker opslaan.
                            _tent_klaar = all(s["correct"] for s in st.session_state.tent_state.values())
                            if _tent_klaar:
                                markeer_actief_paradigma(huidig_paradigma)
                            trigger_save(forceer=_tent_klaar)
                            st.rerun()
                    else:
                        st.success("🏆 Geweldig! Je hebt het volledige paradigma foutloos gereproduceerd!")
                        if st.button("Reset Rooster"):
                            st.session_state.tent_state = {item["id"]: {"correct": False, "value": ""} for item in huidig_paradigma}; st.rerun()

                elif "3." in actief_modus:
                    st.markdown(f"### ⚡ Flashcards ({gekozen_sub})")
                    st.write("Overhoor willekeurige losse vormen uit dit paradigma om je snelheid te trainen.")

                    _flash_key = f"{gekozen_niv}|{gekozen_cat}|{gekozen_sub}"
                    if "flash_huidig" not in st.session_state or st.session_state.get("flash_para_id") != _flash_key:
                        st.session_state.flash_para_id = _flash_key
                        st.session_state.flash_huidig = r_engine.choice(huidig_paradigma)
                    
                    # Feedback van de vórige kaart tonen (bovenaan), dan pas de nieuwe vraag.
                    if st.session_state.get('fc_feedback'):
                        _fb = st.session_state.fc_feedback
                        {"success": st.success, "error": st.error}.get(_fb["type"], st.info)(_fb["msg"])
                        st.session_state.fc_feedback = None

                    huidig_fc = st.session_state.flash_huidig
                    st.info(f"Vertaal naar het Grieks: **{gekozen_cat} - {huidig_fc['label']}**")

                    with st.form("fc_form", clear_on_submit=True):
                        fc_in = st.text_input("Griekse vorm:")
                        if st.form_submit_button("✓ Nakijken"):
                            verwacht = normaliseer_accent(huidig_fc["vorm"])
                            ingevuld = normaliseer_accent(naar_grieks_transliteratie(fc_in))
                            if verwacht == ingevuld:
                                _actief_noteer(huidig_fc.get("id"), True)
                                st.session_state.fc_feedback = {"type": "success", "msg": f"✓ Goed! Het was inderdaad **{huidig_fc['vorm']}**."}
                            else:
                                _actief_noteer(huidig_fc.get("id"), False)
                                stam = huidig_fc.get("stam", ""); uitgang = huidig_fc.get("uitgang", ""); toelichting = huidig_fc.get("toelichting", "")
                                st.session_state.fc_feedback = {"type": "error", "msg": f"✗ Fout. Verwacht: **{huidig_fc['vorm']}** (Stam: `{stam}` + Uitgang: `{uitgang}`).\n\n*Tip: {toelichting}*"}
                            # Nieuwe kaart klaarzetten en hertekenen — zo blijven vraag en antwoord in sync.
                            st.session_state.flash_huidig = r_engine.choice(huidig_paradigma)
                            trigger_save(); st.rerun()

                elif "Leerpad" in actief_modus:
                    # === LEERPAD: elke cel individueel leren (flashcard → meerkeuze → typen), en pas
                    # het HELE rijtje ('grote cel') zodra alle cellen de beheers-drempel halen. ===
                    # LET OP: dezelfde drempel als actief_level_status/markeer_actief_paradigma (ACTIEF_BEHEERST),
                    # anders is de meesterproef onbereikbaar en slaat de retentie-herhaling nooit aan.
                    _af_levels = actief_level_status(bouw_actief_levels(actief_db), st.session_state.actief_stats)
                    _af_niv = niveau_van_xp(bereken_xp_actief(st.session_state.actief_stats))
                    _af_vol = sum(1 for l in _af_levels if l['voltooid'])
                    st.markdown(f"#### 🎮 Niveau {_af_niv['niveau']} · {_af_niv['titel']} — {_af_niv['xp_totaal']} XP")
                    st.progress(_af_niv['xp_in_niveau'] / max(1, _af_niv['xp_voor_volgend']))
                    _af_aanbev = next((l for l in _af_levels if l['ontgrendeld'] and not l['voltooid']), None)
                    st.caption(f"🏁 {_af_vol}/{len(_af_levels)} paradigma's beheerst.")

                    # Automatisch doorlopen: pak steeds vanzelf het eerstvolgende nog niet beheerste
                    # paradigma, zodat je lekker kunt doorleren zonder telkens te selecteren.
                    _af_auto = _pref_bool(st.toggle, "▶️ Automatisch doorlopen naar het volgende paradigma", 'actief_auto', default=True)
                    if _af_auto:
                        if _af_aanbev:
                            gekozen_niv = _af_aanbev['niveau']; gekozen_cat = _af_aanbev['categorie']; gekozen_sub = _af_aanbev['sub']
                            huidig_paradigma = actief_db[gekozen_niv][gekozen_cat][gekozen_sub]
                            st.info(f"▶️ Bezig met **{gekozen_sub}** ({gekozen_niv}). Zodra dit rijtje beheerst is, gaat de app vanzelf door naar het volgende.")
                        else:
                            st.success("🎉 Alle paradigma's beheerst! Zet 'Automatisch doorlopen' uit om er zelf een te herhalen.")
                            huidig_paradigma = []
                    else:
                        st.caption(f"Handmatig — kies hierboven een paradigma." + (f" (aanbevolen: **{_af_aanbev['titel']}**)" if _af_aanbev else ""))

                    cells = [c for c in huidig_paradigma if c.get('id')]
                    def _cstreak(_c): return int((st.session_state.actief_stats.get(_c['id']) or {}).get('streak', 0))
                    # Index van ALLE cellen over álle paradigma's — nodig om al beheerste rijtjes
                    # als retentie-herhaling terug te laten komen (blijft er zo goed in zitten).
                    _alle_cel_idx = {}   # id -> cel
                    _alle_cel_sib = {}   # id -> [vormen in eigen paradigma] (voor MC-afleiders)
                    _alle_cel_par = {}   # id -> paradigma-naam (welk rijtje) — voorkomt verwarring
                    for _nvv in actief_db.values():
                        for _catt in _nvv.values():
                            for _para_naam, _para in _catt.items():
                                _vv = [x['vorm'] for x in _para if x.get('id')]
                                for x in _para:
                                    if x.get('id'):
                                        _alle_cel_idx[x['id']] = x; _alle_cel_sib[x['id']] = _vv
                                        _alle_cel_par[x['id']] = _para_naam
                    _klaar20 = sum(1 for c in cells if _cstreak(c) >= ACTIEF_BEHEERST)
                    st.markdown(f"### {gekozen_sub}  ({_klaar20}/{len(cells)} cellen beheerst)")

                    with st.expander("📖 Bekijk het rijtje", expanded=(_klaar20 == 0)):
                        for c in cells:
                            st.markdown(f"- **{c['label']}** — {c.get('stam','')}:blue[{c.get('uitgang','')}]")

                    if st.session_state.get('af_feedback'):
                        _fb = st.session_state.af_feedback
                        {"success": st.success, "warning": st.warning}.get(_fb["type"], st.error)(_fb["msg"])
                        st.session_state.af_feedback = None

                    def _af_score(_cid, _delta, _goed):
                        _rec = st.session_state.actief_stats.setdefault(_cid, {'g': 0, 'f': 0, 'streak': 0})
                        if _goed: _rec['g'] = int(_rec.get('g', 0)) + 1
                        else: _rec['f'] = int(_rec.get('f', 0)) + 1
                        _rec['streak'] = max(0, int(_rec.get('streak', 0)) + _delta)

                    _pkey = f"{gekozen_niv}|{gekozen_cat}|{gekozen_sub}"

                    if cells and all(_cstreak(c) >= ACTIEF_BEHEERST for c in cells):
                        # MEESTERPROEF: het hele rijtje in één keer reproduceren.
                        st.success("💪 Alle cellen beheerst — meesterproef: reproduceer het hele rijtje.")
                        if st.session_state.get('actief_lp_key') != _pkey:
                            st.session_state.actief_lp_state = {c['id']: {"correct": False, "value": ""} for c in cells}
                            st.session_state.actief_lp_key = _pkey
                        _cols = st.columns(2); _inp = {}
                        for _i, c in enumerate(cells):
                            with _cols[_kolom_index(_i, len(cells))]:
                                _s = st.session_state.actief_lp_state.get(c['id'], {"correct": False, "value": ""})
                                if _s["correct"]: st.success(f"**{c['label']}:** {c['vorm']}")
                                else: _inp[c['id']] = st.text_input(f"**{c['label']}**", value=_s["value"], key=f"lpm_{c['id']}")
                        if not all(s["correct"] for s in st.session_state.actief_lp_state.values()):
                            if st.button("✓ Nakijken", type="primary", key="lpm_nakijk"):
                                for c in cells:
                                    if not st.session_state.actief_lp_state[c['id']]["correct"]:
                                        if grieks_vorm_ok(_inp.get(c['id'], ""), c['vorm']):
                                            st.session_state.actief_lp_state[c['id']] = {"correct": True, "value": c['vorm']}
                                        else:
                                            st.session_state.actief_lp_state[c['id']]["value"] = ""
                                            st.session_state.pop(f"lpm_{c['id']}", None)   # veld echt legen
                                st.rerun()
                        else:
                            st.success("🏆 Volledig foutloos — dit paradigma zit écht vast!")
                            st.balloons()
                            if st.button("🔄 Opnieuw", key="lpm_reset"):
                                st.session_state.actief_lp_state = {c['id']: {"correct": False, "value": ""} for c in cells}
                                for c in cells: st.session_state.pop(f"lpm_{c['id']}", None)   # velden echt legen
                                st.rerun()
                    else:
                        # PER-CEL SCAFFOLD: bouw een rij kaarten op basis van de streak per cel.
                        def _bouw_q():
                            _q = []
                            for c in cells:
                                s = _cstreak(c)
                                if s >= ACTIEF_BEHEERST: continue
                                if s <= 0: _q.append((c['id'], 'Leer')); _q.append((c['id'], 'MC'))
                                elif s <= 9: _q.append((c['id'], 'MC'))
                                else: _q.append((c['id'], 'Typen'))
                            # Retentie: meng een paar al beheerste cellen uit ándere paradigma's erdoorheen,
                            # zodat oude stof erin blijft zitten.
                            _huidige_ids = {c['id'] for c in cells}
                            _beheerst = [cid for cid in _alle_cel_idx
                                         if cid not in _huidige_ids
                                         and int((st.session_state.actief_stats.get(cid) or {}).get('streak', 0)) >= ACTIEF_BEHEERST]
                            if _beheerst and _q:
                                _n = min(3, len(_beheerst))
                                _herhaal = r_engine.sample(_beheerst, _n)
                                _stap = max(1, len(_q) // (_n + 1))
                                for _i, _rid in enumerate(_herhaal):
                                    _q.insert(min(len(_q), _stap * (_i + 1) + _i), (_rid, 'Herhaal'))
                            elif _beheerst:
                                # Niets nieuws meer te leren in dit rijtje → puur herhaal-modus van oude stof.
                                _n = min(8, len(_beheerst))
                                _q = [(rid, 'Herhaal') for rid in r_engine.sample(_beheerst, _n)]
                            return _q
                        if st.session_state.get('af_qkey') != _pkey or not st.session_state.get('af_q'):
                            st.session_state.af_q = _bouw_q()
                            st.session_state.af_qkey = _pkey
                            st.session_state.af_opties = None
                        _q = st.session_state.af_q
                        if not _q:
                            st.info("Geen cellen te oefenen in dit paradigma.")
                        else:
                            cid, sub = _q[0]
                            # Eerst in het HUIDIGE paradigma zoeken: 59 cel-ids komen in meerdere
                            # paradigma's voor, dus de globale index mag alleen als terugval dienen
                            # (anders krijg je de vorm van een ander rijtje te zien én beoordeeld).
                            cell = next((c for c in cells if c['id'] == cid), None) or _alle_cel_idx.get(cid)
                            if cell is None:
                                _q.pop(0); st.rerun()
                            _slabel = {'Leer': '🧠 Leer', 'MC': '🔢 Meerkeuze', 'Typen': '⌨️ Typen', 'Herhaal': '🔁 Herhaling (oude stof)'}.get(sub, sub)
                            _celpar = _alle_cel_par.get(cid, gekozen_sub)   # welk rijtje deze cel hoort bij
                            _arec = st.session_state.actief_stats.get(cid) or {}
                            st.caption(f"{_slabel} · ✅ {int(_arec.get('g', 0))} / ❌ {int(_arec.get('f', 0))} · "
                                       f"🔥 streak {_cstreak(cell)}/{ACTIEF_BEHEERST} · nog {len(_q)} kaart(en) in de rij")
                            if sub == 'Herhaal':
                                st.caption("↩️ Herhaling van oude stof — even ophalen zodat het erin blijft zitten.")
                            # Paradigma NAAST het cel-label, zodat 'Gen ev van ἐγώ' niet met 'Gen ev van σύ' verwart.
                            st.markdown(f"<div class='grieks-woord' style='font-size:30px'>{cell['label']} "
                                        f"<span style='font-size:17px;color:#9aa3af;font-weight:400'>van {_celpar}</span></div>",
                                        unsafe_allow_html=True)

                            def _volgende(requeue=False):
                                if requeue and _q: _q.append(_q[0])
                                if _q: _q.pop(0)
                                st.session_state.af_opties = None

                            if sub == 'Leer':
                                if cell.get('uitgang'):
                                    _antw = f"{cell.get('stam','')}**{cell['uitgang']}** = **{cell['vorm']}**"
                                else:
                                    _antw = f"**{cell['vorm']}**"
                                st.info(f"**{cell['label']}** → {_antw}"
                                        + (f"  \n_{cell.get('toelichting','')}_" if cell.get('toelichting') else ""))
                                if st.button("Volgende", type="primary", key=f"afl_{cid}"):
                                    _volgende(); st.rerun()
                            elif sub == 'MC':
                                if not st.session_state.get('af_opties'):
                                    _pool = list({v for v in _alle_cel_sib.get(cid, [c['vorm'] for c in cells]) if v != cell['vorm']})
                                    r_engine.shuffle(_pool)
                                    _opts = [cell['vorm']] + _pool[:3]
                                    r_engine.shuffle(_opts)
                                    st.session_state.af_opties = _opts
                                _mcols = st.columns(2)
                                for _oi, _opt in enumerate(st.session_state.af_opties):
                                    if _mcols[_oi % 2].button(_opt, key=f"afm_{cid}_{_oi}"):
                                        if _opt == cell['vorm']:
                                            _af_score(cid, 2, True); dagdoel_plus('actief'); st.session_state.af_feedback = {"type": "success", "msg": f"✓ Goed! {_celpar} · {cell['label']} = {cell['vorm']}"}; _volgende()
                                        else:
                                            _af_score(cid, -2, False); st.session_state.af_feedback = {"type": "error", "msg": f"✗ {_celpar} · {cell['label']} = **{cell['vorm']}** (jij koos {_opt})"}; _volgende(requeue=True)
                                        trigger_save(); st.rerun()
                            else:  # Typen
                                forceer_focus()
                                with st.form(f"aft_{cid}", clear_on_submit=True):
                                    _in = st.text_input("Typ de vorm (Latijnse toetsen mag):")
                                    if st.form_submit_button("✓ Nakijken", type="primary"):
                                        if grieks_vorm_ok(_in, cell['vorm']):
                                            _af_score(cid, 4, True); dagdoel_plus('actief'); st.session_state.af_feedback = {"type": "success", "msg": f"✓ Goed! {_celpar} · {cell['label']} = {cell['vorm']}"}; _volgende()
                                        else:
                                            _af_score(cid, -2, False); st.session_state.af_feedback = {"type": "error", "msg": f"✗ {_celpar} · {cell['label']} = **{cell['vorm']}**"}; _volgende(requeue=True)
                                        trigger_save(); st.rerun()

                            # 'Ik weet het niet' — toont het antwoord zonder aftrek en zet de kaart weer
                            # achteraan in de rij, zodat je 'm straks nog een keer echt ophaalt.
                            if sub != 'Leer':
                                if st.button("🤔 Ik weet het niet — toon het antwoord", key=f"afweet_{cid}"):
                                    st.session_state.af_feedback = {"type": "info", "msg": f"💡 {_celpar} · {cell['label']} = **{cell['vorm']}** — geen aftrek, je krijgt 'm zo nog een keer."}
                                    _volgende(requeue=True); st.rerun()

                    with st.expander("🗺️ Alle paradigma-levels"):
                        for l in _af_levels:
                            _ico = "✅" if l['voltooid'] else ("▶️" if l['ontgrendeld'] else "🔒")
                            st.markdown(f"{_ico} **{l['index']}.** {l['titel']} — {l['klaar']}/{l['totaal']}")

        # ==========================================
        # TAB 5: STAMTIJDEN
        # ==========================================
        if _TOON[4]:
         with menu[4]:
            stamtijden_db = laad_stamtijden_db()
            bijbel_db = laad_bijbel_db()
            
            if not stamtijden_db: st.warning("Bestand 'stamtijden_verrijkt.json' ontbreekt.")
            else:
                with st.expander("⌨️ Spiekbrief: Hoe typ ik Grieks? (Latijnse toetsen)"):
                    sc1, sc2, sc3 = st.columns(3)
                    sc1.markdown("**Klinkers:**\n* `a` = α, `e` = ε, `h` = η\n* `i` = ι, `o` = ο, `u` = υ, `w` = ω")
                    sc2.markdown("**Medeklinkers:**\n* `b`=β, `g`=γ, `d`=δ, `z`=ζ\n* `k`=κ, `l`=λ, `m`=μ, `n`=ν\n* `p`=π, `r`=ρ, `t`=τ")
                    sc3.markdown("**Bèta-code:**\n* `q` = θ (thèta)\n* `c` = ξ (xi)\n* `f` = φ (phi)\n* `x` = χ (chi)\n* `y` = ψ (psi)\n* `s` = σ (wordt aan het eind ς!)")

                st.subheader("⏳ Stamtijden: Overzien, Herleiden & Trainen")
                # Eerst WAT je oefent (standaard het Leerpad); de oefenvorm (MC/typen) kies je
                # bij de sessie-instellingen - standaard bepaalt de app die zelf.
                _stam_modi = (["🎮 Leerpad (levels)", "🧠 Leer (flashcards)",
                               "📖 Werkwoordpaspoort", "🔎 Herkennen (koud)"]
                              if _geav else ["🎮 Leerpad (levels)", "🧠 Leer (flashcards)"])
                stam_modus = _pref_keuze(st.selectbox, "Oefening:", _stam_modi, 'stam_modus')
                st.write("---")

                if "Werkwoordpaspoort" in stam_modus:
                    st.markdown("### 📖 Morfologisch Paspoort")
                    alle_lessen_p = sorted(list(set(i.get('les', 0) for i in stamtijden_db if i.get('les', 0) > 0)))
                    pas_les = st.selectbox("Selecteer uit les:", alle_lessen_p)
                    
                    ww_in_les = [w for w in stamtijden_db if w.get('les') == pas_les]
                    gekozen_pas_ww = st.selectbox("Kies het werkwoord:", [w['praesens'] for w in ww_in_les])
                    
                    for w in ww_in_les:
                        if w['praesens'] == gekozen_pas_ww:
                            morf = w.get('morfologie', {}); regel = morf.get('mutatieregel', {})
                            st.markdown(f"<div class='grieks-woord' style='font_size:45px;'>{w['praesens']}</div>", unsafe_allow_html=True)
                            st.markdown(f"<h4 style='text-align:center; color:#aaaaaa;'>\"{w['betekenis']}\"</h4>", unsafe_allow_html=True)
                            
                            c_b1, c_b2, c_b3, c_b4 = st.columns(4)
                            c_b1.info(f"**Klasse:** {morf.get('klasse', 'onbekend').capitalize()}")
                            c_b2.warning(f"**Stamwortel:** {morf.get('stamwortel', '-')}")
                            c_b3.success(f"**Strong:** {w.get('strong_nummer', '-')}")
                            c_b4.error(f"**Type:** {'Uitzondering (Stampen)' if morf.get('memoriseren_vereist') else 'Regelmatig (Herleidbaar)'}")
                            
                            st.write("---")
                            st.markdown("#### 🏛️ De 6 Stamtijden")
                            st_grid = [
                                ("1. Praesens", w['praesens'], "Praesens"),
                                ("2. Futurum", w.get('stamtijden', {}).get("Futurum Actief/Medium", "-"), "Futurum Actief/Medium"),
                                ("3. Aoristus", w.get('stamtijden', {}).get("Aoristus Actief/Medium", "-"), "Aoristus Actief/Medium"),
                                ("4. Perfectum Act.", w.get('stamtijden', {}).get("Perfectum Actief", "-"), "Perfectum Actief"),
                                ("5. Perfectum M/P", w.get('stamtijden', {}).get("Perfectum Medium/Passief", "-"), "Perfectum Medium/Passief"),
                                ("6. Aoristus Pass.", w.get('stamtijden', {}).get("Aoristus Passief", "-"), "Aoristus Passief")
                            ]
                            
                            g_cols = st.columns(3)
                            for idx, (titel, svorm, t_diathese) in enumerate(st_grid):
                                with g_cols[idx % 3]:
                                    st.markdown(f"<div class='grid-label'>{titel}</div>", unsafe_allow_html=True)
                                    if svorm != "-":
                                        dstam, duit = deconstrueer_stamtijd_live(svorm, t_diathese, w['praesens'])
                                        gekleurd_html = f"{dstam}<span style='color:#33ccff'>{duit}</span>" if duit else svorm
                                    else: gekleurd_html = "-"
                                    st.markdown(f"<div style='font-size:22px; font-weight:bold; color:#fff; background-color:#222; padding:10px; border-radius:6px; text-align:center; margin-bottom:15px;'>{gekleurd_html}</div>", unsafe_allow_html=True)

                            st.markdown("#### ⚙️ Wat er per stamtijd met de klanken gebeurt")
                            st.caption("Per vorm afgeleid uit de vorm zélf: augment, reduplicatie, σ-samensmelting of klinkerrekking.")
                            for _titel, _sv, _td in st_grid[1:]:
                                if not _stam_vorm_ok(_sv):
                                    continue
                                _ds2, _du2 = deconstrueer_stamtijd_live(_sv, _td, w['praesens'])
                                _kop = f"{_ds2}**{_du2}**" if _du2 else f"**{_sv}**"
                                st.markdown(f"**{_titel}** · {_kop}")
                                for _r in stamtijd_opbouw_regels(_sv, _td, w):
                                    st.markdown("  - " + _r)

                elif "flashcards" in stam_modus:
                    # === LEER-MODUS: rustige flashcards, vorm -> (zelf benoemen) -> antwoord tonen ===
                    st.markdown("### 🧠 Leer-modus (flashcards)")
                    st.caption("Bekijk de vorm, benoem in gedachten wélke tijd het is en van wélk praesens (+ betekenis) hij komt, en check jezelf. Geen punten-druk — puur om de stamtijden in te slijpen. Wat je 'nog niet' wist komt achteraan opnieuw.")
                    _tijden_fc = ["Futurum Actief/Medium", "Aoristus Actief/Medium", "Aoristus Passief", "Perfectum Actief", "Perfectum Medium/Passief"]

                    fc1, fc2 = st.columns([1, 2])
                    with fc1:
                        alle_lessen_fc = sorted(set(i.get('les', 0) for i in stamtijden_db if i.get('les', 0) > 0))
                        gekozen_fc = st.multiselect("Kies les(sen):", alle_lessen_fc, default=alle_lessen_fc[:1], key="fc_lessen")
                        fc_focus = st.radio("Welke werkwoorden:", ["Alle", "🔥 Alleen onregelmatige (suppletie)"], key="fc_focus")
                        pool_fc = [w for w in stamtijden_db if w.get('les', 0) in gekozen_fc]
                        if "onregelmatige" in fc_focus:
                            pool_fc = [w for w in pool_fc if w.get('morfologie', {}).get('memoriseren_vereist')]

                        groep = st.radio("Leer stap voor stap:",
                                         ["🔤 Per werkwoord (mét overzicht)", "⏳ Per tijd", "🔀 Alles door elkaar"],
                                         key="fc_group",
                                         help="Per werkwoord: eerst het hele rijtje van één werkwoord bekijken, daarna oefenen. Per tijd: alleen één tijd (bv. aoristus) over alle gekozen werkwoorden. Alles: alle vormen gehusseld.")
                        fc_incl_prae = st.checkbox("Praesens zelf ook als kaart tonen", value=True, key="fc_incl_prae")

                        def _maak_kaart(w, tijd):
                            vorm = w['praesens'] if tijd == "Praesens" else w.get('stamtijden', {}).get(tijd)
                            return {"basis": w, "tijd": tijd, "vorm": vorm} if (tijd == "Praesens" or _stam_vorm_ok(vorm)) else None

                        gekozen_ww = None
                        if groep.startswith("🔤"):
                            if pool_fc:
                                _labels_ww = [f"{w['praesens']} — {w['betekenis']}" for w in pool_fc]
                                _sel_ww = st.selectbox("Kies werkwoord:", _labels_ww, key="fc_ww")
                                gekozen_ww = pool_fc[_labels_ww.index(_sel_ww)]
                            reeks = (["Praesens"] if fc_incl_prae else []) + _tijden_fc
                            items_fc = [k for k in (_maak_kaart(gekozen_ww, t) for t in reeks) if k] if gekozen_ww else []
                        elif groep.startswith("⏳"):
                            gekozen_tijd = st.selectbox("Kies tijd/diathese:", _tijden_fc, key="fc_tijd")
                            items_fc = [k for k in (_maak_kaart(w, gekozen_tijd) for w in pool_fc) if k]
                        else:
                            reeks = (["Praesens"] if fc_incl_prae else []) + _tijden_fc
                            items_fc = [k for w in pool_fc for k in (_maak_kaart(w, t) for t in reeks) if k]

                        st.caption(f"🃏 {len(items_fc)} kaarten in deze selectie.")

                        if st.button("Start", type="primary", use_container_width=True, key="fc_start"):
                            _per_ww = groep.startswith("🔤")
                            if not _per_ww:
                                r_engine.shuffle(items_fc)
                            st.session_state.stam_fc_queue = list(items_fc)
                            st.session_state.stam_fc_totaal = len(items_fc)
                            st.session_state.stam_fc_gedaan = 0
                            st.session_state.stam_fc_goed = 0
                            st.session_state.stam_fc_huidig = items_fc[0] if items_fc else None
                            st.session_state.stam_fc_onthuld = False
                            st.session_state.stam_fc_overzicht = _per_ww  # per werkwoord: eerst het overzicht
                            st.rerun()

                        if st.session_state.get("stam_fc_totaal"):
                            _tot = st.session_state.get("stam_fc_totaal", 0)
                            _ged = st.session_state.get("stam_fc_gedaan", 0)
                            st.progress(min(1.0, _ged / _tot) if _tot else 0.0)
                            st.caption(f"{_ged} bekeken · {st.session_state.get('stam_fc_goed', 0)} in één keer goed.")

                    with fc2:
                        h = st.session_state.get("stam_fc_huidig")
                        if not h:
                            if st.session_state.get("stam_fc_totaal") and st.session_state.get("stam_fc_gedaan"):
                                st.success("🎉 Alle kaarten gehad! Klik links op **Start / schud kaarten** voor een nieuwe ronde.")
                            else:
                                st.info("Kies links je lessen en klik op **Start**.")
                        elif st.session_state.get("stam_fc_overzicht"):
                            # LEREN VANUIT OVERZICHT: eerst de hele rij van dit werkwoord bekijken
                            _b = h["basis"]; _morf = _b.get("morfologie", {}); _regel = _morf.get("mutatieregel", {})
                            st.markdown("#### 📖 Bekijk eerst het hele rijtje")
                            st.markdown(f"<div class='grieks-woord' style='font-size:40px;'>{_b['praesens']}</div>", unsafe_allow_html=True)
                            st.markdown(f"<h4 style='text-align:center;color:#aaa;'>\"{_b['betekenis']}\"</h4>", unsafe_allow_html=True)
                            _grid = [("1. Praesens", _b['praesens'], "Praesens")] + \
                                    [(f"{_i+2}. {_t.split(' ')[0]}", _b.get('stamtijden', {}).get(_t, '-'), _t) for _i, _t in enumerate(_tijden_fc)]
                            _cols_ov = st.columns(3)
                            for _i, (_lab, _v, _td) in enumerate(_grid):
                                with _cols_ov[_i % 3]:
                                    st.markdown(f"<div class='grid-label'>{_lab}</div>", unsafe_allow_html=True)
                                    if _v and _v != "-":
                                        _ds, _du = deconstrueer_stamtijd_live(_v, _td, _b['praesens'])
                                        _hh = f"{_ds}<span style='color:#33ccff'>{_du}</span>" if _du else _v
                                    else:
                                        _hh = "-"
                                    st.markdown(f"<div style='font-size:20px;font-weight:bold;color:#fff;background:#222;padding:8px;border-radius:6px;text-align:center;margin-bottom:12px;'>{_hh}</div>", unsafe_allow_html=True)
                            with st.expander("⚙️ Wat er per stamtijd met de klanken gebeurt", expanded=False):
                                for _lab, _v, _td in _grid[1:]:
                                    if not _stam_vorm_ok(_v):
                                        continue
                                    st.markdown(f"**{_lab}** · {_v}")
                                    for _r in stamtijd_opbouw_regels(_v, _td, _b):
                                        st.markdown("  - " + _r)
                            if st.button("▶️ Ik heb het bekeken — start met oefenen", type="primary", use_container_width=True, key="fc_go"):
                                st.session_state.stam_fc_overzicht = False
                                st.rerun()
                        else:
                            basis = h["basis"]; morf = basis.get("morfologie", {}); regel = morf.get("mutatieregel", {})
                            st.markdown(f"<div class='grieks-woord' style='font-size:48px; text-align:center;'>{h['vorm']}</div>", unsafe_allow_html=True)
                            if not st.session_state.get("stam_fc_onthuld"):
                                st.caption("Welke tijd/diathese is dit? En van welk praesens (+ betekenis)?")
                                if st.button("👁️ Toon antwoord", use_container_width=True, key="fc_reveal"):
                                    st.session_state.stam_fc_onthuld = True; st.rerun()
                            else:
                                if h["tijd"] == "Praesens":
                                    st.success(f"**Praesens** van **{basis['praesens']}** — *{basis['betekenis']}*")
                                else:
                                    dstam, duit = deconstrueer_stamtijd_live(h["vorm"], h["tijd"], basis['praesens'])
                                    _vh = f"**{dstam}**:blue[**{duit}**]" if duit else f"**{h['vorm']}**"
                                    st.success(f"{_vh}\n\n**{h['tijd']}** van **{basis['praesens']}** — *{basis['betekenis']}*")
                                if h["tijd"] != "Praesens":
                                    st.info("💡 **Zo is deze vorm opgebouwd:**\n\n"
                                            + "\n".join("- " + _r for _r in stamtijd_opbouw_regels(h["vorm"], h["tijd"], basis)))
                                elif morf.get("memoriseren_vereist"):
                                    st.warning(f"🔥 **Onregelmatig (suppletie):** {regel.get('toelichting', 'Puur memoriseren.')}")

                                _adv = None
                                cok, cno = st.columns(2)
                                if cok.button("✅ Wist ik", use_container_width=True, key="fc_ok"):
                                    _adv = True
                                if cno.button("❌ Nog niet", use_container_width=True, key="fc_no"):
                                    _adv = False
                                if _adv is not None:
                                    vid = f"{basis['praesens']}_{h['vorm']}"
                                    stt = st.session_state.stam_stats.setdefault(vid, {'g': 0, 'f': 0, 'streak': 0})
                                    registreer_oefening()
                                    q = st.session_state.get("stam_fc_queue", [])
                                    if _adv:
                                        stt['g'] = int(stt.get('g', 0)) + 1
                                        stt['streak'] = int(stt.get('streak', 0)) + 1
                                        st.session_state.stam_fc_goed = st.session_state.get("stam_fc_goed", 0) + 1
                                    else:
                                        stt['f'] = int(stt.get('f', 0)) + 1
                                        if h not in q[1:]:
                                            q.append(h)  # nog-niet-geweten kaart achteraan opnieuw
                                    if q:
                                        q.pop(0)
                                    st.session_state.stam_fc_gedaan = st.session_state.get("stam_fc_gedaan", 0) + 1
                                    st.session_state.stam_fc_huidig = q[0] if q else None
                                    st.session_state.stam_fc_onthuld = False
                                    trigger_save()
                                    st.rerun()

                elif "Herkennen" in stam_modus:
                    # === KOUDE HERKENNING: vorm -> welk werkwoord (lemma) + welke tijd ===
                    st.markdown("### 🔎 Koude herkenning")
                    st.caption("Je krijgt één losse stamtijd-vorm te zien, zónder dat je weet uit welk werkwoord hij komt — precies zoals bij het lezen van een tekst. Werk terug naar het praesens (lemma) en de tijd.")

                    kc1, kc2 = st.columns([1, 2])
                    with kc1:
                        # Bronfilter: alle werkwoorden, of alleen de onregelmatige 'hall of pain'
                        focus = st.radio(
                            "Oefenselectie:",
                            ["📚 Uit geselecteerde lessen", "🔥 Alleen onregelmatige (suppletie)", "🌍 Alle werkwoorden"],
                            key="kh_focus"
                        )
                        antwoordvorm = st.radio(
                            "Antwoordvorm:",
                            ["🔢 Meerkeuze (herkennen)", "⌨️ Typen (reproduceren)"],
                            key="kh_antwoordvorm"
                        )

                        kh_pool = []
                        if focus == "📚 Uit geselecteerde lessen":
                            alle_lessen_kh = sorted(list(set(i.get('les', 0) for i in stamtijden_db if i.get('les', 0) > 0)))
                            gekozen_kh_lessen = st.multiselect("Kies les(sen):", alle_lessen_kh, default=alle_lessen_kh[:2] if alle_lessen_kh else [], key="kh_lessen")
                            kh_pool = [w for w in stamtijden_db if w.get('les', 0) in gekozen_kh_lessen]
                        elif focus == "🔥 Alleen onregelmatige (suppletie)":
                            kh_pool = [w for w in stamtijden_db if w.get('morfologie', {}).get('memoriseren_vereist')]
                            st.caption(f"🔥 {len(kh_pool)} onregelmatige werkwoorden in de database. Dit zijn de vormen die geen klankwet volgen en die je puur uit het hoofd moet kennen.")
                        else:
                            kh_pool = list(stamtijden_db)

                        # bouw alle (werkwoord, tijd, vorm)-combinaties
                        alle_tijden = ["Futurum Actief/Medium", "Aoristus Actief/Medium", "Aoristus Passief", "Perfectum Actief", "Perfectum Medium/Passief"]
                        kh_items = []
                        for w in kh_pool:
                            for t_d in alle_tijden:
                                vorm = w.get('stamtijden', {}).get(t_d)
                                if _stam_vorm_ok(vorm):
                                    kh_items.append({"basis": w, "tijd": t_d, "vorm": vorm})

                        st.caption(f"Beschikbare vormen om te herkennen: **{len(kh_items)}**")

                        if st.button("Start / volgende vorm", key="kh_start", type="primary", use_container_width=True):
                            if kh_items:
                                st.session_state.kh_huidig = r_engine.choice(kh_items)
                                st.session_state.kh_opties = None
                                st.session_state.kh_onthuld = False
                                st.session_state.kh_gecheckt = False
                            else:
                                st.session_state.kh_huidig = None
                            st.rerun()

                        if st.session_state.get("kh_score_totaal"):
                            st.metric("Deze sessie", f"{st.session_state.get('kh_score_goed',0)}/{st.session_state.get('kh_score_totaal',0)} goed")

                    with kc2:
                        huidig_kh = st.session_state.get("kh_huidig")
                        if not huidig_kh:
                            st.info("Kies links je selectie en klik op **Start / volgende vorm**.")
                        else:
                            basis = huidig_kh["basis"]
                            correct_prae = basis["praesens"]
                            correct_bet = basis["betekenis"]
                            correct_tijd = huidig_kh["tijd"]
                            vorm = huidig_kh["vorm"]
                            is_suppletie = basis.get("morfologie", {}).get("memoriseren_vereist", False)

                            st.markdown(f"<div class='grieks-woord' style='font-size:46px; text-align:center;'>{vorm}</div>", unsafe_allow_html=True)
                            st.caption("Uit welk werkwoord komt deze vorm, en welke tijd is het?")

                            # ---- MEERKEUZE ----
                            if antwoordvorm.startswith("🔢"):
                                if not st.session_state.get("kh_opties"):
                                    # afleiders uit de HELE database (koude herkenning: geen 'bekende pool'-hint)
                                    correct_optie = f"{correct_prae} — {correct_bet}"
                                    pool_andere = [w for w in stamtijden_db if w["praesens"] != correct_prae]
                                    r_engine.shuffle(pool_andere)
                                    afl, gezien = [], {correct_bet}
                                    for w in pool_andere:
                                        if w["betekenis"] not in gezien:
                                            afl.append(f"{w['praesens']} — {w['betekenis']}"); gezien.add(w["betekenis"])
                                        if len(afl) >= 3: break
                                    opties_lemma = [correct_optie] + afl
                                    r_engine.shuffle(opties_lemma)
                                    st.session_state.kh_opties = opties_lemma

                                with st.form("kh_mc_form"):
                                    keuze_lemma = st.radio("Welk werkwoord?", st.session_state.kh_opties, index=None)
                                    afleiders_t = [t for t in alle_tijden if t != correct_tijd]
                                    opties_tijd = [correct_tijd] + r_engine.sample(afleiders_t, min(3, len(afleiders_t)))
                                    opties_tijd = sorted(set(opties_tijd))
                                    keuze_tijd = st.radio("Welke tijd?", opties_tijd, index=None)
                                    if st.form_submit_button("✓ Nakijken", type="primary"):
                                        registreer_oefening()
                                        goed_lemma = (keuze_lemma == f"{correct_prae} — {correct_bet}")
                                        goed_tijd = (keuze_tijd == correct_tijd)
                                        st.session_state.kh_score_totaal = st.session_state.get("kh_score_totaal", 0) + 1
                                        if goed_lemma and goed_tijd:
                                            st.session_state.kh_score_goed = st.session_state.get("kh_score_goed", 0) + 1
                                        st.session_state.kh_gecheckt = True
                                        st.session_state.kh_res = (goed_lemma, goed_tijd)
                                        st.rerun()

                                if st.session_state.get("kh_gecheckt"):
                                    goed_lemma, goed_tijd = st.session_state.get("kh_res", (False, False))
                                    if goed_lemma and goed_tijd:
                                        st.success(f"✅ Juist! **{vorm}** = {correct_tijd} van **{correct_prae}** — _{correct_bet}_")
                                    else:
                                        deel_l = "✓" if goed_lemma else "✗"
                                        deel_t = "✓" if goed_tijd else "✗"
                                        st.error(f"{deel_l} lemma · {deel_t} tijd — het was **{correct_tijd}** van **{correct_prae}** — _{correct_bet}_")
                                    morf = basis.get("morfologie", {}); regel = morf.get("mutatieregel", {})
                                    if is_suppletie:
                                        st.warning(f"🔥 **Onregelmatig (suppletie):** {regel.get('toelichting', 'Puur memoriseren.')}")
                                    else:
                                        st.info(f"💡 **Klankwet ({morf.get('klasse','regelmatig')}):** {regel.get('formule','')} — {regel.get('toelichting','')}")
                                    if st.button("➡️ Volgende vorm", key="kh_next_mc", use_container_width=True):
                                        st.session_state.kh_huidig = r_engine.choice(kh_items) if kh_items else None
                                        st.session_state.kh_opties = None; st.session_state.kh_gecheckt = False
                                        st.rerun()

                            # ---- TYPEN ----
                            else:
                                with st.form("kh_typ_form"):
                                    in_prae = st.text_input("1. Praesens (lemma) — Latijnse toetsen mag:", key="kh_in_prae")
                                    in_bet = st.text_input("2. Betekenis:", key="kh_in_bet")
                                    afleiders_t = [t for t in alle_tijden if t != correct_tijd]
                                    opties_tijd = sorted(set([correct_tijd] + r_engine.sample(afleiders_t, min(3, len(afleiders_t)))))
                                    in_tijd = st.selectbox("3. Tijd:", [""] + opties_tijd)
                                    if st.form_submit_button("✓ Nakijken", type="primary"):
                                        registreer_oefening()
                                        ok_prae = normaliseer_accent(naar_grieks_transliteratie(in_prae)) == normaliseer_accent(correct_prae)
                                        ok_bet = check_betekenis(in_bet, correct_bet)
                                        ok_tijd = (in_tijd == correct_tijd)
                                        st.session_state.kh_score_totaal = st.session_state.get("kh_score_totaal", 0) + 1
                                        if ok_prae and ok_bet and ok_tijd:
                                            st.session_state.kh_score_goed = st.session_state.get("kh_score_goed", 0) + 1
                                        st.session_state.kh_gecheckt = True
                                        st.session_state.kh_res_typ = (ok_prae, ok_bet, ok_tijd)
                                        st.rerun()

                                if st.session_state.get("kh_gecheckt"):
                                    ok_prae, ok_bet, ok_tijd = st.session_state.get("kh_res_typ", (False, False, False))
                                    if ok_prae and ok_bet and ok_tijd:
                                        st.success(f"✅ Precies! **{vorm}** = {correct_tijd} van **{correct_prae}** — _{correct_bet}_")
                                    else:
                                        st.error(f"{'✓' if ok_prae else '✗'} lemma · {'✓' if ok_bet else '✗'} betekenis · {'✓' if ok_tijd else '✗'} tijd  \nCorrect: **{correct_prae}** — _{correct_bet}_ ({correct_tijd})")
                                    morf = basis.get("morfologie", {}); regel = morf.get("mutatieregel", {})
                                    if is_suppletie:
                                        st.warning(f"🔥 **Onregelmatig (suppletie):** {regel.get('toelichting', 'Puur memoriseren.')}")
                                    else:
                                        st.info(f"💡 **Klankwet ({morf.get('klasse','regelmatig')}):** {regel.get('formule','')} — {regel.get('toelichting','')}")
                                    if st.button("➡️ Volgende vorm", key="kh_next_typ", use_container_width=True):
                                        st.session_state.kh_huidig = r_engine.choice(kh_items) if kh_items else None
                                        st.session_state.kh_opties = None; st.session_state.kh_gecheckt = False
                                        st.rerun()

                else:
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        # Leerpad is nu een eigen modus-bolletje; in de andere modi kies je hier de bron.
                        if "Leerpad" in stam_modus:
                            bron_keuze = "🎮 Leerpad (levels)"
                        else:
                            bron_keuze = st.selectbox("Oefening:", ["📚 Uit geselecteerde lessen", "📖 Uit een Bijbeltekst"])
                        gekozen_stam_lessen = []; gefilterde_ww_pool = []
                        is_stam_leerpad = False
                        lp_stam_aantal = 0

                        if bron_keuze == "🎮 Leerpad (levels)":
                            is_stam_leerpad = True
                            _xp_s = bereken_xp_stam(st.session_state.stam_stats)
                            _niv_s = niveau_van_xp(_xp_s)
                            st.markdown(f"#### 🎮 Stamtijden — niveau {_niv_s['niveau']} · {_niv_s['titel']}")
                            st.progress(_niv_s['xp_in_niveau'] / max(1, _niv_s['xp_voor_volgend']))
                            st.caption(f"⭐ {_niv_s['xp_totaal']} XP — nog {_niv_s['xp_voor_volgend'] - _niv_s['xp_in_niveau']} XP tot niveau {_niv_s['niveau'] + 1}.")
                            _lv_s = stam_level_status(bouw_stam_levels(stamtijden_db), st.session_state.stam_stats)
                            _ontgr_s = [l for l in _lv_s if l['ontgrendeld']]
                            _vol_s = sum(1 for l in _lv_s if l['voltooid'])
                            st.caption(f"🏁 {_vol_s}/{len(_lv_s)} werkwoorden voltooid · een vorm telt als 'af' bij streak ≥ 5.")
                            st.caption("🧭 Oplopend: het Leerpad geeft **meerkeuze** zolang je streak laag is en **typen** zodra je vorderingen maakt. Tip: gebruik voor een gloednieuw werkwoord eerst de modus **🧠 Leer (flashcards)**.")
                            if _ontgr_s:
                                _huidig_s = next((l for l in _lv_s if l['ontgrendeld'] and not l['voltooid']), _ontgr_s[-1])
                                _labels_s = [f"{'✅' if l['voltooid'] else '▶️'} Level {l['index']} · {l['titel']} ({l['klaar']}/{l['totaal']})" for l in _ontgr_s]
                                _sel_s = st.selectbox("Kies een ontgrendeld werkwoord:", _labels_s,
                                                      index=_ontgr_s.index(_huidig_s) if _huidig_s in _ontgr_s else 0)
                                gefilterde_ww_pool = [_ontgr_s[_labels_s.index(_sel_s)]['verb']]
                                _slot_s = next((l for l in _lv_s if not l['ontgrendeld']), None)
                                if _slot_s:
                                    st.caption(f"🔒 Hierna: Level {_slot_s['index']} — {_slot_s['titel']}.")
                            lp_stam_aantal = {"1 oude vorm (aanrader)": 1, "Kleine herhaalronde (4)": 4, "Alleen dit werkwoord": 0}[
                                st.selectbox("🔁 Oude stof meenemen:", ["1 oude vorm (aanrader)", "Kleine herhaalronde (4)", "Alleen dit werkwoord"], index=0, key="lp_stam_herhaal")]
                            with st.expander("🗺️ Toon het hele pad", expanded=False):
                                for l in _lv_s:
                                    _ico = "✅" if l['voltooid'] else ("▶️" if l['ontgrendeld'] else "🔒")
                                    st.markdown(f"{_ico} **Level {l['index']}** · {l['titel']} — {l['klaar']}/{l['totaal']}")

                        elif bron_keuze == "📚 Uit geselecteerde lessen":
                            alle_lessen_stam = sorted(list(set(i.get('les', 0) for i in stamtijden_db if i.get('les', 0) > 0)))
                            gekozen_stam_lessen = st.multiselect("Kies les(sen):", alle_lessen_stam, default=alle_lessen_stam[:1])
                            gefilterde_ww_pool = [w for w in stamtijden_db if w.get('les', 0) in gekozen_stam_lessen]

                        elif bron_keuze == "📖 Uit een Bijbeltekst":
                            b_lijst = sorted(list(set(k.split(" ")[0] for k in bijbel_db.keys() if " " in k)))
                            p_boek = st.selectbox("Kies Bijbelboek:", b_lijst if b_lijst else ["Mattheus"])
                            h_lijst = sorted(list(set(k.split(" ")[1].split(":")[0] for k in bijbel_db.keys() if k.startswith(p_boek) and ":" in k)), key=lambda x: int(x) if x.isdigit() else 0)
                            p_hoofdstuk = st.selectbox("Kies Hoofdstuk:", h_lijst)
                            
                            strongs_in_tekst = set()
                            prefix_zoek = f"{p_boek} {p_hoofdstuk}:"
                            for ref, zin in bijbel_db.items():
                                if ref.startswith(prefix_zoek):
                                    for woord in zin:
                                        if w_str := woord.get('strong'): strongs_in_tekst.add(str(w_str))
                            st.caption(f"Gevonden unieke stammen: {len(strongs_in_tekst)}")
                            gefilterde_ww_pool = [w for w in stamtijden_db if str(w.get('strong_nummer', '')).replace('G', '') in strongs_in_tekst]

                        if _geav:
                            stam_vorm = st.radio("Oefenvorm:", _STAM_VORMEN, horizontal=True,
                                                 key="stam_oefenvorm",
                                                 help="Automatisch = de app kiest per vorm: eerst leren, dan meerkeuze, en typen zodra je hem kent.")
                            oefen_stijl = st.radio("Sessie opbouw:", ["🤖 Automatische Gated Mix", "🎛️ Zelf Fasen Samenstellen"], horizontal=True)
                            stam_negeer_gate = st.checkbox(
                                "🔓 Negeer vergrendeling (oefen ook stamtijden waarvan het basiswoord nog niet op streak 5 staat)",
                                key="stam_negeer_gate",
                                help="Normaal ontgrendel je de stamtijden van een werkwoord pas als je het basiswoord al kent (vocab-streak ≥ 5), en elke volgende tijd als de vorige zit. Zet dit aan om meteen met alle stamtijden te oefenen."
                            )
                        else:
                            stam_vorm = _STAM_VORMEN[0]
                            oefen_stijl = "🤖 Automatische Gated Mix"
                            stam_negeer_gate = False
                        custom_counts = None
                        if oefen_stijl == "🎛️ Zelf Fasen Samenstellen" and gefilterde_ww_pool:
                            custom_counts = {
                                'nieuw': st.slider("Nieuw (Streak 0)", 0, 20, 4), 'training': st.slider("In Training (Streak 1–15)", 0, 20, 6),
                                'beheerst': st.slider("Beheerst (Streak 16–29)", 0, 20, 0), 'mastery': st.slider("Mastery (Streak 30+)", 0, 20, 0)
                            }

                        if st.button("Start Sessie", key="btn_start_stam", type="primary"):
                            st.session_state.gestrafte_woorden_stam = set()
                            doel_vormen = []
                            tijden_volgorde = ["Futurum Actief/Medium", "Aoristus Actief/Medium", "Aoristus Passief", "Perfectum Actief", "Perfectum Medium/Passief"]

                            gate_uit = stam_negeer_gate or is_stam_leerpad
                            for w in gefilterde_ww_pool:
                                p_streak = vocab_streak_van(w['praesens'])
                                if not gate_uit and p_streak < 5: continue

                                vorige_streak = 999 if gate_uit else p_streak
                                for t_d in tijden_volgorde:
                                    if not _stam_vorm_ok(vorm := w.get('stamtijden', {}).get(t_d)): continue
                                    vid = f"{w['praesens']}_{vorm}"
                                    stats = st.session_state.stam_stats.get(vid, {'g':0, 'f':0, 'streak':0})
                                    if gate_uit or vorige_streak >= 5:
                                        doel_vormen.append({"basis": w, "vraag_vorm": {"tijd_diathese": t_d, "vorm": vorm}, "score_goed": stats.get('g',0), "score_fout": stats.get('f',0), "streak": stats.get('streak',0), "vid": vid})
                                        vorige_streak = 999 if gate_uit else stats.get('streak', 0)
                                    else: break

                            # Leerpad: haal af en toe oude stamtijd-vormen op (laagste streak eerst).
                            if is_stam_leerpad and lp_stam_aantal > 0 and gefilterde_ww_pool:
                                doel_vormen += stam_herhaalvormen(stamtijden_db, st.session_state.stam_stats,
                                                                  gefilterde_ww_pool[0].get('praesens'), lp_stam_aantal)

                            if doel_vormen:
                                sampled = kies_gefaseerde_oefensessie(doel_vormen, 'stam', custom_counts=custom_counts)
                                m_id = "2" if "Mix" in stam_vorm else ("3" if "Typen" in stam_vorm else "1")
                                if is_stam_leerpad and stam_vorm == _STAM_VORMEN[0]:
                                    # Leerpad: oplopend — nieuwe vorm eerst als flashcard (Leer), dan
                                    # meerkeuze zolang de streak laag is, en pas daarna typen.
                                    _stam_kaarten = []
                                    for v in sampled:
                                        _s = int(v.get('streak', 0))
                                        if _s <= 0:
                                            _stam_kaarten.append((v, "Leer")); _stam_kaarten.append((v, "MC"))
                                        elif _s < LEERPAD_TYP_STREAK:
                                            _stam_kaarten.append((v, "MC"))
                                        else:
                                            _stam_kaarten.append((v, "Typen"))
                                    st.session_state.stam_sessie_lijst = _stam_kaarten
                                elif m_id == "2": st.session_state.stam_sessie_lijst = [(v, "MC") for v in sampled[::2]] + [(v, "Typen") for v in sampled[1::2]]
                                elif m_id == "3": st.session_state.stam_sessie_lijst = [(v, "Typen") for v in sampled]
                                else: st.session_state.stam_sessie_lijst = [(v, "MC") for v in sampled]
                                laad_volgend_stam_woord(); st.rerun()
                            else: st.warning("⚠️ Geen stamtijden gevonden. Zet hierboven **🔓 Negeer vergrendeling** aan om meteen te oefenen, of breng eerst de basiswoorden op streak ≥ 5 in het Woordenschat-tabblad.")

                    with c2:
                        if st.session_state.stam_huidig:
                            huidig = st.session_state.stam_huidig
                            sub_modus = st.session_state.stam_sub_modus
                            vid = huidig['vid']
                            if vid not in st.session_state.stam_stats: st.session_state.stam_stats[vid] = {'g':0, 'f':0, 'streak':0}
                            
                            if st.session_state.stam_feedback:
                                if st.session_state.stam_feedback["type"] == "success": st.success(st.session_state.stam_feedback["msg"])
                                elif st.session_state.stam_feedback["type"] == "warning": st.warning(st.session_state.stam_feedback["msg"])
                                else: st.error(st.session_state.stam_feedback["msg"])
                                st.session_state.stam_feedback = None 

                            correct_gram = huidig['vraag_vorm']['tijd_diathese']
                            correct_praesens = huidig['basis']['praesens']
                            correct_betekenis = huidig['basis']['betekenis']
                            
                            # Stam/uitgang bepalen mét de praesensvorm als anker (betrouwbaar), en de
                            # klankwet-uitleg afleiden uit de vorm zelf in plaats van uit een vuistregel
                            # die per werkwoord niet altijd klopt.
                            dstam, duit = deconstrueer_stamtijd_live(huidig['vraag_vorm']['vorm'], correct_gram, correct_praesens)

                            # Native Streamlit markdown-kleurcode :blue[...] in plaats van HTML
                            gekleurde_vorm_html = f"**{dstam}**:blue[**{duit}**]" if duit else f"**{huidig['vraag_vorm']['vorm']}**"
                            fout_msg = f"{gekleurde_vorm_html} — {correct_gram} van **{correct_praesens}** — **{correct_betekenis}**"

                            morf = huidig['basis'].get('morfologie', {}); regel = morf.get('mutatieregel', {})
                            _stam_regels = stamtijd_opbouw_regels(huidig['vraag_vorm']['vorm'], correct_gram, huidig['basis'])
                            uitleg_regel = "💡 **Zo is deze vorm opgebouwd:**\n\n" + "\n".join("- " + _r for _r in _stam_regels)
                            
                            # Live streak lezen: 'huidig' is een momentopname van bij het opbouwen van de
                            # sessie, dus straf op basis daarvan wist winst die je binnen deze sessie boekte.
                            huidige_streak = int((st.session_state.stam_stats.get(huidig.get('vid'), {}) or {}).get('streak', huidig.get('streak', 0)))
                            if huidige_streak >= 30:
                                st.caption("🏆 Mastery Modus: Herken de stamtijd in de Bijbel!")
                                s_nr = str(huidig['basis'].get('strong_nummer', '')).replace('G', '')
                                if zin_data := zoek_context_zin(s_nr, 'ww', bijbel_db, anti_spiek=True, specifieke_vorm=huidig['vraag_vorm']['vorm']): st.markdown(zin_data["html"], unsafe_allow_html=True)
                                else: st.markdown(f"<div class='grieks-woord'>{huidig['vraag_vorm']['vorm']}</div>", unsafe_allow_html=True)
                            else:
                                st.caption("Identificeer deze stamtijd:")
                                st.markdown(f"<div class='grieks-woord'>{huidig['vraag_vorm']['vorm']}</div>", unsafe_allow_html=True)

                            if sub_modus == "Leer":
                                st.info("🧠 Leer-kaart — bekijk de vorm en het antwoord, en klik op Volgende als je 'm kent.")
                                st.markdown(f"**Antwoord:** {fout_msg}")
                                st.markdown(uitleg_regel)
                                if st.button("Volgende", key="stam_leer_next", type="primary"):
                                    laad_volgend_stam_woord(); st.rerun()

                            elif sub_modus == 'overtik':
                                st.warning("⚠️ Overtikken: Je had deze vorm fout. Vul de correcte gegevens exact in.")
                                st.info(f"Het juiste antwoord is: {fout_msg}"); st.markdown(uitleg_regel)
                                p_gram = st.selectbox("1. Grammatica:", ["", "Futurum Actief/Medium", "Aoristus Actief/Medium", "Aoristus Passief", "Perfectum Actief", "Perfectum Medium/Passief"], key=f"in_ov_g_{vid}")
                                p_prae = st.text_input("2. Praesens bronwoord:", key=f"in_ov_p_{vid}")
                                if st.button("Bevestig Overtikken"):
                                    registreer_oefening()
                                    if p_gram == correct_gram and normaliseer_accent(naar_grieks_transliteratie(p_prae)) == normaliseer_accent(correct_praesens):
                                        st.session_state.stam_feedback = {"type": "success", "msg": "Genoteerd! Hij komt straks weer."}; trigger_save(); laad_volgend_stam_woord(); st.rerun()
                                    else: st.error("Nog niet exact overgetypt!")

                            elif sub_modus == "Typen":
                                t_gram = st.selectbox("1. Grammatica:", ["", "Futurum Actief/Medium", "Aoristus Actief/Medium", "Aoristus Passief", "Perfectum Actief", "Perfectum Medium/Passief"], key=f"in_tp_g_{vid}")
                                t_prae = st.text_input("2. Praesens bronwoord:", key=f"in_tp_p_{vid}"); t_bete = st.text_input("3. Betekenis bronwoord:", key=f"in_tp_b_{vid}")
                                if st.button("✓ Nakijken", type="primary"):
                                    registreer_oefening()
                                    if (t_gram == correct_gram) and (normaliseer_accent(naar_grieks_transliteratie(t_prae)) == normaliseer_accent(correct_praesens)) and check_betekenis(t_bete, correct_betekenis):
                                        if st.session_state.stam_fouten == 0 and vid not in st.session_state.gestrafte_woorden_stam: st.session_state.stam_stats[vid]['g'] += 1; st.session_state.stam_stats[vid]['streak'] += 1
                                        dagdoel_plus('stam')
                                        s_msg = f"✓ Goed! {fout_msg}\n\n{uitleg_regel}"
                                        if vid in st.session_state.gestrafte_woorden_stam: s_msg += "\n\n*(Geen streak-punten wegens eerdere fout)*"
                                        st.session_state.stam_feedback = {"type": "success", "msg": s_msg}; trigger_save(); laad_volgend_stam_woord(); st.rerun()
                                    else:
                                        st.session_state.stam_fouten += 1
                                        if huidige_streak >= 16 or st.session_state.stam_fouten >= 2:
                                            st.session_state.stam_stats[vid]['f'] += 1
                                            st.session_state.stam_stats[vid]['streak'] = max(0, huidige_streak - 2); st.session_state.gestrafte_woorden_stam.add(vid)
                                            st.session_state.stam_sessie_lijst.insert(0, (huidig, 'overtik')); st.session_state.stam_sessie_lijst.append((huidig, sub_modus))
                                            st.session_state.stam_feedback = {"type": "error", "msg": f"✗ Fout. Het was: {fout_msg}.\n\n{uitleg_regel}"}; trigger_save(); laad_volgend_stam_woord(); st.rerun()
                                        else: st.session_state.stam_stats[vid]['f'] += 1; st.session_state.stam_feedback = {"type": "warning", "msg": f"Bijna! Probeer het nog eens.\n\n{uitleg_regel}"}
                                        st.rerun()

                            else: 
                                if not st.session_state.stam_opties_gram:
                                    afleiders_g = [g for g in ["Futurum Actief/Medium", "Aoristus Actief/Medium", "Aoristus Passief", "Perfectum Actief", "Perfectum Medium/Passief"] if g != correct_gram]
                                    st.session_state.stam_opties_gram = [correct_gram] + r_engine.sample(afleiders_g, 3); r_engine.shuffle(st.session_state.stam_opties_gram)
                                    
                                    correct_p = f"{correct_praesens} — {correct_betekenis}"; afleiders_p = []; bestaande_b = {correct_betekenis}
                                    ww_pool = [w for w in stamtijden_db if w['praesens'] != correct_praesens]
                                    r_engine.shuffle(ww_pool)
                                    for w in ww_pool:
                                        if w['betekenis'] not in bestaande_b: afleiders_p.append(f"{w['praesens']} — {w['betekenis']}"); bestaande_b.add(w['betekenis'])
                                        if len(afleiders_p) >= 3: break
                                    st.session_state.stam_opties_praesens = [correct_p] + afleiders_p; r_engine.shuffle(st.session_state.stam_opties_praesens)

                                with st.form("form_stamtijd_mc"):
                                    st.write("**1. Grammatica:**")
                                    if st.session_state.stam_mc_solved["gram"]: st.success(f"✓ {correct_gram}"); keuze_gram = correct_gram
                                    else: keuze_gram = st.radio("Wat is deze vorm?", st.session_state.stam_opties_gram, index=None, label_visibility="collapsed")
                                    
                                    st.write("**2. Herleiding:**")
                                    if st.session_state.stam_mc_solved["praesens"]: st.success(f"✓ {correct_praesens} — {correct_betekenis}"); keuze_praesens = f"{correct_praesens} — {correct_betekenis}"
                                    else: keuze_praesens = st.radio("Bij welk werkwoord hoort dit?", st.session_state.stam_opties_praesens, index=None, label_visibility="collapsed")
                                    
                                    if st.form_submit_button("✓ Nakijken"):
                                        registreer_oefening()
                                        if (keuze_gram == correct_gram): st.session_state.stam_mc_solved["gram"] = True
                                        if (keuze_praesens == f"{correct_praesens} — {correct_betekenis}"): st.session_state.stam_mc_solved["praesens"] = True
                                        
                                        if st.session_state.stam_mc_solved["gram"] and st.session_state.stam_mc_solved["praesens"]:
                                            if st.session_state.stam_fouten == 0 and vid not in st.session_state.gestrafte_woorden_stam: st.session_state.stam_stats[vid]['g'] += 1; st.session_state.stam_stats[vid]['streak'] += 1
                                            dagdoel_plus('stam')
                                            s_msg = f"✓ Goed! {fout_msg}\n\n{uitleg_regel}"
                                            if vid in st.session_state.gestrafte_woorden_stam: s_msg += "\n\n*(Geen streak-punten wegens eerdere fout)*"
                                            st.session_state.stam_feedback = {"type": "success", "msg": s_msg}; trigger_save(); laad_volgend_stam_woord(); st.rerun()
                                        else:
                                            st.session_state.stam_fouten += 1
                                            if huidige_streak >= 16 or st.session_state.stam_fouten >= 2:
                                                st.session_state.stam_stats[vid]['f'] += 1
                                                st.session_state.stam_stats[vid]['streak'] = max(0, huidige_streak - 2); st.session_state.gestrafte_woorden_stam.add(vid)
                                                # In MC blijven: toon het antwoord en doe dezelfde vraag meteen nog een keer als meerkeuze.
                                                st.session_state.stam_sessie_lijst.insert(0, (huidig, sub_modus))
                                                st.session_state.stam_feedback = {"type": "error", "msg": f"✗ Fout. Het was: {fout_msg}.\n\n{uitleg_regel}\n\nKlik hem nu nog één keer goed aan."}; trigger_save(); laad_volgend_stam_woord(); st.rerun()
                                            else: st.session_state.stam_stats[vid]['f'] += 1; st.session_state.stam_feedback = {"type": "warning", "msg": f"Eén van je keuzes is onjuist!\n\n{uitleg_regel}"}
                                            st.rerun()

                            # 'Ik weet het niet' — toont het antwoord zonder aftrek en zet 'm terug in de rij,
                            # zodat je 'm straks nog een keer echt ophaalt (geen streak-punten deze keer).
                            if sub_modus not in ('Leer', 'overtik'):
                                if st.button("🤔 Ik weet het niet — toon het antwoord", key=f"stam_weetniet_{vid}"):
                                    st.session_state.gestrafte_woorden_stam.add(vid)
                                    st.session_state.stam_sessie_lijst.append((huidig, sub_modus))
                                    st.session_state.stam_feedback = {"type": "info", "msg": f"💡 {fout_msg}\n\n{uitleg_regel}\n\nGeen aftrek — je krijgt 'm straks nog een keer om echt op te halen."}
                                    trigger_save(); laad_volgend_stam_woord(); st.rerun()

                            if sub_modus != 'overtik':
                                st.write("---")
                                fn = 'Nieuw' if huidige_streak==0 else ('In Training' if huidige_streak<=15 else ('Beheerst' if huidige_streak<=29 else 'Mastery'))
                                st.caption(f"🔢 Nog {len(st.session_state.get('stam_sessie_lijst') or [])} te gaan | Fase: {fn} | Streak: {huidige_streak} | Goed/Fout: {st.session_state.stam_stats[vid].get('g',0)}/{st.session_state.stam_stats[vid].get('f',0)}")

       # ==========================================
        # TAB 6: STRUCTUURWOORDEN & SYNTAXIS
        # ==========================================
        if _TOON[5]:
         with menu[5]:
            struct_db = laad_structuurwoorden_db()
            if not struct_db: 
                st.warning("Bestand 'structuurwoorden.json' ontbreekt.")
            else:
                st.subheader("🧱 Structuurwoorden Herkennen & Syntaxis")
                c1, c2 = st.columns([1, 2])
                
                with c1:
                    # --- DE NIEUWE LEER-SPOOR FILTER ---
                    _struct_sporen = [
                        "🎮 Leerpad (levels)",
                        "Alles gemixt",
                        "Alleen Voorzetsels",
                        "Voegwoorden & Partikels",
                        "Voornaamwoorden (Pronomina)"
                    ] if _geav else ["🎮 Leerpad (levels)"]
                    struct_filter = _pref_keuze(st.selectbox, "Oefening:", _struct_sporen,
                                                'struct_spoor', key="struct_filter_box")

                    is_struct_leerpad = False
                    struct_leerpad_indices = set()
                    if struct_filter == "🎮 Leerpad (levels)":
                        is_struct_leerpad = True
                        _xp_st = bereken_xp_struct(st.session_state.struct_stats)
                        _niv_st = niveau_van_xp(_xp_st)
                        st.markdown(f"**🎮 Niveau {_niv_st['niveau']} · {_niv_st['titel']}** — {_niv_st['xp_totaal']} XP")
                        st.progress(_niv_st['xp_in_niveau'] / max(1, _niv_st['xp_voor_volgend']))
                        _lv_st = struct_level_status(bouw_struct_levels(struct_db), st.session_state.struct_stats)
                        _ontgr_st = [l for l in _lv_st if l['ontgrendeld']]
                        _vol_st = sum(1 for l in _lv_st if l['voltooid'])
                        st.caption(f"🏁 {_vol_st}/{len(_lv_st)} levels voltooid · woord 'af' bij streak ≥ 5.")
                        if _ontgr_st:
                            _huidig_st = next((l for l in _lv_st if l['ontgrendeld'] and not l['voltooid']), _ontgr_st[-1])
                            _labels_st = [f"{'✅' if l['voltooid'] else '▶️'} Level {l['index']} · {l['titel']} ({l['klaar']}/{l['totaal']})" for l in _ontgr_st]
                            _sel_st = st.selectbox("Kies een ontgrendeld level:", _labels_st,
                                                   index=_ontgr_st.index(_huidig_st) if _huidig_st in _ontgr_st else 0)
                            _gekozen_lv_st = _ontgr_st[_labels_st.index(_sel_st)]
                            struct_leerpad_indices = {idx for idx, _w in _gekozen_lv_st['items']}
                            with st.expander("📖 Leer eerst dit rijtje", expanded=False):
                                for _idx, _w in _gekozen_lv_st['items']:
                                    st.markdown(f"- **{_w['grieks']}** — {_w.get('betekenis','')}  \n  <span style='color:#888;font-size:12px;'>{_w.get('categorie','')} · {_w.get('eigenschap','')}</span>", unsafe_allow_html=True)
                            st.caption("💡 Tip: tijdens het oefenen zie je de woorden ook in een echte Bijbelzin (met naamval-kleuren).")
                            _slot_st = next((l for l in _lv_st if not l['ontgrendeld']), None)
                            if _slot_st:
                                st.caption(f"🔒 Hierna: Level {_slot_st['index']} — {_slot_st['titel']}.")

                    struct_modus = _pref_keuze(st.radio, "Oefenvorm:", _STRUCT_VORMEN, 'struct_oefenvorm', key="struct_modus_radio",
                                                help="Automatisch = de app kiest per woord: eerst leren, dan meerkeuze, en typen zodra je het woord kent.")

                    if st.button("Start Sessie", key="btn_start_struct", type="primary"):
                        st.session_state.gestrafte_woorden_struct = set()
                        doel_vormen = []

                        for idx_w, w in enumerate(struct_db):
                            cat_str = w.get('categorie', '')

                            # Leerpad: alleen de woorden van het gekozen level
                            if is_struct_leerpad and idx_w not in struct_leerpad_indices: continue

                            # Toepassing van de door de student gekozen filter
                            if struct_filter == "Alleen Voorzetsels" and "Voorzetsel" not in cat_str: continue
                            if struct_filter == "Voegwoorden & Partikels" and "Voegwoord" not in cat_str and "Partikel" not in cat_str: continue
                            if struct_filter == "Voornaamwoorden (Pronomina)" and "Vnw" not in cat_str and "Pronomina" not in cat_str: continue

                            vid = f"{w['grieks']}_{idx_w}"
                            stats = st.session_state.struct_stats.get(vid, st.session_state.struct_stats.get(w['grieks'], {'g': 0, 'f': 0, 'streak': 0}))
                            # Kopie maken: 'w' komt uit de @st.cache_data-database en die mag je niet
                            # muteren (elke aanroep geeft een verse kopie, dus de streak zou bevriezen).
                            w2 = dict(w)
                            w2['score_goed'] = stats.get('g', 0)
                            w2['score_fout'] = stats.get('f', 0)
                            w2['streak'] = stats.get('streak', 0)
                            w2['vid'] = vid
                            doel_vormen.append(w2)
                        
                        if doel_vormen:
                            sampled = kies_gefaseerde_oefensessie(doel_vormen, module='struct')
                            modus_id = str(struct_modus[0])
                            if is_struct_leerpad or struct_modus == AUTO_VORM:
                                # Leerpad: oplopend per woord — nieuw eerst flashcard (Leer) + meerkeuze,
                                # daarna meerkeuze, en bij een stevige streak typen.
                                _struct_kaarten = []
                                for v in sampled:
                                    _s = int(v.get('streak', 0))
                                    if _s <= 0:
                                        _struct_kaarten.append((v, "Leer")); _struct_kaarten.append((v, "MC"))
                                    elif _s < LEERPAD_TYP_STREAK:
                                        _struct_kaarten.append((v, "MC"))
                                    else:
                                        _struct_kaarten.append((v, "Typen"))
                                st.session_state.struct_sessie_lijst = _struct_kaarten
                            elif modus_id == "2": st.session_state.struct_sessie_lijst = [(v, "MC") for v in sampled] + [(v, "Typen") for v in sampled]
                            elif modus_id == "3": st.session_state.struct_sessie_lijst = [(v, "Typen") for v in sampled]
                            else: st.session_state.struct_sessie_lijst = [(v, "MC") for v in sampled]
                            laad_volgend_struct_woord()
                            st.rerun()

                with c2:
                    if st.session_state.struct_huidig:
                        huidig = st.session_state.struct_huidig
                        sub_modus = st.session_state.struct_sub_modus
                        vid = huidig['vid']
                        w_id_clean = re.sub(r'\W+', '_', vid)
                        
                        if vid not in st.session_state.struct_stats: 
                            st.session_state.struct_stats[vid] = {'g': 0, 'f': 0, 'streak': 0}
                        
                        if st.session_state.struct_feedback:
                            if st.session_state.struct_feedback["type"] == "success": st.success(st.session_state.struct_feedback["msg"])
                            elif st.session_state.struct_feedback["type"] == "warning": st.warning(st.session_state.struct_feedback["msg"])
                            else: st.error(st.session_state.struct_feedback["msg"])
                            st.session_state.struct_feedback = None 

                        correct_cat = huidig['categorie']
                        correct_eig = huidig['eigenschap']
                        correct_bet = huidig['betekenis']
                        fout_msg_volledig = f"**{huidig['grieks']}** — {correct_cat} ({correct_eig}) — **{correct_bet}**"
                        alle_cats = sorted(list(set([w['categorie'] for w in struct_db])))

                        # --- AUTHENTIEK ZINVERBAND MET ANTI-SPOIL TOOLTIPS ---
                        bijbel_db = laad_bijbel_db()
                        label_puur = re.sub(r'\(.*?\)', '', huidig['grieks']).strip()
                        zoek_opties = [normaliseer_accent(d) for d in label_puur.split('/') if d.strip()]
                        
                        gevonden_context = None
                        extra_casus_hint = ""
                        doel_nv = huidig.get('eigenschap', '') 

                        struct_kleur_nv = _pref_bool(st.checkbox, "🎨 Markeer Naamvallen in zin (Kleur)", 'struct_kleur_nv_pref', default=False, key="struct_global_kleur_nv")
                        
                        if bijbel_db:
                            # Gecachte vorm-index i.p.v. het hele NT scannen bij elke rerun.
                            _sidx = _struct_vorm_posities(bijbel_db)
                            _kandidaten = []
                            for k in zoek_opties:
                                _kandidaten.extend(_sidx.get(k.replace('ς', 'σ'), []))
                            for ref, idx_w in _kandidaten:
                                zin = bijbel_db.get(ref)
                                if not zin or idx_w >= len(zin):
                                    continue
                                eis_voldaan = True
                                if "Voorzetsel" in huidig.get('categorie', ''):
                                    if idx_w + 1 < len(zin):
                                        next_p = zin[idx_w + 1].get('parsing_info', '')
                                        nv_prefix = doel_nv[:3]
                                        if nv_prefix not in next_p: eis_voldaan = False
                                    else: eis_voldaan = False

                                if eis_voldaan:
                                    if idx_w + 1 < len(zin):
                                        next_p = zin[idx_w + 1].get('parsing_info', '')
                                        if "Gen" in next_p: extra_casus_hint = " *(wordt hier direct gevolgd door de Genitivus)*"
                                        elif "Dat" in next_p: extra_casus_hint = " *(wordt hier direct gevolgd door de Dativus)*"
                                        elif "Acc" in next_p: extra_casus_hint = " *(wordt hier direct gevolgd door de Accusativus)*"

                                    html_z = ""
                                    for sub_w in zin:
                                        txt_col = "#bbb"
                                        if struct_kleur_nv:
                                            p_inf = sub_w.get('parsing_info', '')
                                            if "Nom" in p_inf: txt_col = "#33ccff"
                                            elif "Gen" in p_inf: txt_col = "#28a745"
                                            elif "Dat" in p_inf: txt_col = "#6f42c1"
                                            elif "Acc" in p_inf: txt_col = "#dc3545"
                                            elif "Voc" in p_inf: txt_col = "#fd7e14"

                                        n_sub = normaliseer_accent(sub_w['grieks'])
                                        is_doel = any(n_sub == k or n_sub == k.replace('ς','σ') for k in zoek_opties)

                                        if is_doel:
                                            # Doelwoord: neutrale (witte) tekst — NIET de naamval-kleur,
                                            # anders verklapt de kleur de gevraagde naamval. Alleen het
                                            # gele kader markeert dat dit het te toetsen woord is.
                                            t_tip = "❓ [Dit woord wordt getoetst]"
                                            w_style = "color: #ffffff; font-weight: 900; background-color: rgba(255, 215, 0, 0.15); border: 1px solid #ffd700; border-bottom: 3px solid #ffd700; padding: 1px 5px; border-radius: 4px;"
                                        else:
                                            v_nl = sub_w.get('vertaling_nl', '')
                                            v_bsb = sub_w.get('vertaling_bsb', '')
                                            p_inf = sub_w.get('parsing_info', '')
                                            # Nederlandse glosse primair; val terug op BSB; toon EN alleen als anker
                                            _kern = v_nl if v_nl.strip() else v_bsb
                                            _en_anker = f"\nEN: {v_bsb}" if (v_nl.strip() and v_bsb.strip()) else ""
                                            t_tip = f"{_kern} ({p_inf})" if _kern else p_inf
                                            t_tip = f"{t_tip}{_en_anker}"
                                            t_tip = t_tip.replace("'", "&#39;").replace('"', "&quot;")
                                            w_style = f"color: {txt_col}; border-bottom: 1px dotted #555;"

                                        html_z += f"<span class='mobile-tooltip' tabindex='0' style='{w_style}'>{sub_w['grieks']}<span class='tooltiptext'>{t_tip}</span></span>{sub_w.get('interpunctie','')} "
                                        
                                    gevonden_context = (ref, html_z.strip())
                                    break

                        # --- SPOILERVRIJE WEERGAVE ---
                        # Zuiver de weergavenaam permanent van haakjes (maakt van 'παρά (dat)' -> 'παρά')
                        toon_naam = re.sub(r'\(.*?\)', '', huidig['grieks']).strip()

                        if gevonden_context:
                            st.markdown(f"<div style='font-size: 13px; color: #f6c23e; margin-bottom: 2px;'>📖 Zinverband ({gevonden_context[0]}):</div>", unsafe_allow_html=True)
                            if struct_kleur_nv:
                                st.markdown("**(Kleurlegenda: <span style='color:#33ccff'>Nom</span> | <span style='color:#28a745'>Gen</span> | <span style='color:#6f42c1'>Dat</span> | <span style='color:#dc3545'>Acc</span> | <span style='color:#fd7e14'>Voc</span>)**", unsafe_allow_html=True)
                            st.markdown(f"<div class='grieks-zin' style='font-size: 22px; padding: 12px; margin-bottom: 12px;'>{gevonden_context[1]}</div>", unsafe_allow_html=True)
                            st.caption(f"Kijk naar de grammaticale functie van **{toon_naam}** in deze zin:")
                        else:
                            st.markdown(f"<div class='grieks-woord'>{toon_naam}</div>", unsafe_allow_html=True)
                            st.caption("Identificeer dit structuurwoord.")

                        # --- MODUS 0: LEER-KAART (flashcard, alleen in het Leerpad) ---
                        if sub_modus == "Leer":
                            st.info("🧠 Leer-kaart — bekijk het woord en het antwoord, en klik op Volgende als je 't kent.")
                            st.markdown(f"**Antwoord:** {fout_msg_volledig}")
                            if st.button("Volgende", key=f"struct_leer_next_{w_id_clean}", type="primary"):
                                laad_volgend_struct_woord(); st.rerun()

                        # --- MODUS 1: OVERTIKKEN ---
                        elif sub_modus == 'overtik':
                            st.warning("⚠️ Overtikken: Je had dit woord zojuist onjuist. Vul de correcte gegevens exact in om de verbinding te herstellen.")
                            st.info(f"Het juiste antwoord is: {fout_msg_volledig}")
                            forceer_focus()
                            with st.form(f"form_ov_{w_id_clean}", clear_on_submit=True):
                                p_cat = st.selectbox("1. Categorie:", [""] + alle_cats, key=f"ov_c_{w_id_clean}")
                                p_eig = st.text_input("2. Eigenschap/Naamval (exact overtypen):", key=f"ov_e_{w_id_clean}")
                                if st.form_submit_button("Bevestig"):
                                    registreer_oefening()
                                    if p_cat == correct_cat and p_eig.lower().strip() == correct_eig.lower().strip():
                                        st.session_state.struct_feedback = {"type": "success", "msg": "Genoteerd! Komt straks terug."}
                                        trigger_save(); laad_volgend_struct_woord(); st.rerun()
                                    else: st.error("Nog niet exact overgetypt.")

                        # --- MODUS 2: TYPEN ---
                        elif sub_modus == "Typen":
                            gekozen_cat = st.selectbox("1. Categorie:", [""] + alle_cats, key=f"typ_c_{w_id_clean}")
                            forceer_focus()
                            with st.form(f"form_typ_{w_id_clean}", clear_on_submit=True):
                                c_eig, c_bet = st.columns(2)
                                with c_eig: 
                                    gefilterde_eigs = sorted(list(set([w['eigenschap'] for w in struct_db if w['categorie'] == gekozen_cat]))) if gekozen_cat else []
                                    p_eig = st.selectbox("2. Eigenschap/Naamval", [""] + gefilterde_eigs, key=f"typ_e_{w_id_clean}")
                                with c_bet: p_bet = st.text_input("3. Betekenis:", key=f"typ_b_{w_id_clean}")
                                
                                if st.form_submit_button("✓ Nakijken"):
                                    registreer_oefening()
                                    if (gekozen_cat == correct_cat) and (p_eig == correct_eig) and check_betekenis(p_bet, correct_bet):
                                        if st.session_state.struct_fouten == 0 and vid not in st.session_state.gestrafte_woorden_struct:
                                            st.session_state.struct_stats[vid]['g'] += 1; st.session_state.struct_stats[vid]['streak'] += 1
                                        dagdoel_plus('struct')
                                        success_msg = f"✓ Goed! {fout_msg_volledig}"
                                        if vid in st.session_state.gestrafte_woorden_struct: success_msg += " *(Geen streak-punten: je zag het antwoord al eerder bij dit woord)*"
                                        st.session_state.struct_feedback = {"type": "success", "msg": success_msg}; trigger_save(); laad_volgend_struct_woord(); st.rerun()
                                    else:
                                        st.session_state.struct_fouten += 1; huidige_streak = st.session_state.struct_stats[vid]['streak']
                                        if huidige_streak >= 16 or st.session_state.struct_fouten >= 2:
                                            st.session_state.struct_stats[vid]['f'] += 1
                                            st.session_state.struct_stats[vid]['streak'] = max(0, huidige_streak - 2); st.session_state.gestrafte_woorden_struct.add(vid)
                                            st.session_state.struct_sessie_lijst.insert(0, (huidig, 'overtik')); st.session_state.struct_sessie_lijst.append((huidig, sub_modus))
                                            st.session_state.struct_feedback = {"type": "error", "msg": f"✗ Helaas. Jij dacht: *{gekozen_cat} | {p_eig} | {p_bet}*. Het was: {fout_msg_volledig}."}; trigger_save(); laad_volgend_struct_woord()
                                        else: st.session_state.struct_stats[vid]['f'] += 1; st.session_state.struct_feedback = {"type": "warning", "msg": "Niet helemaal juist. Bekijk de hint en probeer het opnieuw!"}
                                        st.rerun()

# --- MODUS 3: MEERKEUZE (GEÜPGRADED MET FAMILIE-TRIAGE) ---
                        else: 
                            if not st.session_state.struct_opties_cat:
                                import random as rnd
                                
                                # 1. Bepaal de 'Bloedgroep' van het huidige woord
                                cat_txt = huidig.get('categorie', '')
                                if "Voorzetsel" in cat_txt: fam = "Voorzetsel"
                                elif "Voegwoord" in cat_txt or "Partikel" in cat_txt: fam = "Voegwoord"
                                else: fam = "Pronomina"

                                # Helper om te checken of een ander DB-item tot dezelfde familie behoort
                                def is_genoot(item_cat, doel_fam):
                                    if doel_fam == "Voorzetsel": return "Voorzetsel" in item_cat
                                    elif doel_fam == "Voegwoord": return "Voegwoord" in item_cat or "Partikel" in item_cat
                                    else: return "Vnw" in item_cat or "Pronomina" in item_cat

                                # Vraag 1 (Categorie): Mag globaal blijven om de hoofdsoort te toetsen
                                afleiders_c = [c for c in alle_cats if c != correct_cat]
                                st.session_state.struct_opties_cat = [correct_cat] + rnd.sample(afleiders_c, min(3, len(afleiders_c)))
                                rnd.shuffle(st.session_state.struct_opties_cat)
                                
                                # Vraag 2 (Eigenschap / Naamval): STRIKT BINNEN DEZELFDE FAMILIE
                                if fam == "Voorzetsel":
                                    # Voorzetsels dwingen we op de 3 reële Griekse casus-opties:
                                    mogelijke_nv = ["Genitivus", "Dativus", "Accusativus"]
                                    if correct_eig in mogelijke_nv:
                                        st.session_state.struct_opties_eig = mogelijke_nv
                                    else:
                                        st.session_state.struct_opties_eig = [correct_eig] + [n for n in mogelijke_nv if n != correct_eig]
                                else:
                                    # Pronomina of Voegwoorden pakken de unieke parsing-termen van soortgenoten
                                    poule_e = sorted(list(set([w['eigenschap'] for w in struct_db if is_genoot(w['categorie'], fam) and w['eigenschap'] != correct_eig])))
                                    st.session_state.struct_opties_eig = [correct_eig] + rnd.sample(poule_e, min(3, len(poule_e)))

                                # Vaste didactische volgorde i.p.v. shuffle (Nom, Gen, Dat, Acc → ev/mv → M/V/O).
                                st.session_state.struct_opties_eig = sorteer_grammaticaal(st.session_state.struct_opties_eig)
                                
                                # Vraag 3 (Betekenis): STRIKT VERTALINGEN VAN SOORTGENOTEN
                                poule_b = list(set([w['betekenis'] for w in struct_db if is_genoot(w['categorie'], fam) and w['betekenis'] != correct_bet]))
                                st.session_state.struct_opties_bet = [correct_bet] + rnd.sample(poule_b, min(3, len(poule_b)))
                                rnd.shuffle(st.session_state.struct_opties_bet)
                                
                            with st.form(f"form_mc_{w_id_clean}"):
                                if st.session_state.struct_mc_solved["cat"]: st.success(f"✓ Categorie: {correct_cat}"); keuze_cat = correct_cat
                                else: keuze_cat = st.radio("1. Categorie:", st.session_state.struct_opties_cat, index=None, key=f"mc_c_{w_id_clean}")
                                
                                if st.session_state.struct_mc_solved["eig"]: st.success(f"✓ Eigenschap: {correct_eig}"); keuze_eig = correct_eig
                                else: keuze_eig = st.radio("2. Eigenschap / Naamval:", st.session_state.struct_opties_eig, index=None, key=f"mc_e_{w_id_clean}")
                                
                                if st.session_state.struct_mc_solved["bet"]: st.success(f"✓ Betekenis: {correct_bet}"); keuze_bet = correct_bet
                                else: keuze_bet = st.radio("3. Betekenis:", st.session_state.struct_opties_bet, index=None, key=f"mc_b_{w_id_clean}")
                                
                                if st.form_submit_button("✓ Nakijken"):
                                    registreer_oefening()
                                    if (keuze_cat == correct_cat): st.session_state.struct_mc_solved["cat"] = True
                                    if (keuze_eig == correct_eig): st.session_state.struct_mc_solved["eig"] = True
                                    if (keuze_bet == correct_bet): st.session_state.struct_mc_solved["bet"] = True
                                    
                                    if st.session_state.struct_mc_solved["cat"] and st.session_state.struct_mc_solved["eig"] and st.session_state.struct_mc_solved["bet"]:
                                        if st.session_state.struct_fouten == 0 and vid not in st.session_state.gestrafte_woorden_struct:
                                            st.session_state.struct_stats[vid]['g'] += 1; st.session_state.struct_stats[vid]['streak'] += 1
                                        dagdoel_plus('struct')
                                        success_msg = f"✓ Goed! {fout_msg_volledig}"
                                        if vid in st.session_state.gestrafte_woorden_struct: success_msg += " *(Geen streak-punten: je zag het antwoord al eerder bij dit woord)*"
                                        st.session_state.struct_feedback = {"type": "success", "msg": success_msg}; trigger_save(); laad_volgend_struct_woord()
                                    else:
                                        st.session_state.struct_fouten += 1; huidige_streak = st.session_state.struct_stats[vid]['streak']
                                        if huidige_streak >= 16 or st.session_state.struct_fouten >= 2:
                                            st.session_state.struct_stats[vid]['f'] += 1
                                            st.session_state.struct_stats[vid]['streak'] = max(0, huidige_streak - 2); st.session_state.gestrafte_woorden_struct.add(vid)
                                            # In MC blijven: toon het antwoord en doe deze vraag meteen nog een keer als meerkeuze.
                                            st.session_state.struct_sessie_lijst.insert(0, (huidig, sub_modus))
                                            st.session_state.struct_feedback = {"type": "error", "msg": f"✗ Helaas. Jij dacht: *{keuze_cat} | {keuze_eig} | {keuze_bet}*. Het was: {fout_msg_volledig}. Klik hem nu nog één keer goed aan."}; trigger_save(); laad_volgend_struct_woord()
                                        else: st.session_state.struct_stats[vid]['f'] += 1; st.session_state.struct_feedback = {"type": "warning", "msg": "De correcte delen zijn vastgezet. Probeer de overgebleven velden opnieuw!"}
                                    st.rerun()

                        if sub_modus != 'overtik':
                            st.write("---")
                            f_naam = 'Nieuw' if st.session_state.struct_stats[vid].get('streak', 0)==0 else ('In Training' if st.session_state.struct_stats[vid].get('streak', 0)<=15 else ('Beheerst' if st.session_state.struct_stats[vid].get('streak', 0)<=29 else 'Mastery'))
                            st.caption(f"🔢 Nog {len(st.session_state.get('struct_sessie_lijst') or [])} te gaan | Fase: {f_naam} | Streak: {st.session_state.struct_stats[vid].get('streak', 0)} | Goed/Fout: {st.session_state.struct_stats[vid].get('g', 0)}/{st.session_state.struct_stats[vid].get('f', 0)}")
                            
        # ==========================================
        # TAB 7: LEESTEKSTEN
        # ==========================================
        if _TOON[6]:
         with menu[6]:
            bijbel_db = laad_bijbel_db()
            stam_db_leestekst = laad_stamtijden_db() or []
            if not bijbel_db: st.warning("De Bijbel-database ontbreekt.")
            else:
                st.subheader("📝 Bijbelse Leesteksten & Exegese")
                top_c1, top_c2 = st.columns(2)
                with top_c1:
                    alle_lessen = sorted(list(set(veilig_les_nummer(i) for i in st.session_state.data)))
                    gekozen = st.multiselect("1. Oefen lessen (voor cyaan/paarse woorden):", alle_lessen, default=[alle_lessen[0]] if alle_lessen else [])
                    actieve_strongs = {str(w['strong']): w for w in st.session_state.data if veilig_les_nummer(w) in gekozen and w.get('strong')}
                    actieve_stam_vormen = {}
                    for s_ww in stam_db_leestekst:
                        if s_ww.get('les', 0) in gekozen:
                            for td, v in s_ww['stamtijden'].items(): actieve_stam_vormen[normaliseer_accent(v)] = {"tijd_diathese": td, "praesens": s_ww['praesens'], "betekenis": s_ww['betekenis']}
                with top_c2:
                    tekst_modus = _pref_keuze(st.radio, "2. Oefenmethode:", ["1. Lees & Spiek (Geen vragen)", "2. Vertaal (Meerkeuze)", "3. Vertaal (Typen)", "4. Masterclass (Ontleden)"], 'lees_methode')

                st.write("---")
                vis_c1, vis_c2, vis_c3, vis_c4 = st.columns(4)
                with vis_c1: kleur_naamvallen = st.checkbox("🎨 Markeer Naamvallen (Kleur)")
                with vis_c2: kleur_voegwoorden = st.checkbox("🔗 Markeer Voegwoorden (Geel)")
                with vis_c3: kleur_stamtijden = st.checkbox("⚛️ Markeer Stamtijden (Paars)")
                with vis_c4: master_niveau = _pref_keuze(st.selectbox, "Niveau Masterclass:", ["Grieks 1", "Grieks 2", "Grieks 3"], 'lees_niveau')

                st.write("---")
                st.markdown("### 3. Selecteer een Bijbeltekst")
                lees_modus = st.radio(
                    "Hoe wil je de tekst kiezen?", 
                    ["Kies specifiek(e) vers(zen)", "Scavenger Hunt (Willekeurig)", "🛡️ Autonome Leestekst (100% Bekend)"], 
                    horizontal=True
                )
                
                if lees_modus == "Kies specifiek(e) vers(zen)":
                    parsed_db = bijbel_boek_index(bijbel_db)   # gecached: scheelt ~8.000 regex-matches per rerun
                    
                    col_b, col_c, col_v = st.columns(3)
                    with col_b: gekozen_boek = st.selectbox("Boek:", list(parsed_db.keys()))
                    with col_c:
                        hoofdstukken = list(parsed_db[gekozen_boek].keys()); hoofdstukken.sort(key=lambda x: int(x) if str(x).isdigit() else 0)
                        gekozen_hoofdstuk = st.selectbox("Hoofdstuk:", hoofdstukken)
                    with col_v:
                        verzen_data = parsed_db[gekozen_boek][gekozen_hoofdstuk]; verzen_data.sort(key=lambda x: x[0])
                        vers_opties = [v[1] for v in verzen_data]
                        gekozen_verzen = st.multiselect("Vers(zen):", vers_opties, default=[vers_opties[0]] if vers_opties else [])
                    
                    if st.button("Laad Tekst"):
                        gecombineerd_vers = []
                        for vd in verzen_data:
                            if vd[1] in gekozen_verzen:
                                gecombineerd_vers.extend(bijbel_db[vd[2]])
                                if vd[2] not in st.session_state.geziene_verzen: st.session_state.geziene_verzen.append(vd[2])
                        st.session_state.geziene_verzen = st.session_state.geziene_verzen[-100:]
                        if gecombineerd_vers:
                            st.session_state.huidig_vers = gecombineerd_vers
                            st.session_state.huidige_vers_referentie = f"{gekozen_boek} {gekozen_hoofdstuk}:{', '.join(gekozen_verzen)}"
                            
                elif lees_modus == "Scavenger Hunt (Willekeurig)":
                    if st.button("Vind passend vers (Focus op zwakke woorden)"):
                        passende = []
                        for ref, w_list in bijbel_db.items():
                            if ref in st.session_state.geziene_verzen: continue
                            bekende_woorden = [w for w in w_list if w.get('strong') and str(w['strong']) in actieve_strongs]
                            if len(bekende_woorden) >= 3:
                                vers_gewicht = sum(bereken_gewicht(actieve_strongs[str(w['strong'])]) for w in bekende_woorden)
                                passende.append((ref, w_list, vers_gewicht))
                        if not passende: st.session_state.geziene_verzen = []; st.warning("Geschiedenis gereset. Geen nieuwe verzen gevonden, klik nogmaals om opnieuw te beginnen.")
                        else:
                            passende.sort(key=lambda x: x[2], reverse=True)
                            top_picks = passende[:min(10, len(passende))]; gekozen_vers = r_engine.choice(top_picks)
                            st.session_state.huidig_vers = gekozen_vers[1]; st.session_state.huidige_vers_referentie = gekozen_vers[0]
                            st.session_state.geziene_verzen.append(gekozen_vers[0]); st.session_state.geziene_verzen = st.session_state.geziene_verzen[-100:]

                else: # --- MODUS 3: AUTONOME LEESTEKST (100% BEKEND) ---
                    st.caption("Dit model zoekt in het Nieuwe Testament naar verzen die uitsluitend bestaan uit woorden met een actuele streak van ≥ 1.")
                    if st.button("Zoek autonome tekst", type="primary"):
                        bekende_strongs_all = {str(w['strong']) for w in st.session_state.data if int(w.get('streak', 0)) >= 1 and w.get('strong')}
                        
                        perfecte_matches = []
                        bijna_matches = [] 

                        for ref, zin in bijbel_db.items():
                            if ref in st.session_state.geziene_verzen: continue
                            
                            lexicale_items = [w for w in zin if w.get('strong')]
                            if len(lexicale_items) < 3: continue 

                            onbekende_tellers = sum(1 for w in lexicale_items if str(w['strong']) not in bekende_strongs_all)

                            if onbekende_tellers == 0: perfecte_matches.append((ref, zin))
                            elif onbekende_tellers == 1: bijna_matches.append((ref, zin))

                        selectie_pool = perfecte_matches if perfecte_matches else bijna_matches
                        
                        if not selectie_pool:
                            st.warning("Er zijn op dit moment geen ongelezen verzen gevonden die volledig binnen je beheerste woordenschat vallen. Train nog enkele nieuwe lessen in Tabblad 1.")
                        else:
                            gekozen_v = r_engine.choice(selectie_pool)
                            st.session_state.huidig_vers = gekozen_v[1]
                            st.session_state.huidige_vers_referentie = gekozen_v[0]
                            st.session_state.geziene_verzen.append(gekozen_v[0])
                            st.session_state.geziene_verzen = st.session_state.geziene_verzen[-100:]
                            
                            if not perfecte_matches and bijna_matches:
                                st.toast("ℹ️ Geen vers met 100% bekende woorden gevonden; dit vers bevat exact 1 nieuw woord (Krashen i+1 principe).")

                st.write("---")

                if st.session_state.huidig_vers:
                    st.markdown(f"### 📖 {st.session_state.huidige_vers_referentie}")
                    html_zin = ""; oefen_woorden = []
                    
                    for w in st.session_state.huidig_vers:
                        _nl_g = w.get('vertaling_nl', '')
                        _bsb_g = w.get('vertaling_bsb', '')
                        _kop_g = _nl_g if _nl_g else _bsb_g
                        _anker_g = f"\nEN: {_bsb_g}" if _bsb_g.strip() else ""
                        tooltip = f"{_kop_g}\n{w['parsing_info']}{_anker_g}".replace("'", "&#39;").replace('"', "&quot;")
                        extra_style = ""
                        if kleur_naamvallen:
                            if "Nom" in w['parsing_info']: extra_style += "color: #33ccff;"
                            elif "Gen" in w['parsing_info']: extra_style += "color: #28a745;"
                            elif "Dat" in w['parsing_info']: extra_style += "color: #6f42c1;"
                            elif "Acc" in w['parsing_info']: extra_style += "color: #dc3545;"
                            elif "Voc" in w['parsing_info']: extra_style += "color: #fd7e14;"
                        
                        if kleur_voegwoorden and ("Voegwoord" in w['parsing_info'] or "Conjunction" in w['parsing_info']): extra_style += "background-color: #ffd700; color: #000; padding: 0 4px; border-radius: 4px;"

                        clean_w = normaliseer_accent(w['grieks'])
                        is_stam = clean_w in actieve_stam_vormen
                        is_bekend = w.get('strong') and str(w['strong']) in actieve_strongs
                        
                        if is_stam and kleur_stamtijden: css_class = "woord-stamtijd"
                        elif is_bekend: css_class = "woord-bekend"
                        else: css_class = "woord-onbekend"

                        if css_class in ["woord-bekend", "woord-stamtijd"]:
                            if "1." in tekst_modus:
                                if is_bekend: 
                                    b_woord = actieve_strongs[str(w['strong'])]
                                    hover_text = f"Les {b_woord.get('les', '?')} | {b_woord.get('grieks', '?')} → {b_woord.get('nederlands', '')}\n{tooltip}"
                                else: 
                                    hover_text = f"{actieve_stam_vormen[clean_w]['praesens']} → {actieve_stam_vormen[clean_w]['betekenis']}\n{tooltip}"
                            else:
                                # HIER IS HET VANGNET TERUGGEPLAATST:
                                hover_text = f"❓ [Oefenwoord] Beantwoord de opdracht hieronder.\n{tooltip}"
                            
                            # Escapen buiten de f-string: backslashes in een f-string-expressie zijn pas
                            # geldig vanaf Python 3.12, en de devcontainer draait op 3.11.
                            hover_esc = hover_text.replace("'", "&#39;").replace('"', "&quot;")
                            html_zin += f"<span class='{css_class} mobile-tooltip' tabindex='0' style='{extra_style}'>{w['grieks']}<span class='tooltiptext'>{hover_esc}</span></span>{w['interpunctie']} "
                            oef_dict = w.copy(); oef_dict['is_stamtijd'] = is_stam; oef_dict['stam_info'] = actieve_stam_vormen[clean_w] if is_stam else None; oefen_woorden.append(oef_dict)
                        else: 
                            html_zin += f"<span class='{css_class} mobile-tooltip' tabindex='0' style='{extra_style}; border-bottom: 1px dotted #555;'>{w['grieks']}<span class='tooltiptext'>{tooltip}</span></span>{w['interpunctie']} "
                    
                    if kleur_naamvallen: st.markdown("**(Kleurlegenda: <span style='color:#33ccff'>Nom</span> | <span style='color:#28a745'>Gen</span> | <span style='color:#6f42c1'>Dat</span> | <span style='color:#dc3545'>Acc</span> | <span style='color:#fd7e14'>Voc</span>)**", unsafe_allow_html=True)
                    st.markdown(f"<div class='grieks-zin'>{html_zin}</div>", unsafe_allow_html=True)
                    st.caption("ℹ️ Tik op (of hover over) een woord om de vertaling en ontleding te zien. Cyaan/Paarse woorden komen uit je actieve lessen.")
                    
                    if oefen_woorden and "1." not in tekst_modus:
                        st.write("### 📝 Oefen je woorden in context")
                        for idx, w in enumerate(oefen_woorden):
                            if w['is_stamtijd'] and kleur_stamtijden:
                                stam_data = w['stam_info']
                                st.markdown(f"**<div style='color:#d63384'>[Stamtijd]</div> {w['grieks']}**", unsafe_allow_html=True)
                                forceer_focus()
                                with st.form(key=f"form_lees_stam_{idx}"):
                                    c_gram, c_bet = st.columns(2)
                                    with c_gram: p_gram = st.selectbox("Tijd & Diathese", ["", "Futurum Actief/Medium", "Aoristus Actief/Medium", "Aoristus Passief", "Perfectum Actief", "Perfectum Medium/Passief"], key=f"s_g_{idx}"); p_praesens = st.text_input("Praesens:", key=f"s_p_{idx}")
                                    with c_bet: p_betekenis = st.text_input("Betekenis:", key=f"s_b_{idx}")
                                    
                                    if st.form_submit_button("✓ Nakijken"):
                                        registreer_oefening()
                                        if (p_gram == stam_data['tijd_diathese']) and (normaliseer_accent(naar_grieks_transliteratie(p_praesens)) == normaliseer_accent(stam_data['praesens'])) and check_betekenis(p_betekenis, stam_data['betekenis']): st.success(f"✓ Goed! **{w['grieks']}** is de {stam_data['tijd_diathese']} van {stam_data['praesens']}.")
                                        else: st.error(f"✗ Onjuist. Het is de **{stam_data['tijd_diathese']}** van **{stam_data['praesens']}** (Betekenis: **{stam_data['betekenis']}**).")
                            else:
                                basis = actieve_strongs[str(w['strong'])]; in_scope = True; norm_basis = normaliseer_accent(basis['grieks']); is_ww = "Werkwoord" in w['parsing_info'] or basis.get('woordsoort') == 'ww'
                                
                                if master_niveau == "Grieks 1":
                                    if is_ww: in_scope = (norm_basis == "ειμι") or (("Actief" in w['parsing_info']) and not any(x in w['parsing_info'] for x in ["Participium", "Conjunctivus", "Optativus"]))
                                    else: in_scope = norm_basis.endswith(('ος', 'ον', 'α', 'η', 'ω', 'υ', 'ουτος', 'αυτη', 'τουτο')) or norm_basis in ['ο', 'η', 'το', 'εγω', 'συ']
                                elif master_niveau == "Grieks 2":
                                    if is_ww: in_scope = not any(x in w['parsing_info'] for x in ["Conjunctivus", "Optativus"])
                                    if norm_basis.endswith('μι') and norm_basis != "ειμι": in_scope = False

                                st.markdown(f"**{w['grieks']}**" if "4." in tekst_modus else f"**{w['grieks']}** (Basis: {basis['grieks']})")
                                
                                if "2." in tekst_modus: 
                                    if f"mc_opties_{idx}" not in st.session_state or st.session_state.get(f"mc_vers_{idx}") != st.session_state.huidige_vers_referentie:
                                        # Gecorrigeerde aanroep via de alias r_engine
                                        r_engine.seed(str(st.session_state.huidige_vers_referentie) + str(idx))
                                        afleiders = list(set([i['nederlands'] for i in st.session_state.data if i['nederlands'] != basis['nederlands']]))
                                        opties = [basis['nederlands']] + r_engine.sample(afleiders, min(3, len(afleiders)))
                                        r_engine.shuffle(opties); r_engine.seed()
                                        st.session_state[f"mc_opties_{idx}"] = opties; st.session_state[f"mc_vers_{idx}"] = st.session_state.huidige_vers_referentie
                                        
                                    cols = st.columns(2)
                                    for c_idx, optie in enumerate(st.session_state[f"mc_opties_{idx}"]):
                                        if cols[c_idx % 2].button(optie, key=f"mc_{idx}_{c_idx}_{w['grieks']}"):
                                            registreer_oefening(basis)
                                            if optie == basis['nederlands']: 
                                                basis['streak'] = int(basis.get('streak', 0)) + 1; basis['score_goed'] = int(basis.get('score_goed', 0)) + 1; trigger_save()
                                                st.success(f"✓ Goed! **{w['grieks']}** = {basis['nederlands']} ({w['parsing_info']})")
                                            else: 
                                                basis['streak'] = max(0, int(basis.get('streak', 0)) - 1); basis['score_fout'] = int(basis.get('score_fout', 0)) + 1; trigger_save()
                                                st.error(f"✗ Fout. Het was: {basis['nederlands']}")
                                    
                                elif "3." in tekst_modus: 
                                    forceer_focus()
                                    with st.form(key=f"form_typ_{idx}"):
                                        inp = st.text_input("Woordenboekvertaling:")
                                        if st.form_submit_button("✓ Nakijken"):
                                            registreer_oefening(basis)
                                            if check_betekenis(inp, basis['nederlands']): basis['streak'] = int(basis.get('streak', 0)) + 3; basis['score_goed'] = int(basis.get('score_goed', 0)) + 1; trigger_save(); st.success(f"✓ Goed! **{w['grieks']}** = {basis['nederlands']} ({w['parsing_info']})")
                                            else: basis['streak'] = max(0, int(basis.get('streak', 0)) - 1); basis['score_fout'] = int(basis.get('score_fout', 0)) + 1; trigger_save(); st.error(f"✗ Fout. Het is: {basis['nederlands']}")
                                            
                                elif "4." in tekst_modus:
                                    if not in_scope: st.success(f"*(Buiten scope voor {master_niveau})* **{w['grieks']}** = {basis['nederlands']} ({w['parsing_info']})")
                                    else:
                                        p_soort = st.selectbox("Woordsoort", ["", "Zelfst. nw.", "Werkwoord", "Bijv. nw.", "Lidwoord", "Voornaamwoord", "Overig"], key=f"soort_{idx}"); t_inp = st.text_input("Woordenboekvertaling:", key=f"bet_{idx}")
                                        p_naam, p_get, p_ges, p_tijd, p_wijs, p_pers, p_diat = "", "", "", "", "", "", ""
                                        
                                        if p_soort in ["Zelfst. nw.", "Bijv. nw.", "Lidwoord", "Voornaamwoord"]:
                                            mc1, mc2, mc3 = st.columns(3)
                                            with mc1: p_naam = st.selectbox("Naamval", ["", "N.v.t.", "Nom", "Gen", "Dat", "Acc", "Voc"], key=f"nv_{idx}")
                                            with mc2: p_get = st.selectbox("Getal", ["", "N.v.t.", "ev", "mv"], key=f"gt_{idx}")
                                            with mc3: p_ges = st.selectbox("Geslacht", ["", "N.v.t.", "M", "V", "O"], key=f"gs_{idx}")
                                        elif p_soort == "Werkwoord":
                                            mc1, mc2, mc3 = st.columns(3)
                                            with mc1: p_tijd = st.selectbox("Tijd", ["", "Praesens", "Imperfectum", "Futurum", "Aoristus", "Perfectum", "Plusquamperfectum"], key=f"td_{idx}")
                                            with mc2: p_wijs = st.selectbox("Wijs", ["", "Indicativus", "Conjunctivus", "Optativus", "Imperativus", "Infinitivus", "Participium"], key=f"wj_{idx}")
                                            with mc3: p_diat = st.selectbox("Diathese", ["", "Actief", "Medium", "Passief", "Medium/Passief"], key=f"di_{idx}")
                                            if p_wijs == "Participium":
                                                c1, c2, c3 = st.columns(3)
                                                with c1: p_naam = st.selectbox("Naamval", ["", "N.v.t.", "Nom", "Gen", "Dat", "Acc", "Voc"], key=f"nv_ptc_{idx}")
                                                with c2: p_get = st.selectbox("Getal", ["", "N.v.t.", "ev", "mv"], key=f"gt_ptc_{idx}")
                                                with c3: p_ges = st.selectbox("Geslacht", ["", "N.v.t.", "M", "V", "O"], key=f"gs_ptc_{idx}")
                                            else:
                                                c1, c2 = st.columns(2)
                                                with c1: p_pers = st.selectbox("Persoon", ["", "N.v.t.", "1e pers.", "2e pers.", "3e pers."], key=f"ps_{idx}")
                                                with c2: p_get = st.selectbox("Getal", ["", "N.v.t.", "ev", "mv"], key=f"gt_ww_{idx}")
                                                
                                        # Dezelfde hulp als in de Ontleden-tab: klankwetten/samentrekkingen + het rijtje.
                                        _lt_lemma = str(basis.get('grieks', ''))
                                        _lt_ginfo = str(basis.get('grieks_info', '')) or _lt_lemma
                                        toon_opbouw_hulp(w.get('grieks', ''), _lt_lemma, w.get('parsing_info', ''),
                                                         _lt_ginfo, uitgeklapt=False, strong=w.get('strong'))
                                        toon_rijtje_hulp(w.get('parsing_info', ''), _lt_lemma, _lt_ginfo,
                                                         sleutel=f"lt_{idx}", uitgeklapt=False)
                                        toon_vertaalhulp(w.get('parsing_info', ''), sleutel=f"lt_{idx}")

                                        if st.button("Controleer Analyse", key=f"chk_{idx}"):
                                            registreer_oefening(basis)
                                            if check_betekenis(t_inp, basis['nederlands']) and check_bijbel_parsing_uitgebreid(p_soort, p_naam, p_get, p_ges, p_tijd, p_wijs, p_diat, p_pers, w['parsing_info']):
                                                basis['streak'] = int(basis.get('streak', 0)) + 3; basis['score_goed'] = int(basis.get('score_goed', 0)) + 1; dagdoel_plus('verzen'); trigger_save(); st.success(f"✓ Volledig correct! ({w['parsing_info']})")
                                            else:
                                                basis['streak'] = max(0, int(basis.get('streak', 0)) - 1); basis['score_fout'] = int(basis.get('score_fout', 0)) + 1; trigger_save(); st.error(f"✗ Net niet. Het juiste antwoord: {w['parsing_info']} | Betekenis: {basis['nederlands']}")
                                                
                    st.write("---")
                    st.write("### ✍️ Zinsvertaling")
                    user_vertaling = st.text_area("Vertaal de hele zin naar het Nederlands:")
                    if st.button("👁️ Toon antwoord"):
                        def _eerste_betekenis(g):
                            # Pak alleen de eerste betekenis (tot eerste komma/slash) voor een leesbare zin;
                            # strip eventuele naamval-aanduiding als "(+gen.)" vooraan.
                            g = str(g).strip()
                            g = re.sub(r'^\(\+?[^)]*\)\s*', '', g)
                            g = re.split(r'[,/;]', g)[0].strip()
                            return g
                        _nl_zin = ' '.join([_eerste_betekenis(w.get('vertaling_nl') or w.get('vertaling_bsb', '')) for w in st.session_state.huidig_vers]).strip()
                        _bsb_zin = ' '.join([w.get('vertaling_bsb', '') for w in st.session_state.huidig_vers if w.get('vertaling_bsb', '').strip()]).strip()
                        st.success(f"**Nederlandse glosse-vertaling (woord-voor-woord):**\n\n{_nl_zin}")
                        st.caption("Alleen de kernbetekenis per woord; hover over de Griekse woorden hierboven voor alle betekenissen.")
                        if _bsb_zin:
                            st.caption(f"Engels (BSB) ter controle: {_bsb_zin}")
                        

        # ==========================================
        # TAB 8: GRAMMATICA (zoeken · bestuderen · contractietrainer)
        # ==========================================
        if _TOON[7]:
         with menu[7]:
            st.subheader("📐 Grammatica")
            gram_db = laad_grammatica_db()

            if gram_db is None:
                st.warning("Bestand 'grammatica_index.json' ontbreekt of is niet ingeladen.")
            elif not FITZ_BESCHIKBAAR or open_grammatica_pdf() is None:
                st.error("De grammatica-slides konden niet worden geopend. Controleer of 'grammatica_overzicht.pdf' aanwezig is en of PyMuPDF is geïnstalleerd (voeg `pymupdf` toe aan requirements.txt).")
            else:
                items = gram_db["items"]
                overzichten = gram_db.get("overzichten", {})
                slide_index = gram_db.get("slide_index", {})
                book_toc = gram_db.get("book_toc", [])

                if 'gram_stats' not in st.session_state or st.session_state.gram_stats is None:
                    st.session_state.gram_stats = {}

                def toon_boekverwijzingen(info, compact=True):
                    refs = info.get("boek_refs", [])
                    if not refs:
                        return
                    regels = []
                    for e in refs:
                        deel = e["deel"]
                        regels.append(f"• **Deel {deel}**, hfdst. {e['hoofdstuk']} — {e['sub']} · boek p. {e['boekpagina']} _(PDF-pag. {e['pdf_pagina']})_")
                    with st.expander(f"📖 Vindplaats in het handboek ({len(refs)})", expanded=not compact):
                        st.markdown("\n".join(regels))
                        st.caption("⚠️ Automatisch gekoppeld via de inhoudsopgaven — controleer de exacte paragraaf zelf even in het boek.")

                gram_modus = st.radio(
                    "Kies:",
                    ["🔎 Zoeken", "📖 Bestuderen", "🔀 Contractietrainer", "📊 Voortgang"],
                    horizontal=True
                )
                st.write("---")

                # ==========================================================
                # MODUS: ZOEKEN
                # ==========================================================
                if gram_modus.startswith("🔎"):
                    st.markdown("#### Zoek een grammaticaal onderwerp of term")
                    st.caption("Typ bijv. *genitivus absolutus*, *aoristus*, *αὐτός*, *contractie* of *voorwaardelijke zin*. Grieks mag mét of zonder accenten, of getypt in gewone letters (*logos* → λόγος, *didwmi* → δίδωμι, θ=q, ξ=c, ω=w, ψ=y, η=h). Je krijgt de slide(s) én de vindplaats in het handboek.")
                    zoek = st.text_input("Zoekterm:", key="gram_zoek", placeholder="genitivus absolutus")

                    if zoek and len(zoek.strip()) >= 2:
                        q = zoek.strip().lower()
                        q_woorden = [w for w in re.split(r"\s+", q) if w]

                        def _ontaccent(s):
                            s = unicodedata.normalize("NFD", s.lower())
                            return "".join(c for c in s if unicodedata.category(c) != "Mn")
                        # Grieks -> Latijnse sleutel: zo matcht getypte transliteratie ('logos')
                        # op het Griekse trefwoord (λόγος). Eén richting = robuust (ς/σ, spiritus).
                        _GR2LAT = {'α':'a','β':'b','γ':'g','δ':'d','ε':'e','ζ':'z','η':'h','θ':'q',
                                   'ι':'i','κ':'k','λ':'l','μ':'m','ν':'n','ξ':'c','ο':'o','π':'p',
                                   'ρ':'r','σ':'s','ς':'s','τ':'t','υ':'u','φ':'f','χ':'x','ψ':'y','ω':'w'}
                        def _translit(s):
                            return "".join(_GR2LAT.get(c, c) for c in _ontaccent(s))
                        q_norm = _ontaccent(q)
                        q_key = _translit(q)
                        qn_woorden = [_ontaccent(w) for w in q_woorden]

                        # Score per G-item: titel > trefwoorden > OCR van slides
                        resultaten = []
                        for g_str, info in items.items():
                            titel = info["titel"].lower()
                            trefw = " ".join(info.get("trefwoorden", [])).lower()
                            ocr_all = " ".join(
                                slide_index.get(str(p), {}).get("ocr", "")
                                for p in range(info["pdf_start"], info["pdf_eind"] + 1)
                            ).lower()
                            titel_n = _ontaccent(titel)
                            trefw_n = _ontaccent(trefw)
                            trefw_key = _translit(trefw)

                            score = 0
                            if q in titel: score += 100
                            if q_norm and q_norm in trefw_n: score += 60  # Griekse trefwoord-match (accentvrij)
                            if q_key and len(q_key) >= 3 and q_key in trefw_key: score += 45  # getypte transliteratie
                            for w, wn in zip(q_woorden, qn_woorden):
                                if w in titel: score += 40
                                if w in trefw: score += 25
                                elif wn and wn in trefw_n: score += 22  # accentvrije Griekse match
                                if w in ocr_all: score += 6
                            # fuzzy op titelwoorden (typefouten)
                            for w in q_woorden:
                                for tw in titel.split():
                                    if len(w) >= 4 and difflib.SequenceMatcher(None, w, tw).ratio() > 0.85:
                                        score += 15
                            if score > 0:
                                resultaten.append((score, int(g_str), info))

                        resultaten.sort(key=lambda x: (-x[0], x[1]))

                        if not resultaten:
                            st.info("Niets gevonden. Probeer een andere term (bijv. de Latijnse naam of een kernwoord).")
                        else:
                            st.success(f"{len(resultaten)} onderwerp(en) gevonden.")
                            for score, g, info in resultaten[:8]:
                                with st.container(border=True):
                                    st.markdown(f"**G{g} · {info['titel']}**  \n_{info['thema']} · {info['aantal']} slide(s)_")
                                    kw = info.get("trefwoorden", [])
                                    if kw:
                                        st.caption("Trefwoorden: " + ", ".join(kw[:8]))
                                    c1, c2 = st.columns([1, 1])
                                    with c1:
                                        if st.button(f"📖 Bekijk slides van G{g}", key=f"zoek_naar_{g}", use_container_width=True):
                                            st.session_state["gram_spring_naar"] = g
                                            st.session_state["gram_modus_forceer"] = "📖 Bestuderen"
                                            st.rerun()
                                    with c2:
                                        first = render_slide(info["pdf_start"] + (1 if info["aantal"] > 1 else 0), dpi=70)
                                        if first:
                                            st.image(first, use_container_width=True)
                                    toon_boekverwijzingen(info, compact=True)

                # ==========================================================
                # MODUS: BESTUDEREN
                # ==========================================================
                elif gram_modus.startswith("📖"):
                    themas = ["Alle thema's", "Naamwoorden", "Voornaamwoorden", "Werkwoorden", "Syntaxis & overig"]
                    gekozen_thema = st.selectbox("Filter op thema:", themas, key="study_thema")

                    g_nummers = sorted(items.keys(), key=lambda x: int(x))
                    if gekozen_thema != "Alle thema's":
                        g_nummers = [g for g in g_nummers if items[g]["thema"] == gekozen_thema]

                    if not g_nummers:
                        st.info("Geen onderwerpen in dit thema.")
                    else:
                        labels = {g: f"G{g} · {items[g]['titel']}" for g in g_nummers}
                        # eventueel doorgesprongen vanuit de zoekfunctie
                        default_idx = 0
                        spring = st.session_state.pop("gram_spring_naar", None)
                        if spring is not None and str(spring) in g_nummers:
                            default_idx = g_nummers.index(str(spring))
                        gekozen_g = st.selectbox(
                            "Kies een grammatica-onderwerp:", g_nummers,
                            index=default_idx, format_func=lambda g: labels[g], key="study_gitem"
                        )
                        info = items[gekozen_g]
                        start, eind, aantal = info["pdf_start"], info["pdf_eind"], info["aantal"]

                        st.markdown(f"### G{gekozen_g} · {info['titel']}")
                        st.caption(f"Thema: {info['thema']} · {aantal} slide(s)")
                        toon_boekverwijzingen(info, compact=True)

                        bladerkey = f"study_pos_{gekozen_g}"
                        if bladerkey not in st.session_state:
                            st.session_state[bladerkey] = start
                        st.session_state[bladerkey] = max(start, min(eind, st.session_state[bladerkey]))
                        huidige = st.session_state[bladerkey]

                        c_prev, c_mid, c_next = st.columns([1, 2, 1])
                        with c_prev:
                            if st.button("⬅️ Vorige", key=f"prev_{gekozen_g}", disabled=(huidige <= start), use_container_width=True):
                                st.session_state[bladerkey] = huidige - 1; st.rerun()
                        with c_mid:
                            st.markdown(f"<div style='text-align:center;padding-top:8px;font-weight:bold;'>Slide {huidige-start+1} / {aantal}</div>", unsafe_allow_html=True)
                        with c_next:
                            if st.button("Volgende ➡️", key=f"next_{gekozen_g}", disabled=(huidige >= eind), use_container_width=True):
                                st.session_state[bladerkey] = huidige + 1; st.rerun()

                        png = render_slide(huidige, dpi=130)
                        if png:
                            st.image(png, use_container_width=True)
                        if aantal > 1:
                            with st.expander(f"📑 Direct naar slide (1–{aantal})"):
                                spr = st.slider("Slide", 1, aantal, huidige - start + 1, key=f"slider_{gekozen_g}")
                                if start + spr - 1 != huidige:
                                    st.session_state[bladerkey] = start + spr - 1; st.rerun()

                        st.write("---")
                        with st.expander("📚 Losse overzichten & samenvattingen achterin"):
                            if overzichten:
                                ov_keys = sorted(overzichten.keys(), key=lambda x: int(x))
                                gekozen_ov = st.selectbox("Kies een overzicht:", ov_keys,
                                    format_func=lambda k: overzichten[k], key="overzicht_keuze")
                                png_ov = render_slide(int(gekozen_ov), dpi=130)
                                if png_ov:
                                    st.image(png_ov, use_container_width=True)
                            else:
                                st.caption("Geen losse overzichten gevonden.")

                # ==========================================================
                # MODUS: CONTRACTIETRAINER
                # ==========================================================
                elif gram_modus.startswith("🔀"):
                    cdb = laad_contractie_db()
                    if cdb is None:
                        st.warning("Bestand 'contractie_data.json' ontbreekt.")
                    else:
                        st.markdown("#### 🔀 Contractie- & samensmeltingstrainer")
                        st.caption("Oplopende moeilijkheid: eerst de regel herkennen, daarna zelf toepassen. Traint de σ-klankwetten, de verba contracta en het augment.")

                        niveau = st.select_slider(
                            "Niveau",
                            options=["1 · Herken de klankklasse", "2 · Voorspel de uitkomst", "3 · Vorm zelf (typen)"],
                            key="contr_niveau"
                        )
                        soort = st.radio("Oefenstof:", ["σ-samensmelting (fut./aor.)", "Verba contracta (klinkers)", "Augment (verleden tijd)"], horizontal=True, key="contr_soort")
                        st.write("---")

                        # bouw een platte lijst van opgaven op basis van soort.
                        # LET OP: 'hint' bevat NOOIT het antwoord (geen 'naar'-vorm) — anders spoiler.
                        def bouw_opgaven():
                            opg = []
                            if soort.startswith("σ"):
                                for regel in cdb["sigma"]:
                                    for (van, naar, bet) in regel["vb"]:
                                        opg.append({"van": van, "naar": naar, "hint": bet,
                                                    "klasse": regel["klasse"], "regel": regel["regel"],
                                                    "uitkomst": regel["uitkomst"]})
                            elif soort.startswith("Verba"):
                                for regel in cdb["contracta"]:
                                    # 'vb' bevat het antwoord, dus die gebruiken we NIET als hint
                                    opg.append({"van": regel["combo"], "naar": regel["uitkomst"],
                                                "hint": f"stam op -{regel['stam']}", "klasse": f"stam op -{regel['stam']}",
                                                "regel": f"{regel['combo']} → {regel['uitkomst']}",
                                                "uitkomst": regel["uitkomst"]})
                            else:
                                for regel in cdb["augment"]:
                                    for (van, naar) in regel["vb"]:
                                        opg.append({"van": van, "naar": naar, "hint": f"begint met {regel['begin']}",
                                                    "klasse": f"begint met {regel['begin']}", "regel": regel["regel"],
                                                    "uitkomst": naar})
                            return opg

                        opgaven = bouw_opgaven()
                        skey = f"contr_state_{soort}_{niveau}"
                        if skey not in st.session_state:
                            st.session_state[skey] = {"idx": r_engine.randrange(len(opgaven)), "goed": 0, "totaal": 0, "feedback": None}
                        stt = st.session_state[skey]
                        opg = opgaven[stt["idx"]]

                        # --- Feedbackbanner van de vórige opgave bovenaan (flow zoals bij woorden leren) ---
                        if stt.get("feedback"):
                            fb = stt["feedback"]
                            if fb["type"] == "success":
                                st.success(fb["msg"])
                            else:
                                st.error(fb["msg"])
                            stt["feedback"] = None
                        if stt["totaal"]:
                            st.caption(f"Deze sessie: {stt['goed']}/{stt['totaal']} goed")

                        def _norm(s):
                            s = unicodedata.normalize("NFD", str(s).strip().lower())
                            return "".join(c for c in s if unicodedata.category(c) != "Mn")

                        def volgende_opgave(goed, banner):
                            stt["totaal"] += 1
                            if goed:
                                stt["goed"] += 1
                            stt["feedback"] = {"type": "success" if goed else "error", "msg": banner}
                            stt["idx"] = r_engine.randrange(len(opgaven))
                            # Duurzame voortgang per contractie-soort (overleeft herladen én niveauwissel,
                            # i.t.t. de sessie-teller hierboven). Wordt getoond in de Voortgang-modus.
                            if not isinstance(st.session_state.get('gram_stats'), dict):
                                st.session_state.gram_stats = {}
                            _gk = f"contr::{soort}"
                            _gs = st.session_state.gram_stats.setdefault(_gk, {"g": 0, "f": 0, "streak": 0})
                            if goed:
                                _gs["g"] = int(_gs.get("g", 0)) + 1
                                _gs["streak"] = int(_gs.get("streak", 0)) + 1
                            else:
                                _gs["f"] = int(_gs.get("f", 0)) + 1
                                _gs["streak"] = 0
                            registreer_oefening()
                            trigger_save()
                            st.rerun()

                        # ---- NIVEAU 1: herken de klasse ----
                        if niveau.startswith("1"):
                            st.markdown(f"### {opg['van']}  →  ?")
                            if soort.startswith("σ"):
                                st.write("Tot welke klankklasse behoort de stam?")
                                opties = [r["klasse"] for r in cdb["sigma"]]
                                goed_antwoord = opg["klasse"]
                            elif soort.startswith("Verba"):
                                st.write("Welke uitkomst heeft deze klinkercombinatie?")
                                opties = sorted({r["uitkomst"] for r in cdb["contracta"]})
                                goed_antwoord = opg["uitkomst"]
                            else:
                                st.write("Welke augment-regel geldt hier?")
                                opties = [r["regel"] for r in cdb["augment"]]
                                goed_antwoord = opg["regel"]
                            keuze = st.radio("Kies:", opties, index=None, key=f"n1_{skey}_{stt['idx']}")
                            if st.button("✓ Nakijken", key=f"chk1_{skey}", type="primary"):
                                if keuze is None:
                                    st.warning("Kies eerst een optie.")
                                else:
                                    goed = (keuze == goed_antwoord)
                                    banner = (f"✅ Juist! {opg['van']} → {opg['naar']} ({opg['regel']})" if goed
                                              else f"❌ Het was **{goed_antwoord}**. {opg['van']} → {opg['naar']} ({opg['regel']})")
                                    volgende_opgave(goed, banner)

                        # ---- NIVEAU 2: voorspel de uitkomstvorm (meerkeuze) ----
                        elif niveau.startswith("2"):
                            st.markdown(f"### {opg['van']}  →  ?")
                            st.caption("Welke vorm ontstaat er na de samensmelting/contractie?")
                            # De opties EENMALIG per opgave vastleggen. Bij elke rerun opnieuw shuffelen
                            # is fout: Streamlit onthoudt de radio-keuze als index, dus na de rerun wees
                            # die naar een andere vorm en werd het verkeerde antwoord nagekeken.
                            if stt.get("opties_voor") != stt["idx"]:
                                alle_naar = list({o["naar"] for o in opgaven})
                                afleiders = [x for x in alle_naar if x != opg["naar"]]
                                r_engine.shuffle(afleiders)
                                _o = afleiders[:3] + [opg["naar"]]
                                r_engine.shuffle(_o)
                                stt["opties"] = _o
                                stt["opties_voor"] = stt["idx"]
                            opties = stt.get("opties") or [opg["naar"]]
                            keuze = st.radio("Wat is de juiste vorm?", opties, index=None, key=f"n2_{skey}_{stt['idx']}")
                            if st.button("✓ Nakijken", key=f"chk2_{skey}", type="primary"):
                                if keuze is None:
                                    st.warning("Kies eerst een optie.")
                                else:
                                    goed = (keuze == opg["naar"])
                                    banner = (f"✅ Juist! {opg['van']} → {opg['naar']} — {opg['regel']}" if goed
                                              else f"❌ Het was **{opg['naar']}**. {opg['van']} → {opg['naar']} — {opg['regel']}")
                                    volgende_opgave(goed, banner)

                        # ---- NIVEAU 3: zelf typen ----
                        else:
                            st.markdown(f"### {opg['van']}  →  ?")
                            st.caption("Typ de gecontraheerde/samengesmolten vorm (Grieks). Kleine accentafwijkingen worden soepel nagekeken.")
                            with st.form(f"form_n3_{skey}_{stt['idx']}"):
                                antwoord = st.text_input("Jouw vorm:", key=f"n3_{skey}_{stt['idx']}")
                                verzonden = st.form_submit_button("✓ Nakijken", type="primary")
                            if verzonden:
                                if not antwoord.strip():
                                    st.warning("Typ eerst een vorm.")
                                else:
                                    exact = _norm(antwoord) == _norm(opg["naar"])
                                    dichtbij = difflib.SequenceMatcher(None, _norm(antwoord), _norm(opg["naar"])).ratio() > 0.8
                                    goed = exact or dichtbij
                                    if exact:
                                        banner = f"✅ Precies! {opg['van']} → {opg['naar']} ({opg['regel']})"
                                    elif dichtbij:
                                        banner = f"✅ Goed (op accenten na). Correct: {opg['naar']} ({opg['regel']})"
                                    else:
                                        banner = f"❌ Het was **{opg['naar']}** ({opg['regel']})"
                                    volgende_opgave(goed, banner)

                        with st.expander("📋 Toon alle regels (spiekbriefje)"):
                            if soort.startswith("σ"):
                                for regel in cdb["sigma"]:
                                    st.markdown(f"**{regel['klasse']}** ({regel['medeklinkers']}) → {regel['uitkomst']}  \n_{regel['regel']}_")
                            elif soort.startswith("Verba"):
                                for regel in cdb["contracta"]:
                                    st.markdown(f"stam -{regel['stam']}: **{regel['combo']} → {regel['uitkomst']}** _(bv. {regel['vb']})_")
                            else:
                                for regel in cdb["augment"]:
                                    st.markdown(f"**{regel['begin']}**: {regel['regel']}")

                # ==========================================================
                # MODUS: VOORTGANG
                # ==========================================================
                else:
                    # --- Contractietrainer: echte, duurzame voortgang per soort ---
                    st.markdown("### 🔀 Contractietrainer-voortgang")
                    st.caption("Je oefeningen in de Contractietrainer tellen hier mee. Vanaf 3 goed op rij = 'op weg', vanaf 8 = 'beheerst'.")
                    _contr_soorten = ["σ-samensmelting (fut./aor.)", "Verba contracta (klinkers)", "Augment (verleden tijd)"]
                    _gstats = st.session_state.get('gram_stats') or {}
                    _crijen = []
                    for _cs in _contr_soorten:
                        _s = _gstats.get(f"contr::{_cs}", {})
                        _strk = int(_s.get("streak", 0))
                        if _strk >= 8: _st = "🟢 Beheerst"
                        elif _strk >= 3: _st = "🟡 Op weg"
                        elif _strk >= 1 or int(_s.get("g", 0)) or int(_s.get("f", 0)): _st = "🟠 Begonnen"
                        else: _st = "⚪ Nog niet"
                        _crijen.append({"Oefenstof": _cs, "Streak": _strk, "Goed": int(_s.get("g", 0)), "Fout": int(_s.get("f", 0)), "Status": _st})
                    st.dataframe(pd.DataFrame(_crijen), use_container_width=True, hide_index=True)
                    st.write("---")

                    st.markdown("### 📖 Onderwerpen in het handboek")
                    st.caption("Dit zijn de onderwerpen die je via 📖 Bestuderen kunt doornemen. De zelftoets met voortgang zit in de 🔀 Contractietrainer hierboven.")
                    rijen = []
                    for g in sorted(items.keys(), key=lambda x: int(x)):
                        rijen.append({"Onderwerp": f"G{g} · {items[g]['titel']}", "Thema": items[g]["thema"]})
                    df_gram = pd.DataFrame(rijen)
                    tf = st.selectbox("Toon thema:", ["Alle thema's", "Naamwoorden", "Voornaamwoorden", "Werkwoorden", "Syntaxis & overig"], key="voortgang_thema")
                    toon_df = df_gram if tf == "Alle thema's" else df_gram[df_gram["Thema"] == tf]
                    st.dataframe(toon_df, use_container_width=True, hide_index=True)

        # ==========================================
        # TAB 9: UITLEG & HULP (Masterclass Bijsluiter)
        # ==========================================
        if _TOON[8]:
         with menu[8]:
            st.subheader("ℹ️ Handboek & Achterliggende Logica")
            if nieuwe_gebruiker():
                st.success("👋 **Welkom!** Je begint hier omdat je nog niets hebt geoefend. Lees eventueel eerst "
                           "de korte uitleg hieronder (of download de PowerPoint), en ga daarna naar "
                           "**🚀 Woordenschat → 🎮 Leerpad** om te beginnen. Zodra je je eerste woorden hebt "
                           "gedaan, opent de app gewoon op Woordenschat.")

            # --- Downloadbare instructie-PowerPoint ---
            _ppt_pad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Instructie_GrieksPTHU.pptx")
            if os.path.exists(_ppt_pad):
                try:
                    with open(_ppt_pad, "rb") as _pf:
                        _ppt_bytes = _pf.read()
                    st.markdown("### 📥 Uitgebreide instructie (PowerPoint)")
                    st.caption("Een complete rondleiding door de app: wat je per tabblad kunt doen, én — met stroomdiagrammen — hoe de app bepaalt wélk woord je wanneer krijgt (fasen, spaced repetition, worstel-score, opbouw van een sessie). Handig als naslag of om te delen met anderen.")
                    st.download_button(
                        "📥 Download de instructie-PowerPoint",
                        data=_ppt_bytes,
                        file_name="Instructie_GrieksPTHU.pptx",
                        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    )
                    st.write("---")
                except Exception:
                    pass

            # --- Eenvoud-/geavanceerd-schakelaar ---
            st.markdown("### 🧭 Weergave-modus")
            _prefs_ui = st.session_state.get('ui_prefs')
            if not isinstance(_prefs_ui, dict):
                _prefs_ui = {}; st.session_state.ui_prefs = _prefs_ui
            _geav_nu = st.toggle(
                "Geavanceerde opties tonen",
                value=bool(_prefs_ui.get('geavanceerd', False)),
                key="ui_geavanceerd",
                help="Uit = eenvoudige modus: per onderdeel alleen het Leerpad en de kern. Aan = alle oefenvormen, filters en instellingen. Je keuze wordt onthouden."
            )
            if bool(_prefs_ui.get('geavanceerd', False)) != _geav_nu:
                # Alleen in-memory bijwerken (geen directe cloud-write → spaart lees-quotum);
                # wordt meegeschreven bij de eerstvolgende gewone opslag of bij uitloggen.
                _prefs_ui['geavanceerd'] = _geav_nu
                st.rerun()
            st.caption("Eenvoudig = rustige start (Leerpad + kern). Geavanceerd = alles: knelpunten, mastery, bijbelcontext, zelf samenstellen, koude herkenning, enz.")

            # --- Welke tabbladen wil je zien? ---
            st.markdown("### 🗂️ Welke tabbladen wil je zien?")
            st.caption("Zet uit wat je (nog) niet gebruikt — dan oogt de app een stuk rustiger. Je voortgang "
                       "blijft gewoon bewaard; je kunt een tabblad hier altijd weer aanzetten. "
                       "**📊 Voortgang** en **ℹ️ Uitleg & Hulp** blijven altijd staan.")
            _verborgen_nu = set((_prefs_ui.get('verborgen_tabs') or []))
            _nieuw_verborgen = set()
            _tk1, _tk2 = st.columns(2)
            for _i, (_sl, _lab) in enumerate(TAB_KEUZE):
                _kol = _tk1 if _i % 2 == 0 else _tk2
                if _sl in TAB_ALTIJD:
                    _kol.checkbox(_lab, value=True, disabled=True, key=f"tabzicht_{_sl}",
                                  help="Dit tabblad blijft altijd zichtbaar.")
                    continue
                _aan = _kol.checkbox(_lab, value=(_sl not in _verborgen_nu), key=f"tabzicht_{_sl}")
                if not _aan:
                    _nieuw_verborgen.add(_sl)
            if _nieuw_verborgen != _verborgen_nu:
                _prefs_ui['verborgen_tabs'] = sorted(_nieuw_verborgen)
                # Meteen wegschrijven: anders is je keuze na herladen weer weg (dit gebeurt zelden,
                # dus één extra opslag kan prima).
                trigger_save(forceer=True)
                st.rerun()
            if _nieuw_verborgen:
                st.caption(f"🙈 Verborgen: {len(_nieuw_verborgen)} tabblad(en). "
                           "Ze staan er nog wel — je ziet ze alleen niet in de balk.")
            st.write("---")

            st.markdown("### 📱 De App installeren als PWA (Beginscherm)")
            st.info("Je kunt deze webapplicatie opslaan op je telefoon. Hij opent dan razendsnel in full-screen zonder afleidende adresbalk.")
            st.markdown("* **iPhone (Safari):** Tik onderin op de deel-knop (vierkantje met pijltje omhoog) → *'Zet op beginscherm'*\n* **Android (Chrome):** Tik rechtsboven op de drie puntjes → *'Toevoegen aan startscherm'*")
            st.write("---")
            st.markdown("""
            ## 🏛️ Hoe deze app je laat leren

            De volledige uitleg — met stroomdiagrammen van hoe de app een woord kiest — staat in de
            **instructie-PowerPoint** bovenaan deze pagina. Hieronder de kern in het kort.

            ### Het uitgangspunt
            De app legt alleen een regel uit als hij die **aantoonbaar kan verantwoorden**. Kan hij een vorm
            niet met zekerheid ontleden of verklaren, dan zegt hij niets — liever geen uitleg dan een uitleg
            die er goed uitziet maar fout is. Elke regel is getoetst tegen het complete Nieuwe Testament.

            ### De vier fasen
            Elk woord heeft een **streak**: hoe vaak je het achter elkaar goed had.
            🌱 Nieuw (0) · 🏃 In training (1–15) · 🛡️ Beheerst (16–29) · 🏆 Mastery (30+).
            Goed antwoord levert +1 (meerkeuze) tot +3 (zelf typen) op; een fout kost 2 punten, waarna het
            woord terugzakt en dus weer vaker langskomt.

            ### Wat je wanneer krijgt
            Hoe hoger je streak, hoe langer een woord met rust gelaten wordt (van elke sessie tot ongeveer
            maandelijks). Daar bovenop krijgen woorden voorrang waar jij persoonlijk over struikelt — wat je
            gisteren fout had, komt vandaag met voorrang terug. Een sessie is een bewuste mix: een paar nieuwe
            woorden, de prille en de lopende stof, plus een opfrisser uit een eerdere les.

            ### Oefenvorm groeit mee
            Hetzelfde woord wordt steeds moeilijker gevraagd: **flashcard → meerkeuze → zelf typen**.
            Herkennen is makkelijker dan produceren, dus je hoeft pas te typen als het woord al zit.

            ### Nakijken is streng maar redelijk
            * **Typefouten:** een kleine vertyping in een langer woord wordt goedgekeurd — je ziet altijd het
              juiste antwoord erbij, dus een echte fout merk je meteen.
            * **Meerdere betekenissen:** staat er `zien / kijken` in de lijst, dan zijn dat allebei goede antwoorden.
            * **Haakjes:** uitleg tussen `()`, `[]` of `{}` hoeft je niet mee te typen.
            * **Synoniemen:** twee woorden met dezelfde betekenis worden nooit als elkaars foute antwoord gerekend.

            ### Fouten zijn stuurinformatie
            Twee keer fout (of één keer bij een woord dat je al beheerste)? Dan tik je het juiste antwoord over
            en komt het woord later terug — die keer zonder streakpunten, want overtypen is geen kennis.
            In **🔎 Ontleden** en **🔊 Klankwetten** kun je nooit punten verliezen: daar mag je vrij experimenteren.

            ---
            *Ontwikkeld voor Grieks Premaster PTHU. Vragen of suggesties? Mail naar:* **jtimmer@students.pthu.nl**
            """)

        # ==========================================
        # TAB 10: NL -> GRIEKS (ACTIEVE PRODUCTIE)
        # ==========================================
        if _TOON[9]:
         with menu[9]:
            st.subheader("✍️ NL → Grieks: actieve productie")
            st.info("Dit tabblad staat los van het gewone (passieve) woorden leren. Hier zie je de **Nederlandse** betekenis en reproduceer je zélf het Griekse woord — de moeilijkere, actieve vaardigheid. Je voortgang hier wordt apart bijgehouden en beïnvloedt je gewone streaks niet.")

            prod_db = laad_vocab_db()
            if not prod_db:
                st.warning("Woordenbestand ontbreekt.")
            else:
                if 'prod_stats' not in st.session_state or st.session_state.prod_stats is None:
                    st.session_state.prod_stats = {}
                if 'prod_sessie' not in st.session_state:
                    st.session_state.prod_sessie = []
                if 'prod_huidig' not in st.session_state:
                    st.session_state.prod_huidig = None
                if 'prod_feedback' not in st.session_state:
                    st.session_state.prod_feedback = None
                if 'prod_score' not in st.session_state:
                    st.session_state.prod_score = {"goed": 0, "totaal": 0}

                pc1, pc2 = st.columns([1, 2])
                with pc1:
                    alle_lessen_p = sorted(list(set(veilig_les_nummer(w) for w in prod_db)))
                    gekozen_p = st.multiselect("Kies lessen:", alle_lessen_p, default=alle_lessen_p[:2] if alle_lessen_p else [], key="prod_lessen")
                    invoer_type = _pref_keuze(st.radio, "Invoer:",
                        ["⌨️ Typen (Latijnse toetsen → Grieks)", "🔢 Meerkeuze (kies de juiste Griekse vorm)"],
                        'prod_invoer_pref', key="prod_invoer")
                    with st.expander("⌨️ Spiekbrief: Griekse letters typen"):
                        st.markdown("`a`=α `b`=β `g`=γ `d`=δ `e`=ε `z`=ζ `h`=η `q`=θ `i`=ι `k`=κ `l`=λ `m`=μ `n`=ν `c`=ξ `o`=ο `p`=π `r`=ρ `s`=σ/ς `t`=τ `u`=υ `f`=φ `x`=χ `y`=ψ `w`=ω")
                        st.caption("Accenten en spiritus hoeven niet: er wordt accent-ongevoelig nagekeken.")

                    if st.button("Start / nieuwe sessie", key="prod_start", type="primary", use_container_width=True):
                        pool = [w for w in prod_db if veilig_les_nummer(w) in gekozen_p and w.get('grieks') and w.get('nederlands')]
                        r_engine.shuffle(pool)
                        st.session_state.prod_sessie = pool[:15]
                        st.session_state.prod_score = {"goed": 0, "totaal": 0}
                        st.session_state.prod_feedback = None
                        st.session_state.prod_huidig = st.session_state.prod_sessie.pop(0) if st.session_state.prod_sessie else None
                        st.rerun()

                    if st.session_state.prod_score["totaal"]:
                        st.metric("Deze sessie", f"{st.session_state.prod_score['goed']}/{st.session_state.prod_score['totaal']} goed")

                with pc2:
                    if st.session_state.prod_feedback:
                        fb = st.session_state.prod_feedback
                        (st.success if fb["type"] == "success" else st.error)(fb["msg"])
                        st.session_state.prod_feedback = None

                    huidig_p = st.session_state.prod_huidig
                    if not huidig_p:
                        st.info("Kies links je lessen en klik op **Start / nieuwe sessie**.")
                    else:
                        correct_grieks = huidig_p.get('grieks', '')
                        betekenis = str(huidig_p.get('nederlands', ''))
                        strong_key = huidig_p.get('grieks', '')
                        p_stat = st.session_state.prod_stats.get(strong_key, {"g": 0, "f": 0, "streak": 0})

                        st.caption(f"Streak: {p_stat.get('streak', 0)} · Goed/Fout: {p_stat.get('g', 0)}/{p_stat.get('f', 0)}")
                        st.markdown(f"<div style='font-size:16px; color:#aaa;'>Geef het Griekse woord voor:</div>", unsafe_allow_html=True)
                        st.markdown(f"<div style='font-size:34px; font-weight:bold; color:#fff; margin-bottom:10px;'>{betekenis}</div>", unsafe_allow_html=True)
                        ws = huidig_p.get('woordsoort', '')
                        if ws:
                            st.caption(f"Woordsoort: {ws}")

                        def _norm_gr(s):
                            s = unicodedata.normalize("NFD", str(s).strip().lower())
                            s = "".join(c for c in s if unicodedata.category(c) != "Mn")
                            return s.replace('ς', 'σ')  # slot-sigma en gewone sigma gelijk behandelen

                        def prod_verwerk(goed):
                            st.session_state.prod_score["totaal"] += 1
                            entry = st.session_state.prod_stats.get(strong_key, {"g": 0, "f": 0, "streak": 0})
                            if goed:
                                st.session_state.prod_score["goed"] += 1
                                entry["g"] = int(entry.get("g", 0)) + 1
                                entry["streak"] = int(entry.get("streak", 0)) + 1
                                st.session_state.prod_feedback = {"type": "success", "msg": f"✅ Juist! {betekenis} → {correct_grieks}"}
                            else:
                                entry["f"] = int(entry.get("f", 0)) + 1
                                entry["streak"] = max(0, int(entry.get("streak", 0)) - 1)
                                st.session_state.prod_feedback = {"type": "error", "msg": f"❌ Het was: {correct_grieks} — {betekenis}"}
                            st.session_state.prod_stats[strong_key] = entry
                            registreer_oefening()
                            trigger_save()
                            # volgende
                            if st.session_state.prod_sessie:
                                st.session_state.prod_huidig = st.session_state.prod_sessie.pop(0)
                            else:
                                st.session_state.prod_huidig = None
                                st.session_state.prod_feedback["msg"] += "  \n\n🏁 Sessie klaar!"
                                trigger_save(forceer=True)  # sessie klaar: laatste antwoorden zeker bewaren
                            st.rerun()

                        if invoer_type.startswith("⌨️"):
                            with st.form(f"prod_typ_{strong_key}", clear_on_submit=True):
                                inp = st.text_input("Grieks (Latijnse toetsen mag):", key=f"prod_in_{strong_key}")
                                verzonden = st.form_submit_button("✓ Nakijken", type="primary")
                            if verzonden:
                                if not inp.strip():
                                    st.warning("Typ eerst een antwoord.")
                                else:
                                    omgezet = naar_grieks_transliteratie(inp)
                                    goed = _norm_gr(omgezet) == _norm_gr(correct_grieks)
                                    prod_verwerk(goed)
                            audio_knop(huidig_p.get('fonetisch', ''), key="prod")
                        else:
                            if 'prod_opties' not in st.session_state or not st.session_state.get('prod_opties') or st.session_state.get('prod_opties_voor') != strong_key:
                                afl = [w.get('grieks') for w in prod_db
                                       if w.get('grieks') and w.get('grieks') != correct_grieks
                                       and w.get('woordsoort') == ws]
                                r_engine.shuffle(afl)
                                opties = [correct_grieks] + afl[:3]
                                r_engine.shuffle(opties)
                                st.session_state.prod_opties = opties
                                st.session_state.prod_opties_voor = strong_key
                            keuze = st.radio("Kies de juiste Griekse vorm:", st.session_state.prod_opties, index=None, key=f"prod_mc_{strong_key}")
                            if st.button("✓ Nakijken", key=f"prod_mc_btn_{strong_key}", type="primary"):
                                if keuze is None:
                                    st.warning("Kies eerst een optie.")
                                else:
                                    st.session_state.prod_opties = None
                                    prod_verwerk(keuze == correct_grieks)

        # ==========================================
        # TAB 12: ONTLEDEN (morfologische trainer)
        # ==========================================
        if _TOON[10]:
         with menu[10]:
            st.subheader("🔎 Ontleden")
            _ONTL_MODI = ["📖 Zin ontleden", "🔤 Losse woorden ontleden", "📜 Hele tekst ontleden", "🔍 Zoeken"]
            _ontl_modus = _pref_keuze(st.radio, "Wat wil je ontleden?", _ONTL_MODI, 'ontl_modus', horizontal=True)
            if _ontl_modus.startswith("📖"):
                st.caption("Ontleed een Bijbelvers in vijf rondes — net als op het tentamen: **1)** woordsoort van elk woord, **2)** naamwoorden ontleden, **3)** werkwoorden ontleden, **4)** woord voor woord vertalen, **5)** de hele zin. De zin kleurt mee met de naamvallen (Nom · Gen · Dat · Acc · Voc).")
            elif _ontl_modus.startswith("🔤"):
                st.caption("Losse woorden uit de lessen die jij kiest, steeds in een echt Bijbelvers. Je ontleedt het woord volledig en vertaalt het — met de samentrekkingsregels en het juiste rijtje als hulp.")
            elif _ontl_modus.startswith("🔍"):
                st.caption("Typ een Griekse vorm (mét of zonder accenten, of in gewone letters) en zie álle ontledingen die die vorm in het Nieuwe Testament kan hebben — met basiswoord, betekenis, opbouw en het juiste rijtje.")
            else:
                st.caption("Werk een hele passage door: kies boek, hoofdstuk en verzen, en ontleed vers na vers met dezelfde vijf rondes.")
            _obdb = laad_bijbel_db()
            if not _obdb:
                st.info("De Bijbeltekst-database is niet beschikbaar.")

            # ==================================================================
            # SUB-MODUS: ZOEKEN (opzoeken welke ontledingen een vorm kan hebben)
            # ==================================================================
            elif _ontl_modus.startswith("🔍"):
                with st.form("ontl_zoek_form"):
                    _zq = st.text_input("Zoek een Griekse vorm:", key="ontl_zoek_in",
                                        placeholder="bv. λόγον, ἔλυσεν, of logon / elusen",
                                        help="Latijnse letters worden omgezet naar Grieks (logos → λόγος, q=θ, c=ξ, w=ω, h=η, y=ψ). Accenten hoef je niet in te typen.")
                    _zsub = st.form_submit_button("🔍 Zoek", type="primary")
                st.caption("⌨️ Typ Grieks in gewone letters: **logos → λόγος**. Bijzondere tekens: "
                           "θ=q · ξ=c · χ=x · ψ=y · ω=w · η=h · φ=f. Accenten hoef je niet in te typen.")
                if _zsub and (_zq or "").strip():
                    st.session_state.ontl_zoek_term = _zq.strip()

                _term = st.session_state.get('ontl_zoek_term', '')
                if _term:
                    _vidx = bijbel_vorm_index(_obdb)
                    _key = normaliseer_accent(naar_grieks_transliteratie(_term))
                    _res = _vidx.get(_key) or _vidx.get(normaliseer_accent(_term)) or []
                    _vocab = {str(v.get('strong')): v for v in (st.session_state.get('data') or []) if v.get('strong')}

                    def _toon_suggesties(_sugs, _titel):
                        if not _sugs:
                            return
                        st.caption(_titel)
                        _scols = st.columns(min(4, len(_sugs)))
                        for _si, _sug in enumerate(_sugs):
                            if _scols[_si % len(_scols)].button(_sug, key=f"zoeksug_{_si}"):
                                st.session_state.ontl_zoek_term = _sug
                                st.rerun()

                    if not _res:
                        st.warning(f"Geen vorm **{_term}** gevonden in het Nieuwe Testament. Controleer de spelling "
                                   "(je mag ook in gewone letters typen, bv. *anthrwpos*).")
                        _toon_suggesties(zoek_suggesties(_obdb, _term), "🔎 Bedoelde je misschien? Klik om te openen:")
                    else:
                        _toon = _res[0][0]
                        st.markdown(f"<div style='font-size:40px;font-weight:800;color:#33ccff;text-align:center;padding:4px 0'>{_toon}</div>",
                                    unsafe_allow_html=True)
                        audio_knop(fonetisch_uit_translit(_res[0][5]), key="ontlzoek")
                        _mv = "vorm" if len(_res) == 1 else "mogelijke ontledingen"
                        st.caption(f"**{len(_res)}** {_mv} in het NT — meest voorkomende bovenaan.")
                        # Meerdere ontledingen van hetzelfde woord = dubbelzinnige vorm: de context beslist.
                        if any(len(vorm_ontledingen(_obdb, _res[0][0], _r[2])) > 1 for _r in _res):
                            st.info("⚠️ Dit is een **dubbelzinnige vorm**: los van de zin zijn meerdere ontledingen "
                                    "mogelijk. In een echte tekst bepaalt de context (en soms het accent) welke het is.")
                        with st.expander("🔎 Vergelijkbare vormen (andere spelling/accent)"):
                            _toon_suggesties(zoek_suggesties(_obdb, _term), "Klik om te openen:")
                        for _zi, (_g, _pi, _strong, _ref, _n, _tr) in enumerate(_res):
                            _bw = _vocab.get(str(_strong))
                            _lemma = str(_bw.get('grieks', '')) if _bw else ""
                            _ginfo = str(_bw.get('grieks_info', '') or _lemma) if _bw else ""
                            _bet = str(_bw.get('nederlands', '')) if _bw else ""
                            _ws = _woordsoort_van(_pi)
                            with st.container():
                                # De accentvorm vooraan, zodat je bij gelijkluidende woorden (εἰς vs εἷς)
                                # meteen de juiste kunt herkennen en aanklikken.
                                st.markdown(f"#### {_zi + 1}. <span style='color:#33ccff'>{_g}</span> — "
                                            f"{_ws if _ws != '—' else 'Vorm'} · {_pi or '(geen ontleding)'}",
                                            unsafe_allow_html=True)
                                _regelinfo = []
                                if _lemma:
                                    _regelinfo.append(f"🔑 Basiswoord: **{_ginfo or _lemma}**")
                                if _bet:
                                    _regelinfo.append(f"betekenis: *{_bet}*")
                                _regelinfo.append(f"komt **{_n}×** voor · bv. {_ref}")
                                _lu = biblehub_woord_url(_strong)
                                if _lu:
                                    _regelinfo.append(f"[📖 BibleHub-lexicon]({_lu})")
                                st.caption(" · ".join(_regelinfo))
                                # Hoe vertaal je déze vorm? (naamval-functie / wijs-tijd-diathese in het NL)
                                for _vh in _ontleed_vertaalhulp(_pi):
                                    st.markdown("💡 " + _vh)
                                toon_opbouw_hulp(_g, _lemma, _pi, _ginfo, sleutel=f"zoek_{_zi}", strong=_strong)
                                toon_rijtje_hulp(_pi, _lemma, _ginfo, sleutel=f"zoek_{_zi}")
                                st.write("")

                        # --- Alle vindplaatsen + hoe het in het Engels (BSB) wordt vertaald ---
                        _vp = zoek_vindplaatsen(_obdb, _key)
                        if _vp:
                            st.write("---")
                            _paren = tel_glossen(bsb_glosse(v[3]) for v in _vp)
                            _zonder = len(_vp) - sum(n for _l, n in _paren)
                            if len(_paren) > 1:
                                st.markdown("##### 🇬🇧 Zo wordt deze vorm in het Engels vertaald (BSB)")
                                st.markdown(cirkeldiagram_html(_paren), unsafe_allow_html=True)
                                if _zonder:
                                    st.caption(f"ℹ️ {_zonder} van de {len(_vp)} plekken zijn in een zinsdeel vertaald "
                                               "(geen los Engels woord in de BSB).")
                            # Werkwoord? Toon hoe de Bijbel álle tijden van dit werkwoord vertaalt.
                            _ww_strong = next((r[2] for r in _res if "Werkwoord" in r[1]), None)
                            if _ww_strong:
                                _pt = werkwoord_vertaling_per_tijd(_obdb, _ww_strong)
                                if _pt:
                                    st.markdown("##### ⏳ Per tijd — zo vertaalt de Bijbel de vormen van dit werkwoord")
                                    for _r in _regels_per_tijd(_pt):
                                        st.markdown(_r)
                            # Naamwoord? Toon hoe de Bijbel de verschillende naamvallen vertaalt.
                            _nv_strong = next((r[2] for r in _res if "Werkwoord" not in r[1]
                                               and any(c in r[1] for c in ("Nom", "Gen", "Dat", "Acc", "Voc"))), None)
                            if _nv_strong:
                                _pnv = naamwoord_vertaling_per_naamval(_obdb, _nv_strong)
                                if _pnv:
                                    st.markdown("##### 📐 Per naamval — zo vertaalt de Bijbel de vormen van dit woord")
                                    for _r in _regels_per_tijd(_pnv):
                                        st.markdown(_r)
                            with st.expander(f"📍 Alle {len(_vp)} vindplaatsen in het NT"):
                                st.caption("Klik op een vers voor de interlinear op BibleHub.")
                                for _ref2, _g2, _pi2, _en2 in _vp[:300]:
                                    _en_c = bsb_glosse(_en2)
                                    _en_s = f" — *{_en_c}*" if _en_c else " — *(in zinsdeel vertaald)*"
                                    _ru = biblehub_vers_url(_ref2)
                                    _ref_md = f"[{_ref2}]({_ru})" if _ru else f"**{_ref2}**"
                                    st.markdown(f"{_ref_md} · {_g2}{_en_s}")
                                if len(_vp) > 300:
                                    st.caption(f"… en nog {len(_vp) - 300} meer (eerste 300 getoond).")
                else:
                    st.info("Typ hierboven een woord en klik op **🔍 Zoek**.")

            # ==================================================================
            # SUB-MODUS: LOSSE WOORDEN ONTLEDEN
            # ==================================================================
            elif _ontl_modus.startswith("🔤"):
                _wprefs = st.session_state.get('ui_prefs')
                if not isinstance(_wprefs, dict):
                    _wprefs = {}; st.session_state.ui_prefs = _wprefs

                with st.expander("⚙️ Instellingen (lessen · woordsoorten · niveau · kleuren)", expanded=False):
                    _alle_lessen = sorted({veilig_les_nummer(i) for i in (st.session_state.get('data') or [])})
                    _wc1, _wc2 = st.columns([2, 1])
                    _wles_alles = _wc2.toggle("Alle lessen", value=bool(_wprefs.get('ontlw_alles', True)), key="ontlw_alles_t")
                    _wprefs['ontlw_alles'] = _wles_alles
                    if _wles_alles:
                        _wc1.caption("Woorden mogen uit **alle lessen** komen.")
                        _wlessen = set(_alle_lessen)
                    else:
                        _vorige = [l for l in (_wprefs.get('ontlw_lessen') or []) if l in _alle_lessen]
                        _wsel = _wc1.multiselect("Uit welke lessen?", _alle_lessen,
                                                 default=_vorige or _alle_lessen[:1], key="ontlw_lessen_ms")
                        _wprefs['ontlw_lessen'] = list(_wsel)
                        _wlessen = set(_wsel)

                    _wd1, _wd2, _wd3, _wd4 = st.columns([1.7, 1.0, 1.1, 0.9])
                    # Alles wat verbogen of vervoegd wordt is oefenbaar — ook bijv. naamwoorden,
                    # voornaamwoorden en lidwoorden (die hebben allemaal naamval/getal/geslacht).
                    _WSOORTEN = ["Zelfst. nw.", "Bijv. nw.", "Voornaamwoord", "Lidwoord", "Werkwoord"]
                    _wvorige = [s for s in (_wprefs.get('ontlw_soorten') or []) if s in _WSOORTEN]
                    _wsoorten = _wd1.multiselect("Welke woordsoorten?", _WSOORTEN,
                                                 default=_wvorige or _WSOORTEN, key="ontlw_soorten_ms",
                                                 help="Alles wat verbogen of vervoegd wordt kun je ontleden.")
                    _wprefs['ontlw_soorten'] = list(_wsoorten)
                    if not _wsoorten:
                        _wsoorten = list(_WSOORTEN)
                    _wniveau = _pref_keuze(_wd2.selectbox, "Niveau:", ["Grieks 1", "Grieks 2", "Grieks 3"],
                                           'ontlw_niveau', default='Grieks 2',
                                           help="Bepaalt welke vormen je hoeft te ontleden (bv. bij Grieks 1 geen conjunctivus).")
                    _wbekend = _wd3.toggle("Alleen woorden die ik ken", value=bool(_wprefs.get('ontlw_bekend', True)),
                                           key="ontlw_bekend_t")
                    _wprefs['ontlw_bekend'] = _wbekend
                    _wdrempel = int(_wprefs.get('ontlw_drempel', 3))
                    if _wbekend:
                        _wdrempel = _wd3.slider("Min. streak:", 1, 30, _wdrempel, key="ontlw_drempel_s")
                        _wprefs['ontlw_drempel'] = _wdrempel
                    _wsteun = _wd4.toggle("💡 Hulp", value=bool(_wprefs.get('ontlw_steun', True)), key="ontlw_steun_t")
                    _wprefs['ontlw_steun'] = _wsteun

                    # Kleur-schuifjes voor de contextzin (zoals in Leesteksten) — het doelwoord blijft
                    # ongekleurd, anders verraadt de kleur het antwoord.
                    # Twee rijen van drie: vijf schuifjes naast elkaar wordt op mobiel onleesbaar.
                    _wkc1, _wkc2, _wkc3 = st.columns(3)
                    _wkl_nv = _wkc1.toggle("🎨 Kleur naamvallen", value=bool(_wprefs.get('ontlw_kl_nv', False)), key="ontlw_kl_nv_t",
                                           help="Kleurt de andere woorden in de zin op naamval. Het woord dat je ontleedt blijft ongekleurd.")
                    _wkl_vw = _wkc2.toggle("🔗 Kleur voegwoorden", value=bool(_wprefs.get('ontlw_kl_vw', False)), key="ontlw_kl_vw_t")
                    _wkl_st = _wkc3.toggle("⚛️ Kleur stamtijden", value=bool(_wprefs.get('ontlw_kl_st', False)), key="ontlw_kl_st_t")
                    _wkc4, _wkc5, _wkc6 = st.columns(3)
                    _wkl_ug = _wkc4.toggle("🌈 Kleur uitgangen", value=bool(_wprefs.get('ontlw_kl_ug', False)), key="ontlw_kl_ug_t",
                                           help="Splitst elk woord in stam + uitgang (en augment) met eigen kleuren — óók het doelwoord.")
                    _wkl_sm = _wkc5.toggle("🔊 Toon samensmeltingen", value=bool(_wprefs.get('ontlw_kl_sm', False)), key="ontlw_kl_sm_t",
                                           help="Zet onder de zin welke klankwetten erin zitten (bv. φ + σ → ψ). Meer oefenen? Zie de tab 🔊 Klankwetten.")
                    _wprefs['ontlw_kl_nv'] = _wkl_nv; _wprefs['ontlw_kl_vw'] = _wkl_vw; _wprefs['ontlw_kl_st'] = _wkl_st
                    _wprefs['ontlw_kl_ug'] = _wkl_ug; _wprefs['ontlw_kl_sm'] = _wkl_sm

                # Werkwoordsvorm-filter: alleen zichtbaar als je werkwoorden oefent. Zo kun je gericht
                # bv. alleen participia of alleen de aoristus oefenen.
                _WIJZEN = ["Indicativus", "Conjunctivus", "Optativus", "Imperativus", "Infinitivus", "Participium"]
                _TIJDEN = ["Praesens", "Imperfectum", "Futurum", "Aoristus", "Perfectum", "Plusquamperfectum"]
                _wwijs, _wtijd = [], []
                if "Werkwoord" in _wsoorten:
                    with st.expander("⚙️ Alleen bepaalde werkwoordsvormen (optioneel)", expanded=False):
                        st.caption("Laat leeg = alle vormen. Vink aan om je alleen op bepaalde wijzen of tijden te richten.")
                        _wvw = [x for x in (_wprefs.get('ontlw_wijs') or []) if x in _WIJZEN]
                        _wvt = [x for x in (_wprefs.get('ontlw_tijd') or []) if x in _TIJDEN]
                        _wwijs = st.multiselect("Wijs:", _WIJZEN, default=_wvw, key="ontlw_wijs_ms")
                        _wtijd = st.multiselect("Tijd:", _TIJDEN, default=_wvt, key="ontlw_tijd_ms")
                        _wprefs['ontlw_wijs'] = list(_wwijs)
                        _wprefs['ontlw_tijd'] = list(_wtijd)

                def _wsoort_match(info):
                    """Hoort deze vorm bij een van de gekozen woordsoorten? En, bij een werkwoord, ook
                    bij de gekozen wijs/tijd (indien daarop gefilterd)?"""
                    info = info or ""
                    _merk = {"Zelfst. nw.": "Zelfst.", "Bijv. nw.": "Bijv.", "Voornaamwoord": "Voornaamwoord",
                             "Lidwoord": "Lidwoord", "Werkwoord": "Werkwoord"}
                    if not any(_merk[s] in info for s in _wsoorten):
                        return False
                    if "Werkwoord" in info:
                        if _wwijs and not any(w in info for w in _wwijs):
                            return False
                        if _wtijd and not any(t in info for t in _wtijd):
                            return False
                    return True

                def _nieuw_ontleed_woord():
                    """Zoekt een woord uit de gekozen lessen op in een echt Bijbelvers."""
                    _sidx = _bijbel_strong_index(_obdb)
                    _poule = []
                    for v in (st.session_state.get('data') or []):
                        if not v.get('strong') or veilig_les_nummer(v) not in _wlessen:
                            continue
                        if _wbekend and int(v.get('streak', 0)) < _wdrempel:
                            continue
                        _poule.append(v)
                    if not _poule:
                        st.session_state.ontlw_geen = ("Geen woorden gevonden met deze filters. Kies meer lessen, "
                                                       "zet de streak-drempel lager of vink 'Alleen woorden die ik ken' uit.")
                        st.session_state.ontlw_ref = None
                        return
                    _recent = st.session_state.get('ontlw_gezien') or []
                    _poule.sort(key=lambda v: (str(v.get('strong')) in _recent, r_engine.random()))
                    for v in _poule[:120]:
                        _refs = list(_sidx.get(str(v.get('strong')), []))
                        if not _refs:
                            continue
                        r_engine.shuffle(_refs)
                        for ref in _refs[:25]:
                            zin = _obdb.get(ref) or []
                            for i, w in enumerate(zin):
                                if str(w.get('strong', '')) != str(v.get('strong')):
                                    continue
                                _info = w.get('parsing_info', '')
                                if not _wsoort_match(_info):
                                    continue
                                if not _ontleed_dims_zonder_ws(_info):
                                    continue  # geen naamval/tijd/getal → niets te ontleden
                                if not _ontleed_in_scope(_info, _wniveau):
                                    continue
                                st.session_state.ontlw_ref = ref
                                st.session_state.ontlw_zin = zin
                                st.session_state.ontlw_idx = i
                                st.session_state.ontlw_basis = v
                                st.session_state.ontlw_fase = 'ontleed'
                                st.session_state.ontlw_fb = None
                                st.session_state.ontlw_geteld = False
                                st.session_state.ontlw_geen = None
                                _rc = (st.session_state.get('ontlw_gezien') or []) + [str(v.get('strong'))]
                                st.session_state.ontlw_gezien = _rc[-30:]
                                return
                    _extra = " Je werkwoordsvorm-filter (wijs/tijd) is misschien te smal." if (_wwijs or _wtijd) else ""
                    st.session_state.ontlw_geen = ("Geen Bijbelvers gevonden met een passende vorm van deze woorden "
                                                   "(let op het niveau en de filters)." + _extra)
                    st.session_state.ontlw_ref = None

                if st.button("🎲 Nieuw woord", key="ontlw_nieuw", type="primary"):
                    _nieuw_ontleed_woord(); st.rerun()

                if st.session_state.get('ontlw_geen'):
                    st.warning(st.session_state.ontlw_geen)
                elif not st.session_state.get('ontlw_ref'):
                    st.info("Klik op **🎲 Nieuw woord** om te beginnen.")
                else:
                    _wzin = st.session_state.ontlw_zin
                    _wi = st.session_state.ontlw_idx
                    _ww = _wzin[_wi]
                    _winfo = _ww.get('parsing_info', '')
                    _wbasis = st.session_state.get('ontlw_basis') or {}
                    _wlemma = str(_wbasis.get('grieks', ''))
                    _wginfo = str(_wbasis.get('grieks_info', '')) or _wlemma

                    if st.session_state.get('ontlw_topfb'):
                        _t = st.session_state.ontlw_topfb
                        {"success": st.success, "info": st.info}.get(_t.get('type'), st.info)(_t.get('msg', ''))
                        st.session_state.ontlw_topfb = None

                    # Groot doelwoord — met 'kleur uitgangen' de stam/uitgang gesplitst.
                    _wug_html = kleur_uitgangen_html(_ww.get('grieks', ''), _wlemma, _wginfo, _winfo, strong=_ww.get('strong')) if _wkl_ug else None
                    st.markdown(f"<div style='font-size:44px;font-weight:800;color:#33ccff;text-align:center;"
                                f"padding:6px 0'>{_wug_html or _ww.get('grieks','')}</div>", unsafe_allow_html=True)

                    # De zin eromheen als context (het doelwoord licht op). Kleur-schuifjes kleuren
                    # de ándere woorden op naamval; 'kleur uitgangen' mag ook op het doelwoord.
                    _wstamset = stamtijd_vormen_set() if _wkl_st else set()
                    _wvocab_bs = {str(v.get('strong')): v for v in (st.session_state.get('data') or []) if v.get('strong')} if _wkl_ug else {}
                    _ctx = ""
                    for _j, _cw in enumerate(_wzin):
                        _g = _cw.get('grieks', ''); _ip = _cw.get('interpunctie', '')
                        _cseg = None
                        if _wkl_ug:
                            _cbw = _wvocab_bs.get(str(_cw.get('strong')))
                            _cseg = kleur_uitgangen_html(_g, _cbw.get('grieks', '') if _cbw else '',
                                                         _cbw.get('grieks_info', '') if _cbw else '', _cw.get('parsing_info', ''),
                                                         strong=_cw.get('strong'))
                        if _j == _wi:
                            _ctx += (f"<span style='background:rgba(255,215,0,.25);border-bottom:3px solid #ffd700;"
                                     f"padding:0 3px;border-radius:4px;font-weight:700'>{_cseg or _g}</span>{_ip} ")
                        else:
                            _cstijl = "" if _cseg else (ontleed_kleur_stijl(_cw.get('parsing_info', ''), _g, _wkl_nv, _wkl_vw, _wkl_st, _wstamset) or "color:#8a8a8a")
                            _tt = (str(_cw.get('vertaling_nl', '') or _cw.get('vertaling_bsb', ''))).replace("'", "&#39;").replace('"', "&quot;")
                            if _cw.get('strong') and _tt:
                                _ctx += f"<span class='mobile-tooltip' tabindex='0' style='{_cstijl}'>{_cseg or _g}<span class='tooltiptext'>{_tt}</span></span>{_ip} "
                            else:
                                _ctx += f"<span style='{_cstijl}'>{_cseg or _g}</span>{_ip} "
                    st.markdown(f"<div style='font-size:13px;color:#f6c23e'>📖 {st.session_state.ontlw_ref}</div>"
                                f"<div style='font-size:19px;padding:6px 4px;line-height:1.6'>{_ctx.strip()}</div>",
                                unsafe_allow_html=True)
                    if _wkl_nv or _wkl_vw or _wkl_st or _wkl_ug:
                        _wleg = []
                        if _wkl_nv:
                            _wleg.append(" · ".join(f"<span style='color:{_ONTLEED_KLEUR[c]}'>{c}</span>"
                                                    for c in ["Nom", "Gen", "Dat", "Acc", "Voc"]))
                        if _wkl_vw: _wleg.append("<span style='background:#ffd700;color:#000;padding:0 3px;border-radius:3px'>voegwoord</span>")
                        if _wkl_st: _wleg.append("<span style='color:#d63384'>stamtijd</span>")
                        if _wkl_ug: _wleg.append("<span style='color:#56b4e9'>augment</span> <span style='color:#e8eaed'>stam</span> <span style='color:#ff9d5c'>uitgang</span>")
                        _wstaart = "" if _wkl_ug else " &nbsp;·&nbsp; het te ontleden woord blijft ongekleurd"
                        st.markdown("<div style='font-size:12px;color:#9aa3af'>🎨 " + " &nbsp;|&nbsp; ".join(_wleg) + _wstaart + "</div>",
                                    unsafe_allow_html=True)
                    # Welke klankwetten zitten er in deze zin? (schuifje '🔊 Toon samensmeltingen')
                    if _wprefs.get('ontlw_kl_sm'):
                        _wsm_bron = {str(v.get('strong')): v for v in (st.session_state.get('data') or [])
                                     if v.get('strong')}
                        _wsm = samensmeltingen_in_zin(_wzin, _wsm_bron)
                        if _wsm:
                            st.markdown("<div style='font-size:13px;color:#9aa3af'>🔊 " +
                                        " &nbsp;|&nbsp; ".join(f"<b>{v}</b>: {f}" for v, f, _k in _wsm) + "</div>",
                                        unsafe_allow_html=True)
                        else:
                            st.caption("🔊 In deze zin zit geen samensmelting die de app zeker kan aanwijzen.")
                    # Uitspraak: eerst het woord zelf, dan de hele zin eromheen.
                    _wfon = fonetisch_uit_translit(_ww.get('transliteratie', ''))
                    audio_knop((_wfon + ". " + bijbelzin_fonetisch(_wzin)).strip(". "), key="ontlwoord")
                    st.caption(f"🔑 Basiswoord: **{_wginfo}**")

                    # Stapsgewijs ontleden (bolletjes buiten het formulier, zodat de volgende rij pas
                    # verschijnt als je iets aanklikt — anders verraadt bv. de naamval-rij al een
                    # participium). Pas als alles ingevuld is, komt de vertaling erbij.
                    _wdims = _ontleed_dims(_winfo)
                    _wsleutel = f"{st.session_state.ontlw_ref}_{_wi}"
                    def _wrk(_k):
                        return f"ontlw_{_k}_{_wsleutel}"
                    _wbeantwoord = 0
                    for _k, _lab, _opts in _wdims:
                        if st.session_state.get(_wrk(_k)) is not None:
                            _wbeantwoord += 1
                        else:
                            break
                    _wkeuzes = {}
                    for _k, _lab, _opts in _wdims[:min(len(_wdims), _wbeantwoord + 1)]:
                        _wkeuzes[_k] = st.radio(_lab, _opts, index=None, horizontal=True, key=_wrk(_k))
                    _wklaar = (_wbeantwoord >= len(_wdims))
                    _wv = ""; _wvz = ""; _wsub = False
                    if not _wklaar:
                        st.caption("↓ Vul in; de volgende regel verschijnt zodra je iets aanklikt.")
                    else:
                        with st.form(f"ontlw_form_{_wsleutel}", clear_on_submit=False):
                            _wv = st.text_input("Woordenboekvertaling:", key=f"ontlw_vert_{_wsleutel}",
                                                help="De betekenis zoals die in je woordenlijst staat — dus de vorm van het basiswoord. "
                                                     "Dit veld wordt automatisch nagekeken.")
                            _wvz = st.text_input("En zoals het hier in de zin staat (optioneel):", key=f"ontlw_zin_{_wsleutel}",
                                                 help="Bijvoorbeeld 'aan de mens' bij een dativus. Dit kan de app niet automatisch "
                                                      "nakijken — je krijgt na het checken het antwoord te zien en beoordeelt zelf.")
                            _wsub = st.form_submit_button("✓ Alles nakijken", type="primary")

                    if st.session_state.get('ontlw_fb'):
                        for _r in st.session_state.ontlw_fb:
                            st.markdown(_r)

                    if _wsub:
                        _res = []; _goed = True
                        _eerste = not st.session_state.get('ontlw_geteld')
                        for _k, _lab, _opts in _wdims:
                            _ok = _ontleed_deel_ok(_k, _wkeuzes.get(_k), _winfo)
                            if _eerste and _wkeuzes.get(_k) is not None:
                                _rec = st.session_state.ontleed_stats.setdefault(_k, {'g': 0, 'f': 0})
                                _rec['g' if _ok else 'f'] = int(_rec.get('g' if _ok else 'f', 0)) + 1
                            if _ok:
                                _res.append(f"- ✅ **{_lab}:** {_wkeuzes.get(_k)}")
                            else:
                                _goed = False
                                _res.append(f"- ❌ **{_lab}:** juist is **{_ontleed_deel_correct(_k, _winfo)}**")
                        # De vertaling wordt tegen het BASISWOORD gecheckt (de woordenboekbetekenis).
                        _wdoel = str(_wbasis.get('nederlands', ''))
                        _vok = check_betekenis(_wv or "", _wdoel)
                        if _eerste and (_wv or "").strip():
                            _rec = st.session_state.ontleed_stats.setdefault('vertaling', {'g': 0, 'f': 0})
                            _rec['g' if _vok else 'f'] = int(_rec.get('g' if _vok else 'f', 0)) + 1
                        if _vok:
                            _res.append(f"- ✅ **Vertaling:** {_wdoel}")
                        else:
                            _goed = False
                            _res.append(f"- ❌ **Vertaling:** het basiswoord betekent **{_wdoel}**")
                        st.session_state.ontlw_geteld = True
                        # In de zin zelf kan de vertaling anders uitvallen (naamval, tijd). Die kan de app
                        # niet automatisch nakijken, dus alleen tonen — jij beoordeelt zelf.
                        _incontext = str(_ww.get('vertaling_nl', '') or _ww.get('vertaling_bsb', '')).strip()
                        if _incontext:
                            if (_wvz or "").strip():
                                _res.append(f"- 🔍 **In de zin** — jij: *{_wvz.strip()}* · in de tekst: **{_incontext}** "
                                            f"(beoordeel zelf of dat op hetzelfde neerkomt)")
                            else:
                                _res.append(f"- 📖 *In deze zin:* **{_incontext}**")
                        if _goed:
                            _wbasis['streak'] = int(_wbasis.get('streak', 0)) + 1
                            _wbasis['score_goed'] = int(_wbasis.get('score_goed', 0)) + 1
                            registreer_oefening(_wbasis)
                            _tl = int(st.session_state.get('ontlw_teller', 0)) + 1
                            st.session_state.ontlw_teller = _tl
                            if _tl % 3 == 0:  # 3 volledig afgeronde woorden = één 'vers' voor het dagdoel
                                dagdoel_plus('verzen')
                            _msg = f"✅ **{_ww.get('grieks','')}** — {_winfo} = {_wdoel}"
                            if _incontext:
                                # De zelf te beoordelen zin-vertaling gaat mee in de balk, anders zou je
                                # hem nooit zien omdat we meteen doorspringen naar het volgende woord.
                                _msg += (f"\n\n🔍 In de zin — jij: *{_wvz.strip()}* · in de tekst: **{_incontext}**"
                                         if (_wvz or "").strip() else f"\n\n📖 In deze zin: **{_incontext}**")
                            st.session_state.ontlw_topfb = {"type": "success", "msg": _msg}
                            st.session_state.ontlw_fb = None
                            trigger_save()
                            _nieuw_ontleed_woord()
                        else:
                            _amb = ambiguiteit_regel(_obdb, _ww.get('grieks', ''), _ww.get('strong'),
                                                     _wkeuzes, _winfo, _wdims)
                            if _amb:
                                _res.append(_amb)
                            st.session_state.ontlw_fb = _res
                        st.rerun()

                    _wt1, _wt2 = st.columns(2)
                    if _wt1.button("👁️ Toon antwoord", key="ontlw_toon"):
                        if not st.session_state.get('ontlw_geteld'):
                            for _k, _lab, _opts in _wdims:
                                _rec = st.session_state.ontleed_stats.setdefault(_k, {'g': 0, 'f': 0})
                                _rec['f'] = int(_rec.get('f', 0)) + 1
                            st.session_state.ontlw_geteld = True
                        st.session_state.ontlw_topfb = {
                            "type": "info",
                            "msg": f"👁️ **{_ww.get('grieks','')}** — {_winfo} = {_wbasis.get('nederlands','')}"}
                        st.session_state.ontlw_fb = None
                        _nieuw_ontleed_woord(); st.rerun()
                    if _wt2.button("➡️ Overslaan", key="ontlw_next"):
                        st.session_state.ontlw_fb = None
                        _nieuw_ontleed_woord(); st.rerun()

                    if _wsteun:
                        toon_vertaalhulp(_winfo, sleutel="ontlw")

                    # --- HULP: het juiste rijtje én de samentrekkingsregels ---
                    if _wsteun:
                        toon_opbouw_hulp(_ww.get('grieks', ''), _wlemma, _winfo, _wginfo,
                                         uitgeklapt=bool(st.session_state.get('ontlw_fb')), strong=_ww.get('strong'))
                        toon_rijtje_hulp(_winfo, _wlemma, _wginfo, sleutel="ontlw",
                                         uitgeklapt=bool(st.session_state.get('ontlw_fb')))
                        toon_engels_diagram(_ww.get('grieks', ''), _obdb, sleutel="ontlw",
                                            strong=_ww.get('strong'), parsing_info=_winfo)
                        _bhw = biblehub_regel(st.session_state.ontlw_ref, _ww.get('strong'))
                        if _bhw:
                            st.caption(_bhw)
                    st.caption("📊 Je ontleed-accuratesse per onderdeel vind je op het **📊 Voortgang**-tabblad.")

            else:
                with st.expander("⚙️ Instellingen (niveau · kleuren · rondes · lessen)", expanded=False):
                    _oc1, _oc2, _oc3, _oc4 = st.columns([1.3, 1.3, 0.9, 1.0])
                    # Instellingen onthouden over sessies heen via ui_prefs (wordt bij opslag meegeschreven).
                    _oprefs = st.session_state.get('ui_prefs')
                    if not isinstance(_oprefs, dict):
                        _oprefs = {}; st.session_state.ui_prefs = _oprefs
                    _niv_def = _oprefs.get('ontl_niveau', 'Grieks 2')
                    if _niv_def not in ["Grieks 1", "Grieks 2", "Grieks 3"]:
                        _niv_def = 'Grieks 2'
                    _oniveau = _oc1.selectbox("Niveau:", ["Grieks 1", "Grieks 2", "Grieks 3"],
                                              index=["Grieks 1", "Grieks 2", "Grieks 3"].index(_niv_def),
                                              key="ontl_niveau_sel", help="Bepaalt welke vormen je hoeft te ontleden (bv. bij Grieks 1 geen conjunctivus/participium).")
                    st.session_state.ontl_niveau = _oniveau; _oprefs['ontl_niveau'] = _oniveau
                    _odrempel = _oc2.slider("Ontleed woorden die je kent (min. streak):", 1, 30,
                                            int(_oprefs.get('ontl_drempel', 5)), key="ontl_drempel_slider")
                    st.session_state.ontl_drempel = _odrempel; _oprefs['ontl_drempel'] = _odrempel
                    _osteun = _oc3.toggle("💡 Hulp", value=bool(_oprefs.get('ontl_steun', True)), key="ontl_steun_toggle")
                    st.session_state.ontl_steun = _osteun; _oprefs['ontl_steun'] = _osteun
                    _obasis = _oc4.toggle("🔑 Basiswoord", value=bool(_oprefs.get('ontl_basis', False)), key="ontl_basis_toggle",
                                          help="Toon bij elk woord de woordenboekvorm (basiswoord), zonder de betekenis.")
                    st.session_state.ontl_basis = _obasis; _oprefs['ontl_basis'] = _obasis

                    # Kleur-schuifjes (zoals in Leesteksten) — het doelwoord kleurt nooit mee, anders
                    # verraadt de kleur het antwoord.
                    # Twee rijen van drie: vijf schuifjes naast elkaar wordt op mobiel onleesbaar.
                    _kc1, _kc2, _kc3 = st.columns(3)
                    _kl_nv = _kc1.toggle("🎨 Kleur naamvallen", value=bool(_oprefs.get('ontl_kl_nv', False)), key="ontl_kl_nv_t",
                                         help="Kleurt de andere woorden op naamval. Het woord dat je ontleedt blijft ongekleurd.")
                    _kl_vw = _kc2.toggle("🔗 Kleur voegwoorden", value=bool(_oprefs.get('ontl_kl_vw', False)), key="ontl_kl_vw_t")
                    _kl_st = _kc3.toggle("⚛️ Kleur stamtijden", value=bool(_oprefs.get('ontl_kl_st', False)), key="ontl_kl_st_t")
                    _kc4, _kc5, _kc6 = st.columns(3)
                    _kl_ug = _kc4.toggle("🌈 Kleur uitgangen", value=bool(_oprefs.get('ontl_kl_ug', False)), key="ontl_kl_ug_t",
                                         help="Splitst elk woord in stam + uitgang (en augment) met eigen kleuren — óók het doelwoord, dat helpt bij herleiden.")
                    _kl_sm = _kc5.toggle("🔊 Toon samensmeltingen", value=bool(_oprefs.get('ontl_kl_sm', False)), key="ontl_kl_sm_t",
                                         help="Zet onder de zin welke klankwetten erin zitten (bv. φ + σ → ψ, α → η). Meer oefenen? Zie de tab 🔊 Klankwetten.")
                    _oprefs['ontl_kl_nv'] = _kl_nv; _oprefs['ontl_kl_vw'] = _kl_vw; _oprefs['ontl_kl_st'] = _kl_st
                    _oprefs['ontl_kl_ug'] = _kl_ug; _oprefs['ontl_kl_sm'] = _kl_sm

                    # Welke rondes wil je doen? Positief neergezet (leeg = alle rondes) — net als overal.
                    _ronde_opts = {"Woordsoort": "woordsoort", "Naamwoorden ontleden": "znw",
                                   "Werkwoorden ontleden": "ww", "Woord-voor-woord vertalen": "vertalen",
                                   "Hele zin vertalen": "zin"}
                    _alle_fasen = list(_ronde_opts.values())
                    _do_default = [lab for lab, f in _ronde_opts.items() if f in (_oprefs.get('ontl_do') or [])]
                    _do_sel = st.multiselect("Welke rondes wil je doen? (leeg = alle rondes)", list(_ronde_opts.keys()),
                                             default=_do_default, key="ontl_do_sel")
                    _do_fasen = [_ronde_opts[lab] for lab in _do_sel]
                    _oprefs['ontl_do'] = _do_fasen
                    # Intern werken we nog met 'over te slaan' fasen: alles wat je NIET koos (als je iets koos).
                    _skip_fasen = [f for f in _alle_fasen if f not in _do_fasen] if _do_fasen else []
                    st.session_state.ontl_skip_fasen = _skip_fasen

                    # Op bepaalde lessen richten (net als bij 'Losse woorden ontleden').
                    _ol_all_lessen = sorted({veilig_les_nummer(i) for i in (st.session_state.get('data') or [])})
                    _olc1, _olc2 = st.columns([2, 1])
                    _ol_alles = _olc2.toggle("Alle lessen", value=bool(_oprefs.get('ontl_lessen_alles', True)), key="ontl_lessen_alles_t")
                    _oprefs['ontl_lessen_alles'] = _ol_alles
                    if _ol_alles:
                        _olc1.caption("Te ontleden woorden mogen uit **alle lessen** komen.")
                        _ontl_lessen = set(_ol_all_lessen)
                    else:
                        _ol_vorige = [l for l in (_oprefs.get('ontl_lessen') or []) if l in _ol_all_lessen]
                        _ol_sel = _olc1.multiselect("Richt op lessen:", _ol_all_lessen,
                                                    default=_ol_vorige or _ol_all_lessen[:1], key="ontl_lessen_ms")
                        _oprefs['ontl_lessen'] = list(_ol_sel)
                        _ontl_lessen = set(_ol_sel)
                # strong → lesnummer, om te ontleden woorden op les te kunnen filteren
                _ontl_les_van = {str(w['strong']): veilig_les_nummer(w)
                                 for w in (st.session_state.get('data') or []) if w.get('strong')}
                def _ontl_les_ok(w):
                    return _ol_alles or _ontl_les_van.get(str(w.get('strong'))) in _ontl_lessen

                def _zet_ontleed_vers(ref, zin, alleen_bekend=True):
                    """Zet één vers klaar voor de vijf rondes (gedeeld door zin- en tekstmodus)."""
                    _ss = {str(w['strong']): int(w.get('streak', 0)) for w in (st.session_state.get('data') or []) if w.get('strong')}
                    _niv = st.session_state.get('ontl_niveau', 'Grieks 2')
                    lex = [i for i, w in enumerate(zin) if w.get('strong')]

                    def _tgt(i):
                        w = zin[i]
                        if alleen_bekend and _ss.get(str(w.get('strong')), 0) < _odrempel:
                            return False
                        if not _ontl_les_ok(w):
                            return False
                        return _ontleed_in_scope(w.get('parsing_info', ''), _niv)
                    znw = [i for i in lex if _ontleed_type(zin[i].get('parsing_info', '')) == 'naam' and _tgt(i)]
                    ww = [i for i in lex if _ontleed_type(zin[i].get('parsing_info', '')) in ('ww', 'ptc') and _tgt(i)]
                    # Woordsoort-ronde: alleen woorden waarvan we de woordsoort echt kunnen bepalen,
                    # zodat er nooit een onwinbare vraag ('juist is —') tussen zit.
                    ws = [i for i in lex if _woordsoort_van(zin[i].get('parsing_info', '')) != "—"]
                    st.session_state.ontl_ref = ref
                    st.session_state.ontl_zin = zin
                    st.session_state.ontl_lex = lex
                    st.session_state.ontl_ws = ws
                    st.session_state.ontl_znw = znw
                    st.session_state.ontl_ww = ww
                    st.session_state.ontl_pos = 0
                    st.session_state.ontl_kleur = {}
                    # Eerste ronde = eerste niet-overgeslagen ronde met inhoud.
                    _skip = set(st.session_state.get('ontl_skip_fasen') or [])
                    _lijsten0 = {'woordsoort': ws, 'znw': znw, 'ww': ww, 'vertalen': lex, 'zin': True}
                    _start = 'klaar'
                    for _f in ['woordsoort', 'znw', 'ww', 'vertalen', 'zin']:
                        if _f not in _skip and _lijsten0.get(_f):
                            _start = _f; break
                    st.session_state.ontl_fase = _start
                    st.session_state.ontl_feedback = None
                    st.session_state.ontl_topfb = None
                    st.session_state.ontl_zin_model = None
                    st.session_state.ontl_geteld = set()
                    st.session_state.ontl_geen = False

                def _nieuw_ontleed_vers():
                    # Tekstmodus: werk de gekozen passage vers voor vers af.
                    _rij = st.session_state.get('ontl_wachtrij') or []
                    if _rij:
                        _ref = _rij.pop(0)
                        st.session_state.ontl_wachtrij = _rij
                        _zin = _obdb.get(_ref) or []
                        if _zin:
                            _zet_ontleed_vers(_ref, _zin, alleen_bekend=False)
                            return
                    if st.session_state.get('ontl_tekst_actief'):
                        # De passage is uit → afronden in plaats van een willekeurig vers pakken.
                        st.session_state.ontl_tekst_actief = False
                        st.session_state.ontl_ref = None
                        st.session_state.ontl_klaar_tekst = True
                        return
                    _ss = {str(w['strong']): int(w.get('streak', 0)) for w in (st.session_state.get('data') or []) if w.get('strong')}
                    _niv = st.session_state.get('ontl_niveau', 'Grieks 2')
                    kandidaten = []
                    for ref, zin in _obdb.items():
                        if ref in (st.session_state.get('ontl_gezien') or []):
                            continue
                        lex = [i for i, w in enumerate(zin) if w.get('strong')]
                        if len(lex) < 3:
                            continue
                        if any(_ss.get(str(zin[i]['strong']), 0) < 1 for i in lex):
                            continue  # hele zin moet bekend zijn
                        def _tgt(i):
                            w = zin[i]
                            return (_ss.get(str(w.get('strong')), 0) >= _odrempel and _ontl_les_ok(w)
                                    and _ontleed_in_scope(w.get('parsing_info', ''), _niv))
                        znw = [i for i in lex if _ontleed_type(zin[i].get('parsing_info', '')) == 'naam' and _tgt(i)]
                        ww = [i for i in lex if _ontleed_type(zin[i].get('parsing_info', '')) in ('ww', 'ptc') and _tgt(i)]
                        if znw or ww:
                            kandidaten.append((ref, zin))
                    if not kandidaten:
                        st.session_state.ontl_ref = None
                        st.session_state.ontl_geen = True
                        return
                    r_engine.shuffle(kandidaten)
                    ref, zin = kandidaten[0]
                    _gz = st.session_state.get('ontl_gezien') or []
                    _gz.append(ref); st.session_state.ontl_gezien = _gz[-40:]
                    _zet_ontleed_vers(ref, zin, alleen_bekend=True)

                # --- TEKSTMODUS: kies een passage en werk die vers voor vers af ---
                if _ontl_modus.startswith("📜"):
                    st.write("---")
                    _tparsed = bijbel_boek_index(_obdb)   # gecached
                    if _tparsed:
                        _tb, _th, _tv = st.columns([1.2, 0.8, 2])
                        _boek = _tb.selectbox("Boek:", list(_tparsed.keys()), key="ontl_t_boek")
                        _hfd = sorted(_tparsed[_boek].keys(), key=lambda x: int(x) if str(x).isdigit() else 0)
                        _hoofd = _th.selectbox("Hoofdstuk:", _hfd, key="ontl_t_hfd")
                        _vlijst = sorted(_tparsed[_boek][_hoofd], key=lambda x: x[0])
                        _vopts = [v[1] for v in _vlijst]
                        _vkeuze = _tv.multiselect("Vers(zen):", _vopts, default=_vopts[:3], key="ontl_t_verzen")
                        _tk1, _tk2 = st.columns([1, 3])
                        if _tk1.button("▶️ Start deze tekst", key="ontl_t_start", type="primary"):
                            _refs = [v[2] for v in _vlijst if v[1] in _vkeuze]
                            if not _refs:
                                st.warning("Kies eerst minstens één vers.")
                            else:
                                st.session_state.ontl_wachtrij = _refs
                                st.session_state.ontl_tekst_totaal = len(_refs)
                                st.session_state.ontl_tekst_actief = True
                                st.session_state.ontl_klaar_tekst = False
                                _nieuw_ontleed_vers(); st.rerun()
                        _restant = len(st.session_state.get('ontl_wachtrij') or [])
                        _tot = int(st.session_state.get('ontl_tekst_totaal', 0))
                        if st.session_state.get('ontl_tekst_actief') and _tot:
                            _tk2.progress((_tot - _restant) / _tot,
                                          text=f"Vers {_tot - _restant} van {_tot} in deze passage")
                    if st.session_state.get('ontl_klaar_tekst'):
                        st.success("🎉 Hele passage ontleed! Kies hierboven een nieuwe tekst.")
                    st.write("---")
                elif st.button("🎲 Nieuw vers", key="ontl_nieuw", type="primary"):
                    st.session_state.ontl_wachtrij = []
                    st.session_state.ontl_tekst_actief = False
                    _nieuw_ontleed_vers(); st.rerun()

                if st.session_state.get('ontl_geen'):
                    _les_hint = "" if _ol_alles else " Je hebt de lessen beperkt — zet 'Alle lessen' aan of kies meer lessen."
                    st.warning(f"Geen verzen gevonden waarin je álle woorden kent én minstens één te ontleden woord met streak ≥ {_odrempel} (niveau {_oniveau}). Zet de drempel lager, kies een ander niveau, of oefen eerst meer woorden.{_les_hint}")
                elif not st.session_state.get('ontl_ref'):
                    st.info("Kies hierboven een tekst en klik op **▶️ Start deze tekst**."
                            if _ontl_modus.startswith("📜") else "Klik op **🎲 Nieuw vers** om te beginnen.")
                else:
                    _zin = st.session_state.ontl_zin
                    _fase = st.session_state.ontl_fase
                    _kleur = st.session_state.get('ontl_kleur', {})
                    _pos = st.session_state.ontl_pos
                    _lijst = {'woordsoort': st.session_state.get('ontl_ws', st.session_state.ontl_lex), 'znw': st.session_state.ontl_znw,
                              'ww': st.session_state.ontl_ww, 'vertalen': st.session_state.ontl_lex}.get(_fase, [])
                    _hidx = _lijst[_pos] if _pos < len(_lijst) else -1

                    def _ontl_advance():
                        # naar de volgende ronde met inhoud die niet is overgeslagen ('zin'/'klaar' altijd)
                        volgorde = ['woordsoort', 'znw', 'ww', 'vertalen', 'zin', 'klaar']
                        lijsten = {'woordsoort': st.session_state.get('ontl_ws', st.session_state.ontl_lex), 'znw': st.session_state.ontl_znw,
                                   'ww': st.session_state.ontl_ww, 'vertalen': st.session_state.ontl_lex}
                        _skip = set(st.session_state.get('ontl_skip_fasen') or [])
                        _i = volgorde.index(st.session_state.ontl_fase)
                        for _f in volgorde[_i + 1:]:
                            if _f in _skip:
                                continue
                            if _f in ('zin', 'klaar') or lijsten.get(_f):
                                st.session_state.ontl_fase = _f
                                st.session_state.ontl_pos = 0
                                st.session_state.ontl_feedback = None
                                if _f == 'zin':
                                    dagdoel_plus('verzen')
                                return
                        st.session_state.ontl_fase = 'klaar'

                    # --- gekleurde zin --- (in de vertaalrondes hover je over elk woord voor de glosse)
                    _hover = _fase in ('vertalen', 'zin')
                    _kl_nv = bool(_oprefs.get('ontl_kl_nv')); _kl_vw = bool(_oprefs.get('ontl_kl_vw'))
                    _kl_st = bool(_oprefs.get('ontl_kl_st')); _kl_ug = bool(_oprefs.get('ontl_kl_ug'))
                    _stamset = stamtijd_vormen_set() if _kl_st else set()
                    _vocab_bs = {str(v.get('strong')): v for v in (st.session_state.get('data') or []) if v.get('strong')} if _kl_ug else {}
                    _html = ""
                    for i, w in enumerate(_zin):
                        g = w.get('grieks', ''); interp = w.get('interpunctie', '')
                        # 'Kleur uitgangen' mag ook op het doelwoord (helpt onderscheiden).
                        _seg = None
                        if _kl_ug:
                            _bw = _vocab_bs.get(str(w.get('strong')))
                            _seg = kleur_uitgangen_html(g, _bw.get('grieks', '') if _bw else '',
                                                        _bw.get('grieks_info', '') if _bw else '', w.get('parsing_info', ''),
                                                        strong=w.get('strong'))
                        if i == _hidx:
                            _stijl = "background:rgba(255,215,0,.25);border-bottom:3px solid #ffd700;padding:0 3px;border-radius:4px"
                            _inhoud = _seg or g
                        elif _seg:
                            _stijl = ""; _inhoud = _seg
                        elif i in _kleur:
                            _stijl = f"color:{_kleur[i]};font-weight:700"; _inhoud = g
                        else:
                            # 'Kleur uitgangen' onderdrukt de naamval-kleuring niet, maar heeft voorrang waar er een splitsing is.
                            _stijl = ontleed_kleur_stijl(w.get('parsing_info', ''), g, _kl_nv, _kl_vw, _kl_st, _stamset) or "color:#8a8a8a"
                            _inhoud = g
                        if _hover and w.get('strong'):
                            _tt = (str(w.get('vertaling_nl', '') or w.get('vertaling_bsb', '')) + "  ·  " + str(w.get('parsing_info', ''))).replace("'", "&#39;").replace('"', "&quot;")
                            _html += f"<span class='mobile-tooltip' tabindex='0' style='{_stijl}'>{_inhoud}<span class='tooltiptext'>{_tt}</span></span>{interp} "
                        else:
                            _html += f"<span style='{_stijl}'>{_inhoud}</span>{interp} "
                    st.markdown(f"<div style='font-size:13px;color:#f6c23e'>📖 {st.session_state.ontl_ref}</div>"
                                f"<div style='font-size:26px;padding:12px 4px;line-height:1.6'>{_html.strip()}</div>", unsafe_allow_html=True)
                    if _kl_nv or _kl_vw or _kl_st or _kl_ug:
                        _leg = []
                        if _kl_nv:
                            _leg.append(" · ".join(f"<span style='color:{_ONTLEED_KLEUR[c]}'>{c}</span>"
                                                   for c in ["Nom", "Gen", "Dat", "Acc", "Voc"]))
                        if _kl_vw: _leg.append("<span style='background:#ffd700;color:#000;padding:0 3px;border-radius:3px'>voegwoord</span>")
                        if _kl_st: _leg.append("<span style='color:#d63384'>stamtijd</span>")
                        if _kl_ug: _leg.append("<span style='color:#56b4e9'>augment</span> <span style='color:#e8eaed'>stam</span> <span style='color:#ff9d5c'>uitgang</span>")
                        _staart = "" if _kl_ug else " &nbsp;·&nbsp; het te ontleden woord blijft ongekleurd"
                        st.markdown("<div style='font-size:12px;color:#9aa3af'>🎨 " + " &nbsp;|&nbsp; ".join(_leg) + _staart + "</div>",
                                    unsafe_allow_html=True)
                    # Welke klankwetten zitten er in deze zin? (schuifje '🔊 Toon samensmeltingen')
                    if _oprefs.get('ontl_kl_sm'):
                        _sm_bron = {str(v.get('strong')): v for v in (st.session_state.get('data') or [])
                                    if v.get('strong')}
                        _sm = samensmeltingen_in_zin(_zin, _sm_bron)
                        if _sm:
                            st.markdown("<div style='font-size:13px;color:#9aa3af'>🔊 " +
                                        " &nbsp;|&nbsp; ".join(f"<b>{v}</b>: {f}" for v, f, _k in _sm) + "</div>",
                                        unsafe_allow_html=True)
                        else:
                            st.caption("🔊 In deze zin zit geen samensmelting die de app zeker kan aanwijzen.")
                    # Uitspraak van de hele zin (Erasmiaans, via de fonetische transliteratie).
                    audio_knop(bijbelzin_fonetisch(_zin), key="ontlzin")
                    if _hover:
                        st.caption("💡 Hover (of tik) over een woord voor de betekenis en ontleding.")

                    # Vaste balk met de uitslag van het vorige woord (wat goed was + wat het woord is).
                    _tfb = st.session_state.get('ontl_topfb')
                    if _tfb:
                        {"success": st.success, "info": st.info}.get(_tfb.get('type'), st.info)(_tfb.get('msg', ''))

                    # Basiswoord-hulp: toon de woordenboekvorm bij het huidige woord (zonder betekenis).
                    if _obasis and _hidx >= 0 and _fase in ('woordsoort', 'znw', 'ww', 'vertalen'):
                        _bw = next((v for v in (st.session_state.get('data') or [])
                                    if str(v.get('strong')) == str(_zin[_hidx].get('strong')) and v.get('strong')), None)
                        if _bw:
                            _blem = str(_bw.get('grieks', '')); _bgi = str(_bw.get('grieks_info', '')).strip()
                            _btxt = f"🔑 Basiswoord: **{_blem}**" + (f" — {_bgi}" if _bgi and _bgi != _blem else "")
                            st.caption(_btxt)

                    _rondes = {'woordsoort': '1/5 · Woordsoort van elk woord', 'znw': '2/5 · Naamwoorden ontleden',
                               'ww': '3/5 · Werkwoorden ontleden', 'vertalen': '4/5 · Woord voor woord vertalen',
                               'zin': '5/5 · Hele zin vertalen', 'klaar': 'Klaar'}
                    if _fase not in ('zin', 'klaar'):
                        st.progress(min(_pos, len(_lijst)) / max(1, len(_lijst)),
                                    text=f"Ronde {_rondes.get(_fase, '')} — {min(_pos + 1, len(_lijst))} van {len(_lijst)}")
                    elif _fase == 'zin':
                        st.caption(f"Ronde {_rondes['zin']}")

                    def _tel_deel(_dim, _goed):
                        _rec = st.session_state.ontleed_stats.setdefault(_dim, {'g': 0, 'f': 0})
                        _rec['g' if _goed else 'f'] = int(_rec.get('g' if _goed else 'f', 0)) + 1

                    def _eerste_keer():
                        _sleutel = (_fase, _hidx)
                        _gt = st.session_state.get('ontl_geteld') or set()
                        return _sleutel not in _gt

                    def _markeer_geteld():
                        _gt = st.session_state.get('ontl_geteld') or set()
                        _gt.add((_fase, _hidx)); st.session_state.ontl_geteld = _gt

                    if _fase == 'woordsoort':
                        _w = _zin[_hidx]; _info = _w.get('parsing_info', '')
                        st.markdown(f"<div style='font-size:34px;font-weight:800;color:#33ccff'>{_w.get('grieks','')}</div>", unsafe_allow_html=True)
                        _kz = st.radio("Woordsoort:", _ONTLEED_WS_OPTS, index=None, horizontal=True,
                                       key=f"ontl_ws_{st.session_state.ontl_ref}_{_pos}")
                        if st.session_state.get('ontl_feedback'):
                            for _line in st.session_state.ontl_feedback:
                                st.markdown(_line)
                        if st.button("✓ Nakijken", key=f"ontl_wscheck_{_pos}", type="primary"):
                            _ok = _ontleed_deel_ok('woordsoort', _kz, _info)
                            if _eerste_keer() and _kz is not None:
                                _tel_deel('woordsoort', _ok); _markeer_geteld()
                            if _ok:
                                st.session_state.ontl_topfb = {"type": "success", "msg": f"✅ **{_w.get('grieks','')}** — {_ontleed_deel_correct('woordsoort', _info)}"}
                                st.session_state.ontl_pos += 1
                                st.session_state.ontl_feedback = None
                                if st.session_state.ontl_pos >= len(_lijst):
                                    _ontl_advance()
                                trigger_save()
                            else:
                                st.session_state.ontl_feedback = [f"❌ Juist is **{_ontleed_deel_correct('woordsoort', _info)}**."]
                            st.rerun()

                    elif _fase in ('znw', 'ww'):
                        _w = _zin[_hidx]; _info = _w.get('parsing_info', '')
                        st.markdown(f"<div style='font-size:34px;font-weight:800;color:#33ccff'>{_w.get('grieks','')}</div>", unsafe_allow_html=True)
                        _dims = _ontleed_dims_zonder_ws(_info)
                        # Stapsgewijs tonen: de volgende rij verschijnt pas als je de vorige hebt
                        # aangeklikt. Zo verraadt de rij Naamval/Geslacht niet meteen dat het een
                        # participium is — die komt pas ná je Wijs-keuze. Bolletjes blijven.
                        def _rk(_key):
                            return f"ontl_{_key}_{st.session_state.ontl_ref}_{_fase}_{_pos}"
                        _beantwoord = 0
                        for _key, _label, _opts in _dims:
                            if st.session_state.get(_rk(_key)) is not None:
                                _beantwoord += 1
                            else:
                                break
                        _toon_n = min(len(_dims), _beantwoord + 1)
                        _keuzes = {}
                        for _key, _label, _opts in _dims[:_toon_n]:
                            _keuzes[_key] = st.radio(_label, _opts, index=None, horizontal=True, key=_rk(_key))
                        _alles_ingevuld = (_beantwoord >= len(_dims))
                        if not _alles_ingevuld:
                            st.caption("↓ Vul in; de volgende regel verschijnt zodra je iets aanklikt.")
                        if st.session_state.get('ontl_feedback'):
                            for _line in st.session_state.ontl_feedback:
                                st.markdown(_line)
                        # De spiek-/opbouwhulp staat ONDER de check-knop (zie het hulpblok onderaan),
                        # zodat het doelwoord en de antwoordknoppen bij elkaar staan.
                        _cA, _cB = st.columns(2)
                        if _alles_ingevuld and _cA.button("✓ Check antwoord", key=f"ontl_check_{_fase}_{_pos}", type="primary"):
                            _res = []; _alle_goed = True; _eerste = _eerste_keer()
                            for _key, _label, _opts in _dims:
                                _kz = _keuzes.get(_key)
                                _ok = _ontleed_deel_ok(_key, _kz, _info)
                                if _eerste and _kz is not None:
                                    _tel_deel(_key, _ok)
                                if _ok:
                                    _res.append(f"- ✅ **{_label}:** {_kz}")
                                else:
                                    _alle_goed = False
                                    _res.append(f"- ❌ **{_label}:** juist is **{_ontleed_deel_correct(_key, _info)}**")
                            if _eerste:
                                _markeer_geteld()
                            if _alle_goed:
                                _nv = _ontleed_deel_correct('naamval', _info)
                                st.session_state.ontl_kleur[_hidx] = _ONTLEED_KLEUR.get(_nv, "#20c997")
                                st.session_state.ontl_topfb = {"type": "success", "msg": f"✅ **{_w.get('grieks','')}** — {_info}"}
                                st.session_state.ontl_pos += 1
                                st.session_state.ontl_feedback = None
                                if st.session_state.ontl_pos >= len(_lijst):
                                    _ontl_advance()
                                trigger_save()
                            else:
                                _amb = ambiguiteit_regel(_obdb, _w.get('grieks', ''), _w.get('strong'),
                                                         _keuzes, _info, _dims)
                                if _amb:
                                    _res.append(_amb)
                                st.session_state.ontl_feedback = _res
                            st.rerun()
                        if _cB.button("👁️ Toon antwoord", key=f"ontl_toon_{_fase}_{_pos}"):
                            if _eerste_keer():
                                for _key, _label, _opts in _dims:
                                    _tel_deel(_key, False)
                                _markeer_geteld()
                            _nv = _ontleed_deel_correct('naamval', _info)
                            st.session_state.ontl_kleur[_hidx] = _ONTLEED_KLEUR.get(_nv, "#20c997")
                            st.session_state.ontl_topfb = {"type": "info", "msg": f"👁️ **{_w.get('grieks','')}** — {_info}"}
                            st.session_state.ontl_pos += 1
                            st.session_state.ontl_feedback = None
                            if st.session_state.ontl_pos >= len(_lijst):
                                _ontl_advance()
                            st.rerun()

                    elif _fase == 'vertalen':
                        _w = _zin[_hidx]; _info = _w.get('parsing_info', '')
                        _vorm = _info.split(' - ', 1)[1] if ' - ' in _info else _info
                        st.markdown(f"<div style='font-size:34px;font-weight:800;color:#33ccff'>{_w.get('grieks','')}</div>", unsafe_allow_html=True)
                        st.caption(f"Vorm: *{_vorm}* — houd rekening met naamval/tijd in je vertaling.")
                        # De vertaal-/opbouwhulp staat ONDER de check-knop (zie het hulpblok onderaan).
                        if st.session_state.get('ontl_feedback'):
                            for _line in st.session_state.ontl_feedback:
                                st.markdown(_line)
                        forceer_focus()   # cursor staat meteen in het typveld, zo kun je doortikken
                        with st.form(f"ontl_vform_{st.session_state.ontl_ref}_{_pos}", clear_on_submit=True):
                            _vin = st.text_input("Vertaling van dit woord:")
                            _vsub = st.form_submit_button("✓ Nakijken", type="primary")  # Enter werkt binnen een form
                        if _vsub:
                            _vok = check_betekenis(_vin or "", _w.get('vertaling_nl', ''))
                            if _eerste_keer() and (_vin or "").strip():
                                _tel_deel('vertaling', _vok); _markeer_geteld()
                            if _vok:
                                # Goede vertaling telt POSITIEF mee voor de woord-streak (nooit aftrek in deze tab).
                                _vw = next((v for v in (st.session_state.get('data') or [])
                                            if str(v.get('strong')) == str(_w.get('strong')) and v.get('strong')), None)
                                if _vw is not None:
                                    _vw['streak'] = int(_vw.get('streak', 0)) + 1
                                    _vw['score_goed'] = int(_vw.get('score_goed', 0)) + 1
                                st.session_state.ontl_topfb = {"type": "success", "msg": f"✅ **{_w.get('grieks','')}** = {_w.get('vertaling_nl','')}"}
                                st.session_state.ontl_pos += 1
                                st.session_state.ontl_feedback = None
                                if st.session_state.ontl_pos >= len(_lijst):
                                    _ontl_advance()
                                trigger_save()
                            else:
                                st.session_state.ontl_feedback = [f"❌ Het is o.a. *{str(_w.get('vertaling_nl','')).split(',')[0]}*. Probeer opnieuw of klik 'Toon'."]
                            st.rerun()
                        if st.button("👁️ Toon antwoord", key=f"ontl_vtoon_{_pos}"):
                            if _eerste_keer():
                                _tel_deel('vertaling', False); _markeer_geteld()
                            st.session_state.ontl_topfb = {"type": "info", "msg": f"👁️ **{_w.get('grieks','')}** = {_w.get('vertaling_nl','')}"}
                            st.session_state.ontl_feedback = None
                            st.session_state.ontl_pos += 1
                            if st.session_state.ontl_pos >= len(_lijst):
                                _ontl_advance()
                            st.rerun()

                    elif _fase == 'zin':
                        st.success("✅ Alles ontleed! Vertaal nu de **hele zin** — kies per woord de best passende betekenis.")
                        with st.expander("📖 Alle woorden met betekenis (kies de beste glosse)", expanded=True):
                            for w in _zin:
                                if not w.get('strong'):
                                    continue
                                _nl = w.get('vertaling_nl', '') or w.get('vertaling_bsb', '')
                                st.markdown(f"- **{w.get('grieks','')}** — {_nl}")
                        if _osteun:
                            with st.expander("💡 Hoe vertaal je de vormen in deze zin?", expanded=False):
                                _gezien_r = []
                                for _i2 in (st.session_state.ontl_znw + st.session_state.ontl_ww):
                                    for _r in _ontleed_vertaalhulp(_zin[_i2].get('parsing_info', '')):
                                        if _r not in _gezien_r:
                                            _gezien_r.append(_r); st.markdown("- " + _r)
                        st.text_area("Jouw vertaling van de hele zin:", key=f"ontl_zin_{st.session_state.ontl_ref}", height=90)
                        if st.button("👁️ Toon modelvertaling", key="ontl_zintoon"):
                            _en = " ".join(str(w.get('vertaling_bsb', '')) for w in _zin if w.get('strong') and w.get('vertaling_bsb'))
                            st.session_state.ontl_zin_model = _en.strip() or "(geen Engelse vertaling beschikbaar)"
                        if st.session_state.get('ontl_zin_model'):
                            st.info(f"**Engelse vertaling (BSB, ter controle):**\n\n{st.session_state.ontl_zin_model}")
                        if st.button("➡️ Volgend vers", key="ontl_volgend_zin", type="primary"):
                            st.session_state.ontl_zin_model = None
                            _nieuw_ontleed_vers(); st.rerun()

                    else:  # klaar
                        st.success("🎉 Hele vers ontleed én vertaald! Goed gedaan.")
                        if st.button("➡️ Volgend vers", key="ontl_volgend", type="primary"):
                            _nieuw_ontleed_vers(); st.rerun()

                    # === HULP: ALLE uitklap-balkjes staan hier, ÓNDER het antwoord + de check-knop, zodat
                    # het doelwoord en de invoer altijd bij elkaar staan (fijner op mobiel). ===
                    if _osteun:
                        if _fase in ('woordsoort', 'znw', 'ww', 'vertalen') and _hidx >= 0:
                            _hw = _zin[_hidx]
                            _hinfo = _hw.get('parsing_info', '')
                            _hvw = next((v for v in (st.session_state.get('data') or [])
                                         if str(v.get('strong')) == str(_hw.get('strong')) and v.get('strong')), None)
                            _hlemma = str(_hvw.get('grieks', '')) if _hvw else ""
                            _hginfo = str(_hvw.get('grieks_info', '')) if _hvw else ""
                            _hopen = bool(st.session_state.get('ontl_feedback'))   # na een fout meteen open
                            if _fase == 'vertalen':
                                toon_vertaalhulp(_hinfo, sleutel=f"ontl_vert_{_pos}")
                            toon_opbouw_hulp(_hw.get('grieks', ''), _hlemma, _hinfo, _hginfo,
                                             uitgeklapt=_hopen, strong=_hw.get('strong'))
                            toon_rijtje_hulp(_hinfo, _hlemma, _hginfo,
                                             sleutel=f"ontl_{_fase}_{_pos}", uitgeklapt=_hopen)
                            toon_engels_diagram(_hw.get('grieks', ''), _obdb, sleutel=f"ontl_{_fase}_{_pos}",
                                                strong=_hw.get('strong'), parsing_info=_hinfo)
                            _bh = biblehub_regel(st.session_state.ontl_ref, _hw.get('strong'))
                            if _bh:
                                st.caption(_bh)
                        elif _fase == 'zin':
                            # Bij de hele zin: alle ontlede woorden met hun eigen rijtje op een rij.
                            with st.expander("📋 De rijtjes van de woorden in deze zin", expanded=False):
                                for _zi in (st.session_state.ontl_znw + st.session_state.ontl_ww):
                                    _zw = _zin[_zi]
                                    _zvw = next((v for v in (st.session_state.get('data') or [])
                                                 if str(v.get('strong')) == str(_zw.get('strong')) and v.get('strong')), None)
                                    st.markdown(f"**{_zw.get('grieks','')}** — {_zw.get('parsing_info','')}")
                                    toon_rijtje_hulp(_zw.get('parsing_info', ''),
                                                     str(_zvw.get('grieks', '')) if _zvw else "",
                                                     str(_zvw.get('grieks_info', '')) if _zvw else "",
                                                     sleutel=f"ontl_zin_{_zi}", uitgeklapt=False)
                        with st.expander("💡 Vertaalhulp: naamvallen & vormen (volledig overzicht)", expanded=False):
                            for _c in ["Nom", "Gen", "Dat", "Acc", "Voc"]:
                                st.markdown("- " + _ONTLEED_STEUN[_c])
                            for _t in ["Praesens", "Imperfectum", "Futurum", "Aoristus", "Perfectum", "Plusquamperfectum",
                                       "Participium", "Infinitivus", "Conjunctivus", "Optativus", "Imperativus", "Actief", "Medium", "Passief"]:
                                st.markdown("- " + _ONTLEED_STEUN[_t])
                    st.caption("📊 Je ontleed-accuratesse per onderdeel vind je op het **📊 Voortgang**-tabblad.")

        # ==========================================
        # DAGELIJKS DOEL — ondergebracht onderaan de Voortgang-tab
        # ==========================================
        if _TOON[2]:
         with menu[2]:
            st.write("---")
            st.subheader("🎯 Dagelijks doel")
            _cfg = dagdoel_config()
            _lg = dagdoel_log_vandaag()

            c_top1, c_top2 = st.columns(2)
            c_top1.metric("🔥 Oefen-streak", f"{dagdoel_streak()} dagen op rij",
                          help="Aantal dagen achter elkaar dat je iets hebt geoefend — wat je oefent maakt niet uit.")
            c_top2.metric("Totaal geoefend vandaag", int((st.session_state.dag_stats or {}).get(_vandaag_str(), 0)))
            st.caption(f"Doel vandaag: **{_cfg['woorden']} woorden · {_cfg['stam']} stamtijden · {_cfg['struct']} structuurwoorden · {_cfg['actief']} actief-cellen · {_cfg['verzen']} verzen**. Alles telt automatisch mee zodra je goed antwoordt in het betreffende tabblad.")

            st.write("---")
            st.markdown("### ✅ Voortgang onderdelen vandaag")
            st.caption("Deze tellen automatisch mee zodra je een goed antwoord geeft in dat tabblad.")
            for _soort, _emoji, _label in [('woorden', '🚀', 'Woorden (verschillende)'),
                                           ('actief', '🎓', 'Actief Beheersen'),
                                           ('stam', '⏳', 'Stamtijden'),
                                           ('struct', '🧱', 'Structuurwoorden'),
                                           ('verzen', '📝', 'Verzen ontleden'),
                                           ('klank', '🔊', 'Klankwetten')]:
                # 'Woorden' telt het aantal VERSCHILLENDE woorden dat je vandaag hebt gehad; hetzelfde
                # woord twee keer overhoren telt dus één keer (live berekend, altijd actueel).
                _gedaan = woorden_vandaag_uniek() if _soort == 'woorden' else int(_lg.get(_soort, 0))
                _doel = int(_cfg[_soort])
                st.progress(min(1.0, _gedaan / _doel) if _doel else 1.0, text=f"{_emoji} {_label}: {_gedaan}/{_doel}")
            st.caption("ℹ️ Bij **Woorden** tellen verschillende woorden: oefen je hetzelfde woord vaker, "
                       "dan telt dat één keer. De andere tellers tellen elk goed antwoord.")

            with st.expander("⚙️ Mijn dagelijkse doelen instellen"):
                _nw = {
                    'woorden': st.slider("Woorden", 0, 40, _cfg['woorden'], key="dd_woorden"),
                    'knelpunt': st.slider("Moeilijke woorden", 0, 20, _cfg['knelpunt'], key="dd_knelpunt"),
                    'verwar': st.slider("Verwarparen", 0, 15, _cfg['verwar'], key="dd_verwar"),
                    'actief': st.slider("Actief Beheersen (cellen)", 0, 30, _cfg['actief'], key="dd_actief"),
                    'stam': st.slider("Stamtijden", 0, 20, _cfg['stam'], key="dd_stam"),
                    'struct': st.slider("Structuurwoorden", 0, 20, _cfg['struct'], key="dd_struct"),
                    'verzen': st.slider("Verzen ontleden", 0, 10, _cfg['verzen'], key="dd_verzen"),
                    'klank': st.slider("Klankwetten", 0, 30, _cfg['klank'], key="dd_klank"),
                }
                if st.button("💾 Doelen opslaan", key="dd_save"):
                    _d = st.session_state.get('dagdoel')
                    if not isinstance(_d, dict):
                        _d = {}; st.session_state.dagdoel = _d
                    _d['config'] = _nw
                    trigger_save(forceer=True); st.success("Doelen opgeslagen!"); st.rerun()


        # ==========================================
        # TAB: KLANKWETTEN & SAMENSMELTINGEN
        # ==========================================
        if _TOON[11]:
         with menu[11]:
            st.subheader("🔊 Klankwetten & samensmeltingen")
            st.caption("Leer herkennen **welke letters zijn samengesmolten** (κ + σ → ξ) en **van welk "
                       "werkwoord** een vorm komt. Alle vormen komen echt in het Nieuwe Testament voor en "
                       "gaan alleen over woorden die jij al kent.")

            _kprefs = st.session_state.get('ui_prefs')
            if not isinstance(_kprefs, dict):
                _kprefs = {}; st.session_state.ui_prefs = _kprefs
            _kdb = laad_bijbel_db()
            _kdata = st.session_state.get('data') or []
            _kbron = {str(v.get('strong')): v for v in _kdata if v.get('strong') and v.get('grieks')}
            _kginfo = {str(v.get('strong')): str(v.get('grieks_info', '') or '') for v in _kdata if v.get('strong')}
            _kbet = {str(v.get('strong')): str(v.get('nederlands', '')) for v in _kdata if v.get('strong')}
            _kstreak = {str(v.get('strong')): int(v.get('streak', 0) or 0) for v in _kdata if v.get('strong')}
            _kles = {str(v.get('strong')): veilig_les_nummer(v) for v in _kdata if v.get('strong')}

            if not _kdb:
                st.info("De Bijbeltekst-database is niet beschikbaar.")
            else:
                _kidx = klankwet_index(_kdb, _kbron)
                _kformules = klankwet_formule_index(_kdb, _kbron)

                # --- Instellingen (mobielvriendelijk achter één dropdown) ---
                with st.expander("⚙️ Instellingen (klanksoorten · niveau · lessen)", expanded=False):
                    _beschikbaar = [s for s in _SAMENSMELT_KLASSEN if _kidx.get(s)]
                    _labels = {s: f"{_SAMENSMELT_KLASSEN[s][0]} ({_SAMENSMELT_KLASSEN[s][1]})" for s in _beschikbaar}
                    _vorige = [s for s in (_kprefs.get('klank_klassen') or []) if s in _beschikbaar]
                    _gekozen = st.multiselect("Welke klanksoorten wil je oefenen?", _beschikbaar,
                                              default=_vorige or _beschikbaar,
                                              format_func=lambda s: _labels.get(s, s), key="klank_klassen_ms")
                    _kprefs['klank_klassen'] = list(_gekozen)
                    if not _gekozen:
                        _gekozen = list(_beschikbaar)
                    _kdrempel = st.slider("Alleen woorden die ik ken (min. streak):", 1, 30,
                                          int(_kprefs.get('klank_drempel', 5)), key="klank_drempel_s",
                                          help="Standaard 5: het woord moet je al een paar keer goed hebben gehad.")
                    _kprefs['klank_drempel'] = _kdrempel
                    _kalle_lessen = sorted({veilig_les_nummer(i) for i in _kdata})
                    _klc1, _klc2 = st.columns([2, 1])
                    _kalles = _klc2.toggle("Alle lessen", value=bool(_kprefs.get('klank_alles', True)),
                                           key="klank_alles_t")
                    _kprefs['klank_alles'] = _kalles
                    if _kalles:
                        _klc1.caption("Woorden mogen uit **alle lessen** komen.")
                        _klessen = set(_kalle_lessen)
                    else:
                        _kvorige = [l for l in (_kprefs.get('klank_lessen') or []) if l in _kalle_lessen]
                        _ksel = _klc1.multiselect("Uit welke lessen?", _kalle_lessen,
                                                  default=_kvorige or _kalle_lessen[:1], key="klank_lessen_ms")
                        _kprefs['klank_lessen'] = list(_ksel)
                        _klessen = set(_ksel)
                    _kmarkeer = st.toggle("🔦 Markeer de letter waar het om gaat",
                                          value=bool(_kprefs.get('klank_markeer', True)),
                                          key="klank_markeer_t",
                                          help="Kleurt in het woord de letter die uit de samensmelting is ontstaan. Handig om te zien wáár het gebeurt; zet uit als je het zelf wilt zoeken.")
                    _kprefs['klank_markeer'] = _kmarkeer

                # --- Naslag: de regels uit de grammatica op een rij ---
                _kcdb = laad_contractie_db()
                if _kcdb:
                    with st.expander("📋 De regels op een rij (naslag)", expanded=False):
                        if _kcdb.get('sigma'):
                            st.markdown("##### σ-samensmeltingen (futurum & aoristus)")
                            _rijen = ["| Klasse | Medeklinkers | + σ wordt | Voorbeeld |", "|---|---|---|---|"]
                            for _r in _kcdb['sigma']:
                                _vb = _r.get('vb') or []
                                _vbtxt = f"{_vb[0][0]} → {_vb[0][1]}" if _vb and len(_vb[0]) >= 2 else ""
                                _rijen.append(f"| **{_r.get('klasse','')}** | {_r.get('medeklinkers','')} | "
                                              f"{_r.get('uitkomst','')} | {_vbtxt} |")
                            st.markdown("\n".join(_rijen))
                        if _kcdb.get('contracta'):
                            st.markdown("##### Verba contracta (G20) — klinkers die samentrekken")
                            _perstam = {}
                            for _r in _kcdb['contracta']:
                                _perstam.setdefault(_r.get('stam', '?'), []).append(_r)
                            for _stam, _rs in _perstam.items():
                                st.markdown(f"**Stam op -{_stam}:** " +
                                            " · ".join(f"{_r.get('combo','')} → **{_r.get('uitkomst','')}**" for _r in _rs))
                            if _kcdb.get('contracta_noot'):
                                st.caption(_kcdb['contracta_noot'])
                        if _kcdb.get('augment'):
                            st.markdown("##### Augment (verleden tijd)")
                            for _r in _kcdb['augment']:
                                _vb = _r.get('vb') or []
                                _vbtxt = f" — *{_vb[0][0]} → {_vb[0][1]}*" if _vb and len(_vb[0]) >= 2 else ""
                                st.markdown(f"- Begint op **{_r.get('begin','')}**: {_r.get('regel','')}{_vbtxt}")

                # --- De oefenvoorraad: alleen woorden die je kent, uit de gekozen lessen ---
                _kpool = []
                for _s in _gekozen:
                    for (_vorm, _lem, _info, _ref, _strong) in _kidx.get(_s, []):
                        if _kstreak.get(_strong, 0) < _kdrempel:
                            continue
                        if not _kalles and _kles.get(_strong) not in _klessen:
                            continue
                        _kpool.append((_s, _vorm, _lem, _info, _ref, _strong))

                _kstats = st.session_state.get('klank_stats')
                if not isinstance(_kstats, dict):
                    _kstats = {}; st.session_state.klank_stats = _kstats

                if not _kpool:
                    st.warning(f"Nog geen oefenvormen bij deze instellingen. Zet de streak-drempel lager "
                               f"(staat nu op {_kdrempel}), kies meer klanksoorten of meer lessen — je oefent "
                               "alleen met werkwoorden die je al kent.")
                else:
                    _perklasse = {}
                    for _p in _kpool:
                        _perklasse[_p[0]] = _perklasse.get(_p[0], 0) + 1
                    st.caption("🎯 " + " · ".join(f"{_SAMENSMELT_KLASSEN[_s][0]}: {_n}"
                                                  for _s, _n in sorted(_perklasse.items())))

                    def _klank_van(_v, _l, _i, _st, _sleut):
                        """(analyse van deze kaart, overige klankwetten in dezelfde vorm)."""
                        _alles = samensmeltingen_alle(_v, _l, _i,
                                                      grieks_info=_kginfo.get(_st, ''),
                                                      corpus_stam=corpus_stam_van(_st, _i))
                        _deze = next((_a for _a in _alles if _a['sleutel'] == _sleut), None)
                        if _deze is None:
                            _deze = _alles[0] if _alles else {}
                        return _deze, [_a for _a in _alles if _a is not _deze]

                    def _klank_nieuw():
                        """Kiest een nieuwe oefenvorm; klanksoorten die je vaker fout doet komen vaker."""
                        _gewicht = []
                        for _p in _kpool:
                            _rec = _kstats.get(_p[0]) or {}
                            _f = int(_rec.get('f', 0)); _g = int(_rec.get('g', 0))
                            _gewicht.append(1 + min(6, 2 * _f) + (2 if (_g + _f) == 0 else 0))
                        _keuze = r_engine.choices(_kpool, weights=_gewicht, k=1)[0]
                        st.session_state.klank_huidig = _keuze
                        st.session_state.klank_fb = None
                        st.session_state.klank_geteld = False
                        _sleutel, _vorm, _lem, _info, _ref, _strong = _keuze
                        _an, _an_extra = _klank_van(_vorm, _lem, _info, _strong, _sleutel)
                        # Antwoordopties: eerst afleiders uit DEZELFDE klanksoort (κ/γ/χ door elkaar
                        # halen is de klassieke fout), daarna uit andere soorten.
                        _juist = _an.get('formule', '')
                        _afl = klank_afleiders(_sleutel, _juist, _kformules, r_engine, aantal=3)
                        _opties = [_juist] + _afl
                        r_engine.shuffle(_opties)
                        st.session_state.klank_opts_regel = _opties
                        # Basiswoord-opties: andere lemma's uit dezelfde klasse (lijken meer op elkaar).
                        _strong_van_lem = {}
                        for (_v3, _l3, _i3, _r3, _s3) in _kidx.get(_sleutel, []):
                            _strong_van_lem.setdefault(_l3, _s3)
                        def _toon_lem(_l):
                            _b = _kbet.get(_strong_van_lem.get(_l, ''), '')
                            _b = _b.split(',')[0].strip()
                            return f"{_l} ({_b})" if _b else _l
                        _lemmas = [_l3 for _l3 in _strong_van_lem if _l3 != _lem]
                        r_engine.shuffle(_lemmas)
                        _lopts = [_toon_lem(_lem)] + [_toon_lem(_x) for _x in _lemmas[:3]]
                        _lopts = list(dict.fromkeys(_lopts))
                        r_engine.shuffle(_lopts)
                        st.session_state.klank_opts_lemma = _lopts
                        st.session_state.klank_lemma_juist = _toon_lem(_lem)

                    if st.button("🎲 Nieuwe vorm", type="primary", key="klank_nieuw"):
                        _klank_nieuw(); st.rerun()

                    _ktop = st.session_state.get('klank_topfb')
                    if _ktop:
                        {"success": st.success, "info": st.info}.get(_ktop.get('type'), st.error)(_ktop.get('msg', ''))

                    _kh = st.session_state.get('klank_huidig')
                    if not _kh:
                        st.info("Klik op **🎲 Nieuwe vorm** om te beginnen.")
                    else:
                        _sleutel, _vorm, _lem, _info, _ref, _strong = _kh
                        _an, _an_extra = _klank_van(_vorm, _lem, _info, _strong, _sleutel)
                        # Volledige vormaanduiding: tijd + wijs + diathese + persoon/getal (of naamval).
                        _vorm_txt = _info.split(' - ', 1)[1] if ' - ' in _info else _info
                        _is_ww = "Werkwoord" in _info
                        _toon_vorm = klank_vorm_gemarkeerd(_vorm, _an) if _kmarkeer else _vorm
                        st.markdown(f"<div style='font-size:44px;font-weight:800;color:#33ccff;text-align:center;"
                                    f"padding:6px 0'>{_toon_vorm}</div>", unsafe_allow_html=True)
                        st.caption(f"📖 {_ref} · **{_vorm_txt}**" if _vorm_txt else f"📖 {_ref}")
                        st.caption("Welke klankwet zie je hier, en van welk "
                                   + ("werkwoord" if _is_ww else "woord") + " komt deze vorm?")

                        _kopts_r = st.session_state.get('klank_opts_regel') or []
                        _kopts_l = st.session_state.get('klank_opts_lemma') or []
                        with st.form(f"klank_form_{_vorm}_{_strong}", clear_on_submit=False):
                            _kz_regel = st.radio("1. Welke letters zijn hier samengegaan?", _kopts_r,
                                                 index=None, key=f"klank_r_{_vorm}_{_strong}")
                            _kz_lemma = st.radio("2. Van welk " + ("werkwoord" if _is_ww else "woord")
                                                 + " komt deze vorm?", _kopts_l,
                                                 index=None, key=f"klank_l_{_vorm}_{_strong}")
                            _ksub = st.form_submit_button("✓ Nakijken", type="primary")

                        if st.session_state.get('klank_fb'):
                            for _regel in st.session_state.klank_fb:
                                st.markdown(_regel)

                        if _ksub:
                            registreer_oefening()
                            _ok_r = (_kz_regel == _an.get('formule'))
                            _ok_l = (_kz_lemma == st.session_state.get('klank_lemma_juist', _lem))
                            if not st.session_state.get('klank_geteld'):
                                _rec = _kstats.setdefault(_sleutel, {'g': 0, 'f': 0})
                                _rec['g' if _ok_r else 'f'] = int(_rec.get('g' if _ok_r else 'f', 0)) + 1
                                _recb = _kstats.setdefault('basiswoord', {'g': 0, 'f': 0})
                                _recb['g' if _ok_l else 'f'] = int(_recb.get('g' if _ok_l else 'f', 0)) + 1
                                st.session_state.klank_geteld = True
                            _res = []
                            _res.append(f"- {'✅' if _ok_r else '❌'} **Samensmelting:** "
                                        f"{_an.get('formule','—')} ({_an.get('klasse','')})")
                            _res.append(f"- {'✅' if _ok_l else '❌'} **Basiswoord:** {_lem}"
                                        + (f" — *{_kbet.get(_strong,'')}*" if _kbet.get(_strong) else ""))
                            if _an.get('uitleg'):
                                _res.append(f"- 💡 {_an['uitleg']}")
                            for _ax in _an_extra:
                                _res.append(f"- ➕ **Ook in deze vorm:** {_ax['formule']} ({_ax['klasse']}) — {_ax['uitleg']}")
                            # Laat expliciet zien hoe de vorm is opgebouwd — welke uitgang er staat en
                            # waar die met de stam samensmelt.
                            _kseg = ontleed_segmenten(_vorm, _lem, _kginfo.get(_strong, ''), _info,
                                                      corpus_stam=corpus_stam_van(_strong, _info))
                            if _kseg:
                                _res.append("- 🧩 **Opbouw:** " + " + ".join(f"**{_t}**" for _t, _s2 in _kseg)
                                            + f" → **{_vorm}**  ({' + '.join(_s2 for _t, _s2 in _kseg)})")
                            if _an.get('stam'):
                                _res.append(f"- 🔑 **Echte stam:** {_an['stam']}- "
                                            f"(daar botst **{_an.get('links','')}** met de uitgang)")
                            if _ok_r and _ok_l:
                                dagdoel_plus('klank')
                                _opb = klank_opbouw_regels(_vorm, _an, _kseg)
                                st.session_state.klank_topfb = {
                                    "type": "success",
                                    "msg": f"✅ **{_vorm}** ({_vorm_txt}) — van **{_lem}**"
                                           + (_NR + _NR.join(_opb) if _opb else "")}
                                st.session_state.klank_fb = None
                                trigger_save(); _klank_nieuw()
                            else:
                                st.session_state.klank_fb = _res
                            st.rerun()

                        _kc1, _kc2 = st.columns(2)
                        if _kc1.button("🤔 Ik weet het niet — toon het antwoord", key=f"klank_weet_{_vorm}_{_strong}"):
                            if not st.session_state.get('klank_geteld'):
                                _rec = _kstats.setdefault(_sleutel, {'g': 0, 'f': 0})
                                _rec['f'] = int(_rec.get('f', 0)) + 1
                                st.session_state.klank_geteld = True
                            _opb_w = klank_opbouw_regels(
                                _vorm, _an,
                                ontleed_segmenten(_vorm, _lem, _kginfo.get(_strong, ''), _info,
                                                  corpus_stam=corpus_stam_van(_strong, _info)))
                            st.session_state.klank_topfb = {
                                "type": "info",
                                "msg": f"💡 **{_vorm}** ({_vorm_txt}) — van **{_lem}**. {_an.get('uitleg','')}"
                                       + (_NR + _NR.join(_opb_w) if _opb_w else "")}
                            st.session_state.klank_fb = None
                            _klank_nieuw(); st.rerun()
                        if _kc2.button("➡️ Overslaan", key=f"klank_skip_{_vorm}_{_strong}"):
                            st.session_state.klank_fb = None
                            _klank_nieuw(); st.rerun()

                        # De hele zin erbij, zodat je de vorm in zijn context ziet staan.
                        with st.expander("📖 Bekijk het vers waar deze vorm in staat", expanded=False):
                            _kzin = _kdb.get(_ref) or []
                            _khtml = ""
                            for _w in _kzin:
                                _g = str(_w.get('grieks', '') or '')
                                _pi = _w.get('parsing_info', '') or ''
                                if _g == _vorm:
                                    _stijl = ("background:rgba(255,215,0,.25);border-bottom:3px solid #ffd700;"
                                              "padding:0 3px;border-radius:4px;font-weight:700")
                                else:
                                    # Naamvalkleuren staan hier standaard aan (het antwoord is al gegeven).
                                    _nvk = next((c for c in ("Nom", "Gen", "Dat", "Acc", "Voc") if c in _pi), None)
                                    _stijl = f"color:{_ONTLEED_KLEUR.get(_nvk, '#9aa3af')}"
                                _tt = (str(_w.get('vertaling_nl', '') or _w.get('vertaling_bsb', '')) +
                                       ("  ·  " + _pi if _pi else "")).replace("'", "&#39;").replace('"', "&quot;")
                                _khtml += (f"<span class='mobile-tooltip' tabindex='0' style='{_stijl}'>{_g}"
                                           f"<span class='tooltiptext'>{_tt}</span></span>"
                                           f"{_w.get('interpunctie','')} ")
                            st.markdown(f"<div style='font-size:20px;line-height:1.6'>{_khtml.strip()}</div>",
                                        unsafe_allow_html=True)
                            st.caption("💡 Hover (of tik) over een woord voor de betekenis en ontleding. "
                                       + " · ".join(f":{c}[{n}]" for c, n in
                                                    [("blue", "Nom"), ("green", "Gen"), ("violet", "Dat"),
                                                     ("red", "Acc"), ("orange", "Voc")]))

                    # --- Hoe doe je het? ---
                    _ktot_g = sum(int((v or {}).get('g', 0)) for v in _kstats.values())
                    _ktot_f = sum(int((v or {}).get('f', 0)) for v in _kstats.values())
                    if _ktot_g + _ktot_f:
                        st.write("---")
                        st.markdown("##### 📊 Jouw klankwet-score")
                        for _s in sorted(_kstats):
                            _rec = _kstats.get(_s) or {}
                            _g2 = int(_rec.get('g', 0)); _f2 = int(_rec.get('f', 0))
                            if _g2 + _f2 == 0:
                                continue
                            _naam = ("Basiswoord herkennen" if _s == 'basiswoord'
                                     else _SAMENSMELT_KLASSEN.get(_s, (_s, ''))[0])
                            st.progress(_g2 / (_g2 + _f2), text=f"{_naam}: {_g2}/{_g2 + _f2} goed")

if __name__ == "__main__":
    main()
