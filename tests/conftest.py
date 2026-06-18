import sys
from pathlib import Path

import pytest

# make the package importable when running pytest from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from superbox_bom.catalog import Catalog


@pytest.fixture(scope="session")
def catalog():
    return Catalog.load()
