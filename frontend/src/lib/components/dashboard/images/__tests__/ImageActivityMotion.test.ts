import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
const { patch } = vi.hoisted(() => ({ patch: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: { patch }, ApiError: class ApiError extends Error {} }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'project-a' }) }));
import ImageCard from '../ImageCard.svelte';
import ImageEditModal from '../ImageEditModal.svelte';
import ImageDistroFilter from '../ImageDistroFilter.svelte';
import { t } from '$lib/i18n/ns/images-keys';

const image = { id: 'image-a', name: 'ubuntu:latest', status: 'active', min_disk: 0, min_ram: 0 };
beforeEach(() => vi.clearAllMocks());

describe('image catalog activity feedback', () => {
	it('retains operational status while an owner activation request is pending', async () => {
		const onToggleActivation = vi.fn();
		const props = { img: image, current: true, isOwner: true, toggling: false, deleting: false,
			onSelect: vi.fn(), onToggleSelect: vi.fn(), onToggleActivation, onEdit: vi.fn(), onDelete: vi.fn() };
		const view = render(ImageCard, props);
		const card = screen.getByRole('article');
		const activation = within(card).getByRole('button', { name: '비활성화' }) as HTMLButtonElement;
		const deletion = within(card).getByRole('button', { name: '삭제' }) as HTMLButtonElement;
		expect(activation.disabled).toBe(false);
		expect(card.getAttribute('aria-busy')).toBe('false');
		expect(within(card).queryByRole('status')).toBeNull();
		await fireEvent.click(activation);
		expect(onToggleActivation).toHaveBeenCalledExactlyOnceWith(image);

		await view.rerender({ ...props, toggling: true });
		expect(activation.disabled).toBe(true);
		expect(card.getAttribute('aria-busy')).toBe('true');
		expect(within(activation).getByRole('status').textContent?.trim()).toBe(t('imageCard.toggling'));
		expect(within(card).getAllByRole('status')).toHaveLength(1);
		expect(within(card).getByText('active')).toBeTruthy();
		expect(deletion.disabled).toBe(false);
		expect(within(deletion).queryByRole('status')).toBeNull();

		await view.rerender({ ...props, img: { ...image, status: 'deactivated' } });
		expect(within(card).getByRole('button', { name: '활성화' })).toBe(activation);
		expect(activation.disabled).toBe(false);
		expect(card.getAttribute('aria-busy')).toBe('false');
		expect(within(card).queryByRole('status')).toBeNull();
		expect(within(card).getByText('deactivated')).toBeTruthy();
		expect(onToggleActivation).toHaveBeenCalledOnce();

		await view.rerender(props);
		expect(card.getAttribute('aria-busy')).not.toBe('true');
		expect(activation.disabled).toBe(false);
		expect(within(card).queryByRole('status')).toBeNull();
		expect(within(card).getByText(image.status)).toBeTruthy();
	});

	it('shows edit-save feedback until the real metadata request resolves', async () => {
		let resolve!: (value: typeof image) => void;
		patch.mockReturnValue(new Promise<typeof image>((done) => { resolve = done; }));
		const onClose = vi.fn();
		const onSaved = vi.fn();
		render(ImageEditModal, { props: { target: image, onClose, onSaved } });
		const dialog = screen.getByRole('dialog');
		const save = within(dialog).getByRole('button', { name: '저장' }) as HTMLButtonElement;
		expect(save.disabled).toBe(false);
		expect(within(dialog).queryByRole('status')).toBeNull();
		await fireEvent.input(within(dialog).getByRole('textbox', { name: /이름/ }), { target: { value: 'ubuntu:24.04' } });
		await fireEvent.click(save);
		expect(patch).toHaveBeenCalledExactlyOnceWith('/api/v1/images/image-a', { name: 'ubuntu:24.04' }, 'token', 'project-a');
		expect(save.disabled).toBe(true);
		expect(within(save).getByRole('status').textContent?.trim()).toBeTruthy();
		expect(onSaved).not.toHaveBeenCalled();
		expect(onClose).not.toHaveBeenCalled();
		const updated = { ...image, name: 'ubuntu:24.04' };
		resolve(updated);
		await waitFor(() => expect(save.disabled).toBe(false));
		expect(within(dialog).getByRole('button', { name: '저장' })).toBe(save);
		expect(within(dialog).queryByRole('status')).toBeNull();
		expect(onSaved).toHaveBeenCalledExactlyOnceWith(updated);
		expect(onClose).toHaveBeenCalledOnce();
		expect(onSaved.mock.invocationCallOrder[0]).toBeLessThan(onClose.mock.invocationCallOrder[0]);
	});

	it('keeps distro counts and filter controls stable during a count refresh', async () => {
		const view = render(ImageDistroFilter, { distroFilter: 'all', counts: { all: 2, ubuntu: 2 } });
		const button = screen.getByRole('button', { name: /^Ubuntu\s*\(\s*2\s*\)$/ });
		await view.rerender({ distroFilter: 'all', counts: { all: 3, ubuntu: 3 } });
		expect(screen.getByRole('button', { name: /^Ubuntu\s*\(\s*3\s*\)$/ })).toBe(button);
		expect(screen.getByRole('button', { name: /^전체\s*\(\s*3\s*\)$/ })).toBeTruthy();
		expect((button as HTMLButtonElement).disabled).toBe(false);
	});
});
