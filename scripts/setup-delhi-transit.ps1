<#
.SYNOPSIS
    Automated and idempotent setup script for WaitWatch transit tracking application.

.DESCRIPTION
    Checks prerequisites (PowerShell, Docker Desktop & Engine), validates .env configuration,
    locates/validates static GTFS archives, builds and starts Docker services, applies
    migrations, performs idempotent dual-feed registration/ingestion, and verifies stack health.

.PARAMETER ArchivePath
    Optional manual path to a local GTFS zip archive (e.g. C:\Downloads\delhi_buses_static_gtfs_v1.zip).

.PARAMETER StaticFeedUrl
    Optional direct download URL for an authorized static GTFS archive.

.PARAMETER ExpectedSha256
    Optional expected SHA-256 checksum for GTFS archive verification.

.PARAMETER DownloadStaticFeed
    Switch to trigger automated download of the static GTFS archive using configured or default URL.

.PARAMETER SkipBuild
    Skip container image build step and start existing container images directly.

.PARAMETER ForceImport
    Force static GTFS ingestion even if the archive has already been imported into the database.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$ArchivePath = "",

    [Parameter(Mandatory = $false)]
    [string]$StaticFeedUrl = "",

    [Parameter(Mandatory = $false)]
    [string]$ExpectedSha256 = "",

    [Parameter(Mandatory = $false)]
    [switch]$DownloadStaticFeed,

    [Parameter(Mandatory = $false)]
    [switch]$SkipBuild,

    [Parameter(Mandatory = $false)]
    [switch]$ForceImport
)

$ErrorActionPreference = "Stop"

# Ensure ZIP compression assembly is loaded for archive validation
Add-Type -AssemblyName System.IO.Compression.FileSystem

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envFile = Join-Path $projectRoot ".env"
$envExampleFile = Join-Path $projectRoot ".env.example"
$gtfsDirectory = Join-Path $projectRoot "data\gtfs"
$defaultArchivePath = Join-Path $gtfsDirectory "delhi-buses.zip"
$apiBaseUrl = "http://localhost:8000"
$liveFeedSlug = "delhi-bus"
$staticFeedSlug = "delhi-buses"

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

function Get-EnvValue {
    param([string]$FilePath, [string]$Key)
    if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) { return $null }
    $match = Get-Content -LiteralPath $FilePath | Where-Object { $_ -match "^\s*$Key\s*=" } | Select-Object -Last 1
    if ($match) {
        return ($match -split "=", 2)[1].Trim().Trim('"').Trim("'")
    }
    return $null
}

function Set-EnvValue {
    param([string]$FilePath, [string]$Key, [string]$Value)
    $lines = if (Test-Path -LiteralPath $FilePath -PathType Leaf) { Get-Content -LiteralPath $FilePath } else { @() }
    $found = $false
    $newLines = @()
    foreach ($line in $lines) {
        if ($line -match "^\s*$Key\s*=") {
            $newLines += "$Key=$Value"
            $found = $true
        } else {
            $newLines += $line
        }
    }
    if (-not $found) {
        $newLines += "$Key=$Value"
    }
    Set-Content -LiteralPath $FilePath -Value $newLines -Encoding UTF8
}

function Test-GTFSArchive {
    param(
        [string]$Path,
        [string]$ExpectedHash = ""
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "GTFS archive not found at: $Path"
    }

    $fileInfo = Get-Item -LiteralPath $Path
    if ($fileInfo.Length -eq 0) {
        throw "GTFS archive at '$Path' is an empty file (0 bytes)."
    }

    # Verify SHA-256 checksum if configured
    if (-not [string]::IsNullOrWhiteSpace($ExpectedHash)) {
        Write-Host "Verifying archive SHA-256 checksum..."
        $actualHash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLower()
        $expectedClean = $ExpectedHash.Trim().ToLower()
        if ($actualHash -ne $expectedClean) {
            throw "Archive SHA-256 checksum mismatch! Expected: $expectedClean, Actual: $actualHash"
        }
        Write-Host " [OK] Checksum verified: $actualHash" -ForegroundColor Green
    }

    # Verify ZIP integrity and required GTFS tables
    Write-Host "Inspecting GTFS archive integrity and required files..."
    $requiredFiles = @("agency.txt", "routes.txt", "stops.txt", "trips.txt", "stop_times.txt")
    $zip = $null
    try {
        $zip = [System.IO.Compression.ZipFile]::OpenRead($Path)
        $entryNames = @($zip.Entries | Where-Object { -not $_.FullName.StartsWith("__MACOSX") -and -not $_.Name.StartsWith("._") } | ForEach-Object { $_.Name.ToLower() })

        $missingFiles = @()
        foreach ($req in $requiredFiles) {
            if (-not ($entryNames -contains $req)) {
                $missingFiles += $req
            }
        }
        if ($missingFiles.Count -gt 0) {
            throw "GTFS archive is missing required schema files: $($missingFiles -join ', ')"
        }
        Write-Host " [OK] Archive integrity verified (Found $($entryNames.Count) entries, all required GTFS tables present)." -ForegroundColor Green
        return $true
    } catch [System.IO.InvalidDataException] {
        throw "GTFS archive at '$Path' is corrupt or not a valid ZIP archive: $_"
    } finally {
        if ($zip) { $zip.Dispose() }
    }
}

function Download-ArchiveFile {
    param(
        [string]$Url,
        [string]$DestinationPath
    )

    $parentDir = Split-Path -Parent $DestinationPath
    if (-not (Test-Path -LiteralPath $parentDir)) {
        New-Item -ItemType Directory -Force -Path $parentDir | Out-Null
    }

    $partPath = "$DestinationPath.part"
    if (Test-Path -LiteralPath $partPath) {
        Remove-Item -LiteralPath $partPath -Force -ErrorAction SilentlyContinue
    }

    Write-Host "Downloading GTFS archive from $Url..."
    try {
        Invoke-WebRequest -Uri $Url -OutFile $partPath -TimeoutSec 120
        if (-not (Test-Path -LiteralPath $partPath -PathType Leaf)) {
            throw "Downloaded file was not created on disk."
        }
        $partSize = (Get-Item -LiteralPath $partPath).Length
        if ($partSize -lt 1024) {
            $sample = Get-Content -LiteralPath $partPath -Raw -ErrorAction SilentlyContinue
            if ($sample -match "(<!DOCTYPE html|<html|<head|login|auth)") {
                throw "Remote URL returned an HTML page (portal login or agreement required) rather than a ZIP archive."
            }
        }
        if (Test-Path -LiteralPath $DestinationPath) {
            Remove-Item -LiteralPath $DestinationPath -Force
        }
        Move-Item -LiteralPath $partPath -Destination $DestinationPath -Force
        Write-Host " [OK] Download complete: $partSize bytes." -ForegroundColor Green
        return $DestinationPath
    } catch {
        if (Test-Path -LiteralPath $partPath) {
            Remove-Item -LiteralPath $partPath -Force -ErrorAction SilentlyContinue
        }
        throw "Failed to download static GTFS archive: $_"
    }
}

# -----------------------------------------------------------------------------
# Main Setup Execution (runs when script is executed, not dot-sourced)
# -----------------------------------------------------------------------------

if ($MyInvocation.InvocationName -ne '.') {
    Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "WaitWatch — Automated Transit Application Setup" -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan

if ($PSVersionTable.PSVersion.Major -lt 5) {
    throw "PowerShell 5.1 or newer is required to run this setup script."
}

# Find docker CLI
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
    throw "Docker CLI (docker.exe) was not found in PATH or standard install directories. Please install Docker Desktop."
}

# Verify Docker engine is running
Write-Host "Checking Docker engine status..."
$engineReady = $false
try {
    $dockerInfo = & $dockerPath info --format "{{.ServerVersion}}" 2>$null
    if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($dockerInfo)) {
        $engineReady = $true
    }
} catch { }

if (-not $engineReady) {
    $desktopAppCandidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\Docker Desktop.exe"),
        (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe")
    )
    $desktopApp = $desktopAppCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if ($desktopApp) {
        Write-Host " [INFO] Docker engine is starting up. Waiting for engine readiness..." -ForegroundColor Yellow
        Start-Process $desktopApp -ErrorAction SilentlyContinue
        $waitDeadline = (Get-Date).AddSeconds(90)
        while ((Get-Date) -lt $waitDeadline) {
            Start-Sleep -Seconds 5
            try {
                $dockerInfo = & $dockerPath info --format "{{.ServerVersion}}" 2>$null
                if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($dockerInfo)) {
                    $engineReady = $true
                    break
                }
            } catch { }
        }
    }
}

if (-not $engineReady) {
    throw "Docker Desktop engine is not running. Please start Docker Desktop, ensure the WSL2/Linux engine is ready, and run this script again."
}
Write-Host " [OK] Docker engine is running (v$dockerInfo)." -ForegroundColor Green

# Ensure data/gtfs directory exists
if (-not (Test-Path -LiteralPath $gtfsDirectory)) {
    New-Item -ItemType Directory -Force -Path $gtfsDirectory | Out-Null
}

# -----------------------------------------------------------------------------
# 2. Environment Configuration Validation
# -----------------------------------------------------------------------------

Write-Host "Validating environment configuration (.env)..."

if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    if (Test-Path -LiteralPath $envExampleFile -PathType Leaf) {
        Write-Host " [INFO] .env file not found; copying template from .env.example..." -ForegroundColor Yellow
        Copy-Item -LiteralPath $envExampleFile -Destination $envFile
    } else {
        throw "Neither .env nor .env.example was found in $projectRoot."
    }
}

# Check POSTGRES_PASSWORD
$postgresPassword = Get-EnvValue -FilePath $envFile -Key "POSTGRES_PASSWORD"
if ([string]::IsNullOrWhiteSpace($postgresPassword) -or $postgresPassword -eq "replace_with_a_secure_password") {
    $generatedPassword = [System.Guid]::NewGuid().ToString("N").Substring(0, 24)
    Set-EnvValue -FilePath $envFile -Key "POSTGRES_PASSWORD" -Value $generatedPassword
    $dbUrl = "postgresql+asyncpg://waitwatch:$generatedPassword@db:5432/waitwatch"
    Set-EnvValue -FilePath $envFile -Key "DATABASE_URL" -Value $dbUrl
    Write-Host " [OK] Initialized local development database credentials in .env." -ForegroundColor Green
} else {
    Write-Host " [OK] Database credentials configured." -ForegroundColor Green
}

# Check DELHI_TRANSIT_API_KEY
$liveKey = Get-EnvValue -FilePath $envFile -Key "DELHI_TRANSIT_API_KEY"
$hasLiveKey = (-not [string]::IsNullOrWhiteSpace($liveKey) -and $liveKey -notmatch "^(your_|replace_)")
if ($hasLiveKey) {
    Write-Host " [OK] Delhi realtime API key configured (value not printed for security)." -ForegroundColor Green
} else {
    Write-Host " [NOTICE] DELHI_TRANSIT_API_KEY is not configured or using placeholder." -ForegroundColor Yellow
    Write-Host "   Real-time vehicle tracking ('delhi-bus') requires an authorized API key from https://otd.delhi.gov.in/." -ForegroundColor Yellow
    Write-Host "   Static schedules, routes, stops, and journey planner ('delhi-buses') remain fully functional." -ForegroundColor Yellow
}
Remove-Variable liveKey -ErrorAction SilentlyContinue

# Read static archive configuration from .env if not passed as CLI parameter
if ([string]::IsNullOrWhiteSpace($ArchivePath)) {
    $ArchivePath = Get-EnvValue -FilePath $envFile -Key "DELHI_GTFS_ARCHIVE_PATH"
}
if ([string]::IsNullOrWhiteSpace($StaticFeedUrl)) {
    $StaticFeedUrl = Get-EnvValue -FilePath $envFile -Key "DELHI_GTFS_STATIC_URL"
}
if ([string]::IsNullOrWhiteSpace($ExpectedSha256)) {
    $ExpectedSha256 = Get-EnvValue -FilePath $envFile -Key "DELHI_GTFS_STATIC_SHA256"
}

# -----------------------------------------------------------------------------
# 3. Static GTFS Archive Resolution & Validation
# -----------------------------------------------------------------------------

$resolvedArchive = $null

# Option A: Manual Archive Path provided
if (-not [string]::IsNullOrWhiteSpace($ArchivePath)) {
    $candidatePath = if ([System.IO.Path]::IsPathRooted($ArchivePath)) { $ArchivePath } else { Join-Path $projectRoot $ArchivePath }
    if (Test-Path -LiteralPath $candidatePath -PathType Leaf) {
        Write-Host "Using specified static GTFS archive: $candidatePath"
        Test-GTFSArchive -Path $candidatePath -ExpectedHash $ExpectedSha256
        $resolvedArchive = $candidatePath
    } else {
        throw "Specified archive path does not exist: $candidatePath"
    }
}

# Option B: Automated Download if requested or configured
if (-not $resolvedArchive -and ($DownloadStaticFeed -or -not [string]::IsNullOrWhiteSpace($StaticFeedUrl))) {
    $urlToDownload = if (-not [string]::IsNullOrWhiteSpace($StaticFeedUrl)) { $StaticFeedUrl } else { "https://otd.delhi.gov.in/data/static/delhi-buses.zip" }
    try {
        $downloadedFile = Download-ArchiveFile -Url $urlToDownload -DestinationPath $defaultArchivePath
        Test-GTFSArchive -Path $downloadedFile -ExpectedHash $ExpectedSha256
        $resolvedArchive = $downloadedFile
    } catch {
        Write-Host " [WARNING] Automated download could not complete: $_" -ForegroundColor Yellow
        Write-Host "   Please obtain the licensed GTFS static archive manually from https://delhi.transportstack.in/data-services" -ForegroundColor Yellow
    }
}

# Option C: Default workspace archive path
if (-not $resolvedArchive -and (Test-Path -LiteralPath $defaultArchivePath -PathType Leaf)) {
    Write-Host "Found default static GTFS archive: $defaultArchivePath"
    Test-GTFSArchive -Path $defaultArchivePath -ExpectedHash $ExpectedSha256
    $resolvedArchive = $defaultArchivePath
}

# Option D: Check user Downloads folder as convenience fallback
if (-not $resolvedArchive) {
    $userDownloads = Join-Path $env:USERPROFILE "Downloads\delhi_buses_static_gtfs_v1.zip"
    if (Test-Path -LiteralPath $userDownloads -PathType Leaf) {
        Write-Host "Found static GTFS archive in user Downloads: $userDownloads"
        Test-GTFSArchive -Path $userDownloads -ExpectedHash $ExpectedSha256
        $resolvedArchive = $userDownloads
    }
}

# Ensure resolved archive is staged at data/gtfs/delhi-buses.zip for Docker mount
if ($resolvedArchive) {
    if ((Resolve-Path $resolvedArchive).Path -ne (Resolve-Path $defaultArchivePath -ErrorAction SilentlyContinue)) {
        Write-Host "Staging archive into data/gtfs/delhi-buses.zip..."
        Copy-Item -LiteralPath $resolvedArchive -Destination $defaultArchivePath -Force
    }
    Write-Host " [OK] Static GTFS archive staged and validated for ingestion." -ForegroundColor Green
} else {
    Write-Host " [INFO] No static GTFS archive found yet." -ForegroundColor Cyan
    Write-Host "   To view static schedules, stops, and shapes, request the dataset from" -ForegroundColor Cyan
    Write-Host "   https://delhi.transportstack.in/data-services and save to data\gtfs\delhi-buses.zip" -ForegroundColor Cyan
}

# -----------------------------------------------------------------------------
# 4. Start Docker Infrastructure & Database Migrations
# -----------------------------------------------------------------------------

Push-Location $projectRoot
try {
    Write-Host "Starting WaitWatch infrastructure via Docker Compose..."
    $composeArgs = @("compose", "up", "-d")
    if (-not $SkipBuild) {
        $composeArgs += "--build"
    }
    & $dockerPath @composeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed to start services. Check 'docker compose ps' and 'docker compose logs'."
    }

    Write-Host "Waiting for database migration and API readiness..."
    $deadline = (Get-Date).AddSeconds(90)
    $healthy = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $health = Invoke-RestMethod -Uri "$apiBaseUrl/api/health" -TimeoutSec 5
            if ($health.status -eq "healthy" -and $health.database -eq "connected") {
                $healthy = $true
                break
            }
        } catch {
            Start-Sleep -Seconds 3
        }
    }
    if (-not $healthy) {
        throw "The WaitWatch API did not become healthy within 90 seconds. Inspect 'docker compose logs api'."
    }
    Write-Host " [OK] API and database are healthy." -ForegroundColor Green

    # -------------------------------------------------------------------------
    # 5. Idempotent Feed Registration & Ingestion
    # -------------------------------------------------------------------------

    $feedsResponse = Invoke-RestMethod -Uri "$apiBaseUrl/api/v1/feeds" -TimeoutSec 10
    $existingFeeds = @($feedsResponse.data)

    # 5.1 Real-time Tracking Feed (delhi-bus)
    $liveFeed = $existingFeeds | Where-Object { $_.slug -eq $liveFeedSlug } | Select-Object -First 1
    if (-not $liveFeed) {
        Write-Host "Registering real-time tracking feed ($liveFeedSlug)..."
        & $dockerPath compose exec -T api python -m app.services.gtfs.cli register `
            --slug $liveFeedSlug `
            --city-name "Delhi Buses" `
            --vehicle-positions-url "https://otd.delhi.gov.in/api/realtime/VehiclePositions.pb" `
            --api-key-env-var DELHI_TRANSIT_API_KEY `
            --api-key-query-param key `
            --enable-live-tracking `
            --allow-existing
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to register live feed '$liveFeedSlug'."
        }
        Write-Host " [OK] Feed '$liveFeedSlug' registered successfully." -ForegroundColor Green
    } else {
        Write-Host " [OK] Feed '$liveFeedSlug' (live tracking) is already registered." -ForegroundColor Green
    }

    # 5.2 Static Routes & Schedules Feed (delhi-buses)
    if (Test-Path -LiteralPath $defaultArchivePath -PathType Leaf) {
        $staticFeed = $existingFeeds | Where-Object { $_.slug -eq $staticFeedSlug } | Select-Object -First 1
        if (-not $staticFeed) {
            Write-Host "Registering static routes & schedules feed ($staticFeedSlug)..."
            & $dockerPath compose exec -T api python -m app.services.gtfs.cli register `
                --slug $staticFeedSlug `
                --city-name "Delhi Buses (Schedule & Routes)" `
                --static-url "https://otd.delhi.gov.in/data/static/delhi-buses.zip" `
                --allow-existing
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to register static feed '$staticFeedSlug'."
            }
            $staticFeed = (Invoke-RestMethod -Uri "$apiBaseUrl/api/v1/feeds/$staticFeedSlug" -TimeoutSec 10).data
        } else {
            Write-Host " [OK] Feed '$staticFeedSlug' is already registered." -ForegroundColor Green
        }

        # Check if ingestion is needed
        $shouldImport = $true
        if ($staticFeed.last_static_import_at -and -not $ForceImport) {
            $importedAt = [DateTimeOffset]::Parse($staticFeed.last_static_import_at).UtcDateTime
            $archiveModifiedAt = (Get-Item -LiteralPath $defaultArchivePath).LastWriteTimeUtc
            $shouldImport = $archiveModifiedAt -gt $importedAt.AddSeconds(2)
        }

        if ($shouldImport) {
            Write-Host "Ingesting static GTFS archive into '$staticFeedSlug' (this may take a few minutes)..."
            & $dockerPath compose exec -T api python -m app.services.gtfs.cli ingest `
                --slug $staticFeedSlug `
                --file /data/gtfs/delhi-buses.zip `
                --batch-size 5000
            if ($LASTEXITCODE -ne 0) {
                throw "Static GTFS ingestion failed. Existing database data was preserved."
            }
            Write-Host " [OK] Static GTFS data ingested successfully into '$staticFeedSlug'." -ForegroundColor Green
        } else {
            Write-Host " [OK] Feed '$staticFeedSlug' already contains imported static data. Skipping redundant re-ingestion." -ForegroundColor Green
            Write-Host "   (Run with -ForceImport to re-import)." -ForegroundColor Cyan
        }
    }

    # -------------------------------------------------------------------------
    # 6. Verification & Health Summary
    # -------------------------------------------------------------------------

    Write-Host "`nVerifying WaitWatch service endpoints..."
    $apiHealth = Invoke-RestMethod -Uri "$apiBaseUrl/api/health" -TimeoutSec 10
    $webResponse = Invoke-WebRequest -Uri "http://localhost:3000/" -UseBasicParsing -TimeoutSec 10

    if ($apiHealth.status -ne "healthy" -or $webResponse.StatusCode -ne 200) {
        throw "Application verification failed. API status: $($apiHealth.status), Web status: $($webResponse.StatusCode)"
    }

    # If live key is active, verify live vehicle count
    $vehicleCount = 0
    if ($hasLiveKey) {
        Write-Host "Checking live vehicle telemetry polling..."
        $pollDeadline = (Get-Date).AddSeconds(45)
        while ((Get-Date) -lt $pollDeadline) {
            try {
                $vData = (Invoke-RestMethod -Uri "$apiBaseUrl/api/v1/feeds/$liveFeedSlug/vehicles?limit=5" -TimeoutSec 10).data
                $vehicleCount = @($vData).Count
                if ($vehicleCount -gt 0) { break }
            } catch { }
            Start-Sleep -Seconds 3
        }
    }

    Write-Host "`n==============================================================" -ForegroundColor Green
    Write-Host "WaitWatch Setup Completed Successfully!" -ForegroundColor Green
    Write-Host "==============================================================" -ForegroundColor Green
    Write-Host "  Web Application:   http://localhost:3000/"
    Write-Host "  API Base URL:      http://localhost:8000/"
    Write-Host "  API Health Check:  http://localhost:8000/api/health"
    Write-Host "  Live Feed:         $liveFeedSlug $(if ($vehicleCount -gt 0) { "($vehicleCount active buses parsed)" } else { "(pending provider key or first poll)" })"
    Write-Host "  Static Feed:       $staticFeedSlug $(if (Test-Path -LiteralPath $defaultArchivePath) { "(routes, schedules, stops, shapes available)" } else { "(pending dataset download)" })"
    Write-Host "==============================================================" -ForegroundColor Green
        Write-Host "Open http://localhost:3000/ in your browser to begin exploring."
    } finally {
        Pop-Location
    }
}
