"""High-level RGB orchestration for the plugin."""

from rgb_support import (
    RGB_COLOR_PRESETS,
    RGB_DEFAULT_BRIGHTNESS,
    RGB_DEFAULT_MODE,
    RGB_DEFAULT_SPEED,
    RGB_SPEED_OPTIONS,
)


class RgbController:
    def __init__(
        self,
        *,
        logger,
        get_settings,
        get_platform_support,
        get_rgb_backend,
        get_rgb_supported_modes,
        get_rgb_mode_capabilities,
        read_rgb_state_from_led,
        get_saved_rgb_mode,
        normalize_rgb_speed,
        normalize_rgb_color,
        get_saved_rgb_brightness,
        normalize_rgb_brightness,
        set_led_color,
        write_hid_rgb,
        save_settings,
        debug_attempt,
        debug_success,
        debug_failure,
    ):
        self.logger = logger
        self.get_settings = get_settings
        self.get_platform_support = get_platform_support
        self.get_rgb_backend = get_rgb_backend
        self.get_rgb_supported_modes = get_rgb_supported_modes
        self.get_rgb_mode_capabilities = get_rgb_mode_capabilities
        self.read_rgb_state_from_led = read_rgb_state_from_led
        self.get_saved_rgb_mode = get_saved_rgb_mode
        self.normalize_rgb_speed = normalize_rgb_speed
        self.normalize_rgb_color = normalize_rgb_color
        self.get_saved_rgb_brightness = get_saved_rgb_brightness
        self.normalize_rgb_brightness = normalize_rgb_brightness
        self.set_led_color = set_led_color
        self.write_hid_rgb = write_hid_rgb
        self.save_settings = save_settings
        self.debug_attempt = debug_attempt
        self.debug_success = debug_success
        self.debug_failure = debug_failure

    def _settings(self) -> dict:
        return self.get_settings()

    def _unsupported_state(self, reason: str) -> dict:
        return {
            "available": False,
            "enabled": False,
            "mode": "solid",
            "color": RGB_COLOR_PRESETS[0],
            "brightness": RGB_DEFAULT_BRIGHTNESS,
            "speed": RGB_DEFAULT_SPEED,
            "brightness_available": False,
            "supports_free_color": False,
            "speed_available": False,
            "capabilities": {
                "toggle": False,
                "color": False,
                "brightness": False,
            },
            "supported_modes": [],
            "mode_capabilities": {},
            "speed_options": list(RGB_SPEED_OPTIONS),
            "presets": RGB_COLOR_PRESETS,
            "details": reason,
        }

    def _ensure_supported(self, action: str, details: dict | None = None) -> tuple[bool, dict | None]:
        support = self.get_platform_support()
        if support.get("supported", False):
            return True, None
        reason = support.get("reason", "Platform is not supported")
        self.logger.warning(reason)
        self.debug_failure("rgb", action, reason, details)
        return False, support

    def _ensure_backend(self, action: str, backend: dict, details: dict | None = None) -> bool:
        if backend["type"] != "none":
            return True
        self.logger.warning("RGB control not available")
        self.debug_failure("rgb", action, "RGB control not available", details)
        return False

    def _current_hid_state(self, backend: dict) -> tuple[bool, str, int, str, str]:
        settings = self._settings()
        enabled = bool(settings.get("rgb_enabled", False))
        color = self.normalize_rgb_color(settings.get("rgb_color", RGB_COLOR_PRESETS[0])) or RGB_COLOR_PRESETS[0]
        brightness = self.get_saved_rgb_brightness()
        mode = self.get_saved_rgb_mode(backend)
        speed = self.normalize_rgb_speed(settings.get("rgb_speed", RGB_DEFAULT_SPEED))
        return enabled, color, brightness, mode, speed

    async def get_state(self) -> dict:
        support = self.get_platform_support()
        if not support.get("supported", False):
            return self._unsupported_state(support.get("reason", "Platform is not supported"))

        backend = self.get_rgb_backend()
        supported_modes = self.get_rgb_supported_modes(backend)
        mode_capabilities = self.get_rgb_mode_capabilities(backend)
        if backend["type"] == "sysfs":
            enabled, color, brightness = self.read_rgb_state_from_led(backend["path"])
            mode = self.get_saved_rgb_mode(backend)
            speed = self.normalize_rgb_speed(self._settings().get("rgb_speed", RGB_DEFAULT_SPEED))
        elif backend["type"] in {"legion_hid", "asus_hid"}:
            enabled, color, brightness, mode, speed = self._current_hid_state(backend)
        else:
            enabled, color, brightness = False, RGB_COLOR_PRESETS[0], RGB_DEFAULT_BRIGHTNESS
            mode = RGB_DEFAULT_MODE
            speed = RGB_DEFAULT_SPEED

        return {
            "available": backend["type"] != "none",
            "enabled": enabled,
            "mode": mode,
            "color": color,
            "brightness": brightness,
            "speed": speed,
            "brightness_available": backend["type"] != "none",
            "supports_free_color": backend["type"] != "none",
            "speed_available": bool(mode_capabilities.get(mode, {}).get("speed", False)),
            "capabilities": {
                "toggle": backend["type"] != "none",
                "color": bool(mode_capabilities.get(mode, {}).get("color", backend["type"] != "none")),
                "brightness": backend["type"] != "none",
            },
            "supported_modes": supported_modes,
            "mode_capabilities": mode_capabilities,
            "speed_options": list(RGB_SPEED_OPTIONS),
            "presets": RGB_COLOR_PRESETS,
            "details": backend["details"],
        }

    async def set_enabled(self, enabled: bool) -> bool:
        self.debug_attempt("rgb", "set_enabled", "Changing RGB enabled state", {"enabled": enabled})
        ok, _support = self._ensure_supported("set_enabled")
        if not ok:
            return False

        backend = self.get_rgb_backend()
        if not self._ensure_backend("set_enabled", backend):
            return False

        if backend["type"] == "sysfs":
            _current_enabled, current_color, current_brightness = self.read_rgb_state_from_led(backend["path"])
            success = self.set_led_color(backend["path"], current_color, enabled, current_brightness)
        else:
            _current_enabled, current_color, current_brightness, current_mode, current_speed = self._current_hid_state(backend)
            success = self.write_hid_rgb(
                backend,
                current_color,
                enabled,
                current_brightness,
                current_mode,
                current_speed,
            )

        if not success:
            self.debug_failure("rgb", "set_enabled", "Failed to write RGB state", {"backend": backend["type"]})
            return False

        settings = self._settings()
        settings["rgb_enabled"] = enabled
        settings["rgb_color"] = current_color
        settings["rgb_brightness"] = current_brightness
        self.save_settings()
        self.debug_success(
            "rgb",
            "set_enabled",
            f"RGB {'enabled' if enabled else 'disabled'}",
            {"backend": backend["type"], "color": current_color, "brightness": current_brightness},
        )
        return True

    async def set_color(self, color: str) -> bool:
        self.debug_attempt("rgb", "set_color", "Changing RGB color", {"color": color})
        ok, _support = self._ensure_supported("set_color")
        if not ok:
            return False

        backend = self.get_rgb_backend()
        if not self._ensure_backend("set_color", backend):
            return False

        normalized = self.normalize_rgb_color(color)
        if normalized is None:
            self.logger.warning(f"Unsupported RGB color value: {color}")
            self.debug_failure("rgb", "set_color", "Unsupported RGB color value", {"color": color})
            return False

        if backend["type"] == "sysfs":
            enabled, _current_color, brightness = self.read_rgb_state_from_led(backend["path"])
            success = self.set_led_color(backend["path"], normalized, enabled, brightness)
        else:
            enabled, _current_color, brightness, mode, speed = self._current_hid_state(backend)
            success = self.write_hid_rgb(backend, normalized, enabled, brightness, mode, speed)

        if not success:
            self.debug_failure("rgb", "set_color", "Failed to apply RGB color", {"backend": backend["type"], "color": normalized})
            return False

        settings = self._settings()
        settings["rgb_color"] = normalized
        settings["rgb_brightness"] = brightness
        self.save_settings()
        self.debug_success(
            "rgb",
            "set_color",
            "RGB color applied",
            {"backend": backend["type"], "color": normalized, "brightness": brightness},
        )
        return True

    async def set_brightness(self, brightness: int) -> bool:
        self.debug_attempt("rgb", "set_brightness", "Changing RGB brightness", {"brightness": brightness})
        ok, _support = self._ensure_supported("set_brightness")
        if not ok:
            return False

        backend = self.get_rgb_backend()
        if not self._ensure_backend("set_brightness", backend):
            return False

        normalized_brightness = self.normalize_rgb_brightness(brightness)
        if backend["type"] == "sysfs":
            enabled, current_color, _current_brightness = self.read_rgb_state_from_led(backend["path"])
            success = True if not enabled else self.set_led_color(backend["path"], current_color, enabled, normalized_brightness)
        else:
            enabled, current_color, _current_brightness, mode, speed = self._current_hid_state(backend)
            success = True if not enabled else self.write_hid_rgb(
                backend,
                current_color,
                enabled,
                normalized_brightness,
                mode,
                speed,
            )

        if not success:
            self.debug_failure(
                "rgb",
                "set_brightness",
                "Failed to apply RGB brightness",
                {"backend": backend["type"], "brightness": normalized_brightness},
            )
            return False

        self._settings()["rgb_brightness"] = normalized_brightness
        self.save_settings()
        self.debug_success(
            "rgb",
            "set_brightness",
            "RGB brightness applied",
            {"backend": backend["type"], "brightness": normalized_brightness},
        )
        return True

    async def set_mode(self, mode: str) -> bool:
        self.debug_attempt("rgb", "set_mode", "Changing RGB mode", {"mode": mode})
        ok, _support = self._ensure_supported("set_mode")
        if not ok:
            return False

        backend = self.get_rgb_backend()
        supported_modes = self.get_rgb_supported_modes(backend)
        normalized_mode = str(mode or "").strip().lower()
        if normalized_mode not in supported_modes:
            self.logger.warning(f"Unsupported RGB mode: {mode}")
            self.debug_failure("rgb", "set_mode", "Unsupported RGB mode", {"mode": mode, "supported_modes": supported_modes})
            return False

        enabled, current_color, current_brightness, _current_mode, current_speed = self._current_hid_state(backend)
        success = True
        if backend["type"] in {"legion_hid", "asus_hid"} and enabled:
            success = self.write_hid_rgb(
                backend,
                current_color,
                enabled,
                current_brightness,
                normalized_mode,
                current_speed,
            )

        if not success:
            self.debug_failure("rgb", "set_mode", "Failed to apply RGB mode", {"backend": backend["type"], "mode": normalized_mode})
            return False

        self._settings()["rgb_mode"] = normalized_mode
        self.save_settings()
        self.debug_success("rgb", "set_mode", "RGB mode applied", {"backend": backend["type"], "mode": normalized_mode})
        return True

    async def set_speed(self, speed: str) -> bool:
        self.debug_attempt("rgb", "set_speed", "Changing RGB speed", {"speed": speed})
        ok, _support = self._ensure_supported("set_speed")
        if not ok:
            return False

        backend = self.get_rgb_backend()
        normalized_speed = self.normalize_rgb_speed(speed)
        current_mode = self.get_saved_rgb_mode(backend)
        mode_capabilities = self.get_rgb_mode_capabilities(backend)
        if not mode_capabilities.get(current_mode, {}).get("speed", False):
            self.logger.warning(f"RGB speed is not supported for mode: {current_mode}")
            self.debug_failure(
                "rgb",
                "set_speed",
                "RGB speed unsupported for current mode",
                {"mode": current_mode, "speed": normalized_speed},
            )
            return False

        enabled, current_color, current_brightness, _mode, _speed = self._current_hid_state(backend)
        success = True
        if backend["type"] in {"legion_hid", "asus_hid"} and enabled:
            success = self.write_hid_rgb(
                backend,
                current_color,
                enabled,
                current_brightness,
                current_mode,
                normalized_speed,
            )

        if not success:
            self.debug_failure(
                "rgb",
                "set_speed",
                "Failed to apply RGB speed",
                {"backend": backend["type"], "mode": current_mode, "speed": normalized_speed},
            )
            return False

        self._settings()["rgb_speed"] = normalized_speed
        self.save_settings()
        self.debug_success(
            "rgb",
            "set_speed",
            "RGB speed applied",
            {"backend": backend["type"], "mode": current_mode, "speed": normalized_speed},
        )
        return True
