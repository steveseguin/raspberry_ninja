import threading
import time
import ssl
import sys
import os
try:
    import cv2 ## PIL or CV2 can be used
except:
    print("OpenCV wasn't found. Trying to use Pillow instead")
    from PIL import Image
    from io import BytesIO
from socketserver import ThreadingMixIn
from http.server import BaseHTTPRequestHandler, HTTPServer
import socket
import multiprocessing
import numpy as np
import time
from multiprocessing import shared_memory, Lock
from multiprocessing.resource_tracker import unregister
from threading import Event

global last_frame, jpeg,promise
promise = Event()

def read_shared_memory():
    global last_frame, jpeg, promise

    try:
        shm = False
        trigger_socket = False
        trigger_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        trigger_socket.bind(("127.0.0.1", 12345))

        shm_name = "psm_raspininja_streamid"
        shm = shared_memory.SharedMemory(name=shm_name)
        frame_buffer = np.ndarray(1280*720*3+5, dtype=np.uint8, buffer=shm.buf)
        unregister(shm._name, 'shared_memory') # https://forums.raspberrypi.com/viewtopic.php?t=340441#p2039792
        last_frame = -1
        frame = 0
        failed = 0

        prev_array = False

        while True:
            trigger_signal = trigger_socket.recv(1024) # wait for some alert that the shared memory was updated
            frame_data = frame_buffer.copy()  # Make a copy to avoid modifying the shared memory
            frame_array = np.frombuffer(frame_data, dtype=np.uint8)
            meta_header = frame_array[0:5]
            frame = meta_header[4]
            if frame == last_frame:
                failed = failed + 1
                if failed > 5:
                    print("this is unexpected; let's reconnect")
                    break
            failed = 0
            width = meta_header[0]*255+meta_header[1]
            if width==0:
                print("image size is 0. will retry")
                time.sleep(1)
                continue
            height = meta_header[2]*255+meta_header[3]
            
            frame_array = frame_array[5:5+width*height*3].reshape((height,width,3))

#            if type(prev_array) == type(False):
 #               prev_array = frame_array
  #              modded_array = frame_array
   #         if np.shape(frame_array) == np.shape(prev_array):
    #            modded_array = frame_array%128+128 - prev_array%128
     #           prev_array = frame_array

            try: # Try OpenCV
                _, jpeg = cv2.imencode('.jpeg', frame_array)
            except: # Try Pillow if CV2 isnt' there
                with BytesIO() as f:
                    im = Image.fromarray(frame_array[:, :, ::-1]) # Convert from  numpy/cv2 BGR to pillow RGB (OpenCV to PIL format)
                    im.save(f, format='JPEG')
                    jpeg = f.getvalue()

            last_frame = frame
            if not promise.is_set(): # let any waiting thread know we are done
                promise.set()
            print(np.shape(frame_array),frame, frame_array[0, 0, :])
    except Exception as E:
        print(E)
    finally:
        if shm:
            shm.close()
        if trigger_socket:
            trigger_socket.close()
        return True


class myHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global jpeg, last_frame, promise
        print("Web connect")

        try:
            videotype = self.path.split(".")[1].split("?")[0]
        except:
            videotype = "html"

        if videotype == 'mjpg':
            self.send_response(200)
            self.send_header('Content-type','multipart/x-mixed-replace; boundary=--jpgboundary')
            self.end_headers()
            sent_frame = -1
            while True:
                try:
                    
                    while last_frame == sent_frame: # if we have multiple viewers, can see if already done this way
                        if not promise.is_set():
                            promise.wait(25) # under 30s, incase there's a timeout on some CDN?
                        else:
                            promise.clear # just in case last-frame == sent-frame is incorrect, we won't get stuck this way.

                    sent_frame = last_frame

                    self.wfile.write("--jpgboundary".encode('utf-8'))
                    self.send_header('Content-type','image/jpeg')
                    self.send_header('Content-length',str(len(jpeg)))
                    self.end_headers()
                    self.wfile.write(jpeg)

                    # promise.clear() # we 
                except KeyboardInterrupt:
                    break
            return
        else:
            self.send_response(200)
            self.send_header('Content-type','text/html')
            self.end_headers()
            self.wfile.write('<html><head></head><body>'.encode('utf-8'))
            self.wfile.write(('<img src="vdoninja.mjpg" width=640 height=360 />').encode('utf-8'))
            self.wfile.write('</body></html>'.encode('utf-8'))
            return

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
        """Handle requests in a separate thread."""
        pass

def remote_threader():
    remote_Server = ThreadedHTTPServer(("", 81), myHandler)
    #remote_Server.socket = ssl.wrap_socket(remote_Server.socket, keyfile=key_pem, certfile=chain_pem, server_side=True) ## if you need SSL, you can use certbot to get free valid keys
    remote_Server.serve_forever()
    print("webserver ending")

if __name__ == "__main__":
    remote_http_thread = threading.Thread(target=remote_threader)
    remote_http_thread.start()
    while read_shared_memory():
        print("reloading in a second")
        time.sleep(1)
    print("processing server ending")

