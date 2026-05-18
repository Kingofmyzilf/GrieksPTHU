import streamlit as st
from streamlit_gsheets import GSheetsConnection
import json
import random
import re
import math
import pandas as pd
import matplotlib.pyplot as plt
import os
import unicodedata

# --- CONFIGURATIE ---
st.set_page_config(page_title="Grieks Cloud Tutor", layout="wide")
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("Kan niet verbinden met Google Sheets. Controleer je internetverbinding.")

st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 10px; height: 3em; font-weight: bold; }
    .stTextInput>div>div>input { font-size: 20px; text-align: center; }
    .grieks-woord { font-size: 50px; font-weight: bold; color: #33ccff; text-align: center; padding: 20px; }
    .grieks-zin { font-size: 28px; line-height: 1.8; color: #ffffff; padding: 20px; background-color: #1e1e1e; border-radius: 10px; }
    .woord-bekend { color: #00ffff; font-weight: bold; border-bottom: 2px solid #00ffff; cursor: help; padding: 0 4px; }
    .woord-stamtijd { color: #d63384; font-weight: bold; border-bottom: 2px solid #d63384; cursor: help; padding: 0 4px; }
    .woord-onbekend { color: #aaaaaa; cursor: help; padding: 0 2px; }
    .grid-label { font-weight: bold; color: #33ccff; margin-bottom: 5px; }
    .rooster-input>div>div>input { font-size: 16px; padding: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- LOGICA & TRANSLITERATIE ---

def veilig_les_nummer(item):
    try: return int(item.get('les', 1))
    except: return 1

def naar_grieks_transliteratie(tekst):
    mapping = {
        'a': 'α', 'b': 'β', 'g': 'γ', 'd': 'δ', 'e': 'ε', 'z': 'ζ', 'h': 'η', 'q': 'θ',
        'i': 'ι', 'k': 'κ', 'l': 'λ', 'm': 'μ', 'n': 'ν', 'c': 'ξ', 'o': 'ο', 'p': 'π',
        'r': 'ρ', 's': 'σ', 't': 'τ', 'u': 'υ', 'f': 'φ', 'x': 'χ', 'y': 'ψ', 'w': 'ω'
    }
    res = ""
    tekst = str(tekst).lower().strip()
    for char in tekst: res += mapping.get(char, char)
    if res.endswith('σ'): res = res[:-1] + 'ς'
    return res

def normaliseer_accent(woord):
    if pd.notna(woord) and str(woord).strip() != "":
        w = str(woord).strip().lower()
        w = ''.join(c for c in unicodedata.normalize('NFD', w) if unicodedata.category(c) != 'Mn')
        w = w.replace('a', 'α').replace('e', 'ε').replace('i', 'ι').replace('o', 'ο').replace('u', 'υ')
        w = w.replace('(ν)', '').replace('(ν', '').replace('ν)', '')
        return w.strip()
    return ""

def check_betekenis(ingevuld, correcte_zin):
    """Zeer robuuste nakijk-functie die synoniemen, komma's, puntkomma's en haakjes snapt."""
    ingevuld = str(ingevuld).lower().strip()
    correcte_zin = str(correcte_zin).lower().strip()
    
    if not ingevuld: return False
    if ingevuld == correcte_zin: return True
    
    # 1. Ruwe delen (komma's en puntkomma's gesplitst)
    delen_ruw = [d.strip() for d in correcte_zin.replace(';', ',').split(',')]
    if ingevuld in delen_ruw: return True
    
    # 2. Haakjes en speciale tekens negeren (verwijder alles IN haakjes)
    schoon = re.sub(r'\(.*?\)', '', correcte_zin)
    schoon = re.sub(r'\[.*?\]', '', schoon)
    schoon = schoon.replace('=', '').replace('*', '').replace('+', '')
    delen_schoon = [d.strip() for d in schoon.replace(';', ',').split(',')]
    if ingevuld in [d for d in delen_schoon if d]: return True
    
    # 3. Haakjes negeren (maar inhoud BEHOUDEN) -> (weg)gaan wordt weggaan
    zonder = re.sub(r'[()\[\]]', '', correcte_zin).replace('=', '').replace('*', '').replace('+', '')
    delen_zonder = [d.strip() for d in zonder.replace(';', ',').split(',')]
    if ingevuld in [d for d in delen_zonder if d]: return True
    
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

# --- GEFASEERD LEREN ALGORITME ---
def krijg_streak(item, module, modus_id=None):
    if module == 'vocab':
        return int(item.get(f'streak_m{modus_id}', 0))
    else:
        return int(item.get('streak', 0))

def kies_gefaseerde_oefensessie(doel_lijst, module, modus_id=None, max_items=10, max_nieuw=3):
    nieuw, training, beheerst, mastery = [], [], [], []
    for item in doel_lijst:
        s = krijg_streak(item, module, modus_id)
        if s == 0: nieuw.append(item)
        elif 1 <= s <= 4: training.append(item)
        elif 5 <= s <= 19: beheerst.append(item)
        else: mastery.append(item)
    
    random.shuffle(nieuw)
    random.shuffle(training)
    random.shuffle(beheerst)
    random.shuffle(mastery)
    
    sessie = []
    ruimte_voor_training = max_items - min(len(nieuw), max_nieuw)
    sessie.extend(training[:ruimte_voor_training])
    
    ruimte_voor_nieuw = max_items - len(sessie)
    sessie.extend(nieuw[:min(ruimte_voor_nieuw, max_nieuw)])
    
    if len(sessie) < max_items: sessie.extend(beheerst[:max_items - len(sessie)])
    if len(sessie) < max_items: sessie.extend(mastery[:max_items - len(sessie)])
        
    random.shuffle(sessie)
    return sessie

def bereken_gewicht(item):
    gewicht = 1.0
    freq = int(item.get('frequentie_nt', 0))
    if freq > 0: gewicht += math.log10(freq + 1)
    gewicht += (int(item.get('score_fout', 0)) * 1.5)
    gewicht -= (int(item.get('score_goed', 0)) * 0.1)
    
    sm1, sm2, sm3, sm4 = int(item.get('streak_m1', 0)), int(item.get('streak_m2', 0)), int(item.get('streak_m3', 0)), int(item.get('streak_m4', 0))
    mastery_score = (sm1 * 0.5) + (sm2 * 1.0) + (sm3 * 1.5) + (sm4 * 2.0)
    gewicht -= (mastery_score * 0.2)
    
    gem_streak = (sm1 + sm2 + sm3 + sm4) / 4
    if sm4 >= 20 or gem_streak >= 20: gewicht *= 0.1
    return max(0.1, gewicht)

def bereken_gewicht_stam(item):
    gewicht = 1.0
    freq = int(item['basis'].get('frequentie', 0))
    if freq > 0: gewicht += math.log10(freq + 1)
    
    fouten = int(item.get('score_fout', 0))
    goed = int(item.get('score_goed', 0))
    streak = int(item.get('streak', 0))
    
    gewicht += (fouten * 1.5)
    gewicht -= (goed * 0.1)
    gewicht -= (streak * 2.0)
    
    if streak >= 10: gewicht *= 0.1
    return max(0.1, gewicht)

# --- DATABASE FUNCTIES ---
@st.cache_data
def laad_actief_beheersen_db():
    if os.path.exists("actief_beheersen.json"):
        try:
            with open("actief_beheersen.json", "r", encoding="utf-8") as f: return json.load(f)
        except Exception: pass
    return None

@st.cache_data
def laad_stamtijden_db():
    if os.path.exists("stamtijden.json"):
        try:
            with open("stamtijden.json", "r", encoding="utf-8") as f: return json.load(f)
        except Exception: pass
    return None

@st.cache_data
def laad_structuurwoorden_db():
    if os.path.exists("structuurwoorden.json"):
        try:
            with open("structuurwoorden.json", "r", encoding="utf-8") as f: return json.load(f)
        except Exception: pass
    return None

@st.cache_data
def laad_bijbel_db():
    bijbel = {}
    if os.path.exists("bijbel_nt.json"):
        try:
            with open("bijbel_nt.json", "r", encoding="utf-8") as f: bijbel = json.load(f)
        except: pass
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
        user_row = df[df['gebruikersnaam'] == naam]
        
        if os.path.exists("basis_woorden.json"):
            with open("basis_woorden.json", "r", encoding="utf-8") as f: basis = json.load(f)
        else:
            return None

        if user_row.empty:
            st.session_state.vocab_stats = {}
            st.session_state.gram_stats = {}
            st.session_state.stam_stats = {}
            st.session_state.struct_stats = {}
            df_andere = df[df['gebruikersnaam'] != naam]
            nieuwe_rij = pd.DataFrame([{'gebruikersnaam': naam, 'vocab_stats': '{}', 'gram_stats': '{}', 'stam_stats': '{}', 'struct_stats': '{}'}])
            conn.update(data=pd.concat([df_andere, nieuwe_rij], ignore_index=True))
        else:
            try: st.session_state.vocab_stats = json.loads(str(user_row.iloc[0].get('vocab_stats', '{}')))
            except: st.session_state.vocab_stats = {}
            try: st.session_state.gram_stats = json.loads(str(user_row.iloc[0].get('gram_stats', '{}')))
            except: st.session_state.gram_stats = {}
            try: st.session_state.stam_stats = json.loads(str(user_row.iloc[0].get('stam_stats', '{}')))
            except: st.session_state.stam_stats = {}
            try: st.session_state.struct_stats = json.loads(str(user_row.iloc[0].get('struct_stats', '{}')))
            except: st.session_state.struct_stats = {}
            
        for r in basis:
            stats = st.session_state.vocab_stats.get(r['grieks'], {'m1':0, 'm2':0, 'm3':0, 'm4':0, 'g':0, 'f':0})
            r['streak_m1'] = stats.get('m1', 0)
            r['streak_m2'] = stats.get('m2', 0)
            r['streak_m3'] = stats.get('m3', 0)
            r['streak_m4'] = stats.get('m4', 0)
            r['score_goed'] = stats.get('g', 0)
            r['score_fout'] = stats.get('f', 0)
        return basis
    except Exception as e:
        return None

def opslaan_naar_cloud():
    if not st.session_state.get('last_user'): return
    try:
        df = conn.read(ttl=0)
        if 'gebruikersnaam' not in df.columns: df['gebruikersnaam'] = ""
        df_andere = df[df['gebruikersnaam'] != st.session_state.last_user]
        
        v_json = json.dumps(st.session_state.get('vocab_stats', {}), ensure_ascii=False)
        g_json = json.dumps(st.session_state.get('gram_stats', {}), ensure_ascii=False)
        s_json = json.dumps(st.session_state.get('stam_stats', {}), ensure_ascii=False)
        str_json = json.dumps(st.session_state.get('struct_stats', {}), ensure_ascii=False)
        
        nieuwe_rij = pd.DataFrame([{
            'gebruikersnaam': st.session_state.last_user,
            'vocab_stats': v_json,
            'gram_stats': g_json,
            'stam_stats': s_json,
            'struct_stats': str_json
        }])
            
        conn.update(data=pd.concat([df_andere, nieuwe_rij], ignore_index=True))
    except Exception: pass

def trigger_save():
    if not st.session_state.get('last_user'): return
    for word in st.session_state.data:
        st.session_state.vocab_stats[word['grieks']] = {
            'm1': word.get('streak_m1', 0),
            'm2': word.get('streak_m2', 0),
            'm3': word.get('streak_m3', 0),
            'm4': word.get('streak_m4', 0),
            'g': word.get('score_goed', 0),
            'f': word.get('score_fout', 0)
        }
    opslaan_naar_cloud()

# --- SESSION STATE INITIALISATIE ---
for key in ['data', 'sessie_lijst', 'huidig_item', 'huidige_sub_modus', 'huidige_vorm_data', 'feedback', 
            'fouten_huidig_woord', 'huidige_opties', 'last_user',
            'huidig_vers', 'huidige_vers_referentie', 'geziene_verzen',
            'actief_flashcard_huidig', 'actief_nakijk_resultaten',
            'stam_sessie_lijst', 'stam_huidig', 'stam_sub_modus', 'stam_fouten', 'stam_feedback', 'stam_opties_gram', 'stam_opties_praesens', 'stam_mc_solved',
            'struct_sessie_lijst', 'struct_huidig', 'struct_sub_modus', 'struct_fouten', 'struct_feedback', 'struct_opties_cat', 'struct_opties_eig', 'struct_opties_bet', 'struct_mc_solved']:
    if key not in st.session_state: st.session_state[key] = None

if st.session_state.stam_sessie_lijst is None: st.session_state.stam_sessie_lijst = []
if st.session_state.struct_sessie_lijst is None: st.session_state.struct_sessie_lijst = []
if st.session_state.geziene_verzen is None: st.session_state.geziene_verzen = []
if 'vocab_stats' not in st.session_state: st.session_state.vocab_stats = {}
if 'gram_stats' not in st.session_state: st.session_state.gram_stats = {}
if 'stam_stats' not in st.session_state: st.session_state.stam_stats = {}
if 'struct_stats' not in st.session_state: st.session_state.struct_stats = {}

def laad_volgend_woord():
    if st.session_state.sessie_lijst:
        volgend = st.session_state.sessie_lijst.pop(0)
        st.session_state.huidig_item = volgend[0]
        st.session_state.huidige_sub_modus = volgend[1]
    else:
        st.session_state.huidig_item = None
        st.session_state.huidige_sub_modus = None
    st.session_state.fouten_huidig_woord = 0
    st.session_state.huidige_opties = [] 
    st.session_state.huidige_vorm_data = None

def laad_volgend_stam_woord():
    if st.session_state.stam_sessie_lijst:
        volgend = st.session_state.stam_sessie_lijst.pop(0)
        st.session_state.stam_huidig = volgend[0]
        st.session_state.stam_sub_modus = volgend[1]
    else:
        st.session_state.stam_huidig = None
        st.session_state.stam_sub_modus = None
    st.session_state.stam_fouten = 0
    st.session_state.stam_opties_gram = [] 
    st.session_state.stam_opties_praesens = []
    st.session_state.stam_mc_solved = {"gram": False, "praesens": False}

def laad_volgend_struct_woord():
    if st.session_state.struct_sessie_lijst:
        volgend = st.session_state.struct_sessie_lijst.pop(0)
        st.session_state.struct_huidig = volgend[0]
        st.session_state.struct_sub_modus = volgend[1]
    else:
        st.session_state.struct_huidig = None
        st.session_state.struct_sub_modus = None
    st.session_state.struct_fouten = 0
    st.session_state.struct_opties_cat = [] 
    st.session_state.struct_opties_eig = []
    st.session_state.struct_opties_bet = []
    st.session_state.struct_mc_solved = {"cat": False, "eig": False, "bet": False}


# ==========================================
# MAIN APP FUNCTIE
# ==========================================
def main():
    # --- SIDEBAR & LOGIN ---
    with st.sidebar:
        st.header("👤 Inloggen")
        user_input = st.text_input("Naam", key="user_login").strip()
        if user_input and (st.session_state.data is None or st.session_state.last_user != user_input):
            st.session_state.data = laad_gebruiker_data(user_input)
            st.session_state.last_user = user_input
        
        if st.session_state.data:
            if st.button("🚪 Uitloggen"):
                trigger_save()
                st.session_state.data = None; st.rerun()

    # --- HOOFDMENU ---
    if st.session_state.data:
        menu = st.tabs(["🚀 Woordenschat", "📖 Lijst", "📊 Voortgang", "🎓 Actief Beheersen", "⏳ Stamtijden", "🧱 Structuurwoorden", "📝 Leesteksten"])

        with menu[0]: # WOORDENSCHAT
            col1, col2 = st.columns([1, 2])
            with col1:
                modus = st.radio("Modus:", ["1. Leer", "2. MC", "3. Mix (MC + Typen)", "4. Typen"])
                keuze = st.selectbox("Oefening:", ["Lessen", "Mastery"])
                doel = []
                if keuze == "Lessen":
                    alle_lessen = sorted(list(set(veilig_les_nummer(i) for i in st.session_state.data)))
                    gekozen = st.multiselect("Kies lessen", alle_lessen)
                    doel = [word for word in st.session_state.data if veilig_les_nummer(word) in gekozen]
                elif keuze == "Mastery":
                    doel = [word for word in st.session_state.data if ((int(word.get('streak_m1',0))+int(word.get('streak_m2',0))+int(word.get('streak_m3',0))+int(word.get('streak_m4',0)))/4) >= 20]
                
                if st.button("Start Sessie"):
                    if doel:
                        modus_id = str(modus[0])
                        opslag_mod = "4" if modus_id == "4" else ("2" if modus_id == "2" else "3")
                        
                        sampled = kies_gefaseerde_oefensessie(doel, module='vocab', modus_id=opslag_mod, max_items=10, max_nieuw=3)
                        
                        st.session_state.modus_actief = modus_id
                        
                        if modus_id == "3":
                            st.session_state.sessie_lijst = [(w, random.choice(["3_mc", "3_typ"])) for w in sampled]
                        else:
                            st.session_state.sessie_lijst = [(w, modus_id) for w in sampled]
                        
                        laad_volgend_woord()
                        st.rerun()

            with col2:
                if st.session_state.huidig_item:
                    item = st.session_state.huidig_item
                    huidige_sub_modus = st.session_state.huidige_sub_modus
                    
                    opslag_modus = "4" if huidige_sub_modus in ["4", "3_typ"] else ("2" if huidige_sub_modus == "3_mc" else huidige_sub_modus)
                    act_streak_key = f"streak_m{opslag_modus}"
                    
                    sm1, sm2, sm3, sm4 = int(item.get('streak_m1', 0)), int(item.get('streak_m2', 0)), int(item.get('streak_m3', 0)), int(item.get('streak_m4', 0))
                    gem_streak = (sm1 + sm2 + sm3 + sm4) / 4
                    is_mastery = gem_streak >= 20 or sm4 >= 20
                    heeft_vormen = 'vormen_data' in item and isinstance(item['vormen_data'], list) and len(item['vormen_data']) > 0
                    
                    if st.session_state.huidige_vorm_data is None:
                        if is_mastery and heeft_vormen:
                            st.session_state.huidige_vorm_data = random.choice(item['vormen_data'])
                        else:
                            st.session_state.huidige_vorm_data = {"vorm": item.get('grieks', 'Onbekend'), "parsing": "basis"}

                    huidige_vorm = str(st.session_state.huidige_vorm_data.get('vorm', item.get('grieks')))
                    huidige_parsing = str(st.session_state.huidige_vorm_data.get('parsing', 'basis'))

                    if st.session_state.feedback:
                        if st.session_state.feedback["type"] == "success": st.success(st.session_state.feedback["msg"])
                        elif st.session_state.feedback["type"] == "warning": st.warning(st.session_state.feedback["msg"])
                        else: st.error(st.session_state.feedback["msg"])
                        st.session_state.feedback = None 

                    st.markdown(f"<div class='grieks-woord'>{huidige_vorm}</div>", unsafe_allow_html=True)
                    
                    if is_mastery and heeft_vormen and huidige_vorm != item.get('grieks'):
                        st.caption(f"🏆 Vormleer Modus. (Basiswoord: **{item.get('grieks')}**)")

                    if huidige_sub_modus == '1' or st.session_state.fouten_huidig_woord >= 1:
                        st.info(f"💡 {item.get('fonetisch', '')} | {item.get('anker', '')} {item.get('beeld', '')}")

                    correct_antw = str(item.get('nederlands', ''))
                    volledig_antwoord_str = f"**{huidige_vorm}** = {correct_antw}" + (f" ({huidige_parsing})" if is_mastery and heeft_vormen else "")
                    
                    # TYPEN MODUS
                    if huidige_sub_modus in ['4', '3_typ']:
                        with st.form(key=f"form_vocab_{item.get('grieks')}", clear_on_submit=True):
                            inp = st.text_input("Woordenboekvertaling:").lower().strip()
                            if is_mastery and heeft_vormen:
                                p_vorm = st.text_input("Vorm (bijv. nom ev m):").lower().strip()
                            else:
                                p_vorm = huidige_parsing.lower().strip()

                            if st.form_submit_button("Check Antwoord"):
                                betekenis_goed = check_betekenis(inp, correct_antw)
                                vorm_goed = (p_vorm == huidige_parsing.lower().strip())

                                if betekenis_goed and vorm_goed:
                                    if st.session_state.fouten_huidig_woord == 0:
                                        item[act_streak_key] = int(item.get(act_streak_key, 0)) + 1
                                        item['score_goed'] = int(item.get('score_goed', 0)) + 1
                                    st.session_state.feedback = {"type": "success", "msg": f"✓ Goed! {volledig_antwoord_str}"}
                                    trigger_save(); laad_volgend_woord(); st.rerun()
                                else:
                                    st.session_state.fouten_huidig_woord = int(st.session_state.fouten_huidig_woord) + 1
                                    if st.session_state.fouten_huidig_woord == 1:
                                        st.session_state.feedback = {"type": "warning", "msg": "Bijna! Bekijk de hint en probeer nog eens."}
                                    elif st.session_state.fouten_huidig_woord == 2:
                                        item[act_streak_key] = max(0, int(item.get(act_streak_key, 0)) - 2)
                                        item['score_fout'] = int(item.get('score_fout', 0)) + 1
                                        st.session_state.sessie_lijst.append((item, huidige_sub_modus))
                                        st.session_state.feedback = {"type": "error", "msg": f"✗ Fout. Het juiste antwoord is: {volledig_antwoord_str}. Hij komt later terug."}
                                        trigger_save()
                                        laad_volgend_woord()
                                    st.rerun()
                    
                    # MEERKEUZE MODUS
                    else:
                        correct_optie = f"{correct_antw} ({huidige_parsing})" if (is_mastery and heeft_vormen) else correct_antw
                        if not st.session_state.huidige_opties:
                            huidige_woordsoort = item.get('woordsoort', '')
                            afleiders = []
                            if is_mastery and heeft_vormen:
                                andere = [str(v.get('parsing', '')) for v in item.get('vormen_data', []) if str(v.get('parsing', '')) != str(huidige_parsing)]
                                if andere: afleiders = [f"{correct_antw} ({f})" for f in random.sample(andere, min(3, len(andere)))]
                            else:
                                zelfde_soort = [str(i.get('nederlands', '')) for i in st.session_state.data if i.get('grieks') != item.get('grieks') and i.get('woordsoort') == huidige_woordsoort]
                                alle_andere = [str(i.get('nederlands', '')) for i in st.session_state.data if i.get('grieks') != item.get('grieks')]
                                afleiders = zelfde_soort if len(set(zelfde_soort)) >= 3 else (zelfde_soort + alle_andere)
                            
                            opties = list(dict.fromkeys([str(a) for a in afleiders if a]))[:3] + [correct_optie]
                            st.session_state.huidige_opties = opties
                            random.shuffle(st.session_state.huidige_opties)
                        
                        cols = st.columns(2)
                        for idx, optie in enumerate(st.session_state.huidige_opties):
                            if cols[idx % 2].button(optie, key=f"btn_{idx}_{item.get('grieks')}"):
                                if optie == correct_optie:
                                    if st.session_state.fouten_huidig_woord == 0:
                                        item[act_streak_key] = int(item.get(act_streak_key, 0)) + 1
                                        item['score_goed'] = int(item.get('score_goed', 0)) + 1
                                    st.session_state.feedback = {"type": "success", "msg": f"✓ Juist! {volledig_antwoord_str}"}
                                    trigger_save(); laad_volgend_woord(); st.rerun()
                                else:
                                    st.session_state.fouten_huidig_woord = int(st.session_state.fouten_huidig_woord) + 1
                                    if st.session_state.fouten_huidig_woord == 1:
                                        st.session_state.feedback = {"type": "warning", "msg": "Niet helemaal juist. Bekijk de hint en probeer nog eens!"}
                                    elif st.session_state.fouten_huidig_woord == 2:
                                        item[act_streak_key] = max(0, int(item.get(act_streak_key, 0)) - 2)
                                        item['score_fout'] = int(item.get('score_fout', 0)) + 1
                                        st.session_state.sessie_lijst.append((item, huidige_sub_modus))
                                        st.session_state.feedback = {"type": "error", "msg": f"✗ Fout. Het juiste antwoord is: '{correct_optie}'. Hij komt later terug."}
                                        trigger_save()
                                        laad_volgend_woord()
                                    st.rerun()

                    st.write("---")
                    st.caption(f"Streak voor deze modus: {item.get(act_streak_key, 0)} | Totaal Goed/Fout: {item.get('score_goed', 0)} / {item.get('score_fout', 0)}")

        with menu[1]: # LIJST
            st.subheader("📖 Database & Lijsten")
            weergave = st.selectbox("Wat wil je bekijken?", ["Vocabulaire", "Actief Beheersen (Rijtjes)", "Stamtijden", "Structuurwoorden"])
            
            if weergave == "Vocabulaire" and st.session_state.data:
                alle_lessen = sorted(list(set(veilig_les_nummer(i) for i in st.session_state.data)))
                les_filter = st.selectbox("Bekijk les:", alle_lessen)
                df = pd.DataFrame([i for i in st.session_state.data if veilig_les_nummer(i) == les_filter])
                if not df.empty:
                    st.dataframe(df[[c for c in ['grieks', 'nederlands', 'streak_m1', 'streak_m2', 'streak_m3', 'streak_m4', 'score_goed', 'score_fout', 'woordsoort'] if c in df.columns]], use_container_width=True)
                    
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
                            stam_lijst.append({
                                "Les": w.get('les', 0),
                                "Praesens": w['praesens'],
                                "Tijd/Diathese": t_d,
                                "Vorm": vorm,
                                "Betekenis": w['betekenis'],
                                "Streak": s['streak'],
                                "Goed": s['g'],
                                "Fout": s['f']
                            })
                    st.dataframe(pd.DataFrame(stam_lijst), use_container_width=True)
                    
            elif weergave == "Structuurwoorden":
                struct_db = laad_structuurwoorden_db()
                if struct_db:
                    str_lijst = []
                    for w in struct_db:
                        s = st.session_state.struct_stats.get(w['grieks'], {'g': 0, 'f': 0, 'streak': 0})
                        str_lijst.append({
                            "Woord": w['grieks'],
                            "Categorie": w['categorie'],
                            "Eigenschap": w['eigenschap'],
                            "Betekenis": w['betekenis'],
                            "Streak": s['streak'],
                            "Goed": s['g'],
                            "Fout": s['f']
                        })
                    st.dataframe(pd.DataFrame(str_lijst), use_container_width=True)

        with menu[2]: # VOORTGANG
            st.subheader("📊 Persoonlijk Dashboard")
            
            stats_vocab = {'Nieuw': 0, 'In Training': 0, 'Beheerst': 0, 'Mastery': 0}
            tot_goed_v, tot_fout_v = 0, 0
            if st.session_state.data:
                for w in st.session_state.data:
                    sm1, sm2, sm3, sm4 = int(w.get('streak_m1',0)), int(w.get('streak_m2',0)), int(w.get('streak_m3',0)), int(w.get('streak_m4',0))
                    gem = (sm1+sm2+sm3+sm4)/4
                    tot_goed_v += int(w.get('score_goed', 0))
                    tot_fout_v += int(w.get('score_fout', 0))
                    if gem >= 20: stats_vocab['Mastery'] += 1
                    elif gem >= 5: stats_vocab['Beheerst'] += 1
                    elif gem >= 1: stats_vocab['In Training'] += 1
                    else: stats_vocab['Nieuw'] += 1

            stats_stam = {'Nieuw': 0, 'In Training': 0, 'Beheerst': 0, 'Mastery': 0}
            tot_goed_s, tot_fout_s = 0, 0
            stam_db = laad_stamtijden_db()
            if stam_db:
                for w in stam_db:
                    for t_d, vorm in w['stamtijden'].items():
                        vid = f"{w['praesens']}_{vorm}"
                        s = st.session_state.stam_stats.get(vid, {'g': 0, 'f': 0, 'streak': 0})
                        strk = s['streak']
                        tot_goed_s += s['g']
                        tot_fout_s += s['f']
                        if strk >= 20: stats_stam['Mastery'] += 1
                        elif strk >= 5: stats_stam['Beheerst'] += 1
                        elif strk >= 1: stats_stam['In Training'] += 1
                        else: stats_stam['Nieuw'] += 1

            stats_str = {'Nieuw': 0, 'In Training': 0, 'Beheerst': 0, 'Mastery': 0}
            tot_goed_st, tot_fout_st = 0, 0
            str_db = laad_structuurwoorden_db()
            if str_db:
                for w in str_db:
                    s = st.session_state.struct_stats.get(w['grieks'], {'g': 0, 'f': 0, 'streak': 0})
                    strk = s['streak']
                    tot_goed_st += s['g']
                    tot_fout_st += s['f']
                    if strk >= 20: stats_str['Mastery'] += 1
                    elif strk >= 5: stats_str['Beheerst'] += 1
                    elif strk >= 1: stats_str['In Training'] += 1
                    else: stats_str['Nieuw'] += 1

            c_met1, c_met2, c_met3 = st.columns(3)
            tot_g = tot_goed_v + tot_goed_s + tot_goed_st
            tot_f = tot_fout_v + tot_fout_s + tot_fout_st
            acc = int((tot_g / (tot_g + tot_f) * 100)) if (tot_g + tot_f) > 0 else 0
            
            c_met1.metric("Totale Accuratesse", f"{acc}%")
            c_met2.metric("Items op 'Mastery'", stats_vocab['Mastery'] + stats_stam['Mastery'] + stats_str['Mastery'])
            c_met3.metric("Totale Beoordelingen", tot_g + tot_f)
            
            st.write("---")
            st.markdown("### Fasering Leerlijnen")
            
            df_plot = pd.DataFrame({
                'Module': ['Vocabulaire', 'Stamtijden', 'Structuurwoorden'],
                'Nieuw (0)': [stats_vocab['Nieuw'], stats_stam['Nieuw'], stats_str['Nieuw']],
                'In Training (1-4)': [stats_vocab['In Training'], stats_stam['In Training'], stats_str['In Training']],
                'Beheerst (5-19)': [stats_vocab['Beheerst'], stats_stam['Beheerst'], stats_str['Beheerst']],
                'Mastery (20+)': [stats_vocab['Mastery'], stats_stam['Mastery'], stats_str['Mastery']]
            })
            
            fig, ax = plt.subplots(figsize=(10, 4))
            df_plot.set_index('Module').plot(kind='bar', stacked=True, color=['#e0e0e0', '#f6c23e', '#28a745', '#33ccff'], ax=ax)
            ax.set_ylabel("Aantal items")
            plt.xticks(rotation=0)
            st.pyplot(fig)

        with menu[3]: # ACTIEF BEHEERSEN
            actief_db = laad_actief_beheersen_db()
            if not actief_db:
                st.warning("Kan actief_beheersen.json niet vinden.")
            else:
                st.subheader("🎓 Actief Beheersen (Tentamentraining)")
                
                c1, c2, c3 = st.columns(3)
                with c1: 
                    niveau = st.selectbox("Niveau:", [n for n in actief_db.keys() if actief_db[n]])
                with c2: 
                    if niveau:
                        cat_opties = list(actief_db[niveau].keys())
                        categorie = st.selectbox("Categorie:", cat_opties)
                with c3:
                    if niveau and categorie:
                        subcat_opties = list(actief_db[niveau][categorie].keys())
                        subcat = st.selectbox("Rijtje/Paradigma:", subcat_opties)

                if niveau and categorie and subcat:
                    huidig_rijtje = actief_db[niveau][categorie][subcat]
                    
                    st.write("---")
                    oefen_modus = st.radio("Kies je Oefenmethode:", ["📝 Tentamen (Heel Rooster)", "🎯 Train Zwakke Plekken (Flashcards)"], horizontal=True)
                    st.write("---")
                    
                    st.info("ℹ️ Gebruik Bèta-code. Accenten worden automatisch genegeerd bij het nakijken.")

                    if oefen_modus == "📝 Tentamen (Heel Rooster)":
                        with st.form(key=f"form_tentamen_{niveau}_{categorie}_{subcat}"):
                            st.markdown(f"### {categorie} - {subcat}")
                            
                            cols = st.columns(3)
                            input_refs = {}
                            
                            for idx, item in enumerate(huidig_rijtje):
                                with cols[idx % 3]:
                                    st.markdown(f"<div class='grid-label'>{item['label']}</div>", unsafe_allow_html=True)
                                    input_refs[item['id']] = st.text_input("", key=f"inp_{item['id']}", label_visibility="collapsed")
                            
                            if st.form_submit_button("Nakijken"):
                                st.session_state.actief_nakijk_resultaten = {}
                                alles_goed = True
                                
                                for item in huidig_rijtje:
                                    ingevuld = naar_grieks_transliteratie(input_refs[item['id']])
                                    correct = normaliseer_accent(ingevuld) == normaliseer_accent(item['vorm'])
                                    
                                    if item['id'] not in st.session_state.gram_stats:
                                        st.session_state.gram_stats[item['id']] = {'goed': 0, 'fout': 0, 'streak': 0}
                                    
                                    if correct:
                                        st.session_state.gram_stats[item['id']]['goed'] += 1
                                        st.session_state.gram_stats[item['id']]['streak'] += 1
                                    else:
                                        st.session_state.gram_stats[item['id']]['fout'] += 1
                                        st.session_state.gram_stats[item['id']]['streak'] = 0
                                        alles_goed = False
                                    
                                    st.session_state.actief_nakijk_resultaten[item['id']] = {
                                        "ingevuld": ingevuld,
                                        "correct": correct,
                                        "antwoord": item['vorm']
                                    }
                                    
                                trigger_save()
                                if alles_goed:
                                    st.balloons()
                                    st.success("Uitstekend! Je hebt het hele rooster foutloos ingevuld.")
                                
                        if st.session_state.actief_nakijk_resultaten:
                            st.markdown("### Resultaten:")
                            r_cols = st.columns(3)
                            for idx, item in enumerate(huidig_rijtje):
                                res = st.session_state.actief_nakijk_resultaten.get(item['id'])
                                if res:
                                    with r_cols[idx % 3]:
                                        if res['correct']:
                                            st.success(f"**{item['label']}**: {res['ingevuld']} ✅")
                                        else:
                                            st.error(f"**{item['label']}**: ❌ Jouw antwoord: '{res['ingevuld']}'. Correct is: **{res['antwoord']}**")

                    elif oefen_modus == "🎯 Train Zwakke Plekken (Flashcards)":
                        st.write(f"Hier train je specifieke vormen uit **{subcat}** door elkaar.")
                        
                        if st.button("Nieuwe Vorm") or not st.session_state.get('actief_flashcard_huidig'):
                            weights = []
                            for item in huidig_rijtje:
                                stats = st.session_state.gram_stats.get(item['id'], {'goed': 0, 'fout': 0, 'streak': 0})
                                w = max(0.1, 1.0 + (stats['fout'] * 1.5) - (stats['streak'] * 0.4))
                                weights.append(w)
                            st.session_state.actief_flashcard_huidig = random.choices(huidig_rijtje, weights=weights, k=1)[0]
                        
                        huidig = st.session_state.actief_flashcard_huidig
                        if huidig:
                            st.markdown(f"<div class='grieks-woord' style='font-size: 30px;'>Geef de vorm voor: <b>{huidig['label']}</b></div>", unsafe_allow_html=True)
                            
                            with st.form(key=f"form_flash_{huidig['id']}"):
                                inp = st.text_input("Jouw antwoord (Bèta-code):")
                                if st.form_submit_button("Controleer"):
                                    if huidig['id'] not in st.session_state.gram_stats:
                                        st.session_state.gram_stats[huidig['id']] = {'goed': 0, 'fout': 0, 'streak': 0}
                                    
                                    ingevuld = naar_grieks_transliteratie(inp)
                                    if normaliseer_accent(ingevuld) == normaliseer_accent(huidig['vorm']):
                                        st.session_state.gram_stats[huidig['id']]['goed'] += 1
                                        st.session_state.gram_stats[huidig['id']]['streak'] += 1
                                        st.success(f"✓ Correct! **{huidig['vorm']}**")
                                        st.session_state.actief_flashcard_huidig = None
                                        trigger_save()
                                    else:
                                        st.session_state.gram_stats[huidig['id']]['fout'] += 1
                                        st.session_state.gram_stats[huidig['id']]['streak'] = 0
                                        st.error(f"✗ Onjuist. Het juiste antwoord is: **{huidig['vorm']}**")
                                        trigger_save()

        with menu[4]: # STAMTIJDEN
            stamtijden_db = laad_stamtijden_db()
            if not stamtijden_db:
                st.warning("Bestand 'stamtijden.json' ontbreekt.")
            else:
                st.subheader("⏳ Stamtijden Analyseren (Meerkeuze)")
                
                c1, c2 = st.columns([1, 2])
                with c1:
                    stam_modus = st.radio("Modus:", ["1. MC", "2. Mix (MC + Typen)", "3. Typen"], key="stam_modus_radio")
                    alle_lessen_stam = sorted(list(set(i.get('les', 0) for i in stamtijden_db if i.get('les', 0) > 0)))
                    gekozen_stam = st.multiselect("Kies les(sen):", alle_lessen_stam, default=alle_lessen_stam)
                    
                    if st.button("Start Sessie", key="btn_start_stam"):
                        doel_vormen = []
                        for w in stamtijden_db:
                            if w.get('les', 0) in gekozen_stam:
                                for t_d, vorm in w['stamtijden'].items():
                                    vid = f"{w['praesens']}_{vorm}"
                                    stats = st.session_state.stam_stats.get(vid, {'g': 0, 'f': 0, 'streak': 0})
                                    form_obj = {
                                        "basis": w,
                                        "vraag_vorm": {"tijd_diathese": t_d, "vorm": vorm},
                                        "score_goed": stats['g'],
                                        "score_fout": stats['f'],
                                        "streak": stats['streak'],
                                        "vid": vid
                                    }
                                    doel_vormen.append(form_obj)
                        
                        if doel_vormen:
                            sampled = kies_gefaseerde_oefensessie(doel_vormen, module='stam', max_items=10, max_nieuw=3)
                            
                            modus_id = str(stam_modus[0])
                            if modus_id == "2":
                                st.session_state.stam_sessie_lijst = [(v, random.choice(["MC", "Typen"])) for v in sampled]
                            elif modus_id == "3":
                                st.session_state.stam_sessie_lijst = [(v, "Typen") for v in sampled]
                            else:
                                st.session_state.stam_sessie_lijst = [(v, "MC") for v in sampled]
                                
                            laad_volgend_stam_woord()
                            st.rerun()

                with c2:
                    if st.session_state.stam_huidig:
                        huidig = st.session_state.stam_huidig
                        sub_modus = st.session_state.stam_sub_modus
                        vid = huidig['vid']
                        
                        if vid not in st.session_state.stam_stats:
                            st.session_state.stam_stats[vid] = {'g': 0, 'f': 0, 'streak': 0}
                        
                        if st.session_state.stam_feedback:
                            if st.session_state.stam_feedback["type"] == "success": st.success(st.session_state.stam_feedback["msg"])
                            elif st.session_state.stam_feedback["type"] == "warning": st.warning(st.session_state.stam_feedback["msg"])
                            else: st.error(st.session_state.stam_feedback["msg"])
                            st.session_state.stam_feedback = None 

                        st.markdown(f"<div class='grieks-woord'>{huidig['vraag_vorm']['vorm']}</div>", unsafe_allow_html=True)
                        st.caption("Identificeer deze vorm en herleid hem naar het basiswoord.")
                        
                        correct_gram = huidig['vraag_vorm']['tijd_diathese']
                        correct_praesens = huidig['basis']['praesens']
                        correct_betekenis = huidig['basis']['betekenis']
                        
                        if sub_modus == "Typen":
                            with st.form("form_stamtijd_typen", clear_on_submit=True):
                                c_gram, c_bet = st.columns(2)
                                with c_gram:
                                    p_gram = st.selectbox("Tijd & Diathese", ["", "Futurum Actief/Medium", "Aoristus Actief/Medium", "Aoristus Passief", "Perfectum Actief", "Perfectum Medium/Passief"])
                                    p_praesens = st.text_input("Praesens:")
                                with c_bet:
                                    p_betekenis = st.text_input("Betekenis:")
                                
                                if st.form_submit_button("Check Antwoord"):
                                    is_gram_correct = (p_gram == correct_gram)
                                    is_praesens_correct = (normaliseer_accent(naar_grieks_transliteratie(p_praesens)) == normaliseer_accent(correct_praesens))
                                    is_bet_correct = check_betekenis(p_betekenis, correct_betekenis)
                                    
                                    if is_gram_correct and is_praesens_correct and is_bet_correct:
                                        if st.session_state.stam_fouten == 0:
                                            st.session_state.stam_stats[vid]['g'] += 1
                                            st.session_state.stam_stats[vid]['streak'] += 1
                                        st.session_state.stam_feedback = {"type": "success", "msg": f"✓ Goed! **{huidig['vraag_vorm']['vorm']}** is de {correct_gram} van {correct_praesens} (Betekenis: {correct_betekenis})."}
                                        trigger_save(); laad_volgend_stam_woord(); st.rerun()
                                    else:
                                        st.session_state.stam_fouten += 1
                                        if st.session_state.stam_fouten == 1:
                                            st.session_state.stam_feedback = {"type": "warning", "msg": "Niet helemaal juist. Probeer het nog eens!"}
                                        elif st.session_state.stam_fouten == 2:
                                            st.session_state.stam_stats[vid]['f'] += 1
                                            st.session_state.stam_stats[vid]['streak'] = 0
                                            st.session_state.stam_sessie_lijst.append((huidig, sub_modus))
                                            st.session_state.stam_feedback = {"type": "error", "msg": f"✗ Helaas. Het was: **{correct_gram}** van **{correct_praesens}** (Betekenis: **{correct_betekenis}**). Hij komt later terug."}
                                            trigger_save(); laad_volgend_stam_woord(); st.rerun()
                                        st.rerun()
                        else: # PARTIËLE MC FEEDBACK
                            if not st.session_state.stam_opties_gram:
                                alle_g = ["Futurum Actief/Medium", "Aoristus Actief/Medium", "Aoristus Passief", "Perfectum Actief", "Perfectum Medium/Passief"]
                                afleiders_g = [g for g in alle_g if g != correct_gram]
                                st.session_state.stam_opties_gram = [correct_gram] + random.sample(afleiders_g, 3)
                                random.shuffle(st.session_state.stam_opties_gram)
                                
                                correct_p = f"{correct_praesens} — {correct_betekenis}"
                                afleiders_p = [f"{w['praesens']} — {w['betekenis']}" for w in stamtijden_db if w['praesens'] != correct_praesens]
                                st.session_state.stam_opties_praesens = [correct_p] + random.sample(afleiders_p, min(3, len(afleiders_p)))
                                random.shuffle(st.session_state.stam_opties_praesens)

                            with st.form("form_stamtijd_mc"):
                                st.write("**1. Grammatica:**")
                                if st.session_state.stam_mc_solved["gram"]:
                                    st.success(f"✓ {correct_gram}")
                                    keuze_gram = correct_gram
                                else:
                                    keuze_gram = st.radio("Wat is deze vorm?", st.session_state.stam_opties_gram, index=None, label_visibility="collapsed")
                                
                                st.write("**2. Herleiding:**")
                                if st.session_state.stam_mc_solved["praesens"]:
                                    st.success(f"✓ {correct_praesens} — {correct_betekenis}")
                                    keuze_praesens = f"{correct_praesens} — {correct_betekenis}"
                                else:
                                    keuze_praesens = st.radio("Bij welk werkwoord hoort dit?", st.session_state.stam_opties_praesens, index=None, label_visibility="collapsed")
                                
                                if st.form_submit_button("Check Antwoord"):
                                    is_gram_correct = (keuze_gram == correct_gram)
                                    is_prae_correct = (keuze_praesens == f"{correct_praesens} — {correct_betekenis}")
                                    
                                    if is_gram_correct and not st.session_state.stam_mc_solved["gram"]: st.session_state.stam_mc_solved["gram"] = True
                                    if is_prae_correct and not st.session_state.stam_mc_solved["praesens"]: st.session_state.stam_mc_solved["praesens"] = True
                                    
                                    if st.session_state.stam_mc_solved["gram"] and st.session_state.stam_mc_solved["praesens"]:
                                        if st.session_state.stam_fouten == 0:
                                            st.session_state.stam_stats[vid]['g'] += 1
                                            st.session_state.stam_stats[vid]['streak'] += 1
                                        st.session_state.stam_feedback = {"type": "success", "msg": f"✓ Goed! **{huidig['vraag_vorm']['vorm']}** is de {correct_gram} van {correct_praesens} (Betekenis: {correct_betekenis})."}
                                        trigger_save(); laad_volgend_stam_woord(); st.rerun()
                                    else:
                                        st.session_state.stam_fouten += 1
                                        if st.session_state.stam_fouten == 1:
                                            st.session_state.stam_feedback = {"type": "warning", "msg": "Een van je keuzes is niet juist. Het goede deel is vastgezet, probeer het foutieve deel opnieuw!"}
                                        elif st.session_state.stam_fouten == 2:
                                            st.session_state.stam_stats[vid]['f'] += 1
                                            st.session_state.stam_stats[vid]['streak'] = 0
                                            st.session_state.stam_sessie_lijst.append((huidig, sub_modus))
                                            st.session_state.stam_feedback = {"type": "error", "msg": f"✗ Helaas. Het was: **{correct_gram}** van **{correct_praesens}** (Betekenis: **{correct_betekenis}**). Hij komt later terug."}
                                            trigger_save(); laad_volgend_stam_woord(); st.rerun()
                                        st.rerun()

                        st.write("---")
                        st.caption(f"Fase: {'Nieuw' if st.session_state.stam_stats[vid].get('streak', 0)==0 else ('In Training' if st.session_state.stam_stats[vid].get('streak', 0)<5 else ('Beheerst' if st.session_state.stam_stats[vid].get('streak', 0)<20 else 'Mastery'))} | Streak: {st.session_state.stam_stats[vid].get('streak', 0)} | Goed/Fout: {st.session_state.stam_stats[vid].get('g', 0)}/{st.session_state.stam_stats[vid].get('f', 0)}")

        with menu[5]: # STRUCTUURWOORDEN
            struct_db = laad_structuurwoorden_db()
            if not struct_db:
                st.warning("Bestand 'structuurwoorden.json' ontbreekt.")
            else:
                st.subheader("🧱 Structuurwoorden Herkennen")
                
                c1, c2 = st.columns([1, 2])
                with c1:
                    struct_modus = st.radio("Modus:", ["1. MC", "2. Mix (MC + Typen)", "3. Typen"], key="struct_modus_radio")
                    
                    if st.button("Start Sessie", key="btn_start_struct"):
                        doel_vormen = []
                        for w in struct_db:
                            vid = w['grieks']
                            stats = st.session_state.struct_stats.get(vid, {'g': 0, 'f': 0, 'streak': 0})
                            w['score_goed'] = stats['g']
                            w['score_fout'] = stats['f']
                            w['streak'] = stats['streak']
                            w['vid'] = vid
                            doel_vormen.append(w)
                        
                        if doel_vormen:
                            sampled = kies_gefaseerde_oefensessie(doel_vormen, module='struct', max_items=10, max_nieuw=3)
                            
                            modus_id = str(struct_modus[0])
                            if modus_id == "2":
                                st.session_state.struct_sessie_lijst = [(v, random.choice(["MC", "Typen"])) for v in sampled]
                            elif modus_id == "3":
                                st.session_state.struct_sessie_lijst = [(v, "Typen") for v in sampled]
                            else:
                                st.session_state.struct_sessie_lijst = [(v, "MC") for v in sampled]
                                
                            laad_volgend_struct_woord()
                            st.rerun()

                with c2:
                    if st.session_state.struct_huidig:
                        huidig = st.session_state.struct_huidig
                        sub_modus = st.session_state.struct_sub_modus
                        vid = huidig['vid']
                        
                        if vid not in st.session_state.struct_stats:
                            st.session_state.struct_stats[vid] = {'g': 0, 'f': 0, 'streak': 0}
                        
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
                        
                        alle_cats = list(set([w['categorie'] for w in struct_db]))
                        alle_eigs = list(set([w['eigenschap'] for w in struct_db]))
                        
                        if sub_modus == "Typen":
                            with st.form("form_struct_typen", clear_on_submit=True):
                                c_cat, c_eig = st.columns(2)
                                with c_cat: p_cat = st.selectbox("Categorie", [""] + alle_cats)
                                with c_eig: p_eig = st.selectbox("Eigenschap/Naamval", [""] + alle_eigs)
                                p_bet = st.text_input("Betekenis:")
                                
                                if st.form_submit_button("Check Antwoord"):
                                    is_cat_correct = (p_cat == correct_cat)
                                    is_eig_correct = (p_eig == correct_eig)
                                    is_bet_correct = check_betekenis(p_bet, correct_bet)
                                    
                                    if is_cat_correct and is_eig_correct and is_bet_correct:
                                        if st.session_state.struct_fouten == 0:
                                            st.session_state.struct_stats[vid]['g'] += 1
                                            st.session_state.struct_stats[vid]['streak'] += 1
                                        st.session_state.struct_feedback = {"type": "success", "msg": f"✓ Goed! **{huidig['grieks']}** is een {correct_cat} ({correct_eig}) en betekent: {correct_bet}."}
                                        trigger_save(); laad_volgend_struct_woord(); st.rerun()
                                    else:
                                        st.session_state.struct_fouten += 1
                                        if st.session_state.struct_fouten == 1:
                                            st.session_state.struct_feedback = {"type": "warning", "msg": "Niet helemaal juist. Probeer het nog eens!"}
                                        elif st.session_state.struct_fouten == 2:
                                            st.session_state.struct_stats[vid]['f'] += 1
                                            st.session_state.struct_stats[vid]['streak'] = 0
                                            st.session_state.struct_sessie_lijst.append((huidig, sub_modus))
                                            st.session_state.struct_feedback = {"type": "error", "msg": f"✗ Helaas. Het was: **{correct_cat}** ({correct_eig}) | Betekenis: **{correct_bet}**."}
                                            trigger_save(); laad_volgend_struct_woord(); st.rerun()
                                        st.rerun()
                        else: # PARTIËLE MC FEEDBACK
                            if not st.session_state.struct_opties_cat:
                                afleiders_c = [c for c in alle_cats if c != correct_cat]
                                st.session_state.struct_opties_cat = [correct_cat] + random.sample(afleiders_c, min(3, len(afleiders_c)))
                                random.shuffle(st.session_state.struct_opties_cat)
                                
                                afleiders_e = [e for e in alle_eigs if e != correct_eig]
                                st.session_state.struct_opties_eig = [correct_eig] + random.sample(afleiders_e, min(3, len(afleiders_e)))
                                random.shuffle(st.session_state.struct_opties_eig)
                                
                                afleiders_b = [w['betekenis'] for w in struct_db if w['betekenis'] != correct_bet]
                                st.session_state.struct_opties_bet = [correct_bet] + random.sample(afleiders_b, min(3, len(afleiders_b)))
                                random.shuffle(st.session_state.struct_opties_bet)
                                
                            with st.form("form_struct_mc"):
                                if st.session_state.struct_mc_solved["cat"]:
                                    st.success(f"✓ Categorie: {correct_cat}")
                                    keuze_cat = correct_cat
                                else:
                                    keuze_cat = st.radio("1. Categorie:", st.session_state.struct_opties_cat, index=None)
                                
                                if st.session_state.struct_mc_solved["eig"]:
                                    st.success(f"✓ Eigenschap: {correct_eig}")
                                    keuze_eig = correct_eig
                                else:
                                    keuze_eig = st.radio("2. Eigenschap / Naamval:", st.session_state.struct_opties_eig, index=None)
                                
                                if st.session_state.struct_mc_solved["bet"]:
                                    st.success(f"✓ Betekenis: {correct_bet}")
                                    keuze_bet = correct_bet
                                else:
                                    keuze_bet = st.radio("3. Betekenis:", st.session_state.struct_opties_bet, index=None)
                                
                                if st.form_submit_button("Check Antwoord"):
                                    is_cat_correct = (keuze_cat == correct_cat)
                                    is_eig_correct = (keuze_eig == correct_eig)
                                    is_bet_correct = (keuze_bet == correct_bet)
                                    
                                    if is_cat_correct and not st.session_state.struct_mc_solved["cat"]: st.session_state.struct_mc_solved["cat"] = True
                                    if is_eig_correct and not st.session_state.struct_mc_solved["eig"]: st.session_state.struct_mc_solved["eig"] = True
                                    if is_bet_correct and not st.session_state.struct_mc_solved["bet"]: st.session_state.struct_mc_solved["bet"] = True
                                    
                                    if st.session_state.struct_mc_solved["cat"] and st.session_state.struct_mc_solved["eig"] and st.session_state.struct_mc_solved["bet"]:
                                        if st.session_state.struct_fouten == 0:
                                            st.session_state.struct_stats[vid]['g'] += 1
                                            st.session_state.struct_stats[vid]['streak'] += 1
                                        st.session_state.struct_feedback = {"type": "success", "msg": f"✓ Goed! **{huidig['grieks']}** is een {correct_cat} ({correct_eig}) en betekent: {correct_bet}."}
                                        trigger_save(); laad_volgend_struct_woord(); st.rerun()
                                    else:
                                        st.session_state.struct_fouten += 1
                                        if st.session_state.struct_fouten == 1:
                                            st.session_state.struct_feedback = {"type": "warning", "msg": "De goede delen zijn vastgezet. Probeer de rest opnieuw!"}
                                        elif st.session_state.struct_fouten == 2:
                                            st.session_state.struct_stats[vid]['f'] += 1
                                            st.session_state.struct_stats[vid]['streak'] = 0
                                            st.session_state.struct_sessie_lijst.append((huidig, sub_modus))
                                            st.session_state.struct_feedback = {"type": "error", "msg": f"✗ Helaas. Het was: **{correct_cat}** ({correct_eig}) | Betekenis: **{correct_bet}**."}
                                            trigger_save(); laad_volgend_struct_woord(); st.rerun()
                                        st.rerun()

                        st.write("---")
                        st.caption(f"Fase: {'Nieuw' if st.session_state.struct_stats[vid].get('streak', 0)==0 else ('In Training' if st.session_state.struct_stats[vid].get('streak', 0)<5 else ('Beheerst' if st.session_state.struct_stats[vid].get('streak', 0)<20 else 'Mastery'))} | Streak: {st.session_state.struct_stats[vid].get('streak', 0)} | Goed/Fout: {st.session_state.struct_stats[vid].get('g', 0)}/{st.session_state.struct_stats[vid].get('f', 0)}")

        with menu[6]: # LEESTEKSTEN
            bijbel_db = laad_bijbel_db()
            stam_db_leestekst = laad_stamtijden_db() or []
            
            if not bijbel_db:
                st.warning("De Bijbel-database ontbreekt.")
            else:
                st.subheader("📝 Bijbelse Leesteksten & Exegese")
                
                top_c1, top_c2 = st.columns(2)
                with top_c1:
                    alle_lessen = sorted(list(set(veilig_les_nummer(i) for i in st.session_state.data)))
                    gekozen = st.multiselect("1. Oefen lessen (voor blauwe/paarse woorden):", alle_lessen, default=[alle_lessen[0]] if alle_lessen else [])
                    
                    actieve_strongs = {str(w['strong']): w for w in st.session_state.data if veilig_les_nummer(w) in gekozen and w.get('strong')}
                    
                    actieve_stam_vormen = {}
                    for s_ww in stam_db_leestekst:
                        if s_ww.get('les', 0) in gekozen:
                            for td, v in s_ww['stamtijden'].items():
                                actieve_stam_vormen[normaliseer_accent(v)] = {"tijd_diathese": td, "praesens": s_ww['praesens'], "betekenis": s_ww['betekenis']}
                
                with top_c2:
                    tekst_modus = st.radio("2. Oefenmethode:", 
                                           ["1. Lees & Spiek (Geen vragen)", 
                                            "2. Vertaal (Meerkeuze)", 
                                            "3. Vertaal (Typen)", 
                                            "4. Masterclass (Ontleden)"])

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
                        if match:
                            b, c, v = match.group(1), match.group(2), match.group(3)
                        else:
                            parts = ref.split(" ")
                            if len(parts) >= 2 and ":" in parts[-1]:
                                cv = parts[-1].split(":")
                                b, c, v = " ".join(parts[:-1]), cv[0], cv[1]
                            else:
                                b, c, v = ref, "1", "1"
                                
                        if b not in parsed_db: parsed_db[b] = {}
                        if c not in parsed_db[b]: parsed_db[b][c] = []
                        
                        v_sort = int(re.sub(r"\D", "", v)) if re.sub(r"\D", "", v).isdigit() else 0
                        parsed_db[b][c].append((v_sort, v, ref))
                    
                    col_b, col_c, col_v = st.columns(3)
                    with col_b:
                        gekozen_boek = st.selectbox("Boek:", list(parsed_db.keys()))
                    with col_c:
                        hoofdstukken = list(parsed_db[gekozen_boek].keys())
                        hoofdstukken.sort(key=lambda x: int(x) if str(x).isdigit() else 0)
                        gekozen_hoofdstuk = st.selectbox("Hoofdstuk:", hoofdstukken)
                    with col_v:
                        verzen_data = parsed_db[gekozen_boek][gekozen_hoofdstuk]
                        verzen_data.sort(key=lambda x: x[0])
                        vers_opties = [v[1] for v in verzen_data]
                        gekozen_verzen = st.multiselect("Vers(zen):", vers_opties, default=[vers_opties[0]] if vers_opties else [])
                    
                    if st.button("Laad Tekst"):
                        gecombineerd_vers = []
                        for vd in verzen_data:
                            if vd[1] in gekozen_verzen:
                                gecombineerd_vers.extend(bijbel_db[vd[2]])
                                if vd[2] not in st.session_state.geziene_verzen:
                                    st.session_state.geziene_verzen.append(vd[2])
                        
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
                                vers_gewicht = 0
                                for w in bekende_woorden:
                                    vers_gewicht += bereken_gewicht(actieve_strongs[str(w['strong'])])
                                passende.append((ref, w_list, vers_gewicht))
                        
                        if not passende:
                            st.session_state.geziene_verzen = [] 
                            st.warning("Geschiedenis gereset. Geen nieuwe verzen gevonden, klik nogmaals om opnieuw te beginnen.")
                        else:
                            passende.sort(key=lambda x: x[2], reverse=True)
                            top_picks = passende[:min(10, len(passende))]
                            gekozen_vers = random.choice(top_picks)
                            st.session_state.huidig_vers = gekozen_vers[1]
                            st.session_state.huidige_vers_referentie = gekozen_vers[0]
                            st.session_state.geziene_verzen.append(gekozen_vers[0])
                            st.session_state.geziene_verzen = st.session_state.geziene_verzen[-100:]

                st.write("---")

                if st.session_state.huidig_vers:
                    st.markdown(f"### 📖 {st.session_state.huidige_vers_referentie}")
                    html_zin = ""
                    oefen_woorden = []
                    
                    for w in st.session_state.huidig_vers:
                        tooltip = f"{w['vertaling_bsb']} ({w['parsing_info']})"
                        
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
                        
                        if is_stam and kleur_stamtijden:
                            css_class = "woord-stamtijd"
                        elif is_bekend:
                            css_class = "woord-bekend"
                        else:
                            css_class = "woord-onbekend"

                        if css_class in ["woord-bekend", "woord-stamtijd"]:
                            if "1." in tekst_modus:
                                if is_bekend:
                                    basis_nederlands = actieve_strongs[str(w['strong'])].get('nederlands', '')
                                    les_nr = actieve_strongs[str(w['strong'])].get('les', '?')
                                    hover_text = f"Les {les_nr}: {basis_nederlands} | {tooltip}"
                                else:
                                    hover_text = f"{actieve_stam_vormen[clean_w]['betekenis']} | {tooltip}"
                            else:
                                hover_text = "Oefenwoord! Vul de gegevens hieronder in."
                                
                            html_zin += f"<span class='{css_class}' style='{extra_style}' title='{hover_text}'>{w['grieks']}</span>{w['interpunctie']} "
                            
                            oef_dict = w.copy()
                            oef_dict['is_stamtijd'] = is_stam
                            oef_dict['stam_info'] = actieve_stam_vormen[clean_w] if is_stam else None
                            oefen_woorden.append(oef_dict)
                        else:
                            html_zin += f"<span class='{css_class}' style='{extra_style}' title='{tooltip}'>{w['grieks']}</span>{w['interpunctie']} "
                    
                    if kleur_naamvallen:
                        st.markdown("**(Kleurlegenda: <span style='color:#33ccff'>Nom</span> | <span style='color:#28a745'>Gen</span> | <span style='color:#6f42c1'>Dat</span> | <span style='color:#dc3545'>Acc</span> | <span style='color:#fd7e14'>Voc</span>)**", unsafe_allow_html=True)

                    st.markdown(f"<div class='grieks-zin'>{html_zin}</div>", unsafe_allow_html=True)
                    st.caption("ℹ️ Hover over een woord om de vertaling te zien. Cyaan/Paarse woorden komen uit je actieve lessen.")
                    
                    if oefen_woorden and "1." not in tekst_modus:
                        st.write("### 📝 Oefen je woorden in context")
                        for idx, w in enumerate(oefen_woorden):
                            if w['is_stamtijd'] and kleur_stamtijden:
                                stam_data = w['stam_info']
                                st.markdown(f"**<span style='color:#d63384'>[Stamtijd]</span> {w['grieks']}**", unsafe_allow_html=True)
                                
                                with st.form(key=f"form_lees_stam_{idx}"):
                                    c_gram, c_bet = st.columns(2)
                                    with c_gram:
                                        p_gram = st.selectbox("Tijd & Diathese", ["", "Futurum Actief/Medium", "Aoristus Actief/Medium", "Aoristus Passief", "Perfectum Actief", "Perfectum Medium/Passief"], key=f"s_g_{idx}")
                                        p_praesens = st.text_input("Praesens:", key=f"s_p_{idx}")
                                    with c_bet:
                                        p_betekenis = st.text_input("Betekenis:", key=f"s_b_{idx}")
                                    
                                    if st.form_submit_button("Check Stamtijd"):
                                        is_gram_correct = (p_gram == stam_data['tijd_diathese'])
                                        is_praesens_correct = (normaliseer_accent(naar_grieks_transliteratie(p_praesens)) == normaliseer_accent(stam_data['praesens']))
                                        is_bet_correct = check_betekenis(p_betekenis, stam_data['betekenis'])
                                        
                                        if is_gram_correct and is_praesens_correct and is_bet_correct:
                                            st.success(f"✓ Goed! **{w['grieks']}** is de {stam_data['tijd_diathese']} van {stam_data['praesens']}.")
                                        else:
                                            st.error(f"✗ Onjuist. Het is de **{stam_data['tijd_diathese']}** van **{stam_data['praesens']}** (Betekenis: **{stam_data['betekenis']}**).")

                            else:
                                basis = actieve_strongs[str(w['strong'])]
                                
                                in_scope = True
                                norm_basis = normaliseer_accent(basis['grieks'])
                                is_ww = "Werkwoord" in w['parsing_info'] or basis.get('woordsoort') == 'ww'
                                
                                if master_niveau == "Grieks 1":
                                    if is_ww:
                                        is_actief = "Actief" in w['parsing_info']
                                        is_ptc_conj_opt = any(x in w['parsing_info'] for x in ["Participium", "Conjunctivus", "Optativus"])
                                        is_eimi = norm_basis == "ειμι"
                                        in_scope = is_eimi or (is_actief and not is_ptc_conj_opt)
                                    else:
                                        in_scope = norm_basis.endswith(('ος', 'ον', 'α', 'η', 'ω', 'υ', 'ουτος', 'αυτη', 'τουτο')) or norm_basis in ['ο', 'η', 'το', 'εγω', 'συ']
                                elif master_niveau == "Grieks 2":
                                    if is_ww:
                                        in_scope = not any(x in w['parsing_info'] for x in ["Conjunctivus", "Optativus"])
                                    if norm_basis.endswith('μι') and norm_basis != "ειμι":
                                        in_scope = False

                                if "4." in tekst_modus:
                                    st.markdown(f"**{w['grieks']}**")
                                else:
                                    st.markdown(f"**{w['grieks']}** (Basis: {basis['grieks']})")
                                
                                if "2." in tekst_modus: 
                                    if f"mc_opties_{idx}" not in st.session_state or st.session_state.get(f"mc_vers_{idx}") != st.session_state.huidige_vers_referentie:
                                        random.seed(st.session_state.huidige_vers_referentie + str(idx))
                                        afleiders = list(set([i['nederlands'] for i in st.session_state.data if i['nederlands'] != basis['nederlands']]))
                                        opties = [basis['nederlands']] + random.sample(afleiders, min(3, len(afleiders)))
                                        random.shuffle(opties)
                                        random.seed()
                                        st.session_state[f"mc_opties_{idx}"] = opties
                                        st.session_state[f"mc_vers_{idx}"] = st.session_state.huidige_vers_referentie
                                        
                                    cols = st.columns(2)
                                    for c_idx, optie in enumerate(st.session_state[f"mc_opties_{idx}"]):
                                        if cols[c_idx % 2].button(optie, key=f"mc_{idx}_{c_idx}_{w['grieks']}"):
                                            if optie == basis['nederlands']: 
                                                basis['streak_m2'] = int(basis.get('streak_m2', 0)) + 1
                                                basis['score_goed'] = int(basis.get('score_goed', 0)) + 1
                                                trigger_save()
                                                st.success(f"✓ Goed! **{w['grieks']}** = {basis['nederlands']} ({w['parsing_info']})")
                                            else: 
                                                basis['streak_m2'] = max(0, int(basis.get('streak_m2', 0)) - 2)
                                                basis['score_fout'] = int(basis.get('score_fout', 0)) + 1
                                                trigger_save()
                                                st.error(f"✗ Fout. Het was: {basis['nederlands']}")
                                    
                                elif "3." in tekst_modus: 
                                    with st.form(key=f"form_typ_{idx}"):
                                        inp = st.text_input("Woordenboekvertaling:")
                                        if st.form_submit_button("Check"):
                                            if check_betekenis(inp, basis['nederlands']): 
                                                basis['streak_m4'] = int(basis.get('streak_m4', 0)) + 1
                                                basis['score_goed'] = int(basis.get('score_goed', 0)) + 1
                                                trigger_save()
                                                st.success(f"✓ Goed! **{w['grieks']}** = {basis['nederlands']} ({w['parsing_info']})")
                                            else: 
                                                basis['streak_m4'] = max(0, int(basis.get('streak_m4', 0)) - 2)
                                                basis['score_fout'] = int(basis.get('score_fout', 0)) + 1
                                                trigger_save()
                                                st.error(f"✗ Fout. Het is: {basis['nederlands']}")
                                            
                                elif "4." in tekst_modus:
                                    if not in_scope:
                                        st.success(f"*(Buiten scope voor {master_niveau})* **{w['grieks']}** = {basis['nederlands']} ({w['parsing_info']})")
                                    else:
                                        p_soort = st.selectbox("Woordsoort", ["", "Zelfst. nw.", "Werkwoord", "Bijv. nw.", "Lidwoord", "Voornaamwoord", "Overig"], key=f"soort_{idx}")
                                        t_inp = st.text_input("Woordenboekvertaling:", key=f"bet_{idx}")
                                        
                                        p_naam, p_get, p_ges = "", "", ""
                                        p_tijd, p_wijs, p_pers, p_diat = "", "", "", ""
                                        
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
                                            betekenis_ok = check_betekenis(t_inp, basis['nederlands'])
                                            parsing_ok = check_bijbel_parsing_uitgebreid(p_soort, p_naam, p_get, p_ges, p_tijd, p_wijs, p_diat, p_pers, w['parsing_info'])
                                            
                                            if betekenis_ok and parsing_ok:
                                                basis['streak_m4'] = int(basis.get('streak_m4', 0)) + 1
                                                basis['score_goed'] = int(basis.get('score_goed', 0)) + 1
                                                trigger_save()
                                                st.success(f"✓ Volledig correct! ({w['parsing_info']})")
                                            else:
                                                basis['streak_m4'] = max(0, int(basis.get('streak_m4', 0)) - 2)
                                                basis['score_fout'] = int(basis.get('score_fout', 0)) + 1
                                                trigger_save()
                                                st.error(f"✗ Onjuist. Officiële data: {w['parsing_info']} | Betekenis: {basis['nederlands']}")
                                                
                    st.write("---")
                    st.write("### ✍️ Zinsvertaling")
                    user_vertaling = st.text_area("Vertaal de hele zin naar het Nederlands:")
                    if st.button("Toon officiële vertaling"):
                        officiële_zin = " ".join([w['vertaling_bsb'] for w in st.session_state.huidig_vers])
                        st.success(f"**Officiële Engelse zinsvertaling (BSB):** {officiële_zin}")

if __name__ == "__main__":
    main()
