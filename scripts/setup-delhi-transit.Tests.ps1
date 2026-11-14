# Pester tests for WaitWatch setup script functions

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$setupScript = Join-Path $scriptDir "setup-delhi-transit.ps1"

# Dot-source the setup script to import functions
. $setupScript

Describe "WaitWatch Setup Script Unit Tests" {

    Context "Environment Value Helpers" {
        $testEnvFile = Join-Path ([System.IO.Path]::GetTempPath()) "waitwatch_test_$([System.Guid]::NewGuid().ToString('N')).env"

        AfterEach {
            if (Test-Path -LiteralPath $testEnvFile) {
                Remove-Item -LiteralPath $testEnvFile -Force -ErrorAction SilentlyContinue
            }
        }

        It "Reads existing environment keys safely" {
            Set-Content -LiteralPath $testEnvFile -Value "POSTGRES_USER=myuser`nPOSTGRES_PASSWORD=secret"
            (Get-EnvValue -FilePath $testEnvFile -Key "POSTGRES_USER") | Should Be "myuser"
            (Get-EnvValue -FilePath $testEnvFile -Key "POSTGRES_PASSWORD") | Should Be "secret"
            (Get-EnvValue -FilePath $testEnvFile -Key "NON_EXISTENT") | Should BeNullOrEmpty
        }

        It "Updates existing keys and appends new keys" {
            Set-Content -LiteralPath $testEnvFile -Value "KEY_A=original"
            Set-EnvValue -FilePath $testEnvFile -Key "KEY_A" -Value "updated"
            Set-EnvValue -FilePath $testEnvFile -Key "KEY_B" -Value "new_value"

            (Get-EnvValue -FilePath $testEnvFile -Key "KEY_A") | Should Be "updated"
            (Get-EnvValue -FilePath $testEnvFile -Key "KEY_B") | Should Be "new_value"
        }
    }

    Context "GTFS Archive Validation" {
        BeforeAll {
            $script:tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "waitwatch_gtfs_test_$([System.Guid]::NewGuid().ToString('N'))"
            New-Item -ItemType Directory -Force -Path $script:tempDir | Out-Null
        }

        AfterAll {
            if (Test-Path -LiteralPath $script:tempDir) {
                Remove-Item -LiteralPath $script:tempDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Throws when archive file does not exist" {
            $missingPath = Join-Path $script:tempDir "missing.zip"
            { Test-GTFSArchive -Path $missingPath } | Should Throw "not found"
        }

        It "Throws when archive file is empty" {
            $emptyPath = Join-Path $script:tempDir "empty.zip"
            [System.IO.File]::WriteAllBytes($emptyPath, [byte[]]@())
            { Test-GTFSArchive -Path $emptyPath } | Should Throw "empty file"
        }

        It "Throws when archive file is corrupt" {
            $corruptPath = Join-Path $script:tempDir "corrupt.zip"
            Set-Content -LiteralPath $corruptPath -Value "PK0304NotARealZipArchive"
            { Test-GTFSArchive -Path $corruptPath } | Should Throw "corrupt"
        }

        It "Throws on checksum mismatch" {
            $sampleZip = Join-Path $script:tempDir "sample.zip"
            # Create a simple zip file
            $zip = [System.IO.Compression.ZipFile]::Open($sampleZip, [System.IO.Compression.ZipArchiveMode]::Create)
            $zip.Dispose()

            $wrongHash = "0000000000000000000000000000000000000000000000000000000000000000"
            { Test-GTFSArchive -Path $sampleZip -ExpectedHash $wrongHash } | Should Throw "checksum mismatch"
        }

        It "Throws when required GTFS tables are missing" {
            $incompleteZip = Join-Path $script:tempDir "incomplete.zip"
            $zip = [System.IO.Compression.ZipFile]::Open($incompleteZip, [System.IO.Compression.ZipArchiveMode]::Create)
            $entry = $zip.CreateEntry("agency.txt")
            $writer = New-Object System.IO.StreamWriter($entry.Open())
            $writer.WriteLine("agency_name,agency_url,agency_timezone`nTest,http://test.com,UTC")
            $writer.Dispose()
            $zip.Dispose()

            { Test-GTFSArchive -Path $incompleteZip } | Should Throw "missing required schema files"
        }

        It "Succeeds when all 5 required GTFS tables are present" {
            $validZip = Join-Path $script:tempDir "valid.zip"
            $zip = [System.IO.Compression.ZipFile]::Open($validZip, [System.IO.Compression.ZipArchiveMode]::Create)
            foreach ($file in @("agency.txt", "routes.txt", "stops.txt", "trips.txt", "stop_times.txt")) {
                $entry = $zip.CreateEntry($file)
                $writer = New-Object System.IO.StreamWriter($entry.Open())
                $writer.WriteLine("header1,header2`nval1,val2")
                $writer.Dispose()
            }
            $zip.Dispose()

            (Test-GTFSArchive -Path $validZip) | Should Be $true

            # Also verify with matching hash
            $hash = (Get-FileHash -LiteralPath $validZip -Algorithm SHA256).Hash
            (Test-GTFSArchive -Path $validZip -ExpectedHash $hash) | Should Be $true
        }
    }
}
