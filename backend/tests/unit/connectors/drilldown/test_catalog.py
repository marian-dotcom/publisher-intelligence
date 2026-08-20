from datetime import date

import pytest

from app.connectors.core.contracts import ConnectorError
from app.connectors.drilldown.catalog import (
    DRILLDOWN_CATALOG,
    DRILLDOWN_CATALOG_VERSION,
    get_drilldown_definition,
    provider_codes,
    validate_drilldown_scope,
)
from app.connectors.ga4.drilldown import GA4_DRILLDOWN_DEFINITIONS
from app.connectors.gam.drilldown import GAM_DRILLDOWN_DEFINITIONS
from app.connectors.gsc.drilldown import GSC_DRILLDOWN_DEFINITIONS


def test_catalog_contains_only_the_twelve_canonical_semantic_requests() -> None:
    assert len(DRILLDOWN_CATALOG) == 12
    assert len(provider_codes("GA4")) == 4
    assert len(provider_codes("GSC")) == 3
    assert len(provider_codes("GAM")) == 5
    provider_definition_codes: dict[str, set[str]] = {
        "GA4": set(GA4_DRILLDOWN_DEFINITIONS),
        "GSC": set(GSC_DRILLDOWN_DEFINITIONS),
        "GAM": set(GAM_DRILLDOWN_DEFINITIONS),
    }
    for semantic_code, catalog_definition in DRILLDOWN_CATALOG.items():
        assert semantic_code == catalog_definition.code
        assert catalog_definition.catalog_version == DRILLDOWN_CATALOG_VERSION
        assert (
            catalog_definition.provider_definition_code
            in provider_definition_codes[catalog_definition.provider]
        )


def test_explicit_window_and_exact_page_parameter_are_bounded() -> None:
    definition = get_drilldown_definition("web_top_queries_for_page")
    validate_drilldown_scope(
        definition,
        start_date=date(2026, 8, 14),
        end_date=date(2026, 8, 20),
        profile=None,
        parameters={"page": "https://www.example.com/article/?edition=1"},
        today=date(2026, 8, 20),
    )

    for invalid in (
        {"page": "javascript:alert(1)"},
        {"page": "https://user:password@example.com/article/"},
        {"page": "https://example.com/", "operator": "contains"},
    ):
        with pytest.raises(ConnectorError) as raised:
            validate_drilldown_scope(
                definition,
                start_date=date(2026, 8, 14),
                end_date=date(2026, 8, 20),
                profile=None,
                parameters=invalid,
                today=date(2026, 8, 20),
            )
        assert raised.value.code == "DRILLDOWN_PARAMETERS_INVALID"


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (date(2026, 8, 13), date(2026, 8, 20)),
        (date(2026, 8, 20), date(2026, 8, 19)),
        (date(2026, 8, 20), date(2026, 8, 21)),
    ],
)
def test_explicit_window_rejects_more_than_seven_reverse_or_future_dates(
    start: date, end: date
) -> None:
    with pytest.raises(ConnectorError) as raised:
        validate_drilldown_scope(
            get_drilldown_definition("traffic_by_page_device"),
            start_date=start,
            end_date=end,
            profile=None,
            parameters={},
            today=date(2026, 8, 20),
        )
    assert raised.value.code == "DRILLDOWN_WINDOW_INVALID"


def test_gam_accepts_only_fixed_profiles_and_stale_catalog_fails_closed() -> None:
    definition = get_drilldown_definition("ad_unit_by_device")
    validate_drilldown_scope(
        definition,
        start_date=None,
        end_date=None,
        profile="LAST_7_DAYS",
        parameters={},
        today=date(2026, 8, 20),
    )
    with pytest.raises(ConnectorError) as profile_error:
        validate_drilldown_scope(
            definition,
            start_date=None,
            end_date=None,
            profile="CUSTOM",
            parameters={},
            today=date(2026, 8, 20),
        )
    assert profile_error.value.code == "DRILLDOWN_WINDOW_INVALID"
    with pytest.raises(ConnectorError) as version_error:
        get_drilldown_definition("ad_unit_by_device", catalog_version="llm-generated-v9")
    assert version_error.value.code == "CATALOG_VERSION_INVALID"
