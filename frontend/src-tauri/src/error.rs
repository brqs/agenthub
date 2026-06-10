use serde::Serialize;

#[derive(Debug, Clone, Serialize, thiserror::Error)]
#[error("{message}")]
#[serde(rename_all = "camelCase")]
pub struct DesktopError {
    pub code: String,
    pub message: String,
    pub detail: Option<String>,
}

impl DesktopError {
    pub fn new(code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
            detail: None,
        }
    }

    pub fn with_detail(
        code: impl Into<String>,
        message: impl Into<String>,
        detail: impl Into<String>,
    ) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
            detail: Some(detail.into()),
        }
    }
}

impl From<std::io::Error> for DesktopError {
    fn from(value: std::io::Error) -> Self {
        Self::with_detail(
            "desktop_io_error",
            "桌面客户端访问本地资源失败。",
            value.to_string(),
        )
    }
}

impl From<serde_json::Error> for DesktopError {
    fn from(value: serde_json::Error) -> Self {
        Self::with_detail(
            "desktop_data_error",
            "桌面客户端解析本地状态失败。",
            value.to_string(),
        )
    }
}

pub type DesktopResult<T> = Result<T, DesktopError>;
