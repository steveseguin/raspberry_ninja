from __future__ import annotations

from argparse import ArgumentParser, Namespace
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set


IGNORED_CONFIG_KEYS = {"platform", "auto_start", "custom_video_pipeline", "video_device", "video_format"}
CONFIG_ARG_ALIASES = {"stream_id": "streamid"}
AUDIO_SOURCE_OVERRIDE_ATTRS = {"alsa", "pulse", "audio_pipeline", "noaudio"}
VIDEO_CODEC_OVERRIDE_ATTRS = {
    "h264", "x264", "openh264", "omx", "vp8", "vp9",
    "h265", "hevc", "x265", "av1", "aom", "rav1e", "qsv",
}
VIDEO_SOURCE_OVERRIDE_ATTRS = (
    "test",
    "hdmi",
    "camlink",
    "z1",
    "z1passthru",
    "apple",
    "v4l2",
    "libcamera",
    "rpicam",
    "nvidiacsi",
    "pipeline",
    "video_pipeline",
    "filesrc",
    "filesrc2",
    "pipein",
    "novideo",
)


def load_config_file(path: str) -> Dict[str, Any]:
    """Load one JSON configuration file or raise an actionable exception."""
    config_path = Path(path).expanduser()
    with config_path.open("r", encoding="utf-8-sig") as config_file:
        config = json.load(config_file)
    if not isinstance(config, dict):
        raise ValueError("configuration root must be a JSON object")
    return config


def _explicit_cli_destinations(parser: ArgumentParser, cli_argv: Iterable[str]) -> Set[str]:
    """Return parser destinations explicitly present on the command line."""
    option_destinations = {
        option: action.dest
        for action in parser._actions
        for option in action.option_strings
    }
    destinations: Set[str] = set()
    for token in cli_argv:
        if token == "--":
            break
        if not token.startswith("-"):
            continue
        option = token.split("=", 1)[0]
        destination = option_destinations.get(option)
        if destination is None and parser.allow_abbrev and option.startswith("--"):
            # argparse accepts unique long-option prefixes. Preserve explicit
            # values even when they happen to equal the parser's default.
            matches = [name for name in option_destinations if name.startswith(option)]
            if len(matches) == 1:
                destination = option_destinations[matches[0]]
        if destination:
            destinations.add(destination)
    return destinations


def _arg_is_default(
    args: Namespace,
    parser: ArgumentParser,
    attr: str,
    explicit_cli_args: Set[str],
) -> bool:
    if not hasattr(args, attr):
        return False
    if attr in explicit_cli_args:
        return False
    return getattr(args, attr) == parser.get_default(attr)


def _video_source_has_cli_override(
    args: Namespace,
    parser: ArgumentParser,
    explicit_cli_args: Set[str],
) -> bool:
    for attr in VIDEO_SOURCE_OVERRIDE_ATTRS:
        if attr in explicit_cli_args:
            return True
        if hasattr(args, attr) and getattr(args, attr) != parser.get_default(attr):
            return True
    return False


def _apply_video_source_override(
    args: Namespace,
    parser: ArgumentParser,
    value: Any,
    config: Dict[str, Any],
    explicit_cli_args: Set[str],
) -> None:
    if _video_source_has_cli_override(args, parser, explicit_cli_args):
        return

    if value not in ("test", "libcamera", "v4l2", "custom"):
        parser.error("configuration key 'video_source' must be one of: test, libcamera, v4l2, custom")

    if value == "test" and _arg_is_default(args, parser, "test", explicit_cli_args):
        args.test = True
    elif value == "libcamera" and _arg_is_default(args, parser, "libcamera", explicit_cli_args):
        args.libcamera = True
    elif value == "v4l2" and _arg_is_default(args, parser, "v4l2", explicit_cli_args):
        device = config.get("video_device", "/dev/video0")
        if not isinstance(device, str) or not device.strip():
            parser.error("configuration key 'video_device' must be a non-empty JSON string")
        args.v4l2 = device
    elif value == "custom" and _arg_is_default(args, parser, "video_pipeline", explicit_cli_args):
        custom_pipeline = config.get("custom_video_pipeline")
        if not isinstance(custom_pipeline, str) or not custom_pipeline.strip():
            parser.error("configuration key 'custom_video_pipeline' must be a non-empty JSON string when video_source is custom")
        args.video_pipeline = custom_pipeline


def _validate_config_value(parser: ArgumentParser, action, key: str, value: Any) -> None:
    """Check typed settings before bypassing argparse via setattr."""
    if value is None and action.default is None:
        return
    if action.nargs == 0 and isinstance(action.const, bool):
        if not isinstance(value, bool):
            parser.error(f"configuration key '{key}' must be a JSON boolean (true or false)")
    elif action.type is int:
        if type(value) is not int:
            parser.error(f"configuration key '{key}' must be a JSON integer")
    elif action.type is str:
        if not isinstance(value, str):
            parser.error(f"configuration key '{key}' must be a JSON string")
    elif action.type is float:
        if type(value) not in (int, float):
            parser.error(f"configuration key '{key}' must be a finite JSON number")
        try:
            finite = math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            parser.error(f"configuration key '{key}' must be a finite JSON number")
    if action.choices is not None and value not in action.choices:
        parser.error(f"configuration key '{key}' must be one of: " + ", ".join(map(str, action.choices)))


def apply_config_overrides(
    args: Namespace,
    parser: ArgumentParser,
    config: Dict[str, Any],
    cli_argv: Optional[Iterable[str]] = None,
) -> Namespace:
    explicit_cli_args = _explicit_cli_destinations(parser, cli_argv or ())
    # Snapshot before applying config values, which must not be mistaken for
    # command-line source selections on later iterations.
    cli_video_source = _video_source_has_cli_override(args, parser, explicit_cli_args)
    cli_video_codec = bool(explicit_cli_args & VIDEO_CODEC_OVERRIDE_ATTRS)
    cli_audio_source = bool(explicit_cli_args & AUDIO_SOURCE_OVERRIDE_ATTRS)
    actions = {action.dest: action for action in parser._actions}

    for key, value in config.items():
        if key in IGNORED_CONFIG_KEYS:
            continue

        if key == "audio_enabled":
            if cli_audio_source or "noaudio" in config:
                continue
            if _arg_is_default(args, parser, "noaudio", explicit_cli_args):
                if not isinstance(value, bool):
                    parser.error("configuration key 'audio_enabled' must be a JSON boolean (true or false)")
                if value is False:
                    args.noaudio = True
            continue

        if key == "video_source":
            _apply_video_source_override(args, parser, value, config, explicit_cli_args)
            continue

        target_key = CONFIG_ARG_ALIASES.get(key, key)
        # Prefer current names over legacy aliases independently of JSON order.
        if target_key != key and target_key in config:
            continue
        if cli_audio_source and target_key in AUDIO_SOURCE_OVERRIDE_ATTRS:
            continue
        if cli_video_codec and target_key in VIDEO_CODEC_OVERRIDE_ATTRS:
            continue
        if cli_video_source and target_key in VIDEO_SOURCE_OVERRIDE_ATTRS:
            continue
        if _arg_is_default(args, parser, target_key, explicit_cli_args):
            action = actions.get(target_key)
            if action is not None:
                _validate_config_value(parser, action, key, value)
            setattr(args, target_key, value)

    return args
