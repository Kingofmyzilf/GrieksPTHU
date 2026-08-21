# -*- coding: utf-8 -*-
"""Maakt een htmlbestand om de overgetypte slides na te kijken.

Om met eigen ogen te vergelijken met de pdf. De opmaak hier is dezelfde als die de app
gebruikt, dus wat je hier ziet is wat je in de app krijgt.

Draaien:  py gereedschap/proef_slides.py [van] [tot]
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

import uitvoer

uitvoer.zet_utf8()

BRON = os.path.join(REPO, "grammatica_slides.json")
UIT = os.path.join(REPO, "slides_werk", "proef.html")

# Deze opmaak hoort bij de app. De klassen heten naar de kleur en niet naar de rol, want
# die rol wisselt: op slide 9 zijn de sublabels groen en op slide 200 blauw. Kleur
# vastleggen als kleur is eerlijker dan er betekenis in lezen die de slides zelf niet
# volhouden.
#
#   oranje   het kernbegrip van de slide
#   blauw    een letter, label of term om te onthouden
#   groen    voorbeelden en Griekse citaten
#   grieks   Grieks schrift; alleen het lettertype, geen kleur, dus te combineren
#   grijs    vormen die je niet hoeft te leren; slide 63 en 65 zeggen dat er letterlijk
#            bij ("het meervoud (in grijs) hoeft daarom niet geleerd te worden"), dus is
#            dit grijs betekenis en geen opsmuk
OPMAAK = """
:root { --inkt:#0e1117; --vlak:#161a22; --rand:#2b3038; --tekst:#e8eaed;
        --zacht:#9aa4ae; --oranje:#ff9d3c; --blauw:#4bb6e8; --groen:#8bbf6a;
        --rood:#ff7d7d; --paars:#c8a2ff;
        --kop:#f0f2f4; --tabelkop:#2e7d95; --tabelvlak:#1d232c; }
body { background:var(--inkt); color:var(--tekst); margin:0; padding:20px;
       font-family:'Gentium Book Plus','Palatino Linotype',Georgia,serif;
       font-size:17px; line-height:1.55; }
/* Een tabel van vijf kolommen (slide 77) past niet op een telefoon. Dan schuift de
   slide zelf, niet de hele pagina. */
.slide { max-width:820px; margin:0 auto 26px; background:var(--vlak);
         border:1px solid var(--rand); border-radius:12px; padding:20px 24px;
         overflow-x:auto; }
.slide h2 { color:var(--kop); font-size:19px; margin:0 0 12px; }
.slidenr { float:right; color:var(--zacht); font-size:13px; font-family:system-ui,sans-serif; }
.oranje { color:var(--oranje); font-weight:700; }
.blauw  { color:var(--blauw); font-weight:700; }
.groen  { color:var(--groen); }
.rood   { color:var(--rood); }
.paars  { color:var(--paars); }
.grijs  { color:var(--zacht); }
.grieks { font-family:'Gentium Book Plus','Palatino Linotype',Georgia,serif; }
.kopje  { font-size:18px; margin-bottom:2px; }
.groot  { font-size:23px; }
.teken  { font-size:21px; text-align:center; width:2.2em; }
.vb     { color:var(--groen); margin:2px 0 6px 18px; }
.auteur { color:var(--zacht); text-align:center; margin-top:18px; }
/* Kolombreedte in plaats van een vast aantal, want op een telefoon passen er geen drie
   naast elkaar. */
.inhoud { columns:220px; column-gap:26px; list-style:none; padding:0; font-size:15px; }
.inhoud li { break-inside:avoid; margin-bottom:3px; color:var(--zacht); }
table.par { border-collapse:collapse; width:100%; margin:10px 0; font-size:16px; }
table.par th { background:var(--tabelkop); color:#fff; text-align:left; font-weight:400;
               padding:7px 10px; vertical-align:bottom; }
table.par td { background:var(--tabelvlak); border-top:1px solid var(--rand);
               padding:6px 10px; }
table.par.licht th { background:#2f6f82; }
table.par.licht tbody th { background:#24596a; font-size:15px; }
table.par.kaal th, table.par.kaal td { background:none; border:none; padding:3px 12px 3px 0; }
/* De groene uitgangentabellen (vanaf slide 77). De slides gebruiken blauw voor de
   naamwoorden en groen voor de werkwoordsuitgangen; dat onderscheid is het waard om te
   houden, want je ziet aan de kleur al waar je naar kijkt. */
/* Slides 81, 85 en 88: blauwe kop met groene rijlabels. De kop zegt waar de kolom over
   gaat, de groene rand links zegt dat het om werkwoordsvormen gaat. */
table.par.licht.groenrij tbody th { background:#5d8c3c; }
table.par.groen th { background:#5d8c3c; }
table.par.groen tbody th { background:#456a2c; font-size:15px; }
table.par.groen td { background:#262c20; }
.kader { background:var(--tabelvlak); border:1px solid var(--rand); border-radius:8px;
         padding:12px 16px; margin:10px 0; }
/* De beige kadertjes links op de slide: verwijzingen naar het handboek en zijsprongen.
   Naast de tekst als het past, en anders er gewoon boven — op een telefoon is een kolom
   ernaast onleesbaar. */
.kader.zijnoot { float:right; max-width:210px; margin:0 0 10px 16px; font-size:14px;
                 color:var(--zacht); }
/* Het groene vlak (slide 237): een geheugensteuntje op rijm. Het staat er niet groen voor
   de sier -- het is de enige plek waar de slides een kadertje kleuren, dus dat blijft. */
.kader.groenvlak { background:#31462a; border-color:#4a6b3d; }
@media (max-width:640px) { .kader.zijnoot { float:none; max-width:none; } }
ol, ul { padding-left:22px; }
li { margin-bottom:5px; }
a { color:var(--blauw); }
"""


def main():
    van = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    tot = int(sys.argv[2]) if len(sys.argv) > 2 else 10 ** 6
    with open(BRON, encoding="utf-8") as f:
        slides = [s for s in json.load(f) if van <= s["nr"] <= tot]
    stukken = [f"<style>{OPMAAK}</style>",
               f"<p style='max-width:820px;margin:0 auto 20px;color:#9aa4ae;"
               f"font-family:system-ui'>{len(slides)} slides overgetypt uit "
               f"grammatica_overzicht.pdf. Vergelijk met de pdf; wat hier staat is wat de "
               f"app laat zien.</p>"]
    for s in slides:
        stukken.append(
            f"<div class='slide'><span class='slidenr'>slide {s['nr']}</span>"
            f"<h2>{s.get('kop', '')}</h2>{s.get('html', '')}</div>")
    os.makedirs(os.path.dirname(UIT), exist_ok=True)
    with open(UIT, "w", encoding="utf-8") as f:
        f.write("<!doctype html><meta charset='utf-8'>"
                "<title>Grammatica-slides, proef</title>"
                "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                + "".join(stukken))
    print(f"{UIT}: {len(slides)} slides, {os.path.getsize(UIT)/1024:.0f} kB")


if __name__ == "__main__":
    main()
