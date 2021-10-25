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
gi.require_version('Gst', '1.0')
from gi.repository import Gst
gi.require_version('GstWebRTC', '1.0')
from gi.repository import GstWebRTC
gi.require_version('GstSdp', '1.0')
from gi.repository import GstSdp
                               
class WebRTCClient:
    def __init__(self, stream_id, server, multiviewer, record):
        self.conn = None
        self.pipe = None
        self.server = server
        self.stream_id = stream_id
        self.multiviewer = multiviewer
        self.record = record
        self.puuid = None
        self.clients = {}
        
    async def connect(self):
        sslctx = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
        self.conn = await websockets.connect(self.server, ssl=sslctx)
        
        if args.record:
            msg = json.dumps({"request":"play","streamID":args.record})
            await self.conn.send(msg)
        else:
            msg = json.dumps({"request":"seed","streamID":self.stream_id})
            await self.conn.send(msg)
        
        
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
                print("sent via datachannels")
            except Exception as e:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(self.conn.send(msg))
                #print("sent message wss")
        else:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self.conn.send(msg))
            #print("sent message wss")
        
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
            msg = {'description': {'type': 'offer', 'sdp': text}, 'UUID': client['UUID'], 'session': client['session'], 'streamID':self.stream_id}
            self.sendMessage(msg)

        def on_negotiation_needed(element):
            print("ON NEGO NEEDED")
            promise = Gst.Promise.new_with_change_func(on_offer_created, element, None)
            element.emit('create-offer', None, promise)

        def send_ice_local_candidate_message(_, mlineindex, candidate):
            icemsg = {'candidates': [{'candidate': candidate, 'sdpMLineIndex': mlineindex}], 'session':client['session'], 'type':'local', 'UUID':client['UUID']}
            self.sendMessage(icemsg)
            
        def send_ice_remote_candidate_message(_, mlineindex, candidate):
            icemsg = {'candidates': [{'candidate': candidate, 'sdpMLineIndex': mlineindex}], 'session':client['session'], 'type':'remote', 'UUID':client['UUID']}
            self.sendMessage(icemsg)

        
        def on_signaling_state(p1, p2):
            print("ON SIGNALING STATE CHANGE: {}".format(client['webrtc'].get_property(p2.name)))

        def on_ice_connection_state(p1, p2):
            print("ON ICE CONNECTION STATE CHANGE: {}".format(client['webrtc'].get_property(p2.name)))

        def on_connection_state(p1, p2):
            print("on_connection_state")
            
            if (client['webrtc'].get_property(p2.name)==2): # connected
                print("PEER CONNECTION ACTIVE")
                promise = Gst.Promise.new_with_change_func(on_stats, client['webrtc'], None) # check stats
                client['webrtc'].emit('get-stats', None, promise)
                
                # if self.record:
                    # direction = GstWebRTC.WebRTCRTPTransceiverDirection.RECVONLY
                    # caps = Gst.caps_from_string("application/x-rtp,media=video,encoding-name=VP8/9000,payload=96")
                    # client['webrtc'].emit('add-transceiver', direction, caps)
                if not self.record and not client['send_channel']:
                    channel = client['webrtc'].emit('create-data-channel', 'sendChannel', None)
                    on_data_channel(client['webrtc'], channel)
                
                if client['timer'] == None:
                    client['ping'] = 0
                    client['timer'] = threading.Timer(3, pingTimer).start()
                    self.clients[client["UUID"]] = client
                    
            elif (client['webrtc'].get_property(p2.name)>=4): # closed/failed , but this won't work unless Gstreamer / LibNice support it -- which isn't the case in most versions.
                print("PEER CONNECTION DISCONNECTED")
                self.stop_pipeline(client['UUID'])     
            else:
                print("PEER CONNECTION STATE {}".format(client['webrtc'].get_property(p2.name)))

        def pingTimer():
            if not client['send_channel']:
                threading.Timer(3, pingTimer).start()
                print("data channel not setup yet")
                return
                
            if client['ping'] < 4:
                client['ping'] += 1
                self.clients[client["UUID"]] = client
                try:
                    client['send_channel'].emit('send-string', '{"ping":"'+str(time.time())+'"}')
                    print("PINGED")
                except Exception as E:
                    print(E)
                    print("PING FAILED")
                threading.Timer(3, pingTimer).start()
            else:
                print("NO HEARTBEAT")
                self.stop_pipeline(client['UUID'])
                
        def on_data_channel(webrtc, channel):
            print("ON DATA CHANNEL")
            if channel is None:
                print('DATA CHANNEL: NOT AVAILABLE')
            else:
                print('DATA CHANNEL SETUP')                               
            channel.connect('on-open', on_data_channel_open)
            channel.connect('on-error', on_data_channel_error)
            channel.connect('on-close', on_data_channel_close)
            channel.connect('on-message-string', on_data_channel_message)

        def on_data_channel_error(channel):
            print('DATA CHANNEL: ERROR')

        def on_data_channel_open(channel):
            print('DATA CHANNEL: OPENED')
            client['send_channel'] = channel
            self.clients[client["UUID"]] = client
            if self.record:
                msg = {"audio":False, "video":True, "UUID": client["UUID"]}
                self.sendMessage(msg)

        def on_data_channel_close(channel):
            print('DATA CHANNEL: CLOSE')

        def on_data_channel_message(channel, msg_raw):
            try:
                msg = json.loads(msg_raw)
            except:
                return
            if 'candidates' in msg:
                print("inbound ice")
                for ice in msg['candidates']:
                    self.handle_sdp(ice, client["UUID"])
            elif 'pong' in msg: # Supported in v19 of VDO.Ninja
                print('PONG:', msg['pong'])
                client['ping'] = 0     
                self.clients[client["UUID"]] = client                
            elif 'bye' in msg: ## v19 of VDO.Ninja
                print("PEER INTENTIONALLY HUNG UP")
            else:
                return

        def on_stats(promise, abin, data):
            promise.wait()
            stats = promise.get_reply()
            stats.foreach(foreach_stats)
            
        def foreach_stats(field_id, stats):
            if stats.get_name() == "remote-inbound-rtp":
                print(stats.to_string())
            else:
                print(stats.to_string())

       
        
        def on_incoming_decodebin_stream(_, pad): # If daring to capture inbound video; support not assured at this point.
            print("ON INCOMING")
            if not pad.has_current_caps():
                print (pad, 'has no caps, ignoring')
                return

            caps = pad.get_current_caps()
            name = caps.to_string()
            
            print(caps)
            print(name)
            
            print("--------------")
            if name.startswith('video'):
                q = Gst.ElementFactory.make('queue')
                conv = Gst.ElementFactory.make('videoconvert')
    #            sink = Gst.ElementFactory.make('filesink', "fsink")  # record inbound stream to file
                sink = Gst.ElementFactory.make('autovideosink')
    #            sink.set_property("location", str(time.time())+'.mkv')
                self.pipe.add(q)
                self.pipe.add(conv)
                self.pipe.add(sink)
                self.pipe.sync_children_states()
                pad.link(q.get_static_pad('sink'))
                q.link(conv)
                conv.link(sink)
            elif name.startswith('audio'):
                q = Gst.ElementFactory.make('queue')
                conv = Gst.ElementFactory.make('audioconvert')
                resample = Gst.ElementFactory.make('audioresample')
                sink = Gst.ElementFactory.make('autoaudiosink')
                self.pipe.add(q)
                self.pipe.add(conv)
                self.pipe.add(resample)
                self.pipe.add(sink)
                self.pipe.sync_children_states()
                pad.link(q.get_static_pad('sink'))
                q.link(conv)
                conv.link(resample)
                resample.link(sink)

        def on_incoming_stream( _, pad):
            print("ON INCOMING STREAM !! ************* ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ .......$$$$$$$")
            try:
                if Gst.PadDirection.SRC != pad.direction:
                    return
            except:
                return
            print("INCOMING STREAM")
            
            print("INCOMING STREAM !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            queue = Gst.ElementFactory.make('queue')
            queue.connect('pad-added', on_incoming_decodebin_stream)
            self.pipe.add(queue)
            queue.sync_state_with_parent()
            client['webrtc'].link(queue)
        
        print("creating a new webrtc bin")
        
        started = True
        if not self.pipe:
            print("loading pipe")
           
            if self.record:
                self.pipe = Gst.Pipeline.new('decode-pipeline')
            else:
                print(PIPELINE_DESC)
                self.pipe = Gst.parse_launch(PIPELINE_DESC)
            print(self.pipe)
            started = False
            
            
        if self.record:
            client['webrtc'] = Gst.ElementFactory.make("webrtcbin", client['UUID'])
            #client['webrtc'].set_property('bundle-policy', 'max-bundle') 
            client['webrtc'].set_property('stun-server', "stun-server=stun://stun4.l.google.com:19302")
            client['webrtc'].set_property('turn-server', 'turn://vdoninja:IchBinSteveDerNinja@www.turn.vdo.ninja:3478') # temporarily hard-coded
            self.pipe.add(client['webrtc'])
            
            #direction = GstWebRTC.WebRTCRTPTransceiverDirection.SENDRECV
            #caps = Gst.caps_from_string("application/x-rtp,media=video,encoding-name=VP8/9000,payload=96")
            #client['webrtc'].emit('add-transceiver', direction, caps)
            
            client['qv'] = None
            client['qa'] = None
        elif not self.multiviewer:
            client['webrtc'] = self.pipe.get_by_name('sendrecv')
            client['qv'] = None
            client['qa'] = None
        else:
            client['webrtc'] = Gst.ElementFactory.make("webrtcbin", client['UUID'])
            client['webrtc'].set_property('bundle-policy', 'max-bundle') 
            client['webrtc'].set_property('stun-server', "stun-server=stun://stun4.l.google.com:19302")
            client['webrtc'].set_property('turn-server', 'turn://vdoninja:IchBinSteveDerNinja@www.turn.vdo.ninja:3478') # temporarily hard-coded
            self.pipe.add(client['webrtc'])
            
            atee = self.pipe.get_by_name('audiotee')
            vtee = self.pipe.get_by_name('videotee')
            
            client['qv'] = None
            client['qa'] = None
            
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
            
        try:
            client['webrtc'].connect('notify::ice-connection-state', on_ice_connection_state)
            client['webrtc'].connect('notify::connection-state', on_connection_state)
            client['webrtc'].connect('notify::signaling-state', on_signaling_state)
                
        except Exception as e:
            print(e)
            pass
            
        if self.record:
            client['webrtc'].connect('pad-added', on_incoming_stream)
            client['webrtc'].connect('on-data-channel', on_data_channel)
            client['webrtc'].connect('on-ice-candidate', send_ice_remote_candidate_message)
        else:
            client['webrtc'].connect('on-ice-candidate', send_ice_local_candidate_message)
            client['webrtc'].connect('on-negotiation-needed', on_negotiation_needed)
            
        if not started and self.pipe.get_state(0)[1] is not Gst.State.PLAYING:
            self.pipe.set_state(Gst.State.PLAYING)
            
        client['webrtc'].sync_state_with_parent()
        self.clients[client["UUID"]] = client
        
    def handle_sdp(self, msg, UUID):
        print("HANDLE SDP")
        client = self.clients[UUID]
        if not client or not client['webrtc']:
            return
        if 'sdp' in msg:
            msg = msg
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
            candidate = msg['candidate']
            sdpmlineindex = msg['sdpMLineIndex']
            client['webrtc'].emit('add-ice-candidate', sdpmlineindex, candidate)

    def on_answer_created(self, promise, _, client):
        print("ON ANSWER CREATED")
        promise.wait()
        reply = promise.get_reply()
        answer = reply.get_value('answer')
        if not answer:
            return
        promise = Gst.Promise.new()
        client['webrtc'].emit('set-local-description', answer, promise)
        promise.interrupt()
        print("SEND SDP ANSWER")
        print(answer)
        text = answer.sdp.as_text()
        msg = {'description': {'type': 'answer', 'sdp': text}, 'UUID': client['UUID'], 'session': client['session']}
        self.sendMessage(msg)
            
    async def handle_offer(self, msg, UUID):
        print("HANDLE SDP OFFER")
        client = self.clients[UUID]
        if not client or not client['webrtc']:
            return
        if 'sdp' in msg:
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
        
    async def start_pipeline(self, UUID):
        print("START PIPE")
        if self.multiviewer:
            await self.createPeer(UUID)
        else:
            for uid in self.clients:
                if uid != UUID:
                    self.stop_pipeline(uid)
                    break
            if self.pipe:
                self.pipe.set_state(Gst.State.NULL)
                self.pipe = None
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
            
        if self.pipe:
            if len(self.clients)==0:
                self.pipe.set_state(Gst.State.NULL)
                self.pipe = None
            
    async def loop(self):
        assert self.conn
        print("WSS CONNECTED")
        async for message in self.conn:
            msg = json.loads(message)
            if 'from' in msg:
                UUID = msg['from']
            elif 'UUID' in msg:
                if (self.puuid != None) and (self.puuid != msg['UUID']):
                    continue
                UUID = msg['UUID']
            else:
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
                else:
                    print("sessions don't match")

            if 'description' in msg:
                msg = msg['description']
                if 'type' in msg:
                    if msg['type'] == "offer":
                        await self.start_pipeline(UUID)
                        await self.handle_offer(msg, UUID)
                    elif msg['type'] == "answer":
                        self.handle_sdp(msg, UUID)
            elif 'candidates' in msg:
                for ice in msg['candidates']:
                    self.handle_sdp(ice, UUID)

            elif 'request' in msg:
                if 'offerSDP' in  msg['request']:
                    await self.start_pipeline(UUID)
                elif msg['request'] == 'play':
                    if self.puuid==None:
                        self.puuid = str(random.randint(10000000,99999999))
                    if 'streamID' in msg:
                        if msg['streamID'] == self.stream_id:
                            await self.start_pipeline(UUID)
           
        return 0


def check_plugins(needed):
    missing = list(filter(lambda p: Gst.Registry.get().find_plugin(p) is None, needed))
    if len(missing):
        print('Missing gstreamer plugins:', missing)
        return False
    return True

WSS="wss://wss.vdo.ninja:443"

if __name__=='__main__':
    Gst.init(None)
    # Gst.debug_set_active(True)
    # Gst.debug_set_default_threshold(3)
    error = False
    parser = argparse.ArgumentParser()
    parser.add_argument('--streamid', type=str, default=str(random.randint(1000000,9999999)), help='Stream ID of the peer to connect to')
    parser.add_argument('--server', type=str, default=WSS, help='Handshake server to use, eg: "wss://wss.vdo.ninja:443"')
    parser.add_argument('--bitrate', type=int, default=4000, help='Sets the video bitrate. This is not adaptive, so packet loss and insufficient bandwidth will cause frame loss')
    parser.add_argument('--width', type=int, default=1920, help='Sets the video width. Make sure that your input supports it.')
    parser.add_argument('--height', type=int, default=1080, help='Sets the video height. Make sure that your input supports it.')
    parser.add_argument('--framerate', type=int, default=30, help='Sets the video framerate. Make sure that your input supports it.')
    parser.add_argument('--test', action='store_true', help='Use test sources.')
    parser.add_argument('--hdmi', action='store_true', help='Try to setup a HDMI dongle')
    parser.add_argument('--v4l2',type=str, default='/dev/video0', help='Sets the V4L2 input device.')
    parser.add_argument('--rpicam', action='store_true', help='Sets the RaspberryPi input device.')
    parser.add_argument('--nvidiacsi', action='store_true', help='Sets the input to the nvidia csi port.')
    parser.add_argument('--alsa', type=str, default='default', help='Use alsa audio input.')
    parser.add_argument('--pulse', type=str, help='Use pulse audio (or pipewire) input.')
    parser.add_argument('--raw', action='store_true', help='Opens the V4L2 device with raw capabilities.')
    parser.add_argument('--h264', action='store_true', help='For PC, instead of VP8, use x264.')
    parser.add_argument('--nvidia', action='store_true', help='Creates a pipeline optimised for nvidia hardware.')
    parser.add_argument('--rpi', action='store_true', help='Creates a pipeline optimised for raspberry pi hadware.')
    parser.add_argument('--multiviewer', action='store_true', help='Allows for multiple viewers to watch a single encoded stream; will use more CPU and bandwidth.')
    parser.add_argument('--novideo', action='store_true', help='Disables video input.')
    parser.add_argument('--noaudio', action='store_true', help='Disables audio input.')
    parser.add_argument('--pipeline', type=str, help='A full custom pipeline')
    parser.add_argument('--record', type=str, help='A remote stream ID to record to disk') ### Doens't work correctly yet. might be a gstreamer limitation.
    
    args = parser.parse_args()
     
    if Gst.Registry.get().find_plugin("rpicamsrc"):
        args.rpi=True
    elif Gst.Registry.get().find_plugin("nvvidconv"):
        args.nvidia=True
    
    needed = ["nice", "webrtc", "dtls", "srtp", "rtp", "sctp", "rtpmanager"]
    
    if args.pipeline is not None:
        PIPELINE_DESC = args.pipeline
        print('We assume you have tested your custom pipeline with: gst-launch-1.0 ' + args.pipeline.replace('(', '\\(').replace('(', '\\)'))
    else:
        pipeline_video_input = ''
        pipeline_audio_input = ''

        if args.hdmi:
            args.v4l2 = '/dev/v4l/by-id/usb-MACROSILICON_USB_Video-video-index0'
            args.alsa = 'hw:MS2109'
            if args.raw:
                args.width = 1280
                args.height = 720
                args.framerate = 10

        if not args.novideo:
            if args.nvidia:
                needed += ['omx', 'nvvidconv']
                if not args.raw:
                    needed += ['nvjpeg']

            elif args.rpi and not args.rpicam:
                needed += ['x264', 'video4linux2']
                if not args.raw:
                    needed += ['jpeg']

            if not (args.nvidia or args.rpi) and args.h264:
                needed += ['x264']

            # THE VIDEO INPUT
            if args.test:
                needed += ['videotestsrc']
                pipeline_video_input = 'videotestsrc'
                if args.nvidia:
                    pipeline_video_input = f'videotestsrc ! video/x-raw,width=(int){args.width},height=(int){args.height},format=(string)NV12,framerate=(fraction){args.framerate}/1'
                else:
                    pipeline_video_input = f'videotestsrc ! video/x-raw,width=(int){args.width},height=(int){args.height},type=video,framerate=(fraction){args.framerate}/1'

            elif args.rpicam:
                needed += ['rpicamsrc']
                args.rpi = True
                pipeline_video_input = f'rpicamsrc bitrate={args.bitrate}000 ! video/x-h264,profile=constrained-baseline,width={args.width},height={args.height},level=3.0 ! queue'

            elif args.nvidiacsi:
                # TODO:
                # needed += ['nvarguscamerasrc']
                args.nvidia = True
                pipeline_video_input = f'nvarguscamerasrc ! video/x-raw(memory:NVMM),width=(int){args.width},height=(int){args.height},format=(string)NV12,framerate=(fraction){args.framerate}/1'

            elif args.v4l2:
                needed += ['video4linux2']
                pipeline_video_input = f'v4l2src device={args.v4l2} io-mode=2'
                if not os.path.exists(args.v4l2):
                    print(f"The video input {args.v4l2} does not exists.")
                    error = True
                elif not os.access(args.v4l2, os.R_OK):
                    print(f"The video input {args.v4l2} does exists, but no persmissions te read.")
                    error = True

                if args.raw:
                    if args.rpi:
                        pipeline_video_input += f' ! video/x-raw,width=(int){args.width},height=(int){args.height},type=video,framerate=(fraction){args.framerate}/1 ! capssetter caps="video/x-raw,format=YUY2,colorimetry=(string)2:4:5:4"'  ## bt601 is another option,etc.
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

            if args.h264 or args.nvidia or args.rpi:
                # H264
                if args.nvidia:
                    pipeline_video_input += f' ! nvvidconv ! video/x-raw(memory:NVMM) ! omxh264enc bitrate={args.bitrate}000 ! video/x-h264,stream-format=(string)byte-stream'
                elif args.rpicam:
                    pass
                elif args.rpi:
                    if args.width>1280: ## x264enc works at 1080p30, but only for static scenes with a bitrate of around 2500 or less.
                        width = 1280  ## 720p60 is more accessible with the PI4, versus 1080p30.  
                        height = 720
                    else:
                        width = args.width
                        height = args.height
                    pipeline_video_input += f' ! v4l2convert ! video/x-raw,format=I420,width=(int){width},height=(int){height} ! x264enc bitrate={args.bitrate} speed-preset=1 tune=zerolatency qos=true ! video/x-h264,stream-format=(string)byte-stream'
                    ## pipeline_video_input += f' ! v4l2convert ! video/x-raw,format=I420 ! omxh264enc ! video/x-h264,stream-format=(string)byte-stream' ## Good for a RPI Zero I guess?
                else:
                    pipeline_video_input += f' ! videoconvert ! x264enc bitrate={args.bitrate} speed-preset=ultrafast tune=zerolatency key-int-max=15 ! video/x-h264,profile=constrained-baseline'
                    
                if args.multiviewer:
                    pipeline_video_input += ' ! h264parse ! rtph264pay config-interval=-1 ! application/x-rtp,media=video,encoding-name=H264,payload=96 ! tee name=videotee '
                else:
                    pipeline_video_input += ' ! h264parse ! rtph264pay config-interval=-1 ! application/x-rtp,media=video,encoding-name=H264,payload=96 ! queue ! sendrecv.'

            else:
                # VP8
                if args.multiviewer:
                    pipeline_video_input += f' ! videoconvert ! vp8enc deadline=1 target-bitrate={args.bitrate}000 ! rtpvp8pay ! application/x-rtp,media=video,encoding-name=VP8,payload=97 ! tee name=videotee '
                else:
                    pipeline_video_input += f' ! videoconvert ! vp8enc deadline=1 target-bitrate={args.bitrate}000 ! rtpvp8pay ! application/x-rtp,media=video,encoding-name=VP8,payload=97 ! queue ! sendrecv.'

        if not args.noaudio:
            if args.test:
                needed += ['audiotestsrc']
                pipeline_audio_input += 'audiotestsrc is-live=true wave=red-noise'

            elif args.pulse:
                needed += ['pulseaudio']
                pipeline_audio_input += f'pulsesrc device={args.pulse}'

            else:
                needed += ['alsa']
                pipeline_audio_input += f'alsasrc device={args.alsa}'
                
            if args.multiviewer: # a 'tee' element may use more CPU or cause extra stuttering, so by default not enabled, but needed to support multiple viewers
                pipeline_audio_input += ' ! audioconvert ! audioresample ! queue ! opusenc ! rtpopuspay ! queue ! application/x-rtp,media=audio,encoding-name=OPUS,payload=96 ! tee name=audiotee '
            else:
                pipeline_audio_input += ' ! audioconvert ! audioresample ! queue ! opusenc ! rtpopuspay ! queue ! application/x-rtp,media=audio,encoding-name=OPUS,payload=96 ! queue ! sendrecv.'

        if args.record:
            pass
        elif not args.multiviewer:
            PIPELINE_DESC = f'webrtcbin name=sendrecv stun-server=stun://stun4.l.google.com:19302 bundle-policy=max-bundle {pipeline_video_input} {pipeline_audio_input}'
            print('gst-launch-1.0 ' + PIPELINE_DESC.replace('(', '\\(').replace(')', '\\)'))
        else:
            PIPELINE_DESC = f'{pipeline_video_input} {pipeline_audio_input}'
            print('Partial pipeline used: ' + PIPELINE_DESC.replace('(', '\\(').replace(')', '\\)'))
            
        if not check_plugins(needed) or error:
            sys.exit(1)

    print("\nAvailable options include --streamid, --bitrate, and --server. Default bitrate is 4000 (kbps)")
    print(f"\nYou can view this stream at: https://vdo.ninja/?password=false&view={args.streamid}");

    c = WebRTCClient(args.streamid, args.server, args.multiviewer, args.record)
    asyncio.get_event_loop().run_until_complete(c.connect())
    res = asyncio.get_event_loop().run_until_complete(c.loop())
    sys.exit(res)
