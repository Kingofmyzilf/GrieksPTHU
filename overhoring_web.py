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
    .woord-bekend { color: #33ccff; font-weight: bold; border-bottom: 2px solid #33ccff; cursor: help; padding: 0 4px; }
    .woord-onbekend { color: #aaaaaa; cursor: help; padding: 0 2px; }
    .grid-label { font-weight: bold; color: #33ccff; margin-bottom: 5px; }
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
        return w
    return ""

def splits_sleutel(sleutel):
    s = str(sleutel).strip()
    wijzen = ["Indicativus", "Conjunctivus", "Optativus", "Imperativus", "Infinitivus", "Participium", "Part"]
    for w in wijzen:
        if s.lower().startswith(w.lower()):
            rest = s[len(w):].strip(" _-.")
            return w.capitalize(), rest if rest else "Vorm"
    naamvallen = ["nom", "gen", "dat", "acc", "voc"]
    if any(s.lower().startswith(n) for n in naamvallen): return "Declinatie", s
    return "Overig", s

def maak_schoon(tekst):
    schoon = re.sub(r'\(.*?\)', '', str(tekst))
    schoon = re.sub(r'\[.*?\]', '', schoon)
    return schoon.replace(';', ',').split(',')[0].strip().lower()

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

def kies_adaptieve_gram_vorm(vlak, prefix):
    if not vlak: return None
    weights = []
    for v in vlak:
        vorm_id = f"{prefix}_{v['naam']}" if prefix else f"{v.get('prefix', '')}_{v['naam']}"
        stats = st.session_state.gram_stats.get(vorm_id, {'goed': 0, 'fout': 0, 'streak': 0})
        w = max(0.1, 1.0 + (stats['fout'] * 1.5) - (stats['streak'] * 0.4))
        weights.append(w)
    return random.choices(vlak, weights=weights, k=1)[0]

def check_bijbel_parsing(p_soort, p_naamval, p_getal, p_geslacht, bsb_info):
    info = bsb_info.lower()
    
    soort_map = {"Zelfst. nw.": "noun", "Werkwoord": "verb", "Bijv. nw.": "adjective", "Lidwoord": "article", "Voornaamwoord": "pronoun"}
    if p_soort in soort_map and soort_map[p_soort] not in info: return False
    
    nv_map = {"Nom": "nominative", "Gen": "genitive", "Dat": "dative", "Acc": "accusative", "Voc": "vocative"}
    if p_naamval in nv_map and nv_map[p_naamval] not in info: return False
    if p_naamval == "N.v.t." and any(x in info for x in nv_map.values()): return False
    
    gt_map = {"ev": "singular", "mv": "plural"}
    if p_getal in gt_map and gt_map[p_getal] not in info: return False
    
    gs_map = {"M": "masculine", "V": "feminine", "O": "neuter"}
    if p_geslacht in gs_map and gs_map[p_geslacht] not in info: return False
    
    return True

# --- DATABASE FUNCTIES ---

@st.cache_data
def laad_grammatica_db():
    if os.path.exists("grammatica.json"):
        try:
            with open("grammatica.json", "r", encoding="utf-8") as f: return json.load(f)
        except Exception: pass
    return None

@st.cache_data
def laad_declinaties_db():
    if os.path.exists("declinaties.json"):
        try:
            with open("declinaties.json", "r", encoding="utf-8") as f: return json.load(f)
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
            df_andere = df[df['gebruikersnaam'] != naam]
            nieuwe_rij = pd.DataFrame([{'gebruikersnaam': naam, 'vocab_stats': '{}', 'gram_stats': '{}'}])
            conn.update(data=pd.concat([df_andere, nieuwe_rij], ignore_index=True))
        else:
            try: st.session_state.vocab_stats = json.loads(str(user_row.iloc[0].get('vocab_stats', '{}')))
            except: st.session_state.vocab_stats = {}
            try: st.session_state.gram_stats = json.loads(str(user_row.iloc[0].get('gram_stats', '{}')))
            except: st.session_state.gram_stats = {}
            
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
        
        nieuwe_rij = pd.DataFrame([{
            'gebruikersnaam': st.session_state.last_user,
            'vocab_stats': v_json,
            'gram_stats': g_json
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

# --- SESSION STATE ---
for key in ['data', 'sessie_lijst', 'huidig_item', 'huidige_sub_modus', 'huidige_vorm_data', 'feedback', 
            'fouten_huidig_woord', 'huidige_opties', 'last_user',
            'gram_oefening', 'laatste_filter',
            'decl_oefening', 'laatste_filter_decl', 'gram_feedback', 'decl_feedback',
            'huidig_vers', 'huidige_vers_referentie']:
    if key not in st.session_state: st.session_state[key] = None

if 'vocab_stats' not in st.session_state: st.session_state.vocab_stats = {}
if 'gram_stats' not in st.session_state: st.session_state.gram_stats = {}
if st.session_state.fouten_huidig_woord is None: st.session_state.fouten_huidig_woord = 0

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
    menu = st.tabs(["🚀 Woordenschat", "📖 Lijst", "📊 Voortgang", "🏛️ Werkwoorden", "🏷️ Naamwoorden", "📝 Leesteksten"])

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
                    doel.sort(key=bereken_gewicht, reverse=True)
                    sampled = random.sample(doel, min(len(doel), 10))
                    
                    modus_id = str(modus[0])
                    st.session_state.modus_actief = modus_id
                    
                    if modus_id == "3":
                        mc_deel = [(w, "3_mc") for w in sampled]
                        typen_deel = [(w, "3_typ") for w in sampled]
                        st.session_state.sessie_lijst = mc_deel + typen_deel
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
                correct_volledig = correct_antw.lower()
                correct_schoon = maak_schoon(correct_antw)
                correcte_delen = [d.strip() for d in correct_volledig.split(',')]
                volledig_antwoord_str = f"**{huidige_vorm}** = {correct_antw}" + (f" ({huidige_parsing})" if is_mastery and heeft_vormen else "")
                
                # --- TYPEN MODUS ---
                if huidige_sub_modus in ['4', '3_typ']:
                    with st.form(key=f"form_vocab_{item.get('grieks')}", clear_on_submit=True):
                        inp = st.text_input("Betekenis:").lower().strip()
                        if is_mastery and heeft_vormen:
                            p_vorm = st.text_input("Vorm (bijv. nom ev m):").lower().strip()
                        else:
                            p_vorm = huidige_parsing.lower().strip()

                        if st.form_submit_button("Check Antwoord"):
                            betekenis_goed = (inp == correct_volledig or inp == correct_schoon or inp in correcte_delen)
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
                                    st.session_state.feedback = {"type": "error", "msg": f"✗ Fout. Typ exact over om door te gaan: {volledig_antwoord_str}"}
                                    trigger_save()
                                else:
                                    st.session_state.feedback = {"type": "error", "msg": f"✗ Typ exact over: {volledig_antwoord_str}"}
                                st.rerun()
                
                # --- MEERKEUZE MODUS ---
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
                                    st.session_state.feedback = {"type": "error", "msg": f"✗ Fout. Het juiste antwoord is: '{correct_optie}'. Klik hierop om door te gaan."}
                                    trigger_save()
                                else:
                                    st.session_state.feedback = {"type": "error", "msg": f"Kies het juiste antwoord: '{correct_optie}'."}
                                st.rerun()

                st.write("---")
                st.caption(f"Streaks: M1:{sm1} | M2:{sm2} | M3(Mix):{sm3} | M4:{sm4} — Totaal Goed/Fout: {item.get('score_goed', 0)} / {item.get('score_fout', 0)}")

    with menu[1]: # LIJST
        if st.session_state.data:
            alle_lessen = sorted(list(set(veilig_les_nummer(i) for i in st.session_state.data)))
            les_filter = st.selectbox("Bekijk les:", alle_lessen)
            df = pd.DataFrame([i for i in st.session_state.data if veilig_les_nummer(i) == les_filter])
            if not df.empty:
                st.dataframe(df[[c for c in ['grieks', 'nederlands', 'streak_m1', 'streak_m2', 'streak_m3', 'streak_m4', 'score_goed', 'score_fout', 'woordsoort'] if c in df.columns]], use_container_width=True)

    with menu[2]: # VOORTGANG
        if st.session_state.data:
            st.write("Voortgang per les op basis van mastery (Gemiddelde streak >= 20)")
            lessen = sorted(list(set(veilig_les_nummer(i) for i in st.session_state.data)))
            stats = []
            for l in lessen:
                it = [i for i in st.session_state.data if veilig_les_nummer(i) == l]
                beheerst = len([i for i in it if (int(i.get('streak_m1',0))+int(i.get('streak_m2',0))+int(i.get('streak_m3',0))+int(i.get('streak_m4',0)))/4 >= 20])
                stats.append((beheerst/len(it))*100 if len(it) > 0 else 0)
            fig, ax = plt.subplots()
            ax.bar(lessen, stats, color='#33ccff')
            ax.set_ylim(0, 100)
            st.pyplot(fig)

    with menu[3]: # WERKWOORDEN
        gram_db = laad_grammatica_db()
        if gram_db and "λύω" in gram_db.get("werkwoorden", {}):
            luo = gram_db["werkwoorden"]["λύω"]
            st.subheader("🏛️ Verbale Morfologie (λύω)")
            
            c1, c2, c3 = st.columns(3)
            with c1: gram_keuze = st.radio("Modus:", ["Visueel Leren (Tabel)", "Vormen Analyseren", "Rijtjes Produceren"])
            with c2: gekozen_tijden = st.multiselect("1. Tijd/Diathese:", list(luo.keys()), default=[list(luo.keys())[0]])
            
            with c3:
                wijzen_set = set()
                for t in gekozen_tijden:
                    for k in luo[t].keys(): wijzen_set.add(splits_sleutel(k)[0])
                gekozen_wijzen = st.multiselect("2. Modus/Wijs:", ["Alles"] + sorted(list(wijzen_set)), default=["Alles"])
            
            vlak = []
            for t in gekozen_tijden:
                for k, v in luo[t].items():
                    wijs, rest = splits_sleutel(k)
                    if "Alles" in gekozen_wijzen or wijs in gekozen_wijzen:
                        vlak.append({"tijd": t, "naam": k, "vorm": v, "wijs": wijs, "rest": rest, "prefix": f"ww_{t}"})

            if st.session_state.gram_feedback:
                if st.session_state.gram_feedback['type'] == 'success': st.success(st.session_state.gram_feedback['msg'])
                else: st.error(st.session_state.gram_feedback['msg'])
                st.session_state.gram_feedback = None

            st.write("---")

            if gram_keuze == "Visueel Leren (Tabel)":
                for t in gekozen_tijden:
                    st.markdown(f"#### {t}")
                    items = {v['rest'] if v['rest'] else v['wijs']: v['vorm'] for v in vlak if v['tijd'] == t}
                    if items: st.dataframe(pd.DataFrame(list(items.items()), columns=["Vorm", "Griekse Vorm"]), use_container_width=True, hide_index=True)

            elif gram_keuze == "Vormen Analyseren":
                huidig_filter = str(gekozen_tijden) + str(gekozen_wijzen)
                if st.button("Nieuwe Vorm") or not st.session_state.gram_oefening or st.session_state.get('laatste_filter') != huidig_filter:
                    st.session_state.gram_oefening = kies_adaptieve_gram_vorm(vlak, prefix=None) 
                    st.session_state.laatste_filter = huidig_filter
                
                oef = st.session_state.gram_oefening
                if oef:
                    st.markdown(f"<div class='grieks-woord'>{oef['vorm']}</div>", unsafe_allow_html=True)
                    vorm_id = f"{oef['prefix']}_{oef['naam']}"
                    if vorm_id not in st.session_state.gram_stats: st.session_state.gram_stats[vorm_id] = {'goed': 0, 'fout': 0, 'streak': 0}

                    with st.form(key=f"form_analyse_ww_{oef['vorm']}"):
                        if len(gekozen_tijden) > 1: p_tijd = st.selectbox("Welke Tijd/Diathese?", [""] + gekozen_tijden)
                        else: p_tijd = oef['tijd']

                        if oef['wijs'] == "Participium":
                            ca1, ca2, ca3 = st.columns(3)
                            with ca1: nv = st.selectbox("Naamval:", ["", "Nom.", "Gen.", "Dat.", "Acc."])
                            with ca2: gt = st.selectbox("Getal:", ["", "ev.", "mv."])
                            with ca3: gs = st.selectbox("Geslacht:", ["", "M", "V", "O"])
                            poging_naam = f"Participium {nv} {gt} {gs}".strip()
                        else:
                            beschikbare_vormen = list(dict.fromkeys([v['naam'] for v in vlak]))
                            poging_naam = st.selectbox("Welke Persoon/Vorm is dit?", [""] + beschikbare_vormen)
                        
                        if st.form_submit_button("Controleer"):
                            if p_tijd == oef['tijd'] and normaliseer_accent(poging_naam) == normaliseer_accent(oef['naam']):
                                st.session_state.gram_stats[vorm_id]['goed'] += 1
                                st.session_state.gram_stats[vorm_id]['streak'] += 1
                                st.session_state.gram_feedback = {'type': 'success', 'msg': f"✓ Correct! **{oef['vorm']}** was de {oef['naam']} van de {oef['tijd']}."}
                                st.session_state.gram_oefening = kies_adaptieve_gram_vorm(vlak, prefix=None)
                                trigger_save(); st.rerun()
                            else:
                                st.session_state.gram_stats[vorm_id]['fout'] += 1
                                st.session_state.gram_stats[vorm_id]['streak'] = 0
                                st.session_state.gram_feedback = {'type': 'error', 'msg': f"✗ Onjuist. **{oef['vorm']}** is de {oef['naam']} van de {oef['tijd']}."}
                                trigger_save(); st.rerun()

            else: # Produceren
                st.info("ℹ️ Gebruik Bèta-code. Accenten worden automatisch genegeerd.")
                with st.form(key=f"form_prod_ww_{gekozen_tijden}_{gekozen_wijzen}"):
                    fouten_teller = 0
                    for t in gekozen_tijden:
                        st.markdown(f"#### {t}")
                        t_vlak = [v for v in vlak if v['tijd'] == t]
                        
                        if any(v['wijs'] == "Participium" for v in t_vlak):
                            for nv in ["Nom.", "Gen.", "Dat.", "Acc."]:
                                for gt in ["ev.", "mv."]:
                                    st.markdown(f"<div class='grid-label'>{nv} {gt}</div>", unsafe_allow_html=True)
                                    cols = st.columns(3)
                                    for i, ges in enumerate(["M", "V", "O"]):
                                        label = f"Participium {nv} {gt} {ges}"
                                        correct_item = next((v for v in t_vlak if v['naam'] == label), None)
                                        if correct_item:
                                            inp = cols[i].text_input(ges, key=f"ptc_{t}_{label}")
                                            if inp:
                                                if normaliseer_accent(naar_grieks_transliteratie(inp)) == normaliseer_accent(correct_item['vorm']): cols[i].caption(f"✅ {correct_item['vorm']}")
                                                else: cols[i].caption(f"❌ {correct_item['vorm']}"); fouten_teller += 1
                        
                        standaard_vormen = [v for v in t_vlak if v['wijs'] != "Participium"]
                        for v in standaard_vormen:
                            label = v['rest'] if v['rest'] else v['wijs']
                            inp = st.text_input(label, key=f"std_{t}_{v['naam']}")
                            if inp:
                                if normaliseer_accent(naar_grieks_transliteratie(inp)) == normaliseer_accent(v['vorm']): st.success(f"✓ {v['vorm']}")
                                else: st.error(f"✗ {v['vorm']}"); fouten_teller += 1
                    
                    if st.form_submit_button("Check Rijtjes") and fouten_teller == 0: st.balloons()

    with menu[4]: # NAAMWOORDEN
        decl_db = laad_declinaties_db()
        if decl_db:
            st.subheader("🏷️ Nominale Morfologie")
            dc1, dc2, dc3 = st.columns(3)
            with dc1: decl_keuze = st.radio("Modus:", ["Visueel Leren (Tabel)", "Vormen Analyseren", "Rijtjes Produceren"], key="decl_radio")
            
            with dc2: gekozen_groepen = st.multiselect("Groep:", list(decl_db["Declinaties"].keys()), default=[list(decl_db["Declinaties"].keys())[0]])
            
            paradigma_opties = []
            for g in gekozen_groepen: paradigma_opties.extend([f"{g} | {p}" for p in decl_db["Declinaties"][g].keys()])
                
            with dc3: gekozen_paradigmas = st.multiselect("Paradigma:", paradigma_opties, default=[paradigma_opties[0]] if paradigma_opties else [])
            
            vlak = []
            for gp in gekozen_paradigmas:
                g, p = gp.split(" | ")
                for k, v in decl_db["Declinaties"][g][p].items():
                    vlak.append({"groep": g, "paradigma": p, "naam": k, "vorm": v, "prefix": f"nw_{g}_{p}"})

            st.write("---")

            if st.session_state.decl_feedback:
                if st.session_state.decl_feedback['type'] == 'success': st.success(st.session_state.decl_feedback['msg'])
                else: st.error(st.session_state.decl_feedback['msg'])
                st.session_state.decl_feedback = None

            if decl_keuze == "Visueel Leren (Tabel)":
                for gp in gekozen_paradigmas:
                    g, p = gp.split(" | ")
                    st.markdown(f"#### {p} ({g})")
                    items = {v['naam']: v['vorm'] for v in vlak if v['paradigma'] == p}
                    st.dataframe(pd.DataFrame(list(items.items()), columns=["Naamval", "Vorm"]), use_container_width=True, hide_index=True)
                    
            elif decl_keuze == "Vormen Analyseren":
                huidig_filter = str(gekozen_paradigmas)
                if st.button("Nieuwe Vorm", key="btn_nw_decl") or not st.session_state.get('decl_oefening') or st.session_state.get('laatste_filter_decl') != huidig_filter:
                    st.session_state.decl_oefening = kies_adaptieve_gram_vorm(vlak, prefix=None)
                    st.session_state.laatste_filter_decl = huidig_filter
                
                oef = st.session_state.decl_oefening
                if oef:
                    st.markdown(f"<div class='grieks-woord'>{oef['vorm']}</div>", unsafe_allow_html=True)
                    vorm_id = f"{oef['prefix']}_{oef['naam']}"
                    if vorm_id not in st.session_state.gram_stats: st.session_state.gram_stats[vorm_id] = {'goed': 0, 'fout': 0, 'streak': 0}
                    
                    with st.form(key=f"form_analyse_nw_{oef['vorm']}"):
                        if len(gekozen_paradigmas) > 1: p_para = st.selectbox("Welk Paradigma?", [""] + gekozen_paradigmas)
                        else: p_para = f"{oef['groep']} | {oef['paradigma']}"

                        beschikbare_naamvallen = list(dict.fromkeys([v['naam'] for v in vlak]))
                        poging = st.selectbox("Naamval/Getal?", [""] + beschikbare_naamvallen, key="sel_decl_analyse")
                        
                        if st.form_submit_button("Controleer Analyse"):
                            if p_para == f"{oef['groep']} | {oef['paradigma']}" and normaliseer_accent(poging) == normaliseer_accent(oef['naam']):
                                st.session_state.gram_stats[vorm_id]['goed'] += 1
                                st.session_state.gram_stats[vorm_id]['streak'] += 1
                                st.session_state.decl_feedback = {'type': 'success', 'msg': f"✓ Juist! **{oef['vorm']}** is de {oef['naam']} van {oef['paradigma']}."}
                                st.session_state.decl_oefening = kies_adaptieve_gram_vorm(vlak, prefix=None)
                                trigger_save(); st.rerun()
                            else:
                                st.session_state.gram_stats[vorm_id]['fout'] += 1
                                st.session_state.gram_stats[vorm_id]['streak'] = 0
                                st.session_state.decl_feedback = {'type': 'error', 'msg': f"✗ Onjuist. **{oef['vorm']}** is de **{oef['naam']}** van paradigma **{oef['paradigma']}**."}
                                trigger_save(); st.rerun()
                            
            else: # Produceren
                st.info("ℹ️ Gebruik Bèta-code. Accenten worden automatisch genegeerd.")
                with st.form(key=f"form_prod_nw_{gekozen_paradigmas}"):
                    fouten_teller = 0
                    for gp in gekozen_paradigmas:
                        g, p = gp.split(" | ")
                        st.markdown(f"#### {p} ({g})")
                        specifiek_vlak = [v for v in vlak if v['paradigma'] == p]
                        for v in specifiek_vlak:
                            inp = st.text_input(v['naam'], key=f"decl_{g}_{p}_{v['naam']}")
                            if inp:
                                if normaliseer_accent(naar_grieks_transliteratie(inp)) == normaliseer_accent(v['vorm']): st.success(f"✓ {v['vorm']}")
                                else: st.error(f"✗ {v['vorm']}"); fouten_teller += 1
                    if st.form_submit_button("Check Rijtjes", key="btn_chk_rijtje_decl") and fouten_teller == 0: st.balloons()

    with menu[5]: # LEESTEKSTEN
        bijbel_db = laad_bijbel_db()
        if not bijbel_db:
            st.warning("De Bijbel-database ontbreekt.")
        else:
            st.subheader("📝 Bijbelse Leesteksten & Exegese")
            
            c1, c2, c3 = st.columns(3)
            with c1:
                alle_lessen = sorted(list(set(veilig_les_nummer(i) for i in st.session_state.data)))
                gekozen = st.multiselect("1. Oefen lessen:", alle_lessen, default=[alle_lessen[0]] if alle_lessen else [])
                actieve_strongs = {str(w['strong']): w for w in st.session_state.data if veilig_les_nummer(w) in gekozen and w.get('strong')}
            
            with c2:
                lees_modus = st.radio("2. Kies een vers:", ["Scavenger Hunt (Willekeurig)", "Kies specifiek vers"])
                if lees_modus == "Kies specifiek vers":
                    boek = st.selectbox("Referentie (Bijv. John 1:1):", list(bijbel_db.keys()))
                    if st.button("Laad dit vers"):
                        st.session_state.huidig_vers = bijbel_db[boek]
                        st.session_state.huidige_vers_referentie = boek
                else:
                    if st.button("Vind passend vers"):
                        passende = [(ref, w, sum(1 for x in w if x['strong'] in actieve_strongs)) for ref, w in bijbel_db.items()]
                        passende = [p for p in passende if p[2] >= 3]
                        if passende:
                            gekozen_vers = random.choice(sorted(passende, key=lambda x: x[2], reverse=True)[:20])
                            st.session_state.huidig_vers = gekozen_vers[1]
                            st.session_state.huidige_vers_referentie = gekozen_vers[0]
                        else:
                            st.warning("Geen verzen gevonden met 3+ bekende woorden.")
            
            with c3:
                tekst_modus = st.radio("3. Hoe wil je de bekende woorden oefenen?", 
                                       ["1. Lees & Spiek (Geen vragen)", 
                                        "2. Vertaal (Meerkeuze)", 
                                        "3. Vertaal (Typen)", 
                                        "4. Masterclass (Ontleden)"])

            st.write("---")

            if st.session_state.huidig_vers:
                st.markdown(f"### 📖 {st.session_state.huidige_vers_referentie}")
                html_zin = ""
                oefen_woorden = []
                
                for w in st.session_state.huidig_vers:
                    tooltip = f"{w['vertaling_bsb']} ({w['parsing_info']})"
                    if w['strong'] in actieve_strongs:
                        basis = actieve_strongs[w['strong']]
                        html_zin += f"<span class='woord-bekend' title='Les {basis.get('les', '?')}: {basis.get('nederlands', '')} | {tooltip}'>{w['grieks']}</span>{w['interpunctie']} "
                        oefen_woorden.append(w)
                    else:
                        html_zin += f"<span class='woord-onbekend' title='{tooltip}'>{w['grieks']}</span>{w['interpunctie']} "
                
                st.markdown(f"<div class='grieks-zin'>{html_zin}</div>", unsafe_allow_html=True)
                st.caption("ℹ️ Hover over een woord om de vertaling te zien. Blauwe woorden komen uit je actieve lessen.")
                
                if oefen_woorden and "1." not in tekst_modus:
                    st.write("### 📝 Oefen je woorden in context")
                    for idx, w in enumerate(oefen_woorden):
                        basis = actieve_strongs[w['strong']]
                        st.markdown(f"**{w['grieks']}** (Basis: {basis['grieks']})")
                        
                        if "2." in tekst_modus: # Meerkeuze
                            opties = [basis['nederlands']] + [i['nederlands'] for i in random.sample(st.session_state.data, min(3, len(st.session_state.data)))]
                            if st.button(basis['nederlands'], key=f"mc_{idx}_{w['grieks']}_correct"): st.success("✓ Goed!")
                            
                        elif "3." in tekst_modus: # Typen
                            with st.form(key=f"form_typ_{idx}"):
                                inp = st.text_input("Vertaling in deze context:")
                                if st.form_submit_button("Check"):
                                    if inp.lower().strip() in basis['nederlands'].lower(): st.success(f"✓ Goed! {basis['nederlands']}")
                                    else: st.error(f"✗ Fout. Het betekent: {basis['nederlands']}")
                                    
                        elif "4." in tekst_modus: # Ontleden (Masterclass)
                            with st.form(key=f"form_mc_{idx}"):
                                st.write("Ontleed dit woord op basis van de Bijbeltekst:")
                                t_inp = st.text_input("1. Betekenis:")
                                mc1, mc2, mc3, mc4 = st.columns(4)
                                with mc1: p_soort = st.selectbox("Woordsoort", ["", "Zelfst. nw.", "Werkwoord", "Bijv. nw.", "Lidwoord", "Voornaamwoord", "Overig"])
                                with mc2: p_naam = st.selectbox("Naamval", ["", "N.v.t.", "Nom", "Gen", "Dat", "Acc", "Voc"])
                                with mc3: p_get = st.selectbox("Getal", ["", "N.v.t.", "ev", "mv"])
                                with mc4: p_ges = st.selectbox("Geslacht", ["", "N.v.t.", "M", "V", "O"])
                                
                                if st.form_submit_button("Controleer Analyse"):
                                    betekenis_ok = t_inp.lower().strip() in basis['nederlands'].lower()
                                    parsing_ok = check_bijbel_parsing(p_soort, p_naam, p_get, p_ges, w['parsing_info'])
                                    
                                    if betekenis_ok and parsing_ok:
                                        st.success(f"✓ Volledig correct! ({w['parsing_info']})")
                                    else:
                                        st.error(f"✗ Onjuist. Officiële data: {w['parsing_info']} | Betekenis: {basis['nederlands']}")
                                        
                st.write("---")
                st.write("### ✍️ Zinsvertaling")
                user_vertaling = st.text_area("Vertaal de hele zin naar het Nederlands:")
                if st.button("Toon officiële vertaling"):
                    officiële_zin = " ".join([w['vertaling_bsb'] for w in st.session_state.huidig_vers])
                    st.success(f"**Originele Engelse vertaling (BSB):** {officiële_zin}")
