#!/usr/bin/env python3
"""
Extended version of publish.py with working recording functionality
This demonstrates how recording should work
"""
import os
import sys
import time
import asyncio
import subprocess
import signal
from pathlib import Path

# Import the original publish.py functionality
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from publish import *


class WebRTCClientWithRecording(WebRTCClient):
    """Extended WebRTC client with proper recording support"""
    
    def __init__(self, params):
        """Initialize with recording support"""
        super().__init__(params)
        self.recording_files = []
        self.recording_enabled = bool(self.record)
        
        # Override the display mode if recording
        if self.recording_enabled and self.view:
            print(f"Recording mode enabled for stream: {self.view}")
            print(f"Files will be saved with prefix: {self.record}")
    
    def on_incoming_stream(self, webrtc, pad):
        """Override to add recording support"""
        try:
            if Gst.PadDirection.SRC != pad.direction:
                print("pad direction wrong?")
                return
            caps = pad.get_current_caps()
            name = caps.to_string()
            print(f"Incoming stream caps: {name}")
            
            # Check if we're in recording mode
            if self.recording_enabled and self.view and "video" in name:
                self.setup_recording_pipeline(pad, name)
                return
            
            # Otherwise, use the original behavior
            super().on_incoming_stream(webrtc, pad)
            
        except Exception as e:
            print(f"Error in on_incoming_stream: {e}")
            import traceback
            traceback.print_exc()
    
    def setup_recording_pipeline(self, pad, name):
        """Set up recording pipeline for incoming stream"""
        print("RECORDING MODE ACTIVATED")
        timestamp = str(int(time.time()))
        filename = f"{self.record}_{timestamp}.ts"
        
        try:
            if "VP8" in name:
                pipeline_str = "queue ! rtpvp8depay ! mpegtsmux ! filesink location=" + filename
                print(f"Recording VP8 to: {filename}")
            elif "H264" in name:
                pipeline_str = "queue ! rtph264depay ! h264parse ! mpegtsmux ! filesink location=" + filename
                print(f"Recording H264 to: {filename}")
            elif "VP9" in name:
                pipeline_str = "queue ! rtpvp9depay ! mpegtsmux ! filesink location=" + filename
                print(f"Recording VP9 to: {filename}")
            else:
                print(f"Unsupported codec for recording: {name}")
                # Fall back to display mode
                super().on_incoming_stream(pad.get_parent(), pad)
                return
            
            # Create recording bin
            out = Gst.parse_bin_from_description(pipeline_str, True)
            self.pipe.add(out)
            out.sync_state_with_parent()
            sink = out.get_static_pad('sink')
            pad.link(sink)
            
            # Track recording file
            self.recording_files.append(filename)
            print(f"✅ Recording pipeline set up successfully")
            
            # Also set up audio recording if available
            # This will be called separately for audio pad
            
        except Exception as e:
            print(f"Error setting up recording pipeline: {e}")
            import traceback
            traceback.print_exc()
    
    def cleanup(self):
        """Clean up and report recorded files"""
        if self.recording_files:
            print("\n" + "="*50)
            print("Recording Summary:")
            for f in self.recording_files:
                if os.path.exists(f):
                    size = os.path.getsize(f)
                    print(f"  ✅ {f} ({size:,} bytes)")
                else:
                    print(f"  ❌ {f} (not found)")
            print("="*50)
        
        # Call parent cleanup
        super().cleanup_pipeline()


def test_recording_implementation():
    """Test the recording implementation"""
    import argparse
    
    print("Testing Recording Implementation")
    print("="*50)
    
    # Create test arguments
    parser = argparse.ArgumentParser()
    
    # Add all the arguments that publish.py expects
    for arg in ['view', 'record', 'room', 'noaudio', 'server', 'password', 
                'h264', 'vp8', 'vp9', 'bitrate', 'test']:
        parser.add_argument(f'--{arg}', default=None)
    
    # Set up test parameters
    test_args = [
        '--view', 'strve123',
        '--record', 'test_recording',
        '--noaudio'
    ]
    
    args = parser.parse_args(test_args)
    
    # Set defaults
    args.server = "wss://wss.vdo.ninja:443"
    args.password = "someEncryptionKey123"
    args.bitrate = 2500
    
    # Set all other required attributes
    for attr in dir(args):
        if not attr.startswith('_') and getattr(args, attr) is None:
            setattr(args, attr, False)
    
    # Create recording client
    client = WebRTCClientWithRecording(args)
    
    # Run for 20 seconds
    print("\nStarting recording test...")
    print("Recording for 20 seconds...")
    
    # Set up signal handler
    def signal_handler(sig, frame):
        print("\nStopping recording...")
        client.cleanup()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run the client
    try:
        asyncio.run(client.connect())
        asyncio.run(client.loop())
    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        client.cleanup()


async def test_complete_flow():
    """Test complete publishing and recording flow"""
    print("\nComplete Flow Test")
    print("="*50)
    
    # Start a test publisher
    test_room = f"test_room_{int(time.time())}"
    test_stream = "test_publisher"
    
    print(f"Starting test publisher in room: {test_room}")
    publisher_cmd = [
        'python3', 'publish.py',
        '--test',
        '--room', test_room,
        '--stream', test_stream,
        '--noaudio'
    ]
    
    publisher = subprocess.Popen(publisher_cmd)
    
    # Wait for publisher to connect
    await asyncio.sleep(5)
    
    # Start recorder
    print(f"Starting recorder for stream: {test_stream}")
    recorder_cmd = [
        'python3', __file__,
        '--view', test_stream,
        '--record', 'flow_test',
        '--room', test_room,
        '--noaudio'
    ]
    
    recorder = subprocess.Popen(recorder_cmd)
    
    # Let it record
    print("Recording for 15 seconds...")
    await asyncio.sleep(15)
    
    # Stop both
    print("Stopping...")
    recorder.terminate()
    publisher.terminate()
    
    # Wait for cleanup
    recorder.wait(timeout=5)
    publisher.wait(timeout=5)
    
    # Check for output files
    recordings = list(Path('.').glob('flow_test_*.ts'))
    
    print("\nResults:")
    if recordings:
        print(f"✅ Success! Created {len(recordings)} recording files:")
        for r in recordings:
            print(f"   - {r} ({r.stat().st_size:,} bytes)")
    else:
        print("❌ Failed - no recording files created")


if __name__ == '__main__':
    if len(sys.argv) > 1:
        # Run as a recorder with command line args
        # Replace the WebRTCClient with our recording version
        import publish
        original_class = publish.WebRTCClient
        publish.WebRTCClient = WebRTCClientWithRecording
        
        # Run the main function
        asyncio.run(main())
    else:
        # Run tests
        print("Running Recording Tests")
        print("="*50)
        
        # Test 1: Basic recording implementation
        # test_recording_implementation()
        
        # Test 2: Complete flow
        asyncio.run(test_complete_flow())