# === Get system disk ===
$disk = Get-Disk | Where-Object PartitionStyle -eq 'GPT' | Where-Object IsSystem -eq $true
if (-not $disk) { $disk = Get-Disk | Where-Object Number -eq 0 }

$diskNumber = $disk.Number
Write-Host "Disk: $diskNumber"

# === Get partitions ===
$parts = Get-Partition -DiskNumber $diskNumber

Write-Host "=== Initial Partition layout ==="
$parts | Format-Table PartitionNumber, Type, GptType, Size, DriveLetter

# === Detect recovery partition ===
$recoveryGuid = 'de94bba4-06d1-4d40-a16a-bfd50179d6ac'

$recovery = $parts | Where-Object {
    $_.Type -eq 'Recovery' -or
    $_.GptType -eq $recoveryGuid -or
    ($_.Size -lt 2000MB -and -not $_.DriveLetter -and $_.Type -ne 'System')
}

# === Detect OS partition ===
$os = $parts | Where-Object DriveLetter -eq 'C'
if (-not $os) { Write-Host "ERROR: OS partition not found"; exit 1 }

# === Backup WinRE from existing recovery partition ===
Write-Host "Backing up WinRE from recovery partition..."

$recoveryGuid = '{DE94BBA4-06D1-4D40-A16A-BFD50179D6AC}'

$recovery = Get-Partition -DiskNumber $diskNumber | Where-Object {
    $_.GptType -eq $recoveryGuid -or $_.Type -eq 'Recovery'
}

$backupPath = "$env:WINDIR\System32\Recovery"
New-Item -ItemType Directory -Path $backupPath -Force | Out-Null

if ($recovery) {
    foreach ($part in $recovery) {

        $tempLetter = "R"

        Write-Host "Assigning temporary drive letter to partition $($part.PartitionNumber)..."

        Set-Partition `
            -DiskNumber $diskNumber `
            -PartitionNumber $part.PartitionNumber `
            -NewDriveLetter $tempLetter

        Start-Sleep -Seconds 2

        $source = "$tempLetter`:\Recovery\WindowsRE\Winre.wim"

        if (Test-Path $source) {
            Copy-Item $source "$backupPath\Winre.wim" -Force
            Write-Host "Winre.wim backed up successfully"
        } else {
            Write-Host "WARNING: Winre.wim not found on recovery partition"
        }

        # Remove temporary drive letter
        Remove-PartitionAccessPath `
            -DiskNumber $diskNumber `
            -PartitionNumber $part.PartitionNumber `
            -AccessPath "$tempLetter`:"
    }
} else {
    Write-Host "No recovery partition found to back up"
}

# === Remove existing recovery ===
if ($recovery) {
    Write-Host "Removing existing recovery partition..."
    $recovery | ForEach-Object {
        Remove-Partition -DiskNumber $diskNumber -PartitionNumber $_.PartitionNumber -Confirm:$false
    }
}

Start-Sleep 2

# Refresh OS partition
$os = Get-Partition -DiskNumber $diskNumber | Where-Object DriveLetter -eq 'C'

# === Extend OS fully ===
$size = Get-PartitionSupportedSize -DiskNumber $diskNumber -PartitionNumber $os.PartitionNumber

if ($size.SizeMax -gt $os.Size) {
    Write-Host "Extending OS partition..."
    Resize-Partition -DiskNumber $diskNumber -PartitionNumber $os.PartitionNumber -Size $size.SizeMax
}

# === Recreate WinRE folder ===
Write-Host "Configuring WinRE in folder..."

$winrePath = "C:\Recovery\WindowsRE"
New-Item -Path $winrePath -ItemType Directory -Force | Out-Null

$source = "$env:WINDIR\System32\Recovery\Winre.wim"

if (-not (Test-Path $source)) {
    Write-Host "Winre.wim not found, forcing regeneration..."
    reagentc /disable | Out-Null
    reagentc /enable | Out-Null
    Start-Sleep -Seconds 3
}

if (Test-Path $source) {
    Copy-Item $source $winrePath -Force
    Write-Host "Winre.wim copied successfully"
} else {
    Write-Host "WARNING: Winre.wim still missing"
}

reagentc /disable | Out-Null
reagentc /setreimage /path $winrePath | Out-Null
reagentc /enable | Out-Null

# === Hide folder ===
attrib +h +s C:\Recovery

Write-Host "Done."
