# Overdracht — van de eerste sessie (fundament + Streamlit) naar de NiceGUI-sessie

Geschreven op 17 augustus 2026 door de sessie die de motor heeft losgemaakt, de
opslaglaag heeft gebouwd en daarna de Streamlit-app is blijven onderhouden.
Bedoeld voor de sessie die de NiceGUI-app afmaakt.

Wat hierin staat is wat **niet uit de code of git blijkt**: waarom iets zo is, en
welke valkuilen er al twee keer hebben toegeslagen.

---

## 1. Waarom de opzet is zoals hij is

**De motor is gegenereerd, niet met de hand geschreven.**
`grieks_motor.py` komt uit `scratchpad/bouw_motor.py`, dat de functies uit
`overhoring_web.py` haalt die geen Streamlit aanraken. Pas je de motor met de hand
aan, dan is die aanpassing weg zodra iemand opnieuw genereert. Wijzig dus de bron
of de generator.

De generator kent drie dingen die je moet weten:
- functies die `st.`, `components.` of `conn.` gebruiken vallen af (`conn.` is opslag,
  geen motor — daar viel `lees_scorebord` op door);
- `_TIJDZONE` en `fitz` staan in de bron in een `try`-blok en zijn daarom apart
  meegegeven in de preambule, niet uit de bron gekopieerd;
- `EXTRA_VAR` bevat taalkundige tabellen die geen motorfunctie aanroept maar de
  schil wel nodig heeft (`_VOORZETSEL_INFO` voor de woordopbouw).

**De cache is nagebouwd, niet weggelaten.**
`@st.cache_data` en `@st.cache_resource` zijn vervangen door een eigen implementatie
met exact dezelfde semantiek: argumenten met een `_`-prefix tellen niet mee in de
sleutel, `cache_data` geeft een kopie terug en `cache_resource` het gedeelde object,
en `.clear()` werkt (nodig voor `voortgang_kernstats` en `lees_scorebord`).
Die kopie is bewust: zonder kopie zou een aanroeper de cache kunnen muteren.

**De verificatie die je moet blijven draaien.**
`scratchpad/test_motor.py` vergelijkt de motor met het origineel op echte data:
60 woorden, 250 willekeurige bijbelvormen door de vier zwaarste ontleedfuncties, plus
de constanten. Dat waren 1.305 vergelijkingen met 0 verschillen. Draai dit na élke
regeneratie van de motor.

**Waarom `grieks_gebruiker.py` bestaat.**
`woord_opbouw()` en `fase_van()` konden niet mee naar de motor: de Streamlit-versie
van `woord_opbouw` haalt de woordenlijst uit `st.session_state`. Hier is die lijst een
parameter. Als je meer van dat soort functies tegenkomt, is dit de plek.

---

## 2. Valkuilen die al hebben toegeslagen

**NiceGUI wikkelt elk element in een eigen div.**
Zet je losse elementen in een flex-container, dan staat je `flex:1` op het element
*binnen* de wrapper en verdeelt de balk zich niet. De onderbalk viel daardoor uiteen
in twee rijen, en de statusvakjes werden ongelijk hoog. Oplossing: zulke rijen als
één `ui.html()`-blok bouwen. Zie `onderbalk()` en `_statusrij()`.

**`ui.run.io_bound` bestaat niet.** Het is `from nicegui import run` → `run.io_bound`.
`ui.run()` is de startfunctie.

**`ui.add_head_html` in globale scope vereist `shared=True`** in NiceGUI 3.x.

**Norton breekt https in Python.** Virusscanners die meelezen vervangen het
certificaat van Google; dat staat in de Windows-opslag maar niet in die van Python,
dus je krijgt `CERTIFICATE_VERIFY_FAILED` — ook mét certifi. `grieks_opslag.py`
importeert daarom `truststore`. Verificatie blijft aan; zet die nooit uit.

**De tellercel uit Google komt soms als `'3.0'`.** Naïef `int()` geeft dan nul stukken,
dus een lege dict, en dat overschrijft bij de eerstvolgende opslag je hele voortgang.
Altijd `int(float(...))`. `grieks_opslag.lees_rij` weigert bovendien te lezen als een
teller N stukken belooft die er niet zijn.

**NFC/NFD.** Dezelfde Griekse letters staan soms als NFC en soms als NFD in de data.
Vergelijk altijd genormaliseerd. Dit beet bij `lexeem_info != grieks` in het
feedbackblok.

**Feedback mag niet vooruit verklappen.** In Ontleden toonde de feedback de volledige
parsing terwijl de naamval, het geslacht en het getal daarna nog gevraagd werden.
Toon alleen de dimensie die net beantwoord is; de volledige parsing en de vertaalhulp
pas als alle vragen over dat woord op zijn.

**`_ontleed_tip_tabellen` geeft namen terug, geen tabellen.** De rijen staan in
`laad_gramtabellen()`. Geef je de naam door aan `_render_gramtabel_html`, dan krijg je
een tabel van één letter per rij.

**Voor de woordsoortvraag moet je `_ONTLEED_WS_OPTS` gebruiken.** De verkorte lijst uit
`_ontleed_dims` bevat geen 'Voorzetsel', waardoor het juiste antwoord bij zo'n woord
ontbrak en de vraag onwinbaar was.

**Dubbelklik.** Een tweede tik op 'Volgende' schoof door én klaagde daarna dat er geen
antwoord gekozen was. Elke oefenlus heeft nu een `bezig`-grendel; houd die erin.

---

## 3. Wat Bob concreet miste, en wat ik daarvan terugvond

**"Ik mis aan het einde dat ik verwarwoorden kan aanvinken."**
De eindsamenvatting bestáát (`toon_samenvatting()`, `grieks_app.py:1427`) en wordt
aangeroepen als de ronde leeg raakt. Maar het blok "Mogelijk verward" slaat zichzelf
over met `if not sessie.kandidaten: return`, en `verwar_kandidaten()` vult die lijst
alleen als zijn foute antwoord precies de betekenis van een ánder woord is.

Te controleren: is dat net zo streng als in Streamlit? Daar verzamelt
`bouw_verwar_melding(..., onthoud=True)` de kandidaten, en dat gebeurt ook bij een
foute meerkeuzeklik (`huidige_optie_bron`) — dus ook als je op het verkeerde
knopje klikte, niet alleen bij typen. Als de NiceGUI-versie alleen op typen kijkt,
ziet Bob dit blok bijna nooit.

---

## 4. Openstaand aan de Streamlit-kant

De Streamlit-app is nog steeds de app die Bob dagelijks gebruikt, en die staat op
`main`. Deze vier commits met `overhoring_web.py`-wijzigingen staan **alleen op
`nicegui-opslag`** en dus niet live:

- `8424633` + `7b6a362` — verwijzing van Grammatica-zoeken naar Ontleden
  (we hebben die per ongeluk dubbel toegevoegd; `35a4f8d` ruimde dat op)
- `896eb38` — bevat ook de drie Actief Beheersen-verbeteringen:
  1. herhaalvormen uit andere rijtjes gaan achteraan in de rij in plaats van
     ertussendoor (`_q.extend` i.p.v. `_q.insert`), want middenin het rijtje van
     'jij/jullie' de accusativus van 'ik/wij' krijgen gaat per definitie fout;
  2. de feedback staat via `_toon_af_feedback()` vlak boven de nieuwe vraag in plaats
     van bovenaan het tabblad, waar hij wegviel zodra het invoerveld de focus pakte;
  3. nieuwe functie `welke_vorm_typte_je()` meldt welke cel je wél typte — 'jij typte
     de Gen ev, gevraagd was de Dat ev'. Werkt op alle 66 rijtjes.

Die horen naar `main`, bij voorkeur als losse branch met alleen `overhoring_web.py`:

```
git checkout -b streamlit-fixes main
git checkout nicegui-opslag -- overhoring_web.py
git commit -m "Actief Beheersen: rijtje eerst af, feedback bij de vraag, verwisseling melden"
git push -u origin streamlit-fixes
```

---

## 5. Werkafspraken met Bob

- **Typen wordt streng nagekeken** ("Nee, want je moet het goed doen!"), maar
  `check_betekenis` blijft verdraagzaam — je ziet het juiste antwoord er toch bij.
- **Verkeerde uitleg is erger dan geen uitleg.** De app verzint geen etymologie: bij
  ἀναβαίνω laat `woord_opbouw` niets zien omdat βαίνω niet los in de lijst staat.
  Houd dat zo.
- **Hij test op zijn telefoon en stuurt schermafbeeldingen.** Dat heeft vier dingen
  gevonden die met DOM-tests onvindbaar waren: de onderbalk, het statusbalkje, het
  feedbackblok en de leerkaart. Meet altijd óók of het scherm past
  (`scrollHeight > innerHeight`) — hij scrolt niet graag tijdens het oefenen.
- **Aanwijzen vóór typen.** Typen op een telefoon is foutgevoelig; hij vroeg
  expliciet om de drempel op streak 10 te zetten voor stamtijden en actief beheersen.
- **Eén sessie tegelijk in deze map.** Twee chats die tegelijk in
  `overhoring_web.py` schreven leverden een dubbele caption op en lieten een keer
  ongecommit werk verdwijnen. Een nieuwe chat geeft géén eigen werkkopie.

---

## 6. Waar de dingen staan

| | |
|---|---|
| `MIGRATIE.md` | stand per tabblad, afgevinkt |
| `HOSTEN.md` + `render.yaml` | hostingvoorbereiding |
| `scratchpad/bouw_motor.py` | genereert `grieks_motor.py` |
| `scratchpad/test_motor.py` | 1.305 vergelijkingen motor vs origineel |
| `scratchpad/test_opslag.py` | 9 kruistests op het Sheet-formaat |
| `.streamlit/secrets.toml` | service-account, staat in `.gitignore` — nooit committen |
