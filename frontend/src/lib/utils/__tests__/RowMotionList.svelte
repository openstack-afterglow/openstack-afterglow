<script lang="ts">
	import { rowChanged, rowEnter, rowExit, rowReflow } from '../rowMotion';

	let { rows }: { rows: { id: string; name: string; size: number }[] } = $props();
</script>

<table>
	<tbody>
		{#each rows as row (row.id)}
			<tr data-id={row.id} in:rowEnter out:rowExit animate:rowReflow use:rowChanged={row}>
				<td>{row.name}</td>
				<td>{row.size}</td>
			</tr>
		{/each}
	</tbody>
</table>
