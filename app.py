from flask import Flask, request, render_template
from werkzeug.utils import secure_filename
import pandas as pd
import os
import json
from datetime import datetime, timedelta
import smtplib
from email.message import EmailMessage
import re

# Configuración general
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'json'}

# Configuración del correo
REMITENTE = "terastreocl@gmail.com"
CLAVE_APP = "owei lbzk inms cvqn"

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Verifica que el archivo sea .json
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Define el rango del mes anterior
def get_previous_month_range():
    today = datetime.today()
    first_day_this_month = datetime(today.year, today.month, 1)
    last_day_prev_month = first_day_this_month - timedelta(days=1)
    first_day_prev_month = datetime(last_day_prev_month.year, last_day_prev_month.month, 1)
    return first_day_prev_month, last_day_prev_month

# Extrae coordenadas de un string como "-38.111111,-72.222222"
def extraer_coordenadas(texto):
    if not texto:
        return "", ""
    match = re.search(r'(-?\d+\.\d+),\s*(-?\d+\.\d+)', texto)
    return (match.group(1), match.group(2)) if match else ("", "")

# Busca un valor en un diccionario anidado
def obtener_valor_seguro(diccionario, ruta):
    try:
        for clave in ruta:
            diccionario = diccionario[clave]
        return diccionario
    except (KeyError, TypeError):
        return ""

# Valida el formato de código SEREMI
def es_codigo_seremi_valido(valor):
    return bool(re.match(r"^(CTR|CTA|CTE)\d{4}$", valor or "", re.IGNORECASE))

# Valida formato de patente: 4 letras + 2 números (ej: ABCD12)
def es_patente_valida(valor):
    return bool(re.match(r"^[A-Z]{4}\d{2}$", valor or "", re.IGNORECASE))

# Envía el archivo por correo
def enviar_email_con_archivo(destinatario, archivo_adjunto):
    msg = EmailMessage()
    msg["Subject"] = "Reporte mensual de rastreo GPS"
    msg["From"] = REMITENTE
    msg["To"] = REMITENTE
    msg["Cc"] = destinatario
    msg.set_content("Gracias, tu archivo fue procesado con éxito y enviado por correo.")

    with open(archivo_adjunto, "rb") as f:
        datos = f.read()
        nombre = os.path.basename(archivo_adjunto)
        msg.add_attachment(datos, maintype="application", subtype="octet-stream", filename=nombre)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(REMITENTE, CLAVE_APP)
        smtp.send_message(msg)

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files or 'email' not in request.form:
            return "Falta archivo o correo", 400

        file = request.files['file']
        email = request.form['email']

        if file.filename == '' or not allowed_file(file.filename):
            return "Archivo inválido", 400

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Carga JSON
        with open(filepath, "r", encoding="utf-8") as f:
            contenido = json.load(f)

        tablas = contenido.get("items", [])
        for tabla in tablas:
            rows = tabla.get("table", {}).get("rows", [])
            if not rows:
                continue

            df = pd.DataFrame(rows)
            if 'start_at' not in df.columns:
                continue

            # Filtra por mes anterior
            df['start_at'] = pd.to_datetime(df['start_at'], errors='coerce')
            inicio, fin = get_previous_month_range()
            df_filtrado = df[(df['start_at'] >= inicio) & (df['start_at'] <= fin)]

            if df_filtrado.empty:
                continue

            # Extrae coordenadas desde location_start
            df_filtrado[['GPS_Latitud', 'GPS_Longitud']] = df_filtrado['location_start'].apply(lambda x: pd.Series(extraer_coordenadas(x)))

            # Extrae campos obligatorios del meta
            meta = tabla.get("meta", {})
            id_servicio = next(
                (v for v in meta.values() if isinstance(v, dict) and es_codigo_seremi_valido(v.get("value"))),
                {}
            ).get("value")

            ppu = next(
                (v for v in meta.values() if isinstance(v, dict) and es_patente_valida(v.get("value"))),
                {}
            ).get("value")

            imei = obtener_valor_seguro(meta, ["device.imei", "value"])

            # Completa columnas
            df_filtrado['ID_Servicio'] = id_servicio
            df_filtrado['GPS_IMEI'] = imei
            df_filtrado['PPU'] = ppu
            df_filtrado['GPS_Fecha_Hora_Chile'] = df_filtrado['start_at'].dt.strftime("%Y-%m-%d %H:%M:%S")

            # Define columnas finales
            columnas_finales = ['ID_Servicio', 'GPS_IMEI', 'PPU', 'GPS_Fecha_Hora_Chile', 'GPS_Latitud', 'GPS_Longitud']
            df_export = df_filtrado[columnas_finales]

            # Nombre archivo: reporte_<PPU>_<mesAño>.csv
            nombre_mes = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                          "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"][inicio.month - 1]
            output_filename = f"reporte_{ppu}_{nombre_mes}{inicio.year}.csv"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
            df_export.to_csv(output_path, index=False)

            # Envía por correo
            enviar_email_con_archivo(email, output_path)

        return render_template("gracias.html")

    return render_template("formulario.html")
