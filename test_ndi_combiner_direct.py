#!/usr/bin/env python3
"""
Test NDI combiner directly with test sources
"""

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import sys

Gst.init(None)

def test_ndi_combiner():
    """Test NDI combiner with test sources"""
    print("Testing NDI combiner with test audio/video sources...")
    
    # Create pipeline
    pipeline_str = """
    videotestsrc pattern=ball ! 
    video/x-raw,width=640,height=480,framerate=30/1 ! 
    ndisinkcombiner name=combiner ! 
    ndisink ndi-name="TestCombinerStream"
    
    audiotestsrc wave=sine freq=440 ! 
    audio/x-raw,rate=48000,channels=2 ! 
    combiner.
    """
    
    try:
        pipeline = Gst.parse_launch(pipeline_str)
    except Exception as e:
        print(f"ERROR creating pipeline: {e}")
        return
    
    print("Pipeline created successfully")
    
    # Set up bus
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    
    def on_message(bus, message):
        t = message.type
        if t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"Error: {err}, Debug: {debug}")
            loop.quit()
        elif t == Gst.MessageType.EOS:
            print("End of stream")
            loop.quit()
    
    bus.connect("message", on_message)
    
    # Start pipeline
    print("Starting pipeline...")
    ret = pipeline.set_state(Gst.State.PLAYING)
    if ret == Gst.StateChangeReturn.FAILURE:
        print("Failed to start pipeline")
        return
    
    print("\nNDI stream 'TestCombinerStream' should now be visible on the network")
    print("This stream contains both audio (440Hz sine wave) and video (moving ball)")
    print("Press Ctrl+C to stop")
    
    # Run main loop
    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        print("\nStopping...")
    
    # Cleanup
    pipeline.set_state(Gst.State.NULL)
    print("Done")

if __name__ == "__main__":
    test_ndi_combiner()