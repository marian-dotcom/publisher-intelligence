from app.public_config.client import ROBOTS_TXT_MAX_BYTES
from app.public_config.robots import RobotsRule, parse_robots_txt


def test_groups_merge_repeated_agents_and_bad_lines_do_not_discard_rules() -> None:
    result = parse_robots_txt(
        b"""
        User-Agent: GoogleBot
        User-agent: BingBot
        Disallow: /private
        Unsupported: still-in-group
        bad line
        User-agent: googlebot
        Allow: /private/public
        """
    )

    assert result.parse_status == "VALID_WITH_WARNINGS"
    assert result.groups == (
        ("bingbot", (RobotsRule("disallow", "/private"),)),
        (
            "googlebot",
            (RobotsRule("allow", "/private/public"), RobotsRule("disallow", "/private")),
        ),
    )
    assert "LINE_6_MISSING_SEPARATOR" in result.diagnostics


def test_longest_match_allow_tie_wildcard_and_end_marker_follow_rfc() -> None:
    result = parse_robots_txt(
        b"""
        User-agent: *
        Disallow: /folder
        Allow: /folder
        Disallow: /*.pdf$
        Allow: /public/*.pdf$
        User-agent: Googlebot
        Disallow: /google-only
        """
    )

    assert result.is_allowed("OtherBot", "/folder/page")
    assert not result.is_allowed("OtherBot", "/manual.pdf")
    assert result.is_allowed("OtherBot", "/manual.pdf?download=1")
    assert result.is_allowed("OtherBot", "/public/manual.pdf")
    assert not result.is_allowed("Googlebot-News", "/google-only")
    assert result.is_allowed("Googlebot-News", "/manual.pdf")


def test_empty_rule_still_ends_the_user_agent_block() -> None:
    result = parse_robots_txt(
        b"User-agent: FirstBot\nDisallow:\nUser-agent: SecondBot\nDisallow: /second\n"
    )

    assert result.is_allowed("FirstBot", "/second")
    assert not result.is_allowed("SecondBot", "/second")


def test_percent_encoding_case_and_semantic_noise_normalize() -> None:
    first = parse_robots_txt(b"User-agent: *\r\nDisallow: /caf%C3%A9\r\nAllow: /foo%62ar\r\n")
    second = parse_robots_txt(
        "# moved\nUSER-AGENT: *\nALLOW: /foobar\nDISALLOW: /caf\u00e9\n".encode()
    )

    assert first.semantic_hash == second.semantic_hash
    assert not first.is_allowed("Crawler", "/caf%C3%A9")
    assert first.is_allowed("Crawler", "/foobar")


def test_comments_order_duplicates_and_sitemaps_do_not_change_semantic_hash() -> None:
    first = parse_robots_txt(
        b"User-agent: *\nDisallow: /private\nSitemap: https://example.com/a.xml\n"
    )
    second = parse_robots_txt(
        b"# comment\nSitemap: https://example.com/b.xml\nDisallow: /private\n"
        b"User-agent: *\nDisallow: /private\n"
    )

    assert first.semantic_hash == second.semantic_hash
    assert first.summary["sitemaps"] != second.summary["sitemaps"]


def test_empty_invalid_broad_block_and_warning_states_are_distinct() -> None:
    assert parse_robots_txt(b"# only a comment\n").parse_status == "EMPTY"
    assert parse_robots_txt(b"Sitemap: https://example.com/map.xml\n").parse_status == "INVALID"

    blocked = parse_robots_txt(b"User-agent: *\nDisallow: /\n")
    excepted = parse_robots_txt(b"User-agent: *\nDisallow: /\nAllow: /public\n")

    assert blocked.broad_blocked
    assert not excepted.broad_blocked


def test_parser_processes_the_full_512000_byte_budget() -> None:
    prefix = b"User-agent: *\nDisallow: /private\n"
    content = prefix + b"#" + b"x" * (ROBOTS_TXT_MAX_BYTES - len(prefix) - 2) + b"\n"

    result = parse_robots_txt(content)

    assert len(content) == ROBOTS_TXT_MAX_BYTES
    assert result.parse_status == "VALID"
    assert not result.is_allowed("Crawler", "/private")
