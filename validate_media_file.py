#!/usr/bin/env python3
"""
Media file validation using GStreamer
Validates that recorded files can be decoded and played
"""

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import os
import sys
import time
from pathlib import Path

# Initialize GStreamer
Gst.init(None)


class MediaFileValidator:
    """Validates media files using GStreamer pipelines"""
    
    def __init__(self):
        self.errors = []
        self.duration = None
        self.format_info = {}
        
    def validate_file(self, filepath, timeout=10):
        """
        Validate a media file by attempting to decode and play it
        
        Args:
            filepath: Path to the media file
            timeout: Maximum time to wait for validation (seconds)
            
        Returns:
            tuple: (is_valid, info_dict)
        """
        if not os.path.exists(filepath):
            return False, {"error": "File does not exist"}
            
        file_ext = Path(filepath).suffix.lower()
        
        # Build pipeline based on file type
        if file_ext in ['.ts', '.m3u8']:
            # MPEG-TS format (H.264)
            pipeline_str = (
                f"filesrc location={filepath} ! "
                "tsdemux ! h264parse ! avdec_h264 ! "
                "videoconvert ! fakesink name=vsink"
            )
        elif file_ext in ['.mkv', '.webm']:
            # Matroska/WebM format (VP8/VP9)
            pipeline_str = (
                f"filesrc location={filepath} ! "
                "matroskademux ! decodebin ! "
                "videoconvert ! fakesink name=vsink"
            )
        elif file_ext == '.mp4':
            # MP4 format
            pipeline_str = (
                f"filesrc location={filepath} ! "
                "qtdemux ! decodebin ! "
                "videoconvert ! fakesink name=vsink"
            )
        else:
            # Generic pipeline for unknown formats
            pipeline_str = (
                f"filesrc location={filepath} ! "
                "decodebin ! videoconvert ! fakesink name=vsink"
            )
            
        try:
            # Create pipeline
            self.pipeline = Gst.parse_launch(pipeline_str)
            
            # Get bus for messages
            bus = self.pipeline.get_bus()
            bus.add_signal_watch()
            
            # Track state
            self.got_eos = False
            self.got_error = False
            self.error_message = None
            self.frames_rendered = 0
            
            # Connect to messages
            def on_message(bus, message):
                t = message.type
                if t == Gst.MessageType.EOS:
                    self.got_eos = True
                elif t == Gst.MessageType.ERROR:
                    self.got_error = True
                    err, debug = message.parse_error()
                    self.error_message = f"{err}: {debug}"
                elif t == Gst.MessageType.STATE_CHANGED:
                    if message.src == self.pipeline:
                        old_state, new_state, pending = message.parse_state_changed()
                        if new_state == Gst.State.PLAYING:
                            # Query duration when playing
                            success, self.duration = self.pipeline.query_duration(Gst.Format.TIME)
                            if success:
                                self.duration = self.duration / Gst.SECOND  # Convert to seconds
                                
            bus.connect("message", on_message)
            
            # Get fakesink to count frames
            vsink = self.pipeline.get_by_name("vsink")
            if vsink:
                # Enable signal emission
                vsink.set_property("signal-handoffs", True)
                
                def on_handoff(element, buffer, pad):
                    self.frames_rendered += 1
                    
                vsink.connect("handoff", on_handoff)
            
            # Start playing
            ret = self.pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                return False, {"error": "Failed to start pipeline"}
                
            # Wait for completion or timeout
            start_time = time.time()
            while True:
                if self.got_eos or self.got_error:
                    break
                    
                if time.time() - start_time > timeout:
                    # For large files, getting some frames is enough
                    if self.frames_rendered > 0:
                        break
                    else:
                        self.error_message = "Timeout waiting for frames"
                        self.got_error = True
                        break
                        
                # Process bus messages
                msg = bus.timed_pop_filtered(
                    100 * Gst.MSECOND,
                    Gst.MessageType.ERROR | Gst.MessageType.EOS
                )
                if msg:
                    if msg.type == Gst.MessageType.ERROR:
                        self.got_error = True
                        err, debug = msg.parse_error()
                        self.error_message = f"{err}: {debug}"
                        break
                    elif msg.type == Gst.MessageType.EOS:
                        self.got_eos = True
                        break
                        
            # Stop pipeline
            self.pipeline.set_state(Gst.State.NULL)
            
            # Prepare result
            info = {
                "valid": not self.got_error and self.frames_rendered > 0,
                "frames_decoded": self.frames_rendered,
                "duration_seconds": self.duration,
                "file_size_bytes": os.path.getsize(filepath),
                "format": file_ext[1:] if file_ext else "unknown"
            }
            
            if self.got_error:
                info["error"] = self.error_message
                
            if self.frames_rendered > 0 and self.duration:
                info["estimated_fps"] = self.frames_rendered / min(self.duration, timeout)
                
            return info["valid"], info
            
        except Exception as e:
            return False, {"error": f"Exception during validation: {str(e)}"}
            
    def validate_multiple_files(self, file_list):
        """Validate multiple files and return summary"""
        results = {}
        valid_count = 0
        
        for filepath in file_list:
            is_valid, info = self.validate_file(filepath)
            results[filepath] = info
            if is_valid:
                valid_count += 1
                
        summary = {
            "total_files": len(file_list),
            "valid_files": valid_count,
            "invalid_files": len(file_list) - valid_count,
            "results": results
        }
        
        return summary


def validate_recording(filepath, verbose=True):
    """
    Simple function to validate a single recording
    
    Args:
        filepath: Path to the media file
        verbose: Print detailed information
        
    Returns:
        bool: True if file is valid
    """
    validator = MediaFileValidator()
    is_valid, info = validator.validate_file(filepath)
    
    if verbose:
        print(f"\nValidating: {filepath}")
        print(f"Valid: {is_valid}")
        if is_valid:
            print(f"Format: {info.get('format', 'unknown')}")
            print(f"Frames decoded: {info.get('frames_decoded', 0)}")
            if info.get('duration_seconds'):
                print(f"Duration: {info['duration_seconds']:.2f} seconds")
            print(f"File size: {info.get('file_size_bytes', 0):,} bytes")
            if info.get('estimated_fps'):
                print(f"Estimated FPS: {info['estimated_fps']:.1f}")
        else:
            print(f"Error: {info.get('error', 'Unknown error')}")
            
    return is_valid


def main():
    """Command line interface for media validation"""
    if len(sys.argv) < 2:
        print("Usage: python validate_media_file.py <media_file> [media_file2 ...]")
        sys.exit(1)
        
    files = sys.argv[1:]
    validator = MediaFileValidator()
    
    if len(files) == 1:
        # Single file validation
        is_valid, info = validator.validate_file(files[0])
        if is_valid:
            print(f"✅ {files[0]} is valid")
            print(f"   Frames: {info.get('frames_decoded', 0)}")
            if info.get('duration_seconds'):
                print(f"   Duration: {info['duration_seconds']:.2f}s")
        else:
            print(f"❌ {files[0]} is invalid")
            print(f"   Error: {info.get('error', 'Unknown')}")
            sys.exit(1)
    else:
        # Multiple file validation
        summary = validator.validate_multiple_files(files)
        print(f"\nValidation Summary:")
        print(f"Total files: {summary['total_files']}")
        print(f"Valid files: {summary['valid_files']}")
        print(f"Invalid files: {summary['invalid_files']}")
        
        print("\nDetails:")
        for filepath, info in summary['results'].items():
            if info.get('valid'):
                print(f"✅ {filepath} - {info.get('frames_decoded', 0)} frames")
            else:
                print(f"❌ {filepath} - {info.get('error', 'Unknown error')}")
                
        if summary['invalid_files'] > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()