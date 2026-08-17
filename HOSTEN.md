# De NiceGUI-app buiten je eigen netwerk bereikbaar maken

Twee dingen door elkaar: **even ergens anders kunnen kijken** en **echt hosten**.
Voor het eerste hoef je niets te installeren.

## 1. Snel even delen — NiceGUI On Air

Start de app zo, dan krijg je in de terminal een openbare URL die je op je telefoon
of op een ander netwerk kunt openen:

```bash
set GRIEKS_ON_AIR=1 && py grieks_app.py
```

De app blijft gewoon op jouw computer draaien; On Air zet er alleen een tunnel
naartoe. Een willekeurige URL is een uur geldig. Wil je een vaste URL, vraag dan een
gratis token aan op [on-air.nicegui.io](https://on-air.nicegui.io) en gebruik dat:

```bash
set GRIEKS_ON_AIR=jouw-token && py grieks_app.py
```

Let op: zolang die URL open staat kan iedereen die hem heeft bij de app. Voortgang
zit achter naam + codewoord, maar dat is geen wachtwoord — deel de link dus niet
breder dan nodig, en sluit de app als je klaar bent.

## 2. Echt hosten

### Licht of volledig

De NT-tekst (`bijbel_nt_deel1.json` + `deel2.json`, samen 31 MB) is optioneel. Laat je
die weg, dan draait de app gewoon door; alleen wat de bijbeltekst nodig heeft vervalt,
en de app zegt dat zelf met een link naar de Streamlit-app:

* Ontleden
* de verbogen vorm uit het NT bij beheerste woorden
* het filter 'uit een Bijbeltekst' bij Stamtijden

Wat blijft: Woordenschat (inclusief verwarparen), Structuurwoorden, Stamtijden,
Actief Beheersen, Voortgang en de Lijst.

| | licht | volledig |
|---|---|---|
| Geheugen | 121 MB | 218 MB |
| Databestanden | 1,8 MB | 55 MB |

Zet `GRIEKS_STREAMLIT` op de URL van de Streamlit-app, dan wijst de lichte versie
overal netjes de weg.

### Wat de app nodig heeft

| | |
|---|---|
| Geheugen | 121 MB licht, 218 MB met de NT-tekst |
| Instanties | **precies één** — zie hieronder |
| Verbinding | WebSockets, want NiceGUI stuurt elke klik over een open verbinding |
| Opslag | geen schijf nodig; alle voortgang gaat naar de Google Sheet |
| Python | 3.11 of nieuwer (`tomllib` zit vanaf 3.11 in de standaardbibliotheek) |

**Waarom één instantie:** wie is ingelogd staat in het geheugen van het proces
(`_sessies` in `grieks_app.py`). Draaien er twee, dan kom je bij elke klik misschien
op de andere terecht en moet je steeds opnieuw inloggen. Zet autoscaling dus uit.

### Waarom niet Streamlit Community Cloud

Dat platform draait alleen Streamlit-apps (`streamlit run ...`). De Streamlit-versie
kan daar blijven staan; de NiceGUI-app heeft een gewone Python-host nodig.

### De bestaande service ombouwen

Er draait al een Render-service **GrieksPTHU** (`griekspthu.onrender.com`) die van
`main` de Streamlit-app uitrolt. Die is overbodig geworden — Streamlit staat ook op
Streamlit Community Cloud — en de 750 gratis uren per maand gelden voor je hele
account samen. Bouw hem dus om in plaats van er een tweede naast te zetten.

In **Settings → Build & Deploy**:

| veld | van | naar |
|---|---|---|
| Branch | `main` | `nicegui-deploy` |
| Build Command | (streamlit) | `pip install -r requirements-nicegui.txt` |
| Start Command | (streamlit) | `python grieks_app.py` |

En in **Environment** deze vier erbij (of controleren):

| variabele | waarde |
|---|---|
| `GSHEETS_CREDENTIALS` | de service-account-JSON, als één regel |
| `GSHEETS_SPREADSHEET` | de URL of sleutel van je Google Sheet |
| `GRIEKS_STREAMLIT` | `https://woordengriekspthu.streamlit.app` |
| `GRIEKS_SESSIE_SLEUTEL` | een willekeurige lange tekst; ondertekent de sessiecookie |

Deze service is met de hand aangemaakt, niet uit `render.yaml`. Render kan hem
daarom niet alsnog aan die blauwdruk koppelen: als je **New → Blueprint** doet krijg
je een tweede service ernaast. `render.yaml` blijft wél kloppen als beschrijving van
wat er moet staan, en is handig als je ooit opnieuw begint.

### Helemaal opnieuw beginnen: Render Blueprint

Kies **New → Blueprint** en wijs deze repo aan; Render leest `render.yaml` en vraagt
om de drie waarden met `sync: false`. `GRIEKS_SESSIE_SLEUTEL` verzint hij zelf.

### Welk plan

* **Free** — 512 MB, 0,1 CPU, gratis. Slaapt na 15 minuten zonder verkeer en doet er
  daarna ongeveer een minuut over om wakker te worden. Je voortgang blijft veilig
  (die staat in de Sheet), maar je moet na het slapen opnieuw inloggen: wie is
  ingelogd staat in het geheugen van het proces.
* **Starter** — 512 MB, 0,5 CPU, ongeveer $7 per maand. Slaapt niet. Dit is wat je
  wilt zodra een klas de app echt gebruikt.

De 750 gratis instance-uren per maand gelden voor je hele account, niet per service.
Twee gratis services die allebei wakker zijn halveren dus je budget.

### De sleutels

De inhoud voor `GSHEETS_CREDENTIALS` en `GSHEETS_SPREADSHEET` haal je uit
`.streamlit/secrets.toml`, sectie `[connections.gsheets]`. Dat bestand staat in
`.gitignore` en moet daar blijven — zet de sleutels alleen in het dashboard, nooit
in de repo. De JSON als één regel op je klembord:

```bash
py -c "import tomllib,json;b=tomllib.load(open('.streamlit/secrets.toml','rb'))['connections']['gsheets'];print(json.dumps({k:v for k,v in b.items() if k not in ('spreadsheet','url','worksheet')}))" | clip
```

### Alternatieven

* **Fly.io** — geen gratis laag meer (alleen een proef van 2 VM-uren of 7 dagen),
  maar wel het sterkst in langlopende verbindingen. Betaal per seconde. Let op:
  zet `min_machines_running = 1`, anders slaapt de machine net als bij Render gratis.
* **Railway** — geen gratis laag; Hobby kost $5 per maand inclusief $5 tegoed.
* **Eigen VPS** (Hetzner e.d., vanaf ~€4) — meeste vrijheid, meeste werk: zelf
  systemd, NGINX en een certificaat regelen.

### Deployen zonder blauwdruk

Werkt op elk platform dat Python draait:

* installeren: `pip install -r requirements-nicegui.txt`
* starten: `python grieks_app.py`
* poort: de app pakt `PORT` uit de omgeving en luistert op `0.0.0.0`

## 3. De deploytak

Een hostingplatform kloont de tak die je aanwijst. Staan de NT-tekst (31 MB), de
grammatica-PDF (22 MB) en de Streamlit-app er nog in, dan wacht je daar bij elke
deploy op — en op de gratis laag, die vaak herstart, merk je dat.

Daarom is er `nicegui-deploy`: alleen de app en de zeven databestanden die hij echt
opent. **1,3 MB in plaats van 55.** `render.yaml` wijst daarnaar.

Die tak wordt telkens opnieuw gemaakt vanaf de werktak — hij heeft geen eigen
geschiedenis en je past hem nooit met de hand aan:

```bash
py gereedschap/maak_deploy.py
```

```bash
git push -f origin nicegui-deploy
```

Wat er niet in zit: de bijbelbestanden, de grammatica-PDF, `overhoring_web.py`, de
praatplaten, de APK, het gereedschap en de tests. De app draait dan in de lichte
stand (zie hierboven) en wijst voor de rest naar de Streamlit-app.

## 4. Waar de code staat

| tak | waarvoor |
|---|---|
| `main` | de Streamlit-app; die deployt Streamlit Community Cloud |
| `nicegui-opslag` | de werktak van de NiceGUI-app |
| `nicegui-deploy` | wat er gehost wordt; gemaakt door het script hierboven |
