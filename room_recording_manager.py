#!/usr/bin/env python3
"""
Room Recording Manager - Orchestrates multiple isolated WebRTC connections for room recording.
Manages lifecycle, monitoring, and cleanup of all stream connections in a room.
"""

import asyncio
import time
import os
import threading
from typing import Dict, List, Optional
from isolated_webrtc_client import IsolatedWebRTCClient


def printc(message, color_code=""):
    """Colored print function"""
    if color_code:
        # Simple color mapping
        colors = {
            "0F0": "\033[92m",  # Green
            "F00": "\033[91m",  # Red  
            "FF0": "\033[93m",  # Yellow
            "0FF": "\033[96m",  # Cyan
            "F0F": "\033[95m",  # Magenta
            "77F": "\033[94m",  # Blue
            "FFF": "\033[97m",  # White
        }
        color = colors.get(color_code[:3], "")
        print(f"{color}{message}\033[0m")
    else:
        print(message)


class RoomRecordingManager:
    """Manages multiple isolated WebRTC connections for room recording"""
    
    def __init__(self, parent_client, room_name: str, record_prefix: str):
        """
        Initialize the room recording manager
        
        Args:
            parent_client: Reference to main WebRTCClient
            room_name: Name of the room being recorded
            record_prefix: Prefix for recording files
        """
        self.parent_client = parent_client
        self.room_name = room_name
        self.record_prefix = record_prefix
        self.params = parent_client.params if hasattr(parent_client, 'params') else None
        
        # Stream management
        self.isolated_clients: Dict[str, IsolatedWebRTCClient] = {}
        self.stream_info: Dict[str, dict] = {}  # UUID -> stream info
        self.pending_streams: List[dict] = []
        
        # State management
        self.active = True
        self.clients_lock = asyncio.Lock()
        self.stats_timer = None
        self.recording_start_time = time.time()
        
        # Recording tracking
        self.completed_recordings: List[dict] = []
        
        printc(f"\n🎬 Room Recording Manager initialized", "0FF")
        printc(f"   Room: {room_name}", "77F")
        printc(f"   Prefix: {record_prefix}", "77F")
        
    async def add_stream(self, stream_id: str, stream_uuid: str):
        """Add a new stream to be recorded"""
        async with self.clients_lock:
            if stream_uuid in self.isolated_clients:
                printc(f"Stream {stream_id} already being recorded", "FF0")
                return
                
            printc(f"\n📹 Adding stream for recording: {stream_id}", "0F0")
            
            # Create isolated client for this stream
            client = IsolatedWebRTCClient(
                stream_id=stream_id,
                stream_uuid=stream_uuid,
                room_name=self.room_name,
                record_prefix=self.record_prefix,
                params=self.params,
                parent_client=self.parent_client
            )
            
            self.isolated_clients[stream_uuid] = client
            self.stream_info[stream_uuid] = {
                'stream_id': stream_id,
                'uuid': stream_uuid,
                'start_time': time.time(),
                'status': 'connecting'
            }
            
            # Start connection process
            await client.connect()
            
    async def handle_room_list(self, room_list: List[dict]):
        """Process room list and start recording all streams"""
        printc(f"\n📋 Processing room list with {len(room_list)} members", "0FF")
        
        # Filter streams based on stream_filter if set
        stream_filter = getattr(self.parent_client, 'stream_filter', None)
        
        for member in room_list:
            if 'UUID' in member and 'streamID' in member:
                stream_id = member['streamID']
                stream_uuid = member['UUID']
                
                # Apply filter if configured
                if stream_filter and stream_id not in stream_filter:
                    printc(f"   Skipping {stream_id} (filtered)", "77F")
                    continue
                    
                # Add to pending streams
                self.pending_streams.append({
                    'stream_id': stream_id,
                    'uuid': stream_uuid
                })
                
        printc(f"   Will record {len(self.pending_streams)} streams", "0F0")
        
        # Start recording each stream
        for stream in self.pending_streams:
            await self.add_stream(stream['stream_id'], stream['uuid'])
            # Small delay to avoid overwhelming the server
            await asyncio.sleep(0.5)
            
        # Start monitoring
        if not self.stats_timer:
            self.start_monitoring()
            
    async def handle_message(self, msg: dict):
        """Route messages to appropriate isolated clients"""
        # Get the UUID from the message to identify which client it's for
        uuid = msg.get('UUID')
        session = msg.get('session')
        
        # Find the matching isolated client
        target_client = None
        
        if uuid:
            # Direct UUID match
            target_client = self.isolated_clients.get(uuid)
        elif session:
            # Try to match by session
            for client_uuid, client in self.isolated_clients.items():
                if client.session_id == session:
                    target_client = client
                    break
                    
        if not target_client:
            # Try to match by the 'from' field which might contain the stream ID
            from_id = msg.get('from')
            if from_id:
                for client_uuid, client in self.isolated_clients.items():
                    if client.stream_id == from_id:
                        target_client = client
                        break
                        
        if target_client:
            # Update session ID if provided
            if session and not target_client.session_id:
                target_client.session_id = session
                
            # Route message based on type
            if 'description' in msg:
                # SDP offer/answer
                if msg.get('description', {}).get('type') == 'offer':
                    await target_client.handle_offer(msg)
            elif 'candidates' in msg:
                # ICE candidates
                await target_client.handle_ice_candidate(msg)
        else:
            # Message doesn't match any isolated client
            # This might be a general room message or for the main connection
            pass
            
    def start_monitoring(self):
        """Start periodic monitoring of all connections"""
        def monitor():
            while self.active:
                try:
                    # Collect stats from all clients
                    active_count = 0
                    total_bytes = 0
                    
                    for uuid, client in list(self.isolated_clients.items()):
                        if client.connected and client.recording:
                            active_count += 1
                            stats = client.get_stats()
                            bytes_recorded = stats.get('bytes_recorded', 0)
                            total_bytes += bytes_recorded
                            
                            # Update stream info
                            if uuid in self.stream_info:
                                self.stream_info[uuid]['status'] = 'recording'
                                self.stream_info[uuid]['bytes'] = bytes_recorded
                                
                            # Print individual stream progress
                            if bytes_recorded > 0:
                                printc(f"📊 {client.stream_id}: {client.recording_file} - {bytes_recorded:,} bytes", "77F")
                                
                    # Summary line
                    if active_count > 0:
                        elapsed = int(time.time() - self.recording_start_time)
                        printc(f"\n⏱️  Recording: {active_count} streams, {total_bytes:,} total bytes, {elapsed}s elapsed\n", "0FF")
                        
                except Exception as e:
                    printc(f"Monitor error: {e}", "F00")
                    
                # Wait before next update
                time.sleep(5)
                
        self.stats_timer = threading.Thread(target=monitor, daemon=True)
        self.stats_timer.start()
        
    async def stop_all(self):
        """Stop all recordings and cleanup"""
        self.active = False
        
        printc("\n🛑 Stopping all room recordings...", "FF0")
        
        # Stop all isolated clients
        async with self.clients_lock:
            cleanup_tasks = []
            
            for uuid, client in self.isolated_clients.items():
                cleanup_tasks.append(client.cleanup())
                
            # Wait for all cleanups to complete
            if cleanup_tasks:
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)
                
        # Generate summary report
        self.generate_summary()
        
    def generate_summary(self):
        """Generate and display recording summary"""
        printc("\n" + "="*60, "FFF")
        printc("📹 Room Recording Summary", "0FF")
        printc("="*60, "FFF")
        
        total_files = 0
        total_bytes = 0
        
        # Check each client's recording
        for uuid, client in self.isolated_clients.items():
            stream_id = client.stream_id
            
            if client.recording_file and os.path.exists(client.recording_file):
                file_size = os.path.getsize(client.recording_file)
                total_files += 1
                total_bytes += file_size
                
                printc(f"\nStream: {stream_id}", "0F0")
                printc(f"  ✅ {client.recording_file} ({file_size:,} bytes)", "0F0")
                
                # Add to completed recordings
                self.completed_recordings.append({
                    'stream_id': stream_id,
                    'file': client.recording_file,
                    'size': file_size,
                    'duration': client.stats.get('recording_duration', 0)
                })
            else:
                printc(f"\nStream: {stream_id}", "F00")
                printc(f"  ❌ No recording found", "F00")
                
        # Summary stats
        printc(f"\nTotal: {total_files} files, {total_bytes:,} bytes", "0FF")
        
        if total_files > 0:
            avg_size = total_bytes / total_files
            printc(f"Average size: {avg_size:,.0f} bytes per stream", "77F")
            
        recording_duration = time.time() - self.recording_start_time
        printc(f"Recording duration: {int(recording_duration)} seconds", "77F")
        
        printc("="*60, "FFF")
        
    def get_completed_recordings(self) -> List[dict]:
        """Get list of completed recordings"""
        return self.completed_recordings
        
    async def handle_new_stream_joined(self, stream_id: str, stream_uuid: str):
        """Handle a new stream that joined the room during recording"""
        printc(f"\n🆕 New stream joined room: {stream_id}", "0FF")
        
        # Check if we should record this stream
        stream_filter = getattr(self.parent_client, 'stream_filter', None)
        if stream_filter and stream_id not in stream_filter:
            printc(f"   Skipping {stream_id} (filtered)", "77F")
            return
            
        # Add the new stream
        await self.add_stream(stream_id, stream_uuid)
        
    async def handle_stream_left(self, stream_uuid: str):
        """Handle a stream leaving the room"""
        async with self.clients_lock:
            if stream_uuid in self.isolated_clients:
                client = self.isolated_clients[stream_uuid]
                printc(f"\n👋 Stream left room: {client.stream_id}", "FF0")
                
                # Cleanup the client
                await client.cleanup()
                
                # Remove from tracking
                del self.isolated_clients[stream_uuid]
                if stream_uuid in self.stream_info:
                    del self.stream_info[stream_uuid]