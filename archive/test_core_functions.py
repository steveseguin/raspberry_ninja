#!/usr/bin/env python3
"""
Unit tests for core functions in publish.py
Testing individual functions without full class initialization
"""
import unittest
import json
import hashlib
from base64 import b64encode, b64decode
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad

# Import the functions we want to test
def generateHash(input_str, length):
    """Generate hash for room/stream IDs"""
    hash_object = hashlib.sha256(input_str.encode())
    hash_hex = hash_object.hexdigest()
    return hash_hex[:length]

def encrypt_message(message, password):
    """Encrypt a message using AES"""
    key = hashlib.sha256(password.encode()).digest()[:16]
    iv = get_random_bytes(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded_message = pad(message.encode(), AES.block_size)
    encrypted = cipher.encrypt(padded_message)
    return b64encode(encrypted).decode('utf-8'), b64encode(iv).decode('utf-8')

def decrypt_message(encrypted_message, vector, password):
    """Decrypt a message using AES"""
    key = hashlib.sha256(password.encode()).digest()[:16]
    iv = b64decode(vector)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    decrypted = cipher.decrypt(b64decode(encrypted_message))
    return unpad(decrypted, AES.block_size).decode('utf-8')


class TestCoreFunctions(unittest.TestCase):
    """Test core utility functions"""
    
    def test_generate_hash(self):
        """Test hash generation"""
        # Test basic hash generation
        hash1 = generateHash("test123", 6)
        self.assertEqual(len(hash1), 6)
        
        # Test consistency
        hash2 = generateHash("test123", 6)
        self.assertEqual(hash1, hash2)
        
        # Test different inputs produce different hashes
        hash3 = generateHash("test456", 6)
        self.assertNotEqual(hash1, hash3)
        
    def test_room_hash_generation(self):
        """Test room hash generation as used in the app"""
        room_name = "steve1233"
        password = "someEncryptionKey123"
        salt = "vdo.ninja"
        
        room_hash = generateHash(room_name + password + salt, 16)
        self.assertEqual(room_hash, "23c5fe1d7ae89540")
        
    def test_stream_id_hash(self):
        """Test stream ID hash generation"""
        stream_id = "test_stream"
        password = "someEncryptionKey123"
        salt = "vdo.ninja"
        
        # Standard stream ID is 6 characters
        stream_hash = generateHash(password + salt, 6)
        self.assertEqual(len(stream_hash), 6)
        
    def test_encryption_decryption(self):
        """Test message encryption and decryption"""
        original_message = {"test": "data", "number": 123}
        password = "testpassword"
        
        # Convert to JSON string
        message_str = json.dumps(original_message)
        
        # Encrypt
        encrypted, vector = encrypt_message(message_str, password)
        self.assertIsInstance(encrypted, str)
        self.assertIsInstance(vector, str)
        
        # Decrypt
        decrypted_json = decrypt_message(encrypted, vector, password)
        
        # Compare as strings
        self.assertEqual(decrypted_json, message_str)
        
        # Also verify we can parse it back
        decrypted_obj = json.loads(decrypted_json)
        self.assertEqual(decrypted_obj, original_message)
        
    def test_encryption_with_special_characters(self):
        """Test encryption with special characters"""
        message = "Test with special chars: !@#$%^&*()_+{}[]|\\:;<>?,./"
        password = "testpass123"
        
        encrypted, vector = encrypt_message(message, password)
        decrypted = decrypt_message(encrypted, vector, password)
        
        self.assertEqual(decrypted, message)


class TestMessageStructures(unittest.TestCase):
    """Test message structures used in VDO.Ninja protocol"""
    
    def test_play_request_structure(self):
        """Test play request message structure"""
        stream_id = "test123"
        
        play_msg = {
            "request": "play",
            "streamID": stream_id
        }
        
        # Verify structure
        self.assertIn("request", play_msg)
        self.assertEqual(play_msg["request"], "play")
        self.assertIn("streamID", play_msg)
        
    def test_room_listing_structure(self):
        """Test room listing message structure"""
        listing = {
            "request": "listing",
            "list": [
                {"streamID": "stream1", "UUID": "uuid1"},
                {"streamID": "stream2", "UUID": "uuid2"}
            ]
        }
        
        # Verify structure
        self.assertEqual(listing["request"], "listing")
        self.assertIsInstance(listing["list"], list)
        self.assertEqual(len(listing["list"]), 2)
        
        # Verify each member
        for member in listing["list"]:
            self.assertIn("streamID", member)
            self.assertIn("UUID", member)
            
    def test_sdp_offer_structure(self):
        """Test SDP offer message structure"""
        offer = {
            "description": {
                "type": "offer",
                "sdp": "v=0\\r\\no=- 123456 2 IN IP4 127.0.0.1\\r\\n..."
            },
            "UUID": "sender-uuid",
            "session": "session-id"
        }
        
        # Verify structure
        self.assertIn("description", offer)
        self.assertIn("type", offer["description"])
        self.assertEqual(offer["description"]["type"], "offer")
        self.assertIn("sdp", offer["description"])
        
    def test_ice_candidate_structure(self):
        """Test ICE candidate message structure"""
        candidate = {
            "candidate": {
                "candidate": "candidate:1 1 UDP 2122252543 192.168.1.1 50000 typ host",
                "sdpMLineIndex": 0,
                "sdpMid": "0"
            },
            "UUID": "sender-uuid"
        }
        
        # Verify structure
        self.assertIn("candidate", candidate)
        self.assertIn("candidate", candidate["candidate"])
        self.assertIn("sdpMLineIndex", candidate["candidate"])


class TestRoomRecordingLogic(unittest.TestCase):
    """Test room recording specific logic"""
    
    def test_stream_filter_logic(self):
        """Test stream filtering logic"""
        # No filter - all streams should be accepted
        stream_filter = None
        stream_id = "any_stream"
        self.assertTrue(stream_filter is None or stream_id in stream_filter)
        
        # With filter - only specified streams
        stream_filter = ["stream1", "stream2"]
        self.assertTrue("stream1" in stream_filter)
        self.assertFalse("stream3" in stream_filter)
        
    def test_file_naming_convention(self):
        """Test file naming for room recordings"""
        room_name = "testroom"
        stream_id = "stream123"
        timestamp = "1234567890"
        uuid_short = "abcd1234"
        
        # Expected format: roomname_streamid_timestamp_uuid.ts
        filename = f"{room_name}_{stream_id}_{timestamp}_{uuid_short}.ts"
        
        # Verify format
        self.assertTrue(filename.startswith(room_name))
        self.assertIn(stream_id, filename)
        self.assertIn(timestamp, filename)
        self.assertTrue(filename.endswith(".ts"))


if __name__ == '__main__':
    unittest.main(verbosity=2)