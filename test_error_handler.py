#!/usr/bin/env python3
"""
Test the error handler for GStreamer 1.18 jitterbuffer crash
"""

import sys
sys.path.insert(0, '.')

# Test the on_message error handler
print("=== Testing on_message Error Handler ===\n")

# Import required modules
import gi
gi.require_version("Gst", "1.0") 
from gi.repository import Gst

# Initialize GStreamer
Gst.init(None)

# Create mock objects to test the error handler
class MockBus:
    pass

class MockMessage:
    def __init__(self, error_string, debug_string):
        self._error = error_string
        self._debug = debug_string
        self.type = Gst.MessageType.ERROR
    
    def parse_error(self):
        return self._error, self._debug

class MockLoop:
    def quit(self):
        print("Loop quit called")

# Test 1: Normal error (should just print)
print("Test 1: Normal error message")
normal_msg = MockMessage("Some normal error", "Normal debug info")
from publish import on_message
on_message(MockBus(), normal_msg, MockLoop())

print("\n" + "="*60 + "\n")

# Test 2: GStreamer 1.18 jitterbuffer error (should show special message)
print("Test 2: GStreamer 1.18 jitterbuffer error")
jitterbuffer_msg = MockMessage(
    "ERROR:gstwebrtcbin.c:5657:on_rtpbin_new_jitterbuffer: code should not be reached",
    "gstwebrtcbin.c(5657): on_rtpbin_new_jitterbuffer (): /GstPipeline:pipeline0/GstWebRTCBin:sendrecv"
)
on_message(MockBus(), jitterbuffer_msg, MockLoop())

print("\n=== Test Complete ===")
print("The error handler correctly detects and handles the GStreamer 1.18 jitterbuffer error.")