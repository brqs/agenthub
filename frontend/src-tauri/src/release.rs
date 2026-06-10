use std::io::Write;
use std::panic::PanicHookInfo;
use std::path::{Path, PathBuf};
use std::time::Instant;

use chrono::Utc;
use tauri::State;
use tauri_plugin_updater::UpdaterExt;

use crate::error::{DesktopError, DesktopResult};
use crate::models::{
    AuditEntry, DesktopCrashReport, DesktopOpenResult, DesktopReleaseInfo,
    DesktopUpdateCheckResult, DesktopUpdateInstallResult,
};
use crate::native::{open_shell_target, validate_external_url};
use crate::sanitizer::sanitize_text;
use crate::state::AppState;

const RELEASE_PAGE_URL: &str = "https://github.com/brqs/agenthub/releases/latest";
const UPDATE_ENDPOINT: &str =
    "https://github.com/brqs/agenthub/releases/latest/download/latest.json";
const CRASH_LOG_MAX_LINES: usize = 120;

#[tauri::command]
pub fn desktop_get_release_info(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
) -> DesktopResult<DesktopReleaseInfo> {
    let preferences = state.load_preferences()?;
    Ok(DesktopReleaseInfo {
        app_version: app.package_info().version.to_string(),
        update_channel: preferences.update_channel,
        update_endpoint: UPDATE_ENDPOINT.to_string(),
        release_page_url: RELEASE_PAGE_URL.to_string(),
        installer_kind: "nsis_or_msi".to_string(),
        auto_check_updates: preferences.auto_check_updates,
        last_update_check_at: preferences.last_update_check_at,
    })
}

#[tauri::command]
pub async fn desktop_check_for_update(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
) -> DesktopResult<DesktopUpdateCheckResult> {
    let started = Instant::now();
    let result = check_for_update(app.clone(), &state).await;
    audit(&app, &state, "check_for_update", &result, started);
    result
}

async fn check_for_update(
    app: tauri::AppHandle,
    state: &AppState,
) -> DesktopResult<DesktopUpdateCheckResult> {
    let checked_at = Utc::now().to_rfc3339();
    let mut preferences = state.load_preferences()?;
    preferences.last_update_check_at = Some(checked_at.clone());
    state.save_preferences(&preferences)?;

    let update = app
        .updater()
        .map_err(updater_error)?
        .check()
        .await
        .map_err(updater_error)?;
    let current_version = app.package_info().version.to_string();
    Ok(match update {
        Some(update) => DesktopUpdateCheckResult {
            checked_at,
            available: true,
            current_version,
            version: Some(update.version),
            date: update.date.map(|date| date.to_string()),
            body: update.body,
            release_page_url: RELEASE_PAGE_URL.to_string(),
        },
        None => DesktopUpdateCheckResult {
            checked_at,
            available: false,
            current_version,
            version: None,
            date: None,
            body: None,
            release_page_url: RELEASE_PAGE_URL.to_string(),
        },
    })
}

#[tauri::command]
pub async fn desktop_install_update(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
) -> DesktopResult<DesktopUpdateInstallResult> {
    let started = Instant::now();
    let result = install_update(app.clone()).await;
    if let Err(error) = &result {
        let _ = append_crash_line(
            &state.crash_log_path(),
            &format!("update_install_failed: {error:?}"),
        );
    }
    audit(&app, &state, "install_update", &result, started);
    result
}

async fn install_update(app: tauri::AppHandle) -> DesktopResult<DesktopUpdateInstallResult> {
    let update = app
        .updater()
        .map_err(updater_error)?
        .check()
        .await
        .map_err(updater_error)?
        .ok_or_else(|| {
            DesktopError::new(
                "desktop_update_not_available",
                "当前已经是最新版本，没有可安装的更新。",
            )
        })?;
    let version = update.version.clone();
    update
        .download_and_install(|_, _| {}, || {})
        .await
        .map_err(updater_error)?;
    Ok(DesktopUpdateInstallResult {
        installed: true,
        restart_required: true,
        version: Some(version),
    })
}

#[tauri::command]
pub fn desktop_open_release_page(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
) -> DesktopResult<DesktopOpenResult> {
    let started = Instant::now();
    let result = validate_external_url(RELEASE_PAGE_URL).and_then(|url| {
        open_shell_target(url.as_str())?;
        Ok(DesktopOpenResult { opened: true })
    });
    audit(&app, &state, "open_release_page", &result, started);
    result
}

#[tauri::command]
pub fn desktop_collect_crash_report(
    state: State<'_, AppState>,
) -> DesktopResult<DesktopCrashReport> {
    collect_crash_report(&state.crash_log_path())
}

fn collect_crash_report(path: &Path) -> DesktopResult<DesktopCrashReport> {
    if !path.exists() {
        return Ok(DesktopCrashReport {
            exists: false,
            lines: Vec::new(),
            truncated: false,
        });
    }
    let raw = std::fs::read_to_string(path)?;
    let all = raw.lines().map(sanitize_text).collect::<Vec<_>>();
    let truncated = all.len() > CRASH_LOG_MAX_LINES;
    let lines = all
        .into_iter()
        .rev()
        .take(CRASH_LOG_MAX_LINES)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect();
    Ok(DesktopCrashReport {
        exists: true,
        lines,
        truncated,
    })
}

pub fn install_panic_hook(path: PathBuf) {
    let previous = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        let _ = append_crash_line(&path, &format!("rust_panic: {}", format_panic(info)));
        previous(info);
    }));
}

fn format_panic(info: &PanicHookInfo<'_>) -> String {
    let location = info
        .location()
        .map(|location| format!("{}:{}", location.file(), location.line()))
        .unwrap_or_else(|| "unknown".to_string());
    let payload = info
        .payload()
        .downcast_ref::<&str>()
        .copied()
        .or_else(|| info.payload().downcast_ref::<String>().map(String::as_str))
        .unwrap_or("panic");
    format!("{location} {payload}")
}

fn append_crash_line(path: &Path, line: &str) -> DesktopResult<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)?;
    writeln!(file, "{} {}", Utc::now().to_rfc3339(), sanitize_text(line))?;
    Ok(())
}

fn updater_error(error: tauri_plugin_updater::Error) -> DesktopError {
    DesktopError::with_detail(
        "desktop_update_failed",
        "桌面客户端更新检查或安装失败。你可以稍后重试，或打开 GitHub Releases 手动下载安装包。",
        sanitize_text(&error.to_string()),
    )
}

fn audit<T>(
    app: &tauri::AppHandle,
    state: &AppState,
    action: &str,
    result: &DesktopResult<T>,
    started: Instant,
) {
    let _ = state.append_audit(&AuditEntry {
        timestamp: Utc::now().to_rfc3339(),
        action: action.to_string(),
        result: if result.is_ok() { "success" } else { "error" }.to_string(),
        duration_ms: started.elapsed().as_millis(),
        app_version: app.package_info().version.to_string(),
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn crash_report_tail_is_sanitized_and_bounded() {
        let temp = tempfile::tempdir().expect("tempdir");
        let path = temp.path().join("desktop-crashes.log");
        for index in 0..130 {
            append_crash_line(&path, &format!("line-{index} OPENAI_API_KEY=sk-secret"))
                .expect("append");
        }
        let report = collect_crash_report(&path).expect("report");
        assert!(report.exists);
        assert!(report.truncated);
        assert_eq!(report.lines.len(), CRASH_LOG_MAX_LINES);
        assert!(!report.lines.join("\n").contains("sk-secret"));
    }
}
