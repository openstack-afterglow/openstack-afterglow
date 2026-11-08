// Keeps the port a tutorial just created on page 1 so its delete step can anchor on it even when the real
// list has more rows than one page. Without a running tour the Neutron order is returned unchanged.
export function pinCreatedPort<T extends { id: string }>(
	items: T[],
	created: T | null,
	options: { tourActive: boolean; firstPage: boolean; scoped: boolean },
): T[] {
	if (!options.tourActive || !options.firstPage || options.scoped || !created) return items;
	return items.some((item) => item.id === created.id) ? items : [created, ...items];
}
