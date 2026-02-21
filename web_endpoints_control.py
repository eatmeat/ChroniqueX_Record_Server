from flask import Blueprint, jsonify, Response
from threading import Thread
import time
import os
import queue
import wave

from recorder import (
    start_recording_from_tray, stop_recording_from_tray,
    pause_recording_from_tray, resume_recording_from_tray,
    get_elapsed_record_time
)
import app_state

control_bp = Blueprint('control', __name__)

@control_bp.route('/rec')
def rec():
    Thread(target=start_recording_from_tray, daemon=True).start()
    return jsonify({"status": "ok", "message": "Recording command sent."})

@control_bp.route('/stop')
def stop():
    Thread(target=stop_recording_from_tray, daemon=True).start()
    return jsonify({"status": "ok", "message": "Stop command sent."})

@control_bp.route('/pause')
def pause():
    Thread(target=pause_recording_from_tray, daemon=True).start()
    return jsonify({"status": "ok", "message": "Pause command sent."})

@control_bp.route('/resume')
def resume():
    Thread(target=resume_recording_from_tray, daemon=True).start()
    return jsonify({"status": "ok", "message": "Resume command sent."})

@control_bp.route('/status')
def status():
    if app_state.is_recording:
        status_str = "paused" if app_state.is_paused else "rec"
        rec_time = time.strftime('%H:%M:%S', time.gmtime(get_elapsed_record_time()))
        recording_status = {"status": status_str, "time": rec_time, "is_paused": app_state.is_paused}
    else:
        recording_status = {"status": "stop", "time": "00:00:00"}

    if app_state.is_post_processing:
        stage_map = {"transcribe": "Транскрибация", "protocol": "Создание протокола"}
        info = f"{stage_map.get(app_state.post_process_stage, 'Постобработка')} файла: {os.path.basename(app_state.post_process_file_path)}"
    else:
        info = "Постобработка не выполняется"
    
    recording_status["post_processing"] = {"active": app_state.is_post_processing, "info": info, "stage": app_state.post_process_stage if app_state.is_post_processing else None}
    return jsonify(recording_status)

@control_bp.route('/audio_levels')
def get_audio_levels():
    return jsonify(app_state.audio_levels)

@control_bp.route('/shutdown', methods=['POST'])
def shutdown():
    def do_shutdown():
        if app_state.http_server: app_state.http_server.shutdown()
    Thread(target=do_shutdown).start()
    return 'Server is shutting down...'