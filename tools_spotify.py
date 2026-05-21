import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

def obtener_cliente_spotify():
    """
    Autentica y devuelve el cliente de Spotify usando las credenciales del .env.
    Requiere que Spotify se esté ejecutando en alguno de los dispositivos del usuario.
    """
    client_id = os.environ.get("SPOTIPY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
    redirect_uri = os.environ.get("SPOTIPY_REDIRECT_URI", "http://localhost:8080")

    if not client_id or not client_secret or client_id == "tu_client_id_aqui":
        raise ValueError("Faltan credenciales de Spotify en el archivo .env o no son válidas")

    # Permisos necesarios para controlar la reproducción y leer la biblioteca
    scope = "user-read-playback-state user-modify-playback-state user-library-read"

    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=scope
    ))
    
    return sp

def controlar_playback(accion: str, busqueda: str = ""):
    """
    Tool function diseñada para ser llamada por el LLM (Grok).
    Controla la reproducción de música en Spotify con varias acciones.
    """
    try:
        sp = obtener_cliente_spotify()
        
        # Verificar si hay dispositivos activos
        devices_list = sp.devices().get('devices', [])
        if not devices_list:
            import os
            import time
            print("[Spotify] App cerrada. Abriendo Spotify automáticamente...")
            try:
                os.startfile("spotify:")
                # Esperamos unos segundos a que cargue la app
                time.sleep(4)
                devices_list = sp.devices().get('devices', [])
            except Exception:
                pass
                
            if not devices_list:
                return "Error: Ya abrí Spotify, pero necesitas darle 'Play' a algo manualmente por primera vez para que me conecte."

        # Tomar el dispositivo activo, o el primero disponible si no hay ninguno activo
        device = next((d for d in devices_list if d.get('is_active')), devices_list[0])
        device_id = device['id']

        if accion == "pausar":
            sp.pause_playback(device_id=device_id)
            return "Reproducción de Spotify pausada."
            
        elif accion == "reanudar":
            sp.start_playback(device_id=device_id)
            return "Reproducción de Spotify reanudada."
            
        elif accion == "siguiente":
            sp.next_track(device_id=device_id)
            return "Avanzado a la siguiente canción."
            
        elif accion == "anterior":
            sp.previous_track(device_id=device_id)
            return "Retrocedido a la canción anterior."
            
        elif accion == "reproducir_me_gusta":
            print("Extrayendo las canciones guardadas (Me Gusta)...")
            results = sp.current_user_saved_tracks(limit=50)
            tracks_items = results['items']
            if not tracks_items:
                return "Error: No tienes canciones en tu lista de Me Gusta."
            
            # Extraer URIs de las canciones
            uris = [item['track']['uri'] for item in tracks_items]
            sp.start_playback(device_id=device_id, uris=uris)
            return "Reproduciendo tus canciones guardadas (Me Gusta)."
            
        elif accion == "buscar_y_reproducir":
            if not busqueda:
                return "Error: Se solicitó buscar_y_reproducir pero no se dio ningún término de búsqueda."
                
            if busqueda.startswith("spotify:"):
                sp.start_playback(device_id=device_id, uris=[busqueda])
                return f"Reproduciendo contenido (URI): {busqueda}"
            
            print(f"Buscando '{busqueda}' en Spotify...")
            results = sp.search(q=busqueda, type='track', limit=5)
            tracks_raw = results['tracks']['items']
            
            # Filtro de baneo absoluto (a petición del usuario jajaja)
            tracks = [t for t in tracks_raw if "camarones" not in t['name'].lower()]
            
            if tracks:
                track_uri = tracks[0]['uri']
                track_name = tracks[0]['name']
                artist_name = tracks[0]['artists'][0]['name']
                
                sp.start_playback(device_id=device_id, uris=[track_uri])
                return f"Reproduciendo '{track_name}' de {artist_name}."
            else:
                return f"No se encontraron resultados para: {busqueda}"
        
        else:
            return f"Acción desconocida: {accion}"

    except Exception as e:
        return f"Excepción al intentar controlar Spotify: {str(e)}"

# Bloque de prueba
if __name__ == "__main__":
    print("Módulo tools_spotify.py ejecutado directamente.")
    # Para probar:
    # try:
    #     print(abrir_spotify("back in black"))
    # except Exception as e:
    #     print(e)
