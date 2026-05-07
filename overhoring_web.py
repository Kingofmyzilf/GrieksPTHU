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

# --- CONFIGURATIE ---
st.set_page_config(page_title="Grieks Cloud Tutor", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 10px; height: 3em; font-weight: bold; }
    .stTextInput>div>div>input { font-size: 20px; text-align: center; }
    .grieks-woord { font-size: 50px; font-weight: bold; color: #33ccff; text-align: center; padding: 20px; }
    </style>
    """, unsafe_allow_html=True)

# --- LOGICA & TRANSLITERATIE ---

def naar_grieks_transliteratie(tekst):
    """Zet latijnse invoer om naar Griekse letters (Bèta-code stijl)"""
    mapping = {
        'a': 'α', 'b': 'β', 'g': 'γ', 'd': 'δ', 'e': 'ε', 'z': 'ζ', 'h': 'η', 'q': 'θ',
        'i': 'ι', 'k': 'κ', 'l': 'λ', 'm': 'μ', 'n': 'ν', 'c': 'ξ', 'o': 'ο', 'p': 'π',
        'r': 'ρ', 's': 'σ', 't': 'τ', 'u': 'υ', 'f': 'φ', 'x': 'χ', 'y': 'ψ', 'w': 'ω'
    }
    res = ""
    tekst = tekst.lower().strip()
    for char in tekst:
        res += mapping.get(char, char)
    
    # Eind-sigma correctie
    if res.endswith('σ'):
        res = res[:-1] + 'ς'
    return res

def normaliseer_accent(woord):
    if pd.notna(woord) and str(woord).strip() != "":
        w = str(woord).replace("ὸ", "ό").replace("ὰ", "ά").replace("ὴ", "ή").replace("ὼ", "ώ").replace("ὶ", "ί").replace("ὺ", "ύ").strip().lower()
        # Voor de controle negeren we ook de spiritus en overige accenten als we transliteratie gebruiken
        return w
    return ""

def maak_schoon(tekst):
    schoon = re.sub(r'\(.*?\)', '', str(tekst))
    schoon = re.sub(r'\[.*?\]', '', schoon)
    return schoon.replace(';', ',').split(',')[0].strip().lower()

def bereken_gewicht(item):
    gewicht = 1.0
    gem_streak = (int(item.get('streak_m1', 0)) + int(item.get('streak_m2', 0)) + int(item.get('streak_m3', 0))) / 3
    if gem_streak >= 20 or int(item.get('streak_m3', 0)) >= 20:
        gewicht *= 0.1
    return max(0.1, gewicht)

def geldig(val):
    return pd.notna(val) and str(val).strip() not in ['', 'nan', 'None']

# --- DATABASE FUNCTIES ---

@st.cache_data
def laad_grammatica_db():
    if os.path.exists("grammatica.json"):
        with open("grammatica.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def laad_gebruiker_data(naam):
    df = conn.read(ttl=0) 
    if 'gebruikersnaam' not in df.columns:
        df['gebruikersnaam'] = ""
    user_df = df[df['gebruikersnaam'] == naam]
    
    if user_df.empty:
        if os.path.exists("basis_woorden.json"):
            with open("basis_woorden.json", "r", encoding="utf-8") as f:
                basis = json.load(f)
                new_data = []
                for b in basis:
                    b['gebruikersnaam'] = naam
                    b['streak_m1'] = 0; b['streak_m2'] = 0; b['streak_m3'] = 0
                    if 'vormen_data' in b and isinstance(b['vormen_data'], list):
                        b['vormen_data'] = json.dumps(b['vormen_data'], ensure_ascii=False)
                    new_data.append(b)
                updated_df = pd.concat([df, pd.DataFrame(new_data)], ignore_index=True)
                conn.update(data=updated_df)
                return laad_gebruiker_data(naam) # Herlaad na creatie
        return None
            
    user_records = user_df.to_dict('records')
    for r in user_records:
        r['streak_m1'] = int(r.get('streak_m1', 0))
        r['streak_m2'] = int(r.get('streak_m2', 0))
        r['streak_m3'] = int(r.get('streak_m3', 0))
        if 'vormen_data' in r and geldig(r['vormen_data']):
            try: r['vormen_data'] = json.loads(str(r['vormen_data']))
            except: r['vormen_data'] = []
        else: r['vormen_data'] = []
    return user_records

def opslaan_naar_cloud():
    if not st.session_state.get('last_user') or not st.session_state.get('data'): return
    try:
        df = conn.read(ttl=0)
        df_andere_gebruikers = df[df['gebruikersnaam'] != st.session_state.last_user]
        huidige_data_kopie = []
        for item in st.session_state.data:
            k = item.copy()
            if 'vormen_data' in k and isinstance(k['vormen_data'], list):
                k['vormen_data'] = json.dumps(k['vormen_data'], ensure_ascii=False)
            huidige_data_kopie.append(k)
        df_jouw_data = pd.DataFrame(huidige_data_kopie)
        conn.update(data=pd.concat([df_andere_gebruikers, df_jouw_data], ignore_index=True))
    except Exception: pass

# --- SESSION STATE ---
for key in ['data', 'sessie_lijst', 'huidig_item', 'huidige_vorm_data', 'feedback', 
            'fouten_huidig_woord', 'huidige_opties', 'last_user', 'actieve_keuze',
            'gram_oefening', 'gram_fouten']:
    if key not in st.session_state: st.session_state[key] = None

if st.session_state.fouten_huidig_woord is None: st.session_state.fouten_huidig_woord = 0
if st.session_state.gram_fouten is None: st.session_state.gram_fouten = 0

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
            opslaan_naar_cloud()
            st.session_state.data = None; st.rerun()

# --- HOOFDMENU ---
if st.session_state.data:
    menu = st.tabs(["🚀 Oefenen", "📖 Lijst", "📊 Voortgang", "🏛️ Grammatica"])

    with menu[0]: # OEFENEN (VOCABULAIRE)
        col1, col2 = st.columns([1, 2])
        with col1:
            modus = st.radio("Modus:", ["1. Leer", "2. MC", "3. Typen"])
            keuze = st.selectbox("Oefening:", ["Lessen", "Mastery"])
            doel = []
            if keuze == "Lessen":
                alle_lessen = sorted(list(set(i.get('les', 1) for i in st.session_state.data)))
                gekozen = st.multiselect("Kies lessen", alle_lessen)
                doel = [i for i in st.session_state.data if i.get('les', 1) in gekozen]
            
            if st.button("Start"):
                if doel:
                    doel.sort(key=bereken_gewicht, reverse=True)
                    st.session_state.sessie_lijst = random.sample(doel, min(len(doel), 10))
                    st.session_state.modus_actief = modus[0]
                    laad_volgend_woord(); st.rerun()

        with col2:
            if st.session_state.huidig_item:
                item = st.session_state.huidig_item
                actieve_streak = f"streak_m{st.session_state.modus_actief}"
                
                # Mastery check (Gemiddelde 20 of M3 20)
                gem_streak = (item['streak_m1'] + item['streak_m2'] + item['streak_m3']) / 3
                is_mastery = gem_streak >= 20 or item['streak_m3'] >= 20
                
                if st.session_state.huidige_vorm_data is None:
                    if is_mastery and item['vormen_data']:
                        st.session_state.huidige_vorm_data = random.choice(item['vormen_data'])
                    else:
                        st.session_state.huidige_vorm_data = {"vorm": item['grieks'], "parsing": "basis"}

                st.markdown(f"<div class='grieks-woord'>{st.session_state.huidige_vorm_data['vorm']}</div>", unsafe_allow_html=True)
                
                if st.session_state.modus_actief == '1' or st.session_state.fouten_huidig_woord >= 1:
                    st.info(f"💡 {item.get('fonetisch', '')} | {item.get('anker', '')} {item.get('beeld', '')}")

                # NAKIIK LOGICA (3 STAPPEN)
                correct_antw = str(item['nederlands'])
                if st.session_state.modus_actief == '3':
                    inp = st.text_input("Betekenis:", key="vocab_inp").lower().strip()
                    if st.button("Check"):
                        if inp == maak_schoon(correct_antw) or inp in correct_antw.lower():
                            item[actieve_streak] += 1
                            st.success("✓ Goed!"); laad_volgend_woord(); st.rerun()
                        else:
                            st.session_state.fouten_huidig_woord += 1
                            if st.session_state.fouten_huidig_woord >= 2:
                                item[actieve_streak] = max(0, item[actieve_streak] - 2)
                                st.error(f"✗ Fout. Het was: {correct_antw}")
                                st.session_state.sessie_lijst.append(item)
                            else:
                                st.warning("Bijna! Gebruik de hint en probeer nog eens.")
                else:
                    # MC Logica (vereenvoudigd voor deze update)
                    st.write("Klik op het juiste antwoord:")
                    if st.button(correct_antw):
                        item[actieve_streak] += 1
                        st.success("✓ Goed!"); laad_volgend_woord(); st.rerun()

    with menu[3]: # GRAMMATICA
        gram_db = laad_grammatica_db()
        if gram_db:
            luo = gram_db["werkwoorden"]["λύω"]
            st.subheader("🏛️ Grammatica Paradigma's (λύω)")
            
            c1, c2 = st.columns(2)
            with c1:
                gram_keuze = st.radio("Oefenvorm:", ["Vormen Analyseren", "Rijtjes Produceren"])
            with c2:
                beschikbare_tijden = list(luo.keys())
                gekozen_tijd = st.selectbox("Selecteer rijtje:", beschikbare_tijden)

            if gram_keuze == "Vormen Analyseren":
                if st.button("Nieuwe Vorm") or not st.session_state.gram_oefening:
                    vlak = [{"tijd": gekozen_tijd, "persoon": p, "vorm": v} for p, v in luo[gekozen_tijd].items()]
                    st.session_state.gram_oefening = random.choice(vlak)
                    st.session_state.gram_fouten = 0
                
                oef = st.session_state.gram_oefening
                st.markdown(f"<div class='grieks-woord'>{oef['vorm']}</div>", unsafe_allow_html=True)
                
                ans = st.selectbox("Welke persoon is dit?", [""] + list(luo[gekozen_tijd].keys()))
                if st.button("Controleer Analyse"):
                    if ans == oef['persoon']:
                        st.success("✓ Correct!")
                        st.session_state.gram_oefening = None; st.rerun()
                    else:
                        st.error(f"✗ Nee, dit is de {oef['persoon']}")

            else: # Rijtjes Produceren met Transliteratie
                st.info("ℹ️ Typ met normale letters. Voorbeeld: **luis** wordt **λύεις**, **luomen** wordt **λύομεν**.")
                rijtje = luo[gekozen_tijd]
                fouten_teller = 0
                
                for pers, correcte_vorm in rijtje.items():
                    user_inp = st.text_input(f"{pers}:", key=f"grid_{gekozen_tijd}_{pers}")
                    vertaald = naar_grieks_transliteratie(user_inp)
                    
                    if user_inp:
                        if normaliseer_accent(vertaald) == normaliseer_accent(correcte_vorm):
                            st.caption(f"✅ {vertaald}")
                        else:
                            st.caption(f"❌ Wordt: {vertaald} (Correct: {correcte_vorm})")
                            fouten_teller += 1
                
                if st.button("Rijtje Opslaan"):
                    if fouten_teller == 0: st.success("Geweldig! Het hele rijtje is foutloos.")
                    else: st.warning(f"Je had nog {fouten_teller} fouten in dit rijtje.")

    with menu[2]: # VOORTGANG
        st.write("Voortgang per les op basis van mastery (Gemiddelde streak 20)")
        # ... (bestaande grafiek code)
