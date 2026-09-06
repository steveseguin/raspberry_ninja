#!/usr/bin/env python3
"""Install a small, restartable Raspberry Ninja systemd service.

This helper intentionally targets unattended Raspberry Pi deployments. It
stores runtime options in a non-world-readable JSON file so passwords do not
appear in the unit's ExecStart command.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, Optional, Sequence, Union


SERVICE_NAME_RE = re.compile(r"^[A-Za-z0-9_.@-]+$")
STREAM_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def systemd_quote(value: str, *, executable: bool = False) -> str:
    """Quote a literal command path, accounting for systemd's expansions."""
    if any(character in value for character in ("\n", "\r", "\0")):
        raise ValueError("systemd paths cannot contain newlines or NUL bytes")
    escaped = value.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
    # Environment substitution applies to arguments, not the executable path.
    if not executable:
        escaped = escaped.replace("$", "$$")
    return f'"{escaped}"'


def systemd_setting_path(value: str) -> str:
    """Escape a path used as a non-command systemd setting value."""
    replacements = {
        "%": "%%",
        "\\": "\\x5c",
        " ": "\\x20",
        "\t": "\\x09",
        '"': "\\x22",
    }
    if any(character in value for character in ("\n", "\r", "\0")):
        raise ValueError("systemd paths cannot contain newlines or NUL bytes")
    return "".join(replacements.get(character, character) for character in value)


def render_service(
    *,
    service_name: str,
    description: str,
    user: str,
    repo_dir: Path,
    config_path: Path,
    python_path: Path,
) -> str:
    publish_path = repo_dir / "publish.py"
    # systemd rejects executable paths containing slashes unless absolute.
    # Preserve a venv's symlink path: resolving it can select system Python.
    if not python_path.is_absolute():
        python_path = Path(python_path).absolute()
    return f"""[Unit]
Description={description}
Wants=network-online.target
After=network-online.target
StartLimitIntervalSec=120
StartLimitBurst=10

[Service]
Type=simple
User={user}
WorkingDirectory={systemd_setting_path(str(repo_dir))}
Environment=PYTHONUNBUFFERED=1
Environment=DISPLAY=
Environment=WAYLAND_DISPLAY=
ExecStart={systemd_quote(str(python_path), executable=True)} {systemd_quote(str(publish_path))} --config {systemd_quote(str(config_path))}
Restart=always
RestartSec=5
TimeoutStopSec=20
UMask=0077
SyslogIdentifier={service_name}

[Install]
WantedBy=multi-user.target
"""


def build_config(args: argparse.Namespace) -> Dict[str, Any]:
    config: Dict[str, Any] = {"password": args.password}
    if args.stun_server is not None:
        config["stun_server"] = args.stun_server
    if args.role == "receiver":
        config.update(
            {
                "view": args.stream_id,
                "stretch_display": args.stretch_display,
                "noaudio": args.no_audio,
                "viewer_retry_initial": args.viewer_retry_initial,
                "viewer_retry_short": args.viewer_retry_short,
                "viewer_retry_long": args.viewer_retry_long,
            }
        )
        return config

    config.update(
        {
            "streamid": args.stream_id,
            "width": args.width,
            "height": args.height,
            "framerate": args.framerate,
            "bitrate": args.bitrate,
            "noaudio": args.audio_device is None,
            "rpi": True,
        }
    )
    config[args.codec] = True
    if args.test_source:
        config["test"] = True
    elif args.libcamera:
        config["libcamera"] = True
    elif args.rpicam:
        config["rpicam"] = True
    else:
        # The service runs from repo_dir, which may differ from the installer's
        # working directory. Keep stable device symlinks rather than resolving.
        config["v4l2"] = str(Path(args.camera).absolute())
        if args.raw or args.format in {"YUYV", "YUY2"}:
            config["raw"] = True
        if args.format:
            config["format"] = "YUY2" if args.format == "YUYV" else args.format
    if args.audio_device:
        config["alsa"] = args.audio_device
        config["audiobitrate"] = args.audio_bitrate
    return config


def _finite_non_negative(parser: argparse.ArgumentParser, value: float, option: str) -> None:
    import math

    if not math.isfinite(value) or value < 0:
        parser.error(f"{option} must be a finite, non-negative number")


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not STREAM_ID_RE.fullmatch(args.stream_id):
        parser.error("--stream-id must contain 1-128 letters, numbers, underscores, or hyphens")
    if not SERVICE_NAME_RE.fullmatch(args.service_name):
        parser.error("--service-name contains unsupported characters")
    if args.service_name.startswith(('-', '@')):
        parser.error("--service-name must not start with '-' or '@'")
    if len(args.service_name) > 247:
        parser.error("--service-name must be at most 247 characters before the .service suffix")
    if args.service_name.find('@') == len(args.service_name) - 1:
        parser.error("--service-name must include an instance after '@', for example camera@front")
    if args.role == "receiver":
        _finite_non_negative(parser, args.viewer_retry_initial, "--viewer-retry-initial")
        _finite_non_negative(parser, args.viewer_retry_short, "--viewer-retry-short")
        _finite_non_negative(parser, args.viewer_retry_long, "--viewer-retry-long")
    elif not (args.test_source or args.libcamera or args.rpicam):
        if not args.camera or not args.camera.strip():
            parser.error("--camera must be a non-empty device path")
        camera = Path(args.camera)
        if camera.is_dir():
            parser.error("--camera must point to a device, not a directory")
        if not camera.exists() and not args.allow_missing_device:
            parser.error(
                f"camera does not exist: {camera}; attach it or use --allow-missing-device"
            )
    if args.role == "sender":
        if args.audio_device is not None and not args.audio_device.strip():
            parser.error("--audio-device must be a non-empty ALSA device name; omit it to disable audio")
        for value, option in (
            (args.width, "--width"),
            (args.height, "--height"),
            (args.framerate, "--framerate"),
            (args.bitrate, "--bitrate"),
            (args.audio_bitrate, "--audio-bitrate"),
        ):
            if value <= 0:
                parser.error(f"{option} must be greater than zero")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install an unattended Raspberry Ninja receiver or sender service."
    )
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--user", default=os.environ.get("SUDO_USER") or os.environ.get("USER"))
    parser.add_argument("--python", type=Path, default=Path("/usr/bin/python3"))
    parser.add_argument("--password", help="shared VDO.Ninja password; prompts when omitted")
    parser.add_argument("--stun-server", help="STUN URL, or false to disable it")
    parser.add_argument("--dry-run", action="store_true", help="print generated files without installing")
    parser.add_argument("--no-start", action="store_true", help="install and enable without starting now")

    roles = parser.add_subparsers(dest="role", required=True)
    receiver = roles.add_parser("receiver", help="install an HDMI receiver")
    receiver.add_argument("--stream-id", required=True)
    receiver.add_argument("--service-name", default="raspberry-ninja-viewer")
    receiver.add_argument("--no-audio", action="store_true")
    receiver.add_argument(
        "--stretch-display",
        action="store_true",
        help="stretch to fill the display instead of preserving aspect ratio",
    )
    receiver.add_argument("--viewer-retry-initial", type=float, default=15.0)
    receiver.add_argument("--viewer-retry-short", type=float, default=45.0)
    receiver.add_argument("--viewer-retry-long", type=float, default=180.0)

    sender = roles.add_parser("sender", help="install a camera or test-source sender")
    sender.add_argument("--stream-id", required=True)
    sender.add_argument("--service-name", default="raspberry-ninja-sender")
    source = sender.add_mutually_exclusive_group(required=True)
    source.add_argument("--camera", help="V4L2 device; prefer /dev/v4l/by-id/... paths")
    source.add_argument("--test-source", action="store_true")
    source.add_argument("--libcamera", action="store_true", help=argparse.SUPPRESS)
    source.add_argument("--rpicam", action="store_true", help=argparse.SUPPRESS)
    sender.add_argument("--allow-missing-device", action="store_true")
    sender.add_argument("--format", choices=("H264", "MJPG", "YUYV", "YUY2"))
    sender.add_argument("--raw", action="store_true", help=argparse.SUPPRESS)
    sender.add_argument("--codec", choices=("h264", "vp8"), default="h264")
    sender.add_argument("--width", type=int, default=640)
    sender.add_argument("--height", type=int, default=360)
    sender.add_argument("--framerate", type=int, default=15)
    sender.add_argument("--bitrate", type=int, default=500)
    sender.add_argument("--audio-device", help="ALSA capture name, for example hw:C920,0")
    sender.add_argument("--audio-bitrate", type=int, default=48)
    return parser


def _write_atomic(path: Path, content: Union[str, bytes], mode: int, uid: int, gid: int) -> None:
    # Exclusive creation avoids following stale symlinks or sharing staging
    # files with another run. tempfile starts with mode 0600 before any secrets
    # are written, regardless of the caller's umask.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent,
            # Do not extend the destination name beyond the filesystem limit.
            prefix=".raspberry-ninja-", suffix=".tmp", delete=False,
        ) as staging:
            temporary = Path(staging.name)
            staging.write(content.encode("utf-8") if isinstance(content, str) else content)
        os.chmod(temporary, mode)
        os.chown(temporary, uid, gid)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def verify_service_started(
    unit_name: str,
    *,
    runner=subprocess.run,
    sleep=time.sleep,
) -> None:
    """Confirm that a newly configured service survives its initial startup."""
    sleep(2)
    result = runner(
        ["systemctl", "is-active", "--quiet", unit_name],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{unit_name} did not start correctly; run "
            f"journalctl -u {unit_name} -n 30 --no-pager"
        )


def install(args: argparse.Namespace) -> None:
    try:
        import pwd
    except ImportError:
        raise RuntimeError("installation requires Linux with systemd")

    if os.geteuid() != 0:
        raise RuntimeError("installation requires sudo; use --dry-run to preview")
    if not args.user:
        raise RuntimeError("could not determine service user; pass --user")
    try:
        account = pwd.getpwnam(args.user)
    except KeyError as exc:
        raise RuntimeError(f"service user does not exist: {args.user}") from exc

    repo_dir = args.repo.resolve()
    if not (repo_dir / "publish.py").is_file():
        raise RuntimeError(f"publish.py was not found under {repo_dir}")
    if not args.python.is_file():
        raise RuntimeError(f"Python interpreter was not found: {args.python}")

    config_dir = Path("/etc/raspberry-ninja")
    config_path = config_dir / f"{args.service_name}.json"
    unit_path = Path("/etc/systemd/system") / f"{args.service_name}.service"
    description = (
        "Raspberry Ninja unattended HDMI receiver"
        if args.role == "receiver"
        else "Raspberry Ninja unattended camera sender"
    )
    config_text = json.dumps(build_config(args), indent=2, sort_keys=True) + "\n"
    unit_text = render_service(
        service_name=args.service_name,
        description=description,
        user=args.user,
        repo_dir=repo_dir,
        config_path=config_path,
        python_path=args.python,
    )

    previous = {
        path: (path.read_bytes(), path.stat()) if path.exists() else None
        for path in (config_path, unit_path)
    }
    directory_stat = config_dir.stat() if config_dir.exists() else None
    written = []
    try:
        # Services may run under different groups. Allow traversal of the shared
        # directory without exposing its listing; each file restricts readers.
        config_dir.mkdir(mode=0o711, parents=True, exist_ok=True)
        os.chmod(config_dir, 0o711)
        os.chown(config_dir, 0, 0)
        _write_atomic(config_path, config_text, 0o640, 0, account.pw_gid)
        written.append(config_path)
        _write_atomic(unit_path, unit_text, 0o644, 0, 0)
        written.append(unit_path)
        subprocess.run(["systemd-analyze", "verify", str(unit_path)], check=True)
    except Exception as error:
        rollback_errors = []
        for path in reversed(written):
            try:
                saved = previous[path]
                if saved is None:
                    path.unlink(missing_ok=True)
                else:
                    content, metadata = saved
                    _write_atomic(path, content, metadata.st_mode & 0o7777,
                                  metadata.st_uid, metadata.st_gid)
            except Exception as rollback_error:
                rollback_errors.append(f"{path}: {rollback_error}")
        try:
            if directory_stat is not None:
                os.chown(config_dir, directory_stat.st_uid, directory_stat.st_gid)
                os.chmod(config_dir, directory_stat.st_mode & 0o7777)
            elif config_dir.exists():
                config_dir.rmdir()
        except Exception as rollback_error:
            rollback_errors.append(f"{config_dir}: {rollback_error}")
        if rollback_errors:
            raise RuntimeError(
                f"Installation failed: {error}; rollback incomplete: "
                + "; ".join(rollback_errors)
            ) from error
        raise

    subprocess.run(["systemctl", "daemon-reload"], check=True)
    unit_name = f"{args.service_name}.service"
    subprocess.run(["systemctl", "enable", unit_name], check=True)
    if not args.no_start:
        # `enable --now` does not restart an already-running unit, so a
        # reconfiguration would otherwise keep using stale settings.
        subprocess.run(["systemctl", "restart", unit_name], check=True)
        verify_service_started(unit_name)
    print(f"Installed {args.service_name}.service")
    print(f"Config: {config_path}")
    print(f"Logs: journalctl -u {args.service_name}.service -f")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)
    if args.password is None:
        if args.dry_run:
            parser.error("--password is required with --dry-run")
        args.password = getpass.getpass("Shared VDO.Ninja password (or false for a test): ")
    if args.password == "":
        parser.error("password cannot be empty; use the literal value false only for a test")
    validate_args(parser, args)

    repo_dir = args.repo.resolve()
    config_path = Path("/etc/raspberry-ninja") / f"{args.service_name}.json"
    description = (
        "Raspberry Ninja unattended HDMI receiver"
        if args.role == "receiver"
        else "Raspberry Ninja unattended camera sender"
    )
    if args.dry_run:
        print(f"# {config_path}")
        print(json.dumps(build_config(args), indent=2, sort_keys=True))
        print(f"\n# /etc/systemd/system/{args.service_name}.service")
        print(
            render_service(
                service_name=args.service_name,
                description=description,
                user=args.user or "YOUR_USER",
                repo_dir=repo_dir,
                config_path=config_path,
                python_path=args.python,
            ),
            end="",
        )
        return 0

    install(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
