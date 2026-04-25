"""
Xbox Companion - Decky Loader Plugin Backend
SteamOS handheld control and SteamOS-native system management

Licensed under MIT
"""

import os
import json
import math
import subprocess
import shlex
import glob
import shutil
import importlib

import decky

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

STEAMOS_MIN_VERSION = (3, 8)
ASUS_VENDOR_NAMES = {"ASUS", "ASUSTEK", "ASUSTEK COMPUTER INC."}
LENOVO_VENDOR_NAMES = {"LENOVO"}
STEAM_DECK_VENDOR_NAMES = {"VALVE"}

PLUGIN_NAME = "Xbox Companion"

STEAMOS_MANAGER_SERVICE = "com.steampowered.SteamOSManager1"
STEAMOS_MANAGER_OBJECT = "/com/steampowered/SteamOSManager1"
STEAMOS_PERFORMANCE_INTERFACE = "com.steampowered.SteamOSManager1.PerformanceProfile1"
STEAMOS_CHARGE_LIMIT_PERCENT = 80
STEAMOS_CHARGE_FULL_PERCENT = 100
STEAMOS_CHARGE_LIMIT_INTERFACES = [
    "com.steampowered.SteamOSManager1",
    "com.steampowered.SteamOSManager1.BatteryChargeLimit1",
    "com.steampowered.SteamOSManager1.Battery1",
    "com.steampowered.SteamOSManager1.PowerManagement1",
    "com.steampowered.SteamOSManager1.Power1",
]
STEAMOS_CHARGE_LIMIT_PROPERTIES = [
    "ChargeLimit",
    "BatteryChargeLimit",
    "ChargeControlEndThreshold",
    "MaxChargeLevel",
    "ChargeLimitPercent",
    "ChargeLimitEnabled",
]
STEAMOS_SMT_INTERFACES = [
    "com.steampowered.SteamOSManager1",
    "com.steampowered.SteamOSManager1.PerformanceProfile1",
    "com.steampowered.SteamOSManager1.PowerManagement1",
    "com.steampowered.SteamOSManager1.Cpu1",
]
STEAMOS_SMT_PROPERTIES = [
    "SMT",
    "Smt",
    "SmtEnabled",
    "SMTEnabled",
    "CpuSmtEnabled",
]

GAMESCOPE_VRR_CAPABLE_ATOM = "GAMESCOPE_VRR_CAPABLE"
GAMESCOPE_VRR_ENABLED_ATOM = "GAMESCOPE_VRR_ENABLED"
GAMESCOPE_VRR_FEEDBACK_ATOM = "GAMESCOPE_VRR_FEEDBACK"
GAMESCOPE_ALLOW_TEARING_ATOM = "GAMESCOPE_ALLOW_TEARING"

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
DEFAULT_COMMAND_TIMEOUT = 5
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

ATOMIC_UPDATE_DIR = "/etc/atomic-update.conf.d"

SCX_DEFAULT_PATH = "/etc/default/scx"
MEMORY_SYSCTL_PATH = "/etc/sysctl.d/99-xbox-companion-memory-tuning.conf"
THP_TMPFILES_PATH = "/etc/tmpfiles.d/xbox-companion-thp.conf"
NPU_BLACKLIST_PATH = "/etc/modprobe.d/blacklist-xbox-companion-npu.conf"
USB_WAKE_SERVICE_PATH = "/etc/systemd/system/xbox-companion-disable-usb-wake.service"
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

USB_WAKE_SERVICE_CONTENT = """[Unit]
Description=Xbox Companion - Block USB Wake
After=network.target

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'awk "$NF == \\"enabled\\" && ($1 ~ /^XHC/ || $1 ~ /^USB/) { print $1 }" /proc/acpi/wakeup | while read -r device; do echo "$device" > /proc/acpi/wakeup; done'

[Install]
WantedBy=multi-user.target
"""

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

class SteamOsManagerClient:
    """Small DBus client for SteamOS Manager via busctl."""

    def __init__(self, logger):
        self.logger = logger

    def _run_busctl(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["busctl", "--system", *args],
            capture_output=True,
            text=True,
            timeout=5,
            env=sanitized_system_env(),
        )

    def _get_property(
        self,
        prop: str,
        interface: str = STEAMOS_PERFORMANCE_INTERFACE,
    ) -> tuple[bool, str, str]:
        try:
            result = self._run_busctl([
                "get-property",
                STEAMOS_MANAGER_SERVICE,
                STEAMOS_MANAGER_OBJECT,
                interface,
                prop
            ])
        except FileNotFoundError:
            return False, "", "busctl is not installed"
        except subprocess.TimeoutExpired:
            return False, "", "SteamOS Manager DBus request timed out"
        except Exception as e:
            return False, "", str(e)

        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip() or "DBus property read failed"
            return False, "", error

        return True, result.stdout.strip(), ""

    def _set_property(self, interface: str, prop: str, signature: str, value: str) -> tuple[bool, str]:
        try:
            result = self._run_busctl([
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
            return False, "SteamOS Manager DBus request timed out"
        except Exception as e:
            return False, str(e)

        if result.returncode != 0:
            return False, result.stderr.strip() or result.stdout.strip() or "DBus property write failed"

        return True, ""

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
        available_ok, available_output, available_error = self._get_property(
            "AvailablePerformanceProfiles"
        )
        if not available_ok:
            return {
                "available": False,
                "available_native": [],
                "current": "",
                "suggested_default": "",
                "status": f"SteamOS native profiles unavailable: {available_error}"
            }

        available_native = self._parse_busctl_string_array(available_output)

        current_ok, current_output, current_error = self._get_property("PerformanceProfile")
        current = self._parse_busctl_string(current_output) if current_ok else ""

        suggested_ok, suggested_output, _ = self._get_property(
            "SuggestedDefaultPerformanceProfile"
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
            return self._set_property(
                STEAMOS_PERFORMANCE_INTERFACE,
                "PerformanceProfile",
                "s",
                profile_id,
            )
        except Exception as e:
            return False, str(e)

    def _get_charge_limit_property(self) -> tuple[bool, str, str, str, str]:
        last_error = "SteamOS Manager charge limit API unavailable"
        for interface in STEAMOS_CHARGE_LIMIT_INTERFACES:
            for prop in STEAMOS_CHARGE_LIMIT_PROPERTIES:
                ok, output, error = self._get_property(prop, interface)
                if ok:
                    signature = self._busctl_signature(output)
                    if signature in ("b", "y", "n", "q", "i", "u", "x", "t"):
                        return True, interface, prop, signature, output
                elif error:
                    last_error = error
        return False, "", "", "", last_error

    def get_charge_limit_state(self) -> dict:
        ok, _interface, _prop, signature, output = self._get_charge_limit_property()
        if not ok:
            return {
                "available": False,
                "enabled": False,
                "limit": STEAMOS_CHARGE_FULL_PERCENT,
                "status": output,
                "details": "SteamOS Manager charge limit control unavailable",
            }

        if signature == "b":
            enabled = self._parse_busctl_bool(output)
            limit = STEAMOS_CHARGE_LIMIT_PERCENT if enabled else STEAMOS_CHARGE_FULL_PERCENT
        else:
            limit = self._parse_busctl_int(output)
            enabled = 0 < limit <= STEAMOS_CHARGE_LIMIT_PERCENT

        return {
            "available": True,
            "enabled": enabled,
            "limit": limit or STEAMOS_CHARGE_FULL_PERCENT,
            "status": "available",
            "details": f"Limits battery charging to {STEAMOS_CHARGE_LIMIT_PERCENT}% through SteamOS Manager",
        }

    def set_charge_limit_enabled(self, enabled: bool) -> tuple[bool, str]:
        ok, interface, prop, signature, _output = self._get_charge_limit_property()
        if not ok:
            return False, "SteamOS Manager charge limit control unavailable"

        if signature == "b":
            return self._set_property(interface, prop, signature, "true" if enabled else "false")

        value = STEAMOS_CHARGE_LIMIT_PERCENT if enabled else STEAMOS_CHARGE_FULL_PERCENT
        return self._set_property(interface, prop, signature, str(value))

    def _get_smt_property(self) -> tuple[bool, str, str, str, str]:
        last_error = "SteamOS Manager SMT control unavailable"
        for interface in STEAMOS_SMT_INTERFACES:
            for prop in STEAMOS_SMT_PROPERTIES:
                ok, output, error = self._get_property(prop, interface)
                if ok:
                    signature = self._busctl_signature(output)
                    if signature in ("b", "y", "n", "q", "i", "u", "x", "t"):
                        return True, interface, prop, signature, output
                elif error:
                    last_error = error
        return False, "", "", "", last_error

    def get_smt_state(self) -> dict:
        ok, _interface, _prop, signature, output = self._get_smt_property()
        if not ok:
            return {
                "available": False,
                "enabled": False,
                "status": output,
                "details": "SteamOS Manager SMT control unavailable",
            }

        enabled = (
            self._parse_busctl_bool(output)
            if signature == "b"
            else self._parse_busctl_int(output) > 0
        )
        return {
            "available": True,
            "enabled": enabled,
            "status": "available",
            "details": "Controls SMT through SteamOS Manager",
        }

    def set_smt_enabled(self, enabled: bool) -> tuple[bool, str]:
        ok, interface, prop, signature, _output = self._get_smt_property()
        if not ok:
            return False, "SteamOS Manager SMT control unavailable"

        if signature == "b":
            return self._set_property(interface, prop, signature, "true" if enabled else "false")

        return self._set_property(interface, prop, signature, "1" if enabled else "0")


class GamescopeSettingsClient:
    """Small X11 root-property client for SteamOS gamescope settings."""

    def __init__(self, logger, display: str | None = None):
        self.logger = logger
        self.display = display or os.environ.get("DISPLAY") or ":0"
        self.display_candidates = self._build_display_candidates(display)

    def _build_display_candidates(self, preferred: str | None) -> list[str]:
        candidates = []
        for candidate in (preferred, os.environ.get("DISPLAY"), ":0", ":1"):
            if candidate and candidate not in candidates:
                candidates.append(candidate)
        return candidates or [":0"]

    def _xprop_env(self, display: str) -> dict:
        return sanitized_system_env({"DISPLAY": display})

    def _run_xprop(self, args: list[str], display: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["xprop", "-root", *args],
            capture_output=True,
            text=True,
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

        vrr_capable = vrr_capable_ok and bool(vrr_capable_value)
        vrr_enabled = vrr_enabled_ok and bool(vrr_enabled_value)
        vrr_active = vrr_feedback_ok and bool(vrr_feedback_value)

        if not vrr_capable_ok:
            vrr_status = f"VRR state unavailable: {vrr_capable_error}"
        elif not vrr_capable:
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
                "available": vrr_capable_ok and vrr_capable,
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
        self.steamos_manager: SteamOsManagerClient | None = None
        self.gamescope_settings: GamescopeSettingsClient | None = None

    async def _main(self):
        """Main entry point for the plugin"""
        self.settings_path = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json")
        self.steamos_manager = SteamOsManagerClient(decky.logger)
        self.gamescope_settings = GamescopeSettingsClient(decky.logger)
        await self.load_settings()
        decky.logger.info(f"{PLUGIN_NAME} initialized")

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
        if device.get("product_id") not in config["pids"]:
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

    def _get_rgb_backend(self) -> dict:
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

    def _get_battery_path(self) -> str:
        direct_paths = [BATTERY_PATH]
        for path in direct_paths:
            if os.path.exists(path):
                return path

        candidates = []
        for pattern in BATTERY_PATH_GLOBS:
            candidates.extend(sorted(glob.glob(pattern)))

        for path in candidates:
            type_path = os.path.join(path, "type")
            if self._read_file(type_path, "").lower() == "battery":
                return path

        return candidates[0] if candidates else ""

    def _format_duration_hours(self, hours: float) -> str:
        if not math.isfinite(hours) or hours <= 0:
            return "Unknown"

        total_minutes = max(1, int(round(hours * 60)))
        whole_hours, minutes = divmod(total_minutes, 60)
        if whole_hours == 0:
            return f"{minutes}m"
        if minutes == 0:
            return f"{whole_hours}h"
        return f"{whole_hours}h {minutes}m"

    def _estimate_battery_times(self, battery: dict) -> tuple[str, str]:
        voltage = float(battery.get("voltage", 0) or 0)
        current = abs(float(battery.get("current", 0) or 0))
        capacity = float(battery.get("capacity", 0) or 0)
        full_capacity = float(
            battery.get("full_capacity", 0)
            or battery.get("design_capacity", 0)
            or 0
        )

        if voltage <= 0 or current <= 0 or capacity <= 0 or full_capacity <= 0:
            return "Unknown", "Unknown"

        power = voltage * current
        if power <= 0:
            return "Unknown", "Unknown"

        stored_energy = full_capacity * min(capacity, 100) / 100
        target_percent = min(
            max(float(battery.get("charge_limit", STEAMOS_CHARGE_FULL_PERCENT) or 0), 0),
            100,
        )
        target_energy = full_capacity * target_percent / 100
        status = str(battery.get("status", "") or "").strip().lower()

        time_to_empty = "Unknown"
        time_to_full = "Unknown"

        if status == "discharging" and stored_energy > 0:
            time_to_empty = self._format_duration_hours(stored_energy / power)
        elif status == "charging" and target_energy > stored_energy:
            time_to_full = self._format_duration_hours((target_energy - stored_energy) / power)

        return time_to_empty, time_to_full

    def _get_os_release_values(self) -> dict:
        os_release = "/etc/os-release"
        try:
            if not os.path.exists(os_release):
                return {}

            values = {}
            with open(os_release, 'r') as f:
                for line in f:
                    if "=" not in line:
                        continue
                    key, value = line.strip().split("=", 1)
                    values[key] = value.strip('"')

            return values
        except Exception as e:
            decky.logger.error(f"Failed to read OS release data: {e}")
            return {}

    def _get_steamos_version(self, os_release_values: dict | None = None) -> str:
        values = os_release_values if os_release_values is not None else self._get_os_release_values()
        return (
            values.get("PRETTY_NAME")
            or values.get("VERSION")
            or values.get("NAME")
            or "Unknown"
        )

    def _is_steam_deck_device(
        self,
        board_name: str,
        product_name: str,
        sys_vendor: str,
        product_family: str,
    ) -> bool:
        normalized_vendor = sys_vendor.strip().upper()
        identifiers = " ".join(
            value.strip().upper()
            for value in (board_name, product_name, product_family)
            if value and value != "Unknown"
        )
        return normalized_vendor in STEAM_DECK_VENDOR_NAMES or any(
            keyword in identifiers
            for keyword in ("STEAM DECK", "JUPITER", "GALILEO")
        )

    def _is_supported_handheld_vendor_device(
        self,
        board_name: str,
        product_name: str,
        sys_vendor: str,
        product_family: str,
    ) -> bool:
        normalized_vendor = sys_vendor.strip().upper()
        identifiers = " ".join(
            value.strip().upper()
            for value in (board_name, product_name, product_family)
            if value and value != "Unknown"
        )

        if normalized_vendor in ASUS_VENDOR_NAMES:
            return any(keyword in identifiers for keyword in ("ALLY", "ROG", "XBOX", "RC7"))

        if normalized_vendor in LENOVO_VENDOR_NAMES:
            return "LEGION" in identifiers

        return False

    def _parse_version_tuple(self, raw_version: str) -> tuple[int, int] | None:
        parts = []
        current = ""
        for char in raw_version:
            if char.isdigit():
                current += char
            elif current:
                parts.append(int(current))
                current = ""
                if len(parts) == 2:
                    break
        if current and len(parts) < 2:
            parts.append(int(current))
        if not parts:
            return None
        if len(parts) == 1:
            parts.append(0)
        return parts[0], parts[1]

    def _steamos_version_is_supported(self, values: dict) -> bool:
        for key in ("VERSION_ID", "VERSION", "PRETTY_NAME"):
            parsed = self._parse_version_tuple(values.get(key, ""))
            if parsed is not None:
                return parsed >= STEAMOS_MIN_VERSION
        return False

    def _get_platform_support(
        self,
        board_name: str,
        product_name: str,
        sys_vendor: str,
        product_family: str,
        os_release_values: dict | None = None,
    ) -> dict:
        values = os_release_values if os_release_values is not None else self._get_os_release_values()
        os_id = values.get("ID", "").strip().lower()
        os_name = " ".join(
            values.get(key, "")
            for key in ("NAME", "PRETTY_NAME", "ID", "ID_LIKE")
        ).lower()

        if self._is_steam_deck_device(board_name, product_name, sys_vendor, product_family):
            return {
                "supported": False,
                "support_level": "blocked",
                "reason": "Steam Deck is blocked to avoid interfering with Valve hardware defaults.",
            }

        if os_id != "steamos" or any(name in os_name for name in ("bazzite", "chimeraos", "chimera")):
            return {
                "supported": False,
                "support_level": "blocked",
                "reason": "Xbox Companion is only enabled on SteamOS 3.8 or newer.",
            }

        if not self._steamos_version_is_supported(values):
            return {
                "supported": False,
                "support_level": "blocked",
                "reason": "Xbox Companion requires SteamOS 3.8 or newer.",
            }

        if not self._is_supported_handheld_vendor_device(
            board_name,
            product_name,
            sys_vendor,
            product_family,
        ):
            return {
                "supported": False,
                "support_level": "blocked",
                "reason": "Xbox Companion is only enabled on ASUS and Lenovo handhelds.",
            }

        return {
            "supported": True,
            "support_level": "supported",
            "reason": "Supported ASUS/Lenovo handheld on SteamOS 3.8 or newer.",
        }

    def _get_device_metadata(
        self,
        board_name: str,
        product_name: str,
        sys_vendor: str = "",
        product_family: str = "",
    ) -> dict:
        vendor = (
            sys_vendor
            if sys_vendor and sys_vendor != "Unknown"
            else "Unknown"
        )
        friendly_name = product_name if product_name and product_name != "Unknown" else "SteamOS handheld"

        return {
            "board_name": board_name,
            "product_name": product_name,
            "product_family": product_family or "Unknown",
            "sys_vendor": vendor,
            "variant": board_name or product_name or "Unknown",
            "friendly_name": friendly_name,
            "device_family": "steamos_handheld",
            "support_level": "supported",
        }

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

    async def get_device_info(self) -> dict:
        info = {
            "model": "Unknown",
            "friendly_name": "Unknown",
            "board_name": "Unknown",
            "product_name": "Unknown",
            "sys_vendor": "Unknown",
            "variant": "Unknown",
            "device_family": "unknown",
            "support_level": "unsupported",
            "steamos_version": "Unknown",
            "bios_version": "Unknown",
            "serial": "Unknown",
            "cpu": "Unknown",
            "gpu": "Unknown",
            "kernel": "Unknown",
            "memory_total": "Unknown",
            "platform_supported": False,
            "platform_support_reason": "Platform support has not been checked",
        }
        
        try:
            os_release_values = self._get_os_release_values()

            # Read DMI info
            dmi_files = {
                "model": "product_name",
                "product_name": "product_name",
                "product_family": "product_family",
                "sys_vendor": "sys_vendor",
                "board_name": "board_name",
                "bios_version": "bios_version",
                "serial": "product_serial"
            }
            
            for key, filename in dmi_files.items():
                filepath = os.path.join(DMI_PATH, filename)
                if os.path.exists(filepath):
                    with open(filepath, 'r') as f:
                        info[key] = f.read().strip()

            device_metadata = self._get_device_metadata(
                board_name=info.get("board_name", "Unknown"),
                product_name=info.get("model", "Unknown"),
                sys_vendor=info.get("sys_vendor", "Unknown"),
                product_family=info.get("product_family", "Unknown"),
            )
            platform_support = self._get_platform_support(
                board_name=info.get("board_name", "Unknown"),
                product_name=info.get("model", "Unknown"),
                sys_vendor=info.get("sys_vendor", "Unknown"),
                product_family=info.get("product_family", "Unknown"),
                os_release_values=os_release_values,
            )
            info.update(device_metadata)
            info.update(platform_support)
            info["platform_supported"] = platform_support.get("supported", False)
            info["platform_support_reason"] = platform_support.get("reason", "")
            info["steamos_version"] = self._get_steamos_version(os_release_values)
            
            # Get CPU info
            if os.path.exists("/proc/cpuinfo"):
                with open("/proc/cpuinfo", 'r') as f:
                    for line in f:
                        if line.startswith("model name"):
                            info["cpu"] = line.split(":")[1].strip()
                            break
            
            # Get kernel version
            result = subprocess.run(
                ["uname", "-r"],
                capture_output=True,
                text=True,
                timeout=DEFAULT_COMMAND_TIMEOUT,
                env=sanitized_system_env(),
            )
            if result.returncode == 0:
                info["kernel"] = result.stdout.strip()
            
            # Get memory info
            if os.path.exists("/proc/meminfo"):
                with open("/proc/meminfo", 'r') as f:
                    for line in f:
                        if line.startswith("MemTotal"):
                            mem_kb = int(line.split()[1])
                            info["memory_total"] = f"{mem_kb // 1024 // 1024} GB"
                            break
            
            # GPU info (AMD APU)
            info["gpu"] = "AMD Radeon 780M" if "Z1" in info.get("cpu", "") else "AMD Radeon Graphics"
            
        except Exception as e:
            decky.logger.error(f"Failed to get device info: {e}")
        
        return info

    async def get_battery_info(self) -> dict:
        battery = {
            "present": False,
            "status": "Unknown",
            "capacity": 0,
            "health": 100,
            "cycle_count": 0,
            "voltage": 0,
            "current": 0,
            "temperature": 0,
            "design_capacity": 0,
            "full_capacity": 0,
            "charge_limit": STEAMOS_CHARGE_FULL_PERCENT,
            "time_to_empty": "Unknown",
            "time_to_full": "Unknown"
        }
        
        try:
            battery_path = self._get_battery_path()
            if not battery_path:
                return battery
            
            battery["present"] = True
            
            # Read battery files
            battery_files = {
                "status": "status",
                "capacity": "capacity",
                "cycle_count": "cycle_count",
                "voltage_now": "voltage_now",
                "current_now": "current_now",
                "energy_full_design": "energy_full_design",
                "energy_full": "energy_full"
            }
            
            for key, filename in battery_files.items():
                filepath = os.path.join(battery_path, filename)
                if os.path.exists(filepath):
                    with open(filepath, 'r') as f:
                        value = f.read().strip()
                        if key == "status":
                            battery["status"] = value
                        elif key == "capacity":
                            battery["capacity"] = int(value)
                        elif key == "cycle_count":
                            battery["cycle_count"] = int(value)
                        elif key == "voltage_now":
                            battery["voltage"] = int(value) / 1000000  # Convert to V
                        elif key == "current_now":
                            battery["current"] = int(value) / 1000000  # Convert to A
                        elif key == "energy_full_design":
                            battery["design_capacity"] = int(value) / 1000000  # Convert to Wh
                        elif key == "energy_full":
                            battery["full_capacity"] = int(value) / 1000000  # Convert to Wh
            
            # Calculate health percentage
            if battery["design_capacity"] > 0:
                battery["health"] = round((battery["full_capacity"] / battery["design_capacity"]) * 100, 1)
            
            # Try to get temperature from ACPI
            temp_path = os.path.join(battery_path, "temp")
            if os.path.exists(temp_path):
                with open(temp_path, 'r') as f:
                    battery["temperature"] = int(f.read().strip()) / 10  # Convert to Celsius

            charge_limit_state = await self.get_charge_limit_state()
            battery["charge_limit"] = charge_limit_state.get("limit", battery["charge_limit"])
            (
                battery["time_to_empty"],
                battery["time_to_full"],
            ) = self._estimate_battery_times(battery)
            
        except Exception as e:
            decky.logger.error(f"Failed to get battery info: {e}")
        
        return battery

    def _set_led_color(self, led_path: str, color: str, enabled: bool) -> bool:
        try:
            brightness_path = os.path.join(led_path, "brightness")
            multi_intensity_path = os.path.join(led_path, "multi_intensity")
            if not os.path.exists(brightness_path) or not os.path.exists(multi_intensity_path):
                return False

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
                f.write("255")
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

    def _read_rgb_state_from_led(self, led_path: str) -> tuple[bool, str]:
        enabled = False
        color = RGB_COLOR_PRESETS[0]

        try:
            brightness_path = os.path.join(led_path, "brightness")
            if os.path.exists(brightness_path):
                with open(brightness_path, "r") as f:
                    enabled = int(f.read().strip() or "0") > 0
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

        return enabled, color

    def _legion_go_s_rgb_commands(self, color: str, enabled: bool) -> list[bytes]:
        if not enabled:
            return [bytes([0x04, 0x06, 0x00])]

        r, g, b = self._hex_to_rgb(color)
        profile = 3
        brightness = 63
        speed = 63
        return [
            bytes([0x04, 0x06, 0x01]),
            bytes([0x10, 0x02, profile]),
            bytes([0x10, profile + 2, 0x00, r, g, b, brightness, speed]),
        ]

    def _legion_go_tablet_rgb_commands(self, color: str, enabled: bool) -> list[bytes]:
        def enable_command(controller: int, value: bool) -> bytes:
            return bytes([0x05, 0x06, 0x70, 0x02, controller, 0x01 if value else 0x00, 0x01])

        if not enabled:
            return [enable_command(0x03, False), enable_command(0x04, False)]

        r, g, b = self._hex_to_rgb(color)
        profile = 3
        brightness = 63
        period = 0
        commands = []
        for controller in (0x03, 0x04):
            commands.append(bytes([0x05, 0x0C, 0x72, 0x01, controller, 0x01, r, g, b, brightness, period, profile, 0x01]))
        for controller in (0x03, 0x04):
            commands.append(bytes([0x05, 0x06, 0x73, 0x02, controller, profile, 0x01]))
        commands.extend([enable_command(0x03, True), enable_command(0x04, True)])
        return commands

    def _hex_to_rgb(self, color: str) -> tuple[int, int, int]:
        rgb = color.lstrip("#")
        return int(rgb[0:2], 16), int(rgb[2:4], 16), int(rgb[4:6], 16)

    def _legion_hid_rgb_commands(self, device: dict, color: str, enabled: bool) -> list[bytes]:
        protocol = device["config"]["protocol"]
        if protocol == "legion_go_s":
            return self._legion_go_s_rgb_commands(color, enabled)
        if protocol == "legion_go_tablet":
            return self._legion_go_tablet_rgb_commands(color, enabled)
        return []

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

    def _write_legion_hid_rgb(self, device: dict, color: str, enabled: bool) -> bool:
        commands = self._legion_hid_rgb_commands(device, color, enabled)
        if not commands:
            return False

        if device.get("backend") == "hidraw":
            try:
                with open(device["path"], "wb", buffering=0) as f:
                    for command in commands:
                        f.write(command)
                return True
            except Exception as e:
                decky.logger.warning(f"Failed to write Legion HID raw RGB command: {e}")
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
            decky.logger.warning(f"Failed to write Legion HID RGB command: {e}")
            return False

    async def get_rgb_state(self) -> dict:
        support = self._get_current_platform_support()
        if not support.get("supported", False):
            return {
                "available": False,
                "enabled": False,
                "color": RGB_COLOR_PRESETS[0],
                "presets": RGB_COLOR_PRESETS,
                "details": support.get("reason", "Platform is not supported"),
            }

        backend = self._get_rgb_backend()
        if backend["type"] == "sysfs":
            enabled, color = self._read_rgb_state_from_led(backend["path"])
        elif backend["type"] == "legion_hid":
            enabled = bool(self.settings.get("rgb_enabled", False))
            color = self.settings.get("rgb_color", RGB_COLOR_PRESETS[0])
        else:
            enabled, color = False, RGB_COLOR_PRESETS[0]

        return {
            "available": backend["type"] != "none",
            "enabled": enabled,
            "color": color,
            "presets": RGB_COLOR_PRESETS,
            "details": backend["details"],
        }

    async def set_rgb_enabled(self, enabled: bool) -> bool:
        support = self._get_current_platform_support()
        if not support.get("supported", False):
            decky.logger.warning(support.get("reason", "Platform is not supported"))
            return False

        backend = self._get_rgb_backend()
        if backend["type"] == "none":
            decky.logger.warning("RGB control not available")
            return False

        if backend["type"] == "sysfs":
            _current_enabled, current_color = self._read_rgb_state_from_led(backend["path"])
            success = self._set_led_color(backend["path"], current_color, enabled)
        else:
            current_color = self.settings.get("rgb_color", RGB_COLOR_PRESETS[0])
            success = self._write_legion_hid_rgb(backend["device"], current_color, enabled)

        if not success:
            return False

        self.settings["rgb_enabled"] = enabled
        self.settings["rgb_color"] = current_color
        self._save_settings()
        return True

    async def set_rgb_color(self, color: str) -> bool:
        support = self._get_current_platform_support()
        if not support.get("supported", False):
            decky.logger.warning(support.get("reason", "Platform is not supported"))
            return False

        backend = self._get_rgb_backend()
        if backend["type"] == "none":
            decky.logger.warning("RGB control not available")
            return False

        normalized = color.upper()
        if normalized not in RGB_COLOR_PRESETS:
            decky.logger.warning(f"Unsupported RGB color preset: {color}")
            return False

        if backend["type"] == "sysfs":
            enabled, _current_color = self._read_rgb_state_from_led(backend["path"])
            success = self._set_led_color(backend["path"], normalized, enabled)
        else:
            enabled = bool(self.settings.get("rgb_enabled", False))
            success = self._write_legion_hid_rgb(backend["device"], normalized, enabled)

        if not success:
            return False

        self.settings["rgb_color"] = normalized
        self._save_settings()
        return True

    def _command_exists(self, cmd: str) -> bool:
        return shutil.which(cmd) is not None

    def _write_managed_file(self, path: str, content: str, mode: int | None = None):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        if mode is not None:
            os.chmod(path, mode)

    def _remove_file(self, path: str):
        try:
            if os.path.exists(path):
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
        ]
        entries = [path for path, needles in checks if self._file_contains_all(path, needles)]
        kernel_params = self._managed_kernel_params()
        if kernel_params and self._file_contains_any(GRUB_DEFAULT_PATH, kernel_params):
            entries.append(GRUB_DEFAULT_PATH)
        return entries

    def _refresh_atomic_manifest(self):
        self._cleanup_legacy_managed_files()
        entries = self._atomic_managed_entries()
        if entries:
            content = "\n".join(entries) + "\n"
            self._write_managed_file(ATOMIC_MANIFEST_PATH, content)
        else:
            self._remove_file(ATOMIC_MANIFEST_PATH)
        self._cleanup_legacy_atomic_manifests()

    def _atomic_manifest_contains(self, paths: list[str]) -> bool:
        return self._file_contains_all(ATOMIC_MANIFEST_PATH, paths)

    def _migrate_atomic_manifest_if_needed(self):
        if any(os.path.exists(path) for path in LEGACY_ATOMIC_PATHS):
            self._refresh_atomic_manifest()

    def _remove_managed_file(
        self,
        path: str,
        removed_files: list[str],
        skipped_files: list[str],
        errors: list[str],
        needles: list[str] | None = None,
    ):
        try:
            if not os.path.exists(path):
                return

            if needles and not self._file_contains_all(path, needles):
                skipped_files.append(path)
                return

            os.remove(path)
            removed_files.append(path)
        except Exception as e:
            errors.append(f"{path}: {e}")

    def _run_command(self, command: list[str]) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=20,
                env=sanitized_system_env(),
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

    def _run_command_output(self, command: list[str]) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=20,
                env=sanitized_system_env(),
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

    def _run_optional_command(self, command: list[str]) -> str:
        success, error = self._run_command(command)
        if not success:
            decky.logger.warning(f"Optional command failed: {' '.join(command)}: {error}")
            return error
        return ""

    def _read_optimization_state(self) -> dict:
        try:
            if not os.path.exists(OPTIMIZATION_STATE_PATH):
                return {}
            with open(OPTIMIZATION_STATE_PATH, "r") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            decky.logger.warning(f"Failed to read optimization state: {e}")
            return {}

    def _write_optimization_state(self, state: dict):
        try:
            if not state:
                self._remove_file(OPTIMIZATION_STATE_PATH)
                return
            os.makedirs(os.path.dirname(OPTIMIZATION_STATE_PATH), exist_ok=True)
            with open(OPTIMIZATION_STATE_PATH, "w") as f:
                json.dump(state, f, indent=2, sort_keys=True)
                f.write("\n")
        except Exception as e:
            decky.logger.warning(f"Failed to write optimization state: {e}")

    def _pop_optimization_state_value(self, key: str):
        state = self._read_optimization_state()
        value = state.pop(key, None)
        self._write_optimization_state(state)
        return value

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
        return self._run_optional_command(["systemctl", *args])

    def _service_exists(self, service: str) -> bool:
        if os.path.exists(f"/etc/systemd/system/{service}") or os.path.exists(f"/usr/lib/systemd/system/{service}"):
            return True

        try:
            result = subprocess.run(
                ["systemctl", "list-unit-files", service, "--no-legend"],
                capture_output=True,
                text=True,
                timeout=5,
                env=sanitized_system_env(),
            )
            return result.returncode == 0 and service in result.stdout
        except Exception:
            return False

    def _service_enabled(self, service: str) -> bool:
        try:
            result = subprocess.run(
                ["systemctl", "is-enabled", service],
                capture_output=True,
                text=True,
                timeout=DEFAULT_COMMAND_TIMEOUT,
                env=sanitized_system_env(),
            )
            return result.returncode == 0 and result.stdout.strip() == "enabled"
        except Exception:
            return False

    def _service_active(self, service: str) -> bool:
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service],
                capture_output=True,
                text=True,
                timeout=DEFAULT_COMMAND_TIMEOUT,
                env=sanitized_system_env(),
            )
            return result.returncode == 0 and result.stdout.strip() == "active"
        except Exception:
            return False

    def _read_sysctl(self, key: str) -> str:
        result = subprocess.run(
            ["sysctl", "-n", key],
            capture_output=True,
            text=True,
            timeout=DEFAULT_COMMAND_TIMEOUT,
            env=sanitized_system_env(),
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip()

    def _write_sysctl(self, key: str, value: str):
        self._run_optional_command(["sysctl", "-w", f"{key}={value}"])

    def _file_contains_all(self, path: str, needles: list[str]) -> bool:
        try:
            if not os.path.exists(path):
                return False
            with open(path, "r") as f:
                contents = f.read()
            return all(needle in contents for needle in needles)
        except Exception:
            return False

    def _file_contains_any(self, path: str, needles: list[str]) -> bool:
        try:
            if not os.path.exists(path):
                return False
            with open(path, "r") as f:
                contents = f.read()
            return any(needle in contents for needle in needles)
        except Exception:
            return False

    def _is_amd_platform(self) -> bool:
        return "AMD" in self._read_file("/proc/cpuinfo", "").upper()

    def _amd_npu_present(self) -> bool:
        if os.path.exists("/sys/module/amdxdna"):
            return True

        for device in glob.glob("/sys/bus/pci/devices/*"):
            module_path = os.path.join(device, "driver", "module")
            try:
                if os.path.basename(os.path.realpath(module_path)) == "amdxdna":
                    return True
            except Exception:
                continue

        if self._command_exists("lspci"):
            success, output = self._run_command_output(["lspci", "-nn"])
            if success:
                normalized = output.upper()
                return "XDNA" in normalized or "NPU" in normalized or "AI ENGINE" in normalized

        return False

    def _usb_wake_control_available(self) -> bool:
        return os.path.exists(ACPI_WAKEUP_PATH) and self._command_exists("systemctl")

    def _read_cmdline(self) -> str:
        try:
            with open("/proc/cmdline", "r") as f:
                return f.read()
        except Exception:
            return ""

    def _read_acpi_wake_enabled_devices(self) -> list[str]:
        try:
            with open(ACPI_WAKEUP_PATH, "r") as f:
                devices = []
                for line in f:
                    parts = line.split()
                    if len(parts) >= 3 and parts[2] == "*enabled" and (parts[0].startswith("XHC") or parts[0].startswith("USB")):
                        devices.append(parts[0])
                return devices
        except Exception:
            return []

    def _set_acpi_wake_devices(self, devices: list[str]):
        for device in devices:
            try:
                with open(ACPI_WAKEUP_PATH, "w") as f:
                    f.write(device)
            except Exception as e:
                decky.logger.warning(f"Failed to restore ACPI wake device {device}: {e}")

    def _thp_is_madvise(self) -> bool:
        try:
            if not os.path.exists(THP_ENABLED_PATH):
                return False
            with open(THP_ENABLED_PATH, "r") as f:
                return "[madvise]" in f.read()
        except Exception:
            return False

    def _read_thp_mode(self) -> str:
        try:
            if not os.path.exists(THP_ENABLED_PATH):
                return ""
            with open(THP_ENABLED_PATH, "r") as f:
                for token in f.read().split():
                    if token.startswith("[") and token.endswith("]"):
                        return token.strip("[]")
        except Exception:
            return ""
        return ""

    def _write_thp_mode(self, mode: str):
        if not mode:
            return
        try:
            with open(THP_ENABLED_PATH, "w") as f:
                f.write(mode)
        except Exception as e:
            decky.logger.warning(f"Failed to set THP mode {mode}: {e}")

    def _kernel_param_active(self, param: str) -> bool:
        return param in self._read_cmdline()

    def _grub_param_configured(self, param: str) -> bool:
        return self._file_contains_all(GRUB_DEFAULT_PATH, [param])

    def _managed_kernel_params(self) -> list[str]:
        params = self._read_optimization_state().get("kernel_params", {})
        if not isinstance(params, dict):
            return []
        known_params = {option["param"] for option in GRUB_KERNEL_PARAM_OPTIONS.values()}
        return [param for param in params if param in known_params]

    def _kernel_param_managed(self, param: str) -> bool:
        return param in self._managed_kernel_params()

    def _remember_kernel_param_state(self, param: str, was_configured: bool):
        state = self._read_optimization_state()
        params = state.get("kernel_params", {})
        if not isinstance(params, dict):
            params = {}
        params.setdefault(param, {"was_configured": was_configured})
        state["kernel_params"] = params
        self._write_optimization_state(state)

    def _forget_kernel_param_state(self, param: str) -> bool:
        state = self._read_optimization_state()
        params = state.get("kernel_params", {})
        if not isinstance(params, dict):
            return False
        data = params.pop(param, {})
        if params:
            state["kernel_params"] = params
        else:
            state.pop("kernel_params", None)
        self._write_optimization_state(state)
        return isinstance(data, dict) and data.get("was_configured", False)

    def _update_grub_param(self, param: str, enabled: bool) -> str:
        if not os.path.exists(GRUB_DEFAULT_PATH):
            return "GRUB config not found"

        try:
            with open(GRUB_DEFAULT_PATH, "r") as f:
                contents = f.read()

            lines = []
            changed = False
            for line in contents.splitlines():
                if line.startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
                    prefix, value = line.split("=", 1)
                    raw = value.strip().strip('"').strip("'")
                    parts = [part for part in raw.split() if part != param]

                    if enabled:
                        parts.append(param)

                    new_value = " ".join(parts).strip()
                    line = f'{prefix}="{new_value}"'
                    changed = True
                lines.append(line)

            if not changed and enabled:
                lines.append(f'GRUB_CMDLINE_LINUX_DEFAULT="{param}"')

            with open(GRUB_DEFAULT_PATH, "w") as f:
                f.write("\n".join(lines) + "\n")

            self._refresh_atomic_manifest()

            if self._command_exists("update-grub"):
                return self._run_optional_command(["update-grub"])
            return "update-grub is not installed"
        except Exception as e:
            return str(e)

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
        status = "unavailable"
        if available:
            if needs_reboot:
                status = "reboot-required"
            elif enabled and active:
                status = "active"
            elif enabled:
                status = "configured"
            elif active:
                status = "active"
            else:
                status = "off"

        return {
            "key": key,
            "name": name,
            "description": description,
            "enabled": enabled,
            "active": active,
            "available": available,
            "needs_reboot": needs_reboot,
            "details": details,
            "risk_note": risk_note,
            "status": status,
        }

    def _get_lavd_state(self) -> dict:
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
            details="SteamOS scx.service" if self._service_exists("scx.service") else "scx.service unavailable",
            risk_note="Touches a system service.",
        )

    def _get_swap_protect_state(self) -> dict:
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
            details="swappiness 10, min_free_kbytes 524288, dirty_ratio 5",
            risk_note="Runtime sysctl values may remain until they are reloaded.",
        )

    def _get_thp_madvise_state(self) -> dict:
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
            details="Transparent Huge Pages mode: madvise",
            risk_note="Some games prefer different THP behavior.",
        )

    def _get_npu_blacklist_state(self) -> dict:
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
            details="Module: amdxdna",
            risk_note="Requires reboot when the module is already loaded.",
        )

    def _get_usb_wake_state(self) -> dict:
        service_configured = os.path.exists(USB_WAKE_SERVICE_PATH)
        atomic = self._atomic_manifest_contains([USB_WAKE_SERVICE_PATH])
        service_enabled = self._service_enabled("xbox-companion-disable-usb-wake.service")
        service_active = self._service_active("xbox-companion-disable-usb-wake.service")
        enabled = service_configured and atomic and service_enabled

        return self._optimization_state(
            "usb_wake",
            "USB Wake Guard",
            "Disables USB wake sources that can wake the handheld unexpectedly.",
            enabled,
            service_active,
            available=self._usb_wake_control_available(),
            details="Uses /proc/acpi/wakeup through a systemd service",
            risk_note="Touches a system service.",
        )

    def _get_kernel_param_state(self, key: str, option: dict) -> dict:
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
            available=os.path.exists(GRUB_DEFAULT_PATH) and self._is_amd_platform(),
            needs_reboot=(enabled and not active) or (not enabled and active),
            details=option["details"],
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

        states = [
            self._get_lavd_state(),
            self._get_swap_protect_state(),
            self._get_thp_madvise_state(),
            self._get_npu_blacklist_state(),
            self._get_usb_wake_state(),
        ]
        states.extend(
            self._get_kernel_param_state(key, option)
            for key, option in GRUB_KERNEL_PARAM_OPTIONS.items()
        )

        return {
            "states": states,
        }

    def _optimization_handlers(self) -> dict:
        handlers = {
            "lavd": self._set_lavd_enabled,
            "swap_protect": self._set_swap_protect_enabled,
            "thp_madvise": self._set_thp_madvise_enabled,
            "npu_blacklist": self._set_npu_blacklist_enabled,
            "usb_wake": self._set_usb_wake_enabled,
        }
        for param_key, option in GRUB_KERNEL_PARAM_OPTIONS.items():
            handlers[param_key] = lambda value, selected=option["param"]: self._set_kernel_param_enabled(selected, value)
        return handlers

    def _optimization_state_readers(self) -> dict:
        states = {
            "lavd": self._get_lavd_state,
            "swap_protect": self._get_swap_protect_state,
            "thp_madvise": self._get_thp_madvise_state,
            "npu_blacklist": self._get_npu_blacklist_state,
            "usb_wake": self._get_usb_wake_state,
        }
        for param_key, option in GRUB_KERNEL_PARAM_OPTIONS.items():
            states[param_key] = lambda selected_key=param_key, selected_option=option: self._get_kernel_param_state(
                selected_key,
                selected_option,
            )
        return states

    async def set_optimization_enabled(self, key: str, enabled: bool) -> bool:
        try:
            support = self._get_current_platform_support()
            if not support.get("supported", False):
                decky.logger.warning(support.get("reason", "Platform is not supported"))
                return False

            handlers = self._optimization_handlers()
            states = self._optimization_state_readers()

            handler = handlers.get(key)
            state_reader = states.get(key)
            if handler is None or state_reader is None:
                decky.logger.error(f"Unknown optimization: {key}")
                return False

            before = state_reader()
            if not before.get("available", True):
                decky.logger.warning(f"Optimization unavailable: {key}")
                return False

            handler(enabled)
            state = state_reader()
            if enabled:
                return state.get("enabled", False)
            return not state.get("enabled", False)
        except Exception as e:
            decky.logger.error(f"Failed to toggle optimization {key}: {e}")
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
                if os.path.exists(SCX_DEFAULT_PATH) and not self._file_contains_all(
                    SCX_DEFAULT_PATH,
                    ['SCX_SCHEDULER="scx_lavd"', 'SCX_FLAGS="--performance"'],
                ):
                    try:
                        with open(SCX_DEFAULT_PATH, "r") as f:
                            previous_content = f.read()
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
            self._run_optional_command(["sysctl", "--system"])
        else:
            self._remove_file(MEMORY_SYSCTL_PATH)
            self._refresh_atomic_manifest()
            previous = self._pop_optimization_state_value("swap_protect_previous")
            if isinstance(previous, dict):
                for key, value in previous.items():
                    if value:
                        self._write_sysctl(key, str(value))
            else:
                self._run_optional_command(["sysctl", "--system"])

    def _set_thp_madvise_enabled(self, enabled: bool):
        if enabled:
            state = self._read_optimization_state()
            state.setdefault("thp_previous_mode", self._read_thp_mode())
            self._write_optimization_state(state)
            self._write_managed_file(THP_TMPFILES_PATH, THP_TMPFILES_CONTENT)
            self._refresh_atomic_manifest()
            self._run_optional_command(["systemd-tmpfiles", "--create", THP_TMPFILES_PATH])
        else:
            self._remove_file(THP_TMPFILES_PATH)
            self._refresh_atomic_manifest()
            previous_mode = self._pop_optimization_state_value("thp_previous_mode")
            if isinstance(previous_mode, str) and previous_mode:
                self._write_thp_mode(previous_mode)
            else:
                self._run_optional_command(["systemd-tmpfiles", "--create"])

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

        service_name = "xbox-companion-disable-usb-wake.service"
        if enabled:
            state = self._read_optimization_state()
            state.setdefault("usb_wake_enabled_devices", self._read_acpi_wake_enabled_devices())
            self._write_optimization_state(state)
            self._write_managed_file(USB_WAKE_SERVICE_PATH, USB_WAKE_SERVICE_CONTENT)
            self._refresh_atomic_manifest()
            self._systemctl("daemon-reload")
            self._systemctl("enable", "--now", service_name)
        else:
            self._systemctl("disable", "--now", service_name)
            self._remove_file(USB_WAKE_SERVICE_PATH)
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
                self._run_optional_command(["update-grub"])
            return

        self._update_grub_param(param, False)

    async def get_performance_profiles(self) -> dict:
        support = self._get_current_platform_support()
        if not support.get("supported", False):
            return {
                "profiles": {
                    profile_id: {**profile, "available": False}
                    for profile_id, profile in NATIVE_PERFORMANCE_PROFILES.items()
                },
                "current": "",
                "suggested_default": "",
                "available": False,
                "available_native": [],
                "status": support.get("reason", "Platform is not supported"),
            }

        if self.steamos_manager is None:
            self.steamos_manager = SteamOsManagerClient(decky.logger)

        native_state = self.steamos_manager.get_performance_state()
        available_native = native_state.get("available_native", [])
        current = native_state.get("current") or ""
        profiles = {}

        for profile_id, profile in NATIVE_PERFORMANCE_PROFILES.items():
            profiles[profile_id] = {
                **profile,
                "available": native_state.get("available", False) and profile_id in available_native
            }

        return {
            "profiles": profiles,
            "current": current,
            "suggested_default": native_state.get("suggested_default", ""),
            "available": native_state.get("available", False),
            "available_native": available_native,
            "status": native_state.get("status", "SteamOS native profiles unavailable")
        }

    async def get_performance_modes(self) -> dict:
        profiles_data = await self.get_performance_profiles()
        active_native = profiles_data.get("current", "")
        active_mode = active_native if active_native in NATIVE_PERFORMANCE_PROFILES else ""

        modes = []
        for profile_id, profile in NATIVE_PERFORMANCE_PROFILES.items():
            native_profile = profiles_data["profiles"].get(profile_id, {})
            modes.append({
                "id": profile_id,
                "label": profile["name"],
                "native_id": profile_id,
                "description": profile["description"],
                "available": native_profile.get("available", False),
                "active": active_mode == profile_id and native_profile.get("available", False),
            })

        return {
            "modes": modes,
            "active_mode": active_mode,
            "native_active": active_native,
            "available": profiles_data.get("available", False),
            "status": profiles_data.get("status", "SteamOS native profiles unavailable"),
        }

    async def set_performance_profile(self, profile_id: str) -> bool:
        try:
            support = self._get_current_platform_support()
            if not support.get("supported", False):
                decky.logger.warning(support.get("reason", "Platform is not supported"))
                return False

            if profile_id not in NATIVE_PERFORMANCE_PROFILES:
                decky.logger.error(f"Unknown profile: {profile_id}")
                return False

            if self.steamos_manager is None:
                self.steamos_manager = SteamOsManagerClient(decky.logger)

            native_state = self.steamos_manager.get_performance_state()
            if not native_state.get("available", False):
                decky.logger.warning(native_state.get("status", "SteamOS native profiles unavailable"))
                return False

            if profile_id not in native_state.get("available_native", []):
                decky.logger.warning(f"SteamOS performance profile is not available: {profile_id}")
                return False

            success, error = self.steamos_manager.set_performance_profile(profile_id)
            if not success:
                decky.logger.error(f"Failed to set SteamOS performance profile: {error}")
                return False
            
            profile_name = NATIVE_PERFORMANCE_PROFILES[profile_id]["name"]
            decky.logger.info(f"Applied SteamOS performance profile: {profile_name} ({profile_id})")
            return True
            
        except Exception as e:
            decky.logger.error(f"Failed to set performance profile: {e}")
            return False

    async def get_display_sync_state(self) -> dict:
        support = self._get_current_platform_support()
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

        if self.gamescope_settings is None:
            self.gamescope_settings = GamescopeSettingsClient(decky.logger)

        return self.gamescope_settings.get_display_sync_state()

    async def set_display_sync_setting(self, key: str, enabled: bool) -> bool:
        try:
            support = self._get_current_platform_support()
            if not support.get("supported", False):
                decky.logger.warning(support.get("reason", "Platform is not supported"))
                return False

            if self.gamescope_settings is None:
                self.gamescope_settings = GamescopeSettingsClient(decky.logger)

            if key == "vrr":
                success, error = self.gamescope_settings.set_vrr_enabled(enabled)
            elif key == "vsync":
                success, error = self.gamescope_settings.set_vsync_enabled(enabled)
            else:
                decky.logger.error(f"Unknown display sync setting: {key}")
                return False

            if not success:
                decky.logger.warning(f"Failed to set display sync setting {key}: {error}")
                return False

            decky.logger.info(
                f"Set display sync setting {key} to {'enabled' if enabled else 'disabled'}"
            )
            return True
        except Exception as e:
            decky.logger.error(f"Failed to set display sync setting {key}: {e}")
            return False

    async def get_fps_limit_state(self) -> dict:
        support = self._get_current_platform_support()
        if not support.get("supported", False):
            return {
                "available": False,
                "current": 0,
                "requested": 0,
                "is_live": False,
                "presets": self._get_fps_presets(),
                "status": support.get("reason", "Platform is not supported"),
                "details": support.get("reason", "Platform is not supported"),
            }

        available = self._command_exists("gamescopectl")
        live_value = None

        if available:
            success, output = self._run_command_output(["gamescopectl", "debug_get_fps_limit"])
            if success:
                try:
                    live_value = int((output or "0").splitlines()[-1])
                except Exception as exc:
                    decky.logger.warning(f"Could not parse live gamescope fps limit: {exc}")
            elif output:
                decky.logger.warning(f"Could not read live gamescope fps limit: {output}")

        current = 0 if live_value is None else live_value
        return {
            "available": available,
            "current": current,
            "requested": current,
            "is_live": live_value is not None,
            "presets": self._get_fps_presets(),
            "status": "available" if available else "gamescopectl is not installed",
            "details": (
                "Uses live gamescope framerate control"
                if live_value is not None
                else "Live gamescope framerate control is available, but the current limit cannot be read"
                if available
                else "Live framerate control is unavailable on this system"
            ),
        }

    async def set_fps_limit(self, value: int) -> bool:
        support = self._get_current_platform_support()
        if not support.get("supported", False):
            decky.logger.warning(support.get("reason", "Platform is not supported"))
            return False

        value = max(0, int(value))
        if not self._command_exists("gamescopectl"):
            decky.logger.warning("gamescopectl is not installed")
            return False

        if value not in self._get_fps_presets():
            decky.logger.warning(f"Unsupported framerate preset: {value}")
            return False

        success, error = self._run_command([
            "gamescopectl",
            "debug_set_fps_limit",
            str(value),
        ])
        if not success:
            decky.logger.error(f"Failed to set framerate limit: {error}")
            return False

        decky.logger.info(
            "Applied gamescope framerate limit: unlimited"
            if value == 0
            else f"Applied gamescope framerate limit: {value}"
        )
        return True

    async def get_charge_limit_state(self) -> dict:
        support = self._get_current_platform_support()
        if not support.get("supported", False):
            return {
                "available": False,
                "enabled": False,
                "limit": STEAMOS_CHARGE_FULL_PERCENT,
                "status": support.get("reason", "Platform is not supported"),
                "details": support.get("reason", "Platform is not supported"),
            }

        if self.steamos_manager is None:
            self.steamos_manager = SteamOsManagerClient(decky.logger)

        return self.steamos_manager.get_charge_limit_state()

    async def set_charge_limit_enabled(self, enabled: bool) -> bool:
        try:
            support = self._get_current_platform_support()
            if not support.get("supported", False):
                decky.logger.warning(support.get("reason", "Platform is not supported"))
                return False

            if self.steamos_manager is None:
                self.steamos_manager = SteamOsManagerClient(decky.logger)

            success, error = self.steamos_manager.set_charge_limit_enabled(enabled)
            if not success:
                decky.logger.warning(f"Failed to set SteamOS charge limit: {error}")
                return False

            decky.logger.info(
                f"SteamOS charge limit {'enabled' if enabled else 'disabled'}"
            )
            return True
        except Exception as e:
            decky.logger.error(f"Failed to set SteamOS charge limit: {e}")
            return False

    async def get_smt_state(self) -> dict:
        support = self._get_current_platform_support()
        if not support.get("supported", False):
            return {
                "available": False,
                "enabled": False,
                "status": support.get("reason", "Platform is not supported"),
                "details": support.get("reason", "Platform is not supported"),
            }

        if self.steamos_manager is None:
            self.steamos_manager = SteamOsManagerClient(decky.logger)

        steamos_state = self.steamos_manager.get_smt_state()
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
            support = self._get_current_platform_support()
            if not support.get("supported", False):
                decky.logger.warning(support.get("reason", "Platform is not supported"))
                return False

            if self.steamos_manager is None:
                self.steamos_manager = SteamOsManagerClient(decky.logger)

            steamos_state = self.steamos_manager.get_smt_state()
            if steamos_state.get("available", False):
                success, error = self.steamos_manager.set_smt_enabled(enabled)
                if not success:
                    decky.logger.warning(f"Failed to set SteamOS SMT: {error}")
                    return False
            elif os.path.exists(SMT_CONTROL_PATH):
                with open(SMT_CONTROL_PATH, "w") as f:
                    f.write("on" if enabled else "off")
            else:
                decky.logger.warning("SMT control unavailable")
                return False

            decky.logger.info(f"SMT {'enabled' if enabled else 'disabled'}")
            return True
        except PermissionError:
            decky.logger.error("Permission denied setting SMT - requires root")
            return False
        except Exception as e:
            decky.logger.error(f"Failed to set SMT: {e}")
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
            return {
                "smt_enabled": False,
                "smt_available": False,
                "boost_enabled": False,
                "boost_available": False,
                "status": support.get("reason", "Platform is not supported"),
            }

        smt = await self.get_smt_state()
        result = {
            "smt_enabled": smt.get("enabled", False),
            "smt_available": smt.get("available", False),
            "smt_status": smt.get("status", ""),
            "smt_details": smt.get("details", ""),
            "boost_enabled": False,
            "boost_available": os.path.exists(CPU_BOOST_PATH)
        }
        
        try:
            if os.path.exists(CPU_BOOST_PATH):
                with open(CPU_BOOST_PATH, 'r') as f:
                    boost_state = f.read().strip()
                result["boost_enabled"] = boost_state == "1"
        except Exception as e:
            decky.logger.error(f"Failed to read CPU settings: {e}")
        
        return result

    async def set_cpu_boost_enabled(self, enabled: bool) -> bool:
        """Enable or disable CPU boost"""
        try:
            support = self._get_current_platform_support()
            if not support.get("supported", False):
                decky.logger.warning(support.get("reason", "Platform is not supported"))
                return False

            if not os.path.exists(CPU_BOOST_PATH):
                decky.logger.warning("CPU boost control not available")
                return False
            
            value = "1" if enabled else "0"
            with open(CPU_BOOST_PATH, 'w') as f:
                f.write(value)
            
            decky.logger.info(f"CPU boost {'enabled' if enabled else 'disabled'}")
            return True
            
        except PermissionError:
            decky.logger.error("Permission denied setting CPU boost - requires root")
            return False
        except Exception as e:
            decky.logger.error(f"Failed to set CPU boost: {e}")
            return False

    async def get_dashboard_state(self) -> dict:
        performance_modes = await self.get_performance_modes()
        cpu = await self.get_cpu_settings()
        rgb = await self.get_rgb_state()
        sync = await self.get_display_sync_state()
        fps_limit = await self.get_fps_limit_state()
        charge_limit = await self.get_charge_limit_state()

        return {
            "performance_modes": performance_modes.get("modes", []),
            "active_mode": performance_modes.get("active_mode", ""),
            "profiles_available": performance_modes.get("available", False),
            "profiles_status": performance_modes.get("status", ""),
            "cpu_boost": {
                "available": cpu.get("boost_available", False),
                "enabled": cpu.get("boost_enabled", False),
                "status": "available" if cpu.get("boost_available", False) else "CPU boost control unavailable",
                "details": (
                    "Boosts CPU clocks for heavier games"
                    if cpu.get("boost_available", False)
                    else cpu.get("status", "CPU boost control unavailable")
                ),
            },
            "smt": {
                "available": cpu.get("smt_available", False),
                "enabled": cpu.get("smt_enabled", False),
                "status": "available" if cpu.get("smt_available", False) else "SMT control unavailable",
                "details": (
                    cpu.get("smt_details")
                    if cpu.get("smt_available", False)
                    else cpu.get("smt_status", "SMT control unavailable")
                ),
            },
            "rgb": rgb,
            "vrr": sync.get("vrr", {}),
            "vsync": sync.get("vsync", {}),
            "fps_limit": fps_limit,
            "charge_limit": charge_limit,
        }

    async def get_information_state(self) -> dict:
        device = await self.get_device_info()
        battery = await self.get_battery_info()
        profiles = await self.get_performance_profiles()
        sync = await self.get_display_sync_state()
        temps = await self.get_current_tdp()
        cpu = await self.get_cpu_settings()
        rgb = await self.get_rgb_state()
        optimizations = await self.get_optimization_states()
        fps_limit = await self.get_fps_limit_state()
        charge_limit = await self.get_charge_limit_state()
        platform_supported = device.get("platform_supported", device.get("supported", False))

        hardware_controls = {
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
        }
