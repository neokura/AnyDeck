import {
  definePlugin,
  PanelSection,
  PanelSectionRow,
  ButtonItem,
  SliderField,
  ToggleField,
  staticClasses,
} from "@decky/ui";
import { callable, toaster } from "@decky/api";

const { useEffect, useState } = window.SP_REACT;
type VFC<P = {}> = (props: P) => JSX.Element | null;

const PLUGIN_NAME = "Xbox Companion";
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
};
const RGB_SPEED_LABELS: Record<string, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
};

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
const setPerformanceProfile = callable<[string], boolean>("set_performance_profile");
const setCpuBoostEnabled = callable<[boolean], boolean>("set_cpu_boost_enabled");
const setSmtEnabled = callable<[boolean], boolean>("set_smt_enabled");
const setRgbEnabled = callable<[boolean], boolean>("set_rgb_enabled");
const setRgbColor = callable<[string], boolean>("set_rgb_color");
const setRgbBrightness = callable<[number], boolean>("set_rgb_brightness");
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

const rgbModeButtonStyle = (active: boolean): React.CSSProperties => ({
  width: "100%",
  borderRadius: "10px",
  padding: "10px 8px",
  textAlign: "left",
  background: active
    ? "linear-gradient(180deg, #60a5fa, #3b82f6)"
    : "linear-gradient(180deg, rgba(51,65,85,0.92), rgba(30,41,59,0.92))",
  border: active
    ? "1px solid rgba(191, 219, 254, 0.9)"
    : "1px solid rgba(100, 116, 139, 0.35)",
});

const compactModeButtonStyle = (active: boolean, disabled: boolean): React.CSSProperties => ({
  width: "100%",
  minWidth: 0,
  borderRadius: "12px",
  padding: "10px 8px",
  background: active
    ? "linear-gradient(180deg, #60a5fa, #3b82f6)"
    : "linear-gradient(180deg, rgba(51,65,85,0.9), rgba(30,41,59,0.9))",
  border: active
    ? "1px solid rgba(191, 219, 254, 0.9)"
    : "1px solid rgba(100, 116, 139, 0.35)",
  opacity: disabled ? 0.45 : 1,
  overflow: "hidden",
});

const statusColor = (status: string): string => {
  switch (status) {
    case "active":
      return "#4ade80";
    case "configured":
      return "#60a5fa";
    case "reboot-required":
      return "#f59e0b";
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

const PerformanceModeGlyph: VFC<{ modeId: string; active: boolean }> = ({
  modeId,
  active,
}) => {
  const stroke = active ? "#0f172a" : "#e2e8f0";
  const fill = "none";

  if (modeId === "low-power") {
    return (
      <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
        <rect x="6" y="8" width="10" height="8" rx="2" stroke={stroke} strokeWidth="1.8" fill={fill} />
        <path d="M17 10.5H18.5V13.5H17" stroke={stroke} strokeWidth="1.8" strokeLinecap="round" />
        <path d="M8.5 12H10.4" stroke={stroke} strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    );
  }

  if (modeId === "balanced") {
    return (
      <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
        <path d="M12 5L18 8.5V15.5L12 19L6 15.5V8.5L12 5Z" stroke={stroke} strokeWidth="1.8" fill={fill} />
        <path d="M9 12H15" stroke={stroke} strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
      <path d="M13 3L6 13H11L10 21L18 10H13L13 3Z" stroke={stroke} strokeWidth="1.8" fill={fill} strokeLinejoin="round" />
    </svg>
  );
};

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
        <ButtonItem layout="below" onClick={onBack}>
          {backLabel || "Back"}
        </ButtonItem>
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
            <ButtonItem layout="below" onClick={() => void onRefresh()}>
              Retry
            </ButtonItem>
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
            <ButtonItem
              key={mode.id}
              layout="below"
              onClick={() => handlePerformanceProfile(mode.native_id, mode.label)}
              disabled={!mode.available || controlsDisabled}
            >
              <div style={compactModeButtonStyle(mode.active, !mode.available || controlsDisabled)}>
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "6px",
                    textAlign: "center",
                    minWidth: 0,
                  }}
                >
                  <PerformanceModeGlyph modeId={mode.id} active={mode.active} />
                  <div
                    style={{
                      color: mode.active ? "#0f172a" : "#ffffff",
                      fontWeight: 800,
                      fontSize: "11px",
                      lineHeight: 1.2,
                      overflowWrap: "anywhere",
                    }}
                  >
                    {mode.label}
                  </div>
                  <div
                    style={{
                      color: mode.active ? "rgba(15,23,42,0.82)" : "#94a3b8",
                      fontSize: "10px",
                      fontWeight: 700,
                      lineHeight: 1.2,
                    }}
                  >
                    {mode.active ? "Active" : mode.available ? "Ready" : "Unavailable"}
                  </div>
                </div>
              </div>
            </ButtonItem>
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
        <ButtonItem layout="below" onClick={onOpenRgb}>
          RGB
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={onOpenOptimizations}>
          Optimizations
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={onOpenInformation}>
          Information
        </ButtonItem>
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
              <ButtonItem layout="below" onClick={() => void onRefresh()}>
                Retry
              </ButtonItem>
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
            <ButtonItem
              layout="below"
              disabled={
                controlsDisabled ||
                !data.states.some((optimization) => optimization.available && !optimization.enabled)
              }
              onClick={handleEnableAvailable}
            >
              Enable Available Optimizations
            </ButtonItem>
          </PanelSectionRow>
          {data.states.map((optimization) => (
            <PanelSectionRow key={optimization.key}>
              <ToggleField
                label={`${optimization.name}: ${optimization.status}`}
                description={`${optimization.description} ${optimization.needs_reboot ? "Reboot required. " : ""}${optimization.risk_note}`.trim()}
                checked={optimization.enabled}
                disabled={!optimization.available || controlsDisabled}
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
  const [selectedColor, setSelectedColor] = useState<string>(normalizedColor);
  const [hueValue, setHueValue] = useState<number>(hexToHue(normalizedColor));
  const [brightnessValue, setBrightnessValue] = useState<number>(
    clamp(rgb?.brightness ?? 100, 0, 100)
  );
  const [selectedMode, setSelectedMode] = useState<string>(rgb?.mode ?? "solid");
  const [selectedSpeed, setSelectedSpeed] = useState<string>(rgb?.speed ?? "medium");
  const activeColor = selectedColor;
  const supportedModes = rgb?.supported_modes?.length ? rgb.supported_modes : ["solid"];
  const currentModeCapabilities = rgb?.mode_capabilities?.[selectedMode] ?? {
    color: true,
    brightness: true,
    speed: false,
  };
  const canToggleRgb = Boolean(rgb?.capabilities?.toggle ?? rgb?.available);
  const canAdjustColor = Boolean(currentModeCapabilities.color && (rgb?.supports_free_color ?? true));
  const canAdjustBrightness = Boolean(currentModeCapabilities.brightness && (rgb?.brightness_available ?? true));
  const canAdjustSpeed = Boolean(currentModeCapabilities.speed && (rgb?.speed_available ?? true));
  const controlScopeLabel = rgb?.enabled ? "Live output" : "Next output on enable";
  const controlScopeDescription = rgb?.enabled
    ? "Changes apply immediately."
    : "HueSync-style staging: these values are saved now and applied when RGB is turned back on.";

  useEffect(() => {
    setSelectedColor(normalizedColor);
    setHueValue(hexToHue(normalizedColor));
  }, [normalizedColor]);

  useEffect(() => {
    setBrightnessValue(clamp(rgb?.brightness ?? 100, 0, 100));
  }, [rgb?.brightness]);

  useEffect(() => {
    setSelectedMode(rgb?.mode ?? "solid");
  }, [rgb?.mode]);

  useEffect(() => {
    setSelectedSpeed(rgb?.speed ?? "medium");
  }, [rgb?.speed]);

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

  const handleRgbToggle = async (enabled: boolean) => {
    await runAction(
      "rgb-toggle",
      () => setRgbEnabled(enabled),
      `RGB ${enabled ? "enabled" : "disabled"}`,
      "Could not change RGB"
    );
  };

  const handleRgbColor = async (color: string) => {
    const normalized = normalizeHexColor(color);
    await runAction(
      `rgb:${normalized}`,
      () => setRgbColor(normalized),
      `RGB color: ${RGB_PRESET_LABELS[normalized] || normalized}`,
      "Could not change the RGB color"
    );
  };

  const handleRgbBrightness = async (brightness: number) => {
    const normalized = clamp(brightness, 0, 100);
    await runAction(
      `rgb-brightness:${normalized}`,
      () => setRgbBrightness(normalized),
      `RGB brightness: ${normalized}%`,
      "Could not change RGB brightness"
    );
  };

  const handleRgbMode = async (mode: string) => {
    await runAction(
      `rgb-mode:${mode}`,
      () => setRgbMode(mode),
      `RGB mode: ${RGB_MODE_LABELS[mode] || mode}`,
      "Could not change RGB mode"
    );
  };

  const handleRgbSpeed = async (speed: string) => {
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
              <ButtonItem layout="below" onClick={() => void onRefresh()}>
                Retry
              </ButtonItem>
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

          <PanelSection title="RGB">
            <PanelSectionRow>
              <ToggleField
                label={`RGB: ${rgb.enabled ? "enabled" : "disabled"}`}
                description={rgb.enabled ? rgb.details : `${rgb.details}. ${controlScopeDescription}`}
                checked={rgb.enabled}
                disabled={!canToggleRgb || controlsDisabled}
                onChange={handleRgbToggle}
              />
            </PanelSectionRow>

            <PanelSectionRow>
              <div style={cardStyle}>
                <div style={rgbHeroStyle(rgb.enabled, activeColor)}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "12px" }}>
                    <div>
                      <div style={{ color: "#ffffff", fontSize: "15px", fontWeight: 700 }}>
                        {rgb.enabled ? "Lighting Enabled" : "Lighting Disabled"}
                      </div>
                      <div style={{ ...subtextStyle, color: "rgba(255,255,255,0.8)" }}>
                        {controlScopeLabel}
                      </div>
                      <div style={{ ...subtextStyle, color: "rgba(255,255,255,0.8)" }}>
                        {RGB_MODE_LABELS[selectedMode] || selectedMode}
                      </div>
                    </div>
                    <div
                      style={{
                        color: rgb.enabled ? "#ffffff" : "#cbd5e1",
                        fontSize: "12px",
                        fontWeight: 700,
                        textAlign: "right",
                      }}
                    >
                      {RGB_PRESET_LABELS[activeColor] || activeColor}
                      <div style={{ marginTop: "4px", fontSize: "11px", fontWeight: 600 }}>
                        {brightnessValue}%
                      </div>
                    </div>
                  </div>

                  <div style={rgbSwatchStripStyle}>
                    {rgbPresets.map((color) => (
                      <div
                        key={color}
                        style={{
                          height: "18px",
                          borderRadius: "999px",
                          background: color,
                          border:
                            color === activeColor
                              ? "2px solid rgba(255,255,255,0.95)"
                              : "1px solid rgba(255,255,255,0.28)",
                          boxShadow:
                            rgb.enabled && color === activeColor
                              ? `0 0 18px ${color}`
                              : "none",
                        }}
                      />
                    ))}
                  </div>
                </div>
              </div>
            </PanelSectionRow>

            <PanelSectionRow>
              <div style={cardStyle}>
                <div style={viewTitleStyle}>Mode</div>
                <div style={subtextStyle}>
                  Native RGB modes only. Legion HID gets hardware `pulse` and `rainbow`; sysfs
                  stays on clean `solid`.
                </div>
                <div style={optionGridStyle}>
                  {supportedModes.map((mode) => {
                    const active = selectedMode === mode;
                    return (
                      <ButtonItem
                        key={mode}
                        layout="below"
                        disabled={controlsDisabled}
                        onClick={() => {
                          if (mode === selectedMode) {
                            return;
                          }
                          setSelectedMode(mode);
                          void handleRgbMode(mode);
                        }}
                      >
                        <div style={rgbModeButtonStyle(active)}>
                          <div
                            style={{
                              color: active ? "#0f172a" : "#ffffff",
                              fontSize: "12px",
                              fontWeight: 800,
                            }}
                          >
                            {RGB_MODE_LABELS[mode] || mode}
                          </div>
                          <div
                            style={{
                              color: active ? "rgba(15,23,42,0.82)" : "#cbd5e1",
                              fontSize: "10px",
                              marginTop: "4px",
                              lineHeight: 1.35,
                            }}
                          >
                            {mode === "solid"
                              ? "Static color"
                              : mode === "pulse"
                                ? "Native breathing effect"
                                : "Native cycling effect"}
                          </div>
                        </div>
                      </ButtonItem>
                    );
                  })}
                </div>
              </div>
            </PanelSectionRow>

            <PanelSectionRow>
              <div style={cardStyle}>
                <div style={viewTitleStyle}>Fine Control</div>
                <div style={subtextStyle}>{controlScopeDescription}</div>
              </div>
            </PanelSectionRow>

            <PanelSectionRow>
              <SliderField
                label={`Hue: ${RGB_PRESET_LABELS[activeColor] || activeColor}`}
                description={
                  canAdjustColor
                    ? rgb.enabled
                      ? "Free color selection across the full spectrum"
                      : "Choose the next color before enabling RGB"
                    : rgb.details
                }
                value={hueValue}
                min={0}
                max={360}
                step={5}
                disabled={!canAdjustColor || controlsDisabled}
                showValue={false}
                notchCount={7}
                notchTicksVisible
                validValues="range"
                notchLabels={[
                  "Red",
                  "Yellow",
                  "Green",
                  "Cyan",
                  "Blue",
                  "Magenta",
                  "Red",
                ].map((label, notchIndex) => ({
                  notchIndex,
                  label,
                  value: notchIndex * 60,
                }))}
                onChange={(value: number) => {
                  const normalizedHue = clamp(value, 0, 360);
                  const nextColor = hueToHex(normalizedHue);
                  if (nextColor === activeColor) {
                    return;
                  }
                  setHueValue(normalizedHue);
                  setSelectedColor(nextColor);
                  void handleRgbColor(nextColor);
                }}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <div style={rgbHueRailStyle} />
            </PanelSectionRow>

            <PanelSectionRow>
              <SliderField
                label={`Brightness: ${brightnessValue}%`}
                description={
                  canAdjustBrightness
                    ? "Shared intensity model normalized to 0-100 across supported devices"
                    : rgb.details
                }
                value={brightnessValue}
                min={0}
                max={100}
                step={5}
                disabled={!canAdjustBrightness || controlsDisabled}
                showValue={false}
                notchCount={6}
                notchTicksVisible
                validValues="range"
                notchLabels={[0, 20, 40, 60, 80, 100].map((value, notchIndex) => ({
                  notchIndex,
                  label: `${value}`,
                  value,
                }))}
                onChange={(value: number) => {
                  const normalizedBrightness = clamp(value, 0, 100);
                  if (normalizedBrightness === brightnessValue) {
                    return;
                  }
                  setBrightnessValue(normalizedBrightness);
                  void handleRgbBrightness(normalizedBrightness);
                }}
              />
            </PanelSectionRow>

            {canAdjustSpeed && (
              <PanelSectionRow>
                <div style={cardStyle}>
                  <div style={viewTitleStyle}>Animation Speed</div>
                  <div style={subtextStyle}>
                    Native animation speed for the current RGB mode.
                  </div>
                  <div style={optionGridStyle}>
                    {(rgb.speed_options?.length ? rgb.speed_options : ["low", "medium", "high"]).map(
                      (speed) => {
                        const active = selectedSpeed === speed;
                        return (
                          <ButtonItem
                            key={speed}
                            layout="below"
                            disabled={controlsDisabled}
                            onClick={() => {
                              if (speed === selectedSpeed) {
                                return;
                              }
                              setSelectedSpeed(speed);
                              void handleRgbSpeed(speed);
                            }}
                          >
                            <div style={rgbModeButtonStyle(active)}>
                              <div
                                style={{
                                  color: active ? "#0f172a" : "#ffffff",
                                  fontSize: "12px",
                                  fontWeight: 800,
                                }}
                              >
                                {RGB_SPEED_LABELS[speed] || speed}
                              </div>
                            </div>
                          </ButtonItem>
                        );
                      }
                    )}
                  </div>
                </div>
              </PanelSectionRow>
            )}

            <PanelSectionRow>
              <div style={cardStyle}>
                <div style={viewTitleStyle}>Palette</div>
                <div style={subtextStyle}>
                  Quick colors for the common looks, with free hue selection above for everything
                  else.
                </div>
                <div style={rgbPresetRailStyle(rgbPresets)} />
                <div style={rgbQuickSwatchGridStyle}>
                  {rgbPresets.map((color) => {
                    const active = activeColor === color;
                    return (
                      <button
                        key={color}
                        type="button"
                        disabled={!canAdjustColor || controlsDisabled}
                        style={{
                          ...rgbQuickSwatchButtonStyle(active, color),
                          opacity: !canAdjustColor || controlsDisabled ? 0.45 : 1,
                        }}
                        onClick={() => {
                          setSelectedColor(color);
                          setHueValue(hexToHue(color));
                          void handleRgbColor(color);
                        }}
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
                            color: active ? "#ffffff" : "#cbd5e1",
                            textAlign: "center",
                            lineHeight: 1.2,
                          }}
                        >
                          {RGB_PRESET_LABELS[color] || color.replace("#", "")}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            </PanelSectionRow>
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
  onBack: () => void;
  onRefresh: () => Promise<void>;
}> = ({ data, loading, error, onBack, onRefresh }) => {
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
              <ButtonItem layout="below" onClick={() => void onRefresh()}>
                Retry
              </ButtonItem>
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
        </div>
      )}
    </div>
  );
};

const XboxCompanionContent: VFC = () => {
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
        onBack={() => setView("dashboard")}
        onRefresh={refreshInformation}
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

const XboxCompanionIcon: VFC = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" width="1em" height="1em">
    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" />
  </svg>
);

export default definePlugin(() => {
  console.log("Xbox Companion plugin loaded!");

  return {
    name: "Xbox Companion",
    title: <div className={staticClasses.Title}>Xbox Companion</div>,
    content: <XboxCompanionContent />,
    icon: <XboxCompanionIcon />,
    onDismount() {
      console.log("Xbox Companion plugin unloaded!");
    },
  };
});
