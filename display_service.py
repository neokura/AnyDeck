"""High-level orchestration for display sync and FPS flows."""

import shlex


class DisplayService:
    def __init__(
        self,
        *,
        logger,
        get_platform_support,
        get_gamescope_settings,
        command_info,
        command_exists,
        run_command,
        get_fps_presets,
        debug_attempt,
        debug_success,
        debug_failure,
    ):
        self.logger = logger
        self.get_platform_support = get_platform_support
        self.get_gamescope_settings = get_gamescope_settings
        self.command_info = command_info
        self.command_exists = command_exists
        self.run_command = run_command
        self.get_fps_presets = get_fps_presets
        self.debug_attempt = debug_attempt
        self.debug_success = debug_success
        self.debug_failure = debug_failure

    async def get_sync_state(self) -> dict:
        support = self.get_platform_support()
        if not support.get("supported", False):
            reason = support.get("reason", "Platform is not supported")
            return {
                "backend": "platform-guard",
                "display": "",
                "vrr": {
                    "available": False,
                    "capable": False,
                    "enabled": False,
                    "active": False,
                    "status": reason,
                    "details": reason,
                },
                "vsync": {
                    "available": False,
                    "enabled": False,
                    "allow_tearing": False,
                    "status": reason,
                    "details": reason,
                },
            }
        return self.get_gamescope_settings().get_display_sync_state()

    async def set_sync_setting(self, key: str, enabled: bool) -> bool:
        try:
            self.debug_attempt("display", "set_sync", "Changing display sync setting", {"key": key, "enabled": enabled})
            support = self.get_platform_support()
            if not support.get("supported", False):
                reason = support.get("reason", "Platform is not supported")
                self.logger.warning(reason)
                self.debug_failure("display", "set_sync", reason, {"key": key, "enabled": enabled})
                return False

            gamescope = self.get_gamescope_settings()
            if key == "vrr":
                success, error = gamescope.set_vrr_enabled(enabled)
            elif key == "vsync":
                success, error = gamescope.set_vsync_enabled(enabled)
            else:
                self.logger.error(f"Unknown display sync setting: {key}")
                self.debug_failure("display", "set_sync", "Unknown display sync setting", {"key": key, "enabled": enabled})
                return False

            if not success:
                self.logger.warning(f"Failed to set display sync setting {key}: {error}")
                self.debug_failure("display", "set_sync", f"Failed to set display sync setting: {error}", {"key": key, "enabled": enabled})
                return False

            self.logger.info(f"Set display sync setting {key} to {'enabled' if enabled else 'disabled'}")
            self.debug_success("display", "set_sync", "Display sync setting updated", {"key": key, "enabled": enabled})
            return True
        except Exception as e:
            self.logger.error(f"Failed to set display sync setting {key}: {e}")
            self.debug_failure("display", "set_sync", f"Failed to set display sync setting: {e}", {"key": key, "enabled": enabled})
            return False

    async def get_fps_limit_state(self) -> dict:
        support = self.get_platform_support()
        if not support.get("supported", False):
            return {
                "available": False,
                "current": 0,
                "requested": 0,
                "is_live": False,
                "presets": self.get_fps_presets(),
                "status": support.get("reason", "Platform is not supported"),
                "details": support.get("reason", "Platform is not supported"),
            }

        gamescope = self.get_gamescope_settings()
        gamescopectl_info = self.command_info("gamescopectl")
        available = gamescopectl_info.get("available", False)
        live_value = None
        gamescopectl_error = ""
        xprop_error = ""

        if available:
            for command in (
                ["gamescopectl", "debug_get_fps_limit"],
                ["gamescopectl", "get_fps_limit"],
            ):
                success, output = self.run_command(command)
                if not success:
                    gamescopectl_error = output
                    continue
                tokens = [token for token in shlex.split(output) if token.strip()]
                integers = []
                for token in tokens:
                    try:
                        integers.append(int(token, 0))
                    except ValueError:
                        continue
                if integers:
                    live_value = integers[-1]
                    break
            if live_value is None:
                ok, atom_value, xprop_error, _atom = gamescope.get_fps_limit_state()
                if ok:
                    live_value = atom_value

        if live_value is None:
            ok, atom_value, xprop_error, _atom = gamescope.get_fps_limit_state()
            if ok:
                live_value = atom_value
                available = True

        current = 0 if live_value is None else live_value
        available_for_ui = live_value is not None
        if live_value is not None:
            status = "available"
            details = "Uses live gamescope framerate control"
        elif available and gamescopectl_error:
            status = f"gamescopectl unavailable at runtime: {gamescopectl_error}"
            details = gamescopectl_error
        elif xprop_error:
            status = f"gamescope fps properties unavailable: {xprop_error}"
            details = xprop_error
        else:
            status = "gamescopectl or gamescope fps properties are unavailable"
            details = "Live framerate control is unavailable on this system"

        return {
            "available": available_for_ui,
            "current": current,
            "requested": current,
            "is_live": live_value is not None,
            "presets": self.get_fps_presets(),
            "status": status,
            "details": details,
        }

    async def set_fps_limit(self, value: int) -> bool:
        self.debug_attempt("display", "set_fps_limit", "Changing framerate limit", {"value": value})
        support = self.get_platform_support()
        if not support.get("supported", False):
            reason = support.get("reason", "Platform is not supported")
            self.logger.warning(reason)
            self.debug_failure("display", "set_fps_limit", reason, {"value": value})
            return False

        value = max(0, int(value))
        if not self.command_exists("gamescopectl"):
            self.logger.warning("gamescopectl is not installed")
            self.debug_failure("display", "set_fps_limit", "gamescopectl is not installed", {"value": value})
            return False

        if value not in self.get_fps_presets():
            self.logger.warning(f"Unsupported framerate preset: {value}")
            self.debug_failure("display", "set_fps_limit", "Unsupported framerate preset", {"value": value, "supported": self.get_fps_presets()})
            return False

        success = False
        error = "Failed to set framerate limit"
        for command in (
            ["gamescopectl", "debug_set_fps_limit", str(value)],
            ["gamescopectl", "set_fps_limit", str(value)],
        ):
            success, error = self.run_command(command, use_sudo=False)
            if success:
                break
        if not success:
            self.logger.error(f"Failed to set framerate limit: {error}")
            self.debug_failure("display", "set_fps_limit", f"Failed to set framerate limit: {error}", {"value": value})
            return False

        self.logger.info(
            "Applied gamescope framerate limit: unlimited"
            if value == 0
            else f"Applied gamescope framerate limit: {value}"
        )
        self.debug_success("display", "set_fps_limit", "Framerate limit updated", {"value": value})
        return True
