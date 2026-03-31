python -m mpremote cp secrets.py :
python -m mpremote cp -r drivers :/
python -m mpremote cp main.py :
python -m mpremote connect COM8 repl
python -m mpremote reset

#for my laptop
# py -3.14 -m mpremote cp secrets.py :
# py -3.14 -m mpremote fs cp -r drivers :/
# py -3.14 -m mpremote fs cp main.py :main.py
# py -3.14 -m mpremote connect COM4 repl
# py -3.14 -m mpremote reset
