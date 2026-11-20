let refreshPromise: Promise<boolean> | null = null;

async function refreshAccess(): Promise<boolean> {
  const token = localStorage.getItem('refresh_token');
  if (!token) return false;
  const response = await fetch('/api/v1/auth/refresh', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: token }),
  });
  if (!response.ok) return false;
  const tokens = await response.json();
  localStorage.setItem('access_token', tokens.access_token);
  localStorage.setItem('refresh_token', tokens.refresh_token);
  return true;
}

export async function authenticatedFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const send = () => {
    const headers = new Headers(options.headers);
    const token = typeof window === 'undefined' ? null : localStorage.getItem('access_token');
    if (token) headers.set('Authorization', `Bearer ${token}`);
    return fetch(url, { ...options, headers });
  };
  let response = await send();
  if (response.status === 401 && typeof window !== 'undefined' && !url.includes('/auth/')) {
    refreshPromise ??= refreshAccess().catch(() => false).finally(() => { refreshPromise = null; });
    if (await refreshPromise) response = await send();
    else {
      localStorage.removeItem('access_token'); localStorage.removeItem('refresh_token');
      window.location.assign('/login');
    }
  }
  return response;
}

export async function responseError(response: Response): Promise<string> {
  const body = await response.json().catch(() => ({}));
  if (Array.isArray(body.detail)) return body.detail.map((item: {msg: string}) => item.msg).join('; ');
  return typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`;
}

class ApiClient {
  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const response = await authenticatedFetch(path, { ...options,
      headers: { 'Content-Type': 'application/json', ...options.headers } });
    if (!response.ok) throw new Error(await responseError(response));
    if (response.status === 204) return undefined as T;
    return response.json();
  }
  get<T>(path: string): Promise<T> { return this.request<T>(path); }
  post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });
  }
  put<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, { method: 'PUT', body: body === undefined ? undefined : JSON.stringify(body) });
  }
  del(path: string): Promise<void> { return this.request<void>(path, { method: 'DELETE' }); }
}
export const api = new ApiClient();
