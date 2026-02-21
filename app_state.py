import queue
from threading import Event
from flask import Flask
import os
import io
from PIL import Image, ImageDraw

def get_application_path():
    """Get the path where the application is located, whether running as script or executable"""
    import sys
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        application_path = os.path.dirname(sys.executable)
    else:
        # Running as script
        application_path = os.path.dirname(os.path.abspath(__file__))
    return application_path


# --- Глобальные переменные ---
app = Flask(
    __name__,
    template_folder=os.path.join(get_application_path(), 'templates'),
    static_folder=os.path.join(get_application_path(), 'static')
)

is_recording = False
is_paused = False
start_time = None
pause_start_time = None
total_pause_duration = 0.0
recording_threads = []
stop_event = Event()

mic_audio_queue = queue.Queue()
sys_audio_queue = queue.Queue()
relay_audio_queue = queue.Queue()

is_post_processing = False
post_process_file_path = ""
post_process_stage = ""

audio_levels = {"mic": 0.0, "sys": 0.0}
monitoring_stop_event = Event()

http_server = None
main_icon = None

settings = {}
contacts_data = {"groups": []}

# --- Audio settings ---
RATE = 44100 # Fallback sample rate

# --- Favicon Generation ---
FAVICON_REC_BYTES = None
FAVICON_PAUSE_BYTES = None
FAVICON_STOP_BYTES = None

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
    
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='ICO', sizes=[(32,32)])
    return img_byte_arr.getvalue()

def generate_favicons():
    """Генерирует все favicon'ы при старте."""
    global FAVICON_REC_BYTES, FAVICON_PAUSE_BYTES, FAVICON_STOP_BYTES
    FAVICON_REC_BYTES = create_favicon('circle', 'red')
    FAVICON_PAUSE_BYTES = create_favicon('pause', 'orange')
    FAVICON_STOP_BYTES = create_favicon('square', 'gray')
    print("Favicons generated.")