// 캔버스형 토폴로지의 순수 도메인 타입. wire 타입($lib/types/topology)에서 파생되며 DOM 을 참조하지 않는다.
import type { FloatingIpInfo } from '$lib/types/networks';
import type {
	SubnetDetail,
	TopologyInstance,
	TopologyLBListener,
	TopologyLBMember,
	TopologyLoadBalancer,
	TopologyNetwork,
	TopologyRouter,
} from '$lib/types/topology';

export type CanvasNodeKind = 'switch' | 'router' | 'vm' | 'lb';
export type CanvasNetKind = 'external' | 'shared' | 'internal';
export type CanvasNetTier = 'provider' | 'tenant';
export type CanvasEdgeKind = 'cable' | 'trunk' | 'fip' | 'lbvip' | 'lbmember';

export interface Pt { x: number; y: number; }
export interface Rect { x: number; y: number; w: number; h: number; }
export type Side = 'TOP' | 'BOTTOM' | 'LEFT' | 'RIGHT';

export interface CanvasNet {
	id: string;
	name: string;
	kind: CanvasNetKind;
	tier: CanvasNetTier;
	/** tenant 네트워크 중 어떤 라우터에도 연결되지 않은 경우 */
	isolated: boolean;
	cidrs: string[];
	subnets: SubnetDetail[];
	status: string;
	project_id: string | null;
	/** CSS 변수 문자열. 예: 'var(--color-topology-internal)' */
	color: string;
	raw: TopologyNetwork;
}

export interface CanvasFip {
	addr: string;
	netId: string | null;
	fixed: string | null;
	status: string | null;
}

export interface CanvasNic {
	/** `${instanceId}|${netId}|${idx}` */
	key: string;
	idx: number;
	/** 카드 내부 행 인덱스(FIP 행 포함 누적) */
	rowIdx: number;
	label: string;
	netId: string;
	ip: string;
	ips: string[];
	mac: string | null;
	portId: string | null;
	fips: CanvasFip[];
}

export interface RouterPort {
	label: string;
	netId: string;
	ip: string | null;
	subnet: (SubnetDetail & { netId: string }) | null;
}

export interface VmMeta {
	flavor_name: string | null;
	image_id: string | null;
	project_id: string | null;
}

interface CanvasNodeBase {
	id: string;
	name: string;
	status: string;
	netIds: string[];
}

export interface SwitchNode extends CanvasNodeBase {
	kind: 'switch';
	netId: string;
	role: string;
	isolated: boolean;
}

export interface RouterNode extends CanvasNodeBase {
	kind: 'router';
	extNetId: string | null;
	intNetIds: string[];
	ports: RouterPort[];
	badges: string[];
	raw: TopologyRouter;
}

export interface VmNode extends CanvasNodeBase {
	kind: 'vm';
	nics: CanvasNic[];
	rows: number;
	parked: boolean;
	/** Trove 데이터베이스 인스턴스 — 존 안에서 인스턴스 아래 계층에 배치한다 */
	isDatabase: boolean;
	meta: VmMeta;
	raw: TopologyInstance;
}

export interface LbNode extends CanvasNodeBase {
	kind: 'lb';
	operating: string;
	vipNetId: string | null;
	vip: string | null;
	listeners: TopologyLBListener[];
	members: TopologyLBMember[];
	memberVmIds: string[];
	parked: boolean;
	raw: TopologyLoadBalancer;
}

export type CanvasNode = SwitchNode | RouterNode | VmNode | LbNode;

export interface CanvasEdge {
	key: string;
	kind: CanvasEdgeKind;
	from: string;
	to: string;
	netId: string;
	/** from 쪽이 VM 일 때 사용하는 NIC */
	nic?: CanvasNic;
	/** to 쪽이 VM 일 때 사용하는 NIC(lbmember) */
	toNic?: CanvasNic;
	portId?: string | null;
	instanceId?: string;
	lbId?: string;
	memberId?: string;
	fip?: CanvasFip;
}

export interface CanvasGraph {
	nets: CanvasNet[];
	netById: Map<string, CanvasNet>;
	nodes: Map<string, CanvasNode>;
	edges: CanvasEdge[];
	edgesByNode: Map<string, CanvasEdge[]>;
	subnetNet: Map<string, string>;
	subnetById: Map<string, SubnetDetail & { netId: string }>;
	fipByAddr: Map<string, FloatingIpInfo>;
}

/** 배치된 tenant 행 하나. provider 행은 order.provider / L.PROV_Y 로 따로 표현한다. */
export interface LayoutRow {
	/** provider 로부터의 라우터 홉 수(1, 2, 3…). 라우터로 provider 에 닿지 않는 독립 행은 null */
	depth: number | null;
	/** 이 행 존의 좌→우 배치 순서. HUD 라벨의 "이전 존과 겹치면 밀기" 는 이 배열 단위로 돌아야 한다 */
	netIds: string[];
	/** 이 행 라우터 레인의 라우터 id, 이름 순 */
	routerIds: string[];
	/** 이 행 라우터 레인 y. 라우터가 없으면 tenantY 와 같다 */
	routerY: number;
	/** 이 행 존(스위치 행) y */
	tenantY: number;
}

export interface LayoutBands {
	/** 위→아래 tenant 행. 망도 라우터도 없는 깊이는 담기지 않으므로 행 인덱스는 연속이다(깊이와 다를 수 있다). */
	rows: LayoutRow[];
	/** @deprecated 배치된 첫 행의 routerY. 행이 하나도 없으면 provider 바닥 + ROUTER_GAP. 새 코드는 rows[0] 을 쓸 것 */
	ROUTER_Y: number;
	/** @deprecated 배치된 첫 행의 tenantY */
	LOWER_Y: number;
	/**
	 * @deprecated 배치된 **마지막** 행의 routerY. 이름과 달리 독립(solo) 행이라는 보장이 없다 —
	 * 독립 망이 없으면 가장 깊은 도달 가능 행을 가리킨다. 새 코드는 rows.at(-1) 을 쓸 것.
	 */
	SOLO_ROUTER_Y: number;
	/** @deprecated 배치된 마지막 행의 tenantY. 위와 같은 이름 함정 */
	SOLO_Y: number;
	/** 노드·존 rect 를 모두 포함한 콘텐츠 바닥 */
	BOTTOM_Y: number;
	/** 노드·존 rect 를 모두 포함한 콘텐츠 우단. `totalW` 는 밴드 중앙 정렬용 폭이라 존 밖 라우터 레인·주차 스트립을 빠뜨린다 */
	RIGHT_X: number;
	totalW: number;
}

export interface LayoutResult {
	pos: Map<string, Rect>;
	/**
	 * provider = 깊이 0(외부·공유), lower = 라우터로 provider 에 닿는 모든 망을 위→아래·좌→우로 이어붙인 것,
	 * solo = 닿지 않는 독립 망 행. **행 경계가 필요하면 bands.rows 를 써라** — lower 는 여러 행이 flatten 돼 있다.
	 */
	order: { provider: string[]; lower: string[]; solo: string[] };
	/** vmId → home 존 netId 목록(0, 1, 2개) */
	home: Map<string, string[]>;
	/** netId → 존 멤버 노드 id(스위치 포함) */
	zoneMembers: Map<string, string[]>;
	parked: Set<string>;
	domOrder: string[];
	bands: LayoutBands;
}

export interface EdgeGeometry {
	d: string;
	a: Pt;
	b: Pt;
	mid: Pt;
	sa: Side;
	sb: Side;
}

export interface GeometryResult {
	geom: Map<string, EdgeGeometry>;
	slotOrder: Map<string, string[]>;
	zones: Map<string, Rect>;
}

export interface ViewState {
	panX: number;
	panY: number;
	k: number;
}

export type ManualPositions = Record<string, { x: number; y: number }>;

export interface EdgeStyle {
	opacity: number;
	width: number;
	dash: string | null;
	bps: number | null;
	rate: { rx_bps: number; tx_bps: number } | null;
}

export interface QueryMatch {
	nodes: Set<string>;
	nets: Set<string>;
}
