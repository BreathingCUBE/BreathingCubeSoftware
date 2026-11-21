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
#
# If mpy-cross cannot run at all (e.g. Windows Smart App Control blocks the
# unsigned mpy-cross.exe), the plain .py files are uploaded instead and the
# board compiles them. That works since main.py reserves BLE memory first,
# with less memory headroom than .mpy.
$sources = @("cube_app.py") + (Get-ChildItem -Path (Join-Path $PSScriptRoot "drivers") -Filter *.py | ForEach-Object { "drivers/" + $_.Name })

# Catch syntax errors here, not on the board.
foreach ($src in $sources) {
	& $python $pythonVersion -c "import ast, sys; ast.parse(open(sys.argv[1], encoding='utf-8').read(), sys.argv[1])" (Join-Path $PSScriptRoot $src)
	if ($LASTEXITCODE -ne 0) { throw "Syntax error in $src (see above)" }
}

& $python $pythonVersion -m mpy_cross --version *> $null
$precompile = ($LASTEXITCODE -eq 0)
if (-not $precompile) {
	Write-Warning "mpy-cross cannot run (blocked by Windows Smart App Control?). Uploading .py sources instead."
}

if ($precompile) {
	if (Test-Path $build) { Remove-Item -Recurse -Force $build }
	New-Item -ItemType Directory -Force (Join-Path $build "drivers") | Out-Null
	foreach ($src in $sources) {
		$out = Join-Path $build ([IO.Path]::ChangeExtension($src, ".mpy"))
		& $python $pythonVersion -m mpy_cross -o $out (Join-Path $PSScriptRoot $src)
		if ($LASTEXITCODE -ne 0) { throw "mpy-cross failed on $src" }
	}
}

# Clear old code on the board. MicroPython imports x.py before x.mpy, so
# leftovers of the other kind would win.
try { Invoke-Mpremote fs rm -r :drivers } catch { Write-Host "(no drivers folder on the board yet)" }
try { Invoke-Mpremote fs rm :cube_app.py } catch { }
try { Invoke-Mpremote fs rm :cube_app.mpy } catch { }

Invoke-Mpremote fs cp secrets.py :secrets.py
if ($precompile) {
	Invoke-Mpremote fs cp -r (Join-Path $build "drivers") :/
	Invoke-Mpremote fs cp (Join-Path $build "cube_app.mpy") :cube_app.mpy
} else {
	Invoke-Mpremote fs mkdir :drivers
	foreach ($src in $sources) { Invoke-Mpremote fs cp (Join-Path $PSScriptRoot $src) ":$src" }
}
Invoke-Mpremote fs cp main.py :main.py
Invoke-Mpremote exec "from drivers.dataTransfer import overwrite_animation_pattern; overwrite_animation_pattern()"
Invoke-Mpremote reset
# Attach to the serial REPL to display MicroPython print/debug output.
if (-not $NoRepl) { Invoke-Mpremote repl }
