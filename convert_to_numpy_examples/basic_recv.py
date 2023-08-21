import multiprocessing
import numpy as np
import time
from multiprocessing import shared_memory, Lock
from multiprocessing.resource_tracker import unregister

def receiver_process(shm_name):
    shm = shared_memory.SharedMemory(name=shm_name)
    frame_buffer = np.ndarray(1280*720*3+5, dtype=np.uint8, buffer=shm.buf)
    unregister(shm._name, 'shared_memory') # https://forums.raspberrypi.com/viewtopic.php?t=340441#p2039792
    last_frame = -1
    #lock = Lock()
    try:
        while True:
            #lock.acquire()
            frame_data = frame_buffer.copy()  # Make a copy to avoid modifying the shared memory
            #lock.release()
            frame_array = np.frombuffer(frame_data, dtype=np.uint8)
            meta_header = frame_array[0:5]
    
            frame = meta_header[4]
            if frame == last_frame:
                continue
    
            width = meta_header[0]*255+meta_header[1]
            if width==0:
                print("image size is 0. will retry")
                time.sleep(1)
                continue
            height = meta_header[2]*255+meta_header[3]
            last_frame = frame

            frame_array = frame_array[5:5+width*height*3].reshape((height,width,3))
            print(np.shape(frame_array),frame, frame_array[0, 0, :])

            time.sleep(1/60)
    finally:
        shm.close()

if __name__ == "__main__":
    shm_name = "psm_raspininja_streamid"
    
    receiver = multiprocessing.Process(target=receiver_process, args=(shm_name,))
    receiver.start()
    receiver.join()
