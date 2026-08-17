# -*- coding: utf-8 -*-
"""Vergelijkt grieks_motor.py met het origineel: dezelfde invoer moet dezelfde uitvoer geven."""
import io, sys, os, json, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 1. de motor moet zónder streamlit importeerbaar zijn
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIER = os.path.dirname(os.path.abspath(__file__))
os.chdir(REPO)
sys.path.insert(0, REPO)
_echte_st = sys.modules.pop("streamlit", None)
import grieks_motor as motor
print("motor geïmporteerd zonder streamlit:", "streamlit" not in sys.modules)

# 2. het origineel via het nep-Streamlit-harnas
os.chdir(HIER)
exec(open("test_app.py", encoding="utf-8").read())     # levert module `m`
os.chdir(REPO)

# 3. vergelijken
gelijk = verschil = overgeslagen = 0
fouten = []
namen = [n for n in dir(motor) if not n.startswith("__") and callable(getattr(motor, n, None))]

bijbel = motor.laad_bijbel_db()
vocab = motor.laad_vocab_db()
random.seed(7)
steek = random.sample(vocab, 60) if len(vocab) > 60 else vocab

# 3a. constanten moeten identiek zijn
for c in ["_ONTLEED_KLEUR", "_NAAM3_UITG", "LEERPAD_DREMPEL", "_AUG_TEMPOREEL", "_CORPUS_UITG"]:
    if hasattr(motor, c) and hasattr(m, c):
        if getattr(motor, c) == getattr(m, c):
            gelijk += 1
        else:
            verschil += 1; fouten.append(f"constante {c} wijkt af")

# 3b. woordfuncties op 60 echte woorden
ENKEL = ["normaliseer_accent", "_opb_kaal", "_opb_norm", "check_betekenis", "betekenis_exact"]
for w in steek:
    g = w.get("grieks", "")
    for fn in ENKEL:
        f1, f2 = getattr(motor, fn, None), getattr(m, fn, None)
        if not (f1 and f2):
            continue
        try:
            a = f1(g) if fn not in ("check_betekenis", "betekenis_exact") else f1(g, w.get("nederlands", ""))
            b = f2(g) if fn not in ("check_betekenis", "betekenis_exact") else f2(g, w.get("nederlands", ""))
        except TypeError:
            overgeslagen += 1; continue
        except Exception as e:
            verschil += 1; fouten.append(f"{fn}({g!r}) wierp {e!r}"); continue
        if a == b: gelijk += 1
        else: verschil += 1; fouten.append(f"{fn}({g!r}): {a!r} != {b!r}")

# 3c. de zware ontleedfuncties op echte bijbelvormen
random.seed(11)
alle = [w for vs in bijbel.values() for w in vs]
vormen = random.sample(alle, 250)
for v in vormen:
    vorm = v.get("grieks") or v.get("woord") or ""
    lem = v.get("lemma") or v.get("strong", "")
    pars = v.get("parsing_info", "") or v.get("parsing", "")
    for fn in ["ontleed_segmenten", "samensmeltingen_alle", "_splits_werkwoord", "_splits_naamwoord"]:
        f1, f2 = getattr(motor, fn, None), getattr(m, fn, None)
        if not (f1 and f2):
            continue
        for args in ((vorm, lem, pars), (vorm, lem), (vorm,)):
            try:
                a, b = f1(*args), f2(*args)
            except TypeError:
                continue
            except Exception as e:
                verschil += 1; fouten.append(f"{fn}{args!r} wierp {e!r}"); break
            if a == b: gelijk += 1
            else: verschil += 1; fouten.append(f"{fn}({vorm!r}): uitvoer wijkt af")
            break

# 3d. cache-gedrag
c1 = motor.voortgang_kernstats if hasattr(motor, "voortgang_kernstats") else None
print(f"cache heeft .clear(): {hasattr(motor.laad_vocab_db, 'clear')}")
print(f"cache_resource deelt object: {motor.laad_bijbel_db() is motor.laad_bijbel_db()}")
_a, _b = motor.laad_vocab_db(), motor.laad_vocab_db()
print(f"cache_data geeft kopie: {_a is not _b and _a == _b}")

print()
print(f"gelijk: {gelijk} · verschillend: {verschil} · overgeslagen: {overgeslagen}")
for f in fouten[:12]:
    print("   FOUT:", f)
print("GESLAAGD" if verschil == 0 else "ER ZIJN VERSCHILLEN")
