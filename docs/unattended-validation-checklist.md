# Unattended deployment validation checklist

Use this checklist after the basic publisher or receiver works. It is designed to catch failures that a brief local preview misses.

## Record the exact platform

Save these results with the deployment notes:

```bash
cat /proc/device-tree/model 2>/dev/null; echo
cat /etc/os-release
uname -a
python3 --version
gst-launch-1.0 --version
gst-inspect-1.0 webrtcbin kmssink v4l2h264enc
v4l2-ctl --list-devices 2>/dev/null
v4l2-ctl -d /dev/video0 --list-formats-ext 2>/dev/null
arecord -l 2>/dev/null
free -h
vcgencmd get_throttled 2>/dev/null
```

A result on one Pi, OS, or GStreamer version does not validate another. Record whether the camera path is raw, MJPEG, native H.264, Pi V4L2, `libcamera`, `rpicam`, NVIDIA, or Rockchip-specific.

## Receiver acceptance

Confirm all of the following:

- HDMI is connected before boot and the selected DRM mode matches the monitor's advertised mode.
- With no sender, the display is idle/blank and the service remains active.
- Starting a sender produces video on the Pi-connected display, not an SSH-forwarded window.
- Source aspect ratio is preserved unless stretch was explicitly selected.
- HDMI audio is audible and routed to the intended ALSA device.
- Stopping the sender returns the receiver to idle; restarting it reconnects without SSH or a reboot.
- A receiver connection remains healthy for longer than 30 seconds and logs periodic ping/pong health.

## Sender acceptance

Confirm the remote endpoint, not just a local preview, receives:

- the requested codec, resolution, and frame rate;
- non-zero and reasonably stable bitrate;
- microphone audio when enabled;
- 0% or acceptably low raw packet loss on a healthy LAN;
- continued media after at least one viewer disconnect/reconnect.

For native camera H.264, verify that the log says the camera stream is passed through without re-encoding. Do not infer native H.264 support from a camera model name alone.

## Failure and recovery checks

Run these deliberately, one at a time:

1. Stop and restart the remote sender.
2. Restart the Raspberry Ninja service.
3. Reboot the Pi with HDMI already attached.
4. Reboot once with the USB camera and powered hub attached.
5. Temporarily use an invalid camera path and confirm installation rejects it, unless `--allow-missing-device` was explicitly chosen.
6. Pass invalid retry values such as a negative number and confirm startup rejects them.
7. Confirm a missing or malformed `--config` file exits with an error instead of starting a default publisher.

Physically unplugging power, HDMI, or USB can damage files or devices. Only perform cable-removal tests when the hardware and storage risk is acceptable.

## Soak observations

For receive-only use, run at least a few hours. For two-way use, run both services together:

```bash
watch -n 2 'free -h; ps -o pid,rss,%cpu,%mem,etime,cmd -C python3; vcgencmd measure_temp 2>/dev/null; vcgencmd get_throttled 2>/dev/null'
```

Also inspect logs:

```bash
journalctl -u raspberry-ninja-viewer.service --since today --no-pager
journalctl -u raspberry-ninja-return.service --since today --no-pager
```

Reject the deployment if RSS or swap grows continuously, throttling is recorded, the service repeatedly restarts, media regularly falls to zero bitrate, or recovery requires manual intervention. A Zero 2 W should retain meaningful available memory; there is no single safe number for every OS image, but a steady downward trend is not acceptable.

## Security and maintenance

- Replace `--password false` with a strong shared password before Internet use.
- Keep the config under `/etc/raspberry-ninja/` non-world-readable.
- Prefer SSH keys and disable password SSH when practical.
- Schedule OS and repository updates as supervised maintenance, then repeat the short recovery tests.
- Do not perform package upgrades during a live event or with unstable power.
