$port = "COM5"

function Invoke-Mpremote {
	& py -3.14 -m mpremote connect $port @args
	if ($LASTEXITCODE -ne 0) {
		throw "mpremote failed with exit code $LASTEXITCODE"
	}
}

Invoke-Mpremote fs cp secrets.py :secrets.py
Invoke-Mpremote fs cp -r drivers :/
Invoke-Mpremote fs cp main.py :main.py
Invoke-Mpremote exec "from drivers.dataTransfer import overwrite_animation_pattern; overwrite_animation_pattern()"
Invoke-Mpremote reset
# Attach to the serial REPL to display MicroPython print/debug output.
Invoke-Mpremote repl


