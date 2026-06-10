use std::path::{Path, PathBuf};
use std::time::Duration;

use serde_json::Value;

use crate::error::{DesktopError, DesktopResult};
use crate::models::{DesktopPreferences, StackBinding, StackProfile};
use crate::process::run_fixed;

const REQUIRED_MARKERS: &[&str] = &[
    "docker-compose.yml",
    ".env.example",
    "backend/alembic.ini",
    "shared/openapi.yaml",
];

pub fn validate_project_root(path: &Path) -> DesktopResult<PathBuf> {
    let raw = path.to_string_lossy();
    if raw.starts_with(r"\\") {
        return Err(DesktopError::new(
            "project_root_not_allowed",
            "P2 不支持网络共享目录，请选择本机 AgentHub 项目目录。",
        ));
    }
    let canonical = path.canonicalize().map_err(|error| {
        DesktopError::with_detail(
            "project_root_not_found",
            "未找到所选 AgentHub 项目目录。",
            error.to_string(),
        )
    })?;
    if !canonical.is_dir() {
        return Err(DesktopError::new(
            "project_root_not_found",
            "所选路径不是目录。",
        ));
    }
    let missing: Vec<&str> = REQUIRED_MARKERS
        .iter()
        .copied()
        .filter(|marker| !canonical.join(marker).is_file())
        .collect();
    if !missing.is_empty() {
        return Err(DesktopError::with_detail(
            "project_root_invalid",
            "这不是可识别的 AgentHub 项目目录。",
            format!("缺少：{}", missing.join(", ")),
        ));
    }
    Ok(canonical)
}

pub fn derive_project_name(root: &Path) -> String {
    let raw = root
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("agenthub");
    let mut normalized = String::new();
    for character in raw.to_ascii_lowercase().chars() {
        if character.is_ascii_alphanumeric() || matches!(character, '-' | '_') {
            normalized.push(character);
        } else if !normalized.ends_with('-') {
            normalized.push('-');
        }
    }
    let normalized = normalized.trim_matches(['-', '_']).to_string();
    if normalized.is_empty() {
        "agenthub".to_string()
    } else {
        normalized
    }
}

pub fn discover_project_root(preferences: &DesktopPreferences) -> DesktopResult<Option<PathBuf>> {
    if let Some(path) = preferences.project_root.as_deref() {
        if let Ok(root) = validate_project_root(Path::new(path)) {
            return Ok(Some(root));
        }
    }
    if let Ok(path) = std::env::var("AGENTHUB_DESKTOP_PROJECT_ROOT") {
        if let Ok(root) = validate_project_root(Path::new(&path)) {
            return Ok(Some(root));
        }
    }
    let mut candidates = Vec::new();
    if let Ok(cwd) = std::env::current_dir() {
        candidates.extend(cwd.ancestors().map(Path::to_path_buf));
    }
    if let Ok(executable) = std::env::current_exe() {
        if let Some(parent) = executable.parent() {
            candidates.extend(parent.ancestors().map(Path::to_path_buf));
        }
    }
    Ok(candidates
        .into_iter()
        .find_map(|candidate| validate_project_root(&candidate).ok()))
}

pub async fn existing_container_binding() -> Option<StackBinding> {
    let args = vec![
        "inspect".to_string(),
        "agenthub-backend".to_string(),
        "--format".to_string(),
        "{{json .Config.Labels}}".to_string(),
    ];
    let output = run_fixed("docker", &args, None, Duration::from_secs(10))
        .await
        .ok()?;
    let labels: Value = serde_json::from_str(output.stdout.trim()).ok()?;
    let root = labels
        .get("com.docker.compose.project.working_dir")
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())?;
    let project_name = labels
        .get("com.docker.compose.project")
        .and_then(Value::as_str)
        .unwrap_or("agenthub")
        .to_string();
    let config_files = labels
        .get("com.docker.compose.project.config_files")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let profile = if config_files.contains("docker-compose.windows-image.yml") {
        StackProfile::WindowsImage
    } else {
        StackProfile::Source
    };
    Some(StackBinding {
        project_root: root.to_string(),
        project_name,
        profile,
        source: "existing_container".to_string(),
    })
}

pub async fn resolve_binding(preferences: &DesktopPreferences) -> DesktopResult<StackBinding> {
    let existing = existing_container_binding().await;
    let discovered = discover_project_root(preferences)?;

    if let Some(existing) = existing {
        if let Some(candidate) = discovered {
            let existing_root = Path::new(&existing.project_root);
            let roots_match = existing_root
                .canonicalize()
                .map(|root| root == candidate)
                .unwrap_or(false);
            if !roots_match {
                return Err(DesktopError::with_detail(
                    "project_binding_conflict",
                    "检测到现有 AgentHub 数据栈属于另一个项目目录。",
                    format!(
                        "现有目录：{}\n当前目录：{}",
                        existing_root.display(),
                        candidate.display()
                    ),
                ));
            }
        }
        validate_project_root(Path::new(&existing.project_root)).map_err(|error| {
            DesktopError::with_detail(
                "existing_stack_project_missing",
                "检测到现有 AgentHub 数据栈，但它原来的项目目录已不可用。",
                format!(
                    "原目录：{}\n请恢复该目录，避免创建新的 Compose 数据卷。\n{}",
                    existing.project_root, error.message
                ),
            )
        })?;
        return Ok(existing);
    }

    let root = discovered.ok_or_else(|| {
        DesktopError::new(
            "project_root_not_found",
            "尚未绑定 AgentHub 项目目录，请先选择项目目录。",
        )
    })?;
    Ok(StackBinding {
        project_root: root.to_string_lossy().into_owned(),
        project_name: preferences
            .project_name
            .clone()
            .unwrap_or_else(|| derive_project_name(&root)),
        profile: preferences.profile.unwrap_or(StackProfile::Source),
        source: if preferences.project_root.is_some() {
            "preferences".to_string()
        } else {
            "discovery".to_string()
        },
    })
}

pub fn compose_prefix(binding: &StackBinding) -> Vec<String> {
    let mut args = vec![
        "compose".to_string(),
        "-p".to_string(),
        binding.project_name.clone(),
        "-f".to_string(),
        "docker-compose.yml".to_string(),
    ];
    match binding.profile {
        StackProfile::Source => {
            if Path::new(&binding.project_root)
                .join("docker-compose.override.yml")
                .is_file()
            {
                args.extend(["-f".to_string(), "docker-compose.override.yml".to_string()]);
            }
        }
        StackProfile::WindowsImage => {
            args.extend([
                "-f".to_string(),
                "docker-compose.windows-image.yml".to_string(),
            ]);
        }
    }
    args
}

pub fn persist_binding(preferences: &mut DesktopPreferences, binding: &StackBinding) {
    preferences.project_root = Some(binding.project_root.clone());
    preferences.project_name = Some(binding.project_name.clone());
    preferences.profile = Some(binding.profile);
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_project() -> tempfile::TempDir {
        let temp = tempfile::tempdir().expect("tempdir");
        for marker in REQUIRED_MARKERS {
            let path = temp.path().join(marker);
            std::fs::create_dir_all(path.parent().expect("parent")).expect("mkdir");
            std::fs::write(path, b"test").expect("write marker");
        }
        temp
    }

    #[test]
    fn validates_required_project_markers() {
        let temp = make_project();
        assert_eq!(
            validate_project_root(temp.path()).expect("valid root"),
            temp.path().canonicalize().expect("canonical")
        );
        std::fs::remove_file(temp.path().join("shared/openapi.yaml")).expect("remove marker");
        let error = validate_project_root(temp.path()).expect_err("invalid root");
        assert_eq!(error.code, "project_root_invalid");
    }

    #[test]
    fn compose_arguments_are_fixed_by_profile() {
        let binding = StackBinding {
            project_root: make_project().path().to_string_lossy().into_owned(),
            project_name: "agenthub-github".to_string(),
            profile: StackProfile::WindowsImage,
            source: "test".to_string(),
        };
        let args = compose_prefix(&binding);
        assert_eq!(&args[0..3], ["compose", "-p", "agenthub-github"]);
        assert!(args.contains(&"docker-compose.windows-image.yml".to_string()));
        assert!(!args.iter().any(|arg| arg == "down" || arg == "prune"));
    }
}
