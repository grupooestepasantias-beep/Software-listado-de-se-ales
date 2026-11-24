#!/usr/bin/env bash
# Se ejecuta EN el servidor (lo lanza «1-INSTALAR.bat» por SSH). Instala Play y lo deja funcionando.
# Si Play ya estaba instalado se ACTUALIZA el programa pero NO se pisan los datos (la base de datos queda como está).
set -euo pipefail

ORIGEN="$(cd "$(dirname "$0")" && pwd)"
export PLAY_PUERTO="__PUERTO__"

case "$(uname -m)" in
  x86_64|amd64)  VERSION=linux-x64 ;;
  aarch64|arm64) VERSION=linux-arm64 ;;
  *) echo "Este equipo es de un tipo que no tengo compilado: $(uname -m). Avisá a quien te ayuda." >&2; exit 2 ;;
esac
echo "Tipo de equipo: $(uname -m)  ->  se instala la versión $VERSION"

# Carpeta de instalación: la del usuario; si no se puede escribir ahí (algunos NAS), una carpeta del volumen de datos.
DEST=""
if [ -n "${PLAY_DEST:-}" ]; then
  # Carpeta elegida a mano (por ejemplo en un NAS: PLAY_DEST=/share/homes/admin/play)
  if mkdir -p "$PLAY_DEST/datos" 2>/dev/null && [ -w "$PLAY_DEST" ]; then DEST="$PLAY_DEST"; fi
else
  for candidato in "$HOME/play" /volume1/play /share/Public/play /srv/play; do
    if mkdir -p "$candidato/datos" 2>/dev/null && [ -w "$candidato" ]; then DEST="$candidato"; break; fi
  done
fi
if [ -z "$DEST" ]; then
  echo "No encuentro una carpeta donde este usuario pueda escribir (usuario: $(id -un), HOME: $HOME)." >&2
  exit 3
fi
echo "Se instala en: $DEST   (puerto $PLAY_PUERTO)"

# Si ya estaba corriendo, se detiene para poder reemplazar el programa.
if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files 2>/dev/null | grep -q '^play.service'; then
  sudo systemctl stop play 2>/dev/null || true
fi
pkill -f "$DEST/Play.Server" 2>/dev/null || true
sleep 1

echo "Copiando el programa..."
cp -a "$ORIGEN/programa/$VERSION/." "$DEST/"
cp -f "$ORIGEN/instalar-play.sh" "$DEST/instalar-play.sh"
cp -f "$ORIGEN/nombres.xlsx" "$DEST/nombres.xlsx"

# Los datos (base de datos con obras, subtareas, administradores, empleados) solo se copian la PRIMERA vez.
if [ ! -f "$DEST/datos/play.db" ] && [ -f "$ORIGEN/datos/play.db" ]; then
  echo "Copiando los datos que ya existían..."
  cp -a "$ORIGEN/datos/play.db"* "$DEST/datos/"
else
  echo "Ya había datos en el servidor: se conservan tal cual."
fi
# El programa de los empleados (Play.exe) se actualiza siempre para que los paneles lo descarguen y se actualicen solos.
if [ -f "$ORIGEN/datos/descargas/Play.exe" ]; then
  mkdir -p "$DEST/datos/descargas"
  cp -f "$ORIGEN/datos/descargas/Play.exe" "$DEST/datos/descargas/Play.exe"
fi

# Se guarda dónde quedó instalado, para actualizar el Excel después.
echo "$DEST" > "$HOME/.play-ruta" 2>/dev/null || true

cd "$DEST"
bash "$DEST/instalar-play.sh" "$DEST/nombres.xlsx"
rm -rf "$ORIGEN"
echo
echo "Instalación terminada."
