# Fix DPI Scaling for Electron Apps
# This script fixes blurred/scrambled text in Electron-based applications on high-DPI displays
# by configuring Windows DPI awareness settings and per-app overrides.

param(
    [switch]$Restore,
    [string]$BackupFile = "dpi-settings-backup-$(Get-Date -Format 'yyyyMMdd-HHmmss').json",
    [switch]$SystemEnhanced
)

# Requires administrator privileges for registry modifications
#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"

# Debug logging
$DebugLogPath = Join-Path $PSScriptRoot ".cursor\debug.log"
$SessionId = "debug-session-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

function Write-DebugLog {
    param(
        [string]$Location,
        [string]$Message,
        [hashtable]$Data = @{},
        [string]$HypothesisId = ""
    )
    $logEntry = @{
        sessionId = $SessionId
        runId = "run1"
        hypothesisId = $HypothesisId
        location = $Location
        message = $Message
        data = $Data
        timestamp = [DateTimeOffset]::Now.ToUnixTimeMilliseconds()
    } | ConvertTo-Json -Compress
    try {
        $logDir = Split-Path -Path $DebugLogPath -Parent
        if (-not (Test-Path $logDir)) {
            New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        }
        $logEntry | Out-File -FilePath $DebugLogPath -Append -Encoding UTF8 -ErrorAction Stop
    } catch {
        Write-Host "DEBUG LOG ERROR: $_" -ForegroundColor Red
    }
}

# Registry paths
$DesktopRegPath = "HKCU:\Control Panel\Desktop"
$AppCompatRegPath = "HKCU:\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"

# Known Electron app paths
$ElectronApps = @(
    @{
        Name = "Docker Desktop"
        Path = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        AltPath = "${env:ProgramFiles(x86)}\Docker\Docker\Docker Desktop.exe"
    },
    @{
        Name = "ChatGPT"
        Path = "$env:LOCALAPPDATA\Programs\ChatGPT\ChatGPT.exe"
    },
    @{
        Name = "VS Code"
        Path = "$env:LOCALAPPDATA\Programs\Microsoft VS Code\Code.exe"
    }
)

# DPI override flags (default: High DPI aware; optional: System (Enhanced))
if ($SystemEnhanced) {
    $DPIOverrideFlags = "~ HIGHDPIAWARE DPIUNAWARE"
} else {
    $DPIOverrideFlags = "~ HIGHDPIAWARE"
}

function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Backup-RegistrySettings {
    Write-ColorOutput "Creating backup of current registry settings..." "Yellow"
    
    $backup = @{
        Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        SystemWide = @{}
        PerApp = @{}
    }
    
    # Backup system-wide DPI settings
    try {
        if (Test-Path $DesktopRegPath) {
            $win8DpiScaling = Get-ItemProperty -Path $DesktopRegPath -Name "Win8DpiScaling" -ErrorAction SilentlyContinue
            $dpiScalingVer = Get-ItemProperty -Path $DesktopRegPath -Name "DPIScalingVer" -ErrorAction SilentlyContinue
            
            if ($win8DpiScaling) {
                $backup.SystemWide.Win8DpiScaling = $win8DpiScaling.Win8DpiScaling
            }
            if ($dpiScalingVer) {
                $backup.SystemWide.DPIScalingVer = $dpiScalingVer.DPIScalingVer
            }
        }
    } catch {
        Write-ColorOutput "Warning: Could not backup system-wide settings: $_" "Yellow"
    }
    
    # Backup per-app overrides
    try {
        if (Test-Path $AppCompatRegPath) {
            $layers = Get-ItemProperty -Path $AppCompatRegPath -ErrorAction SilentlyContinue
            if ($layers) {
                $layerProps = $layers.PSObject.Properties | Where-Object { 
                    $_.Name -notlike "PS*" -and $_.Name -ne "Path" 
                }
                foreach ($prop in $layerProps) {
                    $backup.PerApp[$prop.Name] = $prop.Value
                }
            }
        }
    } catch {
        Write-ColorOutput "Warning: Could not backup per-app settings: $_" "Yellow"
    }
    
    # Save backup to file
    $backupFile = Join-Path $PSScriptRoot $BackupFile
    $backup | ConvertTo-Json -Depth 10 | Out-File -FilePath $backupFile -Encoding UTF8
    
    Write-ColorOutput "Backup saved to: $backupFile" "Green"
    return $backupFile
}

function Restore-RegistrySettings {
    param([string]$BackupFilePath)
    
    if (-not (Test-Path $BackupFilePath)) {
        Write-ColorOutput "Error: Backup file not found: $BackupFilePath" "Red"
        return $false
    }
    
    Write-ColorOutput "Restoring registry settings from backup..." "Yellow"
    
    try {
        $backup = Get-Content -Path $BackupFilePath -Raw | ConvertFrom-Json
        
        # Restore system-wide settings
        if ($backup.SystemWide) {
            if ($backup.SystemWide.Win8DpiScaling -ne $null) {
                Set-ItemProperty -Path $DesktopRegPath -Name "Win8DpiScaling" -Value $backup.SystemWide.Win8DpiScaling -ErrorAction SilentlyContinue
            } else {
                Remove-ItemProperty -Path $DesktopRegPath -Name "Win8DpiScaling" -ErrorAction SilentlyContinue
            }
            
            if ($backup.SystemWide.DPIScalingVer -ne $null) {
                Set-ItemProperty -Path $DesktopRegPath -Name "DPIScalingVer" -Value $backup.SystemWide.DPIScalingVer -ErrorAction SilentlyContinue
            } else {
                Remove-ItemProperty -Path $DesktopRegPath -Name "DPIScalingVer" -ErrorAction SilentlyContinue
            }
        }
        
        # Restore per-app overrides
        if ($backup.PerApp) {
            if (-not (Test-Path $AppCompatRegPath)) {
                New-Item -Path $AppCompatRegPath -Force | Out-Null
            }
            
            # Remove all current overrides
            $currentLayers = Get-ItemProperty -Path $AppCompatRegPath -ErrorAction SilentlyContinue
            if ($currentLayers) {
                $layerProps = $currentLayers.PSObject.Properties | Where-Object { 
                    $_.Name -notlike "PS*" -and $_.Name -ne "Path" 
                }
                foreach ($prop in $layerProps) {
                    Remove-ItemProperty -Path $AppCompatRegPath -Name $prop.Name -ErrorAction SilentlyContinue
                }
            }
            
            # Restore backed up overrides
            foreach ($appPath in $backup.PerApp.PSObject.Properties) {
                Set-ItemProperty -Path $AppCompatRegPath -Name $appPath.Name -Value $appPath.Value -ErrorAction SilentlyContinue
            }
        }
        
        Write-ColorOutput "Registry settings restored successfully!" "Green"
        return $true
    } catch {
        Write-ColorOutput "Error restoring settings: $_" "Red"
        return $false
    }
}

function Get-CurrentDPISettings {
    Write-ColorOutput "`nCurrent DPI Settings:" "Cyan"
    Write-ColorOutput "====================" "Cyan"
    
    #region agent log
    Write-DebugLog -Location "Get-CurrentDPISettings:entry" -Message "Reading current DPI settings" -Data @{DesktopRegPath=$DesktopRegPath} -HypothesisId "H2"
    #endregion
    
    try {
        $pathExists = Test-Path $DesktopRegPath
        #region agent log
        Write-DebugLog -Location "Get-CurrentDPISettings:pathCheck" -Message "Desktop registry path exists check" -Data @{PathExists=$pathExists; Path=$DesktopRegPath} -HypothesisId "H2"
        #endregion
        
        if ($pathExists) {
            $win8DpiScaling = Get-ItemProperty -Path $DesktopRegPath -Name "Win8DpiScaling" -ErrorAction SilentlyContinue
            $dpiScalingVer = Get-ItemProperty -Path $DesktopRegPath -Name "DPIScalingVer" -ErrorAction SilentlyContinue
            
            #region agent log
            Write-DebugLog -Location "Get-CurrentDPISettings:readValues" -Message "Read registry values BEFORE changes" -Data @{Win8DpiScaling=$win8DpiScaling.Win8DpiScaling; DPIScalingVer=$dpiScalingVer.DPIScalingVer} -HypothesisId "H2"
            #endregion
            
            Write-ColorOutput "Win8DpiScaling: $($win8DpiScaling.Win8DpiScaling)" "White"
            Write-ColorOutput "DPIScalingVer: $($dpiScalingVer.DPIScalingVer)" "White"
        } else {
            Write-ColorOutput "Desktop registry path not found" "Yellow"
        }
    } catch {
        Write-ColorOutput "Could not read current DPI settings: $_" "Yellow"
        #region agent log
        Write-DebugLog -Location "Get-CurrentDPISettings:error" -Message "Error reading DPI settings" -Data @{Error=$_.ToString()} -HypothesisId "H2"
        #endregion
    }
}

function Set-SystemWideDPISettings {
    Write-ColorOutput "`nSetting system-wide DPI awareness..." "Yellow"
    
    #region agent log
    Write-DebugLog -Location "Set-SystemWideDPISettings:entry" -Message "Setting system-wide DPI settings" -Data @{DesktopRegPath=$DesktopRegPath} -HypothesisId "H1"
    #endregion
    
    try {
        # Ensure registry path exists
        $pathExistsBefore = Test-Path $DesktopRegPath
        #region agent log
        Write-DebugLog -Location "Set-SystemWideDPISettings:beforeWrite" -Message "Registry path check before write" -Data @{PathExists=$pathExistsBefore} -HypothesisId "H1"
        #endregion
        
        if (-not $pathExistsBefore) {
            New-Item -Path $DesktopRegPath -Force | Out-Null
        }
        
        # Set Win8DpiScaling = 1
        #region agent log
        Write-DebugLog -Location "Set-SystemWideDPISettings:writeWin8" -Message "Writing Win8DpiScaling=1" -Data @{Value=1; Type="DWord"} -HypothesisId "H1"
        #endregion
        Set-ItemProperty -Path $DesktopRegPath -Name "Win8DpiScaling" -Value 1 -Type DWord
        Write-ColorOutput "  ✓ Set Win8DpiScaling = 1" "Green"
        
        # Set DPIScalingVer = 0
        #region agent log
        Write-DebugLog -Location "Set-SystemWideDPISettings:writeDPI" -Message "Writing DPIScalingVer=0" -Data @{Value=0; Type="DWord"} -HypothesisId "H1"
        #endregion
        Set-ItemProperty -Path $DesktopRegPath -Name "DPIScalingVer" -Value 0 -Type DWord
        Write-ColorOutput "  ✓ Set DPIScalingVer = 0" "Green"
        
        # Verify values were written correctly
        $win8After = Get-ItemProperty -Path $DesktopRegPath -Name "Win8DpiScaling" -ErrorAction SilentlyContinue
        $dpiAfter = Get-ItemProperty -Path $DesktopRegPath -Name "DPIScalingVer" -ErrorAction SilentlyContinue
        #region agent log
        Write-DebugLog -Location "Set-SystemWideDPISettings:verifyAfter" -Message "Verifying registry values AFTER write" -Data @{Win8DpiScaling=$win8After.Win8DpiScaling; DPIScalingVer=$dpiAfter.DPIScalingVer} -HypothesisId "H1"
        #endregion
        
        Write-ColorOutput "System-wide DPI settings configured successfully!" "Green"
    } catch {
        Write-ColorOutput "Error setting system-wide DPI settings: $_" "Red"
        #region agent log
        Write-DebugLog -Location "Set-SystemWideDPISettings:error" -Message "Error writing system-wide DPI settings" -Data @{Error=$_.ToString()} -HypothesisId "H1"
        #endregion
        throw
    }
}

function Find-InstalledElectronApps {
    Write-ColorOutput "`nDetecting installed Electron apps..." "Yellow"
    
    #region agent log
    Write-DebugLog -Location "Find-InstalledElectronApps:entry" -Message "Detecting Electron apps" -Data @{AppCount=$ElectronApps.Count} -HypothesisId "H3"
    #endregion
    
    $foundApps = @()
    
    foreach ($app in $ElectronApps) {
        $found = $false
        $appPath = $null
        
        # Check primary path
        $primaryExists = Test-Path $app.Path
        #region agent log
        Write-DebugLog -Location "Find-InstalledElectronApps:checkPrimary" -Message "Checking primary app path" -Data @{AppName=$app.Name; Path=$app.Path; Exists=$primaryExists} -HypothesisId "H3"
        #endregion
        
        if ($primaryExists) {
            $appPath = $app.Path
            $found = $true
        }
        # Check alternate path if available
        elseif ($app.AltPath) {
            $altExists = Test-Path $app.AltPath
            #region agent log
            Write-DebugLog -Location "Find-InstalledElectronApps:checkAlt" -Message "Checking alternate app path" -Data @{AppName=$app.Name; AltPath=$app.AltPath; Exists=$altExists} -HypothesisId "H3"
            #endregion
            if ($altExists) {
                $appPath = $app.AltPath
                $found = $true
            }
        }
        
        if ($found) {
            Write-ColorOutput "  ✓ Found: $($app.Name) at $appPath" "Green"
            #region agent log
            Write-DebugLog -Location "Find-InstalledElectronApps:found" -Message "App found" -Data @{AppName=$app.Name; FinalPath=$appPath} -HypothesisId "H3"
            #endregion
            $foundApps += @{
                Name = $app.Name
                Path = $appPath
            }
        } else {
            Write-ColorOutput "  ✗ Not found: $($app.Name)" "Gray"
        }
    }
    
    #region agent log
    Write-DebugLog -Location "Find-InstalledElectronApps:exit" -Message "App detection complete" -Data @{FoundCount=$foundApps.Count} -HypothesisId "H3"
    #endregion
    
    return $foundApps
}

function Set-PerAppDPIOverrides {
    param([array]$Apps)
    
    Write-ColorOutput "`nSetting per-app DPI overrides..." "Yellow"
    
    #region agent log
    Write-DebugLog -Location "Set-PerAppDPIOverrides:entry" -Message "Setting per-app DPI overrides" -Data @{AppCount=$Apps.Count; DPIOverrideFlags=$DPIOverrideFlags; AppCompatRegPath=$AppCompatRegPath} -HypothesisId "H1,H3,H4"
    #endregion
    
    try {
        # Ensure registry path exists
        $pathExistsBefore = Test-Path $AppCompatRegPath
        #region agent log
        Write-DebugLog -Location "Set-PerAppDPIOverrides:pathCheck" -Message "AppCompat registry path check" -Data @{PathExists=$pathExistsBefore; Path=$AppCompatRegPath} -HypothesisId "H1"
        #endregion
        
        if (-not $pathExistsBefore) {
            New-Item -Path $AppCompatRegPath -Force | Out-Null
        }
        
        foreach ($app in $Apps) {
            try {
                # Read existing value before write
                $existingValue = Get-ItemProperty -Path $AppCompatRegPath -Name $app.Path -ErrorAction SilentlyContinue
                #region agent log
                Write-DebugLog -Location "Set-PerAppDPIOverrides:beforeWrite" -Message "Before writing app override" -Data @{AppName=$app.Name; AppPath=$app.Path; ExistingValue=$existingValue.$($app.Path)} -HypothesisId "H1,H4"
                #endregion
                
                #region agent log
                Write-DebugLog -Location "Set-PerAppDPIOverrides:write" -Message "Writing app DPI override" -Data @{AppName=$app.Name; AppPath=$app.Path; Value=$DPIOverrideFlags; Type="String"} -HypothesisId "H1,H4"
                #endregion
                Set-ItemProperty -Path $AppCompatRegPath -Name $app.Path -Value $DPIOverrideFlags -Type String
                
                # Verify value was written correctly
                $verifyValue = Get-ItemProperty -Path $AppCompatRegPath -Name $app.Path -ErrorAction SilentlyContinue
                #region agent log
                Write-DebugLog -Location "Set-PerAppDPIOverrides:verifyAfter" -Message "Verifying app override AFTER write" -Data @{AppName=$app.Name; AppPath=$app.Path; WrittenValue=$verifyValue.$($app.Path); ExpectedValue=$DPIOverrideFlags; Match=($verifyValue.$($app.Path) -eq $DPIOverrideFlags)} -HypothesisId "H1,H4"
                #endregion
                
                Write-ColorOutput "  ✓ Added DPI override for $($app.Name)" "Green"
            } catch {
                Write-ColorOutput "  ✗ Failed to set override for $($app.Name): $_" "Red"
                #region agent log
                Write-DebugLog -Location "Set-PerAppDPIOverrides:error" -Message "Error writing app override" -Data @{AppName=$app.Name; AppPath=$app.Path; Error=$_.ToString()} -HypothesisId "H1"
                #endregion
            }
        }
        
        Write-ColorOutput "Per-app DPI overrides configured successfully!" "Green"
    } catch {
        Write-ColorOutput "Error setting per-app overrides: $_" "Red"
        #region agent log
        Write-DebugLog -Location "Set-PerAppDPIOverrides:error" -Message "Error in per-app overrides function" -Data @{Error=$_.ToString()} -HypothesisId "H1"
        #endregion
        throw
    }
}

function Show-ManualInstructions {
    Write-ColorOutput "`n========================================" "Cyan"
    Write-ColorOutput "Manual Instructions (if apps weren't detected)" "Cyan"
    Write-ColorOutput "========================================" "Cyan"
    Write-ColorOutput "`nTo manually add DPI overrides for other Electron apps:" "White"
    Write-ColorOutput "1. Open Registry Editor (regedit.exe)" "White"
    Write-ColorOutput "2. Navigate to: $AppCompatRegPath" "White"
    Write-ColorOutput "3. Create a new String value with the full path to the .exe file" "White"
    Write-ColorOutput "4. Set the value to: $DPIOverrideFlags" "White"
    Write-ColorOutput "5. Restart the application" "White"
    Write-ColorOutput "`nIf issues persist, try 'System (Enhanced)' override:" "Yellow"
    Write-ColorOutput "  Value: ~ HIGHDPIAWARE DPIUNAWARE" "White"
    Write-ColorOutput "`nFor Docker Desktop specifically, if issues persist:" "Yellow"
    Write-ColorOutput "  See docker-settings-fix.json for instructions on disabling hardware acceleration" "White"
}

# Main execution
try {
    Write-ColorOutput "========================================" "Cyan"
    Write-ColorOutput "  DPI Scaling Fix for Electron Apps" "Cyan"
    Write-ColorOutput "========================================" "Cyan"
    
    if ($Restore) {
        if (-not $BackupFile) {
            Write-ColorOutput "Error: Backup file path required for restore operation" "Red"
            exit 1
        }
        $restored = Restore-RegistrySettings -BackupFilePath $BackupFile
        if ($restored) {
            Write-ColorOutput "`nPlease restart affected applications for changes to take effect." "Yellow"
        }
        exit 0
    }
    
    # Show current settings
    Get-CurrentDPISettings
    
    # Backup current settings
    $backupFile = Backup-RegistrySettings
    
    # Indicate which per-app DPI mode will be used
    if ($SystemEnhanced) {
        Write-ColorOutput "`nPer-app DPI mode: System (Enhanced) [~ HIGHDPIAWARE DPIUNAWARE]" "Yellow"
    } else {
        Write-ColorOutput "`nPer-app DPI mode: High DPI aware only [~ HIGHDPIAWARE]" "Yellow"
    }
    
    #region agent log
    Write-DebugLog -Location "Main:DPIOverrideMode" -Message "DPI override mode selected" -Data @{SystemEnhanced=$SystemEnhanced; DPIOverrideFlags=$DPIOverrideFlags} -HypothesisId "H4"
    #endregion
    
    # Set system-wide DPI settings
    Set-SystemWideDPISettings
    
    # Find and configure Electron apps
    $installedApps = Find-InstalledElectronApps
    
    if ($installedApps.Count -gt 0) {
        Set-PerAppDPIOverrides -Apps $installedApps
    } else {
        Write-ColorOutput "`nNo Electron apps were detected. You may need to add overrides manually." "Yellow"
    }
    
    # Show manual instructions
    Show-ManualInstructions
    
    Write-ColorOutput "`n========================================" "Cyan"
    Write-ColorOutput "  Configuration Complete!" "Green"
    Write-ColorOutput "========================================" "Cyan"
    Write-ColorOutput "`nNext steps:" "Yellow"
    Write-ColorOutput "1. Restart affected applications (Docker Desktop, ChatGPT, VS Code)" "White"
    Write-ColorOutput "2. Verify that text is no longer blurred/scrambled" "White"
    Write-ColorOutput "3. If issues persist, try running with 'System (Enhanced)' override" "White"
    Write-ColorOutput "`nTo restore previous settings, run:" "Yellow"
    Write-ColorOutput "  .\fix-dpi-scaling.ps1 -Restore -BackupFile `"$backupFile`"" "White"
    
} catch {
    Write-ColorOutput "`nError: $_" "Red"
    Write-ColorOutput "Stack trace: $($_.ScriptStackTrace)" "Red"
    exit 1
}
