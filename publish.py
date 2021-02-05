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
gi.require_version('Gst', '1.0')
from gi.repository import Gst
gi.require_version('GstWebRTC', '1.0')
from gi.repository import GstWebRTC
gi.require_version('GstSdp', '1.0')
from gi.repository import GstSdp

PIPELINE_DESC = ''' 
webrtcbin name=sendrecv bundle-policy=max-bundle
 videotestsrc ! videoconvert ! queue ! vp8enc deadline=1 ! rtpvp8pay !
 queue ! application/x-rtp,media=video,encoding-name=VP8,payload=97 ! sendrecv.
 audiotestsrc is-live=true wave=red-noise ! audioconvert ! audioresample ! queue ! opusenc ! rtpopuspay !
 queue ! application/x-rtp,media=audio,encoding-name=OPUS,payload=96 ! sendrecv.
''' ## In case you don't have a camera attached, try using this instead?

PIPELINE_DESC = '''
webrtcbin name=sendrecv bundle-policy=max-bundle
rpicamsrc bitrate=2000000 ! video/x-h264,profile=constrained-baseline,width=1280,height=720,level=3.0 ! queue ! h264parse ! rtph264pay config-interval=-1 !
queue ! application/x-rtp,media=video,encoding-name=H264,payload=96 ! sendrecv.
''' # raspberry pi camera needed; audio source removed to perserve simplicity.


class WebRTCClient:
    def __init__(self, peer_id, server):
        self.conn = None
        self.pipe = None
        self.webrtc = None
        self.UUID = None
        self.session = None
        self.peer_id = peer_id
        self.server = 'wss://apibackup.obs.ninja:443' ###  To avoid causing issues for production; streams can be view at https://backup.obs.ninja as a result.

    async def connect(self):
        print("Connect")
        sslctx = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
        self.conn = await websockets.connect(self.server, ssl=sslctx)
        msg = json.dumps({"request":"seed","streamID":self.peer_id})
        print(msg)
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
        print(msg)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(self.conn.send(msg))
        print("SENT MESSAGE")

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
        print("SENT MESSAGE")

    def send_ice_candidate_message(self, _, mlineindex, candidate):
        print("SEND ICE")
        icemsg = json.dumps({'candidates': [{'candidate': candidate, 'sdpMLineIndex': mlineindex}], 'session':self.session, 'type':'local', 'UUID':self.UUID})
        loop = asyncio.new_event_loop()
        loop.run_until_complete(self.conn.send(icemsg))

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
        self.pipe = Gst.parse_launch(PIPELINE_DESC)
        self.webrtc = self.pipe.get_by_name('sendrecv')
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
            print ('Received answer:\n%s' % sdp)
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
            print ('Received offer:\n%s' % sdp)
            res, sdpmsg = GstSdp.SDPMessage.new()
            GstSdp.sdp_message_parse_buffer(bytes(sdp.encode()), sdpmsg)
            offer = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.OFFER, sdpmsg)
            promise = Gst.Promise.new()
            self.webrtc.emit('set-remote-description', offer, promise)
            promise.interrupt()
            self.create_answer()


    async def loop(self):
        print("LOOP START")
        assert self.conn
        print("WSS CONNECTED")
        async for message in self.conn:
            msg = json.loads(message)
            print(msg)
            
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
    needed = ["opus", "vpx", "nice", "webrtc", "dtls", "srtp", "rtp",  ## vpx probably isn't needed
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
    parser.add_argument('streamid', help='Stream ID of the peer to connect to')
    parser.add_argument('--server', help='Handshake server to use, eg: "wss://backupapi.obs.ninja:443"')
    args = parser.parse_args()
    c = WebRTCClient(args.streamid, args.server)
    asyncio.get_event_loop().run_until_complete(c.connect())
    res = asyncio.get_event_loop().run_until_complete(c.loop())
    sys.exit(res)
