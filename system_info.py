"""Helpers for device and battery information collection."""

import glob
import math
import os


def default_device_info() -> dict:
    return {
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


def default_battery_info(charge_full_percent: int) -> dict:
    return {
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
        "charge_limit": charge_full_percent,
        "time_to_empty": "Unknown",
        "time_to_full": "Unknown",
    }


def get_battery_path(read_file, direct_path: str, glob_patterns: list[str]) -> str:
    if direct_path and os.path.exists(direct_path):
        return direct_path

    candidates = []
    for pattern in glob_patterns:
        candidates.extend(sorted(glob.glob(pattern)))

    for path in candidates:
        type_path = os.path.join(path, "type")
        if read_file(type_path, "").lower() == "battery":
            return path

    return candidates[0] if candidates else ""


def format_duration_hours(hours: float) -> str:
    if not math.isfinite(hours) or hours <= 0:
        return "Unknown"

    total_minutes = max(1, int(round(hours * 60)))
    whole_hours, minutes = divmod(total_minutes, 60)
    if whole_hours == 0:
        return f"{minutes}m"
    if minutes == 0:
        return f"{whole_hours}h"
    return f"{whole_hours}h {minutes}m"


def estimate_battery_times(battery: dict, charge_full_percent: int) -> tuple[str, str]:
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
        max(float(battery.get("charge_limit", charge_full_percent) or 0), 0),
        100,
    )
    target_energy = full_capacity * target_percent / 100
    status = str(battery.get("status", "") or "").strip().lower()

    time_to_empty = "Unknown"
    time_to_full = "Unknown"

    if status == "discharging" and stored_energy > 0:
        time_to_empty = format_duration_hours(stored_energy / power)
    elif status == "charging" and target_energy > stored_energy:
        time_to_full = format_duration_hours((target_energy - stored_energy) / power)

    return time_to_empty, time_to_full


def populate_device_info(
    info: dict,
    *,
    dmi_path: str,
    os_release_values: dict,
    read_text_file,
    read_cpu_model,
    read_kernel_version,
    read_memory_total_gb,
    get_device_metadata_fn,
    get_platform_support_fn,
    get_steamos_version_fn,
) -> dict:
    dmi_files = {
        "model": "product_name",
        "product_name": "product_name",
        "product_family": "product_family",
        "sys_vendor": "sys_vendor",
        "board_name": "board_name",
        "bios_version": "bios_version",
        "serial": "product_serial",
    }

    for key, filename in dmi_files.items():
        value = read_text_file(os.path.join(dmi_path, filename))
        if value:
            info[key] = value

    device_metadata = get_device_metadata_fn(
        board_name=info.get("board_name", "Unknown"),
        product_name=info.get("model", "Unknown"),
        sys_vendor=info.get("sys_vendor", "Unknown"),
        product_family=info.get("product_family", "Unknown"),
    )
    platform_support = get_platform_support_fn(
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
    info["steamos_version"] = get_steamos_version_fn(os_release_values)

    cpu_model = read_cpu_model()
    if cpu_model:
        info["cpu"] = cpu_model

    kernel_version = read_kernel_version()
    if kernel_version:
        info["kernel"] = kernel_version

    memory_total_gb = read_memory_total_gb()
    if memory_total_gb:
        info["memory_total"] = memory_total_gb

    info["gpu"] = "AMD Radeon 780M" if "Z1" in info.get("cpu", "") else "AMD Radeon Graphics"
    return info


def populate_battery_info(
    battery: dict,
    *,
    battery_path: str,
    charge_full_percent: int,
    read_text_file,
) -> dict:
    if not battery_path:
        return battery

    battery["present"] = True

    battery_files = {
        "status": "status",
        "capacity": "capacity",
        "cycle_count": "cycle_count",
        "voltage_now": "voltage_now",
        "current_now": "current_now",
        "energy_full_design": "energy_full_design",
        "energy_full": "energy_full",
    }

    for key, filename in battery_files.items():
        value = read_text_file(os.path.join(battery_path, filename))
        if not value:
            continue
        if key == "status":
            battery["status"] = value
        elif key == "capacity":
            battery["capacity"] = int(value)
        elif key == "cycle_count":
            battery["cycle_count"] = int(value)
        elif key == "voltage_now":
            battery["voltage"] = int(value) / 1000000
        elif key == "current_now":
            battery["current"] = int(value) / 1000000
        elif key == "energy_full_design":
            battery["design_capacity"] = int(value) / 1000000
        elif key == "energy_full":
            battery["full_capacity"] = int(value) / 1000000

    if battery["design_capacity"] > 0:
        battery["health"] = round((battery["full_capacity"] / battery["design_capacity"]) * 100, 1)

    temp_value = read_text_file(os.path.join(battery_path, "temp"))
    if temp_value:
        battery["temperature"] = int(temp_value) / 10

    battery["time_to_empty"], battery["time_to_full"] = estimate_battery_times(
        battery,
        charge_full_percent,
    )
    return battery
