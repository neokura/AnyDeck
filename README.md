# AnyDeck

[![Build and Package](https://github.com/neokura/AnyDeck/actions/workflows/release.yml/badge.svg)](https://github.com/neokura/AnyDeck/actions/workflows/release.yml)
[![Release](https://img.shields.io/github/v/release/neokura/AnyDeck?include_prereleases&label=alpha)](https://github.com/neokura/AnyDeck/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

AnyDeck is a root Decky Loader plugin for AMD x86 handhelds running SteamOS.

The goal is simple: make a non-Steam-Deck handheld feel closer to a Steam Deck without faking support, shipping mystery presets, or silently writing system state behind the user’s back.

Current release line: `0.2.0-alpha.13`

## What It Is

AnyDeck brings together the controls and diagnostics that matter most on a SteamOS handheld:

- native SteamOS performance profile switching
- display sync controls such as VRR and V-Sync when gamescope exposes them
- live FPS limit control
- CPU Boost, SMT, charge-limit, battery, thermal, and device diagnostics
- RGB control across supported sysfs and HID backends
- rollback-aware system optimizations with explicit per-toggle state
- a backend that is now split into focused services instead of living entirely in one monolithic file

## Project Status

This project is still alpha, but it is no longer a proof of concept.

What alpha means here:

- hardware coverage is still expanding
- some controls depend on SteamOS interfaces that can vary by build
- validated coverage is stronger on a few families than on the wider handheld market
- UI polish and wording are still moving

## Support Model

AnyDeck is intentionally SteamOS-first.

Today the plugin:

- requires SteamOS `3.8+`
- blocks Steam Deck hardware to avoid overriding Valve defaults
- only enables on official SteamOS builds, not SteamOS-like derivatives
- fully validates support on ASUS and Lenovo handhelds already mapped by the project
- exposes experimental support on other non-Steam-Deck handhelds it can identify as handheld-class devices

Important detail:

- support is capability-driven
- not every handheld exposes the same RGB, power, display, or SteamOS Manager interfaces
- the UI is supposed to show what is really available on the current machine, not what would be nice to have

## Main Features

### Handheld controls

- SteamOS performance profiles: `low-power`, `balanced`, `performance`
- VRR state
- V-Sync state
- live FPS limit through gamescope
- CPU Boost
- SMT
- battery charge limit
- RGB enabled state, color, brightness, mode, and speed

### Device and runtime information

- handheld identification and support status
- vendor, board, BIOS, CPU, GPU, kernel, and memory details
- battery capacity, health, cycles, voltage, current, and temperature
- estimated time to empty or full when enough live data exists
- current TDP, CPU temperature, GPU temperature, and GPU clock
- runtime diagnostics for host command resolution, display environment, and SteamOS Manager access
- debug log snapshots for user-visible operations

### Optional system optimizations

Each optimization is exposed as a separate toggle with explicit state:

- `LAVD Scheduler`
- `Swap Protection`
- `THP Madvise`
- `NPU Blacklist`
- `USB Wake Guard`
- `AMD P-State`
- `Disable ABM`
- `Split Lock Mitigation`
- `NMI Watchdog`
- `PCIe ASPM`

The plugin distinguishes between:

- `enabled`: AnyDeck configured the optimization
- `active`: the optimization is live at runtime
- `available`: the current machine exposes the required interface
- `needs_reboot`: configured state and running state do not match yet

## Feature Backends

| Area | Backend |
| --- | --- |
| Performance profiles | SteamOS Manager DBus |
| VRR / V-Sync | gamescope root properties through `xprop` |
| FPS limit | `gamescopectl` with property fallback for reads |
| Charge limit | SteamOS Manager DBus |
| SMT | SteamOS Manager first, kernel SMT sysfs fallback |
| CPU Boost | SteamOS Manager first, kernel cpufreq boost fallback |
| RGB | multicolor LED sysfs or handheld-specific HID backend |
| Device / battery info | DMI, power supply, kernel, and runtime files |
| Optimizations | managed files, services, sysctl, tmpfiles, ACPI wake, and GRUB |

## RGB Support

RGB support is backend-aware rather than one-size-fits-all.

Current support includes:

- multicolor LED sysfs backends
- Legion Go / Legion Go S HID backends
- ASUS Ally style HID backends

Capabilities vary by backend:

- some backends only expose `solid`
- HID backends can expose `pulse`, `rainbow`, or `spiral`
- speed controls only appear when the selected mode really supports speed

## Optimization Model

Optimizations are managed explicitly and designed to be reversible.

Managed configuration currently uses:

- atomic manifest: `/etc/atomic-update.conf.d/anydeck.conf`
- persistent optimization state: `/var/lib/anydeck/optimization-state.json`

The plugin keeps enough previous state to roll back important runtime changes where possible, including examples such as:

- prior SCX config
- prior sysctl memory values
- prior THP mode
- prior ACPI wake-enabled devices
- kernel parameters that existed before AnyDeck changed GRUB

### USB Wake Guard

`USB Wake Guard` uses the kernel ACPI wake interface directly through:

- a managed systemd unit
- a managed helper script
- a managed config file listing the ACPI USB wake devices to disable

This is intentionally more native and more durable than embedding opaque shell one-liners straight into a service definition.

## Architecture

The backend is no longer just a giant `main.py`.

Key pieces already extracted:

- [platform_support.py](platform_support.py)
- [rgb_support.py](rgb_support.py)
- [rgb_controller.py](rgb_controller.py)
- [system_info.py](system_info.py)
- [optimization_support.py](optimization_support.py)
- [optimization_ops.py](optimization_ops.py)
- [optimization_runtime.py](optimization_runtime.py)
- [performance_service.py](performance_service.py)
- [display_service.py](display_service.py)
- [state_aggregator.py](state_aggregator.py)

`main.py` still orchestrates the plugin, but much less raw logic is trapped in it than before.

## Privilege Model

AnyDeck is intended to run with Decky root mode:

```json
"flags": ["root"]
```

in [plugin.json](plugin.json).

That means:

- Decky should launch the backend as root
- protected writes can then happen directly when the user explicitly requests them

The installer now verifies the Decky `plugin_loader` services it detects,
installs a root systemd override for each one when needed, restarts them, and
refuses to treat the install as healthy unless the backend comes back with
effective root privileges for protected writes in Game Mode. It still does not
create broad `sudoers` or `polkit` rules.

## Installation

### Install the latest published alpha

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/neokura/AnyDeck/main/install.sh)
```

The installer expects:

- `curl`
- `python3`
- `unzip`
- `systemctl`
- a working Decky Loader installation

It also normalizes ownership on `~/homebrew/plugins` and the installed `AnyDeck`
directory so Decky plugin files do not get stranded under users such as
`nfsnobody` after a sudo-assisted install.

It installs to:

```text
$HOME/homebrew/plugins/AnyDeck
```

### Install a specific version

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/neokura/AnyDeck/main/install.sh) 0.2.0-alpha.13
```

## First Launch Behavior

AnyDeck does not silently apply a default tuning profile during installation or first boot.

On startup it reads real state from:

- SteamOS Manager
- gamescope
- sysfs
- DMI
- ACPI and runtime files
- runtime command probes

The UI should first describe the device as it is, then only write system state when the user asks for a change.

## Development

```bash
pnpm install
pnpm run typecheck
pnpm test
pnpm run build
```

Create a release zip locally with:

```bash
./release.sh
```

## GitHub Resources

- [Contributing guide](CONTRIBUTING.md)
- [Support guide](SUPPORT.md)
- [Security policy](SECURITY.md)
- [Issue templates](.github/ISSUE_TEMPLATE)
- [Pull request template](.github/pull_request_template.md)

## Credits

- the ASUS, Lenovo, and broader handheld Linux community for device discovery and validation
- projects like Ally Center and other handheld tools that helped map the problem space
