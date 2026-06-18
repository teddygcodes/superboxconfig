"""Refuse-don't-fabricate posture."""

import pytest

from superbox_bom.engine import Breaker, Spec, assemble_bom, resolve_breaker
from superbox_bom.errors import FACTORY_BANNER, FactoryAssemblyRequired


def test_750_kcmil_refused(catalog):
    b = Breaker(frame="XT5", poles=3, amps=600, int_rating="H", load_lug="750 kcmil")
    with pytest.raises(FactoryAssemblyRequired) as ei:
        resolve_breaker(b, catalog)
    assert "750" in ei.value.reason


def test_100pct_rated_refused(catalog):
    b = Breaker(frame="XT4", poles=3, amps=250, int_rating="H", rated_100pct=True)
    with pytest.raises(FactoryAssemblyRequired) as ei:
        resolve_breaker(b, catalog)
    assert "100%" in ei.value.reason


def test_unknown_combo_refused(catalog):
    b = Breaker(frame="XT4", poles=3, amps=999, int_rating="H")
    with pytest.raises(FactoryAssemblyRequired):
        resolve_breaker(b, catalog)


def test_assemble_bom_returns_refused_status_for_750(catalog):
    spec = Spec(
        panel_amps=1200, main_type="MLO", enclosure="NEMA1",
        branches=[Breaker(frame="XT5", poles=3, amps=600, int_rating="H", load_lug="750 kcmil")],
    )
    result = assemble_bom(spec, catalog)
    assert result["status"] == "refused"
    assert "750" in result["reason"]
    assert any(FACTORY_BANNER in f for f in result["validation"]["flags"])


def test_exceeds_largest_superbox_refused(catalog):
    # Way too many large left-only XT6 breakers for any 1200A box.
    spec = Spec(
        panel_amps=1200, main_type="MLO", enclosure="NEMA1",
        branches=[Breaker(frame="XT6", poles=3, amps=800, int_rating="H",
                          trip_unit="TMA", qty=12)],
    )
    result = assemble_bom(spec, catalog)
    assert result["status"] == "refused"
