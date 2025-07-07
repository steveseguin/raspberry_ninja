#!/bin/bash
echo "GStreamer version check:"
echo "======================="
gst-launch-1.0 --version
echo ""
echo "Mpegtsmux element details:"
gst-inspect-1.0 mpegtsmux | grep -E "Version|Rank|Long-name"
echo ""
echo "Check if running on ARM:"
uname -m
echo ""
echo "Check GStreamer plugin versions:"
gst-inspect-1.0 --version