# -*- coding: utf-8 -*-
"""Bouwt de tak `nicegui-deploy`: alles wat de NiceGUI-app nodig heeft, en niets meer.

Een hostingplatform kloont de tak die je aanwijst. Staat de NT-tekst (31 MB), de
grammatica-PDF (22 MB) en de Streamlit-app er nog in, dan wacht je daar bij elke
deploy op — en op de gratis laag, die vaak herstart, merk je dat.

Deze tak wordt telkens opnieuw gemaakt vanaf de werktak; hij heeft dus geen eigen
geschiedenis om bij te houden. Draaien:

    py gereedschap/maak_deploy.py

Daarna:  git push -f origin nicegui-deploy

Het script raakt je werkmap niet aan: er wordt niet van tak gewisseld en er wordt geen
bestand verwijderd. Alles gebeurt in een eigen index en met git-plumbing, en aan het eind
wordt alleen de tak-verwijzing verzet.

Dat is niet uit netheid. Eerst wisselde het script wél van tak, en dat gaf twee problemen
die allebei zijn voorgekomen:

  * Bleef het halverwege steken, dan stond jij op de deploytak. Je volgende commits kwamen
    daar terecht in plaats van op de werktak — en die tak gooit dit script weg.
  * Git op Windows kan de zeven Hebreeuwse PDF's niet verwijderen: hun naam bevat een
    bolletje, en dan geeft unlink 'Invalid argument'. 'git rm' liet ze dus staan, en
    daarna kon git niet meer terug naar de werktak omdat er onbeheerde bestanden in de weg
    stonden. Wat je nooit aanraakt kan ook niet blijven hangen.
"""
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WERKTAK = "nicegui-opslag"
DEPLOYTAK = "nicegui-deploy"

# Wat de app zelf opent, plus wat de schil nodig heeft. Gecontroleerd door alle
# laad_*-functies aan te roepen en te kijken welke bestanden er echt opengaan.
HOUDEN = {
    "grieks_app.py", "grieks_motor.py", "grieks_opslag.py", "grieks_gebruiker.py",
    "basis_woorden_verrijkt.json", "actief_beheersen.json", "stamtijden.json",
    "structuurwoorden.json", "verwarparen.json",
    # Hebreeuws. Zonder deze drie valt de taalknop stil weg (hebreeuws.aanwezig() geeft
    # dan False) en merk je pas op de live app dat de helft ontbreekt.
    "hebreeuws.py", "hebreeuws_woorden.json", "hebreeuws_actief.json",
    # grammatica_tabellen.json en grammatica_index.json blijven weg: die gebruikt
    # alleen het 'rijtje spieken' bij Ontleden, en dat scherm vervalt zonder de
    # NT-tekst. Zet je die tekst er ooit bij, neem dan deze twee ook weer op.
    "static",                 # de iconen voor het webmanifest
    "requirements-nicegui.txt", "render.yaml", ".gitignore", ".python-version",
    "HOSTEN.md", "MIGRATIE.md", "OVERDRACHT.md",
}

BERICHT = (
    "Deploytak: alleen wat de NiceGUI-app nodig heeft\n"
    "\n"
    f"Automatisch gemaakt door gereedschap/maak_deploy.py vanaf {WERKTAK}. Niet met de\n"
    "hand aanpassen — wijzig de werktak en draai het script opnieuw.\n"
    "\n"
    "Zonder de NT-tekst draait de app door; Ontleden en het opzoeken van vormen wijzen\n"
    "dan naar de Streamlit-app.\n")


def git(*args, index=None, invoer=None):
    """Git aanroepen. `index` zet GIT_INDEX_FILE, zodat we een eigen index gebruiken en
    die van je werkmap onaangeroerd blijft."""
    omgeving = dict(os.environ)
    if index:
        omgeving["GIT_INDEX_FILE"] = index
    # encoding expliciet op utf-8: zonder dat pakt Python op Windows de codepagina van het
    # systeem, en dan komt het bolletje in de Hebreeuwse bestandsnamen er als 'â€¢' uit —
    # drie tekens waar er één hoort, en dus een pad dat niet bestaat.
    klaar = subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=omgeving, input=invoer)
    if klaar.returncode:
        sys.exit(f"git {' '.join(args[:2])} mislukte:\n{klaar.stderr.strip()}")
    return klaar.stdout


def bestanden_in(wat, index=None):
    """De bestanden in een tak of boom, gescheiden door een nulbyte.

    Niet op regeleinden splitsen: git zet een pad met een bijzonder teken erin tussen
    aanhalingstekens en schrijft dat teken als octale escape. Met -z laat hij dat
    achterwege en komen de paden er onbewerkt uit."""
    ruw = git("ls-tree", "-r", "--name-only", "-z", wat, index=index)
    return [p for p in ruw.split("\0") if p]


def main():
    kop = git("rev-parse", WERKTAK).strip()
    alles = bestanden_in(WERKTAK)
    weg = [p for p in alles if p.split("/")[0] not in HOUDEN and p not in HOUDEN]
    houden = [p for p in alles if p not in weg]

    # Een eigen index in een tijdelijk bestand: daarin knippen we, en je werkmap merkt er
    # niets van. Er wordt geen enkel bestand van schijf gehaald.
    with tempfile.TemporaryDirectory() as tijdelijk:
        index = os.path.join(tijdelijk, "deploy.index")
        git("read-tree", kop, index=index)
        if weg:
            # --cached: alleen uit de index, niet van schijf. En via stdin, want zeven van
            # deze paden hebben een bolletje in hun naam en die wil je niet over de
            # opdrachtregel sturen.
            git("rm", "-q", "--cached", "--pathspec-from-file=-", "--pathspec-file-nul",
                index=index, invoer="\0".join(weg))
        boom = git("write-tree", index=index).strip()

    commit = git("commit-tree", boom, "-p", kop, "-m", BERICHT).strip()
    git("update-ref", f"refs/heads/{DEPLOYTAK}", commit)

    groot = 0
    for pad in bestanden_in(DEPLOYTAK):
        blob = git("rev-parse", f"{DEPLOYTAK}:{pad}").strip()
        groot += int(git("cat-file", "-s", blob).strip())
    print(f"{DEPLOYTAK}: {len(houden)} bestanden, {groot / 1048576:.1f} MB "
          f"({len(weg)} weggelaten)")
    print(f"Je werkmap is niet aangeraakt. Publiceren met:  "
          f"git push -f origin {DEPLOYTAK}")


if __name__ == "__main__":
    main()
