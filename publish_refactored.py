#!/usr/bin/env python3
"""
Refactored WebRTC client with modular connection management
Demonstrates how room recording should work with the new architecture
"""
import asyncio
import json
import websockets
import ssl
import logging
from urllib.parse import urlparse
import hashlib

from connection_manager import RoomRecordingManager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generateHash(input_str, length):
    """Generate hash for room/stream IDs"""
    hash_object = hashlib.sha256(input_str.encode())
    hash_hex = hash_object.hexdigest()
    return hash_hex[:length]


class RefactoredWebRTCClient:
    """Refactored WebRTC client using modular components"""
    
    def __init__(self, config):
        """Initialize the client"""
        self.config = config
        self.server = config.get('server', 'wss://wss.vdo.ninja:443')
        self.room_name = config.get('room')
        self.password = config.get('password', 'someEncryptionKey123')
        
        # Parse hostname for salt
        parsed_url = urlparse(self.server)
        hostname_parts = parsed_url.hostname.split(".")
        self.salt = ".".join(hostname_parts[-2:])
        
        # Generate hashes
        self.room_hash = generateHash(self.room_name + self.password + self.salt, 16)
        
        # Connection management
        self.connection_manager = RoomRecordingManager(self.room_name)
        
        # WebSocket connection
        self.websocket = None
        self.running = False
        
        # Set up callbacks
        self.connection_manager.on_ice_candidate = self.send_ice_candidate
        self.connection_manager.on_answer_created = self.send_answer
        
    async def connect(self):
        """Connect to WebSocket server"""
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        logger.info(f"Connecting to {self.server}")
        self.websocket = await websockets.connect(
            self.server,
            ssl=ssl_context,
            ping_interval=None
        )
        
        # Join room
        await self.send_message({
            "request": "joinroom",
            "roomid": self.room_hash
        })
        
        logger.info(f"Joined room {self.room_name} (hash: {self.room_hash})")
        
    async def send_message(self, message):
        """Send message via WebSocket"""
        if self.websocket:
            await self.websocket.send(json.dumps(message))
            logger.debug(f"Sent: {message.get('request', 'data')}")
            
    async def send_ice_candidate(self, connection_id, candidate):
        """Send ICE candidate via WebSocket"""
        msg = {
            'candidate': candidate,
            'UUID': connection_id
        }
        
        # In real implementation, would encrypt if password is set
        await self.send_message(msg)
        
    async def send_answer(self, connection_id, answer):
        """Send SDP answer via WebSocket"""
        msg = {
            'description': answer,
            'UUID': connection_id
        }
        
        # In real implementation, would encrypt if password is set
        await self.send_message(msg)
        
    async def handle_message(self, message):
        """Handle incoming WebSocket message"""
        try:
            msg = json.loads(message)
            
            # Extract UUID from message
            uuid = None
            if 'from' in msg:
                uuid = msg['from']
            elif 'UUID' in msg:
                uuid = msg['UUID']
                
            # Handle different message types
            if 'request' in msg:
                await self.handle_request(msg, uuid)
            elif 'description' in msg:
                await self.handle_description(msg, uuid)
            elif 'candidate' in msg:
                await self.handle_ice_candidate(msg, uuid)
            elif 'candidates' in msg:
                await self.handle_ice_candidates(msg, uuid)
                
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            
    async def handle_request(self, msg, uuid):
        """Handle request messages"""
        request_type = msg['request']
        
        if request_type == 'listing':
            # Room listing with current members
            if 'list' in msg:
                await self.connection_manager.handle_room_listing(msg['list'])
                
                # Request to play each stream
                for member in msg['list']:
                    if 'streamID' in member:
                        await self.send_message({
                            "request": "play",
                            "streamID": member['streamID']
                        })
                        
        elif request_type == 'videoaddedtoroom':
            # New stream joined the room
            if 'streamID' in msg:
                logger.info(f"New stream joined: {msg['streamID']}")
                await self.send_message({
                    "request": "play",
                    "streamID": msg['streamID']
                })
                
    async def handle_description(self, msg, uuid):
        """Handle SDP description (offer/answer)"""
        # Decrypt if needed (simplified here)
        description = msg['description'] if isinstance(msg['description'], dict) else msg
        
        if description.get('type') == 'offer':
            logger.info(f"Received offer from {uuid}")
            
            # Get stream ID from room streams
            stream_info = self.connection_manager.room_streams.get(uuid, {})
            stream_id = stream_info.get('streamID', 'unknown')
            
            # Create or get connection
            if uuid not in self.connection_manager.connections:
                await self.connection_manager.create_recording_connection(uuid, stream_id)
                
            # Handle the offer
            await self.connection_manager.handle_offer(uuid, description)
            
    async def handle_ice_candidate(self, msg, uuid):
        """Handle single ICE candidate"""
        candidate = msg['candidate']
        # Decrypt if needed
        
        await self.connection_manager.add_ice_candidate(uuid, candidate)
        
    async def handle_ice_candidates(self, msg, uuid):
        """Handle multiple ICE candidates"""
        candidates = msg['candidates']
        # Decrypt if needed
        
        if isinstance(candidates, list):
            for candidate in candidates:
                await self.connection_manager.add_ice_candidate(uuid, candidate)
                
    async def run(self):
        """Main event loop"""
        self.running = True
        
        try:
            await self.connect()
            
            while self.running:
                message = await self.websocket.recv()
                await self.handle_message(message)
                
        except websockets.ConnectionClosed:
            logger.info("WebSocket connection closed")
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            await self.cleanup()
            
    async def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up...")
        
        # Stop all connections
        await self.connection_manager.stop_all()
        
        # Close WebSocket
        if self.websocket:
            await self.websocket.close()
            
    def get_status(self):
        """Get current status"""
        return {
            'websocket_connected': self.websocket is not None and not self.websocket.closed,
            'room': self.room_name,
            'connection_stats': self.connection_manager.get_stats(),
            'room_status': self.connection_manager.get_room_status()
        }


async def main():
    """Main entry point"""
    # Example configuration
    config = {
        'server': 'wss://wss.vdo.ninja:443',
        'room': 'steve1233',
        'password': 'someEncryptionKey123'
    }
    
    client = RefactoredWebRTCClient(config)
    
    # Run client
    try:
        await client.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        # Print final status
        status = client.get_status()
        print("\nFinal Status:")
        print(f"Room: {status['room']}")
        print(f"Total connections: {status['connection_stats']['total_connections']}")
        
        recordings = client.connection_manager.get_recording_connections()
        if recordings:
            print("\nRecordings:")
            for rec in recordings:
                print(f"  - {rec['stream_id']}: {rec['filename']}")


if __name__ == '__main__':
    # Initialize GStreamer
    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst
    Gst.init(None)
    
    # Run
    asyncio.run(main())