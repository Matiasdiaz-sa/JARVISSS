import re
import os

main_path = r"e:\Proyecto-IALOCAL\main.py"
tts_path = r"e:\Proyecto-IALOCAL\tts.py"

with open(main_path, "r", encoding="utf-8") as f:
    main_code = f.read()

# Replace LLM calls with asyncio.to_thread
main_code = re.sub(
    r"response = client_principal\.chat\.completions\.create\((.*?)\)",
    r"response = await asyncio.to_thread(client_principal.chat.completions.create, \1)",
    main_code,
    flags=re.DOTALL
)

main_code = re.sub(
    r"response = client_reserva\.chat\.completions\.create\((.*?)\)",
    r"response = await asyncio.to_thread(client_reserva.chat.completions.create, \1)",
    main_code,
    flags=re.DOTALL
)

main_code = re.sub(
    r"segunda_response = client_reserva\.chat\.completions\.create\((.*?)\)",
    r"segunda_response = await asyncio.to_thread(client_reserva.chat.completions.create, \1)",
    main_code,
    flags=re.DOTALL
)

main_code = re.sub(
    r"segunda_response = client_principal\.chat\.completions\.create\((.*?)\)",
    r"segunda_response = await asyncio.to_thread(client_principal.chat.completions.create, \1)",
    main_code,
    flags=re.DOTALL
)

main_code = main_code.replace(
    "resultado = controlar_playback(accion, busqueda)",
    "resultado = await asyncio.to_thread(controlar_playback, accion, busqueda)"
)
main_code = main_code.replace(
    "resultado = buscar_internet(consulta)",
    "resultado = await asyncio.to_thread(buscar_internet, consulta)"
)
main_code = main_code.replace(
    "img_base64 = ver_pantalla()",
    "img_base64 = await asyncio.to_thread(ver_pantalla)"
)
main_code = main_code.replace(
    "resultado = hacer_clic_visual(descripcion, esperar)",
    "resultado = await asyncio.to_thread(hacer_clic_visual, descripcion, esperar)"
)
main_code = main_code.replace(
    "resultado = hacer_clic_fondo(descripcion, ventana, esperar)",
    "resultado = await asyncio.to_thread(hacer_clic_fondo, descripcion, ventana, esperar)"
)

with open(main_path, "w", encoding="utf-8") as f:
    f.write(main_code)


with open(tts_path, "r", encoding="utf-8") as f:
    tts_code = f.read()

# Replace edge-tts blocking code
edge_tts_target = """    try:
        # Ejecutar en un hilo separado para evitar conflictos con el event loop activo de FastAPI
        t = threading.Thread(target=lambda: asyncio.run(generar()))
        t.start()
        t.join()
        
        print("[TTS] 📢 Usando voz de Microsoft (Edge-TTS)")
        _reproducir_audio(archivo_temp)
    except Exception as e:"""

edge_tts_repl = """    def run_tts():
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
    except Exception as e:"""

tts_code = tts_code.replace(edge_tts_target, edge_tts_repl)

# Replace ElevenLabs blocking code
eleven_target = """        print("[TTS] 🎙️ Usando voz premium (ElevenLabs)")
        _reproducir_audio(archivo_temp)
        
        # Limpiar (puede fallar si playsound no soltó el archivo, pero el SO lo borrará después)
        try:
            os.remove(archivo_temp)
        except:
            pass
            
        return True"""

eleven_repl = """        def run_audio():
            print("[TTS] 🎙️ Usando voz premium (ElevenLabs)")
            _reproducir_audio(archivo_temp)
            try:
                os.remove(archivo_temp)
            except:
                pass

        import threading
        t = threading.Thread(target=run_audio)
        t.start()
        return True"""

tts_code = tts_code.replace(eleven_target, eleven_repl)

with open(tts_path, "w", encoding="utf-8") as f:
    f.write(tts_code)

print("Modificaciones realizadas con exito.")
