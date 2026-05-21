import os
import tempfile
import subprocess
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# SISTEMA DE VOZ DUAL: ElevenLabs (premium) + Edge-TTS (backup)
# ============================================================
# ElevenLabs suena ULTRA natural pero tiene 10,000 caracteres gratis/mes.
# Edge-TTS es gratis ilimitado pero suena más robótico.
# Jarvis usará ElevenLabs mientras tenga saldo, y si se acaba, Edge-TTS.

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")

# Voces GRATUITAS de ElevenLabs (pre-hechas, no necesitan plan pago):
# "pNInz6obpgDQGcFmaJgB" = Adam (masculina, profunda)
# "ErXwobaYiN019PkySvjV" = Antoni (masculina, cálida)  
# "VR6AewLTigWG4xSOukaG" = Arnold (masculina, grave, tipo narrador)
# "29vD33N1CtxCmqQRPOHJ" = Drew (masculina, joven)
# "TxGEqnHWrfWFTfGW9XjX" = Josh (masculina, natural)
# "yoZ06aMxZJJ28mfd3POQ" = Sam (masculina, conversacional)
ELEVENLABS_VOICE = "ErXwobaYiN019PkySvjV"  # Antoni (cálida, amigable)

# Voz de respaldo (Edge-TTS, gratis ilimitado)
EDGE_VOZ_BACKUP = "es-CO-GonzaloNeural"


LOCK_FILE = os.path.join(tempfile.gettempdir(), "jarvis_speaking.lock")

# Limpiar posible bloqueo huérfano de ejecuciones anteriores al importar
try:
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)
except:
    pass


def _reproducir_audio(archivo: str):
    """Reproduce un archivo de audio de forma síncrona sin sleeps innecesarios."""
    # Crear archivo de bloqueo de voz
    try:
        with open(LOCK_FILE, "w") as f:
            f.write("1")
    except:
        pass

    try:
        from playsound import playsound
        playsound(archivo)
    except Exception as e:
        print(f"[TTS] Error al reproducir audio: {e}")
    finally:
        # Eliminar archivo de bloqueo de voz pase lo que pase
        try:
            if os.path.exists(LOCK_FILE):
                os.remove(LOCK_FILE)
        except:
            pass


def _hablar_elevenlabs(texto: str) -> bool:
    """Intenta hablar con ElevenLabs. Retorna True si tuvo éxito."""
    if not ELEVENLABS_API_KEY:
        return False
    
    try:
        from elevenlabs import ElevenLabs
        import time
        
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        
        # Archivo único para evitar el bloqueo de playsound
        archivo_temp = os.path.join(tempfile.gettempdir(), f"Jarvis_voz_{int(time.time()*1000)}.mp3")
        
        # Generar audio con ElevenLabs
        audio_generator = client.text_to_speech.convert(
            text=texto,
            voice_id=ELEVENLABS_VOICE,
            model_id="eleven_multilingual_v2",  # Modelo multilingüe (soporta español nativo)
            output_format="mp3_44100_128"
        )
        
        # Escribir los chunks de audio al archivo
        with open(archivo_temp, 'wb') as f:
            for chunk in audio_generator:
                f.write(chunk)
        
        def run_audio():
            print("[TTS] 🎙️ Usando voz premium (ElevenLabs)")
            _reproducir_audio(archivo_temp)
            try:
                os.remove(archivo_temp)
            except:
                pass

        import threading
        t = threading.Thread(target=run_audio)
        t.start()
        return True
    except Exception as e:
        print(f"[TTS] ElevenLabs falló ({e}). Usando voz de respaldo...")
        return False


def _hablar_edge_tts(texto: str):
    """Habla con Edge-TTS (respaldo gratuito ilimitado)."""
    import asyncio
    import edge_tts
    import time
    import threading
    
    archivo_temp = os.path.join(tempfile.gettempdir(), f"Jarvis_backup_{int(time.time()*1000)}.mp3")
    
    async def generar():
        communicate = edge_tts.Communicate(texto, EDGE_VOZ_BACKUP)
        await communicate.save(archivo_temp)
    
    def run_tts():
        asyncio.run(generar())
        print("[TTS] 📢 Usando voz de Microsoft (Edge-TTS)")
        _reproducir_audio(archivo_temp)
        try:
            os.remove(archivo_temp)
        except:
            pass

    try:
        t = threading.Thread(target=run_tts)
        t.start()
    except Exception as e:
        print(f"[TTS] Error en Edge-TTS: {e}")
    finally:
        try:
            os.remove(archivo_temp)
        except:
            pass


def hablar(texto: str):
    """
    Jarvis habla en voz alta usando la voz de Microsoft (Edge-TTS).
    """
    if not texto or len(texto.strip()) < 2:
        return
    
    # Limpiar el texto para la voz
    texto_limpio = texto.replace("🎵", "").replace("🤖", "").replace("⚡", "").replace("🧠", "").replace("🔋", "").strip()
    
    # Usar directamente la voz de Microsoft (Edge-TTS)
    _hablar_edge_tts(texto_limpio)


if __name__ == "__main__":
    hablar("Hola señor, soy Jarvis. Ahora mi voz suena mucho más natural, ¿no te parece?")
