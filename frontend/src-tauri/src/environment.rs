use std::time::Duration;

use tauri::State;

use crate::error::DesktopResult;
use crate::models::{
    DesktopEnvironment, DesktopPreferences, DesktopPreferencesPatch, StackBinding,
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
    if let Some(backend_url) = patch.backend_url {
        let trimmed = backend_url.trim();
        if !(trimmed.starts_with("http://") || trimmed.starts_with("https://")) {
            return Err(crate::error::DesktopError::new(
                "backend_url_invalid",
                "后端地址必须以 http:// 或 https:// 开头。",
            ));
        }
        preferences.backend_url = trimmed.trim_end_matches('/').to_string();
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
