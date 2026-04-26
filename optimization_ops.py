"""Operational helpers for optimization persistence and managed files."""

import json
import os

from optimization_support import updated_grub_contents


def refresh_atomic_manifest(
    *,
    manifest_path: str,
    entries: list[str],
    write_managed_file,
    remove_file,
    cleanup_legacy_managed_files,
    cleanup_legacy_atomic_manifests,
) -> None:
    cleanup_legacy_managed_files()
    if entries:
        write_managed_file(manifest_path, "\n".join(entries) + "\n")
    else:
        remove_file(manifest_path)
    cleanup_legacy_atomic_manifests()


def migrate_atomic_manifest_if_needed(*, legacy_atomic_paths: list[str], host_file_exists, refresh_atomic_manifest_fn) -> None:
    if any(host_file_exists(path) for path in legacy_atomic_paths):
        refresh_atomic_manifest_fn()


def remove_managed_file(
    *,
    path: str,
    needles: list[str] | None,
    removed_files: list[str],
    skipped_files: list[str],
    errors: list[str],
    host_file_exists,
    file_contains_all,
    route_path_via_host,
    optimization_state_path: str,
    needs_privilege_escalation_fn,
    run_command,
) -> None:
    try:
        if not host_file_exists(path):
            return

        if needles and not file_contains_all(path, needles):
            skipped_files.append(path)
            return

        if route_path_via_host(path) or needs_privilege_escalation_fn(optimization_state_path):
            success, error = run_command(["rm", "-f", path], use_sudo=True)
            if not success:
                raise RuntimeError(error)
        else:
            os.remove(path)
        removed_files.append(path)
    except Exception as e:
        errors.append(f"{path}: {e}")


def read_optimization_state(*, optimization_state_path: str, host_file_exists, read_text_file, warn) -> dict:
    try:
        if not host_file_exists(optimization_state_path):
            return {}
        data = json.loads(read_text_file(optimization_state_path, "{}"))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        warn(f"Failed to read optimization state: {e}")
        return {}


def write_optimization_state(
    state: dict,
    *,
    optimization_state_path: str,
    route_path_via_host,
    needs_privilege_escalation_fn,
    run_command,
    write_file,
    remove_file,
    warn,
) -> None:
    try:
        if not state:
            remove_file(optimization_state_path)
            return
        content = json.dumps(state, indent=2, sort_keys=True) + "\n"
        directory = os.path.dirname(optimization_state_path)
        if route_path_via_host(optimization_state_path) or needs_privilege_escalation_fn(optimization_state_path):
            if directory:
                run_command(["mkdir", "-p", directory], use_sudo=True)
            write_file(optimization_state_path, content, use_sudo=True)
            return
        os.makedirs(directory, exist_ok=True)
        with open(optimization_state_path, "w") as f:
            f.write(content)
    except Exception as e:
        warn(f"Failed to write optimization state: {e}")


def pop_optimization_state_value(*, key: str, read_optimization_state_fn, write_optimization_state_fn):
    state = read_optimization_state_fn()
    value = state.pop(key, None)
    write_optimization_state_fn(state)
    return value


def update_grub_param(
    *,
    grub_default_path: str,
    param: str,
    enabled: bool,
    host_file_exists,
    read_text_file,
    write_file,
    refresh_atomic_manifest_fn,
    command_exists,
    run_command,
    warn,
) -> str:
    if not host_file_exists(grub_default_path):
        return "GRUB config not found"

    try:
        contents = read_text_file(grub_default_path, "")
        success, error = write_file(
            grub_default_path,
            updated_grub_contents(contents, param, enabled),
            use_sudo=True,
        )
        if not success:
            return error

        refresh_atomic_manifest_fn()

        if command_exists("update-grub"):
            success, error = run_command(["update-grub"], use_sudo=True)
            if not success:
                warn(f"Optional command failed: update-grub: {error}")
                return error
            return ""
        return "update-grub is not installed"
    except Exception as e:
        return str(e)
