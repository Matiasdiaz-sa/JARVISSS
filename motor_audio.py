import os
import tempfile
import numpy as np
import sounddevice as sd
import httpx
import queue
import io
import wave
import time
from dotenv import load_dotenv
from openai import OpenAI
from tts import hablar

load_dotenv()

LOCK_FILE = os.path.join(tempfile.gettempdir(), "jarvis_speaking.lock")

# Limpiar posible bloqueo huérfano de ejecuciones anteriores al iniciar
try:
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)
except:
    pass

# Cliente de Groq para Whisper
client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)


# ============================================================
# CONFIGURACIÓN DEL MICRÓFONO SIEMPRE ACTIVO
# ============================================================
RATE = 16000                    # Frecuencia de muestreo
UMBRAL_VOZ = 120 # Umbral de energía para empezar/mantener grabación
SILENCIO_PARA_CORTAR = 1.0      # Segundos de silencio para finalizar el comando
DURACION_MINIMA = 0.5           # Segundos mínimos que debe durar un audio para procesarlo ruidos sueltos

# Estado de Jarvis (despierto o dormido)
jarvis_activo = True


def calcular_energia(audio_data):
    """Calcula el nivel de energía (volumen) de un bloque de audio."""
    return np.sqrt(np.mean(audio_data.astype(np.float32) ** 2))


def escuchar_continuo(callback_ui=None):
    """
    Escucha continuamente el micrófono usando openwakeword.
    Cuando detecta la palabra clave 'hey_jarvis':
    - Si está inactivo (hibernando), se activa y anuncia que está listo.
    - Si está activo, emite un sonido rápido y graba el comando del usuario.
    """
    global jarvis_activo
    import logging
    logging.getLogger().setLevel(logging.ERROR)
    
    from openwakeword.model import Model
    import winsound
    import os
    
    print("[Reconocimiento] Cargando modelo predeterminado 'hey_jarvis'...")
    oww_model = Model(wakeword_models=["hey_jarvis"], vad_threshold=0.5, inference_framework="onnx")
        
    wakeword_key = list(oww_model.models.keys())[0]
    print(f"[Reconocimiento] Modelo cargado con éxito. Palabra de activación: '{wakeword_key}'")
    
    q = queue.Queue()
    
    def callback(indata, frames, time_info, status):
        q.put(indata.copy())
 
    # Usamos blocksize=1280 (80 ms a 16 kHz) que es el tamaño de buffer exacto requerido por openwakeword
    with sd.InputStream(samplerate=RATE, channels=1, dtype='int16', callback=callback, blocksize=1280):
        # Jarvis inicia esperando la palabra de activación
        estado_escucha = "esperando_wake"
        audio_chunks = []
        ultimo_sonido = time.time()
        inicio_grabacion = time.time()
        max_energia_grabada = 0.0
        
        def forzar_grabacion():
            nonlocal estado_escucha, audio_chunks, ultimo_sonido, max_energia_grabada
            print("\n[⌨️] ¡Atajo detectado (Ctrl+Alt+J)! Activando grabación de comando...")
            
            # Cortar audio si Jarvis está hablando
            import tempfile
            STOP_FILE = os.path.join(tempfile.gettempdir(), "jarvis_stop.lock")
            try:
                with open(STOP_FILE, "w") as f:
                    f.write("1")
            except:
                pass
                
            # Limpiar cola de audio para evitar procesar ruido residual
            while not q.empty():
                q.get()
            audio_chunks = []
            ultimo_sonido = time.time()
            inicio_grabacion = time.time()
            max_energia_grabada = 0.0
            estado_escucha = "grabando_comando"
            
        import keyboard
        # Registrar atajo de teclado global
        keyboard.add_hotkey('ctrl+alt+j', forzar_grabacion)
        
        ultimo_bloqueo = 0.0
        while True:
            # Si Jarvis está hablando (TTS activo), vaciar la cola de audio y esperar
            if os.path.exists(LOCK_FILE):
                try:
                    with open(LOCK_FILE, "r") as f:
                        ts = float(f.read().strip())
                    if time.time() - ts > 15.0:
                        os.remove(LOCK_FILE)
                    else:
                        while not q.empty():
                            q.get()
                        sd.sleep(50)
                        ultimo_bloqueo = time.time()
                        continue
                except Exception:
                    try:
                        os.remove(LOCK_FILE)
                    except:
                        pass
                
            # Cooldown de 0.8 segundos después de dejar de hablar para evitar eco tardío en los buffers
            if time.time() - ultimo_bloqueo < 0.8:
                while not q.empty():
                    q.get()
                sd.sleep(50)
                continue
                
            if not q.empty():
                bloque = q.get()
                
                if not jarvis_activo:
                    if callback_ui:
                        callback_ui("hibernando", 0, 0.0)
                        
                if estado_escucha == "esperando_wake":
                    # Extraer el canal mono y aplanar el buffer
                    chunk = bloque.squeeze()
                    
                    # Calcular la energía del bloque de audio
                    energia = calcular_energia(bloque)
                    
                    # Evitar ejecutar la red neuronal si hay silencio absoluto o el micrófono está apagado.
                    # Los modelos ONNX suelen dar predicciones falsas estables de ~0.37 cuando reciben todo ceros (silencio).
                    prediction = oww_model.predict(chunk)
                    
                    if energia > 30:
                        conf = prediction.get(wakeword_key, 0.0)
                    else:
                        conf = 0.0
                    
                    if callback_ui and jarvis_activo:
                        callback_ui("esperando", energia, conf)
                    
                    # Umbral bajo (0.3) = máxima sensibilidad funcional, activa con decir "Jarvis" bajito
                    if conf > 0.3:
                        # ¡Wake word detectado!
                        if not jarvis_activo:
                            # Estaba hibernando, despertar sistemas
                            jarvis_activo = True
                            print("\n" + "═"*40)
                            print(" ⚡ INICIANDO SISTEMAS Jarvis...")
                            print("  ├ Cerebro: ONLINE")
                            print("  ├ Escucha: ONLINE")
                            print("  └ Todos los sistemas operativos.")
                            print("═"*40)
                            
                            # Pitidos desactivados para evitar bucle de retroalimentación en el micrófono
                            # winsound.Beep(800, 100)
                            # winsound.Beep(1200, 150)
                            
                            hablar("Sistemas en línea. Cerebro cargado. ¿En qué te ayudo, señor?")
                            print(f"\n[🎧] Jarvis a la escucha de comandos... (Palabra: 'Jarvis')\n")
                            # Limpiar cola para no acumular ruido de la respuesta TTS
                            while not q.empty():
                                q.get()
                        else:
                            # Estaba activo, listo para capturar un comando
                            print(f"\n[🎙️] ¡Jarvis detectado! (conf: {conf:.2f})")
                            
                            # Pitidos desactivados para evitar bucle de retroalimentación en el micrófono
                            # winsound.Beep(1000, 80)
                            # winsound.Beep(1300, 80)
                            
                            print("[🎙️] Grabando comando...")
                            estado_escucha = "grabando_comando"
                            audio_chunks = []
                            max_energia_grabada = 0.0
                            ultimo_sonido = time.time()
                            inicio_grabacion = time.time()
                            
                elif estado_escucha == "grabando_comando":
                    energia = calcular_energia(bloque)
                    audio_chunks.append(bloque)
                    max_energia_grabada = max(max_energia_grabada, energia)
                    
                    if callback_ui:
                        callback_ui("grabando", energia, max_energia_grabada)
                        
                    if energia > UMBRAL_VOZ:
                        ultimo_sonido = time.time()
                        
                    # Detener grabación si hay silencio continuo o si pasaron más de 12 segundos (timeout de seguridad)
                    if (time.time() - ultimo_sonido > SILENCIO_PARA_CORTAR) or (time.time() - inicio_grabacion > 12.0):
                        print("[🎙️] Procesando comando grabado...")
                        audio_completo = np.concatenate(audio_chunks, axis=0)
                        duracion = len(audio_completo) / RATE
                        
                        print(f"[🎙️] Grabación finalizada. Duración: {duracion:.1f}s | Energía máx: {max_energia_grabada:.0f} (Umbral: {UMBRAL_VOZ})")
                        
                        if duracion >= DURACION_MINIMA:
                            print(f"[⚙️] Transcribiendo y pensando...")
                            if callback_ui:
                                callback_ui("pensando", 0, 0.0)
                                
                            texto = transcribir_audio(audio_completo)
                            
                            if texto:
                                texto_lower = texto.lower().strip()
                                
                                # === COMANDOS DE APAGADO/HIBERNACIÓN ===
                                palabras_apagar = ["apágate", "apagate", "apagar", "duérmete", "dormite", "modo sueño", "silencio"]
                                if any(p in texto_lower for p in palabras_apagar):
                                    print("\n" + "═"*40)
                                    print(" 💤 APAGANDO SISTEMAS...")
                                    print("  ├ Desactivando escucha activa")
                                    print("  └ Entrando en modo hibernación")
                                    print("═"*40)
                                    
                                    hablar("Apagando sistemas. Estaré en hibernación. Di Jarvis para despertarme.")
                                    jarvis_activo = False
                                    print(f"\n[💤] Jarvis en HIBERNACIÓN. Esperando: 'Jarvis'\n")
                                else:
                                    # Procesar comando normal
                                    enviar_comando_a_cerebro(texto)
                            else:
                                print("[⚙️] Transcripción vacía. Posible silencio o corte prematuro.")
                        
                        # Limpiar y regresar a la espera de wake word
                        estado_escucha = "esperando_wake"
                            
                        while not q.empty():
                            q.get()
                            
            else:
                sd.sleep(10)


def transcribir_audio(audio_completo):
    """Envía audio a Whisper (vía Groq) para transcripción."""
    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(RATE)
        wav_file.writeframes(audio_completo.tobytes())
    
    wav_io.name = "audio.wav"
    wav_io.seek(0)
    
    try:
        transcription = client.audio.transcriptions.create(
            file=wav_io,
            model="whisper-large-v3-turbo"
        )
        texto = transcription.text.strip()
        
        # Ignorar alucinaciones de Whisper
        alucinaciones = [
            "subtítulos por la comunidad de amara.org",
            "subtítulos realizados por la comunidad de amara.org",
            "gracias por ver el video",
            "gracias.",
            "thanks for watching",
        ]
        if not texto or texto.lower() in alucinaciones or len(texto) < 3:
            return None
            
        # Hardcodes para errores de pronunciación/alucinaciones
        correcciones = {
            "camarones y viniles": "creep de radiohead",
            "crip de radiohead": "creep de radiohead",
            "crep de radiohead": "creep de radiohead",
            "grip de radiohead": "creep de radiohead",
            "crip": "creep",
            "grip": "creep"
        }
        
        texto_lower = texto.lower()
        for error, correccion in correcciones.items():
            if error in texto_lower:
                texto = texto_lower.replace(error, correccion)
                texto_lower = texto
                
        print(f"[💬] Tú: '{texto}'")
        return texto
    except Exception as e:
        print(f"[❌] Error en Whisper: {e}")
        return None


def enviar_comando_a_cerebro(texto):
    """Envía el texto transcrito al servidor FastAPI local."""
    try:
        respuesta = httpx.post(
            "http://127.0.0.1:8000/api/command", 
            json={"command": texto},
            timeout=30.0
        )
        if respuesta.status_code == 200:
            datos = respuesta.json()
            texto_respuesta = datos.get('respuesta_texto', '')
            print(f"[🧠] Jarvis: {texto_respuesta}")
            
            # Solo hablar si el servidor NO habló ya (preview de herramientas)
            if not datos.get('ya_hablado', False):
                hablar(texto_respuesta)
        else:
            print(f"[❌] Error en servidor: {respuesta.status_code}")
    except httpx.RequestError as e:
        print(f"[❌] No se pudo conectar al servidor. ¿Está main.py corriendo? Error: {e}")


def iniciar_cliente():
    print("\n" + "═"*40)
    print(" 🧠 Jarvis - Sistema de IA Activo")
    print(" 🔊 Escuchando por voz: 'Jarvis'")
    print(" ⌨️  Atajo de teclado global: [Ctrl + Alt + J]")
    print(" Listo para recibir comandos. (Ctrl+C para salir)")
    print("═"*40 + "\n")
    
    print("[🎧] Jarvis a la escucha...\n")
    
    try:
        escuchar_continuo()
    except KeyboardInterrupt:
        print("\n[!] Apagando a Jarvis...")


if __name__ == '__main__':
    iniciar_cliente()
