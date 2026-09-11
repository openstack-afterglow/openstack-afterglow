<script lang="ts">
  import { auth } from '$lib/stores/auth';
  import { api } from '$lib/api/client';
  import TopologyMini from '$lib/components/TopologyMini.svelte';
  import type { FloatingIpInfo } from '$lib/types/networks';

  interface SubnetDetail {
    id: string; name: string; cidr: string;
    gateway_ip: string | null; dhcp_enabled: boolean;
  }
  interface TopologyNetwork {
    id: string; name: string; status: string;
    is_external: boolean; is_shared: boolean;
    project_id: string | null;
    subnet_details: SubnetDetail[];
  }
  interface TopologyRouter {
    id: string; name: string; status: string;
    external_gateway_network_id: string | null;
    external_gateway_ips: string[];
    interface_ips: { ip_address: string; subnet_id: string }[];
    is_distributed: boolean; is_ha: boolean;
    connected_subnet_ids: string[];
    dvr_subnet_ids: string[];
    project_id: string | null;
  }
  interface TopologyInstance {
    id: string; name: string; status: string;
    project_id?: string | null;
    network_names: string[];
    ip_addresses: { addr: string; type: string; network_name: string; network_id?: string | null }[];
  }
  interface TopologyLBMember {
    id: string; address: string; protocol_port: number;
    status: string; subnet_id: string | null;
    pool_id: string; server_id: string | null;
  }
  interface TopologyLBListener {
    id: string; name: string; protocol: string;
    protocol_port: number; default_pool_id: string | null;
  }
  interface TopologyLoadBalancer {
    id: string; name: string;
    vip_address: string | null; vip_port_id: string | null;
    vip_subnet_id: string | null; vip_network_id: string | null;
    provisioning_status: string; operating_status: string;
    project_id: string | null;
    listeners: TopologyLBListener[];
    members: TopologyLBMember[];
  }
  interface TopologyData {
    networks: TopologyNetwork[];
    routers: TopologyRouter[];
    instances: TopologyInstance[];
    floating_ips: FloatingIpInfo[];
    load_balancers?: TopologyLoadBalancer[];
  }

  let data = $state<TopologyData | null>(null);
  let loading = $state(true);
  let error = $state('');

  $effect(() => {
    const token = $auth.token ?? undefined;
    const projectId = $auth.projectId ?? undefined;
    if (!token) return;
    loading = true;
    api.get<TopologyData>('/api/v1/networks/topology', token, projectId)
      .then(v => { data = v; })
      .catch(() => { error = '토폴로지 불러오기 실패'; })
      .finally(() => { loading = false; });
  });
</script>

<div class="bg-surface-base border border-line rounded-lg p-5">
  <div class="flex items-center justify-between mb-3.5">
    <div class="text-ink-0 text-[15px] font-semibold">네트워크 토폴로지</div>
    <a href="/dashboard/network/topology" class="text-[13px] text-ink-3 hover:text-ink-1 transition-colors">전체 보기 →</a>
  </div>

  {#if loading}
    <div class="topology-clip flex items-center justify-center">
      <div class="text-ink-3 text-sm">불러오는 중...</div>
    </div>
  {:else if error}
    <div class="topology-clip flex items-center justify-center">
      <div class="text-ink-3 text-sm">{error}</div>
    </div>
  {:else if data && (data.networks.length > 0 || data.routers.length > 0)}
    <div class="topology-clip">
      <TopologyMini {data} />
    </div>
  {:else}
    <div class="topology-clip flex items-center justify-center">
      <div class="text-ink-3 text-sm">네트워크 리소스가 없습니다</div>
    </div>
  {/if}
</div>

<style>
  .topology-clip {
    height: 340px;
    overflow: hidden;
    position: relative;
    border-radius: 10px;
  }
</style>
