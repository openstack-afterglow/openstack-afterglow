import { t } from '$lib/i18n/ns/chat-studio';
import { api, ApiError, fetchWithAuth } from './client';
import { requireLumenCapability } from './lumenAccess';
import { downloadChatAsset, uploadChatAttachment } from './chatAttachments';
import type { AvailableModel } from './chatTree';

export interface ImageModel extends AvailableModel {
	provider_api_key_configured?: boolean;
}

export type ImageRunStatus = 'queued' | 'running' | 'waiting_resource' | 'finalizing' | 'completed' | 'failed' | 'canceled';
export interface ImageOutputAsset {
	asset_id: string;
	mime_type: string;
	size_bytes: number;
	download_url: string;
}
export interface ImageRun {
	run_id: string;
	status: ImageRunStatus;
	terminal: boolean;
	output_assets: ImageOutputAsset[];
}
export interface ImageRunDescriptor {
	run_id: string;
	status: ImageRunStatus;
}
export interface ImageCapabilities {
	available_image_variants: string[];
	max_image_count: number;
}
export interface ImageRequest {
	model_id: string;
	prompt: string;
	size: string;
	quality: string;
	n: number;
}
export interface ImageEditRequest extends ImageRequest {
	input_asset_id: string;
}
export interface ImageApiScope {
	token: string;
	projectId: string;
}

export function imageModelReadiness(model: ImageModel | undefined): string | null {
	if (!model) return t('imageStudioApi.selectModel');
	if (!model.provider_api_key_configured) return t('imageStudioApi.providerKeyMissing');
	const gate = model.capabilities?.feature_gates?.image_output;
	if (!gate || !gate.available || gate.mode === 'none' || gate.reason_code === 'route_unavailable') return gate?.reason_code ? t('imageStudioApi.routeUnavailableReason', { reason: gate.reason_code }) : t('imageStudioApi.routeUnavailable');
	if (!gate.pricing_available) return t('imageStudioApi.pricingMissing');
	return null;
}

export const imageStudioApi = {
	models: (scope: ImageApiScope) => api.get<ImageModel[]>('/api/v1/chat/models?model_kind=image', scope.token, scope.projectId, { refresh: true }),
	capabilities: (modelId: number, scope: ImageApiScope) => api.get<ImageCapabilities>(`/api/v1/chat/capabilities?model_id=${encodeURIComponent(modelId)}&model_kind=image`, scope.token, scope.projectId, { refresh: true }),
	async submit(kind: 'generations' | 'edits', request: ImageRequest | ImageEditRequest, scope: ImageApiScope, idempotencyKey: string, signal?: AbortSignal): Promise<ImageRunDescriptor> {
		requireLumenCapability('lumen-images_user', scope.token, scope.projectId);
		const response = await fetchWithAuth(`/api/v1/chat/images/${kind}`, {
			method: 'POST',
			credentials: 'include',
			headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
			body: JSON.stringify(request),
			signal
		}, scope.token, scope.projectId);
		if (!response.ok) {
			const body = await response.json().catch(() => null);
			const detail = body?.detail;
			throw new ApiError(response.status, typeof detail === 'string' ? detail : t('imageStudioApi.requestFailed', { status: response.status }));
		}
		return response.json();
	},
	run: (runId: string, scope: ImageApiScope) => api.get<ImageRun>(`/api/v1/chat/runs/${encodeURIComponent(runId)}`, scope.token, scope.projectId, { refresh: true }),
	cancel: (runId: string, scope: ImageApiScope) => api.post(`/api/v1/chat/runs/${encodeURIComponent(runId)}/cancel`, {}, scope.token, scope.projectId),
	upload: (file: File, scope: ImageApiScope, signal?: AbortSignal) => uploadChatAttachment(file, { ...scope, signal }),
	download: (assetId: string, scope: ImageApiScope, signal?: AbortSignal) => downloadChatAsset(assetId, { ...scope, signal })
};
