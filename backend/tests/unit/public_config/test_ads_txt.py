from app.public_config.ads_txt import parse_ads_txt


def test_valid_three_and_four_field_records_are_normalized() -> None:
    result = parse_ads_txt(
        b"Example.COM, account-1, direct\nseller.example, account-2, RESELLER, ABCDEF012345\n"
    )

    assert result.parse_status == "VALID"
    assert len(result.records) == 2
    records = {record.publisher_account_id: record for record in result.records}
    assert records["account-1"].advertising_system_domain == "example.com"
    assert records["account-1"].relationship == "DIRECT"
    assert records["account-2"].cert_authority_id == "abcdef012345"


def test_v11_directives_are_semantic_but_never_followed() -> None:
    result = parse_ads_txt(
        b"OWNERDOMAIN=Publisher.Example\n"
        b"MANAGERDOMAIN=Manager.Example, us\n"
        b"SUBDOMAIN=inventory.publisher.example\n"
        b"INVENTORYPARTNERDOMAIN=partner.example\n"
        b"CONTACT=mailto:ads@example.com\n"
        b"exchange.example, seller-1, DIRECT\n"
    )

    assert result.parse_status == "VALID"
    assert result.owner_domain == "publisher.example"
    assert result.manager_domains == (("manager.example", "US"),)
    assert result.summary["directive_counts"] == {
        "CONTACT": 1,
        "INVENTORYPARTNERDOMAIN": 1,
        "MANAGERDOMAIN": 1,
        "OWNERDOMAIN": 1,
        "SUBDOMAIN": 1,
    }


def test_semantic_hash_ignores_comments_order_whitespace_and_duplicates() -> None:
    first = parse_ads_txt(
        b"OWNERDOMAIN=publisher.example\n"
        b"exchange.example, acct, DIRECT, abc\n"
        b"seller.example, other, reseller\n"
    )
    second = parse_ads_txt(
        b"# reordered\r\n seller.example , other , RESELLER \r\n"
        b"EXCHANGE.EXAMPLE,acct,direct,ABC\r\n"
        b"exchange.example, acct, DIRECT, abc # duplicate\r\n"
        b"OWNERDOMAIN = publisher.example\r\n"
    )

    assert first.semantic_hash == second.semantic_hash
    assert second.parse_status == "VALID_WITH_WARNINGS"
    assert second.summary["duplicate_record_count"] == 1


def test_malformed_rows_are_bounded_warnings_when_valid_records_remain() -> None:
    malformed = b"\n".join(b"not,enough" for _index in range(30))
    result = parse_ads_txt(malformed + b"\nexchange.example, account, DIRECT\n")

    assert result.parse_status == "VALID_WITH_WARNINGS"
    assert result.summary["invalid_row_count"] == 30
    assert len(result.diagnostics) == 20
    assert len(result.records) == 1


def test_empty_and_materially_invalid_states_are_distinct() -> None:
    empty = parse_ads_txt(b"# intentionally blank\n")
    invalid = parse_ads_txt(b"OWNERDOMAIN=publisher.example\nnot,a,seller,record,here\n")

    assert empty.parse_status == "EMPTY"
    assert invalid.parse_status == "INVALID"
    assert invalid.summary["valid_record_count"] == 0
    assert "NO_VALID_SELLER_RECORDS" in invalid.diagnostics


def test_invalid_and_duplicate_owner_manager_directives_are_diagnostic() -> None:
    result = parse_ads_txt(
        b"OWNERDOMAIN=publisher.example\n"
        b"OWNERDOMAIN=other.example\n"
        b"MANAGERDOMAIN=manager.example, USA\n"
        b"exchange.example, account, DIRECT\n"
    )

    assert result.parse_status == "VALID_WITH_WARNINGS"
    assert result.owner_domain == "publisher.example"
    assert any("DUPLICATE_OWNERDOMAIN" in item for item in result.diagnostics)
    assert any("INVALID_MANAGERDOMAIN" in item for item in result.diagnostics)
