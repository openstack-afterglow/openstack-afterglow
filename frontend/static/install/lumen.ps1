# Lumen Windows setup: paste only public base URLs into the invoking command.
# The API key is prompted privately, encrypted with Windows DPAPI CurrentUser,
# and decrypted only by this user's PowerShell profile into process environment.
# Environment credentials are inherited by child processes; do not dump env or
# enable PowerShell tracing/debug logging while entering or using credentials.
# Existing Codex defaults are retained unless the explicit default-model prompt
# is accepted. Changed config/profile files receive timestamped .bak copies.
# TOML must be valid UTF-8. Profiles accept UTF-8 or BOM-marked UTF-16;
# ambiguous legacy encodings are refused without rewriting. Backups retain bytes.
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

    function ConvertTo-LumenModel([string] $Value) {
        if ($Value -notmatch '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$') {
            throw 'Enter a public model ID (letters, digits, dot, underscore, colon, slash or hyphen; at most 200 characters).'
        }
        return $Value
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

    function Test-LumenProviderSection($Parts) {
        return $Parts.Count -eq 2 -and $Parts[0] -ceq 'model_providers' -and $Parts[1] -ceq 'lumen'
    }

    function Update-LumenToml([string] $Text, [string] $BaseUrl, [string] $DefaultModel = '') {
        $BaseUrl = ConvertTo-LumenBaseUrl $BaseUrl
        if ($DefaultModel) { $DefaultModel = ConvertTo-LumenModel $DefaultModel }
        $nl = "`n"; if ($Text.Contains("`r`n")) { $nl = "`r`n" }
        $fields = [ordered] @{
            name = '"Lumen Responses"'; base_url = (ConvertTo-LumenTomlString $BaseUrl)
            env_key = '"LUMEN_API_KEY"'; wire_api = '"responses"'; requires_openai_auth = 'false'; supports_websockets = 'false'
        }
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
                if (Test-LumenProviderSection $section) { $providerEnd = $statement.Start }
                $header = $m; if ($array.Success) { $header = $array }
                $section = Get-LumenTomlPath $header.Groups[1].Value
                if (Test-LumenProviderSection $section) {
                    if ($array.Success -or $providerFound) { throw 'Duplicate or array Lumen provider table; config was not changed.' }
                    $providerFound = $true
                }
                if ($section.Count -gt 2 -and $section[0] -ceq 'model_providers' -and $section[1] -ceq 'lumen' -and $fields.Keys -ccontains $section[2]) {
                    throw 'A managed Lumen provider field is defined as a table; config was not changed.'
                }
                continue
            }
            $assignment = [regex]::Match($s, '^((?:[^="'']|"(?:[^"\\]|\\.)*"|''[^'']*'')+)\s*=')
            if (-not $assignment.Success) { throw 'Unsupported TOML assignment; config was not changed.' }
            $key = Get-LumenTomlPath $assignment.Groups[1].Value
            if (($section.Count -eq 0 -and $key[0] -ceq 'model_providers') -or
                ($section.Count -eq 1 -and $section[0] -ceq 'model_providers' -and $key[0] -ceq 'lumen')) {
                throw 'Inline/dotted model_providers configuration needs manual migration to tables; config was not changed.'
            }
            $replacement = $null
            if ($section.Count -eq 0 -and $key.Count -eq 1 -and $key[0] -cin @('model', 'model_provider')) {
                if ($rootSeen.ContainsKey($key[0])) { throw 'Duplicate Codex default key; config was not changed.' }
                $rootSeen[$key[0]] = $true
                if ($DefaultModel -and $key[0] -ceq 'model') {
                    $replacement = 'model = ' + (ConvertTo-LumenTomlString $DefaultModel) + $nl
                }
            }
            if ((Test-LumenProviderSection $section) -and $fields.Keys -ccontains $key[0]) {
                if ($key.Count -ne 1 -or $seen.ContainsKey($key[0])) { throw 'Conflicting Lumen provider key; config was not changed.' }
                $seen[$key[0]] = $true
                $replacement = $key[0] + ' = ' + $fields[$key[0]] + $nl
            }
            if ($null -ne $replacement) {
                $edits += [pscustomobject] @{ Start = $statement.Start; Length = $statement.Length; Value = $replacement; Order = 0 }
            }
        }
        $rootInsert = ''
        if ($DefaultModel -and -not $rootSeen.ContainsKey('model')) {
            $rootInsert = 'model = ' + (ConvertTo-LumenTomlString $DefaultModel) + $nl
        }
        $providerInsert = ''
        if (-not $providerFound) { $providerInsert = $nl + '[model_providers.lumen]' + $nl }
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
        # Apply replacements before insertions at the same offset; root insertion
        # must precede an appended provider table when starting with an empty file.
        foreach ($edit in @($edits | Sort-Object -Property @{ Expression = 'Start'; Descending = $true }, @{ Expression = 'Length'; Descending = $true }, @{ Expression = 'Order'; Descending = $false })) {
            $Text = $Text.Remove($edit.Start, $edit.Length).Insert($edit.Start, $edit.Value)
        }
        return $Text
    }

    function New-LumenProfileBlock([string] $KeyPath, [string] $Sid, [string] $BaseUrl, [string] $Model, [string] $CodexModel, [string] $CodexHome, [string] $CaBundle = '') {
        $pathLiteral = ConvertTo-LumenPsLiteral $KeyPath
        $sidLiteral = ConvertTo-LumenPsLiteral $Sid
        $urlLiteral = ConvertTo-LumenPsLiteral (ConvertTo-LumenBaseUrl $BaseUrl)
        $modelLiteral = ConvertTo-LumenPsLiteral (ConvertTo-LumenModel $Model)
        $codexModelLiteral = ConvertTo-LumenPsLiteral (ConvertTo-LumenModel $CodexModel)
        $caLiteral = ConvertTo-LumenPsLiteral $CaBundle
        $codexHomeLiteral = ConvertTo-LumenPsLiteral $CodexHome
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
        $env:LUMEN_CODEX_MODEL = __CODEX_MODEL__
        $env:CODEX_HOME = __CODEX_HOME__
        if (__CA__) { $env:CODEX_CA_CERTIFICATE = __CA__ }
        $env:ANTHROPIC_BASE_URL = __URL__
        $env:LUMEN_MODEL = __MODEL__
        $env:ANTHROPIC_MODEL = $env:LUMEN_MODEL
        $env:ANTHROPIC_DEFAULT_SONNET_MODEL = __MODEL__
        $env:ANTHROPIC_DEFAULT_OPUS_MODEL = __MODEL__
        $env:ANTHROPIC_DEFAULT_HAIKU_MODEL = __MODEL__
    } catch {
        Remove-Item Env:LUMEN_API_KEY, Env:ANTHROPIC_AUTH_TOKEN -ErrorAction SilentlyContinue
        Write-Warning 'Lumen key could not be decrypted for this Windows user. Rerun the Lumen installer locally; there is no plaintext fallback.'
    } finally {
        if ($null -ne $bytes) { [Array]::Clear($bytes, 0, $bytes.Length) }
    }
}
# <<< Lumen CLI <<<
'@
        # Replace tokens in one pass so user paths cannot introduce another token.
        $values = @{ '__PATH__' = $pathLiteral; '__SID__' = $sidLiteral; '__URL__' = $urlLiteral; '__MODEL__' = $modelLiteral; '__CODEX_MODEL__' = $codexModelLiteral; '__CODEX_HOME__' = $codexHomeLiteral; '__CA__' = $caLiteral }
        return [regex]::Replace($template, '__PATH__|__SID__|__URL__|__MODEL__|__CODEX_MODEL__|__CODEX_HOME__|__CA__', [Text.RegularExpressions.MatchEvaluator] { param($m) $values[$m.Value] })
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

    function Write-LumenFile([string] $Path, [string] $Content, [bool] $ProfileFile = $false) {
        $previous = $null
        if ([IO.File]::Exists($Path)) { $previous = Read-LumenTextFile $Path $ProfileFile }
        if ($previous -ceq $Content) { return }
        [void] [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path))
        if ($null -ne $previous) {
            [IO.File]::Copy($Path, $Path + '.' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff') + '.' + [Guid]::NewGuid().ToString('N') + '.bak', $false)
        }
        [IO.File]::WriteAllText($Path, $Content, (New-Object Text.UTF8Encoding($ProfileFile)))
    }

    function Save-LumenKey([Security.SecureString] $Key, [string] $Path) {
        Assert-LumenWindows
        Assert-LumenLocalPath $Path
        $pointer = [IntPtr]::Zero; $bytes = $null
        try {
            if ($Key.Length -eq 0 -or $Key.Length -gt 4096) { throw 'Invalid API key length.' }
            $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Key)
            $bytes = New-Object byte[] $Key.Length
            for ($i = 0; $i -lt $Key.Length; $i++) {
                $c = [Runtime.InteropServices.Marshal]::ReadInt16($pointer, $i * 2)
                if ($c -lt 33 -or $c -gt 126) { throw 'API key must contain printable ASCII characters without spaces.' }
                $bytes[$i] = [byte] $c
            }
            $encrypted = [Security.Cryptography.ProtectedData]::Protect($bytes, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)
            $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
            $directory = [IO.Path]::GetDirectoryName($Path)
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
            if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
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

    function Invoke-LumenInstall {
        Assert-LumenWindows
        $codexUrl = $env:LUMEN_CODEX_BASE_URL
        if (-not $codexUrl) { $codexUrl = Read-Host 'Public Lumen Codex Responses HTTPS base URL (include /v1 if advertised)' }
        $codexUrl = ConvertTo-LumenBaseUrl $codexUrl
        $anthropicUrl = $env:LUMEN_ANTHROPIC_BASE_URL
        if (-not $anthropicUrl) { $anthropicUrl = Read-Host 'Public Lumen Anthropic HTTPS base URL (as advertised)' }
        $anthropicUrl = ConvertTo-LumenBaseUrl $anthropicUrl
        $caBundle = Resolve-LumenCaBundle $env:LUMEN_CA_BUNDLE $env:CODEX_CA_CERTIFICATE
        $model = ConvertTo-LumenModel (Read-Host 'Public Anthropic model ID for Claude Code (not a provider ID)')
        $responsesModel = ConvertTo-LumenModel (Read-Host 'Public Responses model ID for Codex (not a provider ID)')
        Write-Host 'Codex defaults and unrelated TOML tables will be preserved. Use -m to select the Responses model per run.'
        Write-Host 'Optional change: replace only the top-level Codex model with this Responses model. Your default provider stays unchanged; the command explicitly selects Lumen. Existing config is backed up.'
        $answer = Read-Host 'Use this Responses model as the top-level Codex model? [y/N]'
        if ($answer -notmatch '^(?i:y|yes|n|no)?$') { throw 'Answer y/yes or n/no; no files were changed.' }
        $defaultModel = ''; if ($answer -match '^(?i:y|yes)$') { $defaultModel = $responsesModel }
        $codexHome = $env:CODEX_HOME
        if (-not $codexHome) { $codexHome = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex' }
        $codexHome = [IO.Path]::GetFullPath($codexHome)
        $configPath = Join-Path $codexHome 'config.toml'
        $profilePath = $PROFILE.CurrentUserAllHosts
        if (-not $profilePath) { throw 'This host does not expose PROFILE.CurrentUserAllHosts; run setup in an interactive Windows PowerShell host.' }
        $localData = [Environment]::GetFolderPath('LocalApplicationData')
        if (-not $localData) { throw 'Windows LocalApplicationData is unavailable; no secure credential location exists.' }
        $keyPath = Join-Path $localData 'Lumen\cli\api-key.dpapi'
        foreach ($path in @($configPath, $profilePath, $keyPath)) { Assert-LumenLocalPath $path }
        $config = ''; if ([IO.File]::Exists($configPath)) { $config = Read-LumenTextFile $configPath }
        $profileText = ''; if ([IO.File]::Exists($profilePath)) { $profileText = Read-LumenTextFile $profilePath $true }
        $newConfig = Update-LumenToml $config $codexUrl $defaultModel
        $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        $block = New-LumenProfileBlock $keyPath $sid $anthropicUrl $model $responsesModel $codexHome $caBundle
        $newProfile = Update-LumenProfile $profileText $block
        $policyNotice = Get-LumenProfilePolicyNotice ([string] (Get-ExecutionPolicy))
        if ($policyNotice) { Write-Warning $policyNotice }
        Write-Host 'The full API key is entered privately, never written to TOML/profile/history, and stored using Windows DPAPI CurrentUser.'
        $key = Read-Host 'Full Lumen API key (input hidden)' -AsSecureString
        try { Save-LumenKey $key $keyPath } finally { if ($null -ne $key) { $key.Dispose() } }
        Write-LumenFile $configPath $newConfig
        Write-LumenFile $profilePath $newProfile $true
        # Execute only our generated block, never unrelated user profile code.
        & ([scriptblock]::Create($block))
        if (-not $env:LUMEN_API_KEY) { throw 'Credential was saved but could not be loaded; setup is not complete.' }
        Write-Host "Configured current-user all-hosts profile: $profilePath"
        Write-Host 'PowerShell 5.1 and PowerShell 7 have separate profile locations: rerun in each edition you use. -NoProfile shells do not load credentials.'
        Write-Host 'Windows certificate trust is used unless your validated LUMEN_CA_BUNDLE or existing CODEX_CA_CERTIFICATE selects a custom Codex PEM bundle. Existing Claude trust overrides are untouched; TLS verification remains enabled.'
        if ($defaultModel) { Write-Host 'Run: codex --strict-config -c model_provider=lumen' }
        else { Write-Host 'Run: codex --strict-config -c model_provider=lumen -m "$env:LUMEN_CODEX_MODEL"' }
        Write-Host 'Run: claude. Future profile loading requires an execution policy that permits this profile; other shells do not load it. Backups retain original settings and encoding.'
    }

    Invoke-LumenInstall
}
