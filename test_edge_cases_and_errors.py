#!/usr/bin/env python3
"""
Test Edge Cases and Error Conditions for WebRTC Application
Tests various error scenarios and edge cases to ensure robustness
"""
import asyncio
import gc
import json
import logging
import os
import psutil
import pytest
import signal
import sys
import time
import threading
from unittest.mock import Mock, patch, MagicMock
from concurrent.futures import ThreadPoolExecutor

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
from gi.repository import Gst, GstWebRTC, GLib

# Add parent directory to path to import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from webrtc_connection import WebRTCConnection
from connection_manager import ConnectionManager

# Initialize GStreamer
Gst.init(None)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TestMaxConnections:
    """Test maximum connection limits"""
    
    @pytest.mark.asyncio
    async def test_max_connections_reached(self):
        """Test behavior when maximum number of connections is reached"""
        manager = ConnectionManager()
        max_connections = 50  # Simulate a reasonable max
        connections = []
        
        # Create connections up to the limit
        for i in range(max_connections):
            config = {
                'pipeline_string': 'videotestsrc ! queue ! webrtcbin name=webrtc',
                'receive_only': False
            }
            conn = await manager.create_connection(f"conn_{i}", f"stream_{i}", config)
            connections.append(conn)
        
        # Verify all connections were created
        assert len(manager.connections) == max_connections
        
        # Try to create one more connection - should handle gracefully
        try:
            # Simulate system resource exhaustion
            with patch('webrtc_connection.Gst.parse_launch') as mock_parse:
                mock_parse.side_effect = Exception("Resource exhausted")
                
                with pytest.raises(Exception) as exc_info:
                    await manager.create_connection("overflow", "overflow_stream", config)
                
                assert "Resource exhausted" in str(exc_info.value)
        finally:
            # Cleanup
            for conn_id in list(manager.connections.keys()):
                await manager.remove_connection(conn_id)
    
    @pytest.mark.asyncio
    async def test_connection_cleanup_on_limit(self):
        """Test that connections are properly cleaned up when limits are reached"""
        manager = ConnectionManager()
        
        # Track memory before
        process = psutil.Process()
        memory_before = process.memory_info().rss
        
        # Create and destroy many connections
        for batch in range(5):
            connections = []
            for i in range(10):
                config = {
                    'pipeline_string': 'videotestsrc ! queue ! webrtcbin name=webrtc',
                    'receive_only': False
                }
                conn = await manager.create_connection(
                    f"batch{batch}_conn{i}", 
                    f"stream_{i}", 
                    config
                )
                connections.append(conn)
            
            # Remove all connections
            for conn_id in list(manager.connections.keys()):
                await manager.remove_connection(conn_id)
            
            # Force garbage collection
            gc.collect()
            await asyncio.sleep(0.1)
        
        # Check memory hasn't grown excessively (allow 50MB growth)
        memory_after = process.memory_info().rss
        memory_growth = memory_after - memory_before
        assert memory_growth < 50 * 1024 * 1024, f"Memory grew by {memory_growth / 1024 / 1024:.2f}MB"


class TestCorruptSDP:
    """Test handling of corrupt or invalid SDP offers/answers"""
    
    @pytest.mark.asyncio
    async def test_invalid_sdp_offer(self):
        """Test handling of invalid SDP offers"""
        manager = ConnectionManager()
        config = {
            'pipeline_string': 'videotestsrc ! queue ! webrtcbin name=webrtc',
            'receive_only': False
        }
        
        connection = await manager.create_connection("test_conn", "test_stream", config)
        
        # Test various invalid SDP scenarios
        invalid_sdps = [
            None,  # None SDP
            "",    # Empty string
            "not valid sdp",  # Invalid format
            {"type": "offer"},  # Missing sdp field
            {"sdp": "v=0\r\n"},  # Incomplete SDP
            {"type": "answer", "sdp": "valid sdp but wrong type"},  # Wrong type
            {"type": "offer", "sdp": "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=-\r\n"},  # Missing required fields
        ]
        
        for invalid_sdp in invalid_sdps:
            try:
                await manager.handle_offer("test_conn", invalid_sdp)
            except Exception as e:
                # Should handle gracefully
                logger.info(f"Expected error for invalid SDP: {e}")
            
            # Connection should still be in manager
            assert "test_conn" in manager.connections
        
        await manager.remove_connection("test_conn")
    
    @pytest.mark.asyncio
    async def test_malformed_ice_candidates(self):
        """Test handling of malformed ICE candidates"""
        manager = ConnectionManager()
        config = {
            'pipeline_string': 'videotestsrc ! queue ! webrtcbin name=webrtc',
            'receive_only': False
        }
        
        connection = await manager.create_connection("test_conn", "test_stream", config)
        
        # Test various invalid ICE candidate scenarios
        invalid_candidates = [
            None,
            {},
            {"candidate": None},
            {"candidate": "", "sdpMLineIndex": 0},
            {"candidate": "invalid", "sdpMLineIndex": -1},
            {"candidate": "candidate:1 1 UDP 2130706431 192.168.1.1 12345 typ host"},  # Missing sdpMLineIndex
            {"sdpMLineIndex": 0},  # Missing candidate
        ]
        
        for invalid_candidate in invalid_candidates:
            try:
                await manager.add_ice_candidate("test_conn", invalid_candidate)
            except Exception as e:
                logger.info(f"Expected error for invalid ICE candidate: {e}")
        
        await manager.remove_connection("test_conn")


class TestGStreamerErrors:
    """Test recovery from GStreamer pipeline errors"""
    
    @pytest.mark.asyncio
    async def test_pipeline_creation_failure(self):
        """Test handling of pipeline creation failures"""
        manager = ConnectionManager()
        
        # Test invalid pipeline strings
        invalid_configs = [
            {'pipeline_string': ''},  # Empty pipeline
            {'pipeline_string': 'invalidelement ! webrtcbin name=webrtc'},  # Invalid element
            {'pipeline_string': 'videotestsrc !'},  # Incomplete pipeline
            {'pipeline_string': 'videotestsrc ! webrtcbin'},  # Missing webrtc name
        ]
        
        for i, config in enumerate(invalid_configs):
            try:
                await manager.create_connection(f"invalid_{i}", "stream", config)
            except Exception as e:
                logger.info(f"Expected error for invalid pipeline: {e}")
                # Connection should not be created
                assert f"invalid_{i}" not in manager.connections
    
    @pytest.mark.asyncio
    async def test_pipeline_state_change_failure(self):
        """Test handling of pipeline state change failures"""
        config = {
            'pipeline_string': 'videotestsrc ! queue ! webrtcbin name=webrtc',
            'receive_only': False
        }
        
        connection = WebRTCConnection("test", "stream", config)
        
        # Mock pipeline to fail state changes
        with patch.object(connection, 'create_pipeline') as mock_create:
            mock_pipeline = Mock()
            mock_pipeline.set_state.return_value = Gst.StateChangeReturn.FAILURE
            mock_pipeline.get_by_name.return_value = Mock()
            connection.pipeline = mock_pipeline
            connection.webrtc_bin = mock_pipeline.get_by_name.return_value
            
            # Try to start - should handle failure gracefully
            try:
                connection.start()
            except Exception as e:
                logger.info(f"Expected error on state change failure: {e}")
    
    @pytest.mark.asyncio
    async def test_pipeline_error_recovery(self):
        """Test recovery from pipeline errors during operation"""
        manager = ConnectionManager()
        config = {
            'pipeline_string': 'videotestsrc ! queue ! webrtcbin name=webrtc',
            'receive_only': False
        }
        
        connection = await manager.create_connection("test_conn", "test_stream", config)
        
        # Simulate pipeline error
        if connection.pipeline:
            # Force an error by setting invalid state
            connection.pipeline.set_state(Gst.State.NULL)
            
            # Try to perform operations - should handle gracefully
            try:
                connection.handle_offer({"type": "offer", "sdp": "dummy"})
            except Exception as e:
                logger.info(f"Expected error after pipeline failure: {e}")
        
        await manager.remove_connection("test_conn")


class TestNetworkDisconnections:
    """Test handling of network disconnections and reconnections"""
    
    @pytest.mark.asyncio
    async def test_ice_connection_failure(self):
        """Test handling of ICE connection failures"""
        connection = WebRTCConnection("test", "stream", {
            'pipeline_string': 'videotestsrc ! queue ! webrtcbin name=webrtc',
            'receive_only': False
        })
        connection.create_pipeline()
        
        # Simulate ICE connection state changes
        ice_states = [
            GstWebRTC.WebRTCICEConnectionState.NEW,
            GstWebRTC.WebRTCICEConnectionState.CHECKING,
            GstWebRTC.WebRTCICEConnectionState.FAILED,
            GstWebRTC.WebRTCICEConnectionState.DISCONNECTED,
            GstWebRTC.WebRTCICEConnectionState.CLOSED
        ]
        
        for state in ice_states:
            # Simulate state change
            connection.ice_connection_state = state
            connection._on_ice_connection_state(connection.webrtc_bin, None)
            
            # Verify connection handles state appropriately
            if state in [GstWebRTC.WebRTCICEConnectionState.FAILED,
                        GstWebRTC.WebRTCICEConnectionState.DISCONNECTED,
                        GstWebRTC.WebRTCICEConnectionState.CLOSED]:
                assert not connection.is_connected
        
        connection.stop()
    
    @pytest.mark.asyncio
    async def test_reconnection_handling(self):
        """Test handling of reconnection attempts"""
        manager = ConnectionManager()
        config = {
            'pipeline_string': 'videotestsrc ! queue ! webrtcbin name=webrtc',
            'receive_only': False
        }
        
        # Create initial connection
        connection = await manager.create_connection("test_conn", "test_stream", config)
        
        # Simulate disconnection
        if connection.webrtc_bin:
            connection.ice_connection_state = GstWebRTC.WebRTCICEConnectionState.DISCONNECTED
            connection.is_connected = False
        
        # Attempt to handle new offer (simulating reconnection)
        try:
            await manager.handle_offer("test_conn", {
                "type": "offer",
                "sdp": "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\n"
            })
        except Exception as e:
            logger.info(f"Reconnection handling: {e}")
        
        await manager.remove_connection("test_conn")


class TestMemoryLeaks:
    """Test for memory leaks when creating/destroying many connections"""
    
    @pytest.mark.asyncio
    async def test_connection_lifecycle_memory(self):
        """Test memory usage during connection lifecycle"""
        manager = ConnectionManager()
        process = psutil.Process()
        
        # Get baseline memory
        gc.collect()
        baseline_memory = process.memory_info().rss
        
        # Create and destroy connections repeatedly
        for iteration in range(10):
            connections = []
            
            # Create batch of connections
            for i in range(20):
                config = {
                    'pipeline_string': 'videotestsrc ! queue ! webrtcbin name=webrtc',
                    'receive_only': False
                }
                conn = await manager.create_connection(
                    f"iter{iteration}_conn{i}",
                    f"stream_{i}",
                    config
                )
                connections.append(conn)
            
            # Simulate some activity
            for conn_id in manager.connections:
                conn = manager.connections[conn_id]
                if conn.pipeline:
                    conn.pipeline.set_state(Gst.State.PLAYING)
            
            await asyncio.sleep(0.1)
            
            # Stop and remove all connections
            for conn_id in list(manager.connections.keys()):
                await manager.remove_connection(conn_id)
            
            # Force garbage collection
            gc.collect()
            await asyncio.sleep(0.1)
        
        # Check final memory usage
        final_memory = process.memory_info().rss
        memory_increase = final_memory - baseline_memory
        memory_increase_mb = memory_increase / (1024 * 1024)
        
        logger.info(f"Memory increase: {memory_increase_mb:.2f} MB")
        
        # Allow some memory increase but flag potential leaks (threshold: 100MB)
        assert memory_increase_mb < 100, f"Potential memory leak: {memory_increase_mb:.2f} MB increase"
    
    @pytest.mark.asyncio
    async def test_circular_reference_cleanup(self):
        """Test cleanup of circular references"""
        manager = ConnectionManager()
        
        # Create connections with potential circular references
        config = {
            'pipeline_string': 'videotestsrc ! queue ! webrtcbin name=webrtc',
            'receive_only': False
        }
        
        connection = await manager.create_connection("test", "stream", config)
        
        # Create circular reference through callbacks
        circular_ref = {'conn': connection}
        connection.test_circular = circular_ref
        
        # Remove connection
        await manager.remove_connection("test")
        
        # Delete local reference
        del connection
        del circular_ref
        
        # Force garbage collection
        gc.collect()
        
        # Verify cleanup
        assert len(manager.connections) == 0


class TestRaceConditions:
    """Test race conditions in concurrent operations"""
    
    @pytest.mark.asyncio
    async def test_concurrent_connection_creation(self):
        """Test concurrent creation of connections"""
        manager = ConnectionManager()
        
        async def create_connection(conn_id):
            config = {
                'pipeline_string': 'videotestsrc ! queue ! webrtcbin name=webrtc',
                'receive_only': False
            }
            try:
                return await manager.create_connection(conn_id, f"stream_{conn_id}", config)
            except Exception as e:
                logger.error(f"Error creating connection {conn_id}: {e}")
                return None
        
        # Create many connections concurrently
        tasks = []
        num_connections = 20
        
        for i in range(num_connections):
            tasks.append(create_connection(f"concurrent_{i}"))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successful connections
        successful = sum(1 for r in results if r is not None and not isinstance(r, Exception))
        logger.info(f"Successfully created {successful}/{num_connections} connections")
        
        # Verify no duplicate connections
        assert len(manager.connections) == successful
        
        # Cleanup
        for conn_id in list(manager.connections.keys()):
            await manager.remove_connection(conn_id)
    
    @pytest.mark.asyncio
    async def test_concurrent_offer_handling(self):
        """Test concurrent handling of offers for the same connection"""
        manager = ConnectionManager()
        config = {
            'pipeline_string': 'videotestsrc ! queue ! webrtcbin name=webrtc',
            'receive_only': False
        }
        
        connection = await manager.create_connection("test", "stream", config)
        
        # Mock the handle_offer method to simulate processing time
        original_handle = connection.handle_offer
        processing_count = 0
        
        def slow_handle_offer(offer):
            nonlocal processing_count
            processing_count += 1
            time.sleep(0.1)  # Simulate processing
            return original_handle(offer)
        
        connection.handle_offer = slow_handle_offer
        
        # Send multiple offers concurrently
        async def send_offer(index):
            offer = {
                "type": "offer",
                "sdp": f"v=0\r\no=- {index} 0 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\n"
            }
            try:
                await manager.handle_offer("test", offer)
            except Exception as e:
                logger.error(f"Error handling offer {index}: {e}")
        
        tasks = [send_offer(i) for i in range(5)]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify all offers were processed
        assert processing_count == 5
        
        await manager.remove_connection("test")
    
    @pytest.mark.asyncio
    async def test_concurrent_ice_candidates(self):
        """Test concurrent addition of ICE candidates"""
        manager = ConnectionManager()
        config = {
            'pipeline_string': 'videotestsrc ! queue ! webrtcbin name=webrtc',
            'receive_only': False
        }
        
        connection = await manager.create_connection("test", "stream", config)
        
        # Send many ICE candidates concurrently
        async def add_candidate(index):
            candidate = {
                "candidate": f"candidate:{index} 1 UDP 2130706431 192.168.1.{index} 5000{index} typ host",
                "sdpMLineIndex": 0
            }
            try:
                await manager.add_ice_candidate("test", candidate)
            except Exception as e:
                logger.error(f"Error adding candidate {index}: {e}")
        
        tasks = [add_candidate(i) for i in range(50)]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        await manager.remove_connection("test")


class TestInvalidInputs:
    """Test handling of invalid room names and stream IDs"""
    
    @pytest.mark.asyncio
    async def test_invalid_connection_ids(self):
        """Test handling of invalid connection IDs"""
        manager = ConnectionManager()
        config = {
            'pipeline_string': 'videotestsrc ! queue ! webrtcbin name=webrtc',
            'receive_only': False
        }
        
        # Test various invalid IDs
        invalid_ids = [
            "",  # Empty string
            None,  # None
            " ",  # Whitespace only
            "a" * 1000,  # Very long ID
            "../../etc/passwd",  # Path traversal attempt
            "conn\x00id",  # Null byte
            "conn\nid",  # Newline
            "😀🎉",  # Unicode/emoji
            "<script>alert('xss')</script>",  # XSS attempt
        ]
        
        for invalid_id in invalid_ids:
            try:
                if invalid_id is not None:  # Skip None for string operations
                    await manager.create_connection(invalid_id, "stream", config)
            except Exception as e:
                logger.info(f"Expected error for invalid ID '{invalid_id}': {e}")
    
    @pytest.mark.asyncio
    async def test_invalid_stream_ids(self):
        """Test handling of invalid stream IDs"""
        manager = ConnectionManager()
        config = {
            'pipeline_string': 'videotestsrc ! queue ! webrtcbin name=webrtc',
            'receive_only': False
        }
        
        # Test various invalid stream IDs
        invalid_streams = [
            "",
            None,
            "stream" * 100,  # Very long
            "stream/../../../",  # Path traversal
            "stream\r\n",  # CRLF injection
            "stream'; DROP TABLE streams;--",  # SQL injection attempt
        ]
        
        for i, invalid_stream in enumerate(invalid_streams):
            try:
                if invalid_stream is not None:
                    await manager.create_connection(f"conn_{i}", invalid_stream, config)
            except Exception as e:
                logger.info(f"Expected error for invalid stream '{invalid_stream}': {e}")


class TestCodecNegotiation:
    """Test codec negotiation failures"""
    
    @pytest.mark.asyncio
    async def test_unsupported_codec_offer(self):
        """Test handling of offers with unsupported codecs"""
        manager = ConnectionManager()
        config = {
            'pipeline_string': 'videotestsrc ! queue ! webrtcbin name=webrtc',
            'receive_only': False
        }
        
        connection = await manager.create_connection("test", "stream", config)
        
        # SDP with unsupported codec
        unsupported_sdp = {
            "type": "offer",
            "sdp": """v=0
o=- 0 0 IN IP4 127.0.0.1
s=-
t=0 0
m=video 9 UDP/TLS/RTP/SAVPF 200
c=IN IP4 0.0.0.0
a=rtcp:9 IN IP4 0.0.0.0
a=ice-ufrag:test
a=ice-pwd:test
a=fingerprint:sha-256 00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00
a=setup:actpass
a=rtpmap:200 UNSUPPORTED/90000
"""
        }
        
        try:
            await manager.handle_offer("test", unsupported_sdp)
        except Exception as e:
            logger.info(f"Expected error for unsupported codec: {e}")
        
        await manager.remove_connection("test")
    
    @pytest.mark.asyncio
    async def test_codec_mismatch(self):
        """Test handling of codec mismatches between offer and capabilities"""
        config = {
            'pipeline_string': 'videotestsrc ! video/x-raw,format=I420 ! videoconvert ! vp8enc ! webrtcbin name=webrtc',
            'receive_only': False
        }
        
        connection = WebRTCConnection("test", "stream", config)
        connection.create_pipeline()
        
        # SDP requesting H264 when pipeline only supports VP8
        h264_sdp = {
            "type": "offer",
            "sdp": """v=0
o=- 0 0 IN IP4 127.0.0.1
s=-
t=0 0
m=video 9 UDP/TLS/RTP/SAVPF 96
c=IN IP4 0.0.0.0
a=rtcp:9 IN IP4 0.0.0.0
a=ice-ufrag:test
a=ice-pwd:test
a=fingerprint:sha-256 00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00
a=setup:actpass
a=rtpmap:96 H264/90000
a=fmtp:96 level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42e01f
"""
        }
        
        try:
            connection.handle_offer(h264_sdp)
        except Exception as e:
            logger.info(f"Expected error for codec mismatch: {e}")
        
        connection.stop()


class TestSystemResourceExhaustion:
    """Test behavior under system resource exhaustion"""
    
    @pytest.mark.asyncio
    async def test_file_descriptor_exhaustion(self):
        """Test handling when file descriptors are exhausted"""
        manager = ConnectionManager()
        
        # Store original limit
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        
        try:
            # Set a low limit for file descriptors
            resource.setrlimit(resource.RLIMIT_NOFILE, (100, hard))
            
            # Try to create many connections
            created = 0
            for i in range(50):
                try:
                    config = {
                        'pipeline_string': 'videotestsrc ! queue ! webrtcbin name=webrtc',
                        'receive_only': False
                    }
                    await manager.create_connection(f"fd_test_{i}", f"stream_{i}", config)
                    created += 1
                except Exception as e:
                    logger.info(f"Expected error after {created} connections: {e}")
                    break
            
            logger.info(f"Created {created} connections before hitting limit")
            
        finally:
            # Restore original limit
            resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))
            
            # Cleanup
            for conn_id in list(manager.connections.keys()):
                await manager.remove_connection(conn_id)
    
    @pytest.mark.asyncio
    async def test_thread_exhaustion(self):
        """Test handling when thread pool is exhausted"""
        manager = ConnectionManager()
        
        # Create a small thread pool to simulate exhaustion
        small_pool = ThreadPoolExecutor(max_workers=2)
        
        async def create_with_thread_pool(conn_id):
            config = {
                'pipeline_string': 'videotestsrc ! queue ! webrtcbin name=webrtc',
                'receive_only': False
            }
            
            # Simulate thread pool usage
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(small_pool, time.sleep, 0.1)
            
            return await manager.create_connection(conn_id, f"stream_{conn_id}", config)
        
        # Try to create many connections concurrently
        tasks = []
        for i in range(10):
            tasks.append(create_with_thread_pool(f"thread_test_{i}"))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successful connections
        successful = sum(1 for r in results if not isinstance(r, Exception))
        logger.info(f"Created {successful}/10 connections with limited thread pool")
        
        # Cleanup
        small_pool.shutdown(wait=True)
        for conn_id in list(manager.connections.keys()):
            await manager.remove_connection(conn_id)


class TestSignalHandling:
    """Test handling of system signals and interrupts"""
    
    @pytest.mark.asyncio
    async def test_graceful_shutdown_on_sigterm(self):
        """Test graceful shutdown when receiving SIGTERM"""
        manager = ConnectionManager()
        
        # Create some connections
        for i in range(5):
            config = {
                'pipeline_string': 'videotestsrc ! queue ! webrtcbin name=webrtc',
                'receive_only': False
            }
            await manager.create_connection(f"sig_test_{i}", f"stream_{i}", config)
        
        # Set up signal handler
        shutdown_complete = asyncio.Event()
        
        def handle_sigterm(signum, frame):
            logger.info("Received SIGTERM, shutting down...")
            asyncio.create_task(shutdown_connections())
        
        async def shutdown_connections():
            for conn_id in list(manager.connections.keys()):
                await manager.remove_connection(conn_id)
            shutdown_complete.set()
        
        # Install signal handler
        old_handler = signal.signal(signal.SIGTERM, handle_sigterm)
        
        try:
            # Send SIGTERM to self
            os.kill(os.getpid(), signal.SIGTERM)
            
            # Wait for shutdown
            await asyncio.wait_for(shutdown_complete.wait(), timeout=5.0)
            
            # Verify all connections were cleaned up
            assert len(manager.connections) == 0
            
        finally:
            # Restore original handler
            signal.signal(signal.SIGTERM, old_handler)


class TestEdgeCaseScenarios:
    """Test various edge case scenarios"""
    
    @pytest.mark.asyncio
    async def test_rapid_connection_cycling(self):
        """Test rapid creation and destruction of connections"""
        manager = ConnectionManager()
        
        # Rapidly create and destroy connections
        for i in range(20):
            config = {
                'pipeline_string': 'videotestsrc ! queue ! webrtcbin name=webrtc',
                'receive_only': False
            }
            
            # Create connection
            conn = await manager.create_connection(f"rapid_{i}", f"stream_{i}", config)
            
            # Immediately destroy it
            await manager.remove_connection(f"rapid_{i}")
            
            # No delay between iterations
        
        # Verify no connections remain
        assert len(manager.connections) == 0
    
    @pytest.mark.asyncio
    async def test_connection_with_no_ice_servers(self):
        """Test connection creation without ICE servers"""
        config = {
            'pipeline_string': 'videotestsrc ! queue ! webrtcbin name=webrtc',
            'receive_only': False,
            'ice_servers': {}  # Empty ICE servers
        }
        
        connection = WebRTCConnection("test", "stream", config)
        connection.create_pipeline()
        
        # Should work with just host candidates
        assert connection.webrtc_bin is not None
        
        connection.stop()
    
    @pytest.mark.asyncio
    async def test_duplicate_connection_ids(self):
        """Test handling of duplicate connection IDs"""
        manager = ConnectionManager()
        config = {
            'pipeline_string': 'videotestsrc ! queue ! webrtcbin name=webrtc',
            'receive_only': False
        }
        
        # Create first connection
        conn1 = await manager.create_connection("duplicate", "stream1", config)
        assert conn1 is not None
        
        # Try to create another with same ID
        conn2 = await manager.create_connection("duplicate", "stream2", config)
        
        # Should return existing connection
        assert conn2 == conn1
        assert len(manager.connections) == 1
        
        await manager.remove_connection("duplicate")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])