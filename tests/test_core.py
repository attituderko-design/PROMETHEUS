import json
import os
import tempfile
import unittest
from pathlib import Path

from luce_core import (
    ArtNetSender,
    LuceVoiceState,
    build_dmx_frame,
    validate_fixture_map,
)
from luce_defaults import fresh_default_config, merge_with_defaults

COLORS = {}
for pc in range(12):
    COLORS[str(pc)] = {"name": str(pc), "rgb": [pc * 10, pc * 5, pc * 3]}
COLORS["0"] = {"name": "red", "rgb": [255, 0, 0]}
COLORS["4"] = {"name": "blue-green", "rgb": [0, 100, 100]}
COLORS["7"] = {"name": "orange", "rgb": [255, 100, 0]}


def rgb_fixtures():
    out = []
    for i in range(12):
        base = i * 3 + 1
        out.append({
            "name": f"O{i+1}",
            "r": base,
            "g": base + 1,
            "b": base + 2,
            "w": None,
            "dimmer": None,
        })
    return out


class VoiceTests(unittest.TestCase):
    def test_one_note(self):
        v = LuceVoiceState(3)
        v.note_on(60)
        self.assertEqual(v.six_outputs(), [60] * 6)

    def test_two_notes(self):
        v = LuceVoiceState(3)
        v.note_on(67)
        v.note_on(60)
        self.assertEqual(v.six_outputs(), [60, 67, 60, 67, 60, 67])

    def test_three_notes(self):
        v = LuceVoiceState(3)
        for n in (67, 60, 64):
            v.note_on(n)
        self.assertEqual(v.six_outputs(), [60, 64, 67, 60, 64, 67])

    def test_overflow(self):
        v = LuceVoiceState(3)
        for n in (60, 64, 67, 71):
            v.note_on(n)
        self.assertTrue(v.is_overflow)
        self.assertEqual(v.selected_notes, [60, 64, 67])
        self.assertEqual(v.overflow_notes, [71])
        v.note_off(64)
        self.assertFalse(v.is_overflow)
        self.assertEqual(v.selected_notes, [60, 67, 71])


class DmxTests(unittest.TestCase):
    def test_map(self):
        self.assertEqual(validate_fixture_map(rgb_fixtures()), [])

    def test_required_rgb_channels_cannot_be_empty(self):
        fixtures = rgb_fixtures()
        fixtures[0]["r"] = None
        errors = validate_fixture_map(fixtures)
        self.assertTrue(any("Fixture 1 r: channel is required" in e for e in errors))
        with self.assertRaisesRegex(ValueError, "Fixture 1 r"):
            build_dmx_frame([60] * 12, fixtures, COLORS)

    def test_fixture_must_be_an_object(self):
        fixtures = rgb_fixtures()
        fixtures[0] = None
        errors = validate_fixture_map(fixtures)
        self.assertTrue(any("Fixture 1: expected an object" in e for e in errors))

    def test_fractional_channel_is_rejected(self):
        fixtures = rgb_fixtures()
        fixtures[0]["r"] = 1.5
        errors = validate_fixture_map(fixtures)
        self.assertTrue(any("Fixture 1 r: invalid channel" in e for e in errors))

    def test_twelve_outputs(self):
        v1 = LuceVoiceState(3)
        v2 = LuceVoiceState(3)
        v1.note_on(60)
        v1.note_on(67)
        v2.note_on(66)
        notes = v1.six_outputs() + v2.six_outputs()
        self.assertEqual(notes[:6], [60, 67, 60, 67, 60, 67])
        self.assertEqual(notes[6:], [66] * 6)

    def test_final_white(self):
        frame = build_dmx_frame(
            [60] * 12, rgb_fixtures(), COLORS,
            master=1.0, final_white_level=1.0
        )
        self.assertEqual(frame[0:3], bytes([255, 255, 255]))
        self.assertEqual(frame[33:36], bytes([255, 255, 255]))

    def test_blackout(self):
        frame = build_dmx_frame(
            [None] * 12, rgb_fixtures(), COLORS,
            master=1.0, final_white_level=0.0
        )
        self.assertEqual(set(frame), {0})

    def test_artdmx_packet(self):
        sender = ArtNetSender("127.0.0.1", 0)
        try:
            dmx = bytes(range(36))
            packet = sender.make_packet(dmx)
            self.assertEqual(packet[:8], b"Art-Net\x00")
            self.assertEqual(packet[8:10], bytes([0x00, 0x50]))
            self.assertEqual(packet[10:12], bytes([0x00, 0x0E]))
            self.assertEqual(packet[12], 1)
            self.assertEqual(packet[14:16], bytes([0x00, 0x00]))
            self.assertEqual(packet[16:18], bytes([0x00, 36]))
            self.assertEqual(packet[18:], dmx)
        finally:
            sender.close()


class ConfigTests(unittest.TestCase):
    def test_defaults_are_independent(self):
        a = fresh_default_config()
        b = fresh_default_config()
        a["artnet"]["luce1"]["target_ip"] = "1.2.3.4"
        self.assertNotEqual(a["artnet"]["luce1"]["target_ip"], b["artnet"]["luce1"]["target_ip"])

    def test_merge_preserves_user_setting(self):
        merged = merge_with_defaults({
            "master_brightness": 0.5,
            "artnet": {"target_ip": "10.0.0.2", "universe": 3},
        })
        self.assertEqual(merged["master_brightness"], 0.5)
        self.assertEqual(merged["artnet"]["luce1"]["target_ip"], "10.0.0.2")
        self.assertEqual(merged["artnet"]["luce1"]["universe"], 3)
        self.assertEqual(merged["artnet"]["luce2"]["target_ip"], "2.0.0.11")
        self.assertIn("fixtures", merged["dmx"])


if __name__ == "__main__":
    unittest.main()
