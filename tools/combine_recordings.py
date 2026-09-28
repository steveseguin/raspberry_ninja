#!/usr/bin/env python3
"""
Combine async audio and video recordings with proper timestamp-based synchronization
"""

import argparse
import asyncio
import math
import os
import sys
import json
import tempfile
from pathlib import Path


VIDEO_EXTENSIONS = {'.ts', '.webm', '.mkv'}
AUDIO_EXTENSIONS = {'.webm', '.wav', '.ts', '.mka'}


def recording_identity(filepath, audio=False):
    """Return a timestamp-independent recording identity for a generated filename."""
    path = Path(filepath)
    stem = path.stem
    if audio:
        if not stem.endswith('_audio') or path.suffix.lower() not in AUDIO_EXTENSIONS:
            return None
        stem = stem[:-len('_audio')]
    elif stem.endswith('_audio') or path.suffix.lower() not in VIDEO_EXTENSIONS:
        return None

    parts = stem.split('_')
    timestamp_index = None
    # Room recordings append eight UUID hex characters, which can be all digits.
    # Do not mistake that suffix for the preceding Unix timestamp.
    end = len(parts)
    if (end >= 3 and len(parts[-1]) == 8
            and all(c in '0123456789abcdefABCDEF' for c in parts[-1])
            and parts[-2].isdigit()):
        end -= 1
    for index in range(end - 1, -1, -1):
        try:
            int(parts[index])
        except ValueError:
            continue
        timestamp_index = index
        break

    if timestamp_index is None:
        return None
    timestamp = int(parts[timestamp_index])
    identity_parts = parts[:timestamp_index] + parts[timestamp_index + 1:]
    identity = '_'.join(identity_parts)
    if not identity:
        return None
    return identity, timestamp


def discover_recording_pairs(directory='.', tolerance_seconds=5):
    """Find current and legacy video/audio recording pairs in a directory."""
    directory = Path(directory)
    videos = []
    audio_files = []
    for path in directory.iterdir():
        if not path.is_file() or path.name.startswith('combined_'):
            continue
        video_info = recording_identity(path, audio=False)
        if video_info:
            videos.append((path, *video_info))
        audio_info = recording_identity(path, audio=True)
        if audio_info:
            audio_files.append((path, *audio_info))

    pairs = []
    used_audio = set()
    for video_path, video_identity, video_timestamp in sorted(videos):
        candidates = [
            (abs(audio_timestamp - video_timestamp), audio_path)
            for audio_path, audio_identity, audio_timestamp in audio_files
            if audio_path not in used_audio
            and audio_identity == video_identity
            and abs(audio_timestamp - video_timestamp) <= tolerance_seconds
        ]
        if not candidates:
            continue
        _, audio_path = min(candidates, key=lambda candidate: (candidate[0], str(candidate[1])))
        used_audio.add(audio_path)
        pairs.append((video_path, audio_path))
    return pairs


async def get_file_info(filepath):
    """Probe media without treating invalid inputs as zero-timestamp recordings."""
    process = await asyncio.create_subprocess_exec(
        'ffprobe', '-v', 'error', '-print_format', 'json',
        '-show_format', '-show_streams', str(filepath),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await process.communicate()
    finally:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.communicate()
    if process.returncode:
        raise ValueError(f"Cannot inspect {filepath}: {stderr.decode(errors='replace').strip()}")
    return json.loads(stdout.decode())


def stream_start(info, kind):
    stream = next((s for s in info.get('streams', []) if s.get('codec_type') == kind), None)
    if stream is None:
        raise ValueError(f"Input has no {kind} track")
    value = stream.get('start_time', '0')
    start = 0.0 if value in (None, 'N/A') else float(value)
    if not math.isfinite(start):
        raise ValueError(f"Invalid {kind} start timestamp")
    return start


async def get_stream_start_time(filepath):
    """Return the first audio/video track's start time (legacy helper)."""
    info = await get_file_info(filepath)
    kind = next((s.get('codec_type') for s in info.get('streams', [])
                 if s.get('codec_type') in ('video', 'audio')), 'video')
    return stream_start(info, kind)


async def combine_files(video_file, audio_file, output_file, audio_offset=None):
    """Align tracks on their common timestamp timeline and replace only on success."""
    temporary = None
    process = None
    try:
        video_file, audio_file, output_file = (Path(p).resolve() for p in
                                               (video_file, audio_file, output_file))
        if output_file in (video_file, audio_file):
            raise ValueError('Output must differ from both input files')
        print(f"\nCombining {video_file.name} + {audio_file.name} -> {output_file.name}")
        video_info = await get_file_info(video_file)
        audio_info = await get_file_info(audio_file)
        video_start = stream_start(video_info, 'video')
        audio_start = stream_start(audio_info, 'audio')
        if audio_offset is not None:
            if not math.isfinite(audio_offset):
                raise ValueError('--audio-offset must be a finite number of seconds')
            video_start, audio_start = 0.0, audio_offset
        else:
            video_ts = 'mpegts' in video_info.get('format', {}).get('format_name', '').split(',')
            audio_ts = 'mpegts' in audio_info.get('format', {}).get('format_name', '').split(',')
            if video_ts != audio_ts:
                raise ValueError('MPEG-TS and other containers can use different timestamp origins. '
                                 'Set --audio-offset SECONDS; 0 aligns the first samples, '
                                 'positive values delay audio, negative values delay video.')
        origin = min(video_start, audio_start)
        video_delay, audio_delay = video_start - origin, audio_start - origin
        print(f"  Video start: {video_start:.3f}s; audio start: {audio_start:.3f}s")

        # Each demuxer can normalize its input timestamps separately. Reset both
        # explicitly, then pad the LATER track to preserve their relative timing.
        video_filter = '[0:v:0]setpts=PTS-STARTPTS'
        audio_filter = '[1:a:0]asetpts=PTS-STARTPTS'
        if video_delay > 0:
            video_filter += f',tpad=start_duration={video_delay:.6f}:start_mode=add:color=black'
        if audio_delay > 0:
            audio_filter += f',adelay=delays={audio_delay * 1000:.3f}:all=1'
        filters = video_filter + '[video];' + audio_filter + '[audio]'
        fd, name = tempfile.mkstemp(prefix='.' + output_file.stem + '-',
                                    suffix=output_file.suffix, dir=output_file.parent)
        os.close(fd)
        temporary = Path(name)
        process = await asyncio.create_subprocess_exec(
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
            '-i', str(video_file), '-i', str(audio_file),
            '-filter_complex', filters, '-map', '[video]', '-map', '[audio]',
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'aac', '-b:a', '192k', '-shortest', str(temporary),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, stderr = await process.communicate()
        if process.returncode:
            raise ValueError(stderr.decode(errors='replace').strip() or 'FFmpeg failed')
        info = await get_file_info(temporary)
        stream_start(info, 'video')
        stream_start(info, 'audio')
        temporary.replace(output_file)
        print(f"  Success: {output_file.stat().st_size:,} bytes; audio and video verified")
        return True
    except (OSError, ValueError) as exc:
        print(f"  Merge failed: {exc}", file=sys.stderr)
        return False
    finally:
        if process is not None and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.communicate()
        if temporary is not None:
            temporary.unlink(missing_ok=True)


async def main(directory='.', audio_offset=None):
    """Find and combine matching audio/video pairs"""
    print("=== Combine Audio/Video Recordings (v2 - Timestamp-based sync) ===\n")

    pairs = discover_recording_pairs(directory)
    if not pairs:
        print("No files to combine!")
        return 0

    print(f"Found {len(pairs)} matching audio/video pair(s)\n")

    combined_count = 0
    failed_count = 0
    directory = Path(directory)
    for video_file, audio_file in pairs:
        output_file = directory / f"combined_{video_file.stem}.mp4"
        if output_file.exists():
            print(f"Skipping {output_file} - already exists")
            continue
        success = await combine_files(video_file, audio_file, output_file, audio_offset=audio_offset)
        if success:
            combined_count += 1
        else:
            failed_count += 1

    print(f"\n=== Summary ===")
    print(f"Combined {combined_count} file pairs")

    # List combined files
    combined_files = sorted(directory.glob("combined_*.mp4"))
    if combined_files:
        print("\nCombined files:")
        for cf in combined_files:
            size = os.path.getsize(cf)
            print(f"  {cf} ({size:,} bytes)")
    if failed_count:
        raise ValueError(f'{failed_count} recording pair(s) failed to merge')
    return combined_count


def cli(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio-offset', type=float, metavar='SECONDS',
                        help='override container timestamps: positive delays audio, negative delays video; 0 aligns first samples')
    parser.add_argument('files', nargs='*', metavar='FILE',
                        help='video_file audio_file output_file; omit to discover pairs')
    args = parser.parse_args(argv)
    if args.audio_offset is not None and not math.isfinite(args.audio_offset):
        parser.error('--audio-offset must be a finite number of seconds')
    if args.files and len(args.files) != 3:
        parser.error('provide video_file audio_file output_file, or no arguments')
    try:
        if args.files:
            return 0 if asyncio.run(combine_files(*args.files, audio_offset=args.audio_offset)) else 1
        asyncio.run(main(audio_offset=args.audio_offset))
        return 0
    except (OSError, ValueError) as exc:
        print(f'Merge failed: {exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(cli())
