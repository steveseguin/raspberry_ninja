from __future__ import annotations

from argparse import ArgumentParser, Namespace
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set


IGNORED_CONFIG_KEYS = {"platform", "auto_start", "custom_video_pipeline", "video_device", "video_format"}
CONFIG_ARG_ALIASES = {"stream_id": "streamid"}
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
    with config_path.open("r", encoding="utf-8") as config_file:
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
        if not token.startswith("-"):
            continue
        option = token.split("=", 1)[0]
        destination = option_destinations.get(option)
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

    if value == "test" and _arg_is_default(args, parser, "test", explicit_cli_args):
        args.test = True
    elif value == "libcamera" and _arg_is_default(args, parser, "libcamera", explicit_cli_args):
        args.libcamera = True
    elif value == "v4l2" and _arg_is_default(args, parser, "v4l2", explicit_cli_args):
        args.v4l2 = config.get("video_device", "/dev/video0")
    elif value == "custom" and _arg_is_default(args, parser, "video_pipeline", explicit_cli_args):
        custom_pipeline = config.get("custom_video_pipeline")
        if custom_pipeline:
            args.video_pipeline = custom_pipeline


def apply_config_overrides(
    args: Namespace,
    parser: ArgumentParser,
    config: Dict[str, Any],
    cli_argv: Optional[Iterable[str]] = None,
) -> Namespace:
    explicit_cli_args = _explicit_cli_destinations(parser, cli_argv or ())

    for key, value in config.items():
        if key in IGNORED_CONFIG_KEYS:
            continue

        if key == "audio_enabled":
            if value is False and _arg_is_default(args, parser, "noaudio", explicit_cli_args):
                args.noaudio = True
            continue

        if key == "video_source":
            _apply_video_source_override(args, parser, value, config, explicit_cli_args)
            continue

        target_key = CONFIG_ARG_ALIASES.get(key, key)
        if _arg_is_default(args, parser, target_key, explicit_cli_args):
            setattr(args, target_key, value)

    return args
