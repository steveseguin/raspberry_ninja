#!/usr/bin/env python3
"""
Fix for recording functionality in publish.py
This demonstrates how recording should work when viewing a stream
"""
import subprocess
import sys
import time
import os
from pathlib import Path


def record_stream(stream_id, room=None, duration=30, output_dir="recordings"):
    """
    Record a stream using GStreamer directly
    """
    # Create output directory
    Path(output_dir).mkdir(exist_ok=True)
    
    # Build the pipeline
    timestamp = int(time.time())
    output_file = f"{output_dir}/{stream_id}_{timestamp}.ts"
    
    # Create a custom pipeline that records
    pipeline = f"""
    gst-launch-1.0 -e \
    webrtcbin name=webrtc bundle-policy=max-bundle \
    ! rtph264depay ! h264parse ! mpegtsmux ! filesink location={output_file}
    """
    
    # For now, use a simpler approach - modify publish.py behavior
    # Create a wrapper script that forces recording
    wrapper_script = f"""
import sys
import os

# Monkey patch to force recording instead of display
original_file = '{os.path.abspath("publish.py")}'

# Read the original file
with open(original_file, 'r') as f:
    content = f.read()

# Replace the display setup with recording setup
content = content.replace(
    'elif self.view:',
    '''elif self.view and self.record:
                    # RECORDING MODE
                    print("RECORDING MODE ACTIVATED")
                    timestamp = str(int(time.time()))
                    filename = self.record + "_" + timestamp + ".ts"
                    
                    if "VP8" in name:
                        out = Gst.parse_bin_from_description(
                            "queue ! rtpvp8depay ! mpegtsmux ! filesink location=" + filename, True)
                    elif "H264" in name:
                        out = Gst.parse_bin_from_description(
                            "queue ! rtph264depay ! h264parse ! mpegtsmux ! filesink location=" + filename, True)
                    else:
                        print("Unsupported codec for recording:", name)
                        return
                        
                    self.pipe.add(out)
                    out.sync_state_with_parent()
                    sink = out.get_static_pad('sink')
                    pad.link(sink)
                    print(f"Recording to: {{filename}}")
                    return
                elif self.view:'''
)

# Execute the modified code
exec(compile(content, original_file, 'exec'))
"""
    
    # Write the wrapper
    wrapper_file = f"{output_dir}/record_wrapper.py"
    with open(wrapper_file, 'w') as f:
        f.write(wrapper_script)
    
    # Build command
    cmd = [
        sys.executable,
        wrapper_file,
        "--view", stream_id,
        "--record", stream_id,
        "--noaudio"
    ]
    
    if room:
        cmd.extend(["--room", room])
    
    print(f"Recording {stream_id} for {duration} seconds...")
    print(f"Output will be saved to: {output_file}")
    
    # Start recording
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    try:
        # Let it record
        time.sleep(duration)
        
        # Stop recording
        proc.terminate()
        proc.wait(timeout=5)
        
        # Check if file was created
        if os.path.exists(output_file):
            size = os.path.getsize(output_file)
            print(f"✅ Recording successful! File size: {size:,} bytes")
            return output_file
        else:
            print("❌ Recording failed - no output file created")
            
            # Get process output
            stdout, stderr = proc.communicate(timeout=1)
            if stdout:
                print("STDOUT:", stdout.decode())
            if stderr:
                print("STDERR:", stderr.decode())
                
            return None
            
    except Exception as e:
        print(f"Error during recording: {e}")
        proc.kill()
        return None
    finally:
        # Clean up wrapper
        if os.path.exists(wrapper_file):
            os.remove(wrapper_file)


def test_recording():
    """Test recording functionality"""
    print("Testing recording functionality...")
    
    # Test with known stream
    result = record_stream("strve123", duration=15)
    
    if result:
        print(f"\nRecording test passed! Output: {result}")
        
        # Verify with ffprobe if available
        try:
            info = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", 
                 "-show_format", result],
                capture_output=True,
                text=True
            )
            if info.returncode == 0:
                print("File validated with ffprobe ✅")
        except:
            pass
    else:
        print("\nRecording test failed ❌")


if __name__ == "__main__":
    test_recording()