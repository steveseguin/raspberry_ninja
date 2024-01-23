**Raspberry Ninja runs on a Mac!** Useful if you want low level control over your VDO.Ninja outputs, or perhaps you want to use VDO.Ninaj with OpenCV/SciKit for your next AI project. Anyways, the installer guide is below

#### Moderate pain tolerance needed to install on Mac

Installing Raspberry Ninja for Mac OS is made a bit more difficult due to the decision not to include GStreamer-WebRTC support by the Homebrew developers. see: https://github.com/Homebrew/homebrew-core/pull/25680.  Be sure to provide them feedback that you think its valuable to have included by default. It could the easiest way to install Raspberry Ninja with a minor change. :)

It's also possible to install Gstreamer on Mac OS using an install package provided by the Gstreamer developers, but it's unsigned (so Apple makes it annoying to install), the website for it is often offline, and I'm not sure how to get its Python-bindings working. If somneone can provide instructions for it instead though, I'll include them though.

## Homebrew install method for Mac OS X

note: I already had XCode installed on my Mac M1, but you might need to install XCode as well for the following steps to work.

Just open Terminal on your mac, and enter each of the following commands, one at a time, and hopefully it goes well!

```
# install brew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# update if needed
brew update
brew upgrade

# install dependencies
brew install automake autoconf libtool pkg-config glib gtk-doc srtp wget git
brew install python gobject-introspection

# need to build gstreamer from source - it took several minutes for me.
wget https://gist.githubusercontent.com/steveseguin/0533d4ab0bd8cc9acf5737bff20d37a8/raw/e495c41b85808d845ed4d21b0b41840a03d44e96/gstreamer.rb
brew reinstall --build-from-source gstreamer.rb

# get Raspberry Ninja
git clone https://github.com/steveseguin/raspberry_ninja
cd raspberry_ninja

# run test
python3 publish.py --test
```
I think I got most of the hard parts figured out with this brew method, but I don't have a fresh macbook to test the installer on again, so I might be overlooking something. Please report issues with the installer so I can update as needed.

## Hardware encoding

Looks like there is an h264 and h265 video encoder available, but by default I think I have x264 added support at the moment.
```
steveseguin@Steves-MacBook-Air raspberry_ninja % gst-inspect-1.0 | grep "264"
applemedia:  vtenc_h264: H.264 encoder
applemedia:  vtenc_h264_hw: H.264 (HW only) encoder
x264:  x264enc: x264 H.264 Encoder
```
