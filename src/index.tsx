import {
  definePlugin,
  PanelSection,
  PanelSectionRow,
  ButtonItem,
  ToggleField,
  staticClasses,
} from "@decky/ui";
import { callable, toaster } from "@decky/api";

const { useEffect, useState } = window.SP_REACT;
type VFC<P = {}> = (props: P) => JSX.Element | null;

const PLUGIN_NAME = "Xbox Companion";
const RGB_PRESETS = ["#FF0000", "#00B7FF", "#00FF85", "#FFFFFF"];

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
  color: string;
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

type ViewName = "dashboard" | "optimizations" | "information";

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

const colorPresetGridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
  gap: "8px",
  width: "100%",
};

const optionGridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
  gap: "8px",
  width: "100%",
};

const presetButtonStyle = (active: boolean): React.CSSProperties => ({
  borderRadius: "10px",
  padding: "8px 6px",
  textAlign: "center",
  fontSize: "11px",
  fontWeight: 700,
  color: active ? "#0f172a" : "#ffffff",
  background: active ? "#60a5fa" : "rgba(51, 65, 85, 0.85)",
  border: active
    ? "1px solid rgba(147, 197, 253, 0.8)"
    : "1px solid rgba(100, 116, 139, 0.4)",
});

const modeButtonStyle = (active: boolean, disabled: boolean): React.CSSProperties => ({
  width: "100%",
  borderRadius: "12px",
  padding: "9px 10px",
  background: active
    ? "linear-gradient(180deg, #60a5fa, #3b82f6)"
    : "linear-gradient(180deg, rgba(51,65,85,0.9), rgba(30,41,59,0.9))",
  border: active
    ? "1px solid rgba(191, 219, 254, 0.9)"
    : "1px solid rgba(100, 116, 139, 0.35)",
  opacity: disabled ? 0.45 : 1,
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
  onOpenOptimizations: () => void;
  onOpenInformation: () => void;
}> = ({
  data,
  loading,
  error,
  busyKey,
  onRefresh,
  onOpenOptimizations,
  onOpenInformation,
}) => {
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const controlsDisabled = busyKey !== null || actionBusy !== null;
  const fpsPresets = data?.fps_limit.presets?.length
    ? data.fps_limit.presets
    : [30, 40, 60, 0];

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

  const handleRgbToggle = async (enabled: boolean) => {
    await runAction(
      "rgb-toggle",
      () => setRgbEnabled(enabled),
      `RGB ${enabled ? "enabled" : "disabled"}`,
      "Could not change RGB"
    );
  };

  const handleRgbColor = async (color: string) => {
    await runAction(
      `rgb:${color}`,
      () => setRgbColor(color),
      `RGB color: ${color}`,
      "Could not change the RGB color"
    );
  };

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

      {data.performance_modes.map((mode) => (
        <PanelSectionRow key={mode.id}>
          <ButtonItem
            layout="below"
            onClick={() => handlePerformanceProfile(mode.native_id, mode.label)}
            disabled={!mode.available || controlsDisabled}
          >
            <div style={modeButtonStyle(mode.active, !mode.available || controlsDisabled)}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: "12px",
                }}
              >
                <div
                  style={{
                    color: mode.active ? "#0f172a" : "#ffffff",
                    fontWeight: 800,
                    fontSize: "13px",
                  }}
                >
                  {mode.label}
                </div>
                {mode.active && (
                  <div
                    style={{
                      color: "#0f172a",
                      fontSize: "11px",
                      fontWeight: 700,
                    }}
                  >
                    Active
                  </div>
                )}
              </div>
              <div
                style={{
                  color: mode.active ? "rgba(15,23,42,0.85)" : "#cbd5e1",
                  fontSize: "11px",
                  marginTop: "4px",
                  lineHeight: 1.35,
                }}
              >
                {mode.available ? mode.description : "Mode unavailable on this system"}
              </div>
            </div>
          </ButtonItem>
        </PanelSectionRow>
      ))}

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

      {data.rgb.available && (
        <div>
          <PanelSectionRow>
            <ToggleField
              label={`RGB: ${data.rgb.enabled ? "enabled" : "disabled"}`}
              description={data.rgb.details}
              checked={data.rgb.enabled}
              disabled={!data.rgb.available || controlsDisabled}
              onChange={handleRgbToggle}
            />
          </PanelSectionRow>
          {data.rgb.enabled && (
            <PanelSectionRow>
              <div style={colorPresetGridStyle}>
                {(data.rgb.presets?.length ? data.rgb.presets : RGB_PRESETS).map((color) => (
                  <ButtonItem
                    key={color}
                    layout="below"
                    disabled={!data.rgb.available || controlsDisabled}
                    onClick={() => handleRgbColor(color)}
                  >
                    <div
                      style={{
                        ...presetButtonStyle(data.rgb.color === color),
                        background: color,
                        color: color === "#FFFFFF" ? "#0f172a" : "#ffffff",
                      }}
                    >
                      {color.replace("#", "")}
                    </div>
                  </ButtonItem>
                ))}
              </div>
            </PanelSectionRow>
          )}
        </div>
      )}

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
        <div style={cardStyle}>
          <div style={viewTitleStyle}>Max Framerate</div>
          <div style={subtextStyle}>{data.fps_limit.details}</div>
        </div>
      </PanelSectionRow>
      <PanelSectionRow>
        <div style={optionGridStyle}>
          {fpsPresets.map((preset) => (
            <ButtonItem
              key={preset}
              layout="below"
              disabled={!data.fps_limit.available || controlsDisabled}
              onClick={() => commitFpsLimit(preset)}
            >
              <div style={presetButtonStyle(data.fps_limit.current === preset)}>
                {formatFpsLabel(preset)}
              </div>
            </ButtonItem>
          ))}
        </div>
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
    if (view === "dashboard") {
      void refreshDashboard();
      const interval = setInterval(() => {
        void refreshDashboard({ silent: true });
      }, 5000);
      return () => clearInterval(interval);
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
