import os
import re
import uuid
import json
from threading import Thread

from flask import (
    Blueprint, render_template, jsonify, request, send_file, Response,
    session, redirect, url_for
)
from werkzeug.security import check_password_hash
from pydub import AudioSegment

from app_state import get_application_path, settings, contacts_data
from config_manager import save_settings, save_contacts
from utils import (
    get_date_dirs_data, get_recordings_for_date_data, get_recordings_last_modified,
    build_final_prompt_addition
)
from postprocessing import process_transcription_task, process_protocol_task
from app_state import is_recording, is_paused, FAVICON_REC_BYTES, FAVICON_PAUSE_BYTES, FAVICON_STOP_BYTES

ui_bp = Blueprint('ui', __name__)

@ui_bp.route('/')
def index():
    return render_template('index.html')

@ui_bp.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        USERNAME = os.getenv("CRS_USERNAME")
        PASSWORD_HASH = os.getenv("CRS_PASSWORD_HASH")
        if request.form['username'] == USERNAME and PASSWORD_HASH and check_password_hash(PASSWORD_HASH, request.form['password']):
            session['logged_in'] = True
            return redirect(url_for('ui.index'))
        else:
            error = 'Неверный логин или пароль'
    return render_template('login.html', error=error)

@ui_bp.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('ui.login'))

@ui_bp.route('/get_date_dirs')
def get_date_dirs():
    return jsonify(get_date_dirs_data())

@ui_bp.route('/get_recordings_for_date/<date_str>')
def get_recordings_for_date(date_str):
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return jsonify({"error": "Invalid date format"}), 400
    return jsonify(get_recordings_for_date_data(date_str))

@ui_bp.route('/recordings_state')
def recordings_state():
    return jsonify({"last_modified": get_recordings_last_modified()})

@ui_bp.route('/preview_prompt_addition', methods=['POST'])
def preview_prompt_addition():
    from datetime import datetime
    from pathlib import Path
    try:
        preview_settings = request.get_json()
        if not preview_settings: return jsonify({"error": "No settings provided"}), 400
        original_settings = settings.copy()
        settings.update(preview_settings)
        preview_path = Path(os.path.join(get_application_path(), 'rec', datetime.now().strftime('%Y-%m-%d')))
        final_prompt_text = build_final_prompt_addition(base_path=preview_path, recording_date=datetime.now(), is_preview=True)
        settings.clear(); settings.update(original_settings)
        return jsonify({"prompt_text": final_prompt_text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@ui_bp.route('/update_metadata/<date_str>/<filename>', methods=['POST'])
def update_metadata(date_str, filename):
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str): return jsonify({"error": "Invalid date format"}), 400
    new_title = request.json.get('title')
    if not new_title: return jsonify({"error": "Title cannot be empty"}), 400
    json_path = os.path.join(get_application_path(), 'rec', date_str, os.path.splitext(filename)[0] + '.json')
    if not os.path.exists(json_path): return jsonify({"error": "Metadata file not found"}), 404
    with open(json_path, 'r+', encoding='utf-8') as f:
        metadata = json.load(f)
        metadata['title'] = new_title
        f.seek(0); json.dump(metadata, f, indent=4, ensure_ascii=False); f.truncate()
    return jsonify({"status": "ok"})

@ui_bp.route('/files/<path:filepath>')
def serve_recorded_file(filepath):
    rec_dir = os.path.join(get_application_path(), 'rec')
    file_path = os.path.join(rec_dir, filepath)
    if not os.path.abspath(file_path).startswith(os.path.abspath(rec_dir)): return "Access denied", 403
    if not os.path.exists(file_path): return "File not found", 404
    
    import mimetypes
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type and (mime_type.startswith('text/') or mime_type == 'application/pdf' or mime_type.startswith(('audio/', 'video/'))):
        return send_file(file_path, mimetype=mime_type)
    return send_file(file_path)

@ui_bp.route('/save_web_settings', methods=['POST'])
def save_web_settings():
    try:
        data = request.get_json()
        if not data: return jsonify({"status": "error", "message": "Нет данных"}), 400
        for key in ['use_custom_prompt', 'prompt_addition', 'selected_contacts', 'context_file_rules',
                    'add_meeting_date', 'meeting_date_source', 'meeting_name_templates',
                    'active_meeting_name_template_id', 'relay_enabled', 'confirm_prompt_on_action']:
            if key in data: settings[key] = data[key]
        save_settings(settings)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Ошибка: {e}"}), 500

@ui_bp.route('/get_web_settings')
def get_web_settings():
    return jsonify({
        "use_custom_prompt": settings.get("use_custom_prompt", False),
        "prompt_addition": settings.get("prompt_addition", ""),
        "selected_contacts": settings.get("selected_contacts", []),
        "context_file_rules": settings.get("context_file_rules", []),
        "add_meeting_date": settings.get("add_meeting_date", True),
        "meeting_date_source": settings.get("meeting_date_source", "current"),
        "meeting_name_templates": settings.get("meeting_name_templates", []),
        "active_meeting_name_template_id": settings.get("active_meeting_name_template_id", None),
        "relay_enabled": settings.get("relay_enabled", False),
        "confirm_prompt_on_action": settings.get("confirm_prompt_on_action", False),
    })

@ui_bp.route('/get_contacts')
def get_contacts():
    contacts_data.get("groups", []).sort(key=lambda g: g.get("name", ""))
    return jsonify(contacts_data)

@ui_bp.route('/get_group_names')
def get_group_names():
    group_names = sorted(list(set([g.get("name") for g in contacts_data.get("groups", []) if g.get("name")])))
    return jsonify(group_names)

@ui_bp.route('/contacts/add', methods=['POST'])
def add_contact_web():
    data = request.json
    name = data.get('name', '').strip()
    group_name = data.get('group_name', 'Без группы').strip() or 'Без группы'
    if not name: return jsonify({"status": "error", "message": "Имя не может быть пустым"}), 400
    if name == '_init_group_':
        if group_name and not any(g['name'] == group_name for g in contacts_data.get("groups", [])):
            contacts_data.setdefault('groups', []).append({"name": group_name, "contacts": []})
            save_contacts(contacts_data)
        return jsonify({"status": "ok"})
    new_contact = {"id": str(uuid.uuid4()), "name": name}
    group = next((g for g in contacts_data.get("groups", []) if g['name'] == group_name), None)
    if group: group.setdefault('contacts', []).append(new_contact)
    else: contacts_data.setdefault('groups', []).append({"name": group_name, "contacts": [new_contact]})
    save_contacts(contacts_data)
    return jsonify({"status": "ok", "contact": new_contact})

@ui_bp.route('/contacts/update/<contact_id>', methods=['POST'])
def update_contact_web(contact_id):
    new_name = request.json.get('name', '').strip()
    if not new_name: return jsonify({"status": "error", "message": "Имя не может быть пустым"}), 400
    for group in contacts_data.get("groups", []):
        for contact in group.get("contacts", []):
            if contact.get("id") == contact_id:
                contact["name"] = new_name
                save_contacts(contacts_data)
                return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": "Участник не найден"}), 404

@ui_bp.route('/contacts/delete/<contact_id>', methods=['POST'])
def delete_contact_web(contact_id):
    for group in contacts_data.get("groups", []):
        original_len = len(group.get("contacts", []))
        group["contacts"] = [c for c in group.get("contacts", []) if c.get("id") != contact_id]
        if len(group.get("contacts", [])) < original_len:
            contacts_data["groups"] = [g for g in contacts_data.get("groups", []) if g.get("contacts")]
            if contact_id in settings.get("selected_contacts", []):
                settings["selected_contacts"].remove(contact_id)
                save_settings(settings)
            save_contacts(contacts_data)
            return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": "Участник не найден"}), 404

@ui_bp.route('/groups/update', methods=['POST'])
def update_group_web():
    data = request.json
    old_name, new_name = data.get('old_name', '').strip(), data.get('new_name', '').strip()
    if not old_name or not new_name: return jsonify({"status": "error", "message": "Имя группы не может быть пустым"}), 400
    if old_name == new_name: return jsonify({"status": "ok"})
    if any(g.get('name') == new_name for g in contacts_data.get("groups", [])): return jsonify({"status": "error", "message": f"Группа '{new_name}' уже существует"}), 409
    for group in contacts_data.get("groups", []):
        if group.get("name") == old_name:
            group["name"] = new_name
            save_contacts(contacts_data)
            return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": "Группа не найдена"}), 404

@ui_bp.route('/groups/delete', methods=['POST'])
def delete_group_web():
    group_name = request.json.get('name', '').strip()
    if not group_name: return jsonify({"status": "error", "message": "Имя группы не может быть пустым"}), 400
    group_to_delete = next((g for g in contacts_data.get("groups", []) if g.get("name") == group_name), None)
    if not group_to_delete: return jsonify({"status": "error", "message": "Группа не найдена"}), 404
    contact_ids_to_remove = {c.get("id") for c in group_to_delete.get("contacts", []) if c.get("id")}
    contacts_data["groups"] = [g for g in contacts_data.get("groups", []) if g.get("name") != group_name]
    if contact_ids_to_remove and "selected_contacts" in settings:
        settings["selected_contacts"] = [cid for cid in settings.get("selected_contacts", []) if cid not in contact_ids_to_remove]
        save_settings(settings)
    save_contacts(contacts_data)
    return jsonify({"status": "ok"})

@ui_bp.route('/recreate_transcription/<date>/<filename>', methods=['POST'])
def recreate_transcription(date, filename):
    file_path = os.path.join(get_application_path(), 'rec', date, filename)
    if not os.path.exists(file_path): return jsonify({"status": "error", "message": "Аудиофайл не найден"}), 404
    Thread(target=process_transcription_task, args=(file_path,), daemon=True).start()
    return jsonify({"status": "ok"})

@ui_bp.route('/recreate_protocol/<date>/<filename>', methods=['POST'])
def recreate_protocol(date, filename):
    txt_file_path = os.path.join(get_application_path(), 'rec', date, os.path.splitext(filename)[0] + ".txt")
    if not os.path.exists(txt_file_path): return jsonify({"status": "error", "message": "Файл транскрипции (.txt) не найден."}), 404
    Thread(target=process_protocol_task, args=(txt_file_path,), daemon=True).start()
    return jsonify({"status": "ok"})

@ui_bp.route('/compress_to_mp3/<date>/<filename>', methods=['POST'])
def compress_to_mp3(date, filename):
    wav_path = os.path.join(get_application_path(), 'rec', date, filename)
    if not os.path.exists(wav_path) or not wav_path.lower().endswith('.wav'): return jsonify({"status": "error", "message": "WAV файл не найден"}), 404
    def compress():
        try:
            mp3_path = wav_path.replace('.wav', '.mp3')
            AudioSegment.from_wav(wav_path).export(mp3_path, format="mp3", parameters=["-y", "-loglevel", "quiet"])
            os.remove(wav_path)
        except Exception as e: print(f"Ошибка при сжатии в MP3: {e}")
    Thread(target=compress, daemon=True).start()
    return jsonify({"status": "ok"})

@ui_bp.route('/favicon.ico')
def favicon():
    if is_recording and not is_paused: icon_bytes = FAVICON_REC_BYTES
    elif is_recording and is_paused: icon_bytes = FAVICON_PAUSE_BYTES
    else: icon_bytes = FAVICON_STOP_BYTES
    return Response(icon_bytes, mimetype='image/vnd.microsoft.icon')