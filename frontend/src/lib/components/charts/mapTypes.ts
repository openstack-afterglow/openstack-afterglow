import type { FeatureCollection, Geometry } from 'geojson';

export type MapCoordinate = [longitude: number, latitude: number];

export interface ChoroplethFeatureState {
	name: string;
	/** Fully localized accessible observation, including the no-data case. */
	label: string;
	/** An absent observation is null; a measured zero stays zero. */
	value: number | null;
	fill: string;
}

export interface MapFlow {
	key: string;
	from: MapCoordinate;
	to: MapCoordinate;
	color: string;
	width: number;
	dashed?: boolean;
	highlighted?: boolean;
	opacity?: number;
}

/** Geographic data/interaction only: the adapter never imports an API schema. */
export interface ChoroplethSpec {
	kind: 'choropleth';
	data: FeatureCollection<Geometry, Record<string, unknown>>;
	/** Property containing the selection key; null properties are not selectable. */
	featureKey: string;
	features: Record<string, ChoroplethFeatureState>;
	label: string;
	selectedKey: string;
	activeKey: string;
	onSelect: (key: string) => void;
	onHover: (key: string | null) => void;
	flows?: MapFlow[];
	anchor?: { coordinate: MapCoordinate; radius: number | null };
}
