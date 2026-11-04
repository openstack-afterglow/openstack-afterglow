import { api, ApiError } from '$lib/api/client';
import { t } from '$lib/i18n/ns/admin-system';
import { domainsApi, domainPath } from '$lib/api/domains';
import type { AdminDomain } from '$lib/api/domains';
import { t as td } from '$lib/i18n/ns/domain-admin';
import { mailDispatchFailure } from '$lib/api/email';
import { t as tm } from '$lib/i18n/ns/admin-email';
import { beginExperienceAction, beginExperienceLoad, experienceState, experienceApplied, experienceDiscarded, type ExperienceContext } from '$lib/utils/experience';

import type {
	AnnouncementAdmin,
	AnnouncementCreatePayload,
	AnnouncementOptions,
} from '$lib/types/announcements';
export type AnnouncementCreateResult = { status: 'ok' | 'invalid' | 'rejected' | 'indeterminate' };

export interface AdminAnnouncementsControllerOpts {
	token: () => string | undefined;
	projectId: () => string | undefined;
	ownerKey?: () => string;
	ownerEpoch?: () => number;
	allowed?: () => boolean;
}

interface PickerUser {
	id: string;
	name: string;
	domain_id: string;
}

interface PickerProject {
	id: string;
	name: string;
	domain_id: string;
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
	let projectsGeneration = 0;
	let disposed = false;
	let domainsGeneration = 0;
	let loadGeneration = 0;

	let creating = $state(false);
	let createError = $state('');
	let emailOperation = $state<AnnouncementAdmin['email_operation']>(null);

	let togglingId = $state<number | null>(null);

	let deleteTarget = $state<AnnouncementAdmin | null>(null);
	let deleting = $state(false);
	let deleteError = $state('');

	const tok = opts.token;
	const pid = opts.projectId;
	const ownerStamp = () => JSON.stringify([opts.ownerKey?.() ?? tok(), pid(), opts.ownerEpoch?.() ?? 0]);
	const allowed = () => !disposed && (opts.allowed?.() ?? true);

	function invalidateOwner() {
		loadGeneration++; domainsGeneration++; usersGeneration++; projectsGeneration++;
		announcements = []; allUsers = []; allProjects = []; domains = []; domainId = '';
		loading = false; refreshing = false; domainsLoading = false; usersLoading = false; projectsLoading = false;
		error = ''; domainsError = ''; usersError = ''; projectsError = ''; createError = '';
		creating = false; togglingId = null; deleting = false; deleteTarget = null; deleteError = '';
		emailOperation = null;
	}

	async function load(owner?: () => boolean) {
		await loadWithExperience(owner);
	}

	async function loadWithExperience(owner?: () => boolean, inherited?: ExperienceContext) {
		const generation = ++loadGeneration, token = tok(), projectId = pid(), stamp = ownerStamp();
		const current = () => allowed() && generation === loadGeneration && stamp === ownerStamp();
		const experience = inherited ?? beginExperienceLoad('admin', 'resource.list');
		const request = experience ? api.withExperience(experience) : api;
		const owns = () => current() && (!owner || owner());
		if (!owns()) { experienceDiscarded(experience, 'stale'); return; }
		experienceState(experience, 'loading');
		if (announcements.length === 0) loading = true;
		else refreshing = true;
		error = '';
		try {
			const rows = await request.get<AnnouncementAdmin[]>('/api/v1/admin/announcements', token, projectId);
			if (!owns()) { experienceDiscarded(experience, 'stale'); return; }
			announcements = rows;
			experienceState(experience, rows.length ? 'ready' : 'empty');
			void experienceApplied(experience, {}, owns);
		} catch (e) {
			if (owns()) { error = e instanceof ApiError ? e.message : t('announcements.error.loadFailed'); experienceState(experience, 'error'); void experienceApplied(experience, {}, owns); }
			else experienceDiscarded(experience, 'stale');
		} finally {
			if (current()) { loading = false; refreshing = false; }
		}
	}

	async function loadOptions() {
		if (options) return;
		const experience = beginExperienceLoad('admin', 'page');
		experienceState(experience, 'loading');
		try {
			options = await (experience ? api.withExperience(experience) : api).get<AnnouncementOptions>('/api/v1/admin/announcements/meta/options', tok(), pid());
			experienceState(experience, options ? 'ready' : 'disabled');
			void experienceApplied(experience);
		} catch {
			// 실패해도 폼은 하드코딩된 fallback 없이 비활성 유지 — 재시도는 다음 open에서.
			experienceState(experience, 'error');
		}
	}

	async function loadDomains() {
		const generation = ++domainsGeneration;
		const token = tok(), projectId = pid(), stamp = ownerStamp();
		const experience = beginExperienceLoad('iam', 'resource.list');
		const owns = () => allowed() && generation === domainsGeneration && stamp === ownerStamp();
		experienceState(experience, 'loading');
		domains = [];
		domainsLoading = true; domainsError = '';
		try {
			const response = experience ? await domainsApi.list({ token, projectId }, { experience }) : await domainsApi.list({ token, projectId });
			if (owns()) { domains = response.items; experienceState(experience, domains.length ? 'ready' : 'empty'); void experienceApplied(experience, {}, owns); }
			else experienceDiscarded(experience, 'stale');
		} catch (e) {
			if (!disposed && generation === domainsGeneration) {
				domainsError = e instanceof ApiError ? e.message : td('scope.loadFailed');
				experienceState(experience, 'error');
				void experienceApplied(experience, {}, () => !disposed && generation === domainsGeneration);
			} else experienceDiscarded(experience, 'stale');
		} finally { if (!disposed && generation === domainsGeneration) domainsLoading = false; }
	}
	function selectDomain(value: string, target: 'user' | 'project' = 'user') {
		const experience = beginExperienceAction('iam', 'select', 'resource.list');
		usersGeneration += 1; projectsGeneration += 1;
		domainId = domains.some(domain => domain.id === value) ? value : '';
		allUsers = []; usersError = ''; usersLoading = false;
		allProjects = []; projectsError = ''; projectsLoading = false;
		creating = false; createError = '';
		void experienceApplied(experience);
		if (domainId) { if (target === 'project') void loadProjectsWithExperience(experience); else void loadUsersWithExperience(experience); }
	}
	async function loadUsers() {
		await loadUsersWithExperience();
	}

	async function loadUsersWithExperience(inherited?: ExperienceContext) {
		if (!domainId || usersLoading || disposed) return;
		const generation = ++usersGeneration;
		const selectedDomain = domainId, token = tok(), projectId = pid(), stamp = ownerStamp();
		const owns = () => allowed() && generation === usersGeneration && selectedDomain === domainId && stamp === ownerStamp();
		const experience = inherited ?? beginExperienceLoad('iam', 'resource.list');
		const request = experience ? api.withExperience(experience) : api;
		experienceState(experience, 'loading');
		usersLoading = true; usersError = ''; allUsers = [];
		try {
			let marker: string | null = null;
			const collected: PickerUser[] = [], seen = new Set<string>();
			do {
				const path = domainPath(`/api/v1/admin/users?limit=100${marker ? `&marker=${encodeURIComponent(marker)}` : ''}`, selectedDomain);
				const response: { items: PickerUser[]; next_marker: string | null } = await request.get(path, token, projectId);
				if (!owns()) { experienceDiscarded(experience, 'stale'); return; }
				if (response.items.some(user => user.domain_id !== selectedDomain)) throw new Error(td('scope.invalid'));
				collected.push(...response.items);
				marker = response.next_marker;
				if (marker && seen.has(marker)) throw new Error(td('scope.invalid'));
				if (marker) seen.add(marker);
			} while (marker);
			if (owns()) { allUsers = collected; experienceState(experience, collected.length ? 'ready' : 'empty'); void experienceApplied(experience, {}, owns); }
			else experienceDiscarded(experience, 'stale');
		} catch (e) {
			if (owns()) { usersError = e instanceof ApiError ? e.message : t('announcements.error.usersLoadFailed'); experienceState(experience, 'error'); void experienceApplied(experience, {}, owns); }
			else experienceDiscarded(experience, 'stale');
		} finally { if (owns()) usersLoading = false; }
	}
	function dispose() { disposed = true; usersGeneration += 1; projectsGeneration += 1; domainsGeneration += 1; allUsers = []; allProjects = []; }

	async function loadProjects() {
		await loadProjectsWithExperience();
	}

	async function loadProjectsWithExperience(inherited?: ExperienceContext) {
		if (!domainId || projectsLoading || disposed) return;
		const selectedDomain = domainId, token = tok(), projectId = pid(), generation = ++projectsGeneration, stamp = ownerStamp();
		const owns = () => allowed() && selectedDomain === domainId && generation === projectsGeneration && stamp === ownerStamp();
		const experience = inherited ?? beginExperienceLoad('iam', 'resource.list');
		const request = experience ? api.withExperience(experience) : api;
		experienceState(experience, 'loading');
		projectsLoading = true; projectsError = ''; allProjects = [];
		try {
			const rows = await request.get<PickerProject[]>(domainPath('/api/v1/admin/projects/names', selectedDomain), token, projectId);
			if (!owns()) { experienceDiscarded(experience, 'stale'); return; }
			if (rows.some(project => project.domain_id !== selectedDomain)) throw new Error(td('scope.invalid'));
			allProjects = rows;
			experienceState(experience, rows.length ? 'ready' : 'empty');
			void experienceApplied(experience, {}, owns);
		} catch (error) {
			if (owns()) { projectsError = error instanceof ApiError ? error.message : t('announcements.error.projectsLoadFailed'); experienceState(experience, 'error'); void experienceApplied(experience, {}, owns); }
			else experienceDiscarded(experience, 'stale');
		} finally { if (owns()) projectsLoading = false; }
	}

	async function create(payload: AnnouncementCreatePayload): Promise<AnnouncementCreateResult> {
		const selectedDomain = domainId, token = tok(), projectId = pid(), generation = usersGeneration, projectGeneration = projectsGeneration, stamp = ownerStamp();
		const owns = () => allowed() && stamp === ownerStamp() && selectedDomain === domainId && generation === usersGeneration && projectGeneration === projectsGeneration;
		if (!owns() || creating || deleting || togglingId !== null) return { status: 'invalid' };
		if ((payload.target_type === 'user' && (!domainId || usersLoading || usersError || !allUsers.some(user => user.id === payload.target_id)))
			|| (payload.target_type === 'project' && (!domainId || projectsLoading || projectsError || !allProjects.some(project => project.id === payload.target_id && project.domain_id === domainId)))) {
			createError = td('scope.required');
			return { status: 'invalid' };
		}
		const experience = beginExperienceAction('admin', 'create', 'resource.list');
		const request = experience ? api.withExperience(experience) : api;
		experienceState(experience, 'loading');
		creating = true;
		createError = '';
		try {
			const created = await request.post<AnnouncementAdmin>('/api/v1/admin/announcements', payload, token, projectId, { cache: 'no-store', replayOnUnauthorized: false });
			if (owns()) { emailOperation = created?.email_operation ?? null; void experienceApplied(experience, {}, owns); }
			if (!owns()) { experienceDiscarded(experience, 'stale'); return { status: 'invalid' }; }
			await loadWithExperience(owns, experience);
			if (!owns()) experienceDiscarded(experience, 'stale');
			return { status: owns() ? 'ok' : 'invalid' };
		} catch (e) {
			const failure = mailDispatchFailure(e);
			if (owns()) { createError = `${tm(failure.message)}${failure.code ? ` (${failure.code})` : ''}`; experienceState(experience, 'error'); void experienceApplied(experience, {}, owns); }
			else experienceDiscarded(experience, 'stale');
			return { status: failure.status };
		} finally {
			if (owns()) creating = false;
		}
	}

	async function toggleActive(target: AnnouncementAdmin): Promise<void> {
		if (!allowed() || creating || deleting || togglingId !== null) return;
		const stamp = ownerStamp(), token = tok(), projectId = pid();
		const owns = () => allowed() && stamp === ownerStamp();
		const experience = beginExperienceAction('admin', 'update', 'resource.list');
		const request = experience ? api.withExperience(experience) : api;
		experienceState(experience, 'loading');
		togglingId = target.id;
		error = '';
		try {
			await request.patch(`/api/v1/admin/announcements/${target.id}`, { is_active: !target.is_active }, token, projectId, { replayOnUnauthorized: false });
			if (owns()) await loadWithExperience(owns, experience);
			else experienceDiscarded(experience, 'scope_changed');
		} catch (e) {
			if (owns()) { error = e instanceof ApiError ? e.message : t('announcements.error.toggleFailed'); experienceState(experience, 'error'); void experienceApplied(experience, {}, owns); }
			else experienceDiscarded(experience, 'scope_changed');
		} finally {
			if (owns()) togglingId = null;
		}
	}

	async function confirmDelete(): Promise<void> {
		if (!deleteTarget || !allowed() || creating || deleting || togglingId !== null) return;
		const stamp = ownerStamp(), token = tok(), projectId = pid(), target = deleteTarget;
		const owns = () => allowed() && stamp === ownerStamp();
		const experience = beginExperienceAction('admin', 'delete', 'resource.list');
		const request = experience ? api.withExperience(experience) : api;
		experienceState(experience, 'loading');
		deleting = true;
		deleteError = '';
		try {
			await request.delete(`/api/v1/admin/announcements/${target.id}`, token, projectId, { replayOnUnauthorized: false });
			if (!owns()) { experienceDiscarded(experience, 'scope_changed'); return; }
			deleteTarget = null;
			void experienceApplied(experience, {}, owns);
			await loadWithExperience(owns, experience);
		} catch (e) {
			if (owns()) { deleteError = e instanceof ApiError ? e.message : t('announcements.error.deleteFailed'); experienceState(experience, 'error'); void experienceApplied(experience, {}, owns); }
			else experienceDiscarded(experience, 'scope_changed');
		} finally {
			if (owns()) deleting = false;
		}
	}

	return {
		get announcements() { return announcements; },
		get emailOperation() { return emailOperation; },
		invalidateOwner,
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
