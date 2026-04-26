import {
  definePlugin,
  PanelSection,
  PanelSectionRow,
  DialogButton,
  DropdownItem,
  Focusable,
  SliderField,
  ToggleField,
  staticClasses,
} from "@decky/ui";
import { callable, toaster } from "@decky/api";

const { useEffect, useState } = window.SP_REACT;
type VFC<P = {}> = (props: P) => JSX.Element | null;

const PLUGIN_NAME = "AnyDeck";
const RGB_PRESETS = [
  "#FF0000",
  "#00FFFF",
  "#8B00FF",
  "#00FF00",
  "#FF8000",
  "#FF00FF",
  "#FFFFFF",
  "#0000FF",
];
const RGB_PRESET_LABELS: Record<string, string> = {
  "#FF0000": "ROG Red",
  "#00FFFF": "Cyan",
  "#8B00FF": "Purple",
  "#00FF00": "Green",
  "#FF8000": "Orange",
  "#FF00FF": "Pink",
  "#FFFFFF": "White",
  "#0000FF": "Blue",
};
const RGB_MODE_LABELS: Record<string, string> = {
  solid: "Solid",
  pulse: "Pulse",
  rainbow: "Rainbow",
  spiral: "Spiral",
};
const RGB_SPEED_LABELS: Record<string, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
};
const RGB_SPEED_DESCRIPTIONS: Record<string, string> = {
  low: "Smoother and slower animation",
  medium: "Default native cadence",
  high: "Fastest native animation",
};
const RGB_EFFECTS = [
  { data: "static", label: "Static" },
  { data: "pulse", label: "Pulse" },
  { data: "spectrum", label: "Spectrum" },
  { data: "wave", label: "Wave" },
  { data: "flash", label: "Flash" },
  { data: "battery", label: "Battery Level" },
  { data: "off", label: "Off" },
];
const RGB_ANIMATED_EFFECTS = ["pulse", "spectrum", "wave", "flash"];

const clamp = (value: number, min: number, max: number): number =>
  Math.max(min, Math.min(max, value));

const normalizeHexColor = (color: string): string => {
  const trimmed = color.trim().toUpperCase().replace(/^#/, "");
  return /^[0-9A-F]{6}$/.test(trimmed) ? `#${trimmed}` : RGB_PRESETS[0];
};

const hueToHex = (hue: number): string => {
  const normalizedHue = ((hue % 360) + 360) % 360;
  const c = 1;
  const x = c * (1 - Math.abs(((normalizedHue / 60) % 2) - 1));
  let r = 0;
  let g = 0;
  let b = 0;

  if (normalizedHue < 60) {
    r = c;
    g = x;
  } else if (normalizedHue < 120) {
    r = x;
    g = c;
  } else if (normalizedHue < 180) {
    g = c;
    b = x;
  } else if (normalizedHue < 240) {
    g = x;
    b = c;
  } else if (normalizedHue < 300) {
    r = x;
    b = c;
  } else {
    r = c;
    b = x;
  }

  const toHex = (channel: number) =>
    Math.round(channel * 255)
      .toString(16)
      .padStart(2, "0")
      .toUpperCase();

  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
};

const hexToHue = (color: string): number => {
  const normalized = normalizeHexColor(color).replace("#", "");
  const r = parseInt(normalized.slice(0, 2), 16) / 255;
  const g = parseInt(normalized.slice(2, 4), 16) / 255;
  const b = parseInt(normalized.slice(4, 6), 16) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const delta = max - min;

  if (delta === 0) {
    return 0;
  }

  let hue = 0;
  if (max === r) {
    hue = 60 * (((g - b) / delta) % 6);
  } else if (max === g) {
    hue = 60 * ((b - r) / delta + 2);
  } else {
    hue = 60 * ((r - g) / delta + 4);
  }

  return Math.round((hue + 360) % 360);
};

const rgbStateToEffect = (rgb?: RgbState | null): string => {
  if (!rgb?.enabled) {
    return "off";
  }

  switch (rgb.mode) {
    case "pulse":
      return "pulse";
    case "rainbow":
      return "spectrum";
    case "spiral":
      return "wave";
    default:
      return "static";
  }
};

const rgbSpeedToSliderValue = (speed?: string): number => {
  switch ((speed || "").toLowerCase()) {
    case "low":
      return 20;
    case "high":
      return 100;
    default:
      return 50;
  }
};

const getDashboardState = callable<[], DashboardState>("get_dashboard_state");
const getOptimizationStates = callable<[], OptimizationData>(
  "get_optimization_states"
);
const setOptimizationEnabled = callable<[string, boolean], boolean>(
  "set_optimization_enabled"
);
const enableAvailableOptimizations = callable<[], BulkOptimizationResult>(
  "enable_available_optimizations"
);
const getInformationState = callable<[], InformationState>(
  "get_information_state"
);
const clearDebugLog = callable<[], boolean>("clear_debug_log");
const setPerformanceProfile = callable<[string], boolean>("set_performance_profile");
const setCpuBoostEnabled = callable<[boolean], boolean>("set_cpu_boost_enabled");
const setSmtEnabled = callable<[boolean], boolean>("set_smt_enabled");
const setRgbEnabled = callable<[boolean], boolean>("set_rgb_enabled");
const setRgbColor = callable<[string], boolean>("set_rgb_color");
const setRgbBrightness = callable<[number], boolean>("set_rgb_brightness");
const setRgbEffect = callable<[string], boolean>("set_rgb_effect");
const setRgbMode = callable<[string], boolean>("set_rgb_mode");
const setRgbSpeed = callable<[string], boolean>("set_rgb_speed");
const setDisplaySyncSetting = callable<[string, boolean], boolean>(
  "set_display_sync_setting"
);
const setFpsLimit = callable<[number], boolean>("set_fps_limit");
const setChargeLimitEnabled = callable<[boolean], boolean>("set_charge_limit_enabled");

interface PerformanceMode {
  id: string;
  label: string;
  native_id: string;
  description: string;
  available: boolean;
  active: boolean;
}

interface AvailabilityToggle {
  available: boolean;
  enabled: boolean;
  status: string;
  details: string;
  capable?: boolean;
  active?: boolean;
}

interface RgbState {
  available: boolean;
  enabled: boolean;
  mode: string;
  color: string;
  brightness: number;
  speed: string;
  brightness_available: boolean;
  supports_free_color: boolean;
  speed_available: boolean;
  capabilities: {
    toggle: boolean;
    color: boolean;
    brightness: boolean;
  };
  supported_modes: string[];
  mode_capabilities: Record<
    string,
    {
      color: boolean;
      brightness: boolean;
      speed: boolean;
    }
  >;
  speed_options: string[];
  presets: string[];
  details: string;
}

interface FpsLimitState {
  available: boolean;
  current: number;
  requested?: number;
  is_live?: boolean;
  presets: number[];
  status: string;
  details: string;
}

interface ChargeLimitState {
  available: boolean;
  enabled: boolean;
  limit: number;
  status: string;
  details: string;
}

interface DashboardState {
  performance_modes: PerformanceMode[];
  active_mode: string;
  profiles_available: boolean;
  profiles_status: string;
  cpu_boost: AvailabilityToggle;
  smt: AvailabilityToggle;
  rgb: RgbState;
  vrr: AvailabilityToggle;
  vsync: AvailabilityToggle & { allow_tearing?: boolean };
  fps_limit: FpsLimitState;
  charge_limit: ChargeLimitState;
}

interface OptimizationState {
  key: string;
  name: string;
  description: string;
  enabled: boolean;
  active: boolean;
  available: boolean;
  mutable?: boolean;
  needs_reboot: boolean;
  details: string;
  risk_note: string;
  status: string;
}

interface OptimizationData {
  states: OptimizationState[];
}

interface BulkOptimizationItem {
  key: string;
  name: string;
  reason?: string;
}

interface BulkOptimizationResult {
  success: boolean;
  enabled: BulkOptimizationItem[];
  already_enabled: BulkOptimizationItem[];
  skipped: BulkOptimizationItem[];
  failed: BulkOptimizationItem[];
}

interface DeviceInfo {
  friendly_name: string;
  board_name: string;
  product_name: string;
  product_family?: string;
  sys_vendor: string;
  variant: string;
  device_family: string;
  support_level: string;
  platform_supported?: boolean;
  platform_support_reason?: string;
  steamos_version: string;
  bios_version: string;
  serial: string;
  cpu: string;
  gpu: string;
  kernel: string;
  memory_total: string;
}

interface BatteryInfo {
  present: boolean;
  status: string;
  capacity: number;
  health: number;
  cycle_count: number;
  voltage: number;
  current: number;
  temperature: number;
  design_capacity: number;
  full_capacity: number;
  charge_limit: number;
  time_to_empty: string;
  time_to_full: string;
}

interface InformationState {
  device: DeviceInfo;
  battery: BatteryInfo;
  performance: {
    current_profile: string;
    available_native: string[];
    status: string;
  };
  display: {
    vrr: AvailabilityToggle;
    vsync: AvailabilityToggle;
  };
  temperatures: {
    tdp: number;
    cpu: number;
    gpu: number;
    gpu_clock: number;
  };
  optimizations: OptimizationState[];
  hardware_controls: Record<string, boolean>;
  fps_limit: FpsLimitState;
  runtime: {
    execution_backend: "direct" | "flatpak-host";
    os_release_path: string;
    host_os_id: string;
    privileges: {
      user: string;
      effective_uid: number;
      is_root: boolean;
      sudo_noninteractive: boolean;
      system_write_access: boolean;
    };
    commands: Record<
      string,
      {
        available: boolean;
        path: string;
        via_host: boolean;
      }
    >;
    steamos_manager_bus: "user" | "system" | "none";
    display_env: {
      display: string;
      xauthority: string;
      gamescope_env_path: string;
      gamescope_wayland_display: string;
    };
  };
  debug_log: DebugLogEntry[];
}

interface DebugLogEntry {
  timestamp: string;
  area: string;
  action: string;
  status: string;
  message: string;
  details: Record<string, unknown>;
}

type ViewName = "dashboard" | "rgb" | "optimizations" | "information";

const viewTitleStyle: React.CSSProperties = {
  fontSize: "18px",
  fontWeight: 700,
  color: "#ffffff",
};

const subtextStyle: React.CSSProperties = {
  fontSize: "12px",
  color: "#8b929a",
  lineHeight: 1.4,
};

const cardStyle: React.CSSProperties = {
  background: "linear-gradient(180deg, rgba(36,42,49,0.95), rgba(25,29,35,0.95))",
  border: "1px solid rgba(100, 116, 139, 0.35)",
  borderRadius: "8px",
  padding: "14px",
  marginBottom: "12px",
  width: "100%",
  boxSizing: "border-box",
  minWidth: 0,
  overflow: "hidden",
};

const statusRowStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "flex-start",
  gap: "12px",
  marginBottom: "6px",
};

const debugLogStyle: React.CSSProperties = {
  fontSize: "11px",
  lineHeight: 1.45,
  color: "#dbe4ee",
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
  fontFamily: "monospace",
};

const infoLabelStyle: React.CSSProperties = {
  color: "#8b929a",
  fontSize: "12px",
  flex: "0 0 38%",
};

const infoValueStyle: React.CSSProperties = {
  color: "#ffffff",
  fontSize: "12px",
  textAlign: "right",
  flex: "1 1 auto",
  overflowWrap: "anywhere",
  wordBreak: "break-word",
  lineHeight: 1.4,
};

const rgbQuickSwatchGridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
  gap: "8px",
  width: "100%",
};

const optionGridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
  gap: "8px",
  width: "100%",
};

const performanceModeGridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
  gap: "8px",
  width: "100%",
};

const nativeButtonCellStyle: React.CSSProperties = {
  minWidth: 0,
};

const nativeDialogButtonStyle = (
  active: boolean,
  disabled: boolean
): React.CSSProperties => ({
  width: "100%",
  minWidth: 0,
  padding: "10px 8px",
  opacity: disabled ? 0.5 : 1,
  boxShadow: active ? "inset 0 0 0 1px rgba(96, 165, 250, 0.6)" : "none",
});

const nativeButtonContentStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  gap: "6px",
  width: "100%",
  minWidth: 0,
  textAlign: "center",
};

const nativeButtonTextBlockStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  gap: "3px",
  width: "100%",
  minWidth: 0,
};

const nativeButtonTitleStyle = (active: boolean): React.CSSProperties => ({
  color: active ? "#dbeafe" : "#ffffff",
  fontWeight: 700,
  fontSize: "11px",
  lineHeight: 1.2,
  overflowWrap: "anywhere",
});

const nativeButtonDescriptionStyle = (active: boolean): React.CSSProperties => ({
  color: active ? "#bfdbfe" : "#9aa6b2",
  fontSize: "9px",
  lineHeight: 1.25,
  overflowWrap: "anywhere",
});

const nativeButtonBadgeStyle = (
  active: boolean,
  disabled: boolean
): React.CSSProperties => ({
  marginTop: "2px",
  padding: "2px 8px",
  borderRadius: "999px",
  fontSize: "9px",
  fontWeight: 700,
  lineHeight: 1.2,
  color: disabled ? "#94a3b8" : active ? "#dbeafe" : "#cbd5e1",
  background: active ? "rgba(59, 130, 246, 0.24)" : "rgba(255,255,255,0.08)",
});

const actionButtonRowStyle: React.CSSProperties = {
  display: "flex",
  gap: "8px",
  width: "100%",
};

const stackedActionButtonGroupStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr)",
  gap: "8px",
  width: "100%",
};

const actionButtonCellStyle: React.CSSProperties = {
  flex: "1 1 0",
  minWidth: 0,
};

const secondaryActionButtonStyle = (
  disabled: boolean
): React.CSSProperties => ({
  width: "100%",
  minWidth: 0,
  padding: "10px 12px",
  opacity: disabled ? 0.5 : 1,
});

const rgbHeroStyle = (enabled: boolean, color: string): React.CSSProperties => ({
  borderRadius: "8px",
  padding: "14px",
  border: "1px solid rgba(100, 116, 139, 0.35)",
  background: enabled
    ? `linear-gradient(135deg, ${color} 0%, rgba(15,23,42,0.96) 82%)`
    : "linear-gradient(135deg, rgba(51,65,85,0.7), rgba(15,23,42,0.96))",
  minHeight: "84px",
  display: "flex",
  flexDirection: "column",
  justifyContent: "space-between",
  gap: "10px",
});

const rgbSwatchStripStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(8, minmax(0, 1fr))",
  gap: "6px",
  marginTop: "10px",
};

const rgbPresetRailStyle = (colors: string[]): React.CSSProperties => ({
  width: "100%",
  height: "10px",
  borderRadius: "999px",
  background: `linear-gradient(90deg, ${colors.join(", ")})`,
  border: "1px solid rgba(148, 163, 184, 0.28)",
  marginTop: "-8px",
});

const rgbHueRailStyle: React.CSSProperties = {
  width: "100%",
  height: "10px",
  borderRadius: "999px",
  background:
    "linear-gradient(90deg, #FF0000, #FFFF00, #00FF00, #00FFFF, #0000FF, #FF00FF, #FF0000)",
  border: "1px solid rgba(148, 163, 184, 0.28)",
  marginTop: "-8px",
};

const rgbQuickSwatchButtonStyle = (
  active: boolean,
  color: string
): React.CSSProperties => ({
  appearance: "none",
  width: "100%",
  borderRadius: "10px",
  padding: "0",
  border: active
    ? "2px solid rgba(255,255,255,0.95)"
    : "1px solid rgba(148, 163, 184, 0.35)",
  background: "rgba(15, 23, 42, 0.35)",
  boxShadow: active ? `0 0 16px ${color}` : "none",
  overflow: "hidden",
  minHeight: "54px",
  cursor: "pointer",
});

const statusColor = (status: string): string => {
  switch (status) {
    case "active":
    case "success":
      return "#4ade80";
    case "attempt":
    case "configured":
    case "snapshot":
      return "#60a5fa";
    case "reboot-required":
      return "#f59e0b";
    case "error":
    case "unavailable":
      return "#f87171";
    default:
      return "#cbd5e1";
  }
};

const formatToggleLabel = (
  title: string,
  setting?: AvailabilityToggle,
  unavailableLabel?: string
): string => {
  if (!setting?.available) {
    return unavailableLabel || `${title}: unavailable`;
  }
  return `${title}: ${setting.enabled ? "enabled" : "disabled"}`;
};

const formatFpsLabel = (value: number): string =>
  value === 0 ? "Unlimited" : `${value} FPS`;

const formatFpsReadout = (state: FpsLimitState): string => {
  if (!state.available) {
    return state.status;
  }
  if (state.is_live) {
    return `Current limit: ${formatFpsLabel(state.current)}`;
  }
  return state.details;
};

const compactPerformanceDescription = (modeId: string): string => {
  switch (modeId) {
    case "low-power":
      return "Cool and quiet";
    case "balanced":
      return "Everyday play";
    case "performance":
      return "Higher performance";
    default:
      return "Performance mode";
  }
};

const PerformanceModeGlyph: VFC<{ modeId: string; active: boolean }> = ({
  modeId,
  active,
}) => {
  const stroke = active ? "#dbeafe" : "#e2e8f0";
  const fill = "none";

  if (modeId === "low-power") {
    return (
      <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
        <path
          d="M14.8 4.5C11.2 6.3 9.2 9.3 9.2 12.6C9.2 16 11.4 18.5 14.6 18.5C17.2 18.5 19 16.7 19 14.1C19 11.2 16.9 9.5 14.3 9.6C15.3 8.4 15.8 6.8 15.8 5.2C15.8 4.8 15.4 4.5 14.8 4.5Z"
          stroke={stroke}
          strokeWidth="1.8"
          fill={fill}
          strokeLinejoin="round"
        />
        <path d="M12 13.4C12.9 12.5 14.1 12 15.4 12" stroke={stroke} strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    );
  }

  if (modeId === "balanced") {
    return (
      <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
        <path d="M12 5V8" stroke={stroke} strokeWidth="1.8" strokeLinecap="round" />
        <path d="M7 9H17" stroke={stroke} strokeWidth="1.8" strokeLinecap="round" />
        <path d="M8.5 9L6.8 15.5C6.5 16.8 7.5 18 8.8 18H10.8C12 18 13 17 13 15.8V9" stroke={stroke} strokeWidth="1.8" fill={fill} strokeLinejoin="round" />
        <path d="M15.5 9L17.2 15.5C17.5 16.8 16.5 18 15.2 18H13.2C12 18 11 17 11 15.8V9" stroke={stroke} strokeWidth="1.8" fill={fill} strokeLinejoin="round" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
      <path d="M5 15.5C5 10.8 8.4 7 12 7C15.6 7 19 10.8 19 15.5" stroke={stroke} strokeWidth="1.8" fill={fill} strokeLinecap="round" />
      <path d="M12 12L15.5 10.2" stroke={stroke} strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="12" cy="15.5" r="1.2" fill={stroke} />
    </svg>
  );
};

interface NativeOptionButtonProps {
  title: string;
  description?: string;
  status?: string;
  active?: boolean;
  disabled?: boolean;
  icon?: JSX.Element;
  onClick: () => void;
}

const NativeOptionButton: VFC<NativeOptionButtonProps> = ({
  title,
  description,
  status,
  active = false,
  disabled = false,
  icon,
  onClick,
}) => (
  <Focusable style={nativeButtonCellStyle}>
    <DialogButton
      style={nativeDialogButtonStyle(active, disabled)}
      disabled={disabled}
      onClick={onClick}
    >
      <div style={nativeButtonContentStyle}>
        {icon}
        <div style={nativeButtonTextBlockStyle}>
          <div style={nativeButtonTitleStyle(active)}>{title}</div>
          {description && (
            <div style={nativeButtonDescriptionStyle(active)}>{description}</div>
          )}
        </div>
        {status && <div style={nativeButtonBadgeStyle(active, disabled)}>{status}</div>}
      </div>
    </DialogButton>
  </Focusable>
);

interface SecondaryActionButtonProps {
  label: string;
  disabled?: boolean;
  onClick: () => void;
}

const SecondaryActionButton: VFC<SecondaryActionButtonProps> = ({
  label,
  disabled = false,
  onClick,
}) => (
  <Focusable style={actionButtonCellStyle}>
    <DialogButton
      style={secondaryActionButtonStyle(disabled)}
      disabled={disabled}
      onClick={onClick}
    >
      {label}
    </DialogButton>
  </Focusable>
);

const hardwareControlLabels: Record<string, string> = {
  performance_profiles: "SteamOS profiles",
  cpu_boost: "CPU Boost",
  smt: "SMT",
  charge_limit: "Charge limit",
  rgb: "RGB",
  vrr: "VRR",
  vsync: "V-Sync",
  fps_limit: "Max Framerate",
  optimizations: "Optimizations",
};

const formatMeasurementValue = (value: number): string =>
  Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1);

const formatPositiveMeasurement = (value: number, unit: string): string =>
  Number.isFinite(value) && value > 0 ? `${formatMeasurementValue(value)} ${unit}` : "Unknown";

const formatSignedMeasurement = (value: number, unit: string): string =>
  Number.isFinite(value) ? `${formatMeasurementValue(value)} ${unit}` : "Unknown";

const describeError = (error: unknown): string => {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  if (typeof error === "string" && error.trim()) {
    return error;
  }
  return "The plugin could not refresh this view.";
};

const formatDisplayStatus = (setting?: AvailabilityToggle): string => {
  if (!setting?.available) {
    return setting?.capable === false ? "Not compatible" : "Unavailable";
  }
  if (setting.active !== undefined) {
    return setting.active ? "Active" : setting.enabled ? "Enabled" : "Disabled";
  }
  return setting.enabled ? "Enabled" : "Disabled";
};

const InfoRow: VFC<{ label: string; value: string }> = ({ label, value }) => (
  <div style={statusRowStyle}>
    <div style={infoLabelStyle}>{label}</div>
    <div style={infoValueStyle}>{value}</div>
  </div>
);

const ViewHeader: VFC<{
  title: string;
  subtitle: string;
  backLabel?: string;
  onBack?: () => void;
}> = ({ title, subtitle, backLabel, onBack }) => (
  <PanelSection>
    {onBack && (
      <PanelSectionRow>
        <div style={actionButtonRowStyle}>
          <SecondaryActionButton label={backLabel || "Back"} onClick={onBack} />
        </div>
      </PanelSectionRow>
    )}
    <PanelSectionRow>
      <div style={cardStyle}>
        <div style={viewTitleStyle}>{title}</div>
        <div style={subtextStyle}>{subtitle}</div>
      </div>
    </PanelSectionRow>
  </PanelSection>
);

const StatusCard: VFC<{
  title: string;
  message: string;
  tone?: "neutral" | "error";
}> = ({ title, message, tone = "neutral" }) => (
  <div
    style={{
      ...cardStyle,
      border:
        tone === "error"
          ? "1px solid rgba(248, 113, 113, 0.4)"
          : "1px solid rgba(100, 116, 139, 0.35)",
      marginBottom: 0,
    }}
  >
    <div
      style={{
        ...viewTitleStyle,
        fontSize: "15px",
        color: tone === "error" ? "#fecaca" : "#ffffff",
      }}
    >
      {title}
    </div>
    <div style={subtextStyle}>{message}</div>
  </div>
);

const DashboardView: VFC<{
  data: DashboardState | null;
  loading: boolean;
  error: string | null;
  busyKey: string | null;
  onRefresh: () => Promise<void>;
  onOpenRgb: () => void;
  onOpenOptimizations: () => void;
  onOpenInformation: () => void;
}> = ({
  data,
  loading,
  error,
  busyKey,
  onRefresh,
  onOpenRgb,
  onOpenOptimizations,
  onOpenInformation,
}) => {
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const controlsDisabled = busyKey !== null || actionBusy !== null;
  const fpsPresets = data?.fps_limit.presets?.length
    ? data.fps_limit.presets
    : [30, 40, 60, 0];
  const normalizedCurrentFpsPreset = fpsPresets.includes(data?.fps_limit.current ?? 0)
    ? data?.fps_limit.current ?? 0
    : fpsPresets.includes(60)
      ? 60
      : fpsPresets[0];
  const normalizedFpsPresetIndex = Math.max(0, fpsPresets.indexOf(normalizedCurrentFpsPreset));
  const [fpsPresetIndex, setFpsPresetIndex] = useState<number>(normalizedFpsPresetIndex);
  const fpsPresetValue = fpsPresets[fpsPresetIndex] ?? normalizedCurrentFpsPreset;

  const runAction = async (
    actionKey: string,
    operation: () => Promise<boolean>,
    successMessage: string,
    failureMessage: string
  ) => {
    if (controlsDisabled) {
      return;
    }

    setActionBusy(actionKey);
    let success = false;
    try {
      success = await operation();
      toaster.toast({
        title: PLUGIN_NAME,
        body: success ? successMessage : failureMessage,
      });
      await onRefresh();
    } finally {
      setActionBusy(null);
    }
  };

  const handlePerformanceProfile = async (profileId: string, label: string) => {
    await runAction(
      `profile:${profileId}`,
      () => setPerformanceProfile(profileId),
      `${label} SteamOS profile applied`,
      "Could not apply this SteamOS profile"
    );
  };

  const handleBoost = async (enabled: boolean) => {
    await runAction(
      "cpu-boost",
      () => setCpuBoostEnabled(enabled),
      `CPU Boost ${enabled ? "enabled" : "disabled"}`,
      "Could not change CPU Boost"
    );
  };

  const handleSmt = async (enabled: boolean) => {
    await runAction(
      "smt",
      () => setSmtEnabled(enabled),
      `SMT ${enabled ? "enabled" : "disabled"}`,
      "Could not change SMT"
    );
  };

  const handleChargeLimit = async (enabled: boolean) => {
    await runAction(
      "charge-limit",
      () => setChargeLimitEnabled(enabled),
      `Charge limit ${enabled ? "enabled at 80%" : "disabled"}`,
      "Could not change the charge limit"
    );
  };

  const handleSync = async (key: "vrr" | "vsync", enabled: boolean) => {
    await runAction(
      key,
      () => setDisplaySyncSetting(key, enabled),
      `${key === "vrr" ? "VRR" : "V-Sync"} ${enabled ? "enabled" : "disabled"}`,
      `Could not change ${key === "vrr" ? "VRR" : "V-Sync"}`
    );
  };

  const commitFpsLimit = async (value: number) => {
    await runAction(
      `fps:${value}`,
      () => setFpsLimit(value),
      `Max framerate: ${formatFpsLabel(value)}`,
      "Could not change the max framerate"
    );
  };

  useEffect(() => {
    setFpsPresetIndex(normalizedFpsPresetIndex);
  }, [normalizedFpsPresetIndex]);

  if (!data) {
    return (
      <PanelSection title="Dashboard">
        <PanelSectionRow>
          <div style={{ ...cardStyle, ...subtextStyle }}>
            {loading ? "Loading dashboard..." : "Dashboard data is unavailable right now."}
          </div>
        </PanelSectionRow>
        {error && (
          <PanelSectionRow>
            <StatusCard title="Refresh Failed" message={error} tone="error" />
          </PanelSectionRow>
        )}
        {!loading && (
          <PanelSectionRow>
            <div style={actionButtonRowStyle}>
              <SecondaryActionButton label="Retry" onClick={() => void onRefresh()} />
            </div>
          </PanelSectionRow>
        )}
      </PanelSection>
    );
  }

  return (
    <PanelSection title="Dashboard">
      {error && (
        <PanelSectionRow>
          <StatusCard
            title="Last Refresh Failed"
            message={error}
            tone="error"
          />
        </PanelSectionRow>
      )}
      <PanelSectionRow>
        <div style={cardStyle}>
          <div style={viewTitleStyle}>Performance Modes</div>
          <div style={subtextStyle}>
            Choose the handheld's overall behavior directly.
          </div>
        </div>
      </PanelSectionRow>

      {!data.profiles_available && (
        <PanelSectionRow>
          <div style={{ ...cardStyle, ...subtextStyle }}>{data.profiles_status}</div>
        </PanelSectionRow>
      )}

      <PanelSectionRow>
        <div style={performanceModeGridStyle}>
          {data.performance_modes.map((mode) => (
            <NativeOptionButton
              key={mode.id}
              title={mode.label}
              description={compactPerformanceDescription(mode.id)}
              status={mode.active ? "Active" : mode.available ? "Ready" : "Unavailable"}
              active={mode.active}
              disabled={!mode.available || controlsDisabled}
              icon={<PerformanceModeGlyph modeId={mode.id} active={mode.active} />}
              onClick={() => handlePerformanceProfile(mode.native_id, mode.label)}
            />
          ))}
        </div>
      </PanelSectionRow>

      <PanelSectionRow>
        <ToggleField
          label={formatToggleLabel("CPU Boost", data.cpu_boost)}
          description={data.cpu_boost.details}
          checked={data.cpu_boost.enabled}
          disabled={!data.cpu_boost.available || controlsDisabled}
          onChange={handleBoost}
        />
      </PanelSectionRow>

      <PanelSectionRow>
        <ToggleField
          label={formatToggleLabel("SMT", data.smt)}
          description={data.smt.details}
          checked={data.smt.enabled}
          disabled={!data.smt.available || controlsDisabled}
          onChange={handleSmt}
        />
      </PanelSectionRow>

      <PanelSectionRow>
        <ToggleField
          label={`Charge limit: ${
            data.charge_limit.enabled ? `${data.charge_limit.limit}%` : "disabled"
          }`}
          description={data.charge_limit.details}
          checked={data.charge_limit.enabled}
          disabled={!data.charge_limit.available || controlsDisabled}
          onChange={handleChargeLimit}
        />
      </PanelSectionRow>

      <PanelSectionRow>
        <ToggleField
          label={`VRR: ${formatDisplayStatus(data.vrr).toLowerCase()}`}
          description={
            data.vrr.available
              ? data.vrr.active
                ? "VRR currently active"
                : data.vrr.details || data.vrr.status
              : data.vrr.status || data.vrr.details
          }
          checked={data.vrr.enabled}
          disabled={!data.vrr.available || controlsDisabled}
          onChange={(enabled: boolean) => handleSync("vrr", enabled)}
        />
      </PanelSectionRow>

      <PanelSectionRow>
        <ToggleField
          label={`V-Sync: ${formatDisplayStatus(data.vsync).toLowerCase()}`}
          description={
            data.vsync.available
              ? data.vsync.details || data.vsync.status
              : data.vsync.status || data.vsync.details
          }
          checked={data.vsync.enabled}
          disabled={!data.vsync.available || controlsDisabled}
          onChange={(enabled: boolean) => handleSync("vsync", enabled)}
        />
      </PanelSectionRow>

      <PanelSectionRow>
        <SliderField
          label={`Max Framerate: ${formatFpsLabel(fpsPresetValue)}`}
          description={formatFpsReadout(data.fps_limit)}
          value={fpsPresetIndex}
          min={0}
          max={Math.max(0, fpsPresets.length - 1)}
          step={1}
          disabled={!data.fps_limit.available || controlsDisabled}
          showValue={false}
          notchCount={fpsPresets.length}
          notchTicksVisible
          validValues="steps"
          notchLabels={fpsPresets.map((preset, notchIndex) => ({
            notchIndex,
            label: preset === 0 ? "Off" : `${preset}`,
            value: notchIndex,
          }))}
          onChange={(value: number) => {
            const nextIndex = Math.max(0, Math.min(fpsPresets.length - 1, value));
            const nextPreset = fpsPresets[nextIndex];
            if (nextPreset === undefined || nextIndex === fpsPresetIndex) {
              return;
            }
            setFpsPresetIndex(nextIndex);
            void commitFpsLimit(nextPreset);
          }}
        />
      </PanelSectionRow>

      <PanelSectionRow>
        <div style={stackedActionButtonGroupStyle}>
          <SecondaryActionButton label="RGB" onClick={onOpenRgb} />
          <SecondaryActionButton label="Optimizations" onClick={onOpenOptimizations} />
          <SecondaryActionButton label="Information" onClick={onOpenInformation} />
        </div>
      </PanelSectionRow>
    </PanelSection>
  );
};

const OptimizationsView: VFC<{
  data: OptimizationData | null;
  loading: boolean;
  error: string | null;
  busyKey: string | null;
  onBack: () => void;
  onRefresh: () => Promise<void>;
}> = ({ data, loading, error, busyKey, onBack, onRefresh }) => {
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const controlsDisabled = busyKey !== null || actionBusy !== null;

  const runAction = async (
    actionKey: string,
    operation: () => Promise<void>,
    successMessage: string,
    failureMessage: string
  ) => {
    if (controlsDisabled) {
      return;
    }

    setActionBusy(actionKey);
    let success = true;
    try {
      await operation();
    } catch (_error) {
      success = false;
    }
    toaster.toast({
      title: PLUGIN_NAME,
      body: success ? successMessage : failureMessage,
    });
    try {
      await onRefresh();
    } finally {
      setActionBusy(null);
    }
  };

  const handleEnableAvailable = async () => {
    if (controlsDisabled) {
      return;
    }

    setActionBusy("enable-available");
    try {
      const result = await enableAvailableOptimizations();
      toaster.toast({
        title: PLUGIN_NAME,
        body: result.success
          ? `Enabled ${result.enabled.length}; skipped ${result.skipped.length}.`
          : `Enabled ${result.enabled.length}; ${result.failed.length} failed.`,
      });
      await onRefresh();
    } finally {
      setActionBusy(null);
    }
  };

  const handleOptimizationToggle = async (
    optimization: OptimizationState,
    enabled: boolean
  ) => {
    await runAction(
      optimization.key,
      async () => {
        const success = await setOptimizationEnabled(optimization.key, enabled);
        if (!success) {
          throw new Error("toggle failed");
        }
      },
      `${optimization.name} ${enabled ? "enabled" : "disabled"}`,
      `Could not change ${optimization.name}`
    );
  };

  return (
    <div>
      <ViewHeader
        title="Optimizations"
        subtitle="Optional optimizations that can be disabled, sometimes requiring a reboot."
        onBack={onBack}
      />
      {!data ? (
        <PanelSection>
          <PanelSectionRow>
            <div style={{ ...cardStyle, ...subtextStyle }}>
              {loading ? "Loading optimizations..." : "Optimization data is unavailable right now."}
            </div>
          </PanelSectionRow>
          {error && (
            <PanelSectionRow>
              <StatusCard title="Refresh Failed" message={error} tone="error" />
            </PanelSectionRow>
          )}
          {!loading && (
            <PanelSectionRow>
              <div style={actionButtonRowStyle}>
                <SecondaryActionButton label="Retry" onClick={() => void onRefresh()} />
              </div>
            </PanelSectionRow>
          )}
        </PanelSection>
      ) : (
        <PanelSection title="Optimizations">
          {error && (
            <PanelSectionRow>
              <StatusCard title="Last Refresh Failed" message={error} tone="error" />
            </PanelSectionRow>
          )}
          <PanelSectionRow>
            <div style={actionButtonRowStyle}>
              <SecondaryActionButton
                label="Enable Available Optimizations"
                disabled={
                  controlsDisabled ||
                  !data.states.some(
                    (optimization) =>
                      optimization.available &&
                      optimization.mutable !== false &&
                      !optimization.enabled
                  )
                }
                onClick={handleEnableAvailable}
              />
            </div>
          </PanelSectionRow>
          {data.states.map((optimization) => (
            <PanelSectionRow key={optimization.key}>
              <ToggleField
                label={`${optimization.name}: ${optimization.status}`}
                description={`${optimization.description} ${optimization.details ? `${optimization.details}. ` : ""}${optimization.needs_reboot ? "Reboot required. " : ""}${optimization.risk_note}`.trim()}
                checked={optimization.enabled}
                disabled={!optimization.available || optimization.mutable === false || controlsDisabled}
                onChange={(enabled: boolean) =>
                  handleOptimizationToggle(optimization, enabled)
                }
              />
            </PanelSectionRow>
          ))}
        </PanelSection>
      )}
    </div>
  );
};

const RGBView: VFC<{
  data: DashboardState | null;
  loading: boolean;
  error: string | null;
  busyKey: string | null;
  onBack: () => void;
  onRefresh: () => Promise<void>;
}> = ({ data, loading, error, busyKey, onBack, onRefresh }) => {
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const controlsDisabled = busyKey !== null || actionBusy !== null;
  const rgb = data?.rgb;
  const rgbPresets = rgb?.presets?.length ? rgb.presets : RGB_PRESETS;
  const normalizedColor = normalizeHexColor(rgb?.color ?? rgbPresets[0]);
  const canToggleRgb = Boolean(rgb?.capabilities?.toggle ?? rgb?.available);
  const canAdjustColor = Boolean(rgb?.capabilities?.color ?? rgb?.supports_free_color ?? rgb?.available);
  const canAdjustBrightness = Boolean(rgb?.capabilities?.brightness ?? rgb?.brightness_available ?? rgb?.available);
  const currentEffectValue = rgbStateToEffect(rgb);
  const [hueValue, setHueValue] = useState<number>(hexToHue(normalizedColor));
  const [currentEffect, setCurrentEffect] = useState<string>(currentEffectValue);

  useEffect(() => {
    setHueValue(hexToHue(normalizedColor));
  }, [normalizedColor]);

  useEffect(() => {
    setCurrentEffect(currentEffectValue);
  }, [currentEffectValue]);

  const runAction = async (
    actionKey: string,
    operation: () => Promise<boolean>,
    successMessage: string,
    failureMessage: string
  ) => {
    if (controlsDisabled) {
      return;
    }

    setActionBusy(actionKey);
    let success = false;
    try {
      success = await operation();
      toaster.toast({
        title: PLUGIN_NAME,
        body: success ? successMessage : failureMessage,
      });
      await onRefresh();
    } finally {
      setActionBusy(null);
    }
  };

  const handleToggle = async (enabled: boolean) => {
    await runAction(
      "rgb-toggle",
      () => setRgbEnabled(enabled),
      `RGB ${enabled ? "enabled" : "disabled"}`,
      "Could not change RGB"
    );
  };

  const handleHueChange = async (value: number) => {
    const normalizedHue = clamp(value, 0, 360);
    setHueValue(normalizedHue);
    const nextColor = hueToHex(normalizedHue);
    const normalized = normalizeHexColor(nextColor);
    await runAction(
      `rgb:${normalized}`,
      () => setRgbColor(normalized),
      `RGB color: ${RGB_PRESET_LABELS[normalized] || normalized}`,
      "Could not change the RGB color"
    );
  };

  const handlePresetColor = async (color: string) => {
    const normalized = normalizeHexColor(color);
    setHueValue(hexToHue(normalized));
    await runAction(
      `rgb:${normalized}`,
      () => setRgbColor(normalized),
      `RGB color: ${RGB_PRESET_LABELS[normalized] || normalized}`,
      "Could not change the RGB color"
    );
  };

  const handleBrightnessChange = async (brightness: number) => {
    const normalized = clamp(brightness, 0, 100);
    await runAction(
      `rgb-brightness:${normalized}`,
      () => setRgbBrightness(normalized),
      `RGB brightness: ${normalized}%`,
      "Could not change RGB brightness"
    );
  };

  const handleEffectChange = async (effect: { data: string; label: string }) => {
    setCurrentEffect(effect.data);
    await runAction(
      `rgb-effect:${effect.data}`,
      () => setRgbEffect(effect.data),
      `RGB effect: ${effect.label}`,
      "Could not change RGB effect"
    );
  };

  const handleSpeedChange = async (speedValue: number) => {
    const speed =
      speedValue <= 33 ? "low" : speedValue <= 66 ? "medium" : "high";
    await runAction(
      `rgb-speed:${speed}`,
      () => setRgbSpeed(speed),
      `RGB speed: ${RGB_SPEED_LABELS[speed] || speed}`,
      "Could not change RGB speed"
    );
  };

  return (
    <div>
      <ViewHeader
        title="RGB"
        subtitle="Dedicated lighting controls with a cleaner preset workflow."
        onBack={onBack}
      />
      {!data || !rgb ? (
        <PanelSection>
          <PanelSectionRow>
            <div style={{ ...cardStyle, ...subtextStyle }}>
              {loading ? "Loading RGB controls..." : "RGB controls are unavailable right now."}
            </div>
          </PanelSectionRow>
          {error && (
            <PanelSectionRow>
              <StatusCard title="Refresh Failed" message={error} tone="error" />
            </PanelSectionRow>
          )}
          {!loading && (
            <PanelSectionRow>
              <div style={actionButtonRowStyle}>
                <SecondaryActionButton label="Retry" onClick={() => void onRefresh()} />
              </div>
            </PanelSectionRow>
          )}
        </PanelSection>
      ) : (
        <div>
          {error && (
            <PanelSection>
              <PanelSectionRow>
                <StatusCard title="Last Refresh Failed" message={error} tone="error" />
              </PanelSectionRow>
            </PanelSection>
          )}

          <PanelSection title="RGB Lighting">
            <PanelSectionRow>
              <ToggleField
                label="Enable RGB"
                description={rgb.details}
                checked={rgb.enabled}
                disabled={!canToggleRgb || controlsDisabled}
                onChange={handleToggle}
              />
            </PanelSectionRow>

            {rgb.enabled && (
              <div>
                <PanelSectionRow>
                  <SliderField
                    label="Color"
                    value={hueValue}
                    min={0}
                    max={360}
                    step={5}
                    disabled={!canAdjustColor || controlsDisabled}
                    onChange={handleHueChange}
                    showValue={false}
                  />
                </PanelSectionRow>
                <PanelSectionRow>
                  <div style={rgbHueRailStyle} />
                </PanelSectionRow>
                <PanelSectionRow>
                  <div style={rgbQuickSwatchGridStyle}>
                    {rgbPresets.map((color) => (
                      <button
                        key={color}
                        type="button"
                        disabled={!canAdjustColor || controlsDisabled}
                        style={{
                          ...rgbQuickSwatchButtonStyle(
                            normalizeHexColor(color) === normalizedColor,
                            color
                          ),
                          opacity: !canAdjustColor || controlsDisabled ? 0.45 : 1,
                        }}
                        onClick={() => void handlePresetColor(color)}
                      >
                        <div
                          style={{
                            height: "24px",
                            background: color,
                            borderBottom: "1px solid rgba(255,255,255,0.12)",
                          }}
                        />
                        <div
                          style={{
                            padding: "7px 6px 8px",
                            fontSize: "10px",
                            fontWeight: 700,
                            color: "#cbd5e1",
                            textAlign: "center",
                            lineHeight: 1.2,
                          }}
                        >
                          {RGB_PRESET_LABELS[color] || color.replace("#", "")}
                        </div>
                      </button>
                    ))}
                  </div>
                </PanelSectionRow>

                <PanelSectionRow>
                  <SliderField
                    label="Brightness"
                    value={clamp(rgb?.brightness ?? 100, 0, 100)}
                    min={0}
                    max={100}
                    step={10}
                    disabled={!canAdjustBrightness || controlsDisabled}
                    onChange={handleBrightnessChange}
                  />
                </PanelSectionRow>

                <PanelSectionRow>
                  <DropdownItem
                    label="Effect"
                    strDefaultLabel={
                      RGB_EFFECTS.find((effect) => effect.data === currentEffect)?.label ||
                      "Static"
                    }
                    menuLabel={
                      RGB_EFFECTS.find((effect) => effect.data === currentEffect)?.label ||
                      "Static"
                    }
                    rgOptions={RGB_EFFECTS}
                    selectedOption={
                      RGB_EFFECTS.find((effect) => effect.data === currentEffect) ||
                      RGB_EFFECTS[0]
                    }
                    onChange={handleEffectChange}
                  />
                </PanelSectionRow>

                {RGB_ANIMATED_EFFECTS.includes(currentEffect) && (
                  <PanelSectionRow>
                    <SliderField
                      label="Speed"
                      value={rgbSpeedToSliderValue(rgb?.speed)}
                      min={10}
                      max={100}
                      step={10}
                      disabled={controlsDisabled}
                      onChange={handleSpeedChange}
                    />
                  </PanelSectionRow>
                )}
              </div>
            )}

            {!rgb.enabled && (
              <PanelSectionRow>
                <div style={cardStyle}>
                  <div style={viewTitleStyle}>RGB Lighting</div>
                  <div style={subtextStyle}>
                    Toggle RGB on to access the same direct color, brightness, effect, and speed
                    workflow used by AllyCenter.
                  </div>
                </div>
              </PanelSectionRow>
            )}
          </PanelSection>
        </div>
      )}
    </div>
  );
};

const InformationView: VFC<{
  data: InformationState | null;
  loading: boolean;
  error: string | null;
  busyKey: string | null;
  onBack: () => void;
  onRefresh: () => Promise<void>;
  onClearDebug: () => Promise<void>;
}> = ({ data, loading, error, busyKey, onBack, onRefresh, onClearDebug }) => {
  const controlsDisabled = busyKey !== null;
  return (
    <div>
      <ViewHeader
        title="Information"
        subtitle="Detailed technical status for the handheld and available controls."
        onBack={onBack}
      />
      {!data ? (
        <PanelSection>
          <PanelSectionRow>
            <div style={{ ...cardStyle, ...subtextStyle }}>
              {loading ? "Loading information..." : "Information data is unavailable right now."}
            </div>
          </PanelSectionRow>
          {error && (
            <PanelSectionRow>
              <StatusCard title="Refresh Failed" message={error} tone="error" />
            </PanelSectionRow>
          )}
          {!loading && (
            <PanelSectionRow>
              <div style={actionButtonRowStyle}>
                <SecondaryActionButton label="Retry" onClick={() => void onRefresh()} />
              </div>
            </PanelSectionRow>
          )}
        </PanelSection>
      ) : (
        <div>
          {error && (
            <PanelSection title="Status">
              <PanelSectionRow>
                <StatusCard title="Last Refresh Failed" message={error} tone="error" />
              </PanelSectionRow>
            </PanelSection>
          )}
          <PanelSection title="Device">
            <PanelSectionRow>
              <div style={cardStyle}>
                <InfoRow label="Device" value={data.device.friendly_name} />
                <InfoRow label="Vendor" value={data.device.sys_vendor} />
                <InfoRow label="Variant" value={data.device.variant} />
                <InfoRow label="Board" value={data.device.board_name} />
                <InfoRow label="Support" value={data.device.support_level} />
                <InfoRow
                  label="Platform"
                  value={data.device.platform_support_reason || "Unknown"}
                />
                <InfoRow label="SteamOS" value={data.device.steamos_version} />
                <InfoRow label="Kernel" value={data.device.kernel} />
                <InfoRow label="BIOS" value={data.device.bios_version} />
              </div>
            </PanelSectionRow>
          </PanelSection>

          <PanelSection title="Hardware">
            <PanelSectionRow>
              <div style={cardStyle}>
                <InfoRow label="CPU" value={data.device.cpu} />
                <InfoRow label="GPU" value={data.device.gpu} />
                <InfoRow label="RAM" value={data.device.memory_total} />
                <InfoRow
                  label="Temp CPU"
                  value={formatPositiveMeasurement(data.temperatures.cpu, "°C")}
                />
                <InfoRow
                  label="Temp GPU"
                  value={formatPositiveMeasurement(data.temperatures.gpu, "°C")}
                />
                <InfoRow
                  label="GPU Clock"
                  value={formatPositiveMeasurement(data.temperatures.gpu_clock, "MHz")}
                />
              </div>
            </PanelSectionRow>
          </PanelSection>

          <PanelSection title="Battery">
            <PanelSectionRow>
              <div style={cardStyle}>
                <InfoRow
                  label="Status"
                  value={
                    data.battery.present
                      ? `${data.battery.capacity}% (${data.battery.status})`
                      : "Battery not detected"
                  }
                />
                <InfoRow label="Health" value={`${data.battery.health}%`} />
                <InfoRow
                  label="Cycles"
                  value={String(data.battery.cycle_count)}
                />
                <InfoRow
                  label="Temperature"
                  value={formatPositiveMeasurement(data.battery.temperature, "°C")}
                />
                <InfoRow
                  label="Charge limit"
                  value={`${data.battery.charge_limit}%`}
                />
                <InfoRow
                  label="Voltage"
                  value={formatPositiveMeasurement(data.battery.voltage, "V")}
                />
                <InfoRow
                  label="Current"
                  value={formatSignedMeasurement(data.battery.current, "A")}
                />
                <InfoRow
                  label="Design capacity"
                  value={formatPositiveMeasurement(data.battery.design_capacity, "Wh")}
                />
                <InfoRow
                  label="Full capacity"
                  value={formatPositiveMeasurement(data.battery.full_capacity, "Wh")}
                />
                <InfoRow label="Time to empty" value={data.battery.time_to_empty || "Unknown"} />
                <InfoRow label="Time to full" value={data.battery.time_to_full || "Unknown"} />
              </div>
            </PanelSectionRow>
          </PanelSection>

          <PanelSection title="SteamOS / Display">
            <PanelSectionRow>
              <div style={cardStyle}>
                <InfoRow
                  label="Current profile"
                  value={data.performance.current_profile || "Unknown"}
                />
                <InfoRow
                  label="Native profiles"
                  value={data.performance.available_native.join(", ") || "None"}
                />
                <InfoRow
                  label="VRR"
                  value={formatDisplayStatus(data.display.vrr)}
                />
                <InfoRow
                  label="V-Sync"
                  value={formatDisplayStatus(data.display.vsync)}
                />
                <InfoRow
                  label="Max Framerate"
                  value={formatFpsLabel(data.fps_limit.current)}
                />
                <InfoRow
                  label="Current TDP"
                  value={formatPositiveMeasurement(data.temperatures.tdp, "W")}
                />
              </div>
            </PanelSectionRow>
          </PanelSection>

          <PanelSection title="Runtime Diagnostics">
            <PanelSectionRow>
              <div style={cardStyle}>
                <InfoRow
                  label="Execution"
                  value={
                    data.runtime.execution_backend === "flatpak-host"
                      ? "flatpak-spawn --host"
                      : "Direct"
                  }
                />
                <InfoRow
                  label="OS release"
                  value={data.runtime.os_release_path || "Unknown"}
                />
                <InfoRow
                  label="Host OS ID"
                  value={data.runtime.host_os_id || "Unknown"}
                />
                <InfoRow
                  label="SteamOS bus"
                  value={data.runtime.steamos_manager_bus || "none"}
                />
                <InfoRow
                  label="Backend user"
                  value={data.runtime.privileges.user || "Unknown"}
                />
                <InfoRow
                  label="EUID"
                  value={`${data.runtime.privileges.effective_uid ?? "Unknown"}`}
                />
                <InfoRow
                  label="Root"
                  value={data.runtime.privileges.is_root ? "Yes" : "No"}
                />
                <InfoRow
                  label="Passwordless sudo"
                  value={data.runtime.privileges.sudo_noninteractive ? "Yes" : "No"}
                />
                <InfoRow
                  label="System writes"
                  value={data.runtime.privileges.system_write_access ? "Available" : "Blocked"}
                />
                <InfoRow
                  label="DISPLAY"
                  value={data.runtime.display_env.display || "Unavailable"}
                />
                <InfoRow
                  label="XAUTHORITY"
                  value={data.runtime.display_env.xauthority || "Unavailable"}
                />
                <InfoRow
                  label="Gamescope env"
                  value={data.runtime.display_env.gamescope_env_path || "Unavailable"}
                />
                <InfoRow
                  label="Gamescope wayland"
                  value={data.runtime.display_env.gamescope_wayland_display || "Unavailable"}
                />
                {Object.entries(data.runtime.commands).map(([command, info]) => (
                  <InfoRow
                    key={command}
                    label={command}
                    value={
                      info.available
                        ? `${info.via_host ? "Host" : "Direct"}${info.path ? `: ${info.path}` : ""}`
                        : "Unavailable"
                    }
                  />
                ))}
              </div>
            </PanelSectionRow>
          </PanelSection>

          <PanelSection title="Optimizations">
            <PanelSectionRow>
              <div style={cardStyle}>
                {data.optimizations.map((optimization) => (
                  <div key={optimization.key} style={{ marginBottom: "10px" }}>
                    <div
                      style={{
                        ...statusRowStyle,
                        marginBottom: "2px",
                      }}
                    >
                      <div style={{ color: "#ffffff", fontSize: "12px", fontWeight: 700 }}>
                        {optimization.name}
                      </div>
                      <div
                        style={{
                          color: statusColor(optimization.status),
                          fontSize: "12px",
                          textTransform: "capitalize",
                        }}
                      >
                        {optimization.status}
                      </div>
                    </div>
                    <div style={subtextStyle}>{optimization.description}</div>
                  </div>
                ))}
              </div>
            </PanelSectionRow>
          </PanelSection>

          <PanelSection title="Available Controls">
            <PanelSectionRow>
              <div style={cardStyle}>
                {Object.entries(data.hardware_controls).map(([key, supported]) => (
                  <InfoRow
                    key={key}
                    label={hardwareControlLabels[key] || key}
                    value={supported ? "Available" : "Unavailable"}
                  />
                ))}
              </div>
            </PanelSectionRow>
          </PanelSection>

          <PanelSection title="Debug">
            <PanelSectionRow>
              <div style={cardStyle}>
                <div style={{ ...statusRowStyle, marginBottom: "8px" }}>
                  <div style={{ color: "#ffffff", fontSize: "12px", fontWeight: 700 }}>
                    Runtime Log
                  </div>
                  <div style={{ color: "#94a3b8", fontSize: "11px" }}>
                    {data.debug_log.length} entries
                  </div>
                </div>
                <div style={subtextStyle}>
                  Tracks attempts, successes, failures, and state snapshots for performance,
                  CPU, display, optimizations, and RGB controls.
                </div>
              </div>
            </PanelSectionRow>
            <PanelSectionRow>
              <div style={actionButtonRowStyle}>
                <SecondaryActionButton
                  label="Clear Debug Log"
                  disabled={controlsDisabled}
                  onClick={() => void onClearDebug()}
                />
              </div>
            </PanelSectionRow>
            <PanelSectionRow>
              <div style={cardStyle}>
                {data.debug_log.length === 0 ? (
                  <div style={subtextStyle}>No debug entries yet.</div>
                ) : (
                  [...data.debug_log].reverse().map((entry, index) => (
                    <div
                      key={`${entry.timestamp}-${index}`}
                      style={{
                        padding: "8px 0",
                        borderBottom:
                          index === data.debug_log.length - 1
                            ? "none"
                            : "1px solid rgba(148, 163, 184, 0.15)",
                      }}
                    >
                      <div style={{ ...debugLogStyle, color: statusColor(entry.status) }}>
                        [{entry.status.toUpperCase()}] {entry.area}.{entry.action}
                      </div>
                      <div style={{ ...debugLogStyle, color: "#94a3b8" }}>{entry.timestamp}</div>
                      <div style={debugLogStyle}>{entry.message}</div>
                      <div style={{ ...debugLogStyle, color: "#8fb7ff" }}>
                        {JSON.stringify(entry.details)}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </PanelSectionRow>
          </PanelSection>
        </div>
      )}
    </div>
  );
};

const AnyDeckContent: VFC = () => {
  const [view, setView] = useState<ViewName>("dashboard");
  const [dashboard, setDashboard] = useState<DashboardState | null>(null);
  const [optimizations, setOptimizations] = useState<OptimizationData | null>(null);
  const [information, setInformation] = useState<InformationState | null>(null);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const [optimizationsError, setOptimizationsError] = useState<string | null>(null);
  const [informationError, setInformationError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const refreshDashboard = async (options?: { silent?: boolean }) => {
    const silent = options?.silent ?? false;
    if (!silent) {
      setBusyKey("dashboard");
    }
    try {
      setDashboard(await getDashboardState());
      setDashboardError(null);
    } catch (error) {
      console.error("Failed to refresh dashboard:", error);
      if (!silent) {
        setDashboardError(describeError(error));
      }
    } finally {
      if (!silent) {
        setBusyKey(null);
      }
      setLoading(false);
    }
  };

  const refreshOptimizations = async () => {
    setBusyKey("optimizations");
    try {
      setOptimizations(await getOptimizationStates());
      setOptimizationsError(null);
    } catch (error) {
      console.error("Failed to refresh optimizations:", error);
      setOptimizationsError(describeError(error));
    } finally {
      setBusyKey(null);
      setLoading(false);
    }
  };

  const refreshInformation = async () => {
    setBusyKey("information");
    try {
      setInformation(await getInformationState());
      setInformationError(null);
    } catch (error) {
      console.error("Failed to refresh information:", error);
      setInformationError(describeError(error));
    } finally {
      setBusyKey(null);
      setLoading(false);
    }
  };

  const handleClearDebugLog = async () => {
    setBusyKey("information");
    try {
      const success = await clearDebugLog();
      toaster.toast({
        title: PLUGIN_NAME,
        body: success ? "Debug log cleared" : "Could not clear debug log",
      });
      await refreshInformation();
    } catch (error) {
      console.error("Failed to clear debug log:", error);
      toaster.toast({
        title: PLUGIN_NAME,
        body: "Could not clear debug log",
      });
    } finally {
      setBusyKey(null);
    }
  };

  useEffect(() => {
    if (view === "dashboard" || view === "rgb") {
      void refreshDashboard();
      if (view === "dashboard") {
        const interval = setInterval(() => {
          void refreshDashboard({ silent: true });
        }, 5000);
        return () => clearInterval(interval);
      }
      return;
    }

    if (view === "optimizations") {
      void refreshOptimizations();
      return;
    }

    void refreshInformation();
  }, [view]);

  if (view === "optimizations") {
    return (
      <OptimizationsView
        data={optimizations}
        loading={loading}
        error={optimizationsError}
        busyKey={busyKey}
        onBack={() => setView("dashboard")}
        onRefresh={refreshOptimizations}
      />
    );
  }

  if (view === "rgb") {
    return (
      <RGBView
        data={dashboard}
        loading={loading}
        error={dashboardError}
        busyKey={busyKey}
        onBack={() => setView("dashboard")}
        onRefresh={refreshDashboard}
      />
    );
  }

  if (view === "information") {
    return (
      <InformationView
        data={information}
        loading={loading}
        error={informationError}
        busyKey={busyKey}
        onBack={() => setView("dashboard")}
        onRefresh={refreshInformation}
        onClearDebug={handleClearDebugLog}
      />
    );
  }

  return (
    <DashboardView
      data={dashboard}
      loading={loading}
      error={dashboardError}
      busyKey={busyKey}
      onRefresh={refreshDashboard}
      onOpenRgb={() => {
        setLoading(true);
        setView("rgb");
      }}
      onOpenOptimizations={() => {
        setLoading(true);
        setView("optimizations");
      }}
      onOpenInformation={() => {
        setLoading(true);
        setView("information");
      }}
    />
  );
};

const AnyDeckIcon: VFC = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" width="1em" height="1em">
    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" />
  </svg>
);

export default definePlugin(() => {
  console.log("AnyDeck plugin loaded!");

  return {
    name: "AnyDeck",
    title: <div className={staticClasses.Title}>AnyDeck</div>,
    content: <AnyDeckContent />,
    icon: <AnyDeckIcon />,
    onDismount() {
      console.log("AnyDeck plugin unloaded!");
    },
  };
});
