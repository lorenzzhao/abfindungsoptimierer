"""Payment months and registration dates of the former XML variants/scenarios of the test data sets
(tests/fixtures/beispiel_persoenlich.xml: P_Erika/P_Max; tests/fixtures/fiktiv_paar.xml: P1/P2).
The tool no longer has variants; the tests set the values directly."""

from datetime import date

from abfindung.dates import month_index

VARIANTS = {
    "A": {"P1": (2027, 8), "P2": (2027, 5), "P_Erika": (2027, 1), "P_Max": (2027, 1)},
    "B": {"P_Erika": (2026, 12), "P_Max": (2027, 1)},
    "E": {"P1": (2027, 8), "P2": (2028, 1)},
    "F": {"P1": (2028, 1), "P2": (2027, 5)},
}
SCENARIOS = {
    "S1": {"P1": date(2027, 9, 1), "P2": date(2027, 6, 1), "P_Erika": date(2027, 1, 1), "P_Max": date(2027, 3, 1)},
    "S2": {"P1": date(2028, 9, 2), "P2": date(2028, 6, 2), "P_Erika": date(2028, 1, 2), "P_Max": date(2028, 3, 2)},
}


def apply_variant(s, vid: str) -> None:
    for i, ps in enumerate(s.persons):
        if ps.id in VARIANTS[vid]:
            s.set(f"persons.{i}.pay_idx", month_index(*VARIANTS[vid][ps.id]))


def apply_scenario(s, sid: str) -> None:
    for i, ps in enumerate(s.persons):
        if ps.id in SCENARIOS[sid]:
            s.set(f"persons.{i}.meldung", SCENARIOS[sid][ps.id])


def set_basisrente(s, amounts: dict) -> None:
    """Basisrente per year as planned entries (replaces the former dict measures.basisrente)."""
    from abfindung.engine.settings import set_basisrente_year

    for y, v in amounts.items():
        set_basisrente_year(s, y, v)


def basisrente_by_year(s) -> dict:
    from abfindung.engine.settings import gestaltungen

    out = {}
    for _, g in gestaltungen(s, "basisrente"):
        out[g.jahr] = out.get(g.jahr, 0.0) + g.betrag
    return out
