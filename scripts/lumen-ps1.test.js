const assert = require("node:assert/strict");
const test = require("node:test");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn, spawnSync } = require("node:child_process");

function runtimeEnvironment(home, extra = {}) {
	const env = {};
	for (const name of ["PATH", "Path", "SystemRoot", "SYSTEMROOT", "WINDIR", "windir", "COMSPEC", "ComSpec", "PATHEXT", "LANG", "LC_ALL", "LC_CTYPE", "PSModulePath"]) {
		if (process.env[name] !== undefined) env[name] = process.env[name];
	}
	return { ...env, HOME: home, USERPROFILE: home, APPDATA: home, LOCALAPPDATA: home, TEMP: home, TMP: home,
		CODEX_HOME: path.join(home, ".codex"), XDG_DATA_HOME: path.join(home, ".local", "share"),
		POWERSHELL_TELEMETRY_OPTOUT: "1", DOTNET_CLI_TELEMETRY_OPTOUT: "1", ...extra };
}

// PWSH can point to an unpacked official runtime. Pure behavior and parser
// checks run on every host with PowerShell, not just Windows. Only the real
// CurrentUser DPAPI/ACL test is Windows-only; there is no storage mock.
const pwsh = process.env.PWSH || (process.platform === "win32" ? "powershell.exe" : "pwsh");
const available = spawnSync(pwsh, ["-NoLogo", "-NoProfile", "-NonInteractive", "-Command", "$PSVersionTable.PSVersion.ToString()"], { encoding: "utf8", env: runtimeEnvironment(os.tmpdir()) });
if (process.env.PWSH) {
	assert.equal(available.status, 0, `PWSH runtime unavailable: ${available.error || available.stderr}`);
}
const missingRuntime = available.status !== 0 ? "PowerShell unavailable: parser and behavior checks were not executed (set PWSH to a runtime path)" : false;
const installer = path.resolve(__dirname, "../frontend/static/install/lumen.ps1");
const psLiteral = (value) => `'${value.replaceAll("'", "''")}'`;
// Keep generated test scripts ASCII so Windows PowerShell 5.1 reads them unchanged.
const asciiJson = (value) => JSON.stringify(value).replace(/[\u007f-\uffff]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, "0")}`);
const codexPromptSha256 = "ac8ae107a0d72fe3476b430afb161ea4e67da2e446d778aefc44828160559807";
const middleDot = " \u00b7 ";

function run(code, { definitions = true, env = {} } = {}) {
	const dir = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "lumen-ps1-")));
	const script = path.join(dir, "behavior.ps1");
	const bootstrap = `
$ErrorActionPreference = 'Stop'
$sourcePath = ${psLiteral(installer)}
$work = ${psLiteral(dir)}
$tokens = $null; $parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($sourcePath, [ref] $tokens, [ref] $parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
${definitions ? "$ast.FindAll({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] }, $true) | ForEach-Object { . ([scriptblock]::Create($_.Extent.Text)) }" : ""}
${code}
`;
	fs.writeFileSync(script, bootstrap);
	try {
		const result = spawnSync(pwsh, ["-NoLogo", "-NoProfile", "-NonInteractive", "-File", script], { cwd: dir, encoding: "utf8", env: runtimeEnvironment(dir, env), timeout: 120000 });
		assert.equal(result.status, 0, result.error ? String(result.error) : result.stderr + result.stdout);
		return JSON.parse(result.stdout.trim());
	} finally {
		fs.rmSync(dir, { recursive: true, force: true });
	}
}

function behavior(name, fn, options = {}) {
	test(name, { skip: missingRuntime || options.skip || false }, fn);
}

// Server catalog shape (GET /v1/cli/models). Provider 7 rows are split by
// another provider to prove display grouping; "shared-model" exists on two
// provider connections with different protocol support.
const catalogFixture = { models: [
	{ id: "lumen/7/11", api_model_name: "gpt-5.6-sol", display_name: "GPT-5.6 Sol", provider: "openai", provider_name: "OpenAI API", provider_type: "openai",
		protocols: ["messages", "responses"], usable: true, disabled_reason: null,
		capabilities: { context_limit: 400000, input_modalities: ["text", "image"], function_calling: true, reasoning_options: [{ type: "effort", values: ["low", "medium", "high", "xhigh"] }] },
		input_price_per_million: "1.25", output_price_per_million: "10" },
	{ id: "lumen/3/21", api_model_name: "claude-sonnet-5", display_name: "Claude Sonnet 5", provider: "anthropic", provider_name: "Anthropic API", provider_type: "anthropic",
		protocols: ["messages", "responses"], usable: true, disabled_reason: null,
		capabilities: { context_limit: 200000, input_modalities: ["text"], reasoning_options: [{ type: "budget_tokens", min: 1024, max: 64000 }] },
		input_price_per_million: "3", output_price_per_million: "15" },
	{ id: "lumen/7/12", api_model_name: "shared-model", display_name: "Shared \u001b[31mModel\u202e", provider: "openai", provider_name: "OpenAI API", provider_type: "openai",
		protocols: ["responses"], usable: true, disabled_reason: null, capabilities: {}, input_price_per_million: null, output_price_per_million: null },
	{ id: "lumen/4/22", api_model_name: "shared-model", display_name: "Shared Model", provider: "claude-sub", provider_name: "Team's sub $(Get-Date)", provider_type: "anthropic_subscription",
		protocols: ["messages"], usable: true, disabled_reason: null, capabilities: null, input_price_per_million: "0", output_price_per_million: null },
	{ id: "lumen/9/5", api_model_name: "device-model", display_name: "Device Model", provider: "chatgpt", provider_name: "ChatGPT device", provider_type: "chatgpt_device",
		protocols: [], usable: false, disabled_reason: "subscription_protocol_unsupported", capabilities: { context_limit: 128000 }, input_price_per_million: null, output_price_per_million: null },
] };
const fixtureLiteral = psLiteral(asciiJson(catalogFixture));
// Display indices after provider grouping: 1=7/11 2=7/12 3=3/21 4=4/22 5=9/5.
const label = (role, provider, model) => role + middleDot + provider + middleDot + model;

// Scripted terminal answers drive the real selection prompts.
function selectionPrelude(answers) {
	return `
$rows = ConvertFrom-LumenCliCatalog ${fixtureLiteral}
$script:answers = @(${answers.map(psLiteral).join(", ")}); $script:answerIndex = 0; $script:prompts = @()
function Read-Host {
 param([string] $Prompt, [switch] $AsSecureString)
 $script:prompts += $Prompt
 $value = $script:answers[$script:answerIndex]; $script:answerIndex++
 return $value
}
$selection = Read-LumenRoleSelection $rows
`;
}
const defaultAnswers = ["1", "2", "4", "3", "1", "4", "opus"];

behavior("HTTPS bases, public model IDs and catalog route IDs reject unsafe or ambiguous input", () => {
	const result = run(`
$badUrls = @('http://example.com/v1', 'https://user:password@example.com', 'https://example.com?key=x', 'https://example.com#x', 'https://example.com/?', 'https://example.com/#', 'https://example.com/%0a', 'https://example.com/%7F', ' https://example.com', "https://example.com/\\", 'https://example.com\\evil', 'not a URL')
$rejected = foreach ($value in $badUrls) { try { $null = ConvertTo-LumenBaseUrl $value; $false } catch { $true } }
$badModels = @('', '-flag', 'a b', 'a;whoami', 'a"b', ('a' * 201), ('model' + [char]10))
$modelRejected = foreach ($value in $badModels) { try { $null = ConvertTo-LumenModel $value; $false } catch { $true } }
$badRoutes = @('gpt-5', 'lumen/0/1', 'lumen/1/0', 'lumen/01/2', 'lumen/1/2/3', ('lumen/1/2' + [char]10), 'Lumen/1/2', ' lumen/1/2', ('lumen/1/' + ('9' * 19)), 'lumen/-1/2')
$routeRejected = foreach ($value in $badRoutes) { try { $null = ConvertTo-LumenRouteId $value; $false } catch { $true } }
@{ rejected = @($rejected); modelRejected = @($modelRejected); routeRejected = @($routeRejected); url = (ConvertTo-LumenBaseUrl 'https://EXAMPLE.com:443/v1/'); model = (ConvertTo-LumenModel 'public/model:1.2'); route = (ConvertTo-LumenRouteId 'lumen/12/34') } | ConvertTo-Json -Compress
`);
	assert.ok(result.rejected.every(Boolean));
	assert.ok(result.modelRejected.every(Boolean));
	assert.equal(result.routeRejected.length, 10);
	assert.ok(result.routeRejected.every(Boolean));
	assert.equal(result.url, "https://example.com/v1");
	assert.equal(result.model, "public/model:1.2");
	assert.equal(result.route, "lumen/12/34");
});

behavior("catalog groups providers, keeps identical public IDs distinct and neutralizes terminal control text", () => {
	const result = run(`
$rows = ConvertFrom-LumenCliCatalog ${fixtureLiteral}
@{ rows = @($rows | ForEach-Object { @{ index = $_.Index; id = $_.Id; display = $_.DisplayName; provider = $_.ProviderName; api = $_.ApiModelName; publicId = $_.PublicModelId; responses = $_.Responses; messages = $_.Messages; usable = $_.Usable; reason = $_.DisabledReason; context = $_.ContextLimit; image = $_.Image; efforts = @($_.ReasoningEfforts) } }) } | ConvertTo-Json -Compress -Depth 5
`);
	assert.deepEqual(result.rows.map((row) => [row.index, row.id]), [[1, "lumen/7/11"], [2, "lumen/7/12"], [3, "lumen/3/21"], [4, "lumen/4/22"], [5, "lumen/9/5"]]);
	const [sol, sharedResponses, sonnet, sharedMessages, device] = result.rows;
	assert.equal(sharedResponses.api, "shared-model");
	assert.equal(sharedMessages.api, "shared-model");
	assert.deepEqual([sharedResponses.responses, sharedResponses.messages], [true, false]);
	assert.deepEqual([sharedMessages.responses, sharedMessages.messages], [false, true]);
	assert.doesNotMatch(sharedResponses.display, /[\u0000-\u001f\u007f\u202e]/);
	assert.match(sharedResponses.display, /^Shared .*Model$/);
	assert.deepEqual([device.usable, device.responses, device.messages, device.reason], [false, false, false, "subscription_protocol_unsupported"]);
	assert.equal(sol.context, 400000);
	assert.equal(sol.image, true);
	assert.deepEqual(sol.efforts, ["low", "medium", "high", "xhigh"]);
	assert.equal(sol.publicId, "gpt-5.6-sol");
	assert.equal(sonnet.image, false);
	assert.equal(sharedResponses.context, null);
	assert.equal(sharedMessages.provider, "Team's sub $(Get-Date)");
});

behavior("incomplete, malformed or unusable catalogs are refused before any choice", () => {
	const row = catalogFixture.models[0];
	const without = (name) => Object.fromEntries(Object.entries(row).filter(([key]) => key !== name));
	const documents = [
		"not json", "[]", "{}", asciiJson({ models: {} }), asciiJson({ models: [without("usable")] }), asciiJson({ models: [without("protocols")] }),
		asciiJson({ models: [{ ...row, id: "gpt-5" }] }), asciiJson({ models: [row, { ...row }] }), asciiJson({ models: [{ ...row, input_price_per_million: 1.5 }] }),
		asciiJson({ models: [{ ...row, output_price_per_million: "1e3" }] }), asciiJson({ models: [{ ...row, protocols: "responses" }] }),
		asciiJson({ models: [{ ...row, usable: "true" }] }), asciiJson({ models: [{ ...row, capabilities: [] }] }), asciiJson({ models: [{ ...row, display_name: 7 }] }),
	];
	const unusable = [
		asciiJson({ models: [] }),
		asciiJson({ models: [{ ...row, protocols: ["messages"] }] }),
		asciiJson({ models: [{ ...row, protocols: ["responses"] }] }),
		asciiJson({ models: [{ ...row, usable: false, protocols: [], disabled_reason: "pricing_unavailable" }] }),
	];
	const result = run(`
$invalid = foreach ($document in @(${documents.map(psLiteral).join(", ")})) { try { $null = ConvertFrom-LumenCliCatalog $document; '' } catch { $_.Exception.Message } }
$unusable = foreach ($document in @(${unusable.map(psLiteral).join(", ")})) { try { $null = ConvertFrom-LumenCliCatalog $document; '' } catch { $_.Exception.Message } }
@{ invalid = @($invalid); unusable = @($unusable) } | ConvertTo-Json -Compress
`);
	assert.equal(result.invalid.length, documents.length);
	for (const message of result.invalid) assert.match(message, /catalog response is invalid; no files were changed/);
	assert.match(result.unusable[0], /no usable Codex \(Responses\) model/);
	assert.match(result.unusable[1], /no usable Codex \(Responses\) model/);
	assert.match(result.unusable[2], /no usable Claude Code \(Messages\) model/);
	assert.match(result.unusable[3], /no usable Codex \(Responses\) model/);
});

behavior("catalog listing shows provider groups with known context, price and protocol status only", () => {
	const result = run(`
@{ lines = @(Format-LumenCliCatalog (ConvertFrom-LumenCliCatalog ${fixtureLiteral})) } | ConvertTo-Json -Compress
`);
	const text = result.lines.join("\n");
	const headers = result.lines.filter((line) => line && !line.startsWith("  "));
	assert.deepEqual(headers, ["OpenAI API (openai, openai)", "Anthropic API (anthropic, anthropic)", "Team's sub $(Get-Date) (claude-sub, anthropic_subscription)", "ChatGPT device (chatgpt, chatgpt_device)"]);
	assert.match(text, /\[1\] GPT-5\.6 Sol \[gpt-5\.6-sol\] - context 400,000 tokens; price per 1M tokens: input 1\.25, output 10; Codex\/Responses: yes, Claude\/Messages: yes/);
	assert.match(text, /\[2\] Shared .*Model \[shared-model\] - context unknown; price unknown; Codex\/Responses: yes, Claude\/Messages: no/);
	assert.match(text, /\[4\] Shared Model \[shared-model\] - context unknown; price per 1M tokens: input 0, output unknown; Codex\/Responses: no, Claude\/Messages: yes/);
	assert.match(text, /\[5\] Device Model \[device-model\] - context 128,000 tokens; price unknown; unavailable: subscription_protocol_unsupported/);
	assert.doesNotMatch(text, /[\u0000-\u0009\u000b-\u001f\u202e]/);
});

behavior("role prompts follow Sol, Luna, Fable, Opus, Sonnet, Haiku, startup and refuse incompatible choices", () => {
	const result = run(`
${selectionPrelude(defaultAnswers)}
$picked = [ordered] @{}; foreach ($role in $selection.Roles.Keys) { $picked[$role] = $selection.Roles[$role].Id }
$slots = @(Get-LumenRoleSlots)
$sol = $slots[0]; $fable = $slots[2]
$refusals = @(
 (& { try { $null = Select-LumenCatalogRow $rows '4' $sol; '' } catch { $_.Exception.Message } }),
 (& { try { $null = Select-LumenCatalogRow $rows '2' $fable; '' } catch { $_.Exception.Message } }),
 (& { try { $null = Select-LumenCatalogRow $rows '5' $fable; '' } catch { $_.Exception.Message } })
)
$unlisted = foreach ($value in @('0', '6', 'abc', '1.0', ' ', '', '+1', '1 2')) { try { $null = Select-LumenCatalogRow $rows $value $sol; $false } catch { $_.Exception.Message -like 'Choose a listed model number for Codex Sol*' } }
$startup = @('', 'HAIKU', ' Fable ') | ForEach-Object { ConvertTo-LumenStartupRole $_ }
$badStartup = try { ConvertTo-LumenStartupRole 'gpt'; $false } catch { $true }
# At script scope $prompts would alias $script:prompts; keep a copy of the first run.
$firstPrompts = @($script:prompts)
$script:answers = @('1', '4', '1'); $script:answerIndex = 0; $script:prompts = @()
$stopped = try { $null = Read-LumenRoleSelection $rows; '' } catch { $_.Exception.Message }
@{ picked = $picked; startupRole = $selection.StartupRole; prompts = $firstPrompts; refusals = $refusals; unlisted = @($unlisted); startup = @($startup); badStartup = $badStartup; stopped = $stopped; stoppedPrompts = @($script:prompts) } | ConvertTo-Json -Compress -Depth 4
`);
	assert.deepEqual(result.picked, { Sol: "lumen/7/11", Luna: "lumen/7/12", Fable: "lumen/4/22", Opus: "lumen/3/21", Sonnet: "lumen/7/11", Haiku: "lumen/4/22" });
	assert.equal(result.startupRole, "opus");
	assert.deepEqual(result.prompts.map((prompt) => prompt.split(" ").slice(0, 2).join(" ")),
		["Codex Sol", "Codex Luna", "Claude Fable", "Claude Opus", "Claude Sonnet", "Claude Haiku", "Claude Code"]);
	assert.match(result.prompts[6], /startup role.*\[sonnet\]/);
	assert.match(result.refusals[0], /^Model 4 does not support the Responses API that Codex Sol requires; no files were changed\.$/);
	assert.match(result.refusals[1], /^Model 2 does not support the Messages API that Claude Fable requires/);
	assert.match(result.refusals[2], /^Model 5 is unavailable \(subscription_protocol_unsupported\) and cannot be Claude Fable/);
	assert.ok(result.unlisted.every(Boolean));
	assert.deepEqual(result.startup, ["sonnet", "haiku", "fable"]);
	assert.equal(result.badStartup, true);
	assert.match(result.stopped, /Model 4 does not support the Responses API that Codex Luna requires/);
	assert.equal(result.stoppedPrompts.length, 2, "selection stops at the first incompatible choice");
});

behavior("declared custom effort metadata and exact decimals survive while the native catalog projects named efforts only", () => {
	const fixture = structuredClone(catalogFixture);
	fixture.models[0].capabilities.reasoning_options = [{ type: "effort", values: ["vendor/Expert", "medium", "max", "HIGH"] }];
	fixture.models[0].input_price_per_million = "0.0000000000000000007";
	const result = run(`
$rows = ConvertFrom-LumenCliCatalog ${psLiteral(asciiJson(fixture))}
$selection = [pscustomobject] @{ Roles = [ordered] @{ Sol = $rows[0]; Luna = $rows[0] }; StartupRole = 'sonnet' }
$efforts = @($rows[0].ReasoningEfforts)
$catalog = New-LumenCodexCatalog $selection (Get-LumenCodexBaseInstructions)
$rows[0].ReasoningEfforts = @('vendor/Expert')
@{ efforts = $efforts; price = $rows[0].InputPrice; catalog = $catalog; customOnly = (New-LumenCodexCatalog $selection (Get-LumenCodexBaseInstructions)) } | ConvertTo-Json -Compress
`);
	assert.deepEqual(result.efforts, ["vendor/Expert", "medium", "max", "HIGH"]);
	assert.equal(result.price, "0.0000000000000000007");
	const model = JSON.parse(result.catalog).models[0];
	assert.deepEqual(model.supported_reasoning_levels.map((entry) => entry.effort), ["medium", "max"]);
	assert.equal(model.default_reasoning_level, "medium");
	const customOnly = JSON.parse(result.customOnly).models[0];
	assert.deepEqual(customOnly.supported_reasoning_levels, []);
	assert.equal(Object.hasOwn(customOnly, "default_reasoning_level"), false);
});

behavior("native Codex catalog lists both selected roles with pinned instructions and only known metadata", () => {
	const result = run(`
${selectionPrelude(defaultAnswers)}
$instructions = Get-LumenCodexBaseInstructions
$distinct = New-LumenCodexCatalog $selection $instructions
$same = [pscustomobject] @{ Roles = [ordered] @{ Sol = $rows[0]; Luna = $rows[0] }; StartupRole = 'sonnet' }
$deduplicated = New-LumenCodexCatalog $same $instructions
$missing = try { $null = New-LumenCodexCatalog $selection ''; $false } catch { $true }
@{ distinct = $distinct; deduplicated = $deduplicated; missing = $missing } | ConvertTo-Json -Compress
`);
	const distinct = JSON.parse(result.distinct).models;
	const deduplicated = JSON.parse(result.deduplicated).models;
	assert.equal(result.missing, true);
	assert.deepEqual(distinct.map((model) => model.slug), ["lumen/7/11", "lumen/7/12"]);
	assert.equal(distinct[0].display_name, label("Sol", "OpenAI API", "GPT-5.6 Sol"));
	assert.match(distinct[1].display_name, /^Luna \u00b7 OpenAI API \u00b7 Shared .*Model$/);
	// Required ModelInfo fields of openai/codex rust-v0.160.0 plus the legacy
	// base_instructions field its catalog deserializer requires.
	for (const model of distinct) {
		for (const field of ["slug", "display_name", "description", "supported_reasoning_levels", "shell_type", "visibility", "supported_in_api", "priority",
			"availability_nux", "upgrade", "support_verbosity", "default_verbosity", "apply_patch_tool_type", "truncation_policy", "experimental_supported_tools", "base_instructions"]) {
			assert.ok(Object.hasOwn(model, field), `${model.slug} lacks ${field}`);
		}
		assert.equal(crypto.createHash("sha256").update(model.base_instructions, "utf8").digest("hex"), codexPromptSha256);
		assert.equal(model.shell_type, "unified_exec");
		assert.equal(model.visibility, "list");
		assert.equal(model.supports_reasoning_summary_parameter, false);
		assert.deepEqual(model.truncation_policy, { mode: "bytes", limit: 10000 });
		assert.deepEqual(model.experimental_supported_tools, []);
		assert.equal(model.model_messages, undefined, "native Codex instructions are not replaced by a model-family template");
	}
	assert.deepEqual(distinct.map((model) => model.priority), [0, 1]);
	assert.equal(distinct[0].context_window, 400000);
	assert.equal(distinct[0].max_context_window, 400000);
	assert.equal(distinct[1].context_window, null, "unknown context stays unknown");
	assert.equal(Object.hasOwn(distinct[1], "max_context_window"), false);
	assert.deepEqual(distinct[0].input_modalities, ["text", "image"]);
	assert.deepEqual(distinct[1].input_modalities, ["text"]);
	assert.deepEqual(distinct[0].supported_reasoning_levels.map((level) => level.effort), ["low", "medium", "high", "xhigh"]);
	assert.equal(distinct[0].default_reasoning_level, "medium");
	assert.deepEqual(distinct[1].supported_reasoning_levels, []);
	assert.equal(Object.hasOwn(distinct[1], "default_reasoning_level"), false);
	assert.equal(deduplicated.length, 1);
	assert.equal(deduplicated[0].slug, "lumen/7/11");
	assert.equal(deduplicated[0].display_name, label("Sol + Luna", "OpenAI API", "GPT-5.6 Sol"));
});

behavior("embedded Codex instructions are the exact pinned bytes and the installer stays ASCII", () => {
	const source = fs.readFileSync(installer);
	assert.ok(source.every((byte) => byte < 128), "irm|iex decoding must not be able to alter the installer");
	const result = run(`
@{ instructions = (Get-LumenCodexBaseInstructions) } | ConvertTo-Json -Compress
`);
	const bytes = Buffer.from(result.instructions, "utf8");
	assert.equal(bytes.length, 20903);
	assert.equal(crypto.createHash("sha256").update(bytes).digest("hex"), codexPromptSha256);
	assert.ok(result.instructions.startsWith("You are a coding agent running in the Codex CLI"));
	assert.ok(result.instructions.endsWith("\n"));
});

behavior("rerun preserves Codex defaults, unrelated tables and multiline values", () => {
	const result = run(`
$original = @'
# user's defaults
model = "keep-default"
model_provider = "openai"
notes = """
[model_providers.lumen]
model = "not a real assignment"
"""
args = [
  "[model_providers.lumen]", # table-looking content
  { a = "quoted # and =" }
]
[projects.'C:\\Users\\Owner']
trust_level = "trusted"
[model_providers.other]
base_url = "https://other.example/v1"
[model_providers."lumen"]
name = "Old Lumen"
base_url = "https://old.example/v1"
wire_api = "chat"
env_key = "OLD_KEY"
custom_setting = { nested = true }
[model_providers.lumen.http_headers]
X-Custom = "preserved"
[profiles.work]
model = "work-default"
'@
$changed = Update-LumenToml $original 'https://lumen.example/v1'
$again = Update-LumenToml $changed 'https://lumen.example/v1'
@{ original = $original; changed = $changed; again = $again } | ConvertTo-Json -Compress
`);
	assert.equal(result.again, result.changed);
	assert.ok(result.changed.startsWith(result.original.slice(0, result.original.indexOf('[model_providers."lumen"]'))));
	assert.ok(result.changed.endsWith(result.original.slice(result.original.indexOf("[model_providers.lumen.http_headers]"))));
	assert.ok(result.changed.includes('custom_setting = { nested = true }'));
	assert.ok(result.changed.includes('base_url = "https://lumen.example/v1"'));
	assert.ok(result.changed.includes('wire_api = "responses"'));
	assert.ok(result.changed.includes('env_key = "LUMEN_API_KEY"'));
});

behavior("native role profile files select route, provider and catalog without changing nested profiles", () => {
	const result = run(`
$catalog = Join-Path $work 'codex home\\lumen-models.json'
$original = "model = 'old'\nmodel_provider = 'openai'\nmodel_catalog_json = '/old/catalog.json'\n[profiles.work]\nmodel = 'work'"
$changed = Update-LumenToml $original 'https://lumen.example/v1' 'lumen/7/11' $true $catalog
$empty = Update-LumenToml '' 'https://lumen.example/v1' 'lumen/7/12' $true $catalog
$only = Update-LumenToml '# comment without newline' 'https://lumen.example/v1' 'lumen/7/11' $true $catalog
$refused = @(
 (& { try { $null = Update-LumenToml '' 'https://lumen.example/v1' 'gpt-5.6-sol' $true $catalog; $false } catch { $true } }),
 (& { try { $null = Update-LumenToml '' 'https://lumen.example/v1' 'lumen/7/11' $true ''; $false } catch { $true } }),
 (& { try { $null = Update-LumenToml '' 'https://lumen.example/v1' 'lumen/7/11' $true 'relative.json'; $false } catch { $true } })
)
@{ changed = $changed; empty = $empty; only = $only; catalog = (ConvertTo-LumenTomlString $catalog); refused = $refused; again = (Update-LumenToml $changed 'https://lumen.example/v1' 'lumen/7/11' $true $catalog) } | ConvertTo-Json -Compress
`);
	for (const [value, route] of [[result.changed, "lumen/7/11"], [result.empty, "lumen/7/12"], [result.only, "lumen/7/11"]]) {
		const root = value.slice(0, value.indexOf("["));
		assert.ok(root.includes(`model = "${route}"`));
		assert.ok(root.includes('model_provider = "lumen-cli"'));
		assert.ok(root.includes(`model_catalog_json = ${result.catalog}`));
		assert.ok(value.includes("[model_providers.lumen-cli]"));
	}
	assert.ok(!result.changed.includes("/old/catalog.json"));
	assert.ok(result.changed.includes("[profiles.work]\nmodel = 'work'"));
	assert.equal(result.again, result.changed);
	assert.deepEqual(result.refused, [true, true, true]);
});

behavior("desktop model changes only on opt-in to a public ID; provider and catalog are never changed or inserted", () => {
	const result = run(`
$original = "model = 'old'\nmodel_provider = 'openai'\n[profiles.work]\nmodel = 'work'"
$unchangedDefaults = Update-LumenToml $original 'https://lumen.example/v1'
$changed = Update-LumenToml $original 'https://lumen.example/v1' 'gpt-5.6-sol'
$empty = Update-LumenToml '' 'https://lumen.example/v1' 'gpt-5.6-sol'
@{ unchangedDefaults = $unchangedDefaults; original = $original; changed = $changed; empty = $empty; again = (Update-LumenToml $changed 'https://lumen.example/v1' 'gpt-5.6-sol') } | ConvertTo-Json -Compress
`);
	assert.ok(result.unchangedDefaults.startsWith(result.original));
	assert.ok(result.changed.startsWith("model = \"gpt-5.6-sol\"\nmodel_provider = 'openai'"));
	assert.ok(!result.empty.includes("model_provider ="));
	for (const value of [result.unchangedDefaults, result.changed, result.empty]) assert.ok(!value.includes("model_catalog_json"));
	assert.ok(result.changed.includes("[profiles.work]\nmodel = 'work'"));
	assert.equal(result.again, result.changed);
});

behavior("CLI provider isolation preserves legacy desktop selectors and clears only managed selector headers", () => {
	const result = run(`
$catalog = Join-Path $work 'lumen-models.json'
$legacy = "[model_providers.lumen]\nbase_url = 'https://old.example/v1'\n[model_providers.lumen.http_headers]\nX-Lumen-Provider = 'openai'\nX-Team = 'keep'\n"
$managed = "[model_providers.lumen-cli]\nbase_url = 'https://old.example/v1'\n[model_providers.lumen-cli.http_headers]\nX-Lumen-Provider = 'openai' # old pin\n""x-lumen-provider"" = 'second'\nX-Team = 'keep'\n[model_providers.lumen-cli.env_http_headers]\nX-Lumen-Provider = 'PROVIDER_NAME'\nX-Trace = 'TRACE_ID'\n"
$dotted = "[model_providers.lumen-cli]\nhttp_headers.X-Lumen-Provider = 'openai'\nhttp_headers.X-Team = 'keep'\nenv_http_headers.X-Lumen-Provider = 'PROVIDER_NAME'\n"
$inline = "[model_providers.lumen-cli]\nhttp_headers = { X-Lumen-Provider = 'openai', X-Team = 'keep' }\n"
$profile = Update-LumenToml ($legacy + $managed) 'https://lumen.example/v1' 'lumen/7/11' $true $catalog
$profileDotted = Update-LumenToml $dotted 'https://lumen.example/v1' 'lumen/7/11' $true $catalog
$inlineRefused = try { $null = Update-LumenToml $inline 'https://lumen.example/v1' 'lumen/7/11' $true $catalog; '' } catch { $_.Exception.Message }
$legacyInline = "[model_providers.lumen]\nhttp_headers = { 'X-Lumen-Provider' = 'openai' }\n"
$legacyEnv = "[model_providers.lumen.env_http_headers]\n'X-Lumen-Provider' = 'PROVIDER_NAME'\n"
@{ legacy = $legacy; profile = $profile; profileDotted = $profileDotted; inlineRefused = $inlineRefused; legacyInline = $legacyInline; isolatedInline = (Update-LumenToml $legacyInline 'https://lumen.example/v1' 'lumen/7/11' $true $catalog); legacyEnv = $legacyEnv; isolatedEnv = (Update-LumenToml $legacyEnv 'https://lumen.example/v1' 'lumen/7/11' $true $catalog); desktop = (Update-LumenToml $legacy 'https://lumen.example/v1'); again = (Update-LumenToml $profile 'https://lumen.example/v1' 'lumen/7/11' $true $catalog) } | ConvertTo-Json -Compress
`);
	assert.ok(result.profile.includes(result.legacy), "legacy provider table is preserved byte-for-byte in CLI profiles");
	for (const value of [result.profile.slice(result.profile.indexOf("[model_providers.lumen-cli]")), result.profileDotted]) {
		assert.doesNotMatch(value, /lumen-provider/i);
		assert.match(value, /X-Team = 'keep'/);
	}
	assert.match(result.profile, /X-Trace = 'TRACE_ID'/);
	assert.ok(result.isolatedInline.includes(result.legacyInline));
	assert.ok(result.isolatedEnv.includes(result.legacyEnv));
	assert.match(result.desktop, /X-Lumen-Provider = 'openai'/);
	assert.match(result.inlineRefused, /inline Lumen CLI header table sets X-Lumen-Provider/);
	assert.equal(result.again, result.profile);
});

behavior("Claude selector preflight refuses case-insensitive header names but preserves unrelated headers", () => {
	const result = run(`
$bad = @('X-Lumen-Provider: openai', "X-Team: keep\n x-lumen-provider : anthropic", "X-Team: keep\r\nX-LUMEN-PROVIDER: openai", "X-Team: keep\rX-Lumen-Provider: openai")
$refused = foreach ($headers in $bad) { try { Assert-LumenClaudeSelectors $headers; '' } catch { $_.Exception.Message } }
$good = @('', 'X-Team: keep', 'X-Team: X-Lumen-Provider', 'X-Lumen-Provider-Other: keep')
$accepted = foreach ($headers in $good) { Assert-LumenClaudeSelectors $headers; $true }
# Claude user settings env overrides the shell, so it is checked as well.
$env:CLAUDE_CONFIG_DIR = Join-Path $work 'claude'
[void] [IO.Directory]::CreateDirectory($env:CLAUDE_CONFIG_DIR)
$settings = Join-Path $env:CLAUDE_CONFIG_DIR 'settings.json'
$missing = Get-LumenClaudeSettingsHeaders
[IO.File]::WriteAllText($settings, '{"env":{"ANTHROPIC_CUSTOM_HEADERS":"X-Team: keep\\nX-Lumen-Provider: openai"}}')
$settingsRefused = try { Assert-LumenClaudeSelectors @('', (Get-LumenClaudeSettingsHeaders)); '' } catch { $_.Exception.Message }
[IO.File]::WriteAllText($settings, '{ not json')
$malformed = Get-LumenClaudeSettingsHeaders
@{ refused = @($refused); accepted = @($accepted); missing = $missing; settingsRefused = $settingsRefused; malformed = $malformed } | ConvertTo-Json -Compress
`);
	assert.equal(result.refused.length, 4);
	for (const message of [...result.refused, result.settingsRefused]) assert.match(message, /^ANTHROPIC_CUSTOM_HEADERS sets X-Lumen-Provider.*No files were changed/);
	assert.deepEqual(result.accepted, [true, true, true, true]);
	assert.equal(result.missing, "");
	assert.equal(result.malformed, "");
});

behavior("managed profile updates preserve unrelated fields and exact backups on idempotent reruns", () => {
	const result = run(`
$original = @'
# native profile root selections
model = "old-model"
model_provider = "old-provider"
approval_policy = "on-request"
custom_setting = { nested = true }
[profiles.work]
model = "work-default"
[profiles."lumen-cli"]
model = "old-model"
model_provider = "old-provider"
approval_policy = "on-request"
custom_setting = { nested = true }
[profiles.lumen-cli.custom]
note = "keep profile child"
[model_providers.'lumen']
base_url = "https://old.example/v1"
custom_setting = { nested = true }
[model_providers.lumen.http_headers]
X-Custom = "keep provider child"
'@
$original = $original.Replace("\n", "\r\n")
$p = Join-Path $work 'lumen-cli.config.toml'
$catalog = Join-Path $work 'lumen-models.json'
$rootPath = Join-Path $work 'config.toml'
[IO.File]::WriteAllText($rootPath, "model = 'desktop'\nmodel_provider = 'openai'", (New-Object Text.UTF8Encoding($true)))
[IO.File]::WriteAllText($p, $original, (New-Object Text.UTF8Encoding($true)))
$rootBytes = [Convert]::ToBase64String([IO.File]::ReadAllBytes($rootPath))
$before = [Convert]::ToBase64String([IO.File]::ReadAllBytes($p))
$changed = Update-LumenToml (Read-LumenTextFile $p) 'https://lumen.example/v1' 'lumen/7/11' $true $catalog
Write-LumenFile $p $changed
$again = Update-LumenToml (Read-LumenTextFile $p) 'https://lumen.example/v1' 'lumen/7/11' $true $catalog
Write-LumenFile $p $again
$backups = @(Get-ChildItem -LiteralPath $work -Filter '*.bak')
@{ original = $original; changed = $changed; again = $again; count = $backups.Count; before = $before; backup = [Convert]::ToBase64String([IO.File]::ReadAllBytes($backups[0].FullName)); rootUnchanged = ($rootBytes -ceq [Convert]::ToBase64String([IO.File]::ReadAllBytes($rootPath))) } | ConvertTo-Json -Compress
`);
	assert.equal(result.again, result.changed);
	assert.equal(result.count, 1);
	assert.equal(result.backup, result.before);
	assert.equal(result.rootUnchanged, true);
	assert.ok(result.changed.includes('model = "lumen/7/11"\r\nmodel_provider = "lumen-cli"'));
	assert.ok(result.changed.slice(0, result.changed.indexOf("[profiles.work]")).includes("model_catalog_json = "));
	assert.ok(result.changed.includes(result.original.slice(result.original.indexOf("[profiles.work]"), result.original.indexOf("[model_providers.'lumen']"))));
	for (const field of ['approval_policy = "on-request"', 'custom_setting = { nested = true }', '[profiles.lumen-cli.custom]\r\nnote = "keep profile child"', '[model_providers.lumen.http_headers]\r\nX-Custom = "keep provider child"']) {
		assert.ok(result.changed.includes(field));
	}
});

behavior("quoted dots and case-sensitive TOML keys are not mistaken for the managed provider", () => {
	const result = run(`
$original = @'
MODEL = "unrelated"
["model_providers.lumen"]
base_url = "https://unrelated.example"
[model_providers.Lumen]
base_url = "https://different.example"
[model_providers.lumen]
BASE_URL = "unrelated-case"
'@
$changed = Update-LumenToml $original 'https://lumen.example/v1'
@{ original = $original; changed = $changed; again = (Update-LumenToml $changed 'https://lumen.example/v1') } | ConvertTo-Json -Compress
`);
	assert.ok(result.changed.startsWith(result.original));
	assert.ok(result.changed.includes('base_url = "https://lumen.example/v1"'));
	assert.equal(result.again, result.changed);
});

behavior("ambiguous TOML conflicts and unterminated collections fail without a rewrite", () => {
	const result = run(`
$bad = @(
 'model_providers = { "lumen-cli" = { name = "x" } }',
 'model_providers.lumen-cli.name = "x"',
 "[model_providers]\nlumen-cli = { name = 'x' }",
 "[model_providers.lumen-cli]\nbase_url = 'a'\nbase_url = 'b'",
 "[model_providers.lumen-cli]\n[model_providers.'lumen-cli']",
 "[[model_providers.lumen-cli]]\nname = 'x'",
 "[[model_providers]]\nname = 'x'",
 "[model_providers.lumen-cli.base_url]\nx = 'y'",
 "model = 'a'\nmodel = 'b'",
 "model_provider = 'a'\n'model_provider' = 'b'",
 "model_catalog_json = 'a'\nmodel_catalog_json = 'b'",
 'model.name = "x"',
 'model_provider.name = "x"',
 'model_catalog_json.path = "x"',
 "[model]\nname = 'x'",
 "[[model_provider]]\nname = 'x'",
 "[model_catalog_json]\npath = 'x'",
 "[model_providers.lumen-cli]\nhttp_headers = { 'X-Lumen-Provider' = 'x' }",
 'value = [1, 2',
 'value = "unterminated'
)
$p = Join-Path $work 'lumen-cli.config.toml'
$catalog = Join-Path $work 'lumen-models.json'
$rejected = foreach ($value in $bad) {
 [IO.File]::WriteAllText($p, $value, (New-Object Text.UTF8Encoding($false)))
 $before = [Convert]::ToBase64String([IO.File]::ReadAllBytes($p))
 $failed = $false
 try { Write-LumenFile $p (Update-LumenToml (Read-LumenTextFile $p) 'https://lumen.example/v1' 'lumen/7/11' $true $catalog) } catch { $failed = $true }
 $failed -and $before -ceq [Convert]::ToBase64String([IO.File]::ReadAllBytes($p))
}
@{ rejected = @($rejected); backups = @(Get-ChildItem -LiteralPath $work -Filter '*.bak').Count } | ConvertTo-Json -Compress
`);
	assert.equal(result.rejected.length, 20);
	assert.ok(result.rejected.every(Boolean));
	assert.equal(result.backups, 0);
});

behavior("profile marker replacement is idempotent and escaping cannot execute injected path or catalog text", () => {
	const result = run(`
${selectionPrelude(defaultAnswers)}
$hostile = "C:\\Users\\O'Brien\\" + '$(__CLAUDE__);' + [char]96 + "\\secret.dpapi"
$block = New-LumenProfileBlock $hostile 'S-1-5-21-test' 'https://lumen.example' $selection $work
$prefix = "# existing Unicode: caf" + [char]0xE9 + "\nfunction User-Tool { 'unchanged' }\n"
$suffix = "# after Lumen\nSet-Alias user-tool User-Tool\n"
$profileText = Update-LumenProfile $prefix $block
$combined = $profileText + $suffix
$again = Update-LumenProfile $combined $block
$tokens = $null; $errors = $null
$blockAst = [Management.Automation.Language.Parser]::ParseInput($block, [ref] $tokens, [ref] $errors)
if ($errors.Count) { throw ($errors | Out-String) }
$pathConstants = @($blockAst.FindAll({ param($n) $n -is [Management.Automation.Language.StringConstantExpressionAst] -and $n.Value -ceq $hostile }, $true))
$expandable = @($blockAst.FindAll({ param($n) $n -is [Management.Automation.Language.ExpandableStringExpressionAst] -or $n -is [Management.Automation.Language.SubExpressionAst] }, $true) | Where-Object { $_.Extent.Text -like '*Get-Date*' })
$bad = @('# >>> Lumen CLI >>>', '# <<< Lumen CLI <<<', "# <<< Lumen CLI <<<\n# >>> Lumen CLI >>>", ($block + "\n" + $block))
$rejected = foreach ($value in $bad) { try { $null = Update-LumenProfile $value $block; $false } catch { $true } }
@{ combined = $combined; again = $again; prefix = $prefix; suffix = $suffix; literalPath = ($pathConstants.Count -eq 1); expandable = $expandable.Count; rejected = @($rejected) } | ConvertTo-Json -Compress
`);
	assert.equal(result.again, result.combined);
	assert.ok(result.again.startsWith(result.prefix));
	assert.ok(result.again.endsWith(result.suffix));
	assert.equal(result.literalPath, true);
	assert.equal(result.expandable, 0, "server-provided names stay literal");
	assert.ok(result.rejected.every(Boolean));
});

behavior("profile exports independent Claude family routes, honest labels and startup alias without inert capability pins", () => {
	const result = run(`
${selectionPrelude(defaultAnswers)}
$block = New-LumenProfileBlock 'C:\\private\\key.dpapi' 'S-1-5-test' 'https://lumen.example' $selection $work
$tokens = $null; $errors = $null
$blockAst = [Management.Automation.Language.Parser]::ParseInput($block, [ref] $tokens, [ref] $errors)
if ($errors.Count) { throw ($errors | Out-String) }
$assigned = [ordered] @{}
foreach ($node in $blockAst.FindAll({ param($n) $n -is [Management.Automation.Language.AssignmentStatementAst] -and $n.Left -is [Management.Automation.Language.VariableExpressionAst] -and $n.Left.VariablePath.DriveName -eq 'env' }, $true)) {
 $value = $null
 if ($node.Right.Expression -is [Management.Automation.Language.StringConstantExpressionAst]) { $value = $node.Right.Expression.Value }
 $assigned[$node.Left.VariablePath.UserPath.Substring(4)] = $value
}
$removed = @($blockAst.FindAll({ param($n) $n -is [Management.Automation.Language.CommandAst] -and $n.GetCommandName() -eq 'Remove-Item' }, $true) | ForEach-Object { $_.CommandElements[1].Extent.Text })
@{ assigned = $assigned; removed = $removed } | ConvertTo-Json -Compress -Depth 3
`);
	const env = result.assigned;
	assert.deepEqual([env.ANTHROPIC_DEFAULT_FABLE_MODEL, env.ANTHROPIC_DEFAULT_OPUS_MODEL, env.ANTHROPIC_DEFAULT_SONNET_MODEL, env.ANTHROPIC_DEFAULT_HAIKU_MODEL],
		["lumen/4/22", "lumen/3/21", "lumen/7/11", "lumen/4/22"]);
	assert.equal(env.ANTHROPIC_DEFAULT_FABLE_MODEL_NAME, label("Fable", "Team's sub $(Get-Date)", "Shared Model"));
	assert.equal(env.ANTHROPIC_DEFAULT_OPUS_MODEL_NAME, label("Opus", "Anthropic API", "Claude Sonnet 5"));
	assert.equal(env.ANTHROPIC_DEFAULT_SONNET_MODEL_NAME, label("Sonnet", "OpenAI API", "GPT-5.6 Sol"));
	assert.match(env.ANTHROPIC_DEFAULT_HAIKU_MODEL_DESCRIPTION, /^shared-model via Team's sub \$\(Get-Date\) \(anthropic_subscription\), Lumen route lumen\/4\/22\./);
	assert.equal(env.ANTHROPIC_MODEL, "opus");
	assert.equal(env.ANTHROPIC_BASE_URL, "https://lumen.example");
	for (const obsolete of ["LUMEN_MODEL", "LUMEN_CODEX_MODEL", "CLAUDE_CODE_AUTO_MODE_SERVER"]) assert.equal(Object.hasOwn(env, obsolete), false);
});

behavior("terminal function survives installer child scopes and profile startup without alias shadowing", () => {
	const result = run(`
${selectionPrelude(defaultAnswers)}
$block = New-LumenProfileBlock 'C:\\private\\key.dpapi' 'S-1-5-test' 'https://lumen.example' $selection $work
$tokens = $null; $errors = $null
$profileAst = [Management.Automation.Language.Parser]::ParseInput($block, [ref] $tokens, [ref] $errors)
if ($errors.Count) { throw ($errors | Out-String) }
# Exercise the actual generated terminal declarations, excluding DPAPI (covered
# by the real Windows test). No external-command or credential stand-ins.
$terminal = [scriptblock]::Create((($profileAst.EndBlock.Statements | Select-Object -Skip 1 | ForEach-Object { $_.Extent.Text }) -join "\n"))
Set-Alias -Name codex -Value Get-Date -Scope Global -Option ReadOnly
Set-Alias -Name codex -Value Get-Location -Scope Script -Force
& {
 Set-Alias -Name codex -Value Get-Item -Force
 & { & $terminal }
}
$immediate = (Get-Command codex).CommandType.ToString()
$globalAliasGone = -not (Get-Alias -Name codex -Scope Global -ErrorAction SilentlyContinue)
Remove-Item Function:codex -Force
Set-Alias -Name codex -Value Get-Date -Scope Global
. $terminal
$startup = (Get-Command codex).CommandType.ToString()
$startupAliasGone = -not (Get-Alias -Name codex -ErrorAction SilentlyContinue)
@{ immediate = $immediate; globalAliasGone = $globalAliasGone; startup = $startup; startupAliasGone = $startupAliasGone } | ConvertTo-Json -Compress
`);
	assert.equal(result.immediate, "Function");
	assert.equal(result.globalAliasGone, true);
	assert.equal(result.startup, "Function");
	assert.equal(result.startupAliasGone, true);
});

behavior("wrapper classification follows native option arity, aliases and prompt boundaries", () => {
	const cases = [
		[[], true, true], [["fix this"], true, true],
		...['agents', 'exec', 'e', 'review', 'resume', 'fork', 'queue', 'archive', 'delete', 'unarchive'].map((command) => [[command], true, true]),
		...['login', 'logout', 'mcp', 'plugin', 'app-server', 'remote-control', 'app', 'completion', 'update', 'doctor', 'sandbox', 'execpolicy', 'apply', 'a', 'migrate-rollouts', 'cloud', 'cloud-tasks', 'responses-api-proxy', 'stdio-to-uds', 'exec-server', 'features', 'tcp-tunnel', 'help'].map((command) => [[command], false, false]),
		[["debug", "models", "--bundled"], false, false], [["debug", "prompt-input", "prompt"], false, true],
		[["--profile", "lumen-luna", "debug", "prompt-input", "prompt"], false, false],
		...['-pother', '-p=other', '--profile=other'].map((option) => [[option, 'exec'], true, false]),
		[["--strict-config", "exec"], false, true],
		[["--config", "--profile=other", "exec"], true, true],
		[["exec", "--model", "--profile=other"], true, true],
		[["exec", "-c", "--strict-config"], true, true],
		[["debug", "--config", "model='login'", "prompt-input", "prompt"], false, true],
		[["debug", "--config=model='login'", "prompt-input", "prompt"], false, true],
		[["exec", "--profile", "--strict-config"], true, false],
		[["exec", "-i", "file.png", "login", "--profile=other"], true, false],
		...['-c', '-m', '-s', '-a', '-C', '--config', '--enable', '--disable', '--remote', '--remote-auth-token-env', '--model', '--local-provider', '--sandbox', '--ask-for-approval', '--cd', '--add-dir'].map((option) => [[option, 'login', 'exec'], true, true]),
		...['-clogin', '-mlogin', '-slogin', '-alogin', '-Clogin', '--config=login', '--model=login', '--add-dir=login'].map((option) => [[option, 'mcp'], false, false]),
		// Native 0.160: only the space forms are greedy; attached image values leave the next word a subcommand.
		...['-i', '--image'].map((option) => [[option, 'login', 'mcp', '--search'], true, true]),
		...['-ifile.png', '-i=file.png', '--image=file.png'].map((option) => [[option, 'login', 'mcp', '--search'], false, false]),
		[["-i", "file.png", "login", "--profile", "other", "exec"], true, false],
		[["--", "login", "--profile=other", "--strict-config"], true, true],
		[["exec", "--", "--profile=other", "--strict-config"], true, true],
		[["debug", "prompt-input", "--", "--profile=other"], false, true],
	];
	const result = run(`
${selectionPrelude(defaultAnswers)}
$block = New-LumenProfileBlock 'C:\\private\\key.dpapi' 'S-1-5-test' 'https://lumen.example' $selection $work
$tokens = $null; $errors = $null
$profileAst = [Management.Automation.Language.Parser]::ParseInput($block, [ref] $tokens, [ref] $errors)
if ($errors.Count) { throw ($errors | Out-String) }
$wrapper = $profileAst.Find({ param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'global:codex' }, $true)
# Evaluate the generated classification, not a forwarding mock or echo binary.
# The separate native test consumes these defaults through real Codex config.
$statements = @($wrapper.Body.EndBlock.Statements)
$classifier = [scriptblock]::Create((($statements | Select-Object -Skip 3 | Select-Object -SkipLast 1 | ForEach-Object { $_.Extent.Text }) -join "\n"))
$cases = ConvertFrom-Json ${psLiteral(asciiJson(cases))}
$results = foreach ($case in $cases) {
 $forward = [Collections.ArrayList] @($case[0])
 . $classifier
 @{ strict = ($defaults -ccontains '--strict-config'); profile = ($defaults -ccontains '--profile') }
}
@{ results = @($results) } | ConvertTo-Json -Compress -Depth 4
`);
	assert.deepEqual(result.results, cases.map(([, strict, profile]) => ({ strict, profile })));
});

behavior("native Codex consumes wrapper defaults, explicit profiles/config/model and typed or splatted boundaries", (t) => {
	const result = run(`
${selectionPrelude(defaultAnswers)}
$native = Get-Command codex -CommandType Application,ExternalScript -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -eq $native) { @{ available = $false } | ConvertTo-Json -Compress; return }
$codexHome = Join-Path $work 'codex'
[void] [IO.Directory]::CreateDirectory($codexHome)
$catalog = Join-Path $codexHome 'lumen-models.json'
$instructions = Get-LumenCodexBaseInstructions
Write-LumenFile $catalog (New-LumenCodexCatalog $selection $instructions)
# Test-only developer instructions identify the real native profile/config
# consumer's choice. debug prompt-input renders locally; it makes no model call.
foreach ($profile in @('lumen-cli', 'lumen-sol', 'lumen-luna')) {
 $model = $selection.Roles['Sol'].Id; if ($profile -eq 'lumen-luna') { $model = $selection.Roles['Luna'].Id }
 $text = Update-LumenToml '' 'https://127.0.0.1:1/v1' $model $true $catalog
 $text = 'developer_instructions = "SELECTED ' + $profile + '"' + [char]10 + $text
 Write-LumenFile (Join-Path $codexHome ($profile + '.config.toml')) $text
}
$env:CODEX_HOME = $codexHome
$env:LUMEN_API_KEY = 'synthetic-offline-key'
$block = New-LumenProfileBlock 'C:\\private\\key.dpapi' 'S-1-5-test' 'https://lumen.example' $selection $codexHome
$tokens = $null; $errors = $null
$profileAst = [Management.Automation.Language.Parser]::ParseInput($block, [ref] $tokens, [ref] $errors)
if ($errors.Count) { throw ($errors | Out-String) }
$terminal = [scriptblock]::Create((($profileAst.EndBlock.Statements | Select-Object -Skip 1 | ForEach-Object { $_.Extent.Text }) -join "\n"))
. $terminal
$results = [ordered] @{}
$results['default'] = ((codex debug prompt-input 'fix "this" now') -join "\n")
if ($LASTEXITCODE -ne 0) { throw 'Native Codex rejected the default profile.' }
$results['explicit'] = ((codex --profile lumen-luna debug prompt-input 'Luna prompt') -join "\n")
if ($LASTEXITCODE -ne 0) { throw 'Native Codex rejected the explicit profile.' }
$results['short'] = ((codex -plumen-sol debug prompt-input 'Sol prompt') -join "\n")
if ($LASTEXITCODE -ne 0) { throw 'Native Codex rejected the short profile option.' }
$results['override'] = ((codex -m lumen/7/12 -c 'developer_instructions="CALLER OVERRIDE"' debug prompt-input 'Config prompt') -join "\n")
if ($LASTEXITCODE -ne 0) { throw 'Native Codex rejected caller model/config overrides.' }
# A typed -- vanishes at the function binder; a splatted '--' does not. Both
# must reach Codex so a prompt that looks like --profile is not an option.
$results['typed'] = ((codex debug prompt-input -- '--profile=lumen-luna') -join "\n")
if ($LASTEXITCODE -ne 0) { throw 'Native Codex rejected a typed boundary.' }
$argv = @('debug', 'prompt-input', '--', '--profile=lumen-luna')
$results['splatted'] = ((codex @argv) -join "\n")
if ($LASTEXITCODE -ne 0) { throw 'Native Codex rejected a splatted boundary.' }
$tail = @('--profile=lumen-luna')
$results['tailSplat'] = ((codex debug prompt-input -- @tail) -join "\n")
if ($LASTEXITCODE -ne 0) { throw 'Native Codex rejected a typed boundary before splatted prompt text.' }
$results['attached'] = ((codex --profile=lumen-luna debug prompt-input 'Attached profile') -join "\n")
if ($LASTEXITCODE -ne 0) { throw 'Native Codex rejected the attached profile option.' }
$results['commandValue'] = ((codex -c 'developer_instructions="login"' debug prompt-input 'Value prompt') -join "\n")
if ($LASTEXITCODE -ne 0) { throw 'Native Codex rejected a command-looking option value.' }
$management = [ordered] @{}
$management['features'] = ((codex features list) -join "\n")
if ($LASTEXITCODE -ne 0) { throw 'Native features command received unsupported wrapper defaults.' }
$management['completion'] = ((codex completion powershell) -join "\n")
if ($LASTEXITCODE -ne 0) { throw 'Native completion command received unsupported wrapper defaults.' }
$management['mcp'] = ((codex mcp list) -join "\n")
if ($LASTEXITCODE -ne 0) { throw 'Native mcp command received unsupported wrapper defaults.' }
$management['models'] = ((codex debug models --bundled) -join "\n")
if ($LASTEXITCODE -ne 0) { throw 'Native debug models command received unsupported wrapper defaults.' }
@{ available = $true; results = $results; management = $management } | ConvertTo-Json -Compress
`);
	if (!result.available) return t.skip("Native Codex executable unavailable; no forwarding stub is substituted");
	assert.match(result.management.features, /\S/);
	assert.match(result.management.completion, /Register-ArgumentCompleter/);
	assert.ok(JSON.parse(result.management.models).models.length > 0);
	for (const [name, value] of Object.entries(result.results)) {
		const items = JSON.parse(value);
		assert.ok(Array.isArray(items), `${name}: native model-visible input list`);
		const textFor = (role) => items.filter((item) => item.role === role).flatMap((item) => item.content || []).map((part) => part.text || "").join("\n");
		const expectedProfile = ["explicit", "attached"].includes(name) ? "lumen-luna" : name === "short" ? "lumen-sol" : "lumen-cli";
		const expectedDeveloper = name === "override" ? "CALLER OVERRIDE" : name === "commandValue" ? "login" : `SELECTED ${expectedProfile}`;
		assert.ok(textFor("developer").includes(expectedDeveloper), `${name}: caller/default native config took effect`);
		const prompt = ({ default: 'fix "this" now', explicit: "Luna prompt", short: "Sol prompt", override: "Config prompt", attached: "Attached profile", commandValue: "Value prompt" })[name] || "--profile=lumen-luna";
		assert.ok(textFor("user").includes(prompt), `${name}: complete prompt argument reached the native consumer`);
	}
});

behavior("changed files get exact backups; identical reruns make no additional backups", () => {
	const result = run(`
${selectionPrelude(defaultAnswers)}
$p = Join-Path $work 'profile.ps1'
$original = "# caf" + [char]0xE9 + "\r\nfunction Existing { 'ok' }\r\n"
[IO.File]::WriteAllText($p, $original, (New-Object Text.UTF8Encoding($true)))
$oldBytes = [Convert]::ToBase64String([IO.File]::ReadAllBytes($p))
$changed = Update-LumenProfile $original (New-LumenProfileBlock 'C:\\private\\api-key.dpapi' 'S-1-5-test' 'https://lumen.example' $selection $work)
Write-LumenFile $p $changed $true
Write-LumenFile $p $changed $true
$backups = @(Get-ChildItem -LiteralPath $work -Filter '*.bak')
@{ content = [IO.File]::ReadAllText($p); expected = $changed; count = $backups.Count; before = $oldBytes; backup = [Convert]::ToBase64String([IO.File]::ReadAllBytes($backups[0].FullName)) } | ConvertTo-Json -Compress
`);
	assert.equal(result.content, result.expected);
	assert.equal(result.count, 1);
	assert.equal(result.backup, result.before);
});

behavior("a failed write restores every earlier file of the run and removes its backups", () => {
	const result = run(`
$existing = Join-Path $work 'config.toml'
$created = Join-Path $work 'lumen-models.json'
$blocker = Join-Path $work 'blocker'
[IO.File]::WriteAllText($existing, "model = 'desktop'\n")
[IO.File]::WriteAllText($blocker, 'a regular file where a directory is required')
$before = [Convert]::ToBase64String([IO.File]::ReadAllBytes($existing))
$item = { param($path, $content) [pscustomobject] @{ Path = $path; Content = $content; ProfileFile = $false; Key = $null } }
$message = ''
try {
 Invoke-LumenWritePlan @((& $item $created '{"models":[]}'), (& $item $existing "model = 'changed'\n"), (& $item (Join-Path $blocker 'profile.ps1') '# new'))
} catch { $message = $_.Exception.Message }
$failed = @{ message = $message; restored = ([Convert]::ToBase64String([IO.File]::ReadAllBytes($existing)) -ceq $before); createdRemoved = (-not [IO.File]::Exists($created)); backups = @(Get-ChildItem -LiteralPath $work -Filter '*.bak').Count }
Invoke-LumenWritePlan @((& $item $created '{"models":[]}'), (& $item $existing "model = 'changed'\n"))
$backups = @(Get-ChildItem -LiteralPath $work -Filter '*.bak')
@{ failed = $failed; written = [IO.File]::ReadAllText($existing); created = [IO.File]::ReadAllText($created); backups = $backups.Count; backupMatches = ([Convert]::ToBase64String([IO.File]::ReadAllBytes($backups[0].FullName)) -ceq $before) } | ConvertTo-Json -Compress
`);
	assert.match(result.failed.message, /^No changes were kept: /);
	assert.equal(result.failed.restored, true);
	assert.equal(result.failed.createdRemoved, true);
	assert.equal(result.failed.backups, 0);
	assert.equal(result.written, "model = 'changed'\n");
	assert.equal(result.created, '{"models":[]}');
	assert.equal(result.backups, 1);
	assert.equal(result.backupMatches, true);
});

behavior("legacy encodings fail without rewriting while UTF-8 BOM and Unicode round-trip", () => {
	const result = run(`
$p = Join-Path $work 'profile.ps1'
$unicode = "# caf" + [char]0xE9 + " " + [char]0x65E5 + [char]0x672C + [char]0x8A9E + "\n"
$values = @(
 [byte[]] @(35, 32, 233),
 [Text.Encoding]::UTF8.GetBytes("# text" + [char]0)
)
$rejected = foreach ($value in $values) {
 [IO.File]::WriteAllBytes($p, [byte[]] $value)
 $before = [Convert]::ToBase64String([IO.File]::ReadAllBytes($p))
 $failed = $false
 try { Write-LumenFile $p '# replacement' $true } catch { $failed = $_.Exception.Message -like '*Unsupported config/profile encoding*' }
 $failed -and $before -ceq [Convert]::ToBase64String([IO.File]::ReadAllBytes($p))
}
[IO.File]::WriteAllText($p, $unicode, (New-Object Text.UTF8Encoding($true)))
$withBom = Read-LumenTextFile $p
[IO.File]::WriteAllText($p, $unicode, (New-Object Text.UTF8Encoding($false)))
@{ rejected = @($rejected); backups = @(Get-ChildItem -LiteralPath $work -Filter '*.bak').Count; withBom = $withBom; withoutBom = (Read-LumenTextFile $p); expected = $unicode } | ConvertTo-Json -Compress
`);
	assert.ok(result.rejected.every(Boolean));
	assert.equal(result.backups, 0);
	assert.equal(result.withBom, result.expected);
	assert.equal(result.withoutBom, result.expected);
});

behavior("BOM-marked UTF-16 profiles preserve Unicode and exact backups; TOML refuses UTF-16", () => {
	const result = run(`
${selectionPrelude(defaultAnswers)}
$profilePath = Join-Path $work 'legacy-profile.ps1'
$configPath = Join-Path $work 'config.toml'
$original = "# caf" + [char]0xE9 + " " + [char]0x65E5 + [char]0x672C + [char]0x8A9E + "\r\nfunction Existing { 'ok' }\r\n"
[IO.File]::WriteAllText($profilePath, $original, [Text.Encoding]::Unicode)
[IO.File]::WriteAllText($configPath, $original, [Text.Encoding]::Unicode)
$before = [Convert]::ToBase64String([IO.File]::ReadAllBytes($profilePath))
$loaded = Read-LumenTextFile $profilePath $true
$newProfile = Update-LumenProfile $loaded (New-LumenProfileBlock 'C:\\private\\key.dpapi' 'S-1-5-test' 'https://lumen.example' $selection $work)
Write-LumenFile $profilePath $newProfile $true
Write-LumenFile $profilePath $newProfile $true
$backups = @(Get-ChildItem -LiteralPath $work -Filter '*.bak')
$configRejected = $false
try { Write-LumenFile $configPath '# replacement' } catch { $configRejected = $_.Exception.Message -like '*Unsupported config/profile encoding*' }
@{ loaded = $loaded; original = $original; changed = (Read-LumenTextFile $profilePath $true); expected = $newProfile; backups = $backups.Count; backup = [Convert]::ToBase64String([IO.File]::ReadAllBytes($backups[0].FullName)); before = $before; configRejected = $configRejected; configUnchanged = ([Convert]::ToBase64String([IO.File]::ReadAllBytes($configPath)) -ceq $before) } | ConvertTo-Json -Compress
`);
	assert.equal(result.loaded, result.original);
	assert.equal(result.changed, result.expected);
	assert.equal(result.backups, 1);
	assert.equal(result.backup, result.before);
	assert.equal(result.configRejected, true);
	assert.equal(result.configUnchanged, true);
});


behavior("custom CA selection preserves existing trust, validates PEM and honors explicit override", () => {
	const result = run(`
$existing = Join-Path $work 'existing.pem'
$override = Join-Path $work 'override.pem'
$invalid = Join-Path $work 'invalid.pem'
$rsa = [Security.Cryptography.RSA]::Create()
$rsa.KeySize = 2048
$certificate = $null
try {
 $request = New-Object Security.Cryptography.X509Certificates.CertificateRequest -ArgumentList ('CN=Lumen installer test', $rsa, [Security.Cryptography.HashAlgorithmName]::SHA256, [Security.Cryptography.RSASignaturePadding]::Pkcs1)
 $certificate = $request.CreateSelfSigned([DateTimeOffset]::UtcNow.AddDays(-1), [DateTimeOffset]::UtcNow.AddDays(1))
 $pem = "-----BEGIN CERTIFICATE-----\n" + [Convert]::ToBase64String($certificate.Export([Security.Cryptography.X509Certificates.X509ContentType]::Cert)) + "\n-----END CERTIFICATE-----\n"
 [IO.File]::WriteAllText($existing, $pem)
 [IO.File]::WriteAllText($override, $pem)
 [IO.File]::WriteAllText($invalid, "-----BEGIN CERTIFICATE-----\nZmFrZQ==\n-----END CERTIFICATE-----\n")
 $rejected = foreach ($value in @($invalid, (Join-Path $work 'missing.pem'), $work)) {
  try { $null = Resolve-LumenCaBundle '' $value; $false } catch { $true }
 }
 @{ existing = (Resolve-LumenCaBundle '' $existing); expectedExisting = $existing; override = (Resolve-LumenCaBundle $override $invalid); expectedOverride = $override; systemTrust = (Resolve-LumenCaBundle '' ''); rejected = @($rejected) } | ConvertTo-Json -Compress
} finally { if ($null -ne $certificate) { $certificate.Dispose() }; $rsa.Dispose() }
`);
	assert.equal(result.existing, result.expectedExisting);
	assert.equal(result.override, result.expectedOverride);
	assert.equal(result.systemTrust, "");
	assert.ok(result.rejected.every(Boolean));
});

behavior("discovery HTTPS bases can use local and intranet hosts without network access", () => {
	const result = run(`
@('https://localhost:8443/v1', 'https://127.0.0.1/v1', 'https://service.internal', 'https://[::1]:9443/v1') | ForEach-Object { ConvertTo-LumenBaseUrl $_ } | ConvertTo-Json -Compress
`);
	assert.deepEqual(result, ["https://localhost:8443/v1", "https://127.0.0.1/v1", "https://service.internal", "https://[::1]:9443/v1"]);
});

behavior("local paths reject actual directory links and accept ordinary directories", () => {
	const result = run(`
$target = Join-Path $work 'target'
$link = Join-Path $work 'link'
[void] [IO.Directory]::CreateDirectory($target)
Assert-LumenLocalPath (Join-Path $target 'new-profile.ps1')
$kind = 'SymbolicLink'
if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) { $kind = 'Junction' }
$null = New-Item -ItemType $kind -Path $link -Target $target -ErrorAction Stop
$rejected = $false
try { Assert-LumenLocalPath (Join-Path $link 'new-profile.ps1') } catch { $rejected = $_.Exception.Message -like '*symlinks/junctions*' }
@{ rejected = $rejected } | ConvertTo-Json -Compress
`);
	assert.equal(result.rejected, true);
});

behavior("TOML string escaping round-trips quotes, backslashes and controls", () => {
	const result = run(`
$value = 'https://example.test/a"b\\c' + [char]9 + [char]127
$encoded = ConvertTo-LumenTomlString $value
@{ decoded = (ConvertFrom-Json $encoded); original = $value } | ConvertTo-Json -Compress
`);
	assert.equal(result.decoded, result.original);
});

behavior("irm|iex-style invocation fails clearly before prompts or writes on non-Windows", () => {
	const result = run(`
$env:CODEX_HOME = Join-Path $work 'codex'
$prompted = $false
function Read-Host { $script:prompted = $true; throw 'Unexpected prompt' }
$message = ''
try { [IO.File]::ReadAllText($sourcePath) | Invoke-Expression } catch { $message = $_.Exception.Message }
@{ message = $message; prompted = $prompted; created = (Test-Path -LiteralPath $env:CODEX_HOME) } | ConvertTo-Json -Compress
`, { definitions: false });
	assert.match(result.message, /requires Windows DPAPI CurrentUser/);
	assert.equal(result.prompted, false);
	assert.equal(result.created, false);
}, { skip: process.platform === "win32" ? "Non-Windows unsupported-host behavior is exercised on non-Windows" : false });

// ---------------------------------------------------------------------------
// Real installer flow: the actual Invoke-LumenInstall, real HTTPS client and a
// local HTTPS catalog server. These planner/HTTP flows isolate the platform
// gate, account SID lookup and key persistence; separate Windows-only tests
// exercise real CurrentUser DPAPI and private ACLs. Other operations are real.
// Credential paths are redirected to the temporary directory too; the flow
// harness never reads or restores the user's real credential file. Native
// Windows DPAPI/ACL are exercised separately, without any storage stand-in.
const testKey = "lumen-test-key-not-real-0001";

function installHarness() {
	return `
$codexHome = Join-Path $work 'codex'
$profilePath = Join-Path $work 'profile.ps1'
$PROFILE = [pscustomobject] @{ CurrentUserAllHosts = $profilePath }
$env:CODEX_HOME = $codexHome
$env:LUMEN_ANTHROPIC_BASE_URL = 'https://lumen.example'
Remove-Item Env:LUMEN_CA_BUNDLE, Env:CODEX_CA_CERTIFICATE -ErrorAction SilentlyContinue
$tracked = @(@('config.toml', 'lumen-cli.config.toml', 'lumen-sol.config.toml', 'lumen-luna.config.toml', 'lumen-models.json') | ForEach-Object { Join-Path $codexHome $_ }) + @($profilePath)
function Assert-LumenWindows { }
function Get-LumenUserSid { 'S-1-5-21-1000-2000-3000-1001' }
function Get-LumenKeyPath { Join-Path $work 'synthetic-key.dpapi' }
function Save-LumenKey {
 param([Security.SecureString] $Key, [string] $Path)
 $script:keySaves++
 if ($script:saveFails) { throw 'API key was not saved: injected DPAPI failure.' }
}
function Read-Host {
 param([string] $Prompt, [switch] $AsSecureString)
 $script:prompts += $Prompt
 if ($AsSecureString) { return (ConvertTo-SecureString $script:secret -AsPlainText -Force) }
 $value = $script:answers[$script:answerIndex]; $script:answerIndex++
 if ($value -ceq 'ABORT') { throw 'Simulated prompt interruption.' }
 return $value
}
function Get-Snapshot { foreach ($file in $tracked) { if ([IO.File]::Exists($file)) { [Convert]::ToBase64String([IO.File]::ReadAllBytes($file)) } else { '-' } } }
function Reset-Seeds {
 if ([IO.Directory]::Exists($codexHome)) { [IO.Directory]::Delete($codexHome, $true) }
 [void] [IO.Directory]::CreateDirectory($codexHome)
 [IO.File]::WriteAllText((Join-Path $codexHome 'config.toml'), "model = 'desktop'\nmodel_provider = 'openai'\n")
 [IO.File]::WriteAllText((Join-Path $codexHome 'lumen-cli.config.toml'), "model = 'old-terminal'\nmodel_provider = 'lumen'\n[model_providers.lumen]\nbase_url = 'https://old.example/v1'\n[model_providers.lumen.http_headers]\nX-Lumen-Provider = 'openai'\nX-Team = 'keep'\n")
 [IO.File]::WriteAllText($profilePath, "# user profile\n")
}
function Invoke-TestInstall([string] $Url, [string[]] $Answers = @(), [string] $Secret = ${psLiteral(testKey)}, [bool] $SaveFails = $false) {
 Reset-Seeds
 $env:LUMEN_CODEX_BASE_URL = $Url
 $script:answers = $Answers; $script:answerIndex = 0; $script:prompts = @(); $script:secret = $Secret; $script:keySaves = 0; $script:saveFails = $SaveFails
 $before = Get-Snapshot
 $script:hostLines = @(); $message = ''
 try { Invoke-LumenInstall 6>&1 3>&1 | ForEach-Object { $script:hostLines += [string] $_ } } catch { $message = $_.Exception.Message }
 $after = Get-Snapshot
 $hostText = $script:hostLines -join "\n"
 [pscustomobject] @{ message = $message; prompts = @($script:prompts); keySaves = $script:keySaves; unchanged = (($before -join '|') -ceq ($after -join '|')); leaked = ($hostText + $message).Contains($Secret); backups = @(Get-ChildItem -LiteralPath $work -Recurse -Filter '*.bak').Count; host = $hostText }
}
function Read-Installed([string] $Name) { $file = Join-Path $codexHome $Name; if ([IO.File]::Exists($file)) { [IO.File]::ReadAllText($file) } else { $null } }
`;
}

let certificateCache;
function testCertificate() {
	if (certificateCache === undefined) {
		certificateCache = run(`
if ($PSVersionTable.PSEdition -ne 'Core') { @{ supported = $false } | ConvertTo-Json -Compress; return }
$rsa = [Security.Cryptography.RSA]::Create(2048)
$request = [Security.Cryptography.X509Certificates.CertificateRequest]::new('CN=127.0.0.1', $rsa, [Security.Cryptography.HashAlgorithmName]::SHA256, [Security.Cryptography.RSASignaturePadding]::Pkcs1)
$san = [Security.Cryptography.X509Certificates.SubjectAlternativeNameBuilder]::new()
$san.AddIpAddress([Net.IPAddress]::Parse('127.0.0.1')); $san.AddDnsName('localhost')
$request.CertificateExtensions.Add($san.Build())
$usage = [Security.Cryptography.OidCollection]::new(); [void] $usage.Add([Security.Cryptography.Oid]::new('1.3.6.1.5.5.7.3.1'))
$request.CertificateExtensions.Add([Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]::new($usage, $false))
$certificate = $request.CreateSelfSigned([DateTimeOffset]::UtcNow.AddDays(-1), [DateTimeOffset]::UtcNow.AddDays(2))
$pemBoundary = '-----'
@{ supported = $true
 cert = "-----BEGIN CERTIFICATE-----\n" + [Convert]::ToBase64String($certificate.RawData, 'InsertLineBreaks') + "\n-----END CERTIFICATE-----\n"
 key = ($pemBoundary + "BEGIN PRIVATE" + " KEY-----\n" + [Convert]::ToBase64String($rsa.ExportPkcs8PrivateKey(), 'InsertLineBreaks') + "\n" + $pemBoundary + "END PRIVATE" + " KEY-----\n") } | ConvertTo-Json -Compress
`, { definitions: false });
	}
	return certificateCache.supported ? certificateCache : null;
}

// Local HTTPS catalog: /ok, /empty, /redirect, /denied (echoes the received
// Authorization header to prove it never reaches installer output) and /html.
const serverSource = `
const https = require("node:https");
const fs = require("node:fs");
const [certPath, keyPath, logPath, catalogPath] = process.argv.slice(2);
const log = (entry) => fs.appendFileSync(logPath, JSON.stringify(entry) + "\\n");
const server = https.createServer({ cert: fs.readFileSync(certPath), key: fs.readFileSync(keyPath) }, (req, res) => {
	log({ method: req.method, url: req.url, authorization: req.headers.authorization || null });
	const route = req.url.split("/")[1];
	if (!req.url.endsWith("/v1/cli/models")) { res.writeHead(404); return res.end(); }
	if (route === "redirect") { res.writeHead(302, { location: "/captured/v1/cli/models" }); return res.end(); }
	if (route === "denied") { res.writeHead(401, { "content-type": "application/json" }); return res.end(JSON.stringify({ error: { message: "rejected " + req.headers.authorization } })); }
	if (route === "html") { res.writeHead(200, { "content-type": "text/html" }); return res.end("<html></html>"); }
	const body = route === "empty" ? JSON.stringify({ models: [] }) : fs.readFileSync(catalogPath);
	res.writeHead(200, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
	res.end(body);
});
server.on("connection", () => log({ connected: true }));
server.listen(0, "127.0.0.1", () => process.stdout.write("PORT " + server.address().port + "\\n"));
`;

async function withCatalogServer(certificate, fn) {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "lumen-catalog-"));
	const files = { server: path.join(dir, "server.js"), cert: path.join(dir, "cert.pem"), key: path.join(dir, "key.pem"), log: path.join(dir, "requests.log"), catalog: path.join(dir, "catalog.json") };
	fs.writeFileSync(files.server, serverSource);
	fs.writeFileSync(files.cert, certificate.cert);
	fs.writeFileSync(files.key, certificate.key, { mode: 0o600 });
	fs.writeFileSync(files.catalog, JSON.stringify(catalogFixture));
	fs.writeFileSync(files.log, "");
	const child = spawn(process.execPath, [files.server, files.cert, files.key, files.log, files.catalog], { stdio: ["ignore", "pipe", "inherit"] });
	try {
		const port = await new Promise((resolve, reject) => {
			let output = "";
			child.stdout.on("data", (chunk) => {
				output += chunk;
				const match = /PORT (\d+)/.exec(output);
				if (match) resolve(Number(match[1]));
			});
			child.on("exit", (code) => reject(new Error(`catalog server exited ${code}`)));
		});
		const requests = () => fs.readFileSync(files.log, "utf8").split("\n").filter(Boolean).map((line) => JSON.parse(line));
		return await fn({ base: `https://127.0.0.1:${port}`, certPath: files.cert, requests });
	} finally {
		child.kill();
		fs.rmSync(dir, { recursive: true, force: true });
	}
}

function assertNothingChanged(flow, label) {
	assert.equal(flow.unchanged, true, `${label}: files changed`);
	assert.equal(flow.keySaves, 0, `${label}: key storage reached`);
	assert.equal(flow.backups, 0, `${label}: backups created`);
	assert.equal(flow.leaked, false, `${label}: key printed`);
}

behavior("installer refuses invalid keys and unreachable or untrusted catalogs before any write or role prompt", async (t) => {
	const certificate = testCertificate();
	if (!certificate) return t.skip("TLS fixture key export requires PowerShell 7");
	await withCatalogServer(certificate, async ({ base, requests }) => {
		const result = run(`
${installHarness()}
@{
 invalidKey = (Invoke-TestInstall '${base}/ok/v1' @() 'bad key')
 unreachable = (Invoke-TestInstall 'https://127.0.0.1:1/v1')
 untrusted = (Invoke-TestInstall '${base}/ok/v1')
} | ConvertTo-Json -Compress -Depth 4
`);
		assert.match(result.invalidKey.message, /printable ASCII characters without spaces; no files were changed/);
		assert.match(result.unreachable.message, /^Could not read the Lumen model catalog over verified HTTPS/);
		assert.match(result.untrusted.message, /^Could not read the Lumen model catalog over verified HTTPS/);
		for (const [name, flow] of Object.entries(result)) {
			assertNothingChanged(flow, name);
			assert.deepEqual(flow.prompts, ["Full Lumen API key (input hidden)"], `${name}: no selection prompt`);
		}
		const seen = requests();
		assert.equal(seen.filter((entry) => entry.method).length, 0, "an untrusted certificate never receives the HTTP request or key");
		assert.ok(seen.some((entry) => entry.connected), "the untrusted attempt reached the server and stopped during TLS");
	});
});

// Linux .NET honors SSL_CERT_FILE, so a test-only CA can be trusted without
// touching the user's trust store; macOS/Windows have no equivalent.
const trustedSkip = process.platform !== "linux" ? "Verified-HTTPS success flows need Linux SSL_CERT_FILE; the OS trust store is never modified" : false;

behavior("verified catalog failures, incompatible choices and interruption change nothing", async (t) => {
	const certificate = testCertificate();
	if (!certificate) return t.skip("TLS fixture key export requires PowerShell 7");
	await withCatalogServer(certificate, async ({ base, certPath, requests }) => {
		const result = run(`
${installHarness()}
@{
 redirect = (Invoke-TestInstall '${base}/redirect/v1')
 denied = (Invoke-TestInstall '${base}/denied/v1')
 html = (Invoke-TestInstall '${base}/html/v1')
 empty = (Invoke-TestInstall '${base}/empty/v1')
 incompatible = (Invoke-TestInstall '${base}/ok/v1' @('4'))
 unavailable = (Invoke-TestInstall '${base}/ok/v1' @('1', '2', '5'))
 interrupted = (Invoke-TestInstall '${base}/ok/v1' @('1', '2', '4', '3', '1', 'ABORT'))
 badStartup = (Invoke-TestInstall '${base}/ok/v1' @('1', '2', '4', '3', '1', '4', 'gpt'))
 badDesktop = (Invoke-TestInstall '${base}/ok/v1' @('1', '2', '4', '3', '1', '4', '', 'maybe'))
} | ConvertTo-Json -Compress -Depth 4
`, { env: { SSL_CERT_FILE: certPath } });
		assert.match(result.redirect.message, /redirect \(HTTP 302\)\. Setup never forwards the key/);
		assert.match(result.denied.message, /rejected or lacks the models:read scope \(HTTP 401\)/);
		assert.match(result.html.message, /response is not JSON/);
		assert.match(result.empty.message, /no usable Codex \(Responses\) model/);
		assert.match(result.incompatible.message, /^Model 4 does not support the Responses API that Codex Sol requires/);
		assert.match(result.unavailable.message, /^Model 5 is unavailable \(subscription_protocol_unsupported\)/);
		assert.equal(result.interrupted.message, "Simulated prompt interruption.");
		assert.match(result.badStartup.message, /startup role/);
		assert.match(result.badDesktop.message, /Answer y\/yes or n\/no/);
		for (const [name, flow] of Object.entries(result)) assertNothingChanged(flow, name);
		assert.ok(!result.denied.host.includes("rejected Bearer"), "server error bodies are never echoed");
		const urls = requests().filter((entry) => entry.method).map((entry) => entry.url);
		assert.ok(urls.includes("/redirect/v1/cli/models"));
		assert.ok(!urls.includes("/captured/v1/cli/models"), "redirects are not followed");
		for (const entry of requests().filter((item) => item.method)) {
			assert.equal(entry.method, "GET");
			assert.equal(entry.authorization, `Bearer ${testKey}`);
			assert.ok(!entry.url.includes(testKey));
		}
	});
}, { skip: trustedSkip });

behavior("verified catalog install writes independent roles, native profiles and catalog; key failure rolls everything back", async (t) => {
	const certificate = testCertificate();
	if (!certificate) return t.skip("TLS fixture key export requires PowerShell 7");
	await withCatalogServer(certificate, async ({ base, certPath, requests }) => {
		const result = run(`
${installHarness()}
$rollback = Invoke-TestInstall '${base}/ok/v1' @('1', '2', '4', '3', '1', '4', 'opus', 'y') ${psLiteral(testKey)} $true
$installed = Invoke-TestInstall '${base}/ok/v1' @('1', '2', '4', '3', '1', '4', 'opus', 'n')
$files = @{ config = (Read-Installed 'config.toml'); cli = (Read-Installed 'lumen-cli.config.toml'); sol = (Read-Installed 'lumen-sol.config.toml'); luna = (Read-Installed 'lumen-luna.config.toml'); catalog = (Read-Installed 'lumen-models.json'); profile = [IO.File]::ReadAllText($profilePath) }
$catalogToml = ConvertTo-LumenTomlString (Join-Path $codexHome 'lumen-models.json')
$desktop = Invoke-TestInstall '${base}/ok/v1' @('2', '1', '3', '3', '3', '3', '', 'y')
$desktopFiles = @{ config = (Read-Installed 'config.toml'); cli = (Read-Installed 'lumen-cli.config.toml'); luna = (Read-Installed 'lumen-luna.config.toml'); profile = [IO.File]::ReadAllText($profilePath) }
@{ rollback = $rollback; installed = $installed; files = $files; catalogToml = $catalogToml; desktop = $desktop; desktopFiles = $desktopFiles } | ConvertTo-Json -Compress -Depth 4
`, { env: { SSL_CERT_FILE: certPath } });
		// DPAPI failure is the last step: every prepared file returns to its exact bytes.
		assert.match(result.rollback.message, /^No changes were kept: API key was not saved/);
		assert.equal(result.rollback.unchanged, true);
		assert.equal(result.rollback.keySaves, 1);
		assert.equal(result.rollback.backups, 0);
		assert.equal(result.rollback.leaked, false);

		const { installed, files } = result;
		// The generated profile cannot decrypt on a non-Windows host; every file was written first.
		assert.equal(installed.message, "Credential was saved but could not be loaded; setup is not complete.");
		assert.equal(installed.keySaves, 1);
		assert.equal(installed.leaked, false);
		assert.deepEqual(installed.prompts.slice(1).map((prompt) => prompt.split(" ").slice(0, 2).join(" ")),
			["Codex Sol", "Codex Luna", "Claude Fable", "Claude Opus", "Claude Sonnet", "Claude Haiku", "Claude Code", "Use this"]);
		assert.match(installed.host, /OpenAI API \(openai, openai\)/);
		assert.equal(files.config, "model = 'desktop'\nmodel_provider = 'openai'\n\n[model_providers.lumen]\nname = \"Lumen Responses\"\n" +
			`base_url = "${base}/ok/v1"\nenv_key = "LUMEN_API_KEY"\nwire_api = "responses"\nrequires_openai_auth = false\nsupports_websockets = false\n`);
		for (const [name, route] of [["cli", "lumen/7/11"], ["sol", "lumen/7/11"], ["luna", "lumen/7/12"]]) {
			const root = files[name].slice(0, files[name].indexOf("["));
			assert.ok(root.includes(`model = "${route}"`), `${name} route`);
			assert.ok(root.includes('model_provider = "lumen-cli"'), `${name} provider`);
			assert.ok(root.includes(`model_catalog_json = ${result.catalogToml}`), `${name} catalog`);
			assert.ok(files[name].includes("[model_providers.lumen-cli]"));
			assert.doesNotMatch(files[name].slice(files[name].indexOf("[model_providers.lumen-cli]")), /X-Lumen-Provider/);
		}
		assert.match(files.cli, /X-Team = 'keep'/);
		const catalog = JSON.parse(files.catalog).models;
		assert.deepEqual(catalog.map((model) => [model.slug, model.display_name.split(middleDot)[0]]), [["lumen/7/11", "Sol"], ["lumen/7/12", "Luna"]]);
		assert.ok(files.profile.startsWith("# user profile\n# >>> Lumen CLI >>>"));
		for (const [role, route] of [["FABLE", "lumen/4/22"], ["OPUS", "lumen/3/21"], ["SONNET", "lumen/7/11"], ["HAIKU", "lumen/4/22"]]) {
			assert.ok(files.profile.includes(`$env:ANTHROPIC_DEFAULT_${role}_MODEL = '${route}'`), role);
		}
		assert.ok(files.profile.includes("$env:ANTHROPIC_MODEL = 'opus'"));
		assert.ok(!files.profile.includes(testKey));

		// A different assignment keeps every role distinct (no collapse to one
		// model); the desktop opt-in writes the real public ID, provider untouched.
		assert.equal(result.desktop.message, "Credential was saved but could not be loaded; setup is not complete.");
		assert.ok(result.desktopFiles.config.startsWith("model = \"shared-model\"\nmodel_provider = 'openai'\n"));
		assert.ok(result.desktopFiles.cli.includes('model = "lumen/7/12"'));
		assert.ok(result.desktopFiles.luna.includes('model = "lumen/7/11"'));
		assert.ok(result.desktopFiles.profile.includes("$env:ANTHROPIC_DEFAULT_OPUS_MODEL = 'lumen/3/21'"));
		assert.ok(result.desktopFiles.profile.includes("$env:ANTHROPIC_MODEL = 'sonnet'"));

		const seen = requests().filter((entry) => entry.method);
		assert.equal(seen.length, 3, "one catalog request per installer run");
		for (const entry of seen) assert.deepEqual(entry, { method: "GET", url: "/ok/v1/cli/models", authorization: `Bearer ${testKey}` });
	});
}, { skip: trustedSkip });

behavior("Windows native catalog and backups are CurrentUser-only and rollback restores the prior ACL", () => {
	const result = run(`
$catalog = Join-Path $work 'lumen-models.json'
$blocker = Join-Path $work 'blocker'
[IO.File]::WriteAllText($catalog, '{"models":["old"]}')
[IO.File]::WriteAllText($blocker, 'not a directory')
$before = [Convert]::ToBase64String([IO.File]::ReadAllBytes($catalog))
$beforeAcl = (Get-Acl -LiteralPath $catalog).Sddl
$item = [pscustomobject] @{ Path = $catalog; Content = '{"models":["new"]}'; ProfileFile = $false; Key = $null; Private = $true }
$message = try {
 Invoke-LumenWritePlan @($item, [pscustomobject] @{ Path = (Join-Path $blocker 'bad'); Content = 'fail'; ProfileFile = $false; Key = $null })
 ''; } catch { $_.Exception.Message }
$restored = $before -ceq [Convert]::ToBase64String([IO.File]::ReadAllBytes($catalog)) -and $beforeAcl -ceq (Get-Acl -LiteralPath $catalog).Sddl
Invoke-LumenWritePlan @($item)
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$private = $true
$backups = @(Get-ChildItem -LiteralPath $work -Filter '*.bak')
foreach ($file in @($catalog) + @($backups | ForEach-Object { $_.FullName })) {
 $acl = Get-Acl -LiteralPath $file
 if (-not $acl.AreAccessRulesProtected) { $private = $false }
 foreach ($rule in $acl.Access) {
  if ($rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -cne $sid) { $private = $false }
 }
}
@{ message = $message; restored = $restored; private = $private; backups = $backups.Count } | ConvertTo-Json -Compress
`);
	assert.match(result.message, /^No changes were kept:/);
	assert.equal(result.restored, true);
	assert.equal(result.private, true);
	assert.equal(result.backups, 1);
}, { skip: process.platform !== "win32" ? "Real Windows catalog ACL behavior requires Windows" : false });

behavior("actual Windows CurrentUser DPAPI, private ACL, profile decryption and key rotation", () => {
	const result = run(`
${selectionPrelude(defaultAnswers)}
$path = Join-Path $work 'private\\api-key.dpapi'
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$first = 'test-key-one-not-a-real-credential'
$second = 'test-key-two-not-a-real-credential'
$key = ConvertTo-SecureString $first -AsPlainText -Force
try { Save-LumenKey $key $path } finally { $key.Dispose() }
$cipher = [IO.File]::ReadAllBytes($path)
$block = New-LumenProfileBlock $path $sid 'https://lumen.example' $selection $work
Set-Alias -Name codex -Value Get-Date -Scope Global -Option ReadOnly
$output = & { & { & ([scriptblock]::Create($block)) } } 3>&1 | Out-String
$immediateFunction = (Get-Command codex).CommandType -eq 'Function' -and -not (Get-Alias codex -Scope Global -ErrorAction SilentlyContinue)
$firstLoaded = $env:LUMEN_API_KEY -ceq $first -and $env:ANTHROPIC_AUTH_TOKEN -ceq $first
$key = ConvertTo-SecureString $second -AsPlainText -Force
try { Save-LumenKey $key $path } finally { $key.Dispose() }
Remove-Item Function:codex -Force
Set-Alias -Name codex -Value Get-Date -Scope Global
. ([scriptblock]::Create($block))
$startupFunction = (Get-Command codex).CommandType -eq 'Function' -and -not (Get-Alias codex -ErrorAction SilentlyContinue)
$secondLoaded = $env:LUMEN_API_KEY -ceq $second -and $env:ANTHROPIC_AUTH_TOKEN -ceq $second
$acl = Get-Acl -LiteralPath $path
$directoryAcl = Get-Acl -LiteralPath ([IO.Path]::GetDirectoryName($path))
$private = $acl.AreAccessRulesProtected -and $directoryAcl.AreAccessRulesProtected
foreach ($rule in @($acl.Access) + @($directoryAcl.Access)) {
 if ($rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -ne $sid) { $private = $false }
}
$invalidKey = ConvertTo-SecureString 'bad key' -AsPlainText -Force
$beforeInvalid = [Convert]::ToBase64String([IO.File]::ReadAllBytes($path))
$invalidRejected = $false
try { Save-LumenKey $invalidKey $path } catch { $invalidRejected = $true } finally { $invalidKey.Dispose() }
$afterInvalid = [Convert]::ToBase64String([IO.File]::ReadAllBytes($path))
$roles = @{ fable = $env:ANTHROPIC_DEFAULT_FABLE_MODEL; opus = $env:ANTHROPIC_DEFAULT_OPUS_MODEL; sonnet = $env:ANTHROPIC_DEFAULT_SONNET_MODEL; haiku = $env:ANTHROPIC_DEFAULT_HAIKU_MODEL; startup = $env:ANTHROPIC_MODEL }
# Rerender the marker with a different assignment and load it in a genuinely
# fresh PowerShell process. CurrentUser DPAPI is real; all paths are under work.
$changedSelection = [pscustomobject] @{ Roles = [ordered] @{ Sol = $rows[2]; Luna = $rows[0]; Fable = $rows[3]; Opus = $rows[0]; Sonnet = $rows[2]; Haiku = $rows[3] }; StartupRole = 'haiku' }
$installedProfile = Join-Path $work 'installed-profile.ps1'
Write-LumenFile $installedProfile (Update-LumenProfile '# harmless test profile' $block) $true
$changedBlock = New-LumenProfileBlock $path $sid 'https://lumen.example' $changedSelection $work
Write-LumenFile $installedProfile (Update-LumenProfile (Read-LumenTextFile $installedProfile $true) $changedBlock) $true
$probe = Join-Path $work 'fresh-shell.ps1'
$probeText = @'
param([string] $ProfilePath)
$ErrorActionPreference = 'Stop'
. $ProfilePath
@{ fable = $env:ANTHROPIC_DEFAULT_FABLE_MODEL; opus = $env:ANTHROPIC_DEFAULT_OPUS_MODEL; sonnet = $env:ANTHROPIC_DEFAULT_SONNET_MODEL; haiku = $env:ANTHROPIC_DEFAULT_HAIKU_MODEL; startup = $env:ANTHROPIC_MODEL; keyLoaded = [bool] $env:LUMEN_API_KEY; wrapper = (Get-Command codex).CommandType.ToString() } | ConvertTo-Json -Compress
'@
Write-LumenFile $probe $probeText $true
$engine = (Get-Process -Id $PID).Path
$freshText = (& $engine -NoLogo -NoProfile -NonInteractive -File $probe -ProfilePath $installedProfile) -join "\n"
if ($LASTEXITCODE -ne 0) { throw 'Fresh Windows shell failed to load its generated profile.' }
$fresh = ConvertFrom-Json $freshText
$foreign = New-LumenProfileBlock $path 'S-1-5-21-0-0-0-9999' 'https://lumen.example' $selection $work
$warning = & ([scriptblock]::Create($foreign)) 3>&1 | Out-String
@{ firstLoaded = $firstLoaded; secondLoaded = $secondLoaded; private = $private; plaintextPersisted = ([Text.Encoding]::UTF8.GetString($cipher).Contains($first)); leaked = ($output.Contains($first) -or $warning.Contains($second) -or $block.Contains($first)); foreignCleared = (-not $env:LUMEN_API_KEY -and -not $env:ANTHROPIC_AUTH_TOKEN); roles = $roles; fresh = $fresh; homeMatches = ($env:CODEX_HOME -ceq $work); invalidRejected = $invalidRejected; invalidUnchanged = ($beforeInvalid -ceq $afterInvalid); immediateFunction = $immediateFunction; startupFunction = $startupFunction } | ConvertTo-Json -Compress
`);
	assert.equal(result.firstLoaded, true);
	assert.equal(result.secondLoaded, true);
	assert.equal(result.private, true);
	assert.equal(result.plaintextPersisted, false);
	assert.equal(result.leaked, false);
	assert.equal(result.foreignCleared, true);
	assert.deepEqual(result.roles, { fable: "lumen/4/22", opus: "lumen/3/21", sonnet: "lumen/7/11", haiku: "lumen/4/22", startup: "opus" });
	assert.deepEqual(result.fresh, { fable: "lumen/4/22", opus: "lumen/7/11", sonnet: "lumen/3/21", haiku: "lumen/4/22", startup: "haiku", keyLoaded: true, wrapper: "Function" });
	assert.equal(result.homeMatches, true);
	assert.equal(result.invalidRejected, true);
	assert.equal(result.invalidUnchanged, true);
	assert.equal(result.immediateFunction, true);
	assert.equal(result.startupFunction, true);
}, { skip: process.platform !== "win32" ? "Windows DPAPI CurrentUser and Windows ACL execution unavailable on this host; no insecure emulation is used" : false });

behavior("installer preflights every native destination before requesting or persisting a credential", () => {
	const result = run(`
$env:CODEX_HOME = Join-Path $work 'codex'
$env:LUMEN_CODEX_BASE_URL = 'https://lumen.example/v1'
$env:LUMEN_ANTHROPIC_BASE_URL = 'https://lumen.example'
[void] [IO.Directory]::CreateDirectory($env:CODEX_HOME)
$configPath = Join-Path $env:CODEX_HOME 'config.toml'
$cliConfigPath = Join-Path $env:CODEX_HOME 'lumen-cli.config.toml'
$solConfigPath = Join-Path $env:CODEX_HOME 'lumen-sol.config.toml'
$lunaConfigPath = Join-Path $env:CODEX_HOME 'lumen-luna.config.toml'
$catalogPath = Join-Path $env:CODEX_HOME 'lumen-models.json'
$profilePath = Join-Path $work 'profile.ps1'
$PROFILE = [pscustomobject] @{ CurrentUserAllHosts = $profilePath }
$installAst = $ast.Find({ param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Invoke-LumenInstall' }, $true)
$statements = @()
foreach ($statement in $installAst.Body.EndBlock.Statements) {
 if ($statement.Extent.Text -match '^\\$key = Read-Host') { break }
 $statements += $statement.Extent.Text
}
# Run the real installer preflight, stopping at the secure prompt. No storage,
# path-check or parser substitute can hide an unsafe native config destination.
$preflight = [scriptblock]::Create($statements -join "\n")
$script:secretPrompted = $false
$script:publicPrompted = $false
function Read-Host {
 param([string] $Prompt, [switch] $AsSecureString)
 if ($AsSecureString) { $script:secretPrompted = $true; throw 'Unexpected secure prompt' }
 $script:publicPrompted = $true; throw 'Unexpected prompt before the key'
}
$all = @($configPath, $cliConfigPath, $solConfigPath, $lunaConfigPath, $catalogPath, $profilePath)
function Get-LumenKeyPath { Join-Path $work 'synthetic-key.dpapi' }
function Reset-Seeds {
 [IO.File]::WriteAllText($configPath, "model = 'desktop'\nmodel_provider = 'openai'")
 [IO.File]::WriteAllText($cliConfigPath, "model = 'terminal'")
 [IO.File]::WriteAllText($solConfigPath, "model = 'sol'")
 [IO.File]::WriteAllText($lunaConfigPath, "model = 'luna'")
 [IO.File]::WriteAllText($catalogPath, '{"models":[]}')
 [IO.File]::WriteAllText($profilePath, '# user profile')
}
$failures = @()
foreach ($target in @($configPath, $cliConfigPath, $solConfigPath, $lunaConfigPath)) {
 foreach ($invalid in @("model = 'a'\nmodel = 'b'", "[model_providers.$(if ($target -eq $configPath) { 'lumen' } else { 'lumen-cli' })]\nbase_url = 'a'\nbase_url = 'b'")) {
  Reset-Seeds
  [IO.File]::WriteAllText($target, $invalid)
  $before = $all | ForEach-Object { [Convert]::ToBase64String([IO.File]::ReadAllBytes($_)) }
  $failed = $false
  try { & $preflight *> $null } catch { $failed = $true }
  $after = $all | ForEach-Object { [Convert]::ToBase64String([IO.File]::ReadAllBytes($_)) }
  $failures += $failed -and ($before -join '|') -ceq ($after -join '|')
 }
}
Reset-Seeds
[IO.File]::WriteAllBytes($catalogPath, [byte[]] @(123, 233, 125))
$encodingRejected = $false
try { & $preflight *> $null } catch { $encodingRejected = $_.Exception.Message -like '*Unsupported config/profile encoding*' }
Reset-Seeds
[IO.File]::WriteAllText($profilePath, "# >>> Lumen CLI >>>\n")
$markerRejected = $false
try { & $preflight *> $null } catch { $markerRejected = $_.Exception.Message -like '*Ambiguous Lumen profile markers*' }
Reset-Seeds
$directoryResults = foreach ($target in @($cliConfigPath, $solConfigPath, $lunaConfigPath, $catalogPath)) {
 Remove-Item -LiteralPath $target
 [void] [IO.Directory]::CreateDirectory($target)
 $rejected = $false
 try { & $preflight *> $null } catch { $rejected = $_.Exception.Message -like '*must be files or absent*' }
 [IO.Directory]::Delete($target)
 [IO.File]::WriteAllText($target, 'x')
 $rejected
}
Reset-Seeds
$before = $all | ForEach-Object { [Convert]::ToBase64String([IO.File]::ReadAllBytes($_)) }
$env:ANTHROPIC_CUSTOM_HEADERS = "X-Team: keep\n x-lumen-provider : openai"
$selectorRejected = $false
try { & $preflight *> $null } catch { $selectorRejected = $_.Exception.Message -like 'ANTHROPIC_CUSTOM_HEADERS sets X-Lumen-Provider*' }
$after = $all | ForEach-Object { [Convert]::ToBase64String([IO.File]::ReadAllBytes($_)) }
$selectorUnchanged = ($before -join '|') -ceq ($after -join '|')
Remove-Item Env:ANTHROPIC_CUSTOM_HEADERS
Remove-Item -LiteralPath $cliConfigPath
$linkedDirectory = Join-Path $work 'linked-config.toml'
[void] [IO.Directory]::CreateDirectory($linkedDirectory)
$null = New-Item -ItemType Junction -Path $cliConfigPath -Target $linkedDirectory
$linkRejected = $false
try { & $preflight *> $null } catch { $linkRejected = $true }
@{ failures = $failures; secretPrompted = $script:secretPrompted; publicPrompted = $script:publicPrompted; encodingRejected = $encodingRejected; markerRejected = $markerRejected; linkRejected = $linkRejected; selectorRejected = $selectorRejected; selectorUnchanged = $selectorUnchanged; directoryResults = @($directoryResults); backups = @(Get-ChildItem -LiteralPath $work -Recurse -Filter '*.bak').Count } | ConvertTo-Json -Compress
`);
	assert.equal(result.failures.length, 8);
	assert.ok(result.failures.every(Boolean));
	assert.equal(result.secretPrompted, false);
	assert.equal(result.publicPrompted, false);
	assert.equal(result.encodingRejected, true);
	assert.equal(result.markerRejected, true);
	assert.equal(result.linkRejected, true);
	assert.equal(result.selectorRejected, true);
	assert.equal(result.selectorUnchanged, true);
	assert.deepEqual(result.directoryResults, [true, true, true, true]);
	assert.equal(result.backups, 0);
}, { skip: process.platform !== "win32" ? "Real Windows installer preflight requires Windows; no Windows API emulation" : false });
