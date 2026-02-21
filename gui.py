import tkinter as tk
from tkinter import messagebox
from werkzeug.security import generate_password_hash
import os
import sys

from app_state import get_application_path, settings
from config_manager import save_settings, DEFAULT_SETTINGS

main_window_instance = None

def _add_context_menu_to_text_widget(text_widget):
    """Add a context menu to a text widget with common text editing commands"""
    if isinstance(text_widget, tk.Text):
        text_widget.config(undo=True, maxundo=20)

    context_menu = tk.Menu(text_widget, tearoff=0)

    context_menu.add_command(label="Выделить всё", command=lambda: _select_all(text_widget))
    if isinstance(text_widget, tk.Text):
        context_menu.add_command(label="Найти", command=lambda: _find_text(text_widget))
        context_menu.add_separator()
    context_menu.add_command(label="Вырезать", command=lambda: _cut_text(text_widget))
    context_menu.add_command(label="Копировать", command=lambda: _copy_text(text_widget))
    context_menu.add_command(label="Вставить", command=lambda: _paste_text(text_widget))
    
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
        context_menu.add_separator()
        context_menu.add_command(label="Очистить", command=lambda: _clear_text_widget(text_widget))

    def universal_key_handler(event):
        ctrl_pressed = event.state & 0x4
        shift_pressed = event.state & 0x1

        if ctrl_pressed:
            if event.keycode == 88: return (_cut_text(text_widget), "break")[1]
            elif event.keycode == 67: return (_copy_text(text_widget), "break")[1]
            elif event.keycode == 86: return (_paste_text(text_widget), "break")[1]
            elif event.keycode == 65: return (_select_all(text_widget), "break")[1]
            elif event.keycode == 90: return (_undo_text(text_widget), "break")[1]
            elif event.keycode == 89: return (_redo_text(text_widget), "break")[1]
            elif event.keycode == 19:
                if shift_pressed: return (_uncomment_lines(text_widget), "break")[1]
                else: return (_comment_lines(text_widget), "break")[1]
            elif event.keycode == 69: return (_copy_text(text_widget), "break")[1]
        elif shift_pressed and event.keycode == 69:
            return (_paste_text(text_widget), "break")[1]
        return None

    text_widget.bind("<Control-KeyPress>", universal_key_handler)

    def show_context_menu_wrapper(event):
        original_state = text_widget.cget("state")
        if original_state == "disabled":
            text_widget.config(state="normal")
            context_menu.tk_popup(event.x_root, event.y_root)
            text_widget.config(state=original_state)
        else:
            context_menu.tk_popup(event.x_root, event.y_root)

    try:
        text_widget.bind("<Button-3>", show_context_menu_wrapper)
    except tk.TclError:
        text_widget.bind("<Control-Button-1>", show_context_menu_wrapper)

def _undo_text(text_widget):
    if isinstance(text_widget, tk.Text):
        try: text_widget.edit_undo()
        except tk.TclError: pass

def _redo_text(text_widget):
    if isinstance(text_widget, tk.Text):
        try: text_widget.edit_redo()
        except tk.TclError: pass

def _comment_lines(text_widget):
    if isinstance(text_widget, tk.Text):
        try:
            start_pos = text_widget.index("sel.first")
            end_pos = text_widget.index("sel.last")
            start_line = int(start_pos.split('.')[0])
            end_line = int(end_pos.split('.')[0])
            end_col = int(end_pos.split('.')[1])
            if end_col == 0 and start_line != end_line: end_line -= 1

            for line_num in range(start_line, end_line + 1):
                line_start = f"{line_num}.0"
                line_end = f"{line_num}.end"
                line_content = text_widget.get(line_start, line_end)
                text_widget.delete(line_start, line_end)
                text_widget.insert(line_start, "//" + line_content)

            text_widget.tag_remove("sel", "1.0", "end")
            text_widget.tag_add("sel", f"{start_line}.0", f"{end_line + 1}.0")
        except tk.TclError:
            current_line = text_widget.index("insert").split('.')[0]
            line_start = f"{current_line}.0"
            line_end = f"{current_line}.end"
            line_content = text_widget.get(line_start, line_end)
            text_widget.delete(line_start, line_end)
            text_widget.insert(line_start, "//" + line_content)

def _uncomment_lines(text_widget):
    if isinstance(text_widget, tk.Text):
        try:
            start_pos = text_widget.index("sel.first")
            end_pos = text_widget.index("sel.last")
            start_line = int(start_pos.split('.')[0])
            end_line = int(end_pos.split('.')[0])
            end_col = int(end_pos.split('.')[1])
            if end_col == 0 and start_line != end_line: end_line -= 1

            for line_num in range(start_line, end_line + 1):
                line_start = f"{line_num}.0"
                line_end = f"{line_num}.end"
                line_content = text_widget.get(line_start, line_end)
                if line_content.startswith("//"):
                    text_widget.delete(line_start, line_end)
                    text_widget.insert(line_start, line_content[2:])

            text_widget.tag_remove("sel", "1.0", "end")
            text_widget.tag_add("sel", f"{start_line}.0", f"{end_line + 1}.0")
        except tk.TclError:
            current_line = text_widget.index("insert").split('.')[0]
            line_start = f"{current_line}.0"
            line_end = f"{current_line}.end"
            line_content = text_widget.get(line_start, line_end)
            if line_content.startswith("//"):
                text_widget.delete(line_start, line_end)
                text_widget.insert(line_start, line_content[2:])

def _select_all(text_widget):
    if isinstance(text_widget, tk.Text):
        text_widget.tag_add("sel", "1.0", "end")
        text_widget.mark_set("insert", "end")
        text_widget.see("insert")
    elif isinstance(text_widget, tk.Entry):
        text_widget.select_range(0, tk.END)
        text_widget.icursor(tk.END)

def _find_text(text_widget):
    find_window = tk.Toplevel(text_widget.winfo_toplevel())
    find_window.title("Найти")
    find_window.geometry("300x100")
    find_window.resizable(False, False)
    find_window.transient(text_widget.winfo_toplevel())
    find_window.grab_set()

    tk.Label(find_window, text="Найти:").pack(pady=5)
    search_var = tk.StringVar()
    entry = tk.Entry(find_window, textvariable=search_var, width=30)
    entry.pack(pady=5)
    entry.focus()

    button_frame = tk.Frame(find_window)
    button_frame.pack(pady=5)

    def find_next():
        search_term = search_var.get()
        if not search_term: return
        start_pos = text_widget.search(search_term, tk.INSERT, tk.END)
        if start_pos:
            end_pos = f"{start_pos}+{len(search_term)}c"
            text_widget.tag_remove("found", "1.0", tk.END)
            text_widget.tag_add("found", start_pos, end_pos)
            text_widget.tag_config("found", background="yellow", foreground="black")
            text_widget.see(start_pos)
            text_widget.mark_set(tk.INSERT, end_pos)

    def close_dialog():
        text_widget.tag_remove("found", "1.0", tk.END)
        find_window.destroy()

    entry.bind('<Return>', lambda e: find_next())
    tk.Button(button_frame, text="Найти далее", command=find_next).pack(side=tk.LEFT, padx=5)
    tk.Button(button_frame, text="Закрыть", command=close_dialog).pack(side=tk.LEFT, padx=5)
    find_window.protocol("WM_DELETE_WINDOW", close_dialog)
    x = text_widget.winfo_toplevel().winfo_x() + 50
    y = text_widget.winfo_toplevel().winfo_y() + 50
    find_window.geometry(f"+{x}+{y}")

def _cut_text(text_widget):
    if isinstance(text_widget, tk.Text):
        if text_widget.tag_ranges("sel"):
            text_widget.clipboard_clear()
            text_widget.clipboard_append(text_widget.get("sel.first", "sel.last"))
            text_widget.delete("sel.first", "sel.last")
    elif isinstance(text_widget, tk.Entry):
        try:
            text_widget.clipboard_clear()
            selected_text = text_widget.selection_get()
            text_widget.clipboard_append(selected_text)
            text_widget.delete("sel.first", "sel.last")
        except tk.TclError: pass
    return "break"

def _copy_text(text_widget):
    if isinstance(text_widget, tk.Text):
        if text_widget.tag_ranges("sel"):
            text_widget.clipboard_clear()
            text_widget.clipboard_append(text_widget.get("sel.first", "sel.last"))
    elif isinstance(text_widget, tk.Entry):
        try:
            text_widget.clipboard_clear()
            selected_text = text_widget.selection_get()
            text_widget.clipboard_append(selected_text)
        except tk.TclError:
            text_widget.clipboard_clear()
            text_widget.clipboard_append(text_widget.get())
    return "break"

def _paste_text(text_widget):
    try:
        clipboard_content = text_widget.clipboard_get()
        if clipboard_content:
            if isinstance(text_widget, tk.Text):
                if text_widget.tag_ranges("sel"):
                    text_widget.delete("sel.first", "sel.last")
                text_widget.insert("insert", clipboard_content)
            elif isinstance(text_widget, tk.Entry):
                try: text_widget.delete("sel.first", "sel.last")
                except tk.TclError: pass
                text_widget.insert("insert", clipboard_content)
    except tk.TclError: pass
    return "break"

def _clear_text_widget(text_widget):
    state_before = text_widget.cget("state")
    text_widget.config(state="normal")
    if isinstance(text_widget, tk.Text):
        text_widget.delete(1.0, tk.END)
    elif isinstance(text_widget, tk.Entry):
        text_widget.delete(0, tk.END)
    text_widget.config(state=state_before)
    if state_before == "disabled":
        text_widget.config(state="disabled")

def open_web_interface(icon=None, item=None):
    """Открывает веб-интерфейс в браузере по умолчанию."""
    if settings.get("server_enabled"):
        import webbrowser
        port = settings.get("port", DEFAULT_SETTINGS["port"])
        url = f"http://127.0.0.1:{port}/"
        webbrowser.open(url)
    else:
        print("Веб-сервер отключен. Невозможно открыть интерфейс.")

def open_main_window(icon=None, item=None, restart_server_cb=None):
    global main_window_instance
    if main_window_instance and main_window_instance.winfo_exists():
        main_window_instance.deiconify()
        main_window_instance.lift()
        main_window_instance.focus_force()
        print("Main window already open. Bringing to front.")
        return

    main_window_instance = None
    old_settings = settings.copy()
    
    dotenv_path = os.path.join(get_application_path(), '.env')
    API_URL = os.getenv("CRS_API_URL")
    API_KEY = os.getenv("CRS_API_KEY")
    USERNAME = os.getenv("CRS_USERNAME")
    PASSWORD_HASH = os.getenv("CRS_PASSWORD_HASH")

    def on_close_prompt():
        win.destroy()

    def on_save():
        nonlocal API_URL, API_KEY, USERNAME, PASSWORD_HASH
        
        try:
            new_port = int(port_var.get())
            if not (1024 <= new_port <= 65535):
                raise ValueError("Порт должен быть между 1024 и 65535.")

            x = win.winfo_x()
            y = win.winfo_y()
            width = win.winfo_width()
            height = win.winfo_height()

            new_username = new_username_var.get().strip()
            new_password = new_password_var.get()
            confirm_password = confirm_password_var.get()

            env_data = {}
            if os.path.exists(dotenv_path):
                with open(dotenv_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if '=' in line:
                            key, value = line.strip().split('=', 1)
                            if value.startswith('"') and value.endswith('"'):
                                value = value[1:-1]
                            env_data[key] = value

            env_data['CRS_API_URL'] = api_url_var.get()
            env_data['CRS_API_KEY'] = api_key_var.get()

            if new_username and new_username != USERNAME:
                env_data['CRS_USERNAME'] = new_username

            if new_password:
                if new_password != confirm_password:
                    messagebox.showerror("Ошибка", "Пароли не совпадают.", parent=win)
                    return
                env_data['CRS_PASSWORD_HASH'] = generate_password_hash(new_password)

            with open(dotenv_path, 'w', encoding='utf-8') as f:
                for key, value in env_data.items():
                    f.write(f'{key}="{value}"\n')

            new_settings = {
                **settings,
                "port": new_port,
                "server_enabled": server_enabled_var.get(),
                "lan_accessible": lan_accessible_var.get(),
                "main_window_width": width, "main_window_height": height,
                "main_window_x": x, "main_window_y": y
            }

            restart_needed = (
                old_settings.get('port') != new_settings.get('port') or
                old_settings.get('server_enabled') != new_settings.get('server_enabled') or
                old_settings.get('lan_accessible') != new_settings.get('lan_accessible')
            )
            save_settings(new_settings)
            
            API_URL = api_url_var.get()
            API_KEY = api_key_var.get()
            USERNAME = env_data.get('CRS_USERNAME')
            PASSWORD_HASH = env_data.get('CRS_PASSWORD_HASH')
            new_password_var.set("")
            confirm_password_var.set("")

            if restart_needed and restart_server_cb:
                messagebox.showinfo("Применение", "Настройки сохранены. Сервер будет перезапущен.", parent=win)
                restart_server_cb(old_settings)
                mark_as_saved()
            else:
                messagebox.showinfo("Сохранено", "Настройки сохранены.", parent=win)
                mark_as_saved()

        except ValueError as e:
            messagebox.showerror("Ошибка", f"Неверное значение для порта: {e}", parent=win)

    def on_hide():
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
        win.withdraw()

    def on_destroy():
        on_hide()
        if hasattr(win, '_after_jobs'):
            for job_id in win._after_jobs:
                win.after_cancel(job_id)
        global main_window_instance
        main_window_instance = None
        win.destroy()
        
    win = tk.Tk()
    win.title("ChroniqueX - Запись @ Транскрибация @ Протоколы")

    original_settings = {}
    settings_changed = tk.BooleanVar(value=False)

    def mark_as_changed(*args):
        settings_changed.set(True)

    def mark_as_saved():
        settings_changed.set(False)
        capture_original_settings()

    def update_ui_for_changes(*args):
        if settings_changed.get():
            win.title("ChroniqueX - Настройки *")
            save_button.config(text="Сохранить *")
        else:
            win.title("ChroniqueX - Настройки")
            save_button.config(text="Сохранить")

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
    win.protocol("WM_DELETE_WINDOW", on_hide)

    win.grid_rowconfigure(0, weight=1)
    win.grid_columnconfigure(0, weight=1)

    main_frame = tk.Frame(win)
    main_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
    main_frame.grid_rowconfigure(1, weight=1)
    main_frame.grid_columnconfigure(0, weight=1)

    settings_container = tk.Frame(main_frame)
    settings_container.grid(row=0, column=0, sticky="new", padx=10, pady=5)
    settings_container.grid_columnconfigure(0, weight=1)

    port_var = tk.StringVar(value=str(settings.get("port", DEFAULT_SETTINGS["port"])))
    server_enabled_var = tk.BooleanVar(value=settings.get("server_enabled", DEFAULT_SETTINGS["server_enabled"]))
    lan_accessible_var = tk.BooleanVar(value=settings.get("lan_accessible"))
    api_url_var = tk.StringVar(value=str(API_URL or "https://www.chroniquex.ru:16040"))
    api_key_var = tk.StringVar(value=str(API_KEY or ""))
    new_username_var = tk.StringVar(value=str(USERNAME or ""))
    new_password_var = tk.StringVar()
    confirm_password_var = tk.StringVar()

    def capture_original_settings():
        original_settings['port'] = port_var.get()
        original_settings['server_enabled'] = server_enabled_var.get()
        original_settings['lan_accessible'] = lan_accessible_var.get()
        original_settings['api_url'] = api_url_var.get()
        original_settings['api_key'] = api_key_var.get()
        original_settings['username'] = new_username_var.get()

    spacer_frame = tk.Frame(settings_container, height=20)
    spacer_frame.pack()

    server_settings_frame = tk.LabelFrame(settings_container, text="Настройки сервера", padx=10, pady=10)
    server_settings_frame.pack(fill="x", expand=True)
    server_settings_frame.grid_columnconfigure(1, weight=1)

    api_settings_frame = tk.LabelFrame(settings_container, text="Настройки API ChroniqueX", padx=10, pady=10)
    api_settings_frame.pack(fill="x", expand=True, pady=(10, 0))
    api_settings_frame.grid_columnconfigure(1, weight=1)

    tk.Label(api_settings_frame, text="API URL:").grid(row=0, column=0, sticky="w", pady=5, padx=(0, 5))
    api_url_edit = tk.Entry(api_settings_frame, textvariable=api_url_var)
    api_url_edit.grid(row=0, column=1, sticky="ew", padx=5)
    _add_context_menu_to_text_widget(api_url_edit)

    tk.Label(api_settings_frame, text="API Key:").grid(row=1, column=0, sticky="w", pady=5, padx=(0, 5))
    api_key_edit = tk.Entry(api_settings_frame, textvariable=api_key_var, show="*")
    api_key_edit.grid(row=1, column=1, sticky="ew", padx=5)
    _add_context_menu_to_text_widget(api_key_edit)

    account_settings_frame = tk.LabelFrame(settings_container, text="Учетная запись веб-интерфейса", padx=10, pady=10)
    account_settings_frame.pack(fill="x", expand=True, pady=(10, 0))
    account_settings_frame.grid_columnconfigure(1, weight=1)

    tk.Label(account_settings_frame, text="Логин:").grid(row=0, column=0, sticky="w", pady=5, padx=(0, 5))
    username_edit = tk.Entry(account_settings_frame, textvariable=new_username_var)
    username_edit.grid(row=0, column=1, sticky="ew", padx=5)
    _add_context_menu_to_text_widget(username_edit)

    tk.Label(account_settings_frame, text="Новый пароль:").grid(row=1, column=0, sticky="w", pady=5, padx=(0, 5))
    password_edit = tk.Entry(account_settings_frame, textvariable=new_password_var, show="*")
    password_edit.grid(row=1, column=1, sticky="ew", padx=5)
    _add_context_menu_to_text_widget(password_edit)

    tk.Label(account_settings_frame, text="Подтвердите пароль:").grid(row=2, column=0, sticky="w", pady=5, padx=(0, 5))
    confirm_password_edit = tk.Entry(account_settings_frame, textvariable=confirm_password_var, show="*")
    confirm_password_edit.grid(row=2, column=1, sticky="ew", padx=5)
    _add_context_menu_to_text_widget(confirm_password_edit)

    button_frame = tk.Frame(settings_container)
    button_frame.pack(pady=10)
    save_button = tk.Button(button_frame, text="Сохранить", command=on_save)
    save_button.pack(side="left", padx=5)
    tk.Button(button_frame, text="Свернуть", command=on_hide).pack(side="left", padx=5)

    endpoints_frame = tk.LabelFrame(main_frame, text="Адреса и эндпоинты сервера", padx=10, pady=10)
    endpoints_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
    endpoints_frame.grid_columnconfigure(0, weight=1)
    
    endpoints_links_frame = tk.Frame(endpoints_frame)
    endpoints_links_frame.pack(fill=tk.BOTH, expand=True)
    
    endpoint_labels = {}
    
    def update_endpoint_links():
        for label in endpoint_labels.values():
            label.destroy()
        endpoint_labels.clear()
        
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
            full_url = f"http://localhost:{current_port}{endpoint}"
            
            row_frame = tk.Frame(endpoints_links_frame)
            row_frame.grid(row=i, column=0, sticky="w", padx=5, pady=2)
            
            get_label = tk.Label(row_frame, text="GET ", anchor="w", justify=tk.LEFT)
            get_label.pack(side=tk.LEFT)
            
            url_label = tk.Label(row_frame, text=full_url, fg="blue", cursor="hand2", anchor="w", justify=tk.LEFT)
            url_label.pack(side=tk.LEFT)
            
            desc_label = tk.Label(row_frame, text=f" - {description}", anchor="w", justify=tk.LEFT)
            desc_label.pack(side=tk.LEFT)
            
            def make_callback(url):
                def callback(event):
                    import webbrowser
                    webbrowser.open(url)
                return callback
            
            url_label.bind("<Button-1>", make_callback(full_url))
            
            def on_enter(e): e.widget.config(cursor="hand2")
            def on_leave(e): e.widget.config(cursor="arrow")
            
            url_label.bind("<Enter>", on_enter)
            url_label.bind("<Leave>", on_leave)
            
            endpoint_labels[endpoint] = url_label
    
    update_endpoint_links()
    
    def on_port_change(*args):
        update_endpoint_links()
    
    port_var.trace_add("write", on_port_change)

    tk.Label(server_settings_frame, text="Порт:").grid(row=0, column=0, sticky="w", pady=5, padx=(0, 5))
    port_edit = tk.Entry(server_settings_frame, textvariable=port_var)
    port_edit.grid(row=0, column=1, sticky="w", padx=5)
    _add_context_menu_to_text_widget(port_edit)
    tk.Checkbutton(server_settings_frame, text="Сервер запущен", variable=server_enabled_var).grid(row=1, column=0, columnspan=2, sticky="w", padx=5)
    tk.Checkbutton(server_settings_frame, text="Доступен по локальной сети (host 0.0.0.0)", variable=lan_accessible_var).grid(row=2, column=0, columnspan=2, sticky="w", padx=5)

    capture_original_settings()
    settings_changed.trace_add("write", update_ui_for_changes)
    port_var.trace_add("write", mark_as_changed)
    server_enabled_var.trace_add("write", mark_as_changed)
    lan_accessible_var.trace_add("write", mark_as_changed)
    api_url_var.trace_add("write", mark_as_changed)
    api_key_var.trace_add("write", mark_as_changed)
    new_username_var.trace_add("write", mark_as_changed)
    new_password_var.trace_add("write", mark_as_changed)
    confirm_password_var.trace_add("write", mark_as_changed)
    win.mainloop()

def prompt_for_initial_config():
    """
    Показывает окно для первоначальной настройки, если учетные данные или API ключи отсутствуют.
    """
    dotenv_path = os.path.join(get_application_path(), '.env')
    USERNAME = os.getenv("CRS_USERNAME")
    PASSWORD_HASH = os.getenv("CRS_PASSWORD_HASH")
    API_URL = os.getenv("CRS_API_URL")
    API_KEY = os.getenv("CRS_API_KEY")

    missing_creds = not USERNAME or not PASSWORD_HASH
    missing_api = not API_URL or not API_KEY

    if not missing_creds and not missing_api:
        return

    win = tk.Tk()
    win.title("Первоначальная настройка")
    win.transient(); win.grab_set()

    main_frame = tk.Frame(win, padx=15, pady=15)
    main_frame.pack(fill="both", expand=True)

    username_var = tk.StringVar()
    password_var = tk.StringVar()
    password_confirm_var = tk.StringVar()
    api_url_var = tk.StringVar(value="https://www.chroniquex.ru:16040")
    api_key_var = tk.StringVar()

    if missing_creds:
        creds_frame = tk.LabelFrame(main_frame, text="Создайте учетную запись для веб-интерфейса", padx=10, pady=10)
        creds_frame.pack(fill="x", expand=True, pady=5)
        creds_frame.grid_columnconfigure(1, weight=1)

        tk.Label(creds_frame, text="Логин:").grid(row=0, column=0, sticky="w", pady=2)
        tk.Entry(creds_frame, textvariable=username_var).grid(row=0, column=1, sticky="ew", pady=2)

        tk.Label(creds_frame, text="Пароль:").grid(row=1, column=0, sticky="w", pady=2)
        tk.Entry(creds_frame, textvariable=password_var, show="*").grid(row=1, column=1, sticky="ew", pady=2)

        tk.Label(creds_frame, text="Повторите пароль:").grid(row=2, column=0, sticky="w", pady=2)
        tk.Entry(creds_frame, textvariable=password_confirm_var, show="*").grid(row=2, column=1, sticky="ew", pady=2)

    if missing_api:
        api_frame = tk.LabelFrame(main_frame, text="Введите данные API ChroniqueX", padx=10, pady=10)
        api_frame.pack(fill="x", expand=True, pady=5)
        api_frame.grid_columnconfigure(1, weight=1)

        tk.Label(api_frame, text="API URL:").grid(row=0, column=0, sticky="w", pady=2)
        tk.Entry(api_frame, textvariable=api_url_var).grid(row=0, column=1, sticky="ew", pady=2)

        tk.Label(api_frame, text="API Key:").grid(row=1, column=0, sticky="w", pady=2)
        tk.Entry(api_frame, textvariable=api_key_var).grid(row=1, column=1, sticky="ew", pady=2)

    def save_initial_config():
        env_data = {}
        if os.path.exists(dotenv_path):
            with open(dotenv_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if '=' in line:
                        key, value = line.strip().split('=', 1)
                        env_data[key] = value

        if missing_creds:
            username = username_var.get().strip()
            password = password_var.get()
            password_confirm = password_confirm_var.get()

            if not username or not password:
                messagebox.showerror("Ошибка", "Логин и пароль не могут быть пустыми.", parent=win)
                return
            if password != password_confirm:
                messagebox.showerror("Ошибка", "Пароли не совпадают.", parent=win)
                return
            env_data['CRS_USERNAME'] = username
            env_data['CRS_PASSWORD_HASH'] = generate_password_hash(password)

        if missing_api:
            api_url = api_url_var.get().strip()
            api_key = api_key_var.get().strip()
            if not api_url or not api_key:
                messagebox.showerror("Ошибка", "API URL и API Key не могут быть пустыми.", parent=win)
                return
            env_data['CRS_API_URL'] = api_url
            env_data['CRS_API_KEY'] = api_key

        with open(dotenv_path, 'w', encoding='utf-8') as f:
            for key, value in env_data.items():
                f.write(f'{key}="{value}"\n')

        messagebox.showinfo("Успех", "Настройки сохранены. Приложение будет перезапущено для их применения.", parent=win)
        win.destroy()
        os.execv(sys.executable, ['python'] + sys.argv)

    button_frame = tk.Frame(main_frame)
    button_frame.pack(pady=10)
    tk.Button(button_frame, text="Сохранить и перезапустить", command=save_initial_config).pack()

    win.protocol("WM_DELETE_WINDOW", lambda: sys.exit(0))
    win.eval('tk::PlaceWindow . center')
    win.mainloop()

def check_and_prompt_config():
    """Проверяет наличие конфигурации и запрашивает ее у пользователя при необходимости."""
    USERNAME = os.getenv("CRS_USERNAME")
    PASSWORD_HASH = os.getenv("CRS_PASSWORD_HASH")
    API_URL = os.getenv("CRS_API_URL")
    API_KEY = os.getenv("CRS_API_KEY")
    if not all([USERNAME, PASSWORD_HASH, API_URL, API_KEY]):
        prompt_for_initial_config()