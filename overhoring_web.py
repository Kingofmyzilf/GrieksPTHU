import streamlit as st
import streamlit.components.v1 as components
from streamlit_gsheets import GSheetsConnection
import json
import pandas as pd
import random
import re
import math
import matplotlib.pyplot as plt
import os
import unicodedata
from datetime import datetime

def veilig_les_nummer(item):
    try:
        return int(item.get('les', 0))
    except (ValueError, TypeError):
        return 0
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

def veilig_les_nummer(item):
    try: return int(item.get('les', 1))
    except: return 1

def naar_grieks_transliteratie(tekst):
    mapping = { 'a': 'α', 'b': 'β', 'g': 'γ', 'd': 'δ', 'e': 'ε', 'z': 'ζ', 'h': 'η', 'q': 'θ', 'i': 'ι', 'k': 'κ', 'l': 'λ', 'm': 'μ', 'n': 'ν', 'c': 'ξ', 'o': 'ο', 'p': 'π', 'r': 'ρ', 's': 'σ', 't': 'τ', 'u': 'υ', 'f': 'φ', 'x': 'χ', 'y': 'ψ', 'w': 'ω' }
    res = ""
    tekst = str(tekst).lower().strip()
    for char in tekst: res += mapping.get(char, char)
    return res.replace('σ', 'ς') if res.endswith('σ') else res

def normaliseer_accent(woord):
    if pd.notna(woord) and str(woord).strip() != "":
        w = str(woord).strip().lower()
        w = ''.join(c for c in unicodedata.normalize('NFD', w) if unicodedata.category(c) != 'Mn')
        w = w.replace('a', 'α').replace('e', 'ε').replace('i', 'ι').replace('o', 'ο').replace('u', 'υ')
        w = w.replace('(ν)', '').replace('(ν', '').replace('ν)', '')
        return w.strip()
    return ""

def deconstrueer_stamtijd_live(vorm, tijd_diathese):
    """Knipt een Griekse stamtijd live op in (Stam, Uitgang/Tijdkenmerk)"""
    if not vorm or vorm in ["n.v.t.", "---", "-"]:
        return "", ""

    v_schoon = vorm.strip()

    # De vaste Griekse tijd-markers (Gesorteerd van lang naar kort!)
    if tijd_diathese == "Futurum Actief/Medium":
        uitgangen = ["θήσομαι", "ήσομαι", "σομαι", "οῦμαι", "ομαι", "σω", "ψω", "ξω", "ῶ", "ω"]
    elif tijd_diathese == "Aoristus Actief/Medium":
        uitgangen = ["σάμην", "άμην", "όμην", "σα", "ψα", "ξα", "ον", "αν", "ην", "α", "ν"]
    elif tijd_diathese == "Aoristus Passief":
        uitgangen = ["θην", "ην"]
    elif tijd_diathese == "Perfectum Actief":
        uitgangen = ["κα", "α"]
    elif tijd_diathese == "Perfectum Medium/Passief":
        uitgangen = ["σμαι", "μμαι", "γμαι", "ημαι", "ειμαι", "ωμαι", "αμαι", "μαι"]
    else:
        return v_schoon, ""

    for u in uitgangen:
        if v_schoon.endswith(u):
            knip = len(v_schoon) - len(u)
            stam = v_schoon[:knip]
            uitgang = v_schoon[knip:]
            # Voorkom absurde splitsingen (bijv. 'ἔγνων' -> stam '' en uitgang 'ων')
            if len(stam) > 0:
                return stam, uitgang

    return v_schoon, "" # Fallback: toon het woord ongesplitst
    
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

    delen_ruw = [d.strip() for d in correcte_zin.replace(';', ',').split(',')]
    for d in delen_ruw:
        if is_match(ingevuld, d): return True

    schoon = re.sub(r'\([^)]*\)', '', correcte_zin)
    schoon = re.sub(r'\[[^\]]*\]', '', schoon)
    schoon = re.sub(r'\{[^}]*\}', '', schoon)
    schoon = schoon.replace('=', '').replace('*', '').replace('+', '')

    delen_schoon = [d.strip() for d in schoon.replace(';', ',').split(',') if d.strip()]
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

def zoek_context_zin(strong_nr, woordsoort, bijbel_db, anti_spiek=False, specifieke_vorm=None):
    if not strong_nr or not bijbel_db: return None
    beste_zin = None
    fallback_zin = None
    
    doel_vorm_schoon = normaliseer_accent(specifieke_vorm) if specifieke_vorm else None
    
    for ref, zin in bijbel_db.items():
        for w in zin:
            if str(w.get('strong', '')) == str(strong_nr):
                if doel_vorm_schoon:
                    if normaliseer_accent(w['grieks']) == doel_vorm_schoon:
                        beste_zin = (ref, zin)
                        break
                else:
                    if not fallback_zin: fallback_zin = (ref, zin)
                    p = w.get('parsing_info', '')
                    is_dict_form = False
                    if woordsoort == 'ww' or "Werkwoord" in p:
                        if "1e pers." in p and "ev" in p and "Indicativus" in p: is_dict_form = True
                    elif woordsoort in ['znw', 'bnw', 'lidw'] or any(x in p for x in ["Zelfst.", "Bijv.", "Lidw"]):
                        if "Nom" in p and "ev" in p: is_dict_form = True
                    else:
                        is_dict_form = True 

                    if is_dict_form:
                        beste_zin = (ref, zin)
                        break
        if beste_zin: break
        
    keuze = beste_zin if beste_zin else (fallback_zin if not doel_vorm_schoon else None)
    
    if keuze:
        ref, zin = keuze
        html_zin = ""
        grieks_puur = ""
        engels_puur = ""
        
        for zw in zin:
            g_woord = zw['grieks']
            interp = zw.get('interpunctie', '')
            grieks_puur += f"{g_woord}{interp} "
            engels_puur += f"{zw.get('vertaling_bsb', '')} "
            
            tooltip = f"{zw.get('vertaling_bsb', '')} ({zw.get('parsing_info', '')})"
            tooltip = tooltip.replace("'", "&#39;").replace('"', "&quot;")
            
            p_info = zw.get('parsing_info', '')
            kleur_stijl = ""
            if "Nom" in p_info: kleur_stijl += "color: #33ccff;"
            elif "Gen" in p_info: kleur_stijl += "color: #28a745;"
            elif "Dat" in p_info: kleur_stijl += "color: #6f42c1;"
            elif "Acc" in p_info: kleur_stijl += "color: #dc3545;"
            elif "Voc" in p_info: kleur_stijl += "color: #fd7e14;"
            elif not anti_spiek and ("Voegwoord" in p_info or "Conjunction" in p_info):
                kleur_stijl += "background-color: #ffd700; color: #000; padding: 0 4px; border-radius: 4px;"
            else:
                kleur_stijl += "color: #888888;"
            
            is_doelwoord = (str(zw.get('strong', '')) == str(strong_nr)) and (not doel_vorm_schoon or normaliseer_accent(g_woord) == doel_vorm_schoon)
            
            if is_doelwoord:
                if anti_spiek:
                    html_zin += f"<span tabindex='0' style='color: #ffffff; font-weight: bold; text-decoration: underline;'>{g_woord}</span>{interp} "
                else:
                    html_zin += f"<span class='mobile-tooltip' tabindex='0' style='color: #ffffff; font-weight: bold; text-decoration: underline;'>{g_woord}<span class='tooltiptext'>{tooltip}</span></span>{interp} "
            else:
                html_zin += f"<span class='mobile-tooltip' tabindex='0' style='{kleur_stijl} border-bottom: 1px dotted #555;'>{g_woord}<span class='tooltiptext'>{tooltip}</span></span>{interp} "
                
        html_weergave = f"<div style='font-size: 14px; margin-bottom: 5px; color: #f6c23e;'>📖 Context: {ref}</div><div class='grieks-zin' style='font-size: 24px; padding: 15px; margin-bottom: 15px;'>{html_zin.strip()}</div>"
        
        return {"html": html_weergave, "ref": ref, "grieks_puur": grieks_puur.strip(), "engels_puur": engels_puur.strip()}
    return None

def veilige_json_load(data_str):
    s = str(data_str).strip()
    if not s or s.lower() == 'nan': return {}
    s = s.replace('“', '"').replace('”', '"').replace("'", '"')
    try:
        return json.loads(s)
    except:
        return {}

# --- ALGORITMES & TRACKING ---
def registreer_oefening(item=None):
    vandaag = str(datetime.now().date())
    if 'dag_stats' not in st.session_state: st.session_state.dag_stats = {}
    st.session_state.dag_stats[vandaag] = st.session_state.dag_stats.get(vandaag, 0) + 1
    if item is not None:
        item['laatst_geoefend'] = vandaag

def krijg_streak(item, module):
    return int(item.get('streak', 0))

def kies_gefaseerde_oefensessie(doel_lijst, module, custom_counts=None, max_nieuw=3):
    nieuw, training, beheerst, mastery = [], [], [], []
    for item in doel_lijst:
        s = krijg_streak(item, module)
        if s == 0: nieuw.append(item)
        elif 1 <= s <= 15: training.append(item)
        elif 16 <= s <= 29: beheerst.append(item)
        else: mastery.append(item)
    
    def sorteer_key(x):
        d_str = x.get('laatst_geoefend', '')
        if not d_str: return datetime.min.date()
        try: return datetime.strptime(d_str, '%Y-%m-%d').date()
        except: return datetime.min.date()

    training.sort(key=sorteer_key)
    beheerst.sort(key=sorteer_key)
    mastery.sort(key=sorteer_key)
    random.shuffle(nieuw)
    
    sessie = []
    
    if custom_counts is not None:
        sessie.extend(nieuw[:custom_counts.get('nieuw', 0)])
        sessie.extend(training[:custom_counts.get('training', 0)])
        sessie.extend(beheerst[:custom_counts.get('beheerst', 0)])
        sessie.extend(mastery[:custom_counts.get('mastery', 0)])
        random.shuffle(sessie)
        return sessie

    doel_grootte = 15 if (len(nieuw) + len(training)) <= 4 else 10
    ruimte_voor_training = min(len(training), 8 - min(len(nieuw), max_nieuw))
    sessie.extend(training[:ruimte_voor_training])
    sessie.extend(nieuw[:max_nieuw])
    
    if len(sessie) < doel_grootte: sessie.extend(beheerst[:doel_grootte - len(sessie)])
    if len(sessie) < doel_grootte: sessie.extend(mastery[:doel_grootte - len(sessie)])
        
    random.shuffle(sessie)
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

# --- DATABASE FUNCTIES ---
@st.cache_data
def laad_actief_beheersen_db():
    if os.path.exists("actief_beheersen.json"):
        with open("actief_beheersen.json", "r", encoding="utf-8") as f: return json.load(f)
    return None
    
@st.cache_data
def laad_actief_db():
    try:
        # Zorg dat deze bestandsnaam exact overeenkomt met de naam in je map
        with open("actief_beheersen.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
        
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
            st.session_state.vocab_stats = {}; st.session_state.gram_stats = {}; st.session_state.stam_stats = {}; st.session_state.struct_stats = {}; st.session_state.dag_stats = {}
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
                else:
                    return veilige_json_load(row.get(prefix, '{}'))

            st.session_state.vocab_stats = reassemble_chunks('vocab_stats', 'v_chunks')
            st.session_state.gram_stats = reassemble_chunks('gram_stats', 'g_chunks')
            st.session_state.stam_stats = reassemble_chunks('stam_stats', 'st_chunks')
            st.session_state.struct_stats = reassemble_chunks('struct_stats', 'sr_chunks')
            st.session_state.dag_stats = reassemble_chunks('dag_stats', 'd_chunks')
            
        for r in basis:
            stats = st.session_state.vocab_stats.get(r['grieks'], {})
            
            if 'm4' in stats or 'm1' in stats:
                m1 = stats.get('m1', 0); m2 = stats.get('m2', 0); m3 = stats.get('m3', 0); m4 = stats.get('m4', 0)
                r['streak'] = (m1 * 0) + (m2 * 1) + (m3 * 2) + (m4 * 4)
            else:
                r['streak'] = stats.get('streak', 0)
            
            r['score_goed'] = stats.get('g', 0)
            r['score_fout'] = stats.get('f', 0)
            r['laatst_geoefend'] = stats.get('laatst_geoefend', "")
            
            if 'lexeem_info' not in r or not r['lexeem_info']:
                r['lexeem_info'] = r.get('grieks_info', '')

        return basis
    except Exception: return None

def opslaan_naar_cloud():
    if not st.session_state.get('last_user'): return
    try:
        df = conn.read(ttl=0)
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
        st_ch, st_count = get_chunks(st.session_state.get('stam_stats', {}), 'stam_stats')
        sr_ch, sr_count = get_chunks(st.session_state.get('struct_stats', {}), 'struct_stats')
        d_ch, d_count = get_chunks(st.session_state.get('dag_stats', {}), 'dag_stats')
        
        nieuwe_rij_dict = {
            'gebruikersnaam': st.session_state.last_user,
            'v_chunks': v_count, 'g_chunks': g_count, 'st_chunks': st_count, 'sr_chunks': sr_count, 'd_chunks': d_count
        }
        
        nieuwe_rij_dict.update(v_ch); nieuwe_rij_dict.update(g_ch); nieuwe_rij_dict.update(st_ch)
        nieuwe_rij_dict.update(sr_ch); nieuwe_rij_dict.update(d_ch)
        
        nieuwe_rij = pd.DataFrame([nieuwe_rij_dict])
        conn.update(data=pd.concat([df_andere, nieuwe_rij], ignore_index=True))
    except Exception as e:
        st.error(f"⚠️ Fout bij cloud-opslag. Je verliest geen data, maar check je Google Sheet koppeling: {e}")

def trigger_save():
    if not st.session_state.get('last_user') or not st.session_state.get('data'): return
    
    nieuwe_vocab_stats = {}
    for word in st.session_state.data:
        s = int(word.get('streak', 0))
        g = int(word.get('score_goed', 0))
        f = int(word.get('score_fout', 0))
        l = word.get('laatst_geoefend', "")
        if s > 0 or g > 0 or f > 0 or l != "":
            entry = {'streak': s, 'g': g, 'f': f}
            if l: entry['laatst_geoefend'] = l
            nieuwe_vocab_stats[word['grieks']] = entry
            
    st.session_state.vocab_stats = nieuwe_vocab_stats
    opslaan_naar_cloud()

# --- INITIALISATIE ---
for key in ['data', 'sessie_lijst', 'huidig_item', 'huidige_sub_modus', 'huidige_vorm_data', 'feedback', 
            'fouten_huidig_woord', 'huidige_opties', 'last_user', 'huidig_vers', 'huidige_vers_referentie', 'geziene_verzen',
            'actief_flashcard_huidig', 'actief_nakijk_resultaten', 'mix_combo', 'dag_stats',
            'stam_sessie_lijst', 'stam_huidig', 'stam_sub_modus', 'stam_fouten', 'stam_feedback', 'stam_opties_gram', 'stam_opties_praesens', 'stam_mc_solved',
            'struct_sessie_lijst', 'struct_huidig', 'struct_sub_modus', 'struct_fouten', 'struct_feedback', 'struct_opties_cat', 'struct_opties_eig', 'struct_opties_bet', 'struct_mc_solved',
            'gestrafte_woorden_vocab', 'gestrafte_woorden_stam', 'gestrafte_woorden_struct']:
    if key not in st.session_state: st.session_state[key] = None

if st.session_state.stam_sessie_lijst is None: st.session_state.stam_sessie_lijst = []
if st.session_state.struct_sessie_lijst is None: st.session_state.struct_sessie_lijst = []
if st.session_state.geziene_verzen is None: st.session_state.geziene_verzen = []
if st.session_state.mix_combo is None: st.session_state.mix_combo = {}
if st.session_state.dag_stats is None: st.session_state.dag_stats = {}

# Beveiliging Strafbankjes
if st.session_state.gestrafte_woorden_vocab is None: st.session_state.gestrafte_woorden_vocab = set()
if st.session_state.gestrafte_woorden_stam is None: st.session_state.gestrafte_woorden_stam = set()
if st.session_state.gestrafte_woorden_struct is None: st.session_state.gestrafte_woorden_struct = set()

def laad_volgend_woord():
    if st.session_state.sessie_lijst:
        volgend = st.session_state.sessie_lijst.pop(0)
        st.session_state.huidig_item = volgend[0]
        st.session_state.huidige_sub_modus = volgend[1]
    else: st.session_state.huidig_item = None; st.session_state.huidige_sub_modus = None
    st.session_state.fouten_huidig_woord = 0
    st.session_state.huidige_opties = []; st.session_state.huidige_vorm_data = None

def laad_volgend_stam_woord():
    if st.session_state.stam_sessie_lijst:
        volgend = st.session_state.stam_sessie_lijst.pop(0)
        st.session_state.stam_huidig = volgend[0]
        st.session_state.stam_sub_modus = volgend[1]
    else: st.session_state.stam_huidig = None; st.session_state.stam_sub_modus = None
    st.session_state.stam_fouten = 0
    st.session_state.stam_opties_gram = []; st.session_state.stam_opties_praesens = []
    st.session_state.stam_mc_solved = {"gram": False, "praesens": False}

def laad_volgend_struct_woord():
    if st.session_state.struct_sessie_lijst:
        volgend = st.session_state.struct_sessie_lijst.pop(0)
        st.session_state.struct_huidig = volgend[0]
        st.session_state.struct_sub_modus = volgend[1]
    else: st.session_state.struct_huidig = None; st.session_state.struct_sub_modus = None
    st.session_state.struct_fouten = 0
    st.session_state.struct_opties_cat = []; st.session_state.struct_opties_eig = []; st.session_state.struct_opties_bet = []
    st.session_state.struct_mc_solved = {"cat": False, "eig": False, "bet": False}

# ==========================================
# MAIN APP FUNCTIE
# ==========================================
def main():
    # URL-Based Auto-Login
    if "u" in st.query_params:
        auto_user = st.query_params["u"]
        if st.session_state.data is None or st.session_state.last_user != auto_user:
            st.session_state.last_user = auto_user
            st.session_state.data = laad_gebruiker_data(auto_user)

    with st.sidebar:
        if st.session_state.data is None:
            st.header("👤 Inloggen")
            st.caption("ℹ️ Kies een unieke naam en persoonlijke code (bijv. 'zomer2026' of je postcode). Dit voorkomt dat een naamgenoot met jouw data oefent.")
            
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
                else:
                    st.warning("Vul beide velden in om in te loggen.")
        else:
            st.success(f"👋 Welkom terug, {st.session_state.last_user.split('_')[0]}!")
            st.info("💡 **Auto-Login via de Adresbalk:**\n\nJe bent nu ingelogd. Als je **deze specifieke link** nu toevoegt aan je Startscherm of Bladwijzers, logt de app volgende keer vanzelf in. Je hoeft niets meer in te typen!")
            
            if st.button("🚪 Uitloggen"): 
                trigger_save()
                st.session_state.data = None
                st.session_state.last_user = None
                if "u" in st.query_params:
                    del st.query_params["u"]
                st.rerun()
            
            st.write("---")
            with st.expander("⚙️ Geavanceerd / Backup"):
                st.caption("Plak hier je ruwe JSON-backup om je scores direct en veilig te herstellen:")
                backup_input = st.text_area("JSON Backup", label_visibility="collapsed")
                if st.button("Herstel Voortgang"):
                    if backup_input:
                        try:
                            schoon_input = backup_input.strip().replace('“', '"').replace('”', '"').replace("'", '"')
                            nieuwe_data = json.loads(schoon_input)
                            
                            for w in st.session_state.data:
                                if w['grieks'] in nieuwe_data:
                                    b = nieuwe_data[w['grieks']]
                                    w['streak'] = b.get('streak', 0)
                                    w['score_goed'] = b.get('g', 0)
                                    w['score_fout'] = b.get('f', 0)
                                    w['laatst_geoefend'] = b.get('laatst_geoefend', "")
                            trigger_save()
                            st.success("Backup is succesvol hersteld en opgeknipt naar de cloud! Je kunt dit menu nu sluiten.")
                        except Exception as e:
                            st.error(f"Fout! Ongeldige code. Details: {e}")

    if st.session_state.data:
        menu = st.tabs(["🚀 Woordenschat", "📖 Lijst", "📊 Voortgang", "🎓 Actief Beheersen", "⏳ Stamtijden", "🧱 Structuurwoorden", "📝 Leesteksten", "ℹ️ Uitleg & Hulp"])

        # ==========================================
        # TAB 1: WOORDENSCHAT
        # ==========================================
        with menu[0]: 
            col1, col2 = st.columns([1, 2])
            with col1:
                modus = st.radio("Modus:", ["1. Leer", "2. MC", "3. Mix (MC + Typen)", "4. Typen"])
                keuze = st.selectbox("Oefening:", ["Lessen", "Mastery", "Knelpunten (Gericht Oefenen)"])
                doel = []
                
                if keuze == "Lessen":
                    alle_lessen = sorted(list(set(veilig_les_nummer(i) for i in st.session_state.data)))
                    gekozen = st.multiselect("Kies lessen", alle_lessen)
                    doel = [word for word in st.session_state.data if veilig_les_nummer(word) in gekozen]
                elif keuze == "Mastery":
                    doel = [word for word in st.session_state.data if int(word.get('streak', 0)) >= 30]
                elif "Knelpunten" in keuze:
                    knel_lijst = []
                    for w in st.session_state.data:
                        g = int(w.get('score_goed', 0))
                        f = int(w.get('score_fout', 0))
                        if (g + f) >= 3 and f > 0:
                            ratio = f / (g + f)
                            knel_lijst.append((w, ratio))
                    knel_lijst.sort(key=lambda x: x[1], reverse=True)
                    doel = [x[0] for x in knel_lijst[:15]]
                
                st.write("---")
                st.write("⚙️ **Sessie Instellingen**")
                
                optie_context = st.checkbox("📖 Toon woorden áltijd in Bijbelcontext", key="optie_context")
                oefen_stijl = st.radio("Sessie opbouw:", ["🤖 Aanbevolen Mix", "🎛️ Zelf Samenstellen"])
                
                custom_counts = None
                if oefen_stijl == "🎛️ Zelf Samenstellen" and doel:
                    c_nieuw = len([w for w in doel if krijg_streak(w, 'vocab') == 0])
                    c_train = len([w for w in doel if 1 <= krijg_streak(w, 'vocab') <= 15])
                    c_beheer = len([w for w in doel if 16 <= krijg_streak(w, 'vocab') <= 29])
                    c_mast = len([w for w in doel if krijg_streak(w, 'vocab') >= 30])
                    
                    st.caption("Kies exact hoeveel woorden je per fase wilt oefenen:")
                    
                    if c_nieuw > 0:
                        val_nieuw = st.slider(f"Nieuw (0) - Beschikbaar: {c_nieuw}", 0, min(20, c_nieuw), min(3, c_nieuw))
                    else:
                        val_nieuw = 0
                        st.write("➖ Geen 'Nieuwe' woorden beschikbaar.")
                        
                    if c_train > 0:
                        val_train = st.slider(f"In Training (1-15) - Beschikbaar: {c_train}", 0, min(20, c_train), min(5, c_train))
                    else:
                        val_train = 0
                        st.write("➖ Geen woorden 'In Training' beschikbaar.")
                        
                    if c_beheer > 0:
                        val_beheer = st.slider(f"Beheerst (16-29) - Beschikbaar: {c_beheer}", 0, min(20, c_beheer), 0)
                    else:
                        val_beheer = 0
                        st.write("➖ Geen 'Beheerste' woorden beschikbaar.")
                        
                    if c_mast > 0:
                        val_mast = st.slider(f"Mastery (30+) - Beschikbaar: {c_mast}", 0, min(20, c_mast), 0)
                    else:
                        val_mast = 0
                        st.write("➖ Geen 'Mastery' woorden beschikbaar.")
                    
                    custom_counts = {'nieuw': val_nieuw, 'training': val_train, 'beheerst': val_beheer, 'mastery': val_mast}
                
                if st.button("Start Sessie", type="primary"):
                    if doel:
                        st.session_state.gestrafte_woorden_vocab = set() # Reset de strafbank voor Vocab
                        modus_id = str(modus[0])
                        sampled = kies_gefaseerde_oefensessie(doel, module='vocab', custom_counts=custom_counts)
                        
                        if not sampled:
                            st.warning("⚠️ Je hebt 0 woorden geselecteerd met de schuifjes. Verhoog de sliders om te beginnen.")
                        else:
                            st.session_state.modus_actief = modus_id
                            
                            if modus_id == "3":
                                mc_deel = [(w, "3_mc") for w in sampled]
                                typ_deel = [(w, "3_typ") for w in sampled]
                                st.session_state.sessie_lijst = mc_deel + typ_deel
                                st.session_state.mix_combo = {w['grieks']: False for w in sampled}
                            else:
                                st.session_state.sessie_lijst = [(w, modus_id) for w in sampled]
                            
                            laad_volgend_woord(); st.rerun()

            with col2:
                if st.session_state.huidig_item:
                    item = st.session_state.huidig_item
                    huidige_sub_modus = st.session_state.huidige_sub_modus
                    
                    is_mastery = int(item.get('streak', 0)) >= 30
                    heeft_vormen = 'vormen_data' in item and isinstance(item['vormen_data'], list) and len(item['vormen_data']) > 0
                    
                    if st.session_state.huidige_vorm_data is None:
                        if is_mastery and heeft_vormen: st.session_state.huidige_vorm_data = random.choice(item['vormen_data'])
                        else: st.session_state.huidige_vorm_data = {"vorm": item.get('grieks', 'Onbekend'), "parsing": "basis"}

                    huidige_vorm = str(st.session_state.huidige_vorm_data.get('vorm', item.get('grieks')))
                    huidige_parsing = str(st.session_state.huidige_vorm_data.get('parsing', 'basis'))
                    
                    extra_info = item.get('lexeem_info', '') or item.get('grieks_info', '')

                    if st.session_state.feedback:
                        if st.session_state.feedback["type"] == "success": st.success(st.session_state.feedback["msg"])
                        elif st.session_state.feedback["type"] == "warning": st.warning(st.session_state.feedback["msg"])
                        else: st.error(st.session_state.feedback["msg"])
                        st.session_state.feedback = None 

                    zin_data = None
                    is_context_gewenst = (is_mastery and huidige_sub_modus != '1') or st.session_state.get('optie_context', False)
                    
                    if is_context_gewenst:
                        if is_mastery and huidige_sub_modus != '1':
                            st.caption(f"🏆 Mastery Modus. (Basiswoord: **{item.get('grieks')}**)")
                        else:
                            st.caption(f"📖 Leren in Context. (Basiswoord: **{item.get('grieks')}**)")
                            
                        bijbel_db = laad_bijbel_db()
                        anti_spiek_aan = (huidige_sub_modus != '1')
                        
                        zin_data = zoek_context_zin(item.get('strong'), item.get('woordsoort', ''), bijbel_db, anti_spiek=anti_spiek_aan, specifieke_vorm=huidige_vorm)
                        if zin_data: 
                            st.markdown(zin_data["html"], unsafe_allow_html=True)
                            st.markdown("<div style='font-size: 14px; margin-bottom: 10px;'>**(Kleurlegenda: <span style='color:#33ccff'>Nom</span> | <span style='color:#28a745'>Gen</span> | <span style='color:#6f42c1'>Dat</span> | <span style='color:#dc3545'>Acc</span> | <span style='color:#fd7e14'>Voc</span>)**</div>", unsafe_allow_html=True)
                        else: 
                            st.markdown(f"<div class='grieks-woord'>{huidige_vorm}</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div class='grieks-woord'>{huidige_vorm}</div>", unsafe_allow_html=True)
                    
                    correct_antw = str(item.get('nederlands', ''))
                    fout_msg_volledig = f"**{item.get('grieks')}** ({extra_info}) — {item.get('fonetisch', '')} — **{correct_antw}**"
                    if is_mastery and heeft_vormen: fout_msg_volledig += f" ({huidige_parsing})"

                    if huidige_sub_modus == 'overtik':
                        st.warning("⚠️ Overtikken: Typ de betekenis over om door te gaan.")
                        st.info(f"Het juiste antwoord is: **{correct_antw}**")
                        forceer_focus()
                        with st.form(key=f"form_overtik_{item.get('grieks')}", clear_on_submit=True):
                            inp = st.text_input("Typ het juiste antwoord over:").lower().strip()
                            if st.form_submit_button("Bevestig"):
                                registreer_oefening(item)
                                if check_betekenis(inp, correct_antw):
                                    st.session_state.feedback = {"type": "success", "msg": "Genoteerd! Dit woord komt straks nog een keer terug."}
                                    laad_volgend_woord(); st.rerun()
                                else: st.error("Niet correct overgetypt. Kijk goed naar het voorbeeld hierboven.")

                    elif huidige_sub_modus == '1':
                        st.info(f"💡 {extra_info} | {item.get('fonetisch', '')} | {item.get('anker', '')} {item.get('beeld', '')}")
                        st.write(f"Betekenis: **{correct_antw}**")
                        if st.button("Volgende (Geen Punten)"): laad_volgend_woord(); st.rerun()

                    elif huidige_sub_modus in ['4', '3_typ']:
                        if st.session_state.fouten_huidig_woord >= 1: st.info(f"💡 {extra_info} | {item.get('fonetisch', '')} | {item.get('anker', '')} {item.get('beeld', '')}")
                        forceer_focus()
                        with st.form(key=f"form_vocab_{item.get('grieks')}", clear_on_submit=True):
                            inp = st.text_input("Woordenboekvertaling:").lower().strip()
                            if is_mastery and heeft_vormen: p_vorm = st.text_input("Vorm (bijv. nom ev m):").lower().strip()
                            else: p_vorm = huidige_parsing.lower().strip()

                            if st.form_submit_button("Check Antwoord"):
                                registreer_oefening(item)
                                betekenis_goed = check_betekenis(inp, correct_antw)
                                vorm_goed = (p_vorm == huidige_parsing.lower().strip())

                                if betekenis_goed and vorm_goed:
                                    if st.session_state.fouten_huidig_woord == 0:
                                        if item['grieks'] not in st.session_state.gestrafte_woorden_vocab:
                                            item['score_goed'] = int(item.get('score_goed', 0)) + 1
                                            if huidige_sub_modus == '4': item['streak'] = int(item.get('streak', 0)) + 3
                                            elif huidige_sub_modus == '3_typ':
                                                if st.session_state.mix_combo.get(item['grieks'], False): item['streak'] = int(item.get('streak', 0)) + 2
                                                else: item['streak'] = int(item.get('streak', 0)) + 1
                                            
                                    success_msg = f"✓ Goed! **{huidige_vorm}** ({extra_info}) = {correct_antw}"
                                    if item['grieks'] in st.session_state.gestrafte_woorden_vocab:
                                        success_msg += " *(Maar wegens je eerdere fout levert dit geen streak-punten op)*"
                                    elif zin_data: 
                                        success_msg += f"\n\n📖 **{zin_data['ref']}**: {zin_data['grieks_puur']}\n\n🇬🇧 *{zin_data['engels_puur']}*"
                                    
                                    st.session_state.feedback = {"type": "success", "msg": success_msg}
                                    trigger_save(); laad_volgend_woord(); st.rerun()
                                else:
                                    if huidige_sub_modus == '3_typ': st.session_state.mix_combo[item['grieks']] = False
                                    
                                    st.session_state.fouten_huidig_woord += 1
                                    huidige_streak = int(item.get('streak', 0))
                                    
                                    if huidige_streak >= 16 or st.session_state.fouten_huidig_woord >= 2:
                                        item['streak'] = max(0, huidige_streak - 2)
                                        st.session_state.gestrafte_woorden_vocab.add(item['grieks'])
                                        st.session_state.sessie_lijst.insert(0, (item, 'overtik'))
                                        st.session_state.sessie_lijst.append((item, huidige_sub_modus))
                                        st.session_state.feedback = {"type": "error", "msg": f"✗ Fout. Jouw invoer: '{inp}'. Het was: {fout_msg_volledig}"}
                                        trigger_save(); laad_volgend_woord()
                                    else:
                                        item['score_fout'] = int(item.get('score_fout', 0)) + 1
                                        st.session_state.feedback = {"type": "warning", "msg": "Bijna! Bekijk de hint en probeer nog eens."}
                                    st.rerun()
                    
                    else:
                        if st.session_state.fouten_huidig_woord >= 1: st.info(f"💡 {extra_info} | {item.get('fonetisch', '')} | {item.get('anker', '')} {item.get('beeld', '')}")
                        correct_optie = f"{correct_antw} ({huidige_parsing})" if (is_mastery and heeft_vormen) else correct_antw
                        
                        if not st.session_state.huidige_opties:
                            afleiders = []
                            gekozen_betekenissen = {correct_optie}
                            
                            if is_mastery and heeft_vormen:
                                andere_parsings = list(set([str(v.get('parsing', '')) for v in item.get('vormen_data', []) if str(v.get('parsing', '')) != str(huidige_parsing)]))
                                random.shuffle(andere_parsings)
                                for p in andere_parsings:
                                    optie = f"{correct_antw} ({p})"
                                    if optie not in gekozen_betekenissen:
                                        afleiders.append(optie); gekozen_betekenissen.add(optie)
                                    if len(afleiders) >= 3: break
                                
                                if len(afleiders) < 3:
                                    pool = [w for w in st.session_state.data if w.get('woordsoort') == item.get('woordsoort') and 'vormen_data' in w]
                                    random.shuffle(pool)
                                    for w in pool:
                                        for v in w.get('vormen_data', []):
                                            p = v.get('parsing', '')
                                            optie = f"{correct_antw} ({p})" 
                                            if optie not in gekozen_betekenissen:
                                                afleiders.append(optie); gekozen_betekenissen.add(optie)
                                            if len(afleiders) >= 3: break
                                        if len(afleiders) >= 3: break
                            else:
                                huidige_w_soort = item.get('woordsoort', '')
                                prefix = item.get('grieks', '')[:2] 
                                pool = [w for w in st.session_state.data if w['grieks'] != item['grieks'] and w.get('woordsoort') == huidige_w_soort]
                                if len(pool) < 3: pool = [w for w in st.session_state.data if w['grieks'] != item['grieks']]
                                
                                similar = [w for w in pool if w['grieks'].startswith(prefix)]
                                random.shuffle(similar)
                                random.shuffle(pool)
                                
                                for w in similar + pool:
                                    bet = str(w.get('nederlands', ''))
                                    if bet not in gekozen_betekenissen:
                                        afleiders.append(bet); gekozen_betekenissen.add(bet)
                                    if len(afleiders) >= 3: break
                            
                            st.session_state.huidige_opties = [correct_optie] + afleiders[:3]
                            random.shuffle(st.session_state.huidige_opties)
                        
                        cols = st.columns(2)
                        for idx, optie in enumerate(st.session_state.huidige_opties):
                            if cols[idx % 2].button(optie, key=f"btn_{idx}_{item.get('grieks')}"):
                                registreer_oefening(item)
                                if optie == correct_optie:
                                    if st.session_state.fouten_huidig_woord == 0:
                                        if item['grieks'] not in st.session_state.gestrafte_woorden_vocab:
                                            item['score_goed'] = int(item.get('score_goed', 0)) + 1
                                            if huidige_sub_modus == '2': item['streak'] = int(item.get('streak', 0)) + 1
                                            elif huidige_sub_modus == '3_mc': st.session_state.mix_combo[item['grieks']] = True
                                        
                                    success_msg = f"✓ Juist! {fout_msg_volledig}"
                                    if item['grieks'] in st.session_state.gestrafte_woorden_vocab:
                                        success_msg += " *(Maar wegens je eerdere fout levert dit geen streak-punten op)*"
                                    elif zin_data: 
                                        success_msg += f"\n\n📖 **{zin_data['ref']}**: {zin_data['grieks_puur']}\n\n🇬🇧 *{zin_data['engels_puur']}*"
                                        
                                    st.session_state.feedback = {"type": "success", "msg": success_msg}
                                    trigger_save(); laad_volgend_woord(); st.rerun()
                                else:
                                    if huidige_sub_modus == '3_mc': st.session_state.mix_combo[item['grieks']] = False
                                    
                                    st.session_state.fouten_huidig_woord += 1
                                    huidige_streak = int(item.get('streak', 0))
                                    
                                    if huidige_streak >= 16 or st.session_state.fouten_huidig_woord >= 2:
                                        item['streak'] = max(0, huidige_streak - 2)
                                        st.session_state.gestrafte_woorden_vocab.add(item['grieks'])
                                        st.session_state.sessie_lijst.insert(0, (item, 'overtik'))
                                        st.session_state.sessie_lijst.append((item, huidige_sub_modus))
                                        st.session_state.feedback = {"type": "error", "msg": f"✗ Fout. Je koos '{optie}'. Het was: {fout_msg_volledig}"}
                                        trigger_save(); laad_volgend_woord()
                                    else:
                                        item['score_fout'] = int(item.get('score_fout', 0)) + 1
                                        st.session_state.feedback = {"type": "warning", "msg": "Niet helemaal juist. Bekijk de hint!"}
                                    st.rerun()

                    if huidige_sub_modus != 'overtik':
                        st.write("---")
                        fase = 'Nieuw' if int(item.get('streak', 0))==0 else ('In Training' if int(item.get('streak', 0))<=15 else ('Beheerst' if int(item.get('streak', 0))<=29 else 'Mastery'))
                        laatst = item.get('laatst_geoefend', 'Nooit')
                        st.caption(f"Fase: {fase} | Universele Streak: {item.get('streak', 0)} | Goed/Fout: {item.get('score_goed', 0)}/{item.get('score_fout', 0)} | Laatst geoefend: {laatst}")

        # ==========================================
        # TAB 2: LIJST
        # ==========================================
        with menu[1]: 
            st.subheader("📖 Database & Lijsten")
            weergave = st.selectbox("Wat wil je bekijken?", ["Vocabulaire", "Actief Beheersen (Rijtjes)", "Stamtijden", "Structuurwoorden"])
            
            if weergave == "Vocabulaire" and st.session_state.data:
                alle_lessen = sorted(list(set(veilig_les_nummer(i) for i in st.session_state.data)))
                les_filter = st.selectbox("Bekijk les:", alle_lessen)
                df_vocab = pd.DataFrame([i for i in st.session_state.data if veilig_les_nummer(i) == les_filter])
                if not df_vocab.empty: st.dataframe(df_vocab[[c for c in ['grieks', 'nederlands', 'streak', 'score_goed', 'score_fout', 'laatst_geoefend', 'woordsoort', 'lexeem_info'] if c in df_vocab.columns]], use_container_width=True)
            elif weergave == "Actief Beheersen (Rijtjes)":
                st.info("De scores voor actieve rijtjes worden per specifieke cel bijgehouden in je profiel.")
            elif weergave == "Stamtijden":
                stamtijden_db = laad_stamtijden_db()
                if stamtijden_db:
                    stam_lijst = []
                    for w in stamtijden_db:
                        for t_d, vorm in w['stamtijden'].items():
                            vid = f"{w['praesens']}_{vorm}"
                            s = st.session_state.stam_stats.get(vid, {'g': 0, 'f': 0, 'streak': 0})
                            stam_lijst.append({"Les": w.get('les', 0), "Praesens": w['praesens'], "Tijd/Diathese": t_d, "Vorm": vorm, "Betekenis": w['betekenis'], "Streak": s['streak'], "Goed": s['g'], "Fout": s['f']})
                    st.dataframe(pd.DataFrame(stam_lijst), use_container_width=True)
            elif weergave == "Structuurwoorden":
                struct_db = laad_structuurwoorden_db()
                if struct_db:
                    str_lijst = []
                    for w in struct_db:
                        s = st.session_state.struct_stats.get(w['grieks'], {'g': 0, 'f': 0, 'streak': 0})
                        str_lijst.append({"Woord": w['grieks'], "Categorie": w['categorie'], "Eigenschap": w['eigenschap'], "Betekenis": w['betekenis'], "Streak": s['streak'], "Goed": s['g'], "Fout": s['f']})
                    st.dataframe(pd.DataFrame(str_lijst), use_container_width=True)

        # ==========================================
        # TAB 3: VOORTGANG & DASHBOARD
        # ==========================================
        with menu[2]: 
            st.subheader("📊 Academische Cockpit & Dashboard")
            
            # --- 1. DATA INLADEN & INITIALISEREN ---
            vocab_db = laad_vocab_db()
            actief_db = laad_actief_db()
            stamtijden_db = laad_stamtijden_db()
            str_db = laad_structuurwoorden_db()

            if "actief_stats" not in st.session_state:
                st.session_state.actief_stats = {}

            # Hulpfunctie voor voortgangsbalken
            def toon_meting(label, beheerst, totaal):
                pct = int((beheerst / totaal) * 100) if totaal > 0 else 0
                st.markdown(f"**{label}** (`{beheerst}/{totaal}` — **{pct}%**)")
                st.progress(beheerst / totaal if totaal > 0 else 0.0)

            # --- 2. STATISTIEKEN BEREKENEN (Jouw bestaande logica) ---
            stats_vocab = {'Nieuw': 0, 'In Training': 0, 'Beheerst': 0, 'Mastery': 0}
            tot_goed_v, tot_fout_v = 0, 0
            vocab_streaks = {} # Handige dictionary voor snelle lookups verderop

            if st.session_state.data:
                for w in st.session_state.data:
                    grieks_woord = w.get('grieks', '')
                    strk = int(w.get('streak', 0))
                    vocab_streaks[grieks_woord] = strk
                    
                    tot_goed_v += int(w.get('score_goed', 0)); tot_fout_v += int(w.get('score_fout', 0))
                    if strk >= 30: stats_vocab['Mastery'] += 1
                    elif strk >= 16: stats_vocab['Beheerst'] += 1
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

            # --- 3. TOP METRICS WEERGAVE ---
            c_met1, c_met2, c_met3 = st.columns(3)
            tot_g = tot_goed_v + tot_goed_s + tot_goed_st
            tot_f = tot_fout_v + tot_fout_s + tot_fout_st
            acc = int((tot_g / (tot_g + tot_f) * 100)) if (tot_g + tot_f) > 0 else 0
            
            c_met1.metric("Totale Accuratesse", f"{acc}%")
            c_met2.metric("Items op 'Mastery'", stats_vocab['Mastery'] + stats_stam['Mastery'] + stats_str['Mastery'])
            c_met3.metric("Totale Beoordelingen", tot_g + tot_f)
            
            st.write("---")

            # --- 4. VOORTGANG PER VAK (Nieuw!) ---
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

            # --- 5. DE STAMTIJDEN SLUIS (Nieuw!) ---
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

            # --- 6. FASERING LEERLIJNEN GRAFIEK (Jouw bestaande logica) ---
            st.markdown("### 📈 Fasering Leerlijnen")
            import pandas as pd
            import matplotlib.pyplot as plt
            
            df_plot = pd.DataFrame({
                'Module': ['Vocabulaire', 'Stamtijden', 'Structuurwoorden'],
                'Nieuw (0)': [stats_vocab['Nieuw'], stats_stam['Nieuw'], stats_str['Nieuw']],
                'In Training (1-15)': [stats_vocab['In Training'], stats_stam['In Training'], stats_str['In Training']],
                'Beheerst (16-29)': [stats_vocab['Beheerst'], stats_stam['Beheerst'], stats_str['Beheerst']],
                'Mastery (30+)': [stats_vocab['Mastery'], stats_stam['Mastery'], stats_str['Mastery']]
            })
            fig, ax = plt.subplots(figsize=(10, 4))
            df_plot.set_index('Module').plot(kind='bar', stacked=True, color=['#e0e0e0', '#f6c23e', '#28a745', '#33ccff'], ax=ax)
            ax.set_ylabel("Aantal items")
            plt.xticks(rotation=0)
            st.pyplot(fig)
            
            st.write("---")

            # --- 7. JOUW OEFENRITME (Jouw bestaande logica) ---
            st.subheader("📅 Jouw Oefenritme (Laatste 14 dagen)")
            from datetime import datetime
            if st.session_state.dag_stats:
                df_dagen = pd.DataFrame(list(st.session_state.dag_stats.items()), columns=['Datum', 'Aantal'])
                df_dagen['Datum'] = pd.to_datetime(df_dagen['Datum'])
                vandaag_dt = datetime.now().date()
                vandaag_pd = pd.to_datetime(vandaag_dt).normalize()
                start_datum = vandaag_pd - pd.Timedelta(days=13)
                
                df_dagen = df_dagen[df_dagen['Datum'] >= start_datum]
                alle_dagen = pd.date_range(start=start_datum, end=vandaag_pd)
                df_dagen = df_dagen.set_index('Datum').reindex(alle_dagen, fill_value=0).reset_index()
                df_dagen.columns = ['Datum', 'Aantal']
                df_dagen['Datum_str'] = df_dagen['Datum'].dt.strftime('%d-%m')

                fig2, ax2 = plt.subplots(figsize=(10, 3))
                ax2.bar(df_dagen['Datum_str'], df_dagen['Aantal'], color='#28a745')
                ax2.set_ylabel("Geoefende items")
                plt.xticks(rotation=45)
                st.pyplot(fig2)
                st.metric("Totaal geoefend (All-time)", sum(st.session_state.dag_stats.values()))
            else:
                st.info("Nog geen oefenhistorie opgebouwd. Begin vandaag!")
            
            st.write("---")

            # --- 8. COMPETITIE DASHBOARD (Jouw bestaande logica) ---
            st.subheader("🏆 Competitie Dashboard (Laatste 14 dagen)")
            try:
                # Let op: Zorg dat 'conn' wereldwijd of in deze scope gedefinieerd is in jouw script
                df_global = conn.read(ttl=0)
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
                        
                        st.dataframe(df_comp, use_container_width=True)
            except Exception:
                st.caption("Kon de competitiegegevens momenteel niet synchroniseren.")
            
            st.write("---")

            # --- 9. KNELPUNTEN (Jouw bestaande logica) ---
            st.subheader("🔥 Jouw Knelpunten (Top 10)")
            knelpunten = []
            for w in st.session_state.data:
                g = int(w.get('score_goed', 0))
                f = int(w.get('score_fout', 0))
                if (g + f) >= 3 and f > 0: 
                    ratio = f / (g + f)
                    knelpunten.append({"Woord": w['grieks'], "Betekenis": w['nederlands'], "Fout-ratio": f"{int(ratio*100)}%", "Fouten": f})
            if knelpunten:
                knelpunten.sort(key=lambda x: x["Fouten"], reverse=True)
                st.dataframe(pd.DataFrame(knelpunten[:10]), use_container_width=True)
            else:
                st.success("Je hebt nog geen duidelijke knelpunten. Ga zo door!")
                
            st.write("---")

            # --- 10. EXPORTEREN ---
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
                # BÈTA-CODE SPIEKBRIEF
                with st.expander("⌨️ Spiekbrief: Hoe typ ik Grieks? (Latijnse toetsen)"):
                    sc1, sc2, sc3 = st.columns(3)
                    sc1.markdown("**Klinkers:**\n* `a` = α\n* `e` = ε\n* `h` = η\n* `i` = ι\n* `o` = ο\n* `u` = υ\n* `w` = ω")
                    sc2.markdown("**Medeklinkers:**\n* `b`=β, `g`=γ, `d`=δ, `z`=ζ\n* `k`=κ, `l`=λ, `m`=μ, `n`=ν\n* `p`=π, `r`=ρ, `t`=τ")
                    sc3.markdown("**Bèta-code:**\n* `q` = θ (thèta)\n* `c` = ξ (xi)\n* `f` = φ (phi)\n* `x` = χ (chi)\n* `y` = ψ (psi)\n* `s` = σ (wordt aan het eind ς!)")

                st.subheader("📝 Paradigma's: Analyseren & Reproduceren")

                # De 4 didactische leerniveaus
                actief_modus = st.radio(
                    "Kies je leervorm:", 
                    ["📖 0. Paradigma-paspoort (Bestuderen)", "🎯 1. Focus op Uitgangen", "📝 2. Volledig Tentamenrooster", "⚡ 3. Flashcards (Zwakke plekken)"], 
                    horizontal=True
                )
                st.write("---")

                # Selectie menu
                niveaus = list(actief_db.keys())
                gekozen_niv = st.selectbox("Niveau / Boek:", niveaus)
                
                categorieen = list(actief_db[gekozen_niv].keys())
                gekozen_cat = st.selectbox("Categorie:", categorieen)
                
                subcats = list(actief_db[gekozen_niv][gekozen_cat].keys())
                gekozen_sub = st.selectbox("Paradigma:", subcats)
                
                huidig_paradigma = actief_db[gekozen_niv][gekozen_cat][gekozen_sub]
                
                st.write("---")

                # =========================================================
                # MODUS 0: PARADIGMA-PASPOORT (De Mental Map)
                # =========================================================
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
                            if toelichting:
                                st.caption(f"_{toelichting}_")
                            st.write("")

                # =========================================================
                # MODUS 1: FOCUS OP UITGANGEN (Micro-Scaffolding)
                # =========================================================
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
                            score = 0
                            fouten = []
                            for item in huidig_paradigma:
                                verwacht = normaliseer_accent(item.get("uitgang", ""))
                                ingevuld = normaliseer_accent(naar_grieks_transliteratie(inputs[item["id"]]))
                                stam = item.get("stam", "")
                                
                                if verwacht == ingevuld or (verwacht == "" and ingevuld == ""):
                                    score += 1
                                else:
                                    fouten.append(f"**{item['label']}:** Verwacht: `{stam}` + `{item.get('uitgang', '')}`, jij typte: `{stam}` + `{ingevuld}`")
                            
                            if score == len(huidig_paradigma):
                                st.success(f"🎉 Perfect! Je hebt alle {score} uitgangen correct!")
                                st.balloons()
                            else:
                                st.error(f"Je had er {score} van de {len(huidig_paradigma)} goed. Kijk naar je fouten:")
                                for f in fouten: st.write("-", f)

                # =========================================================
                # MODUS 2: VOLLEDIG TENTAMENROOSTER (Met Cel-Bevriezing)
                # =========================================================
                elif "2." in actief_modus:
                    st.markdown(f"### {gekozen_sub} (Tentamen)")
                    st.write("Typ de volledige vormen. Goede antwoorden worden vastgezet, foute velden worden leeggemaakt voor een nieuwe poging.")
                    
                    # Beheer van de status per cel in session_state
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
                            
                            if state["correct"]:
                                st.success(f"**{item['label']}:** {item['vorm']}")
                            else:
                                huidige_inputs[i_id] = st.text_input(f"**{item['label']}**", value=state["value"], key=f"tent_{i_id}")

                    st.write("")
                    # Als nog niet alles goed is, toon nakijk knop
                    if not all(s["correct"] for s in st.session_state.tent_state.values()):
                        if st.button("Nakijken", type="primary"):
                            for item in huidig_paradigma:
                                i_id = item["id"]
                                if not st.session_state.tent_state[i_id]["correct"]:
                                    ingevuld = normaliseer_accent(naar_grieks_transliteratie(huidige_inputs.get(i_id, "")))
                                    verwacht = normaliseer_accent(item["vorm"])
                                    
                                    if ingevuld == verwacht:
                                        st.session_state.tent_state[i_id]["correct"] = True
                                        st.session_state.tent_state[i_id]["value"] = item["vorm"]
                                    else:
                                        st.session_state.tent_state[i_id]["value"] = "" # Cel genadeloos leegmaken bij fout!
                            st.rerun()
                    else:
                        st.success("🏆 Geweldig! Je hebt het volledige paradigma foutloos gereproduceerd!")
                        if st.button("Reset Rooster"):
                            st.session_state.tent_state = {item["id"]: {"correct": False, "value": ""} for item in huidig_paradigma}
                            st.rerun()

                # =========================================================
                # MODUS 3: FLASHCARDS (Zwakke plekken)
                # =========================================================
                elif "3." in actief_modus:
                    st.markdown(f"### ⚡ Flashcards ({gekozen_sub})")
                    st.write("Overhoor willekeurige losse vormen uit dit paradigma om je snelheid te trainen.")
                    
                    import random
                    if "flash_huidig" not in st.session_state or st.session_state.get("flash_para_id") != gekozen_sub:
                        st.session_state.flash_para_id = gekozen_sub
                        st.session_state.flash_huidig = random.choice(huidig_paradigma)
                    
                    huidig_fc = st.session_state.flash_huidig
                    
                    st.info(f"Vertaal naar het Grieks: **{gekozen_cat} - {huidig_fc['label']}**")
                    
                    with st.form("fc_form", clear_on_submit=True):
                        fc_in = st.text_input("Griekse vorm:")
                        if st.form_submit_button("Controleer"):
                            verwacht = normaliseer_accent(huidig_fc["vorm"])
                            ingevuld = normaliseer_accent(naar_grieks_transliteratie(fc_in))
                            
                            if verwacht == ingevuld:
                                st.success(f"✓ Goed! Het was inderdaad **{huidig_fc['vorm']}**.")
                                st.session_state.flash_huidig = random.choice(huidig_paradigma)
                            else:
                                stam = huidig_fc.get("stam", "")
                                uitgang = huidig_fc.get("uitgang", "")
                                toelichting = huidig_fc.get("toelichting", "")
                                st.error(f"✗ Fout. Verwacht: **{huidig_fc['vorm']}** (Stam: `{stam}` + Uitgang: `{uitgang}`).\n\n*Tip: {toelichting}*")

        # ==========================================
        # TAB 5: STAMTIJDEN
        # ==========================================
        with menu[4]: 
            stamtijden_db = laad_stamtijden_db()
            bijbel_db = laad_bijbel_db()
            
            if not stamtijden_db: 
                st.warning("Bestand 'stamtijden_verrijkt.json' ontbreekt of is niet ingeladen.")
            else:
                with st.expander("⌨️ Spiekbrief: Hoe typ ik Grieks? (Latijnse toetsen)"):
                    sc1, sc2, sc3 = st.columns(3)
                    sc1.markdown("**Klinkers:**\n* `a` = α, `e` = ε, `h` = η\n* `i` = ι, `o` = ο, `u` = υ, `w` = ω")
                    sc2.markdown("**Medeklinkers:**\n* `b`=β, `g`=γ, `d`=δ, `z`=ζ\n* `k`=κ, `l`=λ, `m`=μ, `n`=ν\n* `p`=π, `r`=ρ, `t`=τ")
                    sc3.markdown("**Bèta-code:**\n* `q` = θ (thèta)\n* `c` = ξ (xi)\n* `f` = φ (phi)\n* `x` = χ (chi)\n* `y` = ψ (psi)\n* `s` = σ (wordt aan het eind ς!)")

                st.subheader("⏳ Stamtijden: Overzien, Herleiden & Trainen")
                
                stam_modus = st.radio(
                    "Kies je activiteit:", 
                    ["📖 0. Werkwoordpaspoort (Vrij studeren)", "1. MC Overhoring", "2. Mix (MC + Typen)", "3. Typen (Herleiden)"], 
                    horizontal=True
                )
                st.write("---")

                # =================================================================
                # MODUS 0: HET WERKWOORDPASPOORT (Met oplichtende tijdkenmerken!)
                # =================================================================
                if "0." in stam_modus:
                    st.markdown("### 📖 Morfologisch Paspoort")
                    alle_lessen_p = sorted(list(set(i.get('les', 0) for i in stamtijden_db if i.get('les', 0) > 0)))
                    pas_les = st.selectbox("Selecteer uit les:", alle_lessen_p)
                    
                    ww_in_les = [w for w in stamtijden_db if w.get('les') == pas_les]
                    gekozen_pas_ww = st.selectbox("Kies het werkwoord:", [w['praesens'] for w in ww_in_les])
                    
                    for w in ww_in_les:
                        if w['praesens'] == gekozen_pas_ww:
                            morf = w.get('morfologie', {})
                            regel = morf.get('mutatieregel', {})
                            
                            st.markdown(f"<div class='grieks-woord' style='font_size:45px;'>{w['praesens']}</div>", unsafe_allow_html=True)
                            st.markdown(f"<h4 style='text-align:center; color:#aaaaaa;'>\"{w['betekenis']}\"</h4>", unsafe_allow_html=True)
                            
                            c_b1, c_b2, c_b3, c_b4 = st.columns(4)
                            c_b1.info(f"**Klasse:** {morf.get('klasse', 'onbekend').capitalize()}")
                            c_b2.warning(f"**Stamwortel:** {morf.get('stamwortel', '-')}")
                            c_b3.success(f"**Strong:** {w.get('strong_nummer', '-')}")
                            c_b4.error(f"**Type:** {'Uitzondering (Stampen)' if morf.get('memoriseren_vereist') else 'Regelmatig (Herleidbaar)'}")
                            
                            st.write("---")
                            st.markdown("#### 🏛️ De 6 Stamtijden")
                            
                            # Koppel de weergave direct aan de exacte JSON-tijd diathese key!
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
                                        # Deconstrueer de vorm live!
                                        dstam, duit = deconstrueer_stamtijd_live(svorm, t_diathese)
                                        gekleurd_html = f"{dstam}<span style='color:#33ccff'>{duit}</span>" if duit else svorm
                                    else:
                                        gekleurd_html = "-"

                                    st.markdown(f"<div style='font-size:22px; font-weight:bold; color:#fff; background-color:#222; padding:10px; border-radius:6px; text-align:center; margin-bottom:15px;'>{gekleurd_html}</div>", unsafe_allow_html=True)
                            
                            st.markdown("#### ⚙️ De Klankwet achter dit raamwerk")
                            if morf.get('memoriseren_vereist'):
                                st.error(f"**Suppletie-werkwoord:** {regel.get('toelichting', 'Puur memoriseren.')}")
                            else:
                                st.success(f"**Formule:** `{regel.get('formule', 'Stam + σ')}`\n\n**Uitleg:** {regel.get('toelichting', '')}")

                # =================================================================
                # MODUS 1, 2 & 3: DE TRAININGS- EN OVERHOOR-ENGINE
                # =================================================================
                else:
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        bron_keuze = st.radio("Oefenbron:", ["📚 Uit geselecteerde lessen", "📖 Uit een Bijbeltekst"], horizontal=True)
                        gekozen_stam_lessen = []
                        gefilterde_ww_pool = []
                        
                        if bron_keuze == "📚 Uit geselecteerde lessen":
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
                                            
                            st.caption(f"Gevonden unieke werkwoord-stammen: {len(strongs_in_tekst)}")
                            gefilterde_ww_pool = [w for w in stamtijden_db if str(w.get('strong_nummer', '')).replace('G', '') in strongs_in_tekst]

                        oefen_stijl = st.radio("Sessie opbouw:", ["🤖 Automatische Gated Mix", "🎛️ Zelf Fasen Samenstellen"], horizontal=True)
                        custom_counts = None
                        
                        if oefen_stijl == "🎛️ Zelf Fasen Samenstellen" and gefilterde_ww_pool:
                            st.caption("Kies de verdeling van de stamtijd-vormen:")
                            custom_counts = {
                                'nieuw': st.slider("Nieuw (Streak 0)", 0, 20, 4),
                                'training': st.slider("In Training (Streak 1–15)", 0, 20, 6),
                                'beheerst': st.slider("Beheerst (Streak 16–29)", 0, 20, 0),
                                'mastery': st.slider("Mastery (Streak 30+)", 0, 20, 0)
                            }

                        if st.button("Start Sessie", key="btn_start_stam", type="primary"):
                            st.session_state.gestrafte_woorden_stam = set()
                            doel_vormen = []
                            tijden_volgorde = ["Futurum Actief/Medium", "Aoristus Actief/Medium", "Aoristus Passief", "Perfectum Actief", "Perfectum Medium/Passief"]

                            for w in gefilterde_ww_pool:
                                p_streak = st.session_state.vocab_stats.get(w['praesens'], {}).get('streak', 0)
                                if p_streak < 5: continue 
                                
                                vorige_streak = p_streak
                                for t_d in tijden_volgorde:
                                    if not (vorm := w.get('stamtijden', {}).get(t_d)): continue
                                    vid = f"{w['praesens']}_{vorm}"
                                    stats = st.session_state.stam_stats.get(vid, {'g':0, 'f':0, 'streak':0})
                                    
                                    if vorige_streak >= 5:
                                        doel_vormen.append({
                                            "basis": w, "vraag_vorm": {"tijd_diathese": t_d, "vorm": vorm}, 
                                            "score_goed": stats.get('g',0), "score_fout": stats.get('f',0), "streak": stats.get('streak',0), "vid": vid
                                        })
                                        vorige_streak = stats.get('streak', 0)
                                    else: break

                            if doel_vormen:
                                sampled = kies_gefaseerde_oefensessie(doel_vormen, 'stam', custom_counts=custom_counts) 
                                m_id = "3" if "3." in stam_modus else ("2" if "2." in stam_modus else "1")
                                if m_id == "2": st.session_state.stam_sessie_lijst = [(v, "MC") for v in sampled[::2]] + [(v, "Typen") for v in sampled[1::2]]
                                elif m_id == "3": st.session_state.stam_sessie_lijst = [(v, "Typen") for v in sampled]
                                else: st.session_state.stam_sessie_lijst = [(v, "MC") for v in sampled]
                                laad_volgend_stam_woord(); st.rerun()
                            else: st.warning("⚠️ Geen stamtijden gevonden. Zorg dat basiswoorden op streak >= 5 staan!")

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
                            
                            # DECONSTRUEER DE VORM VOOR DE FEEDBACK!
                            dstam, duit = deconstrueer_stamtijd_live(huidig['vraag_vorm']['vorm'], correct_gram)
                            gekleurde_vorm_html = f"**{dstam}**<span style='color:#33ccff'>**{duit}**</span>" if duit else f"**{huidig['vraag_vorm']['vorm']}**"
                            
                            fout_msg = f"{gekleurde_vorm_html} — {correct_gram} van **{correct_praesens}** — **{correct_betekenis}**"
                            
                            morf = huidig['basis'].get('morfologie', {})
                            regel = morf.get('mutatieregel', {})
                            uitleg_regel = f"⚠️ **Suppletie:** {regel.get('toelichting', 'Puur memoriseren.')}" if morf.get('memoriseren_vereist') else f"💡 **Klankwet ({morf.get('klasse', 'regelmatig')}):** {regel.get('formule','')} — *{regel.get('toelichting','')}*"

                            huidige_streak = huidig.get('streak', 0)
                            if huidige_streak >= 30:
                                st.caption("🏆 Mastery Modus: Herken de stamtijd in de Bijbel!")
                                s_nr = str(huidig['basis'].get('strong_nummer', '')).replace('G', '')
                                if zin_data := zoek_context_zin(s_nr, 'ww', bijbel_db, anti_spiek=True, specifieke_vorm=huidig['vraag_vorm']['vorm']):
                                    st.markdown(zin_data["html"], unsafe_allow_html=True)
                                else: st.markdown(f"<div class='grieks-woord'>{huidig['vraag_vorm']['vorm']}</div>", unsafe_allow_html=True)
                            else:
                                st.caption("Identificeer deze Griekse stamtijd-vorm:")
                                st.markdown(f"<div class='grieks-woord'>{huidig['vraag_vorm']['vorm']}</div>", unsafe_allow_html=True)

                            # OVERTIKKEN
                            if sub_modus == 'overtik':
                                st.warning("⚠️ Overtikken: Je had deze vorm fout. Vul de correcte gegevens exact in.")
                                st.info(f"Het juiste antwoord is: {fout_msg}")
                                st.markdown(uitleg_regel)
                                
                                p_gram = st.selectbox("1. Grammatica:", ["", "Futurum Actief/Medium", "Aoristus Actief/Medium", "Aoristus Passief", "Perfectum Actief", "Perfectum Medium/Passief"])
                                p_prae = st.text_input("2. Praesens bronwoord:", key="in_ov_p")
                                
                                if st.button("Bevestig Overtikken"):
                                    registreer_oefening()
                                    if p_gram == correct_gram and normaliseer_accent(naar_grieks_transliteratie(p_prae)) == normaliseer_accent(correct_praesens):
                                        st.session_state.stam_feedback = {"type": "success", "msg": "Genoteerd! Hij komt straks weer."}
                                        trigger_save(); laad_volgend_stam_woord(); st.rerun()
                                    else: st.error("Nog niet exact overgetypt!")

                            # TYPEN
                            elif sub_modus == "Typen":
                                t_gram = st.selectbox("1. Grammatica:", ["", "Futurum Actief/Medium", "Aoristus Actief/Medium", "Aoristus Passief", "Perfectum Actief", "Perfectum Medium/Passief"])
                                t_prae = st.text_input("2. Praesens bronwoord:", key="in_tp_p")
                                t_bete = st.text_input("3. Betekenis bronwoord:", key="in_tp_b")
                                
                                if st.button("Controleer Antwoord", type="primary"):
                                    registreer_oefening()
                                    ok_g = (t_gram == correct_gram)
                                    ok_p = (normaliseer_accent(naar_grieks_transliteratie(t_prae)) == normaliseer_accent(correct_praesens))
                                    ok_b = check_betekenis(t_bete, correct_betekenis)
                                    
                                    if ok_g and ok_p and ok_b:
                                        if st.session_state.stam_fouten == 0 and vid not in st.session_state.gestrafte_woorden_stam:
                                            st.session_state.stam_stats[vid]['g'] += 1; st.session_state.stam_stats[vid]['streak'] += 1
                                            
                                        s_msg = f"✓ Goed! {fout_msg}\n\n{uitleg_regel}"
                                        if vid in st.session_state.gestrafte_woorden_stam: s_msg += "\n\n*(Geen streak-punten wegens eerdere fout)*"
                                        st.session_state.stam_feedback = {"type": "success", "msg": s_msg}
                                        trigger_save(); laad_volgend_stam_woord(); st.rerun()
                                    else:
                                        st.session_state.stam_fouten += 1
                                        if huidige_streak >= 16 or st.session_state.stam_fouten >= 2:
                                            st.session_state.stam_stats[vid]['streak'] = max(0, huidige_streak - 2)
                                            st.session_state.gestrafte_woorden_stam.add(vid)
                                            st.session_state.stam_sessie_lijst.insert(0, (huidig, 'overtik'))
                                            st.session_state.stam_sessie_lijst.append((huidig, sub_modus))
                                            st.session_state.stam_feedback = {"type": "error", "msg": f"✗ Fout. Het was: {fout_msg}.\n\n{uitleg_regel}"}
                                            trigger_save(); laad_volgend_stam_woord(); st.rerun()
                                        else:
                                            st.session_state.stam_stats[vid]['f'] += 1 
                                            st.session_state.stam_feedback = {"type": "warning", "msg": f"Bijna! Probeer het nog eens.\n\n{uitleg_regel}"}
                                        st.rerun()

                            # MC OVERHORING
                            else: 
                                if not st.session_state.stam_opties_gram:
                                    afleiders_g = [g for g in ["Futurum Actief/Medium", "Aoristus Actief/Medium", "Aoristus Passief", "Perfectum Actief", "Perfectum Medium/Passief"] if g != correct_gram]
                                    st.session_state.stam_opties_gram = [correct_gram] + random.sample(afleiders_g, 3)
                                    random.shuffle(st.session_state.stam_opties_gram)
                                    
                                    correct_p = f"{correct_praesens} — {correct_betekenis}"
                                    afleiders_p = []
                                    bestaande_b = {correct_betekenis}
                                    ww_pool = [w for w in stamtijden_db if w['praesens'] != correct_praesens]
                                    random.shuffle(ww_pool)
                                    for w in ww_pool:
                                        if w['betekenis'] not in bestaande_b:
                                            afleiders_p.append(f"{w['praesens']} — {w['betekenis']}"); bestaande_b.add(w['betekenis'])
                                        if len(afleiders_p) >= 3: break
                                    st.session_state.stam_opties_praesens = [correct_p] + afleiders_p
                                    random.shuffle(st.session_state.stam_opties_praesens)

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
                                            if st.session_state.stam_fouten == 0 and vid not in st.session_state.gestrafte_woorden_stam:
                                                st.session_state.stam_stats[vid]['g'] += 1; st.session_state.stam_stats[vid]['streak'] += 1
                                            s_msg = f"✓ Goed! {fout_msg}\n\n{uitleg_regel}"
                                            if vid in st.session_state.gestrafte_woorden_stam: s_msg += "\n\n*(Geen streak-punten wegens eerdere fout)*"
                                            st.session_state.stam_feedback = {"type": "success", "msg": s_msg}
                                            trigger_save(); laad_volgend_stam_woord(); st.rerun()
                                        else:
                                            st.session_state.stam_fouten += 1
                                            if huidige_streak >= 16 or st.session_state.stam_fouten >= 2:
                                                st.session_state.stam_stats[vid]['streak'] = max(0, huidige_streak - 2)
                                                st.session_state.gestrafte_woorden_stam.add(vid)
                                                st.session_state.stam_sessie_lijst.insert(0, (huidig, 'overtik'))
                                                st.session_state.stam_sessie_lijst.append((huidig, sub_modus))
                                                st.session_state.stam_feedback = {"type": "error", "msg": f"✗ Fout. Het was: {fout_msg}.\n\n{uitleg_regel}"}
                                                trigger_save(); laad_volgend_stam_woord(); st.rerun()
                                            else:
                                                st.session_state.stam_stats[vid]['f'] += 1 
                                                st.session_state.stam_feedback = {"type": "warning", "msg": f"Eén van je keuzes is onjuist!\n\n{uitleg_regel}"}
                                            st.rerun()

                            if sub_modus != 'overtik':
                                st.write("---")
                                fn = 'Nieuw' if huidige_streak==0 else ('In Training' if huidige_streak<=15 else ('Beheerst' if huidige_streak<=29 else 'Mastery'))
                                st.caption(f"Fase: {fn} | Autonome Stamtijd-Streak: {huidige_streak} | Goed/Fout: {st.session_state.stam_stats[vid].get('g',0)}/{st.session_state.stam_stats[vid].get('f',0)}")

        # ==========================================
        # TAB 6: STRUCTUURWOORDEN
        # ==========================================
        with menu[5]: 
            struct_db = laad_structuurwoorden_db()
            if not struct_db: st.warning("Bestand 'structuurwoorden.json' ontbreekt.")
            else:
                st.subheader("🧱 Structuurwoorden Herkennen")
                c1, c2 = st.columns([1, 2])
                with c1:
                    struct_modus = st.radio("Modus:", ["1. MC", "2. Mix (MC + Typen)", "3. Typen"], key="struct_modus_radio")
                    if st.button("Start Sessie", key="btn_start_struct"):
                        st.session_state.gestrafte_woorden_struct = set() # Reset de strafbank
                        doel_vormen = []
                        for w in struct_db:
                            vid = w['grieks']
                            stats = st.session_state.struct_stats.get(vid, {'g': 0, 'f': 0, 'streak': 0})
                            w['score_goed'] = stats['g']; w['score_fout'] = stats['f']; w['streak'] = stats['streak']; w['vid'] = vid
                            doel_vormen.append(w)
                        
                        if doel_vormen:
                            sampled = kies_gefaseerde_oefensessie(doel_vormen, module='struct')
                            modus_id = str(struct_modus[0])
                            if modus_id == "2":
                                mc_deel = [(v, "MC") for v in sampled]
                                typ_deel = [(v, "Typen") for v in sampled]
                                st.session_state.struct_sessie_lijst = mc_deel + typ_deel
                            elif modus_id == "3": st.session_state.struct_sessie_lijst = [(v, "Typen") for v in sampled]
                            else: st.session_state.struct_sessie_lijst = [(v, "MC") for v in sampled]
                                
                            laad_volgend_struct_woord(); st.rerun()

                with c2:
                    if st.session_state.struct_huidig:
                        huidig = st.session_state.struct_huidig
                        sub_modus = st.session_state.struct_sub_modus
                        vid = huidig['vid']
                        if vid not in st.session_state.struct_stats: st.session_state.struct_stats[vid] = {'g': 0, 'f': 0, 'streak': 0}
                        
                        if st.session_state.struct_feedback:
                            if st.session_state.struct_feedback["type"] == "success": st.success(st.session_state.struct_feedback["msg"])
                            elif st.session_state.struct_feedback["type"] == "warning": st.warning(st.session_state.struct_feedback["msg"])
                            else: st.error(st.session_state.struct_feedback["msg"])
                            st.session_state.struct_feedback = None 

                        st.markdown(f"<div class='grieks-woord'>{huidig['grieks']}</div>", unsafe_allow_html=True)
                        st.caption("Identificeer dit structuurwoord.")
                        
                        correct_cat = huidig['categorie']
                        correct_eig = huidig['eigenschap']
                        correct_bet = huidig['betekenis']
                        fout_msg_volledig = f"**{huidig['grieks']}** — {correct_cat} ({correct_eig}) — **{correct_bet}**"
                        
                        alle_cats = list(set([w['categorie'] for w in struct_db]))
                        
                        if sub_modus == 'overtik':
                            st.warning("⚠️ Overtikken: Je had dit woord fout. Kies de juiste gegevens.")
                            st.info(f"Het juiste antwoord is: {fout_msg_volledig}")
                            forceer_focus()
                            with st.form("form_struct_overtik", clear_on_submit=True):
                                p_cat = st.selectbox("1. Categorie:", [""] + alle_cats)
                                p_eig = st.text_input("2. Eigenschap/Naamval (exact overtypen):")
                                if st.form_submit_button("Bevestig"):
                                    registreer_oefening()
                                    if p_cat == correct_cat and p_eig.lower().strip() == correct_eig.lower().strip():
                                        st.session_state.struct_feedback = {"type": "success", "msg": "Genoteerd! Komt straks terug."}
                                        trigger_save(); laad_volgend_struct_woord(); st.rerun()
                                    else:
                                        st.error("Niet correct overgenomen.")

                        elif sub_modus == "Typen":
                            gekozen_cat = st.selectbox("1. Categorie:", [""] + alle_cats, key="dyn_cat")
                            forceer_focus()
                            with st.form("form_struct_typen", clear_on_submit=True):
                                c_eig, c_bet = st.columns(2)
                                with c_eig: 
                                    gefilterde_eigs = list(set([w['eigenschap'] for w in struct_db if w['categorie'] == gekozen_cat])) if gekozen_cat else []
                                    p_eig = st.selectbox("2. Eigenschap/Naamval", [""] + gefilterde_eigs)
                                with c_bet: 
                                    p_bet = st.text_input("3. Betekenis:")
                                
                                if st.form_submit_button("Check Antwoord"):
                                    registreer_oefening()
                                    is_cat_correct = (gekozen_cat == correct_cat)
                                    is_eig_correct = (p_eig == correct_eig)
                                    is_bet_correct = check_betekenis(p_bet, correct_bet)
                                    
                                    if is_cat_correct and is_eig_correct and is_bet_correct:
                                        if st.session_state.struct_fouten == 0:
                                            if vid not in st.session_state.gestrafte_woorden_struct:
                                                st.session_state.struct_stats[vid]['g'] += 1; st.session_state.struct_stats[vid]['streak'] += 1
                                        
                                        success_msg = f"✓ Goed! {fout_msg_volledig}"
                                        if vid in st.session_state.gestrafte_woorden_struct:
                                            success_msg += " *(Maar wegens je eerdere fout levert dit geen streak-punten op)*"
                                        st.session_state.struct_feedback = {"type": "success", "msg": success_msg}
                                        
                                        trigger_save(); laad_volgend_struct_woord(); st.rerun()
                                    else:
                                        st.session_state.struct_fouten += 1
                                        huidige_streak = st.session_state.struct_stats[vid]['streak']
                                        
                                        if huidige_streak >= 16 or st.session_state.struct_fouten >= 2:
                                            st.session_state.struct_stats[vid]['streak'] = max(0, huidige_streak - 2)
                                            st.session_state.gestrafte_woorden_struct.add(vid)
                                            st.session_state.struct_sessie_lijst.insert(0, (huidig, 'overtik'))
                                            st.session_state.struct_sessie_lijst.append((huidig, sub_modus))
                                            
                                            jouw_inv = f"{gekozen_cat} | {p_eig} | {p_bet}"
                                            st.session_state.struct_feedback = {"type": "error", "msg": f"✗ Helaas. Jij dacht: *{jouw_inv}*. Het was: {fout_msg_volledig}."}
                                            trigger_save(); laad_volgend_struct_woord(); st.rerun()
                                        else:
                                            st.session_state.struct_stats[vid]['f'] += 1 # Freeze
                                            st.session_state.struct_feedback = {"type": "warning", "msg": "Niet helemaal juist. Probeer het nog eens!"}
                                        st.rerun()
                        else: # PARTIËLE MC FEEDBACK
                            if not st.session_state.struct_opties_cat:
                                afleiders_c = [c for c in alle_cats if c != correct_cat]
                                st.session_state.struct_opties_cat = [correct_cat] + random.sample(afleiders_c, min(3, len(afleiders_c)))
                                random.shuffle(st.session_state.struct_opties_cat)
                                
                                alle_eigs = list(set([w['eigenschap'] for w in struct_db]))
                                afleiders_e = [e for e in alle_eigs if e != correct_eig]
                                st.session_state.struct_opties_eig = [correct_eig] + random.sample(afleiders_e, min(3, len(afleiders_e)))
                                random.shuffle(st.session_state.struct_opties_eig)
                                
                                afleiders_b = []
                                bestaande_b = {correct_bet}
                                str_pool = [w for w in struct_db if w['betekenis'] != correct_bet]
                                random.shuffle(str_pool)
                                for w in str_pool:
                                    if w['betekenis'] not in bestaande_b:
                                        afleiders_b.append(w['betekenis']); bestaande_b.add(w['betekenis'])
                                    if len(afleiders_b) >= 3: break
                                st.session_state.struct_opties_bet = [correct_bet] + afleiders_b
                                random.shuffle(st.session_state.struct_opties_bet)
                                
                            with st.form("form_struct_mc"):
                                if st.session_state.struct_mc_solved["cat"]:
                                    st.success(f"✓ Categorie: {correct_cat}"); keuze_cat = correct_cat
                                else: keuze_cat = st.radio("1. Categorie:", st.session_state.struct_opties_cat, index=None)
                                
                                if st.session_state.struct_mc_solved["eig"]:
                                    st.success(f"✓ Eigenschap: {correct_eig}"); keuze_eig = correct_eig
                                else: keuze_eig = st.radio("2. Eigenschap / Naamval:", st.session_state.struct_opties_eig, index=None)
                                
                                if st.session_state.struct_mc_solved["bet"]:
                                    st.success(f"✓ Betekenis: {correct_bet}"); keuze_bet = correct_bet
                                else: keuze_bet = st.radio("3. Betekenis:", st.session_state.struct_opties_bet, index=None)
                                
                                if st.form_submit_button("Check Antwoord"):
                                    registreer_oefening()
                                    is_cat_correct = (keuze_cat == correct_cat)
                                    is_eig_correct = (keuze_eig == correct_eig)
                                    is_bet_correct = (keuze_bet == correct_bet)
                                    
                                    if is_cat_correct and not st.session_state.struct_mc_solved["cat"]: st.session_state.struct_mc_solved["cat"] = True
                                    if is_eig_correct and not st.session_state.struct_mc_solved["eig"]: st.session_state.struct_mc_solved["eig"] = True
                                    if is_bet_correct and not st.session_state.struct_mc_solved["bet"]: st.session_state.struct_mc_solved["bet"] = True
                                    
                                    if st.session_state.struct_mc_solved["cat"] and st.session_state.struct_mc_solved["eig"] and st.session_state.struct_mc_solved["bet"]:
                                        if st.session_state.struct_fouten == 0:
                                            if vid not in st.session_state.gestrafte_woorden_struct:
                                                st.session_state.struct_stats[vid]['g'] += 1; st.session_state.struct_stats[vid]['streak'] += 1
                                        
                                        success_msg = f"✓ Goed! {fout_msg_volledig}"
                                        if vid in st.session_state.gestrafte_woorden_struct:
                                            success_msg += " *(Maar wegens je eerdere fout levert dit geen streak-punten op)*"
                                        st.session_state.struct_feedback = {"type": "success", "msg": success_msg}
                                        
                                        trigger_save(); laad_volgend_struct_woord(); st.rerun()
                                    else:
                                        st.session_state.struct_fouten += 1
                                        huidige_streak = st.session_state.struct_stats[vid]['streak']
                                        
                                        if huidige_streak >= 16 or st.session_state.struct_fouten >= 2:
                                            st.session_state.struct_stats[vid]['streak'] = max(0, huidige_streak - 2)
                                            st.session_state.gestrafte_woorden_struct.add(vid)
                                            st.session_state.struct_sessie_lijst.insert(0, (huidig, 'overtik'))
                                            st.session_state.struct_sessie_lijst.append((huidig, sub_modus))
                                            
                                            jouw_inv = f"{keuze_cat} | {keuze_eig} | {keuze_bet}"
                                            st.session_state.struct_feedback = {"type": "error", "msg": f"✗ Helaas. Jij dacht: *{jouw_inv}*. Het was: {fout_msg_volledig}."}
                                            trigger_save(); laad_volgend_struct_woord(); st.rerun()
                                        else:
                                            st.session_state.struct_stats[vid]['f'] += 1 # Freeze
                                            st.session_state.struct_feedback = {"type": "warning", "msg": "De goede delen zijn vastgezet. Probeer de rest opnieuw!"}
                                        st.rerun()

                        if sub_modus != 'overtik':
                            st.write("---")
                            fase_naam = 'Nieuw' if st.session_state.struct_stats[vid].get('streak', 0)==0 else ('In Training' if st.session_state.struct_stats[vid].get('streak', 0)<=15 else ('Beheerst' if st.session_state.struct_stats[vid].get('streak', 0)<=29 else 'Mastery'))
                            st.caption(f"Fase: {fase_naam} | Universele Streak: {st.session_state.struct_stats[vid].get('streak', 0)} | Goed/Fout: {st.session_state.struct_stats[vid].get('g', 0)}/{st.session_state.struct_stats[vid].get('f', 0)}")

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
                lees_modus = st.radio("Hoe wil je de tekst kiezen?", ["Kies specifiek(e) vers(zen)", "Scavenger Hunt (Willekeurig)"], horizontal=True)
                
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
                else:
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
                            top_picks = passende[:min(10, len(passende))]; gekozen_vers = random.choice(top_picks)
                            st.session_state.huidig_vers = gekozen_vers[1]; st.session_state.huidige_vers_referentie = gekozen_vers[0]
                            st.session_state.geziene_verzen.append(gekozen_vers[0]); st.session_state.geziene_verzen = st.session_state.geziene_verzen[-100:]

                st.write("---")

                if st.session_state.huidig_vers:
                    st.markdown(f"### 📖 {st.session_state.huidige_vers_referentie}")
                    html_zin = ""; oefen_woorden = []
                    
                    for w in st.session_state.huidig_vers:
                        tooltip = f"{w['vertaling_bsb']} ({w['parsing_info']})"
                        tooltip = tooltip.replace("'", "&#39;").replace('"', "&quot;")
                        
                        extra_style = ""
                        if kleur_naamvallen:
                            if "Nom" in w['parsing_info']: extra_style += "color: #33ccff;"
                            elif "Gen" in w['parsing_info']: extra_style += "color: #28a745;"
                            elif "Dat" in w['parsing_info']: extra_style += "color: #6f42c1;"
                            elif "Acc" in w['parsing_info']: extra_style += "color: #dc3545;"
                            elif "Voc" in w['parsing_info']: extra_style += "color: #fd7e14;"
                        
                        if kleur_voegwoorden and ("Voegwoord" in w['parsing_info'] or "Conjunction" in w['parsing_info']):
                            extra_style += "background-color: #ffd700; color: #000; padding: 0 4px; border-radius: 4px;"

                        clean_w = normaliseer_accent(w['grieks'])
                        is_stam = clean_w in actieve_stam_vormen
                        is_bekend = w.get('strong') and str(w['strong']) in actieve_strongs
                        
                        if is_stam and kleur_stamtijden: css_class = "woord-stamtijd"
                        elif is_bekend: css_class = "woord-bekend"
                        else: css_class = "woord-onbekend"

                        if css_class in ["woord-bekend", "woord-stamtijd"]:
                            if "1." in tekst_modus:
                                if is_bekend:
                                    basis_nederlands = actieve_strongs[str(w['strong'])].get('nederlands', '')
                                    les_nr = actieve_strongs[str(w['strong'])].get('les', '?')
                                    hover_text = f"Les {les_nr}: {basis_nederlands} | {tooltip}"
                                else: hover_text = f"{actieve_stam_vormen[clean_w]['betekenis']} | {tooltip}"
                            else: hover_text = "Oefenwoord! Vul de gegevens hieronder in."
                            
                            hover_text = hover_text.replace("'", "&#39;").replace('"', "&quot;")
                            html_zin += f"<span class='{css_class} mobile-tooltip' tabindex='0' style='{extra_style}'>{w['grieks']}<span class='tooltiptext'>{hover_text}</span></span>{w['interpunctie']} "
                            oef_dict = w.copy()
                            oef_dict['is_stamtijd'] = is_stam
                            oef_dict['stam_info'] = actieve_stam_vormen[clean_w] if is_stam else None
                            oefen_woorden.append(oef_dict)
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
                                    with c_gram:
                                        p_gram = st.selectbox("Tijd & Diathese", ["", "Futurum Actief/Medium", "Aoristus Actief/Medium", "Aoristus Passief", "Perfectum Actief", "Perfectum Medium/Passief"], key=f"s_g_{idx}")
                                        p_praesens = st.text_input("Praesens:", key=f"s_p_{idx}")
                                    with c_bet: p_betekenis = st.text_input("Betekenis:", key=f"s_b_{idx}")
                                    
                                    if st.form_submit_button("Check Stamtijd"):
                                        registreer_oefening()
                                        is_gram_correct = (p_gram == stam_data['tijd_diathese'])
                                        is_praesens_correct = (normaliseer_accent(naar_grieks_transliteratie(p_praesens)) == normaliseer_accent(stam_data['praesens']))
                                        is_bet_correct = check_betekenis(p_betekenis, stam_data['betekenis'])
                                        if is_gram_correct and is_praesens_correct and is_bet_correct: st.success(f"✓ Goed! **{w['grieks']}** is de {stam_data['tijd_diathese']} van {stam_data['praesens']}.")
                                        else: st.error(f"✗ Onjuist. Het is de **{stam_data['tijd_diathese']}** van **{stam_data['praesens']}** (Betekenis: **{stam_data['betekenis']}**).")
                            else:
                                basis = actieve_strongs[str(w['strong'])]
                                in_scope = True
                                norm_basis = normaliseer_accent(basis['grieks'])
                                is_ww = "Werkwoord" in w['parsing_info'] or basis.get('woordsoort') == 'ww'
                                
                                if master_niveau == "Grieks 1":
                                    if is_ww:
                                        is_actief = "Actief" in w['parsing_info']
                                        is_ptc_conj_opt = any(x in w['parsing_info'] for x in ["Participium", "Conjunctivus", "Optativus"])
                                        in_scope = (norm_basis == "ειμι") or (is_actief and not is_ptc_conj_opt)
                                    else: in_scope = norm_basis.endswith(('ος', 'ον', 'α', 'η', 'ω', 'υ', 'ουτος', 'αυτη', 'τουτο')) or norm_basis in ['ο', 'η', 'το', 'εγω', 'συ']
                                elif master_niveau == "Grieks 2":
                                    if is_ww: in_scope = not any(x in w['parsing_info'] for x in ["Conjunctivus", "Optativus"])
                                    if norm_basis.endswith('μι') and norm_basis != "ειμι": in_scope = False

                                if "4." in tekst_modus: st.markdown(f"**{w['grieks']}**")
                                else: st.markdown(f"**{w['grieks']}** (Basis: {basis['grieks']})")
                                
                                if "2." in tekst_modus: 
                                    if f"mc_opties_{idx}" not in st.session_state or st.session_state.get(f"mc_vers_{idx}") != st.session_state.huidige_vers_referentie:
                                        random.seed(st.session_state.huidige_vers_referentie + str(idx))
                                        afleiders = list(set([i['nederlands'] for i in st.session_state.data if i['nederlands'] != basis['nederlands']]))
                                        opties = [basis['nederlands']] + random.sample(afleiders, min(3, len(afleiders)))
                                        random.shuffle(opties); random.seed()
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
                                            if check_betekenis(inp, basis['nederlands']): 
                                                basis['streak'] = int(basis.get('streak', 0)) + 3; basis['score_goed'] = int(basis.get('score_goed', 0)) + 1; trigger_save()
                                                st.success(f"✓ Goed! **{w['grieks']}** = {basis['nederlands']} ({w['parsing_info']})")
                                            else: 
                                                basis['streak'] = max(0, int(basis.get('streak', 0)) - 2); basis['score_fout'] = int(basis.get('score_fout', 0)) + 1; trigger_save()
                                                st.error(f"✗ Fout. Het is: {basis['nederlands']}")
                                            
                                elif "4." in tekst_modus:
                                    if not in_scope: st.success(f"*(Buiten scope voor {master_niveau})* **{w['grieks']}** = {basis['nederlands']} ({w['parsing_info']})")
                                    else:
                                        p_soort = st.selectbox("Woordsoort", ["", "Zelfst. nw.", "Werkwoord", "Bijv. nw.", "Lidwoord", "Voornaamwoord", "Overig"], key=f"soort_{idx}")
                                        t_inp = st.text_input("Woordenboekvertaling:", key=f"bet_{idx}")
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
                                            betekenis_ok = check_betekenis(t_inp, basis['nederlands'])
                                            parsing_ok = check_bijbel_parsing_uitgebreid(p_soort, p_naam, p_get, p_ges, p_tijd, p_wijs, p_diat, p_pers, w['parsing_info'])
                                            if betekenis_ok and parsing_ok:
                                                basis['streak'] = int(basis.get('streak', 0)) + 3; basis['score_goed'] = int(basis.get('score_goed', 0)) + 1; trigger_save()
                                                st.success(f"✓ Volledig correct! ({w['parsing_info']})")
                                            else:
                                                basis['streak'] = max(0, int(basis.get('streak', 0)) - 2); basis['score_fout'] = int(basis.get('score_fout', 0)) + 1; trigger_save()
                                                st.error(f"✗ Onjuist. Officiële data: {w['parsing_info']} | Betekenis: {basis['nederlands']}")
                                                
                    st.write("---")
                    st.write("### ✍️ Zinsvertaling")
                    user_vertaling = st.text_area("Vertaal de hele zin naar het Nederlands:")
                    if st.button("Toon officiële vertaling"):
                        officiële_zin = " ".join([w['vertaling_bsb'] for w in st.session_state.huidig_vers])
                        st.success(f"**Officiële Engelse zinsvertaling (BSB):** {officiële_zin}")
                        
        # ==========================================
        # TAB 8: UITLEG & HULP (Masterclass Bijsluiter)
        # ==========================================
        with menu[7]:
            st.subheader("ℹ️ Handboek & Achterliggende Logica")
            
            st.markdown("### 📱 De App installeren als PWA (Beginscherm)")
            st.info("Je kunt deze webapplicatie opslaan op je telefoon. Hij opent dan razendsnel in full-screen zonder afleidende adresbalk.")
            st.markdown("* **iPhone (Safari):** Tik onderin op de deel-knop (vierkantje met pijltje omhoog) $\\rightarrow$ *'Zet op beginscherm'*\n* **Android (Chrome):** Tik rechtsboven op de drie puntjes $\\rightarrow$ *'Toevoegen aan startscherm'*")
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
              1. *Labialen (π, β, φ):* versmelten met σ tot een **ψ** (*βλέπω $\\rightarrow$ βλέψω*).
              2. *Gutturalen (κ, γ, χ):* versmelten met σ tot een **ξ** (*ἄγω $\\rightarrow$ ἄξω*).
              3. *Dentalen (τ, δ, θ, ζ):* vallen simpelweg weg voor de σ (*πείθω $\\rightarrow$ πείσω*).
              4. *Contracta (α, ε, ο):* de stamklinker ondergaat compensatorische rekking (*ποιέω $\\rightarrow$ ποιήσω*).
              5. *Liquidae (λ, μ, ν, ρ):* haten de sigma en trekken samen tot een circumflexus (*μένω $\\rightarrow$ μενῶ*).

            ---
            *Ontwikkeld voor theologische exegese aan de PThU. Vragen of suggesties? Mail naar:* **jtimmer@students.pthu.nl**
            """)

if __name__ == "__main__":
    main()
