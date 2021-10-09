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
    def __init__(self, peer_id, server):
        self.conn = None
        self.pipe = None
        self.webrtc = None
        self.UUID = None
        self.session = None
        self.peer_id = peer_id
        self.server = server ###  To avoid causing issues for production; streams can be view at https://backup.obs.ninja as a result.
        self.send_channel = None
        self.timer = None

    async def connect(self):
        sslctx = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
        self.conn = await websockets.connect(self.server, ssl=sslctx)
        msg = json.dumps({"request":"seed","streamID":self.peer_id})
        await self.conn.send(msg)
    
    def on_offer_created(self, promise, _, __):  ## This is all based on the legacy API of OBS.Ninja; gstreamer-1.19 lacks support for the newer API.
        print("ON OFFER CREATED")
        promise.wait()
        reply = promise.get_reply()
        offer = reply.get_value('offer')
        promise = Gst.Promise.new()
        self.webrtc.emit('set-local-description', offer, promise)
        promise.interrupt()
        print("SEND SDP OFFER")
        text = offer.sdp.as_text()
        msg = json.dumps({'description': {'type': 'offer', 'sdp': text}, 'UUID': self.UUID, 'session': self.session, 'streamID':self.peer_id})
        #print(msg)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(self.conn.send(msg))

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
        msg = json.dumps({'description': {'type': 'answer', 'sdp': text, 'UUID': self.UUID, 'session': self.session}})
        loop = asyncio.new_event_loop()
        loop.run_until_complete(self.conn.send(msg))

    def send_ice_candidate_message(self, _, mlineindex, candidate):
#        print("SEND ICE")
        icemsg = json.dumps({'candidates': [{'candidate': candidate, 'sdpMLineIndex': mlineindex}], 'session':self.session, 'type':'local', 'UUID':self.UUID})
        loop = asyncio.new_event_loop()
        loop.run_until_complete(self.conn.send(icemsg))

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
#            exc_type, exc_obj, exc_tb = sys.exc_info()
 #           fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
  #          print(e)
   #         print(exc_type, fname, exc_tb.tb_lineno)
    #        pass 
        self.webrtc.connect('on-negotiation-needed', self.on_negotiation_needed)
        self.webrtc.connect('on-ice-candidate', self.send_ice_candidate_message)
        self.webrtc.connect('pad-added', self.on_incoming_stream)
        self.pipe.set_state(Gst.State.PLAYING)

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
        elif 'bye' in msg: ## v19 of VDO.Ninja
            print("PEER INTENTIONALLY HUNG UP")
        else:
            return
            #print('DATA CHANNEL: MESSAGE:', msg_raw)

    def pingTimer(self):
        try:
            self.send_channel.emit('send-string', '{"ping":"'+str(time.time())+'"}')
            print("PINGED")
        except Exception as E:
            print("PING FAILED")
        threading.Timer(3, self.pingTimer).start()

    async def loop(self):
        assert self.conn
        print("WSS CONNECTED")
        async for message in self.conn:
            msg = json.loads(message)
            if 'UUID' in msg:
                self.UUID = msg['UUID']

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
            else:
                print (message)
                # return 1 ## disconnects on bad message
        return 0


def check_plugins():
    needed = ["opus", "vpx", "nice", "webrtc", "dtls", "srtp", "rtp", "sctp",  ## vpx probably isn't needed
              "rtpmanager", "videotestsrc", "audiotestsrc"]
    missing = list(filter(lambda p: Gst.Registry.get().find_plugin(p) is None, needed))
    if len(missing):
        print('Missing gstreamer plugins:', missing)
        return False
    return True

if __name__=='__main__':
    Gst.init(None)
    if not check_plugins():
        sys.exit(1)
    parser = argparse.ArgumentParser()
    parser.add_argument('--streamid', help='Stream ID of the peer to connect to')
    parser.add_argument('--server', help='Handshake server to use, eg: "wss://backupapi.obs.ninja:443"')
    parser.add_argument('--bitrate', help='Sets the video bitrate. This is not adaptive, so packet loss and insufficient bandwidth will cause frame loss')
    args = parser.parse_args()

    server = args.server or "wss://wss13.obs.ninja:443" # production WSS is only for optimized webrtc handshaking; other traffic must be done via p2p.
    streamid = args.streamid or str(random.randint(1000000,9999999))
    bitrate = args.bitrate or str(4000)

    print("\nAvailable options include --streamid, --bitrate, and --server. Default bitrate is 4000 (kbps)")
    print("\nYou can view this stream at: https:/vdo.ninja/beta/?password=false&view="+streamid);

    ## Works with those cheap HDMI to USB 2.0 UVC capture dongle. Assumes just one UVC device is connected; see below for some others
    PIPELINE_DESC = "v4l2src device=/dev/video0 io-mode=2 ! image/jpeg,framerate=30/1,width=1920,height=1080 ! jpegparse ! nvjpegdec ! video/x-raw ! nvvidconv ! video/x-raw(memory:NVMM) ! omxh264enc bitrate="+bitrate+"000 ! video/x-h264, stream-format=(string)byte-stream ! h264parse ! rtph264pay config-interval=-1 ! application/x-rtp,media=video,encoding-name=H264,payload=96 ! webrtcbin stun-server=stun://stun4.l.google.com:19302 name=sendrecv pulsesrc device=alsa_input.usb-MACROSILICON_2109-02.analog-stereo ! audioconvert ! audioresample ! queue ! opusenc ! rtpopuspay ! queue ! application/x-rtp,media=audio,encoding-name=OPUS,payload=96 ! sendrecv. "

    c = WebRTCClient(streamid, server)
    asyncio.get_event_loop().run_until_complete(c.connect())
    res = asyncio.get_event_loop().run_until_complete(c.loop())
    sys.exit(res)

