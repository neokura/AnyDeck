import asyncio
import importlib
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


class FakeLogger:
    def info(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass

    def error(self, *_args, **_kwargs):
        pass


class FakeHidDevice:
    writes = []

    def __init__(self, path=None):
        self.path = path

    def write(self, command):
        self.writes.append(bytes(command))

    def close(self):
        pass


class FakeHidModule:
    devices = []
    Device = FakeHidDevice

    @classmethod
    def enumerate(cls):
        return cls.devices


fake_decky = types.SimpleNamespace(
    DECKY_PLUGIN_SETTINGS_DIR=tempfile.gettempdir(),
    logger=FakeLogger(),
)
sys.modules.setdefault("decky", fake_decky)
main = importlib.import_module("main")

SUPPORTED_PLATFORM = {
    "supported": True,
    "support_level": "supported",
    "reason": "Supported ASUS/Lenovo handheld on SteamOS 3.8 or newer.",
}


class SteamOsManagerClientTest(unittest.TestCase):
    def test_sanitized_system_env_removes_embedded_runtime_library_overrides(self):
        with patch.dict(
            "main.os.environ",
            {
                "LD_LIBRARY_PATH": "/tmp/_MEI/lib",
                "PYTHONHOME": "/tmp/_MEI",
                "_PYI_APPLICATION_HOME_DIR": "/tmp/_MEI",
                "DISPLAY": ":1",
                "PATH": "/usr/bin:/bin",
            },
            clear=True,
        ):
            env = main.sanitized_system_env({"DISPLAY": ":0"})

        self.assertNotIn("LD_LIBRARY_PATH", env)
        self.assertNotIn("PYTHONHOME", env)
        self.assertNotIn("_PYI_APPLICATION_HOME_DIR", env)
        self.assertEqual(env["DISPLAY"], ":0")
        self.assertEqual(env["PATH"], "/usr/bin:/bin")

    def test_reads_native_performance_state(self):
        def fake_run(cmd, **_kwargs):
            if "introspect" in cmd:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    "\n".join(
                        [
                            "com.steampowered.SteamOSManager1.PerformanceProfile1 interface - -",
                            "AvailablePerformanceProfiles property as 3 emits-change",
                            "PerformanceProfile property s - emits-change",
                            "SuggestedDefaultPerformanceProfile property s - emits-change",
                        ]
                    ),
                    "",
                )
            prop = cmd[-1]
            if prop == "AvailablePerformanceProfiles":
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    'as 3 "low-power" "balanced" "performance"\n',
                    "",
                )
            if prop == "PerformanceProfile":
                return subprocess.CompletedProcess(cmd, 0, 's "balanced"\n', "")
            if prop == "SuggestedDefaultPerformanceProfile":
                return subprocess.CompletedProcess(cmd, 0, 's "performance"\n', "")
            return subprocess.CompletedProcess(cmd, 1, "", "unknown property")

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.SteamOsManagerClient(FakeLogger())
            state = client.get_performance_state()

        self.assertTrue(state["available"])
        self.assertEqual(state["current"], "balanced")
        self.assertEqual(state["suggested_default"], "performance")
        self.assertEqual(
            state["available_native"],
            ["low-power", "balanced", "performance"],
        )

    def test_reports_unavailable_when_dbus_fails(self):
        def fake_run(cmd, **_kwargs):
            return subprocess.CompletedProcess(cmd, 1, "", "service not found")

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.SteamOsManagerClient(FakeLogger())
            state = client.get_performance_state()

        self.assertFalse(state["available"])
        self.assertEqual(state["available_native"], [])
        self.assertIn("SteamOS native profiles unavailable", state["status"])

    def test_uses_user_bus_with_explicit_session_bus_address(self):
        calls = []

        def fake_run(cmd, **_kwargs):
            calls.append((cmd, _kwargs))
            if "introspect" in cmd:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    "\n".join(
                        [
                            "com.steampowered.SteamOSManager1.PerformanceProfile1 interface - -",
                            "AvailablePerformanceProfiles property as 3 emits-change",
                            "PerformanceProfile property s - emits-change",
                            "SuggestedDefaultPerformanceProfile property s - emits-change",
                        ]
                    ),
                    "",
                )
            prop = cmd[-1]
            if prop == "AvailablePerformanceProfiles":
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    'as 3 "low-power" "balanced" "performance"\n',
                    "",
                )
            if prop == "PerformanceProfile":
                return subprocess.CompletedProcess(cmd, 0, 's "balanced"\n', "")
            if prop == "SuggestedDefaultPerformanceProfile":
                return subprocess.CompletedProcess(cmd, 0, 's "performance"\n', "")
            return subprocess.CompletedProcess(cmd, 1, "", "unknown interface")

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.SteamOsManagerClient(FakeLogger())
            state = client.get_performance_state()

        self.assertTrue(state["available"])
        self.assertEqual(state["current"], "balanced")
        first_cmd, first_kwargs = calls[0]
        self.assertIn("--user", first_cmd)
        env = first_kwargs.get("env", {})
        self.assertTrue(env.get("DBUS_SESSION_BUS_ADDRESS", "").startswith("unix:path="))
        self.assertTrue(env.get("XDG_RUNTIME_DIR", "").startswith("/run/user/"))

    def test_sets_native_performance_profile(self):
        calls = []

        def fake_run(cmd, **_kwargs):
            calls.append(cmd)
            if "introspect" in cmd:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    "com.steampowered.SteamOSManager1.PerformanceProfile1 interface - -\n"
                    "PerformanceProfile property s - emits-change\n",
                    "",
                )
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.SteamOsManagerClient(FakeLogger())
            success, error = client.set_performance_profile("low-power")

        self.assertTrue(success)
        self.assertEqual(error, "")
        set_calls = [call for call in calls if "set-property" in call]
        self.assertTrue(set_calls)
        self.assertEqual(set_calls[0][-1], "low-power")

    def test_reads_steamos_charge_limit_state(self):
        def fake_run(cmd, **_kwargs):
            if "introspect" in cmd:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    "\n".join(
                        [
                            "com.steampowered.SteamOSManager1.BatteryChargeLimit1 interface - -",
                            "MaxChargeLevel property i - emits-change",
                            "SuggestedMinimumLimit property i - emits-change",
                        ]
                    ),
                    "",
                )
            if "get-property" in cmd and cmd[-1] == "MaxChargeLevel":
                return subprocess.CompletedProcess(cmd, 0, "i 80\n", "")
            if "get-property" in cmd and cmd[-1] == "SuggestedMinimumLimit":
                return subprocess.CompletedProcess(cmd, 0, "i 30\n", "")
            return subprocess.CompletedProcess(cmd, 1, "", "unknown property")

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.SteamOsManagerClient(FakeLogger())
            state = client.get_charge_limit_state()

        self.assertTrue(state["available"])
        self.assertTrue(state["enabled"])
        self.assertEqual(state["limit"], 80)
        self.assertEqual(state["suggested_minimum"], 30)

    def test_sets_steamos_charge_limit_to_80_or_reset_default(self):
        calls = []

        def fake_run(cmd, **_kwargs):
            calls.append(cmd)
            if "introspect" in cmd:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    "com.steampowered.SteamOSManager1.BatteryChargeLimit1 interface - -\n"
                    "MaxChargeLevel property i - emits-change\n",
                    "",
                )
            if "set-property" in cmd:
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return subprocess.CompletedProcess(cmd, 1, "", "unknown property")

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.SteamOsManagerClient(FakeLogger())
            enabled, enabled_error = client.set_charge_limit_enabled(True)
            disabled, disabled_error = client.set_charge_limit_enabled(False)

        self.assertTrue(enabled)
        self.assertEqual(enabled_error, "")
        self.assertTrue(disabled)
        self.assertEqual(disabled_error, "")
        set_calls = [call for call in calls if "set-property" in call]
        self.assertEqual(set_calls[0][-1], "80")
        self.assertEqual(set_calls[1][-1], "-1")

    def test_reads_steamos_cpu_boost_state(self):
        def fake_run(cmd, **_kwargs):
            if "introspect" in cmd:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    "com.steampowered.SteamOSManager1.CpuBoost1 interface - -\n"
                    "CpuBoostState property u - emits-change\n",
                    "",
                )
            if "get-property" in cmd and cmd[-1] == "CpuBoostState":
                return subprocess.CompletedProcess(cmd, 0, "u 1\n", "")
            return subprocess.CompletedProcess(cmd, 1, "", "unknown property")

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.SteamOsManagerClient(FakeLogger())
            state = client.get_cpu_boost_state()

        self.assertTrue(state["available"])
        self.assertTrue(state["enabled"])

    def test_sets_steamos_cpu_boost_state(self):
        calls = []

        def fake_run(cmd, **_kwargs):
            calls.append(cmd)
            if "introspect" in cmd:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    "com.steampowered.SteamOSManager1.CpuBoost1 interface - -\n"
                    "CpuBoostState property u - emits-change\n",
                    "",
                )
            if "set-property" in cmd:
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return subprocess.CompletedProcess(cmd, 1, "", "unknown property")

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.SteamOsManagerClient(FakeLogger())
            enabled, enabled_error = client.set_cpu_boost_enabled(True)
            disabled, disabled_error = client.set_cpu_boost_enabled(False)

        self.assertTrue(enabled)
        self.assertEqual(enabled_error, "")
        self.assertTrue(disabled)
        self.assertEqual(disabled_error, "")
        set_calls = [call for call in calls if "set-property" in call]
        self.assertEqual(set_calls[0][-1], "1")
        self.assertEqual(set_calls[1][-1], "0")

    def test_reports_smt_as_not_exposed_by_steamos_manager(self):
        client = main.SteamOsManagerClient(FakeLogger())
        state = client.get_smt_state()

        self.assertFalse(state["available"])
        self.assertIn("does not expose", state["details"])


class GamescopeSettingsClientTest(unittest.TestCase):
    def test_reads_gamescope_display_sync_state(self):
        outputs = {
            main.GAMESCOPE_VRR_CAPABLE_ATOM: "GAMESCOPE_VRR_CAPABLE(CARDINAL) = 1\n",
            main.GAMESCOPE_VRR_ENABLED_ATOM: "GAMESCOPE_VRR_ENABLED(CARDINAL) = 1\n",
            main.GAMESCOPE_VRR_FEEDBACK_ATOM: "GAMESCOPE_VRR_FEEDBACK(CARDINAL) = 0\n",
            main.GAMESCOPE_ALLOW_TEARING_ATOM: "GAMESCOPE_ALLOW_TEARING(CARDINAL) = 0\n",
        }

        def fake_run(cmd, **_kwargs):
            return subprocess.CompletedProcess(cmd, 0, outputs[cmd[-1]], "")

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.GamescopeSettingsClient(FakeLogger(), display=":0")
            state = client.get_display_sync_state()

        self.assertTrue(state["vrr"]["available"])
        self.assertTrue(state["vrr"]["enabled"])
        self.assertFalse(state["vrr"]["active"])
        self.assertTrue(state["vsync"]["available"])
        self.assertTrue(state["vsync"]["enabled"])
        self.assertFalse(state["vsync"]["allow_tearing"])

    def test_sets_vsync_as_inverse_allow_tearing(self):
        calls = []

        def fake_run(cmd, **_kwargs):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.GamescopeSettingsClient(FakeLogger(), display=":0")
            enabled, enabled_error = client.set_vsync_enabled(True)
            disabled, disabled_error = client.set_vsync_enabled(False)

        self.assertTrue(enabled)
        self.assertEqual(enabled_error, "")
        self.assertTrue(disabled)
        self.assertEqual(disabled_error, "")
        self.assertEqual(calls[0][-2], main.GAMESCOPE_ALLOW_TEARING_ATOM)
        self.assertEqual(calls[0][-1], "0")
        self.assertEqual(calls[1][-2], main.GAMESCOPE_ALLOW_TEARING_ATOM)
        self.assertEqual(calls[1][-1], "1")

    def test_rejects_vrr_when_display_is_not_capable(self):
        def fake_run(cmd, **_kwargs):
            return subprocess.CompletedProcess(
                cmd,
                0,
                "GAMESCOPE_VRR_CAPABLE(CARDINAL) = 0\n",
                "",
            )

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.GamescopeSettingsClient(FakeLogger(), display=":0")
            success, error = client.set_vrr_enabled(True)

        self.assertFalse(success)
        self.assertIn("not VRR capable", error)

    def test_falls_back_to_secondary_display_when_primary_is_unavailable(self):
        outputs = {
            main.GAMESCOPE_VRR_CAPABLE_ATOM: "GAMESCOPE_VRR_CAPABLE(CARDINAL) = 1\n",
            main.GAMESCOPE_VRR_ENABLED_ATOM: "GAMESCOPE_VRR_ENABLED(CARDINAL) = 0\n",
            main.GAMESCOPE_VRR_FEEDBACK_ATOM: "GAMESCOPE_VRR_FEEDBACK(CARDINAL) = 0\n",
            main.GAMESCOPE_ALLOW_TEARING_ATOM: "GAMESCOPE_ALLOW_TEARING(CARDINAL) = 0\n",
        }

        def fake_run(cmd, **kwargs):
            display = kwargs.get("env", {}).get("DISPLAY")
            if display == ":0":
                return subprocess.CompletedProcess(cmd, 1, "", "unable to open display :0")
            return subprocess.CompletedProcess(cmd, 0, outputs[cmd[-1]], "")

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.GamescopeSettingsClient(FakeLogger(), display=":0")
            state = client.get_display_sync_state()

        self.assertEqual(state["display"], ":1")
        self.assertTrue(state["vrr"]["available"])

    def test_vrr_stays_available_when_capable_atom_is_missing_but_enabled_atom_exists(self):
        outputs = {
            main.GAMESCOPE_VRR_ENABLED_ATOM: "GAMESCOPE_VRR_ENABLED(CARDINAL) = 1\n",
            main.GAMESCOPE_VRR_FEEDBACK_ATOM: "GAMESCOPE_VRR_FEEDBACK(CARDINAL) = 1\n",
            main.GAMESCOPE_ALLOW_TEARING_ATOM: "GAMESCOPE_ALLOW_TEARING(CARDINAL) = 0\n",
        }

        def fake_run(cmd, **_kwargs):
            atom = cmd[-1]
            if atom == main.GAMESCOPE_VRR_CAPABLE_ATOM:
                return subprocess.CompletedProcess(cmd, 1, "", "no such atom")
            return subprocess.CompletedProcess(cmd, 0, outputs[atom], "")

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.GamescopeSettingsClient(FakeLogger(), display=":0")
            state = client.get_display_sync_state()

        self.assertTrue(state["vrr"]["available"])
        self.assertTrue(state["vrr"]["enabled"])
        self.assertTrue(state["vrr"]["active"])


class PluginPerformanceProfileTest(unittest.TestCase):
    def test_device_metadata_uses_uniform_handheld_support(self):
        plugin = main.Plugin()

        first = plugin._get_device_metadata("BOARD-A", "Generic Handheld A", "ASUS")
        second = plugin._get_device_metadata("BOARD-B", "Generic Handheld B", "LENOVO")

        self.assertEqual(first["device_family"], "steamos_handheld")
        self.assertEqual(first["support_level"], "supported")
        self.assertEqual(second["device_family"], "steamos_handheld")
        self.assertEqual(second["support_level"], "supported")

    def test_platform_support_allows_asus_and_lenovo_on_steamos_38_or_newer(self):
        plugin = main.Plugin()
        asus = plugin._get_platform_support(
            "RC7A",
            "ASUS Handheld",
            "ASUS",
            "",
            {
                "ID": "steamos",
                "VERSION_ID": "3.8.0",
                "PRETTY_NAME": "SteamOS 3.8",
            },
        )
        lenovo_future = plugin._get_platform_support(
            "BOARD-B",
            "Lenovo Handheld",
            "LENOVO",
            "Legion",
            {
                "ID": "steamos",
                "VERSION_ID": "3.9.1",
                "PRETTY_NAME": "SteamOS 3.9.1",
            },
        )

        self.assertTrue(asus["supported"])
        self.assertEqual(asus["support_level"], "supported")
        self.assertTrue(lenovo_future["supported"])

    def test_platform_support_allows_common_lenovo_legion_identifiers(self):
        plugin = main.Plugin()
        support = plugin._get_platform_support(
            "LNVNB161216",
            "83E1",
            "LENOVO",
            "Legion Go",
            {
                "ID": "steamos",
                "VERSION_ID": "3.8.0",
                "PRETTY_NAME": "SteamOS 3.8",
            },
        )

        self.assertTrue(support["supported"])

    def test_platform_support_allows_common_asus_ally_identifiers(self):
        plugin = main.Plugin()
        support = plugin._get_platform_support(
            "RC71L",
            "ROG Ally",
            "ASUSTeK COMPUTER INC.",
            "",
            {
                "ID": "steamos",
                "VERSION_ID": "3.8.0",
                "PRETTY_NAME": "SteamOS 3.8",
            },
        )

        self.assertTrue(support["supported"])

    def test_platform_support_blocks_steam_deck(self):
        plugin = main.Plugin()
        support = plugin._get_platform_support(
            "Jupiter",
            "Steam Deck",
            "Valve",
            "",
            {
                "ID": "steamos",
                "VERSION_ID": "3.8.0",
                "PRETTY_NAME": "SteamOS 3.8",
            },
        )

        self.assertFalse(support["supported"])
        self.assertEqual(support["support_level"], "blocked")
        self.assertIn("Steam Deck", support["reason"])

    def test_platform_support_blocks_non_steamos_distributions(self):
        plugin = main.Plugin()

        bazzite = plugin._get_platform_support(
            "BOARD-A",
            "Generic Handheld",
            "ASUS",
            "",
            {"ID": "bazzite", "VERSION_ID": "42", "PRETTY_NAME": "Bazzite"},
        )
        chimera = plugin._get_platform_support(
            "BOARD-A",
            "Generic Handheld",
            "ASUS",
            "",
            {"ID": "chimeraos", "VERSION_ID": "48", "PRETTY_NAME": "ChimeraOS"},
        )

        self.assertFalse(bazzite["supported"])
        self.assertFalse(chimera["supported"])

    def test_platform_support_blocks_other_steamos_versions(self):
        plugin = main.Plugin()
        support = plugin._get_platform_support(
            "BOARD-A",
            "ASUS Handheld",
            "ASUS",
            "",
            {
                "ID": "steamos",
                "VERSION_ID": "3.7.0",
                "PRETTY_NAME": "SteamOS 3.7",
            },
        )

        self.assertFalse(support["supported"])

    def test_platform_support_blocks_non_asus_lenovo_handhelds(self):
        plugin = main.Plugin()
        support = plugin._get_platform_support(
            "BOARD-A",
            "Generic Handheld",
            "VENDOR-A",
            "",
            {
                "ID": "steamos",
                "VERSION_ID": "3.9.0",
                "PRETTY_NAME": "SteamOS 3.9",
            },
        )

        self.assertFalse(support["supported"])
        self.assertIn("ASUS and Lenovo", support["reason"])

    def test_plugin_instances_do_not_share_settings(self):
        first = main.Plugin()
        second = main.Plugin()

        first.settings["example"] = "value"

        self.assertNotIn("example", second.settings)

    def test_plugin_rejects_unknown_profile(self):
        plugin = main.Plugin()
        plugin.steamos_manager = object()
        result = asyncio.run(plugin.set_performance_profile("turbo"))
        self.assertFalse(result)

    def test_plugin_rejects_unknown_display_sync_setting(self):
        plugin = main.Plugin()
        result = asyncio.run(plugin.set_display_sync_setting("hdr", True))
        self.assertFalse(result)

    def test_plugin_uses_steamos_manager_without_manual_tdp(self):
        class FakeSteamOsManager:
            def __init__(self):
                self.set_calls = []

            def get_performance_state(self):
                return {
                    "available": True,
                    "available_native": ["low-power", "balanced", "performance"],
                    "current": "performance",
                    "suggested_default": "performance",
                    "status": "available",
                }

            def set_performance_profile(self, profile_id):
                self.set_calls.append(profile_id)
                return True, ""

        async def fail_if_called(_tdp):
            raise AssertionError("manual TDP fallback should not be used")

        with tempfile.TemporaryDirectory() as tmpdir:
            plugin = main.Plugin()
            plugin.settings_path = os.path.join(tmpdir, "settings.json")
            plugin.settings = {}
            plugin.steamos_manager = FakeSteamOsManager()
            plugin.set_tdp = fail_if_called

            with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM):
                result = asyncio.run(plugin.set_performance_profile("balanced"))

        self.assertTrue(result)
        self.assertNotIn("current_profile", plugin.settings)
        self.assertEqual(plugin.steamos_manager.set_calls, ["balanced"])

    def test_load_settings_does_not_create_default_settings_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin = main.Plugin()
            plugin.settings_path = os.path.join(tmpdir, "settings.json")

            settings = asyncio.run(plugin.load_settings())

            self.assertEqual(settings, {})
            self.assertFalse(os.path.exists(plugin.settings_path))

    def test_performance_modes_surface_native_steamos_modes(self):
        plugin = main.Plugin()

        with patch.object(
            plugin,
            "get_performance_profiles",
            return_value={
                "profiles": {
                    "low-power": {"available": True},
                    "balanced": {"available": True},
                    "performance": {"available": True},
                },
                "current": "balanced",
                "available": True,
                "status": "available",
            },
        ):
            state = asyncio.run(plugin.get_performance_modes())

        self.assertEqual(state["active_mode"], "balanced")
        self.assertEqual(len(state["modes"]), 3)
        self.assertEqual(
            [mode["id"] for mode in state["modes"]],
            ["low-power", "balanced", "performance"],
        )

    def test_dashboard_state_contains_cpu_sync_and_fps(self):
        plugin = main.Plugin()

        with patch.object(
            plugin,
            "get_performance_modes",
            return_value={
                "modes": [{"id": "performance", "label": "Performance", "available": True, "active": True}],
                "active_mode": "performance",
                "available": True,
                "status": "available",
            },
        ), patch.object(
            plugin,
            "get_cpu_settings",
            return_value={
                "boost_available": True,
                "boost_enabled": True,
                "smt_available": True,
                "smt_enabled": False,
                "smt_details": "smt",
            },
        ), patch.object(
            plugin,
            "get_display_sync_state",
            return_value={
                "vrr": {"available": True, "enabled": True, "details": "VRR"},
                "vsync": {"available": True, "enabled": False, "details": "VSync"},
            },
        ), patch.object(
            plugin,
            "get_fps_limit_state",
            return_value={"available": True, "current": 40, "details": "fps", "status": "available"},
        ):
            state = asyncio.run(plugin.get_dashboard_state())

        self.assertEqual(state["active_mode"], "performance")
        self.assertTrue(state["cpu_boost"]["enabled"])
        self.assertTrue(state["smt"]["available"])
        self.assertFalse(state["smt"]["enabled"])
        self.assertEqual(state["fps_limit"]["current"], 40)

    def test_cpu_boost_uses_privileged_write_when_not_root(self):
        plugin = main.Plugin()

        with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM), patch(
            "main.os.path.exists",
            side_effect=lambda path: path == main.CPU_BOOST_PATH,
        ), patch(
            "main.needs_privilege_escalation",
            return_value=True,
        ), patch.object(
            plugin,
            "_write_file",
            return_value=(True, ""),
        ) as write_file:
            result = asyncio.run(plugin.set_cpu_boost_enabled(True))

        self.assertTrue(result)
        write_file.assert_called_once_with(main.CPU_BOOST_PATH, "1", use_sudo=True)

    def test_smt_kernel_fallback_uses_privileged_write_when_not_root(self):
        plugin = main.Plugin()
        plugin.steamos_manager = types.SimpleNamespace(
            get_smt_state=lambda: {
                "available": False,
                "enabled": False,
                "status": "unavailable",
                "details": "fallback",
            }
        )

        with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM), patch(
            "main.os.path.exists",
            side_effect=lambda path: path == main.SMT_CONTROL_PATH,
        ), patch(
            "main.needs_privilege_escalation",
            return_value=True,
        ), patch.object(
            plugin,
            "_write_file",
            return_value=(True, ""),
        ) as write_file:
            result = asyncio.run(plugin.set_smt_enabled(True))

        self.assertTrue(result)
        write_file.assert_called_once_with(main.SMT_CONTROL_PATH, "on", use_sudo=True)

    def test_swap_protect_runs_sysctl_with_sudo_when_not_root(self):
        plugin = main.Plugin()

        with patch(
            "main.needs_privilege_escalation",
            return_value=True,
        ), patch.object(
            plugin,
            "_read_optimization_state",
            return_value={},
        ), patch.object(
            plugin,
            "_write_optimization_state",
            return_value=None,
        ), patch.object(
            plugin,
            "_read_sysctl",
            return_value="",
        ), patch.object(
            plugin,
            "_write_managed_file",
            return_value=None,
        ), patch.object(
            plugin,
            "_refresh_atomic_manifest",
            return_value=None,
        ), patch.object(
            plugin,
            "_run_optional_command",
            return_value="",
        ) as run_optional:
            plugin._set_swap_protect_enabled(True)

        run_optional.assert_called_once_with(["sysctl", "--system"], use_sudo=True)

    def test_fps_presets_use_native_modes_without_high_refresh_by_default(self):
        plugin = main.Plugin()
        plugin.settings = {"fps_limit": 0}

        with patch.object(plugin, "_get_supported_high_refresh_rates", return_value=[]):
            presets = plugin._get_fps_presets()

        self.assertEqual(presets, [30, 40, 60, 0])

    def test_fps_presets_include_supported_high_refresh_modes(self):
        plugin = main.Plugin()
        plugin.settings = {"fps_limit": 0}

        with patch.object(plugin, "_get_supported_high_refresh_rates", return_value=[90, 120, 144]):
            presets = plugin._get_fps_presets()

        self.assertEqual(presets, [30, 40, 60, 90, 120, 144, 0])

    def test_supported_high_refresh_rates_are_read_from_xrandr(self):
        plugin = main.Plugin()
        output = """
Screen 0: minimum 16 x 16, current 1920 x 1080, maximum 32767 x 32767
eDP-1 connected primary 1920x1080+0+0
   1920x1080     143.86*+ 120.00 90.00 60.00
   1280x720      165.00 75.00 59.94
"""

        with patch.object(plugin, "_command_exists", return_value=True), patch.object(
            plugin,
            "_run_command_output",
            return_value=(True, output),
        ):
            rates = plugin._get_supported_high_refresh_rates()

        self.assertEqual(rates, [90, 120, 144, 165])

    def test_supported_high_refresh_rates_accept_integer_xrandr_values(self):
        plugin = main.Plugin()
        output = """
Screen 0: minimum 16 x 16, current 1920 x 1080, maximum 32767 x 32767
eDP-1 connected primary 1920x1080+0+0
   1920x1080     120*+ 90 60
"""

        with patch.object(plugin, "_command_exists", return_value=True), patch.object(
            plugin,
            "_run_command_output",
            return_value=(True, output),
        ):
            rates = plugin._get_supported_high_refresh_rates()

        self.assertEqual(rates, [90, 120])

    def test_fps_limit_rejects_values_outside_supported_presets(self):
        plugin = main.Plugin()
        plugin.settings = {"fps_limit": 0}

        with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM), patch.object(
            plugin,
            "_command_exists",
            return_value=True,
        ), patch.object(plugin, "_get_fps_presets", return_value=[30, 40, 60, 0]):
            result = asyncio.run(plugin.set_fps_limit(45))

        self.assertFalse(result)

    def test_fps_limit_state_reads_alternate_gamescopectl_output(self):
        plugin = main.Plugin()

        def fake_run_command_output(command):
            if command[1] == "debug_get_fps_limit":
                return False, "unknown command"
            if command[1] == "get_fps_limit":
                return True, "current_fps_limit 40"
            return False, ""

        with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM), patch.object(
            plugin,
            "_command_exists",
            return_value=True,
        ), patch.object(
            plugin,
            "_run_command_output",
            side_effect=fake_run_command_output,
        ):
            state = asyncio.run(plugin.get_fps_limit_state())

        self.assertTrue(state["available"])
        self.assertTrue(state["is_live"])
        self.assertEqual(state["current"], 40)

    def test_fps_limit_state_falls_back_to_gamescope_atom(self):
        plugin = main.Plugin()

        with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM), patch.object(
            plugin,
            "_command_exists",
            return_value=False,
        ), patch.object(
            main.GamescopeSettingsClient,
            "get_fps_limit_state",
            return_value=(True, 60, "", "GAMESCOPE_FPS_LIMIT"),
        ):
            state = asyncio.run(plugin.get_fps_limit_state())

        self.assertTrue(state["available"])
        self.assertEqual(state["current"], 60)
        self.assertTrue(state["is_live"])

    def test_charge_limit_returns_false_when_control_is_unavailable(self):
        plugin = main.Plugin()

        device = {"supported": True}

        with patch.object(plugin, "get_device_info", return_value=device), patch.object(
            plugin,
            "get_cpu_settings",
            return_value={"boost_available": False, "smt_available": False},
        ), patch.object(
            plugin,
            "get_rgb_state",
            return_value={"available": True},
        ), patch.object(
            plugin,
            "get_performance_profiles",
            return_value={"current": "", "available_native": [], "status": ""},
        ), patch.object(
            plugin,
            "get_display_sync_state",
            return_value={"vrr": {}, "vsync": {}},
        ), patch.object(
            plugin,
            "get_current_tdp",
            return_value={"cpu_temp": 0, "gpu_temp": 0, "gpu_clock": 0},
        ), patch.object(
            plugin,
            "get_optimization_states",
            return_value={"states": []},
        ), patch.object(
            plugin,
            "get_fps_limit_state",
            return_value={"available": False, "current": 0},
        ), patch.object(
            plugin,
            "get_charge_limit_state",
            return_value={"available": False, "enabled": False, "limit": 100},
        ), patch("main.os.path.exists", side_effect=lambda path: path == main.ALLY_LED_PATH), patch(
            "main.glob.glob",
            return_value=[],
        ):
            state = asyncio.run(plugin.get_information_state())

        self.assertFalse(state["hardware_controls"]["charge_limit"])
        self.assertTrue(state["hardware_controls"]["rgb"])

    def test_charge_limit_uses_steamos_manager_state(self):
        plugin = main.Plugin()
        plugin.steamos_manager = types.SimpleNamespace(
            get_charge_limit_state=lambda: {
                "available": True,
                "enabled": True,
                "limit": 80,
                "status": "available",
                "details": "charge",
            }
        )

        with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM):
            state = asyncio.run(plugin.get_charge_limit_state())

        self.assertTrue(state["available"])
        self.assertTrue(state["enabled"])
        self.assertEqual(state["limit"], 80)

    def test_cpu_settings_report_boost_disabled_when_control_is_unavailable(self):
        plugin = main.Plugin()
        original_exists = os.path.exists

        with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM), patch.object(
            plugin,
            "get_smt_state",
            return_value={"available": False, "enabled": False, "status": "missing", "details": "missing"},
        ), patch(
            "main.os.path.exists",
            side_effect=lambda path: False if path == main.CPU_BOOST_PATH else original_exists(path),
        ):
            state = asyncio.run(plugin.get_cpu_settings())

        self.assertFalse(state["boost_available"])
        self.assertFalse(state["boost_enabled"])

    def test_battery_info_discovers_lenovo_style_battery_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            power_supply = os.path.join(tmpdir, "power_supply")
            bat1 = os.path.join(power_supply, "BAT1")
            os.makedirs(bat1)
            files = {
                "type": "Battery",
                "status": "Discharging",
                "capacity": "73",
                "cycle_count": "42",
                "voltage_now": "15400000",
                "current_now": "1800000",
                "energy_full_design": "49000000",
                "energy_full": "46000000",
                "temp": "319",
            }
            for name, value in files.items():
                with open(os.path.join(bat1, name), "w") as f:
                    f.write(value)

            plugin = main.Plugin()

            with patch("main.BATTERY_PATH", os.path.join(power_supply, "BAT0")), patch(
                "main.BATTERY_PATH_GLOBS", [os.path.join(power_supply, "BAT*")]
            ), patch.object(
                plugin,
                "get_charge_limit_state",
                return_value={"available": True, "enabled": True, "limit": 80},
            ):
                state = asyncio.run(plugin.get_battery_info())

        self.assertTrue(state["present"])
        self.assertEqual(state["capacity"], 73)
        self.assertEqual(state["voltage"], 15.4)
        self.assertEqual(state["current"], 1.8)
        self.assertEqual(state["design_capacity"], 49)
        self.assertEqual(state["full_capacity"], 46)
        self.assertEqual(state["temperature"], 31.9)
        self.assertEqual(state["charge_limit"], 80)
        self.assertEqual(state["time_to_empty"], "1h 13m")
        self.assertEqual(state["time_to_full"], "Unknown")

    def test_battery_info_estimates_time_to_charge_limit_when_charging(self):
        plugin = main.Plugin()
        battery = {
            "status": "Charging",
            "capacity": 50,
            "voltage": 15.0,
            "current": 2.0,
            "full_capacity": 40,
            "design_capacity": 42,
            "charge_limit": 80,
        }

        time_to_empty, time_to_full = plugin._estimate_battery_times(battery)

        self.assertEqual(time_to_empty, "Unknown")
        self.assertEqual(time_to_full, "24m")

    def test_rgb_standard_multicolor_led_is_read_and_written(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            led = os.path.join(tmpdir, "legion:rgb:joystick")
            os.makedirs(led)
            with open(os.path.join(led, "brightness"), "w") as f:
                f.write("255")
            with open(os.path.join(led, "multi_index"), "w") as f:
                f.write("red green blue")
            with open(os.path.join(led, "multi_intensity"), "w") as f:
                f.write("0 183 255")

            plugin = main.Plugin()

            with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM), patch(
                "main.ALLY_LED_PATH", os.path.join(tmpdir, "missing")
            ), patch(
                "main.RGB_LED_PATH_GLOBS", [os.path.join(tmpdir, "*:rgb:*")]
            ):
                state = asyncio.run(plugin.get_rgb_state())
                success = asyncio.run(plugin.set_rgb_color("#00FF00"))

            with open(os.path.join(led, "multi_intensity"), "r") as f:
                values = f.read()

        self.assertTrue(state["available"])
        self.assertTrue(state["enabled"])
        self.assertEqual(state["color"], "#00B7FF")
        self.assertTrue(success)
        self.assertEqual(values, "0 255 0")
        self.assertEqual(state["brightness"], 100)
        self.assertEqual(state["mode"], "solid")
        self.assertEqual(state["speed"], "medium")
        self.assertTrue(state["capabilities"]["toggle"])
        self.assertTrue(state["capabilities"]["color"])
        self.assertTrue(state["capabilities"]["brightness"])
        self.assertEqual(state["supported_modes"], ["solid"])
        self.assertFalse(state["speed_available"])

    def test_rgb_accepts_freeform_hex_color_on_sysfs_backend(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            led = os.path.join(tmpdir, "ally:rgb:joystick_rings")
            os.makedirs(led)
            with open(os.path.join(led, "brightness"), "w") as f:
                f.write("255")
            with open(os.path.join(led, "multi_intensity"), "w") as f:
                f.write("47103 47103 47103 47103")

            plugin = main.Plugin()

            with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM), patch(
                "main.ALLY_LED_PATH", led
            ), patch(
                "main.RGB_LED_PATH_GLOBS", []
            ):
                success = asyncio.run(plugin.set_rgb_color("#123ABC"))
                state = asyncio.run(plugin.get_rgb_state())

            with open(os.path.join(led, "multi_intensity"), "r") as f:
                values = f.read()

        self.assertTrue(success)
        self.assertEqual(values, "1194684 1194684 1194684 1194684")
        self.assertEqual(state["color"], "#123ABC")

    def test_rgb_legacy_packed_led_format_still_works_for_ally(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            led = os.path.join(tmpdir, "ally:rgb:joystick_rings")
            os.makedirs(led)
            with open(os.path.join(led, "brightness"), "w") as f:
                f.write("255")
            with open(os.path.join(led, "multi_intensity"), "w") as f:
                f.write("47103 47103 47103 47103")

            plugin = main.Plugin()

            with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM), patch(
                "main.ALLY_LED_PATH", led
            ), patch(
                "main.RGB_LED_PATH_GLOBS", []
            ):
                state = asyncio.run(plugin.get_rgb_state())
                success = asyncio.run(plugin.set_rgb_color("#00FF00"))

            with open(os.path.join(led, "multi_intensity"), "r") as f:
                values = f.read()

        self.assertTrue(state["available"])
        self.assertEqual(state["color"], "#00B7FF")
        self.assertTrue(success)
        self.assertEqual(values, "65280 65280 65280 65280")

    def test_legion_go_s_hid_rgb_uses_huesync_device_ids(self):
        plugin = main.Plugin()
        plugin.settings_path = None
        plugin.settings = {
            "rgb_enabled": True,
            "rgb_color": "#00FFFF",
            "rgb_mode": "solid",
            "rgb_speed": "medium",
        }
        FakeHidDevice.writes = []
        FakeHidModule.devices = [
            {
                "path": b"/dev/hidraw-legion-go-s",
                "vendor_id": 0x1A86,
                "product_id": 0xE310,
                "usage_page": 0xFFA0,
                "usage": 0x0001,
                "interface_number": 3,
            }
        ]

        with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM), patch.object(
            plugin, "_get_rgb_led_path", return_value=""
        ), patch.object(
            plugin, "_hid_module", return_value=FakeHidModule
        ), patch.object(
            plugin, "_hidraw_devices", return_value=[]
        ):
            state = asyncio.run(plugin.get_rgb_state())
            success = asyncio.run(plugin.set_rgb_color("#00FF00"))

        self.assertTrue(state["available"])
        self.assertIn("Legion Go S", state["details"])
        self.assertTrue(success)
        self.assertEqual(state["supported_modes"], ["solid", "pulse", "rainbow"])
        self.assertEqual(FakeHidDevice.writes[0], bytes([0x04, 0x06, 0x01]))
        self.assertEqual(FakeHidDevice.writes[1], bytes([0x10, 0x02, 0x03]))
        self.assertEqual(FakeHidDevice.writes[2], bytes([0x10, 0x05, 0x00, 0x00, 0xFF, 0x00, 0x3F, 0x2A]))

    def test_legion_rgb_brightness_is_scaled_and_persisted(self):
        plugin = main.Plugin()
        plugin.settings_path = None
        plugin.settings = {
            "rgb_enabled": True,
            "rgb_color": "#00FFFF",
            "rgb_brightness": 100,
            "rgb_mode": "solid",
            "rgb_speed": "medium",
        }
        FakeHidDevice.writes = []
        FakeHidModule.devices = [
            {
                "path": b"/dev/hidraw-legion-go-s",
                "vendor_id": 0x1A86,
                "product_id": 0xE310,
                "usage_page": 0xFFA0,
                "usage": 0x0001,
                "interface_number": 3,
            }
        ]

        with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM), patch.object(
            plugin, "_get_rgb_led_path", return_value=""
        ), patch.object(
            plugin, "_hid_module", return_value=FakeHidModule
        ), patch.object(
            plugin, "_hidraw_devices", return_value=[]
        ):
            success = asyncio.run(plugin.set_rgb_brightness(50))
            state = asyncio.run(plugin.get_rgb_state())

        self.assertTrue(success)
        self.assertEqual(plugin.settings["rgb_brightness"], 50)
        self.assertEqual(state["brightness"], 50)
        self.assertEqual(FakeHidDevice.writes[2], bytes([0x10, 0x05, 0x00, 0x00, 0xFF, 0xFF, 0x20, 0x2A]))

    def test_legion_rgb_mode_and_speed_are_applied_natively(self):
        plugin = main.Plugin()
        plugin.settings_path = None
        plugin.settings = {
            "rgb_enabled": True,
            "rgb_color": "#00FFFF",
            "rgb_brightness": 100,
            "rgb_mode": "solid",
            "rgb_speed": "medium",
        }
        FakeHidDevice.writes = []
        FakeHidModule.devices = [
            {
                "path": b"/dev/hidraw-legion-go-s",
                "vendor_id": 0x1A86,
                "product_id": 0xE310,
                "usage_page": 0xFFA0,
                "usage": 0x0001,
                "interface_number": 3,
            }
        ]

        with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM), patch.object(
            plugin, "_get_rgb_led_path", return_value=""
        ), patch.object(
            plugin, "_hid_module", return_value=FakeHidModule
        ), patch.object(
            plugin, "_hidraw_devices", return_value=[]
        ):
            mode_success = asyncio.run(plugin.set_rgb_mode("pulse"))
            speed_success = asyncio.run(plugin.set_rgb_speed("high"))
            state = asyncio.run(plugin.get_rgb_state())

        self.assertTrue(mode_success)
        self.assertTrue(speed_success)
        self.assertEqual(state["mode"], "pulse")
        self.assertEqual(state["speed"], "high")
        self.assertTrue(state["speed_available"])
        self.assertEqual(FakeHidDevice.writes[2], bytes([0x10, 0x05, 0x01, 0x00, 0xFF, 0xFF, 0x3F, 0x2A]))
        self.assertEqual(FakeHidDevice.writes[-1], bytes([0x10, 0x05, 0x01, 0x00, 0xFF, 0xFF, 0x3F, 0x3F]))

    def test_legion_go_tablet_hid_rgb_uses_huesync_device_ids(self):
        plugin = main.Plugin()
        plugin.settings_path = None
        plugin.settings = {
            "rgb_enabled": True,
            "rgb_color": "#00FFFF",
            "rgb_mode": "solid",
            "rgb_speed": "medium",
        }
        FakeHidDevice.writes = []
        FakeHidModule.devices = [
            {
                "path": b"/dev/hidraw-legion-go",
                "vendor_id": 0x17EF,
                "product_id": 0x6182,
                "usage_page": 0xFFA0,
                "usage": 0x0001,
                "interface_number": 0,
            }
        ]

        with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM), patch.object(
            plugin, "_get_rgb_led_path", return_value=""
        ), patch.object(
            plugin, "_hid_module", return_value=FakeHidModule
        ), patch.object(
            plugin, "_hidraw_devices", return_value=[]
        ):
            state = asyncio.run(plugin.get_rgb_state())
            success = asyncio.run(plugin.set_rgb_enabled(False))

        self.assertTrue(state["available"])
        self.assertIn("Legion Go HID", state["details"])
        self.assertTrue(success)
        self.assertEqual(FakeHidDevice.writes[0], bytes([0x05, 0x06, 0x70, 0x02, 0x03, 0x00, 0x01]))
        self.assertEqual(FakeHidDevice.writes[1], bytes([0x05, 0x06, 0x70, 0x02, 0x04, 0x00, 0x01]))

    def test_rgb_state_is_exposed_in_dashboard(self):
        plugin = main.Plugin()
        plugin.settings = {"rgb_enabled": True, "rgb_color": "#00FFFF", "fps_limit": 0}

        with patch.object(
            plugin,
            "get_performance_modes",
            return_value={
                "modes": [],
                "active_mode": "",
                "available": True,
                "status": "available",
            },
        ), patch.object(
            plugin,
            "get_cpu_settings",
            return_value={"boost_available": True, "boost_enabled": True},
        ), patch.object(
            plugin,
            "get_display_sync_state",
            return_value={
                "vrr": {"available": False, "enabled": False, "details": "vrr"},
                "vsync": {"available": True, "enabled": True, "details": "vsync"},
            },
        ), patch.object(
            plugin,
            "get_fps_limit_state",
            return_value={"available": False, "current": 0, "details": "fps", "status": "unavailable"},
        ), patch.object(
            plugin,
            "get_rgb_state",
            return_value={
                "available": True,
                "enabled": True,
                "mode": "solid",
                "color": "#00FFFF",
                "brightness": 75,
                "speed": "medium",
                "brightness_available": True,
                "supports_free_color": True,
                "speed_available": False,
                "capabilities": {
                    "toggle": True,
                    "color": True,
                    "brightness": True,
                },
                "supported_modes": ["solid"],
                "mode_capabilities": {
                    "solid": {"color": True, "brightness": True, "speed": False},
                },
                "speed_options": ["low", "medium", "high"],
                "presets": main.RGB_COLOR_PRESETS,
                "details": "rgb",
            },
        ):
            state = asyncio.run(plugin.get_dashboard_state())

        self.assertTrue(state["rgb"]["available"])
        self.assertEqual(state["rgb"]["color"], "#00FFFF")
        self.assertEqual(state["rgb"]["brightness"], 75)


class OptimizationStateTest(unittest.TestCase):
    def test_swap_protect_state_reports_configured_and_active(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sysctl_path = os.path.join(tmpdir, "memory.conf")
            atomic_path = os.path.join(tmpdir, "atomic.conf")

            with open(sysctl_path, "w") as f:
                f.write(main.MEMORY_SYSCTL_CONTENT)
            with open(atomic_path, "w") as f:
                f.write(f"{sysctl_path}\n")

            plugin = main.Plugin()

            def fake_read_sysctl(key):
                return {
                    "vm.swappiness": "10",
                    "vm.min_free_kbytes": "524288",
                    "vm.dirty_ratio": "5",
                }.get(key, "")

            with patch("main.MEMORY_SYSCTL_PATH", sysctl_path), patch(
                "main.ATOMIC_MANIFEST_PATH", atomic_path
            ), patch.object(plugin, "_read_sysctl", side_effect=fake_read_sysctl), patch.object(
                plugin, "_command_exists", return_value=True
            ):
                state = plugin._get_swap_protect_state()

        self.assertTrue(state["enabled"])
        self.assertTrue(state["active"])
        self.assertFalse(state["needs_reboot"])
        self.assertEqual(state["status"], "active")
        self.assertIn("memory sysctl", state["description"])

    def test_thp_madvise_state_reports_configured_and_active(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            thp_config_path = os.path.join(tmpdir, "thp.conf")
            atomic_path = os.path.join(tmpdir, "atomic.conf")
            thp_enabled_path = os.path.join(tmpdir, "thp_enabled")

            with open(thp_config_path, "w") as f:
                f.write(main.THP_TMPFILES_CONTENT)
            with open(atomic_path, "w") as f:
                f.write(f"{thp_config_path}\n")
            with open(thp_enabled_path, "w") as f:
                f.write("always [madvise] never")

            plugin = main.Plugin()

            with patch("main.THP_TMPFILES_PATH", thp_config_path), patch(
                "main.ATOMIC_MANIFEST_PATH", atomic_path
            ), patch("main.THP_ENABLED_PATH", thp_enabled_path):
                state = plugin._get_thp_madvise_state()

        self.assertTrue(state["enabled"])
        self.assertTrue(state["active"])
        self.assertFalse(state["needs_reboot"])

    def test_atomic_manifest_is_single_file_and_cleans_legacy_manifests(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scx_path = os.path.join(tmpdir, "scx")
            memory_path = os.path.join(tmpdir, "memory.conf")
            thp_path = os.path.join(tmpdir, "thp.conf")
            manifest_path = os.path.join(tmpdir, "xbox-companion.conf")
            legacy_paths = [
                os.path.join(tmpdir, "xbox-companion-scx.conf"),
                os.path.join(tmpdir, "xbox-companion-memory.conf"),
            ]

            with open(scx_path, "w") as f:
                f.write(main.SCX_DEFAULT_CONTENT)
            with open(memory_path, "w") as f:
                f.write(main.MEMORY_SYSCTL_CONTENT)
            with open(thp_path, "w") as f:
                f.write(main.THP_TMPFILES_CONTENT)
            for path in legacy_paths:
                with open(path, "w") as f:
                    f.write("legacy\n")

            plugin = main.Plugin()

            with patch("main.SCX_DEFAULT_PATH", scx_path), patch(
                "main.MEMORY_SYSCTL_PATH", memory_path
            ), patch("main.THP_TMPFILES_PATH", thp_path), patch(
                "main.NPU_BLACKLIST_PATH", os.path.join(tmpdir, "npu.conf")
            ), patch(
                "main.USB_WAKE_SERVICE_PATH", os.path.join(tmpdir, "usb.service")
            ), patch(
                "main.GRUB_DEFAULT_PATH", os.path.join(tmpdir, "grub")
            ), patch(
                "main.ATOMIC_MANIFEST_PATH", manifest_path
            ), patch(
                "main.LEGACY_ATOMIC_PATHS", legacy_paths
            ), patch(
                "main.LEGACY_MANAGED_PATHS", []
            ):
                plugin._refresh_atomic_manifest()

            with open(manifest_path, "r") as f:
                manifest = f.read()
            legacy_removed = not any(os.path.exists(path) for path in legacy_paths)

        self.assertIn(scx_path, manifest)
        self.assertIn(memory_path, manifest)
        self.assertIn(thp_path, manifest)
        self.assertNotIn("xbox-companion-scx.conf", manifest)
        self.assertTrue(legacy_removed)

    def test_lavd_disable_restores_previous_scx_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scx_path = os.path.join(tmpdir, "scx")
            atomic_path = os.path.join(tmpdir, "xbox-companion.conf")
            state_path = os.path.join(tmpdir, "optimization-state.json")
            previous = 'SCX_SCHEDULER="scx_rustland"\nSCX_FLAGS="--custom"\n'
            with open(scx_path, "w") as f:
                f.write(previous)

            plugin = main.Plugin()

            with patch("main.SCX_DEFAULT_PATH", scx_path), patch(
                "main.ATOMIC_MANIFEST_PATH", atomic_path
            ), patch(
                "main.OPTIMIZATION_STATE_PATH", state_path
            ), patch(
                "main.LEGACY_ATOMIC_PATHS", []
            ), patch(
                "main.LEGACY_MANAGED_PATHS", []
            ), patch.object(
                plugin, "_command_exists", return_value=False
            ), patch.object(
                plugin, "_systemctl", return_value=""
            ):
                plugin._set_lavd_enabled(True)
                plugin._set_lavd_enabled(False)

            with open(scx_path, "r") as f:
                restored = f.read()

        self.assertEqual(restored, previous)

    def test_disabling_optimization_removes_only_its_atomic_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scx_path = os.path.join(tmpdir, "scx")
            memory_path = os.path.join(tmpdir, "memory.conf")
            thp_path = os.path.join(tmpdir, "thp.conf")
            manifest_path = os.path.join(tmpdir, "xbox-companion.conf")

            with open(scx_path, "w") as f:
                f.write(main.SCX_DEFAULT_CONTENT)
            with open(memory_path, "w") as f:
                f.write(main.MEMORY_SYSCTL_CONTENT)
            with open(thp_path, "w") as f:
                f.write(main.THP_TMPFILES_CONTENT)

            plugin = main.Plugin()

            with patch("main.SCX_DEFAULT_PATH", scx_path), patch(
                "main.MEMORY_SYSCTL_PATH", memory_path
            ), patch("main.THP_TMPFILES_PATH", thp_path), patch(
                "main.NPU_BLACKLIST_PATH", os.path.join(tmpdir, "npu.conf")
            ), patch(
                "main.USB_WAKE_SERVICE_PATH", os.path.join(tmpdir, "usb.service")
            ), patch(
                "main.GRUB_DEFAULT_PATH", os.path.join(tmpdir, "grub")
            ), patch(
                "main.ATOMIC_MANIFEST_PATH", manifest_path
            ), patch(
                "main.LEGACY_ATOMIC_PATHS", []
            ), patch(
                "main.LEGACY_MANAGED_PATHS", []
            ), patch.object(
                plugin, "_run_optional_command", return_value=""
            ):
                plugin._refresh_atomic_manifest()
                plugin._set_swap_protect_enabled(False)

                with open(manifest_path, "r") as f:
                    manifest = f.read()
                memory_exists = os.path.exists(memory_path)
                thp_exists = os.path.exists(thp_path)

        self.assertIn(scx_path, manifest)
        self.assertNotIn(memory_path, manifest)
        self.assertIn(thp_path, manifest)
        self.assertFalse(memory_exists)
        self.assertTrue(thp_exists)

    def test_atomic_manifest_is_removed_when_last_optimization_is_disabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_path = os.path.join(tmpdir, "memory.conf")
            thp_path = os.path.join(tmpdir, "thp.conf")
            manifest_path = os.path.join(tmpdir, "xbox-companion.conf")

            with open(memory_path, "w") as f:
                f.write(main.MEMORY_SYSCTL_CONTENT)
            with open(thp_path, "w") as f:
                f.write(main.THP_TMPFILES_CONTENT)

            plugin = main.Plugin()

            with patch("main.SCX_DEFAULT_PATH", os.path.join(tmpdir, "scx")), patch(
                "main.MEMORY_SYSCTL_PATH", memory_path
            ), patch("main.THP_TMPFILES_PATH", thp_path), patch(
                "main.NPU_BLACKLIST_PATH", os.path.join(tmpdir, "npu.conf")
            ), patch(
                "main.USB_WAKE_SERVICE_PATH", os.path.join(tmpdir, "usb.service")
            ), patch(
                "main.GRUB_DEFAULT_PATH", os.path.join(tmpdir, "grub")
            ), patch(
                "main.ATOMIC_MANIFEST_PATH", manifest_path
            ), patch(
                "main.LEGACY_ATOMIC_PATHS", []
            ), patch(
                "main.LEGACY_MANAGED_PATHS", []
            ), patch.object(
                plugin, "_run_optional_command", return_value=""
            ):
                plugin._refresh_atomic_manifest()
                plugin._set_swap_protect_enabled(False)
                plugin._set_thp_madvise_enabled(False)
                manifest_exists = os.path.exists(manifest_path)

        self.assertFalse(manifest_exists)

    def test_swap_protect_state_reports_reboot_required_when_runtime_tuning_remains_after_disable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_path = os.path.join(tmpdir, "memory.conf")
            manifest_path = os.path.join(tmpdir, "xbox-companion.conf")

            plugin = main.Plugin()

            def fake_read_sysctl(key):
                return {
                    "vm.swappiness": "10",
                    "vm.min_free_kbytes": "524288",
                    "vm.dirty_ratio": "5",
                }.get(key, "")

            with patch("main.MEMORY_SYSCTL_PATH", memory_path), patch(
                "main.ATOMIC_MANIFEST_PATH", manifest_path
            ), patch.object(plugin, "_read_sysctl", side_effect=fake_read_sysctl), patch.object(
                plugin, "_command_exists", return_value=True
            ):
                state = plugin._get_swap_protect_state()

        self.assertFalse(state["enabled"])
        self.assertTrue(state["active"])
        self.assertTrue(state["needs_reboot"])
        self.assertEqual(state["status"], "reboot-required")

    def test_kernel_param_state_uses_grub_and_atomic_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            grub_path = os.path.join(tmpdir, "grub")
            atomic_path = os.path.join(tmpdir, "xbox-companion.conf")
            state_path = os.path.join(tmpdir, "optimization-state.json")
            with open(grub_path, "w") as f:
                f.write('GRUB_CMDLINE_LINUX_DEFAULT="amd_pstate=active"\n')
            with open(atomic_path, "w") as f:
                f.write(f"{grub_path}\n")
            with open(state_path, "w") as f:
                json.dump({"kernel_params": {"amd_pstate=active": {"was_configured": False}}}, f)

            plugin = main.Plugin()

            with patch("main.GRUB_DEFAULT_PATH", grub_path), patch(
                "main.ATOMIC_MANIFEST_PATH", atomic_path
            ), patch(
                "main.OPTIMIZATION_STATE_PATH", state_path
            ), patch.object(plugin, "_is_amd_platform", return_value=True), patch.object(
                plugin, "_read_cmdline", return_value="quiet amd_pstate=active"
            ):
                state = plugin._get_kernel_param_state(
                    "kernel_amd_pstate",
                    main.GRUB_KERNEL_PARAM_OPTIONS["kernel_amd_pstate"],
                )

        self.assertTrue(state["enabled"])
        self.assertTrue(state["active"])
        self.assertFalse(state["needs_reboot"])
        self.assertEqual(state["status"], "active")

    def test_update_grub_param_refreshes_atomic_manifest_and_removes_legacy_healer(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            grub_path = os.path.join(tmpdir, "grub")
            atomic_path = os.path.join(tmpdir, "xbox-companion.conf")
            state_path = os.path.join(tmpdir, "optimization-state.json")
            legacy_script = os.path.join(tmpdir, "grub-healer.sh")
            legacy_service = os.path.join(tmpdir, "grub-healer.service")
            with open(grub_path, "w") as f:
                f.write('GRUB_CMDLINE_LINUX_DEFAULT="quiet"\n')
            for path in [legacy_script, legacy_service]:
                with open(path, "w") as f:
                    f.write("legacy\n")

            plugin = main.Plugin()

            with patch("main.GRUB_DEFAULT_PATH", grub_path), patch(
                "main.ATOMIC_MANIFEST_PATH", atomic_path
            ), patch(
                "main.OPTIMIZATION_STATE_PATH", state_path
            ), patch(
                "main.LEGACY_MANAGED_PATHS", [legacy_script, legacy_service]
            ), patch(
                "main.LEGACY_ATOMIC_PATHS", []
            ), patch.object(
                plugin, "_is_amd_platform", return_value=True
            ), patch.object(
                plugin, "_command_exists", return_value=False
            ):
                plugin._set_kernel_param_enabled("amd_pstate=active", True)

            with open(grub_path, "r") as f:
                grub_contents = f.read()
            with open(atomic_path, "r") as f:
                manifest = f.read()

        self.assertIn("quiet amd_pstate=active", grub_contents)
        self.assertIn(grub_path, manifest)
        self.assertFalse(os.path.exists(legacy_script))
        self.assertFalse(os.path.exists(legacy_service))

    def test_kernel_param_disable_preserves_preexisting_grub_setting(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            grub_path = os.path.join(tmpdir, "grub")
            atomic_path = os.path.join(tmpdir, "xbox-companion.conf")
            state_path = os.path.join(tmpdir, "optimization-state.json")
            with open(grub_path, "w") as f:
                f.write('GRUB_CMDLINE_LINUX_DEFAULT="quiet amd_pstate=active"\n')

            plugin = main.Plugin()

            with patch("main.GRUB_DEFAULT_PATH", grub_path), patch(
                "main.ATOMIC_MANIFEST_PATH", atomic_path
            ), patch(
                "main.OPTIMIZATION_STATE_PATH", state_path
            ), patch(
                "main.LEGACY_ATOMIC_PATHS", []
            ), patch(
                "main.LEGACY_MANAGED_PATHS", []
            ), patch.object(
                plugin, "_is_amd_platform", return_value=True
            ), patch.object(
                plugin, "_command_exists", return_value=False
            ):
                plugin._set_kernel_param_enabled("amd_pstate=active", True)
                plugin._set_kernel_param_enabled("amd_pstate=active", False)

            with open(grub_path, "r") as f:
                grub_contents = f.read()

        self.assertIn("amd_pstate=active", grub_contents)
        self.assertFalse(os.path.exists(atomic_path))

    def test_swap_protect_disable_restores_previous_runtime_sysctls(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_path = os.path.join(tmpdir, "memory.conf")
            atomic_path = os.path.join(tmpdir, "xbox-companion.conf")
            state_path = os.path.join(tmpdir, "optimization-state.json")
            writes = []

            plugin = main.Plugin()

            def fake_read_sysctl(key):
                return {
                    "vm.swappiness": "100",
                    "vm.min_free_kbytes": "65536",
                    "vm.dirty_ratio": "20",
                }.get(key, "")

            with patch("main.MEMORY_SYSCTL_PATH", memory_path), patch(
                "main.ATOMIC_MANIFEST_PATH", atomic_path
            ), patch(
                "main.OPTIMIZATION_STATE_PATH", state_path
            ), patch(
                "main.LEGACY_ATOMIC_PATHS", []
            ), patch(
                "main.LEGACY_MANAGED_PATHS", []
            ), patch.object(
                plugin, "_read_sysctl", side_effect=fake_read_sysctl
            ), patch.object(
                plugin, "_run_optional_command", return_value=""
            ), patch.object(
                plugin, "_write_sysctl", side_effect=lambda key, value: writes.append((key, value))
            ):
                plugin._set_swap_protect_enabled(True)
                plugin._set_swap_protect_enabled(False)

        self.assertIn(("vm.swappiness", "100"), writes)
        self.assertIn(("vm.min_free_kbytes", "65536"), writes)
        self.assertIn(("vm.dirty_ratio", "20"), writes)

    def test_unknown_optimization_is_rejected(self):
        plugin = main.Plugin()
        result = asyncio.run(plugin.set_optimization_enabled("unknown", True))
        self.assertFalse(result)

    def test_npu_blacklist_is_gated_when_no_npu_is_detected(self):
        plugin = main.Plugin()

        with patch.object(plugin, "_command_exists", return_value=True), patch.object(
            plugin,
            "_is_amd_platform",
            return_value=True,
        ), patch.object(
            plugin,
            "_amd_npu_present",
            return_value=False,
        ):
            state = plugin._get_npu_blacklist_state()

        self.assertFalse(state["available"])

    def test_optimization_states_are_exposed_as_granular_controls(self):
        plugin = main.Plugin()

        with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM), patch.object(
            plugin, "_migrate_atomic_manifest_if_needed", return_value=None
        ), patch.object(plugin, "_command_exists", return_value=True), patch.object(
            plugin, "_is_amd_platform", return_value=True
        ), patch.object(plugin, "_amd_npu_present", return_value=True), patch.object(
            plugin, "_usb_wake_control_available", return_value=True
        ), patch("main.os.path.exists", return_value=True):
            state = asyncio.run(plugin.get_optimization_states())

        keys = {item["key"] for item in state["states"]}
        self.assertIn("swap_protect", keys)
        self.assertIn("thp_madvise", keys)
        self.assertIn("npu_blacklist", keys)
        self.assertIn("usb_wake", keys)
        self.assertIn("kernel_amd_pstate", keys)
        self.assertIn("kernel_abm_off", keys)

    def test_enable_available_optimizations_skips_unavailable_controls(self):
        plugin = main.Plugin()
        calls = []

        def fake_set(enabled):
            calls.append(("swap_protect", enabled))

        with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM), patch.object(
            plugin,
            "get_optimization_states",
            return_value={
                "states": [
                    {"key": "swap_protect", "name": "Swap Protection", "available": True, "enabled": False},
                    {"key": "npu_blacklist", "name": "NPU Blacklist", "available": False, "enabled": False, "details": "No NPU"},
                    {"key": "thp_madvise", "name": "THP Madvise", "available": True, "enabled": True},
                ]
            },
        ), patch.object(
            plugin,
            "_optimization_handlers",
            return_value={"swap_protect": fake_set, "npu_blacklist": fake_set, "thp_madvise": fake_set},
        ), patch.object(
            plugin,
            "_optimization_state_readers",
            return_value={"swap_protect": lambda: {"available": True, "enabled": True}},
        ):
            result = asyncio.run(plugin.enable_available_optimizations())

        self.assertTrue(result["success"])
        self.assertEqual(calls, [("swap_protect", True)])
        self.assertEqual(result["enabled"][0]["key"], "swap_protect")
        self.assertEqual(result["skipped"][0]["key"], "npu_blacklist")
        self.assertEqual(result["already_enabled"][0]["key"], "thp_madvise")

    def test_optimization_toggle_verifies_resulting_state(self):
        plugin = main.Plugin()

        with patch.object(plugin, "_set_swap_protect_enabled", return_value=None), patch.object(
            plugin,
            "_get_swap_protect_state",
            return_value={"enabled": False},
        ):
            result = asyncio.run(plugin.set_optimization_enabled("swap_protect", True))

        self.assertFalse(result)

    def test_optimization_disable_rejects_when_runtime_is_still_active(self):
        plugin = main.Plugin()

        with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM), patch.object(
            plugin, "_set_swap_protect_enabled", return_value=None
        ), patch.object(
            plugin,
            "_get_swap_protect_state",
            return_value={"enabled": False, "active": True},
        ):
            result = asyncio.run(plugin.set_optimization_enabled("swap_protect", False))

        self.assertTrue(result)

    def test_optimization_disable_accepts_only_clean_rollback(self):
        plugin = main.Plugin()

        with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM), patch.object(
            plugin, "_set_swap_protect_enabled", return_value=None
        ), patch.object(
            plugin,
            "_get_swap_protect_state",
            return_value={"enabled": False, "active": False},
        ):
            result = asyncio.run(plugin.set_optimization_enabled("swap_protect", False))

        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
