import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/mcp-gallery';
import type { ManagedSandboxToolState } from '$lib/stores/managedSandboxTools';

const mocks = vi.hoisted(() => ({
	publish: (_value: ManagedSandboxToolState) => {},
	snapshot: (): ManagedSandboxToolState => undefined as unknown as ManagedSandboxToolState,
	set: vi.fn(), tool: vi.fn(), profile: vi.fn(), refresh: vi.fn()
}));
vi.mock('$lib/stores/managedSandboxTools', async () => {
	// Hoisted mock factories run before static bindings; load real store primitives inside this test boundary.
	const { get, writable } = await import('svelte/store');
	const value = writable<ManagedSandboxToolState>(undefined as unknown as ManagedSandboxToolState);
	mocks.publish = (next) => value.set(next);
	mocks.snapshot = () => get(value);
	return {
		managedSandboxTools: value,
		setManagedSandboxTools: mocks.set,
		toggleManagedSandboxTool: mocks.tool,
		toggleManagedSandboxProfile: mocks.profile,
		refreshManagedSandboxTools: mocks.refresh,
		managedSandboxIssueMessage: (code: string, names: readonly string[] = []) => `${code}: ${names.join(', ')}`
	};
});
import ManagedSandboxToolsPicker from '../ManagedSandboxToolsPicker.svelte';

function state(overrides: Partial<ManagedSandboxToolState> = {}): ManagedSandboxToolState {
	return {
		ownerKey: 'owner-a', selected: [], loading: false, preparing: false, catalogLoaded: true,
		catalogError: false, unavailable: [], issue: null, canSelect: true, storageFailed: false,
		profiles: [{ id: 'playwright', name: 'Playwright', available: true, reason: null, tools: ['browser_navigate', 'browser_snapshot'] }],
		...overrides
	};
}
function select(names: string[]) {
	mocks.publish({ ...mocks.snapshot(), selected: names, issue: null, unavailable: [] });
	return true;
}

beforeEach(() => {
	initLocale('ko');
	vi.clearAllMocks();
	mocks.publish(state());
	mocks.set.mockImplementation(select);
	mocks.tool.mockImplementation((name: string, selected: boolean) => select(selected
		? [...new Set([...mocks.snapshot().selected, name])]
		: mocks.snapshot().selected.filter((current) => current !== name)));
	mocks.profile.mockImplementation((id: string, selected: boolean) => {
		const names = mocks.snapshot().profiles.find((profile) => profile.id === id)!.tools;
		return select(selected ? [...new Set([...mocks.snapshot().selected, ...names])]
			: mocks.snapshot().selected.filter((name) => !names.includes(name)));
	});
	mocks.refresh.mockResolvedValue(undefined);
});
afterEach(cleanup);

describe('explicit managed sandbox selection', () => {
	it('starts unselected and selects a profile only after the user checks it', async () => {
		render(ManagedSandboxToolsPicker, { profileId: 'playwright' });
		const profile = screen.getByRole('checkbox', { name: t('selectionProfile', { name: 'Playwright' }) });
		expect((profile as HTMLInputElement).checked).toBe(false);
		expect(mocks.profile).not.toHaveBeenCalled();
		expect(mocks.tool).not.toHaveBeenCalled();
		await fireEvent.click(profile);
		expect(mocks.profile).toHaveBeenCalledWith('playwright', true);
		await waitFor(() => expect((profile as HTMLInputElement).checked).toBe(true));
		expect(mocks.snapshot().selected).toEqual(['browser_navigate', 'browser_snapshot']);
		await fireEvent.click(profile);
		expect(mocks.snapshot().selected).toEqual([]);
	});

	it('retains exact individual names instead of sending a profile or remote server ID', async () => {
		mocks.publish(state({ profiles: [{ id: 'playwright', name: 'Playwright', available: true, reason: null, tools: ['BrowserRead', 'browser_snapshot'] }] }));
		render(ManagedSandboxToolsPicker, { profileId: 'playwright' });
		await fireEvent.click(screen.getByText(t('selectionToolsCount', { selected: 0, count: 2 })));
		await fireEvent.click(screen.getByRole('checkbox', { name: 'BrowserRead' }));
		expect(mocks.tool).toHaveBeenCalledWith('BrowserRead', true);
		expect(mocks.snapshot().selected).toEqual(['BrowserRead']);
	});

	it('keeps unavailable selected names visible and removable while refusing new additions', async () => {
		mocks.publish(state({ selected: ['browser_navigate'], canSelect: false, issue: 'unavailable', unavailable: ['browser_navigate'],
			profiles: [{ id: 'playwright', name: 'Playwright', available: false, reason: 'execution_protocol_v2_unavailable', tools: ['browser_navigate', 'browser_snapshot'] }] }));
		render(ManagedSandboxToolsPicker, { menu: true });
		expect(screen.getByRole('status').textContent).toContain('unavailable: browser_navigate');
		const chosen = screen.getByRole('menuitemcheckbox', { name: 'browser_navigate' });
		expect(chosen.getAttribute('aria-checked')).toBe('true');
		expect((chosen as HTMLButtonElement).disabled).toBe(false);
		expect((screen.getByRole('menuitemcheckbox', { name: 'browser_snapshot' }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.click(chosen);
		expect(mocks.tool).toHaveBeenCalledWith('browser_navigate', false);
		expect(mocks.snapshot().selected).toEqual([]);
	});

	it('offers menu-compatible profile and tool controls without remote connection actions', async () => {
		render(ManagedSandboxToolsPicker, { menu: true });
		expect(screen.getAllByRole('menuitemcheckbox')).toHaveLength(3);
		await fireEvent.click(screen.getByRole('menuitemcheckbox', { name: t('selectionProfile', { name: 'Playwright' }) }));
		expect(mocks.snapshot().selected).toEqual(['browser_navigate', 'browser_snapshot']);
		await fireEvent.click(screen.getByRole('menuitem', { name: t('selectionClear') }));
		expect(mocks.set).toHaveBeenCalledWith([]);
		expect(screen.queryByText(t('connectPersonal'))).toBeNull();
	});

	it('does not infer availability from the profile being present', () => {
		mocks.publish(state({ profiles: [{ id: 'playwright', name: 'Playwright', available: null, reason: null, tools: ['browser_navigate'] }] }));
		render(ManagedSandboxToolsPicker, { profileId: 'playwright' });
		expect((screen.getByRole('checkbox', { name: t('selectionProfile', { name: 'Playwright' }) }) as HTMLInputElement).disabled).toBe(true);
		expect(screen.getByText(t('managedUnknown'))).toBeTruthy();
		expect(mocks.profile).not.toHaveBeenCalled();
	});

	it.each(['invalid_saved', 'too_many'] as const)('requires an explicit reset of %s saved selection, even when no names could be read', async (issue) => {
		mocks.publish(state({ selected: [], issue }));
		render(ManagedSandboxToolsPicker, { summaryOnly: true });
		expect(screen.queryByText(t('selectionNone'))).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: t('selectionClear') }));
		expect(mocks.set).toHaveBeenCalledWith([]);
		await screen.findByText(t('selectionNone'));
	});

	it('clears prior owner action errors instead of displaying them to a new owner', async () => {
		mocks.profile.mockReturnValue(false);
		render(ManagedSandboxToolsPicker, { profileId: 'playwright' });
		await fireEvent.click(screen.getByRole('checkbox', { name: t('selectionProfile', { name: 'Playwright' }) }));
		await screen.findByText(t('selectionChangeFailed'));
		mocks.publish(state({ ownerKey: 'owner-b' }));
		await waitFor(() => expect(screen.queryByText(t('selectionChangeFailed'))).toBeNull());
	});

	it('reports optional preference-storage failure without claiming the choice was persisted', () => {
		mocks.publish(state({ storageFailed: true }));
		render(ManagedSandboxToolsPicker, { summaryOnly: true });
		expect(screen.getByText(t('selectionStorageFailed'))).toBeTruthy();
	});
});
