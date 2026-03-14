from __future__ import annotations

from argparse import ArgumentParser, Namespace
from typing import Any, Dict


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


def _arg_is_default(args: Namespace, parser: ArgumentParser, attr: str) -> bool:
    if not hasattr(args, attr):
        return False
    return getattr(args, attr) == parser.get_default(attr)


def _video_source_has_cli_override(args: Namespace, parser: ArgumentParser) -> bool:
    for attr in VIDEO_SOURCE_OVERRIDE_ATTRS:
        if hasattr(args, attr) and getattr(args, attr) != parser.get_default(attr):
            return True
    return False


def _apply_video_source_override(
    args: Namespace,
    parser: ArgumentParser,
    value: Any,
    config: Dict[str, Any],
) -> None:
    if _video_source_has_cli_override(args, parser):
        return

    if value == "test" and _arg_is_default(args, parser, "test"):
        args.test = True
    elif value == "libcamera" and _arg_is_default(args, parser, "libcamera"):
        args.libcamera = True
    elif value == "v4l2" and _arg_is_default(args, parser, "v4l2"):
        args.v4l2 = config.get("video_device", "/dev/video0")
    elif value == "custom" and _arg_is_default(args, parser, "video_pipeline"):
        custom_pipeline = config.get("custom_video_pipeline")
        if custom_pipeline:
            args.video_pipeline = custom_pipeline


def apply_config_overrides(
    args: Namespace,
    parser: ArgumentParser,
    config: Dict[str, Any],
) -> Namespace:
    for key, value in config.items():
        if key in IGNORED_CONFIG_KEYS:
            continue

        if key == "audio_enabled":
            if value is False and _arg_is_default(args, parser, "noaudio"):
                args.noaudio = True
            continue

        if key == "video_source":
            _apply_video_source_override(args, parser, value, config)
            continue

        target_key = CONFIG_ARG_ALIASES.get(key, key)
        if _arg_is_default(args, parser, target_key):
            setattr(args, target_key, value)

    return args
