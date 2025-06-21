# Fix for NDI Combiner Freezing Issue

## Problem Summary
The `ndisinkcombiner` element freezes after processing approximately 2000 buffers (~60-66 seconds at 30fps). The root cause is that the combiner waits indefinitely for perfect timestamp alignment between audio and video streams, which may never occur with WebRTC streams due to timing variations.

## Root Cause Analysis
1. **Infinite waiting**: The combiner returns `AGGREGATOR_FLOW_NEED_DATA` when audio/video timestamps don't align perfectly
2. **No timeout mechanism**: There's no maximum wait time or buffer count limit
3. **Buffer accumulation**: Audio buffers accumulate in `current_audio_buffers` vector without bounds
4. **No recovery**: Once stuck waiting for alignment, there's no mechanism to force output

## Quick Fix Instructions

### Option 1: Apply the Minimal Patch
```bash
cd gst-plugin-ndi
patch -p1 < ../ndi_combiner_minimal_fix.patch
cargo build --release
sudo cp target/release/libgstndi.so /usr/lib/x86_64-linux-gnu/gstreamer-1.0/
```

### Option 2: Manual Fix (Recommended)
Edit `src/ndisinkcombiner/imp.rs`:

1. **Add to State struct** (around line 43):
```rust
struct State {
    // ... existing fields ...
    last_successful_output: Option<gst::ClockTime>,
    consecutive_wait_count: u32,
}
```

2. **In aggregate() method**, add at the beginning:
```rust
fn aggregate(&self, timeout: bool) -> Result<gst::FlowSuccess, gst::FlowError> {
    let mut state = self.state.lock().unwrap();
    
    // Increment wait counter
    state.consecutive_wait_count += 1;
    
    // Force output if waiting too long
    if state.consecutive_wait_count > 10 {
        gst::warning!(CAT, imp: self, "Forcing output after {} waits", state.consecutive_wait_count);
        if let Some((video_buffer, _)) = state.current_video_buffer.take() {
            let output = self.create_output_buffer(&mut state, video_buffer, None);
            state.consecutive_wait_count = 0;
            return self.finish_buffer(output);
        }
    }
```

3. **Where audio is after video** (around line 603), replace the waiting logic:
```rust
if let Some(audio_running_time) = audio_running_time {
    if audio_running_time > video_running_time {
        let time_diff = audio_running_time.saturating_sub(video_running_time);
        
        // Don't wait if difference is too large
        if time_diff > gst::ClockTime::from_mseconds(100) {
            gst::warning!(CAT, imp: self, "Audio too far ahead, outputting video");
            state.current_video_buffer = video_buffer_after;
            state.consecutive_wait_count = 0;
            return self.finish_buffer(output);
        }
        
        // Prevent buffer accumulation
        if state.current_audio_buffers.len() > 30 {
            state.current_audio_buffers.drain(0..10);
        }
        
        // Continue with existing wait logic...
```

4. **After successful output**, reset the counter:
```rust
state.consecutive_wait_count = 0;
self.finish_buffer(output)
```

## Testing the Fix
```bash
# Test with simple pipeline
gst-launch-1.0 videotestsrc ! ndisinkcombiner name=c ! ndisink audiotestsrc ! c.

# Test with your WebRTC setup
python3 publish.py --room-ndi --room testroom123999999999 --password false
```

## Alternative Solutions

### 1. Use Direct NDI Sink (No Combiner)
Use the provided `webrtc_subprocess_glib_ndi_direct.py` which bypasses the combiner entirely.

### 2. Use Separate NDI Streams
Send video and audio as separate NDI streams instead of combining them.

### 3. Use a Different NDI Plugin
Consider using the obs-ndi plugin or other alternatives that don't have this issue.

## Long-term Solution
The NDI plugin maintainers should implement:
1. Configurable maximum wait time
2. Maximum buffer accumulation limits  
3. Timestamp tolerance for alignment
4. Better handling of WebRTC timing variations

## Verification
After applying the fix, the NDI stream should:
- Continue running past 2000 buffers
- Not freeze after ~60 seconds
- Handle timing mismatches gracefully
- Log warnings when forcing output