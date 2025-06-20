#!/usr/bin/env python3
"""
Test session management for multiple peer connections.

This test suite focuses on:
1. Session ID generation and tracking for multiple peers
2. UUID to session mapping and vice versa
3. Handling session conflicts when peers reconnect
4. Session state transitions (connecting, connected, reconnecting, disconnected)
5. Session cleanup and expiry
6. Multiviewer mode session handling
7. Room-based session management
8. Session persistence and recovery
"""

import asyncio
import json
import time
import uuid
from typing import Dict, List, Optional, Set, Tuple
import pytest
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SessionState(Enum):
    """Session states for peer connections."""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    DISCONNECTED = "disconnected"
    EXPIRED = "expired"

@dataclass
class PeerSession:
    """Represents a peer session."""
    session_id: str
    peer_uuid: str
    room_id: str
    state: SessionState
    created_at: datetime
    last_activity: datetime
    connection_count: int = 0
    metadata: Dict = field(default_factory=dict)
    
    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity = datetime.now()
    
    def is_expired(self, timeout_seconds: int = 300) -> bool:
        """Check if session has expired."""
        return (datetime.now() - self.last_activity).seconds > timeout_seconds

class SessionManager:
    """Manages sessions for multiple peer connections."""
    
    def __init__(self, session_timeout: int = 300):
        self.sessions: Dict[str, PeerSession] = {}  # session_id -> PeerSession
        self.uuid_to_session: Dict[str, str] = {}  # peer_uuid -> session_id
        self.room_sessions: Dict[str, Set[str]] = {}  # room_id -> set of session_ids
        self.session_timeout = session_timeout
        self.cleanup_interval = 60  # Run cleanup every minute
        self._cleanup_task = None
        
    async def start(self):
        """Start the session manager."""
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_sessions())
        logger.info("Session manager started")
        
    async def stop(self):
        """Stop the session manager."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("Session manager stopped")
    
    def create_session(self, peer_uuid: str, room_id: str, metadata: Optional[Dict] = None) -> str:
        """Create a new session for a peer."""
        # Check if peer already has a session
        if peer_uuid in self.uuid_to_session:
            existing_session_id = self.uuid_to_session[peer_uuid]
            existing_session = self.sessions.get(existing_session_id)
            if existing_session and existing_session.state != SessionState.EXPIRED:
                logger.warning(f"Peer {peer_uuid} already has active session {existing_session_id}")
                # Handle reconnection
                return self._handle_reconnection(existing_session)
        
        # Generate new session ID
        session_id = f"session_{uuid.uuid4().hex[:8]}_{int(time.time())}"
        
        # Create session
        session = PeerSession(
            session_id=session_id,
            peer_uuid=peer_uuid,
            room_id=room_id,
            state=SessionState.CONNECTING,
            created_at=datetime.now(),
            last_activity=datetime.now(),
            connection_count=1,
            metadata=metadata or {}
        )
        
        # Store session
        self.sessions[session_id] = session
        self.uuid_to_session[peer_uuid] = session_id
        
        # Add to room sessions
        if room_id not in self.room_sessions:
            self.room_sessions[room_id] = set()
        self.room_sessions[room_id].add(session_id)
        
        logger.info(f"Created session {session_id} for peer {peer_uuid} in room {room_id}")
        return session_id
    
    def _handle_reconnection(self, session: PeerSession) -> str:
        """Handle peer reconnection."""
        session.state = SessionState.RECONNECTING
        session.connection_count += 1
        session.update_activity()
        logger.info(f"Peer {session.peer_uuid} reconnecting, session {session.session_id}, connection count: {session.connection_count}")
        return session.session_id
    
    def update_session_state(self, session_id: str, new_state: SessionState) -> bool:
        """Update session state."""
        session = self.sessions.get(session_id)
        if not session:
            logger.error(f"Session {session_id} not found")
            return False
        
        old_state = session.state
        session.state = new_state
        session.update_activity()
        
        logger.info(f"Session {session_id} state changed: {old_state.value} -> {new_state.value}")
        return True
    
    def get_session(self, session_id: str) -> Optional[PeerSession]:
        """Get session by ID."""
        return self.sessions.get(session_id)
    
    def get_session_by_uuid(self, peer_uuid: str) -> Optional[PeerSession]:
        """Get session by peer UUID."""
        session_id = self.uuid_to_session.get(peer_uuid)
        if session_id:
            return self.sessions.get(session_id)
        return None
    
    def get_room_sessions(self, room_id: str) -> List[PeerSession]:
        """Get all sessions in a room."""
        session_ids = self.room_sessions.get(room_id, set())
        return [self.sessions[sid] for sid in session_ids if sid in self.sessions]
    
    def remove_session(self, session_id: str) -> bool:
        """Remove a session."""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        # Remove from sessions
        del self.sessions[session_id]
        
        # Remove UUID mapping
        if session.peer_uuid in self.uuid_to_session:
            del self.uuid_to_session[session.peer_uuid]
        
        # Remove from room sessions
        if session.room_id in self.room_sessions:
            self.room_sessions[session.room_id].discard(session_id)
            if not self.room_sessions[session.room_id]:
                del self.room_sessions[session.room_id]
        
        logger.info(f"Removed session {session_id}")
        return True
    
    async def _cleanup_expired_sessions(self):
        """Periodically cleanup expired sessions."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                
                expired_sessions = []
                for session_id, session in self.sessions.items():
                    if session.is_expired(self.session_timeout):
                        expired_sessions.append(session_id)
                
                for session_id in expired_sessions:
                    session = self.sessions[session_id]
                    session.state = SessionState.EXPIRED
                    logger.info(f"Session {session_id} expired after {self.session_timeout}s of inactivity")
                    self.remove_session(session_id)
                
                if expired_sessions:
                    logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error during session cleanup: {e}")

class MultiviewerSessionManager(SessionManager):
    """Extended session manager for multiviewer mode."""
    
    def __init__(self, session_timeout: int = 300):
        super().__init__(session_timeout)
        self.viewer_sessions: Dict[str, Set[str]] = {}  # viewer_uuid -> set of viewed session_ids
        self.session_viewers: Dict[str, Set[str]] = {}  # session_id -> set of viewer_uuids
    
    def add_viewer_to_session(self, viewer_uuid: str, target_session_id: str) -> bool:
        """Add a viewer to a session."""
        # Check if target session exists
        if target_session_id not in self.sessions:
            logger.error(f"Target session {target_session_id} not found")
            return False
        
        # Add viewer to session
        if target_session_id not in self.session_viewers:
            self.session_viewers[target_session_id] = set()
        self.session_viewers[target_session_id].add(viewer_uuid)
        
        # Add session to viewer
        if viewer_uuid not in self.viewer_sessions:
            self.viewer_sessions[viewer_uuid] = set()
        self.viewer_sessions[viewer_uuid].add(target_session_id)
        
        logger.info(f"Added viewer {viewer_uuid} to session {target_session_id}")
        return True
    
    def remove_viewer_from_session(self, viewer_uuid: str, target_session_id: str) -> bool:
        """Remove a viewer from a session."""
        removed = False
        
        # Remove from session viewers
        if target_session_id in self.session_viewers:
            self.session_viewers[target_session_id].discard(viewer_uuid)
            if not self.session_viewers[target_session_id]:
                del self.session_viewers[target_session_id]
            removed = True
        
        # Remove from viewer sessions
        if viewer_uuid in self.viewer_sessions:
            self.viewer_sessions[viewer_uuid].discard(target_session_id)
            if not self.viewer_sessions[viewer_uuid]:
                del self.viewer_sessions[viewer_uuid]
            removed = True
        
        if removed:
            logger.info(f"Removed viewer {viewer_uuid} from session {target_session_id}")
        return removed
    
    def get_session_viewers(self, session_id: str) -> Set[str]:
        """Get all viewers for a session."""
        return self.session_viewers.get(session_id, set())
    
    def get_viewer_sessions(self, viewer_uuid: str) -> Set[str]:
        """Get all sessions a viewer is watching."""
        return self.viewer_sessions.get(viewer_uuid, set())

class SessionPersistence:
    """Handles session persistence and recovery."""
    
    def __init__(self, persistence_file: str = "sessions.json"):
        self.persistence_file = persistence_file
    
    def save_sessions(self, session_manager: SessionManager) -> bool:
        """Save sessions to persistent storage."""
        try:
            data = {
                "sessions": {},
                "uuid_mappings": session_manager.uuid_to_session,
                "room_sessions": {k: list(v) for k, v in session_manager.room_sessions.items()},
                "timestamp": datetime.now().isoformat()
            }
            
            # Serialize sessions
            for session_id, session in session_manager.sessions.items():
                data["sessions"][session_id] = {
                    "session_id": session.session_id,
                    "peer_uuid": session.peer_uuid,
                    "room_id": session.room_id,
                    "state": session.state.value,
                    "created_at": session.created_at.isoformat(),
                    "last_activity": session.last_activity.isoformat(),
                    "connection_count": session.connection_count,
                    "metadata": session.metadata
                }
            
            with open(self.persistence_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"Saved {len(data['sessions'])} sessions to {self.persistence_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save sessions: {e}")
            return False
    
    def load_sessions(self, session_manager: SessionManager) -> bool:
        """Load sessions from persistent storage."""
        try:
            with open(self.persistence_file, 'r') as f:
                data = json.load(f)
            
            # Clear existing sessions
            session_manager.sessions.clear()
            session_manager.uuid_to_session.clear()
            session_manager.room_sessions.clear()
            
            # Restore sessions
            for session_id, session_data in data["sessions"].items():
                session = PeerSession(
                    session_id=session_data["session_id"],
                    peer_uuid=session_data["peer_uuid"],
                    room_id=session_data["room_id"],
                    state=SessionState(session_data["state"]),
                    created_at=datetime.fromisoformat(session_data["created_at"]),
                    last_activity=datetime.fromisoformat(session_data["last_activity"]),
                    connection_count=session_data["connection_count"],
                    metadata=session_data["metadata"]
                )
                
                # Skip expired sessions
                if not session.is_expired(session_manager.session_timeout):
                    session_manager.sessions[session_id] = session
            
            # Restore mappings
            session_manager.uuid_to_session = data["uuid_mappings"]
            for room_id, session_ids in data["room_sessions"].items():
                session_manager.room_sessions[room_id] = set(session_ids)
            
            logger.info(f"Loaded {len(session_manager.sessions)} sessions from {self.persistence_file}")
            return True
            
        except FileNotFoundError:
            logger.info(f"No persistence file found at {self.persistence_file}")
            return False
        except Exception as e:
            logger.error(f"Failed to load sessions: {e}")
            return False

@pytest.mark.asyncio
async def test_basic_session_management():
    """Test basic session creation and management."""
    logger.info("\n=== Testing Basic Session Management ===")
    
    manager = SessionManager()
    await manager.start()
    
    try:
        # Create sessions for multiple peers
        peer1_uuid = str(uuid.uuid4())
        peer2_uuid = str(uuid.uuid4())
        room_id = "test_room"
        
        session1_id = manager.create_session(peer1_uuid, room_id, {"name": "Peer1"})
        session2_id = manager.create_session(peer2_uuid, room_id, {"name": "Peer2"})
        
        # Verify sessions created
        assert session1_id != session2_id
        assert manager.get_session(session1_id) is not None
        assert manager.get_session(session2_id) is not None
        
        # Test UUID to session mapping
        session1 = manager.get_session_by_uuid(peer1_uuid)
        assert session1 is not None
        assert session1.session_id == session1_id
        
        # Test room sessions
        room_sessions = manager.get_room_sessions(room_id)
        assert len(room_sessions) == 2
        
        logger.info("✓ Basic session management test passed")
        
    finally:
        await manager.stop()

@pytest.mark.asyncio
async def test_session_reconnection():
    """Test session handling during peer reconnection."""
    logger.info("\n=== Testing Session Reconnection ===")
    
    manager = SessionManager()
    await manager.start()
    
    try:
        peer_uuid = str(uuid.uuid4())
        room_id = "test_room"
        
        # Initial connection
        session1_id = manager.create_session(peer_uuid, room_id)
        manager.update_session_state(session1_id, SessionState.CONNECTED)
        
        # Simulate disconnection
        manager.update_session_state(session1_id, SessionState.DISCONNECTED)
        
        # Reconnection attempt
        session2_id = manager.create_session(peer_uuid, room_id)
        
        # Should get the same session ID (reconnection)
        assert session1_id == session2_id
        
        session = manager.get_session(session1_id)
        assert session.state == SessionState.RECONNECTING
        assert session.connection_count == 2
        
        logger.info("✓ Session reconnection test passed")
        
    finally:
        await manager.stop()

@pytest.mark.asyncio
async def test_session_state_transitions():
    """Test session state transitions."""
    logger.info("\n=== Testing Session State Transitions ===")
    
    manager = SessionManager()
    await manager.start()
    
    try:
        peer_uuid = str(uuid.uuid4())
        room_id = "test_room"
        
        session_id = manager.create_session(peer_uuid, room_id)
        session = manager.get_session(session_id)
        
        # Initial state should be CONNECTING
        assert session.state == SessionState.CONNECTING
        
        # Test state transitions
        transitions = [
            SessionState.CONNECTED,
            SessionState.DISCONNECTED,
            SessionState.RECONNECTING,
            SessionState.CONNECTED,
            SessionState.DISCONNECTED
        ]
        
        for new_state in transitions:
            success = manager.update_session_state(session_id, new_state)
            assert success
            assert session.state == new_state
        
        logger.info("✓ Session state transitions test passed")
        
    finally:
        await manager.stop()

@pytest.mark.asyncio
async def test_session_expiry():
    """Test session expiry and cleanup."""
    logger.info("\n=== Testing Session Expiry ===")
    
    # Use very short timeout for testing
    manager = SessionManager(session_timeout=2)
    manager.cleanup_interval = 1  # Check every second
    await manager.start()
    
    try:
        peer_uuid = str(uuid.uuid4())
        room_id = "test_room"
        
        session_id = manager.create_session(peer_uuid, room_id)
        
        # Verify session exists
        assert manager.get_session(session_id) is not None
        
        # Wait for session to expire
        await asyncio.sleep(4)
        
        # Session should be removed
        assert manager.get_session(session_id) is None
        assert manager.get_session_by_uuid(peer_uuid) is None
        
        logger.info("✓ Session expiry test passed")
        
    finally:
        await manager.stop()

@pytest.mark.asyncio
async def test_multiviewer_sessions():
    """Test multiviewer mode session handling."""
    logger.info("\n=== Testing Multiviewer Sessions ===")
    
    manager = MultiviewerSessionManager()
    await manager.start()
    
    try:
        # Create broadcaster sessions
        broadcaster1_uuid = str(uuid.uuid4())
        broadcaster2_uuid = str(uuid.uuid4())
        viewer1_uuid = str(uuid.uuid4())
        viewer2_uuid = str(uuid.uuid4())
        room_id = "multiview_room"
        
        # Create broadcaster sessions
        session1_id = manager.create_session(broadcaster1_uuid, room_id)
        session2_id = manager.create_session(broadcaster2_uuid, room_id)
        
        # Add viewers to sessions
        manager.add_viewer_to_session(viewer1_uuid, session1_id)
        manager.add_viewer_to_session(viewer1_uuid, session2_id)
        manager.add_viewer_to_session(viewer2_uuid, session1_id)
        
        # Verify viewer mappings
        assert len(manager.get_session_viewers(session1_id)) == 2
        assert len(manager.get_session_viewers(session2_id)) == 1
        assert len(manager.get_viewer_sessions(viewer1_uuid)) == 2
        assert len(manager.get_viewer_sessions(viewer2_uuid)) == 1
        
        # Remove viewer
        manager.remove_viewer_from_session(viewer1_uuid, session1_id)
        assert len(manager.get_session_viewers(session1_id)) == 1
        assert len(manager.get_viewer_sessions(viewer1_uuid)) == 1
        
        logger.info("✓ Multiviewer sessions test passed")
        
    finally:
        await manager.stop()

@pytest.mark.asyncio
async def test_session_persistence():
    """Test session persistence and recovery."""
    logger.info("\n=== Testing Session Persistence ===")
    
    persistence = SessionPersistence("test_sessions.json")
    
    # Create and save sessions
    manager1 = SessionManager()
    await manager1.start()
    
    try:
        # Create multiple sessions
        peer_uuids = [str(uuid.uuid4()) for _ in range(3)]
        room_id = "persist_room"
        
        session_ids = []
        for peer_uuid in peer_uuids:
            session_id = manager1.create_session(peer_uuid, room_id, {"test": "data"})
            manager1.update_session_state(session_id, SessionState.CONNECTED)
            session_ids.append(session_id)
        
        # Save sessions
        assert persistence.save_sessions(manager1)
        
        # Create new manager and load sessions
        manager2 = SessionManager()
        assert persistence.load_sessions(manager2)
        
        # Verify sessions loaded correctly
        for i, session_id in enumerate(session_ids):
            session = manager2.get_session(session_id)
            assert session is not None
            assert session.peer_uuid == peer_uuids[i]
            assert session.room_id == room_id
            assert session.state == SessionState.CONNECTED
            assert session.metadata == {"test": "data"}
        
        # Verify mappings restored
        for peer_uuid in peer_uuids:
            assert manager2.get_session_by_uuid(peer_uuid) is not None
        
        assert len(manager2.get_room_sessions(room_id)) == 3
        
        logger.info("✓ Session persistence test passed")
        
    finally:
        await manager1.stop()
        # Cleanup test file
        import os
        if os.path.exists("test_sessions.json"):
            os.remove("test_sessions.json")

@pytest.mark.asyncio
async def test_concurrent_session_operations():
    """Test concurrent session operations."""
    logger.info("\n=== Testing Concurrent Session Operations ===")
    
    manager = SessionManager()
    await manager.start()
    
    try:
        room_id = "concurrent_room"
        num_peers = 10
        
        # Create multiple sessions concurrently
        async def create_peer_session(index: int):
            peer_uuid = f"peer_{index}_{uuid.uuid4().hex[:8]}"
            session_id = manager.create_session(peer_uuid, room_id)
            
            # Simulate some operations
            await asyncio.sleep(0.1)
            manager.update_session_state(session_id, SessionState.CONNECTED)
            
            await asyncio.sleep(0.1)
            manager.update_session_state(session_id, SessionState.DISCONNECTED)
            
            return session_id
        
        # Create sessions concurrently
        tasks = [create_peer_session(i) for i in range(num_peers)]
        session_ids = await asyncio.gather(*tasks)
        
        # Verify all sessions created
        assert len(session_ids) == num_peers
        assert len(set(session_ids)) == num_peers  # All unique
        
        # Verify room has all sessions
        room_sessions = manager.get_room_sessions(room_id)
        assert len(room_sessions) == num_peers
        
        # All should be in DISCONNECTED state
        for session in room_sessions:
            assert session.state == SessionState.DISCONNECTED
        
        logger.info("✓ Concurrent session operations test passed")
        
    finally:
        await manager.stop()

@pytest.mark.asyncio
async def test_session_conflict_resolution():
    """Test session conflict resolution."""
    logger.info("\n=== Testing Session Conflict Resolution ===")
    
    manager = SessionManager()
    await manager.start()
    
    try:
        peer_uuid = str(uuid.uuid4())
        room1_id = "room1"
        room2_id = "room2"
        
        # Create session in room1
        session1_id = manager.create_session(peer_uuid, room1_id)
        manager.update_session_state(session1_id, SessionState.CONNECTED)
        
        # Try to create session in different room with same peer UUID
        session2_id = manager.create_session(peer_uuid, room2_id)
        
        # Should handle as reconnection to existing session
        assert session1_id == session2_id
        
        session = manager.get_session(session1_id)
        assert session.room_id == room1_id  # Should keep original room
        assert session.state == SessionState.RECONNECTING
        
        logger.info("✓ Session conflict resolution test passed")
        
    finally:
        await manager.stop()

async def main():
    """Run all tests."""
    tests = [
        test_basic_session_management,
        test_session_reconnection,
        test_session_state_transitions,
        test_session_expiry,
        test_multiviewer_sessions,
        test_session_persistence,
        test_concurrent_session_operations,
        test_session_conflict_resolution
    ]
    
    for test in tests:
        try:
            await test()
        except Exception as e:
            logger.error(f"Test {test.__name__} failed: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(main())
    logger.info("\n✅ All session management tests passed!")