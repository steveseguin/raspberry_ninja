# A version for the Nvidia Jetson

This is very much like the RPI version, but uses the Nvidia Jetson (Nano/NX/AGX) and the official Nvidia Jetson Ubuntu 18 system image.

Trying to upgrade Gstreamer to 1.16 or newer involves nothing but endless pain and suffering, so I'm sticking with the officially supported 1.14. It needs libnice to be added for webRTC support to be available still, and the install script provided attempts to do that.

Even the newest Gstreamer version still have incomplete compatilbity with VDO.Ninja, so this Python scripts uses the legacy-compatible API interface offered by VDO.Ninja; it's enough to still get a basic video/audio stream though to at least one viewer. Potentially more.

Details on the Nvidia encoder and pipeline options:
https://docs.nvidia.com/jetson/l4t/index.html#page/Tegra%20Linux%20Driver%20Package%20Development%20Guide/accelerated_gstreamer.html#wwpID0E0A40HA
