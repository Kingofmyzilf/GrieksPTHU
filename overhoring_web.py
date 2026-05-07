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
conn = st.connection("gsheets", type=GSheetsConnection)

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
    tekst = tekst.lower().strip()
    for char in tekst:
        res += mapping.get(char, char)
    if res.endswith('σ'):
        res = res[:-1] + 'ς'
    return res

def normaliseer_accent(woord):
    """Verwijdert diakritische tekens en corrigeert Latijnse 'vervuiling' uit Excel."""
    if pd.notna(woord) and str(woord).strip() != "":
        w = str(woord).strip().lower()
        w = ''.join(c for c in unicodedata.normalize('NFD', w) if unicodedata.category(c) != 'Mn')
        # Corrigeer Latijnse klinkers die vaak meekomen uit Excel-imports
        w = w.replace('a', 'α').replace('e', 'ε').replace('i', 'ι').replace('o', 'ο').replace('u', 'υ')
        return w
    return ""

def splits_sleutel(sleutel):
    """Ontleedt complexe Excel-sleutels naar herbruikbare grammaticale labels."""
    s = str(sleutel).strip()
    wijzen = ["Indicativus", "Conjunctivus", "Optativus", "Imperativus", "Infinitivus", "Participium", "Part"]
    
    for w in wijzen:
        if s.lower().startswith(w.lower()):
            rest = s[len(w):].strip(" _-.")
            return w.capitalize(), rest if rest else "Vorm"
            
    naamvallen = ["nom", "gen", "dat", "acc", "voc"]
    if any(s.lower().startswith(n) for n in naamvallen):
        return "Declinatie", s
    return "Overig", s

def maak_schoon(tekst):
    schoon = re.sub(r'\(.*?\)', '', str(tekst))
    schoon = re.sub(r'\[.*?\]', '', schoon)
    return schoon.replace(';', ',').split(',')[0].strip().lower()

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
                conn.update(data=pd.concat([df, pd.DataFrame(new_data)], ignore_index=True))
                return laad_gebruiker_data(naam)
        return None
            
    user_records = user_df.to_dict('records')
    for r in user_records:
        r['streak_m1'] = int(r.get('streak_m1', 0))
        r['streak_m2'] = int(r.get('streak_m2', 0))
        r['streak_m3'] = int(r.get('streak_m3', 0))
        if 'vormen_data' in r:
            try: r['vormen_data'] = json.loads(str(r['vormen_data']))
            except: r['vormen_data'] = []
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
        conn.update(data=pd.concat([df_andere_gebruikers, pd.DataFrame(huidige_data_kopie)], ignore_index=True))
    except Exception: pass

# --- SESSION STATE ---
for key in ['data', 'sessie_lijst', 'huidig_item', 'huidige_vorm_data', 'feedback', 
            'fouten_huidig_woord', 'huidige_opties', 'last_user', 'actieve_keuze',
            'gram_oefening', 'gram_fouten', 'laatste_filter']:
    if key not in st.session_state: st.session_state[key] = None

# --- HOOFDMENU ---
if st.session_state.data:
    menu = st.tabs(["🚀 Oefenen", "📖 Lijst", "📊 Voortgang", "🏛️ Grammatica"])

    with menu[0]:
        st.write("Vocabulaire overhoring (actief)") # ... bestaande vocab code blijft hier

    with menu[3]: # GRAMMATICA (VERNIEUWD)
        gram_db = laad_grammatica_db()
        if gram_db:
            luo = gram_db["werkwoorden"]["λύω"]
            st.subheader("🏛️ Grammatica Masterclass")
            
            c1, c2, c3 = st.columns(3)
            with c1:
                gram_keuze = st.radio("Oefenvorm:", ["Vormen Analyseren", "Rijtjes Produceren"])
            with c2:
                gekozen_tijd = st.selectbox("1. Tijd/Diathese:", list(luo.keys()))
            with c3:
                wijzen_set = set()
                for k in luo[gekozen_tijd].keys():
                    wijs, _ = splits_sleutel(k)
                    wijzen_set.add(wijs)
                gekozen_wijs_input = st.selectbox("2. Modus/Wijs:", ["Alles"] + sorted(list(wijzen_set)))
            
            gekozen_wijs = None if gekozen_wijs_input == "Alles" else gekozen_wijs_input
            gefilterd_rijtje = { (splits_sleutel(k)[1]): v for k, v in luo[gekozen_tijd].items() 
                                if gekozen_wijs is None or splits_sleutel(k)[0] == gekozen_wijs }

            st.write("---")

            if gram_keuze == "Vormen Analyseren":
                if st.button("Volgende vorm") or not st.session_state.gram_oefening:
                    vlak = [{"naam": k, "vorm": v} for k, v in gefilterd_rijtje.items()]
                    st.session_state.gram_oefening = random.choice(vlak)
                
                oef = st.session_state.gram_oefening
                st.markdown(f"<div class='grieks-woord'>{oef['vorm']}</div>", unsafe_allow_html=True)
                
                if gekozen_wijs == "Participium":
                    # DRIE-TRAPS ANALYSE VOOR PTC
                    ca1, ca2, ca3 = st.columns(3)
                    with ca1: nv = st.selectbox("Naamval:", ["", "Nom.", "Gen.", "Dat.", "Acc."])
                    with ca2: gt = st.selectbox("Getal:", ["", "ev.", "mv."])
                    with ca3: gs = st.selectbox("Geslacht:", ["", "M", "V", "O"])
                    poging = f"{nv} {gt} {gs}".strip()
                else:
                    poging = st.selectbox("Welke persoon/vorm is dit?", [""] + list(gefilterd_rijtje.keys()))
                
                if st.button("Controleer"):
                    if normaliseer_accent(poging) == normaliseer_accent(oef['naam']):
                        st.success(f"✓ Correct! Dit is inderdaad de {oef['naam']}")
                        st.session_state.gram_oefening = None
                    else:
                        st.error(f"✗ Niet juist. Het is de: {oef['naam']}")

            else: # RIJTJES PRODUCEREN (GRID-LOGICA)
                st.info("ℹ️ Gebruik Bèta-code (bijv. 'luon' voor λύων). Accenten worden automatisch genegeerd.")
                
                if gekozen_wijs == "Participium":
                    # TABEL WEERGAVE VOOR PTC
                    for nv in ["Nom.", "Gen.", "Dat.", "Acc."]:
                        for gt in ["ev.", "mv."]:
                            st.markdown(f"<div class='grid-label'>{nv} {gt}</div>", unsafe_allow_html=True)
                            cols = st.columns(3)
                            for i, ges in enumerate(["M", "V", "O"]):
                                label = f"{nv} {gt} {ges}"
                                correct = gefilterd_rijtje.get(label, "")
                                if correct:
                                    inp = cols[i].text_input(ges, key=f"ptc_{gekozen_tijd}_{label}")
                                    if inp:
                                        if normaliseer_accent(naar_grieks_transliteratie(inp)) == normaliseer_accent(correct):
                                            cols[i].caption(f"✅ {correct}")
                                        else:
                                            cols[i].caption(f"❌ {correct}")
                else:
                    # STANDAARD LIJST VOOR INDICATIVUS ETC.
                    for label, correct in gefilterd_rijtje.items():
                        inp = st.text_input(label, key=f"std_{gekozen_tijd}_{label}")
                        if inp:
                            if normaliseer_accent(naar_grieks_transliteratie(inp)) == normaliseer_accent(correct):
                                st.success(f"✓ {correct}")
                            else:
                                st.error(f"✗ {correct}")

    with menu[1]: # HERSTELDE LIJST
        if st.session_state.data:
            les_filter = st.selectbox("Bekijk les:", sorted(list(set(i.get('les', 1) for i in st.session_state.data))))
            df = pd.DataFrame([i for i in st.session_state.data if i.get('les', 1) == les_filter])
            st.dataframe(df[['grieks', 'nederlands', 'streak_m1', 'streak_m2', 'streak_m3']], use_container_width=True)

    with menu[2]: # HERSTELDE VOORTGANG
        if st.session_state.data:
            lessen = sorted(list(set(i.get('les', 1) for i in st.session_state.data)))
            stats = []
            for l in lessen:
                it = [i for i in st.session_state.data if i.get('les', 1) == l]
                beheerst = len([i for i in it if (int(i.get('streak_m1',0))+int(i.get('streak_m2',0))+int(i.get('streak_m3',0)))/3 >= 20])
                stats.append((beheerst/len(it))*100 if it else 0)
            fig, ax = plt.subplots()
            ax.bar(lessen, stats, color='#33ccff')
            ax.set_ylim(0, 100)
            st.pyplot(fig)
