import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen, fireEvent, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { fromStore, writable } from 'svelte/store';
import type { Writable } from 'svelte/store';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/instance';
import type { Instance } from '$lib/types/compute';
import type { InstanceDetailController } from '$lib/stores/instanceDetailController.svelte';

const mocks = vi.hoisted(() => ({
	controller: undefined as unknown,
	viewport: { mobile: true },
	openConsole: vi.fn(),
	openRename: vi.fn(),
	performAction: vi.fn(),
	deleteInstance: vi.fn(),
	confirmResize: vi.fn(),
	revertResize: vi.fn(),
}));

vi.mock('$lib/stores/instanceDetailController.svelte', () => ({
	useInstanceDetailController: () => mocks.controller,
}));
vi.mock('$lib/utils/mobileViewport', () => ({
	mobileViewport: { get current() { return mocks.viewport.mobile; } },
}));

import InstanceHeader from '../InstanceHeader.svelte';

const activeInstance = { id: 'inst-1', name: 'vm-1', status: 'ACTIVE' } as Instance;
let controllerState: Writable<InstanceDetailController>;

function renderHeader(
	overrides: Partial<InstanceDetailController> = {},
	props: { adminProjectId?: string | null; canMutate?: boolean; onOpenResizeModal?: () => void; onOpenEvacuateModal?: () => void } = {},
) {
	controllerState = writable({
		instance: activeInstance,
		actioning: null,
		deleting: false,
		resizeLoading: false,
		renameLoading: false,
		canRename: true,
		waygateLocked: false,
		consoleOpening: false,
		consoleOpenMessage: '',
		consoleOpenError: '',
		migrationStatus: null,
		canChangePassword: false,
		passwordPrecheckLoading: false,
		passwordPrecheck: null,
		passwordPrecheckReason: null,
		passwordPrecheckError: '',
		openConsole: mocks.openConsole,
		openRename: mocks.openRename,
		performAction: mocks.performAction,
		deleteInstance: mocks.deleteInstance,
		confirmResize: mocks.confirmResize,
		revertResize: mocks.revertResize,
		...overrides,
	} as unknown as InstanceDetailController);
	const state = fromStore(controllerState);
	mocks.controller = new Proxy(state.current, {
		get: (_target, key) => state.current[key as keyof InstanceDetailController],
	});
	return render(InstanceHeader, {
		adminProjectId: props.adminProjectId ?? null,
		canMutate: props.canMutate ?? true,
		onOpenMigrateModal: vi.fn(),
		onOpenPasswordModal: vi.fn(),
		onOpenResizeModal: props.onOpenResizeModal ?? vi.fn(),
		onOpenEvacuateModal: props.onOpenEvacuateModal ?? vi.fn(),
	});
}

function primaryRow() {
	return screen.getByTestId('instance-mobile-primary-actions');
}
function buttonNames(container: HTMLElement) {
	return within(container).queryAllByRole('button').map((button) => button.textContent?.trim());
}
async function openOverflow() {
	await fireEvent.click(screen.getByRole('button', { name: t('rowActions.instanceActions', { name: 'vm-1' }) }));
	return screen.getByRole('group', { name: (name) => name.includes(t('rowActions.instanceActions', { name: 'vm-1' })) });
}

beforeEach(() => {
	vi.clearAllMocks();
	mocks.viewport.mobile = true;
	initLocale('ko');
});
afterEach(() => cleanup());

describe('InstanceHeader mobile layout', () => {
	it('puts the name and status first and keeps only Stop and Reboot inline for a running VM', async () => {
		const onOpenResizeModal = vi.fn();
		renderHeader({}, { onOpenResizeModal });
		const header = screen.getByTestId('instance-mobile-header');
		const heading = within(header).getByRole('heading', { name: 'vm-1' });
		const nameRow = heading.parentElement!;
		expect(nameRow.textContent).toContain('vm-1');
		// The name row holds only the name and pill; the overflow trigger sits in the primary-actions row.
		expect(within(nameRow).queryAllByRole('button')).toHaveLength(0);
		expect(primaryRow().parentElement!.contains(screen.getByRole('button', { name: t('rowActions.instanceActions', { name: 'vm-1' }) }))).toBe(true);
		expect(buttonNames(primaryRow())).toEqual([t('header.stop'), t('header.reboot')]);
		for (const name of [t('rename.title'), t('header.openConsole'), t('header.resize')]) {
			expect(screen.queryByRole('button', { name })).toBeNull();
		}

		await fireEvent.click(within(primaryRow()).getByRole('button', { name: t('header.stop') }));
		expect(mocks.performAction).toHaveBeenCalledWith('stop');

		const menu = await openOverflow();
		expect(buttonNames(menu)).toEqual([t('rename.title'), t('header.openConsole'), t('header.resize')]);
		await fireEvent.click(within(menu).getByRole('button', { name: t('header.resize') }));
		expect(onOpenResizeModal).toHaveBeenCalledTimes(1);
		await tick();
		expect(screen.queryByRole('group', { name: (name) => name.includes(t('rowActions.instanceActions', { name: 'vm-1' })) })).toBeNull();

		const reopened = await openOverflow();
		await fireEvent.click(within(reopened).getByRole('button', { name: t('header.openConsole') }));
		expect(mocks.openConsole).toHaveBeenCalledTimes(1);
	});

	it('shows only Start inline for a stopped VM and moves archive/delete/resize to the menu', async () => {
		renderHeader({ instance: { ...activeInstance, status: 'SHUTOFF' } });
		expect(buttonNames(primaryRow())).toEqual([t('header.start')]);
		const menu = await openOverflow();
		expect(buttonNames(menu)).toEqual([t('rename.title'), t('header.shelve'), t('header.resize'), t('header.delete')]);
		await fireEvent.click(within(menu).getByRole('button', { name: t('header.delete') }));
		expect(mocks.deleteInstance).toHaveBeenCalledTimes(1);
	});

	it('keeps Waygate lock and busy guards on overflow actions', async () => {
		renderHeader({ instance: { ...activeInstance, status: 'SHUTOFF' }, waygateLocked: true });
		expect(within(primaryRow()).getByRole<HTMLButtonElement>('button', { name: t('header.start') }).disabled).toBe(false);
		const menu = await openOverflow();
		for (const name of [t('rename.title'), t('header.shelve'), t('header.resize'), t('header.delete')]) {
			const button = within(menu).getByRole<HTMLButtonElement>('button', { name });
			expect(button.disabled).toBe(true);
			expect(button.title).toBe(t('waygate.managedNote'));
		}
		cleanup();
		renderHeader({ actioning: 'reboot' });
		expect(within(primaryRow()).getByRole<HTMLButtonElement>('button', { name: t('header.stop') }).disabled).toBe(true);
	});

	it('gives a reader only the console in the overflow menu and no inline mutations', async () => {
		renderHeader({}, { canMutate: false });
		expect(screen.queryByTestId('instance-mobile-primary-actions')).toBeNull();
		const menu = await openOverflow();
		expect(buttonNames(menu)).toEqual([t('header.openConsole')]);
		cleanup();
		renderHeader({ instance: { ...activeInstance, status: 'SHUTOFF' }, canChangePassword: true }, { canMutate: false });
		expect(screen.queryAllByRole('button')).toHaveLength(0);
	});

	it('moves administrator recovery actions into the overflow menu', async () => {
		const onOpenEvacuateModal = vi.fn();
		renderHeader({}, { adminProjectId: 'project-a', onOpenEvacuateModal });
		const menu = await openOverflow();
		for (const name of [t('header.liveMigration'), t('header.coldMigration'), t('header.evacuate')]) {
			expect(within(menu).getByRole('button', { name })).toBeTruthy();
		}
		await fireEvent.click(within(menu).getByRole('button', { name: t('header.evacuate') }));
		expect(onOpenEvacuateModal).toHaveBeenCalledTimes(1);
	});

	it('keeps the state-specific primaries inline for shelved and resize-verification states', () => {
		renderHeader({ instance: { ...activeInstance, status: 'SHELVED_OFFLOADED' } });
		expect(buttonNames(primaryRow())).toEqual([t('header.unshelve')]);
		cleanup();
		renderHeader({ instance: { ...activeInstance, status: 'VERIFY_RESIZE' } });
		expect(buttonNames(primaryRow())).toEqual([t('header.confirmResize'), t('header.revert')]);
	});

	it('renders the unchanged tablet/desktop header outside the mobile viewport', () => {
		mocks.viewport.mobile = false;
		renderHeader();
		expect(screen.queryByTestId('instance-mobile-header')).toBeNull();
		for (const name of [t('rename.title'), t('header.openConsole'), t('header.stop'), t('header.reboot'), t('header.resize')]) {
			expect(screen.getByRole('button', { name })).toBeTruthy();
		}
		expect(screen.queryByRole('button', { name: t('rowActions.instanceActions', { name: 'vm-1' }) })).toBeNull();
	});
});
