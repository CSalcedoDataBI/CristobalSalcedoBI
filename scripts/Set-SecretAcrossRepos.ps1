<#
.SYNOPSIS
    Set one GitHub Actions secret across many repositories in a single pass.

.DESCRIPTION
    A GitHub personal account has no account-level Actions secrets: the only scopes are
    repository, environment (per repository) and organization. A secret that several repos
    need therefore has to exist in each of them. This script removes the manual work, not
    the duplication.

    The secret value is never accepted as a parameter and never written to a command line.
    It is read from an environment variable named by the caller and piped to `gh secret set`
    through stdin, so it does not appear in shell history, in the process command line, or
    anywhere in this repository.

.PARAMETER Name
    The secret name, e.g. CLAUDE_CODE_OAUTH_TOKEN. Must match what the workflows reference.

.PARAMETER ValueFromEnv
    Name of the environment variable holding the value. Checked in the process environment
    first, then the Windows USER registry (where this account keeps its long-lived tokens),
    because a variable set after the shell started is not visible in $env:.

.PARAMETER Repos
    Explicit target list as owner/name. Defaults to every owned, non-fork, public repo.

.PARAMETER Owner
    Account whose repos are targeted by default. Defaults to CSalcedoDataBI.

.PARAMETER IncludePrivate
    Also target owned private repos. Off by default: a token scoped for public work has no
    business being installed where it is not needed.

.PARAMETER TokenVar
    Environment/registry variable holding the PAT used to authenticate gh.

.PARAMETER DryRun
    Print the plan and exit without calling the API.

.EXAMPLE
    # rotation: set the new value once, fan it out everywhere
    .\Set-SecretAcrossRepos.ps1 -Name CLAUDE_CODE_OAUTH_TOKEN -ValueFromEnv CLAUDE_OAUTH_NEW -DryRun
    .\Set-SecretAcrossRepos.ps1 -Name CLAUDE_CODE_OAUTH_TOKEN -ValueFromEnv CLAUDE_OAUTH_NEW

.NOTES
    Idempotent: `gh secret set` overwrites an existing secret, which is what rotation needs.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Name,
    [Parameter(Mandatory)][string]$ValueFromEnv,
    [string[]]$Repos,
    [string]$Owner = 'CSalcedoDataBI',
    [switch]$IncludePrivate,
    [string]$TokenVar = 'GITHUB_TOKEN_PERSONAL',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

function Read-Var([string]$varName) {
    # A variable set after this shell started is absent from $env:, so fall back to the
    # USER registry - the same reason the repo convention reads tokens that way.
    $v = [Environment]::GetEnvironmentVariable($varName, 'Process')
    if (-not $v) { $v = [Environment]::GetEnvironmentVariable($varName, 'User') }
    return $v
}

if ($Name -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
    throw "Secret name '$Name' is not a valid Actions secret name (letters, digits, underscore; no leading digit)."
}

$token = Read-Var $TokenVar
if (-not $token) { throw "No PAT found in '$TokenVar' (process or USER registry)." }
$env:GH_TOKEN = $token

$secret = Read-Var $ValueFromEnv
if (-not $secret) {
    throw "No value found in '$ValueFromEnv'. Set it first, e.g.:  `$env:$ValueFromEnv = '<value>'   (this script never takes the value as a parameter)."
}

# --- resolve targets ----------------------------------------------------------
if ($Repos) {
    $targets = @($Repos | ForEach-Object { if ($_ -match '/') { $_ } else { "$Owner/$_" } })
} else {
    $visibility = if ($IncludePrivate) { '' } else { ' | select(.private == false)' }
    $jq = ".[] | select(.fork == false)$visibility | .full_name"
    $targets = @(gh api "users/$Owner/repos?type=owner&per_page=100" --paginate --jq $jq)
    if ($LASTEXITCODE -ne 0 -or -not $targets) { throw "Could not list repos for '$Owner'." }
}

Write-Host ""
Write-Host "=== Set-SecretAcrossRepos  '$Name' ===" -ForegroundColor Cyan
Write-Host ("  Owner   : {0}" -f $Owner)
Write-Host ("  Value   : from `${0} (never printed)" -f $ValueFromEnv)
Write-Host ("  Scope   : {0}" -f $(if ($IncludePrivate) { 'owned non-fork, public + private' } else { 'owned non-fork, public only' }))
Write-Host ("  Targets : {0} repo(s)" -f $targets.Count)
$targets | ForEach-Object { Write-Host ("    - {0}" -f $_) }

if ($DryRun) {
    Write-Host ""
    Write-Host "[DryRun] nothing was written." -ForegroundColor Yellow
    return
}

# --- fan out ------------------------------------------------------------------
Write-Host ""
$ok = 0
$failed = @()
foreach ($r in $targets) {
    # stdin, not --body: --body would place the secret in the process command line.
    $secret | gh secret set $Name --repo $r --app actions 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host ("  OK    {0}" -f $r) -ForegroundColor Green
        $ok++
    } else {
        Write-Host ("  FAIL  {0}" -f $r) -ForegroundColor Red
        $failed += $r
    }
}

Write-Host ""
Write-Host ("Set '{0}' on {1}/{2} repo(s)." -f $Name, $ok, $targets.Count)
if ($failed.Count) {
    Write-Host ("FAILED: {0}" -f ($failed -join ', ')) -ForegroundColor Red
    Write-Host "Re-run to retry only those with -Repos." -ForegroundColor Yellow
    exit 1
}
Write-Host "Verify with:  gh secret list --repo <owner/name>"
