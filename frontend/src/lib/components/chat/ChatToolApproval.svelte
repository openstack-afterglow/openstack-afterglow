<script lang="ts">
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import type { ChatPart } from '$lib/api/chatContracts';
	import { taskLabelForTool } from '$lib/api/chatTaskLabels';

	export type ChatToolApproval = {
	callId: string;
	name: string;
	effect: 'read' | 'workspace_write' | 'process' | 'external_mutation';
	argumentKeys: string[];
	preview: ChatPart[];
	expiresAt: string;
};

	interface Props {
	approval: ChatToolApproval;
	busy?: boolean;
	onDecision: (callId: string, decision: 'approve' | 'deny') => void;
	}

	let { approval, busy = false, onDecision }: Props = $props();
	const taskName = $derived(taskLabelForTool(approval.name));

	function previewText(parts: ChatPart[]): string {
		return parts
			.filter((part) => part.type === 'text')
			.map((part) => part.text)
			.join('\n');
	}

	function expiresAt(value: string): string {
		const parsed = new Date(value);
		return Number.isNaN(parsed.valueOf()) ? '만료 시간 확인 불가' : parsed.toLocaleString();
	}
</script>

<div class="approval-card">
	<Card surface="subtle" padding="sm">
	<section aria-label={`${taskName} 도구 승인 요청`}>
		<div class="heading">
			<div>
				<p class="eyebrow">도구 승인 필요</p>
				<h3>{taskName}</h3>
				<p class="tool-identifier" title={approval.name}>{approval.name}</p>
			</div>
			<span class="effect">{approval.effect === 'external_mutation' ? '외부 변경' : '실행'}</span>
		</div>

		{#if previewText(approval.preview)}
			<p class="preview">{previewText(approval.preview)}</p>
		{:else}
			<p class="preview muted">승인 후 현재 상태를 다시 확인하고 요청을 실행합니다.</p>
		{/if}

		{#if approval.argumentKeys.length}
			<p class="arguments" aria-label="요청 인자">
				<span>요청 인자</span>
				{approval.argumentKeys.join(', ')}
			</p>
		{/if}

		<div class="footer">
			<p>승인 기한: {expiresAt(approval.expiresAt)}</p>
			<div class="actions">
				<Button variant="danger-outline" size="sm" disabled={busy} onclick={() => onDecision(approval.callId, 'deny')}>거부</Button>
				<Button variant="primary" size="sm" disabled={busy} onclick={() => onDecision(approval.callId, 'approve')}>{busy ? '처리 중…' : '승인'}</Button>
			</div>
		</div>
	</section>
	</Card>
</div>

<style>
	.approval-card { margin: 0.5rem 1rem; }
	.heading, .footer, .actions { display: flex; align-items: center; }
	.heading, .footer { justify-content: space-between; gap: 0.75rem; }
	.eyebrow { margin: 0 0 0.1875rem; color: var(--color-state-warning); font-size: 0.6875rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
	h3 { margin: 0; color: var(--color-ink-0); font-size: 0.875rem; }
	.tool-identifier { margin: 0.1875rem 0 0; color: var(--color-ink-2); font-family: var(--font-mono); font-size: 0.6875rem; overflow-wrap: anywhere; }
	.effect { border: 1px solid var(--color-line-2); border-radius: 999px; color: var(--color-state-warning); font-size: 0.6875rem; padding: 0.1875rem 0.5rem; white-space: nowrap; }
	.preview, .arguments { margin: 0.75rem 0 0; color: var(--color-ink-1); font-size: 0.8125rem; line-height: 1.5; white-space: pre-wrap; }
	.muted, .footer p { color: var(--color-ink-2); }
	.arguments span { color: var(--color-ink-2); margin-right: 0.5rem; }
	.footer { border-top: 1px solid var(--color-line); margin-top: 0.75rem; padding-top: 0.625rem; }
	.footer p { margin: 0; font-size: 0.6875rem; }
	.actions { gap: 0.5rem; }
	@media (max-width: 40rem) {
		.approval-card { margin-inline: 0.625rem; }
		.footer { align-items: flex-start; flex-direction: column; }
	}
</style>
