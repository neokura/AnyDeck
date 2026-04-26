#!/bin/bash
# AnyDeck - Installation Script
# Author: neokura
set -euo pipefail

PLUGIN_NAME="AnyDeck"
PLUGIN_SLUG="anydeck"
PLUGIN_DIR="$HOME/homebrew/plugins/$PLUGIN_NAME"
REPO_OWNER="neokura"
REPO_NAME="AnyDeck"
REQUESTED_VERSION="${1:-${ANYDECK_VERSION:-}}"
PLUGIN_LOADER_SERVICE_NAME="plugin_loader"
PLUGIN_LOADER_OVERRIDE_DIR="/etc/systemd/system/${PLUGIN_LOADER_SERVICE_NAME}.service.d"
PLUGIN_LOADER_OVERRIDE_FILE="${PLUGIN_LOADER_OVERRIDE_DIR}/90-anydeck-root.conf"

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

PLUGIN_LOADER_UNIT="$HOME/homebrew/services/.systemd/plugin_loader.service"

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

check_plugin_loader_root_mode() {
    if [ ! -f "$PLUGIN_LOADER_UNIT" ]; then
        echo "⚠ Could not inspect Decky service unit: $PLUGIN_LOADER_UNIT"
        echo "  AnyDeck expects Decky to launch plugin backends with effective root access."
        return 0
    fi

    if grep -Eq '^[[:space:]]*User=root[[:space:]]*$' "$PLUGIN_LOADER_UNIT"; then
        echo "✓ Decky plugin_loader is configured with User=root"
        return 0
    fi

    echo "⚠ Decky plugin_loader does not appear to run as User=root."
    echo "  Protected writes may fail unless your setup provides passwordless sudo."
    echo "  Check: $PLUGIN_LOADER_UNIT"
    return 0
}

ensure_plugin_loader_root_mode() {
    if grep -Eq '^[[:space:]]*User=root[[:space:]]*$' "$PLUGIN_LOADER_UNIT" 2>/dev/null; then
        echo "✓ Decky plugin_loader is already configured with User=root"
        return 0
    fi

    echo "Configuring Decky plugin_loader override for root backend access..."
    sudo mkdir -p "$PLUGIN_LOADER_OVERRIDE_DIR"
    sudo tee "$PLUGIN_LOADER_OVERRIDE_FILE" >/dev/null <<'EOF'
[Service]
User=root
EOF

    if command -v systemctl >/dev/null 2>&1; then
        sudo systemctl daemon-reload
        echo "✓ Installed systemd override: $PLUGIN_LOADER_OVERRIDE_FILE"
    else
        echo "⚠ systemctl is unavailable; created the override but could not reload systemd"
    fi
}

verify_plugin_loader_effective_user() {
    if ! command -v systemctl >/dev/null 2>&1; then
        echo "⚠ systemctl is unavailable; unable to verify plugin_loader effective user"
        return 0
    fi

    local effective_user
    effective_user="$(systemctl show "$PLUGIN_LOADER_SERVICE_NAME" -p User --value 2>/dev/null || true)"
    if [ "$effective_user" = "root" ]; then
        echo "✓ plugin_loader effective user is root"
        return 0
    fi

    if [ -n "$effective_user" ]; then
        echo "⚠ plugin_loader effective user is '$effective_user' instead of 'root'"
    else
        echo "⚠ Could not read plugin_loader effective user from systemd"
    fi
    echo "  AnyDeck may not be able to apply protected settings until Decky is relaunched in root mode."
    return 0
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
    for release in releases:
        tag_name = str(release.get("tag_name", "") or "")
        if requested and tag_name != f"v{requested}":
            continue

        for asset in release.get("assets") or []:
            asset_url = str(asset.get("browser_download_url", "") or "")
            if not asset_url.endswith(".zip"):
                continue

            version = tag_name[1:] if tag_name.startswith("v") else tag_name
            print(asset_url)
            print(version)
            print("true" if release.get("prerelease", False) else "false")
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
sudo chown -R "$(id -un):$(id -gn)" "$PLUGIN_DIR"
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
sudo chown -R "$(id -un):$(id -gn)" "$PLUGIN_DIR"

echo "✓ Release installed successfully!"
echo ""
echo "================================"
echo "  Installation Complete!"
echo "================================"
echo ""
echo "Plugin installed to: $PLUGIN_DIR"
echo "Installed version: $SELECTED_VERSION"
echo "Decky service unit: $PLUGIN_LOADER_UNIT"
echo ""
echo "Restarting Decky Loader..."

if sudo systemctl restart "$PLUGIN_LOADER_SERVICE_NAME" 2>/dev/null; then
    echo "✓ Decky Loader restarted successfully!"
    verify_plugin_loader_effective_user
    echo ""
    echo "Your plugin should now be available in the Quick Access menu."
else
    echo "⚠ Could not restart Decky Loader automatically."
    echo "Please restart it manually with:"
    echo "  sudo systemctl restart plugin_loader"
    echo "Or reboot your device."
fi

echo ""
