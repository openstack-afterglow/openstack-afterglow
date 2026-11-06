import { imageReferenceSearchFields, parseImageReference } from '$lib/utils/imageReference';
import { createTableView, type TableColumn, type TableViewState } from '$lib/utils/tableView.svelte';
import { t } from '$lib/i18n/ns/images-keys';
import { intlLocale } from '$lib/i18n/runtime.svelte';
import type { ImageInfo } from '$lib/types/compute';


export type VerificationStatus = 'verified' | 'unverified' | 'unavailable';
export interface ImageCatalogState {
  searchQuery: string;
  view: TableViewState;
}


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



export function createImageCatalog<T extends ImageInfo>(source: () => T[], canonicalSource: () => T[] = source, retained?: ImageCatalogState) {
  const state = $state<ImageCatalogState>(retained ?? { searchQuery: '', view: { sort: null, filters: {} } });
  const columns = $derived<TableColumn<T>[]>([
    { key: 'repository', label: t('catalogToolbar.repositoryLabel'), value: image => imageReferenceParts(image).repository },
    { key: 'tag', label: t('catalogToolbar.tagLabel'), value: image => imageReferenceParts(image).tag },
    { key: 'status', label: t('repositoryDetail.status'), value: image => image.status },
    { key: 'os_distro', label: t('infoSection.osDistro'), value: image => image.os_distro },
    { key: 'verification', label: t('catalogToolbar.trustLabel'), value: imageVerificationStatus, format: value => value === 'verified' ? t('catalogToolbar.verified') : value === 'unavailable' ? t('catalogToolbar.unavailable') : t('catalogToolbar.unverified') },
    { key: 'visibility', label: t('uploadModal.visibility'), value: image => image.visibility },
    { key: 'size', label: t('repositoryDetail.size'), value: image => image.size },
    { key: 'created_at', label: t('repositoryDetail.uploaded'), value: imageUploadInstant, filterValues: image => { const time = imageUploadTime(image); return [time === null ? null : new Date(time).toISOString().slice(0, 10)]; }, format: value => typeof value === 'number' ? new Date(value / 1000).toISOString().slice(0, 10) : String(value ?? '') },
    { key: 'name', label: t('imageEdit.name'), value: image => image.name },
    { key: 'id', label: t('repositoryDetail.digest'), value: image => image.os_hash_value ?? image.id },
    { key: 'disk_format', label: t('infoSection.diskFormat'), value: image => image.disk_format },
    { key: 'owner', label: t('infoSection.owner'), value: image => image.owner },
  ]);
  const newest = $derived.by(() => {
    const times = new Map(source().map(image => [image.id, imageUploadInstant(image)]));
    return [...source()].sort((a, b) => compareUploadOrder(a, b, times));
  });
  const view = createTableView<T>({ rows: () => newest, columns: () => columns, search: () => state.searchQuery, searchable: imageReferenceSearchFields, locale: intlLocale, state: state.view });
  const currentImages = $derived(currentImagesByReference(canonicalSource()));
  const filteredImages = $derived(view.rows);

  function buildGroups(images: readonly T[], orderRepresentatives = false): ImageRepositoryGroup<T>[] {
    const groups = new Map<string, T[]>();
    const sorting = orderRepresentatives && view.sort !== null;
    // Resolve newest displayed versions before applying a column order to their groups.
    let uploads = images;
    if (sorting) {
      const times = new Map(images.map(image => [image.id, imageUploadInstant(image)]));
      uploads = [...images].sort((a, b) => compareUploadOrder(a, b, times));
    }
    for (const image of uploads) {
      const repository = imageReferenceParts(image).repository;
      const entries = groups.get(repository) ?? [];
      entries.push(image);
      groups.set(repository, entries);
    }
    const result = [...groups.entries()].map(([repository, entries]): ImageRepositoryGroup<T> => {
      const tagGroups = new Map<string, ImageTagGroup<T>>();
      for (const image of entries) {
        const tag = imageReferenceParts(image).tag;
        const existing = tagGroups.get(tag);
        if (existing) existing.images.push(image);
        else tagGroups.set(tag, { tag, latest: image, current: currentImages.get(JSON.stringify([repository, tag])) ?? image, images: [image] });
      }
      const tags = [...tagGroups.values()];
      const byLatest = sorting ? new Map(tags.map(group => [group.latest, group])) : null;
      return {
        repository, images: entries, latest: entries[0],
        tags: sorting ? view.orderRows(tags.map(group => group.latest)).map(image => byLatest!.get(image)!) : tags,
      };
    });
    if (!sorting) return result;
    const byLatest = new Map(result.map(group => [group.latest, group]));
    return view.orderRows(result.map(group => group.latest)).map(image => byLatest.get(image)!);
  }
  const allRepositoryGroups = $derived(buildGroups(newest));
  const repositoryGroups = $derived(buildGroups(filteredImages, true));
  function clearFilters() { state.searchQuery = ''; view.reset(); }
  return {
    view,
    get searchQuery() { return state.searchQuery; },
    set searchQuery(value: string) { state.searchQuery = value; },
    get filteredImages() { return filteredImages; },
    get visibleRepositoryCount() { return repositoryGroups.length; },
    get repositoryGroups() { return repositoryGroups; },
    get allRepositoryGroups() { return allRepositoryGroups; },
    clearFilters,
  };
}
