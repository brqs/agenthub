use std::path::Path;

use chrono::Utc;
use serde_json::json;
use tauri::State;

use crate::error::DesktopResult;
use crate::logs::tail_service_logs;
use crate::models::{DiagnosticsExport, ServiceName};
use crate::sanitizer::sanitize_text;
use crate::stack::check_local_stack;
use crate::state::AppState;

#[tauri::command]
pub async fn desktop_export_diagnostics(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
) -> DesktopResult<DiagnosticsExport> {
    let mut status = check_local_stack(&state).await?;
    status.project_root = status.project_root.as_deref().and_then(project_leaf);
    let backend = tail_service_logs(ServiceName::Backend, Some(300), &state)
        .await
        .ok();
    let postgres = tail_service_logs(ServiceName::Postgres, Some(120), &state)
        .await
        .ok();
    let redis = tail_service_logs(ServiceName::Redis, Some(120), &state)
        .await
        .ok();
    let audit = read_sanitized_audit(&state.audit_path());

    let document = json!({
        "generatedAt": Utc::now().to_rfc3339(),
        "appVersion": app.package_info().version.to_string(),
        "platform": std::env::consts::OS,
        "stack": status,
        "logs": {
            "backend": backend,
            "postgres": postgres,
            "redis": redis,
        },
        "auditTail": audit,
        "privacy": {
            "includesEnvironmentFile": false,
            "includesRuntimeAuthentication": false,
            "includesConversationContent": false,
            "includesWorkspaceFiles": false,
            "sanitized": true,
        }
    });

    let directory = state.diagnostics_dir();
    std::fs::create_dir_all(&directory)?;
    let filename = format!(
        "agenthub-diagnostics-{}.json",
        Utc::now().format("%Y%m%d-%H%M%S")
    );
    let path = directory.join(filename);
    let serialized = serde_json::to_string_pretty(&document)?;
    std::fs::write(&path, sanitize_text(&serialized))?;
    let file_token = uuid::Uuid::new_v4().to_string();
    let suggested_name = path
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("agenthub-diagnostics.json")
        .to_string();
    state.register_diagnostic(file_token.clone(), path)?;
    Ok(DiagnosticsExport {
        file_token,
        suggested_name,
    })
}

#[tauri::command]
pub async fn desktop_save_diagnostics(
    file_token: String,
    app: tauri::AppHandle,
    state: State<'_, AppState>,
) -> DesktopResult<crate::models::DesktopSaveResult> {
    let started = std::time::Instant::now();
    let result = save_diagnostics(file_token, &state).await;
    let _ = state.append_audit(&crate::models::AuditEntry {
        timestamp: Utc::now().to_rfc3339(),
        action: "save_diagnostics".to_string(),
        result: if result.is_ok() { "success" } else { "error" }.to_string(),
        duration_ms: started.elapsed().as_millis(),
        app_version: app.package_info().version.to_string(),
    });
    result
}

async fn save_diagnostics(
    file_token: String,
    state: &AppState,
) -> DesktopResult<crate::models::DesktopSaveResult> {
    let source = state.diagnostic_path(&file_token)?;
    if !source.is_file() {
        return Err(crate::error::DesktopError::new(
            "diagnostic_file_missing",
            "诊断文件已不存在，请重新导出。",
        ));
    }
    let suggested_name = source
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("agenthub-diagnostics.json")
        .to_string();
    let destination = tauri::async_runtime::spawn_blocking(move || {
        rfd::FileDialog::new()
            .set_title("保存 AgentHub 诊断文件")
            .set_file_name(&suggested_name)
            .add_filter("JSON", &["json"])
            .save_file()
    })
    .await
    .map_err(|error| {
        crate::error::DesktopError::with_detail(
            "diagnostic_save_dialog_failed",
            "无法打开诊断文件保存窗口。",
            error.to_string(),
        )
    })?;
    let Some(destination) = destination else {
        return Ok(crate::models::DesktopSaveResult {
            saved: false,
            file_name: None,
        });
    };
    std::fs::copy(source, &destination)?;
    Ok(crate::models::DesktopSaveResult {
        saved: true,
        file_name: destination
            .file_name()
            .and_then(|name| name.to_str())
            .map(ToString::to_string),
    })
}

fn read_sanitized_audit(path: &Path) -> Vec<String> {
    let Ok(raw) = std::fs::read_to_string(path) else {
        return Vec::new();
    };
    raw.lines()
        .rev()
        .take(100)
        .map(sanitize_text)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect()
}

fn project_leaf(value: &str) -> Option<String> {
    Path::new(value)
        .file_name()
        .and_then(|name| name.to_str())
        .map(ToString::to_string)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn diagnostics_only_keep_project_directory_name() {
        assert_eq!(
            project_leaf(r"C:\Users\private\agenthub-github"),
            Some("agenthub-github".to_string())
        );
    }
}
