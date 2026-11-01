import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import type { InstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
import type { Instance } from '$lib/types/compute';
import { flavorCreateBlock, type FlavorComposition, type FlavorComposerSnapshot, type FlavorOption } from '$lib/types/flavor';
import { ApiError } from '$lib/api/errors';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/instance';
import { t as tw } from '$lib/i18n/ns/vm-wizard';
import { consumerFlavorLabel } from '$lib/utils/flavorDisplay';

const { mockControllerRef, mockGet, mockPost } = vi.hoisted(() => ({
	mockControllerRef: { current: undefined as unknown }, mockGet: vi.fn(), mockPost: vi.fn(),
}));
vi.mock('$lib/stores/instanceDetailController.svelte', () => ({
	useInstanceDetailController: () => mockControllerRef.current,
}));
vi.mock('$lib/api/client', () => ({ api: { get: mockGet, post: mockPost } }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', sessionId: 'login', userId: 'user', identityDomainId: 'home', domainId: 'domain', projectId: 'caller-project', roles: ['member'], isSystemAdmin: true }),
	authReady: writable(true), canWrite: writable(true), logoutInProgress: writable(false), projectSwitching: writable(false),
}));

import ResizeModal from '../ResizeModal.svelte';

const composition: FlavorComposition = { vcpus: 4, ram_mb: 4096, gpu_profile_id: null, gpu_count: 0 };
function flavor(id: string, tuple = composition): FlavorOption {
	return { id, name: `native-${id}`, vcpus: tuple.vcpus, ram: tuple.ram_mb, disk: 20, is_public: true, composition: tuple,
		eligibility: { selectable: true, blockers: [], requirements: { instances: 0, cores: tuple.vcpus, ram_mb: tuple.ram_mb, gpus: {} }, remaining: { instances: 10, cores: 128, ram_mb: 131072, gpus: {} },
			capacity: { status: 'available', checked_at: '2026-10-31T10:00:00Z', candidate_hosts: 1, cpu_resource_class: 'VCPU', remaining_vcpus: 128, remaining_ram_mb: 131072 } } };
}
const target = flavor('flavor-2');
const current = flavor('flavor-1', { ...composition, vcpus: 2, ram_mb: 2048 });
const snapshot: FlavorComposerSnapshot = {
	checked_at: '2026-10-31T10:00:00Z', status: 'available', gpu_profiles: [], variants: [
		{ gpu_profile_id: null, gpu_count: 0, status: 'available', regions: [{ vcpus: { min: 2, max: 8, step: 2 }, ram_mb: { min: 1024, max: 8192, step: 1024 } }], preview: target },
	],
};
function renderModal(overrides: Partial<InstanceDetailController> = {}, props: { adminMode?: boolean; preselectFlavorId?: string } = {}) {
	const controller = {
		resizeFlavors: [target],
		instance: { id: 'vm', project_id: 'target-project', flavor_id: current.id, status: 'SHUTOFF' } as Instance,
		resizeLoading: false, resizeFlavorsLoading: false, resizeError: '', loadResizeFlavors: vi.fn(),
		doResize: vi.fn().mockResolvedValue(true),
		selectableResizeFlavor: (id: string, composed?: FlavorOption | null): boolean => {
			const choice = composed ?? controller.resizeFlavors.find(row => row.id === id);
			return Boolean(choice && choice.id === id && id !== controller.instance?.flavor_id && flavorCreateBlock(choice) === null);
		},
		...overrides,
	};
	mockControllerRef.current = controller;
	const onClose = vi.fn();
	return { onClose, doResize: controller.doResize, ...render(ResizeModal, { props: { ...props, onClose } }) };
}
async function chooseCatalog(choice = target) {
	const mode = screen.getByRole<HTMLButtonElement>('button', { name: tw('composer.catalog') });
	await waitFor(() => expect(mode.disabled).toBe(false));
	await fireEvent.click(mode);
	const rows = await screen.findAllByRole('button', { name: tw('flavor.selectLabel', { name: consumerFlavorLabel(choice) }) });
	await fireEvent.click(rows[0]);
}
async function submitButton() {
	const button = await screen.findByRole<HTMLButtonElement>('button', { name: t('resize.submit') });
	await waitFor(() => expect(button.disabled).toBe(false));
	return button;
}

beforeEach(() => {
	vi.clearAllMocks();
	initLocale('ko');
	mockGet.mockImplementation(async (path: string) => new URL(path, 'https://test.invalid').pathname.endsWith('compositions') ? { items: [target] } : snapshot);
	mockPost.mockImplementation(async (_path, tuple, _token, _project, request) => {
		request.beforeDispatch();
		return flavor('readback-flavor', tuple);
	});
});
afterEach(() => cleanup());

describe('ResizeModal', () => {
	it('submits the selected catalog identity and closes only after controller success', async () => {
		const { doResize, onClose } = renderModal();
		await chooseCatalog();
		await fireEvent.click(await submitButton());
		await waitFor(() => expect(doResize).toHaveBeenCalledWith(target.id, null));
		expect(mockPost).not.toHaveBeenCalled();
		expect(onClose).toHaveBeenCalledTimes(1);
	});

	it('preselects a recommendation in the catalog once ready', async () => {
		const { doResize } = renderModal({}, { preselectFlavorId: target.id });
		await waitFor(() => expect(screen.getAllByRole('button', { name: tw('flavor.selectLabel', { name: consumerFlavorLabel(target) }) })[0].getAttribute('aria-pressed')).toBe('true'));
		await fireEvent.click(await submitButton());
		expect(doResize).toHaveBeenCalledWith(target.id, null);
	});

	it.each([false, true])('saves the entered composition before resizing its readback in adminMode=%s', async adminMode => {
		const pending = Promise.withResolvers<FlavorOption>();
		mockPost.mockImplementationOnce((_path, _tuple, _token, _project, request) => { request.beforeDispatch(); return pending.promise; });
		const { doResize, onClose } = renderModal({}, { adminMode });
		const direct = screen.getByRole<HTMLButtonElement>('button', { name: tw('composer.direct') });
		await waitFor(() => expect(direct.disabled).toBe(false));
		await fireEvent.click(direct);
		await fireEvent.input(screen.getByRole('spinbutton', { name: tw('composer.cores') }), { target: { value: '4' } });
		await fireEvent.blur(screen.getByRole('spinbutton', { name: tw('composer.cores') }));
		await fireEvent.input(screen.getByRole('spinbutton', { name: tw('composer.ram') }), { target: { value: '4' } });
		await fireEvent.blur(screen.getByRole('spinbutton', { name: tw('composer.ram') }));
		const button = await submitButton();
		await fireEvent.click(button);
		await fireEvent.click(button);
		await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1));
		const [path, tuple, token, project] = mockPost.mock.calls[0];
		const url = new URL(path, 'https://test.invalid');
		expect(url.pathname).toBe(adminMode ? '/api/v1/admin/instances/flavor-compositions' : '/api/v1/flavors/compositions');
		expect(url.searchParams.get('instance_id')).toBe('vm');
		expect(url.searchParams.get('project_id')).toBe(adminMode ? 'target-project' : null);
		expect(tuple).toEqual(composition);
		expect([token, project]).toEqual(['token', 'caller-project']);
		expect(doResize).not.toHaveBeenCalled();
		expect(onClose).not.toHaveBeenCalled();
		const readback = flavor('readback-flavor');
		pending.resolve(readback);
		await waitFor(() => expect(doResize).toHaveBeenCalledWith(readback.id, readback));
		expect(onClose).toHaveBeenCalledTimes(1);
	});

	it('reassesses a saved composition and resizes the fresh native identity', async () => {
		const { doResize } = renderModal();
		const mode = screen.getByRole<HTMLButtonElement>('button', { name: tw('composer.saved') });
		await waitFor(() => expect(mode.disabled).toBe(false));
		await fireEvent.click(mode);
		await fireEvent.click(await screen.findByRole('button', { name: tw('composer.reuse') }));
		await fireEvent.click(await submitButton());
		expect(mockPost).toHaveBeenCalledTimes(1);
		expect(mockPost.mock.calls[0][1]).toEqual(composition);
		expect(doResize).toHaveBeenCalledWith('readback-flavor', flavor('readback-flavor'));
	});

	it.each(['declined', 'failed'])('keeps the modal open when controller resize is %s', async outcome => {
		const doResize = vi.fn().mockResolvedValue(false);
		const { onClose } = renderModal({ doResize, resizeError: outcome === 'failed' ? 'Nova unavailable' : '' });
		await chooseCatalog();
		await fireEvent.click(await submitButton());
		await waitFor(() => expect(doResize).toHaveBeenCalledWith(target.id, null));
		expect(onClose).not.toHaveBeenCalled();
		if (outcome === 'failed') expect(screen.getByText('Nova unavailable')).toBeTruthy();
	});

	it('keeps the modal open and does not resize when composition publication fails', async () => {
		mockPost.mockImplementationOnce(async (_path, _tuple, _token, _project, request) => { request.beforeDispatch(); throw new ApiError(409, 'Composition unavailable'); });
		const { doResize, onClose } = renderModal();
		await fireEvent.click(await submitButton());
		await screen.findByText('Composition unavailable');
		expect(doResize).not.toHaveBeenCalled();
		expect(onClose).not.toHaveBeenCalled();
		expect((await submitButton()).disabled).toBe(false);
	});

	it('blocks overlapping submissions while controller confirmation is pending', async () => {
		const pending = Promise.withResolvers<boolean>();
		const doResize = vi.fn().mockReturnValue(pending.promise);
		renderModal({ doResize });
		await chooseCatalog();
		const button = await submitButton();
		await fireEvent.click(button);
		await fireEvent.click(button);
		expect(doResize).toHaveBeenCalledTimes(1);
		expect(screen.getByRole<HTMLButtonElement>('button', { name: t('resize.awaitingConfirmation') }).disabled).toBe(true);
		pending.resolve(false);
		await submitButton();
		expect(doResize).toHaveBeenCalledTimes(1);
	});

	it('hides current and blocked catalog choices instead of offering disabled options', async () => {
		const blocked = flavor('blocked', { ...composition, vcpus: 8 });
		blocked.eligibility = { ...blocked.eligibility!, selectable: false, blockers: [{ code: 'disk_shrink' }] };
		const currentChoice = { ...current, eligibility: { ...current.eligibility!, selectable: false, blockers: [{ code: 'current_flavor' }] } };
		renderModal({ resizeFlavors: [currentChoice, target, blocked] });
		await chooseCatalog();
		for (const hidden of [currentChoice, blocked]) expect(screen.queryByRole('button', { name: tw('flavor.selectLabel', { name: consumerFlavorLabel(hidden) }) })).toBeNull();
	});

	it.each(['ACTIVE', 'SHUTOFF'])('shows the guest restart notice only for %s', status => {
		renderModal({ instance: { id: 'vm', project_id: 'target-project', flavor_id: current.id, status } as Instance });
		expect(Boolean(screen.queryByText(t('resize.runningNotice')))).toBe(status === 'ACTIVE');
	});

	it('shows flavor-loading and request errors without submitting', () => {
		const { doResize } = renderModal({ resizeFlavorsLoading: true, resizeError: '플레이버 목록을 가져올 수 없습니다' });
		expect(screen.getByText('플레이버 목록을 가져올 수 없습니다')).toBeTruthy();
		expect(screen.getByRole<HTMLButtonElement>('button', { name: t('resize.submit') }).disabled).toBe(true);
		expect(doResize).not.toHaveBeenCalled();
	});
});
