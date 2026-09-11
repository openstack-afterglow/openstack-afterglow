<script lang="ts">
	import type { ModelCapabilities } from '$lib/api/chatContracts';

	interface Props {
		caps?: ModelCapabilities | null;
		/** 'sm' 작은 배지(입력창 하단·리스트), 'xs' 더 작게(행 인라인) */
		size?: 'sm' | 'xs';
		/** 라벨 숨기고 아이콘만 */
		iconsOnly?: boolean;
	}
	let { caps = null, size = 'sm', iconsOnly = false }: Props = $props();

	interface Badge {
		key: string;
		label: string;
		title: string;
	}
	const badges = $derived.by((): Badge[] => {
		if (!caps) return [];
		const out: Badge[] = [];
		if (caps.vision) out.push({ key: 'vision', label: 'Vision', title: '이미지 입력 지원' });
		if (caps.reasoning) out.push({ key: 'think', label: 'Think', title: '추론(thinking) 지원' });
		if (caps.tool_call) out.push({ key: 'tools', label: 'Tools', title: '도구 호출 지원' });
		if (caps.web_search) out.push({ key: 'search', label: 'Search', title: '웹 검색 지원' });
		if (caps.attachment && !caps.vision)
			out.push({ key: 'files', label: 'Files', title: '파일 첨부 지원' });
		return out;
	});
</script>

{#if badges.length}
	<div class="badges {size}">
		{#each badges as b (b.key)}
			<span class="badge {b.key}" title={b.title}>
				{#if b.key === 'vision'}
					<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" /><circle cx="12" cy="12" r="2.6" /></svg>
				{:else if b.key === 'think'}
					<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M9.5 21h5M12 3a6 6 0 0 1 4 10.5c-.6.6-1 1.4-1 2.2V17H9v-1.3c0-.8-.4-1.6-1-2.2A6 6 0 0 1 12 3z" stroke-linecap="round" stroke-linejoin="round" /></svg>
				{:else if b.key === 'tools'}
					<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18v3h3l6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.5-2.5 2.5-2.5z" stroke-linejoin="round" /></svg>
				{:else if b.key === 'search'}
					<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.35-4.35" stroke-linecap="round" /></svg>
				{:else}
					<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><path d="M21 8l-9 9a5 5 0 0 1-7-7l9-9a3.5 3.5 0 0 1 5 5l-9 9a2 2 0 0 1-3-3l8-8" stroke-linecap="round" stroke-linejoin="round" /></svg>
				{/if}
				{#if !iconsOnly}<span class="label">{b.label}</span>{/if}
			</span>
		{/each}
	</div>
{/if}

<style>
	.badges {
		display: inline-flex;
		flex-wrap: wrap;
		gap: 0.3rem;
		align-items: center;
	}
	.badge {
		display: inline-flex;
		align-items: center;
		gap: 0.22rem;
		padding: 0.12rem 0.4rem;
		border-radius: 999px;
		border: 1px solid var(--color-line);
		background: var(--color-surface-sunken);
		color: var(--color-ink-2);
		font-size: 0.66rem;
		font-weight: 600;
		line-height: 1.2;
		white-space: nowrap;
	}
	.badges.xs .badge {
		padding: 0.08rem 0.32rem;
		font-size: 0.6rem;
	}
	.badge.vision {
		color: color-mix(in oklab, var(--color-accent) 85%, var(--color-ink-1));
	}
	.badge.think {
		color: color-mix(in oklab, var(--color-accent-2) 70%, var(--color-ink-1));
	}
	.badge.tools {
		color: color-mix(in oklab, var(--color-state-success) 70%, var(--color-ink-1));
	}
	.badge.search {
		color: color-mix(in oklab, var(--color-state-info) 85%, var(--color-ink-1));
	}
	.label {
		display: inline-block;
	}
</style>
