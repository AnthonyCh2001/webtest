import os
import time
import pandas as pd
import cohere
import concurrent.futures
import unicodedata
import re
import json
import uuid
import requests
import numpy as np

from flask import Flask, request, render_template, send_from_directory, redirect, url_for, flash, abort, session
from fpdf import FPDF
from io import BytesIO
from werkzeug.utils import secure_filename
from concurrent.futures import ProcessPoolExecutor
from dotenv import load_dotenv
from datetime import datetime
import matplotlib
matplotlib.use('Agg')  # Reemplaza el backend de matplotlib
import matplotlib.pyplot as plt

from dao.DAOEmpresas import DAOEmpresas
from dao.DAOUsuario import DAOUsuario
from dao.DAOReportes import DAOReportes

app = Flask(__name__)
app.secret_key = 'supersecretkey'

dao_reportes = DAOReportes()
dao_empresas = DAOEmpresas()
dao_usuario = DAOUsuario()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
PDF_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pdfs')
CHART_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'charts')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PDF_FOLDER, exist_ok=True)
os.makedirs(CHART_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'uploads')
app.config['PDF_FOLDER'] = os.path.join(BASE_DIR, 'pdfs')
app.config['CHART_FOLDER'] = os.path.join(BASE_DIR, 'charts')

load_dotenv()

api_key = os.getenv("CO_API_KEY")
co = cohere.Client(api_key)

# Manejo de variables del excel
MAPA_PDFS_PATH = os.path.join(PDF_FOLDER, 'mapa_pdfs.json')
def cargar_mapa_pdfs():
    if os.path.exists(MAPA_PDFS_PATH):
        with open(MAPA_PDFS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}
def guardar_mapa_pdfs(mapa):
    with open(MAPA_PDFS_PATH, 'w', encoding='utf-8') as f:
        json.dump(mapa, f, indent=2, ensure_ascii=False)


#-------------------------
# Diccionarios de apoyo
#-------------------------

# Escala softskills
ESCALA_INTERPERSONAL = {
    "muy baja": 1,
    "baja": 2,
    "media": 3,
    "alta": 4,
    "muy alta": 5
}

# Alias de columnas
ALIAS_COLUMNAS = {
    "nombre": "Nombre Completo",
    "edad": "Edad",
    "correo": "Correo Electrónico",
    "estado civil": "Estado civil",
    "telefono": "Teléfono",
    "evaluador": "Evaluador",
    "grado de instruccion": "Grado de Instruccion",
    "fecha de evaluacion": "Fecha de evaluación",
    "carrera": "Carrera",
    "puesto": "Puesto Postulado",
    "nivel": "Nivel de Compatibilidad",
    "experiencia": "Experiencia (años)",
    "áreas": "Áreas de Experiencia",
    "plc": "PLC y Redes Industriales",
    "inglés": "Inglés",
    "proyectos": "Gestión de Proyectos",
    "interdisciplinario": "Trabajo Interdisciplinario",
    "proactividad": "Proactividad y Adaptación",
    "comunicación": "Comunicación",
    "equipo": "Trabajo en Equipo",
    "liderazgo": "Liderazgo",
    "resiliencia": "Resiliencia",
    "comentarios": "Comentarios Generales"
}

#------------------------
# Funciones auxiliares
#------------------------

def mapear_columna(col):
    col_norm = normalizar(col)
    for clave, valor in ALIAS_COLUMNAS.items():
        if clave in col_norm:
            return valor
    return col_norm


def normalizar(texto):
    if not isinstance(texto, str):
        texto = str(texto)
    texto = texto.strip().lower()
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('utf-8')
    return texto

def extraer_numero(nombre):
    match = re.search(r'(\d+)', nombre)
    return int(match.group()) if match else float('inf')

def limpiar_nombre(nombre):
    return re.sub(r'[^\w\s-]', '', nombre).strip().replace(' ', '_')


def descargar_sheet_como_excel(sheet_url, ruta_destino=None):
    try:
        # Extraer ID del documento
        match = re.search(r'/d/([a-zA-Z0-9-_]+)', sheet_url)
        if not match:
            raise ValueError("URL inválida de Google Sheets")

        sheet_id = match.group(1)
        export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"

        # Si no se proporciona una ruta de guardado, genera una única
        if ruta_destino is None:
            nombre_archivo = f"google_sheets_{uuid.uuid4().hex}.xlsx"
            ruta_destino = os.path.join( 'uploads', nombre_archivo)

        # Verificar si ya existe el archivo
        if os.path.exists(ruta_destino):
            print(f"[✓] Google Sheet ya descargado: {ruta_destino}")
            return ruta_destino

        # Descargar y guardar
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(export_url, headers=headers)

        if response.status_code == 200:
            with open(ruta_destino, 'wb') as f:
                f.write(response.content)
            print(f"[✓] Google Sheet descargado en: {ruta_destino}")
            return ruta_destino
        else:
            raise Exception(f"Error al descargar el archivo: {response.status_code}")

    except Exception as e:
        print("Error descargando el archivo de Google Sheets:", e)
        return None


#-------------------------------------
# Funciones para reporte de candidato
#-------------------------------------

def construir_prompt(datos, nombre_candidato):
    prompt = (
        f"Eres un reclutador senior. Redacta una evaluación clara, profesional y natural en español para el candidato {nombre_candidato}. "
        f"El informe debe iniciar con el subtítulo **Evaluación de {nombre_candidato}** y luego cubrir: resumen general, fortalezas, competencias técnicas, competencias interpersonales, experiencia relevante, oportunidades de mejora y una recomendación. "
        "No repitas información que ya esté en la sección de datos personales. No escribas encabezados como 'Evaluación de Selección' salvo el subtítulo mencionado. "
        "Organiza el contenido usando subtítulos marcados con **, por ejemplo: **Fortalezas**. "
        "Evita listas con guiones. El texto debe ser fluido, coherente, y no debe parecer una lista. "
        "Máximo 500 palabras por secciones. Todo debe parecer redactado por un humano con criterio profesional."
    )
    for k, v in datos.items():
        prompt += f"\n{k}: {v}"
    return prompt

def crear_pdf(nombre_archivo, datos_resumen, informe_texto):
    pdf = FPDF()
    pdf.set_left_margin(25)
    pdf.set_right_margin(25)
    pdf.add_page()

    pdf.set_font("Times", "B", 16)
    pdf.cell(0, 10, "INFORME DE EVALUACIÓN DEL CANDIDATO", ln=True, align="C")
    pdf.ln(5)

    pdf.set_font("Times", "B", 12)
    pdf.cell(0, 10, "DATOS PERSONALES", ln=True)

    campos_orden = [
        "Nombre Completo", "Edad", "Estado civil", "Teléfono",
        "Evaluador", "Grado de Instruccion", "Carrera", "Puesto Postulado",
        "Fecha de evaluación", "Correo Electrónico"
    ]

    etiqueta_width = 60
    separador_width = 5
    valor_width = 0

    for campo in campos_orden:
        posibles_keys = [k for k in datos_resumen if campo.lower().strip() in k.lower().strip()]
        if posibles_keys:
            key = posibles_keys[0]
            valor_raw = datos_resumen[key]
            if pd.isna(valor_raw):
                valor = ""
            elif isinstance(valor_raw, float):
                valor = str(int(valor_raw))
            elif isinstance(valor_raw, datetime):
                valor = valor_raw.strftime("%d/%m/%Y")
            else:
                valor = str(valor_raw).strip()

            pdf.set_font("Times", "B", 11)
            pdf.cell(etiqueta_width, 8, campo.upper(), ln=False)
            pdf.cell(separador_width, 8, ":", ln=False)
            pdf.set_font("Times", "", 11)
            pdf.cell(valor_width, 8, valor, ln=True)

    pdf.ln(5)

    secciones = re.split(r'(\*\*[^*]+\*\*)', informe_texto)
    for i, seccion in enumerate(secciones):
        if seccion.startswith("**") and seccion.endswith("**"):
            titulo = seccion.strip("*.").strip().upper()
            pdf.set_font("Times", "B", 12)
            pdf.cell(0, 8, titulo, ln=True)
            pdf.ln(2)

            # Revisión flexible de subtítulo interpersonal
            if any(palabra in titulo.lower() for palabra in ["interpersonales", "habilidades blandas", "soft skills"]):
                nombre_base = limpiar_nombre(nombre_archivo.replace('.pdf', ''))
                nombre_img = f"{nombre_base}_interpersonal.png"
                ruta_img = generar_grafico_interpersonal(datos_resumen, nombre_img)
                if ruta_img and os.path.exists(ruta_img):
                    pdf.image(ruta_img, x=30, w=150)
                    pdf.ln(5)

        else:
            pdf.set_font("Times", "", 11)
            parrafos = seccion.strip().split('\n')
            for parrafo in parrafos:
                if parrafo.strip():
                    pdf.multi_cell(0, 8, parrafo.strip())
                    pdf.ln(1)

    pdf.output(os.path.join(PDF_FOLDER, nombre_archivo))

def generar_grafico_interpersonal(datos, nombre_archivo):
    habilidades = []
    valores = []

    datos_normalizados = {normalizar(k): normalizar(v) for k, v in datos.items()}

    for campo in [
        "Trabajo en Equipo", "Comunicación", "Liderazgo",
        "Resiliencia", "Proactividad y Adaptación"
    ]:
        clave_norm = normalizar(campo)
        if clave_norm in datos_normalizados:
            valor_norm = datos_normalizados[clave_norm]
            if valor_norm in ESCALA_INTERPERSONAL:
                habilidades.append(campo)  # conservar el original con mayúsculas para el gráfico
                valores.append(ESCALA_INTERPERSONAL[valor_norm])

    if habilidades:
        plt.figure(figsize=(6, 3.5))
        bars = plt.barh(habilidades, valores, color='#4A90E2', height=0.4)
        plt.title("Habilidades Blandas", fontsize=12)
        plt.xlim(0, 5.5)
        plt.xticks([1, 2, 3, 4, 5])
        plt.yticks(fontsize=9)
        plt.xlabel("Nivel", fontsize=10)
        plt.grid(axis='x', linestyle='--', alpha=0.6)

        for bar in bars:
            width = bar.get_width()
            plt.text(width + 0.1, bar.get_y() + bar.get_height() / 2, f'{int(width)}', va='center', fontsize=9)

        plt.tight_layout()
        ruta_imagen = os.path.join(CHART_FOLDER, nombre_archivo)
        plt.savefig(ruta_imagen)
        plt.close()
        return ruta_imagen
    return None

def generar_informe_y_pdf(index, fila, usuario_id, empresa_id, origen_documento, nombre_documento_origen, reintentos=3, espera_base=2):
    try:
        datos_candidato = {
            mapear_columna(col): fila[col]
            for col in fila.index
            if pd.notna(fila[col]) and str(fila[col]).strip() != ""
        }

        columna_nombre = next((col for col in fila.index if "nombre" in col.lower()), None)
        nombre_candidato = str(fila[columna_nombre]) if columna_nombre and pd.notna(fila[columna_nombre]) else f"candidato_{index+1}"
        nombre_archivo_pdf = limpiar_nombre(nombre_candidato) + ".pdf"
        ruta_pdf = os.path.join(PDF_FOLDER, nombre_archivo_pdf)

        if os.path.exists(ruta_pdf):
            print(f"{nombre_archivo_pdf} ya existe, será actualizado.")
            os.remove(ruta_pdf)

        print(f"Procesando candidato {index + 1}: {nombre_candidato}")

        datos_prompt = {k: v for k, v in datos_candidato.items() if k not in [
            "Nombre Completo", "Edad", "Estado civil", "Teléfono", "Evaluador", "Grado de Instruccion",
            "Carrera", "Puesto Postulado", "Fecha de evaluación", "Correo Electrónico"]}

        prompt = construir_prompt(datos_prompt, nombre_candidato)
        response = co.generate(
            model="command-r-plus",
            prompt=prompt,
            max_tokens=800,
            temperature=0.4
        )
        informe = response.generations[0].text.strip()

        crear_pdf(nombre_archivo_pdf, datos_candidato, informe)
        print(f"PDF creado: {nombre_archivo_pdf}")

        # Registrar nombre original del candidato
        mapa_actual = cargar_mapa_pdfs()
        mapa_actual[nombre_archivo_pdf] = nombre_candidato
        guardar_mapa_pdfs(mapa_actual)

        dao_reportes.insertar_reporte({
            'nombre_pdf': nombre_archivo_pdf,
            'nombre_candidato': nombre_candidato,
            'es_comparativo': False,
            'nombre_documento_origen': nombre_documento_origen,
            'origen_documento': origen_documento,
            'empresa_id': empresa_id,
            'usuario_id': usuario_id
        })

        return True

    except Exception as e:
        print(f"[Error] Índice {index}: {e}")
        return False


#-------------------------------------
# Funciones para reporte comparativo
#-------------------------------------
def construir_prompt_comparativo(lista_datos):
    prompt = (
       "Eres un reclutador senior con amplia experiencia evaluando candidatos. "
        "Redacta un informe comparativo claro, profesional y natural en español para un grupo de candidatos evaluados. "
        "El informe debe cubrir las siguientes secciones: **Resumen General Comparativo**, **Fortalezas**, **Competencias Técnicas**, **Competencias Interpersonales**, **Experiencia Relevante**, **Oportunidades de Mejora** y una **Recomendación General**.\n\n"

        "En cada sección, **compara directamente el desempeño entre los candidatos**. No te limites a enumerar habilidades o cualidades: **explica quién destaca más, quién tiene un desempeño medio y quién muestra debilidades**, y en qué aspectos concretos. "
        "Utiliza frases como 'el candidato X demuestra un nivel más alto en...', 'en comparación con Y, Z muestra una menor habilidad para...', 'mientras que...', etc. "
        "Haz que el análisis sea claro y útil para tomar decisiones. Evita repeticiones innecesarias y referencias a los datos personales.\n\n"

        "Usa subtítulos marcados con doble asterisco (**), por ejemplo: **Fortalezas**. "
        "No uses listas con guiones; redacta párrafos coherentes, fluidos, y bien estructurados. "
        "Máximo 1000 palabras por sección. "
        "Todo el informe debe parecer escrito por un profesional con criterio experto y lenguaje natural, no por una IA.\n\n"
        "Aquí están los datos relevantes de cada candidato:\n")

    for idx, datos in enumerate(lista_datos, start=1):
        prompt += f"\n\nCandidato {idx}:\n"
        for k, v in datos.items():
            prompt += f"{k}: {v}\n"
    return prompt

def generar_texto_comparativo(prompt):
    try:
        response = co.generate(
            model="command-r-plus",
            prompt=prompt,
            max_tokens=2500,
            temperature=0.7,
            stop_sequences=["--"],
        )
        texto = response.generations[0].text.strip()
        return texto
    except Exception as e:
        print("Error al generar texto comparativo con Cohere:", e)
        return "No se pudo generar el informe comparativo."

def crear_grafico_radar_comparativo(datos_candidatos, nombre_archivo):
    etiquetas = ["Liderazgo", "Comunicación", "Trabajo en equipo", "Resiliencia"]
    etiquetas_norm = [normalizar(e) for e in etiquetas]

    candidatos = list(datos_candidatos.keys())
    valores_por_candidato = []

    # Calcular ángulos antes de cerrar el círculo
    angulos = np.linspace(0, 2 * np.pi, len(etiquetas), endpoint=False).tolist()
    angulos.append(angulos[0])  # cerrar el radar

    for nombre in candidatos:
        datos = datos_candidatos[nombre]
        datos_normalizados = {normalizar(k): normalizar(v) for k, v in datos.items()}
        valores = [
            ESCALA_INTERPERSONAL.get(datos_normalizados.get(etq, ""), 0)
            for etq in etiquetas_norm
        ]
        valores.append(valores[0])  # cerrar el radar
        valores_por_candidato.append(valores)

    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
    colores = ['#FF5733', '#33B5FF', '#8D33FF', '#33FF91', '#FFC733', '#FF33B8']

    for i, valores in enumerate(valores_por_candidato):
        ax.plot(angulos, valores, label=candidatos[i], linewidth=2, color=colores[i % len(colores)])
        ax.fill(angulos, valores, alpha=0.15, color=colores[i % len(colores)])

    ax.set_xticks(angulos[:-1])
    ax.set_xticklabels(etiquetas, fontsize=9)
    ax.set_yticks(range(1, 6))
    ax.set_yticklabels([str(i) for i in range(1, 6)], fontsize=8)
    ax.set_ylim(0, 5)
    plt.title("Comparativa de Competencias Interpersonales", fontsize=13)
    plt.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), fontsize=8)
    plt.tight_layout()

    ruta_imagen = os.path.join(CHART_FOLDER, nombre_archivo)
    plt.savefig(ruta_imagen)
    plt.close()
    return ruta_imagen

def generar_pdf_comparativo(nombre_archivo, seleccionados):
    mapa_nombres = cargar_mapa_pdfs()
    ruta_uploads = os.path.join( 'uploads')
    archivos_excel = [f for f in os.listdir(ruta_uploads) if f.endswith('.xlsx')]

    filas_candidatos = []
    datos_interpersonales = {}

    for archivo_pdf in seleccionados:
        nombre_pdf = os.path.splitext(archivo_pdf)[0].lower()
        nombre_real = mapa_nombres.get(archivo_pdf, None)
        encontrado = False

        if not nombre_real:
            filas_candidatos.append({
                'Nombre': archivo_pdf,
                'Correo': 'No disponible',
                'Teléfono': 'No disponible',
                'Grado de Instruccion': 'No disponible',
                'Estado civil': 'No disponible',
                'Evaluador': 'No disponible',
            })
            continue

        nombre_normalizado = normalizar(nombre_real)

        for archivo_excel in archivos_excel:
            ruta_excel = os.path.join(ruta_uploads, archivo_excel)
            try:
                df = pd.read_excel(ruta_excel)
                nombres_normalizados = df.columns.to_series().apply(mapear_columna)
                df.columns = nombres_normalizados

                nombres_df = df["Nombre Completo"].dropna().astype(str).str.lower().apply(normalizar)
                coincidencias = df[nombres_df.str.contains(nombre_normalizado, na=False)]

                if not coincidencias.empty:
                    fila = coincidencias.iloc[0]
                    fila_dict = {
                        'Nombre': fila.get("Nombre Completo", "No disponible"),
                        'Correo': fila.get("Correo Electrónico", "No disponible"),
                        'Teléfono': fila.get("Teléfono", "No disponible"),
                        'Grado de Instruccion': fila.get("Grado de Instruccion", "No disponible"),
                        'Estado civil': fila.get("Estado civil", "No disponible"),
                        'Evaluador': fila.get("Evaluador", "No disponible"),
                    }

                    datos_interpersonales[fila_dict['Nombre']] = {
                        'Trabajo en Equipo': fila.get("Trabajo en Equipo", ""),
                        'Comunicación': fila.get("Comunicación", ""),
                        'Liderazgo': fila.get("Liderazgo", ""),
                        'Resiliencia': fila.get("Resiliencia", ""),
                        'Proactividad y Adaptación': fila.get("Proactividad y Adaptación", ""),
                    }

                    filas_candidatos.append(fila_dict)
                    encontrado = True
                    break
            except Exception as e:
                print(f"[Error] Procesando {archivo_excel}: {e}")

        if not encontrado:
            filas_candidatos.append({
                'Nombre': nombre_real,
                'Correo': 'No disponible',
                'Teléfono': 'No disponible',
                'Grado de Instruccion': 'No disponible',
                'Estado civil': 'No disponible',
                'Evaluador': 'No disponible',
            })

    # PDF
    pdf = FPDF()
    pdf.set_left_margin(25)
    pdf.set_right_margin(25)
    pdf.add_page()

    pdf.set_font("Times", "B", 16)
    pdf.cell(0, 10, "INFORME COMPARATIVO DE CANDIDATOS", ln=True, align="C")
    pdf.ln(10)

    etiqueta_width = 60
    separador_width = 5
    valor_width = 0

    for i, fila in enumerate(filas_candidatos, start=1):
        pdf.set_font("Times", "B", 12)
        pdf.cell(0, 10, f"CANDIDATO {i}", ln=True)
        pdf.ln(2)

        for campo in ["Nombre", "Correo", "Teléfono", "Grado de Instruccion", "Estado civil", "Evaluador"]:
            valor = str(fila.get(campo, "")).strip()
            pdf.set_font("Times", "B", 11)
            pdf.cell(etiqueta_width, 8, campo.upper(), ln=False)
            pdf.cell(separador_width, 8, ":", ln=False)
            pdf.set_font("Times", "", 11)
            pdf.cell(valor_width, 8, valor, ln=True)

        pdf.ln(5)

    prompt_comparativo = construir_prompt_comparativo(filas_candidatos)
    texto_informe = generar_texto_comparativo(prompt_comparativo)
    secciones = re.split(r'(\*\*[^*]+\*\*)', texto_informe)

    for i, seccion in enumerate(secciones):
        if seccion.startswith("**") and seccion.endswith("**"):
            titulo = seccion.strip("*.").strip().upper()
            pdf.set_font("Times", "B", 12)
            pdf.cell(0, 8, titulo, ln=True)
            pdf.ln(2)

            if any(palabra in titulo.lower() for palabra in ["interpersonales", "habilidades blandas", "soft skills"]):
                nombre_img = f"interpersonal_radar_{uuid.uuid4().hex[:6]}.png"
                ruta_grafico = crear_grafico_radar_comparativo(datos_interpersonales, nombre_img)
                if ruta_grafico and os.path.exists(ruta_grafico):
                    pdf.image(ruta_grafico, w=140)
                    pdf.ln(5)
        else:
            pdf.set_font("Times", "", 11)
            parrafos = seccion.strip().split('\n')
            for parrafo in parrafos:
                if parrafo.strip():
                    pdf.multi_cell(0, 8, parrafo.strip())
                    pdf.ln(1)

    ruta_salida = os.path.join( 'pdfs', nombre_archivo)
    pdf.output(ruta_salida)
    return ruta_salida

#------------------------------------------
# Rutas a diferentes pantallas y procesos 
#------------------------------------------
@app.route('/cargar_data')
def cargar_data():
    return render_template('cargar_data.html')

@app.route('/procesar', methods=['POST'])
def procesar():
    archivo = request.files.get('archivo')
    sheet_url = request.form.get('sheet_url', '').strip()
    df = None

    usuario_id = session.get('user_id')
    empresa_id = dao_usuario.obtener_empresa_id(usuario_id)
    limite_reportes = dao_usuario.obtener_limite(usuario_id)
    reportes_actuales = dao_reportes.contar_reportes_por_empresa(empresa_id)

    # Validar límite ANTES de cargar archivo
    if reportes_actuales >= limite_reportes:
        flash(f"Se alcanzó el límite de reportes ({limite_reportes}) para tu empresa. No se generó ningún informe.", "danger")
        return redirect(url_for('listar_pdfs'))

    # (El resto del código igual, con el ajuste para cortar df si supera el disponible)
    if archivo and archivo.filename:
        nombre_archivo = secure_filename(archivo.filename)
        ruta_guardado = os.path.join(app.config['UPLOAD_FOLDER'], nombre_archivo)
        if not os.path.exists(ruta_guardado):
            archivo.save(ruta_guardado)
            print(f"[✓] Archivo Excel subido: {nombre_archivo}")
        else:
            print(f"[✓] Archivo Excel ya existe: {nombre_archivo}")

        df = pd.read_excel(ruta_guardado)
        origen_documento = 'excel'
        nombre_documento_origen = nombre_archivo

    elif sheet_url:
        if "docs.google.com/spreadsheets" in sheet_url:
            try:
                sheet_id = sheet_url.split('/')[5]
                nombre_documento_origen = sheet_id + '.xlsx'
                ruta_guardado = os.path.join(app.config['UPLOAD_FOLDER'], nombre_documento_origen)

                ruta_excel = descargar_sheet_como_excel(sheet_url, ruta_guardado)
                if ruta_excel is None or not os.path.exists(ruta_excel):
                    flash("No se pudo descargar el archivo desde Google Sheets.", "danger")
                    return redirect(url_for('cargar_data'))

                df = pd.read_excel(ruta_excel)
                print(f"[✓] Google Sheet procesado: {ruta_excel}")
                origen_documento = 'google_sheet'

            except Exception as e:
                flash(f"Error al procesar Google Sheet: {e}", "danger")
                return redirect(url_for('cargar_data'))
        else:
            flash("El enlace proporcionado no es válido para Google Sheets.", "danger")
            return redirect(url_for('cargar_data'))

    else:
        flash("Debe subir un archivo Excel o proporcionar un enlace válido de Google Sheets.", "danger")
        return redirect(url_for('cargar_data'))

    total_a_generar = len(df)
    disponibles = max(0, limite_reportes - reportes_actuales)

    if total_a_generar > disponibles:
        df = df.head(disponibles)
        print(f"Se generarán solo {disponibles} reportes por límite de empresa.")

    print(f"Total filas a procesar: {len(df)}")
    fallidos = []

    with ProcessPoolExecutor(max_workers=8) as executor:
        future_to_index = {
            executor.submit(
                generar_informe_y_pdf,
                idx, fila, usuario_id, empresa_id, origen_documento, nombre_documento_origen
            ): idx for idx, fila in df.iterrows()
        }
        for future in concurrent.futures.as_completed(future_to_index):
            idx = future_to_index[future]
            try:
                if not future.result():
                    fallidos.append((idx, df.iloc[idx]))
            except Exception as e:
                print(f"[Error] Índice {idx} al procesar en paralelo: {e}")
                fallidos.append((idx, df.iloc[idx]))

    if fallidos:
        print(f"Reintentando {len(fallidos)} candidatos fallidos...")
        with ProcessPoolExecutor(max_workers=8) as retry_executor:
            retry_futures = [
                retry_executor.submit(
                    generar_informe_y_pdf,
                    idx, fila, usuario_id, empresa_id, origen_documento, nombre_documento_origen
                ) for idx, fila in fallidos
            ]
            concurrent.futures.wait(retry_futures)

    return redirect(url_for('listar_pdfs'))


@app.route('/pdfs')
def listar_pdfs():
    usuario_id = session.get('user_id')
    if not usuario_id:
        return redirect(url_for('login'))

    # Obtener nombres de PDFs individuales del usuario desde la base de datos
    reportes = dao_reportes.obtener_reportes_individuales_por_usuario(usuario_id)
    nombres_validos = set(r['nombre_pdf'] for r in reportes)

    # Filtrar archivos que existen en la carpeta y están en la lista
    archivos_existentes = os.listdir(PDF_FOLDER)
    archivos = [
        f for f in archivos_existentes
        if f in nombres_validos and f.endswith(".pdf") and not es_reporte_comparativo(f)
    ]
    archivos.sort(key=extraer_numero)

    return render_template('pdfs.html', archivos=archivos)

def redireccionar_segun_origen(origen, pdfs_comparativos=False):
    if origen == 'admin_medio_individual':
        return redirect(url_for('listar_pdfs_admin_medio'))
    elif origen == 'admin_medio_comparativo':
        return redirect(url_for('listar_pdfs_comparativo_admin_medio'))
    else:
        return redirect(url_for('listar_pdfs_comparativos' if pdfs_comparativos else 'listar_pdfs'))


@app.route('/eliminar', methods=['POST'])
def eliminar_multiples():
    seleccionados_str = request.form.get('seleccionados', '')
    origen = request.form.get('origen', '')  # <- Captura el origen

    if not seleccionados_str:
        flash("Debe seleccionar al menos un archivo para eliminar.")
        return redireccionar_segun_origen(origen, pdfs_comparativos=False)

    seleccionados = seleccionados_str.split(',')
    eliminados = []
    no_encontrados = []

    for archivo in seleccionados:
        ruta = os.path.join(app.config['PDF_FOLDER'], archivo)
        if os.path.exists(ruta):
            os.remove(ruta)
            eliminados.append(archivo)

            # Eliminar gráfico asociado
            nombre_base = os.path.splitext(archivo)[0]
            ruta_grafico = os.path.join(app.config['CHART_FOLDER'], f"{nombre_base}_interpersonal.png")
            if os.path.exists(ruta_grafico):
                os.remove(ruta_grafico)

            # Eliminar de la base de datos
            dao_reportes.eliminar_reporte_por_nombre_pdf(archivo)
        else:
            no_encontrados.append(archivo)

    if eliminados:
        flash(f"Archivos eliminados correctamente: {', '.join(eliminados)}")
    if no_encontrados:
        flash(f"No se encontraron los archivos: {', '.join(no_encontrados)}")

    # Redirigir según el tipo y origen
    es_comparativo = any(es_reporte_comparativo(a) for a in eliminados)
    return redireccionar_segun_origen(origen, pdfs_comparativos=es_comparativo)



@app.route('/comparar', methods=['POST'])
def comparar_candidatos():
    seleccionados = request.form.getlist('seleccionados')
    if not (3 <= len(seleccionados) <= 6):
        flash("Debe seleccionar entre 3 y 6 candidatos para generar el informe comparativo.")
        return redirect(url_for('listar_pdfs'))

    empresa_id = session.get('empresa_id')
    if not empresa_id:
        flash("No se pudo identificar la empresa del usuario.")
        return redirect(url_for('listar_pdfs'))

    total_reportes = dao_reportes.contar_reportes_por_empresa(empresa_id)
    limite_reportes = dao_empresas.obtener_limite_reportes(empresa_id)

    if total_reportes >= limite_reportes:
        flash("Se alcanzó el límite de reportes permitidos para esta empresa.")
        return redirect(url_for('listar_pdfs'))

    mapa_nombres = cargar_mapa_pdfs()
    filas_candidatos = []

    for archivo_pdf in seleccionados:
        nombre_candidato = mapa_nombres.get(archivo_pdf, "Nombre Desconocido")
        fila = {
            'Nombre': nombre_candidato,
            'Correo': 'No disponible',
            'Teléfono': 'No disponible',
            'Grado de Instruccion': 'No disponible',
            'Estado civil': 'No disponible',
            'Evaluador': 'No disponible'
        }
        filas_candidatos.append(fila)

    nombre_comparativo = f"Reporte_Comparativo_{uuid.uuid4().hex[:8]}.pdf"
    ruta_pdf = generar_pdf_comparativo(nombre_comparativo, seleccionados)

    dao_reportes.insertar_reporte({
        'nombre_pdf': nombre_comparativo,
        'nombre_candidato': None,
        'es_comparativo': True,
        'nombre_documento_origen': session.get('nombre_documento_origen', ''),
        'origen_documento': session.get('origen_documento', ''),
        'empresa_id': empresa_id,
        'usuario_id': session.get('user_id')
    })

    return redirect(url_for('listar_pdfs_comparativos'))



def es_reporte_comparativo(nombre_archivo):
    return nombre_archivo.startswith("Reporte_Comparativo_")


@app.route('/pdfs/comparativos')
def listar_pdfs_comparativos():
    usuario_id = session.get('user_id')
    if not usuario_id:
        return redirect(url_for('login'))

    # Obtener nombres de PDFs comparativos del usuario desde la base de datos
    reportes = dao_reportes.obtener_reportes_comparativos_por_usuario(usuario_id)
    nombres_validos = set(r['nombre_pdf'] for r in reportes)

    # Filtrar archivos comparativos existentes y válidos
    archivos_existentes = os.listdir(PDF_FOLDER)
    archivos = [
        f for f in archivos_existentes
        if f in nombres_validos and f.endswith(".pdf") and es_reporte_comparativo(f)
    ]
    archivos.sort(key=extraer_numero)

    return render_template('pdfs_comparativos.html', archivos=archivos)


@app.route('/ver_pdf/<nombre>')
def ver_pdf(nombre):
    if not os.path.exists(os.path.join(app.config['PDF_FOLDER'], nombre)):
        abort(404)
    return send_from_directory(app.config['PDF_FOLDER'], nombre)


@app.route('/editar_pdf/<nombre>', methods=['GET', 'POST'])
def editar_pdf(nombre):
    carpeta = app.config['PDF_FOLDER']
    ruta_actual = os.path.join(carpeta, nombre)

    if request.method == 'POST':
        nuevo_nombre = request.form['nuevo_nombre']
        origen = request.form.get('origen', 'pdfs')

        nueva_ruta = os.path.join(carpeta, nuevo_nombre)

        if os.path.exists(ruta_actual) and not os.path.exists(nueva_ruta):
            os.rename(ruta_actual, nueva_ruta)

            # Actualizar en el JSON
            pdf_to_nombre_real = cargar_mapa_pdfs()
            if nombre in pdf_to_nombre_real:
                pdf_to_nombre_real[nuevo_nombre] = pdf_to_nombre_real.pop(nombre)
                guardar_mapa_pdfs(pdf_to_nombre_real)
                print(f"Actualizado en JSON: {nombre} -> {nuevo_nombre}")
            else:
                print(f"Nombre '{nombre}' no encontrado en el JSON.")

            # Actualizar en base de datos
            dao_reportes.actualizar_nombre_pdf(nombre, nuevo_nombre)

        # Redirección según origen
        if origen == 'pdfs_comparativos':
            return redirect(url_for('listar_pdfs_comparativos'))
        elif origen == 'pdfs_comparativo_admin_medio':
            return redirect(url_for('listar_pdfs_comparativo_admin_medio'))
        elif origen == 'pdfs_admin_medio':
            return redirect(url_for('listar_pdfs_admin_medio'))
        else:
            return redirect(url_for('listar_pdfs'))

    else:
        origen = request.args.get('origen', 'pdfs')
        return render_template('editar_nombre.html', nombre_actual=nombre, origen=origen)




@app.route('/descargar_pdf/<nombre>')
def descargar_pdf(nombre):
    if not os.path.exists(os.path.join(app.config['PDF_FOLDER'], nombre)):
        abort(404)
    return send_from_directory(app.config['PDF_FOLDER'], nombre, as_attachment=True)


@app.route('/admin_superior')
def dashboard_admin_superior():
    if session.get('rol') != 'admin_superior':
        return redirect(url_for('login'))
    return render_template('dashboard_admin_superior.html')

#---------------------
# Rutas ADMIN MEDIO
#---------------------

@app.route('/admin_medio')
def vista_admin_medio():
    if session.get('rol') != 'admin_medio':
        return redirect(url_for('login'))

    empresa_id = session.get('empresa_id')
    print(f"[admin_medio] empresa_id en sesión: {empresa_id}")

    try:
        empresa_id = int(empresa_id)
    except:
        print("[admin_medio] empresa_id no es válido")
        return "Error interno: empresa_id inválido", 500

    usuarios = dao_usuario.obtener_usuarios_por_empresa(empresa_id)
    print(f"[admin_medio] Usuarios encontrados: {usuarios}")

    for usuario in usuarios:
        usuario['cantidad_reportes'] = dao_reportes.contar_reportes_por_usuario(usuario['id'])

    return render_template('admin_medio.html', usuarios=usuarios)

@app.route('/admin_medio/agregar', methods=['GET', 'POST'])
def admin_medio_agregar():
    if session.get('rol') != 'admin_medio':
        return redirect(url_for('login'))

    empresa_id = session.get('empresa_id')

    # Validar que haya empresa_id en sesión
    if not empresa_id:
        flash('Error: no se pudo identificar la empresa.', 'danger')
        return redirect(url_for('vista_admin_medio'))

    if request.method == 'POST':
        nombre = request.form['nombre']
        email = request.form['email']
        contrasena = request.form['contrasena']

        # Validar límite de usuarios activos
        limite = dao_empresas.obtener_limite_usuarios(empresa_id)
        actuales = dao_empresas.contar_usuarios_activos(empresa_id)

        if actuales >= limite:
            flash(f'No puedes agregar más usuarios. Límite alcanzado ({limite}).', 'warning')
            return redirect(url_for('vista_admin_medio'))

        dao_usuario.insertar_usuario(nombre, email, contrasena, empresa_id)
        return redirect(url_for('vista_admin_medio'))

    return render_template('agregar_usuario.html')

@app.route('/admin_medio/editar/<int:usuario_id>', methods=['GET', 'POST'])
def admin_medio_editar(usuario_id):
    if session.get('rol') != 'admin_medio':
        return redirect(url_for('login'))

    usuario = dao_usuario.obtener_usuario_por_id(usuario_id)
    if not usuario:
        flash('Usuario no encontrado.', 'danger')
        return redirect(url_for('vista_admin_medio'))

    empresa_id = session.get('empresa_id')
    if not empresa_id:
        flash('Error: no se pudo identificar la empresa.', 'danger')
        return redirect(url_for('vista_admin_medio'))

    if request.method == 'POST':
        nueva_contrasena = request.form['contrasena']
        nuevo_estado_activo = bool(int(request.form['activo']))

        # Si el usuario estaba inactivo y se intenta activar, validar límite
        if not usuario['activo'] and nuevo_estado_activo:
            limite = dao_empresas.obtener_limite_usuarios(empresa_id)
            activos_actuales = dao_empresas.contar_usuarios_activos(empresa_id)
            if activos_actuales >= limite:
                flash(f'No puedes activar este usuario. Límite de usuarios activos alcanzado ({limite}).', 'warning')
                return redirect(url_for('vista_admin_medio'))

        dao_usuario.actualizar_usuario(usuario_id, nueva_contrasena, nuevo_estado_activo)
        flash('Usuario actualizado correctamente', 'success')
        return redirect(url_for('vista_admin_medio'))

    return render_template('editar_usuario.html', usuario=usuario)


@app.route('/admin_medio/eliminar/<int:usuario_id>')
def admin_medio_eliminar(usuario_id):
    if session.get('rol') != 'admin_medio':
        return redirect(url_for('login'))

    dao_reportes.eliminar_reportes_por_usuario(usuario_id)
    dao_usuario.eliminar_usuario(usuario_id)
    flash('Usuario eliminado correctamente', 'success')
    return redirect(url_for('vista_admin_medio'))

@app.route('/pdfs/admin_medio')
def listar_pdfs_admin_medio():
    empresa_id = session.get('empresa_id')
    reportes = dao_reportes.obtener_reportes_individuales_por_empresa(empresa_id)

    nombres_validos = set(r['nombre_pdf'] for r in reportes)
    print("NOMBRES DE ARCHIVOS EN BD:", nombres_validos)

    archivos_existentes = os.listdir(PDF_FOLDER)
    print("ARCHIVOS EN CARPETA:", archivos_existentes)

    archivos = [
        f for f in archivos_existentes
        if f in nombres_validos and f.endswith(".pdf") and not es_reporte_comparativo(f)
    ]
    print("ARCHIVOS FILTRADOS PARA MOSTRAR:", archivos)

    archivos.sort(key=extraer_numero)
    mapa_usuario = {r['nombre_pdf']: r['usuario_email'] for r in reportes}

    return render_template('pdfs_admin_medio.html', archivos=archivos, mapa_usuario=mapa_usuario)


@app.route('/pdfs/admin_medio/comparativos')
def listar_pdfs_comparativo_admin_medio():
    empresa_id = session.get('empresa_id')
    if not empresa_id:
        return redirect(url_for('login'))

    reportes = dao_reportes.obtener_reportes_comparativos_por_empresa(empresa_id)
    nombres_validos = set(r['nombre_pdf'] for r in reportes)

    archivos_existentes = os.listdir(PDF_FOLDER)
    archivos = [
        f for f in archivos_existentes
        if f in nombres_validos and f.endswith(".pdf") and es_reporte_comparativo(f)
    ]
    archivos.sort(key=extraer_numero)

    mapa_usuario = {r['nombre_pdf']: r['usuario_email'] for r in reportes}

    return render_template('pdfs_comparativo_admin_medio.html', archivos=archivos, mapa_usuario=mapa_usuario)


#---------
# Login 
#---------
@app.route('/', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('listar_pdfs')) 

    if request.method == 'POST':
        email = request.form['email']
        contrasena = request.form['contrasena']

        user = dao_usuario.get_user_by_email(email)

        if user and user['contrasena'] == contrasena:
            session['user_id'] = user['id']
            session['user_nombre'] = user['nombre']
            session['rol'] = user['rol']
            session['empresa_id'] = user.get('empresa_id')
            if session['empresa_id'] is None:
                print("[ERROR] empresa_id es None para el usuario:", user)
            session['empresa_nombre'] = dao_empresas.obtener_nombre_empresa(user['empresa_id'])


            print("LOGIN - Sesión iniciada:")
            print("user_id:", session.get('user_id'))
            print("empresa_id:", session.get('empresa_id'))
            print("rol:", session.get('rol'))
            

            if user['rol'] == 'admin_superior':
                return redirect(url_for('dashboard_admin_superior'))
            elif user['rol'] == 'admin_medio':
                return redirect(url_for('vista_admin_medio'))
            else:
                return redirect(url_for('listar_pdfs'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)