@echo off
rem Chuyen tiep lenh sang run_windows.bat de xu ly truong hop go nham ten file run_windown.bat
call "%~dp0run_windows.bat" %*
exit /b %errorlevel%
