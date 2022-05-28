@echo off

TITLE thegamebot

:: Remove shutdown file at start of run loop
IF EXIST "SHUTDOWN" (
	DEL "SHUTDOWN"
)

:: Run the script
:run
:: ".venv\Scripts\pip.exe" "install" "-U" "discord.py"
".venv\Scripts\python.exe" "main.py" %*
IF NOT EXIST "SHUTDOWN" (
	GOTO run
) ELSE (
	DEL "SHUTDOWN"
)

:: The bot will generate a file indicating if it wants to shutdown.
:: If that file doesn't exist, delete it and run the script again
