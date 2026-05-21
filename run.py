import subprocess
import time
import sys

def iniciar_todo():
    print("================================================")
    print("🚀 Iniciando el sistema completo de Jarvis...")
    print("================================================\n")
    
    import os
    # Detectar si existe un entorno virtual local para usar su ejecutable de Python
    python_exe = sys.executable
    venv_python = os.path.join("venv", "Scripts", "python.exe")
    if os.path.exists(venv_python):
        python_exe = venv_python
        print(f"[Info] Usando Python del entorno virtual: {python_exe}")
    else:
        print(f"[Info] Usando Python del sistema: {python_exe}")

    print("[1/2] Levantando el servidor de IA (Grok) y herramientas...")
    # Iniciamos main.py en un proceso hijo
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    cerebro = subprocess.Popen([python_exe, "main.py"], env=env)
    
    # Le damos 3 segundos al servidor para que arranque y esté listo para recibir peticiones
    time.sleep(3)
    
    print("\n[2/2] Conectando el micrófono y levantando el Widget Visual (HUD)...")
    # Iniciamos ui_jarvis.py en otro proceso hijo (que a su vez arranca el motor de audio interno)
    oidos = subprocess.Popen([python_exe, "ui_jarvis.py"], env=env)
    
    try:
        # Mantenemos este script vivo mientras el motor de audio funcione
        oidos.wait()
    except KeyboardInterrupt:
        print("\n[!] Apagando todos los sistemas de Jarvis...")
        # Si presionas Ctrl+C aquí, mata a ambos hijos limpiamente
        cerebro.terminate()
        oidos.terminate()
        print("Sistemas apagados. ¡Hasta luego!")

if __name__ == "__main__":
    iniciar_todo()
