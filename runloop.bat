@echo off

TITLE thegamebot

:: Argument parsing
:: https://stackoverflow.com/a/3981086
SET args=
:parse
if NOT [%1]==[] (
	SET args=%args% %1
	SHIFT
	GOTO parse
)

:: Remove restart file at start of run loop
IF EXIST "RESTART" (
	DEL "RESTART"
)

:: Run the script
:run
:: ".venv\Scripts\pip.exe" "install" "-U" "discord.py"
".venv\Scripts\python.exe" "main.py" %args%
IF EXIST "RESTART" (
	DEL "RESTART"
	GOTO run
)

:: The bot will generate a file indicating if it wants to restart.
:: If that file exists, delete it and run the script again
