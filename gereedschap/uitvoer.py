# -*- coding: utf-8 -*-
"""Zorgt dat Grieks en Hebreeuws in de uitvoer niet omvallen op Windows.

Naar het scherm gaat het goed: Python schrijft daar rechtstreeks Unicode naartoe. Maar
zodra de uitvoer ergens ánders naartoe gaat — een bestand, een pijp, een taak in de
Taakplanner die het weglogt — pakt Python de codepagina van het systeem. Dat is hier
cp1252, en daarin bestaat geen enkele Griekse of Hebreeuwse letter. Het gevolg is geen
lelijke tekst maar een harde fout:

    UnicodeEncodeError: 'charmap' codec can't encode characters in position 7-15

Dat trof precies het geval waar je het niet wil: een reservekopie die je automatisch laat
draaien schrijft zijn uitvoer naar een logbestand, en zou dus omvallen.

Elk script in deze map roept zet_utf8() aan, vóór de eerste print.
"""
import sys


def zet_utf8():
    """De eigen uitvoer op UTF-8 zetten. Raakt de codepagina van het venster niet aan."""
    for stroom in (sys.stdout, sys.stderr):
        # reconfigure bestaat vanaf Python 3.7; ontbreekt hij, dan is er niets te doen.
        if hasattr(stroom, "reconfigure"):
            try:
                stroom.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass          # al vastgezet of geen echte stroom; dan laten we het zo
