"""Every result has a plain-language meaning (shown above the calculation steps)."""

from pathlib import Path

import pytest

from abfindung import explain
from abfindung.engine.scenario import run
from abfindung.engine.settings import add_gestaltung, from_personal
from abfindung.io import load_personal
from abfindung.meaning import meaning

FIXTURES = Path(__file__).parent / "fixtures"
DERIVED = ("kfrist_monate", "kv_status", "sperrzeit_wochen", "arbeitsuchend_datum", "kv_beitrag_schaetzung",
           "alg_monat", "fuenftel_ok")


@pytest.mark.parametrize("name", ["beispiel_persoenlich.xml", "fiktiv_paar.xml"])
@pytest.mark.parametrize("variant", ["joint", "single_derived"])
def test_every_result_has_a_meaning(legal, name, variant):
    s = from_personal(load_personal(FIXTURES / name), legal)
    if variant == "single_derived":
        for y in s.years():
            s.veranlagung[y] = "einzel"
        for f in DERIVED:
            s.set_origin(f"persons.0.{f}", "abgeleitet")
        for typ in ("basisrente", "erhaltung", "spende", "sonstige"):
            add_gestaltung(s, typ, 2027, betrag=2000)
        add_gestaltung(s, "kauf", 2027, kaufpreis=200_000, darlehen=150_000, miete_jahr=8000)
        s.persons[1].alg_aktiv = False
    r = run(s, legal)
    missing = sorted(k for k in r.rs if not meaning(k))
    assert not missing


def test_meaning_comes_first_in_the_explanation(legal, personal):
    s = from_personal(personal, legal)
    r = run(s, legal, extras=False)
    e = explain.build(r.rs["saldo"], legal, r.rs)
    html = explain.to_html(e, {"accent": "#000", "muted": "#777", "warn_bg": "#ff0", "warn_fg": "#a00", "border": "#ccc",
                               "text": "#000", "code_bg": "#eee", "link": "#00f"})
    assert e.meaning.startswith("Die Zielgröße")
    assert html.index("Was bedeutet dieser Wert?") < html.index("Rechenweg")
