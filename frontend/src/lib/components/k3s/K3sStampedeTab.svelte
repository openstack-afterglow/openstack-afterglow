<script lang="ts">
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import type { StampedeStatus } from '$lib/types/k3s';
	import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';

	const s = useK3sClusterDetailController();
	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const clusterId = $derived(s.cluster?.id ?? '');

	interface StampedeEvent {
		id: number;
		created_at: string | null;
		action: string;
		status: string;
		nodegroup_id: string | null;
		extra: Record<string, unknown>;
	}

	let events = $state<StampedeEvent[]>([]);
	let status = $state<StampedeStatus | null>(null);
	let loading = $state(false);
	let error = $state('');

	$effect(() => {
		if (clusterId) untrack(() => void load());
	});

	async function load() {
		loading = true;
		error = '';
		try {
			const [nextStatus, nextEvents] = await Promise.all([
				api.get<StampedeStatus>(`/api/v1/k3s/clusters/${clusterId}/stampede`, token, projectId),
				api.get<StampedeEvent[]>(`/api/v1/k3s/clusters/${clusterId}/stampede/events?limit=100`, token, projectId),
			]);
			status = nextStatus;
			events = nextEvents;
		} catch {
			error = '이벤트 이력을 불러올 수 없습니다.';
			events = [];
		} finally {
			loading = false;
		}
	}

	function formatResource(value: unknown, kind: 'cpu' | 'memory' | 'gpu'): string {
		const n = Number(value ?? 0);
		if (kind === 'cpu') return `${Math.round(n)}m`;
		if (kind === 'memory') return `${Math.round(n / 1024 / 1024)}Mi`;
		return `${n}`;
	}

	function actionIcon(action: string): string {
		if (action === 'scale_up') return '▲';
		if (action === 'scale_down') return '▼';
		if (action === 'blocked') return '!';
		return '●';
	}

	function actionColor(action: string, status: string): string {
		if (status === 'failed') return 'text-red-400';
		if (action === 'blocked') return 'text-action-warm';
		if (action === 'scale_up') return 'text-green-400';
		if (action === 'scale_down') return 'text-yellow-400';
		return 'text-ink-2';
	}

	function actionLabel(action: string, status: string): string {
		const statusLabel = status === 'started' ? '시작' : status === 'success' ? '완료' : '실패';
		if (action === 'scale_up') return `노드 추가 ${statusLabel}`;
		if (action === 'scale_down') return `노드 제거 ${statusLabel}`;
		if (action === 'blocked') return '스케일 차단';
		return action;
	}

	function formatTime(iso: string | null): string {
		if (!iso) return '-';
		const d = new Date(iso);
		return d.toLocaleString('ko-KR', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
	}

	function extraSummary(action: string, extra: Record<string, unknown>): string {
		if (action === 'scale_up') {
			const count = extra.add_count as number | undefined;
			const flavor = extra.flavor_name as string | undefined;
			const ready = (extra.ready_nodes as string[] | undefined)?.length;
			if (ready !== undefined) return `${ready}개 노드 Ready (요청 ${count}개, ${flavor ?? ''})`;
			return `${count ?? ''}개 요청${flavor ? ` — ${flavor}` : ''}`;
		}
		if (action === 'scale_down') {
			const node = extra.node_name as string | undefined;
			const removed = extra.removed_count as number | undefined;
			if (removed !== undefined) return `${removed}개 제거 완료`;
			return node ?? '';
		}
		if (action === 'blocked') {
			const reason = extra.reason as string | undefined;
			const pod = extra.pod as { namespace?: string; name?: string } | undefined;
			return `${reason ?? 'blocked'}${pod?.name ? ` — ${pod.namespace ?? 'default'}/${pod.name}` : ''}`;
		}
		return '';
	}
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
	{#if status?.nodegroups?.length}
		<div class="grid gap-2 mb-4 md:grid-cols-2">
			{#each status.nodegroups as ng (ng.id)}
				<div class="rounded-lg border border-line bg-surface-canvas/40 p-3">
					<div class="flex items-center justify-between gap-2">
						<div class="text-sm font-medium text-ink-1">{ng.name}</div>
						<div class="flex items-center gap-1">
							{#if Number((ng.capacity?.allocatable as Record<string, unknown> | undefined)?.gpu ?? 0) > 0}
								<span class="rounded border border-emerald-700/50 bg-emerald-900/30 px-1.5 py-0.5 text-xs text-emerald-300">GPU</span>
							{/if}
							{#if ng.in_flight}
								<span class="rounded border border-action-warm/50 bg-surface-selected/30 px-1.5 py-0.5 text-xs text-action-warm">in-flight {ng.in_flight}</span>
							{/if}
						</div>
					</div>
					<div class="mt-2 grid grid-cols-3 gap-2 text-xs">
						<div class="rounded bg-surface-base p-2">
							<div class="text-ink-3">CPU free</div>
							<div class="text-ink-1">{formatResource((ng.capacity?.free as Record<string, unknown> | undefined)?.cpu_m, 'cpu')}</div>
						</div>
						<div class="rounded bg-surface-base p-2">
							<div class="text-ink-3">MEM free</div>
							<div class="text-ink-1">{formatResource((ng.capacity?.free as Record<string, unknown> | undefined)?.memory_bytes, 'memory')}</div>
						</div>
						<div class="rounded bg-surface-base p-2">
							<div class="text-ink-3">GPU free</div>
							<div class="text-ink-1">{formatResource((ng.capacity?.free as Record<string, unknown> | undefined)?.gpu, 'gpu')}</div>
						</div>
					</div>
					{#if ng.pending_assignments?.length}
						<div class="mt-2 text-xs text-action-warm">Pending: {ng.pending_assignments.map(p => `${p.namespace ?? 'default'}/${p.name}`).join(', ')}</div>
					{/if}
					{#if ng.blocked_reasons?.length}
						<div class="mt-2 text-xs text-action-warm">Blocked: {ng.blocked_reasons.map(b => `${b.reason}: ${b.namespace ?? 'default'}/${b.name}`).join(', ')}</div>
					{/if}
					{#if ng.last_blocked_reason}
						<div class="mt-2 text-xs text-action-warm">Last blocked: {ng.last_blocked_reason}</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}

	<div class="flex items-center justify-between mb-4">
		<h3 class="text-xs text-ink-3 uppercase tracking-wide">Stampede 스케일 이벤트</h3>
		<button onclick={load} disabled={loading}
			class="text-xs text-ink-3 hover:text-ink-2 transition-colors disabled:opacity-50">
			{loading ? '로딩 중...' : '새로고침'}
		</button>
	</div>

	{#if error}
		<div class="text-xs text-red-400 py-2">{error}</div>
	{:else if loading && events.length === 0}
		<div class="text-xs text-ink-3 py-2">불러오는 중...</div>
	{:else if events.length === 0}
		<div class="text-xs text-ink-3 py-4 text-center">
			<div class="text-2xl mb-2">⚡</div>
			<div>아직 Stampede 이벤트가 없습니다.</div>
			<div class="text-ink-3 mt-1">노드그룹에 Stampede를 활성화하면 스케일 이벤트가 여기에 표시됩니다.</div>
		</div>
	{:else}
		<div class="space-y-0.5">
			{#each events as ev (ev.id)}
				<div class="flex items-start gap-3 py-2 border-b border-line/60 last:border-b-0">
					<span class="text-sm mt-0.5 {actionColor(ev.action, ev.status)} w-4 text-center flex-shrink-0">
						{actionIcon(ev.action)}
					</span>
					<div class="flex-1 min-w-0">
						<div class="flex items-center gap-2 flex-wrap">
							<span class="text-xs font-medium {actionColor(ev.action, ev.status)}">
								{actionLabel(ev.action, ev.status)}
							</span>
							{#if ev.nodegroup_id}
								<span class="text-xs text-ink-3 font-mono truncate max-w-40">{ev.nodegroup_id.slice(0, 8)}…</span>
							{/if}
							{#if ev.status === 'failed'}
								<span class="text-xs bg-red-900/40 text-red-400 border border-red-800/40 rounded px-1.5 py-0.5">실패</span>
							{/if}
						</div>
						{#if extraSummary(ev.action, ev.extra)}
							<div class="text-xs text-ink-3 mt-0.5">{extraSummary(ev.action, ev.extra)}</div>
						{/if}
					</div>
					<span class="text-xs text-ink-3 flex-shrink-0 tabular-nums">{formatTime(ev.created_at)}</span>
				</div>
			{/each}
		</div>
	{/if}
</div>
