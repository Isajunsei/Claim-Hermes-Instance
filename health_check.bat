@echo off
title Hermes Health Check
cd /d "%~dp0"
powershell.exe -ExecutionPolicy Bypass -File "%~dp0health_check.ps1"
