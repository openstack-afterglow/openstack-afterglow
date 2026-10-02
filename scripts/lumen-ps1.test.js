const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

function runtimeEnvironment(home) {
	const env = {};
	for (const name of ["PATH", "Path", "SystemRoot", "SYSTEMROOT", "WINDIR", "windir", "COMSPEC", "ComSpec", "PATHEXT", "LANG", "LC_ALL", "LC_CTYPE", "PSModulePath"]) {
		if (process.env[name] !== undefined) env[name] = process.env[name];
	}
	return { ...env, HOME: home, USERPROFILE: home, APPDATA: home, LOCALAPPDATA: home, TEMP: home, TMP: home,
		POWERSHELL_TELEMETRY_OPTOUT: "1", DOTNET_CLI_TELEMETRY_OPTOUT: "1" };
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

function run(code, { definitions = true } = {}) {
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
	const env = runtimeEnvironment(dir);
	try {
		const result = spawnSync(pwsh, ["-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", script], { encoding: "utf8", env, timeout: 60000 });
		assert.equal(result.status, 0, result.error ? String(result.error) : result.stderr + result.stdout);
		return JSON.parse(result.stdout.trim());
	} finally {
		fs.rmSync(dir, { recursive: true, force: true });
	}
}

function behavior(name, fn, options = {}) {
	test(name, { skip: missingRuntime || options.skip || false }, fn);
}

behavior("HTTPS bases and public model IDs reject unsafe or ambiguous input", () => {
	const result = run(`
$badUrls = @('http://example.com/v1', 'https://user:password@example.com', 'https://example.com?key=x', 'https://example.com#x', 'https://example.com/?', 'https://example.com/#', 'https://example.com/%0a', 'https://example.com/%7F', ' https://example.com', "https://example.com/\", 'https://example.com\\evil', 'not a URL')
$rejected = foreach ($value in $badUrls) { try { $null = ConvertTo-LumenBaseUrl $value; $false } catch { $true } }
$badModels = @('', '-flag', 'a b', 'a;whoami', 'a"b', ('a' * 201))
$modelRejected = foreach ($value in $badModels) { try { $null = ConvertTo-LumenModel $value; $false } catch { $true } }
@{ rejected = @($rejected); modelRejected = @($modelRejected); url = (ConvertTo-LumenBaseUrl 'https://EXAMPLE.com:443/v1/'); model = (ConvertTo-LumenModel 'public/model:1.2') } | ConvertTo-Json -Compress
`);
	assert.ok(result.rejected.every(Boolean));
	assert.ok(result.modelRejected.every(Boolean));
	assert.equal(result.url, "https://example.com/v1");
	assert.equal(result.model, "public/model:1.2");
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

behavior("opt-in updates only root model and never changes or inserts the default provider", () => {
	const result = run(`
$original = "model = 'old'\nmodel_provider = 'openai'\n[profiles.work]\nmodel = 'work'"
$changed = Update-LumenToml $original 'https://lumen.example/v1' 'responses/public'
$empty = Update-LumenToml '' 'https://lumen.example/v1' 'responses/public'
$only = Update-LumenToml '# comment without newline' 'https://lumen.example/v1' 'responses/public'
@{ changed = $changed; empty = $empty; only = $only; again = (Update-LumenToml $changed 'https://lumen.example/v1' 'responses/public') } | ConvertTo-Json -Compress
`);
	for (const value of [result.changed, result.empty, result.only]) {
		assert.ok(value.indexOf('model = "responses/public"') < value.indexOf("[model_providers.lumen]"));
	}
	assert.ok(result.changed.includes("model_provider = 'openai'"));
	assert.ok(!result.empty.includes("model_provider ="));
	assert.ok(!result.only.includes("model_provider ="));
	assert.ok(result.changed.includes("[profiles.work]\nmodel = 'work'"));
	assert.equal(result.again, result.changed);
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
 'model_providers = { lumen = { name = "x" } }',
 'model_providers.lumen.name = "x"',
 "[model_providers]\nlumen = { name = 'x' }",
 "[model_providers.lumen]\nbase_url = 'a'\nbase_url = 'b'",
 "[model_providers.lumen]\n[model_providers.lumen]",
 "[[model_providers.lumen]]\nname = 'x'",
 "[model_providers.lumen.base_url]\nx = 'y'",
 'value = [1, 2',
 'value = "unterminated'
)
$rejected = foreach ($value in $bad) { try { $null = Update-LumenToml $value 'https://lumen.example/v1'; $false } catch { $true } }
@($rejected) | ConvertTo-Json -Compress
`);
	assert.ok(result.every(Boolean));
});

behavior("profile marker replacement is idempotent and escaping cannot execute injected path text", () => {
	const result = run(`
$hostile = "C:\\Users\\O'Brien\\" + '$(__MODEL__);' + [char]96 + "\\secret.dpapi"
$block = New-LumenProfileBlock $hostile 'S-1-5-21-test' 'https://lumen.example' 'public/model' 'responses/public' $work
$prefix = "# existing Unicode: café\nfunction User-Tool { 'unchanged' }\n"
$suffix = "# after Lumen\nSet-Alias user-tool User-Tool\n"
$profileText = Update-LumenProfile $prefix $block
$combined = $profileText + $suffix
$again = Update-LumenProfile $combined $block
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseInput($block, [ref] $tokens, [ref] $errors)
if ($errors.Count) { throw ($errors | Out-String) }
$pathConstants = @($ast.FindAll({ param($n) $n -is [Management.Automation.Language.StringConstantExpressionAst] -and $n.Value -ceq $hostile }, $true))
$bad = @('# >>> Lumen CLI >>>', '# <<< Lumen CLI <<<', "# <<< Lumen CLI <<<\n# >>> Lumen CLI >>>", ($block + "\n" + $block))
$rejected = foreach ($value in $bad) { try { $null = Update-LumenProfile $value $block; $false } catch { $true } }
@{ combined = $combined; again = $again; prefix = $prefix; suffix = $suffix; literalPath = ($pathConstants.Count -eq 1); rejected = @($rejected) } | ConvertTo-Json -Compress
`);
	assert.equal(result.again, result.combined);
	assert.ok(result.again.startsWith(result.prefix));
	assert.ok(result.again.endsWith(result.suffix));
	assert.equal(result.literalPath, true);
	assert.ok(result.rejected.every(Boolean));
});

behavior("changed files get exact backups; identical reruns make no additional backups", () => {
	const result = run(`
$p = Join-Path $work 'profile.ps1'
$original = "# café\r\nfunction Existing { 'ok' }\r\n"
[IO.File]::WriteAllText($p, $original, (New-Object Text.UTF8Encoding($true)))
$oldBytes = [Convert]::ToBase64String([IO.File]::ReadAllBytes($p))
$changed = Update-LumenProfile $original (New-LumenProfileBlock 'C:\\private\\api-key.dpapi' 'S-1-5-test' 'https://lumen.example' 'public-model' 'responses/public' $work)
Write-LumenFile $p $changed $true
Write-LumenFile $p $changed $true
$backups = @(Get-ChildItem -LiteralPath $work -Filter '*.bak')
@{ content = [IO.File]::ReadAllText($p); expected = $changed; count = $backups.Count; before = $oldBytes; backup = [Convert]::ToBase64String([IO.File]::ReadAllBytes($backups[0].FullName)) } | ConvertTo-Json -Compress
`);
	assert.equal(result.content, result.expected);
	assert.equal(result.count, 1);
	assert.equal(result.backup, result.before);
});

behavior("legacy encodings fail without rewriting while UTF-8 BOM and Unicode round-trip", () => {
	const result = run(`
$p = Join-Path $work 'profile.ps1'
$unicode = "# café 日本語\n"
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
$profilePath = Join-Path $work 'legacy-profile.ps1'
$configPath = Join-Path $work 'config.toml'
$original = "# café 日本語\r\nfunction Existing { 'ok' }\r\n"
[IO.File]::WriteAllText($profilePath, $original, [Text.Encoding]::Unicode)
[IO.File]::WriteAllText($configPath, $original, [Text.Encoding]::Unicode)
$before = [Convert]::ToBase64String([IO.File]::ReadAllBytes($profilePath))
$loaded = Read-LumenTextFile $profilePath $true
$newProfile = Update-LumenProfile $loaded (New-LumenProfileBlock 'C:\\private\\key.dpapi' 'S-1-5-test' 'https://lumen.example' 'public-model' 'responses/public' $work)
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

behavior("actual Windows CurrentUser DPAPI, private ACL, profile decryption and key rotation", () => {
	const result = run(`
$path = Join-Path $work 'private\\api-key.dpapi'
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$first = 'test-key-one-not-a-real-credential'
$second = 'test-key-two-not-a-real-credential'
$key = ConvertTo-SecureString $first -AsPlainText -Force
try { Save-LumenKey $key $path } finally { $key.Dispose() }
$cipher = [IO.File]::ReadAllBytes($path)
$block = New-LumenProfileBlock $path $sid 'https://lumen.example' 'public/model' 'responses/public' $work
$output = & ([scriptblock]::Create($block)) 3>&1 | Out-String
$firstLoaded = $env:LUMEN_API_KEY -ceq $first -and $env:ANTHROPIC_AUTH_TOKEN -ceq $first
$key = ConvertTo-SecureString $second -AsPlainText -Force
try { Save-LumenKey $key $path } finally { $key.Dispose() }
& ([scriptblock]::Create($block))
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
$foreign = New-LumenProfileBlock $path 'S-1-5-21-0-0-0-9999' 'https://lumen.example' 'public/model' 'responses/public' $work
$warning = & ([scriptblock]::Create($foreign)) 3>&1 | Out-String
@{ firstLoaded = $firstLoaded; secondLoaded = $secondLoaded; private = $private; plaintextPersisted = ([Text.Encoding]::UTF8.GetString($cipher).Contains($first)); leaked = ($output.Contains($first) -or $warning.Contains($second) -or $block.Contains($first)); foreignCleared = (-not $env:LUMEN_API_KEY -and -not $env:ANTHROPIC_AUTH_TOKEN); model = $env:ANTHROPIC_MODEL; codexModel = $env:LUMEN_CODEX_MODEL; homeMatches = ($env:CODEX_HOME -ceq $work); invalidRejected = $invalidRejected; invalidUnchanged = ($beforeInvalid -ceq $afterInvalid) } | ConvertTo-Json -Compress
`);
	assert.equal(result.firstLoaded, true);
	assert.equal(result.secondLoaded, true);
	assert.equal(result.private, true);
	assert.equal(result.plaintextPersisted, false);
	assert.equal(result.leaked, false);
	assert.equal(result.foreignCleared, true);
	assert.equal(result.model, "public/model");
	assert.equal(result.codexModel, "responses/public");
	assert.equal(result.homeMatches, true);
	assert.equal(result.invalidRejected, true);
	assert.equal(result.invalidUnchanged, true);
}, { skip: process.platform !== "win32" ? "Windows DPAPI CurrentUser and Windows ACL execution unavailable on this host; no insecure emulation is used" : false });
