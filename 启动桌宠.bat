@echo off
rem 启动桌宠（无控制台窗口）
setlocal
set "PY=C:\Users\43771\.workbuddy\binaries\python\envs\default\Scripts\pythonw.exe"
if exist "%PY%" (
  start "" "%PY%" "%~dp0main.py"
) else (
  start "" pythonw "%~dp0main.py"
)
