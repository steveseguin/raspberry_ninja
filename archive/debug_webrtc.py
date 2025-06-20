#!/usr/bin/env python3
"""Debug WebRTC connection to see if we're receiving media"""

import asyncio
import json
import sys
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
from gi.repository import Gst, GstWebRTC, GLib

Gst.init(None)

class WebRTCDebugger:
    def __init__(self):
        self.pipe = None
        self.webrtc = None
        self.pad_count = 0
        
    def start_pipeline(self):
        """Create a simple WebRTC receive pipeline"""
        # Just WebRTC to fakesink for debugging
        self.pipe = Gst.Pipeline.new('debug-pipe')
        
        self.webrtc = Gst.ElementFactory.make('webrtcbin', 'webrtc')
        self.webrtc.set_property('bundle-policy', GstWebRTC.WebRTCBundlePolicy.MAX_BUNDLE)
        
        # Connect all signals
        self.webrtc.connect('on-ice-candidate', self.on_ice_candidate)
        self.webrtc.connect('pad-added', self.on_pad_added)
        self.webrtc.connect('on-new-transceiver', self.on_new_transceiver)
        self.webrtc.connect('notify::ice-connection-state', self.on_ice_state)
        self.webrtc.connect('notify::connection-state', self.on_connection_state)
        
        self.pipe.add(self.webrtc)
        
        # Start pipeline
        self.pipe.set_state(Gst.State.PLAYING)
        print("Pipeline started")
        
    def on_ice_candidate(self, element, mline, candidate):
        print(f"Local ICE candidate: mline={mline}")
        
    def on_pad_added(self, element, pad):
        self.pad_count += 1
        pad_name = pad.get_name()
        print(f"\n🎉 PAD ADDED #{self.pad_count}: {pad_name}")
        
        # Get caps
        caps = pad.get_current_caps()
        if caps:
            print(f"   Caps: {caps.to_string()}")
        
        # Just connect to fakesink
        fakesink = Gst.ElementFactory.make('fakesink', f'sink_{pad_name}')
        self.pipe.add(fakesink)
        fakesink.sync_state_with_parent()
        pad.link(fakesink.get_static_pad('sink'))
        print(f"   Connected to fakesink")
        
    def on_new_transceiver(self, element, transceiver):
        print(f"New transceiver created")
        transceiver.set_property('direction', GstWebRTC.WebRTCRTPTransceiverDirection.RECVONLY)
        
    def on_ice_state(self, element, pspec):
        state = element.get_property('ice-connection-state')
        print(f"ICE state: {state.value_name}")
        
    def on_connection_state(self, element, pspec):
        state = element.get_property('connection-state')
        print(f"Connection state: {state.value_name}")
        
    def handle_offer(self, sdp):
        """Process SDP offer"""
        print("Processing offer...")
        res, sdp_msg = GstWebRTC.SDPMessage.new_from_text(sdp)
        if res != 0:
            print(f"Failed to parse SDP")
            return
            
        offer = GstWebRTC.WebRTCSessionDescription.new(
            GstWebRTC.WebRTCSDPType.OFFER,
            sdp_msg
        )
        
        # Set remote description
        promise = Gst.Promise.new()
        self.webrtc.emit('set-remote-description', offer, promise)
        promise.wait()
        
        print("Creating answer...")
        # Create answer
        promise = Gst.Promise.new()
        self.webrtc.emit('create-answer', None, promise)
        promise.wait()
        
        reply = promise.get_reply()
        answer = reply.get_value('answer')
        
        # Set local description
        promise = Gst.Promise.new()
        self.webrtc.emit('set-local-description', answer, promise)
        promise.wait()
        
        print("Answer created")
        return answer.sdp.as_text()
        
    def add_ice(self, candidate, mline=0):
        """Add remote ICE candidate"""
        self.webrtc.emit('add-ice-candidate', mline, candidate)


# Test with stdin/stdout communication
def main():
    debugger = WebRTCDebugger()
    debugger.start_pipeline()
    
    print("Waiting for offer on stdin...")
    
    # Simple stdin reader
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
                
            data = json.loads(line.strip())
            
            if 'offer' in data:
                answer = debugger.handle_offer(data['offer'])
                print(json.dumps({'answer': answer}))
                sys.stdout.flush()
                
            elif 'ice' in data:
                debugger.add_ice(data['ice'], data.get('mline', 0))
                
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            
    print("Exiting...")

if __name__ == "__main__":
    main()