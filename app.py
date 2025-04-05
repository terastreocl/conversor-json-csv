from flask import Flask, request, render_template
from werkzeug.utils import secure_filename
import pandas as pd
import os
import json
from datetime import datetime, timedelta
import smtplib
from email.message import EmailMessage
import re

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'json'}

REMITENTE = "terastreocl@gmail.com"
CLAVE_APP = "owei lbzk inms cvqn"

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Verificamos extensiones permitidas
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Rango del mes anterior
def get_previous_month_range():
    today = datetime.today()
    first_day_this_month = datetime(today.year, today.month, 1)
    last_day_prev_month = first_day_this_month - timedelta(days=1)
    first_day_prev_month = datetime(last_day_prev_month.year, last_day_prev_month.month, 1)
    return first_day_prev_month, last_day_prev_month

# Extraer coordenadas de ubicación
def extraer_coordenadas(texto):
    if not texto:
        return "", ""
    match = re.search(r'(-?\d+\.\d+),\s*(-?\d+\.\d+)', texto)
    if match:
        return match.group(1), match.group(2)
    return "", ""

# Extraer un valor profundo en un diccionario
def obtener_valor_seguro(diccionario, ruta):
    try:
        for clave in ruta:
            diccionario = diccionario[clave]
        return diccionario
    except (KeyError, TypeError):
        return None

# Validar ID_Servicio (CTA, CTR, CTE + 4 dígitos)
def es_id_servicio_valido(valor):
    return bool(re.match(r'^(CTA|CTR|CTE)\d{4}$', valor or ''))

# Validar PPU (4 letras + 2 números)
def es_patente_valida(valor):
    return bool(re.match(r'^[A-Z]{4}\d{2}$', valor or ''))

# Enviar correo con archivo adjunto
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

            # Convertir fechas y filtrar por el mes anterior
            df['start_at'] = pd.to_datetime(df['start_at'], errors='coerce')
            inicio, fin = get_previous_month_range()
            df_filtrado = df[(df['start_at'] >= inicio) & (df['start_at'] <= fin)]
            if df_filtrado.empty:
                continue

            # Extraer coordenadas de inicio
            df_filtrado[['GPS_Latitud', 'GPS_Longitud']] = df_filtrado['location_start'].apply(lambda x: pd.Series(extraer_coordenadas(x)))

            # Buscar posibles valores válidos en el JSON
            valores_posibles = str(tabla).split()

            id_servicio = next((v for v in valores_posibles if es_id_servicio_valido(v)), "SIN_ID")
            patente = next((v for v in valores_posibles if es_patente_valida(v)), "vehiculo")

            # Otros campos requeridos
            imei = obtener_valor_seguro(tabla, ["meta", "device.imei", "value"])
            df_filtrado['ID_Servicio'] = id_servicio
            df_filtrado['GPS_IMEI'] = imei
            df_filtrado['PPU'] = patente
            df_filtrado['GPS_Fecha_Hora_Chile'] = df_filtrado['start_at'].dt.strftime("%Y-%m-%d %H:%M:%S")

            columnas_finales = ['ID_Servicio', 'GPS_IMEI', 'PPU', 'GPS_Fecha_Hora_Chile', 'GPS_Latitud', 'GPS_Longitud']
            df_export = df_filtrado[columnas_finales]

            nombre_mes = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                          "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"][inicio.month - 1]

            output_filename = f"reporte_{patente}_{nombre_mes}{inicio.year}.csv"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
            df_export.to_csv(output_path, index=False)

            enviar_email_con_archivo(email, output_path)

        return render_template("gracias.html")

    return render_template("formulario.html")
