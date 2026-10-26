import { t as tr } from '$lib/i18n/ns/network-resources';
import { getContext, setContext, untrack } from 'svelte';
import { api, ApiError } from '$lib/api/client';
import { confirmDialog } from '$lib/stores/confirm.svelte';
import { toast } from '$lib/stores/toast';
import type { LoadBalancerDetail, Listener, Pool, Member, LbStatusNode } from '$lib/types/loadbalancer';
import { isDroverLoadBalancer, loadBalancerDeleteConfirmation } from '$lib/utils/droverLoadBalancer';

export function provisioningColor(status: string): string {
  return status === 'ERROR' ? 'text-red-400' : 'text-gray-400';
}

export interface LoadbalancerDetailControllerOpts {
  lbId: () => string;
  token: () => string | undefined;
  projectId: () => string | undefined;
  adminMode?: () => boolean;
  onDeleted?: () => void;
  onClose?: () => void;
}

export function createLoadbalancerDetailController(opts: LoadbalancerDetailControllerOpts) {
  let lb = $state<LoadBalancerDetail | null>(null);
  let listeners = $state<Listener[]>([]);
  let pools = $state<Pool[]>([]);
  let selectedPoolMembers = $state<Member[]>([]);
  let statusTree = $state<LbStatusNode | null>(null);
  let selectedPoolId = $state<string | null>(null);
  let loading = $state(true);
  let error = $state('');
  let membersError = $state('');
  let saving = $state(false);

  let showAddListener = $state(false);
  let listenerForm = $state({ protocol: 'HTTP', protocol_port: 80, name: '' });
  let showAddPool = $state(false);
  let poolForm = $state({ protocol: 'HTTP', lb_algorithm: 'ROUND_ROBIN', name: '' });
  let showAddMember = $state(false);
  let memberForm = $state({ address: '', protocol_port: 80, weight: 1, name: '' });

  const isErrored = $derived(
    !!lb && (lb.status === 'ERROR' || lb.status?.includes('ERROR')),
  );
  const isProtected = $derived(isDroverLoadBalancer(lb));
  const canMutate = $derived(!opts.adminMode?.() || (lb?.id === opts.lbId() && !!lb?.project_id && lb.project_id === opts.projectId()));
  const readBase = () => opts.adminMode?.() ? '/api/v1/admin/loadbalancers' : '/api/v1/loadbalancers';
  // selectedPoolId 변화 시 멤버 fetch (token/projectId는 untrack)
  $effect(() => {
    const poolId = selectedPoolId;
    if (!poolId) {
      selectedPoolMembers = [];
      membersError = '';
      return;
    }
    const t = untrack(() => opts.token());
    const pid = untrack(() => opts.projectId());
    membersError = '';
    api
      .get<Member[]>(`${readBase()}/${opts.lbId()}/pools/${poolId}/members`, t, pid)
      .then((m) => {
        selectedPoolMembers = m;
      })
      .catch(e => { selectedPoolMembers = []; membersError = e instanceof ApiError ? e.message : tr('lb.errors.loadFailed'); });
  });

  async function fetchAll(force = false) {
    const id = opts.lbId();
    const t = opts.token();
    const pid = opts.projectId();
    loading = true;
    try {
      const [lbData, listenersData, poolsData] = await Promise.all([
        api.get<LoadBalancerDetail>(`${readBase()}/${id}`, t, pid, { refresh: force }),
        api.get<Listener[]>(`${readBase()}/${id}/listeners`, t, pid, { refresh: force }),
        api.get<Pool[]>(`${readBase()}/${id}/pools`, t, pid, { refresh: force }),
      ]);
      lb = lbData;
      listeners = listenersData;
      pools = poolsData;
      error = '';
      statusTree = null;
      if (lbData.status === 'ERROR') {
        await api
          .get<LbStatusNode>(`${readBase()}/${id}/status`, t, pid, { refresh: force })
          .then((tree) => {
            statusTree = tree;
          })
          .catch(() => { statusTree = null; });
      }
    } catch (e) {
      error = e instanceof ApiError ? e.message : tr('lb.errors.loadFailed');
    } finally {
      loading = false;
    }
  }

  async function createListener(form?: { protocol: string; protocol_port: number; name: string }): Promise<boolean> {
    if (!canMutate) return false;
    if (form) listenerForm = { ...form };
    saving = true;
    try {
      await api.post(
        `/api/v1/loadbalancers/${opts.lbId()}/listeners`,
        listenerForm,
        opts.token(),
        opts.projectId(),
      );
      showAddListener = false;
      listenerForm = { protocol: 'HTTP', protocol_port: 80, name: '' };
      await fetchAll();
      return true;
    } catch (e) {
      toast.error(tr('lb.errors.createListenerFailed', { error: e instanceof ApiError ? e.message : String(e) }));
      return false;
    } finally {
      saving = false;
    }
  }

  async function deleteListener(listenerId: string) {
    if (!canMutate) return;
    if (!(await confirmDialog(tr('lb.confirm.deleteListener')))) return;
    saving = true;
    try {
      await api.delete(
        `/api/v1/loadbalancers/${opts.lbId()}/listeners/${listenerId}`,
        opts.token(),
        opts.projectId(),
      );
      await fetchAll();
    } catch (e) {
      toast.error(tr('lb.errors.deleteFailed', { error: e instanceof ApiError ? e.message : String(e) }));
    } finally {
      saving = false;
    }
  }

  function toggleAddListener() {
    if (!canMutate) return;
    showAddListener = !showAddListener;
  }

  async function createPool(form?: { protocol: string; lb_algorithm: string; name: string }): Promise<boolean> {
    if (!canMutate) return false;
    if (form) poolForm = { ...form };
    saving = true;
    try {
      await api.post(
        `/api/v1/loadbalancers/${opts.lbId()}/pools`,
        poolForm,
        opts.token(),
        opts.projectId(),
      );
      showAddPool = false;
      poolForm = { protocol: 'HTTP', lb_algorithm: 'ROUND_ROBIN', name: '' };
      await fetchAll();
      return true;
    } catch (e) {
      toast.error(tr('lb.errors.createPoolFailed', { error: e instanceof ApiError ? e.message : String(e) }));
      return false;
    } finally {
      saving = false;
    }
  }

  async function deletePool(poolId: string) {
    if (!canMutate) return;
    if (!(await confirmDialog(tr('lb.confirm.deletePool')))) return;
    saving = true;
    try {
      await api.delete(
        `/api/v1/loadbalancers/${opts.lbId()}/pools/${poolId}`,
        opts.token(),
        opts.projectId(),
      );
      if (selectedPoolId === poolId) selectedPoolId = null;
      await fetchAll();
    } catch (e) {
      toast.error(tr('lb.errors.deleteFailed', { error: e instanceof ApiError ? e.message : String(e) }));
    } finally {
      saving = false;
    }
  }

  function togglePool(id: string) {
    selectedPoolId = selectedPoolId === id ? null : id;
  }

  function toggleAddPool() {
    if (!canMutate) return;
    showAddPool = !showAddPool;
  }

  async function addMember(form?: { address: string; protocol_port: number; weight: number; name: string }): Promise<boolean> {
    if (!canMutate) return false;
    if (!selectedPoolId) return false;
    if (form) memberForm = { ...form };
    saving = true;
    try {
      await api.post(
        `/api/v1/loadbalancers/${opts.lbId()}/pools/${selectedPoolId}/members`,
        memberForm,
        opts.token(),
        opts.projectId(),
      );
      showAddMember = false;
      memberForm = { address: '', protocol_port: 80, weight: 1, name: '' };
      selectedPoolMembers = await api.get<Member[]>(
        `${readBase()}/${opts.lbId()}/pools/${selectedPoolId}/members`,
        opts.token(),
        opts.projectId(),
      );
      return true;
    } catch (e) {
      toast.error(tr('lb.errors.addMemberFailed', { error: e instanceof ApiError ? e.message : String(e) }));
      return false;
    } finally {
      saving = false;
    }
  }

  async function removeMember(memberId: string) {
    if (!canMutate) return;
    if (!selectedPoolId || !(await confirmDialog(tr('lb.confirm.removeMember')))) return;
    saving = true;
    try {
      await api.delete(
        `/api/v1/loadbalancers/${opts.lbId()}/pools/${selectedPoolId}/members/${memberId}`,
        opts.token(),
        opts.projectId(),
      );
      selectedPoolMembers = selectedPoolMembers.filter((m) => m.id !== memberId);
    } catch (e) {
      toast.error(tr('lb.errors.removeFailed', { error: e instanceof ApiError ? e.message : String(e) }));
    } finally {
      saving = false;
    }
  }

  function toggleAddMember() {
    if (!canMutate) return;
    showAddMember = !showAddMember;
  }

  async function deleteLb() {
    if (!canMutate) return;
    const id = opts.lbId();
    const message = loadBalancerDeleteConfirmation(lb, id);
    if (!(await confirmDialog(message)))
      return;
    saving = true;
    try {
      await api.delete(`/api/v1/loadbalancers/${id}`, opts.token(), opts.projectId());
      opts.onDeleted?.();
    } catch (e) {
      toast.error(tr('lb.errors.deleteFailed', { error: e instanceof ApiError ? e.message : String(e) }));
      saving = false;
    }
  }

  return {
    // State getters
    get lb() { return lb; },
    get listeners() { return listeners; },
    get pools() { return pools; },
    get selectedPoolMembers() { return selectedPoolMembers; },
    get statusTree() { return statusTree; },
    get selectedPoolId() { return selectedPoolId; },
    get loading() { return loading; },
    get error() { return error; },
    get membersError() { return membersError; },
    get saving() { return saving; },
    // Form state (mutable via bind:)
    get showAddListener() { return showAddListener; },
    set showAddListener(v: boolean) { showAddListener = v; },
    get listenerForm() { return listenerForm; },
    get showAddPool() { return showAddPool; },
    set showAddPool(v: boolean) { showAddPool = v; },
    get poolForm() { return poolForm; },
    get showAddMember() { return showAddMember; },
    set showAddMember(v: boolean) { showAddMember = v; },
    get memberForm() { return memberForm; },
    // Derived
    get isErrored() { return isErrored; },
    get isProtected() { return isProtected; },
    get canMutate() { return canMutate; },
    fetchAll,
    createListener,
    deleteListener,
    toggleAddListener,
    createPool,
    deletePool,
    togglePool,
    toggleAddPool,
    addMember,
    removeMember,
    toggleAddMember,
    deleteLb,
  };
}

export type LoadbalancerDetailController = ReturnType<typeof createLoadbalancerDetailController>;

const LB_DETAIL_KEY = Symbol('lb-detail');

export function provideLoadbalancerDetailController(store: LoadbalancerDetailController) {
  setContext(LB_DETAIL_KEY, store);
}

export function useLoadbalancerDetailController(): LoadbalancerDetailController {
  const store = getContext<LoadbalancerDetailController | undefined>(LB_DETAIL_KEY);
  if (!store) throw new Error(tr('lb.errors.missingController'));
  return store;
}
