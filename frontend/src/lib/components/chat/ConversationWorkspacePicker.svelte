<script lang="ts">
	import type { Workspace } from '$lib/api/chatWorkspaces';

	interface Props {
		workspaces: Workspace[];
		currentWorkspaceId: number | null;
		disabled?: boolean;
		onChange: (workspaceId: number | null) => void;
		onCreateProject: () => void;
	}
	let { workspaces, currentWorkspaceId, disabled = false, onChange, onCreateProject }: Props = $props();

	let open = $state(false);
	let root = $state<HTMLDivElement | null>(null);
	$effect(() => {
		const closeOutside = (event: PointerEvent) => {
			if (open && root && event.target instanceof Node && !root.contains(event.target)) open = false;
		};
		document.addEventListener('pointerdown', closeOutside);
		return () => document.removeEventListener('pointerdown', closeOutside);
	});
	const current = $derived(workspaces.find((w) => w.id === currentWorkspaceId) ?? null);

	function choose(id: number | null) {
		open = false;
		if (id !== currentWorkspaceId) onChange(id);
	}
</script>

<div class="wsp" bind:this={root}>
	<button
		type="button"
		class="trigger"
		{disabled}
		onclick={() => (open = !open)}
	>
		<span class="label">{current?.name ?? '프로젝트 선택'}</span>
		<svg class="chev" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="m7 10 5 5 5-5" stroke-linecap="round" stroke-linejoin="round" /></svg>
	</button>

	{#if open}
		<div class="menu" role="listbox">
			{#each workspaces as w (w.id)}
				<button type="button" class="opt" class:sel={currentWorkspaceId === w.id} role="option" aria-selected={currentWorkspaceId === w.id} onclick={() => choose(w.id)}>
					{w.name}
				</button>
			{/each}
			{#if workspaces.length > 0}
				<div class="sep"></div>
			{/if}
			<button type="button" class="opt" onclick={() => { open = false; onCreateProject(); }}>
				+ 새 프로젝트
			</button>
			{#if currentWorkspaceId !== null}
				<button type="button" class="opt" onclick={() => choose(null)}>
					프로젝트 없이 작업
				</button>
			{/if}
		</div>
	{/if}
</div>

<style>
	.wsp {
		position: relative;
		display: inline-block;
	}
	.trigger {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		min-height: 2rem;
		padding: 0.38rem 0.7rem;
		border: 0;
		border-radius: 0.65rem;
		background: color-mix(in oklab, var(--color-ink-0) 5%, transparent);
		box-shadow: none;
		color: var(--color-ink-1);
		font-size: 0.78rem;
		font-weight: 600;
		cursor: pointer;
		transition: background 0.12s, color 0.12s, transform 0.12s;
	}
	.trigger:hover:not(:disabled),
	.trigger:focus-visible {
		color: var(--color-ink-0);
		background: color-mix(in oklab, var(--color-ink-0) 9%, transparent);
		transform: translateY(-1px);
	}
	.trigger:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.label {
		max-width: 12rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.chev {
		transition: transform 0.12s;
	}
	.menu {
		position: absolute;
		bottom: calc(100% + 0.3rem);
		left: 0;
		z-index: 21;
		min-width: 11rem;
		max-height: 16rem;
		overflow-y: auto;
		background: var(--color-surface-raised);
		border: 1px solid var(--color-line);
		border-radius: 0.6rem;
		box-shadow: 0 10px 28px color-mix(in oklab, var(--color-ink-0) 20%, transparent);
		padding: 0.3rem;
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
	}
	.sep {
		height: 1px;
		margin: 0.3rem 0.25rem;
		background: var(--color-line);
	}
	.opt {
		text-align: left;
		padding: 0.4rem 0.55rem;
		border: none;
		border-radius: 0.4rem;
		background: transparent;
		color: var(--color-ink-1);
		font-size: 0.8rem;
		cursor: pointer;
		white-space: nowrap;
	}
	.opt:hover {
		background: var(--color-surface-sunken);
	}
	.opt.sel {
		color: var(--color-accent);
		font-weight: 600;
	}
</style>
