"""
Xbox Companion - Decky Loader Plugin Backend
SteamOS handheld control and SteamOS-native system management

Licensed under MIT
"""

import os
import json
import math
import datetime
import subprocess
import shlex
import glob
import shutil
import importlib

import decky
from state_aggregator import StateAggregator
from platform_support import (
    get_device_metadata,
    get_platform_support,
    get_steamos_version,
    is_steam_deck_device,
    is_supported_handheld_vendor_device,
    parse_version_tuple,
    steamos_version_is_supported,
)
from rgb_support import (
    LEGION_RGB_BRIGHTNESS_MAX,
    RGB_COLOR_PRESETS,
    RGB_DEFAULT_BRIGHTNESS,
    RGB_DEFAULT_MODE,
    RGB_DEFAULT_SPEED,
    RGB_SPEED_OPTIONS,
    asus_hid_rgb_commands,
    clamp_int,
    get_rgb_mode_capabilities,
    get_rgb_supported_modes,
    get_saved_rgb_mode,
    hex_to_rgb,
    legion_hid_rgb_commands,
    normalize_rgb_brightness,
    normalize_rgb_color,
    normalize_rgb_speed,
    rgb_hid_padded,
    scale_rgb_brightness_from_raw,
    scale_rgb_brightness_to_raw,
)
from optimization_support import (
    atomic_managed_entries,
    forget_kernel_param_state,
    managed_kernel_params_from_state,
    optimization_state,
    remember_kernel_param_state,
)
from optimization_ops import (
    migrate_atomic_manifest_if_needed,
    pop_optimization_state_value,
    read_optimization_state,
    refresh_atomic_manifest,
    remove_managed_file,
    update_grub_param,
    write_optimization_state,
)
from optimization_runtime import (
    amd_npu_present,
    grub_param_configured,
    is_amd_platform,
    kernel_param_active,
    read_acpi_wakeup_entries,
    read_acpi_wake_enabled_devices,
    read_cmdline,
    read_sysctl,
    read_thp_mode,
    service_active,
    service_enabled,
    service_exists,
    set_acpi_wake_devices,
    systemctl,
    thp_is_madvise,
    usb_wake_candidate_devices,
    usb_wake_control_available,
    write_sysctl,
    write_thp_mode,
)
from performance_service import PerformanceService
from display_service import DisplayService
from rgb_controller import RgbController
from system_info import (
    default_battery_info,
    default_device_info,
    estimate_battery_times,
    format_duration_hours,
    get_battery_path,
    populate_battery_info,
    populate_device_info,
)

# Hardware paths. Vendor-specific paths are optional and features stay hidden
# when the running handheld does not expose them.
BATTERY_PATH = "/sys/class/power_supply/BAT0"
BATTERY_PATH_GLOBS = [
    "/sys/class/power_supply/BAT*",
    "/sys/class/power_supply/CMB*",
]
DMI_PATH = "/sys/class/dmi/id"
ALLY_LED_PATH = "/sys/class/leds/ally:rgb:joystick_rings"
SMT_CONTROL_PATH = "/sys/devices/system/cpu/smt/control"

RGB_LED_PATH_GLOBS = [
    "/sys/class/leds/*:rgb:joystick_rings",
    "/sys/class/leds/*:rgb:*",
    "/sys/class/leds/*ally*rgb*",
    "/sys/class/leds/*legion*rgb*",
    "/sys/class/leds/*legion*go*",
    "/sys/class/leds/*joystick*ring*",
]

PLUGIN_NAME = "Xbox Companion"

STEAMOS_MANAGER_SERVICE = "com.steampowered.SteamOSManager1"
STEAMOS_MANAGER_OBJECT = "/com/steampowered/SteamOSManager1"
STEAMOS_PERFORMANCE_INTERFACE = "com.steampowered.SteamOSManager1.PerformanceProfile1"
STEAMOS_MANAGER_INTERFACE = "com.steampowered.SteamOSManager1.Manager2"
STEAMOS_CHARGE_LIMIT_INTERFACE = "com.steampowered.SteamOSManager1.BatteryChargeLimit1"
STEAMOS_CPU_BOOST_INTERFACE = "com.steampowered.SteamOSManager1.CpuBoost1"
STEAMOS_CHARGE_LIMIT_PERCENT = 80
STEAMOS_CHARGE_FULL_PERCENT = 100
STEAMOS_CHARGE_LIMIT_RESET = -1

GAMESCOPE_VRR_CAPABLE_ATOM = "GAMESCOPE_VRR_CAPABLE"
GAMESCOPE_VRR_ENABLED_ATOM = "GAMESCOPE_VRR_ENABLED"
GAMESCOPE_VRR_FEEDBACK_ATOM = "GAMESCOPE_VRR_FEEDBACK"
GAMESCOPE_ALLOW_TEARING_ATOM = "GAMESCOPE_ALLOW_TEARING"
GAMESCOPE_FPS_LIMIT_ATOMS = [
    "GAMESCOPE_FPS_LIMIT",
    "GAMESCOPE_FRAMERATE_LIMIT",
]

NATIVE_PERFORMANCE_PROFILES = {
    "low-power": {
        "name": "Low Power",
        "native_id": "low-power",
        "description": "SteamOS low-power profile for cooler battery-focused play"
    },
    "balanced": {
        "name": "Balanced",
        "native_id": "balanced",
        "description": "SteamOS balanced profile for everyday handheld play"
    },
    "performance": {
        "name": "Performance",
        "native_id": "performance",
        "description": "SteamOS performance profile for demanding games"
    }
}

FPS_NATIVE_PRESET_VALUES = [30, 40, 60]
FPS_HIGH_REFRESH_MIN = 90
FPS_OPTION_DISABLED = 0
LEGION_RGB_SPEED_DEFAULT = 63
DEFAULT_COMMAND_TIMEOUT = 5
DEBUG_LOG_LIMIT = 250
SYSTEM_COMMAND_ENV_DROP_KEYS = {
    "LD_LIBRARY_PATH",
    "LD_PRELOAD",
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONNOUSERSITE",
    "PYINSTALLER_RESET_ENVIRONMENT",
    "PYINSTALLER_STRICT_UNPACK_MODE",
    "_MEIPASS2",
    "_PYI_ARCHIVE_FILE",
    "_PYI_APPLICATION_HOME_DIR",
    "_PYI_LINUX_PROCESS_NAME",
    "_PYI_PARENT_PROCESS_LEVEL",
}

LEGION_GO_S_HID = {
    "name": "Legion Go S HID RGB",
    "vid": 0x1A86,
    "pids": [0xE310, 0xE311],
    "usage_page": 0xFFA0,
    "usage": 0x0001,
    "interface": 3,
    "protocol": "legion_go_s",
}
LEGION_GO_TABLET_HID = {
    "name": "Legion Go HID RGB",
    "vid": 0x17EF,
    "pids": [0x6182, 0x6183, 0x6184, 0x6185, 0x61EB, 0x61EC, 0x61ED, 0x61EE],
    "usage_page": 0xFFA0,
    "usage": 0x0001,
    "interface": None,
    "protocol": "legion_go_tablet",
}
ASUS_ALLY_HID = {
    "name": "ASUS Handheld HID RGB",
    "vid": 0x0B05,
    "pids": [],
    "usage_page": 0xFF31,
    "usage": 0x0080,
    "interface": None,
    "protocol": "asus_ally",
}

ATOMIC_UPDATE_DIR = "/etc/atomic-update.conf.d"

SCX_DEFAULT_PATH = "/etc/default/scx"
MEMORY_SYSCTL_PATH = "/etc/sysctl.d/99-xbox-companion-memory-tuning.conf"
THP_TMPFILES_PATH = "/etc/tmpfiles.d/xbox-companion-thp.conf"
NPU_BLACKLIST_PATH = "/etc/modprobe.d/blacklist-xbox-companion-npu.conf"
USB_WAKE_SERVICE_PATH = "/etc/systemd/system/xbox-companion-disable-usb-wake.service"
USB_WAKE_SCRIPT_PATH = "/etc/xbox-companion/apply-usb-wake.sh"
USB_WAKE_CONFIG_PATH = "/etc/xbox-companion/usb-wake-devices.conf"
ATOMIC_MANIFEST_PATH = f"{ATOMIC_UPDATE_DIR}/xbox-companion.conf"
OPTIMIZATION_STATE_PATH = "/var/lib/xbox-companion/optimization-state.json"
LEGACY_ATOMIC_PATHS = [
    f"{ATOMIC_UPDATE_DIR}/xbox-companion-scx.conf",
    f"{ATOMIC_UPDATE_DIR}/xbox-companion-memory.conf",
    f"{ATOMIC_UPDATE_DIR}/xbox-companion-power.conf",
    f"{ATOMIC_UPDATE_DIR}/xbox-companion-grub-healer.conf",
]
LEGACY_MANAGED_PATHS = [
    "/etc/xbox-companion-grub-healer.sh",
    "/etc/systemd/system/xbox-companion-grub-healer.service",
]
GRUB_DEFAULT_PATH = "/etc/default/grub"
CPU_BOOST_PATH = "/sys/devices/system/cpu/cpufreq/boost"
THP_ENABLED_PATH = "/sys/kernel/mm/transparent_hugepage/enabled"
ACPI_WAKEUP_PATH = "/proc/acpi/wakeup"

MEMORY_SYSCTL_VALUES = {
    "vm.swappiness": "10",
    "vm.min_free_kbytes": "524288",
    "vm.dirty_ratio": "5",
}

SCX_DEFAULT_CONTENT = '''SCX_SCHEDULER="scx_lavd"
SCX_FLAGS="--performance"
'''

MEMORY_SYSCTL_CONTENT = "".join(
    f"{key} = {value}\n" for key, value in MEMORY_SYSCTL_VALUES.items()
)

THP_TMPFILES_CONTENT = (
    "w /sys/kernel/mm/transparent_hugepage/enabled - - - - madvise\n"
)

NPU_BLACKLIST_CONTENT = "blacklist amdxdna\n"

GRUB_KERNEL_PARAM_OPTIONS = {
    "kernel_amd_pstate": {
        "param": "amd_pstate=active",
        "name": "AMD P-State",
        "description": "Forces the AMD P-State driver into active mode.",
        "details": "Kernel parameter: amd_pstate=active",
    },
    "kernel_abm_off": {
        "param": "amdgpu.abmlevel=0",
        "name": "Disable ABM",
        "description": "Disables AMD panel adaptive backlight modulation.",
        "details": "Kernel parameter: amdgpu.abmlevel=0",
    },
    "kernel_split_lock": {
        "param": "split_lock_mitigate=0",
        "name": "Split Lock Mitigation",
        "description": "Disables split lock mitigation for lower CPU overhead.",
        "details": "Kernel parameter: split_lock_mitigate=0",
    },
    "kernel_watchdog": {
        "param": "nmi_watchdog=0",
        "name": "NMI Watchdog",
        "description": "Disables the NMI watchdog to reduce background overhead.",
        "details": "Kernel parameter: nmi_watchdog=0",
    },
    "kernel_aspm": {
        "param": "pcie_aspm=force",
        "name": "PCIe ASPM",
        "description": "Forces PCIe active-state power management.",
        "details": "Kernel parameter: pcie_aspm=force",
    },
}


def sanitized_system_env(overrides: dict | None = None) -> dict:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in SYSTEM_COMMAND_ENV_DROP_KEYS
        and not key.startswith("PYI_")
        and key != "MEIPASS"
    }
    if overrides:
        env.update(overrides)
    return env


SYSTEM_PROTECTED_PREFIXES = (
    "/etc/",
    "/proc/",
    "/sys/",
    "/usr/lib/systemd/",
    "/var/lib/",
)

HOST_OS_RELEASE_PATHS = (
    "/run/host/etc/os-release",
    "/run/host/usr/lib/os-release",
    "/etc/os-release",
    "/usr/lib/os-release",
)
HOST_COMMAND_CANDIDATE_DIRS = (
    "/run/host/usr/bin",
    "/run/host/bin",
    "/usr/bin",
    "/bin",
)
HOST_BRIDGED_COMMANDS = {
    "busctl",
    "gamescopectl",
    "xprop",
    "xrandr",
    "systemctl",
    "update-grub",
    "sudo",
    "tee",
    "mkdir",
    "chmod",
    "rm",
    "sysctl",
    "lspci",
}


def needs_privilege_escalation(path: str | None = None) -> bool:
    if os.geteuid() == 0:
        return False
    if path is None:
        return True
    normalized = os.path.abspath(path)
    return normalized.startswith(SYSTEM_PROTECTED_PREFIXES)


class HostRuntime:
    def __init__(self):
        self.uid = os.getuid()
        self.runtime_dir = f"/run/user/{self.uid}"
        self.gamescope_env_path = os.path.join(self.runtime_dir, "gamescope-environment")
        self._host_env_cache: dict | None = None
        self._os_release_cache: tuple[str, dict] | None = None

    def _read_key_value_file(self, path: str) -> dict:
        values = {}
        try:
            with open(path, "r") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if "=" not in line or not line or line.startswith("#"):
                        continue
                    key, value = line.split("=", 1)
                    values[key] = value.strip().strip('"').strip("'")
        except Exception:
            return {}
        return values

    def get_os_release(self) -> tuple[str, dict]:
        if self._os_release_cache is not None:
            return self._os_release_cache
        for path in HOST_OS_RELEASE_PATHS:
            if not os.path.exists(path):
                continue
            values = self._read_key_value_file(path)
            if values:
                self._os_release_cache = (path, values)
                return self._os_release_cache
        self._os_release_cache = ("", {})
        return self._os_release_cache

    def _host_environment_file_values(self) -> dict:
        if not os.path.exists(self.gamescope_env_path):
            if not self.can_bridge_host():
                return {}
            try:
                result = subprocess.run(
                    ["flatpak-spawn", "--host", "cat", self.gamescope_env_path],
                    capture_output=True,
                    text=True,
                    timeout=DEFAULT_COMMAND_TIMEOUT,
                    env=sanitized_system_env(),
                )
            except Exception:
                return {}
            if result.returncode != 0:
                return {}

            values = {}
            for raw_line in result.stdout.splitlines():
                line = raw_line.strip()
                if "=" not in line or not line or line.startswith("#"):
                    continue
                key, value = line.split("=", 1)
                values[key] = value.strip().strip('"').strip("'")
            return values
        return self._read_key_value_file(self.gamescope_env_path)

    def host_env(self, overrides: dict | None = None) -> dict:
        if self._host_env_cache is None:
            base = sanitized_system_env()
            host_values = self._host_environment_file_values()
            base.update(host_values)
            base["PATH"] = host_values.get("PATH", base.get("PATH", "/usr/local/bin:/usr/bin:/bin"))
            base.setdefault("XDG_RUNTIME_DIR", self.runtime_dir)
            base.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={self.runtime_dir}/bus")
            self._host_env_cache = base
        env = dict(self._host_env_cache)
        if overrides:
            env.update(overrides)
        return env

    def steamos_bus_env(self) -> dict:
        return self.host_env(
            {
                "XDG_RUNTIME_DIR": self.runtime_dir,
                "DBUS_SESSION_BUS_ADDRESS": f"unix:path={self.runtime_dir}/bus",
            }
        )

    def display_env(self, display: str | None = None) -> dict:
        env = self.host_env()
        if display:
            env["DISPLAY"] = display
        return env

    def execution_backend(self) -> str:
        if self.can_bridge_host():
            return "flatpak-host"
        return "direct"

    def can_bridge_host(self) -> bool:
        return shutil.which("flatpak-spawn") is not None and any(
            os.path.exists(path) for path in HOST_OS_RELEASE_PATHS[:2]
        )

    def resolve_command(self, cmd: str) -> dict:
        direct = shutil.which(cmd)
        if direct:
            return {"available": True, "path": direct, "via_host": False}

        host_path = ""
        for base in HOST_COMMAND_CANDIDATE_DIRS:
            candidate = os.path.join(base, cmd)
            if os.path.exists(candidate) and os.access(candidate, os.X_OK):
                host_path = candidate
                break

        if host_path and cmd in HOST_BRIDGED_COMMANDS and self.can_bridge_host():
            return {"available": True, "path": host_path, "via_host": True}

        return {"available": False, "path": host_path, "via_host": False}

    def _prepare_command(self, command: list[str]) -> tuple[list[str], dict]:
        if not command:
            raise FileNotFoundError("empty command")
        info = self.resolve_command(command[0])
        if not info["available"]:
            # Let subprocess surface a real FileNotFoundError at execution time.
            # This keeps mocked subprocess.run tests working even when the local
            # development machine does not provide host-only commands like xprop.
            return command, info
        if info["via_host"]:
            return ["flatpak-spawn", "--host", *command], info
        return command, info

    def run(
        self,
        command: list[str],
        *,
        timeout: int = DEFAULT_COMMAND_TIMEOUT,
        env: dict | None = None,
        capture_output: bool = True,
        text: bool = True,
        input: str | None = None,
    ) -> subprocess.CompletedProcess:
        final_command, _info = self._prepare_command(command)
        return subprocess.run(
            final_command,
            capture_output=capture_output,
            text=text,
            timeout=timeout,
            env=env if env is not None else sanitized_system_env(),
            input=input,
        )

    def run_host_command(
        self,
        command: list[str],
        *,
        timeout: int = DEFAULT_COMMAND_TIMEOUT,
        env: dict | None = None,
        capture_output: bool = True,
        text: bool = True,
        input: str | None = None,
    ) -> subprocess.CompletedProcess:
        final_command = ["flatpak-spawn", "--host", *command] if self.can_bridge_host() else command
        return subprocess.run(
            final_command,
            capture_output=capture_output,
            text=text,
            timeout=timeout,
            env=env if env is not None else sanitized_system_env(),
            input=input,
        )

    def diagnostics(self) -> dict:
        os_release_path, os_release_values = self.get_os_release()
        host_env = self.host_env()
        gamescope_env_loaded = bool(
            host_env.get("GAMESCOPE_WAYLAND_DISPLAY")
            or host_env.get("DISPLAY")
            or host_env.get("XAUTHORITY")
        )
        commands = {}
        for cmd in ("busctl", "gamescopectl", "xprop", "systemctl", "update-grub"):
            info = self.resolve_command(cmd)
            commands[cmd] = {
                "available": info["available"],
                "path": info["path"] or "",
                "via_host": info["via_host"],
            }

        return {
            "execution_backend": self.execution_backend(),
            "os_release_path": os_release_path,
            "host_os_id": os_release_values.get("ID", ""),
            "commands": commands,
            "display_env": {
                "display": host_env.get("DISPLAY", ""),
                "xauthority": host_env.get("XAUTHORITY", ""),
                "gamescope_env_path": self.gamescope_env_path if gamescope_env_loaded else "",
                "gamescope_wayland_display": host_env.get("GAMESCOPE_WAYLAND_DISPLAY", ""),
            },
        }

class SteamOsManagerClient:
    """Small DBus client for SteamOS Manager via busctl."""

    def __init__(self, logger, runtime: HostRuntime | None = None):
        self.logger = logger
        self.runtime = runtime or HostRuntime()
        self.user_bus_env = self._build_user_bus_env()
        self._interface_bus_cache: dict[str, str] = {}

    def _build_user_bus_env(self) -> dict:
        return self.runtime.steamos_bus_env()

    def _run_busctl(self, bus: str, args: list[str]) -> subprocess.CompletedProcess:
        env = self.user_bus_env if bus == "user" else self.runtime.host_env()
        return self.runtime.run(
            ["busctl", f"--{bus}", *args],
            timeout=5,
            env=env,
        )

    def get_active_bus(self) -> str:
        if not self._interface_bus_cache:
            return "none"
        return next(iter(self._interface_bus_cache.values()), "none") or "none"

    def _candidate_buses(self) -> list[str]:
        return ["user", "system"]

    def _introspect_interfaces(self, bus: str) -> dict[str, set[str]]:
        try:
            result = self._run_busctl(bus, [
                "introspect",
                STEAMOS_MANAGER_SERVICE,
                STEAMOS_MANAGER_OBJECT,
            ])
        except Exception:
            return {}

        if result.returncode != 0:
            return {}

        interfaces: dict[str, set[str]] = {}
        current_interface = ""
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            if parts[1] == "interface":
                current_interface = parts[0]
                interfaces.setdefault(current_interface, set())
                continue
            if parts[1] == "property" and current_interface:
                interfaces.setdefault(current_interface, set()).add(parts[0])
        return interfaces

    def _find_interface_bus(self, interface: str) -> str:
        cached = self._interface_bus_cache.get(interface, "")
        if cached:
            return cached
        for bus in self._candidate_buses():
            if interface in self._introspect_interfaces(bus):
                self._interface_bus_cache[interface] = bus
                return bus
        return ""

    def _get_available_properties(self, interface: str) -> set[str]:
        bus = self._find_interface_bus(interface)
        if not bus:
            return set()
        return self._introspect_interfaces(bus).get(interface, set())

    def _has_property(self, interface: str, prop: str) -> bool:
        return prop in self._get_available_properties(interface)

    def _get_property(
        self,
        prop: str,
        interface: str = STEAMOS_PERFORMANCE_INTERFACE,
    ) -> tuple[bool, str, str]:
        buses = []
        preferred_bus = self._find_interface_bus(interface)
        if preferred_bus:
            buses.append(preferred_bus)
        buses.extend(bus for bus in self._candidate_buses() if bus not in buses)

        last_error = "DBus property read failed"
        for bus in buses:
            try:
                result = self._run_busctl(bus, [
                    "get-property",
                    STEAMOS_MANAGER_SERVICE,
                    STEAMOS_MANAGER_OBJECT,
                    interface,
                    prop
                ])
            except FileNotFoundError:
                return False, "", "busctl is not installed"
            except subprocess.TimeoutExpired:
                last_error = "SteamOS Manager DBus request timed out"
                continue
            except Exception as e:
                last_error = str(e)
                continue

            if result.returncode == 0:
                self._interface_bus_cache[interface] = bus
                return True, result.stdout.strip(), ""

            last_error = result.stderr.strip() or result.stdout.strip() or "DBus property read failed"

        return False, "", last_error

    def _set_property(self, interface: str, prop: str, signature: str, value: str) -> tuple[bool, str]:
        buses = []
        preferred_bus = self._find_interface_bus(interface)
        if preferred_bus:
            buses.append(preferred_bus)
        buses.extend(bus for bus in self._candidate_buses() if bus not in buses)

        last_error = "DBus property write failed"
        for bus in buses:
            try:
                result = self._run_busctl(bus, [
                    "set-property",
                    STEAMOS_MANAGER_SERVICE,
                    STEAMOS_MANAGER_OBJECT,
                    interface,
                    prop,
                    signature,
                    value,
                ])
            except FileNotFoundError:
                return False, "busctl is not installed"
            except subprocess.TimeoutExpired:
                last_error = "SteamOS Manager DBus request timed out"
                continue
            except Exception as e:
                last_error = str(e)
                continue

            if result.returncode == 0:
                self._interface_bus_cache[interface] = bus
                return True, ""

            last_error = result.stderr.strip() or result.stdout.strip() or "DBus property write failed"

        return False, last_error

    def _parse_busctl_bool(self, output: str) -> bool:
        tokens = shlex.split(output)
        return len(tokens) >= 2 and tokens[0] == "b" and tokens[1].lower() in ("true", "1")

    def _parse_busctl_int(self, output: str) -> int:
        tokens = shlex.split(output)
        if len(tokens) >= 2:
            try:
                return int(tokens[1], 0)
            except ValueError:
                return 0
        return 0

    def _busctl_signature(self, output: str) -> str:
        tokens = shlex.split(output)
        return tokens[0] if tokens else ""

    def _parse_busctl_string(self, output: str) -> str:
        tokens = shlex.split(output)
        if len(tokens) >= 2 and tokens[0] == "s":
            return tokens[1]
        return ""

    def _parse_busctl_string_array(self, output: str) -> list[str]:
        tokens = shlex.split(output)
        if not tokens or tokens[0] != "as":
            return []

        if len(tokens) >= 2 and tokens[1].isdigit():
            return tokens[2:]

        return tokens[1:]

    def get_performance_state(self) -> dict:
        properties = self._get_available_properties(STEAMOS_PERFORMANCE_INTERFACE)
        if "AvailablePerformanceProfiles" not in properties:
            return {
                "available": False,
                "available_native": [],
                "current": "",
                "suggested_default": "",
                "status": (
                    "SteamOS native profiles unavailable: "
                    "PerformanceProfile1 is not exposed on the SteamOS Manager user bus"
                ),
            }

        available_ok, available_output, available_error = self._get_property(
            "AvailablePerformanceProfiles",
            STEAMOS_PERFORMANCE_INTERFACE,
        )
        if not available_ok:
            return {
                "available": False,
                "available_native": [],
                "current": "",
                "suggested_default": "",
                "status": f"SteamOS native profiles unavailable: {available_error}",
            }
        available_native = self._parse_busctl_string_array(available_output)
        current_ok, current_output, current_error = self._get_property(
            "PerformanceProfile",
            STEAMOS_PERFORMANCE_INTERFACE,
        )
        current = self._parse_busctl_string(current_output) if current_ok else ""
        suggested_ok, suggested_output, _ = self._get_property(
            "SuggestedDefaultPerformanceProfile",
            STEAMOS_PERFORMANCE_INTERFACE,
        )
        suggested_default = (
            self._parse_busctl_string(suggested_output)
            if suggested_ok
            else ""
        )

        if not current_ok:
            self.logger.warning(f"Could not read SteamOS performance profile: {current_error}")

        return {
            "available": True,
            "available_native": available_native,
            "current": current,
            "suggested_default": suggested_default,
            "status": "available"
        }

    def set_performance_profile(self, profile_id: str) -> tuple[bool, str]:
        try:
            if not self._has_property(STEAMOS_PERFORMANCE_INTERFACE, "PerformanceProfile"):
                return False, "SteamOS Manager PerformanceProfile1 interface is unavailable on the user bus"
            return self._set_property(
                STEAMOS_PERFORMANCE_INTERFACE,
                "PerformanceProfile",
                "s",
                profile_id,
            )
        except Exception as e:
            return False, str(e)

    def get_charge_limit_state(self) -> dict:
        if not self._has_property(STEAMOS_CHARGE_LIMIT_INTERFACE, "MaxChargeLevel"):
            return {
                "available": False,
                "enabled": False,
                "limit": STEAMOS_CHARGE_FULL_PERCENT,
                "status": "SteamOS Manager charge limit API unavailable on the user bus",
                "details": "SteamOS Manager BatteryChargeLimit1 interface is unavailable",
            }

        ok, output, error = self._get_property("MaxChargeLevel", STEAMOS_CHARGE_LIMIT_INTERFACE)
        if not ok:
            return {
                "available": False,
                "enabled": False,
                "limit": STEAMOS_CHARGE_FULL_PERCENT,
                "status": error,
                "details": "Failed to read SteamOS Manager battery charge limit",
            }

        raw_limit = self._parse_busctl_int(output)
        suggested_minimum = STEAMOS_CHARGE_LIMIT_PERCENT
        if self._has_property(STEAMOS_CHARGE_LIMIT_INTERFACE, "SuggestedMinimumLimit"):
            suggested_ok, suggested_output, _ = self._get_property(
                "SuggestedMinimumLimit",
                STEAMOS_CHARGE_LIMIT_INTERFACE,
            )
            if suggested_ok:
                suggested_minimum = self._parse_busctl_int(suggested_output)
        enabled = raw_limit >= 0
        limit = raw_limit if enabled else STEAMOS_CHARGE_FULL_PERCENT

        return {
            "available": True,
            "enabled": enabled,
            "limit": limit or STEAMOS_CHARGE_FULL_PERCENT,
            "raw_limit": raw_limit,
            "suggested_minimum": suggested_minimum,
            "status": "available",
            "details": "Controls battery charge limit through SteamOS Manager BatteryChargeLimit1",
        }

    def set_charge_limit_enabled(self, enabled: bool) -> tuple[bool, str]:
        if not self._has_property(STEAMOS_CHARGE_LIMIT_INTERFACE, "MaxChargeLevel"):
            return False, "SteamOS Manager BatteryChargeLimit1 interface is unavailable on the user bus"

        value = STEAMOS_CHARGE_LIMIT_PERCENT if enabled else STEAMOS_CHARGE_LIMIT_RESET
        return self._set_property(STEAMOS_CHARGE_LIMIT_INTERFACE, "MaxChargeLevel", "i", str(value))

    def get_cpu_boost_state(self) -> dict:
        if not self._has_property(STEAMOS_CPU_BOOST_INTERFACE, "CpuBoostState"):
            return {
                "available": False,
                "enabled": False,
                "status": "SteamOS Manager CPU boost API unavailable on the user bus",
                "details": "SteamOS Manager CpuBoost1 interface is unavailable",
            }

        ok, output, error = self._get_property("CpuBoostState", STEAMOS_CPU_BOOST_INTERFACE)
        if not ok:
            return {
                "available": False,
                "enabled": False,
                "status": error,
                "details": "Failed to read SteamOS Manager CPU boost state",
            }

        enabled = self._parse_busctl_int(output) > 0
        return {
            "available": True,
            "enabled": enabled,
            "status": "available",
            "details": "Controls CPU boost through SteamOS Manager CpuBoost1",
        }

    def set_cpu_boost_enabled(self, enabled: bool) -> tuple[bool, str]:
        if not self._has_property(STEAMOS_CPU_BOOST_INTERFACE, "CpuBoostState"):
            return False, "SteamOS Manager CpuBoost1 interface is unavailable on the user bus"
        return self._set_property(
            STEAMOS_CPU_BOOST_INTERFACE,
            "CpuBoostState",
            "u",
            "1" if enabled else "0",
        )

    def get_smt_state(self) -> dict:
        return {
            "available": False,
            "enabled": False,
            "status": "SteamOS Manager SMT control unavailable",
            "details": "SteamOS 3.8 SteamOS Manager does not expose an SMT interface",
        }

    def set_smt_enabled(self, enabled: bool) -> tuple[bool, str]:
        return False, "SteamOS 3.8 SteamOS Manager does not expose SMT control"


class GamescopeSettingsClient:
    """Small X11 root-property client for SteamOS gamescope settings."""

    def __init__(self, logger, runtime: HostRuntime | None = None, display: str | None = None):
        self.logger = logger
        self.runtime = runtime or HostRuntime()
        self.display = display or self.runtime.host_env().get("DISPLAY") or os.environ.get("DISPLAY") or ":0"
        self.display_candidates = self._build_display_candidates(display)

    def _build_display_candidates(self, preferred: str | None) -> list[str]:
        candidates = []
        for candidate in (
            preferred,
            self.runtime.host_env().get("DISPLAY"),
            os.environ.get("DISPLAY"),
            ":0",
            ":1",
        ):
            if candidate and candidate not in candidates:
                candidates.append(candidate)
        return candidates or [":0"]

    def _xprop_env(self, display: str) -> dict:
        return self.runtime.display_env(display)

    def _run_xprop(self, args: list[str], display: str) -> subprocess.CompletedProcess:
        return self.runtime.run(
            ["xprop", "-root", *args],
            timeout=5,
            env=self._xprop_env(display),
        )

    def _should_try_next_display(self, error: str) -> bool:
        lowered = error.lower()
        return any(
            fragment in lowered
            for fragment in (
                "unable to open display",
                "can't open display",
                "cannot open display",
                "no such atom",
                "not available",
            )
        )

    def _read_cardinal(self, atom: str) -> tuple[bool, int, str]:
        last_error = ""

        for display in self.display_candidates:
            try:
                result = self._run_xprop([atom], display)
            except FileNotFoundError:
                return False, 0, "xprop is not installed"
            except subprocess.TimeoutExpired:
                return False, 0, "gamescope X property request timed out"
            except Exception as e:
                return False, 0, str(e)

            if result.returncode != 0:
                error = result.stderr.strip() or result.stdout.strip() or "xprop read failed"
                last_error = error
                if self._should_try_next_display(error):
                    continue
                return False, 0, error

            for line in result.stdout.splitlines():
                if not line.startswith(f"{atom}(") or "=" not in line:
                    continue

                raw_value = line.split("=", 1)[1].strip().split(",", 1)[0].strip()
                try:
                    self.display = display
                    return True, int(raw_value, 0), ""
                except ValueError:
                    return False, 0, f"Invalid gamescope property value: {raw_value}"

            last_error = f"{atom} is not available"

        return False, 0, last_error or f"{atom} is not available"

    def _read_first_available_cardinal(self, atoms: list[str]) -> tuple[bool, int, str, str]:
        last_error = ""
        for atom in atoms:
            ok, value, error = self._read_cardinal(atom)
            if ok:
                return True, value, "", atom
            if error:
                last_error = error
        return False, 0, last_error or "gamescope property is not available", ""

    def _set_cardinal(self, atom: str, enabled: bool) -> tuple[bool, str]:
        last_error = ""

        for display in self.display_candidates:
            try:
                result = self._run_xprop([
                    "-f",
                    atom,
                    "32c",
                    "-set",
                    atom,
                    "1" if enabled else "0",
                ], display)
            except FileNotFoundError:
                return False, "xprop is not installed"
            except subprocess.TimeoutExpired:
                return False, "gamescope X property request timed out"
            except Exception as e:
                return False, str(e)

            if result.returncode != 0:
                error = result.stderr.strip() or result.stdout.strip() or "xprop write failed"
                last_error = error
                if self._should_try_next_display(error):
                    continue
                return False, error

            self.display = display
            return True, ""

        return False, last_error or "xprop write failed"

    def _read_integer_atom(self, atoms: list[str]) -> tuple[bool, int, str, str]:
        return self._read_first_available_cardinal(atoms)

    def get_fps_limit_state(self) -> tuple[bool, int, str, str]:
        return self._read_integer_atom(GAMESCOPE_FPS_LIMIT_ATOMS)

    def get_display_sync_state(self) -> dict:
        vrr_capable_ok, vrr_capable_value, vrr_capable_error = self._read_cardinal(
            GAMESCOPE_VRR_CAPABLE_ATOM
        )
        vrr_enabled_ok, vrr_enabled_value, vrr_enabled_error = self._read_cardinal(
            GAMESCOPE_VRR_ENABLED_ATOM
        )
        vrr_feedback_ok, vrr_feedback_value, _ = self._read_cardinal(
            GAMESCOPE_VRR_FEEDBACK_ATOM
        )
        tearing_ok, tearing_value, tearing_error = self._read_cardinal(
            GAMESCOPE_ALLOW_TEARING_ATOM
        )

        vrr_capable = (
            (vrr_capable_ok and bool(vrr_capable_value))
            or vrr_enabled_ok
            or vrr_feedback_ok
        )
        vrr_enabled = vrr_enabled_ok and bool(vrr_enabled_value)
        vrr_active = vrr_feedback_ok and bool(vrr_feedback_value)

        if not vrr_capable_ok and not (vrr_enabled_ok or vrr_feedback_ok):
            vrr_status = f"VRR state unavailable: {vrr_capable_error}"
        elif vrr_capable_ok and not bool(vrr_capable_value):
            vrr_status = "Display is not VRR capable"
        else:
            vrr_status = "available"

        if not tearing_ok:
            vsync_status = f"VSync state unavailable: {tearing_error}"
        else:
            vsync_status = "available"

        return {
            "backend": "gamescope-xprop",
            "display": self.display,
            "vrr": {
                "available": vrr_capable,
                "capable": vrr_capable,
                "enabled": vrr_enabled,
                "active": vrr_active,
                "status": vrr_status,
                "details": "Gamescope VRR on current display",
            },
            "vsync": {
                "available": tearing_ok,
                "enabled": not bool(tearing_value) if tearing_ok else False,
                "allow_tearing": bool(tearing_value) if tearing_ok else False,
                "status": vsync_status,
                "details": "Maps to SteamOS Allow Tearing",
            },
        }

    def set_vrr_enabled(self, enabled: bool) -> tuple[bool, str]:
        capable_ok, capable_value, capable_error = self._read_cardinal(
            GAMESCOPE_VRR_CAPABLE_ATOM
        )
        if not capable_ok:
            return False, capable_error
        if not capable_value:
            return False, "Display is not VRR capable"

        return self._set_cardinal(GAMESCOPE_VRR_ENABLED_ATOM, enabled)

    def set_vsync_enabled(self, enabled: bool) -> tuple[bool, str]:
        # SteamOS exposes this as "Allow Tearing"; VSync is the inverse.
        return self._set_cardinal(GAMESCOPE_ALLOW_TEARING_ATOM, not enabled)


class Plugin:
    def __init__(self):
        self.settings_path: str | None = None
        self.settings: dict = {}
        self.runtime = HostRuntime()
        self.steamos_manager: SteamOsManagerClient | None = None
        self.gamescope_settings: GamescopeSettingsClient | None = None
        self.debug_log: list[dict] = []
        self._sudo_available_cache: bool | None = None

    def _debug_event(self, area: str, action: str, status: str, message: str, details=None):
        entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "area": area,
            "action": action,
            "status": status,
            "message": message,
            "details": details if details is not None else {},
        }
        self.debug_log.append(entry)
        if len(self.debug_log) > DEBUG_LOG_LIMIT:
            self.debug_log = self.debug_log[-DEBUG_LOG_LIMIT:]
        return entry

    def _debug_success(self, area: str, action: str, message: str, details=None):
        self._debug_event(area, action, "success", message, details)

    def _debug_failure(self, area: str, action: str, message: str, details=None):
        self._debug_event(area, action, "error", message, details)

    def _debug_attempt(self, area: str, action: str, message: str, details=None):
        self._debug_event(area, action, "attempt", message, details)

    async def get_debug_log(self) -> list[dict]:
        return list(self.debug_log)

    async def clear_debug_log(self) -> bool:
        self.debug_log = []
        self._debug_success("debug", "clear", "Debug log cleared")
        return True

    async def _main(self):
        """Main entry point for the plugin"""
        self.settings_path = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json")
        self.steamos_manager = SteamOsManagerClient(decky.logger, self.runtime)
        self.gamescope_settings = GamescopeSettingsClient(decky.logger, self.runtime)
        await self.load_settings()
        decky.logger.info(f"{PLUGIN_NAME} initialized")
        self._debug_success("plugin", "init", f"{PLUGIN_NAME} initialized")

    async def _unload(self):
        """Cleanup when plugin is unloaded"""
        decky.logger.info(f"{PLUGIN_NAME} unloaded")

    async def _migration(self):
        """Handle plugin migrations"""
        pass

    async def load_settings(self):
        try:
            if os.path.exists(self.settings_path):
                with open(self.settings_path, 'r') as f:
                    self.settings = json.load(f)
            else:
                self.settings = {}
        except Exception as e:
            decky.logger.error(f"Failed to load settings: {e}")
            self.settings = {}

        return self.settings

    def _save_settings(self):
        try:
            if not self.settings_path:
                return
            os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
            with open(self.settings_path, "w") as f:
                json.dump(self.settings, f, indent=2, sort_keys=True)
                f.write("\n")
        except Exception as e:
            decky.logger.error(f"Failed to save settings: {e}")

    def _read_file(self, path: str, default: str = "Unknown") -> str:
        try:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    return f.read().strip() or default
        except Exception:
            pass
        return default

    def _find_first_existing_path(
        self,
        direct_paths: list[str],
        glob_patterns: list[str],
    ) -> str:
        for path in direct_paths:
            if path and os.path.exists(path):
                return path

        for pattern in glob_patterns:
            for path in sorted(glob.glob(pattern)):
                if path and os.path.exists(path):
                    return path

        return ""

    def _get_rgb_led_path(self) -> str:
        candidates = []
        if os.path.exists(ALLY_LED_PATH):
            candidates.append(ALLY_LED_PATH)

        for pattern in RGB_LED_PATH_GLOBS:
            candidates.extend(sorted(glob.glob(pattern)))

        seen = set()
        for path in candidates:
            if path in seen:
                continue
            seen.add(path)
            if self._rgb_led_usable(path):
                return path

        return ""

    def _hid_module(self):
        for module_name in ("lib_hid", "hid"):
            try:
                return importlib.import_module(module_name)
            except Exception:
                continue
        return None

    def _hid_module_devices(self) -> list[dict]:
        module = self._hid_module()
        if module is None or not hasattr(module, "enumerate"):
            return []
        try:
            return list(module.enumerate())
        except Exception:
            return []

    def _hidraw_devices(self) -> list[dict]:
        devices = []
        for hidraw_path in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
            uevent_path = os.path.join(hidraw_path, "device", "uevent")
            dev_name = os.path.basename(hidraw_path)
            dev_path = f"/dev/{dev_name}"
            try:
                values = {}
                with open(uevent_path, "r") as f:
                    for line in f:
                        if "=" in line:
                            key, value = line.strip().split("=", 1)
                            values[key] = value
                hid_id = values.get("HID_ID", "")
                parts = hid_id.split(":")
                if len(parts) < 3:
                    continue
                devices.append({
                    "path": dev_path,
                    "vendor_id": int(parts[-2], 16),
                    "product_id": int(parts[-1], 16),
                    "usage_page": None,
                    "usage": None,
                    "interface_number": None,
                    "backend": "hidraw",
                })
            except Exception:
                continue
        return devices

    def _normalize_hid_device(self, device: dict) -> dict:
        return {
            "path": device.get("path"),
            "vendor_id": device.get("vendor_id"),
            "product_id": device.get("product_id"),
            "usage_page": device.get("usage_page"),
            "usage": device.get("usage"),
            "interface_number": device.get("interface_number"),
            "backend": device.get("backend", "hid"),
        }

    def _legion_hid_candidates(self) -> list[dict]:
        return [self._normalize_hid_device(device) for device in self._hid_module_devices()] + self._hidraw_devices()

    def _hid_device_matches_config(self, device: dict, config: dict) -> bool:
        if device.get("vendor_id") != config["vid"]:
            return False
        product_ids = config.get("pids") or []
        if product_ids and device.get("product_id") not in product_ids:
            return False
        if config.get("interface") is not None and device.get("interface_number") is not None:
            if device.get("interface_number") != config["interface"]:
                return False
        if device.get("usage_page") is not None and device.get("usage") is not None:
            return device.get("usage_page") == config["usage_page"] and device.get("usage") == config["usage"]
        return True

    def _get_legion_hid_rgb_device(self) -> dict | None:
        configs = [LEGION_GO_S_HID, LEGION_GO_TABLET_HID]
        for config in configs:
            for device in self._legion_hid_candidates():
                if self._hid_device_matches_config(device, config):
                    return {**device, "config": config}
        return None

    def _get_asus_hid_rgb_device(self) -> dict | None:
        for device in self._legion_hid_candidates():
            if self._hid_device_matches_config(device, ASUS_ALLY_HID):
                return {**device, "config": ASUS_ALLY_HID}
        return None

    def _get_rgb_backend(self) -> dict:
        asus_device = self._get_asus_hid_rgb_device()
        if asus_device:
            return {
                "type": "asus_hid",
                "device": asus_device,
                "details": asus_device["config"]["name"],
            }

        led_path = self._get_rgb_led_path()
        if led_path:
            return {"type": "sysfs", "path": led_path, "details": "sysfs multicolor LED"}

        device = self._get_legion_hid_rgb_device()
        if device:
            return {
                "type": "legion_hid",
                "device": device,
                "details": device["config"]["name"],
            }

        return {"type": "none", "details": "RGB control unavailable"}

    def _rgb_led_usable(self, led_path: str) -> bool:
        return (
            bool(led_path)
            and os.path.exists(os.path.join(led_path, "brightness"))
            and os.path.exists(os.path.join(led_path, "multi_intensity"))
        )

    def _clamp_int(self, value, minimum: int, maximum: int) -> int:
        return clamp_int(value, minimum, maximum)

    def _normalize_rgb_brightness(self, brightness) -> int:
        return normalize_rgb_brightness(brightness)

    def _normalize_rgb_color(self, color: str) -> str | None:
        return normalize_rgb_color(color)

    def _get_saved_rgb_brightness(self) -> int:
        return self._normalize_rgb_brightness(
            self.settings.get("rgb_brightness", RGB_DEFAULT_BRIGHTNESS)
        )

    def _normalize_rgb_speed(self, speed: str | None) -> str:
        return normalize_rgb_speed(speed)

    def _get_rgb_supported_modes(self, backend: dict) -> list[str]:
        return get_rgb_supported_modes(backend)

    def _get_rgb_mode_capabilities(self, backend: dict) -> dict[str, dict]:
        return get_rgb_mode_capabilities(backend)

    def _get_saved_rgb_mode(self, backend: dict) -> str:
        return get_saved_rgb_mode(self.settings, backend)

    def _scale_rgb_brightness_to_raw(self, brightness: int, maximum: int) -> int:
        return scale_rgb_brightness_to_raw(brightness, maximum)

    def _scale_rgb_brightness_from_raw(self, raw_value: int, maximum: int) -> int:
        return scale_rgb_brightness_from_raw(raw_value, maximum)

    def _get_led_max_brightness(self, led_path: str) -> int:
        max_brightness_path = os.path.join(led_path, "max_brightness")
        try:
            if os.path.exists(max_brightness_path):
                with open(max_brightness_path, "r") as f:
                    return max(1, int(f.read().strip() or "255"))
        except Exception:
            pass
        return 255

    def _get_battery_path(self) -> str:
        return get_battery_path(self._read_file, BATTERY_PATH, list(BATTERY_PATH_GLOBS))

    def _format_duration_hours(self, hours: float) -> str:
        return format_duration_hours(hours)

    def _estimate_battery_times(self, battery: dict) -> tuple[str, str]:
        return estimate_battery_times(battery, STEAMOS_CHARGE_FULL_PERCENT)

    def _read_text_file_if_exists(self, path: str) -> str:
        try:
            if os.path.exists(path):
                with open(path, "r") as f:
                    return f.read().strip()
        except Exception:
            pass
        return ""

    def _read_cpu_model(self) -> str:
        try:
            if os.path.exists("/proc/cpuinfo"):
                with open("/proc/cpuinfo", "r") as f:
                    for line in f:
                        if line.startswith("model name"):
                            return line.split(":", 1)[1].strip()
        except Exception:
            pass
        return ""

    def _read_kernel_version(self) -> str:
        try:
            result = subprocess.run(
                ["uname", "-r"],
                capture_output=True,
                text=True,
                timeout=DEFAULT_COMMAND_TIMEOUT,
                env=sanitized_system_env(),
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return ""

    def _read_memory_total_gb(self) -> str:
        try:
            if os.path.exists("/proc/meminfo"):
                with open("/proc/meminfo", "r") as f:
                    for line in f:
                        if line.startswith("MemTotal"):
                            mem_kb = int(line.split()[1])
                            return f"{mem_kb // 1024 // 1024} GB"
        except Exception:
            pass
        return ""

    def _get_os_release_values(self) -> dict:
        try:
            _path, values = self.runtime.get_os_release()
            return values
        except Exception as e:
            decky.logger.error(f"Failed to read OS release data: {e}")
            return {}

    def _get_os_release_path(self) -> str:
        try:
            path, _values = self.runtime.get_os_release()
            return path
        except Exception:
            return ""

    def _get_steamos_version(self, os_release_values: dict | None = None) -> str:
        values = os_release_values if os_release_values is not None else self._get_os_release_values()
        return get_steamos_version(values)

    def _is_steam_deck_device(
        self,
        board_name: str,
        product_name: str,
        sys_vendor: str,
        product_family: str,
    ) -> bool:
        return is_steam_deck_device(
            board_name,
            product_name,
            sys_vendor,
            product_family,
        )

    def _is_supported_handheld_vendor_device(
        self,
        board_name: str,
        product_name: str,
        sys_vendor: str,
        product_family: str,
    ) -> bool:
        return is_supported_handheld_vendor_device(
            board_name,
            product_name,
            sys_vendor,
            product_family,
        )

    def _parse_version_tuple(self, raw_version: str) -> tuple[int, int] | None:
        return parse_version_tuple(raw_version)

    def _steamos_version_is_supported(self, values: dict) -> bool:
        return steamos_version_is_supported(values)

    def _get_platform_support(
        self,
        board_name: str,
        product_name: str,
        sys_vendor: str,
        product_family: str,
        os_release_values: dict | None = None,
    ) -> dict:
        values = os_release_values if os_release_values is not None else self._get_os_release_values()
        return get_platform_support(
            board_name,
            product_name,
            sys_vendor,
            product_family,
            values,
        )

    def _get_device_metadata(
        self,
        board_name: str,
        product_name: str,
        sys_vendor: str = "",
        product_family: str = "",
    ) -> dict:
        return get_device_metadata(board_name, product_name, sys_vendor, product_family)

    def _get_current_platform_support(self) -> dict:
        board_name = self._read_file(os.path.join(DMI_PATH, "board_name"))
        product_name = self._read_file(os.path.join(DMI_PATH, "product_name"))
        product_family = self._read_file(os.path.join(DMI_PATH, "product_family"))
        sys_vendor = self._read_file(os.path.join(DMI_PATH, "sys_vendor"))
        return self._get_platform_support(
            board_name,
            product_name,
            sys_vendor,
            product_family,
        )

    def _unsupported_platform_state(self, defaults: dict, support: dict | None = None) -> dict:
        current_support = support if support is not None else self._get_current_platform_support()
        reason = current_support.get("reason", "Platform is not supported")
        return {
            **defaults,
            "status": reason,
            "details": reason,
        }

    def _guard_supported_action(self, area: str, action: str, details: dict | None = None) -> tuple[bool, dict]:
        support = self._get_current_platform_support()
        if support.get("supported", False):
            return True, support
        reason = support.get("reason", "Platform is not supported")
        decky.logger.warning(reason)
        self._debug_failure(area, action, reason, details)
        return False, support

    async def get_device_info(self) -> dict:
        info = default_device_info()

        try:
            os_release_values = self._get_os_release_values()
            info = populate_device_info(
                info,
                dmi_path=DMI_PATH,
                os_release_values=os_release_values,
                read_text_file=self._read_text_file_if_exists,
                read_cpu_model=self._read_cpu_model,
                read_kernel_version=self._read_kernel_version,
                read_memory_total_gb=self._read_memory_total_gb,
                get_device_metadata_fn=self._get_device_metadata,
                get_platform_support_fn=self._get_platform_support,
                get_steamos_version_fn=self._get_steamos_version,
            )
        except Exception as e:
            decky.logger.error(f"Failed to get device info: {e}")

        return info

    async def get_battery_info(self) -> dict:
        battery = default_battery_info(STEAMOS_CHARGE_FULL_PERCENT)

        try:
            battery_path = self._get_battery_path()
            battery = populate_battery_info(
                battery,
                battery_path=battery_path,
                charge_full_percent=STEAMOS_CHARGE_FULL_PERCENT,
                read_text_file=self._read_text_file_if_exists,
            )
            charge_limit_state = await self.get_charge_limit_state()
            battery["charge_limit"] = charge_limit_state.get("limit", battery["charge_limit"])
            battery["time_to_empty"], battery["time_to_full"] = self._estimate_battery_times(battery)
        except Exception as e:
            decky.logger.error(f"Failed to get battery info: {e}")

        return battery

    def _set_led_color(self, led_path: str, color: str, enabled: bool, brightness: int | None = None) -> bool:
        try:
            brightness_path = os.path.join(led_path, "brightness")
            multi_intensity_path = os.path.join(led_path, "multi_intensity")
            if not os.path.exists(brightness_path) or not os.path.exists(multi_intensity_path):
                return False

            max_brightness = self._get_led_max_brightness(led_path)
            target_brightness = self._get_saved_rgb_brightness() if brightness is None else brightness
            raw_brightness = self._scale_rgb_brightness_to_raw(target_brightness, max_brightness)

            if not enabled:
                with open(brightness_path, "w") as f:
                    f.write("0")
                return True

            rgb = color.lstrip("#")
            if len(rgb) != 6:
                return False

            r = int(rgb[0:2], 16)
            g = int(rgb[2:4], 16)
            b = int(rgb[4:6], 16)
            values = self._rgb_multi_intensity_values(led_path, r, g, b)

            with open(multi_intensity_path, "w") as f:
                f.write(" ".join(str(value) for value in values))
            with open(brightness_path, "w") as f:
                f.write(str(raw_brightness))
            return True
        except Exception as e:
            decky.logger.warning(f"Failed to apply RGB state: {e}")
            return False

    def _rgb_multi_index_tokens(self, led_path: str) -> list[str]:
        multi_index_path = os.path.join(led_path, "multi_index")
        try:
            if os.path.exists(multi_index_path):
                with open(multi_index_path, "r") as f:
                    return [token.strip().lower() for token in f.read().replace(",", " ").split()]
        except Exception:
            pass
        return []

    def _read_multi_intensity_values(self, led_path: str) -> list[int]:
        multi_intensity_path = os.path.join(led_path, "multi_intensity")
        try:
            if os.path.exists(multi_intensity_path):
                with open(multi_intensity_path, "r") as f:
                    return [int(value) for value in f.read().split() if value.strip()]
        except Exception:
            pass
        return []

    def _rgb_multi_intensity_values(self, led_path: str, r: int, g: int, b: int) -> list[int]:
        index_tokens = self._rgb_multi_index_tokens(led_path)
        if index_tokens:
            channel_values = {
                "red": r,
                "green": g,
                "blue": b,
                "white": 0,
            }
            values = [channel_values.get(token, 0) for token in index_tokens]
            if any(values):
                return values

        current_values = self._read_multi_intensity_values(led_path)
        if current_values and len(current_values) == 4 and max(current_values) > 255:
            color_int = (r << 16) | (g << 8) | b
            return [color_int] * len(current_values)

        if current_values and len(current_values) % 3 == 0:
            return [value for _ in range(len(current_values) // 3) for value in (r, g, b)]

        return [r, g, b]

    def _read_rgb_state_from_led(self, led_path: str) -> tuple[bool, str, int]:
        enabled = False
        color = RGB_COLOR_PRESETS[0]
        brightness = self._get_saved_rgb_brightness()

        try:
            brightness_path = os.path.join(led_path, "brightness")
            if os.path.exists(brightness_path):
                with open(brightness_path, "r") as f:
                    raw_brightness = int(f.read().strip() or "0")
                    enabled = raw_brightness > 0
                    if enabled:
                        brightness = self._scale_rgb_brightness_from_raw(
                            raw_brightness,
                            self._get_led_max_brightness(led_path),
                        )
        except Exception:
            enabled = False

        try:
            values = self._read_multi_intensity_values(led_path)
            index_tokens = self._rgb_multi_index_tokens(led_path)
            if values and index_tokens:
                by_channel = dict(zip(index_tokens, values))
                color = "#{:02X}{:02X}{:02X}".format(
                    min(max(by_channel.get("red", 0), 0), 255),
                    min(max(by_channel.get("green", 0), 0), 255),
                    min(max(by_channel.get("blue", 0), 0), 255),
                )
            elif values and len(values) == 4 and max(values) > 255:
                color_int = values[0]
                r = (color_int >> 16) & 0xFF
                g = (color_int >> 8) & 0xFF
                b = color_int & 0xFF
                color = f"#{r:02X}{g:02X}{b:02X}"
            elif len(values) >= 3:
                r, g, b = values[:3]
                color = "#{:02X}{:02X}{:02X}".format(
                    min(max(r, 0), 255),
                    min(max(g, 0), 255),
                    min(max(b, 0), 255),
                )
        except Exception:
            color = RGB_COLOR_PRESETS[0]

        return enabled, color, brightness

    def _get_rgb_controller(self) -> RgbController:
        return RgbController(
            logger=decky.logger,
            get_settings=lambda: self.settings,
            get_platform_support=self._get_current_platform_support,
            get_rgb_backend=self._get_rgb_backend,
            get_rgb_supported_modes=self._get_rgb_supported_modes,
            get_rgb_mode_capabilities=self._get_rgb_mode_capabilities,
            read_rgb_state_from_led=self._read_rgb_state_from_led,
            get_saved_rgb_mode=self._get_saved_rgb_mode,
            normalize_rgb_speed=self._normalize_rgb_speed,
            normalize_rgb_color=self._normalize_rgb_color,
            get_saved_rgb_brightness=self._get_saved_rgb_brightness,
            normalize_rgb_brightness=self._normalize_rgb_brightness,
            set_led_color=self._set_led_color,
            write_hid_rgb=self._write_hid_rgb,
            save_settings=self._save_settings,
            debug_attempt=self._debug_attempt,
            debug_success=self._debug_success,
            debug_failure=self._debug_failure,
        )

    def _get_steamos_manager(self) -> SteamOsManagerClient:
        if self.steamos_manager is None:
            self.steamos_manager = SteamOsManagerClient(decky.logger, self.runtime)
        return self.steamos_manager

    def _get_gamescope_settings(self) -> GamescopeSettingsClient:
        if self.gamescope_settings is None:
            self.gamescope_settings = GamescopeSettingsClient(decky.logger, self.runtime)
        return self.gamescope_settings

    def _get_performance_service(self) -> PerformanceService:
        return PerformanceService(
            logger=decky.logger,
            native_profiles=NATIVE_PERFORMANCE_PROFILES,
            get_platform_support=self._get_current_platform_support,
            get_steamos_manager=self._get_steamos_manager,
            get_profiles_callback=self.get_performance_profiles,
            debug_attempt=self._debug_attempt,
            debug_success=self._debug_success,
            debug_failure=self._debug_failure,
        )

    def _get_display_service(self) -> DisplayService:
        return DisplayService(
            logger=decky.logger,
            get_platform_support=self._get_current_platform_support,
            get_gamescope_settings=self._get_gamescope_settings,
            command_info=self._command_info,
            command_exists=self._command_exists,
            run_command=self._run_command_output,
            get_fps_presets=self._get_fps_presets,
            debug_attempt=self._debug_attempt,
            debug_success=self._debug_success,
            debug_failure=self._debug_failure,
        )

    def _get_state_aggregator(self) -> StateAggregator:
        return StateAggregator(
            get_performance_modes=self.get_performance_modes,
            get_cpu_settings=self.get_cpu_settings,
            get_rgb_state=self.get_rgb_state,
            get_display_sync_state=self.get_display_sync_state,
            get_fps_limit_state=self.get_fps_limit_state,
            get_charge_limit_state=self.get_charge_limit_state,
            get_device_info=self.get_device_info,
            get_battery_info=self.get_battery_info,
            get_performance_profiles=self.get_performance_profiles,
            get_current_tdp=self.get_current_tdp,
            get_optimization_states=self.get_optimization_states,
            get_runtime_state=self._get_runtime_state,
            get_runtime_backend=self.runtime.execution_backend,
            get_debug_log_snapshot=lambda: list(self.debug_log),
            debug_event=self._debug_event,
        )

    def _legion_go_s_rgb_commands(
        self,
        color: str,
        enabled: bool,
        brightness: int = RGB_DEFAULT_BRIGHTNESS,
        mode: str = RGB_DEFAULT_MODE,
        speed: str = RGB_DEFAULT_SPEED,
    ) -> list[bytes]:
        return legion_hid_rgb_commands(
            {"config": {"protocol": "legion_go_s"}},
            color,
            enabled,
            brightness,
            mode,
            speed,
        )

    def _legion_go_tablet_rgb_commands(
        self,
        color: str,
        enabled: bool,
        brightness: int = RGB_DEFAULT_BRIGHTNESS,
        mode: str = RGB_DEFAULT_MODE,
        speed: str = RGB_DEFAULT_SPEED,
    ) -> list[bytes]:
        return legion_hid_rgb_commands(
            {"config": {"protocol": "legion_go_tablet"}},
            color,
            enabled,
            brightness,
            mode,
            speed,
        )

    def _hex_to_rgb(self, color: str) -> tuple[int, int, int]:
        return hex_to_rgb(color)

    def _rgb_hid_padded(self, payload: list[int]) -> bytes:
        return rgb_hid_padded(payload)

    def _asus_rgb_brightness_level(self, brightness: int) -> int:
        normalized = self._normalize_rgb_brightness(brightness)
        if normalized <= 0:
            return 0x00
        if normalized <= 33:
            return 0x01
        if normalized <= 66:
            return 0x02
        return 0x03

    def _asus_rgb_config_command(self, boot: bool = False, charging: bool = False) -> bytes:
        payload = [0x5A, 0xD1, 0x09, 0x01, 0x02 + (0x09 if boot else 0) + (0x04 if charging else 0)]
        return bytes(payload) + bytes(max(0, 64 - len(payload)))

    def _disable_asus_dynamic_lighting(self, device: dict) -> None:
        if device.get("product_id") != 0x1B4C:
            return
        module = self._hid_module()
        if module is None or not hasattr(module, "Device"):
            return
        try:
            for candidate in self._hid_module_devices():
                if candidate.get("vendor_id") != ASUS_ALLY_HID["vid"]:
                    continue
                if candidate.get("product_id") != 0x1B4C:
                    continue
                application = ((candidate.get("usage_page") or 0) << 16) | (candidate.get("usage") or 0)
                if application != 0x00590001:
                    continue
                dyn_device = module.Device(path=candidate["path"])
                dyn_device.write(bytes([0x06, 0x01]))
                close = getattr(dyn_device, "close", None)
                if callable(close):
                    close()
                break
        except Exception:
            pass

    def _asus_hid_rgb_commands(
        self,
        color: str,
        enabled: bool,
        brightness: int = RGB_DEFAULT_BRIGHTNESS,
        mode: str = RGB_DEFAULT_MODE,
        speed: str = RGB_DEFAULT_SPEED,
    ) -> list[bytes]:
        return asus_hid_rgb_commands(color, enabled, brightness, mode, speed)

    def _legion_hid_rgb_commands(
        self,
        device: dict,
        color: str,
        enabled: bool,
        brightness: int = RGB_DEFAULT_BRIGHTNESS,
        mode: str = RGB_DEFAULT_MODE,
        speed: str = RGB_DEFAULT_SPEED,
    ) -> list[bytes]:
        return legion_hid_rgb_commands(device, color, enabled, brightness, mode, speed)

    def _open_hid_module_device(self, path):
        module = self._hid_module()
        if module is None:
            return None
        try:
            if hasattr(module, "Device"):
                return module.Device(path=path)
            if hasattr(module, "device"):
                device = module.device()
                device.open_path(path)
                return device
        except Exception as e:
            decky.logger.warning(f"Failed to open HID device: {e}")
        return None

    def _write_hid_rgb(
        self,
        backend: dict,
        color: str,
        enabled: bool,
        brightness: int | None = None,
        mode: str | None = None,
        speed: str | None = None,
    ) -> bool:
        device = backend["device"]
        target_brightness = self._get_saved_rgb_brightness() if brightness is None else brightness
        target_mode = self._get_saved_rgb_mode(backend) if mode is None else mode
        target_speed = self._normalize_rgb_speed(
            self.settings.get("rgb_speed", RGB_DEFAULT_SPEED) if speed is None else speed
        )
        commands = self._legion_hid_rgb_commands(
            device,
            color,
            enabled,
            target_brightness,
            target_mode,
            target_speed,
        )
        if not commands:
            return False

        if backend["type"] == "asus_hid":
            self._disable_asus_dynamic_lighting(device)

        if device.get("backend") == "hidraw":
            try:
                with open(device["path"], "wb", buffering=0) as f:
                    for command in commands:
                        f.write(command)
                return True
            except Exception as e:
                decky.logger.warning(f"Failed to write HID raw RGB command: {e}")
                return False

        hid_device = self._open_hid_module_device(device.get("path"))
        if hid_device is None:
            return False

        try:
            for command in commands:
                hid_device.write(command)
            close = getattr(hid_device, "close", None)
            if callable(close):
                close()
            return True
        except Exception as e:
            decky.logger.warning(f"Failed to write HID RGB command: {e}")
            return False

    async def get_rgb_state(self) -> dict:
        return await self._get_rgb_controller().get_state()

    async def set_rgb_enabled(self, enabled: bool) -> bool:
        return await self._get_rgb_controller().set_enabled(enabled)

    async def set_rgb_color(self, color: str) -> bool:
        return await self._get_rgb_controller().set_color(color)

    async def set_rgb_brightness(self, brightness: int) -> bool:
        return await self._get_rgb_controller().set_brightness(brightness)

    async def set_rgb_mode(self, mode: str) -> bool:
        return await self._get_rgb_controller().set_mode(mode)

    async def set_rgb_speed(self, speed: str) -> bool:
        return await self._get_rgb_controller().set_speed(speed)

    def _command_exists(self, cmd: str) -> bool:
        return self.runtime.resolve_command(cmd).get("available", False)

    def _command_info(self, cmd: str) -> dict:
        return self.runtime.resolve_command(cmd)

    def _is_system_protected_path(self, path: str | None) -> bool:
        if not path:
            return False
        normalized = os.path.abspath(path)
        return normalized.startswith(SYSTEM_PROTECTED_PREFIXES)

    def _route_path_via_host(self, path: str | None) -> bool:
        return bool(path) and self.runtime.execution_backend() == "flatpak-host" and self._is_system_protected_path(path)

    def _needs_noninteractive_sudo(self, path: str | None = None) -> bool:
        if os.geteuid() == 0:
            return False
        if path is not None:
            return self._is_system_protected_path(path)
        return True

    def _has_noninteractive_sudo(self) -> bool:
        if os.geteuid() == 0:
            return True
        if self._sudo_available_cache is not None:
            return self._sudo_available_cache
        try:
            result = self.runtime.run_host_command(
                ["sudo", "-n", "true"],
                timeout=DEFAULT_COMMAND_TIMEOUT,
                env=self.runtime.host_env(),
            )
            self._sudo_available_cache = result.returncode == 0
        except Exception:
            self._sudo_available_cache = False
        return self._sudo_available_cache

    def _host_file_exists(self, path: str) -> bool:
        if not self._route_path_via_host(path):
            return os.path.exists(path)
        try:
            result = self.runtime.run_host_command(
                ["test", "-e", path],
                timeout=DEFAULT_COMMAND_TIMEOUT,
                env=self.runtime.host_env(),
            )
            return result.returncode == 0
        except Exception:
            return False

    def _read_text_file(self, path: str, default: str = "") -> str:
        try:
            if self._route_path_via_host(path):
                result = self.runtime.run_host_command(
                    ["cat", path],
                    timeout=DEFAULT_COMMAND_TIMEOUT,
                    env=self.runtime.host_env(),
                )
                if result.returncode != 0:
                    return default
                return result.stdout
            if os.path.exists(path):
                with open(path, "r") as f:
                    return f.read()
        except Exception:
            pass
        return default

    def _write_managed_file(self, path: str, content: str, mode: int | None = None):
        directory = os.path.dirname(path)
        if self._route_path_via_host(path) or needs_privilege_escalation(path):
            if directory:
                self._run_command(["mkdir", "-p", directory], use_sudo=True)
            self._write_file(path, content, use_sudo=True)
            if mode is not None:
                self._run_command(["chmod", f"{mode:o}", path], use_sudo=True)
            return

        os.makedirs(directory, exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        if mode is not None:
            os.chmod(path, mode)

    def _remove_file(self, path: str):
        try:
            if self._host_file_exists(path):
                if self._route_path_via_host(path) or needs_privilege_escalation(path):
                    self._run_command(["rm", "-f", path], use_sudo=True)
                else:
                    os.remove(path)
        except Exception as e:
            decky.logger.warning(f"Failed to remove {path}: {e}")

    def _cleanup_legacy_atomic_manifests(self):
        for path in LEGACY_ATOMIC_PATHS:
            self._remove_file(path)

    def _cleanup_legacy_managed_files(self):
        for path in LEGACY_MANAGED_PATHS:
            self._remove_file(path)

    def _atomic_managed_entries(self) -> list[str]:
        checks = [
            (SCX_DEFAULT_PATH, ['SCX_SCHEDULER="scx_lavd"', 'SCX_FLAGS="--performance"']),
            (
                MEMORY_SYSCTL_PATH,
                ["vm.swappiness = 10", "vm.min_free_kbytes = 524288", "vm.dirty_ratio = 5"],
            ),
            (THP_TMPFILES_PATH, ["madvise"]),
            (NPU_BLACKLIST_PATH, ["blacklist amdxdna"]),
            (USB_WAKE_SERVICE_PATH, ["Xbox Companion - Block USB Wake"]),
            (USB_WAKE_SCRIPT_PATH, ["xbox-companion-usb-wake"]),
            (USB_WAKE_CONFIG_PATH, ["# xbox-companion-usb-wake"]),
        ]
        return atomic_managed_entries(
            checks,
            file_contains_all=self._file_contains_all,
            file_contains_any=self._file_contains_any,
            grub_default_path=GRUB_DEFAULT_PATH,
            kernel_params=self._managed_kernel_params(),
        )

    def _refresh_atomic_manifest(self):
        refresh_atomic_manifest(
            manifest_path=ATOMIC_MANIFEST_PATH,
            entries=self._atomic_managed_entries(),
            write_managed_file=self._write_managed_file,
            remove_file=self._remove_file,
            cleanup_legacy_managed_files=self._cleanup_legacy_managed_files,
            cleanup_legacy_atomic_manifests=self._cleanup_legacy_atomic_manifests,
        )

    def _atomic_manifest_contains(self, paths: list[str]) -> bool:
        return self._file_contains_all(ATOMIC_MANIFEST_PATH, paths)

    def _migrate_atomic_manifest_if_needed(self):
        migrate_atomic_manifest_if_needed(
            legacy_atomic_paths=LEGACY_ATOMIC_PATHS,
            host_file_exists=self._host_file_exists,
            refresh_atomic_manifest_fn=self._refresh_atomic_manifest,
        )

    def _remove_managed_file(
        self,
        path: str,
        removed_files: list[str],
        skipped_files: list[str],
        errors: list[str],
        needles: list[str] | None = None,
        ):
        remove_managed_file(
            path=path,
            needles=needles,
            removed_files=removed_files,
            skipped_files=skipped_files,
            errors=errors,
            host_file_exists=self._host_file_exists,
            file_contains_all=self._file_contains_all,
            route_path_via_host=self._route_path_via_host,
            optimization_state_path=OPTIMIZATION_STATE_PATH,
            needs_privilege_escalation_fn=needs_privilege_escalation,
            run_command=self._run_command,
        )

    def _run_command(self, command: list[str], use_sudo: bool = False) -> tuple[bool, str]:
        try:
            if use_sudo and self._needs_noninteractive_sudo():
                if not self._has_noninteractive_sudo():
                    return False, "Non-interactive sudo is unavailable for system writes"
                final_command = ["sudo", "-n", *command]
            else:
                final_command = command
            result = self.runtime.run_host_command(
                final_command,
                timeout=20,
                env=self.runtime.host_env(),
            )
        except FileNotFoundError:
            return False, f"{command[0]} is not installed"
        except subprocess.TimeoutExpired:
            return False, f"{command[0]} timed out"
        except Exception as e:
            return False, str(e)

        if result.returncode != 0:
            return False, result.stderr.strip() or result.stdout.strip()

        return True, ""

    def _write_file(self, path: str, content: str, use_sudo: bool = False) -> tuple[bool, str]:
        try:
            if self._route_path_via_host(path):
                if use_sudo and self._needs_noninteractive_sudo(path):
                    if not self._has_noninteractive_sudo():
                        return False, "Non-interactive sudo is unavailable for system writes"
                    command = ["sudo", "-n", "tee", path]
                else:
                    command = ["tee", path]
                result = self.runtime.run_host_command(
                    command,
                    input=content,
                    timeout=20,
                    env=self.runtime.host_env(),
                )
            elif use_sudo and needs_privilege_escalation(path):
                if not self._has_noninteractive_sudo():
                    return False, "Non-interactive sudo is unavailable for system writes"
                result = self.runtime.run_host_command(
                    ["sudo", "-n", "tee", path],
                    input=content,
                    timeout=20,
                    env=self.runtime.host_env(),
                )
            else:
                with open(path, "w") as f:
                    f.write(content)
                return True, ""
        except FileNotFoundError:
            return False, "tee is not installed"
        except subprocess.TimeoutExpired:
            return False, "file write timed out"
        except Exception as e:
            return False, str(e)

        if result.returncode != 0:
            return False, result.stderr.strip() or result.stdout.strip()

        return True, ""

    def _run_command_output(self, command: list[str]) -> tuple[bool, str]:
        try:
            result = self.runtime.run(
                command,
                timeout=20,
                env=self.runtime.host_env(),
            )
        except FileNotFoundError:
            return False, f"{command[0]} is not installed"
        except subprocess.TimeoutExpired:
            return False, f"{command[0]} timed out"
        except Exception as e:
            return False, str(e)

        if result.returncode != 0:
            return False, result.stderr.strip() or result.stdout.strip()

        return True, result.stdout.strip()

    def _run_optional_command(self, command: list[str], use_sudo: bool = False) -> str:
        success, error = self._run_command(command, use_sudo=use_sudo)
        if not success:
            decky.logger.warning(f"Optional command failed: {' '.join(command)}: {error}")
            return error
        return ""

    def _read_optimization_state(self) -> dict:
        return read_optimization_state(
            optimization_state_path=OPTIMIZATION_STATE_PATH,
            host_file_exists=self._host_file_exists,
            read_text_file=self._read_text_file,
            warn=decky.logger.warning,
        )

    def _write_optimization_state(self, state: dict):
        write_optimization_state(
            state,
            optimization_state_path=OPTIMIZATION_STATE_PATH,
            route_path_via_host=self._route_path_via_host,
            needs_privilege_escalation_fn=needs_privilege_escalation,
            run_command=self._run_command,
            write_file=self._write_file,
            remove_file=self._remove_file,
            warn=decky.logger.warning,
        )

    def _pop_optimization_state_value(self, key: str):
        return pop_optimization_state_value(
            key=key,
            read_optimization_state_fn=self._read_optimization_state,
            write_optimization_state_fn=self._write_optimization_state,
        )

    def _system_write_access_available(self) -> bool:
        if os.geteuid() == 0:
            return True
        return self._has_noninteractive_sudo()

    def _optimization_runtime_details(self) -> str:
        if self._system_write_access_available():
            return ""
        return "System writes require root or passwordless sudo; the current Decky backend cannot elevate non-interactively"

    def _get_fps_presets(self) -> list[int]:
        presets = list(FPS_NATIVE_PRESET_VALUES)
        presets.extend(self._get_supported_high_refresh_rates())
        presets.append(FPS_OPTION_DISABLED)
        return presets

    def _get_supported_high_refresh_rates(self) -> list[int]:
        if not self._command_exists("xrandr"):
            return []

        success, output = self._run_command_output(["xrandr", "--current"])
        if not success:
            return []

        refresh_rates = set()
        for line in output.splitlines():
            stripped = line.strip()
            if not stripped or not line[:1].isspace():
                continue

            parts = stripped.split()
            if not parts or "x" not in parts[0]:
                continue

            for token in parts[1:]:
                candidate = token.rstrip("*+")
                if not candidate or any(char not in "0123456789." for char in candidate):
                    continue

                try:
                    value = float(candidate)
                except ValueError:
                    continue

                rounded = int(round(value))
                if rounded >= FPS_HIGH_REFRESH_MIN:
                    refresh_rates.add(rounded)

        return sorted(refresh_rates)

    def _systemctl(self, *args: str) -> str:
        return systemctl(*args, run_command=self._run_command, warn=decky.logger.warning)

    def _service_exists(self, service: str) -> bool:
        return service_exists(
            service,
            host_file_exists=self._host_file_exists,
            runtime=self.runtime,
            default_timeout=DEFAULT_COMMAND_TIMEOUT,
        )

    def _service_enabled(self, service: str) -> bool:
        return service_enabled(
            service,
            runtime=self.runtime,
            default_timeout=DEFAULT_COMMAND_TIMEOUT,
        )

    def _service_active(self, service: str) -> bool:
        return service_active(
            service,
            runtime=self.runtime,
            default_timeout=DEFAULT_COMMAND_TIMEOUT,
        )

    def _read_sysctl(self, key: str) -> str:
        return read_sysctl(
            key,
            runtime=self.runtime,
            default_timeout=DEFAULT_COMMAND_TIMEOUT,
        )

    def _write_sysctl(self, key: str, value: str):
        write_sysctl(key, value, run_command=self._run_command)

    def _file_contains_all(self, path: str, needles: list[str]) -> bool:
        try:
            if not self._host_file_exists(path):
                return False
            contents = self._read_text_file(path, "")
            return all(needle in contents for needle in needles)
        except Exception:
            return False

    def _file_contains_any(self, path: str, needles: list[str]) -> bool:
        try:
            if not self._host_file_exists(path):
                return False
            contents = self._read_text_file(path, "")
            return any(needle in contents for needle in needles)
        except Exception:
            return False

    def _is_amd_platform(self) -> bool:
        return is_amd_platform(read_file=self._read_file)

    def _amd_npu_present(self) -> bool:
        return amd_npu_present(
            command_exists=self._command_exists,
            run_command_output=self._run_command_output,
        )

    def _usb_wake_control_available(self) -> bool:
        return usb_wake_control_available(
            acpi_wakeup_path=ACPI_WAKEUP_PATH,
            command_exists=self._command_exists,
        )

    def _read_acpi_wakeup_entries(self) -> list[dict]:
        return read_acpi_wakeup_entries(acpi_wakeup_path=ACPI_WAKEUP_PATH)

    def _read_cmdline(self) -> str:
        return read_cmdline()

    def _read_acpi_wake_enabled_devices(self) -> list[str]:
        return read_acpi_wake_enabled_devices(acpi_wakeup_path=ACPI_WAKEUP_PATH)

    def _get_usb_wake_candidate_devices(self) -> list[str]:
        return usb_wake_candidate_devices(entries=self._read_acpi_wakeup_entries())

    def _read_usb_wake_configured_devices(self) -> list[str]:
        devices = []
        seen = set()
        for raw_line in self._read_text_file(USB_WAKE_CONFIG_PATH, "").splitlines():
            device = raw_line.strip()
            if not device or device.startswith("#"):
                continue
            if device in seen:
                continue
            seen.add(device)
            devices.append(device)
        return devices

    def _usb_wake_service_name(self) -> str:
        return os.path.basename(USB_WAKE_SERVICE_PATH)

    def _usb_wake_service_content(self) -> str:
        return f"""[Unit]
Description=Xbox Companion - Block USB Wake
ConditionPathExists={USB_WAKE_SCRIPT_PATH}
ConditionPathExists={USB_WAKE_CONFIG_PATH}
ConditionPathExists={ACPI_WAKEUP_PATH}
After=local-fs.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart={USB_WAKE_SCRIPT_PATH} {USB_WAKE_CONFIG_PATH} {ACPI_WAKEUP_PATH}

[Install]
WantedBy=multi-user.target
"""

    def _usb_wake_script_content(self) -> str:
        return """#!/bin/sh
set -eu

CONFIG_PATH="${1:-}"
WAKE_PATH="${2:-}"

[ -n "$CONFIG_PATH" ] || exit 0
[ -n "$WAKE_PATH" ] || exit 0
[ -r "$CONFIG_PATH" ] || exit 0
[ -w "$WAKE_PATH" ] || exit 0

# xbox-companion-usb-wake
while IFS= read -r device || [ -n "$device" ]; do
  case "$device" in
    ""|"#"*)
      continue
      ;;
  esac

  if awk -v target="$device" '$1 == target && $3 == "*enabled" { found=1 } END { exit(found ? 0 : 1) }' "$WAKE_PATH"; then
    printf '%s\n' "$device" > "$WAKE_PATH"
  fi
done < "$CONFIG_PATH"
"""

    def _usb_wake_config_content(self, devices: list[str]) -> str:
        unique_devices = []
        seen = set()
        for device in devices:
            normalized = str(device).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique_devices.append(normalized)
        lines = ["# xbox-companion-usb-wake", *unique_devices]
        return "\n".join(lines) + "\n"

    def _set_acpi_wake_devices(self, devices: list[str]):
        set_acpi_wake_devices(
            devices,
            acpi_wakeup_path=ACPI_WAKEUP_PATH,
            write_file=self._write_file,
            warn=decky.logger.warning,
        )

    def _thp_is_madvise(self) -> bool:
        return thp_is_madvise(thp_enabled_path=THP_ENABLED_PATH)

    def _read_thp_mode(self) -> str:
        return read_thp_mode(thp_enabled_path=THP_ENABLED_PATH)

    def _write_thp_mode(self, mode: str):
        write_thp_mode(
            mode,
            thp_enabled_path=THP_ENABLED_PATH,
            write_file=self._write_file,
            warn=decky.logger.warning,
        )

    def _kernel_param_active(self, param: str) -> bool:
        return kernel_param_active(param, read_cmdline_fn=self._read_cmdline)

    def _grub_param_configured(self, param: str) -> bool:
        return grub_param_configured(
            param,
            grub_default_path=GRUB_DEFAULT_PATH,
            file_contains_all=self._file_contains_all,
        )

    def _managed_kernel_params(self) -> list[str]:
        known_params = {option["param"] for option in GRUB_KERNEL_PARAM_OPTIONS.values()}
        return managed_kernel_params_from_state(self._read_optimization_state(), known_params)

    def _kernel_param_managed(self, param: str) -> bool:
        return param in self._managed_kernel_params()

    def _remember_kernel_param_state(self, param: str, was_configured: bool):
        state = self._read_optimization_state()
        self._write_optimization_state(
            remember_kernel_param_state(state, param, was_configured)
        )

    def _forget_kernel_param_state(self, param: str) -> bool:
        state = self._read_optimization_state()
        next_state, was_configured = forget_kernel_param_state(state, param)
        self._write_optimization_state(next_state)
        return was_configured

    def _update_grub_param(self, param: str, enabled: bool) -> str:
        return update_grub_param(
            grub_default_path=GRUB_DEFAULT_PATH,
            param=param,
            enabled=enabled,
            host_file_exists=self._host_file_exists,
            read_text_file=self._read_text_file,
            write_file=self._write_file,
            refresh_atomic_manifest_fn=self._refresh_atomic_manifest,
            command_exists=self._command_exists,
            run_command=self._run_command,
            warn=decky.logger.warning,
        )

    def _optimization_state(
        self,
        key: str,
        name: str,
        description: str,
        enabled: bool,
        active: bool,
        available: bool = True,
        needs_reboot: bool = False,
        details: str = "",
        risk_note: str = "",
    ) -> dict:
        return optimization_state(
            key,
            name,
            description,
            enabled,
            active,
            available,
            needs_reboot,
            details,
            risk_note,
        )

    def _get_lavd_state(self) -> dict:
        runtime_details = self._optimization_runtime_details()
        configured = self._file_contains_all(
            SCX_DEFAULT_PATH,
            ['SCX_SCHEDULER="scx_lavd"', 'SCX_FLAGS="--performance"'],
        )
        atomic = self._atomic_manifest_contains([SCX_DEFAULT_PATH])
        service_active = self._service_active("scx.service")
        service_enabled = self._service_enabled("scx.service")
        enabled = configured and atomic and service_enabled

        return self._optimization_state(
            "lavd",
            "LAVD Scheduler",
            "Switch SteamOS scheduling to scx_lavd for smoother frame delivery.",
            enabled,
            service_active,
            available=self._command_exists("systemctl") and self._service_exists("scx.service"),
            details=("SteamOS scx.service" if self._service_exists("scx.service") else "scx.service unavailable") + (f" | {runtime_details}" if runtime_details else ""),
            risk_note="Touches a system service.",
        )

    def _get_swap_protect_state(self) -> dict:
        runtime_details = self._optimization_runtime_details()
        configured = self._file_contains_all(
            MEMORY_SYSCTL_PATH,
            ["vm.swappiness = 10", "vm.min_free_kbytes = 524288", "vm.dirty_ratio = 5"],
        )
        atomic = self._atomic_manifest_contains([MEMORY_SYSCTL_PATH])
        enabled = configured and atomic
        runtime = (
            self._read_sysctl("vm.swappiness") == MEMORY_SYSCTL_VALUES["vm.swappiness"]
            and self._read_sysctl("vm.min_free_kbytes") == MEMORY_SYSCTL_VALUES["vm.min_free_kbytes"]
            and self._read_sysctl("vm.dirty_ratio") == MEMORY_SYSCTL_VALUES["vm.dirty_ratio"]
        )

        return self._optimization_state(
            "swap_protect",
            "Swap Protection",
            "Applies conservative memory sysctl tuning for smoother pressure handling.",
            enabled,
            runtime,
            available=self._command_exists("sysctl"),
            needs_reboot=(enabled and not runtime) or (not enabled and runtime),
            details="swappiness 10, min_free_kbytes 524288, dirty_ratio 5" + (f" | {runtime_details}" if runtime_details else ""),
            risk_note="Runtime sysctl values may remain until they are reloaded.",
        )

    def _get_thp_madvise_state(self) -> dict:
        runtime_details = self._optimization_runtime_details()
        configured = self._file_contains_all(THP_TMPFILES_PATH, ["madvise"])
        atomic = self._atomic_manifest_contains([THP_TMPFILES_PATH])
        enabled = configured and atomic
        runtime = self._thp_is_madvise()

        return self._optimization_state(
            "thp_madvise",
            "THP Madvise",
            "Sets Transparent Huge Pages to madvise.",
            enabled,
            runtime,
            available=os.path.exists(THP_ENABLED_PATH),
            needs_reboot=(enabled and not runtime) or (not enabled and runtime),
            details="Transparent Huge Pages mode: madvise" + (f" | {runtime_details}" if runtime_details else ""),
            risk_note="Some games prefer different THP behavior.",
        )

    def _get_npu_blacklist_state(self) -> dict:
        runtime_details = self._optimization_runtime_details()
        configured = self._file_contains_all(NPU_BLACKLIST_PATH, ["blacklist amdxdna"])
        atomic = self._atomic_manifest_contains([NPU_BLACKLIST_PATH])
        enabled = configured and atomic
        module_loaded = os.path.exists("/sys/module/amdxdna")
        npu_present = self._amd_npu_present()

        return self._optimization_state(
            "npu_blacklist",
            "NPU Blacklist",
            "Blacklists the AMD NPU module on handhelds that expose an AMD XDNA NPU.",
            enabled,
            enabled and not module_loaded,
            available=self._is_amd_platform() and (npu_present or configured),
            needs_reboot=enabled and module_loaded,
            details="Module: amdxdna" + (f" | {runtime_details}" if runtime_details else ""),
            risk_note="Requires reboot when the module is already loaded.",
        )

    def _get_usb_wake_state(self) -> dict:
        runtime_details = self._optimization_runtime_details()
        service_name = self._usb_wake_service_name()
        service_configured = self._host_file_exists(USB_WAKE_SERVICE_PATH)
        script_configured = self._host_file_exists(USB_WAKE_SCRIPT_PATH)
        config_configured = self._host_file_exists(USB_WAKE_CONFIG_PATH)
        atomic = self._atomic_manifest_contains(
            [USB_WAKE_SERVICE_PATH, USB_WAKE_SCRIPT_PATH, USB_WAKE_CONFIG_PATH]
        )
        legacy_service = service_configured and self._file_contains_all(
            USB_WAKE_SERVICE_PATH,
            ["ExecStart=/bin/sh -c", '/proc/acpi/wakeup'],
        )
        service_enabled = self._service_enabled(service_name)
        service_active = self._service_active(service_name)
        configured_devices = self._read_usb_wake_configured_devices()
        if not configured_devices and legacy_service:
            previous_devices = self._read_optimization_state().get("usb_wake_enabled_devices", [])
            if isinstance(previous_devices, list):
                configured_devices = [str(device).strip() for device in previous_devices if str(device).strip()]
        enabled = service_configured and service_enabled and (
            (script_configured and config_configured and atomic) or legacy_service
        )
        enabled_devices = set(self._read_acpi_wake_enabled_devices())
        runtime_active = bool(configured_devices) and all(
            device not in enabled_devices for device in configured_devices
        )
        candidate_devices = self._get_usb_wake_candidate_devices()
        available = self._usb_wake_control_available() and (
            bool(candidate_devices) or bool(configured_devices) or enabled
        )
        details = "Managed ACPI USB wake devices"
        if configured_devices:
            details += f": {', '.join(configured_devices)}"
        else:
            details += f": {'none detected' if not candidate_devices else ', '.join(candidate_devices)}"
        details += " | Applies /proc/acpi/wakeup policy through a managed systemd unit"
        if runtime_details:
            details += f" | {runtime_details}"

        return self._optimization_state(
            "usb_wake",
            "USB Wake Guard",
            "Disables USB wake sources that can wake the handheld unexpectedly.",
            enabled,
            service_active and runtime_active,
            available=available,
            details=details,
            risk_note="Touches ACPI wake sources and a managed systemd unit.",
        )

    def _get_kernel_param_state(self, key: str, option: dict) -> dict:
        runtime_details = self._optimization_runtime_details()
        param = option["param"]
        configured = self._grub_param_configured(param)
        atomic = self._atomic_manifest_contains([GRUB_DEFAULT_PATH])
        enabled = configured and atomic and self._kernel_param_managed(param)
        active = self._kernel_param_active(param)

        return self._optimization_state(
            key,
            option["name"],
            option["description"],
            enabled,
            active,
            available=self._host_file_exists(GRUB_DEFAULT_PATH) and self._is_amd_platform(),
            needs_reboot=(enabled and not active) or (not enabled and active),
            details=option["details"] + (f" | {runtime_details}" if runtime_details else ""),
            risk_note="Modifies boot configuration and requires reboot to become active.",
        )

    async def get_optimization_states(self) -> dict:
        support = self._get_current_platform_support()
        if not support.get("supported", False):
            return {
                "states": [
                    self._optimization_state(
                        "platform_guard",
                        "Platform Guard",
                        support.get("reason", "Platform is not supported"),
                        False,
                        False,
                        available=False,
                    )
                ],
            }

        self._migrate_atomic_manifest_if_needed()

        return {
            "states": [definition["state_reader"]() for definition in self._optimization_registry()],
        }

    def _optimization_registry(self) -> list[dict]:
        registry = [
            {
                "key": "lavd",
                "state_reader": self._get_lavd_state,
                "handler": self._set_lavd_enabled,
            },
            {
                "key": "swap_protect",
                "state_reader": self._get_swap_protect_state,
                "handler": self._set_swap_protect_enabled,
            },
            {
                "key": "thp_madvise",
                "state_reader": self._get_thp_madvise_state,
                "handler": self._set_thp_madvise_enabled,
            },
            {
                "key": "npu_blacklist",
                "state_reader": self._get_npu_blacklist_state,
                "handler": self._set_npu_blacklist_enabled,
            },
            {
                "key": "usb_wake",
                "state_reader": self._get_usb_wake_state,
                "handler": self._set_usb_wake_enabled,
            },
        ]
        for param_key, option in GRUB_KERNEL_PARAM_OPTIONS.items():
            registry.append(
                {
                    "key": param_key,
                    "state_reader": lambda selected_key=param_key, selected_option=option: self._get_kernel_param_state(
                        selected_key,
                        selected_option,
                    ),
                    "handler": lambda value, selected=option["param"]: self._set_kernel_param_enabled(selected, value),
                }
            )
        return registry

    def _optimization_handlers(self) -> dict:
        return {
            definition["key"]: definition["handler"]
            for definition in self._optimization_registry()
        }

    def _optimization_state_readers(self) -> dict:
        return {
            definition["key"]: definition["state_reader"]
            for definition in self._optimization_registry()
        }

    async def set_optimization_enabled(self, key: str, enabled: bool) -> bool:
        try:
            normalized_key = str(key or "").strip().lower()
            self._debug_attempt("optimization", "set_enabled", "Toggling optimization", {"key": key, "normalized_key": normalized_key, "enabled": enabled})
            support = self._get_current_platform_support()
            if not support.get("supported", False):
                decky.logger.warning(support.get("reason", "Platform is not supported"))
                self._debug_failure("optimization", "set_enabled", support.get("reason", "Platform is not supported"), {"key": key, "normalized_key": normalized_key, "enabled": enabled})
                return False
            if not self._system_write_access_available():
                message = self._optimization_runtime_details()
                decky.logger.warning(message)
                self._debug_failure("optimization", "set_enabled", message, {"key": key, "normalized_key": normalized_key, "enabled": enabled})
                return False

            handlers = self._optimization_handlers()
            states = self._optimization_state_readers()

            handler = handlers.get(normalized_key)
            state_reader = states.get(normalized_key)
            if handler is None or state_reader is None:
                decky.logger.error(f"Unknown optimization: {key}")
                self._debug_failure("optimization", "set_enabled", "Unknown optimization", {"key": key, "normalized_key": normalized_key, "enabled": enabled})
                return False

            before = state_reader()
            if not before.get("available", True):
                decky.logger.warning(f"Optimization unavailable: {key}")
                self._debug_failure("optimization", "set_enabled", "Optimization unavailable", {"key": key, "normalized_key": normalized_key, "enabled": enabled, "before": before})
                return False

            handler(enabled)
            state = state_reader()
            success = state.get("enabled", False) if enabled else not state.get("enabled", False)
            if success:
                self._debug_success("optimization", "set_enabled", "Optimization updated", {"key": key, "normalized_key": normalized_key, "enabled": enabled, "before": before, "after": state})
            else:
                self._debug_failure("optimization", "set_enabled", "Optimization state did not change as requested", {"key": key, "normalized_key": normalized_key, "enabled": enabled, "before": before, "after": state})
            if enabled:
                return success
            return success
        except Exception as e:
            decky.logger.error(f"Failed to toggle optimization {key}: {e}")
            self._debug_failure("optimization", "set_enabled", f"Failed to toggle optimization: {e}", {"key": key, "normalized_key": str(key or '').strip().lower(), "enabled": enabled})
            return False

    async def enable_available_optimizations(self) -> dict:
        result = {
            "success": False,
            "enabled": [],
            "already_enabled": [],
            "skipped": [],
            "failed": [],
        }

        try:
            support = self._get_current_platform_support()
            if not support.get("supported", False):
                result["skipped"].append({
                    "key": "platform_guard",
                    "name": "Platform Guard",
                    "reason": support.get("reason", "Platform is not supported"),
                })
                return result

            handlers = self._optimization_handlers()
            states = (await self.get_optimization_states()).get("states", [])

            for state in states:
                key = state.get("key", "")
                name = state.get("name", key)

                if key not in handlers:
                    continue

                if not state.get("available", False):
                    result["skipped"].append({
                        "key": key,
                        "name": name,
                        "reason": state.get("details") or state.get("status", "unavailable"),
                    })
                    continue

                if state.get("enabled", False):
                    result["already_enabled"].append({"key": key, "name": name})
                    continue

                success = await self.set_optimization_enabled(key, True)
                if success:
                    result["enabled"].append({"key": key, "name": name})
                else:
                    result["failed"].append({"key": key, "name": name})

            result["success"] = len(result["failed"]) == 0
            return result
        except Exception as e:
            decky.logger.error(f"Failed to enable available optimizations: {e}")
            result["failed"].append({"key": "bulk_enable", "name": "Enable Available", "reason": str(e)})
            return result

    def _set_lavd_enabled(self, enabled: bool):
        if enabled:
            state = self._read_optimization_state()
            if "lavd_previous_content" not in state:
                previous_content = None
                if self._host_file_exists(SCX_DEFAULT_PATH) and not self._file_contains_all(
                    SCX_DEFAULT_PATH,
                    ['SCX_SCHEDULER="scx_lavd"', 'SCX_FLAGS="--performance"'],
                ):
                    try:
                        previous_content = self._read_text_file(SCX_DEFAULT_PATH, "")
                    except Exception:
                        previous_content = None
                state["lavd_previous_content"] = previous_content
                self._write_optimization_state(state)
            self._write_managed_file(SCX_DEFAULT_PATH, SCX_DEFAULT_CONTENT)
            self._refresh_atomic_manifest()
            if self._command_exists("steamosctl"):
                self._run_optional_command(["steamosctl", "set-cpu-scheduler", "lavd"])
            self._systemctl("enable", "--now", "scx.service")
        else:
            self._systemctl("disable", "--now", "scx.service")
            previous_content = self._pop_optimization_state_value("lavd_previous_content")
            if isinstance(previous_content, str):
                self._write_managed_file(SCX_DEFAULT_PATH, previous_content)
            else:
                removed_files = []
                skipped_files = []
                errors = []
                self._remove_managed_file(
                    SCX_DEFAULT_PATH,
                    removed_files,
                    skipped_files,
                    errors,
                    ['SCX_SCHEDULER="scx_lavd"', 'SCX_FLAGS="--performance"'],
                )
                for error in errors:
                    decky.logger.warning(f"Failed to clean LAVD file: {error}")
            self._refresh_atomic_manifest()

    def _set_swap_protect_enabled(self, enabled: bool):
        if enabled:
            state = self._read_optimization_state()
            state.setdefault(
                "swap_protect_previous",
                {key: self._read_sysctl(key) for key in MEMORY_SYSCTL_VALUES},
            )
            self._write_optimization_state(state)
            self._write_managed_file(MEMORY_SYSCTL_PATH, MEMORY_SYSCTL_CONTENT)
            self._refresh_atomic_manifest()
            self._run_optional_command(["sysctl", "--system"], use_sudo=True)
        else:
            self._remove_file(MEMORY_SYSCTL_PATH)
            self._refresh_atomic_manifest()
            previous = self._pop_optimization_state_value("swap_protect_previous")
            if isinstance(previous, dict):
                for key, value in previous.items():
                    if value:
                        self._write_sysctl(key, str(value))
            else:
                self._run_optional_command(["sysctl", "--system"], use_sudo=True)

    def _set_thp_madvise_enabled(self, enabled: bool):
        if enabled:
            state = self._read_optimization_state()
            state.setdefault("thp_previous_mode", self._read_thp_mode())
            self._write_optimization_state(state)
            self._write_managed_file(THP_TMPFILES_PATH, THP_TMPFILES_CONTENT)
            self._refresh_atomic_manifest()
            self._run_optional_command(["systemd-tmpfiles", "--create", THP_TMPFILES_PATH], use_sudo=True)
        else:
            self._remove_file(THP_TMPFILES_PATH)
            self._refresh_atomic_manifest()
            previous_mode = self._pop_optimization_state_value("thp_previous_mode")
            if isinstance(previous_mode, str) and previous_mode:
                self._write_thp_mode(previous_mode)
            else:
                self._run_optional_command(["systemd-tmpfiles", "--create"], use_sudo=True)

    def _set_npu_blacklist_enabled(self, enabled: bool):
        if enabled and not (self._is_amd_platform() and self._amd_npu_present()):
            decky.logger.warning("NPU blacklist requires a detected AMD NPU")
            return

        if enabled:
            self._write_managed_file(NPU_BLACKLIST_PATH, NPU_BLACKLIST_CONTENT)
        else:
            self._remove_file(NPU_BLACKLIST_PATH)
        self._refresh_atomic_manifest()

    def _set_usb_wake_enabled(self, enabled: bool):
        if enabled and not self._usb_wake_control_available():
            decky.logger.warning("USB wake guard requires ACPI wake controls and systemctl")
            return

        service_name = self._usb_wake_service_name()
        if enabled:
            target_devices = self._get_usb_wake_candidate_devices()
            if not target_devices:
                decky.logger.warning("USB wake guard found no ACPI USB wake devices to manage")
                return

            state = self._read_optimization_state()
            state.setdefault("usb_wake_enabled_devices", self._read_acpi_wake_enabled_devices())
            self._write_optimization_state(state)
            self._write_managed_file(
                USB_WAKE_CONFIG_PATH,
                self._usb_wake_config_content(target_devices),
            )
            self._write_managed_file(
                USB_WAKE_SCRIPT_PATH,
                self._usb_wake_script_content(),
                mode=0o755,
            )
            self._write_managed_file(USB_WAKE_SERVICE_PATH, self._usb_wake_service_content())
            self._refresh_atomic_manifest()
            self._systemctl("daemon-reload")
            self._systemctl("enable", "--now", service_name)
        else:
            self._systemctl("disable", "--now", service_name)
            self._remove_file(USB_WAKE_SERVICE_PATH)
            self._remove_file(USB_WAKE_SCRIPT_PATH)
            self._remove_file(USB_WAKE_CONFIG_PATH)
            self._refresh_atomic_manifest()
            self._systemctl("daemon-reload")
            previous_devices = self._pop_optimization_state_value("usb_wake_enabled_devices")
            if isinstance(previous_devices, list):
                self._set_acpi_wake_devices([str(device) for device in previous_devices])

    def _set_kernel_param_enabled(self, param: str, enabled: bool):
        if enabled and not self._is_amd_platform():
            decky.logger.warning("Kernel parameter optimization requires an AMD platform")
            return

        if enabled:
            self._remember_kernel_param_state(param, self._grub_param_configured(param))
            self._update_grub_param(param, True)
            return

        was_configured = self._forget_kernel_param_state(param)
        if was_configured:
            self._refresh_atomic_manifest()
            if self._command_exists("update-grub"):
                self._run_optional_command(["update-grub"], use_sudo=True)
            return

        self._update_grub_param(param, False)

    async def get_performance_profiles(self) -> dict:
        return await self._get_performance_service().get_profiles()

    async def get_performance_modes(self) -> dict:
        return await self._get_performance_service().get_modes()

    async def set_performance_profile(self, profile_id: str) -> bool:
        return await self._get_performance_service().set_profile(profile_id)

    async def get_display_sync_state(self) -> dict:
        return await self._get_display_service().get_sync_state()

    async def set_display_sync_setting(self, key: str, enabled: bool) -> bool:
        return await self._get_display_service().set_sync_setting(key, enabled)

    async def get_fps_limit_state(self) -> dict:
        return await self._get_display_service().get_fps_limit_state()

    async def set_fps_limit(self, value: int) -> bool:
        return await self._get_display_service().set_fps_limit(value)

    async def get_charge_limit_state(self) -> dict:
        support = self._get_current_platform_support()
        if not support.get("supported", False):
            return self._unsupported_platform_state(
                {
                    "available": False,
                    "enabled": False,
                    "limit": STEAMOS_CHARGE_FULL_PERCENT,
                },
                support,
            )

        return self._get_steamos_manager().get_charge_limit_state()

    async def set_charge_limit_enabled(self, enabled: bool) -> bool:
        try:
            self._debug_attempt("power", "set_charge_limit", "Changing battery charge limit", {"enabled": enabled})
            ok, _support = self._guard_supported_action("power", "set_charge_limit", {"enabled": enabled})
            if not ok:
                return False

            success, error = self._get_steamos_manager().set_charge_limit_enabled(enabled)
            if not success:
                decky.logger.warning(f"Failed to set SteamOS charge limit: {error}")
                self._debug_failure("power", "set_charge_limit", f"Failed to set SteamOS charge limit: {error}", {"enabled": enabled})
                return False

            decky.logger.info(
                f"SteamOS charge limit {'enabled' if enabled else 'disabled'}"
            )
            self._debug_success("power", "set_charge_limit", "Battery charge limit updated", {"enabled": enabled})
            return True
        except Exception as e:
            decky.logger.error(f"Failed to set SteamOS charge limit: {e}")
            self._debug_failure("power", "set_charge_limit", f"Failed to set SteamOS charge limit: {e}", {"enabled": enabled})
            return False

    async def get_smt_state(self) -> dict:
        support = self._get_current_platform_support()
        if not support.get("supported", False):
            return self._unsupported_platform_state(
                {
                    "available": False,
                    "enabled": False,
                },
                support,
            )

        steamos_state = self._get_steamos_manager().get_smt_state()
        if steamos_state.get("available", False):
            return steamos_state

        if not os.path.exists(SMT_CONTROL_PATH):
            return steamos_state

        try:
            with open(SMT_CONTROL_PATH, "r") as f:
                smt_state = f.read().strip()
            return {
                "available": True,
                "enabled": smt_state == "on",
                "status": "available",
                "details": "Controls SMT through the kernel SMT interface",
            }
        except Exception as e:
            return {
                "available": False,
                "enabled": False,
                "status": str(e),
                "details": "SMT control unavailable",
            }

    async def set_smt_enabled(self, enabled: bool) -> bool:
        try:
            self._debug_attempt("cpu", "set_smt", "Changing SMT state", {"enabled": enabled})
            ok, _support = self._guard_supported_action("cpu", "set_smt", {"enabled": enabled})
            if not ok:
                return False

            steamos_state = self._get_steamos_manager().get_smt_state()
            if steamos_state.get("available", False):
                success, error = self._get_steamos_manager().set_smt_enabled(enabled)
                if not success:
                    decky.logger.warning(f"Failed to set SteamOS SMT: {error}")
                    self._debug_failure("cpu", "set_smt", f"Failed to set SteamOS SMT: {error}", {"enabled": enabled})
                    return False
            elif os.path.exists(SMT_CONTROL_PATH):
                success, error = self._write_file(
                    SMT_CONTROL_PATH,
                    "on" if enabled else "off",
                    use_sudo=True,
                )
                if not success:
                    decky.logger.warning(f"Failed to set kernel SMT state: {error}")
                    self._debug_failure("cpu", "set_smt", f"Failed to set kernel SMT state: {error}", {"enabled": enabled})
                    return False
            else:
                decky.logger.warning("SMT control unavailable")
                self._debug_failure("cpu", "set_smt", "SMT control unavailable", {"enabled": enabled})
                return False

            decky.logger.info(f"SMT {'enabled' if enabled else 'disabled'}")
            self._debug_success("cpu", "set_smt", "SMT updated", {"enabled": enabled})
            return True
        except PermissionError:
            decky.logger.error("Permission denied setting SMT - requires root")
            self._debug_failure("cpu", "set_smt", "Permission denied setting SMT", {"enabled": enabled})
            return False
        except Exception as e:
            decky.logger.error(f"Failed to set SMT: {e}")
            self._debug_failure("cpu", "set_smt", f"Failed to set SMT: {e}", {"enabled": enabled})
            return False

    async def get_current_tdp(self) -> dict:
        result = {
            "tdp": 0,
            "gpu_clock": 0,
            "cpu_temp": 0,
            "gpu_temp": 0
        }
        
        try:
            # Try to read from hwmon
            hwmon_base = "/sys/class/hwmon"
            if os.path.exists(hwmon_base):
                for hwmon in os.listdir(hwmon_base):
                    hwmon_path = os.path.join(hwmon_base, hwmon)
                    name_path = os.path.join(hwmon_path, "name")
                    
                    if os.path.exists(name_path):
                        with open(name_path, 'r') as f:
                            name = f.read().strip()
                        
                        # AMD CPU/APU temps
                        if name in ["k10temp", "zenpower"]:
                            temp_path = os.path.join(hwmon_path, "temp1_input")
                            if os.path.exists(temp_path):
                                with open(temp_path, 'r') as f:
                                    result["cpu_temp"] = int(f.read().strip()) / 1000
                        
                        # AMD GPU temps
                        if name == "amdgpu":
                            for power_file in ("power1_average", "power1_input"):
                                power_path = os.path.join(hwmon_path, power_file)
                                if os.path.exists(power_path):
                                    with open(power_path, 'r') as f:
                                        result["tdp"] = round(int(f.read().strip()) / 1000000, 1)
                                    break

                            temp_path = os.path.join(hwmon_path, "temp1_input")
                            if os.path.exists(temp_path):
                                with open(temp_path, 'r') as f:
                                    result["gpu_temp"] = int(f.read().strip()) / 1000
                            
                            # GPU clock
                            freq_path = os.path.join(hwmon_path, "freq1_input")
                            if os.path.exists(freq_path):
                                with open(freq_path, 'r') as f:
                                    result["gpu_clock"] = int(f.read().strip()) / 1000000  # MHz
        
        except Exception as e:
            decky.logger.error(f"Failed to get TDP info: {e}")
        
        return result

    async def get_cpu_settings(self) -> dict:
        """Get current SMT and CPU boost settings"""
        support = self._get_current_platform_support()
        if not support.get("supported", False):
            return self._unsupported_platform_state(
                {
                    "smt_enabled": False,
                    "smt_available": False,
                    "boost_enabled": False,
                    "boost_available": False,
                },
                support,
            )

        smt = await self.get_smt_state()
        result = {
            "smt_enabled": smt.get("enabled", False),
            "smt_available": smt.get("available", False),
            "smt_status": smt.get("status", ""),
            "smt_details": smt.get("details", ""),
            "boost_enabled": False,
            "boost_available": False,
        }

        try:
            boost_state = self._get_steamos_manager().get_cpu_boost_state()
            if boost_state.get("available", False):
                result["boost_available"] = True
                result["boost_enabled"] = boost_state.get("enabled", False)
                result["boost_status"] = boost_state.get("status", "")
                result["boost_details"] = boost_state.get("details", "")
            elif os.path.exists(CPU_BOOST_PATH):
                result["boost_available"] = True
                with open(CPU_BOOST_PATH, 'r') as f:
                    boost_value = f.read().strip()
                result["boost_enabled"] = boost_value == "1"
        except Exception as e:
            decky.logger.error(f"Failed to read CPU settings: {e}")

        return result

    async def set_cpu_boost_enabled(self, enabled: bool) -> bool:
        """Enable or disable CPU boost"""
        try:
            self._debug_attempt("cpu", "set_boost", "Changing CPU boost state", {"enabled": enabled})
            ok, _support = self._guard_supported_action("cpu", "set_boost", {"enabled": enabled})
            if not ok:
                return False

            native_state = self._get_steamos_manager().get_cpu_boost_state()
            if native_state.get("available", False):
                success, error = self._get_steamos_manager().set_cpu_boost_enabled(enabled)
                if not success:
                    decky.logger.warning(f"Failed to set SteamOS CPU boost: {error}")
                    self._debug_failure("cpu", "set_boost", f"Failed to set SteamOS CPU boost: {error}", {"enabled": enabled})
                    return False
            else:
                if not os.path.exists(CPU_BOOST_PATH):
                    decky.logger.warning("CPU boost control not available")
                    self._debug_failure("cpu", "set_boost", "CPU boost control not available", {"enabled": enabled})
                    return False

                value = "1" if enabled else "0"
                success, error = self._write_file(CPU_BOOST_PATH, value, use_sudo=True)
                if not success:
                    decky.logger.warning(f"Failed to set CPU boost: {error}")
                    self._debug_failure("cpu", "set_boost", f"Failed to set CPU boost: {error}", {"enabled": enabled})
                    return False

            decky.logger.info(f"CPU boost {'enabled' if enabled else 'disabled'}")
            self._debug_success("cpu", "set_boost", "CPU boost updated", {"enabled": enabled, "native": native_state.get("available", False)})
            return True
            
        except PermissionError:
            decky.logger.error("Permission denied setting CPU boost - requires root")
            self._debug_failure("cpu", "set_boost", "Permission denied setting CPU boost", {"enabled": enabled})
            return False
        except Exception as e:
            decky.logger.error(f"Failed to set CPU boost: {e}")
            self._debug_failure("cpu", "set_boost", f"Failed to set CPU boost: {e}", {"enabled": enabled})
            return False

    def _get_runtime_state(self) -> dict:
        runtime_state = self.runtime.diagnostics()
        steamos_bus = "none"
        if self.steamos_manager is not None:
            steamos_bus = self.steamos_manager.get_active_bus()
        runtime_state["steamos_manager_bus"] = steamos_bus
        return runtime_state

    async def get_dashboard_state(self) -> dict:
        return await self._get_state_aggregator().get_dashboard_state()

    async def get_information_state(self) -> dict:
        return await self._get_state_aggregator().get_information_state()
