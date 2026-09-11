<script lang="ts">
	import Modal from '../Modal.svelte';

	let parentOpen = $state(false);
	let childOpen = $state(false);
	let lockedOpen = $state(false);
</script>

<button type="button" onclick={() => { parentOpen = true; }}>부모 열기</button>
<div data-testid="background-control"><button type="button">배경 작업</button></div>
<button type="button" onclick={() => { lockedOpen = true; }}>잠금 열기</button>

<Modal open={parentOpen} onClose={() => { parentOpen = false; }} ariaLabel="부모 대화상자">
	<div>
		<button type="button">부모 첫 작업</button>
		<button type="button" onclick={() => { childOpen = true; }}>자식 열기</button>
		<button type="button">부모 마지막 작업</button>
	</div>
	<Modal open={childOpen} onClose={() => { childOpen = false; }} ariaLabel="자식 대화상자">
		<div>
			<button type="button">자식 첫 작업</button>
			<button type="button">자식 마지막 작업</button>
		</div>
	</Modal>
</Modal>

<Modal open={lockedOpen} onClose={() => { lockedOpen = false; }} dismissible={false} ariaLabel="잠금 대화상자">
	<div>
		<button type="button" onclick={() => { lockedOpen = false; }}>완료</button>
	</div>
</Modal>
