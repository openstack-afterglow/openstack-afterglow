import { api, ApiError } from '$lib/api/client';
import { t } from '$lib/i18n/ns/admin-system';
import { domainsApi, domainPath } from '$lib/api/domains';
import type { AdminDomain } from '$lib/api/domains';
import { t as td } from '$lib/i18n/ns/domain-admin';
import type {
	AnnouncementAdmin,
	AnnouncementCreatePayload,
	AnnouncementOptions,
} from '$lib/types/announcements';

export interface AdminAnnouncementsControllerOpts {
	token: () => string | undefined;
	projectId: () => string | undefined;
}

interface PickerUser {
	id: string;
	name: string;
	domain_id: string;
}

interface PickerProject {
	id: string;
	name: string;
}

export function createAdminAnnouncementsController(opts: AdminAnnouncementsControllerOpts) {
	let announcements = $state<AnnouncementAdmin[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let error = $state('');

	let options = $state<AnnouncementOptions | null>(null);
	let allUsers = $state<PickerUser[]>([]);
	let allProjects = $state<PickerProject[]>([]);
	let usersLoading = $state(false);
	let usersError = $state('');
	let projectsLoading = $state(false);
	let projectsError = $state('');
	let domains = $state<AdminDomain[]>([]);
	let domainId = $state('');
	let domainsError = $state('');
	let domainsLoading = $state(false);
	let usersGeneration = 0;
	let disposed = false;
	let domainsGeneration = 0;

	let creating = $state(false);
	let createError = $state('');

	let togglingId = $state<number | null>(null);

	let deleteTarget = $state<AnnouncementAdmin | null>(null);
	let deleting = $state(false);
	let deleteError = $state('');

	const tok = opts.token;
	const pid = opts.projectId;

	async function load() {
		if (announcements.length === 0) loading = true;
		else refreshing = true;
		error = '';
		try {
			announcements = await api.get<AnnouncementAdmin[]>('/api/v1/admin/announcements', tok(), pid());
		} catch (e) {
			error = e instanceof ApiError ? e.message : t('announcements.error.loadFailed');
		} finally {
			loading = false;
			refreshing = false;
		}
	}

	async function loadOptions() {
		if (options) return;
		try {
			options = await api.get<AnnouncementOptions>('/api/v1/admin/announcements/meta/options', tok(), pid());
		} catch {
			// 실패해도 폼은 하드코딩된 fallback 없이 비활성 유지 — 재시도는 다음 open에서.
		}
	}

	async function loadDomains() {
		const generation = ++domainsGeneration;
		const token = tok(), projectId = pid();
		domains = [];
		domainsLoading = true; domainsError = '';
		try {
			const response = await domainsApi.list({ token, projectId });
			if (!disposed && generation === domainsGeneration && token === tok() && projectId === pid()) domains = response.items;
		} catch (e) {
			if (!disposed && generation === domainsGeneration) domainsError = e instanceof ApiError ? e.message : td('scope.loadFailed');
		} finally { if (!disposed && generation === domainsGeneration) domainsLoading = false; }
	}
	function selectDomain(value: string) {
		usersGeneration += 1;
		domainId = domains.some(domain => domain.id === value) ? value : '';
		allUsers = []; usersError = ''; usersLoading = false;
		creating = false; createError = '';
		if (domainId) void loadUsers();
	}
	async function loadUsers() {
		if (!domainId || usersLoading || disposed) return;
		const generation = ++usersGeneration;
		const selectedDomain = domainId, token = tok(), projectId = pid();
		const owns = () => !disposed && generation === usersGeneration && selectedDomain === domainId && token === tok() && projectId === pid();
		usersLoading = true; usersError = ''; allUsers = [];
		try {
			let marker: string | null = null;
			const collected: PickerUser[] = [], seen = new Set<string>();
			do {
				const path = domainPath(`/api/v1/admin/users?limit=100${marker ? `&marker=${encodeURIComponent(marker)}` : ''}`, selectedDomain);
				const response: { items: PickerUser[]; next_marker: string | null } = await api.get(path, token, projectId);
				if (!owns()) return;
				if (response.items.some(user => user.domain_id !== selectedDomain)) throw new Error(td('scope.invalid'));
				collected.push(...response.items);
				marker = response.next_marker;
				if (marker && seen.has(marker)) throw new Error(td('scope.invalid'));
				if (marker) seen.add(marker);
			} while (marker);
			if (owns()) allUsers = collected;
		} catch (e) {
			if (owns()) usersError = e instanceof ApiError ? e.message : t('announcements.error.usersLoadFailed');
		} finally { if (owns()) usersLoading = false; }
	}
	function dispose() { disposed = true; usersGeneration += 1; domainsGeneration += 1; allUsers = []; }

	async function loadProjects() {
		if (allProjects.length > 0 || projectsLoading) return;
		projectsLoading = true;
		projectsError = '';
		try {
			allProjects = await api.get<PickerProject[]>('/api/v1/admin/projects/names', tok(), pid());
		} catch {
			projectsError = t('announcements.error.projectsLoadFailed');
		} finally {
			projectsLoading = false;
		}
	}

	async function create(payload: AnnouncementCreatePayload): Promise<boolean> {
		const selectedDomain = domainId, token = tok(), projectId = pid(), generation = usersGeneration;
		const owns = () => !disposed && token === tok() && projectId === pid() && (payload.target_type !== 'user' || (selectedDomain === domainId && generation === usersGeneration));
		if (payload.target_type === 'user' && (!domainId || !allUsers.some(user => user.id === payload.target_id))) {
			createError = td('scope.required');
			return false;
		}
		creating = true;
		createError = '';
		try {
			await api.post('/api/v1/admin/announcements', payload, token, projectId);
			if (!owns()) return false;
			await load();
			return true;
		} catch (e) {
			if (owns()) createError = e instanceof ApiError ? e.message : t('announcements.error.createFailed');
			return false;
		} finally {
			if (owns()) creating = false;
		}
	}

	async function toggleActive(target: AnnouncementAdmin): Promise<void> {
		togglingId = target.id;
		error = '';
		try {
			await api.patch(`/api/v1/admin/announcements/${target.id}`, { is_active: !target.is_active }, tok(), pid());
			await load();
		} catch (e) {
			error = e instanceof ApiError ? e.message : t('announcements.error.toggleFailed');
		} finally {
			togglingId = null;
		}
	}

	async function confirmDelete(): Promise<void> {
		if (!deleteTarget) return;
		deleting = true;
		deleteError = '';
		try {
			await api.delete(`/api/v1/admin/announcements/${deleteTarget.id}`, tok(), pid());
			deleteTarget = null;
			await load();
		} catch (e) {
			deleteError = e instanceof ApiError ? e.message : t('announcements.error.deleteFailed');
		} finally {
			deleting = false;
		}
	}

	return {
		get announcements() { return announcements; },
		get loading() { return loading; },
		get refreshing() { return refreshing; },
		get error() { return error; },
		get options() { return options; },
		get allUsers() { return allUsers; },
		get allProjects() { return allProjects; },
		get usersLoading() { return usersLoading; },
		get usersError() { return usersError; },
		get projectsLoading() { return projectsLoading; },
		get projectsError() { return projectsError; },
		get domains() { return domains; }, get domainId() { return domainId; },
		get domainsError() { return domainsError; }, get domainsLoading() { return domainsLoading; },
		loadDomains, selectDomain, dispose,
		get creating() { return creating; },
		get createError() { return createError; },
		set createError(v: string) { createError = v; },
		get togglingId() { return togglingId; },
		get deleteTarget() { return deleteTarget; },
		set deleteTarget(v: AnnouncementAdmin | null) { deleteTarget = v; },
		get deleting() { return deleting; },
		get deleteError() { return deleteError; },
		set deleteError(v: string) { deleteError = v; },
		load,
		loadOptions,
		loadUsers,
		loadProjects,
		create,
		toggleActive,
		confirmDelete,
	};
}
