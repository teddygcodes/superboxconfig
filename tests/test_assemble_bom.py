"""End-to-end happy path + ambiguity."""

from superbox_bom.engine import Breaker, Spec, assemble_bom


def _mlo_1200_spec():
    return Spec(
        panel_amps=1200, main_type="MLO", enclosure="NEMA1",
        branches=[
            Breaker(frame="XT4", poles=3, amps=250, int_rating="H", trip_unit="TMF", qty=2),
            Breaker(frame="XT1", poles=3, amps=100, int_rating="N", qty=7),
        ],
    )


def test_happy_path_ok(catalog):
    result = assemble_bom(_mlo_1200_spec(), catalog)
    assert result["status"] == "ok"
    assert result["validation"]["selected_superbox"] == "RNSB12L8445A"


def test_xt1_grouping_in_validation(catalog):
    v = assemble_bom(_mlo_1200_spec(), catalog)["validation"]
    assert v["xt1_grouping"]["groups"] == [5, 2]
    assert v["xt1_grouping"]["rails"] == ["SR5XBF", "SR2XBF"]


def test_bom_contains_superbox_and_rails(catalog):
    bom = assemble_bom(_mlo_1200_spec(), catalog)["bom"]
    parts = {line.part_number for line in bom}
    assert "RNSB12L8445A" in parts          # the SuperBox
    assert "SR5XBF" in parts                 # XT1 rail group of 5
    assert "SR2XBF" in parts                 # XT1 rail group of 2
    assert "XT4HU3250AY8000XXX" in parts     # branch breaker


def test_xspace_audit_within_capacity(catalog):
    x = assemble_bom(_mlo_1200_spec(), catalog)["validation"]["xspace"]
    assert x["left_used"] <= x["left_capacity"]
    assert x["right_used"] <= x["right_capacity"]
    # MLO main consumes 0 (lugs already in the published capacity) and XT4 is not
    # left-only, so nothing is forced left. left_required = 0.
    assert x["left_required"] == 0
    # total: main 0 + 2x XT4 (3 each) + XT1 groups 5+2 (16) = 22
    assert x["total"] == 22


def test_exact_ampacity_selects_that_box(catalog):
    # panel_amps is the box rating: 600A picks the 600A box, not 800/1200
    spec = Spec(
        panel_amps=600, main_type="MLO", enclosure="NEMA1",
        branches=[Breaker(frame="XT1", poles=3, amps=20, int_rating="N", qty=1)],
    )
    result = assemble_bom(spec, catalog)
    assert result["status"] == "ok"
    assert result["validation"]["selected_superbox"] == "RNSB06L6040A"


def test_load_exceeding_chosen_box_refused(catalog):
    # an 800A box that the load overflows -> refuse, prompting a larger ampacity
    spec = Spec(
        panel_amps=800, main_type="MLO", enclosure="NEMA1",
        branches=[Breaker(frame="XT6", poles=3, amps=800, int_rating="H",
                          trip_unit="TMA", qty=10)],
    )
    result = assemble_bom(spec, catalog)
    assert result["status"] == "refused"
