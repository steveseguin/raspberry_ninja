#!/usr/bin/env python3
"""Serve local HLS files with CORS headers."""
import argparse
from functools import partial
import http.server
from pathlib import Path


class CORSHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def _is_playlist(self):
        return Path(self.translate_path(self.path)).suffix.lower() == '.m3u8'

    def send_head(self):
        if self._is_playlist():
            # HTTP dates only have second precision; live playlists can change
            # more than once per second. Always serve their current contents.
            for header in ('If-Modified-Since', 'If-None-Match'):
                if header in self.headers:
                    del self.headers[header]
        return super().send_head()

    def end_headers(self):
        if self._is_playlist():
            self.send_header('Cache-Control', 'no-store')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path(__file__).resolve().parents[1],
                        help='directory to serve (default: repository root)')
    parser.add_argument('--port', type=int, default=8089)
    parser.add_argument('--bind', default='', help='address to bind (default: all interfaces)')
    args = parser.parse_args(argv)
    directory = args.directory.expanduser().resolve()
    if not directory.is_dir():
        parser.error('--directory must be an existing directory')
    if not 0 <= args.port <= 65535:
        parser.error('--port must be between 0 and 65535')
    handler = partial(CORSHTTPRequestHandler, directory=str(directory))
    with http.server.ThreadingHTTPServer((args.bind, args.port), handler) as server:
        print(f'Serving {directory} at http://{args.bind or "localhost"}:{server.server_port}')
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
