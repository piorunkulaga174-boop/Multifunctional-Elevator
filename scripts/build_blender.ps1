param(
    [string]$BlenderPath,
    [switch]$Stills,
    [switch]$Previews,
    [switch]$VerifyOnly
)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if(!$BlenderPath){ $BlenderPath=Join-Path $projectRoot '.tools\blender-4.5.9-windows-x64\blender.exe' }
if(!(Test-Path -LiteralPath $BlenderPath)){throw 'Pass -BlenderPath with a Blender 4.5 LTS executable.'}
$BlenderPath=(Resolve-Path -LiteralPath $BlenderPath).Path
$python=Join-Path $projectRoot '.venv\Scripts\python.exe'
if(!(Test-Path -LiteralPath $python)){throw 'Create .venv and install requirements.txt first.'}
if($Previews -and !(Get-Command ffmpeg -ErrorAction SilentlyContinue)){
    throw 'Video preview encoding requires ffmpeg on PATH.'
}
$env:PYTHONUTF8='1'
$env:TEMP=Join-Path $projectRoot '.tools\temp'
$env:TMP=$env:TEMP
$env:BLENDER_USER_CONFIG=Join-Path $projectRoot '.tools\blender-config'
$env:BLENDER_USER_DATAFILES=Join-Path $projectRoot '.tools\blender-data'
$env:OPTIX_CACHE_PATH=Join-Path $projectRoot '.tools\optix-cache'
$env:CUDA_CACHE_PATH=Join-Path $projectRoot '.tools\cuda-cache'
foreach($dir in @($env:TEMP,'.local-audit','output\stills','output\preview-frames','assets\previews','media\demos')){New-Item -ItemType Directory -Path $dir -Force | Out-Null}
function Invoke-BlenderJob($LogName, [string[]]$BlenderArgs){
    & $BlenderPath --python-exit-code 1 @BlenderArgs *> (Join-Path $projectRoot ".local-audit\$LogName.txt")
    if($LASTEXITCODE -ne 0){throw "Blender failed; see .local-audit/$LogName.txt"}
}
if(!$VerifyOnly){
    & $python (Join-Path $projectRoot 'scripts\export_demo_replays.py')
    if($LASTEXITCODE -ne 0){throw 'Replay export failed'}
}
foreach($name in @('normal_ride','anti_pinch')){
    $blend=Join-Path $projectRoot "assets\blender\$name.blend"
    if(!$VerifyOnly){
        Invoke-BlenderJob "build-$name" @('--background','--factory-startup','--python',(Join-Path $projectRoot 'blender\build_scene.py'),'--','--name',$name)
    }
    Invoke-BlenderJob "verify-$name" @('--background',$blend,'--python',(Join-Path $projectRoot 'blender\verify_scene.py'))
    Write-Output "Verified: $name"
    if($Previews){
        Invoke-BlenderJob "preview-$name" @('--background',$blend,'--python',(Join-Path $projectRoot 'blender\render_replay.py'),'--','--name',$name,'--engine','CYCLES','--samples','16','--width','768','--height','432','--preview','--output',(Join-Path $projectRoot "output\preview-frames\$name"))
        & ffmpeg -hide_banner -loglevel error -y -framerate 12 -i (Join-Path $projectRoot "output\preview-frames\$name\frame_%04d.png") -c:v libx264 -crf 19 -pix_fmt yuv420p -movflags +faststart (Join-Path $projectRoot "media\demos\$name.mp4")
        if($LASTEXITCODE -ne 0){throw "Video encoding failed: $name"}
        Copy-Item -LiteralPath (Join-Path $projectRoot "output\preview-frames\$name\shots.json") -Destination (Join-Path $projectRoot "media\demos\${name}_shots.json") -Force
        Write-Output "Video: media/demos/$name.mp4"
    }
}
if($Stills){
    $jobs=@(
        @('normal_ride','Hall','1','normal_hall'),
        @('normal_ride','Section','21','full_section'),
        @('normal_ride','Cabin','6','cabin'),
        @('anti_pinch','Hall','8','anti_pinch')
    )
    foreach($job in $jobs){
        $stillArgs=@('--background',(Join-Path $projectRoot "assets\blender\$($job[0]).blend"),'--python',(Join-Path $projectRoot 'blender\render_replay.py'),'--','--name',$job[0],'--view',$job[1],'--time',$job[2],'--samples','48','--output',(Join-Path $projectRoot "assets\previews\$($job[3]).png"))
        if($job[1] -eq 'Section'){ $stillArgs+=@('--width','900','--height','1280') }
        Invoke-BlenderJob "still-$($job[3])" $stillArgs
        Write-Output "Still: assets/previews/$($job[3]).png"
    }
}
