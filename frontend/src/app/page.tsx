"use client";

import { useEffect, useRef, useState, useCallback } from "react";

// Types
interface IndexedItem {
  name: string;
  path: string;
  kind: string;
  icon: string;
}

// Detect if running in Tauri
const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

async function invoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  if (isTauri) {
    try {
      const { invoke: tauriInvoke } = await import("@tauri-apps/api/core");
      return await tauriInvoke<T>(cmd, args);
    } catch (e) {
      console.error("Tauri invoke error:", e);
      throw e;
    }
  }
  return [] as unknown as T;
}

async function listenEvent(event: string, handler: () => void) {
  if (isTauri) {
    const { listen } = await import("@tauri-apps/api/event");
    return listen(event, handler);
  }
  return undefined;
}

async function hideWindow() {
  if (isTauri) {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    await getCurrentWindow().hide();
  }
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<IndexedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [showSettings, setShowSettings] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Load indexed items, and refresh when background indexing completes.
  useEffect(() => {
    let unlisten: (() => void) | undefined;
    let cancelled = false;

    async function refresh() {
      try {
        const result = await invoke<IndexedItem[]>("get_indexed_items");
        if (cancelled) return;
        if (result && result.length > 0) {
          setItems(result);
          setLoading(false);
        }
      } catch (e) {
        console.error("Failed to load items:", e);
      }
    }

    async function init() {
      // The cache may already be populated on a fast machine.
      await refresh();
      // Indexing runs on a background thread; refresh when it signals ready.
      unlisten = await listenEvent("index-ready", () => {
        setLoading(false);
        refresh();
      });
      // Fallback so we never spin forever if the event was missed.
      setTimeout(() => {
        if (!cancelled) setLoading(false);
      }, 8000);
    }

    init();
    return () => {
      cancelled = true;
      if (unlisten) unlisten();
    };
  }, []);

  // Listen for focus-search event from Tauri (on hotkey toggle)
  useEffect(() => {
    let unlisten: (() => void) | undefined;
    (async () => {
      unlisten = await listenEvent("focus-search", () => {
        inputRef.current?.focus();
        setQuery("");
        setShowSettings(false);
      });
    })();
    return () => {
      if (unlisten) unlisten();
    };
  }, []);

  // Derive the filtered list during render (no effect, no cascading state).
  const filtered =
    query.trim() === ""
      ? items
      : items.filter((item) =>
          item.name.toLowerCase().includes(query.toLowerCase())
        );

  // Open the selected item
  const openItem = useCallback(async (item: IndexedItem) => {
    try {
      await invoke("open_item", { path: item.path });
    } catch (e) {
      console.error("Failed to open item:", e);
    }
  }, []);

  const quitApp = useCallback(async () => {
    try {
      await invoke("quit_app");
    } catch (e) {
      console.error("Failed to quit:", e);
    }
  }, []);

  // Keyboard navigation (horizontal layout)
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowRight" || e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((prev) => Math.min(prev + 1, filtered.length - 1));
      } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((prev) => Math.max(prev - 1, 0));
      } else if (e.key === "Enter" && filtered[selectedIndex]) {
        e.preventDefault();
        openItem(filtered[selectedIndex]);
      } else if (e.key === "Escape") {
        if (showSettings) {
          setShowSettings(false);
        } else {
          hideWindow();
        }
      }
    },
    [filtered, selectedIndex, openItem, showSettings]
  );

  // Auto-scroll selected item into view
  useEffect(() => {
    const listEl = listRef.current;
    if (listEl) {
      const selected = listEl.children[selectedIndex] as HTMLElement;
      if (selected) {
        selected.scrollIntoView({ block: "nearest", inline: "nearest" });
      }
    }
  }, [selectedIndex]);

  const displayItems = filtered;

  return (
    <div
      className="w-full h-screen flex flex-col relative overflow-hidden"
      onKeyDown={handleKeyDown}
    >
      {/* Window Frame */}
      <div className="pixel-window flex-1 flex flex-col">
        {/* Title Bar */}
        <div className="pixel-titlebar">
          <span className="pixel-title">ATLAS</span>
          <div className="pixel-controls">
            <button
              className="pixel-btn-settings"
              title="Settings"
              onClick={() => setShowSettings((s) => !s)}
            >
              <span>⚙</span>
            </button>
            <button
              className="pixel-btn-close"
              title="Close (Esc)"
              onClick={() => hideWindow()}
            >
              <span>✕</span>
            </button>
          </div>
        </div>

        {/* Content Area */}
        <div className="pixel-content flex-1 flex flex-col">
          {/* Search Bar */}
          <div className="pixel-searchbar">
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setSelectedIndex(0);
              }}
              placeholder="Search anything..."
              autoFocus
              className="pixel-search-input"
            />
            <span className="pixel-search-icon">🔍</span>
          </div>

          {/* Items Grid */}
          <div ref={listRef} className="pixel-grid flex-1 overflow-auto">
            {loading ? (
              <div className="col-span-5 flex items-center justify-center h-24">
                <span className="pixel-text pixel-loading">Indexing...</span>
              </div>
            ) : displayItems.length === 0 ? (
              <div className="col-span-5 flex items-center justify-center h-24">
                <span className="pixel-text">No items found</span>
              </div>
            ) : (
              displayItems.map((item, index) => (
                <button
                  key={`${item.kind}-${item.path}`}
                  onClick={() => openItem(item)}
                  className={`pixel-item ${selectedIndex === index ? "selected" : ""}`}
                >
                  <div className="pixel-item-icon">
                    <img src="/folder.svg" alt={item.name} className="folder-icon" />
                  </div>
                  <span className="pixel-item-name">{item.name}</span>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Settings Panel */}
        {showSettings && (
          <div className="pixel-settings-overlay" onClick={() => setShowSettings(false)}>
            <div className="pixel-settings-panel" onClick={(e) => e.stopPropagation()}>
              <div className="pixel-settings-title">Settings</div>
              <div className="pixel-settings-row">
                <span>Indexed items</span>
                <span>{items.length}</span>
              </div>
              <div className="pixel-settings-row">
                <span>Toggle launcher</span>
                <span>Win + -</span>
              </div>
              <div className="pixel-settings-actions">
                <button
                  className="pixel-settings-btn"
                  onClick={() => setShowSettings(false)}
                >
                  Close
                </button>
                <button
                  className="pixel-settings-btn pixel-settings-btn-danger"
                  onClick={() => quitApp()}
                >
                  Quit ATLAS
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
