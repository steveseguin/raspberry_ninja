#!/bin/bash
echo "Creating test NDI stream 'WSL-NDI-Test'..."
echo "Check your Windows NDI viewer for this stream."
echo "Press Ctrl+C to stop."
gst-launch-1.0 videotestsrc pattern=ball ! video/x-raw,width=640,height=480,framerate=30/1 ! ndisink ndi-name="WSL-NDI-Test"
