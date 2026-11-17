from pathlib import Path

import pytest

from abfindung import LEGAL_XML
from abfindung.io import load_legal, load_personal

ROOT = Path(__file__).resolve().parent.parent
PERSONAL = ROOT / "tests" / "fixtures" / "beispiel_persoenlich.xml"  # fictitious data
LEGAL = LEGAL_XML  # shipped with the program


@pytest.fixture(scope="session")
def legal():
    return load_legal(LEGAL)


@pytest.fixture()
def personal():
    return load_personal(PERSONAL)
