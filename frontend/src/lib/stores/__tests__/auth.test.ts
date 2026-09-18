import { describe, it, expect, beforeEach, vi } from 'vitest';
import { get } from 'svelte/store';
import type { Writable } from 'svelte/store';
import type { AuthState } from '../auth';

// localStorage mock
const storage: Record<string, string> = {};
vi.stubGlobal('localStorage', {
  getItem: (key: string) => storage[key] ?? null,
  setItem: (key: string, val: string) => { storage[key] = val; },
  removeItem: (key: string) => { delete storage[key]; },
});
vi.stubGlobal('window', { localStorage: globalThis.localStorage });

describe('auth store', () => {
  let auth: Writable<AuthState>;
  let setAuth: typeof import('../auth')['setAuth'];
  let clearAuth: typeof import('../auth')['clearAuth'];
  let isAdmin: typeof import('../auth')['isAdmin'];
  let isReader: typeof import('../auth')['isReader'];
  let canWrite: typeof import('../auth')['canWrite'];

  beforeEach(async () => {
    vi.resetModules();
    const mod = await import('../auth');
    auth = mod.auth as typeof auth;
    setAuth = mod.setAuth;
    clearAuth = mod.clearAuth;
    isAdmin = mod.isAdmin;
    isReader = mod.isReader;
    canWrite = mod.canWrite;
    clearAuth();
  });

  it('초기 상태는 로그인되지 않음', () => {
    const state = get(auth);
    expect(state.token).toBeNull();
    expect(state.roles).toEqual([]);
  });

  it('setAuth 후 token과 roles가 저장됨', () => {
    setAuth({
      token: 'my-token',
      userId: 'user-1',
      username: 'testuser',
      projectId: 'proj-1',
      projectName: 'Test Project',
      accessExpiresAt: null,
      roles: ['member', 'admin'],
    });
    const state = get(auth);
    expect(state.token).toBe('my-token');
    expect(state.roles).toContain('admin');
  });

  it('isAdmin은 isSystemAdmin이 true일 때 true', () => {
    setAuth({ token: 'tok', userId: 'u', username: 'u', projectId: 'p', projectName: 'p', accessExpiresAt: null, roles: ['admin'], isSystemAdmin: true });
    expect(get(isAdmin)).toBe(true);
  });

  it('isAdmin은 isSystemAdmin이 false일 때 false', () => {
    setAuth({ token: 'tok', userId: 'u', username: 'u', projectId: 'p', projectName: 'p', accessExpiresAt: null, roles: ['admin'], isSystemAdmin: false });
    expect(get(isAdmin)).toBe(false);
  });
  it('isReader와 canWrite는 roles에 따라 정확히 계산됨', () => {
    // 1. reader 단독
    setAuth({ token: 'tok', userId: 'u', username: 'u', projectId: 'p', projectName: 'p', accessExpiresAt: null, roles: ['reader'], isSystemAdmin: false });
    expect(get(isReader)).toBe(true);
    expect(get(canWrite)).toBe(false);

    // 2. member 포함
    setAuth({ token: 'tok', userId: 'u', username: 'u', projectId: 'p', projectName: 'p', accessExpiresAt: null, roles: ['member'], isSystemAdmin: false });
    expect(get(isReader)).toBe(false);
    expect(get(canWrite)).toBe(true);

    // 3. reader + member 복합
    setAuth({ token: 'tok', userId: 'u', username: 'u', projectId: 'p', projectName: 'p', accessExpiresAt: null, roles: ['reader', 'member'], isSystemAdmin: false });
    expect(get(isReader)).toBe(false);
    expect(get(canWrite)).toBe(true);

    // 4. system admin은 reader role이 있어도 canWrite=true, isReader=false
    setAuth({ token: 'tok', userId: 'u', username: 'u', projectId: 'p', projectName: 'p', accessExpiresAt: null, roles: ['reader'], isSystemAdmin: true });
    expect(get(isReader)).toBe(false);
    expect(get(canWrite)).toBe(true);
  });


  it('clearAuth 후 초기 상태로 복원', () => {
    setAuth({ token: 'tok', userId: 'u', username: 'u', projectId: 'p', projectName: 'p', accessExpiresAt: null, roles: ['admin'] });
    clearAuth();
    const state = get(auth);
    expect(state.token).toBeNull();
    expect(state.roles).toEqual([]);
  });
});
