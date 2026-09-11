<script lang="ts">
	import { citationDomain, citationLabel, type Citation } from '$lib/api/chatCitations';

	interface Props {
		open: boolean;
		citations: Citation[];
		onClose: () => void;
	}
	let { open, citations, onClose }: Props = $props();
</script>

{#if open}
	<div
		class="overlay"
		role="button"
		tabindex="-1"
		aria-label="닫기"
		onclick={onClose}
		onkeydown={(e) => e.key === 'Escape' && onClose()}
	></div>
	<div class="drawer" role="dialog" aria-label="대화 출처">
		<header class="head">
			<h2>출처 {citations.length}</h2>
			<button type="button" class="close" onclick={onClose} aria-label="닫기">
				<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M18 6L6 18M6 6l12 12" stroke-linecap="round" /></svg>
			</button>
		</header>

		{#if citations.length === 0}
			<div class="empty">이 대화에는 아직 출처가 없습니다.</div>
		{:else}
			<ol class="list">
				{#each citations as c, i (`${c.source_kind}:${c.url ?? c.document_index}:${i}`)}
					<li>
						{#if c.url}
							<a href={c.url} target="_blank" rel="noopener noreferrer nofollow">
								<div class="top">
									<span class="num">{i + 1}</span>
									<span class="title">{citationLabel(c)}</span>
								</div>
								<div class="domain">{citationDomain(c.url)}</div>
								{#if c.snippet}
									<div class="snippet">{c.snippet}</div>
								{/if}
							</a>
						{:else}
							<div class="document">
								<div class="top">
									<span class="num">{i + 1}</span>
									<span class="title">{citationLabel(c)}</span>
								</div>
								<div class="domain">입력 문서</div>
								{#if c.snippet}
									<div class="snippet">{c.snippet}</div>
								{/if}
							</div>
						{/if}
					</li>
				{/each}
			</ol>
		{/if}
	</div>
{/if}

<style>
	.overlay {
		position: fixed;
		inset: 0;
		background: color-mix(in oklab, var(--color-ink-0) 45%, transparent);
		z-index: 40;
		border: none;
	}
	.drawer {
		position: fixed;
		top: 0;
		right: 0;
		bottom: 0;
		width: min(24rem, 92vw);
		background: var(--color-surface-base);
		border-left: 1px solid var(--color-line);
		z-index: 41;
		display: flex;
		flex-direction: column;
		box-shadow: -8px 0 24px color-mix(in oklab, var(--color-ink-0) 12%, transparent);
	}
	.head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.9rem 1rem;
		border-bottom: 1px solid var(--color-line);
	}
	.head h2 {
		margin: 0;
		font-size: 0.95rem;
		font-weight: 650;
		color: var(--color-ink-0);
	}
	.close {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 2rem;
		height: 2rem;
		border-radius: 0.45rem;
		border: none;
		background: transparent;
		color: var(--color-ink-3);
		cursor: pointer;
	}
	.close:hover {
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
	}
	.empty {
		padding: 2rem 1rem;
		text-align: center;
		font-size: 0.82rem;
		color: var(--color-ink-3);
	}
	.list {
		list-style: none;
		margin: 0;
		padding: 0.6rem;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}
	.list a,
	.document {
		padding: 0.6rem 0.7rem;
		border-radius: 0.5rem;
		border: 1px solid var(--color-line);
		text-decoration: none;
		background: var(--color-surface-raised);
		color: var(--color-ink-1);
	}
	.list a:hover {
		border-color: var(--color-accent);
	}
	.top {
		display: flex;
		align-items: baseline;
		gap: 0.45rem;
	}
	.num {
		flex-shrink: 0;
		min-width: 1.2rem;
		height: 1.2rem;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		border-radius: 0.3rem;
		background: var(--color-surface-sunken);
		border: 1px solid var(--color-line);
		font-size: 0.66rem;
		color: var(--color-ink-3);
		font-variant-numeric: tabular-nums;
	}
	.title {
		font-size: 0.82rem;
		font-weight: 600;
		line-height: 1.35;
		word-break: break-word;
	}
	.domain {
		margin-top: 0.2rem;
		padding-left: 1.65rem;
		font-size: 0.7rem;
		color: var(--color-accent);
	}
	.snippet {
		margin-top: 0.35rem;
		padding-left: 1.65rem;
		font-size: 0.74rem;
		line-height: 1.5;
		color: var(--color-ink-3);
		display: -webkit-box;
		-webkit-line-clamp: 3;
		line-clamp: 3;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
</style>
