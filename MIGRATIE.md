# Migratie Streamlit → NiceGUI

Wat er in `overhoring_web.py` zit en wat er in de NiceGUI-app (`grieks_app.py`) staat.
Bijgewerkt na een systematische vergelijking van alle widgets per tabblad.

## Fundament — klaar

| | status |
|---|---|
| Griekse motor (`grieks_motor.py`, 160 functies) | klaar, 1.305 vergelijkingen identiek |
| Opslag naar dezelfde Google Sheet (`grieks_opslag.py`) | klaar, live getest |
| Inloggen + scores terugschrijven (`grieks_gebruiker.py`) | klaar |
| Onderbalk, Vandaag, Voortgang (basis), Oefenen-lijst | klaar |

## Woordenschat — klaar

Aanwezig: oefening (7 soorten), lessenkeuze, oefenvorm, kaarten per ronde,
nieuwe woorden mee-oefenen, uitspraakknop, woordopbouw.
Plus: statusbalkje, hint, opbouw, leerkaart bij nieuwe woorden, feedbackblok.

- [x] Level kiezen binnen het Leerpad, met XP/rang-kop (nog te doen: "Toon het hele pad")
- [x] Oude stof meenemen (0 / 5 / 10 / alleen level)
- [x] Nieuwe woorden per sessie als aantal
- [x] Sessie opbouw: Aanbevolen mix vs Zelf samenstellen (vijf fase-tellers, met
      per fase hoeveel er in de gekozen poule klaarstaat)
- [x] Beheerste woorden (streak 30+) als echte verbogen vorm uit het NT, met de
      parsing en de vindplaats in de feedback — vervangt "mastery in Bijbelcontext"
- [x] Verwarwoorden er samen bij trekken (discrimineren)
- [~] Bijbelcontext-modus, kaartenbak-clustering en naamvalkleuring in de zin:
      LATEN VALLEN op verzoek. Die oefen je in Leesteksten en Ontleden.
- [x] Verwarparen als paar-oefening (`/oefenen/paren`, met overtikken na twee
      missers) + de eindsamenvatting waarin je zelf bevestigt wat je verwarde

## Stamtijden — kern klaar

Aanwezig: 4 oefeningen, vraagvorm (automatisch/tijd/tijd+werkwoord, drempel 10),
vormen per ronde, uitgangen kleuren, feedback met opbouw.

Nog te doen:
- [ ] Filter op Bijbelboek / hoofdstuk / les
- [ ] Flashcard-modus ("Leer") naast herkennen
- [ ] Spiekbrief: hoe typ ik Grieks met Latijnse toetsen

## Actief Beheersen — kern klaar

Aanwezig: 3 oefeningen, niveaufilter, vraagvorm, cellen per ronde, afleiders uit
het eigen rijtje, feedback met stam + gekleurde uitgang en toelichting.

Nog te doen:
- [ ] Tentamenrooster (heel rijtje in één keer invullen)
- [ ] Spiekbrief Griekse toetsaanslagen

## Structuurwoorden — klaar

Aanwezig: 4 oefeningen, categoriefilter, vraagvorm, aantal per ronde.
Geen bekende gaten.

## Ontleden — kern klaar

Aanwezig: niveau, streak-drempel, naamvallen kleuren (nu ook tijdens het invullen),
rijtje spieken, vertaalhulp, BibleHub-links, elk met een eigen schakelaar.

Nog te doen:
- [ ] Rondekeuze (welke van de vijf rondes je wilt doen)
- [ ] Losse kleurschakelaars: voegwoorden, stamtijden, uitgangen
- [ ] Toon samensmeltingen
- [ ] Oranje uitgangen + gouden kader om jouw vorm in het rijtje
      (`_render_gramtabel_html` heeft er parameters voor: kolom_target, mark_row, mark_col)
- [ ] "Zo vertaalt de Bijbel deze vorm" (vindplaatsen in het NT)
- [ ] De rijtjes van álle woorden in deze zin
- [ ] Vergelijkbare vormen (andere spelling/accent)
- [ ] Vertaalrondes: woord voor woord en de hele zin

## Voortgang — klaar

Aanwezig: niveau en rang, accuratesse, beheerst, oefendagen, dagstreak, vandaag,
NT-dekking, woorden-dekking, uitloggen.

- [x] Oefenritme-kalender (vijf weken, met een stip per gehaald dagdoel)
- [x] Dagelijks doel instellen + voortgang per onderdeel vandaag
- [x] Gedetailleerde voortgang per onderdeel (fasen per onderdeel, lekkende emmer,
      per tentamen, ontleed-accuratesse)
- [x] Badges
- [x] Hardnekkige probleemwoorden
- [x] Studieplanner (kennis-diepte, tempo, verwachte accuratesse, einddatum)
- [x] Competitiedashboard + scorebord (leest en schrijft hetzelfde
      Scorebord-tabblad als de Streamlit-app, sleutelkolom `gebruiker`)
- [x] CSV-export

Alle vijf de oefenonderdelen tellen nu mee in `dag_stats` en in het dagdoel-logboek
(`Gebruiker.tel_dag` en `dagdoel_plus`); daarvoor deed alleen Woordenschat dat.

## Nog helemaal niet gebouwd

- [ ] **Klankwetten** — 5 instellingen, filter op klanksoort, aparte scorelijst
- [ ] **Leesteksten** — 17 instellingen, vier methodes waaronder Masterclass
- [ ] **Nederlands → Grieks**
- [ ] **Grammatica** — slides uit de PDF, thema-filter, overzichten
- [ ] **Lijst** — woordenlijst en verwarparen bekijken
- [ ] **Uitleg & Hulp** — inclusief de schakelaar geavanceerde opties en
      het aan/uit zetten van tabbladen

## Bekende afwijkingen (bewust)

- Opslaan gebeurt na elke beurt in plaats van elke vijf; kan hier omdat het in een
  aparte thread draait terwijl je de feedback leest.
- Ontleden is één doorlopende reeks vragen in plaats van vijf aparte rondes.
- Instellingen staan in `ui_prefs` met een `ng_`-voorvoegsel, zodat ze niet botsen
  met de Streamlit-sleutels. Het dagdoel deelt wél dezelfde `dagdoel`-dict; alleen
  de doelen die hier instelbaar zijn worden overschreven, de rest blijft staan.
- Het scorebord wordt bijgewerkt zodra je de competitie-uitklapper opent, niet bij
  elke opslag; dat scheelt schrijfbeurten op de gedeelde Sheet.
- In de paar-oefening wist een misser de streak niet (alleen score_fout gaat omhoog).
  Het is een onderscheid-oefening, geen gewone overhoring — net als in Streamlit.
