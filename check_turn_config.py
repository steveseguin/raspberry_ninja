#!/usr/bin/env python3
"""Check if TURN is being configured"""

# Quick test to see TURN configuration
import sys
sys.path.insert(0, '.')

# Mock args to test WebRTCClient initialization
class MockArgs:
    def __init__(self):
        # Basic required params
        self.room = "testroom123"
        self.view = "test_stream"
        self.record = "test"
        self.password = "false"
        self.noaudio = True
        self.novideo = True
        
        # Room recording params
        self.record_room = True
        self.room_recording = True
        self.streamin = "room_recording"
        
        # Server params
        self.hostname = None
        self.server = None
        
        # Other params
        self.puuid = None
        self.midi = False
        self.nored = True
        self.noqos = True
        self.framerate = None
        self.width = None
        self.height = None
        self.bitrate = None
        self.audiobitrate = None
        self.buffer = 200
        self.maxbuffer = None
        self.h264 = False
        self.vp8 = False
        self.vp9 = False
        self.av1 = False
        self.hw = False
        self.test = False
        self.pipeline = ""
        self.sink = None
        self.scale = None
        self.adevice = None
        self.vdevice = None
        self.rotate = 0
        self.multiviewer = False
        self.noaec = True
        self.turn_server = None
        self.stun_server = None
        self.ice_transport_policy = None
        self.pipein = None
        self.libcamera = False
        self.rawaudio = False
        self.tcp = False
        self.wss = True
        self.no_stun = False
        self.streamid = None
        self.stream = None
        self.turn_user = None
        self.turn_pass = None

# Test initialization
print("Testing WebRTCClient initialization with room recording...")
print("=" * 70)

try:
    from publish import WebRTCClient
    
    args = MockArgs()
    client = WebRTCClient(args)
    
    print(f"✓ Client created")
    print(f"  room_recording: {client.room_recording}")
    print(f"  record_room: {client.record_room}")
    
    # Check if TURN would be configured
    if hasattr(client, '_get_default_turn_server'):
        turn = client._get_default_turn_server()
        print(f"\n✓ Default TURN server available:")
        print(f"  URL: {turn['url']}")
        print(f"  User: {turn['user']}")
        print(f"  Region: {turn['region']}")
    
    print("\n✅ Room recording should use automatic TURN!")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()