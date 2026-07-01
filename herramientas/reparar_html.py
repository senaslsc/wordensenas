"""
SCRIPT REPARADOR DE PÁGINAS HTML DE LA TESIS
=============================================
Uso: python reparar_html.py nombre_del_archivo.html

Este script repara el problema donde el bloque de ejercicios aparece vacío
porque GitHub Copilot dejó código corrupto (bloques de diff/patch) dentro del <script>.

Cómo funciona:
1. Detecta si el archivo tiene el problema
2. Extrae el código correcto de los bloques "newString"
3. Lo aplica sobre la copia limpia del código que está al final del archivo
4. Guarda el resultado como nombre_del_archivo-fixed.html
"""

import re
import sys
import os


def decode_escaped(s):
    """Decodifica las secuencias de escape que Copilot mete en los strings."""
    return (s
            .replace("\\'", "'")
            .replace('\\n', '\n')
            .replace('\\"', '"')
            .replace('\\\\', '\\'))


def reparar(archivo_entrada):
    nombre_base = os.path.splitext(archivo_entrada)[0]
    archivo_salida = nombre_base + '-fixed.html'

    with open(archivo_entrada, 'r', encoding='utf-8') as f:
        content = f.read()

    # ── 1. Verificar si el archivo tiene el problema ──────────────────────────
    if '"filePath"' not in content and ',"newString":' not in content:
        print(f'✅ "{archivo_entrada}" no tiene el problema. No se necesita reparación.')
        return

    print(f'⚠️  Bloque corrupto detectado en "{archivo_entrada}". Reparando...')

    # ── 2. Localizar las secciones del archivo ────────────────────────────────

    # Encontrar dónde empieza la segunda IIFE (la del juego)
    # Buscamos '(function () {' seguido de 'var tasks = ['
    iife_positions = [m.start() for m in re.finditer(r'\(function \s*\(\s*\)', content)]
    if len(iife_positions) < 2:
        print('❌ No se encontró la segunda función del juego. Revisa el archivo manualmente.')
        return
    game_iife_start = iife_positions[1]

    # Encontrar el primer bloque corrupto (empieza con '","newString"' o '"},{"filePath"')
    corrupt_start = content.find('","newString"', game_iife_start)
    if corrupt_start == -1:
        corrupt_start = content.find('},{"filePath"', game_iife_start)
    if corrupt_start == -1:
        print('❌ No se encontró el inicio del bloque corrupto.')
        return

    # ── 3. Extraer el código bueno ANTES del corrupto ────────────────────────
    # (tasks + state)
    code_before_corrupt = content[game_iife_start:corrupt_start]

    # ── 4. Extraer los newStrings (el código correcto) ───────────────────────
    corrupt_block = content[corrupt_start:]
    raw_pairs = re.findall(
        r'"newString":"(.*?)(?="[,\}])',
        corrupt_block,
        re.DOTALL
    )
    new_strings = [decode_escaped(ns) for ns in raw_pairs]
    print(f'   Encontrados {len(new_strings)} bloques de código nuevo (newString)')

    # ── 5. Encontrar la copia limpia al final del archivo ────────────────────
    # La copia limpia empieza con 'var editor = document.getElementById'
    # o con 'var feedback = document.getElementById' después del bloque corrupto
    clean_code_start = None
    for marker in ['var editor = document.getElementById', 'var feedback = document.getElementById']:
        positions = [m.start() for m in re.finditer(re.escape(marker), content)]
        # Tomar la última aparición (es la copia limpia al final)
        if positions:
            last_pos = positions[-1]
            if last_pos > corrupt_start + 1000:  # debe estar lejos del inicio
                clean_code_start = last_pos
                break

    if clean_code_start is None:
        print('❌ No se encontró la copia limpia al final del archivo.')
        return

    clean_code = content[clean_code_start:]

    # ── 6. Aplicar los newStrings sobre la copia limpia ──────────────────────
    raw_pairs_full = re.findall(
        r'"oldString":"(.*?)","newString":"(.*?)(?="[,\}])',
        corrupt_block,
        re.DOTALL
    )

    applied = 0
    for old_raw, new_raw in raw_pairs_full:
        old_decoded = decode_escaped(old_raw)
        new_decoded = decode_escaped(new_raw)
        if old_decoded in clean_code:
            clean_code = clean_code.replace(old_decoded, new_decoded, 1)
            applied += 1

    print(f'   Parches aplicados: {applied} de {len(raw_pairs_full)}')

    # Correcciones adicionales frecuentes:
    # a) Agregar gameScoreLabel si no está
    score_id_match = re.search(r"getElementById\('(\w+-score)'\)", '\n'.join(new_strings))
    if score_id_match:
        score_id = score_id_match.group(1)
        game_score_line = f"      var gameScoreLabel = document.getElementById('{score_id}');"
        if 'gameScoreLabel' not in clean_code:
            # Insertarlo después de la primera línea de var feedback
            clean_code = re.sub(
                r"(var feedback = document\.getElementById\('[^']+'\);)",
                r"\1\n" + game_score_line,
                clean_code,
                count=1
            )
            print(f'   gameScoreLabel ({score_id}) añadido manualmente')

    # b) Asegurar que el state tiene ; al final
    clean_code = re.sub(r'(gameScore:\s*0\s*\})\s*\n', r'\1;\n', clean_code)

    # ── 7. Reconstruir el archivo ─────────────────────────────────────────────
    before_game = content[:game_iife_start]

    new_content = (
        before_game
        + code_before_corrupt
        + '\n\n      '
        + clean_code
    )

    # ── 8. Verificación ───────────────────────────────────────────────────────
    bad_markers = [',"newString":', '"oldString":', '"filePath":']
    dirty = [b for b in bad_markers if b in new_content]
    if dirty:
        print(f'⚠️  Aún quedan rastros de código corrupto: {dirty}')
    else:
        print('✅ Sin rastros de código corrupto')

    with open(archivo_salida, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f'✅ Archivo reparado guardado como: {archivo_salida}')
    print()


# ── Punto de entrada ──────────────────────────────────────────────────────────
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Uso: python reparar_html.py archivo.html [archivo2.html ...]')
        print('Ejemplo: python reparar_html.py 12-interlineado.html 13-sangria.html')
        sys.exit(1)

    for archivo in sys.argv[1:]:
        if not os.path.exists(archivo):
            print(f'❌ Archivo no encontrado: {archivo}')
            continue
        reparar(archivo)
