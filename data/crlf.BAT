@echo off
setlocal

if "%~1"=="" (
    echo Usage: ConvertLFtoCRLF.bat "Path\To\ModFolder"
    pause
    exit /b 1
)

set "MODDIR=%~1"

powershell -NoProfile -ExecutionPolicy Bypass ^
"$files = Get-ChildItem -Path '%MODDIR%' -Filter *.txt -Recurse; ^
foreach ($file in $files) { ^
    $content = [System.IO.File]::ReadAllText($file.FullName); ^
    $content = $content -replace '\r?\n', \"`r`n\"; ^
    [System.IO.File]::WriteAllText($file.FullName, $content); ^
    Write-Host ('Converted: ' + $file.FullName); ^
}"

echo.
echo Done.
pause