<script lang="ts">
	import type { PortInfo } from '$lib/types/networks';

	let {
		target = $bindable(),
		updating,
		error,
		onSave,
	}: {
		target: PortInfo | null;
		updating: boolean;
		error: string;
		onSave: (name: string) => Promise<boolean>;
	} = $props();

	let name = $state('');

	// Sync name from target whenever a new port is opened for editing
	$effect(() => {
		if (target) name = target.name ?? '';
	});

	async function handleSave() {
		const success = await onSave(name);
		if (success) name = '';
	}
</script>

{#if target}
	<div
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={(event) => { if (event.target === event.currentTarget) (() => { target = null; })(); }}
		role="dialog"
		onkeydown={(e) => e.key === 'Escape' && (target = null)}
		tabindex="-1"
	>
		<div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]">
			<h2 class="text-lg font-semibold text-ink-0 mb-5">포트 수정</h2>
			{#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}
			<div>
				<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-porteditmodal-41">이름</label>
				<input id="field-porteditmodal-41" bind:value={name} type="text" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
			</div>
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={() => { target = null; }} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">취소</button>
				<button onclick={handleSave} disabled={updating} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">{updating ? '수정 중...' : '수정'}</button>
			</div>
		</div>
	</div>
{/if}
