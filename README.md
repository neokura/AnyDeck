# Xbox Companion

[![Build and Package](https://github.com/neokura/XboxCompanion/actions/workflows/release.yml/badge.svg)](https://github.com/neokura/XboxCompanion/actions/workflows/release.yml)
[![Release](https://img.shields.io/github/v/release/neokura/XboxCompanion?include_prereleases&label=alpha)](https://github.com/neokura/XboxCompanion/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Xbox Companion is a root Decky Loader plugin for ASUS and Lenovo SteamOS handhelds.

It is designed to expose real handheld state inside the Decky quick access menu without inventing fake support, silently applying presets, or pretending a feature works when the required SteamOS interface is missing.

Current release line: `0.2.0-alpha.7`

## Project Status

This is still an alpha project, but it is no longer a small proof of concept.

Today the plugin already provides:

- native SteamOS performance profile control
- display sync controls for VRR and V-Sync when gamescope exposes them
- live FPS limit control through `gamescopectl`
- CPU Boost, SMT, charge-limit, battery, runtime, and device diagnostics
- RGB control for supported sysfs and HID backends
- rollback-aware system optimizations with explicit per-toggle state
- an architecture that is now partially split into dedicated backend services instead of keeping everything in one giant `main.py`

What alpha still means here:

- hardware coverage is intentionally conservative
- some controls depend on SteamOS interfaces that can vary by build
- UI and wording are still being refined
- no promise of broad distro compatibility outside the SteamOS target

## Goals

Xbox Companion aims to be:

- SteamOS-first: prefer native SteamOS or kernel interfaces over ad-hoc workarounds
- handheld-aware: only expose controls that make sense on the current device
- honest: unsupported features stay unavailable instead of showing a broken toggle
- reversible: optimizations track managed state and restore previous values when possible
- Decky-native: use interface patterns that feel at home in the Decky quick access menu

## What It Controls

### Core handheld controls

- SteamOS performance profiles: `low-power`, `balanced`, `performance`
- VRR state
- V-Sync state
- live FPS limit through gamescope
- CPU Boost
- SMT
- charge limit
- RGB enable/state/color/brightness/mode/speed

### Device and runtime information

- handheld identification and support status
- vendor, board, BIOS, CPU, GPU, kernel, RAM
- battery capacity, health, cycles, voltage, current, temperature
- estimated time to empty / full when enough live data is available
- current TDP, CPU temperature, GPU temperature, GPU clock
- runtime diagnostics for host command resolution, execution backend, display environment, and SteamOS Manager bus access
- debug log snapshots for user-visible operations

### Optional system optimizations

Each optimization is exposed as an independent user-facing control with explicit state:

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

- `enabled`: the optimization is configured by Xbox Companion
- `active`: the optimization is live at runtime
- `available`: the current handheld and SteamOS environment expose the required interface
- `needs_reboot`: configuration and active runtime state do not match yet

## Supported Target

Xbox Companion is currently built for:

- SteamOS `3.8+`
- ASUS handhelds running SteamOS
- Lenovo handhelds running SteamOS

The plugin intentionally blocks:

- Steam Deck hardware
- non-SteamOS distributions such as Bazzite or ChimeraOS
- unsupported vendor hardware

This is not because those systems are impossible to support forever, but because the plugin currently relies on SteamOS-specific assumptions around:

- SteamOS Manager DBus
- gamescope integration
- host command layout
- system paths and managed-file behavior

## Feature Backends

| Area | Backend |
| --- | --- |
| Performance profiles | SteamOS Manager DBus |
| VRR / V-Sync | gamescope root properties through `xprop` |
| FPS limit | `gamescopectl` live reads/writes, with gamescope property fallback for reads |
| Charge limit | SteamOS Manager DBus |
| SMT | SteamOS Manager first, kernel SMT sysfs fallback |
| CPU Boost | SteamOS Manager first, kernel cpufreq boost fallback |
| RGB | multicolor LED sysfs or handheld-specific HID backend |
| Battery / device info | DMI, power supply, kernel/runtime files |
| Optimizations | managed files, services, sysctl, tmpfiles, ACPI wake, GRUB |

## RGB Support

RGB support is no longer just a simple LED write.

The plugin currently supports:

- sysfs multicolor LED paths when the handheld exposes them
- Legion Go / Legion Go S style HID control
- ASUS Ally style HID control

Capabilities vary by backend:

- some backends only support `solid`
- HID backends can expose `pulse`, `rainbow`, and `spiral`
- speed controls are only shown when the active mode actually supports speed

The UI mirrors real backend capabilities instead of assuming every handheld supports the same RGB modes.

## Optimization Model

Optimizations are managed explicitly and are designed to be reversible.

Managed configuration currently uses:

- consolidated atomic manifest:
  `/etc/atomic-update.conf.d/xbox-companion.conf`
- persistent optimization state:
  `/var/lib/xbox-companion/optimization-state.json`

The plugin tracks previous values where runtime rollback matters, including examples such as:

- prior SCX config
- previous sysctl memory values
- previous THP mode
- previous ACPI wake-enabled devices
- kernel parameters that existed before Xbox Companion touched GRUB

### USB Wake Guard

`USB Wake Guard` was recently hardened.

It no longer relies on a fragile one-liner embedded in the service unit. It now manages:

- a dedicated systemd unit
- a dedicated helper script
- a managed config file listing the ACPI USB/XHC wake devices to disable

This keeps the behavior more native, easier to inspect, and more robust across future changes.

## Privilege Model

This is the part that matters most for real deployments.

The plugin declares Decky root mode through:

```json
"flags": ["_root"]
```

in [plugin.json](plugin.json).

That means the intended runtime is:

- Decky launches the backend with root privileges
- the plugin writes directly to protected system paths when requested by the user

The installer does **not** create extra `sudoers` or `polkit` rules. It only:

- installs the plugin files
- fixes ownership
- restarts Decky Loader when possible

So the plugin depends on Decky's runtime behavior for real root execution. If the backend is not actually running as root, the code can attempt `sudo -n` for protected operations, but this is only a fallback path and should not be treated as the primary deployment model.

## Installation

### Install latest published alpha

Open Konsole on the handheld and run:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/neokura/XboxCompanion/main/install.sh)
```

The installer expects:

- `curl`
- `python3`
- `unzip`
- a working Decky installation

It installs to:

```text
$HOME/homebrew/plugins/Xbox Companion
```

### Install a specific version

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/neokura/XboxCompanion/main/install.sh) 0.2.0-alpha.7
```

## First Launch Behavior

Xbox Companion does not push a hidden default profile at install time or first boot.

On startup it reads real state from:

- SteamOS Manager
- gamescope
- sysfs
- DMI
- ACPI/runtime files
- systemd/runtime command probes

The UI is supposed to reflect what the handheld is already doing, then only write system state when the user explicitly changes something.

## Current Backend Architecture

The project started as a much larger monolith and has been partially decomposed.

`main.py` is still the Decky backend entrypoint, but major logic is now split out into dedicated support modules:

- [platform_support.py](platform_support.py): platform detection and SteamOS support checks
- [rgb_support.py](rgb_support.py): RGB normalization, capabilities, and HID payload building
- [rgb_controller.py](rgb_controller.py): RGB orchestration
- [system_info.py](system_info.py): device and battery information population
- [performance_service.py](performance_service.py): performance profile orchestration
- [display_service.py](display_service.py): VRR / V-Sync / FPS flows
- [optimization_support.py](optimization_support.py): pure optimization logic helpers
- [optimization_ops.py](optimization_ops.py): optimization persistence and managed file operations
- [optimization_runtime.py](optimization_runtime.py): runtime helpers for services, sysctl, THP, ACPI, kernel params
- [state_aggregator.py](state_aggregator.py): dashboard and information view aggregation

That split does not make the project “finished”, but it does make it much easier to keep extending without turning every change into a `main.py` regression risk.

## Frontend State

The frontend lives in [src/index.tsx](src/index.tsx).

Recent UI work brought the plugin closer to a more Decky-native feel:

- large custom action cards were replaced in several places with `DialogButton`-style interactions
- performance mode buttons now use new handheld-oriented icons
- performance, RGB, optimization, and information views share more consistent action-button patterns

## Known Limits

Current limitations that are intentional or not fully solved yet:

- support is limited to SteamOS on ASUS/Lenovo handhelds
- some controls depend on host commands like `gamescopectl`, `xprop`, `busctl`, or `update-grub`
- `USB Wake Guard` and several optimizations still depend on system interfaces that can vary across firmware/SteamOS updates
- root execution is expected from Decky; the installer does not provision a separate privilege model
- no broad hardware abstraction layer exists yet beyond the currently supported targets

## Troubleshooting

If the plugin does not show up in Decky:

```bash
sudo systemctl restart plugin_loader
```

If a control is unavailable, check the Information view inside the plugin first. It exposes:

- platform support state
- hardware controls availability
- display/runtime diagnostics
- command resolution state
- SteamOS Manager bus status
- debug operation log

Typical reasons for unavailable controls:

- the current device is blocked by platform guard
- SteamOS Manager is missing the expected DBus property
- gamescope does not expose the required root property
- `gamescopectl` is unavailable or cannot return a live value
- the handheld does not expose the required sysfs path
- the backend is not actually running with sufficient privileges

## Development

Install dependencies:

```bash
pnpm install
```

Run the standard checks:

```bash
pnpm run typecheck
pnpm test
pnpm run build
```

## Packaging And Release

The local release script builds and packages a Decky-ready zip:

```bash
./release.sh
```

For the current line:

```bash
./release.sh 0.2.0-alpha.7
```

The release zip contains:

- `dist/`
- `main.py`
- `plugin.json`
- `package.json`
- `README.md`
- `LICENSE`
- `icons/`

GitHub Actions also packages the plugin on CI and attaches release zips to tagged releases.

To publish the matching GitHub pre-release tag:

```bash
git tag v0.2.0-alpha.7
git push origin v0.2.0-alpha.7
```

## Thanks

Thanks to:

- [Decky Loader](https://decky.xyz/) and the Decky ecosystem
- the SteamOS and gamescope interfaces that make native control possible
- the ASUS and Lenovo handheld community for path discovery, validation, and testing
- projects like Ally Center and other handheld control tools that helped map the problem space

## License

MIT. See [LICENSE](LICENSE).
