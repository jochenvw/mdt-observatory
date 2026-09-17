import { errorMessage } from './helpers';

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}
async function send(path: string, body?: unknown, signal?: AbortSignal): Promise<Response> {
  const response = await fetch(`/api${path}`, {
    credentials: 'same-origin',
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    const raw = await response.text();
    let payload: unknown;
    try { payload = JSON.parse(raw); } catch { payload = null; }
    throw new ApiError(errorMessage(payload, response.status), response.status);
  }
  return response;
}
export async function request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  return (await send(path, body, signal)).json() as Promise<T>;
}
export async function requestEmpty(path: string, body: unknown): Promise<void> {
  await send(path, body);
}
