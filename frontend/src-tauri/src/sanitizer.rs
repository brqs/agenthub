use regex::Regex;

pub fn sanitize_text(input: &str) -> String {
    let mut output = input.to_string();
    let patterns = [
        (
            r"(?i)\b(ANTHROPIC_API_KEY|OPENAI_API_KEY|DEEPSEEK_API_KEY|CLAUDE_[A-Z0-9_]+|OPENCODE_[A-Z0-9_]+)\s*=\s*[^\s]+",
            "$1=[REDACTED]",
        ),
        (
            r"(?i)\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._\-]+",
            "Authorization: Bearer [REDACTED]",
        ),
        (r"(?i)\bBearer\s+[A-Za-z0-9._\-]{8,}", "Bearer [REDACTED]"),
        (
            r"(?i)(postgres(?:ql)?(?:\+[a-z0-9]+)?://[^:\s/@]+:)[^@\s]+(@)",
            "$1[REDACTED]$2",
        ),
        (
            r"(?i)\b(sk-(?:ant-|proj-)?[A-Za-z0-9_\-]{8,})",
            "[REDACTED_API_KEY]",
        ),
    ];
    for (pattern, replacement) in patterns {
        if let Ok(regex) = Regex::new(pattern) {
            output = regex.replace_all(&output, replacement).into_owned();
        }
    }
    output
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn redacts_credentials_without_hiding_normal_logs() {
        let raw = "ANTHROPIC_API_KEY=sk-ant-secret\nAuthorization: Bearer abc.def.ghi\npostgresql://agenthub:password@postgres:5432/agenthub\nready";
        let clean = sanitize_text(raw);
        assert!(!clean.contains("sk-ant-secret"));
        assert!(!clean.contains("abc.def.ghi"));
        assert!(!clean.contains(":password@"));
        assert!(clean.contains("ready"));
    }
}
