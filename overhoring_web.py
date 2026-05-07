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
    
    if res.endswith('σ'):
        res = res[:-1] + 'ς'
    return res

def normaliseer_accent(woord):
    """Verwijdert alle accenten en spiritus zodat typen zonder accenten altijd wordt goedgekeurd."""
    if pd.notna(woord) and str(woord).strip() != "":
        w = str(woord).strip().lower()
        w = ''.join(c for c in unicodedata.normalize('NFD', w) if unicodedata.category(c) != 'Mn')
        w = w.replace('a', 'α').replace('e', 'ε').replace('i', 'ι').replace('o', 'ο').replace('u', 'υ')
        return w
    return ""

def splits_sleutel(sleutel):
    """Een veel slimmere knipper die Participia en Declinaties begrijpt."""
    s = str(sleutel).strip()
    
    wijzen = ["Indicativus", "Conjunctivus", "Optativus", "Imperativus", "Infinitivus", "Participium", "Part"]
    for w in wijzen:
        if s.lower().startswith(w.lower()):
            rest = s[len(w):].strip(" _-.")
            return w.capitalize(), rest if rest else "Vorm"
            
    naamvallen = ["nom", "gen", "dat", "acc", "voc"]
    if any(s.lower().startswith(n) for n in naamvallen):
        return "Declinatie", s
        
    match = re.match(r"([A-Za-z]+)(.*)", s)
    if match:
        rest = match.group(2).strip()
        return match.group(1).capitalize(), rest if rest else "Vorm"
        
    return "Overig", s

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
                return laad_gebruiker_data(naam)
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
        conn.update(data=pd.concat([df_andere_gebruikers, df_jouw_data], ignore_index=True))
    except Exception: pass

# --- SESSION STATE ---
for key in ['data', 'sessie_lijst', 'huidig_item', 'huidige_vorm_data', 'feedback', 
            'fouten_huidig_woord', 'huidige_opties', 'last_user', 'actieve_keuze',
            'gram_oefening', 'gram_fouten', 'laatste_filter']:
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
                
                sm1 = int(item.get('streak_m1', 0))
                sm2 = int(item.get('streak_m2', 0))
                sm3 = int(item.get('streak_m3', 0))
                
                gem_streak = (sm1 + sm2 + sm3) / 3
                is_mastery = gem_streak >= 20 or sm3 >= 20
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

                if st.session_state.modus_actief == '1' or st.session_state.fouten_huidig_woord >= 1:
                    st.info(f"💡 {item.get('fonetisch', '')} | {item.get('anker', '')} {item.get('beeld', '')}")

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
                                    item[actieve_streak] = int(item.get(actieve_streak, 0)) + 1
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
                                        item[actieve_streak] = max(0, int(item.get(actieve_streak, 0)) - 2)
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
                                item[actieve_streak] = int(item.get(actieve_streak, 0)) + 1
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
                                    item[actieve_streak] = max(0, int(item.get(actieve_streak, 0)) - 2)
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
        st.write("Voortgang per les op basis van mastery (Gemiddelde streak 20)")
        lessen = sorted(list(set(i.get('les', 1) for i in st.session_state.data)))
        stats = []
        for l in lessen:
            it = [i for i in st.session_state.data if i.get('les', 1) == l]
            if len(it) > 0:
                beheerst = len([i for i in it if ((int(i.get('streak_m1',0)) + int(i.get('streak_m2',0)) + int(i.get('streak_m3',0))) / 3) >= 20 or int(i.get('streak_m3', 0)) >= 20])
                stats.append((beheerst / len(it)) * 100)
            else:
                stats.append(0)
        
        fig, ax = plt.subplots()
        ax.bar(lessen, stats, color='#33ccff')
        ax.set_ylim(0, 100)
        st.pyplot(fig)

    with menu[3]: # GRAMMATICA
        gram_db = laad_grammatica_db()
        if gram_db:
            luo = gram_db["werkwoorden"]["λύω"]
            st.subheader("🏛️ Grammatica Paradigma's (λύω)")
            
            c1, c2, c3 = st.columns(3)
            with c1:
                gram_keuze = st.radio("Oefenvorm:", ["Vormen Analyseren", "Rijtjes Produceren"])
            with c2:
                beschikbare_tijden = list(luo.keys())
                gekozen_tijd = st.selectbox("1. Selecteer Tijd/Diathese:", beschikbare_tijden)
            with c3:
                wijzen_set = set()
                for k in luo[gekozen_tijd].keys():
                    wijs, _ = splits_sleutel(k)
                    wijzen_set.add(wijs)
                
                opties_wijzen = ["Alles (Compleet blok)"] + sorted(list(wijzen_set))
                gekozen_wijs_input = st.selectbox("2. Selecteer Modus/Wijs:", opties_wijzen)
            
            gekozen_wijs = None if "Alles" in gekozen_wijs_input else gekozen_wijs_input
            
            gefilterd_rijtje = {}
            for k, v in luo[gekozen_tijd].items():
                wijs, rest = splits_sleutel(k)
                if gekozen_wijs is None:
                    gefilterd_rijtje[k] = v 
                elif wijs == gekozen_wijs:
                    weergave_naam = rest if rest != "" else wijs
                    gefilterd_rijtje[weergave_naam] = v

            st.write("---")

            if gram_keuze == "Vormen Analyseren":
                huidig_filter = f"{gekozen_tijd}_{gekozen_wijs_input}"
                if st.button("Nieuwe Vorm") or not st.session_state.gram_oefening or st.session_state.get('laatste_filter') != huidig_filter:
                    vlak = [{"naam": k, "vorm": v} for k, v in gefilterd_rijtje.items()]
                    st.session_state.gram_oefening = random.choice(vlak)
                    st.session_state.gram_fouten = 0
                    st.session_state.laatste_filter = huidig_filter
                
                oef = st.session_state.gram_oefening
                st.markdown(f"<div class='grieks-woord'>{oef['vorm']}</div>", unsafe_allow_html=True)
                
                if gekozen_wijs and ("part" in gekozen_wijs.lower() or "declinatie" in gekozen_wijs.lower()):
                    vraag_label = "Welke naamval, getal en geslacht is dit?"
                else:
                    vraag_label = "Welke persoon / vorm is dit?"
                
                ans = st.selectbox(vraag_label, [""] + list(gefilterd_rijtje.keys()))
                
                if st.button("Controleer Analyse"):
                    if ans == oef['naam']:
                        st.success("✓ Correct! Maak hierboven een nieuwe vorm aan.")
                        st.session_state.gram_oefening = None; st.rerun()
                    else:
                        st.error(f"✗ Nee, het was de {oef['naam']}")

            else: # Rijtjes Produceren
                st.info("ℹ️ Typ met normale letters. Voorbeeld: **luis** wordt **λύεις**, **luomen** wordt **λύομεν**.")
                fouten_teller = 0
                
                for weergave_naam, correcte_vorm in gefilterd_rijtje.items():
                    user_inp = st.text_input(f"{weergave_naam}:", key=f"grid_{gekozen_tijd}_{gekozen_wijs_input}_{weergave_naam}")
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
