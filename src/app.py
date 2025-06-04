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
import io
import numpy as np
import zipfile
import reportlab


from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from flask import Flask, request, render_template, send_from_directory, redirect, url_for, flash, abort, session, send_file
from fpdf import FPDF
from io import BytesIO
from werkzeug.utils import secure_filename
from concurrent.futures import ProcessPoolExecutor
from dotenv import load_dotenv
from datetime import datetime
import matplotlib
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from difflib import SequenceMatcher

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
    "Salario actual":"Salario actual",
    "Pretencion Salarial":"Pretencion Salarial",
    "Disponibilidad":"Disponibilidad",
    "nivel": "Nivel de Compatibilidad",
    "experiencia": "Experiencia (años)",
    "áreas": "Áreas de Experiencia",
    "plc": "PLC y Redes Industriales",
    "inglés": "Inglés",
    "proyectos": "Gestión de Proyectos",
    "interdisciplinario": "Trabajo Interdisciplinario",
    "proactividad": "Proactividad y Adaptación",
    "inte_verbal": "Inteligencia Verbal",
    "inte_matematica": "Inteligencia Matematica",
    "inte_espacial": "Inteligencia Espacial",
    "inte_abstracta": "Inteligencia Abstracta",
    "comunicación": "Comunicación",
    "equipo": "Trabajo en Equipo",
    "liderazgo": "Liderazgo",
    "resiliencia": "Resiliencia",
    "comentarios": "Comentarios Generales"
}


# Campos definidos para cada gráfico
CAMPOS_COMPETENCIAS = [
    ALIAS_COLUMNAS["comunicación"],
    ALIAS_COLUMNAS["equipo"],
    ALIAS_COLUMNAS["liderazgo"],
    ALIAS_COLUMNAS["resiliencia"]
]

CAMPOS_INTELIGENCIAS = [
    ALIAS_COLUMNAS["inte_verbal"],
    ALIAS_COLUMNAS["inte_matematica"],
    ALIAS_COLUMNAS["inte_espacial"],  
    ALIAS_COLUMNAS["inte_abstracta"]
]


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

# Escala softskills
ESCALA_INTERPERSONAL = {
    normalizar("muy baja"): 1,
    normalizar("baja"): 2,
    normalizar("media"): 3,
    normalizar("alta"): 4,
    normalizar("muy alta"): 5
}

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
            ruta_destino = os.path.join('uploads', nombre_archivo)

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

#---------------------------------------------
# Funciones para reporte resumido de candidato
#---------------------------------------------

def construir_prompt_resumido(datos, nombre_candidato):
    nivel_compatibilidad = datos.get("Nivel de Compatibilidad", "").strip().lower()

    recomendaciones = {
        "muy alta": "Altamente recomendable para el puesto postulado.",
        "alta": "Recomendable, con alto potencial de ajuste.",
        "media": "Evaluar con precaución: el ajuste es parcial.",
        "baja": "Limitada adecuación: considerar otros perfiles.",
        "muy baja": "No recomendable según los criterios evaluados."
    }

    recomendacion = recomendaciones.get(nivel_compatibilidad, "Evaluación no concluyente: faltan datos de compatibilidad.")

    prompt = (
        f"Eres un psicólogo organizacional senior. Escribe un informe psicotécnico profesional para el candidato {nombre_candidato}, "
        f"basado en los datos evaluativos proporcionados. El tono debe ser analítico, claro y objetivo. El formato debe ajustarse a una sola hoja (menos de 250 palabras).\n\n"
        f"Estructura el texto en los siguientes bloques, usando títulos en negrita:\n"
        f"**Resumen del Perfil**\n"
        f"**Competencias**\n"
        f"**Inteligencias**\n"
        f"**Personalidad**\n"
        f"**Conclusión**\n"
        f"**Recomendacion**\n\n"
        f"Basado en el nivel de compatibilidad indicado ({datos.get('Nivel de Compatibilidad', '')}), la recomendación es:\n"
        f"{recomendacion}\n\n"
        f"Sé conciso y evita repetir ideas ni enumerar resultados, solo genera texto en parrafos. Usa un estilo profesional, directo y evaluativo.\n\n"
    )

    for k, v in datos.items():
        prompt += f"\n{k}: {v}"

    return prompt



def extraer_bloque(titulo, texto):
    """
    Extrae el contenido de un bloque desde un texto markdown con títulos **titulo**.
    """
    pattern = re.escape(titulo) + r"\s*(.*?)(\n\*\*|$)"
    match = re.search(pattern, texto, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""

def calcular_porcentaje_ajuste(requisito, detalle):
    if not requisito or not detalle:
        return 0
    ratio = SequenceMatcher(None, requisito.lower(), detalle.lower()).ratio()
    return ratio

def convertir_valor(val):
    if val is None:
        return None
    try:
        return float(val)
    except Exception:
        v = normalizar(str(val))
        valor_escala = ESCALA_INTERPERSONAL.get(v)
        if valor_escala is not None:
            return (valor_escala) * 20
        else:
            return None 

def crear_pdf_resumido(nombre_archivo, datos_resumen, informe_texto, graficos=None,
                       usuario_id=None, empresa_id=None, origen_documento=None, nombre_documento_origen=None):
    try:
        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.set_auto_page_break(auto=False)
        pdf.add_page()
        pdf.set_left_margin(10)
        pdf.set_right_margin(10)

        ancho_total = 297 - 20
        altura_maxima = 210 - 20
        x_inicio = 10

        nombre = datos_resumen.get("Nombre Completo", "Candidato")
        edad = datos_resumen.get("Edad")
        estado_civil = datos_resumen.get("Estado civil")
        puesto = datos_resumen.get("Puesto Postulado")

        pdf.set_font("Times", "B", 18)
        pdf.set_xy(x_inicio, 10)
        pdf.cell(0, 10, nombre, ln=True, align="L")

        pdf.set_font("Times", "", 10)
        pdf.set_xy(x_inicio, 20)
        pdf.cell(0, 6, f"Edad: {edad}   |   Estado Civil: {estado_civil}   |   Puesto de Postulacion: {puesto}", ln=True)

        y_cursor = 28
        columna_actual = 0
        ancho_columna = 85
        x_columnas = [10, 105, 200]
        y_columnas = [y_cursor, y_cursor, y_cursor]

        secciones = re.split(r'(\*\*[^*]+\*\*)', informe_texto)
        bloques = []
        for i, parte in enumerate(secciones):
            if parte.startswith("**") and parte.endswith("**"):
                titulo = parte.strip("*").strip().upper()
                texto = secciones[i + 1] if i + 1 < len(secciones) else ""
                bloques.append((titulo, texto.strip()))

        titulos_presentes = [titulo for titulo, _ in bloques]
        if "INFORMACION SALARIAL" not in titulos_presentes:
            bloques.insert(3, ("INFORMACION SALARIAL", ""))

        ajuste_final = 0
        ruta_grafico_conclusiones = None

        for titulo, contenido in bloques:
            pdf.set_font("Times", "B", 11)
            h_titulo = 5
            h_texto = len(contenido.split('\n')) * 5

            h_grafico = 0
            ruta_grafico = None
            if graficos:
                mapa = {"COMPETENCIAS": "blandas", "INTELIGENCIAS": "tecnicas"}
                sufijo = mapa.get(titulo.upper())
                if sufijo:
                    for grafico_path in graficos:
                        if sufijo in grafico_path.lower() and os.path.exists(grafico_path):
                            h_grafico = 45
                            ruta_grafico = grafico_path
                            break

            if titulo == "INFORMACION SALARIAL":
                h_texto = 0
                h_total = h_titulo + (3 * 6) + 2
            elif titulo == "RESUMEN DEL PERFIL":
                h_total = h_titulo + h_texto + 3 * 6 + 12
            else:
                h_total = h_titulo + h_texto + h_grafico + 5

            while columna_actual < 3 and y_columnas[columna_actual] + h_total > altura_maxima:
                columna_actual += 1
            if columna_actual >= 3:
                break

            x_actual = x_columnas[columna_actual]
            y_actual = y_columnas[columna_actual]

            pdf.set_xy(x_actual, y_actual)
            pdf.set_fill_color(200, 220, 255)
            pdf.set_font("Times", "B", 11)
            pdf.multi_cell(ancho_columna, 6, titulo, border=0, fill=True)
            y_actual = pdf.get_y() + 1

            if titulo != "INFORMACION SALARIAL":
                pdf.set_font("Times", "", 9)
                pdf.set_xy(x_actual, y_actual)
                pdf.multi_cell(ancho_columna, 5, contenido)
                y_actual = pdf.get_y() + 2

            if titulo == "RESUMEN DEL PERFIL":
                y_cursor = y_actual + 1
                alto_fila = 6
                ancho_col1 = 32
                ancho_col2 = 40
                ancho_col3 = 12
                altura_encabezado = 8

                pdf.set_draw_color(255, 255, 255)
                pdf.set_fill_color(230, 230, 230)
                pdf.set_text_color(0, 0, 0)
                pdf.set_font("Times", "B", 6)

                pdf.set_xy(x_actual, y_cursor)
                pdf.cell(ancho_col1, altura_encabezado, "Especificación del puesto", border=1, align="C", fill=True, ln=0)
                pdf.cell(ancho_col2, altura_encabezado, "Atributos del candidato", border=1, align="C", fill=True, ln=0)
                pdf.cell(ancho_col3, altura_encabezado, "Ajuste", border=1, align="C", fill=True)

                y_cursor += altura_encabezado
                pdf.set_font("Times", "", 6)

                filas = [
                    ("Formación", datos_resumen.get("Formacion"), datos_resumen.get("grado de instruccion") or datos_resumen.get("Grado de Instruccion")),
                    ("Conocimientos",
                     datos_resumen.get("conocimientos"),
                     " / ".join(filter(None, [
                         datos_resumen.get("PLC y Redes Industriales"),
                         datos_resumen.get("Inglés")
                     ]))),
                    ("Experiencia",
                     datos_resumen.get("experiencias"),
                     " / ".join(filter(None, [
                         datos_resumen.get("Áreas de Experiencia"),
                         str(datos_resumen.get("Experiencia (años)")) if datos_resumen.get("Experiencia (años)") is not None else ""
                     ]))),
                ]

                total_ajuste = 0
                total_items = 0

                for etiqueta, valor_req, valor_det in filas:
                    ajuste = calcular_porcentaje_ajuste(valor_req, valor_det)
                    porcentaje = f"{int(ajuste * 100)}%"

                    total_ajuste += ajuste
                    total_items += 1

                    pdf.set_fill_color(245, 245, 245)
                    pdf.set_text_color(0, 0, 0)

                    pdf.set_xy(x_actual, y_cursor)
                    pdf.cell(ancho_col1, alto_fila, f"{etiqueta}", border=1, align="C", fill=True, ln=0)

                    x_det = x_actual + ancho_col1
                    pdf.set_xy(x_det, y_cursor)
                    pdf.cell(ancho_col2, alto_fila, valor_det or "", border=1, align="C", fill=True, ln=0)

                    x_ajuste = x_actual + ancho_col1 + ancho_col2
                    pdf.set_xy(x_ajuste, y_cursor)
                    pdf.cell(ancho_col3, alto_fila, porcentaje, border=1, align="C", fill=True)

                    y_cursor += alto_fila

                ajuste_final = int((total_ajuste / total_items) * 100) if total_items else 0
                pdf.set_xy(x_actual, y_cursor)
                pdf.set_font("Times", "B", 7)
                pdf.set_fill_color(230, 230, 230)
                pdf.cell(ancho_col1 + ancho_col2, alto_fila, "Porcentaje total de ajuste", border=1, align="C", fill=True, ln=0)
                pdf.cell(ancho_col3, alto_fila, f"{ajuste_final}%", border=1, align="C", fill=True)
                y_actual = y_cursor + alto_fila + 2

            elif titulo == "INFORMACION SALARIAL":
                alto_fila = 6
                ancho_col1 = 42
                ancho_col2 = 42

                filas_salariales = [
                    ("Sueldo actual/último", datos_resumen.get("salario actual")),
                    ("Expectativa salarial", datos_resumen.get("pretencion salarial")),
                    ("Disponibilidad", datos_resumen.get("disponibilidad")),
                ]

                pdf.set_draw_color(255, 255, 255)
                pdf.set_text_color(0, 0, 0)

                for i, (label, valor) in enumerate(filas_salariales):
                    y_fila = y_actual + i * alto_fila

                    pdf.set_fill_color(200, 200, 200)
                    pdf.set_xy(x_actual, y_fila)
                    pdf.set_font("Times", "B", 6)
                    pdf.cell(ancho_col1, alto_fila, label, border=1, align="C", fill=True)

                    pdf.set_fill_color(240, 240, 240)
                    pdf.set_xy(x_actual + ancho_col1, y_fila)
                    pdf.set_font("Times", "", 6)
                    pdf.cell(ancho_col2, alto_fila, str(valor) if valor is not None else "", border=1, align="C", fill=True)

                y_actual += alto_fila * len(filas_salariales) + 2

            if ruta_grafico:
                pdf.image(ruta_grafico, x=x_actual, y=y_actual, w=ancho_columna - 5)
                y_actual += h_grafico + 2
            else:
                y_actual += 3

            if titulo == "CONCLUSIÓN":
                competencias_raw = {k: datos_resumen[k] for k in CAMPOS_COMPETENCIAS if k in datos_resumen}
                inteligencias_raw = {k: v for k, v in datos_resumen.items() if k.lower().startswith("inteligencia")}

                promedio_competencias = sum(convertir_valor(v) for v in competencias_raw.values()) / len(competencias_raw) if competencias_raw else 0
                promedio_inteligencias = sum(convertir_valor(v) for v in inteligencias_raw.values()) / len(inteligencias_raw) if inteligencias_raw else 0
                porcentaje_personalidad = estimar_porcentaje_personalidad(contenido)
                ajuste_final = 70

                resumen_conclusiones = {
                    "Ajuste al Puesto": ajuste_final,
                    "Competencias": int(promedio_competencias),
                    "Inteligencias": int(promedio_inteligencias),
                    "Perfil de Personalidad": porcentaje_personalidad
                }
                nombre_grafico = f"conclusiones_{nombre_archivo.replace('.pdf', '.png')}"
                ruta_grafico_conclusiones = generar_grafico_barras(resumen_conclusiones, list(resumen_conclusiones.keys()), "Resumen General", nombre_grafico)

                if ruta_grafico_conclusiones and os.path.exists(ruta_grafico_conclusiones):
                    alto_grafico_conclusiones = 45
                    if y_actual + alto_grafico_conclusiones > altura_maxima:
                        columna_actual += 1
                        if columna_actual >= 3:
                            pdf.add_page()
                            y_columnas = [28, 28, 28]  # valor inicial según tu y_cursor
                            columna_actual = 0
                        x_actual = x_columnas[columna_actual]
                        y_actual = y_columnas[columna_actual]

                    pdf.image(ruta_grafico_conclusiones, x=x_actual, y=y_actual, w=ancho_columna - 5)
                    y_actual += alto_grafico_conclusiones

            y_columnas[columna_actual] = y_actual

        ruta_final = os.path.join(PDF_FOLDER, nombre_archivo)
        pdf.output(ruta_final)

        nombre_candidato = nombre or limpiar_nombre(nombre_archivo.replace("_resumido.pdf", ""))
        dao_reportes.insertar_reporte({
            'nombre_pdf': nombre_archivo,
            'nombre_candidato': nombre_candidato,
            'tipo_reporte': 'resumido',
            'nombre_documento_origen': nombre_documento_origen,
            'origen_documento': origen_documento,
            'empresa_id': empresa_id,
            'usuario_id': usuario_id
        })

        if graficos:
            for grafico in graficos:
                if os.path.exists(grafico):
                    os.remove(grafico)
        if ruta_grafico_conclusiones and os.path.exists(ruta_grafico_conclusiones):
            os.remove(ruta_grafico_conclusiones)

        print(f"PDF resumido generado correctamente: {nombre_archivo}")
        return True

    except Exception as e:
        print(f"[Error al crear PDF resumido] {e}")
        return False


def estimar_porcentaje_personalidad(texto_personalidad):
    if not texto_personalidad:
        return 50
    texto = texto_personalidad.lower()
    niveles = {
        "muy alta": 100,
        "alta": 80,
        "media": 60,
        "baja": 40,
        "muy baja": 20
    }
    for nivel, valor in niveles.items():
        if nivel in texto:
            return valor
    palabras_clave = ["positivo", "estable", "proactivo", "flexible", "sociable"]
    puntaje = sum(1 for palabra in palabras_clave if palabra in texto)
    return min(100, 50 + puntaje * 10)


def generar_reporte_resumido(index, fila, usuario_id, empresa_id, origen_documento, nombre_documento_origen, reintentos=3, espera_base=2):
    try:
        # Extraer datos relevantes del candidato
        datos_candidato = {
            mapear_columna(col): fila[col]
            for col in fila.index
            if pd.notna(fila[col]) and str(fila[col]).strip() != ""
        }

        # Obtener nombre candidato para el archivo y título
        columna_nombre = next((col for col in fila.index if "nombre" in col.lower()), None)
        nombre_candidato = str(fila[columna_nombre]) if columna_nombre and pd.notna(fila[columna_nombre]) else f"candidato_{index+1}"
        nombre_archivo_pdf = limpiar_nombre(nombre_candidato) + "_resumido.pdf"
        ruta_pdf = os.path.join(PDF_FOLDER, nombre_archivo_pdf)

        # Si ya existe el pdf, eliminar para actualizar
        if os.path.exists(ruta_pdf):
            print(f"{nombre_archivo_pdf} ya existe, será actualizado.")
            os.remove(ruta_pdf)

        print(f"Procesando reporte psicotécnico resumido candidato {index + 1}: {nombre_candidato}")

        # Construir prompt específico para reporte resumido
        prompt = construir_prompt_resumido(datos_candidato, nombre_candidato)

        # Llamada a la API de generación (Cohere u otra)
        response = co.generate(
            model="command-r-plus",
            prompt=prompt,
            max_tokens=600,
            temperature=0.4
        )
        informe = response.generations[0].text.strip()

        # Generar gráficos si quieres (puedes definir qué campos graficar)
        graficos = []
        try:
            # Ejemplo: graficar competencias blandas y habilidades técnicas
            competencias_blandas = [
                "Comunicación", "Trabajo en equipo", "Liderazgo",
                "Resiliencia"
            ]
            habilidades_tecnicas = [
                "Inteligencia Verbal", "Inteligencia Matematica", "Inteligencia Espacial",
                "Inteligencia Abstracta"
            ]

            grafico_blandas = generar_grafico_barras(datos_candidato, competencias_blandas,
                                                    "Competencias", f"{limpiar_nombre(nombre_candidato)}_blandas.png", usar_escala=True)
            grafico_tecnicas = generar_grafico_barras(datos_candidato, habilidades_tecnicas,
                                                     "Inteligencias", f"{limpiar_nombre(nombre_candidato)}_tecnicas.png", usar_escala=False)

            if grafico_blandas:
                graficos.append(grafico_blandas)
            if grafico_tecnicas:
                graficos.append(grafico_tecnicas)
        except Exception as e:
            print(f"[Aviso] No se pudieron generar gráficos para {nombre_candidato}: {e}")

        # Crear PDF resumido con texto y gráficos
        exito_pdf = crear_pdf_resumido(nombre_archivo_pdf, datos_candidato, informe, graficos,
                                       usuario_id, empresa_id, origen_documento, nombre_documento_origen)
        if not exito_pdf:
            print(f"[Error] No se pudo crear PDF resumido para {nombre_candidato}")
            return False

        return True

    except Exception as e:
        print(f"[Error] Índice {index} - reporte resumido: {e}")
        return False



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

    pdf.set_fill_color(220, 230, 250)  # azul claro
    pdf.set_text_color(0, 0, 0)        # texto negro
    pdf.set_font("Times", "B", 12)
    pdf.cell(0, 10, "DATOS PERSONALES", ln=True, fill=True)
    pdf.ln(2)

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


            if "EVALUACIÓN DE " in titulo:
                continue

            # Fondo azul claro para subtítulos
            pdf.set_fill_color(220, 230, 250)
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Times", "B", 12)
            pdf.cell(0, 10, titulo, ln=True, fill=True)
            pdf.ln(2)

            # Si es sección interpersonal, incluir gráfico
            if any(palabra in titulo.lower() for palabra in ["interpersonales", "habilidades blandas", "soft skills"]):
                nombre_base = limpiar_nombre(nombre_archivo.replace('.pdf', ''))
                nombre_img = f"{nombre_base}_interpersonal.png"

                campos_interpersonales = [
                    "Comunicación", "Trabajo en equipo", "Liderazgo", "Resiliencia"
                ]

                ruta_img = generar_grafico_barras(
                    datos_resumen,
                    campos_interpersonales,
                    titulo,
                    nombre_img,
                    usar_escala=True,
                    escala=ESCALA_INTERPERSONAL
                )

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



def generar_grafico_barras(datos, campos, titulo, nombre_archivo, usar_escala=False, escala=ESCALA_INTERPERSONAL):
    etiquetas = []
    valores = []

    datos_normalizados = {normalizar(k): v for k, v in datos.items()}

    for campo in campos:
        clave_norm = normalizar(campo)
        for k, v in datos.items():
            if normalizar(k) == clave_norm:
                valor = v
                if usar_escala:
                    valor_norm = normalizar(str(valor))
                    if valor_norm in escala:
                        etiquetas.append(campo)
                        valores.append(escala[valor_norm])
                else:
                    try:
                        valores.append(float(valor))
                        etiquetas.append(campo)
                    except ValueError:
                        pass
                break  # Ya se encontró este campo

    if etiquetas and valores:
        plt.figure(figsize=(6, 3.5))
        bars = plt.barh(etiquetas, valores, color='#4A90E2', height=0.4)
        plt.title(titulo, fontsize=12)

        if usar_escala:
            plt.xlim(0, 5.5)
            plt.xticks([1, 2, 3, 4, 5])
            plt.xlabel("Nivel", fontsize=10)
        else:
            max_val = max(valores + [100])  # En caso de que quieras asegurar 100% si son porcentajes
            plt.xlim(0, max_val * 1.1)
            plt.xlabel("Puntaje", fontsize=10)

        plt.yticks(fontsize=9)
        plt.grid(axis='x', linestyle='--', alpha=0.6)

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

        mapa_actual = cargar_mapa_pdfs()
        mapa_actual[nombre_archivo_pdf] = nombre_candidato
        guardar_mapa_pdfs(mapa_actual)

        dao_reportes.insertar_reporte({
            'nombre_pdf': nombre_archivo_pdf,
            'nombre_candidato': nombre_candidato,
            'tipo_reporte': 'individual',
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

def crear_grafico_barras_comparativo(datos_candidatos, nombre_archivo):
    etiquetas = ["Liderazgo", "Comunicación", "Trabajo en equipo", "Resiliencia"]
    etiquetas_norm = [normalizar(e) for e in etiquetas]

    candidatos = list(datos_candidatos.keys())
    colores = ['#FF5733', '#33B5FF', '#8D33FF', '#33FF91', '#FFC733', '#FF33B8']

    valores_por_competencia = []

    for etq in etiquetas_norm:
        valores = []
        for nombre in candidatos:
            datos = datos_candidatos[nombre]
            datos_claves_normalizadas = {normalizar(k): v for k, v in datos.items()}

            if etq not in datos_claves_normalizadas:
                print(f"[ERROR] Competencia no encontrada: '{etq}' en candidato {nombre}")
                print(f"DEBUG - claves: {list(datos_claves_normalizadas.keys())}")

            valor = datos_claves_normalizadas.get(etq, 0)
            if not isinstance(valor, (int, float)):
                print(f"[ADVERTENCIA] Valor no numérico '{valor}' para '{etq}' en candidato {nombre}")
                valor = 0
            valores.append(valor)

        valores_por_competencia.append(valores)

    x = np.arange(len(etiquetas))
    width = 0.8 / len(candidatos)

    fig, ax = plt.subplots(figsize=(10, 6))

    for i, nombre in enumerate(candidatos):
        desplazamiento = (i - len(candidatos)/2) * width + width/2
        valores = [valores_por_competencia[j][i] for j in range(len(etiquetas))]
        ax.bar(x + desplazamiento, valores, width, label=nombre, color=colores[i % len(colores)])

    ax.set_ylabel('Nivel')
    ax.set_title('Comparativa de Competencias Interpersonales')
    ax.set_xticks(x)
    ax.set_xticklabels(etiquetas, fontsize=9)
    ax.set_ylim(0, 5)
    ax.legend(loc='upper right', fontsize=8)
    plt.tight_layout()

    ruta_imagen = os.path.join(CHART_FOLDER, nombre_archivo)
    plt.savefig(ruta_imagen)
    plt.close()
    return ruta_imagen

def valor_escalar(etiqueta, valor_raw, nombre_candidato):
    val_str = str(valor_raw).strip().lower()
    print(f"DEBUG valor_escalar: etiqueta='{etiqueta}', valor_raw='{valor_raw}', val_str='{val_str}' para candidato '{nombre_candidato}'")
    if val_str not in ESCALA_INTERPERSONAL:
        print(f"[ADVERTENCIA] Valor desconocido '{val_str}' para '{etiqueta}' en candidato {nombre_candidato} (original: '{valor_raw}')")
        return 3  # Valor por defecto
    return ESCALA_INTERPERSONAL[val_str]

def generar_pdf_comparativo(nombre_archivo, seleccionados):

    mapa_nombres = cargar_mapa_pdfs()
    ruta_uploads = os.path.join('uploads')
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
                        'Trabajo en Equipo': valor_escalar("Trabajo en Equipo", fila.get("Trabajo en Equipo", ""), fila_dict['Nombre']),
                        'comunicacion': valor_escalar("comunicacion", fila.get("comunicacion", ""), fila_dict['Nombre']),
                        'Liderazgo': valor_escalar("Liderazgo", fila.get("Liderazgo", ""), fila_dict['Nombre']),
                        'Resiliencia': valor_escalar("Resiliencia", fila.get("Resiliencia", ""), fila_dict['Nombre']),
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
        pdf.set_fill_color(220, 230, 250)  
        pdf.set_text_color(0, 0, 0)        
        pdf.set_font("Times", "B", 12)
        pdf.cell(0, 10, f"CANDIDATO {i}", ln=True, fill=True)
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

            if "INFORME COMPARATIVO DE CANDIDATOS" in titulo:
                continue  

            pdf.set_fill_color(220, 230, 250)  
            pdf.set_text_color(0, 0, 0)        
            pdf.set_font("Times", "B", 12)
            pdf.cell(0, 10, titulo, ln=True, fill=True)
            pdf.ln(2)


            if any(palabra in titulo.lower() for palabra in ["interpersonales", "habilidades blandas", "soft skills"]):
                nombre_img = f"interpersonal_radar_{uuid.uuid4().hex[:6]}.png"
                ruta_grafico = crear_grafico_barras_comparativo(datos_interpersonales, nombre_img)
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

    ruta_salida = os.path.join('pdfs', nombre_archivo)
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
    tipo_reporte = request.form.get('tipo_reporte')
    df = None

    usuario_id = session.get('user_id')
    empresa_id = dao_usuario.obtener_empresa_id(usuario_id)
    limite_reportes = dao_usuario.obtener_limite(usuario_id)
    reportes_actuales = dao_reportes.contar_reportes_por_empresa(empresa_id)

    if reportes_actuales >= limite_reportes:
        flash(f"Se alcanzó el límite de reportes ({limite_reportes}) para tu empresa. No se generó ningún informe.", "danger")
        return redirect(url_for('listar_pdfs'))

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

    # Selección de función de generación
    if tipo_reporte == 'clinico':
        generador = generar_informe_y_pdf
    elif tipo_reporte == 'psicotecnico':  
        generador = generar_reporte_resumido
    else:
        flash("Tipo de reporte no válido.", "danger")
        return redirect(url_for('cargar_data'))

    with ProcessPoolExecutor(max_workers=8) as executor:
        future_to_index = {
            executor.submit(
                generador,
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
                    generador,
                    idx, fila, usuario_id, empresa_id, origen_documento, nombre_documento_origen
                ) for idx, fila in fallidos
            ]
            concurrent.futures.wait(retry_futures)

    if tipo_reporte == 'clinico':
        return redirect(url_for('listar_pdfs'))
    elif tipo_reporte == 'psicotecnico':
        return redirect(url_for('listar_pdfs_resumidos'))


def es_reporte_comparativo(nombre_archivo):
    return nombre_archivo.startswith("Reporte_Comparativo_")

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
    elif origen == 'admin_medio_resumidos':
        return redirect(url_for('listar_pdfs_resumidos_admin_medio'))
    elif origen == 'resumidos':
        return redirect(url_for('listar_pdfs_resumidos'))
    else:
        return redirect(url_for('listar_pdfs_comparativos' if pdfs_comparativos else 'listar_pdfs'))


@app.route('/pdfs_resumidos')
def listar_pdfs_resumidos():
    usuario_id = session.get('user_id')
    if not usuario_id:
        return redirect(url_for('login'))

    # Obtener nombres de PDFs resumidos del usuario desde la base de datos
    reportes = dao_reportes.obtener_reportes_resumidos_por_usuario(usuario_id)
    nombres_validos = set(r['nombre_pdf'] for r in reportes if r['nombre_pdf'])

    archivos_existentes = os.listdir(PDF_FOLDER)
    archivos = [
        f for f in archivos_existentes
        if f in nombres_validos and f.endswith(".pdf") and not es_reporte_comparativo(f)
    ]
    archivos.sort(key=extraer_numero)

    return render_template('pdfs_resumidos.html', archivos=archivos)

@app.route('/pdfs_resumidos_admin_medio')
def listar_pdfs_resumidos_admin_medio():
    usuario_id = session.get('user_id')
    if not usuario_id:
        return redirect(url_for('login'))

    empresa_id = dao_usuario.obtener_empresa_id(usuario_id)

    # Obtener todos los reportes tipo 'resumido' de la empresa
    reportes = dao_reportes.obtener_reportes_resumidos_por_empresa(empresa_id)
    nombres_validos = set(r['nombre_pdf'] for r in reportes if r['nombre_pdf'])

    # Mapa archivo -> nombre usuario
    mapa_usuario = {
        r['nombre_pdf']: r['nombre_usuario'] if r.get('nombre_usuario') else "Desconocido"
        for r in reportes
    }

    archivos_existentes = os.listdir(PDF_FOLDER)
    archivos = [
        f for f in archivos_existentes
        if f in nombres_validos and f.endswith(".pdf") and not es_reporte_comparativo(f)
    ]
    archivos.sort(key=extraer_numero)

    return render_template('pdfs_resumidos_admin_medio.html', archivos=archivos, mapa_usuario=mapa_usuario)


@app.route('/descargar_multiples', methods=['POST'])
def descargar_multiples():
    seleccionados_str = request.form.get('seleccionados_descarga', '')
    if not seleccionados_str:
        flash("Debe seleccionar al menos un archivo para descargar.")
        return redirect(url_for('listar_pdfs'))

    seleccionados = seleccionados_str.split(',')

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zipf:
        for nombre_archivo in seleccionados:
            ruta_archivo = os.path.join(app.config['PDF_FOLDER'], nombre_archivo)
            if os.path.exists(ruta_archivo):
                zipf.write(ruta_archivo, arcname=nombre_archivo)

    zip_buffer.seek(0)

    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name='reportes_seleccionados.zip'
    )


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
        'tipo_reporte': 'comparativo',
        'nombre_documento_origen': session.get('nombre_documento_origen', ''),
        'origen_documento': session.get('origen_documento', ''),
        'empresa_id': empresa_id,
        'usuario_id': session.get('user_id')
    })

    return redirect(url_for('listar_pdfs_comparativos'))




@app.route('/pdfs/comparativos')
def listar_pdfs_comparativos():
    usuario_id = session.get('user_id')
    if not usuario_id:
        return redirect(url_for('login'))
    reportes = dao_reportes.obtener_reportes_comparativos_por_usuario(usuario_id)
    nombres_validos = set(r['nombre_pdf'] for r in reportes)
    archivos_existentes = os.listdir(PDF_FOLDER)
    archivos = [
        f for f in archivos_existentes
        if f in nombres_validos and f.endswith(".pdf")
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
        print(f"Origen recibido: {origen}")


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
        elif origen == 'pdfs_resumidos_admin_medio':
            return redirect(url_for('listar_pdfs_resumidos_admin_medio'))
        elif origen == 'pdfs_resumidos':
            return redirect(url_for('listar_pdfs_resumidos'))
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
def vista_admin_superior():
    try:
        empresas_con_datos = dao_empresas.obtener_todas_las_empresas_con_datos(dao_reportes)
        return render_template('admin_superior.html', empresas=empresas_con_datos)
    except Exception as e:
        print(f"[vista_admin_superior] Error: {e}")
        return "Error al cargar datos de empresas"
    
@app.route('/admin_superior/nueva_empresa', methods=['GET', 'POST'])
def nueva_empresa():
    if session.get('rol') != 'admin_superior':
        return redirect(url_for('login'))

    if request.method == 'POST':
        nombre_empresa = request.form['nombre'].strip()
        nombre_admin = request.form['nombre_admin'].strip()
        correo_admin = request.form['correo_admin'].strip()
        contrasena_admin = request.form['contrasena_admin']
        plan = request.form['plan']

        try:
            limite_usuarios = int(request.form['limite_usuarios'])
            limite_reportes = int(request.form['limite_reportes'])
        except ValueError:
            flash("Los límites deben ser números enteros válidos.", "danger")
            return render_template('nueva_empresa.html')

        if not nombre_empresa or not nombre_admin or not correo_admin or not contrasena_admin or not plan:
            flash("Todos los campos son obligatorios.", "danger")
            return render_template('nueva_empresa.html')

        try:
            # Crear empresa
            empresa_id = dao_empresas.crear_empresa_y_retornar_id(nombre_empresa, plan, limite_usuarios, limite_reportes)

            # Crear administrador medio
            dao_usuario.insertar_usuario(nombre_admin, correo_admin, contrasena_admin, empresa_id, rol='admin_medio')

            flash("Empresa y administrador creados exitosamente", "success")
            return redirect(url_for('vista_admin_superior'))

        except Exception as e:
            flash(f"Error al crear empresa: {e}", "danger")
            return render_template('nueva_empresa.html')

    return render_template('nueva_empresa.html')



@app.route('/admin_superior/editar_empresa/<int:empresa_id>', methods=['GET', 'POST'])
def editar_empresa(empresa_id):
    if session.get('rol') != 'admin_superior':
        return redirect(url_for('login'))

    empresa = dao_empresas.obtener_empresa_por_id(empresa_id)
    admin = dao_usuario.obtener_admin_medio_por_empresa(empresa_id)

    if not empresa or not admin:
        flash("Empresa o administrador no encontrados.", "danger")
        return redirect(url_for('vista_admin_superior'))

    if request.method == 'POST':
        nombre_empresa = request.form['nombre'].strip()
        nombre_admin = request.form['nombre_admin'].strip()
        correo_admin = request.form['correo_admin'].strip()
        contrasena_admin = request.form['contrasena_admin']
        plan = request.form['plan']

        try:
            limite_usuarios = int(request.form['limite_usuarios'])
            limite_reportes = int(request.form['limite_reportes'])
        except ValueError:
            flash("Los límites deben ser números enteros válidos.", "danger")
            return render_template('editar_empresa.html', empresa=empresa, admin=admin)

        if not nombre_empresa or not correo_admin or not nombre_admin:
            flash("Todos los campos son obligatorios.", "danger")
            return render_template('editar_empresa.html', empresa=empresa, admin=admin)

        empresa['nombre'] = nombre_empresa
        empresa['plan'] = plan
        empresa['limite_usuarios'] = limite_usuarios
        empresa['limite_reportes'] = limite_reportes

        dao_empresas.actualizar_empresa(empresa)

        # Actualiza el administrador
        activo = True  # por defecto
        if contrasena_admin:
            dao_usuario.actualizar_usuario(admin['id'], contrasena_admin, activo)

        dao_usuario.actualizar_datos_admin_medio(admin['id'], nombre_admin, correo_admin)

        flash("Empresa y administrador actualizados.", "success")
        return redirect(url_for('vista_admin_superior'))

    return render_template('editar_empresa.html', empresa=empresa, admin=admin)



@app.route('/gestion_planes')
def gestion_planes():
    return render_template('planes_admin_superior.html')




#---------------------
# Rutas ADMIN MEDIO
#---------------------

@app.route('/admin_medio')
def vista_admin_medio():
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return redirect("/")

    dao_empresas = DAOEmpresas()
    dao_reportes = DAOReportes()

    empresa_id = dao_empresas.obtener_empresa_id_por_usuario(usuario_id)
    usuarios = dao_empresas.obtener_usuarios_por_empresa(empresa_id)

    usuarios_con_datos = []
    for row in usuarios:
        usuario = dict(row)  # Convertimos el DictRow en un diccionario normal
        usuario['cantidad_reportes'] = dao_reportes.contar_reportes_por_usuario(usuario['id'])
        usuarios_con_datos.append(usuario)

    return render_template('admin_medio.html', usuarios=usuarios_con_datos)


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
                return redirect(url_for('vista_admin_superior'))
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
