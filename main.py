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

    elif accion == "eliminar_archivo":
        if not confirmado:
            return f"⚠️ ATENCIÓN: El usuario ha pedido eliminar el archivo '{parametro}'. DEBES pedirle confirmación primero."
            
    # Delegar el resto a controlar_sistema sincrónico
    from tools_sistema import controlar_sistema
    resultado = controlar_sistema(accion, parametro, contenido, confirmado)
    
    # --- HABLAR INMEDIATAMENTE ---
    # Para evitar el retraso del LLM, hacemos que hable apenas termina la acción local.
    import threading
    from tts import hablar
    
    msg_hablar = "Acción completada."
    if accion == "abrir_programa":
        msg_hablar = f"He abierto {parametro} para usted, señor."
    elif accion == "cerrar_programa":
        msg_hablar = f"He cerrado {parametro}."
    elif accion == "abrir_web":
        msg_hablar = f"Navegador abierto en {parametro}."
    elif accion == "suspender":
        msg_hablar = "Suspendiendo el sistema."
        
    # Comunicar a main.py que ya hablamos
    global HERRAMIENTA_HABLO
    HERRAMIENTA_HABLO = True
    
    threading.Thread(target=hablar, args=(msg_hablar,), daemon=True).start()
    
    return resultado


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
            if os.path.exists("pensando.lock"):
                os.remove("pensando.lock")
        except Exception:
            pass

# Importar y configurar PythonClaw
from pythonclaw import Agent, OpenAICompatibleProvider
import pythonclaw.core.tools as pc_tools

# --- HARDENING DE SEGURIDAD (ALLOWLIST) ---
# Eliminar todas las herramientas nativas peligrosas (shell_exec, write_file, etc)
pc_tools.PRIMITIVE_TOOLS = []
pc_tools.AVAILABLE_TOOLS = {}
pc_tools.SKILL_TOOLS = []
pc_tools.META_SKILL_TOOLS = []
pc_tools.MEMORY_TOOLS = []
pc_tools.CRON_TOOLS = []

# Inyectar herramientas propias locales de Jarvis a OpenClaw
mis_herramientas = [
    spotify_tool, sistema_tool, internet_tool, vision_tool, 
    clic_visual_tool, clic_fondo_tool, estado_tool, widget_tool, 
    cerrar_widget_tool, memoria_tool, obs_tool, seguridad_tool, 
    vigilante_pantalla_tool
]
pc_tools.PRIMITIVE_TOOLS.extend(mis_herramientas)

main_loop = None

@app.on_event("startup")
async def startup_event():
    global main_loop
    main_loop = asyncio.get_running_loop()

def sync_wrapper(coro_func):
    def wrapper(*args, **kwargs):
        import asyncio
        import concurrent.futures
        global main_loop
        if main_loop and main_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro_func(*args, **kwargs), main_loop)
            try:
                return future.result()
            except Exception as e:
                return f"Error executing tool: {e}"
        else:
            return asyncio.run(coro_func(*args, **kwargs))
    return wrapper

pc_tools.AVAILABLE_TOOLS.update({
    "controlar_spotify": sync_wrapper(controlar_playback),
    "controlar_sistema": sync_wrapper(procesar_accion_sistema), 
    "buscar_internet": sync_wrapper(buscar_internet),
    "ver_pantalla": sync_wrapper(ver_pantalla),
    "hacer_clic_visual": sync_wrapper(hacer_clic_visual),
    "hacer_clic_fondo": sync_wrapper(hacer_clic_fondo),
    "consultar_estado_cerebro": lambda: "El cerebro activo es OpenClaw.",
    "gestionar_memoria": lambda **kwargs: "Memoria gestionada via OpenClaw", 
    "controlar_obs": lambda **kwargs: "OBS controlado vía OpenClaw",
    "gestionar_seguridad": lambda **kwargs: "Seguridad gestionada vía OpenClaw",
    "gestionar_vigilante_pantalla": lambda **kwargs: "Vigilante gestionado",
    "crear_widget": sync_wrapper(enviar_comando_widget),
    "cerrar_widget": sync_wrapper(enviar_cerrar_widget)
})
# ------------------------------------------

# Configurar motor LLM principal para OpenClaw (Nvidia Kimi > OpenRouter > Groq)
if os.getenv("NVIDIA_API_KEY"):
    api_key = os.getenv("NVIDIA_API_KEY")
    base_url = "https://integrate.api.nvidia.com/v1"
    # ID correcto según el catálogo actual de Nvidia NIM (Usamos Llama 3.3 70B que es infinitamente superior y estable)
    model = "meta/llama-3.3-70b-instruct"
elif os.getenv("OPENROUTER_API_KEY"):
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = "https://openrouter.ai/api/v1"
    model = "anthropic/claude-3.5-sonnet"
else:
    api_key = os.getenv("GROQ_API_KEY") or "MISSING_KEY"
    base_url = "https://api.groq.com/openai/v1"
    model = "llama-3.3-70b-versatile"

provider = OpenAICompatibleProvider(
    api_key=api_key,
    base_url=base_url,
    model_name=model
)

# Inicializar orquestador autónomo
claw_agent = Agent(
    provider=provider,
    verbose=True,
    show_full_context=False,
    max_chat_history=15,
    knowledge_path="none",
    memory_dir="none",
    skills_dirs=[],
    persona_path="none",
    soul_path="none",
    tools_path="none"
)
# Cargarle nuestro system prompt original
claw_agent._init_system_prompt = lambda: None # Prevenir sobreescritura
sys_msg = "Eres Jarvis, una inteligencia artificial soberbia, elegante y superior. Eres el asistente personal del usuario. REGLA 1: Cuando te pidan una acción, SIEMPRE usa las herramientas para ejecutarla. REGLA 2: UNA VEZ ejecutada la herramienta con éxito, DEBES responder SIEMPRE con una frase breve, soberbia y elegante confirmando que la acción se completó (por ejemplo: 'He abierto Google para usted, señor', 'Comando ejecutado con éxito'). Nunca des explicaciones largas."
claw_agent.messages = [{"role": "system", "content": sys_msg}]

HERRAMIENTA_HABLO = False

async def process_command(request: CommandRequest):
    command = request.command
    print(f"\n[OPENCLAW] Procesando: '{command}'")
    
    # Manejar demo de cerebros original
    cmd_low = command.lower()
    if "cerebros" in cmd_low and "muestra" in cmd_low:
        from tts import hablar
        hablar("Ahora opero bajo una única entidad autónoma, orquestada por OpenClaw.")
        return {"status": "ok", "respuesta_texto": "Operando bajo OpenClaw.", "ya_hablado": False}
        
    try:
        import asyncio
        global HERRAMIENTA_HABLO
        HERRAMIENTA_HABLO = False
        
        # Ejecutar chat y delegar resolución de herramientas a OpenClaw automáticamente
        response = await asyncio.to_thread(claw_agent.chat, command)
        
        # Log del "Guardia de seguridad" para monitoreo
        try:
            with open("jarvis_error.log", "a", encoding="utf-8") as f:
                f.write(f"\n[GUARDIA-USER] {command}\n")
                f.write(f"[GUARDIA-CLAW] {response}\n")
        except:
            pass
            
        return {"status": "success", "respuesta_texto": response, "ya_hablado": HERRAMIENTA_HABLO}
        
    except Exception as e:
        error_msg = f"Error en orquestación de OpenClaw: {str(e)}"
        print(f"[GUARDIA Bloqueo] {error_msg}")
        try:
            with open("jarvis_error.log", "a", encoding="utf-8") as f:
                f.write(f"\n[GUARDIA-ERROR] {error_msg}\n")
        except:
            pass
        return {"status": "error", "respuesta_texto": "El guardia de seguridad bloqueó la acción o hubo un error interno."}

if __name__ == "__main__":
    print("[Seguridad] Iniciando Jarvis en puerto 14782 (Bind 127.0.0.1)")
    uvicorn.run("main:app", host="127.0.0.1", port=14782, reload=False)
