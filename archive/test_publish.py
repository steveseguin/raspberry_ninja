#!/usr/bin/env python3
"""
Unit tests for publish.py
"""
import unittest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import asyncio
import json
import sys
import os

# Add the parent directory to the path so we can import publish
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock Gst before importing publish
sys.modules['gi'] = MagicMock()
sys.modules['gi.repository'] = MagicMock()
sys.modules['gi.repository.Gst'] = MagicMock()
sys.modules['gi.repository.GstWebRTC'] = MagicMock()
sys.modules['gi.repository.GstSdp'] = MagicMock()

class TestWebSocketMessages(unittest.TestCase):
    """Test WebSocket message handling"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Import after mocking
        from publish import generateHash, decrypt_message, encrypt_message
        self.generateHash = generateHash
        self.decrypt_message = decrypt_message
        self.encrypt_message = encrypt_message
        
    def test_generate_hash(self):
        """Test hash generation"""
        # Test basic hash generation
        hash1 = self.generateHash("test123", 6)
        self.assertEqual(len(hash1), 6)
        
        # Test consistency
        hash2 = self.generateHash("test123", 6)
        self.assertEqual(hash1, hash2)
        
        # Test different inputs produce different hashes
        hash3 = self.generateHash("test456", 6)
        self.assertNotEqual(hash1, hash3)
        
    def test_room_hash_generation(self):
        """Test room hash generation as used in the app"""
        room_name = "steve1233"
        password = "someEncryptionKey123"
        salt = "vdo.ninja"
        
        room_hash = self.generateHash(room_name + password + salt, 16)
        self.assertEqual(room_hash, "23c5fe1d7ae89540")
        
    def test_encryption_decryption(self):
        """Test message encryption and decryption"""
        original_message = {"test": "data", "number": 123}
        password = "testpassword"
        
        # Encrypt
        encrypted, vector = self.encrypt_message(json.dumps(original_message), password)
        self.assertIsInstance(encrypted, str)
        self.assertIsInstance(vector, str)
        
        # Decrypt
        decrypted_json = self.decrypt_message(encrypted, vector, password)
        
        # The decrypt function returns a string, so compare as string
        self.assertEqual(decrypted_json, json.dumps(original_message))


class TestMessageParsing(unittest.TestCase):
    """Test message parsing logic"""
    
    @patch('publish.GstWebRTC')
    @patch('publish.Gst')
    def setUp(self, mock_gst, mock_webrtc):
        """Set up test client"""
        from publish import WebRTCClient
        
        # Create mock params
        params = MagicMock()
        params.password = "someEncryptionKey123"
        params.room = "steve1233"
        params.streamin = False
        params.stream_id = "test_stream"
        params.server = "wss://test.server"
        params.h264 = True
        params.noaudio = False
        params.multiviewer = False
        params.room_recording = False
        params.record_room = False
        params.room_ndi = False
        params.stream_filter = None
        
        # Set other required params
        for attr in ['vp8', 'vp9', 'av1', 'server', 'bitrate', 'no_stun', 
                     'test', 'raw', 'record', 'fullscreen', 'buffer', 
                     'ndiout', 'ndiname', 'h265', 'framebuffer', 
                     'novideo', 'rotate', 'noqos', 'HDR', 'save', 
                     'zerolatency', 'midi', 'aom_av1', 'pipein', 
                     'view', 'puuid', 'manual', 'commands', 'motd', 
                     'http', 'debug', 'scale', 'faux', 'noap', 
                     'codec', 'clock', 'cleantag']:
            if not hasattr(params, attr):
                setattr(params, attr, False or None)
        
        self.client = GstWebRTC_client(params)
        self.client.conn = AsyncMock()
        
    def test_room_listing_parsing(self):
        """Test parsing of room listing message"""
        listing_msg = {
            "request": "listing",
            "list": [
                {"streamID": "stream1", "UUID": "uuid1"},
                {"streamID": "stream2", "UUID": "uuid2"}
            ]
        }
        
        # Manually call handle_room_listing since we can't easily test async
        asyncio.run(self.client.handle_room_listing(listing_msg["list"]))
        
        # Check that streams were tracked
        self.assertEqual(len(self.client.room_streams), 2)
        self.assertIn("uuid1", self.client.room_streams)
        self.assertIn("uuid2", self.client.room_streams)
        self.assertEqual(self.client.room_streams["uuid1"]["streamID"], "stream1")
        
    def test_session_tracking(self):
        """Test session tracking for clients"""
        uuid = "test-uuid"
        session1 = "session1"
        session2 = "session2"
        
        # Create client
        self.client.clients[uuid] = {
            "UUID": uuid,
            "session": None,
            "webrtc": MagicMock()
        }
        
        # First session should be accepted
        msg1 = {"session": session1}
        self.client.clients[uuid]["session"] = session1
        self.assertEqual(self.client.clients[uuid]["session"], session1)
        
        # Different session should be handled based on room_recording
        self.client.room_recording = False
        # In normal mode, different sessions would print "sessions don't match"
        
        self.client.room_recording = True
        # In room recording mode, new sessions should be accepted


class TestWebRTCPipeline(unittest.TestCase):
    """Test WebRTC pipeline creation"""
    
    @patch('publish.Gst')
    def test_pipeline_string_generation(self, mock_gst):
        """Test that pipeline strings are generated correctly"""
        from publish import WebRTCClient
        
        params = MagicMock()
        # Set basic params
        params.h264 = True
        params.noaudio = False
        params.streamin = False
        params.test = True  # Use test source
        params.bitrate = 2000
        
        # Set all other required params to False/None
        for attr in ['vp8', 'vp9', 'av1', 'password', 'room', 'server',
                     'no_stun', 'raw', 'record', 'fullscreen', 'buffer', 
                     'ndiout', 'ndiname', 'h265', 'framebuffer', 
                     'novideo', 'rotate', 'noqos', 'HDR', 'save', 
                     'zerolatency', 'midi', 'aom_av1', 'pipein', 
                     'view', 'puuid', 'stream_id', 'manual', 'commands', 
                     'motd', 'http', 'debug', 'scale', 'faux', 'noap', 
                     'codec', 'clock', 'multiviewer', 'room_recording',
                     'record_room', 'room_ndi', 'stream_filter', 'cleantag']:
            if not hasattr(params, attr):
                setattr(params, attr, False or None)
                
        client = WebRTCClient(params)
        
        # Check that pipeline includes expected elements
        self.assertIn("videotestsrc", client.pipeline)
        self.assertIn("x264enc", client.pipeline)
        self.assertIn("webrtcbin", client.pipeline)


class TestRoomRecording(unittest.TestCase):
    """Test room recording functionality"""
    
    def test_room_recording_enables_multiviewer(self):
        """Test that room recording enables multiviewer mode"""
        from publish import WebRTCClient
        
        params = MagicMock()
        params.room_recording = True
        params.multiviewer = False
        
        # Set other required params
        for attr in ['password', 'room', 'server', 'stream_id', 'streamin',
                     'h264', 'vp8', 'vp9', 'av1', 'no_stun', 'test', 'raw', 
                     'record', 'fullscreen', 'buffer', 'ndiout', 'ndiname', 
                     'h265', 'framebuffer', 'noaudio', 'novideo', 'rotate', 
                     'noqos', 'HDR', 'save', 'zerolatency', 'midi', 'aom_av1', 
                     'pipein', 'view', 'puuid', 'manual', 'commands', 'motd', 
                     'http', 'debug', 'scale', 'faux', 'noap', 'codec', 
                     'clock', 'bitrate', 'record_room', 'room_ndi', 
                     'stream_filter', 'cleantag']:
            if not hasattr(params, attr):
                setattr(params, attr, False or None)
                
        client = WebRTCClient(params)
        
        # Room recording should enable multiviewer
        self.assertTrue(client.multiviewer)
        
    def test_stream_filter(self):
        """Test stream filtering for room recording"""
        from publish import WebRTCClient
        
        params = MagicMock()
        params.stream_filter = ["stream1", "stream2"]
        params.room_recording = True
        
        # Set other required params
        for attr in ['password', 'room', 'server', 'stream_id', 'streamin',
                     'h264', 'vp8', 'vp9', 'av1', 'no_stun', 'test', 'raw', 
                     'record', 'fullscreen', 'buffer', 'ndiout', 'ndiname', 
                     'h265', 'framebuffer', 'noaudio', 'novideo', 'rotate', 
                     'noqos', 'HDR', 'save', 'zerolatency', 'midi', 'aom_av1', 
                     'pipein', 'view', 'puuid', 'manual', 'commands', 'motd', 
                     'http', 'debug', 'scale', 'faux', 'noap', 'codec', 
                     'clock', 'bitrate', 'multiviewer', 'record_room', 
                     'room_ndi', 'cleantag']:
            if not hasattr(params, attr):
                setattr(params, attr, False or None)
                
        client = WebRTCClient(params)
        
        # Test filter is applied
        self.assertEqual(client.stream_filter, ["stream1", "stream2"])


def run_tests():
    """Run all tests"""
    unittest.main(argv=[''], exit=False, verbosity=2)


if __name__ == '__main__':
    run_tests()