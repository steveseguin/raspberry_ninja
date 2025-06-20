#!/usr/bin/env python3
"""
Test script for MKV recording with renegotiation handling
Tests that the webrtc_subprocess_mkv.py properly handles data channel renegotiation
"""

import asyncio
import sys
import os
import subprocess
import json
import time
from uuid import uuid4

# Add the parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vdo_minimal_websocket import VdoClientProtocol, WebRTCSubprocessHandler

# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)


class TestMKVRecording:
    def __init__(self):
        self.room = f"testmkv{int(time.time())}"
        self.stream_id = str(uuid4())[:8]
        self.test_passed = False
        
    async def run_test(self):
        """Run the MKV recording test"""
        print(f"\n🧪 Testing MKV Recording with Renegotiation")
        print(f"   Room: {self.room}")
        print(f"   Stream ID: {self.stream_id}")
        print(f"   Testing: Data channel renegotiation handling")
        
        # Create WebRTC handler
        handler = WebRTCSubprocessHandler(
            room=self.room,
            stream_id=self.stream_id,
            mode='record',
            pipeline_version='auto',
            websocket_url='wss://vdo.ninja:443',
            bitrate=2000,
            encoder='vp8',
            record_file=f"test_mkv_{self.room}_{self.stream_id}.mkv",
            record_audio=True,
            subprocess_module='webrtc_subprocess_mkv'  # Use MKV subprocess
        )
        
        # Set up event handlers
        handler.on_ready = self.on_handler_ready
        handler.on_video_connected = self.on_video_connected
        handler.on_audio_connected = self.on_audio_connected
        
        # Connect via websocket
        protocol = VdoClientProtocol(handler, auto_retry=False)
        
        print("\n📡 Connecting to VDO.Ninja...")
        
        try:
            # Connect with timeout
            transport, _ = await asyncio.wait_for(
                asyncio.get_event_loop().create_connection(
                    lambda: protocol,
                    host='vdo.ninja',
                    port=443,
                    ssl=True
                ),
                timeout=10.0
            )
            
            print("✅ Connected to websocket")
            
            # Join room
            await protocol.join_room(handler.room, handler.stream_id, {'audioMuted': False})
            print(f"✅ Joined room: {handler.room}")
            
            # Let the test run for 15 seconds
            print("\n⏳ Waiting for media connection and renegotiation...")
            print("   - Initial connection establishes data channel")
            print("   - Media request sent via data channel")
            print("   - Renegotiation offer received with media tracks")
            print("   - Answer sent back, media pads should appear")
            
            await asyncio.sleep(15)
            
            # Check if video was connected
            if handler.video_connected:
                print("\n✅ TEST PASSED: Video pads were received!")
                print("   Renegotiation handling is working correctly")
                self.test_passed = True
            else:
                print("\n❌ TEST FAILED: No video pads received")
                print("   Renegotiation offer may not have been processed")
                
                # Check subprocess logs for clues
                if hasattr(handler, '_subprocess_handler'):
                    print("\n📝 Recent subprocess logs:")
                    logs = getattr(handler._subprocess_handler, '_recent_logs', [])
                    for log in logs[-20:]:  # Last 20 logs
                        print(f"   {log}")
            
            # Clean up
            print("\n🧹 Cleaning up...")
            handler.stop()
            transport.close()
            
            # Check if file was created
            output_file = f"test_mkv_{self.room}_{self.stream_id}.mkv"
            if os.path.exists(output_file):
                size = os.path.getsize(output_file)
                print(f"📄 Output file created: {output_file} ({size} bytes)")
                if size > 1000:  # More than 1KB suggests actual data
                    print("   File contains data - recording worked!")
                else:
                    print("   File is too small - may not contain video data")
                    
                # Clean up test file
                os.remove(output_file)
                print("   Test file removed")
            else:
                print("❌ No output file created")
                
        except asyncio.TimeoutError:
            print("❌ Connection timeout")
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            
        return self.test_passed
            
    def on_handler_ready(self):
        """Called when handler is ready"""
        print("🚀 Handler ready")
        
    def on_video_connected(self):
        """Called when video is connected"""
        print("📹 Video connected!")
        
    def on_audio_connected(self):
        """Called when audio is connected"""
        print("🎤 Audio connected!")


async def main():
    """Main test runner"""
    test = TestMKVRecording()
    passed = await test.run_test()
    
    print("\n" + "="*50)
    if passed:
        print("✅ ALL TESTS PASSED")
        print("The MKV subprocess now correctly handles renegotiation!")
    else:
        print("❌ TESTS FAILED")
        print("Check the logs above for details")
    print("="*50 + "\n")
    
    return 0 if passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)