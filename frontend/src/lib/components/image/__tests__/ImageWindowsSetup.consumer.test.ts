import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { ApiError } from '$lib/api/errors';
import type { ImageDetail } from '$lib/types/adminImage';
import type { ImageDetailController } from '$lib/stores/imageDetailController.svelte';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/images-keys';
import {
	originalImage, authoritativeSavedImage, persistedImage, requiredDifferences, win11Differences,
} from './windowsSetupFixtures';

const boundary = vi.hoisted(() => ({
	get: vi.fn(), patch: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(),
}));
vi.mock('$lib/api/client', () => ({ api: boundary, get ApiError() { return ApiError; } }));
// No controller, component, context, i18n, or UI primitive mocks.
import Harness from './WindowsSetupConsumerHarness.svelte';

interface Scope { imageId: string; token: string; projectId: string; isAdmin: boolean }
const initialScope: Scope = { imageId: 'image-a', token: 'token-a', projectId: 'project-a', isAdmin: false };

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (error: unknown) => void;
	const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
	return { promise, resolve, reject };
}

function mountPending(scope: Scope = initialScope) {
	let controller!: ImageDetailController;
	const view = render(Harness, { ...scope, onController: value => { controller = value; } });
	return { view, get controller() { return controller; } };
}

async function mount(scope: Scope = initialScope) {
	const mounted = mountPending(scope);
	await waitFor(() => expect(mounted.controller.image).not.toBeNull());
	return mounted;
}

function setupRegion() { return screen.getByRole('region', { name: 'Windows setup consumer' }); }
function propertiesRegion() { return screen.getByRole('region', { name: 'Image properties consumer' }); }
function accountInput() {
	return within(setupRegion()).getByRole<HTMLInputElement>('textbox', { name: t('windowsSetup.accountLabel') });
}
function confirmation() {
	return within(setupRegion()).getByRole<HTMLInputElement>('checkbox', { name: t('windowsSetup.acknowledge') });
}
function optionalInput(feature: 'win11' | 'qga') {
	return within(setupRegion()).getByRole<HTMLInputElement>('checkbox', {
		name: t(feature === 'win11' ? 'windowsSetup.win11Label' : 'windowsSetup.qgaLabel'),
	});
}
function saveButton(retry = false) {
	return within(setupRegion()).getByRole<HTMLButtonElement>('button', {
		name: t(retry ? 'windowsSetup.retry' : 'windowsSetup.save'),
	});
}
async function openSetup(account?: string) {
	await fireEvent.click(within(setupRegion()).getByRole('button', { name: t('windowsSetup.start') }));
	if (account !== undefined) await fireEvent.input(accountInput(), { target: { value: account } });
}
async function prepareSetup(account = 'PlatformAdmin') {
	await openSetup(account);
	await fireEvent.click(confirmation());
}
function propertyRow(key: string) {
	return within(propertiesRegion()).getByText(key, { exact: true }).closest('tr')!;
}
function expectPreview(expected: Record<string, string>, current = originalImage().properties) {
	const rows = within(setupRegion()).getAllByTestId('windows-setup-change');
	expect(rows.map(row => row.getAttribute('data-property')).sort()).toEqual(Object.keys(expected).sort());
	for (const [key, value] of Object.entries(expected)) {
		const row = rows.find(row => row.getAttribute('data-property') === key)!;
		expect(within(row).getByTestId('windows-setup-change-current').textContent).toBe(current[key] ?? t('windowsSetup.unset'));
		expect(within(row).getByTestId('windows-setup-change-proposed').textContent).toBe(value);
	}
}
function expectFullProjection(controller: ImageDetailController, expected: ImageDetail) {
	expect(controller.image).toEqual(expected);
	expect(controller.visibilityValue).toBe(expected.visibility);
	for (const key of [
		'name', 'visibility', 'updated_at', 'os_type', 'os_distro', 'os_admin_user',
		'windows_initial_password_method', 'os_version', 'disk_format', 'size', 'virtual_size',
		'min_disk', 'min_ram', 'protected', 'checksum', 'os_hash_value', 'tags',
	] as const) {
		const value = expected[key];
		expect(screen.getByTestId(`projection-${key}`).textContent).toBe(Array.isArray(value) ? value.join(', ') : String(value));
	}
	for (const [key, value] of Object.entries(expected.properties)) {
		expect(within(propertyRow(key)).getByText(value, { exact: true })).toBeTruthy();
	}
}
function expectNoMutation() {
	for (const method of [boundary.patch, boundary.post, boundary.put, boundary.delete]) expect(method).not.toHaveBeenCalled();
}

beforeEach(() => {
	for (const method of Object.values(boundary)) method.mockReset();
	boundary.get.mockResolvedValue(originalImage());
	boundary.patch.mockResolvedValue(authoritativeSavedImage());
	initLocale('ko');
});
afterEach(() => cleanup());

describe('Windows setup consumer, real controller and metadata editors', () => {
	it('requires explicit confirmation and shows a preview without changing the image or native marker', async () => {
		const { controller } = await mount();
		const before = originalImage();
		await openSetup('PlatformAdmin');
		expect(accountInput().value).toBe('PlatformAdmin');
		expect(confirmation().checked).toBe(false);
		expect(saveButton().disabled).toBe(true);
		expectPreview(requiredDifferences);
		expect(controller.windowsChanges.map(change => change.key).sort()).toEqual(Object.keys(requiredDifferences).sort());
		expect(controller.image).toEqual(before);
		expect(controller.windowsStatus).toBe('legacy');
		expect(within(setupRegion()).queryByText(t('windowsSetup.status.native'))).toBeNull();
		await fireEvent.click(saveButton());
		await controller.saveWindowsSetup(); // A disabled button is not the authorization/confirmation guard.
		expectNoMutation();
		expect(controller.image).toEqual(before);
		await fireEvent.click(confirmation());
		expect(saveButton().disabled).toBe(false);
		expectNoMutation();
		expect(controller.windowsStatus).toBe('legacy');
		await fireEvent.click(confirmation());
		expect(saveButton().disabled).toBe(true);
		await controller.saveWindowsSetup();
		expectNoMutation();
	});

	it.each(['', '   ', '\t', 'Bad\u0000Account', 'Bad\u007fAccount'])('rejects invalid account %j after confirmation', async account => {
		const { controller } = await mount();
		await prepareSetup();
		await fireEvent.input(accountInput(), { target: { value: account } });
		expect(controller.windowsAccount).toBe(account);
		expect(controller.windowsAccountValid).toBe(false);
		expect(saveButton().disabled).toBe(true);
		expect(within(setupRegion()).getByText(t('windowsSetup.invalidAccount'))).toBeTruthy();
		await controller.saveWindowsSetup();
		expectNoMutation();
		expect(controller.image).toEqual(originalImage());
	});

	it('guards newline accounts even though native single-line inputs normalize newlines', async () => {
		const { controller } = await mount();
		await prepareSetup();
		controller.windowsAccount = 'Bad\nAccount';
		await tick();
		expect(controller.windowsAccountValid).toBe(false);
		expect(saveButton().disabled).toBe(true);
		await controller.saveWindowsSetup();
		expectNoMutation();
	});

	it.each(['ExistingOperator', undefined])('defaults the account from the image or to Admin: %s', async existing => {
		const image = originalImage();
		if (existing === undefined) {
			delete image.properties.os_admin_user;
			image.os_admin_user = null;
		}
		boundary.get.mockResolvedValueOnce(image);
		const { controller } = await mount();
		await openSetup();
		expect(accountInput().value).toBe(existing ?? 'Admin');
		expect(controller.windowsAccount).toBe(existing ?? 'Admin');
		expect(confirmation().checked).toBe(false);
		expectNoMutation();
	});

	it('uses a top-level existing account when properties omit the projected key', async () => {
		const image = originalImage();
		delete image.properties.os_admin_user;
		boundary.get.mockResolvedValueOnce(image);
		await mount();
		await openSetup();
		expect(accountInput().value).toBe('ExistingOperator');
		expectNoMutation();
	});

	it('requires the real distro flag even when the display projection inferred Windows', async () => {
		const image = authoritativeSavedImage();
		delete image.properties.os_distro;
		boundary.get.mockResolvedValueOnce(image);
		const { controller } = await mount();
		await prepareSetup();
		expectPreview({ os_distro: 'windows' }, image.properties);
		expect(controller.windowsCurrentProperties.os_distro).toBeUndefined();
		await fireEvent.click(saveButton());
		await waitFor(() => expect(controller.windowsSuccess).toBe(true));
		expect(boundary.patch).toHaveBeenCalledExactlyOnceWith('/api/v1/images/image-a/properties', {
			set: { os_distro: 'windows' }, remove: [],
		}, 'token-a', 'project-a');
		expectFullProjection(controller, authoritativeSavedImage());
	});

	it.each(['optional', undefined])('includes mandatory ConfigDrive when initially %s', async configDrive => {
		const image = originalImage();
		if (configDrive === undefined) delete image.properties.img_config_drive;
		else image.properties.img_config_drive = configDrive;
		boundary.get.mockResolvedValueOnce(image);
		const { controller } = await mount();
		await prepareSetup();
		const expected = { ...requiredDifferences, img_config_drive: 'mandatory' };
		expectPreview(expected, image.properties);
		await fireEvent.click(saveButton());
		await waitFor(() => expect(controller.windowsSuccess).toBe(true));
		expect(boundary.patch).toHaveBeenCalledExactlyOnceWith('/api/v1/images/image-a/properties', { set: expected, remove: [] }, 'token-a', 'project-a');
		expectFullProjection(controller, authoritativeSavedImage());
	});

	it('sends only preview differences once; unchecked options and unrelated properties survive authoritative save and independent reload', async () => {
		const { view, controller } = await mount();
		await prepareSetup();
		expect(optionalInput('win11').checked).toBe(false);
		expect(optionalInput('qga').checked).toBe(false);
		expectPreview(requiredDifferences);
		expect(within(setupRegion()).queryByText('img_config_drive', { exact: true })).toBeNull();
		await fireEvent.click(saveButton());
		await waitFor(() => expect(controller.windowsSuccess).toBe(true));
		expect(boundary.patch).toHaveBeenCalledTimes(1);
		expect(boundary.patch).toHaveBeenCalledWith('/api/v1/images/image-a/properties', {
			set: requiredDifferences, remove: [],
		}, 'token-a', 'project-a');
		expect(boundary.get).toHaveBeenCalledTimes(1); // PATCH is already a full provider reread.
		expectFullProjection(controller, authoritativeSavedImage());
		expect(controller.windowsStatus).toBe('native');
		expect(within(setupRegion()).getByText(t('windowsSetup.status.native'))).toBeTruthy();
		expect(within(setupRegion()).getByText(t('windowsSetup.saved'))).toBeTruthy();
		for (const key of ['hw_firmware_type', 'hw_machine_type', 'hw_tpm_version', 'hw_tpm_model', 'os_secure_boot', 'hw_qemu_guest_agent', 'license_channel', 'support_ticket']) {
			expect(controller.image!.properties[key]).toBe(originalImage().properties[key]);
		}
		view.unmount();
		boundary.get.mockResolvedValueOnce(persistedImage());
		const reloaded = await mount();
		expect(boundary.get).toHaveBeenNthCalledWith(2, '/api/v1/images/image-a', 'token-a', 'project-a');
		expectFullProjection(reloaded.controller, persistedImage());
		expect(reloaded.controller.windowsStatus).toBe('native');
		expect(boundary.patch).toHaveBeenCalledTimes(1);
		await openSetup();
		expect(accountInput().value).toBe('PlatformAdmin');
		expect(reloaded.controller.windowsChanges).toEqual([]);
		expect(saveButton().disabled).toBe(true);
	});

	it.each([
		{ win11: true, qga: false }, { win11: false, qga: true }, { win11: true, qga: true },
	])('writes exact selected optional flags win11=$win11 qga=$qga', async ({ win11, qga }) => {
		const server = authoritativeSavedImage();
		if (win11) Object.assign(server.properties, win11Differences);
		if (qga) server.properties.hw_qemu_guest_agent = 'yes';
		boundary.patch.mockResolvedValueOnce(server);
		const { controller } = await mount();
		await prepareSetup();
		if (win11) await fireEvent.click(optionalInput('win11'));
		if (qga) await fireEvent.click(optionalInput('qga'));
		const expected = { ...requiredDifferences, ...(win11 ? win11Differences : {}), ...(qga ? { hw_qemu_guest_agent: 'yes' } : {}) };
		expectPreview(expected);
		expect(Object.fromEntries(controller.windowsChanges.map(change => [change.key, change.proposed]))).toEqual(expected);
		await fireEvent.click(saveButton());
		await waitFor(() => expect(controller.windowsSuccess).toBe(true));
		expect(boundary.patch).toHaveBeenCalledExactlyOnceWith('/api/v1/images/image-a/properties', { set: expected, remove: [] }, 'token-a', 'project-a');
		expectFullProjection(controller, server);
	});

	it('cancels the setup draft without saving or modifying the original image', async () => {
		const { controller } = await mount();
		await prepareSetup('DiscardMe');
		await fireEvent.click(optionalInput('win11'));
		await fireEvent.click(optionalInput('qga'));
		await fireEvent.click(within(setupRegion()).getByRole('button', { name: t('windowsSetup.cancel') }));
		expect(controller.windowsEditing).toBe(false);
		expect(controller.windowsConfirmed).toBe(false);
		expect(controller.windowsAccount).toBe('');
		expect(controller.image).toEqual(originalImage());
		expectNoMutation();
		await openSetup();
		expect(accountInput().value).toBe('ExistingOperator');
		expect(optionalInput('win11').checked).toBe(false);
		expect(optionalInput('qga').checked).toBe(false);
		expect(confirmation().checked).toBe(false);
	});

	it('never overwrites an arbitrary draft and locks setup and properties editors against each other', async () => {
		const { controller } = await mount();
		await fireEvent.click(within(propertiesRegion()).getByRole('button', { name: t('propertiesSection.edit') }));
		await fireEvent.input(within(propertyRow('support_ticket')).getByRole('textbox'), { target: { value: 'UNSAVED-TICKET' } });
		await fireEvent.click(within(propertyRow('license_channel')).getByRole('button'));
		await fireEvent.input(within(propertiesRegion()).getByPlaceholderText(t('propertiesSection.keyPlaceholder')), { target: { value: 'pending_custom' } });
		await fireEvent.input(within(propertiesRegion()).getByPlaceholderText(t('propertiesSection.valuePlaceholder')), { target: { value: 'pending-value' } });
		const draft = { ...controller.propsDraft };
		const removed = Array.from(controller.propsRemovedKeys);
		const start = within(setupRegion()).getByRole<HTMLButtonElement>('button', { name: t('windowsSetup.start') });
		expect(start.disabled).toBe(true);
		expect(within(setupRegion()).getByText(t('windowsSetup.draftConflict'))).toBeTruthy();
		await fireEvent.click(start);
		controller.startWindowsSetup();
		await controller.saveWindowsSetup();
		await controller.loadImage();
		expect(controller.windowsEditing).toBe(false);
		expect(controller.editingProps).toBe(true);
		expect(controller.propsDraft).toEqual(draft);
		expect(Array.from(controller.propsRemovedKeys)).toEqual(removed);
		expect(controller.newPropKey).toBe('pending_custom');
		expect(controller.newPropValue).toBe('pending-value');
		expect(boundary.get).toHaveBeenCalledTimes(1);
		expectNoMutation();
		await fireEvent.click(within(propertiesRegion()).getByRole('button', { name: t('propertiesSection.cancel') }));
		await openSetup();
		const edit = within(propertiesRegion()).getByRole<HTMLButtonElement>('button', { name: t('propertiesSection.edit') });
		expect(edit.disabled).toBe(true);
		await fireEvent.click(edit);
		controller.startEditProps();
		await controller.saveProperties();
		expect(controller.editingProps).toBe(false);
		expect(controller.windowsEditing).toBe(true);
		expectNoMutation();
	});

	it('keeps nonowner requirements readable while guarding direct setup and property mutations', async () => {
		boundary.get.mockResolvedValueOnce(originalImage('image-a', 'another-owner'));
		const { controller } = await mount();
		for (const key of ['windowsSetup.requirements.guest', 'windowsSetup.requirements.hardware', 'windowsSetup.requirements.access', 'windowsSetup.warning'] as const) {
			expect(within(setupRegion()).getByText(t(key))).toBeTruthy();
		}
		expect(within(setupRegion()).getByText(t('windowsSetup.readonly'))).toBeTruthy();
		expect(within(setupRegion()).queryByRole('button', { name: t('windowsSetup.start') })).toBeNull();
		expect(within(propertiesRegion()).queryByRole('button', { name: t('propertiesSection.edit') })).toBeNull();
		controller.startWindowsSetup();
		controller.windowsAccount = 'Intruder';
		controller.windowsConfirmed = true;
		controller.windowsWin11 = true;
		controller.windowsQga = true;
		await controller.saveWindowsSetup();
		controller.startEditProps();
		controller.newPropKey = 'os_type';
		controller.newPropValue = 'windows';
		controller.addProperty();
		controller.removeProperty('support_ticket');
		await controller.saveProperties();
		expect(controller.canEditMetadata).toBe(false);
		expect(controller.windowsEditing).toBe(false);
		expect(controller.editingProps).toBe(false);
		expect(controller.windowsConfirmed).toBe(false);
		expect(controller.image).toEqual(originalImage('image-a', 'another-owner'));
		expectNoMutation();
	});

	it('uses the administrator properties endpoint for an image owned by another project', async () => {
		boundary.get.mockResolvedValueOnce(originalImage('image-a', 'another-owner'));
		const server = authoritativeSavedImage();
		server.owner = 'another-owner';
		boundary.patch.mockResolvedValueOnce(server);
		const { controller } = await mount({ ...initialScope, isAdmin: true });
		expect(boundary.get).toHaveBeenCalledExactlyOnceWith('/api/v1/admin/images/image-a', 'token-a', 'project-a');
		expect(controller.isOwner).toBe(false);
		expect(controller.canEditMetadata).toBe(true);
		await prepareSetup();
		await fireEvent.click(saveButton());
		await waitFor(() => expect(controller.windowsSuccess).toBe(true));
		expect(boundary.patch).toHaveBeenCalledExactlyOnceWith('/api/v1/admin/images/image-a/properties', { set: requiredDifferences, remove: [] }, 'token-a', 'project-a');
		expectFullProjection(controller, server);
	});

	it('locks pending saves, preserves image and draft on failure, and retries to a full authoritative projection', async () => {
		const first = deferred<ImageDetail>();
		const retry = deferred<ImageDetail>();
		boundary.patch.mockReturnValueOnce(first.promise).mockReturnValueOnce(retry.promise);
		const { controller } = await mount();
		await prepareSetup();
		await fireEvent.click(saveButton());
		expect(controller.windowsSaving).toBe(true);
		expect(accountInput().disabled).toBe(true);
		for (const input of [confirmation(), optionalInput('win11'), optionalInput('qga')]) expect(input.disabled).toBe(true);
		for (const button of within(setupRegion()).getAllByRole<HTMLButtonElement>('button')) expect(button.disabled).toBe(true);
		expect(within(propertiesRegion()).getByRole<HTMLButtonElement>('button', { name: t('propertiesSection.edit') }).disabled).toBe(true);
		controller.windowsAccount = 'OverwrittenDuringSave';
		controller.windowsWin11 = true;
		controller.windowsQga = true;
		controller.windowsConfirmed = false;
		controller.cancelWindowsSetup();
		controller.startEditProps();
		await controller.saveWindowsSetup();
		await controller.saveProperties();
		await controller.loadImage();
		expect(controller.windowsAccount).toBe('PlatformAdmin');
		expect(controller.windowsConfirmed).toBe(true);
		expect(controller.windowsWin11).toBe(false);
		expect(controller.windowsQga).toBe(false);
		expect(controller.editingProps).toBe(false);
		expect(controller.windowsEditing).toBe(true);
		expect(controller.windowsStatus).toBe('legacy');
		expect(boundary.patch).toHaveBeenCalledTimes(1);
		expect(boundary.get).toHaveBeenCalledTimes(1);
		first.reject(new ApiError(503, 'Provider unavailable; retry permitted'));
		await waitFor(() => expect(controller.windowsSaving).toBe(false));
		expect(controller.image).toEqual(originalImage());
		expect(controller.windowsEditing).toBe(true);
		expect(controller.windowsSuccess).toBe(false);
		expect(accountInput().value).toBe('PlatformAdmin');
		expect(confirmation().checked).toBe(true);
		expectPreview(requiredDifferences);
		expect(within(setupRegion()).getByText('Provider unavailable; retry permitted')).toBeTruthy();
		expect(saveButton(true).disabled).toBe(false);
		await fireEvent.click(saveButton(true));
		expect(controller.windowsSaving).toBe(true);
		expect(boundary.patch).toHaveBeenCalledTimes(2);
		expect(boundary.patch.mock.calls[1]).toEqual(boundary.patch.mock.calls[0]);
		retry.resolve(authoritativeSavedImage());
		await waitFor(() => expect(controller.windowsSuccess).toBe(true));
		expect(controller.windowsSaving).toBe(false);
		expect(controller.windowsEditing).toBe(false);
		expect(controller.windowsError).toBe('');
		expectFullProjection(controller, authoritativeSavedImage());
	});

	it('preserves arbitrary edits, pending new property and removal on failure, then restores the full provider projection on retry', async () => {
		const failedSave = deferred<ImageDetail>();
		const retriedSave = deferred<ImageDetail>();
		boundary.patch.mockReturnValueOnce(failedSave.promise).mockReturnValueOnce(retriedSave.promise);
		const { controller } = await mount();
		await fireEvent.click(within(propertiesRegion()).getByRole('button', { name: t('propertiesSection.edit') }));
		await fireEvent.input(within(propertyRow('support_ticket')).getByRole('textbox'), { target: { value: 'DRAFT-TICKET' } });
		await fireEvent.click(within(propertyRow('license_channel')).getByRole('button'));
		await fireEvent.input(within(propertiesRegion()).getByPlaceholderText(t('propertiesSection.keyPlaceholder')), { target: { value: 'pending_custom' } });
		await fireEvent.input(within(propertiesRegion()).getByPlaceholderText(t('propertiesSection.valuePlaceholder')), { target: { value: 'draft-pending-value' } });
		await fireEvent.click(within(propertiesRegion()).getByRole('button', { name: t('propertiesSection.save') }));
		expect(boundary.patch).toHaveBeenCalledExactlyOnceWith('/api/v1/images/image-a/properties', {
			set: { support_ticket: 'DRAFT-TICKET', pending_custom: 'draft-pending-value' }, remove: ['license_channel'],
		}, 'token-a', 'project-a');
		expect(controller.savingProps).toBe(true);
		for (const input of within(propertiesRegion()).getAllByRole<HTMLInputElement>('textbox')) expect(input.disabled).toBe(true);
		for (const button of within(propertiesRegion()).getAllByRole<HTMLButtonElement>('button')) expect(button.disabled).toBe(true);
		expect(within(setupRegion()).getByRole<HTMLButtonElement>('button', { name: t('windowsSetup.start') }).disabled).toBe(true);
		controller.startWindowsSetup();
		controller.cancelEditProps();
		controller.removeProperty('support_ticket');
		await controller.saveProperties();
		await controller.loadImage();
		expect(controller.windowsEditing).toBe(false);
		expect(controller.editingProps).toBe(true);
		expect(boundary.get).toHaveBeenCalledTimes(1);
		expect(boundary.patch).toHaveBeenCalledTimes(1);
		failedSave.reject(new ApiError(503, 'Arbitrary metadata provider failure'));
		await waitFor(() => expect(controller.savingProps).toBe(false));
		expect(controller.image).toEqual(originalImage());
		expect(controller.editingProps).toBe(true);
		expect(controller.propsError).toBe('Arbitrary metadata provider failure');
		expect(within(propertiesRegion()).getByText('Arbitrary metadata provider failure')).toBeTruthy();
		expect(controller.propsDraft.support_ticket).toBe('DRAFT-TICKET');
		// Save consumes the pending input into the real draft; failure must not lose it.
		expect(controller.propsDraft.pending_custom).toBe('draft-pending-value');
		expect(controller.propsDraft.license_channel).toBeUndefined();
		expect(Array.from(controller.propsRemovedKeys)).toEqual(['license_channel']);
		expect(within(propertyRow('support_ticket')).getByRole<HTMLInputElement>('textbox').value).toBe('DRAFT-TICKET');
		expect(within(propertyRow('pending_custom')).getByRole<HTMLInputElement>('textbox').value).toBe('draft-pending-value');
		await fireEvent.click(within(propertiesRegion()).getByRole('button', { name: t('propertiesSection.save') }));
		expect(boundary.patch).toHaveBeenCalledTimes(2);
		expect(boundary.patch.mock.calls[1]).toEqual(boundary.patch.mock.calls[0]);
		// Independently authored provider-normalized values, not an echo of the request.
		const provider = authoritativeSavedImage();
		provider.properties.support_ticket = 'PROVIDER-TICKET';
		provider.properties.pending_custom = 'accepted-by-provider';
		delete provider.properties.license_channel;
		retriedSave.resolve(provider);
		await waitFor(() => expect(controller.editingProps).toBe(false));
		expect(controller.savingProps).toBe(false);
		expect(controller.propsError).toBe('');
		expectFullProjection(controller, provider);
		expect(controller.windowsStatus).toBe('native');
		expect(within(propertiesRegion()).queryByText('license_channel', { exact: true })).toBeNull();
	});

});

const scopeChanges = [
	{ dimension: 'image', changed: { ...initialScope, imageId: 'image-b' } },
	{ dimension: 'token', changed: { ...initialScope, token: 'token-b' } },
	{ dimension: 'project', changed: { ...initialScope, projectId: 'project-b' } },
	{ dimension: 'admin', changed: { ...initialScope, isAdmin: true } },
];
const races = scopeChanges.flatMap(change => [false, true].flatMap(aba => ['success', 'error'].map(outcome => ({ ...change, aba, outcome }))));

describe('mounted Windows setup consumer scope and generation fences', () => {
	it.each(races)('ignores late load $outcome and finally for $dimension (ABA=$aba)', async ({ changed, aba, outcome }) => {
		const oldLoad = deferred<ImageDetail>();
		const intermediateLoad = deferred<ImageDetail>();
		const currentLoad = deferred<ImageDetail>();
		boundary.get.mockReset();
		boundary.get.mockReturnValueOnce(oldLoad.promise);
		if (aba) boundary.get.mockReturnValueOnce(intermediateLoad.promise);
		boundary.get.mockReturnValueOnce(currentLoad.promise);
		const mounted = mountPending();
		await waitFor(() => expect(boundary.get).toHaveBeenCalledTimes(1));
		await mounted.view.rerender(changed);
		await waitFor(() => expect(boundary.get).toHaveBeenCalledTimes(2));
		if (aba) {
			await mounted.view.rerender(initialScope);
			await waitFor(() => expect(boundary.get).toHaveBeenCalledTimes(3));
		}
		const currentScope = aba ? initialScope : changed;
		expect(boundary.get).toHaveBeenLastCalledWith(`${currentScope.isAdmin ? '/api/v1/admin/images' : '/api/v1/images'}/${currentScope.imageId}`, currentScope.token, currentScope.projectId);
		if (outcome === 'success') oldLoad.resolve(authoritativeSavedImage());
		else oldLoad.reject(new ApiError(503, 'Late load failure'));
		if (aba) intermediateLoad.resolve(originalImage(changed.imageId, changed.projectId));
		await oldLoad.promise.catch(() => undefined);
		await tick();
		expect(mounted.controller.loading).toBe(true); // Stale finally must not end the new load.
		expect(mounted.controller.error).toBe('');
		expect(mounted.controller.image).toBeNull();
		expect(screen.getByRole('status').textContent).toBe('Loading image');
		expect(screen.queryByRole('region', { name: 'Windows setup consumer' })).toBeNull();
		const current = originalImage(currentScope.imageId, currentScope.projectId);
		current.name = `Current ${currentScope.token} ${currentScope.isAdmin}`;
		currentLoad.resolve(current);
		await waitFor(() => expect(mounted.controller.loading).toBe(false));
		expectFullProjection(mounted.controller, current);
		expect(mounted.controller.windowsSuccess).toBe(false);
		expectNoMutation();
	});

	it.each(races)('ignores late save $outcome/error/finally for $dimension while new scope saves (ABA=$aba)', async ({ changed, aba, outcome }) => {
		const oldSave = deferred<ImageDetail>();
		const currentSave = deferred<ImageDetail>();
		boundary.patch.mockReturnValueOnce(oldSave.promise).mockReturnValueOnce(currentSave.promise);
		const mounted = await mount();
		await prepareSetup();
		await fireEvent.click(saveButton());
		expect(mounted.controller.windowsSaving).toBe(true);
		const changedImage = originalImage(changed.imageId, changed.projectId);
		changedImage.name = 'Intermediate scope image';
		boundary.get.mockResolvedValueOnce(changedImage);
		await mounted.view.rerender(changed);
		await waitFor(() => expect(mounted.controller.image?.name).toBe('Intermediate scope image'));
		if (aba) {
			const returned = originalImage();
			returned.name = 'Returned A, new generation';
			boundary.get.mockResolvedValueOnce(returned);
			await mounted.view.rerender(initialScope);
			await waitFor(() => expect(mounted.controller.image?.name).toBe('Returned A, new generation'));
		}
		const currentScope = aba ? initialScope : changed;
		const currentImage = mounted.controller.image!;
		expect(mounted.controller.windowsSaving).toBe(false);
		expect(mounted.controller.windowsEditing).toBe(false);
		expect(mounted.controller.windowsError).toBe('');
		expect(mounted.controller.windowsSuccess).toBe(false);
		await prepareSetup('CurrentScopeAccount');
		await fireEvent.click(optionalInput('qga'));
		await fireEvent.click(saveButton());
		expect(boundary.patch).toHaveBeenCalledTimes(2);
		expect(boundary.patch).toHaveBeenLastCalledWith(
			`${currentScope.isAdmin ? '/api/v1/admin/images' : '/api/v1/images'}/${currentScope.imageId}/properties`,
			{ set: { ...requiredDifferences, os_admin_user: 'CurrentScopeAccount', hw_qemu_guest_agent: 'yes' }, remove: [] },
			currentScope.token, currentScope.projectId,
		);
		if (outcome === 'success') oldSave.resolve(authoritativeSavedImage());
		else oldSave.reject(new ApiError(503, 'Late old-scope failure'));
		await oldSave.promise.catch(() => undefined);
		await tick();
		expect(mounted.controller.image).toEqual(currentImage);
		expect(screen.getByTestId('projection-name').textContent).toBe(currentImage.name);
		expect(mounted.controller.windowsSaving).toBe(true); // Old finally cannot unlock a newer save.
		expect(mounted.controller.windowsEditing).toBe(true);
		expect(mounted.controller.windowsError).toBe('');
		expect(mounted.controller.windowsSuccess).toBe(false);
		expect(mounted.controller.windowsStatus).toBe('legacy');
		expect(accountInput().value).toBe('CurrentScopeAccount');
		expect(accountInput().disabled).toBe(true);
		expect(confirmation().checked).toBe(true);
		expect(optionalInput('qga').checked).toBe(true);
		currentSave.reject(new ApiError(503, 'Current-scope retryable failure'));
		await waitFor(() => expect(mounted.controller.windowsSaving).toBe(false));
		expect(mounted.controller.windowsError).toBe('Current-scope retryable failure');
		expect(within(setupRegion()).getByText('Current-scope retryable failure')).toBeTruthy();
		expect(saveButton(true).disabled).toBe(false);
		expect(mounted.controller.image).toEqual(currentImage);
		expect(accountInput().value).toBe('CurrentScopeAccount');
	});

	it.each(['success', 'error'])('fences arbitrary save %s and finally across token ABA while a newer arbitrary save is pending', async outcome => {
		const oldSave = deferred<ImageDetail>();
		const newSave = deferred<ImageDetail>();
		boundary.patch.mockReturnValueOnce(oldSave.promise).mockReturnValueOnce(newSave.promise);
		const { view, controller } = await mount();
		await fireEvent.click(within(propertiesRegion()).getByRole('button', { name: t('propertiesSection.edit') }));
		await fireEvent.input(within(propertyRow('support_ticket')).getByRole('textbox'), { target: { value: 'Old token draft' } });
		await fireEvent.click(within(propertiesRegion()).getByRole('button', { name: t('propertiesSection.save') }));
		expect(controller.savingProps).toBe(true);
		const intermediate = originalImage();
		intermediate.name = 'Token B image';
		boundary.get.mockResolvedValueOnce(intermediate);
		await view.rerender({ ...initialScope, token: 'token-b' });
		await waitFor(() => expect(controller.image?.name).toBe('Token B image'));
		const returned = originalImage();
		returned.name = 'Token A new generation';
		boundary.get.mockResolvedValueOnce(returned);
		await view.rerender(initialScope);
		await waitFor(() => expect(controller.image?.name).toBe('Token A new generation'));
		expect(controller.savingProps).toBe(false);
		expect(controller.editingProps).toBe(false);
		expect(controller.propsDraft).toEqual({});
		await fireEvent.click(within(propertiesRegion()).getByRole('button', { name: t('propertiesSection.edit') }));
		await fireEvent.input(within(propertyRow('support_ticket')).getByRole('textbox'), { target: { value: 'Current token draft' } });
		await fireEvent.click(within(propertiesRegion()).getByRole('button', { name: t('propertiesSection.save') }));
		expect(boundary.patch).toHaveBeenLastCalledWith('/api/v1/images/image-a/properties', {
			set: { support_ticket: 'Current token draft' }, remove: [],
		}, 'token-a', 'project-a');
		if (outcome === 'success') oldSave.resolve(authoritativeSavedImage());
		else oldSave.reject(new ApiError(503, 'Obsolete arbitrary save error'));
		await oldSave.promise.catch(() => undefined);
		await tick();
		expect(controller.savingProps).toBe(true);
		expect(controller.editingProps).toBe(true);
		expect(controller.propsError).toBe('');
		expect(controller.image).toEqual(returned);
		expect(controller.propsDraft.support_ticket).toBe('Current token draft');
		expect(within(propertyRow('support_ticket')).getByRole<HTMLInputElement>('textbox').value).toBe('Current token draft');
		expect(within(propertyRow('support_ticket')).getByRole<HTMLInputElement>('textbox').disabled).toBe(true);
		expect(within(setupRegion()).getByRole<HTMLButtonElement>('button', { name: t('windowsSetup.start') }).disabled).toBe(true);
		const provider = authoritativeSavedImage();
		provider.properties.support_ticket = 'Independent latest provider value';
		newSave.resolve(provider);
		await waitFor(() => expect(controller.savingProps).toBe(false));
		expect(controller.editingProps).toBe(false);
		expect(controller.propsError).toBe('');
		expectFullProjection(controller, provider);
		expect(boundary.patch).toHaveBeenCalledTimes(2);
	});

	it.each(['success', 'error'])('ignores Windows save %s/error/finally after consumer destruction', async outcome => {
		const save = deferred<ImageDetail>();
		boundary.patch.mockReturnValueOnce(save.promise);
		const { view, controller } = await mount();
		await prepareSetup();
		await fireEvent.click(saveButton());
		expect(controller.windowsSaving).toBe(true);
		view.unmount();
		expect(controller.image).toBeNull();
		expect(controller.windowsSaving).toBe(false);
		expect(controller.windowsEditing).toBe(false);
		if (outcome === 'success') save.resolve(authoritativeSavedImage());
		else save.reject(new ApiError(503, 'Unmounted consumer save error'));
		await save.promise.catch(() => undefined);
		await tick();
		expect(controller.image).toBeNull();
		expect(controller.loading).toBe(true); // Reset state must not be touched by stale finally.
		expect(controller.windowsSaving).toBe(false);
		expect(controller.windowsEditing).toBe(false);
		expect(controller.windowsSuccess).toBe(false);
		expect(controller.windowsError).toBe('');
		expect(screen.queryByRole('region', { name: 'Windows setup consumer' })).toBeNull();
		expect(boundary.patch).toHaveBeenCalledTimes(1);
	});
});
