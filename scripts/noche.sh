#!/bin/zsh
# Corre el buscador cada 15 minutos sin mandar mails, y evita que la Mac se duerma.
cd "$(dirname "$0")/.."
LOG=data/noche.log
while pgrep -f "finder.run" >/dev/null; do sleep 10; done
while true; do
  .venv/bin/python -W ignore -m finder.run --dry-run >> $LOG 2>&1
  sleep 900
done
