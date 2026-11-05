@echo off
cd /d "%~dp0"
set PY=python
%PY% --version >nul 2>&1 || set PY=py
%PY% --version >nul 2>&1 || (
  echo.
  echo [ERRO] Python nao encontrado.
  echo Instale o Python 3.11 ou mais novo em https://www.python.org/downloads/
  echo e marque a opcao "Add Python to PATH" no instalador.
  pause
  exit /b 1
)
if not exist run.py (
  echo [ERRO] Este arquivo precisa ficar na mesma pasta do run.py.
  pause
  exit /b 1
)

echo === 1/3 Instalando a biblioteca de xadrez ===
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERRO] Falha no pip install. Confira a internet e tente de novo.
  pause
  exit /b 1
)

echo.
echo === 2/3 Baixando o Stockfish 19 ===
if exist engines\stockfish.exe (
  echo Stockfish ja instalado em engines\stockfish.exe
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest 'https://github.com/official-stockfish/Stockfish/releases/download/sf_19/stockfish-windows-x86-64-universal.zip' -OutFile 'sf.zip'; Expand-Archive 'sf.zip' -DestinationPath 'sf_tmp' -Force; Get-ChildItem 'sf_tmp' -Recurse -Filter *.exe | Select-Object -First 1 | Copy-Item -Destination 'engines\stockfish.exe'; Remove-Item 'sf.zip'; Remove-Item 'sf_tmp' -Recurse -Force"
)
if not exist engines\stockfish.exe (
  echo [ERRO] Nao consegui baixar o Stockfish. Veja o GUIA, secao "Instalacao manual".
  pause
  exit /b 1
)
if not exist engines\stockfish-reserva.exe copy engines\stockfish.exe engines\stockfish-reserva.exe >nul

echo.
echo === 3/3 Verificando ===
%PY% tools\check_setup.py
echo.
echo Instalacao concluida. Para abrir o sistema, de dois cliques em 2-iniciar.bat
pause
