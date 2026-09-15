#!/usr/bin/env node
const fs = require("fs");
const path = require("path");
const { spawn, spawnSync } = require("child_process");

const rootDir = path.resolve(__dirname, "..");
const backendDir = path.join(rootDir, "backend");
const frontendDir = path.join(rootDir, "frontend");
const dbRequirementMessage = "AFTERGLOW_TEST_DATABASE_URL is required for target db. Example: mysql+aiomysql://afterglow:dev@127.0.0.1:3306/afterglow_pytest";


function expandChatBackendSelectors() {
	const testsDir = path.join(backendDir, "tests");
	return fs
		.readdirSync(testsDir, { withFileTypes: true })
		.filter((entry) => entry.isFile() && /^test_chat_.*\.py$/.test(entry.name))
		.map((entry) => `tests/${entry.name}`)
		.sort();
}

function expandDbBackendSelectors() {
	const testsDir = path.join(backendDir, "tests");
	return fs
		.readdirSync(testsDir, { withFileTypes: true })
		.filter((entry) => entry.isFile() && /^test_.*\.py$/.test(entry.name))
		.filter((entry) => {
			const source = fs.readFileSync(path.join(testsDir, entry.name), "utf8");
			return source
				.split(/\r?\n/)
				.some((line) => /^\s*(?:pytestmark\s*=.*pytest\.mark\.db|@pytest\.mark\.db\b)/.test(line));
		})
		.map((entry) => `tests/${entry.name}`)
		.sort();
}


function expandChatFrontendSelectors() {
	const apiTestsDir = path.join(frontendDir, "src", "lib", "api", "__tests__");
	const selectors = fs
		.readdirSync(apiTestsDir, { withFileTypes: true })
		.filter((entry) => entry.isFile() && /^chat.*\.test\.ts$/.test(entry.name))
		.map((entry) => `src/lib/api/__tests__/${entry.name}`)
		.sort();
	selectors.push("src/routes/__tests__/chat-gated-surfaces.test.ts");
	const componentTests = "src/lib/components/chat/__tests__";
	if (fs.existsSync(path.join(frontendDir, componentTests))) selectors.push(componentTests);
	return selectors;
}

const targets = {
	auth: {
		description: "Login/logout, token, session, site-config auth surfaces",
		liveServices: "none",
		backend: {
			selectors: [
				"tests/test_auth_endpoints.py",
				"tests/test_auth_jwt.py",
				"tests/test_auth_security.py",
				"tests/test_jwt_session_timeout.py",
				"tests/test_session_device.py",
				"tests/test_session_security.py",
				"tests/test_token_binding.py",
				"tests/test_x_auth_token_removal.py",
				"tests/test_login_guard.py",
				"tests/test_keystone_system_scope.py"
			]
		},
		frontend: {
			selectors: [
				"src/lib/stores/__tests__/auth.test.ts",
				"src/lib/stores/__tests__/auth.security.test.ts",
				"src/lib/stores/__tests__/auth.sync.test.ts",
				"src/lib/api/__tests__/client.authRedirect.test.ts",
				"src/lib/utils/__tests__/authFlow.test.ts",
				"src/lib/components/auth/__tests__/LoginBrandHeader.test.ts",
				"src/routes/__tests__/gitlab-auth-paths.test.ts",
				"src/routes/__tests__/logout-flow.test.ts",
				"src/lib/config/site.test.ts"
			]
		}
	},
	access: {
		description: "Admin-only checks, owner checks, IDOR/BOLA, v1 compatibility",
		liveServices: "none",
		backend: {
			selectors: [
				"tests/test_admin_write.py",
				"tests/test_admin_identity.py",
				"tests/test_project_self_service.py",
				"tests/test_database_owner_check.py",
				"tests/test_file_storage_owner_check.py",
				"tests/test_network_owner_check.py",
				"tests/test_volume_owner_check.py",
				"tests/test_loadbalancer_owner_check.py",
				"tests/test_secrets_admin.py",
				"tests/test_endpoint_inventory.py",
				"tests/test_api_v1_legacy_compat.py"
			]
		}
	},
	config: {
		description: "afterglow.conf, K8s config generation, cache, frontend runtime config",
		liveServices: "none",
		backend: {
			selectors: [
				"tests/test_afterglow_conf_config.py",
				"tests/contracts/test_ingress_root_path_coverage.py",
				"tests/test_config_insecure_guard.py",
				"tests/test_config_keystone_url.py",
				"tests/test_config_layer_images.py",
				"tests/test_generate_k8s.py",
				"tests/test_cache_abstraction.py",
				"tests/test_cache_opt_in.py",
				"tests/test_cache_ttl_policy.py"
			]
		},
		frontend: {
			selectors: ["src/lib/config/site.test.ts", "src/lib/server/config.test.ts"]
		}
	},
	chat: {
		description: "Built-in chat contracts, runs, workers, providers, assets, memory, and typed UI",
		liveServices: "none",
		backend: {
			selectors: expandChatBackendSelectors
		},
		frontend: {
			selectors: expandChatFrontendSelectors
		}
	},
	crypto: {
		description: "k3s encryption and key derivation",
		liveServices: "none",
		backend: {
			selectors: ["tests/test_k3s_crypto.py", "tests/test_k3s_crypto_v3_subkey.py"],
			extraArgs: ["-m", "crypto"]
		}
	},
	db: {
		description: "MariaDB-backed persistence and SQL behavior",
		liveServices: "MariaDB test database",
		requiredEnv: ["AFTERGLOW_TEST_DATABASE_URL"],
		backend: {
			selectors: expandDbBackendSelectors,
			extraArgs: ["-m", "db"]
		}
	},
	instances: {
		description: "Nova instance API, metadata, metrics, health, and instance UI",
		liveServices: "none",
		backend: {
			selectors: [
				"tests/test_instances.py",
				"tests/test_instance_names.py",
				"tests/test_instance_health.py",
				"tests/test_instance_metrics.py",
				"tests/test_instance_metrics_summary.py",
				"tests/test_instance_password.py",
				"tests/test_instance_boot_from_volume.py",
				"tests/test_instance_existing_upper.py",
				"tests/test_instance_scheduling.py",
				"tests/test_instances_data_mounts.py",
				"tests/test_instances_no_libraries.py",
				"tests/test_bulk_instance_action.py",
				"tests/test_admin_instances.py",
				"tests/test_admin_instances_health.py",
				"tests/test_admin_instance_recovery.py",
				"tests/test_admin_resize.py"
			]
		},
		frontend: {
			selectors: [
				"src/lib/components/instance/__tests__",
				"src/lib/components/admin/__tests__/AdminInstanceTable.test.ts"
			]
		}
	},
	storage: {
		description: "Cinder, Manila, Swift storage APIs and storage UI",
		liveServices: "none",
		backend: {
			selectors: [
				"tests/test_volumes.py",
				"tests/test_volume_backups.py",
				"tests/test_ceph_rbd.py",
				"tests/test_volume_delete_recovery.py",
				"tests/test_volume_extend.py",
				"tests/test_volume_owner_check.py",
				"tests/test_volume_snapshots.py",
				"tests/test_volume_transfer.py",
				"tests/test_admin_volume_delete.py",
				"tests/test_file_storage.py",
				"tests/test_file_storage_owner_check.py",
				"tests/test_share_networks.py",
				"tests/test_share_snapshots.py",
				"tests/test_manila.py",
				"tests/test_manila_error_surfacing.py",
				"tests/test_manila_isolation.py",
				"tests/test_manila_rotate.py",
				"tests/test_object_storage.py",
				"tests/test_object_storage_trash.py",
				"tests/test_object_storage_upload.py",
				"tests/test_bucket_naming.py",
				"tests/test_create_access_rule_metadata.py",
				"tests/test_cinder_pools.py",
				"tests/test_swift_count_all_projects.py",
				"tests/test_swift_owner_metadata.py"
			]
		},
		frontend: {
			selectors: [
				"src/lib/components/admin-volume/__tests__/AdminVolumeDeleteDiagnosticSection.test.ts",
				"src/lib/components/admin/volumes/__tests__/AdminVolumeStatusSummary.test.ts",
				"src/lib/components/admin/file-storage/__tests__",
				"src/lib/components/volume/__tests__/VolumeSummaryCards.test.ts",
				"src/lib/components/volume/__tests__/VolumeBulkSelection.test.ts",
				"src/lib/api/__tests__/client.upload.test.ts"
			]
		}
	},
	layers: {
		description: "Admin libraries, squashfs, and union layer build/consume flow",
		liveServices: "none",
		backend: {
			selectors: [
				"tests/test_common_libraries_squashfs.py",
				"tests/test_layer_ops.py",
				"tests/test_layer_build.py",
				"tests/test_layer_consume.py",
				"tests/test_libraries.py",
				"tests/test_library_builder.py",
				"tests/test_library_usage.py",
				"tests/test_dockerfile_import.py",
				"tests/test_recipe_blocks.py",
				"tests/test_reconcile_builds.py",
				"tests/test_existing_share_build.py",
				"tests/test_ephemeral_build_orchestration.py",
				"tests/test_ephemeral_builder_vm.py",
				"tests/test_ephemeral_mount.py",
				"tests/test_prebuilt_nfs_auto_grant.py",
				"tests/test_smoke_mount_heat.py",
				"tests/test_smoke_mount_tofu.py",
				"tests/test_config_layer_images.py"
			]
		},
		frontend: {
			selectors: [
				"src/routes/admin/libraries/__tests__/libraries-layer-workflow.test.ts",
				"src/lib/components/wizard/__tests__/vm-create-squashfs-beta.test.ts"
			]
		}
	},
	k3s: {
		description: "Drover BFF proxy, cluster management, and nodegroup UI integration tests",
		liveServices: "none",
		backend: {
			selectors: ["tests/contracts/test_drover_proxy.py", "tests/contracts/test_k3s_shell_proxy.py"]
		},
		frontend: {
			selectors: [
				"src/lib/components/k3s/__tests__/K3sStampedeTab.test.ts",
				"src/lib/components/k3s/__tests__/K3sClusterNetworksCard.test.ts",
				"src/lib/components/dashboard/drover/__tests__/K3sNodegroupCard.test.ts"
			]
		}
	},
	workers: {
		description: "Worker runtime, worker templates, and notion worker behavior",
		liveServices: "none",
		backend: {
			selectors: [
				"tests/test_worker_runtime.py",
				"tests/test_worker_runtime_templates.py",
				"tests/test_notion_worker.py"
			]
		}
	},
	waygate: {
		description: "Waygate BFF proxy, agent proxy, and VPN UI integration tests",
		liveServices: "none",
		backend: {
			selectors: ["tests/contracts/test_waygate_proxy.py", "tests/contracts/test_waygate_agent.py"]
		}
	},
	lumen: {
		description: "Lumen BFF proxy, SSE streaming, and chat stream integration tests",
		liveServices: "none",
		backend: {
			selectors: ["tests/contracts/test_lumen_proxy.py"]
		},
		frontend: {
			selectors: [
				"src/lib/api/__tests__/chatTaskLabels.test.ts",
				"src/lib/api/__tests__/chatRevealBuffer.test.ts",
				"src/lib/components/chat/__tests__/ChatPanel.test.ts",
				"src/lib/components/chat/__tests__/ChatInput.test.ts",
				"src/lib/components/chat/__tests__/ModelPickerOverlay.test.ts",
				"src/lib/components/chat/__tests__/ChatWindow.test.ts",
				"src/lib/components/chat/__tests__/ChatSidebar.test.ts",
				"src/lib/api/__tests__/chatStream.test.ts",
				"src/lib/api/__tests__/chatContracts.test.ts",
				"src/lib/api/__tests__/chatRunReducer.test.ts"
			]
		}
	},
	palimpsest: {
		description: "Palimpsest BFF proxy, layer management, and digest tests",
		liveServices: "none",
		backend: {
			selectors: [
				"tests/contracts/test_palimpsest_hub_proxy.py",
				"tests/test_palimpsest_api.py",
				"tests/test_palimpsest_kvm.py",
				"tests/test_palimpsest_dockerfile.py",
				"tests/test_palimpsest_digest.py"
			]
		}
	},
	design: {
		description: "Design-system and raw visual debt guardrails",
		liveServices: "none",
		frontend: {
			selectors: [
				"src/routes/__tests__/designSystemRules.test.ts",
				"src/lib/design/__tests__/visualDebt.test.ts",
				"src/lib/components/ui/__tests__"
			]
		}
	},
	contracts: {
		description: "Service proxy, SDK dependency, ingress, and MCP bridge contract tests",
		liveServices: "none",
		backend: {
			selectors: [
				"tests/contracts/test_service_proxy.py",
				"tests/contracts/test_drover_proxy.py",
				"tests/contracts/test_waygate_proxy.py",
				"tests/contracts/test_waygate_agent.py",
				"tests/contracts/test_lumen_proxy.py",
				"tests/contracts/test_palimpsest_hub_proxy.py",
				"tests/contracts/test_service_sdk_dependency_sources.py",
				"tests/contracts/test_mcp_stage2_adapters.py",
				"tests/contracts/test_ingress_root_path_coverage.py",
				"tests/contracts/test_k3s_shell_proxy.py",
				"tests/contracts/test_mcp_lumen_bridge.py"
			],
			extraArgs: ["-m", "contract"]
		}
	},
	"live:auth": {
		description: "Live OpenStack auth integration slice",
		liveServices: "Redis + OpenStack credentials",
		backend: {
			selectors: ["tests/integration/test_auth.py"]
		}
	},
	"live:admin": {
		description: "Live OpenStack admin integration slice",
		liveServices: "Redis + OpenStack credentials",
		backend: {
			selectors: ["tests/integration/test_admin.py", "tests/integration/test_admin_writes.py"]
		}
	},
	"live:compute": {
		description: "Live OpenStack compute integration slice",
		liveServices: "Redis + OpenStack credentials",
		backend: {
			selectors: ["tests/integration/test_compute.py", "tests/integration/test_user_writes.py"]
		}
	},
	"live:network": {
		description: "Live OpenStack network integration slice",
		liveServices: "Redis + OpenStack credentials",
		backend: {
			selectors: ["tests/integration/test_network.py"]
		}
	},
	"live:storage": {
		description: "Live OpenStack storage integration slice",
		liveServices: "Redis + OpenStack credentials",
		backend: {
			selectors: ["tests/integration/test_storage.py", "tests/integration/test_file_storage.py"]
		}
	},
	"live:layers": {
		description: "Live OpenStack union layer integration slice",
		liveServices: "Redis + OpenStack credentials",
		backend: {
			selectors: [
				"tests/integration/test_union_e2e.py",
				"tests/integration/test_isolation.py",
				"tests/integration/test_resize_overlay.py",
				"tests/integration/test_concurrent_boot.py"
			],
			extraArgs: ["-m", "slow"]
		}
	}
};

function printUsage(stream) {
	stream.write("Usage: node scripts/test-target.js [--list] [--validate] [--help] [--dry-run|-n] [--parallel|-p] <target|backend:selector|frontend:selector>...\n");
	stream.write("\n");
	stream.write("Examples:\n");
	stream.write("  npm run test:list\n");
	stream.write("  npm run test:target -- auth layers\n");
	stream.write("  npm run test:target -- --parallel instances\n");
	stream.write("  npm run test:target -- backend:tests/test_instances.py::test_delete_instance\n");
	stream.write("  npm run test:target -- frontend:src/lib/config/site.test.ts\n");
	stream.write("  npm run test:auth -- --dry-run\n");
}

function printTargetList() {
	const rows = [["Target", "Description", "Live services"]];
	for (const [name, target] of Object.entries(targets)) {
		rows.push([name, target.description, target.liveServices]);
	}
	const widths = rows[0].map((_, index) => Math.max(...rows.map((row) => row[index].length)));
	for (const row of rows) {
		console.log(
			row
				.map((cell, index) => cell.padEnd(widths[index]))
				.join("  ")
		);
	}
}

function stripSelectorPath(selector) {
	return selector.split("::", 1)[0];
}

function ensureInside(baseDir, selectorPath, label) {
	if (!selectorPath) {
		fail(`Missing selector path for ${label}`);
	}
	const absolutePath = path.resolve(baseDir, selectorPath);
	const relativePath = path.relative(baseDir, absolutePath);
	if (relativePath.startsWith("..") || path.isAbsolute(relativePath)) {
		fail(`Selector must stay within ${path.basename(baseDir)} for ${label}: ${selectorPath}`);
	}
	if (!fs.existsSync(absolutePath)) {
		fail(`Missing test selector path for ${label}: ${selectorPath}`);
	}
}

function resolveBackendDir(targetName, config) {
	if (!config.root) return backendDir;
	ensureInside(rootDir, config.root, `${targetName} backend root`);
	return path.resolve(rootDir, config.root);
}

function validateBackendSelectors(targetName, selectors, baseDir = backendDir) {
	for (const selector of selectors) {
		const selectorPath = stripSelectorPath(selector);
		ensureInside(baseDir, selectorPath, targetName);
		if (baseDir === backendDir && !targetName.startsWith("live:") && selectorPath.startsWith("tests/integration")) {
			fail(`Backend unit target ${targetName} cannot include integration selector: ${selectorPath}`);
		}
	}
}

function validateFrontendSelectors(targetName, selectors) {
	for (const selector of selectors) {
		ensureInside(frontendDir, stripSelectorPath(selector), targetName);
	}
}

function getSelectors(selectorsOrFactory) {
	return typeof selectorsOrFactory === "function" ? selectorsOrFactory() : selectorsOrFactory.slice();
}
function validateTargetDefinition(targetName, target) {
	if (target.backend) {
		const baseDir = resolveBackendDir(targetName, target.backend);
		validateBackendSelectors(targetName, getSelectors(target.backend.selectors), baseDir);
	}
	if (target.frontend) {
		validateFrontendSelectors(targetName, getSelectors(target.frontend.selectors));
	}
}

function validateAllTargetDefinitions() {
	for (const [targetName, target] of Object.entries(targets)) {
		validateTargetDefinition(targetName, target);
	}
}


function buildBackendStep(targetName, config) {
	const selectors = getSelectors(config.selectors);
	const baseDir = resolveBackendDir(targetName, config);
	validateBackendSelectors(targetName, selectors, baseDir);
	return {
		targetName,
		label: `${targetName} [backend]`,
		cwd: baseDir,
		cwdLabel: config.root || "backend",
		command: "uv",
		args: ["run", ...(config.root ? ["--extra", "dev"] : []), "python", "-m", "pytest", ...selectors, "-v", ...(config.extraArgs || [])],
		envAdditions: { AFTERGLOW_ALLOW_INSECURE: "1" },
		requiredEnv: targets[targetName].requiredEnv || []
	};
}

function buildFrontendStep(targetName, config) {
	const selectors = getSelectors(config.selectors);
	validateFrontendSelectors(targetName, selectors);
	return {
		targetName,
		label: `${targetName} [frontend]`,
		cwd: frontendDir,
		cwdLabel: "frontend",
		command: "npm",
		args: ["exec", "--", "vitest", "run", ...selectors],
		envAdditions: {},
		requiredEnv: []
	};
}

function buildNamedTargetSteps(targetName) {
	const target = targets[targetName];
	if (!target) {
		console.error(`Unknown test target: ${targetName}`);
		console.error("Run npm run test:list");
		process.exit(1);
	}
	const steps = [];
	if (target.backend) {
		steps.push(buildBackendStep(targetName, target.backend));
	}
	if (target.frontend) {
		steps.push(buildFrontendStep(targetName, target.frontend));
	}
	return steps;
}

function buildCustomBackendStep(selectors) {
	validateBackendSelectors("custom backend selectors", selectors);
	return {
		targetName: "custom-backend",
		label: "custom [backend]",
		cwd: backendDir,
		cwdLabel: "backend",
		command: "uv",
		args: ["run", "python", "-m", "pytest", ...selectors, "-v"],
		envAdditions: { AFTERGLOW_ALLOW_INSECURE: "1" },
		requiredEnv: []
	};
}

function buildCustomFrontendStep(selectors) {
	validateFrontendSelectors("custom frontend selectors", selectors);
	return {
		targetName: "custom-frontend",
		label: "custom [frontend]",
		cwd: frontendDir,
		cwdLabel: "frontend",
		command: "npm",
		args: ["exec", "--", "vitest", "run", ...selectors],
		envAdditions: {},
		requiredEnv: []
	};
}

function formatArg(arg) {
	if (/^[A-Za-z0-9_./:@=-]+$/.test(arg)) {
		return arg;
	}
	return JSON.stringify(arg);
}

function formatCommand(step) {
	return [step.command, ...step.args].map(formatArg).join(" ");
}

function printStep(step) {
	console.log(`${step.label}`);
	console.log(`  cwd: ${step.cwdLabel}`);
	if (Object.keys(step.envAdditions).length > 0) {
		console.log(
			`  env: ${Object.entries(step.envAdditions)
				.map(([key, value]) => `${key}=${value}`)
				.join(" ")}`
		);
	}
	if (step.requiredEnv.length > 0) {
		console.log(`  required env: ${step.requiredEnv.join(", ")}`);
	}
	console.log(`  cmd: ${formatCommand(step)}`);
}

function runStep(step, dryRun) {
	if (dryRun) {
		printStep(step);
		return 0;
	}
	if (step.targetName === "db" && !process.env.AFTERGLOW_TEST_DATABASE_URL) {
		console.error(dbRequirementMessage);
		return 2;
	}
	printStep(step);
	const result = spawnSync(step.command, step.args, {
		cwd: step.cwd,
		env: { ...process.env, ...step.envAdditions },
		stdio: "inherit",
		shell: process.platform === "win32"
	});
	if (result.error) {
		console.error(result.error.message);
		return 1;
	}
	return result.status === null ? 1 : result.status;
}

function runStepAsync(step, dryRun) {
	if (dryRun) {
		printStep(step);
		return Promise.resolve(0);
	}
	if (step.targetName === "db" && !process.env.AFTERGLOW_TEST_DATABASE_URL) {
		console.error(dbRequirementMessage);
		return Promise.resolve(2);
	}
	printStep(step);
	return new Promise((resolve) => {
		const child = spawn(step.command, step.args, {
			cwd: step.cwd,
			env: { ...process.env, ...step.envAdditions },
			stdio: "inherit",
			shell: process.platform === "win32"
		});
		child.on("error", (error) => {
			console.error(error.message);
			resolve(1);
		});
		child.on("exit", (code) => {
			resolve(code === null ? 1 : code);
		});
	});
}

function getLaneName(step, index) {
	if (step.cwdLabel === "backend" || step.cwdLabel === "frontend") {
		return step.cwdLabel;
	}
	return `other-${index}`;
}

function groupStepsByLane(steps) {
	const lanes = new Map();
	steps.forEach((step, index) => {
		const laneName = getLaneName(step, index);
		if (!lanes.has(laneName)) {
			lanes.set(laneName, []);
		}
		lanes.get(laneName).push(step);
	});
	return Array.from(lanes.values());
}

function runStepsSerial(steps, dryRun, runner = runStep) {
	for (const step of steps) {
		const exitCode = runner(step, dryRun);
		if (exitCode !== 0) {
			return exitCode;
		}
	}
	return 0;
}

async function runLaneSerial(steps, dryRun, runner = runStepAsync) {
	for (const step of steps) {
		const exitCode = await runner(step, dryRun);
		if (exitCode !== 0) {
			return exitCode;
		}
	}
	return 0;
}

async function runStepsParallel(steps, dryRun, runner = runStepAsync) {
	if (dryRun) {
		return runStepsSerial(steps, dryRun);
	}
	const laneExitCodes = await Promise.all(groupStepsByLane(steps).map((lane) => runLaneSerial(lane, false, runner)));
	return laneExitCodes.find((code) => code !== 0) || 0;
}

function fail(message, code = 1) {
	console.error(message);
	process.exit(code);
}

async function main(argv) {
	let dryRun = false;
	let parallel = false;
	let showList = false;
	let showHelp = false;
	let validateCatalog = false;
	const namedTargets = [];
	const customBackendSelectors = [];
	const customFrontendSelectors = [];

	for (const arg of argv) {
		if (arg === "--dry-run" || arg === "-n") {
			dryRun = true;
			continue;
		}
		if (arg === "--parallel" || arg === "-p") {
			parallel = true;
			continue;
		}
		if (arg === "--list") {
			showList = true;
			continue;
		}
		if (arg === "--validate") {
			validateCatalog = true;
			continue;
		}
		if (arg === "--help") {
			showHelp = true;
			continue;
		}
		if (arg.startsWith("backend:")) {
			customBackendSelectors.push(arg.slice("backend:".length));
			continue;
		}
		if (arg.startsWith("frontend:")) {
			customFrontendSelectors.push(arg.slice("frontend:".length));
			continue;
		}
		namedTargets.push(arg);
	}

	if (showHelp) {
		printUsage(process.stdout);
		return 0;
	}
	if (showList) {
		validateAllTargetDefinitions();
		printTargetList();
		return 0;
	}
	if (validateCatalog) {
		validateAllTargetDefinitions();
		if (namedTargets.length === 0 && customBackendSelectors.length === 0 && customFrontendSelectors.length === 0) {
			return 0;
		}
	}
	if (namedTargets.length === 0 && customBackendSelectors.length === 0 && customFrontendSelectors.length === 0) {
		printUsage(process.stderr);
		return 1;
	}

	const steps = [];
	for (const targetName of namedTargets) {
		steps.push(...buildNamedTargetSteps(targetName));
	}
	if (customBackendSelectors.length > 0) {
		steps.push(buildCustomBackendStep(customBackendSelectors));
	}
	if (customFrontendSelectors.length > 0) {
		steps.push(buildCustomFrontendStep(customFrontendSelectors));
	}

	return parallel ? runStepsParallel(steps, dryRun) : runStepsSerial(steps, dryRun);
}

if (require.main === module) {
	main(process.argv.slice(2))
		.then((code) => process.exit(code))
		.catch((error) => {
			console.error(error.message);
			process.exit(1);
		});
}

module.exports = {
	buildBackendStep,
	buildFrontendStep,
	buildNamedTargetSteps,
	buildCustomBackendStep,
	buildCustomFrontendStep,
	groupStepsByLane,
	main,
	runStep,
	runStepAsync,
	runStepsParallel,
	targets,
	runStepsSerial
};

