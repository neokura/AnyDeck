"""High-level orchestration for performance profile flows."""


class PerformanceService:
    def __init__(
        self,
        *,
        logger,
        native_profiles: dict,
        get_platform_support,
        get_steamos_manager,
        get_profiles_callback,
        debug_attempt,
        debug_success,
        debug_failure,
    ):
        self.logger = logger
        self.native_profiles = native_profiles
        self.get_platform_support = get_platform_support
        self.get_steamos_manager = get_steamos_manager
        self.get_profiles_callback = get_profiles_callback
        self.debug_attempt = debug_attempt
        self.debug_success = debug_success
        self.debug_failure = debug_failure

    async def get_profiles(self) -> dict:
        support = self.get_platform_support()
        if not support.get("supported", False):
            return {
                "profiles": {
                    profile_id: {**profile, "available": False}
                    for profile_id, profile in self.native_profiles.items()
                },
                "current": "",
                "suggested_default": "",
                "available": False,
                "available_native": [],
                "status": support.get("reason", "Platform is not supported"),
            }

        native_state = self.get_steamos_manager().get_performance_state()
        available_native = native_state.get("available_native", [])
        current = native_state.get("current") or ""
        profiles = {}

        for profile_id, profile in self.native_profiles.items():
            profiles[profile_id] = {
                **profile,
                "available": native_state.get("available", False) and profile_id in available_native,
            }

        return {
            "profiles": profiles,
            "current": current,
            "suggested_default": native_state.get("suggested_default", ""),
            "available": native_state.get("available", False),
            "available_native": available_native,
            "status": native_state.get("status", "SteamOS native profiles unavailable"),
        }

    async def get_modes(self) -> dict:
        profiles_data = await self.get_profiles_callback()
        active_native = profiles_data.get("current", "")
        active_mode = active_native if active_native in self.native_profiles else ""

        modes = []
        for profile_id, profile in self.native_profiles.items():
            native_profile = profiles_data["profiles"].get(profile_id, {})
            modes.append(
                {
                    "id": profile_id,
                    "label": profile["name"],
                    "native_id": profile_id,
                    "description": profile["description"],
                    "available": native_profile.get("available", False),
                    "active": active_mode == profile_id and native_profile.get("available", False),
                }
            )

        return {
            "modes": modes,
            "active_mode": active_mode,
            "native_active": active_native,
            "available": profiles_data.get("available", False),
            "status": profiles_data.get("status", "SteamOS native profiles unavailable"),
        }

    async def set_profile(self, profile_id: str) -> bool:
        try:
            self.debug_attempt("performance", "set_profile", "Changing performance profile", {"profile_id": profile_id})
            support = self.get_platform_support()
            if not support.get("supported", False):
                reason = support.get("reason", "Platform is not supported")
                self.logger.warning(reason)
                self.debug_failure("performance", "set_profile", reason, {"profile_id": profile_id})
                return False

            if profile_id not in self.native_profiles:
                self.logger.error(f"Unknown profile: {profile_id}")
                self.debug_failure("performance", "set_profile", "Unknown profile", {"profile_id": profile_id})
                return False

            native_state = self.get_steamos_manager().get_performance_state()
            if not native_state.get("available", False):
                status = native_state.get("status", "SteamOS native profiles unavailable")
                self.logger.warning(status)
                self.debug_failure("performance", "set_profile", status, {"profile_id": profile_id, "state": native_state})
                return False

            if profile_id not in native_state.get("available_native", []):
                self.logger.warning(f"SteamOS performance profile is not available: {profile_id}")
                self.debug_failure(
                    "performance",
                    "set_profile",
                    "Requested profile unavailable",
                    {"profile_id": profile_id, "available_native": native_state.get("available_native", [])},
                )
                return False

            success, error = self.get_steamos_manager().set_performance_profile(profile_id)
            if not success:
                self.logger.error(f"Failed to set SteamOS performance profile: {error}")
                self.debug_failure(
                    "performance",
                    "set_profile",
                    f"Failed to set SteamOS performance profile: {error}",
                    {"profile_id": profile_id},
                )
                return False

            profile_name = self.native_profiles[profile_id]["name"]
            self.logger.info(f"Applied SteamOS performance profile: {profile_name} ({profile_id})")
            self.debug_success(
                "performance",
                "set_profile",
                "Performance profile applied",
                {"profile_id": profile_id, "profile_name": profile_name},
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to set performance profile: {e}")
            self.debug_failure("performance", "set_profile", f"Failed to set performance profile: {e}", {"profile_id": profile_id})
            return False
