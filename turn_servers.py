"""VDO.Ninja TURN discovery using only Python's standard library.

Keep credentials in memory. The browser uses this endpoint and a one-hour cache;
explicit TURN URLs and disabled TURN never need to call it.
"""

import json
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


TURN_DISCOVERY_URL = 'https://turnservers.vdo.ninja/'
# Public fallback also present in VDO.Ninja's root webrtc.js. Prefer discovery,
# which returns current, geographically selected servers and credentials.
FALLBACK_SERVERS = (
    {'url': 'turn:turn-cae1.vdo.ninja:3478', 'user': 'steve', 'pass': 'setupYourOwnPlease'},
    {'url': 'turns:turn-cae1.vdo.ninja:443', 'user': 'steve', 'pass': 'setupYourOwnPlease'},
)
_cache = []
_expires = 0
_lock = threading.Lock()


def select_servers(data):
    """Validate discovery data; use up to two UDP servers and one TCP/TLS."""
    selected, seen = [], set()
    counts = {'udp': 0, 'tcp': 0}
    for server in data.get('servers', []):
        if not isinstance(server, dict):
            continue
        user, password = server.get('username'), server.get('credential')
        if any(not isinstance(value, str) or not value or any(ord(c) < 32 for c in value)
               for value in (user, password)):
            continue
        urls = server.get('urls', [])
        if isinstance(urls, str):
            urls = [urls]
        if not isinstance(urls, list):
            continue
        for url in urls:
            if not isinstance(url, str) or any(c.isspace() for c in url):
                continue
            scheme, _, address = url.partition(':')
            if scheme not in ('turn', 'turns'):
                continue
            try:
                parsed = urlsplit(scheme + '://' + (address[2:] if address.startswith('//') else address))
                if (not parsed.hostname or parsed.username is not None or parsed.path or parsed.fragment
                        or parsed.query not in ('', 'transport=udp', 'transport=tcp')
                        or (parsed.port is not None and not 0 < parsed.port < 65536)):
                    continue
            except ValueError:
                continue
            transport = 'tcp' if scheme == 'turns' or parsed.query == 'transport=tcp' else 'udp'
            if url in seen or counts[transport] >= (2 if transport == 'udp' else 1):
                continue
            selected.append({'url': url, 'user': user, 'pass': password})
            seen.add(url)
            counts[transport] += 1
    return selected


def get_default_turn_servers(log=None):
    global _cache, _expires
    with _lock:
        now = time.monotonic()
        if now >= _expires:
            try:
                request = Request(TURN_DISCOVERY_URL, headers={'User-Agent': 'RaspberryNinja'})
                with urlopen(request, timeout=2) as response:
                    raw = response.read(128 * 1024 + 1)
                if len(raw) > 128 * 1024:
                    raise ValueError('oversized TURN list')
                servers = select_servers(json.loads(raw))
                if not servers:
                    raise ValueError('empty TURN list')
                _cache, _expires = servers, now + 3600
            except Exception:
                _cache, _expires = list(FALLBACK_SERVERS), now + 60
                if log:
                    log('TURN discovery unavailable; using VDO.Ninja fallback servers.')
        return [dict(server) for server in _cache]
