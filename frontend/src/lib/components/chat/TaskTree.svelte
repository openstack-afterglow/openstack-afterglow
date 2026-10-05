<script lang="ts">
	import { t } from '$lib/i18n/ns/chat-studio';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';

	export interface ChatTask { childRunId: string; agentId: number; role: string; position: number; status: 'queued' | 'running' | 'completed' | 'failed' | 'canceled'; summary?: string; }
	interface Props { tasks: ChatTask[]; }
	let { tasks }: Props = $props();
</script>

<section class="task-tree" aria-label={t('taskTree.childAgentTasks')}>
	{#each [...tasks].sort((a, b) => a.position - b.position) as task (task.childRunId)}
		<div class="task"><div><strong>{task.role}</strong>{#if task.summary}<p>{task.summary}</p>{/if}</div><StatusChip status={task.status} /></div>
	{/each}
</section>

<style>
	.task-tree { display: grid; gap: .4rem; }
	.task { display: flex; justify-content: space-between; align-items: start; gap: .75rem; border-left: 2px solid var(--color-line-2); padding: .35rem .5rem; color: var(--color-ink-2); }
	strong { color: var(--color-ink-1); font-size: .8rem; }
	p { margin: .15rem 0 0; font-size: .75rem; }
</style>
