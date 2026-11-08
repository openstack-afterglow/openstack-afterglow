// The VM create wizard returns to the instance list, and the instance-detail-delete tour then opens
// the new instance's detail page. Its item-scoped stop/delete anchors need the created id across
// those navigations; page state is not usable because the tutorial layout re-issues navigations.
export const createdInstance = $state<{ id: string | null }>({ id: null });
