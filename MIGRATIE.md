# Migratie Streamlit → NiceGUI

Wat er in `overhoring_web.py` zit en wat er in de NiceGUI-app (`grieks_app.py`) staat.
Bijgewerkt na een systematische vergelijking van alle widgets per tabblad.

## Stand per tabblad

De Streamlit-app heeft twaalf tabbladen (`TAB_KEUZE`, overhoring_web.py:3374).

| Streamlit-tabblad | NiceGUI | status |
|---|---|---|
| 🚀 Woordenschat | `/oefenen/woorden`, `/oefenen/paren` | klaar, regel voor regel vergeleken |
| 🎓 Actief Beheersen | `/oefenen/actief`, `/oefenen/actief/rooster` | klaar |
| ⏳ Stamtijden | `/oefenen/stamtijden`, `.../leren` | klaar |
| 🧱 Structuurwoorden | `/oefenen/structuur` | klaar |
| 📊 Voortgang | `/voortgang` | klaar |
| 📖 Lijst | `/lijst` | klaar |
| 🔎 Ontleden | `/oefenen/ontleden` | kern klaar, acht opties open |
| 📝 Leesteksten | — | niet gebouwd |
| 🔊 Klankwetten | — | niet gebouwd |
| 📐 Grammatica | — | niet gebouwd |
| ℹ️ Uitleg & Hulp | — | niet gebouwd |
| ✍️ NL → Grieks | — | niet gebouwd |

## Fundament — klaar

| | status |
|---|---|
| Griekse motor (`grieks_motor.py`, 160 functies) | klaar, 1.305 vergelijkingen identiek |
| Opslag naar dezelfde Google Sheet (`grieks_opslag.py`) | klaar, live getest |
| Inloggen + scores terugschrijven (`grieks_gebruiker.py`) | klaar |
| Onderbalk, Vandaag (alle onderdelen klaargezet), Oefenen-lijst | klaar |
| Grieks typen met Latijnse toetsen (spiekbrief achter ⌨ waar je Grieks typt) | klaar |

## Woordenschat — klaar, systematisch vergeleken met tab 0 van Streamlit

De oefenlus is gelijk: de ronde is een wachtrij, dus een gemist woord komt terug.
Eerste misser kost geen streak (hint + herkansing), tweede misser of streak 16+ kost
er twee en gaat via overtikken. Typen levert +3 op, aanwijzen +1, Mix het dubbele bij
een schone combo. 'Ik weet het niet' toont het antwoord zonder aftrek. Afleiders in
dezelfde volgorde: verwarparen-twins, dan spelling-lookalikes binnen de woordsoort,
dan de rest. Poules (knelpunten, lang niet gedaan, gelijkende woorden, mijn
verwarwoorden) gebruiken dezelfde filters, en de instroom van nieuwe woorden ligt stil
bij knelpunten, lang-niet-gedaan en puur typen.


- [x] Level kiezen binnen het Leerpad, met XP/rang-kop, "Toon het hele pad" en
      "Hierna: level X"
- [x] Oude stof meenemen (0 / 1 / 5 / 10)
- [x] Nieuwe woorden per sessie als aantal, plus de melding hoeveel nieuwe woorden
      er nog in dit level wachten
- [x] Sessie opbouw: Automatisch (de motor weegt hoe zwaar je woorden zijn en bepaalt
      zelf de omvang, zoals Streamlit) / Vast aantal kaarten / Zelf samenstellen met
      vijf fase-tellers en per fase hoeveel er klaarstaat
- [x] Beheerste woorden (streak 30+) als echte verbogen vorm uit het NT, met de
      parsing en de vindplaats in de feedback — vervangt "mastery in Bijbelcontext"
- [x] Verwarwoorden er samen bij trekken (discrimineren), met instelbaar maximum
- [x] Verwarparen als paar-oefening (`/oefenen/paren`, met hint, overtikken na twee
      missers en een stopknop) + de eindsamenvatting waarin je zelf bevestigt wat je
      verwarde
- [x] Uitspraakknop spreekt het woord echt uit (Web Speech API op de Erasmiaanse
      transliteratie, net als in Streamlit — geen Nieuwgriekse stem dus)
- [~] Bijbelcontext-modus, kaartenbak-clustering en naamvalkleuring in de zin:
      LATEN VALLEN op verzoek. Die oefen je in Leesteksten en Ontleden.
- [~] Mastery-parsingvragen (naamval/getal/geslacht invullen bij een beheerst woord)
      en de bijbehorende "inhoudelijk juist, ontleding fout"-feedback: vervallen met
      de Bijbelcontext-modus. In plaats daarvan krijg je een echte NT-vorm te zien.

Alleen hier, niet in Streamlit: de stijl "Vast aantal kaarten", een instelbaar maximum
voor de verwarwoorden, expliciete levelkeuze, de streepjesbalk met teller, losse
hint-knop, bediening met Enter, en een slot tegen dubbelklikken.

## Stamtijden — klaar

Aanwezig: 4 oefeningen, vraagvorm (automatisch/tijd/tijd+werkwoord, drempel 10),
vormen per ronde, uitgangen kleuren, feedback met opbouw.

- [x] Filter op Bijbelboek + hoofdstuk of op losse lessen (de tekstfilter zoekt de
      Strong-nummers in dat hoofdstuk op en houdt de werkwoorden over die je daar
      tegenkomt; boeknamen zijn Engels, zoals in de NT-data)
- [x] Flashcard-modus "Leren" naast overhoren (`/oefenen/stamtijden/leren`): vorm
      zien, jezelf checken, 'wist ik' of 'nog niet' — dat laatste komt achteraan terug
- [x] Spiekbrief: hoe typ ik Grieks met Latijnse toetsen (⌨-knopje in de kop)
- [x] Werkwoordpaspoort (klasse, stamwortel, Strong, mutatieregel met toelichting,
      markering van de onregelmatige werkwoorden) — staat bij Stamtijden in de Lijst
      in plaats van als eigen oefenmodus

## Actief Beheersen — klaar

Aanwezig: 3 oefeningen, niveaufilter, vraagvorm, cellen per ronde, afleiders uit
het eigen rijtje, feedback met stam + gekleurde uitgang en toelichting.

- [x] Tentamenrooster: heel rijtje in één keer invullen (`/oefenen/actief/rooster`).
      Goede cellen worden vastgezet, foute velden leeggemaakt voor een nieuwe poging.
- [x] "Alleen de uitgangen": de stam staat er al, jij typt alleen wat erachter komt
- [x] Paradigma-paspoort ("Bekijk het rijtje") op beide schermen: stam wit, uitgang cyaan
- [x] Spiekbrief Griekse toetsaanslagen

## Structuurwoorden — klaar

Aanwezig: 4 oefeningen, categoriefilter, vraagvorm, aantal per ronde.

- [x] Leerpad in blokjes van zes zoals de motor ze bouwt (het groepeerde eerst op
      categorie, waardoor 'volgend blokje' soms dertig woorden pakte), met keuzelijst
      van de ontgrendelde blokjes, "Hierna: blokje X" en het rijtje eerst kunnen lezen

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

## Lijst — klaar

`/lijst`, te bereiken via Lezen. Woordenschat, verwarparen, structuurwoorden en
stamtijden opzoeken met je eigen streaks erbij, met zoekveld op Grieks of Nederlands
en een filter 'alleen wat ik al geoefend heb'. Bij Stamtijden staat het
werkwoordpaspoort erbij.

## Nog helemaal niet gebouwd

- [ ] **Klankwetten** — 5 instellingen, filter op klanksoort, aparte scorelijst.
      De motor heeft alles al: `klankwet_index`, `klankwet_formule_index`,
      `samensmeltingen_alle`, `klank_afleiders`, `klank_opbouw_regels`,
      `klank_vorm_gemarkeerd`. Alleen de schil ontbreekt.
- [ ] **Leesteksten** — de grootste: boek/hoofdstuk/verzen kiezen, drie kleurlagen
      (naamvallen, stamtijden, voegwoorden), ontleedvragen per woord met alle acht
      dimensies, vier methodes waaronder Masterclass
- [ ] **Nederlands → Grieks** — lessenkeuze, meerkeuze op de juiste Griekse vorm,
      spiekbrief (die laatste is er al als gedeelde component)
- [ ] **Grammatica** — slides uit `grammatica_overzicht.pdf` (via pymupdf), thema-filter,
      losse overzichten en de contractietrainer
- [ ] **Uitleg & Hulp** — inclusief de schakelaar geavanceerde opties en het aan/uit
      zetten van tabbladen. Zolang die er niet is, toont de NiceGUI-app altijd alles;
      de Streamlit-app kent een eenvoudige modus die opties verbergt.

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
- Een sessie leeft in de pagina, niet in een sessie-opslag: navigeer je weg van
  `/oefenen/woorden`, dan begin je bij terugkomst een nieuwe ronde. In Streamlit
  overleeft de wachtrij een tabwissel.
- "Nieuwe woorden per sessie" geldt hier bij elke oefening; in Streamlit stuurt die
  schuif alleen het Leerpad en gebruikt de rest de standaard van de motor.
- Kies je in het Leerpad "Vast aantal kaarten" of "Zelf samenstellen", dan gaat de
  ronde via de motor in plaats van via de Leerpad-opbouw. Streamlit negeert die keuze
  in het Leerpad; hier telt hij, anders zou je instelling niets doen.
- Geen ballonnen bij een afgeronde ronde, en geen eenvoud/geavanceerd-schakelaar —
  die hoort bij Uitleg & Hulp en is nog niet overgezet.
