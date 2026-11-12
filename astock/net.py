#!/usr/bin/env python3
"""Shared public-network fetch with a verifiable TLS context.

On macOS a framework Python can ship without a usable CA bundle, which makes
every ``urllib`` call fail certificate verification. Rather than disable
verification, this module builds the default context and, only when needed,
falls back to well-known system certificate bundles. Stdlib only.
"""

from __future__ import annotations

import ssl
import urllib.request

_FALLBACK_BUNDLES = (
    "/etc/ssl/cert.pem",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/usr/local/etc/openssl/cert.pem",
    "/opt/homebrew/etc/ca-certificates/cert.pem",
)

_context: ssl.SSLContext | None = None


def context() -> ssl.SSLContext:
    """Return a verifying SSL context, falling back to system CA bundles."""
    global _context
    if _context is not None:
        return _context
    _context = ssl.create_default_context()
    if not _has_ca(_context):
        for bundle in _FALLBACK_BUNDLES:
            try:
                candidate = ssl.create_default_context(cafile=bundle)
            except (ssl.SSLError, OSError):
                continue
            if _has_ca(candidate):
                _context = candidate
                break
    return _context


def _has_ca(ctx: ssl.SSLContext) -> bool:
    return bool(ctx.cert_store_stats().get("x509"))


def open_url(
    url: str,
    *,
    headers: dict | None = None,
    data: bytes | None = None,
    timeout: int = 15,
):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    return urllib.request.urlopen(req, timeout=timeout, context=context())
