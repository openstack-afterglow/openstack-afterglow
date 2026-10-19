import { beforeEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token-a', projectId: 'project-a', userId: 'user-a', sessionId: 'session-a', domainId: 'domain-a', identityDomainId: 'home-a', isSystemAdmin: true }),
	authReady: writable(true), projectSwitching: writable(false), logoutInProgress: writable(false),
}));
import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
import { createTelemetryContext } from './context';

beforeEach(() => {
	auth.update(state => ({ ...state, token: 'token-a', projectId: 'project-a', userId: 'user-a', sessionId: 'session-a', domainId: 'domain-a', identityDomainId: 'home-a', isSystemAdmin: true }));
	authReady.set(true); projectSwitching.set(false); logoutInProgress.set(false);
});
describe('mounted native administration ownership', () => {
	it('invalidates synchronously through same-tick scope ABA without reviving a confirmation', () => {
		const changed = vi.fn(); const context = createTelemetryContext(changed);
		const pending = context.capture()!;
		auth.update(state => ({ ...state, projectId: 'project-b' }));
		expect(pending.current()).toBe(false);
		auth.update(state => ({ ...state, projectId: 'project-a' }));
		expect(pending.current()).toBe(false);
		expect(context.capture()!.current()).toBe(true);
		expect(changed).toHaveBeenCalledTimes(2);
		context.dispose();
	});
	it('permits native system scope without a project and fences its transition into project scope', () => {
		auth.update(state => ({ ...state, projectId: '' }));
		const context = createTelemetryContext(vi.fn());
		const system = context.capture()!;
		expect(system.authority.projectId).toBe('');
		auth.update(state => ({ ...state, projectId: 'project-b' }));
		expect(system.current()).toBe(false);
		expect(context.capture()!.authority.projectId).toBe('project-b');
		context.dispose();
	});
	it.each(['token', 'userId', 'sessionId', 'domainId', 'identityDomainId'] as const)('fences private snapshots on %s replacement', key => {
		const context = createTelemetryContext(vi.fn()); const pending = context.capture()!;
		auth.update(state => ({ ...state, [key]: 'changed' }));
		expect(pending.current()).toBe(false); context.dispose();
	});
	it('blocks reads and writes before rescope and during auth verification loss', () => {
		const context = createTelemetryContext(vi.fn());
		projectSwitching.set(true); expect(context.capture()).toBeNull();
		projectSwitching.set(false); authReady.set(false); expect(context.capture()).toBeNull();
		authReady.set(true); logoutInProgress.set(true); expect(context.capture()).toBeNull();
		logoutInProgress.set(false); auth.update(state => ({ ...state, isSystemAdmin: false })); expect(context.capture()).toBeNull();
		context.dispose();
	});
	it('does not publish after unmount and releases its subscriptions', () => {
		const changed = vi.fn(); const context = createTelemetryContext(changed); const pending = context.capture()!;
		context.dispose(); auth.update(state => ({ ...state, token: 'late' }));
		expect(context.capture()).toBeNull(); expect(pending.current()).toBe(false); expect(changed).not.toHaveBeenCalled();
	});
});
