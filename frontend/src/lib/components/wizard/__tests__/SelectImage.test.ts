import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import type { ImageInfo } from '$lib/types/compute';
import SelectImage from '../SelectImage.svelte';

const images: ImageInfo[] = [
	{
		id: 'ubuntu-2204',
		name: 'ubuntu:22.04',
		repository: 'ubuntu',
		tag: '22.04',
		status: 'active',
		os_distro: 'ubuntu',
	},
	{
		id: 'ubuntu-2404',
		name: 'ubuntu:24.04',
		repository: 'ubuntu',
		tag: '24.04',
		status: 'active',
		os_distro: 'ubuntu',
	},
	{
		id: 'fedora-40',
		name: 'fedora:40',
		repository: 'fedora',
		tag: '40',
		status: 'active',
		os_distro: 'fedora',
	},
];

const older = {
	...images[0], id: 'older-ubuntu', tag: 'latest', name: 'ubuntu:latest',
	created_at: '2026-01-01T12:00:00.123456Z', os_hash_algo: 'sha256', os_hash_value: 'a'.repeat(64),
};
const newer = {
	...older, id: 'newer-ubuntu', created_at: '2026-01-01T12:00:00.123457Z',
	os_hash_value: 'b'.repeat(64),
};

function renderSelector(onSelect = vi.fn()) {
	return { onSelect, ...render(SelectImage, { images, selectedId: null, onSelect }) };
}

describe('SelectImage', () => {
	it('opens filtering on demand and searches canonical image names and tags', async () => {
		const { onSelect } = renderSelector();

		const filterButton = screen.getByRole('button', { name: '필터' });
		expect(filterButton.getAttribute('aria-expanded')).toBe('false');
		expect(screen.queryByRole('searchbox', { name: '이미지 이름, tag, OS 검색' })).toBeNull();

		await fireEvent.click(filterButton);
		expect(filterButton.getAttribute('aria-expanded')).toBe('true');
		const search = screen.getByRole('searchbox', { name: '이미지 이름, tag, OS 검색' });
		await fireEvent.input(search, { target: { value: '24.04' } });

		expect(screen.getByRole('button', { name: 'ubuntu:24.04 이미지 선택' })).toBeTruthy();
		expect(screen.queryByRole('button', { name: 'ubuntu:22.04 이미지 선택' })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'ubuntu:24.04 이미지 선택' }));
		expect(onSelect).toHaveBeenCalledWith('ubuntu-2404', 'ubuntu:24.04');
	});

	it('filters the image grid by OS family before selecting a tag', async () => {
		renderSelector();

		await fireEvent.click(screen.getByRole('button', { name: '필터' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Fedora 1' }));
		expect(screen.getByRole('button', { name: 'fedora:40 이미지 선택' })).toBeTruthy();
		expect(screen.queryByRole('button', { name: 'ubuntu:22.04 이미지 선택' })).toBeNull();
		expect(screen.queryByRole('button', { name: 'ubuntu:24.04 이미지 선택' })).toBeNull();
	});

	it('keeps the source image name for version-aware library validation', async () => {
		const onSelect = vi.fn();
		render(SelectImage, {
			images: [{
				...images[0],
				id: 'ubuntu-raw-name',
				name: 'ubuntu-24.04-server',
				tag: 'latest',
			}],
			selectedId: null,
			onSelect,
		});

		expect(screen.getByText('Ubuntu 24.04 LTS')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: 'ubuntu:latest 이미지 선택' }));
		expect(onSelect).toHaveBeenCalledWith('ubuntu-raw-name', 'ubuntu-24.04-server');
	});

	it('normalizes legacy names when repository and tag fields are absent', async () => {
		const onSelect = vi.fn();
		render(SelectImage, {
			images: [{ ...images[0], id: 'legacy-ubuntu', name: 'ubuntu', repository: undefined, tag: undefined }],
			selectedId: null,
			onSelect,
		});

		const card = screen.getByRole('button', { name: 'ubuntu:latest 이미지 선택' });
		expect(card).toBeTruthy();
		await fireEvent.click(card);
		expect(onSelect).toHaveBeenCalledWith('legacy-ubuntu', 'ubuntu:latest');
	});

	it('blocks an older active upload when the newest upload is saving, even after filtering', async () => {
		const onSelect = vi.fn();
		render(SelectImage, {
			images: [{ ...older, os_distro: 'fedora' }, { ...newer, status: 'saving', os_hash_value: null }, images[2]],
			selectedId: null, onSelect,
		});

		const saving = screen.getByRole('button', { name: 'ubuntu:latest 이미지 선택 불가 (saving)' });
		expect(saving.hasAttribute('disabled')).toBe(true);
		expect(within(saving).getByText('현재 · saving')).toBeTruthy();
		expect(within(saving).getByText('해시 계산 중')).toBeTruthy();
		expect(within(saving).getByLabelText(`이미지 ID: ${newer.id}`)).toBeTruthy();
		expect(screen.queryByRole('button', { name: 'ubuntu:latest 이미지 선택' })).toBeNull();
		(saving as HTMLButtonElement).click();
		expect(onSelect).not.toHaveBeenCalled();

		await fireEvent.click(screen.getByRole('button', { name: '필터' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Fedora 1' }));
		expect(screen.queryByRole('button', { name: /ubuntu:latest 이미지 선택/ })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'Ubuntu 1' }));
		const search = screen.getByRole('searchbox', { name: '이미지 이름, tag, OS 검색' });
		await fireEvent.input(search, { target: { value: 'latest' } });
		expect(screen.getByRole('button', { name: 'ubuntu:latest 이미지 선택 불가 (saving)' })).toBeTruthy();
		expect(onSelect).not.toHaveBeenCalled();
	});

	it('uses the microsecond upload order for the single current tag and selects its UUID', async () => {
		const onSelect = vi.fn();
		render(SelectImage, { images: [older, { ...newer, updated_at: '2027-02-01T00:00:00Z' }], selectedId: null, onSelect });

		const card = screen.getByRole('button', { name: 'ubuntu:latest 이미지 선택' });
		expect(screen.getAllByRole('button', { name: 'ubuntu:latest 이미지 선택' })).toHaveLength(1);
		expect(within(card).getByLabelText(`이미지 ID: ${newer.id}`)).toBeTruthy();
		expect(within(card).getByText('2026-01-01')).toBeTruthy();
		expect(within(card).queryByText('2027-02-01')).toBeNull();
		await fireEvent.click(card);
		expect(onSelect).toHaveBeenCalledWith(newer.id, 'ubuntu:latest');
	});

	it('keeps a historical selection explicit until a current UUID is chosen', async () => {
		const onSelect = vi.fn();
		render(SelectImage, { images: [older, newer], selectedId: older.id, onSelect });

		const previous = screen.getByRole('region', { name: '이전에 선택한 이미지' });
		expect(within(previous).getByText(/이전에 선택한 이미지 · 현재 tag 이미지와 다릅니다/)).toBeTruthy();
		expect(within(previous).getByLabelText(`이전에 선택한 이미지 ID: ${older.id}`)).toBeTruthy();
		expect(within(previous).getByLabelText(`SHA-256: ${older.os_hash_value}`)).toBeTruthy();
		const current = screen.getByRole('button', { name: 'ubuntu:latest 이미지 선택' });
		expect(within(current).getByLabelText(`SHA-256: ${newer.os_hash_value}`)).toBeTruthy();
		expect(within(current).getByLabelText(`이미지 ID: ${newer.id}`)).toBeTruthy();
		expect(onSelect).not.toHaveBeenCalled();
		await fireEvent.click(current);
		expect(onSelect).toHaveBeenCalledTimes(1);
		expect(onSelect).toHaveBeenCalledWith(newer.id, 'ubuntu:latest');
	});

	it('retains the UUID of a selected image absent from the loaded list', () => {
		const onSelect = vi.fn();
		render(SelectImage, { images: [newer], selectedId: 'previous-unlisted-uuid', onSelect });
		const previous = screen.getByRole('region', { name: '이전에 선택한 이미지' });
		expect(within(previous).getByText('선택한 이미지가 목록에 없습니다.')).toBeTruthy();
		expect(within(previous).getByLabelText('이전에 선택한 이미지 ID: previous-unlisted-uuid')).toBeTruthy();
		expect(onSelect).not.toHaveBeenCalled();
	});
});
