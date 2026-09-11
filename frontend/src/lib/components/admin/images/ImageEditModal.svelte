<script lang="ts">
	import type { AdminImage } from '$lib/types/adminImage';
	import Button from '$lib/components/ui/Button.svelte';

	let {
		target = $bindable(),
		form = $bindable(),
		editing,
		editError,
		onSave,
	}: {
		target: AdminImage | null;
		form: { name: string; os_distro: string; visibility: string };
		editing: boolean;
		editError: string;
		onSave: () => Promise<void>;
	} = $props();
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
			class="bg-[var(--color-surface-raised)] border border-[var(--color-line)] rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
		>
			<h2 class="text-lg font-semibold text-[var(--color-ink-0)] mb-5">이미지 수정</h2>
			{#if editError}
				<div class="bg-[var(--color-state-danger)]/20 border border-[var(--color-state-danger)] text-[var(--color-state-danger)] rounded-lg px-4 py-3 text-sm mb-4">{editError}</div>
			{/if}
			<div class="space-y-4">
				<div>
					<label class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide" for="field-imageeditmodal-38">이름</label>
					<input id="field-imageeditmodal-38"
						bind:value={form.name}
						type="text"
						class="w-full bg-[var(--color-surface-sunken)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[var(--color-ink-0)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
					/>
					<span class="block text-[11px] text-[var(--color-ink-3)] mt-1">repository:tag 형식이며 tag를 생략하면 latest가 사용됩니다.</span>
				</div>
				<div>
					<label class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide" for="field-imageeditmodal-47">OS 배포판</label>
					<input id="field-imageeditmodal-47"
						bind:value={form.os_distro}
						type="text"
						placeholder="ubuntu, centos, rocky ..."
						class="w-full bg-[var(--color-surface-sunken)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[var(--color-ink-0)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
					/>
				</div>
				<div>
					<label class="block text-xs text-[var(--color-ink-2)] mb-1.5 uppercase tracking-wide" for="field-imageeditmodal-56">공개 범위</label>
					<select id="field-imageeditmodal-56"
						bind:value={form.visibility}
						class="w-full bg-[var(--color-surface-sunken)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[var(--color-ink-0)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
					>
						<option value="public">public</option>
						<option value="community">community</option>
						<option value="shared">shared</option>
						<option value="private">private</option>
					</select>
				</div>
			</div>
			<div class="flex justify-end gap-3 mt-6">
				<Button variant="ghost" size="md" onclick={() => { target = null; }}>취소</Button>
				<Button variant="accent" size="md" onclick={onSave} disabled={editing}>
					{editing ? '저장 중...' : '저장'}
				</Button>
			</div>
		</div>
	</div>
{/if}
