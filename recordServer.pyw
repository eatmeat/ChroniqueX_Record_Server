import os
import json
import wave
import time
import re
import sys
from datetime import datetime
from pathlib import Path
from threading import Thread, Event

import pyaudiowpatch as pyaudio
import requests
from dotenv import load_dotenv

from flask import Flask, jsonify, render_template, request
from pydub import AudioSegment
from werkzeug.serving import make_server

import tkinter as tk
from tkinter import messagebox
from pystray import Icon, Menu, MenuItem as item
from PIL import Image, ImageDraw
from PIL import ImageTk

def get_application_path():
    """Get the path where the application is located, whether running as script or executable"""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        application_path = os.path.dirname(sys.executable)
    else:
        # Running as script
        application_path = os.path.dirname(os.path.abspath(__file__))
    return application_path


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
    "lan_accessible": False,
    "use_custom_prompt": False,
    "prompt_addition": "",
    "include_html_files": True,  # Default to True to maintain existing behavior
    "main_window_width": 700,
    "main_window_height": 800,
    "main_window_x": None,
    "main_window_y": None
}
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

# --- Load Environment Variables ---
dotenv_path = os.path.join(get_application_path(), '.env')
load_dotenv(dotenv_path)
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")

# --- Глобальные переменные ---
app = Flask(__name__)
is_recording = False
is_paused = False  # Track pause state
start_time = None
pause_start_time = None  # Track when pause started
total_pause_duration = 0  # Total duration of pauses
recording_thread = None
stop_event = Event()
frames = {}
RATE = 44100
CHANNELS = 2
FORMAT = pyaudio.paInt16
flask_thread = None
http_server = None

# Variables for post-processing status
is_post_processing = False  # Track if post-processing is happening
post_process_file_path = ""  # Track the file being processed
post_process_stage = ""  # Track the current stage (transcribe, protocol)

# --- Server Lifecycle Management ---
def start_server():
    global flask_thread
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
                item('Основное окно', open_main_window),
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
                item('Основное окно', open_main_window),
                item('Открыть папку с записями', open_rec_folder),
                Menu.SEPARATOR,
                item('Выход', exit_action)
            )
        else:
            # No active recording, show start option
            main_icon.menu = Menu(
                item('Начать запись', start_recording_from_tray, enabled=True),  # Always enabled when not recording
                item('Остановить запись', stop_recording_from_tray, enabled=False),  # Disabled since no recording is active
                Menu.SEPARATOR,
                item('Основное окно', open_main_window),
                item('Открыть папку с записями', open_rec_folder),
                Menu.SEPARATOR,
                item('Выход', exit_action)
            )
# --- Settings Window ---
def open_main_window(icon=None, item=None):
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
                "port": new_port,
                "server_enabled": server_enabled_var.get(),
                "lan_accessible": lan_accessible_var.get(),
                "use_custom_prompt": use_custom_prompt_var.get(),
                "prompt_addition": prompt_addition_text.get("1.0", tk.END).strip(),
                "include_html_files": include_html_files_var.get(),
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
                # Don't close the window, just update the tray menu
                update_tray_menu()
            else:
                messagebox.showinfo("Сохранено", "Настройки сохранены.", parent=win)
                # Don't close the window, just update the tray menu
                update_tray_menu()

        except ValueError as e:
            messagebox.showerror("Ошибка", f"Неверное значение для порта: {e}", parent=win)

    def on_close():
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
        win.destroy()

    win = tk.Tk()
    win.title("ChroniqueX - Запись @ Транскрибация @ Протоколы")

    # Set window size and position from settings
    width = settings.get("main_window_width", 700)
    height = settings.get("main_window_height", 500)
    x = settings.get("main_window_x", None)
    y = settings.get("main_window_y", None)

    win.geometry(f"{width}x{height}")
    if x is not None and y is not None:
        win.geometry(f"+{x}+{y}")

    win.transient(); win.grab_set()
    win.protocol("WM_DELETE_WINDOW", on_close)  # Handle window close event

    # Configure grid weights for proper resizing
    win.grid_rowconfigure(0, weight=1)
    win.grid_columnconfigure(0, weight=1)

    # Main frame
    main_frame = tk.Frame(win)
    main_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
    main_frame.grid_rowconfigure(4, weight=1)  # Give row 4 (text area) weight to expand
    main_frame.grid_rowconfigure(7, weight=0)  # Row for endpoints info
    main_frame.grid_columnconfigure(0, weight=1)

    # Telegram bot link frame
    telegram_frame = tk.Frame(main_frame)
    telegram_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
    telegram_frame.grid_columnconfigure(0, weight=1)
    
    # Telegram bot link label
    telegram_label = tk.Label(telegram_frame, text="Telegram-бот: @ChroniqueX_bot", fg="blue", cursor="hand2", font=("Arial", 10, "underline"))
    telegram_label.pack(side="left")
    
    # Function to handle clicking on the Telegram link
    def open_telegram_bot():
        import webbrowser
        webbrowser.open("https://t.me/ChroniqueX_bot")
    
    # Bind click event to the label
    telegram_label.bind("<Button-1>", lambda e: open_telegram_bot())

    # Toolbar frame for recording controls
    toolbar_frame = tk.Frame(main_frame)
    toolbar_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
    toolbar_frame.grid_columnconfigure(0, weight=1)
    toolbar_frame.grid_columnconfigure(1, weight=1)
    toolbar_frame.grid_columnconfigure(2, weight=1)
    toolbar_frame.grid_columnconfigure(3, weight=1)

    # Status label for post-processing
    post_process_status_label = tk.Label(main_frame, text="", fg="blue", font=("Arial", 10))
    post_process_status_label.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
    
    # Function to update post-processing status display
    def update_post_process_status():
        if is_post_processing:
            if post_process_stage == "transcribe":
                status_text = f"Идет постобработка: транскрибация файла {os.path.basename(post_process_file_path)}"
            elif post_process_stage == "protocol":
                status_text = f"Идет постобработка: создание протокола из {os.path.basename(post_process_file_path)}"
            else:
                status_text = f"Идет постобработка: {os.path.basename(post_process_file_path)}"
        else:
            status_text = "Постобработка не выполняется"

        post_process_status_label.config(text=status_text)
        # Schedule next update
        win.after(1000, update_post_process_status)  # Update every second
    
    # Start the status update loop
    update_post_process_status()

    # Create icons for buttons
    def create_button_icon_with_text(shape, color, text, size=(60, 65)):
        """Create an icon for buttons with both shape and text centered"""
        image = Image.new('RGBA', size, (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)
        width, height = size
        
        # Calculate positions for centered icon and text
        icon_y = 8  # Position icon lower to make space for text
        text_y = height - 22  # Position text at the bottom, adjusted for larger font
        
        # Draw the icon shape
        if shape == 'circle': 
            dc.ellipse((width//2 - 8, icon_y, width//2 + 8, icon_y + 16), fill=color)
        elif shape == 'pause':
            # Draw two vertical bars for pause symbol
            bar_width = 4
            bar_height = 14
            # Left bar
            dc.rectangle([(width//2 - 6, icon_y), (width//2 - 6 + bar_width, icon_y + bar_height)], fill=color)
            # Right bar
            dc.rectangle([(width//2 + 2, icon_y), (width//2 + 2 + bar_width, icon_y + bar_height)], fill=color)
        elif shape == 'square':
            margin = 4
            dc.rectangle((width//2 - 8, icon_y, width//2 + 8, icon_y + 16), fill=color)
        
        # Add text below the icon
        try:
            # Try to use a default font
            font = ImageFont.truetype("arial.ttf", 14)  # Increased font size
        except:
            try:
                font = ImageFont.truetype("Arial.ttf", 14)  # Alternative capitalization
            except:
                # Fallback to default font if Arial is not available
                font = ImageFont.load_default()
        
        # Calculate text position to be centered below the icon
        text_bbox = dc.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_x = (width - text_width) // 2  # Horizontally center the text
        
        dc.text((text_x, text_y), text, fill=(0, 0, 0, 255), font=font)
        
        # Convert to PhotoImage
        photo = ImageTk.PhotoImage(image)
        return photo

    # Import ImageFont inside the function to avoid import issues
    from PIL import ImageFont

    # Create button icons with text
    rec_icon = create_button_icon_with_text('circle', 'red', 'REC')
    pause_icon = create_button_icon_with_text('pause', 'orange', 'PAUSE')
    stop_icon = create_button_icon_with_text('square', 'gray', 'STOP')
    # For open folder button, keep text since it's a different type of action

    # Define button variables with icons
    rec_button = tk.Button(toolbar_frame, image=rec_icon, width=65, height=70)
    pause_button = tk.Button(toolbar_frame, image=pause_icon, width=65, height=70)
    stop_button = tk.Button(toolbar_frame, image=stop_icon, width=65, height=70)
    open_folder_button = tk.Button(toolbar_frame, text="Открыть папку с записями", width=30, height=2)
    
    # Keep references to images to prevent garbage collection
    rec_button.image = rec_icon
    pause_button.image = pause_icon
    stop_button.image = stop_icon

    # Pack buttons in the toolbar
    rec_button.grid(row=0, column=0, padx=2, pady=2)
    pause_button.grid(row=0, column=1, padx=2, pady=2)
    stop_button.grid(row=0, column=2, padx=2, pady=2)
    open_folder_button.grid(row=0, column=3, padx=2, pady=2)

    # Update button states based on current recording status
    def update_toolbar_buttons():
        # Check local recording state first
        if is_recording and not is_paused:
            # Recording is active, show pause and stop buttons as enabled
            rec_button.config(relief="sunken", state="disabled")  # Pressed appearance
            pause_button.config(relief="raised", state="normal")
            stop_button.config(relief="raised", state="normal")
        elif is_recording and is_paused:
            # Recording is paused, show resume and stop buttons
            rec_button.config(relief="raised", state="normal")
            pause_button.config(relief="sunken", state="disabled")  # Pressed appearance
            stop_button.config(relief="raised", state="normal")
        else:
            # No active recording, show rec button enabled
            rec_button.config(relief="raised", state="normal")
            pause_button.config(relief="sunken", state="disabled")  # Pressed but disabled
            stop_button.config(relief="sunken", state="disabled")  # Pressed but disabled

            # Disable pause and stop buttons when not recording
            pause_button.config(state="disabled")
            stop_button.config(state="disabled")

    # Configure button commands
    rec_button.config(command=lambda: start_recording_from_tray(None, None))
    pause_button.config(command=lambda: pause_recording_from_tray(None, None))
    stop_button.config(command=lambda: stop_recording_from_tray(None, None))
    open_folder_button.config(command=lambda: open_rec_folder(None, None))

    # Initial update of button states
    update_toolbar_buttons()
    
    # Schedule periodic updates of button states
    def schedule_toolbar_update():
        update_toolbar_buttons()
        win.after(1000, schedule_toolbar_update)  # Update every 1000ms (1 second)
    
    schedule_toolbar_update()

    port_var = tk.StringVar(value=str(settings.get("port")))
    server_enabled_var = tk.BooleanVar(value=settings.get("server_enabled"))
    lan_accessible_var = tk.BooleanVar(value=settings.get("lan_accessible"))
    use_custom_prompt_var = tk.BooleanVar(value=settings.get("use_custom_prompt"))
    include_html_files_var = tk.BooleanVar(value=settings.get("include_html_files", True))

    # Create StringVar for the text widget
    prompt_addition_frame = tk.Frame(main_frame)
    prompt_addition_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=5)
    main_frame.grid_columnconfigure(0, weight=1)

    tk.Checkbutton(prompt_addition_frame, text="Использовать дополнение к промпту", variable=use_custom_prompt_var).pack(anchor="w")

    prompt_addition_label = tk.Label(prompt_addition_frame, text="Дополнение к промпту:")
    prompt_addition_label.pack(anchor="w")

    # Information label about {current_date} placeholder
    info_label = tk.Label(prompt_addition_frame, text="Доступные плейсхолдеры: {current_data} - текущая дата в формате DD MMMMM YYYY", fg="gray", font=("Arial", 8))
    info_label.pack(anchor="w")

    # Information label about "//" comment lines
    comment_info_label = tk.Label(prompt_addition_frame, text="Строки, начинающиеся с //, будут исключены при отправке задачи", fg="gray", font=("Arial", 8))
    comment_info_label.pack(anchor="w")

    # Checkbox for including HTML files
    include_html_check = tk.Checkbutton(prompt_addition_frame, text="Добавлять HTML файлы в контекст (будут подписаны @имя_файла)", variable=include_html_files_var)
    include_html_check.pack(anchor="w")

    # Create a text widget with scrollbar
    text_frame = tk.Frame(main_frame)
    text_frame.grid(row=4, column=0, sticky="nsew", padx=10, pady=5)
    main_frame.grid_rowconfigure(4, weight=1)  # This row will expand vertically
    main_frame.grid_columnconfigure(0, weight=1)

    prompt_addition_text = tk.Text(text_frame, height=6, width=50)
    scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL, command=prompt_addition_text.yview)
    prompt_addition_text.configure(yscrollcommand=scrollbar.set)

    prompt_addition_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    prompt_addition_text.insert(tk.END, settings.get("prompt_addition", ""))

    # Add context menu to the text widget
    _add_context_menu_to_text_widget(prompt_addition_text)

    # Field is always editable regardless of the checkbox state
    prompt_addition_text.config(state=tk.NORMAL)

    # Note: The checkbox state only affects whether the prompt is used during processing,
    # not the editability of the field

    frame = tk.Frame(main_frame, padx=10, pady=10)
    frame.grid(row=6, column=0, sticky="ew", padx=10, pady=10)
    frame.grid_columnconfigure(1, weight=1)

    # Endpoints info frame
    endpoints_frame = tk.Frame(main_frame)
    endpoints_frame.grid(row=7, column=0, sticky="ew", padx=10, pady=10)
    endpoints_frame.grid_columnconfigure(0, weight=1)
    
    endpoints_label = tk.Label(endpoints_frame, text="Эндпоинты сервера:", font=("Arial", 10, "bold"))
    endpoints_label.pack(anchor="w")
    
    # Create a frame for the endpoint links
    endpoints_links_frame = tk.Frame(endpoints_frame)
    endpoints_links_frame.pack(fill=tk.BOTH, expand=True)
    
    # Define endpoint information
    endpoints_info = [
        ("/", "веб-интерфейс"),
        ("/rec", "начать запись"),
        ("/stop", "остановить запись"),
        ("/pause", "приостановить запись"),
        ("/resume", "возобновить запись"),
        ("/status", "получить статус записи")
    ]
    
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

    tk.Label(frame, text="Порт:").grid(row=0, column=0, sticky="w", pady=5)
    port_edit = tk.Entry(frame, textvariable=port_var)
    port_edit.grid(row=0, column=1, sticky="ew")
    _add_context_menu_to_text_widget(port_edit)
    tk.Checkbutton(frame, text="Сервер запущен", variable=server_enabled_var).grid(row=1, columnspan=2, sticky="w")
    tk.Checkbutton(frame, text="Доступен по локальной сети (host 0.0.0.0)", variable=lan_accessible_var).grid(row=2, columnspan=2, sticky="w")

    button_frame = tk.Frame(frame)
    button_frame.grid(row=3, columnspan=2, pady=10)
    tk.Button(button_frame, text="Сохранить", command=on_save).pack(side="left", padx=5)
    tk.Button(button_frame, text="Свернуть", command=on_close).pack(side="left", padx=5)
    win.mainloop()

# --- Post-processing, Audio Recording, and other functions (mostly unchanged) ---
def post_task(file_path, task_type, prompt_addition=None):
    if not API_URL or not API_KEY: return None
    try:
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f)}
            data = {'api_key': API_KEY, 'task_type': task_type}
            # Add prompt_addition if it's a protocol task and prompt_addition is provided
            if task_type == 'protocol' and prompt_addition:
                data['prompt_addition'] = prompt_addition
            # Disable SSL certificate verification for self-signed certificates
            response = requests.post(f"{API_URL}/add_task", files=files, data=data, verify=False)
        if response.status_code == 202:
            return response.json().get("task_id")
        else:
            print(f"Ошибка создания задачи '{task_type}': {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Ошибка соединения при создании задачи '{task_type}': {e}")
        return None

def poll_and_save_result(task_id, output_path):
    if not task_id: return False
    while True:
        try:
            # Disable SSL certificate verification for self-signed certificates
            response = requests.get(f"{API_URL}/get_result/{task_id}", timeout=10, verify=False)
            if response.status_code == 200:
                with open(output_path, 'wb') as f: f.write(response.content)
                return True
            elif response.status_code == 202: time.sleep(5)
            elif response.status_code == 500:
                print(f"Задача {task_id} провалена: {response.json().get('error', 'Неизвестная ошибка')}")
                return False
            else: time.sleep(10)
        except requests.exceptions.RequestException as e:
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

        # Check if HTML files should be included in the context
        if settings.get("include_html_files", True):
            # Check for HTML files in the same directory as the audio file
            audio_path = Path(file_path)
            html_files = sorted(list(audio_path.parent.glob('*.html')))

            if html_files:
                print(f"Найдено HTML-файлов: {len(html_files)}")

                # Process each HTML file and add to prompt
                for html_file in html_files:
                    try:
                        print(f"Обработка HTML-файла: {html_file.name}")
                        with open(html_file, 'r', encoding='utf-8') as f:
                            task_context_html = f.read()

                        # Убираем HTML-теги, кроме табличных, для уменьшения контекста
                        allowed_tags = {'table', 'tr', 'td', 'th', 'tbody', 'thead', 'tfoot'}

                        def should_keep_tag(match):
                            tag = match.group(0)
                            try:
                                is_closing = tag.startswith('</')
                                tag_name = tag.strip('</>').split()[0].lower()
                                if tag_name in allowed_tags:
                                    return f'</{tag_name}>' if is_closing else f'<{tag_name}>'
                                else:
                                    return ' '
                            except IndexError:
                                return ' '  # Handle malformed tags like <>

                        task_context = re.sub(r'<[^>]+>', should_keep_tag, task_context_html).strip()

                        if task_context:
                            # Format the HTML content with file name markers
                            html_content_formatted = f"\n--- НАЧАЛО файла @{html_file.name} ---\n{task_context}\n--- КОНЕЦ файла @{html_file.name} ---\n"
                            prompt_addition += html_content_formatted
                            print(f"Добавлен контент из HTML-файла: {html_file.name}")

                    except Exception as e:
                        print(f"Не удалось прочитать файл задач {html_file}: {e}")

        # Filter out lines that start with "//" from prompt_addition
        filtered_prompt_addition = "\n".join([
            line for line in prompt_addition.splitlines() 
            if not line.strip().startswith("//")
        ])

        # Update post-processing status for protocol stage
        post_process_stage = "protocol"
        protocol_task_id = post_task(txt_output_path, "protocol", prompt_addition=filtered_prompt_addition)
        if protocol_task_id:
            protocol_output_path = base_name + "_protocol.pdf"
            poll_and_save_result(protocol_task_id, protocol_output_path)
    
    # Reset post-processing status
    is_post_processing = False
    post_process_file_path = ""
    post_process_stage = ""

    print(f"--- Завершение постобработки для файла: {file_path} ---")

def recorder(device_indices):
    global frames, RATE, CHANNELS, FORMAT
    CHUNK = 1024; COMMON_RATES = [48000, 44100, 32000]
    audio = pyaudio.PyAudio()
    supported_rate = 44100 # Default
    # Simplified rate detection
    RATE = supported_rate
    def cb(in_data, frame_count, time_info, status):
        # Only append frames if not paused
        if not is_paused:
            frames[0].append(in_data)
        return (None, pyaudio.paContinue)
    frames[0] = []
    stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK, input_device_index=device_indices[0], stream_callback=cb)
    stream.start_stream()
    stop_event.wait()
    stream.stop_stream(); stream.close(); audio.terminate()

import os
from datetime import datetime
from flask import send_file
from flask import Response

# --- Конечные точки API ---

# Endpoint to recreate transcription
@app.route('/recreate_transcription/<date>/<filename>')
def recreate_transcription(date, filename):
    # Reload settings to ensure API credentials are fresh
    load_settings()
    global API_URL, API_KEY
    # Re-load environment variables
    API_URL = os.getenv("API_URL")
    API_KEY = os.getenv("API_KEY")

    rec_dir = os.path.join(get_application_path(), 'rec')
    file_path = os.path.join(rec_dir, date, filename)
    
    if not os.path.exists(file_path):
        return "File not found", 404
    
    # Check if it's an audio file
    name, ext = os.path.splitext(filename)
    if ext.lower() not in ['.wav', '.mp3']:
        return "Not an audio file", 400
    
    # Check if API is configured
    if not API_URL or not API_KEY:
        return "API not configured. Please set API_URL and API_KEY in .env file", 500
    
    # Submit transcription task in a separate thread
    def run_transcription_task():
        global is_post_processing, post_process_file_path, post_process_stage
        # Reload settings in the thread to ensure API credentials are fresh
        load_settings()
        global API_URL, API_KEY
        # Re-load environment variables in the thread
        API_URL = os.getenv("API_URL")
        API_KEY = os.getenv("API_KEY")
        
        is_post_processing = True
        post_process_file_path = file_path
        post_process_stage = "transcribe"
        
        try:
            task_id = post_task(file_path, "transcribe")
            if task_id:
                txt_output_path = os.path.join(get_application_path(), 'rec', date, name + ".txt")
                poll_and_save_result(task_id, txt_output_path)
            else:
                print(f"Failed to submit transcription task for {file_path}")
        except Exception as e:
            print(f"Error during transcription recreation for {file_path}: {e}")
        
        # Reset post-processing status
        is_post_processing = False
        post_process_file_path = ""
        post_process_stage = ""
    
    thread = Thread(target=run_transcription_task, daemon=True)
    thread.start()
    
    return "Transcription recreation started", 200

# Endpoint to recreate protocol
@app.route('/compress_to_mp3/<date>/<filename>')
def compress_to_mp3(date, filename):
    """Compress WAV file to MP3 format"""
    rec_dir = os.path.join(get_application_path(), 'rec')
    file_path = os.path.join(rec_dir, date, filename)
    
    if not os.path.exists(file_path):
        return "File not found", 404
    
    # Check if it's a WAV file
    name, ext = os.path.splitext(filename)
    if ext.lower() != '.wav':
        return "Not a WAV file", 400
    
    # Create MP3 file path
    mp3_filename = name + ".mp3"
    mp3_path = os.path.join(get_application_path(), 'rec', date, mp3_filename)
    
    def run_manual_compression():
        global is_post_processing, post_process_file_path, post_process_stage
        try:
            # Update post-processing status to compression
            is_post_processing = True
            post_process_file_path = file_path
            post_process_stage = "compression"
            
            # Load the WAV file and export as MP3
            audio = AudioSegment.from_file(file_path)
            audio.export(mp3_path, format="mp3", parameters=["-y", "-loglevel", "quiet"])
            
            # Delete the original WAV file after successful compression
            try:
                os.remove(file_path)
                print(f"Original WAV file deleted after compression: {file_path}")
            except OSError as e:
                print(f"Error deleting original WAV file {file_path}: {e}")
            
            print(f"Manual compression completed: {mp3_path}")
            
            # Reset post-processing status
            is_post_processing = False
            post_process_file_path = ""
            post_process_stage = ""
        except Exception as e:
            print(f"Error compressing file {file_path} to MP3: {e}")
            # Reset post-processing status in case of error
            is_post_processing = False
            post_process_file_path = ""
            post_process_stage = ""
    
    # Run compression in a separate thread
    Thread(target=run_manual_compression, daemon=True).start()
    
    return f"Compression started for {filename}", 200

@app.route('/recreate_protocol/<date>/<filename>')
def recreate_protocol(date, filename):
    # Reload settings to ensure API credentials are fresh
    load_settings()
    global API_URL, API_KEY
    # Re-load environment variables
    API_URL = os.getenv("API_URL")
    API_KEY = os.getenv("API_KEY")

    rec_dir = os.path.join(get_application_path(), 'rec')
    file_path = os.path.join(rec_dir, date, filename)
    
    if not os.path.exists(file_path):
        return "File not found", 404
    
    # Check if it's an audio file
    name, ext = os.path.splitext(filename)
    if ext.lower() not in ['.wav', '.mp3']:
        return "Not an audio file", 400
    
    # Check if API is configured
    if not API_URL or not API_KEY:
        return "API not configured. Please set API_URL and API_KEY in .env file", 500
    
    # Submit protocol task in a separate thread
    def run_protocol_task():
        global is_post_processing, post_process_file_path, post_process_stage
        # Reload settings in the thread to ensure API credentials are fresh
        load_settings()
        global API_URL, API_KEY
        # Re-load environment variables in the thread
        API_URL = os.getenv("API_URL")
        API_KEY = os.getenv("API_KEY")
        
        is_post_processing = True
        post_process_file_path = file_path
        post_process_stage = "protocol"
        
        try:
            # Check if transcription exists, if not, create it first
            txt_file_path = os.path.join(get_application_path(), 'rec', date, name + ".txt")
            if not os.path.exists(txt_file_path):
                # Submit transcription task first
                task_id = post_task(file_path, "transcribe")
                if task_id:
                    poll_and_save_result(task_id, txt_file_path)
                else:
                    print("Failed to submit transcription task for protocol")
                    # Reset post-processing status
                    is_post_processing = False
                    post_process_file_path = ""
                    post_process_stage = ""
                    return
            
            # Now create the protocol from the transcription
            # Check for custom prompt addition from settings
            if settings.get("use_custom_prompt", False):
                prompt_addition = settings.get("prompt_addition", "")
            else:
                prompt_addition = ""

            # Replace {current_date} placeholder with current date in 'DD MMMMM YYYY' format
            current_date_formatted = format_date_russian(datetime.now())
            prompt_addition = prompt_addition.replace("{current_date}", current_date_formatted)

            # Filter out lines that start with "//" from prompt_addition
            filtered_prompt_addition = "\n".join([
                line for line in prompt_addition.splitlines()
                if not line.strip().startswith("//")
            ])

            task_id = post_task(txt_file_path, "protocol", prompt_addition=filtered_prompt_addition)
            if task_id:
                protocol_output_path = os.path.join(get_application_path(), 'rec', date, name + "_protocol.pdf")
                poll_and_save_result(task_id, protocol_output_path)
        except Exception as e:
            print(f"Error during protocol recreation for {file_path}: {e}")
        
        # Reset post-processing status
        is_post_processing = False
        post_process_file_path = ""
        post_process_stage = ""
    
    thread = Thread(target=run_protocol_task, daemon=True)
    thread.start()
    
    return "Protocol recreation started", 200

@app.route('/')
def index():
    # Get all recordings from the 'rec' directory
    date_groups = []
    rec_dir = os.path.join(get_application_path(), 'rec')
    
    if os.path.exists(rec_dir):
        # Get all date directories
        date_dirs = [d for d in os.listdir(rec_dir) if os.path.isdir(os.path.join(rec_dir, d))]
        
        # Define Russian day names
        day_names = {
            0: 'Понедельник',
            1: 'Вторник', 
            2: 'Среда',
            3: 'Четверг',
            4: 'Пятница',
            5: 'Суббота',
            6: 'Воскресенье'
        }
        
        for date_dir in date_dirs:
            date_path = os.path.join(rec_dir, date_dir)
            
            # Parse the date to get the day of the week and formatted date
            try:
                date_obj = datetime.strptime(date_dir, '%Y-%m-%d')
                day_of_week = day_names[date_obj.weekday()]
                
                # Format date as DD MMMM YYYY in Russian
                months = {
                    1: 'Января', 2: 'Февраля', 3: 'Марта', 4: 'Апреля', 5: 'Мая', 6: 'Июня',
                    7: 'Июля', 8: 'Августа', 9: 'Сентября', 10: 'Октября', 11: 'Ноября', 12: 'Декабря'
                }
                formatted_date = f"{date_obj.day:02d} {months[date_obj.month]} {date_obj.year}"
            except ValueError:
                # If parsing fails, use the directory name as-is
                day_of_week = date_dir
                formatted_date = date_dir
            
            # Get all files in the date directory
            all_files = [f for f in os.listdir(date_path) if os.path.isfile(os.path.join(date_path, f))]
            
            # Group files by their base name (without extension)
            file_groups = {}
            for filename in all_files:
                name, ext = os.path.splitext(filename)
                if name not in file_groups:
                    file_groups[name] = {}
                file_groups[name][ext] = filename
            
            # Process each group of related files
            recordings_in_group = []
            for base_name, file_dict in file_groups.items():
                # Check if this is an audio file group (has .wav or .mp3 extension)
                audio_filename = None
                audio_filepath = None
                
                if '.wav' in file_dict:
                    audio_filename = file_dict['.wav']
                    audio_filepath = os.path.join(date_path, audio_filename)
                elif '.mp3' in file_dict:
                    audio_filename = file_dict['.mp3']
                    audio_filepath = os.path.join(date_path, audio_filename)
                
                if audio_filename and audio_filepath:
                    # Look for related files (transcription and protocol)
                    txt_filename = base_name + ".txt"
                    txt_filepath = os.path.join(date_path, txt_filename)
                    
                    # Check for different protocol file formats in order of preference
                    protocol_filename = None
                    protocol_filepath = None
                    
                    # Check for _protocol.pdf first (newest format)
                    protocol_pdf_path = os.path.join(date_path, base_name + "_protocol.pdf")
                    if os.path.exists(protocol_pdf_path):
                        protocol_filename = base_name + "_protocol.pdf"
                        protocol_filepath = protocol_pdf_path
                    # Then check for _ai.md
                    elif os.path.exists(os.path.join(date_path, base_name + "_ai.md")):
                        protocol_filename = base_name + "_ai.md"
                        protocol_filepath = os.path.join(date_path, base_name + "_ai.md")
                    # Then check for _ai.pdf
                    elif os.path.exists(os.path.join(date_path, base_name + "_ai.pdf")):
                        protocol_filename = base_name + "_ai.pdf"
                        protocol_filepath = os.path.join(date_path, base_name + "_ai.pdf")
                    # Then check for _ai.txt
                    elif os.path.exists(os.path.join(date_path, base_name + "_ai.txt")):
                        protocol_filename = base_name + "_ai.txt"
                        protocol_filepath = os.path.join(date_path, base_name + "_ai.txt")
                    # Finally check for _protocol.txt
                    elif os.path.exists(os.path.join(date_path, base_name + "_protocol.txt")):
                        protocol_filename = base_name + "_protocol.txt"
                        protocol_filepath = os.path.join(date_path, base_name + "_protocol.txt")
                    
                    # Get file creation/modification time
                    file_time = datetime.fromtimestamp(os.path.getctime(audio_filepath))
                    
                    recording_info = {
                        'date': date_dir,
                        'filename': audio_filename,
                        'filepath': audio_filepath,
                        'size': os.path.getsize(audio_filepath),
                        'time': file_time.strftime('%H:%M:%S'),
                        'transcription_exists': os.path.exists(txt_filepath),
                        'transcription_path': txt_filepath if os.path.exists(txt_filepath) else None,
                        'transcription_filename': txt_filename,
                        'protocol_exists': protocol_filepath is not None,
                        'protocol_path': protocol_filepath,
                        'protocol_filename': protocol_filename
                    }
                    recordings_in_group.append(recording_info)
            
            # Only add the group if it has recordings
            if recordings_in_group:
                # Sort recordings in this group by time (newest first)
                recordings_in_group.sort(key=lambda x: x['time'], reverse=True)
                
                date_group = {
                    'date': date_dir,
                    'day_of_week': day_of_week,
                    'formatted_date': formatted_date,
                    'recordings': recordings_in_group
                }
                date_groups.append(date_group)
    
    # Sort date groups by date (newest first)
    date_groups.sort(key=lambda x: x['date'], reverse=True)
    
    return render_template('index.html', date_groups=date_groups)

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
    if is_recording and not is_paused:
        return jsonify({"status": "error", "error": "Запись уже идет."})
    elif is_recording and is_paused:
        # Resume recording from pause
        resume_recording()
        return jsonify({"status": "rec", "time": time.strftime('%H:%M:%S', time.gmtime(get_elapsed_record_time()))})
    else:
        # Start new recording
        start_new_recording()
        return jsonify({"status": "rec", "time": 0})

@app.route('/stop', methods=['GET'])
def stop():
    global is_recording
    if not is_recording: return jsonify({"status": "error", "error": "Запись не идет."})
    
    stop_recording()
    
    return jsonify({"status": "stop", "time": time.strftime('%H:%M:%S', time.gmtime((datetime.now() - start_time).total_seconds()))})


@app.route('/pause', methods=['GET'])
def pause():
    global is_recording, is_paused
    if not is_recording: return jsonify({"status": "error", "error": "Запись не идет."})
    if is_paused: return jsonify({"status": "error", "error": "Запись уже на паузе."})

    pause_recording()

    return jsonify({"status": "paused", "time": time.strftime('%H:%M:%S', time.gmtime(get_elapsed_record_time()))})


@app.route('/resume', methods=['GET'])
def resume():
    global is_recording, is_paused
    if not is_recording: return jsonify({"status": "error", "error": "Запись не идет."})
    if not is_paused: return jsonify({"status": "error", "error": "Запись не на паузе."})

    resume_recording()

    return jsonify({"status": "rec", "time": time.strftime('%H:%M:%S', time.gmtime(get_elapsed_record_time()))})

@app.route('/status', methods=['GET'])
def status():
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

# --- Основная часть ---
def run_flask():
    global http_server
    host = '0.0.0.0' if settings.get("lan_accessible") else '127.0.0.1'
    port = settings.get("port", DEFAULT_SETTINGS["port"])
    try:
        http_server = make_server(host, port, app)
        http_server.serve_forever()
    except Exception as e:
        print(f"Failed to start Flask server: {e}")

def exit_action(icon, item):
    if flask_thread and flask_thread.is_alive() and settings.get("server_enabled"):
        print("Attempting to shut down server on exit...")
        try:
            port = settings.get("port")
            requests.post(f'http://127.0.0.1:{port}/shutdown', timeout=1, verify=False)
            flask_thread.join(timeout=2)
        except requests.exceptions.RequestException as e:
            print(f"Info: Request to shutdown endpoint failed on exit: {e}")
    icon.stop()
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

def start_new_recording():
    """Starts a new recording session"""
    global is_recording, start_time, recording_thread, frames, stop_event, is_paused, pause_start_time, total_pause_duration
    
    # Start new recording
    is_recording = True
    is_paused = False  # Reset pause state
    pause_start_time = None  # Reset pause start time
    # Don't reset total_pause_duration here as it's cumulative across pauses
    start_time = datetime.now()
    frames = {}
    stop_event.clear()

    # Simplified device selection for stability
    audio = pyaudio.PyAudio()
    device_index = audio.get_default_input_device_info()['index']
    audio.terminate()

    recording_thread = Thread(target=recorder, args=([device_index],))
    recording_thread.start()


def resume_recording():
    """Resumes a paused recording session"""
    global is_paused, pause_start_time, total_pause_duration
    
    # Calculate pause duration and add to total
    pause_duration = (datetime.now() - pause_start_time).total_seconds()
    total_pause_duration += pause_duration
    
    # Reset pause state
    is_paused = False
    pause_start_time = None


def start_recording_from_tray(icon, item):
    global is_recording, is_paused, pause_start_time, total_pause_duration
    if is_recording and not is_paused:
        print("Запись уже идет.")
        return
    elif is_recording and is_paused:
        # Resume recording from pause
        resume_recording()
        
        # Update tray menu to reflect new state
        update_tray_menu()
        
        print("Запись возобновлена.")
    else:
        start_new_recording()
        
        # Update tray menu to reflect new state
        update_tray_menu()
        
        print("Запись начата.")

def stop_recording():
    """Stops the current recording session"""
    global is_recording, start_time, recording_thread, frames, is_paused, pause_start_time, total_pause_duration

    stop_event.set()
    recording_thread.join()
    end_time = datetime.now()
    is_recording = False
    is_paused = False  # Reset pause state
    pause_start_time = None  # Reset pause start time
    total_pause_duration = 0  # Reset total pause duration

    script_dir = get_application_path()
    day_dir = os.path.join(script_dir, 'rec', start_time.strftime('%Y-%m-%d'))
    os.makedirs(day_dir, exist_ok=True)
    
    if frames:
        sound = AudioSegment(data=b''.join(frames.get(0, [])), 
                             sample_width=pyaudio.PyAudio().get_sample_size(FORMAT), 
                             frame_rate=RATE, 
                             channels=CHANNELS)
        duration = (end_time - start_time)
        minutes, seconds = divmod(int(duration.total_seconds()), 60)
        wav_filename = os.path.join(day_dir, f"{start_time.strftime('%H.%M')}_{minutes:02d}m{seconds:02d}s.wav")
        sound.export(wav_filename, format='wav')
        
        # Compress to MP3 immediately
        mp3_filename = wav_filename.replace('.wav', '.mp3')
        try:
            # Use the globally imported AudioSegment
            audio = AudioSegment.from_file(wav_filename)
            audio.export(mp3_filename, format="mp3", parameters=["-y", "-loglevel", "quiet"])
            print(f"Auto-compression completed: {mp3_filename}")
            
            # Delete the original WAV file after successful compression
            try:
                os.remove(wav_filename)
                print(f"Original WAV file deleted: {wav_filename}")
            except OSError as e:
                print(f"Error deleting original WAV file {wav_filename}: {e}")
            
            # Process the MP3 file instead of the WAV file
            Thread(target=process_recording_tasks, args=(mp3_filename,), daemon=True).start()
        except Exception as e:
            print(f"Error during auto-compression to MP3: {e}")
            # If compression fails, process the WAV file as backup
            Thread(target=process_recording_tasks, args=(wav_filename,), daemon=True).start()


def stop_recording_from_tray(icon, item):
    global is_recording
    if not is_recording: 
        print("Запись не идет.")
        return
    
    stop_recording()
    
    # Update tray menu to reflect new state
    update_tray_menu()
    
    print("Запись остановлена.")

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
    
    pause_recording()
    
    # Update tray menu to reflect new state
    update_tray_menu()
    
    print("Запись приостановлена.")

def resume_recording_from_tray(icon, item):
    global is_recording
    if not is_recording: 
        print("Запись не идет.")
        return
    if not is_paused: 
        print("Запись не на паузе.")
        return
    
    resume_recording()
    
    # Update tray menu to reflect new state
    update_tray_menu()
    
    print("Запись возобновлена.")

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
    load_settings()

    stop_icon = create_icon('square', 'gray')
    main_icon = Icon('recordServer', stop_icon, 'recordServer')

    # Start server and update menu for the first time
    start_server()

    update_thread = Thread(target=update_icon, args=(main_icon,), daemon=True)
    update_thread.start()
    
    # Start periodic tray menu update thread
    menu_update_thread = Thread(target=periodic_tray_menu_update, daemon=True)
    menu_update_thread.start()

    main_icon.run()