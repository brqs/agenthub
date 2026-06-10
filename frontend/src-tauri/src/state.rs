use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Mutex as SyncMutex;

use tokio::sync::Mutex;

use crate::error::{DesktopError, DesktopResult};
use crate::models::{AuditEntry, BackendProfile, BackendProfileMode, DesktopPreferences};

pub struct AppState {
    pub app_data_dir: PathBuf,
    pub operation: Mutex<()>,
    diagnostics: SyncMutex<HashMap<String, PathBuf>>,
    #[cfg(windows)]
    pub notifications: SyncMutex<HashMap<String, windows::UI::Notifications::ToastNotification>>,
}

impl AppState {
    pub fn new(app_data_dir: PathBuf) -> DesktopResult<Self> {
        std::fs::create_dir_all(&app_data_dir)?;
        Ok(Self {
            app_data_dir,
            operation: Mutex::new(()),
            diagnostics: SyncMutex::new(HashMap::new()),
            #[cfg(windows)]
            notifications: SyncMutex::new(HashMap::new()),
        })
    }

    pub fn preferences_path(&self) -> PathBuf {
        self.app_data_dir.join("desktop-preferences.json")
    }

    pub fn audit_path(&self) -> PathBuf {
        self.app_data_dir.join("desktop-actions.jsonl")
    }

    pub fn diagnostics_dir(&self) -> PathBuf {
        self.app_data_dir.join("diagnostics")
    }

    pub fn crash_log_path(&self) -> PathBuf {
        self.app_data_dir.join("desktop-crashes.log")
    }

    pub fn load_preferences(&self) -> DesktopResult<DesktopPreferences> {
        load_preferences(&self.preferences_path())
    }

    pub fn save_preferences(&self, preferences: &DesktopPreferences) -> DesktopResult<()> {
        let bytes = serde_json::to_vec_pretty(preferences)?;
        std::fs::write(self.preferences_path(), bytes)?;
        Ok(())
    }

    pub fn append_audit(&self, entry: &AuditEntry) -> DesktopResult<()> {
        use std::io::Write;

        let mut file = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(self.audit_path())?;
        serde_json::to_writer(&mut file, entry)?;
        file.write_all(b"\n")?;
        Ok(())
    }

    pub fn register_diagnostic(&self, token: String, path: PathBuf) -> DesktopResult<()> {
        let mut diagnostics = self.diagnostics.lock().map_err(|_| {
            DesktopError::new(
                "desktop_state_unavailable",
                "桌面客户端暂时无法保存诊断文件状态。",
            )
        })?;
        diagnostics.insert(token, path);
        Ok(())
    }

    pub fn diagnostic_path(&self, token: &str) -> DesktopResult<PathBuf> {
        let diagnostics = self.diagnostics.lock().map_err(|_| {
            DesktopError::new(
                "desktop_state_unavailable",
                "桌面客户端暂时无法读取诊断文件状态。",
            )
        })?;
        diagnostics.get(token).cloned().ok_or_else(|| {
            DesktopError::new(
                "diagnostic_token_invalid",
                "诊断文件已失效，请重新导出后再保存。",
            )
        })
    }
}

fn load_preferences(path: &Path) -> DesktopResult<DesktopPreferences> {
    if !path.exists() {
        return Ok(normalize_preferences(DesktopPreferences {
            backend_url: "http://localhost:8000".to_string(),
            auto_check_updates: true,
            update_channel: crate::models::UpdateChannel::Stable,
            ..DesktopPreferences::default()
        }));
    }
    let bytes = std::fs::read(path)?;
    let mut preferences: DesktopPreferences = serde_json::from_slice(&bytes).map_err(|error| {
        DesktopError::with_detail(
            "desktop_preferences_invalid",
            "桌面客户端偏好文件无法读取。",
            error.to_string(),
        )
    })?;
    preferences = normalize_preferences(preferences);
    if !matches!(
        preferences.update_channel,
        crate::models::UpdateChannel::Stable
    ) {
        preferences.update_channel = crate::models::UpdateChannel::Stable;
    }
    Ok(preferences)
}

fn normalize_preferences(mut preferences: DesktopPreferences) -> DesktopPreferences {
    if preferences.backend_url.trim().is_empty() {
        preferences.backend_url = "http://localhost:8000".to_string();
    }
    if preferences.backend_profiles.is_empty() {
        let mode = if is_local_backend_url(&preferences.backend_url) {
            BackendProfileMode::Local
        } else {
            BackendProfileMode::Remote
        };
        preferences.backend_profiles.push(BackendProfile {
            id: "default".to_string(),
            name: if mode == BackendProfileMode::Local {
                "本地 AgentHub".to_string()
            } else {
                "AgentHub 服务器".to_string()
            },
            url: preferences.backend_url.clone(),
            mode,
            server_id: None,
            last_connected_at: None,
            last_health: None,
        });
    }
    let active_id = preferences
        .active_backend_profile_id
        .as_deref()
        .filter(|id| {
            preferences
                .backend_profiles
                .iter()
                .any(|profile| profile.id == *id)
        })
        .map(str::to_string)
        .or_else(|| {
            preferences
                .backend_profiles
                .iter()
                .find(|profile| profile.url == preferences.backend_url)
                .map(|profile| profile.id.clone())
        })
        .unwrap_or_else(|| preferences.backend_profiles[0].id.clone());
    preferences.active_backend_profile_id = Some(active_id.clone());
    if let Some(active) = preferences
        .backend_profiles
        .iter()
        .find(|profile| profile.id == active_id)
    {
        preferences.backend_url = active.url.clone();
    }
    preferences
}

fn is_local_backend_url(input: &str) -> bool {
    url::Url::parse(input)
        .ok()
        .and_then(|url| url.host_str().map(str::to_ascii_lowercase))
        .is_some_and(|host| matches!(host.as_str(), "localhost" | "127.0.0.1" | "::1"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn missing_preferences_use_safe_defaults() {
        let temp = tempfile::tempdir().expect("tempdir");
        let prefs = load_preferences(&temp.path().join("missing.json")).expect("preferences");
        assert_eq!(prefs.backend_url, "http://localhost:8000");
        assert!(!prefs.auto_start_local_stack);
        assert!(!prefs.notifications_enabled);
        assert!(prefs.auto_check_updates);
        assert_eq!(prefs.update_channel, crate::models::UpdateChannel::Stable);
        assert_eq!(prefs.backend_profiles.len(), 1);
        assert_eq!(prefs.active_backend_profile_id.as_deref(), Some("default"));
    }

    #[test]
    fn legacy_backend_url_is_migrated_to_a_profile() {
        let temp = tempfile::tempdir().expect("tempdir");
        let path = temp.path().join("desktop-preferences.json");
        std::fs::write(
            &path,
            br#"{"backendUrl":"https://agenthub.example.com","autoCheckUpdates":true}"#,
        )
        .expect("write preferences");

        let prefs = load_preferences(&path).expect("preferences");

        assert_eq!(prefs.backend_profiles.len(), 1);
        assert_eq!(prefs.backend_profiles[0].mode, BackendProfileMode::Remote);
        assert_eq!(prefs.backend_url, "https://agenthub.example.com");
    }

    #[test]
    fn diagnostic_tokens_only_resolve_registered_files() {
        let temp = tempfile::tempdir().expect("tempdir");
        let state = AppState::new(temp.path().to_path_buf()).expect("state");
        let diagnostic = temp.path().join("diagnostic.json");
        std::fs::write(&diagnostic, b"{}").expect("diagnostic");

        state
            .register_diagnostic("known-token".to_string(), diagnostic.clone())
            .expect("register");

        assert_eq!(
            state.diagnostic_path("known-token").expect("known token"),
            diagnostic
        );
        assert!(state.diagnostic_path("unknown-token").is_err());
    }
}
