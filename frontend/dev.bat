@echo off
taskkill /f /im python.exe >nul 2>nul
npm run tauri-dev
pause
