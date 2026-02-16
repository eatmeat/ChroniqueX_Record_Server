import os
import json
import wave
import time
import re
import sys
import platform
from datetime import datetime
import tempfile
from pathlib import Path
from threading import Thread, Event
import uuid
import logging

import sounddevice as sd
import numpy as np
try:
    from sounddevice import WasapiSettings
except ImportError:
    # WasapiSettings may not be available in all versions of sounddevice
    WasapiSettings = None
import pyaudiowpatch as pyaudio

# Для проверки одного экземпляра приложения
try:
    from win32event import CreateMutex
    from win32api import GetLastError
    from winerror import ERROR_ALREADY_EXISTS
except ImportError:
    CreateMutex, GetLastError, ERROR_ALREADY_EXISTS = None, None, None
# Импортируем PaWasapiStreamInfo напрямую из оригинального pyaudio,
# так как в некоторых версиях pyaudiowpatch он может отсутствовать.
try:
    from pyaudio import PaWasapiStreamInfo
except ImportError:
    PaWasapiStreamInfo = None
import requests
from dotenv import load_dotenv

import queue
from flask import Flask, jsonify, render_template, request, send_file, Response
from pydub import AudioSegment
from werkzeug.serving import make_server

import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
from pystray import Icon, Menu, MenuItem as item
from PIL import Image, ImageDraw
from PIL import ImageTk
import io

def get_application_path():
    """Get the path where the application is located, whether running as script or executable"""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        application_path = os.path.dirname(sys.executable)
    else:
        # Running as script
        application_path = os.path.dirname(os.path.abspath(__file__))
    return application_path

def setup_logging():
    """Настраивает логирование в файл и в консоль."""
    log_file = os.path.join(get_application_path(), 'record_server.log')
    # Используем getLogger для создания или получения логгера, чтобы избежать многократной настройки
    logger = logging.getLogger()
    if not logger.handlers: # Настраиваем только если обработчики еще не добавлены
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        
        # Обработчик для записи только ошибок в файл
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.ERROR) # Устанавливаем уровень логирования только для ошибок
        logger.addHandler(file_handler)

        # Обработчик для вывода INFO и выше в консоль
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


def _add_context_menu_to_text_widget(text_widget):
    """Add a context menu to a text widget with common text editing commands"""
    # Enable undo/redo functionality only for Text widgets (Entry widgets don't support undo)
    if isinstance(text_widget, tk.Text):
        text_widget.config(undo=True, maxundo=20)

    # Create the context menu
    context_menu = tk.Menu(text_widget, tearoff=0)

    # Add commands to the context menu
    context_menu.add_command(label="Выделить всё", command=lambda: _select_all(text_widget))
    # Only add "Найти" for Text widgets since Entry widgets are single-line
    if isinstance(text_widget, tk.Text):
        context_menu.add_command(label="Найти", command=lambda: _find_text(text_widget))
        context_menu.add_separator()
    context_menu.add_command(label="Вырезать", command=lambda: _cut_text(text_widget))
    context_menu.add_command(label="Копировать", command=lambda: _copy_text(text_widget))
    context_menu.add_command(label="Вставить", command=lambda: _paste_text(text_widget))
    
    # Only add comment/uncomment options for Text widgets
    if isinstance(text_widget, tk.Text):
        context_menu.add_separator()
        context_menu.add_command(label="Закомментировать", command=lambda: _comment_lines(text_widget))
        context_menu.add_command(label="Раскомментировать", command=lambda: _uncomment_lines(text_widget))
        context_menu.add_separator()
        context_menu.add_command(label="Отменить", command=lambda: _undo_text(text_widget))
        context_menu.add_command(label="Повторить", command=lambda: _redo_text(text_widget))
        context_menu.add_separator()
        context_menu.add_command(label="Очистить", command=lambda: _clear_text_widget(text_widget))
    else:
        # For Entry widgets, add a separator and clear option only
        context_menu.add_separator()
        context_menu.add_command(label="Очистить", command=lambda: _clear_text_widget(text_widget))

    # Bind keyboard shortcuts for common operations (language-independent)
    # Using a universal key handler that checks keycodes to ensure cross-layout compatibility
    def universal_key_handler(event):
        # Check if Control key is pressed (state & 0x4 means Ctrl is pressed)
        ctrl_pressed = event.state & 0x4
        # Check if Shift key is pressed (state & 0x1 means Shift is pressed)
        shift_pressed = event.state & 0x1

        if ctrl_pressed:
            # Using keysym_num to identify physical keys regardless of layout
            if event.keycode == 88:  # Physical X key (for Cut)
                return (_cut_text(text_widget), "break")[1]
            elif event.keycode == 67:  # Physical C key (for Copy)
                return (_copy_text(text_widget), "break")[1]
            elif event.keycode == 86:  # Physical V key (for Paste)
                return (_paste_text(text_widget), "break")[1]
            elif event.keycode == 65:  # Physical A key (for Select All)
                return (_select_all(text_widget), "break")[1]
            elif event.keycode == 90:  # Physical Z key (for Undo)
                return (_undo_text(text_widget), "break")[1]
            elif event.keycode == 89:  # Physical Y key (for Redo)
                return (_redo_text(text_widget), "break")[1]
            elif event.keycode == 19:  # Physical Semicolon key (for Comment/Uncomment - ; is near L on QWERTY)
                # We'll use Ctrl+; for comment/uncomment
                # Check if Shift is also pressed to determine comment vs uncomment
                if shift_pressed:
                    return (_uncomment_lines(text_widget), "break")[1]
                else:
                    return (_comment_lines(text_widget), "break")[1]
            elif event.keycode == 69:  # Physical Insert key (for Copy - Ctrl+Insert)
                return (_copy_text(text_widget), "break")[1]

        # Check for Shift+Insert separately (Shift + Insert)
        elif shift_pressed and event.keycode == 69:  # Physical Insert key (for Paste - Shift+Insert)
            return (_paste_text(text_widget), "break")[1]

        # Return None to allow default handling for other keys
        return None

    text_widget.bind("<Control-KeyPress>", universal_key_handler)

    # Bind right-click event to show context menu
    def show_context_menu_wrapper(event):
        # Temporarily enable the widget to handle the context menu if it's disabled
        original_state = text_widget.cget("state")
        if original_state == "disabled":
            text_widget.config(state="normal")
            context_menu.tk_popup(event.x_root, event.y_root)
            # Restore the original state after a short delay
            text_widget.config(state=original_state)
        else:
            context_menu.tk_popup(event.x_root, event.y_root)

    try:
        # For Windows and Linux
        text_widget.bind("<Button-3>", show_context_menu_wrapper)
    except tk.TclError:
        # For macOS, bind Control+Left-click to show context menu
        text_widget.bind("<Control-Button-1>", show_context_menu_wrapper)


def _undo_text(text_widget):
    """Undo the last action"""
    if isinstance(text_widget, tk.Text):
        try:
            text_widget.edit_undo()
        except tk.TclError:
            # No more actions to undo
            pass


def _redo_text(text_widget):
    """Redo the last undone action"""
    if isinstance(text_widget, tk.Text):
        try:
            text_widget.edit_redo()
        except tk.TclError:
            # No more actions to redo
            pass


def _comment_lines(text_widget):
    """Comment selected lines by adding // at the beginning"""
    if isinstance(text_widget, tk.Text):
        try:
            # Store the original selection
            start_pos = text_widget.index("sel.first")
            end_pos = text_widget.index("sel.last")

            # Get the line numbers of the selection
            start_line = int(start_pos.split('.')[0])
            end_line = int(end_pos.split('.')[0])

            # Adjust end_line if the selection ends at the beginning of a line
            end_col = int(end_pos.split('.')[1])
            if end_col == 0 and start_line != end_line:
                end_line -= 1

            # Process each line in the selection
            for line_num in range(start_line, end_line + 1):
                line_start = f"{line_num}.0"
                line_end = f"{line_num}.end"
                line_content = text_widget.get(line_start, line_end)

                # Insert // at the beginning of the line
                text_widget.delete(line_start, line_end)
                text_widget.insert(line_start, "//" + line_content)

            # Restore the selection
            text_widget.tag_remove("sel", "1.0", "end")
            text_widget.tag_add("sel", f"{start_line}.0", f"{end_line + 1}.0")

        except tk.TclError:
            # No selection, just add comment at current line
            current_line = text_widget.index("insert").split('.')[0]
            line_start = f"{current_line}.0"
            line_end = f"{current_line}.end"
            line_content = text_widget.get(line_start, line_end)

            text_widget.delete(line_start, line_end)
            text_widget.insert(line_start, "//" + line_content)


def _uncomment_lines(text_widget):
    """Uncomment selected lines by removing // at the beginning if present"""
    if isinstance(text_widget, tk.Text):
        try:
            # Store the original selection
            start_pos = text_widget.index("sel.first")
            end_pos = text_widget.index("sel.last")

            # Get the line numbers of the selection
            start_line = int(start_pos.split('.')[0])
            end_line = int(end_pos.split('.')[0])

            # Adjust end_line if the selection ends at the beginning of a line
            end_col = int(end_pos.split('.')[1])
            if end_col == 0 and start_line != end_line:
                end_line -= 1

            # Process each line in the selection
            for line_num in range(start_line, end_line + 1):
                line_start = f"{line_num}.0"
                line_end = f"{line_num}.end"
                line_content = text_widget.get(line_start, line_end)

                # Remove // from the beginning of the line if present
                if line_content.startswith("//"):
                    text_widget.delete(line_start, line_end)
                    text_widget.insert(line_start, line_content[2:])

            # Restore the selection
            text_widget.tag_remove("sel", "1.0", "end")
            text_widget.tag_add("sel", f"{start_line}.0", f"{end_line + 1}.0")

        except tk.TclError:
            # No selection, just uncomment current line
            current_line = text_widget.index("insert").split('.')[0]
            line_start = f"{current_line}.0"
            line_end = f"{current_line}.end"
            line_content = text_widget.get(line_start, line_end)

            # Remove // from the beginning of the line if present
            if line_content.startswith("//"):
                text_widget.delete(line_start, line_end)
                text_widget.insert(line_start, line_content[2:])


def _select_all(text_widget):
    """Select all text in the widget"""
    if isinstance(text_widget, tk.Text):
        # For Text widgets
        text_widget.tag_add("sel", "1.0", "end")
        text_widget.mark_set("insert", "end")
        text_widget.see("insert")
    elif isinstance(text_widget, tk.Entry):
        # For Entry widgets
        text_widget.select_range(0, tk.END)
        text_widget.icursor(tk.END)  # Move cursor to end


def _find_text(text_widget):
    """Open a find dialog to search for text in the widget"""
    # Create a top-level window for the find dialog
    find_window = tk.Toplevel(text_widget.winfo_toplevel())
    find_window.title("Найти")
    find_window.geometry("300x100")
    find_window.resizable(False, False)

    # Center the dialog over the main window
    find_window.transient(text_widget.winfo_toplevel())
    find_window.grab_set()

    # Create and pack the widgets for the find dialog
    tk.Label(find_window, text="Найти:").pack(pady=5)

    search_var = tk.StringVar()
    entry = tk.Entry(find_window, textvariable=search_var, width=30)
    entry.pack(pady=5)
    entry.focus()

    button_frame = tk.Frame(find_window)
    button_frame.pack(pady=5)

    def find_next():
        search_term = search_var.get()
        if not search_term:
            return

        # Search for the next occurrence
        start_pos = text_widget.search(search_term, tk.INSERT, tk.END)

        if start_pos:
            # Calculate end position
            end_pos = f"{start_pos}+{len(search_term)}c"

            # Highlight the found text
            text_widget.tag_remove("found", "1.0", tk.END)
            text_widget.tag_add("found", start_pos, end_pos)
            text_widget.tag_config("found", background="yellow", foreground="black")

            # Scroll to the found text
            text_widget.see(start_pos)

            # Move the cursor to the end of the found text for the next search
            text_widget.mark_set(tk.INSERT, end_pos)

    def close_dialog():
        # Remove highlighting when dialog is closed
        text_widget.tag_remove("found", "1.0", tk.END)
        find_window.destroy()

    # Bind Enter key to find_next
    entry.bind('<Return>', lambda e: find_next())

    # Create buttons
    tk.Button(button_frame, text="Найти далее", command=find_next).pack(side=tk.LEFT, padx=5)
    tk.Button(button_frame, text="Закрыть", command=close_dialog).pack(side=tk.LEFT, padx=5)

    # Handle window closing
    find_window.protocol("WM_DELETE_WINDOW", close_dialog)

    # Position the dialog relative to the main window
    x = text_widget.winfo_toplevel().winfo_x() + 50
    y = text_widget.winfo_toplevel().winfo_y() + 50
    find_window.geometry(f"+{x}+{y}")


def _cut_text(text_widget):
    """Cut selected text to clipboard"""
    if isinstance(text_widget, tk.Text):
        # For Text widgets
        if text_widget.tag_ranges("sel"):
            text_widget.clipboard_clear()
            text_widget.clipboard_append(text_widget.get("sel.first", "sel.last"))
            text_widget.delete("sel.first", "sel.last")
    elif isinstance(text_widget, tk.Entry):
        # For Entry widgets
        try:
            text_widget.clipboard_clear()
            selected_text = text_widget.selection_get()
            text_widget.clipboard_append(selected_text)
            text_widget.delete("sel.first", "sel.last")
        except tk.TclError:
            # No selection
            pass
    return "break"  # Prevent default handling


def _copy_text(text_widget):
    """Copy selected text to clipboard"""
    if isinstance(text_widget, tk.Text):
        # For Text widgets
        if text_widget.tag_ranges("sel"):
            text_widget.clipboard_clear()
            text_widget.clipboard_append(text_widget.get("sel.first", "sel.last"))
    elif isinstance(text_widget, tk.Entry):
        # For Entry widgets
        try:
            text_widget.clipboard_clear()
            selected_text = text_widget.selection_get()
            text_widget.clipboard_append(selected_text)
        except tk.TclError:
            # No selection, copy all text
            text_widget.clipboard_clear()
            text_widget.clipboard_append(text_widget.get())
    return "break"  # Prevent default handling


def _paste_text(text_widget):
    """Paste text from clipboard"""
    try:
        clipboard_content = text_widget.clipboard_get()
        if clipboard_content:
            if isinstance(text_widget, tk.Text):
                # For Text widgets
                # Delete selected text if any
                if text_widget.tag_ranges("sel"):
                    text_widget.delete("sel.first", "sel.last")
                text_widget.insert("insert", clipboard_content)
            elif isinstance(text_widget, tk.Entry):
                # For Entry widgets
                # Delete selected text if any
                try:
                    text_widget.delete("sel.first", "sel.last")
                except tk.TclError:
                    # No selection, just insert at cursor
                    pass
                text_widget.insert("insert", clipboard_content)
    except tk.TclError:
        # Clipboard is empty or unavailable
        pass
    return "break"  # Prevent default handling


def _clear_text_widget(text_widget):
    """Clear the content of a text widget"""
    # Enable the widget temporarily to allow editing
    state_before = text_widget.cget("state")
    text_widget.config(state="normal")

    if isinstance(text_widget, tk.Text):
        # For Text widgets
        text_widget.delete(1.0, tk.END)
    elif isinstance(text_widget, tk.Entry):
        # For Entry widgets
        text_widget.delete(0, tk.END)

    # Restore the original state
    text_widget.config(state=state_before)

    # If the widget was originally disabled, make sure it stays disabled
    if state_before == "disabled":
        text_widget.config(state="disabled")


# --- Settings Management ---
SETTINGS_FILE = os.path.join(get_application_path(), 'record_server_settings.json')
DEFAULT_SETTINGS = {
    "port": 8288,
    "server_enabled": True,
    "autostart_server": True, # New setting to control server autostart
    "lan_accessible": False,
    "use_custom_prompt": False,
    "prompt_addition": "",
    # Новая настройка для правил файлов контекста. Заменяет include_html_files.
    "context_file_rules": [
        {
            "pattern": "*.html", 
            "prompt": "\n--- НАЧАЛО файла @{filename} ---\n{content}\n--- КОНЕЦ файла @{filename} ---\n",
            "enabled": True
        }
    ],
    "add_meeting_date": True,
    "meeting_date_source": "current", # 'current' or 'folder'
    "meeting_name_templates": [
        {"id": "default1", "template": "Еженедельное собрание команды"},
        {"id": "default2", "template": "Планирование спринта"}
    ],
    "active_meeting_name_template_id": None,
    "main_window_width": 700,
    "main_window_height": 800,
    "main_window_x": None, 
    "main_window_y": None
}
DEFAULT_SETTINGS["selected_contacts"] = [] # List of selected contact IDs
settings = {}
main_icon = None # Global reference to the pystray icon

def load_settings():
    """Loads settings from the JSON file or creates it with defaults."""
    global settings
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
            for key, value in DEFAULT_SETTINGS.items():
                settings.setdefault(key, value)
        except (json.JSONDecodeError, TypeError):
            settings = DEFAULT_SETTINGS.copy()
    else:
        settings = DEFAULT_SETTINGS.copy()
    save_settings(settings)

def save_settings(new_settings):
    """Saves settings to the JSON file."""
    global settings
    settings = new_settings
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=4)
    print("Settings saved.")

# --- Contacts Management ---
CONTACTS_FILE = os.path.join(get_application_path(), 'contacts.json')
contacts_data = {"groups": []}

def load_contacts():
    """Loads contacts from the JSON file or creates it if it doesn't exist."""
    global contacts_data
    if os.path.exists(CONTACTS_FILE):
        try:
            with open(CONTACTS_FILE, 'r', encoding='utf-8') as f:
                contacts_data = json.load(f)
            if "groups" not in contacts_data:
                contacts_data = {"groups": []}
        except (json.JSONDecodeError, TypeError):
            contacts_data = {"groups": []}
    else:
        contacts_data = {"groups": []}
        save_contacts(contacts_data)

def save_contacts(new_contacts_data):
    """Saves contacts to the JSON file."""
    global contacts_data
    contacts_data = new_contacts_data
    with open(CONTACTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(contacts_data, f, indent=4, ensure_ascii=False)

# --- Load Environment Variables ---
dotenv_path = os.path.join(get_application_path(), '.env')
load_dotenv(dotenv_path)
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")

# --- Глобальные переменные ---
app = Flask(
    __name__,
    template_folder=os.path.join(get_application_path(), 'templates'),
    static_folder=os.path.join(get_application_path(), 'static')
)
is_recording = False
is_paused = False  # Track pause state
start_time = None
pause_start_time = None  # Track when pause started
total_pause_duration = 0.0  # Total duration of pauses
recording_threads = []
stop_event = Event()
frames = {}
temp_buffers = {}  # Temporary buffers for real-time mixing
CHANNELS = 2
FORMAT = pyaudio.paInt16  # Keep for compatibility, though we're using sounddevice now

audio_queue = queue.Queue()
recording_thread = None

flask_thread = None
http_server = None

# Variable to store available audio devices

# Variables for post-processing status
is_post_processing = False  # Track if post-processing is happening
post_process_file_path = ""  # Track the file being processed
post_process_stage = ""  # Track the current stage (transcribe, protocol, etc.)

# --- Глобальные переменные для уровней звука ---
audio_levels = {"mic": 0.0, "sys": 0.0}
monitoring_stop_event = Event()


# --- Server Lifecycle Management ---
def start_server():
    global flask_thread
    flask_thread = None
    if settings.get("server_enabled"):
        if flask_thread and flask_thread.is_alive():
            print("Server thread is already running.")
            return
        flask_thread = Thread(target=run_flask, daemon=True)
        flask_thread.start()
        print("Flask server thread started.")
    update_tray_menu()

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
    update_tray_menu()

def restart_server(old_settings):
    stop_server(old_settings)
    start_server()

def update_tray_menu():
    """Updates the tray menu items based on current settings."""
    if main_icon:
        server_is_on = settings.get("server_enabled")

        # Determine current recording state using internal variables
        if is_recording and not is_paused:
            # Recording is active, show pause option
            main_icon.menu = Menu(
                item('Начать запись', start_recording_from_tray, enabled=False),  # Disabled since recording is active
                item('Приостановить запись', pause_recording_from_tray, enabled=True),  # Always enabled if recording is active
                item('Остановить запись', stop_recording_from_tray, enabled=True),  # Always enabled if recording is active
                Menu.SEPARATOR,
                item('Веб-интерфейс', open_web_interface, enabled=server_is_on),
                item('Настройки', open_main_window),
                item('Открыть папку с записями', open_rec_folder),
                Menu.SEPARATOR,
                item('Выход', exit_action)
            )
        elif is_recording and is_paused:
            # Recording is paused, show resume option
            main_icon.menu = Menu(
                item('Начать запись', start_recording_from_tray, enabled=False),  # Disabled since recording is active
                item('Возобновить запись', resume_recording_from_tray, enabled=True),  # Always enabled if paused
                item('Остановить запись', stop_recording_from_tray, enabled=True),  # Always enabled if recording is active
                Menu.SEPARATOR,
                item('Веб-интерфейс', open_web_interface, enabled=server_is_on),
                item('Настройки', open_main_window),
                item('Открыть папку с записями', open_rec_folder),
                Menu.SEPARATOR,
                item('Выход', exit_action)
            )
        else:
            # No active recording, show start option
            main_icon.menu = Menu(
                item('Начать запись', start_recording_from_tray, enabled=True),  # Always enabled when not recording
                item('Приостановить запись', pause_recording_from_tray, enabled=False),  # Always enabled if recording is active
                item('Остановить запись', stop_recording_from_tray, enabled=False),  # Disabled since no recording is active
                Menu.SEPARATOR,
                item('Веб-интерфейс', open_web_interface, enabled=server_is_on),
                item('Настройки', open_main_window),
                item('Открыть папку с записями', open_rec_folder),
                Menu.SEPARATOR,
                item('Выход', exit_action)
            )
# --- Settings Window ---
def open_web_interface(icon=None, item=None):
    """Открывает веб-интерфейс в браузере по умолчанию."""
    if settings.get("server_enabled"):
        import webbrowser
        port = settings.get("port", DEFAULT_SETTINGS["port"])
        url = f"http://127.0.0.1:{port}/"
        webbrowser.open(url)
    else:
        print("Веб-сервер отключен. Невозможно открыть интерфейс.")

main_window_instance = None

def open_main_window(icon=None, item=None):
    global main_window_instance
    # Если окно уже существует, показать его и передать фокус
    if main_window_instance and main_window_instance.winfo_exists():
        main_window_instance.deiconify() # Показываем окно, если оно было скрыто
        main_window_instance.lift()
        main_window_instance.focus_force()
        print("Main window already open. Bringing to front.")
        return

    # Если окно было уничтожено, но ссылка осталась, сбрасываем ее
    main_window_instance = None

    old_settings = settings.copy()
    

    def on_save():
        try:
            new_port = int(port_var.get())
            if not (1024 <= new_port <= 65535):
                raise ValueError("Порт должен быть между 1024 и 65535.")

            # Get current window geometry to save
            geom = win.winfo_geometry()
            x = win.winfo_x()
            y = win.winfo_y()
            width = win.winfo_width()
            height = win.winfo_height()

            new_settings = {
                # Сохраняем старые настройки, чтобы не перезаписать их
                **settings, 
                "port": new_port,
                "server_enabled": server_enabled_var.get(),
                "lan_accessible": lan_accessible_var.get(),
                "main_window_width": width,
                "main_window_height": height,
                "main_window_x": x,
                "main_window_y": y
            }

            restart_needed = (
                old_settings['port'] != new_settings['port'] or
                old_settings['server_enabled'] != new_settings['server_enabled'] or
                old_settings['lan_accessible'] != new_settings['lan_accessible']
            )
            save_settings(new_settings)
            if restart_needed:
                messagebox.showinfo("Применение", "Настройки сохранены. Сервер будет перезапущен.", parent=win)
                restart_server(old_settings)
                mark_as_saved() # Mark as saved after restart
            else:
                messagebox.showinfo("Сохранено", "Настройки сохранены.", parent=win)
                mark_as_saved()

        except ValueError as e:
            messagebox.showerror("Ошибка", f"Неверное значение для порта: {e}", parent=win)

    def on_hide():
        # Save window geometry before closing
        x = win.winfo_x()
        y = win.winfo_y()
        width = win.winfo_width()
        height = win.winfo_height()
        
        new_settings = settings.copy()
        new_settings.update({
            "main_window_width": width,
            "main_window_height": height,
            "main_window_x": x,
            "main_window_y": y
        })
        save_settings(new_settings)

        win.withdraw() # Скрываем окно вместо уничтожения

    def on_destroy():
        on_hide() # Сохраняем геометрию и скрываем
        # Cancel all scheduled 'after' jobs before destroying the window
        if hasattr(win, '_after_jobs'):
            for job_id in win._after_jobs:
                win.after_cancel(job_id)
        global main_window_instance
        main_window_instance = None
        win.destroy()
        
    
    win = tk.Tk()
    win.title("ChroniqueX - Запись @ Транскрибация @ Протоколы") # Title will be updated if changes are made

    # --- Unsaved Changes Logic (Moved after tk.Tk() initialization) ---
    original_settings = {}
    settings_changed = tk.BooleanVar(value=False)

    def mark_as_changed(*args):
        """Marks settings as changed and updates UI."""
        settings_changed.set(True)

    def mark_as_saved():
        """Marks settings as saved and updates UI."""
        settings_changed.set(False)
        # Store the new state as the original state for future comparisons
        capture_original_settings()

    def update_ui_for_changes(*args):
        """Updates window title and save button text based on change status."""
        if settings_changed.get():
            win.title("ChroniqueX - Настройки *")
            save_button.config(text="Сохранить *")
        else:
            win.title("ChroniqueX - Настройки")
            save_button.config(text="Сохранить")

    # Set window size and position from settings
    width = settings.get("main_window_width", 700)
    height = settings.get("main_window_height", 500)
    x = settings.get("main_window_x", None)
    y = settings.get("main_window_y", None)

    win.geometry(f"{width}x{height}")
    if x is not None and y is not None:
        win.geometry(f"+{x}+{y}")

    main_window_instance = win
    win._after_jobs = []

    win.transient(); win.grab_set()
    win.protocol("WM_DELETE_WINDOW", on_hide)  # Handle window close event

    # Configure grid weights for proper resizing
    win.grid_rowconfigure(0, weight=1)
    win.grid_columnconfigure(0, weight=1)

    # Main frame
    main_frame = tk.Frame(win)
    main_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
    main_frame.grid_rowconfigure(1, weight=1)  # Give row 1 (endpoints) weight to expand
    main_frame.grid_columnconfigure(0, weight=1)

    settings_container = tk.Frame(main_frame)
    settings_container.grid(row=0, column=0, sticky="new", padx=10, pady=5)
    settings_container.grid_columnconfigure(0, weight=1)

    # Переменные для виджетов настроек
    port_var = tk.StringVar(value=str(settings.get("port")))
    server_enabled_var = tk.BooleanVar(value=settings.get("server_enabled"))
    lan_accessible_var = tk.BooleanVar(value=settings.get("lan_accessible"))

    # --- Unsaved Changes Logic (continued) ---
    def capture_original_settings():
        original_settings['port'] = port_var.get()
        original_settings['server_enabled'] = server_enabled_var.get()
        original_settings['lan_accessible'] = lan_accessible_var.get()

    # Пустой фрейм для сохранения отступов
    spacer_frame = tk.Frame(settings_container, height=20)
    spacer_frame.pack()

    
    server_settings_frame = tk.Frame(settings_container, padx=10, pady=10)
    server_settings_frame.pack(fill="x", expand=True)
    server_settings_frame.grid_columnconfigure(3, weight=1) # Let the last column expand

    # Endpoints info frame
    endpoints_frame = tk.LabelFrame(main_frame, text="Адреса и эндпоинты сервера", padx=10, pady=10)
    endpoints_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
    endpoints_frame.grid_columnconfigure(0, weight=1)
    
    # Create a frame for the endpoint links
    endpoints_links_frame = tk.Frame(endpoints_frame)
    endpoints_links_frame.pack(fill=tk.BOTH, expand=True)
    
    # Dictionary to store label widgets for later updates
    endpoint_labels = {}
    
    # Function to update endpoint links with current port
    def update_endpoint_links():
        # Destroy existing labels
        for label in endpoint_labels.values():
            label.destroy()
        endpoint_labels.clear()
        
        # Get current port
        current_port = port_var.get() if port_var.get() else "8288"
        
        endpoints_info = [
            ("/", "веб-интерфейс"),
            ("/rec", "начать запись"),
            ("/stop", "остановить запись"),
            ("/pause", "приостановить запись"),
            ("/resume", "возобновить запись"),
            ("/status", "получить статус записи")
        ]

        for i, (endpoint, description) in enumerate(endpoints_info):
            # Create full URL
            full_url = f"http://localhost:{current_port}{endpoint}"
            
            # Create a frame for each row to hold multiple elements
            row_frame = tk.Frame(endpoints_links_frame)
            row_frame.grid(row=i, column=0, sticky="w", padx=5, pady=2)
            
            # Add "GET" as regular text
            get_label = tk.Label(row_frame, text="GET ", anchor="w", justify=tk.LEFT)
            get_label.pack(side=tk.LEFT)
            
            # Create a clickable label for just the URL
            url_label = tk.Label(
                row_frame,
                text=full_url,
                fg="blue",
                cursor="hand2",
                anchor="w",
                justify=tk.LEFT
            )
            url_label.pack(side=tk.LEFT)
            
            # Add description as regular text
            desc_label = tk.Label(row_frame, text=f" - {description}", anchor="w", justify=tk.LEFT)
            desc_label.pack(side=tk.LEFT)
            
            # Bind click event to open URL
            def make_callback(url):
                def callback(event):
                    import webbrowser
                    webbrowser.open(url)
                return callback
            
            url_label.bind("<Button-1>", make_callback(full_url))
            
            # Bind hover events to change cursor only on the URL part
            def on_enter(e):
                e.widget.config(cursor="hand2")
            def on_leave(e):
                e.widget.config(cursor="arrow")  # Use arrow as default cursor
            
            url_label.bind("<Enter>", on_enter)
            url_label.bind("<Leave>", on_leave)
            
            # Store reference to the URL label
            endpoint_labels[endpoint] = url_label
    
    # Call the function to create the links
    update_endpoint_links()
    
    # Add trace to update links when port changes
    def on_port_change(*args):
        update_endpoint_links()
    
    port_var.trace_add("write", on_port_change)

    tk.Label(server_settings_frame, text="Порт:").grid(row=0, column=0, sticky="w", pady=5, padx=(0, 5))
    port_edit = tk.Entry(server_settings_frame, textvariable=port_var)
    port_edit.grid(row=0, column=1, sticky="w", padx=5)
    _add_context_menu_to_text_widget(port_edit)
    tk.Checkbutton(server_settings_frame, text="Сервер запущен", variable=server_enabled_var).grid(row=0, column=2, sticky="w", padx=5)
    tk.Checkbutton(server_settings_frame, text="Доступен по локальной сети (host 0.0.0.0)", variable=lan_accessible_var).grid(row=0, column=3, sticky="w", padx=5)

    button_frame = tk.Frame(server_settings_frame)
    button_frame.grid(row=1, columnspan=4, pady=10)
    save_button = tk.Button(button_frame, text="Сохранить", command=on_save)
    save_button.pack(side="left", padx=5)
    tk.Button(button_frame, text="Свернуть", command=on_hide).pack(side="left", padx=5)

    # --- Unsaved Changes Logic (final part) ---
    # Capture initial state
    capture_original_settings()
    settings_changed.trace_add("write", update_ui_for_changes)
    # Trace changes on all variable-based widgets
    port_var.trace_add("write", mark_as_changed)
    server_enabled_var.trace_add("write", mark_as_changed)
    lan_accessible_var.trace_add("write", mark_as_changed)
    win.mainloop()

# --- Post-processing, Audio Recording, and other functions (mostly unchanged) ---
def post_task(file_path, task_type, prompt_addition_str=None, add_participants_prompt=False):
    if not API_URL or not API_KEY: return None
    try:
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f)}
            data = {'api_key': API_KEY, 'task_type': task_type}
            
            # --- Contact List Integration ---
            selected_contact_ids = set(settings.get("selected_contacts", []))
            num_speakers_from_contacts = len(selected_contact_ids)
            
            participants_prompt = ""
            if num_speakers_from_contacts > 0:
                # Группируем выбранных участников по их группам
                participants_by_group = {}
                for group in contacts_data.get("groups", []):
                    group_name = group.get("name", "Без группы")
                    for contact in group.get("contacts", []):
                        if contact.get("id") in selected_contact_ids:
                            if group_name not in participants_by_group:
                                participants_by_group[group_name] = []
                            participants_by_group[group_name].append(contact.get("name"))
                
                if participants_by_group:
                    prompt_lines = ["# Список участников:\n"]
                    # Сортируем группы по имени для консистентности
                    for group_name in sorted(participants_by_group.keys()):
                        prompt_lines.append(f"## Группа: {group_name}")
                        # Сортируем участников внутри группы
                        for participant_name in sorted(participants_by_group[group_name]):
                            prompt_lines.append(f"- {participant_name}")
                        prompt_lines.append("") # Пустая строка после каждой группы
                    
                    participants_prompt = "\n".join(prompt_lines)

            # Add prompt_addition if it's a protocol task and prompt_addition is provided
            if task_type == 'protocol' and (prompt_addition_str or (add_participants_prompt and participants_prompt)):
                data['prompt_addition'] = (participants_prompt if add_participants_prompt else "") + (prompt_addition_str or "")

            # Количество спикеров определяется по количеству выбранных контактов
            if task_type == 'transcribe':
                if num_speakers_from_contacts > 0:
                    data['num_speakers'] = num_speakers_from_contacts
            
            # --- Logging ---
            # Создаем копию данных для логирования, чтобы не изменять оригинал и не светить ключ
            log_data = data.copy()
            if 'api_key' in log_data:
                log_data['api_key'] = '***' # Маскируем ключ API
            if 'prompt_addition' in log_data and log_data['prompt_addition']:
                log_data['prompt_addition'] = log_data['prompt_addition'][:100] + '...' # Укорачиваем промпт
            logging.info(f"Отправка задачи: файл='{os.path.basename(file_path)}', параметры={log_data}")

            # Disable SSL certificate verification for self-signed certificates
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
def poll_and_save_result(task_id, output_path):
    if not task_id: return False
    while True:
        try:
            # Disable SSL certificate verification for self-signed certificates
            response = requests.get(f"{API_URL}/get_result/{task_id}", timeout=10, verify=False)
            if response.status_code == 200:
                with open(output_path, 'wb') as f: f.write(response.content)
                logging.info(f"Задача {task_id} успешно завершена. Результат сохранен в {output_path}")
                return True
            elif response.status_code == 202: time.sleep(5)
            elif response.status_code == 500:
                print(f"Задача {task_id} провалена: {response.json().get('error', 'Неизвестная ошибка')}")
                error_msg = response.json().get('error', 'Неизвестная ошибка')
                logging.error(f"Задача {task_id} провалена на сервере: {error_msg}")
                return False
            else: time.sleep(10)
        except requests.exceptions.RequestException as e:
            logging.warning(f"Ошибка соединения при проверке статуса задачи {task_id}: {e}. Повтор через 10 секунд...")
            print(f"Ошибка соединения при проверке статуса задачи {task_id}: {e}. Повтор через 10 секунд...")
            time.sleep(10)


def get_elapsed_record_time():
    """Calculate elapsed recording time accounting for pauses"""
    if not start_time:
        return 0
    
    current_time = datetime.now()
    elapsed = (current_time - start_time).total_seconds()
    
    # Subtract total pause duration
    elapsed -= total_pause_duration
    
    # If currently paused, subtract time since pause started
    if is_paused and pause_start_time:
        pause_since = (current_time - pause_start_time).total_seconds()
        elapsed -= pause_since
    
    return max(elapsed, 0)  # Ensure non-negative result


def periodic_tray_menu_update():
    """Periodically update the tray menu to reflect current state"""
    last_state = (is_recording, is_paused)
    while True:
        current_state = (is_recording, is_paused)
        if current_state != last_state:
            try:
                update_tray_menu()
                last_state = current_state
            except Exception as e:
                print(f"Error updating tray menu: {e}")
        
        time.sleep(0.5)  # Update every 0.5 seconds

def process_recording_tasks(file_path):
    global is_post_processing, post_process_file_path, post_process_stage
    print(f"--- Начало постобработки для файла: {file_path} ---")
    
    # Update post-processing status
    is_post_processing = True
    post_process_file_path = file_path
    post_process_stage = "transcribe"
    
    base_name, _ = os.path.splitext(file_path)
    txt_output_path = base_name + ".txt"
    transcription_task_id = post_task(file_path, "transcribe")
    if transcription_task_id and poll_and_save_result(transcription_task_id, txt_output_path):
        print(f"Транскрибация успешна. Начало создания протокола из {txt_output_path}")

        # Reload settings to get the most recent prompt addition
        load_settings()

        # Check for custom prompt addition from settings
        if settings.get("use_custom_prompt", False):
            prompt_addition = settings.get("prompt_addition", "")
        else:
            prompt_addition = ""

        # Replace {current_date} placeholder with current date in 'DD MMMMM YYYY' format
        current_date_formatted = format_date_russian(datetime.now())
        prompt_addition = prompt_addition.replace("{current_date}", current_date_formatted)

        # --- Meeting Name addition logic ---
        meeting_name_prompt_addition = ""
        active_template_id = settings.get("active_meeting_name_template_id")
        if active_template_id:
            templates = settings.get("meeting_name_templates", [])
            active_template = next((t for t in templates if t.get("id") == active_template_id), None)
            if active_template:
                template_text = active_template.get("template", "")
                if template_text:
                    meeting_name_prompt_addition = f"# Название собрания: {template_text}\n\n"

        # --- Date addition logic ---
        date_prompt_addition = ""
        if settings.get("add_meeting_date", False):
            date_source = settings.get("meeting_date_source", "current")
            meeting_date = None
            if date_source == 'folder':
                try:
                    # file_path is like '.../rec/2023-10-27/somefile.mp3'
                    date_str = Path(file_path).parent.name
                    meeting_date = datetime.strptime(date_str, '%Y-%m-%d')
                except (ValueError, IndexError):
                    print(f"Could not parse date from folder name: {Path(file_path).parent.name}. Falling back to current date.")
                    meeting_date = datetime.now()
            else: # 'current'
                meeting_date = datetime.now()
            
            if meeting_date:
                formatted_date = format_date_russian(meeting_date)
                date_prompt_addition = f"# Дата собрания: {formatted_date}\n\n"

        # --- Новая логика для файлов контекста ---
        context_rules = settings.get("context_file_rules", [])
        audio_path = Path(file_path)
        for rule in context_rules:
            # Проверяем, включено ли правило
            if not rule.get("enabled", False):
                continue

            pattern = rule.get("pattern")
            prompt_template = rule.get("prompt")
            if not pattern or not prompt_template:
                continue

            # Ищем файлы по шаблону в папке с аудиофайлом
            found_files = sorted(list(audio_path.parent.glob(pattern)))
            for found_file in found_files:
                try:
                    print(f"Обработка файла контекста: {found_file.name} по правилу '{pattern}'")
                    with open(found_file, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Для HTML файлов применяем специальную обработку для уменьшения контекста
                    if found_file.suffix.lower() == '.html':
                        allowed_tags = {'table', 'tr', 'td', 'th', 'tbody', 'thead', 'tfoot'}
                        def should_keep_tag(match):
                            tag = match.group(0); is_closing = tag.startswith('</'); tag_name = tag.strip('</>').split()[0].lower()
                            return f'</{tag_name}>' if is_closing and tag_name in allowed_tags else f'<{tag_name}>' if tag_name in allowed_tags else ' '
                        content = re.sub(r'<[^>]+>', should_keep_tag, content).strip()

                    if content:
                        formatted_prompt = prompt_template.replace("{filename}", found_file.name).replace("{content}", content)
                        prompt_addition += formatted_prompt
                        print(f"Добавлен контент из файла: {found_file.name}")
                except Exception as e:
                    print(f"Не удалось прочитать или обработать файл контекста {found_file}: {e}")

        # Filter out lines that start with "//" from prompt_addition
        filtered_prompt_addition = "\n".join([
            line for line in prompt_addition.splitlines() 
            if not line.strip().startswith("//")
        ])

        # --- Формирование списка участников для сохранения в promptAddition ---
        selected_contact_ids = set(settings.get("selected_contacts", []))
        participants_prompt_for_metadata = ""
        if selected_contact_ids:
            participants_by_group = {}
            for group in contacts_data.get("groups", []):
                group_name = group.get("name", "Без группы")
                for contact in group.get("contacts", []):
                    if contact.get("id") in selected_contact_ids:
                        if group_name not in participants_by_group:
                            participants_by_group[group_name] = []
                        participants_by_group[group_name].append(contact.get("name"))
            if participants_by_group:
                prompt_lines = ["# Список участников:\n"]
                for group_name in sorted(participants_by_group.keys()):
                    prompt_lines.append(f"## Группа: {group_name}")
                    for participant_name in sorted(participants_by_group[group_name]):
                        prompt_lines.append(f"- {participant_name}")
                    prompt_lines.append("")
                participants_prompt_for_metadata = "\n".join(prompt_lines)

        # Update post-processing status for protocol stage
        post_process_stage = "protocol"
        
        # Собираем финальную строку для промпта в правильном порядке
        final_prompt_addition = date_prompt_addition + meeting_name_prompt_addition + participants_prompt_for_metadata + filtered_prompt_addition
        
        protocol_task_id = post_task(txt_output_path, "protocol", prompt_addition_str=final_prompt_addition, add_participants_prompt=False) # add_participants_prompt=False, так как они уже в строке
        if protocol_task_id:
            protocol_output_path = base_name + "_protocol.pdf"

            # --- Сохранение добавки к промпту в метаданные ---
            json_path = base_name + '.json'
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r+', encoding='utf-8') as f: # Открываем для чтения и записи
                        metadata = json.load(f)
                        metadata['promptAddition'] = final_prompt_addition
                        f.seek(0)
                        json.dump(metadata, f, indent=4, ensure_ascii=False)
                        f.truncate()
                except Exception as e:
                    print(f"Не удалось обновить метаданные с промптом для {json_path}: {e}")

            # Теперь результат сохраняется только в правильный PDF файл
            poll_and_save_result(protocol_task_id, protocol_output_path)
    
    # Reset post-processing status
    is_post_processing = False
    post_process_file_path = ""
    post_process_stage = ""

    print(f"--- Завершение постобработки для файла: {file_path} ---")

def recorder_mic(device_index, stop_event, audio_queue):
    """Records audio from microphone using sounddevice."""
    def callback(indata, frames, time, status):
        if status:
            print(status, file=sys.stderr)
        if not is_paused:
            # Put audio data into the shared queue for the mixer
            audio_queue.put(indata.copy())

    try:
        with sd.InputStream(samplerate=RATE, device=device_index, channels=1, dtype='int16', callback=callback):
            print(f"Recording started for mic device {device_index}.")
            # Keep the stream open while the stop event is not set
            stop_event.wait()
    except Exception as e:
        print(f"Error during mic recording: {e}", file=sys.stderr)
    finally:
        print(f"Mic recording process finished for device {device_index}.")

def recorder_sys(stop_event, audio_queue):
    """Records system audio using pyaudiowpatch."""
    try:
        with pyaudio.PyAudio() as p:
            wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])

            if not default_speakers["isLoopbackDevice"]:
                for loopback in p.get_loopback_device_info_generator():
                    if default_speakers["name"] in loopback["name"]:
                        default_speakers = loopback
                        break
                else:
                    print("Не удалось найти loopback-устройство для системного звука.", file=sys.stderr)
                    return

            print(f"Recording from: ({default_speakers['index']}){default_speakers['name']}")

            channels = default_speakers["maxInputChannels"]

            def callback(in_data, frame_count, time_info, status):
                if not is_paused:
                    # Преобразуем байты в numpy массив и сразу добавляем в очередь
                    # Это немного быстрее, чем создавать промежуточные переменные
                    audio_queue.put(np.frombuffer(in_data, dtype=np.int16).reshape(-1, channels))
                return (in_data, pyaudio.paContinue)

            stream = p.open(format=pyaudio.paInt16,
                            channels=channels,
                            rate=RATE,
                            input=True,
                            input_device_index=default_speakers["index"],
                            stream_callback=callback,
                            # Используем флаг для повышения приоритета потока обработки аудио, если PaWasapiStreamInfo доступен.
                            # Это помогает обеспечить более стабильный поток данных и избежать "рваной" записи.
                            input_host_api_specific_stream_info=PaWasapiStreamInfo(flags=pyaudio.paWinWasapiThreadPriority)
                                if PaWasapiStreamInfo else None
                            )

            stream.start_stream()
            print("System audio recording started.")
            while not stop_event.is_set():
                time.sleep(0.001) # Prevent busy-waiting and allow other threads to run
            stream.stop_stream()
            stream.close()
    except Exception as e:
        print(f"Error during system audio recording: {e}", file=sys.stderr)
    finally:
        print("System audio recording process finished.")

def get_date_dirs_data():
    """Gathers and structures date directory data from the 'rec' directory."""
    date_groups = []
    rec_dir = os.path.join(get_application_path(), 'rec')
    
    if os.path.exists(rec_dir):
        date_dirs = [d for d in os.listdir(rec_dir) if os.path.isdir(os.path.join(rec_dir, d))]
        
        day_names = {
            0: 'Понедельник', 1: 'Вторник', 2: 'Среда', 3: 'Четверг',
            4: 'Пятница', 5: 'Суббота', 6: 'Воскресенье'
        }
        
        for date_dir in date_dirs:
            try:
                date_obj = datetime.strptime(date_dir, '%Y-%m-%d')
                day_of_week = day_names[date_obj.weekday()]
                
                months = {
                    1: 'Января', 2: 'Февраля', 3: 'Марта', 4: 'Апреля', 5: 'Мая', 6: 'Июня',
                    7: 'Июля', 8: 'Августа', 9: 'Сентября', 10: 'Октября', 11: 'Ноября', 12: 'Декабря'
                }
                formatted_date = f"{date_obj.day:02d} {months[date_obj.month]} {date_obj.year}"
                
                date_groups.append({
                    'date': date_dir,
                    'day_of_week': day_of_week,
                    'formatted_date': formatted_date,
                })
            except ValueError:
                # If parsing fails, skip this directory
                continue
    
    date_groups.sort(key=lambda x: x['date'], reverse=True)
    return date_groups

def get_recordings_for_date_data(date_dir):
    """Gathers and structures recording data for a specific date directory."""
    recordings_in_group = []
    rec_dir = os.path.join(get_application_path(), 'rec')
    date_path = os.path.join(rec_dir, date_dir)

    if not os.path.isdir(date_path):
        return []

    all_files = [f for f in os.listdir(date_path) if os.path.isfile(os.path.join(date_path, f))]
    
    file_groups = {}
    for filename in all_files:
        name, ext = os.path.splitext(filename)
        if name not in file_groups:
            file_groups[name] = {}
        file_groups[name][ext] = filename
    
    for base_name, file_dict in file_groups.items():
        audio_filename = None
        
        if '.wav' in file_dict:
            audio_filename = file_dict['.wav']
        elif '.mp3' in file_dict:
            audio_filename = file_dict['.mp3']
        
        if audio_filename:
            audio_filepath = os.path.join(date_path, audio_filename)
            txt_filename = base_name + ".txt"
            txt_filepath = os.path.join(date_path, txt_filename)
            
            protocol_filename = None
            protocol_filepath = None
            
            protocol_pdf_path = os.path.join(date_path, base_name + "_protocol.pdf")
            if os.path.exists(protocol_pdf_path):
                protocol_filename = base_name + "_protocol.pdf"
                protocol_filepath = protocol_pdf_path
            # ... (rest of the protocol file checking logic can be added here if needed)
            
            file_time = datetime.fromtimestamp(os.path.getctime(audio_filepath))
            json_path = os.path.join(date_path, base_name + '.json')
            
            # Load metadata from JSON if it exists
            metadata = {}
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                except (json.JSONDecodeError, TypeError):
                    print(f"  - Warning: Could not decode JSON for {audio_filename}")
            
            # Получаем данные из JSON, если он есть, иначе используем фолбэки
            title = metadata.get('title', base_name)
            if 'startTime' in metadata:
                start_time_obj = datetime.fromisoformat(metadata['startTime'])
                display_time = start_time_obj.strftime('%H:%M:%S')
            else:
                start_time_obj = file_time
                display_time = file_time.strftime('%H:%M:%S')
            
            duration = metadata.get('duration')
            if duration is None and os.path.exists(audio_filepath):
                try:
                    duration = len(AudioSegment.from_file(audio_filepath)) / 1000.0
                except Exception:
                    duration = 0
            elif duration is None:
                duration = 0
            
            recording_info = {
                'filename': audio_filename,
                'size': os.path.getsize(audio_filepath),
                'time': display_time,
                'transcription_exists': os.path.exists(txt_filepath),
                'transcription_filename': txt_filename,
                'protocol_exists': protocol_filepath is not None,
                'protocol_filename': protocol_filename,
                'title': title,
                'startTime': start_time_obj.isoformat(), # Оставляем для сортировки
                'promptAddition': metadata.get('promptAddition', ''),
                'duration': duration
            }
            recordings_in_group.append(recording_info)
    
    recordings_in_group.sort(key=lambda x: x['time'], reverse=True)
    return recordings_in_group

def get_recordings_last_modified():
    """Возвращает время последнего изменения в папке с записями."""
    rec_dir = os.path.join(get_application_path(), 'rec')
    if not os.path.exists(rec_dir):
        return 0
    
    latest_mtime = 0
    for root, _, files in os.walk(rec_dir):
        for file in files:
            # Consider only relevant file types
            if file.endswith(('.wav', '.mp3', '.txt', '.pdf', '.json')):
                try:
                    file_path = os.path.join(root, file)
                    mtime = os.path.getmtime(file_path)
                    if mtime > latest_mtime:
                        latest_mtime = mtime
                except OSError:
                    continue
    return latest_mtime

@app.route('/')
def index():    
    date_groups = get_date_dirs_data()
    # Pass current settings to the template
    return render_template('index.html', date_groups=date_groups)

@app.route('/get_date_dirs', methods=['GET'])
def get_date_dirs():
    return jsonify(get_date_dirs_data())

@app.route('/get_recordings_for_date/<date_str>', methods=['GET'])
def get_recordings_for_date(date_str):
    # Basic validation for the date string to prevent directory traversal
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return jsonify({"error": "Invalid date format"}), 400
    recordings = get_recordings_for_date_data(date_str)
    return jsonify(recordings)

@app.route('/recordings_state', methods=['GET'])
def recordings_state():
    """Возвращает время последнего изменения в папке с записями."""
    return jsonify({"last_modified": get_recordings_last_modified()})

@app.route('/preview_prompt_addition', methods=['GET'])
def preview_prompt_addition():
    """
    Генерирует и возвращает предпросмотр "добавки к промпту"
    на основе текущих настроек.
    """
    try:
        # Загружаем самые свежие настройки и контакты
        load_settings()
        load_contacts()

        # --- Логика сборки промпта (аналогично process_protocol_task) ---

        # 1. Добавка из textarea
        prompt_addition = settings.get("prompt_addition", "") if settings.get("use_custom_prompt", False) else ""
        prompt_addition = prompt_addition.replace("{current_date}", format_date_russian(datetime.now()))

        # 2. Название собрания
        meeting_name_prompt_addition = ""
        active_template_id = settings.get("active_meeting_name_template_id")
        if active_template_id:
            templates = settings.get("meeting_name_templates", [])
            active_template = next((t for t in templates if t.get("id") == active_template_id), None)
            if active_template and active_template.get("template"):
                meeting_name_prompt_addition = f"# Название собрания: {active_template.get('template')}\n\n"

        # 3. Дата собрания
        date_prompt_addition = ""
        if settings.get("add_meeting_date", False):
            # Для предпросмотра всегда используем текущую дату, т.к. папки еще нет
            formatted_date = format_date_russian(datetime.now())
            date_prompt_addition = f"# Дата собрания: {formatted_date}\n\n"

        # 4. Файлы контекста
        context_files_prompt_addition = ""
        context_rules = settings.get("context_file_rules", [])
        # Для предпросмотра ищем файлы в корневой папке 'rec'
        rec_dir = Path(os.path.join(get_application_path(), 'rec'))
        if rec_dir.exists() and context_rules:
            for rule in context_rules:
                if not rule.get("enabled", False):
                    continue
                pattern = rule.get("pattern")
                prompt_template = rule.get("prompt")
                if not pattern or not prompt_template:
                    continue

                found_files = sorted(list(rec_dir.glob(pattern)))
                for found_file in found_files:
                    try:
                        with open(found_file, 'r', encoding='utf-8') as f:
                            # Читаем только первые 500 символов + запас для безопасности
                            content = f.read(550)
                            if len(content) > 500:
                                content = content[:500] + "..."
                        if content:
                            formatted_prompt = prompt_template.replace("{filename}", found_file.name).replace("{content}", content)
                            context_files_prompt_addition += formatted_prompt
                    except Exception as e:
                        print(f"Не удалось прочитать файл контекста для предпросмотра {found_file}: {e}")
        
        # Объединяем добавку из textarea и из файлов
        combined_prompt_addition = prompt_addition + context_files_prompt_addition
        filtered_prompt_addition = "\n".join([line for line in combined_prompt_addition.splitlines() if not line.strip().startswith("//")])

        # 5. Список участников
        participants_prompt = ""
        selected_contact_ids = set(settings.get("selected_contacts", []))
        if selected_contact_ids:
            participants_by_group = {}
            for group in contacts_data.get("groups", []):
                group_name = group.get("name", "Без группы")
                for contact in group.get("contacts", []):
                    if contact.get("id") in selected_contact_ids:
                        if group_name not in participants_by_group:
                            participants_by_group[group_name] = []
                        participants_by_group[group_name].append(contact.get("name"))
            if participants_by_group:
                prompt_lines = ["# Список участников:\n"]
                for group_name in sorted(participants_by_group.keys()):
                    prompt_lines.append(f"## Группа: {group_name}")
                    for participant_name in sorted(participants_by_group[group_name]):
                        prompt_lines.append(f"- {participant_name}")
                    prompt_lines.append("")
                participants_prompt = "\n".join(prompt_lines)

        # Собираем финальную строку в правильном порядке
        final_prompt_text = date_prompt_addition + meeting_name_prompt_addition + participants_prompt + filtered_prompt_addition
        return jsonify({"prompt_text": final_prompt_text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/update_metadata/<date_str>/<filename>', methods=['POST'])
def update_metadata(date_str, filename):
    """Updates the title in the metadata JSON file."""
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return jsonify({"error": "Invalid date format"}), 400

    data = request.get_json()
    new_title = data.get('title')
    if not new_title:
        return jsonify({"error": "Title cannot be empty"}), 400

    rec_dir = os.path.join(get_application_path(), 'rec')
    base_name, _ = os.path.splitext(filename)
    json_path = os.path.join(rec_dir, date_str, base_name + '.json')

    if not os.path.exists(json_path):
        return jsonify({"error": "Metadata file not found"}), 404

    with open(json_path, 'r+', encoding='utf-8') as f:
        metadata = json.load(f)
        metadata['title'] = new_title
        f.seek(0)
        json.dump(metadata, f, indent=4, ensure_ascii=False)
        f.truncate()

    return jsonify({"status": "ok", "message": "Metadata updated successfully."})

# Route to serve recorded files
@app.route('/files/<path:filepath>')
def serve_recorded_file(filepath):
    rec_dir = os.path.join(get_application_path(), 'rec')
    file_path = os.path.join(rec_dir, filepath)
    
    # Security check to prevent directory traversal
    if not os.path.abspath(file_path).startswith(os.path.abspath(rec_dir)):
        return "Access denied", 403
    
    if os.path.exists(file_path):
        # Determine the file type and set appropriate response headers
        import mimetypes
        mime_type, _ = mimetypes.guess_type(file_path)
        
        if mime_type:
            # For text files, set the content type to display in browser
            if mime_type.startswith('text/') or filepath.lower().endswith(('.txt', '.md')):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                # For markdown files, set appropriate content type
                if filepath.lower().endswith('.md'):
                    return Response(content, mimetype='text/markdown; charset=utf-8')
                else:
                    return Response(content, mimetype='text/plain; charset=utf-8')
            # For PDF files, set the content type to display in browser
            elif mime_type == 'application/pdf':
                return send_file(file_path, mimetype='application/pdf')
            # For audio/video files, set the content type to display in browser
            elif mime_type.startswith(('audio/', 'video/')):
                return send_file(file_path, mimetype=mime_type)
            else:
                # For other file types, use send_file with appropriate mimetype
                return send_file(file_path, mimetype=mime_type)
        else:
            # If we can't determine the mime type, try to guess based on extension
            if filepath.lower().endswith('.txt'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return Response(content, mimetype='text/plain; charset=utf-8')
            elif filepath.lower().endswith('.md'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return Response(content, mimetype='text/markdown; charset=utf-8')
            elif filepath.lower().endswith('.pdf'):
                return send_file(file_path, mimetype='application/pdf')
            else:
                return send_file(file_path)
    else:
        return "File not found", 404

@app.route('/save_web_settings', methods=['POST'])
def save_web_settings():
    """Saves settings received from the web UI."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "Нет данных"}), 400

        # Update only the settings from the web UI
        # Use .get() to avoid errors if a key is missing in the request
        # This allows partial updates (e.g., only updating contacts)
        for key in ['use_custom_prompt', 'prompt_addition', 'selected_contacts', 'context_file_rules',
                    'add_meeting_date', 'meeting_date_source', 'meeting_name_templates',
                    'active_meeting_name_template_id']:
            if key in data:
                settings[key] = data[key]

        save_settings(settings) # Save all settings
        return jsonify({"status": "ok", "message": "Настройки успешно сохранены!"})
    except Exception as e:
        print(f"Error saving web settings: {e}")
        return jsonify({"status": "error", "message": f"Ошибка при сохранении настроек: {e}"}), 500

@app.route('/get_web_settings', methods=['GET'])
def get_web_settings():
    """Возвращает текущие настройки для веб-интерфейса в формате JSON."""
    web_settings = {
        "use_custom_prompt": settings.get("use_custom_prompt", False),
        "prompt_addition": settings.get("prompt_addition", ""),
        "selected_contacts": settings.get("selected_contacts", []),
        "context_file_rules": settings.get("context_file_rules", []),
        "add_meeting_date": settings.get("add_meeting_date", True),
        "meeting_date_source": settings.get("meeting_date_source", "current"),
        "meeting_name_templates": settings.get("meeting_name_templates", []),
        "active_meeting_name_template_id": settings.get("active_meeting_name_template_id", None),
    }
    return jsonify(web_settings)

@app.route('/get_contacts', methods=['GET'])
def get_contacts():
    """Returns the current contacts list."""
    # Сортируем группы по имени перед отправкой
    contacts_data.get("groups", []).sort(key=lambda g: g.get("name", ""))
    return jsonify(contacts_data)

@app.route('/get_group_names', methods=['GET'])
def get_group_names():
    """Returns a list of existing group names."""
    # Используем set для получения уникальных имен, затем сортируем
    group_names = sorted(list(set([group.get("name") for group in contacts_data.get("groups", []) if group.get("name")])))
    return jsonify(group_names)

@app.route('/contacts/add', methods=['POST'])
def add_contact_web():
    """Adds a new contact."""
    data = request.get_json()
    name = data.get('name', '').strip()
    group_name = data.get('group_name', 'Без группы').strip()
    if not group_name: group_name = 'Без группы'

    if not name:
        return jsonify({"status": "error", "message": "Имя не может быть пустым"}), 400

    # Специальный случай для создания пустой группы
    if name == '_init_group_':
        # Если имя группы не пустое, создаем группу, если она не существует
        if group_name:
            group_exists = any(g['name'] == group_name for g in contacts_data.get("groups", []))
            if not group_exists:
                contacts_data.setdefault('groups', []).append({"name": group_name, "contacts": []})
                save_contacts(contacts_data)
                return jsonify({"status": "ok", "message": "Группа создана"})
        # Возвращаем 'ok', даже если группа уже существует или имя группы пустое, чтобы не вызывать ошибку в UI
        return jsonify({"status": "ok", "message": "Действие обработано"})

    new_contact = {"id": str(uuid.uuid4()), "name": name}

    group_found = False
    for group in contacts_data.get("groups", []):
        if group['name'] == group_name:
            group.setdefault('contacts', []).append(new_contact)
            group_found = True
            break
    if not group_found:
        contacts_data.setdefault('groups', []).append({"name": group_name, "contacts": [new_contact]})

    save_contacts(contacts_data)
    return jsonify({"status": "ok", "contact": new_contact})

@app.route('/contacts/update/<contact_id>', methods=['POST'])
def update_contact_web(contact_id):
    """Updates an existing contact."""
    data = request.get_json()
    new_name = data.get('name', '').strip()

    if not new_name:
        return jsonify({"status": "error", "message": "Имя не может быть пустым"}), 400

    for group in contacts_data.get("groups", []):
        for contact in group.get("contacts", []):
            if contact.get("id") == contact_id:
                contact["name"] = new_name
                save_contacts(contacts_data)
                return jsonify({"status": "ok", "message": "Участник обновлен"})

    return jsonify({"status": "error", "message": "Участник не найден"}), 404

@app.route('/contacts/delete/<contact_id>', methods=['POST'])
def delete_contact_web(contact_id):
    """Deletes a contact."""
    contact_found = False
    for group in contacts_data.get("groups", []):
        original_len = len(group.get("contacts", []))
        group["contacts"] = [c for c in group.get("contacts", []) if c.get("id") != contact_id]
        if len(group.get("contacts", [])) < original_len:
            contact_found = True
            break
    
    if not contact_found:
        return jsonify({"status": "error", "message": "Участник не найден"}), 404

    # Remove empty groups
    contacts_data["groups"] = [g for g in contacts_data.get("groups", []) if g.get("contacts")]

    # Также удаляем контакт из списка выбранных в настройках
    if contact_id in settings.get("selected_contacts", []):
        settings["selected_contacts"].remove(contact_id)
        # Сохраняем обновленные настройки (без перезапуска сервера)
        save_settings(settings)

    save_contacts(contacts_data)
    return jsonify({"status": "ok", "message": "Участник удален"})

@app.route('/groups/update', methods=['POST'])
def update_group_web():
    """Updates an existing group's name."""
    data = request.get_json()
    old_name = data.get('old_name', '').strip()
    new_name = data.get('new_name', '').strip()

    if not old_name or not new_name:
        return jsonify({"status": "error", "message": "Имя группы не может быть пустым"}), 400

    if old_name == new_name:
        return jsonify({"status": "ok", "message": "Имя группы не изменилось"})

    # Проверяем, не существует ли уже группа с новым именем
    if any(g.get('name') == new_name for g in contacts_data.get("groups", [])):
        return jsonify({"status": "error", "message": f"Группа с именем '{new_name}' уже существует"}), 409 # 409 Conflict

    for group in contacts_data.get("groups", []):
        if group.get("name") == old_name:
            group["name"] = new_name
            save_contacts(contacts_data)
            return jsonify({"status": "ok", "message": "Группа переименована"})

    return jsonify({"status": "error", "message": "Группа не найдена"}), 404

@app.route('/groups/delete', methods=['POST'])
def delete_group_web():
    """Deletes an entire group."""
    data = request.get_json()
    group_name = data.get('name', '').strip()

    if not group_name:
        return jsonify({"status": "error", "message": "Имя группы не может быть пустым"}), 400

    # Находим группу для удаления, чтобы получить ID ее участников
    group_to_delete = next((g for g in contacts_data.get("groups", []) if g.get("name") == group_name), None)

    if not group_to_delete:
        return jsonify({"status": "error", "message": "Группа не найдена"}), 404

    # Собираем ID всех участников в удаляемой группе
    contact_ids_to_remove = {c.get("id") for c in group_to_delete.get("contacts", []) if c.get("id")}

    # Удаляем саму группу
    contacts_data["groups"] = [g for g in contacts_data.get("groups", []) if g.get("name") != group_name]

    # Также удаляем участников этой группы из списка выбранных в настройках
    if contact_ids_to_remove and "selected_contacts" in settings:
        settings["selected_contacts"] = [cid for cid in settings.get("selected_contacts", []) if cid not in contact_ids_to_remove]
        save_settings(settings)

    save_contacts(contacts_data)
    return jsonify({"status": "ok", "message": "Группа удалена"})

@app.route('/shutdown', methods=['POST'])
def shutdown():
    def do_shutdown():
        global http_server
        if http_server:
            # This must be called from a separate thread
            http_server.shutdown()

    Thread(target=do_shutdown).start()
    return 'Server is shutting down...'

@app.route('/rec', methods=['GET'])
def rec():
    global is_recording, is_paused
    # Запускаем start_recording_from_tray в отдельном потоке, чтобы немедленно вернуть ответ веб-интерфейсу.
    # Это предотвращает ошибку "Ошибка начала записи" в браузере.
    Thread(target=start_recording_from_tray, args=(None, None), daemon=True).start()
    return jsonify({"status": "ok", "message": "Recording command sent."})

@app.route('/stop', methods=['GET'])
def stop():
    # Используем ту же функцию, что и для трея
    Thread(target=stop_recording_from_tray, args=(None, None), daemon=True).start()
    return jsonify({"status": "ok", "message": "Stop command sent."})


@app.route('/pause', methods=['GET'])
def pause():
    # Используем ту же функцию, что и для трея
    Thread(target=pause_recording_from_tray, args=(None, None), daemon=True).start()
    return jsonify({"status": "ok", "message": "Pause command sent."})


@app.route('/resume', methods=['GET'])
def resume():
    # Используем ту же функцию, что и для трея
    Thread(target=resume_recording_from_tray, args=(None, None), daemon=True).start()
    return jsonify({"status": "ok", "message": "Resume command sent."})

@app.route('/status', methods=['GET'])
def status():
    # Update device list more frequently during recording
    # check_and_update_devices_if_needed() # Disabled for simplicity
    
    if is_recording:
        if is_paused:
            recording_status = {"status": "paused", "time": time.strftime('%H:%M:%S', time.gmtime(get_elapsed_record_time()))}
        else:
            recording_status = {"status": "rec", "time": time.strftime('%H:%M:%S', time.gmtime(get_elapsed_record_time()))}
    else:
        recording_status = {"status": "stop", "time": "00:00:00"}

    # Add post-processing information
    if is_post_processing:
        if post_process_stage == "transcribe":
            post_process_info = f"Транскрибация файла: {os.path.basename(post_process_file_path)}"
        elif post_process_stage == "protocol":
            post_process_info = f"Создание протокола из: {os.path.basename(post_process_file_path)}"
        else:
            post_process_info = f"Постобработка: {os.path.basename(post_process_file_path)}"
    else:
        post_process_info = "Постобработка не выполняется"

    recording_status["post_processing"] = {
        "active": is_post_processing,
        "info": post_process_info,
        "stage": post_process_stage if is_post_processing else None
    }

    return jsonify(recording_status)

@app.route('/audio_levels', methods=['GET'])
def get_audio_levels():
    """Возвращает текущие уровни громкости для микрофона и системного аудио."""
    return jsonify(audio_levels)

@app.route('/recreate_transcription/<date>/<filename>', methods=['GET'])
def recreate_transcription(date, filename):
    """Запускает задачу пересоздания транскрипции для аудиофайла."""
    rec_dir = os.path.join(get_application_path(), 'rec')
    file_path = os.path.join(rec_dir, date, filename)

    if not os.path.exists(file_path):
        return jsonify({"status": "error", "message": "Аудиофайл не найден"}), 404

    # Запускаем задачу в фоновом потоке
    Thread(target=process_transcription_task, args=(file_path,), daemon=True).start()

    return jsonify({"status": "ok", "message": f"Задача транскрибации для {filename} отправлена."})

@app.route('/recreate_protocol/<date>/<filename>', methods=['GET'])
def recreate_protocol(date, filename):
    """Запускает задачу пересоздания протокола для аудиофайла."""
    rec_dir = os.path.join(get_application_path(), 'rec')
    audio_file_path = os.path.join(rec_dir, date, filename)
    base_name, _ = os.path.splitext(audio_file_path)
    txt_file_path = base_name + ".txt"

    if not os.path.exists(txt_file_path):
        return jsonify({"status": "error", "message": "Файл транскрипции (.txt) не найден. Сначала создайте транскрипцию."}), 404

    # Запускаем задачу в фоновом потоке
    Thread(target=process_protocol_task, args=(txt_file_path,), daemon=True).start()

    return jsonify({"status": "ok", "message": f"Задача создания протокола для {filename} отправлена."})

@app.route('/compress_to_mp3/<date>/<filename>', methods=['GET'])
def compress_to_mp3(date, filename):
    """Сжимает WAV файл в MP3."""
    rec_dir = os.path.join(get_application_path(), 'rec')
    wav_path = os.path.join(rec_dir, date, filename)

    if not os.path.exists(wav_path) or not wav_path.lower().endswith('.wav'):
        return jsonify({"status": "error", "message": "WAV файл не найден"}), 404

    mp3_path = wav_path.replace('.wav', '.mp3')

    def compress():
        try:
            audio = AudioSegment.from_wav(wav_path)
            audio.export(mp3_path, format="mp3", parameters=["-y", "-loglevel", "quiet"])
            print(f"Сжатие завершено: {mp3_path}")
            # Удаляем WAV после успешной конвертации
            os.remove(wav_path)
            print(f"Удален WAV файл: {wav_path}")
        except Exception as e:
            print(f"Ошибка при сжатии в MP3: {e}")

    # Запускаем сжатие в фоновом потоке, чтобы не блокировать интерфейс
    Thread(target=compress, daemon=True).start()

    return jsonify({"status": "ok", "message": f"Процесс сжатия для {filename} запущен."})


@app.route('/favicon.ico')
def favicon():
    """Отдает favicon в зависимости от статуса записи."""
    if is_recording and not is_paused:
        # Запись
        icon_bytes = FAVICON_REC_BYTES
    elif is_recording and is_paused:
        # Пауза
        icon_bytes = FAVICON_PAUSE_BYTES
    else:
        # Остановлено
        icon_bytes = FAVICON_STOP_BYTES
    
    return Response(icon_bytes, mimetype='image/vnd.microsoft.icon')

# --- Favicon Generation ---
def create_favicon(shape, color, size=(32, 32)):
    """Создает иконку для favicon и возвращает ее в виде байтов."""
    image = Image.new('RGBA', size, (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    width, height = size
    
    if shape == 'circle': 
        dc.ellipse((4, 4, width-5, height-5), fill=color)
    elif shape == 'pause':
        bar_width = 8
        dc.rectangle([(4, 4), (4 + bar_width, height-4)], fill=color)
        dc.rectangle([(width - 4 - bar_width, 4), (width-4, height-4)], fill=color)
    else: # square
        dc.rectangle((4, 4, width-5, height-5), fill=color)
    
    # Сохраняем в байтовый поток в формате ICO
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='ICO', sizes=[(32,32)])
    return img_byte_arr.getvalue()

# --- Глобальные переменные для иконок ---
FAVICON_REC_BYTES = None
FAVICON_PAUSE_BYTES = None
FAVICON_STOP_BYTES = None

def generate_favicons():
    """Генерирует все favicon'ы при старте."""
    global FAVICON_REC_BYTES, FAVICON_PAUSE_BYTES, FAVICON_STOP_BYTES
    FAVICON_REC_BYTES = create_favicon('circle', 'red')
    FAVICON_PAUSE_BYTES = create_favicon('pause', 'orange')
    FAVICON_STOP_BYTES = create_favicon('square', 'gray')
    print("Favicons generated.")

def process_transcription_task(file_path):
    """Обрабатывает только задачу транскрибации."""
    global is_post_processing, post_process_file_path, post_process_stage
    print(f"--- Начало транскрибации для файла: {file_path} ---")
    is_post_processing = True
    post_process_file_path = file_path
    post_process_stage = "transcribe"

    base_name, _ = os.path.splitext(file_path)
    txt_output_path = base_name + ".txt"
    transcription_task_id = post_task(file_path, "transcribe", add_participants_prompt=False) # add_participants_prompt=False, но num_speakers будет добавлен
    if transcription_task_id:
        poll_and_save_result(transcription_task_id, txt_output_path)

    is_post_processing = False
    post_process_file_path = ""
    post_process_stage = ""
    print(f"--- Завершение транскрибации для файла: {file_path} ---")

def process_protocol_task(txt_file_path):
    """Обрабатывает только задачу создания протокола из .txt файла."""
    global is_post_processing, post_process_file_path, post_process_stage
    print(f"--- Начало создания протокола из файла: {txt_file_path} ---")
    is_post_processing = True
    post_process_file_path = txt_file_path
    post_process_stage = "protocol"

    load_settings()
    prompt_addition = settings.get("prompt_addition", "") if settings.get("use_custom_prompt", False) else ""
    current_date_formatted = format_date_russian(datetime.now())
    prompt_addition = prompt_addition.replace("{current_date}", current_date_formatted)

    # --- Meeting Name addition logic ---
    meeting_name_prompt_addition = ""
    active_template_id = settings.get("active_meeting_name_template_id")
    if active_template_id:
        templates = settings.get("meeting_name_templates", [])
        active_template = next((t for t in templates if t.get("id") == active_template_id), None)
        if active_template:
            template_text = active_template.get("template", "")
            if template_text:
                meeting_name_prompt_addition = f"# Название собрания: {template_text}\n\n"

    # --- Date addition logic ---
    date_prompt_addition = ""
    if settings.get("add_meeting_date", False):
        date_source = settings.get("meeting_date_source", "current")
        meeting_date = None
        if date_source == 'folder':
            try:
                # txt_file_path is like '.../rec/2023-10-27/somefile.txt'
                date_str = Path(txt_file_path).parent.name
                meeting_date = datetime.strptime(date_str, '%Y-%m-%d')
            except (ValueError, IndexError):
                print(f"Could not parse date from folder name: {Path(txt_file_path).parent.name}. Falling back to current date.")
                meeting_date = datetime.now()
        else: # 'current'
            meeting_date = datetime.now()
        
        if meeting_date:
            formatted_date = format_date_russian(meeting_date)
            date_prompt_addition = f"# Дата собрания: {formatted_date}\n\n"

    # --- Новая логика для файлов контекста (исправлено) ---
    context_rules = settings.get("context_file_rules", [])
    if context_rules:
        txt_path = Path(txt_file_path)
        for rule in context_rules:
            if not rule.get("enabled", False):
                continue
            pattern = rule.get("pattern")
            prompt_template = rule.get("prompt")
            if not pattern or not prompt_template:
                continue

            found_files = sorted(list(txt_path.parent.glob(pattern)))
            for found_file in found_files:
                try:
                    with open(found_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    if content:
                        formatted_prompt = prompt_template.replace("{filename}", found_file.name).replace("{content}", content)
                        prompt_addition += formatted_prompt
                except Exception as e:
                    print(f"Не удалось прочитать или обработать файл контекста {found_file}: {e}")

    # --- Формирование списка участников для сохранения в promptAddition (повтор логики) ---
    selected_contact_ids = set(settings.get("selected_contacts", []))
    participants_prompt_for_metadata = ""
    if selected_contact_ids:
        participants_by_group = {}
        for group in contacts_data.get("groups", []):
            group_name = group.get("name", "Без группы")
            for contact in group.get("contacts", []):
                if contact.get("id") in selected_contact_ids:
                    if group_name not in participants_by_group:
                        participants_by_group[group_name] = []
                    participants_by_group[group_name].append(contact.get("name"))
        if participants_by_group:
            prompt_lines = ["# Список участников:\n"]
            for group_name in sorted(participants_by_group.keys()):
                prompt_lines.append(f"## Группа: {group_name}")
                for participant_name in sorted(participants_by_group[group_name]):
                    prompt_lines.append(f"- {participant_name}")
                prompt_lines.append("")
            participants_prompt_for_metadata = "\n".join(prompt_lines)

    filtered_prompt_addition = "\n".join([line for line in prompt_addition.splitlines() if not line.strip().startswith("//")])
    
    # Собираем финальную строку для промпта в правильном порядке
    final_prompt_addition = date_prompt_addition + meeting_name_prompt_addition + participants_prompt_for_metadata + filtered_prompt_addition

    protocol_task_id = post_task(
        txt_file_path, "protocol", 
        prompt_addition_str=final_prompt_addition,
        add_participants_prompt=False # add_participants_prompt=False, так как они уже в строке
    )
    if protocol_task_id:
        base_name, _ = os.path.splitext(txt_file_path)
        protocol_output_path = base_name + "_protocol.pdf"

        # --- Сохранение добавки к промпту в метаданные ---
        json_path = base_name + '.json'
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r+', encoding='utf-8') as f:
                    metadata = json.load(f)
                    metadata['promptAddition'] = final_prompt_addition
                    f.seek(0)
                    json.dump(metadata, f, indent=4, ensure_ascii=False)
                    f.truncate()
            except Exception as e:
                print(f"Не удалось обновить метаданные с промптом для {json_path}: {e}")

        poll_and_save_result(protocol_task_id, protocol_output_path)

    is_post_processing = False
    post_process_file_path = ""
    post_process_stage = ""
    print(f"--- Завершение создания протокола из файла: {txt_file_path} ---")

# --- Основная часть ---
def run_flask():
    flask_thread = None
    global http_server
    host = '0.0.0.0' if settings.get("lan_accessible") else '127.0.0.1'
    port = settings.get("port", DEFAULT_SETTINGS["port"])
    try:
        http_server = make_server(host, port, app)
        http_server.serve_forever()
    except Exception as e:
        print(f"Failed to start Flask server: {e}")

def exit_action(icon, item):
    flask_thread = None
    if flask_thread and flask_thread.is_alive() and settings.get("server_enabled"):
        print("Attempting to shut down server on exit...")
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

def update_icon(icon):
    rec_icon = create_icon('circle', 'red'); stop_icon = create_icon('square', 'gray'); pause_icon = create_icon('pause', 'orange')
    last_recording_state = is_recording
    last_pause_state = is_paused
    
    while True:
        # Check if recording state or pause state has changed
        if is_recording != last_recording_state or is_paused != last_pause_state:
            if is_recording and is_paused:
                # Recording is paused
                icon.icon = pause_icon
            elif is_recording:
                # Recording is active
                icon.icon = rec_icon
            else:
                # Not recording
                icon.icon = stop_icon
            
            last_recording_state = is_recording
            last_pause_state = is_paused
        
        time.sleep(0.1)

def start_recording():
    """Starts a new recording session"""
    global is_recording, start_time, stop_event, is_paused, total_pause_duration, recording_threads, RATE

    # 1. Find devices
    try:
        with pyaudio.PyAudio() as p:
            wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
            RATE = int(default_speakers['defaultSampleRate'])
            print(f"System audio sample rate detected: {RATE} Hz. Using this for all recordings.")
    except Exception as e:
        RATE = 44100 # Fallback to default
        print(f"Could not detect system sample rate, falling back to {RATE} Hz. Error: {e}")

    mic_device_index = None
    try:
        mic_device_index = sd.default.device[0]
        print(f"Default microphone found: {sd.query_devices(mic_device_index)['name']}")
    except (ValueError, sd.PortAudioError) as e:
        print(f"Could not find a default microphone: {e}")


    # System audio is handled by pyaudiowpatch, no need to find device index here
    if mic_device_index is None and platform.system() != "Windows":
        print("FATAL: No recording devices found. Aborting.")
        messagebox.showerror("Ошибка записи", "Не найдено ни одного устройства для записи (микрофон или системный звук).")
        return

    # 2. Reset state and start recording
    is_recording = True
    is_paused = False
    total_pause_duration = 0.0
    start_time = datetime.now()
    stop_event.clear()

    # 3. Create temporary file paths
    script_dir = get_application_path()
    temp_dir = os.path.join(script_dir, 'rec', 'temp')
    os.makedirs(temp_dir, exist_ok=True)
    # Используем системную временную директорию
    temp_dir = tempfile.gettempdir()

    timestamp = start_time.strftime('%Y%m%d_%H%M%S')
    mic_temp_file = os.path.join(temp_dir, f"{timestamp}_mic.wav")
    sys_temp_file = os.path.join(temp_dir, f"{timestamp}_sys.wav")

    # 4. Start recording threads
    recording_threads = []

    if mic_device_index is not None:
        mic_thread = Thread(target=recorder_mic_to_file, args=(mic_device_index, stop_event, mic_temp_file))
        recording_threads.append(mic_thread)
        mic_thread.start()

    if platform.system() == "Windows":
        sys_thread = Thread(target=recorder_sys_to_file, args=(stop_event, sys_temp_file))
        recording_threads.append(sys_thread)
        sys_thread.start()


def resume_recording():
    """Resumes a paused recording session"""
    global is_paused, pause_start_time, total_pause_duration

    # Calculate pause duration and add to total if pause_start_time is set
    if pause_start_time:
        pause_duration = (datetime.now() - pause_start_time).total_seconds()
        total_pause_duration += pause_duration

    # Reset pause state
    is_paused = False
    pause_start_time = None


def start_recording_from_tray(icon, item):
    global is_recording, is_paused
    if is_recording:
        print("Запись уже идет (возможно, на паузе). Используйте 'Возобновить'.")
        return

    def _start():
        try:
            start_recording()
            print("Запись начата.")
        except Exception as e:
            print(f"Ошибка при запуске записи: {e}")
            is_recording = False  # Ensure recording flag is reset on error
        update_tray_menu()

    # Запускаем в отдельном потоке, чтобы не блокировать основной поток (особенно важно для Flask)
    Thread(target=_start, daemon=True).start()

def stop_recording():
    """Stops the current recording session"""
    global is_recording, start_time, recording_threads, is_paused, total_pause_duration

    stop_event.set()
    for thread in recording_threads:
        if thread.is_alive():
            thread.join(timeout=5)
    recording_threads = []

    end_time = datetime.now()
    is_recording = False
    is_paused = False
    total_pause_duration = 0.0

    script_dir = get_application_path()
    rec_dir = os.path.join(script_dir, 'rec')
    day_dir = os.path.join(rec_dir, start_time.strftime('%Y-%m-%d'))
    os.makedirs(day_dir, exist_ok=True)
    temp_dir = os.path.join(rec_dir, 'temp')
    # Используем системную временную директорию
    temp_dir = tempfile.gettempdir()

    timestamp = start_time.strftime('%Y%m%d_%H%M%S')
    mic_temp_file = os.path.join(temp_dir, f"{timestamp}_mic.wav")
    sys_temp_file = os.path.join(temp_dir, f"{timestamp}_sys.wav")

    final_audio = None
    mic_audio = None
    sys_audio = None

    if os.path.exists(mic_temp_file) and os.path.getsize(mic_temp_file) > 44:
        mic_audio = AudioSegment.from_wav(mic_temp_file)

    if os.path.exists(sys_temp_file) and os.path.getsize(sys_temp_file) > 44:
        sys_audio = AudioSegment.from_wav(sys_temp_file)

    if mic_audio and sys_audio:
        # Ensure both segments have the same frame rate before overlaying
        if mic_audio.frame_rate != sys_audio.frame_rate:
             # Resample mic audio to match system audio's higher sample rate
            print(f"Resampling mic audio from {mic_audio.frame_rate} to {sys_audio.frame_rate}")
            mic_audio = mic_audio.set_frame_rate(sys_audio.frame_rate)

        # Ensure mic audio is stereo to match system audio
        if mic_audio.channels == 1:
            mic_audio = mic_audio.set_channels(2)

        print("Mixing microphone and system audio...")
        final_audio = mic_audio.overlay(sys_audio)
    elif mic_audio:
        print("Only microphone audio was recorded.")
        final_audio = mic_audio
    elif sys_audio:
        print("Only system audio was recorded.")
        final_audio = sys_audio
    else:
        print("Warning: No audio data was recorded. Skipping file creation.")
        if os.path.exists(mic_temp_file): os.remove(mic_temp_file)
        if os.path.exists(sys_temp_file): os.remove(sys_temp_file)
        return

    duration = (end_time - start_time)
    minutes, seconds = divmod(int(duration.total_seconds()), 60)
    wav_filename = os.path.join(day_dir, f"{start_time.strftime('%H.%M')}_{minutes:02d}m{seconds:02d}s.wav")
    final_audio.export(wav_filename, format='wav')
    print(f"Final audio saved to: {wav_filename}")
    
    # --- Post-processing ---
    final_audio_path = None
    mp3_filename = wav_filename.replace('.wav', '.mp3')
    try:
        final_audio.export(mp3_filename, format="mp3", parameters=["-y", "-loglevel", "quiet"])
        print(f"Auto-compression completed: {mp3_filename}")
        final_audio_path = mp3_filename
        # Удаляем временный WAV-файл после успешной конвертации в MP3
        try:
            os.remove(wav_filename)
            print(f"Removed temporary WAV file: {wav_filename}")
        except OSError as e:
            print(f"Error removing temporary WAV file {wav_filename}: {e}")
    except Exception as e:
        print(f"Error during auto-compression to MP3: {e}")
        final_audio_path = wav_filename

    # --- Create Metadata JSON file ---
    if final_audio_path:
        json_path = os.path.splitext(final_audio_path)[0] + '.json'
        
        # Determine the title
        title = os.path.basename(os.path.splitext(final_audio_path)[0]) # Default to filename
        active_template_id = settings.get("active_meeting_name_template_id")
        if active_template_id:
            templates = settings.get("meeting_name_templates", [])
            active_template = next((t for t in templates if t.get("id") == active_template_id), None)
            if active_template and active_template.get("template"):
                title = active_template.get("template")

        metadata = {
            "startTime": start_time.isoformat(),
            "duration": duration.total_seconds(),
            "title": title,
            "promptAddition": "" # Инициализируем пустым значением
        }
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=4, ensure_ascii=False)
        print(f"Metadata saved to: {json_path}")

        # Start post-processing tasks
        Thread(target=process_recording_tasks, args=(final_audio_path,), daemon=True).start()

    # Clean up temporary files
    if os.path.exists(mic_temp_file): os.remove(mic_temp_file)
    if os.path.exists(sys_temp_file): os.remove(sys_temp_file)



def stop_recording_from_tray(icon, item):
    global is_recording
    if not is_recording:
        print("Запись не идет.")
        return

    try:
        stop_recording()

        # Update tray menu to reflect new state
        update_tray_menu()

        print("Запись остановлена.")
    except Exception as e:
        print(f"Ошибка при остановке записи: {e}")
        # Reset recording state in case of error
        is_recording = False

def pause_recording():
    """Pauses the current recording session"""
    global is_paused, pause_start_time

    # Set pause state
    is_paused = True
    pause_start_time = datetime.now()


def pause_recording_from_tray(icon, item):
    global is_recording
    if not is_recording:
        print("Запись не идет.")
        return
    if is_paused:
        print("Запись уже на паузе.")
        return

    try:
        pause_recording()

        # Update tray menu to reflect new state
        update_tray_menu()

        print("Запись приостановлена.")
    except Exception as e:
        print(f"Ошибка при паузе записи: {e}")

def resume_recording_from_tray(icon, item):
    global is_recording, is_paused
    if not is_recording:
        print("Запись не идет.")
        return
    if not is_paused:
        print("Запись не на паузе, возобновление не требуется.")
        return

    try:
        resume_recording()

        # Update tray menu to reflect new state
        update_tray_menu()

        print("Запись возобновлена.")
    except Exception as e:
        print(f"Ошибка при возобновлении записи: {e}")

# The safe_open_stream function is no longer needed with the new sounddevice implementation

def recorder_mic_to_file(device_index, stop_event, output_filename):
    """Records audio from microphone using sounddevice and writes to a file."""
    global audio_levels
    try:
        q = queue.Queue()

        def callback(indata, frames, time, status):
            if status:
                print(status, file=sys.stderr)
            q.put(indata.copy())

        with sd.InputStream(samplerate=RATE, device=device_index, channels=1, dtype='int16', callback=callback) as stream, \
             wave.open(output_filename, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2) # 16-bit
            wf.setframerate(stream.samplerate)
            print(f"Recording started for mic device {device_index} to {output_filename}.")

            while not stop_event.is_set():
                if is_paused:
                    time.sleep(0.1) # Просто ждем, если на паузе
                else:
                    try:
                        data = q.get(timeout=0.1)
                        wf.writeframes(data)
                    except queue.Empty:
                        pass
    except Exception as e:
        print(f"Error during mic recording: {e}", file=sys.stderr)
    finally:
        print(f"Mic recording process finished for device {device_index}.")

def recorder_sys_to_file(stop_event, output_filename):
    """Records system audio using pyaudiowpatch and writes to a file."""
    try:
        with pyaudio.PyAudio() as p:
            wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])

            if not default_speakers["isLoopbackDevice"]:
                for loopback in p.get_loopback_device_info_generator():
                    if default_speakers["name"] in loopback["name"]:
                        default_speakers = loopback
                        break
                else:
                    print("Не удалось найти loopback-устройство для системного звука.", file=sys.stderr)
                    return

            print(f"Recording from: ({default_speakers['index']}){default_speakers['name']} to {output_filename}")

            channels = default_speakers["maxInputChannels"]
            rate = int(default_speakers['defaultSampleRate'])
            
            with wave.open(output_filename, 'wb') as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
                wf.setframerate(rate)

                q = queue.Queue()

                def callback(in_data, frame_count, time_info, status):
                    q.put(in_data)
                    return (None, pyaudio.paContinue)

                stream = p.open(format=pyaudio.paInt16, channels=channels, rate=rate, input=True,
                                input_device_index=default_speakers["index"], stream_callback=callback)

                stream.start_stream()
                print("System audio recording started.")
                while not stop_event.is_set():
                    if is_paused:
                        time.sleep(0.1)
                    else:
                        try:
                            data = q.get(timeout=0.1)
                            wf.writeframes(data)
                        except queue.Empty:
                            # Если в очереди нет данных (например, системный звук не воспроизводится),
                            # просто ждем, чтобы не нагружать процессор.
                            time.sleep(0.05)
                stream.stop_stream()
                stream.close()
    except Exception as e:
        print(f"Error during system audio recording: {e}", file=sys.stderr)
    finally:
        print("System audio recording process finished.")

def monitor_mic(stop_event):
    """Постоянно отслеживает уровень громкости микрофона."""
    global audio_levels
    try:
        mic_device_index = sd.default.device[0]
        samplerate = sd.query_devices(mic_device_index, 'input')['default_samplerate']

        def callback(indata, frames, time, status):
            if status: print(status, file=sys.stderr)
            
            # Рассчитываем RMS для уровня громкости
            rms = np.sqrt(np.mean(np.square(indata.astype(np.float32) / 32768.0)))
            audio_levels["mic"] = float(rms)

        with sd.InputStream(samplerate=samplerate, device=mic_device_index, channels=1, dtype='int16', callback=callback):
            print("Мониторинг микрофона запущен.")
            stop_event.wait()

    except Exception as e:
        print(f"Ошибка мониторинга микрофона: {e}", file=sys.stderr)
        audio_levels["mic"] = -1 # Индикатор ошибки
    finally:
        print("Мониторинг микрофона остановлен.")

def monitor_sys(stop_event):
    """Постоянно отслеживает уровень громкости системного аудио."""
    global audio_levels
    try:
        with pyaudio.PyAudio() as p:
            wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
            if not default_speakers["isLoopbackDevice"]:
                for loopback in p.get_loopback_device_info_generator():
                    if default_speakers["name"] in loopback["name"]:
                        default_speakers = loopback
                        break
                else: return

            def callback(in_data, frame_count, time_info, status):
                np_data = np.frombuffer(in_data, dtype=np.int16)
                rms = np.sqrt(np.mean(np.square(np_data.astype(np.float32) / 32768.0)))
                audio_levels["sys"] = float(rms)
                return (None, pyaudio.paContinue)

            stream = p.open(format=pyaudio.paInt16,
                            channels=default_speakers["maxInputChannels"],
                            rate=int(default_speakers['defaultSampleRate']),
                            input=True,
                            input_device_index=default_speakers["index"],
                            stream_callback=callback)
            stream.start_stream()
            print("Мониторинг системного аудио запущен.")
            stop_event.wait()
            stream.stop_stream()
            stream.close()
    except Exception as e:
        print(f"Ошибка мониторинга системного аудио: {e}", file=sys.stderr)
        audio_levels["sys"] = -1 # Индикатор ошибки
    finally:
        print("Мониторинг системного аудио остановлен.")

def open_rec_folder(icon, item):
    rec_dir = os.path.join(get_application_path(), 'rec')
    os.makedirs(rec_dir, exist_ok=True)
    os.startfile(rec_dir)

def make_hyperlink(widget):
    """
    Makes a tkinter Text widget support clickable hyperlinks.
    """
    # Configure a tag for hyperlinks
    widget.tag_configure("hyperlink", foreground="blue", underline=True)
    
    # Keep track of the active hyperlink
    widget.hyperlink_cursor = widget.cget("cursor")
    
    def get_hyperlink_at_cursor(event):
        index = widget.index(f"@{event.x},{event.y}")
        names = widget.tag_names(index)
        if "hyperlink" in names:
            # Find the URL associated with this hyperlink
            for pos, url in getattr(widget, 'hyperlink_manager', {}).items():
                # Extract just the line and character numbers for comparison
                pos_line, pos_char = pos.split('.')
                idx_line, idx_char = index.split('.')
                
                # Check if the clicked position is within the hyperlink range
                if pos_line == idx_line:
                    # Find the end of this hyperlink tag on the same line
                    ranges = widget.tag_ranges("hyperlink")
                    for i in range(0, len(ranges), 2):
                        start_range = str(ranges[i])
                        end_range = str(ranges[i+1])
                        
                        start_line, start_char = start_range.split('.')
                        end_line, end_char = end_range.split('.')
                        
                        if start_line == idx_line and start_range <= index <= end_range:
                            return url
        return None
    
    def enter_link(event):
        url = get_hyperlink_at_cursor(event)
        if url:
            widget.config(cursor="hand2")
        else:
            widget.config(cursor=widget.hyperlink_cursor)
    
    def leave_link(event):
        widget.config(cursor=widget.hyperlink_cursor)
    
    def click_link(event):
        url = get_hyperlink_at_cursor(event)
        if url:
            import webbrowser
            webbrowser.open(url)
    
    # Bind events to the text widget
    widget.tag_bind("hyperlink", "<Enter>", enter_link)
    widget.tag_bind("hyperlink", "<Leave>", leave_link)
    widget.tag_bind("hyperlink", "<Button-1>", click_link)

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

    setup_logging()
    load_settings()
    load_contacts()
    generate_favicons()

    stop_icon = create_icon('square', 'gray')
    main_icon = Icon('recordServer', stop_icon, 'recordServer')

    # Start server and update menu for the first time
    start_server()

    update_thread = Thread(target=update_icon, args=(main_icon,), daemon=True)
    update_thread.start()

    # --- Запуск потоков мониторинга звука ---
    mic_monitor_thread = Thread(target=monitor_mic, args=(monitoring_stop_event,), daemon=True)
    mic_monitor_thread.start()

    if platform.system() == "Windows":
        sys_monitor_thread = Thread(target=monitor_sys, args=(monitoring_stop_event,), daemon=True)
        sys_monitor_thread.start()

    # Start periodic tray menu update thread
    menu_update_thread = Thread(target=periodic_tray_menu_update, daemon=True)
    menu_update_thread.start()

    main_icon.run()