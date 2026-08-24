"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useAgentClient, type AgentEvent } from "./agentClient";

// Types
interface IndexedItem {
  name: string;
  path: string;
  kind: string;
  icon: string;
}

const HOST_STORAGE_KEY = "atlas.agent.host";
const PORT_STORAGE_KEY = "atlas.agent.port";
const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = "8000";

// Read a persisted setting during state initialization. Guarded so the static
// export prerender (no window) falls back to the default without throwing.
function readStored(key: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  try {
    return window.localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}

function writeStored(key: string, value: string) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Ignore: persistence is best effort.
  }
}

// Render one console entry as a single readable line.
function formatEvent(evt: AgentEvent): string {
  if (evt.kind === "progress") {
    const head = [evt.step, evt.status].filter(Boolean).join(" - ");
    return evt.detail ? `${head}${head ? ": " : ""}${evt.detail}` : head || "progress";
  }
  if (evt.kind === "result") {
    const label = evt.success === false ? "FAILED" : "DONE";
    return evt.detail ? `${label}: ${evt.detail}` : label;
  }
  if (evt.kind === "error") {
    return evt.message || "error";
  }
  return evt.detail || "";
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

  // Agent command console state.
  const agent = useAgentClient();
  const [showConsole, setShowConsole] = useState(false);
  const [command, setCommand] = useState("");
  const [agentHost, setAgentHost] = useState<string>(() =>
    readStored(HOST_STORAGE_KEY, DEFAULT_HOST)
  );
  const [agentPort, setAgentPort] = useState<string>(() =>
    readStored(PORT_STORAGE_KEY, DEFAULT_PORT)
  );
  const commandRef = useRef<HTMLInputElement>(null);
  const feedEndRef = useRef<HTMLDivElement>(null);

  const updateHost = useCallback((value: string) => {
    setAgentHost(value);
    writeStored(HOST_STORAGE_KEY, value);
  }, []);

  const updatePort = useCallback((value: string) => {
    setAgentPort(value);
    writeStored(PORT_STORAGE_KEY, value);
  }, []);

  const openConsole = useCallback(() => {
    setShowSettings(false);
    setShowConsole(true);
    agent.checkHealth(agentHost, agentPort);
  }, [agent, agentHost, agentPort]);

  const toggleConsole = useCallback(() => {
    if (showConsole) {
      setShowConsole(false);
    } else {
      openConsole();
    }
  }, [showConsole, openConsole]);

  const sendCurrentCommand = useCallback(() => {
    const text = command.trim();
    if (text === "") return;
    agent.sendCommand(text, agentHost, agentPort);
    setCommand("");
  }, [agent, command, agentHost, agentPort]);

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
        setShowConsole(false);
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
      // Ctrl + backquote toggles the agent console from anywhere.
      if (e.ctrlKey && e.key === "`") {
        e.preventDefault();
        toggleConsole();
        return;
      }
      // While the console is open it owns the keyboard; let its own handlers
      // (Enter to send, Escape to close) drive things instead of file nav.
      if (showConsole) {
        return;
      }
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
    [filtered, selectedIndex, openItem, showSettings, showConsole, toggleConsole]
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

  // Keep the console feed pinned to the newest event (DOM only, no state).
  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ block: "nearest" });
  }, [agent.events]);

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
              className={`pixel-btn-agent ${showConsole ? "active" : ""}`}
              title="Agent console (Ctrl + `)"
              onClick={toggleConsole}
            >
              <span>&gt;_</span>
            </button>
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

        {/* Agent Command Console */}
        {showConsole && (
          <div
            className="pixel-console-overlay"
            onClick={() => setShowConsole(false)}
          >
            <div
              className="pixel-console-panel"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="pixel-console-header">
                <span className="pixel-console-title">Agent</span>
                <span className={`pixel-console-state ${agent.connectionState}`}>
                  {agent.connectionState}
                </span>
              </div>

              {/* Backend target settings */}
              <div className="pixel-console-config">
                <label className="pixel-console-field">
                  <span>Host</span>
                  <input
                    className="pixel-console-config-input"
                    value={agentHost}
                    onChange={(e) => updateHost(e.target.value)}
                    onKeyDown={(e) => e.stopPropagation()}
                    placeholder={DEFAULT_HOST}
                    spellCheck={false}
                  />
                </label>
                <label className="pixel-console-field">
                  <span>Port</span>
                  <input
                    className="pixel-console-config-input pixel-console-port"
                    value={agentPort}
                    onChange={(e) => updatePort(e.target.value)}
                    onKeyDown={(e) => e.stopPropagation()}
                    placeholder={DEFAULT_PORT}
                    spellCheck={false}
                  />
                </label>
                <button
                  className={`pixel-console-health ${agent.health}`}
                  onClick={() => agent.checkHealth(agentHost, agentPort)}
                  title="Check backend /health"
                >
                  {agent.health === "reachable"
                    ? "reachable"
                    : agent.health === "unreachable"
                      ? "unreachable"
                      : agent.health === "checking"
                        ? "checking..."
                        : "check"}
                </button>
              </div>

              {/* Live event feed */}
              <div className="pixel-console-feed">
                {agent.events.length === 0 ? (
                  <div className="pixel-console-empty">
                    Type a command to talk to the agent.
                  </div>
                ) : (
                  agent.events.map((evt) => (
                    <div
                      key={evt.id}
                      className={`pixel-console-line ${evt.kind}`}
                    >
                      {formatEvent(evt)}
                    </div>
                  ))
                )}
                <div ref={feedEndRef} />
              </div>

              {/* Command input row */}
              <div className="pixel-console-input-row">
                <input
                  ref={commandRef}
                  className="pixel-console-input"
                  value={command}
                  onChange={(e) => setCommand(e.target.value)}
                  onKeyDown={(e) => {
                    e.stopPropagation();
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      sendCurrentCommand();
                    } else if (e.key === "Escape") {
                      e.preventDefault();
                      setShowConsole(false);
                    }
                  }}
                  placeholder="Ask the agent to do something..."
                  autoFocus
                  spellCheck={false}
                />
                <button
                  className="pixel-console-btn"
                  onClick={sendCurrentCommand}
                >
                  Send
                </button>
                <button
                  className="pixel-console-btn pixel-console-btn-stop"
                  onClick={() => agent.stop()}
                >
                  Stop
                </button>
              </div>

              <div className="pixel-console-actions">
                <button
                  className="pixel-console-link"
                  onClick={() => agent.clearEvents()}
                >
                  Clear log
                </button>
                <button
                  className="pixel-console-link"
                  onClick={() => setShowConsole(false)}
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
