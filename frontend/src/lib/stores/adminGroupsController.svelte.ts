import { untrack } from 'svelte';
import { api, ApiError } from '$lib/api/client';
import type { Group, GroupCandidates, GroupMember, User } from '$lib/types/adminGroup';
import { domainsApi, type AdminDomain } from '$lib/api/domains';
import { t } from '$lib/i18n/ns/admin-identity';
import { t as td } from '$lib/i18n/ns/domain-admin';
import { beginExperienceAction, beginExperienceLoad, experienceState, experienceApplied, experienceDiscarded, type ExperienceContext } from '$lib/utils/experience';

export interface AdminGroupsControllerOpts {
  token: () => string | undefined;
  projectId: () => string | undefined;
  domainId: () => string;
  actorId?: () => string | undefined;
  owner?: () => string;
}

export function createAdminGroupsController(opts: AdminGroupsControllerOpts) {
  let groups = $state<Group[]>([]);
  let loading = $state(true);
  let refreshing = $state(false);
  let error = $state('');
  let showCreate = $state(false);
  let creating = $state(false);
  let createError = $state('');
  let editGroup = $state<Group | null>(null);
  let updating = $state(false);
  let editError = $state('');
  let deleteGroup = $state<Group | null>(null);
  let deleting = $state(false);
  let deleteError = $state('');
  // The group this page just created; only its row carries the guided-tour delete anchor.
  let createdGroupId = $state<string | null>(null);
  let expandedGroup = $state<string | null>(null);
  let groupMembers = $state<Record<string, GroupMember[]>>({});
  let membersLoading = $state<Record<string, boolean>>({});
  let membersError = $state<Record<string, string>>({});
  let allUsers = $state<User[]>([]);
  let usersLoading = $state(false);
  let usersOwns: (() => boolean) | null = null;
  let usersError = $state('');
  let addMemberError = $state<Record<string, string>>({});
  let addMemberSaving = $state<Record<string, boolean>>({});
  let userDomainId = $state('');
  let sourceDomains = $state<AdminDomain[]>([]);
  let sourceDomainsLoading = $state(false);
  let sourceDomainsError = $state('');
  let sourceDomainsLoaded = false;
  let sourceDomainsGeneration = 0;
  let sourceGeneration = 0;
  let epoch = 0;
  let listGeneration = 0;
  let usersGeneration = 0;
  const memberGenerations: Record<string, number> = {};
  const ownerKey = $derived(JSON.stringify([
    opts.owner?.(), !!opts.token(), opts.projectId(), opts.domainId(), opts.actorId?.(),
  ]));

  function capture() {
    const generation = epoch;
    const token = opts.token();
    const projectId = opts.projectId();
    const domainId = opts.domainId();
    const actorId = opts.actorId?.();
    const owner = ownerKey;
    return {
      token, projectId, domainId,
      owns: () => generation === epoch && !!domainId && !!opts.token() && ownerKey === owner
        && opts.domainId() === domainId && opts.projectId() === projectId && opts.actorId?.() === actorId,
      path: (path: string) => `${path}${path.includes('?') ? '&' : '?'}domain_id=${encodeURIComponent(domainId)}`,
    };
  }
  const message = (e: unknown, fallback: Parameters<typeof t>[0]) => e instanceof ApiError ? e.message : t(fallback);
  const ownsGroup = (id: string) => groups.some((group) => group.id === id && group.domain_id === opts.domainId());

  $effect(() => {
    void ownerKey;
    untrack(() => {
      epoch += 1;
      groups = []; allUsers = []; groupMembers = {}; membersLoading = {}; membersError = {};
      addMemberError = {}; addMemberSaving = {}; usersError = ''; error = '';
      usersLoading = false; usersOwns = null;
      sourceGeneration += 1; sourceDomainsGeneration += 1;
      userDomainId = ''; sourceDomains = []; sourceDomainsLoading = false;
      sourceDomainsError = ''; sourceDomainsLoaded = false;
      showCreate = false; editGroup = null; deleteGroup = null; expandedGroup = null; createdGroupId = null;
      creating = false; updating = false; deleting = false;
      createError = ''; editError = ''; deleteError = '';
      void load();
    });
    return () => { epoch += 1; };
  });

  async function load() {
    await loadAttempt(false);
  }

  async function loadAttempt(replacement: boolean, inherited?: ExperienceContext) {
    const experience = inherited ?? beginExperienceLoad('iam', 'resource.list');
    const request = experience ? api.withExperience(experience) : api;
    const scope = capture();
    if (!scope.owns()) { experienceDiscarded(experience, 'scope_changed'); loading = false; return; }
    const generation = ++listGeneration;
    const owns = () => scope.owns() && generation === listGeneration;
    if (groups.length === 0) loading = true;
    else refreshing = true;
    error = '';
    experienceState(experience, 'loading');
    try {
      const res = await request.get<Group[]>(scope.path('/api/v1/admin/groups'), scope.token, scope.projectId);
      if (!owns()) { experienceDiscarded(experience, 'stale'); return; }
      if (res.some((group) => group.domain_id !== scope.domainId)) throw new Error('foreign domain');
      groups = res;
      experienceState(experience, res.length ? 'ready' : 'empty');
      void experienceApplied(experience, {}, owns);
    } catch (e) {
      if (owns() && !replacement && e instanceof DOMException && e.name === 'AbortError') {
        experienceDiscarded(experience, 'aborted');
        await loadAttempt(true, experience);
      } else if (owns()) {
        groups = []; error = message(e, 'groupController.loadFailed');
        experienceState(experience, 'error');
        void experienceApplied(experience, {}, owns);
      }
      else experienceDiscarded(experience, 'stale');
    } finally { if (owns()) { loading = false; refreshing = false; } }
  }

  function clearCandidates() {
    sourceGeneration += 1;
    allUsers = []; usersOwns = null; usersError = ''; usersLoading = false;
  }

  async function loadSourceDomains(refresh = false) {
    await loadSourceDomainsWithExperience(refresh);
  }

  async function loadSourceDomainsWithExperience(refresh = false, inherited?: ExperienceContext) {
    const scope = capture();
    if (!scope.owns()) { experienceDiscarded(inherited, 'scope_changed'); return; }
    if (sourceDomainsLoading || (sourceDomainsLoaded && !refresh)) return;
    const generation = ++sourceDomainsGeneration;
    const owns = () => scope.owns() && generation === sourceDomainsGeneration;
    const experience = inherited ?? beginExperienceLoad('iam', 'resource.list');
    experienceState(experience, 'loading');
    sourceDomainsLoading = true; sourceDomainsError = '';
    try {
      const res = await domainsApi.list(scope, { refresh, ...(experience ? { experience } : {}) });
      if (!owns()) { experienceDiscarded(experience, 'stale'); return; }
      sourceDomains = res.items.filter((domain) => domain.enabled === true && domain.id !== scope.domainId);
      sourceDomainsLoaded = true;
      experienceState(experience, sourceDomains.length ? 'ready' : 'empty');
      void experienceApplied(experience, {}, owns);
    } catch (e) {
      if (owns()) {
        sourceDomains = []; sourceDomainsLoaded = false;
        sourceDomainsError = message(e, 'groupCard.sourceDomainsFailed');
        experienceState(experience, 'error');
        void experienceApplied(experience, {}, owns);
      }
      else experienceDiscarded(experience, 'stale');
    } finally { if (owns()) sourceDomainsLoading = false; }
  }

  async function selectUserDomain(value: string) {
    if (!expandedGroup || addMemberSaving[expandedGroup] || value === userDomainId
      || (value !== '' && !sourceDomains.some((domain) => domain.id === value))) return;
    const experience = beginExperienceAction('iam', 'select', 'resource.list');
    const scope = capture();
    userDomainId = value;
    clearCandidates();
    const source = sourceGeneration;
    void experienceApplied(experience, {}, () => scope.owns() && source === sourceGeneration);
    await loadUsersWithExperience(experience);
  }

  async function loadUsers() {
    await loadUsersWithExperience();
  }

  async function loadUsersWithExperience(inherited?: ExperienceContext) {
    const scope = capture();
    const groupId = expandedGroup;
    if (!scope.owns() || !groupId || !ownsGroup(groupId)) { experienceDiscarded(inherited, 'scope_changed'); return; }
    const sourceId = userDomainId;
    const source = sourceGeneration;
    const generation = ++usersGeneration;
    const owns = () => scope.owns() && generation === usersGeneration && source === sourceGeneration
      && expandedGroup === groupId && userDomainId === sourceId && ownsGroup(groupId);
    const experience = inherited ?? beginExperienceLoad('iam', 'resource.list');
    const request = experience ? api.withExperience(experience) : api;
    experienceState(experience, 'loading');
    usersLoading = true;
    usersOwns = null;
    usersError = '';
    allUsers = [];
    try {
      const res = sourceId
        ? await request.get<GroupCandidates>(`${scope.path(`/api/v1/admin/groups/${encodeURIComponent(groupId)}/candidates`)}&user_domain_id=${encodeURIComponent(sourceId)}`, scope.token, scope.projectId, { cache: 'no-store' })
        : await request.get<{ domain_id: string; items: User[] }>(`/api/v1/admin/domains/${encodeURIComponent(scope.domainId)}/members`, scope.token, scope.projectId, { refresh: true });
      if (!owns()) { experienceDiscarded(experience, 'stale'); return; }
      if (res.domain_id !== scope.domainId || (sourceId && (!('user_domain_id' in res)
        || res.user_domain_id !== sourceId || res.items.some((user) => user.domain_id !== sourceId)))) throw new Error('foreign domain');
      allUsers = res.items; usersOwns = owns;
      experienceState(experience, allUsers.length ? 'ready' : 'empty');
      void experienceApplied(experience, {}, owns);
    } catch (e) {
      if (owns()) {
        allUsers = []; usersOwns = null;
        usersError = e instanceof ApiError ? e.message : td('groups.usersFailed');
        experienceState(experience, 'error');
        void experienceApplied(experience, {}, owns);
      }
      else experienceDiscarded(experience, 'stale');
    } finally { if (owns()) usersLoading = false; }
  }

  async function createGroup(name: string, description: string): Promise<boolean> {
    const scope = capture();
    if (!scope.owns() || creating) return false;
    const experience = beginExperienceAction('iam', 'create', 'resource.list');
    const request = experience ? api.withExperience(experience) : api;
    experienceState(experience, 'loading');
    creating = true; createError = '';
    try {
      const created = await request.post<{ id?: unknown } | null>(scope.path('/api/v1/admin/groups'), { name, description: description || null, domain_id: scope.domainId }, scope.token, scope.projectId);
      if (!scope.owns()) { experienceDiscarded(experience, 'scope_changed'); return false; }
      createdGroupId = typeof created?.id === 'string' ? created.id : null;
      await loadAttempt(false, experience);
      if (!scope.owns()) experienceDiscarded(experience, 'scope_changed');
      return scope.owns();
    } catch (e) { if (scope.owns()) { createError = message(e, 'groupController.createFailed'); experienceState(experience, 'error'); void experienceApplied(experience, {}, scope.owns); } else experienceDiscarded(experience, 'scope_changed'); return false; }
    finally { if (scope.owns()) creating = false; }
  }

  async function updateGroup(form: { name: string; description: string }): Promise<boolean> {
    const scope = capture();
    if (!scope.owns() || !editGroup || !ownsGroup(editGroup.id) || updating) return false;
    const target = editGroup.id;
    const experience = beginExperienceAction('iam', 'update', 'resource.list');
    const request = experience ? api.withExperience(experience) : api;
    experienceState(experience, 'loading');
    updating = true; editError = '';
    try {
      await request.patch(scope.path(`/api/v1/admin/groups/${encodeURIComponent(target)}`), { name: form.name, description: form.description || null }, scope.token, scope.projectId);
      if (!scope.owns()) { experienceDiscarded(experience, 'scope_changed'); return false; }
      await loadAttempt(false, experience);
      if (!scope.owns()) experienceDiscarded(experience, 'scope_changed');
      return scope.owns();
    } catch (e) { if (scope.owns()) { editError = message(e, 'groupController.updateFailed'); experienceState(experience, 'error'); void experienceApplied(experience, {}, scope.owns); } else experienceDiscarded(experience, 'scope_changed'); return false; }
    finally { if (scope.owns()) updating = false; }
  }

  async function confirmDelete() {
    const scope = capture();
    if (!scope.owns() || !deleteGroup || !ownsGroup(deleteGroup.id) || deleting) return;
    const target = deleteGroup.id;
    const experience = beginExperienceAction('iam', 'delete', 'resource.list');
    const request = experience ? api.withExperience(experience) : api;
    experienceState(experience, 'loading');
    deleting = true; deleteError = '';
    try {
      await request.delete(scope.path(`/api/v1/admin/groups/${encodeURIComponent(target)}`), scope.token, scope.projectId);
      if (!scope.owns()) { experienceDiscarded(experience, 'scope_changed'); return; }
      deleteGroup = null;
      if (createdGroupId === target) createdGroupId = null;
      void experienceApplied(experience, {}, scope.owns);
      await loadAttempt(false, experience);
    } catch (e) { if (scope.owns()) { deleteError = message(e, 'groupController.deleteFailed'); experienceState(experience, 'error'); void experienceApplied(experience, {}, scope.owns); } else experienceDiscarded(experience, 'scope_changed'); }
    finally { if (scope.owns()) deleting = false; }
  }

  async function loadGroupMembers(groupId: string) {
    await loadGroupMembersWithExperience(groupId);
  }

  async function loadGroupMembersWithExperience(groupId: string, inherited?: ExperienceContext) {
    const scope = capture();
    if (!scope.owns() || !ownsGroup(groupId)) { experienceDiscarded(inherited, 'scope_changed'); return; }
    const experience = inherited ?? beginExperienceLoad('iam', 'resource.detail');
    const request = experience ? api.withExperience(experience) : api;
    experienceState(experience, 'loading');
    const generation = (memberGenerations[groupId] ?? 0) + 1;
    memberGenerations[groupId] = generation;
    const owns = () => scope.owns() && memberGenerations[groupId] === generation;
    membersLoading = { ...membersLoading, [groupId]: true };
    membersError = { ...membersError, [groupId]: '' };
    try {
      const res = await request.get<GroupMember[]>(scope.path(`/api/v1/admin/groups/${encodeURIComponent(groupId)}/users`), scope.token, scope.projectId);
      if (!owns()) { experienceDiscarded(experience, 'stale'); return; }
      groupMembers = { ...groupMembers, [groupId]: res };
      experienceState(experience, res.length ? 'ready' : 'empty');
      void experienceApplied(experience, {}, owns);
    } catch (e) {
      if (owns()) {
        groupMembers = { ...groupMembers, [groupId]: [] };
        membersError = { ...membersError, [groupId]: e instanceof ApiError ? e.message : td('groups.membersFailed') };
        experienceState(experience, 'error');
        void experienceApplied(experience, {}, owns);
      }
      else experienceDiscarded(experience, 'stale');
    } finally { if (owns()) membersLoading = { ...membersLoading, [groupId]: false }; }
  }

  async function toggleMembers(g: Group) {
    if (!ownsGroup(g.id)) return;
    const experience = beginExperienceAction('iam', 'select', 'resource.detail');
    const scope = capture();
    clearCandidates();
    userDomainId = '';
    const source = sourceGeneration;
    const owns = () => scope.owns() && source === sourceGeneration;
    if (expandedGroup === g.id) { expandedGroup = null; void experienceApplied(experience, {}, owns); return; }
    expandedGroup = g.id;
    void experienceApplied(experience, {}, owns);
    await Promise.all([loadGroupMembersWithExperience(g.id, experience), loadUsersWithExperience(experience), loadSourceDomainsWithExperience(false, experience)]);
  }

  async function addMember(groupId: string, userId: string): Promise<boolean> {
    const scope = capture();
    const source = sourceGeneration;
    const sourceId = userDomainId;
    const owns = () => scope.owns() && source === sourceGeneration && userDomainId === sourceId && expandedGroup === groupId;
    if (!owns() || !ownsGroup(groupId) || !usersOwns?.() || usersLoading || usersError
      || membersLoading[groupId] || membersError[groupId]
      || !allUsers.some((user) => user.id === userId && user.enabled)
      || groupMembers[groupId]?.some((user) => user.id === userId) || addMemberSaving[groupId]) return false;
    const experience = beginExperienceAction('iam', 'attach', 'resource.detail');
    const request = experience ? api.withExperience(experience) : api;
    experienceState(experience, 'loading');
    addMemberSaving = { ...addMemberSaving, [groupId]: true };
    addMemberError = { ...addMemberError, [groupId]: '' };
    try {
      const path = scope.path(`/api/v1/admin/groups/${encodeURIComponent(groupId)}/users/${encodeURIComponent(userId)}`);
      await request.put(sourceId ? `${path}&user_domain_id=${encodeURIComponent(sourceId)}` : path, {}, scope.token, scope.projectId);
      if (!owns()) { experienceDiscarded(experience, 'stale'); return false; }
      await loadGroupMembersWithExperience(groupId, experience);
      if (!owns()) experienceDiscarded(experience, 'stale');
      return owns();
    } catch (e) {
      if (owns()) { addMemberError = { ...addMemberError, [groupId]: message(e, 'groupController.addFailed') }; experienceState(experience, 'error'); void experienceApplied(experience, {}, owns); }
      else experienceDiscarded(experience, 'stale');
      return false;
    } finally { if (scope.owns()) addMemberSaving = { ...addMemberSaving, [groupId]: false }; }
  }

  async function removeMember(groupId: string, userId: string) {
    const scope = capture();
    if (!scope.owns() || !ownsGroup(groupId) || !groupMembers[groupId]?.some((user) => user.id === userId)) return;
    const experience = beginExperienceAction('iam', 'detach', 'resource.detail');
    const request = experience ? api.withExperience(experience) : api;
    experienceState(experience, 'loading');
    addMemberError = { ...addMemberError, [groupId]: '' };
    try {
      await request.delete(scope.path(`/api/v1/admin/groups/${encodeURIComponent(groupId)}/users/${encodeURIComponent(userId)}`), scope.token, scope.projectId);
      if (scope.owns()) await loadGroupMembersWithExperience(groupId, experience);
      else experienceDiscarded(experience, 'scope_changed');
    } catch (e) {
      if (scope.owns()) { addMemberError = { ...addMemberError, [groupId]: e instanceof ApiError ? e.message : td('groups.removeFailed') }; experienceState(experience, 'error'); void experienceApplied(experience, {}, scope.owns); }
      else experienceDiscarded(experience, 'scope_changed');
    }
  }

  return {
    get groups() { return groups; }, get loading() { return loading; }, get refreshing() { return refreshing; }, get error() { return error; },
    get showCreate() { return showCreate; }, set showCreate(v: boolean) { showCreate = v; },
    get creating() { return creating; }, get createError() { return createError; }, set createError(v: string) { createError = v; },
    get editGroup() { return editGroup; }, set editGroup(v: Group | null) { editGroup = v; },
    get updating() { return updating; }, get editError() { return editError; }, set editError(v: string) { editError = v; },
    get deleteGroup() { return deleteGroup; }, set deleteGroup(v: Group | null) { deleteGroup = v; },
    get deleting() { return deleting; }, get deleteError() { return deleteError; }, set deleteError(v: string) { deleteError = v; },
    get createdGroupId() { return createdGroupId; },
    get expandedGroup() { return expandedGroup; }, get groupMembers() { return groupMembers; }, get membersLoading() { return membersLoading; },
    get membersError() { return membersError; }, get usersError() { return usersError; }, get usersLoading() { return usersLoading; }, get allUsers() { return allUsers; },
    get addMemberError() { return addMemberError; }, get addMemberSaving() { return addMemberSaving; },
    get userDomainId() { return userDomainId; }, get sourceGeneration() { return sourceGeneration; },
    get sourceDomains() { return sourceDomains; }, get sourceDomainsLoading() { return sourceDomainsLoading; },
    get sourceDomainsError() { return sourceDomainsError; },
    loadSourceDomains, selectUserDomain,
    load, loadUsers, createGroup, updateGroup, confirmDelete, toggleMembers, loadGroupMembers, addMember, removeMember,
  };
}
