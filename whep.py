"""WHEP HTTP signaling using Python's standard library and ordinary webrtcbin.

No gst-plugins-rs elements are used. Legacy GStreamer defers gathered candidates
with standard WHEP PATCH signaling when supported; other peers use complete offers.
GStreamer control operations run on the GLib context; HTTP runs off that context.
"""

import json
import threading
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from email.utils import parsedate_to_datetime


def opt_out_fields(disabled):
    if not disabled:
        return {}
    return dict.fromkeys(("allowmeshcast", "allowwhipout", "allowscreenmeshcast",
                          "allowscreenwhipout"), False)


def media_request_fields(audio, video, disabled):
    # MediaMTX/WHIP publishers interpret a partial A/V request as a request for
    # P2P. Keep relay discovery enabled and apply output filters locally. An
    # explicit --nowhep retains selective P2P requests and their bandwidth savings.
    if not disabled and (audio or video):
        audio = video = True
    return dict(audio=bool(audio), video=bool(video), **opt_out_fields(disabled))


def validate_url(url, protocol='WHEP'):
    if not isinstance(url, str) or any(ord(c) < 32 or c.isspace() for c in url):
        raise ValueError("%s requires an HTTP(S) URL" % protocol)
    try:
        parsed = urlsplit(url)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username is not None or parsed.password is not None or parsed.fragment
                or (parsed.port is not None and not 0 < parsed.port < 65536)):
            raise ValueError()
    except ValueError:
        # urlsplit/port exceptions can otherwise expose parts of a secret URL.
        raise ValueError("%s requires a valid HTTP(S) URL without embedded credentials or fragment" % protocol) from None
    return url


def normalize_settings(settings, media=None):
    if not isinstance(settings, dict) or settings.get("type", "whep") != "whep":
        raise ValueError("Unsupported relay type; use --nowhep for legacy Meshcast")
    result = dict(settings)
    result["url"] = validate_url(settings.get("url"))
    result["media"] = media or settings.get("media", "primary")
    if result["media"] not in ("primary", "screen"):
        raise ValueError("Unknown WHEP media identity")
    token = settings.get("token") or ""
    if not isinstance(token, str) or any(ord(c) < 32 for c in token):
        raise ValueError("Invalid WHEP bearer token")
    result["token"] = token
    return result


def advertisements(message):
    """Return both advertisements when a control packet contains primary + screen."""
    result = []
    for key, media in (("whepSettings", None), ("whepScreenSettings", "screen")):
        if key in message:
            result.append(normalize_settings(message[key], media))
    return result


def has_started(settings):
    """Match VDO.Ninja's whepSettingsHasStarted, including string markers."""
    value = settings.get('started')
    if isinstance(value, str):
        return value.strip().lower() not in ('', '0', 'false')
    if isinstance(value, (int, float)):
        return value > 0
    return False


class RelayControlState:
    """Remember an advertised screen endpoint until the publisher starts it."""

    def __init__(self):
        self.screen = None
        self.screen_active = False

    def update(self, message):
        settings = advertisements(message)
        info = message.get('info') if isinstance(message.get('info'), dict) else {}
        screen_state = message.get('screenShareState', info.get('screenShareState'))
        if 'screenStopped' in message:
            screen_state = not bool(message['screenStopped'])
        ready = [item for item in settings if item['media'] == 'primary']
        screen_changed = False
        for item in settings:
            if item['media'] == 'screen':
                self.screen = item
                screen_changed = True
                if has_started(item):
                    self.screen_active = True
        if screen_state is False:
            self.screen = None
            self.screen_active = False
        elif screen_state is True:
            self.screen_active = True
        if self.screen and self.screen_active and (screen_changed or screen_state is True):
            ready.append(self.screen)
        return ready, screen_state is False


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class TrickleUnsupported(RuntimeError):
    """Retry this endpoint with a complete, non-trickle offer."""


def mux_candidates(sdp):
    """WHEP max-bundle uses one ICE component for multiplexed RTP and RTCP."""
    return '\r\n'.join(line for line in sdp.splitlines() if not (
        line.startswith('a=candidate:') and len(line.split()) > 1 and line.split()[1] != '1')) + '\r\n'


def deferred_candidates(sdp):
    """Separate a gathered max-bundle offer from its RFC 8840 ICE fragment."""
    lines = mux_candidates(sdp).splitlines()
    offer = [line for line in lines if not line.startswith(('a=candidate:', 'a=end-of-candidates'))]
    sections, current = [], []
    for line in lines:
        if line.startswith('m='):
            sections.append(current)
            current = []
        current.append(line)
    sections.append(current)
    session = sections.pop(0)
    fragment = [line for line in session if line.startswith(
        ('a=ice-ufrag:', 'a=ice-pwd:', 'a=ice-options:', 'a=ice-lite', 'a=group:BUNDLE'))]
    for section in sections:
        if 'a=bundle-only' in section or section[0].split()[1] == '0':
            continue
        fragment.append(section[0])
        fragment.extend(line for line in section if line.startswith(
            ('a=mid:', 'a=ice-ufrag:', 'a=ice-pwd:', 'a=candidate:')))
        fragment.append('a=end-of-candidates')
    return '\r\n'.join(offer) + '\r\n', '\r\n'.join(fragment) + '\r\n'


def numeric_mids(text, mids=None):
    """Adapt a candidate fragment for relays requiring numeric media indexes."""
    lines = text.splitlines()
    if mids is None:
        mids = {line[6:]: str(index) for index, line in enumerate(
            line for line in lines if line.startswith('a=mid:'))}
    for index, line in enumerate(lines):
        if line.startswith('a=mid:'):
            lines[index] = 'a=mid:' + mids.get(line[6:], line[6:])
        elif line.startswith('a=group:BUNDLE '):
            lines[index] = 'a=group:BUNDLE ' + ' '.join(mids.get(mid, mid) for mid in line.split()[1:])
    return '\r\n'.join(lines) + '\r\n'


class HttpStatusError(RuntimeError):
    """Safe HTTP diagnostics shared by WHIP and WHEP; no response body or URL."""

    def __init__(self, protocol, method, status, retry_after=None):
        super().__init__("%s %s returned HTTP %s" % (protocol, method, status))
        self.method = method
        self.status = status
        self.retry_after = 0
        if retry_after:
            try:
                self.retry_after = max(0, int(retry_after))
            except (ValueError, TypeError):
                try:
                    self.retry_after = max(0, parsedate_to_datetime(retry_after).timestamp() - time.time())
                except (ValueError, TypeError, OverflowError):
                    pass


class WhepHttpSession:
    """Shared WHIP/WHEP HTTP resource, with POST-preserving redirects and DELETE."""

    def __init__(self, url, token="", timeout=15, trickle=False, protocol="WHEP"):
        self.url = validate_url(url, protocol)
        self.protocol = protocol
        if not isinstance(token, str) or any(not 33 <= ord(c) <= 126 for c in token):
            raise ValueError("Invalid %s bearer token" % protocol)
        self.token = token
        self.timeout = timeout
        self.location = None
        self.trickle = trickle
        self.candidates = None
        self.mid_indices = {}
        self.etag = None
        self._closed = False
        self._lock = threading.Lock()
        self.opener = build_opener(_NoRedirect())

    def _request(self, method, url, data=None):
        headers = {"Accept": "application/sdp", "User-Agent": "RaspberryNinja"}
        if data is not None:
            headers["Content-Type"] = "application/sdp"
        if method == 'PATCH':
            headers['Content-Type'] = 'application/trickle-ice-sdpfrag'
            headers['If-Match'] = self.etag
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        for _ in range(6):
            with self._lock:
                if self._closed and method != 'DELETE':
                    raise RuntimeError('%s session was cancelled' % self.protocol)
            request = Request(url, data=data, headers=headers, method=method)
            try:
                response = self.opener.open(request, timeout=self.timeout)
            except HTTPError as exc:
                response = exc
            except (URLError, OSError, UnicodeError):
                # Exceptions and response bodies can contain secret-bearing URLs.
                raise RuntimeError("%s HTTP connection failed (check endpoint, TLS and network)" % self.protocol) from None
            with response:
                status = response.code
                response_headers = response.headers
                if status in (307, 308):
                    target = validate_url(urljoin(url, response_headers.get("Location", "")), self.protocol)
                    if urlsplit(url).scheme == "https" and urlsplit(target).scheme != "https":
                        raise RuntimeError("%s refused an HTTPS downgrade redirect" % self.protocol)
                    url = target
                    continue
                body = response.read(1024 * 1024 + 1)
                if len(body) > 1024 * 1024:
                    raise RuntimeError("%s response exceeded 1 MiB" % self.protocol)
                return status, response_headers, body, url
        raise RuntimeError("Too many %s redirects" % self.protocol)

    def offer(self, sdp):
        if self.trickle:
            self.mid_indices = {line[6:]: str(index) for index, line in enumerate(
                line for line in sdp.splitlines() if line.startswith('a=mid:'))}
            sdp, self.candidates = deferred_candidates(sdp)
        status, headers, body, endpoint = self._request("POST", self.url, sdp.encode("utf-8"))
        if status not in (200, 201):
            raise HttpStatusError(self.protocol, "POST", status, headers.get('Retry-After'))
        if headers.get("Location"):
            location = validate_url(urljoin(endpoint, headers["Location"]), self.protocol)
            if urlsplit(endpoint).scheme == "https" and urlsplit(location).scheme != "https":
                raise RuntimeError("%s refused an insecure session Location" % self.protocol)
            with self._lock:
                self.location = location
                cancelled = self._closed
            if cancelled:
                self.close()
                raise RuntimeError("%s session was cancelled" % self.protocol)
        if headers.get_content_type() != "application/sdp":
            raise RuntimeError("%s endpoint did not return application/sdp" % self.protocol)
        try:
            answer = body.decode("utf-8")
        except UnicodeError:
            raise RuntimeError("%s returned invalid SDP encoding" % self.protocol) from None
        if not answer.startswith("v=0") or "\nm=" not in answer:
            raise RuntimeError("%s returned an invalid SDP answer" % self.protocol)
        if self.trickle:
            self.etag = headers.get('ETag')
            if (not self.location or not self.etag or
                    'application/trickle-ice-sdpfrag' not in headers.get('Accept-Patch', '').lower()):
                raise TrickleUnsupported('Relay does not advertise %s trickle ICE; using a complete offer' % self.protocol)
            # 1.18 also gathers a separate RTCP component. With a multiplexed
            # relay, checking it can redirect the relay away from the RTP socket.
            answer = mux_candidates(answer)
        return answer

    def send_candidates(self):
        with self._lock:
            if self._closed or not self.candidates:
                return
            location, fragment = self.location, self.candidates
            self.candidates = None
        status, _, body, _ = self._request('PATCH', location, fragment.encode('utf-8'))
        try:
            mid_error = status == 500 and json.loads(body).get('error') == 'invalid mid attribute'
        except (ValueError, AttributeError):
            mid_error = False
        if status == 400 or mid_error:
            # Some MediaMTX versions parse MID as a media-line number and
            # report that parse error as HTTP 500. Try the numeric format
            # only after rejection; standards-compliant relays retain
            # the original MID. Never rewrite native offers/transceiver MIDs:
            # newer webrtcbin rejects that change before HTTP can even start.
            numeric = numeric_mids(fragment, self.mid_indices)
            if numeric != fragment:
                status, _, _, _ = self._request('PATCH', location, numeric.encode('utf-8'))
        if status in (405, 412, 415, 422, 428, 501):
            raise TrickleUnsupported('Relay rejected %s trickle ICE; using a complete offer' % self.protocol)
        if status != 204:
            raise HttpStatusError(self.protocol, 'PATCH', status)

    def close(self):
        with self._lock:
            self._closed = True
            location, self.location = self.location, None
        if location:
            try:
                self._request("DELETE", location)
            except Exception:
                pass  # Best effort; never retain a session after local shutdown.


def negotiation_timeout(peer, gst, trickle):
    """Describe stalled negotiation without SDP, addresses or credentials."""
    states = []
    for label, name in (('ICE', 'ice-connection-state'), ('peer', 'connection-state'),
                        ('signaling', 'signaling-state')):
        try:
            state = peer.get_property(name).value_nick
        except (AttributeError, TypeError):
            state = 'unknown'
        states.append('%s=%s' % (label, state))
    mode = 'PATCH' if trickle else 'complete offer'
    reason = 'Negotiation/connection timed out (%s; %s; %s)' % (
        gst.version_string(), ', '.join(states), mode)
    if gst.version()[:2] < (1, 20) and not trickle:
        reason += ('; legacy ICE/DTLS can stall without PATCH; use a PATCH-capable endpoint '
                   'or a newer GStreamer/libnice stack (see docs/troubleshooting.md)')
    return reason


def _gst():
    import gi
    gi.require_version("Gst", "1.0")
    gi.require_version("GstWebRTC", "1.0")
    gi.require_version("GstSdp", "1.0")
    from gi.repository import Gst, GstWebRTC, GstSdp, GLib
    # Resolve lazy boxed types and enum members before concurrent A/V callbacks.
    # Older PyGObject can otherwise create incompatible Caps wrappers or expose
    # a partially initialized PadDirection enum. Entry points call this before
    # any pipeline starts, including P2P receivers that create switches lazily.
    _ = (Gst.Caps, Gst.Structure, Gst.Buffer, Gst.Event, Gst.Pad, Gst.GhostPad,
         Gst.PadProbeInfo, Gst.PadDirection.SRC, Gst.PadProbeType.BUFFER,
         Gst.PadProbeReturn.OK, Gst.EventType.EOS)
    return Gst, GstWebRTC, GstSdp, GLib


class RtpSourceSwitch:
    """Keep output branches stable across relay reconnects; play each track once.

    Each instance represents one participant/media identity. Selectors accept both
    the control peer's RTP and relay RTP, preferring the relay when it has a pad.
    A new transport cannot reset/overwrite an already-open recording file.
    """

    def __init__(self, pipeline, on_pad, log, audio=True, video=True, flush_on_detach=False):
        self.Gst, _, _, _ = _gst()
        self.pipeline, self.on_pad, self.log = pipeline, on_pad, log
        self.enabled = {"audio": audio, "video": video}
        self.flush_on_detach = flush_on_detach
        self.tracks = {}
        self.inputs = {}
        self.lock = threading.RLock()
        self.closed = False

    def codecs(self):
        return {kind: track["codec"] for kind, track in self.tracks.items()}

    def attach(self, element, pad, relay=False):
        Gst = self.Gst
        if pad.get_direction() != Gst.PadDirection.SRC or pad.is_linked():
            return
        caps = pad.get_current_caps() or pad.query_caps(None)
        if not caps or caps.is_empty() or caps.is_any():
            raise RuntimeError("Incoming RTP pad has no negotiated caps")
        structure = caps.get_structure(0)
        kind, codec = structure.get_string("media"), structure.get_string("encoding-name")
        if kind not in ("audio", "video"):
            return
        with self.lock:
            if self.closed or pad in self.inputs:
                return
            track = self.tracks.get(kind)
            if track and track["codec"] != codec:
                raise RuntimeError("RTP codec changed from %s to %s; reconnect the viewer/recorder" % (track["codec"], codec))
            if not track:
                name = "whep_track_" + uuid.uuid4().hex
                container = Gst.Bin.new(name)
                selector = Gst.ElementFactory.make("input-selector", None)
                if selector is None:
                    raise RuntimeError("Missing GStreamer input-selector (plugins-base)")
                selector.set_property("sync-streams", False)
                container.add(selector)
                output = Gst.GhostPad.new(name, selector.get_static_pad("src"))
                container.add_pad(output)
                self.pipeline.add(container)
                container.sync_state_with_parent()
                track = {"bin": container, "selector": selector, "output": output,
                         "codec": codec, "connected": False}
                self.tracks[kind] = track
            selector = track["selector"]
            sink = (selector.request_pad_simple("sink_%u") if hasattr(selector, "request_pad_simple")
                    else selector.get_request_pad("sink_%u"))
            ghost = Gst.GhostPad.new("input_" + uuid.uuid4().hex, sink)
            track["bin"].add_pad(ghost)
            ghost.set_active(True)
            # Transport teardown must not EOS a recording that will reconnect.
            def drop_eos(_pad, info):
                event = info.get_event()
                return Gst.PadProbeReturn.DROP if event and event.type == Gst.EventType.EOS else Gst.PadProbeReturn.OK
            ghost.add_probe(Gst.PadProbeType.EVENT_DOWNSTREAM, drop_eos)
            if pad.link(ghost) != Gst.PadLinkReturn.OK:
                track["bin"].remove_pad(ghost)
                selector.release_request_pad(sink)
                raise RuntimeError("Cannot link incoming RTP to output selector")
            self.inputs[pad] = (kind, ghost, sink, relay)
            active = selector.get_property("active-pad")
            if relay or active is None:
                selector.set_property("active-pad", sink)
            if not track["connected"]:
                output = track["output"]
                output.push_event(Gst.Event.new_stream_start("rn-" + uuid.uuid4().hex))
                output.push_event(Gst.Event.new_caps(caps))
                if self.enabled[kind]:
                    self.on_pad(element, output)
                else:
                    discard = Gst.ElementFactory.make("fakesink", None)
                    discard.set_property("sync", False)
                    discard.set_property("async", False)
                    self.pipeline.add(discard)
                    discard.sync_state_with_parent()
                    output.link(discard.get_static_pad("sink"))
                    track["discard"] = discard
                track["connected"] = output.is_linked()
                if not track["connected"]:
                    raise RuntimeError("No output accepted incoming %s/%s RTP" % (kind, codec))

    def detach(self, pad):
        with self.lock:
            item = self.inputs.pop(pad, None)
            if not item:
                return
            kind, ghost, sink, _ = item
            track = self.tracks[kind]
            # Playback can still be waiting for preroll when a transport stops.
            # Wake its downstream chain before releasing the selector's stream
            # lock. Recording outputs retain queued data for mux finalization.
            flush = self.flush_on_detach and track['selector'].get_property('active-pad') == sink
            if flush:
                track['output'].push_event(self.Gst.Event.new_flush_start())
            pad.unlink(ghost)
            track["bin"].remove_pad(ghost)
            track["selector"].release_request_pad(sink)
            if flush:
                track['output'].push_event(self.Gst.Event.new_flush_stop(False))
            alternatives = [value for value in self.inputs.values() if value[0] == kind]
            if alternatives:
                chosen = max(alternatives, key=lambda value: value[3])
                track["selector"].set_property("active-pad", chosen[2])

    def close(self, on_removed=None):
        with self.lock:
            self.closed = True
            for pad in list(self.inputs):
                self.detach(pad)
            for track in self.tracks.values():
                if on_removed:
                    on_removed(None, track["output"])
                track["bin"].set_state(self.Gst.State.NULL)
                self.pipeline.remove(track["bin"])
                discard = track.get("discard")
                if discard:
                    discard.set_state(self.Gst.State.NULL)
                    self.pipeline.remove(discard)
            self.tracks.clear()


class WhepReceiver:
    """A restartable WHEP transport; the supplied RTP switch owns output lifetime."""

    def __init__(self, pipeline, output, configure_ice, log, video_codecs=("H264", "VP8"), latency=200):
        self.Gst, self.WebRTC, self.Sdp, self.GLib = _gst()
        self.pipeline, self.output = pipeline, output
        self.configure_ice, self.log = configure_ice, log
        self.video_codecs = video_codecs
        self.latency = max(10, int(latency))
        self.settings = None
        self.peer = None
        self.http = None
        self.epoch = 0
        self.timer = None
        self.attempt = 0
        self.stage = "stopped"
        self.pads = []
        self.next_retry = 0
        self.last_media = 0
        self._state_lock = threading.RLock()
        self.trickle = self.Gst.version()[:2] < (1, 20)
        self.patch_pending = False

    def update(self, settings):
        settings = normalize_settings(settings)
        with self._state_lock:
            if settings == self.settings and self.stage != "stopped":
                return
            self._stop_transport()
            self.settings = settings
            self.trickle = self.Gst.version()[:2] < (1, 20)
            self.attempt = 0
            self.next_retry = 0
            self.stage = "retry"
            if self.timer is None:
                self.timer = self.GLib.timeout_add(200, self._tick)

    def _defer(self, epoch, callback, *args):
        def run():
            with self._state_lock:
                if epoch == self.epoch and self.stage != "stopped":
                    try:
                        callback(*args)
                    except Exception as exc:
                        self._fail(str(exc))
            return False
        self.GLib.idle_add(run)

    def _promise(self, epoch, callback):
        def completed(promise, *_):
            reply = promise.get_reply()
            if reply and reply.has_field("error"):
                self._defer(epoch, self._fail, "GStreamer rejected WHEP SDP")
            else:
                # Promise-owned boxed SDP must be copied before crossing threads.
                offer = reply.get_value("offer").copy() if reply and reply.has_field("offer") else None
                self._defer(epoch, callback, offer)
        return self.Gst.Promise.new_with_change_func(completed, None, None)

    def _start(self):
        Gst = self.Gst
        self.patch_pending = False
        for element in ("webrtcbin", "nicesrc", "dtlssrtpdec", "rtpbin"):
            if not Gst.ElementFactory.find(element):
                raise RuntimeError("WHEP requires GStreamer %s; install the ordinary WebRTC plugins or use --nowhep" % element)
        self.epoch += 1
        epoch = self.epoch
        peer = Gst.ElementFactory.make("webrtcbin", "whep_" + uuid.uuid4().hex)
        self.peer = peer
        peer.set_property("bundle-policy", "max-bundle")
        if peer.find_property('latency'):
            peer.set_property('latency', self.latency)
        self.configure_ice(peer)
        peer.connect("pad-added", self._on_pad, epoch)
        peer.connect("pad-removed", lambda _peer, pad: self.output.detach(pad))
        self.pipeline.add(peer)
        self.pipeline.set_state(Gst.State.PLAYING)
        peer.sync_state_with_parent()
        direction = self.WebRTC.WebRTCRTPTransceiverDirection.RECVONLY
        locked = self.output.codecs()
        # Negotiate A/V even when an output is muted: some relays reject partial offers.
        audio = Gst.Caps.from_string("application/x-rtp,media=audio,encoding-name=OPUS,payload=111,clock-rate=48000,encoding-params=(string)2")
        peer.emit("add-transceiver", direction, audio)
        formats = []
        for codec, pt, depay in (("H264", 102, "rtph264depay"), ("VP8", 96, "rtpvp8depay"),
                                 ("VP9", 98, "rtpvp9depay"), ("AV1", 100, "rtpav1depay")):
            if codec not in self.video_codecs or (locked.get("video") and locked["video"] != codec):
                continue
            if not Gst.ElementFactory.find(depay):
                continue
            caps = "application/x-rtp,media=video,encoding-name=%s,payload=%d,clock-rate=90000" % (codec, pt)
            if codec == "H264":
                caps += ",packetization-mode=(string)1,level-asymmetry-allowed=(string)1,profile-level-id=(string)42e01f"
            formats.append(caps)
        if not formats:
            raise RuntimeError("No supported WHEP video depayloader; install RTP plugins or use --nowhep")
        video = peer.emit("add-transceiver", direction, Gst.Caps.from_string(";".join(formats)))
        # Preserve the application's legacy-1.18 RTX workaround.
        if video and Gst.version()[:2] >= (1, 20) and video.find_property('do-nack'):
            video.set_property('do-nack', True)
        self.stage = "offer"
        self.deadline = time.monotonic() + 30
        peer.emit("create-offer", None, self._promise(epoch, self._offer_created))
        self.log("WHEP %s: negotiating with relay (%s)" % (self.settings["media"], Gst.version_string()))

    def _offer_created(self, offer):
        if not offer:
            raise RuntimeError("GStreamer did not create a WHEP offer")
        self.peer.emit("set-local-description", offer,
                       self._promise(self.epoch, lambda _reply: setattr(self, "stage", "gathering")))

    def _post(self):
        offer = self.peer.get_property("local-description")
        if not offer:
            raise RuntimeError("No local WHEP description after ICE gathering")
        sdp = offer.sdp.as_text()
        epoch = self.epoch
        self.stage = "http"
        self.deadline = time.monotonic() + 100  # Includes bounded relay redirects.
        http = WhepHttpSession(self.settings["url"], self.settings["token"], trickle=self.trickle)
        # Register before POST so shutdown can cancel even a late HTTP response,
        # without needing the GLib loop to still be running to delete its resource.
        self.http = http
        def exchange():
            try:
                answer = http.offer(sdp)
            except Exception as exc:
                http.close()
                self._defer(epoch, self._http_failed, exc)
                return
            def accept():
                with self._state_lock:
                    if epoch != self.epoch or self.stage == "stopped":
                        threading.Thread(target=http.close, daemon=True).start()
                        return False
                    try:
                        result, parsed = self.Sdp.SDPMessage.new_from_text(answer)
                        if result != self.Sdp.SDPResult.OK:
                            raise RuntimeError("GStreamer could not parse the WHEP answer")
                        desc = self.WebRTC.WebRTCSessionDescription.new(self.WebRTC.WebRTCSDPType.ANSWER, parsed)
                        self.peer.emit("set-remote-description", desc, self._promise(epoch, self._answer_applied))
                    except Exception as exc:
                        self._fail(str(exc))
                return False
            self.GLib.idle_add(accept)
        threading.Thread(target=exchange, name="whep-http", daemon=True).start()

    def _answer_applied(self, _reply):
        self.stage = "connecting"
        self.last_media = time.monotonic()
        self.deadline = time.monotonic() + 30
        self.patch_pending = bool(self.http and self.http.trickle)

    def _patch_candidates(self):
        http, epoch = self.http, self.epoch
        if http:
            offer = self.peer.get_property('local-description')
            if not offer:
                raise RuntimeError('Missing local description for WHEP candidates')
            _, http.candidates = deferred_candidates(offer.sdp.as_text())
            self.patch_pending = False
            # On 1.18, a relay checking the gathered offer before its answer is
            # applied can leave ICE connected while DTLS packets never arrive
            # at webrtcbin. Expose candidates only after applying the answer.
            def patch():
                try:
                    http.send_candidates()
                except Exception as exc:
                    self._defer(epoch, self._http_failed, exc)
            threading.Thread(target=patch, name='whep-patch', daemon=True).start()

    def _http_failed(self, error):
        if isinstance(error, TrickleUnsupported):
            self.trickle = False
        self._fail(str(error))

    def _on_pad(self, peer, pad, epoch):
        if epoch != self.epoch or pad.get_direction() != self.Gst.PadDirection.SRC:
            return
        self.pads.append(pad)
        # Building an output from webrtcbin's streaming thread can race shutdown
        # (or block NULL waiting for that same thread). Hold buffers until the
        # GLib context has attached the existing application's output branch.
        block = pad.add_probe(self.Gst.PadProbeType.BLOCK_DOWNSTREAM,
                              lambda *_: self.Gst.PadProbeReturn.OK)
        def attach():
            try:
                with self._state_lock:
                    if epoch != self.epoch or self.stage == 'stopped':
                        return False
                    def media_received(_pad, _info):
                        if epoch == self.epoch:
                            self.last_media = time.monotonic()
                        return self.Gst.PadProbeReturn.OK
                    pad.add_probe(self.Gst.PadProbeType.BUFFER, media_received)
                    self.output.attach(peer, pad, relay=True)
            except Exception as exc:
                self._defer(epoch, self._fail, str(exc))
            finally:
                pad.remove_probe(block)
            return False
        self.GLib.idle_add(attach)

    def _tick(self):
        with self._state_lock:
            return self._poll()

    def _poll(self):
        try:
            now = time.monotonic()
            if (self.patch_pending and self.peer and self.peer.get_property('ice-gathering-state') ==
                    self.WebRTC.WebRTCICEGatheringState.COMPLETE):
                self._patch_candidates()
            if self.stage == "stopped":
                self.timer = None
                return False
            if self.stage == "retry":
                if now >= self.next_retry:
                    self._start()
            elif self.stage == "gathering":
                if self.trickle or self.peer.get_property("ice-gathering-state") == self.WebRTC.WebRTCICEGatheringState.COMPLETE:
                    self._post()
                elif now >= self.deadline:
                    self._fail("ICE gathering timed out; check STUN/TURN configuration")
            else:
                state = self.peer.get_property("connection-state") if self.peer else None
                if state == self.WebRTC.WebRTCPeerConnectionState.CONNECTED:
                    if self.last_media and now - self.last_media > 30:
                        self._fail("Relay connected but no RTP arrived for 30 seconds")
                        return True
                    if self.stage != "playing":
                        self.log("WHEP %s: relay connected" % self.settings["media"])
                    self.stage = "playing"
                    self.attempt = 0
                    self.deadline = now + 15
                elif state in (self.WebRTC.WebRTCPeerConnectionState.FAILED, self.WebRTC.WebRTCPeerConnectionState.CLOSED):
                    self._fail("Relay WebRTC connection failed")
                elif now >= self.deadline:
                    self._fail(negotiation_timeout(self.peer, self.Gst, self.trickle))
        except Exception as exc:
            self._fail(str(exc))
        return True

    def _fail(self, reason):
        self._stop_transport()
        self.attempt += 1
        delay = min(30, 2 ** min(self.attempt, 5))
        self.stage = "retry"
        self.next_retry = time.monotonic() + delay
        self.log("WHEP: %s; retrying in %ss (--nowhep requests P2P instead)" % (reason, delay))

    def _stop_transport(self):
        self.epoch += 1
        self.patch_pending = False
        peer, self.peer = self.peer, None
        for pad in self.pads:
            self.output.detach(pad)
        self.pads = []
        if peer:
            peer.set_state(self.Gst.State.NULL)
            self.pipeline.remove(peer)
        http, self.http = self.http, None
        if http:
            threading.Thread(target=http.close, name="whep-delete", daemon=True).start()

    def close(self):
        with self._state_lock:
            self.stage = "stopped"
            self._stop_transport()
            if self.timer is not None:
                self.GLib.source_remove(self.timer)
                self.timer = None
