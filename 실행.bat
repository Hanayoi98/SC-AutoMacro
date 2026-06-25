@echo off
cd /d "%~dp0"

:: pythonw = Python without console window
:: cmd window closes immediately, only tkinter GUI remains
start "" pythonw "%~dp0macro.py"
