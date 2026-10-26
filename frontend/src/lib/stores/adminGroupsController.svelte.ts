import { untrack } from 'svelte';
import { api, ApiError } from '$lib/api/client';
import type { Group, GroupCandidates, GroupMember, User } from '$lib/types/adminGroup';
import { domainsApi, type AdminDomain } from '$lib/api/domains';
import { t } from '$lib/i18n/ns/admin-identity';
import { t as td } from '$lib/i18n/ns/domain-admin';

export interface AdminGroupsControllerOpts {
  token: () => string | undefined;
  projectId: () => string | undefined;
  domainId: () => string;
  actorId?: () => string | undefined;
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

  function capture() {
    const generation = epoch;
    const token = opts.token();
    const projectId = opts.projectId();
    const domainId = opts.domainId();
    const actorId = opts.actorId?.();
    return {
      token, projectId, domainId,
      owns: () => generation === epoch && !!domainId && opts.domainId() === domainId
        && opts.token() === token && opts.projectId() === projectId && opts.actorId?.() === actorId,
      path: (path: string) => `${path}${path.includes('?') ? '&' : '?'}domain_id=${encodeURIComponent(domainId)}`,
    };
  }
  const message = (e: unknown, fallback: Parameters<typeof t>[0]) => e instanceof ApiError ? e.message : t(fallback);
  const ownsGroup = (id: string) => groups.some((group) => group.id === id && group.domain_id === opts.domainId());

  $effect(() => {
    void opts.token(); void opts.projectId(); void opts.domainId(); void opts.actorId?.();
    untrack(() => {
      epoch += 1;
      groups = []; allUsers = []; groupMembers = {}; membersLoading = {}; membersError = {};
      addMemberError = {}; addMemberSaving = {}; usersError = ''; error = '';
      usersLoading = false; usersOwns = null;
      sourceGeneration += 1; sourceDomainsGeneration += 1;
      userDomainId = ''; sourceDomains = []; sourceDomainsLoading = false;
      sourceDomainsError = ''; sourceDomainsLoaded = false;
      showCreate = false; editGroup = null; deleteGroup = null; expandedGroup = null;
      creating = false; updating = false; deleting = false;
      createError = ''; editError = ''; deleteError = '';
      void load();
    });
    return () => { epoch += 1; };
  });

  async function load() {
    const scope = capture();
    if (!scope.owns()) { loading = false; return; }
    const generation = ++listGeneration;
    const owns = () => scope.owns() && generation === listGeneration;
    if (groups.length === 0) loading = true;
    else refreshing = true;
    error = '';
    try {
      const res = await api.get<Group[]>(scope.path('/api/v1/admin/groups'), scope.token, scope.projectId);
      if (!owns()) return;
      if (res.some((group) => group.domain_id !== scope.domainId)) throw new Error('foreign domain');
      groups = res;
    } catch (e) {
      if (owns()) { groups = []; error = message(e, 'groupController.loadFailed'); }
    } finally { if (owns()) { loading = false; refreshing = false; } }
  }

  function clearCandidates() {
    sourceGeneration += 1;
    allUsers = []; usersOwns = null; usersError = ''; usersLoading = false;
  }

  async function loadSourceDomains(refresh = false) {
    const scope = capture();
    if (!scope.owns() || sourceDomainsLoading || (sourceDomainsLoaded && !refresh)) return;
    const generation = ++sourceDomainsGeneration;
    const owns = () => scope.owns() && generation === sourceDomainsGeneration;
    sourceDomainsLoading = true; sourceDomainsError = '';
    try {
      const res = await domainsApi.list(scope, { refresh });
      if (!owns()) return;
      sourceDomains = res.items.filter((domain) => domain.enabled === true && domain.id !== scope.domainId);
      sourceDomainsLoaded = true;
    } catch (e) {
      if (owns()) {
        sourceDomains = []; sourceDomainsLoaded = false;
        sourceDomainsError = message(e, 'groupCard.sourceDomainsFailed');
      }
    } finally { if (owns()) sourceDomainsLoading = false; }
  }

  async function selectUserDomain(value: string) {
    if (!expandedGroup || addMemberSaving[expandedGroup] || value === userDomainId
      || (value !== '' && !sourceDomains.some((domain) => domain.id === value))) return;
    userDomainId = value;
    clearCandidates();
    await loadUsers();
  }

  async function loadUsers() {
    const scope = capture();
    const groupId = expandedGroup;
    if (!scope.owns() || !groupId || !ownsGroup(groupId)) return;
    const sourceId = userDomainId;
    const source = sourceGeneration;
    const generation = ++usersGeneration;
    const owns = () => scope.owns() && generation === usersGeneration && source === sourceGeneration
      && expandedGroup === groupId && userDomainId === sourceId && ownsGroup(groupId);
    usersLoading = true;
    usersOwns = null;
    usersError = '';
    allUsers = [];
    try {
      const res = sourceId
        ? await api.get<GroupCandidates>(`${scope.path(`/api/v1/admin/groups/${encodeURIComponent(groupId)}/candidates`)}&user_domain_id=${encodeURIComponent(sourceId)}`, scope.token, scope.projectId, { cache: 'no-store' })
        : await api.get<{ domain_id: string; items: User[] }>(`/api/v1/admin/domains/${encodeURIComponent(scope.domainId)}/members`, scope.token, scope.projectId, { refresh: true });
      if (!owns()) return;
      if (res.domain_id !== scope.domainId || (sourceId && (!('user_domain_id' in res)
        || res.user_domain_id !== sourceId || res.items.some((user) => user.domain_id !== sourceId)))) throw new Error('foreign domain');
      allUsers = res.items; usersOwns = owns;
    } catch (e) {
      if (owns()) {
        allUsers = []; usersOwns = null;
        usersError = e instanceof ApiError ? e.message : td('groups.usersFailed');
      }
    } finally { if (owns()) usersLoading = false; }
  }

  async function createGroup(name: string, description: string): Promise<boolean> {
    const scope = capture();
    if (!scope.owns() || creating) return false;
    creating = true; createError = '';
    try {
      await api.post(scope.path('/api/v1/admin/groups'), { name, description: description || null, domain_id: scope.domainId }, scope.token, scope.projectId);
      if (!scope.owns()) return false;
      await load();
      return scope.owns();
    } catch (e) { if (scope.owns()) createError = message(e, 'groupController.createFailed'); return false; }
    finally { if (scope.owns()) creating = false; }
  }

  async function updateGroup(form: { name: string; description: string }): Promise<boolean> {
    const scope = capture();
    if (!scope.owns() || !editGroup || !ownsGroup(editGroup.id) || updating) return false;
    const target = editGroup.id;
    updating = true; editError = '';
    try {
      await api.patch(scope.path(`/api/v1/admin/groups/${encodeURIComponent(target)}`), { name: form.name, description: form.description || null }, scope.token, scope.projectId);
      if (!scope.owns()) return false;
      await load();
      return scope.owns();
    } catch (e) { if (scope.owns()) editError = message(e, 'groupController.updateFailed'); return false; }
    finally { if (scope.owns()) updating = false; }
  }

  async function confirmDelete() {
    const scope = capture();
    if (!scope.owns() || !deleteGroup || !ownsGroup(deleteGroup.id) || deleting) return;
    const target = deleteGroup.id;
    deleting = true; deleteError = '';
    try {
      await api.delete(scope.path(`/api/v1/admin/groups/${encodeURIComponent(target)}`), scope.token, scope.projectId);
      if (!scope.owns()) return;
      deleteGroup = null;
      await load();
    } catch (e) { if (scope.owns()) deleteError = message(e, 'groupController.deleteFailed'); }
    finally { if (scope.owns()) deleting = false; }
  }

  async function loadGroupMembers(groupId: string) {
    const scope = capture();
    if (!scope.owns() || !ownsGroup(groupId)) return;
    const generation = (memberGenerations[groupId] ?? 0) + 1;
    memberGenerations[groupId] = generation;
    const owns = () => scope.owns() && memberGenerations[groupId] === generation;
    membersLoading = { ...membersLoading, [groupId]: true };
    membersError = { ...membersError, [groupId]: '' };
    try {
      const res = await api.get<GroupMember[]>(scope.path(`/api/v1/admin/groups/${encodeURIComponent(groupId)}/users`), scope.token, scope.projectId);
      if (owns()) groupMembers = { ...groupMembers, [groupId]: res };
    } catch (e) {
      if (owns()) {
        groupMembers = { ...groupMembers, [groupId]: [] };
        membersError = { ...membersError, [groupId]: e instanceof ApiError ? e.message : td('groups.membersFailed') };
      }
    } finally { if (owns()) membersLoading = { ...membersLoading, [groupId]: false }; }
  }

  async function toggleMembers(g: Group) {
    if (!ownsGroup(g.id)) return;
    clearCandidates();
    userDomainId = '';
    if (expandedGroup === g.id) { expandedGroup = null; return; }
    expandedGroup = g.id;
    await Promise.all([loadGroupMembers(g.id), loadUsers(), loadSourceDomains()]);
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
    addMemberSaving = { ...addMemberSaving, [groupId]: true };
    addMemberError = { ...addMemberError, [groupId]: '' };
    try {
      const path = scope.path(`/api/v1/admin/groups/${encodeURIComponent(groupId)}/users/${encodeURIComponent(userId)}`);
      await api.put(sourceId ? `${path}&user_domain_id=${encodeURIComponent(sourceId)}` : path, {}, scope.token, scope.projectId);
      if (!owns()) return false;
      await loadGroupMembers(groupId);
      return owns();
    } catch (e) {
      if (owns()) addMemberError = { ...addMemberError, [groupId]: message(e, 'groupController.addFailed') };
      return false;
    } finally { if (scope.owns()) addMemberSaving = { ...addMemberSaving, [groupId]: false }; }
  }

  async function removeMember(groupId: string, userId: string) {
    const scope = capture();
    if (!scope.owns() || !ownsGroup(groupId) || !groupMembers[groupId]?.some((user) => user.id === userId)) return;
    addMemberError = { ...addMemberError, [groupId]: '' };
    try {
      await api.delete(scope.path(`/api/v1/admin/groups/${encodeURIComponent(groupId)}/users/${encodeURIComponent(userId)}`), scope.token, scope.projectId);
      if (scope.owns()) await loadGroupMembers(groupId);
    } catch (e) {
      if (scope.owns()) addMemberError = { ...addMemberError, [groupId]: e instanceof ApiError ? e.message : td('groups.removeFailed') };
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
