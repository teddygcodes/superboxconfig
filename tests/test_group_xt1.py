"""XT1 grouping rule (rule #1) — the most bug-prone logic."""

import pytest

from superbox_bom.engine import group_xt1

# n -> (expected groups descending, expected total X-space)
CASES = {
    1: ([1], 3),
    2: ([2], 5),
    3: ([2, 1], 8),
    4: ([2, 2], 10),
    5: ([5], 11),
    6: ([5, 1], 14),
    7: ([5, 2], 16),     # NOT [5, 1, 1] (17X)
    10: ([5, 5], 22),
    11: ([5, 5, 1], 25),
}


@pytest.mark.parametrize("n,expected", CASES.items())
def test_grouping_and_xspace(catalog, n, expected):
    groups, total = expected
    result = group_xt1(n, catalog)
    assert result["groups"] == groups
    assert result["total_xspace"] == total


def test_seven_is_five_plus_two_not_five_one_one(catalog):
    r = group_xt1(7, catalog)
    assert r["groups"] == [5, 2]
    assert r["groups"] != [5, 1, 1]
    assert r["total_xspace"] == 16  # 11 + 5, beats 11 + 3 + 3 = 17


def test_rails_emitted_bf_family(catalog):
    r = group_xt1(7, catalog, rail_family="BF")
    assert r["rails"] == ["SR5XBF", "SR2XBF"]


def test_eleven_emits_three_rails(catalog):
    r = group_xt1(11, catalog, rail_family="BF")
    assert r["rails"] == ["SR5XBF", "SR5XBF", "SR1XBF"]


def test_zero(catalog):
    r = group_xt1(0, catalog)
    assert r["groups"] == []
    assert r["total_xspace"] == 0
