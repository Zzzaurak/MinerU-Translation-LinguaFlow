#!/usr/bin/env pwsh

# Boundary contract:
# - Authoritative entrypoint is Python module: python -m mineru_batch_cli
# - This script only does arg parsing/path resolution/forwarding
# - Do not implement translation business logic in PowerShell

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$script:ScriptDir = Split-Path -Path $MyInvocation.MyCommand.Path -Parent
$script:ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $script:ScriptDir ".."))

function Show-Usage {
    @"
Usage: translate-markdown.ps1 [options] [-- <extra-cli-args>]

Options:
  --input DIR                Input directory (default: inbox)
  --output DIR               Output directory (default: out)
  --config PATH              JSON config path (optional)
  --continue-on-error VALUE  true | false (default: true)
  -h, --help                 Show this help

Notes:
  - Python resolution order: MINERU_PYTHON_BIN, ./.venv/Scripts/python.exe, python3, python
  - Delegates to: python -m mineru_batch_cli translate
  - Extra unknown args are forwarded to CLI translate command
"@ | Write-Output
}

function Exit-WithError {
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [int]$Code = 1
    )

    [Console]::Error.WriteLine($Message)
    exit $Code
}

function Resolve-DirPath {
    param([Parameter(Mandatory = $true)][string]$PathValue)
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return [System.IO.Path]::GetFullPath($PathValue)
    }
    return [System.IO.Path]::GetFullPath((Join-Path (Get-Location).Path $PathValue))
}

function Resolve-FilePath {
    param([Parameter(Mandatory = $true)][string]$PathValue)
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return [System.IO.Path]::GetFullPath($PathValue)
    }
    return [System.IO.Path]::GetFullPath((Join-Path (Get-Location).Path $PathValue))
}

function Test-PythonCandidate {
    param(
        [Parameter(Mandatory = $true)][string]$Candidate,
        [Parameter(Mandatory = $true)][string]$SrcPath
    )

    if ([string]::IsNullOrWhiteSpace($Candidate)) {
        return $false
    }

    $resolvedCandidate = $null
    if ([System.IO.Path]::IsPathRooted($Candidate) -or $Candidate.Contains([System.IO.Path]::DirectorySeparatorChar) -or $Candidate.Contains([System.IO.Path]::AltDirectorySeparatorChar)) {
        if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) {
            return $false
        }
        $resolvedCandidate = (Resolve-Path -LiteralPath $Candidate).Path
    }
    else {
        $cmd = Get-Command -Name $Candidate -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -eq $cmd) {
            return $false
        }
        $resolvedCandidate = $cmd.Source
    }

    $oldPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = $SrcPath
    try {
        & $resolvedCandidate "-c" "import sys" *> $null
        if ($LASTEXITCODE -ne 0) {
            return $false
        }

        & $resolvedCandidate "-m" "mineru_batch_cli" "--help" *> $null
        if ($LASTEXITCODE -ne 0) {
            return $false
        }

        return $resolvedCandidate
    }
    finally {
        $env:PYTHONPATH = $oldPythonPath
    }
}

function Resolve-PythonBin {
    param([Parameter(Mandatory = $true)][string]$ProjectRootPath)

    $srcPath = Join-Path $ProjectRootPath "src"
    $candidates = @()

    if (-not [string]::IsNullOrWhiteSpace($env:MINERU_PYTHON_BIN)) {
        $candidates += $env:MINERU_PYTHON_BIN
    }
    $candidates += (Join-Path $ProjectRootPath ".venv/Scripts/python.exe")
    $candidates += "python3"
    $candidates += "python"

    foreach ($candidate in $candidates) {
        $usable = Test-PythonCandidate -Candidate $candidate -SrcPath $srcPath
        if ($usable) {
            return [string]$usable
        }
    }

    Exit-WithError -Message "Error: no usable Python interpreter found.`nHint: set MINERU_PYTHON_BIN, create .venv (python -m venv .venv), and install project dependencies." -Code 1
}

$inputDir = "inbox"
$outputDir = "out"
$continueOnError = "true"
$configPath = ""

$forwardArgs = @()
$argv = @($args)
$index = 0
while ($index -lt $argv.Count) {
    $arg = [string]$argv[$index]
    switch ($arg) {
        "--input" {
            if ($index + 1 -ge $argv.Count) {
                Exit-WithError -Message "Error: --input requires a value" -Code 2
            }
            $inputDir = [string]$argv[$index + 1]
            $index += 2
            continue
        }
        "--output" {
            if ($index + 1 -ge $argv.Count) {
                Exit-WithError -Message "Error: --output requires a value" -Code 2
            }
            $outputDir = [string]$argv[$index + 1]
            $index += 2
            continue
        }
        "--config" {
            if ($index + 1 -ge $argv.Count) {
                Exit-WithError -Message "Error: --config requires a value" -Code 2
            }
            $configPath = [string]$argv[$index + 1]
            $index += 2
            continue
        }
        "--continue-on-error" {
            if ($index + 1 -ge $argv.Count) {
                Exit-WithError -Message "Error: --continue-on-error requires a value" -Code 2
            }
            $continueOnError = [string]$argv[$index + 1]
            $index += 2
            continue
        }
        "-h" {
            Show-Usage
            exit 0
        }
        "--help" {
            Show-Usage
            exit 0
        }
        "--" {
            if ($index + 1 -lt $argv.Count) {
                $forwardArgs = @($argv[($index + 1)..($argv.Count - 1)])
            }
            else {
                $forwardArgs = @()
            }
            $index = $argv.Count
            continue
        }
        default {
            $forwardArgs = @($argv[$index..($argv.Count - 1)])
            $index = $argv.Count
            continue
        }
    }
}

$pythonBin = Resolve-PythonBin -ProjectRootPath $script:ProjectRoot
$srcDir = Join-Path $script:ProjectRoot "src"
if (-not (Test-Path -LiteralPath $srcDir -PathType Container)) {
    Exit-WithError -Message "Error: src directory not found under project root: $script:ProjectRoot" -Code 1
}

$inputDir = Resolve-DirPath -PathValue $inputDir
$outputDir = Resolve-DirPath -PathValue $outputDir

if (-not (Test-Path -LiteralPath $inputDir -PathType Container)) {
    Exit-WithError -Message "Error: Input directory does not exist: $inputDir" -Code 1
}

$cmdArgs = @("-m", "mineru_batch_cli", "translate", "--input", $inputDir, "--output", $outputDir, "--continue-on-error", $continueOnError)

if (-not [string]::IsNullOrWhiteSpace($configPath)) {
    $configPath = Resolve-FilePath -PathValue $configPath
    if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
        Exit-WithError -Message "Error: Config file not found: $configPath" -Code 1
    }
    $cmdArgs += @("--config", $configPath)
}

if ($forwardArgs.Count -gt 0) {
    $cmdArgs += $forwardArgs
}

$oldPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = $srcDir
try {
    & $pythonBin @cmdArgs
    exit $LASTEXITCODE
}
finally {
    $env:PYTHONPATH = $oldPythonPath
}
