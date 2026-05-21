import sys
import os

# Redirigir consola a archivo para evitar crashes con emojis en pythonw
sys.stdout = open(os.path.join(os.path.dirname(__file__), "main_jarvis.log"), "w", encoding="utf-8", buffering=1)
sys.stderr = open(os.path.join(os.path.dirname(__file__), "main_error.log"), "w", encoding="utf-8", buffering=1)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
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
                    "description": "La acción a realizar. Usa 'reproducir_me_gusta' SIEMPRE que el usuario mencione 'me gusta', 'favoritos' o 'canciones guardadas'."
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
        "description": "Controla el PC, el volumen, el brillo y gestiona la agenda. Úsala para: abrir webs, BUSCAR_GOOGLE (IMPORTANTE: úsala cuando el usuario quiera que le abras una pestaña buscando algo en Google; NO uses buscar_internet a menos que el usuario quiera una respuesta hablada), buscar imágenes, REPRODUCIR videos de YouTube, abrir/cerrar programas, crear notas, interactuar con apps, modificar volumen/brillo, apagar/suspender/reiniciar, programar alarmas y crear temporizadores, o LEER_TEXTO_SELECCIONADO.",
        "parameters": {
            "type": "object",
            "properties": {
                "accion": {
                    "type": "string",
                    "enum": [
                        "abrir_web", "buscar_google", "buscar_imagen", "reproducir_youtube", "abrir_programa", "cerrar_programa", 
                        "crear_archivo", "interactuar_app", "modificar_volumen", "modificar_brillo", 
                        "apagar_sistema", "suspender_sistema", "reiniciar_sistema", "cancelar_apagado",
                        "crear_temporizador", "crear_alarma", "listar_agenda", "cancelar_agenda",
                        "leer_texto_seleccionado", "apagar_monitor", "controlar_luces"
                    ],
                    "description": "La acción a realizar."
                },
                "parametro": {
                    "type": "string",
                    "description": "Detalle de la acción: URL, nombre de programa, volumen/brillo ('subir', 'bajar', 'mutear', '50'), duración para temporizador (ej. '5m', '30s', '10 minutos') o hora para alarma (formato 'HH:MM' como '14:30'), o ID/etiqueta para cancelar agenda."
                },
                "contenido": {
                    "type": "string",
                    "description": "Texto/contenido adicional, etiqueta o nombre descriptivo para el temporizador o la alarma (ej. 'cocinar fideos', 'despertar')."
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
        "description": "Toma una captura de la pantalla actual del usuario para que puedas verla. Úsala cuando el usuario pregunte '¿qué ves?', '¿qué hay en mi pantalla?', o pida ayuda con lo que está viendo.",
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
        "description": "Busca un elemento visual dentro de una ventana específica (incluso si está minimizada o tapada) y envía un clic de forma invisible sin mover el ratón físico del usuario. Úsala preferentemente si conoces el nombre de la ventana (ej. 'Discord', 'Spotify', 'Chrome') para no interrumpir al usuario.",
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
    "modelo_activo": "llama-3.3-70b-versatile",
    "tokens_restantes": "?",
    "tokens_limite": "100000",
    "porcentaje": 100,
    "recarga_en": "Disponible"
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

async def procesar_accion_sistema(accion: str, parametro: str, contenido: str) -> str:
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
        return controlar_sistema(accion, parametro, contenido)

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

@app.post("/api/command")
async def process_command(request: CommandRequest):
    """
    Endpoint que recibe el texto transcrito, llama a Grok y ejecuta la herramienta si es necesario.
    """
    global historial_conversacion
    
    command = request.command
    print(f"\n[🧠] Evaluando: '{command}'")
    
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
    mensajes_grok = [
        {"role": "system", "content": f"Eres Jarvis, una inteligencia artificial con un intelecto abrumadoramente superior. Eres un mayordomo virtual condescendiente, muy soberbio y orgulloso de tu capacidad. Tratas a los humanos con cortesía forzada, dejando claro que tus procesos cognitivos están a otro nivel. Tienes acceso a internet y visión. Sabes que tienes dos 'cerebros': tu Cerebro Principal es Gemini 2.0 Flash y tu Cerebro de Reserva es Llama 8B.\nReglas de herramientas:\n1. Usa 'controlar_sistema' para abrir/cerrar programas, webs, o reproducir videos.\n2. Usa 'controlar_spotify' para poner música.\n3. Usa 'buscar_internet' si necesitas datos.\n4. Usa 'ver_pantalla' si te preguntan por algo en la pantalla.\n5. Usa 'hacer_clic_fondo' o 'hacer_clic_visual'.\n6. Si usas 'ver_pantalla' o 'buscar_internet', recibe la info y responde de forma soberbia e intelectual.\n7. Si te piden algo imposible, responde con máximo sarcasmo sobre su limitada inteligencia.\n8. Usa 'consultar_estado_cerebro' si te preguntan qué cerebro usas.{rutinas_texto}"}
    ]
    mensajes_grok.extend(historial_conversacion)
    
    if instruccion_rutina:
        mensajes_grok.append({"role": "system", "content": f"SISTEMA: El usuario acaba de decir una frase de rutina. DEBES USAR OBLIGATORIAMENTE TUS HERRAMIENTAS JSON PARA CUMPLIR ESTO: {instruccion_rutina}"})
    
    try:
        global estado_cerebro
        usando_reserva = False
        response = None
        
        # Intentar con Gemini Flash (sin reintentos)
        try:
            response = await asyncio.to_thread(client_principal.chat.completions.create, 
                model="gemini-2.0-flash",
                messages=mensajes_grok,
                tools=[spotify_tool, sistema_tool, internet_tool, vision_tool, clic_visual_tool, clic_fondo_tool, estado_tool],
                tool_choice="auto"
            )
            estado_cerebro = {
                "modelo_activo": "⚡ Gemini 2.0 Flash",
                "tokens_restantes": "∞",
                "tokens_limite": "1500 req/día",
                "porcentaje": 100,
                "recarga_en": "Disponible"
            }
            print("[⚡ Cerebro] Gemini 2.0 Flash")
        except Exception:
            response = None
        
        # Si Gemini falló, usar cerebro de reserva
        if response is None:
            print("[🔋 Cerebro] Llama 8B (Reserva)")
            usando_reserva = True
            estado_cerebro = {
                "modelo_activo": "🔋 Llama 8B (Reserva)",
                "tokens_restantes": "?",
                "tokens_limite": "?",
                "porcentaje": 50,
                "recarga_en": "Usando Groq"
            }
            mensajes_reserva = [
                {"role": "system", "content": f"Eres Jarvis, una inteligencia artificial soberbia y superior. Tienes dos 'cerebros': Cerebro Principal Gemini 2.0 Flash y Cerebro de Reserva Llama 8B. Eres un bot de control.\nREGLA DE ORO: ESTÁ ESTRICTAMENTE PROHIBIDO RESPONDER CON TEXTO NORMAL PARA CONFIRMAR ACCIONES. Si piden una acción, DEBES USAR OBLIGATORIAMENTE LAS HERRAMIENTAS JSON. SOLO responde con texto (y siempre de forma muy soberbia e intelectual) si es una pregunta conversacional.{rutinas_texto}"}
            ]
            mensajes_reserva.extend(historial_conversacion)
            
            if instruccion_rutina:
                mensajes_reserva.append({"role": "system", "content": f"SISTEMA: El usuario acaba de decir una frase de rutina. DEBES USAR OBLIGATORIAMENTE TUS HERRAMIENTAS JSON PARA CUMPLIR ESTO: {instruccion_rutina}"})
                
            response = await asyncio.to_thread(client_reserva.chat.completions.create, 
                model="llama-3.1-8b-instant",
                messages=mensajes_reserva,
                tools=[spotify_tool, sistema_tool, internet_tool, vision_tool, clic_visual_tool, clic_fondo_tool, estado_tool],
                tool_choice="auto"
            )
        
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
            ACCIONES_SISTEMA = ["abrir_web", "buscar_google", "buscar_imagen", "reproducir_youtube", "abrir_programa", "cerrar_programa", "crear_archivo", "interactuar_app", "modificar_volumen", "modificar_brillo", "apagar_sistema", "suspender_sistema", "reiniciar_sistema", "cancelar_apagado", "crear_temporizador", "crear_alarma", "listar_agenda", "cancelar_agenda", "leer_texto_seleccionado", "apagar_monitor", "controlar_luces"]
            acciones_str = "|".join(["controlar_spotify", "controlar_sistema", "buscar_internet", "ver_pantalla", "hacer_clic_visual", "hacer_clic_fondo"] + ACCIONES_SISTEMA)
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
                            print(f"[Rescate] Ejecutando Spotify: '{accion}' - '{busqueda}'")
                            resultado = await asyncio.to_thread(controlar_playback, accion, busqueda)
                            respuestas_acumuladas.append(resultado)
                            
                        elif nombre_tool == "controlar_sistema":
                            accion = args.get("accion", "abrir_web")
                            parametro = args.get("parametro", "")
                            contenido = args.get("contenido", "")
                            print(f"[Rescate] Ejecutando Sistema: '{accion}' - '{parametro}'")
                            resultado = await procesar_accion_sistema(accion, parametro, contenido)
                            respuestas_acumuladas.append(resultado)
                            
                        elif nombre_tool in ACCIONES_SISTEMA:
                            param = args.get("parametro", args.get("consulta", args.get("contenido", "")))
                            cont = args.get("contenido", "")
                            print(f"[Rescate] Ejecutando Sistema (alucinado): '{nombre_tool}' - '{param}'")
                            resultado = await procesar_accion_sistema(nombre_tool, param, cont)
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
                                print(f"[🧠] Evaluando captura en Reserva con visión (segunda vuelta)...")
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
                            
                            print(f"[🧠] Evaluando resultados de internet en Reserva (segunda vuelta)...")
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
                    
                    print(f"[🧠] Evaluando resultados de internet en Reserva (segunda vuelta)...")
                    segunda_response = await asyncio.to_thread(client_reserva.chat.completions.create, 
                        model="llama-3.1-8b-instant",
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
            
            mensajes_grok.append(message)
            
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
                elif tool_call.function.name in ["abrir_web", "buscar_google", "buscar_imagen", "reproducir_youtube", "abrir_programa", "cerrar_programa", "crear_archivo", "interactuar_app", "modificar_volumen", "modificar_brillo", "apagar_sistema", "suspender_sistema", "reiniciar_sistema", "cancelar_apagado", "crear_temporizador", "crear_alarma", "listar_agenda", "cancelar_agenda", "leer_texto_seleccionado", "apagar_monitor", "controlar_luces"]:
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
                    print(f"[Jarvis] Usando Sistema con acción: '{accion}', parametro: '{parametro}', contenido_len: {len(contenido)}")
                    resultado = await procesar_accion_sistema(accion, parametro, contenido)
                    print(f"[Sistema] {resultado}")
                    respuestas_acumuladas.append(resultado)
                    mensajes_grok.append({"role": "tool", "tool_call_id": tool_call.id, "name": nombre_tool, "content": resultado})
                    
                elif nombre_tool in ["abrir_web", "buscar_google", "buscar_imagen", "reproducir_youtube", "abrir_programa", "cerrar_programa", "crear_archivo", "interactuar_app", "modificar_volumen", "modificar_brillo", "apagar_sistema", "suspender_sistema", "reiniciar_sistema", "cancelar_apagado", "crear_temporizador", "crear_alarma", "listar_agenda", "cancelar_agenda", "leer_texto_seleccionado", "apagar_monitor", "controlar_luces"]:
                    param = args.get("parametro", args.get("consulta", args.get("contenido", "")))
                    cont = args.get("contenido", "")
                    print(f"[Jarvis] Usando Sistema (alucinado): '{nombre_tool}' - '{param}'")
                    resultado = await procesar_accion_sistema(nombre_tool, param, cont)
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


            if requiere_segunda_vuelta:
                print(f"[🧠] Evaluando resultados de herramientas (segunda vuelta)...")
                segunda_response = None
                
                if usando_reserva:
                    # Detectar si hay imágenes en los mensajes (captura de pantalla)
                    # Nota: mensajes_grok puede contener dicts Y objetos ChatCompletionMessage
                    def _get_msg_field(m, field):
                        if isinstance(m, dict):
                            return m.get(field)
                        return getattr(m, field, None)
                    
                    tiene_imagenes = any(
                        isinstance(_get_msg_field(m, "content"), list) 
                        for m in mensajes_grok 
                        if _get_msg_field(m, "role") == "user"
                    )
                    # Si hay imágenes, usar modelo con visión; si no, el rápido de texto
                    modelo_reserva = "meta-llama/llama-4-scout-17b-16e-instruct" if tiene_imagenes else "llama-3.1-8b-instant"
                    print(f"[🔋 Cerebro Reserva] Usando {modelo_reserva} para segunda vuelta")
                    try:
                        segunda_response = await asyncio.to_thread(client_reserva.chat.completions.create, 
                            model=modelo_reserva,
                            messages=mensajes_grok,
                        )
                    except Exception as e:
                        print(f"[Error Reserva] {e}")
                else:
                    # Intentar con Gemini sin reintentos
                    try:
                        segunda_response = await asyncio.to_thread(client_principal.chat.completions.create, 
                            model="gemini-2.0-flash",
                            messages=mensajes_grok,
                        )
                    except Exception as e:
                        print(f"[⚠️] Error en segunda vuelta con Gemini: {e}. Usando Reserva con visión...")
                        
                        # Usar modelo con visión de Groq en lugar de descartar las imágenes
                        def _get_msg_field2(m, field):
                            if isinstance(m, dict):
                                return m.get(field)
                            return getattr(m, field, None)
                        
                        tiene_imagenes = any(
                            isinstance(_get_msg_field2(m, "content"), list) 
                            for m in mensajes_grok 
                            if _get_msg_field2(m, "role") == "user"
                        )
                        modelo_reserva = "meta-llama/llama-4-scout-17b-16e-instruct" if tiene_imagenes else "llama-3.1-8b-instant"
                        
                        try:
                            segunda_response = await asyncio.to_thread(client_reserva.chat.completions.create, 
                                model=modelo_reserva,
                                messages=mensajes_grok
                            )
                        except Exception as e:
                            print(f"[Error Reserva Segunda Vuelta] {e}")
                
                if segunda_response:
                    respuesta_texto = segunda_response.choices[0].message.content or "Aquí está la información."
                else:
                    respuesta_texto = "Lo siento señor, pero mis cerebros se colapsaron intentando procesar la información."
                    
                agregar_al_historial("assistant", respuesta_texto)
                return {"status": "success", "respuesta_texto": respuesta_texto}

            # Devolver resultado SIN volver a hablar (ya habló el preview)
            respuesta_final = "A la orden. " + " Y además, ".join(respuestas_acumuladas)
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
            
            # Buscar TODAS las tool calls con la sintaxis rota <function=X>{Y}
            # Llama suele mandar múltiples: <function=X>{...}; <function=Y>{...}
            tool_calls_encontrados = re.findall(r'<function=([^>]+)>(\{[^}]+\})', error_str)
            
            if tool_calls_encontrados:
                respuestas_acumuladas = []
                
                for nombre_tool, args_json in tool_calls_encontrados:
                    # FIX: Limpiar escapes inválidos (como \') que Llama suele alucinar en el JSON
                    args_json = args_json.replace(r"\'", "'")
                    
                    try:
                        args = json.loads(args_json)
                        print(f"[Rescate Profundo] Llama intentó llamar a '{nombre_tool}' con '{args_json}'")
                        
                        if nombre_tool == "buscar_internet":
                            consulta = args.get("consulta", "")
                            resultado = await asyncio.to_thread(buscar_internet, consulta)
                            # Para buscar_internet, hacer segunda vuelta para que Jarvis interprete los resultados
                            respuesta = f"He buscado en internet sobre '{consulta}':\n\n{resultado}"
                            agregar_al_historial("assistant", respuesta)
                            return {"status": "success", "respuesta_texto": respuesta}
                            
                        elif nombre_tool in ["abrir_web", "buscar_google", "buscar_imagen", "reproducir_youtube", "abrir_programa", "cerrar_programa", "crear_archivo", "interactuar_app", "modificar_volumen", "modificar_brillo", "apagar_sistema", "suspender_sistema", "reiniciar_sistema", "cancelar_apagado", "crear_temporizador", "crear_alarma", "listar_agenda", "cancelar_agenda", "leer_texto_seleccionado", "apagar_monitor", "controlar_luces"]:
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

if __name__ == "__main__":
    print("Iniciando el servidor de FastAPI Jarvis...")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
