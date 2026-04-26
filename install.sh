#!/bin/bash
# AnyDeck - Installation Script
# Author: neokura
set -euo pipefail

PLUGIN_NAME="AnyDeck"
PLUGIN_SLUG="anydeck"
PLUGIN_DIR="$HOME/homebrew/plugins/$PLUGIN_NAME"
PLUGIN_BASE_DIR="$HOME/homebrew/plugins"
REPO_OWNER="neokura"
REPO_NAME="AnyDeck"
REQUESTED_VERSION="${1:-${ANYDECK_VERSION:-}}"
TEMP_FILES=()
cleanup() {
    if [ ${#TEMP_FILES[@]} -gt 0 ]; then
        echo "Cleaning up temporary files..."
        for file in "${TEMP_FILES[@]}"; do
            rm -rf "$file" 2>/dev/null || true
        done
    fi
}
trap cleanup EXIT

PLUGIN_LOADER_SYSTEMD_DIR="$HOME/homebrew/services/.systemd"
PLUGIN_LOADER_UNIT="$PLUGIN_LOADER_SYSTEMD_DIR/plugin_loader.service"
PLUGIN_LOADER_SERVICE_NAMES=()
PLUGIN_LOADER_REGISTERED_SERVICES=()

discover_plugin_loader_services() {
    local unit_path
    local service_name

    PLUGIN_LOADER_SERVICE_NAMES=()

    if [ -d "$PLUGIN_LOADER_SYSTEMD_DIR" ]; then
        while IFS= read -r unit_path; do
            [ -n "$unit_path" ] || continue
            service_name="$(basename "$unit_path" .service)"
            if [[ "$service_name" == *"-backup" ]]; then
                continue
            fi
            PLUGIN_LOADER_SERVICE_NAMES+=("$service_name")
        done < <(find "$PLUGIN_LOADER_SYSTEMD_DIR" -maxdepth 1 -type f -name 'plugin_loader*.service' | sort)
    fi

    if [ ${#PLUGIN_LOADER_SERVICE_NAMES[@]} -eq 0 ]; then
        PLUGIN_LOADER_SERVICE_NAMES=("plugin_loader")
    fi
}

filter_known_plugin_loader_services() {
    local filtered=()
    local service_name
    local load_state

    for service_name in "${PLUGIN_LOADER_SERVICE_NAMES[@]}"; do
        load_state="$(systemctl show "${service_name}.service" -p LoadState --value 2>/dev/null || true)"
        if [ -z "$load_state" ] || [ "$load_state" = "not-found" ]; then
            continue
        fi
        filtered+=("$service_name")
    done

    if [ ${#filtered[@]} -gt 0 ]; then
        PLUGIN_LOADER_SERVICE_NAMES=("${filtered[@]}")
    fi
}

discover_registered_plugin_loader_services() {
    local service_name

    PLUGIN_LOADER_REGISTERED_SERVICES=()

    for service_name in "${PLUGIN_LOADER_SERVICE_NAMES[@]}"; do
        if systemctl list-unit-files "${service_name}.service" --no-legend 2>/dev/null | grep -q "^${service_name}\.service"; then
            PLUGIN_LOADER_REGISTERED_SERVICES+=("$service_name")
        fi
    done
}

require_command() {
    local cmd="$1"
    local description="$2"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Error: $description is required but '$cmd' is not installed."
        exit 1
    fi
}

REQUIRED_PLUGIN_FILES=(
    "main.py"
    "platform_support.py"
    "display_service.py"
    "system_info.py"
    "optimization_runtime.py"
    "rgb_controller.py"
    "rgb_support.py"
    "optimization_support.py"
    "optimization_ops.py"
    "state_aggregator.py"
    "performance_service.py"
    "plugin.json"
    "package.json"
    "dist/index.js"
)

validate_plugin_layout() {
    local root="$1"
    local missing=()
    local relative_path

    for relative_path in "${REQUIRED_PLUGIN_FILES[@]}"; do
        if [ ! -e "$root/$relative_path" ]; then
            missing+=("$relative_path")
        fi
    done

    if [ ${#missing[@]} -gt 0 ]; then
        echo "Error: Release archive is incomplete and cannot be installed."
        echo "Missing files:"
        printf '  - %s\n' "${missing[@]}"
        return 1
    fi

    return 0
}

normalize_plugin_ownership() {
    local current_user
    local current_group
    current_user="$(id -un)"
    current_group="$(id -gn)"

    if [ -d "$PLUGIN_BASE_DIR" ]; then
        sudo chown "$current_user:$current_group" "$PLUGIN_BASE_DIR"
    fi

    if [ -e "$PLUGIN_DIR" ]; then
        sudo chown -R "$current_user:$current_group" "$PLUGIN_DIR"
    fi
}

check_plugin_loader_root_mode() {
    local service_name
    local unit_path
    local missing=0

    for service_name in "${PLUGIN_LOADER_SERVICE_NAMES[@]}"; do
        unit_path="$PLUGIN_LOADER_SYSTEMD_DIR/${service_name}.service"
        if [ ! -f "$unit_path" ]; then
            echo "⚠ Could not inspect Decky service unit: $unit_path"
            missing=1
            continue
        fi

        if grep -Eq '^[[:space:]]*User=root[[:space:]]*$' "$unit_path"; then
            echo "✓ Decky ${service_name} unit is configured with User=root"
            continue
        fi

        echo "⚠ Decky ${service_name} does not appear to run as User=root."
        echo "  Protected writes may fail unless your setup provides passwordless sudo."
        echo "  Check: $unit_path"
    done

    if [ "$missing" -eq 1 ]; then
        echo "  AnyDeck expects Decky to launch plugin backends with effective root access."
    fi

    return 0
}

ensure_plugin_loader_root_mode() {
    local service_name
    local override_dir
    local override_file
    local applied=0

    for service_name in "${PLUGIN_LOADER_SERVICE_NAMES[@]}"; do
        override_dir="/etc/systemd/system/${service_name}.service.d"
        override_file="${override_dir}/90-anydeck-root.conf"

        echo "Configuring Decky ${service_name} override for root backend access..."
        sudo mkdir -p "$override_dir"
        sudo tee "$override_file" >/dev/null <<'EOF'
[Service]
User=root
EOF
        echo "✓ Installed systemd override: $override_file"
        applied=1
    done

    if [ "$applied" -eq 0 ]; then
        echo "Error: No Decky plugin_loader services were detected."
        exit 1
    fi

    sudo systemctl daemon-reload
}

verify_plugin_loader_effective_user() {
    local service_name
    local effective_user
    local failed=0

    if [ ${#PLUGIN_LOADER_REGISTERED_SERVICES[@]} -eq 0 ]; then
        echo "⚠ No registered Decky plugin_loader systemd services were found to verify."
        return 0
    fi

    for service_name in "${PLUGIN_LOADER_REGISTERED_SERVICES[@]}"; do
        effective_user="$(systemctl show "$service_name" -p User --value 2>/dev/null || true)"
        if [ "$effective_user" = "root" ]; then
            echo "✓ ${service_name} effective user is root"
            continue
        fi

        failed=1
        if [ -n "$effective_user" ]; then
            echo "✗ ${service_name} effective user is '$effective_user' instead of 'root'"
        else
            echo "✗ Could not read effective user for ${service_name} from systemd"
        fi
    done

    return "$failed"
}

restart_plugin_loader_services() {
    local service_name

    if [ ${#PLUGIN_LOADER_REGISTERED_SERVICES[@]} -eq 0 ]; then
        echo "⚠ No registered Decky plugin_loader systemd services were found to restart."
        return 1
    fi

    for service_name in "${PLUGIN_LOADER_REGISTERED_SERVICES[@]}"; do
        echo "Restarting Decky Loader service: ${service_name}"
        sudo systemctl restart "$service_name"
    done
}

fetch_release_metadata() {
    python3 - "$REPO_OWNER" "$REPO_NAME" "$REQUESTED_VERSION" <<'PY'
import json
import sys
import urllib.error
import urllib.request

owner, repo, requested = sys.argv[1:4]
headers = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "AnyDeckInstaller/1.0",
}

urls = []
if requested:
    urls.append(f"https://api.github.com/repos/{owner}/{repo}/releases/tags/v{requested}")
urls.append(f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=20")

def open_json(url: str):
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)

def parse_version(version: str):
    core, sep, suffix = version.partition("-")
    try:
        major_s, minor_s, patch_s = core.split(".")
        core_parts = (int(major_s), int(minor_s), int(patch_s))
    except ValueError:
        return None

    if not sep:
        return (*core_parts, 1, ())

    suffix_parts = []
    for part in suffix.split("."):
        if part.isdigit():
            suffix_parts.append((0, int(part)))
        else:
            suffix_parts.append((1, part))
    return (*core_parts, 0, tuple(suffix_parts))

last_error = ""
for url in urls:
    try:
        payload = open_json(url)
    except urllib.error.HTTPError as exc:
        last_error = f"GitHub API error: HTTP {exc.code}"
        continue
    except Exception as exc:
        last_error = str(exc)
        continue

    releases = payload if isinstance(payload, list) else [payload]
    candidates = []
    for release in releases:
        tag_name = str(release.get("tag_name", "") or "")
        if requested and tag_name != f"v{requested}":
            continue

        version = tag_name[1:] if tag_name.startswith("v") else tag_name
        parsed_version = parse_version(version)
        if parsed_version is None:
            continue

        for asset in release.get("assets") or []:
            asset_url = str(asset.get("browser_download_url", "") or "")
            if not asset_url.endswith(".zip"):
                continue
            candidates.append(
                (
                    parsed_version,
                    version,
                    asset_url,
                    "true" if release.get("prerelease", False) else "false",
                )
            )

    if candidates:
        _parsed_version, version, asset_url, prerelease = max(candidates, key=lambda item: item[0])
        print(asset_url)
        print(version)
        print(prerelease)
        sys.exit(0)

if requested:
    print(f"Requested release v{requested} was not found.", file=sys.stderr)
elif last_error:
    print(last_error, file=sys.stderr)
else:
    print("No downloadable release zip was found.", file=sys.stderr)
sys.exit(1)
PY
}

resolve_extract_root() {
    local extract_dir="$1"

    if [ -f "$extract_dir/plugin.json" ] && [ -d "$extract_dir/dist" ]; then
        printf '%s\n' "$extract_dir"
        return 0
    fi

    if [ -d "$extract_dir/$PLUGIN_SLUG" ] && [ -f "$extract_dir/$PLUGIN_SLUG/plugin.json" ]; then
        printf '%s\n' "$extract_dir/$PLUGIN_SLUG"
        return 0
    fi

    local child
    while IFS= read -r child; do
        if [ -f "$child/plugin.json" ] && [ -d "$child/dist" ]; then
            printf '%s\n' "$child"
            return 0
        fi
    done < <(find "$extract_dir" -mindepth 1 -maxdepth 1 -type d | sort)

    return 1
}

echo "================================"
echo "  AnyDeck Installer"
echo "  alpha release by neokura"
echo "================================"
echo ""

require_command "curl" "curl"
require_command "python3" "Python 3"
require_command "unzip" "unzip"
require_command "sudo" "sudo"
require_command "systemctl" "systemctl"

if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo "Error: This script is intended for Linux/SteamOS only."
    exit 1
fi

if [ ! -d "$HOME/homebrew/plugins" ]; then
    echo "Decky Loader does not appear to be installed."
    echo ""
    echo "AnyDeck is a Decky plugin, so Decky must be installed first."
    echo "Decky website: https://decky.xyz/"
    echo ""
    read -p "Open the Decky website now? (Y/n): " -n 1 -r
    echo ""
    if [[ -z "${REPLY:-}" || "$REPLY" =~ ^[Yy]$ ]]; then
        if command -v xdg-open >/dev/null 2>&1; then
            xdg-open "https://decky.xyz/" >/dev/null 2>&1 || true
        else
            echo "Open this URL in your browser: https://decky.xyz/"
        fi
    fi
    echo ""
    echo "Install Decky first, then rerun this installer from Konsole."
    exit 1
fi

echo "Installing $PLUGIN_NAME..."
discover_plugin_loader_services
filter_known_plugin_loader_services
discover_registered_plugin_loader_services

if [ -d "$PLUGIN_DIR" ]; then
    echo ""
    echo "Existing installation detected at: $PLUGIN_DIR"
    echo "This will remove the old installation and reinstall the plugin."
    read -p "Continue? (y/N): " -n 1 -r
    echo ""
    if [[ ! "${REPLY:-}" =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi
    echo "Removing old installation..."
    sudo rm -rf "$PLUGIN_DIR"
fi

echo ""
echo "Creating plugin directory (requires sudo permission)..."
sudo mkdir -p "$PLUGIN_DIR"
normalize_plugin_ownership
check_plugin_loader_root_mode
ensure_plugin_loader_root_mode

echo "Checking for a downloadable release..."
mapfile -t RELEASE_METADATA < <(fetch_release_metadata)
LATEST_URL="${RELEASE_METADATA[0]:-}"
SELECTED_VERSION="${RELEASE_METADATA[1]:-unknown}"
IS_PRERELEASE="${RELEASE_METADATA[2]:-false}"

if [ -z "$LATEST_URL" ]; then
    echo ""
    echo "Error: No downloadable release zip was found."
    echo ""
    echo "Please download a release from:"
    echo "  https://github.com/$REPO_OWNER/$REPO_NAME/releases"
    echo ""
    exit 1
fi

echo "Found release v$SELECTED_VERSION$( [ "$IS_PRERELEASE" = "true" ] && printf ' (pre-release)' )."
echo "Downloading release..."
TEMP_ZIP="$(mktemp --suffix=.zip)"
TEMP_FILES+=("$TEMP_ZIP")

if ! curl -L -f "$LATEST_URL" -o "$TEMP_ZIP" 2>/dev/null; then
    echo ""
    echo "Error: Failed to download release."
    echo "Please check your internet connection and try again."
    exit 1
fi

TEMP_EXTRACT_DIR="$(mktemp -d)"
TEMP_FILES+=("$TEMP_EXTRACT_DIR")

echo "Extracting release..."
if ! unzip -q -o "$TEMP_ZIP" -d "$TEMP_EXTRACT_DIR"; then
    echo ""
    echo "Error: Failed to extract release."
    exit 1
fi

EXTRACT_ROOT="$(resolve_extract_root "$TEMP_EXTRACT_DIR" || true)"
if [ -z "$EXTRACT_ROOT" ]; then
    echo ""
    echo "Error: Release archive does not contain a valid Decky plugin layout."
    exit 1
fi

if ! validate_plugin_layout "$EXTRACT_ROOT"; then
    echo ""
    echo "The published release asset appears to be truncated."
    echo "Please publish a complete release zip, then rerun this installer."
    exit 1
fi

echo "Installing files..."
sudo cp -R "$EXTRACT_ROOT"/. "$PLUGIN_DIR"/
normalize_plugin_ownership

echo "✓ Release installed successfully!"
echo ""
echo "================================"
echo "  Installation Complete!"
echo "================================"
echo ""
echo "Plugin installed to: $PLUGIN_DIR"
echo "Installed version: $SELECTED_VERSION"
echo "Decky service units:"
printf '  - %s\n' "${PLUGIN_LOADER_SERVICE_NAMES[@]}"
if [ ${#PLUGIN_LOADER_REGISTERED_SERVICES[@]} -gt 0 ]; then
    echo "Registered systemd services:"
    printf '  - %s\n' "${PLUGIN_LOADER_REGISTERED_SERVICES[@]}"
else
    echo "Registered systemd services:"
    echo "  - none detected"
fi
echo ""
echo "Restarting Decky Loader..."

if restart_plugin_loader_services; then
    echo "✓ Decky Loader restarted successfully!"
else
    echo "⚠ Could not find a registered Decky systemd service to restart automatically."
    echo "  The plugin files are installed, but you may need to reboot or restart Decky through its own installer/update flow."
fi
if ! verify_plugin_loader_effective_user; then
    echo ""
    echo "Error: Decky did not come back with effective root privileges."
    echo "Protected writes would still be broken, so AnyDeck is refusing to treat this install as healthy."
    echo ""
    echo "Check the Decky units and overrides:"
    for service_name in "${PLUGIN_LOADER_SERVICE_NAMES[@]}"; do
        echo "  sudo systemctl status ${service_name}"
        echo "  sudo systemctl cat ${service_name}"
    done
    echo "Or reboot your device after confirming the overrides were written under /etc/systemd/system."
    exit 1
fi

echo ""
echo "Your plugin should now be available in the Quick Access menu."

echo ""
