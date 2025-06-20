# NDI Subprocess Implementation Issues and Fixes

## Issues Found:

1. **Missing NDI Parameters**: The `WebRTCSubprocessManager` in `publish.py` was not passing `room_ndi` and `ndi_name` parameters to the subprocess. This has been fixed.

2. **Incomplete NDI Implementation**: The current NDI implementation in `webrtc_subprocess_glib.py` has several issues:
   - Audio is just sent to fakesink when NDI mode is enabled
   - No proper audio/video synchronization for NDI output
   - NDI sink is created only for video, not for combined audio/video

3. **Variable Reference Error**: The code references `filename` variable when storing recording info, but this variable doesn't exist in the NDI branch.

## Fixes Applied:

1. ✅ Added `room_ndi` and `ndi_name` parameters to the subprocess configuration in `publish.py` (lines 1414-1415)

2. ✅ Fixed the undefined `filename` variable issue in `webrtc_subprocess_glib.py` (lines 767-773)

## Remaining Issues:

The NDI implementation needs to be redesigned to properly handle audio and video together. Currently:
- Video goes to NDI sink
- Audio goes to fakesink (discarded)

For proper NDI output, we need:
- Use `ndisinkcombiner` to mux audio and video
- Connect both audio and video streams to the combiner
- Single NDI sink output with synchronized A/V

## Recommended Next Steps:

1. Redesign the NDI pipeline in the subprocess to use:
   ```
   video_queue -> depay -> decode -> videoconvert -> ndisinkcombiner.video
   audio_queue -> depay -> decode -> audioconvert -> ndisinkcombiner.audio
                                                     ndisinkcombiner -> ndisink
   ```

2. Store references to NDI elements per stream for proper cleanup

3. Test with actual NDI viewers to ensure streams are visible and synchronized

## Test Commands:

To test the NDI functionality:
```bash
# Publisher 1
python3 publish.py --test --room testroom123999999999 --streamid tUur6fffwt --h264

# Publisher 2  
python3 publish.py --test --room testroom123999999999 --streamid tUur6wt --h264

# Room NDI relay (in another terminal)
python3 publish.py --room testroom123999999999 --room-ndi --password false
```

Then use an NDI viewer (like NDI Studio Monitor) to check if the streams appear as:
- `testroom123999999999_tUur6fffwt`
- `testroom123999999999_tUur6wt`