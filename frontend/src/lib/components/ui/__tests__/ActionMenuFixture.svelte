<script lang="ts">
	import ActionMenu from '../ActionMenu.svelte';

	let open = $state(false);
	let actionCount = $state(0);
	let rowCount = $state(0);
</script>

<button type="button" aria-label="메뉴 밖" data-testid="outside">메뉴 밖</button>
<div
	role="button"
	tabindex="0"
	aria-label="인스턴스 행"
	onclick={() => { rowCount += 1; }}
	onkeydown={() => {}}
>
	<ActionMenu
		{open}
		onopen={() => { open = true; }}
		onclose={() => { open = false; }}
		ariaLabel="인스턴스 작업"
	>
		<button type="button" disabled>사용 불가</button>
		<button type="button" onclick={() => { actionCount += 1; }}>시작</button>
		<button type="button">중지</button>
	</ActionMenu>
</div>
<output data-testid="action-count">{actionCount}</output>
<output data-testid="row-count">{rowCount}</output>
