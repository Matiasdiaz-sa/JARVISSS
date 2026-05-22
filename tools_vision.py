from PIL import ImageGrab
import io
import base64

def ver_pantalla():
    """Toma una captura de pantalla y la devuelve codificada en base64 para el LLM."""
    try:
        import os
        try:
            with open("vigilante_pantalla.lock", "w") as f:
                f.write("1")
        except Exception:
            pass
        print("[Visión] Capturando la pantalla...")
        pantalla = ImageGrab.grab()
        
        # Redimensionar para no sobrepasar límites de API y hacer el envío rápido
        # Mantenemos el aspecto pero máximo 1280x720
        pantalla.thumbnail((1280, 720))
        
        buffered = io.BytesIO()
        # Guardar en JPEG para comprimir, quality=80 es un buen balance
        pantalla.save(buffered, format="JPEG", quality=80)
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        return img_str
    except Exception as e:
        print(f"[Visión] Error capturando pantalla: {e}")
        return None

def hacer_clic_visual(descripcion: str, esperar_segundos: int = 0) -> str:
    """
    Busca un elemento visual en la pantalla descrito en texto, encuentra sus coordenadas 
    usando Gemini, y hace clic sobre él.
    """
    try:
        import os
        import re
        import pyautogui
        import time
        from openai import OpenAI
        from dotenv import load_dotenv

        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return "Error: No hay GEMINI_API_KEY configurada para usar la visión avanzada."

        if esperar_segundos > 0:
            print(f"[Visión] Esperando {esperar_segundos}s antes de capturar pantalla para '{descripcion}'...")
            time.sleep(esperar_segundos)

        print(f"[Visión] Buscando visualmente: '{descripcion}'...")
        pantalla = ImageGrab.grab()
        ancho, alto = pantalla.size
        
        buffered = io.BytesIO()
        pantalla.save(buffered, format="JPEG", quality=85)
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

        client = OpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )

        vision_prompt = f'Find "{descripcion}" on the screen. Return ONLY its bounding box in the format [ymin, xmin, ymax, xmax] where values are from 0 to 1000. If you cannot find it, reply with "not found".'
        vision_messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": vision_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_str}"}}
                ]
            }
        ]

        # Intentar con Gemini, si falla por rate limit usar Groq con visión
        resultado = None
        try:
            response = client.chat.completions.create(
                model="gemini-2.0-flash",
                messages=vision_messages
            )
            resultado = response.choices[0].message.content.strip()
            print(f"[Visión Gemini] Respuesta: {resultado}")
        except Exception as gemini_error:
            error_msg = str(gemini_error)
            if "429" in error_msg or "Quota exceeded" in error_msg:
                print(f"[Visión] Gemini en rate limit. Usando Groq con visión...")
                groq_key = os.getenv("GROQ_API_KEY")
                if groq_key:
                    try:
                        client_groq = OpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1")
                        response = client_groq.chat.completions.create(
                            model="meta-llama/llama-4-scout-17b-16e-instruct",
                            messages=vision_messages
                        )
                        resultado = response.choices[0].message.content.strip()
                        print(f"[Visión Groq] Respuesta: {resultado}")
                    except Exception as groq_error:
                        return f"Error: Tanto Gemini como Groq fallaron al analizar la pantalla. Groq: {groq_error}"
                else:
                    return "Error de Límite (429): Gemini agotó su cuota y no hay GROQ_API_KEY configurada como respaldo."
            else:
                return f"Error inesperado al hacer clic visual: {gemini_error}"
        
        if not resultado:
            return "Error: No se obtuvo respuesta del modelo de visión."
        
        if "not found" in resultado.lower():
            return f"No pude encontrar '{descripcion}' en la pantalla actual."
            
        match = re.search(r"\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]", resultado)
        if match:
            ymin, xmin, ymax, xmax = map(int, match.groups())
            
            # Calcular centro en coordenadas reales
            x_centro = int(((xmin + xmax) / 2 / 1000.0) * ancho)
            y_centro = int(((ymin + ymax) / 2 / 1000.0) * alto)
            
            print(f"[Visión] Haciendo clic en coordenadas ({x_centro}, {y_centro}) para '{descripcion}'")
            pyautogui.moveTo(x_centro, y_centro, duration=0.5)
            pyautogui.click()
            return f"Hice clic exitosamente en '{descripcion}'."
        else:
            return f"No pude interpretar la ubicación de '{descripcion}'. El modelo respondió: {resultado}"
            
    except ImportError as e:
        return f"Error: Faltan dependencias para el clic visual ({e}). Instala pyautogui."
    except Exception as e:
        return f"Error inesperado al hacer clic visual: {e}"

def _get_hwnd_by_title(title_query: str):
    import win32gui
    hwnds = []
    def enum_handler(hwnd, ctx):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd).lower()
            if title_query.lower() in title:
                hwnds.append(hwnd)
    win32gui.EnumWindows(enum_handler, None)
    return hwnds[0] if hwnds else None

def _capture_window(hwnd):
    import win32gui
    import win32ui
    import ctypes
    from PIL import Image
    
    left, top, right, bot = win32gui.GetWindowRect(hwnd)
    w = right - left
    h = bot - top
    if w <= 0 or h <= 0:
        return None, 0, 0

    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC  = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()

    saveBitMap = win32ui.CreateBitmap()
    saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
    saveDC.SelectObject(saveBitMap)

    # PrintWindow(hwnd, hdc, PW_RENDERFULLCONTENT = 2)
    result = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)
    
    bmpinfo = saveBitMap.GetInfo()
    bmpstr = saveBitMap.GetBitmapBits(True)
    
    im = Image.frombuffer('RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRX', 0, 1)

    win32gui.DeleteObject(saveBitMap.GetHandle())
    saveDC.DeleteDC()
    mfcDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwndDC)

    if result == 1:
        return im, w, h
    return None, 0, 0

def hacer_clic_fondo(descripcion: str, ventana_titulo: str, esperar_segundos: int = 0) -> str:
    """
    Busca un elemento visual dentro de una ventana específica (incluso si está en segundo plano)
    y envía un evento de clic lógico (PostMessage) sin mover el ratón físico.
    """
    try:
        import os
        import re
        import time
        import win32api
        import win32con
        import win32gui
        from openai import OpenAI
        from dotenv import load_dotenv

        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return "Error: No hay GEMINI_API_KEY configurada para usar la visión avanzada."

        if esperar_segundos > 0:
            print(f"[Visión Fondo] Esperando {esperar_segundos}s antes de capturar '{ventana_titulo}'...")
            time.sleep(esperar_segundos)

        hwnd = _get_hwnd_by_title(ventana_titulo)
        if not hwnd:
            return f"No se encontró ninguna ventana abierta con el título '{ventana_titulo}'."

        nombre_real = win32gui.GetWindowText(hwnd)
        print(f"[Visión Fondo] Capturando ventana '{nombre_real}' (HWND: {hwnd})...")
        
        pantalla, ancho, alto = _capture_window(hwnd)
        if not pantalla:
            return f"Fallo al intentar capturar la imagen de la ventana '{nombre_real}'."

        buffered = io.BytesIO()
        pantalla.save(buffered, format="JPEG", quality=85)
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

        client = OpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )

        vision_prompt = f'Find "{descripcion}" in this application window. Return ONLY its bounding box in the format [ymin, xmin, ymax, xmax] where values are from 0 to 1000. If you cannot find it, reply with "not found".'
        vision_messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": vision_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_str}"}}
                ]
            }
        ]

        # Intentar con Gemini, si falla por rate limit usar Groq con visión
        resultado = None
        try:
            response = client.chat.completions.create(
                model="gemini-2.0-flash",
                messages=vision_messages
            )
            resultado = response.choices[0].message.content.strip()
            print(f"[Visión Gemini] Respuesta: {resultado}")
        except Exception as gemini_error:
            error_msg = str(gemini_error)
            if "429" in error_msg or "Quota exceeded" in error_msg:
                print(f"[Visión Fondo] Gemini en rate limit. Usando Groq con visión...")
                groq_key = os.getenv("GROQ_API_KEY")
                if groq_key:
                    try:
                        client_groq = OpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1")
                        response = client_groq.chat.completions.create(
                            model="meta-llama/llama-4-scout-17b-16e-instruct",
                            messages=vision_messages
                        )
                        resultado = response.choices[0].message.content.strip()
                        print(f"[Visión Groq] Respuesta: {resultado}")
                    except Exception as groq_error:
                        return f"Error: Tanto Gemini como Groq fallaron. Groq: {groq_error}"
                else:
                    return "Error de Límite (429): Gemini agotó su cuota y no hay GROQ_API_KEY como respaldo."
            else:
                return f"Error inesperado al hacer clic en fondo: {gemini_error}"
        
        if not resultado:
            return "Error: No se obtuvo respuesta del modelo de visión."
        
        if "not found" in resultado.lower():
            return f"No pude encontrar '{descripcion}' dentro de la ventana '{nombre_real}'."
            
        match = re.search(r"\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]", resultado)
        if match:
            ymin, xmin, ymax, xmax = map(int, match.groups())
            
            x_centro = int(((xmin + xmax) / 2 / 1000.0) * ancho)
            y_centro = int(((ymin + ymax) / 2 / 1000.0) * alto)
            
            print(f"[Visión Fondo] Enviando clic sintético a coordenadas ({x_centro}, {y_centro}) de '{nombre_real}'")
            
            lparam = win32api.MAKELONG(x_centro, y_centro)
            # Enviar mensaje de botón apretado y soltado a la ventana
            win32api.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
            time.sleep(0.05)
            win32api.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)
            
            return f"Clic enviado en segundo plano a '{descripcion}' dentro de '{nombre_real}'."
        else:
            return f"No pude interpretar la ubicación de '{descripcion}'. El modelo respondió: {resultado}"

    except ImportError as e:
        return f"Error: Faltan dependencias (pywin32) para clics en segundo plano ({e})."
    except Exception as e:
        return f"Error inesperado al hacer clic en fondo: {e}"

def analizar_pantalla(prompt: str) -> str:
    """Toma una captura de pantalla y se la envía a la IA de visión con el prompt dado."""
    try:
        import os
        from openai import OpenAI
        from dotenv import load_dotenv
        
        try:
            with open("vigilante_pantalla.lock", "w") as f:
                f.write("1")
        except Exception:
            pass

        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return "Error: No hay GEMINI_API_KEY configurada para usar la visión."

        img_str = ver_pantalla()
        if not img_str:
            return "Error: No se pudo capturar la pantalla."

        client = OpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )

        vision_messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_str}"}}
                ]
            }
        ]

        response = client.chat.completions.create(
            model="gemini-2.0-flash",
            messages=vision_messages,
            temperature=0.2,
            max_tokens=150
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"[Visión] Error en analizar_pantalla: {e}")
        return f"Error analizando pantalla: {e}"
    finally:
        try:
            import os
            if os.path.exists("vigilante_pantalla.lock"):
                os.remove("vigilante_pantalla.lock")
        except Exception:
            pass
