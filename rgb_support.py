"""RGB normalization and HID command helpers."""

RGB_COLOR_PRESETS = [
    "#FF0000",
    "#00FFFF",
    "#8B00FF",
    "#00FF00",
    "#FF8000",
    "#FF00FF",
    "#FFFFFF",
    "#0000FF",
]
RGB_DEFAULT_BRIGHTNESS = 100
LEGION_RGB_BRIGHTNESS_MAX = 63
RGB_DEFAULT_MODE = "solid"
RGB_SPEED_OPTIONS = ("low", "medium", "high")
RGB_DEFAULT_SPEED = "medium"


def clamp_int(value, minimum: int, maximum: int) -> int:
    try:
        numeric = int(round(float(value)))
    except Exception:
        numeric = minimum
    return max(minimum, min(maximum, numeric))


def normalize_rgb_brightness(brightness) -> int:
    return clamp_int(brightness, 0, 100)


def normalize_rgb_color(color: str) -> str | None:
    if not isinstance(color, str):
        return None

    normalized = color.strip().upper()
    if normalized.startswith("#"):
        normalized = normalized[1:]

    if len(normalized) != 6:
        return None

    if any(char not in "0123456789ABCDEF" for char in normalized):
        return None

    return f"#{normalized}"


def normalize_rgb_speed(speed: str | None) -> str:
    if not isinstance(speed, str):
        return RGB_DEFAULT_SPEED
    normalized = speed.strip().lower()
    return normalized if normalized in RGB_SPEED_OPTIONS else RGB_DEFAULT_SPEED


def get_rgb_supported_modes(backend: dict) -> list[str]:
    if backend["type"] == "legion_hid":
        protocol = backend.get("device", {}).get("config", {}).get("protocol")
        if protocol in {"legion_go_s", "legion_go_tablet"}:
            return ["solid", "pulse", "rainbow", "spiral"]
        return ["solid", "pulse", "rainbow"]
    if backend["type"] == "asus_hid":
        return ["solid", "pulse", "rainbow", "spiral"]
    if backend["type"] == "sysfs":
        return ["solid"]
    return []


def get_rgb_mode_capabilities(backend: dict) -> dict[str, dict]:
    supported_modes = get_rgb_supported_modes(backend)
    capabilities = {}
    for mode in supported_modes:
        capabilities[mode] = {
            "color": mode in {"solid", "pulse"},
            "brightness": True,
            "speed": backend["type"] in {"legion_hid", "asus_hid"} and mode in {"pulse", "rainbow", "spiral"},
        }
    return capabilities


def get_saved_rgb_mode(settings: dict, backend: dict) -> str:
    supported_modes = get_rgb_supported_modes(backend)
    if not supported_modes:
        return RGB_DEFAULT_MODE
    mode = str(settings.get("rgb_mode", supported_modes[0]) or supported_modes[0]).strip().lower()
    return mode if mode in supported_modes else supported_modes[0]


def scale_rgb_brightness_to_raw(brightness: int, maximum: int) -> int:
    if maximum <= 0:
        return 0
    brightness = normalize_rgb_brightness(brightness)
    return int(round((brightness / 100) * maximum))


def scale_rgb_brightness_from_raw(raw_value: int, maximum: int) -> int:
    if maximum <= 0:
        return RGB_DEFAULT_BRIGHTNESS
    return clamp_int((raw_value / maximum) * 100, 0, 100)


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    rgb = color.lstrip("#")
    return int(rgb[0:2], 16), int(rgb[2:4], 16), int(rgb[4:6], 16)


def rgb_hid_padded(payload: list[int]) -> bytes:
    return bytes(payload) + bytes(max(0, 64 - len(payload)))


def asus_rgb_brightness_level(brightness: int) -> int:
    normalized = normalize_rgb_brightness(brightness)
    if normalized <= 0:
        return 0x00
    if normalized <= 33:
        return 0x01
    if normalized <= 66:
        return 0x02
    return 0x03


def asus_rgb_config_command(boot: bool = False, charging: bool = False) -> bytes:
    value = 0x02
    if boot:
        value += 0x09
    if charging:
        value += 0x04
    return rgb_hid_padded([0x5A, 0xD1, 0x09, 0x01, value])


def legion_go_s_rgb_commands(
    color: str,
    enabled: bool,
    brightness: int = RGB_DEFAULT_BRIGHTNESS,
    mode: str = RGB_DEFAULT_MODE,
    speed: str = RGB_DEFAULT_SPEED,
) -> list[bytes]:
    if not enabled:
        return [bytes([0x04, 0x06, 0x00])]

    r, g, b = hex_to_rgb(color)
    profile = 3
    mode_map = {
        "solid": 0,
        "pulse": 1,
        "rainbow": 2,
        "spiral": 3,
    }
    speed_map = {
        "low": 21,
        "medium": 42,
        "high": 63,
    }
    raw_brightness = scale_rgb_brightness_to_raw(brightness, LEGION_RGB_BRIGHTNESS_MAX)
    return [
        bytes([0x04, 0x06, 0x01]),
        bytes([0x10, 0x02, profile]),
        bytes([
            0x10,
            profile + 2,
            mode_map.get(mode, 0),
            r,
            g,
            b,
            raw_brightness,
            speed_map.get(speed, speed_map[RGB_DEFAULT_SPEED]),
        ]),
    ]


def legion_go_tablet_rgb_commands(
    color: str,
    enabled: bool,
    brightness: int = RGB_DEFAULT_BRIGHTNESS,
    mode: str = RGB_DEFAULT_MODE,
    speed: str = RGB_DEFAULT_SPEED,
) -> list[bytes]:
    def enable_command(controller: int, value: bool) -> bytes:
        return bytes([0x05, 0x06, 0x70, 0x02, controller, 0x01 if value else 0x00, 0x01])

    if not enabled:
        return [enable_command(0x03, False), enable_command(0x04, False)]

    r, g, b = hex_to_rgb(color)
    profile = 3
    mode_map = {
        "solid": 1,
        "pulse": 2,
        "rainbow": 3,
        "spiral": 4,
    }
    speed_map = {
        "low": 42,
        "medium": 21,
        "high": 0,
    }
    raw_brightness = scale_rgb_brightness_to_raw(brightness, LEGION_RGB_BRIGHTNESS_MAX)
    period = speed_map.get(speed, speed_map[RGB_DEFAULT_SPEED])
    commands = []
    for controller in (0x03, 0x04):
        commands.append(bytes([
            0x05,
            0x0C,
            0x72,
            0x01,
            controller,
            mode_map.get(mode, 1),
            r,
            g,
            b,
            raw_brightness,
            period,
            profile,
            0x01,
        ]))
    for controller in (0x03, 0x04):
        commands.append(bytes([0x05, 0x06, 0x73, 0x02, controller, profile, 0x01]))
    commands.extend([enable_command(0x03, True), enable_command(0x04, True)])
    return commands


def asus_hid_rgb_commands(
    color: str,
    enabled: bool,
    brightness: int = RGB_DEFAULT_BRIGHTNESS,
    mode: str = RGB_DEFAULT_MODE,
    speed: str = RGB_DEFAULT_SPEED,
) -> list[bytes]:
    if not enabled:
        return [rgb_hid_padded([0x5A, 0xBA, 0xC5, 0xC4, 0x00])]

    r, g, b = hex_to_rgb(color)
    mode_map = {
        "solid": 0x00,
        "pulse": 0x01,
        "rainbow": 0x02,
        "spiral": 0x03,
    }
    speed_map = {
        "low": 0xE1,
        "medium": 0xEB,
        "high": 0xF5,
    }
    mode_value = mode_map.get(mode, 0x00)
    speed_value = 0x00 if mode == "solid" else speed_map.get(speed, speed_map[RGB_DEFAULT_SPEED])
    if mode == "spiral":
        r, g, b = 0, 0, 0
    payload = [0x5A, 0xB3, 0x00, mode_value, r, g, b, speed_value, 0x00, 0x00, 0x00, 0x00, 0x00]
    return [
        asus_rgb_config_command(),
        rgb_hid_padded([0x5A, 0xBA, 0xC5, 0xC4, asus_rgb_brightness_level(brightness)]),
        rgb_hid_padded(payload),
        rgb_hid_padded([0x5A, 0xB5]),
        rgb_hid_padded([0x5A, 0xB4]),
    ]


def legion_hid_rgb_commands(
    device: dict,
    color: str,
    enabled: bool,
    brightness: int = RGB_DEFAULT_BRIGHTNESS,
    mode: str = RGB_DEFAULT_MODE,
    speed: str = RGB_DEFAULT_SPEED,
) -> list[bytes]:
    protocol = device["config"]["protocol"]
    if protocol == "legion_go_s":
        return legion_go_s_rgb_commands(color, enabled, brightness, mode, speed)
    if protocol == "legion_go_tablet":
        return legion_go_tablet_rgb_commands(color, enabled, brightness, mode, speed)
    if protocol == "asus_ally":
        return asus_hid_rgb_commands(color, enabled, brightness, mode, speed)
    return []
