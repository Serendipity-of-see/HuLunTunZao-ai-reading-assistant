use std::sync::Mutex;
use tauri::Manager;
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

struct BackendProcess(Mutex<Option<CommandChild>>);

fn find_backend_dir() -> Option<std::path::PathBuf> {
    let exe_dir = std::env::current_exe().ok()?.parent()?.to_path_buf();

    // 结构: frontend/src-tauri/target/release/app.exe → 上4级 → backend/
    let rel = exe_dir.join("../../../../backend");
    if rel.join("main.py").exists() {
        return Some(rel);
    }

    // 回退：CWD 的 ../backend
    let cwd_rel = std::env::current_dir().ok()?.join("../backend");
    if cwd_rel.join("main.py").exists() {
        return Some(cwd_rel);
    }

    None
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            // 生产模式：通过 shell 插件启动 Python 后端
            if !cfg!(debug_assertions) {
                let backend_dir = find_backend_dir();
                let mut cmd = app
                    .shell()
                    .command("python")
                    .args([
                        "-m", "uvicorn", "main:app",
                        "--host", "127.0.0.1", "--port", "8765",
                    ]);

                if let Some(ref dir) = backend_dir {
                    cmd = cmd.current_dir(dir);
                }

                match cmd.spawn() {
                    Ok((rx, child)) => {
                        // 异步消费 stderr，避免管道阻塞
                        tauri::async_runtime::spawn(async move {
                            use tauri_plugin_shell::process::CommandEvent;
                            let mut rx = rx;
                            while let Some(event) = rx.recv().await {
                                if let CommandEvent::Stderr(line) = event {
                                    eprintln!("[backend] {}", String::from_utf8_lossy(&line));
                                }
                            }
                        });
                        app.manage(BackendProcess(Mutex::new(Some(child))));
                    }
                    Err(e) => {
                        eprintln!("[Tauri] Failed to start Python backend: {e}");
                        eprintln!("[Tauri] Please ensure Python 3.11+ and uvicorn are installed.");
                        // App 继续运行，前端显示 backend 不可用
                    }
                }
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
