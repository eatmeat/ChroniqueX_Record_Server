import os
import sys
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
import json

from pydub import AudioSegment

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from app_state import settings, contacts_data
from config_manager import load_settings, load_contacts

def setup_logging():
    """Настраивает логирование в файл и в консоль."""
    from app_state import get_application_path
    log_file = os.path.join(get_application_path(), 'record_server.log')
    logger = logging.getLogger()
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.ERROR)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

def format_date_russian(date_obj):
    """Форматирует дату в формат 'DD MMMMM YYYY' на русском языке."""
    months = {
        1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля', 5: 'мая', 6: 'июня',
        7: 'июля', 8: 'августа', 9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'
    }
    day = date_obj.day
    month = months[date_obj.month]
    year = date_obj.year
    return f"{day:02d} {month} {year}"

def get_date_dirs_data():
    """Gathers and structures date directory data from the 'rec' directory."""
    from app_state import get_application_path
    date_groups = []
    rec_dir = os.path.join(get_application_path(), 'rec')
    
    if os.path.exists(rec_dir):
        date_dirs = [d for d in os.listdir(rec_dir) if os.path.isdir(os.path.join(rec_dir, d))]
        
        day_names = {
            0: 'понедельник', 1: 'вторник', 2: 'среда', 3: 'четверг',
            4: 'пятница', 5: 'суббота', 6: 'воскресенье'
        }
        months_genitive = {
            1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля', 5: 'мая', 6: 'июня',
            7: 'июля', 8: 'августа', 9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'
        }
        
        for date_dir in date_dirs:
            try:
                date_obj = datetime.strptime(date_dir, '%Y-%m-%d')
                day_of_week = day_names[date_obj.weekday()]
                week_number = int(date_obj.strftime('%W')) + 1
                
                start_of_week = date_obj - timedelta(days=date_obj.weekday())
                end_of_week = start_of_week + timedelta(days=6)
                short_months_lower = {
                    1: 'янв', 2: 'фев', 3: 'мар', 4: 'апр', 5: 'мая', 6: 'июн',
                    7: 'июл', 8: 'авг', 9: 'сен', 10: 'окт', 11: 'ноя', 12: 'дек'
                }

                if start_of_week.month == end_of_week.month:
                    date_range_str = f"{start_of_week.day} - {end_of_week.day} {short_months_lower[end_of_week.month]} {end_of_week.year}"
                else:
                    date_range_str = f"{start_of_week.day} {short_months_lower[start_of_week.month]} - {end_of_week.day} {short_months_lower[end_of_week.month]} {end_of_week.year}"

                week_header_text = f"{date_range_str} : неделя №{week_number}"
                date_part = f"{date_obj.day} {months_genitive[date_obj.month]}"
                
                date_groups.append({
                    'date': date_dir, 'date_part': date_part, 'day_of_week': day_of_week,
                    'week_number': week_number, 'week_header_text': week_header_text,
                })
            except ValueError:
                continue
    
    date_groups.sort(key=lambda x: x['date'], reverse=True)
    return date_groups

def get_recordings_for_date_data(date_dir):
    """Gathers and structures recording data for a specific date directory."""
    from app_state import get_application_path
    recordings_in_group = []
    rec_dir = os.path.join(get_application_path(), 'rec')
    date_path = os.path.join(rec_dir, date_dir)

    if not os.path.isdir(date_path): return []

    all_files = [f for f in os.listdir(date_path) if os.path.isfile(os.path.join(date_path, f))]
    file_groups = {}
    for filename in all_files:
        name, ext = os.path.splitext(filename)
        if name not in file_groups: file_groups[name] = {}
        file_groups[name][ext] = filename
    
    for base_name, file_dict in file_groups.items():
        audio_filename = file_dict.get('.wav') or file_dict.get('.mp3')
        if not audio_filename: continue

        audio_filepath = os.path.join(date_path, audio_filename)
        txt_filepath = os.path.join(date_path, base_name + ".txt")
        protocol_filepath = os.path.join(date_path, base_name + "_protocol.pdf")
        json_path = os.path.join(date_path, base_name + '.json')
        
        metadata = {}
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f: metadata = json.load(f)
            except (json.JSONDecodeError, TypeError): pass
        
        title = metadata.get('title', base_name)
        start_time_obj = datetime.fromisoformat(metadata['startTime']) if 'startTime' in metadata else datetime.fromtimestamp(os.path.getctime(audio_filepath))
        display_time = start_time_obj.strftime('%H:%M:%S')
        
        duration = metadata.get('duration')
        if duration is None:
            try: duration = len(AudioSegment.from_file(audio_filepath)) / 1000.0
            except Exception: duration = 0
        
        recordings_in_group.append({
            'filename': audio_filename, 'size': os.path.getsize(audio_filepath), 'time': display_time,
            'transcription_exists': os.path.exists(txt_filepath), 'transcription_filename': base_name + ".txt",
            'protocol_exists': os.path.exists(protocol_filepath), 'protocol_filename': base_name + "_protocol.pdf",
            'title': title, 'startTime': start_time_obj.isoformat(),
            'promptAddition': metadata.get('promptAddition', ''), 'duration': duration
        })
    
    recordings_in_group.sort(key=lambda x: x['time'], reverse=True)
    return recordings_in_group

def get_recordings_last_modified():
    """Возвращает время последнего изменения в папке с записями."""
    from app_state import get_application_path
    rec_dir = os.path.join(get_application_path(), 'rec')
    if not os.path.exists(rec_dir):
        return 0

    latest_mtime = os.path.getmtime(rec_dir)
    for root, dirs, files in os.walk(rec_dir):
        for name in files + dirs:
            try:
                path = os.path.join(root, name)
                latest_mtime = max(latest_mtime, os.path.getmtime(path))
            except (IOError, OSError):
                continue
    return latest_mtime

def _clean_html_content(html_content):
    if not html_content or not BeautifulSoup: return ""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        allowed_tags = {'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td'}
        for s in soup(['script', 'style']): s.decompose()
        for tag in soup.find_all(True):
            tag.attrs = {}
            if tag.name not in allowed_tags: tag.unwrap()
        if soup.body: soup = soup.body
        for cell in soup.find_all(['td', 'th']):
            cell.string = cell.get_text(separator=' ', strip=True)
        cleaned_html = soup.decode(formatter=None)
        cleaned_html = re.sub(r'(?<=>)\s*\n\s*(?=<)', '', cleaned_html)
        return re.sub(r'\n{2,}', '\n', cleaned_html).strip()
    except Exception as e:
        print(f"Ошибка при очистке HTML: {e}")
        return html_content

def build_final_prompt_addition(base_path, recording_date, is_preview=False, override_settings=None):
    current_settings = settings
    if override_settings:
        current_settings = override_settings
    else:
        load_settings() # Загружаем, если не переданы временные
    
    prompt_addition = current_settings.get("prompt_addition", "") if current_settings.get("use_custom_prompt", False) else ""
    prompt_addition = prompt_addition.replace("{current_date}", format_date_russian(recording_date))

    meeting_name_prompt_addition = ""
    active_template_id = current_settings.get("active_meeting_name_template_id")
    if active_template_id:
        templates = current_settings.get("meeting_name_templates", [])
        active_template = next((t for t in templates if t.get("id") == active_template_id), None)
        if active_template and active_template.get("template"):
            meeting_name_prompt_addition = f"# Название собрания: {active_template.get('template')}\n\n"

    date_prompt_addition = ""
    if current_settings.get("add_meeting_date", False):
        date_source = current_settings.get("meeting_date_source", "current")
        date_to_format = recording_date if date_source == 'folder' else datetime.now()
        date_prompt_addition = f"# Дата собрания: {format_date_russian(date_to_format)}\n\n"

    context_files_prompt_addition = ""
    context_rules = current_settings.get("context_file_rules", [])
    if base_path.exists() and context_rules:
        for rule in context_rules:
            if not rule.get("enabled", False): continue
            pattern, prompt_template = rule.get("pattern"), rule.get("prompt")
            if not pattern or not prompt_template: continue
            for found_file in sorted(list(base_path.glob(pattern))):
                try:
                    with open(found_file, 'r', encoding='utf-8') as f: content = f.read()
                    if found_file.suffix.lower() in ['.html', '.htm']: content = _clean_html_content(content)
                    if is_preview and len(content) > 1000: content = content[:1000] + "..."
                    if content: context_files_prompt_addition += prompt_template.replace("{filename}", found_file.name).replace("{content}", content)
                except Exception as e: print(f"Не удалось прочитать файл контекста {found_file}: {e}")

    combined_prompt_addition = prompt_addition + context_files_prompt_addition
    filtered_prompt_addition = "\n".join([line for line in combined_prompt_addition.splitlines() if not line.strip().startswith("//")])

    participants_prompt = ""
    selected_contact_ids = set(current_settings.get("selected_contacts", []))
    if selected_contact_ids:
        participants_by_group = {}
        for group in contacts_data.get("groups", []):
            group_name = group.get("name", "Без группы")
            for contact in group.get("contacts", []):
                if contact.get("id") in selected_contact_ids:
                    participants_by_group.setdefault(group_name, []).append(contact.get("name"))
        if participants_by_group:
            prompt_lines = ["# Список участников:\n"]
            for group_name in sorted(participants_by_group.keys()):
                prompt_lines.append(f"## Группа: {group_name}")
                for participant_name in sorted(participants_by_group[group_name]):
                    prompt_lines.append(f"- {participant_name}")
                prompt_lines.append("")
            participants_prompt = "\n".join(prompt_lines)

    return date_prompt_addition + meeting_name_prompt_addition + participants_prompt + "\n" + filtered_prompt_addition