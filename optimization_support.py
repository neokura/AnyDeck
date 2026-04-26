"""Pure helpers for system optimization state and config shaping."""


def atomic_managed_entries(
    checks: list[tuple[str, list[str]]],
    *,
    file_contains_all,
    file_contains_any,
    grub_default_path: str,
    kernel_params: list[str],
) -> list[str]:
    entries = [path for path, needles in checks if file_contains_all(path, needles)]
    if kernel_params and file_contains_any(grub_default_path, kernel_params):
        entries.append(grub_default_path)
    return entries


def optimization_state(
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


def managed_kernel_params_from_state(state: dict, known_params: set[str]) -> list[str]:
    params = state.get("kernel_params", {})
    if not isinstance(params, dict):
        return []
    return [param for param in params if param in known_params]


def remember_kernel_param_state(state: dict, param: str, was_configured: bool) -> dict:
    next_state = dict(state)
    params = next_state.get("kernel_params", {})
    if not isinstance(params, dict):
        params = {}
    else:
        params = dict(params)
    params.setdefault(param, {"was_configured": was_configured})
    next_state["kernel_params"] = params
    return next_state


def forget_kernel_param_state(state: dict, param: str) -> tuple[dict, bool]:
    next_state = dict(state)
    params = next_state.get("kernel_params", {})
    if not isinstance(params, dict):
        return next_state, False
    params = dict(params)
    data = params.pop(param, {})
    if params:
        next_state["kernel_params"] = params
    else:
        next_state.pop("kernel_params", None)
    return next_state, isinstance(data, dict) and data.get("was_configured", False)


def updated_grub_contents(contents: str, param: str, enabled: bool) -> str:
    lines = []
    changed = False

    for line in contents.splitlines():
        if line.startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
            prefix, value = line.split("=", 1)
            raw = value.strip().strip('"').strip("'")
            parts = [part for part in raw.split() if part != param]
            if enabled:
                parts.append(param)
            line = f'{prefix}="{" ".join(parts).strip()}"'
            changed = True
        lines.append(line)

    if not changed and enabled:
        lines.append(f'GRUB_CMDLINE_LINUX_DEFAULT="{param}"')

    return "\n".join(lines) + "\n"
