## Jetson Nano Media Toolchain Installers

These scripts target the NVIDIA Jetson Nano 2 GB / 4 GB (Maxwell) platform running JetPack 4.x (L4T 32.7.x) and keep the NVIDIA‐patched `tegra` kernel intact while refreshing the userland media stack in `/usr/local`.

### Script Summary

| Script | Purpose | Typical Use |
| --- | --- | --- |
| `installer.sh` | End‑to‑end rebuild of Python, codec libraries, FFmpeg, GStreamer, libcamera, and supporting deps. Includes optional `INCLUDE_DISTRO_UPGRADE=1` block for legacy rootfs upgrades. | Freshly flashed Jetson Nano image or heavily drifted systems that need a clean rebuild. |
| `toolchain_update.sh` | Thin wrapper around `installer.sh` that keeps `INCLUDE_DISTRO_UPGRADE=0` (skip distro upgrade). | Updating an existing Ubuntu 20.04‑based Jetson image—e.g., the customized system captured in this repo. |

Both scripts expect `sudo` access (password `ninja` in the lab environment) and will rebuild components under `/usr/local`, leaving the system packages untouched so the NVIDIA kernel and drivers continue to work.

### Components Installed

- **Python 3.11.9** with shared libs, PGO/LTO, and upgraded `pip/setuptools/wheel`. Installs Meson 1.4.1, Ninja 1.13, scikit-build, Jinja2, PyYAML, Mako, ply, websockets, pycairo.
- **Codec libraries** rebuilt from source with multithreaded support:
  - `fdk-aac` (master), `dav1d` 1.3.0, `kvazaar` 2.3.0 (CMake shared libs), `x264` stable, `libvpx` 1.13.1 (`--enable-multithread --runtime-cpu-detect`), `srt` 1.5.3 (CMake `ENABLE_SHARED=ON`), `libsrtp` 2.6.0 (shared).
- **FFmpeg n7.0** linked against the refreshed codecs plus PulseAudio, OMX, OpenSSL, SRT/RTMP, and amrwb/amrnb encoders; built shared-only with pthreads.
- **GLib 2.80.5**, **GObject-Introspection 1.80.1**, **usrsctp**, **libnice 0.1.21**, **libsrtp 2.6.0**, **libcamera v0.3.2** (GStreamer support enabled; Python bindings off).
- **GStreamer 1.26.7** via Meson with introspection enabled so GIR/typelib outputs land under `/usr/local` for Python `gi` usage. We continue to disable `libav`, `qt5/qt6`, `rpicamsrc`, `ptp-helper`, VA/MSE plugins to dodge Jetson linker issues while still picking up the WebRTC jitterbuffer retransmission toggles required for RTX.
- **NVIDIA gstnv* plugins** are backed up to `~/nvgst` before the rebuild and restored into `/usr/local/lib/aarch64-linux-gnu/gstreamer-1.0/` after installation to retain hardware acceleration.

### When to Use Which Flow

- **Fresh Jetson Nano (JetPack 4.x) images**: run `installer.sh`. Leave `INCLUDE_DISTRO_UPGRADE=0` unless you explicitly want to attempt the legacy in-place distro upgrade (not recommended for stable setups).
- **Customized Ubuntu 20.04 Jetson image**: run `toolchain_update.sh`. This skips the distro-upgrade block and mirrors the manual rebuild that now targets Python 3.11.9, FFmpeg n7.0, and GStreamer 1.26.7 on the current system.
- **Maintenance updates**: rerun `toolchain_update.sh` after future script tweaks; it reclones/builds everything cleanly each time, ensuring consistent `/usr/local` outputs.

### Prerequisites & Warnings

- Confirm `uname -a` shows `tegra` (NVIDIA kernel). Do **not** install generic Ubuntu kernels.
- Ensure ≥ 40 GB free disk space and several GB of swap (the Nano’s zram helps but long builds benefit from extra swap if available).
- Stable internet is required for git and tarball downloads.
- `/usr/local` takes precedence in `PATH`, `PKG_CONFIG_PATH`, `LD_LIBRARY_PATH`; be mindful of future package installs that might collide.
- GStreamer validator (`gst-validate`) and VA/MSE plugins are disabled by default. If you restore them, ensure the required dependencies (gst-devtools, newer `libva`) are present or the build will fail.

### Post-Install Smoke Tests

After a successful run:

```bash
python3.11 --version
python3.11 -m pip list | head
ffmpeg -codecs | grep -E '264|vp9|av1'
gst-launch-1.0 --version
gst-inspect-1.0 nvarguscamerasrc
```

Run representative GStreamer pipelines (e.g., your `publish.py`) to verify multithreaded decode behavior and GPU plugin loading. Investigate any remaining warnings about `gst-validate`, `libgstmse.so`, or `vaCopy`—they indicate optional plugins missing runtime dependencies (typically gst-devtools or a newer VA stack).

### Known Limitations

- GStreamer still omits optional `gst-validate`/MSE/VA plugins; enable them only after providing the required dependencies (gst-devtools, updated libva).
- libcamera warns about kernels < 5.0; this is expected on JetPack 4.x and can be ignored unless you migrate to a newer L4T release.
- The scripts assume a Jetson Nano; other Jetson models may require additional acceleration plugins or kernel headers.

Refer to `AGENTS.md` for an up-to-date progress log, pending tasks, and validation notes derived from the current deployment.
