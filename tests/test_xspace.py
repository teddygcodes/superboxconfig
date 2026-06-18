"""Main / frame X-space accounting (rules #3 and #4)."""

from superbox_bom.engine import Breaker, Spec, frame_xspace, main_xspace


def test_mlo_main_consumes_zero(catalog):
    # the published MLO box capacity already nets out the main lugs -> charge 0
    spec = Spec(panel_amps=600, main_type="MLO", enclosure="NEMA1")
    assert main_xspace(spec, catalog) == 0


def test_mcb_horizontal_is_frame_xspace_only(catalog):
    main = Breaker(frame="XT4", poles=3, amps=250, int_rating="H", orientation="horizontal")
    spec = Spec(panel_amps=600, main_type="MCB", enclosure="NEMA1", main=main)
    # only the selected main breaker's own frame X-space (Step 4 footnote 1)
    assert main_xspace(spec, catalog) == 3


def test_vertical_main_is_frame_xspace_only(catalog):
    main = Breaker(frame="XT4", poles=3, amps=250, int_rating="H", orientation="vertical")
    spec = Spec(panel_amps=600, main_type="MCB", enclosure="NEMA1", main=main)
    # simplified per "use the published spaces": main breaker frame X only (3), no extra lug pad
    assert main_xspace(spec, catalog) == 3


def test_xt5_plus_one_with_accessory(catalog):
    base = frame_xspace("XT5", 3, catalog, has_elec_accessory=False)
    withacc = frame_xspace("XT5", 3, catalog, has_elec_accessory=True)
    assert withacc == base + 1


def test_xt5_no_extra_without_accessory(catalog):
    assert frame_xspace("XT5", 3, catalog, has_elec_accessory=False) == 4
