REM Extend OS partition
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Windows\Setup\Scripts\ExtendOSPartition.ps1

REM Restore dynamic pagefile.sys
reg add "HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management" /f /v PagingFiles /t REG_MULTI_SZ /d "%SystemDrive%\pagefile.sys 0 0"

REM Enable back hibernation
powercfg -h on

REM Install Medulla Agent
%windir%\Setup\Scripts\Medulla-Agent-windows-FULL-latest.exe /S
