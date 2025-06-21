// Comprehensive fix for ndisinkcombiner freezing issue
// This fix addresses the buffer accumulation problem that causes freezing after ~2000 buffers

// The main issues found:
// 1. The combiner waits indefinitely for perfect timestamp alignment
// 2. No maximum buffer limit or timeout mechanism
// 3. Audio buffers can accumulate infinitely while waiting for video
// 4. No recovery mechanism when timestamps drift

// Key changes needed in src/ndisinkcombiner/imp.rs:

// 1. Add these fields to the State struct (around line 43):
/*
struct State {
    ...
    current_video_buffer: Option<(gst::Buffer, gst::ClockTime)>,
    current_audio_buffers: Vec<(gst::Buffer, AudioInfo, Option<gst_video::VideoTimeCode>)>,
    // ADD THESE NEW FIELDS:
    last_successful_output: Option<gst::ClockTime>,  // Track when we last output successfully
    consecutive_wait_count: u32,                      // Count how many times we've waited
    total_buffers_processed: u64,                     // Total buffers for debugging
}
*/

// 2. In the aggregate() method, add this safety check at the beginning (around line 400):
/*
fn aggregate(&self, timeout: bool) -> Result<gst::FlowSuccess, gst::FlowError> {
    let mut state = self.state.lock().unwrap();
    
    // Safety check: Force output if we've been waiting too long
    state.consecutive_wait_count += 1;
    state.total_buffers_processed += 1;
    
    // Log every 100 buffers for debugging
    if state.total_buffers_processed % 100 == 0 {
        gst::debug!(CAT, imp: self, "Processed {} buffers, wait count: {}", 
                   state.total_buffers_processed, state.consecutive_wait_count);
    }
    
    // Force output if we've waited more than 10 times in a row
    if state.consecutive_wait_count > 10 {
        gst::warning!(CAT, imp: self, "Forcing output after {} consecutive waits", state.consecutive_wait_count);
        
        // If we have a video buffer, output it even without perfect audio sync
        if let Some((video_buffer, video_time)) = state.current_video_buffer.take() {
            let output = self.create_output_buffer(&mut state, video_buffer, None);
            state.consecutive_wait_count = 0;
            state.last_successful_output = Some(video_time);
            return self.finish_buffer(output);
        }
    }
    
    // Check if we're stuck (no output for more than 1 second)
    if let Some(last_output) = state.last_successful_output {
        if let Ok(current_time) = self.obj().current_running_time() {
            if current_time.saturating_sub(last_output) > gst::ClockTime::from_seconds(1) {
                gst::warning!(CAT, imp: self, "No output for >1 second, forcing buffer");
                
                // Force output whatever we have
                if let Some((video_buffer, _)) = state.current_video_buffer.take() {
                    let output = self.create_output_buffer(&mut state, video_buffer, None);
                    state.consecutive_wait_count = 0;
                    state.last_successful_output = current_time.into();
                    return self.finish_buffer(output);
                }
            }
        }
    }
*/

// 3. In the section where audio is after video (around line 603):
/*
// If audio is after video, we can't output it yet
if let Some(audio_running_time) = audio_running_time {
    if audio_running_time > video_running_time {
        // ADD: Don't wait forever - use a reasonable threshold
        let time_diff = audio_running_time.saturating_sub(video_running_time);
        
        // If audio is more than 100ms ahead, something is wrong
        if time_diff > gst::ClockTime::from_mseconds(100) {
            gst::warning!(CAT, imp: self, 
                        "Audio {} is {}ms ahead of video {}, outputting video only",
                        audio_running_time, time_diff.mseconds(), video_running_time);
            
            // Output video without waiting for audio
            state.current_video_buffer = video_buffer_after;
            state.consecutive_wait_count = 0;
            return self.finish_buffer(output);
        }
        
        // Prevent infinite audio buffer accumulation
        if state.current_audio_buffers.len() > 30 {
            gst::warning!(CAT, imp: self, 
                        "Dropping old audio buffers, queue size: {}", 
                        state.current_audio_buffers.len());
            // Keep only the most recent 20 buffers
            state.current_audio_buffers.drain(0..10);
        }
        
        gst::trace!(
            CAT,
            imp: self,
            "Waiting for more audio, audio {} > video {}",
            audio_running_time,
            video_running_time,
        );
        state.current_video_buffer = video_buffer_after;
        return Err(gst_base::AGGREGATOR_FLOW_NEED_DATA);
    }
}
*/

// 4. After successful output (around line 659):
/*
// Update success tracking
state.consecutive_wait_count = 0;
state.last_successful_output = self.obj().current_running_time().ok();

self.finish_buffer(output)
*/

// 5. Initialize the new fields in State::default():
/*
impl Default for State {
    fn default() -> Self {
        Self {
            audio_info: None,
            video_info: None,
            current_video_buffer: None,
            current_audio_buffers: Vec::new(),
            last_successful_output: None,
            consecutive_wait_count: 0,
            total_buffers_processed: 0,
        }
    }
}
*/