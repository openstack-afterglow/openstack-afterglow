<script lang="ts">
	import { useDbCreate } from '$lib/stores/dbCreateStore.svelte';
	const s = useDbCreate();
</script>

<div class="space-y-4">
	<div>
		<label class={s.labelCls} for="field-dbcreatestep1details-8">인스턴스 이름 <span class="text-red-400">*</span></label>
		<input id="field-dbcreatestep1details-8" type="text" bind:value={s.name} placeholder="my-database" class={s.inputCls} />
	</div>

	<div class="grid grid-cols-2 gap-3">
		<div>
			<label class={s.labelCls} for="field-dbcreatestep1details-14">데이터스토어 <span class="text-red-400">*</span></label>
			{#if s.datastores.length}
				<select id="field-dbcreatestep1details-14"
					value={s.datastoreType}
					onchange={(e) => s.selectDatastore((e.target as HTMLSelectElement).value)}
					class={s.inputCls}
				>
					{#each s.datastores as ds}
						<option value={ds.name}>{ds.name}</option>
					{/each}
				</select>
			{:else}
				<input type="text" bind:value={s.datastoreType} placeholder="mysql" class={s.inputCls} />
			{/if}
		</div>
		<div>
			<label class={s.labelCls} for="field-dbcreatestep1details-30">버전 <span class="text-red-400">*</span></label>
			{#if s.selectedDs?.versions.length}
				<select id="field-dbcreatestep1details-30" bind:value={s.datastoreVersion} class={s.inputCls}>
					{#each s.selectedDs.versions as v}
						<option value={v.name}>{v.name}</option>
					{/each}
				</select>
			{:else}
				<input type="text" bind:value={s.datastoreVersion} placeholder="5.7" class={s.inputCls} />
			{/if}
		</div>
	</div>

	<div>
		<label class={s.labelCls} for="field-dbcreatestep1details-44">플레이버 <span class="text-red-400">*</span></label>
		{#if s.flavors.length}
			<select id="field-dbcreatestep1details-44" bind:value={s.flavorId} class={s.inputCls}>
				{#each s.flavors as f}
					<option value={f.id}>{f.name} ({f.vcpus} vCPU · {Math.round(f.ram / 1024)} GB RAM)</option>
				{/each}
			</select>
		{:else}
			<input type="text" bind:value={s.flavorId} placeholder="flavor ID" class={s.inputCls} />
		{/if}
	</div>

	<div class="grid grid-cols-2 gap-3">
		<div>
			<label class={s.labelCls} for="field-dbcreatestep1details-58">볼륨 크기 (GB) <span class="text-red-400">*</span></label>
			<input id="field-dbcreatestep1details-58" type="number" bind:value={s.volumeSize} min="1" max="1024" class={s.inputCls} />
		</div>
		<div>
			<label class={s.labelCls} for="field-dbcreatestep1details-62">볼륨 타입</label>
			<select id="field-dbcreatestep1details-62" bind:value={s.volumeType} class={s.inputCls}>
				<option value="">기본값</option>
				{#each s.volumeTypes as vt}
					<option value={vt.name}>{vt.name}</option>
				{/each}
			</select>
			<p class="text-xs text-ink-3 mt-1">기본값을 권장합니다. 모든 Cinder 타입이 Trove 와 호환되지 않습니다.</p>
		</div>
	</div>

	<div>
		<label class={s.labelCls} for="field-dbcreatestep1details-74">가용 구역</label>
		<select id="field-dbcreatestep1details-74" bind:value={s.availabilityZone} class={s.inputCls}>
			<option value="">자동 선택</option>
			{#each s.availabilityZones as az}
				<option value={az.name}>{az.name}</option>
			{/each}
		</select>
	</div>
</div>
