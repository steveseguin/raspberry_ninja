#!/usr/bin/env python3
"""
Integrated test that simulates both publisher and recorder in one process
This allows us to test without needing external streams
"""

import asyncio
import sys
import os
import json
import time
import glob
import threading
from unittest.mock import Mock

# Clean up
for f in glob.glob("integrated_*.ts") + glob.glob("integrated_*.mkv"):
    try:
        os.remove(f)
    except:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from publish import WebRTCClient
from multi_peer_client import MultiPeerClient
import argparse
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

Gst.init(None)

class TestEnvironment:
    """Simulates the VDO.Ninja environment"""
    def __init__(self):
        self.publishers = {}
        self.subscribers = {}
        self.room_members = {}
        
    def add_publisher(self, room, stream_id):
        """Add a publisher to a room"""
        if room not in self.room_members:
            self.room_members[room] = []
        self.room_members[room].append({
            'streamID': stream_id,
            'UUID': f'uuid-{stream_id}'
        })
        
    def get_room_members(self, room):
        """Get members in a room"""
        return self.room_members.get(room, [])

# Global test environment
test_env = TestEnvironment()

class MockWebSocket:
    """Mock WebSocket that simulates VDO.Ninja server"""
    def __init__(self, room_name, is_publisher=False, stream_id=None):
        self.room_name = room_name
        self.is_publisher = is_publisher
        self.stream_id = stream_id
        self.message_queue = asyncio.Queue()
        self.sent_messages = []
        self.peer_connection = None
        
        if is_publisher:
            test_env.add_publisher(room_name, stream_id)
            
    async def send(self, message):
        """Handle sent messages"""
        msg = json.loads(message)
        self.sent_messages.append(msg)
        print(f"[MockWS] {'Publisher' if self.is_publisher else 'Recorder'} sent: {msg.get('request', msg.get('type', 'message'))}")
        
        # Simulate server responses
        if msg.get('request') == 'joinroom':
            # Send room listing
            members = test_env.get_room_members(self.room_name)
            response = {
                'request': 'listing',
                'list': members
            }
            await self.message_queue.put(json.dumps(response))
            
        elif msg.get('request') == 'play':
            # Simulate publisher offering
            stream_id = msg.get('streamID')
            if stream_id in [m['streamID'] for m in test_env.get_room_members(self.room_name)]:
                # Create a simple test pipeline as "publisher"
                self._create_test_publisher(stream_id)
                
        elif msg.get('description'):
            # Handle answer from recorder
            if msg['description']['type'] == 'answer' and self.peer_connection:
                # Process answer in publisher
                await self._handle_answer(msg['description']['sdp'])
                
    async def recv(self):
        """Receive messages"""
        return await self.message_queue.get()
        
    def _create_test_publisher(self, stream_id):
        """Create a test publisher pipeline"""
        def on_negotiation_needed(webrtc):
            # Create offer
            promise = Gst.Promise.new_with_change_func(on_offer_created, webrtc, None)
            webrtc.emit('create-offer', None, promise)
            
        def on_offer_created(promise, webrtc, _):
            reply = promise.get_reply()
            offer = reply.get_value('answer')
            webrtc.emit('set-local-description', offer, Gst.Promise.new())
            
            # Send offer to recorder
            offer_msg = {
                'description': {
                    'type': 'offer', 
                    'sdp': offer.sdp.as_text()
                },
                'session': f'test-session-{stream_id}'
            }
            asyncio.create_task(self.message_queue.put(json.dumps(offer_msg)))
            
        # Create publisher pipeline
        pipeline = Gst.parse_launch(
            "videotestsrc pattern=ball ! "
            "video/x-raw,width=320,height=240,framerate=30/1 ! "
            "videoconvert ! x264enc tune=zerolatency ! rtph264pay ! "
            "application/x-rtp,media=video,encoding-name=H264,payload=96 ! "
            "webrtcbin name=webrtc"
        )
        
        self.peer_connection = pipeline.get_by_name('webrtc')
        self.peer_connection.connect('on-negotiation-needed', on_negotiation_needed)
        
        # Add transceiver
        caps = Gst.caps_from_string("application/x-rtp,media=video,encoding-name=H264")
        self.peer_connection.emit('add-transceiver', 
                                  GstWebRTC.WebRTCRTPTransceiverDirection.SENDONLY, 
                                  caps)
        
        pipeline.set_state(Gst.State.PLAYING)
        
    async def _handle_answer(self, answer_sdp):
        """Handle answer from recorder"""
        # Set remote description
        res, sdp_msg = GstSdp.SDPMessage.new_from_text(answer_sdp)
        answer = GstWebRTC.WebRTCSessionDescription.new(
            GstWebRTC.WebRTCSDPType.ANSWER,
            sdp_msg
        )
        self.peer_connection.emit('set-remote-description', answer, Gst.Promise.new())

async def test_room_recording():
    """Test room recording with simulated publisher"""
    print("="*70)
    print("INTEGRATED ROOM RECORDING TEST")
    print("="*70)
    
    # Step 1: Create a mock publisher
    print("\n1. Creating mock publisher...")
    publisher_ws = MockWebSocket("testroom", is_publisher=True, stream_id="alice")
    
    # Step 2: Create room recorder
    print("\n2. Creating room recorder...")
    args = argparse.Namespace()
    args.room = 'testroom'
    args.record = 'integrated'
    args.record_room = True
    args.noaudio = True
    args.password = None
    args.hostname = 'wss://mock.test'
    args.server = None
    args.streamid = "recorder"
    args.puuid = None
    args.buffer = 200
    args.stream_filter = None
    args.room_ndi = False
    
    # Set other required attributes
    for attr in ['view', 'novideo', 'h264', 'vp8', 'vp9', 'av1', 'test', 
                 'pipein', 'filesrc', 'ndiout', 'fdsink', 'framebuffer', 
                 'midi', 'save', 'socketout', 'aom', 'rotate', 'multiviewer',
                 'pipeline', 'bitrate', 'width', 'height', 'framerate', 
                 'nored', 'noqos', 'zerolatency', 'noprompt', 'socketport',
                 'room_recording', 'streamin']:
        setattr(args, attr, None)
    
    args.bitrate = 2500
    args.width = 1920
    args.height = 1080
    args.framerate = 30
    args.rotate = 0
    
    # Create recorder client
    recorder = WebRTCClient(args)
    recorder.conn = MockWebSocket("testroom", is_publisher=False)
    
    print("   ✓ Room recording enabled:", recorder.room_recording)
    
    # Step 3: Join room
    print("\n3. Joining room...")
    await recorder.sendMessageAsync({
        "request": "joinroom",
        "roomid": recorder.room_name
    })
    
    # Process listing
    listing_msg = await recorder.conn.recv()
    listing = json.loads(listing_msg)
    await recorder.handle_room_listing(listing['list'])
    
    print("   ✓ Room members:", len(listing['list']))
    print("   ✓ Multi-peer client created:", recorder.multi_peer_client is not None)
    
    # Step 4: Process offer/answer
    print("\n4. Processing WebRTC negotiation...")
    
    # Recorder should have sent play request
    # Publisher will send offer
    
    # Process messages
    for i in range(5):  # Process a few messages
        try:
            msg = await asyncio.wait_for(recorder.conn.recv(), timeout=2.0)
            msg_data = json.loads(msg)
            
            if recorder.multi_peer_client:
                await recorder.multi_peer_client.handle_message(msg_data)
                
            if 'description' in msg_data:
                print(f"   ✓ Processed {msg_data['description']['type']}")
                
        except asyncio.TimeoutError:
            break
            
    # Step 5: Check recording state
    print("\n5. Checking recording state...")
    if recorder.multi_peer_client:
        stats = recorder.multi_peer_client.get_all_stats()
        for stat in stats:
            print(f"   Stream {stat['stream_id']}:")
            print(f"     - Recording: {stat['recording']}")
            print(f"     - File: {stat['file']}")
            
    # Step 6: Simulate some recording
    print("\n6. Recording for 5 seconds...")
    await asyncio.sleep(5)
    
    # Step 7: Stop and check files
    print("\n7. Stopping...")
    if recorder.multi_peer_client:
        recorder.multi_peer_client.cleanup()
        
    # Check for files
    recordings = glob.glob("integrated_*.ts") + glob.glob("integrated_*.mkv")
    
    print("\n8. Results:")
    if recordings:
        print(f"   ✅ Found {len(recordings)} recordings")
        for f in recordings:
            print(f"     - {f}: {os.path.getsize(f):,} bytes")
    else:
        print("   ❌ No recordings found")
        
    return len(recordings) > 0

# GLib main loop for GStreamer
def run_glib_loop():
    """Run GLib main loop in separate thread"""
    loop = GLib.MainLoop()
    GLib.timeout_add(100, lambda: True)  # Keep alive
    loop.run()

if __name__ == "__main__":
    print("Starting integrated test...")
    
    # Start GLib loop in background
    glib_thread = threading.Thread(target=run_glib_loop, daemon=True)
    glib_thread.start()
    
    # Run test
    try:
        success = asyncio.run(test_room_recording())
        
        print("\n" + "="*70)
        if success:
            print("✅ TEST PASSED - Room recording works!")
        else:
            print("❌ TEST FAILED - Check output above")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        
    # Cleanup
    for f in glob.glob("integrated_*.ts") + glob.glob("integrated_*.mkv"):
        try:
            os.remove(f)
        except:
            pass