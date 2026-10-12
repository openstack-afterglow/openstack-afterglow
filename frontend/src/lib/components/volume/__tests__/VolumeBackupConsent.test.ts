import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import type { Volume } from '$lib/types/volume';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: { post }, ApiError: class ApiError extends Error {} }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'project-a' }) }));
vi.mock('$lib/i18n/ns/volume', () => ({ t: (key: string) => key }));
import VolumeBackupModal from '../VolumeBackupModal.svelte';
import VolumeBackupCreateModal from '../backups/VolumeBackupCreateModal.svelte';

const available: Volume = { id: 'disk-a', name: 'Data', status: 'available', size: 40, attachments: [], volume_type: null };
const attached: Volume = { ...available, status: 'in-use', attachments: [{ server_id: 'server-a' }] };
const otherAttached: Volume = { ...attached, id: 'disk-b', name: 'Other' };
const consent = () => screen.getByRole('checkbox', { name: 'backupForce.enable' }) as HTMLInputElement;
const inlineSubmit = () => screen.getByRole('button', { name: 'backupModal.create' }) as HTMLButtonElement;
const selectorSubmit = () => screen.getByRole('button', { name: 'backupCreateModal.create' }) as HTMLButtonElement;

beforeEach(() => {
	post.mockReset();
	post.mockResolvedValue({ id: 'accepted-backup', status: 'creating' });
});

describe('inline volume backup consent', () => {
	it('prevents submission until consent and restores the block when consent is withdrawn', async () => {
		const onsuccess = vi.fn();
		render(VolumeBackupModal, { volume: attached, onclose: vi.fn(), onsuccess });
		expect(consent().checked).toBe(false);
		expect(inlineSubmit().disabled).toBe(true);
		await fireEvent.click(inlineSubmit());
		expect(post).not.toHaveBeenCalled();
		await fireEvent.click(consent());
		expect(inlineSubmit().disabled).toBe(false);
		await fireEvent.click(consent());
		expect(inlineSubmit().disabled).toBe(true);
		await fireEvent.click(consent());
		await fireEvent.click(inlineSubmit());
		await waitFor(() => expect(onsuccess).toHaveBeenCalledOnce());
	});

	it('does not reuse an attached source acknowledgement for a different source or reopened dialog', async () => {
		const props = { onclose: vi.fn(), onsuccess: vi.fn() };
		const view = render(VolumeBackupModal, { volume: attached, ...props });
		await fireEvent.click(consent());
		await view.rerender({ volume: otherAttached, ...props });
		expect(consent().checked).toBe(false);
		expect(inlineSubmit().disabled).toBe(true);
		await fireEvent.click(consent());
		await view.rerender({ volume: null, ...props });
		await view.rerender({ volume: otherAttached, ...props });
		expect(consent().checked).toBe(false);
		expect(inlineSubmit().disabled).toBe(true);
		expect(post).not.toHaveBeenCalled();
	});

	it('allows an available source to be submitted without an attached-volume acknowledgement', async () => {
		const onsuccess = vi.fn();
		render(VolumeBackupModal, { volume: available, onclose: vi.fn(), onsuccess });
		expect(screen.queryByRole('checkbox', { name: 'backupForce.enable' })).toBeNull();
		await fireEvent.click(inlineSubmit());
		await waitFor(() => expect(onsuccess).toHaveBeenCalledOnce());
	});
});

describe('backup-list source consent', () => {
	async function selectSource(id: string) {
		await fireEvent.change(screen.getByRole('combobox'), { target: { value: id } });
		await fireEvent.input(screen.getByRole('textbox', { name: 'backupCreateModal.nameLabel' }), { target: { value: 'Daily backup' } });
	}

	it('requires consent for an attached selection before the create callback can run', async () => {
		const onCreate = vi.fn().mockResolvedValue(true);
		render(VolumeBackupCreateModal, { open: true, volumes: [attached], onCreate });
		await selectSource(attached.id);
		expect(selectorSubmit().disabled).toBe(true);
		await fireEvent.click(selectorSubmit());
		expect(onCreate).not.toHaveBeenCalled();
		await fireEvent.click(consent());
		expect(selectorSubmit().disabled).toBe(false);
		await fireEvent.click(selectorSubmit());
		await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
	});

	it('requires new consent after changing attached source or closing and reopening', async () => {
		const props = { volumes: [attached, otherAttached], onCreate: vi.fn().mockResolvedValue(true) };
		const view = render(VolumeBackupCreateModal, { open: true, ...props });
		await selectSource(attached.id);
		await fireEvent.click(consent());
		await selectSource(otherAttached.id);
		expect(consent().checked).toBe(false);
		expect(selectorSubmit().disabled).toBe(true);
		await fireEvent.click(consent());
		await view.rerender({ open: false, ...props });
		await view.rerender({ open: true, ...props });
		await selectSource(otherAttached.id);
		expect(consent().checked).toBe(false);
		expect(selectorSubmit().disabled).toBe(true);
		expect(props.onCreate).not.toHaveBeenCalled();
	});

	it('does not carry the attached consent into an available selection', async () => {
		const onCreate = vi.fn().mockResolvedValue(true);
		render(VolumeBackupCreateModal, { open: true, volumes: [attached, { ...available, id: 'disk-c' }], onCreate });
		await selectSource(attached.id);
		await fireEvent.click(consent());
		await selectSource('disk-c');
		expect(screen.queryByRole('checkbox', { name: 'backupForce.enable' })).toBeNull();
		await fireEvent.click(selectorSubmit());
		await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
	});
});
