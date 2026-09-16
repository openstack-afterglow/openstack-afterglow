import { getContext, setContext } from 'svelte';
import { api, ApiError } from '$lib/api/client';
import type { ZunContainerDetail } from '$lib/types/zunContainer';
import { confirmDialog } from '$lib/stores/confirm.svelte';

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

	async function fetchContainer() {
		loading = true;
		error = '';
		try {
			container = await api.get<ZunContainerDetail>(`${apiBase}/${opts.containerId()}`, opts.token(), opts.projectId());
		} catch (e) {
			error = e instanceof ApiError ? `조회 실패: ${e.message}` : '서버 오류';
		} finally {
			loading = false;
		}
	}

	async function fetchLogs() {
		logsLoading = true;
		try {
			const res = await api.get<{ logs: string }>(`${apiBase}/${opts.containerId()}/logs`, opts.token(), opts.projectId());
			logs = res.logs;
		} catch {
			logs = '로그를 가져올 수 없습니다';
		} finally {
			logsLoading = false;
		}
	}

	async function handleAction(action: 'start' | 'stop') {
		actioning = true;
		actionError = '';
		try {
			await api.post(`${apiBase}/${opts.containerId()}/${action}`, {}, opts.token(), opts.projectId());
			await fetchContainer();
			opts.onRefresh?.();
		} catch (e) {
			actionError = e instanceof ApiError ? e.message : `${action === 'start' ? '시작' : '중지'} 실패`;
		} finally {
			actioning = false;
		}
	}

	async function handleDelete() {
		if (!container) return;
		if (!(await confirmDialog(`컨테이너 "${container.name}"을 삭제하시겠습니까?`))) return;
		actioning = true;
		actionError = '';
		try {
			await api.delete(`${apiBase}/${opts.containerId()}`, opts.token(), opts.projectId());
			opts.onRefresh?.();
			opts.onClose?.();
		} catch (e) {
			actionError = e instanceof ApiError ? e.message : '삭제 실패';
			actioning = false;
		}
	}

	function toggleLogs() {
		logsOpen = !logsOpen;
		if (logsOpen && !logs) fetchLogs();
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
