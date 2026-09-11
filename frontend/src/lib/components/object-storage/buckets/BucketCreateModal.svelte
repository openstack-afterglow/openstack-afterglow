<script lang="ts">
	import { validateBucketName } from '$lib/utils/bucketName';

	let {
		open = $bindable(),
		onCreate,
	}: {
		open: boolean;
		onCreate: (name: string) => Promise<string | true>;
	} = $props();

	let name = $state('');
	let creating = $state(false);
	let error = $state('');

	$effect(() => {
		if (!open) {
			name = '';
			error = '';
		}
	});

	async function submit() {
		const trimmed = name.trim();
		if (!trimmed) return;
		const validationError = validateBucketName(trimmed);
		if (validationError) {
			error = validationError;
			return;
		}
		creating = true;
		error = '';
		const result = await onCreate(trimmed);
		creating = false;
		if (result === true) {
			open = false;
		} else {
			error = result;
		}
	}
</script>

{#if open}
	<div
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={() => { open = false; }}
		role="dialog"
		aria-modal="true"
		tabindex="-1"
		onkeydown={(e) => e.key === 'Escape' && (open = false)}
	>
		<div
			class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
			onkeydown={(e) => e.stopPropagation()}
		>
			<h2 class="text-lg font-semibold text-ink-0 mb-4">버킷 생성</h2>
			<div class="space-y-3">
				<div>
					<label class="block text-xs text-ink-2 mb-1" for="field-bucketcreatemodal-61">이름</label>
					<input id="field-bucketcreatemodal-61"
						type="text"
						bind:value={name}
						placeholder="my-container"
						class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 focus:outline-none focus:border-indigo-500"
						onkeydown={(e) => e.key === 'Enter' && submit()}
					/>
				</div>
				{#if error}
					<p class="text-red-400 text-xs">{error}</p>
				{/if}
			</div>
			<div class="flex justify-end gap-2 mt-5">
				<button
					onclick={() => { open = false; }}
					class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 border border-line-2 rounded-lg transition-colors"
				>취소</button>
				<button
					onclick={submit}
					disabled={creating || !name.trim()}
					class="px-4 py-2 text-sm bg-indigo-600 hover:bg-indigo-500 disabled:bg-surface-selected disabled:text-ink-3 text-ink-0 rounded-lg transition-colors"
				>{creating ? '생성 중...' : '생성'}</button>
			</div>
		</div>
	</div>
{/if}
