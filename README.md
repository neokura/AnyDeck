# Xbox Companion

[![Build and Package](https://github.com/neokura/XboxCompanion/actions/workflows/release.yml/badge.svg)](https://github.com/neokura/XboxCompanion/actions/workflows/release.yml)
[![Release](https://img.shields.io/github/v/release/neokura/XboxCompanion?include_prereleases&label=alpha)](https://github.com/neokura/XboxCompanion/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Xbox Companion is an alpha Decky Loader plugin for ASUS and Lenovo handhelds running SteamOS 3.8 or newer. It brings the most useful system controls into the Decky quick access menu while staying close to SteamOS-native APIs.

The goal is simple: install it, open Decky, and see controls that reflect the real state of the handheld. No default profile is applied on first launch, no hidden preset is pushed silently, and unsupported features stay disabled instead of pretending they work.

Current alpha: `0.2.0-alpha.6`

## What It Does

- Uses the three native SteamOS performance profiles: `low-power`, `balanced`, and `performance`.
- Reads and toggles VRR and V-Sync through gamescope root properties when available.
- Reads and sets live framerate limits through `gamescopectl`.
- Reads and toggles CPU boost when the kernel exposes the control.
- Reads and toggles SMT through SteamOS Manager first, then the kernel SMT interface when needed.
- Reads battery status, health, charge limit, voltage, current, capacity, and estimated charge or discharge timing when enough live data is available.
- Reads RGB state from compatible LED sysfs paths and applies preset colors.
- Shows device, BIOS, kernel, CPU, GPU, memory, temperature, GPU clock, and current TDP information.
- Offers optional system optimizations as separate end-user controls with visible compatibility and rollback-aware state.

## Install From SteamOS

Open Konsole on the handheld and run:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/neokura/XboxCompanion/main/install.sh)
```

The installer checks for Decky Loader before it touches the plugin directory. It requires `curl`, `python3`, and `unzip`.

If Decky is missing, the installer stops and offers to open:

```text
https://decky.xyz/
```

Install Decky first, then rerun the command above.

When Decky is present, the installer resolves the newest published GitHub release zip, including alpha pre-releases, validates the Decky plugin layout, and installs it to:

```text
$HOME/homebrew/plugins/Xbox Companion
```

Then it restarts Decky Loader when possible. Xbox Companion should appear in the Decky quick access menu after the restart. The installer keeps the extracted file modes as-is and only fixes ownership on the plugin directory after copying.

To install a specific published version instead of the newest one:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/neokura/XboxCompanion/main/install.sh) 0.2.0-alpha.6
```

## Supported Platforms

Xbox Companion intentionally uses runtime checks instead of a hardcoded model whitelist. A handheld is supported only when all of these are true:

- SteamOS 3.8 or newer
- ASUS or Lenovo handheld hardware
- Not Steam Deck hardware
- Required system interfaces exist for the specific feature

Steam Deck is blocked to avoid changing Valve hardware defaults. Bazzite, ChimeraOS, and non-SteamOS distributions are also blocked for now because the system assumptions are tuned for SteamOS on ASUS and Lenovo handhelds.

## Feature Availability

Each control has its own compatibility gate. This means one missing interface should not break the whole plugin.

| Area | Backend used | Frontend behavior |
| --- | --- | --- |
| Performance profiles | SteamOS Manager DBus | Shows only native SteamOS modes and marks the active one |
| VRR | gamescope `GAMESCOPE_VRR_*` atoms through `xprop` | Shows unavailable, incompatible, enabled, disabled, or active |
| V-Sync | gamescope allow-tearing atom through `xprop` | Shows the current real state and toggles the inverse allow-tearing value |
| FPS limit | `gamescopectl debug_get_fps_limit` and `debug_set_fps_limit` | Shows live limit when readable, otherwise disables writes that cannot be verified |
| CPU boost | `/sys/devices/system/cpu/cpufreq/boost` | Mirrors the kernel value |
| SMT | SteamOS Manager DBus, then `/sys/devices/system/cpu/smt/control` | Mirrors whichever supported backend is available |
| Charge limit | SteamOS Manager DBus | Mirrors current SteamOS charge limit state |
| RGB | LED `brightness`, `multi_index`, and `multi_intensity` sysfs files | Mirrors ASUS Ally-style and Lenovo-style multicolor LEDs when exposed |
| Optimizations | managed system files, services, sysctl, tmpfiles, and GRUB | Shows configured, active, off, unavailable, or reboot-required state per option |

ASUS and Lenovo handhelds are treated as first-class targets. Device detection accepts common ROG Ally and Legion identifiers, battery discovery scans compatible `BAT*` and `CMB*` power-supply entries instead of assuming `BAT0`, and RGB discovery only enables the control when a compatible LED backend is detected. Legion Go S and Legion Go/Go 2 RGB support follows the HID protocol used by HueSync, with sysfs multicolor LEDs kept as a fallback when exposed by the kernel.

## First Launch Behavior

Xbox Companion does not apply a default configuration during installation or first launch.

On startup it reads the handheld state from SteamOS, gamescope, kernel sysfs, DBus, and systemd. The UI should represent the console as it is, not as a local defaults file says it should be.

The plugin may write system state only when you explicitly toggle a control.

## Safety Model

This is a root Decky plugin. Treat it like system software.

Xbox Companion avoids direct manual TDP writes and prefers SteamOS-native APIs. Optional optimizations write managed files under known paths, register them through one consolidated atomic manifest at:

```text
/etc/atomic-update.conf.d/xbox-companion.conf
```

Runtime rollback state is stored separately at:

```text
/var/lib/xbox-companion/optimization-state.json
```

Optimization toggles report whether they are active, configured, unavailable, or waiting for reboot. Each option is separated so users can enable only the controls they actually want:

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

Compatibility is checked per option. For example, the NPU blacklist is unavailable unless an AMD NPU is detected, USB wake control requires `/proc/acpi/wakeup`, THP requires the kernel THP interface, and kernel parameter controls require an AMD platform with a writable GRUB configuration.

Kernel parameter options are handled directly through `/etc/default/grub` and the SteamOS atomic manifest. Xbox Companion does not install a background GRUB repair script, does not auto-reboot the device, and reports the difference between configured state and the currently active `/proc/cmdline` state so reboot-required controls stay visible. If a kernel parameter already existed before Xbox Companion enabled it, disabling that option preserves the user's original GRUB setting.

Rollback is explicit. Disabling an optimization removes only Xbox Companion-managed files, refreshes the atomic manifest, and restores remembered runtime values where SteamOS does not automatically do that for us, such as the previous SCX config, sysctl memory tuning, THP mode, and USB wake devices.

The Optimizations view also includes an `Enable Available Optimizations` action. It only enables options that are available on the current SteamOS handheld, skips incompatible controls, and leaves already-enabled controls untouched.

## Troubleshooting

If the plugin does not appear:

```bash
sudo systemctl restart plugin_loader
```

If the installer says Decky is missing, install Decky first:

```text
https://decky.xyz/
```

If a specific control is disabled, open the Information view inside Xbox Companion. It shows platform support, available controls, display state, battery state, optimization state, and hardware diagnostics.

Common reasons for disabled controls:

- `gamescopectl` is not installed or cannot read the live FPS limit.
- gamescope root properties are not exposed on the current display.
- SteamOS Manager does not expose the expected DBus property.
- The handheld does not expose the required kernel sysfs path.
- The device or OS is intentionally blocked by the platform guard.

## Development

Install dependencies:

```bash
pnpm install
```

Run checks:

```bash
pnpm run typecheck
pnpm test
pnpm run build
```

Build output is written to `dist/`.

## Release Pipeline

GitHub Actions runs on pull requests, pushes to `main`, manual dispatches, and version tags.

The workflow:

- installs dependencies with pnpm
- runs TypeScript type checks
- runs Python unit tests
- builds the Decky frontend as part of the packaging step
- packages a Decky-ready release zip with a top-level `xbox-companion/` directory
- uploads the zip as a workflow artifact
- attaches the zip to a GitHub Release when a `v*` tag is pushed
- marks tagged pre-release versions such as `v0.2.0-alpha.6` as GitHub pre-releases

The release package contains:

- `xbox-companion/dist/index.js`
- `main.py`
- `plugin.json`
- `package.json`
- `README.md`
- `LICENSE`
- `icons/`

Source maps are excluded from published release zips.

To publish a tagged alpha:

```bash
git tag v0.2.0-alpha.6
git push origin v0.2.0-alpha.6
```

## Thanks

Xbox Companion builds on ideas, tooling, and platform work from the wider handheld Linux community. Thanks especially to:

- [Ally Center](https://github.com/PixelAddictUnlocked/allycenter) by PixelAddictUnlocked for inspiration around handheld control-center workflows.
- [Decky Loader](https://decky.xyz/) and the Decky plugin ecosystem.
- SteamOS and the SteamOS Manager interfaces that make native system control possible.
- The Steam Deck, ASUS ROG Ally, Lenovo Legion Go, and broader SteamOS handheld communities for documentation, testing, and shared discoveries.

## License

MIT. See [LICENSE](LICENSE).
