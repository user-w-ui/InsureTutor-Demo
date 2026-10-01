# Build the demo, wait for retrieval readiness, and open the published web page.
$ErrorActionPreference = 'Stop'
Get-Command docker -ErrorAction Stop | Out-Null

Push-Location (Join-Path $PSScriptRoot '..')
try {
    docker compose up --build --wait --wait-timeout 180
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker startup failed. Check Docker Desktop and run: docker compose logs --tail 50'
    }

    $publishedAddress = (docker compose port insuretutor 8000 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $publishedAddress -notmatch '^127\.0\.0\.1:(\d+)$') {
        throw 'Could not determine the published web port.'
    }
    $demoUrl = "http://127.0.0.1:$($Matches[1])/"
    Write-Host "InsureTutor is ready: $demoUrl"
    Start-Process $demoUrl
}
finally {
    Pop-Location
}
