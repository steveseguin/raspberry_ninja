# WebRTC Promise Callback Fix for AsyncIO + GLib Threading

## Problem Summary

When using GStreamer's webrtcbin in a Python application with both an asyncio event loop (main thread) and a GLib main loop (separate thread), promise callbacks from WebRTC operations may never execute. This commonly manifests as:

1. `set-remote-description` promise callbacks not being called
2. Signaling state remaining `STABLE` instead of transitioning to `HAVE_REMOTE_OFFER`
3. WebRTC connections failing to establish

## Root Causes

1. **Thread Context Mismatch**: GStreamer callbacks may execute in different thread contexts than expected
2. **Promise Lifecycle**: Promises may be garbage collected before callbacks execute
3. **Data Channel Initialization**: WebRTC may not be ready to handle data-channel-only offers
4. **Main Loop Integration**: The GLib main loop may not properly dispatch callbacks when running in a separate thread

## Solutions

### Solution 1: Synchronous Promise Handling (Recommended)

The most reliable approach is to use synchronous promise handling with explicit waits:

```python
def _handle_sdp_on_main_thread(self, sdp_type, sdp_text):
    """Handle SDP on the GLib main thread using synchronous promises"""
    # Parse SDP
    res, sdp_msg = GstSdp.SDPMessage.new_from_text(sdp_text)
    if res != GstSdp.SDPResult.OK:
        self.log(f"Failed to parse SDP: result={res}", "error")
        return False
    
    if sdp_type == 'offer':
        # Create offer description
        offer = GstWebRTC.WebRTCSessionDescription.new(
            GstWebRTC.WebRTCSDPType.OFFER,
            sdp_msg
        )
        
        # Use synchronous promise - create without callback
        promise = Gst.Promise.new()
        self.webrtc.emit('set-remote-description', offer, promise)
        
        # Wait for completion
        promise.wait()
        reply = promise.get_reply()
        
        if not reply:
            self.log("Failed to set remote description", "error")
            return False
            
        # Now create answer synchronously
        answer_promise = Gst.Promise.new()
        self.webrtc.emit('create-answer', None, answer_promise)
        
        # Wait for answer
        answer_promise.wait()
        answer_reply = answer_promise.get_reply()
        
        if answer_reply:
            answer = answer_reply.get_value('answer')
            if answer:
                # Set local description
                local_promise = Gst.Promise.new()
                self.webrtc.emit('set-local-description', answer, local_promise)
                local_promise.wait()
                
                # Send answer
                answer_sdp = answer.sdp.as_text()
                self.send_answer(answer_sdp)
```

### Solution 2: Ensure Data Channel Support

For offers that only contain data channels (no audio/video), ensure WebRTC is initialized to handle them:

```python
def create_pipeline(self):
    """Create pipeline with data channel support"""
    # ... create pipeline ...
    
    # IMPORTANT: Create a data channel early to initialize SCTP transport
    # This ensures webrtcbin can handle data-channel-only offers
    channel = self.webrtc.emit('create-data-channel', 'control', None)
    if channel:
        self.log("Data channel support initialized")
```

### Solution 3: Proper Thread Context for Callbacks

If you must use async callbacks, ensure they execute in the correct thread context:

```python
def _handle_sdp_on_main_thread(self, sdp_type, sdp_text):
    """Handle SDP with callbacks that reschedule to main thread"""
    # ... parse SDP ...
    
    def on_offer_set(promise, _, __):
        # Reschedule actual work to GLib main thread
        GLib.idle_add(self._create_answer_after_offer)
        
    promise = Gst.Promise.new_with_change_func(on_offer_set, None, None)
    self.webrtc.emit('set-remote-description', offer, promise)
    
def _create_answer_after_offer(self):
    """Create answer on main thread"""
    # Now safely create answer
    answer_promise = Gst.Promise.new()
    self.webrtc.emit('create-answer', None, answer_promise)
    answer_promise.wait()
    # ... handle answer ...
```

### Solution 4: AsyncIO Integration

For clean asyncio integration, wrap WebRTC operations:

```python
class AsyncWebRTCWrapper:
    async def handle_offer(self, sdp_text: str) -> str:
        """Async method to handle offer and get answer"""
        future = asyncio.Future()
        
        def on_answer_ready(answer_sdp):
            # Complete future on asyncio loop
            asyncio.get_event_loop().call_soon_threadsafe(
                future.set_result, answer_sdp
            )
            
        # Handle offer on GLib thread
        GLib.idle_add(self._handle_offer_sync, sdp_text, on_answer_ready)
        
        # Wait for answer
        return await future
```

## Best Practices

1. **Always use `GLib.idle_add`** to schedule WebRTC operations on the GLib main thread
2. **Initialize data channel support early** if handling data-channel-only offers
3. **Use synchronous promises** for critical operations like setting descriptions
4. **Verify pipeline state** before WebRTC operations (should be PLAYING)
5. **Handle ICE candidates** only after remote description is set
6. **Log thread information** during debugging to verify execution context

## Common Pitfalls to Avoid

1. **Don't** create promises with callbacks that might execute on wrong thread
2. **Don't** assume callbacks will execute immediately
3. **Don't** forget to wait for pipeline to reach PLAYING state
4. **Don't** add ICE candidates before setting remote description

## Debugging Tips

1. Add thread logging to callbacks:
   ```python
   print(f"Callback executing on thread: {threading.current_thread().name}")
   ```

2. Check signaling state transitions:
   ```python
   state = self.webrtc.get_property('signaling-state')
   print(f"Signaling state: {state.value_name}")
   ```

3. Verify promise replies:
   ```python
   promise.wait()
   reply = promise.get_reply()
   if not reply:
       print("ERROR: Promise completed but no reply")
   ```

## Complete Working Example

See `webrtc_promise_fix_solution.py` for a complete working implementation that demonstrates all solutions.

## Testing

Run the test suite to verify the fixes work in your environment:

```bash
python test_webrtc_promise_fix.py
```

Select option 5 to run all test approaches and see which work best for your setup.