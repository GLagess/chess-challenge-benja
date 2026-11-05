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

echo Baixando tablebases de 3 a 5 pecas (cerca de 1 GB). Precisa de internet.
%PY% tools\download_syzygy.py
pause
