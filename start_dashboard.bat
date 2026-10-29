@echo off
REM Double-click this file to (1) pull new plays from GitHub and (2) open the dashboard.
REM It works from any folder because it first moves into the project folder.
cd /d "%~dp0"

echo Pulling new plays from the GitHub data branch...
.venv\Scripts\python.exe -m database.pull_cloud

echo.
echo Starting the dashboard (close this window to stop it)...
.venv\Scripts\python.exe -m streamlit run dashboard/app.py
