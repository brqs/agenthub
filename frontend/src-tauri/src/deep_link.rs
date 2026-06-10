use tauri::Emitter;
use url::Url;
use uuid::Uuid;

use crate::models::DesktopDeepLinkActivation;

const DEEP_LINK_EVENT: &str = "desktop://deep-link";
const MAX_DEEP_LINK_LENGTH: usize = 512;

pub fn emit_deep_links(app: &tauri::AppHandle, urls: impl IntoIterator<Item = String>) {
    for url in urls {
        if let Ok(activation) = parse_deep_link(&url) {
            let _ = app.emit(DEEP_LINK_EVENT, activation);
        }
    }
}

pub fn parse_deep_link(input: &str) -> Result<DesktopDeepLinkActivation, String> {
    if input.len() > MAX_DEEP_LINK_LENGTH {
        return Err("deep link too long".to_string());
    }
    let url = Url::parse(input).map_err(|error| error.to_string())?;
    if url.scheme() != "agenthub" {
        return Err("unsupported scheme".to_string());
    }
    if !url.username().is_empty() || url.password().is_some() {
        return Err("credentials are not allowed".to_string());
    }
    match url.host_str() {
        Some("chat") => {
            let conversation_id = trim_single_path_segment(url.path())?;
            Uuid::parse_str(conversation_id).map_err(|_| "invalid conversation id".to_string())?;
            Ok(DesktopDeepLinkActivation::Chat {
                conversation_id: conversation_id.to_string(),
            })
        }
        Some("notification") => {
            let notification_id = trim_single_path_segment(url.path())?;
            Uuid::parse_str(notification_id).map_err(|_| "invalid notification id".to_string())?;
            let conversation_id = url
                .query_pairs()
                .find_map(|(key, value)| {
                    if key == "conversationId" {
                        Some(value.into_owned())
                    } else {
                        None
                    }
                })
                .ok_or_else(|| "missing conversation id".to_string())?;
            Uuid::parse_str(&conversation_id).map_err(|_| "invalid conversation id".to_string())?;
            Ok(DesktopDeepLinkActivation::Notification {
                notification_id: notification_id.to_string(),
                conversation_id,
            })
        }
        _ => Err("unsupported deep link host".to_string()),
    }
}

fn trim_single_path_segment(path: &str) -> Result<&str, String> {
    let value = path.trim_matches('/');
    if value.is_empty() || value.contains('/') || value.contains('\\') {
        return Err("invalid path segment".to_string());
    }
    Ok(value)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_chat_and_notification_links() {
        let conversation_id = Uuid::new_v4();
        assert_eq!(
            parse_deep_link(&format!("agenthub://chat/{conversation_id}")).expect("chat"),
            DesktopDeepLinkActivation::Chat {
                conversation_id: conversation_id.to_string()
            }
        );

        let notification_id = Uuid::new_v4();
        assert_eq!(
            parse_deep_link(&format!(
                "agenthub://notification/{notification_id}?conversationId={conversation_id}"
            ))
            .expect("notification"),
            DesktopDeepLinkActivation::Notification {
                notification_id: notification_id.to_string(),
                conversation_id: conversation_id.to_string()
            }
        );
    }

    #[test]
    fn rejects_untrusted_deep_links() {
        assert!(parse_deep_link("https://example.com").is_err());
        assert!(
            parse_deep_link("agenthub://user:pass@chat/00000000-0000-0000-0000-000000000000")
                .is_err()
        );
        assert!(parse_deep_link("agenthub://chat/not-a-uuid").is_err());
        assert!(
            parse_deep_link("agenthub://chat/00000000-0000-0000-0000-000000000000/extra").is_err()
        );
    }
}
