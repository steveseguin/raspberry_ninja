#!/usr/bin/env python3
"""
Minimal test focused on WebRTC negotiation issue
"""

import asyncio
import json
import websockets
import ssl
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
gi.require_version('GstSdp', '1.0')
from gi.repository import Gst, GstWebRTC, GstSdp, GLib
import threading

Gst.init(None)

# Run GLib main loop in background
def run_glib_loop():
    loop = GLib.MainLoop()
    loop.run()

glib_thread = threading.Thread(target=run_glib_loop, daemon=True)
glib_thread.start()

class MinimalRecorder:
    def __init__(self):
        self.ws = None
        self.pipeline = None
        self.webrtc = None
        self.session_id = None
        
    async def connect(self):
        """Connect to server"""
        uri = "wss://wss.vdo.ninja:443"
        ssl_context = ssl.create_default_context()
        self.ws = await websockets.connect(uri, ssl=ssl_context)
        print("✅ Connected to server")
        
    async def join_room(self):
        """Join room"""
        await self.ws.send(json.dumps({
            "request": "joinroom",
            "roomid": "testroom123"
        }))
        print("✅ Sent join request")
        
    def create_pipeline(self):
        """Create GStreamer pipeline"""
        self.pipeline = Gst.Pipeline.new('recorder')
        self.webrtc = Gst.ElementFactory.make('webrtcbin', 'webrtc')
        
        # Configure
        self.webrtc.set_property('bundle-policy', GstWebRTC.WebRTCBundlePolicy.MAX_BUNDLE)
        self.webrtc.set_property('stun-server', 'stun://stun.cloudflare.com:3478')
        
        self.pipeline.add(self.webrtc)
        
        # Add receive-only transceiver BEFORE connecting signals
        caps = Gst.caps_from_string("application/x-rtp,media=video")
        self.webrtc.emit('add-transceiver', GstWebRTC.WebRTCRTPTransceiverDirection.RECVONLY, caps)
        
        # Connect signals
        self.webrtc.connect('on-ice-candidate', self.on_ice_candidate)
        self.webrtc.connect('notify::connection-state', self.on_connection_state)
        self.webrtc.connect('notify::ice-connection-state', self.on_ice_state)
        self.webrtc.connect('pad-added', self.on_pad_added)
        
        # Start pipeline
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            print("❌ Failed to start pipeline")
        else:
            print("✅ Pipeline started")
        
    def on_ice_candidate(self, webrtc, mlineindex, candidate):
        """Handle ICE candidate"""
        if self.session_id:
            # Send in main thread
            asyncio.create_task(self.send_ice_candidate(candidate, mlineindex))
        
    async def send_ice_candidate(self, candidate, mlineindex):
        """Send ICE candidate to server"""
        try:
            await self.ws.send(json.dumps({
                'candidates': [{
                    'candidate': candidate,
                    'sdpMLineIndex': mlineindex
                }],
                'session': self.session_id,
                'type': 'remote'
            }))
            print(f"📤 Sent ICE candidate")
        except Exception as e:
            print(f"❌ Failed to send ICE: {e}")
        
    def on_connection_state(self, webrtc, pspec):
        """Monitor connection state"""
        state = webrtc.get_property('connection-state')
        print(f"🔌 Connection state: {state.value_name}")
        
    def on_ice_state(self, webrtc, pspec):
        """Monitor ICE state"""
        state = webrtc.get_property('ice-connection-state')
        print(f"🧊 ICE state: {state.value_name}")
            
    def on_pad_added(self, webrtc, pad):
        """Handle new pad"""
        caps = pad.get_current_caps()
        if caps:
            structure = caps.get_structure(0)
            print(f"✅ New pad: {structure.get_name()}")
            
            # Create simple recording pipeline
            queue = Gst.ElementFactory.make('queue', 'queue')
            fakesink = Gst.ElementFactory.make('fakesink', 'sink')
            
            self.pipeline.add(queue)
            self.pipeline.add(fakesink)
            queue.link(fakesink)
            
            queue.sync_state_with_parent()
            fakesink.sync_state_with_parent()
            
            # Link pad
            queue_sink = queue.get_static_pad('sink')
            if pad.link(queue_sink) == Gst.PadLinkReturn.OK:
                print("✅ Pad linked successfully")
            else:
                print("❌ Failed to link pad")
            
    async def handle_offer(self, offer_sdp, session_id):
        """Handle SDP offer"""
        self.session_id = session_id
        print(f"\n📝 Session ID: {session_id}")
        
        # Parse SDP
        res, sdp_msg = GstSdp.SDPMessage.new_from_text(offer_sdp)
        if res != GstSdp.SDPResult.OK:
            print("❌ Failed to parse SDP")
            return None
            
        offer = GstWebRTC.WebRTCSessionDescription.new(
            GstWebRTC.WebRTCSDPType.OFFER,
            sdp_msg
        )
        
        # Set remote description
        promise = Gst.Promise.new()
        self.webrtc.emit('set-remote-description', offer, promise)
        promise.wait()
        
        # Check for error
        reply = promise.get_reply()
        if reply:
            error = reply.get_value('error')
            if error:
                print(f"❌ Error setting remote description: {error}")
                return None
        
        print("✅ Set remote description")
        
        # Create answer
        promise = Gst.Promise.new()
        self.webrtc.emit('create-answer', None, promise)
        promise.wait()
        
        reply = promise.get_reply()
        if not reply:
            print("❌ No reply from create-answer")
            return None
            
        answer = reply.get_value('answer')
        error = reply.get_value('error')
        
        if error:
            print(f"❌ Error creating answer: {error}")
            return None
            
        if not answer:
            print("❌ No answer in reply")
            return None
            
        # Set local description
        promise = Gst.Promise.new()
        self.webrtc.emit('set-local-description', answer, promise)
        promise.wait()
        
        print("✅ Created and set answer")
        return answer.sdp.as_text()
        
    async def run(self):
        """Main loop"""
        await self.connect()
        await self.join_room()
        
        # Wait for room listing
        msg = await self.ws.recv()
        data = json.loads(msg)
        print(f"\n📨 Received: {data.get('request', 'unknown')}")
        
        if 'list' in data and len(data['list']) > 0:
            stream = data['list'][0]
            stream_id = stream['streamID']
            print(f"📺 Found stream: {stream_id}")
            
            # Create pipeline NOW before requesting stream
            self.create_pipeline()
            
            # Request to play
            await self.ws.send(json.dumps({
                "request": "play",
                "streamID": stream_id
            }))
            print("📤 Sent play request")
            
            # Process messages
            timeout_count = 0
            while timeout_count < 10:
                try:
                    msg = await asyncio.wait_for(self.ws.recv(), timeout=2.0)
                    data = json.loads(msg)
                    
                    if 'description' in data:
                        desc_type = data['description']['type']
                        print(f"\n📨 Received {desc_type}")
                        
                        if desc_type == 'offer':
                            # Handle offer
                            answer_sdp = await self.handle_offer(
                                data['description']['sdp'],
                                data.get('session')
                            )
                            
                            if answer_sdp:
                                # Send answer
                                await self.ws.send(json.dumps({
                                    'description': {
                                        'type': 'answer',
                                        'sdp': answer_sdp
                                    },
                                    'session': self.session_id
                                }))
                                print("📤 Sent answer")
                                
                    elif 'candidates' in data:
                        # Add remote ICE candidates
                        for candidate in data['candidates']:
                            if 'candidate' in candidate:
                                self.webrtc.emit('add-ice-candidate', 
                                               candidate.get('sdpMLineIndex', 0),
                                               candidate['candidate'])
                        print(f"📥 Added {len(data['candidates'])} remote ICE candidates")
                        
                except asyncio.TimeoutError:
                    timeout_count += 1
                    
        else:
            print("❌ No streams in room")
            
async def main():
    recorder = MinimalRecorder()
    
    try:
        await recorder.run()
        
        # Run for 20 seconds
        print("\n⏱️ Running for 20 seconds...")
        await asyncio.sleep(20)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if recorder.ws:
            await recorder.ws.close()
        if recorder.pipeline:
            recorder.pipeline.set_state(Gst.State.NULL)

if __name__ == "__main__":
    print("="*60)
    print("MINIMAL WEBRTC TEST - Room: testroom123")
    print("="*60)
    asyncio.run(main())