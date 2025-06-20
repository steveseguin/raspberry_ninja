#!/usr/bin/env python3
"""
Test that room NDI mode properly uses subprocess and creates NDI streams
"""

import asyncio
import sys
import time

async def test_room_ndi():
    """Test room NDI with subprocess"""
    print("Starting room NDI test...")
    
    # Run publish.py with room NDI
    proc = await asyncio.create_subprocess_exec(
        'python3', 'publish.py',
        '--room', 'testroom123999999999',
        '--room-ndi',
        '--password', 'false',
        '--debug',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    
    # Collect output for 20 seconds
    start_time = time.time()
    output_lines = []
    
    try:
        while time.time() - start_time < 20:
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=0.1)
                if not line:
                    break
                line = line.decode('utf-8').strip()
                output_lines.append(line)
                
                # Print interesting lines
                if any(keyword in line.lower() for keyword in ['ndi', 'subprocess', 'error', 'creating', 'room_ndi', 'mapping uuid', '📹']):
                    print(f"[{time.time()-start_time:.1f}s] {line}")
                    
            except asyncio.TimeoutError:
                continue
                
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        proc.terminate()
        await proc.wait()
    
    # Analyze output
    print("\n" + "="*50)
    print("ANALYSIS:")
    print("="*50)
    
    # Check if subprocess was created
    subprocess_created = any('Creating subprocess' in line for line in output_lines)
    print(f"✓ Subprocess created: {subprocess_created}")
    
    # Check if NDI was mentioned
    ndi_mentioned = any('ndi' in line.lower() for line in output_lines)
    print(f"✓ NDI mentioned: {ndi_mentioned}")
    
    # Check for errors
    errors = [line for line in output_lines if 'error' in line.lower()]
    if errors:
        print(f"✗ Errors found: {len(errors)}")
        for error in errors[:5]:
            print(f"  - {error}")
    else:
        print("✓ No errors found")
    
    # Check for room_ndi flag
    room_ndi_found = any('room_ndi' in line for line in output_lines)
    print(f"✓ room_ndi flag found: {room_ndi_found}")
    
    # Save full output
    with open('test_room_ndi_output.txt', 'w') as f:
        f.write('\n'.join(output_lines))
    print(f"\nFull output saved to test_room_ndi_output.txt ({len(output_lines)} lines)")

if __name__ == "__main__":
    asyncio.run(test_room_ndi())