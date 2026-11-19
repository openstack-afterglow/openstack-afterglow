/**
 * Isometric grid view scene contract.
 *
 * Adapters (topology, instance network, Waygate) build an `IsoScene` from observed API data;
 * `IsoGridView.svelte` projects it onto an isometric grid floor. Coordinates are logical grid
 * cells, not pixels: +x runs toward the lower right, +y toward the lower left, z lifts a node.
 * The scene is presentation only: it must never imply reachability or state that the source
 * data does not report (unknown stays unknown).
 */

/** Semantic colour roles, mapped to Afterglow topology/state tokens in both themes. */
export type IsoTone =
	| 'external'
	| 'shared'
	| 'internal'
	| 'internal-2'
	| 'router'
	| 'gateway'
	| 'accent'
	| 'info'
	| 'success'
	| 'warning'
	| 'danger'
	| 'neutral';

/** Node glyph/shape family. `block` kinds render as raised prisms; others as flat or small marks. */
export type IsoNodeKind =
	| 'instance'
	| 'router'
	| 'loadbalancer'
	| 'database'
	| 'gateway'
	| 'vpn-server'
	| 'peer'
	| 'peer-group'
	| 'internet'
	| 'cidr'
	| 'floating-ip'
	| 'port'
	| 'security-group'
	| 'volume'
	| 'file-share'
	| 'k8s-service';

/** Observed health for a node; `unknown` must be used when the source does not report state. */
export type IsoStatus = 'ok' | 'pending' | 'warning' | 'error' | 'off' | 'unknown';

export interface IsoBadge {
	text: string;
	tone: IsoTone;
}

export interface IsoNode {
	id: string;
	kind: IsoNodeKind;
	label: string;
	sublabel?: string;
	tone: IsoTone;
	/** Grid cell coordinates (may be fractional). */
	x: number;
	y: number;
	/** Height level above the floor; platforms sit at 0, blocks default to 0. */
	z?: number;
	size?: 'sm' | 'md' | 'lg';
	status?: IsoStatus;
	badges?: IsoBadge[];
	/** Full accessible name; defaults to `label, sublabel`. */
	ariaLabel?: string;
	/** Optional id of the platform this node stands on (for grouping/highlight). */
	platformId?: string;
	/** Non-interactive nodes are drawn but not focusable/selectable. */
	interactive?: boolean;
}

export interface IsoPlatform {
	id: string;
	label: string;
	sublabel?: string;
	tone: IsoTone;
	/** Grid origin and size in cells. */
	x: number;
	y: number;
	w: number;
	h: number;
	/** `slab`: raised plate (networks, peer groups). `zone`: dashed boundary (security group, project). */
	style: 'slab' | 'zone';
	/** Optional resource kind for the accessible name; generic slabs and zones use their shape. */
	kind?: 'external-network' | 'shared-network' | 'internal-network';
	interactive?: boolean;
}

export type IsoEdgeKind = 'link' | 'flow' | 'tunnel' | 'ingress' | 'egress' | 'denied';

export interface IsoEdge {
	id: string;
	/** Node or platform ids. */
	from: string;
	to: string;
	kind: IsoEdgeKind;
	tone: IsoTone;
	label?: string;
	/** Draw an arrowhead at `to` (and at `from` when bidirectional). */
	directed?: boolean;
	bidirectional?: boolean;
	/** Animate a configured path (default true for every edge, subject to motion preferences). */
	flow?: boolean;
	dashed?: boolean;
	/** Dashed/muted presentation for a reported inactive path. Does not disable configured-path motion. */
	inactive?: boolean;
}

export interface IsoLegendItem {
	label: string;
	tone: IsoTone;
	kind: 'node' | 'platform' | 'edge' | 'packet';
}

export interface IsoScene {
	nodes: IsoNode[];
	platforms: IsoPlatform[];
	edges: IsoEdge[];
	legend?: IsoLegendItem[];
}

/** Shared persisted preference for host surfaces that offer grid and list views. */
export type IsoViewMode = 'grid' | 'list';
