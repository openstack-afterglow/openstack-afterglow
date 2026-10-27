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

function expandMcpBackendSelectors() {
	return fs
		.readdirSync(path.join(backendDir, "tests"), { withFileTypes: true })
		.filter((entry) => entry.isFile() && /^test_mcp_.*\.py$/.test(entry.name))
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
	for (const adminChatTests of ["src/lib/components/admin/chat/__tests__", "src/routes/admin/chat/__tests__"]) {
		if (fs.existsSync(path.join(frontendDir, adminChatTests))) selectors.push(adminChatTests);
	}
	return selectors;
}

const targets = {
	mcp: {
		description: "Consumer MCP registry, delegated authority, SDK adapters and HTTP transport",
		liveServices: "none",
		backend: {
			selectors: expandMcpBackendSelectors,
			extraArgs: ["-m", "not db and not contract"]
		},
		frontend: {
			selectors: ["src/lib/components/account/__tests__/McpAccessSection.test.ts"]
		}
	},
	auth: {
		description: "Login/logout, token, session, site-config auth surfaces",
		liveServices: "none",
		backend: {
			selectors: [
				"tests/test_auth_endpoints.py",
				"tests/test_auth_domain_boundaries.py",
				"tests/test_auth_rotation_security.py",
				"tests/test_auth_diagnostics.py",
				"tests/test_domain_auth.py",
				"tests/test_canonical_federation.py",
				"tests/test_native_oidc.py",
				"tests/test_organization_provisioning.py",
				"tests/test_account_recovery.py",
				"tests/test_public_signup.py",
				"tests/test_enrollment_policy.py",
				"tests/test_personal_login_defaults.py",
				"tests/test_personal_quota_convergence.py",
				"tests/test_profile.py",
				"tests/test_profile_images.py",
				"tests/test_auth_jwt.py",
				"tests/test_role_visibility.py",
				"tests/test_auth_security.py",
				"tests/test_jwt_session_timeout.py",
				"tests/test_session_device.py",
				"tests/test_session_security.py",
				"tests/test_session_family_revocation.py",
				"tests/test_token_binding.py",
				"tests/test_x_auth_token_removal.py",
				"tests/test_login_guard.py",
				"tests/test_login_native_operation.py",
				"tests/test_auth_login_proof.py",
				"tests/test_domain_scope_operation.py",
				"tests/test_workspace_directory.py",
				"tests/test_project_display.py",
				"tests/test_keystone_endpoint_selection.py",
				"tests/test_native_transport.py",
				"tests/test_keystone_service_connection_regression.py",
				"tests/test_keystone_system_scope.py"
			]
		},
		frontend: {
			selectors: [
				"src/lib/stores/__tests__/auth.test.ts",
				"src/lib/stores/__tests__/auth.security.test.ts",
				"src/lib/stores/__tests__/auth.sync.test.ts",
				"src/lib/stores/__tests__/profileImage.test.ts",
				"src/lib/components/account/__tests__/ProfileImages.test.ts",
				"src/lib/components/account/__tests__/LoginPreferenceSection.test.ts",
				"src/lib/components/admin/__tests__/PersonalQuotaConvergence.test.ts",
				"src/lib/utils/__tests__/freshLoginDestination.test.ts",
				"src/lib/api/__tests__/client.authRedirect.test.ts",
				"src/lib/utils/__tests__/authFlow.test.ts",
				"src/lib/utils/__tests__/authSession.test.ts",
				"src/lib/utils/__tests__/authVerification.test.ts",
				"src/routes/select-domain/DomainSelection.test.ts",
				"src/lib/components/__tests__/ProjectSelector.test.ts",
				"src/lib/components/account/__tests__/PersonalProjectLabelSection.test.ts",
				"src/lib/components/__tests__/CmdPaletteSurface.test.ts",
				"src/lib/components/__tests__/AdminSidebar.test.ts",
				"src/lib/stores/__tests__/servicePermissions.test.ts",
				"src/lib/stores/__tests__/workspaceController.test.ts",
				"src/lib/components/auth/__tests__/DomainOnboarding.test.ts",
				"src/lib/components/auth/__tests__/OnboardingAccountForm.test.ts",
				"src/lib/components/auth/__tests__/AccountRecovery.test.ts",
				"src/lib/components/admin/__tests__/AdminEnrollmentPolicyPanel.test.ts",
				"src/lib/utils/projectDeletionContinuation.test.ts",
				"src/routes/auth/callback/ProviderCallback.test.ts",
				"src/lib/stores/__tests__/projectList.test.ts",
				"src/lib/api/__tests__/client.authRecovery.test.ts",
				"src/lib/components/auth/__tests__/LoginPage.test.ts",
				"src/lib/components/auth/__tests__/LoginBrandHeader.test.ts",
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
				"tests/test_admin_user_deletion.py",
				"tests/test_admin_credentials.py",
				"tests/test_admin_identity_inventory.py",
				"tests/test_admin_identity_domain_scope.py",
				"tests/test_admin_group_identity_home.py",
				"tests/test_admin_domains.py",
				"tests/test_admin_domain_resources.py",
				"tests/test_admin_resource_scope.py",
				"tests/test_admin_resource_details.py",
				"tests/test_admin_images.py",
				"tests/test_admin_filters.py",
				"tests/test_domain_iam.py",
				"tests/test_domain_iam_invitation_projects.py",
				"tests/test_domain_membership.py",
				"tests/test_domain_projects.py",
				"tests/test_personal_domains.py",
				"tests/test_personal_quota_convergence.py",
				"tests/test_personal_member_authority.py",
				"tests/test_organization_provisioning.py",
				"tests/test_admin_enrollment_recovery.py",
				"tests/test_domain_quotas.py",
				"tests/test_domain_quota_native.py",
				"tests/test_domain_quota_monitoring.py",
				"tests/test_default_domain_policy.py",
				"tests/test_admin_hypervisor_removal.py",
				"tests/test_project_self_service.py",
				"tests/test_project_display.py",
				"tests/test_project_authority_lifecycle.py",
				"tests/test_project_membership_roles.py",
				"tests/test_project_deletion.py",
				"tests/test_project_deletion_optional.py",
				"tests/test_project_cleanup.py",
				"tests/test_project_cleanup_optional.py",
				"tests/test_identity_roles.py",
				"tests/test_role_visibility.py",
				"tests/test_rbac_project_roles.py",
				"tests/test_database_owner_check.py",
				"tests/test_file_storage_owner_check.py",
				"tests/test_network_owner_check.py",
				"tests/test_volume_owner_check.py",
				"tests/test_loadbalancer_owner_check.py",
				"tests/test_secrets_admin.py",
				"tests/test_endpoint_inventory.py",
				"tests/test_api_v1_legacy_compat.py"
			]
		},
		frontend: {
			selectors: [
				"src/routes/admin/AdminReadiness.test.ts",
				"src/lib/stores/__tests__/adminCredentialsController.test.ts",
				"src/lib/api/__tests__/adminCredentials.test.ts",
				"src/lib/api/__tests__/domainIam.test.ts",
				"src/lib/api/__tests__/workspaceIam.test.ts",
				"src/lib/api/__tests__/workspaceIamTransport.test.ts",
				"src/lib/components/account/__tests__/ProjectLifecycleSection.test.ts",
				"src/lib/components/account/__tests__/ProjectMemberRolesModal.test.ts",
				"src/lib/components/admin/projects/__tests__/AdminProjectAccessModal.test.ts",
				"src/lib/components/admin/projects/__tests__/AdminProjectDeleteModal.test.ts",
				"src/lib/components/admin/projects/__tests__/ProjectResourceMonitor.test.ts",
				"src/lib/components/account/__tests__/PersonalProjectLabelSection.test.ts",
				"src/lib/stores/__tests__/servicePermissions.test.ts",
				"src/lib/components/iam/__tests__/DomainIam.test.ts",
				"src/lib/components/iam/__tests__/IamProjects.test.ts",
				"src/lib/components/iam/__tests__/ProjectIamConsole.test.ts",
				"src/lib/stores/__tests__/projectManagement.test.ts",
				"src/lib/components/iam/__tests__/IamInvitationProjects.test.ts",
				"src/lib/components/iam/__tests__/Monitoring.test.ts",
				"src/lib/components/iam/__tests__/QuotaEditor.test.ts",
				"src/lib/components/admin/domains/DomainMonitoring.test.ts",
				"src/lib/components/admin/domains/DomainInventory.test.ts",
				"src/lib/components/admin/users/__tests__/UserDomainManagers.test.ts",
				"src/lib/components/admin/groups/__tests__/GroupCard.test.ts",
				"src/lib/components/admin/groups/__tests__/AdminGroupsPage.test.ts",
				"src/lib/components/admin/groups/__tests__/AdminGroupsPage.transport.test.ts",
				"src/lib/components/admin/users/__tests__/AdminUserCreateModal.test.ts",
				"src/lib/components/admin/users/__tests__/AdminUserEditModal.test.ts",
				"src/lib/components/admin/users/__tests__/AdminUserDeleteModal.test.ts",
				"src/lib/components/admin/users/__tests__/AdminUsersPage.delete.test.ts",
				"src/routes/admin/chat/quotas/__tests__/page.test.ts",
				"src/lib/components/admin/roles/__tests__/catalog.test.ts",
				"src/routes/admin/roles/__tests__/page.boundaries.test.ts"
			]
		}
	},
	monitoring: {
		description: "Native OpenStack telemetry, Aodh alarms/Gnocchi administration, fallback metrics, host/peer observations, paths, traffic, and login sessions",
		liveServices: "none (native Redis is exercised separately by the functional profile)",
		backend: {
			selectors: [
				"tests/test_native_telemetry.py",
				"tests/test_instance_metrics.py",
				"tests/test_instance_metrics_summary.py",
				"tests/test_dashboard_metrics.py",
				"tests/test_dashboard_usage_spark.py",
				"tests/test_dashboard_usage_stats.py",
				"tests/test_admin_monitoring.py",
				"tests/test_admin_telemetry.py",
				"tests/test_host_health.py",
				"tests/test_host_health_config.py",
				"tests/test_monitoring_config.py",
				"tests/test_host_observer.py",
				"tests/test_infrastructure_topology.py",
				"tests/test_topology_flows.py",
				"tests/test_flow_collector.py",
				"tests/test_infrastructure_fabric.py",
				"tests/test_traffic_analytics.py",
				"tests/test_login_monitoring.py"
			]
		},
		frontend: {
			selectors: [
				"src/lib/components/instance/__tests__/MetricsPanel.test.ts",
				"src/lib/components/__tests__/InstanceDetailPanel.lifecycle.test.ts",
				"src/routes/dashboard/compute/instances/__tests__/page.lifecycle.test.ts",
				"src/routes/dashboard/compute/instances/__tests__/page.loading.test.ts",
				"src/routes/dashboard/__tests__/dashboard.test.ts",
				"src/routes/dashboard/usage/__tests__/page.test.ts",
				"src/lib/components/admin/monitoring/MonitoringSummaryTab.test.ts",
				"src/lib/components/admin/monitoring/InstanceMetricsTab.test.ts",
				"src/routes/admin/monitoring/page.test.ts",
				"src/lib/components/admin/telemetry",
				"src/lib/api/__tests__/adminTelemetry.test.ts",
				"src/routes/admin/monitoring/aodh/settings/page.test.ts",
				"src/lib/config/nav.test.ts",
				"src/lib/components/__tests__/AdminSidebar.test.ts",
				"src/lib/components/admin/hypervisors/HostHealthPanel.test.ts",
				"src/lib/components/admin/infrastructure-topology/__tests__",
				"src/lib/stores/__tests__/infrastructureTopologyController.test.ts",
				"src/lib/components/admin/traffic/__tests__",
				"src/routes/admin/monitoring/traffic/page.test.ts",
				"src/lib/types/trafficAnalytics.test.ts",
				"src/lib/server/trafficReporter.test.ts",
				"src/hooks.server.test.ts",
				"src/lib/stores/__tests__/loginMonitoringController.test.ts",
				"src/lib/api/__tests__/loginMonitoring.test.ts"
			]
		}
	},
	config: {
		description: "afterglow.conf, setup, Kolla/K8s/Helm generation, cache, frontend runtime config",
		liveServices: "none",
		backend: {
			selectors: [
				"tests/test_afterglow_conf_config.py",
				"tests/test_monitoring_config.py",
				"tests/contracts/test_ingress_root_path_coverage.py",
				"tests/contracts/test_proxy_scheme.py",
				"tests/test_config_insecure_guard.py",
				"tests/test_config_keystone_url.py",
				"tests/test_config_layer_images.py",
				"tests/test_generate_k8s.py",
				"tests/test_config2helm.py",
				"tests/test_generate_helm_application.py",
				"tests/test_generated_debug_config.py",
				"tests/test_generation_config.py",
				"tests/test_kolla_effective_config.py",
				"tests/test_kolla_frontend_config_renderer.py",
				"tests/test_setup_workflow.py",
				"tests/test_setup_entrypoint.py",
				"tests/test_cache_abstraction.py",
				"tests/test_cache_opt_in.py",
				"tests/test_cache_ttl_policy.py"
			]
		},
		frontend: {
			selectors: ["src/lib/config/site.test.ts", "src/lib/server/config.test.ts"]
		}
	},
	"cloud-shell": {
		description: "Cloud Shell config, lifecycle, tickets, isolation, and protocol",
		liveServices: "none",
		backend: {
			selectors: ["tests/test_cloud_shell.py", "tests/test_cloud_shell_live_safety.py"]
		},
		frontend: {
			selectors: [
				"src/lib/stores/cloudShell.svelte.test.ts",
				"src/lib/components/cloud-shell/CloudShellTerminal.test.ts",
				"src/lib/components/__tests__/ProjectSelector.test.ts",
				"src/lib/config/statusColors.test.ts"
			]
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
				"tests/test_admin_instance_details.py",
				"tests/test_instance_volume_protection.py",
				"tests/test_image_gpu_metadata.py",
				"tests/test_glance_properties_native_http.py",
				"tests/test_flavors.py",
				"tests/test_admin_flavor_access.py",
				"tests/test_admin_flavors.py",
				"tests/test_flavor_eligibility.py",
				"tests/test_flavor_capacity.py",
				"tests/test_flavor_capacity_admission.py",
				"tests/test_gpu_quota_resilience.py",
				"tests/test_instance_names.py",
				"tests/test_instance_health.py",
				"tests/test_instance_metrics.py",
				"tests/test_instance_metrics_summary.py",
				"tests/test_instance_password.py",
				"tests/test_instance_operating_system.py",
				"tests/test_windows_instance_password.py",
				"tests/test_admin_instance_password.py",
				"tests/test_instance_password_validation.py",
				"tests/test_windows_image_metadata.py",
				"tests/test_instance_boot_from_volume.py",
				"tests/test_instance_scheduling.py",
				"tests/test_instances_data_mounts.py",
				"tests/test_instance_storage_delete.py",
				"tests/test_data_mount_subnet_cidrs.py",
				"tests/test_instances_no_libraries.py",
				"tests/test_bulk_instance_action.py",
				"tests/test_admin_instances.py",
				"tests/test_admin_instances_health.py",
				"tests/test_admin_instance_recovery.py",
				"tests/test_admin_host_control.py",
				"tests/test_admin_hypervisor_removal.py",
				"tests/test_hypervisor_removal.py",
				"tests/test_admin_resize.py",
				"tests/test_instance_resize.py",
				"tests/test_vm_github_ssh_history.py",
				"tests/test_nova_metadata.py",
				"tests/test_github_ssh_access.py"
			]
		},
		frontend: {
			selectors: [
				"src/lib/components/instance/__tests__",
				"src/lib/components/wizard/__tests__/SelectFlavor.test.ts",
				"src/lib/components/wizard/__tests__/SelectImage.test.ts",
				"src/lib/utils/imageRecommendation.test.ts",
				"src/lib/tutorial/__tests__/engine.test.ts",
				"src/lib/components/wizard/__tests__/WizardStep5Config.test.ts",
				"src/lib/components/wizard/__tests__/WizardStep6Review.test.ts",
				"src/lib/components/wizard/__tests__/WizardFooter.test.ts",
				"src/lib/components/wizard/__tests__/WizardStepper.test.ts",
				"src/lib/stores/__tests__/wizard.test.ts",
				"src/lib/components/wizard/__tests__/VmDeployProgress.test.ts",
				"src/lib/stores/__tests__/vmCreateStoreLoad.test.ts",
				"src/lib/stores/__tests__/vmCreateStoreRealClient.test.ts",
				"src/lib/stores/__tests__/vmCreateStoreProgress.test.ts",
				"src/lib/stores/__tests__/vmCreatePassword.test.ts",
				"src/lib/utils/__tests__/instanceCreate.test.ts",
				"src/lib/components/admin/__tests__/AdminInstanceTable.test.ts",
				"src/routes/admin/hypervisors/__tests__",
				"src/lib/stores/__tests__/instanceDetailController.password.test.ts",
				"src/lib/stores/__tests__/instanceDetailController.actions.test.ts",
				"src/lib/components/__tests__/InstanceDetailPanel.lifecycle.test.ts",
				"src/lib/components/instance/list/__tests__/InstancesTable.test.ts",
				"src/routes/dashboard/compute/instances/__tests__",
				"src/routes/admin/instances/__tests__",
				"src/lib/stores/__tests__/instanceDetailController.resize.test.ts"
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
				"tests/test_auto_backup.py",
				"tests/test_auto_snapshot.py",
				"tests/test_work_dispatcher.py",
				"tests/test_auto_backup_distributed.py",
				"tests/test_auto_backup_native_http.py",
				"tests/test_ceph_rbd.py",
				"tests/test_volume_delete_recovery.py",
				"tests/test_volume_extend.py",
				"tests/test_volume_owner_check.py",
				"tests/test_volume_snapshots.py",
				"tests/test_volume_transfer.py",
				"tests/test_admin_volume_transfer.py",
				"tests/test_admin_volume_transfer_native_http.py",
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
				"tests/test_admin_swift_inventory.py",
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
				"src/lib/components/volume/__tests__/VolumeExtendModal.test.ts",
				"src/lib/components/volume/__tests__/VolumeBackupConsent.test.ts",
				"src/lib/components/volume/__tests__/VolumeTransferModal.test.ts",
				"src/lib/components/__tests__/VolumeDetailPanel.test.ts",
				"src/routes/dashboard/volumes/__tests__/volumeRenameParity.test.ts",
				"src/routes/dashboard/volumes/__tests__/volumeTransferLifecycle.test.ts",
				"src/routes/dashboard/volumes/backups/__tests__",
				"src/routes/admin/object-storage/page.inventory-boundary.test.ts",
				"src/lib/mockup/transport.test.ts",
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
				"tests/test_layer_build_ownership.py",
				"tests/test_layer_consume.py",
				"tests/test_libraries.py",
				"tests/test_library_builder.py",
				"tests/test_build_work.py",
				"tests/test_build_admission_durable.py",
				"tests/test_library_usage.py",
				"tests/test_dockerfile_import.py",
				"tests/test_dockerfile_verify.py",
				"tests/test_recipe_blocks.py",
				"tests/test_reconcile_builds.py",
				"tests/test_ephemeral_build_orchestration.py",
				"tests/test_ephemeral_builder_vm.py",
				"tests/test_ephemeral_mount.py",
				"tests/test_smoke_mount_heat.py",
				"tests/test_smoke_mount_tofu.py",
				"tests/test_config_layer_images.py"
			]
		},
		frontend: {
			selectors: [
				"src/routes/admin/libraries/__tests__/dockerfile-lint.test.ts",
				"src/lib/components/admin/libraries/__tests__/DockerfileLintPanel.test.ts"
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
				"tests/test_notion_worker.py",
				"tests/test_work_dispatcher.py",
				"tests/test_db_auto_backup.py",
				"tests/test_db_auto_backup_native_http.py",
				"tests/test_database_auto_backup.py",
				"tests/test_trove_backup.py"
			]
		}
	},
	waygate: {
		description: "Waygate BFF proxy, agent proxy, and VPN UI integration tests",
		liveServices: "none",
		backend: {
			selectors: ["tests/contracts/test_waygate_proxy.py", "tests/contracts/test_waygate_agent.py"]
		},
		frontend: {
			selectors: ["src/routes/dashboard/network/waygate/__tests__/page.test.ts"]
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
				"src/lib/components/chat/__tests__/ChatApiKeysManager.test.ts",
				"src/lib/components/chat/__tests__/ChatSidebar.test.ts",
				"src/lib/api/__tests__/chatStream.test.ts",
				"src/lib/api/__tests__/chatContracts.test.ts",
				"src/lib/api/__tests__/chatRunReducer.test.ts"
			]
		}
	},
	palimpsest: {
		description: "Palimpsest native catalog, caller environments, packages, proxy and layer management",
		liveServices: "none",
		backend: {
			selectors: [
				"tests/contracts/test_palimpsest_hub_proxy.py",
				"tests/test_palimpsest_api.py",
				"tests/test_palimpsest_kvm.py",
				"tests/test_palimpsest_dockerfile.py",
				"tests/test_palimpsest_digest.py",
				"tests/test_palimpsest_catalog.py",
				"tests/test_palimpsest_catalog_cleanup.py",
				"tests/test_palimpsest_packages.py",
				"tests/test_palimpsest_authorization.py",
				"tests/test_build_work.py",
				"tests/test_layer_build_ownership.py"
			]
		},
		frontend: {
			selectors: [
				"src/lib/api/__tests__/palimpsestCatalog.test.ts",
				"src/lib/api/__tests__/palimpsestAssets.test.ts",
				"src/lib/api/__tests__/palimpsestHub.test.ts",
				"src/lib/stores/palimpsestAssetsController.svelte.test.ts",
				"src/lib/stores/palimpsestHubController.svelte.test.ts",
				"src/lib/stores/palimpsestPackagesController.svelte.test.ts",
				"src/lib/components/admin/libraries/__tests__/PalimpsestCatalogPanel.test.ts",
				"src/lib/components/palimpsest/AssetSearchPanel.svelte.test.ts",
				"src/routes/admin/libraries/__tests__",
				"src/routes/palimpsest/packages/__tests__"
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
				"tests/contracts/test_proxy_scheme.py",
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
	"live:cloud-shell": {
		description: "Live Cloud Shell approve, CLI, home reuse, cleanup, and reset",
		liveServices: "Redis + Keystone + Zun + Cinder + Neutron + published Cloud Shell image",
		backend: {
			selectors: ["tests/integration/test_cloud_shell.py"],
			extraArgs: ["-m", "slow"]
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

