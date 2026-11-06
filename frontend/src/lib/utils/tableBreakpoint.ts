import { MediaQuery } from 'svelte/reactivity';

/** One viewport owner for authored tables/cards and their equivalent controls. */
export const tableDesktop = new MediaQuery('(min-width: 1024px)', true);
