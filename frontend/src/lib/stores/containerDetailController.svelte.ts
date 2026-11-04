import { getContext, setContext } from 'svelte';
import { api, ApiError } from '$lib/api/client';
import type { ZunContainerDetail } from '$lib/types/zunContainer';
import { confirmDialog } from '$lib/stores/confirm.svelte';
import { t } from '$lib/i18n/ns/containers-shell';
import { beginExperienceAction, beginExperienceLoad, experienceApplied, experienceState, type ExperienceContext } from '$lib/utils/experience';

interface Options {
	containerId: () => string;
	adminMode: () => boolean;
	token: () => string | undefined;
	projectId: () => string | undefined;
	onClose?: () => void;
	onRefresh?: () => void;
}

function createContainerDetailController(opts: Options) {
	let container = $state<ZunContainerDetail | null>(null);
	let loading = $state(true);
	let error = $state('');
	let logs = $state('');
	let logsLoading = $state(false);
	let logsOpen = $state(false);
	let actioning = $state(false);
	let actionError = $state('');

	const apiBase = $derived(opts.adminMode() ? '/api/v1/admin/containers' : '/api/v1/containers');

	function applied(ctx: ExperienceContext | undefined, state: 'ready' | 'empty' | 'error' | 'disabled') {
		experienceState(ctx, state);
		// This controller has no teardown owner; the DOM tail remains unknown.
		void experienceApplied(ctx, {});
	}

	async function fetchContainer(force = false, context?: ExperienceContext) {
		const ctx = context ?? (force ? beginExperienceAction('container', 'refresh', 'resource.detail') : beginExperienceLoad('container', 'resource.detail'));
		experienceState(ctx, 'loading');
		loading = true;
		error = '';
		try {
			container = await api.withExperience(ctx).get<ZunContainerDetail>(`${apiBase}/${opts.containerId()}`, opts.token(), opts.projectId(), { refresh: force });
			applied(ctx, container ? 'ready' : 'empty');
		} catch (e) {
			error = e instanceof ApiError ? t('container.fetchFailedDetail', { message: e.message }) : t('container.serverError');
			applied(ctx, 'error');
		} finally {
			loading = false;
		}
	}

	async function fetchLogs() {
		await loadLogs(beginExperienceAction('container', 'inspect', 'shared.stream'));
	}

	async function loadLogs(ctx: ExperienceContext | undefined) {
		experienceState(ctx, 'loading');
		logsLoading = true;
		try {
			const res = await api.withExperience(ctx).get<{ logs: string }>(`${apiBase}/${opts.containerId()}/logs`, opts.token(), opts.projectId());
			logs = res.logs;
			applied(ctx, logs ? 'ready' : 'empty');
		} catch {
			logs = t('container.logsFailed');
			applied(ctx, 'error');
		} finally {
			logsLoading = false;
		}
	}

	async function handleAction(action: 'start' | 'stop') {
		const ctx = beginExperienceAction('container', action, 'resource.detail');
		experienceState(ctx, 'loading');
		actioning = true;
		actionError = '';
		try {
			await api.withExperience(ctx).post(`${apiBase}/${opts.containerId()}/${action}`, {}, opts.token(), opts.projectId());
			await fetchContainer(false, ctx);
			opts.onRefresh?.();
		} catch (e) {
			actionError = e instanceof ApiError ? e.message : t(action === 'start' ? 'container.startFailed' : 'container.stopFailed');
			applied(ctx, 'error');
		} finally {
			actioning = false;
		}
	}

	async function handleDelete() {
		if (!container) return;
		if (!(await confirmDialog(t('container.deleteConfirm', { name: container.name })))) return;
		const ctx = beginExperienceAction('container', 'delete', 'resource.detail');
		experienceState(ctx, 'loading');
		actioning = true;
		actionError = '';
		try {
			await api.withExperience(ctx).delete(`${apiBase}/${opts.containerId()}`, opts.token(), opts.projectId());
			experienceState(ctx, 'ready');
			opts.onRefresh?.();
			opts.onClose?.();
		} catch (e) {
			actionError = e instanceof ApiError ? e.message : t('container.deleteFailed');
			applied(ctx, 'error');
			actioning = false;
		}
	}

	function toggleLogs() {
		const ctx = beginExperienceAction('container', logsOpen ? 'close' : 'open', 'shared.stream');
		logsOpen = !logsOpen;
		if (logsOpen && !logs) void loadLogs(ctx);
		else applied(ctx, logsOpen ? 'ready' : 'disabled');
	}

	return {
		get container() { return container; },
		get loading() { return loading; },
		get error() { return error; },
		get logs() { return logs; },
		get logsLoading() { return logsLoading; },
		get logsOpen() { return logsOpen; },
		get actioning() { return actioning; },
		get actionError() { return actionError; },
		fetchContainer,
		fetchLogs,
		handleAction,
		handleDelete,
		toggleLogs,
	};
}

export type ContainerDetailController = ReturnType<typeof createContainerDetailController>;
export { createContainerDetailController };

const CONTAINER_DETAIL_KEY = Symbol('container-detail');

export function provideContainerDetailController(store: ContainerDetailController) {
	setContext(CONTAINER_DETAIL_KEY, store);
}

export function useContainerDetailController(): ContainerDetailController {
	const store = getContext<ContainerDetailController | undefined>(CONTAINER_DETAIL_KEY);
	if (!store) throw new Error('useContainerDetailController must be called within ContainerDetailPanel');
	return store;
}
