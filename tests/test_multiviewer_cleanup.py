import unittest
import threading

import publish


class FakePad:
    def __init__(self, name):
        self.name = name
        self.peer = None

    def link(self, peer):
        self.peer = peer
        peer.peer = self
        return publish.Gst.PadLinkReturn.OK

    def unlink(self, peer):
        if self.peer is peer:
            self.peer = None
            peer.peer = None
            return True
        return False

    def get_peer(self):
        return self.peer


class FakeElement:
    def __init__(self, name):
        self.name = name
        self.states = []
        self.unlinked = []
        self.sink_pad = FakePad(f"{name}-sink")
        self.requested_pads = []
        self.released_pads = []
        self.properties = {}

    def get_name(self):
        return self.name

    def set_state(self, state):
        self.states.append(state)

    def unlink(self, downstream):
        self.unlinked.append(downstream)
        return True

    def get_static_pad(self, name):
        return self.sink_pad if name == "sink" else None

    def request_pad_simple(self, name):
        pad = FakePad(f"src_{len(self.requested_pads)}")
        self.requested_pads.append(pad)
        return pad

    def release_request_pad(self, pad):
        self.released_pads.append(pad)

    def set_property(self, name, value):
        self.properties[name] = value


class FakePipeline:
    def __init__(self, elements=None):
        self.elements = {element.get_name(): element for element in (elements or [])}

    def get_by_name(self, name):
        return self.elements.get(name)

    def add(self, element):
        name = element.get_name()
        if name in self.elements:
            return False
        self.elements[name] = element
        return True

    def remove(self, element):
        return self.elements.pop(element.get_name(), None) is element


class FakeTimer:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class ReplacementDuringWaitPromise:
    def __init__(self, owner, uuid, replacement):
        self.owner = owner
        self.uuid = uuid
        self.replacement = replacement
        self.reply_requested = False

    def wait(self):
        self.owner.clients[self.uuid] = self.replacement

    def get_reply(self):
        self.reply_requested = True
        raise AssertionError("stale promise reply must not be consumed")


class MultiviewerCleanupTests(unittest.TestCase):
    def make_client(self, pipeline):
        client = publish.WebRTCClient.__new__(publish.WebRTCClient)
        client.pipe = pipeline
        return client

    def test_cleanup_removes_untracked_uuid_named_elements(self):
        uuid = "viewer-123"
        audio_tee = FakeElement("audiotee")
        video_tee = FakeElement("videotee")
        webrtc = FakeElement(uuid)
        audio_queue = FakeElement(f"qa-{uuid}")
        video_queue = FakeElement(f"qv-{uuid}")
        pipeline = FakePipeline(
            [audio_tee, video_tee, webrtc, audio_queue, video_queue]
        )
        audio_pad = audio_tee.request_pad_simple("src_%u")
        video_pad = video_tee.request_pad_simple("src_%u")
        audio_pad.link(audio_queue.get_static_pad("sink"))
        video_pad.link(video_queue.get_static_pad("sink"))
        owner = self.make_client(pipeline)
        peer = {"UUID": uuid, "webrtc": webrtc, "qa": None, "qv": None}

        owner._cleanup_multiviewer_client_elements(peer)

        self.assertEqual(set(pipeline.elements), {"audiotee", "videotee"})
        self.assertIn(audio_pad, audio_tee.released_pads)
        self.assertIn(video_pad, video_tee.released_pads)
        self.assertIn(webrtc, audio_queue.unlinked)
        self.assertIn(webrtc, video_queue.unlinked)
        self.assertIs(peer["webrtc"], webrtc)
        self.assertEqual(peer["qa"], None)
        self.assertEqual(peer["qv"], None)
        self.assertEqual(webrtc.states[-1], publish.Gst.State.NULL)

    def test_new_element_is_tracked_immediately_after_add(self):
        pipeline = FakePipeline()
        owner = self.make_client(pipeline)
        peer = {"UUID": "viewer-456"}
        queue = FakeElement("qv-viewer-456")

        result = owner._add_multiviewer_element(
            peer, "qv", queue, "video queue qv-viewer-456"
        )

        self.assertTrue(result)
        self.assertIs(peer["qv"], queue)
        self.assertIs(pipeline.get_by_name("qv-viewer-456"), queue)

    def test_duplicate_name_is_not_tracked(self):
        existing = FakeElement("viewer-789")
        pipeline = FakePipeline([existing])
        owner = self.make_client(pipeline)
        peer = {"UUID": "viewer-789", "webrtc": None}
        duplicate = FakeElement("viewer-789")

        result = owner._add_multiviewer_element(
            peer, "webrtc", duplicate, "webrtcbin viewer-789"
        )

        self.assertFalse(result)
        self.assertIsNone(peer["webrtc"])
        self.assertEqual(duplicate.states[-1], publish.Gst.State.NULL)
        self.assertIs(pipeline.get_by_name("viewer-789"), existing)

    def test_tee_request_pad_is_tracked_and_released(self):
        owner = self.make_client(FakePipeline())
        peer = {"UUID": "viewer-pad"}
        tee = FakeElement("videotee")
        queue = FakeElement("qv-viewer-pad")

        linked = owner._link_multiviewer_tee_branch(
            peer, "qv_tee_pad", tee, queue, "video branch"
        )
        request_pad = peer["qv_tee_pad"]
        owner._release_multiviewer_tee_branch(
            peer, "qv_tee_pad", tee, queue
        )

        self.assertTrue(linked)
        self.assertIn(request_pad, tee.released_pads)
        self.assertIsNone(peer["qv_tee_pad"])
        self.assertIsNone(queue.get_static_pad("sink").get_peer())
        self.assertTrue(tee.properties["allow-not-linked"])

    def test_reconnect_replaces_client_generation_and_cancels_old_timer(self):
        uuid = "viewer-reconnect"
        webrtc = FakeElement(uuid)
        pipeline = FakePipeline([webrtc])
        owner = self.make_client(pipeline)
        owner.pipeline_lock = threading.Lock()
        owner.view = False
        timer = FakeTimer()
        previous = {
            "UUID": uuid,
            "session": "session-1",
            "send_channel": object(),
            "timer": timer,
            "ping": 9,
            "webrtc": webrtc,
        }
        owner.clients = {uuid: previous}

        replacement = owner._replace_multiviewer_client_record(uuid)

        self.assertIs(owner.clients[uuid], replacement)
        self.assertIsNot(previous, replacement)
        self.assertTrue(timer.cancelled)
        self.assertEqual(replacement["session"], "session-1")
        self.assertIsNone(replacement["send_channel"])
        self.assertIsNone(replacement["timer"])
        self.assertEqual(replacement["ping"], 0)
        self.assertIsNone(pipeline.get_by_name(uuid))
        self.assertIs(previous["webrtc"], webrtc)
        self.assertFalse(owner._client_is_current(previous))

    def test_answer_callback_rechecks_generation_after_wait(self):
        uuid = "viewer-answer-race"
        owner = self.make_client(FakePipeline())
        current = {"UUID": uuid, "webrtc": FakeElement(uuid)}
        replacement = {"UUID": uuid, "webrtc": FakeElement(uuid)}
        owner.clients = {uuid: current}
        promise = ReplacementDuringWaitPromise(owner, uuid, replacement)

        owner.on_answer_created(promise, None, current)

        self.assertIs(owner.clients[uuid], replacement)
        self.assertFalse(promise.reply_requested)

    def test_stale_cleanup_does_not_remove_replacement_client(self):
        uuid = "viewer-stale"
        owner = self.make_client(FakePipeline())
        owner.pipeline_lock = threading.Lock()
        owner._shutdown_requested = False
        stale = {"UUID": uuid}
        replacement = {"UUID": uuid}
        owner.clients = {uuid: replacement}

        owner._stop_pipeline_internal(uuid, expected_client=stale)

        self.assertIs(owner.clients[uuid], replacement)


if __name__ == "__main__":
    unittest.main()
