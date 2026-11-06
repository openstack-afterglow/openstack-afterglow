import { t } from '$lib/i18n/ns/images-keys';
import { compileRegexSearch, matchesRegexSearch } from './regexSearch';

const TAG_PATTERN = /^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$/;
const REPOSITORY_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]*(?::[0-9]{1,5})?(?:\/[A-Za-z0-9][A-Za-z0-9._-]*)*$/;

export interface ImageReferenceParts {
	repository: string;
	tag: string;
	name: string;
}

export function parseImageReference(value: string): ImageReferenceParts {
	const raw = value.trim();
	if (!raw || /\s|[\u0000-\u001f\u007f]/.test(raw) || raw.includes('@')) {
		throw new Error(t('imageReference.invalidName'));
	}
	const slashIndex = raw.lastIndexOf('/');
	const colonIndex = raw.lastIndexOf(':');
	const hasTag = colonIndex > slashIndex;
	const repository = hasTag ? raw.slice(0, colonIndex) : raw;
	const tag = hasTag ? raw.slice(colonIndex + 1) : 'latest';
	if (!REPOSITORY_PATTERN.test(repository) || !TAG_PATTERN.test(tag)) {
		throw new Error(t('imageReference.invalidName'));
	}
	return { repository, tag, name: `${repository}:${tag}` };
}

export function sanitizeImageFilename(filename: string): string {
	const basename = filename.replace(/\.[^.]+$/, '').trim().toLowerCase();
	const repository = basename.replace(/[^a-z0-9._/-]+/g, '-').replace(/-+/g, '-').replace(/^[-./]+|[-./]+$/g, '') || 'image';
	return `${repository}:latest`;
}
export interface SearchableImageReference {
	name: string;
	id?: string;
	os_hash_value?: string | null;
	repository?: string | null;
	tag?: string | null;
	os_distro?: string | null;
	os_type?: string | null;
}

export function imageReferenceSearchFields(image: SearchableImageReference): string[] {
	let repository = image.repository ?? '';
	let tag = image.tag ?? 'latest';
	if (!image.repository || image.tag == null) {
		try {
			const parsed = parseImageReference(image.name);
			repository = image.repository ?? parsed.repository;
			tag = image.tag ?? parsed.tag;
		} catch { /* Preserve native legacy names as searchable identities. */ }
	}
	return [
		image.name,
		repository,
		tag,
		image.id ?? '',
		image.os_hash_value ?? '',
		image.os_distro ?? '',
		image.os_type ?? '',
	];
}

export function imageReferenceMatchesQuery(image: SearchableImageReference, query: string): boolean {
	return matchesRegexSearch(compileRegexSearch(query), imageReferenceSearchFields(image));
}


