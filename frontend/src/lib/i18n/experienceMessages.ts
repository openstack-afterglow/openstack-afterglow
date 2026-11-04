import type { Locale } from './locales';
import { EXPERIENCE_CATALOG_REVISION } from './experienceCatalogRevision';

/** Captured alongside formatting; never contains values, formatted text, DOM text or raw errors. */
export interface ExperienceMessageMetadata {
	readonly key: string | null;
	readonly locale: Locale | 'unknown';
	readonly catalog_revision: string;
	readonly tone: 'neutral' | 'info' | 'success' | 'warning' | 'danger';
	readonly restoration: 'restored' | 'redacted' | 'unavailable';
}

export function unavailableExperienceMessage(
	tone: ExperienceMessageMetadata['tone'] = 'neutral',
): ExperienceMessageMetadata {
	return Object.freeze({
		key: null,
		locale: 'unknown',
		catalog_revision: EXPERIENCE_CATALOG_REVISION,
		tone,
		restoration: 'unavailable',
	});
}
