import time
import sys
import os
import platform
from datetime import datetime, timedelta
from threading import Thread, Event

import sounddevice as sd
import numpy as np
try:
    import pyaudiowpatch as pyaudio
except ImportError:
    pyaudio = None

# Для проверки одного экземпляра приложения
try:
    from win32event import CreateMutex
    from win32api import GetLastError
    from winerror import ERROR_ALREADY_EXISTS
except ImportError:
    CreateMutex, GetLastError, ERROR_ALREADY_EXISTS = None, None, None

import requests
from dotenv import load_dotenv

from werkzeug.serving import make_server

import tkinter as tk
from tkinter import messagebox
from pystray import Icon, Menu, MenuItem as item
from PIL import Image, ImageDraw
import app_state
from app_state import get_application_path, settings, main_icon, http_server, monitoring_stop_event, app, generate_favicons
from config_manager import load_settings, load_contacts, DEFAULT_SETTINGS
from gui import open_main_window, open_web_interface, check_and_prompt_config
from recorder import start_recording_from_tray, pause_recording_from_tray, stop_recording_from_tray, resume_recording_from_tray, monitor_mic, monitor_sys
from utils import setup_logging
from web_app import create_app

# --- Load Environment Variables ---
dotenv_path = os.path.join(get_application_path(), '.env')
load_dotenv(dotenv_path)

# --- ОТЛАДКА: Выводим загруженные переменные в консоль при старте ---
USERNAME = os.getenv("CRS_USERNAME")
PASSWORD_HASH = os.getenv("CRS_PASSWORD_HASH")
print("--- Загруженные переменные окружения ---")
print(f"USERNAME из .env: '{USERNAME}'")
print(f"PASSWORD из .env: '{PASSWORD_HASH}'")

flask_thread = None

# --- Server Lifecycle Management ---
def start_server():
    global flask_thread
    flask_thread = None
    if settings.get("server_enabled"):
        if flask_thread and flask_thread.is_alive():
            print("Server thread is already running.")
            return # pragma: no cover
        flask_thread = Thread(target=run_flask, daemon=True)
        flask_thread.start()
        print("Flask server thread started.")
    # update_tray_menu() # pragma: no cover - This will be handled by the update thread

def stop_server(old_settings):
    global flask_thread
    flask_thread = None
    if flask_thread and flask_thread.is_alive() and old_settings.get("server_enabled"):
        print("Attempting to shut down old server...")
        try:
            port = old_settings.get("port")
            requests.post(f'http://127.0.0.1:{port}/shutdown', timeout=1)
        except requests.exceptions.RequestException as e:
            print(f"Info: Request to shutdown endpoint failed (this is often normal): {e}")
        flask_thread.join(timeout=2)
        if flask_thread.is_alive():
            print("Warning: Server thread did not terminate gracefully.")
        else:
            print("Old server thread terminated.")
    flask_thread = None
    # update_tray_menu() # pragma: no cover - This will be handled by the update thread

def restart_server(old_settings):
    stop_server(old_settings)
    start_server()

def update_tray_menu():
    """Updates the tray menu items based on current settings."""
    if not main_icon:
        return

    server_is_on = settings.get("server_enabled")

    if app_state.is_recording and not app_state.is_paused:
        # Recording is active
        return Menu(
            item('Начать запись', start_recording_from_tray, enabled=False),
            item('Приостановить запись', pause_recording_from_tray, enabled=True),
            item('Остановить запись', lambda: stop_recording_from_tray(), enabled=True),
            Menu.SEPARATOR,
            item('Веб-интерфейс', lambda: open_web_interface(), enabled=server_is_on),
            item('Настройки', lambda: open_main_window(restart_server_cb=restart_server)),
            item('Открыть папку с записями', open_rec_folder),
            Menu.SEPARATOR,
            item('Выход', exit_action)
        )
    elif app_state.is_recording and app_state.is_paused:
        # Recording is paused
        return Menu(
            item('Начать запись', start_recording_from_tray, enabled=False),
            item('Возобновить запись', resume_recording_from_tray, enabled=True),
            item('Остановить запись', lambda: stop_recording_from_tray(), enabled=True),
            Menu.SEPARATOR,
            item('Веб-интерфейс', lambda: open_web_interface(), enabled=server_is_on),
            item('Настройки', lambda: open_main_window(restart_server_cb=restart_server)),
            item('Открыть папку с записями', open_rec_folder),
            Menu.SEPARATOR,
            item('Выход', exit_action)
        )
    else:
        # Not recording
        return Menu(
            item('Начать запись', start_recording_from_tray, enabled=True),
            item('Приостановить запись', pause_recording_from_tray, enabled=False),
            item('Остановить запись', lambda: stop_recording_from_tray(), enabled=False),
            Menu.SEPARATOR,
            item('Веб-интерфейс', lambda: open_web_interface(), enabled=server_is_on),
            item('Настройки', lambda: open_main_window(restart_server_cb=restart_server)),
            item('Открыть папку с записями', open_rec_folder),
            Menu.SEPARATOR,
            item('Выход', exit_action)
        )

# --- Основная часть ---
def run_flask():
    global http_server
    host = '0.0.0.0' if settings.get("lan_accessible") else '127.0.0.1'
    port = settings.get("port", DEFAULT_SETTINGS["port"])
    try: # pragma: no cover
        http_server = make_server(host, port, app, threaded=True)
        http_server.serve_forever()
    except Exception as e: # pragma: no cover
        print(f"Failed to start Flask server: {e}")

def exit_action(icon, item):
    if flask_thread and flask_thread.is_alive() and settings.get("server_enabled"):
        print("Attempting to shut down server on exit...") # pragma: no cover
        try:
            port = settings.get("port")
            requests.post(f'http://127.0.0.1:{port}/shutdown', timeout=1, verify=False)
            flask_thread.join(timeout=2)
        except requests.exceptions.RequestException as e:
            print(f"Info: Request to shutdown endpoint failed on exit: {e}")
    icon.stop()
    monitoring_stop_event.set() # Останавливаем потоки мониторинга
    # A small delay to allow tray icon to disappear before the process exits
    time.sleep(0.1)
    os._exit(0)

def create_icon(shape, color):
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    if shape == 'circle': 
        dc.ellipse((0, 0, 63, 63), fill=color)
    elif shape == 'triangle':
        # Draw triangle pointing up
        dc.polygon([(32, 10), (10, 50), (54, 50)], fill=color)
    elif shape == 'pause':
        # Draw two vertical bars for pause symbol
        bar_width = 24
        # Left bar
        dc.rectangle([(0, 0), (bar_width, 64)], fill=color)
        # Right bar
        dc.rectangle([(64 - bar_width, 0), (64, 64)], fill=color)
    else: 
        dc.rectangle((0, 0, 63, 63), fill=color)
    return image

def update_icon_and_menu(icon):
    """A dedicated thread to update the icon and menu based on app state."""
    rec_icon = create_icon('circle', 'red'); stop_icon = create_icon('square', 'gray'); pause_icon = create_icon('pause', 'orange')
    last_recording_state = None
    last_pause_state = None
    last_server_state = None
    
    while True:
        # Check if any relevant state has changed
        if app_state.is_recording != last_recording_state or app_state.is_paused != last_pause_state or settings.get("server_enabled") != last_server_state:
            if app_state.is_recording and app_state.is_paused:
                icon.icon = pause_icon
            elif app_state.is_recording:
                icon.icon = rec_icon
            else:
                icon.icon = stop_icon
            
            # Safely update the menu
            icon.menu = update_tray_menu()
            icon.update_menu()
            
            last_recording_state = app_state.is_recording
            last_pause_state = app_state.is_paused
            last_server_state = settings.get("server_enabled")
        
        time.sleep(0.1)

def open_rec_folder(icon, item):
    rec_dir = os.path.join(get_application_path(), 'rec')
    os.makedirs(rec_dir, exist_ok=True)
    os.startfile(rec_dir)

def _suppress_subprocess_window():
    """
    "Оборачивает" subprocess.Popen, чтобы подавить появление консольных окон в Windows
    при вызове внешних программ, таких как ffmpeg из pydub.
    """
    if platform.system() == "Windows":
        try:
            import subprocess
            
            original_popen = subprocess.Popen

            def new_popen(*args, **kwargs):
                # Добавляем флаг CREATE_NO_WINDOW, если он еще не задан
                if 'creationflags' not in kwargs:
                    kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
                return original_popen(*args, **kwargs)

            subprocess.Popen = new_popen
        except Exception as e:
            print(f"Не удалось применить патч для скрытия окон subprocess: {e}")

if __name__ == '__main__':
    # --- Проверка на запуск только одного экземпляра приложения ---
    if CreateMutex:
        mutex_name = "ChroniqueXRecordServerMutex"
        mutex = CreateMutex(None, 1, mutex_name)
        if GetLastError() == ERROR_ALREADY_EXISTS:
            # Если мьютекс уже существует, значит, приложение уже запущено.
            # Можно показать сообщение пользователю.
            root = tk.Tk()
            root.withdraw()  # Скрываем основное окно tkinter
            messagebox.showwarning("Уже запущено", "Приложение ChroniqueX Record Server уже запущено.")
            root.destroy()
            sys.exit(0)
    else:
        print("Предупреждение: библиотека pywin32 не установлена. Проверка на запуск единственного экземпляра отключена.")

    _suppress_subprocess_window()
    setup_logging()
    load_settings()

    # Устанавливаем уровень логирования для Werkzeug, чтобы убрать INFO сообщения о запросах
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.WARNING)
    
    app = create_app()
    app.secret_key = settings.get("secret_key")

    # Проверяем конфигурацию перед загрузкой контактов и запуском сервера
    check_and_prompt_config()

    load_contacts() # pragma: no cover
    generate_favicons()

    stop_icon = create_icon('square', 'gray')
    main_icon = Icon('ChroniqueX Record Server', stop_icon, 'ChroniqueX Record Server', menu=Menu(lambda: update_tray_menu().items))

    # Start server and update menu for the first time
    start_server()  # This will start the flask thread

    update_thread = Thread(target=update_icon_and_menu, args=(main_icon,), daemon=True)
    update_thread.start()

    # --- Запуск потоков мониторинга звука ---
    mic_monitor_thread = Thread(target=monitor_mic, args=(monitoring_stop_event,), daemon=True)
    mic_monitor_thread.start()

    if platform.system() == "Windows" and pyaudio:
        sys_monitor_thread = Thread(target=monitor_sys, args=(monitoring_stop_event,), daemon=True)
        sys_monitor_thread.start()
    
    # Запускаем иконку в основном потоке. Это блокирующий вызов.
    # Веб-сервер и другие компоненты работают в фоновых потоках.
    main_icon.run()