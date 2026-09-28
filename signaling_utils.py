from __future__ import annotations

from urllib.parse import quote, urlparse


def normalize_vdo_password(password, *, raw=False):
    """Match VDO.Ninja's trim + encodeURIComponent before hashing/encryption."""
    if not password or raw:
        return password
    if not password.strip():
        raise ValueError('password cannot contain only whitespace; use --password false to disable it explicitly')
    return quote(password.strip(), safe="~()*!.'-")


def encode_browser_password(password: str) -> str:
    """Quote a browser query value, preserving literal percent escapes too.

    VDO.Ninja decodes passwords once beyond URLSearchParams decoding.
    """
    return quote(password.replace('%', '%25'), safe='')


OFFICIAL_HANDSHAKE_HOSTS = {
    "wss.vdo.ninja",
    "apibackup.vdo.ninja",
}


def handshake_server_requires_puuid(server: str) -> bool:
    """Return whether a custom handshake server needs a generated publisher UUID."""
    parsed = urlparse(server if "://" in server else f"wss://{server}")
    hostname = (parsed.hostname or "").lower()
    return hostname not in OFFICIAL_HANDSHAKE_HOSTS
