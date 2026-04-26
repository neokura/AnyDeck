# Contributing to AnyDeck

Thanks for helping with AnyDeck.

## What Helps Most

- handheld-specific validation on SteamOS
- logs and reproduction steps for broken controls
- careful reports about which interfaces are truly exposed on a device
- focused refactors that reduce backend coupling without changing behavior
- tests for regressions in optimizations, RGB backends, and SteamOS Manager integration

## Development Workflow

1. Install dependencies with `pnpm install`.
2. Run `pnpm run typecheck`.
3. Run `pnpm test`.
4. Run `pnpm run build`.
5. Keep changes scoped and explain the user-facing impact clearly.

## Architecture Notes

The project is moving away from a giant all-in-one backend.

If you are touching a larger area, prefer extending the extracted modules first:

- `platform_support.py`
- `rgb_controller.py`
- `rgb_support.py`
- `system_info.py`
- `optimization_support.py`
- `optimization_ops.py`
- `optimization_runtime.py`
- `performance_service.py`
- `display_service.py`
- `state_aggregator.py`

## Product Rules

- Do not fake hardware support.
- Do not silently apply presets.
- Prefer SteamOS-native and kernel-native interfaces over ad-hoc workarounds.
- Keep optimizations reversible where possible.
- When adding a new control, surface its real availability instead of forcing it visible everywhere.

## Pull Requests

- Describe the tested device and SteamOS version when relevant.
- Mention whether the change affects validated support or experimental support.
- Include screenshots for UI changes when possible.
- Call out any root-required behavior changes explicitly.
