@echo off
title AI Travel Planner - One-Click Start
setlocal enabledelayedexpansion
cd /d "%~dp0"

rem ===== 0. clean broken proxy vars =====
set HTTP_PROXY=
set HTTPS_PROXY=
set ALL_PROXY=
set http_proxy=
set https_proxy=
set all_proxy=
set NO_PROXY=*
set no_proxy=*

echo ============================================
echo    AI Travel Planner - One-Click Start
echo ============================================
echo.

rem ===== 1. check python =====
where python >nul 2>nul
if errorlevel 1 goto no_python
python --version

rem ===== 2. check backend/.env =====
if exist "backend\.env" goto env_ok
echo [INFO] backend\.env not found, copying from template...
copy "backend\.env.example" "backend\.env" >nul
echo Created backend\.env
echo.
echo Please open backend\.env with Notepad and fill in DEEPSEEK_API_KEY
echo - get free key at platform.deepseek.com
echo Optional: QWEATHER_API_KEY / QWEATHER_API_HOST / AMAP_API_KEY
echo.
echo Then run this script again.
pause
exit /b 0
:env_ok

rem ===== 3. backend dependencies =====
echo.
echo [1/5] Checking backend dependencies...
python -m pip show fastapi uvicorn openai langgraph sentence-transformers faiss-cpu transformers modelscope PyJWT requests >nul 2>nul
if errorlevel 1 goto install_deps
echo Dependencies ready
goto deps_done
:install_deps
echo First run: installing backend dependencies (a few minutes)...
python -m pip install -r backend\requirements.txt
if errorlevel 1 goto install_fail
:deps_done

rem ===== 4. AI models =====
echo.
echo [2/5] Checking AI models (embedding/rerank/multimodal)...
if exist "backend\models\bge-small-zh-v1.5\config.json" if exist "backend\models\bge-reranker-base\config.json" if exist "backend\models\chinese-clip-vit-base-patch16\config.json" goto models_ok
echo Models missing, downloading from ModelScope ~1.5GB, first run only...
cd backend
python download_models.py
cd ..
if errorlevel 1 goto download_fail
echo Models ready
goto models_done
:models_ok
echo Models ready
:models_done

rem ===== 5. FAISS index =====
echo.
echo [3/5] Checking knowledge base index...
if exist "backend\data\faiss_index\index.faiss" goto index_ok
echo Index missing, building (a few minutes)...
cd backend
python build_index.py
cd ..
:index_ok
echo Index ready

rem ===== 6. frontend dependencies =====
echo.
echo [4/5] Checking frontend dependencies...
if exist "frontend\node_modules" goto fe_ok
echo First run: installing frontend dependencies (a few minutes)...
cd frontend
call npm install
cd ..
if errorlevel 1 goto fe_fail
echo Dependencies ready
goto fe_done
:fe_ok
echo Dependencies ready
:fe_done

rem ===== 7. ports =====
echo.
echo [5/5] Checking ports...
python check_port.py 8003
if not errorlevel 1 echo WARNING: port 8003 in use, backend may already be running
python check_port.py 5173
if not errorlevel 1 echo WARNING: port 5173 in use, frontend may already be running

rem ===== 8. start services =====
echo.
echo Starting backend server (new window)...
start "travel-backend" cmd /k "cd /d %~dp0backend && python -m uvicorn app.main:app --port 8003"
timeout /t 3 /nobreak >nul

echo Starting frontend server (new window)...
start "travel-frontend" cmd /k "cd /d %~dp0frontend && npm run dev"
timeout /t 10 /nobreak >nul

echo.
echo ============================================
echo    Done! Opening browser: http://localhost:5173
echo ============================================
echo    The two new windows are backend/frontend logs.
echo    Close them to stop the servers.
echo.
start http://localhost:5173
pause >nul
exit /b 0

:no_python
echo [ERROR] Python not found. Install Python 3.10+ first:
echo         https://www.python.org/downloads/
echo         IMPORTANT: check "Add Python to PATH" during install.
pause
exit /b 1

:install_fail
echo [ERROR] Dependency install failed. Check your network and retry.
pause
exit /b 1

:download_fail
echo [ERROR] Model download failed. Check your network and retry.
pause
exit /b 1

:fe_fail
echo [ERROR] Frontend dependency install failed. Check your network and retry.
pause
exit /b 1
