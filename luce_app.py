from __future__ import annotations

import json
import logging
import os
import threading
import time
import tkinter as tk
import sys
from ipaddress import IPv4Address
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import messagebox, ttk

try:
    import pygame
    import pygame.midi
except ImportError:
    pygame = None

from luce_core import (
    ArtNetSender,
    LuceVoiceState,
    build_dmx_frame,
    logical_output_colors,
    note_name,
    pitch_color,
    validate_fixture_map,
)
from luce_defaults import (
    APP_DISPLAY_NAME,
    APP_NAME,
    APP_VERSION,
    LUCE_CODENAMES,
    fresh_default_config,
    merge_with_defaults,
)

PIANO_LOW = 21
PIANO_HIGH = 108
WHITE_PCS = {0, 2, 4, 5, 7, 9, 11}
BLACK_PCS = {1, 3, 6, 8, 10}
ARTNET_REFRESH_MS = 200
ARTNET_BLACKOUT_REPETITIONS = 3

# Laptop keyboard is a first-class performance input, not a test-only feature.
# Both banks map one chromatic octave (C4-B4); pitch class determines Luce color.
PC_KEYBOARD_MAPS = [
    {
        "q": 60, "2": 61, "w": 62, "3": 63, "e": 64, "r": 65,
        "5": 66, "t": 67, "6": 68, "y": 69, "7": 70, "u": 71,
    },
    {
        "z": 60, "s": 61, "x": 62, "d": 63, "c": 64, "v": 65,
        "g": 66, "b": 67, "h": 68, "n": 69, "j": 70, "m": 71,
    },
]

# Windows virtual-key fallback.  This makes performance input independent of
# IME/keysym quirks on Japanese Windows keyboards.  Values are standard VK
# codes for the alphanumeric keys used by the two Luce banks.
PC_WINDOWS_VK_MAPS = [
    {
        0x51: 60, 0x32: 61, 0x57: 62, 0x33: 63, 0x45: 64, 0x52: 65,
        0x35: 66, 0x54: 67, 0x36: 68, 0x59: 69, 0x37: 70, 0x55: 71,
    },
    {
        0x5A: 60, 0x53: 61, 0x58: 62, 0x44: 63, 0x43: 64, 0x56: 65,
        0x47: 66, 0x42: 67, 0x48: 68, 0x4E: 69, 0x4A: 70, 0x4D: 71,
    },
]

PC_KEYBOARD_LABELS = [
    "Q 2 W 3 E R 5 T 6 Y 7 U",
    "Z S X D C V G B H N J M",
]


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        path = Path(base) / APP_NAME
    else:
        path = Path.home() / f".{APP_NAME}"
    path.mkdir(parents=True, exist_ok=True)
    return path


DATA_DIR = app_data_dir()
CONFIG_PATH = DATA_DIR / "config.json"
LOG_PATH = DATA_DIR / "luce.log"

_log_handler = RotatingFileHandler(
    LOG_PATH,
    maxBytes=1_000_000,
    backupCount=3,
    encoding="utf-8",
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[_log_handler],
)


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return fresh_default_config()
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            return merge_with_defaults(json.load(f))
    except Exception:
        logging.exception("Config load failed; using defaults.")
        return fresh_default_config()


def save_config_file(config: dict) -> None:
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    tmp.replace(CONFIG_PATH)


def decode_name(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


class Piano88Canvas(tk.Canvas):
    def __init__(self, parent, click_callback=None, **kwargs):
        kwargs.setdefault("height", 118)
        kwargs.setdefault("background", "#303030")
        kwargs.setdefault("highlightthickness", 0)
        super().__init__(parent, **kwargs)

        self.click_callback = click_callback
        self.active_notes: set[int] = set()
        self.selected_notes: set[int] = set()
        self.color_fn = None
        self._key_regions = []

        self.bind("<Configure>", lambda _e: self.redraw())
        self.bind("<Button-1>", self._on_click)

    def set_notes(self, active_notes, selected_notes, color_fn):
        self.active_notes = set(active_notes)
        self.selected_notes = set(selected_notes)
        self.color_fn = color_fn
        self.redraw()

    def _fill_for(self, note, default):
        if note not in self.active_notes or self.color_fn is None:
            return default
        rgb = self.color_fn(note)
        return "#{:02x}{:02x}{:02x}".format(*rgb)

    def redraw(self):
        self.delete("all")
        self._key_regions.clear()

        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())

        white_notes = [
            n for n in range(PIANO_LOW, PIANO_HIGH + 1)
            if n % 12 in WHITE_PCS
        ]
        white_w = width / len(white_notes)
        black_w = white_w * 0.62
        black_h = height * 0.62
        white_index = {}

        for idx, note in enumerate(white_notes):
            x0 = idx * white_w
            x1 = (idx + 1) * white_w
            white_index[note] = idx

            selected = note in self.selected_notes
            overflow = note in self.active_notes and not selected
            outline = "#ff3030" if overflow else ("#00a8d8" if selected else "#666666")
            line_w = 3 if (selected or overflow) else 1

            self.create_rectangle(
                x0, 0, x1, height,
                fill=self._fill_for(note, "#f4f4f4"),
                outline=outline,
                width=line_w,
            )
            self._key_regions.append((note, x0, 0, x1, height, False))

        for note in range(PIANO_LOW, PIANO_HIGH + 1):
            if note % 12 not in BLACK_PCS:
                continue
            prev_white = note - 1
            if prev_white not in white_index:
                continue

            boundary = (white_index[prev_white] + 1) * white_w
            x0 = boundary - black_w / 2
            x1 = boundary + black_w / 2

            selected = note in self.selected_notes
            overflow = note in self.active_notes and not selected
            outline = "#ff3030" if overflow else ("#00a8d8" if selected else "#050505")
            line_w = 3 if (selected or overflow) else 1

            self.create_rectangle(
                x0, 0, x1, black_h,
                fill=self._fill_for(note, "#171717"),
                outline=outline,
                width=line_w,
            )
            self._key_regions.append((note, x0, 0, x1, black_h, True))

        for note in range(24, 109, 12):
            if note in white_index:
                idx = white_index[note]
                self.create_text(
                    (idx + 0.5) * white_w,
                    height - 10,
                    text=f"C{note // 12 - 1}",
                    fill="#555555",
                    font=("Segoe UI", 7),
                )

    def _on_click(self, event):
        if not self.click_callback:
            return
        for want_black in (True, False):
            for note, x0, y0, x1, y1, is_black in reversed(self._key_regions):
                if is_black != want_black:
                    continue
                if x0 <= event.x <= x1 and y0 <= event.y <= y1:
                    self.click_callback(note)
                    return


class LuceApp:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.max_notes = int(self.cfg.get("max_notes_per_luce", 3))

        self.voices = [
            LuceVoiceState(self.max_notes),
            LuceVoiceState(self.max_notes),
        ]

        self.inputs = [None, None]
        self.input_threads = [None, None]
        self.stop_events = [threading.Event(), threading.Event()]
        self.port_map = {}

        # Track which physical/logical source is holding each note.  This makes
        # MIDI and laptop keyboard valid at the same time without premature
        # note-off when both happen to hold the same pitch.
        self.note_sources = [dict(), dict()]
        self.pc_pressed_keys = set()

        self.final_white_level = 0.0
        self.last_artnet_error = None

        self.senders = [
            ArtNetSender(
                self.cfg["artnet"]["luce1"]["target_ip"],
                self.cfg["artnet"]["luce1"]["universe"],
            ),
            ArtNetSender(
                self.cfg["artnet"]["luce2"]["target_ip"],
                self.cfg["artnet"]["luce2"]["universe"],
            ),
        ]

        self.root.title(f"{APP_DISPLAY_NAME} {APP_VERSION}")
        self.root.geometry("1380x930")
        self.root.minsize(1080, 760)

        self._init_midi()
        self._validate_startup()
        self._build_ui()
        self._bind_pc_keyboard()
        # The PC keyboard is a performance input.  Give the application a
        # neutral focus target at startup so the first keystroke is playable
        # instead of being swallowed by a readonly MIDI combobox.
        self.root.after_idle(self.root.focus_set)
        self.refresh_midi_ports()
        self._schedule_artnet_refresh()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _init_midi(self):
        if pygame is None:
            return
        pygame.midi.init()

    def _validate_startup(self):
        errors = validate_fixture_map(self.cfg["dmx"]["fixtures"])
        if errors:
            raise ValueError("Invalid DMX fixture map:\n" + "\n".join(errors))

    def _build_ui(self):
        devices = ttk.LabelFrame(self.root, text="MIDI Players", padding=9)
        devices.pack(fill="x", padx=10, pady=(10, 6))
        devices.columnconfigure(1, weight=1)
        devices.columnconfigure(5, weight=1)

        ttk.Label(devices, text="Player 1 / Luce 1").grid(row=0, column=0, sticky="w")
        self.port_vars = [tk.StringVar(), tk.StringVar()]
        self.port_combos = []

        combo1 = ttk.Combobox(devices, textvariable=self.port_vars[0], state="readonly")
        combo1.grid(row=0, column=1, padx=6, sticky="ew")
        self.port_combos.append(combo1)

        self.status_labels = [
            ttk.Label(devices, text="未接続"),
            ttk.Label(devices, text="未接続"),
        ]
        self.status_labels[0].grid(row=0, column=2, padx=6)

        ttk.Separator(devices, orient="vertical").grid(
            row=0, column=3, sticky="ns", padx=10
        )

        ttk.Label(devices, text="Player 2 / Luce 2").grid(row=0, column=4, sticky="w")
        combo2 = ttk.Combobox(devices, textvariable=self.port_vars[1], state="readonly")
        combo2.grid(row=0, column=5, padx=6, sticky="ew")
        self.port_combos.append(combo2)
        self.status_labels[1].grid(row=0, column=6, padx=6)

        ttk.Button(devices, text="再読込", command=self.refresh_midi_ports).grid(
            row=0, column=7, padx=4
        )
        self.connect_button = ttk.Button(
            devices, text="2台接続", command=self.toggle_all_inputs
        )
        self.connect_button.grid(row=0, column=8, padx=4)

        self.pc_keyboard_enabled = tk.BooleanVar(
            value=bool(self.cfg.get("pc_keyboard", {}).get("enabled", True))
        )
        keyboard_row = ttk.Frame(devices)
        keyboard_row.grid(row=1, column=0, columnspan=9, sticky="ew", pady=(8, 0))
        ttk.Checkbutton(
            keyboard_row,
            text="PC Keyboard Performance Input",
            variable=self.pc_keyboard_enabled,
            command=self._pc_keyboard_toggle_changed,
        ).pack(side="left")
        ttk.Label(
            keyboard_row,
            text=f"Luce 1 [{LUCE_CODENAMES[0]}]: {PC_KEYBOARD_LABELS[0]}",
        ).pack(side="left", padx=(16, 12))
        ttk.Label(
            keyboard_row,
            text=f"Luce 2 [{LUCE_CODENAMES[1]}]: {PC_KEYBOARD_LABELS[1]}",
        ).pack(side="left", padx=(0, 12))
        ttk.Label(
            keyboard_row,
            text="C4–B4 / MIDI未接続でも演奏可",
        ).pack(side="right")

        light = ttk.LabelFrame(self.root, text="Lighting / Art-Net", padding=9)
        light.pack(fill="x", padx=10, pady=6)

        self.artnet_enabled = tk.BooleanVar(value=bool(self.cfg["artnet"]["enabled"]))
        ttk.Checkbutton(
            light,
            text="Art-Net出力",
            variable=self.artnet_enabled,
            command=self._artnet_toggle_changed,
        ).grid(row=0, column=0, padx=(0, 8))

        ttk.Label(light, text=f"Luce 1 [{LUCE_CODENAMES[0]}] IP").grid(row=0, column=1)
        self.ip_vars = [
            tk.StringVar(value=self.cfg["artnet"]["luce1"]["target_ip"]),
            tk.StringVar(value=self.cfg["artnet"]["luce2"]["target_ip"]),
        ]
        self.universe_vars = [
            tk.IntVar(value=int(self.cfg["artnet"]["luce1"]["universe"])),
            tk.IntVar(value=int(self.cfg["artnet"]["luce2"]["universe"])),
        ]
        ttk.Entry(light, textvariable=self.ip_vars[0], width=13).grid(
            row=0, column=2, padx=4
        )
        ttk.Label(light, text="U").grid(row=0, column=3)
        ttk.Spinbox(
            light, from_=0, to=32767, width=4, textvariable=self.universe_vars[0]
        ).grid(row=0, column=4, padx=(0, 6))

        ttk.Label(light, text=f"Luce 2 [{LUCE_CODENAMES[1]}] IP").grid(row=0, column=5)
        ttk.Entry(light, textvariable=self.ip_vars[1], width=13).grid(
            row=0, column=6, padx=4
        )
        ttk.Label(light, text="U").grid(row=0, column=7)
        ttk.Spinbox(
            light, from_=0, to=32767, width=4, textvariable=self.universe_vars[1]
        ).grid(row=0, column=8, padx=(0, 6))

        ttk.Label(light, text="Master").grid(row=0, column=9, padx=(12, 3))
        self.master_var = tk.DoubleVar(
            value=float(self.cfg.get("master_brightness", 0.72)) * 100
        )
        ttk.Scale(
            light, from_=0, to=100, length=145,
            variable=self.master_var,
            command=lambda _v: self.render_and_output(),
        ).grid(row=0, column=10)
        self.master_label = ttk.Label(light, width=5)
        self.master_label.grid(row=0, column=11, padx=(3, 8))

        ttk.Label(light, text="FINAL WHITE").grid(row=0, column=12, padx=(10, 3))
        self.white_var = tk.DoubleVar(value=0.0)
        ttk.Scale(
            light, from_=0, to=100, length=145,
            variable=self.white_var,
            command=self._white_slider_changed,
        ).grid(row=0, column=13)
        self.white_label = ttk.Label(light, width=5)
        self.white_label.grid(row=0, column=14, padx=(3, 6))

        ttk.Button(
            light, text="WHITE 100%", command=self.toggle_final_white
        ).grid(row=0, column=15, padx=4)

        ttk.Button(light, text="PANIC / BLACKOUT", command=self.panic).grid(
            row=0, column=16, padx=(12, 4)
        )

        ttk.Button(light, text="設定保存", command=self.save_config).grid(
            row=0, column=17, padx=4
        )

        ttk.Button(light, text="設定初期化", command=self.reset_config).grid(
            row=0, column=18, padx=4
        )

        info = ttk.Frame(self.root, padding=(12, 0))
        info.pack(fill="x")
        ttk.Label(
            info,
            text=(
                "MIDI / PC Keyboard は同格の演奏入力。各Player最大3音 → 6出力へ循環配置 "
                "(1音=AAAAAA / 2音=ABABAB / 3音=ABCABC)"
            )
        ).pack(side="left")
        ttk.Label(info, text="F12 = FINAL WHITE 0/100%").pack(side="right")

        self.rows = []
        for voice_idx in range(2):
            out_start = 1 if voice_idx == 0 else 7
            frame = ttk.LabelFrame(
                self.root,
                text=f"Player {voice_idx + 1} / Luce {voice_idx + 1} [{LUCE_CODENAMES[voice_idx]}] "
                     f"— Outputs {out_start}–{out_start + 5}",
                padding=8,
            )
            frame.pack(fill="both", expand=True, padx=10, pady=5)

            top = ttk.Frame(frame)
            top.pack(fill="x")

            chord_label = ttk.Label(
                top, text="—", font=("Segoe UI Semibold", 14), width=32
            )
            chord_label.pack(side="left")

            warning_label = ttk.Label(
                top, text="", font=("Segoe UI Semibold", 10)
            )
            warning_label.pack(side="left", padx=8)

            ttk.Button(
                top, text="Clear",
                command=lambda i=voice_idx: self.clear_voice(i)
            ).pack(side="right")

            piano = Piano88Canvas(
                frame,
                height=118,
                click_callback=lambda note, i=voice_idx: self.toggle_sim_note(i, note),
            )
            piano.pack(fill="both", expand=True, pady=(5, 7))

            outputs_frame = ttk.Frame(frame)
            outputs_frame.pack(fill="x")
            for col in range(6):
                outputs_frame.columnconfigure(col, weight=1)

            output_widgets = []
            for slot in range(6):
                logical_num = out_start + slot
                cell = ttk.Frame(outputs_frame, padding=(2, 0))
                cell.grid(row=0, column=slot, sticky="ew", padx=2)
                ttk.Label(
                    cell, text=f"OUT {logical_num}", anchor="center"
                ).pack(fill="x")
                swatch = tk.Canvas(
                    cell, height=40, bg="#000000", highlightthickness=1
                )
                swatch.pack(fill="x")
                note_lbl = ttk.Label(cell, text="—", anchor="center")
                note_lbl.pack(fill="x")
                output_widgets.append((swatch, note_lbl))

            self.rows.append({
                "chord": chord_label,
                "warning": warning_label,
                "piano": piano,
                "outputs": output_widgets,
            })

        bottom = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        bottom.pack(fill="x")

        self.artnet_status = ttk.Label(bottom, text="Art-Net: OFF")
        self.artnet_status.pack(side="left")

        ttk.Label(
            bottom,
            text=(
                f"設定: {CONFIG_PATH}  |  ログ: {LOG_PATH}"
            )
        ).pack(side="right")

        self.log = tk.Text(self.root, height=4, state="disabled")
        self.log.pack(fill="x", padx=10, pady=(0, 10))

        self.root.bind("<F12>", lambda _e: self.toggle_final_white())
        self.render_and_output()

    def _bind_pc_keyboard(self):
        # bind_all keeps the laptop keyboard available as a real performance
        # input anywhere in the window. Text-entry widgets are explicitly
        # excluded so typing an IP address cannot trigger notes.
        self.root.bind_all("<KeyPress>", self._pc_key_press, add="+")
        self.root.bind_all("<KeyRelease>", self._pc_key_release, add="+")
        self.root.bind_all("<FocusOut>", self._pc_focus_out, add="+")

    def _pc_focus_out(self, _event=None):
        # A KeyRelease is delivered to whichever application owns focus at
        # release time. Defer until Tk has completed the focus transition.
        self.root.after_idle(self._clear_pc_keyboard_if_unfocused)

    def _clear_pc_keyboard_if_unfocused(self):
        try:
            if self.root.focus_displayof() is None:
                self._clear_pc_keyboard_notes()
        except tk.TclError:
            pass

    @staticmethod
    def _is_editable_text_input(widget):
        # Only suppress performance notes while the user is ACTUALLY typing
        # editable configuration text.  Readonly MIDI comboboxes and the
        # disabled log are not text-entry contexts and must not block notes.
        if isinstance(widget, (tk.Entry, ttk.Entry, ttk.Spinbox)):
            try:
                return str(widget.cget("state")) not in ("disabled", "readonly")
            except Exception:
                return True
        if isinstance(widget, ttk.Combobox):
            try:
                return str(widget.cget("state")) != "readonly"
            except Exception:
                return False
        if isinstance(widget, tk.Text):
            try:
                return str(widget.cget("state")) != "disabled"
            except Exception:
                return True
        return False

    def _lookup_pc_key_event(self, event):
        # First use Tk's symbolic key name.
        key = str(getattr(event, "keysym", "")).lower()
        for voice_idx, mapping in enumerate(PC_KEYBOARD_MAPS):
            if key in mapping:
                return voice_idx, key, mapping[key]

        # On Windows, Japanese IME/layout states can produce awkward keysyms.
        # Fall back to the physical alphanumeric virtual-key code.
        if sys.platform.startswith("win"):
            try:
                vk = int(getattr(event, "keycode", -1))
            except Exception:
                vk = -1
            for voice_idx, mapping in enumerate(PC_WINDOWS_VK_MAPS):
                if vk in mapping:
                    # Stable token keeps press/release pairing independent of IME.
                    return voice_idx, f"vk{vk:02x}", mapping[vk]
        return None

    def _pc_key_press(self, event):
        if not self.pc_keyboard_enabled.get():
            return
        if self._is_editable_text_input(event.widget):
            return
        # Do not turn Ctrl/Alt shortcuts into notes.
        if int(getattr(event, "state", 0)) & 0x000C:
            return
        hit = self._lookup_pc_key_event(event)
        if hit is None:
            return
        voice_idx, key, note = hit
        token = (voice_idx, key)
        if token in self.pc_pressed_keys:
            return  # OS key repeat
        self.pc_pressed_keys.add(token)
        self._source_note_on(voice_idx, f"pc:{key}", note, 100)
        return "break"

    def _pc_key_release(self, event):
        hit = self._lookup_pc_key_event(event)
        if hit is None:
            return
        voice_idx, key, note = hit
        token = (voice_idx, key)
        if token not in self.pc_pressed_keys:
            return
        self.pc_pressed_keys.discard(token)
        self._source_note_off(voice_idx, f"pc:{key}", note)
        return "break"

    def _pc_keyboard_toggle_changed(self):
        if not self.pc_keyboard_enabled.get():
            self._clear_pc_keyboard_notes()
        self.render_and_output()

    def _clear_pc_keyboard_notes(self):
        for voice_idx in range(2):
            for note, sources in list(self.note_sources[voice_idx].items()):
                for source in list(sources):
                    if source.startswith("pc:"):
                        self._source_note_off(voice_idx, source, note, render=False)
        self.pc_pressed_keys.clear()
        if hasattr(self, "rows"):
            self.render_and_output()

    def _source_note_on(self, voice_idx, source, note, velocity=100, render=True):
        source_map = self.note_sources[voice_idx]
        sources = source_map.setdefault(int(note), set())
        if source in sources:
            return
        first_source = not sources
        sources.add(source)
        if first_source:
            self.voices[voice_idx].note_on(note, velocity)
        if render:
            self.render_and_output()

    def _source_note_off(self, voice_idx, source, note, render=True):
        source_map = self.note_sources[voice_idx]
        sources = source_map.get(int(note))
        if not sources:
            return
        sources.discard(source)
        if not sources:
            source_map.pop(int(note), None)
            self.voices[voice_idx].note_off(note)
        if render:
            self.render_and_output()

    def gui_log(self, text):
        logging.info(text)
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def refresh_midi_ports(self):
        if pygame is None:
            for combo in self.port_combos:
                combo["values"] = []
            self.gui_log("pygame-ce がありません。")
            return

        if any(self.inputs):
            self.gui_log("MIDI接続中はデバイス一覧を再読込できません。")
            return

        labels = []
        port_map = {}
        try:
            if not pygame.midi.get_init():
                pygame.midi.init()

            for device_id in range(pygame.midi.get_count()):
                info = pygame.midi.get_device_info(device_id)
                if not info:
                    continue
                interface, name, is_input, _is_output, opened = info
                if not is_input:
                    continue
                label = (
                    f"ID {device_id} | {decode_name(name)} "
                    f"[{decode_name(interface)}]"
                )
                if opened:
                    label += " (open)"
                labels.append(label)
                port_map[label] = device_id

            self.port_map = port_map
            for combo in self.port_combos:
                combo["values"] = labels

            if labels:
                if self.port_vars[0].get() not in labels:
                    self.port_vars[0].set(labels[0])
                if len(labels) >= 2 and self.port_vars[1].get() not in labels:
                    self.port_vars[1].set(labels[1])
                elif len(labels) == 1 and self.port_vars[1].get() not in labels:
                    self.port_vars[1].set("")
            else:
                self.gui_log("MIDI入力デバイスが見つかりません。")

        except Exception as exc:
            self.gui_log(f"MIDI列挙エラー: {exc}")

    def toggle_all_inputs(self):
        if any(self.inputs):
            self.disconnect_all_inputs()
        else:
            self.connect_all_inputs()

    def connect_all_inputs(self):
        if pygame is None:
            messagebox.showerror("MIDI", "pygame-ce が利用できません。")
            return

        labels = [v.get() for v in self.port_vars]
        if any(label not in self.port_map for label in labels):
            messagebox.showwarning(
                "MIDI",
                "Player 1 / Player 2 のMIDI入力をそれぞれ選択してください。"
            )
            return

        ids = [self.port_map[label] for label in labels]
        if ids[0] == ids[1]:
            messagebox.showwarning(
                "MIDI",
                "同じMIDI入力を2人に割り当てています。"
            )
            return

        opened = []
        try:
            for i, device_id in enumerate(ids):
                self.stop_events[i].clear()
                midi_input = pygame.midi.Input(device_id, buffer_size=1024)
                self.inputs[i] = midi_input
                opened.append(i)

                thread = threading.Thread(
                    target=self._midi_loop,
                    args=(i,),
                    daemon=True,
                )
                self.input_threads[i] = thread
                thread.start()
                self.status_labels[i].config(text=f"接続 ID {device_id}")

            self.connect_button.config(text="2台切断")
            self.gui_log(
                f"MIDI接続: Player1={labels[0]} / Player2={labels[1]}"
            )

        except Exception as exc:
            for i in opened:
                try:
                    self.inputs[i].close()
                except Exception:
                    pass
                self.inputs[i] = None
            messagebox.showerror("MIDI接続エラー", str(exc))
            self.gui_log(f"MIDI接続エラー: {exc}")

    def disconnect_all_inputs(self):
        for i in range(2):
            self.stop_events[i].set()
            midi_input = self.inputs[i]
            self.inputs[i] = None
            if midi_input is not None:
                try:
                    midi_input.close()
                except Exception:
                    pass
            if hasattr(self, "status_labels"):
                self.status_labels[i].config(text="未接続")
            # Disconnecting external MIDI must not kill the laptop keyboard,
            # which is an independent first-class performance input.
            for note, sources in list(self.note_sources[i].items()):
                if "midi" in sources:
                    self._source_note_off(i, "midi", note, render=False)

        if hasattr(self, "connect_button"):
            self.connect_button.config(text="2台接続")
        if hasattr(self, "rows"):
            self.render_and_output()

    def _midi_loop(self, voice_idx):
        try:
            while not self.stop_events[voice_idx].is_set():
                midi_input = self.inputs[voice_idx]
                if midi_input is None:
                    break

                if not midi_input.poll():
                    time.sleep(0.002)
                    continue

                for event_data, _timestamp in midi_input.read(64):
                    status = int(event_data[0])
                    data1 = int(event_data[1])
                    data2 = int(event_data[2])
                    msg_type = status & 0xF0

                    if msg_type == 0x90 and data2 > 0:
                        self.root.after(
                            0, self.handle_note_on,
                            voice_idx, data1, data2
                        )
                    elif msg_type == 0x80 or (msg_type == 0x90 and data2 == 0):
                        self.root.after(
                            0, self.handle_note_off,
                            voice_idx, data1
                        )
                    elif msg_type == 0xB0 and data1 in (120, 123):
                        self.root.after(0, self.clear_voice, voice_idx)

        except Exception as exc:
            if not self.stop_events[voice_idx].is_set():
                self.root.after(
                    0, self._input_failed, voice_idx, str(exc)
                )

    def _input_failed(self, voice_idx, error):
        self.stop_events[voice_idx].set()
        failed_input = self.inputs[voice_idx]
        self.inputs[voice_idx] = None
        if failed_input is not None:
            try:
                failed_input.close()
            except Exception:
                pass
        for note, sources in list(self.note_sources[voice_idx].items()):
            if "midi" in sources:
                self._source_note_off(voice_idx, "midi", note, render=False)
        self.status_labels[voice_idx].config(text="ERROR / 切断")
        self.render_and_output()
        self.gui_log(
            f"Player {voice_idx + 1} MIDI ERROR: {error}"
        )

    def handle_note_on(self, voice_idx, note, velocity):
        self._source_note_on(voice_idx, "midi", note, velocity)

    def handle_note_off(self, voice_idx, note):
        self._source_note_off(voice_idx, "midi", note)

    def toggle_sim_note(self, voice_idx, note):
        # Mouse piano remains a simulation aid. Clicking an active note clears
        # that pitch from all sources; clicking an inactive note adds a mouse source.
        if note in self.voices[voice_idx].active_notes:
            self.note_sources[voice_idx].pop(int(note), None)
            self.voices[voice_idx].note_off(note)
            self.render_and_output()
        else:
            self._source_note_on(voice_idx, "mouse", note, 100)

    def clear_voice(self, voice_idx):
        self.note_sources[voice_idx].clear()
        self.pc_pressed_keys = {
            token for token in self.pc_pressed_keys if token[0] != voice_idx
        }
        self.voices[voice_idx].clear()
        self.render_and_output()

    def _white_slider_changed(self, _value=None):
        self.final_white_level = max(
            0.0, min(1.0, self.white_var.get() / 100.0)
        )
        self.render_and_output()

    def toggle_final_white(self):
        new_value = 0.0 if self.final_white_level >= 0.999 else 1.0
        self.final_white_level = new_value
        self.white_var.set(new_value * 100)
        self.render_and_output()
        self.gui_log(
            "FINAL WHITE 100%" if new_value else "FINAL WHITE OFF"
        )

    def panic(self):
        for source_map in self.note_sources:
            source_map.clear()
        self.pc_pressed_keys.clear()
        for voice in self.voices:
            voice.clear()
        self.final_white_level = 0.0
        if hasattr(self, "white_var"):
            self.white_var.set(0.0)
        if hasattr(self, "rows"):
            self.render_and_output()
            self.send_blackout_artnet(ARTNET_BLACKOUT_REPETITIONS)
        self.gui_log("PANIC / BLACKOUT")

    def _pitch_rgb(self, note):
        return pitch_color(note, self.cfg["pitch_class_colors"]).rgb

    def _all_logical_notes(self):
        return self.voices[0].six_outputs(6) + self.voices[1].six_outputs(6)

    def render_and_output(self, force_send=False):
        master = max(0.0, min(1.0, self.master_var.get() / 100.0))
        self.master_label.config(text=f"{round(master * 100):.0f}%")
        self.white_label.config(text=f"{round(self.final_white_level * 100):.0f}%")

        for voice_idx, voice in enumerate(self.voices):
            active = voice.active_notes
            selected = voice.selected_notes
            outputs = voice.six_outputs(6)

            chord_text = " + ".join(note_name(n) for n in active) if active else "—"
            self.rows[voice_idx]["chord"].config(text=chord_text)

            if voice.is_overflow:
                ignored = ", ".join(note_name(n) for n in voice.overflow_notes)
                self.rows[voice_idx]["warning"].config(
                    text=f"OVERFLOW: {ignored} は出力対象外",
                    foreground="#c00000",
                )
            else:
                self.rows[voice_idx]["warning"].config(text="")

            self.rows[voice_idx]["piano"].set_notes(
                active, selected, self._pitch_rgb
            )

            colors = logical_output_colors(
                outputs,
                self.cfg["pitch_class_colors"],
                self.final_white_level,
            )

            for slot, (note, rgb) in enumerate(zip(outputs, colors)):
                swatch, note_lbl = self.rows[voice_idx]["outputs"][slot]
                swatch.configure(bg="#{:02x}{:02x}{:02x}".format(*rgb))
                if self.final_white_level >= 0.999:
                    note_lbl.config(
                        text=(note_name(note) if note is not None else "—") + " / WHITE"
                    )
                else:
                    note_lbl.config(text=note_name(note) if note is not None else "—")

        if self.artnet_enabled.get() or force_send:
            self.send_artnet()

        self._update_artnet_status()

    def _node_endpoint(self, idx):
        codename = LUCE_CODENAMES[idx]
        raw_ip = self.ip_vars[idx].get().strip()
        try:
            target_ip = str(IPv4Address(raw_ip))
        except Exception as exc:
            raise ValueError(f"{codename} IPが不正です: {raw_ip!r}") from exc

        try:
            universe = int(self.universe_vars[idx].get())
        except Exception as exc:
            raise ValueError(f"{codename} Universeが整数ではありません") from exc
        if not 0 <= universe <= 32767:
            raise ValueError(f"{codename} Universeは0～32767で指定してください")
        return target_ip, universe

    def _record_artnet_result(self, errors):
        message = " / ".join(errors) if errors else None
        if message == self.last_artnet_error:
            self._update_artnet_status()
            return

        previous_error = self.last_artnet_error
        self.last_artnet_error = message
        if message is not None:
            self.gui_log(f"Art-Net送信エラー: {message}")
        elif previous_error is not None:
            self.gui_log("Art-Net送信が復旧しました。")
        self._update_artnet_status()

    def _update_artnet_status(self):
        if not hasattr(self, "artnet_status"):
            return
        if self.last_artnet_error:
            self.artnet_status.config(text=f"Art-Net: ERROR | {self.last_artnet_error}")
        elif self.artnet_enabled.get():
            self.artnet_status.config(
                text=(
                    f"Art-Net: ON | L1 {self.ip_vars[0].get()} U{self.universe_vars[0].get()} "
                    f"| L2 {self.ip_vars[1].get()} U{self.universe_vars[1].get()}"
                )
            )
        else:
            self.artnet_status.config(text="Art-Net: OFF")

    def _send_frame_to_nodes(self, dmx, repetitions=1):
        errors = []
        count = max(1, int(repetitions))
        for idx, sender in enumerate(self.senders):
            try:
                target_ip, universe = self._node_endpoint(idx)
                sender.update(target_ip, universe)
                for _ in range(count):
                    sender.send_dmx(dmx)
            except Exception as exc:
                errors.append(f"{LUCE_CODENAMES[idx]}: {exc}")
        self._record_artnet_result(errors)
        return not errors

    def send_artnet(self):
        try:
            dmx = build_dmx_frame(
                self._all_logical_notes(),
                self.cfg["dmx"]["fixtures"],
                self.cfg["pitch_class_colors"],
                master=self.master_var.get() / 100.0,
                final_white_level=self.final_white_level,
            )
        except Exception as exc:
            self._record_artnet_result([f"DMX frame: {exc}"])
            return False

        # Both independent nodes receive the same 12-output ArtDmx frame.
        # Luce 1 consumes channels 1-18; Luce 2 consumes channels 19-36.
        return self._send_frame_to_nodes(dmx)

    def send_blackout_artnet(self, repetitions=ARTNET_BLACKOUT_REPETITIONS):
        try:
            dmx = build_dmx_frame(
                [None] * 12,
                self.cfg["dmx"]["fixtures"],
                self.cfg["pitch_class_colors"],
                master=0.0,
                final_white_level=0.0,
            )
        except Exception as exc:
            self._record_artnet_result([f"blackout frame: {exc}"])
            return False
        return self._send_frame_to_nodes(dmx, repetitions=repetitions)

    def _artnet_toggle_changed(self):
        if self.artnet_enabled.get():
            self.render_and_output(force_send=True)
            self.gui_log("Art-Net出力 ON")
        else:
            self.send_blackout_artnet(ARTNET_BLACKOUT_REPETITIONS)
            self._update_artnet_status()
            self.gui_log("Art-Net出力 OFF / BLACKOUT送信")

    def _schedule_artnet_refresh(self):
        if self.artnet_enabled.get():
            self.send_artnet()
        self.root.after(ARTNET_REFRESH_MS, self._schedule_artnet_refresh)

    def save_config(self):
        try:
            endpoints = [self._node_endpoint(idx) for idx in range(2)]
        except ValueError as exc:
            messagebox.showerror("Art-Net設定", str(exc))
            return

        self.cfg["artnet"]["enabled"] = bool(self.artnet_enabled.get())
        for idx, key in enumerate(("luce1", "luce2")):
            target_ip, universe = endpoints[idx]
            self.cfg["artnet"][key]["target_ip"] = target_ip
            self.cfg["artnet"][key]["universe"] = universe
        self.cfg["master_brightness"] = self.master_var.get() / 100.0
        self.cfg.setdefault("pc_keyboard", {})["enabled"] = bool(
            self.pc_keyboard_enabled.get()
        )

        try:
            save_config_file(self.cfg)
        except Exception as exc:
            logging.exception("Config save failed")
            messagebox.showerror("設定保存エラー", str(exc))
            return
        self.gui_log(f"設定を保存しました: {CONFIG_PATH}")

    def reset_config(self):
        if not messagebox.askyesno(
            "設定初期化",
            "Art-Net / DMX / 色設定を初期値へ戻しますか？\nアプリを再起動すると反映されます。"
        ):
            return
        save_config_file(fresh_default_config())
        messagebox.showinfo(
            "設定初期化",
            f"初期設定を保存しました。\n{CONFIG_PATH}\n\nアプリを再起動してください。"
        )

    def on_close(self):
        try:
            self.panic()
        except Exception:
            pass
        self.disconnect_all_inputs()
        for sender in self.senders:
            sender.close()

        if pygame is not None:
            try:
                pygame.midi.quit()
            except Exception:
                pass

        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        LuceApp(root)
    except Exception as exc:
        logging.exception("Startup failure")
        messagebox.showerror(APP_DISPLAY_NAME, str(exc))
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()
