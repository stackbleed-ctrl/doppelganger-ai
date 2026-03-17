// Doppelganger Tauri Desktop App
// Manages the Python backend process, system tray, and IPC bridge.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::{Arc, Mutex};
use std::process::{Child, Command, Stdio};
use tauri::{
    AppHandle, CustomMenuItem, Manager, State, SystemTray,
    SystemTrayEvent, SystemTrayMenu, SystemTrayMenuItem,
    Window, WindowEvent,
};

// ─── State ───────────────────────────────────────────────────────────────────

struct BackendProcess(Arc<Mutex<Option<Child>>>);

struct AppConfig {
    api_port: u16,
    api_url: String,
}

// ─── Commands (IPC from frontend) ────────────────────────────────────────────

#[tauri::command]
async fn get_health(config: State<'_, AppConfig>) -> Result<serde_json::Value, String> {
    let url = format!("{}/health", config.api_url);
    let resp = reqwest::get(&url)
        .await
        .map_err(|e| e.to_string())?
        .json::<serde_json::Value>()
        .await
        .map_err(|e| e.to_string())?;
    Ok(resp)
}

#[tauri::command]
async fn send_chat(
    message: String,
    config: State<'_, AppConfig>,
) -> Result<String, String> {
    let url = format!("{}/chat", config.api_url);
    let client = reqwest::Client::new();
    let resp = client
        .post(&url)
        .json(&serde_json::json!({"message": message}))
        .send()
        .await
        .map_err(|e| e.to_string())?
        .json::<serde_json::Value>()
        .await
        .map_err(|e| e.to_string())?;
    Ok(resp["response"].as_str().unwrap_or("").to_string())
}

#[tauri::command]
async fn switch_persona(
    persona_id: String,
    config: State<'_, AppConfig>,
) -> Result<serde_json::Value, String> {
    let url = format!("{}/personas/{}/activate", config.api_url, persona_id);
    let client = reqwest::Client::new();
    let resp = client
        .post(&url)
        .send()
        .await
        .map_err(|e| e.to_string())?
        .json::<serde_json::Value>()
        .await
        .map_err(|e| e.to_string())?;
    Ok(resp)
}

#[tauri::command]
async fn list_personas(config: State<'_, AppConfig>) -> Result<serde_json::Value, String> {
    let url = format!("{}/personas", config.api_url);
    let resp = reqwest::get(&url)
        .await
        .map_err(|e| e.to_string())?
        .json::<serde_json::Value>()
        .await
        .map_err(|e| e.to_string())?;
    Ok(resp)
}

#[tauri::command]
fn get_backend_status(process: State<'_, BackendProcess>) -> String {
    let guard = process.0.lock().unwrap();
    if guard.is_some() {
        "running".to_string()
    } else {
        "stopped".to_string()
    }
}

#[tauri::command]
async fn restart_backend(
    process: State<'_, BackendProcess>,
    app: AppHandle,
) -> Result<String, String> {
    stop_backend_process(&process);
    tokio::time::sleep(tokio::time::Duration::from_secs(1)).await;
    start_backend_process(&process, &app)?;
    Ok("restarted".to_string())
}

// ─── Backend process management ───────────────────────────────────────────────

fn find_python() -> Option<String> {
    for candidate in &["python3", "python", "python3.11", "python3.12"] {
        if which::which(candidate).is_ok() {
            return Some(candidate.to_string());
        }
    }
    None
}

fn start_backend_process(
    process: &State<'_, BackendProcess>,
    app: &AppHandle,
) -> Result<(), String> {
    let python = find_python().ok_or("Python not found. Install Python 3.11+")?;

    let resource_path = app
        .path_resolver()
        .resource_dir()
        .ok_or("Could not resolve resource dir")?;

    let backend_path = resource_path.join("backend");
    let venv_pip = backend_path.join(".venv").join("bin").join("pip");

    // Install deps if venv not set up
    if !venv_pip.exists() {
        Command::new(&python)
            .args(["-m", "venv", ".venv"])
            .current_dir(&backend_path)
            .status()
            .map_err(|e| e.to_string())?;

        let venv_python = backend_path.join(".venv").join("bin").join("python");
        Command::new(&venv_python)
            .args(["-m", "pip", "install", "-e", ".", "--quiet"])
            .current_dir(&backend_path)
            .status()
            .map_err(|e| e.to_string())?;
    }

    let venv_python = backend_path.join(".venv").join("bin").join("python");
    let python_bin = if venv_python.exists() {
        venv_python.to_string_lossy().to_string()
    } else {
        python
    };

    let child = Command::new(&python_bin)
        .args(["-m", "uvicorn", "doppelganger.interfaces.api:get_app",
               "--host", "127.0.0.1", "--port", "8000",
               "--factory", "--workers", "1"])
        .current_dir(&backend_path)
        .env("PYTHONPATH", backend_path.join("src").to_string_lossy().to_string())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to start backend: {}", e))?;

    *process.0.lock().unwrap() = Some(child);
    Ok(())
}

fn stop_backend_process(process: &State<'_, BackendProcess>) {
    let mut guard = process.0.lock().unwrap();
    if let Some(mut child) = guard.take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

// ─── System tray ─────────────────────────────────────────────────────────────

fn build_tray() -> SystemTray {
    let open     = CustomMenuItem::new("open", "Open Dashboard");
    let persona  = CustomMenuItem::new("persona", "Switch Persona...");
    let sep      = SystemTrayMenuItem::Separator;
    let restart  = CustomMenuItem::new("restart", "Restart Backend");
    let quit     = CustomMenuItem::new("quit", "Quit Doppelganger");

    let menu = SystemTrayMenu::new()
        .add_item(open)
        .add_item(persona)
        .add_native_item(sep)
        .add_item(restart)
        .add_native_item(SystemTrayMenuItem::Separator)
        .add_item(quit);

    SystemTray::new().with_menu(menu)
}

fn handle_tray_event(app: &AppHandle, event: SystemTrayEvent) {
    match event {
        SystemTrayEvent::LeftClick { .. } => {
            if let Some(window) = app.get_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }
        SystemTrayEvent::MenuItemClick { id, .. } => match id.as_str() {
            "open" => {
                if let Some(window) = app.get_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
            "restart" => {
                let process = app.state::<BackendProcess>();
                stop_backend_process(&process);
                let _ = start_backend_process(&process, app);
            }
            "quit" => {
                let process = app.state::<BackendProcess>();
                stop_backend_process(&process);
                app.exit(0);
            }
            _ => {}
        },
        _ => {}
    }
}

// ─── Main ─────────────────────────────────────────────────────────────────────

fn main() {
    let api_port: u16 = 8000;
    let process = BackendProcess(Arc::new(Mutex::new(None)));

    tauri::Builder::default()
        .manage(process)
        .manage(AppConfig {
            api_port,
            api_url: format!("http://127.0.0.1:{}", api_port),
        })
        .system_tray(build_tray())
        .on_system_tray_event(handle_tray_event)
        .setup(|app| {
            let process = app.state::<BackendProcess>();
            match start_backend_process(&process, &app.handle()) {
                Ok(_) => println!("Backend started"),
                Err(e) => eprintln!("Backend start failed: {}", e),
            }
            Ok(())
        })
        .on_window_event(|event| {
            if let WindowEvent::CloseRequested { api, .. } = event.event() {
                // Hide to tray instead of quit
                event.window().hide().unwrap();
                api.prevent_close();
            }
        })
        .invoke_handler(tauri::generate_handler![
            get_health,
            send_chat,
            switch_persona,
            list_personas,
            get_backend_status,
            restart_backend,
        ])
        .run(tauri::generate_context!())
        .expect("error running Doppelganger");
}
