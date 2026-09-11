<script lang="ts">
	import type { AdminRouter } from '$lib/types/networks';

	let {
		router = $bindable(),
		onUpdate,
	}: {
		router: AdminRouter | null;
		onUpdate: (id: string, form: { name: string }) => Promise<string | true>;
	} = $props();

	let name = $state('');
	let updating = $state(false);
	let error = $state('');

	$effect(() => {
		if (router) {
			name = router.name;
			error = '';
			updating = false;
		}
	});

	async function submit() {
		if (!router) return;
		updating = true;
		error = '';
		const result = await onUpdate(router.id, { name });
		updating = false;
		if (result === true) router = null;
		else error = result;
	}
</script>

{#if router}
	<div class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50" onclick={() => { router = null; }} role="dialog" onkeydown={(e) => e.key === 'Escape' && (router = null)} tabindex="-1">
		<div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]" onclick={(e) => e.stopPropagation()} role="none" onkeydown={(e) => e.stopPropagation()}>
			<h2 class="text-lg font-semibold text-ink-0 mb-5">라우터 수정</h2>
			{#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}
			<div>
				<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminroutereditmodal-41">이름</label>
				<input id="field-adminroutereditmodal-41" bind:value={name} type="text" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
			</div>
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={() => { router = null; }} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">취소</button>
				<button onclick={submit} disabled={updating} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">{updating ? '수정 중...' : '수정'}</button>
			</div>
		</div>
	</div>
{/if}
