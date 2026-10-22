import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';

const media = vi.hoisted(() => {
	const events = new EventTarget();
	const query = { matches: true, media: '(min-width: 1024px)', onchange: null,
		addEventListener: events.addEventListener.bind(events), removeEventListener: events.removeEventListener.bind(events),
		dispatchEvent: events.dispatchEvent.bind(events), addListener: () => {}, removeListener: () => {} };
	vi.stubGlobal('matchMedia', () => query);
	return query;
});
vi.mock('$lib/stores/projectNames', () => ({ projectNames: writable(new Map<string, string>()) }));

import AdminVolumeTable from '../AdminVolumeTable.svelte';
import { initLocale } from '$lib/i18n/runtime.svelte';
import type { AdminVolume } from '$lib/types/volume';

const volume: AdminVolume = {
	id: 'native-volume-full-id', name: 'Dataset', status: 'available', size: 200, volume_type: 'fast',
	project_id: 'native-project-full-id', project_name: 'Native project', domain_id: 'native-domain-full-id', domain_name: 'Research', owner_status: 'known', created_at: '2026-10-21',
};

beforeEach(() => { media.matches = true; initLocale('ko'); });
afterEach(() => { cleanup(); initLocale('ko'); });

describe('administrator volume ownership and responsive detail access', () => {
	it('preserves selection and detail/action callbacks across desktop and compact cards without hiding native IDs', async () => {
		const props = {
			volumes: [volume], selectedVolumeId: null, openActionMenu: null, copiedProjectId: null,
			selectedIds: new Set([volume.id]), selectableIds: new Set([volume.id]),
			onSelect: vi.fn(), onToggleSelect: vi.fn(), onToggleAll: vi.fn(), onActionMenuOpen: vi.fn(), onActionMenuClose: vi.fn(), onCopyProjectId: vi.fn(),
			onEdit: vi.fn(), onExtend: vi.fn(), onTransfer: vi.fn(), onReset: vi.fn(), onForceDelete: vi.fn(), onDelete: vi.fn(), onBootFromVolume: vi.fn(),
		};
		render(AdminVolumeTable, props);
		await fireEvent.click(screen.getByRole('button', { name: 'Dataset' }));
		expect(props.onSelect).toHaveBeenCalledWith(volume.id);
		media.matches = false; media.dispatchEvent(new Event('change'));
		await waitFor(() => expect(screen.getAllByRole('article')).toHaveLength(1));
		expect((screen.getByRole('checkbox', { name: 'Dataset 선택' }) as HTMLInputElement).checked).toBe(true);
		expect(screen.getByText('200 GiB · fast')).toBeTruthy();
		expect(screen.getByText('Research · Native project')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: 'Dataset' }));
		expect(props.onSelect).toHaveBeenCalledTimes(2);
		const disclosure = screen.getByText('상세 정보', { selector: 'summary' });
		await fireEvent.click(disclosure);
		expect(screen.getByText(volume.id)).toBeTruthy();
		expect(screen.getByText(`소유 도메인: ${volume.domain_id}`)).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: volume.project_id! }));
		expect(props.onCopyProjectId).toHaveBeenCalledExactlyOnceWith(volume.project_id);
		await fireEvent.click(screen.getByRole('button', { name: 'Dataset 볼륨 작업' }));
		expect(props.onActionMenuOpen).toHaveBeenCalledExactlyOnceWith(volume.id);
		media.matches = true; media.dispatchEvent(new Event('change'));
		await waitFor(() => expect(screen.queryAllByRole('article')).toHaveLength(0));
		expect((screen.getByRole('checkbox', { name: 'Dataset 선택' }) as HTMLInputElement).checked).toBe(true);
		expect(props.onToggleSelect).not.toHaveBeenCalled();
	});
});
