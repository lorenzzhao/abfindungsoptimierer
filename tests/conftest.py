from pathlib import Path

import pytest

from abfindung.io import load_legal, load_personal

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
PERSONAL = ROOT / "tests" / "fixtures" / "beispiel_persoenlich.xml"  # fictitious data
LEGAL = EXAMPLES / "gesetzliche_vorgaben_beispiel.xml"


@pytest.fixture(scope="session")
def legal():
    return load_legal(LEGAL)


@pytest.fixture()
def personal():
    return load_personal(PERSONAL)
