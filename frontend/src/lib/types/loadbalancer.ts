export interface LoadBalancer {
  id: string;
  name: string;
  status: string;
  operating_status: string;
  vip_address: string | null;
  vip_subnet_id: string | null;
  project_id?: string | null;
  tags?: string[];
}

export interface LoadBalancerDetail {
  id: string;
  name: string;
  description?: string | null;
  status: string;
  operating_status: string;
  vip_address: string | null;
  vip_subnet_id: string | null;
  project_id?: string | null;
  tags?: string[];
}

export interface Listener {
  id: string;
  name: string;
  protocol: string;
  protocol_port: number;
  status: string;
  default_pool_id: string | null;
}

export interface Pool {
  id: string;
  name: string;
  protocol: string;
  lb_algorithm: string;
  status: string;
}

export interface Member {
  id: string;
  address: string;
  protocol_port: number;
  weight: number;
  status: string;
}

export interface LbStatusNode {
  id?: string;
  name?: string;
  provisioning_status?: string | null;
  operating_status?: string | null;
  listeners?: Array<{
    id?: string;
    name?: string;
    provisioning_status?: string;
    pools?: Array<{
      id?: string;
      name?: string;
      provisioning_status?: string;
      members?: Array<{
        id?: string;
        name?: string;
        provisioning_status?: string;
      }>;
    }>;
  }>;
  pools?: Array<{
    id?: string;
    name?: string;
    provisioning_status?: string;
    members?: Array<{
      id?: string;
      name?: string;
      provisioning_status?: string;
    }>;
  }>;
}
