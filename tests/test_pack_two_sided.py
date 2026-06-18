"""Two-sided packing / XT5-on-left enforcement (rule #2)."""

from superbox_bom.engine import XItem, pack_two_sided

# a 600A-like SKU: 12 X-space each side (24 total)
SKU = {"sku": "TEST", "xspace_left": 12, "xspace_right": 12}


def _left(frame, x, n):
    return [XItem(label=frame, xspace=x, frame=frame, side="left") for _ in range(n)]


def _flex(frame, x, n):
    return [XItem(label=frame, xspace=x, frame=frame, side="flexible") for _ in range(n)]


def test_fits_on_total_but_violates_left_is_invalid():
    # 3 XT6 (6X each) = 18X on the LEFT only. Total 18 <= 24, but left cap is 12.
    left = _left("XT6", 6, 3)
    result = pack_two_sided(left, [], SKU)
    assert result["fits"] is False
    assert "left" in result["reason"].lower()


def test_mirror_case_fits():
    # 2 XT6 = 12X left, exactly at the left capacity.
    left = _left("XT6", 6, 2)
    result = pack_two_sided(left, [], SKU)
    assert result["fits"] is True
    assert result["left_used"] == 12
    assert result["right_used"] == 0


def test_flexible_overflow_to_right():
    # 2 XT6 left (12X, fills left) + flexible 10X must all go right (<=12). Fits.
    left = _left("XT6", 6, 2)
    flex = _flex("XT2", 5, 2)  # 10X flexible
    result = pack_two_sided(left, flex, SKU)
    assert result["fits"] is True
    assert result["left_used"] == 12
    assert result["right_used"] == 10


def test_total_exceeds_capacity():
    # left 12 + flex 20 = 32 > 24 total -> invalid
    left = _left("XT6", 6, 2)
    flex = _flex("XT2", 5, 4)  # 20X
    result = pack_two_sided(left, flex, SKU)
    assert result["fits"] is False


def test_indivisible_flex_cannot_split():
    # left empty; right cap 12, left cap 12; one indivisible 13X group can't fit either side
    flex = [XItem(label="XT1g", xspace=13, frame="XT1", side="flexible")]
    result = pack_two_sided([], flex, SKU)
    assert result["fits"] is False
