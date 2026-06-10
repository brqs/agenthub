use tauri::State;

use crate::error::{DesktopError, DesktopResult};
use crate::models::{LocalRuntimeConnectorProbe, LocalRuntimeConnectorState};
use crate::state::AppState;

#[tauri::command]
pub async fn desktop_probe_local_runtime_connector(
    state: State<'_, AppState>,
) -> DesktopResult<LocalRuntimeConnectorProbe> {
    let preferences = state.load_preferences()?;
    if !is_loopback_http(&preferences.backend_url) {
        return Ok(LocalRuntimeConnectorProbe {
            available: false,
            reason: Some("本机 Runtime Connector 只允许连接本地后端时启用。".to_string()),
        });
    }
    Ok(LocalRuntimeConnectorProbe {
        available: true,
        reason: None,
    })
}

#[tauri::command]
pub async fn desktop_start_local_runtime_connector(
    state: State<'_, AppState>,
) -> DesktopResult<LocalRuntimeConnectorState> {
    let probe = desktop_probe_local_runtime_connector(state).await?;
    if !probe.available {
        return Err(DesktopError::new(
            "local_runtime_connector_unavailable",
            probe
                .reason
                .as_deref()
                .unwrap_or("本机 Runtime Connector 当前不可用。"),
        ));
    }
    Ok(LocalRuntimeConnectorState {
        running: true,
        endpoint_url: Some("http://127.0.0.1:0".to_string()),
        runtime_ids: Vec::new(),
    })
}

#[tauri::command]
pub async fn desktop_stop_local_runtime_connector() -> DesktopResult<LocalRuntimeConnectorState> {
    Ok(LocalRuntimeConnectorState {
        running: false,
        endpoint_url: None,
        runtime_ids: Vec::new(),
    })
}

fn is_loopback_http(input: &str) -> bool {
    let Ok(url) = url::Url::parse(input) else {
        return false;
    };
    if url.scheme() != "http" {
        return false;
    }
    url.host_str()
        .map(str::to_ascii_lowercase)
        .is_some_and(|host| matches!(host.as_str(), "localhost" | "127.0.0.1" | "::1"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn connector_requires_loopback_http_backend() {
        assert!(is_loopback_http("http://localhost:8000"));
        assert!(is_loopback_http("http://127.0.0.1:8000"));
        assert!(!is_loopback_http("https://agenthub.example.com"));
    }
}
