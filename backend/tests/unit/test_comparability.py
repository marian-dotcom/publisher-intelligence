from app.common.comparability import evidence_fingerprints, fingerprints_comparable


def test_fingerprint_snapshot_is_stable_and_ordered() -> None:
    a = evidence_fingerprints(
        {"rule_bundle": "e3-v1", "collector_bundle": "b8-v1", "robots": "robots-rfc9309-v1"}
    )
    b = evidence_fingerprints(
        {"robots": "robots-rfc9309-v1", "collector_bundle": "b8-v1", "rule_bundle": "e3-v1"}
    )
    assert a == b
    assert list(a) == sorted(a)
    assert a["collector_bundle"] == "b8-v1"


def test_each_differing_version_dimension_breaks_comparability() -> None:
    base = {
        "collector_bundle": "b8-v1",
        "ads_txt": "ads-txt-1.1-v1",
        "rule_bundle": "e3-v1",
    }
    assert fingerprints_comparable(base, dict(base))
    for key, value in (
        ("collector_bundle", "b9-v1"),
        ("ads_txt", "ads-txt-1.2-v1"),
        ("rule_bundle", "e4-v1"),
    ):
        changed = dict(base) | {key: value}
        assert not fingerprints_comparable(base, changed)


def test_missing_version_dimension_is_incomparable() -> None:
    full = evidence_fingerprints({"collector": "b8-v1", "robots": "v1"})
    partial = evidence_fingerprints({"collector": "b8-v1"})
    assert not fingerprints_comparable(full, partial)


def test_values_are_stringified() -> None:
    snapshot = evidence_fingerprints({"version": 8})
    assert snapshot == {"version": "8"}
