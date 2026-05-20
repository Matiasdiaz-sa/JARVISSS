import subprocess
import os

def play_mp3_powershell(file_path):
    # En PowerShell, reproducir MP3 de forma síncrona:
    cmd = f"""
    Add-Type -AssemblyName presentationCore
    $player = New-Object system.windows.media.mediaplayer
    $player.open('{file_path}')
    while ($player.NaturalDuration.HasTimeSpan -eq $false) {{ Start-Sleep -Milliseconds 10 }}
    $duration = $player.NaturalDuration.TimeSpan.TotalSeconds
    Write-Output "Duration: $duration"
    $player.Play()
    Start-Sleep -Seconds $duration
    $player.Close()
    """
    result = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True)
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)

# Create a small dummy file or use an existing one if possible, but let's just see if the script syntax is correct.
# We'll just run it. It should exit immediately if file is empty or missing, or throw a clean PS error.
play_mp3_powershell("nonexistent.mp3")
