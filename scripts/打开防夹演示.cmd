@echo off
set "PROJECT=%~dp0.."
set "BLENDER=%PROJECT%\.tools\blender-4.5.9-windows-x64\blender.exe"
if not exist "%BLENDER%" (
  echo Blender not found. Open assets\blender\anti_pinch.blend in Blender 4.5 LTS.
  pause
  exit /b 1
)
set "TEMP=%PROJECT%\.tools\temp"
set "TMP=%TEMP%"
set "BLENDER_USER_CONFIG=%PROJECT%\.tools\blender-config"
set "BLENDER_USER_DATAFILES=%PROJECT%\.tools\blender-data"
set "OPTIX_CACHE_PATH=%PROJECT%\.tools\optix-cache"
set "CUDA_CACHE_PATH=%PROJECT%\.tools\cuda-cache"
start "" "%BLENDER%" --disable-autoexec "%PROJECT%\assets\blender\anti_pinch.blend"
