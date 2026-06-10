mod deep_link;
mod connector;
mod diagnostics;
mod environment;
mod error;
mod logs;
mod models;
mod native;
mod process;
mod project;
mod release;
mod sanitizer;
mod stack;
mod state;

use tauri::Manager;
use tauri::WebviewWindowBuilder;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let mut builder = tauri::Builder::default();

    #[cfg(windows)]
    {
        builder = builder.plugin(tauri_plugin_single_instance::init(|app, args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
            crate::deep_link::emit_deep_links(app, args);
        }));
    }

    builder
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .setup(|app| {
            let app_data_dir = app.path().app_data_dir()?;
            let state = state::AppState::new(app_data_dir)
                .map_err(|error| -> Box<dyn std::error::Error> { Box::new(error) })?;
            let webview_data_dir = state.app_data_dir.join("webview-v2");
            release::install_panic_hook(state.crash_log_path());
            app.manage(state);
            let window_config = app
                .config()
                .app
                .windows
                .iter()
                .find(|window| window.label == "main")
                .ok_or("main window config is missing")?;
            WebviewWindowBuilder::from_config(app, window_config)?
                .data_directory(webview_data_dir)
                .build()?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            environment::desktop_get_environment,
            environment::desktop_choose_project_root,
            environment::desktop_get_stack_binding,
            stack::desktop_check_local_stack,
            stack::desktop_start_local_stack,
            stack::desktop_stop_local_stack,
            stack::desktop_restart_backend,
            logs::desktop_tail_service_logs,
            diagnostics::desktop_export_diagnostics,
            diagnostics::desktop_save_diagnostics,
            environment::desktop_get_preferences,
            environment::desktop_set_preferences,
            native::desktop_open_workspace_folder,
            native::desktop_open_external_url,
            native::desktop_show_notification,
            release::desktop_get_release_info,
            release::desktop_check_for_update,
            release::desktop_install_update,
            release::desktop_open_release_page,
            release::desktop_collect_crash_report,
            connector::desktop_probe_local_runtime_connector,
            connector::desktop_start_local_runtime_connector,
            connector::desktop_stop_local_runtime_connector,
        ])
        .run(tauri::generate_context!())
        .expect("error while running AgentHub Desktop");
}
