"""Filesystem names for media identifiers received through signaling."""
import hashlib
import string


def recording_component(value):
    """Encode an identifier as one portable filename component.

    Tilde escapes avoid slashes, Windows filename restrictions, URL delimiters,
    and percent directives in GStreamer's numbered HLS segment paths. Encoding
    the escape character itself keeps distinct short identifiers distinct.
    """
    value = str(value)
    safe = string.ascii_letters + string.digits + '-_.'
    encoded = ''.join(char if char in safe else ''.join(f'~{byte:02X}' for byte in char.encode('utf-8'))
                      for char in value)
    if not encoded or encoded in ('.', '..'):
        encoded = ''.join(f'~{byte:02X}' for byte in value.encode('utf-8')) or '~empty'
    if len(encoded) > 80:
        encoded = encoded[:60] + '~' + hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]
    return encoded
