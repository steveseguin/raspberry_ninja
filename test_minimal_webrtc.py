#!/usr/bin/env python3
"""
Minimal WebRTC test to isolate video sending issue
"""

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
from gi.repository import Gst, GstWebRTC, GLib
import json
import asyncio
import websockets
import time

Gst.init(None)

class MinimalWebRTC:
    def __init__(self):
        self.pipe = None
        self.webrtc = None
        self.ws = None
        
    async def connect(self):
        """Connect to VDO.Ninja"""
        uri = "wss://wss.vdo.ninja:443"
        print(f"Connecting to {uri}...")
        self.ws = await websockets.connect(uri)
        print("Connected!")
        
        # Send initial seed
        await self.ws.send(json.dumps({"request": "seed", "streamID": "5566281"}))
        
        # Start receiving messages
        asyncio.create_task(self.receive_messages())
        
    async def receive_messages(self):
        """Handle incoming WebSocket messages"""
        async for message in self.ws:
            try:
                data = json.loads(message)
                if 'description' in data and data['description'].get('type') == 'answer':
                    print("Got answer, setting remote description")
                    answer = data['description']['sdp']
                    ret = GstWebRTC.WebRTCSDPType.ANSWER
                    res, sdpmsg = GstSdp.SDPMessage.new_from_text(answer)
                    answer = GstWebRTC.WebRTCSessionDescription.new(ret, sdpmsg)
                    promise = Gst.Promise.new()
                    self.webrtc.emit('set-remote-description', answer, promise)
            except Exception as e:
                print(f"Error handling message: {e}")
    
    def start_pipeline(self):
        """Create and start the pipeline"""
        # Simple pipeline with just video
        pipeline_str = """
        videotestsrc pattern=ball ! 
        video/x-raw,width=320,height=240,framerate=15/1 ! 
        clockoverlay ! 
        vp8enc deadline=1 target-bitrate=500000 ! 
        rtpvp8pay ! 
        application/x-rtp,media=video,encoding-name=VP8,payload=96 ! 
        webrtcbin name=sendrecv bundle-policy=max-bundle
        """
        
        print("Creating pipeline...")
        self.pipe = Gst.parse_launch(pipeline_str)
        self.webrtc = self.pipe.get_by_name('sendrecv')
        
        # Set STUN server
        self.webrtc.set_property('stun-server', 'stun://stun.l.google.com:19302')
        
        # Handle negotiation
        self.webrtc.connect('on-negotiation-needed', self.on_negotiation_needed)
        self.webrtc.connect('on-ice-candidate', self.on_ice_candidate)
        
        # Monitor state
        self.webrtc.connect('notify::connection-state', self.on_connection_state)
        self.webrtc.connect('notify::ice-connection-state', self.on_ice_connection_state)
        
        # Start pipeline
        print("Starting pipeline...")
        self.pipe.set_state(Gst.State.PLAYING)
        
    def on_negotiation_needed(self, element):
        """Create offer when negotiation needed"""
        print("Negotiation needed, creating offer...")
        promise = Gst.Promise.new_with_change_func(self.on_offer_created, element, None)
        element.emit('create-offer', None, promise)
        
    def on_offer_created(self, promise, element, _):
        """Handle offer creation"""
        promise.wait()
        reply = promise.get_reply()
        offer = reply['offer']
        element.emit('set-local-description', offer, promise)
        
        # Send offer
        text = offer.sdp.as_text()
        msg = {"description": {"type": "offer", "sdp": text}}
        asyncio.create_task(self.send_message(msg))
        
    async def send_message(self, msg):
        """Send message via WebSocket"""
        if self.ws:
            await self.ws.send(json.dumps(msg))
            print(f"Sent: {msg.get('description', {}).get('type', 'message')}")
            
    def on_ice_candidate(self, element, mlineindex, candidate):
        """Handle ICE candidate"""
        msg = {"candidates": [{"candidate": candidate, "sdpMLineIndex": mlineindex}]}
        asyncio.create_task(self.send_message(msg))
        
    def on_connection_state(self, element, pspec):
        """Monitor connection state"""
        state = element.get_property('connection-state')
        print(f"Connection state: {state}")
        
    def on_ice_connection_state(self, element, pspec):
        """Monitor ICE state"""
        state = element.get_property('ice-connection-state')
        print(f"ICE state: {state}")
        
    def check_stats(self):
        """Check WebRTC stats"""
        def on_stats(promise, _, __):
            promise.wait()
            stats = promise.get_reply()
            if stats:
                stats_str = stats.to_string()
                # Look for video bytes
                if "kind=(string)video" in stats_str:
                    try:
                        video_section = stats_str.split("kind=(string)video")[1].split("rtp-")[0]
                        if "bytes-sent=(guint64)" in video_section:
                            bytes_match = video_section.split("bytes-sent=(guint64)")[1]
                            bytes_sent = int(bytes_match.split(",")[0].split(";")[0])
                            print(f"Video bytes sent: {bytes_sent}")
                            if bytes_sent == 0:
                                print("⚠️ WARNING: No video data being sent!")
                    except:
                        pass
                        
        promise = Gst.Promise.new_with_change_func(on_stats, None, None)
        self.webrtc.emit('get-stats', None, promise)
        return True

async def main():
    """Main function"""
    test = MinimalWebRTC()
    
    # Connect WebSocket
    await test.connect()
    
    # Start pipeline
    test.start_pipeline()
    
    # Schedule stats checking
    GLib.timeout_add_seconds(3, test.check_stats)
    
    # Run GLib main loop in thread
    loop = GLib.MainLoop()
    import threading
    thread = threading.Thread(target=loop.run)
    thread.daemon = True
    thread.start()
    
    # Keep running
    try:
        await asyncio.sleep(60)
    except KeyboardInterrupt:
        print("\nStopping...")
    
    if test.pipe:
        test.pipe.set_state(Gst.State.NULL)

if __name__ == "__main__":
    print("Minimal WebRTC Test")
    print("View at: https://vdo.ninja/?view=5566281&password=false")
    print("-" * 50)
    asyncio.run(main())