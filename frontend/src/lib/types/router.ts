export interface RouterInterface {
  id: string;
  subnet_id: string;
  subnet_name: string;
  network_id: string;
  ip_address: string;
}

export interface RouterDetail {
  id: string;
  name: string;
  status: string;
  project_id: string | null;
  external_gateway_network_id: string | null;
  external_gateway_network_name: string | null;
  interfaces: RouterInterface[];
}

export interface RouterSubnet {
  id: string;
  name: string;
  cidr: string;
  network_id: string;
  gateway_ip?: string | null;
}
