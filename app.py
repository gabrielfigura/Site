```python
from flask import Flask, request, render_template, send_file, jsonify
import os
import subprocess
import json
import requests  # Para enviar mensagem ao Telegram
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
import whisper
import torch
from datetime import timedelta

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
EDITED_FOLDER = 'edited'
MUSIC_FOLDER = 'music'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(EDITED_FOLDER, exist_ok=True)
os.makedirs(MUSIC_FOLDER, exist_ok=True)

# Configurações API (substitua com suas chaves reais)
YOUTUBE_API_KEY = 'SUA_CHAVE_API_YOUTUBE'
YOUTUBE_CLIENT_SECRET_FILE = 'client_secret.json'
INSTAGRAM_ACCESS_TOKEN = 'SEU_TOKEN_INSTAGRAM'
INSTAGRAM_USER_ID = 'SEU_ID_USUARIO_INSTAGRAM'

# Configurações do Telegram
TELEGRAM_TOKEN = '8344261996:AAEgDWaIb7hzknPpTQMdiYKSE3hjzP0mqFc'
TELEGRAM_CHAT_ID = '-1002783091818'
SITE_URL = 'https://CleverVideosIA.squarecloud.app'  # Link personalizado

# Enviar mensagem ao Telegram quando o site ficar online
def send_telegram_message(message):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message
    }
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Erro ao enviar mensagem ao Telegram: {e}")

# Enviar link do site ao iniciar
send_telegram_message(f"O site está online! Acesse: {SITE_URL}")

# Mapa de tipos de vídeo para músicas de fundo
MUSIC_MAP = {
    'action': 'action.mp3',
    'calm': 'calm.mp3',
    'educational': 'educational.mp3',
    'funny': 'funny.mp3',
}

def format_time(seconds):
    td = timedelta(seconds=seconds)
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = int(td.microseconds / 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

def generate_srt(segments, output_path):
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, segment in enumerate(segments, start=1):
            start = format_time(segment['start'])
            end = format_time(segment['end'])
            text = segment['text'].strip()
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")

def edit_video(input_path, output_path, duration_seconds, video_type):
    try:
        audio_path = os.path.join(UPLOAD_FOLDER, 'audio.mp3')
        subprocess.run(['ffmpeg', '-i', input_path, '-vn', '-acodec', 'libmp3lame', audio_path], check=True)
        model = whisper.load_model("base")
        result = model.transcribe(audio_path, language=None)
        srt_path = os.path.join(EDITED_FOLDER, 'subtitles.srt')
        generate_srt(result['segments'], srt_path)
        music_file = os.path.join(MUSIC_FOLDER, MUSIC_MAP.get(video_type, 'calm.mp3'))
        temp_path = os.path.join(EDITED_FOLDER, 'temp.mp4')
        subprocess.run([
            'ffmpeg', '-i', input_path, '-t', str(duration_seconds),
            '-vf', f"subtitles={srt_path}:force_style='FontName=Arial,FontSize=24,PrimaryColour=&HFFFFFF&,BorderStyle=3'",
            '-af', 'afade=t=in:ss=0:d=3,afade=t=out:st=' + str(duration_seconds - 3) + ':d=3',
            temp_path
        ], check=True)
        subprocess.run([
            'ffmpeg', '-i', temp_path, '-i', music_file,
            '-filter_complex', '[1:a]volume=0.2[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=3',
            '-map', '0:v', '-c:v', 'copy', '-shortest', output_path
        ], check=True)
        os.remove(audio_path)
        os.remove(srt_path)
        os.remove(temp_path)
        return True
    except Exception as e:
        print(f"Erro ao editar: {e}")
        return False

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({'error': 'Nenhum arquivo enviado'}), 400
        file = request.files['file']
        tipo = request.form.get('tipo')
        duracao = request.form.get('duracao')
        video_type = request.form.get('video_type')
        if file.filename == '':
            return jsonify({'error': 'Arquivo inválido'}), 400
        input_path = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(input_path)
        if duracao == '30s':
            duration_sec = 30
        elif duracao == '1min':
            duration_sec = 60
        elif duracao == '1:30s':
            duration_sec = 90
        elif duracao == 'custom':
            duration_sec = int(request.form.get('custom_duracao', 60))
        else:
            duration_sec = 60
        output_filename = f"edited_{file.filename}"
        output_path = os.path.join(EDITED_FOLDER, output_filename)
        if not edit_video(input_path, output_path, duration_sec, video_type):
            return jsonify({'error': 'Falha na edição'}), 500
        if tipo == 'youtube':
            try:
                credentials = Credentials.from_authorized_user_file('token.json', scopes=['https://www.googleapis.com/auth/youtube.upload'])
                youtube = build('youtube', 'v3', credentials=credentials)
                body = {
                    'snippet': {'title': 'Vídeo Editado Profissionalmente', 'description': 'Com legendas, música e efeitos'},
                    'status': {'privacyStatus': 'private'}
                }
                media = MediaFileUpload(output_path)
                response = youtube.videos().insert(part='snippet,status', body=body, media_body=media).execute()
                video_id = response['id']
                return jsonify({'success': True, 'platform': 'YouTube', 'url': f'https://youtube.com/watch?v={video_id}'})
            except Exception as e:
                return jsonify({'error': f'Falha no upload YouTube: {e}'}), 500
        elif tipo == 'reels':
            try:
                url = f'https://graph.facebook.com/v20.0/{INSTAGRAM_USER_ID}/media'
                params = {
                    'media_type': 'REELS',
                    'video_url': 'URL_DO_VIDEO_HOSPEADO',
                    'caption': 'Reel editado profissionalmente',
                    'access_token': INSTAGRAM_ACCESS_TOKEN
                }
                response = requests.post(url, params=params)
                if response.status_code == 200:
                    publish_url = f'https://graph.facebook.com/v20.0/{INSTAGRAM_USER_ID}/media_publish'
                    creation_id = response.json()['id']
                    publish_params = {'creation_id': creation_id, 'access_token': INSTAGRAM_ACCESS_TOKEN}
                    publish_response = requests.post(publish_url, params=publish_params)
                    return jsonify({'success': True, 'platform': 'Reels', 'id': publish_response.json().get('id')})
                else:
                    return jsonify({'error': 'Falha no upload Reels'}), 500
            except Exception as e:
                return jsonify({'error': f'Falha no upload Reels: {e}'}), 500
        else:
            return send_file(output_path, as_attachment=True)
    return render_template_string('''
    <!doctype html>
    <html lang="pt">
    <head>
        <title>Editor Profissional de Vídeos</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body { padding: 20px; background-color: #f8f9fa; }
            .container { max-width: 600px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="text-center mb-4">Editor Automático de Vídeos Profissional</h1>
            <form method="post" enctype="multipart/form-data" class="border p-4 rounded bg-white">
                <div class="mb-3">
                    <label class="form-label">Selecione o vídeo:</label>
                    <input type="file" name="file" class="form-control">
                </div>
                <div class="mb-3">
                    <label class="form-label">Tipo de plataforma:</label>
                    <select name="tipo" class="form-select">
                        <option value="reels">Reels</option>
                        <option value="youtube">YouTube</option>
                    </select>
                </div>
                <div class="mb-3">
                    <label class="form-label">Duração (para Reels):</label>
                    <select name="duracao" class="form-select">
                        <option value="30s">30s</option>
                        <option value="1min">1min</option>
                        <option value="1:30s">1:30s</option>
                    </select>
                </div>
                <div class="mb-3">
                    <label class="form-label">Duração custom (segundos, para YouTube):</label>
                    <input type="number" name="custom_duracao" value="60" class="form-control">
                </div>
                <div class="mb-3">
                    <label class="form-label">Tipo de vídeo (para música de fundo):</label>
                    <select name="video_type" class="form-select">
                        <option value="action">Ação</option>
                        <option value="calm">Calmo</option>
                        <option value="educational">Educacional</option>
                        <option value="funny">Engraçado</option>
                    </select>
                </div>
                <button type="submit" class="btn btn-primary w-100">Editar e Postar</button>
            </form>
        </div>
    </body>
    </html>
    ''')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
```
