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

def handle_unhandled_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    print("!!!  Unhandled exception !!! ", exc_type, exc_value, exc_traceback)
sys.excepthook = handle_unhandled_exception

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
    
def generateHash(input_str, length=None):
    input_bytes = input_str.encode('utf-8')
    sha256_hash = hashlib.sha256(input_bytes).digest()
    if length:
        hash_hex = sha256_hash[:int(length // 2)].hex()
    else:
        hash_hex = sha256_hash.hex()
    return hash_hex

def hex_to_ansi(hex_color):
    # Remove '#' character if present
    hex_color = hex_color.lstrip('#')

    # Convert hex to RGB
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

    # Calculate the nearest ANSI color
    ansi_color = 16 + (36 * int(r / 255 * 5)) + (6 * int(g / 255 * 5)) + int(b / 255 * 5)

    return f"\033[38;5;{ansi_color}m"

def printc(message, color_code=None):
    # ANSI escape code to reset to default text color
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

class WebRTCClient:
    def __init__(self, params):

        self.pipeline = params.pipeline
        self.conn = None
        self.pipe = None
        self.h264 = params.h264
        self.pipein = params.pipein
        self.bitrate = params.bitrate
        self.max_bitrate = params.bitrate
        self.server = params.server
        self.stream_id = params.streamid
        self.room_name = params.room
        self.multiviewer = params.multiviewer
        self.record = params.record
        self.streamin = params.streamin
        self.ndiout = params.ndiout
        self.fdsink = params.fdsink
        self.framebuffer = params.framebuffer
        self.midi = params.midi
        self.nored = params.nored
        self.noqos = params.noqos
        self.midi_thread = None
        self.midiout = None
        self.midiout_ports = None
        self.puuid = None
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
        self.aom = params.aom
        self.av1 = params.av1

        try:
            if self.password:
                parsed_url = urlparse(self.hostname)
                hostname_parts = parsed_url.hostname.split(".")
                result = ".".join(hostname_parts[-2:])
                self.hashcode = generateHash(self.password+result, 6)
        except Exception as E:
            print(E)

        if self.save_file:
            self.pipe = Gst.parse_launch(self.pipeline)
            self.pipe.set_state(Gst.State.PLAYING)
            print("RECORDING TO DISK STARTED")
        
    async def connect(self):
        print("Connecting to handshake server")
        sslctx = ssl.create_default_context()
        self.conn = await websockets.connect(self.server, ssl=sslctx)
        if self.room_name:
            msg = json.dumps({"request":"joinroom","roomid":self.room_name})
            await self.conn.send(msg)
            printwout("joining room")
        elif self.streamin:
            msg = json.dumps({"request":"play","streamID":self.streamin+self.hashcode})
            await self.conn.send(msg)
            printwout("requesting stream")
        else:
            msg = json.dumps({"request":"seed","streamID":self.stream_id+self.hashcode})
            await self.conn.send(msg)
            printwout("seed start")
        
        
    def sendMessage(self, msg): # send message to wss
        if self.puuid:
            msg['from'] = self.puuid
        
        client = None
        if "UUID" in msg and msg['UUID'] in self.clients:
            client = self.clients[msg['UUID']]
        
        msg = json.dumps(msg)
        
        if client and client['send_channel']:
            try:
                client['send_channel'].emit('send-string', msg)
                printout("a message was sent via datachannels: "+msg[:20])
            except Exception as e:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(self.conn.send(msg))
                printwout("a message was sent via websockets 2: "+msg[:20])
        else:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self.conn.send(msg))
            printwout("a message was sent via websockets 1: "+msg[:20])
            #print("sent message wss")
        
#    def needData(self,xx,yy):
 #       print("NEED DATA")
        #buf = Gst.Buffer.new_allocate(self.size)
        #buf.fill(0, self.data)
  #      buffer = Gst.Buffer.new_allocate(None, 100, None)
   #     self.appsrc.emit('push-buffer', buffer)

   # def getBuffer(self):

        #self.appsrc = self.pipe.get_by_name('appsrc')
        #self.appsrc.connect('need-data', self.needData)
    #    while True:
#            print(".")
#            nal_unit = read_next_nal_unit_from_source()
 #           if not nal_unit:
  #              break
            # Create a new buffer with the NAL unit data
#$            nal_unit = 100
     #       buffer = Gst.Buffer.new_allocate(None, 100, None)
  #          buffer.map(Gst.MapFlags.WRITE)
  #          buffer.fill(0, nal_unit)
    #        buffer.unmap()

      #      self.appsrc.emit("push-buffer", buffer)
       #     time.sleep(1001.0/30000)

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
             ## fix for older gstreamer, since nack/fec seems to mess things up?  Not sure if this is breaking something else though.
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
            #trans.set_property("fec-type", GstWebRTC.WebRTCFECType.ULP_RED)
            #trans.set_property("do-nack", True)

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
                
                # if self.streamin:
                    # direction = GstWebRTC.WebRTCRTPTransceiverDirection.RECVONLY
                    # caps = Gst.caps_from_string("application/x-rtp,media=video,encoding-name=VP8/9000,payload=96")
                    # client['webrtc'].emit('add-transceiver', direction, caps)
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
                    print(E)
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
                for ice in msg['candidates']:
                    self.handle_sdp_ice(ice, client["UUID"])
            elif 'candidate' in msg:
                printin("INBOUND ICE SINGLE - DC")
                self.handle_sdp_ice(msg, client["UUID"])
            elif 'pong' in msg: # Supported in v19 of VDO.Ninja
                printin('PONG')
                client['ping'] = 0     
                self.clients[client["UUID"]] = client                
            elif 'bye' in msg: ## v19 of VDO.Ninja
                printin("PEER INTENTIONALLY HUNG UP")
                #self.stop_pipeline(client['UUID'])
            elif 'description' in msg:
                printin("INCOMING SDP - DC")
                if msg['description']['type'] == "offer":
                    self.handle_offer(msg['description'], client['UUID'])
            elif 'midi' in msg:
                printin(msg)
                vdo2midi(msg['midi'])
            elif 'bitrate' in msg:
                printin(msg)
                if client['encoder'] and msg['bitrate']:
                    print("Trying to change bitrate...")
                    if self.aom:
                        pass
                       # client['encoder'].set_property('target-bitrate', int(msg['bitrate'])*1000)
                    else:
                        client['encoder'].set_property('bitrate', int(msg['bitrate'])*1000)
            else:
                printin("MISC DC DATA")
                return

        def vdo2midi(midi):
            #print(midi)
            try:
                if self.midiout == None:
                    self.midiout = rtmidi.MidiOut()

                new_out_port = self.midiout.get_ports() # a bit inefficient, but safe
                if new_out_port != self.midiout_ports:
                    print("New MIDI Out device(s) initializing...")
                    self.midiout_ports = new_out_port
                    #print(self.midiout_ports)
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
                #print("midi processed")
            except Exception as E:
                print(E)
            
        def sendMIDI(data, template):
            #print(data)
            if data:
                 template['midi']['d'] = data[0];
                 #template['midi']['t'] = data[1];  ## since this is real-time midi, i don't see the point in including this
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
                    #template['midi']['t'] = 0 ## I don't see the point in including this currently
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
                if " vp8enc " in self.pipeline:
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
                            pass
                           # client['encoder'].set_property('target-bitrate', int(bitrate*1000))
                        elif client['encoder']:
                            client['encoder'].set_property('bitrate', int(bitrate*1000))
                        elif client['encoder1']:
                            client['encoder1'].set_property('bitrate', int(bitrate))
                        elif client['encoder2']:
                            pass
                            # client['encoder2'].set_property('extra-controls',"controls,video_bitrate="+str(bitrate)+"000;") ## sadly, this is set on startup

                    except Exception as E:
                        print(E)
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
                            pass
                           # client['encoder'].set_property('target-bitrate', int(bitrate*1000))
                        elif client['encoder']:
                            client['encoder'].set_property('bitrate', int(bitrate*1000))
                        elif client['encoder1']:
                            client['encoder1'].set_property('bitrate', int(bitrate))
                        elif client['encoder2']:
                            pass
                            # client['encoder2'].set_property('extra-controls',"controls,video_bitrate="+str(bitrate)+"000;")  ## set on startup; can't change
                    except Exception as E:
                        print(E)


        def new_sample(sink):
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
                    #np_frame_data = np_frame_data[:, :, ::-1]  # Convert from RGB to BGR (OpenCV format)
            
                    # Update shared memory
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
                print(E)
            self.processing = False
            return False

        def on_frame_probe(pad, info):
            buf = info.get_buffer()
            print(f'[{buf.pts / Gst.SECOND:6.2f}]')
            return Gst.PadProbeReturn.OK

        def on_incoming_stream( _, pad):
            print("ON INCOMING AUDIO OR VIDEO STREAM")
            try:
                if Gst.PadDirection.SRC != pad.direction:
                    print("pad direction wrong?")
                    return
    
                caps = pad.get_current_caps()
                name = caps.to_string()
    
                print(name)
                filesink = False
                if "video" in name:

                    if self.ndiout:
                        print("NDI OUT")
                        if "VP8" in name:
                            out = Gst.parse_bin_from_description("queue ! rtpvp8depay ! decodebin ! videoconvert ! queue ! video/x-raw,format=UYVY ! ndisinkcombiner name=mux1 ! ndisink ndi-name='"+self.streamin+"'", True)
                        elif "H264" in name:
                            #depay.set_property("request-keyframe", True)
                            out = Gst.parse_bin_from_description("queue ! rtph264depay ! h264parse ! queue max-size-buffers=0 max-size-time=0 ! decodebin ! queue max-size-buffers=0 max-size-time=0 ! videoconvert ! queue max-size-buffers=0 max-size-time=0 ! video/x-raw,format=UYVY ! ndisinkcombiner name=mux1 ! queue ! ndisink ndi-name='"+self.streamin+"'", True)
                    elif self.fdsink: ## send raw data to ffmpeg or something I guess, using the stdout?
                        print("FD SINK OUT")
                        if "VP8" in name:
                            out = Gst.parse_bin_from_description("queue ! rtpvp8depay ! decodebin ! queue max-size-buffers=0 max-size-time=0 ! videoconvert ! queue max-size-buffers=0 max-size-time=0 ! video/x-raw,format=BGR ! fdsink", True)
                        elif "H264" in name:
                            #depay.set_property("request-keyframe", True)
                            out = Gst.parse_bin_from_description("queue ! rtph264depay ! h264parse ! openh264dec ! videoconvert ! video/x-raw,format=BGR ! queue max-size-buffers=0 max-size-time=0 ! fdsink", True)
                    elif self.framebuffer: ## send raw data to ffmpeg or something I guess, using the stdout?
                        print("APP SINK OUT")
                        if "VP8" in name:
                            out = Gst.parse_bin_from_description("queue ! rtpvp8depay ! queue max-size-buffers=0 max-size-time=0 ! decodebin ! videoconvert ! video/x-raw,format=BGR ! queue max-size-buffers=2 leaky=downstream ! appsink name=appsink", True)
                        elif "H264" in name:
                            #depay.set_property("request-keyframe", True)
                            ## LEAKY = 2 + Max-Buffer=1 means we will only keep the last most recent frame queued up for the appsink; older frames will get dropped, since we will prioritize latency.  You can change this of course.
                            out = Gst.parse_bin_from_description("queue ! rtph264depay ! h264parse ! queue max-size-buffers=0 max-size-time=0 ! openh264dec ! videoconvert ! video/x-raw,format=BGR ! queue max-size-buffers=2 leaky=downstream ! appsink name=appsink", True)
                    else:
                        # filesink = self.pipe.get_by_name('mux2') ## WIP
                        if filesink:
                            print("Video being added after audio")
                            if "VP8" in name:
                                out = Gst.parse_bin_from_description("queue ! rtpvp8depay", True)
                            elif "H264" in name:
                                #depay.set_property("request-keyframe", True)
                                out = Gst.parse_bin_from_description("queue ! rtph264depay ! h264parse", True)
                        
                        else:
                            print("video being saved...")
                            if "VP8" in name:
                                out = Gst.parse_bin_from_description("queue ! rtpvp8depay !  webmmux  name=mux1 ! filesink sync=false location="+self.streamin+"_"+str(int(time.time()))+"_video.webm", True)
                            elif "H264" in name:
                                #depay.set_property("request-keyframe", True)
                                out = Gst.parse_bin_from_description("queue ! rtph264depay ! h264parse ! mp4mux  name=mux1 ! queue ! filesink sync=true location="+self.streamin+"_"+str(int(time.time()))+"_video.mp4", True)
    
#                    print(Gst.debug_bin_to_dot_data(out, Gst.DebugGraphDetails.ALL))
                    self.pipe.add(out)
                    out.sync_state_with_parent()
                    sink = out.get_static_pad('sink')
                    if filesink:
                        out.link(filesink)

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
                        appsink.connect("new-sample", new_sample)

                elif "audio" in name:
                    if self.ndiout:
                        out = Gst.parse_bin_from_description("queue ! fakesink", True)
                        pass  #WIP 
                    elif self.fdsink:
                        out = Gst.parse_bin_from_description("queue ! fakesink", True)
                        pass # WIP
                    elif self.framebuffer:
                        out = Gst.parse_bin_from_description("queue ! fakesink", True)
                        pass # WIP
                    else:
                        # filesink = self.pipe.get_by_name('mux1') ## WIP
                        if filesink:
                            print("Audio being added after video")
                            if "OPUS" in name:
                                out = Gst.parse_bin_from_description("queue rtpopusdepay ! opusparse ! audio/x-opus,channel-mapping-family=0,channels=2,rate=48000", True)
                        else:
                            print("audio being saved...") 
                            if "OPUS" in name:
                                out = Gst.parse_bin_from_description("queue ! rtpopusdepay ! opusparse ! audio/x-opus,channel-mapping-family=0,channels=2,rate=48000 ! mp4mux name=mux2 ! queue ! filesink sync=true location="+self.streamin+"_"+str(int(time.time()))+"_audio.mp4", True)
        
                    self.pipe.add(out)
                    out.sync_state_with_parent()
                    # self.pipe.sync_children_states()
    
                    sink = out.get_static_pad('sink')
    
                    if filesink:
                        out.link(filesink)
                    pad.link(sink)
                    print("success audio?")

            except Exception as E:
                print("============= ERROR =========")
                print(E)
                exc_type, exc_obj, exc_tb = sys.exc_info()
                fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                print(exc_type, fname, exc_tb.tb_lineno)


        def on_incoming_stream_2( _, pad):
            print("ON INCOMING STREAM !! ************* ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ .......$$$$$$$")
            try:
                if Gst.PadDirection.SRC != pad.direction:
                    print("pad direction wrong?")
                    return
            except Exception as E:
                print(E)
                return

            caps = pad.get_current_caps()
            name = caps.to_string()

            print(name)

            if "video" in name:
                q = Gst.ElementFactory.make('queue')
                q.set_property("max-size-bytes",0)
                q.set_property("max-size-buffers",0)
                q.set_property("max-size-time",0)
                q.set_property("flush-on-eos",True)
                sink = Gst.ElementFactory.make('filesink', "videosink")  # record inbound stream to file

                if "H264" in name:
                    sink.set_property("location", str(time.time())+'.h264')
                    depay = Gst.ElementFactory.make('rtph264depay', "depay")
                    depay.set_property("request-keyframe", True)  
                    p = Gst.ElementFactory.make('h264parse', "parse")
                    caps = Gst.ElementFactory.make("capsfilter", "caps")
                    caps.set_property("caps", Gst.Caps.from_string("video/x-h264,stream-format=byte-stream"))
                elif "VP8" in name: ## doesn't work for some reason yet?  stalls on trying to save
                    sink.set_property("location", str(time.time())+'.vp8')
                    depay = Gst.ElementFactory.make('rtpvp8depay', "depay")
                    depay.set_property("request-keyframe", True)
                    p = None
                    caps = Gst.ElementFactory.make("capsfilter", "caps")
                    caps.set_property('caps', Gst.Caps.from_string("video/x-vp8"))
                else:
                    print("UNKNOWN FORMAT - saving as raw RTP stream")
                    sink.set_property("location", str(time.time())+'.unknown')
                    depay = Gst.ElementFactory.make('queue', "depay")
                    p = None
                    caps = Gst.ElementFactory.make("queue", "caps")


                self.pipe.add(caps)
                self.pipe.add(q)
                self.pipe.add(depay)
                if p:
                    self.pipe.add(p)
                self.pipe.add(sink)
                self.pipe.sync_children_states()

                pad.link(q.get_static_pad('sink'))
                q.link(depay)
                if p:
                    depay.link(p)
                    p.link(caps)
                else:
                    depay.link(caps)
                caps.link(sink)
            elif "audio" in name:
                q = Gst.ElementFactory.make('queue')
                q.set_property("max-size-bytes",0)
                q.set_property("max-size-buffers",0)
                q.set_property("max-size-time",0)
                q.set_property("flush-on-eos",True)

                caps = Gst.ElementFactory.make("capsfilter", "audiocaps")
                caps.set_property('caps', Gst.Caps.from_string('audio/x-opus'))

                decode = Gst.ElementFactory.make("opusdec", "opusdec")

                sink = Gst.ElementFactory.make('filesink', "audiosink")  # record inbound stream to file
                sink.set_property("location", str(time.time())+'.pcm')

                depay = Gst.ElementFactory.make('rtpopusdepay', "audiodepay")

                self.pipe.add(q)
                self.pipe.add(depay)
                self.pipe.add(decode)
                self.pipe.add(sink)
                self.pipe.add(caps)
                self.pipe.sync_children_states()

                pad.link(q.get_static_pad('sink'))
                q.link(depay)
                depay.link(caps)
                caps.link(decode)
                decode.link(sink)

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
            

        client['webrtc'] = self.pipe.get_by_name('sendrecv')
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
            client['webrtc'].set_property('stun-server', "stun://stun4.l.google.com:19302") ## older versions of gstreamer might break with this
            client['webrtc'].set_property('turn-server', 'turn://vdoninja:IchBinSteveDerNinja@www.turn.vdo.ninja:3478') # temporarily hard-coded
            try:
                client['webrtc'].set_property('latency', self.buffer)
            except:
                pass
            self.pipe.add(client['webrtc'])

            if self.h264:
                direction = GstWebRTC.WebRTCRTPTransceiverDirection.RECVONLY
                caps = Gst.caps_from_string("application/x-rtp,media=video,encoding-name=H264,payload=102,clock-rate=90000,packetization-mode=(string)1");
                tcvr = client['webrtc'].emit('add-transceiver', direction, caps)
                if Gst.version().minor > 18:
                    tcvr.set_property("codec-preferences",caps) ## supported as of around June 2021 in gstreamer for answer side?


        elif (not self.multiviewer) and client['webrtc']:
            pass
        else:
            client['webrtc'] = Gst.ElementFactory.make("webrtcbin", client['UUID'])
            client['webrtc'].set_property('bundle-policy', 'max-bundle') 
            client['webrtc'].set_property('stun-server', "stun://stun4.l.google.com:19302")  ## older versions of gstreamer might break with this
            client['webrtc'].set_property('turn-server', 'turn://vdoninja:IchBinSteveDerNinja@www.turn.vdo.ninja:3478') # temporarily hard-coded
            try:
                client['webrtc'].set_property('latency', self.buffer)
            except:
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
                #client['webrtc'].set_state(Gst.State.READY)
                self.midi_thread = threading.Thread(target=midi2vdo, args=(self.midi,))
                self.midi_thread.start()
                print(self.midi_thread)
                print("MIDI THREAD STARTED")

        try:
            client['webrtc'].connect('notify::ice-connection-state', on_ice_connection_state)
            client['webrtc'].connect('notify::connection-state', on_connection_state)
            client['webrtc'].connect('notify::signaling-state', on_signaling_state)
                
        except Exception as e:
            print(e)
            pass
            
        if self.streamin:
            client['webrtc'].connect('pad-added', on_incoming_stream)
            client['webrtc'].connect('on-ice-candidate', send_ice_remote_candidate_message)
            client['webrtc'].connect('on-data-channel', on_data_channel)
        else:
            client['webrtc'].connect('on-ice-candidate', send_ice_local_candidate_message)
            client['webrtc'].connect('on-negotiation-needed', on_negotiation_needed)
            client['webrtc'].connect('on-new-transceiver', on_new_tranceiver)
            #client['webrtc'].connect('on-data-channel', on_data_channel)
 
        try:
            if not self.streamin:
                trans = client['webrtc'].emit("get-transceiver",0)
                if trans is not None:
                    if not self.nored:
                        trans.set_property("fec-type", GstWebRTC.WebRTCFECType.ULP_RED)
                        print("FEC ENABLED")
                    trans.set_property("do-nack", True)
                    print("SEND NACKS ENABLED")

        except Exception as E:
            print(E)


        if not started and self.pipe.get_state(0)[1] is not Gst.State.PLAYING:
            self.pipe.set_state(Gst.State.PLAYING)
                           
        #client['webrtc'].connect('on-ice-candidate', send_ice_local_candidate_message) ## already set this!
        client['webrtc'].sync_state_with_parent()

        if not self.streamin and not client['send_channel']:
            channel = client['webrtc'].emit('create-data-channel', 'sendChannel', None)
            on_data_channel(client['webrtc'], channel)

#        try: ## not working yet
 #           if self.pipein and not self.appsrc:
  #              self.appsrc = self.pipe.get_by_name('appsrc')
            #    self.appsrc.connect('need-data', self.needData)

   #             self.emitter = threading.Thread(target=self.getBuffer)
    #            self.emitter.start()
     #           print("EMITTER THREAD STARTED")
      #  except Exception as E:
       #     print(E)

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
#            print ('Received answer:\n%s' % sdp)
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
        print(text)
        msg = {'description': {'type': 'answer', 'sdp': text}, 'UUID': client['UUID'], 'session': client['session']}
        self.sendMessage(msg)
            
    def handle_offer(self, msg, UUID):
        print("HANDLE SDP OFFER")
        print("-----")
        client = self.clients[UUID]
        if not client or not client['webrtc']:
            return
        if 'sdp' in msg:
            print("INCOMDING OFFER SDP TYPE: "+msg['type']);
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
        print("START PIPE")
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
                    print("Resetting existing pipe and p2p connection.");
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
                
                if 'vector' in msg:
                    print("Try with --password false (here) and &password=false (sender side) instead, as encryption isn't supported it seems with your setup")
                    continue
                elif 'from' in msg:
                    if self.puuid==None:
                        self.puuid = str(random.randint(10000000,99999999))
                    if msg['from'] == self.puuid:
                        continue
                    UUID = msg['from']
                    if ('UUID' in msg) and (msg['UUID'] != self.puuid):
                        continue
                elif 'UUID' in msg:
                    if (self.puuid != None) and (self.puuid != msg['UUID']):
                        continue
                    UUID = msg['UUID']
                else:
                    if self.room_name:
                        if 'request' in msg:
                            if msg['request'] == 'listing':
                                if self.streamin:
                                    msg = json.dumps({"request":"play","streamID":self.streamin+self.hashcode}) ## we're just going to view a stream
                                    printwout(msg)
                                    await self.conn.send(msg)
                                else:
                                    msg = jsoin.dumps({"request":"seed","streamID":self.stream_id+self.hashcode}) ## we're just going to publish a stream
                                    printwout("seed start")
                                    await self.conn.send(msg)
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
                    msg = msg['description']
                    if 'type' in msg:
                        if msg['type'] == "offer":
                            await self.start_pipeline(UUID)
                            self.handle_offer(msg, UUID)
                        elif msg['type'] == "answer":
                            self.handle_sdp_ice(msg, UUID)
                elif 'candidates' in msg:
                    print("ice candidates BUNDLE via WSS")
                    if type(msg['candidates']) is list:
                        for ice in msg['candidates']:
                            self.handle_sdp_ice(ice, UUID)
                    else:
                        print("Try with &password=false / --password=false instead, as encryption isn't supported currently")
                elif 'candidate' in msg:
                    print("ice candidate SINGLE via WSS")
                    self.handle_sdp_ice(msg, UUID)
                elif 'request' in msg:
                    print("REQUEST via WSS: ", msg['request'])
                    if 'offerSDP' in  msg['request']:
                        await self.start_pipeline(UUID)
                    elif msg['request'] == "play":
                        if self.puuid==None:
                            self.puuid = str(random.randint(10000000,99999999))
                        if 'streamID' in msg:
                            if msg['streamID'] == self.stream_id+self.hashcode:
                                await self.start_pipeline(UUID)
            except websockets.ConnectionClosed:
                print("WEB SOCKETS CLOSED; retrying in 5s");
                await asyncio.sleep(5)
                continue
            except Exception as E:
                print(E);
               
        return 0


def check_plugins(needed):
    missing = list(filter(lambda p: Gst.Registry.get().find_plugin(p) is None, needed))
    if len(missing):
        print('Missing gstreamer plugins:', missing)
        return False
    return True

def on_message(bus: Gst.Bus, message: Gst.Message, loop):
    mtype = message.type
    """
        Gstreamer Message Types and how to parse
        https://lazka.github.io/pgi-docs/Gst-1.0/flags.html#Gst.MessageType
    """
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
        # self.pipe.recalculate_latency() 
        
    elif mtype == Gst.MessageType.ELEMENT:
        print("ELEMENT")

    return True


WSS="wss://wss.vdo.ninja:443"

async def main():

    error = False
    parser = argparse.ArgumentParser()
    parser.add_argument('--streamid', type=str, default=str(random.randint(1000000,9999999)), help='Stream ID of the peer to connect to')
    parser.add_argument('--room', type=str, default=None, help='optional - Room name of the peer to join')
    parser.add_argument('--rtmp', type=str, default=None, help='Use RTMP instead; pass the rtmp:// publishing address here to use')
    parser.add_argument('--whip', type=str, default=None, help='Use WHIP output instead; pass the https://whip.publishing/address here to use')
    parser.add_argument('--server', type=str, default=None, help='Handshake server to use, eg: "wss://wss.vdo.ninja:443"')
    parser.add_argument('--bitrate', type=int, default=2500, help='Sets the video bitrate; kbps. If error correction (red) is on, the total bandwidth used may be up to 2X higher than the bitrate')
    parser.add_argument('--audiobitrate', type=int, default=64, help='Sets the audio bitrate; kbps.')
    parser.add_argument('--width', type=int, default=1920, help='Sets the video width. Make sure that your input supports it.')
    parser.add_argument('--height', type=int, default=1080, help='Sets the video height. Make sure that your input supports it.')
    parser.add_argument('--framerate', type=int, default=30, help='Sets the video framerate. Make sure that your input supports it.')
    parser.add_argument('--test', action='store_true', help='Use test sources.')
    parser.add_argument('--hdmi', action='store_true', help='Try to setup a HDMI dongle')
    parser.add_argument('--camlink', action='store_true', help='Try to setup an Elgato Cam Link')
    parser.add_argument('--z1', action='store_true', help='Try to setup a Theta Z1 360 camera')
    parser.add_argument('--z1passthru', action='store_true', help='Try to setup a Theta Z1 360 camera, but do not transcode')
    parser.add_argument('--v4l2', type=str, default=None, help='Sets the V4L2 input device.')
    parser.add_argument('--libcamera', action='store_true',  help='Use libcamera as the input source')
    parser.add_argument('--rpicam', action='store_true', help='Sets the RaspberryPi CSI input device. If this fails, try --rpi --raw or just --raw instead.')
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
    parser.add_argument('--rpi', action='store_true', help='Creates a pipeline optimised for raspberry pi hadware.')
    parser.add_argument('--multiviewer', action='store_true', help='Allows for multiple viewers to watch a single encoded stream; will use more CPU and bandwidth.')
    parser.add_argument('--noqos', action='store_true', help='Do not try to automatically reduce video bitrate if packet loss gets too high. The default will reduce the bitrate if needed.')
    parser.add_argument('--nored', action='store_true', help='Disable error correction redundency for transmitted video. This may reduce the bandwidth used by half, but it will be more sensitive to packet loss')
    parser.add_argument('--novideo', action='store_true', help='Disables video input.')
    parser.add_argument('--noaudio', action='store_true', help='Disables audio input.')
    parser.add_argument('--led', action='store_true', help='Enable GPIO pin 12 as an LED indicator light; for Raspberry Pi.')
    parser.add_argument('--pipeline', type=str, help='A full custom pipeline')
    parser.add_argument('--record',  type=str, help='Specify a stream ID to record to disk. System will not publish a stream when enabled.') ### Doens't work correctly yet. might be a gstreamer limitation.
    parser.add_argument('--save', action='store_true', help='Save a copy of the outbound stream to disk. Publish Live + Store the video.')
    parser.add_argument('--midi', action='store_true', help='Transparent MIDI bridge mode; no video or audio.')
    parser.add_argument('--filesrc', type=str, default=None,  help='Provide a media file (local file location) as a source instead of physical device; it can be a transparent webm or whatever. It will be transcoded, which offers the best results.')
    parser.add_argument('--filesrc2', type=str, default=None,  help='Provide a media file (local file location) as a source instead of physical device; it can be a transparent webm or whatever. It will not be transcoded, so be sure its encoded correctly. Specify if --vp8 or --vp9, else --h264 is assumed.')
    parser.add_argument('--pipein', type=str, default=None, help='Pipe a media stream in as the input source. Pass `auto` for auto-decode,pass codec type for pass-thru (mpegts,h264,vp8,vp9), or use `raw`'); 
    parser.add_argument('--ndiout',  type=str, help='VDO.Ninja to NDI output; requires the NDI Gstreamer plugin installed')
    parser.add_argument('--fdsink',  type=str, help='VDO.Ninja to the stdout pipe; common for piping data between command line processes')
    parser.add_argument('--framebuffer', type=str, help='VDO.Ninja to local frame buffer; performant and Numpy/OpenCV friendly')
    parser.add_argument('--debug', action='store_true', help='Show added debug information from Gsteamer and other aspects of the app')
    parser.add_argument('--buffer',  type=int, default=200, help='The jitter buffer latency in milliseconds; default is 200ms. (gst +v1.18)')
    parser.add_argument('--password', type=str, nargs='?', default=None, required=False, const='', help='Partial password support. If not used, passwords will be off. If a blank value is passed, it will use the default system password. If you pass a value, it will use that value for the pass. No added encryption support however. Works for publishing to vdo.ninja/alpha/ (v24) currently')
    parser.add_argument('--hostname', type=str, default='https://vdo.ninja/alpha/', help='Your URL for vdo.ninja, if self-hosting the website code')

    args = parser.parse_args()
    
    Gst.init(None)
    Gst.debug_set_active(False)
    
    if args.debug:
        Gst.debug_set_default_threshold(2)
    else:
        Gst.debug_set_default_threshold(0)
     
    if Gst.Registry.get().find_plugin("rpicamsrc"):
        args.rpi=True
    elif Gst.Registry.get().find_plugin("nvvidconv"):
        args.nvidia=True
        if Gst.Registry.get().find_plugin("nvarguscamerasrc"):
            if not args.nvidiacsi and not args.record:
                print("\nTip: If using the Nvidia CSI camera, you'll want to use --nvidiacsi to enable it.\n")

    PIPELINE_DESC = ""

    needed = ["nice", "webrtc", "dtls", "srtp", "rtp", "sctp", "rtpmanager"]
    
    h264 = list(filter(lambda p: Gst.Registry.get().find_plugin(p) is None, ['x264', 'openh264']))

    if args.password == None:
        pass
    elif args.password.lower() in ["", "true", "1", "on"]:
        args.password = "someEncryptionKey123"
    elif args.password.lower() in ["false", "0", "off"]:
        args.password = None
    
    

    if args.aom:
        if not check_plugins(['aom','videoparsersbad','rsrtp']):
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
        elif not check_plugins(['videoparsersbad','rsrtp']):
            print("You'll probably need to install gst-plugins-rs to use AV1 (av1parse, av1pay)")
            print("ie: https://github.com/steveseguin/raspberry_ninja/blob/6873b97af02f720b9dc2e5c3ae2e9f02d486ba52/raspberry_pi/installer.sh#L347")
            sys.exit()
        else:
            print("No AV1 encoder found")
            sys.exit()

    if 'openh264' not in h264:
        h264 = "openh264"
    elif 'x264' not in h264:
        h264 = "x264"
    else:
        h264 = False

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
        
    audiodevices = [] 
    if not (args.test or args.noaudio):     
        monitor = Gst.DeviceMonitor.new()
        monitor.add_filter("Audio/Source", None)
        #monitor.start()
        audiodevices = monitor.get_devices()

    if not args.alsa and not args.noaudio and not args.pulse and not args.test and not args.pipein:
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
            #args.noaudio = True
            print("\nDetected audio sources:")
            for i, d in enumerate(audiodevices):
                print("  - ",audiodevices[i].get_display_name(), audiodevices[i].get_property("internal-name"), audiodevices[i].get_properties().get_value("alsa.card"), audiodevices[i].get_properties().get_value("is-default"))
                args.alsa = 'hw:'+str(audiodevices[i].get_properties().get_value("alsa.card"))+',0'
            print()
            default = None
            for d in audiodevices:
                props = d.get_properties()
                for e in range(int(props.n_fields())):
#                    print(props.nth_field_name(e),"=",props.get_value(props.nth_field_name(e)))
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
                #print("======================")
#        sys.exit()
        print()

    if args.rpicam:
        print("Please note: If rpicamsrc cannot be found, use --libcamera instead")
        if not check_plugins(['rpicamsrc']):
            print("rpicamsrc was not found. using just --rpi instead")
            print()
            args.raw = True
            args.rpi = True
            args.rpicam = False
            
 
    if args.rpi and not args.v4l2 and not args.hdmi and not args.rpicam and not args.z1:
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

        if args.nvidia or args.rpi or args.x264 or args.openh264:
            args.h264 = True

        if args.vp8:
            args.h264 = False

        if args.av1:
            args.h264 = False
           
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
       
        if args.ndiout:
            needed += ['ndi']
            if not args.record:
                args.streamin = args.ndiout
            else:
                args.streamin = args.record
        elif args.fdsink:
            args.streamin = args.fdsink
        elif args.framebuffer:
            if not np:
                print("You must install Numpy for this to work.\npip3 install numpy");
                sys.exit()
            args.streamin = args.framebuffer
        elif args.record:
            args.streamin = args.record
        else:
            args.streamin = False

        if not args.novideo:

            if not (args.nvidia or args.rpi) and args.h264:
                if args.x264:
                    needed += ['x264']
                elif args.openh264:
                    needed += ['openh264']
                elif args.omx:
                    needed += ['omx']
                elif h264:
                    needed += ['h264']
                elif args.rpicam:
                    needed += ['rpicamsrc']
                else:
                    print("Is there an H264 encoder installed?")

            if args.nvidia:
                needed += ['omx', 'nvvidconv']
                if not args.raw:
                    needed += ['nvjpeg']
            elif args.rpi and not args.rpicam:
                needed += ['video4linux2']
                if args.x264:
                    needed += ['x264']
                elif args.openh264:
                    needed += ['openh264']
                elif args.omx:
                    needed += ['omx']
                elif h264:
                    needed += [h264]
                else:
                    print("Is there an H264 encoder installed?")

                if not args.raw:
                    needed += ['jpeg']


            # THE VIDEO INPUT
            if args.streamin:
                pass
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
#                elif args.z1: ## theta z1
 #                   pipeline_video_input = f'appsrc emit-signals=True name="appsrc" block=true format=time caps="video/x-h264,stream-format=(string)byte-stream,framerate=(fraction)30000/1001,profile=constrained-baseline" ! queue max-size-time=1000000000  max-size-bytes=10000000000 max-size-buffers=1000000 ! h264parse! rtph264pay config-interval=-1 aggregate-mode=zero-latency ! application/x-rtp,media=video,encoding-name=H264,payload=96'
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

            elif args.libcamera:
                needed += ['libcamera']
                pipeline_video_input = f'libcamerasrc'
                pipeline_video_input += f' ! video/x-raw,width=(int){args.width},height=(int){args.height},format=(string)YUY2,framerate=(fraction){args.framerate}/1'
#                pipeline_video_input += f' ! video/x-raw,width=(int)1280,height=(int)720,framerate=(fraction)30/1,format=(string)YUY2'
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
                # H264
                if args.nvidia:
                    pipeline_video_input += f' ! nvvidconv ! video/x-raw(memory:NVMM) ! omxh264enc bitrate={args.bitrate}000 control-rate="constant" name="encoder" qos=true ! video/x-h264,stream-format=(string)byte-stream'
                elif args.rpicam:
                    pass
                elif args.rpi:
                    if args.omx:
                        pipeline_video_input += f' ! v4l2convert ! video/x-raw,format=I420 ! omxh264enc name="encoder" target-bitrate={args.bitrate}000 qos=true control-rate="constant" ! video/x-h264,stream-format=(string)byte-stream' ## Good for a RPI Zero I guess?
                    elif args.x264:
                        pipeline_video_input += f' ! v4l2convert ! video/x-raw,format=I420 ! queue max-size-buffers=10 ! x264enc  name="encoder1" bitrate={args.bitrate} speed-preset=1 tune=zerolatency qos=true ! video/x-h264,profile=constrained-baseline,stream-format=(string)byte-stream'
                    elif args.openh264:
                        pipeline_video_input += f' ! v4l2convert ! video/x-raw,format=I420 ! queue max-size-buffers=10 ! openh264enc  name="encoder" bitrate={args.bitrate}000 complexity=0 ! video/x-h264,profile=constrained-baseline,stream-format=(string)byte-stream'
                    else:
                        pipeline_video_input += f' ! v4l2convert ! videorate ! video/x-raw,format=I420 ! v4l2h264enc extra-controls="controls,video_bitrate={args.bitrate}000;" qos=true name="encoder2" ! video/x-h264,level=(string)4' ## v4l2h264enc only supports 30fps max @ 1080p on most rpis, and there might be a spike or skipped frame causing the encode to fail; videorating it seems to fix it though

                    ## pipeline_video_input += f' ! v4l2convert ! video/x-raw,format=I420 ! omxh264enc ! video/x-h264,stream-format=(string)byte-stream' ## Good for a RPI Zero I guess?
                elif h264=="x264":
                    pipeline_video_input += f' ! videoconvert ! queue max-size-buffers=10 ! x264enc bitrate={args.bitrate} name="encoder1" speed-preset=1 tune=zerolatency qos=true ! video/x-h264,profile=constrained-baseline'
                elif h264=="openh264":
                    pipeline_video_input += f' ! videoconvert ! queue max-size-buffers=10 ! openh264enc bitrate={args.bitrate}000 name="encoder" complexity=0 ! video/x-h264,profile=constrained-baseline'
                else:
                    pipeline_video_input += f' ! v4l2convert ! video/x-raw,format=I420 ! omxh264enc name="encoder" target-bitrate={args.bitrate}000 qos=true control-rate=1 ! video/x-h264,stream-format=(string)byte-stream' ## Good for a RPI Zero I guess?
                    
                if args.rtmp:
                    pipeline_video_input += f' ! queue ! h264parse {saveVideo}'
                else:
                    pipeline_video_input += f' ! queue max-size-time=1000000000  max-size-bytes=10000000000 max-size-buffers=1000000 ! h264parse {saveVideo} ! rtph264pay config-interval=-1 aggregate-mode=zero-latency ! application/x-rtp,media=video,encoding-name=H264,payload=96'

            elif args.aom: 
                pipeline_video_input += f' ! videoconvert ! av1enc cpu-used=8 target-bitrate={args.bitrate} name="encoder" usage-profile=realtime qos=true ! av1parse ! rtpav1pay'
            elif args.rav1e:
                pipeline_video_input += f' ! videoconvert ! rav1enc bitrate={args.bitrate}000 name="encoder" low-latency=true error-resilient=true speed-preset=10 qos=true ! av1parse ! rtpav1pay'
            elif args.qsv:
                pipeline_video_input += f' ! videoconvert ! qsvav1enc gop-size=60 bitrate={args.bitrate} name="encoder1" ! av1parse ! rtpav1pay'

            else:
                # VP8
                if args.nvidia:
                    pipeline_video_input += f' ! nvvidconv ! video/x-raw(memory:NVMM) ! omxvp8enc bitrate={args.bitrate}000 control-rate="constant" name="encoder" qos=true ! rtpvp8pay ! application/x-rtp,media=video,encoding-name=VP8,payload=96'
                elif args.rpi:
                    pipeline_video_input += f' ! v4l2convert ! video/x-raw,format=I420 ! queue max-size-buffers=10 ! vp8enc deadline=1 name="encoder" target-bitrate={args.bitrate}000 {saveVideo} ! rtpvp8pay ! application/x-rtp,media=video,encoding-name=VP8,payload=96'
                # need to add an nvidia vp8 hardware encoder option.
                else:
                    pipeline_video_input += f' ! videoconvert ! queue max-size-buffers=10 ! vp8enc deadline=1 target-bitrate={args.bitrate}000 name="encoder" {saveVideo} ! rtpvp8pay ! application/x-rtp,media=video,encoding-name=VP8,payload=96'
                    
            if args.multiviewer:
                pipeline_video_input += ' ! tee name=videotee '
            else:
                pipeline_video_input += ' ! queue ! sendrecv. '

        if not args.noaudio:
            if args.pipein:
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
               pipeline_audio_input += f' ! queue ! audioconvert dithering=0 ! audio/x-raw,rate=48000,channel=1 ! fdkaacenc bitrate=65536 {saveAudio} ! audio/mpeg ! aacparse ! audio/mpeg, mpegversion=4 '
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
            pipeline_whip = 'whipsink name=sendrecv whip-endpoint="'+args.whip+'"'
            PIPELINE_DESC = f'{pipeline_video_input} {pipeline_audio_input} {pipeline_whip}'
            print('gst-launch-1.0 ' + PIPELINE_DESC.replace('(', '\\(').replace(')', '\\)'))
            pipe = Gst.parse_launch(PIPELINE_DESC)

            bus = pipe.get_bus()

            bus.add_signal_watch()

            pipe.set_state(Gst.State.PLAYING)

            try:
                loop = GLib.MainLoop()
            except:
                loop = GObject.MainLoop()

            #bus.connect("message", on_message, loop)
            try:
                loop.run()
            except Exception as E:
                print(E)
                loop.quit()

            pipe.set_state(Gst.State.NULL)
            sys.exit(1)


        elif args.streamin:
            args.h264 = True
            pass
        elif not args.multiviewer:
            if Gst.version().minor >= 18:
                PIPELINE_DESC = f'webrtcbin name=sendrecv latency={args.buffer} stun-server=stun://stun4.l.google.com:19302 bundle-policy=max-bundle {pipeline_video_input} {pipeline_audio_input} {pipeline_save}'
            else:
                PIPELINE_DESC = f'webrtcbin name=sendrecv stun-server=stun://stun4.l.google.com:19302 bundle-policy=max-bundle {pipeline_video_input} {pipeline_audio_input} {pipeline_save}'
            print('gst-launch-1.0 ' + PIPELINE_DESC.replace('(', '\\(').replace(')', '\\)'))
        else:
            PIPELINE_DESC = f'{pipeline_video_input} {pipeline_audio_input} {pipeline_save}'
            print('Partial pipeline used: ' + PIPELINE_DESC.replace('(', '\\(').replace(')', '\\)'))
            
        
        if not check_plugins(needed) or error:
            sys.exit(1)

    if args.server:
        server = "&wss="+args.server.split("wss://")[-1];
        args.server = "wss://"+args.server.split("wss://")[-1]
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
    
    if args.streamin:
        if not args.room:
            print(f"\nYou can publish a stream to capture at: {watchURL}push={args.streamin}{server}")
        else:
            print(f"\nYou can publish a stream to capture at: {watchURL}push={args.streamin}{server}&room={args.room}")
        print("\nAvailable options include --noaudio, --ndiout, --record and --server. See --help for more options.")
    elif args.room:
        print("\nAvailable options include --streamid, --bitrate, and --server. See --help for more options. Default bitrate is 2500 (kbps)")
        print(f"\nYou can view this stream at: {watchURL}view={args.streamid}&room={args.room}&scene{server}");
    else:
        print("\nAvailable options include --streamid, --bitrate, and --server. See --help for more options. Default bitrate is 2500 (kbps) ")
        print(f"\nYou can view this stream at: {watchURL}view={args.streamid}{server}")

    args.pipeline = PIPELINE_DESC
    c = WebRTCClient(args)
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
