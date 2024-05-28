import argparse
import asyncio
import sys
import traceback

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

def handle_unhandled_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    print("!!! Unhandled exception!!!")  
    print("Type:", exc_type)
    print("Value:", exc_value)
    print("Traceback:", ''.join(traceback.format_tb(exc_traceback)))
    tb = traceback.extract_tb(exc_traceback)
    for frame in tb:
        print(f"File \"{frame.filename}\", line {frame.lineno}, in {frame.name}")

sys.excepthook = handle_unhandled_exception

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--room', type=str, required=True, help='Specify the vdo.ninja room to record from')
    parser.add_argument('--duration', type=int, default=0, help='Specify the recording duration in minutes (default: unlimited)')
    parser.add_argument('--audio-only', action='store_true', help='Record audio only')
    parser.add_argument('--format', type=str, default='mp4', choices=['mp3', 'wav', 'flv', 'mp4'], help='Specify the recording format (default: mp4)')
    args = parser.parse_args()

    Gst.init(None)

    room = args.room
    duration = args.duration * 60 * Gst.SECOND if args.duration > 0 else -1
    audio_only = args.audio_only
    format = args.format

    if format == 'mp3':
        encoder = 'lamemp3enc'
        muxer = 'id3v2mux'
        extension = 'mp3'
    elif format == 'wav': 
        encoder = 'wavenc'
        muxer = ''
        extension = 'wav'
    elif format == 'flv':
        encoder = 'avenc_flv'
        muxer = 'flvmux'
        extension = 'flv'
    else: # mp4
        encoder = 'x264enc'
        muxer = 'mp4mux'
        extension = 'mp4'

    if audio_only:
        PIPELINE_DESC = f'webrtcbin name=sendrecv stun-server=stun://stun4.l.google.com:19302 bundle-policy=max-bundle ! rtpopusdepay ! opusdec ! audioconvert ! {encoder} ! {muxer} ! filesink location={room}.{extension}'
    else:
        PIPELINE_DESC = f'webrtcbin name=sendrecv stun-server=stun://stun4.l.google.com:19302 bundle-policy=max-bundle ! rtph264depay ! avdec_h264 ! {encoder} ! {muxer} ! filesink location={room}.{extension}'
    
    print('gst-launch-1.0 '+ PIPELINE_DESC.replace('(', '\\(').replace(')', '\\)'))
    pipe = Gst.parse_launch(PIPELINE_DESC)
    pipe.set_state(Gst.State.PLAYING)
    print(f"RECORDING STARTED from room: {room}")
    
    loop = asyncio.get_event_loop()
    try:
        if duration > 0:
            print(f"Recording will stop after {args.duration} minutes")
            loop.run_until_complete(asyncio.sleep(duration)) 
        else:
            loop.run_forever()
    except KeyboardInterrupt:
        print("Ctrl+C detected. Exiting...")
    finally:
        pipe.set_state(Gst.State.NULL)
        print("RECORDING FINISHED")

if __name__ == "__main__":
    main()
