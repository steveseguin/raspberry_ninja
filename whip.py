"""WHIP publishing with Python HTTP signaling and ordinary GStreamer webrtcbin.

Capture/encoding pipelines come from publish.py unchanged. HTTP runs off the
GLib context; promises copy their SDP before dispatching back to that context.
Complete ICE offers work with endpoints that do not implement optional PATCH.
"""

import re
import signal
import threading
import time
import uuid

from whep import (HttpStatusError, WhepHttpSession, TrickleUnsupported, _gst,
                  mux_candidates, numeric_mids, deferred_candidates)


def prepare_offer(text, stream_id):
    """WHIP carries one MediaStream; keep its audio/video MSIDs consistent."""
    sections = re.split(r'(?m)(?=^m=)', text.replace('\r\n', '\n'))
    header = [line for line in sections[0].splitlines() if not line.startswith('a=msid-semantic:')]
    header.append('a=msid-semantic:WMS ' + stream_id)
    lines = header
    for index, section in enumerate(sections[1:]):
        track = 'track%d' % index
        media = []
        for line in section.splitlines():
            if line.startswith('a=msid:'):
                continue
            if line == 'a=sendrecv':
                line = 'a=sendonly'
            if line.startswith('a=ssrc:') and ' msid:' in line:
                line = line.split(' msid:')[0] + ' msid:' + stream_id + ' ' + track
            media.append(line)
        media.append('a=msid:' + stream_id + ' ' + track)
        if 'a=rtcp-mux' in media and 'a=rtcp-mux-only' not in media:
            media.append('a=rtcp-mux-only')
        lines.extend(media)
    return '\r\n'.join(lines) + '\r\n'


class WhipPublisher:
    def __init__(self, pipeline_desc, endpoint, configure_ice, log=print,
                 token='', timeout=15, latency=200, trickle='auto'):
        # Validate before any capture device is opened.
        WhepHttpSession(endpoint, token, timeout, protocol='WHIP')
        self.Gst, self.WebRTC, self.Sdp, self.GLib = _gst()
        self.trickle = self.Gst.version()[:2] < (1, 20) if trickle == 'auto' else trickle == 'on'
        self.patch_pending = False
        self.pipeline_desc = pipeline_desc
        self.endpoint, self.token = endpoint, token
        self.configure_ice, self.log = configure_ice, log
        self.timeout, self.latency = timeout, latency
        self.pipe = self.peer = self.http = self.bus = None
        self.bus_handler = self.timer = None
        self.loop = self.GLib.MainLoop()
        self.stage = 'stopped'
        self.epoch = 0
        self.attempt = 0
        self.next_retry = 0
        self.failed = False
        self.closed = False
        self.cancelled = False
        self.workers = []
        self.stream_id = 'rn-whip-' + uuid.uuid4().hex
        self.last_media = 0
        self.last_feedback = self.feedback_started = 0
        self.rtcp_handlers = []

    def _background(self, callback):
        self.workers = [worker for worker in self.workers if worker.is_alive()]
        # Keep a late POST alive long enough to DELETE its resource on shutdown.
        # Requests have a timeout; daemon threads could exit after allocating it.
        worker = threading.Thread(target=callback, name='whip-http', daemon=False)
        self.workers.append(worker)
        worker.start()

    def _defer(self, epoch, callback, *args):
        def run():
            if not self.closed and epoch == self.epoch:
                try:
                    callback(*args)
                except Exception as exc:
                    self._fatal(str(exc))
            return False
        self.GLib.idle_add(run)

    def _promise(self, callback):
        epoch = self.epoch
        def complete(promise, *_):
            reply = promise.get_reply()
            if reply and reply.has_field('error'):
                self._defer(epoch, self._fatal, 'GStreamer rejected WHIP SDP')
            else:
                offer = reply.get_value('offer').copy() if reply and reply.has_field('offer') else None
                self._defer(epoch, callback, offer)
        return self.Gst.Promise.new_with_change_func(complete, None, None)

    def _begin(self):
        Gst = self.Gst
        for name in ('webrtcbin', 'nicesrc', 'dtlssrtpenc', 'rtpbin'):
            if not Gst.ElementFactory.find(name):
                raise RuntimeError('Missing GStreamer %s; install the ordinary WebRTC plugins' % name)
        self.epoch += 1
        self.pipe = Gst.parse_launch('webrtcbin name=sendrecv bundle-policy=max-bundle ' + self.pipeline_desc)
        self.peer = self.pipe.get_by_name('sendrecv')
        if self.peer.find_property('latency'):
            self.peer.set_property('latency', max(10, int(self.latency)))
        self.configure_ice(self.peer)
        pads = list(self.peer.sinkpads)
        if not pads:
            raise RuntimeError('WHIP needs RTP audio/video linked to sendrecv.')
        epoch = self.epoch
        for pad in pads:
            if pad.find_property('msid'):
                pad.set_property('msid', self.stream_id)
            transceiver = pad.get_property('transceiver')
            transceiver.set_property('direction', self.WebRTC.WebRTCRTPTransceiverDirection.SENDONLY)
            def received(_pad, _info):
                if epoch == self.epoch:
                    self.last_media = time.monotonic()
                return Gst.PadProbeReturn.OK
            pad.add_probe(Gst.PadProbeType.BUFFER, received)
        self.bus = self.pipe.get_bus()
        self.bus.add_signal_watch()
        self.bus_handler = self.bus.connect('message', self._on_message)
        self.stage = 'caps'
        self.deadline = time.monotonic() + 30
        if self.pipe.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError('Capture pipeline could not start')
        self.log('WHIP: Python signaling with %s; waiting for encoded RTP' % Gst.version_string())

    def _on_message(self, _bus, message):
        if message.type == self.Gst.MessageType.ERROR:
            error, _ = message.parse_error()
            self._fatal('Pipeline error from %s: %s (%s)' % (
                message.src.get_name(), error.message, self.Gst.version_string()))
        elif message.type == self.Gst.MessageType.EOS:
            self.loop.quit()

    def _offer_created(self, offer):
        if not offer:
            raise RuntimeError('GStreamer did not create a WHIP offer')
        text = prepare_offer(offer.sdp.as_text(), self.stream_id)
        if self.trickle:
            text = numeric_mids(text)
        result, sdp = self.Sdp.SDPMessage.new_from_text(text)
        if result != self.Sdp.SDPResult.OK:
            raise RuntimeError('Unable to prepare WHIP SDP')
        offer = self.WebRTC.WebRTCSessionDescription.new(self.WebRTC.WebRTCSDPType.OFFER, sdp)
        self.peer.emit('set-local-description', offer, self._promise(self._local_applied))

    def _local_applied(self, _reply):
        self.stage = 'gathering'
        self.deadline = time.monotonic() + 30

    def _post(self):
        offer = self.peer.get_property('local-description')
        if not offer:
            raise RuntimeError('Missing local WHIP description')
        # RTCP is multiplexed with RTP; legacy libnice also gathers component 2.
        sdp = mux_candidates(offer.sdp.as_text())
        http = WhepHttpSession(self.endpoint, self.token, self.timeout, trickle=self.trickle, protocol='WHIP')
        self.http = http
        epoch = self.epoch
        self.stage = 'http'
        self.deadline = time.monotonic() + self.timeout * 6 + 5
        def exchange():
            try:
                answer = http.offer(sdp)
                self._defer(epoch, self._accept_answer, answer)
            except Exception as exc:
                http.close()
                self._defer(epoch, self._http_failed, exc)
        self._background(exchange)

    def _accept_answer(self, answer):
        result, sdp = self.Sdp.SDPMessage.new_from_text(mux_candidates(answer))
        if result != self.Sdp.SDPResult.OK:
            raise RuntimeError('Unable to parse WHIP answer')
        for index in range(sdp.medias_len()):
            media = sdp.get_media(index)
            if media.get_port() == 0 and media.get_attribute_val('bundle-only') is None:
                raise RuntimeError('WHIP endpoint rejected a media track; check its codec support')
        desc = self.WebRTC.WebRTCSessionDescription.new(self.WebRTC.WebRTCSDPType.ANSWER, sdp)
        self.peer.emit('set-remote-description', desc, self._promise(self._remote_applied))

    def _remote_applied(self, _reply):
        self.stage = 'connecting'
        self.deadline = time.monotonic() + 30
        self.patch_pending = bool(self.http and self.http.trickle)
        # Older WebRTC stacks can remain "connected" after the server dies.
        # Monitor the documented RTPSession signal as well as ICE state.
        from gi.repository import GObject
        rtpbin = self.peer.get_by_name('rtpbin')
        epoch = self.epoch
        def feedback(_session, _buffer):
            if epoch == self.epoch:
                self.last_feedback = time.monotonic()
        if rtpbin:
            for index in range(len(self.peer.sinkpads)):
                session = rtpbin.emit('get-internal-session', index)
                if session and GObject.signal_lookup('on-receiving-rtcp', session.__gtype__):
                    self.rtcp_handlers.append((session, session.connect('on-receiving-rtcp', feedback)))

    def _patch_candidates(self):
        http, epoch = self.http, self.epoch
        offer = self.peer.get_property('local-description')
        if not offer:
            raise RuntimeError('Missing local description for WHIP candidates')
        _, http.candidates = deferred_candidates(offer.sdp.as_text())
        self.patch_pending = False
        # Legacy webrtcbin must apply the answer before the relay begins checks.
        def patch():
            try:
                http.send_candidates()
            except Exception as exc:
                self._defer(epoch, self._http_failed, exc)
        self._background(patch)

    def _http_failed(self, error):
        if isinstance(error, TrickleUnsupported):
            self.trickle = False
            self._retry(str(error))
        elif isinstance(error, HttpStatusError) and 400 <= error.status < 500 and error.status not in (408, 429):
            self._fatal(str(error) + '; check endpoint, bearer token and accepted codecs')
        else:
            self._retry(str(error), getattr(error, 'retry_after', 0))

    def _tick(self):
        if self.closed or self.failed:
            return False
        try:
            now = time.monotonic()
            if (self.patch_pending and self.peer and self.peer.get_property('ice-gathering-state') ==
                    self.WebRTC.WebRTCICEGatheringState.COMPLETE):
                self._patch_candidates()
            if self.stage == 'retry':
                # Let DELETE finish before creating another publishing resource.
                if now >= self.next_retry and not any(worker.is_alive() for worker in self.workers):
                    self._begin()
            elif self.stage == 'caps':
                caps = [pad.get_current_caps() for pad in self.peer.sinkpads]
                if caps and all(cap and cap.get_structure(0).has_field('ssrc') for cap in caps):
                    self.stage = 'offer'
                    self.peer.emit('create-offer', None, self._promise(self._offer_created))
                elif now >= self.deadline:
                    self._fatal('No encoded RTP after 30 seconds; check the capture source and encoder')
            elif self.stage == 'gathering':
                if self.trickle or self.peer.get_property('ice-gathering-state') == self.WebRTC.WebRTCICEGatheringState.COMPLETE:
                    self._post()
                elif now >= self.deadline:
                    self._retry('ICE gathering timed out; check STUN/TURN configuration')
            else:
                state = self.peer.get_property('connection-state')
                ice = self.peer.get_property('ice-connection-state')
                if ice in (self.WebRTC.WebRTCICEConnectionState.FAILED, self.WebRTC.WebRTCICEConnectionState.CLOSED):
                    self._retry('ICE connection failed')
                elif state == self.WebRTC.WebRTCPeerConnectionState.CONNECTED:
                    if self.stage != 'publishing':
                        self.log('WHIP: connected')
                        self.feedback_started = now
                    self.stage = 'publishing'
                    self.attempt = 0
                    self.deadline = now + 15
                    if self.last_media and now - self.last_media > 30:
                        self._fatal('Capture stopped producing RTP for 30 seconds')
                    elif self.rtcp_handlers and now - max(self.last_feedback, self.feedback_started) > 30:
                        self._retry('No RTCP feedback from the endpoint for 30 seconds')
                elif state in (self.WebRTC.WebRTCPeerConnectionState.FAILED, self.WebRTC.WebRTCPeerConnectionState.CLOSED):
                    self._retry('WebRTC connection failed')
                elif now >= self.deadline:
                    reason = 'WHIP negotiation/connection timed out'
                    if self.Gst.version()[:2] < (1, 20) and not self.trickle:
                        reason += '; GStreamer <1.20 can stall without PATCH; try a newer GStreamer'
                    self._retry(reason)
        except Exception as exc:
            self._fatal(str(exc))
        return not self.failed and not self.closed

    def _fatal(self, reason):
        self.failed = True
        self.log('WHIP: ' + reason)
        self.loop.quit()

    def _retry(self, reason, retry_after=0):
        self._stop_transport()
        self.attempt += 1
        delay = max(min(30, 2 ** min(self.attempt, 5)), retry_after)
        self.stage = 'retry'
        self.next_retry = time.monotonic() + delay
        self.log('WHIP: %s; retrying in %ss' % (reason, round(delay, 1)))

    def _stop_transport(self):
        self.epoch += 1
        self.patch_pending = False
        for session, handler in self.rtcp_handlers:
            session.disconnect(handler)
        self.rtcp_handlers = []
        self.last_feedback = self.feedback_started = 0
        if self.bus:
            self.bus.disconnect(self.bus_handler)
            self.bus.remove_signal_watch()
            self.bus = self.bus_handler = None
        if self.pipe:
            self.pipe.set_state(self.Gst.State.NULL)
            self.pipe = self.peer = None
        http, self.http = self.http, None
        if http:
            self._background(http.close)

    def start(self):
        handlers = {}
        def interrupt(_signum, _frame):
            self.cancelled = True
            self.loop.quit()
        try:
            if threading.current_thread() is threading.main_thread():
                for signum in (signal.SIGINT, signal.SIGTERM):
                    handlers[signum] = signal.signal(signum, interrupt)
            self._begin()
            self.timer = self.GLib.timeout_add(100, self._tick)
            if not self.cancelled:
                self.loop.run()
        except KeyboardInterrupt:
            pass
        except Exception as exc:
            self._fatal(str(exc))
        finally:
            self.stop()
            for signum, handler in handlers.items():
                signal.signal(signum, handler)
        return not self.failed

    def stop(self):
        if self.closed:
            return
        self.closed = True
        self._stop_transport()
        self.loop.quit()
        if self.timer is not None:
            # A failed tick may have already removed the source.
            if self.GLib.MainContext.default().find_source_by_id(self.timer):
                self.GLib.source_remove(self.timer)
            self.timer = None
        deadline = time.monotonic() + 2
        for worker in self.workers:
            worker.join(max(0, deadline - time.monotonic()))
