@echo off
setlocal
cd /d "%~dp0backend"
set "PYTHON_EXE=D:\program files\Python\Python311\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
"%PYTHON_EXE%" -m uvicorn main:app --host 0.0.0.0 --port 8000
endlocal
