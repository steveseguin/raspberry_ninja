#!/usr/bin/env python3
"""Check streams in VDO.Ninja room via browser"""

print("""
To check the streams in the room:

1. Open a web browser
2. Go to: https://vdo.ninja/?room=testroom123999999999&password=false&view
3. This will show all active streams in the room

Current known streams:
- tUur6wt
- tUur6fffwt

If these streams show video/audio in the browser but not in the recording,
then there's an issue with the WebRTC negotiation in the recorder.

You can also check a specific stream:
https://vdo.ninja/?room=testroom123999999999&password=false&view=tUur6wt

To publish a test stream from browser:
https://vdo.ninja/?room=testroom123999999999&password=false&push=browserteststream
""")