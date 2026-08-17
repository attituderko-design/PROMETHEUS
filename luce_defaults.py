from __future__ import annotations

import copy

APP_NAME = "ScriabinLuce"
APP_DISPLAY_NAME = "PROMETHEUS — Scriabin Luce Controller"
APP_VERSION = "0.6.3"
CONFIG_SCHEMA = 2
SOFTWARE_CODENAME = "PROMETHEUS"
LUCE_CODENAMES = ["FULGUR", "AURORA"]

PITCH_COLORS = {
    "0":  {"pitch": "C",       "name": "Plain red",                                 "rgb": [255, 0, 0]},
    "1":  {"pitch": "C♯/D♭",   "name": "Pure violet",                               "rgb": [125, 35, 175]},
    "2":  {"pitch": "D",       "name": "Sunny yellow",                              "rgb": [255, 215, 0]},
    "3":  {"pitch": "D♯/E♭",   "name": "Steely blue, metallic",                     "rgb": [90, 125, 150]},
    "4":  {"pitch": "E",       "name": "Dark blue-greenish (light blue)",            "rgb": [35, 105, 125]},
    "5":  {"pitch": "F",       "name": "Dark red",                                  "rgb": [135, 0, 18]},
    "6":  {"pitch": "F♯/G♭",   "name": "Deep dark blue with a shade of violet",      "rgb": [48, 35, 145]},
    "7":  {"pitch": "G",       "name": "Orange (red-yellow), fiery",                 "rgb": [255, 95, 0]},
    "8":  {"pitch": "G♯/A♭",   "name": "Lily-colored, reddish",                      "rgb": [190, 85, 155]},
    "9":  {"pitch": "A",       "name": "Grass green",                               "rgb": [65, 175, 65]},
    "10": {"pitch": "A♯/B♭",   "name": "Metallic leaden grey",                      "rgb": [105, 108, 118]},
    "11": {"pitch": "B",       "name": "Dark blue with light blueness (light blue)", "rgb": [45, 85, 170]},
}

FIXTURES = []
for i in range(12):
    base = i * 3 + 1
    FIXTURES.append({
        "name": f"Logical Output {i + 1} RGB",
        "r": base,
        "g": base + 1,
        "b": base + 2,
        "w": None,
        "dimmer": None,
    })

DEFAULT_CONFIG = {
    "schema": CONFIG_SCHEMA,
    "max_notes_per_luce": 3,
    "master_brightness": 0.72,
    "pc_keyboard": {
        "enabled": True,
    },
    "artnet": {
        "enabled": False,
        "luce1": {
            "target_ip": "2.0.0.10",
            "universe": 0,
        },
        "luce2": {
            "target_ip": "2.0.0.11",
            "universe": 0,
        },
    },
    "dmx": {
        "fixtures": FIXTURES,
    },
    "pitch_class_colors": PITCH_COLORS,
    "source_notes": {
        "color_names": "1913 Parisian Score color table; RGB values are modern approximations.",
        "final_white": "mm.592-593 annotation: crescendo, becoming glaring, white.",
    },
}


def fresh_default_config() -> dict:
    return copy.deepcopy(DEFAULT_CONFIG)


def merge_with_defaults(user_config: dict | None) -> dict:
    """
    Preserve user settings while adding newly introduced default keys.
    Lists are treated atomically; dictionaries merge recursively.
    """
    base = fresh_default_config()
    if not isinstance(user_config, dict):
        return base

    # v0.5 -> v0.6 migration: the old single Art-Net destination becomes
    # Luce 1. Luce 2 receives its new independent default destination.
    user_config = copy.deepcopy(user_config)
    old_artnet = user_config.get("artnet")
    if isinstance(old_artnet, dict) and "luce1" not in old_artnet:
        if "target_ip" in old_artnet or "universe" in old_artnet:
            old_artnet["luce1"] = {
                "target_ip": old_artnet.get("target_ip", base["artnet"]["luce1"]["target_ip"]),
                "universe": old_artnet.get("universe", base["artnet"]["luce1"]["universe"]),
            }

    def merge(dst, src):
        for key, value in src.items():
            if key not in dst:
                continue
            if isinstance(dst[key], dict) and isinstance(value, dict):
                merge(dst[key], value)
            else:
                dst[key] = value

    merge(base, user_config)
    base["schema"] = CONFIG_SCHEMA
    return base
