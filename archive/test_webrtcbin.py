#!/usr/bin/env python3
"""
Debug webrtcbin creation
"""

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

# Initialize
Gst.init(None)

# Test different ways to create webrtcbin
print("Testing webrtcbin creation:")

# Method 1: Direct element factory
try:
    element = Gst.ElementFactory.make('webrtcbin', 'test1')
    if element:
        print("✅ Method 1: ElementFactory.make() worked")
    else:
        print("❌ Method 1: ElementFactory.make() returned None")
except Exception as e:
    print(f"❌ Method 1 error: {e}")

# Method 2: Parse launch
try:
    pipeline_str = "webrtcbin name=webrtc latency=0 bundle-policy=max-bundle"
    pipe = Gst.parse_launch(pipeline_str)
    if pipe:
        print("✅ Method 2: parse_launch() created pipeline")
        webrtc = pipe.get_by_name('webrtc')
        if webrtc:
            print("✅ Method 2: get_by_name('webrtc') worked")
        else:
            print("❌ Method 2: get_by_name('webrtc') returned None")
            # Try iterating elements
            it = pipe.iterate_elements()
            print("   Elements in pipeline:")
            while True:
                result, elem = it.next()
                if result != Gst.IteratorResult.OK:
                    break
                print(f"   - {elem.get_name()} ({type(elem).__name__})")
    else:
        print("❌ Method 2: parse_launch() returned None")
except Exception as e:
    print(f"❌ Method 2 error: {e}")

# Method 3: Create pipeline and add element
try:
    pipe = Gst.Pipeline.new('test-pipeline')
    webrtc = Gst.ElementFactory.make('webrtcbin', 'mywebrtc')
    if webrtc:
        pipe.add(webrtc)
        found = pipe.get_by_name('mywebrtc')
        if found:
            print("✅ Method 3: Pipeline.add() and get_by_name() worked")
        else:
            print("❌ Method 3: get_by_name() failed after add")
    else:
        print("❌ Method 3: Could not create webrtcbin")
except Exception as e:
    print(f"❌ Method 3 error: {e}")