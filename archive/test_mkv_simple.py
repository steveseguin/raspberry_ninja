#!/usr/bin/env python3
"""Test MKV recording with simple test sources"""

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import time

Gst.init(None)

def test_mkv_recording():
    """Test basic MKV recording functionality"""
    # Create pipeline with test sources
    pipeline_str = """
        videotestsrc is-live=true ! video/x-raw,width=640,height=480,framerate=30/1 ! 
        queue ! x264enc tune=zerolatency ! h264parse ! matroskamux name=mux !
        filesink location=test_mkv_output.mkv
        
        audiotestsrc is-live=true wave=sine ! audio/x-raw,rate=48000,channels=1 !
        queue ! opusenc ! opusparse ! mux.
    """
    
    print("Creating pipeline...")
    pipe = Gst.parse_launch(pipeline_str)
    
    def on_message(bus, message):
        t = message.type
        if t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"Error: {err}: {debug}")
        elif t == Gst.MessageType.EOS:
            print("End of stream")
        return True
    
    bus = pipe.get_bus()
    bus.add_signal_watch()
    bus.connect("message", on_message)
    
    print("Starting pipeline...")
    pipe.set_state(Gst.State.PLAYING)
    
    # Record for 5 seconds
    print("Recording for 5 seconds...")
    time.sleep(5)
    
    print("Stopping pipeline...")
    pipe.send_event(Gst.Event.new_eos())
    time.sleep(1)
    
    pipe.set_state(Gst.State.NULL)
    print("Done! Check test_mkv_output.mkv")

if __name__ == "__main__":
    test_mkv_recording()