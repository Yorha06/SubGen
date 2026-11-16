# PowerShell launcher untuk SubGen
Set-Location $PSScriptRoot
$env:PYTHONPATH = "$PSScriptRoot\src"
python app.py $args