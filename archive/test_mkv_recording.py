#!/usr/bin/env python3
"""
Test MKV recording with audio/video muxing
Connects to the testroom123999999999 room and records streams
"""

import asyncio
import json
import subprocess
import time
import os
import signal
import sys

# Global subprocess reference for cleanup
active_subprocess = None

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print("\nCaught signal, cleaning up...")
    if active_subprocess:
        active_subprocess.terminate()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

async def run_mkv_subprocess(stream_id, room="testroom123999999999", audio=True):
    """Run MKV subprocess for a single stream"""
    global active_subprocess
    
    config = {
        'stream_id': stream_id,
        'mode': 'record',
        'room': room,
        'record_audio': audio,
        'stun_server': 'stun://stun.cloudflare.com:3478'
    }
    
    print(f"\n🚀 Starting MKV recording subprocess for stream: {stream_id}")
    print(f"   Room: {room}")
    print(f"   Audio: {'enabled' if audio else 'disabled'}")
    
    # Start subprocess
    proc = await asyncio.create_subprocess_exec(
        sys.executable, 'webrtc_subprocess_mkv.py',
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    active_subprocess = proc
    
    # Send configuration
    proc.stdin.write((json.dumps(config) + '\n').encode())
    await proc.stdin.drain()
    
    # Task to read stdout
    async def read_stdout():
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line.decode())
                if msg['type'] == 'log':
                    print(f"[{msg['level']}] {msg['message']}")
                else:
                    print(f"Message: {msg}")
            except Exception as e:
                print(f"Failed to parse: {line.decode().strip()}")
    
    # Task to read stderr
    async def read_stderr():
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            print(f"STDERR: {line.decode().strip()}")
    
    # Start reading tasks
    stdout_task = asyncio.create_task(read_stdout())
    stderr_task = asyncio.create_task(read_stderr())
    
    # Wait for ready signal
    await asyncio.sleep(1)
    
    # Send start command
    print("\n📡 Sending start command...")
    proc.stdin.write((json.dumps({'type': 'start'}) + '\n').encode())
    await proc.stdin.drain()
    
    # Simulate WebRTC offer/answer exchange
    # In real usage, this would come from the websocket connection
    # For testing, we'll use a mock offer
    
    print("\n⏳ Waiting for WebRTC connection...")
    print("   Note: This requires an active stream in the room")
    print("   You can join the room at: https://vdo.ninja/?view=" + room)
    
    # Keep running until interrupted
    try:
        await proc.wait()
    except asyncio.CancelledError:
        print("\nStopping subprocess...")
        proc.stdin.write((json.dumps({'type': 'stop'}) + '\n').encode())
        await proc.stdin.drain()
        await asyncio.sleep(1)
        proc.terminate()
        
    # Wait for tasks to complete
    await stdout_task
    await stderr_task
    
    return proc.returncode

async def test_with_publish_py():
    """Test MKV recording by running publish.py with room recording"""
    print("\n🎬 Testing MKV recording with publish.py")
    print("=" * 50)
    
    # First, let's run publish.py to join the room
    publish_cmd = [
        sys.executable, 'publish.py',
        '--room', 'testroom123999999999',
        '--record-room',  # Enable room recording
        '--audio',  # Enable audio recording (muxed with video)
        '--noaudio',  # Disable local audio input for testing
        '--novideo'  # Disable local video input for testing
    ]
    
    print(f"\n📺 Starting publish.py in view mode...")
    print(f"Command: {' '.join(publish_cmd)}")
    
    # Run publish.py
    proc = await asyncio.create_subprocess_exec(
        *publish_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    # Monitor output
    async def monitor_output():
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            output = line.decode().strip()
            print(f"[publish.py] {output}")
            
            # Look for stream detection
            if "New stream detected" in output or "RECORDING START" in output:
                print("\n✅ Stream detected! Recording should be active")
    
    async def monitor_stderr():
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            print(f"[publish.py ERROR] {line.decode().strip()}")
    
    # Start monitoring
    stdout_task = asyncio.create_task(monitor_output())
    stderr_task = asyncio.create_task(monitor_stderr())
    
    print("\n⏳ Waiting for streams to appear in the room...")
    print("   You can publish a stream at: https://vdo.ninja/?push=" + "testroom123999999999")
    print("   Press Ctrl+C to stop recording")
    
    try:
        await proc.wait()
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping recording...")
        proc.terminate()
        await proc.wait()
    
    await stdout_task
    await stderr_task
    
    # Check for recorded files
    print("\n📁 Checking for recorded files:")
    mkv_files = sorted([f for f in os.listdir('.') if f.endswith('.mkv')])
    if mkv_files:
        print(f"\n✅ Found {len(mkv_files)} MKV file(s):")
        for f in mkv_files[-5:]:  # Show last 5 files
            size = os.path.getsize(f) / (1024 * 1024)
            print(f"   {f} ({size:.2f} MB)")
            
            # Try to get media info
            try:
                result = subprocess.run(
                    ['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', f],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    info = json.loads(result.stdout)
                    video_streams = [s for s in info['streams'] if s['codec_type'] == 'video']
                    audio_streams = [s for s in info['streams'] if s['codec_type'] == 'audio']
                    print(f"      Video streams: {len(video_streams)}")
                    print(f"      Audio streams: {len(audio_streams)}")
                    if video_streams:
                        v = video_streams[0]
                        print(f"      Video: {v.get('codec_name', 'unknown')} {v.get('width', '?')}x{v.get('height', '?')}")
                    if audio_streams:
                        a = audio_streams[0]
                        print(f"      Audio: {a.get('codec_name', 'unknown')} {a.get('sample_rate', '?')}Hz")
            except:
                pass
    else:
        print("   No MKV files found")

async def main():
    """Main test function"""
    print("MKV Audio/Video Recording Test")
    print("==============================")
    
    # Test mode selection
    if len(sys.argv) > 1 and sys.argv[1] == '--direct':
        # Direct subprocess test
        stream_id = sys.argv[2] if len(sys.argv) > 2 else 'test_stream'
        await run_mkv_subprocess(stream_id)
    else:
        # Test with publish.py integration
        await test_with_publish_py()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")