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
    """Zorgt ervoor dat lesnummers áltijd cijfers zijn, voorkomt crashes."""
    try:
        return int(item.get('les', 1))
    except:
        return 1

def naar_grieks_transliteratie(tekst):
    """Zet latijnse invoer om naar Griekse letters (Bèta-code stijl)"""
    mapping = {
        'a': 'α', 'b': 'β', 'g': 'γ', 'd': 'δ', 'e': 'ε', 'z': 'ζ', 'h': 'η', 'q': 'θ',
        'i': 'ι', 'k': 'κ', 'l': 'λ', 'm': 'μ', 'n': 'ν', 'c': 'ξ', 'o': 'ο', 'p': 'π',
        'r': 'ρ', 's': 'σ', 't': 'τ', 'u': 'υ', 'f': 'φ', 'x': 'χ', 'y': 'ψ', 'w': 'ω'
    }
    res = ""
    tekst = str(tekst).lower().strip()
    for char in tekst:
        res += mapping.get(char, char)
    
    # Eind-sigma correctie
    if res.endswith('σ'):
        res = res[:-1] + 'ς'
    return res

def normaliseer_accent(woord):
    """Verwijdert diakritische tekens en corrigeert Latijnse 'vervuiling' uit Excel."""
    if pd.notna(woord) and str(woord).strip() != "":
        w = str(woord).strip().lower()
        w = ''.join(c for c in unicodedata.normalize('NFD', w) if unicodedata.category(c) != 'Mn')
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

def bereken_gewicht(item):
    gewicht = 1.0
    freq = int(item.get('frequentie_nt', 0))
    if freq > 0:
        gewicht += math.log10(freq + 1)
    gewicht += (int(item.get('score_fout', 0)) * 1.5)
    
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
        try:
            with open("grammatica.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            st.error(f"Fout bij inladen grammatica.json: {e}")
    return None

def laad_gebruiker_data(naam):
    try:
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
            if 'vormen_data' in r and pd.notna(r['vormen_data']):
                try: r['vormen_data'] = json.loads(str(r['vormen_data']))
                except: r['vormen_data'] = []
            else: r['vormen_data'] = []
        return user_records
    except Exception as e:
        st.error(f"Fout bij ophalen van data: {e}")
        return None

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
        conn.update(data=pd.concat([df_andere_gebruikers, pd.DataFrame(huidige_data_kopie)], ignore_index=True))
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
                alle_lessen = sorted(list(set(veilig_les_nummer(i) for i in st.session_state.data)))
                gekozen = st.multiselect("Kies lessen", alle_lessen)
                doel = [i for i in st.session_state.data if veilig_les_nummer(i) in gekozen]
            elif keuze == "Mastery":
                doel = [i for i in st.session_state.data if ((int(i.get('streak_m1',0))+int(i.get('streak_m2',0))+int(i.get('streak_m3',0)))/3) >= 20]
            
            if st.button("Start"):
                if doel:
                    doel.sort(key=bereken_gewicht, reverse=True)
                    st.session_state.sessie_lijst = random.sample(doel, min(len(doel), 10))
                    st.session_state.modus_actief = str(modus[0])
                    laad_volgend_woord()
                    st.rerun()

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
                
                # --- TYPEN MODUS ---
                if st.session_state.modus_actief == '3':
                    inp = st.text_input("Betekenis:", key=f"vocab_inp_{item.get('grieks')}").lower().strip()
                    if is_mastery and heeft_vormen:
                        p_vorm = st.text_input("Vorm (bijv. nom ev m):", key=f"inp_v_{item.get('grieks')}").lower().strip()
                    else:
                        p_vorm = huidige_parsing.lower().strip()

                    if st.button("Check"):
                        betekenis_goed = inp == maak_schoon(correct_antw) or inp in correct_antw.lower()
                        vorm_goed = p_vorm == huidige_parsing.lower().strip()

                        if betekenis_goed and vorm_goed:
                            item[actieve_streak] = int(item.get(actieve_streak, 0)) + 1
                            st.success("✓ Goed!")
                            laad_volgend_woord()
                            st.rerun()
                        else:
                            st.session_state.fouten_huidig_woord = int(st.session_state.fouten_huidig_woord) + 1
                            if st.session_state.fouten_huidig_woord >= 2:
                                item[actieve_streak] = max(0, int(item.get(actieve_streak, 0)) - 2)
                                fout_bericht = f"✗ Fout. Betekenis: {correct_antw}"
                                if is_mastery and heeft_vormen: fout_bericht += f" | Vorm: {huidige_parsing}"
                                st.error(fout_bericht)
                                st.session_state.sessie_lijst.append(item)
                            else:
                                st.warning("Bijna! Gebruik de hint en probeer nog eens.")
                # --- MEERKEUZE MODUS ---
                else:
                    correct_optie = f"{correct_antw} ({huidige_parsing})" if (is_mastery and heeft_vormen) else correct_antw
                    
                    if not st.session_state.huidige_opties:
                        afleiders = []
                        if is_mastery and heeft_vormen:
                            andere_parsings = [str(v.get('parsing', '')) for v in item.get('vormen_data', []) if str(v.get('parsing', '')) != str(huidige_parsing)]
                            if andere_parsings:
                                gekozen_foute = random.sample(andere_parsings, min(3, len(andere_parsings)))
                                for foute_p in gekozen_foute:
                                    afleiders.append(f"{correct_antw} ({foute_p})")
                        else:
                            alle_andere = [str(i.get('nederlands', '')) for i in st.session_state.data if i.get('grieks') != item.get('grieks')]
                            afleiders = alle_andere
                        
                        unieke_afleiders = list(set([str(a) for a in afleiders if a]))
                        random.shuffle(unieke_afleiders)
                        opties = unieke_afleiders[:3] + [correct_optie]
                        
                        st.session_state.huidige_opties = list(dict.fromkeys(opties))
                        random.shuffle(st.session_state.huidige_opties)
                    
                    cols = st.columns(2)
                    for idx, optie in enumerate(st.session_state.huidige_opties):
                        if cols[idx % 2].button(optie, key=f"btn_{idx}_{item.get('grieks')}"):
                            if optie == correct_optie:
                                item[actieve_streak] = int(item.get(actieve_streak, 0)) + 1
                                st.success("✓ Goed!")
                                laad_volgend_woord()
                                st.rerun()
                            else:
                                st.session_state.fouten_huidig_woord = int(st.session_state.fouten_huidig_woord) + 1
                                if st.session_state.fouten_huidig_woord >= 2:
                                    item[actieve_streak] = max(0, int(item.get(actieve_streak, 0)) - 2)
                                    st.error(f"✗ Fout. Het was: {correct_optie}")
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
                beschikbare_kolommen = [c for c in ['grieks', 'nederlands', 'streak_m1', 'streak_m2', 'streak_m3', 'woordsoort'] if c in df.columns]
                st.dataframe(df[beschikbare_kolommen], use_container_width=True)
            else:
                st.info("Geen data gevonden voor deze les.")

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

    with menu[3]: # GRAMMATICA
        gram_db = laad_grammatica_db()
        if gram_db and "λύω" in gram_db.get("werkwoorden", {}):
            luo = gram_db["werkwoorden"]["λύω"]
            st.subheader("🏛️ Grammatica Masterclass (λύω)")
            
            c1, c2, c3 = st.columns(3)
            with c1: gram_keuze = st.radio("Oefenvorm:", ["Vormen Analyseren", "Rijtjes Produceren"])
            with c2: gekozen_tijd = st.selectbox("1. Tijd/Diathese:", list(luo.keys()))
            with c3:
                wijzen_set = set()
                for k in luo[gekozen_tijd].keys():
                    wijs, _ = splits_sleutel(k)
                    wijzen_set.add(wijs)
                gekozen_wijs_input = st.selectbox("2. Modus/Wijs:", ["Alles"] + sorted(list(wijzen_set)))
            
            gekozen_wijs = None if gekozen_wijs_input == "Alles" else gekozen_wijs_input
            gefilterd_rijtje = { splits_sleutel(k)[1]: v for k, v in luo[gekozen_tijd].items() 
                                if gekozen_wijs is None or splits_sleutel(k)[0] == gekozen_wijs }

            st.write("---")

            if gram_keuze == "Vormen Analyseren":
                huidig_filter = f"{gekozen_tijd}_{gekozen_wijs_input}"
                if st.button("Nieuwe Vorm") or not st.session_state.gram_oefening or st.session_state.get('laatste_filter') != huidig_filter:
                    vlak = [{"naam": k, "vorm": v} for k, v in gefilterd_rijtje.items()]
                    st.session_state.gram_oefening = random.choice(vlak) if vlak else None
                    st.session_state.laatste_filter = huidig_filter
                
                oef = st.session_state.gram_oefening
                if oef:
                    st.markdown(f"<div class='grieks-woord'>{oef['vorm']}</div>", unsafe_allow_html=True)
                    
                    if gekozen_wijs == "Participium":
                        ca1, ca2, ca3 = st.columns(3)
                        with ca1: nv = st.selectbox("Naamval:", ["", "Nom.", "Gen.", "Dat.", "Acc."])
                        with ca2: gt = st.selectbox("Getal:", ["", "ev.", "mv."])
                        with ca3: gs = st.selectbox("Geslacht:", ["", "M", "V", "O"])
                        poging = f"{nv} {gt} {gs}".strip()
                    else:
                        poging = st.selectbox("Welke persoon/vorm is dit?", [""] + list(gefilterd_rijtje.keys()))
                    
                    if st.button("Controleer Analyse"):
                        if normaliseer_accent(poging) == normaliseer_accent(oef['naam']):
                            st.success(f"✓ Correct! Dit is inderdaad de {oef['naam']}")
                            st.session_state.gram_oefening = None
                        else:
                            st.error(f"✗ Niet juist. Het is de: {oef['naam']}")

            else: # RIJTJES PRODUCEREN
                st.info("ℹ️ Typ met normale letters. Voorbeeld: **luis** wordt **λύεις**, **luomen** wordt **λύομεν**.")
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
                                        if normaliseer_accent(naar_grieks_transliteratie(inp)) == normaliseer_accent(correct):
                                            cols[i].caption(f"✅ {correct}")
                                        else:
                                            cols[i].caption(f"❌ {correct}")
                                            fouten_teller += 1
                else:
                    for label, correct in gefilterd_rijtje.items():
                        inp = st.text_input(label, key=f"std_{gekozen_tijd}_{label}")
                        if inp:
                            if normaliseer_accent(naar_grieks_transliteratie(inp)) == normaliseer_accent(correct):
                                st.success(f"✓ {correct}")
                            else:
                                st.error(f"✗ {correct}")
                                fouten_teller += 1
                
                if st.button("Check Rijtje") and fouten_teller == 0:
                    st.balloons()
        else:
            st.warning("grammatica.json is niet goed geladen of bevat het werkwoord 'λύω' niet.")
