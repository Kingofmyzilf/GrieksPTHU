import streamlit as st
from streamlit_gsheets import GSheetsConnection
import json
import random
import re
import math
import pandas as pd
import matplotlib.pyplot as plt
import os

# --- CONFIGURATIE ---
st.set_page_config(page_title="Grieks Cloud Tutor", layout="wide")

# Verbinding maken met Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# Custom CSS voor mobiele weergave
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 10px; height: 3em; font-weight: bold; }
    .stTextInput>div>div>input { font-size: 20px; text-align: center; }
    .grieks-woord { font-size: 50px; font-weight: bold; color: #33ccff; text-align: center; padding: 20px; }
    </style>
    """, unsafe_allow_html=True)

# --- LOGICA ---

def maak_schoon(tekst):
    schoon = re.sub(r'\(.*?\)', '', str(tekst))
    schoon = re.sub(r'\[.*?\]', '', schoon)
    return schoon.replace(';', ',').split(',')[0].strip().lower()

def bereken_gewicht(item):
    gewicht = 1.0
    freq = int(item.get('frequentie_nt', 0))
    if freq > 0:
        gewicht += math.log10(freq + 1)
    gewicht += (int(item.get('score_fout', 0)) * 1.5)
    if int(item.get('streak', 0)) >= 5:
        gewicht *= 0.1
    return max(0.1, gewicht)

# --- ROBUUSTE DATABASE FUNCTIES ---

def laad_gebruiker_data(naam):
    """Haalt verse data op uit de sheet (geen cache) of maakt een nieuw profiel aan."""
    df = conn.read(ttl=0) # ttl=0 dwingt de app om live in Google Sheets te kijken
    
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
                    new_data.append(b)
                
                updated_df = pd.concat([df, pd.DataFrame(new_data)], ignore_index=True)
                conn.update(data=updated_df)
                return new_data
        else:
            st.error("basis_woorden.json ontbreekt. Kan geen nieuw profiel aanmaken.")
            return None
    return user_df.to_dict('records')

def opslaan_naar_cloud(toon_melding=False):
    """Slaat ALLES van de actieve gebruiker in één keer veilig op."""
    if not st.session_state.get('last_user') or not st.session_state.get('data'):
        return
    
    try:
        # Haal actuele sheet op
        df = conn.read(ttl=0)
        if 'gebruikersnaam' not in df.columns:
            df['gebruikersnaam'] = ""
            
        # Filter iedereen BEHALVE de huidige gebruiker eruit
        df_andere_gebruikers = df[df['gebruikersnaam'] != st.session_state.last_user]
        
        # Maak een verse tabel van JOUW huidige sessie in het geheugen
        df_jouw_data = pd.DataFrame(st.session_state.data)
        
        # Plak ze aan elkaar en update
        nieuwe_df = pd.concat([df_andere_gebruikers, df_jouw_data], ignore_index=True)
        conn.update(data=nieuwe_df)
        
        if toon_melding:
            st.toast("☁️ Voortgang veilig opgeslagen in de cloud!", icon="✅")
            
    except Exception as e:
        # Als de verbinding hapert, crasht de app niet, maar blijft data in RAM bewaard!
        st.toast("Verbinding haperde: resultaat zit in werkgeheugen en wordt straks opgeslagen.", icon="⚠️")

# --- SESSION STATE (GEHEUGEN VAN DE WEBSITE) ---
if 'data' not in st.session_state: st.session_state.data = None
if 'sessie_lijst' not in st.session_state: st.session_state.sessie_lijst = []
if 'huidig_item' not in st.session_state: st.session_state.huidig_item = None
if 'feedback' not in st.session_state: st.session_state.feedback = None
if 'fout_gemaakt' not in st.session_state: st.session_state.fout_gemaakt = False
if 'huidige_opties' not in st.session_state: st.session_state.huidige_opties = []
if 'last_user' not in st.session_state: st.session_state.last_user = None

def laad_volgend_woord():
    st.session_state.huidig_item = st.session_state.sessie_lijst.pop(0) if st.session_state.sessie_lijst else None
    st.session_state.fout_gemaakt = False
    st.session_state.huidige_opties = [] 

# --- SIDEBAR: LOGIN & OPSLAAN ---
with st.sidebar:
    st.header("👤 Inloggen")
    user_input = st.text_input("Voer je voornaam in", key="user_login").strip()
    
    if user_input:
        if st.session_state.data is None or st.session_state.last_user != user_input:
            with st.spinner("Gegevens ophalen uit Google Sheets..."):
                st.session_state.data = laad_gebruiker_data(user_input)
                st.session_state.last_user = user_input
            st.success(f"Ingelogd als {user_input}.")
    
    if st.session_state.data:
        st.write("---")
        if st.button("💾 Forceer Cloud Opslag"):
            with st.spinner("Gegevens naar Google pushen..."):
                opslaan_naar_cloud(toon_melding=True)
                
        if st.button("🚪 Uitloggen"):
            with st.spinner("Laatste antwoorden veiligstellen..."):
                opslaan_naar_cloud()
            st.session_state.data = None
            st.session_state.last_user = None
            st.session_state.sessie_lijst = []
            st.session_state.huidig_item = None
            st.rerun()

# --- HOOFDMENU ---
if st.session_state.data is None:
    st.title("Adaptief Grieks Leren")
    st.info("""
    **Welkom!** Bedenk een vaste gebruikersnaam en vul deze linksboven in. 
    
    Elke keer dat je met deze specifieke naam inlogt, haalt het systeem je persoonlijke resultaten op. Je voortgang wordt na elke gemaakte vraag automatisch naar de cloud gestuurd. 
    
    Klaar met leren? Klik altijd nog even op **Uitloggen** (of Forceer Opslag) in het linkermenu, zodat je zeker weet dat de laatste seconden ook in de database staan!
    """)
else:
    menu = st.tabs(["🚀 Oefenen", "📖 Woordenlijst", "📊 Voortgang"])

    with menu[0]: # OEFENEN
        st.caption(f"Actief profiel: **{st.session_state.last_user}**")
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("Instellingen")
            modus = st.radio("Kies Modus:", ["1. Leer (Hulp + MC)", "2. Leer (MC)", "3. Overhoor (Typen)"])
            keuze = st.selectbox("Wat wil je oefenen?", ["Alles", "Lessen", "Woordsoort", "Les + Woordsoort", "Mastery (<5 streak)"])
            
            doel = st.session_state.data
            if keuze == "Lessen":
                les_nr = st.number_input("Les nummer", min_value=1, value=1)
                doel = [i for i in st.session_state.data if i.get('les', 1) == les_nr]
                
            elif keuze == "Woordsoort":
                soorten = sorted(list(set(i.get('woordsoort', 'onbekend') for i in st.session_state.data)))
                s = st.selectbox("Kies soort", soorten)
                doel = [i for i in st.session_state.data if i.get('woordsoort') == s]
                
            elif keuze == "Les + Woordsoort":
                les_nr = st.number_input("Les nummer", min_value=1, value=1)
                beschikbare_soorten = sorted(list(set(i.get('woordsoort', 'onbekend') for i in st.session_state.data if i.get('les', 1) == les_nr)))
                
                if beschikbare_soorten:
                    s = st.selectbox("Kies woordsoort", beschikbare_soorten)
                    doel = [i for i in st.session_state.data if i.get('les', 1) == les_nr and i.get('woordsoort') == s]
                else:
                    st.warning("Geen woorden gevonden in deze les.")
                    doel = []
                    
            elif keuze == "Mastery (<5 streak)":
                doel = [i for i in st.session_state.data if int(i.get('streak', 0)) < 5]

            if st.button("Start Sessie"):
                if doel:
                    doel.sort(key=bereken_gewicht, reverse=True)
                    gem_streak = sum(int(i.get('streak', 0)) for i in doel) / len(doel)
                    chunk_size = max(5, min(20, 7 + int(gem_streak * 2.5)))
                    st.session_state.sessie_lijst = random.sample(doel[:chunk_size*2], min(len(doel), chunk_size))
                    
                    laad_volgend_woord() 
                    st.session_state.feedback = None
                    st.session_state.modus_actief = modus[0]
                    st.rerun()
                else:
                    st.error("De geselecteerde combinatie bevat geen woorden.")

        with col2:
            if st.session_state.huidig_item:
                item = st.session_state.huidig_item
                info_weergave = item.get('grieks_info', item['grieks'])
                
                if st.session_state.feedback:
                    if st.session_state.feedback["type"] == "success":
                        st.success(st.session_state.feedback["msg"])
                    else:
                        st.error(st.session_state.feedback["msg"])
                    st.session_state.feedback = None 

                st.markdown(f"<div class='grieks-woord'>{item['grieks']}</div>", unsafe_allow_html=True)
                
                if st.session_state.modus_actief == '1':
                    st.warning(f"💡 {item.get('fonetisch', '')} | {item.get('anker', '')} {item.get('beeld', '')}")

                if st.session_state.modus_actief in ['1', '2']:
                    correct = maak_schoon(item['nederlands'])
                    
                    if not st.session_state.huidige_opties:
                        afleiders = list(set([maak_schoon(i['nederlands']) for i in st.session_state.data if i.get('woordsoort') == item.get('woordsoort') and maak_schoon(i['nederlands']) != correct]))
                        if len(afleiders) < 3: 
                            afleiders += [maak_schoon(i['nederlands']) for i in st.session_state.data if i['grieks'] != item['grieks']]
                        opties = random.sample(afleiders, 3) + [correct]
                        random.shuffle(opties)
                        st.session_state.huidige_opties = opties
                    
                    cols = st.columns(2)
                    for idx, optie in enumerate(st.session_state.huidige_opties):
                        if cols[idx % 2].button(optie, key=f"btn_{idx}_{item['grieks']}"):
                            if optie == correct:
                                if not st.session_state.fout_gemaakt:
                                    item['score_goed'] = int(item.get('score_goed', 0)) + 1
                                    item['streak'] = int(item.get('streak', 0)) + 1
                                    opslaan_naar_cloud() # Sla live op
                                
                                st.session_state.feedback = {"type": "success", "msg": f"✓ Juist. '{info_weergave}' betekent inderdaad '{correct}'."}
                                laad_volgend_woord()
                                st.rerun()
                            else:
                                if not st.session_state.fout_gemaakt:
                                    item['score_fout'] = int(item.get('score_fout', 0)) + 1
                                    item['streak'] = 0
                                    opslaan_naar_cloud() # Sla live op
                                    st.session_state.sessie_lijst.append(item)
                                    st.session_state.fout_gemaakt = True
                                
                                st.session_state.feedback = {"type": "error", "msg": f"✗ Niet correct. Het is '{info_weergave}' = '{item['nederlands']}'. Selecteer het juiste antwoord om door te gaan."}
                                st.rerun() 

                else:
                    p = st.text_input("Betekenis:", key=f"input_{item['grieks']}").lower()
                    if st.button("Controleer", key=f"check_{item['grieks']}"):
                        correct_schoon = maak_schoon(item['nederlands'])
                        if p == correct_schoon or p in item['nederlands'].lower():
                            if not st.session_state.fout_gemaakt:
                                item['score_goed'] = int(item.get('score_goed', 0)) + 1
                                item['streak'] = int(item.get('streak', 0)) + 1
                                opslaan_naar_cloud() # Sla live op
                                
                            st.session_state.feedback = {"type": "success", "msg": f"✓ Correct. '{info_weergave}' = '{correct_schoon}'."}
                            laad_volgend_woord()
                            st.rerun()
                        else:
                            if not st.session_state.fout_gemaakt:
                                item['score_fout'] = int(item.get('score_fout', 0)) + 1
                                item['streak'] = 0
                                opslaan_naar_cloud() # Sla live op
                                st.session_state.sessie_lijst.append(item)
                                st.session_state.fout_gemaakt = True
                                
                            st.session_state.feedback = {"type": "error", "msg": f"✗ Onjuist. Typ het volgende over: {correct_schoon} (Informatie: {info_weergave})"}
                            st.rerun()

                st.write(f"---")
                st.caption(f"Statistieken: NT-freq: {item.get('frequentie_nt', 0)} | Reeks: {item.get('streak', 0)} | G/F: {item.get('score_goed', 0)}/{item.get('score_fout', 0)}")

    with menu[1]: # WOORDENLIJST
        les_filter = st.selectbox("Filter op les", sorted(list(set(i.get('les', 1) for i in st.session_state.data))))
        df = pd.DataFrame([i for i in st.session_state.data if i.get('les', 1) == les_filter])
        
        weergave_kolommen = ['grieks', 'nederlands', 'frequentie_nt', 'streak', 'woordsoort']
        if 'grieks_info' in df.columns:
            weergave_kolommen.insert(1, 'grieks_info')
            
        st.dataframe(df[weergave_kolommen], use_container_width=True)

    with menu[2]: # VOORTGANG
        lessen = sorted(list(set(i.get('les', 1) for i in st.session_state.data)))
        stats = []
        for l in lessen:
            it = [i for i in st.session_state.data if i.get('les', 1) == l]
            if len(it) > 0:
                stats.append((len([i for i in it if int(i.get('streak', 0)) >= 5]) / len(it)) * 100)
            else:
                stats.append(0)
        
        fig, ax = plt.subplots()
        ax.bar(lessen, stats, color='#33ccff')
        ax.set_title("Beheersingspercentage per les")
        ax.set_ylim(0, 100)
        st.pyplot(fig)
