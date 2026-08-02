from __future__ import annotations

from urllib.parse import urlparse


OFFICIAL_HANDSHAKE_HOSTS = {
    "wss.vdo.ninja",
    "apibackup.vdo.ninja",
}


def handshake_server_requires_puuid(server: str) -> bool:
    """Return whether a custom handshake server needs a generated publisher UUID."""
    parsed = urlparse(server if "://" in server else f"wss://{server}")
    hostname = (parsed.hostname or "").lower()
    return hostname not in OFFICIAL_HANDSHAKE_HOSTS
