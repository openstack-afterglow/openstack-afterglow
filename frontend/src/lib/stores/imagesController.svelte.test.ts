import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '$lib/api/client';
import type { ImageInfo } from '$lib/types/compute';
import { createImagesController } from './imagesController.svelte';
import type { ImageRepositoryGroup } from './imageCatalog.svelte';

vi.mock('$lib/api/client', () => ({
  ApiError: class ApiError extends Error {},
  api: {
    get: vi.fn(),
    delete: vi.fn(),
    post: vi.fn(),
  },
}));

const images: ImageInfo[] = [
  {
    id: 'ubuntu-latest',
    name: 'ubuntu:latest',
    repository: 'ubuntu',
    tag: 'latest',
    status: 'active',
    os_distro: 'ubuntu',
    created_at: '2026-07-03T00:00:00Z',
    updated_at: '2026-07-03T00:00:00Z',
  },
  {
    id: 'ubuntu-2404',
    name: 'ubuntu:24.04',
    repository: 'ubuntu',
    tag: '24.04',
    status: 'active',
    os_distro: 'ubuntu',
    updated_at: '2026-07-02T00:00:00Z',
    created_at: '2026-07-02T00:00:00Z',
  },
  {
    id: 'ubuntu-minimal-2404',
    name: 'ubuntu-minimal:24.04',
    repository: 'ubuntu-minimal',
    tag: '24.04',
    status: 'active',
    os_distro: 'ubuntu',
    updated_at: '2026-07-01T00:00:00Z',
    created_at: '2026-07-01T00:00:00Z',
  },
  {
    id: 'ubuntu-2404-extended',
    name: 'ubuntu:24.04-extended',
    repository: 'ubuntu',
    tag: '24.04-extended',
    status: 'active',
    os_distro: 'ubuntu',
    updated_at: '2026-07-01T12:00:00Z',
    created_at: '2026-07-01T12:00:00Z',
  },
];

// UUID order deliberately disagrees with upload order so a UUID-only tie-break cannot pass.
const UUID = {
  first: '00000000-0000-4000-8000-000000000001',
  low: '44444444-4444-4444-8444-444444444444',
  middle: '88888888-8888-4888-8888-888888888888',
  high: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
  last: 'ffffffff-ffff-4fff-bfff-ffffffffffff',
};

function ubuntu2404(id: string, created_at: string | null | undefined, extra: Partial<ImageInfo> = {}): ImageInfo {
  return { id, name: 'ubuntu:24.04', repository: 'ubuntu', tag: '24.04', status: 'active', created_at, ...extra };
}

function tagGroupOf(groups: ImageRepositoryGroup[], repository = 'ubuntu', tag = '24.04') {
  const group = groups.find((entry) => entry.repository === repository)?.tags.find((entry) => entry.tag === tag);
  if (!group) throw new Error(`missing ${repository}:${tag} tag group`);
  return group;
}

function ids(list: readonly ImageInfo[]): string[] {
  return list.map((image) => image.id);
}

describe('createImagesController repository catalog', () => {
  beforeEach(() => vi.clearAllMocks());

  async function createController(fixtures: ImageInfo[] = images) {
    vi.mocked(api.get).mockResolvedValue(fixtures);
    const controller = createImagesController({
      token: () => 'token',
      projectId: () => 'project-1',
    });
    await controller.fetchImages();
    return controller;
  }

  it('groups repository tags and puts the newest tag first', async () => {
    const controller = await createController();

    expect(controller.repositoryGroups).toHaveLength(2);
    expect(controller.repositoryGroups[0].repository).toBe('ubuntu');
    expect(controller.repositoryGroups[0].images.map((image) => image.tag)).toEqual([
      'latest',
      '24.04',
      '24.04-extended',
    ]);
    expect(controller.repositoryGroups[0].latest.id).toBe('ubuntu-latest');
  });

  it('keeps the detail view unfiltered while the catalog respects tag filters', async () => {
    const controller = await createController();
    controller.tagFilter = 'latest';

    expect(controller.repositoryGroups).toHaveLength(1);
    expect(controller.repositoryGroups[0].images).toHaveLength(1);
    expect(controller.allRepositoryGroups[0].images).toHaveLength(3);
  });

  it('ranks an exact repository tag reference above a substring match in relevance mode', async () => {
    const controller = await createController();
    controller.sortMode = 'relevance';
    controller.searchQuery = 'ubuntu:24.04';

    expect(controller.filteredImages.map((image) => image.id)).toEqual([
      'ubuntu-2404',
      'ubuntu-2404-extended',
    ]);
  });
  it('orders by parsed upload instants across offsets, with invalid dates last in both directions', async () => {
    const controller = await createController([
      { id: 'a-early', name: 'alpha:early', created_at: '2026-09-01T10:00:00+09:00', status: 'active' },
      { id: 'b-mid', name: 'beta:mid', created_at: '2026-09-01T02:00:00Z', status: 'active' },
      { id: 'a-late', name: 'alpha:late', created_at: '2026-09-01T04:00:00+01:00', status: 'active' },
      { id: 'c-invalid', name: 'charlie:broken', created_at: 'not-a-date', status: 'active' },
      { id: 'd-missing', name: 'delta:missing', status: 'active' },
    ]);
    expect(controller.repositoryGroups.map((group) => group.repository)).toEqual(['alpha', 'beta', 'charlie', 'delta']);
    expect(controller.repositoryGroups[0].latest.id).toBe('a-late');
    expect(controller.repositoryGroups[0].images.map((image) => image.id)).toEqual(['a-late', 'a-early']);

    controller.sortMode = 'oldest';
    expect(controller.repositoryGroups.map((group) => group.repository)).toEqual(['beta', 'alpha', 'charlie', 'delta']);
    expect(controller.repositoryGroups[1].latest.id).toBe('a-late');
    expect(controller.filteredImages.slice(-2).map((image) => image.id)).toEqual(['c-invalid', 'd-missing']);
  });

  it('interprets naive Glance timestamps as UTC and rejects malformed calendar dates', async () => {
    const controller = await createController([
      { id: 'naive', name: 'naive:one', status: 'active', created_at: '2026-09-01T02:30:00.123456' },
      { id: 'offset', name: 'offset:one', status: 'active', created_at: '2026-09-01T11:00:00+09:00' },
      { id: 'bad-day', name: 'invalid:one', status: 'active', created_at: '2026-02-30T00:00:00Z' },
    ]);
    expect(controller.repositoryGroups.map((group) => group.repository)).toEqual(['naive', 'offset', 'invalid']);
    controller.sortMode = 'oldest';
    expect(controller.repositoryGroups.map((group) => group.repository)).toEqual(['offset', 'naive', 'invalid']);
  });

  it('keeps metadata-only updates from changing upload order', async () => {
    const controller = await createController();
    const before = controller.repositoryGroups.map((group) => group.latest.id);
    controller.updateImage({ ...images[1], updated_at: '2030-01-01T00:00:00Z' });
    expect(controller.repositoryGroups.map((group) => group.latest.id)).toEqual(before);
    expect(controller.repositoryGroups[0].images[0].id).toBe('ubuntu-latest');
  });

  it('filters mixed verification independently of visibility and resets every filter', async () => {
    const controller = await createController([
      { id: 'approved', name: 'same:approved', status: 'active', visibility: 'private', verification_status: 'verified' },
      { id: 'legacy', name: 'same:legacy', status: 'active', visibility: 'public' },
      { id: 'unknown', name: 'same:unknown', status: 'active', visibility: 'public', verification_status: 'unavailable' },
    ]);
    controller.verificationFilter = 'verified';
    expect(controller.repositoryGroups[0].images.map((image) => image.id)).toEqual(['approved']);
    expect(controller.allRepositoryGroups[0].images).toHaveLength(3);
    controller.verificationFilter = 'unverified';
    expect(controller.filteredImages.map((image) => image.id)).toEqual(['legacy']);
    controller.verificationFilter = 'unavailable';
    expect(controller.filteredImages.map((image) => image.id)).toEqual(['unknown']);
    controller.clearFilters();
    expect(controller.filteredImages).toHaveLength(3);
    expect(controller.verificationFilter).toBe('all');
    expect(controller.sortMode).toBe('newest');
  });

  it('ranks repositories by their best matching tag and honors name sorting', async () => {
    const controller = await createController([
      { id: 'old-exact', name: 'ubuntu:24.04', status: 'active', created_at: '2024-01-01T00:00:00Z' },
      { id: 'new-partial', name: 'alpha/ubuntu:24.04', status: 'active', created_at: '2026-01-01T00:00:00Z' },
    ]);
    controller.searchQuery = 'ubuntu:24.04';
    controller.sortMode = 'relevance';
    expect(controller.repositoryGroups.map((group) => group.repository)).toEqual(['ubuntu', 'alpha/ubuntu']);
    controller.sortMode = 'name';
    expect(controller.repositoryGroups.map((group) => group.repository)).toEqual(['alpha/ubuntu', 'ubuntu']);
  });

  it('resolves the current duplicate reference from exact microsecond instants across offsets, independent of input order', async () => {
    // All three land in the same UTC millisecond; only the microsecond digit orders them.
    const lexicallyLatest = ubuntu2404(UUID.last, '2026-09-01T10:00:00.000002+09:00');
    const trueNewest = ubuntu2404(UUID.first, '2026-08-31T23:00:00.000003-02:00');
    const naiveOldest = ubuntu2404(UUID.middle, '2026-09-01T01:00:00.000001');

    for (const fixtures of [[lexicallyLatest, naiveOldest, trueNewest], [trueNewest, naiveOldest, lexicallyLatest]]) {
      const controller = await createController(fixtures);
      const tag = tagGroupOf(controller.repositoryGroups);
      expect(tag.current.id).toBe(UUID.first);
      expect(tag.latest.id).toBe(UUID.first);
      expect(ids(tag.images)).toEqual([UUID.first, UUID.last, UUID.middle]);
      expect(controller.repositoryGroups[0].latest.id).toBe(UUID.first);

      controller.sortMode = 'oldest';
      expect(ids(controller.filteredImages)).toEqual([UUID.middle, UUID.last, UUID.first]);
      expect(tagGroupOf(controller.repositoryGroups).current.id).toBe(UUID.first);
    }
  });

  it('keeps a metadata-only update from promoting an older upload of the same reference', async () => {
    const older = ubuntu2404(UUID.last, '2026-01-01T00:00:00Z', { updated_at: '2026-01-01T00:00:00Z' });
    const newer = ubuntu2404(UUID.first, '2026-02-01T00:00:00Z', { updated_at: '2026-02-01T00:00:00Z' });
    const controller = await createController([older, newer]);

    controller.updateImage({ ...older, updated_at: '2030-01-01T00:00:00Z', protected: true });

    const tag = tagGroupOf(controller.repositoryGroups);
    expect(tag.images.map((image) => [image.id, image.protected ?? false])).toEqual([
      [UUID.first, false],
      [UUID.last, true],
    ]);
    expect(tag.current.id).toBe(UUID.first);
    expect(tag.latest.id).toBe(UUID.first);
    expect(tagGroupOf(controller.allRepositoryGroups).current.id).toBe(UUID.first);
  });

  it('keeps identical-content uploads as distinct UUID versions and removes only the deleted UUID', async () => {
    const digest = 'ab'.repeat(64);
    const original = ubuntu2404(UUID.first, '2026-03-01T00:00:00Z', { os_hash_algo: 'sha512', os_hash_value: digest });
    const reupload = ubuntu2404(UUID.last, '2026-03-02T00:00:00Z', { os_hash_algo: 'sha512', os_hash_value: digest });
    const controller = await createController([original, reupload]);

    expect(ids(tagGroupOf(controller.allRepositoryGroups).images)).toEqual([UUID.last, UUID.first]);
    controller.searchQuery = digest;
    expect(ids(controller.filteredImages)).toEqual([UUID.last, UUID.first]);
    expect(tagGroupOf(controller.repositoryGroups).current.id).toBe(UUID.last);

    controller.handleImageDeleted(UUID.last);
    const tag = tagGroupOf(controller.repositoryGroups);
    expect(ids(tag.images)).toEqual([UUID.first]);
    expect(tag.current.id).toBe(UUID.first);
  });

  it('breaks unknown-instant duplicate ties by UUID regardless of input order, and ranks any valid upload first', async () => {
    const unknown = [
      ubuntu2404(UUID.middle, undefined),
      ubuntu2404(UUID.last, 'not-a-date'),
      ubuntu2404(UUID.low, '2026-02-30T00:00:00Z'),
      ubuntu2404(UUID.high, null),
    ];
    for (const fixtures of [unknown, [...unknown].reverse()]) {
      const tag = tagGroupOf((await createController(fixtures)).repositoryGroups);
      expect(tag.current.id).toBe(UUID.last);
      expect(ids(tag.images)).toEqual([UUID.last, UUID.high, UUID.middle, UUID.low]);
    }

    const tag = tagGroupOf((await createController([...unknown, ubuntu2404(UUID.first, '2000-01-01T00:00:00Z')])).repositoryGroups);
    expect(tag.current.id).toBe(UUID.first);
    expect(ids(tag.images)).toEqual([UUID.first, UUID.last, UUID.high, UUID.middle, UUID.low]);
  });

  it('keeps an older visible version as tag latest while tag current tracks the newest upload in the full catalog', async () => {
    const newest = ubuntu2404(UUID.first, '2026-05-02T00:00:00Z', { verification_status: 'unverified' });
    const approved = ubuntu2404(UUID.middle, '2026-05-01T00:00:00Z', { verification_status: 'verified' });
    const oldest = ubuntu2404(UUID.last, '2026-04-01T00:00:00Z', { verification_status: 'verified' });
    // A newer upload of the same tag in another repository must not become ubuntu:24.04's current.
    const controller = await createController([oldest, images[2], approved, newest]);

    controller.verificationFilter = 'verified';
    let tag = tagGroupOf(controller.repositoryGroups);
    expect(ids(tag.images)).toEqual([UUID.middle, UUID.last]);
    expect(tag.latest.id).toBe(UUID.middle);
    expect(tag.current.id).toBe(UUID.first);
    expect(tagGroupOf(controller.allRepositoryGroups).latest.id).toBe(UUID.first);

    controller.verificationFilter = 'all';
    controller.searchQuery = UUID.last;
    tag = tagGroupOf(controller.repositoryGroups);
    expect(ids(tag.images)).toEqual([UUID.last]);
    expect(tag.latest.id).toBe(UUID.last);
    expect(tag.current.id).toBe(UUID.first);

    controller.clearFilters();
    tag = tagGroupOf(controller.repositoryGroups);
    expect(tag.latest.id).toBe(UUID.first);
    expect(tag.current.id).toBe(UUID.first);
    expect(tagGroupOf(controller.repositoryGroups, 'ubuntu-minimal').current.id).toBe('ubuntu-minimal-2404');
  });

  it('matches the exact duplicate version by full SHA-512 or UUID while current stays canonical', async () => {
    const sha512 = (suffix: string) => `${'9f'.repeat(63)}c${suffix}`;
    const versionIds = [
      '7c9e6679-7425-40de-944b-e07fc1f90ae1',
      '7c9e6679-7425-40de-944b-e07fc1f90ae2',
      '7c9e6679-7425-40de-944b-e07fc1f90ae3',
    ];
    const controller = await createController(versionIds.map((id, index) => ubuntu2404(
      id, `2026-06-0${index + 1}T00:00:00Z`, { os_hash_algo: 'sha512', os_hash_value: sha512(String(index + 1)) },
    )));

    controller.searchQuery = sha512('2').slice(0, 64);
    expect(ids(controller.filteredImages)).toHaveLength(3);

    for (const query of [sha512('2'), sha512('2').toUpperCase()]) {
      controller.searchQuery = query;
      expect(ids(controller.filteredImages)).toEqual([versionIds[1]]);
      const tag = tagGroupOf(controller.repositoryGroups);
      expect(tag.latest.id).toBe(versionIds[1]);
      expect(tag.current.id).toBe(versionIds[2]);
    }

    controller.searchQuery = versionIds[0].toUpperCase();
    expect(ids(controller.filteredImages)).toEqual([versionIds[0]]);
    expect(tagGroupOf(controller.repositoryGroups).current.id).toBe(versionIds[2]);

    controller.searchQuery = versionIds[0].slice(0, -1);
    expect(ids(controller.filteredImages)).toEqual([versionIds[2], versionIds[1], versionIds[0]]);
  });
});
