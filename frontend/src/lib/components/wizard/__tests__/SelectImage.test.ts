import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import type { ImageInfo } from '$lib/types/compute';
import SelectImage from '../SelectImage.svelte';
import { t } from '$lib/i18n/ns/vm-wizard';
import { formatDate } from '$lib/utils/format';

const images: ImageInfo[] = [
	{
		id: 'ubuntu-2204',
		name: 'ubuntu:22.04',
		repository: 'ubuntu',
		tag: '22.04',
		status: 'active',
		os_distro: 'ubuntu',
		created_at: '2025-01-01T00:00:00Z',
	},
	{
		id: 'ubuntu-2404',
		name: 'ubuntu:24.04',
		repository: 'ubuntu',
		tag: '24.04',
		status: 'active',
		os_distro: 'ubuntu',
		created_at: '2026-01-01T00:00:00Z',
	},
	{
		id: 'fedora-40',
		name: 'fedora:40',
		repository: 'fedora',
		tag: '40',
		status: 'active',
		os_distro: 'fedora',
		created_at: '2024-01-01T00:00:00Z',
	},
	{
		id: 'waygate-gateway', name: 'waygate-gateway:latest', repository: 'waygate-gateway', tag: 'latest',
		status: 'active', os_distro: 'ubuntu', created_at: '2025-09-01T00:00:00Z',
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

function repositoryButton(repository: string) {
	return screen.getByRole('button', { name: t('image.repositoryLabel', { name: repository }) });
}

function tagButton(name: string) {
	return screen.getByRole('button', { name: t('image.selectLabel', { name }) });
}

function tagPanel(repository: string) {
	return screen.getByRole('region', { name: t('image.tagsTitle', { name: repository }) });
}

function visibleRepositories() {
	return screen.getAllByRole('button').filter(button => button.hasAttribute('aria-expanded') && button.getAttribute('aria-controls') === 'vm-image-tags');
}

describe('SelectImage', () => {
	it('groups tags by repository, not OS, and selects only after a concrete tag is chosen', async () => {
		const { onSelect } = renderSelector();
		expect(visibleRepositories()).toHaveLength(3);
		expect(screen.getAllByRole('button', { name: t('image.repositoryLabel', { name: 'ubuntu' }) })).toHaveLength(1);
		expect(repositoryButton('waygate-gateway')).toBeTruthy();
		expect(screen.queryByRole('region', { name: t('image.tagsTitle', { name: 'ubuntu' }) })).toBeNull();

		await fireEvent.click(repositoryButton('ubuntu'));
		expect(onSelect).not.toHaveBeenCalled();
		expect(repositoryButton('ubuntu').getAttribute('aria-expanded')).toBe('true');
		expect(within(tagPanel('ubuntu')).getAllByRole('button').map(button => button.textContent?.trim())).toEqual([
			expect.stringContaining('24.04'), expect.stringContaining('22.04'),
		]);
		await fireEvent.click(tagButton('ubuntu:24.04'));
		expect(onSelect).toHaveBeenCalledWith('ubuntu-2404', 'ubuntu:24.04');

		await fireEvent.click(repositoryButton('waygate-gateway'));
		expect(screen.queryByRole('region', { name: t('image.tagsTitle', { name: 'ubuntu' }) })).toBeNull();
		await fireEvent.click(tagButton('waygate-gateway:latest'));
		expect(onSelect).toHaveBeenLastCalledWith('waygate-gateway', 'waygate-gateway:latest');
	});

	it('opens filters on demand and searches repositories and tags together', async () => {
		const { onSelect } = renderSelector();
		expect(screen.queryByRole('searchbox')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: t('image.filters.title') }));
		const search = screen.getByRole('searchbox');
		await fireEvent.input(search, { target: { value: 'ubuntu 24.04' } });
		expect(visibleRepositories()).toHaveLength(1);
		await fireEvent.click(repositoryButton('ubuntu'));
		expect(within(tagPanel('ubuntu')).getAllByRole('button')).toHaveLength(1);
		await fireEvent.click(tagButton('ubuntu:24.04'));
		expect(onSelect).toHaveBeenCalledWith('ubuntu-2404', 'ubuntu:24.04');
		await fireEvent.input(search, { target: { value: 'ubuntu' } });
		expect(within(tagPanel('ubuntu')).getAllByRole('button')).toHaveLength(2);
	});

	it('filters by OS while keeping repositories with the same distro distinct', async () => {
		renderSelector();
		await fireEvent.click(screen.getByRole('button', { name: t('image.filters.title') }));
		await fireEvent.click(screen.getByRole('button', { name: 'Ubuntu 2' }));
		expect(visibleRepositories()).toHaveLength(2);
		expect(repositoryButton('ubuntu')).toBeTruthy();
		expect(repositoryButton('waygate-gateway')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: 'Fedora 1' }));
		expect(visibleRepositories()).toHaveLength(1);
		await fireEvent.click(repositoryButton('fedora'));
		expect(tagButton('fedora:40')).toBeTruthy();
	});

	it('keeps the actual source image name for version-aware library validation', async () => {
		const onSelect = vi.fn();
		render(SelectImage, {
			images: [{ ...images[0], id: 'ubuntu-source-name', name: 'ubuntu-24.04-server', tag: 'latest' }],
			selectedId: null, onSelect,
		});
		await fireEvent.click(repositoryButton('ubuntu'));
		await fireEvent.click(tagButton('ubuntu:latest'));
		expect(onSelect).toHaveBeenCalledWith('ubuntu-source-name', 'ubuntu-24.04-server');
	});

	it('normalizes legacy names when repository and tag fields are absent', async () => {
		const onSelect = vi.fn();
		render(SelectImage, {
			images: [{ ...images[0], id: 'legacy-ubuntu', name: 'ubuntu', repository: undefined, tag: undefined }],
			selectedId: null, onSelect,
		});
		await fireEvent.click(repositoryButton('ubuntu'));
		await fireEvent.click(tagButton('ubuntu:latest'));
		expect(onSelect).toHaveBeenCalledWith('legacy-ubuntu', 'ubuntu:latest');
	});

	it('blocks an older active upload when the newest upload is saving, including after filters', async () => {
		const onSelect = vi.fn();
		render(SelectImage, {
			images: [{ ...older, name: 'legacy-upload', os_distro: 'fedora' }, { ...newer, status: 'saving' }, images[2]],
			selectedId: null, onSelect,
		});
		await fireEvent.click(repositoryButton('ubuntu'));
		const disabledName = t('image.unselectableLabel', { name: 'ubuntu:latest', status: 'saving' });
		const saving = screen.getByRole('button', { name: disabledName });
		expect(saving.hasAttribute('disabled')).toBe(true);
		expect(within(saving).getByText(t('image.inactiveReason', { status: 'saving' }))).toBeTruthy();
		(saving as HTMLButtonElement).click();
		expect(onSelect).not.toHaveBeenCalled();

		await fireEvent.click(screen.getByRole('button', { name: t('image.filters.title') }));
		await fireEvent.click(screen.getByRole('button', { name: 'Fedora 1' }));
		expect(screen.queryByRole('button', { name: t('image.repositoryLabel', { name: 'ubuntu' }) })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'Ubuntu 1' }));
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: 'legacy-upload' } });
		expect(visibleRepositories()).toHaveLength(0);
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: 'latest' } });
		expect(screen.getByRole('button', { name: disabledName }).hasAttribute('disabled')).toBe(true);
		expect(onSelect).not.toHaveBeenCalled();
	});

	it.each([false, true])('selects the microsecond-newest upload independent of input order (%s) and updated_at', async reverse => {
		const onSelect = vi.fn();
		const uploads = [{ ...older, updated_at: '2027-02-01T00:00:00Z' }, newer];
		render(SelectImage, { images: reverse ? uploads.reverse() : uploads, selectedId: null, onSelect });
		await fireEvent.click(repositoryButton('ubuntu'));
		expect(within(tagPanel('ubuntu')).getAllByRole('button')).toHaveLength(1);
		expect(within(tagButton('ubuntu:latest')).getByText(formatDate(newer.created_at))).toBeTruthy();
		expect(within(tagButton('ubuntu:latest')).queryByText(formatDate('2027-02-01T00:00:00Z'))).toBeNull();
		await fireEvent.click(tagButton('ubuntu:latest'));
		expect(onSelect).toHaveBeenCalledWith(newer.id, 'ubuntu:latest');
	});

	it('orders repositories and tags by upload time, with unknown dates last rather than latest-tag priority', async () => {
		const onSelect = vi.fn();
		render(SelectImage, {
			images: [
				{ ...images[0], id: 'unknown-repository', name: 'unknown:latest', repository: 'unknown', tag: 'latest', created_at: null, updated_at: '2028-01-01T00:00:00Z' },
				{ ...images[0], id: 'unknown-tag', name: 'ubuntu:latest', tag: 'latest', created_at: 'invalid-date', updated_at: '2028-01-01T00:00:00Z' },
				images[2], images[0], images[3], images[1],
			],
			selectedId: null, onSelect,
		});
		expect(visibleRepositories().map(button => button.getAttribute('aria-label'))).toEqual(
			['ubuntu', 'waygate-gateway', 'fedora', 'unknown'].map(name => t('image.repositoryLabel', { name })),
		);
		await fireEvent.click(repositoryButton('ubuntu'));
		expect(within(tagPanel('ubuntu')).getAllByRole('button').map(button => button.getAttribute('aria-label'))).toEqual(
			['24.04', '22.04', 'latest'].map(tag => t('image.selectLabel', { name: `ubuntu:${tag}` })),
		);
	});

	it('omits technical identity, active/current status, and disk-format clutter from normal choices', async () => {
		render(SelectImage, { images: [{ ...newer, disk_format: 'raw', size: 1024 ** 3 }], selectedId: null, onSelect: vi.fn() });
		await fireEvent.click(repositoryButton('ubuntu'));
		for (const choice of [repositoryButton('ubuntu'), tagPanel('ubuntu')]) {
			for (const value of [newer.id, newer.os_hash_value, 'SHA-', 'active', 'raw']) {
				expect(choice.textContent).not.toContain(value);
			}
		}
		expect(within(tagPanel('ubuntu')).getByText(/GB/)).toBeTruthy();
	});

	it('preserves the chosen UUID and open repository across a refresh without substituting newer uploads', async () => {
		const onSelect = vi.fn();
		const { rerender } = render(SelectImage, { images: [older], selectedId: older.id, onSelect });
		expect(tagButton('ubuntu:latest').getAttribute('aria-pressed')).toBe('true');
		await rerender({ images: [newer, older], selectedId: older.id, onSelect });
		const previous = screen.getByRole('region', { name: t('image.previous.label') });
		expect(within(previous).getByLabelText(t('image.previous.idLabel', { id: older.id }))).toBeTruthy();
		expect(tagButton('ubuntu:latest').getAttribute('aria-pressed')).toBe('false');
		expect(onSelect).not.toHaveBeenCalled();
		await fireEvent.click(tagButton('ubuntu:latest'));
		expect(onSelect).toHaveBeenCalledTimes(1);
		expect(onSelect).toHaveBeenCalledWith(newer.id, 'ubuntu:latest');
		await rerender({ images: [older, newer], selectedId: newer.id, onSelect });
		expect(screen.queryByRole('region', { name: t('image.previous.label') })).toBeNull();
		expect(tagButton('ubuntu:latest').getAttribute('aria-pressed')).toBe('true');
	});

	it('shows a historical UUID warning on initial load until an explicit current choice', async () => {
		const onSelect = vi.fn();
		render(SelectImage, { images: [older, newer], selectedId: older.id, onSelect });
		const previous = screen.getByRole('region', { name: t('image.previous.label') });
		expect(within(previous).getByText(t('image.previous.title'))).toBeTruthy();
		expect(within(previous).getByLabelText(t('image.previous.idLabel', { id: older.id }))).toBeTruthy();
		expect(onSelect).not.toHaveBeenCalled();
		await fireEvent.click(tagButton('ubuntu:latest'));
		expect(onSelect).toHaveBeenCalledWith(newer.id, 'ubuntu:latest');
	});

	it('retains a missing selected UUID across empty and restored refreshes', async () => {
		const onSelect = vi.fn();
		const selectedId = 'previous-unlisted-uuid';
		const { rerender } = render(SelectImage, { images: [newer], selectedId, onSelect });
		await fireEvent.click(repositoryButton('ubuntu'));
		await rerender({ images: [], selectedId, onSelect });
		const previous = screen.getByRole('region', { name: t('image.previous.label') });
		expect(within(previous).getByText(t('image.previous.missing'))).toBeTruthy();
		expect(within(previous).getByLabelText(t('image.previous.idLabel', { id: selectedId }))).toBeTruthy();
		await rerender({ images: [newer], selectedId, onSelect });
		expect(tagPanel('ubuntu')).toBeTruthy();
		expect(tagButton('ubuntu:latest').getAttribute('aria-pressed')).toBe('false');
		expect(onSelect).not.toHaveBeenCalled();
	});
});
