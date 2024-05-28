#!/usr/bin/env python3

import argparse
import asyncio
import sys
import signal
import logging
import traceback
from gi.repository import Gst, GLib

# Initialize GStreamer
Gst.init(None)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def handle_sigint(signal, frame, loop):
    logging.info("Ctrl+C detected. Exiting...")
    loop.stop()

def handle_unhandled_exception(loop, context):
    msg = context.get("exception", context["message"])
    logging.error(f"Caught exception: {msg}")
    loop.stop()

async def main(args):
    if args.audio_only:
        pipeline_desc = (
            'webrtcbin name=sendrecv stun-server=stun://stun4.l.google.com:19302 '
            'bundle-policy=max-bundle ! queue ! opusenc ! filesink location={output}'
        ).format(output=args.output)
    else:
        pipeline_desc = (
            'webrtcbin name=sendrecv stun-server=stun://stun4.l.google.com:19302 '
            'bundle-policy=max-bundle ! matroskamux name=mux ! queue ! filesink location={output}'
        ).format(output=args.output)

    logging.info(f'Pipeline: {pipeline_desc}')
    pipeline = Gst.parse_launch(pipeline_desc)
    pipeline.set_state(Gst.State.PLAYING)
    logging.info(f"Recording to {args.output} started")

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, handle_sigint, signal.SIGINT, None, loop)

    try:
        await asyncio.sleep(args.duration * 60)
    except asyncio.CancelledError:
        pass
    finally:
        pipeline.set_state(Gst.State.NULL)
        logging.info(f"Recording to {args.output} finished")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Record video (or audio only) from a WebRTC stream room like vdo.ninja")
    parser.add_argument('--room', type=str, required=True, help='Room name to join in vdo.ninja')
    parser.add_argument('--duration', type=int, default=1, help='Duration in minutes to record')
    parser.add_argument('--audio-only', action='store_true', help='Record audio only')
    parser.add_argument('--output', type=str, default='/tmp/record.mp4', help='Output file path')
    args = parser.parse_args()

    # Set up the global exception handler
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(handle_unhandled_exception)

    try:
        loop.run_until_complete(main(args))
    except KeyboardInterrupt:
        logging.info("Recording interrupted by user")
    finally:
        loop.close()
