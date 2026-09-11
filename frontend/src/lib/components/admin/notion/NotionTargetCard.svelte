<script lang="ts">
	export interface NotionTarget {
		id: number;
		label: string;
		api_key: string;
		database_id: string;
		users_database_id: string;
		hypervisors_database_id: string;
		gpu_spec_database_id: string;
		enabled: boolean;
		interval_minutes: number;
		last_sync: string | null;
		hypervisors_last_sync: string | null;
		gpu_spec_last_sync: string | null;
		created_at: string;
		updated_at: string;
	}

	let {
		target,
		testing,
		testMessage,
		testError,
		onTest,
		onEdit,
		onDelete,
	}: {
		target: NotionTarget;
		testing: boolean;
		testMessage: string;
		testError: string;
		onTest: () => void;
		onEdit: () => void;
		onDelete: () => void;
	} = $props();

	function formatDate(s: string | null | undefined): string {
		if (!s) return '-';
		const d = new Date(s.endsWith('Z') || s.includes('+') ? s : s + 'Z');
		return d.toLocaleString(undefined, {
			year: 'numeric', month: '2-digit', day: '2-digit',
			hour: '2-digit', minute: '2-digit', second: '2-digit',
			hour12: false,
		});
	}
</script>

<div class="flex items-start justify-between">
	<div class="flex-1 min-w-0">
		<div class="flex items-center gap-2 mb-1">
			<span class="text-ink-0 font-medium">{target.label}</span>
			{#if target.enabled}
				<span class="text-xs text-green-400 bg-green-900/30 px-1.5 py-0.5 rounded">활성</span>
			{:else}
				<span class="text-xs text-ink-3 bg-surface-sunken px-1.5 py-0.5 rounded">비활성</span>
			{/if}
			<span class="text-xs text-ink-3">{target.interval_minutes}분 간격</span>
		</div>
		<div class="text-xs text-ink-3 font-mono truncate">{target.api_key}</div>
		<dl class="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
			<div>
				<dt class="text-ink-3 inline">인스턴스 DB: </dt>
				<dd class="text-ink-2 font-mono inline">{target.database_id || '-'}</dd>
			</div>
			<div>
				<dt class="text-ink-3 inline">마지막 동기화: </dt>
				<dd class="text-ink-2 inline">{formatDate(target.last_sync)}</dd>
			</div>
			{#if target.hypervisors_database_id}
				<div>
					<dt class="text-ink-3 inline">하이퍼바이저 DB: </dt>
					<dd class="text-ink-2 font-mono inline">{target.hypervisors_database_id}</dd>
				</div>
				<div>
					<dt class="text-ink-3 inline">하이퍼바이저 동기화: </dt>
					<dd class="text-ink-2 inline">{formatDate(target.hypervisors_last_sync)}</dd>
				</div>
			{/if}
			{#if target.gpu_spec_database_id}
				<div>
					<dt class="text-ink-3 inline">GPU Spec DB: </dt>
					<dd class="text-ink-2 font-mono inline">{target.gpu_spec_database_id}</dd>
				</div>
				<div>
					<dt class="text-ink-3 inline">GPU spec 동기화: </dt>
					<dd class="text-ink-2 inline">{formatDate(target.gpu_spec_last_sync)}</dd>
				</div>
			{/if}
		</dl>
	</div>
	<div class="flex items-center gap-2 ml-4 shrink-0">
		<button onclick={onTest} disabled={testing}
			class="px-3 py-1.5 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-xs rounded-lg transition-colors">
			{testing ? '동기화 중...' : '지금 동기화'}
		</button>
		<button onclick={onEdit}
			class="px-3 py-1.5 border border-line-2 hover:border-line-2 text-ink-2 hover:text-ink-1 text-xs rounded-lg transition-colors">
			수정
		</button>
		<button onclick={onDelete}
			class="px-3 py-1.5 border border-red-900 hover:border-red-700 text-red-400 hover:text-red-300 text-xs rounded-lg transition-colors">
			삭제
		</button>
	</div>
</div>
{#if testMessage}
	<div class="mt-2 text-green-400 text-xs">{testMessage}</div>
{/if}
{#if testError}
	<div class="mt-2 text-red-400 text-xs">{testError}</div>
{/if}
