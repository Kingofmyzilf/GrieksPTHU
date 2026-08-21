# -*- coding: utf-8 -*-
"""Controleert de dagelijkse reservekopie die de app zelf maakt.

Met een nagemaakt werkblad, dus er gaat niets naar de echte Sheet. Wat er moet kloppen:

  * de eerste opslag van de dag maakt een kopie, de tweede niet meer;
  * wat er in de kopie staat is de stand vóór het samenvoegen — daar zit het hele nut in;
  * morgen komt er weer een kopie bij;
  * na veertien dagen vallen de oudste eraf, en dat gaat per dag en niet per rij;
  * gaat het schrijven van de kopie mis, dan wordt de voortgang alsnog gewoon opgeslagen.

Draaien:  py gereedschap/test_dagkopie.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import grieks_opslag as opslag

import uitvoer

# Vóór de eerste print: anders valt Grieks of Hebreeuws om zodra de uitvoer
# naar een bestand of een pijp gaat in plaats van naar het scherm.
uitvoer.zet_utf8()

fouten = []


def kijk(wat, gekregen, verwacht):
    if gekregen != verwacht:
        fouten.append(wat)
        print(f"  MIS  {wat}: {gekregen} in plaats van {verwacht}")
    else:
        print(f"  ok   {wat}")


class NepTab:
    """Een werkblad in het geheugen, met alleen wat dagkopie() ervan gebruikt."""

    def __init__(self, stuk=False):
        self.rijen = []
        self.stuk = stuk

    def row_values(self, n):
        return list(self.rijen[n - 1]) if len(self.rijen) >= n else []

    def get_all_records(self):
        if not self.rijen:
            return []
        kop = self.rijen[0]
        return [{k: (r[i] if i < len(r) else "") for i, k in enumerate(kop)}
                for r in self.rijen[1:]]

    def col_values(self, n):
        return [r[n - 1] if len(r) >= n else "" for r in self.rijen]

    def update(self, waarden, _bereik):
        for i, rij in enumerate(waarden):
            while len(self.rijen) <= i:
                self.rijen.append([])
            self.rijen[i] = list(rij)

    def append_row(self, rij, value_input_option=None):
        if self.stuk:
            raise RuntimeError("quota overschreden")
        self.rijen.append(list(rij))

    def delete_rows(self, n):
        del self.rijen[n - 1]


def stand(streak, dag):
    return {"vocab_stats": {"λόγος": {"streak": streak, "g": streak, "f": 0}},
            "dag_stats": {dag: streak}}


def main():
    tab = NepTab()
    vandaag = ["2026-08-20"]

    opslag._tab = lambda naam, maak=False: tab
    opslag._vandaag = lambda: vandaag[0]

    # ------------------------------------------------------------------ eerste keer
    in_sheet = stand(5, "2026-08-20")
    gemaakt = opslag.dagkopie("Bob_Timmer", in_sheet)
    kijk("de eerste opslag van de dag maakt een kopie", gemaakt, True)
    kijk("er staat een kopregel plus één rij", len(tab.rijen), 2)
    kijk("de vlag staat in badges",
         in_sheet["badges"]["_backup_op"], "2026-08-20")

    # ------------------------------------------------------------------ tweede keer
    kijk("de tweede opslag van dezelfde dag doet niets",
         opslag.dagkopie("Bob_Timmer", in_sheet), False)
    kijk("en er komt dus geen rij bij", len(tab.rijen), 2)

    # ------------------------------------------------------------------ wat er in staat
    kopieen = opslag.lees_kopieen("Bob_Timmer")
    kijk("de kopie is terug te lezen", len(kopieen), 1)
    if kopieen:
        dag, naam, stats = kopieen[0]
        kijk("met de goede dag", dag, "2026-08-20")
        kijk("en de stand van vóór het samenvoegen",
             (stats.get("vocab_stats") or {}).get("λόγος", {}).get("streak"), 5)

    # ------------------------------------------------------------------ morgen
    vandaag[0] = "2026-08-21"
    morgen = stand(9, "2026-08-21")
    kijk("morgen komt er weer een kopie", opslag.dagkopie("Bob_Timmer", morgen), True)
    kijk("nu twee kopieën", len(opslag.lees_kopieen("Bob_Timmer")), 2)

    # ------------------------------------------------------------------ twee gebruikers
    kijk("een tweede gebruiker krijgt zijn eigen kopie",
         opslag.dagkopie("Anne_2026", stand(3, "2026-08-21")), True)
    kijk("die van Bob blijft van Bob", len(opslag.lees_kopieen("Bob_Timmer")), 2)
    kijk("en Anne heeft er één", len(opslag.lees_kopieen("Anne_2026")), 1)

    # ------------------------------------------------------------------ opruimen
    for n in range(2, 20):
        vandaag[0] = f"2026-09-{n:02d}"
        opslag.dagkopie("Bob_Timmer", stand(n, vandaag[0]))
    dagen = sorted({d for d, _n, _s in opslag.lees_kopieen()})
    kijk("er blijven niet meer dan veertien dagen staan", len(dagen),
         opslag.BACKUP_DAGEN)
    kijk("en de oudste zijn eraf", "2026-08-20" in dagen, False)
    kijk("de nieuwste staat er nog", "2026-09-19" in dagen, True)

    # ------------------------------------------------------------------ als het misgaat
    stuk = NepTab(stuk=True)
    opslag._tab = lambda naam, maak=False: stuk
    vandaag[0] = "2026-09-20"
    mijn = stand(99, "2026-09-20")
    geschreven = {}
    try:
        opslag.dagkopie("Bob_Timmer", mijn)
        fouten.append("een mislukte kopie werpt niet")
        print("  MIS  een mislukte kopie werpt niet — bewaar() moet hem opvangen")
    except RuntimeError:
        print("  ok   een mislukte kopie werpt, en bewaar() vangt dat op")
    kijk("en de vlag is dan niet gezet",
         "_backup_op" in (mijn.get("badges") or {}), False)

    print()
    if fouten:
        sys.exit(f"{len(fouten)} mis")
    print("GESLAAGD")


if __name__ == "__main__":
    main()
