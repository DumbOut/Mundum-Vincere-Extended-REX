@echo off
echo Converting all .txt files under:
echo %~dp0
echo.

powershell -NoProfile -ExecutionPolicy Bypass ^
"$files = Get-ChildItem -Path '%~dp0' -Filter *.txt -Recurse; ^
foreach ($file in $files) { ^
    $content = [System.IO.File]::ReadAllText($file.FullName); ^
    $content = $content -replace '\r?\n', \"`r`n\"; ^
    [System.IO.File]::WriteAllText($file.FullName, $content); ^
    Write-Host ('Converted: ' + $file.FullName); ^
}"

echo.
echo Finished.
pause