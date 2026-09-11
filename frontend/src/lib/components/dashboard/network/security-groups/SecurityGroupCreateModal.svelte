<script lang="ts">
	let {
		open = $bindable(),
		creating,
		error,
		onCreate,
	}: {
		open: boolean;
		creating: boolean;
		error: string;
		onCreate: (form: { name: string; description: string }) => Promise<boolean>;
	} = $props();

	let form = $state({ name: '', description: '' });

	async function handleCreate() {
		const ok = await onCreate(form);
		if (ok) {
			form = { name: '', description: '' };
		}
	}
</script>

{#if open}
	<div class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={() => { open = false; }}
		onkeydown={(e) => e.key === 'Escape' && (open = false)}
		role="dialog" aria-modal="true" tabindex="-1">
		<div class="bg-surface-sunken border border-line-2 rounded-xl p-6 w-full max-w-sm mx-4" onclick={(e) => e.stopPropagation()} role="none" onkeydown={(e) => e.stopPropagation()}>
			<h3 class="text-lg font-semibold text-ink-0 mb-4">보안 그룹 생성</h3>
			<div class="space-y-3 mb-4">
				<div>
					<label class="block text-xs text-ink-2 mb-1">이름 *
						<input bind:value={form.name} placeholder="보안 그룹 이름"
							class="w-full bg-surface-selected border border-line-2 rounded px-3 py-2 text-sm text-ink-1 placeholder-ink-3 focus:border-action-warm focus:outline-none mt-1" />
					</label>
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1">설명
						<input bind:value={form.description} placeholder="설명 (선택)"
							class="w-full bg-surface-selected border border-line-2 rounded px-3 py-2 text-sm text-ink-1 placeholder-ink-3 focus:border-action-warm focus:outline-none mt-1" />
					</label>
				</div>
			</div>
			{#if error}
				<p class="text-xs text-red-400 mb-3">{error}</p>
			{/if}
			<div class="flex gap-2">
				<button onclick={handleCreate} disabled={creating || !form.name.trim()}
					class="flex-1 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm py-2 rounded transition-colors">
					{creating ? '생성 중...' : '생성'}
				</button>
				<button onclick={() => { open = false; }}
					class="flex-1 bg-surface-selected hover:bg-surface-selected text-ink-2 text-sm py-2 rounded transition-colors">취소</button>
			</div>
		</div>
	</div>
{/if}
