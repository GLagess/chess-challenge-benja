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

echo Abrindo o sistema. O navegador abre em http://127.0.0.1:8765
echo Para encerrar: feche esta janela ou aperte Ctrl+C.
echo.
%PY% run.py
pause
