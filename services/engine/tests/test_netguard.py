import ipaddress
from collections.abc import Iterable

import pytest

from engine.adapters.netguard import (
    VENDOR_HOSTS,
    BlockedURL,
    HostAllowlist,
    check_url,
    is_public_ip,
    next_hop,
    resolve_public,
)

DNS = {
    "example.com": ["93.184.215.14"],
    "rebind.evil.test": ["93.184.215.14", "127.0.0.1"],  # any private answer blocks the host
    "internal.evil.test": ["10.0.0.5"],
    "v6.example.com": ["2606:2800:21f:cb07:6820:80da:af6b:8b2c"],
}


def resolver(host: str) -> Iterable[str]:
    return DNS.get(host, [])


@pytest.mark.parametrize(
    ("ip", "public"),
    [
        ("93.184.215.14", True),
        ("8.8.8.8", True),
        ("10.1.2.3", False),
        ("172.16.0.1", False),
        ("192.168.1.1", False),
        ("127.0.0.1", False),
        ("169.254.169.254", False),  # cloud metadata
        ("100.64.0.1", False),  # CGNAT
        ("0.0.0.0", False),  # noqa: S104 - test data: unspecified address must be blocked
        ("224.0.0.1", False),
        ("::1", False),
        ("fd00::1", False),  # unique local
        ("fe80::1", False),
        ("::ffff:10.0.0.1", False),  # IPv4-mapped private
        ("::ffff:8.8.8.8", True),
        ("64:ff9b::a00:1", False),  # NAT64 wrapping 10.0.0.1
        ("2002:a00:1::", False),  # 6to4 wrapping 10.0.0.1
        ("2606:4700:4700::1111", True),
    ],
)
def test_is_public_ip(ip: str, public: bool) -> None:
    assert is_public_ip(ipaddress.ip_address(ip)) is public


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "gopher://example.com/",
        "ftp://example.com/",
        "https://user:pass@example.com/",
        "https://example.com:8080/",
        "http://2130706433/",  # decimal 127.0.0.1
        "http://0x7f000001/",
        "http://0177.0.0.1/",  # octal
        "https:///nohost",
    ],
)
def test_check_url_rejects(url: str) -> None:
    with pytest.raises(BlockedURL):
        check_url(url)


def test_check_url_accepts_normal_urls() -> None:
    assert check_url("https://Example.com./path?q=1") == ("example.com", 443)
    assert check_url("http://example.com/") == ("example.com", 80)


def test_resolve_public_pins_first_public_address() -> None:
    assert resolve_public("https://example.com/x", resolver)[2] == ipaddress.ip_address("93.184.215.14")
    assert resolve_public("https://v6.example.com/", resolver)[2].version == 6


@pytest.mark.parametrize(
    "url",
    [
        "https://internal.evil.test/",
        "https://rebind.evil.test/",
        "https://nowhere.test/",  # doesn't resolve
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data/",
    ],
)
def test_resolve_public_blocks(url: str) -> None:
    with pytest.raises(BlockedURL):
        resolve_public(url, resolver)


def test_redirects_are_revalidated_and_limited() -> None:
    target, ip = next_hop("https://example.com/a", "/b", 0, resolver)
    assert target == "https://example.com/b" and str(ip) == "93.184.215.14"
    with pytest.raises(BlockedURL):
        next_hop("https://example.com/a", "http://internal.evil.test/", 0, resolver)
    with pytest.raises(BlockedURL):
        next_hop("https://example.com/a", "/c", 3, resolver)


def test_host_allowlist() -> None:
    allow = HostAllowlist(["api.anthropic.com", "*.googleapis.com"])
    assert allow.allows("https://api.anthropic.com/v1/messages")
    assert allow.allows("https://www.googleapis.com/calendar/v3")
    assert not allow.allows("https://googleapis.com/")  # wildcard matches subdomains only
    assert not allow.allows("https://api.anthropic.com.evil.test/")
    assert not allow.allows("https://evilgoogleapis.com/")
    assert not allow.allows("file:///etc/passwd")
    assert VENDOR_HOSTS.allows("https://abcdefghijklmnopqrst.supabase.co/rest/v1/")
