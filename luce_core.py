from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import socket
import struct
from typing import Iterable, Optional

ARTNET_PORT = 6454


def clamp8(value: float) -> int:
    return max(0, min(255, int(round(value))))


def note_name(note: int) -> str:
    names = [
        "C", "C♯/D♭", "D", "D♯/E♭", "E", "F",
        "F♯/G♭", "G", "G♯/A♭", "A", "A♯/B♭", "B",
    ]
    return f"{names[note % 12]}{note // 12 - 1}"


@dataclass(frozen=True)
class ColorSpec:
    name: str
    rgb: tuple[int, int, int]


class LuceVoiceState:
    """
    One Luce player's currently held MIDI notes.

    The first max_notes struck notes remain assigned to lighting.
    Additional held notes are retained as overflow so the GUI can warn
    the player; an overflow note is promoted when an assigned note is
    released.
    """

    def __init__(self, max_notes: int = 3):
        if max_notes < 1:
            raise ValueError("max_notes must be >= 1")
        self.max_notes = int(max_notes)
        self._active: OrderedDict[int, int] = OrderedDict()

    def note_on(self, note: int, velocity: int = 100) -> None:
        note = int(note)
        self._active[note] = int(velocity)

    def note_off(self, note: int) -> None:
        self._active.pop(int(note), None)

    def clear(self) -> None:
        self._active.clear()

    @property
    def active_notes(self) -> list[int]:
        return sorted(self._active.keys())

    @property
    def selected_notes(self) -> list[int]:
        first = list(self._active.keys())[: self.max_notes]
        return sorted(first)

    @property
    def overflow_notes(self) -> list[int]:
        selected = set(self.selected_notes)
        return sorted(n for n in self._active if n not in selected)

    @property
    def is_overflow(self) -> bool:
        return len(self._active) > self.max_notes

    def six_outputs(self, output_count: int = 6) -> list[Optional[int]]:
        notes = self.selected_notes
        if not notes:
            return [None] * output_count
        return [notes[i % len(notes)] for i in range(output_count)]


def blend_rgb(base: tuple[int, int, int],
              target: tuple[int, int, int],
              amount: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, float(amount)))
    return tuple(
        clamp8(a + (b - a) * t)
        for a, b in zip(base, target)
    )


def scale_rgb(rgb: tuple[int, int, int],
              level: float) -> tuple[int, int, int]:
    k = max(0.0, min(1.0, float(level)))
    return tuple(clamp8(v * k) for v in rgb)


def pitch_color(note: Optional[int], pitch_colors: dict) -> ColorSpec:
    if note is None:
        return ColorSpec("Blackout", (0, 0, 0))
    spec = pitch_colors[str(note % 12)]
    return ColorSpec(
        str(spec["name"]),
        tuple(int(v) for v in spec["rgb"]),
    )


def logical_output_colors(
    output_notes: Iterable[Optional[int]],
    pitch_colors: dict,
    final_white_level: float = 0.0,
) -> list[tuple[int, int, int]]:
    t = max(0.0, min(1.0, float(final_white_level)))
    result = []
    for note in output_notes:
        base = pitch_color(note, pitch_colors).rgb
        result.append(blend_rgb(base, (255, 255, 255), t))
    return result


def validate_fixture_map(fixtures: list[dict]) -> list[str]:
    errors: list[str] = []
    if len(fixtures) != 12:
        errors.append(f"Expected 12 fixtures/logical outputs, got {len(fixtures)}.")

    used: dict[int, str] = {}
    for idx, fixture in enumerate(fixtures, start=1):
        for field in ("r", "g", "b", "w", "dimmer"):
            channel = fixture.get(field)
            if channel in (None, 0, ""):
                continue
            try:
                channel = int(channel)
            except Exception:
                errors.append(f"Fixture {idx} {field}: invalid channel {channel!r}.")
                continue
            if not 1 <= channel <= 512:
                errors.append(f"Fixture {idx} {field}: channel {channel} outside 1..512.")
            if channel in used:
                errors.append(
                    f"DMX channel {channel} used by both {used[channel]} "
                    f"and fixture {idx} {field}."
                )
            else:
                used[channel] = f"fixture {idx} {field}"
    return errors


def build_dmx_frame(
    logical_notes: list[Optional[int]],
    fixtures: list[dict],
    pitch_colors: dict,
    master: float = 1.0,
    final_white_level: float = 0.0,
) -> bytes:
    if len(logical_notes) != 12:
        raise ValueError("logical_notes must contain exactly 12 outputs")
    if len(fixtures) != 12:
        raise ValueError("fixtures must contain exactly 12 output definitions")

    errors = validate_fixture_map(fixtures)
    if errors:
        raise ValueError("; ".join(errors))

    max_channel = 2
    for fixture in fixtures:
        for field in ("r", "g", "b", "w", "dimmer"):
            ch = fixture.get(field)
            if ch:
                max_channel = max(max_channel, int(ch))
    length = max_channel if max_channel % 2 == 0 else max_channel + 1
    if length > 512:
        raise ValueError("DMX frame exceeds 512 channels")

    frame = bytearray(length)
    master = max(0.0, min(1.0, float(master)))
    white_t = max(0.0, min(1.0, float(final_white_level)))

    for note, fixture in zip(logical_notes, fixtures):
        base = pitch_color(note, pitch_colors).rgb
        has_white = bool(fixture.get("w"))
        has_dimmer = bool(fixture.get("dimmer"))
        active = (note is not None) or (white_t > 0.0)

        if has_white:
            rgb = scale_rgb(base, 1.0 - white_t)
            white = clamp8(255 * white_t)
        else:
            rgb = blend_rgb(base, (255, 255, 255), white_t)
            white = 0

        if not has_dimmer:
            rgb = scale_rgb(rgb, master)
            white = clamp8(white * master)

        frame[int(fixture["r"]) - 1] = rgb[0]
        frame[int(fixture["g"]) - 1] = rgb[1]
        frame[int(fixture["b"]) - 1] = rgb[2]

        if has_white:
            frame[int(fixture["w"]) - 1] = white

        if has_dimmer:
            frame[int(fixture["dimmer"]) - 1] = (
                clamp8(255 * master) if active else 0
            )

    return bytes(frame)


class ArtNetSender:
    """Direct-unicast ArtDmx sender."""

    PORT = ARTNET_PORT
    ID = b"Art-Net\x00"
    OP_DMX = 0x5000
    PROTOCOL_VERSION = 14

    def __init__(self, target_ip: str, universe: int):
        self.target_ip = str(target_ip)
        self.universe = int(universe)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sequence = 0

    def update(self, target_ip: str, universe: int) -> None:
        self.target_ip = str(target_ip)
        self.universe = int(universe)

    def close(self) -> None:
        try:
            self.sock.close()
        except Exception:
            pass

    def make_packet(self, dmx: bytes) -> bytes:
        if not (2 <= len(dmx) <= 512):
            raise ValueError("DMX payload length must be 2..512")
        if len(dmx) % 2:
            dmx += b"\x00"

        self.sequence = (self.sequence % 255) + 1
        port_address = self.universe & 0x7FFF
        sub_uni = port_address & 0xFF
        net = (port_address >> 8) & 0x7F
        length = len(dmx)

        return (
            self.ID
            + struct.pack("<H", self.OP_DMX)
            + bytes([
                0,
                self.PROTOCOL_VERSION,
                self.sequence,
                0,
                sub_uni,
                net,
                (length >> 8) & 0xFF,
                length & 0xFF,
            ])
            + dmx
        )

    def send_dmx(self, dmx: bytes) -> None:
        self.sock.sendto(
            self.make_packet(dmx),
            (self.target_ip, self.PORT),
        )
