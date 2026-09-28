import { describe, expect, it } from 'vitest';
import { writable } from 'svelte/store';
import { createWaygateProjectScope, type WaygateProjectScope } from '../waygateProjectScope';

function setup(token: string | null = 'token-a', projectId: string | null = 'project-a') {
	const auth = writable({ token, projectId });
	const scopes: (WaygateProjectScope | null)[] = [];
	const unsubscribe = createWaygateProjectScope(auth).subscribe((scope) => scopes.push(scope));
	return { auth, scopes, unsubscribe };
}

describe('Waygate project workspace lifetime', () => {
	it('invalidates an old scope synchronously and never revives it on A → B → A', () => {
		const { auth, scopes, unsubscribe } = setup();
		try {
			const first = scopes.at(-1)!;
			auth.set({ token: 'token-b', projectId: 'project-b' });
			const second = scopes.at(-1)!;
			expect(first.isCurrent()).toBe(false);
			auth.set({ token: 'token-a', projectId: 'project-a' });
			const returned = scopes.at(-1)!;
			expect(second.isCurrent()).toBe(false);
			expect(first.isCurrent()).toBe(false);
			expect(returned).not.toBe(first);
			expect(returned.isCurrent()).toBe(true);
		} finally {
			unsubscribe();
		}
	});

	it.each([null, '', '   '])('does not allow a workspace without a project (%s)', (projectId) => {
		const { auth, scopes, unsubscribe } = setup('token-a', projectId);
		try {
			expect(scopes.at(-1)).toBeNull();
			auth.set({ token: 'token-a', projectId: 'project-a' });
			const current = scopes.at(-1)!;
			auth.set({ token: 'token-a', projectId });
			expect(scopes.at(-1)).toBeNull();
			expect(current.isCurrent()).toBe(false);
		} finally {
			unsubscribe();
		}
	});

	it('preserves the lifetime on unrelated auth updates but invalidates on token change and teardown', () => {
		const { auth, scopes, unsubscribe } = setup();
		const first = scopes.at(-1)!;
		auth.update((value) => ({ ...value }));
		expect(scopes.at(-1)).toBe(first);
		auth.update((value) => ({ ...value, token: 'token-new' }));
		const renewed = scopes.at(-1)!;
		expect(first.isCurrent()).toBe(false);
		expect(renewed.isCurrent()).toBe(true);
		unsubscribe();
		expect(renewed.isCurrent()).toBe(false);
	});

	it('removes the scope on logout even if the selected project remains', () => {
		const { auth, scopes, unsubscribe } = setup();
		try {
			const first = scopes.at(-1)!;
			auth.update((value) => ({ ...value, token: null }));
			expect(scopes.at(-1)).toBeNull();
			expect(first.isCurrent()).toBe(false);
		} finally {
			unsubscribe();
		}
	});
});
