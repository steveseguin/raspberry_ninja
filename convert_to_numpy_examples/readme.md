## WebRTC -> Numpy (ML/CV/AI/MJPEG)

One of the more powerful aspects of Python is Numpy; it's a powerful matrix library for data and image processing. 

Data science, machine learning, and computer vision software packages are typically built on Numpy, and it's perhaps one of the core reasons for Python's popularity. While hard core developers might prefer C++, data-scientists, researchers, and students will likely be using SciPy, Pandas, OpenCV, PyTorch, or any of the many other highly-performant toolkits available for Python instead.

Raspberry.Ninja includes in it the ability to pull webRTC streams from VDO.Ninja, and convert them into raw-uncompressed video frames, which can then be used for computer vision, machine learning, or even to simply host as a simple motion jpeg stream.

YouTube Video demo and walk-thru of this code: https://www.youtube.com/watch?v=LGaruUjb8dg)

### how to setup publish.py

To configure Raspberry.Ninja to pull a stream, you can you use the following command:
```python3 publish.py --framebuffer STREAMIDHERE123 --h264 --noaudio```

`--framebuffer` tells the code that we are viewing a remote stream, with the specified stream ID; the goal is to make the video frames available in a shared memory buffer.  Audio can be supported, but at present it's video only, so specifying `--noaudio` can conserve some bandwidth if used.  `--h264` is likely to be more compatible, however vp8 might also work.

While there are ways to modify the `publish.py` code to directly make use of the incoming compressed or decompressed video streams, `--framebuffer` chooses to push as raw video frames to a shared memory buffer, so the frames can be accessible by any other Python script running on the system.  If you wanted to share the raw video frames with another local system, I'd probably suggest pushing frames via a UDP socket or pushing to a Redis server; compressing to JPEG/PNG first would help with bandwidth.  Since we are using a shared memory buffer in this case, we will just leave the frames uncompressed and raw.  There's no need to modify the `publish.py` file this way either, so long as you intend to run your own code from another Python script locally.

### simple example; how to access the raw videos frames in your own code now

In this folder there is a basic reciever example of how to read the frames from the shared memory buffer from a small Python script. The core logic though is as follows:
```
# we assume publish.py --framebuffer is running already on the same computer
shm = shared_memory.SharedMemory(name="psm_raspininja_streamid") # open the shared memory
frame_buffer = np.ndarray(1280*720*3+5, dtype=np.uint8, buffer=shm.buf) # read from the shared memory
frame_array = np.frombuffer(frame_buffer, dtype=np.uint8) # ..

meta_header = frame_array[0:5] ## the first 5-words (10-bytes) store width, height, and frame ID
width = meta_header[0]*255+meta_header[1]
height = meta_header[2]*255+meta_header[3]
frame_array = frame_array[5:5+width*height*3].reshape((height,width,3)) # remove meta data, crop to actual image size, and re-shape 1D -> 2.5D
```
So we access the shared memory, specified with a given name set by the running publish.py script, and then we read the entire shared memory buffer. Since our current image frame might not use up the entire buffer, we include meta-header data to help us know what parts of the shared memory we want to keep or ignore. We now have our raw image data in a numpy array, ready to use however we want.

### advanced example; host numpy images as mjpeg web stream

There's a second example file also provided, which just takes the basic recieve concept to the next level. This more advanced script converts the incoming raw frame into a JPEG image, and hosts it as a motion-jpg stream on a local http webserver (`http://x.x.x.x:81`). This allows you to visualize the video frames on a headless remote system via your browser, without needing to deal with added complexities like gstreamer, ssl, webrtc, or other.  Very simple, and at 640x360 or lower resolutions, it's also extremely low-latency.  In fact, the `--framebuffer` mode, and provided code, is optimized for low-latency. The system will drop video frames if newer frames become available, keeping the latency as low as possible.

The advanced code example also includes some concepts like Events and Socket messaging also, but you can use Redis or other approach of your chosing as well. 

If looking for another advanced example of what's possible, I have another similar project from several years ago now, hosted at: (https://github.com/ooblex/ooblex)[https://github.com/ooblex/ooblex]. The project investigated applying deepfake detection to a webRTC video stream, by actually applying a deepfake TF model to an incoming webRTC stream, and then hosting the resulting deep faked live video. While that project is fairly dusty at this point, it still might offer you some fresh ideas.
