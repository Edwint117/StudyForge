"""SSRF protection policy for outbound HTTP (doc 09 "SSRF Prevention"; M4-07).

Two layers:
* ``HostAllowlist``: vendor API clients may only talk to known hosts (e.g. ``*.googleapis.com``).
* ``check_url`` / ``resolve_public``: for any URL that isn't a fixed vendor API (none at launch; ready for URL
  ingestion later): http(s) only, no credentials in the URL, standard ports, resolve DNS **once**, require every
  resolved address to be public, then connect to that pinned address (defeats DNS rebinding). Every redirect hop is
  re-validated, with at most 3 hops.

The HTTP client that enforces the 5 MB / 10 s limits and connects to the pinned IP is built in M4
on top of these checks.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Callable, Iterable
from urllib.parse import urljoin, urlsplit

VERSION = "netguard-1"

MAX_REDIRECTS = 3
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
TIMEOUT_S = 10.0
ALLOWED_SCHEMES = frozenset({"http", "https"})
ALLOWED_PORTS = frozenset({80, 443})

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
Resolver = Callable[[str], Iterable[str]]  # host -> IP strings (e.g. wraps socket.getaddrinfo)

_EXTRA_BLOCKED = (
    ipaddress.ip_network("100.64.0.0/10"),  # carrier-grade NAT (not flagged private by ipaddress)
    ipaddress.ip_network("192.0.0.0/24"),  # IETF protocol assignments
    ipaddress.ip_network("198.18.0.0/15"),  # benchmarking
)


class BlockedURL(ValueError):
    """The URL or its resolved address is not allowed. Maps to a 422 with a generic message (don't echo internals)."""


def is_public_ip(ip: IPAddress) -> bool:
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:  # ::ffff:10.0.0.1
            return is_public_ip(ip.ipv4_mapped)
        if ip in ipaddress.ip_network("64:ff9b::/96"):  # NAT64 embeds an IPv4 address
            return is_public_ip(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
        if ip.sixtofour is not None:  # 2002::/16 embeds an IPv4 address
            return is_public_ip(ip.sixtofour)
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local  # includes 169.254.169.254 (cloud metadata)
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return False
    return not any(ip in net for net in _EXTRA_BLOCKED if ip.version == net.version)


def _host_of(url: str) -> tuple[str, int]:
    parts = urlsplit(url)
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise BlockedURL("scheme not allowed")
    if parts.username is not None or parts.password is not None:
        raise BlockedURL("credentials in URL not allowed")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise BlockedURL("missing host")
    try:
        port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise BlockedURL("invalid port") from exc
    if port not in ALLOWED_PORTS:
        raise BlockedURL("port not allowed")
    # Obfuscated IPv4 literals (decimal "2130706433", hex "0x7f000001", octal "0177.0.0.1") are refused outright.
    if (
        host.replace(".", "").isdigit()
        or host.startswith("0x")
        or any(p.startswith("0") and len(p) > 1 and p.isdigit() for p in host.split("."))
    ):
        try:
            ipaddress.IPv4Address(host)
        except ValueError as exc:
            raise BlockedURL("non-canonical IP literal") from exc
    try:
        host.encode("idna")
    except UnicodeError as exc:
        raise BlockedURL("invalid hostname") from exc
    return host, port


def check_url(url: str) -> tuple[str, int]:
    """Static checks only (no DNS). Returns (host, port)."""
    return _host_of(url)


def resolve_public(url: str, resolver: Resolver) -> tuple[str, int, IPAddress]:
    """Static checks + DNS: every resolved address must be public. Returns (host, port, pinned_ip)."""
    host, port = _host_of(url)
    try:
        literal: IPAddress | None = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    addresses = [literal] if literal is not None else [ipaddress.ip_address(a) for a in resolver(host)]
    if not addresses:
        raise BlockedURL("host did not resolve")
    if not all(is_public_ip(a) for a in addresses):
        raise BlockedURL("destination is not a public address")
    return host, port, addresses[0]


def next_hop(current_url: str, location: str, hops_so_far: int, resolver: Resolver) -> tuple[str, IPAddress]:
    """Validate a redirect: resolve ``Location`` against the current URL, enforce the hop limit, re-check it all."""
    if hops_so_far >= MAX_REDIRECTS:
        raise BlockedURL("too many redirects")
    target = urljoin(current_url, location)
    _, _, ip = resolve_public(target, resolver)
    return target, ip


class HostAllowlist:
    """Exact hosts, or ``*.example.com`` patterns that match subdomains (not the bare domain)."""

    def __init__(self, patterns: Iterable[str]) -> None:
        self._exact: set[str] = set()
        self._suffixes: list[str] = []
        for p in patterns:
            p = p.lower().rstrip(".")
            if p.startswith("*."):
                self._suffixes.append(p[1:])  # ".example.com"
            else:
                self._exact.add(p)

    def allows(self, url: str) -> bool:
        try:
            host, _ = _host_of(url)
        except BlockedURL:
            return False
        return host in self._exact or any(host.endswith(s) for s in self._suffixes)


# Vendor hosts the engine and web tier may call at launch (doc 06). Extend when an adapter is added.
VENDOR_HOSTS = HostAllowlist(
    [
        "api.anthropic.com",
        "*.googleapis.com",
        "oauth2.googleapis.com",
        "*.supabase.co",
        "*.ingest.us.sentry.io",
        "*.ingest.sentry.io",
        "us.i.posthog.com",
        "us.posthog.com",
        "us.cloud.langfuse.com",
        "cloud.langfuse.com",
        "uptime.betterstack.com",
        "api.deepgram.com",
        "api.assemblyai.com",
        "api.mistral.ai",
        "api.voyageai.com",
        "api.openai.com",
        "haveibeenpwned.com",
        "api.pwnedpasswords.com",
    ]
)
