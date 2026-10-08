import type { ChatFeatureOptions } from './chatContracts';
import { t } from '$lib/i18n/ns/chat-settings';

export type LumenAccess = (leaf: string) => boolean;
export const lumenLeaf = (action: string) => `lumen-${action}`;
export const permissionReason = (leaf: string) => t('permissions.required', { leaf });

/** Leaves are independent. Never derive service authority from project roles. */
export function outputPermission(parts: readonly { type: string }[], allows: LumenAccess): string | null {
	for (const part of parts) {
		const leaves = part.type === 'image' ? ['images_user'] : part.type === 'audio' ? ['audio_user'] : part.type === 'video' ? ['images_user', 'audio_user'] : [];
		for (const action of leaves) if (!allows(lumenLeaf(action))) return lumenLeaf(action);
	}
	return null;
}

export function textOnlyToolPolicy(features: ChatFeatureOptions): void {
	features.tool_policy.mode = 'none';
	features.tool_policy.enabled_tool_ids = [];
	features.tool_policy.enabled_mcp_ids = [];
	features.web_search.enabled = false;
	features.web_fetch.enabled = false;
	features.advisor.enabled = false;
}

/** Recheck saved/retried payloads as well as the currently visible composer. */
export function chatRequestPermission(body: unknown, allows: LumenAccess): string | null {
	if (!allows('lumen-chat_user')) return 'lumen-chat_user';
	// Attached inputs are existing owned assets, not paid media generation.
	const request = body as { agent_id?: unknown; skill_ids?: number[]; features?: ChatFeatureOptions } | null;
	const features = request?.features;
	if (!allows('lumen-tools_user') && (request?.agent_id != null || request?.skill_ids?.length || features?.web_search.enabled || features?.web_fetch.enabled || features?.advisor.enabled || (features && features.tool_policy.mode !== 'none'))) return 'lumen-tools_user';
	for (const modality of features?.output_modalities ?? []) {
		const missing = outputPermission([{ type: modality }], allows);
		if (missing) return missing;
	}
	return null;
}
