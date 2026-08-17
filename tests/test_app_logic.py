import os
import tempfile
import unittest

_TEST_APPDATA = tempfile.TemporaryDirectory()
os.environ["APPDATA"] = _TEST_APPDATA.name

from luce_app import LuceApp


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class FakeSender:
    def __init__(self, fail=False):
        self.fail = fail
        self.updated = None
        self.sent = []

    def update(self, target_ip, universe):
        self.updated = (target_ip, universe)

    def send_dmx(self, dmx):
        if self.fail:
            raise OSError("simulated send failure")
        self.sent.append(dmx)


class ArtNetAppLogicTests(unittest.TestCase):
    def make_app(self, senders=None):
        app = object.__new__(LuceApp)
        app.ip_vars = [Value("2.0.0.10"), Value("2.0.0.11")]
        app.universe_vars = [Value(0), Value(0)]
        app.senders = senders or [FakeSender(), FakeSender()]
        app.last_artnet_error = None
        app.recorded_errors = None
        app._record_artnet_result = lambda errors: setattr(
            app, "recorded_errors", list(errors)
        )
        return app

    def test_second_node_still_sends_when_first_fails(self):
        first = FakeSender(fail=True)
        second = FakeSender()
        app = self.make_app([first, second])

        result = app._send_frame_to_nodes(b"dmx")

        self.assertFalse(result)
        self.assertEqual(second.sent, [b"dmx"])
        self.assertEqual(len(app.recorded_errors), 1)
        self.assertIn("FULGUR", app.recorded_errors[0])

    def test_blackout_repetition_is_sent_to_each_node(self):
        senders = [FakeSender(), FakeSender()]
        app = self.make_app(senders)

        result = app._send_frame_to_nodes(b"zero", repetitions=3)

        self.assertTrue(result)
        self.assertEqual(senders[0].sent, [b"zero"] * 3)
        self.assertEqual(senders[1].sent, [b"zero"] * 3)

    def test_invalid_ip_is_rejected_before_send(self):
        app = self.make_app()
        app.ip_vars[0] = Value("not-an-ip")

        with self.assertRaisesRegex(ValueError, "FULGUR IP"):
            app._node_endpoint(0)


if __name__ == "__main__":
    unittest.main()
