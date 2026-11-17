import { t } from '$lib/i18n/ns/chat-studio';
import type { ModelCapabilities } from './chatContracts';

type FeatureGate = NonNullable<ModelCapabilities['feature_gates']>[string];

/** Translate authoritative gates without mistaking route/pricing failure for unsupported models. */
export function mediaGateReadiness(gate: FeatureGate | undefined): string | null {
	if (!gate) return t('mediaReadiness.unverified');
	if (gate.reason_code === 'asset_pipeline_unavailable') return t('mediaReadiness.assets');
	if (gate.reason_code === 'route_unavailable') return t('mediaReadiness.route');
	if (gate.available !== true || gate.mode !== 'native') return t('mediaReadiness.unverified');
	if (gate.pricing_available !== true) return t('mediaReadiness.price');
	return null;
}

export function mediaReadyLabel(): string {
	return t('mediaReadiness.ready');
}
