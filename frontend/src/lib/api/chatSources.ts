import { api } from './client';
import { parseChatPartsStrict, type ChatPart } from './chatContracts';
import { isSafeCitationHttpUrl, SOURCE_IDENTIFIER } from './chatCitations';

export type RegisteredChatSource = Extract<ChatPart, { type: 'citation' }>;
export interface ChatSourceScope { token: string; projectId: string; signal?: AbortSignal }
export interface ChatSourceAsset { id: string; name: string; mime_type: string; size_bytes: number }

function identifier(value: string): string {
	if (!SOURCE_IDENTIFIER.test(value)) throw new Error('Invalid source identifier');
	return encodeURIComponent(value);
}
export async function getRegisteredChatSource(runId: string, citationId: string, scope: ChatSourceScope): Promise<RegisteredChatSource> {
	const value = await api.get<unknown>(`/api/v1/chat/runs/${identifier(runId)}/sources/${identifier(citationId)}`, scope.token, scope.projectId, { signal: scope.signal, cache: 'no-store' });
	const part = parseChatPartsStrict([value])[0];
	if (part.type !== 'citation' || part.citation_id !== citationId) throw new Error('Mismatched registered source');
	return part;
}
export async function getChatSourceAsset(assetId: string, scope: ChatSourceScope): Promise<ChatSourceAsset> {
	const value = await api.get<ChatSourceAsset>(`/api/v1/chat/assets/${identifier(assetId)}`, scope.token, scope.projectId, { signal: scope.signal, cache: 'no-store' });
	if (value.id !== assetId || typeof value.name !== 'string' || typeof value.mime_type !== 'string' || !Number.isSafeInteger(value.size_bytes) || value.size_bytes < 0) throw new Error('Invalid source asset metadata');
	return value;
}
/** A signed URL is issued only for an explicit click; never persisted or copied into Markdown. */
export async function getChatSourceDownloadLink(assetId: string, scope: ChatSourceScope): Promise<string> {
	const value = await api.get<{ url: string; expires_in: number }>(`/api/v1/chat/assets/${identifier(assetId)}/download-link`, scope.token, scope.projectId, { signal: scope.signal, cache: 'no-store' });
	if (typeof value.url !== 'string' || !isSafeCitationHttpUrl(value.url) || !Number.isSafeInteger(value.expires_in) || value.expires_in <= 0) throw new Error('Invalid source download link');
	return value.url;
}
