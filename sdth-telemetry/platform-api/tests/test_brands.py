from app.brands import GENERIC, brand_catalog, identify_brand
from app.canonical_series import series_from_l1_payload
from tests.hardware_l1 import HARDWARE_CASES


def test_catalog_covers_repo_hardware():
    ids = {item["id"] for item in brand_catalog()}
    assert ids >= {"dji", "px4", "ardupilot", "hermes900", "orbiter4", "aunav", "generic"}


def test_identify_each_hardware_payload():
    for brand_id, builder, _expected in HARDWARE_CASES:
        payload = builder(f"id-{brand_id}")
        series = series_from_l1_payload(payload)
        brand = identify_brand(series[0], source=payload["source"])
        assert brand.id == brand_id, (payload["source"], series[0]["metadata"], series[0]["sensors"])


def test_unknown_source_is_generic():
    assert identify_brand({}, source="teammate-simulator").id == GENERIC.id
