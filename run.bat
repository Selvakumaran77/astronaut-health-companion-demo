@echo off
rem Ensure the model files exist, then launch the local wearable or synthetic demo.
setlocal
cd /d "%~dp0"

if not exist "data\synthetic\crew_vitals_simulated.csv" (
  echo Generating simulated crew dataset...
  py scripts\generate_synthetic_crew.py || goto :err
)

if not exist "models\risk_model.json" (
  echo Training risk model...
  py scripts\train_model.py || goto :err
)

if exist "..\..\wearable-device-dataset-from-induced-stress-and-structured-exercise-sessions-1.0.1\Wearable_Dataset\STRESS\f01\HR.csv" (
  echo Starting the four-participant wearable research demo on localhost...
  start "Crew Health Monitor API" /D "%CD%" py scripts\serve_api.py --wearable-demo
) else (
  echo Wearable dataset not found beside the project; starting the synthetic-data demo...
  start "Crew Health Monitor API" /D "%CD%" py scripts\serve_api.py --public-demo
)
timeout /t 2 /nobreak >nul
echo Opening http://127.0.0.1:8000 ...
start "" "http://127.0.0.1:8000/"
exit /b 0

:err
echo.
echo Something failed. You can run the scripts in scripts\ individually to see details.
pause
exit /b 1
