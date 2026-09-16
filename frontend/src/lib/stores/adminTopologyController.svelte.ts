import { api, ApiError } from '$lib/api/client';
import type { TopologyData, TopologyTraffic, TopologyLoadBalancer, TopologyTrafficHistory } from '$lib/types/topology';

export interface AdminTopologyControllerOpts {
  token: () => string | undefined;
  projectId: () => string | undefined;
}

export function createAdminTopologyController(opts: AdminTopologyControllerOpts) {
  let data = $state<TopologyData | null>(null);
  let traffic = $state<TopologyTraffic | null>(null);
  let loading = $state(true);
  let refreshing = $state(false);
  let error = $state('');
  let selectedInstanceId = $state<string | null>(null);
  let selectedRouterId = $state<string | null>(null);
  let selectedLB = $state<TopologyLoadBalancer | null>(null);
  let projectFilter = $state<string | null>(null);
  let projectSearchText = $state('');
  let projectDropdownOpen = $state(false);

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
      error = e instanceof ApiError ? `조회 실패 (${e.status}): ${e.message}` : '서버 오류';
    } finally {
      loading = false;
      refreshing = false;
    }
  }

  async function loadTraffic() {
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
    if (!opts.token()) return null;
    return api.get<TopologyTrafficHistory>(
      `/api/v1/networks/topology/traffic/history?network_id=${encodeURIComponent(networkId)}`
        + `&range=${encodeURIComponent(range)}&all_projects=true`,
      opts.token(),
      opts.projectId(),
    );
  }

  function handleDocumentClick(e: MouseEvent) {
    const target = e.target as HTMLElement;
    if (!target.closest('.project-filter-wrapper')) {
      projectDropdownOpen = false;
    }
  }

  return {
    loadNetworkHistory,
    get data() { return data; },
    get traffic() { return traffic; },
    get loading() { return loading; },
    get refreshing() { return refreshing; },
    get error() { return error; },
    get selectedInstanceId() { return selectedInstanceId; },
    set selectedInstanceId(v: string | null) { selectedInstanceId = v; },
    get selectedRouterId() { return selectedRouterId; },
    set selectedRouterId(v: string | null) { selectedRouterId = v; },
    get selectedLB() { return selectedLB; },
    set selectedLB(v: TopologyLoadBalancer | null) { selectedLB = v; },
    get projectFilter() { return projectFilter; },
    set projectFilter(v: string | null) { projectFilter = v; },
    get projectSearchText() { return projectSearchText; },
    set projectSearchText(v: string) { projectSearchText = v; },
    get projectDropdownOpen() { return projectDropdownOpen; },
    set projectDropdownOpen(v: boolean) { projectDropdownOpen = v; },
    get topologySelectedId() { return topologySelectedId; },
    fetchTopology,
    loadTraffic,
    handleDocumentClick,
  };
}
