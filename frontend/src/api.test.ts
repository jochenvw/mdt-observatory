import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, request, requestEmpty } from './api';

afterEach(() => vi.unstubAllGlobals());
describe('API transport', () => {
  it('sends JSON mutation bodies with the session cookie', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'meeting' })));
    vi.stubGlobal('fetch', fetchMock);
    expect(await request('/meetings', { mode: 'rehearsal' })).toEqual({ id: 'meeting' });
    expect(fetchMock).toHaveBeenCalledWith('/api/meetings', expect.objectContaining({
      method: 'POST', credentials: 'same-origin', body: '{"mode":"rehearsal"}',
    }));
  });
  it('accepts auth success with no JSON body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(requestEmpty('/auth', { token: 'fixture-token' })).resolves.toBeUndefined();
  });
  it('preserves status and API validation detail', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Presenter access required' }), { status: 401 })));
    await expect(request('/meeting')).rejects.toMatchObject({ status: 401, message: 'Presenter access required' });
  });
  it('surfaces non-JSON gateway failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('Bad gateway', { status: 502 })));
    await expect(request('/meeting')).rejects.toBeInstanceOf(ApiError);
  });
});
