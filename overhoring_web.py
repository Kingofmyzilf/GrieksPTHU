import streamlit as st
from streamlit_gsheets import GSheetsConnection
import json
import random
import re
import math
import pandas as pd
import matplotlib.pyplot as plt
import os
import ast
import unicodedata

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
    .grid-label { font-weight: bold; color: #33ccff; margin-bottom: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- LOGICA & TRANSLITERATIE ---

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
    # Gebruik de scores uit het item (die we uit vocab_stats hebben gehaald)
    gewicht += (int(item.get('score_fout', 0)) * 1.5)
    
    sm1, sm2, sm3 = int(item.get('streak_m1', 0)), int(item.get('streak_m2', 0)), int(item.get('streak_m3', 0))
    gem_streak = (sm1 + sm2 + sm3) / 3
    if gem_streak >= 20 or sm3 >= 20: gewicht *= 0.1
    return max(0.1, gewicht)

def kies_adaptieve_gram_vorm(vlak, prefix):
    if not vlak: return None
    weights = []
    for v in vlak:
        vorm_id = f"{prefix}_{v['naam']}"
        stats = st.session_state.gram_stats.get(vorm_id, {'goed': 0, 'fout': 0, 'streak': 0})
        w = max(0.1, 1.0 + (stats['fout'] * 1.5) - (stats['streak'] * 0.4))
        weights.append(w)
    return random.choices(vlak, weights=weights, k=1)[0]

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

def laad_gebruiker_data(naam):
    """Laden van data via de Single Row methode."""
    try:
        df = conn.read(ttl=0)
        # Zoek naar de unieke rij van de gebruiker
        user_row = df[df['gebruikersnaam'] == naam]
        
        # Inladen basiswoorden (de blauwdruk)
        if os.path.exists("basis_woorden.json"):
            with open("basis_woorden.json", "r", encoding="utf-8") as f:
                vocab_basis = json.load(f)
        else:
            st.error("basis_woorden.json ontbreekt!")
            return None

        if user_row.empty:
            # Nieuwe gebruiker: initialiseer lege stats
            st.session_state.vocab_stats = {}
            st.session_state.gram_stats = {}
            # Maak de rij aan in de cloud
            opslaan_naar_cloud_optimized(naam, {}, {})
        else:
            # Bestaande gebruiker: parse de JSON kolommen
            try:
                st.session_state.vocab_stats = json.loads(str(user_row.iloc[0].get('vocab_stats', '{}')))
            except:
                st.session_state.vocab_stats = {}
            
            try:
                st.session_state.gram_stats = json.loads(str(user_row.iloc[0].get('gram_stats', '{}')))
            except:
                st.session_state.gram_stats = {}

        # Merge de stats met de basiswoorden voor gebruik in de app
        for word in vocab_basis:
            # Zoek in vocab_stats op de Griekse tekst
            stats = st.session_state.vocab_stats.get(word['grieks'], {'m1':0, 'm2':0, 'm3':0, 'g':0, 'f':0})
            word['streak_m1'] = stats.get('m1', 0)
            word['streak_m2'] = stats.get('m2', 0)
            word['streak_m3'] = stats.get('m3', 0)
            word['score_goed'] = stats.get('g', 0)
            word['score_fout'] = stats.get('f', 0)
            
        return vocab_basis
    except Exception as e:
        st.error(f"Fout bij laden: {e}")
        return None

def opslaan_naar_cloud_optimized(naam, vocab_stats, gram_stats):
    """Slaat alles op in één enkele rij in Google Sheets."""
    try:
        df = conn.read(ttl=0)
        # Verwijder oude rij van deze gebruiker indien aanwezig
        df = df[df['gebruikersnaam'] != naam]
        
        new_row = pd.DataFrame([{
            'gebruikersnaam': naam,
            'vocab_stats': json.dumps(vocab_stats, ensure_ascii=False),
            'gram_stats': json.dumps(gram_stats, ensure_ascii=False)
        }])
        
        updated_df = pd.concat([df, new_row], ignore_index=True)
        conn.update(data=updated_df)
    except Exception:
        pass

def trigger_save():
    """Hulpmiddel om huidige sessie-stats om te zetten naar de cloud-indeling."""
    if not st.session_state.get('last_user'): return
    
    # Update vocab_stats dictionary vanuit de huidige data in memory
    for word in st.session_state.data:
        st.session_state.vocab_stats[word['grieks']] = {
            'm1': word.get('streak_m1', 0),
            'm2': word.get('streak_m2', 0),
            'm3': word.get('streak_m3', 0),
            'g': word.get('score_goed', 0),
            'f': word.get('score_fout', 0)
        }
    
    opslaan_naar_cloud_optimized(
        st.session_state.last_user, 
        st.session_state.vocab_stats, 
        st.session_state.gram_stats
    )

# --- SESSION STATE ---
for key in ['data', 'sessie_lijst', 'huidig_item', 'huidige_vorm_data', 'feedback', 
            'fouten_huidig_woord', 'huidige_opties', 'last_user', 'actieve_keuze',
            'gram_oefening', 'gram_fouten', 'laatste_filter',
            'decl_oefening', 'laatste_filter_decl', 'gram_feedback', 'decl_feedback',
            'vocab_stats', 'gram_stats']:
    if key not in st.session_state: st.session_state[key] = None

if 'vocab_stats' not in st.session_state or st.session_state.vocab_stats is None: st.session_state.vocab_stats = {}
if 'gram_stats' not in st.session_state or st.session_state.gram_stats is None: st.session_state.gram_stats = {}
if st.session_state.fouten_huidig_woord is None: st.session_state.fouten_huidig_woord = 0

def laad_volgend_woord():
    st.session_state.huidig_item = st.session_state.sessie_lijst.pop(0) if st.session_state.sessie_lijst else None
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
    menu = st.tabs(["🚀 Woordenschat", "📖 Lijst", "📊 Voortgang", "🏛️ Werkwoorden", "🏷️ Naamwoorden"])

    with menu[0]: # WOORDENSCHAT
        col1, col2 = st.columns([1, 2])
        with col1:
            modus = st.radio("Modus:", ["1. Leer", "2. MC", "3. Typen"])
            keuze = st.selectbox("Oefening:", ["Lessen", "Mastery"])
            doel = []
            if keuze == "Lessen":
                alle_lessen = sorted(list(set(word.get('les', 1) for word in st.session_state.data)))
                gekozen = st.multiselect("Kies lessen", alle_lessen)
                doel = [word for word in st.session_state.data if word.get('les', 1) in gekozen]
            elif keuze == "Mastery":
                doel = [word for word in st.session_state.data if ((int(word.get('streak_m1',0))+int(word.get('streak_m2',0))+int(word.get('streak_m3',0)))/3) >= 20]
            
            if st.button("Start Sessie"):
                if doel:
                    doel.sort(key=bereken_gewicht, reverse=True)
                    st.session_state.sessie_lijst = random.sample(doel, min(len(doel), 10))
                    st.session_state.modus_actief = str(modus[0])
                    laad_volgend_woord(); st.rerun()

        with col2:
            if st.session_state.huidig_item:
                item = st.session_state.huidig_item
                act_streak_key = f"streak_m{st.session_state.modus_actief}"
                
                sm1, sm2, sm3 = int(item.get('streak_m1', 0)), int(item.get('streak_m2', 0)), int(item.get('streak_m3', 0))
                gem_streak = (sm1 + sm2 + sm3) / 3
                is_mastery = gem_streak >= 20 or sm3 >= 20
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

                if st.session_state.modus_actief == '1' or st.session_state.fouten_huidig_woord >= 1:
                    st.info(f"💡 {item.get('fonetisch', '')} | {item.get('anker', '')} {item.get('beeld', '')}")

                correct_antw = str(item.get('nederlands', ''))
                
                if st.session_state.modus_actief == '3':
                    inp = st.text_input("Betekenis:", key=f"vocab_inp_{item.get('grieks')}").lower().strip()
                    if is_mastery and heeft_vormen:
                        p_vorm = st.text_input("Vorm:", key=f"inp_v_{item.get('grieks')}").lower().strip()
                    else:
                        p_vorm = huidige_parsing.lower().strip()

                    if st.button("Check Antwoord"):
                        if (inp == maak_schoon(correct_antw) or inp in correct_antw.lower()) and (p_vorm == huidige_parsing.lower().strip()):
                            item[act_streak_key] = int(item.get(act_streak_key, 0)) + 1
                            item['score_goed'] = int(item.get('score_goed', 0)) + 1
                            st.success("✓ Goed!"); trigger_save(); laad_volgend_woord(); st.rerun()
                        else:
                            st.session_state.fouten_huidig_woord = int(st.session_state.fouten_huidig_woord) + 1
                            if st.session_state.fouten_huidig_woord >= 2:
                                item[act_streak_key] = max(0, int(item.get(act_streak_key, 0)) - 2)
                                item['score_fout'] = int(item.get('score_fout', 0)) + 1
                                st.error(f"✗ Fout. Het was: {correct_antw}")
                                trigger_save(); st.session_state.sessie_lijst.append(item); laad_volgend_woord(); st.rerun()
                            else:
                                st.warning("Bijna! Gebruik de hint en probeer nog eens.")
                else:
                    correct_optie = f"{correct_antw} ({huidige_parsing})" if (is_mastery and heeft_vormen) else correct_antw
                    if not st.session_state.huidige_opties:
                        afleiders = [str(i.get('nederlands', '')) for i in st.session_state.data if i.get('grieks') != item.get('grieks')]
                        opties = list(set([str(a) for a in afleiders if a]))[:3] + [correct_optie]
                        st.session_state.huidige_opties = list(dict.fromkeys(opties))
                        random.shuffle(st.session_state.huidige_opties)
                    
                    cols = st.columns(2)
                    for idx, optie in enumerate(st.session_state.huidige_opties):
                        if cols[idx % 2].button(optie, key=f"btn_{idx}_{item.get('grieks')}"):
                            if optie == correct_optie:
                                item[act_streak_key] = int(item.get(act_streak_key, 0)) + 1
                                item['score_goed'] = int(item.get('score_goed', 0)) + 1
                                st.success("✓ Juist!"); trigger_save(); laad_volgend_woord(); st.rerun()
                            else:
                                st.session_state.fouten_huidig_woord = int(st.session_state.fouten_huidig_woord) + 1
                                if st.session_state.fouten_huidig_woord >= 2:
                                    item[act_streak_key] = max(0, int(item.get(act_streak_key, 0)) - 2)
                                    item['score_fout'] = int(item.get('score_fout', 0)) + 1
                                    st.error(f"✗ Fout. Het was: {correct_optie}"); trigger_save()
                                    st.session_state.sessie_lijst.append(item); laad_volgend_woord(); st.rerun()
                                else:
                                    st.warning("Probeer nog eens!")

                st.caption(f"Streaks: M1:{item.get('streak_m1')} M2:{item.get('streak_m2')} M3:{item.get('streak_m3')}")

    with menu[3]: # WERKWOORDEN
        gram_db = laad_grammatica_db()
        if gram_db and "λύω" in gram_db.get("werkwoorden", {}):
            luo = gram_db["werkwoorden"]["λύω"]
            st.subheader("🏛️ Verbale Morfologie (λύω)")
            
            c1, c2, c3 = st.columns(3)
            with c1: gram_keuze = st.radio("Modus:", ["Visueel Leren (Tabel)", "Vormen Analyseren", "Rijtjes Produceren"])
            with c2: gekozen_tijd = st.selectbox("1. Tijd/Diathese:", list(luo.keys()))
            with c3:
                wijzen_set = set()
                for k in luo[gekozen_tijd].keys(): wijzen_set.add(splits_sleutel(k)[0])
                gekozen_wijs_input = st.selectbox("2. Modus/Wijs:", ["Alles"] + sorted(list(wijzen_set)))
            
            gefilterd_rijtje = { splits_sleutel(k)[1]: v for k, v in luo[gekozen_tijd].items() 
                                if gekozen_wijs_input == "Alles" or splits_sleutel(k)[0] == gekozen_wijs_input }

            if st.session_state.gram_feedback:
                if st.session_state.gram_feedback['type'] == 'success': st.success(st.session_state.gram_feedback['msg'])
                else: st.error(st.session_state.gram_feedback['msg'])
                st.session_state.gram_feedback = None

            if gram_keuze == "Visueel Leren (Tabel)":
                st.dataframe(pd.DataFrame(list(gefilterd_rijtje.items()), columns=["Vorm", "Griekse Vorm"]), use_container_width=True, hide_index=True)
            elif gram_keuze == "Vormen Analyseren":
                huidig_filter = f"{gekozen_tijd}_{gekozen_wijs_input}"
                prefix = f"ww_{gekozen_tijd}"
                vlak = [{"naam": k, "vorm": v} for k, v in gefilterd_rijtje.items()]
                if st.button("Nieuwe Vorm") or not st.session_state.gram_oefening or st.session_state.get('laatste_filter') != huidig_filter:
                    st.session_state.gram_oefening = kies_adaptieve_gram_vorm(vlak, prefix)
                    st.session_state.laatste_filter = huidig_filter
                
                oef = st.session_state.gram_oefening
                if oef:
                    st.markdown(f"<div class='grieks-woord'>{oef['vorm']}</div>", unsafe_allow_html=True)
                    vorm_id = f"{prefix}_{oef['naam']}"
                    if vorm_id not in st.session_state.gram_stats: st.session_state.gram_stats[vorm_id] = {'goed': 0, 'fout': 0, 'streak': 0}

                    if "Participium" in gekozen_wijs_input:
                        ca1, ca2, ca3 = st.columns(3)
                        with ca1: nv = st.selectbox("Naamval:", ["", "Nom.", "Gen.", "Dat.", "Acc."])
                        with ca2: gt = st.selectbox("Getal:", ["", "ev.", "mv."])
                        with ca3: gs = st.selectbox("Geslacht:", ["", "M", "V", "O"])
                        poging = f"{nv} {gt} {gs}".strip()
                    else:
                        poging = st.selectbox("Welke persoon/vorm is dit?", [""] + list(gefilterd_rijtje.keys()))
                    
                    if st.button("Controleer"):
                        if normaliseer_accent(poging) == normaliseer_accent(oef['naam']):
                            st.session_state.gram_stats[vorm_id]['goed'] += 1
                            st.session_state.gram_stats[vorm_id]['streak'] += 1
                            st.session_state.gram_feedback = {'type': 'success', 'msg': f"✓ Correct!"}
                            st.session_state.gram_oefening = kies_adaptieve_gram_vorm(vlak, prefix)
                            trigger_save(); st.rerun()
                        else:
                            st.session_state.gram_stats[vorm_id]['fout'] += 1
                            st.session_state.gram_stats[vorm_id]['streak'] = 0
                            st.session_state.gram_feedback = {'type': 'error', 'msg': f"✗ Het was de: {oef['naam']}"}
                            trigger_save(); st.rerun()
            else: # Produceren
                fouten = 0
                for label, correct in gefilterd_rijtje.items():
                    inp = st.text_input(label, key=f"std_{gekozen_tijd}_{label}")
                    if inp and normaliseer_accent(naar_grieks_transliteratie(inp)) != normaliseer_accent(correct):
                        st.caption(f"❌ {correct}"); fouten += 1
                if st.button("Klaar") and fouten == 0: st.balloons()

    with menu[4]: # NAAMWOORDEN
        decl_db = laad_declinaties_db()
        if decl_db:
            st.subheader("🏷️ Nominale Morfologie")
            dc1, dc2, dc3 = st.columns(3)
            with dc1: decl_keuze = st.radio("Modus:", ["Visueel Leren (Tabel)", "Vormen Analyseren", "Rijtjes Produceren"], key="decl_radio")
            with dc2: gekozen_groep = st.selectbox("Groep:", list(decl_db["Declinaties"].keys()))
            with dc3: gekozen_paradigma = st.selectbox("Paradigma:", list(decl_db["Declinaties"][gekozen_groep].keys()))
            
            gefilterd_rijtje = decl_db["Declinaties"][gekozen_groep][gekozen_paradigma]

            if st.session_state.decl_feedback:
                if st.session_state.decl_feedback['type'] == 'success': st.success(st.session_state.decl_feedback['msg'])
                else: st.error(st.session_state.decl_feedback['msg'])
                st.session_state.decl_feedback = None

            if decl_keuze == "Visueel Leren (Tabel)":
                st.dataframe(pd.DataFrame(list(gefilterd_rijtje.items()), columns=["Naamval", "Vorm"]), use_container_width=True, hide_index=True)
            elif decl_keuze == "Vormen Analyseren":
                huidig_filter = f"{gekozen_groep}_{gekozen_paradigma}"
                prefix = f"nw_{gekozen_groep}_{gekozen_paradigma}"
                vlak = [{"naam": k, "vorm": v} for k, v in gefilterd_rijtje.items()]
                if st.button("Nieuwe Vorm", key="btn_nw_decl") or not st.session_state.get('decl_oefening') or st.session_state.get('laatste_filter_decl') != huidig_filter:
                    st.session_state.decl_oefening = kies_adaptieve_gram_vorm(vlak, prefix)
                    st.session_state.laatste_filter_decl = huidig_filter
                
                oef = st.session_state.decl_oefening
                if oef:
                    st.markdown(f"<div class='grieks-woord'>{oef['vorm']}</div>", unsafe_allow_html=True)
                    vorm_id = f"{prefix}_{oef['naam']}"
                    if vorm_id not in st.session_state.gram_stats: st.session_state.gram_stats[vorm_id] = {'goed': 0, 'fout': 0, 'streak': 0}
                    poging = st.selectbox("Naamval/Getal?", [""] + list(gefilterd_rijtje.keys()), key="sel_decl_analyse")
                    if st.button("Controleer"):
                        if normaliseer_accent(poging) == normaliseer_accent(oef['naam']):
                            st.session_state.gram_stats[vorm_id]['goed'] += 1
                            st.session_state.gram_stats[vorm_id]['streak'] += 1
                            st.session_state.decl_feedback = {'type': 'success', 'msg': "✓ Juist!"}
                            st.session_state.decl_oefening = kies_adaptieve_gram_vorm(vlak, prefix)
                            trigger_save(); st.rerun()
                        else:
                            st.session_state.gram_stats[vorm_id]['fout'] += 1
                            st.session_state.gram_stats[vorm_id]['streak'] = 0
                            st.session_state.decl_feedback = {'type': 'error', 'msg': f"✗ Het was: {oef['naam']}"}
                            trigger_save(); st.rerun()

    with menu[1]: # LIJST
        if st.session_state.data:
            st.dataframe(pd.DataFrame(st.session_state.data)[['grieks', 'nederlands', 'streak_m1', 'streak_m2', 'streak_m3']], use_container_width=True)

    with menu[2]: # VOORTGANG
        if st.session_state.data:
            lessen = sorted(list(set(word.get('les', 1) for word in st.session_state.data)))
            stats = [len([w for w in st.session_state.data if w.get('les') == l and (w['streak_m1']+w['streak_m2']+w['streak_m3'])/3 >= 20]) / len([w for w in st.session_state.data if w.get('les') == l]) * 100 for l in lessen]
            fig, ax = plt.subplots(); ax.bar(lessen, stats, color='#33ccff'); st.pyplot(fig)
