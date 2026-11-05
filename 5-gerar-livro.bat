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

echo Gerando o livro de aberturas. Pode levar varias horas.
echo Feche o sistema (2-iniciar.bat) antes. Pode interromper com Ctrl+C e rodar de novo depois:
echo ele continua de onde parou.
echo.
%PY% tools\build_book.py --plies 12 --our-time 30 --their-time 8 --branch 3
pause
