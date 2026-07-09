param(
    [string]$OutputPath = "backups/transcriber-$(Get-Date -AsUTC -Format 'yyyyMMddTHHmmssZ').dump"
)

if (-not $env:DATABASE_URL) {
    Write-Error "DATABASE_URL is required"
    exit 2
}

$directory = Split-Path -Parent $OutputPath
if ($directory) {
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
}

& pg_dump --format=custom --no-owner --no-acl --file $OutputPath $env:DATABASE_URL
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Output $OutputPath
