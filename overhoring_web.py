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
from datetime import datetime

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
    veilig = str(fonetisch).replace("'", "\\'").replace('"', '\\"')
    components.html(
        f"""
        <button onclick="_spreek_{key}()" style="
            background:#0e5a8a; color:#fff; border:none; border-radius:6px;
            padding:6px 14px; font-size:15px; cursor:pointer; margin-top:4px;">
            🔊 Uitspraak
        </button>
        <script>
        function _spreek_{key}() {{
            try {{
                var u = new SpeechSynthesisUtterance("{veilig}");
                u.rate = 0.85;   // iets langzamer, duidelijker
                u.pitch = 1.0;
                // kies een neutrale stem; forceer géén Griekse (nieuwgriekse) uitspraak
                var stemmen = window.speechSynthesis.getVoices();
                var voorkeur = stemmen.find(v => /en-|nl-|de-/i.test(v.lang));
                if (voorkeur) u.voice = voorkeur;
                window.speechSynthesis.cancel();
                window.speechSynthesis.speak(u);
            }} catch (e) {{ console.log("TTS niet beschikbaar:", e); }}
        }}
        </script>
        """, height=44
    )

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

def normaliseer_accent(woord):
    if pd.notna(woord) and str(woord).strip() != "":
        w = str(woord).strip().lower()
        w = ''.join(c for c in unicodedata.normalize('NFD', w) if unicodedata.category(c) != 'Mn')
        w = w.replace('a', 'α').replace('e', 'ε').replace('i', 'ι').replace('o', 'ο').replace('u', 'υ')
        w = w.replace('(ν)', '').replace('(ν', '').replace('ν)', '')
        return w.strip()
    return ""

def deconstrueer_stamtijd_live(vorm, tijd_diathese):
    if not vorm or vorm in ["n.v.t.", "---", "-"]: return "", ""
    v_schoon = vorm.strip()
    if tijd_diathese == "Futurum Actief/Medium": uitgangen = ["θήσομαι", "ήσομαι", "σομαι", "οῦμαι", "ομαι", "σω", "ψω", "ξω", "ῶ", "ω"]
    elif tijd_diathese == "Aoristus Actief/Medium": uitgangen = ["σάμην", "άμην", "όμην", "σα", "ψα", "ξα", "ον", "αν", "ην", "α", "ν"]
    elif tijd_diathese == "Aoristus Passief": uitgangen = ["θην", "ην"]
    elif tijd_diathese == "Perfectum Actief": uitgangen = ["κα", "α"]
    elif tijd_diathese == "Perfectum Medium/Passief": uitgangen = ["σμαι", "μμαι", "γμαι", "ημαι", "ειμαι", "ωμαι", "αμαι", "μαι"]
    else: return v_schoon, ""

    for u in uitgangen:
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
        
        for ref, zin in bijbel_db.items():
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
    s = s.replace('“', '"').replace('”', '"').replace("'", '"')
    try: return json.loads(s)
    except: return {}

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
        eind_datum = datetime.now() + pd.Timedelta(days=benodigde_dagen)
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
    
def registreer_oefening(item=None):
    vandaag = str(datetime.now().date())
    if 'dag_stats' not in st.session_state: st.session_state.dag_stats = {}
    st.session_state.dag_stats[vandaag] = st.session_state.dag_stats.get(vandaag, 0) + 1
    if item is not None: item['laatst_geoefend'] = vandaag

def krijg_streak(item, module):
    return int(item.get('streak', 0))

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
    
    vandaag_d = datetime.now().date()

    def dagen_geleden(x):
        d_str = x.get('laatst_geoefend', '')
        if not d_str:
            return 9999  # nooit gedaan telt als 'heel lang geleden'
        try:
            return (vandaag_d - datetime.strptime(d_str, '%Y-%m-%d').date()).days
        except:
            return 9999

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
        return max(0, bonus)

    # Hoogste effectieve 'ouderdom' eerst (oud + worstelend bovenaan, vers + solide onderaan).
    def sorteer_key(x):
        return -(dagen_geleden(x) + struggle_bonus(x))

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
        vandaag = str(datetime.now().date())
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
    """Registreert (in-memory) dat dit woord in de huidige sessie fout ging, met het gegeven antwoord."""
    d = st.session_state.get('sessie_fout')
    if not isinstance(d, dict):
        d = {}
        st.session_state.sessie_fout = d
    d[item.get('grieks', '')] = {"nederlands": str(item.get('nederlands', '')), "antwoord": str(antwoord)}

def _sessie_reset_samenvatting():
    """Leegt de sessie-accumulatoren voor de eindsamenvatting."""
    st.session_state.sessie_goed = {}
    st.session_state.sessie_fout = {}
    st.session_state.sessie_verwar_kandidaten = {}

def verzamel_lookalikes(poule, twins_map):
    """Doel-lijst voor 'Gelijkende woorden': woorden binnen de selectie die een look-alike-twin
    (op spelling) hebben, plus de twin-partners die ook in de selectie zitten."""
    if not twins_map:
        return []
    idx = {w.get('grieks'): w for w in poule if isinstance(w, dict) and w.get('grieks')}
    doel = {}
    for w in poule:
        if not isinstance(w, dict):
            continue
        g = w.get('grieks', '')
        if not g or not twins_map.get(g):
            continue
        doel[g] = w
        for tg in twins_map.get(g, []):
            if tg in idx and tg not in doel:
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

_RANG_TITELS = ["Nieuweling", "Beginner", "Leerling", "Student", "Gevorderde", "Kenner",
                "Exegeet", "Vertaler", "Geleerde", "Meester", "Grootmeester"]

def niveau_van_xp(xp):
    """Zet XP om in een oplopend niveau; de benodigde XP per niveau groeit gestaag (100, 175, 250, ...)."""
    niveau = 0
    nodig = 100
    rest = int(xp)
    while rest >= nodig:
        rest -= nodig
        niveau += 1
        nodig += 75
    titel = _RANG_TITELS[min(niveau // 2, len(_RANG_TITELS) - 1)]
    return {"niveau": niveau, "titel": titel, "xp_totaal": int(xp),
            "xp_in_niveau": rest, "xp_voor_volgend": nodig}

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
        elif s <= 7:
            kaarten.append((w, '2'))   # meerkeuze
        else:
            kaarten.append((w, '4'))   # typen
    return kaarten

# --- DAGELIJKS DOEL ---
DAGDOEL_STANDAARD = {'woorden': 10, 'verwar': 3, 'knelpunt': 5, 'struct': 5, 'stam': 5, 'verzen': 2}

def dagdoel_config():
    cfg = (st.session_state.get('dagdoel') or {}).get('config') or {}
    return {k: int(cfg.get(k, v)) for k, v in DAGDOEL_STANDAARD.items()}

def _vandaag_str():
    try:
        return str(datetime.now().date())
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
    """Opeenvolgende dagen tot vandaag waarop het woord-dagblok is afgerond."""
    log = (st.session_state.get('dagdoel') or {}).get('log', {})
    streak = 0
    try:
        cur = pd.Timestamp(datetime.now().date())
        while log.get(str(cur.date()), {}).get('woordblok'):
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
        elif _s <= 7:
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
        if not vorm or vorm == "-":
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
    """5-weekse heatmap-kalender: kleurintensiteit = hoeveel je die dag oefende, plus gekleurde
    stipjes voor de onderdelen die je die dag deed (woorden/stamtijden/structuur/verzen)."""
    try:
        v = pd.Timestamp(datetime.now().date())
    except Exception:
        return ""
    start = v - pd.Timedelta(days=int(v.weekday()) + 28)  # maandag, 4 weken terug
    onderdelen = [("woordblok", "#33ccff", "woorden"), ("stam", "#b07be0", "stamtijden"),
                  ("struct", "#f6923c", "structuur"), ("verzen", "#3fb27f", "verzen")]
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
            if _val is True or (isinstance(_val, (int, float)) and _val > 0):
                stip += f"<span style='display:inline-block;width:11px;height:11px;border-radius:50%;background:{kl};margin:0 2px'></span>"
        bg = "#1a1d22" if toekomst else _bg(n)
        cellen += (f"<div style='background:{bg};border:{rand};border-radius:8px;height:66px;padding:5px;"
                   f"display:flex;flex-direction:column;align-items:center;justify-content:center;gap:5px;opacity:{'0.35' if toekomst else '1'}'>"
                   f"<div style='font-size:22px;font-weight:800;color:#ffffff;line-height:1;text-align:center'>{ts.day}</div>"
                   f"<div style='text-align:center;min-height:11px'>{stip}</div></div>")
    legenda = " &nbsp; ".join(f"<span style='color:{kl}'>●</span> {naam}" for _sl, kl, naam in onderdelen)
    return (f"<div style='display:grid;grid-template-columns:repeat(7,1fr);gap:4px;margin-bottom:6px'>{kop}</div>"
            f"<div style='display:grid;grid-template-columns:repeat(7,1fr);gap:4px'>{cellen}</div>"
            f"<div style='font-size:11px;color:#9aa3af;margin-top:8px'>{legenda} &nbsp;·&nbsp; fellere groen = meer geoefend</div>")

# --- LEERPAD voor STAMTIJDEN (elk werkwoord = één level) ---
_STAM_TIJDEN = ["Futurum Actief/Medium", "Aoristus Actief/Medium", "Aoristus Passief", "Perfectum Actief", "Perfectum Medium/Passief"]

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
    return [v for v in (w.get('stamtijden', {}).get(t) for t in _STAM_TIJDEN) if v and v != "-"]

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
            if not v or v == "-":
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

def actief_level_status(levels, actief_stats, drempel=16):
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

def markeer_actief_paradigma(cellen):
    """Zet de cellen van een paradigma op 'beheerst' (streak 16) na een foutloos rooster + telt g op."""
    ast = st.session_state.get('actief_stats')
    if not isinstance(ast, dict):
        ast = {}; st.session_state.actief_stats = ast
    for c in cellen:
        cid = c.get('id')
        if not cid:
            continue
        rec = ast.setdefault(cid, {'g': 0, 'f': 0, 'streak': 0})
        rec['g'] = int(rec.get('g', 0)) + 1
        rec['streak'] = max(int(rec.get('streak', 0)), 16)

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

@st.cache_data
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
        df = conn.read(ttl=0) 
        if 'gebruikersnaam' not in df.columns: df['gebruikersnaam'] = ""
        if 'dag_stats' not in df.columns: df['dag_stats'] = "{}"
        
        user_row = df[df['gebruikersnaam'] == naam]
        bestand = "basis_woorden_verrijkt.json" if os.path.exists("basis_woorden_verrijkt.json") else "basis_woorden.json"
        if os.path.exists(bestand):
            with open(bestand, "r", encoding="utf-8") as f: basis = json.load(f)
        else: return None

        if user_row.empty:
            st.session_state.vocab_stats = {}; st.session_state.gram_stats = {}; st.session_state.stam_stats = {}; st.session_state.struct_stats = {}; st.session_state.dag_stats = {}; st.session_state.prod_stats = {}
            st.session_state.verwar_stats = {}; st.session_state.ui_prefs = {}; st.session_state.badges = {}; st.session_state.dagdoel = {}; st.session_state.actief_stats = {}
            df_andere = df[df['gebruikersnaam'] != naam]
            nieuwe_rij = pd.DataFrame([{'gebruikersnaam': naam}])
            conn.update(data=pd.concat([df_andere, nieuwe_rij], ignore_index=True))
        else:
            row = user_row.iloc[0]
            def reassemble_chunks(prefix, count_col):
                if count_col in row and not pd.isna(row[count_col]):
                    try:
                        count = int(row[count_col])
                        s = "".join([str(row[f"{prefix}_{i}"]) for i in range(count) if f"{prefix}_{i}" in row])
                        return veilige_json_load(s)
                    except: return {}
                else: return veilige_json_load(row.get(prefix, '{}'))

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

        for r in basis:
            stats = st.session_state.vocab_stats.get(r['grieks'], {})
            if 'm4' in stats or 'm1' in stats:
                m1 = stats.get('m1', 0); m2 = stats.get('m2', 0); m3 = stats.get('m3', 0); m4 = stats.get('m4', 0)
                r['streak'] = (m1 * 0) + (m2 * 1) + (m3 * 2) + (m4 * 4)
            else: r['streak'] = stats.get('streak', 0)
            
            r['score_goed'] = stats.get('g', 0)
            r['score_fout'] = stats.get('f', 0)
            r['laatst_geoefend'] = stats.get('laatst_geoefend', "")
            if 'lexeem_info' not in r or not r['lexeem_info']: r['lexeem_info'] = r.get('grieks_info', '')
        return basis
    except Exception: return None

def opslaan_naar_cloud():
    if not st.session_state.get('last_user'): return
    try:
        df = conn.read(ttl=10)  # korte cache dempt lees-bursts (quota = 60 leesverzoeken/min)
        if 'gebruikersnaam' not in df.columns: df['gebruikersnaam'] = ""
        if 'dag_stats' not in df.columns: df['dag_stats'] = "{}"
        df_andere = df[df['gebruikersnaam'] != st.session_state.last_user]
        
        def get_chunks(data_dict, prefix, max_len=40000):
            s = json.dumps(data_dict, ensure_ascii=False)
            chunks = [s[i:i+max_len] for i in range(0, len(s), max_len)]
            res = {}
            for idx, chunk in enumerate(chunks): res[f"{prefix}_{idx}"] = chunk
            return res, len(chunks)
        
        v_ch, v_count = get_chunks(st.session_state.get('vocab_stats', {}), 'vocab_stats')
        g_ch, g_count = get_chunks(st.session_state.get('gram_stats', {}), 'gram_stats')
        pr_ch, pr_count = get_chunks(st.session_state.get('prod_stats', {}), 'prod_stats')
        st_ch, st_count = get_chunks(st.session_state.get('stam_stats', {}), 'stam_stats')
        sr_ch, sr_count = get_chunks(st.session_state.get('struct_stats', {}), 'struct_stats')
        d_ch, d_count = get_chunks(st.session_state.get('dag_stats', {}), 'dag_stats')
        vw_ch, vw_count = get_chunks(st.session_state.get('verwar_stats', {}), 'verwar_stats')
        ui_ch, ui_count = get_chunks(st.session_state.get('ui_prefs', {}), 'ui_prefs')
        bd_ch, bd_count = get_chunks(st.session_state.get('badges', {}), 'badges')
        dd_ch, dd_count = get_chunks(st.session_state.get('dagdoel', {}), 'dagdoel')
        af_ch, af_count = get_chunks(st.session_state.get('actief_stats', {}), 'actief_stats')

        nieuwe_rij_dict = {
            'gebruikersnaam': st.session_state.last_user,
            'v_chunks': v_count, 'g_chunks': g_count, 'st_chunks': st_count, 'sr_chunks': sr_count, 'd_chunks': d_count, 'pr_chunks': pr_count,
            'vw_chunks': vw_count, 'ui_chunks': ui_count, 'bd_chunks': bd_count, 'dd_chunks': dd_count, 'af_chunks': af_count
        }
        nieuwe_rij_dict.update(v_ch); nieuwe_rij_dict.update(g_ch); nieuwe_rij_dict.update(st_ch)
        nieuwe_rij_dict.update(sr_ch); nieuwe_rij_dict.update(d_ch); nieuwe_rij_dict.update(pr_ch)
        nieuwe_rij_dict.update(vw_ch); nieuwe_rij_dict.update(ui_ch); nieuwe_rij_dict.update(bd_ch); nieuwe_rij_dict.update(dd_ch); nieuwe_rij_dict.update(af_ch)
        
        nieuwe_rij = pd.DataFrame([nieuwe_rij_dict])
        conn.update(data=pd.concat([df_andere, nieuwe_rij], ignore_index=True))
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
            try: st.toast(f"⚠️ Opslaan lukte niet: {_msg[:80]}", icon="⚠️")
            except Exception: pass

def trigger_save(forceer=False):
    if not st.session_state.get('last_user') or not st.session_state.get('data'): return
    nieuwe_vocab_stats = {}
    for word in st.session_state.data:
        s = int(word.get('streak', 0)); g = int(word.get('score_goed', 0)); f = int(word.get('score_fout', 0)); l = word.get('laatst_geoefend', "")
        if s > 0 or g > 0 or f > 0 or l != "":
            entry = {'streak': s, 'g': g, 'f': f}
            if l: entry['laatst_geoefend'] = l
            nieuwe_vocab_stats[word['grieks']] = entry

    st.session_state.vocab_stats = nieuwe_vocab_stats

    # --- GEBATCHTE CLOUD-OPSLAG ---
    # De in-memory stats hierboven zijn altijd up-to-date (instant). Het trage deel is het
    # wegschrijven naar Google Sheets (read + update = twee netwerkrondjes). Dat doen we niet
    # meer op élk antwoord, maar elke 5 antwoorden — plus altijd geforceerd bij einde/uitloggen.
    st.session_state.save_teller = st.session_state.get('save_teller', 0) + 1
    if forceer or st.session_state.save_teller >= 5:
        st.session_state.save_teller = 0
        opslaan_naar_cloud()

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
        # Weergavevolgorde: eerst het dagblok, dan de oefen-tabbladen in leervolgorde, dan de rest.
        _tabs = st.tabs(["🎯 Dagelijks doel", "🚀 Woordenschat", "🎓 Actief Beheersen", "⏳ Stamtijden", "🧱 Structuurwoorden", "📝 Leesteksten", "📊 Voortgang", "📖 Lijst", "📐 Grammatica", "ℹ️ Uitleg & Hulp", "✍️ NL → Grieks (productie)"])
        menu_dagdoel = _tabs[0]
        # Interne indices (menu[0..9]) blijven exact hetzelfde; alleen de weergavevolgorde verandert.
        menu = [_tabs[1], _tabs[7], _tabs[6], _tabs[2], _tabs[3], _tabs[4], _tabs[5], _tabs[8], _tabs[9], _tabs[10]]

        # Dagblok: automatisch naar het juiste tabblad springen (Streamlit heeft geen eigen tab-switch).
        if st.session_state.get('dagblok_bezig'):
            _dagblok_klaar = (not st.session_state.get('huidig_item') and not st.session_state.get('paar_huidig')
                              and not st.session_state.get('sessie_lijst') and not st.session_state.get('paar_lijst')
                              and not st.session_state.get('dagblok_actief'))
            if _dagblok_klaar:
                st.session_state.dagblok_bezig = False
                st.session_state.dagblok_spring = "Dagelijks doel"
        if st.session_state.get('dagblok_spring'):
            spring_naar_tab(st.session_state.dagblok_spring)
            st.session_state.dagblok_spring = None

        # Eenvoud-modus: standaard alleen de basis-opties; aan te zetten in ℹ️ Uitleg & Hulp.
        _geav = bool(st.session_state.get('ui_geavanceerd',
                     (st.session_state.get('ui_prefs') or {}).get('geavanceerd', False)))
        if not _geav:
            st.info("🧭 Je zit in de **eenvoudige modus** — alleen het belangrijkste is zichtbaar. Zet *‘Geavanceerde opties tonen’* aan in het **ℹ️ Uitleg & Hulp**-tabblad voor alle mogelijkheden.")

       # ==========================================
        # TAB 1: WOORDENSCHAT
        # ==========================================
        with menu[0]: 
            if 'vocab_sessie_verzen' not in st.session_state: st.session_state.vocab_sessie_verzen = {}
            if 'vocab_cluster_strongs' not in st.session_state: st.session_state.vocab_cluster_strongs = {}
            
            col1, col2 = st.columns([1, 2])
            with col1:
                # --- Wens 7: herstel eerder gekozen instellingen als default (uit ui_prefs) ---
                _prefs = st.session_state.get('ui_prefs', {}) or {}

                _modus_opts = ["1. Leer", "2. MC", "3. Mix (MC + Typen)", "4. Typen"]
                if _geav:
                    _modus_idx = _modus_opts.index(_prefs['modus']) if _prefs.get('modus') in _modus_opts else 0
                    modus = st.radio("Modus:", _modus_opts, index=_modus_idx)
                else:
                    modus = "2. MC"  # eenvoudige modus: het Leerpad kiest zelf de oefenvorm

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
                        # Wens 3: woorden binnen de selectie die qua spelling op elkaar lijken (verwarparen.json)
                        doel = verzamel_lookalikes(poule_lessen, laad_verwarparen_db())
                        if not doel:
                            st.caption("ℹ️ Geen look-alikes gevonden in deze lessen. Kies meer/andere lessen.")

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
                    st.markdown(f"#### 🎮 Niveau {_niv['niveau']} · {_niv['titel']}")
                    st.progress(_niv['xp_in_niveau'] / max(1, _niv['xp_voor_volgend']))
                    st.caption(f"⭐ {_niv['xp_totaal']} XP — nog {_niv['xp_voor_volgend'] - _niv['xp_in_niveau']} XP tot niveau {_niv['niveau'] + 1}.")

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

                    # Oude stof meenemen: standaard 1 woord (oudste datum eerst), of af en toe een hele ronde.
                    _lp_opts = {
                        "1 oud woord meenemen (aanrader)": 1,
                        "Kleine herhaalronde (5 oude woorden)": 5,
                        "Grote herhaalronde (10 oude woorden)": 10,
                        "Alleen dit level": 0,
                    }
                    _lp_keuze = st.selectbox("🔁 Oude stof meenemen:", list(_lp_opts.keys()), index=0,
                                             help="Naast de woorden van dit level worden ook je langst-niet-geoefende woorden meegenomen (oudste datum eerst), zodat je oude stof niet vergeet.")
                    lp_herhaal_aantal = _lp_opts[_lp_keuze]

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
                    oefen_stijl = "🤖 Aanbevolen Mix"

                # Wens 7: onthoud de actuele keuzes in-memory; ze worden meegeschreven bij de eerstvolgende
                # cloud-opslag (Start Sessie, einde sessie of uitloggen).
                st.session_state.ui_prefs = {
                    'modus': modus, 'keuze': keuze, 'lessen': gekozen, 'oefen_stijl': oefen_stijl,
                    'optie_context': optie_context, 'optie_cluster_vocab': optie_cluster,
                    'optie_kleur_nv_vocab': optie_kleur_nv, 'optie_nieuw_mee_vocab': optie_nieuw_mee,
                    'optie_verwarparen': optie_verwar, 'optie_mastery_context': optie_mastery_context,
                    'optie_audio': optie_audio,
                    'geavanceerd': _geav,  # niet overschrijven: de eenvoud/geavanceerd-keuze behouden
                }

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
                        # Eindsamenvatting-accumulatoren voor de nieuwe sessie leegmaken
                        _sessie_reset_samenvatting()
                        st.session_state.sessie_net_klaar = False
                        st.session_state._ballonnen_getoond = False

                        # Mijn verwarwoorden → paar-oefening: beide woorden tegelijk, beide antwoorden goed.
                        if keuze == "Mijn verwarwoorden":
                            _paren = bouw_verwar_paren(st.session_state.data, st.session_state.get('verwar_stats', {}))
                            if _paren:
                                r_engine.shuffle(_paren)
                                st.session_state.paar_lijst = _paren
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
                        
                        # Bij knelpunten vriest de instroom van gloednieuwe woorden dicht:
                        mag_geen_nieuw = is_lang_geleden or is_knelpunten or is_puur_typen or (not optie_nieuw_mee)
                        
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
                            if keuze == "🎮 Leerpad (levels)":
                                # Leerpad bepaalt zelf de oefenvorm: flashcard → meerkeuze → typen (oplopend).
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
                            registreer_oefening()
                            if check_betekenis(_ovA or "", wA.get('nederlands', '')) and check_betekenis(_ovB or "", wB.get('nederlands', '')):
                                _lijst = st.session_state.get('paar_lijst', [])
                                _lijst.append((wA, wB))  # komt later nog een keer terug
                                st.session_state.paar_huidig = _lijst.pop(0) if _lijst else None
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
                            _sub = st.form_submit_button("Controleer", type="primary")

                        if _sub:
                            registreer_oefening()
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
                                st.markdown("<div style='font-size:14px; margin-bottom:4px;'>**(Legenda: <span style='color:#33ccff'>Nom</span> | <span style='color:#28a745'>Gen</span> | <span style='color:#6f42c1'>Dat</span> | <span style='color:#dc3545'>Acc</span> | <span style='color:#fd7e14'>Voc</span>)**</div>", unsafe_allow_html=True)
                            st.markdown(f"<div class='grieks-woord' style='font-size: 42px; padding: 10px; margin-top: -10px;'>{huidige_vorm}</div>", unsafe_allow_html=True)
                        else: st.markdown(f"<div class='grieks-woord'>{huidige_vorm}</div>", unsafe_allow_html=True)
                    else: st.markdown(f"<div class='grieks-woord'>{huidige_vorm}</div>", unsafe_allow_html=True)

                    if st.session_state.get('optie_audio', True):
                        audio_knop(item.get('fonetisch', ''), key="vocab")

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
                        if st.button("Volgende"): laad_volgend_woord(); st.rerun()

                    elif huidige_sub_modus in ['4', '3_typ']:
                        if st.session_state.fouten_huidig_woord >= 1: 
                            st.info(actuele_hint)
                        forceer_focus()
                        with st.form(key=f"form_vocab_{item.get('grieks')}", clear_on_submit=True):
                            inp = st.text_input("Vertaling:").lower().strip()
                            vorm_getoetst = is_mastery and heeft_vormen
                            if vorm_getoetst:
                                _vc1, _vc2, _vc3 = st.columns(3)
                                _nv = _vc1.selectbox("Naamval", [""] + NAAMVAL_OPTIES, key=f"mvorm_nv_{item.get('grieks')}")
                                _gt = _vc2.selectbox("Getal", [""] + GETAL_OPTIES, key=f"mvorm_gt_{item.get('grieks')}")
                                _gs = _vc3.selectbox("Geslacht", [""] + GESLACHT_OPTIES, key=f"mvorm_gs_{item.get('grieks')}")
                                p_vorm = f"{_nv} {_gt} {_gs}".lower().strip()
                            else:
                                p_vorm = huidige_parsing.lower().strip()

                            if st.form_submit_button("Check Antwoord"):
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
                                    vier_fase_overgang(_oude_streak, int(item.get('streak', 0)), item.get('grieks', ''))
                                    if st.session_state.fouten_huidig_woord == 0:
                                        verzwak_verwarring(item.get('grieks', ''))
                                    _sessie_noteer_goed(item)

                                    success_msg = f"✓ Goed! **{huidige_vorm}** = {correct_antw}"
                                    if item['grieks'] in st.session_state.gestrafte_woorden_vocab: success_msg += " *(Geen streak-punten wegens eerdere fout)*"
                                    elif zin_data: success_msg += f"\n\n📖 **{zin_data['ref']}**: {zin_data['grieks_puur']}\n\n🇬🇧 *{zin_data['engels_puur']}*"
                                    
                                    st.session_state.feedback = {"type": "success", "msg": success_msg}
                                    trigger_save(); laad_volgend_woord(); st.rerun()
                                    
                                elif vertaling_correct and not vorm_correct:
                                    # Genuanceerde opvang: vertaling wél snappen, grammaticale duiding afwijken
                                    st.session_state.fouten_huidig_woord += 1
                                    item['score_fout'] = int(item.get('score_fout', 0)) + 1
                                    st.session_state.feedback = {
                                        "type": "warning", 
                                        "msg": f"Inhoudelijk juist (**{inp}**)! Je grammaticale ontleding (*{p_vorm if p_vorm else 'leeg'}*) afweek echter van de officiële duiding: **{huidige_parsing}**."
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

                            st.session_state.huidige_opties = [correct_optie] + afleiders[:3]
                            rnd.shuffle(st.session_state.huidige_opties)
                        
                        cols = st.columns(2)
                        for idx, optie in enumerate(st.session_state.huidige_opties):
                            if cols[idx % 2].button(optie, key=f"btn_{idx}_{item.get('grieks')}"):
                                registreer_oefening(item)
                                if optie == correct_optie:
                                    _oude_streak_mc = int(item.get('streak', 0))
                                    if st.session_state.fouten_huidig_woord == 0 and item['grieks'] not in st.session_state.gestrafte_woorden_vocab:
                                        item['score_goed'] = int(item.get('score_goed', 0)) + 1
                                        if huidige_sub_modus == '2': item['streak'] = int(item.get('streak', 0)) + 1
                                        elif huidige_sub_modus == '3_mc': st.session_state.mix_combo[item['grieks']] = True
                                    vier_fase_overgang(_oude_streak_mc, int(item.get('streak', 0)), item.get('grieks', ''))
                                    if st.session_state.fouten_huidig_woord == 0:
                                        verzwak_verwarring(item.get('grieks', ''))
                                    _sessie_noteer_goed(item)

                                    success_msg = f"✓ Juist! {fout_msg_volledig}"
                                    if item['grieks'] in st.session_state.gestrafte_woorden_vocab: success_msg += " *(Geen streak-punten wegens eerdere fout)*"
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

                                    if huidige_streak >= 16 or st.session_state.fouten_huidig_woord >= 2:
                                        item['streak'] = max(0, huidige_streak - 2); st.session_state.gestrafte_woorden_vocab.add(item['grieks'])
                                        st.session_state.sessie_lijst.insert(0, (item, 'overtik')); st.session_state.sessie_lijst.append((item, huidige_sub_modus))
                                        st.session_state.feedback = {"type": "error", "msg": f"✗ Fout. Je koos '{optie}'. Het was: {fout_msg_volledig}{_verwar_note}"}
                                        trigger_save(); laad_volgend_woord()
                                    else:
                                        item['score_fout'] = int(item.get('score_fout', 0)) + 1
                                        st.session_state.feedback = {"type": "warning", "msg": f"Onjuist. Bekijk de hint!{_verwar_note}"}
                                    st.rerun()

                    if huidige_sub_modus != 'overtik':
                        st.write("---")
                        fase = 'Nieuw' if int(item.get('streak', 0))==0 else ('In Training' if int(item.get('streak', 0))<=15 else ('Beheerst' if int(item.get('streak', 0))<=29 else 'Mastery'))
                        st.caption(f"Fase: {fase} | Streak: {item.get('streak', 0)} | Goed/Fout: {item.get('score_goed', 0)}/{item.get('score_fout', 0)} | Laatst: {item.get('laatst_geoefend', 'Nooit')}")

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
                        with st.form("verwar_bevestig_form"):
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
                            stam_lijst.append({"Les": w.get('les', 0), "Praesens": w['praesens'], "Tijd/Diathese": t_d, "Vorm": vorm, "Betekenis": w['betekenis'], "Streak": s['streak'], "Goed": s['g'], "Fout": s['f']})
                    st.dataframe(pd.DataFrame(stam_lijst), width='stretch')
            elif weergave == "Structuurwoorden":
                struct_db = laad_structuurwoorden_db()
                if struct_db:
                    str_lijst = []
                    for w in struct_db:
                        s = st.session_state.struct_stats.get(w['grieks'], {'g': 0, 'f': 0, 'streak': 0})
                        str_lijst.append({"Woord": w['grieks'], "Categorie": w['categorie'], "Eigenschap": w['eigenschap'], "Betekenis": w['betekenis'], "Streak": s['streak'], "Goed": s['g'], "Fout": s['f']})
                    st.dataframe(pd.DataFrame(str_lijst), width='stretch')
        
        # ==========================================
        # TAB 3: VOORTGANG & DASHBOARD
        # ==========================================
        with menu[2]: 
            st.subheader("📊 Academische Cockpit & Dashboard")
            
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

            # --- STATISTIEKEN BEREKENEN ---
            stats_vocab = {'Nieuw': 0, 'In Training': 0, 'Beheerst': 0, 'Mastery': 0}
            tot_goed_v, tot_fout_v = 0, 0
            vocab_streaks = {} 
            bekende_freq = 0
            totale_freq = 0

            if st.session_state.data:
                for w in st.session_state.data:
                    grieks_woord = w.get('grieks', '')
                    strk = int(w.get('streak', 0))
                    vocab_streaks[grieks_woord] = strk
                    
                    freq = int(w.get('frequentie', w.get('frequentie_nt', 1)))
                    totale_freq += freq
                    
                    tot_goed_v += int(w.get('score_goed', 0)); tot_fout_v += int(w.get('score_fout', 0))
                    if strk >= 30: stats_vocab['Mastery'] += 1; bekende_freq += freq
                    elif strk >= 16: stats_vocab['Beheerst'] += 1; bekende_freq += freq
                    elif strk >= 1: stats_vocab['In Training'] += 1
                    else: stats_vocab['Nieuw'] += 1

            stats_stam = {'Nieuw': 0, 'In Training': 0, 'Beheerst': 0, 'Mastery': 0}
            tot_goed_s, tot_fout_s = 0, 0
            if stamtijden_db:
                for w in stamtijden_db:
                    for t_d, vorm in w.get('stamtijden', {}).items():
                        s = st.session_state.stam_stats.get(f"{w['praesens']}_{vorm}", {'g': 0, 'f': 0, 'streak': 0})
                        tot_goed_s += s.get('g', 0); tot_fout_s += s.get('f', 0)
                        strk_s = s.get('streak', 0)
                        if strk_s >= 30: stats_stam['Mastery'] += 1
                        elif strk_s >= 16: stats_stam['Beheerst'] += 1
                        elif strk_s >= 1: stats_stam['In Training'] += 1
                        else: stats_stam['Nieuw'] += 1

            stats_str = {'Nieuw': 0, 'In Training': 0, 'Beheerst': 0, 'Mastery': 0}
            tot_goed_st, tot_fout_st = 0, 0
            if str_db:
                for w in str_db:
                    s = st.session_state.struct_stats.get(w['grieks'], {'g': 0, 'f': 0, 'streak': 0})
                    tot_goed_st += s.get('g', 0); tot_fout_st += s.get('f', 0)
                    strk_st = s.get('streak', 0)
                    if strk_st >= 30: stats_str['Mastery'] += 1
                    elif strk_st >= 16: stats_str['Beheerst'] += 1
                    elif strk_st >= 1: stats_str['In Training'] += 1
                    else: stats_str['Nieuw'] += 1

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
                _cur = pd.Timestamp(datetime.now().date())
                while str(_cur.date()) in _dagen_set:
                    _dagstreak += 1
                    _cur -= pd.Timedelta(days=1)
            except Exception:
                _dagstreak = 0

            _beh_tot = (stats_vocab['Beheerst'] + stats_vocab['Mastery']
                        + stats_stam['Beheerst'] + stats_stam['Mastery']
                        + stats_str['Beheerst'] + stats_str['Mastery'])
            _mast_tot = stats_vocab['Mastery'] + stats_stam['Mastery'] + stats_str['Mastery']
            _niv_info = niveau_van_xp(bereken_xp(st.session_state.data))
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
                _vandaag = str(datetime.now().date())
            except Exception:
                _vandaag = ""
            for _bid in _nieuw:
                st.session_state.badges[_bid] = _vandaag

            # Altijd zichtbaar (motiverend), rest achter een dropdown:
            st.markdown(f"**🏅 Badges: {len(_behaald_nu)}/{len(_badges)} behaald**  ·  🎮 Niveau {_niv_info['niveau']} — {_niv_info['titel']} ({_niv_info['xp_totaal']} XP)")
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

            st.write("---")

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
                return sum(1 for w in lijst if vocab_streaks.get(w.get('grieks', w.get('praesens', '')), 0) >= 16)

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
            st.markdown("### 🧭 De Morfologische Horizon (Interactieve Studieplanner)")
            st.caption("Analyseer de wiskundige verhouding tussen doelniveau, dagelijks oefenritme en persoonlijke focus om een haalbare planning te maken.")

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

                st.write("**2. Bepaal je parameters:**")
                sim_doel_streak = st.slider("Gewenste Kennis-diepte (Streak):", min_value=2, max_value=30, value=16, help="16 = Beheerst (Standaard PThU norm). 8 = Voldoende om passief te herkennen in een tekst. 30 = Vloeiende Mastery.")
                sim_dag_vocab = st.slider("Woorden oefenen per dag:", min_value=5, max_value=100, value=30, step=5)
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
                                <span style="font-size: 12px; color: #aaa;">Totale Streak-schuld</span>
                            </div>
                            <div>
                                <span style="font-size: 20px; font-weight: bold; color: #f6c23e;">~{prognose['netto_winst']} pt</span><br>
                                <span style="font-size: 12px; color: #aaa;">Netto winst / oefening</span>
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
                            advies_box += f"2. **Hefboom op Focus:** Als je je accuratesse van {sim_acc_override}% naar **{sim_acc_override + 5}%** weet te tillen (bijvoorbeeld door bij twijfel de hint te openen in plaats van te gokken), bespaar je **{dagen_bespaard} dagen** doorlooptijd."
                            
                    st.info(advies_box)

            st.write("---")

            # --- DE STAMTIJDEN SLUIS ---
            st.markdown("### ⏳ De Stamtijden-Sluis")
            tot_stam_ww = len(stamtijden_db) if stamtijden_db else 0
            ontgrendeld_stam_ww = sum(1 for w in stamtijden_db if vocab_streaks.get(w['praesens'], 0) >= 5) if stamtijden_db else 0

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

            vandaag_str = str(datetime.now().date())
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

            # --- COMPETITIE DASHBOARD ---
            st.subheader("🏆 Competitie Dashboard (Laatste 14 dagen)")
            try:
                # 5 min cachen: dit tabblad rendert bij ELKE rerun, dus ttl=0 vrat het lees-quotum op.
                df_global = conn.read(ttl=300)
                if 'gebruikersnaam' in df_global.columns and 'dag_stats' in df_global.columns:
                    comp_data = []
                    start_compare = datetime.now().date() - pd.Timedelta(days=13)
                    
                    for idx, row in df_global.iterrows():
                        g_naam = row.get('gebruikersnaam', 'Anoniem').split('_')[0] 
                        if not g_naam: continue
                        try:
                            if 'd_chunks' in row and not pd.isna(row['d_chunks']):
                                count = int(row['d_chunks'])
                                s = "".join([str(row[f"dag_stats_{i}"]) for i in range(count) if f"dag_stats_{i}" in row])
                                d_stats_raw = veilige_json_load(s)
                            else:
                                d_stats_raw = veilige_json_load(str(row.get('dag_stats', '{}')))
                        except: d_stats_raw = {}
                        
                        tot_14 = 0
                        for d_str, aantal in d_stats_raw.items():
                            try:
                                d_dt = datetime.strptime(d_str, '%Y-%m-%d').date()
                                if start_compare <= d_dt <= datetime.now().date(): tot_14 += int(aantal)
                            except: pass
                        if tot_14 > 0: comp_data.append({"Gebruiker": g_naam, "Geoefende Items": tot_14})
                    
                    if comp_data:
                        df_comp = pd.DataFrame(comp_data).groupby('Gebruiker').sum().reset_index()
                        df_comp = df_comp.sort_values(by="Geoefende Items", ascending=False).reset_index(drop=True)
                        df_comp.index += 1
                        
                        eigen_naam = st.session_state.last_user.split('_')[0]
                        andere_gebruikers = df_comp[df_comp['Gebruiker'] != eigen_naam]
                        hoogste_score = df_comp['Geoefende Items'].max() if not df_comp.empty else 0
                        gemiddelde_anderen = int(andere_gebruikers['Geoefende Items'].mean()) if not andere_gebruikers.empty else 0
                        
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Hoogste score in groep", hoogste_score)
                        c2.metric("Gemiddelde van de rest", gemiddelde_anderen)
                        
                        user_rank = df_comp[df_comp['Gebruiker'] == eigen_naam].index
                        if len(user_rank) > 0: c3.metric("Jouw Positie", f"#{user_rank[0]} van de {len(df_comp)}")
                        
                        st.dataframe(df_comp, width='stretch')
            except Exception:
                st.caption("Kon de competitiegegevens momenteel niet synchroniseren.")
            
            st.write("---")

            # --- AARTSRIVALEN TOP 5 (Nemesis Tracker) ---
            st.subheader("⚔️ Jouw Aartsrivalen (Top 5 Nemesissen)")
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
                for w in str_db:
                    s = st.session_state.struct_stats.get(w['grieks'], {'g': 0, 'f': 0, 'streak': 0})
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

            # --- EXPORTEREN ---
            st.subheader("💾 Exporteer je data")
            df_export = pd.DataFrame(st.session_state.data)[['grieks', 'nederlands', 'streak', 'score_goed', 'score_fout', 'laatst_geoefend']]
            csv = df_export.to_csv(index=False).encode('utf-8')
            st.download_button(label="📥 Download Data als CSV", data=csv, file_name="mijn_grieks_voortgang.csv", mime="text/csv")
            
        # ==========================================
        # TAB 4: ACTIEF BEHEERSEN (PARADIGMA'S)
        # ==========================================
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
                actief_modus = st.radio("Kies je leervorm:", _af_modi, horizontal=True)
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
                        with cols[idx % 2]:
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
                            with cols[idx % 2]:
                                st.markdown(f"**{item['label']}**")
                                c_stam, c_in = st.columns([1, 2])
                                c_stam.markdown(f"<div style='font-size:22px; text-align:right; padding-top:4px;'>{stam} + </div>", unsafe_allow_html=True)
                                inputs[item["id"]] = c_in.text_input("Uitgang", key=f"foc_{item['id']}", label_visibility="collapsed")
                        
                        st.write("")
                        if st.form_submit_button("Nakijken", type="primary"):
                            score = 0; fouten = []
                            for item in huidig_paradigma:
                                verwacht = normaliseer_accent(item.get("uitgang", ""))
                                ingevuld = normaliseer_accent(naar_grieks_transliteratie(inputs[item["id"]]))
                                stam = item.get("stam", "")
                                
                                if verwacht == ingevuld or (verwacht == "" and ingevuld == ""): score += 1
                                else: fouten.append(f"**{item['label']}:** Verwacht: `{stam}` + `{item.get('uitgang', '')}`, jij typte: `{stam}` + `{ingevuld}`")
                            
                            if score == len(huidig_paradigma):
                                st.success(f"🎉 Perfect! Je hebt alle {score} uitgangen correct!"); st.balloons()
                            else:
                                st.error(f"Je had er {score} van de {len(huidig_paradigma)} goed. Kijk naar je fouten:")
                                for f in fouten: st.write("-", f)

                elif "2." in actief_modus:
                    st.markdown(f"### {gekozen_sub} (Tentamen)")
                    st.write("Typ de volledige vormen. Goede antwoorden worden vastgezet, foute velden worden leeggemaakt voor een nieuwe poging.")
                    
                    if "tent_state" not in st.session_state: st.session_state.tent_state = {}
                    if st.session_state.get("tent_para") != gekozen_sub:
                        st.session_state.tent_state = {item["id"]: {"correct": False, "value": ""} for item in huidig_paradigma}
                        st.session_state.tent_para = gekozen_sub

                    cols = st.columns(2)
                    huidige_inputs = {}
                    
                    for idx, item in enumerate(huidig_paradigma):
                        with cols[idx % 2]:
                            i_id = item["id"]
                            state = st.session_state.tent_state.get(i_id, {"correct": False, "value": ""})
                            if state["correct"]: st.success(f"**{item['label']}:** {item['vorm']}")
                            else: huidige_inputs[i_id] = st.text_input(f"**{item['label']}**", value=state["value"], key=f"tent_{i_id}")

                    st.write("")
                    if not all(s["correct"] for s in st.session_state.tent_state.values()):
                        if st.button("Nakijken", type="primary"):
                            for item in huidig_paradigma:
                                i_id = item["id"]
                                if not st.session_state.tent_state[i_id]["correct"]:
                                    ingevuld = normaliseer_accent(naar_grieks_transliteratie(huidige_inputs.get(i_id, "")))
                                    verwacht = normaliseer_accent(item["vorm"])
                                    if ingevuld == verwacht:
                                        st.session_state.tent_state[i_id]["correct"] = True; st.session_state.tent_state[i_id]["value"] = item["vorm"]
                                    else: st.session_state.tent_state[i_id]["value"] = "" 
                            st.rerun()
                    else:
                        st.success("🏆 Geweldig! Je hebt het volledige paradigma foutloos gereproduceerd!")
                        if st.button("Reset Rooster"):
                            st.session_state.tent_state = {item["id"]: {"correct": False, "value": ""} for item in huidig_paradigma}; st.rerun()

                elif "3." in actief_modus:
                    st.markdown(f"### ⚡ Flashcards ({gekozen_sub})")
                    st.write("Overhoor willekeurige losse vormen uit dit paradigma om je snelheid te trainen.")
                    
                    # --- DE DADER IS HIER WEGGESNEDEN (import random is foetsie!) ---
                    if "flash_huidig" not in st.session_state or st.session_state.get("flash_para_id") != gekozen_sub:
                        st.session_state.flash_para_id = gekozen_sub
                        st.session_state.flash_huidig = r_engine.choice(huidig_paradigma)
                    
                    huidig_fc = st.session_state.flash_huidig
                    st.info(f"Vertaal naar het Grieks: **{gekozen_cat} - {huidig_fc['label']}**")
                    
                    with st.form("fc_form", clear_on_submit=True):
                        fc_in = st.text_input("Griekse vorm:")
                        if st.form_submit_button("Controleer"):
                            verwacht = normaliseer_accent(huidig_fc["vorm"])
                            ingevuld = normaliseer_accent(naar_grieks_transliteratie(fc_in))
                            if verwacht == ingevuld:
                                st.success(f"✓ Goed! Het was inderdaad **{huidig_fc['vorm']}**.")
                                st.session_state.flash_huidig = r_engine.choice(huidig_paradigma)
                            else:
                                stam = huidig_fc.get("stam", ""); uitgang = huidig_fc.get("uitgang", ""); toelichting = huidig_fc.get("toelichting", "")
                                st.error(f"✗ Fout. Verwacht: **{huidig_fc['vorm']}** (Stam: `{stam}` + Uitgang: `{uitgang}`).\n\n*Tip: {toelichting}*")

                elif "Leerpad" in actief_modus:
                    # === LEERPAD: elke cel individueel leren (flashcard → meerkeuze → typen), en pas
                    # het HELE rijtje ('grote cel') zodra alle cellen streak 20+ hebben. ===
                    _af_levels = actief_level_status(bouw_actief_levels(actief_db), st.session_state.actief_stats)
                    _af_niv = niveau_van_xp(bereken_xp_actief(st.session_state.actief_stats))
                    _af_vol = sum(1 for l in _af_levels if l['voltooid'])
                    st.markdown(f"#### 🎮 Niveau {_af_niv['niveau']} · {_af_niv['titel']} — {_af_niv['xp_totaal']} XP")
                    st.progress(_af_niv['xp_in_niveau'] / max(1, _af_niv['xp_voor_volgend']))
                    _af_aanbev = next((l for l in _af_levels if l['ontgrendeld'] and not l['voltooid']), None)
                    st.caption(f"🏁 {_af_vol}/{len(_af_levels)} paradigma's beheerst" + (f" · aanbevolen: **{_af_aanbev['titel']}**" if _af_aanbev else "") + ". Kies hierboven een paradigma.")

                    cells = [c for c in huidig_paradigma if c.get('id')]
                    def _cstreak(_c): return int((st.session_state.actief_stats.get(_c['id']) or {}).get('streak', 0))
                    _klaar20 = sum(1 for c in cells if _cstreak(c) >= 20)
                    st.markdown(f"### {gekozen_sub}  ({_klaar20}/{len(cells)} cellen op streak 20+)")

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

                    if cells and all(_cstreak(c) >= 20 for c in cells):
                        # MEESTERPROEF: het hele rijtje in één keer reproduceren.
                        st.success("💪 Alle cellen op streak 20+ — meesterproef: reproduceer het hele rijtje.")
                        if st.session_state.get('actief_lp_key') != _pkey:
                            st.session_state.actief_lp_state = {c['id']: {"correct": False, "value": ""} for c in cells}
                            st.session_state.actief_lp_key = _pkey
                        _cols = st.columns(2); _inp = {}
                        for _i, c in enumerate(cells):
                            with _cols[_i % 2]:
                                _s = st.session_state.actief_lp_state.get(c['id'], {"correct": False, "value": ""})
                                if _s["correct"]: st.success(f"**{c['label']}:** {c['vorm']}")
                                else: _inp[c['id']] = st.text_input(f"**{c['label']}**", value=_s["value"], key=f"lpm_{c['id']}")
                        if not all(s["correct"] for s in st.session_state.actief_lp_state.values()):
                            if st.button("Nakijken", type="primary", key="lpm_nakijk"):
                                for c in cells:
                                    if not st.session_state.actief_lp_state[c['id']]["correct"]:
                                        if normaliseer_accent(naar_grieks_transliteratie(_inp.get(c['id'], ""))) == normaliseer_accent(c['vorm']):
                                            st.session_state.actief_lp_state[c['id']] = {"correct": True, "value": c['vorm']}
                                        else: st.session_state.actief_lp_state[c['id']]["value"] = ""
                                st.rerun()
                        else:
                            st.success("🏆 Volledig foutloos — dit paradigma zit écht vast!")
                            st.balloons()
                            if st.button("🔄 Opnieuw", key="lpm_reset"):
                                st.session_state.actief_lp_state = {c['id']: {"correct": False, "value": ""} for c in cells}; st.rerun()
                    else:
                        # PER-CEL SCAFFOLD: bouw een rij kaarten op basis van de streak per cel.
                        def _bouw_q():
                            _q = []
                            for c in cells:
                                s = _cstreak(c)
                                if s >= 20: continue
                                if s <= 0: _q.append((c['id'], 'Leer')); _q.append((c['id'], 'MC'))
                                elif s <= 9: _q.append((c['id'], 'MC'))
                                else: _q.append((c['id'], 'Typen'))
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
                            cell = next((c for c in cells if c['id'] == cid), cells[0])
                            _slabel = {'Leer': '🧠 Leer', 'MC': '🔢 Meerkeuze', 'Typen': '⌨️ Typen'}.get(sub, sub)
                            st.caption(f"{_slabel} · streak {_cstreak(cell)} · nog {len(_q)} kaart(en) in de rij")
                            st.markdown(f"<div class='grieks-woord' style='font-size:30px'>{cell['label']}</div>", unsafe_allow_html=True)

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
                                    _pool = list({c['vorm'] for c in cells if c['vorm'] != cell['vorm']})
                                    r_engine.shuffle(_pool)
                                    _opts = [cell['vorm']] + _pool[:3]
                                    r_engine.shuffle(_opts)
                                    st.session_state.af_opties = _opts
                                _mcols = st.columns(2)
                                for _oi, _opt in enumerate(st.session_state.af_opties):
                                    if _mcols[_oi % 2].button(_opt, key=f"afm_{cid}_{_oi}"):
                                        if _opt == cell['vorm']:
                                            _af_score(cid, 2, True); st.session_state.af_feedback = {"type": "success", "msg": f"✓ Goed! {cell['label']} = {cell['vorm']}"}; _volgende()
                                        else:
                                            _af_score(cid, -2, False); st.session_state.af_feedback = {"type": "error", "msg": f"✗ {cell['label']} = **{cell['vorm']}** (jij koos {_opt})"}; _volgende(requeue=True)
                                        trigger_save(); st.rerun()
                            else:  # Typen
                                forceer_focus()
                                with st.form(f"aft_{cid}", clear_on_submit=True):
                                    _in = st.text_input("Typ de vorm (Latijnse toetsen mag):")
                                    if st.form_submit_button("Controleer", type="primary"):
                                        if normaliseer_accent(naar_grieks_transliteratie(_in)) == normaliseer_accent(cell['vorm']):
                                            _af_score(cid, 4, True); st.session_state.af_feedback = {"type": "success", "msg": f"✓ Goed! {cell['label']} = {cell['vorm']}"}; _volgende()
                                        else:
                                            _af_score(cid, -2, False); st.session_state.af_feedback = {"type": "error", "msg": f"✗ {cell['label']} = **{cell['vorm']}**"}; _volgende(requeue=True)
                                        trigger_save(); st.rerun()

                    with st.expander("🗺️ Alle paradigma-levels"):
                        for l in _af_levels:
                            _ico = "✅" if l['voltooid'] else ("▶️" if l['ontgrendeld'] else "🔒")
                            st.markdown(f"{_ico} **{l['index']}.** {l['titel']} — {l['klaar']}/{l['totaal']}")

        # ==========================================
        # TAB 5: STAMTIJDEN
        # ==========================================
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
                _stam_modi = (["🎮 Leerpad (levels)", "📖 Werkwoordpaspoort", "🧠 Leer (flashcards)", "🔢 MC", "🔀 Mix (MC + Typen)", "⌨️ Typen", "🔎 Herkennen (koud)"]
                              if _geav else ["🎮 Leerpad (levels)", "🧠 Leer (flashcards)"])
                stam_modus = st.radio("Modus:", _stam_modi, horizontal=True)
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
                                        dstam, duit = deconstrueer_stamtijd_live(svorm, t_diathese)
                                        gekleurd_html = f"{dstam}<span style='color:#33ccff'>{duit}</span>" if duit else svorm
                                    else: gekleurd_html = "-"
                                    st.markdown(f"<div style='font-size:22px; font-weight:bold; color:#fff; background-color:#222; padding:10px; border-radius:6px; text-align:center; margin-bottom:15px;'>{gekleurd_html}</div>", unsafe_allow_html=True)
                            
                            st.markdown("#### ⚙️ De Klankwet achter dit raamwerk")
                            if morf.get('memoriseren_vereist'): st.error(f"**Suppletie-werkwoord:** {regel.get('toelichting', 'Puur memoriseren.')}")
                            else: st.success(f"**Formule:** `{regel.get('formule', 'Stam + σ')}`\n\n**Uitleg:** {regel.get('toelichting', '')}")

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
                            return {"basis": w, "tijd": tijd, "vorm": vorm} if vorm and vorm != "-" else None

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
                                        _ds, _du = deconstrueer_stamtijd_live(_v, _td)
                                        _hh = f"{_ds}<span style='color:#33ccff'>{_du}</span>" if _du else _v
                                    else:
                                        _hh = "-"
                                    st.markdown(f"<div style='font-size:20px;font-weight:bold;color:#fff;background:#222;padding:8px;border-radius:6px;text-align:center;margin-bottom:12px;'>{_hh}</div>", unsafe_allow_html=True)
                            if _morf.get("memoriseren_vereist"):
                                st.warning(f"🔥 **Onregelmatig (suppletie):** {_regel.get('toelichting', 'Puur memoriseren.')}")
                            else:
                                st.info(f"💡 **Klankwet ({_morf.get('klasse', 'regelmatig')}):** {_regel.get('formule', '')} — {_regel.get('toelichting', '')}")
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
                                    dstam, duit = deconstrueer_stamtijd_live(h["vorm"], h["tijd"])
                                    _vh = f"**{dstam}**:blue[**{duit}**]" if duit else f"**{h['vorm']}**"
                                    st.success(f"{_vh}\n\n**{h['tijd']}** van **{basis['praesens']}** — *{basis['betekenis']}*")
                                if morf.get("memoriseren_vereist"):
                                    st.warning(f"🔥 **Onregelmatig (suppletie):** {regel.get('toelichting', 'Puur memoriseren.')}")
                                else:
                                    st.info(f"💡 **Klankwet ({morf.get('klasse', 'regelmatig')}):** {regel.get('formule', '')} — {regel.get('toelichting', '')}")

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
                                if vorm and vorm != "-":
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
                                    if st.form_submit_button("Controleer", type="primary"):
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
                                    if st.form_submit_button("Controleer", type="primary"):
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
                            oefen_stijl = st.radio("Sessie opbouw:", ["🤖 Automatische Gated Mix", "🎛️ Zelf Fasen Samenstellen"], horizontal=True)
                            stam_negeer_gate = st.checkbox(
                                "🔓 Negeer vergrendeling (oefen ook stamtijden waarvan het basiswoord nog niet op streak 5 staat)",
                                key="stam_negeer_gate",
                                help="Normaal ontgrendel je de stamtijden van een werkwoord pas als je het basiswoord al kent (vocab-streak ≥ 5), en elke volgende tijd als de vorige zit. Zet dit aan om meteen met alle stamtijden te oefenen."
                            )
                        else:
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
                                p_streak = st.session_state.vocab_stats.get(w['praesens'], {}).get('streak', 0)
                                if not gate_uit and p_streak < 5: continue

                                vorige_streak = 999 if gate_uit else p_streak
                                for t_d in tijden_volgorde:
                                    if not (vorm := w.get('stamtijden', {}).get(t_d)): continue
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
                                m_id = "2" if "Mix" in stam_modus else ("3" if "Typen" in stam_modus else "1")
                                if is_stam_leerpad:
                                    # Leerpad: oplopend — nieuwe vorm eerst als flashcard (Leer), dan
                                    # meerkeuze zolang de streak laag is, en pas daarna typen.
                                    _stam_kaarten = []
                                    for v in sampled:
                                        _s = int(v.get('streak', 0))
                                        if _s <= 0:
                                            _stam_kaarten.append((v, "Leer")); _stam_kaarten.append((v, "MC"))
                                        elif _s <= 7:
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
                            
                            dstam, duit = deconstrueer_stamtijd_live(huidig['vraag_vorm']['vorm'], correct_gram)
                            
                            # OPLOSSING 1: Native Streamlit markdown-kleurcode :blue[...] in plaats van HTML
                            gekleurde_vorm_html = f"**{dstam}**:blue[**{duit}**]" if duit else f"**{huidig['vraag_vorm']['vorm']}**"
                            fout_msg = f"{gekleurde_vorm_html} — {correct_gram} van **{correct_praesens}** — **{correct_betekenis}**"
                            
                            # OPLOSSING 2: Voorkomen dat 'Suppletie' dubbel wordt geprint
                            morf = huidig['basis'].get('morfologie', {}); regel = morf.get('mutatieregel', {})
                            toelichting_txt = regel.get('toelichting', 'Puur memoriseren.')
                            prefix_sup = "⚠️ " if toelichting_txt.startswith("Suppletie") else "⚠️ **Suppletie:** "
                            uitleg_regel = f"{prefix_sup}{toelichting_txt}" if morf.get('memoriseren_vereist') else f"💡 **Klankwet ({morf.get('klasse', 'regelmatig')}):** {regel.get('formule','')} — *{regel.get('toelichting','')}*"
                            
                            huidige_streak = huidig.get('streak', 0)
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
                                p_gram = st.selectbox("1. Grammatica:", ["", "Futurum Actief/Medium", "Aoristus Actief/Medium", "Aoristus Passief", "Perfectum Actief", "Perfectum Medium/Passief"])
                                p_prae = st.text_input("2. Praesens bronwoord:", key="in_ov_p")
                                if st.button("Bevestig Overtikken"):
                                    registreer_oefening()
                                    if p_gram == correct_gram and normaliseer_accent(naar_grieks_transliteratie(p_prae)) == normaliseer_accent(correct_praesens):
                                        st.session_state.stam_feedback = {"type": "success", "msg": "Genoteerd! Hij komt straks weer."}; trigger_save(); laad_volgend_stam_woord(); st.rerun()
                                    else: st.error("Nog niet exact overgetypt!")

                            elif sub_modus == "Typen":
                                t_gram = st.selectbox("1. Grammatica:", ["", "Futurum Actief/Medium", "Aoristus Actief/Medium", "Aoristus Passief", "Perfectum Actief", "Perfectum Medium/Passief"])
                                t_prae = st.text_input("2. Praesens bronwoord:", key="in_tp_p"); t_bete = st.text_input("3. Betekenis bronwoord:", key="in_tp_b")
                                if st.button("Controleer Antwoord", type="primary"):
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
                                    
                                    if st.form_submit_button("Check Antwoord"):
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
                                                st.session_state.stam_stats[vid]['streak'] = max(0, huidige_streak - 2); st.session_state.gestrafte_woorden_stam.add(vid)
                                                st.session_state.stam_sessie_lijst.insert(0, (huidig, 'overtik')); st.session_state.stam_sessie_lijst.append((huidig, sub_modus))
                                                st.session_state.stam_feedback = {"type": "error", "msg": f"✗ Fout. Het was: {fout_msg}.\n\n{uitleg_regel}"}; trigger_save(); laad_volgend_stam_woord(); st.rerun()
                                            else: st.session_state.stam_stats[vid]['f'] += 1; st.session_state.stam_feedback = {"type": "warning", "msg": f"Eén van je keuzes is onjuist!\n\n{uitleg_regel}"}
                                            st.rerun()

                            if sub_modus != 'overtik':
                                st.write("---")
                                fn = 'Nieuw' if huidige_streak==0 else ('In Training' if huidige_streak<=15 else ('Beheerst' if huidige_streak<=29 else 'Mastery'))
                                st.caption(f"Fase: {fn} | Autonome Streak: {huidige_streak} | Goed/Fout: {st.session_state.stam_stats[vid].get('g',0)}/{st.session_state.stam_stats[vid].get('f',0)}")

       # ==========================================
        # TAB 6: STRUCTUURWOORDEN & SYNTAXIS
        # ==========================================
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
                    struct_filter = st.selectbox(
                        "1. Kies leer-spoor:",
                        _struct_sporen,
                        key="struct_filter_box"
                    )

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

                    struct_modus = st.radio("2. Oefenvorm:", ["1. MC", "2. Mix (MC + Typen)", "3. Typen"], key="struct_modus_radio")

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
                            w['score_goed'] = stats.get('g', 0)
                            w['score_fout'] = stats.get('f', 0)
                            w['streak'] = stats.get('streak', 0)
                            w['vid'] = vid
                            doel_vormen.append(w)
                        
                        if doel_vormen:
                            sampled = kies_gefaseerde_oefensessie(doel_vormen, module='struct')
                            modus_id = str(struct_modus[0])
                            if is_struct_leerpad:
                                # Leerpad: oplopend per woord — nieuw eerst flashcard (Leer) + meerkeuze,
                                # daarna meerkeuze, en bij een stevige streak typen.
                                _struct_kaarten = []
                                for v in sampled:
                                    _s = int(v.get('streak', 0))
                                    if _s <= 0:
                                        _struct_kaarten.append((v, "Leer")); _struct_kaarten.append((v, "MC"))
                                    elif _s <= 7:
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

                        struct_kleur_nv = st.checkbox("🎨 Markeer Naamvallen in zin (Kleur)", key="struct_global_kleur_nv")
                        
                        if bijbel_db:
                            for ref, zin in bijbel_db.items():
                                for idx_w, w in enumerate(zin):
                                    norm_w = normaliseer_accent(w['grieks'])
                                    if any(norm_w == k or norm_w == k.replace('ς','σ') for k in zoek_opties):
                                        
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
                                                    # HIER IS DE SPOILER WEGGESNEDEN:
                                                    t_tip = "❓ [Dit woord wordt getoetst]"
                                                    w_style = f"color: {txt_col}; font-weight: 900; background-color: rgba(255, 215, 0, 0.15); border: 1px solid #ffd700; border-bottom: 3px solid #ffd700; padding: 1px 5px; border-radius: 4px;"
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
                                if gevonden_context: break

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
                                
                                if st.form_submit_button("Check Antwoord"):
                                    registreer_oefening()
                                    if (gekozen_cat == correct_cat) and (p_eig == correct_eig) and check_betekenis(p_bet, correct_bet):
                                        if st.session_state.struct_fouten == 0 and vid not in st.session_state.gestrafte_woorden_struct:
                                            st.session_state.struct_stats[vid]['g'] += 1; st.session_state.struct_stats[vid]['streak'] += 1
                                        dagdoel_plus('struct')
                                        success_msg = f"✓ Goed! {fout_msg_volledig}"
                                        if vid in st.session_state.gestrafte_woorden_struct: success_msg += " *(Geen streak-punten wegens eerdere fout)*"
                                        st.session_state.struct_feedback = {"type": "success", "msg": success_msg}; trigger_save(); laad_volgend_struct_woord(); st.rerun()
                                    else:
                                        st.session_state.struct_fouten += 1; huidige_streak = st.session_state.struct_stats[vid]['streak']
                                        if huidige_streak >= 16 or st.session_state.struct_fouten >= 2:
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
                                
                                if st.form_submit_button("Check Antwoord"):
                                    registreer_oefening()
                                    if (keuze_cat == correct_cat): st.session_state.struct_mc_solved["cat"] = True
                                    if (keuze_eig == correct_eig): st.session_state.struct_mc_solved["eig"] = True
                                    if (keuze_bet == correct_bet): st.session_state.struct_mc_solved["bet"] = True
                                    
                                    if st.session_state.struct_mc_solved["cat"] and st.session_state.struct_mc_solved["eig"] and st.session_state.struct_mc_solved["bet"]:
                                        if st.session_state.struct_fouten == 0 and vid not in st.session_state.gestrafte_woorden_struct:
                                            st.session_state.struct_stats[vid]['g'] += 1; st.session_state.struct_stats[vid]['streak'] += 1
                                        dagdoel_plus('struct')
                                        success_msg = f"✓ Goed! {fout_msg_volledig}"
                                        if vid in st.session_state.gestrafte_woorden_struct: success_msg += " *(Geen streak-punten wegens eerdere fout)*"
                                        st.session_state.struct_feedback = {"type": "success", "msg": success_msg}; trigger_save(); laad_volgend_struct_woord()
                                    else:
                                        st.session_state.struct_fouten += 1; huidige_streak = st.session_state.struct_stats[vid]['streak']
                                        if huidige_streak >= 16 or st.session_state.struct_fouten >= 2:
                                            st.session_state.struct_stats[vid]['streak'] = max(0, huidige_streak - 2); st.session_state.gestrafte_woorden_struct.add(vid)
                                            # In MC blijven: toon het antwoord en doe deze vraag meteen nog een keer als meerkeuze.
                                            st.session_state.struct_sessie_lijst.insert(0, (huidig, sub_modus))
                                            st.session_state.struct_feedback = {"type": "error", "msg": f"✗ Helaas. Jij dacht: *{keuze_cat} | {keuze_eig} | {keuze_bet}*. Het was: {fout_msg_volledig}. Klik hem nu nog één keer goed aan."}; trigger_save(); laad_volgend_struct_woord()
                                        else: st.session_state.struct_stats[vid]['f'] += 1; st.session_state.struct_feedback = {"type": "warning", "msg": "De correcte delen zijn vastgezet. Probeer de overgebleven velden opnieuw!"}
                                    st.rerun()

                        if sub_modus != 'overtik':
                            st.write("---")
                            f_naam = 'Nieuw' if st.session_state.struct_stats[vid].get('streak', 0)==0 else ('In Training' if st.session_state.struct_stats[vid].get('streak', 0)<=15 else ('Beheerst' if st.session_state.struct_stats[vid].get('streak', 0)<=29 else 'Mastery'))
                            st.caption(f"Fase: {f_naam} | Autonome Streak: {st.session_state.struct_stats[vid].get('streak', 0)} | Goed/Fout: {st.session_state.struct_stats[vid].get('g', 0)}/{st.session_state.struct_stats[vid].get('f', 0)}")
                            
        # ==========================================
        # TAB 7: LEESTEKSTEN
        # ==========================================
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
                    tekst_modus = st.radio("2. Oefenmethode:", ["1. Lees & Spiek (Geen vragen)", "2. Vertaal (Meerkeuze)", "3. Vertaal (Typen)", "4. Masterclass (Ontleden)"])

                st.write("---")
                vis_c1, vis_c2, vis_c3, vis_c4 = st.columns(4)
                with vis_c1: kleur_naamvallen = st.checkbox("🎨 Markeer Naamvallen (Kleur)")
                with vis_c2: kleur_voegwoorden = st.checkbox("🔗 Markeer Voegwoorden (Geel)")
                with vis_c3: kleur_stamtijden = st.checkbox("⚛️ Markeer Stamtijden (Paars)")
                with vis_c4: master_niveau = st.selectbox("Niveau Masterclass:", ["Grieks 1", "Grieks 2", "Grieks 3"])

                st.write("---")
                st.markdown("### 3. Selecteer een Bijbeltekst")
                lees_modus = st.radio(
                    "Hoe wil je de tekst kiezen?", 
                    ["Kies specifiek(e) vers(zen)", "Scavenger Hunt (Willekeurig)", "🛡️ Autonome Leestekst (100% Bekend)"], 
                    horizontal=True
                )
                
                if lees_modus == "Kies specifiek(e) vers(zen)":
                    parsed_db = {}
                    for ref in bijbel_db.keys():
                        match = re.match(r"^(.+)\s+(\d+):(\d+[a-zA-Z]?)$", ref)
                        if match: b, c, v = match.group(1), match.group(2), match.group(3)
                        else:
                            parts = ref.split(" ")
                            if len(parts) >= 2 and ":" in parts[-1]: cv = parts[-1].split(":"); b, c, v = " ".join(parts[:-1]), cv[0], cv[1]
                            else: b, c, v = ref, "1", "1"
                        if b not in parsed_db: parsed_db[b] = {}
                        if c not in parsed_db[b]: parsed_db[b][c] = []
                        v_sort = int(re.sub(r"\D", "", v)) if re.sub(r"\D", "", v).isdigit() else 0
                        parsed_db[b][c].append((v_sort, v, ref))
                    
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
                            
                            html_zin += f"<span class='{css_class} mobile-tooltip' tabindex='0' style='{extra_style}'>{w['grieks']}<span class='tooltiptext'>{hover_text.replace('\'', '&#39;').replace('\"', '&quot;')}</span></span>{w['interpunctie']} "
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
                                    
                                    if st.form_submit_button("Check Stamtijd"):
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
                                                basis['streak'] = max(0, int(basis.get('streak', 0)) - 2); basis['score_fout'] = int(basis.get('score_fout', 0)) + 1; trigger_save()
                                                st.error(f"✗ Fout. Het was: {basis['nederlands']}")
                                    
                                elif "3." in tekst_modus: 
                                    forceer_focus()
                                    with st.form(key=f"form_typ_{idx}"):
                                        inp = st.text_input("Woordenboekvertaling:")
                                        if st.form_submit_button("Check"):
                                            registreer_oefening(basis)
                                            if check_betekenis(inp, basis['nederlands']): basis['streak'] = int(basis.get('streak', 0)) + 3; basis['score_goed'] = int(basis.get('score_goed', 0)) + 1; trigger_save(); st.success(f"✓ Goed! **{w['grieks']}** = {basis['nederlands']} ({w['parsing_info']})")
                                            else: basis['streak'] = max(0, int(basis.get('streak', 0)) - 2); basis['score_fout'] = int(basis.get('score_fout', 0)) + 1; trigger_save(); st.error(f"✗ Fout. Het is: {basis['nederlands']}")
                                            
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
                                                
                                        if st.button("Controleer Analyse", key=f"chk_{idx}"):
                                            registreer_oefening(basis)
                                            if check_betekenis(t_inp, basis['nederlands']) and check_bijbel_parsing_uitgebreid(p_soort, p_naam, p_get, p_ges, p_tijd, p_wijs, p_diat, p_pers, w['parsing_info']):
                                                basis['streak'] = int(basis.get('streak', 0)) + 3; basis['score_goed'] = int(basis.get('score_goed', 0)) + 1; dagdoel_plus('verzen'); trigger_save(); st.success(f"✓ Volledig correct! ({w['parsing_info']})")
                                            else:
                                                basis['streak'] = max(0, int(basis.get('streak', 0)) - 2); basis['score_fout'] = int(basis.get('score_fout', 0)) + 1; trigger_save(); st.error(f"✗ Onjuist. Officiële data: {w['parsing_info']} | Betekenis: {basis['nederlands']}")
                                                
                    st.write("---")
                    st.write("### ✍️ Zinsvertaling")
                    user_vertaling = st.text_area("Vertaal de hele zin naar het Nederlands:")
                    if st.button("Toon vertaling"):
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
                            if st.button("Controleer", key=f"chk1_{skey}", type="primary"):
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
                            alle_naar = list({o["naar"] for o in opgaven})
                            afleiders = [x for x in alle_naar if x != opg["naar"]]
                            r_engine.shuffle(afleiders)
                            opties = afleiders[:3] + [opg["naar"]]
                            r_engine.shuffle(opties)
                            keuze = st.radio("Wat is de juiste vorm?", opties, index=None, key=f"n2_{skey}_{stt['idx']}")
                            if st.button("Controleer", key=f"chk2_{skey}", type="primary"):
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
                                verzonden = st.form_submit_button("Controleer", type="primary")
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
                    st.markdown("### 📊 Jouw grammatica-voortgang per onderwerp")
                    st.caption("Deze telling gebruikt je oefenmomenten in dit tabblad. Vanaf 3 correcte herkenningen op rij = 'op weg', vanaf 8 = 'beheerst'.")
                    rijen = []
                    for g in sorted(items.keys(), key=lambda x: int(x)):
                        s = st.session_state.gram_stats.get(g, {})
                        streak = int(s.get("streak", 0))
                        if streak >= 8: status = "🟢 Beheerst"
                        elif streak >= 3: status = "🟡 Op weg"
                        elif streak >= 1 or int(s.get("g", 0)) or int(s.get("f", 0)): status = "🟠 Begonnen"
                        else: status = "⚪ Nog niet"
                        rijen.append({"Onderwerp": f"G{g} · {items[g]['titel']}", "Thema": items[g]["thema"],
                                      "Streak": streak, "Goed": int(s.get("g", 0)), "Fout": int(s.get("f", 0)), "Status": status})
                    df_gram = pd.DataFrame(rijen)
                    beheerst = sum(1 for r in rijen if "Beheerst" in r["Status"])
                    totaal = len(rijen)
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Beheerst", f"{beheerst}/{totaal}")
                    m2.metric("Op weg", sum(1 for r in rijen if "Op weg" in r["Status"]))
                    m3.metric("Voortgang", f"{int(100*beheerst/totaal) if totaal else 0}%")
                    st.progress(beheerst / totaal if totaal else 0)
                    st.write("---")
                    tf = st.selectbox("Toon thema:", ["Alle thema's", "Naamwoorden", "Voornaamwoorden", "Werkwoorden", "Syntaxis & overig"], key="voortgang_thema")
                    toon_df = df_gram if tf == "Alle thema's" else df_gram[df_gram["Thema"] == tf]
                    st.dataframe(toon_df, use_container_width=True, hide_index=True)

        # ==========================================
        # TAB 9: UITLEG & HULP (Masterclass Bijsluiter)
        # ==========================================
        with menu[8]:
            st.subheader("ℹ️ Handboek & Achterliggende Logica")

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
            st.write("---")

            st.markdown("### 📱 De App installeren als PWA (Beginscherm)")
            st.info("Je kunt deze webapplicatie opslaan op je telefoon. Hij opent dan razendsnel in full-screen zonder afleidende adresbalk.")
            st.markdown("* **iPhone (Safari):** Tik onderin op de deel-knop (vierkantje met pijltje omhoog) → *'Zet op beginscherm'*\n* **Android (Chrome):** Tik rechtsboven op de drie puntjes → *'Toevoegen aan startscherm'*")
            st.write("---")
            st.markdown("""
            ## 🏛️ De Didactische Architectuur
            Deze applicatie is ontworpen om de grens over te steken van *domweg rijtjes stampen* naar **morfologisch inzicht**. Hieronder lees je hoe de AI-motor onder de motorkap functioneert.

            ### 1. De Leermotor: Spaced Repetition
            Elk item in de app heeft een 'Universele Streak'. Hoe vaker je iets achter elkaar goed beantwoordt, hoe hoger de streak en hoe groter de tijdsinterval tot de volgende overhoring.
            * **Streak 0 (Nieuw):** Woorden die je nog moet funderen.
            * **Streak 1–15 (In Training):** De intensieve inslijp-fase.
            * **Streak 16–29 (Beheerst):** Kennis is geland; de app test je nu nog maar sporadisch om wegglijden te voorkomen.
            * **Streak 30+ (Mastery):** Het ultieme doel. Het losse woord verdwijnt. De app zoekt via het Strong-nummer een **authentieke Bijbelzin uit het Nieuwe Testament** en vraagt je het woord live in zijn theologische context te vertalen!

            ### 2. Nakijken: Slagvrij & Synoniem-tolerant
            * **Levenshtein-afstand:** Typ je per ongeluk `weliswar` i.p.v. `weliswaar`? De wiskundige motor telt het aantal 'foute bewerkingen' en keurt kleine typefouten bij langere woorden gewoon goed.
            * **Slashes en Komma's:** Antwoorden in de database zoals `zien / kijken` worden door de app op de achtergrond opgesplitst als twee losse, 100% geldige antwoorden.
            * **Haakjes:** Alles wat in de database tussen `()`, `[]` of `{}` staat (bijv. context-uitleg) filtert de nakijk-engine netjes weg.

            ### 3. De Harde Hand: Het Strafbankje
            Leren vanuit je *kortetermijngeheugen* levert schijn-kennis op. Daarom hanteert de app twee ijzeren regels:
            1. **Strafwerk:** Maak je bij een woord 2x een fout (of 1x een fout terwijl het woord al op 'Beheerst' stond)? Dan incasseer je **-2 streak-punten** én dwingt de app je het antwoord direct foutloos over te tikken.
            2. **Het Strafbankje:** Het foute woord wordt op de achtergrond op een virtueel strafbankje gezet. Wanneer het woord aan het eind van je sessie ter herhaling langskomt en je doet het dán goed, krijg je je welverdiende vinkje, maar **0 streak-punten**. De app weigert je langetermijn-score te verhogen voor een antwoord dat je 3 minuten geleden hebt overgetypt.

            ### 4. Tabblad 5 (Stamtijden): Scaffolding & Klankwetten
            * **Vrij Studeren (Paspoort):** Via Modus 0 kun je de 'Mental Map' van een werkwoord opvragen. Je ziet de 6 stamtijden in hun vaste Griekse raamwerk, de taalkundige stamwortel en de fonetische formule.
            * **De Steigers (Scaffolding):** De trainingsmodus overhoort je autonoom. Je start op 0. Pas als het *Praesens* in je algemene woordenschat-lijst op streak 5 staat, opent de sluis naar dit tabblad en mag je het *Futurum* oefenen.
            * **De 5 Klankklassen:** Het Grieks is wiskunde. De app traint je op de 5 grote stam-botsingen met de Sigma (σ):
              1. *Labialen (π, β, φ):* versmelten met σ tot een **ψ** (*βλέπω → βλέψω*).
              2. *Gutturalen (κ, γ, χ):* versmelten met σ tot een **ξ** (*ἄγω → ἄξω*).
              3. *Dentalen (τ, δ, θ, ζ):* vallen simpelweg weg voor de σ (*πείθω → πείσω*).
              4. *Contracta (α, ε, ο):* de stamklinker ondergaat compensatorische rekking (*ποιέω → ποιήσω*).
              5. *Liquidae (λ, μ, ν, ρ):* haten de sigma en trekken samen tot een circumflexus (*μένω → μενῶ*).

            ### 5. Hoe stelt de app je oefensessie samen?
            Bij *"Aanbevolen Mix"* en in het **Leerpad** kies je de woorden niet zelf — de app stelt elke sessie (± 10 kaarten) slim samen. Dit gebeurt er, op volgorde:

            1. **Fase bepalen** — elk woord valt op basis van je streak in een fase: 🌱 Nieuw (0) · 🐣 Prille start (1–3) · 🏃 In training (4–15) · 🛡️ Beheerst (16–29) · 🏆 Mastery (30+).
            2. **Prioriteren** — wat de meeste aandacht nodig heeft, komt eerst:
               * **Teruggevallen woorden** (ooit gekend, nu terug op 0) gaan vóór op gloednieuwe.
               * Een **worstel-bonus** tilt foutgevoelige woorden omhoog; een stevige streak dempt de urgentie.
               * **Lang niet gedaan** telt zwaarder, zodat oude stof terugkomt.
               * Er is een **rem op nieuwe woorden** (± 2 per sessie), zodat je niet wordt overspoeld.
            3. **Herhaling meemengen** — er komt altijd minstens **één oud/overdue woord** mee (in het Leerpad instelbaar: 1, 5 of 10 — oudste datum eerst). Zo blijft eerder geleerde stof vers.
            4. **Verwar-partners erbij** — woorden die qua **vorm op elkaar lijken** (look-alikes) of die **jij aantoonbaar door elkaar haalt**, komen in dezelfde sessie mee, zodat je ze naast elkaar leert onderscheiden. Nooit gloednieuwe woorden — alleen wat je al eens hebt gezien. Een verwarpaar valt vanzelf weg zodra je beide woorden weer beheerst.
            5. **Oefenvorm laten meegroeien** (Leerpad) — de app kiest zelf de moeilijkheid per woord: 🌱 nieuw → **flashcard + meerkeuze**, 🏃 in training → **meerkeuze**, 🛡️ sterk → **typen**. Twee keer fout? Dan eerst **overtypen** (telt niet mee) en het woord komt later terug.

            ### 6. Dagelijks doel
            In het **🎯 Dagelijks doel**-tabblad stel je je dagelijkse portie in. Het **woord-dagblok** speelt de woord-achtige onderdelen naadloos achter elkaar af: je woorden → moeilijke woorden → verwarparen. De app houdt je **dagblok-streak** bij (opeenvolgende dagen dat je het afmaakt); structuurwoorden, stamtijden en verzen vink je zelf af.

            ---
            *Ontwikkeld voor Grieks Premaster PTHU. Vragen of suggesties? Mail naar:* **jtimmer@students.pthu.nl**
            """)

        # ==========================================
        # TAB 10: NL -> GRIEKS (ACTIEVE PRODUCTIE)
        # ==========================================
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
                    invoer_type = st.radio(
                        "Invoer:",
                        ["⌨️ Typen (Latijnse toetsen → Grieks)", "🔢 Meerkeuze (kies de juiste Griekse vorm)"],
                        key="prod_invoer"
                    )
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
                            st.rerun()

                        if invoer_type.startswith("⌨️"):
                            with st.form(f"prod_typ_{strong_key}", clear_on_submit=True):
                                inp = st.text_input("Grieks (Latijnse toetsen mag):", key=f"prod_in_{strong_key}")
                                verzonden = st.form_submit_button("Controleer", type="primary")
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
                            if st.button("Controleer", key=f"prod_mc_btn_{strong_key}", type="primary"):
                                if keuze is None:
                                    st.warning("Kies eerst een optie.")
                                else:
                                    st.session_state.prod_opties = None
                                    prod_verwerk(keuze == correct_grieks)

        # ==========================================
        # TAB 11: DAGELIJKS DOEL
        # ==========================================
        with menu_dagdoel:
            st.subheader("🎯 Dagelijks doel")
            st.caption("Je vaste dagelijkse ronde. Zet je dagblok klaar en loop de tabbladen van links naar rechts af — je kalender kleurt vol naarmate je meer doet.")
            _cfg = dagdoel_config()
            _lg = dagdoel_log_vandaag()

            c_top1, c_top2, c_top3 = st.columns(3)
            c_top1.metric("🔥 Dagblok-streak", f"{dagdoel_streak()} dagen")
            c_top2.metric("Woord-dagblok vandaag", "✅ klaar" if _lg.get('woordblok') else "nog niet")
            c_top3.metric("Totaal geoefend vandaag", int((st.session_state.dag_stats or {}).get(_vandaag_str(), 0)))

            st.write("---")
            st.markdown("### ▶️ Zet je dagblok klaar")
            st.caption(f"Doel vandaag: **{_cfg['woorden']} woorden · {_cfg['knelpunt']} moeilijke · {_cfg['verwar']} verwarparen · {_cfg['stam']} stamtijden · {_cfg['struct']} structuurwoorden · {_cfg['verzen']} verzen**.")
            if st.button("▶️ Zet woord-dagblok klaar", type="primary", key="dagblok_start"):
                _kaarten, _paren = bouw_dagblok(st.session_state.data, st.session_state.get('verwar_stats', {}), _cfg)
                if not _kaarten and not _paren:
                    st.warning("Geen woorden/paren beschikbaar voor het dagblok. Stel je doelen hoger in of oefen eerst wat woorden.")
                else:
                    st.session_state.gestrafte_woorden_vocab = set()
                    _sessie_reset_samenvatting()
                    st.session_state.sessie_net_klaar = False
                    st.session_state._ballonnen_getoond = False
                    st.session_state.paar_huidig = None; st.session_state.paar_klaar = False
                    st.session_state.vocab_sessie_verzen = {}; st.session_state.vocab_cluster_strongs = {}
                    st.session_state.modus_actief = "dagblok"
                    st.session_state.dagblok_actief = True
                    st.session_state.dagblok_bezig = True
                    st.session_state.dagblok_paar_wacht = _paren
                    st.session_state.sessie_lijst = _kaarten
                    laad_volgend_woord()
                    # Zet ook stamtijden + structuurwoorden kant-en-klaar (openen meteen bij het tabblad).
                    dagblok_arm_stam()
                    dagblok_arm_struct()
                    st.session_state.dagblok_spring = "Woordenschat"
                    st.success("✅ Alles staat klaar! Loop de oefen-tabbladen van links naar rechts af.")
                    st.rerun()

            st.info("👉 **Loop de tabbladen van links naar rechts af:**\n\n"
                    "1. 🚀 **Woordenschat** — je woord-dagblok staat meteen klaar (woorden → moeilijke → verwarparen).\n"
                    "2. 🎓 **Actief Beheersen** — het Leerpad opent meteen bij het huidige rijtje.\n"
                    "3. ⏳ **Stamtijden** — staat kant-en-klaar in het Leerpad.\n"
                    "4. 🧱 **Structuurwoorden** — staat kant-en-klaar in het Leerpad.\n"
                    "5. 📝 **Leesteksten** — kies een tekst en ontleed een paar verzen.\n\n"
                    "Kom daarna hier terug en vink je onderdelen af — dan kleurt je kalender vol. 🎨")

            st.write("---")
            st.markdown("### ✅ Afvinken wat je vandaag deed")
            for _soort, _emoji, _label in [('struct', '🧱', 'Structuurwoorden'),
                                           ('stam', '⏳', 'Stamtijden'),
                                           ('verzen', '📝', 'Verzen ontleden')]:
                _gedaan = int(_lg.get(_soort, 0)); _doel = int(_cfg[_soort])
                cc1, cc2 = st.columns([4, 1])
                with cc1:
                    st.progress(min(1.0, _gedaan / _doel) if _doel else 1.0, text=f"{_emoji} {_label}: {_gedaan}/{_doel}")
                if cc2.button("✓ +1", key=f"dagdoel_plus_{_soort}"):
                    dagdoel_plus(_soort); trigger_save(forceer=True); st.rerun()

            with st.expander("⚙️ Mijn dagelijkse doelen instellen"):
                _nw = {
                    'woorden': st.slider("Woorden", 0, 40, _cfg['woorden'], key="dd_woorden"),
                    'knelpunt': st.slider("Moeilijke woorden", 0, 20, _cfg['knelpunt'], key="dd_knelpunt"),
                    'verwar': st.slider("Verwarparen", 0, 15, _cfg['verwar'], key="dd_verwar"),
                    'struct': st.slider("Structuurwoorden", 0, 20, _cfg['struct'], key="dd_struct"),
                    'stam': st.slider("Stamtijden", 0, 20, _cfg['stam'], key="dd_stam"),
                    'verzen': st.slider("Verzen ontleden", 0, 10, _cfg['verzen'], key="dd_verzen"),
                }
                if st.button("💾 Doelen opslaan", key="dd_save"):
                    _d = st.session_state.get('dagdoel')
                    if not isinstance(_d, dict):
                        _d = {}; st.session_state.dagdoel = _d
                    _d['config'] = _nw
                    trigger_save(forceer=True); st.success("Doelen opgeslagen!"); st.rerun()

            st.write("---")
            st.markdown("#### 📅 Jouw oefenkalender")
            st.markdown(dagkalender_html(st.session_state.get('dag_stats') or {},
                                         (st.session_state.get('dagdoel') or {}).get('log', {})), unsafe_allow_html=True)


if __name__ == "__main__":
    main()
