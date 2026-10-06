
export const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // response body wasn't JSON — fall back to statusText
    }
    throw new ApiError(res.status, detail);
  }
  // 204 No Content (DELETE endpoints) has no body to parse.
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export async function streamSse(url: string, body: unknown, onChunk: (text: string) => void, signal?: AbortSignal): Promise<void> {
  const res = await fetch(`${API_BASE}${url}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // Keep the HTTP status text for non-JSON provider/proxy failures.
    }
    throw new ApiError(res.status, detail);
  }
  if (!res.body) {
    throw new ApiError(res.status, "The AI provider returned an empty stream.");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const eventLine = frame.split("\n").find((line) => line.startsWith("event: "));
      const dataLine = frame.split("\n").find((line) => line.startsWith("data: "));
      if (!dataLine) continue;
      const parsed = JSON.parse(dataLine.slice("data: ".length));
      if (eventLine === "event: error") {
        throw new ApiError(502, parsed.error || "The AI provider request failed.");
      }
      if (typeof parsed.text === "string") {
        onChunk(parsed.text);
      }
    }
  }
}

