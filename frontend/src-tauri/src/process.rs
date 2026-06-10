use std::path::Path;
use std::process::Stdio;
use std::time::Duration;

#[cfg(windows)]
use std::os::windows::process::CommandExt;
use tokio::process::Command;

use crate::error::{DesktopError, DesktopResult};
use crate::sanitizer::sanitize_text;

const CREATE_NO_WINDOW: u32 = 0x0800_0000;

#[derive(Debug)]
pub struct CommandOutput {
    pub stdout: String,
    pub stderr: String,
}

pub async fn run_fixed(
    program: &str,
    args: &[String],
    cwd: Option<&Path>,
    timeout: Duration,
) -> DesktopResult<CommandOutput> {
    let mut command = Command::new(program);
    command
        .args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    if let Some(cwd) = cwd {
        command.current_dir(cwd);
    }
    #[cfg(windows)]
    command.as_std_mut().creation_flags(CREATE_NO_WINDOW);

    let output = tokio::time::timeout(timeout, command.output())
        .await
        .map_err(|_| DesktopError::new("desktop_command_timeout", "本地服务操作超时。"))?
        .map_err(|error| {
            DesktopError::with_detail(
                "desktop_command_unavailable",
                format!("无法运行受控程序 {program}。"),
                error.to_string(),
            )
        })?;

    let stdout = String::from_utf8_lossy(&output.stdout).into_owned();
    let stderr = String::from_utf8_lossy(&output.stderr).into_owned();
    if !output.status.success() {
        let detail = sanitize_text(if stderr.trim().is_empty() {
            &stdout
        } else {
            &stderr
        });
        return Err(DesktopError::with_detail(
            "desktop_command_failed",
            "本地服务命令执行失败。",
            trim_output(&detail, 12_000),
        ));
    }
    Ok(CommandOutput { stdout, stderr })
}

pub fn trim_output(value: &str, max_chars: usize) -> String {
    if value.chars().count() <= max_chars {
        return value.to_string();
    }
    let tail: String = value
        .chars()
        .rev()
        .take(max_chars)
        .collect::<String>()
        .chars()
        .rev()
        .collect();
    format!("[output truncated]\n{tail}")
}
