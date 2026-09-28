import type { BetaFeatures } from '$lib/stores/betaFeatures';

export interface NavItem {
  label: string;
  href: string;
  service: string | null;
  beta?: keyof BetaFeatures;
  topLevel?: boolean;
}

export interface NavSection {
  label: string;
  prefix: string;
  extraPrefixes?: string[];
  icon: string;
  service?: string | null;
  beta?: keyof BetaFeatures;
  items: NavItem[];
}

export const userNavSections: NavSection[] = [
  {
    label: 'Compute',
    prefix: '/dashboard/compute',
    extraPrefixes: [],
    icon: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2',
    items: [
      { label: '인스턴스', href: '/dashboard/compute/instances', service: null },
      { label: '이미지', href: '/dashboard/compute/images', service: null },
    ],
  },
  {
    label: '볼륨',
    prefix: '/dashboard/volumes',
    extraPrefixes: [],
    icon: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4',
    items: [
      { label: '볼륨 목록', href: '/dashboard/volumes', service: null },
      { label: '볼륨 백업', href: '/dashboard/volumes/backups', service: null, beta: 'volumeBackups' },
      { label: '볼륨 스냅샷', href: '/dashboard/volumes/snapshots', service: null, beta: 'volumeSnapshots' },
    ],
  },
  {
    label: 'File Storage',
    prefix: '/dashboard/file-storage',
    extraPrefixes: [],
    icon: 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z',
    service: 'manila',
    items: [
      { label: '파일 스토리지', href: '/dashboard/file-storage', service: null },
      { label: '스냅샷', href: '/dashboard/file-storage/snapshots', service: null, beta: 'fileStorageSnapshots' },
      { label: 'Share 네트워크', href: '/dashboard/file-storage/networks', service: null, beta: 'fileStorageShareNetworks' },
      { label: 'Security Service', href: '/dashboard/file-storage/security-services', service: null, beta: 'fileStorageSecurityServices' },
    ],
  },
  {
    label: '컨테이너',
    prefix: '/dashboard/containers',
    extraPrefixes: ['/dashboard/drover'],
    icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4',
    service: 'containers',
    items: [
      { label: 'K8s 클러스터', href: '/dashboard/containers/clusters', service: 'magnum' },
      { label: '컨테이너', href: '/dashboard/containers/instances', service: 'zun' },
      { label: 'Drover', href: '/dashboard/drover', service: 'k3s' },
    ],
  },
  {
    label: 'Database',
    prefix: '/dashboard/database',
    extraPrefixes: [],
    icon: 'M4 7c0-1.657 3.582-3 8-3s8 1.343 8 3M4 7v5c0 1.657 3.582 3 8 3s8-1.343 8-3V7M4 7c0 1.657 3.582 3 8 3s8-1.343 8-3M4 12v5c0 1.657 3.582 3 8 3s8-1.343 8-3v-5',
    service: 'trove',
    items: [
      { label: 'DB 인스턴스', href: '/dashboard/database/instances', service: null },
      { label: 'DB 백업', href: '/dashboard/database/backups', service: null, beta: 'databaseBackups' },
    ],
  },
  {
    label: 'Object Storage',
    prefix: '/dashboard/object-storage',
    extraPrefixes: [],
    icon: 'M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z',
    service: 'swift',
    items: [
      { label: '버킷', href: '/dashboard/object-storage/buckets', service: null },
    ],
  },
  {
    label: 'Key Manager',
    prefix: '/dashboard/secrets',
    extraPrefixes: [],
    icon: 'M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z',
    beta: 'keyManager',
    items: [
      { label: '비밀 관리', href: '/dashboard/secrets', service: null },
    ],
  },
  {
    label: 'AI 채팅',
    prefix: '/dashboard/chat',
    extraPrefixes: [],
    icon: 'M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z',
    service: 'chat',
    items: [
      { label: 'Lumen', href: '/dashboard/chat', service: 'chat' },
    ],
  },
  {
    label: '네트워크',
    prefix: '/dashboard/network',
    extraPrefixes: [],
    icon: 'M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9',
    items: [
      { label: '네트워크', href: '/dashboard/network/networks', service: null },
      { label: 'Floating IP', href: '/dashboard/network/floating-ips', service: null },
      { label: '라우터', href: '/dashboard/network/routers', service: null },
      { label: '로드밸런서', href: '/dashboard/network/loadbalancers', service: null },
      { label: '보안 그룹', href: '/dashboard/network/security-groups', service: null },
      { label: 'Waygate', href: '/dashboard/network/waygate', service: 'waygate' },
    ],
  },
];

export const adminNavSections: NavSection[] = [
  {
    label: 'Compute',
    prefix: '/admin/instances',
    icon: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2',
    items: [
      { label: '전체 인스턴스', href: '/admin/instances', service: null },
      { label: 'Flavor', href: '/admin/flavors', service: null },
      { label: '이미지', href: '/admin/images', service: null },
      { label: '하이퍼바이저', href: '/admin/hypervisors', service: null },
    ],
  },
  {
    label: '스토리지',
    prefix: '/admin/volumes',
    icon: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4',
    items: [
      { label: '전체 볼륨', href: '/admin/volumes', service: null },
      { label: '파일 스토리지', href: '/admin/file-storage', service: 'manila' },
      { label: 'DB 인스턴스', href: '/admin/database-instances', service: 'trove' },
      { label: 'Object Storage', href: '/admin/object-storage', service: 'swift' },
    ],
  },
  {
    label: '네트워크',
    prefix: '/admin/topology',
    icon: 'M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9',
    items: [
      { label: '토폴로지', href: '/admin/topology', service: null },
      { label: '네트워크', href: '/admin/networks', service: null },
      { label: 'Floating IP', href: '/admin/floating-ips', service: null },
      { label: '라우터', href: '/admin/routers', service: null },
      { label: '로드밸런서', href: '/admin/loadbalancers', service: null },
      { label: '포트', href: '/admin/ports', service: null },
    ],
  },
  {
    label: '컨테이너',
    prefix: '/admin/containers',
    icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4',
    items: [
      { label: '전체 컨테이너', href: '/admin/containers', service: 'zun' },
    ],
  },
  {
    label: '서비스',
    prefix: '/admin/drover',
    icon: 'M4 7h16M4 12h16M4 17h16',
    items: [
      { label: 'Drover', href: '/admin/drover', service: 'k3s', topLevel: true },
      { label: 'Lumen', href: '/admin/chat', service: 'chat', topLevel: true },
      { label: 'Palimpsest', href: '/admin/libraries', service: null, topLevel: true },
      { label: 'Waygate', href: '/admin/waygate', service: 'waygate', topLevel: true },
      { label: '클러스터 템플릿', href: '/admin/drover/templates', service: 'k3s' },
      { label: '채팅 통계', href: '/admin/chat/stats', service: 'chat' },
      { label: '사용자 쿼터', href: '/admin/chat/quotas', service: 'chat' },
      { label: '모델 설정', href: '/admin/chat/models', service: 'chat' },
      { label: '도구 설정', href: '/admin/chat/tools', service: 'chat' },
    ],
  },
  {
    label: 'Key Manager',
    prefix: '/admin/secrets',
    icon: 'M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z',
    beta: 'keyManager',
    items: [
      { label: '프로젝트 쿼터', href: '/admin/secrets', service: null },
    ],
  },
  {
    label: '모니터링',
    prefix: '/admin/monitoring',
    icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z',
    items: [
      { label: '통합 모니터링', href: '/admin/monitoring', service: null },
      { label: '노드', href: '/admin/monitoring/node', service: null },
      { label: 'MySQL', href: '/admin/monitoring/mysql', service: null },
      { label: 'HAProxy', href: '/admin/monitoring/haproxy', service: null },
      { label: 'RabbitMQ', href: '/admin/monitoring/rabbitmq', service: null },
      { label: 'Memcached', href: '/admin/monitoring/memcached', service: null },
      { label: 'etcd', href: '/admin/monitoring/etcd', service: null },
      { label: 'Libvirt', href: '/admin/monitoring/libvirt', service: null },
      { label: 'OpenStack', href: '/admin/monitoring/openstack', service: null },
      { label: 'Ceph', href: '/admin/monitoring/ceph', service: null },
    ],
  },
  {
    label: '시스템',
    prefix: '/admin/services',
    icon: 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z',
    items: [
      { label: '서비스 상태', href: '/admin/services', service: null },
      { label: '운영 이벤트', href: '/admin/events', service: null },
      { label: '고아 리소스', href: '/admin/orphans', service: null },
      { label: 'Notion 연동', href: '/admin/notion', service: null },
      { label: '공지 관리', href: '/admin/announcements', service: null },
      { label: '기본 설정', href: '/admin/settings', service: null },
    ],
  },
  {
    label: 'Identity',
    prefix: '/admin/users',
    icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z',
    items: [
      { label: '사용자', href: '/admin/users', service: null },
      { label: '프로젝트', href: '/admin/projects', service: null },
      { label: '쿼터', href: '/admin/quotas', service: null },
      { label: '그룹', href: '/admin/groups', service: null },
      { label: '역할', href: '/admin/roles', service: null },
      { label: '시스템 관리자', href: '/admin/system-admins', service: null },
    ],
  },
];

export function isNavSectionActive(section: NavSection, pathname: string): boolean {
  const matches = (href: string) => pathname === href || pathname.startsWith(`${href}/`);
  return matches(section.prefix) || section.extraPrefixes?.some(matches) === true || section.items.some((item) => matches(item.href));
}

export function allNavItems(isAdmin: boolean, betaFeatures: BetaFeatures): Array<NavItem & { section: string }> {
  const sections = isAdmin ? adminNavSections : userNavSections;
  const overview = isAdmin ? [{ label: '개요', href: '/admin', service: null, section: '개요' }] : [];
  return [...overview, ...sections.flatMap((section) => {
    if (section.beta && !betaFeatures[section.beta]) return [];
    return section.items
      .filter((item) => !item.beta || betaFeatures[item.beta])
      .map((item) => ({ ...item, service: item.service ?? section.service ?? null, section: section.label }));
  })];
}
