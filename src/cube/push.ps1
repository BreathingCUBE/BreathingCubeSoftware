param([switch]$NoRepl)  # -NoRepl: upload and reset without attaching the REPL
$port = "COM5"
$python = "py"
$pythonVersion = "-3.14"
$build = Join-Path $PSScriptRoot "build"

function Invoke-Mpremote {
	& $python $pythonVersion -m mpremote connect $port @args
	if ($LASTEXITCODE -ne 0) {
		throw "mpremote failed with exit code $LASTEXITCODE"
	}
}

# Precompile everything except main.py and secrets.py to .mpy bytecode.
# Compiling large files on the board grows MicroPython's heap into the
# system memory the BLE controller needs (BLE start then fails with EIO).
# Needs: py -3.14 -m pip install "mpy-cross==1.29.*"  (match the firmware)
if (Test-Path $build) { Remove-Item -Recurse -Force $build }
New-Item -ItemType Directory -Force (Join-Path $build "drivers") | Out-Null
$sources = @("cube_app.py") + (Get-ChildItem -Path (Join-Path $PSScriptRoot "drivers") -Filter *.py | ForEach-Object { "drivers/" + $_.Name })
foreach ($src in $sources) {
	$out = Join-Path $build ([IO.Path]::ChangeExtension($src, ".mpy"))
	& $python $pythonVersion -m mpy_cross -o $out (Join-Path $PSScriptRoot $src)
	if ($LASTEXITCODE -ne 0) { throw "mpy-cross failed on $src" }
}

# MicroPython imports x.py before x.mpy, so remove old sources on the board.
try { Invoke-Mpremote fs rm -r :drivers } catch { Write-Host "(no drivers folder on the board yet)" }
try { Invoke-Mpremote fs rm :cube_app.py } catch { }

Invoke-Mpremote fs cp secrets.py :secrets.py
Invoke-Mpremote fs cp -r (Join-Path $build "drivers") :/
Invoke-Mpremote fs cp (Join-Path $build "cube_app.mpy") :cube_app.mpy
Invoke-Mpremote fs cp main.py :main.py
Invoke-Mpremote exec "from drivers.dataTransfer import overwrite_animation_pattern; overwrite_animation_pattern()"
Invoke-Mpremote reset
# Attach to the serial REPL to display MicroPython print/debug output.
if (-not $NoRepl) { Invoke-Mpremote repl }
