@echo off
title Hermes Status Check
cd /d "%~dp0"
call %USERPROFILE%\oci-cli-env\Scripts\activate.bat 2>nul
python check_status.py
