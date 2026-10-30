::cd %USERPROFILE%\projects\news_pipeline

:: Launch the script silently (start /B) using your internal venv python executable
start /B .\venv\Scripts\python.exe pipeline.py > data\pipeline.log 2>&1