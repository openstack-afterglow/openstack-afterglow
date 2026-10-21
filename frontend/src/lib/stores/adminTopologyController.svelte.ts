import { t } from '$lib/i18n/ns/topology';
import { api as baseApi, ApiError } from '$lib/api/client';
import { createAdminInventoryApi } from '$lib/api/adminInventoryScope';
import { invalidateInstanceDetailSelection } from '$lib/stores/instanceDetailController.svelte';
import type { TopologyData, TopologyTraffic, TopologyLoadBalancer, TopologyTrafficHistory } from '$lib/types/topology';

export interface AdminTopologyControllerOpts {
  token: () => string | undefined;
  projectId: () => string | undefined;
}

export function createAdminTopologyController(opts: AdminTopologyControllerOpts) {
  const api = createAdminInventoryApi(baseApi);
  let data = $state<TopologyData | null>(null);
  let traffic = $state<TopologyTraffic | null>(null);
  let loading = $state(true);
  let refreshing = $state(false);
  let error = $state('');
  let selectedInstanceId = $state<string | null>(null);
  let selectedRouterId = $state<string | null>(null);
  let selectedLB = $state<TopologyLoadBalancer | null>(null);
  const projectFilter = api.filter.projectId || null;

  const topologySelectedId = $derived(
    selectedInstanceId ?? selectedRouterId ?? selectedLB?.id ?? null
  );

  async function fetchTopology() {
    if (!data) loading = true;
    else refreshing = true;
    error = '';
    try {
      data = await api.get<TopologyData>(
        '/api/v1/admin/topology',
        opts.token(),
        opts.projectId(),
      );
    } catch (e) {
      error = e instanceof ApiError ? t('topology.loadFailed', { status: e.status, message: e.message }) : t('topology.serverError');
    } finally {
      loading = false;
      refreshing = false;
    }
  }

  async function loadTraffic() {
    if (api.scoped) { traffic = null; return; }
    if (!opts.token()) return;
    try {
      traffic = await api.get<TopologyTraffic>(
        '/api/v1/networks/topology/traffic?all_projects=true',
        opts.token(),
        opts.projectId(),
      );
    } catch { /* silent — traffic=null 로 표시 유지 */ }
  }

  /**
   * 네트워크 사용량 히스토리. 네트워크 패널을 열 때 1회만 호출한다 —
   * 폴링에 얹으면 Prometheus 부하가 네트워크 수만큼 곱해진다.
   */
  async function loadNetworkHistory(networkId: string, range: string): Promise<TopologyTrafficHistory | null> {
    if (api.scoped) return null;
    if (!opts.token()) return null;
    return api.get<TopologyTrafficHistory>(
      `/api/v1/networks/topology/traffic/history?network_id=${encodeURIComponent(networkId)}`
        + `&range=${encodeURIComponent(range)}&all_projects=true`,
      opts.token(),
      opts.projectId(),
    );
  }


  return {
    dispose: api.dispose,
    loadNetworkHistory,
    get data() { return data; },
    get traffic() { return traffic; },
    get loading() { return loading; },
    get refreshing() { return refreshing; },
    get error() { return error; },
    get selectedInstanceId() { return selectedInstanceId; },
    set selectedInstanceId(v: string | null) { invalidateInstanceDetailSelection(); selectedInstanceId = v; },
    get selectedRouterId() { return selectedRouterId; },
    set selectedRouterId(v: string | null) { selectedRouterId = v; },
    get selectedLB() { return selectedLB; },
    set selectedLB(v: TopologyLoadBalancer | null) { selectedLB = v; },
    get projectFilter() { return projectFilter; },
    get topologySelectedId() { return topologySelectedId; },
    fetchTopology,
    loadTraffic,
  };
}
