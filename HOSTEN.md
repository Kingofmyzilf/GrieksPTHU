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

### Aanbevolen: Render

Render is de enige van de drie grote met een echte gratis laag. In de repo staat
`render.yaml` klaar; kies bij Render **New → Blueprint** en wijs deze repo aan.

* **Free** — 512 MB, 0,1 CPU, gratis. Slaapt na 15 minuten zonder verkeer en doet er
  daarna ongeveer een minuut over om wakker te worden. Je voortgang blijft veilig
  (die staat in de Sheet), maar je moet na het slapen opnieuw inloggen.
* **Starter** — 512 MB, 0,5 CPU, ongeveer $7 per maand. Slaapt niet. Dit is wat je
  wilt zodra een klas de app echt gebruikt.

Zet daarna deze twee omgevingsvariabelen in het Render-dashboard (ze staan in
`render.yaml` op `sync: false`, dus Render vraagt erom):

| variabele | wat erin moet |
|---|---|
| `GSHEETS_SPREADSHEET` | de URL of de sleutel van je Google Sheet |
| `GSHEETS_CREDENTIALS` | de hele service-account-JSON, als één regel |
| `GRIEKS_STREAMLIT` | de URL van de Streamlit-app, voor de verwijzingen |

`GRIEKS_SESSIE_SLEUTEL` genereert Render zelf; die ondertekent de sessiecookie.

De inhoud voor die twee haal je uit `.streamlit/secrets.toml`, sectie
`[connections.gsheets]`. Dat bestand staat in `.gitignore` en moet daar blijven —
zet de sleutels alleen in het dashboard, nooit in de repo.

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

## 3. Wat er nog niet af is

De app op GitHub staat op branch `nicegui-opslag` en is nog niet gepusht. Wat je
host is dus pas actueel nadat die branch erop staat. `render.yaml` wijst nu naar die
branch; zet dat op `main` zodra alles samengevoegd is.
