from flask import Flask, request, render_template, redirect, url_for
from werkzeug.utils import secure_filename
import pandas as pd
import os
import json
from datetime import datetime, timedelta
import smtplib
from email.message import EmailMessage

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'json'}

REMITENTE = "terastreocl@gmail.com"
CLAVE_APP = "owei lbzk inms cvqn"  # Puedes usar variables de entorno luego

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_previous_month_range():
    today = datetime.today()
    first_day_this_month = datetime(today.year, today.month, 1)
    last_day_prev_month = first_day_this_month - timedelta(days=1)
    first_day_prev_month = datetime(last_day_prev_month.year, last_day_prev_month.month, 1)
    return first_day_prev_month, last_day_prev_month

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

        archivos = request.files.getlist('file')
        email = request.form['email']

        for archivo in archivos:
            if archivo.filename == '' or not allowed_file(archivo.filename):
                continue

            filename = secure_filename(archivo.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            archivo.save(filepath)

            with open(filepath, "r", encoding="utf-8") as f:
                contenido = json.load(f)

            tablas = contenido.get("items", [])
            for idx, tabla in enumerate(tablas):
                rows = tabla.get("table", {}).get("rows", [])
                if not rows:
                    continue

                df = pd.DataFrame(rows)
                if 'start_at' not in df.columns or 'group_key' not in df.columns:
                    continue

                df['start_at'] = pd.to_datetime(df['start_at'], errors='coerce')
                inicio, fin = get_previous_month_range()
                df_filtrado = df[(df['start_at'] >= inicio) & (df['start_at'] <= fin)]

                nombre_mes = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                              "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"][inicio.month - 1]
                patente = df['group_key'].iloc[0]
                output_filename = f"reporte_{patente}_{nombre_mes}{inicio.year}.csv"
                output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
                df_filtrado.to_csv(output_path, index=False)

                enviar_email_con_archivo(email, output_path)

        return render_template("gracias.html")

    return render_template("formulario.html")
