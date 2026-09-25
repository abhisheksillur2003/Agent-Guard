param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9.-]+$')]
    [string]$Domain,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[^@\s]+@[^@\s]+\.[^@\s]+$')]
    [string]$AcmeEmail,

    [string]$OutputPath = '.env.production',

    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$templatePath = Join-Path $repositoryRoot '.env.production.example'
$resolvedOutput = if ([System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath
} else {
    Join-Path $repositoryRoot $OutputPath
}

if ((Test-Path -LiteralPath $resolvedOutput) -and -not $Force) {
    throw "$resolvedOutput already exists. Use -Force only when replacement is intentional."
}

function New-UrlSafeSecret {
    $bytes = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(48)
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

$postgresPassword = New-UrlSafeSecret
$redisPassword = New-UrlSafeSecret
$authSigningKey = New-UrlSafeSecret
$agentKeyPepper = New-UrlSafeSecret
$findingPepper = New-UrlSafeSecret

$content = Get-Content -Raw -LiteralPath $templatePath
$replacements = [ordered]@{
    'DOMAIN' = $Domain
    'ACME_EMAIL' = $AcmeEmail
    'POSTGRES_PASSWORD' = $postgresPassword
    'REDIS_PASSWORD' = $redisPassword
    'AGENTGUARD_ALLOWED_HOSTS' = "[`"$Domain`",`"api`"]"
    'AGENTGUARD_DATABASE_URL' = "postgresql+asyncpg://agentguard:${postgresPassword}@postgres:5432/agentguard"
    'AGENTGUARD_REDIS_URL' = "redis://:${redisPassword}@redis:6379/0"
    'AGENTGUARD_AUTH_SIGNING_KEY' = $authSigningKey
    'AGENTGUARD_AGENT_KEY_PEPPER' = $agentKeyPepper
    'AGENTGUARD_FINDING_FINGERPRINT_PEPPER' = $findingPepper
}

foreach ($entry in $replacements.GetEnumerator()) {
    $escapedKey = [Regex]::Escape([string]$entry.Key)
    $replacement = "{0}={1}" -f $entry.Key, $entry.Value
    $content = [Regex]::Replace(
        $content,
        "(?m)^${escapedKey}=.*$",
        [System.Text.RegularExpressions.MatchEvaluator]{ param($match) $replacement }
    )
}

Set-Content -LiteralPath $resolvedOutput -Value $content -Encoding utf8NoBOM
Write-Host "Created $resolvedOutput with independent generated secrets."
Write-Host 'Keep this file private and restrict it to the deployment account.'
