import streamlit as st
import json
import random
import re
import math
import pandas as pd
import matplotlib.pyplot as plt
import os # Voeg deze helemaal bovenaan je script toe bij de andere imports

# --- SIDEBAR: DATA BEHEER ---
with st.sidebar:
    st.header("📂 Jouw Voortgang")
    uploaded_file = st.file_uploader("Upload jouw opgeslagen JSON", type=["json", "txt", ""])
    
    # 1. Als iemand een bestand uploadt:
    if uploaded_file is not None:
        st.session_state.data = json.load(uploaded_file)
        st.success("Jouw voortgang is geladen!")

    # 2. Als er GEEN bestand is, laad dan de schone basislijst van GitHub:
    elif st.session_state.data is None:
        if os.path.exists("basis_woorden.json"):
            with open("basis_woorden.json", "r", encoding="utf-8") as f:
                st.session_state.data = json.load(f)
            st.info("Nieuwe sessie gestart met basiswoorden!")

    # 3. De download knop (blijft hetzelfde)
    if st.session_state.data:
        json_data = json.dumps(st.session_state.data, indent=2)
        st.download_button(
            label="💾 Voortgang Opslaan (Download)",
            data=json_data,
            file_name="mijn_grieks_voortgang.json",
            mime="application/json"
        )

# --- CONFIGURATIE ---
st.set_page_config(page_title="Gemini Grieks Tutor", layout="wide")

# Custom CSS voor mobiele optimalisatie
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 10px; height: 3em; font-weight: bold; }
    .stTextInput>div>div>input { font-size: 20px; text-align: center; }
    .grieks-woord { font-size: 50px; font-weight: bold; color: #33ccff; text-align: center; padding: 20px; }
    </style>
    """, unsafe_allow_html=True)

# --- LOGICA ---

def maak_schoon(tekst):
    schoon = re.sub(r'\(.*?\)', '', tekst)
    schoon = re.sub(r'\[.*?\]', '', schoon)
    return schoon.replace(';', ',').split(',')[0].strip().lower()

def bereken_gewicht(item):
    """Urgentie op basis van NT-frequentie en foutenlast."""
    gewicht = 1.0
    freq = item.get('frequentie_nt', 0)
    if freq > 0:
        # NT-frequentiecijfers sturen de prioriteit
        gewicht += math.log10(freq + 1)
    gewicht += (item.get('score_fout', 0) * 1.5)
    if item.get('streak', 0) >= 5:
        gewicht *= 0.1
    return max(0.1, gewicht)

# --- SESSION STATE (GEHEUGEN VAN DE WEBSITE) ---
if 'data' not in st.session_state:
    st.session_state.data = None
if 'sessie_lijst' not in st.session_state:
    st.session_state.sessie_lijst = []
if 'huidig_item' not in st.session_state:
    st.session_state.huidig_item = None
if 'feedback' not in st.session_state:
    st.session_state.feedback = None

# --- SIDEBAR: DATA BEHEER ---
with st.sidebar:
    st.header("📂 Jouw Voortgang")
    uploaded_file = st.file_uploader("Upload grieks_vocabulaire.json", type="json")
    
    if uploaded_file is not None and st.session_state.data is None:
        st.session_state.data = json.load(uploaded_file)
        st.success("Voortgang geladen!")

    if st.session_state.data:
        json_data = json.dumps(st.session_state.data, indent=2)
        st.download_button(
            label="💾 Voortgang Opslaan (Download)",
            data=json_data,
            file_name="grieks_vocabulaire.json",
            mime="application/json"
        )
        
        if st.button("🧹 Reset alle scores"):
            for item in st.session_state.data:
                item['score_goed'] = 0
                item['score_fout'] = 0
                item['streak'] = 0
            st.rerun()

# --- HOOFDMENU ---
if st.session_state.data is None:
    st.title("Welkom bij de Grieks Tutor")
    st.info("Upload eerst het `grieks_vocabulaire.json` bestand in de zijbalk om te beginnen.")
else:
    menu = st.tabs(["🚀 Oefenen", "📖 Woordenlijst", "📊 Voortgang"])

    with menu[0]: # OEFENEN
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("Instellingen")
            modus = st.radio("Kies Modus:", ["1. Leer (Hulp + MC)", "2. Leer (MC)", "3. Overhoor (Typen)"])
            
            keuze = st.selectbox("Wat wil je oefenen?", ["Alles", "Lessen", "Woordsoort", "Mastery (<5 streak)"])
            
            doel = st.session_state.data
            if keuze == "Lessen":
                les_nr = st.number_input("Les nummer", min_value=1, value=1)
                doel = [i for i in st.session_state.data if i['les'] == les_nr]
            elif keuze == "Woordsoort":
                soorten = sorted(list(set(i['woordsoort'] for i in st.session_state.data)))
                s = st.selectbox("Kies soort", soorten)
                doel = [i for i in st.session_state.data if i['woordsoort'] == s]
            elif keuze == "Mastery (<5 streak)":
                doel = [i for i in st.session_state.data if i['streak'] < 5]

            if st.button("Start Sessie"):
                doel.sort(key=bereken_gewicht, reverse=True)
                # Dynamische Chunks
                gem_streak = sum(i['streak'] for i in doel) / len(doel) if doel else 0
                chunk_size = max(5, min(20, 7 + int(gem_streak * 2.5)))
                st.session_state.sessie_lijst = random.sample(doel[:chunk_size*2], min(len(doel), chunk_size))
                st.session_state.huidig_item = st.session_state.sessie_lijst.pop(0)
                st.session_state.feedback = None
                st.session_state.modus_actief = modus[0]
                st.rerun()

        with col2:
            if st.session_state.huidig_item:
                item = st.session_state.huidig_item
                st.markdown(f"<div class='grieks-woord'>{item['grieks']}</div>", unsafe_allow_html=True)
                
                if st.session_state.modus_actief == '1':
                    st.warning(f"💡 {item['fonetisch']} | {item['anker']} {item['beeld']}")

                # MEERKEUZE (Modus 1 & 2)
                if st.session_state.modus_actief in ['1', '2']:
                    correct = maak_schoon(item['nederlands'])
                    afleiders = list(set([maak_schoon(i['nederlands']) for i in st.session_state.data if i['woordsoort'] == item['woordsoort'] and maak_schoon(i['nederlands']) != correct]))
                    if len(afleiders) < 3: afleiders += [maak_schoon(i['nederlands']) for i in st.session_state.data if i['grieks'] != item['grieks']]
                    opties = random.sample(afleiders, 3) + [correct]
                    random.shuffle(opties)
                    
                    cols = st.columns(2)
                    for idx, optie in enumerate(opties):
                        if cols[idx % 2].button(optie, key=f"btn_{optie}"):
                            if optie == correct:
                                item['score_goed'] += 1
                                item['streak'] += 1
                                st.success("✓ Goed!")
                                st.session_state.huidig_item = st.session_state.sessie_lijst.pop(0) if st.session_state.sessie_lijst else None
                                st.rerun()
                            else:
                                item['score_fout'] += 1
                                item['streak'] = 0
                                st.error(f"✗ Fout. Het was: {item['nederlands']}")
                                st.session_state.sessie_lijst.append(item)

                # OVERHOOR (Modus 3)
                else:
                    p = st.text_input("Betekenis:", key="overhoor_input").lower()
                    if st.button("Check"):
                        correct_schoon = maak_schoon(item['nederlands'])
                        if p == correct_schoon or p in item['nederlands'].lower():
                            item['score_goed'] += 1
                            item['streak'] += 1
                            st.success("✓ Correct!")
                            st.session_state.huidig_item = st.session_state.sessie_lijst.pop(0) if st.session_state.sessie_lijst else None
                            st.rerun()
                        else:
                            item['score_fout'] += 1
                            item['streak'] = 0
                            st.error(f"✗ Het was: {item['nederlands']}")
                            st.session_state.sessie_lijst.append(item)

                st.write(f"---")
                st.caption(f"Stats: NT-freq: {item['frequentie_nt']} | Streak: {item['streak']} | G/F: {item['score_goed']}/{item['score_fout']}")

    with menu[1]: # WOORDENLIJST
        les_filter = st.selectbox("Filter op les", sorted(list(set(i['les'] for i in st.session_state.data))))
        df = pd.DataFrame([i for i in st.session_state.data if i['les'] == les_filter])
        st.dataframe(df[['grieks', 'nederlands', 'frequentie_nt', 'streak', 'woordsoort']], use_container_width=True)

    with menu[2]: # VOORTGANG
        lessen = sorted(list(set(i['les'] for i in st.session_state.data)))
        stats = []
        for l in lessen:
            it = [i for i in st.session_state.data if i['les'] == l]
            stats.append((len([i for i in it if i['streak'] >= 5]) / len(it)) * 100)
        
        fig, ax = plt.subplots()
        ax.bar(lessen, stats, color='#33ccff')
        ax.set_title("Beheersing per Les (%)")
        ax.set_ylim(0, 100)
        st.pyplot(fig)
