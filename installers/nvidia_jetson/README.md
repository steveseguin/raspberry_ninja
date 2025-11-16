# Raspberry Ninja on NVIDIA Jetson

The Jetson Nano/NX/AGX can handle Raspberry Ninja well (1080p30 is easy compared to a Pi). These notes target JetPack 4.x images and keep the NVIDIA `tegra` kernel intact while updating the userland media stack under `/usr/local`.

## Pick the right script

Most users on the provided pre-built image only need to refresh code and dependencies:

```
cd ~/raspberry_ninja
git pull
cd installers/nvidia_jetson
chmod +x installer.sh toolchain_update.sh setup_autostart.sh
./toolchain_update.sh
```

Run `installer.sh` when you are starting from a clean official JetPack image or repairing a badly broken system:

```
cd ~/raspberry_ninja/installers/nvidia_jetson
chmod +x installer.sh
sudo ./installer.sh                 # heavy build; expect several hours
# Optional legacy path if you really want an in-place distro upgrade:
# INCLUDE_DISTRO_UPGRADE=1 sudo ./installer.sh
```

Both flows need sudo, a stable internet connection, and plenty of free space (40 GB+ is safer). Expect to babysit long builds and rerun steps if network mirrors flake out.

## Disable screen blanking and set up autostart

`setup_autostart.sh` can disable DPMS/console blanking, prompt for your `publish.py` command, and create a systemd service:

```
cd ~/raspberry_ninja/installers/nvidia_jetson
sudo ./setup_autostart.sh
```

You can rerun it to toggle screen-blanking later; only that step needs sudo.

## Installing from an official NVIDIA image

The official JetPack images include the encoder/decoder bits we rely on. The installer script builds newer GStreamer and friends on top of that base. Run sections of `installer.sh` manually if you hit errors; newer GStreamer versions sometimes require tweaks.

Building from scratch takes hours. You can skip optional steps (SRT/FFmpeg extras) if you want a faster but less feature-complete setup.

## Using the pre-built image

Latest pre-setup Jetson images (needs 16 GB uSD or larger and up-to-date firmware):

- Download (updated October 2025): https://drive.google.com/file/d/1B_ywphXQ49F9we3ytcM-Zn1h7dCYOLBh/view?usp=share_link
- Works on Jetson Nano 2GB A02; should also work on Nano 4GB with current firmware.
- Includes GStreamer 1.26.7 with libcamera, SRT, RTMP, FFmpeg, hardware encode, and AV1 support.
- Image is shrunk to ~15 GB (about 7 GB zipped); 32 GB cards are recommended.

After flashing, expand the root partition to use the full SD card (example for `/dev/mmcblk0`):

```
sudo growpart /dev/mmcblk0 1   # grows partition 1 to fill the card
sudo resize2fs /dev/mmcblk0p1  # expands the ext4 filesystem
```

If your device enumerates as `/dev/sda`, replace `mmcblk0` with `sda`. You can also do this via GNOME Disks (“Resize…”) if you prefer a GUI.

Flash with Win32DiskImager (or balenaEtcher). Default credentials:

```
username: ninja
password: vdo
```

Chromium may not be installed on older builds.

After flashing, pull the latest code and refresh dependencies:

```
sudo rm -r raspberry_ninja 2>/dev/null || true
git clone https://github.com/steveseguin/raspberry_ninja
cd raspberry_ninja/installers/nvidia_jetson
sudo ./installer.sh
```

## Missing NVIDIA GStreamer plugins?

If you are not on an official JetPack image (or something wiped the NVIDIA plugins), grab `libgstnvidia.zip` from this repo and restore it after running the installer:

- https://github.com/steveseguin/raspberry_ninja/raw/refs/heads/main/installers/nvidia_jetson/libgstnvidia.zip
- After the installer finishes, extract/copy the contents into `/usr/local/lib/aarch64-linux-gnu/gstreamer-1.0/`.
- You can also pre-copy them to `/usr/lib/aarch64-linux-gnu/gstreamer-1.0/` before running the script and hope detection picks them up.

## Official NVIDIA images

Official downloads: https://developer.nvidia.com/embedded/downloads (Jetson Nano images ship with Ubuntu 18 and GStreamer 1.14; we recommend upgrading GStreamer to at least 1.16+ with the installer script).

After flashing the image and logging in:

```
git clone https://github.com/steveseguin/raspberry_ninja/
cd raspberry_ninja/installers/nvidia_jetson
chmod +x installer.sh
sudo ./installer.sh
```

## Auto-start service on boot

You can adapt the Raspberry Pi service file at `installers/raspberry_pi/raspininja.service` if you prefer a manual service setup: https://github.com/steveseguin/raspberry_ninja/tree/main/installers/raspberry_pi#setting-up-auto-boot

If you copy it, consider changing or removing:
```
User=vdo
Group=vdo
Environment=XDG_RUNTIME_DIR=/run/user/1000
ExecStartPre=vcgencmd get_camera
```

`setup_autostart.sh` already handles these tweaks for Jetson users, so start there unless you need a custom service.

## Details on NVIDIA's GStreamer implementation

Docs on the encoder and pipeline options: https://docs.nvidia.com/jetson/l4t/index.html#page/Tegra%20Linux%20Driver%20Package%20Development%20Guide/accelerated_gstreamer.html#wwpID0E0A40HA

![image](https://user-images.githubusercontent.com/2575698/127804472-073ce656-babc-450a-a7a5-754493ad1fd8.png)
![image](https://user-images.githubusercontent.com/2575698/127804558-1560ad4d-6c2a-4791-92ca-ca50d2eacc2d.png)

## Problems and troubleshooting

- **"START PIPE" but nothing happens** – make sure the correct video device is set (`video0`, `video1`, etc.). `gst-device-monitor-1.0` lists available devices.
- **Other capture issues** – confirm the camera supports MJPEG (or adapt the pipeline accordingly).
- **`nvjpegdec` not found** – ensure the NVIDIA GStreamer plugins are present (see `libgstnvidia.zip` above) and that you ran the installer script successfully.

### Updating firmware on Jetson Nano

Nano 2GB/4GB dev kits may need firmware updates for newer images. Updating requires Ubuntu 18 with JetPack 4 installed and can take a couple of hours. Once updated, 2GB and 4GB images are usually compatible.
