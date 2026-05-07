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
    
    # Gebruik het gemiddelde van de drie modi voor de weging
    gem_streak = (int(item.get('streak_m1', 0)) + int(item.get('streak_m2', 0)) + int(item.get('streak_m3', 0))) / 3
    if gem_streak >= 20 or int(item.get('streak_m3', 0)) >= 20:
        gewicht *= 0.1
    return max(0.1, gewicht)

def geldig(val):
    return pd.notna(val) and str(val).strip() not in ['', 'nan', 'None']

# --- DATABASE FUNCTIES MET JSON TRANSLATIE ---
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
                    b['streak_m1'] = 0
                    b['streak_m2'] = 0
                    b['streak_m3'] = 0
                    if 'vormen_data' in b and isinstance(b['vormen_data'], list):
                        b['vormen_data'] = json.dumps(b['vormen_data'], ensure_ascii=False)
                    new_data.append(b)
                
                updated_df = pd.concat([df, pd.DataFrame(new_data)], ignore_index=True)
                conn.update(data=updated_df)
                
                for b in new_data:
                    if 'vormen_data' in b and isinstance(b['vormen_data'], str):
                        try:
                            b['vormen_data'] = json.loads(b['vormen_data'])
                        except:
                            b['vormen_data'] = []
                return new_data
        else:
            st.error("basis_woorden.json ontbreekt. Kan geen profiel aanmaken.")
            return None
            
    user_records = user_df.to_dict('records')
    for r in user_records:
        r['streak_m1'] = int(r.get('streak_m1', 0))
        r['streak_m2'] = int(r.get('streak_m2', 0))
        r['streak_m3'] = int(r.get('streak_m3', 0))
        
        if 'vormen_data' in r and geldig(r['vormen_data']):
            try:
                r['vormen_data'] = json.loads(str(r['vormen_data']))
            except:
                try:
                    r['vormen_data'] = ast.literal_eval(str(r['vormen_data']))
                except:
                    r['vormen_data'] = []
        else:
            r['vormen_data'] = []
    return user_records

def opslaan_naar_cloud(toon_melding=False):
    if not st.session_state.get('last_user') or not st.session_state.get('data'):
        return
    try:
        df = conn.read(ttl=0)
        if 'gebruikersnaam' not in df.columns:
            df['gebruikersnaam'] = ""
            
        df_andere_gebruikers = df[df['gebruikersnaam'] != st.session_state.last_user]
        
        huidige_data_kopie = []
        for item in st.session_state.data:
            k = item.copy()
            if 'vormen_data' in k and isinstance(k['vormen_data'], list):
                k['vormen_data'] = json.dumps(k['vormen_data'], ensure_ascii=False)
            huidige_data_kopie.append(k)
            
        df_jouw_data = pd.DataFrame(huidige_data_kopie)
        nieuwe_df = pd.concat([df_andere_gebruikers, df_jouw_data], ignore_index=True)
        
        conn.update(data=nieuwe_df)
        if toon_melding:
            st.toast("☁️ Voortgang veilig opgeslagen in de cloud!", icon="✅")
    except Exception as e:
        st.toast("Verbinding haperde: resultaat zit in werkgeheugen en wordt straks opgeslagen.", icon="⚠️")

# --- SESSION STATE ---
if 'data' not in st.session_state: st.session_state.data = None
if 'sessie_lijst' not in st.session_state: st.session_state.sessie_lijst = []
if 'huidig_item' not in st.session_state: st.session_state.huidig_item = None
if 'huidige_vorm_data' not in st.session_state: st.session_state.huidige_vorm_data = None
if 'feedback' not in st.session_state: st.session_state.feedback = None
if 'fouten_huidig_woord' not in st.session_state: st.session_state.fouten_huidig_woord = 0
if 'huidige_opties' not in st.session_state: st.session_state.huidige_opties = []
if 'last_user' not in st.session_state: st.session_state.last_user = None
if 'actieve_keuze' not in st.session_state: st.session_state.actieve_keuze = None

def laad_volgend_woord():
    st.session_state.huidig_item = st.session_state.sessie_lijst.pop(0) if st.session_state.sessie_lijst else None
    st.session_state.fouten_huidig_woord = 0
    st.session_state.huidige_opties = [] 
    st.session_state.huidige_vorm_data = None

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
            st.session_state.actieve_keuze = None
            st.rerun()

# --- HOOFDMENU ---
if st.session_state.data is None:
    st.title("Adaptief Grieks Leren")
    st.info("**Welkom!** Bedenk een vaste gebruikersnaam en vul deze linksboven in.")
else:
    menu = st.tabs(["🚀 Oefenen", "📖 Woordenlijst", "📊 Voortgang"])

    with menu[0]: # OEFENEN
        st.caption(f"Actief profiel: **{st.session_state.last_user}**")
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("Instellingen")
            modus = st.radio("Kies Modus:", ["1. Leer (Hulp + MC)", "2. Leer (MC)", "3. Overhoor (Typen)"])
            keuze = st.selectbox("Wat wil je oefenen?", ["Alles", "Lessen", "Woordsoort", "Declinatie", "Les + Woordsoort", "Nog niet beheerst (Gemiddelde < 20)"])
            
            doel = st.session_state.data
            alle_lessen = sorted(list(set(i.get('les', 1) for i in st.session_state.data)))
            
            if keuze == "Lessen":
                gekozen_lessen = st.multiselect("Kies les(sen)", alle_lessen, default=[alle_lessen[0]] if alle_lessen else [])
                doel = [i for i in st.session_state.data if i.get('les', 1) in gekozen_lessen]
                
            elif keuze == "Woordsoort":
                soorten = sorted(list(set(i.get('woordsoort', 'onbekend') for i in st.session_state.data)))
                s = st.selectbox("Kies soort", soorten)
                doel = [i for i in st.session_state.data if i.get('woordsoort') == s]
                
            elif keuze == "Declinatie":
                beschikbare_declinaties = sorted(list(set(str(i.get('declinatie', '')) for i in st.session_state.data if geldig(i.get('declinatie')))))
                if beschikbare_declinaties:
                    d = st.selectbox("Kies declinatie (bijv. 1, 2 of 3)", beschikbare_declinaties)
                    doel = [i for i in st.session_state.data if str(i.get('declinatie', '')) == d]
                else:
                    st.warning("Geen declinatie-data gevonden.")
                    doel = []
                    
            elif keuze == "Les + Woordsoort":
                gekozen_lessen = st.multiselect("Kies les(sen)", alle_lessen, default=[alle_lessen[0]] if alle_lessen else [])
                beschikbare_soorten = sorted(list(set(i.get('woordsoort', 'onbekend') for i in st.session_state.data if i.get('les', 1) in gekozen_lessen)))
                if beschikbare_soorten:
                    s = st.selectbox("Kies woordsoort", beschikbare_soorten)
                    doel = [i for i in st.session_state.data if i.get('les', 1) in gekozen_lessen and i.get('woordsoort') == s]
                else:
                    st.warning("Geen woorden gevonden voor deze combinatie.")
                    doel = []
                    
            elif keuze == "Nog niet beheerst (Gemiddelde < 20)":
                doel = [i for i in st.session_state.data if ((int(i.get('streak_m1', 0)) + int(i.get('streak_m2', 0)) + int(i.get('streak_m3', 0))) / 3) < 20]

            if st.button("Start Sessie"):
                if doel:
                    doel.sort(key=bereken_gewicht, reverse=True)
                    gem_streak = sum(((int(i.get('streak_m1', 0)) + int(i.get('streak_m2', 0)) + int(i.get('streak_m3', 0))) / 3) for i in doel) / len(doel)
                    chunk_size = max(5, min(20, 7 + int(gem_streak * 2.5)))
                    st.session_state.sessie_lijst = random.sample(doel[:chunk_size*2], min(len(doel), chunk_size))
                    
                    st.session_state.actieve_keuze = keuze
                    laad_volgend_woord() 
                    st.session_state.feedback = None
                    st.session_state.modus_actief = str(modus[0])
                    st.rerun()
                else:
                    st.error("De geselecteerde combinatie bevat geen woorden.")

        with col2:
            if st.session_state.huidig_item:
                item = st.session_state.huidig_item
                info_weergave = item.get('grieks_info', item['grieks'])
                actieve_streak_sleutel = f"streak_m{st.session_state.modus_actief}"
                
                # Bepaal mastery: Gemiddelde >= 20 OF Specifieke Typen streak >= 20
                gemiddelde_streak = (int(item.get('streak_m1', 0)) + int(item.get('streak_m2', 0)) + int(item.get('streak_m3', 0))) / 3
                is_mastery = (gemiddelde_streak >= 20) or (int(item.get('streak_m3', 0)) >= 20) or st.session_state.get('actieve_keuze') == "Declinatie"
                heeft_vormen = 'vormen_data' in item and isinstance(item['vormen_data'], list) and len(item['vormen_data']) > 0
                
                if st.session_state.huidige_vorm_data is None:
                    if is_mastery and heeft_vormen:
                        st.session_state.huidige_vorm_data = random.choice(item['vormen_data'])
                    else:
                        st.session_state.huidige_vorm_data = {"vorm": item['grieks'], "parsing": "basis"}

                huidige_vorm = str(st.session_state.huidige_vorm_data.get('vorm', item['grieks']))
                huidige_parsing = str(st.session_state.huidige_vorm_data.get('parsing', 'basis'))
                
                if st.session_state.feedback:
                    if st.session_state.feedback["type"] == "success":
                        st.success(st.session_state.feedback["msg"])
                    elif st.session_state.feedback["type"] == "warning":
                        st.warning(st.session_state.feedback["msg"])
                    else:
                        st.error(st.session_state.feedback["msg"])
                    st.session_state.feedback = None 

                st.markdown(f"<div class='grieks-woord'>{huidige_vorm}</div>", unsafe_allow_html=True)
                
                if is_mastery and heeft_vormen and huidige_vorm != item['grieks']:
                    st.caption(f"🏆 Vormleer Modus. (Basiswoord: **{item['grieks']}**)")

                # Basis hulpweergave voor Modus 1 of indien we in foutstap 1 zitten
                toon_hulp = (st.session_state.modus_actief == '1' or st.session_state.fouten_huidig_woord == 1)
                if toon_hulp:
                    st.info(f"💡 Hint: {item.get('fonetisch', '')} | {item.get('anker', '')} {item.get('beeld', '')}")

                # --- MEERKEUZE MODUS ---
                if st.session_state.modus_actief in ['1', '2']:
                    correct_betekenis = str(maak_schoon(item['nederlands']))
                    correct_optie = f"{correct_betekenis} ({huidige_parsing})" if (is_mastery and heeft_vormen) else correct_betekenis
                    
                    if not st.session_state.huidige_opties:
                        afleiders = []
                        if is_mastery and heeft_vormen:
                            andere_parsings = [str(v.get('parsing', '')) for v in item['vormen_data'] if str(v.get('parsing', '')) != str(huidige_parsing)]
                            if andere_parsings:
                                gekozen_foute_parsings = random.sample(andere_parsings, min(3, len(andere_parsings)))
                                for foute_parsing in gekozen_foute_parsings:
                                    afleiders.append(f"{correct_betekenis} ({foute_parsing})")
                        else:
                            alle_andere_betekenissen = [str(maak_schoon(i.get('nederlands', ''))) for i in st.session_state.data if i.get('grieks') != item.get('grieks')]
                            afleiders = alle_andere_betekenissen
                        
                        veilige_afleiders = [str(a) for a in afleiders if a]
                        unieke_afleiders = list(set(veilige_afleiders))
                        random.shuffle(unieke_afleiders)
                        opties = unieke_afleiders[:3] + [correct_optie]
                        
                        st.session_state.huidige_opties = list(dict.fromkeys(opties))
                        random.shuffle(st.session_state.huidige_opties)
                    
                    cols = st.columns(2)
                    for idx, optie in enumerate(st.session_state.huidige_opties):
                        if cols[idx % 2].button(optie, key=f"btn_{idx}_{item['grieks']}"):
                            if optie == correct_optie:
                                if st.session_state.fouten_huidig_woord == 0:
                                    item['score_goed'] = int(item.get('score_goed', 0)) + 1
                                    item[actieve_streak_sleutel] = int(item.get(actieve_streak_sleutel, 0)) + 1
                                opslaan_naar_cloud() 
                                st.session_state.feedback = {"type": "success", "msg": f"✓ Juist!"}
                                laad_volgend_woord()
                                st.rerun()
                            else:
                                st.session_state.fouten_huidig_woord += 1
                                
                                if st.session_state.fouten_huidig_woord == 1:
                                    st.session_state.feedback = {"type": "warning", "msg": "Niet helemaal juist. Bekijk de hint en probeer het nog een keer!"}
                                elif st.session_state.fouten_huidig_woord == 2:
                                    item['score_fout'] = int(item.get('score_fout', 0)) + 1
                                    if not (is_mastery and heeft_vormen):
                                        item[actieve_streak_sleutel] = max(0, int(item.get(actieve_streak_sleutel, 0)) - 2)
                                    opslaan_naar_cloud() 
                                    st.session_state.sessie_lijst.append(item)
                                    st.session_state.feedback = {"type": "error", "msg": f"✗ Helaas. Het juiste antwoord is: '{correct_optie}'. Klik hierop om door te gaan."}
                                else:
                                    st.session_state.feedback = {"type": "error", "msg": f"Kies het juiste antwoord: '{correct_optie}'."}
                                st.rerun() 

                # --- TYPEN MODUS ---
                else:
                    p_betekenis = st.text_input("1. Betekenis:", key=f"inp_b_{item['grieks']}").lower().strip()
                    
                    if is_mastery and heeft_vormen:
                        p_vorm = st.text_input("2. Vorm (bijv. nom ev m):", key=f"inp_v_{item['grieks']}").lower().strip()
                    else:
                        p_vorm = huidige_parsing.lower().strip()
                        
                    if st.button("Controleer", key=f"check_{item['grieks']}"):
                        correct_volledig = str(item['nederlands']).strip().lower()
                        correct_schoon = maak_schoon(item['nederlands'])
                        correcte_delen = [d.strip() for d in correct_volledig.split(',')]
                        
                        betekenis_goed = (p_betekenis == correct_volledig or p_betekenis == correct_schoon or p_betekenis in correcte_delen)
                        vorm_goed = (p_vorm == huidige_parsing.lower().strip())
                        
                        if betekenis_goed and vorm_goed:
                            if st.session_state.fouten_huidig_woord == 0:
                                item['score_goed'] = int(item.get('score_goed', 0)) + 1
                                item[actieve_streak_sleutel] = int(item.get(actieve_streak_sleutel, 0)) + 1
                            opslaan_naar_cloud()
                            
                            feedback_msg = f"✓ Correct. '{huidige_vorm}' = '{correct_volledig}'"
                            if is_mastery and heeft_vormen:
                                feedback_msg += f" ({huidige_parsing})."
                            st.session_state.feedback = {"type": "success", "msg": feedback_msg}
                            laad_volgend_woord()
                            st.rerun()
                        else:
                            st.session_state.fouten_huidig_woord += 1
                            
                            if st.session_state.fouten_huidig_woord == 1:
                                st.session_state.feedback = {"type": "warning", "msg": "Onjuist. Bekijk de hint en probeer het nog een keer!"}
                            elif st.session_state.fouten_huidig_woord == 2:
                                item['score_fout'] = int(item.get('score_fout', 0)) + 1
                                if not (is_mastery and heeft_vormen):
                                    item[actieve_streak_sleutel] = max(0, int(item.get(actieve_streak_sleutel, 0)) - 2)
                                opslaan_naar_cloud()
                                st.session_state.sessie_lijst.append(item)
                                
                                fout_bericht = f"✗ Helaas. Betekenis: '{correct_volledig}'"
                                if is_mastery and heeft_vormen:
                                    fout_bericht += f" | Vorm: '{huidige_parsing}'"
                                fout_bericht += ". Typ dit exact over om door te gaan."
                                st.session_state.feedback = {"type": "error", "msg": fout_bericht}
                            else:
                                herinnering = f"Typ over: '{correct_volledig}'"
                                if is_mastery and heeft_vormen:
                                    herinnering += f" | '{huidige_parsing}'"
                                st.session_state.feedback = {"type": "error", "msg": herinnering}
                            st.rerun()

                st.write(f"---")
                st.caption(f"Statistieken: NT-freq: {item.get('frequentie_nt', 0)} | Reeksen (M1/M2/M3): {item.get('streak_m1', 0)} / {item.get('streak_m2', 0)} / {item.get('streak_m3', 0)} | G/F: {item.get('score_goed', 0)}/{item.get('score_fout', 0)}")

    with menu[1]: # WOORDENLIJST
        les_filter = st.selectbox("Filter op les", sorted(list(set(i.get('les', 1) for i in st.session_state.data))))
        df = pd.DataFrame([i for i in st.session_state.data if i.get('les', 1) == les_filter])
        
        weergave_kolommen = ['grieks', 'nederlands', 'frequentie_nt', 'streak_m1', 'streak_m2', 'streak_m3', 'woordsoort']
        if 'grieks_info' in df.columns:
            weergave_kolommen.insert(1, 'grieks_info')
            
        st.dataframe(df[weergave_kolommen], use_container_width=True)

    with menu[2]: # VOORTGANG
        lessen = sorted(list(set(i.get('les', 1) for i in st.session_state.data)))
        stats = []
        for l in lessen:
            it = [i for i in st.session_state.data if i.get('les', 1) == l]
            if len(it) > 0:
                # Beheersingspercentage op basis van de nieuwe mastery regels
                beheerst = len([i for i in it if ((int(i.get('streak_m1',0)) + int(i.get('streak_m2',0)) + int(i.get('streak_m3',0))) / 3) >= 20 or int(i.get('streak_m3', 0)) >= 20])
                stats.append((beheerst / len(it)) * 100)
            else:
                stats.append(0)
        
        fig, ax = plt.subplots()
        ax.bar(lessen, stats, color='#33ccff')
        ax.set_title("Volledige beheersing per les (Vormleer geactiveerd)")
        ax.set_ylim(0, 100)
        st.pyplot(fig)
