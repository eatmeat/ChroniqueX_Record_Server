import os
import requests
import time
import logging
from pathlib import Path
from datetime import datetime
import json
from threading import Thread

import app_state
from app_state import settings, contacts_data
from utils import build_final_prompt_addition

def post_task(file_path, task_type, prompt_addition_str=None):
    API_URL = os.getenv("CRS_API_URL")
    API_KEY = os.getenv("CRS_API_KEY")
    if not API_URL or not API_KEY: return None
    try:
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f)}
            data = {'api_key': API_KEY, 'task_type': task_type}
            
            selected_contact_ids = set(settings.get("selected_contacts", []))
            num_speakers_from_contacts = len(selected_contact_ids)
            
            if task_type == 'protocol' and prompt_addition_str:
                data['prompt_addition'] = prompt_addition_str

            if task_type == 'transcribe' and num_speakers_from_contacts > 0:
                data['num_speakers'] = num_speakers_from_contacts
            
            log_data = data.copy()
            if 'api_key' in log_data: log_data['api_key'] = '***'
            if 'prompt_addition' in log_data and log_data['prompt_addition']:
                log_data['prompt_addition'] = log_data['prompt_addition'][:100] + '...'
            logging.info(f"Отправка задачи: файл='{os.path.basename(file_path)}', параметры={log_data}")

            response = requests.post(f"{API_URL}/add_task", files=files, data=data, verify=False)
        if response.status_code == 202:
            return response.json().get("task_id")
        else:
            print(f"Ошибка создания задачи '{task_type}': {response.status_code} - {response.text}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Ошибка соединения при создании задачи '{task_type}': {e}")
        logging.error(f"Ошибка соединения при создании задачи '{task_type}': {e}")
        return None
    except Exception as e:
        logging.error(f"Непредвиденная ошибка в post_task для задачи '{task_type}': {e}", exc_info=True)
        return None

def poll_and_save_result(task_id, output_path):
    API_URL = os.getenv("CRS_API_URL")
    if not task_id: return False
    while True:
        try:
            response = requests.get(f"{API_URL}/get_result/{task_id}", timeout=10, verify=False)
            if response.status_code == 200:
                with open(output_path, 'wb') as f: f.write(response.content)
                logging.info(f"Задача {task_id} успешно завершена. Результат сохранен в {output_path}")
                return True
            elif response.status_code == 202: time.sleep(5)
            elif response.status_code == 500:
                error_msg = response.json().get('error', 'Неизвестная ошибка')
                print(f"Задача {task_id} провалена: {error_msg}")
                logging.error(f"Задача {task_id} провалена на сервере: {error_msg}")
                return False
            else: time.sleep(10)
        except requests.exceptions.RequestException as e:
            logging.warning(f"Ошибка соединения при проверке статуса задачи {task_id}: {e}. Повтор...")
            time.sleep(10)

def process_transcription_task(file_path):
    app_state.is_post_processing = True
    app_state.post_process_file_path = file_path
    app_state.post_process_stage = "transcribe"
    base_name, _ = os.path.splitext(file_path)
    txt_output_path = base_name + ".txt"
    transcription_task_id = post_task(file_path, "transcribe")
    if transcription_task_id:
        poll_and_save_result(transcription_task_id, txt_output_path)
    app_state.is_post_processing = False

def process_protocol_task(txt_file_path):
    app_state.is_post_processing = True
    app_state.post_process_file_path = txt_file_path
    app_state.post_process_stage = "protocol"
    txt_path = Path(txt_file_path)
    try:
        recording_date = datetime.strptime(txt_path.parent.name, '%Y-%m-%d')
    except (ValueError, IndexError):
        recording_date = datetime.now()

    final_prompt_addition = build_final_prompt_addition(base_path=txt_path.parent, recording_date=recording_date)
    protocol_task_id = post_task(txt_file_path, "protocol", prompt_addition_str=final_prompt_addition)
    if protocol_task_id:
        base_name, _ = os.path.splitext(txt_file_path)
        protocol_output_path = base_name + "_protocol.pdf"
        json_path = base_name + '.json'
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r+', encoding='utf-8') as f:
                    metadata = json.load(f)
                    metadata['promptAddition'] = final_prompt_addition
                    f.seek(0); json.dump(metadata, f, indent=4, ensure_ascii=False); f.truncate()
            except Exception as e: print(f"Не удалось обновить метаданные с промптом для {json_path}: {e}")
        poll_and_save_result(protocol_task_id, protocol_output_path)
    app_state.is_post_processing = False

def process_recording_tasks(final_audio_path):
    process_transcription_task(final_audio_path)
    txt_file_path = os.path.splitext(final_audio_path)[0] + ".txt"
    if os.path.exists(txt_file_path):
        process_protocol_task(txt_file_path)