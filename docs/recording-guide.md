# Recording guide

Recording is a receive operation. `--record` and `--record-room` pull remote VDO.Ninja streams to disk; they do not publish the local camera.

## Single-stream recording

```bash
python3 -u publish.py \
  --record STREAM_ID \
  --password false
```

Audio is recorded by default. Add `--noaudio` for video only.

The file container follows the negotiated codec:

| Incoming media | Normal recording output | Processing |
| --- | --- | --- |
| H.264 video | `.ts` MPEG-TS | Depayload and remux |
| VP8 or VP9 video | `.webm` WebM | WebM-compatible path |
| Opus audio | separate `_audio.webm` WebM | Depayload and remux |

Filenames include stream identifiers and timestamps. Read the startup log for the exact paths; do not assume that a user-supplied `.webm` suffix survives when the selected video container is MPEG-TS.

Stop with Ctrl+C and let GStreamer finalize the files. A non-empty file is not proof of a valid recording; validate it as described below.

## Room recording

Record every participant in a room:

```bash
python3 -u publish.py \
  --room ROOM_NAME \
  --record-room \
  --password false
```

Limit recording to selected stream IDs:

```bash
python3 -u publish.py \
  --room ROOM_NAME \
  --record-room \
  --record-streams "camera-one,camera-two" \
  --password false
```

Each participant is handled separately. Expect codec-appropriate video files and separate audio files rather than one mixed room file.

## HLS recording

The validated compatibility path is the splitmux backend:

```bash
python3 -u publish.py \
  --record STREAM_ID \
  --hls --hls-splitmux \
  --password false
```

This produces an `.m3u8` playlist and numbered `.ts` MPEG-TS segments. H.264 is used for video and AAC for audio; non-H.264 input is transcoded and can be expensive on small boards.

Serve the current recording directory with the built-in server:

```bash
python3 -u publish.py \
  --record STREAM_ID \
  --hls --hls-splitmux \
  --webserver 8080 \
  --password false
```

Open the playlist named in the log through port 8080. Browser-native HLS support varies; the included [`tools/play_hls.html`](../tools/play_hls.html) can be used with the helper server when needed.

`--hls` without `--hls-splitmux` keeps the older manual backend for platform compatibility. It produced empty segments in testing on GStreamer 1.18, so it is not the recommended general-purpose path. Do not remove it without testing the platforms that still depend on it.

## Validate recordings

Identify the real container:

```bash
gst-typefind-1.0 recording.ts
ffprobe -hide_banner recording.ts
ffprobe -hide_banner recording_audio.webm
```

Decode without requiring a display or speaker:

```bash
gst-launch-1.0 -q filesrc location=recording.ts ! decodebin ! fakesink
gst-launch-1.0 -q filesrc location=recording_audio.webm ! decodebin ! fakesink
```

For HLS, confirm all three layers:

```bash
test -s recording.m3u8
grep -v '^#' recording.m3u8
gst-typefind-1.0 recording_00000.ts
gst-launch-1.0 -q filesrc location=recording_00000.ts ! decodebin ! fakesink
```

The segment must type-find as MPEG-TS and the playlist must reference existing, non-empty segments.

## Combine separate audio and video

Install FFmpeg, then combine a known pair:

```bash
python3 tools/combine_recordings.py video_file audio_file combined.mp4
```

With no arguments, the tool scans the current directory for timestamp-matched pairs. It recognizes current H.264 `.ts`, VP8/VP9 `.webm`/`.mkv`, and `_audio.webm` outputs, plus legacy `_audio.wav` and `_audio.ts` files:

```bash
python3 tools/combine_recordings.py
```

The tool re-encodes video to H.264 and audio to AAC while compensating for differing stream start timestamps. Keep the originals until the combined file has been inspected and decoded successfully.

## Resource planning

Direct H.264/Opus remuxing is much lighter than decoding and transcoding. HLS conversion, VP8/VP9 re-encoding, several room participants, or simultaneous publishing can exceed a Pi Zero 2 W's practical memory and CPU budget. Test one stream first and monitor:

```bash
watch -n 2 'free -h; ps -o pid,rss,%cpu,%mem,etime,cmd -C python3'
```

Also monitor disk space and write rate. An 8 GB card is suitable for the runtime and short tests, not unattended long-term recording.
