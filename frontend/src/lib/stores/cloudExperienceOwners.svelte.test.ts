import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ExperienceContext } from '$lib/utils/experience';
import type { ImageInfo } from '$lib/types/compute';
import type { LoadBalancerDetail } from '$lib/types/loadbalancer';
import { createImagesController } from './imagesController.svelte';
import { createNetworkLoadbalancerDetailController } from './networkLoadbalancerDetailController.svelte';

const replay = vi.hoisted(() => ({ begin: vi.fn(), load: vi.fn(), state: vi.fn(), applied: vi.fn(), discarded: vi.fn() }));
const transport = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), scoped: vi.fn() }));
vi.mock('$lib/utils/experience', () => ({
  beginExperienceAction: replay.begin,
  beginExperienceLoad: replay.load,
  experienceState: replay.state,
  experienceApplied: replay.applied,
  experienceDiscarded: replay.discarded,
}));
vi.mock('$lib/api/client', () => ({
  ApiError: class extends Error {},
  api: { get: transport.get, post: transport.post, delete: transport.delete, withExperience: transport.scoped },
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn().mockResolvedValue(true) }));
vi.mock('$lib/stores/toast', () => ({ toast: { error: vi.fn() } }));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));

function context(sequence: number, withActionId = true): ExperienceContext {
  return {
    segmentId: '00000000-0000-4000-8000-000000000001', pageViewId: '00000000-0000-4000-8000-000000000002',
    ...(withActionId ? { actionId: `00000000-0000-4000-8000-${String(sequence).padStart(12, '0')}` } : {}),
    traceId: '00000000-0000-4000-8000-000000000003', spanId: '00000000-0000-4000-8000-000000000004',
    feature: 'compute', action: 'load', component: 'resource.list', route: '/dashboard/compute/images',
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  let sequence = 0;
  replay.begin.mockImplementation((feature, action, component) => ({ ...context(++sequence), feature, action, component }));
  replay.load.mockImplementation((feature, component) => ({ ...context(++sequence, false), feature, component }));
  replay.applied.mockResolvedValue(undefined);
  transport.scoped.mockReturnValue({ get: transport.get, post: transport.post, delete: transport.delete });
});

describe('source-owned cloud experience results', () => {
  it('keeps background loads passive and threads a named manual refresh context through the same read owner', async () => {
    transport.get.mockResolvedValue([]);
    const controller = createImagesController({ token: () => 'token', projectId: () => 'project' });
    await controller.fetchImages();
    expect(replay.load).toHaveBeenCalledWith('compute', 'resource.list');
    expect(replay.begin).not.toHaveBeenCalled();
    expect(transport.scoped.mock.calls[0][0].actionId).toBeUndefined();
    await controller.forceRefresh();
    expect(replay.begin).toHaveBeenCalledWith('compute', 'refresh', 'resource.list');
    expect(replay.load).toHaveBeenCalledTimes(1);
    expect(transport.scoped.mock.calls[1][0].actionId).toBeDefined();
    expect(replay.applied.mock.calls[1][0]).toBe(transport.scoped.mock.calls[1][0]);
  });

  it('keeps listener creation acceptance and its actual readback applied without claiming availability', async () => {
    transport.post.mockResolvedValue({});
    transport.get.mockImplementation(async (path: string) => path.endsWith('/listeners') || path.endsWith('/pools')
      ? [] : { id: 'lb-canary', status: 'ACTIVE', name: 'native-name-canary' });
    const controller = createNetworkLoadbalancerDetailController({ lbId: () => 'lb-canary', token: () => 'token-canary', projectId: () => 'project-canary' });
    expect(await controller.createListener({ protocol: 'HTTP', protocol_port: 80, name: 'input-name-canary' })).toBe(true);
    const captured = transport.scoped.mock.calls[0][0];
    expect(captured.action).toBe('create');
    expect(transport.scoped.mock.calls.every(call => call[0] === captured)).toBe(true);
    expect(replay.applied).toHaveBeenCalledWith(captured);
    expect(replay.state).not.toHaveBeenCalledWith(captured, 'ready');
    expect(replay.state).not.toHaveBeenCalledWith(captured, 'empty');
    expect(JSON.stringify([...replay.state.mock.calls, ...replay.applied.mock.calls])).not.toContain('canary');
  });

  it('reports only the actual guarded image assignment and discards the superseded read without resetting its owner', async () => {
    const older = Promise.withResolvers<ImageInfo[]>();
    const newer = Promise.withResolvers<ImageInfo[]>();
    transport.get.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);
    const controller = createImagesController({ token: () => 'credential-canary', projectId: () => 'project-canary' });
    const oldRead = controller.fetchImages();
    const oldContext = transport.scoped.mock.calls[0][0];
    const options = { refresh: true };
    const newRead = controller.fetchImages(options);
    const newContext = transport.scoped.mock.calls[1][0];
    newer.resolve([{ id: 'resource-canary', name: 'image-name-canary', status: 'active' }]);
    await newRead;
    expect(controller.images[0].id).toBe('resource-canary');
    expect(controller.loading).toBe(false);
    expect(transport.get.mock.calls[1][3]).toBe(options);
    older.resolve([]);
    await oldRead;
    expect(controller.images).toHaveLength(1);
    expect(replay.applied.mock.calls.map(call => call[0])).toEqual([newContext]);
    expect(replay.discarded).toHaveBeenCalledWith(oldContext, 'stale');
    expect(replay.state).not.toHaveBeenCalledWith(oldContext, 'empty');
    expect(replay.state).toHaveBeenCalledWith(newContext, 'ready');
    expect(JSON.stringify([...replay.state.mock.calls, ...replay.applied.mock.calls, ...replay.discarded.mock.calls])).not.toContain('canary');
  });

  it('records a late real load-balancer assignment as applied rather than inventing a product discard', async () => {
    const older = Promise.withResolvers<LoadBalancerDetail>();
    const newer = Promise.withResolvers<LoadBalancerDetail>();
    let reads = 0;
    transport.get.mockImplementation((path: string) => path.endsWith('/listeners') || path.endsWith('/pools')
      ? Promise.resolve([]) : ++reads === 1 ? older.promise : newer.promise);
    const controller = createNetworkLoadbalancerDetailController({ lbId: () => 'lb-canary', token: () => 'token-canary', projectId: () => 'project-canary' });
    const oldRead = controller.fetchAll();
    const oldContext = transport.scoped.mock.calls[0][0];
    const newRead = controller.fetchAll(true);
    const newContext = transport.scoped.mock.calls[3][0];
    const value = (name: string) => ({ id: 'lb-canary', name, status: 'ACTIVE' }) as LoadBalancerDetail;
    newer.resolve(value('new-name-canary'));
    await newRead;
    expect(controller.lb?.name).toBe('new-name-canary');
    older.resolve(value('old-name-canary'));
    await oldRead;
    // This controller has no product request-generation fence. Do not disguise its actual write.
    expect(controller.lb?.name).toBe('old-name-canary');
    expect(replay.applied.mock.calls.map(call => call[0])).toEqual([newContext, oldContext]);
    expect(replay.applied.mock.calls.every(call => call.length === 1)).toBe(true);
    expect(replay.discarded).not.toHaveBeenCalled();
    expect(JSON.stringify([...replay.state.mock.calls, ...replay.applied.mock.calls])).not.toContain('canary');
  });

  it('keeps the captured image scope out of error/readiness when the project changes during a request', async () => {
    const pending = Promise.withResolvers<ImageInfo[]>();
    let project = 'first-project-canary';
    transport.get.mockReturnValue(pending.promise);
    const controller = createImagesController({ token: () => 'token-canary', projectId: () => project });
    const read = controller.fetchImages();
    const captured = transport.scoped.mock.calls[0][0];
    project = 'second-project-canary';
    pending.reject(new Error('native-body-canary'));
    await read;
    expect(controller.error).toBe('');
    expect(replay.discarded).toHaveBeenCalledWith(captured, 'stale');
    expect(replay.applied).not.toHaveBeenCalled();
    expect(replay.state).not.toHaveBeenCalledWith(captured, 'error');
    expect(JSON.stringify(replay.state.mock.calls)).not.toContain('canary');
  });
  it('settles a failed listener mutation at the actual error toast without leaking native text', async () => {
    transport.post.mockRejectedValue(new Error('native-secret-canary'));
    const controller = createNetworkLoadbalancerDetailController({ lbId: () => 'resource-canary', token: () => 'credential-canary', projectId: () => 'project-canary' });
    expect(await controller.createListener({ protocol: 'HTTP', protocol_port: 80, name: 'input-canary' })).toBe(false);
    const captured = transport.scoped.mock.calls[0][0];
    expect(replay.state).toHaveBeenCalledWith(captured, 'error');
    expect(replay.applied).toHaveBeenCalledWith(captured);
    expect(transport.get).not.toHaveBeenCalled();
    expect(JSON.stringify([...replay.state.mock.calls, ...replay.applied.mock.calls])).not.toContain('canary');
  });

  it('retains a partial bulk mutation error before its independent successful list readback', async () => {
    transport.post.mockRejectedValue(new Error('native-error-canary'));
    transport.get.mockResolvedValue([]);
    const controller = createImagesController({ token: () => 'token-canary', projectId: () => 'project-canary' });
    const results = await controller.executeBulkAction('activate', ['resource-canary']);
    expect(results).toMatchObject([{ id: 'resource-canary', ok: false }]);
    const states = replay.state.mock.calls.map(call => call[1]);
    expect(states).toContain('error');
    expect(states.indexOf('error')).toBeLessThan(states.indexOf('empty'));
    expect(JSON.stringify(replay.state.mock.calls)).not.toContain('canary');
  });

});
