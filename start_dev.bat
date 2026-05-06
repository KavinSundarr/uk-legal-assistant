@echo off
echo Starting UK Legal Assistant...
echo.
echo Starting backend on http://localhost:8000
start "Backend" cmd /k "conda activate LAWRAG && uvicorn backend.app.main:app --reload"
echo Waiting for backend to start...
timeout /t 5 /nobreak
echo.
echo Starting frontend on http://localhost:3000
start "Frontend" cmd /k "python -m http.server 3000 --directory frontend"
echo.
echo Opening browser...
timeout /t 3 /nobreak
start http://localhost:3000
echo.
echo Both servers running. Close the terminal windows to stop.
