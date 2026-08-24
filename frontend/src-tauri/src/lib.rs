use serde::Serialize;
use std::path::PathBuf;
use std::sync::{Mutex, OnceLock};
use tauri::{Emitter, Manager};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut};
use walkdir::WalkDir;

// Static cache for indexed items
static INDEXED_ITEMS: OnceLock<Mutex<Vec<IndexedItem>>> = OnceLock::new();

fn get_cached_items() -> Vec<IndexedItem> {
    INDEXED_ITEMS
        .get()
        .map(|m| m.lock().unwrap().clone())
        .unwrap_or_default()
}

fn initialize_index() {
    eprintln!("=== Initializing index at startup ===");
    let mut all = scan_apps();
    all.extend(scan_user_folders());
    eprintln!("=== Index complete: {} total items ===", all.len());
    
    let _ = INDEXED_ITEMS.set(Mutex::new(all));
}

#[derive(Debug, Clone, Serialize)]
pub struct IndexedItem {
    pub name: String,
    pub path: String,
    pub kind: String, // "app", "file", "folder", "image", "video", "document"
    pub icon: String, // emoji or icon hint
}

fn detect_kind(path: &std::path::Path, is_app: bool) -> (String, String) {
    if is_app {
        return ("app".into(), "🖥️".into());
    }
    if path.is_dir() {
        return ("folder".into(), "📁".into());
    }

    let ext = path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_lowercase();

    match ext.as_str() {
        "png" | "jpg" | "jpeg" | "gif" | "bmp" | "svg" | "webp" | "ico" => {
            ("image".into(), "🖼️".into())
        }
        "mp4" | "mkv" | "avi" | "mov" | "webm" | "flv" => ("video".into(), "🎬".into()),
        "mp3" | "wav" | "flac" | "ogg" | "aac" => ("audio".into(), "🎵".into()),
        "pdf" | "doc" | "docx" | "txt" | "rtf" | "odt" | "xls" | "xlsx" | "ppt" | "pptx" => {
            ("document".into(), "📄".into())
        }
        "zip" | "rar" | "7z" | "tar" | "gz" => ("archive".into(), "📦".into()),
        "exe" | "msi" => ("app".into(), "🖥️".into()),
        "lnk" => ("shortcut".into(), "🔗".into()),
        _ => ("file".into(), "📄".into()),
    }
}

fn scan_user_folders() -> Vec<IndexedItem> {
    let mut items = Vec::new();

    eprintln!("=== Starting user folders scan ===");

    if let Some(user_dir) = dirs::home_dir() {
        eprintln!("User home: {:?}", user_dir);
        let folders = ["Desktop", "Downloads", "Documents", "Pictures", "Videos"];

        for folder_name in &folders {
            let folder_path = user_dir.join(folder_name);
            eprintln!("Scanning folder: {:?}", folder_path);
            
            if !folder_path.exists() {
                eprintln!("  -> Folder does not exist!");
                continue;
            }

            let mut count = 0;
            // Walk max 4 levels deep for better coverage
            for entry in WalkDir::new(&folder_path)
                .max_depth(4)
                .into_iter()
                .filter_map(|e| e.ok())
            {
                let path = entry.path();

                // Skip the root folder itself
                if path == folder_path {
                    continue;
                }

                let name = path
                    .file_name()
                    .and_then(|n| n.to_str())
                    .unwrap_or("")
                    .to_string();

                if name.starts_with('.') {
                    continue;
                }

                let (kind, icon) = detect_kind(path, false);

                items.push(IndexedItem {
                    name,
                    path: path.to_string_lossy().to_string(),
                    kind,
                    icon,
                });
                count += 1;
            }
            eprintln!("  -> Found {} items in {}", count, folder_name);
        }
    } else {
        eprintln!("ERROR: Could not get home directory!");
    }

    eprintln!("=== Total user files found: {} ===", items.len());
    items
}

fn scan_apps() -> Vec<IndexedItem> {
    let mut items = Vec::new();
    let mut seen = std::collections::HashSet::new();

    eprintln!("=== Starting app scan ===");

    // Scan common app locations on Windows
    let mut app_dirs: Vec<PathBuf> = vec![
        // Start Menu - All Users
        PathBuf::from(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"),
    ];

    // Add user-specific Start Menu
    if let Some(home) = dirs::home_dir() {
        eprintln!("Home directory: {:?}", home);
        app_dirs.push(home.join(r"AppData\Roaming\Microsoft\Windows\Start Menu\Programs"));
        app_dirs.push(home.join("Desktop"));
    }

    // Scan Start Menu locations (deep scan for shortcuts)
    for app_dir in &app_dirs {
        eprintln!("Scanning directory: {:?}", app_dir);
        if !app_dir.exists() {
            eprintln!("  -> Directory does not exist!");
            continue;
        }

        let mut count = 0;
        for entry in WalkDir::new(&app_dir)
            .max_depth(5) // Increased depth to find more nested shortcuts
            .into_iter()
            .filter_map(|e| e.ok())
        {
            let path = entry.path();
            let ext = path
                .extension()
                .and_then(|e| e.to_str())
                .unwrap_or("")
                .to_lowercase();

            if ext == "lnk" {
                let name = path
                    .file_stem()
                    .and_then(|n| n.to_str())
                    .unwrap_or("")
                    .to_string();

                // Filter out common system/uninstall shortcuts
                let name_lower = name.to_lowercase();
                if name.is_empty() 
                    || seen.contains(&name_lower)
                    || name_lower.contains("uninstall")
                    || name_lower.contains("readme")
                    || name_lower.contains("help")
                    || name_lower.starts_with("unins")
                {
                    continue;
                }
                seen.insert(name_lower);

                items.push(IndexedItem {
                    name: name.clone(),
                    path: path.to_string_lossy().to_string(),
                    kind: "app".into(),
                    icon: "🖥️".into(),
                });
                count += 1;
            }
        }
        eprintln!("  -> Found {} apps in this directory", count);
    }

    // Also scan Program Files for common apps (limited depth)
    let program_dirs = vec![
        PathBuf::from(r"C:\Program Files"),
        PathBuf::from(r"C:\Program Files (x86)"),
    ];

    for program_dir in program_dirs {
        eprintln!("Scanning Program Files: {:?}", program_dir);
        if !program_dir.exists() {
            eprintln!("  -> Directory does not exist!");
            continue;
        }

        let mut count = 0;
        for entry in WalkDir::new(&program_dir)
            .max_depth(2) // Only go 2 levels deep in Program Files
            .into_iter()
            .filter_map(|e| e.ok())
        {
            let path = entry.path();
            let ext = path
                .extension()
                .and_then(|e| e.to_str())
                .unwrap_or("")
                .to_lowercase();

            // Only look for executables in the root of app folders
            if ext == "exe" && path.parent().is_some() {
                let name = path
                    .file_stem()
                    .and_then(|n| n.to_str())
                    .unwrap_or("")
                    .to_string();

                let name_lower = name.to_lowercase();
                // Filter out setup/uninstall executables and duplicates
                if !name.is_empty() 
                    && !seen.contains(&name_lower)
                    && !name_lower.contains("uninstall")
                    && !name_lower.contains("setup")
                    && !name_lower.starts_with("unins")
                {
                    seen.insert(name_lower);
                    items.push(IndexedItem {
                        name: name.clone(),
                        path: path.to_string_lossy().to_string(),
                        kind: "app".into(),
                        icon: "🖥️".into(),
                    });
                    count += 1;
                }
            }
        }
        eprintln!("  -> Found {} apps in Program Files", count);
    }

    eprintln!("=== Total applications found: {} ===", items.len());
    items
}

#[tauri::command]
fn get_indexed_items() -> Vec<IndexedItem> {
    let items = get_cached_items();
    eprintln!("get_indexed_items called, returning {} items", items.len());
    items
}

#[tauri::command]
fn open_item(path: String) -> Result<(), String> {
    open::that(&path).map_err(|e| format!("Failed to open {}: {}", path, e))
}

#[tauri::command]
fn quit_app(app: tauri::AppHandle) {
    app.exit(0);
}

fn toggle_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        if window.is_visible().unwrap_or(false) {
            let _ = window.hide();
        } else {
            let _ = window.show();
            let _ = window.set_focus();
            let _ = window.center();
            // Tell the frontend to focus the search input
            let _ = window.emit("focus-search", ());
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // Index files on a background thread so the window paints immediately.
            // When indexing finishes, notify the UI so it can load the results.
            let index_handle = app.handle().clone();
            std::thread::spawn(move || {
                initialize_index();
                if let Some(window) = index_handle.get_webview_window("main") {
                    let _ = window.emit("index-ready", get_cached_items().len());
                }
            });

            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            // Register Win+- global shortcut
            let shortcut = Shortcut::new(Some(Modifiers::SUPER), Code::Minus);
            let handle = app.handle().clone();

            app.handle().plugin(
                tauri_plugin_global_shortcut::Builder::new()
                    .with_handler(move |_app, _shortcut, event| {
                        if event.state == tauri_plugin_global_shortcut::ShortcutState::Pressed {
                            toggle_window(&handle);
                        }
                    })
                    .build(),
            )?;

            // Try to register the shortcut, but don't fail if it's already registered
            if let Err(e) = app.global_shortcut().register(shortcut) {
                eprintln!("Warning: Failed to register global shortcut: {}", e);
            }

            // Also hide window when it loses focus
            let window = app.get_webview_window("main").unwrap();
            let w = window.clone();
            window.on_window_event(move |event| {
                if let tauri::WindowEvent::Focused(false) = event {
                    let _ = w.hide();
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_indexed_items,
            open_item,
            quit_app
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
