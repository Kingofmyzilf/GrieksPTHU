# -*- coding: utf-8 -*-
"""Gebruikerssessie: inloggen, voortgang inlezen en opslaan.

Zit tussen grieks_opslag.py (de Sheet) en de schil (grieks_app.py) in, en houdt zich
aan dezelfde afspraken als overhoring_web.py:
  * de gebruikersnaam is 'naam_code' — die combinatie is je sleutel;
  * scores worden op de woordenlijst gezet met dezelfde velden;
  * opslaan gaat gebatcht (om de vijf beurten), niet bij elke klik.
"""
import threading
from datetime import datetime

import grieks_motor as motor
import grieks_opslag as opslag

OPSLAG_INTERVAL = 5          # zelfde ritme als trigger_save() in de Streamlit-app
STAT_SLEUTELS = [s for s, _ in opslag.SPECS]


def vandaag():
    return datetime.now().strftime("%Y-%m-%d")


class Gebruiker:
    """Alles wat één ingelogde student in het geheugen heeft."""

    def __init__(self, naam, code):
        self.naam = str(naam).strip()
        self.code = str(code).strip()
        self.sleutel = f"{self.naam}_{self.code}"
        self.woorden = []
        self.stats = {s: {} for s in STAT_SLEUTELS}
        self.sinds_opslag = 0
        self.laatste_fout = None
        self._slot = threading.Lock()

    # ---------------------------------------------------------------- laden
    def laad(self):
        """Woordenlijst inlezen en de opgeslagen scores erop zetten."""
        self.woorden = motor.laad_vocab_db()
        if not self.woorden:
            raise opslag.OpslagFout("De woordenlijst kon niet worden geladen.")
        self.stats = opslag.laad(self.sleutel)
        self._pas_scores_toe()
        return self

    def _pas_scores_toe(self):
        """Zelfde toewijzing als laad_gebruiker_data() in overhoring_web.py,
        inclusief de oude m1..m4-telling van vóór het streak-systeem."""
        vocab = self.stats.get("vocab_stats") or {}
        for r in self.woorden:
            s = vocab.get(r["grieks"], {})
            if "m4" in s or "m1" in s:
                r["streak"] = s.get("m2", 0) * 1 + s.get("m3", 0) * 2 + s.get("m4", 0) * 4
            else:
                r["streak"] = s.get("streak", 0)
            r["score_goed"] = s.get("g", 0)
            r["score_fout"] = s.get("f", 0)
            r["laatst_geoefend"] = s.get("laatst_geoefend", "")
            r["laatst_fout"] = s.get("lf", "")
            if not r.get("lexeem_info"):
                r["lexeem_info"] = r.get("grieks_info", "")

    # ---------------------------------------------------------------- scoren
    def noteer(self, woord, goed):
        """Eén beurt verwerken. Geeft terug of er is opgeslagen."""
        vandaag_str = vandaag()
        if goed:
            woord["streak"] = int(woord.get("streak", 0)) + 1
            woord["score_goed"] = int(woord.get("score_goed", 0)) + 1
        else:
            woord["streak"] = 0
            woord["score_fout"] = int(woord.get("score_fout", 0)) + 1
            woord["laatst_fout"] = vandaag_str
        woord["laatst_geoefend"] = vandaag_str
        dag = self.stats.setdefault("dag_stats", {})
        dag[vandaag_str] = int(dag.get(vandaag_str, 0)) + 1
        self.sinds_opslag += 1
        if self.sinds_opslag >= OPSLAG_INTERVAL:
            return self.bewaar()
        return False

    # ---------------------------------------------------------------- opslaan
    def _verzamel_vocab(self):
        """Woordenlijst terug naar het compacte opslagformaat. Woorden waar nog
        niets mee gebeurd is blijven weg, net als in de Streamlit-app."""
        uit = {}
        for w in self.woorden:
            s = int(w.get("streak", 0)); g = int(w.get("score_goed", 0))
            f = int(w.get("score_fout", 0)); l = w.get("laatst_geoefend", "")
            if s or g or f or l:
                e = {"streak": s, "g": g, "f": f}
                if l:
                    e["laatst_geoefend"] = l
                if w.get("laatst_fout"):
                    e["lf"] = w["laatst_fout"]
                uit[w["grieks"]] = e
        return uit

    def bewaar(self, forceer=False):
        """Wegschrijven naar de Sheet. Bij een fout blijft alles in het geheugen staan
        en wordt het bij de volgende poging opnieuw geprobeerd."""
        if not forceer and self.sinds_opslag == 0:
            return False
        with self._slot:
            self.stats["vocab_stats"] = self._verzamel_vocab()
            try:
                opslag.bewaar(self.sleutel, self.stats)
                self.sinds_opslag = 0
                self.laatste_fout = None
                return True
            except opslag.OpslagFout as e:
                self.laatste_fout = str(e)
                return False

    # ---------------------------------------------------------------- overzicht
    def samenvatting(self):
        v = self.stats.get("vocab_stats") or {}
        goed = sum(int(e.get("g", 0)) for e in v.values())
        fout = sum(int(e.get("f", 0)) for e in v.values())
        return {
            "geoefend": len(v),
            "beheerst": sum(1 for e in v.values() if int(e.get("streak", 0)) >= 16),
            "goed": goed,
            "fout": fout,
            "accuratesse": round(100 * goed / (goed + fout)) if goed + fout else 0,
            "dagen": len(self.stats.get("dag_stats") or {}),
            "vandaag": int((self.stats.get("dag_stats") or {}).get(vandaag(), 0)),
        }


def fase_van(streak):
    """Dezelfde vier fasen als de Streamlit-app."""
    s = int(streak or 0)
    if s == 0:
        return "Nieuw"
    if s <= 15:
        return "In training"
    if s <= 29:
        return "Beheerst"
    return "Mastery"


def woord_opbouw(lemma, woordenlijst):
    """Voorzetsel-voorvoegsel + grondwoord, maar alleen als dat grondwoord zélf ook in
    de lijst staat (bv. εἰσέρχομαι = εἰς + ἔρχομαι). Zo verzint de app geen etymologie.

    Zelfde logica als woord_opbouw() in overhoring_web.py; die kon niet mee naar de
    motor omdat hij de woordenlijst uit st.session_state haalde. Hier is het een
    gewone parameter.
    """
    lk = motor._opb_kaal(lemma)
    if len(lk) < 5:
        return None
    idx = {}
    for w in woordenlijst:
        g = str(w.get("grieks", "") or "")
        if g:
            idx.setdefault(motor._opb_kaal(g), g)
    for p in sorted(motor._VOORZETSEL_INFO, key=len, reverse=True):
        if not lk.startswith(p) or len(lk) - len(p) < 3:
            continue
        grond = idx.get(lk[len(p):])
        if grond and motor._opb_kaal(grond) != lk:
            weer, bet = motor._VOORZETSEL_INFO[p]
            return {"voorzetsel": weer, "betekenis": bet, "grondwoord": grond}
    return None


def inloggen(naam, code):
    """Geeft een geladen Gebruiker, of werpt OpslagFout met een leesbare melding."""
    if not str(naam).strip() or not str(code).strip():
        raise opslag.OpslagFout("Vul allebei de velden in.")
    return Gebruiker(naam, code).laad()
