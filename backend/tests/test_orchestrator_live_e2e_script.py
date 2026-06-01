from scripts.orchestrator_live_e2e import SERVER_COMMAND_RE


def test_server_command_scan_ignores_negated_server_js_filename() -> None:
    assert SERVER_COMMAND_RE.search("No server.js or package.json was created.") is None


def test_server_command_scan_rejects_executable_server_js_command() -> None:
    assert SERVER_COMMAND_RE.search("Run node server.js to serve the app.") is not None
