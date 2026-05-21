import webbrowser
import os
import subprocess
import httpx
import re
import glob


def _buscar_en_menu_inicio(nombre_programa: str):
    """
    Busca un programa en los accesos directos del Menú de Inicio de Windows.
    Esto encuentra CUALQUIER aplicación instalada sin necesidad de mapeo manual.
    """
    # Carpetas del Menú de Inicio (usuario + sistema)
    carpetas = [
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
    ]
    
    nombre = nombre_programa.lower()
    mejor_match = None
    
    for carpeta in carpetas:
        if not os.path.exists(carpeta):
            continue
        
        # Buscar todos los .lnk (accesos directos) recursivamente
        for root, dirs, files in os.walk(carpeta):
            for archivo in files:
                if archivo.endswith('.lnk'):
                    nombre_archivo = archivo[:-4].lower()  # Quitar .lnk
                    ruta_completa = os.path.join(root, archivo)
                    
                    # Match exacto
                    if nombre == nombre_archivo:
                        return ruta_completa
                        
                    # Match parcial: lo que pide el usuario está en el nombre del acceso directo (ej. 'chrome' en 'Google Chrome')
                    if nombre in nombre_archivo:
                        # Guardar como candidato
                        if mejor_match is None:
                            mejor_match = ruta_completa
    
    return mejor_match


def controlar_sistema(accion: str, parametro: str = "", contenido: str = ""):
    """
    Función diseñada para ser llamada por el LLM (Grok).
    Ejecuta comandos a nivel de sistema operativo (abrir webs, programas, etc.).
    """
    try:
        # Rescatar parámetro si el LLM los mezcló (p.ej. Llama 8B)
        if not parametro and contenido:
            parametro = contenido
            
        if accion == "abrir_web":
            if not parametro:
                return "Error: No se especificó qué URL o sitio web abrir."
            
            # Si el LLM solo pasa "youtube" o "youtube.com", asegurarnos de que tenga https
            url = parametro.lower()
            if not url.startswith("http://") and not url.startswith("https://"):
                url = f"https://www.{url}"
                if not url.endswith(".com") and not url.endswith(".org") and not url.endswith(".net") and not url.endswith(".es"):
                    url += ".com"
            
            print(f"[Sistema] Abriendo navegador en: {url}")
            webbrowser.open(url, new=2)
            return f"Navegador abierto en {url}."

        elif accion == "buscar_google":
            if not parametro:
                return "Error: No se especificó qué buscar en Google."
            
            query = parametro.replace(" ", "+")
            url = f"https://www.google.com/search?q={query}"
            print(f"[Sistema] Buscando en Google: {url}")
            webbrowser.open(url, new=2)
            return f"Buscando '{parametro}' en Google (nueva pestaña)."

        elif accion == "buscar_imagen":
            if not parametro:
                return "Error: No se especificó qué imagen buscar."
            
            query = parametro.replace(" ", "+")
            url = f"https://www.google.com/search?tbm=isch&q={query}"
            print(f"[Sistema] Buscando imagen: {url}")
            webbrowser.open(url, new=2)
            return f"Buscando imágenes de '{parametro}' en Google."

        elif accion == "abrir_programa":
            if not parametro:
                return "Error: No se especificó el nombre del programa."
            
            programa = parametro.lower().strip()
            if programa.endswith(".exe"):
                programa = programa[:-4]
            
            # 1. Primero: Mapeo manual para nombres especiales o ambiguos
            programas_comunes = {
                "calculadora": "calc.exe",
                "bloc de notas": "notepad.exe",
                "notepad": "notepad.exe",
                "cmd": "cmd.exe",
                "consola": "cmd.exe",
                "explorador": "explorer.exe",
                "archivos": "explorer.exe",
                "administrador de tareas": "taskmgr.exe",
                "administrador": "taskmgr.exe",
                "tareas": "taskmgr.exe",
                "taskmgr": "taskmgr.exe",
                "lol": r"E:\Riot Games\League of Legends\League of Legends.exe",
                "discord": r"C:\Users\luka\AppData\Local\Discord\app-0.0.309\Discord.exe",
                "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                "steam": r"E:\Steam\Steam.exe",
                "cs": r"E:\Steam\steamapps\common\Counter-Strike Global Offensive\csgo.exe",
            }
            
            if programa == "spotify":
                print("[Sistema] Abriendo Spotify vía protocolo...")
                try:
                    os.startfile("spotify:")
                    return "Programa 'Spotify' iniciado."
                except Exception as e:
                    return f"Intenté abrir Spotify, pero falló: {e}"
            
            if programa in programas_comunes:
                comando = programas_comunes[programa]
                print(f"[Sistema] Abriendo (mapeo directo): {comando}")
                subprocess.Popen(comando, shell=True)
                return f"Programa '{parametro}' iniciado."
            
            # 2. Segundo: Buscar en accesos directos del Menú de Inicio (TODA app instalada)
            ruta_encontrada = _buscar_en_menu_inicio(programa)
            if ruta_encontrada:
                print(f"[Sistema] Encontrado en Menú Inicio: {ruta_encontrada}")
                os.startfile(ruta_encontrada)
                return f"Programa '{parametro}' iniciado."
            
            # 3. Tercero: Buscar en PATH del sistema (where)
            try:
                result = subprocess.run(
                    ["where", programa], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    exe_path = result.stdout.strip().split('\n')[0]
                    print(f"[Sistema] Encontrado en PATH: {exe_path}")
                    subprocess.Popen(exe_path, shell=True)
                    return f"Programa '{parametro}' iniciado."
            except Exception:
                pass
            
            # 4. Cuarto: Intentar abrir directamente (por si es un .exe en PATH)
            try:
                print(f"[Sistema] Intento directo: {programa}")
                subprocess.Popen(programa, shell=True)
                return f"Programa '{parametro}' iniciado (intento directo)."
            except Exception as e:
                return f"No pude encontrar el programa '{parametro}'. Error: {e}"
            
        elif accion == "cerrar_programa":
            if not parametro:
                return "Error: No se especificó el nombre del programa a cerrar."
                
            programa = parametro.lower()
            
            # Detección inteligente de programas comunes (soft matching)
            if "chrome" in programa or "google" in programa or "youtube" in programa:
                exe_name = "chrome.exe"
            elif "spotify" in programa:
                exe_name = "Spotify.exe"
            elif "edge" in programa:
                exe_name = "msedge.exe"
            elif "calc" in programa or "calculadora" in programa:
                exe_name = "CalculatorApp.exe"
            elif "nota" in programa or "notepad" in programa:
                exe_name = "notepad.exe"
            elif "riot" in programa or "valorant" in programa or "league" in programa:
                exe_name = "RiotClientServices.exe"
            elif "discord" in programa:
                exe_name = "Discord.exe"
            elif "steam" in programa:
                exe_name = "steam.exe"
            elif "epic" in programa:
                exe_name = "EpicGamesLauncher.exe"
            elif "explorador" in programa or "carpeta" in programa or "archivos" in programa:
                exe_name = "explorer.exe"
            elif "brave" in programa:
                exe_name = "brave.exe"
            elif "vsc" in programa or "code" in programa or "visual studio" in programa:
                exe_name = "Code.exe"
            else:
                # Si no es conocido, usar lo que dio el LLM y asegurar que acabe en .exe
                exe_name = programa
                if not exe_name.endswith(".exe"):
                    exe_name = exe_name.replace(" ", "") + ".exe"
                
            print(f"[Sistema] Intentando cerrar programa: {exe_name}")
            
            if exe_name == "explorer.exe":
                # IMPORTANTE: Si matamos explorer.exe con /T (Tree kill), cerramos todas las aplicaciones 
                # del usuario porque explorer es el proceso padre. 
                # En su lugar, usamos PowerShell para cerrar solo las ventanas de carpetas (el explorador)
                # sin matar la barra de tareas ni el escritorio.
                comando_kill = 'powershell -command "(New-Object -comObject Shell.Application).Windows() | ForEach-Object { $_.Quit() }"'
            else:
                # taskkill en Windows: /IM = Nombre de imagen, /F = Forzar, /T = Cerrar también todos los subprocesos (Chrome crea muchos)
                comando_kill = f'taskkill /IM "{exe_name}" /F /T'
            
            resultado = subprocess.run(comando_kill, shell=True, capture_output=True, text=True)
            
            if resultado.returncode == 0:
                return f"Programa '{exe_name}' cerrado con éxito."
            else:
                error_msg = resultado.stderr.strip() or resultado.stdout.strip()
                print(f"[Error Sistema] {error_msg}")
                return f"No se pudo cerrar '{exe_name}'. Windows dice: {error_msg}"
                
        elif accion == "leer_texto_seleccionado":
            try:
                import pyautogui
                import pyperclip
                import time
                
                # Limpiar portapapeles temporalmente para evitar leer algo viejo
                pyperclip.copy("")
                
                print("[Sistema] Simulando Ctrl+C para leer texto...")
                pyautogui.hotkey('ctrl', 'c')
                time.sleep(0.1)  # Pequeña pausa para que Windows copie el texto
                
                texto = pyperclip.paste()
                if not texto or texto.strip() == "":
                    return "Error: No encontré ningún texto. Dile al usuario: 'Por favor, selecciona primero el texto que quieres que lea y vuelve a pedírmelo'."
                
                # Limitar a 4000 caracteres para no agotar los tokens de Jarvis
                if len(texto) > 4000:
                    texto = texto[:4000] + "\n...[TEXTO TRUNCADO POR SER MUY LARGO]"
                    
                return f"Texto que el usuario está viendo (seleccionado):\n{texto}"
            except ImportError:
                return "Error: Faltan las librerías pyautogui o pyperclip. Se están instalando..."
            except Exception as e:
                return f"Error al intentar leer el texto: {e}"

        elif accion == "crear_archivo":
            if not parametro:
                parametro = "Nota_Jarvis.txt"
                
            # Asegurarnos de que tenga extensión .txt si no la puso
            if not parametro.endswith(".txt"):
                parametro += ".txt"
                
            # Obtener la ruta del Escritorio del usuario actual
            escritorio = os.path.join(os.path.expanduser('~'), 'Desktop')
            ruta_archivo = os.path.join(escritorio, parametro)
            
            print(f"[Sistema] Creando archivo en: {ruta_archivo}")
            
            try:
                with open(ruta_archivo, 'w', encoding='utf-8') as f:
                    f.write(contenido)
                return f"Archivo '{parametro}' creado exitosamente en tu Escritorio."
            except Exception as e:
                return f"Error al intentar crear el archivo: {e}"
                
        elif accion == "reproducir_youtube":
            p_lower = parametro.lower().strip()
            # Si Llama alucinó "música" o solo envió "youtube", abrimos la web principal en lugar de buscar un video
            if not p_lower or p_lower in ["youtube", "youtube.com", "música", "musica"]:
                print(f"[Sistema] Abriendo página principal de YouTube.")
                webbrowser.open("https://www.youtube.com", new=2)
                return "Abriendo la página principal de YouTube."
                
            print(f"[Sistema] Buscando en YouTube: {parametro}")
            
            # Formatear búsqueda para URL
            query = parametro.replace(" ", "+")
            url_busqueda = f"https://www.youtube.com/results?search_query={query}"
            
            try:
                # Extraer HTML de forma oculta
                r = httpx.get(url_busqueda, timeout=10.0)
                # Extraer el ID del primer vídeo usando regex.
                # IMPORTANTE: Usamos "videoRenderer" para evitar extraer IDs de anuncios o videos recomendados aleatorios.
                match = re.search(r'"videoRenderer":\{"videoId":"([a-zA-Z0-9_-]{11})"', r.text)
                
                if match:
                    video_id = match.group(1)
                    url_video = f"https://www.youtube.com/watch?v={video_id}"
                    print(f"[Sistema] Video encontrado. Auto-reproduciendo: {url_video}")
                    webbrowser.open(url_video, new=2)
                    return f"Reproduciendo el primer video de '{parametro}' en YouTube."
                else:
                    # Fallback si no encuentra el ID
                    webbrowser.open(url_busqueda, new=2)
                    return f"Abriendo resultados de búsqueda de '{parametro}' en YouTube."
            except Exception as e:
                print(f"[Error Sistema] Fallo al raspar YouTube: {e}")
                webbrowser.open(url_busqueda, new=2)
                return f"Abriendo resultados de búsqueda de '{parametro}' en YouTube."
            
        elif accion == "interactuar_app":
            # Interactuar con aplicaciones usando protocolos y automatización
            if not parametro:
                return "Error: No se especificó qué hacer."
            
            app = parametro.lower().strip()
            contenido_lower = contenido.lower().strip() if contenido else ""
            
            # === PROTOCOLOS DE APPS ===
            # Steam
            protocolos_steam = {
                "tienda": "steam://store",
                "store": "steam://store",
                "biblioteca": "steam://open/games",
                "libreria": "steam://open/games",
                "library": "steam://open/games",
                "amigos": "steam://open/friends",
                "comunidad": "steam://open/community",
                "descargas": "steam://open/downloads",
                "configuracion": "steam://open/settings",
                "ajustes": "steam://open/settings",
            }
            
            # Discord
            protocolos_discord = {
                "abrir": "discord://",    
            }
            
            if "steam" in app:
                # Buscar la sección específica
                for clave, url in protocolos_steam.items():
                    if clave in app or clave in contenido_lower:
                        print(f"[Sistema] Abriendo Steam protocolo: {url}")
                        os.startfile(url)
                        return f"Abriendo {clave} de Steam."
                # Si solo dijo "steam" sin sección, abrir Steam normal
                os.startfile("steam://open/main")
                return "Abriendo Steam."
            
            elif "discord" in app:
                os.startfile("discord://")
                return "Abriendo Discord."
            
            # === AUTOMATIZACIÓN CON PYAUTOGUI ===
            # Para acciones genéricas: clic, escribir, teclas
            else:
                try:
                    import pyautogui
                    
                    if "escribir" in app or "tipear" in app:
                        pyautogui.write(contenido, interval=0.03)
                        return f"Texto escrito: '{contenido}'"
                    
                    elif "tecla" in app or "presionar" in app:
                        tecla = contenido_lower or parametro
                        pyautogui.press(tecla)
                        return f"Tecla '{tecla}' presionada."
                    
                    elif "atajo" in app or "shortcut" in app or "combinacion" in app:
                        # Parsear combinaciones tipo "ctrl+c", "alt+tab"
                        teclas = [t.strip() for t in contenido_lower.split("+")]
                        pyautogui.hotkey(*teclas)
                        return f"Atajo '{contenido}' ejecutado."
                    
                    elif "click" in app or "clic" in app:
                        pyautogui.click()
                        return "Clic realizado en la posición actual del mouse."
                    
                    else:
                        return f"No sé cómo interactuar con '{parametro}'. Puedo abrir secciones de Steam/Discord, escribir texto, presionar teclas o hacer clics."
                        
                except Exception as e:
                    return f"Error al interactuar: {e}"
        
        elif accion == "modificar_volumen":
            try:
                from pycaw.pycaw import AudioUtilities
                
                volume = AudioUtilities.GetSpeakers().EndpointVolume
                
                p = parametro.lower().strip()
                if p in ["mutear", "silenciar", "mute"]:
                    volume.SetMute(1, None)
                    return "Sistema silenciado."
                elif p in ["desmutear", "activar", "unmute"]:
                    volume.SetMute(0, None)
                    return "Sistema desilenciado."
                
                current_vol = volume.GetMasterVolumeLevelScalar()
                if p == "subir":
                    new_vol = min(1.0, current_vol + 0.1)
                    volume.SetMasterVolumeLevelScalar(new_vol, None)
                    return f"Volumen subido al {int(new_vol * 100)}%."
                elif p == "bajar":
                    new_vol = max(0.0, current_vol - 0.1)
                    volume.SetMasterVolumeLevelScalar(new_vol, None)
                    return f"Volumen bajado al {int(new_vol * 100)}%."
                else:
                    p = p.replace("%", "").strip()
                    val = float(p)
                    if val > 1.0:
                        val = val / 100.0
                    val = max(0.0, min(1.0, val))
                    volume.SetMasterVolumeLevelScalar(val, None)
                    volume.SetMute(0, None)
                    return f"Volumen configurado al {int(val * 100)}%."
            except Exception as e:
                return f"Error al modificar volumen: {e}"

        elif accion == "modificar_brillo":
            try:
                import screen_brightness_control as sbc
                p = parametro.lower().strip()
                
                try:
                    current_bright = sbc.get_brightness()
                    if isinstance(current_bright, list):
                        current_bright = current_bright[0]
                    # Limitar brillo a rango [0, 100] si el sistema devuelve valores atípicos
                    if current_bright > 100:
                        current_bright = 100
                    elif current_bright < 0:
                        current_bright = 0
                except Exception:
                    current_bright = 50
                
                if p == "subir":
                    new_bright = min(100, current_bright + 10)
                    sbc.set_brightness(new_bright)
                    return f"Brillo subido al {new_bright}%."
                elif p == "bajar":
                    new_bright = max(0, current_bright - 10)
                    sbc.set_brightness(new_bright)
                    return f"Brillo bajado al {new_bright}%."
                else:
                    p = p.replace("%", "").strip()
                    val = int(p)
                    val = max(0, min(100, val))
                    sbc.set_brightness(val)
                    return f"Brillo configurado al {val}%."
            except Exception as e:
                return f"Error al modificar brillo: {e}"

        elif accion == "apagar_sistema":
            print("[Sistema] Apagando el PC en 15 segundos...")
            os.system("shutdown /s /t 15")
            return "Apagando el sistema en 15 segundos. Puedes decir 'cancela el apagado' para abortar."

        elif accion == "reiniciar_sistema":
            print("[Sistema] Reiniciando el PC en 15 segundos...")
            os.system("shutdown /r /t 15")
            return "Reiniciando el sistema en 15 segundos. Puedes decir 'cancela el apagado' para abortar."

        elif accion == "suspender_sistema":
            print("[Sistema] Suspendiendo el PC...")
            os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
            return "Orden de suspensión enviada al sistema."

        elif accion == "cancelar_apagado":
            print("[Sistema] Cancelando apagado/reinicio programado...")
            os.system("shutdown /a")
            return "Apagado/reinicio programado cancelado con éxito."
            
        elif accion == "apagar_monitor":
            print("[Sistema] Apagando monitores...")
            import ctypes
            # 0x0112 is WM_SYSCOMMAND, 0xF170 is SC_MONITORPOWER, 2 is OFF
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
            return "El monitor ha sido apagado. Mueva el ratón para encenderlo."
            
        elif accion == "controlar_luces":
            print(f"[Sistema] Configurando luces RGB a: {parametro}")
            try:
                from openrgb import OpenRGBClient
                from openrgb.utils import RGBColor
                
                client = OpenRGBClient()
                
                # Mapeo de colores básicos
                colores = {
                    "rojo": RGBColor(255, 0, 0),
                    "azul": RGBColor(0, 0, 255),
                    "verde": RGBColor(0, 255, 0),
                    "blanco": RGBColor(255, 255, 255),
                    "apagado": RGBColor(0, 0, 0),
                    "amarillo": RGBColor(255, 255, 0),
                    "naranja": RGBColor(255, 128, 0),
                    "morado": RGBColor(128, 0, 128),
                    "rosa": RGBColor(255, 0, 255),
                    "celeste": RGBColor(0, 255, 255)
                }
                
                color_rgb = colores.get(parametro.lower(), RGBColor(255, 255, 255))
                
                # Si el usuario dice "apagar", lo forzamos al color negro/apagado
                if "apagad" in parametro.lower() or "off" in parametro.lower():
                    color_rgb = RGBColor(0, 0, 0)
                
                for device in client.devices:
                    device.set_color(color_rgb)
                    
                return f"Luces ajustadas al color {parametro} correctamente."
            except Exception as e:
                print(f"[Error RGB] {e}")
                return "No se pudo controlar las luces. Asegúrese de que el software OpenRGB esté descargado y el SDK Server esté iniciado."
            
            
        else:
            return f"Acción de sistema desconocida: {accion}"

    except Exception as e:
        print(f"[Error Sistema] Excepción en controlar_sistema: {str(e)}")
        return "Lo siento señor, ocurrió un error interno al intentar realizar esa acción en el sistema."

# Bloque de prueba
if __name__ == "__main__":
    print(controlar_sistema("abrir_web", "youtube.com"))
