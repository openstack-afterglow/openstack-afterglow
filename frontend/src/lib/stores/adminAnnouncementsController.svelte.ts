import { api, ApiError } from '$lib/api/client';
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
			error = e instanceof ApiError ? e.message : '공지 목록 조회 실패';
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

	async function loadUsers() {
		if (allUsers.length > 0 || usersLoading) return;
		usersLoading = true;
		usersError = '';
		try {
			const res = await api.get<{ items: PickerUser[] }>('/api/v1/admin/users?limit=100', tok(), pid());
			allUsers = res.items;
		} catch {
			usersError = '유저 목록을 불러오지 못했습니다';
		} finally {
			usersLoading = false;
		}
	}

	async function loadProjects() {
		if (allProjects.length > 0 || projectsLoading) return;
		projectsLoading = true;
		projectsError = '';
		try {
			allProjects = await api.get<PickerProject[]>('/api/v1/admin/projects/names', tok(), pid());
		} catch {
			projectsError = '프로젝트 목록을 불러오지 못했습니다';
		} finally {
			projectsLoading = false;
		}
	}

	async function create(payload: AnnouncementCreatePayload): Promise<boolean> {
		creating = true;
		createError = '';
		try {
			await api.post('/api/v1/admin/announcements', payload, tok(), pid());
			await load();
			return true;
		} catch (e) {
			createError = e instanceof ApiError ? e.message : '공지 생성 실패';
			return false;
		} finally {
			creating = false;
		}
	}

	async function toggleActive(target: AnnouncementAdmin): Promise<void> {
		togglingId = target.id;
		error = '';
		try {
			await api.patch(`/api/v1/admin/announcements/${target.id}`, { is_active: !target.is_active }, tok(), pid());
			await load();
		} catch (e) {
			error = e instanceof ApiError ? e.message : '공지 상태 변경 실패';
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
			deleteError = e instanceof ApiError ? e.message : '공지 삭제 실패';
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
