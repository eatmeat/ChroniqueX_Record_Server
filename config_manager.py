import os
import json
import secrets
from dotenv import load_dotenv

from app_state import get_application_path, settings, contacts_data

# --- Settings Management ---
SETTINGS_FILE = os.path.join(get_application_path(), 'record_server_settings.json')
DEFAULT_SETTINGS = {
    "port": 8288,
    "server_enabled": True,
    "autostart_server": True,
    "lan_accessible": False,
    "use_custom_prompt": False,
    "prompt_addition": "",
    "context_file_rules": [
        {
            "pattern": "*.html",
            "prompt": "\n--- НАЧАЛО файла @{filename} ---\n{content}\n--- КОНЕЦ файла @{filename} ---\n",
            "enabled": True
        }
    ],
    "add_meeting_date": True,
    "meeting_date_source": "current",
    "meeting_name_templates": [
        {"id": "default1", "template": "Еженедельное собрание команды"},
        {"id": "default2", "template": "Планирование спринта"}
    ],
    "relay_enabled": False,
    "active_meeting_name_template_id": None,
    "confirm_prompt_on_action": False,
    "main_window_width": 700,
    "main_window_height": 800,
    "main_window_x": None,
    "main_window_y": None,
    "secret_key": None,
    "selected_contacts": []
}

def load_settings():
    """Loads settings from the JSON file or creates it with defaults."""
    global settings
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                loaded_settings = json.load(f)
            if isinstance(loaded_settings, dict):
                settings.clear()
                settings.update(loaded_settings)
            else:
                settings.clear()
                settings.update(DEFAULT_SETTINGS.copy())
            for key, value in DEFAULT_SETTINGS.items():
                settings.setdefault(key, value)
        except (json.JSONDecodeError, TypeError):
            settings.clear()
            settings.update(DEFAULT_SETTINGS.copy())
    else:
        # Если файл настроек не существует, создаем его с настройками по умолчанию.
        settings.clear()
        settings.update(DEFAULT_SETTINGS.copy())
    if not settings.get("secret_key"):
        settings["secret_key"] = secrets.token_hex(16)
    save_settings(settings.copy()) # Сохраняем, чтобы создать файл или добавить недостающие ключи.

def save_settings(new_settings):
    """Saves settings to the JSON file."""
    global settings
    settings.clear()
    settings.update(new_settings)
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=4)
    print("Settings saved.")

# --- Contacts Management ---
CONTACTS_FILE = os.path.join(get_application_path(), 'contacts.json')

def load_contacts():
    """Loads contacts from the JSON file or creates it if it doesn't exist."""
    global contacts_data
    if os.path.exists(CONTACTS_FILE):
        try:
            with open(CONTACTS_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            contacts_data.clear()
            contacts_data.update(loaded)
            if "groups" not in contacts_data:
                contacts_data["groups"] = []
        except (json.JSONDecodeError, TypeError):
            contacts_data.clear()
            contacts_data["groups"] = []
    else:
        contacts_data.clear()
        contacts_data["groups"] = []
        save_contacts(contacts_data)

def save_contacts(new_contacts_data):
    """Saves contacts to the JSON file."""
    global contacts_data
    # Создаем копию, чтобы избежать проблем с изменением объекта, по которому итерируемся
    data_to_save = new_contacts_data.copy()
    contacts_data.clear() # Очищаем глобальный объект
    contacts_data.update(data_to_save) # Обновляем его свежими данными
    with open(CONTACTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data_to_save, f, indent=4, ensure_ascii=False)