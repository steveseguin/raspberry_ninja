"""Shared file boundary for the built-in and standalone HLS servers."""
from pathlib import Path, PureWindowsPath


def resolve_hls_file(directory, filename):
    """Accept only media files contained by the configured serving directory."""
    name = Path(filename)
    if (not filename or '\\' in filename or '\x00' in filename or name.is_absolute()
            or PureWindowsPath(filename).drive or '..' in name.parts
            or name.suffix.lower() not in ('.m3u8', '.ts')):
        raise ValueError('Invalid HLS path')
    root = Path(directory).resolve()
    target = (root / name).resolve()
    target.relative_to(root)  # Also reject symlinks escaping the media directory.
    if target.suffix.lower() not in ('.m3u8', '.ts'):
        raise ValueError('Invalid HLS file type')
    if not target.is_file():
        raise FileNotFoundError('HLS file not found')
    return target
