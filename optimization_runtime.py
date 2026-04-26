"""Runtime helpers for system optimization checks and actions."""

import glob
import os


def systemctl(*args: str, run_command, warn) -> str:
    success, error = run_command(["systemctl", *args], use_sudo=True)
    if not success:
        warn(f"Optional command failed: systemctl {' '.join(args)}: {error}")
        return error
    return ""


def service_exists(service: str, *, host_file_exists, runtime, default_timeout: int) -> bool:
    if host_file_exists(f"/etc/systemd/system/{service}") or host_file_exists(f"/usr/lib/systemd/system/{service}"):
        return True

    try:
        result = runtime.run(
            ["systemctl", "list-unit-files", service, "--no-legend"],
            timeout=5,
            env=runtime.host_env(),
        )
        return result.returncode == 0 and service in result.stdout
    except Exception:
        return False


def service_enabled(service: str, *, runtime, default_timeout: int) -> bool:
    try:
        result = runtime.run(
            ["systemctl", "is-enabled", service],
            timeout=default_timeout,
            env=runtime.host_env(),
        )
        return result.returncode == 0 and result.stdout.strip() == "enabled"
    except Exception:
        return False


def service_active(service: str, *, runtime, default_timeout: int) -> bool:
    try:
        result = runtime.run(
            ["systemctl", "is-active", service],
            timeout=default_timeout,
            env=runtime.host_env(),
        )
        return result.returncode == 0 and result.stdout.strip() == "active"
    except Exception:
        return False


def read_sysctl(key: str, *, runtime, default_timeout: int) -> str:
    result = runtime.run(
        ["sysctl", "-n", key],
        timeout=default_timeout,
        env=runtime.host_env(),
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def write_sysctl(key: str, value: str, *, run_command) -> None:
    run_command(["sysctl", "-w", f"{key}={value}"], use_sudo=True)


def is_amd_platform(*, read_file) -> bool:
    return "AMD" in read_file("/proc/cpuinfo", "").upper()


def amd_npu_present(*, command_exists, run_command_output) -> bool:
    if os.path.exists("/sys/module/amdxdna"):
        return True

    for device in glob.glob("/sys/bus/pci/devices/*"):
        module_path = os.path.join(device, "driver", "module")
        try:
            if os.path.basename(os.path.realpath(module_path)) == "amdxdna":
                return True
        except Exception:
            continue

    if command_exists("lspci"):
        success, output = run_command_output(["lspci", "-nn"])
        if success:
            normalized = output.upper()
            return "XDNA" in normalized or "NPU" in normalized or "AI ENGINE" in normalized

    return False


def usb_wake_control_available(*, acpi_wakeup_path: str, command_exists) -> bool:
    return os.path.exists(acpi_wakeup_path) and command_exists("systemctl")


def read_cmdline() -> str:
    try:
        with open("/proc/cmdline", "r") as f:
            return f.read()
    except Exception:
        return ""


def parse_acpi_wakeup_entries(content: str) -> list[dict]:
    entries = []
    for raw_line in content.splitlines():
        parts = raw_line.split()
        if len(parts) < 3:
            continue
        status_token = parts[2]
        enabled = status_token in {"*enabled", "enabled"}
        entries.append(
            {
                "name": parts[0],
                "sleep_state": parts[1],
                "status": "enabled" if enabled else status_token.lstrip("*").lower(),
                "enabled": enabled,
                "raw": raw_line,
            }
        )
    return entries


def read_acpi_wakeup_entries(*, acpi_wakeup_path: str) -> list[dict]:
    try:
        with open(acpi_wakeup_path, "r") as f:
            return parse_acpi_wakeup_entries(f.read())
    except Exception:
        return []


def usb_wake_candidate_devices(*, entries: list[dict]) -> list[str]:
    devices = []
    for entry in entries:
        name = entry.get("name", "")
        if name.startswith("XHC") or name.startswith("USB"):
            devices.append(name)
    return devices


def read_acpi_wake_enabled_devices(*, acpi_wakeup_path: str) -> list[str]:
    return [
        entry["name"]
        for entry in read_acpi_wakeup_entries(acpi_wakeup_path=acpi_wakeup_path)
        if entry.get("enabled", False) and entry.get("name", "").startswith(("XHC", "USB"))
    ]


def set_acpi_wake_devices(devices: list[str], *, acpi_wakeup_path: str, write_file, warn) -> None:
    for device in devices:
        try:
            success, error = write_file(
                acpi_wakeup_path,
                device,
                use_sudo=True,
            )
            if not success:
                raise RuntimeError(error)
        except Exception as e:
            warn(f"Failed to restore ACPI wake device {device}: {e}")


def thp_is_madvise(*, thp_enabled_path: str) -> bool:
    try:
        if not os.path.exists(thp_enabled_path):
            return False
        with open(thp_enabled_path, "r") as f:
            return "[madvise]" in f.read()
    except Exception:
        return False


def read_thp_mode(*, thp_enabled_path: str) -> str:
    try:
        if not os.path.exists(thp_enabled_path):
            return ""
        with open(thp_enabled_path, "r") as f:
            for token in f.read().split():
                if token.startswith("[") and token.endswith("]"):
                    return token.strip("[]")
    except Exception:
        return ""
    return ""


def write_thp_mode(mode: str, *, thp_enabled_path: str, write_file, warn) -> None:
    if not mode:
        return
    try:
        success, error = write_file(thp_enabled_path, mode, use_sudo=True)
        if not success:
            raise RuntimeError(error)
    except Exception as e:
        warn(f"Failed to set THP mode {mode}: {e}")


def kernel_param_active(param: str, *, read_cmdline_fn) -> bool:
    return param in read_cmdline_fn()


def grub_param_configured(param: str, *, grub_default_path: str, file_contains_all) -> bool:
    return file_contains_all(grub_default_path, [param])
