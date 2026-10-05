import { t } from '$lib/i18n/ns/images-keys';

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

export function imageReferenceSearchText(image: SearchableImageReference): string {
	return [
		image.name,
		image.repository ?? '',
		image.tag ?? 'latest',
		image.id ?? '',
		image.os_hash_value ?? '',
		image.os_distro ?? '',
		image.os_type ?? '',
	].join(' ').toLocaleLowerCase();
}

export function imageReferenceMatchesQuery(image: SearchableImageReference, query: string): boolean {
	const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
	if (terms.length === 0) return true;
	const haystack = imageReferenceSearchText(image);
	return terms.every((term) => haystack.includes(term));
}

export function imageReferenceMatchScore(image: SearchableImageReference, query: string): number {
	const normalizedQuery = query.trim().toLocaleLowerCase();
	if (!normalizedQuery) return 0;
	const name = image.name.toLocaleLowerCase();
	const repository = (image.repository ?? '').toLocaleLowerCase();
	const tag = (image.tag ?? 'latest').toLocaleLowerCase();
	if (name === normalizedQuery) return 100;
	if (repository === normalizedQuery) return 80;
	if (tag === normalizedQuery) return 60;
	if (name.startsWith(normalizedQuery)) return 40;
	if (repository.startsWith(normalizedQuery)) return 30;
	return imageReferenceMatchesQuery(image, normalizedQuery) ? 10 : -1;
}
