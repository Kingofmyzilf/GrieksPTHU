# -*- coding: utf-8 -*-
"""De Griekse motor: ontleding, klankwetten, stamtijden, woordkeuze en voortgang.

Dit bestand kent geen UI-framework. Het is losgemaakt uit overhoring_web.py zodat
dezelfde logica onder Streamlit én onder een andere schil (NiceGUI) kan draaien.
Automatisch gegenereerd door scratchpad/bouw_motor.py — pas de bron aan, niet dit bestand.
"""
import copy
import functools
from datetime import datetime
import functools
import json
import math
import os
import random as r_engine
import re
import unicodedata


# --- omgeving ------------------------------------------------------------
# Deze twee staan in de bron in een try-blok (optionele afhankelijkheden) en
# worden daarom apart meegegeven in plaats van uit de broncode gekopieerd.
try:
    from zoneinfo import ZoneInfo
    _TIJDZONE = ZoneInfo("Europe/Amsterdam")
except Exception:
    _TIJDZONE = None

try:
    import fitz  # PyMuPDF: rendert de grammatica-slides
    FITZ_BESCHIKBAAR = True
except Exception:
    fitz = None
    FITZ_BESCHIKBAAR = False


# --- cache ---------------------------------------------------------------
# Vervangt @st.cache_data en @st.cache_resource met dezelfde semantiek:
#  * argumenten waarvan de naam met _ begint tellen niet mee in de sleutel
#    (zo kunnen grote, niet-hashbare structuren worden doorgegeven);
#  * cache_data geeft een kopie terug, cache_resource het gedeelde object;
#  * .clear() maakt de cache leeg.
def _sleutel(fn, args, kwargs):
    namen = fn.__code__.co_varnames[:fn.__code__.co_argcount]
    deel = [a for n, a in zip(namen, args) if not n.startswith("_")]
    deel += [(k, v) for k, v in sorted(kwargs.items()) if not k.startswith("_")]
    return tuple(deel)


def _maak_cache(kopieer):
    def decorator(*dargs, **_dkw):
        def wrap(fn):
            opslag = {}

            @functools.wraps(fn)
            def binnen(*a, **k):
                try:
                    s = _sleutel(fn, a, k)
                except TypeError:
                    return fn(*a, **k)
                if s not in opslag:
                    opslag[s] = fn(*a, **k)
                r = opslag[s]
                return copy.deepcopy(r) if kopieer else r

            binnen.clear = opslag.clear
            binnen.__wrapped__ = fn
            return binnen

        if len(dargs) == 1 and callable(dargs[0]) and not _dkw:
            return wrap(dargs[0])
        return wrap
    return decorator


cache_data = _maak_cache(kopieer=True)
cache_resource = _maak_cache(kopieer=False)
# -------------------------------------------------------------------------

def _nu():
    """Huidige datum/tijd in de Nederlandse tijdzone (zonder tzinfo, zodat rekenen simpel blijft)."""
    if _TIJDZONE is not None:
        try:
            return datetime.now(_TIJDZONE).replace(tzinfo=None)
        except Exception:
            pass
    return datetime.now()


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


def naar_grieks_transliteratie(tekst):
    mapping = { 'a': 'α', 'b': 'β', 'g': 'γ', 'd': 'δ', 'e': 'ε', 'z': 'ζ', 'h': 'η', 'q': 'θ', 'i': 'ι', 'k': 'κ', 'l': 'λ', 'm': 'μ', 'n': 'ν', 'c': 'ξ', 'o': 'ο', 'p': 'π', 'r': 'ρ', 's': 'σ', 't': 'τ', 'u': 'υ', 'f': 'φ', 'x': 'χ', 'y': 'ψ', 'w': 'ω' }
    res = ""
    tekst = str(tekst).lower().strip()
    for char in tekst: res += mapping.get(char, char)
    # Alleen de LAATSTE sigma wordt een slot-sigma (ς); interne sigma's blijven σ.
    if res.endswith('σ'):
        res = res[:-1] + 'ς'
    return res


def _heeft_waarde(waarde):
    """True als er echt iets staat. Doet wat pandas' notna() deed: None en NaN tellen
    niet mee. Zo hoeft de NiceGUI-schil pandas niet te laden — dat scheelt zeventig
    megabyte geheugen op de server, voor deze ene controle. NaN is het enige dat
    ongelijk aan zichzelf is; daar herken je het aan."""
    return waarde is not None and waarde == waarde


@functools.lru_cache(maxsize=200000)
def normaliseer_accent(woord):
    if _heeft_waarde(woord) and str(woord).strip() != "":
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


_ONTLEED_KLEUR = {"Nom": "#7FB3FF", "Gen": "#E8B44A", "Dat": "#B694FF", "Acc": "#FF8FB1", "Voc": "#5ED3C0"}


def naamval_legenda(kop="Kleurlegenda"):
    """Eén legenda voor alle plekken, opgebouwd uit _ONTLEED_KLEUR zodat kleur en legenda
    niet uit elkaar kunnen lopen."""
    _sp = " · ".join(f"<span style='color:{_k}'>{_n}</span>" for _n, _k in _ONTLEED_KLEUR.items())
    return f"<div style='font-size:14px; margin-bottom:4px; opacity:.9'>{kop}: {_sp}</div>"


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


G20_CONTRACTA = {
    'ε': [("ε + ε", "ει"), ("ε + ει", "ει"), ("ε + η", "η"), ("ε + ο", "ου"), ("ε + ου", "ου"), ("ε + ω", "ω")],
    'α': [("α + ε", "α"), ("α + ει", "ᾳ"), ("α + η", "ᾳ"), ("α + ο", "ω"), ("α + ου", "ω"), ("α + ω", "ω")],
    'ο': [("ο + ε", "ου"), ("ο + ει", "οι"), ("ο + η", "οι"), ("ο + ο", "ου"), ("ο + ου", "ου"), ("ο + ω", "ω")],
    'η': [("η + ε", "η"), ("η + ει", "ῃ"), ("η + η", "ῃ"), ("η + ο", "ω"), ("η + ου", "ω"), ("η + ω", "ω")],
}


G20_INFINITIEF = {'α': "τιμα + εν → τιμᾶν", 'ε': "φιλε + εν → φιλεῖν",
                  'ο': "δηλο + εν → δηλοῦν", 'η': "ζη + εν → ζῆν"}


_ETA_CONTRACTA = {"ζαω", "πειναω", "διψαω", "χραομαι"}


_OPB_VOORVOEGSELS = ["προσ", "παρα", "περι", "κατα", "μετα", "ἀνα", "ἀπο", "ἐπι", "ὑπερ", "ὑπο",
                     "δια", "συν", "ἐκ", "ἐν", "εἰς", "προ", "ἀντι", "ἀμφι", "ἀφ", "ἀπ", "ἐξ",
                     "καθ", "μεθ", "παρ", "ἐπ", "ὑπ", "ἀν", "συγ", "συμ", "ἐγ", "ἐμ"]


_OPB_TIJD_MET_AUGMENT = ("Imperfectum", "Aoristus", "Plusquamperfectum")


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


_SAMENSMELT_KLASSEN = {
    "labialen":   ("Labialen", "π, β, φ"),
    "gutturalen": ("Gutturalen (keelklanken)", "κ, γ, χ"),
    "dentalen":   ("Dentalen", "τ, δ, θ, ζ"),
    "liquidae":   ("Liquidae (vloeiklanken)", "λ, μ, ν, ρ"),
    "contracta":  ("Contracta (klinkersamentrekking)", "α, ε, ο, η"),
    "augment":    ("Augment (klinkerverlenging)", "α, ε, ο, αι, ει, αυ"),
    "elisie":     ("Elisie (wegval vóór klinker)", "ά, έ, ό vooraan weg"),
}


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


_ELISIE_ASPIRATIE = {"φ": "π", "θ": "τ", "χ": "κ"}   # φ<π, θ<τ, χ<κ vóór een spiritus asper


_ELISIE_TEKENS = ("’", "᾽", "'", "ʼ")


def _elisie_treffer(vorm, lemma):
    """(weggevallen klinker, geschreven letter, oorspronkelijke letter) bij een elisie, of None.

    ἀλλά → ἀλλ᾽ : de laatste klinker valt weg vóór een woord dat met een klinker begint.
    ἐπί → ἐφ᾽   : daarbij wordt de π ook nog geaspireerd tot φ (vóór een spiritus asper).
    Alleen als de rest exact met het lemma overeenkomt — anders zeggen we niets."""
    v = str(vorm or "")
    if not any(t in v for t in _ELISIE_TEKENS):
        return None
    kaal = v
    for t in _ELISIE_TEKENS:
        kaal = kaal.replace(t, "")
    vk, lk = _opb_kaal(kaal), _opb_kaal(lemma)
    if not vk or not lk or len(lk) != len(vk) + 1:
        return None
    if lk.startswith(vk):
        return (lk[-1], "", "")
    origineel = _ELISIE_ASPIRATIE.get(vk[-1]) if vk else None
    if origineel and lk.startswith(vk[:-1] + origineel):
        return (lk[-1], vk[-1], origineel)
    return None


def samensmeltingen_alle(vorm, lemma="", parsing_info="", grieks_info="", corpus_stam=""):
    """ALLE klankwetten die in deze vorm te zien zijn, op volgorde van voor naar achter in het woord.

    Een vorm kan er meer dan één hebben: bij ἠγαπᾶτε (< ἀγαπάω) is vooraan de beginklinker verlengd
    als augment (α → η) én trekt achteraan de stamklinker samen met de uitgang (α + ε → ᾱ). Alleen
    één ervan tonen zou een half verhaal zijn."""
    uit = []
    if not vorm:
        return uit
    info = parsing_info or ""

    # Elisie kan bij elk woordsoort (ἀλλά → ἀλλ᾽, ἐπί → ἐφ᾽) — dus vóór alle andere regels.
    el = _elisie_treffer(vorm, lemma)
    if el:
        weg, geschreven, origineel = el
        klasse, letters = _SAMENSMELT_KLASSEN["elisie"]
        if geschreven:
            uit.append({"sleutel": "elisie", "klasse": klasse, "letters": letters, "links": weg,
                        "rechts": "klinker", "resultaat": "᾽", "plek": "einde", "pos": -1,
                        "formule": f"-{weg} valt weg  ·  {origineel} → {geschreven}",
                        "uitleg": f"**Elisie:** de slotklinker **{weg}** valt weg omdat het volgende woord "
                                  f"met een klinker begint; de **{origineel}** wordt daarbij geaspireerd tot "
                                  f"**{geschreven}** (het volgende woord heeft een spiritus asper)."})
        else:
            uit.append({"sleutel": "elisie", "klasse": klasse, "letters": letters, "links": weg,
                        "rechts": "klinker", "resultaat": "᾽", "plek": "einde", "pos": -1,
                        "formule": f"-{weg} valt weg (elisie)",
                        "uitleg": f"**Elisie:** de slotklinker **{weg}** valt weg omdat het volgende woord "
                                  f"met een klinker begint. De apostrof laat zien wat er ontbreekt."})
        return uit

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


@cache_resource(show_spinner=False)
def klankwet_index(_bijbel_db, _woord_van_strong):
    """{klasse-sleutel: [(vorm, lemma, parsing_info, ref, strong)]} — alle NT-vormen waarin de app
    aantoonbaar een klankwet herkent (werkwoorden én 3e-declinatie-naamwoorden). Wordt een keer
    opgebouwd; filteren op 'woorden die jij al kent' en op lesnummer gebeurt in de tab zelf."""
    uit = {}
    gezien = set()
    for ref, zin in (_bijbel_db or {}).items():
        for w in zin:
            info = w.get('parsing_info', '') or ''
            _heeft_apostrof = any(t in str(w.get('grieks', '') or '') for t in _ELISIE_TEKENS)
            if not (_heeft_apostrof or "Werkwoord" in info
                    or any(x in info for x in ("Zelfst.", "Bijv."))):
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


@cache_resource(show_spinner=False)
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


@cache_resource
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


@cache_data(show_spinner=False)
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


@cache_data(show_spinner=False)
def laad_gramtabellen():
    """Paradigma-tabellen uit de slides (grammatica_tabellen.json) — voor de 'toon het rijtje'-hulp."""
    try:
        with open("grammatica_tabellen.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


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


@cache_data(show_spinner=False)
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


@cache_data(show_spinner=False)
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


@cache_resource(show_spinner=False)
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


@cache_resource(show_spinner=False)
def _zoek_vormen(_bijbel_db):
    """(genormaliseerde vorm, weergavevorm-met-accenten, totaal aantal) voor de zoeksuggesties."""
    out = []
    for k, rijen in bijbel_vorm_index(_bijbel_db).items():
        out.append((k, rijen[0][0], sum(r[4] for r in rijen)))
    return out


@cache_resource(show_spinner=False)
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


@cache_resource(show_spinner=False)
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


@cache_data(show_spinner=False)
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


@cache_data(show_spinner=False)
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


@cache_data(show_spinner=False)
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
                _nvk = next((_c for _c in _ONTLEED_KLEUR if _c in p_info), None)
                if _nvk: kleur_stijl += f"color: {_ONTLEED_KLEUR[_nvk]};"
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


def krijg_streak(item, module):
    return int(item.get('streak', 0))


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


LEERPAD_CHUNK = 7      # aantal woorden per level


LEERPAD_DREMPEL = 5    # streak waarop een woord binnen het pad als 'af' telt


LEERPAD_TYP_STREAK = 3 # vanaf deze streak oefen je het woord door te TYPEN; moet < LEERPAD_DREMPEL


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


def _vandaag_str():
    try:
        return str(_nu().date())
    except Exception:
        return ""


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


@cache_data(show_spinner=False)
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


def _kolom_index(idx, totaal):
    """Kolom-major indeling voor paradigma-roosters: eerste helft (ev-rijtje) links, tweede helft
    (mv-rijtje) rechts, elk in standaardvolgorde (Nom, Gen, Dat, Acc). Zo loopt tabben netjes
    Nom ev → Gen ev → Dat ev → Acc ev in de linkerkolom, daarna het mv-rijtje rechts."""
    helft = (int(totaal) + 1) // 2
    return 0 if idx < helft else 1


@cache_data
def laad_actief_beheersen_db():
    if os.path.exists("actief_beheersen.json"):
        with open("actief_beheersen.json", "r", encoding="utf-8") as f: return json.load(f)
    return None


@cache_data
def laad_vocab_db():
    bestand = "basis_woorden_verrijkt.json" if os.path.exists("basis_woorden_verrijkt.json") else "basis_woorden.json"
    if os.path.exists(bestand):
        with open(bestand, "r", encoding="utf-8") as f: return json.load(f)
    return []


@cache_data
def laad_actief_db():
    try:
        with open("actief_beheersen.json", "r", encoding="utf-8") as f: return json.load(f)
    except FileNotFoundError: return None


@cache_data
def laad_stamtijden_db():
    if os.path.exists("stamtijden.json"):
        with open("stamtijden.json", "r", encoding="utf-8") as f: return json.load(f)
    return None


@cache_data(show_spinner=False)
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


@cache_data
def laad_structuurwoorden_db():
    if os.path.exists("structuurwoorden.json"):
        with open("structuurwoorden.json", "r", encoding="utf-8") as f: return json.load(f)
    return None


@cache_data
def laad_verwarparen_db():
    """Laadt de map grieks_woord -> lijst van look-alike twins (op gelijkenis gesorteerd)."""
    if os.path.exists("verwarparen.json"):
        with open("verwarparen.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("twins", {})
    return {}


@cache_data
def laad_grammatica_db():
    if os.path.exists("grammatica_index.json"):
        with open("grammatica_index.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return None


@cache_data
def laad_contractie_db():
    if os.path.exists("contractie_data.json"):
        with open("contractie_data.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return None


GRAMMATICA_PDF = "grammatica_overzicht.pdf"


@cache_resource
def open_grammatica_pdf():
    if FITZ_BESCHIKBAAR and os.path.exists(GRAMMATICA_PDF):
        try:
            return fitz.open(GRAMMATICA_PDF)
        except Exception:
            return None
    return None


@cache_data(show_spinner=False)
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


@cache_resource
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


def _ws_naam(naam):
    """Werkbladnaam (tab) voor één gebruiker. Elke student z'n eigen tab → een opslag van de één
    kan die van een ander nooit overschrijven."""
    schoon = re.sub(r'[^0-9A-Za-z_]', '_', str(naam or ''))
    return ("u_" + schoon)[:95]
