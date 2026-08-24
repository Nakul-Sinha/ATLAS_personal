"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// Connection lifecycle for the backend agent WebSocket.
export type ConnectionState =
  | "disconnected"
  | "connecting"
  | "connected"
  | "error";

// Result of the optional /health probe.
export type HealthStatus =
  | "unknown"
  | "checking"
  | "reachable"
  | "unreachable";

export type AgentEventKind = "progress" | "result" | "error" | "info";

// A normalized entry rendered in the console feed. Server messages are
// parsed into this shape; "info" entries are produced locally (echoed
// commands, status notes) so the feed reads as a single stream.
export interface AgentEvent {
  id: number;
  kind: AgentEventKind;
  step?: string;
  status?: string;
  detail?: string;
  message?: string;
  success?: boolean;
  plan?: string[];
  ts: number;
}

// A message queued while the socket is not yet open. Preserving the type lets
// a preview stay a preview (and a command stay a command) once we flush.
interface PendingMessage {
  type: "command" | "plan";
  command: string;
}

interface Target {
  host: string;
  port: string;
}

const MAX_EVENTS = 200;
const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_DELAY_MS = 2000;
const HEALTH_TIMEOUT_MS = 3000;

function normalizeTarget(host: string, port: string): Target {
  return {
    host: host.trim() || "127.0.0.1",
    port: port.trim() || "8000",
  };
}

function wsUrl(t: Target): string {
  return `ws://${t.host}:${t.port}/ws`;
}

function healthUrl(t: Target): string {
  return `http://${t.host}:${t.port}/health`;
}

// Extract a plan (dry-run) step list from a message field, keeping only the
// string entries. Returns undefined when there is nothing plan-shaped to show.
function parsePlan(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const steps = value.filter((s): s is string => typeof s === "string");
  return steps.length > 0 ? steps : undefined;
}

export interface UseAgentClient {
  connectionState: ConnectionState;
  events: AgentEvent[];
  health: HealthStatus;
  sendCommand: (command: string, host: string, port: string) => void;
  sendPlan: (command: string, host: string, port: string) => void;
  stop: () => void;
  checkHealth: (host: string, port: string) => void;
  disconnect: () => void;
  clearEvents: () => void;
}

// A small WebSocket client for the ATLAS backend agent. It uses the browser
// WebSocket API only, so it runs unchanged inside the Tauri webview and in a
// normal browser. All connection failures are contained here: nothing thrown
// from a socket handler is allowed to reach the React tree.
export function useAgentClient(token: string = ""): UseAgentClient {
  const [connectionState, setConnectionState] =
    useState<ConnectionState>("disconnected");
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [health, setHealth] = useState<HealthStatus>("unknown");

  const wsRef = useRef<WebSocket | null>(null);
  const targetRef = useRef<Target | null>(null);
  const pendingRef = useRef<PendingMessage[]>([]);
  const idRef = useRef(0);
  // Keep the latest token in a ref so the socket "open" handler reads the
  // current value without rebuilding connect() (which would drop the socket).
  const tokenRef = useRef(token);
  const shouldConnectRef = useRef(false);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const connectRef = useRef<((target: Target) => void) | null>(null);

  const pushEvent = useCallback(
    (partial: Omit<AgentEvent, "id" | "ts">) => {
      idRef.current += 1;
      const evt: AgentEvent = { ...partial, id: idRef.current, ts: Date.now() };
      setEvents((prev) => {
        const next = [...prev, evt];
        if (next.length > MAX_EVENTS) {
          next.splice(0, next.length - MAX_EVENTS);
        }
        return next;
      });
    },
    []
  );

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const handleMessage = useCallback(
    (raw: string) => {
      let data: unknown;
      try {
        data = JSON.parse(raw);
      } catch {
        pushEvent({ kind: "info", detail: raw });
        return;
      }
      if (typeof data !== "object" || data === null) {
        pushEvent({ kind: "info", detail: raw });
        return;
      }
      const msg = data as Record<string, unknown>;
      const type = typeof msg.type === "string" ? msg.type : "";
      if (type === "progress") {
        pushEvent({
          kind: "progress",
          step: typeof msg.step === "string" ? msg.step : undefined,
          status: typeof msg.status === "string" ? msg.status : undefined,
          detail: typeof msg.detail === "string" ? msg.detail : undefined,
        });
      } else if (type === "result") {
        pushEvent({
          kind: "result",
          success: typeof msg.success === "boolean" ? msg.success : undefined,
          detail: typeof msg.detail === "string" ? msg.detail : undefined,
          plan: parsePlan(msg.plan),
        });
      } else if (type === "plan") {
        // Dry-run preview response: a result-shaped message carrying the plan.
        pushEvent({
          kind: "result",
          detail:
            typeof msg.detail === "string" ? msg.detail : "Preview (dry run)",
          plan: parsePlan(msg.plan),
        });
      } else if (type === "error") {
        pushEvent({
          kind: "error",
          message:
            typeof msg.message === "string" ? msg.message : "Unknown error",
        });
      } else {
        pushEvent({ kind: "info", detail: raw });
      }
    },
    [pushEvent]
  );

  const connect = useCallback(
    (target: Target) => {
      clearReconnectTimer();
      targetRef.current = target;
      shouldConnectRef.current = true;

      // Drop any existing socket without letting its close trigger a reconnect.
      const existing = wsRef.current;
      if (existing) {
        try {
          existing.onclose = null;
          existing.onerror = null;
          existing.onmessage = null;
          existing.onopen = null;
          existing.close();
        } catch {
          // Ignore: closing an already dead socket is harmless.
        }
        wsRef.current = null;
      }

      let ws: WebSocket;
      try {
        ws = new WebSocket(wsUrl(target));
      } catch (e) {
        setConnectionState("error");
        pushEvent({ kind: "error", message: `Failed to connect: ${String(e)}` });
        return;
      }

      wsRef.current = ws;
      setConnectionState("connecting");

      ws.onopen = () => {
        if (wsRef.current !== ws) return;
        reconnectAttemptsRef.current = 0;
        setConnectionState("connected");
        // When auth is required the token must be the first message on the
        // wire, ahead of any queued command or preview.
        const authToken = tokenRef.current.trim();
        if (authToken !== "") {
          try {
            ws.send(JSON.stringify({ type: "auth", token: authToken }));
          } catch {
            // Ignore: a failed send surfaces via the close handler.
          }
        }
        const queued = pendingRef.current;
        pendingRef.current = [];
        for (const msg of queued) {
          try {
            ws.send(JSON.stringify(msg));
          } catch {
            // Ignore: a failed send surfaces via the close handler.
          }
        }
      };

      ws.onmessage = (ev: MessageEvent) => {
        if (wsRef.current !== ws) return;
        if (typeof ev.data === "string") {
          handleMessage(ev.data);
        }
      };

      ws.onerror = () => {
        // The socket error is reported through onclose, which drives state.
      };

      ws.onclose = () => {
        if (wsRef.current === ws) {
          wsRef.current = null;
        }
        if (!shouldConnectRef.current) {
          setConnectionState("disconnected");
          return;
        }
        if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttemptsRef.current += 1;
          setConnectionState("connecting");
          clearReconnectTimer();
          reconnectTimerRef.current = setTimeout(() => {
            const t = targetRef.current;
            if (t && shouldConnectRef.current && connectRef.current) {
              connectRef.current(t);
            }
          }, RECONNECT_DELAY_MS);
        } else {
          setConnectionState("error");
          pushEvent({
            kind: "error",
            message: "Connection lost. Reconnect attempts exhausted.",
          });
        }
      };
    },
    [clearReconnectTimer, handleMessage, pushEvent]
  );

  // Keep a stable ref to the latest connect so the reconnect timer can call it
  // without connect depending on itself.
  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  // Mirror the latest token into a ref so a reconnect's "open" handler always
  // authenticates with the current value. Ref-only, so it triggers no render.
  useEffect(() => {
    tokenRef.current = token;
  }, [token]);

  const sendCommand = useCallback(
    (command: string, host: string, port: string) => {
      const text = command.trim();
      if (text === "") return;
      const target = normalizeTarget(host, port);
      pushEvent({ kind: "info", detail: `> ${text}` });

      const ws = wsRef.current;
      const current = targetRef.current;
      const sameTarget =
        current !== null &&
        current.host === target.host &&
        current.port === target.port;

      if (ws && ws.readyState === WebSocket.OPEN && sameTarget) {
        try {
          ws.send(JSON.stringify({ type: "command", command: text }));
        } catch (e) {
          pushEvent({ kind: "error", message: `Send failed: ${String(e)}` });
        }
        return;
      }

      // Not connected (or the target changed): queue and open a socket.
      pendingRef.current.push({ type: "command", command: text });
      connect(target);
    },
    [connect, pushEvent]
  );

  // Preview a command without executing it. Mirrors sendCommand but emits a
  // "plan" message so the backend returns its dry-run plan instead of running.
  const sendPlan = useCallback(
    (command: string, host: string, port: string) => {
      const text = command.trim();
      if (text === "") return;
      const target = normalizeTarget(host, port);
      pushEvent({ kind: "info", detail: `> (preview) ${text}` });

      const ws = wsRef.current;
      const current = targetRef.current;
      const sameTarget =
        current !== null &&
        current.host === target.host &&
        current.port === target.port;

      if (ws && ws.readyState === WebSocket.OPEN && sameTarget) {
        try {
          ws.send(JSON.stringify({ type: "plan", command: text }));
        } catch (e) {
          pushEvent({ kind: "error", message: `Send failed: ${String(e)}` });
        }
        return;
      }

      // Not connected (or the target changed): queue and open a socket.
      pendingRef.current.push({ type: "plan", command: text });
      connect(target);
    },
    [connect, pushEvent]
  );

  const stop = useCallback(() => {
    pendingRef.current = [];
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify({ type: "stop" }));
        pushEvent({ kind: "info", detail: "Stop requested" });
      } catch (e) {
        pushEvent({ kind: "error", message: `Stop failed: ${String(e)}` });
      }
    } else {
      pushEvent({ kind: "info", detail: "Not connected" });
    }
  }, [pushEvent]);

  const disconnect = useCallback(() => {
    shouldConnectRef.current = false;
    clearReconnectTimer();
    pendingRef.current = [];
    const ws = wsRef.current;
    wsRef.current = null;
    if (ws) {
      try {
        ws.close();
      } catch {
        // Ignore: nothing to do if the socket is already gone.
      }
    }
    setConnectionState("disconnected");
  }, [clearReconnectTimer]);

  const checkHealth = useCallback((host: string, port: string) => {
    const target = normalizeTarget(host, port);
    setHealth("checking");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
    // no-cors lets us treat "the port answered" as reachable even when the
    // backend sends no CORS headers; a genuine network failure still rejects.
    fetch(healthUrl(target), { mode: "no-cors", signal: controller.signal })
      .then(() => {
        clearTimeout(timer);
        setHealth("reachable");
      })
      .catch(() => {
        clearTimeout(timer);
        setHealth("unreachable");
      });
  }, []);

  const clearEvents = useCallback(() => {
    setEvents([]);
  }, []);

  // Tear the socket down on unmount so a hidden window keeps no live connection.
  useEffect(() => {
    return () => {
      shouldConnectRef.current = false;
      if (reconnectTimerRef.current !== null) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      const ws = wsRef.current;
      wsRef.current = null;
      if (ws) {
        try {
          ws.close();
        } catch {
          // Ignore: cleanup should never throw.
        }
      }
    };
  }, []);

  return {
    connectionState,
    events,
    health,
    sendCommand,
    sendPlan,
    stop,
    checkHealth,
    disconnect,
    clearEvents,
  };
}
