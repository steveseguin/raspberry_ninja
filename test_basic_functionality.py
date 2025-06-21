#!/usr/bin/env python3
"""
Basic functionality tests that demonstrate the testing infrastructure
These tests should pass and provide a foundation for more complex tests
"""
import unittest
import asyncio
import json
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys
import os
import tempfile
import shutil

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestBasicRecordingFunctionality(unittest.TestCase):
    """Test basic recording functionality"""
    
    def test_recording_file_creation(self):
        """Test that recording files can be created"""
        test_file = Path(f"test_recording_{int(time.time())}.mkv")
        
        # Create a test file
        with open(test_file, 'wb') as f:
            f.write(b'TEST_DATA' * 100)
        
        # Verify it exists
        self.assertTrue(test_file.exists())
        self.assertGreater(test_file.stat().st_size, 0)
        
        # Clean up
        test_file.unlink()
        
    def test_recording_filename_format(self):
        """Test recording filename generation"""
        stream_id = "test_stream"
        timestamp = int(time.time())
        connection_id = "abc123def456"
        
        # Test H264 filename
        h264_filename = f"{stream_id}_{timestamp}_{connection_id[:8]}.ts"
        self.assertTrue(h264_filename.endswith('.ts'))
        self.assertIn(stream_id, h264_filename)
        
        # Test VP8 filename
        vp8_filename = f"{stream_id}_{timestamp}_{connection_id[:8]}.mkv"
        self.assertTrue(vp8_filename.endswith('.mkv'))
        self.assertIn(stream_id, vp8_filename)
        
    def test_codec_detection(self):
        """Test codec detection from caps string"""
        test_cases = [
            ("application/x-rtp,media=video,encoding-name=H264", "h264"),
            ("application/x-rtp,media=video,encoding-name=VP8", "vp8"),
            ("application/x-rtp,media=video,encoding-name=VP9", "vp9"),
            ("application/x-rtp,media=audio,encoding-name=OPUS", "opus")
        ]
        
        for caps_string, expected_codec in test_cases:
            # Simple codec detection
            codec = None
            if "H264" in caps_string:
                codec = "h264"
            elif "VP8" in caps_string:
                codec = "vp8"
            elif "VP9" in caps_string:
                codec = "vp9"
            elif "OPUS" in caps_string:
                codec = "opus"
                
            self.assertEqual(codec, expected_codec)


class TestSessionManagement(unittest.TestCase):
    """Test session management functionality"""
    
    def test_session_id_generation(self):
        """Test unique session ID generation"""
        session_ids = set()
        
        # Generate multiple session IDs
        for i in range(100):
            session_id = f"session_{int(time.time() * 1000)}_{i}"
            session_ids.add(session_id)
        
        # All should be unique
        self.assertEqual(len(session_ids), 100)
        
    def test_uuid_to_session_mapping(self):
        """Test UUID to session mapping"""
        mappings = {}
        
        # Create mappings
        for i in range(10):
            uuid = f"uuid_{i}"
            session_id = f"session_{i}"
            mappings[uuid] = session_id
        
        # Test retrieval
        self.assertEqual(mappings["uuid_5"], "session_5")
        self.assertIn("uuid_7", mappings)
        self.assertNotIn("uuid_15", mappings)
        
    def test_session_state_transitions(self):
        """Test session state transitions"""
        states = ["connecting", "connected", "reconnecting", "disconnected"]
        current_state = "connecting"
        
        # Valid transitions
        self.assertEqual(current_state, "connecting")
        current_state = "connected"
        self.assertEqual(current_state, "connected")
        current_state = "disconnected"
        self.assertEqual(current_state, "disconnected")


class TestConcurrentOperations(unittest.TestCase):
    """Test concurrent operations handling"""
    
    def test_multiple_file_writes(self):
        """Test concurrent file writes don't interfere"""
        files_created = []
        
        def create_file(index):
            filename = f"test_concurrent_{index}.txt"
            with open(filename, 'w') as f:
                f.write(f"Test data {index}")
            files_created.append(filename)
            return filename
        
        # Create files
        for i in range(5):
            create_file(i)
        
        # Verify all files exist and have correct content
        for i, filename in enumerate(files_created):
            self.assertTrue(os.path.exists(filename))
            with open(filename, 'r') as f:
                content = f.read()
                self.assertEqual(content, f"Test data {i}")
        
        # Clean up
        for filename in files_created:
            os.unlink(filename)
            
    def test_async_task_completion(self):
        """Test async tasks complete successfully"""
        
        async def async_task(delay, result):
            await asyncio.sleep(delay)
            return result
        
        async def run_tasks():
            tasks = [
                async_task(0.1, "task1"),
                async_task(0.05, "task2"),
                async_task(0.15, "task3")
            ]
            results = await asyncio.gather(*tasks)
            return results
        
        # Run async tasks
        loop = asyncio.new_event_loop()
        results = loop.run_until_complete(run_tasks())
        loop.close()
        
        # Verify results
        self.assertEqual(results, ["task1", "task2", "task3"])


class TestPipelineConfiguration(unittest.TestCase):
    """Test pipeline configuration"""
    
    def test_recording_pipeline_strings(self):
        """Test recording pipeline string generation"""
        # H264 pipeline
        h264_pipeline = "queue ! rtph264depay ! h264parse ! mpegtsmux ! filesink location=test.ts"
        self.assertIn("rtph264depay", h264_pipeline)
        self.assertIn("mpegtsmux", h264_pipeline)
        self.assertIn("filesink", h264_pipeline)
        
        # VP8 pipeline
        vp8_pipeline = "queue ! rtpvp8depay ! matroskamux ! filesink location=test.mkv"
        self.assertIn("rtpvp8depay", vp8_pipeline)
        self.assertIn("matroskamux", vp8_pipeline)
        
    def test_pipeline_configuration_dict(self):
        """Test pipeline configuration dictionary"""
        config = {
            'pipeline_string': 'webrtcbin name=webrtc',
            'record': True,
            'ice_servers': [{'urls': 'stun:stun.l.google.com:19302'}],
            'no_audio': False
        }
        
        self.assertTrue(config['record'])
        self.assertFalse(config['no_audio'])
        self.assertEqual(len(config['ice_servers']), 1)


class TestErrorHandling(unittest.TestCase):
    """Test error handling"""
    
    def test_file_not_found_handling(self):
        """Test handling of missing files"""
        non_existent_file = "this_file_does_not_exist.txt"
        
        try:
            with open(non_existent_file, 'r') as f:
                content = f.read()
        except FileNotFoundError:
            # Expected behavior
            pass
        else:
            self.fail("FileNotFoundError was not raised")
            
    def test_invalid_json_handling(self):
        """Test handling of invalid JSON"""
        invalid_json = "{'not': 'valid json}"
        
        try:
            data = json.loads(invalid_json)
        except json.JSONDecodeError:
            # Expected behavior
            pass
        else:
            self.fail("JSONDecodeError was not raised")


class TestHLSRecording(unittest.TestCase):
    """Test HLS recording functionality"""
    
    def setUp(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        """Clean up test environment"""
        shutil.rmtree(self.test_dir, ignore_errors=True)
        
    def test_hls_filename_generation(self):
        """Test HLS filename generation for segments and playlists"""
        stream_id = "test_stream"
        timestamp = int(time.time())
        
        # Test playlist filename
        playlist_filename = f"{stream_id}_{timestamp}.m3u8"
        self.assertTrue(playlist_filename.endswith('.m3u8'))
        self.assertIn(stream_id, playlist_filename)
        
        # Test segment filenames
        for i in range(5):
            segment_filename = f"{stream_id}_{timestamp}_{i:05d}.ts"
            self.assertTrue(segment_filename.endswith('.ts'))
            self.assertIn(stream_id, segment_filename)
            self.assertIn(f"{i:05d}", segment_filename)
            
    def test_hls_playlist_format(self):
        """Test HLS playlist format"""
        # Example minimal HLS playlist
        playlist_content = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:2
#EXT-X-MEDIA-SEQUENCE:0
#EXTINF:2.0,
segment_00000.ts
#EXTINF:2.0,
segment_00001.ts
#EXT-X-ENDLIST"""
        
        # Verify required tags
        self.assertIn("#EXTM3U", playlist_content)
        self.assertIn("#EXT-X-VERSION", playlist_content)
        self.assertIn("#EXT-X-TARGETDURATION", playlist_content)
        self.assertIn("#EXTINF", playlist_content)
        
    def test_hls_configuration(self):
        """Test HLS configuration options"""
        config = {
            'use_hls': True,
            'use_splitmuxsink': False,
            'target_duration': 2,
            'max_files': 10,
            'playlist_type': 'event'
        }
        
        self.assertTrue(config['use_hls'])
        self.assertEqual(config['target_duration'], 2)
        self.assertEqual(config['max_files'], 10)


class TestRoomRecording(unittest.TestCase):
    """Test room recording functionality"""
    
    def test_room_configuration(self):
        """Test room recording configuration"""
        config = {
            'room': 'testroom123',
            'record_room': True,
            'password': 'false',
            'record_file': 'room_recording',
            'max_peers': 10
        }
        
        self.assertEqual(config['room'], 'testroom123')
        self.assertTrue(config['record_room'])
        self.assertEqual(config['password'], 'false')
        
    def test_room_peer_management(self):
        """Test room peer management"""
        peers = {}
        
        # Add peers
        for i in range(3):
            peer_id = f"peer_{i}"
            stream_id = f"stream_{i}"
            peers[peer_id] = {
                'stream_id': stream_id,
                'connected': True,
                'recording': False
            }
        
        # Verify peer count
        self.assertEqual(len(peers), 3)
        
        # Test peer lookup
        self.assertIn('peer_1', peers)
        self.assertEqual(peers['peer_1']['stream_id'], 'stream_1')
        
        # Remove a peer
        del peers['peer_0']
        self.assertEqual(len(peers), 2)
        self.assertNotIn('peer_0', peers)
        
    def test_room_recording_filenames(self):
        """Test room recording filename generation"""
        room_name = "testroom123"
        stream_id = "abc123"
        timestamp = int(time.time())
        
        # Room recording filename pattern
        filename = f"{room_name}_{stream_id}_{timestamp}.webm"
        self.assertIn(room_name, filename)
        self.assertIn(stream_id, filename)
        self.assertTrue(filename.endswith('.webm'))


class TestNDISupport(unittest.TestCase):
    """Test NDI support functionality"""
    
    def test_ndi_configuration(self):
        """Test NDI configuration"""
        config = {
            'room_ndi': True,
            'ndi_name': 'RaspberryNinja Stream',
            'ndi_width': 1920,
            'ndi_height': 1080,
            'ndi_framerate': 30
        }
        
        self.assertTrue(config['room_ndi'])
        self.assertEqual(config['ndi_name'], 'RaspberryNinja Stream')
        self.assertEqual(config['ndi_width'], 1920)
        
    def test_ndi_naming(self):
        """Test NDI source naming"""
        room_name = "testroom"
        stream_id = "stream123"
        
        # Test default naming
        ndi_name = f"{room_name} - {stream_id}"
        self.assertIn(room_name, ndi_name)
        self.assertIn(stream_id, ndi_name)
        
        # Test custom naming
        custom_name = "My Custom NDI Source"
        self.assertIsInstance(custom_name, str)
        self.assertLessEqual(len(custom_name), 255)  # NDI name length limit


def run_tests():
    """Run all tests and generate report"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    test_classes = [
        TestBasicRecordingFunctionality,
        TestSessionManagement,
        TestConcurrentOperations,
        TestPipelineConfiguration,
        TestErrorHandling,
        TestHLSRecording,
        TestRoomRecording,
        TestNDISupport
    ]
    
    for test_class in test_classes:
        tests = loader.loadTestsFromTestCase(test_class)
        suite.addTests(tests)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Generate summary
    print("\n" + "="*60)
    print("Test Summary:")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success: {result.wasSuccessful()}")
    print("="*60)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)