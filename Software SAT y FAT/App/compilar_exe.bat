@echo off
rem Genera "Protocolos FAT y SAT.exe" (un solo archivo, sin consola) en la carpeta dist\
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --name "Protocolos FAT y SAT" ^
  --icon recursos\icono.ico --version-file recursos\version_info.txt ^
  --add-data "recursos\icono.ico;recursos" --add-data "plantillas;plantillas" ^
  --collect-all rapidocr_onnxruntime --hidden-import cv2 --hidden-import numpy ^
  --exclude-module pymupdf.layout --exclude-module pymupdf4llm app.py
echo.
echo Listo: dist\Protocolos FAT y SAT.exe
pause
