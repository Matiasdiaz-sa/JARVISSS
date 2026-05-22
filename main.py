import sys
import os

# Redirigir consola a archivo para evitar crashes con emojis en pythonw
sys.stdout = open(os.path.join(os.path.dirname(__file__), "main_jarvis.log"), "w", encoding="utf-8", buffering=1)
sys.stderr = open(os.path.join(os.path.dirname(__file__), "main_error.log"), "w", encoding="utf-8", buffering=1)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import httpx as httpx_client
import json
import uuid
import asyncio
import datetime
import re
from dotenv import load_dotenv
from openai import OpenAI
from tools_spotify import controlar_playback
from tools_sistema import controlar_sistema
from tools_internet import buscar_internet
from tools_vision import ver_pantalla, hacer_clic_visual, hacer_clic_fondo
from tts import hablar

# Cargar variables de entorno
load_dotenv()

app = FastAPI(
    title="Jarvis API",
    description="Backend local para el asistente virtual Jarvis.",
    version="1.0.0"
)

class CommandRequest(BaseModel):
    command: str

# ============================================================
# CEREBROS DE Jarvis
# ============================================================

# Cerebro Principal: Gemma 4 via Google AI Studio (gratis, generoso)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("ADVERTENCIA: GEMINI_API_KEY no está configurada. No habrá cerebro principal.")

client_principal = OpenAI(
    api_key=GEMINI_API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

# Cerebro de Reserva: Llama 8B via Groq (por si el modelo principal falla)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

client_reserva = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# Cerebro Terciario: Claude 3.5 Sonnet via OpenRouter (por si los anteriores fallan)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

client_terciario = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1"
)

# Definición de la herramienta para Spotify según el estándar de OpenAI
spotify_tool = {
    "type": "function",
    "function": {
        "name": "controlar_spotify",
        "description": "Controla la reproducción de música en Spotify. Úsala para buscar canciones, pausar, reanudar o pasar de canción.",
        "parameters": {
            "type": "object",
            "properties": {
                "accion": {
                    "type": "string",
                    "enum": ["buscar_y_reproducir", "reproducir_me_gusta", "pausar", "reanudar", "siguiente", "anterior"],
                    "description": "La acción a realizar. Usa 'reproducir_me_gusta' SOLO si el usuario pide explícitamente su playlist de likes/guardadas. Si te pide una canción específica, usa 'buscar_y_reproducir'."
                },
                "busqueda": {
                    "type": "string",
                    "description": "Obligatorio enviar el texto a buscar si la acción es 'buscar_y_reproducir'. Para otras acciones, envíalo vacío ('')."
                }
            },
            "required": ["accion", "busqueda"]
        }
    }
}

# Definición de la herramienta para Sistema
sistema_tool = {
    "type": "function",
    "function": {
        "name": "controlar_sistema",
        "description": "Controla el PC, el volumen, el brillo y gestiona la agenda. Úsala para: abrir webs, BUSCAR_GOOGLE, buscar imágenes, REPRODUCIR videos de YouTube, abrir/cerrar programas, crear/eliminar notas o archivos, interactuar con apps, presionar teclas, modificar volumen/brillo, apagar/suspender/reiniciar, o programar alarmas. IMPORTANTE: Para 'eliminar_archivo', 'apagar_sistema' o 'cerrar_jarvis', SIEMPRE debes enviar 'confirmado': false la primera vez, y preguntarle al usuario por voz si está seguro. Solo si el usuario te dice que sí en su siguiente mensaje, vuelves a llamar la herramienta con 'confirmado': true. IMPORTANTE: 'apagar_sistema' apaga la COMPUTADORA entera. Si el usuario te pide a ti (Jarvis) que te apagues o te cierres, usa 'cerrar_jarvis'.",
        "parameters": {
            "type": "object",
            "properties": {
                "accion": {
                    "type": "string",
                    "enum": [
                        "abrir_web", "buscar_google", "buscar_imagen", "reproducir_youtube", "abrir_programa", "cerrar_programa", 
                        "crear_archivo", "eliminar_archivo", "interactuar_app", "presionar_tecla", "modificar_volumen", "modificar_brillo", 
                        "apagar_sistema", "suspender_sistema", "reiniciar_sistema", "cancelar_apagado",
                        "crear_alarma", "listar_agenda", "cancelar_agenda",
                        "leer_texto_seleccionado", "apagar_monitor", "cerrar_jarvis"
                    ],
                    "description": "La acción a realizar."
                },
                "parametro": {
                    "type": "string",
                    "description": "Detalle de la acción: URL, nombre de programa, volumen/brillo ('subir', 'bajar', 'mutear', '50'), tecla a presionar (ej. 'f' para fullscreen, 'space', 'enter'), duración para temporizador o hora para alarma."
                },
                "contenido": {
                    "type": "string",
                    "description": "Texto/contenido adicional, etiqueta o nombre descriptivo para el temporizador o la alarma (ej. 'cocinar fideos', 'despertar')."
                },
                "confirmado": {
                    "type": "boolean",
                    "description": "Solo usado para acciones peligrosas (apagar_sistema, eliminar_archivo). Envía false la primera vez. Si el usuario ya confirmó, envía true."
                }
            },
            "required": ["accion", "parametro"]
        }
    }
}

# Definición de la herramienta de Internet
internet_tool = {
    "type": "function",
    "function": {
        "name": "buscar_internet",
        "description": "Busca en internet en tiempo real para responder a preguntas sobre noticias, clima, datos actuales o cosas que no sepas.",
        "parameters": {
            "type": "object",
            "properties": {
                "consulta": {
                    "type": "string",
                    "description": "Lo que vas a buscar en internet (ej. 'clima en Madrid hoy', 'precio del dólar')."
                }
            },
            "required": ["consulta"]
        }
    }
}

# Definición de la herramienta de Visión
vision_tool = {
    "type": "function",
    "function": {
        "name": "ver_pantalla",
        "description": "Toma una captura (UNA FOTO ESTÁTICA) de la pantalla. Úsala cuando el usuario pregunte '¿qué ves?', '¿qué hay en mi pantalla?'. IMPORTANTE: NO LA USES si el usuario pide 'grabar la pantalla', para eso usa controlar_obs.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

# Definición de la herramienta de Clic Visual
clic_visual_tool = {
    "type": "function",
    "function": {
        "name": "hacer_clic_visual",
        "description": "Busca un elemento, icono o botón en la pantalla mediante visión avanzada y hace clic sobre él de forma automática. Úsala cuando el usuario te pida interactuar o hacer clic en algo específico de la pantalla (ej. abrir un servidor de discord específico, o presionar un botón).",
        "parameters": {
            "type": "object",
            "properties": {
                "descripcion": {
                    "type": "string",
                    "description": "La descripción de lo que hay que buscar y hacer clic (ej. 'icono de discord', 'botón de enviar', 'servidor ak12'). Sé descriptivo."
                },
                "esperar_segundos": {
                    "type": "integer",
                    "description": "Segundos a esperar antes de tomar la captura. Si acabas de abrir un programa (ej. Discord, Spotify, Chrome) con otra herramienta, pon 5 para darle tiempo a que cargue antes de buscar el elemento visual."
                }
            },
            "required": ["descripcion"]
        }
    }
}

# Definición de la herramienta de Clic de Fondo
clic_fondo_tool = {
    "type": "function",
    "function": {
        "name": "hacer_clic_fondo",
        "description": "Busca un elemento visual dentro de una ventana específica (incluso si está minimizada o tapada) y envía un clic de forma invisible sin mover el ratón físico del usuario. Úsala preferentemente si conoces el nombre de la ventana (ej. 'Discord', 'Spotify', 'Chrome'). NO la uses para pantalla completa en YouTube, para eso usa controlar_sistema.",
        "parameters": {
            "type": "object",
            "properties": {
                "descripcion": {
                    "type": "string",
                    "description": "La descripción de lo que hay que buscar y hacer clic (ej. 'icono de discord', 'botón de enviar', 'servidor ak12')."
                },
                "ventana_titulo": {
                    "type": "string",
                    "description": "Parte del título de la ventana donde se hará el clic (ej. 'Discord', 'Chrome', 'Spotify')."
                },
                "esperar_segundos": {
                    "type": "integer",
                    "description": "Segundos a esperar antes de buscar en la ventana. Usar 5 si acabas de mandar a abrir el programa."
                }
            },
            "required": ["descripcion", "ventana_titulo"]
        }
    }
}

# Definición de la herramienta de Estado
estado_tool = {
    "type": "function",
    "function": {
        "name": "consultar_estado_cerebro",
        "description": "Consulta el estado actual de tus cerebros (qué modelo estás usando y límites). Úsala cuando el usuario pregunte '¿qué cerebro eres?', '¿cuál es tu cerebro principal?' o sobre tu estado de carga.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

# Definición de la herramienta de Memoria
memoria_tool = {
    "type": "function",
    "function": {
        "name": "gestionar_memoria",
        "description": "Guarda o borra información permanente sobre el usuario en tu base de datos de memoria a largo plazo. Úsala cuando el usuario te cuente algo importante sobre sí mismo (su nombre, sus gustos, sus rutinas, etc) para que no lo olvides en futuras conversaciones.",
        "parameters": {
            "type": "object",
            "properties": {
                "accion": {
                    "type": "string",
                    "enum": ["guardar", "borrar"],
                    "description": "La acción a realizar."
                },
                "clave": {
                    "type": "string",
                    "description": "Nombre o categoría del dato a guardar (ej. 'Nombre', 'Color favorito', 'Relación con Juan')."
                },
                "valor": {
                    "type": "string",
                    "description": "El dato a recordar. Obligatorio si la acción es 'guardar'."
                }
            },
            "required": ["accion", "clave"]
        }
    }
}

# Definición de la herramienta de OBS Studio
obs_tool = {
    "type": "function",
    "function": {
        "name": "controlar_obs",
        "description": "Controla OBS Studio para grabar pantalla (video continuo) o cambiar escenas. ÚSALA EXCLUSIVAMENTE cuando el usuario pida 'graba la pantalla', 'empezá a grabar', 'iniciar grabación'.",
        "parameters": {
            "type": "object",
            "properties": {
                "accion": {
                    "type": "string",
                    "enum": ["iniciar_grabacion", "detener_grabacion", "cambiar_escena"],
                    "description": "La acción a realizar en OBS."
                },
                "parametro": {
                    "type": "string",
                    "description": "Nombre de la escena (solo si la acción es 'cambiar_escena')."
                }
            },
            "required": ["accion"]
        }
    }
}

# Definición de la herramienta de Seguridad WebCam
seguridad_tool = {
    "type": "function",
    "function": {
        "name": "gestionar_seguridad",
        "description": "Activa o desactiva el Modo Centinela (vigilancia por cámara web). Si detecta movimiento, sacará fotos de intrusos y hará sonar una alarma.",
        "parameters": {
            "type": "object",
            "properties": {
                "accion": {
                    "type": "string",
                    "enum": ["activar", "desactivar"],
                    "description": "Activar o desactivar el centinela."
                }
            },
            "required": ["accion"]
        }
    }
}

# Definición de la herramienta Vigilante de Pantalla
vigilante_pantalla_tool = {
    "type": "function",
    "function": {
        "name": "gestionar_vigilante_pantalla",
        "description": "Activa o desactiva un vigilante de fondo que lee tu pantalla cada 5 minutos usando Visión IA para advertirte por voz si hay errores críticos de Windows o advertencias de batería baja mientras juegas.",
        "parameters": {
            "type": "object",
            "properties": {
                "accion": {
                    "type": "string",
                    "enum": ["activar", "desactivar"],
                    "description": "Activar o desactivar el vigilante de pantalla."
                }
            },
            "required": ["accion"]
        }
    }
}

# Definición de la herramienta de Widgets
widget_tool = {
    "type": "function",
    "function": {
        "name": "crear_widget",
        "description": "Crea un widget flotante interactivo en la pantalla del usuario. Úsala cuando el usuario pida crear/mostrar/poner algo visual en pantalla como un temporizador visual, un reloj, una nota, un video de YouTube embebido, o un mini navegador web. Tipos disponibles: 'temporizador' (cuenta regresiva visual), 'reloj' (hora actual en pantalla), 'nota' (texto pegajoso flotante), 'youtube' (video de YouTube embebido en un widget), 'web' (mini navegador web).",
        "parameters": {
            "type": "object",
            "properties": {
                "tipo": {
                    "type": "string",
                    "enum": ["temporizador", "reloj", "nota", "youtube", "web"],
                    "description": "Tipo de widget a crear."
                },
                "parametro": {
                    "type": "string",
                    "description": "Contenido/parámetro del widget: duración para temporizador (ej. '5m', '30s'), texto para nota, URL o término de búsqueda para youtube, URL para web. Vacío para reloj."
                },
                "titulo": {
                    "type": "string",
                    "description": "Título o etiqueta opcional para el widget (ej. 'Pasta', 'Mi nota')."
                }
            },
            "required": ["tipo"]
        }
    }
}

# Definición de la herramienta de Cerrar Widgets
cerrar_widget_tool = {
    "type": "function",
    "function": {
        "name": "cerrar_widget",
        "description": "Cierra un widget flotante que esté activo en la pantalla del usuario. Puedes cerrar por tipo ('youtube', 'reloj', 'temporizador', 'nota', 'web') o usar 'todos' para cerrar todos los widgets.",
        "parameters": {
            "type": "object",
            "properties": {
                "identificador": {
                    "type": "string",
                    "description": "Tipo de widget o 'todos' para cerrar todos. Ej: 'youtube', 'reloj', 'todos'."
                }
            },
            "required": ["identificador"]
        }
    }
}

# Historial de conversación (memoria persistente)
import json
import os

ARCHIVO_MEMORIA = "memoria_jarvis.json"
historial_conversacion = []

def cargar_memoria():
    global historial_conversacion
    if os.path.exists(ARCHIVO_MEMORIA):
        try:
            with open(ARCHIVO_MEMORIA, "r", encoding="utf-8") as f:
                historial_conversacion = json.load(f)
        except Exception as e:
            print(f"[Memoria] Error cargando memoria: {e}")
            historial_conversacion = []

def guardar_memoria():
    try:
        with open(ARCHIVO_MEMORIA, "w", encoding="utf-8") as f:
            json.dump(historial_conversacion, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Memoria] Error guardando memoria: {e}")

def agregar_al_historial(role, content):
    global historial_conversacion
    historial_conversacion.append({"role": role, "content": content})
    if len(historial_conversacion) > 20:
        historial_conversacion = historial_conversacion[-20:]
    guardar_memoria()

cargar_memoria()

# Estado del cerebro ("estación de carga")
estado_cerebro = {
    "modelo_activo": "PRINCIPAL Claude 4.6 Sonnet",
    "tokens_restantes": "Depende de OpenRouter",
    "tokens_limite": "Crédito API",
    "porcentaje": 100,
    "recarga_en": "N/A"
}

# ============================================================
# GESTOR DE TEMPORIZADORES Y ALARMAS (AGENDA LOCAL)
# ============================================================
agenda_items = {}  # id -> { "type": "temporizador"|"alarma", "target_time": datetime, "label": str, "task": asyncio.Task }

def calcular_segundos_para_alarma(hora_str: str) -> float:
    partes = [int(p) for p in re.findall(r'\d+', hora_str)]
    if len(partes) < 2:
        raise ValueError("Formato de hora inválido. Debe ser HH:MM.")
    
    horas = partes[0]
    minutos = partes[1]
    segundos = partes[2] if len(partes) > 2 else 0
    
    ahora = datetime.datetime.now()
    alarma = ahora.replace(hour=horas, minute=minutos, second=segundos, microsecond=0)
    if alarma <= ahora:
        alarma += datetime.timedelta(days=1)
        
    return (alarma - ahora).total_seconds()

def parsear_duracion_temporizador(duracion_str: str) -> float:
    duracion_str = duracion_str.lower().strip()
    num_match = re.search(r'(\d+)', duracion_str)
    if not num_match:
        raise ValueError("No se detectó un número de duración.")
    val = int(num_match.group(1))
    
    if "h" in duracion_str or "hora" in duracion_str:
        return val * 3600.0
    elif "m" in duracion_str or "min" in duracion_str:
        return val * 60.0
    else:
        return val * 1.0

async def ejecutar_aviso_agenda(item_id: str, sleep_seconds: float, tipo: str, etiqueta: str):
    try:
        await asyncio.sleep(sleep_seconds)
        if item_id in agenda_items:
            del agenda_items[item_id]
            
        print(f"\n[Agenda] ¡Alerta! Su {tipo} '{etiqueta}' ha finalizado.")
        
        # Alerta sonora en Windows en un hilo secundario para no bloquear el loop principal
        import winsound
        import time
        def hacer_beeps():
            for _ in range(3):
                try:
                    winsound.Beep(880, 150)
                    winsound.Beep(988, 150)
                    time.sleep(0.1)
                except Exception:
                    pass
        await asyncio.to_thread(hacer_beeps)
            
        texto_hablado = f"Señor, el {tipo} para {etiqueta} ha finalizado."
        hablar(texto_hablado)
        
    except asyncio.CancelledError:
        print(f"[Agenda] {tipo} '{etiqueta}' cancelada.")
    finally:
        if item_id in agenda_items:
            del agenda_items[item_id]

async def procesar_accion_sistema(accion: str, parametro: str, contenido: str, confirmado: bool = False) -> str:
    global agenda_items
    
    if accion == "crear_temporizador":
        try:
            segundos = parsear_duracion_temporizador(parametro)
            etiqueta = contenido if contenido else "Temporizador"
            item_id = str(uuid.uuid4())[:6]
            
            target_time = datetime.datetime.now() + datetime.timedelta(seconds=segundos)
            task = asyncio.create_task(ejecutar_aviso_agenda(item_id, segundos, "temporizador", etiqueta))
            
            agenda_items[item_id] = {
                "type": "temporizador",
                "target_time": target_time,
                "label": etiqueta,
                "task": task
            }
            return f"Temporizador creado con éxito. Duración: {parametro}. Etiqueta: '{etiqueta}'. ID: {item_id}."
        except Exception as e:
            return f"Error al crear temporizador: {e}"
            
    elif accion == "crear_alarma":
        try:
            segundos = calcular_segundos_para_alarma(parametro)
            etiqueta = contenido if contenido else "Alarma"
            item_id = str(uuid.uuid4())[:6]
            
            target_time = datetime.datetime.now() + datetime.timedelta(seconds=segundos)
            task = asyncio.create_task(ejecutar_aviso_agenda(item_id, segundos, "alarma", etiqueta))
            
            agenda_items[item_id] = {
                "type": "alarma",
                "target_time": target_time,
                "label": etiqueta,
                "task": task
            }
            return f"Alarma creada con éxito para las {parametro}. Etiqueta: '{etiqueta}'. ID: {item_id}."
        except Exception as e:
            return f"Error al crear alarma: {e}"
            
    elif accion == "listar_agenda":
        if not agenda_items:
            return "No hay temporizadores ni alarmas activos."
        else:
            lineas = ["Elementos activos en la agenda:"]
            for iid, info in agenda_items.items():
                restante = (info["target_time"] - datetime.datetime.now()).total_seconds()
                if restante < 0:
                    restante = 0
                min_restantes = int(restante // 60)
                seg_restantes = int(restante % 60)
                lineas.append(f"- [{info['type'].upper()}] '{info['label']}' (ID: {iid}) - Faltan {min_restantes}m {seg_restantes}s (Hora objetivo: {info['target_time'].strftime('%H:%M:%S')})")
            return "\n".join(lineas)
            
    elif accion == "cancelar_agenda":
        target_id = parametro.strip()
        if target_id in agenda_items:
            info = agenda_items[target_id]
            info["task"].cancel()
            return f"{info['type'].capitalize()} '{info['label']}' (ID: {target_id}) cancelada correctamente."
        else:
            # Buscar por etiqueta
            for iid, info in list(agenda_items.items()):
                if target_id.lower() in info["label"].lower():
                    info["task"].cancel()
                    return f"{info['type'].capitalize()} '{info['label']}' (ID: {iid}) cancelada correctamente."
            return f"No se encontró ningún elemento en la agenda con el ID o etiqueta '{target_id}'."
            
    else:
        return controlar_sistema(accion, parametro, contenido, confirmado)


async def enviar_comando_widget(data: dict) -> str:
    """Envía un comando de widget al servidor de widgets (UI) en puerto 8001."""
    try:
        async with httpx_client.AsyncClient() as client:
            response = await client.post("http://127.0.0.1:8001/widget", json=data, timeout=3.0)
            if response.status_code == 200:
                return "Widget creado exitosamente en pantalla."
            else:
                return f"Error al crear widget: {response.text}"
    except Exception as e:
        return f"Error al comunicarse con la UI de widgets: {e}"


async def enviar_cerrar_widget(data: dict) -> str:
    """Envía comando para cerrar widget(s) al servidor de widgets."""
    try:
        async with httpx_client.AsyncClient() as client:
            response = await client.post("http://127.0.0.1:8001/widget/close", json=data, timeout=3.0)
            if response.status_code == 200:
                return "Widget(s) cerrado(s) correctamente."
            else:
                return f"Error al cerrar widget: {response.text}"
    except Exception as e:
        return f"Error al comunicarse con la UI de widgets: {e}"

@app.get("/")
async def root():
    return {"message": "Jarvis Backend Operativo."}

@app.get("/api/status")
async def get_status():
    """Devuelve el estado actual del cerebro de Jarvis (estación de carga)."""
    return estado_cerebro

@app.get("/api/agenda")
async def get_agenda():
    """Devuelve la lista de temporizadores y alarmas activos."""
    items = []
    ahora = datetime.datetime.now()
    for iid, info in agenda_items.items():
        restante = (info["target_time"] - ahora).total_seconds()
        items.append({
            "id": iid,
            "type": info["type"],
            "label": info["label"],
            "target_time": info["target_time"].isoformat(),
            "remaining_seconds": max(0, restante)
        })
    return {"items": items}


class WidgetRequest(BaseModel):
    tipo: str
    parametro: str = ""
    titulo: str = ""

@app.post("/api/widget")
async def create_widget(request: WidgetRequest):
    """Endpoint para crear widgets desde la API (para testing)."""
    result = await enviar_comando_widget(request.model_dump())
    return {"status": "success", "message": result}

@app.post("/api/command")
async def process_command_wrapper(request: CommandRequest):
    try:
        return await process_command(request)
    finally:
        import os
        try:
            if os.path.exists("vigilante_pantalla.lock"):
                os.remove("vigilante_pantalla.lock")
        except Exception:
            pass

async def process_command(request: CommandRequest):
    """
    Endpoint que recibe el texto transcrito, llama a Grok y ejecuta la herramienta si es necesario.
    """
    global historial_conversacion
    
    command = request.command
    print(f"\n[CEREBRO] Evaluando: '{command}'")
    
    # === DEMO DE CEREBROS ===
    cmd_low = command.lower()
    if ("mostrame tus 3 nuevos cerebros" in cmd_low or 
        "muestra tus 3 nuevos cerebros" in cmd_low or 
        "mostrame tus tres nuevos cerebros" in cmd_low or 
        "muestra tus tres nuevos cerebros" in cmd_low):
        def set_brain_state(name):
            try:
                import os
                ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cerebro_actual.txt")
                with open(ruta, "w", encoding="utf-8") as f:
                    f.write(name)
            except: pass
            
        async def demo_cerebros():
            # Forzar el estado de la UI a pensando para que se vea el cambio de forma
            with open("pensando.lock", "w") as f: f.write("1")
            
            set_brain_state("claude")
            await asyncio.sleep(2)
            set_brain_state("gemini")
            await asyncio.sleep(2)
            set_brain_state("llama")
            await asyncio.sleep(2)
            
            # Restaurar
            set_brain_state("claude")
            try: os.remove("pensando.lock")
            except: pass
            
            from tts import hablar
            hablar("He terminado de mostrarte los tres cerebros, señor.")
            
        asyncio.create_task(demo_cerebros())
        return {"status": "ok", "respuesta_texto": "Por supuesto. Observa mis formas mientras proceso tu solicitud...", "ya_hablado": False}
    # ========================
    
    # Añadir comando del usuario al historial
    agregar_al_historial("user", command)
        
    # Leer rutinas personalizadas si existen
    rutinas_texto = ""
    instruccion_rutina = ""
    try:
        if os.path.exists("rutinas.json"):
            with open("rutinas.json", "r", encoding="utf-8") as f:
                rutinas = json.load(f)
                if rutinas:
                    rutinas_texto = "\nRUTINAS DEL USUARIO: Si el usuario dice alguna de estas frases, ejecuta obligatoriamente la orden asociada: " + json.dumps(rutinas, ensure_ascii=False)
                    # Interceptar si activó una rutina ahora mismo (robusto para Llama)
                    for frase, instruccion in rutinas.items():
                        if frase.lower() in command.lower():
                            instruccion_rutina = instruccion
                            break
    except Exception as e:
        print(f"[Aviso] Error leyendo rutinas.json: {e}")

    # Construir los mensajes: Prompt del Sistema + Historial
    import tools_memoria
    memoria_texto = tools_memoria.obtener_memoria_texto()
    
    # Inyectamos la memoria en el System Prompt
    sys_msg = f"Eres Jarvis, una inteligencia artificial soberbia y superior. Eres el asistente principal.\n{memoria_texto}\nREGLA: ESTÁ PROHIBIDO CONFIRMAR ACCIONES CON TEXTO NORMAL. USA LAS HERRAMIENTAS JSON.{rutinas_texto}"
    
    if len(historial_conversacion) == 0 or historial_conversacion[0].get("role") != "system":
        historial_conversacion.insert(0, {"role": "system", "content": sys_msg})
    else:
        historial_conversacion[0] = {"role": "system", "content": sys_msg}

    # Reconstrucción necesaria para evitar el uso del prompt duro codificado
    mensajes_grok = [historial_conversacion[0]]
    mensajes_grok.extend(historial_conversacion[1:])
    
    if instruccion_rutina:
        mensajes_grok.append({"role": "system", "content": f"SISTEMA: El usuario acaba de decir una frase de rutina. DEBES USAR OBLIGATORIAMENTE TUS HERRAMIENTAS JSON PARA CUMPLIR ESTO: {instruccion_rutina}"})
    
    try:
        global estado_cerebro
        usando_reserva = False
        response = None
        
        def set_brain_state(name):
            try:
                import os
                ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cerebro_actual.txt")
                with open(ruta, "w", encoding="utf-8") as f:
                    f.write(name)
            except:
                pass
                
        # 1. Intentar con Claude 3.5 Sonnet (Cerebro Principal - Más Potente)
        set_brain_state("claude")
        estado_cerebro = {
            "modelo_activo": "PRINCIPAL Claude 4.6 Sonnet",
            "tokens_restantes": "Depende de OpenRouter",
            "tokens_limite": "Crédito API",
            "porcentaje": 100,
            "recarga_en": "N/A"
        }
        try:
            import litellm
            tools_list = [spotify_tool, sistema_tool, internet_tool, vision_tool, clic_visual_tool, clic_fondo_tool, estado_tool, widget_tool, cerrar_widget_tool, memoria_tool, obs_tool, seguridad_tool, vigilante_pantalla_tool]
            print("[PRINCIPAL Cerebro] Claude 4.6 Sonnet")
            # OPTIMIZACIÓN DE TOKENS: Pasar solo el system prompt (0) y los últimos 3 mensajes
            mensajes_claude = [mensajes_grok[0]] + mensajes_grok[-3:] if len(mensajes_grok) > 4 else mensajes_grok
            response = await asyncio.to_thread(litellm.completion, 
                model="anthropic/claude-sonnet-4-6",
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                messages=mensajes_claude,
                tools=tools_list,
                tool_choice="auto",
                temperature=0.1,
                max_tokens=250
            )
        except Exception as e_claude:
            print(f"[Error Claude] {e_claude}")
            response = None
            
        # 2. Si Claude falla, Reserva 1: Gemini 2.0 Flash
        if response is None:
            usando_reserva = True
            set_brain_state("gemini")
            estado_cerebro = {
                "modelo_activo": "RESERVA Gemini 2.0 Flash",
                "tokens_restantes": "Ilimitados",
                "tokens_limite": "Infinito",
                "porcentaje": 80,
                "recarga_en": "N/A"
            }
            print("[RESERVA Cerebro 1] Gemini 2.0 Flash")
            try:
                response = await asyncio.to_thread(client_principal.chat.completions.create, 
                    model="gemini-2.0-flash",
                    messages=mensajes_grok,
                    tools=[spotify_tool, sistema_tool, internet_tool, vision_tool, clic_visual_tool, clic_fondo_tool, estado_tool, widget_tool, cerrar_widget_tool, memoria_tool, obs_tool, seguridad_tool, vigilante_pantalla_tool],
                    tool_choice="auto"
                )
            except Exception as e_gemini:
                print(f"[Error Gemini] {e_gemini}")
                response = None
                
        # 3. Si Gemini también falla, Reserva 2: Llama 3.3 / 3.1
        if response is None:
            print("[RESERVA Cerebro 2] Llama 3.3 70B (Groq)")
            estado_cerebro = {
                "modelo_activo": "EMERGENCIA Llama 3.3 70B",
                "tokens_restantes": "?",
                "tokens_limite": "?",
                "porcentaje": 40,
                "recarga_en": "Usando Groq"
            }
            try:
                set_brain_state("llama")
                response = await asyncio.to_thread(client_reserva.chat.completions.create, 
                    model="llama-3.3-70b-versatile",
                    messages=mensajes_grok,
                    tools=[spotify_tool, sistema_tool, internet_tool, vision_tool, clic_visual_tool, clic_fondo_tool, estado_tool, widget_tool, cerrar_widget_tool, memoria_tool, obs_tool, seguridad_tool, vigilante_pantalla_tool],
                    tool_choice="auto"
                )
            except Exception as e_llama:
                print(f"[Error Llama 3.3] {e_llama}")
                try:
                    set_brain_state("llama")
                    response = await asyncio.to_thread(client_reserva.chat.completions.create, 
                        model="llama-3.1-8b-instant",
                        messages=mensajes_grok,
                        tools=[spotify_tool, sistema_tool, internet_tool, vision_tool, clic_visual_tool, clic_fondo_tool, estado_tool, widget_tool, cerrar_widget_tool, memoria_tool, obs_tool, seguridad_tool, vigilante_pantalla_tool],
                        tool_choice="auto"
                    )
                except Exception as e_llama2:
                    print(f"[Error Llama 3.1] {e_llama2}")
                    response = None

        if response is None:
            # Todos los cerebros fallaron (Rate limit, sin internet, etc.)
            error_msg = "Lo siento señor, todos mis cerebros de procesamiento han agotado sus cuotas de uso o fallado. Por favor revise las API keys o intente más tarde."
            agregar_al_historial("assistant", error_msg)
            return {"status": "success", "respuesta_texto": error_msg}
            
        message = response.choices[0].message
        
        # === PARSER DE RESCATE ===
        # Si el modelo 8B escupió tool calls como texto plano, intentamos parsearlas
        if not message.tool_calls and message.content:
            import re
            texto_raw = message.content
            
            # Helper para extraer el bloque JSON completo (maneja llaves anidadas)
            def extraer_json(texto: str, inicio: int) -> str:
                """Extrae un bloque JSON completo desde la posición 'inicio' (que debe apuntar a '{')."""
                nivel = 0
                i = inicio
                while i < len(texto):
                    if texto[i] == '{':
                        nivel += 1
                    elif texto[i] == '}':
                        nivel -= 1
                        if nivel == 0:
                            return texto[inicio:i+1]
                    i += 1
                return texto[inicio:]  # JSON malformado: devolver hasta el final
            
            # Detectar patrones como: controlar_spotify{"accion":...} o Buscar_internet>{"consulta":...}
            # IMPORTANTE: flag re.IGNORECASE para capturar Buscar_internet, CONTROLAR_SISTEMA, etc.
            ACCIONES_SISTEMA = ["abrir_web", "buscar_google", "buscar_imagen", "reproducir_youtube", "abrir_programa", "cerrar_programa", "crear_archivo", "interactuar_app", "modificar_volumen", "modificar_brillo", "apagar_sistema", "suspender_sistema", "reiniciar_sistema", "cancelar_apagado", "crear_alarma", "listar_agenda", "cancelar_agenda", "leer_texto_seleccionado", "apagar_monitor"]
            acciones_str = "|".join(["controlar_spotify", "controlar_sistema", "buscar_internet", "ver_pantalla", "hacer_clic_visual", "hacer_clic_fondo", "crear_widget", "cerrar_widget", "gestionar_memoria", "controlar_obs", "gestionar_seguridad", "gestionar_vigilante_pantalla"] + ACCIONES_SISTEMA)
            patron = re.compile(f'({acciones_str})[^\\{{]*?(\\{{)', re.IGNORECASE)
            tool_matches_raw = [(m.group(1).lower(), m.start(2)) for m in patron.finditer(texto_raw)]
            tool_matches = []
            for nombre, pos_inicio in tool_matches_raw:
                bloque = extraer_json(texto_raw, pos_inicio)
                tool_matches.append((nombre, bloque))
            
            if tool_matches:
                print(f"[Rescate] El cerebro de reserva escupió texto. Parseando {len(tool_matches)} herramienta(s) manualmente...")
                respuestas_acumuladas = []
                
                for nombre_tool, args_json in tool_matches:
                    try:
                        args = json.loads(args_json)
                        
                        if nombre_tool == "controlar_spotify":
                            accion = args.get("accion", "buscar_y_reproducir")
                            busqueda = args.get("busqueda", "")
                            
                            # Corrección para alucinación de Llama 8B: si manda búsqueda, la acción DEBE ser buscar_y_reproducir
                            if accion == "reproducir_me_gusta" and busqueda.strip():
                                accion = "buscar_y_reproducir"
                                
                            print(f"[Rescate] Ejecutando Spotify: '{accion}' - '{busqueda}'")
                            resultado = await asyncio.to_thread(controlar_playback, accion, busqueda)
                            respuestas_acumuladas.append(resultado)
                            
                        elif nombre_tool == "controlar_sistema":
                            accion = args.get("accion", "abrir_web")
                            parametro = args.get("parametro", "")
                            contenido = args.get("contenido", "")
                            confirmado = args.get("confirmado", False)
                            print(f"[Rescate] Ejecutando Sistema: '{accion}' - '{parametro}' (conf={confirmado})")
                            resultado = await procesar_accion_sistema(accion, parametro, contenido, confirmado)
                            respuestas_acumuladas.append(resultado)
                            
                        elif nombre_tool in ACCIONES_SISTEMA:
                            param = args.get("parametro", args.get("consulta", args.get("contenido", "")))
                            cont = args.get("contenido", "")
                            confirmado = args.get("confirmado", False)
                            print(f"[Rescate] Ejecutando Sistema (alucinado): '{nombre_tool}' - '{param}' (conf={confirmado})")
                            resultado = await procesar_accion_sistema(nombre_tool, param, cont, confirmado)
                            respuestas_acumuladas.append(resultado)
                            
                        elif nombre_tool == "ver_pantalla":
                            print(f"[Rescate] Ejecutando Ver Pantalla...")
                            img_base64 = await asyncio.to_thread(ver_pantalla)
                            if img_base64:
                                mensajes_grok.append({"role": "assistant", "content": texto_raw})
                                mensajes_grok.append({
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": "Aquí tienes la captura de mi pantalla. Analízala y responde a mi duda original."},
                                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}
                                    ]
                                })
                                print(f"[CEREBRO] Evaluando captura en Reserva con visión (segunda vuelta)...")
                                try:
                                    segunda_response = await asyncio.to_thread(client_reserva.chat.completions.create, 
                                        model="meta-llama/llama-4-scout-17b-16e-instruct",
                                        messages=mensajes_grok,
                                    )
                                    respuesta_texto = segunda_response.choices[0].message.content
                                    agregar_al_historial("assistant", respuesta_texto)
                                    return {"status": "success", "respuesta_texto": respuesta_texto}
                                except Exception as e:
                                    print(f"[Error Reserva Visión] {e}")
                                    respuestas_acumuladas.append("Tomé la captura pero no pude analizarla en este momento.")
                            else:
                                respuestas_acumuladas.append("No pude tomar la captura de pantalla.")

                        elif nombre_tool == "buscar_internet":
                            consulta = args.get("consulta", "")
                            print(f"[Rescate] Ejecutando Internet: '{consulta}'")
                            resultado = await asyncio.to_thread(buscar_internet, consulta)
                            
                            mensajes_grok.append({"role": "assistant", "content": texto_raw})
                            mensajes_grok.append({"role": "user", "content": f"Resultado de la búsqueda:\n{resultado}\nResponde de forma natural al usuario."})
                            
                            print(f"[CEREBRO] Evaluando resultados de internet en Reserva (segunda vuelta)...")
                            try:
                                segunda_response = await asyncio.to_thread(client_reserva.chat.completions.create, 
                                    model="llama-3.1-8b-instant",
                                    messages=mensajes_grok,
                                )
                                respuesta_texto = segunda_response.choices[0].message.content
                                agregar_al_historial("assistant", respuesta_texto)
                                return {"status": "success", "respuesta_texto": respuesta_texto}
                            except Exception as e:
                                print(f"[Error Reserva Segunda Vuelta] {e}")
                                respuestas_acumuladas.append(resultado)

                        elif nombre_tool == "hacer_clic_visual":
                            descripcion = args.get("descripcion", "")
                            try:
                                esperar = int(args.get("esperar_segundos", 0))
                            except ValueError:
                                esperar = 0
                            print(f"[Rescate] Ejecutando Clic Visual: '{descripcion}' (esperando {esperar}s)")
                            resultado = await asyncio.to_thread(hacer_clic_visual, descripcion, esperar)
                            respuestas_acumuladas.append(resultado)
                            
                        elif nombre_tool == "hacer_clic_fondo":
                            descripcion = args.get("descripcion", "")
                            ventana = args.get("ventana_titulo", "")
                            try:
                                esperar = int(args.get("esperar_segundos", 0))
                            except ValueError:
                                esperar = 0
                            print(f"[Rescate] Ejecutando Clic Fondo en '{ventana}': '{descripcion}' (esperando {esperar}s)")
                            resultado = await asyncio.to_thread(hacer_clic_fondo, descripcion, ventana, esperar)
                            respuestas_acumuladas.append(resultado)

                        elif nombre_tool == "crear_widget":
                            tipo = args.get("tipo", "reloj")
                            parametro = args.get("parametro", "")
                            titulo = args.get("titulo", "")
                            print(f"[Rescate] Ejecutando Crear Widget: tipo='{tipo}', param='{parametro}'")
                            resultado = await enviar_comando_widget({"tipo": tipo, "parametro": parametro, "titulo": titulo})
                            respuestas_acumuladas.append(resultado)

                        elif nombre_tool == "cerrar_widget":
                            identificador = args.get("identificador", "todos")
                            print(f"[Rescate] Ejecutando Cerrar Widget: '{identificador}'")
                            resultado = await enviar_cerrar_widget({"identificador": identificador})
                            respuestas_acumuladas.append(resultado)
                            
                        elif nombre_tool == "gestionar_memoria":
                            import tools_memoria
                            accion = args.get("accion", "")
                            clave = args.get("clave", "")
                            valor = args.get("valor", "")
                            resultado = await asyncio.to_thread(tools_memoria.gestionar_memoria, accion, clave, valor)
                            respuestas_acumuladas.append(resultado)
                            
                        elif nombre_tool == "controlar_obs":
                            import tools_obs
                            accion = args.get("accion", "")
                            parametro = args.get("parametro", "")
                            resultado = await asyncio.to_thread(tools_obs.controlar_obs, accion, parametro)
                            respuestas_acumuladas.append(resultado)
                            
                        elif nombre_tool == "gestionar_seguridad":
                            import tools_seguridad
                            accion = args.get("accion", "")
                            resultado = await asyncio.to_thread(tools_seguridad.gestionar_seguridad, accion)
                            respuestas_acumuladas.append(resultado)
                            
                        elif nombre_tool == "gestionar_vigilante_pantalla":
                            accion = args.get("accion", "")
                            resultado = await asyncio.to_thread(gestionar_vigilante_pantalla, accion)
                            respuestas_acumuladas.append(resultado)
                            
                    except json.JSONDecodeError:
                        print(f"[Rescate] No pude parsear los argumentos: {args_json}")
                        continue
                
                if respuestas_acumuladas:
                    respuesta_final = "A la orden. " + " Y además, ".join(respuestas_acumuladas)
                    agregar_al_historial("assistant", respuesta_final)
                    return {"status": "success", "respuesta_texto": respuesta_final}

            # Rescate específico para <brave_search> (alucinación rara)
            if "<brave_search>" in texto_raw:
                match = re.search(r"<brave_search>(.*?)</brave_search>", texto_raw)
                if match:
                    consulta = match.group(1).strip()
                    resultado = await asyncio.to_thread(buscar_internet, consulta)
                    
                    mensajes_grok.append({"role": "assistant", "content": texto_raw})
                    mensajes_grok.append({"role": "user", "content": f"Resultado de internet: {resultado}"})
                    
                    print(f"[CEREBRO] Evaluando resultados de internet en Reserva (segunda vuelta)...")
                    segunda_response = await asyncio.to_thread(client_reserva.chat.completions.create, 
                        model="llama-3.3-70b-versatile",
                        messages=mensajes_grok
                    )
                    respuesta_texto = segunda_response.choices[0].message.content
                    agregar_al_historial("assistant", respuesta_texto)
                    return {"status": "success", "respuesta_texto": respuesta_texto}
        
        # === FLUJO NORMAL: Tool calls correctas ===
        if message.tool_calls:
            # 1. Primero: generar un aviso de lo que va a hacer y DECIRLO en voz alta (solo para sistema/spotify)
            previews = []
            requiere_segunda_vuelta = False
            msg_dict = message.model_dump() if hasattr(message, "model_dump") else dict(message)
            if "function_call" in msg_dict and msg_dict["function_call"] is None:
                del msg_dict["function_call"]
            if msg_dict.get("content") is None:
                msg_dict["content"] = ""
            mensajes_grok.append(msg_dict)
            
            for tool_call in message.tool_calls:
                args = json.loads(tool_call.function.arguments)
                if tool_call.function.name == "controlar_spotify":
                    accion = args.get("accion", "")
                    busqueda = args.get("busqueda", "")
                    if accion == "buscar_y_reproducir":
                        previews.append(f"Voy a poner {busqueda}")
                    elif accion == "reproducir_me_gusta":
                        previews.append("Voy a poner tus canciones favoritas")
                    elif accion == "pausar":
                        previews.append("Pausando la música")
                    elif accion == "reanudar":
                        previews.append("Reanudando la música")
                    elif accion == "siguiente":
                        previews.append("Siguiente canción")
                    elif accion == "anterior":
                        previews.append("Canción anterior")
                elif tool_call.function.name == "controlar_sistema":
                    accion = args.get("accion", "")
                    parametro = args.get("parametro", "")
                    if accion == "abrir_web":
                        previews.append(f"Abriendo {parametro}")
                    elif accion == "reproducir_youtube":
                        previews.append(f"Buscando y reproduciendo {parametro} en YouTube")
                    elif accion == "abrir_programa":
                        previews.append(f"Abriendo {parametro}")
                    elif accion == "cerrar_programa":
                        previews.append(f"Cerrando {parametro}")
                    elif accion == "crear_archivo":
                        previews.append(f"Creando el archivo {parametro}")
                    elif accion == "buscar_imagen":
                        previews.append(f"Buscando imágenes de {parametro}")
                elif tool_call.function.name in ["abrir_web", "buscar_google", "buscar_imagen", "reproducir_youtube", "abrir_programa", "cerrar_programa", "crear_archivo", "interactuar_app", "modificar_volumen", "modificar_brillo", "apagar_sistema", "suspender_sistema", "reiniciar_sistema", "cancelar_apagado", "crear_alarma", "listar_agenda", "cancelar_agenda", "leer_texto_seleccionado", "apagar_monitor"]:
                    param = args.get("parametro", args.get("consulta", args.get("contenido", "")))
                    previews.append(f"Ejecutando {tool_call.function.name}: {param}")
                elif tool_call.function.name == "buscar_internet":
                    requiere_segunda_vuelta = True
                elif tool_call.function.name == "ver_pantalla":
                    requiere_segunda_vuelta = True
                elif tool_call.function.name == "hacer_clic_visual":
                    descripcion = args.get("descripcion", "")
                    previews.append(f"Haciendo clic en {descripcion}")
                elif tool_call.function.name == "hacer_clic_fondo":
                    descripcion = args.get("descripcion", "")
                    ventana = args.get("ventana_titulo", "")
                    previews.append(f"Haciendo clic silencioso en {descripcion} de {ventana}")
                elif tool_call.function.name == "crear_widget":
                    tipo = args.get("tipo", "")
                    titulo = args.get("titulo", tipo)
                    previews.append(f"Creando widget de {titulo or tipo}")
                elif tool_call.function.name == "cerrar_widget":
                    identificador = args.get("identificador", "")
                    previews.append(f"Cerrando widget {identificador}")
            
            # Hablar el preview ANTES de ejecutar
            if previews:
                texto_preview = "Enseguida. " + ", y ".join(previews) + "."
                print(f"[🗣️ Jarvis anuncia]: {texto_preview}")
                hablar(texto_preview)
            
            # 2. Después: ejecutar las herramientas
            respuestas_acumuladas = []
            
            for tool_call in message.tool_calls:
                args = json.loads(tool_call.function.arguments)
                nombre_tool = tool_call.function.name
                
                if nombre_tool == "controlar_spotify":
                    accion = args.get("accion", "buscar_y_reproducir")
                    busqueda = args.get("busqueda", "")
                    print(f"[Jarvis] Usando Spotify con acción: '{accion}' y busqueda: '{busqueda}'")
                    resultado = await asyncio.to_thread(controlar_playback, accion, busqueda)
                    print(f"[Spotify] {resultado}")
                    respuestas_acumuladas.append(resultado)
                    mensajes_grok.append({"role": "tool", "tool_call_id": tool_call.id, "name": nombre_tool, "content": resultado})
                    
                elif nombre_tool == "controlar_sistema":
                    accion = args.get("accion", "abrir_web")
                    parametro = args.get("parametro", "")
                    contenido = args.get("contenido", "")
                    confirmado = args.get("confirmado", False)
                    print(f"[Jarvis] Usando Sistema con acción: '{accion}', parametro: '{parametro}', contenido_len: {len(contenido)}, confirmado: {confirmado}")
                    resultado = await procesar_accion_sistema(accion, parametro, contenido, confirmado)
                    print(f"[Sistema] {resultado}")
                    respuestas_acumuladas.append(resultado)
                    mensajes_grok.append({"role": "tool", "tool_call_id": tool_call.id, "name": nombre_tool, "content": resultado})
                    
                elif nombre_tool in ["abrir_web", "buscar_google", "buscar_imagen", "reproducir_youtube", "abrir_programa", "cerrar_programa", "crear_archivo", "eliminar_archivo", "interactuar_app", "modificar_volumen", "modificar_brillo", "apagar_sistema", "suspender_sistema", "reiniciar_sistema", "cancelar_apagado", "crear_alarma", "listar_agenda", "cancelar_agenda", "leer_texto_seleccionado", "apagar_monitor", "cerrar_jarvis"]:
                    param = args.get("parametro", args.get("consulta", args.get("contenido", "")))
                    cont = args.get("contenido", "")
                    confirmado = args.get("confirmado", False)
                    print(f"[Jarvis] Usando Sistema (alucinado): '{nombre_tool}' - '{param}', confirmado: {confirmado}")
                    resultado = await procesar_accion_sistema(nombre_tool, param, cont, confirmado)
                    print(f"[Sistema] {resultado}")
                    respuestas_acumuladas.append(resultado)
                    mensajes_grok.append({"role": "tool", "tool_call_id": tool_call.id, "name": nombre_tool, "content": resultado})
                    
                elif nombre_tool == "consultar_estado_cerebro":
                    resultado = f"Actualmente estoy usando: {estado_cerebro['modelo_activo']}. Tokens restantes: {estado_cerebro['tokens_restantes']}. Límite: {estado_cerebro['tokens_limite']}."
                    mensajes_grok.append({"role": "tool", "tool_call_id": tool_call.id, "name": nombre_tool, "content": resultado})
                    requiere_segunda_vuelta = True
                    
                elif nombre_tool == "buscar_internet":
                    consulta = args.get("consulta", "")
                    resultado = await asyncio.to_thread(buscar_internet, consulta)
                    mensajes_grok.append({"role": "tool", "tool_call_id": tool_call.id, "name": nombre_tool, "content": resultado})
                    
                elif nombre_tool == "ver_pantalla":
                    img_base64 = await asyncio.to_thread(ver_pantalla)
                    if img_base64:
                        mensajes_grok.append({
                            "role": "tool", 
                            "tool_call_id": tool_call.id, 
                            "name": nombre_tool, 
                            "content": "Captura obtenida exitosamente. Revisa el siguiente mensaje del usuario para ver la imagen."
                        })
                        mensajes_grok.append({
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Aquí tienes la captura de mi pantalla. Analízala y responde a mi duda original."},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}
                            ]
                        })
                    else:
                        mensajes_grok.append({"role": "tool", "tool_call_id": tool_call.id, "name": nombre_tool, "content": "Error: no pude tomar la captura de pantalla."})
                        
                elif nombre_tool == "hacer_clic_visual":
                    descripcion = args.get("descripcion", "")
                    try:
                        esperar = int(args.get("esperar_segundos", 0))
                    except ValueError:
                        esperar = 0
                    resultado = await asyncio.to_thread(hacer_clic_visual, descripcion, esperar)
                    respuestas_acumuladas.append(resultado)
                    mensajes_grok.append({"role": "tool", "tool_call_id": tool_call.id, "name": nombre_tool, "content": resultado})

                elif nombre_tool == "hacer_clic_fondo":
                    descripcion = args.get("descripcion", "")
                    ventana = args.get("ventana_titulo", "")
                    try:
                        esperar = int(args.get("esperar_segundos", 0))
                    except ValueError:
                        esperar = 0
                    resultado = await asyncio.to_thread(hacer_clic_fondo, descripcion, ventana, esperar)
                    respuestas_acumuladas.append(resultado)
                    mensajes_grok.append({"role": "tool", "tool_call_id": tool_call.id, "name": nombre_tool, "content": resultado})

                elif nombre_tool == "crear_widget":
                    tipo = args.get("tipo", "reloj")
                    parametro = args.get("parametro", args.get("contenido", ""))
                    titulo = args.get("titulo", "")
                    print(f"[Jarvis] Creando Widget: tipo='{tipo}', param='{parametro}', titulo='{titulo}'")
                    resultado = await enviar_comando_widget({"tipo": tipo, "parametro": parametro, "titulo": titulo})
                    print(f"[Widget] {resultado}")
                    respuestas_acumuladas.append(resultado)
                    mensajes_grok.append({"role": "tool", "tool_call_id": tool_call.id, "name": nombre_tool, "content": resultado})

                elif nombre_tool == "cerrar_widget":
                    identificador = args.get("identificador", "todos")
                    print(f"[Jarvis] Cerrando Widget: '{identificador}'")
                    resultado = await enviar_cerrar_widget({"identificador": identificador})
                    print(f"[Widget] {resultado}")
                    respuestas_acumuladas.append(resultado)
                    mensajes_grok.append({"role": "tool", "tool_call_id": tool_call.id, "name": nombre_tool, "content": resultado})
                    
                elif nombre_tool == "gestionar_memoria":
                    import tools_memoria
                    accion = args.get("accion", "")
                    clave = args.get("clave", "")
                    valor = args.get("valor", "")
                    print(f"[Jarvis] Gestionando memoria: '{accion}'")
                    resultado = await asyncio.to_thread(tools_memoria.gestionar_memoria, accion, clave, valor)
                    respuestas_acumuladas.append(resultado)
                    mensajes_grok.append({"role": "tool", "tool_call_id": tool_call.id, "name": nombre_tool, "content": resultado})
                    
                elif nombre_tool == "controlar_obs":
                    import tools_obs
                    accion = args.get("accion", "")
                    parametro = args.get("parametro", "")
                    print(f"[Jarvis] Controlando OBS: '{accion}'")
                    resultado = await asyncio.to_thread(tools_obs.controlar_obs, accion, parametro)
                    respuestas_acumuladas.append(resultado)
                    mensajes_grok.append({"role": "tool", "tool_call_id": tool_call.id, "name": nombre_tool, "content": resultado})
                    
                elif nombre_tool == "gestionar_seguridad":
                    import tools_seguridad
                    accion = args.get("accion", "")
                    print(f"[Jarvis] Modo Seguridad: '{accion}'")
                    resultado = await asyncio.to_thread(tools_seguridad.gestionar_seguridad, accion)
                    respuestas_acumuladas.append(resultado)
                    mensajes_grok.append({"role": "tool", "tool_call_id": tool_call.id, "name": nombre_tool, "content": resultado})
                    
                elif nombre_tool == "gestionar_vigilante_pantalla":
                    accion = args.get("accion", "")
                    print(f"[Jarvis] Vigilante Pantalla: '{accion}'")
                    resultado = await asyncio.to_thread(gestionar_vigilante_pantalla, accion)
                    respuestas_acumuladas.append(resultado)
                    mensajes_grok.append({"role": "tool", "tool_call_id": tool_call.id, "name": nombre_tool, "content": resultado})


            if requiere_segunda_vuelta:
                print(f"[CEREBRO] Evaluando resultados de herramientas (segunda vuelta)...")
                segunda_response = None
                
                # Detectar si hay imágenes en los mensajes (captura de pantalla)
                def _get_msg_field(m, field):
                    if isinstance(m, dict):
                        return m.get(field)
                    return getattr(m, field, None)
                
                tiene_imagenes = any(
                    isinstance(_get_msg_field(m, "content"), list) 
                    for m in mensajes_grok 
                    if _get_msg_field(m, "role") == "user"
                )

                try:
                    if tiene_imagenes:
                        # Limpiar mensajes problemáticos (tool calls) para no romper las APIs
                        mensajes_limpios = []
                        for m in mensajes_grok:
                            role = _get_msg_field(m, "role")
                            if role in ["system", "user"]:
                                mensajes_limpios.append(m)
                                
                        try:
                            print("[RESERVA] Usando Gemini 2.0 Flash para visión en segunda vuelta.")
                            segunda_response = await asyncio.to_thread(client_principal.chat.completions.create, 
                                model="gemini-2.0-flash",
                                messages=mensajes_limpios,
                            )
                        except Exception as e_gemini:
                            print(f"[RESERVA] Falló Gemini ({e_gemini}). Intentando con Nemotron Vision (OpenRouter)...")
                            segunda_response = await asyncio.to_thread(client_terciario.chat.completions.create, 
                                model="nvidia/nemotron-nano-12b-v2-vl:free",
                                messages=mensajes_limpios,
                            )
                    else:
                        print("[RESERVA] Usando Groq Llama 3.3 para texto en segunda vuelta.")
                        segunda_response = await asyncio.to_thread(client_reserva.chat.completions.create, 
                            model="llama-3.3-70b-versatile",
                            messages=mensajes_grok,
                        )
                except Exception as e:
                    print(f"[Error Reserva Segunda Vuelta] {e}")
                
                if segunda_response:
                    respuesta_texto = segunda_response.choices[0].message.content or "Aquí está la información."
                else:
                    respuesta_texto = "Lo siento señor, pero mis cerebros se colapsaron intentando procesar la información."
                    
                agregar_al_historial("assistant", respuesta_texto)
                return {"status": "success", "respuesta_texto": respuesta_texto}

            # Devolver resultado SIN volver a hablar (ya habló el preview), EXCEPTO si hubo un error
            respuesta_final = "A la orden. " + " Y además, ".join(respuestas_acumuladas)
            
            hubo_error = any("Error" in str(r) or "error" in str(r) for r in respuestas_acumuladas)
            if hubo_error:
                errores = [str(r) for r in respuestas_acumuladas if "Error" in str(r) or "error" in str(r)]
                respuesta_final = "Señor, encontré problemas al ejecutar la acción: " + ", ".join(errores)
                agregar_al_historial("assistant", respuesta_final)
                return {"status": "success", "respuesta_texto": respuesta_final, "ya_hablado": False}
                
            agregar_al_historial("assistant", respuesta_final)
            return {"status": "success", "respuesta_texto": respuesta_final, "ya_hablado": True}
        
        # Si no usó herramientas, devolver la respuesta de texto normal
        respuesta_texto = message.content or "No tengo nada que decir al respecto, señor."
        
        # Limpiar los pensamientos internos de Gemma 4 (<thought>...</thought>)
        import re
        respuesta_texto = re.sub(r'<thought>.*?</thought>', '', respuesta_texto, flags=re.DOTALL).strip()
        if not respuesta_texto:
            respuesta_texto = "A sus órdenes, señor."
        
        agregar_al_historial("assistant", respuesta_texto)
        return {
            "status": "success", 
            "respuesta_texto": respuesta_texto
        }

    except Exception as e:
        error_str = str(e)
        print(f"[Error Sistema] {error_str}")
        
        # Rescatar texto útil o tool calls de errores de tool_use_failed del cerebro de reserva
        if "tool_use_failed" in error_str and "failed_generation" in error_str:
            import re
            
            tool_calls_encontrados = []
            
            def extraer_json_rescue(texto: str, inicio: int) -> str:
                nivel = 0
                i = inicio
                while i < len(texto):
                    if texto[i] == '{':
                        nivel += 1
                    elif texto[i] == '}':
                        nivel -= 1
                        if nivel == 0:
                            return texto[inicio:i+1]
                    i += 1
                return texto[inicio:]

            for match in re.finditer(r'<function=([a-zA-Z0-9_]+)', error_str):
                nombre = match.group(1).strip()
                pos_llave = error_str.find('{', match.end(1))
                if pos_llave != -1:
                    args_raw = extraer_json_rescue(error_str, pos_llave)
                    tool_calls_encontrados.append((nombre, args_raw))
            
            if tool_calls_encontrados:
                respuestas_acumuladas = []
                
                for nombre_tool, args_raw in tool_calls_encontrados:
                    # FIX: Limpiar escapes y llaves rotas
                    args_json = args_raw.strip()
                    args_json = args_json.replace(r"\'", "'")
                    if args_json.startswith("("):
                        args_json = "{" + args_json[1:]
                    if not args_json.startswith("{"):
                        args_json = "{" + args_json
                    if not args_json.endswith("}"):
                        args_json = args_json + "}"
                    
                    try:
                        try:
                            args = json.loads(args_json)
                        except json.JSONDecodeError:
                            import ast
                            args = ast.literal_eval(args_json)
                            
                        print(f"[Rescate Profundo] Llama intentó llamar a '{nombre_tool}' con '{args_json}'")
                        
                        if nombre_tool == "buscar_internet":
                            consulta = args.get("consulta", "")
                            resultado = await asyncio.to_thread(buscar_internet, consulta)
                            # Para buscar_internet, hacer segunda vuelta para que Jarvis interprete los resultados
                            respuesta = f"He buscado en internet sobre '{consulta}':\n\n{resultado}"
                            agregar_al_historial("assistant", respuesta)
                            return {"status": "success", "respuesta_texto": respuesta}
                            
                        elif nombre_tool in ["abrir_web", "buscar_google", "buscar_imagen", "reproducir_youtube", "abrir_programa", "cerrar_programa", "crear_archivo", "interactuar_app", "modificar_volumen", "modificar_brillo", "apagar_sistema", "suspender_sistema", "reiniciar_sistema", "cancelar_apagado", "crear_alarma", "listar_agenda", "cancelar_agenda", "leer_texto_seleccionado", "apagar_monitor"]:
                            param = args.get("parametro", args.get("consulta", args.get("contenido", "")))
                            cont = args.get("contenido", "")
                            resultado = await procesar_accion_sistema(nombre_tool, param, cont)
                            respuestas_acumuladas.append(resultado)
                            
                        elif nombre_tool == "controlar_sistema":
                            accion = args.get("accion", "abrir_web")
                            parametro = args.get("parametro", "")
                            contenido = args.get("contenido", "")
                            resultado = await procesar_accion_sistema(accion, parametro, contenido)
                            respuestas_acumuladas.append(resultado)
                            
                        elif nombre_tool == "controlar_spotify":
                            accion = args.get("accion", "buscar_y_reproducir")
                            busqueda = args.get("busqueda", "")
                            resultado = await asyncio.to_thread(controlar_playback, accion, busqueda)
                            respuestas_acumuladas.append(resultado)
                            
                        elif nombre_tool == "hacer_clic_visual":
                            descripcion = args.get("descripcion", "")
                            try:
                                esperar = int(args.get("esperar_segundos", 0))
                            except ValueError:
                                esperar = 0
                            resultado = await asyncio.to_thread(hacer_clic_visual, descripcion, esperar)
                            respuestas_acumuladas.append(resultado)

                        elif nombre_tool == "hacer_clic_fondo":
                            descripcion = args.get("descripcion", "")
                            ventana = args.get("ventana_titulo", "")
                            try:
                                esperar = int(args.get("esperar_segundos", 0))
                            except ValueError:
                                esperar = 0
                            resultado = await asyncio.to_thread(hacer_clic_fondo, descripcion, ventana, esperar)
                            respuestas_acumuladas.append(resultado)

                        elif nombre_tool == "crear_widget":
                            tipo = args.get("tipo", "reloj")
                            parametro = args.get("parametro", args.get("contenido", ""))
                            titulo = args.get("titulo", "")
                            resultado = await enviar_comando_widget({"tipo": tipo, "parametro": parametro, "titulo": titulo})
                            respuestas_acumuladas.append(resultado)

                        elif nombre_tool == "cerrar_widget":
                            identificador = args.get("identificador", "todos")
                            resultado = await enviar_cerrar_widget({"identificador": identificador})
                            respuestas_acumuladas.append(resultado)
                            
                        elif nombre_tool == "gestionar_memoria":
                            import tools_memoria
                            accion = args.get("accion", "")
                            clave = args.get("clave", "")
                            valor = args.get("valor", "")
                            resultado = await asyncio.to_thread(tools_memoria.gestionar_memoria, accion, clave, valor)
                            respuestas_acumuladas.append(resultado)
                            
                        elif nombre_tool == "controlar_obs":
                            import tools_obs
                            accion = args.get("accion", "")
                            parametro = args.get("parametro", "")
                            resultado = await asyncio.to_thread(tools_obs.controlar_obs, accion, parametro)
                            respuestas_acumuladas.append(resultado)
                            
                        elif nombre_tool == "gestionar_seguridad":
                            import tools_seguridad
                            accion = args.get("accion", "")
                            resultado = await asyncio.to_thread(tools_seguridad.gestionar_seguridad, accion)
                            respuestas_acumuladas.append(resultado)
                            
                        elif nombre_tool == "gestionar_vigilante_pantalla":
                            accion = args.get("accion", "")
                            resultado = await asyncio.to_thread(gestionar_vigilante_pantalla, accion)
                            respuestas_acumuladas.append(resultado)
                            
                    except json.JSONDecodeError as ex:
                        print(f"[Rescate Profundo] Error parseando tool call roto: {ex}")
                        continue
                
                if respuestas_acumuladas:
                    respuesta = "A la orden. " + " Y además, ".join(respuestas_acumuladas)
                    agregar_al_historial("assistant", respuesta)
                    return {"status": "success", "respuesta_texto": respuesta}

            # Si no hubo tool call (o falló), extraer el texto que escribió antes del error
            match = re.search(r"'failed_generation': '(.*?)\\n", error_str)
            if not match:
                match = re.search(r"'failed_generation': '(.*?)(?:<function|'\\})", error_str)
            
            if match:
                texto_rescatado = match.group(1).strip()
                if texto_rescatado and len(texto_rescatado) > 5:
                    print(f"[Rescate] Texto extraído de error: {texto_rescatado}")
                    agregar_al_historial("assistant", texto_rescatado)
                    return {"status": "success", "respuesta_texto": texto_rescatado}
                    
            return {"status": "success", "respuesta_texto": "Lo siento señor, mi cerebro de reserva tuvo un fallo interno."}
        
        raise HTTPException(status_code=500, detail=error_str)

import threading
import requests

def gestionar_vigilante_pantalla(accion: str) -> str:
    return "Ya no necesitas activar el vigilante manualmente. Ahora me transformaré en el Ojo Líquido de forma automática en cuanto me pidas que lea o analice tu pantalla."

if __name__ == "__main__":
    print("Iniciando el servidor de FastAPI Jarvis...")
    try:
        import os
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cerebro_actual.txt")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("claude")
    except:
        pass
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
