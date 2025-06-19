#!/usr/bin/env python3
"""
Patch to fix recording functionality in publish.py
This adds proper recording support when using --view and --record together
"""
import os
import sys
import shutil
from datetime import datetime


def create_backup(filename):
    """Create a backup of the original file"""
    backup_name = f"{filename}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(filename, backup_name)
    print(f"Created backup: {backup_name}")
    return backup_name


def apply_recording_patch():
    """Apply the recording fix to publish.py"""
    
    filename = "publish.py"
    
    if not os.path.exists(filename):
        print(f"Error: {filename} not found!")
        return False
    
    # Create backup
    backup = create_backup(filename)
    
    # Read the file
    with open(filename, 'r') as f:
        lines = f.readlines()
    
    # Find the line where display mode is set up
    patch_applied = False
    in_view_block = False
    insert_index = -1
    
    for i, line in enumerate(lines):
        # Look for the display output mode setup
        if 'elif self.view:' in line and 'print("DISPLAY OUTPUT MODE BEING SETUP")' in lines[i+1]:
            # Found the location to patch
            print(f"Found patch location at line {i+1}")
            
            # Insert recording check before display setup
            recording_code = '''                # Check if we're recording instead of displaying
                if self.record:
                    print("RECORDING MODE ACTIVATED")
                    timestamp = str(int(time.time()))
                    filename = self.record + "_" + timestamp + ".ts"
                    
                    if "VP8" in name:
                        out = Gst.parse_bin_from_description(
                            "queue ! rtpvp8depay ! mpegtsmux ! filesink location=" + filename, True)
                        print(f"Recording VP8 to: {filename}")
                    elif "H264" in name:
                        out = Gst.parse_bin_from_description(
                            "queue ! rtph264depay ! h264parse ! mpegtsmux ! filesink location=" + filename, True)
                        print(f"Recording H264 to: {filename}")
                    elif "VP9" in name:
                        out = Gst.parse_bin_from_description(
                            "queue ! rtpvp9depay ! mpegtsmux ! filesink location=" + filename, True)
                        print(f"Recording VP9 to: {filename}")
                    else:
                        print(f"Unsupported codec for recording: {name}")
                        return
                        
                    self.pipe.add(out)
                    out.sync_state_with_parent()
                    sink = out.get_static_pad('sink')
                    pad.link(sink)
                    
                    # Track recording state
                    if not hasattr(self, 'recording_files'):
                        self.recording_files = []
                    self.recording_files.append(filename)
                    
                    return  # Don't set up display
                    
'''
            # Insert the recording code after the elif self.view: line
            lines.insert(i+1, recording_code)
            patch_applied = True
            break
    
    if not patch_applied:
        print("Error: Could not find the location to apply patch!")
        print("The file structure may have changed.")
        return False
    
    # Write the patched file
    with open(filename, 'w') as f:
        f.writelines(lines)
    
    print("✅ Patch applied successfully!")
    print("\nThe recording functionality has been fixed.")
    print("You can now use: python3 publish.py --view <stream_id> --record <filename_prefix>")
    print(f"\nTo restore the original file, use: cp {backup} {filename}")
    
    return True


def test_patch():
    """Test if the patch was applied correctly"""
    
    # Check if the patched code exists
    with open("publish.py", 'r') as f:
        content = f.read()
    
    if "RECORDING MODE ACTIVATED" in content:
        print("\n✅ Patch verification successful!")
        return True
    else:
        print("\n❌ Patch verification failed!")
        return False


if __name__ == "__main__":
    print("Recording Functionality Patch for publish.py")
    print("=" * 50)
    
    # Apply the patch
    if apply_recording_patch():
        # Verify the patch
        test_patch()
        
        print("\n" + "=" * 50)
        print("Usage examples:")
        print("1. Record a single stream:")
        print("   python3 publish.py --view strve123 --record my_recording")
        print("\n2. Record from a room:")
        print("   python3 publish.py --room myroom --view streamid --record recording")
        print("\nFiles will be saved as: <prefix>_<timestamp>.ts")
    else:
        print("\nPatch failed! Please check the error messages above.")