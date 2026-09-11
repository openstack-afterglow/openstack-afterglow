<script lang="ts">
	import { useDbInstanceDetailController } from '$lib/stores/dbInstanceDetailController.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import DbRestoreModal from '$lib/components/database/DbRestoreModal.svelte';
	import type { DbBackup } from '$lib/types/database';

	const s = useDbInstanceDetailController();

	let showRestoreModal = $state(false);
	let selectedBackup = $state<DbBackup | null>(null);

	const STUCK_MS = 6 * 3600 * 1000;
	function isStuck(b: DbBackup): boolean {
		return b.status === 'BUILDING' && (Date.now() - new Date(b.created_at).getTime()) > STUCK_MS;
	}

	let showBackupForm = $state(false);
	let newBackup = $state({ name: '', description: '' });

	// 자동 백업 설정 폼 상태 (frequency + count 단순화)
	type Frequency = 'daily' | 'weekly' | 'monthly';
	let autoForm = $state<{ frequency: Frequency; count: number }>({ frequency: 'daily', count: 7 });
	let showAutoForm = $state(false);

	const FREQ_LABEL: Record<Frequency, string> = { daily: '일별', weekly: '주별', monthly: '월별' };

	// 자동 백업 활성화 여부
	const autoEnabled = $derived(s.autoBackupConfig !== null);

	// 현재 설정에서 주기·개수 역매핑
	function configToForm(): { frequency: Frequency; count: number } {
		const cfg = s.autoBackupConfig;
		if (!cfg) return { frequency: 'daily', count: 7 };
		if (cfg.max_weekly > 0) return { frequency: 'weekly', count: cfg.max_weekly };
		if (cfg.max_monthly > 0) return { frequency: 'monthly', count: cfg.max_monthly };
		return { frequency: 'daily', count: cfg.max_daily || 7 };
	}

	// 주기·개수 → max_* 매핑
	function formToConfig(freq: Frequency, count: number) {
		return {
			max_daily: freq === 'daily' ? count : 0,
			max_weekly: freq === 'weekly' ? count : 0,
			max_monthly: freq === 'monthly' ? count : 0,
		};
	}

	function openAutoForm() {
		autoForm = configToForm();
		showAutoForm = true;
	}

	async function handleToggleAutoBackup() {
		if (autoEnabled) {
			await s.disableAutoBackup();
		} else {
			autoForm = { frequency: 'daily', count: 7 };
			showAutoForm = true;
		}
	}

	async function handleSaveAutoBackup() {
		const { max_daily, max_weekly, max_monthly } = formToConfig(autoForm.frequency, autoForm.count);
		await s.saveAutoBackupConfig(max_daily, max_weekly, max_monthly);
		showAutoForm = false;
	}

	function autoBackupName(): string {
		const base = s.instance?.name ?? 'backup';
		const now = new Date();
		const pad = (n: number) => String(n).padStart(2, '0');
		const date = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`;
		const time = `${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
		return `${base}-${date}-${time}`;
	}

	async function handleCreateBackup() {
		const name = newBackup.name.trim() || autoBackupName();
		const ok = await s.createBackup(name, newBackup.description);
		if (ok) {
			showBackupForm = false;
			newBackup = { name: '', description: '' };
		}
	}
</script>

<DbRestoreModal
	bind:open={showRestoreModal}
	backup={selectedBackup}
	flavors={s.flavors}
	onRestore={async (id, name, fid, vs) => { await s.restoreBackup(id, name, fid, vs); }}
	onClose={() => { showRestoreModal = false; }}
/>

<!-- 자동 백업 설정 -->
<div class="bg-surface-base border border-line rounded-xl p-4 mb-3">
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-sm font-semibold text-ink-0">자동 백업</h2>
			{#if autoEnabled}
				{@const f = configToForm()}
				<p class="text-xs text-ink-3 mt-0.5">{FREQ_LABEL[f.frequency]} · {f.count}회 보존</p>
			{:else}
				<p class="text-xs text-ink-3 mt-0.5">비활성화됨</p>
			{/if}
		</div>
		<div class="flex items-center gap-2">
			{#if autoEnabled}
				<button onclick={openAutoForm}
					class="text-xs text-ink-2 hover:text-ink-0 border border-line-2 hover:border-line-2 px-2 py-1 rounded transition-colors">
					설정 변경
				</button>
			{/if}
			<button
				onclick={handleToggleAutoBackup}
				disabled={s.savingAutoBackup}
				title={autoEnabled ? '자동 백업 비활성화' : '자동 백업 활성화'}
				class="relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out disabled:opacity-50 {autoEnabled ? 'bg-action-warm' : 'bg-surface-selected'}"
			>
				<span class="pointer-events-none inline-block h-4 w-4 transform rounded-full bg-surface-base shadow ring-0 transition duration-200 ease-in-out {autoEnabled ? 'translate-x-4' : 'translate-x-0'}"></span>
			</button>
		</div>
	</div>

	{#if showAutoForm}
		<div class="mt-3 bg-surface-sunken rounded-lg p-3 space-y-3">
			<div class="flex gap-3">
				<label class="flex flex-col gap-1 flex-1">
					<span class="text-xs text-ink-3">백업 주기</span>
					<select bind:value={autoForm.frequency}
						class="bg-surface-selected border border-line-2 rounded px-2 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm">
						<option value="daily">일별</option>
						<option value="weekly">주별</option>
						<option value="monthly">월별</option>
					</select>
				</label>
				<label class="flex flex-col gap-1 w-24">
					<span class="text-xs text-ink-3">보존 개수</span>
					<input type="number" min="1" max="30" bind:value={autoForm.count}
						class="bg-surface-selected border border-line-2 rounded px-2 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm text-center" />
				</label>
			</div>
			<div class="flex gap-2">
				<button onclick={handleSaveAutoBackup} disabled={s.savingAutoBackup}
					class="text-xs bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm px-3 py-1.5 rounded transition-colors">
					{s.savingAutoBackup ? '저장 중...' : '저장'}
				</button>
				<button onclick={() => { showAutoForm = false; }}
					class="text-xs text-ink-2 hover:text-ink-0 border border-line-2 hover:border-line-2 px-3 py-1.5 rounded transition-colors">
					취소
				</button>
			</div>
		</div>
	{/if}
</div>

<!-- 수동 백업 -->
<div class="bg-surface-base border border-line rounded-xl p-4">
	<div class="flex items-center justify-between mb-3">
		<h2 class="text-sm font-semibold text-ink-0">백업</h2>
		<button onclick={() => { showBackupForm = !showBackupForm; s.backupError = ''; }}
			class="text-xs text-ink-2 hover:text-ink-0 border border-line-2 hover:border-line-2 px-2 py-1 rounded transition-colors">
			{showBackupForm ? '취소' : '+ 백업 생성'}
		</button>
	</div>
	{#if showBackupForm}
		<div class="bg-surface-sunken rounded-lg p-3 mb-3 space-y-2">
			<input type="text" bind:value={newBackup.name} placeholder="비우면 {s.instance?.name ?? 'db'}-날짜-시간으로 자동 생성"
				class="w-full bg-surface-selected border border-line-2 rounded px-3 py-1.5 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm" />
			<input type="text" bind:value={newBackup.description} placeholder="설명 (선택)"
				class="w-full bg-surface-selected border border-line-2 rounded px-3 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm" />
			{#if s.backupError}<p class="text-red-400 text-xs">{s.backupError}</p>{/if}
			<button onclick={handleCreateBackup} disabled={s.creatingBackup}
				class="text-xs bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm px-3 py-1.5 rounded transition-colors">
				{s.creatingBackup ? '생성 중...' : '백업 생성'}
			</button>
		</div>
	{/if}
	{#if s.backups.length === 0}
		<div class="text-ink-3 text-xs">백업이 없습니다</div>
	{:else}
		<table class="w-full text-sm">
			<thead>
				<tr class="text-ink-3 text-xs">
					<th class="text-left py-2 font-medium">이름</th>
					<th class="text-left py-2 font-medium">상태</th>
					<th class="text-left py-2 font-medium">크기</th>
					<th class="text-left py-2 font-medium">생성일</th>
					<th class="text-right py-2 font-medium">액션</th>
				</tr>
			</thead>
			<tbody>
				{#each s.backups as b}
					<tr class="border-t border-line/50">
						<td class="py-2 text-ink-0">{b.name}</td>
						<td class="py-2">
							<div class="flex items-center gap-1">
								<StatusChip status={b.status} />
								{#if isStuck(b)}
									<span class="text-xs text-red-400 ml-1" title="Trove guest agent가 백업 업로드를 완료하지 못했습니다. 삭제 후 재시도하세요.">멈춤</span>
								{/if}
							</div>
						</td>
						<td class="py-2 text-ink-2 text-xs">{b.size ? `${b.size} GB` : '-'}</td>
						<td class="py-2 text-ink-3 text-xs">{b.created_at ? b.created_at.slice(0, 10) : '-'}</td>
						<td class="py-2 text-right">
							<div class="flex justify-end gap-1">
								<button onclick={() => { selectedBackup = b; showRestoreModal = true; }} disabled={s.restoringBackup === b.id}
									class="text-action-warm hover:text-action-warm-hover disabled:text-ink-3 text-xs px-2 py-0.5 rounded border border-action-warm hover:border-action-warm transition-colors">
									{s.restoringBackup === b.id ? '...' : '복원'}
								</button>
								<button onclick={() => s.deleteBackup(b.id)} disabled={s.deletingBackup === b.id}
									class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-0.5 rounded border border-red-900 hover:border-red-700 transition-colors">
									{s.deletingBackup === b.id ? '...' : '삭제'}
								</button>
							</div>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
</div>
