#!/usr/bin/env python3
"""Debug audio recording issue"""

import asyncio
import sys

async def debug_audio():
    print("=== Debugging Audio Recording ===\n")
    
    # Record with debug output
    process = await asyncio.create_subprocess_exec(
        sys.executable, 'publish.py',
        '--room', 'testroom123999999999',
        '--record-room',
        '--audio',
        '--password', 'false',
        '--debug',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    
    print("Monitoring for audio events...\n")
    
    start_time = asyncio.get_event_loop().time()
    audio_events = []
    
    while asyncio.get_event_loop().time() - start_time < 30:
        try:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=0.5)
            if line:
                decoded = line.decode().strip()
                
                # Look for audio-related messages
                if any(keyword in decoded for keyword in [
                    "AUDIO", "audio", "Opus", "opus", "mka", "_audio.",
                    "Audio recording", "rtpopusdepay", "link audio"
                ]):
                    print(f"[{int(asyncio.get_event_loop().time() - start_time)}s] {decoded}")
                    audio_events.append(decoded)
                    
        except asyncio.TimeoutError:
            pass
    
    print("\nStopping...")
    process.terminate()
    await process.wait()
    
    print(f"\n=== Audio Events Summary ({len(audio_events)} events) ===")
    for event in audio_events[-20:]:  # Last 20 events
        print(f"  {event}")

if __name__ == "__main__":
    asyncio.run(debug_audio())