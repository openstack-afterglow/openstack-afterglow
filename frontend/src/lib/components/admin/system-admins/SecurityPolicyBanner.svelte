<script lang="ts">
	interface SecurityPolicy {
		legacy_compat: boolean;
		system_admin_count: number;
		admin_project_member_count: number;
	}

	let {
		policy,
		onMigrate,
	}: {
		policy: SecurityPolicy;
		onMigrate: () => void;
	} = $props();
</script>

{#if !policy.legacy_compat && policy.system_admin_count === 0}
	<div class="mb-4 flex items-start gap-3 rounded-lg border border-red-700 bg-red-900/20 px-4 py-3 text-sm">
		<span class="mt-0.5 text-red-400 shrink-0">⚠</span>
		<div class="flex-1">
			<span class="font-semibold text-red-300">Lockout 위험</span>
			<span class="text-red-400 ml-1">system admin이 없고 호환 모드가 비활성화되어 있습니다. 관리자 접근이 차단됩니다.</span>
			<span class="block mt-1 text-red-500 text-xs">복구: <code class="bg-red-900/40 px-1 rounded">python3 scripts/manage_system_admins.py --os-system-scope grant &lt;user-id&gt;</code></span>
		</div>
	</div>
{:else if !policy.legacy_compat}
	<div class="mb-4 flex items-center gap-3 rounded-lg border border-green-700 bg-green-900/20 px-4 py-3 text-sm">
		<span class="text-green-400 shrink-0">✓</span>
		<span class="text-green-300">
			Strict 모드: <strong>system:all</strong> role 보유자({policy.system_admin_count}명)만 관리자입니다.
		</span>
	</div>
{:else}
	<div class="mb-4 flex items-center justify-between gap-3 rounded-lg border border-action-warm bg-surface-selected/20 px-4 py-3 text-sm">
		<div class="flex items-center gap-2 flex-1 min-w-0">
			<span class="text-action-warm shrink-0">⚙</span>
			<span class="text-action-warm">
				Legacy 호환 모드: admin project 멤버({policy.admin_project_member_count}명)도 관리자 권한을 가집니다. 마이그레이션 후 strict 모드로 전환하세요.
			</span>
		</div>
		<button
			onclick={onMigrate}
			class="shrink-0 px-3 py-1.5 text-xs font-medium rounded-lg bg-action-warm/50 hover:bg-action-warm-hover/80 text-action-warm whitespace-nowrap"
		>
			일괄 마이그레이션
		</button>
	</div>
{/if}
