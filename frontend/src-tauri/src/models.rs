use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopEnvironment {
    pub platform: String,
    pub app_version: String,
    pub app_data_dir: String,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
#[serde(default)]
pub struct DesktopPreferences {
    pub backend_url: String,
    pub auto_start_local_stack: bool,
    pub notifications_enabled: bool,
    #[serde(default = "default_auto_check_updates")]
    pub auto_check_updates: bool,
    pub last_update_check_at: Option<String>,
    pub update_channel: UpdateChannel,
    pub project_root: Option<String>,
    pub project_name: Option<String>,
    pub profile: Option<StackProfile>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopPreferencesPatch {
    pub backend_url: Option<String>,
    pub auto_start_local_stack: Option<bool>,
    pub notifications_enabled: Option<bool>,
    pub auto_check_updates: Option<bool>,
    pub last_update_check_at: Option<String>,
    pub update_channel: Option<UpdateChannel>,
}

#[derive(Debug, Clone, Copy, Default, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum UpdateChannel {
    #[default]
    Stable,
}

fn default_auto_check_updates() -> bool {
    true
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum StackProfile {
    Source,
    WindowsImage,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct StackBinding {
    pub project_root: String,
    pub project_name: String,
    pub profile: StackProfile,
    pub source: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DockerStatus {
    Ready,
    NotInstalled,
    NotRunning,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum BackendHealthStatus {
    Ready,
    Starting,
    Unreachable,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ServiceStatus {
    Healthy,
    Running,
    Starting,
    Stopped,
    Error,
    Unknown,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ServiceState {
    pub name: String,
    pub status: ServiceStatus,
    pub detail: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LocalStackStatus {
    pub project_root: Option<String>,
    pub project_name: Option<String>,
    pub profile: Option<StackProfile>,
    pub docker: DockerStatus,
    pub compose_available: bool,
    pub backend_health: BackendHealthStatus,
    pub services: Vec<ServiceState>,
    pub error: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct StartStackOptions {
    pub rebuild: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct StackProgress {
    pub stage: String,
    pub message: String,
    pub detail: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct StackOperation {
    pub action: String,
    pub success: bool,
    pub status: LocalStackStatus,
}

#[derive(Debug, Clone, Copy, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ServiceName {
    Backend,
    Postgres,
    Redis,
}

impl ServiceName {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Backend => "backend",
            Self::Postgres => "postgres",
            Self::Redis => "redis",
        }
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ServiceLogTail {
    pub service: String,
    pub lines: Vec<String>,
    pub truncated: bool,
    pub sanitized: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DiagnosticsExport {
    pub file_token: String,
    pub suggested_name: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopOpenResult {
    pub opened: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopSaveResult {
    pub saved: bool,
    pub file_name: Option<String>,
}

#[derive(Debug, Clone, Copy, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DesktopNotificationKind {
    Done,
    Error,
    Attention,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopNotificationInput {
    pub notification_id: String,
    pub conversation_id: String,
    pub kind: DesktopNotificationKind,
    pub agent_label: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopNotificationActivation {
    pub notification_id: String,
    pub conversation_id: String,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case", tag = "kind")]
pub enum DesktopDeepLinkActivation {
    Chat {
        conversation_id: String,
    },
    Notification {
        notification_id: String,
        conversation_id: String,
    },
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopReleaseInfo {
    pub app_version: String,
    pub update_channel: UpdateChannel,
    pub update_endpoint: String,
    pub release_page_url: String,
    pub installer_kind: String,
    pub auto_check_updates: bool,
    pub last_update_check_at: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopUpdateCheckResult {
    pub checked_at: String,
    pub available: bool,
    pub current_version: String,
    pub version: Option<String>,
    pub date: Option<String>,
    pub body: Option<String>,
    pub release_page_url: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopUpdateInstallResult {
    pub installed: bool,
    pub restart_required: bool,
    pub version: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopCrashReport {
    pub exists: bool,
    pub lines: Vec<String>,
    pub truncated: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AuditEntry {
    pub timestamp: String,
    pub action: String,
    pub result: String,
    pub duration_ms: u128,
    pub app_version: String,
}
