use std::path::Path;
use std::time::Instant;

use chrono::Utc;
use serde_json::Value;
use tauri::{Emitter, Manager, State};
use url::Url;
use uuid::Uuid;

use crate::error::{DesktopError, DesktopResult};
use crate::models::{
    AuditEntry, DesktopNotificationActivation, DesktopNotificationInput, DesktopNotificationKind,
    DesktopOpenResult,
};
use crate::project::resolve_binding;
use crate::state::AppState;

const MAX_EXTERNAL_URL_LENGTH: usize = 2_048;
const MAX_AGENT_LABEL_LENGTH: usize = 64;

#[tauri::command]
pub async fn desktop_open_workspace_folder(
    conversation_id: String,
    state: State<'_, AppState>,
    app: tauri::AppHandle,
) -> DesktopResult<DesktopOpenResult> {
    let started = Instant::now();
    let result = open_workspace_folder(&conversation_id, &state).await;
    audit(
        &app,
        &state,
        "open_workspace_folder",
        &result,
        started.elapsed().as_millis(),
    );
    result
}

async fn open_workspace_folder(
    conversation_id: &str,
    state: &AppState,
) -> DesktopResult<DesktopOpenResult> {
    let conversation_uuid = Uuid::parse_str(conversation_id).map_err(|_| {
        DesktopError::new(
            "conversation_id_invalid",
            "当前会话标识无效，无法打开 Workspace。",
        )
    })?;
    let preferences = state.load_preferences()?;
    if !is_local_backend_url(&preferences.backend_url) {
        return Err(DesktopError::new(
            "workspace_remote_backend",
            "当前连接的是远程后端，无法打开本机 Workspace 文件夹。",
        ));
    }
    let binding = resolve_binding(&preferences).await?;
    let workspace_base = Path::new(&binding.project_root).join("workspaces");
    let canonical_base = workspace_base.canonicalize().map_err(|error| {
        DesktopError::with_detail(
            "workspace_base_missing",
            "尚未找到本地 Workspace 目录。",
            error.to_string(),
        )
    })?;
    let target = canonical_base.join(conversation_uuid.to_string());
    reject_reparse_point(&target)?;
    let canonical_target = target.canonicalize().map_err(|error| {
        DesktopError::with_detail(
            "workspace_folder_missing",
            "当前会话的 Workspace 文件夹尚未创建。",
            error.to_string(),
        )
    })?;
    if !canonical_target.starts_with(&canonical_base) {
        return Err(DesktopError::new(
            "workspace_path_not_allowed",
            "Workspace 路径超出了允许的项目目录。",
        ));
    }
    validate_workspace_manifest(&canonical_target, conversation_uuid)?;
    open_shell_target(&canonical_target.to_string_lossy())?;
    Ok(DesktopOpenResult { opened: true })
}

#[tauri::command]
pub fn desktop_open_external_url(
    url: String,
    state: State<'_, AppState>,
    app: tauri::AppHandle,
) -> DesktopResult<DesktopOpenResult> {
    let started = Instant::now();
    let result = validate_external_url(&url).and_then(|validated| {
        open_shell_target(validated.as_str())?;
        Ok(DesktopOpenResult { opened: true })
    });
    audit(
        &app,
        &state,
        "open_external_url",
        &result,
        started.elapsed().as_millis(),
    );
    result
}

#[tauri::command]
pub fn desktop_show_notification(
    input: DesktopNotificationInput,
    state: State<'_, AppState>,
    app: tauri::AppHandle,
) -> DesktopResult<DesktopOpenResult> {
    let started = Instant::now();
    let result = show_notification(input, &state, app.clone());
    audit(
        &app,
        &state,
        "show_notification",
        &result,
        started.elapsed().as_millis(),
    );
    result
}

fn show_notification(
    input: DesktopNotificationInput,
    state: &AppState,
    app: tauri::AppHandle,
) -> DesktopResult<DesktopOpenResult> {
    if !state.load_preferences()?.notifications_enabled {
        return Err(DesktopError::new(
            "notification_disabled",
            "系统通知尚未在桌面设置中开启。",
        ));
    }
    Uuid::parse_str(&input.notification_id)
        .map_err(|_| DesktopError::new("notification_id_invalid", "桌面通知标识无效。"))?;
    Uuid::parse_str(&input.conversation_id)
        .map_err(|_| DesktopError::new("conversation_id_invalid", "桌面通知的会话标识无效。"))?;
    let agent_label = sanitize_agent_label(&input.agent_label);
    if agent_label.is_empty() {
        return Err(DesktopError::new(
            "notification_agent_invalid",
            "桌面通知缺少 Agent 名称。",
        ));
    }
    show_windows_notification(input, agent_label, state, app)?;
    Ok(DesktopOpenResult { opened: true })
}

pub fn validate_external_url(input: &str) -> DesktopResult<Url> {
    if input.len() > MAX_EXTERNAL_URL_LENGTH {
        return Err(DesktopError::new(
            "external_url_too_long",
            "外部链接过长，已拒绝打开。",
        ));
    }
    let parsed = Url::parse(input)
        .map_err(|_| DesktopError::new("external_url_invalid", "外部链接格式无效。"))?;
    if !matches!(parsed.scheme(), "http" | "https" | "mailto") {
        return Err(DesktopError::new(
            "external_url_not_allowed",
            "只允许打开 http、https 或 mailto 链接。",
        ));
    }
    if !parsed.username().is_empty() || parsed.password().is_some() {
        return Err(DesktopError::new(
            "external_url_credentials_not_allowed",
            "带有用户名或密码的外部链接已被拒绝。",
        ));
    }
    Ok(parsed)
}

fn is_local_backend_url(input: &str) -> bool {
    Url::parse(input)
        .ok()
        .and_then(|url| url.host_str().map(str::to_ascii_lowercase))
        .is_some_and(|host| matches!(host.as_str(), "localhost" | "127.0.0.1" | "::1"))
}

fn validate_workspace_manifest(root: &Path, conversation_id: Uuid) -> DesktopResult<()> {
    let manifest_path = root.join(".agenthub").join("manifest.json");
    let bytes = std::fs::read(&manifest_path).map_err(|error| {
        DesktopError::with_detail(
            "workspace_manifest_missing",
            "Workspace 缺少 AgentHub 身份文件，已拒绝打开。",
            error.to_string(),
        )
    })?;
    let manifest: Value = serde_json::from_slice(&bytes)?;
    if manifest.get("conversation_id").and_then(Value::as_str)
        != Some(conversation_id.to_string().as_str())
    {
        return Err(DesktopError::new(
            "workspace_manifest_mismatch",
            "Workspace 与当前会话不匹配，已拒绝打开。",
        ));
    }
    Ok(())
}

fn sanitize_agent_label(input: &str) -> String {
    input
        .chars()
        .filter(|character| !character.is_control())
        .take(MAX_AGENT_LABEL_LENGTH)
        .collect::<String>()
        .trim()
        .to_string()
}

fn reject_reparse_point(path: &Path) -> DesktopResult<()> {
    let metadata = std::fs::symlink_metadata(path).map_err(|error| {
        DesktopError::with_detail(
            "workspace_folder_missing",
            "当前会话的 Workspace 文件夹尚未创建。",
            error.to_string(),
        )
    })?;
    if metadata.file_type().is_symlink() {
        return Err(DesktopError::new(
            "workspace_path_not_allowed",
            "Workspace 不能是符号链接。",
        ));
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x0400;
        if metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0 {
            return Err(DesktopError::new(
                "workspace_path_not_allowed",
                "Workspace 不能是 Windows reparse point。",
            ));
        }
    }
    Ok(())
}

fn audit<T>(
    app: &tauri::AppHandle,
    state: &AppState,
    action: &str,
    result: &DesktopResult<T>,
    duration_ms: u128,
) {
    let _ = state.append_audit(&AuditEntry {
        timestamp: Utc::now().to_rfc3339(),
        action: action.to_string(),
        result: if result.is_ok() { "success" } else { "error" }.to_string(),
        duration_ms,
        app_version: app.package_info().version.to_string(),
    });
}

#[cfg(windows)]
pub(crate) fn open_shell_target(target: &str) -> DesktopResult<()> {
    use windows::core::{HSTRING, PCWSTR};
    use windows::Win32::Foundation::HWND;
    use windows::Win32::UI::Shell::ShellExecuteW;
    use windows::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;

    let operation = HSTRING::from("open");
    let target = HSTRING::from(target);
    let result = unsafe {
        ShellExecuteW(
            Some(HWND::default()),
            PCWSTR(operation.as_ptr()),
            PCWSTR(target.as_ptr()),
            None,
            None,
            SW_SHOWNORMAL,
        )
    };
    if result.0 as isize <= 32 {
        return Err(DesktopError::new(
            "desktop_open_failed",
            "Windows 无法打开所选目标。",
        ));
    }
    Ok(())
}

#[cfg(not(windows))]
pub(crate) fn open_shell_target(_target: &str) -> DesktopResult<()> {
    Err(DesktopError::new(
        "desktop_platform_not_supported",
        "此原生能力目前只支持 Windows。",
    ))
}

#[cfg(windows)]
fn show_windows_notification(
    input: DesktopNotificationInput,
    agent_label: String,
    state: &AppState,
    app: tauri::AppHandle,
) -> DesktopResult<()> {
    use windows::core::HSTRING;
    use windows::Data::Xml::Dom::XmlDocument;
    use windows::Foundation::TypedEventHandler;
    use windows::UI::Notifications::{ToastNotification, ToastNotificationManager};

    let (title, body) = match input.kind {
        DesktopNotificationKind::Done => (
            format!("{agent_label} 已完成"),
            "后台任务已经完成，点击返回对应会话。",
        ),
        DesktopNotificationKind::Error => (
            format!("{agent_label} 需要处理"),
            "后台任务未能完成，点击查看并重试。",
        ),
        DesktopNotificationKind::Attention => (
            format!("{agent_label} 等待确认"),
            "任务正在等待你的补充或确认。",
        ),
    };
    let launch = format!(
        "agenthub://notification/{}?conversationId={}",
        input.notification_id, input.conversation_id
    );
    let xml = format!(
        "<toast activationType=\"protocol\" launch=\"{}\"><visual><binding template=\"ToastGeneric\"><text>{}</text><text>{}</text></binding></visual></toast>",
        escape_xml(&launch),
        escape_xml(&title),
        escape_xml(body),
    );
    let document = XmlDocument::new().map_err(notification_error)?;
    document
        .LoadXml(&HSTRING::from(xml))
        .map_err(notification_error)?;
    let toast =
        ToastNotification::CreateToastNotification(&document).map_err(notification_error)?;
    let activation = DesktopNotificationActivation {
        notification_id: input.notification_id.clone(),
        conversation_id: input.conversation_id.clone(),
    };
    let app_handle = app.clone();
    toast
        .Activated(&TypedEventHandler::new(move |_, _| {
            if let Some(window) = app_handle.get_webview_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
            let _ = app_handle.emit("desktop://notification-activated", activation.clone());
            Ok(())
        }))
        .map_err(notification_error)?;
    let notifier =
        ToastNotificationManager::CreateToastNotifierWithId(&HSTRING::from("com.agenthub.desktop"))
            .map_err(notification_error)?;
    notifier.Show(&toast).map_err(notification_error)?;
    let mut notifications = state.notifications.lock().map_err(|_| {
        DesktopError::new("notification_state_unavailable", "桌面通知状态暂时不可用。")
    })?;
    notifications.insert(input.notification_id, toast);
    if notifications.len() > 32 {
        if let Some(oldest) = notifications.keys().next().cloned() {
            notifications.remove(&oldest);
        }
    }
    Ok(())
}

#[cfg(not(windows))]
fn show_windows_notification(
    _input: DesktopNotificationInput,
    _agent_label: String,
    _state: &AppState,
    _app: tauri::AppHandle,
) -> DesktopResult<()> {
    Err(DesktopError::new(
        "desktop_platform_not_supported",
        "系统通知目前只支持 Windows。",
    ))
}

#[cfg(windows)]
fn notification_error(error: windows::core::Error) -> DesktopError {
    DesktopError::with_detail(
        "notification_show_failed",
        "Windows 系统通知发送失败。",
        error.to_string(),
    )
}

fn escape_xml(input: &str) -> String {
    input
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn external_urls_use_a_small_allowlist() {
        assert!(validate_external_url("https://example.com/path").is_ok());
        assert!(validate_external_url("mailto:hello@example.com").is_ok());
        assert!(validate_external_url("file:///C:/Windows").is_err());
        assert!(validate_external_url("javascript:alert(1)").is_err());
        assert!(validate_external_url("https://user:secret@example.com").is_err());
    }

    #[test]
    fn manifest_must_match_the_conversation() {
        let temp = tempfile::tempdir().expect("tempdir");
        let metadata = temp.path().join(".agenthub");
        std::fs::create_dir_all(&metadata).expect("metadata");
        let conversation_id = Uuid::new_v4();
        std::fs::write(
            metadata.join("manifest.json"),
            serde_json::to_vec(&serde_json::json!({
                "conversation_id": conversation_id.to_string()
            }))
            .expect("json"),
        )
        .expect("manifest");
        assert!(validate_workspace_manifest(temp.path(), conversation_id).is_ok());
        assert!(validate_workspace_manifest(temp.path(), Uuid::new_v4()).is_err());
    }

    #[test]
    fn agent_labels_drop_control_characters_and_are_bounded() {
        let label = sanitize_agent_label(&format!("Claude\n{}", "x".repeat(100)));
        assert!(!label.contains('\n'));
        assert!(label.chars().count() <= MAX_AGENT_LABEL_LENGTH);
    }

    #[test]
    fn local_backend_detection_is_explicit() {
        assert!(is_local_backend_url("http://localhost:8000"));
        assert!(is_local_backend_url("http://127.0.0.1:8000"));
        assert!(!is_local_backend_url("https://agenthub.example.com"));
    }
}
