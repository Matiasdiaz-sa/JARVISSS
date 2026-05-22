import os
import json
import re
from typing import Optional, Dict, Union, List

import anthropic
import google.generativeai as genai
from dotenv import load_dotenv

# ==========================================
# Carga de Configuración y Variables
# ==========================================
load_dotenv()

# Configurar clientes (las keys deben estar en tu archivo .env)
# Variables esperadas en .env:
# ANTHROPIC_API_KEY=tu_clave_de_claude
# GOOGLE_API_KEY=tu_clave_de_gemini
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if ANTHROPIC_API_KEY:
    client_anthropic = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)


# ==========================================
# 2. Gestor de Memoria (Short-Term Memory)
# ==========================================
# Mantiene el historial de la conversación limitado a los últimos 3 intercambios.
# (3 del usuario + 3 del asistente = 6 mensajes en total)
historial: List[Dict[str, str]] = []

def actualizar_memoria(rol: str, contenido: str):
    """
    Agrega un mensaje al historial y recorta para mantener solo los últimos 6.
    """
    global historial
    historial.append({"role": rol, "content": contenido})
    if len(historial) > 4:
        historial = historial[-4:]

def obtener_historial_formateado() -> str:
    """Devuelve el historial en un formato claro para inyectar en el prompt."""
    if not historial:
        return "No hay historial previo."
    return "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in historial])


# ==========================================
# 1. Enrutador de Latencia Cero (Keyword Router)
# ==========================================
def keyword_router(texto: str) -> Optional[Dict[str, str]]:
    """
    Evalúa el texto buscando palabras clave para ejecutar acciones instantáneas sin consultar a la API.
    Si detecta coincidencia, retorna el JSON correspondiente, minimizando latencia a cero.
    """
    texto_lower = texto.lower()
    
    if "spotify" in texto_lower:
        return {"accion": "abrir_spotify", "argumentos": texto, "respuesta_voz": "Abriendo Spotify de inmediato."}
        
    if "apagar pc" in texto_lower or "apaga la pc" in texto_lower:
        return {"accion": "apagar_pc", "argumentos": "", "respuesta_voz": "Iniciando secuencia de apagado del sistema."}
        
    if "luz" in texto_lower and ("encender" in texto_lower or "prender" in texto_lower):
        return {"accion": "encender_luz_tuya", "argumentos": "", "respuesta_voz": "Encendiendo la luz."}
        
    if "tv" in texto_lower and "prender" in texto_lower:
        return {"accion": "prender_tv", "argumentos": "", "respuesta_voz": "Encendiendo el televisor."}
    
    return None


# ==========================================
# 3. Parser de Seguridad (JSON Extractor)
# ==========================================
def procesar_respuesta(texto: str) -> Union[Dict, str]:
    """
    Analiza la respuesta textual de Claude buscando un bloque JSON válido.
    Si lo encuentra, lo devuelve como diccionario. Si no, devuelve el texto plano para hablar.
    """
    try:
        # Busca el primer bloque encerrado entre { y } (soporta llaves y saltos de línea anidados)
        match = re.search(r'\{.*?\}', texto, re.DOTALL)
        if match:
            bloque_json = match.group(0)
            # Reemplazar posibles comillas simples alucinadas por dobles para parsear correctamente
            bloque_json = bloque_json.replace("'", "\"")
            data = json.loads(bloque_json)
            # Verificamos que tenga la estructura mínima requerida
            if "accion" in data:
                return data
    except Exception:
        pass
    
    # Si falla o no hay JSON, retorna el texto limpio
    return texto.strip()


# ==========================================
# Procesadores Cognitivos (Gemini y Claude)
# ==========================================
def procesar_con_gemini(texto: str, imagen_base64: str) -> str:
    """
    Delega el análisis visual a Gemini 1.5 Flash usando el SDK de Google.
    """
    if not GOOGLE_API_KEY:
        return "Error: Clave de Google API no configurada para procesar imágenes."
        
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        # Preparamos el payload visual (se asume imagen JPEG/PNG)
        prompt_parts = [
            texto if texto else "Describe brevemente qué hay en esta pantalla.",
            {"mime_type": "image/jpeg", "data": imagen_base64}
        ]
        
        response = model.generate_content(prompt_parts)
        return response.text
    except Exception as e:
        return f"Ha ocurrido un error analizando la imagen: {e}"

def procesar_con_claude(texto: str) -> Union[Dict, str]:
    """
    Cerebro analítico principal. Recibe el texto y el contexto reciente,
    evalúa la lógica y decide si ejecutar una acción o hablar.
    """
    if not ANTHROPIC_API_KEY:
        return "Error: Clave de Anthropic no configurada."
        
    system_prompt = (
        "Eres Jarvis, una inteligencia artificial de asistencia. Tu comportamiento es eficiente, "
        "directo, profesional y ligeramente cínico. No uses frases de relleno ni saludos innecesarios.\n"
        "Si el usuario hace una pregunta conversacional, responde brevemente con tu personalidad.\n"
        "Si el usuario pide una acción que requiere control del sistema, DEBES responder ÚNICAMENTE con "
        "un bloque JSON válido con la siguiente estructura, sin texto adicional:\n"
        "{ \"accion\": \"nombre_de_la_herramienta\", \"argumentos\": \"valor_si_aplica\", \"respuesta_voz\": \"Frase corta que dirás en voz alta\" }\n"
        "Herramientas disponibles: [abrir_spotify, apagar_pc, encender_luz_tuya, prender_tv]"
    )
    
    # Preparamos el contexto para inyectarlo en la llamada
    contexto = obtener_historial_formateado()
    mensaje_final = f"=== HISTORIAL RECIENTE ===\n{contexto}\n=========================\n\nUsuario: {texto}"
    
    try:
        response = client_anthropic.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=120,
            temperature=0.0,
            system=system_prompt,
            messages=[
                {"role": "user", "content": mensaje_final}
            ]
        )
        texto_respuesta = response.content[0].text
        return procesar_respuesta(texto_respuesta)
    except Exception as e:
        return f"Ocurrió un fallo en mis sistemas de procesamiento lógico: {e}"


# ==========================================
# ORQUESTADOR PRINCIPAL
# ==========================================
def procesar_entrada(texto: str, imagen_base64: Optional[str] = None) -> Union[Dict, str]:
    """
    Punto de entrada único. Rutea la entrada a través de la arquitectura definida.
    """
    # 1. Intentar el enrutador de latencia cero primero
    accion_rapida = keyword_router(texto)
    if accion_rapida:
        actualizar_memoria("user", texto)
        actualizar_memoria("assistant", f"[Ejecución Rápida] {json.dumps(accion_rapida)}")
        return accion_rapida
    
    # 2. Si hay una imagen presente, derivar el proceso a Gemini (Multimodal)
    if imagen_base64:
        respuesta_visual = procesar_con_gemini(texto, imagen_base64)
        actualizar_memoria("user", f"[Adjuntó imagen] {texto}")
        actualizar_memoria("assistant", respuesta_visual)
        return respuesta_visual
    
    # 3. Flujo normal de conversación hacia Claude
    resultado = procesar_con_claude(texto)
    
    # Guardar en la memoria a corto plazo
    actualizar_memoria("user", texto)
    if isinstance(resultado, dict):
        actualizar_memoria("assistant", json.dumps(resultado))
    else:
        actualizar_memoria("assistant", str(resultado))
        
    return resultado


# ==========================================
# Pruebas Rápidas (Ejecución Directa)
# ==========================================
if __name__ == "__main__":
    print("Probando Router de Latencia Cero:")
    print(procesar_entrada("jarvis apaga la pc por favor"))
    
    print("\nProbando Fallback / Parseo (Sin APIs Configuradas):")
    print(procesar_entrada("Hola, ¿quién eres?"))
