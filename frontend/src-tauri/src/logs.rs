use std::path::Path;
use std::time::Duration;

use tauri::State;

use crate::error::DesktopResult;
use crate::models::{ServiceLogTail, ServiceName};
use crate::process::run_fixed;
use crate::project::{compose_prefix, resolve_binding};
use crate::sanitizer::sanitize_text;
use crate::state::AppState;

#[tauri::command]
pub async fn desktop_tail_service_logs(
    service: ServiceName,
    lines: Option<u16>,
    state: State<'_, AppState>,
) -> DesktopResult<ServiceLogTail> {
    tail_service_logs(service, lines, &state).await
}

pub async fn tail_service_logs(
    service: ServiceName,
    lines: Option<u16>,
    state: &AppState,
) -> DesktopResult<ServiceLogTail> {
    let preferences = state.load_preferences()?;
    let binding = resolve_binding(&preferences).await?;
    let line_count = lines.unwrap_or(300).clamp(1, 300);
    let mut args = compose_prefix(&binding);
    args.extend([
        "logs".to_string(),
        "--no-color".to_string(),
        "--timestamps".to_string(),
        "--tail".to_string(),
        line_count.to_string(),
        service.as_str().to_string(),
    ]);
    let output = run_fixed(
        "docker",
        &args,
        Some(Path::new(&binding.project_root)),
        Duration::from_secs(30),
    )
    .await?;
    let combined = if output.stderr.trim().is_empty() {
        output.stdout
    } else if output.stdout.trim().is_empty() {
        output.stderr
    } else {
        format!("{}\n{}", output.stdout, output.stderr)
    };
    let sanitized = sanitize_text(&combined);
    let lines = sanitized
        .lines()
        .map(ToString::to_string)
        .collect::<Vec<_>>();
    Ok(ServiceLogTail {
        service: service.as_str().to_string(),
        truncated: lines.len() >= usize::from(line_count),
        lines,
        sanitized: true,
    })
}
