import { beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';
import { ApiError } from '$lib/api/errors';
import { catalogApi } from '$lib/api/palimpsestCatalog';
import { createPalimpsestCatalogController } from './palimpsestCatalogController.svelte';
import { beginExperienceAction, beginExperienceLoad, experienceApplied, experienceDiscarded, experienceState } from '$lib/utils/experience';
import type * as ExperienceModule from '$lib/utils/experience';

// vi.mock factories are hoisted above static imports, so svelte/store must be imported dynamically here.
vi.mock('$lib/stores/auth', async () => {
  const { writable } = await import('svelte/store');
  return {
    auth: writable({}),
    authReady: writable(true),
    projectSwitching: writable(false),
    logoutInProgress: writable(false),
  };
});
vi.mock('$lib/api/palimpsestCatalog', () => ({ catalogApi: { layers: vi.fn(), detail: vi.fn() } }));
vi.mock('$lib/utils/experience', async (original) => ({
  ...await original<typeof ExperienceModule>(),
  beginExperienceAction: vi.fn((...args: Parameters<typeof beginExperienceAction>) => Object.freeze({ feature: args[0], action: args[1], component: args[2] })),
  beginExperienceLoad: vi.fn((...args: Parameters<typeof beginExperienceLoad>) => Object.freeze({ feature: args[0], action: 'load', component: args[1] })),
  experienceApplied: vi.fn(),
  experienceDiscarded: vi.fn(),
  experienceState: vi.fn(),
}));

const admin = { token: 'private-token', userId: 'private-user', projectId: 'private-project', domainId: 'default', sessionId: 'private-session', isSystemAdmin: true };
const settle = async () => { for (let index = 0; index < 16; ++index) await Promise.resolve(); };
const failures = () => vi.mocked(experienceState).mock.calls.filter(([, state]) => state === 'error');
const guards = () => vi.mocked(experienceApplied).mock.calls.map(([, , owns]) => owns);

beforeEach(() => { vi.clearAllMocks(); auth.set(admin as never); });

describe('Palimpsest catalog failed reads', () => {
  it('applies a failed list read only while that list request still owns the view', async () => {
    vi.mocked(catalogApi.layers).mockRejectedValueOnce(new ApiError(503, 'private upstream body'));
    const catalog = createPalimpsestCatalogController();
    catalog.start(); await settle();
    expect(catalog.error).toBe('unavailable');
    expect(failures()).toHaveLength(1);
    const [owns] = guards();
    expect(owns?.()).toBe(true);
    catalog.dispose();
    expect(owns?.()).toBe(false);
    expect(experienceDiscarded).not.toHaveBeenCalled();
  });

  it('applies a malformed list response as the displayed invalid-response state', async () => {
    vi.mocked(catalogApi.layers).mockResolvedValueOnce({ source: 'managed', offset: 0, items: 'not-a-list', has_more: false, next_offset: null } as never);
    const catalog = createPalimpsestCatalogController();
    catalog.start(); await settle();
    expect(catalog.error).toBe('invalidResponse');
    expect(failures()).toHaveLength(1);
    expect(guards()).toHaveLength(1);
    expect(guards()[0]?.()).toBe(true);
    catalog.dispose();
  });

  it('applies a failed detail read and rejects the DOM commit after the detail is closed', async () => {
    vi.mocked(catalogApi.layers).mockResolvedValueOnce({ source: 'managed', offset: 0, items: [], has_more: false, next_offset: null } as never);
    vi.mocked(catalogApi.detail).mockRejectedValueOnce(new ApiError(404, 'private upstream body'));
    const catalog = createPalimpsestCatalogController();
    catalog.start(); await settle();
    vi.mocked(experienceApplied).mockClear(); vi.mocked(experienceState).mockClear();
    await catalog.openDetail('layer-a');
    expect(catalog.detailError).toBe('notFound');
    expect(failures()).toHaveLength(1);
    const [owns] = guards();
    expect(owns?.()).toBe(true);
    catalog.closeDetail();
    expect(owns?.()).toBe(false);
    catalog.dispose();
  });
});
