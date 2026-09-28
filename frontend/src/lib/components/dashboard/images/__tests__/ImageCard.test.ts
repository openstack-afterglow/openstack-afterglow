import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import type { ImageInfo } from '$lib/types/compute';
import ImageCard from '../ImageCard.svelte';

const image: ImageInfo = {
	id: 'image-1', name: 'ubuntu-image:latest', repository: 'ubuntu-image', tag: 'latest',
	status: 'active', owner: 'project-1', size: 1024,
};
function renderCard(overrides: Partial<{
	img: ImageInfo;
	current: boolean;
	selectable: boolean;
	selected: boolean;
	onSelect: (id: string) => void;
	onToggleSelect: () => void;
	onEdit: (img: ImageInfo) => void;
	onDelete: (id: string, name: string) => void;
}> = {}) {
	return render(ImageCard, {
		img: image,
		current: true,
		isOwner: true,
		toggling: false,
		deleting: false,
		selectable: true,
		selected: false,
		selectionDisabled: false,
		onSelect: vi.fn(),
		onToggleSelect: vi.fn(),
		onToggleActivation: vi.fn(),
		onEdit: vi.fn(),
		onDelete: vi.fn(),
		...overrides,
	});
}

describe('ImageCard selection', () => {
	it('isolates checkbox click and keyboard activation from the detail button', async () => {
		const onSelect = vi.fn();
		const onToggleSelect = vi.fn();
		renderCard({ onSelect, onToggleSelect });
		const checkbox = screen.getByRole('checkbox', { name: 'ubuntu-image:latest 선택' });

		await fireEvent.click(checkbox.closest('label')!);
		checkbox.focus();
		await fireEvent.keyDown(checkbox, { key: 'Enter' });
		expect(onToggleSelect).toHaveBeenCalledOnce();
		expect(onSelect).not.toHaveBeenCalled();
	});

	it('shows a disabled checkbox for an image outside the current project', () => {
		renderCard({ selectable: false });
		expect((screen.getByRole('checkbox', { name: 'ubuntu-image:latest 선택' }) as HTMLInputElement).disabled).toBe(true);
	});
	it('shows the implicit latest tag when the API omits legacy tag fields', () => {
		renderCard({ img: { ...image, tag: undefined } });
		expect(screen.getByText('latest')).toBeTruthy();
	});
	it('parses a nonlatest tag from legacy image names for selection', async () => {
		const onSelect = vi.fn();
		renderCard({ img: { ...image, name: 'ubuntu-image:24.04', repository: undefined, tag: undefined }, onSelect });
		expect(screen.getByText('24.04')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: /ubuntu-image.*24.04/ }));
		expect(onSelect).toHaveBeenCalledWith(image.id);
	});
	it('keeps verification distinct from public visibility and preserves owner actions', async () => {
		const onSelect = vi.fn();
		const onEdit = vi.fn();
		const onDelete = vi.fn();
		renderCard({ img: { ...image, verification_status: 'unavailable', visibility: 'public', tag: 'very-long-tag' }, onSelect, onEdit, onDelete });
		expect(screen.getByText('검증 불가')).toBeTruthy();
		expect(screen.getByText('공개')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: '편집' }));
		await fireEvent.click(screen.getByRole('button', { name: '삭제' }));
		await fireEvent.click(screen.getByRole('button', { name: /ubuntu-image.*very-long-tag/ }));
		expect(onEdit).toHaveBeenCalledWith(expect.objectContaining({ id: image.id }));
		expect(onDelete).toHaveBeenCalledWith(image.id, image.name);
		expect(onSelect).toHaveBeenCalledWith(image.id);
	});

	it('keeps a historical upload distinguishable and sends its concrete ID to detail and owner actions', async () => {
		const previous = { ...image, id: 'older-uuid-5678', os_hash_algo: 'sha512', os_hash_value: 'b'.repeat(128) };
		const onSelect = vi.fn();
		const onEdit = vi.fn();
		const onDelete = vi.fn();
		renderCard({ img: previous, current: false, onSelect, onEdit, onDelete });
		expect(screen.getByText('이전')).toBeTruthy();
		expect(screen.getByLabelText(`SHA-512: ${'b'.repeat(128)}`)).toBeTruthy();
		expect(screen.getByLabelText(`이미지 ID: ${previous.id}`)).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: /ubuntu-image.*latest/ }));
		await fireEvent.click(screen.getByRole('button', { name: '편집' }));
		await fireEvent.click(screen.getByRole('button', { name: '삭제' }));
		expect(onSelect).toHaveBeenCalledWith(previous.id);
		expect(onEdit).toHaveBeenCalledWith(previous);
		expect(onDelete).toHaveBeenCalledWith(previous.id, previous.name);
	});

	it('treats legacy images without verification status as unverified, not as private', () => {
		renderCard({ img: { ...image, visibility: 'shared' } });
		expect(screen.getByText('미검증')).toBeTruthy();
		expect(screen.getByText('공유')).toBeTruthy();
	});
});
