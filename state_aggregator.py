"""Aggregate dashboard and information view state."""

import asyncio


class StateAggregator:
    def __init__(
        self,
        *,
        get_performance_modes,
        get_cpu_settings,
        get_rgb_state,
        get_display_sync_state,
        get_fps_limit_state,
        get_charge_limit_state,
        get_device_info,
        get_battery_info,
        get_performance_profiles,
        get_current_tdp,
        get_optimization_states,
        get_runtime_state,
        get_runtime_backend,
        get_debug_log_snapshot,
        debug_event,
    ):
        self.get_performance_modes = get_performance_modes
        self.get_cpu_settings = get_cpu_settings
        self.get_rgb_state = get_rgb_state
        self.get_display_sync_state = get_display_sync_state
        self.get_fps_limit_state = get_fps_limit_state
        self.get_charge_limit_state = get_charge_limit_state
        self.get_device_info = get_device_info
        self.get_battery_info = get_battery_info
        self.get_performance_profiles = get_performance_profiles
        self.get_current_tdp = get_current_tdp
        self.get_optimization_states = get_optimization_states
        self.get_runtime_state = get_runtime_state
        self.get_runtime_backend = get_runtime_backend
        self.get_debug_log_snapshot = get_debug_log_snapshot
        self.debug_event = debug_event

    def _cpu_boost_state(self, cpu: dict) -> dict:
        available = cpu.get("boost_available", False)
        return {
            "available": available,
            "enabled": cpu.get("boost_enabled", False),
            "status": "available" if available else "CPU boost control unavailable",
            "details": (
                "Boosts CPU clocks for heavier games"
                if available
                else cpu.get("status", "CPU boost control unavailable")
            ),
        }

    def _smt_state(self, cpu: dict) -> dict:
        available = cpu.get("smt_available", False)
        return {
            "available": available,
            "enabled": cpu.get("smt_enabled", False),
            "status": "available" if available else "SMT control unavailable",
            "details": (
                cpu.get("smt_details")
                if available
                else cpu.get("smt_status", "SMT control unavailable")
            ),
        }

    def _hardware_controls(
        self,
        *,
        platform_supported: bool,
        profiles: dict,
        cpu: dict,
        rgb: dict,
        sync: dict,
        fps_limit: dict,
        charge_limit: dict,
        optimizations: dict,
    ) -> dict:
        return {
            "performance_profiles": platform_supported and profiles.get("available", False),
            "cpu_boost": platform_supported and cpu.get("boost_available", False),
            "smt": platform_supported and cpu.get("smt_available", False),
            "charge_limit": platform_supported and charge_limit.get("available", False),
            "rgb": platform_supported and rgb.get("available", False),
            "vrr": platform_supported and sync.get("vrr", {}).get("available", False),
            "vsync": platform_supported and sync.get("vsync", {}).get("available", False),
            "fps_limit": platform_supported and fps_limit.get("available", False),
            "optimizations": platform_supported and any(
                state.get("available", False)
                for state in optimizations.get("states", [])
            ),
        }

    def _information_snapshot(
        self,
        *,
        profiles: dict,
        cpu: dict,
        sync: dict,
        fps_limit: dict,
        charge_limit: dict,
        rgb: dict,
        optimizations: dict,
    ) -> dict:
        return {
            "runtime_backend": self.get_runtime_backend(),
            "performance_status": profiles.get("status", ""),
            "performance_current": profiles.get("current", ""),
            "cpu_boost_available": cpu.get("boost_available", False),
            "cpu_boost_enabled": cpu.get("boost_enabled", False),
            "smt_available": cpu.get("smt_available", False),
            "smt_enabled": cpu.get("smt_enabled", False),
            "vrr_available": sync.get("vrr", {}).get("available", False),
            "vrr_enabled": sync.get("vrr", {}).get("enabled", False),
            "vsync_available": sync.get("vsync", {}).get("available", False),
            "vsync_enabled": sync.get("vsync", {}).get("enabled", False),
            "fps_available": fps_limit.get("available", False),
            "fps_current": fps_limit.get("current", 0),
            "charge_limit_available": charge_limit.get("available", False),
            "charge_limit_enabled": charge_limit.get("enabled", False),
            "rgb_available": rgb.get("available", False),
            "rgb_mode": rgb.get("mode", ""),
            "rgb_enabled": rgb.get("enabled", False),
            "optimizations_available": [
                state.get("key")
                for state in optimizations.get("states", [])
                if state.get("available", False)
            ],
        }

    async def get_dashboard_state(self) -> dict:
        performance_modes, cpu, rgb, sync, fps_limit, charge_limit = await asyncio.gather(
            self.get_performance_modes(),
            self.get_cpu_settings(),
            self.get_rgb_state(),
            self.get_display_sync_state(),
            self.get_fps_limit_state(),
            self.get_charge_limit_state(),
        )

        return {
            "performance_modes": performance_modes.get("modes", []),
            "active_mode": performance_modes.get("active_mode", ""),
            "profiles_available": performance_modes.get("available", False),
            "profiles_status": performance_modes.get("status", ""),
            "cpu_boost": self._cpu_boost_state(cpu),
            "smt": self._smt_state(cpu),
            "rgb": rgb,
            "vrr": sync.get("vrr", {}),
            "vsync": sync.get("vsync", {}),
            "fps_limit": fps_limit,
            "charge_limit": charge_limit,
        }

    async def get_information_state(self) -> dict:
        (
            device,
            battery,
            profiles,
            sync,
            temps,
            cpu,
            rgb,
            optimizations,
            fps_limit,
            charge_limit,
        ) = await asyncio.gather(
            self.get_device_info(),
            self.get_battery_info(),
            self.get_performance_profiles(),
            self.get_display_sync_state(),
            self.get_current_tdp(),
            self.get_cpu_settings(),
            self.get_rgb_state(),
            self.get_optimization_states(),
            self.get_fps_limit_state(),
            self.get_charge_limit_state(),
        )

        platform_supported = device.get("platform_supported", device.get("supported", False))
        hardware_controls = self._hardware_controls(
            platform_supported=platform_supported,
            profiles=profiles,
            cpu=cpu,
            rgb=rgb,
            sync=sync,
            fps_limit=fps_limit,
            charge_limit=charge_limit,
            optimizations=optimizations,
        )
        snapshot = self._information_snapshot(
            profiles=profiles,
            cpu=cpu,
            sync=sync,
            fps_limit=fps_limit,
            charge_limit=charge_limit,
            rgb=rgb,
            optimizations=optimizations,
        )
        self.debug_event("information", "refresh", "snapshot", "Information view refreshed", snapshot)

        return {
            "device": device,
            "battery": battery,
            "performance": {
                "current_profile": profiles.get("current", ""),
                "available_native": profiles.get("available_native", []),
                "status": profiles.get("status", ""),
            },
            "display": sync,
            "temperatures": {
                "tdp": temps.get("tdp", 0),
                "cpu": temps.get("cpu_temp", 0),
                "gpu": temps.get("gpu_temp", 0),
                "gpu_clock": temps.get("gpu_clock", 0),
            },
            "optimizations": optimizations.get("states", []),
            "hardware_controls": hardware_controls,
            "fps_limit": fps_limit,
            "runtime": self.get_runtime_state(),
            "debug_log": self.get_debug_log_snapshot(),
        }
