import { useCallback, useEffect, useRef, useState } from "react";
import type { DeskEvent, DeskState, Integration } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep status text */
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const api = {
  state: () => request<DeskState>("/api/state"),
  history: () => request<DeskEvent[]>("/api/history"),
  runQueue: () => request("/api/run", { method: "POST" }),
  runTicket: (id: string) => request(`/api/tickets/${id}/run`, { method: "POST" }),
  addTicket: (sender: string, subject: string, body: string) =>
    request<{ id: string }>("/api/tickets", { method: "POST", body: JSON.stringify({ sender, subject, body }) }),
  integration: () => request<Integration>("/api/integration"),
  answer: (id: string, body: { outcome: string; scope: string; values: Record<string, number> }) =>
    request(`/api/decisions/${id}`, { method: "POST", body: JSON.stringify(body) }),
  drift: () => request("/api/drift", { method: "POST" }),
  reset: () => request("/api/reset", { method: "POST" }),
};

/** Desk state, refreshed whenever the server emits an event. */
export function useDesk() {
  const [state, setState] = useState<DeskState | null>(null);
  const [events, setEvents] = useState<DeskEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      setState(await api.state());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const scheduleRefresh = useCallback(() => {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(refresh, 150);
  }, [refresh]);

  useEffect(() => {
    refresh();
    api.history().then(setEvents).catch(() => undefined);
    const source = new EventSource("/api/events");
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.onmessage = (message) => {
      const event = JSON.parse(message.data) as DeskEvent;
      if (event.type === "desk.reset") setEvents([]);
      else setEvents((prev) => [...prev.slice(-400), event]);
      scheduleRefresh();
    };
    return () => source.close();
  }, [refresh, scheduleRefresh]);

  return { state, events, connected, error, refresh };
}
