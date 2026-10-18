@echo off
rem 带控制台启动，用于看报错
setlocal
set "PY=C:\Users\43771\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if exist "%PY%" (
  "%PY%" "%~dp0main.py"
) else (
  python "%~dp0main.py"
)
pause
