"""Resolve explicitly selected USB audio identity on each publisher launch."""
import os
import re


def resolve_alsa_device(device):
    """Accept legacy ALSA names or a persistent udev sound-card symlink.

    Persistent paths select PCM device zero of that card. Missing paths are
    errors, never a request to fall back to another microphone or disable audio.
    """
    if not device or not device.startswith(('/dev/snd/by-id/', '/dev/snd/by-path/')):
        return device
    if not os.path.exists(device):
        raise ValueError('Selected USB microphone is unavailable: ' + device
                         + '. Reconnect it; an unattended service will retry.')
    target = os.path.realpath(device)
    match = re.fullmatch(r'/dev/snd/controlC([0-9]+)', target)
    if not match:
        raise ValueError('USB microphone path must resolve to an ALSA control device: ' + device)
    return 'hw:' + match.group(1) + ',0'
