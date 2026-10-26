import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import { writable } from 'svelte/store';
import { ApiError } from '$lib/api/errors';
import type { ImageDetail } from '$lib/types/adminImage';
import type { ImageDetailController } from '$lib/stores/imageDetailController.svelte';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { originalImage } from './windowsSetupFixtures';

const boundary = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn(), post: vi.fn(), delete: vi.fn(), confirm: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: boundary, get ApiError() { return ApiError; }, getBaseUrl: () => 'https://api.example.test',
}));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token-a', projectId: 'project-a' }) }));
vi.mock('$lib/stores/servicePermissions', () => ({ serviceCapabilities: writable<(leaf: string) => boolean>(() => true) }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: boundary.confirm }));
import Panel from '$lib/components/ImageDetailPanel.svelte';
import Harness from './WindowsSetupConsumerHarness.svelte';

const scope = { imageId: 'image-a', token: 'token-a', projectId: 'project-a', isAdmin: true };
const member = { member_id: 'shared-project', status: 'pending' };
function foreignImage(): ImageDetail { return originalImage('image-a', 'foreign-project'); }
function deferred<T>() { return Promise.withResolvers<T>(); }
async function mount(isAdmin = true, image = foreignImage()) {
	let controller!: ImageDetailController;
	boundary.get.mockImplementation(async (path: string) => path.endsWith('/members') ? [member] : image);
	const view = render(Harness, { ...scope, isAdmin, onController: value => { controller = value; } });
	await waitFor(() => expect(controller.image).not.toBeNull());
	return { view, controller };
}

beforeEach(() => {
	for (const method of Object.values(boundary)) method.mockReset();
	boundary.confirm.mockResolvedValue(true);
	boundary.get.mockResolvedValue(foreignImage());
	initLocale('ko');
});
afterEach(() => cleanup());

describe('administrator image detail with a Personal project context', () => {
	it('renders foreign private detail and existing native admin controls without exporting via caller credentials', async () => {
		render(Panel, { imageId: 'image-a', isAdmin: true });
		expect(await screen.findByText('foreign-project')).toBeTruthy();
		expect(boundary.get).toHaveBeenCalledExactlyOnceWith('/api/v1/admin/images/image-a', 'token-a', 'project-a');
		expect(screen.getByText('공개 범위 수정')).toBeTruthy();
		expect(screen.getByRole('button', { name: '이미지 삭제' })).toBeTruthy();
		expect(screen.getByRole('button', { name: 'Windows 메타데이터 설정' })).toBeTruthy();
		expect(screen.queryByText('이미지 내보내기')).toBeNull();
		expect(boundary.get.mock.calls.some(([path]) => path.includes('palimpsest'))).toBe(false);
	});

	it.each(['public', 'community', 'shared'] as const)('renders caller-authorized %s export without administrator transport', async visibility => {
		const image = foreignImage();
		image.visibility = visibility;
		boundary.get.mockImplementation(async (path: string) => {
			if (path.includes('/palimpsest/')) return [];
			if (path.endsWith('/members')) return [{ member_id: 'project-a', status: 'accepted' }];
			return image;
		});
		render(Panel, { imageId: 'image-a', isAdmin: true });
		expect(await screen.findByText('이미지 내보내기')).toBeTruthy();
		expect(screen.getByRole('button', { name: '내보내기' })).toBeTruthy();
		await waitFor(() => expect(boundary.get).toHaveBeenCalledWith(
			'/api/v1/palimpsest/hub/image-exports?source_image_id=image-a&limit=1',
			'token-a', 'project-a', expect.objectContaining({ refresh: true }),
		));
	});

	it('selects admin visibility, member list/add/remove and delete paths while retaining logical caller project', async () => {
		const image = foreignImage();
		const { controller } = await mount(true, image);
		expect(controller.isOwner).toBe(false);
		expect(controller.canManageImage).toBe(true);
		expect(controller.canExport).toBe(false);
		boundary.patch.mockResolvedValue({ ...image, visibility: 'shared' });
		controller.visibilityValue = 'shared';
		await controller.saveVisibility();
		await waitFor(() => expect(controller.members).toEqual([member]));
		expect(boundary.patch).toHaveBeenCalledExactlyOnceWith('/api/v1/admin/images/image-a', { visibility: 'shared' }, 'token-a', 'project-a');
		expect(boundary.get).toHaveBeenLastCalledWith('/api/v1/admin/images/image-a/members', 'token-a', 'project-a');
		controller.newMemberId = 'shared-project';
		await controller.addMember();
		expect(boundary.post).toHaveBeenCalledExactlyOnceWith('/api/v1/admin/images/image-a/members', { member: 'shared-project' }, 'token-a', 'project-a');
		await controller.removeMember('shared-project');
		expect(boundary.delete).toHaveBeenCalledWith('/api/v1/admin/images/image-a/members/shared-project', 'token-a', 'project-a');
		await controller.deleteImage();
		expect(boundary.delete).toHaveBeenLastCalledWith('/api/v1/admin/images/image-a', 'token-a', 'project-a');
	});

	it('keeps nonowner consumer management denied instead of treating loaded metadata as admin authority', async () => {
		const { controller } = await mount(false);
		expect(boundary.get).toHaveBeenCalledExactlyOnceWith('/api/v1/images/image-a', 'token-a', 'project-a');
		expect(controller.canManageImage).toBe(false);
		controller.visibilityValue = 'public';
		controller.newMemberId = 'shared-project';
		await controller.saveVisibility();
		await controller.addMember();
		await controller.removeMember('shared-project');
		await controller.deleteImage();
		for (const method of [boundary.patch, boundary.post, boundary.delete, boundary.confirm]) expect(method).not.toHaveBeenCalled();
	});

	it.each(['private', 'public', 'community', 'shared'] as const)('only exposes caller-readable %s exports in admin mode', async visibility => {
		const image = foreignImage();
		image.visibility = visibility;
		const { controller } = await mount(true, image);
		await tick();
		expect(controller.canExport).toBe(visibility === 'public' || visibility === 'community');
		if (visibility === 'shared') {
			boundary.get.mockResolvedValueOnce([{ member_id: 'project-a', status: 'accepted' }]);
			await controller.loadMembers();
			expect(controller.canExport).toBe(true);
		}
	});

	it('preserves owner exports and metadata drafts on explicit admin reload', async () => {
		const image = originalImage();
		const { controller } = await mount(true, image);
		expect(controller.canExport).toBe(true);
		controller.startEditProps();
		controller.newPropKey = 'support_note';
		controller.newPropValue = 'Unsubmitted administrator draft';
		await controller.loadImage();
		expect(boundary.get).toHaveBeenCalledTimes(1);
		expect(controller.editingProps).toBe(true);
		expect(controller.newPropValue).toBe('Unsubmitted administrator draft');
		controller.cancelEditProps();
		controller.startWindowsSetup();
		controller.windowsAccount = 'DraftAdmin';
		await controller.loadImage();
		expect(boundary.get).toHaveBeenCalledTimes(1);
		expect(controller.windowsAccount).toBe('DraftAdmin');
	});

	it('fences a late admin member list across admin-to-consumer mode change', async () => {
		const image = foreignImage();
		image.visibility = 'shared';
		const pending = deferred<typeof member[]>();
		let controller!: ImageDetailController;
		boundary.get.mockImplementation((path: string) => path.endsWith('/members') ? pending.promise : Promise.resolve(image));
		const view = render(Harness, { ...scope, onController: value => { controller = value; } });
		await waitFor(() => expect(boundary.get).toHaveBeenCalledTimes(2));
		boundary.get.mockResolvedValueOnce(foreignImage());
		await view.rerender({ ...scope, isAdmin: false });
		await waitFor(() => expect(boundary.get).toHaveBeenCalledTimes(3));
		pending.resolve([member]);
		await pending.promise;
		await tick();
		expect(controller.members).toEqual([]);
		expect(controller.canManageImage).toBe(false);
		expect(controller.image?.visibility).toBe('private');
	});

	it('discards late admin visibility state without replacing the new consumer image or draft', async () => {
		const pending = deferred<ImageDetail>();
		const { controller, view } = await mount();
		boundary.patch.mockReturnValueOnce(pending.promise);
		controller.visibilityValue = 'shared';
		const saving = controller.saveVisibility();
		boundary.get.mockResolvedValueOnce(originalImage());
		await view.rerender({ ...scope, isAdmin: false });
		await waitFor(() => expect(controller.isOwner).toBe(true));
		controller.startEditProps();
		controller.newPropKey = 'new-scope-note';
		controller.newPropValue = 'keep current draft';
		pending.resolve({ ...foreignImage(), visibility: 'shared' });
		await saving;
		expect(controller.image?.owner).toBe('project-a');
		expect(controller.image?.visibility).toBe('private');
		expect(controller.newPropValue).toBe('keep current draft');
		expect(controller.editingProps).toBe(true);
		expect(controller.savingVisibility).toBe(false);
		expect(boundary.get.mock.calls.some(([path]) => path.endsWith('/members'))).toBe(false);
	});

	it('does not send deletion after authority changes while confirmation is open', async () => {
		const confirmed = deferred<boolean>();
		const { controller, view } = await mount();
		boundary.confirm.mockReturnValueOnce(confirmed.promise);
		const deleting = controller.deleteImage();
		boundary.get.mockResolvedValueOnce(foreignImage());
		await view.rerender({ ...scope, isAdmin: false });
		await waitFor(() => expect(controller.canManageImage).toBe(false));
		confirmed.resolve(true);
		await deleting;
		expect(boundary.delete).not.toHaveBeenCalled();
	});
});
