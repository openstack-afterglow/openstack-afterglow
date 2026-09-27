import { KNOWN_DISTROS } from '$lib/utils/imageOs';
import { imageReferenceMatchesQuery, imageReferenceMatchScore, parseImageReference } from '$lib/utils/imageReference';
import type { ImageInfo } from '$lib/types/compute';

export type CatalogSortMode = 'newest' | 'oldest' | 'relevance' | 'name';
export type VerificationStatus = 'verified' | 'unverified' | 'unavailable';
export type VerificationFilter = 'all' | VerificationStatus;

export interface ImageTagGroup<T extends ImageInfo = ImageInfo> {
  tag: string;
  latest: T;
  current: T;
  images: T[];
}

export interface ImageRepositoryGroup<T extends ImageInfo = ImageInfo> {
  repository: string;
  images: T[];
  latest: T;
  tags: ImageTagGroup<T>[];
}

export interface CatalogOption {
  value: string;
  label: string;
  count: number;
}

export function imageVerificationStatus(image: ImageInfo): VerificationStatus {
  return image.verification_status === 'verified' || image.verification_status === 'unavailable'
    ? image.verification_status : 'unverified';
}

export function imageReferenceParts(image: ImageInfo): { repository: string; tag: string } {
  if (image.repository && image.tag != null) return { repository: image.repository, tag: image.tag };
  try {
    const parsed = parseImageReference(image.name);
    return { repository: image.repository ?? parsed.repository, tag: image.tag ?? parsed.tag };
  } catch {
    return { repository: image.repository ?? image.name, tag: image.tag ?? 'latest' };
  }
}

export function imageUploadInstant(image: ImageInfo): number | null {
  const raw = image.created_at?.trim();
  if (!raw) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:?\d{2})?$/i.exec(raw);
  if (!match) return null;
  const [, year, month, day, hour, minute, second, fraction, zone] = match;
  const y = Number(year), m = Number(month), d = Number(day);
  if (m < 1 || m > 12 || d < 1 || d > new Date(Date.UTC(y, m, 0)).getUTCDate()
    || Number(hour) > 23 || Number(minute) > 59 || Number(second) > 59) return null;
  if (zone && zone !== 'Z' && zone !== 'z') {
    const offset = zone.slice(1).replace(':', '');
    if (Number(offset.slice(0, 2)) > 23 || Number(offset.slice(2)) > 59) return null;
  }
  const milliseconds = Date.parse(zone ? raw : `${raw}Z`);
  return Number.isFinite(milliseconds)
    ? milliseconds * 1000 + Number((fraction ?? '').padEnd(6, '0').slice(3, 6)) : null;
}

export function imageUploadTime(image: ImageInfo): number | null {
  const instant = imageUploadInstant(image);
  return instant === null ? null : Math.trunc(instant / 1000);
}

// Unknown dates remain last, even when the order is reversed. Exact ties use
// UUID for a stable alias; Glance timestamps cannot order truly simultaneous uploads.
function compareUploadDates(a: number | null, b: number | null, oldest: boolean): number {
  if (a === null) return b === null ? 0 : 1;
  if (b === null) return -1;
  return oldest ? a - b : b - a;
}

function compareIdentity(a: ImageInfo, b: ImageInfo): number {
  return a.name.localeCompare(b.name) || a.id.localeCompare(b.id);
}

function compareUploadOrder(a: ImageInfo, b: ImageInfo, times: Map<string, number | null>, oldest = false): number {
  const dateOrder = compareUploadDates(times.get(a.id) ?? null, times.get(b.id) ?? null, oldest);
  if (dateOrder) return dateOrder;
  const left = imageReferenceParts(a), right = imageReferenceParts(b);
  return left.repository.localeCompare(right.repository) || left.tag.localeCompare(right.tag) || b.id.localeCompare(a.id);
}

export function currentImagesByReference<T extends ImageInfo>(images: readonly T[]): Map<string, T> {
  const current = new Map<string, T>();
  const times = new Map<string, number | null>();
  for (const image of images) {
    times.set(image.id, imageUploadInstant(image));
    const { repository, tag } = imageReferenceParts(image);
    const key = JSON.stringify([repository, tag]);
    const previous = current.get(key);
    if (!previous || compareUploadOrder(image, previous, times) < 0) current.set(key, image);
  }
  return current;
}

function countOptions(images: readonly ImageInfo[], part: 'repository' | 'tag'): CatalogOption[] {
  const counts = new Map<string, number>();
  for (const image of images) {
    const value = imageReferenceParts(image)[part];
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => part === 'tag'
      ? (a[0] === 'latest' ? -1 : b[0] === 'latest' ? 1 : a[0].localeCompare(b[0]))
      : b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([value, count]) => ({ value, label: value, count }));
}

export function createImageCatalog<T extends ImageInfo>(source: () => T[], canonicalSource: () => T[] = source) {
  let distroFilter = $state('all');
  let searchQuery = $state('');
  let repositoryFilter = $state('all');
  let tagFilter = $state('all');
  let verificationFilter = $state<VerificationFilter>('all');
  let sortMode = $state<CatalogSortMode>('newest');

  const currentImages = $derived(currentImagesByReference(canonicalSource()));
  const filteredImages = $derived.by(() => {
    const query = searchQuery.trim();
    const list = source().filter((image) => {
      const reference = imageReferenceParts(image);
      if (distroFilter !== 'all') {
        if (distroFilter === 'other') {
          if (image.os_distro && KNOWN_DISTROS.includes(image.os_distro)) return false;
        } else if (image.os_distro !== distroFilter) return false;
      }
      if (repositoryFilter !== 'all' && reference.repository !== repositoryFilter) return false;
      if (tagFilter !== 'all' && reference.tag !== tagFilter) return false;
      if (verificationFilter !== 'all' && imageVerificationStatus(image) !== verificationFilter) return false;
      return imageReferenceMatchesQuery(image, query);
    });
    const times = new Map<string, number | null>();
    if (sortMode !== 'name') for (const image of list) times.set(image.id, imageUploadInstant(image));
    list.sort((a, b) => {
      if (sortMode === 'relevance' && query) {
        const delta = imageReferenceMatchScore(b, query) - imageReferenceMatchScore(a, query);
        if (delta) return delta;
      }
      if (sortMode === 'name') {
        const aParts = imageReferenceParts(a);
        const bParts = imageReferenceParts(b);
        return aParts.repository.localeCompare(bParts.repository)
          || aParts.tag.localeCompare(bParts.tag) || compareIdentity(a, b);
      }
      return compareUploadOrder(a, b, times, sortMode === 'oldest');
    });
    return list;
  });

  const distroGroups = $derived.by(() => {
    const images = source();
    const counts: Record<string, number> = { all: images.length };
    for (const image of images) {
      const distro = image.os_distro && KNOWN_DISTROS.includes(image.os_distro) ? image.os_distro : 'other';
      counts[distro] = (counts[distro] ?? 0) + 1;
    }
    return counts;
  });

  const repositoryOptions = $derived(countOptions(source(), 'repository'));
  const tagOptions = $derived(countOptions(repositoryFilter === 'all' ? source() : source().filter((image) =>
    imageReferenceParts(image).repository === repositoryFilter), 'tag'));
  const visibleRepositoryCount = $derived.by(() => {
    const repositories = new Set<string>();
    for (const image of filteredImages) repositories.add(imageReferenceParts(image).repository);
    return repositories.size;
  });

  function buildGroups(images: readonly T[], query: string): ImageRepositoryGroup<T>[] {
    const groups = new Map<string, T[]>();
    const times = new Map<string, number | null>();
    for (const image of images) {
      times.set(image.id, imageUploadInstant(image));
      const repository = imageReferenceParts(image).repository;
      const entries = groups.get(repository) ?? [];
      entries.push(image);
      groups.set(repository, entries);
    }
    const relevance = new Map<string, number>();
    const result = [...groups.entries()].map(([repository, entries]): ImageRepositoryGroup<T> => {
      entries.sort((a, b) => compareUploadOrder(a, b, times));
      const tagGroups = new Map<string, ImageTagGroup<T>>();
      for (const image of entries) {
        const tag = imageReferenceParts(image).tag;
        const existing = tagGroups.get(tag);
        if (existing) existing.images.push(image);
        else tagGroups.set(tag, {
          tag, latest: image, current: currentImages.get(JSON.stringify([repository, tag])) ?? image, images: [image],
        });
      }
      if (sortMode === 'relevance' && query) {
        let best = -1;
        for (const image of entries) best = Math.max(best, imageReferenceMatchScore(image, query));
        relevance.set(repository, best);
      }
      return { repository, images: entries, latest: entries[0], tags: [...tagGroups.values()] };
    });
    result.sort((a, b) => {
      if (sortMode === 'relevance' && query) {
        const delta = (relevance.get(b.repository) ?? -1) - (relevance.get(a.repository) ?? -1);
        if (delta) return delta;
      }
      if (sortMode === 'name') return a.repository.localeCompare(b.repository);
      return compareUploadDates(times.get(a.latest.id) ?? null, times.get(b.latest.id) ?? null, sortMode === 'oldest')
        || a.repository.localeCompare(b.repository);
    });
    return result;
  }

  const allRepositoryGroups = $derived(buildGroups(source(), ''));
  const repositoryGroups = $derived(buildGroups(filteredImages, searchQuery.trim()));
  function clearFilters() {
    searchQuery = '';
    repositoryFilter = 'all';
    tagFilter = 'all';
    distroFilter = 'all';
    verificationFilter = 'all';
    sortMode = 'newest';
  }

  return {
    get distroFilter() { return distroFilter; },
    set distroFilter(value: string) { distroFilter = value; },
    get searchQuery() { return searchQuery; },
    set searchQuery(value: string) { searchQuery = value; },
    get repositoryFilter() { return repositoryFilter; },
    set repositoryFilter(value: string) { repositoryFilter = value; },
    get tagFilter() { return tagFilter; },
    set tagFilter(value: string) { tagFilter = value; },
    get verificationFilter() { return verificationFilter; },
    set verificationFilter(value: VerificationFilter) { verificationFilter = value; },
    get sortMode() { return sortMode; },
    set sortMode(value: CatalogSortMode) { sortMode = value; },
    get filteredImages() { return filteredImages; },
    get distroGroups() { return distroGroups; },
    get repositoryOptions() { return repositoryOptions; },
    get tagOptions() { return tagOptions; },
    get visibleRepositoryCount() { return visibleRepositoryCount; },
    get repositoryGroups() { return repositoryGroups; },
    get allRepositoryGroups() { return allRepositoryGroups; },
    clearFilters,
  };
}
