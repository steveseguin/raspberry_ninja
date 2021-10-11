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

# Gst.debug_set_active(True)
# Gst.debug_set_default_threshold(3)                                   
class WebRTCClient:
    def __init__(self, peer_id, server):
        self.conn = None
        self.pipe = None
        self.webrtc = None
        self.UUID = None
        self.session = None
        self.peer_id = peer_id
        self.server = server
        self.puuid = None
        self.send_channel = None
        self.timer = None
        self.ping = 0             

    async def connect(self):
        sslctx = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
        self.conn = await websockets.connect(self.server, ssl=sslctx)
        msg = json.dumps({"request":"seed","streamID":self.peer_id})
        await self.conn.send(msg)

    def sendMessage(self, msg):
        if self.puuid:
            msg['from'] = self.puuid
        msg = json.dumps(msg)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(self.conn.send(msg))
    
    def on_offer_created(self, promise, _, __): 
        print("ON OFFER CREATED")
        promise.wait()
        reply = promise.get_reply()
        offer = reply.get_value('offer')
        promise = Gst.Promise.new()
        self.webrtc.emit('set-local-description', offer, promise)
        promise.interrupt()
        print("SEND SDP OFFER")
        text = offer.sdp.as_text()
        msg = {'description': {'type': 'offer', 'sdp': text}, 'UUID': self.UUID, 'session': self.session, 'streamID':self.peer_id}
        self.sendMessage(msg)

    def on_negotiation_needed(self, element):
        print("ON NEGO NEEDED")
        promise = Gst.Promise.new_with_change_func(self.on_offer_created, element, None)
        element.emit('create-offer', None, promise)

    def create_answer(self):
        promise = Gst.Promise.new_with_change_func(self.on_answer_created, self.webrtc, None)
        self.webrtc.emit('create-answer', None, promise)

    def on_answer_created(self, promise, _, __):
        print("ON ANSWER CREATED")
        promise.wait()
        reply = promise.get_reply()
        answer = reply.get_value('answer')
        promise = Gst.Promise.new()
        self.webrtc.emit('set-local-description', answer, promise)
        promise.interrupt()
        print("SEND SDP ANSWER")
        text = answer.sdp.as_text()
        msg = {'description': {'type': 'answer', 'sdp': text, 'UUID': self.UUID, 'session': self.session}}
                        
        self.sendMessage(msg)

    def send_ice_candidate_message(self, _, mlineindex, candidate):
        icemsg = {'candidates': [{'candidate': candidate, 'sdpMLineIndex': mlineindex}], 'session':self.session, 'type':'local', 'UUID':self.UUID}
        self.sendMessage(icemsg)

    def on_signaling_state(self, p1, p2):
        print("ON SIGNALING STATE CHANGE: {}".format(self.webrtc.get_property(p2.name)))

    def on_ice_connection_state(self, p1, p2):
        print("ON ICE CONNECTION STATE CHANGE: {}".format(self.webrtc.get_property(p2.name)))

    def on_connection_state(self, p1, p2):
        if (self.webrtc.get_property(p2.name)==2): # connected
            print("PEER CONNECTION ACTIVE")
            promise = Gst.Promise.new_with_change_func(self.on_stats, self.webrtc, None) # check stats
            self.webrtc.emit('get-stats', None, promise)
            self.send_channel = self.webrtc.emit('create-data-channel', 'sendChannel', None)
            self.on_data_channel(self.webrtc, self.send_channel)
            if self.timer == None:
                self.timer = threading.Timer(3, self.pingTimer).start()
        elif (self.webrtc.get_property(p2.name)>=4): # closed/failed , but this won't work unless Gstreamer / LibNice support it -- which isn't the case in most versions.
            print("PEER CONNECTION DISCONNECTED")
        else:
            print("PEER CONNECTION STATE {}".format(self.webrtc.get_property(p2.name)))

    def on_stats(self, promise, abin, data):
        promise.wait()
        stats = promise.get_reply()
        stats.foreach(self.foreach_stats)

    def foreach_stats(self, field_id, stats):
        if stats.get_name() == "remote-inbound-rtp":
            print(stats.to_string())
        else:
            print(stats.to_string())

    def on_signaling_state(self, p1, p2):
        print("ON SIGNALING STATE CHANGE: {}".format(self.webrtc.get_property(p2.name)))

    def on_ice_connection_state(self, p1, p2):
        print("ON ICE CONNECTION STATE CHANGE: {}".format(self.webrtc.get_property(p2.name)))

    def on_connection_state(self, p1, p2):
        if (self.webrtc.get_property(p2.name)==2): # connected
            print("PEER CONNECTION ACTIVE")
            promise = Gst.Promise.new_with_change_func(self.on_stats, self.webrtc, None) # check stats
            self.webrtc.emit('get-stats', None, promise)
            self.send_channel = self.webrtc.emit('create-data-channel', 'sendChannel', None)
            
            if not self.send_channel:
                print("ERROR: CANNOT CREATE DATA CHANNEL")
            else:
                self.ping = 0       
                self.on_data_channel(self.webrtc, self.send_channel)
                if self.timer == None:
                    self.timer = threading.Timer(3, self.pingTimer).start()
        elif (self.webrtc.get_property(p2.name)>=4): # closed/failed , but this won't work unless Gstreamer / LibNice support it -- which isn't the case in most versions.
            print("PEER CONNECTION DISCONNECTED")
            self.stop_pipeline()                    
        else:
            print("PEER CONNECTION STATE {}".format(self.webrtc.get_property(p2.name)))

    def on_stats(self, promise, abin, data):
        promise.wait()
        stats = promise.get_reply()
        stats.foreach(self.foreach_stats)

    def foreach_stats(self, field_id, stats):
        #print(stats)
        if stats.get_name() == "remote-inbound-rtp":
            print(stats.to_string())
        else:
            print(stats.to_string())

    def on_incoming_decodebin_stream(self, _, pad): # If daring to capture inbound video; support not assured at this point.
        print("ON INCOMING")
        if not pad.has_current_caps():
            print (pad, 'has no caps, ignoring')
            return

        caps = pad.get_current_caps()
        name = caps.to_string()
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

    def on_incoming_stream(self, _, pad):
        print("ON INCOMING STREAM")
        try:
            if Gst.PadDirection.SRC != pad.direction:
                return
        except:
            return
        print("INCOMING STREAM")
        decodebin = Gst.ElementFactory.make('decodebin')
        decodebin.connect('pad-added', self.on_incoming_decodebin_stream)
        self.pipe.add(decodebin)
        decodebin.sync_state_with_parent()
        self.webrtc.link(decodebin)

    def start_pipeline(self):
        print("START PIPE")
        if self.pipe:
            self.pipe.set_state(Gst.State.NULL)
        self.pipe = Gst.parse_launch(PIPELINE_DESC)
        self.webrtc = self.pipe.get_by_name('sendrecv')
        try:
            self.webrtc.set_property('bundle-policy', 'max-bundle') # not compatible with GST 1.4
            self.webrtc.connect('notify::ice-connection-state', self.on_ice_connection_state)
            self.webrtc.connect('notify::connection-state', self.on_connection_state)
            self.webrtc.connect('notify::signaling-state', self.on_signaling_state)
        except Exception as e:
            print(e)
            pass
        self.webrtc.connect('on-negotiation-needed', self.on_negotiation_needed)
        self.webrtc.connect('on-ice-candidate', self.send_ice_candidate_message)
        self.webrtc.connect('pad-added', self.on_incoming_stream)
        self.pipe.set_state(Gst.State.PLAYING)

    def stop_pipeline(self):
        print("STOP PIPE")
        if self.pipe:
            self.pipe.set_state(Gst.State.NULL)                                     
    async def handle_sdp(self, msg):
        print("HANDLE SDP")
        assert (self.webrtc)
        if 'sdp' in msg:
            msg = msg
            assert(msg['type'] == 'answer')
            sdp = msg['sdp']
#            print ('Received answer:\n%s' % sdp)
            res, sdpmsg = GstSdp.SDPMessage.new()
            GstSdp.sdp_message_parse_buffer(bytes(sdp.encode()), sdpmsg)
            answer = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.ANSWER, sdpmsg)
            promise = Gst.Promise.new()
            self.webrtc.emit('set-remote-description', answer, promise)
            promise.interrupt()
        elif 'candidate' in msg:
            candidate = msg['candidate']
            sdpmlineindex = msg['sdpMLineIndex']
            self.webrtc.emit('add-ice-candidate', sdpmlineindex, candidate)

    async def handle_offer(self, msg):
        print("HANDLE SDP OFFER")
        assert (self.webrtc)
        if 'sdp' in msg:
            msg = msg
            assert(msg['type'] == 'offer')
            sdp = msg['sdp']
#            print ('Received offer:\n%s' % sdp)
            res, sdpmsg = GstSdp.SDPMessage.new()
            GstSdp.sdp_message_parse_buffer(bytes(sdp.encode()), sdpmsg)
            offer = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.OFFER, sdpmsg)
            promise = Gst.Promise.new()
            self.webrtc.emit('set-remote-description', offer, promise)
            promise.interrupt()
            self.create_answer()

    def on_data_channel(self, webrtc, channel):
        if channel is None:
            print('DATA CHANNEL: NOT AVAILABLE')
        else:
            print('DATA CHANNEL SETUP')                               
        channel.connect('on-open', self.on_data_channel_open)
        channel.connect('on-error', self.on_data_channel_error)
        channel.connect('on-close', self.on_data_channel_close)
        channel.connect('on-message-string', self.on_data_channel_message)

    def on_data_channel_error(self, channel):
        print('DATA CHANNEL: ERROR')

    def on_data_channel_open(self, channel):
        print('DATA CHANNEL: OPENED')

    def on_data_channel_close(self, channel):
        print('DATA CHANNEL: CLOSE')

    def on_data_channel_message(self, channel, msg_raw):
        try:
            msg = json.loads(msg_raw)
        except:
            return
        if 'candidates' in msg:
            for ice in msg['candidates']:
                pass ## TODO: handle incoming ICE
                ## await self.handle_sdp(ice)
        elif 'pong' in msg: # Supported in v19 of VDO.Ninja
            print('PONG:', msg['pong'])
            self.ping = 0             
        elif 'bye' in msg: ## v19 of VDO.Ninja
            print("PEER INTENTIONALLY HUNG UP")
        else:
            return
            #print('DATA CHANNEL: MESSAGE:', msg_raw)

    def pingTimer(self):
        if self.ping < 4:
            self.ping += 1
            try:
                self.send_channel.emit('send-string', '{"ping":"'+str(time.time())+'"}')
                print("PINGED")
            except Exception as E:
                print(E)
                print("PING FAILED")
            threading.Timer(3, self.pingTimer).start()
        else:
            print("NO HEARTBEAT")
            self.stop_pipeline()

    async def loop(self):
        assert self.conn
        print("WSS CONNECTED")
        async for message in self.conn:
            msg = json.loads(message)
            if 'UUID' in msg:
                if (self.puuid != None) and (self.puuid != msg['UUID']):
                    continue
                self.UUID = msg['UUID']
                
            if 'from' in msg:
                self.UUID = msg['from']

            if 'session' in msg:
                self.session = msg['session']

            if 'description' in msg:
                msg = msg['description']
                if 'type' in msg:
                    if msg['type'] == "offer":
                        self.start_pipeline()
                        await self.handle_offer(msg)
                    elif msg['type'] == "answer":
                        await self.handle_sdp(msg)

            elif 'candidates' in msg:
                for ice in msg['candidates']:
                    await self.handle_sdp(ice)

            elif 'request' in msg:
                if 'offerSDP' in  msg['request']:
                    self.start_pipeline()
                elif msg['request'] == 'play':
                    if self.puuid==None:
                        self.puuid = str(random.randint(10000000,99999999))
                    if 'streamID' in msg:
                        if msg['streamID'] == streamid:
                            self.start_pipeline()
            else:
                print(message)
                # return 1 ## disconnects on bad message
        return 0


def check_plugins(needed):
    missing = list(filter(lambda p: Gst.Registry.get().find_plugin(p) is None, needed))
    if len(missing):
        print('Missing gstreamer plugins:', missing)
        return False
    return True

WSS="wss://wss.vdo.ninja:443"

 ## Works with those cheap HDMI to USB 2.0 UVC capture dongle. Assumes just one UVC device is connected; see below for some others
  ###  PIPELINE_DESC = "v4l2src device=/dev/video0 io-mode=2 ! image/jpeg,framerate=30/1,width=1920,height=1080 ! jpegparse ! nvjpegdec ! video/x-raw ! nvvidconv ! video/x-raw(memory:NVMM) ! omxh264enc bitrate="+bitrate+"000 ! video/x-h264, stream-format=(string)byte-stream ! h264parse ! rtph264pay config-interval=-1 ! application/x-rtp,media=video,encoding-name=H264,payload=96 ! webrtc stun-server=stun://stun4.l.google.com:19302 name=sendrecv pulsesrc device=alsa_input.usb-MACROSILICON_2109-02.analog-stereo ! audioconvert ! audioresample ! queue ! opusenc ! rtpopuspay ! queue ! application/x-rtp,media=audio,encoding-name=OPUS,payload=96 ! sendrecv. "

if __name__=='__main__':
    Gst.init(None)
    
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
    parser.add_argument('--novideo', action='store_true', help='Disables video input.')
    parser.add_argument('--noaudio', action='store_true', help='Disables audio input.')
    parser.add_argument('--pipeline', type=str, help='A full custom pipeline')
    
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

            elif args.rpi:
                needed += ['omx']
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
                # TODO
                # needed += ['rpicamsrc']
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
                elif args.rpi:
                    pipeline_video_input += f' ! v4l2convert ! video/x-raw,format=I420 ! x264enc bitrate={args.bitrate} speed-preset=1 tune=zerolatency qos=true ! video/x-h264,stream-format=(string)byte-stream'
                    ## pipeline_video_input += f' ! v4l2convert ! video/x-raw,format=I420 ! omxh264enc ! video/x-h264,stream-format=(string)byte-stream' ## Good for a RPI Zero I guess?
                else:
                    pipeline_video_input += f' ! videoconvert ! x264enc bitrate={args.bitrate} speed-preset=ultrafast tune=zerolatency key-int-max=15 ! video/x-h264,profile=constrained-baseline'

                pipeline_video_input += ' ! h264parse ! rtph264pay config-interval=-1 ! application/x-rtp,media=video,encoding-name=H264,payload=96 ! queue ! sendrecv.'

            else:
                # VP8
                pipeline_video_input += f' ! videoconvert ! vp8enc deadline=1 target-bitrate={args.bitrate}000 ! rtpvp8pay ! application/x-rtp,media=video,encoding-name=VP8,payload=97 ! sendrecv.'

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

            pipeline_audio_input += ' ! audioconvert ! audioresample ! queue ! opusenc ! rtpopuspay ! queue ! application/x-rtp,media=audio,encoding-name=OPUS,payload=96 ! sendrecv.'

        PIPELINE_DESC = f'webrtcbin name=sendrecv bundle-policy=max-bundle {pipeline_video_input} {pipeline_audio_input}'
        print('gst-launch-1.0 ' + PIPELINE_DESC.replace('(', '\\(').replace(')', '\\)'))

        if not check_plugins(needed) or error:
            sys.exit(1)


    print("\nAvailable options include --streamid, --bitrate, and --server. Default bitrate is 4000 (kbps)")
    print(f"\nYou can view this stream at: https://vdo.ninja/?password=false&view={args.streamid}");

    c = WebRTCClient(args.streamid, args.server)
    asyncio.get_event_loop().run_until_complete(c.connect())
    res = asyncio.get_event_loop().run_until_complete(c.loop())
    sys.exit(res)
