<script module lang="ts">
	export interface DockerfileLintDiagnostic { line: number | null; message: string }
	export interface DockerfileLintCompletion { ref: string; id: string; name: string; ubuntu_base: string; created_at: string | null }
	export interface DockerfileLintResponse {
		valid: boolean;
		diagnostics: DockerfileLintDiagnostic[];
		warnings: DockerfileLintDiagnostic[];
		from: {
			line: number | null; ref: string | null; kind: 'glance_name' | 'glance_id' | 'ubuntu_tag' | 'palimpsest' | null;
			image: { id: string; name: string; ubuntu_base: string; min_disk: number; visibility: string } | null;
			parent: { id: number; name: string; blob_digest: string | null; ubuntu_base: string; base_image_name: string | null; chain_depth: number } | null;
			completions: DockerfileLintCompletion[]; error: string | null; note: string | null;
		};
		layers: { new: number; inherited: number; total: number; limit: number; by_instruction: Record<string, number> };
	}
</script>

<script lang="ts">
	import { onDestroy } from 'svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import Button from '$lib/components/ui/Button.svelte';

	let { lint, loading, requestError }: { lint: DockerfileLintResponse | null; loading: boolean; requestError: string } = $props();
	let copiedRef = $state('');
	let copyError = $state('');
	let resetTimer: ReturnType<typeof setTimeout> | undefined;

	async function copyRef(ref: string) {
		copyError = '';
		copiedRef = '';
		if (resetTimer) clearTimeout(resetTimer);
		try {
			await navigator.clipboard.writeText(`FROM ${ref}`);
			copiedRef = ref;
			resetTimer = setTimeout(() => { copiedRef = ''; }, 1500);
		} catch {
			copyError = '복사하지 못했습니다 — 텍스트를 직접 선택해 복사하세요';
		}
	}
	onDestroy(() => { if (resetTimer) clearTimeout(resetTimer); });
</script>

<section aria-label="Dockerfile 검사" class="min-w-0 space-y-3 rounded-lg border border-line-2 bg-surface-base p-3 text-xs">
	<div class="flex flex-wrap items-center justify-between gap-2">
		<h3 class="font-semibold text-ink-0">Dockerfile 검사</h3>
		{#if loading}
			<Pill tone="neutral">검사 중…</Pill>
		{:else if requestError}
			<Pill tone="danger">검사 실패</Pill>
		{:else if lint?.diagnostics.length}
			<Pill tone="danger">오류 {lint.diagnostics.length}개</Pill>
		{:else if lint?.from.error}
			<Pill tone="warning">FROM 미해결</Pill>
		{:else if lint?.valid}
			<Pill tone="success">문법 OK · 레이어 {lint.layers.total}개</Pill>
		{:else}
			<Pill tone="neutral">대기</Pill>
		{/if}
	</div>
	{#if requestError}
		<Alert tone="danger">검사 요청 실패: {requestError}</Alert>
	{/if}
	{#if lint}
		{#if lint.diagnostics.length}
			<Alert tone="danger" title="문법 오류">
				<ul class="space-y-1">
					{#each lint.diagnostics as diagnostic}
						<li class="break-words">{#if diagnostic.line !== null}<code class="font-mono">L{diagnostic.line}</code> {/if}{diagnostic.message}</li>
					{/each}
				</ul>
			</Alert>
		{/if}
		{#if lint.from.kind === 'palimpsest' && lint.from.parent}
			<p class="break-words text-ink-1">FROM 부모 레이어 {lint.from.parent.name} #{lint.from.parent.id} · {lint.from.parent.ubuntu_base} · 체인 {lint.from.parent.chain_depth}개</p>
		{:else if lint.from.image}
			<div class="space-y-1 text-ink-1">
				<p class="break-words">FROM {lint.from.ref} → Glance {lint.from.image.name} · {lint.from.image.ubuntu_base} · {lint.from.image.id.slice(0, 8)}… · min {lint.from.image.min_disk}GB · {lint.from.image.visibility}</p>
				{#if lint.from.note}<p class="text-ink-2">{lint.from.note}</p>{/if}
			</div>
		{/if}
		{#if lint.from.error}
			<Alert tone="warning" title="FROM 해석 실패">
				<p class="break-words">{lint.from.error}</p>
				{#if lint.from.completions.length}
					<p class="mt-2">사용 가능한 FROM 값:</p>
					<ul class="mt-1 space-y-2">
						{#each lint.from.completions as completion (completion.id)}
							<li class="flex min-w-0 flex-wrap items-center gap-2 border-b border-line-2 pb-2 last:border-0 last:pb-0">
								<code class="min-w-0 break-all select-all font-mono">FROM {completion.ref}</code>
								<span class="min-w-0 break-words text-ink-2">{completion.name} · {completion.ubuntu_base}{completion.created_at ? ` · ${completion.created_at.slice(0, 10)}` : ''}</span>
								<Button variant="subtle" size="xs" onclick={() => copyRef(completion.ref)}>{copiedRef === completion.ref ? '복사됨' : '복사'}</Button>
							</li>
						{/each}
					</ul>
					{#if copyError}<p class="mt-2 text-xs" role="alert">{copyError}</p>{/if}
				{/if}
			</Alert>
		{/if}
		<p class="break-words text-ink-1">예상 레이어: 새 레이어 {lint.layers.new}개 ({Object.entries(lint.layers.by_instruction).map(([name, count]) => `${name} ${count}`).join(' · ')}){lint.layers.inherited > 0 ? ` + 상속 ${lint.layers.inherited}개` : ''} = 총 {lint.layers.total}개 / 상한 {lint.layers.limit}</p>
		{#if lint.warnings.length}
			<Alert tone="warning">
				<ul class="space-y-1">{#each lint.warnings as warning}<li class="break-words">{warning.message}</li>{/each}</ul>
			</Alert>
		{/if}
	{:else if !loading && !requestError}
		<p class="text-xs text-ink-2">Dockerfile을 입력하면 자동으로 검사합니다.</p>
	{/if}
</section>
