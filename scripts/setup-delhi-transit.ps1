[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envFile = Join-Path $projectRoot ".env"
$gtfsDirectory = Join-Path $projectRoot "data\gtfs"
$archivePath = Join-Path $gtfsDirectory "delhi-buses.zip"
$apiBaseUrl = "http://localhost:8000"
$feedSlug = "delhi-bus"

if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    throw "Create the project .env file first and configure the saved Delhi OTD API key there."
}

$keyLine = Get-Content -LiteralPath $envFile | Where-Object {
    $_ -match '^\s*DELHI_TRANSIT_API_KEY\s*='
} | Select-Object -Last 1
$keyValue = if ($keyLine) { ($keyLine -split "=", 2)[1].Trim().Trim('"').Trim("'") } else { "" }
if ([string]::IsNullOrWhiteSpace($keyValue) -or $keyValue -match '^(your_|replace_)') {
    throw "The existing Delhi OTD key is missing from .env. The key value will not be displayed."
}
Remove-Variable keyLine, keyValue

$dockerCommand = Get-Command docker.exe -ErrorAction SilentlyContinue
$dockerPath = if ($dockerCommand) { $dockerCommand.Source } else { $null }
if (-not $dockerPath) {
    $dockerCandidates = @(
        (Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\resources\bin\docker.exe")
    )
    $dockerPath = $dockerCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}
if (-not $dockerPath) {
    throw "Docker Desktop is not available. Start Docker Desktop, then run this script again."
}

New-Item -ItemType Directory -Force -Path $gtfsDirectory | Out-Null
Push-Location $projectRoot
try {
    Write-Host "Building and starting WaitWatch..."
    & $dockerPath compose up -d --build
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose could not start WaitWatch. Check that Docker Desktop is running."
    }

    $deadline = (Get-Date).AddSeconds(90)
    $healthy = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $health = Invoke-RestMethod -Uri "$apiBaseUrl/api/health" -TimeoutSec 5
            if ($health) {
                $healthy = $true
                break
            }
        } catch {
            Start-Sleep -Seconds 3
        }
    }
    if (-not $healthy) {
        throw "The WaitWatch API did not become ready within 90 seconds. Check 'docker compose ps'."
    }

    $feeds = (Invoke-RestMethod -Uri "$apiBaseUrl/api/v1/feeds" -TimeoutSec 10).data
    $feed = $feeds | Where-Object { $_.slug -eq $feedSlug } | Select-Object -First 1
    if (-not $feed) {
        Write-Host "Registering the Delhi live bus feed..."
        & $dockerPath compose exec -T api python -m app.services.gtfs.cli register `
            --slug $feedSlug `
            --city-name "Delhi Buses" `
            --vehicle-positions-url "https://otd.delhi.gov.in/api/realtime/VehiclePositions.pb" `
            --api-key-env-var DELHI_TRANSIT_API_KEY `
            --api-key-query-param key `
            --enable-live-tracking
        if ($LASTEXITCODE -ne 0) {
            throw "Delhi live feed registration failed. Check 'docker compose logs api'."
        }
        $feed = (Invoke-RestMethod -Uri "$apiBaseUrl/api/v1/feeds/$feedSlug" -TimeoutSec 10).data
    } else {
        Write-Host "Delhi live bus feed is already registered."
    }

    $staticSlug = "delhi-buses"
    if (Test-Path -LiteralPath $archivePath -PathType Leaf) {
        $staticFeed = $feeds | Where-Object { $_.slug -eq $staticSlug } | Select-Object -First 1
        if (-not $staticFeed) {
            Write-Host "Registering the Delhi static schedule & routes feed..."
            & $dockerPath compose exec -T api python -m app.services.gtfs.cli register `
                --slug $staticSlug `
                --city-name "Delhi Buses (Schedule & Routes)" `
                --static-url "https://otd.delhi.gov.in/data/static/delhi-buses.zip"
            if ($LASTEXITCODE -ne 0) {
                throw "Delhi static feed registration failed. Check 'docker compose logs api'."
            }
            $staticFeed = (Invoke-RestMethod -Uri "$apiBaseUrl/api/v1/feeds/$staticSlug" -TimeoutSec 10).data
        }
        $shouldImport = $true
        if ($staticFeed.last_static_import_at) {
            $importedAt = [DateTimeOffset]::Parse($staticFeed.last_static_import_at).UtcDateTime
            $archiveModifiedAt = (Get-Item -LiteralPath $archivePath).LastWriteTimeUtc
            $shouldImport = $archiveModifiedAt -gt $importedAt.AddSeconds(2)
        }
        if ($shouldImport) {
            Write-Host "Importing the official Delhi bus GTFS archive into $staticSlug..."
            & $dockerPath compose exec -T api python -m app.services.gtfs.cli ingest `
                --slug $staticSlug `
                --file /data/gtfs/delhi-buses.zip `
                --batch-size 5000
            if ($LASTEXITCODE -ne 0) {
                throw "Static GTFS import failed. The current database was preserved; inspect the feed archive and retry."
            }
        } else {
            Write-Host "The current static archive has already been imported into $staticSlug."
        }
    } else {
        Write-Host "No full static archive found yet. Live positions can still run."
        Write-Host "After the portal releases the dataset, save it as data\gtfs\delhi-buses.zip and run this script again."
    }

    Write-Host "Waiting for the API's automatic Open Transit Data poll..."
    $vehicleCount = 0
    $deadline = (Get-Date).AddSeconds(120)
    while ((Get-Date) -lt $deadline) {
        try {
            $vehicleData = (Invoke-RestMethod -Uri "$apiBaseUrl/api/v1/feeds/$feedSlug/vehicles?limit=2000" -TimeoutSec 15).data
            $vehicleCount = @($vehicleData).Count
            if ($vehicleCount -gt 0) {
                break
            }
        } catch {
            # The first poll may still be running while the API finishes startup.
        }
        Start-Sleep -Seconds 3
    }
    if ($vehicleCount -eq 0) {
        throw "No fresh Delhi vehicle positions appeared within 120 seconds. Check 'docker compose logs api'; the live feed is not yet verified."
    }
    if ($vehicleCount -eq 2000) {
        Write-Host "Current live vehicle positions: at least 2000 (the map API display limit)."
    } else {
        Write-Host "Current live vehicle positions: $vehicleCount"
    }
    Write-Host "Open the WaitWatch web app at http://localhost:3000/"
} finally {
    Pop-Location
}
