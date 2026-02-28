import os
import re
import uuid
import json
from threading import Thread
import logging
from pathlib import Path

from pydub import AudioSegment
from flask import (
    Blueprint, render_template, jsonify, request, send_file, Response,
    session, redirect, url_for
)
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta

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

@ui_bp.route('/contacts_state')
def contacts_state():
    contacts_file_path = os.path.join(get_application_path(), 'contacts.json')
    if os.path.exists(contacts_file_path):
        return jsonify({"last_modified": os.path.getmtime(contacts_file_path)})
    return jsonify({"last_modified": 0})


@ui_bp.route('/preview_prompt_addition', methods=['POST'])
def preview_prompt_addition():
    from datetime import datetime
    from pathlib import Path
    try:
        current_settings_from_request = request.get_json()
        if not current_settings_from_request:
            return jsonify({"error": "No settings provided"}), 400

        # Создаем временную копию глобальных настроек и обновляем ее данными из запроса
        temp_settings_for_preview = settings.copy()
        temp_settings_for_preview.update(current_settings_from_request)

        # Определяем дату для предпросмотра на основе настроек из запроса
        # Это важно для корректной работы опции "Дата из папки" vs "Текущая дата"
        date_source = temp_settings_for_preview.get("meeting_date_source", "current")
        recording_date_str = current_settings_from_request.get('recording_date') # YYYY-MM-DD

        if date_source == 'folder' and recording_date_str:
            date_for_preview = datetime.strptime(recording_date_str, '%Y-%m-%d')
        else:
            # Используем текущую дату, если выбрано "current" или если дата не была передана
            date_for_preview = datetime.now()

        # Передаем временные настройки в функцию построения промпта
        preview_path = Path(os.path.join(get_application_path(), 'rec', date_for_preview.strftime('%Y-%m-%d'))) # is_preview=True, so path doesn't have to exist
        final_prompt_text = build_final_prompt_addition(base_path=preview_path, recording_date=date_for_preview, is_preview=True, override_settings=temp_settings_for_preview)
        
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

@ui_bp.route('/get_metadata/<date_str>/<filename>')
def get_metadata(date_str, filename):
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str): return jsonify({"error": "Invalid date format"}), 400
    json_path = os.path.join(get_application_path(), 'rec', date_str, os.path.splitext(filename)[0] + '.json')
    if not os.path.exists(json_path): return jsonify({"error": "Metadata file not found"}), 404
    with open(json_path, 'r', encoding='utf-8') as f: metadata = json.load(f)
    return jsonify(metadata)

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
        if not data:
            return jsonify({"status": "error", "message": "Нет данных"}), 400
        settings.update(data)
        save_settings(settings.copy())
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

@ui_bp.route('/groups/add', methods=['POST'])
def add_group_web():
    import logging
    data = request.json
    group_name = data.get('group_name', '').strip()
    logging.info(f"Получен запрос на добавление группы: '{group_name}'")
    if not group_name:
        logging.warning("Имя группы пустое, возвращаем ошибку 400.")
        return jsonify({"status": "error", "message": "Имя группы не может быть пустым"}), 400
    if any(g['name'] == group_name for g in contacts_data.get("groups", [])):
        logging.warning(f"Группа '{group_name}' уже существует, возвращаем ошибку 409.")
        return jsonify({"status": "error", "message": f"Группа '{group_name}' уже существует"}), 409
    
    contacts_data.setdefault('groups', []).append({"name": group_name, "contacts": []})
    save_contacts(contacts_data)
    logging.info(f"Группа '{group_name}' успешно создана и сохранена.")
    return jsonify({"status": "ok"})

@ui_bp.route('/contacts/add', methods=['POST'])
def add_contact_web():
    data = request.json
    name = data.get('name', '').strip()
    group_name = data.get('group_name', 'Без группы').strip() or 'Без группы'
    if not name: return jsonify({"status": "error", "message": "Имя не может быть пустым"}), 400
    new_contact = {"id": str(uuid.uuid4()), "name": name}
    group = next((g for g in contacts_data.get("groups", []) if g['name'] == group_name), None)
    if group is not None: group.setdefault('contacts', []).append(new_contact)
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
            # Группу не удаляем, даже если она стала пустой
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

@ui_bp.route('/update_metadata_and_recreate/<task_type>/<date>/<filename>', methods=['POST'])
def update_metadata_and_recreate(task_type, date, filename):
    from datetime import datetime
    from pathlib import Path

    data = request.get_json()
    if not data: return jsonify({"status": "error", "message": "Нет данных"}), 400

    json_path = Path(get_application_path()) / 'rec' / date / (os.path.splitext(filename)[0] + '.json')
    if not json_path.exists(): return jsonify({"status": "error", "message": "Файл метаданных не найден"}), 404

    # Обновляем метаданные из запроса
    with open(json_path, 'r+', encoding='utf-8') as f:
        metadata = json.load(f)
        metadata["settings"] = data
        # Пересчитываем и сохраняем promptAddition
        recording_date = datetime.fromisoformat(metadata.get("startTime", datetime.now().isoformat()))
        metadata["promptAddition"] = build_final_prompt_addition(base_path=json_path.parent, recording_date=recording_date, override_settings=data)
        f.seek(0)
        json.dump(metadata, f, indent=4, ensure_ascii=False)
        f.truncate()

    if task_type == 'transcription':
        return recreate_transcription(date, filename)
    elif task_type == 'protocol':
        return recreate_protocol(date, filename)
    return jsonify({"status": "error", "message": "Неизвестный тип задачи"}), 400

@ui_bp.route('/recreate_transcription/<date>/<filename>', methods=['POST'])
def recreate_transcription(date, filename):
    file_path = os.path.join(get_application_path(), 'rec', date, filename)
    if not os.path.exists(file_path): return jsonify({"status": "error", "message": "Аудиофайл не найден"}), 404
    Thread(target=process_transcription_task, args=(file_path,), daemon=True).start()
    return jsonify({"status": "ok", "message": "Задача пересоздания транскрипции запущена."})

@ui_bp.route('/recreate_protocol/<date>/<filename>', methods=['POST'])
def recreate_protocol(date, filename):
    txt_file_path = os.path.join(get_application_path(), 'rec', date, os.path.splitext(filename)[0] + ".txt")
    if not os.path.exists(txt_file_path): return jsonify({"status": "error", "message": "Файл транскрипции (.txt) не найден."}), 404
    Thread(target=process_protocol_task, args=(txt_file_path,), daemon=True).start()
    return jsonify({"status": "ok", "message": "Задача пересоздания протокола запущена."})

@ui_bp.route('/delete_recording/<date>/<filename>', methods=['DELETE'])
def delete_recording(date, filename):
    logging.info(f"Запрос на удаление записи: date='{date}', filename='{filename}'")
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date):
        logging.warning(f"Неверный формат даты при удалении: '{date}'")
        return jsonify({"status": "error", "message": "Неверный формат даты"}), 400

    base_app_path = Path(get_application_path())
    rec_dir = base_app_path / 'rec' / date
    base_name = Path(filename).stem
    logging.info(f"Папка с записями: '{rec_dir}', базовое имя файла: '{base_name}'")

    # Проверка, чтобы избежать выхода за пределы папки с записями
    if not rec_dir.resolve().is_relative_to(base_app_path / 'rec'):
        logging.error(f"Попытка доступа за пределы папки 'rec': '{rec_dir}'")
        return jsonify({"status": "error", "message": "Доступ запрещен"}), 403

    # Собираем все возможные файлы для удаления
    # 1. Основные файлы (аудио, json, txt)
    pattern1 = f"{base_name}.*"
    files_to_delete = list(rec_dir.glob(pattern1))
    logging.info(f"Поиск по шаблону '{pattern1}'. Найдено файлов: {len(files_to_delete)}. Файлы: {[str(f) for f in files_to_delete]}")

    # 2. Файл протокола (имеет суффикс _protocol)
    pattern2 = f"{base_name}_protocol.*"
    protocol_files = list(rec_dir.glob(pattern2))
    logging.info(f"Поиск по шаблону '{pattern2}'. Найдено файлов: {len(protocol_files)}. Файлы: {[str(f) for f in protocol_files]}")
    files_to_delete.extend(protocol_files)

    deleted_count = 0
    # Используем set для удаления дубликатов, если они вдруг появятся
    for file_path in set(files_to_delete):
        try:
            os.remove(file_path)
            logging.info(f"Успешно удален файл: {file_path}")
            deleted_count += 1
        except OSError as e:
            logging.error(f"Ошибка при удалении файла {file_path}: {e}")
            return jsonify({"status": "error", "message": f"Ошибка при удалении файла {file_path.name}: {e}"}), 500
    return jsonify({"status": "ok", "message": f"Удалено {deleted_count} файлов."})

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

def process_uploaded_file_task(audio_file_path):
    """
    Последовательно выполняет задачи транскрибации и создания протокола для загруженного файла.
    """
    # 1. Выполняем транскрибацию
    process_transcription_task(audio_file_path)
    # 2. Проверяем, создался ли .txt файл, и запускаем создание протокола
    txt_file_path = os.path.splitext(audio_file_path)[0] + ".txt"
    if os.path.exists(txt_file_path):
        process_protocol_task(txt_file_path)

@ui_bp.route('/add_file', methods=['POST'])
def add_file():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "Файл не найден в запросе"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "Файл не выбран"}), 400

    try:
        request_settings = json.loads(request.form.get('settings', '{}'))

        # 1. Сохраняем файл
        now = datetime.now()
        date_str = now.strftime('%Y-%m-%d')
        rec_dir = Path(get_application_path()) / 'rec' / date_str
        os.makedirs(rec_dir, exist_ok=True)

        # Используем уникальное имя, чтобы избежать конфликтов
        base_filename = os.path.splitext(secure_filename(file.filename))[0]
        timestamp = now.strftime("%H-%M-%S")
        unique_filename = f"{timestamp}_{base_filename}.{file.filename.rsplit('.', 1)[1].lower()}"
        file_path = os.path.join(rec_dir, unique_filename)
        file.save(file_path)

        # 2. Создаем метаданные
        audio = AudioSegment.from_file(file_path)
        duration_seconds = len(audio) / 1000.0

        # Определяем название записи
        title = base_filename.replace('_', ' ').replace('-', ' ') # Название по умолчанию
        active_template_id = request_settings.get("active_meeting_name_template_id")
        if active_template_id:
            templates = request_settings.get("meeting_name_templates", [])
            active_template = next((t for t in templates if t.get("id") == active_template_id), None)
            if active_template and active_template.get("template"):
                title = active_template.get("template")

        metadata = {
            "startTime": now.isoformat(),
            "endTime": (now + timedelta(seconds=duration_seconds)).isoformat(),
            "duration": duration_seconds,
            "title": title,
            "settings": request_settings,
            "promptAddition": build_final_prompt_addition(base_path=rec_dir, recording_date=now, override_settings=request_settings)
        }
        json_path = os.path.splitext(file_path)[0] + '.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=4, ensure_ascii=False)

        # 3. Запускаем обработку
        Thread(target=process_uploaded_file_task, args=(file_path,), daemon=True).start()
        return jsonify({"status": "ok", "message": f"Файл '{unique_filename}' принят и поставлен в очередь на обработку."})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Ошибка при обработке файла: {e}"}), 500