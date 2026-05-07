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
    st.error("Kan niet verbinden met Google Sheets. Controleer je internetverbinding.")

st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 10px; height: 3em; font-weight: bold; }
    .stTextInput>div>div>input { font-size: 20px; text-align: center; }
    .grieks-woord { font-size: 50px; font-weight: bold; color: #33ccff; text-align: center; padding: 20px; }
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
    gem_streak = (int(item.get('streak_m1', 0)) + int(item.get('streak_m2', 0)) + int(item.get('streak_m3', 0))) / 3
    if gem_streak >= 20 or int(item.get('streak_m3', 0)) >= 20: gewicht *= 0.1
    return max(0.1, gewicht)

def geldig(val):
    return pd.notna(val) and str(val).strip() not in ['', 'nan', 'None']

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
    try:
        df = conn.read(ttl=0) 
        if 'gebruikersnaam' not in df.columns: df['gebruikersnaam'] = ""
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
                        b['gram_stats'] = "{}"
                        new_data.append(b)
                    conn.update(data=pd.concat([df, pd.DataFrame(new_data)], ignore_index=True))
                    return laad_gebruiker_data(naam)
            return None
                
        user_records = user_df.to_dict('records')
        
        if len(user_records) > 0 and 'gram_stats' in user_records[0] and pd.notna(user_records[0]['gram_stats']):
            try: st.session_state.gram_stats = json.loads(str(user_records[0]['gram_stats']))
            except: st.session_state.gram_stats = {}
            
        for r in user_records:
            r['streak_m1'] = int(r.get('streak_m1', 0))
            r['streak_m2'] = int(r.get('streak_m2', 0))
            r['streak_m3'] = int(r.get('streak_m3', 0))
            if 'vormen_data' in r and pd.notna(r['vormen_data']):
                try: r['vormen_data'] = json.loads(str(r['vormen_data']))
                except: r['vormen_data'] = []
            else: r['vormen_data'] = []
        return user_records
    except Exception as e:
        return None

def opslaan_naar_cloud():
    if not st.session_state.get('last_user') or not st.session_state.get('data'): return
    try:
        df = conn.read(ttl=0)
        if 'gebruikersnaam' not in df.columns: df['gebruikersnaam'] = ""
        df_andere_gebruikers = df[df['gebruikersnaam'] != st.session_state.last_user]
        huidige_data_kopie = []
        
        gram_stats_json = json.dumps(st.session_state.get('gram_stats', {}), ensure_ascii=False)
        
        for item in st.session_state.data:
            k = item.copy()
            if 'vormen_data' in k and isinstance(k['vormen_data'], list):
                k['vormen_data'] = json.dumps(k['vormen_data'], ensure_ascii=False)
            k['gram_stats'] = gram_stats_json
            huidige_data_kopie.append(k)
            
        conn.update(data=pd.concat([df_andere_gebruikers, pd.DataFrame(huidige_data_kopie)], ignore_index=True))
    except Exception: pass

# --- SESSION STATE ---
for key in ['data', 'sessie_lijst', 'huidig_item', 'huidige_vorm_data', 'feedback', 
            'fouten_huidig_woord', 'huidige_opties', 'last_user', 'actieve_keuze',
            'gram_oefening', 'gram_fouten', 'laatste_filter',
            'decl_oefening', 'laatste_filter_decl', 'gram_feedback', 'decl_feedback']:
    if key not in st.session_state: st.session_state[key] = None

if 'gram_stats' not in st.session_state: st.session_state.gram_stats = {}
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
            opslaan_naar_cloud()
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
                alle_lessen = sorted(list(set(veilig_les_nummer(i) for i in st.session_state.data)))
                gekozen = st.multiselect("Kies lessen", alle_lessen)
                doel = [i for i in st.session_state.data if veilig_les_nummer(i) in gekozen]
            elif keuze == "Mastery":
                doel = [i for i in st.session_state.data if ((int(i.get('streak_m1',0))+int(i.get('streak_m2',0))+int(i.get('streak_m3',0)))/3) >= 20]
            
            if st.button("Start Sessie"):
                if doel:
                    doel.sort(key=bereken_gewicht, reverse=True)
                    st.session_state.sessie_lijst = random.sample(doel, min(len(doel), 10))
                    st.session_state.modus_actief = str(modus[0])
                    laad_volgend_woord(); st.rerun()

        with col2:
            if st.session_state.huidig_item:
                item = st.session_state.huidig_item
                actieve_streak = f"streak_m{st.session_state.modus_actief}"
                
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
                        p_vorm = st.text_input("Vorm (bijv. nom ev m):", key=f"inp_v_{item.get('grieks')}").lower().strip()
                    else:
                        p_vorm = huidige_parsing.lower().strip()

                    if st.button("Check Antwoord"):
                        betekenis_goed = inp == maak_schoon(correct_antw) or inp in correct_antw.lower()
                        vorm_goed = p_vorm == huidige_parsing.lower().strip()

                        if betekenis_goed and vorm_goed:
                            item[actieve_streak] = int(item.get(actieve_streak, 0)) + 1
                            st.success("✓ Goed!"); opslaan_naar_cloud(); laad_volgend_woord(); st.rerun()
                        else:
                            st.session_state.fouten_huidig_woord = int(st.session_state.fouten_huidig_woord) + 1
                            if st.session_state.fouten_huidig_woord >= 2:
                                item[actieve_streak] = max(0, int(item.get(actieve_streak, 0)) - 2)
                                st.error(f"✗ Fout. Betekenis: {correct_antw}" + (f" | Vorm: {huidige_parsing}" if is_mastery and heeft_vormen else ""))
                                opslaan_naar_cloud()
                                st.session_state.sessie_lijst.append(item)
                            else:
                                st.warning("Bijna! Gebruik de hint en probeer nog eens.")
                else:
                    correct_optie = f"{correct_antw} ({huidige_parsing})" if (is_mastery and heeft_vormen) else correct_antw
                    if not st.session_state.huidige_opties:
                        afleiders = []
                        if is_mastery and heeft_vormen:
                            andere = [str(v.get('parsing', '')) for v in item.get('vormen_data', []) if str(v.get('parsing', '')) != str(huidige_parsing)]
                            if andere: afleiders = [f"{correct_antw} ({f})" for f in random.sample(andere, min(3, len(andere)))]
                        else:
                            afleiders = [str(i.get('nederlands', '')) for i in st.session_state.data if i.get('grieks') != item.get('grieks')]
                        
                        opties = list(set([str(a) for a in afleiders if a]))[:3] + [correct_optie]
                        st.session_state.huidige_opties = list(dict.fromkeys(opties))
                        random.shuffle(st.session_state.huidige_opties)
                    
                    cols = st.columns(2)
                    for idx, optie in enumerate(st.session_state.huidige_opties):
                        if cols[idx % 2].button(optie, key=f"btn_{idx}_{item.get('grieks')}"):
                            if optie == correct_optie:
                                item[actieve_streak] = int(item.get(actieve_streak, 0)) + 1
                                st.success("✓ Goed!"); opslaan_naar_cloud(); laad_volgend_woord(); st.rerun()
                            else:
                                st.session_state.fouten_huidig_woord = int(st.session_state.fouten_huidig_woord) + 1
                                if st.session_state.fouten_huidig_woord >= 2:
                                    item[actieve_streak] = max(0, int(item.get(actieve_streak, 0)) - 2)
                                    st.error(f"✗ Fout. Het was: {correct_optie}")
                                    opslaan_naar_cloud()
                                    st.session_state.sessie_lijst.append(item)
                                else:
                                    st.warning("Niet helemaal juist. Probeer nog eens!")

                st.write("---")
                st.caption(f"Reeksen (M1/M2/M3): {item.get('streak_m1', 0)} / {item.get('streak_m2', 0)} / {item.get('streak_m3', 0)}")

    with menu[1]: # LIJST
        if st.session_state.data:
            alle_lessen = sorted(list(set(veilig_les_nummer(i) for i in st.session_state.data)))
            les_filter = st.selectbox("Bekijk les:", alle_lessen)
            df = pd.DataFrame([i for i in st.session_state.data if veilig_les_nummer(i) == les_filter])
            if not df.empty:
                st.dataframe(df[[c for c in ['grieks', 'nederlands', 'streak_m1', 'streak_m2', 'streak_m3', 'woordsoort'] if c in df.columns]], use_container_width=True)

    with menu[2]: # VOORTGANG
        if st.session_state.data:
            st.write("Voortgang per les op basis van mastery (Gemiddelde streak >= 20)")
            lessen = sorted(list(set(veilig_les_nummer(i) for i in st.session_state.data)))
            stats = []
            for l in lessen:
                it = [i for i in st.session_state.data if veilig_les_nummer(i) == l]
                beheerst = len([i for i in it if (int(i.get('streak_m1',0))+int(i.get('streak_m2',0))+int(i.get('streak_m3',0)))/3 >= 20])
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
            with c1: gram_keuze = st.radio("Oefenvorm:", ["Visueel Leren (Tabel)", "Vormen Analyseren", "Rijtjes Produceren"])
            with c2: gekozen_tijd = st.selectbox("1. Tijd/Diathese:", list(luo.keys()))
            with c3:
                wijzen_set = set()
                for k in luo[gekozen_tijd].keys(): wijzen_set.add(splits_sleutel(k)[0])
                gekozen_wijs_input = st.selectbox("2. Modus/Wijs:", ["Alles"] + sorted(list(wijzen_set)))
            
            gekozen_wijs = None if gekozen_wijs_input == "Alles" else gekozen_wijs_input
            gefilterd_rijtje = { splits_sleutel(k)[1]: v for k, v in luo[gekozen_tijd].items() 
                                if gekozen_wijs is None or splits_sleutel(k)[0] == gekozen_wijs }

            st.write("---")

            if st.session_state.gram_feedback:
                if st.session_state.gram_feedback['type'] == 'success': st.success(st.session_state.gram_feedback['msg'])
                else: st.error(st.session_state.gram_feedback['msg'])
                st.session_state.gram_feedback = None

            if gram_keuze == "Visueel Leren (Tabel)":
                st.info(f"**Overzicht: {gekozen_tijd} | {gekozen_wijs_input}**")
                df_vis = pd.DataFrame(list(gefilterd_rijtje.items()), columns=["Vorm/Persoon", "Griekse Vorm"])
                st.dataframe(df_vis, use_container_width=True, hide_index=True)

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
                    if vorm_id not in st.session_state.gram_stats:
                        st.session_state.gram_stats[vorm_id] = {'goed': 0, 'fout': 0, 'streak': 0}

                    if gekozen_wijs == "Participium":
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
                            opslaan_naar_cloud()
                            st.session_state.gram_feedback = {'type': 'success', 'msg': f"✓ Correct! Dat was de {oef['naam']}. Hier is direct de volgende:"}
                            st.session_state.gram_oefening = kies_adaptieve_gram_vorm(vlak, prefix)
                            st.rerun()
                        else:
                            st.session_state.gram_stats[vorm_id]['fout'] += 1
                            st.session_state.gram_stats[vorm_id]['streak'] = max(0, st.session_state.gram_stats[vorm_id]['streak'] - 2)
                            opslaan_naar_cloud()
                            st.session_state.gram_feedback = {'type': 'error', 'msg': f"✗ Niet juist. Het is de: {oef['naam']}"}
                            st.rerun()

            else: # RIJTJES PRODUCEREN
                st.info("ℹ️ Gebruik Bèta-code. Accenten worden automatisch genegeerd.")
                fouten_teller = 0
                if gekozen_wijs == "Participium":
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
                                        if normaliseer_accent(naar_grieks_transliteratie(inp)) == normaliseer_accent(correct): cols[i].caption(f"✅ {correct}")
                                        else: cols[i].caption(f"❌ {correct}"); fouten_teller += 1
                else:
                    for label, correct in gefilterd_rijtje.items():
                        inp = st.text_input(label, key=f"std_{gekozen_tijd}_{label}")
                        if inp:
                            if normaliseer_accent(naar_grieks_transliteratie(inp)) == normaliseer_accent(correct): st.success(f"✓ {correct}")
                            else: st.error(f"✗ {correct}"); fouten_teller += 1
                
                if st.button("Check Rijtje") and fouten_teller == 0: st.balloons()
        else:
            st.warning("grammatica.json ontbreekt. Voer het luo-conversiescript in.")

    with menu[4]: # NAAMWOORDEN
        decl_db = laad_declinaties_db()
        if decl_db and "Declinaties" in decl_db:
            st.subheader("🏷️ Nominale Morfologie (Declinaties)")
            
            dc1, dc2, dc3 = st.columns(3)
            with dc1: decl_keuze = st.radio("Oefenvorm:", ["Visueel Leren (Tabel)", "Vormen Analyseren", "Rijtjes Produceren"], key="decl_radio")
            with dc2: gekozen_groep = st.selectbox("1. Declinatie Groep:", list(decl_db["Declinaties"].keys()))
            with dc3: gekozen_paradigma = st.selectbox("2. Paradigma:", list(decl_db["Declinaties"][gekozen_groep].keys()))
            
            gefilterd_rijtje = decl_db["Declinaties"][gekozen_groep][gekozen_paradigma]

            st.write("---")

            # Gereserveerde feedback variabele, specifiek voor naamwoorden
            if st.session_state.decl_feedback:
                if st.session_state.decl_feedback['type'] == 'success': st.success(st.session_state.decl_feedback['msg'])
                else: st.error(st.session_state.decl_feedback['msg'])
                st.session_state.decl_feedback = None

            if decl_keuze == "Visueel Leren (Tabel)":
                st.info(f"**Overzicht: {gekozen_groep} | {gekozen_paradigma}**")
                df_vis = pd.DataFrame(list(gefilterd_rijtje.items()), columns=["Naamval & Getal", "Griekse Vorm"])
                st.dataframe(df_vis, use_container_width=True, hide_index=True)

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
                    if vorm_id not in st.session_state.gram_stats:
                        st.session_state.gram_stats[vorm_id] = {'goed': 0, 'fout': 0, 'streak': 0}

                    poging = st.selectbox("Welke naamval/getal is dit?", [""] + list(gefilterd_rijtje.keys()), key="sel_decl_analyse")
                    
                    if st.button("Controleer Analyse", key="btn_chk_decl"):
                        if normaliseer_accent(poging) == normaliseer_accent(oef['naam']):
                            st.session_state.gram_stats[vorm_id]['goed'] += 1
                            st.session_state.gram_stats[vorm_id]['streak'] += 1
                            opslaan_naar_cloud()
                            st.session_state.decl_feedback = {'type': 'success', 'msg': f"✓ Correct! Dat was de {oef['naam']}. Hier is direct de volgende:"}
                            st.session_state.decl_oefening = kies_adaptieve_gram_vorm(vlak, prefix)
                            st.rerun()
                        else:
                            st.session_state.gram_stats[vorm_id]['fout'] += 1
                            st.session_state.gram_stats[vorm_id]['streak'] = max(0, st.session_state.gram_stats[vorm_id]['streak'] - 2)
                            opslaan_naar_cloud()
                            st.session_state.decl_feedback = {'type': 'error', 'msg': f"✗ Niet juist. Het is de: {oef['naam']}"}
                            st.rerun()

            else: # Rijtjes Produceren
                st.info("ℹ️ Gebruik Bèta-code. Accenten worden automatisch genegeerd.")
                fouten_teller = 0
                
                for label, correct in gefilterd_rijtje.items():
                    inp = st.text_input(label, key=f"decl_{gekozen_groep}_{gekozen_paradigma}_{label}")
                    if inp:
                        if normaliseer_accent(naar_grieks_transliteratie(inp)) == normaliseer_accent(correct):
                            st.success(f"✓ {correct}")
                        else:
                            st.error(f"✗ {correct}")
                            fouten_teller += 1
                
                if st.button("Check Rijtje", key="btn_chk_rijtje_decl") and fouten_teller == 0:
                    st.balloons()
        else:
            st.warning("declinaties.json ontbreekt. Run het conversiescript voor de declinaties eerst.")
