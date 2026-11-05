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

echo Diagnostico do notebook (cerca de 1 minuto).
echo Deixe o notebook na tomada, em "Melhor desempenho" e com os outros programas fechados.
echo.
%PY% tools\diagnostico.py %*
echo.
echo Copie o bloco entre "COPIE DAQUI" e "ATE AQUI" e envie para o Gabriel.
echo O mesmo texto fica salvo em saves\diagnostico.txt
pause
