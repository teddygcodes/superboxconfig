"""Accessory catalog resolution + BOM integration (pp.11-61/62)."""

import pytest

from superbox_bom.engine import (
    Breaker, Spec, assemble_bom, resolve_breaker_accessory, resolve_panel_accessory,
)
from superbox_bom.errors import CatalogError


# ---- breaker-mounted accessories ----

@pytest.mark.parametrize("frame,acc,code", [
    ("XT1", {"kind": "shunt_trip", "volts": 110}, "KXTASORCFPD"),
    ("XT7", {"kind": "shunt_trip", "volts": 24}, "ZEZSZ"),
    ("XT1", {"kind": "undervoltage_release", "volts": 24}, "KXTAUVRCFP1"),
    ("XT1", {"kind": "aux_contacts", "type": "AUX-C 2 Q + 1 SY", "volts": 250}, "KXTAAXC2QSYFP"),
    ("XT2", {"kind": "padlock", "style": "fixed_open"}, "KXTCPLLOP"),
    ("A2", {"kind": "padlock", "style": "removable"}, "KA2LDOR"),
    ("XT4", {"kind": "service_entrance_barrier", "variant": "350kcmil"}, "SBX4W35P3"),
])
def test_resolve_breaker_accessory(catalog, frame, acc, code):
    assert resolve_breaker_accessory(acc, frame, catalog)["code"] == code


def test_xt5_shunt_merged_cell_wildcard_volts(catalog):
    # XT5/XT6 shunt trip is a single merged record (volts=null) -> resolves regardless
    assert resolve_breaker_accessory({"kind": "shunt_trip"}, "XT5", catalog)["code"] == "KXTFYOCFPD"


def test_accessory_not_available_for_frame(catalog):
    # XT4 has no pre-cabled shunt trip in the merchandised table
    with pytest.raises(CatalogError):
        resolve_breaker_accessory({"kind": "shunt_trip", "volts": 24}, "XT4", catalog)


# ---- panel-level accessories ----

@pytest.mark.parametrize("acc,code,xspace", [
    ({"kind": "spd", "voltage": "480Y/277", "ka": 150}, "RGPPSP277Y15T2", 10),
    ({"kind": "spd", "voltage": "208Y/120", "ka": 80}, "RGPPSP120Y08T2", 10),
    ({"kind": "rgm40", "function": "advanced", "protocol": "BACnet", "voltage": "480,240"}, "RGM40V6BT", 4),
    ({"kind": "blank", "width": 2, "filler": True}, "SR02BF", 2),
    ({"kind": "relt", "type": "kit", "volts": "480"}, "RT04B", 3),
])
def test_resolve_panel_accessory(catalog, acc, code, xspace):
    r = resolve_panel_accessory(acc, catalog)
    assert r["code"] == code
    assert r["x_space"] == xspace


# ---- end-to-end through assemble_bom ----

def _spec_with_accessories():
    return Spec(
        panel_amps=1200, main_type="MCB", enclosure="NEMA1",
        main=Breaker(frame="XT7", poles=3, amps=1200, int_rating="H",
                     trip_unit="Ekip Touch LSI", orientation="vertical"),
        branches=[
            Breaker(frame="XT5", poles=3, amps=400, int_rating="H", trip_unit="Ekip DIP LSI",
                    qty=1, accessories=[{"kind": "shunt_trip"}]),
            Breaker(frame="XT4", poles=3, amps=250, int_rating="H", trip_unit="TMF", qty=2),
            Breaker(frame="XT1", poles=3, amps=100, int_rating="N", qty=5),
        ],
        accessories=[
            {"kind": "spd", "voltage": "480Y/277", "ka": 150},
            {"kind": "rgm40", "function": "standard", "protocol": "Modbus RTU", "voltage": "480Y/277,208Y/120"},
        ],
    )


def test_accessories_appear_in_bom(catalog):
    bom = assemble_bom(_spec_with_accessories(), catalog)
    assert bom["status"] == "ok"
    parts = {l.part_number for l in bom["bom"]}
    assert "KXTFYOCFPD" in parts        # XT5 shunt trip
    assert "RGPPSP277Y15T2" in parts    # SPD
    assert "RGM40V1MX" in parts         # RGM40 meter
    assert "SR5XBF" in parts            # 5 XT1 -> one rail


def test_xt5_shunt_trip_adds_one_xspace(catalog):
    # left = MCB main (XT7 frame = 6) + XT5 (4 + 1 accessory = 5) = 11
    x = assemble_bom(_spec_with_accessories(), catalog)["validation"]["xspace"]
    assert x["left_required"] == 11


def test_spd_and_rgm40_xspace_counted(catalog):
    x = assemble_bom(_spec_with_accessories(), catalog)["validation"]["xspace"]
    # total = left 11 + flex [2x XT4 =6, XT1x5 grouped =11, SPD 10, RGM40 4] = 11 + 31 = 42
    assert x["total"] == 42
