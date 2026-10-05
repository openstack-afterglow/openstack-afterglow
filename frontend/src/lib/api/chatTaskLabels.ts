import type { ContextUpdatedPayload, RunStage } from './chatContracts';
import { t } from '$lib/i18n/ns/chat-panel';

const TOOL_TASK_LABELS: Record<string, string> = {
	get managed_web_search() { return t('task.webSearch'); },
	get managed_web_fetch() { return t('task.webFetch'); },
	get managed_advisor() { return t('task.advisor'); },
	get list_my_conversations() { return t('task.listConversations'); },
	get get_conversation_detail() { return t('task.conversationDetail'); },
	get list_available_tools() { return t('task.availableTools'); },
	get afterglow_vm_delete() { return t('task.deleteVm'); },
	get afterglow_volume_delete() { return t('task.deleteVolume'); },
	get afterglow_volume_snapshot_delete() { return t('task.deleteSnapshot'); },
	get afterglow_volume_backup_delete() { return t('task.deleteBackup'); },
	get afterglow_database_instance_delete() { return t('task.deleteDatabase'); },
	get afterglow_container_delete() { return t('task.deleteContainer'); },
	get afterglow_network_delete() { return t('task.deleteNetwork'); },
	get afterglow_subnet_delete() { return t('task.deleteSubnet'); }
};

function humanizeIdentifier(value: string): string {
	return value
		.split(/[_-]+/)
		.filter(Boolean)
		.map((part) => part[0]?.toUpperCase() + part.slice(1))
		.join(' ');
}

/** Converts a server tool identifier into a user-facing task label. */
export function taskLabelForTool(toolName: string): string {
	const taskLabel = TOOL_TASK_LABELS[toolName];
	if (taskLabel) return taskLabel;
	if (toolName.startsWith('mcp__')) {
		const mcpToolName = toolName.split('__').at(-1) ?? toolName;
		return t('task.mcp', { name: humanizeIdentifier(mcpToolName) });
	}
	if (toolName.startsWith('afterglow_')) return t('task.cloud', { name: humanizeIdentifier(toolName.slice('afterglow_'.length)) });
	if (toolName === 'memory_search') return t('task.memorySearch');
	return humanizeIdentifier(toolName) || t('task.tool');
}

/** Only task-bearing run stages may be presented as live user activity. */
export function taskLabelForStage(stage: RunStage, toolName: string | null): string | null {
	if (stage === 'tool_execution' && toolName) return t('task.inProgress', { task: taskLabelForTool(toolName) });
	if (stage === 'awaiting_input') return t('task.awaitingApproval');
	return null;
}

export function taskLabelForContext(
	phase: 'compacting' | 'compacted',
	cause: ContextUpdatedPayload['cause']
): string {
	const automatic = cause === 'automatic';
	if (phase === 'compacting') return automatic ? t('task.autoCompacting') : t('task.compacting');
	return automatic ? t('task.autoCompacted') : t('task.compacted');
}
