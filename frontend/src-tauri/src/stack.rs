use std::collections::HashMap;
use std::net::TcpListener;
use std::path::Path;
use std::time::{Duration, Instant};

use chrono::Utc;
use serde_json::Value;
use tauri::ipc::Channel;
use tauri::State;

use crate::environment::{compose_available, docker_available};
use crate::error::{DesktopError, DesktopResult};
use crate::models::{
    AuditEntry, BackendHealthStatus, DockerStatus, LocalStackStatus, ServiceState, ServiceStatus,
    StackBinding, StackOperation, StackProgress, StartStackOptions,
};
use crate::process::{run_fixed, trim_output};
use crate::project::{compose_prefix, persist_binding, resolve_binding};
use crate::sanitizer::sanitize_text;
use crate::state::AppState;

const SERVICES: &[(&str, u16)] = &[("postgres", 5432), ("redis", 6379), ("backend", 8000)];
const LOCAL_BACKEND_URL: &str = "http://localhost:8000";

#[tauri::command]
pub async fn desktop_check_local_stack(
    state: State<'_, AppState>,
) -> DesktopResult<LocalStackStatus> {
    check_local_stack(&state).await
}

#[tauri::command]
pub async fn desktop_start_local_stack(
    options: Option<StartStackOptions>,
    on_event: Channel<StackProgress>,
    app: tauri::AppHandle,
    state: State<'_, AppState>,
) -> DesktopResult<StackOperation> {
    run_operation("start_local_stack", &on_event, &app, &state, async {
        let options = options.unwrap_or_default();
        emit(&on_event, "checking", "正在检查 Docker 和项目目录...", None);
        let binding = prepare_binding(&state).await?;
        ensure_docker_ready().await?;
        ensure_project_files(&binding)?;

        let status = check_bound_stack(&binding, LOCAL_BACKEND_URL).await?;
        ensure_ports_available(&status)?;
        ensure_backend_image(&binding, options.rebuild).await?;

        emit(
            &on_event,
            "starting_services",
            if options.rebuild {
                "正在重新构建并启动本地服务..."
            } else {
                "正在启动本地服务..."
            },
            None,
        );
        let args = start_compose_args(&binding, options.rebuild);
        run_fixed(
            "docker",
            &args,
            Some(Path::new(&binding.project_root)),
            Duration::from_secs(if options.rebuild { 900 } else { 180 }),
        )
        .await
        .map_err(as_start_error)?;

        emit(&on_event, "migrating", "正在升级数据库结构...", None);
        run_compose_exec(
            &binding,
            &["exec", "-T", "backend", "alembic", "upgrade", "head"],
            Duration::from_secs(180),
        )
        .await?;

        emit(&on_event, "seeding", "正在同步内置 Agents...", None);
        run_compose_exec(
            &binding,
            &[
                "exec",
                "-T",
                "backend",
                "python",
                "-m",
                "app.seeds.seed_agents",
            ],
            Duration::from_secs(120),
        )
        .await?;

        emit(
            &on_event,
            "waiting_health",
            "服务已启动，正在等待 AgentHub 就绪...",
            None,
        );
        wait_for_backend(LOCAL_BACKEND_URL, Duration::from_secs(120)).await?;
        let status = check_bound_stack(&binding, LOCAL_BACKEND_URL).await?;
        emit(&on_event, "ready", "AgentHub 本地服务已就绪。", None);
        Ok(StackOperation {
            action: "start".to_string(),
            success: true,
            status,
        })
    })
    .await
}

#[tauri::command]
pub async fn desktop_stop_local_stack(
    on_event: Channel<StackProgress>,
    app: tauri::AppHandle,
    state: State<'_, AppState>,
) -> DesktopResult<StackOperation> {
    run_operation("stop_local_stack", &on_event, &app, &state, async {
        emit(&on_event, "checking", "正在检查本地服务...", None);
        let binding = prepare_binding(&state).await?;
        ensure_docker_ready().await?;
        emit(&on_event, "stopping", "正在停止本地服务...", None);
        let args = stop_compose_args(&binding);
        run_fixed(
            "docker",
            &args,
            Some(Path::new(&binding.project_root)),
            Duration::from_secs(120),
        )
        .await?;
        let mut status = check_bound_stack(&binding, LOCAL_BACKEND_URL).await?;
        status.backend_health = BackendHealthStatus::Unreachable;
        for service in &mut status.services {
            service.status = ServiceStatus::Stopped;
            service.detail = None;
        }
        emit(&on_event, "ready", "本地服务已停止，数据卷保持不变。", None);
        Ok(StackOperation {
            action: "stop".to_string(),
            success: true,
            status,
        })
    })
    .await
}

#[tauri::command]
pub async fn desktop_restart_backend(
    on_event: Channel<StackProgress>,
    app: tauri::AppHandle,
    state: State<'_, AppState>,
) -> DesktopResult<StackOperation> {
    run_operation("restart_backend", &on_event, &app, &state, async {
        emit(&on_event, "checking", "正在检查 Backend...", None);
        let binding = prepare_binding(&state).await?;
        ensure_docker_ready().await?;
        emit(&on_event, "restarting", "正在重启 Backend...", None);
        let args = restart_backend_args(&binding);
        run_fixed(
            "docker",
            &args,
            Some(Path::new(&binding.project_root)),
            Duration::from_secs(120),
        )
        .await?;
        emit(
            &on_event,
            "waiting_health",
            "正在等待 Backend 恢复...",
            None,
        );
        wait_for_backend(LOCAL_BACKEND_URL, Duration::from_secs(120)).await?;
        let status = check_bound_stack(&binding, LOCAL_BACKEND_URL).await?;
        emit(&on_event, "ready", "Backend 已恢复。", None);
        Ok(StackOperation {
            action: "restart_backend".to_string(),
            success: true,
            status,
        })
    })
    .await
}

async fn run_operation<F>(
    action: &str,
    on_event: &Channel<StackProgress>,
    app: &tauri::AppHandle,
    state: &AppState,
    operation: F,
) -> DesktopResult<StackOperation>
where
    F: std::future::Future<Output = DesktopResult<StackOperation>>,
{
    let started = Instant::now();
    let _guard = state.operation.try_lock().map_err(|_| {
        DesktopError::new(
            "desktop_operation_busy",
            "另一个本地服务操作正在进行，请等待完成。",
        )
    })?;
    let result = operation.await;
    let audit = AuditEntry {
        timestamp: Utc::now().to_rfc3339(),
        action: action.to_string(),
        result: if result.is_ok() { "success" } else { "error" }.to_string(),
        duration_ms: started.elapsed().as_millis(),
        app_version: app.package_info().version.to_string(),
    };
    let _ = state.append_audit(&audit);
    if let Err(error) = &result {
        emit(on_event, "error", &error.message, error.detail.as_deref());
    }
    result
}

async fn prepare_binding(state: &AppState) -> DesktopResult<StackBinding> {
    let mut preferences = state.load_preferences()?;
    let binding = resolve_binding(&preferences).await?;
    persist_binding(&mut preferences, &binding);
    state.save_preferences(&preferences)?;
    Ok(binding)
}

async fn ensure_docker_ready() -> DesktopResult<()> {
    match docker_available().await {
        DockerStatus::Ready => {}
        DockerStatus::NotInstalled => {
            return Err(DesktopError::new(
                "docker_not_installed",
                "未找到 Docker Desktop，请先安装 Docker Desktop。",
            ));
        }
        DockerStatus::NotRunning => {
            return Err(DesktopError::new(
                "docker_not_running",
                "需要先启动 Docker Desktop，AgentHub 的本地后端运行在 Docker 中。",
            ));
        }
    }
    if !compose_available().await {
        return Err(DesktopError::new(
            "compose_not_available",
            "Docker Compose 不可用，请更新 Docker Desktop。",
        ));
    }
    Ok(())
}

fn ensure_project_files(binding: &StackBinding) -> DesktopResult<()> {
    let root = Path::new(&binding.project_root);
    let env_path = root.join(".env");
    if !env_path.exists() {
        std::fs::copy(root.join(".env.example"), &env_path).map_err(|error| {
            DesktopError::with_detail(
                "project_env_create_failed",
                "无法从 .env.example 创建本地 .env。",
                error.to_string(),
            )
        })?;
    }
    std::fs::create_dir_all(root.join("workspaces"))?;
    Ok(())
}

async fn ensure_backend_image(binding: &StackBinding, rebuild: bool) -> DesktopResult<()> {
    if rebuild {
        return Ok(());
    }
    let mut args = compose_prefix(binding);
    args.extend([
        "images".to_string(),
        "-q".to_string(),
        "backend".to_string(),
    ]);
    let output = run_fixed(
        "docker",
        &args,
        Some(Path::new(&binding.project_root)),
        Duration::from_secs(30),
    )
    .await?;
    if output.stdout.trim().is_empty() {
        return Err(DesktopError::new(
            "backend_image_missing",
            "本机没有可用的 AgentHub Backend 镜像，请确认后选择“重新构建并启动”。",
        ));
    }
    Ok(())
}

async fn run_compose_exec(
    binding: &StackBinding,
    suffix: &[&str],
    timeout: Duration,
) -> DesktopResult<()> {
    let mut args = compose_prefix(binding);
    args.extend(suffix.iter().map(|value| (*value).to_string()));
    run_fixed(
        "docker",
        &args,
        Some(Path::new(&binding.project_root)),
        timeout,
    )
    .await
    .map(|_| ())
}

pub async fn check_local_stack(state: &AppState) -> DesktopResult<LocalStackStatus> {
    let docker = docker_available().await;
    let compose = compose_available().await;
    let preferences = state.load_preferences()?;
    let binding = resolve_binding(&preferences).await;
    match binding {
        Ok(binding) if matches!(docker, DockerStatus::Ready) && compose => {
            check_bound_stack(&binding, LOCAL_BACKEND_URL).await
        }
        Ok(binding) => Ok(LocalStackStatus {
            project_root: Some(binding.project_root),
            project_name: Some(binding.project_name),
            profile: Some(binding.profile),
            docker,
            compose_available: compose,
            backend_health: BackendHealthStatus::Unreachable,
            services: default_services(),
            error: None,
        }),
        Err(error) => Ok(LocalStackStatus {
            project_root: None,
            project_name: None,
            profile: None,
            docker,
            compose_available: compose,
            backend_health: BackendHealthStatus::Unreachable,
            services: default_services(),
            error: Some(error.message),
        }),
    }
}

async fn check_bound_stack(
    binding: &StackBinding,
    backend_url: &str,
) -> DesktopResult<LocalStackStatus> {
    let mut args = compose_prefix(binding);
    args.extend([
        "ps".to_string(),
        "--all".to_string(),
        "--format".to_string(),
        "json".to_string(),
    ]);
    let output = run_fixed(
        "docker",
        &args,
        Some(Path::new(&binding.project_root)),
        Duration::from_secs(20),
    )
    .await?;
    let services = parse_compose_ps(&output.stdout)?;
    Ok(LocalStackStatus {
        project_root: Some(binding.project_root.clone()),
        project_name: Some(binding.project_name.clone()),
        profile: Some(binding.profile),
        docker: DockerStatus::Ready,
        compose_available: true,
        backend_health: check_backend_health(backend_url).await,
        services,
        error: None,
    })
}

fn parse_compose_ps(raw: &str) -> DesktopResult<Vec<ServiceState>> {
    let trimmed = raw.trim();
    let rows: Vec<Value> = if trimmed.is_empty() {
        Vec::new()
    } else if trimmed.starts_with('[') {
        serde_json::from_str(trimmed)?
    } else {
        trimmed
            .lines()
            .filter(|line| !line.trim().is_empty())
            .map(serde_json::from_str)
            .collect::<Result<Vec<_>, _>>()?
    };
    let mut by_service: HashMap<String, ServiceState> = HashMap::new();
    for row in rows {
        let Some(service) = row
            .get("Service")
            .or_else(|| row.get("service"))
            .and_then(Value::as_str)
        else {
            continue;
        };
        if !SERVICES.iter().any(|(name, _)| name == &service) {
            continue;
        }
        let state = row
            .get("State")
            .or_else(|| row.get("state"))
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_ascii_lowercase();
        let health = row
            .get("Health")
            .or_else(|| row.get("health"))
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_ascii_lowercase();
        let status_text = row
            .get("Status")
            .or_else(|| row.get("status"))
            .and_then(Value::as_str)
            .unwrap_or_default();
        let status = match (state.as_str(), health.as_str()) {
            ("running", "healthy") => ServiceStatus::Healthy,
            ("running", "starting") => ServiceStatus::Starting,
            ("running", _) => ServiceStatus::Running,
            ("created" | "restarting", _) => ServiceStatus::Starting,
            ("exited", _) if status_text.contains("(0)") => ServiceStatus::Stopped,
            ("exited" | "dead", _) => ServiceStatus::Error,
            ("", _) => ServiceStatus::Stopped,
            _ => ServiceStatus::Unknown,
        };
        by_service.insert(
            service.to_string(),
            ServiceState {
                name: service.to_string(),
                status,
                detail: if status_text.is_empty() {
                    None
                } else {
                    Some(sanitize_text(status_text))
                },
            },
        );
    }
    Ok(SERVICES
        .iter()
        .map(|(name, _)| {
            by_service.remove(*name).unwrap_or(ServiceState {
                name: (*name).to_string(),
                status: ServiceStatus::Stopped,
                detail: None,
            })
        })
        .collect())
}

fn default_services() -> Vec<ServiceState> {
    SERVICES
        .iter()
        .map(|(name, _)| ServiceState {
            name: (*name).to_string(),
            status: ServiceStatus::Unknown,
            detail: None,
        })
        .collect()
}

async fn check_backend_health(backend_url: &str) -> BackendHealthStatus {
    let url = format!("{}/health", backend_url.trim_end_matches('/'));
    let client = match reqwest::Client::builder()
        .timeout(Duration::from_secs(5))
        .build()
    {
        Ok(client) => client,
        Err(_) => return BackendHealthStatus::Unreachable,
    };
    match client.get(url).send().await {
        Ok(response) if response.status().is_success() => {
            let body: Value = response.json().await.unwrap_or(Value::Null);
            if body.get("status").and_then(Value::as_str) == Some("ok") {
                BackendHealthStatus::Ready
            } else {
                BackendHealthStatus::Starting
            }
        }
        Ok(_) | Err(_) => BackendHealthStatus::Unreachable,
    }
}

async fn wait_for_backend(backend_url: &str, timeout: Duration) -> DesktopResult<()> {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if matches!(
            check_backend_health(backend_url).await,
            BackendHealthStatus::Ready
        ) {
            return Ok(());
        }
        tokio::time::sleep(Duration::from_secs(2)).await;
    }
    Err(DesktopError::new(
        "backend_health_timeout",
        "Backend 启动超时，请查看后端日志。",
    ))
}

fn ensure_ports_available(status: &LocalStackStatus) -> DesktopResult<()> {
    for (service, port) in SERVICES {
        let is_running = status.services.iter().any(|item| {
            item.name == *service
                && matches!(
                    item.status,
                    ServiceStatus::Healthy | ServiceStatus::Running | ServiceStatus::Starting
                )
        });
        if !is_running && TcpListener::bind(("127.0.0.1", *port)).is_err() {
            return Err(DesktopError::with_detail(
                "port_conflict",
                format!("本地端口 {port} 已被其它程序占用。"),
                format!("{service} 需要使用端口 {port}"),
            ));
        }
    }
    Ok(())
}

fn as_start_error(error: DesktopError) -> DesktopError {
    let detail = error.detail.unwrap_or_default();
    DesktopError::with_detail(
        "service_start_failed",
        "AgentHub 本地服务启动失败。",
        trim_output(&sanitize_text(&detail), 12_000),
    )
}

fn start_compose_args(binding: &StackBinding, rebuild: bool) -> Vec<String> {
    let mut args = compose_prefix(binding);
    args.extend([
        "up".to_string(),
        "-d".to_string(),
        if rebuild {
            "--build".to_string()
        } else {
            "--no-build".to_string()
        },
        "--wait".to_string(),
        "--wait-timeout".to_string(),
        "120".to_string(),
        "postgres".to_string(),
        "redis".to_string(),
        "backend".to_string(),
    ]);
    args
}

fn stop_compose_args(binding: &StackBinding) -> Vec<String> {
    let mut args = compose_prefix(binding);
    args.extend([
        "stop".to_string(),
        "backend".to_string(),
        "redis".to_string(),
        "postgres".to_string(),
    ]);
    args
}

fn restart_backend_args(binding: &StackBinding) -> Vec<String> {
    let mut args = compose_prefix(binding);
    args.extend(["restart".to_string(), "backend".to_string()]);
    args
}

fn emit(channel: &Channel<StackProgress>, stage: &str, message: &str, detail: Option<&str>) {
    let _ = channel.send(StackProgress {
        stage: stage.to_string(),
        message: message.to_string(),
        detail: detail.map(sanitize_text),
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_binding() -> StackBinding {
        StackBinding {
            project_root: "C:\\agenthub".to_string(),
            project_name: "agenthub-github".to_string(),
            profile: crate::models::StackProfile::Source,
            source: "test".to_string(),
        }
    }

    #[test]
    fn parses_compose_json_and_preserves_service_order() {
        let raw = r#"[{"Service":"backend","State":"running","Health":"","Status":"Up 3 seconds"},{"Service":"postgres","State":"running","Health":"healthy","Status":"Up 5 seconds (healthy)"}]"#;
        let services = parse_compose_ps(raw).expect("parse");
        assert_eq!(services[0].name, "postgres");
        assert_eq!(services[0].status, ServiceStatus::Healthy);
        assert_eq!(services[1].name, "redis");
        assert_eq!(services[1].status, ServiceStatus::Stopped);
        assert_eq!(services[2].status, ServiceStatus::Running);
    }

    #[test]
    fn parses_compose_json_lines() {
        let raw = "{\"Service\":\"redis\",\"State\":\"exited\",\"Health\":\"\",\"Status\":\"Exited (1)\"}\n";
        let services = parse_compose_ps(raw).expect("parse");
        assert_eq!(services[1].status, ServiceStatus::Error);
    }

    #[test]
    fn exited_zero_is_a_clean_stopped_state() {
        let raw = "{\"Service\":\"backend\",\"State\":\"exited\",\"Health\":\"\",\"Status\":\"Exited (0) 2 seconds ago\"}\n";
        let services = parse_compose_ps(raw).expect("parse");
        assert_eq!(services[2].status, ServiceStatus::Stopped);
    }

    #[test]
    fn lifecycle_arguments_are_fixed_and_non_destructive() {
        let binding = test_binding();
        let start = start_compose_args(&binding, false);
        let rebuild = start_compose_args(&binding, true);
        let stop = stop_compose_args(&binding);
        let restart = restart_backend_args(&binding);

        assert!(start.windows(2).any(|args| args == ["up", "-d"]));
        assert!(start.contains(&"--no-build".to_string()));
        assert!(rebuild.contains(&"--build".to_string()));
        assert!(stop.ends_with(&[
            "stop".to_string(),
            "backend".to_string(),
            "redis".to_string(),
            "postgres".to_string()
        ]));
        assert!(restart.ends_with(&["restart".to_string(), "backend".to_string()]));
        for args in [&start, &rebuild, &stop, &restart] {
            assert!(!args.iter().any(|arg| {
                matches!(arg.as_str(), "down" | "-v" | "--volumes" | "prune" | "rm")
            }));
        }
    }
}
