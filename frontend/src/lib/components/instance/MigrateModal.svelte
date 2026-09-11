<script lang="ts">
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';

	interface Props {
		type: 'live' | 'cold';
		onClose: () => void;
	}

	let { type, onClose }: Props = $props();

	const s = useInstanceDetailController();

	let migrateHost = $state('');

	// CPU 모델 안내 문구
	const cpuModelHint = $derived(
		type === 'cold'
			? '모든 호스트 표시 (CPU 모델 무관)'
			: s.migrateHosts.length > 0 && s.migrateHosts[0].cpu_model
				? `${s.migrateHosts[0].cpu_model} 호환 호스트만 표시`
				: null
	);

	async function handleMigrate() {
		const ok = await s.doMigrate(type, migrateHost);
		if (ok) onClose();
	}
</script>

<Modal open={true} onClose={onClose} labelledBy="instance-migrate-title">
	<div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]">
		<h2 id="instance-migrate-title" class="text-lg font-semibold text-ink-0 mb-1">
			{type === 'live' ? '라이브 마이그레이션' : '콜드 마이그레이션'}
		</h2>
		<p class="text-xs text-ink-3 mb-5">
			{type === 'live' ? '인스턴스 실행 중에 다른 호스트로 이동합니다.' : '인스턴스를 종료하고 다른 호스트로 이동합니다.'}
		</p>
		{#if s.migrateError}
			<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{s.migrateError}</div>
		{/if}
		<div class="space-y-4">
			<div>
				<div class="flex items-baseline justify-between mb-1.5">
					<label for="migrate-host" class="text-xs text-ink-2 uppercase tracking-wide">
						대상 호스트 <span class="text-ink-3">(선택 안 하면 자동)</span>
					</label>
					{#if cpuModelHint}
						<span class="text-xs text-ink-3">{cpuModelHint}</span>
					{/if}
				</div>
				{#if s.migrateHosts.length === 0}
					<div class="bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-xs text-ink-3">
						호환 가능한 호스트가 없습니다. 자동 선택만 가능합니다.
					</div>
				{:else}
					<select id="migrate-host" bind:value={migrateHost} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm">
						<option value="">자동 선택</option>
						{#each s.migrateHosts as h}
							<option value={h.name}>{h.name}</option>
						{/each}
					</select>
				{/if}
			</div>
		</div>
		<div class="flex justify-end gap-3 mt-6">
			<button onclick={onClose} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">취소</button>
			<button onclick={handleMigrate} disabled={s.migrateLoading} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg disabled:opacity-30">
				{s.migrateLoading ? '마이그레이션 중...' : '마이그레이션'}
			</button>
		</div>
	</div>
</Modal>
