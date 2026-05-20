import re

with open('main.py', 'r', encoding='utf-8') as f:
    code = f.read()

code = re.sub(
    r'historial_conversacion\.append\(\{\s*["\']role["\']\s*:\s*["\'](user|assistant)["\']\s*,\s*["\']content["\']\s*:\s*(.*?)\s*\}\)',
    r'agregar_al_historial("\1", \2)',
    code
)

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(code)
print("Done")
