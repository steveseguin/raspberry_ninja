import random
import ssl
import websockets
import asyncio
import os
import sys
import json
import argparse
import time
import gi
import threading
import socket
import re
import traceback
import subprocess
import struct
try:
    import hashlib
    from urllib.parse import urlparse
except Exception as e:
    pass

try:
    import numpy as np
    import multiprocessing
    from multiprocessing import shared_memory
except Exception as e:
    pass
    
try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes, padding
    from cryptography.hazmat.backends import default_backend
except ImportError as e:
    raise ImportError("Run `pip install cryptography` to install the dependencies needed for passwords") from e

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject
gi.require_version('GstWebRTC', '1.0')
from gi.repository import GstWebRTC
gi.require_version('GstSdp', '1.0')
from gi.repository import GstSdp

try:
    from gi.repository import GLib
except:
    pass
    
#os.environ['GST_DEBUG'] = '3,ndisink:7,videorate:5,videoscale:5,videoconvert:5'

def generate_unique_ndi_name(base_name):
    return f"{base_name}_{int(time.time())}"
    
def handle_unhandled_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    print("!!! Unhandled exception !!!")
    print("Type:", exc_type)
    print("Value:", exc_value)
    print("Traceback:", ''.join(traceback.format_tb(exc_traceback)))

    tb = traceback.extract_tb(exc_traceback)
    for frame in tb:
        print(f"File \"{frame.filename}\", line {frame.lineno}, in {frame.name}")
sys.excepthook = handle_unhandled_exception


def get_exception_info(E):
    tb = traceback.extract_tb(E.__traceback__)
    error_line = tb[-1].lineno
    error_file = tb[-1].filename
    
    if len(tb) >= 2:
        caller = tb[-2]
        caller_line = caller.lineno
        caller_file = caller.filename
    else:
        caller_line = "unknown"
        caller_file = "unknown"
    
    return (
        f"{type(E).__name__} at line {error_line} in {error_file}: {E}\n"
        f"Called from line {caller_line} in {caller_file}"
    )

    
def enableLEDs(level=False):
    try:
        GPIO
    except Exception as e:
        return
    global LED_Level, P_R
    if level!=False:
        LED_Level = level
    p_R.start(0)      # Initial duty Cycle = 0(leds off)
    p_R.ChangeDutyCycle(LED_Level)     # Change duty cycle

def disableLEDs():
    try:
        GPIO
    except Exception as e:
        return

    global pin, P_R
    p_R.stop()
    GPIO.output(pin, GPIO.HIGH)    # Turn off all leds
    GPIO.cleanup()

def hex_to_ansi(hex_color):
    hex_color = hex_color.lstrip('#')

    if len(hex_color)==6:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
    elif len(hex_color)==3:
        r = int(hex_color[0:1]+hex_color[0:1], 16)
        g = int(hex_color[1:2]+hex_color[1:2], 16)
        b = int(hex_color[2:3]+hex_color[2:3], 16)
    else:
        return hex_color

    ansi_color = 16 + (36 * int(r / 255 * 5)) + (6 * int(g / 255 * 5)) + int(b / 255 * 5)

    return f"\033[38;5;{ansi_color}m"

def printc(message, color_code=None):
    reset_color = "\033[0m"

    if color_code is not None:
        color_code = hex_to_ansi(color_code)
        colored_message = f"{color_code}{message}{reset_color}"
        print(colored_message)
    else:
        print(message)

def printwin(message):
    printc("<= "+message,"93F")
def printwout(message):
    printc("=> "+message,"9F3")
def printin(message):
    printc("<= "+message,"F6A")
def printout(message):
    printc("=> "+message,"6F6")
def printwarn(message):
    printc(message,"FF0")
def check_drm_displays():
    try:
        result = subprocess.run(['drm_info'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            output = result.stdout.strip()
            drm_info = json.loads(output)
            connected_displays = [connector for connector in drm_info['connectors'] if connector['status'] == 'connected']
            if connected_displays:
                print("Display(s) connected:")
                for display in connected_displays:
                    print(display)
                return True
            else:
                print("No display connected.")
                return False
        else:
            print(f"Error running drm_info: {result.stderr}")
            return False
    except Exception as e:
        print(f"Exception occurred: {e}")
        return False

def replace_ssrc_and_cleanup_sdp(sdp): ## fix for audio-only gstreamer -> chrome
    def generate_ssrc():
        return str(random.randint(0, 0xFFFFFFFF))

    lines = sdp.split('\r\n')

    in_audio_section = False
    new_ssrc = generate_ssrc()

    for i in range(len(lines)):
        if lines[i].startswith('m=audio '):
            in_audio_section = True
        elif lines[i].startswith('m=') and not lines[i].startswith('m=audio '):
            in_audio_section = False
        if in_audio_section and lines[i].startswith('a=ssrc:'):
            lines[i] = re.sub(r'a=ssrc:\d+', f'a=ssrc:{new_ssrc}', lines[i])

    return '\r\n'.join(lines)

def generateHash(input_str, length=None):
    input_bytes = input_str.encode('utf-8')
    sha256_hash = hashlib.sha256(input_bytes).digest()
    if length:
        hash_hex = sha256_hash[:int(length // 2)].hex()
    else:
        hash_hex = sha256_hash.hex()
    return hash_hex

def convert_string_to_bytes(input_str):
    return input_str.encode('utf-8')

def to_hex_string(byte_data):
    return ''.join(f'{b:02x}' for b in byte_data)

def to_byte_array(hex_str):
    return bytes.fromhex(hex_str)

def generate_key(phrase):
    return hashlib.sha256(phrase.encode()).digest()

def pad_message(message):
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded_data = padder.update(message.encode('utf-8')) + padder.finalize()
    return padded_data

def unpad_message(padded_message):
    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    try:
        data = unpadder.update(padded_message) + unpadder.finalize()
        return data
    except ValueError as e:
        print(f"Padding error: {e}")
        return None

def encrypt_message(message, phrase):
    try:
        message = json.dumps(message)
    except Exception as E:
        printwarn(get_exception_info(E))

    key = generate_key(phrase)
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    padded_message = pad_message(message)
    encrypted_message = encryptor.update(padded_message) + encryptor.finalize()
    return to_hex_string(encrypted_message), to_hex_string(iv)

def decrypt_message(encrypted_data, iv, phrase):
    key = generate_key(phrase)
    encrypted_data_bytes = to_byte_array(encrypted_data)
    iv_bytes = to_byte_array(iv)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv_bytes), backend=default_backend())
    decryptor = cipher.decryptor()
    try:
        decrypted_padded_message = decryptor.update(encrypted_data_bytes) + decryptor.finalize()
        unpadded_message = unpad_message(decrypted_padded_message)
        if unpadded_message is not None:
            return unpadded_message.decode('utf-8')
        else:
            return None
    except (UnicodeDecodeError, ValueError) as e:
        print(f"Error decoding message: {e}")
        return None

                    
class WebRTCClient:
    def __init__(self, params):

        self.pipeline = params.pipeline
        self.conn = None
        self.pipe = None
        self.h264 = params.h264
        self.vp8 = params.vp8
        self.pipein = params.pipein
        self.bitrate = params.bitrate
        self.max_bitrate = params.bitrate
        self.server = params.server
        self.stream_id = params.streamid
        self.view = params.view
        self.room_name = params.room
        self.room_hashcode = None
        self.multiviewer = params.multiviewer
        self.record = params.record
        self.streamin = params.streamin
        self.ndiout = params.ndiout
        self.fdsink = params.fdsink
        self.filesink = None
        self.framebuffer = params.framebuffer
        self.midi = params.midi
        self.nored = params.nored
        self.noqos = params.noqos
        self.midi_thread = None
        self.midiout = None
        self.midiout_ports = None
        self.puuid = params.puuid
        self.clients = {}
        self.rotate = int(params.rotate)
        self.save_file = params.save
        self.noaudio = params.noaudio
        self.novideo = params.novideo
        self.counter = 0
        self.shared_memory = False
        self.trigger_socket = False
        self.processing = False
        self.buffer = params.buffer
        self.password = params.password
        self.hostname = params.hostname
        self.hashcode = ""
        self.salt = ""
        self.aom = params.aom
        self.av1 = params.av1
        self.socketout = params.socketout
        self.socketport = params.socketport
        self.socket = None
        
        try:
            if self.password:
                parsed_url = urlparse(self.hostname)
                hostname_parts = parsed_url.hostname.split(".")
                self.salt = ".".join(hostname_parts[-2:])
                self.hashcode = generateHash(self.password+self.salt, 6)

                if self.room_name:
                    self.room_hashcode = generateHash(self.room_name+self.password+self.salt, 16)
        except Exception as E:
            printwarn(get_exception_info(E))

            
        if self.save_file:
            self.pipe = Gst.parse_launch(self.pipeline)
            self.setup_ice_servers(self.pipe.get_by_name('sendrecv'))
            self.pipe.set_state(Gst.State.PLAYING)
            print("RECORDING TO DISK STARTED")
            
    def setup_ice_servers(self, webrtc):
        try:
            if hasattr(self, 'stun_server') and self.stun_server:
                webrtc.set_property('stun-server', self.stun_server)
            elif not hasattr(self, 'no_stun') or not self.no_stun:
                for server in ["stun://stun.cloudflare.com:3478", "stun://stun.l.google.com:19302"]:
                    webrtc.set_property('stun-server', server)
                    
            if hasattr(self, 'turn_server') and self.turn_server:
                webrtc.set_property('turn-server', self.turn_server)
                
            if hasattr(self, 'ice_transport_policy') and self.ice_transport_policy:
                webrtc.set_property('ice-transport-policy', self.ice_transport_policy)
                
        except Exception as E:
            printwarn(get_exception_info(E))

    async def connect(self):
        print("Connecting to handshake server")
        
        # Convert wss:// to ws:// for no-SSL attempt
        ws_server = self.server.replace('wss://', 'ws://') if self.server.startswith('wss://') else self.server
        
        connection_attempts = [
            (lambda: ssl.create_default_context(), "standard SSL", self.server),
            (lambda: ssl._create_unverified_context(), "unverified SSL", self.server),
            (lambda: None, "no SSL", ws_server)  # Use ws:// URL for no-SSL
        ]
        
        last_exception = None
        for create_ssl_context, context_type, server_url in connection_attempts:
            try:
                print(f"Attempting connection with {context_type} to {server_url}")
                ssl_context = create_ssl_context()
                if ssl_context:
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
                
                self.conn = await websockets.connect(
                    server_url,
                    ssl=ssl_context,
                    ping_interval=None
                )
                print(f"Connected successfully using {context_type}")
                break
            except Exception as e:
                last_exception = e
                print(f"Failed {context_type} connection: {str(e)}")
                continue
        
        if not self.conn:
            raise ConnectionError(f"Failed to connect with all SSL options. Last error: {last_exception}")

        if self.room_hashcode:
            if self.streamin:
                await self.sendMessageAsync({"request":"joinroom","roomid":self.room_hashcode})
            else:
                await self.sendMessageAsync({"request":"joinroom","roomid":self.room_hashcode,"streamID":self.stream_id+self.hashcode})
            printwout("joining room (hashed)")
        elif self.room_name:
            if self.streamin:
                await self.sendMessageAsync({"request":"joinroom","roomid":self.room_name})
            else:
                await self.sendMessageAsync({"request":"joinroom","roomid":self.room_name,"streamID":self.stream_id+self.hashcode})
            printwout("joining room")
        elif self.streamin:
            await self.sendMessageAsync({"request":"play","streamID":self.streamin+self.hashcode})
            printwout("requesting stream")
        else:
            await self.sendMessageAsync({"request":"seed","streamID":self.stream_id+self.hashcode})
            printwout("seed start")

    def sendMessage(self, msg): # send message to wss
        if self.puuid:
            msg['from'] = self.puuid

        client = None
        if "UUID" in msg and msg['UUID'] in self.clients:
            client = self.clients[msg['UUID']]

        if client and client['send_channel']:
            try:
                msgJSON = json.dumps(msg)
                client['send_channel'].emit('send-string', msgJSON)
                printout("a message was sent via datachannels: "+msgJSON[:60])
            except Exception as e:
                try:
                    if self.password:
                        #printc("Password","0F3")
                        if "candidate" in msg:
                            msg['candidate'], msg['vector'] = encrypt_message(msg['candidate'], self.password+self.salt)
                        if "candidates" in msg:
                            msg['candidates'], msg['vector'] = encrypt_message(msg['candidates'], self.password+self.salt)
                        if "description" in msg:
                            msg['description'], msg['vector'] = encrypt_message(msg['description'], self.password+self.salt)
                
                    msgJSON = json.dumps(msg)
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(self.conn.send(msgJSON))
                    printwout("a message was sent via websockets 2: "+msgJSON[:60])
                except Exception as e:
                    printc(e,"F00")
        else:
            try:
                if self.password:
                   # printc("Password","0F3")
                    if "candidate" in msg:
                        msg['candidate'], msg['vector'] = encrypt_message(msg['candidate'], self.password+self.salt)
                    if "candidates" in msg:
                        msg['candidates'], msg['vector'] = encrypt_message(msg['candidates'], self.password+self.salt)
                    if "description" in msg:
                        msg['description'], msg['vector'] = encrypt_message(msg['description'], self.password+self.salt)
                
                msgJSON = json.dumps(msg)
                loop = asyncio.new_event_loop()        
                loop.run_until_complete(self.conn.send(msgJSON))
                printwout("a message was sent via websockets 1: "+msgJSON[:60])
            except Exception as e:
                printc(e,"F01")
                
                
    async def sendMessageAsync(self, msg): # send message to wss
        if self.puuid:
            msg['from'] = self.puuid

        client = None
        if "UUID" in msg and msg['UUID'] in self.clients:
            client = self.clients[msg['UUID']]

        if client and client['send_channel']:
            try:
                msgJSON = json.dumps(msg)
                client['send_channel'].emit('send-string', msgJSON)
                printout("a message was sent via datachannels: "+msgJSON[:60])
            except Exception as e:
                try:
                    if self.password:
                        if "candidate" in msg:
                            msg['candidate'], msg['vector'] = encrypt_message(msg['candidate'], self.password+self.salt)
                        if "candidates" in msg:
                            msg['candidates'], msg['vector'] = encrypt_message(msg['candidates'], self.password+self.salt)
                        if "description" in msg:
                            msg['description'], msg['vector'] = encrypt_message(msg['description'], self.password+self.salt)
                            
                    msgJSON = json.dumps(msg)
                    await self.conn.send(msgJSON)
                    printwout("a message was sent via websockets 2: "+msgJSON[:60])
                except Exception as E:
                    printwarn(get_exception_info(E))

        else:
            try:
                if self.password:
                    if "candidate" in msg:
                        msg['candidate'], msg['vector'] = encrypt_message(msg['candidate'], self.password+self.salt)
                    if "candidates" in msg:
                        msg['candidates'], msg['vector'] = encrypt_message(msg['candidates'], self.password+self.salt)
                    if "description" in msg:
                        msg['description'], msg['vector'] = encrypt_message(msg['description'], self.password+self.salt)
                        
                msgJSON = json.dumps(msg)
                await self.conn.send(msgJSON)
                printwout("a message was sent via websockets 1: "+msgJSON[:60])
            except Exception as e:
                printwarn(get_exception_info(E))

    def setup_socket(self):
        import socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('0.0.0.0', int(self.socketport)))
        
    def on_new_socket_sample(self, sink):
        sample = sink.emit("pull-sample")
        if sample:
            buffer = sample.get_buffer()
            caps = sample.get_caps()
            height = caps.get_structure(0).get_value("height")
            width = caps.get_structure(0).get_value("width")
            
            _, map_info = buffer.map(Gst.MapFlags.READ)
            frame_data = map_info.data
            
            # Send frame size
            self.socket.sendto(struct.pack('!III', width, height, len(frame_data)), ('127.0.0.1', int(self.socketport)))
            print("Sending")
            # Send frame data in chunks
            chunk_size = 65507  # Maximum safe UDP packet size
            for i in range(0, len(frame_data), chunk_size):
                chunk = frame_data[i:i+chunk_size]
                self.socket.sendto(chunk, ('127.0.0.1', int(self.socketport)))
            
            buffer.unmap(map_info)
        return Gst.FlowReturn.OK
    
    def new_sample(self, sink):
        if self.processing:
            return False
        self.processing = True
        try :
            sample = sink.emit("pull-sample")
            if sample:
                buffer = sample.get_buffer()
                caps = sample.get_caps()
                height = int(caps.get_structure(0).get_int("height").value)
                width = int(caps.get_structure(0).get_int("width").value)
                frame_data = buffer.extract_dup(0, buffer.get_size())
                np_frame_data = np.frombuffer(frame_data, dtype=np.uint8).reshape(height, width, 3)
                print(np.shape(np_frame_data), np_frame_data[0,0,:])

                frame_shape = (720 * 1280 * 3)
                frame_buffer = np.ndarray(frame_shape+5, dtype=np.uint8, buffer=self.shared_memory.buf)
                frame_buffer[5:5+width*height*3] = np_frame_data.flatten(order='K') # K means order as how ordered in memory
                frame_buffer[0] = width/255
                frame_buffer[1] = width%255
                frame_buffer[2] = height/255
                frame_buffer[3] = height%255
                frame_buffer[4] = self.counter%255
                self.counter+=1
                self.trigger_socket.sendto(b"update", ("127.0.0.1", 12345))

        except Exception as E:
            printwarn(get_exception_info(E))

        self.processing = False
        return False    
   
    def on_incoming_stream(self, _, pad):
        try:
            if Gst.PadDirection.SRC != pad.direction:
                print("pad direction wrong?")
                return
            caps = pad.get_current_caps()
            name = caps.to_string()
            print(f"Incoming stream caps: {name}")
            if self.ndiout:
                print("NDI OUT")
                ndi_combiner = self.pipe.get_by_name("ndi_combiner")
                ndi_sink = self.pipe.get_by_name("ndi_sink")
                
                if not ndi_combiner:
                    print("Creating new NDI sink combiner")
                    ndi_combiner = Gst.ElementFactory.make("ndisinkcombiner", "ndi_combiner")
                    if not ndi_combiner:
                        print("Failed to create ndisinkcombiner element")
                        return
                    
                    # Set properties
                    ndi_combiner.set_property("latency", 800_000_000)  # 800ms
                    ndi_combiner.set_property("min-upstream-latency", 1_000_000_000)  # 1000ms
                    ndi_combiner.set_property("start-time-selection", 1)  # 1 corresponds to "first"

                    self.pipe.add(ndi_combiner)
                    ndi_combiner.sync_state_with_parent()
                    
                    ret = ndi_combiner.set_state(Gst.State.PLAYING)
                    if ret == Gst.StateChangeReturn.FAILURE:
                        print("Failed to set ndi_combiner to PLAYING state")
                        return
                
                    if not ndi_sink:
                        print("Creating new NDI sink")
                        ndi_sink = Gst.ElementFactory.make("ndisink", "ndi_sink")
                        if not ndi_sink:
                            print("Failed to create ndisink element")
                            return
                        unique_ndi_name = generate_unique_ndi_name(self.ndiout)
                        ndi_sink.set_property("ndi-name", unique_ndi_name)
                        self.pipe.add(ndi_sink)
                        ndi_sink.sync_state_with_parent()
                        print(f"NDI sink name: {ndi_sink.get_property('ndi-name')}")
                    
                    # Link ndi_combiner to ndi_sink
                    if not ndi_combiner.link(ndi_sink):
                        print("Failed to link ndi_combiner to ndi_sink")
                        return

                if "video" in name:
                    print("NDI VIDEO OUT")
                    pad_name = "video"
                    rtp_caps_string = "application/x-rtp,media=(string)video,clock-rate=(int)90000,encoding-name=(string)H264"
                elif "audio" in name:
                    print("NDI AUDIO OUT")
                    pad_name = "audio"
                    rtp_caps_string = "application/x-rtp,media=(string)audio,clock-rate=(int)48000,encoding-name=(string)OPUS"
                else:
                    print("Unsupported media type:", name)
                    return

                # Check if the pad already exists
                target_pad = ndi_combiner.get_static_pad(pad_name)
                if target_pad:
                    print(f"{pad_name.capitalize()} pad already exists, using existing pad")
                else:
                    target_pad = ndi_combiner.request_pad(ndi_combiner.get_pad_template(pad_name), None, None)
                    if target_pad is None:
                        print(f"Failed to get {pad_name} pad from ndi_combiner")
                        print("Available pad templates:")
                        for template in ndi_combiner.get_pad_template_list():
                            print(f"  {template.name_template}: {template.direction.value_name}")
                        print("Current pads:")
                        for pad in ndi_combiner.pads:
                            print(f"  {pad.get_name()}: {pad.get_direction().value_name}")
                        return

                print(f"Got {pad_name} pad: {target_pad.get_name()}")

                # Create elements based on media type
                if pad_name == "video":
                    elements = [
                        Gst.ElementFactory.make("capsfilter", f"{pad_name}_rtp_caps"),
                        Gst.ElementFactory.make("queue", f"{pad_name}_queue"),
                        Gst.ElementFactory.make("rtph264depay", "h264_depay"),
                        Gst.ElementFactory.make("h264parse", "h264_parse"),
                        Gst.ElementFactory.make("avdec_h264", "h264_decode"),
                        Gst.ElementFactory.make("videoconvert", "video_convert"),
                        Gst.ElementFactory.make("videoscale", "video_scale"),
                        Gst.ElementFactory.make("videorate", "video_rate"),
                        Gst.ElementFactory.make("capsfilter", "video_caps"),
                    ]
                    elements[0].set_property("caps", Gst.Caps.from_string(rtp_caps_string))
                    elements[-1].set_property("caps", Gst.Caps.from_string("video/x-raw,format=UYVY,width=1280,height=720,framerate=30/1"))
                else:  # audio
                    elements = [
                        Gst.ElementFactory.make("capsfilter", f"{pad_name}_rtp_caps"),
                        Gst.ElementFactory.make("queue", f"{pad_name}_queue"),
                        Gst.ElementFactory.make("rtpopusdepay", "opus_depay"),
                        Gst.ElementFactory.make("opusdec", "opus_decode"),
                        Gst.ElementFactory.make("audioconvert", "audio_convert"),
                        Gst.ElementFactory.make("audioresample", "audio_resample"),
                        Gst.ElementFactory.make("capsfilter", "audio_caps"),
                    ]
                    elements[0].set_property("caps", Gst.Caps.from_string(rtp_caps_string))
                    elements[-1].set_property("caps", Gst.Caps.from_string("audio/x-raw,format=F32LE,channels=2,rate=48000,layout=interleaved"))

                if not all(elements):
                    print("Couldn't create all elements")
                    return

                # Create a bin for the elements
                bin_name = f"{pad_name}_bin"
                element_bin = Gst.Bin.new(bin_name)
                for element in elements:
                    element_bin.add(element)

                # Link elements within the bin
                for i in range(len(elements) - 1):
                    if not elements[i].link(elements[i+1]):
                        print(f"Failed to link {elements[i].get_name()} to {elements[i+1].get_name()}")
                        return

                # Add ghost pads to the bin
                sink_pad = elements[0].get_static_pad("sink")
                ghost_sink = Gst.GhostPad.new("sink", sink_pad)
                element_bin.add_pad(ghost_sink)

                src_pad = elements[-1].get_static_pad("src")
                ghost_src = Gst.GhostPad.new("src", src_pad)
                element_bin.add_pad(ghost_src)

                # Add the bin to the pipeline
                self.pipe.add(element_bin)
                element_bin.sync_state_with_parent()

                # Link the bin to the ndi_combiner
                if not element_bin.link_pads("src", ndi_combiner, target_pad.get_name()):
                    print(f"Failed to link {bin_name} to ndi_combiner:{target_pad.get_name()}")
                    print(f"Bin src caps: {ghost_src.query_caps().to_string()}")
                    print(f"Target pad caps: {target_pad.query_caps().to_string()}")
                    return

                # Link the incoming pad to the bin
                if not pad.link(ghost_sink):
                    print(f"Failed to link incoming pad to {bin_name}")
                    print(f"Incoming pad caps: {pad.query_caps().to_string()}")
                    print(f"Ghost sink pad caps: {ghost_sink.query_caps().to_string()}")
                    return

                print(f"NDI {pad_name} pipeline set up successfully")

                # Set the bin to PLAYING state
                ret = element_bin.set_state(Gst.State.PLAYING)
                if ret == Gst.StateChangeReturn.FAILURE:
                    print(f"Failed to set {bin_name} to PLAYING state")
                    return

                print(f"All elements in {bin_name} set to PLAYING state")

            elif "video" in name:
                if self.novideo:
                    printc('Ignoring incoming video track', "F88")
                    out = Gst.parse_bin_from_description("queue ! fakesink", True)
                    
                    self.pipe.add(out)
                    out.sync_state_with_parent()
                    sink = out.get_static_pad('sink')
                    pad.link(sink)
                    return

                if self.ndiout:
                   # I'm handling this on elsewhere now
                   pass
                elif self.socketout:
                    print("SOCKET VIDEO OUT")
                    out = Gst.parse_bin_from_description(
                        "queue ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! video/x-raw,format=BGR ! appsink name=appsink emit-signals=true", True)
                    self.pipe.add(out)
                    out.sync_state_with_parent()
                    sink = out.get_static_pad('sink')
                    pad.link(sink)
                    
                    appsink = self.pipe.get_by_name('appsink')
                    appsink.connect("new-sample", self.on_new_socket_sample)
                elif self.view:
                    print("DISPLAY OUTPUT MODE BEING SETUP")
                    
                    outsink = "autovideosink"
                    if check_drm_displays():
                        printc('\nThere is at least one connected display.',"00F")
                    else:
                        printc('\n ! No connected displays found. Will try to use glimagesink instead of autovideosink',"F60")
                        outsink = "glimagesink sync=true"
                    
                    if "VP8" in name:
                        out = Gst.parse_bin_from_description(
                            "queue ! rtpvp8depay ! decodebin ! queue max-size-buffers=0 max-size-time=0 ! videoconvert ! video/x-raw,format=RGB ! queue max-size-buffers=0 max-size-time=0 ! "+outsink, True)
                    elif "H264" in name:
                        out = Gst.parse_bin_from_description(
                            "queue ! rtph264depay ! h264parse ! openh264dec ! queue max-size-buffers=0 max-size-time=0 ! videoconvert ! video/x-raw,format=RGB ! queue max-size-buffers=0 max-size-time=0 ! "+outsink, True)
                        
                    self.pipe.add(out)
                    out.sync_state_with_parent()
                    sink = out.get_static_pad('sink')
                    pad.link(sink)      
                    
                elif self.fdsink:
                    print("FD SINK OUT")
                    queue = Gst.ElementFactory.make("queue", "fd_queue")
                    depay = None
                    parse = None
                    decode = None
                    convert = Gst.ElementFactory.make("videoconvert", "fd_convert")
                    scale = Gst.ElementFactory.make("videoscale", "fd_scale")
                    caps_filter = Gst.ElementFactory.make("capsfilter", "fd_caps")
                    sink = Gst.ElementFactory.make("fdsink", "fd_sink")

                    if "VP8" in name:
                        depay = Gst.ElementFactory.make("rtpvp8depay", "vp8_depay")
                        decode = Gst.ElementFactory.make("vp8dec", "vp8_decode")
                    elif "H264" in name:
                        depay = Gst.ElementFactory.make("rtph264depay", "h264_depay")
                        parse = Gst.ElementFactory.make("h264parse", "h264_parse")
                        decode = Gst.ElementFactory.make("avdec_h264", "h264_decode")
                    else:
                        print("Unsupported video codec:", name)
                        return

                    if not all([queue, depay, decode, convert, scale, caps_filter, sink]):
                        print("Failed to create all elements")
                        return

                    # Set to raw video format, you can adjust based on your needs
                    caps_filter.set_property("caps", Gst.Caps.from_string("video/x-raw,format=RGB"))
                    
                    self.pipe.add(queue)
                    self.pipe.add(depay)
                    if parse:
                        self.pipe.add(parse)
                    self.pipe.add(decode)
                    self.pipe.add(convert)
                    self.pipe.add(scale)
                    self.pipe.add(caps_filter)
                    self.pipe.add(sink)

                    # Link elements
                    if not queue.link(depay):
                        print("Failed to link queue and depay")
                        return
                    if parse:
                        if not depay.link(parse) or not parse.link(decode):
                            print("Failed to link depay, parse, and decode")
                            return
                    else:
                        if not depay.link(decode):
                            print("Failed to link depay and decode")
                            return
                    if not decode.link(convert):
                        print("Failed to link decode and convert")
                        return
                    if not convert.link(scale):
                        print("Failed to link convert and scale")
                        return
                    if not scale.link(caps_filter):
                        print("Failed to link scale and caps_filter")
                        return
                    if not caps_filter.link(sink):
                        print("Failed to link caps_filter and sink")
                        return

                    # Link the incoming pad to our queue
                    pad.link(queue.get_static_pad("sink"))

                    # Sync states
                    queue.sync_state_with_parent()
                    depay.sync_state_with_parent()
                    if parse:
                        parse.sync_state_with_parent()
                    decode.sync_state_with_parent()
                    convert.sync_state_with_parent()
                    scale.sync_state_with_parent()
                    caps_filter.sync_state_with_parent()
                    sink.sync_state_with_parent()

                    print("FD sink video pipeline set up successfully")
                    
                elif self.framebuffer: ## send raw data to ffmpeg or something I guess, using the stdout?
                    print("APP SINK OUT")
                    if "VP8" in name:
                        out = Gst.parse_bin_from_description("queue ! rtpvp8depay ! queue max-size-buffers=0 max-size-time=0 ! decodebin ! videoconvert ! video/x-raw,format=BGR ! queue max-size-buffers=2 leaky=downstream ! appsink name=appsink", True)
                    elif "H264" in name:
                        out = Gst.parse_bin_from_description("queue ! rtph264depay ! h264parse ! queue max-size-buffers=0 max-size-time=0 ! openh264dec ! videoconvert ! video/x-raw,format=BGR ! queue max-size-buffers=2 leaky=downstream ! appsink name=appsink", True)
                    
                    self.pipe.add(out)
                    out.sync_state_with_parent()
                    sink = out.get_static_pad('sink')
                    pad.link(sink)
                    
                else:
                    printc('VIDEO record setup', "88F")
                    if self.pipe.get_by_name('filesink'):
                        print("VIDEO setup")
                        if "VP8" in name:
                            out = Gst.parse_bin_from_description("queue ! rtpvp8depay", True)
                        elif "H264" in name:
                            out = Gst.parse_bin_from_description("queue ! rtph264depay ! h264parse", True)
                            
                        self.pipe.add(out)
                        out.sync_state_with_parent()
                        sink = out.get_static_pad('sink')
                        out.link(self.pipe.get_by_name('filesink'))
                        pad.link(sink)
                    else:
                        if "VP8" in name:
                            out = Gst.parse_bin_from_description("queue ! rtpvp8depay ! mpegtsmux name=mux1 ! queue !"
            + "hlssink name=hlssink max-files=0 "
            + "target-duration=10 playlist-length=0 "
            + "location=" + "./" + self.streamin + "_"+str(int(time.time()))+"_segment_%05d.ts "
            + "playlist-location=" + "./" + self.streamin + "_"+str(int(time.time()))+".video.m3u8 " , True)

                        elif "H264" in name:
                            out = Gst.parse_bin_from_description("queue ! rtph264depay ! h264parse ! mpegtsmux name=mux1 ! queue ! "
            + "hlssink name=hlssink max-files=0 "
            + "target-duration=10 playlist-length=0 "
            + "location=" + "./" + self.streamin + "_"+str(int(time.time()))+"_segment_%05d.ts "
            + "playlist-location=" + "./" + self.streamin + "_"+str(int(time.time()))+".video.m3u8 " , True)

                        self.pipe.add(out)
                        out.sync_state_with_parent()
                        sink = out.get_static_pad('sink')
                        pad.link(sink)
                    print("success video?")

                if self.framebuffer:
                    frame_shape = (720, 1280, 3)
                    size = np.prod(frame_shape) * 3  # Total size in bytes
                    self.shared_memory = shared_memory.SharedMemory(create=True, size=size, name='psm_raspininja_streamid')
                    self.trigger_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # we don't bind, as the reader will be binding
                    print("*************")
                    print(self.shared_memory)
                    appsink = self.pipe.get_by_name('appsink')
                    appsink.set_property("emit-signals", True)
                    appsink.connect("new-sample", self.new_sample)

            elif "audio" in name:
                if self.noaudio:
                    printc('Ignoring incoming audio track', "F88")
                    
                    out = Gst.parse_bin_from_description("queue ! fakesink", True)
                    
                    self.pipe.add(out)
                    out.sync_state_with_parent()
                    sink = out.get_static_pad('sink')
                    pad.link(sink)
                    return

                if self.ndiout:
                    # I'm handling this on elsewhere now
                    pass
                elif self.view:
                   # if "OPUS" in name:
                    print("decode and play out the incoming audio")
                    out = Gst.parse_bin_from_description("queue ! rtpopusdepay ! opusparse ! opusdec ! audioconvert ! audioresample ! audio/x-raw,format=S16LE,rate=48000 ! autoaudiosink", True)
                    
                    self.pipe.add(out)
                    out.sync_state_with_parent()
                    sink = out.get_static_pad('sink')
                    pad.link(sink)
                elif self.fdsink:
                    #if "OPUS" in name:
                    out = Gst.parse_bin_from_description("queue ! rtpopusdepay ! opusparse ! opusdec ! audioconvert ! audioresample ! audio/x-raw,format=S16LE,rate=48000 ! fdsink", True)
                    
                    self.pipe.add(out)
                    out.sync_state_with_parent()
                    sink = out.get_static_pad('sink')
                    pad.link(sink)
                    
                elif self.framebuffer:
                    out = Gst.parse_bin_from_description("queue ! fakesink", True)
                    
                    self.pipe.add(out)
                    out.sync_state_with_parent()
                    sink = out.get_static_pad('sink')
                    pad.link(sink)
                    
                else:
                
                    if self.pipe.get_by_name('filesink'):
                        print("Audio being added after video")
                        if "OPUS" in name:
                            out = Gst.parse_bin_from_description("queue rtpopusdepay ! opusparse ! audio/x-opus,channel-mapping-family=0,channels=2,rate=48000", True)
                            
                        self.pipe.add(out)
                        out.sync_state_with_parent()
                        sink = out.get_static_pad('sink')
                        out.link(self.pipe.get_by_name('filesink'))
                        pad.link(sink)
                        
                    else:
                        print("audio being saved...")
                        if "OPUS" in name:
                            out = Gst.parse_bin_from_description("queue ! rtpopusdepay ! opusparse ! audio/x-opus,channel-mapping-family=0,rate=48000 ! mpegtsmux name=mux2 ! queue ! multifilesink name=filesinkaudio sync=true location="+self.streamin+"_"+str(int(time.time()))+"_audio.%02d.ts next-file=5 max-file-duration="+str(10*Gst.SECOND), True)

                        self.pipe.add(out)
                        out.sync_state_with_parent()
                        sink = out.get_static_pad('sink')
                        pad.link(sink)
                        
                print("success audio?")

        except Exception as E:
            print("============= ERROR =========")
            printwarn(get_exception_info(E))

            traceback.print_exc()

        # Add this debugging information at the end of the function
        print("Pipeline state after setup:")
        print(self.pipe.get_state(0))

            
    async def createPeer(self, UUID):

        if UUID in self.clients:
            client = self.clients[UUID]
        else:
            print("peer not yet created; error")
            return

        def on_offer_created(promise, _, __):
            print("ON OFFER CREATED")
            promise.wait()
            reply = promise.get_reply()
            offer = reply.get_value('offer')
            promise = Gst.Promise.new()
            client['webrtc'].emit('set-local-description', offer, promise)
            promise.interrupt()
            print("SEND SDP OFFER")
            text = offer.sdp.as_text()
            if ("96 96 96 96 96" in text):
                printc("Patching SDP due to Gstreamer webRTC bug - none-unique line values","A6F")
                text = text.replace(" 96 96 96 96 96", " 96 96 97 98 96")
                text = text.replace("a=rtpmap:96 red/90000\r\n","a=rtpmap:97 red/90000\r\n")
                text = text.replace("a=rtpmap:96 ulpfec/90000\r\n","a=rtpmap:98 ulpfec/90000\r\n")
                text = text.replace("a=rtpmap:96 rtx/90000\r\na=fmtp:96 apt=96\r\n","")
            elif self.nored and (" 96 96" in text): ## fix for older gstreamer is using --nored
                printc("Patching SDP due to Gstreamer webRTC bug - issue with nored","A6F")
                text = text.replace(" 96 96", " 96 97")
                text = text.replace("a=rtpmap:96 ulpfec/90000\r\n","a=rtpmap:97 ulpfec/90000\r\n")
                text = text.replace("a=rtpmap:96 rtx/90000\r\na=fmtp:96 apt=96\r\n","")

            if self.novideo and not self.noaudio: # impacts audio and video as well, but chrome / firefox seems to handle it
                printc("Patching SDP due to Gstreamer webRTC bug - audio-only issue", "A6F") # just chrome doesn't handle this
                text = replace_ssrc_and_cleanup_sdp(text)

            msg = {'description': {'type': 'offer', 'sdp': text}, 'UUID': client['UUID'], 'session': client['session'], 'streamID':self.stream_id+self.hashcode}
            self.sendMessage(msg)

        def on_new_tranceiver(element, trans):
            print("ON NEW TRANS")

        def on_negotiation_needed(element):
            print("ON NEGO NEEDED")
            promise = Gst.Promise.new_with_change_func(on_offer_created, element, None)
            element.emit('create-offer', None, promise)

        def send_ice_local_candidate_message(_, mlineindex, candidate):
            if " TCP " in candidate: ##  I Can revisit another time, but for now, this isn't needed: TODO: optimize
                return
            icemsg = {'candidates': [{'candidate': candidate, 'sdpMLineIndex': mlineindex}], 'session':client['session'], 'type':'local', 'UUID':client['UUID']}
            self.sendMessage(icemsg)

        def send_ice_remote_candidate_message(_, mlineindex, candidate):
            icemsg = {'candidates': [{'candidate': candidate, 'sdpMLineIndex': mlineindex}], 'session':client['session'], 'type':'remote', 'UUID':client['UUID']}
            self.sendMessage(icemsg)

        def on_signaling_state(p1, p2):
            print("ON SIGNALING STATE CHANGE: {}".format(client['webrtc'].get_property(p2.name)))

        def on_ice_connection_state(p1, p2):
            if (client['webrtc'].get_property(p2.name)==1):
                printwarn("ice changed to checking state")
            elif (client['webrtc'].get_property(p2.name)==2):
                printwarn("ice changed to connected state")
            elif (client['webrtc'].get_property(p2.name)==3):
                printwarn("ice changed to completed state")
            elif (client['webrtc'].get_property(p2.name)>3):
                printc("ice changed to state +4","FC2")

        def on_connection_state(p1, p2):
            print("on_connection_state")

            if (client['webrtc'].get_property(p2.name)==2): # connected
                print("PEER CONNECTION ACTIVE")
                promise = Gst.Promise.new_with_change_func(on_stats, client['webrtc'], None) # check stats
                client['webrtc'].emit('get-stats', None, promise)

                if not self.streamin and not client['send_channel']:
                    channel = client['webrtc'].emit('create-data-channel', 'sendChannel', None)
                    on_data_channel(client['webrtc'], channel)

                if client['timer'] == None:
                    client['ping'] = 0
                    client['timer'] = threading.Timer(3, pingTimer)
                    client['timer'].start()
                    self.clients[client["UUID"]] = client

            elif (client['webrtc'].get_property(p2.name)>=4): # closed/failed , but this won't work unless Gstreamer / LibNice support it -- which isn't the case in most versions.
                print("PEER CONNECTION DISCONNECTED")
                self.stop_pipeline(client['UUID'])
            else:
                print("PEER CONNECTION STATE {}".format(client['webrtc'].get_property(p2.name)))
        def print_trans(p1,p2):
            print("trans:  {}".format(client['webrtc'].get_property(p2.name)))

        def pingTimer():

            if not client['send_channel']:
                client['timer'] = threading.Timer(3, pingTimer)
                client['timer'].start()
                print("data channel not setup yet")
                return

            if "ping" not in client:
                client['ping'] = 0

            if client['ping'] < 10:
                client['ping'] += 1
                self.clients[client["UUID"]] = client
                try:
                    client['send_channel'].emit('send-string', '{"ping":"'+str(time.time())+'"}')
                    printout("PINGED")
                except Exception as E:
                    printwarn(get_exception_info(E))

                    print("PING FAILED")
                client['timer'] = threading.Timer(3, pingTimer)
                client['timer'].start()

                promise = Gst.Promise.new_with_change_func(on_stats, client['webrtc'], None) # check stats
                client['webrtc'].emit('get-stats', None, promise)

            else:
                printc("NO HEARTBEAT", "F44")
                self.stop_pipeline(client['UUID'])

        def on_data_channel(webrtc, channel):
            print("    --------- ON DATA CHANNEL")
            if channel is None:
                print('DATA CHANNEL: NOT AVAILABLE')
                return
            else:
                print('DATA CHANNEL SETUP')
            channel.connect('on-open', on_data_channel_open)
            channel.connect('on-error', on_data_channel_error)
            channel.connect('on-close', on_data_channel_close)
            channel.connect('on-message-string', on_data_channel_message)

        def on_data_channel_error(arg1, arg2):
            printc('DATA CHANNEL: ERROR', "F44")

        def on_data_channel_open(channel):
            printc('DATA CHANNEL: OPENED', "06F")
            client['send_channel'] = channel
            self.clients[client["UUID"]] = client
            if self.streamin:
                if self.noaudio:
                    msg = {"audio":False, "video":True, "UUID": client["UUID"]} ## You must edit the SDP instead if you want to force a particular codec
                elif self.novideo:
                    msg = {"audio":True, "video":False, "UUID": client["UUID"]} ## You must edit the SDP instead if you want to force a particular codec
                else:
                    msg = {"audio":True, "video":True, "UUID": client["UUID"]} ## You must edit the SDP instead if you want to force a particular codec
                self.sendMessage(msg)
            elif self.midi:
                msg = {"audio":False, "video":False, "allowmidi":True, "UUID": client["UUID"]} ## You must edit the SDP instead if you want to force a particular codec
                self.sendMessage(msg)
            elif self.rotate:
                msg = {"info":{"rotate_video":self.rotate}, "UUID": client["UUID"]}
                self.sendMessage(msg)

        def on_data_channel_close(channel):
            printc('DATA CHANNEL: CLOSE', "F44")

        def on_data_channel_message(channel, msg_raw): 
            try:
                msg = json.loads(msg_raw)
            except:
                printin("DID NOT GET JSON")
                return
            if 'candidates' in msg:
                printin("INBOUND ICE BUNDLE - DC")
                
                if 'vector' in msg:
                    try:
                        decryptedJson = decrypt_message(msg['candidates'], msg['vector'], self.password+self.salt)
                        msg['candidates'] = json.loads(decryptedJson)
                    except Exception as E:
                        printwarn(get_exception_info(E))

                
                for ice in msg['candidates']:
                    self.handle_sdp_ice(ice, client["UUID"])
            elif 'candidate' in msg:
                printin("INBOUND ICE SINGLE - DC")
                
                if 'vector' in msg:
                    try:
                        decryptedJson = decrypt_message(msg['candidate'], msg['vector'], self.password+self.salt)
                        msg['candidate'] = json.loads(decryptedJson)
                    except Exception as E:
                        printwarn(get_exception_info(E))

                
                self.handle_sdp_ice(msg, client["UUID"])
            elif 'pong' in msg: # Supported in v19 of VDO.Ninja
                printin('PONG')
                client['ping'] = 0
                self.clients[client["UUID"]] = client
            elif 'bye' in msg: ## v19 of VDO.Ninja
                printin("PEER INTENTIONALLY HUNG UP")
            elif 'description' in msg:
                printin("INCOMING SDP - DC")
                
                if 'vector' in msg:
                    try:
                        decryptedJson = decrypt_message(msg['description'], msg['vector'], self.password+self.salt)
                        msg['description'] = json.loads(decryptedJson)
                    except Exception as E:
                        printwarn(get_exception_info(E))

                
                if msg['description']['type'] == "offer":
                    self.handle_offer(msg['description'], client['UUID'])
            elif 'midi' in msg:
                printin("midi msg")
                vdo2midi(msg['midi'])
            elif 'bitrate' in msg:
                printin("bitrate msg")
                if client['encoder'] and msg['bitrate']:
                    print("Trying to change bitrate...")
                    if self.aom:
                        print("Aom doesn't support dynamic bitrates currently")
                        pass
                    else:
                        try:
                            client['encoder'].set_property('bitrate', int(msg['bitrate'])*1000)
                        except Exception as E:
                            printwarn(get_exception_info(E))

                            pass
            else:
                printin("MISC DC DATA")
                return

        def vdo2midi(midi):
            try:
                if self.midiout == None:
                    self.midiout = rtmidi.MidiOut()

                new_out_port = self.midiout.get_ports() # a bit inefficient, but safe
                if new_out_port != self.midiout_ports:
                    print("New MIDI Out device(s) initializing...")
                    self.midiout_ports = new_out_port
                    try:
                        self.midiout.close_port()
                    except:
                        pass

                    for i in range(len(self.midiout_ports)):
                        if "Midi Through" in self.midiout_ports[i]:
                            continue
                        break
                    if i < len(self.midiout_ports):
                        self.midiout.open_port(i)
                        print(i) ## midi output device
                    else:
                        return ## no MIDI out found; skipping

                self.midiout.send_message(midi['d'])
            except Exception as E:
                printwarn(get_exception_info(E))

        def sendMIDI(data, template):
            if data:
                 template['midi']['d'] = data[0]
                 data = json.dumps(template)
                 for client in self.clients:
                      if self.clients[client]['send_channel']:
                           try:
                               self.clients[client]['send_channel'].emit('send-string', data)
                           except:
                               pass

        def midi2vdo(midi):
            in_ports = None
            self.midiin = rtmidi.MidiIn()
            while True:
                in_ports_new = self.midiin.get_ports()
                if in_ports_new != in_ports:
                    in_ports = in_ports_new
                    if self.midiin:
                        print("New MIDI Input device(s) initializing...")
                        try:
                            self.midiin.close_port()
                        except:
                            pass
                    while True:
                        print(in_ports)
                        for i in range(len(in_ports)):
                            if "Midi Through" in in_ports[i]:
                                continue
                            break
                        if i < len(in_ports):
                            self.midiin.open_port(i)
                            print(i) ## midi input device
                            break
                        else:
                            time.sleep(0.5)
                            in_ports = self.midiin.get_ports()

                    template = {}
                    template['midi'] = {}
                    template['midi']['d'] = []
                    if self.puuid:
                        template['from'] = self.puuid
                    self.midiin.cancel_callback()
                    self.midiin.set_callback(sendMIDI, template)
                else:
                    time.sleep(4)

        def on_stats(promise, abin, data):
            promise.wait()
            stats = promise.get_reply()
            stats = stats.to_string()
            stats = stats.replace("\\", "")
            stats = stats.split("fraction-lost=(double)")
            if (len(stats)>1):
                stats = stats[1].split(",")[0]
                print("Packet loss:"+stats)
                if " vp8enc " in self.pipeline: # doesn't support dynamic bitrates? not sure the property to use at least
                    return
                elif " av1enc " in self.pipeline: # seg-fault if I try to change it currently
                    return
                stats = float(stats)
                if (stats>0.01) and not self.noqos:
                    print("Trying to reduce change bitrate...")
                    bitrate = self.bitrate*0.9
                    if bitrate < self.max_bitrate*0.2:
                        bitrate = self.max_bitrate*0.2
                    elif bitrate > self.max_bitrate*0.8:
                        bitrate = self.bitrate*0.9
                    self.bitrate = bitrate
                    print(str(bitrate))
                    try:
                        if self.aom:
                            client['encoder'].set_property('target-bitrate', int(bitrate))  # line not active due to 'elif " av1enc " in self.pipeline:' line
                        elif " mpph265enc " in self.pipeline or client['encoder'].get_name().startswith('mpph265enc'):
                            # For mpph265enc, use bps instead of bitrate
                            client['encoder'].set_property('bps', int(bitrate*1000))
                        elif " x265enc " in self.pipeline or client['encoder'].get_name().startswith('x265enc'):
                            client['encoder'].set_property('bitrate', int(bitrate))
                        elif client['encoder']:
                            client['encoder'].set_property('bitrate', int(bitrate*1000))
                        elif client['encoder1']:
                            client['encoder1'].set_property('bitrate', int(bitrate))
                        elif client['encoder2']:
                            pass

                    except Exception as E:
                        printwarn(get_exception_info(E))

                elif (stats<0.003) and not self.noqos:
                    print("Trying to increase change bitrate...")
                    bitrate = self.bitrate*1.05
                    if bitrate>self.max_bitrate:
                        bitrate = self.max_bitrate
                    elif bitrate*2<self.max_bitrate:
                        bitrate = self.bitrate*1.05
                    self.bitrate = bitrate
                    print(str(bitrate))
                    try:
                        if self.aom:
                            client['encoder'].set_property('target-bitrate', int(bitrate))  # line not active due to 'elif " av1enc " in self.pipeline:' line
                        elif " mpph265enc " in self.pipeline or client['encoder'].get_name().startswith('mpph265enc'):
                            # For mpph265enc, use bps instead of bitrate
                            client['encoder'].set_property('bps', int(bitrate*1000))
                        elif " x265enc " in self.pipeline or client['encoder'].get_name().startswith('x265enc'):
                            client['encoder'].set_property('bitrate', int(bitrate))
                        elif client['encoder']:
                            client['encoder'].set_property('bitrate', int(bitrate*1000))
                        elif client['encoder1']:
                            client['encoder1'].set_property('bitrate', int(bitrate))
                        elif client['encoder2']:
                            pass
                    except Exception as E:
                        printwarn(get_exception_info(E))

        print("creating a new webrtc bin")

        started = True
        if not self.pipe:
            print("loading pipe")

            if self.streamin:
                self.pipe = Gst.Pipeline.new('decode-pipeline') ## decode or capture
            elif len(self.pipeline)<=1:
                self.pipe = Gst.Pipeline.new('data-only-pipeline')
            else:
                print(self.pipeline)
                self.pipe = Gst.parse_launch(self.pipeline)
                
            print(self.pipe)
            started = False
            
        client['qv'] = None
        client['qa'] = None
        client['encoder'] = False
        client['encoder1'] = False
        client['encoder2'] = False
        
        try:
            client['encoder'] = self.pipe.get_by_name('encoder')
        except:
            try:
                client['encoder1'] = self.pipe.get_by_name('encoder1')
            except:
                try:
                    client['encoder2'] = self.pipe.get_by_name('encoder2')
                except:
                    pass

        if self.streamin:
            client['webrtc'] = Gst.ElementFactory.make("webrtcbin", client['UUID'])
            client['webrtc'].set_property('bundle-policy', "max-bundle")
            ssetup_ice_servers(client['webrtc'], self)
            
            try:
                client['webrtc'].set_property('latency', self.buffer)
                client['webrtc'].set_property('async-handling', True)
            except Exception as E:
                pass
            self.pipe.add(client['webrtc'])
           
            if self.vp8:     
                pass
            elif self.h264:
                direction = GstWebRTC.WebRTCRTPTransceiverDirection.RECVONLY
                caps = Gst.caps_from_string("application/x-rtp,media=video,encoding-name=H264,payload=102,clock-rate=90000,packetization-mode=(string)1")
                tcvr = client['webrtc'].emit('add-transceiver', direction, caps)
                if Gst.version().minor > 18:
                    tcvr.set_property("codec-preferences",caps) ## supported as of around June 2021 in gstreamer for answer side?

        elif not self.multiviewer:
            client['webrtc'] = self.pipe.get_by_name('sendrecv')
            self.setup_ice_servers(client['webrtc'])
            pass
        else:
            client['webrtc'] = Gst.ElementFactory.make("webrtcbin", client['UUID'])
            client['webrtc'].set_property('bundle-policy', 'max-bundle')
            self.setup_ice_servers(client['webrtc'])
            
            try:
                client['webrtc'].set_property('latency', self.buffer)
                client['webrtc'].set_property('async-handling', True)
            except Exception as E:
                pass
            self.pipe.add(client['webrtc'])

            atee = self.pipe.get_by_name('audiotee')
            vtee = self.pipe.get_by_name('videotee')

            if vtee is not None:
                qv = Gst.ElementFactory.make('queue', f"qv-{client['UUID']}")
                self.pipe.add(qv)
                if not Gst.Element.link(vtee, qv):
                    return
                if not Gst.Element.link(qv, client['webrtc']):
                    return
                if qv is not None: qv.sync_state_with_parent()
                client['qv'] = qv

            if atee is not None:
                qa = Gst.ElementFactory.make('queue', f"qa-{client['UUID']}")
                self.pipe.add(qa)
                if not Gst.Element.link(atee, qa):
                    return
                if not Gst.Element.link(qa, client['webrtc']):
                    return
                if qa is not None: qa.sync_state_with_parent()
                client['qa'] = qa

            if self.midi and (self.midi_thread == None):
                self.midi_thread = threading.Thread(target=midi2vdo, args=(self.midi,))
                self.midi_thread.start()
                print(self.midi_thread)
                print("MIDI THREAD STARTED")

        try:
            client['webrtc'].connect('notify::ice-connection-state', on_ice_connection_state)
            client['webrtc'].connect('notify::connection-state', on_connection_state)
            client['webrtc'].connect('notify::signaling-state', on_signaling_state)

        except Exception as e:
            printwarn(get_exception_info(E))

            pass

        if self.streamin:
            client['webrtc'].connect('pad-added', self.on_incoming_stream)
            client['webrtc'].connect('on-ice-candidate', send_ice_remote_candidate_message)
            client['webrtc'].connect('on-data-channel', on_data_channel)
        else:
            client['webrtc'].connect('on-ice-candidate', send_ice_local_candidate_message)
            client['webrtc'].connect('on-negotiation-needed', on_negotiation_needed)
            client['webrtc'].connect('on-new-transceiver', on_new_tranceiver)

        try:
            if not self.streamin:
                trans = client['webrtc'].emit("get-transceiver",0)
                if trans is not None:
                    try:
                        if not self.nored:
                            trans.set_property("fec-type", GstWebRTC.WebRTCFECType.ULP_RED)
                            print("FEC ENABLED")
                    except Exception as E:
                        pass
                    trans.set_property("do-nack", True)
                    print("SEND NACKS ENABLED")

        except Exception as E:
            printwarn(get_exception_info(E))

        if not started and self.pipe.get_state(0)[1] is not Gst.State.PLAYING:
            self.pipe.set_state(Gst.State.PLAYING)
            
        client['webrtc'].sync_state_with_parent()

        if not self.streamin and not client['send_channel']:
            channel = client['webrtc'].emit('create-data-channel', 'sendChannel', None)
            on_data_channel(client['webrtc'], channel)
            
        self.clients[client["UUID"]] = client
        

    def handle_sdp_ice(self, msg, UUID):
        client = self.clients[UUID]
        if not client or not client['webrtc']:
            print("! CLIENT NOT FOUND OR INVALID")
            return
        if 'sdp' in msg:
            print("INCOMING ANSWER SDP TYPE: "+msg['type'])
            assert(msg['type'] == 'answer')
            sdp = msg['sdp']
            res, sdpmsg = GstSdp.SDPMessage.new()
            GstSdp.sdp_message_parse_buffer(bytes(sdp.encode()), sdpmsg)
            answer = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.ANSWER, sdpmsg)
            promise = Gst.Promise.new()
            client['webrtc'].emit('set-remote-description', answer, promise)
            promise.interrupt()
        elif 'candidate' in msg:
            print("  ~ HANDLING INBOUND ICE")
            candidate = msg['candidate']
            sdpmlineindex = msg['sdpMLineIndex']
            client['webrtc'].emit('add-ice-candidate', sdpmlineindex, candidate)
        else:
            print(msg)
            print("UNEXPECTED INCOMING")

    def on_answer_created(self, promise, _, client):
        print("ON ANSWER CREATED")
        promise.wait()
        reply = promise.get_reply()
        answer = reply.get_value('answer')
        if not answer:
            print("Not answer created?")
            return
        promise = Gst.Promise.new()
        client['webrtc'].emit('set-local-description', answer, promise)
        promise.interrupt()
        print("SEND SDP ANSWER")
        text = answer.sdp.as_text()
        msg = {'description': {'type': 'answer', 'sdp': text}, 'UUID': client['UUID'], 'session': client['session']}
        self.sendMessage(msg)

    def handle_offer(self, msg, UUID):
        print("HANDLE SDP OFFER")
        print("-----")
        client = self.clients[UUID]
        if not client or not client['webrtc']:
            return
        if 'sdp' in msg:
            print("INCOMDING OFFER SDP TYPE: "+msg['type'])
            assert(msg['type'] == 'offer')
            sdp = msg['sdp']
            res, sdpmsg = GstSdp.SDPMessage.new()
            GstSdp.sdp_message_parse_buffer(bytes(sdp.encode()), sdpmsg)
            offer = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.OFFER, sdpmsg)
            promise = Gst.Promise.new()
            client['webrtc'].emit('set-remote-description', offer, promise)
            promise.interrupt()
            promise2 = Gst.Promise.new_with_change_func(self.on_answer_created, client['webrtc'], client)
            client['webrtc'].emit('create-answer', None, promise2)
        else:
            print("No SDP as expected")

    async def start_pipeline(self, UUID):
        print("\nSTART PIPE\n----")
        enableLEDs(100)
        if self.multiviewer:
            await self.createPeer(UUID)
        else:
            for uid in self.clients:
                if uid != UUID:
                    print("Consider --multiviewer mode if you need multiple viewers")
                    self.stop_pipeline(uid)
                    break
            if self.save_file:
                pass
            elif self.pipe:
                print("setting pipe to null")
                self.pipe.set_state(Gst.State.NULL)
                self.pipe = None

                if UUID in self.clients:
                    print("Resetting existing pipe and p2p connection.")
                    session = self.clients[UUID]["session"]

                    if self.clients[UUID]['timer']:
                        self.clients[UUID]['timer'].cancel()
                        print("stop previous ping/pong timer")

                    self.clients[UUID] = {}
                    self.clients[UUID]["UUID"] = UUID
                    self.clients[UUID]["session"] = session
                    self.clients[UUID]["send_channel"] = None

                    self.clients[UUID]["timer"] = None
                    self.clients[UUID]["ping"] = 0
                    self.clients[UUID]["webrtc"] = None

            await self.createPeer(UUID)

    def stop_pipeline(self, UUID):
        print("STOP PIPE")
        if not self.multiviewer:
            if UUID in self.clients:
                del self.clients[UUID]
        elif UUID in self.clients:
            atee = self.pipe.get_by_name('audiotee')
            vtee = self.pipe.get_by_name('videotee')

            if atee is not None and self.clients[UUID]['qa'] is not None:
                atee.unlink(self.clients[UUID]['qa'])
            if vtee is not None and self.clients[UUID]['qv'] is not None:
                vtee.unlink(self.clients[UUID]['qv'])

            if self.clients[UUID]['webrtc'] is not None:
                self.pipe.remove(self.clients[UUID]['webrtc'])
                self.clients[UUID]['webrtc'].set_state(Gst.State.NULL)
            if self.clients[UUID]['qa'] is not None:
                self.pipe.remove(self.clients[UUID]['qa'])
                self.clients[UUID]['qa'].set_state(Gst.State.NULL)
            if self.clients[UUID]['qv'] is not None:
                self.pipe.remove(self.clients[UUID]['qv'])
                self.clients[UUID]['qv'].set_state(Gst.State.NULL)
            del self.clients[UUID]

        if len(self.clients)==0:
            enableLEDs(0.1)

        if self.pipe:
            if self.save_file:
                pass
            elif len(self.clients)==0:
                self.pipe.set_state(Gst.State.NULL)
                self.pipe = None

    async def loop(self):
        assert self.conn
        print("WSS CONNECTED")
        async for message in self.conn:
            try:
                msg = json.loads(message)
                if 'from' in msg:
                    if self.puuid==None:
                        self.puuid = str(random.randint(10000000,99999999999))
                    if msg['from'] == self.puuid:
                        continue
                    UUID = msg['from']
                    if ('UUID' in msg) and (msg['UUID'] != self.puuid):
                        continue
                elif 'UUID' in msg:
                    if (self.puuid != None) and (self.puuid != msg['UUID']):
                        print("PUUID NOT  SAME")
                        continue
                    UUID = msg['UUID']
                else:
                    if self.room_name:
                        if 'request' in msg:
                            if msg['request'] == 'listing':
                                if self.streamin:
                                    printwout("play stream")
                                    await self.sendMessageAsync({"request":"play","streamID":self.streamin+self.hashcode})
                                else:
                                    printwout("seed start")
                                    await self.sendMessageAsync({"request":"seed","streamID":self.stream_id+self.hashcode})
                    continue

                if UUID not in self.clients:
                    self.clients[UUID] = {}
                    self.clients[UUID]["UUID"] = UUID
                    self.clients[UUID]["session"] = None
                    self.clients[UUID]["send_channel"] = None
                    self.clients[UUID]["timer"] = None
                    self.clients[UUID]["ping"] = 0
                    self.clients[UUID]["webrtc"] = None

                if 'session' in msg:
                    if not self.clients[UUID]['session']:
                        self.clients[UUID]['session'] = msg['session']
                    elif self.clients[UUID]['session'] != msg['session']:
                        print("sessions don't match")

                if 'description' in msg:
                    print("description via WSS")
                    
                    if 'vector' in msg:
                        decryptedJson = decrypt_message(msg['description'], msg['vector'], self.password+self.salt)
                        msg = json.loads(decryptedJson)
                    else:
                        msg = msg['description']
                        
                    if 'type' in msg:
                        if msg['type'] == "offer":
                            if self.streamin:
                                printwin("incoming offer")
                                await self.start_pipeline(UUID)
                                self.handle_offer(msg, UUID)
                            else:
                                printc("We don't support two-way video calling yet. ignoring remote offer.", "399")
                                continue
                        elif msg['type'] == "answer":
                            printwin("incoming answer")
                            self.handle_sdp_ice(msg, UUID)
                elif 'candidates' in msg:
                    print("ice candidates BUNDLE via WSS")
                    
                    if 'vector' in msg:
                        decryptedJson = decrypt_message(msg['candidates'], msg['vector'], self.password+self.salt)
                        msg['candidates'] = json.loads(decryptedJson)
                    
                    if type(msg['candidates']) is list:
                        for ice in msg['candidates']:
                            self.handle_sdp_ice(ice, UUID)
                    else:
                        printc("Warning: Expected a list of candidates","F00")
                elif 'candidate' in msg:
                    print("ice candidate SINGLE via WSS")
                    if 'vector' in msg:
                        decryptedJson = decrypt_message(msg['candidate'], msg['vector'], self.password+self.salt)
                        msg['candidate'] = json.loads(decryptedJson)
                    
                    self.handle_sdp_ice(msg, UUID)
                elif 'request' in msg:
                    print("REQUEST via WSS: ", msg['request'])
                    if 'offerSDP' in  msg['request']:
                        await self.start_pipeline(UUID)
                    elif msg['request'] == "play":
                        printwin("play requested")
                        if 'streamID' in msg:
                            if msg['streamID'] == self.stream_id+self.hashcode:
                                await self.start_pipeline(UUID)
                    elif msg['request'] == "videoaddedtoroom":
                        if 'streamID' in msg:
                            if self.streamin:
                                printwout("play stream.")
                                await self.sendMessageAsync({"request":"play","streamID":self.streamin+self.hashcode})
                    elif msg['request'] == 'joinroom':
                        if self.streamin and self.streamID and (self.streamin+self.hashcode == self.streamID):
                            if self.room_hashcode:
                                printwout("play stream..")
                                await self.sendMessageAsync({"request":"play","streamID":self.streamin+self.hashcode,"roomid":self.room_hashcode, "UUID":UUID})
                            elif self.room_name:
                                printwout("play stream...")
                                await self.sendMessageAsync({"request":"play","streamID":self.streamin+self.hashcode,"roomid":self.room_name, "UUID":UUID})
                        else:
                            printwout("seed start")
                            await self.sendMessageAsync({"request":"seed", "streamID":self.stream_id+self.hashcode, "UUID":UUID})
                            
                            
            except KeyboardInterrupt:
                print("Ctrl+C detected. Exiting...")
                break

            except websockets.ConnectionClosed:
                print("WEB SOCKETS CLOSED; retrying in 5s")
                await asyncio.sleep(5)
                continue
            except Exception as E:
                printwarn(get_exception_info(E))


        return 0

def check_plugins(needed, require=False):
    if type(needed)==type("str"):
        needed = [needed]
    missing = list(filter(lambda p: (Gst.Registry.get().find_plugin(p) is None and not Gst.ElementFactory.find(p)), needed))
    if len(missing):
        if require:
            print('Missing gstreamer plugin/element:', missing)
        return False
    return True

def on_message(bus: Gst.Bus, message: Gst.Message, loop):
    mtype = message.type

    if not loop:
        try:
            loop = GLib.MainLoop
        except:
            loop = GObject.MainLoop

    if mtype == Gst.MessageType.EOS:
        print("End of stream")
        loop.quit()

    elif mtype == Gst.MessageType.ERROR:
        err, debug = message.parse_error()
        print(err, debug)
        loop.quit()

    elif mtype == Gst.MessageType.WARNING:
        err, debug = message.parse_warning()
        print(err, debug)

    elif mtype == Gst.MessageType.LATENCY:  # needs self. scope added
        print("LATENCY")

    elif mtype == Gst.MessageType.ELEMENT:
        print("ELEMENT")

    return True

def supports_resolution_and_format(device, width, height, framerate=None):
    supported_formats = []
    if framerate is not None:
        framerate = str(framerate)+"/1"

    if device and device.get_caps():
        for structure in device.get_caps().to_string().split(';'):
            if 'video/x-raw' in structure and 'width=(int)' + str(width) in structure and 'height=(int)' + str(height) in structure:
                if framerate and 'framerate=' in structure:
                    if framerate in structure:
                        format_type = structure.split('format=(string)')[1].split(',')[0]  # Extract the format
                        supported_formats.append(format_type)
                else:
                    format_type = structure.split('format=(string)')[1].split(',')[0]  # Extract the format
                    supported_formats.append(format_type)
            elif 'jpeg' in structure:
                 supported_formats.append('JPEG')
            elif '264' in structure:
                 supported_formats.append('H264')
    priority_order = ['JPEG', 'I420', 'YVYU','YUY2','NV12', 'NV21', 'UYVY', 'RGB', 'BGR', 'BGRx', 'RGBx']
    return sorted(supported_formats, key=lambda x: priority_order.index(x) if x in priority_order else len(priority_order))

class WHIPClient:
    def __init__(self, pipeline_desc, args):
        self.pipeline_desc = pipeline_desc
        self.args = args
        self.pipe = None
        self.loop = None
        
    def setup_pipeline(self):
        # Configure WHIP elements
        whip_props = [
            'whipsink name=sendrecv',
            f'whip-endpoint="{self.args.whip}"'
        ]
        
        # Add STUN servers
        if self.args.stun_server:
            if self.args.stun_server not in ["0", "false", "null"]:
                whip_props.append(f'stun-server="{self.args.stun_server}"')
        else:
            whip_props.append('stun-server="stun://stun.cloudflare.com:3478"')
            whip_props.append('stun-server="stun://stun.l.google.com:19302"')
        
        # Add TURN servers    
        if self.args.turn_server:
            if self.args.turn_server not in ["0", "false", "null"]:
                whip_props.append(f'turn-server="{self.args.turn_server}"')
        else:
            whip_props.append('turn-server="turn://vdoninja:IchBinSteveDerNinja@www.turn.vdo.ninja:3478"')
        
        whip_props.append(f'ice-transport-policy={self.args.ice_transport_policy}')
        
        # Build complete pipeline
        pipeline_segments = [self.pipeline_desc]
        pipeline_segments.append(' '.join(whip_props))
        complete_pipeline = ' '.join(pipeline_segments)
        
        print('gst-launch-1.0 ' + complete_pipeline.replace('(', '\\(').replace(')', '\\)'))
        
        self.pipe = Gst.parse_launch(complete_pipeline)
        return self.pipe

    def on_state_changed(self, bus, message):
        if message.type == Gst.MessageType.STATE_CHANGED:
            if message.src == self.pipe:
                old, new, pending = message.parse_state_changed()
                print(f"Pipeline state changed from {old} to {new}")
                if new == Gst.State.NULL:
                    printwarn("Pipeline stopped unexpectedly")
                    GLib.timeout_add_seconds(30, self.reconnect)

    def reconnect(self):
        if self.pipe:
            self.pipe.set_state(Gst.State.NULL)
        self.setup_pipeline()
        self.pipe.set_state(Gst.State.PLAYING)
        return False

    def start(self):
        if not check_plugins('whipsink'):
            print("WHIP SINK not installed. Please install (build if needed) the gst-plugins-rs webrtchttp plugin for your specific version of Gstreamer; 1.22 or newer required")
            return False
            
        self.setup_pipeline()
        bus = self.pipe.get_bus()
        bus.add_signal_watch()
        bus.connect('message::state-changed', self.on_state_changed)
        
        self.pipe.set_state(Gst.State.PLAYING)
        
        try:
            self.loop = GLib.MainLoop()
        except:
            self.loop = GObject.MainLoop()
            
        try:
            self.loop.run()
        except Exception as E:
            printwarn(get_exception_info(E))
            if self.loop:
                self.loop.quit()
            return False
            
        return True

    def stop(self):
        if self.pipe:
            self.pipe.set_state(Gst.State.NULL)
        if self.loop:
            self.loop.quit()

WSS="wss://wss.vdo.ninja:443"

async def main():

    error = False
    parser = argparse.ArgumentParser()
    parser.add_argument('--streamid', type=str, default=str(random.randint(1000000,9999999)), help='Stream ID of the peer to connect to')
    parser.add_argument('--room', type=str, default=None, help='optional - Room name of the peer to join')
    parser.add_argument('--rtmp', type=str, default=None, help='Use RTMP instead; pass the rtmp:// publishing address here to use')
    parser.add_argument('--whip', type=str, default=None, help='Use WHIP output instead; pass the https://whip.publishing/address here to use')
    parser.add_argument('--bitrate', type=int, default=2500, help='Sets the video bitrate; kbps. If error correction (red) is on, the total bandwidth used may be up to 2X higher than the bitrate')
    parser.add_argument('--audiobitrate', type=int, default=64, help='Sets the audio bitrate; kbps.')
    parser.add_argument('--width', type=int, default=1920, help='Sets the video width. Make sure that your input supports it.')
    parser.add_argument('--height', type=int, default=1080, help='Sets the video height. Make sure that your input supports it.')
    parser.add_argument('--framerate', type=int, default=30, help='Sets the video framerate. Make sure that your input supports it.')
    parser.add_argument('--server', type=str, default=None, help='Handshake server to use, eg: "wss://wss.vdo.ninja:443"')
    parser.add_argument('--puuid',  type=str, default=None, help='Specify a custom publisher UUID value; not required')
    parser.add_argument('--test', action='store_true', help='Use test sources.')
    parser.add_argument('--hdmi', action='store_true', help='Try to setup a HDMI dongle')
    parser.add_argument('--camlink', action='store_true', help='Try to setup an Elgato Cam Link')
    parser.add_argument('--z1', action='store_true', help='Try to setup a Theta Z1 360 camera')
    parser.add_argument('--z1passthru', action='store_true', help='Try to setup a Theta Z1 360 camera, but do not transcode')
    parser.add_argument('--apple', type=str, action=None, help='Sets Apple Video Foundation media device; takes a device index value (0,1,2,3,etc)')
    parser.add_argument('--v4l2', type=str, default=None, help='Sets the V4L2 input device.')
    parser.add_argument('--libcamera', action='store_true',  help='Use libcamera as the input source')
    parser.add_argument('--rpicam', action='store_true', help='Sets the RaspberryPi CSI input device. If this fails, try --rpi --raw or just --raw instead.')
    parser.add_argument('--format', type=str, default=None, help='The capture format type: YUYV, I420, BGR, or even JPEG/H264')
    parser.add_argument('--rotate', type=int, default=0, help='Rotates the camera in degrees; 0 (default), 90, 180, 270 are possible values.')
    parser.add_argument('--nvidiacsi', action='store_true', help='Sets the input to the nvidia csi port.')
    parser.add_argument('--alsa', type=str, default=None, help='Use alsa audio input.')
    parser.add_argument('--pulse', type=str, help='Use pulse audio (or pipewire) input.')
    parser.add_argument('--zerolatency', action='store_true', help='A mode designed for the lowest audio output latency')
    parser.add_argument('--raw', action='store_true', help='Opens the V4L2 device with raw capabilities.')
    parser.add_argument('--bt601', action='store_true', help='Use colormetery bt601 mode; enables raw mode also')
    parser.add_argument('--h264', action='store_true', help='Prioritize h264 over vp8')
    parser.add_argument('--x264', action='store_true', help='Prioritizes x264 encoder over hardware encoder')
    parser.add_argument('--openh264', action='store_true', help='Prioritizes OpenH264 encoder over hardware encoder')
    parser.add_argument('--vp8', action='store_true', help='Prioritizes vp8 codec over h264; software encoder')
    parser.add_argument('--vp9', action='store_true', help='Prioritizes vp9 codec over h264; software encoder')
    parser.add_argument('--aom', action='store_true', help='Prioritizes AV1-AOM codec; software encoder')
    parser.add_argument('--av1', action='store_true', help='Auto selects an AV1 codec for encoding; hardware or software')
    parser.add_argument('--rav1e', action='store_true', help='rav1e AV1 encoder used')
    parser.add_argument('--qsv', action='store_true', help='Intel quicksync AV1 encoder used')
    parser.add_argument('--omx', action='store_true', help='Try to use the OMX driver for encoding video; not recommended')
    parser.add_argument('--vorbis', action='store_true', help='Try to use the OMX driver for encoding video; not recommended')
    parser.add_argument('--nvidia', action='store_true', help='Creates a pipeline optimised for nvidia hardware.')
    parser.add_argument('--rpi', action='store_true', help='Creates a pipeline optimised for raspberry pi hardware encoder. This wont work with the Raspberry Pi 5, as it has no hardware encoder..')
    parser.add_argument('--multiviewer', action='store_true', help='Allows for multiple viewers to watch a single encoded stream; will use more CPU and bandwidth.')
    parser.add_argument('--noqos', action='store_true', help='Do not try to automatically reduce video bitrate if packet loss gets too high. The default will reduce the bitrate if needed.')
    parser.add_argument('--nored', action='store_true', help='Disable error correction redundency for transmitted video. This may reduce the bandwidth used by half, but it will be more sensitive to packet loss')
    parser.add_argument('--novideo', action='store_true', help='Disables video input.')
    parser.add_argument('--noaudio', action='store_true', help='Disables audio input.')
    parser.add_argument('--led', action='store_true', help='Enable GPIO pin 12 as an LED indicator light; for Raspberry Pi.')
    parser.add_argument('--pipeline', type=str, help='A full custom pipeline')
    parser.add_argument('--record',  type=str, help='Specify a stream ID to record to disk. System will not publish a stream when enabled.')
    parser.add_argument('--view',  type=str, help='Specify a stream ID to play out to the local display/audio.')
    parser.add_argument('--save', action='store_true', help='Save a copy of the outbound stream to disk. Publish Live + Store the video.')
    parser.add_argument('--midi', action='store_true', help='Transparent MIDI bridge mode; no video or audio.')
    parser.add_argument('--filesrc', type=str, default=None,  help='Provide a media file (local file location) as a source instead of physical device; it can be a transparent webm or whatever. It will be transcoded, which offers the best results.')
    parser.add_argument('--filesrc2', type=str, default=None,  help='Provide a media file (local file location) as a source instead of physical device; it can be a transparent webm or whatever. It will not be transcoded, so be sure its encoded correctly. Specify if --vp8 or --vp9, else --h264 is assumed.')
    parser.add_argument('--pipein', type=str, default=None, help='Pipe a media stream in as the input source. Pass `auto` for auto-decode,pass codec type for pass-thru (mpegts,h264,vp8,vp9), or use `raw`')
    parser.add_argument('--ndiout',  type=str, help='VDO.Ninja to NDI output; requires the NDI Gstreamer plugin installed')
    parser.add_argument('--fdsink',  type=str, help='VDO.Ninja to the stdout pipe; common for piping data between command line processes')
    parser.add_argument('--framebuffer', type=str, help='VDO.Ninja to local frame buffer; performant and Numpy/OpenCV friendly')
    parser.add_argument('--debug', action='store_true', help='Show added debug information from Gsteamer and other aspects of the app')
    parser.add_argument('--buffer',  type=int, default=200, help='The jitter buffer latency in milliseconds; default is 200ms. (gst +v1.18)')
    parser.add_argument('--password', type=str, nargs='?', default="someEncryptionKey123", required=False, const='', help='Specify a custom password. If setting to false, password/encryption will be disabled.')
    parser.add_argument('--hostname', type=str, default='https://vdo.ninja/', help='Your URL for vdo.ninja, if self-hosting the website code')
    parser.add_argument('--video-pipeline', type=str, default=None, help='Custom GStreamer video source pipeline')
    parser.add_argument('--audio-pipeline', type=str, default=None, help='Custom GStreamer audio source pipeline')
    parser.add_argument('--timestamp', action='store_true',  help='Add a timestamp to the video output, if possible')
    parser.add_argument('--clockstamp', action='store_true',  help='Add a clock overlay to the video output, if possible')
    parser.add_argument('--socketport', type=str, default=12345, help='Output video frames to a socket; specify the port number')
    parser.add_argument('--socketout', type=str, help='Output video frames to a socket; specify the stream ID')
    parser.add_argument('--stun-server', type=str, help='STUN server URL (stun://hostname:port)')
    parser.add_argument('--turn-server', type=str, help='TURN server URL (turn(s)://username:password@host:port)')
    parser.add_argument('--ice-transport-policy', type=str, choices=['all', 'relay'], default='all', help='ICE transport policy (all or relay)')
    parser.add_argument('--h265', action='store_true', help='Prioritize h265/hevc encoding over h264')
    parser.add_argument('--hevc', action='store_true', help='Prioritize h265/hevc encoding over h264 (same as --h265)')
    parser.add_argument('--x265', action='store_true', help='Prioritizes x265 software encoder over hardware encoders')


    args = parser.parse_args()

    Gst.init(None)
    Gst.debug_set_active(False)

    if args.debug:
        Gst.debug_set_default_threshold(2)
    else:
        Gst.debug_set_default_threshold(0)
    if args.led:
        try:
            import RPi.GPIO as GPIO
            global LED_Level, P_R, pin
            GPIO.setwarnings(False)
            pin = 12  # pins is a dict
            GPIO.setmode(GPIO.BOARD)       # Numbers GPIOs by physical location
            LED_Level = 0.1 # 0.1 to 100
            GPIO.setup(pin, GPIO.OUT)   # Set pins' mode is output
            GPIO.output(pin, GPIO.HIGH) # Set pins to high(+3.3V) to off led
            p_R = GPIO.PWM(pin, 120)  # set Frequece to 2KHzi
            enableLEDs(0.1)
        except Exception as E:
            pass

    timestampOverlay = ''
    if args.timestamp:
        timestampOverlay = ' ! timeoverlay valignment=bottom halignment=right font-desc="Sans, 36"'
    elif args.clockstamp:
        timestampOverlay = ' ! clockoverlay valignment=bottom halignment=right font-desc="Sans, 36"'

    if args.password == None:
        pass
    elif args.password.lower() in ["", "true", "1", "on"]:
        args.password = "someEncryptionKey123"
    elif args.password.lower() in ["false", "0", "off"]:
        args.password = None

    PIPELINE_DESC = ""

    needed = ["rtp", "rtpmanager"]
    if not args.rtmp:
        needed += ["webrtc","nice", "sctp", "dtls", "srtp"]
    if not check_plugins(needed, True):
        sys.exit(1)
    needed = []

    if args.ndiout:
        needed += ['ndi']
        if not args.record:
            args.streamin = args.ndiout
        else:
            args.streamin = args.record
    elif args.view:
        args.streamin = args.view
         
    elif args.fdsink:
        args.streamin = args.fdsink
    elif args.socketout:
        args.streamin = args.socketout
    elif args.framebuffer:
        if not np:
            print("You must install Numpy for this to work.\npip3 install numpy")
            sys.exit()
        args.streamin = args.framebuffer
    elif args.record:
        args.streamin = args.record
    else:
        args.streamin = False

    audiodevices = []
    if not (args.test or args.noaudio or args.streamin):
        monitor = Gst.DeviceMonitor.new()
        monitor.add_filter("Audio/Source", None)
        audiodevices = monitor.get_devices()

    if not args.alsa and not args.noaudio and not args.pulse and not args.test and not args.pipein and not args.streamin:
        default = [d for d in audiodevices if d.get_properties().get_value("is-default") is True]
        args.alsa = "default"
        aname = "default"

        if len(default) > 0:
            device = default[0]
            args.alsa = 'hw:'+str(device.get_properties().get_value("alsa.card"))+',0'
            print(" >> Default audio device selected: %s, via '%s'" % (device.get_display_name(), 'alsasrc device="hw:'+str(device.get_properties().get_value("alsa.card"))+',0"'))
        elif len(audiodevices)==0:
            args.noaudio = True
            print("\nNo microphone or audio source found; disabling audio.")
        else:
            try:
                print("\nDetected audio sources:")
                for i, d in enumerate(audiodevices):
                    print("  - ",audiodevices[i].get_display_name(), audiodevices[i].get_property("internal-name"), audiodevices[i].get_properties().get_value("alsa.card"), audiodevices[i].get_properties().get_value("is-default"))
                    args.alsa = 'hw:'+str(audiodevices[i].get_properties().get_value("alsa.card"))+',0'
                print()
                default = None
                for d in audiodevices:
                    props = d.get_properties()
                    for e in range(int(props.n_fields())):
                        if (props.nth_field_name(e) == "device.api" and props.get_value(props.nth_field_name(e)) == "alsa"):
                            default = d
                            break
                    if default:
                        print(" >> Selected the audio device: %s, via '%s'" % (default.get_display_name(), 'alsasrc device="hw:'+str(default.get_properties().get_value("alsa.card"))+',0"'))
                        args.alsa = 'hw:'+str(default.get_properties().get_value("alsa.card"))+',0'
                        break
                if not default:
                    args.noaudio = True
                    print("\nNo audio source selected; disabling audio.")
            except Exception as e:
                print(f"Error accessing properties for audio device {i}: {e}")
        print()

    if check_plugins("rpicamsrc"):
        args.rpi=True
    elif check_plugins("nvvidconv"):
        args.nvidia=True
        if check_plugins("nvarguscamerasrc"):
            if not args.nvidiacsi and not args.record:
                print("\nTip: If using the Nvidia CSI camera, you'll want to use --nvidiacsi to enable it.\n")

    if args.rpicam:
        print("Please note: If rpicamsrc cannot be found, use --libcamera instead")
        if not check_plugins('rpicamsrc'):
            print("rpicamsrc was not found. using just --rpi instead")
            print()
            args.raw = True
            args.rpi = True
            args.rpicam = False

    if args.aom:
        if not check_plugins(['aom','videoparsersbad','rsrtp'], True):
            print("You'll probably need to install gst-plugins-rs to use AV1 (av1enc, av1parse, av1pay)")
            print("ie: https://github.com/steveseguin/raspberry_ninja/blob/6873b97af02f720b9dc2e5c3ae2e9f02d486ba52/raspberry_pi/installer.sh#L347")
            sys.exit()
        else:
            args.av1 = True
        if args.rpi:
            print("A Raspberry Pi 4 can only handle like 640x360 @ 2 fps when using AV1; not recommended")
    elif args.av1:
        if args.rpi:
            print("A Raspberry Pi 4 can only handle like 640x360 @ 2 fps when using AV1; not recommended")
        if check_plugins(['qsv','videoparsersbad','rsrtp']):
            args.qsv = True
            print("Intel Quick Sync AV1 encoder selected")
        elif check_plugins(['aom','videoparsersbad','rsrtp']):
            args.aom = True
            print("AOM AV1 encoder selected")
        elif check_plugins(['rav1e','videoparsersbad','rsrtp']):
            args.rav1e = True
            print("rav1e AV1 encoder selected; see: https://github.com/xiph/rav1e")
        elif not check_plugins(['videoparsersbad','rsrtp'], True):
            print("You'll probably need to install gst-plugins-rs to use AV1 (av1parse, av1pay)")
            print("ie: https://github.com/steveseguin/raspberry_ninja/blob/6873b97af02f720b9dc2e5c3ae2e9f02d486ba52/raspberry_pi/installer.sh#L347")
            sys.exit()
        else:
            print("No AV1 encoder found")
            sys.exit()

    if args.apple:
        if not check_plugins(['applemedia'], True):
            print("Required media source plugin, applemedia, was not found")
            sys.exit()

        monitor = Gst.DeviceMonitor.new()
        monitor.add_filter("Video/Source", None)
        devices = monitor.get_devices()
        index = -1
        camlook = args.apple.lower()
        appleidx = -1
        appledev = None
        for d in devices:
            index += 1
            cam = d.get_display_name().lower()
            if camlook in cam:
                print("Video device found: "+cam)
                appleidx = index
                appledev = d
                break
        print("")

    elif args.rpi and not args.v4l2 and not args.hdmi and not args.rpicam and not args.z1:
        if check_plugins(['libcamera']):
            args.libcamera = True

        monitor = Gst.DeviceMonitor.new()
        monitor.add_filter("Video/Source", None)
        devices = monitor.get_devices()
        for d in devices:
            cam = d.get_display_name()
            if "-isp" in cam:
                continue
            print("Video device found: "+d.get_display_name())
        print("")

        camlink = [d for d in devices if "Cam Link" in  d.get_display_name()]

        if len(camlink):
            args.camlink = True

        picam = [d for d in devices if "Raspberry Pi Camera Module" in  d.get_display_name()]

        if len(picam):
            args.rpicam = True

        usbcam = [d for d in devices if "USB Vid" in  d.get_display_name()]

        if len(usbcam) and not args.v4l2:
            args.v4l2 = "/dev/video0"

    elif not args.v4l2:
        args.v4l2 = '/dev/video0'

    if args.format:
        args.format = args.format.upper()

    if args.pipeline is not None:
        PIPELINE_DESC = args.pipeline
        print('We assume you have tested your custom pipeline with: gst-launch-1.0 ' + args.pipeline.replace('(', '\\(').replace('(', '\\)'))
    elif args.midi:
        try:
            import rtmidi
        except:
            print("You must install RTMIDI first; pip3 install python-rtmidi")
            sys.exit()
        args.multiviewer = True
        pass
    else:
        pipeline_video_input = ''
        pipeline_audio_input = ''

        if args.bt601:
            args.raw = True

        if args.zerolatency:
            args.novideo = True

        if args.nvidia or args.rpi or args.x264 or args.openh264 or args.omx or args.apple:
            args.h264 = True

        if args.vp8:
            args.h264 = False

        if args.av1:
            args.h264 = False
            
        if args.rtmp and not args.h264:
            args.h264 = True
            
        if args.hevc:
            args.h265 = True

        if args.x265:
            args.h265 = True

        h264 = None
        if args.omx and check_plugins('omxh264enc'):
            h264 = 'omxh264enc'
        if args.omx and check_plugins('avenc_h264_omx'):
            h264 = 'avenc_h264_omx'
        elif args.x264 and check_plugins('x264enc'):
            h264 = 'x264enc'
        elif args.openh264 and check_plugins('openh264enc'):
            h264 = 'openh264enc'
        elif args.apple and check_plugins('vtenc_h264_hw'):
            h264 = 'vtenc_h264_hw'
        elif args.h264:
            if check_plugins('v4l2h264enc'):
                h264 = 'v4l2h264enc'
            elif check_plugins('vtenc_h264_hw'):
                h264 = 'vtenc_h264_hw'
            elif check_plugins('omxh264enc'):
                h264 = 'omxh264enc'
            elif check_plugins('x264enc'):
                h264 = 'x264enc'
            elif check_plugins('openh264enc'):
                h264 = 'openh264enc'
            elif check_plugins('avenc_h264_omx'):
                h264 = 'avenc_h264_omx'
            else:
                print("Couldn't find an h264 encoder")
        elif args.omx or args.x264 or args.openh264 or args.h264:
            print("Couldn't find the h264 encoder")
            
        if h264:
            print("H264 encoder that we will try to use: "+h264)
       
        h265 = None
        if args.h265:
            if args.x265 and check_plugins('x265enc'):
                h265 = 'x265enc'
            elif check_plugins('mpph265enc'):
                h265 = 'mpph265enc'
            elif check_plugins('x265enc'):
                h265 = 'x265enc'
            else:
                print("Couldn't find an h265 encoder, falling back to h264")
                args.h264 = True  # Fallback to h264 if no h265 encoder found
            
            if h265:
                print("H265 encoder that we will try to use: "+h265)
                
        if args.hdmi:
            args.v4l2 = '/dev/v4l/by-id/usb-MACROSILICON_*'
            args.alsa = 'hw:MS2109'
            if args.raw:
                args.width = 1280
                args.height = 720
                args.framerate = 10

        if args.camlink:
            args.v4l2 = '/dev/video0'

        if args.save:
            args.multiviewer = True

        saveAudio = ""
        saveVideo = ""
        if args.save:
            saveAudio = ' ! tee name=saveaudiotee ! queue ! mux.audio_0 saveaudiotee.'
            saveVideo = ' ! tee name=savevideotee ! queue ! mux.video_0 savevideotee.'

        if not args.novideo:

            if args.rpicam:
                needed += ['rpicamsrc']
            elif args.nvidia:
                needed += ['omx', 'nvvidconv']
                if not args.raw:
                    needed += ['nvjpeg']
            elif args.rpi and not args.rpicam:
                needed += ['video4linux2']
                if not args.raw:
                    needed += ['jpeg']

            if args.streamin:
                pass
            elif args.video_pipeline:
                pipeline_video_input = args.video_pipeline
            elif args.test:
                needed += ['videotestsrc']
                pipeline_video_input = 'videotestsrc'
                if args.nvidia:
                    pipeline_video_input = f'videotestsrc ! video/x-raw,width=(int){args.width},height=(int){args.height},format=(string)NV12,framerate=(fraction){args.framerate}/1'
                else:
                    pipeline_video_input = f'videotestsrc ! video/x-raw,width=(int){args.width},height=(int){args.height},type=video,framerate=(fraction){args.framerate}/1'
            elif args.filesrc:
                pipeline_video_input = f'filesrc location="{args.filesrc}" ! decodebin'
            elif args.filesrc2:
                if args.vp9:
                    pipeline_video_input = f'filesrc location="{args.filesrc2}" ! matroskademux ! rtpvp9pay'
                elif args.vp8:
                    pipeline_video_input = f'filesrc location="{args.filesrc2}" ! matroskademux ! rtpvp8pay'
                else:
                    pipeline_video_input = f'filesrc location="{args.filesrc2}" ! qtdemux ! h264parse ! rtph264pay'
            elif args.z1:
                needed += ['thetauvc']
                if args.width>1920 or args.height>960:
                    pipeline_video_input = f'thetauvcsrc mode=4K ! queue ! h264parse ! decodebin'
                else:
                    pipeline_video_input = f'thetauvcsrc mode=2K ! queue ! h264parse ! decodebin'
            elif args.z1passthru:
                needed += ['thetauvc']
                if args.width>1920 or args.height>960:
                    pipeline_video_input = f'thetauvcsrc mode=4K ! queue ! h264parse ! rtph264pay config-interval=-1 aggregate-mode=zero-latency ! application/x-rtp,media=video,encoding-name=H264,payload=96'
                else:
                    pipeline_video_input = f'thetauvcsrc mode=2K ! queue ! h264parse ! rtph264pay config-interval=-1 aggregate-mode=zero-latency ! application/x-rtp,media=video,encoding-name=H264,payload=96'
            elif args.pipein:
                if args.pipein=="auto":
                    pipeline_video_input = f'fdsrc ! decodebin name=ts ts.'
                elif args.pipein=="raw":
                    pipeline_video_input = f'fdsrc ! video/x-raw'
                elif args.pipein=="vp9":
                    pipeline_video_input = f'fdsrc ! matroskademux ! rtpvp9pay'
                elif args.pipein=="vp8":
                    pipeline_video_input = f'fdsrc ! matroskademux ! rtpvp8pay'
                elif args.pipein=="h264":
                    pipeline_video_input = f'fdsrc  ! h264parse ! rtph264pay config-interval=-1 aggregate-mode=zero-latency ! application/x-rtp,media=video,encoding-name=H264,payload=96'
                elif args.pipein=="mpegts":
                    pipeline_video_input = f'fdsrc ! tsdemux name=ts ts. ! h264parse ! rtph264pay config-interval=-1 aggregate-mode=zero-latency ! application/x-rtp,media=video,encoding-name=H264,payload=96'

                else:
                    pipeline_video_input = f'fdsrc ! decodebin'
            elif args.camlink:
                needed += ['video4linux2']
                if args.rpi:
                    pipeline_video_input = f'v4l2src device={args.v4l2} io-mode=2 ! videorate max-rate=30 ! capssetter caps="video/x-raw,format=YUY2,colorimetry=(string)2:4:5:4"'
                else:
                    pipeline_video_input = f'v4l2src device={args.v4l2} io-mode=2 ! capssetter caps="video/x-raw,format=YUY2,colorimetry=(string)2:4:5:4"'

            elif args.rpicam:
                needed += ['rpicamsrc']
                args.rpi = True

                rotate = ""
                if args.rotate:
                    rotate = " rotation="+str(int(args.rotate))
                    args.rotate = 0
                pipeline_video_input = f'rpicamsrc bitrate={args.bitrate}000{rotate} ! video/x-h264,profile=constrained-baseline,width={args.width},height={args.height},framerate=(fraction){args.framerate}/1,level=3.0 ! queue max-size-time=1000000000  max-size-bytes=10000000000 max-size-buffers=1000000 '

            elif args.nvidiacsi:
                needed += ['nvarguscamerasrc']
                args.nvidia = True
                pipeline_video_input = f'nvarguscamerasrc ! video/x-raw(memory:NVMM),width=(int){args.width},height=(int){args.height},format=(string)NV12,framerate=(fraction){args.framerate}/1'
            elif args.apple:
                needed += ['applemedia']
                pipeline_video_input = f'avfvideosrc device-index={appleidx} do-timestamp=true ! video/x-raw'

                if appledev and (args.format is None):
                    formats = supports_resolution_and_format(appledev, args.width, args.height, args.framerate)
                    print(formats)
            elif args.libcamera:

                print("Detecting video devices")
                video_monitor = Gst.DeviceMonitor.new()
                video_monitor.add_filter("Video/Source", None)
                videodevices = video_monitor.get_devices()
                print("devices", videodevices)

                if len(videodevices) > 0:
                    print("\nDetected video sources:")
                    for device in videodevices:
                        print("Device Name:", device.get_display_name())
                    if args.format is None:
                        formats = supports_resolution_and_format(videodevices[0], args.width, args.height, args.framerate)
                        print(formats)
                        if len(formats):
                            args.format = formats[0]
                        elif args.aom:
                            args.format = "I420"
                        else:
                            args.format = "UYVY"

                    print(f"\n >> Default video device selected : {videodevices[0]} /w  {args.format}")

                    needed += ['libcamera']
                    pipeline_video_input = f'libcamerasrc'

                    if args.format == "JPEG":
                        pipeline_video_input += f' ! image/jpeg,width=(int){args.width},height=(int){args.height},type=video,framerate=(fraction){args.framerate}/1'
                        if args.nvidia:
                            pipeline_video_input += ' ! jpegparse ! nvjpegdec ! video/x-raw'
                        elif args.rpi:
                            pipeline_video_input += ' ! jpegparse ! v4l2jpegdec '
                        else:
                            pipeline_video_input += ' ! jpegdec'

                    elif args.format == "H264": # Not going to try to support this right now
                        print("Not support h264 at the moment as an input")
                        pipeline_video_input += f' ! video/x-raw,width=(int){args.width},height=(int){args.height},format=(string)YUY2,framerate=(fraction){args.framerate}/1'
                    else:
                        pipeline_video_input += f' ! video/x-raw,width=(int){args.width},height=(int){args.height},format=(string){args.format},framerate=(fraction){args.framerate}/1'

                elif len(videodevices) == 0:
                    args.novideo = True
                    print("\nNo camera or video source found; disabling video.")

            elif args.v4l2:
                needed += ['video4linux2']
                pipeline_video_input = f'v4l2src device={args.v4l2} io-mode=2 do-timestamp=true'
                if not os.path.exists(args.v4l2):
                    print(f"The video input {args.v4l2} does not exists.")
                    error = True
                elif not os.access(args.v4l2, os.R_OK):
                    print(f"The video input {args.v4l2} does exists, but no persmissions te read.")
                    error = True

                if args.raw:
                    if args.rpi:
                        if args.bt601:
                            pipeline_video_input += f' ! video/x-raw,width=(int){args.width},height=(int){args.height},type=video,framerate=(fraction){args.framerate}/1,colorimetry=(string)bt601'  ## bt601 is another option,etc.
                        else:
                            pipeline_video_input += f' ! video/x-raw,width=(int){args.width},height=(int){args.height},type=video,framerate=(fraction){args.framerate}/1 ! capssetter caps="video/x-raw,format=YUY2,colorimetry=(string)2:4:5:4"'

                    else:
                        pipeline_video_input += f' ! video/x-raw,width=(int){args.width},height=(int){args.height},type=video,framerate=(fraction){args.framerate}/1'

                else:
                    pipeline_video_input += f' ! image/jpeg,width=(int){args.width},height=(int){args.height},type=video,framerate=(fraction){args.framerate}/1'
                    if args.nvidia:
                        pipeline_video_input += ' ! jpegparse ! nvjpegdec ! video/x-raw'
                    elif args.rpi:
                        pipeline_video_input += ' ! jpegparse ! v4l2jpegdec '
                    else:
                        pipeline_video_input += ' ! jpegdec'

            if args.filesrc2:
                pass
            elif args.z1passthru:
                pass
            elif args.pipein and args.pipein != "auto" and args.pipein != "raw": # We are doing a pass-thru with this pip # We are doing a pass-thru with this pipee
                pass
            elif args.h264:
                print("h264 preferred codec is ",h264)
                if h264 == "vtenc_h264_hw":
                    pipeline_video_input += f' ! autovideoconvert ! vtenc_h264_hw name="encoder" qos=true bitrate={args.bitrate}realtime=true allow-frame-reordering=false ! video/x-h264'
                elif args.nvidia:
                    pipeline_video_input += f' ! nvvidconv ! video/x-raw(memory:NVMM) ! omxh264enc bitrate={args.bitrate}000 control-rate="constant" name="encoder" qos=true ! video/x-h264,stream-format=(string)byte-stream'
                elif args.rpicam:
                    pass
                elif h264 == "omxh264enc" and args.rpi:
                    pipeline_video_input += f' ! v4l2convert ! video/x-raw,format=I420{timestampOverlay} ! omxh264enc name="encoder" target-bitrate={args.bitrate}000 qos=true control-rate="constant" ! video/x-h264,stream-format=(string)byte-stream' ## Good for a RPI Zero I guess?
                elif h264 == "x264enc" and args.rpi:
                    pipeline_video_input += f' ! v4l2convert ! video/x-raw,format=I420{timestampOverlay} ! queue max-size-buffers=10 ! x264enc  name="encoder1" bitrate={args.bitrate} speed-preset=1 tune=zerolatency qos=true ! video/x-h264,profile=constrained-baseline,stream-format=(string)byte-stream'
                elif h264 == "openh264enc" and args.rpi:
                    pipeline_video_input += f' ! v4l2convert ! video/x-raw,format=I420{timestampOverlay} ! queue max-size-buffers=10 ! openh264enc  name="encoder" bitrate={args.bitrate}000 complexity=0 ! video/x-h264,profile=constrained-baseline,stream-format=(string)byte-stream'
                elif check_plugins("v4l2h264enc") and args.rpi:
                    if args.format in ["I420", "YV12", "NV12" "NV21", "RGB16", "RGB", "BGR", "RGBA", "BGRx", "BGRA", "YUY2", "YVYU", "UYVY"]:
                        pipeline_video_input += f' ! v4l2convert ! videorate ! video/x-raw{timestampOverlay} ! v4l2h264enc extra-controls="controls,video_bitrate={args.bitrate}000;" qos=true name="encoder2" ! video/x-h264,level=(string)4'
                    else:
                        pipeline_video_input += f' ! v4l2convert ! videorate ! video/x-raw,format=I420{timestampOverlay} ! v4l2h264enc extra-controls="controls,video_bitrate={args.bitrate}000;" qos=true name="encoder2" ! video/x-h264,level=(string)4' ## v4l2h264enc only supports 30fps max @ 1080p on most rpis, and there might be a spike or skipped frame causing the encode to fail; videorating it seems to fix it though
                
                elif h264=="x264enc":
                    pipeline_video_input += f' ! videoconvert{timestampOverlay} ! queue max-size-buffers=10 ! x264enc bitrate={args.bitrate} name="encoder1" speed-preset=1 tune=zerolatency qos=true ! video/x-h264,profile=constrained-baseline'
                elif h264=="avenc_h264_omx":
                    pipeline_video_input += f' ! videoconvert{timestampOverlay} ! queue max-size-buffers=10 ! avenc_h264_omx bitrate={args.bitrate}000 name="encoder" ! video/x-h264,profile=constrained-baseline'
                elif check_plugins("v4l2convert") and check_plugins("omxh264enc"):
                    pipeline_video_input += f' ! v4l2convert{timestampOverlay} ! video/x-raw,format=I420 ! omxh264enc name="encoder" target-bitrate={args.bitrate}000 qos=true control-rate=1 ! video/x-h264,stream-format=(string)byte-stream' ## Good for a RPI Zero I guess?
                elif check_plugins("v4l2convert"):
                    pipeline_video_input += f' ! v4l2convert{timestampOverlay} ! video/x-raw,format=I420 ! {h264} name="encoder" bitrate={args.bitrate}000 ! video/x-h264,stream-format=(string)byte-stream' ## Good for a RPI Zero I guess?
                else:
                    pipeline_video_input += f' ! videoconvert{timestampOverlay} ! video/x-raw,format=I420 ! {h264} name="encoder" bitrate={args.bitrate}000 ! video/x-h264,stream-format=(string)byte-stream' ## Good for a RPI Zero I guess?
                    
                if args.rtmp:
                    pipeline_video_input += f' ! queue ! h264parse'
                else:
                    pipeline_video_input += f' ! queue max-size-time=1000000000  max-size-bytes=10000000000 max-size-buffers=1000000 ! h264parse {saveVideo} ! rtph264pay config-interval=-1 aggregate-mode=zero-latency ! application/x-rtp,media=video,encoding-name=H264,payload=96'

            elif args.aom:
                pipeline_video_input += f' ! videoconvert{timestampOverlay} ! av1enc cpu-used=8 target-bitrate={args.bitrate} name="encoder" usage-profile=realtime qos=true ! av1parse ! rtpav1pay'
            elif args.rav1e:
                pipeline_video_input += f' ! videoconvert{timestampOverlay} ! rav1enc bitrate={args.bitrate}000 name="encoder" low-latency=true error-resilient=true speed-preset=10 qos=true ! av1parse ! rtpav1pay'
            elif args.qsv:
                pipeline_video_input += f' ! videoconvert{timestampOverlay} ! qsvav1enc gop-size=60 bitrate={args.bitrate} name="encoder1" ! av1parse ! rtpav1pay'
            elif args.h265 and h265:
                if h265 == "mpph265enc":
                    # mpph265enc uses bps (bits per second) instead of bitrate
                    # bps takes value in bits per second, so multiply bitrate (kbps) by 1000
                   pipeline_video_input += f' ! videoconvert{timestampOverlay} ! video/x-raw,format=NV12 ! {h265} name="encoder" bps={args.bitrate * 1000} qos=true gop=30 header-mode=1 qp-init=30 qp-max=40 qp-min=18 qp-max-i=35 qp-min-i=18 rc-mode=1 ! video/x-h265,stream-format=(string)byte-stream'

                elif h265 == "x265enc":
                    # x265enc uses bitrate in kbps
                    pipeline_video_input += f' ! videoconvert{timestampOverlay} ! queue max-size-buffers=10 ! {h265} bitrate={args.bitrate} speed-preset=superfast tune=zerolatency key-int-max=30 name="encoder" ! video/x-h265,profile=main,stream-format=byte-stream'
                
                if args.rtmp:
                    pipeline_video_input += f' ! queue ! h265parse'
                else:
                    pipeline_video_input += f' ! queue max-size-time=1000000000 max-size-bytes=10000000000 max-size-buffers=1000000 ! h265parse {saveVideo} ! rtph265pay config-interval=-1 ! application/x-rtp,media=video,encoding-name=H265,payload=96'
            else:
                if args.nvidia:
                    pipeline_video_input += f' ! nvvidconv ! video/x-raw(memory:NVMM) ! omxvp8enc bitrate={args.bitrate}000 control-rate="constant" name="encoder" qos=true ! rtpvp8pay ! application/x-rtp,media=video,encoding-name=VP8,payload=96'
                elif args.rpi:
                    pipeline_video_input += f' ! v4l2convert{timestampOverlay} ! video/x-raw,format=I420 ! queue max-size-buffers=10 ! vp8enc deadline=1 name="encoder" target-bitrate={args.bitrate}000 {saveVideo} ! rtpvp8pay ! application/x-rtp,media=video,encoding-name=VP8,payload=96'
                else:
                    pipeline_video_input += f' ! videoconvert{timestampOverlay} ! queue max-size-buffers=10 ! vp8enc deadline=1 target-bitrate={args.bitrate}000 name="encoder" {saveVideo} ! rtpvp8pay ! application/x-rtp,media=video,encoding-name=VP8,payload=96'

            if args.multiviewer:
                pipeline_video_input += ' ! tee name=videotee '
            else:
                pipeline_video_input += ' ! queue ! sendrecv. '

        if not args.noaudio:
            if args.audio_pipeline:
                pipeline_audio_input = args.audio_pipeline
            elif args.pipein:
                pipeline_audio_input += 'ts. ! queue ! decodebin'
            elif args.test:
                needed += ['audiotestsrc']
                pipeline_audio_input += 'audiotestsrc is-live=true wave=red-noise'

            elif args.pulse:
                needed += ['pulseaudio']
                pipeline_audio_input += f'pulsesrc device={args.pulse}'

            else:
                needed += ['alsa']
                pipeline_audio_input += f'alsasrc device={args.alsa} use-driver-timestamps=TRUE'

            if args.rtmp:
               if check_plugins('fdkaacenc'):
                  pipeline_audio_input += f' ! queue ! audioconvert dithering=0 ! audio/x-raw,rate=48000,channel=1 ! fdkaacenc bitrate=65536 {saveAudio} ! audio/mpeg ! aacparse ! audio/mpeg, mpegversion=4 '
               elif check_plugins('voaacenc'):
                  pipeline_audio_input += f' ! queue ! audioconvert dithering=0 ! audio/x-raw,rate=48000,channel=1 ! voaacenc bitrate=65536 {saveAudio} ! audio/mpeg ! aacparse ! audio/mpeg, mpegversion=4 '
               elif check_plugins('avenc_aac'):
                  pipeline_audio_input += f' ! queue ! audioconvert dithering=0 ! audio/x-raw,rate=48000,channel=1 ! avenc_aac bitrate=65536 {saveAudio} ! audio/mpeg ! aacparse ! audio/mpeg, mpegversion=4 '
               else:
                  pipeline_audio_input = ""
                  printwarn("No AAC encoder found. Will not be encoding audio")
            elif args.zerolatency:
               pipeline_audio_input += f' ! queue max-size-buffers=2 leaky=downstream ! audioconvert ! audioresample quality=0 resample-method=0 ! opusenc bitrate-type=0 bitrate=16000 inband-fec=false audio-type=2051 frame-size=20 {saveAudio} ! rtpopuspay pt=100 ssrc=-1 ! application/x-rtp,media=audio,encoding-name=OPUS,payload=100'
            elif args.vorbis:
               pipeline_audio_input += f' ! queue max-size-buffers=3 leaky=downstream ! audioconvert ! audioresample quality=0 resample-method=0 ! vorbisenc bitrate={args.audiobitrate}000 {saveAudio} ! rtpvorbispay pt=100 ssrc=-1 ! application/x-rtp,media=audio,encoding-name=VORBIS,payload=100'
            else:
               pipeline_audio_input += f' ! queue ! audioconvert ! audioresample quality=0 resample-method=0 ! opusenc bitrate-type=1 bitrate={args.audiobitrate}000 inband-fec=true {saveAudio} ! rtpopuspay pt=100 ssrc=-1 ! application/x-rtp,media=audio,encoding-name=OPUS,payload=100'

            if args.multiviewer: # a 'tee' element may use more CPU or cause extra stuttering, so by default not enabled, but needed to support multiple viewers
                pipeline_audio_input += ' ! tee name=audiotee '
            else:
                pipeline_audio_input += ' ! queue ! sendrecv. '

        pipeline_save = ""
        if args.save:
           pipeline_save = " matroskamux name=mux ! queue ! filesink sync=true location="+str(int(time.time()))+".mkv "

        pipeline_rtmp = ""
        if args.rtmp:
        
            if args.save:
                pipeline_video_input += 'tee name=videotee ! queue ! sendrecv. videotee. ! queue ! '
                saveVideo = f'matroskamux name=mux ! filesink location=saved_video_{int(time.time())}.mkv '

                if not args.noaudio:
                    pipeline_audio_input += 'tee name=audiotee ! queue ! sendrecv. audiotee. ! queue ! mux. '

                
            pipeline_rtmp = "flvmux name=sendrecv ! rtmpsink location='"+args.rtmp+" live=1'"
            PIPELINE_DESC = f'{pipeline_video_input} {pipeline_audio_input} {pipeline_rtmp}'
            print('gst-launch-1.0 ' + PIPELINE_DESC.replace('(', '\\(').replace(')', '\\)'))
            pipe = Gst.parse_launch(PIPELINE_DESC)

            bus = pipe.get_bus()

            bus.add_signal_watch()

            pipe.set_state(Gst.State.PLAYING)

            try:
                loop = GLib.MainLoop()
            except:
                loop = GObject.MainLoop()

            bus.connect("message", on_message, loop)
            try:
                loop.run()
            except:
                loop.quit()

            pipe.set_state(Gst.State.NULL)
            sys.exit(1)
        elif args.whip:
            # Build video and audio pipeline segments
            pipeline_segments = []
            if not args.novideo:
                pipeline_segments.append(pipeline_video_input)
            if not args.noaudio:
                pipeline_segments.append(pipeline_audio_input)
                
            pipeline_desc = ' '.join(pipeline_segments)
            
            whip_client = WHIPClient(pipeline_desc, args)
            if whip_client.start():
                whip_client.stop()
            sys.exit(1)

        elif args.streamin:
            args.h264 = True
            pass
        elif not args.multiviewer:
            if Gst.version().minor >= 18:
                PIPELINE_DESC = f'webrtcbin name=sendrecv latency={args.buffer} async-handling=true bundle-policy=max-bundle {pipeline_video_input} {pipeline_audio_input} {pipeline_save}'
                PIPELINE_DESC = f'webrtcbin name=sendrecv latency={args.buffer} async-handling=true stun-server=stun://stun.cloudflare.com:3478 bundle-policy=max-bundle {pipeline_video_input} {pipeline_audio_input} {pipeline_save}'
            else: ## oldvers v1.16 options  non-advanced options
                PIPELINE_DESC = f'webrtcbin name=sendrecv stun-server=stun://stun.cloudflare.com:3478 bundle-policy=max-bundle {pipeline_video_input} {pipeline_audio_input} {pipeline_save}'
            printc('\ngst-launch-1.0 ' + PIPELINE_DESC.replace('(', '\\(').replace(')', '\\)'), "FFF")
        else:
            PIPELINE_DESC = f'{pipeline_video_input} {pipeline_audio_input} {pipeline_save}'
            printc('\ngst-launch-1.0 ' + PIPELINE_DESC.replace('(', '\\(').replace(')', '\\)'), "FFF")

        if not check_plugins(needed) or error:
            sys.exit(1)

    if args.server:
        server = "&wss="+args.server.split("wss://")[-1]
        args.server = "wss://"+args.server.split("wss://")[-1]
        args.puuid = str(random.randint(10000000,99999999999))
    else:
        args.server = WSS
        server = ""

    if not args.hostname.endswith("/"):
        args.hostname = args.hostname+"/"

    watchURL = args.hostname
    if args.password:
        if args.password == "someEncryptionKey123":
            watchURL += "?"
        else:
            watchURL += "?password="+args.password+"&"
    else:
        watchURL += "?password=false&"

    bold_color = hex_to_ansi("FAF")

    if args.streamin:
        if not args.room:
            printc(f"\n-> You can publish a stream to capture at: {bold_color}{watchURL}push={args.streamin}{server}", "77F")
        else:
            printc(f"\n-> You can publish a stream to capture at: {bold_color}{watchURL}push={args.streamin}{server}&room={args.room}", "77F")
        print("\nAvailable options include --noaudio, --ndiout, --record and --server. See --help for more options.")
    else:
        print("\nAvailable options include --streamid, --bitrate, and --server. See --help for more options. Default video bitrate is 2500 (kbps)")
        if not args.nored and not args.novideo:
            print("Note: Redundant error correction is enabled (default). This will double the sending video bitrate, but handle packet loss better. Use --nored to disable this.")
        if args.room:
            printc(f"\n-> You can view this stream at: {bold_color}{watchURL}view={args.streamid}&room={args.room}&scene{server}\n", "77F")
        else:
            printc(f"\n-> You can view this stream at: {bold_color}{watchURL}view={args.streamid}{server}\n", "7FF")

    args.pipeline = PIPELINE_DESC
    
    c = WebRTCClient(args)
    
    if args.socketout:
        c.setup_socket()
    
    while True:
        try:
            await c.connect()
            res = await c.loop()
        except KeyboardInterrupt:
            print("Ctrl+C detected. Exiting...")
            break
        except:
            await asyncio.sleep(5)
    disableLEDs()
    if c.shared_memory:
        c.shared_memory.close()
        c.shared_memory.unlink()
    sys.exit(res)
    return

if __name__ == "__main__":
    asyncio.run(main())
