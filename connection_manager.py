#!/usr/bin/env python3
"""
Connection Manager
Manages multiple WebRTC connections for room recording and multi-stream scenarios
"""
import asyncio
import logging
from typing import Dict, Optional, Callable
from webrtc_connection import WebRTCConnection

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages multiple WebRTC connections"""
    
    def __init__(self):
        """Initialize the connection manager"""
        self.connections: Dict[str, WebRTCConnection] = {}
        self.connection_lock = asyncio.Lock()
        
        # Callbacks
        self.on_ice_candidate: Optional[Callable] = None
        self.on_answer_created: Optional[Callable] = None
        self.on_connection_state_change: Optional[Callable] = None
        
    async def create_connection(self, connection_id: str, stream_id: str, 
                              pipeline_config: dict) -> WebRTCConnection:
        """
        Create a new WebRTC connection
        
        Args:
            connection_id: Unique identifier for the connection
            stream_id: Stream ID being handled
            pipeline_config: Configuration for the pipeline
            
        Returns:
            WebRTCConnection instance
        """
        async with self.connection_lock:
            if connection_id in self.connections:
                logger.warning(f"Connection {connection_id} already exists")
                return self.connections[connection_id]
            
            # Create new connection
            connection = WebRTCConnection(connection_id, stream_id, pipeline_config)
            
            # Set up callbacks
            connection.on_ice_candidate = self._on_ice_candidate
            connection.on_answer_created = self._on_answer_created
            connection.on_state_change = self._on_connection_state_change
            
            # Create pipeline
            connection.create_pipeline()
            
            # Store connection
            self.connections[connection_id] = connection
            
            logger.info(f"Created connection {connection_id} for stream {stream_id}")
            return connection
            
    async def get_connection(self, connection_id: str) -> Optional[WebRTCConnection]:
        """Get a connection by ID"""
        async with self.connection_lock:
            return self.connections.get(connection_id)
            
    async def remove_connection(self, connection_id: str):
        """Remove and stop a connection"""
        async with self.connection_lock:
            if connection_id in self.connections:
                connection = self.connections[connection_id]
                connection.stop()
                del self.connections[connection_id]
                logger.info(f"Removed connection {connection_id}")
                
    async def handle_offer(self, connection_id: str, offer: dict):
        """Handle SDP offer for a connection"""
        connection = await self.get_connection(connection_id)
        if connection:
            connection.handle_offer(offer)
        else:
            logger.error(f"No connection found for {connection_id}")
            
    async def add_ice_candidate(self, connection_id: str, candidate: dict):
        """Add ICE candidate to a connection"""
        connection = await self.get_connection(connection_id)
        if connection:
            connection.add_ice_candidate(
                candidate['candidate'],
                candidate['sdpMLineIndex']
            )
        else:
            logger.error(f"No connection found for {connection_id}")
            
    def _on_ice_candidate(self, connection_id: str, candidate: dict):
        """Internal callback for ICE candidates"""
        if self.on_ice_candidate:
            # Run callback in event loop
            asyncio.create_task(
                self.on_ice_candidate(connection_id, candidate)
            )
            
    def _on_answer_created(self, connection_id: str, answer: dict):
        """Internal callback for answer creation"""
        if self.on_answer_created:
            asyncio.create_task(
                self.on_answer_created(connection_id, answer)
            )
            
    def _on_connection_state_change(self, connection_id: str, state: str):
        """Internal callback for connection state changes"""
        if self.on_connection_state_change:
            asyncio.create_task(
                self.on_connection_state_change(connection_id, state)
            )
            
    async def stop_all(self):
        """Stop all connections"""
        async with self.connection_lock:
            for connection_id in list(self.connections.keys()):
                connection = self.connections[connection_id]
                connection.stop()
            self.connections.clear()
            
    def get_stats(self):
        """Get statistics for all connections"""
        stats = {
            'total_connections': len(self.connections),
            'connections': []
        }
        
        for connection in self.connections.values():
            stats['connections'].append(connection.get_stats())
            
        return stats
        
    def get_recording_connections(self):
        """Get all connections that are recording"""
        recording = []
        for connection in self.connections.values():
            if connection.is_recording:
                recording.append({
                    'connection_id': connection.connection_id,
                    'stream_id': connection.stream_id,
                    'filename': connection.recording_filename
                })
        return recording


class RoomRecordingManager(ConnectionManager):
    """Extended manager specifically for room recording"""
    
    def __init__(self, room_name: str):
        """Initialize room recording manager"""
        super().__init__()
        self.room_name = room_name
        self.room_streams = {}  # Track streams in the room
        
    async def handle_room_listing(self, room_members: list):
        """
        Handle initial room listing
        
        Args:
            room_members: List of dicts with 'streamID' and 'UUID' keys
        """
        logger.info(f"Processing room listing with {len(room_members)} members")
        
        for member in room_members:
            if 'streamID' in member and 'UUID' in member:
                stream_id = member['streamID']
                uuid = member['UUID']
                
                # Track this stream
                self.room_streams[uuid] = {
                    'streamID': stream_id,
                    'recording': False
                }
                
        logger.info(f"Tracking {len(self.room_streams)} streams in room")
        
    async def create_recording_connection(self, uuid: str, stream_id: str):
        """Create a connection for recording a room stream"""
        if uuid not in self.room_streams:
            self.room_streams[uuid] = {
                'streamID': stream_id,
                'recording': False
            }
            
        # Create pipeline config for recording
        pipeline_config = {
            'receive_only': True,
            'record': True,
            'room_name': self.room_name,
            'ice_servers': {
                'stun': 'stun://stun.l.google.com:19302'
            }
        }
        
        # Create connection
        connection = await self.create_connection(uuid, stream_id, pipeline_config)
        
        # Update tracking
        self.room_streams[uuid]['recording'] = True
        
        return connection
        
    def get_room_status(self):
        """Get status of all room streams"""
        status = {
            'room_name': self.room_name,
            'total_streams': len(self.room_streams),
            'recording': 0,
            'streams': []
        }
        
        for uuid, info in self.room_streams.items():
            stream_status = {
                'uuid': uuid,
                'stream_id': info['streamID'],
                'recording': info['recording']
            }
            
            # Check if we have an active connection
            if uuid in self.connections:
                connection = self.connections[uuid]
                stream_status['connected'] = connection.is_connected
                stream_status['filename'] = connection.recording_filename
                if connection.is_recording:
                    status['recording'] += 1
            else:
                stream_status['connected'] = False
                
            status['streams'].append(stream_status)
            
        return status