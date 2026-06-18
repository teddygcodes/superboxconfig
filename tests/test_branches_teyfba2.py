"""TEY / FB / A2 branch resolution (1- and 2-pole, phase-specific)."""

import pytest

from superbox_bom.engine import Breaker, resolve_breaker
from superbox_bom.errors import FactoryAssemblyRequired


@pytest.mark.parametrize("frame,poles,amps,rating,phase,code", [
    ("TEY", 1, 20, "D", "A", "TEYADED0AAXXXXXX"),
    ("TEY", 1, 20, "L", "C", "TEYALED0CAXXXXXX"),
    ("TEY", 2, 40, "D", "BC", "TEYADFHBCBXXXXXX"),
    ("TEY", 2, 125, "D", "AC", "TEYADFSACDXXXXXX"),
    ("FB", 1, 20, "V", "A", "NEFBV16TE020R2A"),
    ("FB", 1, 20, "H", "C", "NEFBH16TE020R2C"),
    ("FB", 2, 100, "V", "BC", "NEFBV26TE100R2BC"),
    ("A2", 2, 125, "A", "AB", "A2A2125ABDXXXX"),
    ("A2", 2, 200, "N", "AC", "A2N2200ACDXXXX"),
    ("A2", 2, 250, "N", "AB", "A2N2250ABDXXXX"),
])
def test_resolve_phase_specific(catalog, frame, poles, amps, rating, phase, code):
    b = Breaker(frame=frame, poles=poles, amps=amps, int_rating=rating, phase=phase)
    assert resolve_breaker(b, catalog)["ordering_code"] == code


def test_phase_required_to_disambiguate(catalog):
    # without phase, the three phase variants are ambiguous
    from superbox_bom.errors import CatalogError
    b = Breaker(frame="TEY", poles=1, amps=20, int_rating="D")
    with pytest.raises(CatalogError):
        resolve_breaker(b, catalog)


def test_a2_250_has_no_al_lug(catalog):
    b = Breaker(frame="A2", poles=2, amps=250, int_rating="N", phase="AB")
    row = resolve_breaker(b, catalog)
    assert row["al_load_lug"] is None
    assert row["load_lug"] == "1-250"


def test_unknown_phase_refused(catalog):
    # FB only comes in 20A (1P); a bogus amp -> factory-assembled
    b = Breaker(frame="FB", poles=1, amps=50, int_rating="N", phase="A")
    with pytest.raises(FactoryAssemblyRequired):
        resolve_breaker(b, catalog)
