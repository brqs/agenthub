use std::collections::HashSet;
use std::time::Duration;

use tauri::State;

use crate::error::DesktopResult;
use crate::models::{
    BackendProfile, BackendProfileMode, DesktopEnvironment, DesktopPreferences,
    DesktopPreferencesPatch, StackBinding,
};
use crate::project::{persist_binding, resolve_binding, validate_project_root};
use crate::state::AppState;

#[tauri::command]
pub fn desktop_get_environment(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
) -> DesktopEnvironment {
    DesktopEnvironment {
        platform: std::env::consts::OS.to_string(),
        app_version: app.package_info().version.to_string(),
        app_data_dir: state.app_data_dir.to_string_lossy().into_owned(),
    }
}

#[tauri::command]
pub fn desktop_get_preferences(state: State<'_, AppState>) -> DesktopResult<DesktopPreferences> {
    state.load_preferences()
}

#[tauri::command]
pub fn desktop_set_preferences(
    patch: DesktopPreferencesPatch,
    state: State<'_, AppState>,
) -> DesktopResult<DesktopPreferences> {
    let mut preferences = state.load_preferences()?;
    if let Some(profiles) = patch.backend_profiles {
        validate_backend_profiles(&profiles)?;
        preferences.backend_profiles = profiles;
    }
    if let Some(active_id) = patch.active_backend_profile_id {
        if !preferences
            .backend_profiles
            .iter()
            .any(|profile| profile.id == active_id)
        {
            return Err(crate::error::DesktopError::new(
                "backend_profile_not_found",
                "所选后端连接不存在。",
            ));
        }
        preferences.active_backend_profile_id = Some(active_id);
    }
    let active_id = preferences
        .active_backend_profile_id
        .clone()
        .unwrap_or_else(|| preferences.backend_profiles[0].id.clone());
    if !preferences
        .backend_profiles
        .iter()
        .any(|profile| profile.id == active_id)
    {
        return Err(crate::error::DesktopError::new(
            "backend_profile_not_found",
            "当前后端连接不能被删除，请先切换到其他连接。",
        ));
    }
    preferences.active_backend_profile_id = Some(active_id);
    if let Some(backend_url) = patch.backend_url {
        let trimmed = backend_url.trim();
        if !(trimmed.starts_with("http://") || trimmed.starts_with("https://")) {
            return Err(crate::error::DesktopError::new(
                "backend_url_invalid",
                "后端地址必须以 http:// 或 https:// 开头。",
            ));
        }
        let normalized = trimmed.trim_end_matches('/').to_string();
        preferences.backend_url = normalized.clone();
        if let Some(active_id) = preferences.active_backend_profile_id.as_deref() {
            if let Some(active) = preferences
                .backend_profiles
                .iter_mut()
                .find(|profile| profile.id == active_id)
            {
                active.url = normalized;
                active.mode = backend_profile_mode(&active.url)?;
                validate_backend_profile_url(active)?;
            }
        }
    }
    if let Some(active_id) = preferences.active_backend_profile_id.as_deref() {
        if let Some(active) = preferences
            .backend_profiles
            .iter()
            .find(|profile| profile.id == active_id)
        {
            preferences.backend_url = active.url.clone();
        }
    }
    if let Some(auto_start) = patch.auto_start_local_stack {
        preferences.auto_start_local_stack = auto_start;
    }
    if let Some(enabled) = patch.notifications_enabled {
        preferences.notifications_enabled = enabled;
    }
    if let Some(auto_check_updates) = patch.auto_check_updates {
        preferences.auto_check_updates = auto_check_updates;
    }
    if let Some(last_update_check_at) = patch.last_update_check_at {
        preferences.last_update_check_at = Some(last_update_check_at);
    }
    if let Some(update_channel) = patch.update_channel {
        preferences.update_channel = update_channel;
    }
    state.save_preferences(&preferences)?;
    Ok(preferences)
}

fn validate_backend_profiles(profiles: &[BackendProfile]) -> DesktopResult<()> {
    if profiles.is_empty() || profiles.len() > 20 {
        return Err(crate::error::DesktopError::new(
            "backend_profiles_invalid",
            "至少需要保留一个后端连接，且最多保存 20 个。",
        ));
    }
    let mut ids = HashSet::new();
    for profile in profiles {
        if profile.id.trim().is_empty()
            || profile.id.len() > 64
            || profile.name.trim().is_empty()
            || profile.name.len() > 64
            || !ids.insert(profile.id.as_str())
        {
            return Err(crate::error::DesktopError::new(
                "backend_profile_invalid",
                "后端连接名称或标识无效。",
            ));
        }
        validate_backend_profile_url(profile)?;
    }
    Ok(())
}

fn validate_backend_profile_url(profile: &BackendProfile) -> DesktopResult<()> {
    let parsed = url::Url::parse(&profile.url).map_err(|_| {
        crate::error::DesktopError::new("backend_url_invalid", "后端地址格式无效。")
    })?;
    if parsed.username() != ""
        || parsed.password().is_some()
        || parsed.query().is_some()
        || parsed.fragment().is_some()
    {
        return Err(crate::error::DesktopError::new(
            "backend_url_invalid",
            "后端地址不能包含账号、密码、查询参数或片段。",
        ));
    }
    let host = parsed.host_str().unwrap_or_default().to_ascii_lowercase();
    let local = matches!(host.as_str(), "localhost" | "127.0.0.1" | "::1");
    match profile.mode {
        BackendProfileMode::Local if !local || parsed.scheme() != "http" => {
            Err(crate::error::DesktopError::new(
                "backend_url_invalid",
                "本地后端必须使用 localhost 或回环地址。",
            ))
        }
        BackendProfileMode::Remote if local || parsed.scheme() != "https" => Err(
            crate::error::DesktopError::new("backend_url_insecure", "公网后端必须使用 HTTPS。"),
        ),
        _ => Ok(()),
    }
}

fn backend_profile_mode(url: &str) -> DesktopResult<BackendProfileMode> {
    let parsed = url::Url::parse(url).map_err(|_| {
        crate::error::DesktopError::new("backend_url_invalid", "后端地址格式无效。")
    })?;
    let host = parsed.host_str().unwrap_or_default().to_ascii_lowercase();
    if matches!(host.as_str(), "localhost" | "127.0.0.1" | "::1") {
        Ok(BackendProfileMode::Local)
    } else {
        Ok(BackendProfileMode::Remote)
    }
}

#[tauri::command]
pub async fn desktop_choose_project_root(
    state: State<'_, AppState>,
) -> DesktopResult<Option<StackBinding>> {
    let selected = tauri::async_runtime::spawn_blocking(|| {
        rfd::FileDialog::new()
            .set_title("选择 AgentHub 项目目录")
            .pick_folder()
    })
    .await
    .map_err(|error| {
        crate::error::DesktopError::with_detail(
            "project_picker_failed",
            "无法打开项目目录选择器。",
            error.to_string(),
        )
    })?;
    let Some(selected) = selected else {
        return Ok(None);
    };
    let root = validate_project_root(&selected)?;
    let mut preferences = state.load_preferences()?;
    preferences.project_root = Some(root.to_string_lossy().into_owned());
    preferences.project_name = Some(crate::project::derive_project_name(&root));
    preferences.profile = Some(crate::models::StackProfile::Source);
    let binding = resolve_binding(&preferences).await?;
    persist_binding(&mut preferences, &binding);
    state.save_preferences(&preferences)?;
    Ok(Some(binding))
}

#[tauri::command]
pub async fn desktop_get_stack_binding(state: State<'_, AppState>) -> DesktopResult<StackBinding> {
    let mut preferences = state.load_preferences()?;
    let binding = resolve_binding(&preferences).await?;
    persist_binding(&mut preferences, &binding);
    state.save_preferences(&preferences)?;
    Ok(binding)
}

pub async fn docker_available() -> crate::models::DockerStatus {
    let version = crate::process::run_fixed(
        "docker",
        &["--version".to_string()],
        None,
        Duration::from_secs(5),
    )
    .await;
    if version.is_err() {
        return crate::models::DockerStatus::NotInstalled;
    }
    let info = crate::process::run_fixed(
        "docker",
        &[
            "info".to_string(),
            "--format".to_string(),
            "{{.ServerVersion}}".to_string(),
        ],
        None,
        Duration::from_secs(10),
    )
    .await;
    if info.is_err() {
        crate::models::DockerStatus::NotRunning
    } else {
        crate::models::DockerStatus::Ready
    }
}

pub async fn compose_available() -> bool {
    crate::process::run_fixed(
        "docker",
        &["compose".to_string(), "version".to_string()],
        None,
        Duration::from_secs(5),
    )
    .await
    .is_ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn profile(url: &str, mode: BackendProfileMode) -> BackendProfile {
        BackendProfile {
            id: "profile-1".to_string(),
            name: "AgentHub".to_string(),
            url: url.to_string(),
            mode,
            server_id: None,
            last_connected_at: None,
            last_health: None,
        }
    }

    #[test]
    fn public_profiles_require_https() {
        assert!(validate_backend_profile_url(&profile(
            "https://agenthub.example.com",
            BackendProfileMode::Remote,
        ))
        .is_ok());
        assert!(validate_backend_profile_url(&profile(
            "http://agenthub.example.com",
            BackendProfileMode::Remote,
        ))
        .is_err());
        assert!(validate_backend_profile_url(&profile(
            "https://agenthub.example.com/#token",
            BackendProfileMode::Remote,
        ))
        .is_err());
    }

    #[test]
    fn local_profiles_require_loopback_hosts() {
        assert!(validate_backend_profile_url(&profile(
            "http://localhost:8000",
            BackendProfileMode::Local,
        ))
        .is_ok());
        assert!(validate_backend_profile_url(&profile(
            "http://192.168.1.20:8000",
            BackendProfileMode::Local,
        ))
        .is_err());
    }
}
