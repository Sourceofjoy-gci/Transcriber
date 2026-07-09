param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile
)

$targetUrl = if ($env:RESTORE_DATABASE_URL) { $env:RESTORE_DATABASE_URL } else { $env:DATABASE_URL }
if (-not $targetUrl) {
    Write-Error "RESTORE_DATABASE_URL or DATABASE_URL is required"
    exit 2
}

if (-not (Test-Path -LiteralPath $BackupFile)) {
    Write-Error "Backup file not found: $BackupFile"
    exit 2
}

& pg_restore --clean --if-exists --no-owner --no-acl --dbname $targetUrl $BackupFile
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
