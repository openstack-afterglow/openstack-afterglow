import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import type { FileStorage } from '$lib/types/fileStorage';

const mocks = vi.hoisted(() => ({
	status: null as number | null,
	refresh: undefined as (() => Promise<void>) | undefined,
	metadata: { private: 'sensitive-value' } as Record<string, string>,
	delete: vi.fn(),
}));

vi.mock('$lib/stores/auth', () => ({
	auth: { subscribe(run: (value: object) => void) { run({ token: 'token', projectId: 'project-a', userId: 'user-a' }); return () => {}; } },
}));
vi.mock('$lib/stores/authDisplayContext', () => ({
	authDisplayContext: { subscribe(run: (value: { key: string }) => void) { run({ key: 'logical-owner-a' }); return () => {}; } },
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh(refresh: () => Promise<void>) {
		mocks.refresh = refresh;
		return { active: false, intervalSeconds: 15, intervalOptions: [10, 15, 30, 60] };
	},
}));
vi.mock('$lib/utils/experience', () => ({
	beginExperienceAction: vi.fn(), beginExperienceLoad: vi.fn(),
	experienceRequest: () => ({}), experienceState: vi.fn(), experienceApplied: vi.fn(async () => {}),
}));
vi.mock('$lib/api/client', () => {
	class ApiError extends Error {
		constructor(public status: number, message: string) { super(message); }
	}
	const api = {
		withExperience() { return api; },
		get: vi.fn(async (path: string) => {
			if (path.endsWith('/access-rules')) return [{ id: 'rule-a', access_to: 'client-a', access_level: 'ro', state: 'active', access_key: 'private-access-key' }];
			if (mocks.status !== null) throw new ApiError(mocks.status, `denied-${mocks.status}`);
			return { ...storage, metadata: { ...mocks.metadata } };
		}),
		delete: mocks.delete,
		post: vi.fn(),
	};
	return { api, ApiError };
});

import FileStorageDetailPanel from '$lib/components/FileStorageDetailPanel.svelte';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/file-storage';

import { t as commonT } from '$lib/i18n/ns/common';
const storage: FileStorage = {
	id: 'share-a', name: 'private-share', status: 'available', size: 10, share_proto: 'CEPHFS',
	export_locations: [], metadata: { private: 'sensitive-value' }, project_id: 'project-a',
	created_at: null, is_public: false, library_name: null, library_version: null, built_at: null,
	progress: null, user_id: 'user-a', user_name: null, access_rules_status: 'active', host: null,
	availability_zone: null, share_type_name: null, share_network_id: null, export_location_details: [],
};

beforeEach(() => { mocks.status = null; mocks.refresh = undefined; mocks.metadata = { private: 'sensitive-value' }; mocks.delete.mockClear(); initLocale('ko'); });
afterEach(cleanup);

describe('file storage detail error content gate', () => {
	it.each([401, 403, 503])('hides stale content/actions after %s and retains searches for recovery', async (status) => {
		render(FileStorageDetailPanel, { fileStorageId: 'share-a' });
		await screen.findByText('sensitive-value');
		const searches = screen.getAllByRole('searchbox');
		await fireEvent.input(searches[0], { target: { value: '^client-a$' } });
		await fireEvent.input(searches[1], { target: { value: '^private$' } });
		await fireEvent.click(screen.getByRole('button', { name: commonT('table.sortColumn', { column: t('accessRules.target'), direction: commonT('table.none') }) }));
		const filterName = commonT('table.filterColumn', { column: t('accessRules.target') });
		await fireEvent.click(screen.getByRole('button', { name: filterName }));
		const filterDialog = screen.getByRole('dialog', { name: filterName });
		await fireEvent.click(within(filterDialog).getByRole('button', { name: commonT('table.selectNone') }));
		await fireEvent.click(within(filterDialog).getByRole('button', { name: commonT('actions.close') }));
		mocks.status = status;
		await mocks.refresh!();
		await screen.findByText(new RegExp(`denied-${status}`));
		expect(screen.queryByText('sensitive-value')).toBeNull();
		expect(screen.queryByText('client-a')).toBeNull();
		expect(screen.queryAllByRole('button', { name: t('actions.delete') })).toHaveLength(0);
		expect(mocks.delete).not.toHaveBeenCalled();
		mocks.status = null;
		await mocks.refresh!();
		await screen.findByText('sensitive-value');
		expect((screen.getAllByRole('searchbox')[0] as HTMLInputElement).value).toBe('^client-a$');
		expect((screen.getAllByRole('searchbox')[1] as HTMLInputElement).value).toBe('^private$');
		expect(screen.getByRole('button', { name: commonT('table.sortColumn', { column: t('accessRules.target'), direction: commonT('table.ascending') }) })).toBeTruthy();
		expect(screen.queryByText('client-a')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: filterName }));
		await fireEvent.click(within(screen.getByRole('dialog', { name: filterName })).getByRole('button', { name: commonT('table.resetFilter') }));
		await screen.findByRole('cell', { name: 'client-a' });
	});

	it('distinguishes an empty metadata source from a nonempty source excluded by retained conditions', async () => {
		render(FileStorageDetailPanel, { fileStorageId: 'share-a' });
		await screen.findByText('sensitive-value');
		const metadataRegion = () => within(screen.getByRole('heading', { name: t('metadata.title') }).parentElement!);
		await fireEvent.input(metadataRegion().getByRole('searchbox'), { target: { value: '^absent$' } });
		expect(metadataRegion().getByText(commonT('table.noMatches'))).toBeTruthy();
		mocks.metadata = {};
		await mocks.refresh!();
		expect(metadataRegion().getByText(commonT('table.missing'))).toBeTruthy();
		expect(metadataRegion().queryByText(commonT('table.noMatches'))).toBeNull();
		expect((metadataRegion().getByRole('searchbox') as HTMLInputElement).value).toBe('^absent$');
		await fireEvent.input(metadataRegion().getByRole('searchbox'), { target: { value: '' } });
		await fireEvent.click(metadataRegion().getByRole('button', { name: commonT('table.sortColumn', { column: commonT('table.key'), direction: commonT('table.none') }) }));
		expect(metadataRegion().getByText(commonT('table.missing'))).toBeTruthy();
		expect(metadataRegion().queryByText(commonT('table.noMatches'))).toBeNull();
	});
});