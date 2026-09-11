<script lang="ts">
	import type { Group } from '$lib/types/adminGroup';

	interface Props {
		target: Group | null;
		updating: boolean;
		error: string;
		onSave: (form: { name: string; description: string }) => Promise<boolean>;
	}

	let { target = $bindable(), updating, error, onSave }: Props = $props();

	let editName = $state('');
	let editDesc = $state('');

	$effect(() => {
		if (target) {
			editName = target.name;
			editDesc = target.description;
		}
	});

	async function handleSave() {
		const ok = await onSave({ name: editName, description: editDesc });
		if (ok) {
			target = null;
		}
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
		<div
			class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
		>
			<h2 class="text-lg font-semibold text-ink-0 mb-5">그룹 수정</h2>
			{#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}
			<div class="space-y-4">
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-groupeditmodal-47">이름</label>
					<input id="field-groupeditmodal-47" bind:value={editName} type="text" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-groupeditmodal-51">설명</label>
					<input id="field-groupeditmodal-51" bind:value={editDesc} type="text" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
				</div>
				<div class="text-xs text-ink-3">ID: {target.id}</div>
			</div>
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={() => { target = null; }} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">취소</button>
				<button onclick={handleSave} disabled={updating} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">{updating ? '수정 중...' : '수정'}</button>
			</div>
		</div>
	</div>
{/if}
