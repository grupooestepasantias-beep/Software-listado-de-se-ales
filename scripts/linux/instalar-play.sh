#!/usr/bin/env bash
# Instala y arranca el servidor de Play en este equipo Linux (o NAS).
#
# Uso (dentro de la carpeta donde está el servidor):
#     bash instalar-play.sh                      # usa esta misma carpeta y nombres.xlsx que esté en ella
#     bash instalar-play.sh /ruta/al/nombres.xlsx
#     PLAY_PUERTO=8090 bash instalar-play.sh     # otro puerto (por defecto 8080)
#
# Qué hace:
#   1) deja ejecutable el programa y crea la carpeta de datos (la base de datos NUNCA debe estar en una carpeta compartida por red),
#   2) escribe iniciar.sh (con la configuración: carpeta de datos, Excel de empleados y puerto),
#   3) si el equipo tiene systemd y sudo, lo instala como servicio (arranca solo al prender el equipo);
#      si no, lo deja corriendo en segundo plano con nohup y te dice cómo volver a iniciarlo.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXCEL="${1:-$DIR/nombres.xlsx}"
PUERTO="${PLAY_PUERTO:-8080}"

if [ ! -f "$DIR/Play.Server" ]; then
  echo "No encuentro 'Play.Server' en $DIR. Ejecutá este script desde la carpeta donde está el servidor." >&2
  exit 1
fi
if [ ! -f "$EXCEL" ]; then
  echo "AVISO: no encuentro el Excel de empleados en $EXCEL." >&2
  echo "       Copialo ahí (o pasá su ruta como primer argumento). Sin Excel, los empleados se manejan desde la app." >&2
fi

chmod +x "$DIR/Play.Server"
mkdir -p "$DIR/datos"

# DOTNET_SYSTEM_GLOBALIZATION_INVARIANT: muchos NAS no traen la biblioteca de idiomas (ICU) y sin esto el programa no arranca.
cat > "$DIR/iniciar.sh" <<EOF
#!/usr/bin/env bash
cd "$DIR"
export DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1
export Play__DataDir="$DIR/datos"
export Play__EmpleadosExcel="$EXCEL"
export Urls="http://0.0.0.0:$PUERTO"
exec "$DIR/Play.Server"
EOF
chmod +x "$DIR/iniciar.sh"

USAR_SERVICIO=0
SUDO=""
if command -v systemctl >/dev/null 2>&1; then
  if [ "$(id -u)" = "0" ]; then
    USAR_SERVICIO=1
  elif command -v sudo >/dev/null 2>&1; then
    echo "Para instalarlo como servicio hace falta sudo (puede pedirte la contraseña de este usuario)."
    if sudo -v; then USAR_SERVICIO=1; SUDO="sudo"; fi
  fi
fi

if [ "$USAR_SERVICIO" = "1" ]; then
  $SUDO tee /etc/systemd/system/play.service >/dev/null <<EOF
[Unit]
Description=Play - registro de horas
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(id -un)
WorkingDirectory=$DIR
ExecStart=$DIR/iniciar.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable --now play.service
  echo
  echo "Listo: Play quedó instalado como servicio (play.service) y arranca solo."
  echo "  Estado:  sudo systemctl status play"
  echo "  Logs:    sudo journalctl -u play -f"
else
  pkill -f "$DIR/Play.Server" 2>/dev/null || true
  if command -v nohup >/dev/null 2>&1; then
    nohup "$DIR/iniciar.sh" > "$DIR/play.log" 2>&1 &
  else
    # Algunos NAS (QNAP) no traen nohup: un subshell deja el proceso independiente de esta sesión.
    ( "$DIR/iniciar.sh" > "$DIR/play.log" 2>&1 & )
  fi
  echo
  echo "Listo: Play quedó corriendo en segundo plano (log: $DIR/play.log)."
  echo "AVISO: este equipo no permite instalarlo como servicio. Si se REINICIA, Play no arranca solo:"
  echo "  hay que volver a correr  $DIR/iniciar.sh  (o programar esa línea para que se ejecute al encender el equipo)."
fi

echo
echo "Probá desde otra PC:  http://$(hostname -I 2>/dev/null | awk '{print $1}'):$PUERTO"
