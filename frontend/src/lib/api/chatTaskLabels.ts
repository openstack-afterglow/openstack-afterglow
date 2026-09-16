import type { ContextUpdatedPayload, RunStage } from './chatContracts';

const TOOL_TASK_LABELS: Record<string, string> = {
	managed_web_search: '웹 검색',
	managed_web_fetch: '웹 페이지 확인',
	managed_advisor: '전문가 검토',
	list_my_conversations: '대화 목록 확인',
	get_conversation_detail: '대화 내용 확인',
	list_available_tools: '필요한 도구 확인',
	afterglow_vm_delete: '가상 머신 삭제',
	afterglow_volume_delete: '볼륨 삭제',
	afterglow_volume_snapshot_delete: '볼륨 스냅샷 삭제',
	afterglow_volume_backup_delete: '볼륨 백업 삭제',
	afterglow_database_instance_delete: '데이터베이스 인스턴스 삭제',
	afterglow_container_delete: '컨테이너 삭제',
	afterglow_network_delete: '네트워크 삭제',
	afterglow_subnet_delete: '서브넷 삭제'
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
	if (TOOL_TASK_LABELS[toolName]) return TOOL_TASK_LABELS[toolName];
	if (toolName.startsWith('mcp__')) {
		const mcpToolName = toolName.split('__').at(-1) ?? toolName;
		return `MCP: ${humanizeIdentifier(mcpToolName)}`;
	}
	if (toolName.startsWith('afterglow_')) return `클라우드: ${humanizeIdentifier(toolName.slice('afterglow_'.length))}`;
	if (toolName === 'memory_search') return '메모리 검색';
	return humanizeIdentifier(toolName) || '도구 작업';
}

/** Only task-bearing run stages may be presented as live user activity. */
export function taskLabelForStage(stage: RunStage, toolName: string | null): string | null {
	if (stage === 'tool_execution' && toolName) return `${taskLabelForTool(toolName)} 진행 중`;
	if (stage === 'awaiting_input') return '작업 승인을 기다리는 중';
	return null;
}

export function taskLabelForContext(
	phase: 'compacting' | 'compacted',
	cause: ContextUpdatedPayload['cause']
): string {
	const automatic = cause === 'automatic';
	if (phase === 'compacting') return automatic ? '컨텍스트 자동 압축 중' : '컨텍스트 압축 중';
	return automatic ? '컨텍스트 자동 압축 완료' : '컨텍스트 압축 완료';
}
