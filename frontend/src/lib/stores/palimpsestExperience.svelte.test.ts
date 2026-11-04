import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { hubApi, HubMe, HubLayerDetail } from '$lib/api/palimpsestHub';
import type { assetApi } from '$lib/api/palimpsestAssets';
import type { packageApi, PackageIdentity } from '$lib/api/palimpsestPackages';
import { createPalimpsestAssetsController } from './palimpsestAssetsController.svelte';
import { createPalimpsestHubController } from './palimpsestHubController.svelte';
import { createPalimpsestPackagesController } from './palimpsestPackagesController.svelte';
import { beginExperienceAction, beginExperienceLoad, experienceApplied, experienceDiscarded, experienceState } from '$lib/utils/experience';
import type * as ExperienceModule from '$lib/utils/experience';

vi.mock('$lib/utils/experience', async (original) => ({
  ...await original<typeof ExperienceModule>(),
  beginExperienceAction: vi.fn((...args: Parameters<typeof beginExperienceAction>) => Object.freeze({ feature: args[0], action: args[1], component: args[2] })),
  beginExperienceLoad: vi.fn((...args: Parameters<typeof beginExperienceLoad>) => Object.freeze({ feature: args[0], action: 'load', component: args[1] })),
  experienceApplied: vi.fn(),
  experienceDiscarded: vi.fn(),
  experienceState: vi.fn(),
}));

const actor: PackageIdentity = { token: 'private-token', projectId: 'private-project', userId: 'private-user' };
const digest = `sha256:${'a'.repeat(64)}`;
const verified: HubMe = {
  user_id: actor.userId, project_id: actor.projectId, project_name: 'private-project-name',
  is_system_admin: false, roles: [],
  capabilities: { inventory: true, download: true, upload: false, delete: false, build: true },
};
async function settle() { for (let index = 0; index < 16; ++index) await Promise.resolve(); }
function setup() {
  const api: typeof hubApi = {
    me: vi.fn(async () => verified), layers: vi.fn(async () => []),
    builds: vi.fn(async () => []), exports: vi.fn(async () => []),
    detail: vi.fn(), ancestors: vi.fn(async () => []), download: vi.fn(),
  };
  const controller = createPalimpsestHubController(() => actor, api, () => true, () => true);
  return { api, controller };
}
beforeEach(() => vi.clearAllMocks());

describe('Palimpsest source-owned experience observations', () => {
  it('records applied only after guarded state assignment', async () => {
    const { api, controller } = setup();
    const pending = Promise.withResolvers<HubMe>();
    vi.mocked(api.me).mockReturnValueOnce(pending.promise);
    controller.bindIdentity();
    expect(experienceApplied).not.toHaveBeenCalled();
    const context = vi.mocked(beginExperienceLoad).mock.results[0].value;
    pending.resolve(verified); await settle();
    expect(controller.me).toEqual(verified);
    expect(experienceApplied).toHaveBeenCalledWith(context, {}, expect.any(Function));
    expect(experienceState).toHaveBeenCalledWith(context, 'ready', 0);
    expect(experienceState).toHaveBeenCalledWith(expect.anything(), 'empty', 4);
    controller.dispose();
  });

  it('drops a closed detail result rather than claiming a state application', async () => {
    const { api, controller } = setup(); controller.bindIdentity(); await settle();
    vi.mocked(experienceApplied).mockClear();
    const pending = Promise.withResolvers<HubLayerDetail>();
    vi.mocked(api.detail).mockReturnValueOnce(pending.promise);
    const loading = controller.openDetail(digest);
    const context = vi.mocked(api.detail).mock.calls[0][0].experience;
    controller.closeDetail();
    pending.resolve({ blob_digest: digest } as HubLayerDetail); await loading;
    expect(controller.detail).toBeNull();
    expect(experienceApplied).not.toHaveBeenCalled();
    expect(experienceDiscarded).toHaveBeenCalledWith(context, 'aborted');
    controller.dispose();
  });

  it('keeps an applied result observable but rejects its DOM commit after the source owner closes', async () => {
    const { api, controller } = setup(); controller.bindIdentity(); await settle();
    vi.mocked(api.detail).mockResolvedValue({ blob_digest: digest, ancestors: [] } as unknown as HubLayerDetail);
    vi.mocked(experienceApplied).mockClear();
    await controller.openDetail(digest);
    const observation = vi.mocked(experienceApplied).mock.calls[0];
    expect(observation[2]?.()).toBe(true);
    controller.closeDetail();
    expect(observation[2]?.()).toBe(false);
    controller.dispose();
  });
});

describe('Palimpsest failed reads reach the same applied boundary as loaded reads', () => {
  const upstream = new Error('private upstream failure');
  const observedFailures = () => vi.mocked(experienceState).mock.calls.filter(([, state]) => state === 'error');
  const guards = () => vi.mocked(experienceApplied).mock.calls.map(([, , owns]) => owns);

  it('hub: applies the failed lane only while that failure is still displayed', async () => {
    const { api, controller } = setup();
    vi.mocked(api.me).mockRejectedValueOnce(upstream);
    controller.bindIdentity(); await settle();
    expect(controller.errors.me).toBeTruthy();
    expect(observedFailures()).toHaveLength(1);
    const [owns] = guards();
    expect(owns?.()).toBe(true);
    controller.dispose();
    expect(owns?.()).toBe(false);
  });

  it('assets: every failed source lane is applied with its ownership fence', async () => {
    const reject = vi.fn(async () => { throw upstream; });
    const api = { hub: reject, environments: reject, context: reject } as unknown as typeof assetApi;
    const controller = createPalimpsestAssetsController(() => ({ ...actor, sessionId: 'private-session' }), () => true, () => true, () => true, api);
    controller.bind(); await settle();
    expect(Object.keys(controller.errors).sort()).toEqual(['environments', 'hub', 'packages']);
    expect(observedFailures()).toHaveLength(3);
    const fences = guards();
    expect(fences).toHaveLength(3);
    expect(fences.every((owns) => owns?.() === true)).toBe(true);
    controller.dispose();
    expect(fences.every((owns) => owns?.() === false)).toBe(true);
  });

  it('packages: a failed context read is applied until the owner is disposed', async () => {
    const api = { context: vi.fn(async () => { throw upstream; }) } as unknown as typeof packageApi;
    const controller = createPalimpsestPackagesController(() => actor, api, () => true, () => false);
    controller.bindIdentity(); await settle();
    expect(controller.errors.context).toBeTruthy();
    expect(observedFailures()).toHaveLength(1);
    const [owns] = guards();
    expect(owns?.()).toBe(true);
    controller.dispose();
    expect(owns?.()).toBe(false);
  });
});
