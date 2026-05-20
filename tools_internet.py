from ddgs import DDGS

def buscar_internet(consulta: str):
    """Busca en internet usando DuckDuckGo y devuelve un resumen de los primeros resultados."""
    try:
        print(f"[Internet] Buscando: {consulta}")
        resultados = DDGS().text(consulta, max_results=4)
        if not resultados:
            return "No se encontraron resultados para la búsqueda."
        
        texto_resultados = "Resultados de búsqueda:\n"
        for i, res in enumerate(resultados):
            texto_resultados += f"{i+1}. {res.get('title', '')}: {res.get('body', '')}\n"
        
        return texto_resultados
    except Exception as e:
        print(f"[Internet] Error: {e}")
        return f"Error al buscar en internet: {e}"

if __name__ == "__main__":
    print(buscar_internet("clima en buenos aires hoy"))
