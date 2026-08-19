# -*- coding: utf-8 -*-
"""Kan het verversen voortgang kwijtmaken? Naspelen met een geval dat echt voorkwam.

De Streamlit-app had een stand van 3 juli in het geheugen terwijl de Sheet allang bij was:
hij las de voortgang maar één keer, bij het inloggen, en daarna nooit meer. Nu haalt hij
hem opnieuw op als het scherm lang openstaat. De vraag die deze proef beantwoordt is of
dat veilig is — welke kant ook voorloopt.

Draaien:  py gereedschap/test_verversen.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from grieks_opslag import samenvoeg_stats

fouten = []


def kijk(wat, gekregen, verwacht):
    if gekregen != verwacht:
        fouten.append(f"{wat}: {gekregen} in plaats van {verwacht}")
        print(f"  MIS  {wat}: {gekregen} in plaats van {verwacht}")
    else:
        print(f"  ok   {wat}")


# ---------------------------------------------------------------- het geval van vandaag
# In de Sheet staat wat de telefoon vanmiddag opsloeg; in Streamlit staat 3 juli.
sheet = {"vocab_stats": {"πειρασμός": {"streak": 24, "g": 20, "f": 6,
                                       "laatst_geoefend": "2026-08-19"},
                         "πῶς": {"streak": 10, "g": 8, "f": 2,
                                 "laatst_geoefend": "2026-08-13"}},
         "dag_stats": {"2026-08-19": 42}}
streamlit_oud = {"vocab_stats": {"πειρασμός": {"streak": 17, "g": 17, "f": 5,
                                               "laatst_geoefend": "2026-07-03"},
                                 "πῶς": {"streak": 2, "g": 4, "f": 1,
                                         "laatst_geoefend": "2026-07-14"}},
                 "dag_stats": {"2026-07-03": 12}}

samen = samenvoeg_stats(sheet, streamlit_oud)
print("de oude Streamlit-stand samenvoegen met de Sheet:")
kijk("πειρασμός houdt de nieuwe streak", samen["vocab_stats"]["πειρασμός"]["streak"], 24)
kijk("πειρασμός houdt de nieuwe datum",
     samen["vocab_stats"]["πειρασμός"]["laatst_geoefend"], "2026-08-19")
kijk("πῶς houdt de nieuwe streak", samen["vocab_stats"]["πῶς"]["streak"], 10)
kijk("de dag van vandaag blijft staan", samen["dag_stats"].get("2026-08-19"), 42)
kijk("de oude dag blijft óók staan", samen["dag_stats"].get("2026-07-03"), 12)

# ---------------------------------------------------------------- en andersom
# Je oefent net in Streamlit; de Sheet is dan de oudere kant. Dat mag niet weggegooid.
print()
print("en andersom — je zit net te oefenen in Streamlit:")
streamlit_nieuw = {"vocab_stats": {"πειρασμός": {"streak": 27, "g": 22, "f": 6,
                                                 "laatst_geoefend": "2026-08-19"}},
                   "dag_stats": {"2026-08-19": 45}}
samen2 = samenvoeg_stats(sheet, streamlit_nieuw)
kijk("wat je net deed blijft staan", samen2["vocab_stats"]["πειρασμός"]["streak"], 27)
kijk("het woord dat alleen in de Sheet stond blijft er",
     samen2["vocab_stats"]["πῶς"]["streak"], 10)
kijk("de dagteller neemt het hoogste", samen2["dag_stats"]["2026-08-19"], 45)

# ---------------------------------------------------------------- gelijkspel
print()
print("gelijkspel — evenveel pogingen aan allebei de kanten:")
samen3 = samenvoeg_stats(
    {"vocab_stats": {"λόγος": {"streak": 5, "g": 3, "f": 1}}},
    {"vocab_stats": {"λόγος": {"streak": 6, "g": 3, "f": 1}}})
kijk("bij gelijkspel wint de eigen versie", samen3["vocab_stats"]["λόγος"]["streak"], 6)

print()
if fouten:
    sys.exit(f"{len(fouten)} mis")
print("GESLAAGD: verversen kan niets kwijtmaken, welke kant ook voorloopt")
