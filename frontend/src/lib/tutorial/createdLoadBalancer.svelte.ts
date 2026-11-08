// The load balancer create page navigates to the new item's detail page, so the tutorial's
// item-scoped delete anchor needs the created id across that navigation. Page state is not
// usable here: the tutorial layout re-issues query-less navigations, which drops it.
export const createdLoadBalancer = $state<{ id: string | null }>({ id: null });
