# Lumen Windows setup: paste only public base URLs into the invoking command.
# The API key is prompted privately, sent only as the HTTPS Authorization header
# of GET <Codex base>/cli/models (Windows certificate verification, no redirects),
# encrypted with Windows DPAPI CurrentUser after every file is prepared, and
# decrypted only by this user's PowerShell profile into process environment.
# Environment credentials are inherited by child processes; do not dump env or
# enable PowerShell tracing/debug logging while entering or using credentials.
# The server catalog is shown by provider; Codex Sol/Luna and Claude Code
# Fable/Opus/Sonnet/Haiku each receive an independently selected route ID.
# Native Codex profiles lumen-cli (Sol), lumen-sol and lumen-luna hold
# terminal-only root selections plus the selected lumen-models.json catalog.
# Desktop root defaults change only on explicit opt-in. Changed configs, the
# catalog and the profile receive timestamped .bak copies; a failed write
# restores every file of this run. TOML/JSON must be valid UTF-8. Profiles
# accept UTF-8 or BOM-marked UTF-16; ambiguous legacy encodings are refused
# without rewriting. Backups retain bytes.
& {
    $ErrorActionPreference = 'Stop'
    function Assert-LumenWindows {
        if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
            throw 'Lumen secure persistence requires Windows DPAPI CurrentUser. No files were changed; no plaintext fallback is available.'
        }
        Add-Type -AssemblyName System.Security -ErrorAction Stop
    }

    function ConvertTo-LumenBaseUrl([string] $Value) {
        $uri = $null
        if ([string]::IsNullOrWhiteSpace($Value) -or $Value -match '[\s\x00-\x1f\x7f\\]' -or
            $Value -match '(?i)%(?:0[0-9a-f]|1[0-9a-f]|7f)' -or
            -not [Uri]::TryCreate($Value, [UriKind]::Absolute, [ref] $uri) -or
            $uri.Scheme -ne 'https' -or -not $uri.Host -or $uri.UserInfo -or
            $Value.Contains('?') -or $Value.Contains('#')) {
            throw 'Enter an absolute HTTPS base URL without credentials, query, fragment, whitespace, or control characters.'
        }
        return $uri.AbsoluteUri.TrimEnd('/')
    }

    # Real public model ID, used only for the desktop model-only opt-in.
    function ConvertTo-LumenModel([string] $Value) {
        if ($Value -cnotmatch '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}\z') {
            throw 'A public model ID uses letters, digits, dot, underscore, colon, slash or hyphen (at most 200 characters).'
        }
        return $Value
    }

    # Opaque catalog route: exactly one active Lumen provider/model.
    function ConvertTo-LumenRouteId([string] $Value) {
        if ($Value -cnotmatch '^lumen/[1-9][0-9]{0,17}/[1-9][0-9]{0,17}\z') {
            throw 'Model selections must be Lumen catalog route IDs (lumen/<provider>/<model>).'
        }
        return $Value
    }

    # Server-supplied names reach the terminal, TOML, JSON and profile literals.
    # Remove control/format characters (including bidi overrides) and bound length.
    function ConvertTo-LumenDisplayText($Value, [int] $Limit = 160) {
        $text = [regex]::Replace([string] $Value, '[\p{Cc}\p{Cf}\p{Zl}\p{Zp}]', ' ')
        $text = [regex]::Replace($text, '\s+', ' ').Trim()
        if ($text.Length -gt $Limit) {
            $cut = $Limit - 3
            if ([char]::IsHighSurrogate($text[$cut - 1])) { $cut-- }
            $text = $text.Substring(0, $cut).TrimEnd() + '...'
        }
        return $text
    }

    function ConvertTo-LumenPsLiteral([string] $Value) {
        if ($Value -match '[\x00-\x1f\x7f]') { throw 'Paths and profile values must not contain control characters.' }
        return "'" + $Value.Replace("'", "''") + "'"
    }

    function ConvertTo-LumenTomlString([string] $Value) {
        $result = '"'
        foreach ($c in $Value.ToCharArray()) {
            switch ([int] $c) {
                34 { $result += '\"' }
                92 { $result += '\\' }
                default {
                    if ([int] $c -lt 32 -or [int] $c -eq 127) { $result += ('\u{0:x4}' -f [int] $c) }
                    else { $result += $c }
                }
            }
        }
        return $result + '"'
    }

    # Identify complete TOML statements, not apparent headers inside multiline
    # strings/arrays. Refuse ambiguous input before making any persistent change.
    function Get-LumenTomlStatements([string] $Text) {
        $start = 0; $depth = 0; $quote = ''; $triple = $false; $comment = $false
        for ($i = 0; $i -lt $Text.Length; $i++) {
            $c = $Text[$i]
            if ($comment) {
                if ($c -ne "`n") { continue }
                $comment = $false
            } elseif ($quote) {
                if ($quote -eq '"' -and $c -eq '\') { $i++; continue }
                if ($c -eq $quote) {
                    if (-not $triple) { $quote = '' }
                    elseif ($i + 2 -lt $Text.Length -and $Text.Substring($i, 3) -eq ($quote * 3)) {
                        # TOML permits one or two additional quotes at a multiline close.
                        $i += 2
                        while ($i + 1 -lt $Text.Length -and $Text[$i + 1] -eq $quote) { $i++ }
                        $quote = ''; $triple = $false
                    }
                } elseif (-not $triple -and $c -eq "`n") { throw 'Invalid TOML string; config was not changed.' }
                continue
            } elseif ($c -eq '#') { $comment = $true; continue }
            elseif ($c -eq '"' -or $c -eq "'") {
                $quote = [string] $c
                $triple = $i + 2 -lt $Text.Length -and $Text.Substring($i, 3) -eq ($quote * 3)
                if ($triple) { $i += 2 }
                continue
            } elseif ($c -eq '[' -or $c -eq '{') { $depth++ }
            elseif ($c -eq ']' -or $c -eq '}') { $depth--; if ($depth -lt 0) { throw 'Unbalanced TOML; config was not changed.' } }
            if ($c -eq "`n" -and $depth -eq 0) {
                [pscustomobject] @{ Start = $start; Length = $i + 1 - $start; Text = $Text.Substring($start, $i + 1 - $start) }
                $start = $i + 1
            }
        }
        if ($quote -or $depth -ne 0) { throw 'Unterminated TOML string or collection; config was not changed.' }
        if ($start -lt $Text.Length) {
            [pscustomobject] @{ Start = $start; Length = $Text.Length - $start; Text = $Text.Substring($start) }
        }
    }

    function Get-LumenTomlPath([string] $Text) {
        $parts = @(); $rest = $Text.Trim()
        while ($rest) {
            $m = [regex]::Match($rest, '^(?:([A-Za-z0-9_-]+)|''([^'']*)''|"((?:[^"\\]|\\.)*)")\s*(\.|$)')
            if (-not $m.Success) { throw 'Unsupported TOML key syntax; config was not changed.' }
            if ($m.Groups[1].Success) { $parts += $m.Groups[1].Value }
            elseif ($m.Groups[2].Success) { $parts += $m.Groups[2].Value }
            else {
                # JSON and TOML share these key escapes. Reject TOML-only \U keys
                # rather than misidentifying a provider and corrupting its tables.
                try { $parts += (ConvertFrom-Json ('"' + $m.Groups[3].Value + '"') -ErrorAction Stop) }
                catch { throw 'Unsupported escaped TOML key; config was not changed.' }
            }
            $rest = $rest.Substring($m.Length).Trim()
            if ($m.Groups[4].Value -eq '.' -and -not $rest) { throw 'Invalid dotted TOML key; config was not changed.' }
        }
        return ,$parts
    }

    function Test-LumenProviderSection($Parts, [string] $Provider = 'lumen') {
        return $Parts.Count -eq 2 -and $Parts[0] -ceq 'model_providers' -and $Parts[1] -ceq $Provider
    }

    function Update-LumenToml([string] $Text, [string] $BaseUrl, [string] $DefaultModel = '', [bool] $CliProfile = $false, [string] $CatalogPath = '') {
        $BaseUrl = ConvertTo-LumenBaseUrl $BaseUrl
        if ($CliProfile) { $DefaultModel = ConvertTo-LumenRouteId $DefaultModel }
        elseif ($DefaultModel) { $DefaultModel = ConvertTo-LumenModel $DefaultModel }
        if ($CliProfile -and -not ($CatalogPath -and [IO.Path]::IsPathRooted($CatalogPath))) {
            throw 'A native Lumen profile requires an absolute model catalog path; config was not changed.'
        }
        $nl = "`n"; if ($Text.Contains("`r`n")) { $nl = "`r`n" }
        # CLI profiles layer over desktop config; a distinct provider prevents
        # desktop lumen headers from constraining independently selected routes.
        $provider = 'lumen'; if ($CliProfile) { $provider = 'lumen-cli' }
        $fields = [ordered] @{
            name = '"Lumen Responses"'; base_url = (ConvertTo-LumenTomlString $BaseUrl)
            env_key = '"LUMEN_API_KEY"'; wire_api = '"responses"'; requires_openai_auth = 'false'; supports_websockets = 'false'
        }
        # A native <profile>.config.toml file uses root selections, not a
        # [profiles.<name>] table. Never apply its provider selection to config.toml.
        $rootFields = [ordered] @{}
        if ($DefaultModel) { $rootFields['model'] = ConvertTo-LumenTomlString $DefaultModel }
        if ($CliProfile) {
            $rootFields['model_provider'] = '"lumen-cli"'
            $rootFields['model_catalog_json'] = ConvertTo-LumenTomlString $CatalogPath
        }
        $rootKeys = @('model', 'model_provider', 'model_catalog_json')
        $section = @(); $edits = @(); $seen = @{}; $rootSeen = @{}
        $rootEnd = $Text.Length; $providerEnd = $Text.Length; $providerFound = $false
        foreach ($statement in @(Get-LumenTomlStatements $Text)) {
            $s = $statement.Text.Trim()
            if (-not $s -or $s.StartsWith('#')) { continue }
            if ($s.StartsWith('[')) {
                $m = [regex]::Match($s, '^\[([^\[\]]+)\]\s*(?:#.*)?$')
                $array = [regex]::Match($s, '^\[\[([^\[\]]+)\]\]\s*(?:#.*)?$')
                if (-not $m.Success -and -not $array.Success) { throw 'Unsupported TOML table syntax; config was not changed.' }
                if ($section.Count -eq 0) { $rootEnd = [Math]::Min($rootEnd, $statement.Start) }
                if (Test-LumenProviderSection $section $provider) { $providerEnd = $statement.Start }
                $header = $m; if ($array.Success) { $header = $array }
                $section = Get-LumenTomlPath $header.Groups[1].Value
                if ($section[0] -cin $rootKeys) { throw 'A Codex root selection is defined as a table; config was not changed.' }
                if ($array.Success -and $section.Count -eq 1 -and $section[0] -ceq 'model_providers') {
                    throw 'Array model_providers configuration needs manual migration to tables; config was not changed.'
                }
                if (Test-LumenProviderSection $section $provider) {
                    if ($array.Success -or $providerFound) { throw 'Duplicate or array Lumen provider table; config was not changed.' }
                    $providerFound = $true
                }
                if ($section.Count -gt 2 -and $section[0] -ceq 'model_providers' -and $section[1] -ceq $provider -and $fields.Keys -ccontains $section[2]) {
                    throw 'A managed Lumen provider field is defined as a table; config was not changed.'
                }
                continue
            }
            $assignment = [regex]::Match($s, '^((?:[^="'']|"(?:[^"\\]|\\.)*"|''[^'']*'')+)\s*=')
            if (-not $assignment.Success) { throw 'Unsupported TOML assignment; config was not changed.' }
            $key = Get-LumenTomlPath $assignment.Groups[1].Value
            if (($section.Count -eq 0 -and $key[0] -ceq 'model_providers') -or
                ($section.Count -eq 1 -and $section[0] -ceq 'model_providers' -and $key[0] -ceq $provider)) {
                throw 'Inline/dotted model_providers configuration needs manual migration to tables; config was not changed.'
            }
            # Route IDs select one provider per model. A fixed legacy provider
            # header in a managed native profile would break /model switching
            # across providers, so remove only that header there.
            if ($CliProfile -and (Test-LumenProviderSection $section $provider) -and $key[0] -cin @('http_headers', 'env_http_headers') -and $key.Count -eq 1 -and
                $statement.Text -match '(?i)x-lumen-provider') {
                throw 'An inline Lumen CLI header table sets X-Lumen-Provider; move it to [model_providers.lumen-cli.http_headers] or [model_providers.lumen-cli.env_http_headers] so setup can remove it. Config was not changed.'
            }
            if ($CliProfile -and ((($section.Count -eq 3 -and (Test-LumenProviderSection $section[0..1] $provider) -and $section[2] -cin @('http_headers', 'env_http_headers') -and
                    $key.Count -eq 1 -and $key[0] -ieq 'X-Lumen-Provider')) -or
                ((Test-LumenProviderSection $section $provider) -and $key.Count -eq 2 -and $key[0] -cin @('http_headers', 'env_http_headers') -and $key[1] -ieq 'X-Lumen-Provider'))) {
                $edits += [pscustomobject] @{ Start = $statement.Start; Length = $statement.Length; Value = ''; Order = 0 }
                continue
            }
            $replacement = $null
            if ($section.Count -eq 0 -and $key[0] -cin $rootKeys) {
                if ($key.Count -ne 1 -or $rootSeen.ContainsKey($key[0])) { throw 'Conflicting Codex root selection; config was not changed.' }
                $rootSeen[$key[0]] = $true
                if ($rootFields.Keys -ccontains $key[0]) { $replacement = $key[0] + ' = ' + $rootFields[$key[0]] + $nl }
            }
            if ((Test-LumenProviderSection $section $provider) -and $fields.Keys -ccontains $key[0]) {
                if ($key.Count -ne 1 -or $seen.ContainsKey($key[0])) { throw 'Conflicting Lumen provider key; config was not changed.' }
                $seen[$key[0]] = $true
                $replacement = $key[0] + ' = ' + $fields[$key[0]] + $nl
            }
            if ($null -ne $replacement) {
                $edits += [pscustomobject] @{ Start = $statement.Start; Length = $statement.Length; Value = $replacement; Order = 0 }
            }
        }
        $rootInsert = ''
        foreach ($key in $rootFields.Keys) {
            if (-not $rootSeen.ContainsKey($key)) { $rootInsert += $key + ' = ' + $rootFields[$key] + $nl }
        }
        $providerInsert = ''
        if (-not $providerFound) { $providerInsert = $nl + '[model_providers.' + $provider + ']' + $nl }
        foreach ($key in $fields.Keys) {
            if (-not $seen.ContainsKey($key)) { $providerInsert += $key + ' = ' + $fields[$key] + $nl }
        }
        if ($providerInsert) {
            if (-not $providerFound) { $providerEnd = $Text.Length }
            if ($providerEnd -gt 0 -and $Text[$providerEnd - 1] -ne "`n") { $providerInsert = $nl + $providerInsert }
            $edits += [pscustomobject] @{ Start = $providerEnd; Length = 0; Value = $providerInsert; Order = 0 }
        }
        if ($rootInsert) {
            if ($rootEnd -gt 0 -and $Text[$rootEnd - 1] -ne "`n") { $rootInsert = $nl + $rootInsert }
            $edits += [pscustomobject] @{ Start = $rootEnd; Length = 0; Value = $rootInsert; Order = 1 }
        }
        # Replacements precede insertions at the same offset; root insertion
        # must precede an appended provider table when starting with an empty file.
        foreach ($edit in @($edits | Sort-Object -Property @{ Expression = 'Start'; Descending = $true }, @{ Expression = 'Length'; Descending = $true }, @{ Expression = 'Order'; Descending = $false })) {
            $Text = $Text.Remove($edit.Start, $edit.Length).Insert($edit.Start, $edit.Value)
        }
        return $Text
    }

    # Prompt order is part of the installer contract: Codex roles, then Claude
    # Code families. Roles are user-assigned positions, not size/quality ratings.
    function Get-LumenRoleSlots {
        foreach ($slot in @(@('Codex', 'Sol', 'responses'), @('Codex', 'Luna', 'responses'), @('Claude', 'Fable', 'messages'),
                @('Claude', 'Opus', 'messages'), @('Claude', 'Sonnet', 'messages'), @('Claude', 'Haiku', 'messages'))) {
            [pscustomobject] @{ Family = $slot[0]; Role = $slot[1]; Protocol = $slot[2] }
        }
    }

    function Get-LumenRoleLabel([string] $Role, $Row) {
        $dot = ' ' + [char] 0x00B7 + ' '
        return $Role + $dot + $Row.ProviderName + $dot + $Row.DisplayName
    }

    function Get-LumenRouteDescription($Row) {
        return $Row.ApiModelName + ' via ' + $Row.ProviderName + ' (' + $Row.ProviderType + '), Lumen route ' + $Row.Id + '. Role chosen at setup, not a size or quality rating.'
    }

    function ConvertTo-LumenStartupRole([string] $Value) {
        $text = ([string] $Value).Trim()
        if (-not $text) { return 'sonnet' }
        if ($text -notmatch '^(?i:fable|opus|sonnet|haiku)\z') {
            throw 'Choose the Claude Code startup role fable, opus, sonnet or haiku; no files were changed.'
        }
        return $text.ToLowerInvariant()
    }

    function New-LumenProfileBlock([string] $KeyPath, [string] $Sid, [string] $BaseUrl, $Selection, [string] $CodexHome, [string] $CaBundle = '') {
        $pathLiteral = ConvertTo-LumenPsLiteral $KeyPath
        $sidLiteral = ConvertTo-LumenPsLiteral $Sid
        $urlLiteral = ConvertTo-LumenPsLiteral (ConvertTo-LumenBaseUrl $BaseUrl)
        $caLiteral = ConvertTo-LumenPsLiteral $CaBundle
        $codexHomeLiteral = ConvertTo-LumenPsLiteral $CodexHome
        # Native Claude Code family aliases: each family keeps its own route and
        # an honest /model label; ANTHROPIC_MODEL only picks the startup family.
        $claude = @()
        foreach ($slot in @(Get-LumenRoleSlots | Where-Object { $_.Family -ceq 'Claude' })) {
            $row = $Selection.Roles[$slot.Role]
            if ($null -eq $row) { throw ('Claude ' + $slot.Role + ' has no selected model; profile was not changed.') }
            $name = '$env:ANTHROPIC_DEFAULT_' + $slot.Role.ToUpperInvariant() + '_MODEL'
            $claude += '        ' + $name + ' = ' + (ConvertTo-LumenPsLiteral (ConvertTo-LumenRouteId $row.Id))
            $claude += '        ' + $name + '_NAME = ' + (ConvertTo-LumenPsLiteral (Get-LumenRoleLabel $slot.Role $row))
            $claude += '        ' + $name + '_DESCRIPTION = ' + (ConvertTo-LumenPsLiteral (Get-LumenRouteDescription $row))
        }
        $claude += '        $env:ANTHROPIC_MODEL = ' + (ConvertTo-LumenPsLiteral (ConvertTo-LumenStartupRole $Selection.StartupRole))
        $claudeLines = $claude -join "`n"
        $template = @'
# >>> Lumen CLI >>>
# Windows DPAPI CurrentUser: this profile never contains a plaintext API key.
& {
    $ErrorActionPreference = 'Stop'
    $bytes = $null
    try {
        if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or
            [Security.Principal.WindowsIdentity]::GetCurrent().User.Value -ne __SID__) {
            throw 'This Lumen credential belongs to a different Windows user/host.'
        }
        Add-Type -AssemblyName System.Security -ErrorAction Stop
        $bytes = [Security.Cryptography.ProtectedData]::Unprotect(
            [IO.File]::ReadAllBytes(__PATH__), $null,
            [Security.Cryptography.DataProtectionScope]::CurrentUser)
        if ($bytes.Length -eq 0 -or $bytes.Length -gt 4096) { throw 'Invalid credential.' }
        foreach ($b in $bytes) { if ($b -lt 33 -or $b -gt 126) { throw 'Invalid credential.' } }
        $env:LUMEN_API_KEY = [Text.Encoding]::UTF8.GetString($bytes)
        $env:ANTHROPIC_AUTH_TOKEN = $env:LUMEN_API_KEY
        Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
        $env:CODEX_HOME = __CODEX_HOME__
        if (__CA__) { $env:CODEX_CA_CERTIFICATE = __CA__ }
        $env:ANTHROPIC_BASE_URL = __URL__
__CLAUDE__
    } catch {
        Remove-Item Env:LUMEN_API_KEY, Env:ANTHROPIC_AUTH_TOKEN -ErrorAction SilentlyContinue
        Write-Warning 'Lumen key could not be decrypted for this Windows user. Rerun the Lumen installer locally; there is no plaintext fallback.'
    } finally {
        if ($null -ne $bytes) { [Array]::Clear($bytes, 0, $bytes.Length) }
    }
}
# Terminal-only selection leaves desktop/user-owned TOML defaults unchanged.
# Remove every visible alias, including inherited/global aliases when setup
# invokes this block in a child scope. PS 5.1 Remove-Item has no -Scope switch;
# Alias:global:codex is not a scope-qualified alias provider path.
while (Get-Alias -Name codex -ErrorAction SilentlyContinue) {
    Remove-Item -LiteralPath Alias:codex -Force -ErrorAction Stop
}
function global:codex {
    $binary = Get-Command codex -CommandType Application,ExternalScript -ErrorAction Stop | Select-Object -First 1
    # PowerShell drops a typed bare -- before calling a function (but keeps a
    # splatted string '--'). Recover only that token from the invocation AST;
    # never re-evaluate caller expressions or reconstruct their argument values.
    $forward = [Collections.ArrayList] @($args)
    if ($MyInvocation.Statement.Contains('--')) {
        $tokens = $null; $parseErrors = $null
        $callAst = [Management.Automation.Language.Parser]::ParseInput($MyInvocation.Statement, [ref] $tokens, [ref] $parseErrors)
        $call = $callAst.Find({ param($node) $node -is [Management.Automation.Language.CommandAst] }, $true)
        if ($null -ne $call -and -not $parseErrors.Count) {
            $elements = $call.CommandElements
            for ($i = 1; $i -lt $elements.Count; $i++) {
                if ($elements[$i] -isnot [Management.Automation.Language.CommandParameterAst] -or $elements[$i].ParameterName -cne '-') { continue }
                $tail = 0
                for ($j = $i + 1; $j -lt $elements.Count; $j++) {
                    $element = $elements[$j]
                    if ($element -is [Management.Automation.Language.VariableExpressionAst] -and $element.Splatted) {
                        # Splatting is a variable lookup, not an expression. Its
                        # caller-scope value determines the number of bound args.
                        $value = Get-Variable -Name $element.VariablePath.UserPath -Scope 1 -ValueOnly -ErrorAction Stop
                        if ($value -is [Collections.IDictionary]) { $tail += 2 * $value.Count }
                        elseif ($value -is [Collections.IEnumerable]) { foreach ($unused in $value.GetEnumerator()) { $tail++ } }
                        else { $tail++ }
                    } else { $tail++ }
                }
                $forward.Insert($forward.Count - $tail, '--')
                break
            }
        }
    }
    # Codex 0.160 root parsing: single-value options consume one token, while
    # images greedily consume non-options (even words that name subcommands).
    # Management commands stay native; debug prompt-input accepts a profile,
    # but rejects strict-config. Never inspect prompt text beyond --.
    $state = 'root'; $returnState = 'root'; $command = ''; $strict = $false; $selected = $false
    foreach ($argument in $forward) {
        $text = [string] $argument
        if ($state -ceq 'value') { $state = $returnState; continue }
        if ($state -ceq 'images') {
            if ($text -cnotmatch '^-.') { continue }
            $state = $returnState
        }
        if ($text -ceq '--') { break }
        if ($text -cmatch '^--strict-config(?:=|\z)') { $strict = $true; continue }
        if ($text -ceq '-p' -or $text -ceq '--profile') {
            $selected = $true
            $returnState = $state; $state = 'value'
            continue
        }
        if ($text -cmatch '^(?:-p.|--profile=)') { $selected = $true; continue }
        if ($text -cmatch '^(?:-i|--image)\z') { $returnState = $state; $state = 'images'; continue }
        if ($text -cmatch '^(?:-[cmsaC]|--(?:config|enable|disable|remote|remote-auth-token-env|model|local-provider|sandbox|ask-for-approval|cd|add-dir))\z') {
            $returnState = $state; $state = 'value'; continue
        }
        if ($text -cmatch '^-.') { continue }
        if ($state -ceq 'debug') { $command = 'debug ' + $text; $state = 'sub'; continue }
        if ($state -cne 'root') { continue }
        $command = $text
        if ($text -ceq 'debug') { $state = 'debug' } else { $state = 'sub' }
    }
    $defaults = @()
    $management = @('login', 'logout', 'mcp', 'plugin', 'app-server', 'remote-control', 'app', 'completion', 'update', 'doctor',
        'sandbox', 'execpolicy', 'apply', 'a', 'migrate-rollouts', 'cloud', 'cloud-tasks', 'responses-api-proxy', 'stdio-to-uds',
        'exec-server', 'features', 'tcp-tunnel', 'help')
    if ($command -ceq 'debug prompt-input') {
        if (-not $selected) { $defaults += @('--profile', 'lumen-cli') }
    } elseif ($management -cnotcontains $command -and $command -cnotmatch '^debug(?: |\z)') {
        if (-not $strict) { $defaults += '--strict-config' }
        if (-not $selected) { $defaults += @('--profile', 'lumen-cli') }
    }
    & $binary.Source @defaults @forward
}
# <<< Lumen CLI <<<
'@
        # Replace tokens in one pass so user paths cannot introduce another token.
        $values = @{ '__PATH__' = $pathLiteral; '__SID__' = $sidLiteral; '__URL__' = $urlLiteral; '__CLAUDE__' = $claudeLines; '__CODEX_HOME__' = $codexHomeLiteral; '__CA__' = $caLiteral }
        return [regex]::Replace($template, '__PATH__|__SID__|__URL__|__CLAUDE__|__CODEX_HOME__|__CA__', [Text.RegularExpressions.MatchEvaluator] { param($m) $values[$m.Value] })
    }

    function Update-LumenProfile([string] $Text, [string] $Block) {
        $begin = [regex]::Matches($Text, '(?m)^# >>> Lumen CLI >>>\r?$')
        $end = [regex]::Matches($Text, '(?m)^# <<< Lumen CLI <<<\r?$')
        if ($begin.Count -ne $end.Count -or $begin.Count -gt 1 -or
            ($begin.Count -eq 1 -and $end[0].Index -lt $begin[0].Index)) {
            throw 'Ambiguous Lumen profile markers; profile was not changed.'
        }
        $nl = "`n"; if ($Text.Contains("`r`n")) { $nl = "`r`n" }
        $Block = $Block.Replace("`r`n", "`n").Replace("`n", $nl).TrimEnd([char[]] "`r`n") + $nl
        if ($begin.Count -eq 1) {
            $stop = $end[0].Index + $end[0].Length
            if ($stop -lt $Text.Length -and $Text[$stop] -eq "`n") { $stop++ }
            return $Text.Substring(0, $begin[0].Index) + $Block + $Text.Substring($stop)
        }
        if ($Text -and -not $Text.EndsWith("`n")) { $Text += $nl }
        return $Text + $Block
    }

    function Assert-LumenLocalPath([string] $Path) {
        if (-not [IO.Path]::IsPathRooted($Path) -or $Path.StartsWith('\\') -or $Path -match '[\x00-\x1f\x7f]') {
            throw 'Setup requires absolute local paths without control characters (no UNC paths).'
        }
        $item = [IO.Path]::GetFullPath($Path)
        while ($item) {
            if (Test-Path -LiteralPath $item) {
                $existing = Get-Item -LiteralPath $item -Force -ErrorAction Stop
                # LinkType identifies symlinks/junctions without rejecting other
                # reparse points such as OneDrive-backed Documents folders.
                if ($existing.LinkType) { throw 'Setup refuses symlinks/junctions in credential, config or profile paths.' }
            }
            $item = [IO.Path]::GetDirectoryName($item)
        }
    }

    function Read-LumenTextFile([string] $Path, [bool] $ProfileFile = $false) {
        $bytes = [IO.File]::ReadAllBytes($Path)
        $offset = 0
        $encoding = New-Object Text.UTF8Encoding($false, $true)
        if ($bytes.Length -ge 3 -and $bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191) { $offset = 3 }
        elseif ($ProfileFile -and $bytes.Length -ge 2) {
            if ($bytes[0] -eq 255 -and $bytes[1] -eq 254) {
                $offset = 2; $encoding = New-Object Text.UnicodeEncoding($false, $false, $true)
            } elseif ($bytes[0] -eq 254 -and $bytes[1] -eq 255) {
                $offset = 2; $encoding = New-Object Text.UnicodeEncoding($true, $false, $true)
            }
        }
        try {
            $text = $encoding.GetString($bytes, $offset, $bytes.Length - $offset)
            if ($text.Contains([string][char]0)) { throw 'NUL text is not supported.' }
            return $text
        } catch {
            throw 'Unsupported config/profile encoding. TOML requires valid UTF-8; profiles allow UTF-8 or BOM-marked UTF-16. Convert legacy text explicitly; it was not rewritten.'
        }
    }

    function Set-LumenPrivateFileAcl([string] $Path) {
        $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
        $acl = New-Object Security.AccessControl.FileSecurity
        $acl.SetOwner($sid)
        $acl.SetAccessRuleProtection($true, $false)
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'Allow')))
        Set-Acl -LiteralPath $Path -AclObject $acl -ErrorAction Stop
    }

    function Write-LumenFile([string] $Path, [string] $Content, [bool] $ProfileFile = $false, [Collections.ArrayList] $Journal = $null, [bool] $Private = $false, $State = $null) {
        $previous = $null
        if ([IO.File]::Exists($Path)) { $previous = Read-LumenTextFile $Path $ProfileFile }
        $privateWindows = $Private -and [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
        if ($previous -ceq $Content) {
            if ($privateWindows) {
                if ($null -ne $State) { $State.Started = $true }
                Set-LumenPrivateFileAcl $Path
            }
            return
        }
        if ($null -ne $State) { $State.Started = $true }
        [void] [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path))
        if ($null -ne $previous) {
            $backup = $Path + '.' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff') + '.' + [Guid]::NewGuid().ToString('N') + '.bak'
            [IO.File]::Copy($Path, $backup, $false)
            if ($null -ne $Journal) { [void] $Journal.Add($backup) }
            if ($privateWindows) { Set-LumenPrivateFileAcl $backup }
        }
        [IO.File]::WriteAllText($Path, $Content, (New-Object Text.UTF8Encoding($ProfileFile)))
        if ($privateWindows) { Set-LumenPrivateFileAcl $Path }
    }

    # Copy the key out of the SecureString only as validated ASCII bytes. The
    # caller must clear the returned array.
    function Get-LumenKeyBytes([Security.SecureString] $Key) {
        if ($null -eq $Key -or $Key.Length -eq 0 -or $Key.Length -gt 4096) { throw 'Invalid API key length; no files were changed.' }
        $pointer = [IntPtr]::Zero; $valid = $false
        $bytes = New-Object byte[] $Key.Length
        try {
            $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Key)
            for ($i = 0; $i -lt $Key.Length; $i++) {
                $c = [Runtime.InteropServices.Marshal]::ReadInt16($pointer, $i * 2)
                if ($c -lt 33 -or $c -gt 126) { throw 'API key must contain printable ASCII characters without spaces; no files were changed.' }
                $bytes[$i] = [byte] $c
            }
            $valid = $true
            return ,$bytes
        } finally {
            if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
            if (-not $valid) { [Array]::Clear($bytes, 0, $bytes.Length) }
        }
    }

    function Save-LumenKey([Security.SecureString] $Key, [string] $Path, $State = $null) {
        Assert-LumenWindows
        Assert-LumenLocalPath $Path
        $bytes = $null
        try {
            $bytes = Get-LumenKeyBytes $Key
            $encrypted = [Security.Cryptography.ProtectedData]::Protect($bytes, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)
            $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
            $directory = [IO.Path]::GetDirectoryName($Path)
            if ($null -ne $State) { $State.Started = $true }
            [void] [IO.Directory]::CreateDirectory($directory)
            $acl = New-Object Security.AccessControl.DirectorySecurity
            $acl.SetOwner($sid)
            $acl.SetAccessRuleProtection($true, $false)
            $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')))
            Set-Acl -LiteralPath $directory -AclObject $acl -ErrorAction Stop
            $fileAcl = New-Object Security.AccessControl.FileSecurity
            $fileAcl.SetOwner($sid)
            $fileAcl.SetAccessRuleProtection($true, $false)
            $fileAcl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'Allow')))
            if ([IO.File]::Exists($Path)) { Set-Acl -LiteralPath $Path -AclObject $fileAcl -ErrorAction Stop }
            [IO.File]::WriteAllBytes($Path, $encrypted)
            Set-Acl -LiteralPath $Path -AclObject $fileAcl -ErrorAction Stop
        } catch {
            throw 'API key was not saved: Windows CurrentUser DPAPI, a valid private key, and a writable local user directory are required.'
        } finally {
            if ($null -ne $bytes) { [Array]::Clear($bytes, 0, $bytes.Length) }
        }
    }

    function Resolve-LumenCaBundle([string] $Override, [string] $Existing) {
        $path = $Existing
        if ($Override) { $path = $Override }
        if (-not $path) { return '' }
        Assert-LumenLocalPath $path
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'The selected CA bundle must be an existing readable PEM certificate file.' }
        $certificates = [regex]::Matches([IO.File]::ReadAllText($path), '-----BEGIN CERTIFICATE-----\s*([A-Za-z0-9+/=\s]+?)\s*-----END CERTIFICATE-----')
        if ($certificates.Count -eq 0) { throw 'The selected CA bundle contains no PEM certificates.' }
        foreach ($match in $certificates) {
            $certificate = $null
            try {
                $der = [Convert]::FromBase64String($match.Groups[1].Value)
                $certificate = New-Object Security.Cryptography.X509Certificates.X509Certificate2 -ArgumentList (,$der)
            } catch { throw 'The selected CA bundle contains an invalid certificate; TLS verification was not changed.' }
            finally { if ($null -ne $certificate) { $certificate.Dispose() } }
        }
        return [IO.Path]::GetFullPath($path)
    }

    function Get-LumenProfilePolicyNotice([string] $Policy) {
        if ($Policy -notin @('RemoteSigned', 'Unrestricted', 'Bypass')) {
            return ('Effective execution policy ' + $Policy + ' may block this unsigned profile in future sessions. Setup has NOT changed execution policy. If permitted by your organization, explicitly opt in with: Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned. Group Policy can override this; AllSigned instead requires a trusted signature on your profile.')
        }
        return ''
    }

    # GET <Codex base>/cli/models with the key only in the Authorization header.
    # The OS verifies the certificate (no override callback); redirects are never
    # followed, so the key cannot be forwarded elsewhere. Errors never echo the
    # response body, URL credentials or key.
    function Get-LumenCatalogJson([string] $BaseUrl, [Security.SecureString] $Key) {
        $uri = New-Object Uri ((ConvertTo-LumenBaseUrl $BaseUrl) + '/cli/models')
        $bytes = Get-LumenKeyBytes $Key
        $client = $null; $request = $null; $response = $null
        $status = 0; $mediaType = ''; $body = $null
        try {
            Add-Type -AssemblyName System.Net.Http -ErrorAction Stop
            if ($PSVersionTable.PSEdition -ne 'Core') {
                # Windows PowerShell 5.1 may default to legacy protocols; only add TLS 1.2.
                [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
            }
            $handler = New-Object Net.Http.HttpClientHandler
            $handler.AllowAutoRedirect = $false
            $handler.UseCookies = $false
            $handler.UseDefaultCredentials = $false
            $client = New-Object Net.Http.HttpClient -ArgumentList $handler, $true
            $client.Timeout = [TimeSpan]::FromSeconds(30)
            $client.MaxResponseContentBufferSize = 4MB
            $request = New-Object Net.Http.HttpRequestMessage -ArgumentList ([Net.Http.HttpMethod]::Get), $uri
            $request.Headers.Accept.ParseAdd('application/json')
            [void] $request.Headers.TryAddWithoutValidation('Authorization', 'Bearer ' + [Text.Encoding]::ASCII.GetString($bytes))
            $response = $client.SendAsync($request).GetAwaiter().GetResult()
            $status = [int] $response.StatusCode
            if ($null -ne $response.Content.Headers.ContentType) { $mediaType = [string] $response.Content.Headers.ContentType.MediaType }
            if ($status -eq 200) {
                $payload = $response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
                $body = (New-Object Text.UTF8Encoding($false, $true)).GetString($payload)
            }
        } catch {
            throw 'Could not read the Lumen model catalog over verified HTTPS (connection, Windows certificate trust, timeout, size or encoding failure). No files were changed.'
        } finally {
            [Array]::Clear($bytes, 0, $bytes.Length)
            foreach ($disposable in @($response, $request, $client)) { if ($null -ne $disposable) { $disposable.Dispose() } }
        }
        if ($status -ge 300 -and $status -lt 400) {
            throw ('The Lumen model catalog answered with a redirect (HTTP ' + $status + '). Setup never forwards the key to another location; use the advertised Codex base URL. No files were changed.')
        }
        if ($status -eq 401 -or $status -eq 403) {
            throw ('The Lumen API key was rejected or lacks the models:read scope (HTTP ' + $status + '). No files were changed.')
        }
        if ($status -eq 404) { throw 'This Lumen server does not provide /v1/cli/models; check the Codex base URL or upgrade Lumen. No files were changed.' }
        if ($status -ne 200) { throw ('The Lumen model catalog is unavailable (HTTP ' + $status + '). No files were changed.') }
        if ($mediaType -ine 'application/json') { throw 'The Lumen model catalog response is not JSON. No files were changed.' }
        return $body
    }

    function Test-LumenJsonObject($Value) {
        return $null -ne $Value -and $Value -is [Management.Automation.PSCustomObject]
    }

    # Validate the complete server response before showing any choice. Rows are
    # grouped by provider connection in server order and numbered in display order.
    function ConvertFrom-LumenCliCatalog([string] $Json) {
        $invalid = 'The Lumen model catalog response is invalid; no files were changed.'
        try { $document = ConvertFrom-Json -InputObject $Json -ErrorAction Stop } catch { throw $invalid }
        if (-not (Test-LumenJsonObject $document)) { throw $invalid }
        $models = $document.PSObject.Properties['models']
        if ($null -eq $models -or $models.Value -isnot [Array] -or $models.Value.Count -gt 1000) { throw $invalid }
        $groups = [ordered] @{}; $seen = @{}
        foreach ($item in $models.Value) {
            if (-not (Test-LumenJsonObject $item)) { throw $invalid }
            $values = @{}
            foreach ($name in @('id', 'api_model_name', 'display_name', 'provider', 'provider_name', 'provider_type', 'protocols', 'usable',
                    'disabled_reason', 'capabilities', 'input_price_per_million', 'output_price_per_million')) {
                $property = $item.PSObject.Properties[$name]
                if ($null -eq $property) { throw $invalid }
                $values[$name] = $property.Value
            }
            foreach ($name in @('id', 'api_model_name', 'display_name', 'provider', 'provider_name', 'provider_type')) {
                if ($values[$name] -isnot [string] -or $values[$name].Length -gt 500) { throw $invalid }
            }
            $route = [regex]::Match($values['id'], '^lumen/([1-9][0-9]{0,17})/([1-9][0-9]{0,17})\z')
            if (-not $route.Success -or $seen.ContainsKey($values['id'])) { throw $invalid }
            $seen[$values['id']] = $true
            $apiName = ConvertTo-LumenDisplayText $values['api_model_name']
            $provider = ConvertTo-LumenDisplayText $values['provider'] 80
            $providerType = ConvertTo-LumenDisplayText $values['provider_type'] 80
            if (-not $apiName -or -not $provider -or -not $providerType) { throw $invalid }
            $displayName = ConvertTo-LumenDisplayText $values['display_name']
            if (-not $displayName) { $displayName = $apiName }
            $providerName = ConvertTo-LumenDisplayText $values['provider_name'] 80
            if (-not $providerName) { $providerName = $provider }
            if ($values['protocols'] -isnot [Array] -or $values['usable'] -isnot [bool]) { throw $invalid }
            foreach ($protocol in $values['protocols']) { if ($protocol -isnot [string]) { throw $invalid } }
            if ($null -ne $values['disabled_reason'] -and $values['disabled_reason'] -isnot [string]) { throw $invalid }
            foreach ($name in @('input_price_per_million', 'output_price_per_million')) {
                $price = $values[$name]
                if ($null -ne $price -and ($price -isnot [string] -or $price.Length -gt 500 -or $price -cnotmatch '^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\z')) { throw $invalid }
            }
            $capabilities = $values['capabilities']
            if ($null -ne $capabilities -and -not (Test-LumenJsonObject $capabilities)) { throw $invalid }
            # Capabilities are the server's effective projection; anything absent
            # or malformed stays unknown instead of being guessed.
            $contextLimit = $null; $image = $false; $efforts = @()
            if ($null -ne $capabilities) {
                $limit = $capabilities.PSObject.Properties['context_limit']
                if ($null -ne $limit -and ($limit.Value -is [int] -or $limit.Value -is [long]) -and $limit.Value -gt 0) { $contextLimit = [long] $limit.Value }
                $modalities = $capabilities.PSObject.Properties['input_modalities']
                if ($null -ne $modalities -and $modalities.Value -is [Array]) { $image = @($modalities.Value) -ccontains 'image' }
                $options = $capabilities.PSObject.Properties['reasoning_options']
                if ($null -ne $options -and $options.Value -is [Array]) {
                    foreach ($option in $options.Value) {
                        if (-not (Test-LumenJsonObject $option)) { continue }
                        $type = $option.PSObject.Properties['type']
                        if ($null -eq $type -or $type.Value -isnot [string]) { continue }
                        $optionValues = $option.PSObject.Properties['values']
                        if ($type.Value -cne 'effort' -or $null -eq $optionValues -or $optionValues.Value -isnot [Array]) { continue }
                        foreach ($effort in $optionValues.Value) {
                            if ($effort -is [string] -and $effort.Length -gt 0 -and $effort.Length -le 500 -and
                                $effort -notmatch '[\p{Cc}\p{Cf}\p{Zl}\p{Zp}]' -and $efforts -cnotcontains $effort) { $efforts += $effort }
                        }
                    }
                }
            }
            $usable = [bool] $values['usable']
            $protocols = @($values['protocols'])
            $disabled = $null
            if (-not $usable) {
                $disabled = ConvertTo-LumenDisplayText $values['disabled_reason'] 80
                if (-not $disabled) { $disabled = 'disabled by the server' }
            }
            $publicId = $null
            if ($values['api_model_name'] -cmatch '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}\z') { $publicId = $values['api_model_name'] }
            $providerKey = $route.Groups[1].Value
            if (-not $groups.Contains($providerKey)) { $groups[$providerKey] = New-Object Collections.ArrayList }
            [void] $groups[$providerKey].Add([pscustomobject] @{
                Index = 0; Id = $values['id']; ProviderKey = $providerKey; ApiModelName = $apiName; PublicModelId = $publicId
                DisplayName = $displayName; Provider = $provider; ProviderName = $providerName; ProviderType = $providerType
                Usable = $usable; DisabledReason = $disabled
                Responses = ($usable -and $protocols -ccontains 'responses'); Messages = ($usable -and $protocols -ccontains 'messages')
                ContextLimit = $contextLimit; Image = $image; ReasoningEfforts = $efforts
                InputPrice = $values['input_price_per_million']; OutputPrice = $values['output_price_per_million']
            })
        }
        $rows = @(); $index = 0
        foreach ($key in $groups.Keys) {
            foreach ($row in $groups[$key]) { $index++; $row.Index = $index; $rows += $row }
        }
        if (-not @($rows | Where-Object { $_.Responses }).Count) {
            throw 'The Lumen catalog has no usable Codex (Responses) model for this key; ask an administrator to activate one. No files were changed.'
        }
        if (-not @($rows | Where-Object { $_.Messages }).Count) {
            throw 'The Lumen catalog has no usable Claude Code (Messages) model for this key; ask an administrator to activate one. No files were changed.'
        }
        return ,$rows
    }

    function Format-LumenCliCatalog($Rows) {
        $lines = @(); $group = $null
        $invariant = [Globalization.CultureInfo]::InvariantCulture
        foreach ($row in $Rows) {
            if ($row.ProviderKey -cne $group) {
                $group = $row.ProviderKey
                $lines += ''
                $lines += ($row.ProviderName + ' (' + $row.Provider + ', ' + $row.ProviderType + ')')
            }
            $name = $row.DisplayName
            if ($row.DisplayName -cne $row.ApiModelName) { $name += ' [' + $row.ApiModelName + ']' }
            $details = @()
            if ($null -ne $row.ContextLimit) { $details += ('context ' + $row.ContextLimit.ToString('N0', $invariant) + ' tokens') }
            else { $details += 'context unknown' }
            if ($null -ne $row.InputPrice -or $null -ne $row.OutputPrice) {
                $in = 'unknown'; if ($null -ne $row.InputPrice) { $in = $row.InputPrice }
                $out = 'unknown'; if ($null -ne $row.OutputPrice) { $out = $row.OutputPrice }
                $details += ('price per 1M tokens: input ' + $in + ', output ' + $out)
            } else { $details += 'price unknown' }
            if ($row.Usable) {
                $codex = 'no'; if ($row.Responses) { $codex = 'yes' }
                $claude = 'no'; if ($row.Messages) { $claude = 'yes' }
                $details += ('Codex/Responses: ' + $codex + ', Claude/Messages: ' + $claude)
            } else { $details += ('unavailable: ' + $row.DisabledReason) }
            $lines += ('  [' + $row.Index + '] ' + $name + ' - ' + ($details -join '; '))
        }
        # One pipeline item per line: callers print each line, not one joined array.
        return $lines
    }

    function Select-LumenCatalogRow($Rows, [string] $Answer, $Slot) {
        $label = $Slot.Family + ' ' + $Slot.Role
        $text = ([string] $Answer).Trim()
        $row = $null
        if ($text -match '^[1-9][0-9]{0,5}\z') { $row = @($Rows | Where-Object { $_.Index -eq [int] $text })[0] }
        if ($null -eq $row) { throw ('Choose a listed model number for ' + $label + '; no files were changed.') }
        if (-not $row.Usable) { throw ('Model ' + $row.Index + ' is unavailable (' + $row.DisabledReason + ') and cannot be ' + $label + '; no files were changed.') }
        $api = 'Messages'; $supported = $row.Messages
        if ($Slot.Protocol -ceq 'responses') { $api = 'Responses'; $supported = $row.Responses }
        if (-not $supported) { throw ('Model ' + $row.Index + ' does not support the ' + $api + ' API that ' + $label + ' requires; no files were changed.') }
        return $row
    }

    function Read-LumenRoleSelection($Rows) {
        $roles = [ordered] @{}
        foreach ($slot in @(Get-LumenRoleSlots)) {
            $api = 'Messages'; if ($slot.Protocol -ceq 'responses') { $api = 'Responses' }
            $answer = Read-Host ($slot.Family + ' ' + $slot.Role + ' model number (' + $api + ')')
            $roles[$slot.Role] = Select-LumenCatalogRow $Rows $answer $slot
        }
        $startup = ConvertTo-LumenStartupRole (Read-Host 'Claude Code startup role: fable, opus, sonnet or haiku [sonnet]')
        return [pscustomobject] @{ Roles = $roles; StartupRole = $startup }
    }

    # Exact bytes of Codex rust-v0.160.0 codex-rs/models-manager/prompt.md, the
    # generic instructions Codex itself uses for models without catalog metadata
    # (source, license and NOTICE at the end of this file). Base64 keeps this
    # script ASCII so download decoding cannot alter it; the digest is enforced.
    function Get-LumenCodexBaseInstructions {
        $encoded = @'
WW91IGFyZSBhIGNvZGluZyBhZ2VudCBydW5uaW5nIGluIHRoZSBDb2RleCBDTEksIGEgdGVybWlu
YWwtYmFzZWQgY29kaW5nIGFzc2lzdGFudC4gQ29kZXggQ0xJIGlzIGFuIG9wZW4gc291cmNlIHBy
b2plY3QgbGVkIGJ5IE9wZW5BSS4gWW91IGFyZSBleHBlY3RlZCB0byBiZSBwcmVjaXNlLCBzYWZl
LCBhbmQgaGVscGZ1bC4KCllvdXIgY2FwYWJpbGl0aWVzOgoKLSBSZWNlaXZlIHVzZXIgcHJvbXB0
cyBhbmQgb3RoZXIgY29udGV4dCBwcm92aWRlZCBieSB0aGUgaGFybmVzcywgc3VjaCBhcyBmaWxl
cyBpbiB0aGUgd29ya3NwYWNlLgotIENvbW11bmljYXRlIHdpdGggdGhlIHVzZXIgYnkgc3RyZWFt
aW5nIHRoaW5raW5nICYgcmVzcG9uc2VzLCBhbmQgYnkgbWFraW5nICYgdXBkYXRpbmcgcGxhbnMu
Ci0gRW1pdCBmdW5jdGlvbiBjYWxscyB0byBydW4gdGVybWluYWwgY29tbWFuZHMgYW5kIGFwcGx5
IHBhdGNoZXMuIERlcGVuZGluZyBvbiBob3cgdGhpcyBzcGVjaWZpYyBydW4gaXMgY29uZmlndXJl
ZCwgeW91IGNhbiByZXF1ZXN0IHRoYXQgdGhlc2UgZnVuY3Rpb24gY2FsbHMgYmUgZXNjYWxhdGVk
IHRvIHRoZSB1c2VyIGZvciBhcHByb3ZhbCBiZWZvcmUgcnVubmluZy4gTW9yZSBvbiB0aGlzIGlu
IHRoZSAiU2FuZGJveCBhbmQgYXBwcm92YWxzIiBzZWN0aW9uLgoKV2l0aGluIHRoaXMgY29udGV4
dCwgQ29kZXggcmVmZXJzIHRvIHRoZSBvcGVuLXNvdXJjZSBhZ2VudGljIGNvZGluZyBpbnRlcmZh
Y2UgKG5vdCB0aGUgb2xkIENvZGV4IGxhbmd1YWdlIG1vZGVsIGJ1aWx0IGJ5IE9wZW5BSSkuCgoj
IEhvdyB5b3Ugd29yawoKIyMgUGVyc29uYWxpdHkKCllvdXIgZGVmYXVsdCBwZXJzb25hbGl0eSBh
bmQgdG9uZSBpcyBjb25jaXNlLCBkaXJlY3QsIGFuZCBmcmllbmRseS4gWW91IGNvbW11bmljYXRl
IGVmZmljaWVudGx5LCBhbHdheXMga2VlcGluZyB0aGUgdXNlciBjbGVhcmx5IGluZm9ybWVkIGFi
b3V0IG9uZ29pbmcgYWN0aW9ucyB3aXRob3V0IHVubmVjZXNzYXJ5IGRldGFpbC4gWW91IGFsd2F5
cyBwcmlvcml0aXplIGFjdGlvbmFibGUgZ3VpZGFuY2UsIGNsZWFybHkgc3RhdGluZyBhc3N1bXB0
aW9ucywgZW52aXJvbm1lbnQgcHJlcmVxdWlzaXRlcywgYW5kIG5leHQgc3RlcHMuIFVubGVzcyBl
eHBsaWNpdGx5IGFza2VkLCB5b3UgYXZvaWQgZXhjZXNzaXZlbHkgdmVyYm9zZSBleHBsYW5hdGlv
bnMgYWJvdXQgeW91ciB3b3JrLgoKIyBBR0VOVFMubWQgc3BlYwotIFJlcG9zIG9mdGVuIGNvbnRh
aW4gQUdFTlRTLm1kIGZpbGVzLiBUaGVzZSBmaWxlcyBjYW4gYXBwZWFyIGFueXdoZXJlIHdpdGhp
biB0aGUgcmVwb3NpdG9yeS4KLSBUaGVzZSBmaWxlcyBhcmUgYSB3YXkgZm9yIGh1bWFucyB0byBn
aXZlIHlvdSAodGhlIGFnZW50KSBpbnN0cnVjdGlvbnMgb3IgdGlwcyBmb3Igd29ya2luZyB3aXRo
aW4gdGhlIGNvbnRhaW5lci4KLSBTb21lIGV4YW1wbGVzIG1pZ2h0IGJlOiBjb2RpbmcgY29udmVu
dGlvbnMsIGluZm8gYWJvdXQgaG93IGNvZGUgaXMgb3JnYW5pemVkLCBvciBpbnN0cnVjdGlvbnMg
Zm9yIGhvdyB0byBydW4gb3IgdGVzdCBjb2RlLgotIEluc3RydWN0aW9ucyBpbiBBR0VOVFMubWQg
ZmlsZXM6CiAgICAtIFRoZSBzY29wZSBvZiBhbiBBR0VOVFMubWQgZmlsZSBpcyB0aGUgZW50aXJl
IGRpcmVjdG9yeSB0cmVlIHJvb3RlZCBhdCB0aGUgZm9sZGVyIHRoYXQgY29udGFpbnMgaXQuCiAg
ICAtIEZvciBldmVyeSBmaWxlIHlvdSB0b3VjaCBpbiB0aGUgZmluYWwgcGF0Y2gsIHlvdSBtdXN0
IG9iZXkgaW5zdHJ1Y3Rpb25zIGluIGFueSBBR0VOVFMubWQgZmlsZSB3aG9zZSBzY29wZSBpbmNs
dWRlcyB0aGF0IGZpbGUuCiAgICAtIEluc3RydWN0aW9ucyBhYm91dCBjb2RlIHN0eWxlLCBzdHJ1
Y3R1cmUsIG5hbWluZywgZXRjLiBhcHBseSBvbmx5IHRvIGNvZGUgd2l0aGluIHRoZSBBR0VOVFMu
bWQgZmlsZSdzIHNjb3BlLCB1bmxlc3MgdGhlIGZpbGUgc3RhdGVzIG90aGVyd2lzZS4KICAgIC0g
TW9yZS1kZWVwbHktbmVzdGVkIEFHRU5UUy5tZCBmaWxlcyB0YWtlIHByZWNlZGVuY2UgaW4gdGhl
IGNhc2Ugb2YgY29uZmxpY3RpbmcgaW5zdHJ1Y3Rpb25zLgogICAgLSBEaXJlY3Qgc3lzdGVtL2Rl
dmVsb3Blci91c2VyIGluc3RydWN0aW9ucyAoYXMgcGFydCBvZiBhIHByb21wdCkgdGFrZSBwcmVj
ZWRlbmNlIG92ZXIgQUdFTlRTLm1kIGluc3RydWN0aW9ucy4KLSBUaGUgY29udGVudHMgb2YgdGhl
IEFHRU5UUy5tZCBmaWxlIGF0IHRoZSByb290IG9mIHRoZSByZXBvIGFuZCBhbnkgZGlyZWN0b3Jp
ZXMgZnJvbSB0aGUgQ1dEIHVwIHRvIHRoZSByb290IGFyZSBpbmNsdWRlZCB3aXRoIHRoZSBkZXZl
bG9wZXIgbWVzc2FnZSBhbmQgZG9uJ3QgbmVlZCB0byBiZSByZS1yZWFkLiBXaGVuIHdvcmtpbmcg
aW4gYSBzdWJkaXJlY3Rvcnkgb2YgQ1dELCBvciBhIGRpcmVjdG9yeSBvdXRzaWRlIHRoZSBDV0Qs
IGNoZWNrIGZvciBhbnkgQUdFTlRTLm1kIGZpbGVzIHRoYXQgbWF5IGJlIGFwcGxpY2FibGUuCgoj
IyBSZXNwb25zaXZlbmVzcwoKIyMjIFByZWFtYmxlIG1lc3NhZ2VzCgpCZWZvcmUgbWFraW5nIHRv
b2wgY2FsbHMsIHNlbmQgYSBicmllZiBwcmVhbWJsZSB0byB0aGUgdXNlciBleHBsYWluaW5nIHdo
YXQgeW914oCZcmUgYWJvdXQgdG8gZG8uIFdoZW4gc2VuZGluZyBwcmVhbWJsZSBtZXNzYWdlcywg
Zm9sbG93IHRoZXNlIHByaW5jaXBsZXMgYW5kIGV4YW1wbGVzOgoKLSAqKkxvZ2ljYWxseSBncm91
cCByZWxhdGVkIGFjdGlvbnMqKjogaWYgeW914oCZcmUgYWJvdXQgdG8gcnVuIHNldmVyYWwgcmVs
YXRlZCBjb21tYW5kcywgZGVzY3JpYmUgdGhlbSB0b2dldGhlciBpbiBvbmUgcHJlYW1ibGUgcmF0
aGVyIHRoYW4gc2VuZGluZyBhIHNlcGFyYXRlIG5vdGUgZm9yIGVhY2guCi0gKipLZWVwIGl0IGNv
bmNpc2UqKjogYmUgbm8gbW9yZSB0aGFuIDEtMiBzZW50ZW5jZXMsIGZvY3VzZWQgb24gaW1tZWRp
YXRlLCB0YW5naWJsZSBuZXh0IHN0ZXBzLiAoOOKAkzEyIHdvcmRzIGZvciBxdWljayB1cGRhdGVz
KS4KLSAqKkJ1aWxkIG9uIHByaW9yIGNvbnRleHQqKjogaWYgdGhpcyBpcyBub3QgeW91ciBmaXJz
dCB0b29sIGNhbGwsIHVzZSB0aGUgcHJlYW1ibGUgbWVzc2FnZSB0byBjb25uZWN0IHRoZSBkb3Rz
IHdpdGggd2hhdOKAmXMgYmVlbiBkb25lIHNvIGZhciBhbmQgY3JlYXRlIGEgc2Vuc2Ugb2YgbW9t
ZW50dW0gYW5kIGNsYXJpdHkgZm9yIHRoZSB1c2VyIHRvIHVuZGVyc3RhbmQgeW91ciBuZXh0IGFj
dGlvbnMuCi0gKipLZWVwIHlvdXIgdG9uZSBsaWdodCwgZnJpZW5kbHkgYW5kIGN1cmlvdXMqKjog
YWRkIHNtYWxsIHRvdWNoZXMgb2YgcGVyc29uYWxpdHkgaW4gcHJlYW1ibGVzIGZlZWwgY29sbGFi
b3JhdGl2ZSBhbmQgZW5nYWdpbmcuCi0gKipFeGNlcHRpb24qKjogQXZvaWQgYWRkaW5nIGEgcHJl
YW1ibGUgZm9yIGV2ZXJ5IHRyaXZpYWwgcmVhZCAoZS5nLiwgYGNhdGAgYSBzaW5nbGUgZmlsZSkg
dW5sZXNzIGl04oCZcyBwYXJ0IG9mIGEgbGFyZ2VyIGdyb3VwZWQgYWN0aW9uLgoKKipFeGFtcGxl
czoqKgoKLSDigJxJ4oCZdmUgZXhwbG9yZWQgdGhlIHJlcG87IG5vdyBjaGVja2luZyB0aGUgQVBJ
IHJvdXRlIGRlZmluaXRpb25zLuKAnQotIOKAnE5leHQsIEnigJlsbCBwYXRjaCB0aGUgY29uZmln
IGFuZCB1cGRhdGUgdGhlIHJlbGF0ZWQgdGVzdHMu4oCdCi0g4oCcSeKAmW0gYWJvdXQgdG8gc2Nh
ZmZvbGQgdGhlIENMSSBjb21tYW5kcyBhbmQgaGVscGVyIGZ1bmN0aW9ucy7igJ0KLSDigJxPayBj
b29sLCBzbyBJ4oCZdmUgd3JhcHBlZCBteSBoZWFkIGFyb3VuZCB0aGUgcmVwby4gTm93IGRpZ2dp
bmcgaW50byB0aGUgQVBJIHJvdXRlcy7igJ0KLSDigJxDb25maWfigJlzIGxvb2tpbmcgdGlkeS4g
TmV4dCB1cCBpcyBwYXRjaGluZyBoZWxwZXJzIHRvIGtlZXAgdGhpbmdzIGluIHN5bmMu4oCdCi0g
4oCcRmluaXNoZWQgcG9raW5nIGF0IHRoZSBEQiBnYXRld2F5LiBJIHdpbGwgbm93IGNoYXNlIGRv
d24gZXJyb3IgaGFuZGxpbmcu4oCdCi0g4oCcQWxyaWdodCwgYnVpbGQgcGlwZWxpbmUgb3JkZXIg
aXMgaW50ZXJlc3RpbmcuIENoZWNraW5nIGhvdyBpdCByZXBvcnRzIGZhaWx1cmVzLuKAnQotIOKA
nFNwb3R0ZWQgYSBjbGV2ZXIgY2FjaGluZyB1dGlsOyBub3cgaHVudGluZyB3aGVyZSBpdCBnZXRz
IHVzZWQu4oCdCgojIyBQbGFubmluZwoKWW91IGhhdmUgYWNjZXNzIHRvIGFuIGB1cGRhdGVfcGxh
bmAgdG9vbCB3aGljaCB0cmFja3Mgc3RlcHMgYW5kIHByb2dyZXNzIGFuZCByZW5kZXJzIHRoZW0g
dG8gdGhlIHVzZXIuIFVzaW5nIHRoZSB0b29sIGhlbHBzIGRlbW9uc3RyYXRlIHRoYXQgeW91J3Zl
IHVuZGVyc3Rvb2QgdGhlIHRhc2sgYW5kIGNvbnZleSBob3cgeW91J3JlIGFwcHJvYWNoaW5nIGl0
LiBQbGFucyBjYW4gaGVscCB0byBtYWtlIGNvbXBsZXgsIGFtYmlndW91cywgb3IgbXVsdGktcGhh
c2Ugd29yayBjbGVhcmVyIGFuZCBtb3JlIGNvbGxhYm9yYXRpdmUgZm9yIHRoZSB1c2VyLiBBIGdv
b2QgcGxhbiBzaG91bGQgYnJlYWsgdGhlIHRhc2sgaW50byBtZWFuaW5nZnVsLCBsb2dpY2FsbHkg
b3JkZXJlZCBzdGVwcyB0aGF0IGFyZSBlYXN5IHRvIHZlcmlmeSBhcyB5b3UgZ28uCgpOb3RlIHRo
YXQgcGxhbnMgYXJlIG5vdCBmb3IgcGFkZGluZyBvdXQgc2ltcGxlIHdvcmsgd2l0aCBmaWxsZXIg
c3RlcHMgb3Igc3RhdGluZyB0aGUgb2J2aW91cy4gVGhlIGNvbnRlbnQgb2YgeW91ciBwbGFuIHNo
b3VsZCBub3QgaW52b2x2ZSBkb2luZyBhbnl0aGluZyB0aGF0IHlvdSBhcmVuJ3QgY2FwYWJsZSBv
ZiBkb2luZyAoaS5lLiBkb24ndCB0cnkgdG8gdGVzdCB0aGluZ3MgdGhhdCB5b3UgY2FuJ3QgdGVz
dCkuIERvIG5vdCB1c2UgcGxhbnMgZm9yIHNpbXBsZSBvciBzaW5nbGUtc3RlcCBxdWVyaWVzIHRo
YXQgeW91IGNhbiBqdXN0IGRvIG9yIGFuc3dlciBpbW1lZGlhdGVseS4KCkRvIG5vdCByZXBlYXQg
dGhlIGZ1bGwgY29udGVudHMgb2YgdGhlIHBsYW4gYWZ0ZXIgYW4gYHVwZGF0ZV9wbGFuYCBjYWxs
IOKAlCB0aGUgaGFybmVzcyBhbHJlYWR5IGRpc3BsYXlzIGl0LiBJbnN0ZWFkLCBzdW1tYXJpemUg
dGhlIGNoYW5nZSBtYWRlIGFuZCBoaWdobGlnaHQgYW55IGltcG9ydGFudCBjb250ZXh0IG9yIG5l
eHQgc3RlcC4KCkJlZm9yZSBydW5uaW5nIGEgY29tbWFuZCwgY29uc2lkZXIgd2hldGhlciBvciBu
b3QgeW91IGhhdmUgY29tcGxldGVkIHRoZSBwcmV2aW91cyBzdGVwLCBhbmQgbWFrZSBzdXJlIHRv
IG1hcmsgaXQgYXMgY29tcGxldGVkIGJlZm9yZSBtb3Zpbmcgb24gdG8gdGhlIG5leHQgc3RlcC4g
SXQgbWF5IGJlIHRoZSBjYXNlIHRoYXQgeW91IGNvbXBsZXRlIGFsbCBzdGVwcyBpbiB5b3VyIHBs
YW4gYWZ0ZXIgYSBzaW5nbGUgcGFzcyBvZiBpbXBsZW1lbnRhdGlvbi4gSWYgdGhpcyBpcyB0aGUg
Y2FzZSwgeW91IGNhbiBzaW1wbHkgbWFyayBhbGwgdGhlIHBsYW5uZWQgc3RlcHMgYXMgY29tcGxl
dGVkLiBTb21ldGltZXMsIHlvdSBtYXkgbmVlZCB0byBjaGFuZ2UgcGxhbnMgaW4gdGhlIG1pZGRs
ZSBvZiBhIHRhc2s6IGNhbGwgYHVwZGF0ZV9wbGFuYCB3aXRoIHRoZSB1cGRhdGVkIHBsYW4gYW5k
IG1ha2Ugc3VyZSB0byBwcm92aWRlIGFuIGBleHBsYW5hdGlvbmAgb2YgdGhlIHJhdGlvbmFsZSB3
aGVuIGRvaW5nIHNvLgoKVXNlIGEgcGxhbiB3aGVuOgoKLSBUaGUgdGFzayBpcyBub24tdHJpdmlh
bCBhbmQgd2lsbCByZXF1aXJlIG11bHRpcGxlIGFjdGlvbnMgb3ZlciBhIGxvbmcgdGltZSBob3Jp
em9uLgotIFRoZXJlIGFyZSBsb2dpY2FsIHBoYXNlcyBvciBkZXBlbmRlbmNpZXMgd2hlcmUgc2Vx
dWVuY2luZyBtYXR0ZXJzLgotIFRoZSB3b3JrIGhhcyBhbWJpZ3VpdHkgdGhhdCBiZW5lZml0cyBm
cm9tIG91dGxpbmluZyBoaWdoLWxldmVsIGdvYWxzLgotIFlvdSB3YW50IGludGVybWVkaWF0ZSBj
aGVja3BvaW50cyBmb3IgZmVlZGJhY2sgYW5kIHZhbGlkYXRpb24uCi0gV2hlbiB0aGUgdXNlciBh
c2tlZCB5b3UgdG8gZG8gbW9yZSB0aGFuIG9uZSB0aGluZyBpbiBhIHNpbmdsZSBwcm9tcHQKLSBU
aGUgdXNlciBoYXMgYXNrZWQgeW91IHRvIHVzZSB0aGUgcGxhbiB0b29sIChha2EgIlRPRE9zIikK
LSBZb3UgZ2VuZXJhdGUgYWRkaXRpb25hbCBzdGVwcyB3aGlsZSB3b3JraW5nLCBhbmQgcGxhbiB0
byBkbyB0aGVtIGJlZm9yZSB5aWVsZGluZyB0byB0aGUgdXNlcgoKIyMjIEV4YW1wbGVzCgoqKkhp
Z2gtcXVhbGl0eSBwbGFucyoqCgpFeGFtcGxlIDE6CgoxLiBBZGQgQ0xJIGVudHJ5IHdpdGggZmls
ZSBhcmdzCjIuIFBhcnNlIE1hcmtkb3duIHZpYSBDb21tb25NYXJrIGxpYnJhcnkKMy4gQXBwbHkg
c2VtYW50aWMgSFRNTCB0ZW1wbGF0ZQo0LiBIYW5kbGUgY29kZSBibG9ja3MsIGltYWdlcywgbGlu
a3MKNS4gQWRkIGVycm9yIGhhbmRsaW5nIGZvciBpbnZhbGlkIGZpbGVzCgpFeGFtcGxlIDI6Cgox
LiBEZWZpbmUgQ1NTIHZhcmlhYmxlcyBmb3IgY29sb3JzCjIuIEFkZCB0b2dnbGUgd2l0aCBsb2Nh
bFN0b3JhZ2Ugc3RhdGUKMy4gUmVmYWN0b3IgY29tcG9uZW50cyB0byB1c2UgdmFyaWFibGVzCjQu
IFZlcmlmeSBhbGwgdmlld3MgZm9yIHJlYWRhYmlsaXR5CjUuIEFkZCBzbW9vdGggdGhlbWUtY2hh
bmdlIHRyYW5zaXRpb24KCkV4YW1wbGUgMzoKCjEuIFNldCB1cCBOb2RlLmpzICsgV2ViU29ja2V0
IHNlcnZlcgoyLiBBZGQgam9pbi9sZWF2ZSBicm9hZGNhc3QgZXZlbnRzCjMuIEltcGxlbWVudCBt
ZXNzYWdpbmcgd2l0aCB0aW1lc3RhbXBzCjQuIEFkZCB1c2VybmFtZXMgKyBtZW50aW9uIGhpZ2hs
aWdodGluZwo1LiBQZXJzaXN0IG1lc3NhZ2VzIGluIGxpZ2h0d2VpZ2h0IERCCjYuIEFkZCB0eXBp
bmcgaW5kaWNhdG9ycyArIHVucmVhZCBjb3VudAoKKipMb3ctcXVhbGl0eSBwbGFucyoqCgpFeGFt
cGxlIDE6CgoxLiBDcmVhdGUgQ0xJIHRvb2wKMi4gQWRkIE1hcmtkb3duIHBhcnNlcgozLiBDb252
ZXJ0IHRvIEhUTUwKCkV4YW1wbGUgMjoKCjEuIEFkZCBkYXJrIG1vZGUgdG9nZ2xlCjIuIFNhdmUg
cHJlZmVyZW5jZQozLiBNYWtlIHN0eWxlcyBsb29rIGdvb2QKCkV4YW1wbGUgMzoKCjEuIENyZWF0
ZSBzaW5nbGUtZmlsZSBIVE1MIGdhbWUKMi4gUnVuIHF1aWNrIHNhbml0eSBjaGVjawozLiBTdW1t
YXJpemUgdXNhZ2UgaW5zdHJ1Y3Rpb25zCgpJZiB5b3UgbmVlZCB0byB3cml0ZSBhIHBsYW4sIG9u
bHkgd3JpdGUgaGlnaCBxdWFsaXR5IHBsYW5zLCBub3QgbG93IHF1YWxpdHkgb25lcy4KCiMjIFRh
c2sgZXhlY3V0aW9uCgpZb3UgYXJlIGEgY29kaW5nIGFnZW50LiBQbGVhc2Uga2VlcCBnb2luZyB1
bnRpbCB0aGUgcXVlcnkgaXMgY29tcGxldGVseSByZXNvbHZlZCwgYmVmb3JlIGVuZGluZyB5b3Vy
IHR1cm4gYW5kIHlpZWxkaW5nIGJhY2sgdG8gdGhlIHVzZXIuIE9ubHkgdGVybWluYXRlIHlvdXIg
dHVybiB3aGVuIHlvdSBhcmUgc3VyZSB0aGF0IHRoZSBwcm9ibGVtIGlzIHNvbHZlZC4gQXV0b25v
bW91c2x5IHJlc29sdmUgdGhlIHF1ZXJ5IHRvIHRoZSBiZXN0IG9mIHlvdXIgYWJpbGl0eSwgdXNp
bmcgdGhlIHRvb2xzIGF2YWlsYWJsZSB0byB5b3UsIGJlZm9yZSBjb21pbmcgYmFjayB0byB0aGUg
dXNlci4gRG8gTk9UIGd1ZXNzIG9yIG1ha2UgdXAgYW4gYW5zd2VyLgoKWW91IE1VU1QgYWRoZXJl
IHRvIHRoZSBmb2xsb3dpbmcgY3JpdGVyaWEgd2hlbiBzb2x2aW5nIHF1ZXJpZXM6CgotIFdvcmtp
bmcgb24gdGhlIHJlcG8ocykgaW4gdGhlIGN1cnJlbnQgZW52aXJvbm1lbnQgaXMgYWxsb3dlZCwg
ZXZlbiBpZiB0aGV5IGFyZSBwcm9wcmlldGFyeS4KLSBBbmFseXppbmcgY29kZSBmb3IgdnVsbmVy
YWJpbGl0aWVzIGlzIGFsbG93ZWQuCi0gU2hvd2luZyB1c2VyIGNvZGUgYW5kIHRvb2wgY2FsbCBk
ZXRhaWxzIGlzIGFsbG93ZWQuCi0gVXNlIHRoZSBgYXBwbHlfcGF0Y2hgIHRvb2wgdG8gZWRpdCBm
aWxlcyAoTkVWRVIgdHJ5IGBhcHBseXBhdGNoYCBvciBgYXBwbHktcGF0Y2hgLCBvbmx5IGBhcHBs
eV9wYXRjaGApOiB7ImNvbW1hbmQiOlsiYXBwbHlfcGF0Y2giLCIqKiogQmVnaW4gUGF0Y2hcXG4q
KiogVXBkYXRlIEZpbGU6IHBhdGgvdG8vZmlsZS5weVxcbkBAIGRlZiBleGFtcGxlKCk6XFxuLSBw
YXNzXFxuKyByZXR1cm4gMTIzXFxuKioqIEVuZCBQYXRjaCJdfQoKSWYgY29tcGxldGluZyB0aGUg
dXNlcidzIHRhc2sgcmVxdWlyZXMgd3JpdGluZyBvciBtb2RpZnlpbmcgZmlsZXMsIHlvdXIgY29k
ZSBhbmQgZmluYWwgYW5zd2VyIHNob3VsZCBmb2xsb3cgdGhlc2UgY29kaW5nIGd1aWRlbGluZXMs
IHRob3VnaCB1c2VyIGluc3RydWN0aW9ucyAoaS5lLiBBR0VOVFMubWQpIG1heSBvdmVycmlkZSB0
aGVzZSBndWlkZWxpbmVzOgoKLSBGaXggdGhlIHByb2JsZW0gYXQgdGhlIHJvb3QgY2F1c2UgcmF0
aGVyIHRoYW4gYXBwbHlpbmcgc3VyZmFjZS1sZXZlbCBwYXRjaGVzLCB3aGVuIHBvc3NpYmxlLgot
IEF2b2lkIHVubmVlZGVkIGNvbXBsZXhpdHkgaW4geW91ciBzb2x1dGlvbi4KLSBEbyBub3QgYXR0
ZW1wdCB0byBmaXggdW5yZWxhdGVkIGJ1Z3Mgb3IgYnJva2VuIHRlc3RzLiBJdCBpcyBub3QgeW91
ciByZXNwb25zaWJpbGl0eSB0byBmaXggdGhlbS4gKFlvdSBtYXkgbWVudGlvbiB0aGVtIHRvIHRo
ZSB1c2VyIGluIHlvdXIgZmluYWwgbWVzc2FnZSB0aG91Z2guKQotIFVwZGF0ZSBkb2N1bWVudGF0
aW9uIGFzIG5lY2Vzc2FyeS4KLSBLZWVwIGNoYW5nZXMgY29uc2lzdGVudCB3aXRoIHRoZSBzdHls
ZSBvZiB0aGUgZXhpc3RpbmcgY29kZWJhc2UuIENoYW5nZXMgc2hvdWxkIGJlIG1pbmltYWwgYW5k
IGZvY3VzZWQgb24gdGhlIHRhc2suCi0gVXNlIGBnaXQgbG9nYCBhbmQgYGdpdCBibGFtZWAgdG8g
c2VhcmNoIHRoZSBoaXN0b3J5IG9mIHRoZSBjb2RlYmFzZSBpZiBhZGRpdGlvbmFsIGNvbnRleHQg
aXMgcmVxdWlyZWQuCi0gTkVWRVIgYWRkIGNvcHlyaWdodCBvciBsaWNlbnNlIGhlYWRlcnMgdW5s
ZXNzIHNwZWNpZmljYWxseSByZXF1ZXN0ZWQuCi0gRG8gbm90IHdhc3RlIHRva2VucyBieSByZS1y
ZWFkaW5nIGZpbGVzIGFmdGVyIGNhbGxpbmcgYGFwcGx5X3BhdGNoYCBvbiB0aGVtLiBUaGUgdG9v
bCBjYWxsIHdpbGwgZmFpbCBpZiBpdCBkaWRuJ3Qgd29yay4gVGhlIHNhbWUgZ29lcyBmb3IgbWFr
aW5nIGZvbGRlcnMsIGRlbGV0aW5nIGZvbGRlcnMsIGV0Yy4KLSBEbyBub3QgYGdpdCBjb21taXRg
IHlvdXIgY2hhbmdlcyBvciBjcmVhdGUgbmV3IGdpdCBicmFuY2hlcyB1bmxlc3MgZXhwbGljaXRs
eSByZXF1ZXN0ZWQuCi0gRG8gbm90IGFkZCBpbmxpbmUgY29tbWVudHMgd2l0aGluIGNvZGUgdW5s
ZXNzIGV4cGxpY2l0bHkgcmVxdWVzdGVkLgotIERvIG5vdCB1c2Ugb25lLWxldHRlciB2YXJpYWJs
ZSBuYW1lcyB1bmxlc3MgZXhwbGljaXRseSByZXF1ZXN0ZWQuCi0gTkVWRVIgb3V0cHV0IGlubGlu
ZSBjaXRhdGlvbnMgbGlrZSAi44CQRjpSRUFETUUubWTigKBMNS1MMTTjgJEiIGluIHlvdXIgb3V0
cHV0cy4gVGhlIENMSSBpcyBub3QgYWJsZSB0byByZW5kZXIgdGhlc2Ugc28gdGhleSB3aWxsIGp1
c3QgYmUgYnJva2VuIGluIHRoZSBVSS4gSW5zdGVhZCwgaWYgeW91IG91dHB1dCB2YWxpZCBmaWxl
cGF0aHMsIHVzZXJzIHdpbGwgYmUgYWJsZSB0byBjbGljayBvbiB0aGVtIHRvIG9wZW4gdGhlIGZp
bGVzIGluIHRoZWlyIGVkaXRvci4KCiMjIFZhbGlkYXRpbmcgeW91ciB3b3JrCgpJZiB0aGUgY29k
ZWJhc2UgaGFzIHRlc3RzIG9yIHRoZSBhYmlsaXR5IHRvIGJ1aWxkIG9yIHJ1biwgY29uc2lkZXIg
dXNpbmcgdGhlbSB0byB2ZXJpZnkgdGhhdCB5b3VyIHdvcmsgaXMgY29tcGxldGUuIAoKV2hlbiB0
ZXN0aW5nLCB5b3VyIHBoaWxvc29waHkgc2hvdWxkIGJlIHRvIHN0YXJ0IGFzIHNwZWNpZmljIGFz
IHBvc3NpYmxlIHRvIHRoZSBjb2RlIHlvdSBjaGFuZ2VkIHNvIHRoYXQgeW91IGNhbiBjYXRjaCBp
c3N1ZXMgZWZmaWNpZW50bHksIHRoZW4gbWFrZSB5b3VyIHdheSB0byBicm9hZGVyIHRlc3RzIGFz
IHlvdSBidWlsZCBjb25maWRlbmNlLiBJZiB0aGVyZSdzIG5vIHRlc3QgZm9yIHRoZSBjb2RlIHlv
dSBjaGFuZ2VkLCBhbmQgaWYgdGhlIGFkamFjZW50IHBhdHRlcm5zIGluIHRoZSBjb2RlYmFzZXMg
c2hvdyB0aGF0IHRoZXJlJ3MgYSBsb2dpY2FsIHBsYWNlIGZvciB5b3UgdG8gYWRkIGEgdGVzdCwg
eW91IG1heSBkbyBzby4gSG93ZXZlciwgZG8gbm90IGFkZCB0ZXN0cyB0byBjb2RlYmFzZXMgd2l0
aCBubyB0ZXN0cy4KClNpbWlsYXJseSwgb25jZSB5b3UncmUgY29uZmlkZW50IGluIGNvcnJlY3Ru
ZXNzLCB5b3UgY2FuIHN1Z2dlc3Qgb3IgdXNlIGZvcm1hdHRpbmcgY29tbWFuZHMgdG8gZW5zdXJl
IHRoYXQgeW91ciBjb2RlIGlzIHdlbGwgZm9ybWF0dGVkLiBJZiB0aGVyZSBhcmUgaXNzdWVzIHlv
dSBjYW4gaXRlcmF0ZSB1cCB0byAzIHRpbWVzIHRvIGdldCBmb3JtYXR0aW5nIHJpZ2h0LCBidXQg
aWYgeW91IHN0aWxsIGNhbid0IG1hbmFnZSBpdCdzIGJldHRlciB0byBzYXZlIHRoZSB1c2VyIHRp
bWUgYW5kIHByZXNlbnQgdGhlbSBhIGNvcnJlY3Qgc29sdXRpb24gd2hlcmUgeW91IGNhbGwgb3V0
IHRoZSBmb3JtYXR0aW5nIGluIHlvdXIgZmluYWwgbWVzc2FnZS4gSWYgdGhlIGNvZGViYXNlIGRv
ZXMgbm90IGhhdmUgYSBmb3JtYXR0ZXIgY29uZmlndXJlZCwgZG8gbm90IGFkZCBvbmUuCgpGb3Ig
YWxsIG9mIHRlc3RpbmcsIHJ1bm5pbmcsIGJ1aWxkaW5nLCBhbmQgZm9ybWF0dGluZywgZG8gbm90
IGF0dGVtcHQgdG8gZml4IHVucmVsYXRlZCBidWdzLiBJdCBpcyBub3QgeW91ciByZXNwb25zaWJp
bGl0eSB0byBmaXggdGhlbS4gKFlvdSBtYXkgbWVudGlvbiB0aGVtIHRvIHRoZSB1c2VyIGluIHlv
dXIgZmluYWwgbWVzc2FnZSB0aG91Z2guKQoKQmUgbWluZGZ1bCBvZiB3aGV0aGVyIHRvIHJ1biB2
YWxpZGF0aW9uIGNvbW1hbmRzIHByb2FjdGl2ZWx5LiBJbiB0aGUgYWJzZW5jZSBvZiBiZWhhdmlv
cmFsIGd1aWRhbmNlOgoKLSBXaGVuIHJ1bm5pbmcgaW4gdGhlIG5vbi1pbnRlcmFjdGl2ZSBhcHBy
b3ZhbCBtb2RlICoqbmV2ZXIqKiwgcHJvYWN0aXZlbHkgcnVuIHRlc3RzLCBsaW50IGFuZCBkbyB3
aGF0ZXZlciB5b3UgbmVlZCB0byBlbnN1cmUgeW91J3ZlIGNvbXBsZXRlZCB0aGUgdGFzay4KLSBX
aGVuIHdvcmtpbmcgaW4gaW50ZXJhY3RpdmUgYXBwcm92YWwgbW9kZXMgbGlrZSAqKnVudHJ1c3Rl
ZCoqLCBvciAqKm9uLXJlcXVlc3QqKiwgaG9sZCBvZmYgb24gcnVubmluZyB0ZXN0cyBvciBsaW50
IGNvbW1hbmRzIHVudGlsIHRoZSB1c2VyIGlzIHJlYWR5IGZvciB5b3UgdG8gZmluYWxpemUgeW91
ciBvdXRwdXQsIGJlY2F1c2UgdGhlc2UgY29tbWFuZHMgdGFrZSB0aW1lIHRvIHJ1biBhbmQgc2xv
dyBkb3duIGl0ZXJhdGlvbi4gSW5zdGVhZCBzdWdnZXN0IHdoYXQgeW91IHdhbnQgdG8gZG8gbmV4
dCwgYW5kIGxldCB0aGUgdXNlciBjb25maXJtIGZpcnN0LgotIFdoZW4gd29ya2luZyBvbiB0ZXN0
LXJlbGF0ZWQgdGFza3MsIHN1Y2ggYXMgYWRkaW5nIHRlc3RzLCBmaXhpbmcgdGVzdHMsIG9yIHJl
cHJvZHVjaW5nIGEgYnVnIHRvIHZlcmlmeSBiZWhhdmlvciwgeW91IG1heSBwcm9hY3RpdmVseSBy
dW4gdGVzdHMgcmVnYXJkbGVzcyBvZiBhcHByb3ZhbCBtb2RlLiBVc2UgeW91ciBqdWRnZW1lbnQg
dG8gZGVjaWRlIHdoZXRoZXIgdGhpcyBpcyBhIHRlc3QtcmVsYXRlZCB0YXNrLgoKIyMgQW1iaXRp
b24gdnMuIHByZWNpc2lvbgoKRm9yIHRhc2tzIHRoYXQgaGF2ZSBubyBwcmlvciBjb250ZXh0IChp
LmUuIHRoZSB1c2VyIGlzIHN0YXJ0aW5nIHNvbWV0aGluZyBicmFuZCBuZXcpLCB5b3Ugc2hvdWxk
IGZlZWwgZnJlZSB0byBiZSBhbWJpdGlvdXMgYW5kIGRlbW9uc3RyYXRlIGNyZWF0aXZpdHkgd2l0
aCB5b3VyIGltcGxlbWVudGF0aW9uLgoKSWYgeW91J3JlIG9wZXJhdGluZyBpbiBhbiBleGlzdGlu
ZyBjb2RlYmFzZSwgeW91IHNob3VsZCBtYWtlIHN1cmUgeW91IGRvIGV4YWN0bHkgd2hhdCB0aGUg
dXNlciBhc2tzIHdpdGggc3VyZ2ljYWwgcHJlY2lzaW9uLiBUcmVhdCB0aGUgc3Vycm91bmRpbmcg
Y29kZWJhc2Ugd2l0aCByZXNwZWN0LCBhbmQgZG9uJ3Qgb3ZlcnN0ZXAgKGkuZS4gY2hhbmdpbmcg
ZmlsZW5hbWVzIG9yIHZhcmlhYmxlcyB1bm5lY2Vzc2FyaWx5KS4gWW91IHNob3VsZCBiYWxhbmNl
IGJlaW5nIHN1ZmZpY2llbnRseSBhbWJpdGlvdXMgYW5kIHByb2FjdGl2ZSB3aGVuIGNvbXBsZXRp
bmcgdGFza3Mgb2YgdGhpcyBuYXR1cmUuCgpZb3Ugc2hvdWxkIHVzZSBqdWRpY2lvdXMgaW5pdGlh
dGl2ZSB0byBkZWNpZGUgb24gdGhlIHJpZ2h0IGxldmVsIG9mIGRldGFpbCBhbmQgY29tcGxleGl0
eSB0byBkZWxpdmVyIGJhc2VkIG9uIHRoZSB1c2VyJ3MgbmVlZHMuIFRoaXMgbWVhbnMgc2hvd2lu
ZyBnb29kIGp1ZGdtZW50IHRoYXQgeW91J3JlIGNhcGFibGUgb2YgZG9pbmcgdGhlIHJpZ2h0IGV4
dHJhcyB3aXRob3V0IGdvbGQtcGxhdGluZy4gVGhpcyBtaWdodCBiZSBkZW1vbnN0cmF0ZWQgYnkg
aGlnaC12YWx1ZSwgY3JlYXRpdmUgdG91Y2hlcyB3aGVuIHNjb3BlIG9mIHRoZSB0YXNrIGlzIHZh
Z3VlOyB3aGlsZSBiZWluZyBzdXJnaWNhbCBhbmQgdGFyZ2V0ZWQgd2hlbiBzY29wZSBpcyB0aWdo
dGx5IHNwZWNpZmllZC4KCiMjIFNoYXJpbmcgcHJvZ3Jlc3MgdXBkYXRlcwoKRm9yIGVzcGVjaWFs
bHkgbG9uZ2VyIHRhc2tzIHRoYXQgeW91IHdvcmsgb24gKGkuZS4gcmVxdWlyaW5nIG1hbnkgdG9v
bCBjYWxscywgb3IgYSBwbGFuIHdpdGggbXVsdGlwbGUgc3RlcHMpLCB5b3Ugc2hvdWxkIHByb3Zp
ZGUgcHJvZ3Jlc3MgdXBkYXRlcyBiYWNrIHRvIHRoZSB1c2VyIGF0IHJlYXNvbmFibGUgaW50ZXJ2
YWxzLiBUaGVzZSB1cGRhdGVzIHNob3VsZCBiZSBzdHJ1Y3R1cmVkIGFzIGEgY29uY2lzZSBzZW50
ZW5jZSBvciB0d28gKG5vIG1vcmUgdGhhbiA4LTEwIHdvcmRzIGxvbmcpIHJlY2FwcGluZyBwcm9n
cmVzcyBzbyBmYXIgaW4gcGxhaW4gbGFuZ3VhZ2U6IHRoaXMgdXBkYXRlIGRlbW9uc3RyYXRlcyB5
b3VyIHVuZGVyc3RhbmRpbmcgb2Ygd2hhdCBuZWVkcyB0byBiZSBkb25lLCBwcm9ncmVzcyBzbyBm
YXIgKGkuZS4gZmlsZXMgZXhwbG9yZXMsIHN1YnRhc2tzIGNvbXBsZXRlKSwgYW5kIHdoZXJlIHlv
dSdyZSBnb2luZyBuZXh0LgoKQmVmb3JlIGRvaW5nIGxhcmdlIGNodW5rcyBvZiB3b3JrIHRoYXQg
bWF5IGluY3VyIGxhdGVuY3kgYXMgZXhwZXJpZW5jZWQgYnkgdGhlIHVzZXIgKGkuZS4gd3JpdGlu
ZyBhIG5ldyBmaWxlKSwgeW91IHNob3VsZCBzZW5kIGEgY29uY2lzZSBtZXNzYWdlIHRvIHRoZSB1
c2VyIHdpdGggYW4gdXBkYXRlIGluZGljYXRpbmcgd2hhdCB5b3UncmUgYWJvdXQgdG8gZG8gdG8g
ZW5zdXJlIHRoZXkga25vdyB3aGF0IHlvdSdyZSBzcGVuZGluZyB0aW1lIG9uLiBEb24ndCBzdGFy
dCBlZGl0aW5nIG9yIHdyaXRpbmcgbGFyZ2UgZmlsZXMgYmVmb3JlIGluZm9ybWluZyB0aGUgdXNl
ciB3aGF0IHlvdSBhcmUgZG9pbmcgYW5kIHdoeS4KClRoZSBtZXNzYWdlcyB5b3Ugc2VuZCBiZWZv
cmUgdG9vbCBjYWxscyBzaG91bGQgZGVzY3JpYmUgd2hhdCBpcyBpbW1lZGlhdGVseSBhYm91dCB0
byBiZSBkb25lIG5leHQgaW4gdmVyeSBjb25jaXNlIGxhbmd1YWdlLiBJZiB0aGVyZSB3YXMgcHJl
dmlvdXMgd29yayBkb25lLCB0aGlzIHByZWFtYmxlIG1lc3NhZ2Ugc2hvdWxkIGFsc28gaW5jbHVk
ZSBhIG5vdGUgYWJvdXQgdGhlIHdvcmsgZG9uZSBzbyBmYXIgdG8gYnJpbmcgdGhlIHVzZXIgYWxv
bmcuCgojIyBQcmVzZW50aW5nIHlvdXIgd29yayBhbmQgZmluYWwgbWVzc2FnZQoKWW91ciBmaW5h
bCBtZXNzYWdlIHNob3VsZCByZWFkIG5hdHVyYWxseSwgbGlrZSBhbiB1cGRhdGUgZnJvbSBhIGNv
bmNpc2UgdGVhbW1hdGUuIEZvciBjYXN1YWwgY29udmVyc2F0aW9uLCBicmFpbnN0b3JtaW5nIHRh
c2tzLCBvciBxdWljayBxdWVzdGlvbnMgZnJvbSB0aGUgdXNlciwgcmVzcG9uZCBpbiBhIGZyaWVu
ZGx5LCBjb252ZXJzYXRpb25hbCB0b25lLiBZb3Ugc2hvdWxkIGFzayBxdWVzdGlvbnMsIHN1Z2dl
c3QgaWRlYXMsIGFuZCBhZGFwdCB0byB0aGUgdXNlcuKAmXMgc3R5bGUuIElmIHlvdSd2ZSBmaW5p
c2hlZCBhIGxhcmdlIGFtb3VudCBvZiB3b3JrLCB3aGVuIGRlc2NyaWJpbmcgd2hhdCB5b3UndmUg
ZG9uZSB0byB0aGUgdXNlciwgeW91IHNob3VsZCBmb2xsb3cgdGhlIGZpbmFsIGFuc3dlciBmb3Jt
YXR0aW5nIGd1aWRlbGluZXMgdG8gY29tbXVuaWNhdGUgc3Vic3RhbnRpdmUgY2hhbmdlcy4gWW91
IGRvbid0IG5lZWQgdG8gYWRkIHN0cnVjdHVyZWQgZm9ybWF0dGluZyBmb3Igb25lLXdvcmQgYW5z
d2VycywgZ3JlZXRpbmdzLCBvciBwdXJlbHkgY29udmVyc2F0aW9uYWwgZXhjaGFuZ2VzLgoKWW91
IGNhbiBza2lwIGhlYXZ5IGZvcm1hdHRpbmcgZm9yIHNpbmdsZSwgc2ltcGxlIGFjdGlvbnMgb3Ig
Y29uZmlybWF0aW9ucy4gSW4gdGhlc2UgY2FzZXMsIHJlc3BvbmQgaW4gcGxhaW4gc2VudGVuY2Vz
IHdpdGggYW55IHJlbGV2YW50IG5leHQgc3RlcCBvciBxdWljayBvcHRpb24uIFJlc2VydmUgbXVs
dGktc2VjdGlvbiBzdHJ1Y3R1cmVkIHJlc3BvbnNlcyBmb3IgcmVzdWx0cyB0aGF0IG5lZWQgZ3Jv
dXBpbmcgb3IgZXhwbGFuYXRpb24uCgpUaGUgdXNlciBpcyB3b3JraW5nIG9uIHRoZSBzYW1lIGNv
bXB1dGVyIGFzIHlvdSwgYW5kIGhhcyBhY2Nlc3MgdG8geW91ciB3b3JrLiBBcyBzdWNoIHRoZXJl
J3Mgbm8gbmVlZCB0byBzaG93IHRoZSBmdWxsIGNvbnRlbnRzIG9mIGxhcmdlIGZpbGVzIHlvdSBo
YXZlIGFscmVhZHkgd3JpdHRlbiB1bmxlc3MgdGhlIHVzZXIgZXhwbGljaXRseSBhc2tzIGZvciB0
aGVtLiBTaW1pbGFybHksIGlmIHlvdSd2ZSBjcmVhdGVkIG9yIG1vZGlmaWVkIGZpbGVzIHVzaW5n
IGBhcHBseV9wYXRjaGAsIHRoZXJlJ3Mgbm8gbmVlZCB0byB0ZWxsIHVzZXJzIHRvICJzYXZlIHRo
ZSBmaWxlIiBvciAiY29weSB0aGUgY29kZSBpbnRvIGEgZmlsZSLigJRqdXN0IHJlZmVyZW5jZSB0
aGUgZmlsZSBwYXRoLgoKSWYgdGhlcmUncyBzb21ldGhpbmcgdGhhdCB5b3UgdGhpbmsgeW91IGNv
dWxkIGhlbHAgd2l0aCBhcyBhIGxvZ2ljYWwgbmV4dCBzdGVwLCBjb25jaXNlbHkgYXNrIHRoZSB1
c2VyIGlmIHRoZXkgd2FudCB5b3UgdG8gZG8gc28uIEdvb2QgZXhhbXBsZXMgb2YgdGhpcyBhcmUg
cnVubmluZyB0ZXN0cywgY29tbWl0dGluZyBjaGFuZ2VzLCBvciBidWlsZGluZyBvdXQgdGhlIG5l
eHQgbG9naWNhbCBjb21wb25lbnQuIElmIHRoZXJl4oCZcyBzb21ldGhpbmcgdGhhdCB5b3UgY291
bGRuJ3QgZG8gKGV2ZW4gd2l0aCBhcHByb3ZhbCkgYnV0IHRoYXQgdGhlIHVzZXIgbWlnaHQgd2Fu
dCB0byBkbyAoc3VjaCBhcyB2ZXJpZnlpbmcgY2hhbmdlcyBieSBydW5uaW5nIHRoZSBhcHApLCBp
bmNsdWRlIHRob3NlIGluc3RydWN0aW9ucyBzdWNjaW5jdGx5LgoKQnJldml0eSBpcyB2ZXJ5IGlt
cG9ydGFudCBhcyBhIGRlZmF1bHQuIFlvdSBzaG91bGQgYmUgdmVyeSBjb25jaXNlIChpLmUuIG5v
IG1vcmUgdGhhbiAxMCBsaW5lcyksIGJ1dCBjYW4gcmVsYXggdGhpcyByZXF1aXJlbWVudCBmb3Ig
dGFza3Mgd2hlcmUgYWRkaXRpb25hbCBkZXRhaWwgYW5kIGNvbXByZWhlbnNpdmVuZXNzIGlzIGlt
cG9ydGFudCBmb3IgdGhlIHVzZXIncyB1bmRlcnN0YW5kaW5nLgoKIyMjIEZpbmFsIGFuc3dlciBz
dHJ1Y3R1cmUgYW5kIHN0eWxlIGd1aWRlbGluZXMKCllvdSBhcmUgcHJvZHVjaW5nIHBsYWluIHRl
eHQgdGhhdCB3aWxsIGxhdGVyIGJlIHN0eWxlZCBieSB0aGUgQ0xJLiBGb2xsb3cgdGhlc2UgcnVs
ZXMgZXhhY3RseS4gRm9ybWF0dGluZyBzaG91bGQgbWFrZSByZXN1bHRzIGVhc3kgdG8gc2Nhbiwg
YnV0IG5vdCBmZWVsIG1lY2hhbmljYWwuIFVzZSBqdWRnbWVudCB0byBkZWNpZGUgaG93IG11Y2gg
c3RydWN0dXJlIGFkZHMgdmFsdWUuCgoqKlNlY3Rpb24gSGVhZGVycyoqCgotIFVzZSBvbmx5IHdo
ZW4gdGhleSBpbXByb3ZlIGNsYXJpdHkg4oCUIHRoZXkgYXJlIG5vdCBtYW5kYXRvcnkgZm9yIGV2
ZXJ5IGFuc3dlci4KLSBDaG9vc2UgZGVzY3JpcHRpdmUgbmFtZXMgdGhhdCBmaXQgdGhlIGNvbnRl
bnQKLSBLZWVwIGhlYWRlcnMgc2hvcnQgKDHigJMzIHdvcmRzKSBhbmQgaW4gYCoqVGl0bGUgQ2Fz
ZSoqYC4gQWx3YXlzIHN0YXJ0IGhlYWRlcnMgd2l0aCBgKipgIGFuZCBlbmQgd2l0aCBgKipgCi0g
TGVhdmUgbm8gYmxhbmsgbGluZSBiZWZvcmUgdGhlIGZpcnN0IGJ1bGxldCB1bmRlciBhIGhlYWRl
ci4KLSBTZWN0aW9uIGhlYWRlcnMgc2hvdWxkIG9ubHkgYmUgdXNlZCB3aGVyZSB0aGV5IGdlbnVp
bmVseSBpbXByb3ZlIHNjYW5hYmlsaXR5OyBhdm9pZCBmcmFnbWVudGluZyB0aGUgYW5zd2VyLgoK
KipCdWxsZXRzKioKCi0gVXNlIGAtYCBmb2xsb3dlZCBieSBhIHNwYWNlIGZvciBldmVyeSBidWxs
ZXQuCi0gTWVyZ2UgcmVsYXRlZCBwb2ludHMgd2hlbiBwb3NzaWJsZTsgYXZvaWQgYSBidWxsZXQg
Zm9yIGV2ZXJ5IHRyaXZpYWwgZGV0YWlsLgotIEtlZXAgYnVsbGV0cyB0byBvbmUgbGluZSB1bmxl
c3MgYnJlYWtpbmcgZm9yIGNsYXJpdHkgaXMgdW5hdm9pZGFibGUuCi0gR3JvdXAgaW50byBzaG9y
dCBsaXN0cyAoNOKAkzYgYnVsbGV0cykgb3JkZXJlZCBieSBpbXBvcnRhbmNlLgotIFVzZSBjb25z
aXN0ZW50IGtleXdvcmQgcGhyYXNpbmcgYW5kIGZvcm1hdHRpbmcgYWNyb3NzIHNlY3Rpb25zLgoK
KipNb25vc3BhY2UqKgoKLSBXcmFwIGFsbCBjb21tYW5kcywgZmlsZSBwYXRocywgZW52IHZhcnMs
IGFuZCBjb2RlIGlkZW50aWZpZXJzIGluIGJhY2t0aWNrcyAoYGAgYC4uLmAgYGApLgotIEFwcGx5
IHRvIGlubGluZSBleGFtcGxlcyBhbmQgdG8gYnVsbGV0IGtleXdvcmRzIGlmIHRoZSBrZXl3b3Jk
IGl0c2VsZiBpcyBhIGxpdGVyYWwgZmlsZS9jb21tYW5kLgotIE5ldmVyIG1peCBtb25vc3BhY2Ug
YW5kIGJvbGQgbWFya2VyczsgY2hvb3NlIG9uZSBiYXNlZCBvbiB3aGV0aGVyIGl04oCZcyBhIGtl
eXdvcmQgKGAqKmApIG9yIGlubGluZSBjb2RlL3BhdGggKGBgIGAgYGApLgoKKipGaWxlIFJlZmVy
ZW5jZXMqKgpXaGVuIHJlZmVyZW5jaW5nIGZpbGVzIGluIHlvdXIgcmVzcG9uc2UsIG1ha2Ugc3Vy
ZSB0byBpbmNsdWRlIHRoZSByZWxldmFudCBzdGFydCBsaW5lIGFuZCBhbHdheXMgZm9sbG93IHRo
ZSBiZWxvdyBydWxlczoKICAqIFVzZSBpbmxpbmUgY29kZSB0byBtYWtlIGZpbGUgcGF0aHMgY2xp
Y2thYmxlLgogICogRWFjaCByZWZlcmVuY2Ugc2hvdWxkIGhhdmUgYSBzdGFuZCBhbG9uZSBwYXRo
LiBFdmVuIGlmIGl0J3MgdGhlIHNhbWUgZmlsZS4KICAqIEFjY2VwdGVkOiBhYnNvbHV0ZSwgd29y
a3NwYWNl4oCRcmVsYXRpdmUsIGEvIG9yIGIvIGRpZmYgcHJlZml4ZXMsIG9yIGJhcmUgZmlsZW5h
bWUvc3VmZml4LgogICogTGluZS9jb2x1bW4gKDHigJFiYXNlZCwgb3B0aW9uYWwpOiA6bGluZVs6
Y29sdW1uXSBvciAjTGxpbmVbQ2NvbHVtbl0gKGNvbHVtbiBkZWZhdWx0cyB0byAxKS4KICAqIERv
IG5vdCB1c2UgVVJJcyBsaWtlIGZpbGU6Ly8sIHZzY29kZTovLywgb3IgaHR0cHM6Ly8uCiAgKiBE
byBub3QgcHJvdmlkZSByYW5nZSBvZiBsaW5lcwogICogRXhhbXBsZXM6IHNyYy9hcHAudHMsIHNy
Yy9hcHAudHM6NDIsIGIvc2VydmVyL2luZGV4LmpzI0wxMCwgQzpccmVwb1xwcm9qZWN0XG1haW4u
cnM6MTI6NQoKKipTdHJ1Y3R1cmUqKgoKLSBQbGFjZSByZWxhdGVkIGJ1bGxldHMgdG9nZXRoZXI7
IGRvbuKAmXQgbWl4IHVucmVsYXRlZCBjb25jZXB0cyBpbiB0aGUgc2FtZSBzZWN0aW9uLgotIE9y
ZGVyIHNlY3Rpb25zIGZyb20gZ2VuZXJhbCDihpIgc3BlY2lmaWMg4oaSIHN1cHBvcnRpbmcgaW5m
by4KLSBGb3Igc3Vic2VjdGlvbnMgKGUuZy4sIOKAnEJpbmFyaWVz4oCdIHVuZGVyIOKAnFJ1c3Qg
V29ya3NwYWNl4oCdKSwgaW50cm9kdWNlIHdpdGggYSBib2xkZWQga2V5d29yZCBidWxsZXQsIHRo
ZW4gbGlzdCBpdGVtcyB1bmRlciBpdC4KLSBNYXRjaCBzdHJ1Y3R1cmUgdG8gY29tcGxleGl0eToK
ICAtIE11bHRpLXBhcnQgb3IgZGV0YWlsZWQgcmVzdWx0cyDihpIgdXNlIGNsZWFyIGhlYWRlcnMg
YW5kIGdyb3VwZWQgYnVsbGV0cy4KICAtIFNpbXBsZSByZXN1bHRzIOKGkiBtaW5pbWFsIGhlYWRl
cnMsIHBvc3NpYmx5IGp1c3QgYSBzaG9ydCBsaXN0IG9yIHBhcmFncmFwaC4KCioqVG9uZSoqCgot
IEtlZXAgdGhlIHZvaWNlIGNvbGxhYm9yYXRpdmUgYW5kIG5hdHVyYWwsIGxpa2UgYSBjb2Rpbmcg
cGFydG5lciBoYW5kaW5nIG9mZiB3b3JrLgotIEJlIGNvbmNpc2UgYW5kIGZhY3R1YWwg4oCUIG5v
IGZpbGxlciBvciBjb252ZXJzYXRpb25hbCBjb21tZW50YXJ5IGFuZCBhdm9pZCB1bm5lY2Vzc2Fy
eSByZXBldGl0aW9uCi0gVXNlIHByZXNlbnQgdGVuc2UgYW5kIGFjdGl2ZSB2b2ljZSAoZS5nLiwg
4oCcUnVucyB0ZXN0c+KAnSBub3Qg4oCcVGhpcyB3aWxsIHJ1biB0ZXN0c+KAnSkuCi0gS2VlcCBk
ZXNjcmlwdGlvbnMgc2VsZi1jb250YWluZWQ7IGRvbuKAmXQgcmVmZXIgdG8g4oCcYWJvdmXigJ0g
b3Ig4oCcYmVsb3figJ0uCi0gVXNlIHBhcmFsbGVsIHN0cnVjdHVyZSBpbiBsaXN0cyBmb3IgY29u
c2lzdGVuY3kuCgoqKkRvbuKAmXQqKgoKLSBEb27igJl0IHVzZSBsaXRlcmFsIHdvcmRzIOKAnGJv
bGTigJ0gb3Ig4oCcbW9ub3NwYWNl4oCdIGluIHRoZSBjb250ZW50LgotIERvbuKAmXQgbmVzdCBi
dWxsZXRzIG9yIGNyZWF0ZSBkZWVwIGhpZXJhcmNoaWVzLgotIERvbuKAmXQgb3V0cHV0IEFOU0kg
ZXNjYXBlIGNvZGVzIGRpcmVjdGx5IOKAlCB0aGUgQ0xJIHJlbmRlcmVyIGFwcGxpZXMgdGhlbS4K
LSBEb27igJl0IGNyYW0gdW5yZWxhdGVkIGtleXdvcmRzIGludG8gYSBzaW5nbGUgYnVsbGV0OyBz
cGxpdCBmb3IgY2xhcml0eS4KLSBEb27igJl0IGxldCBrZXl3b3JkIGxpc3RzIHJ1biBsb25nIOKA
lCB3cmFwIG9yIHJlZm9ybWF0IGZvciBzY2FuYWJpbGl0eS4KCkdlbmVyYWxseSwgZW5zdXJlIHlv
dXIgZmluYWwgYW5zd2VycyBhZGFwdCB0aGVpciBzaGFwZSBhbmQgZGVwdGggdG8gdGhlIHJlcXVl
c3QuIEZvciBleGFtcGxlLCBhbnN3ZXJzIHRvIGNvZGUgZXhwbGFuYXRpb25zIHNob3VsZCBoYXZl
IGEgcHJlY2lzZSwgc3RydWN0dXJlZCBleHBsYW5hdGlvbiB3aXRoIGNvZGUgcmVmZXJlbmNlcyB0
aGF0IGFuc3dlciB0aGUgcXVlc3Rpb24gZGlyZWN0bHkuIEZvciB0YXNrcyB3aXRoIGEgc2ltcGxl
IGltcGxlbWVudGF0aW9uLCBsZWFkIHdpdGggdGhlIG91dGNvbWUgYW5kIHN1cHBsZW1lbnQgb25s
eSB3aXRoIHdoYXTigJlzIG5lZWRlZCBmb3IgY2xhcml0eS4gTGFyZ2VyIGNoYW5nZXMgY2FuIGJl
IHByZXNlbnRlZCBhcyBhIGxvZ2ljYWwgd2Fsa3Rocm91Z2ggb2YgeW91ciBhcHByb2FjaCwgZ3Jv
dXBpbmcgcmVsYXRlZCBzdGVwcywgZXhwbGFpbmluZyByYXRpb25hbGUgd2hlcmUgaXQgYWRkcyB2
YWx1ZSwgYW5kIGhpZ2hsaWdodGluZyBuZXh0IGFjdGlvbnMgdG8gYWNjZWxlcmF0ZSB0aGUgdXNl
ci4gWW91ciBhbnN3ZXJzIHNob3VsZCBwcm92aWRlIHRoZSByaWdodCBsZXZlbCBvZiBkZXRhaWwg
d2hpbGUgYmVpbmcgZWFzaWx5IHNjYW5uYWJsZS4KCkZvciBjYXN1YWwgZ3JlZXRpbmdzLCBhY2tu
b3dsZWRnZW1lbnRzLCBvciBvdGhlciBvbmUtb2ZmIGNvbnZlcnNhdGlvbmFsIG1lc3NhZ2VzIHRo
YXQgYXJlIG5vdCBkZWxpdmVyaW5nIHN1YnN0YW50aXZlIGluZm9ybWF0aW9uIG9yIHN0cnVjdHVy
ZWQgcmVzdWx0cywgcmVzcG9uZCBuYXR1cmFsbHkgd2l0aG91dCBzZWN0aW9uIGhlYWRlcnMgb3Ig
YnVsbGV0IGZvcm1hdHRpbmcuCgojIFRvb2wgR3VpZGVsaW5lcwoKIyMgU2hlbGwgY29tbWFuZHMK
CldoZW4gdXNpbmcgdGhlIHNoZWxsLCB5b3UgbXVzdCBhZGhlcmUgdG8gdGhlIGZvbGxvd2luZyBn
dWlkZWxpbmVzOgoKLSBXaGVuIHNlYXJjaGluZyBmb3IgdGV4dCBvciBmaWxlcywgcHJlZmVyIHVz
aW5nIGByZ2Agb3IgYHJnIC0tZmlsZXNgIHJlc3BlY3RpdmVseSBiZWNhdXNlIGByZ2AgaXMgbXVj
aCBmYXN0ZXIgdGhhbiBhbHRlcm5hdGl2ZXMgbGlrZSBgZ3JlcGAuIChJZiB0aGUgYHJnYCBjb21t
YW5kIGlzIG5vdCBmb3VuZCwgdGhlbiB1c2UgYWx0ZXJuYXRpdmVzLikKLSBEbyBub3QgdXNlIHB5
dGhvbiBzY3JpcHRzIHRvIGF0dGVtcHQgdG8gb3V0cHV0IGxhcmdlciBjaHVua3Mgb2YgYSBmaWxl
LgoKIyMgYHVwZGF0ZV9wbGFuYAoKQSB0b29sIG5hbWVkIGB1cGRhdGVfcGxhbmAgaXMgYXZhaWxh
YmxlIHRvIHlvdS4gWW91IGNhbiB1c2UgaXQgdG8ga2VlcCBhbiB1cOKAkXRv4oCRZGF0ZSwgc3Rl
cOKAkWJ54oCRc3RlcCBwbGFuIGZvciB0aGUgdGFzay4KClRvIGNyZWF0ZSBhIG5ldyBwbGFuLCBj
YWxsIGB1cGRhdGVfcGxhbmAgd2l0aCBhIHNob3J0IGxpc3Qgb2YgMeKAkXNlbnRlbmNlIHN0ZXBz
IChubyBtb3JlIHRoYW4gNS03IHdvcmRzIGVhY2gpIHdpdGggYSBgc3RhdHVzYCBmb3IgZWFjaCBz
dGVwIChgcGVuZGluZ2AsIGBpbl9wcm9ncmVzc2AsIG9yIGBjb21wbGV0ZWRgKS4KCldoZW4gc3Rl
cHMgaGF2ZSBiZWVuIGNvbXBsZXRlZCwgdXNlIGB1cGRhdGVfcGxhbmAgdG8gbWFyayBlYWNoIGZp
bmlzaGVkIHN0ZXAgYXMgYGNvbXBsZXRlZGAgYW5kIHRoZSBuZXh0IHN0ZXAgeW91IGFyZSB3b3Jr
aW5nIG9uIGFzIGBpbl9wcm9ncmVzc2AuIFRoZXJlIHNob3VsZCBhbHdheXMgYmUgZXhhY3RseSBv
bmUgYGluX3Byb2dyZXNzYCBzdGVwIHVudGlsIGV2ZXJ5dGhpbmcgaXMgZG9uZS4gWW91IGNhbiBt
YXJrIG11bHRpcGxlIGl0ZW1zIGFzIGNvbXBsZXRlIGluIGEgc2luZ2xlIGB1cGRhdGVfcGxhbmAg
Y2FsbC4KCklmIGFsbCBzdGVwcyBhcmUgY29tcGxldGUsIGVuc3VyZSB5b3UgY2FsbCBgdXBkYXRl
X3BsYW5gIHRvIG1hcmsgYWxsIHN0ZXBzIGFzIGBjb21wbGV0ZWRgLgo=
'@
        $bytes = [Convert]::FromBase64String(($encoded -replace '\s', ''))
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $digest = -join @($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) } finally { $sha.Dispose() }
        if ($digest -cne 'ac8ae107a0d72fe3476b430afb161ea4e67da2e446d778aefc44828160559807') {
            throw 'Embedded Codex base instructions failed their SHA-256 check; download the installer again. No files were changed.'
        }
        return (New-Object Text.UTF8Encoding($false, $true)).GetString($bytes)
    }

    # Native Codex ModelInfo rows for the selected Sol/Luna routes only. Unknown
    # metadata stays null/empty; the same route chosen twice is one row.
    function New-LumenCodexCatalog($Selection, [string] $BaseInstructions) {
        if (-not $BaseInstructions) { throw 'Codex base instructions are required; no files were changed.' }
        $entries = New-Object Collections.ArrayList
        foreach ($role in @('Sol', 'Luna')) {
            $row = $Selection.Roles[$role]
            $existing = @($entries | Where-Object { $_.Row.Id -ceq $row.Id })
            if ($existing.Count) { $existing[0].Label += ' + ' + $role; continue }
            [void] $entries.Add([pscustomobject] @{ Label = $role; Row = $row })
        }
        $models = @(); $priority = 0
        foreach ($entry in $entries) {
            $row = $entry.Row
            # Preserve server metadata on the row; expose only the named native
            # effort variants here, without guessing translations for customs.
            $nativeEfforts = @($row.ReasoningEfforts | Where-Object { $_ -cin @('none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra', 'persistent') })
            $levels = @(foreach ($effort in $nativeEfforts) { [ordered] @{ effort = $effort; description = 'Server-advertised ' + $effort + ' reasoning effort' } })
            $modalities = @('text'); if ($row.Image) { $modalities += 'image' }
            $model = [ordered] @{
                slug = ConvertTo-LumenRouteId $row.Id
                display_name = Get-LumenRoleLabel $entry.Label $row
                description = Get-LumenRouteDescription $row
                base_instructions = $BaseInstructions
            }
            if ($levels.Count) {
                $default = $levels[0].effort; if ($nativeEfforts -ccontains 'medium') { $default = 'medium' }
                $model['default_reasoning_level'] = $default
            }
            $model['supported_reasoning_levels'] = $levels
            $model['shell_type'] = 'unified_exec'
            $model['visibility'] = 'list'
            $model['supported_in_api'] = $true
            $model['priority'] = $priority
            $model['availability_nux'] = $null
            $model['upgrade'] = $null
            $model['supports_reasoning_summary_parameter'] = $false
            $model['support_verbosity'] = $false
            $model['default_verbosity'] = $null
            $model['apply_patch_tool_type'] = $null
            $model['truncation_policy'] = [ordered] @{ mode = 'bytes'; limit = 10000 }
            $model['context_window'] = $row.ContextLimit
            if ($null -ne $row.ContextLimit) { $model['max_context_window'] = $row.ContextLimit }
            $model['experimental_supported_tools'] = @()
            $model['input_modalities'] = $modalities
            $models += ,$model
            $priority++
        }
        return (ConvertTo-Json -InputObject ([ordered] @{ models = $models }) -Depth 8) + "`n"
    }

    function Undo-LumenWritePlan($States, $Journal) {
        $restored = $true
        for ($i = $States.Count - 1; $i -ge 0; $i--) {
            $state = $States[$i]
            if (-not $state.Started) { continue }
            try {
                $exists = [IO.File]::Exists($state.Path)
                if ($null -eq $state.Original) {
                    if ($exists) { [IO.File]::Delete($state.Path) }
                } elseif (-not $exists -or [Convert]::ToBase64String([IO.File]::ReadAllBytes($state.Path)) -cne [Convert]::ToBase64String($state.Original)) {
                    [IO.File]::WriteAllBytes($state.Path, $state.Original)
                }
                if ($null -ne $state.OriginalAcl -and $state.OriginalAcl.Sddl -cne (Get-Acl -LiteralPath $state.Path -ErrorAction Stop).Sddl) {
                    Set-Acl -LiteralPath $state.Path -AclObject $state.OriginalAcl -ErrorAction Stop
                }
            } catch { $restored = $false }
        }
        # Keep backups whenever any original could not be restored.
        if ($restored) { foreach ($backup in $Journal) { try { [IO.File]::Delete($backup) } catch { $restored = $false } } }
        return $restored
    }

    # Apply fully prepared content as one unit: any failure or interruption
    # restores every touched file (including the encrypted key) to its prior bytes.
    function Invoke-LumenWritePlan($Items) {
        $journal = New-Object Collections.ArrayList
        $states = New-Object Collections.ArrayList
        $complete = $false; $failure = $null; $restored = $true
        try {
            foreach ($item in $Items) {
                $original = $null; $originalAcl = $null
                if ([IO.File]::Exists($item.Path)) {
                    $original = [IO.File]::ReadAllBytes($item.Path)
                    if (($item.Private -or $null -ne $item.Key) -and [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
                        $originalAcl = Get-Acl -LiteralPath $item.Path -ErrorAction Stop
                    }
                }
                $state = [pscustomobject] @{ Path = $item.Path; Original = $original; OriginalAcl = $originalAcl; Started = $false }
                [void] $states.Add($state)
                if ($null -ne $item.Key) { Save-LumenKey $item.Key $item.Path $state }
                else { Write-LumenFile $item.Path $item.Content ([bool] $item.ProfileFile) $journal ([bool] $item.Private) $state }
            }
            $complete = $true
        } catch {
            $failure = $_
        } finally {
            if (-not $complete) {
                $restored = Undo-LumenWritePlan $states $journal
                if (-not $restored) { Write-Warning 'Setup stopped and some files could not be restored; their timestamped .bak copies were kept.' }
            }
        }
        if ($null -ne $failure) {
            if ($restored) { throw ('No changes were kept: ' + $failure.Exception.Message) }
            throw ('Setup failed and some files could not be restored from their .bak copies: ' + $failure.Exception.Message)
        }
    }

    # The profile block decrypts only for this Windows account.
    function Get-LumenUserSid {
        return [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    }

    function Get-LumenKeyPath {
        $localData = [Environment]::GetFolderPath('LocalApplicationData')
        if (-not $localData) { throw 'Windows LocalApplicationData is unavailable; no secure credential location exists.' }
        return Join-Path $localData 'Lumen\cli\api-key.dpapi'
    }

    # Claude routes identify their provider. A legacy selector in the shell or in
    # Claude's user settings env (which overrides the shell) would pin every
    # family to one provider; refuse it without changing unrelated headers.
    function Get-LumenClaudeSettingsHeaders {
        $directory = $env:CLAUDE_CONFIG_DIR
        if (-not $directory) { $directory = Join-Path $HOME '.claude' }
        $path = Join-Path $directory 'settings.json'
        try {
            if (-not [IO.File]::Exists($path) -or (Get-Item -LiteralPath $path -Force).Length -gt 1MB) { return '' }
            $value = ([IO.File]::ReadAllText($path) | ConvertFrom-Json -ErrorAction Stop).env.ANTHROPIC_CUSTOM_HEADERS
            if ($value -is [string]) { return $value }
        } catch {}
        return ''
    }

    function Assert-LumenClaudeSelectors([string[]] $Headers) {
        foreach ($line in (($Headers | Where-Object { $_ }) -split '\r\n|\n|\r')) {
            if (($line -split ':', 2)[0].Trim() -ieq 'X-Lumen-Provider') {
                throw 'ANTHROPIC_CUSTOM_HEADERS sets X-Lumen-Provider (shell or Claude settings.json env). Claude role routes already identify their provider; remove that header, open a new terminal, and rerun setup. No files were changed.'
            }
        }
    }

    function Invoke-LumenInstall {
        Assert-LumenWindows
        $codexUrl = $env:LUMEN_CODEX_BASE_URL
        if (-not $codexUrl) { $codexUrl = Read-Host 'Public Lumen Codex Responses HTTPS base URL (include /v1 if advertised)' }
        $codexUrl = ConvertTo-LumenBaseUrl $codexUrl
        $anthropicUrl = $env:LUMEN_ANTHROPIC_BASE_URL
        if (-not $anthropicUrl) { $anthropicUrl = Read-Host 'Public Lumen Anthropic HTTPS base URL (as advertised)' }
        $anthropicUrl = ConvertTo-LumenBaseUrl $anthropicUrl
        $caBundle = Resolve-LumenCaBundle $env:LUMEN_CA_BUNDLE $env:CODEX_CA_CERTIFICATE
        $baseInstructions = Get-LumenCodexBaseInstructions
        $codexHome = $env:CODEX_HOME
        if (-not $codexHome) { $codexHome = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex' }
        $codexHome = [IO.Path]::GetFullPath($codexHome)
        $configPath = Join-Path $codexHome 'config.toml'
        $cliConfigPath = Join-Path $codexHome 'lumen-cli.config.toml'
        $solConfigPath = Join-Path $codexHome 'lumen-sol.config.toml'
        $lunaConfigPath = Join-Path $codexHome 'lumen-luna.config.toml'
        $catalogPath = Join-Path $codexHome 'lumen-models.json'
        $profilePath = $PROFILE.CurrentUserAllHosts
        if (-not $profilePath) { throw 'This host does not expose PROFILE.CurrentUserAllHosts; run setup in an interactive Windows PowerShell host.' }
        $keyPath = Get-LumenKeyPath
        foreach ($path in @($configPath, $cliConfigPath, $solConfigPath, $lunaConfigPath, $catalogPath, $profilePath, $keyPath)) {
            Assert-LumenLocalPath $path
            if ([IO.Directory]::Exists($path)) { throw 'Config, catalog, profile and credential destinations must be files or absent; no files were changed.' }
        }
        $config = ''; if ([IO.File]::Exists($configPath)) { $config = Read-LumenTextFile $configPath }
        $cliConfig = ''; if ([IO.File]::Exists($cliConfigPath)) { $cliConfig = Read-LumenTextFile $cliConfigPath }
        $solConfig = ''; if ([IO.File]::Exists($solConfigPath)) { $solConfig = Read-LumenTextFile $solConfigPath }
        $lunaConfig = ''; if ([IO.File]::Exists($lunaConfigPath)) { $lunaConfig = Read-LumenTextFile $lunaConfigPath }
        if ([IO.File]::Exists($catalogPath)) { $null = Read-LumenTextFile $catalogPath }
        $profileText = ''; if ([IO.File]::Exists($profilePath)) { $profileText = Read-LumenTextFile $profilePath $true }
        # Refuse ambiguous TOML and profile markers before the key prompt; final
        # content is rendered from the selected routes before any write.
        $null = Update-LumenToml $config $codexUrl
        foreach ($text in @($cliConfig, $solConfig, $lunaConfig)) { $null = Update-LumenToml $text $codexUrl 'lumen/1/1' $true $catalogPath }
        Assert-LumenClaudeSelectors @($env:ANTHROPIC_CUSTOM_HEADERS, (Get-LumenClaudeSettingsHeaders))
        $null = Update-LumenProfile $profileText ''
        $sid = Get-LumenUserSid
        $policyNotice = Get-LumenProfilePolicyNotice ([string] (Get-ExecutionPolicy))
        if ($policyNotice) { Write-Warning $policyNotice }
        Write-Host 'The full API key is entered privately. It is sent only in the HTTPS Authorization header to read the model catalog, never written to TOML/profile/history, and stored with Windows DPAPI CurrentUser after every file is prepared.'
        $key = Read-Host 'Full Lumen API key (input hidden)' -AsSecureString
        try {
            Write-Host ('Reading the model catalog from ' + $codexUrl + '/cli/models (Windows certificate verification; redirects refused).')
            $rows = ConvertFrom-LumenCliCatalog (Get-LumenCatalogJson $codexUrl $key)
            Write-Host 'Active Lumen text models by provider:'
            foreach ($line in @(Format-LumenCliCatalog $rows)) { Write-Host $line }
            Write-Host ''
            Write-Host 'Choose a number for each role. One model may fill several roles; roles are positions you assign, not size or quality ratings.'
            $selection = Read-LumenRoleSelection $rows
            $sol = $selection.Roles['Sol']; $luna = $selection.Roles['Luna']
            $defaultModel = ''
            if ($sol.PublicModelId) {
                Write-Host ('Optional: set only the top-level desktop Codex model to the Sol public model ID ' + $sol.PublicModelId + '. Your desktop default provider stays unchanged, so this works only if that provider serves this ID. Existing config is backed up.')
                $answer = Read-Host 'Use this public model ID as the top-level Codex model? [y/N]'
                if ($answer -notmatch '^(?i:y|yes|n|no)?\z') { throw 'Answer y/yes or n/no; no files were changed.' }
                if ($answer -match '^(?i:y|yes)\z') { $defaultModel = $sol.PublicModelId }
            }
            $catalog = New-LumenCodexCatalog $selection $baseInstructions
            $newConfig = Update-LumenToml $config $codexUrl $defaultModel
            $newCliConfig = Update-LumenToml $cliConfig $codexUrl $sol.Id $true $catalogPath
            $newSolConfig = Update-LumenToml $solConfig $codexUrl $sol.Id $true $catalogPath
            $newLunaConfig = Update-LumenToml $lunaConfig $codexUrl $luna.Id $true $catalogPath
            $block = New-LumenProfileBlock $keyPath $sid $anthropicUrl $selection $codexHome $caBundle
            $newProfile = Update-LumenProfile $profileText $block
            Invoke-LumenWritePlan @(
                [pscustomobject] @{ Path = $catalogPath; Content = $catalog; ProfileFile = $false; Key = $null; Private = $true }
                [pscustomobject] @{ Path = $configPath; Content = $newConfig; ProfileFile = $false; Key = $null }
                [pscustomobject] @{ Path = $cliConfigPath; Content = $newCliConfig; ProfileFile = $false; Key = $null }
                [pscustomobject] @{ Path = $solConfigPath; Content = $newSolConfig; ProfileFile = $false; Key = $null }
                [pscustomobject] @{ Path = $lunaConfigPath; Content = $newLunaConfig; ProfileFile = $false; Key = $null }
                [pscustomobject] @{ Path = $profilePath; Content = $newProfile; ProfileFile = $true; Key = $null }
                [pscustomobject] @{ Path = $keyPath; Content = $null; ProfileFile = $false; Key = $key }
            )
        } finally {
            if ($null -ne $key) { $key.Dispose() }
        }
        # Execute only our generated block, never unrelated user profile code.
        & ([scriptblock]::Create($block))
        if (-not $env:LUMEN_API_KEY) { throw 'Credential was saved but could not be loaded; setup is not complete.' }
        Write-Host "Configured current-user all-hosts profile: $profilePath"
        Write-Host 'Installed roles:'
        foreach ($slot in @(Get-LumenRoleSlots)) {
            $row = $selection.Roles[$slot.Role]
            Write-Host ('  ' + $slot.Family + ' ' + (Get-LumenRoleLabel $slot.Role $row) + ' -> ' + $row.Id)
        }
        Write-Host 'PowerShell 5.1 and PowerShell 7 have separate profile locations: rerun in each edition you use. -NoProfile shells do not load credentials.'
        Write-Host 'Setup always uses Windows certificate trust. Codex also uses Windows trust unless your validated LUMEN_CA_BUNDLE or existing CODEX_CA_CERTIFICATE selects a custom Codex PEM bundle. A private CA must be trusted by Windows for the catalog request. Existing Claude trust overrides are untouched; TLS verification remains enabled.'
        Write-Host 'Run: codex (Sol) or codex --profile lumen-luna (Luna); /model lists both roles. Session commands get --strict-config and --profile lumen-cli unless you pass them (debug prompt-input gets only the profile); codex login, codex mcp and other management commands keep native defaults. Your -m, -c and -p/--profile win.'
        Write-Host ('Run: claude (starts as ' + $selection.StartupRole + ') or claude --model fable|opus|sonnet|haiku; /model shows each role label.')
        Write-Host 'Desktop provider/default model stay unchanged unless you opted into the model change. Future profile loading requires an execution policy that permits this profile; other shells do not load it. Backups retain original settings and encoding.'
    }

    Invoke-LumenInstall
}

# Third-party notice for Get-LumenCodexBaseInstructions: the embedded text is the
# unmodified file https://raw.githubusercontent.com/openai/codex/rust-v0.160.0/codex-rs/models-manager/prompt.md
# (git blob 907ff8b877026871b088f01f4366cea36e1f02cd, 20903 bytes, SHA-256
# ac8ae107a0d72fe3476b430afb161ea4e67da2e446d778aefc44828160559807) from OpenAI Codex,
# licensed under the Apache License, Version 2.0. Its NOTICE (no-break spaces shown as
# ASCII spaces to keep this installer ASCII) and license text follow.
#
# NOTICE (openai/codex rust-v0.160.0):
# OpenAI Codex
# Copyright 2025 OpenAI
#
# This project includes code derived from [Ratatui](https://github.com/ratatui/ratatui), licensed under the MIT license.
# Copyright (c) 2016-2022 Florian Dehau
# Copyright (c) 2023-2025 The Ratatui Developers
#
#                                  Apache License
#                            Version 2.0, January 2004
#                         http://www.apache.org/licenses/
#
# TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION
#
# 1.  Definitions.
#
#     "License" shall mean the terms and conditions for use, reproduction,
#     and distribution as defined by Sections 1 through 9 of this document.
#
#     "Licensor" shall mean the copyright owner or entity authorized by
#     the copyright owner that is granting the License.
#
#     "Legal Entity" shall mean the union of the acting entity and all
#     other entities that control, are controlled by, or are under common
#     control with that entity. For the purposes of this definition,
#     "control" means (i) the power, direct or indirect, to cause the
#     direction or management of such entity, whether by contract or
#     otherwise, or (ii) ownership of fifty percent (50%) or more of the
#     outstanding shares, or (iii) beneficial ownership of such entity.
#
#     "You" (or "Your") shall mean an individual or Legal Entity
#     exercising permissions granted by this License.
#
#     "Source" form shall mean the preferred form for making modifications,
#     including but not limited to software source code, documentation
#     source, and configuration files.
#
#     "Object" form shall mean any form resulting from mechanical
#     transformation or translation of a Source form, including but
#     not limited to compiled object code, generated documentation,
#     and conversions to other media types.
#
#     "Work" shall mean the work of authorship, whether in Source or
#     Object form, made available under the License, as indicated by a
#     copyright notice that is included in or attached to the work
#     (an example is provided in the Appendix below).
#
#     "Derivative Works" shall mean any work, whether in Source or Object
#     form, that is based on (or derived from) the Work and for which the
#     editorial revisions, annotations, elaborations, or other modifications
#     represent, as a whole, an original work of authorship. For the purposes
#     of this License, Derivative Works shall not include works that remain
#     separable from, or merely link (or bind by name) to the interfaces of,
#     the Work and Derivative Works thereof.
#
#     "Contribution" shall mean any work of authorship, including
#     the original version of the Work and any modifications or additions
#     to that Work or Derivative Works thereof, that is intentionally
#     submitted to Licensor for inclusion in the Work by the copyright owner
#     or by an individual or Legal Entity authorized to submit on behalf of
#     the copyright owner. For the purposes of this definition, "submitted"
#     means any form of electronic, verbal, or written communication sent
#     to the Licensor or its representatives, including but not limited to
#     communication on electronic mailing lists, source code control systems,
#     and issue tracking systems that are managed by, or on behalf of, the
#     Licensor for the purpose of discussing and improving the Work, but
#     excluding communication that is conspicuously marked or otherwise
#     designated in writing by the copyright owner as "Not a Contribution."
#
#     "Contributor" shall mean Licensor and any individual or Legal Entity
#     on behalf of whom a Contribution has been received by Licensor and
#     subsequently incorporated within the Work.
#
# 2.  Grant of Copyright License. Subject to the terms and conditions of
#     this License, each Contributor hereby grants to You a perpetual,
#     worldwide, non-exclusive, no-charge, royalty-free, irrevocable
#     copyright license to reproduce, prepare Derivative Works of,
#     publicly display, publicly perform, sublicense, and distribute the
#     Work and such Derivative Works in Source or Object form.
#
# 3.  Grant of Patent License. Subject to the terms and conditions of
#     this License, each Contributor hereby grants to You a perpetual,
#     worldwide, non-exclusive, no-charge, royalty-free, irrevocable
#     (except as stated in this section) patent license to make, have made,
#     use, offer to sell, sell, import, and otherwise transfer the Work,
#     where such license applies only to those patent claims licensable
#     by such Contributor that are necessarily infringed by their
#     Contribution(s) alone or by combination of their Contribution(s)
#     with the Work to which such Contribution(s) was submitted. If You
#     institute patent litigation against any entity (including a
#     cross-claim or counterclaim in a lawsuit) alleging that the Work
#     or a Contribution incorporated within the Work constitutes direct
#     or contributory patent infringement, then any patent licenses
#     granted to You under this License for that Work shall terminate
#     as of the date such litigation is filed.
#
# 4.  Redistribution. You may reproduce and distribute copies of the
#     Work or Derivative Works thereof in any medium, with or without
#     modifications, and in Source or Object form, provided that You
#     meet the following conditions:
#
#     (a) You must give any other recipients of the Work or
#     Derivative Works a copy of this License; and
#
#     (b) You must cause any modified files to carry prominent notices
#     stating that You changed the files; and
#
#     (c) You must retain, in the Source form of any Derivative Works
#     that You distribute, all copyright, patent, trademark, and
#     attribution notices from the Source form of the Work,
#     excluding those notices that do not pertain to any part of
#     the Derivative Works; and
#
#     (d) If the Work includes a "NOTICE" text file as part of its
#     distribution, then any Derivative Works that You distribute must
#     include a readable copy of the attribution notices contained
#     within such NOTICE file, excluding those notices that do not
#     pertain to any part of the Derivative Works, in at least one
#     of the following places: within a NOTICE text file distributed
#     as part of the Derivative Works; within the Source form or
#     documentation, if provided along with the Derivative Works; or,
#     within a display generated by the Derivative Works, if and
#     wherever such third-party notices normally appear. The contents
#     of the NOTICE file are for informational purposes only and
#     do not modify the License. You may add Your own attribution
#     notices within Derivative Works that You distribute, alongside
#     or as an addendum to the NOTICE text from the Work, provided
#     that such additional attribution notices cannot be construed
#     as modifying the License.
#
#     You may add Your own copyright statement to Your modifications and
#     may provide additional or different license terms and conditions
#     for use, reproduction, or distribution of Your modifications, or
#     for any such Derivative Works as a whole, provided Your use,
#     reproduction, and distribution of the Work otherwise complies with
#     the conditions stated in this License.
#
# 5.  Submission of Contributions. Unless You explicitly state otherwise,
#     any Contribution intentionally submitted for inclusion in the Work
#     by You to the Licensor shall be under the terms and conditions of
#     this License, without any additional terms or conditions.
#     Notwithstanding the above, nothing herein shall supersede or modify
#     the terms of any separate license agreement you may have executed
#     with Licensor regarding such Contributions.
#
# 6.  Trademarks. This License does not grant permission to use the trade
#     names, trademarks, service marks, or product names of the Licensor,
#     except as required for reasonable and customary use in describing the
#     origin of the Work and reproducing the content of the NOTICE file.
#
# 7.  Disclaimer of Warranty. Unless required by applicable law or
#     agreed to in writing, Licensor provides the Work (and each
#     Contributor provides its Contributions) on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
#     implied, including, without limitation, any warranties or conditions
#     of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A
#     PARTICULAR PURPOSE. You are solely responsible for determining the
#     appropriateness of using or redistributing the Work and assume any
#     risks associated with Your exercise of permissions under this License.
#
# 8.  Limitation of Liability. In no event and under no legal theory,
#     whether in tort (including negligence), contract, or otherwise,
#     unless required by applicable law (such as deliberate and grossly
#     negligent acts) or agreed to in writing, shall any Contributor be
#     liable to You for damages, including any direct, indirect, special,
#     incidental, or consequential damages of any character arising as a
#     result of this License or out of the use or inability to use the
#     Work (including but not limited to damages for loss of goodwill,
#     work stoppage, computer failure or malfunction, or any and all
#     other commercial damages or losses), even if such Contributor
#     has been advised of the possibility of such damages.
#
# 9.  Accepting Warranty or Additional Liability. While redistributing
#     the Work or Derivative Works thereof, You may choose to offer,
#     and charge a fee for, acceptance of support, warranty, indemnity,
#     or other liability obligations and/or rights consistent with this
#     License. However, in accepting such obligations, You may act only
#     on Your own behalf and on Your sole responsibility, not on behalf
#     of any other Contributor, and only if You agree to indemnify,
#     defend, and hold each Contributor harmless for any liability
#     incurred by, or claims asserted against, such Contributor by reason
#     of your accepting any such warranty or additional liability.
#
# END OF TERMS AND CONDITIONS
#
# APPENDIX: How to apply the Apache License to your work.
#
#       To apply the Apache License to your work, attach the following
#       boilerplate notice, with the fields enclosed by brackets "[]"
#       replaced with your own identifying information. (Don't include
#       the brackets!)  The text should be enclosed in the appropriate
#       comment syntax for the file format. We also recommend that a
#       file or class name and description of purpose be included on the
#       same "printed page" as the copyright notice for easier
#       identification within third-party archives.
#
# Copyright 2025 OpenAI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
