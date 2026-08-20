# -*- coding: utf-8 -*-
"""Zet een gedownloade service-account-sleutel op de goede plekken.

Een sleutel vervangen moet op drie plaatsen gebeuren, en met de hand gaat dat mis: één
regel over het hoofd zien levert 'invalid_grant: Invalid JWT Signature' op — dan klopt het
private_key_id wel maar de sleutel eronder niet, en die foutmelding zegt dat niet.

Dit script neemt het JSON-bestand dat je uit de Google Cloud Console downloadt en:

  * schrijft .streamlit/secrets.toml opnieuw, met de bestaande spreadsheet-URL erin;
  * zet de éénregelige JSON voor Render in een los bestand klaar om te kopiëren;
  * zet het hele TOML-blok voor Streamlit Cloud in een los bestand klaar.

Die twee losse bestanden staan in een map die in .gitignore staat, en het script zegt aan
het eind hoe je ze weer weggooit. De sleutel wordt nooit op het scherm getoond.

Draaien:

    py gereedschap/zet_sleutel.py "C:/Users/kingo/Downloads/grieks-tutor-xxxx.json"
"""
import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS = os.path.join(REPO, ".streamlit", "secrets.toml")
KLADMAP = os.path.join(REPO, "sleutel_klaar")

# De velden van een service-account, in de volgorde waarin Google ze zelf zet.
VELDEN = ["type", "project_id", "private_key_id", "private_key", "client_email",
          "client_id", "auth_uri", "token_uri", "auth_provider_x509_cert_url",
          "client_x509_cert_url"]


def huidige_spreadsheet():
    """De spreadsheet-URL uit het bestaande secrets.toml; die staat niet in de sleutel."""
    if not os.path.exists(SECRETS):
        return ""
    try:
        import tomllib
        with open(SECRETS, "rb") as f:
            return tomllib.load(f).get("connections", {}).get("gsheets", {}).get(
                "spreadsheet", "")
    except Exception:
        # Nog geen tomllib, of het bestand is stuk: dan met de hand die ene regel zoeken.
        for regel in open(SECRETS, encoding="utf-8"):
            if regel.strip().startswith("spreadsheet"):
                return regel.partition("=")[2].strip().strip('"')
        return ""


def toml_blok(sleutel, spreadsheet):
    """Het [connections.gsheets]-blok. De sleutel als gewone string met \\n-escapes, want
    dat is de vorm die Streamlit en de mobiele app allebei al lezen."""
    regels = ["[connections.gsheets]"]
    if spreadsheet:
        regels.append(f'spreadsheet = "{spreadsheet}"')
    for veld in VELDEN:
        waarde = str(sleutel.get(veld, ""))
        # json.dumps doet het escapen goed, inclusief de regeleindes in de sleutel.
        regels.append(f"{veld} = {json.dumps(waarde)}")
    return "\n".join(regels) + "\n"


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("bestand", help="het JSON-bestand uit de Google Cloud Console")
    args = p.parse_args()

    if not os.path.exists(args.bestand):
        sys.exit(f"{args.bestand} bestaat niet.")
    with open(args.bestand, encoding="utf-8") as f:
        sleutel = json.load(f)
    if sleutel.get("type") != "service_account":
        sys.exit("Dit lijkt geen service-account-sleutel: 'type' is niet 'service_account'.")
    ontbreekt = [v for v in VELDEN if not sleutel.get(v)]
    if ontbreekt:
        sys.exit(f"Deze velden ontbreken in het bestand: {', '.join(ontbreekt)}")

    spreadsheet = huidige_spreadsheet()
    if not spreadsheet:
        print("Let op: er stond geen spreadsheet-URL in secrets.toml. Zet die er straks")
        print("met de hand bij, anders weet de app niet welke Sheet hij moet openen.")

    os.makedirs(os.path.dirname(SECRETS), exist_ok=True)
    with open(SECRETS, "w", encoding="utf-8") as f:
        f.write(toml_blok(sleutel, spreadsheet))
    print(f"secrets.toml opnieuw geschreven ({sleutel['client_email']}, "
          f"sleutel {sleutel['private_key_id'][:8]}…)")

    os.makedirs(KLADMAP, exist_ok=True)
    # Render leest GSHEETS_CREDENTIALS: de hele sleutel als één regel JSON.
    render = os.path.join(KLADMAP, "voor_render.txt")
    with open(render, "w", encoding="utf-8") as f:
        f.write(json.dumps({v: sleutel.get(v, "") for v in VELDEN}, ensure_ascii=False))
    # Streamlit Cloud wil hetzelfde TOML-blok als hierboven.
    cloud = os.path.join(KLADMAP, "voor_streamlit_cloud.toml")
    with open(cloud, "w", encoding="utf-8") as f:
        f.write(toml_blok(sleutel, spreadsheet))

    print()
    print("Klaargezet om te kopiëren:")
    print(f"  {os.path.relpath(render, REPO)}                 -> Render, "
          f"variabele GSHEETS_CREDENTIALS")
    print(f"  {os.path.relpath(cloud, REPO)}   -> Streamlit Cloud, app settings > Secrets")
    print()
    print("Gooi die map daarna weg — hij staat in .gitignore, maar hij hoort er niet")
    print("langer te staan dan nodig:")
    print(f"  Remove-Item -Recurse -Force {os.path.relpath(KLADMAP, REPO)}")


if __name__ == "__main__":
    main()
