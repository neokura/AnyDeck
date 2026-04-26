"""Helpers for SteamOS handheld detection and support gating."""

STEAMOS_MIN_VERSION = (3, 8)
ASUS_VENDOR_NAMES = {"ASUS", "ASUSTEK", "ASUSTEK COMPUTER INC."}
LENOVO_VENDOR_NAMES = {"LENOVO"}
GENERIC_HANDHELD_VENDOR_NAMES = {
    "AOKZOE",
    "AYA",
    "AYADEVICE",
    "AYANEO",
    "GPD",
    "MSI",
    "ONEXPLAYER",
    "ONE-NETBOOK",
    "ZOTAC",
    "ACER",
}
STEAM_DECK_VENDOR_NAMES = {"VALVE"}
HANDHELD_IDENTIFIER_KEYWORDS = (
    "ALLY",
    "AYA",
    "AYANEO",
    "CLAW",
    "GAMEPAD",
    "GAMING HANDHELD",
    "GPD",
    "HANDHELD",
    "LEGION",
    "ONEX",
    "PLAYER",
    "PORTABLE",
    "ROG",
    "WIN",
    "XBOX",
    "Z1",
)


def get_steamos_version(os_release_values: dict | None = None) -> str:
    values = os_release_values or {}
    return (
        values.get("PRETTY_NAME")
        or values.get("VERSION")
        or values.get("NAME")
        or "Unknown"
    )


def is_steam_deck_device(
    board_name: str,
    product_name: str,
    sys_vendor: str,
    product_family: str,
) -> bool:
    normalized_vendor = sys_vendor.strip().upper()
    identifiers = " ".join(
        value.strip().upper()
        for value in (board_name, product_name, product_family)
        if value and value != "Unknown"
    )
    return normalized_vendor in STEAM_DECK_VENDOR_NAMES or any(
        keyword in identifiers
        for keyword in ("STEAM DECK", "JUPITER", "GALILEO")
    )


def is_supported_handheld_vendor_device(
    board_name: str,
    product_name: str,
    sys_vendor: str,
    product_family: str,
) -> bool:
    normalized_vendor = sys_vendor.strip().upper()
    identifiers = " ".join(
        value.strip().upper()
        for value in (board_name, product_name, product_family)
        if value and value != "Unknown"
    )

    if normalized_vendor in ASUS_VENDOR_NAMES:
        return any(keyword in identifiers for keyword in ("ALLY", "ROG", "XBOX", "RC7"))

    if normalized_vendor in LENOVO_VENDOR_NAMES:
        return "LEGION" in identifiers

    if normalized_vendor in GENERIC_HANDHELD_VENDOR_NAMES:
        return any(keyword in identifiers for keyword in HANDHELD_IDENTIFIER_KEYWORDS)

    return any(keyword in identifiers for keyword in HANDHELD_IDENTIFIER_KEYWORDS)


def parse_version_tuple(raw_version: str) -> tuple[int, int] | None:
    parts = []
    current = ""
    for char in raw_version:
        if char.isdigit():
            current += char
        elif current:
            parts.append(int(current))
            current = ""
            if len(parts) == 2:
                break
    if current and len(parts) < 2:
        parts.append(int(current))
    if not parts:
        return None
    if len(parts) == 1:
        parts.append(0)
    return parts[0], parts[1]


def steamos_version_is_supported(values: dict) -> bool:
    for key in ("VERSION_ID", "VERSION", "PRETTY_NAME"):
        parsed = parse_version_tuple(values.get(key, ""))
        if parsed is not None:
            return parsed >= STEAMOS_MIN_VERSION
    return False


def get_platform_support(
    board_name: str,
    product_name: str,
    sys_vendor: str,
    product_family: str,
    os_release_values: dict | None = None,
) -> dict:
    values = os_release_values or {}
    os_id = values.get("ID", "").strip().lower()
    os_name = " ".join(
        values.get(key, "")
        for key in ("NAME", "PRETTY_NAME", "ID", "ID_LIKE")
    ).lower()

    if is_steam_deck_device(board_name, product_name, sys_vendor, product_family):
        return {
            "supported": False,
            "support_level": "blocked",
            "reason": "Steam Deck is blocked to avoid interfering with Valve hardware defaults.",
        }

    if os_id != "steamos" or any(name in os_name for name in ("bazzite", "chimeraos", "chimera")):
        return {
            "supported": False,
            "support_level": "blocked",
            "reason": "AnyDeck is only enabled on SteamOS 3.8 or newer.",
        }

    if not steamos_version_is_supported(values):
        return {
            "supported": False,
            "support_level": "blocked",
            "reason": "AnyDeck requires SteamOS 3.8 or newer.",
        }

    if not is_supported_handheld_vendor_device(
        board_name,
        product_name,
        sys_vendor,
        product_family,
    ):
        return {
            "supported": False,
            "support_level": "blocked",
            "reason": "AnyDeck is only enabled on non-Steam-Deck handhelds it can identify.",
        }

    normalized_vendor = sys_vendor.strip().upper()
    support_level = (
        "supported"
        if normalized_vendor in ASUS_VENDOR_NAMES | LENOVO_VENDOR_NAMES
        else "experimental"
    )
    return {
        "supported": True,
        "support_level": support_level,
        "reason": (
            "Validated SteamOS handheld on SteamOS 3.8 or newer."
            if support_level == "supported"
            else "Experimental SteamOS handheld support on SteamOS 3.8 or newer."
        ),
    }


def get_device_metadata(
    board_name: str,
    product_name: str,
    sys_vendor: str = "",
    product_family: str = "",
) -> dict:
    vendor = (
        sys_vendor
        if sys_vendor and sys_vendor != "Unknown"
        else "Unknown"
    )
    friendly_name = product_name if product_name and product_name != "Unknown" else "SteamOS handheld"

    return {
        "board_name": board_name,
        "product_name": product_name,
        "product_family": product_family or "Unknown",
        "sys_vendor": vendor,
        "variant": board_name or product_name or "Unknown",
        "friendly_name": friendly_name,
        "device_family": "steamos_handheld",
        "support_level": "supported",
    }
