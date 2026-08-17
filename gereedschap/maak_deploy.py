# -*- coding: utf-8 -*-
"""Bouwt de tak `nicegui-deploy`: alles wat de NiceGUI-app nodig heeft, en niets meer.

Een hostingplatform kloont de tak die je aanwijst. Staat de NT-tekst (31 MB), de
grammatica-PDF (22 MB) en de Streamlit-app er nog in, dan wacht je daar bij elke
deploy op — en op de gratis laag, die vaak herstart, merk je dat.

Deze tak wordt telkens opnieuw gemaakt vanaf de werktak; hij heeft dus geen eigen
geschiedenis om bij te houden. Draaien:

    py gereedschap/maak_deploy.py

Daarna:  git push -f origin nicegui-deploy
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WERKTAK = "nicegui-opslag"
DEPLOYTAK = "nicegui-deploy"

# Wat de app zelf opent, plus wat de schil nodig heeft. Gecontroleerd door alle
# laad_*-functies aan te roepen en te kijken welke bestanden er echt opengaan.
HOUDEN = {
    "grieks_app.py", "grieks_motor.py", "grieks_opslag.py", "grieks_gebruiker.py",
    "basis_woorden_verrijkt.json", "actief_beheersen.json", "stamtijden.json",
    "structuurwoorden.json", "verwarparen.json",
    # grammatica_tabellen.json en grammatica_index.json blijven weg: die gebruikt
    # alleen het 'rijtje spieken' bij Ontleden, en dat scherm vervalt zonder de
    # NT-tekst. Zet je die tekst er ooit bij, neem dan deze twee ook weer op.
    "requirements-nicegui.txt", "render.yaml", ".gitignore", ".python-version",
    "HOSTEN.md", "MIGRATIE.md", "OVERDRACHT.md",
}


def git(*args, **kw):
    return subprocess.run(["git", "-C", REPO, *args], check=kw.pop("check", True),
                          capture_output=True, text=True, **kw)


def bestanden_in(tak):
    return git("ls-tree", "-r", "--name-only", tak).stdout.split("\n")


def main():
    if git("status", "--porcelain").stdout.strip():
        sys.exit("Er staan nog ongecommitte wijzigingen. Commit die eerst.")
    hier = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    git("branch", "-D", DEPLOYTAK, check=False)
    git("checkout", "-q", "-b", DEPLOYTAK, WERKTAK)

    weg = [p for p in bestanden_in(DEPLOYTAK)
           if p and p.split("/")[0] not in HOUDEN and p not in HOUDEN]
    if weg:
        git("rm", "-q", "--", *weg)
        git("commit", "-q", "-m",
            "Deploytak: alleen wat de NiceGUI-app nodig heeft\n\n"
            "Automatisch gemaakt door gereedschap/maak_deploy.py vanaf "
            f"{WERKTAK}. Niet met de hand aanpassen — wijzig de werktak en draai\n"
            "het script opnieuw.\n\n"
            "Zonder de NT-tekst draait de app door; Ontleden en het opzoeken van\n"
            "vormen wijzen dan naar de Streamlit-app.")

    groot = sum(os.path.getsize(os.path.join(REPO, p))
                for p in bestanden_in(DEPLOYTAK) if p and
                os.path.exists(os.path.join(REPO, p)))
    print(f"{DEPLOYTAK}: {len(bestanden_in(DEPLOYTAK)) - 1} bestanden, "
          f"{groot / 1048576:.1f} MB ({len(weg)} weggelaten)")
    git("checkout", "-q", hier)
    print(f"Terug op {hier}. Publiceren met:  git push -f origin {DEPLOYTAK}")


if __name__ == "__main__":
    main()
