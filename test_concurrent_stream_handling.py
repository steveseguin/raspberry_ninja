#!/usr/bin/env python3
"""
Test concurrent stream handling capabilities for Raspberry Ninja.

This module tests:
- Multiple simultaneous incoming streams
- Stream queueing and buffering strategies
- Bandwidth management and allocation
- Dynamic quality adaptation
- Audio/video synchronization
- Dynamic stream addition/removal
- Performance under load
- Error recovery mechanisms
"""

import asyncio
import time
import random
import threading
import multiprocessing
import pytest
from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Callable
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from enum import Enum
import psutil
import json


class StreamState(Enum):
    """Stream connection states."""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    BUFFERING = "buffering"
    PLAYING = "playing"
    PAUSED = "paused"
    ERROR = "error"
    DISCONNECTED = "disconnected"


class StreamPriority(Enum):
    """Stream priority levels for resource allocation."""
    CRITICAL = 5
    HIGH = 4
    NORMAL = 3
    LOW = 2
    BACKGROUND = 1


@dataclass
class StreamMetrics:
    """Metrics for individual stream performance."""
    stream_id: str
    bitrate: float = 0.0
    fps: float = 0.0
    latency: float = 0.0
    jitter: float = 0.0
    packet_loss: float = 0.0
    buffer_fill: float = 0.0
    quality_score: float = 1.0
    last_update: float = field(default_factory=time.time)


@dataclass
class StreamConfig:
    """Configuration for individual streams."""
    stream_id: str
    priority: StreamPriority = StreamPriority.NORMAL
    max_bitrate: int = 5_000_000  # 5 Mbps
    target_fps: int = 30
    buffer_size: int = 1024 * 1024  # 1MB
    enable_adaptive_quality: bool = True
    audio_enabled: bool = True
    video_enabled: bool = True


class StreamBuffer:
    """Circular buffer for stream data with overflow protection."""
    
    def __init__(self, size: int, stream_id: str):
        self.size = size
        self.stream_id = stream_id
        self.buffer = deque(maxlen=size)
        self.lock = threading.Lock()
        self.overflow_count = 0
        self.underflow_count = 0
        
    def write(self, data: bytes) -> bool:
        """Write data to buffer, returns False if full."""
        with self.lock:
            if len(self.buffer) >= self.size:
                self.overflow_count += 1
                return False
            self.buffer.append(data)
            return True
    
    def read(self, size: int) -> Optional[bytes]:
        """Read data from buffer."""
        with self.lock:
            if not self.buffer:
                self.underflow_count += 1
                return None
            
            data = b''
            while len(data) < size and self.buffer:
                chunk = self.buffer.popleft()
                data += chunk
            
            return data if data else None
    
    def get_fill_level(self) -> float:
        """Get buffer fill percentage."""
        with self.lock:
            return len(self.buffer) / self.size


class BandwidthManager:
    """Manages bandwidth allocation across multiple streams."""
    
    def __init__(self, total_bandwidth: int):
        self.total_bandwidth = total_bandwidth
        self.allocations: Dict[str, int] = {}
        self.lock = threading.Lock()
        
    def allocate_bandwidth(self, stream_id: str, requested: int, priority: StreamPriority) -> int:
        """Allocate bandwidth to a stream based on priority and availability."""
        with self.lock:
            # Calculate available bandwidth
            used = sum(self.allocations.values())
            available = self.total_bandwidth - used
            
            if available <= 0:
                # Redistribute based on priority
                return self._redistribute_bandwidth(stream_id, requested, priority)
            
            # Allocate what's available up to requested
            allocated = min(requested, available)
            self.allocations[stream_id] = allocated
            return allocated
    
    def _redistribute_bandwidth(self, stream_id: str, requested: int, priority: StreamPriority) -> int:
        """Redistribute bandwidth based on priorities."""
        # Simple priority-based redistribution
        priority_weight = priority.value
        total_weight = sum(priority.value for priority in StreamPriority)
        
        allocated = int((priority_weight / total_weight) * self.total_bandwidth)
        self.allocations[stream_id] = allocated
        return allocated
    
    def release_bandwidth(self, stream_id: str):
        """Release bandwidth allocation for a stream."""
        with self.lock:
            self.allocations.pop(stream_id, None)


class QualityAdapter:
    """Adapts stream quality based on network conditions."""
    
    def __init__(self):
        self.quality_levels = [
            (240, 15, 500_000),    # 240p, 15fps, 500kbps
            (360, 24, 1_000_000),  # 360p, 24fps, 1Mbps
            (480, 30, 2_000_000),  # 480p, 30fps, 2Mbps
            (720, 30, 3_000_000),  # 720p, 30fps, 3Mbps
            (1080, 30, 5_000_000), # 1080p, 30fps, 5Mbps
        ]
        self.current_levels: Dict[str, int] = {}
        
    def adapt_quality(self, stream_id: str, metrics: StreamMetrics) -> Tuple[int, int, int]:
        """Adapt quality based on stream metrics."""
        current_level = self.current_levels.get(stream_id, 2)  # Start at 480p
        
        # Adapt based on metrics
        if metrics.packet_loss > 0.05 or metrics.jitter > 100:
            # Poor network, decrease quality
            current_level = max(0, current_level - 1)
        elif metrics.packet_loss < 0.01 and metrics.jitter < 20 and metrics.buffer_fill > 0.8:
            # Good network, increase quality
            current_level = min(len(self.quality_levels) - 1, current_level + 1)
        
        self.current_levels[stream_id] = current_level
        return self.quality_levels[current_level]


class AVSynchronizer:
    """Handles audio/video synchronization across streams."""
    
    def __init__(self):
        self.stream_timestamps: Dict[str, Dict[str, float]] = defaultdict(dict)
        self.sync_offset: Dict[str, float] = defaultdict(float)
        self.lock = threading.Lock()
        
    def update_timestamp(self, stream_id: str, media_type: str, timestamp: float):
        """Update timestamp for audio or video stream."""
        with self.lock:
            self.stream_timestamps[stream_id][media_type] = timestamp
            self._calculate_sync_offset(stream_id)
    
    def _calculate_sync_offset(self, stream_id: str):
        """Calculate sync offset between audio and video."""
        timestamps = self.stream_timestamps[stream_id]
        if 'audio' in timestamps and 'video' in timestamps:
            self.sync_offset[stream_id] = timestamps['video'] - timestamps['audio']
    
    def get_sync_offset(self, stream_id: str) -> float:
        """Get current sync offset for stream."""
        with self.lock:
            return self.sync_offset.get(stream_id, 0.0)


class StreamHandler:
    """Handles individual stream processing."""
    
    def __init__(self, config: StreamConfig, buffer: StreamBuffer, 
                 bandwidth_manager: BandwidthManager, quality_adapter: QualityAdapter,
                 av_synchronizer: AVSynchronizer):
        self.config = config
        self.buffer = buffer
        self.bandwidth_manager = bandwidth_manager
        self.quality_adapter = quality_adapter
        self.av_synchronizer = av_synchronizer
        self.state = StreamState.CONNECTING
        self.metrics = StreamMetrics(stream_id=config.stream_id)
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Start stream handling."""
        self._running = True
        self.state = StreamState.CONNECTING
        self._task = asyncio.create_task(self._handle_stream())
        
    async def stop(self):
        """Stop stream handling."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.state = StreamState.DISCONNECTED
        self.bandwidth_manager.release_bandwidth(self.config.stream_id)
        
    async def _handle_stream(self):
        """Main stream handling loop."""
        try:
            # Allocate initial bandwidth
            allocated = self.bandwidth_manager.allocate_bandwidth(
                self.config.stream_id,
                self.config.max_bitrate,
                self.config.priority
            )
            
            self.state = StreamState.CONNECTED
            
            while self._running:
                # Simulate stream data reception
                await self._receive_data()
                
                # Update metrics
                self._update_metrics()
                
                # Adapt quality if enabled
                if self.config.enable_adaptive_quality:
                    quality = self.quality_adapter.adapt_quality(
                        self.config.stream_id,
                        self.metrics
                    )
                    # Apply quality settings...
                
                # Check buffer levels
                fill_level = self.buffer.get_fill_level()
                if fill_level < 0.2:
                    self.state = StreamState.BUFFERING
                elif fill_level > 0.5 and self.state == StreamState.BUFFERING:
                    self.state = StreamState.PLAYING
                
                await asyncio.sleep(0.033)  # ~30fps
                
        except Exception as e:
            self.state = StreamState.ERROR
            print(f"Stream {self.config.stream_id} error: {e}")
            
    async def _receive_data(self):
        """Simulate receiving stream data."""
        # Simulate network conditions
        if random.random() < 0.95:  # 5% packet loss
            data_size = random.randint(1000, 5000)
            data = bytes(data_size)
            
            # Write to buffer
            if not self.buffer.write(data):
                self.metrics.packet_loss += 0.01
            
            # Update AV sync timestamps
            timestamp = time.time()
            if self.config.video_enabled:
                self.av_synchronizer.update_timestamp(
                    self.config.stream_id, 'video', timestamp
                )
            if self.config.audio_enabled:
                # Audio slightly ahead to simulate typical scenario
                self.av_synchronizer.update_timestamp(
                    self.config.stream_id, 'audio', timestamp - 0.020
                )
    
    def _update_metrics(self):
        """Update stream metrics."""
        self.metrics.buffer_fill = self.buffer.get_fill_level()
        self.metrics.fps = 30 + random.uniform(-2, 2)
        self.metrics.bitrate = self.config.max_bitrate * random.uniform(0.8, 1.0)
        self.metrics.latency = random.uniform(10, 50)
        self.metrics.jitter = random.uniform(5, 25)
        self.metrics.last_update = time.time()


class ConcurrentStreamManager:
    """Manages multiple concurrent streams."""
    
    def __init__(self, max_streams: int = 10, total_bandwidth: int = 100_000_000):
        self.max_streams = max_streams
        self.streams: Dict[str, StreamHandler] = {}
        self.buffers: Dict[str, StreamBuffer] = {}
        self.bandwidth_manager = BandwidthManager(total_bandwidth)
        self.quality_adapter = QualityAdapter()
        self.av_synchronizer = AVSynchronizer()
        self.lock = asyncio.Lock()
        self._monitor_task: Optional[asyncio.Task] = None
        
    async def add_stream(self, config: StreamConfig) -> bool:
        """Add a new stream."""
        async with self.lock:
            if len(self.streams) >= self.max_streams:
                print(f"Maximum streams ({self.max_streams}) reached")
                return False
            
            if config.stream_id in self.streams:
                print(f"Stream {config.stream_id} already exists")
                return False
            
            # Create buffer
            buffer = StreamBuffer(config.buffer_size, config.stream_id)
            self.buffers[config.stream_id] = buffer
            
            # Create handler
            handler = StreamHandler(
                config, buffer, self.bandwidth_manager,
                self.quality_adapter, self.av_synchronizer
            )
            self.streams[config.stream_id] = handler
            
            # Start stream
            await handler.start()
            print(f"Added stream {config.stream_id}")
            return True
    
    async def remove_stream(self, stream_id: str) -> bool:
        """Remove a stream."""
        async with self.lock:
            if stream_id not in self.streams:
                return False
            
            handler = self.streams[stream_id]
            await handler.stop()
            
            del self.streams[stream_id]
            del self.buffers[stream_id]
            
            print(f"Removed stream {stream_id}")
            return True
    
    async def start_monitoring(self):
        """Start performance monitoring."""
        self._monitor_task = asyncio.create_task(self._monitor_performance())
    
    async def stop_monitoring(self):
        """Stop performance monitoring."""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
    
    async def _monitor_performance(self):
        """Monitor system and stream performance."""
        while True:
            try:
                # System metrics
                cpu_percent = psutil.cpu_percent(interval=0.1)
                memory_info = psutil.virtual_memory()
                
                # Stream metrics
                active_streams = len(self.streams)
                total_bitrate = sum(
                    handler.metrics.bitrate 
                    for handler in self.streams.values()
                )
                
                # Buffer health
                avg_buffer_fill = np.mean([
                    handler.metrics.buffer_fill 
                    for handler in self.streams.values()
                ]) if self.streams else 0
                
                # Sync offsets
                max_sync_offset = max([
                    abs(self.av_synchronizer.get_sync_offset(sid))
                    for sid in self.streams.keys()
                ]) if self.streams else 0
                
                print(f"\n--- Performance Monitor ---")
                print(f"Active Streams: {active_streams}/{self.max_streams}")
                print(f"CPU Usage: {cpu_percent:.1f}%")
                print(f"Memory Usage: {memory_info.percent:.1f}%")
                print(f"Total Bitrate: {total_bitrate/1_000_000:.1f} Mbps")
                print(f"Avg Buffer Fill: {avg_buffer_fill:.1%}")
                print(f"Max AV Sync Offset: {max_sync_offset*1000:.1f}ms")
                
                # Check for issues
                if cpu_percent > 80:
                    print("WARNING: High CPU usage!")
                if memory_info.percent > 80:
                    print("WARNING: High memory usage!")
                if avg_buffer_fill < 0.3:
                    print("WARNING: Low buffer levels!")
                if max_sync_offset > 0.1:
                    print("WARNING: AV sync issues!")
                
                await asyncio.sleep(2)
                
            except Exception as e:
                print(f"Monitor error: {e}")
                await asyncio.sleep(2)
    
    def get_stream_states(self) -> Dict[str, str]:
        """Get current states of all streams."""
        return {
            stream_id: handler.state.value
            for stream_id, handler in self.streams.items()
        }
    
    def get_stream_metrics(self) -> Dict[str, StreamMetrics]:
        """Get metrics for all streams."""
        return {
            stream_id: handler.metrics
            for stream_id, handler in self.streams.items()
        }


@pytest.mark.asyncio
async def test_concurrent_streams():
    """Test concurrent stream handling."""
    print("Testing Concurrent Stream Handling")
    print("=" * 50)
    
    # Create manager
    manager = ConcurrentStreamManager(max_streams=10, total_bandwidth=50_000_000)
    
    # Start monitoring
    await manager.start_monitoring()
    
    # Test 1: Add multiple streams gradually
    print("\nTest 1: Adding streams gradually...")
    for i in range(5):
        config = StreamConfig(
            stream_id=f"stream_{i}",
            priority=random.choice(list(StreamPriority)),
            max_bitrate=random.randint(2_000_000, 8_000_000)
        )
        await manager.add_stream(config)
        await asyncio.sleep(1)
    
    # Let them run
    await asyncio.sleep(5)
    
    # Test 2: Add burst of streams
    print("\nTest 2: Adding burst of streams...")
    tasks = []
    for i in range(5, 10):
        config = StreamConfig(
            stream_id=f"stream_{i}",
            priority=StreamPriority.NORMAL,
            max_bitrate=5_000_000
        )
        tasks.append(manager.add_stream(config))
    
    await asyncio.gather(*tasks)
    await asyncio.sleep(5)
    
    # Test 3: Remove some streams
    print("\nTest 3: Removing streams dynamically...")
    for i in range(3):
        await manager.remove_stream(f"stream_{i}")
        await asyncio.sleep(1)
    
    # Test 4: Add high priority stream
    print("\nTest 4: Adding high priority stream...")
    config = StreamConfig(
        stream_id="critical_stream",
        priority=StreamPriority.CRITICAL,
        max_bitrate=10_000_000
    )
    await manager.add_stream(config)
    await asyncio.sleep(5)
    
    # Test 5: Simulate stream failures
    print("\nTest 5: Simulating stream failures...")
    # Force error state on some streams
    for stream_id in ["stream_5", "stream_7"]:
        if stream_id in manager.streams:
            manager.streams[stream_id].state = StreamState.ERROR
    
    await asyncio.sleep(3)
    
    # Get final states
    states = manager.get_stream_states()
    print("\nFinal Stream States:")
    for stream_id, state in states.items():
        print(f"  {stream_id}: {state}")
    
    # Cleanup
    await manager.stop_monitoring()
    for stream_id in list(manager.streams.keys()):
        await manager.remove_stream(stream_id)


@pytest.mark.asyncio
async def test_bandwidth_management():
    """Test bandwidth allocation and management."""
    print("\nTesting Bandwidth Management")
    print("=" * 50)
    
    manager = ConcurrentStreamManager(max_streams=20, total_bandwidth=20_000_000)
    
    # Add streams that exceed total bandwidth
    print("Adding streams exceeding total bandwidth...")
    for i in range(10):
        config = StreamConfig(
            stream_id=f"bw_test_{i}",
            priority=StreamPriority.NORMAL if i < 5 else StreamPriority.LOW,
            max_bitrate=5_000_000  # 5Mbps each = 50Mbps total
        )
        await manager.add_stream(config)
    
    await asyncio.sleep(3)
    
    # Check bandwidth allocations
    print("\nBandwidth Allocations:")
    for stream_id, allocation in manager.bandwidth_manager.allocations.items():
        print(f"  {stream_id}: {allocation/1_000_000:.1f} Mbps")
    
    # Add critical stream
    print("\nAdding critical priority stream...")
    config = StreamConfig(
        stream_id="critical_bw_test",
        priority=StreamPriority.CRITICAL,
        max_bitrate=10_000_000
    )
    await manager.add_stream(config)
    
    await asyncio.sleep(3)
    
    # Check reallocations
    print("\nBandwidth Reallocations:")
    for stream_id, allocation in manager.bandwidth_manager.allocations.items():
        print(f"  {stream_id}: {allocation/1_000_000:.1f} Mbps")
    
    # Cleanup
    for stream_id in list(manager.streams.keys()):
        await manager.remove_stream(stream_id)


@pytest.mark.asyncio
async def test_performance_limits():
    """Test system performance limits."""
    print("\nTesting Performance Limits")
    print("=" * 50)
    
    manager = ConcurrentStreamManager(max_streams=50, total_bandwidth=100_000_000)
    await manager.start_monitoring()
    
    # Gradually increase stream count
    stream_count = 0
    while stream_count < 30:
        config = StreamConfig(
            stream_id=f"perf_test_{stream_count}",
            priority=StreamPriority.NORMAL,
            max_bitrate=3_000_000
        )
        
        if await manager.add_stream(config):
            stream_count += 1
        else:
            break
        
        # Check performance every 5 streams
        if stream_count % 5 == 0:
            await asyncio.sleep(2)
            print(f"\nActive streams: {stream_count}")
            
            # Check for performance degradation
            cpu_percent = psutil.cpu_percent(interval=0.1)
            if cpu_percent > 70:
                print(f"High CPU usage detected: {cpu_percent:.1f}%")
            
            # Check buffer health
            metrics = manager.get_stream_metrics()
            low_buffers = sum(1 for m in metrics.values() if m.buffer_fill < 0.3)
            if low_buffers > 0:
                print(f"Low buffers detected: {low_buffers} streams")
    
    print(f"\nMax sustainable streams: {stream_count}")
    
    await asyncio.sleep(5)
    
    # Cleanup
    await manager.stop_monitoring()
    for i in range(stream_count):
        await manager.remove_stream(f"perf_test_{i}")


@pytest.mark.asyncio
async def test_error_recovery():
    """Test error recovery mechanisms."""
    print("\nTesting Error Recovery")
    print("=" * 50)
    
    manager = ConcurrentStreamManager(max_streams=10)
    
    # Add test streams
    for i in range(5):
        config = StreamConfig(stream_id=f"recovery_test_{i}")
        await manager.add_stream(config)
    
    print("Streams added, simulating failures...")
    await asyncio.sleep(2)
    
    # Simulate various failures
    print("\nSimulating buffer overflow...")
    buffer = manager.buffers["recovery_test_0"]
    for _ in range(buffer.size + 10):
        buffer.write(b"x" * 1000)
    print(f"Buffer overflow count: {buffer.overflow_count}")
    
    print("\nSimulating buffer underflow...")
    buffer = manager.buffers["recovery_test_1"]
    for _ in range(10):
        buffer.read(1000)
    print(f"Buffer underflow count: {buffer.underflow_count}")
    
    print("\nSimulating connection loss...")
    handler = manager.streams["recovery_test_2"]
    handler.state = StreamState.ERROR
    handler.metrics.packet_loss = 0.5
    
    await asyncio.sleep(2)
    
    # Check recovery
    states = manager.get_stream_states()
    print("\nStream states after failures:")
    for stream_id, state in states.items():
        print(f"  {stream_id}: {state}")
    
    # Cleanup
    for i in range(5):
        await manager.remove_stream(f"recovery_test_{i}")


async def main():
    """Run all concurrent stream handling tests."""
    tests = [
        test_concurrent_streams,
        test_bandwidth_management,
        test_performance_limits,
        test_error_recovery,
    ]
    
    for test in tests:
        try:
            await test()
            print("\n" + "="*50 + "\n")
        except Exception as e:
            print(f"Test failed: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    # Set up multiprocessing for CPU-bound tasks
    multiprocessing.set_start_method('spawn', force=True)
    
    # Run tests
    asyncio.run(main())