export interface ModelCatalogRow {
	id: number;
	provider_id?: number;
	provider?: string | null;
	provider_type?: string | null;
	model_name: string;
	display_name: string;
}

export interface ModelProvider<T extends ModelCatalogRow> {
	key: string;
	label: string | null;
	models: T[];
}

export function modelProviderKey(model: ModelCatalogRow): string {
	return model.provider_id == null
		? `provider:${model.provider ?? model.provider_type ?? ''}`
		: String(model.provider_id);
}

export function groupModelProviders<T extends ModelCatalogRow>(models: readonly T[]): ModelProvider<T>[] {
	const groups = new Map<string, ModelProvider<T>>();
	for (const model of models) {
		const key = modelProviderKey(model);
		const existing = groups.get(key);
		if (existing) existing.models.push(model);
		else groups.set(key, { key, label: model.provider ?? model.provider_type ?? null, models: [model] });
	}
	return [...groups.values()];
}

export function resolveCatalogModel<T extends ModelCatalogRow>(
	models: readonly T[], rowId?: number | null, legacyName?: string | null
): T | undefined {
	if (rowId != null) return models.find((model) => model.id === rowId);
	if (!legacyName) return undefined;
	let match: T | undefined;
	for (const model of models) {
		if (model.model_name !== legacyName) continue;
		if (match) return undefined;
		match = model;
	}
	return match;
}

export const LAST_CHAT_MODEL_ID = 'chat:lastModelId';
const LEGACY_CHAT_MODEL = 'chat:lastModel';

export function restoreChatModel<T extends ModelCatalogRow>(models: readonly T[], storage: Storage): T | null | undefined {
	const saved = storage.getItem(LAST_CHAT_MODEL_ID);
	if (saved !== null) return resolveCatalogModel(models, Number(saved)) ?? null;
	const name = storage.getItem(LEGACY_CHAT_MODEL);
	if (name === null) return undefined;
	const legacy = resolveCatalogModel(models, null, name);
	if (legacy) persistChatModel(storage, legacy.id);
	return legacy ?? null;
}

export function persistChatModel(storage: Storage, rowId: number): void {
	storage.setItem(LAST_CHAT_MODEL_ID, String(rowId));
	storage.removeItem(LEGACY_CHAT_MODEL);
}
