#!/usr/bin/env python3
"""
Unit tests for WebRTC components
"""
import unittest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import asyncio
import sys

# Mock GStreamer before importing our modules
sys.modules['gi'] = MagicMock()
sys.modules['gi.repository'] = MagicMock()
sys.modules['gi.repository.Gst'] = MagicMock()
sys.modules['gi.repository.GstWebRTC'] = MagicMock()
sys.modules['gi.repository.GstSdp'] = MagicMock()

# Now import our modules
from webrtc_connection import WebRTCConnection
from connection_manager import ConnectionManager, RoomRecordingManager


class TestWebRTCConnection(unittest.TestCase):
    """Test WebRTCConnection class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.connection_id = "test-conn-123"
        self.stream_id = "test-stream"
        self.pipeline_config = {
            'receive_only': True,
            'record': True,
            'pipeline_string': 'webrtcbin name=webrtc'
        }
        
    @patch('webrtc_connection.Gst')
    def test_connection_creation(self, mock_gst):
        """Test creating a WebRTC connection"""
        # Create connection
        conn = WebRTCConnection(self.connection_id, self.stream_id, self.pipeline_config)
        
        # Verify initialization
        self.assertEqual(conn.connection_id, self.connection_id)
        self.assertEqual(conn.stream_id, self.stream_id)
        self.assertIsNone(conn.session_id)
        self.assertFalse(conn.is_connected)
        self.assertFalse(conn.is_recording)
        
    @patch('webrtc_connection.Gst')
    def test_pipeline_creation(self, mock_gst):
        """Test pipeline creation"""
        # Mock GStreamer elements
        mock_pipeline = MagicMock()
        mock_webrtc = MagicMock()
        mock_gst.parse_launch.return_value = mock_pipeline
        mock_pipeline.get_by_name.return_value = mock_webrtc
        
        # Create connection and pipeline
        conn = WebRTCConnection(self.connection_id, self.stream_id, self.pipeline_config)
        conn.create_pipeline()
        
        # Verify pipeline was created
        mock_gst.parse_launch.assert_called()
        mock_pipeline.get_by_name.assert_called_with('webrtc')
        self.assertEqual(conn.pipeline, mock_pipeline)
        self.assertEqual(conn.webrtc_bin, mock_webrtc)
        
    def test_ice_configuration(self):
        """Test ICE server configuration"""
        config = {
            'receive_only': True,
            'ice_servers': {
                'stun': 'stun://stun.example.com:3478',
                'turn': 'turn://user:pass@turn.example.com:3478'
            }
        }
        
        conn = WebRTCConnection(self.connection_id, self.stream_id, config)
        
        # Verify ICE config is stored
        self.assertIn('ice_servers', conn.pipeline_config)
        self.assertEqual(conn.pipeline_config['ice_servers']['stun'], 
                        'stun://stun.example.com:3478')
        
    def test_stats_generation(self):
        """Test statistics generation"""
        conn = WebRTCConnection(self.connection_id, self.stream_id, self.pipeline_config)
        
        stats = conn.get_stats()
        
        # Verify stats structure
        self.assertIn('connection_id', stats)
        self.assertIn('stream_id', stats)
        self.assertIn('is_connected', stats)
        self.assertIn('is_recording', stats)
        self.assertEqual(stats['connection_id'], self.connection_id)
        self.assertEqual(stats['stream_id'], self.stream_id)
        

class TestConnectionManager(unittest.TestCase):
    """Test ConnectionManager class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.manager = ConnectionManager()
        
    @patch('connection_manager.WebRTCConnection')
    async def test_create_connection(self, mock_conn_class):
        """Test creating a connection through manager"""
        # Mock connection
        mock_conn = MagicMock()
        mock_conn_class.return_value = mock_conn
        
        # Create connection
        conn_id = "test-123"
        stream_id = "stream-456"
        config = {'test': True}
        
        result = await self.manager.create_connection(conn_id, stream_id, config)
        
        # Verify
        mock_conn_class.assert_called_with(conn_id, stream_id, config)
        self.assertEqual(result, mock_conn)
        self.assertIn(conn_id, self.manager.connections)
        
    async def test_duplicate_connection(self):
        """Test handling duplicate connection IDs"""
        conn_id = "test-123"
        
        # Create first connection
        with patch('connection_manager.WebRTCConnection') as mock_conn:
            mock_instance = MagicMock()
            mock_conn.return_value = mock_instance
            
            conn1 = await self.manager.create_connection(conn_id, "stream1", {})
            conn2 = await self.manager.create_connection(conn_id, "stream2", {})
            
            # Should return the same connection
            self.assertEqual(conn1, conn2)
            # Constructor should only be called once
            mock_conn.assert_called_once()
            
    async def test_remove_connection(self):
        """Test removing a connection"""
        conn_id = "test-123"
        
        # Create connection
        with patch('connection_manager.WebRTCConnection') as mock_conn:
            mock_instance = MagicMock()
            mock_conn.return_value = mock_instance
            
            await self.manager.create_connection(conn_id, "stream", {})
            self.assertIn(conn_id, self.manager.connections)
            
            # Remove it
            await self.manager.remove_connection(conn_id)
            
            # Verify
            self.assertNotIn(conn_id, self.manager.connections)
            mock_instance.stop.assert_called_once()
            
    def test_get_stats(self):
        """Test getting manager statistics"""
        stats = self.manager.get_stats()
        
        # Verify structure
        self.assertIn('total_connections', stats)
        self.assertIn('connections', stats)
        self.assertEqual(stats['total_connections'], 0)
        self.assertIsInstance(stats['connections'], list)
        

class TestRoomRecordingManager(unittest.TestCase):
    """Test RoomRecordingManager class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.room_name = "test-room"
        self.manager = RoomRecordingManager(self.room_name)
        
    async def test_handle_room_listing(self):
        """Test processing room listing"""
        room_members = [
            {'streamID': 'stream1', 'UUID': 'uuid1'},
            {'streamID': 'stream2', 'UUID': 'uuid2'},
            {'streamID': 'stream3', 'UUID': 'uuid3'}
        ]
        
        await self.manager.handle_room_listing(room_members)
        
        # Verify streams are tracked
        self.assertEqual(len(self.manager.room_streams), 3)
        self.assertIn('uuid1', self.manager.room_streams)
        self.assertEqual(self.manager.room_streams['uuid1']['streamID'], 'stream1')
        self.assertFalse(self.manager.room_streams['uuid1']['recording'])
        
    @patch('connection_manager.WebRTCConnection')
    async def test_create_recording_connection(self, mock_conn_class):
        """Test creating a recording connection"""
        # Mock connection
        mock_conn = MagicMock()
        mock_conn_class.return_value = mock_conn
        
        uuid = "test-uuid"
        stream_id = "test-stream"
        
        result = await self.manager.create_recording_connection(uuid, stream_id)
        
        # Verify connection was created with recording config
        self.assertEqual(result, mock_conn)
        self.assertIn(uuid, self.manager.room_streams)
        self.assertTrue(self.manager.room_streams[uuid]['recording'])
        
        # Check pipeline config
        call_args = mock_conn_class.call_args
        config = call_args[0][2]  # third argument is pipeline_config
        self.assertTrue(config['receive_only'])
        self.assertTrue(config['record'])
        self.assertEqual(config['room_name'], self.room_name)
        
    def test_get_room_status(self):
        """Test getting room status"""
        # Add some test streams
        self.manager.room_streams = {
            'uuid1': {'streamID': 'stream1', 'recording': True},
            'uuid2': {'streamID': 'stream2', 'recording': False}
        }
        
        status = self.manager.get_room_status()
        
        # Verify status structure
        self.assertEqual(status['room_name'], self.room_name)
        self.assertEqual(status['total_streams'], 2)
        self.assertIn('streams', status)
        self.assertEqual(len(status['streams']), 2)
        

def run_async_test(coro):
    """Helper to run async tests"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# Patch async test methods
for test_class in [TestConnectionManager, TestRoomRecordingManager]:
    for attr_name in dir(test_class):
        attr = getattr(test_class, attr_name)
        if asyncio.iscoroutinefunction(attr) and attr_name.startswith('test_'):
            wrapped = lambda self, coro=attr: run_async_test(coro(self))
            wrapped.__name__ = attr_name
            setattr(test_class, attr_name, wrapped)


if __name__ == '__main__':
    unittest.main(verbosity=2)