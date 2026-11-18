import { t } from '$lib/i18n/ns/chat-studio';
import { api, ApiError, fetchWithAuth } from './client';
import { requireLumenCapability } from './lumenAccess';
import { downloadChatAsset, uploadChatAttachment } from './chatAttachments';
import type { AvailableModel } from './chatTree';
import type { ExperienceContext } from '$lib/utils/experience';
import { mediaGateReadiness } from './mediaReadiness';
import { decodeFrames } from './chatStream';
import { parseChatRunEvent, type ChatRunEvent } from './chatContracts';

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
export type ImageUsage = Extract<ChatRunEvent, { type: 'usage.updated' }>['payload'];
export interface ImageRunDescriptor {
	run_id: string;
	status: ImageRunStatus;
}
export interface ImageSizeLimits {
	min_pixels: number;
	max_pixels: number;
	dimension_multiple: number;
	max_edge: number;
	max_aspect_ratio: number;
}
export interface ImageGifLimits {
	min_frame_count: number;
	max_frame_count: number;
	default_frame_count: number;
	min_frame_duration_ms: number;
	max_frame_duration_ms: number;
	default_frame_duration_ms: number;
	max_total_pixels: number;
	size_auto_supported?: boolean;
}
export interface ImageCapabilities {
	available_image_variants: string[];
	max_image_count: number;
	image_backgrounds?: string[];
	image_output_formats?: string[];
	image_complexities?: string[];
	image_custom_size?: ImageSizeLimits | null;
	image_gif?: ImageGifLimits | null;
	image_output_price_per_million?: string | null;
	image_svg_author_models?: { model: string; reasoning_efforts: string[] }[];
	image_moderation_options?: string[];
	max_image_input_count?: number;
	image_mask_supported?: boolean;
	image_markup_supported?: boolean;
	image_input_fidelities?: string[];
}
export interface ImageRequest {
	model_id: string;
	prompt: string;
	size: string;
	quality: string;
	n: number;
	background?: string;
	output_format?: string;
	output_compression?: number;
	complexity?: string;
	frame_count?: number;
	frame_duration_ms?: number;
	moderation?: string;
	svg_model?: string;
	svg_reasoning_effort?: string;
}
export type ImageEditFields = ({ input_asset_id: string; input_asset_ids?: never } |
	{ input_asset_id?: never; input_asset_ids: string[] }) & {
	mask_asset_id?: string;
	markup_asset_id?: string;
	input_fidelity?: string;
};
export type ImageEditRequest = ImageRequest & ImageEditFields;
export interface ImageApiScope {
	token: string;
	projectId: string;
	experience?: ExperienceContext;
}

export function imageModelReadiness(model: ImageModel | undefined): string | null {
	if (!model) return t('imageStudioApi.selectModel');
	if (!model.provider_api_key_configured) return t('imageStudioApi.providerKeyMissing');
	const gate = model.capabilities?.feature_gates?.image_output;
	return mediaGateReadiness(gate);
}

export const imageStudioApi = {
	models: (scope: ImageApiScope) => api.get<ImageModel[]>('/api/v1/chat/models?model_kind=image', scope.token, scope.projectId, { refresh: true, experience: scope.experience }),
	capabilities: (modelId: number, scope: ImageApiScope) => api.get<ImageCapabilities>(`/api/v1/chat/capabilities?model_id=${encodeURIComponent(modelId)}&model_kind=image`, scope.token, scope.projectId, { refresh: true, experience: scope.experience }),
	async submit(kind: 'generations' | 'edits', request: ImageRequest | ImageEditRequest, scope: ImageApiScope, idempotencyKey: string, signal?: AbortSignal): Promise<ImageRunDescriptor> {
		requireLumenCapability('lumen-images_user', scope.token, scope.projectId);
		const response = await fetchWithAuth(`/api/v1/chat/images/${kind}`, {
			method: 'POST',
			credentials: 'include',
			headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
			body: JSON.stringify(request),
			signal
		}, scope.token, scope.projectId, { experience: scope.experience });
		if (!response.ok) {
			const body = await response.json().catch(() => null);
			const detail = body?.detail;
			throw new ApiError(response.status, typeof detail === 'string' ? detail : t('imageStudioApi.requestFailed', { status: response.status }));
		}
		return response.json();
	},
	run: (runId: string, scope: ImageApiScope) => api.get<ImageRun>(`/api/v1/chat/runs/${encodeURIComponent(runId)}`, scope.token, scope.projectId, { refresh: true, experience: scope.experience }),
	async usage(runId: string, scope: ImageApiScope, signal: AbortSignal): Promise<ImageUsage | null> {
		requireLumenCapability('lumen-images_user', scope.token, scope.projectId);
		const response = await fetchWithAuth(`/api/v1/chat/runs/${encodeURIComponent(runId)}/events?after_seq=0`, {
			headers: { Accept: 'text/event-stream' }, signal
		}, scope.token, scope.projectId);
		if (!response.ok || !response.body) return null;
		let usage: ImageUsage | null = null;
		for await (const frame of decodeFrames(response.body)) {
			const value = JSON.parse(frame.data);
			if (value?.run_id !== runId) return null;
			if (value.type === 'run.completed') return usage;
			if (value.type === 'usage.updated') {
				const event = parseChatRunEvent(value);
				if (event.type === 'usage.updated') usage = event.payload;
			}
		}
		return null;
	},
	cancel: (runId: string, scope: ImageApiScope) => api.post(`/api/v1/chat/runs/${encodeURIComponent(runId)}/cancel`, {}, scope.token, scope.projectId, { experience: scope.experience }),
	upload: (file: File, scope: ImageApiScope, signal?: AbortSignal) => uploadChatAttachment(file, { ...scope, signal }),
	download: (assetId: string, scope: ImageApiScope, signal?: AbortSignal) => downloadChatAsset(assetId, { ...scope, signal })
};
