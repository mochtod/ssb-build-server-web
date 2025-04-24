@echo off
REM test_atlantis_local.bat
REM Script to test the Atlantis integration with local filesystem

echo Testing Atlantis integration with local filesystem...

echo 1. Checking if Docker is running...
docker info > nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Docker is not running. Please start Docker Desktop.
    exit /b 1
)

echo 2. Preparing workspace for Atlantis...
call prepare_atlantis_workspace.bat

echo 3. Bringing down any existing containers...
docker-compose down

echo 4. Building and starting containers...
docker-compose up -d

echo 5. Waiting for containers to start (30 seconds)...
timeout /t 30

echo 6. Testing Atlantis connection...
curl -s http://localhost:4141 > nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Could not connect to Atlantis at http://localhost:4141
    echo Check docker-compose logs for errors: docker-compose logs atlantis
) else (
    echo SUCCESS: Atlantis is running and accessible at http://localhost:4141
    echo.
    echo The application is available at http://localhost:5150
    echo.
    echo You can now build VMs through the application interface.
    echo The VM workspace is mounted inside Atlantis as /terraform/vm-workspace
    echo.
    echo Check logs with: docker-compose logs
)

echo Done!