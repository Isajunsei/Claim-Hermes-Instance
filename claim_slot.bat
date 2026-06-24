@echo off
title Hermes OCI Claim-Slot
echo Starting the Hermes instance claim-slot script.
echo Leave this window open (minimizing is fine).
echo Press Ctrl+C to stop at any time.
echo.

:: OCI CLI 仮想環境を有効化
call %USERPROFILE%\oci-cli-env\Scripts\activate.bat 2>nul

:: スクリプトのあるフォルダに移動してから実行
cd /d "%~dp0"
python claim_slot.py

echo.
echo Script ended. Press any key to close.
pause >nul
