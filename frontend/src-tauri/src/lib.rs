use std::sync::Mutex;
use tauri::Manager;
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

struct BackendProcess(Mutex<Option<CommandChild>>);

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
                // 尝试从 exe 位置推断 backend 目录（开发模式）
                // 结构: frontend/src-tauri/target/release/app.exe → 上4级 → backend/
                let backend_dir = std::env::current_exe()
                    .ok()
                    .and_then(|p| p.parent().map(|d| d.to_path_buf()))
                    .and_then(|d| {
                        let rel = d.join("../../../../backend");
                        if rel.join("main.py").exists() {
                            Some(rel)
                        } else {
                            // 如果相对路径不存在，试试 Cargo 工作目录（开发模式）
                            let cwd_rel = std::env::current_dir().ok()?.join("../backend");
                            if cwd_rel.join("main.py").exists() {
                                Some(cwd_rel)
                            } else {
                                None
                            }
                        }
                    });

                let (rx, child) = app
                    .shell()
                    .command("python")
                    .args([
                        "-m", "uvicorn", "main:app",
                        "--host", "127.0.0.1", "--port", "8765",
                    ])
                    .current_dir(&backend_dir)
                    .spawn()
                    .expect("failed to spawn backend");

                // 异步消费输出，避免管道阻塞
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

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
