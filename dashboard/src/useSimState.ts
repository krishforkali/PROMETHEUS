import { useEffect, useState } from "react";
import { wsUrl } from "./api";
import type { SimState } from "./types";

export type Connection = "connecting" | "open" | "reconnecting";

const MIN_RETRY_MS = 500;
const MAX_RETRY_MS = 5000;

/** Live simulation state over WebSocket, reconnecting with backoff. */
export function useSimState(): { state: SimState | null; connection: Connection } {
  const [state, setState] = useState<SimState | null>(null);
  const [connection, setConnection] = useState<Connection>("connecting");

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retryMs = MIN_RETRY_MS;
    let timer: number | undefined;
    let closed = false;

    const connect = () => {
      ws = new WebSocket(wsUrl());
      ws.onopen = () => {
        retryMs = MIN_RETRY_MS;
        setConnection("open");
      };
      ws.onmessage = (msg: MessageEvent<string>) => setState(JSON.parse(msg.data) as SimState);
      ws.onclose = () => {
        if (closed) return;
        setConnection("reconnecting");
        timer = window.setTimeout(connect, retryMs);
        retryMs = Math.min(retryMs * 2, MAX_RETRY_MS);
      };
      ws.onerror = () => ws?.close();
    };
    connect();

    return () => {
      closed = true;
      window.clearTimeout(timer);
      ws?.close();
    };
  }, []);

  return { state, connection };
}
