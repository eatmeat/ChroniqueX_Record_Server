import os
import sys
import platform
import time
from datetime import datetime
from threading import Thread
import queue
import tempfile
import json
import logging

import sounddevice as sd
import numpy as np
import pyaudiowpatch as pyaudio
from pydub import AudioSegment
from tkinter import messagebox

from app_state import (
    get_application_path, is_recording, is_paused, start_time, pause_start_time,
    total_pause_duration, recording_threads, stop_event, mic_audio_queue,
    sys_audio_queue, relay_audio_queue, audio_levels, settings, RATE
)
import app_state
from postprocessing import process_recording_tasks

def get_elapsed_record_time():
    if not app_state.start_time: return 0
    current_time = datetime.now()
    elapsed = (current_time - app_state.start_time).total_seconds()
    elapsed -= app_state.total_pause_duration
    if app_state.is_paused and app_state.pause_start_time:
        elapsed -= (current_time - app_state.pause_start_time).total_seconds()
    return max(elapsed, 0)

def recorder_mic(device_index, stop_event, audio_queue):
    def callback(indata, frames, time, status):
        if status: print(status, file=sys.stderr)
        if not app_state.is_paused:
            audio_queue.put(indata.copy())
    try:
        with sd.InputStream(samplerate=app_state.RATE, device=device_index, channels=1, dtype='int16', callback=callback):
            print(f"Recording started for mic device {device_index}.")
            stop_event.wait()
    except Exception as e:
        print(f"Error during mic recording: {e}", file=sys.stderr)
    finally:
        print(f"Mic recording process finished for device {device_index}.")

def recorder_sys(stop_event, audio_queue):
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
                if not app_state.is_paused:
                    audio_queue.put(np.frombuffer(in_data, dtype=np.int16).reshape(-1, channels))
                return (in_data, pyaudio.paContinue)
            stream = p.open(format=pyaudio.paInt16, channels=channels, rate=app_state.RATE, input=True,
                            input_device_index=default_speakers["index"], stream_callback=callback)
            stream.start_stream()
            print("System audio recording started.")
            while not stop_event.is_set(): time.sleep(0.001)
            stream.stop_stream()
            stream.close()
    except Exception as e:
        print(f"Error during system audio recording: {e}", file=sys.stderr)
    finally:
        print("System audio recording process finished.")

def audio_mixer_and_writer(stop_event, mic_file, sys_file):
    import wave
    with wave.open(mic_file, 'wb') as wf_mic, wave.open(sys_file, 'wb') as wf_sys:
        wf_mic.setnchannels(1); wf_mic.setsampwidth(2); wf_mic.setframerate(app_state.RATE)
        wf_sys.setnchannels(2); wf_sys.setsampwidth(2); wf_sys.setframerate(app_state.RATE)
        while not stop_event.is_set():
            if app_state.is_paused:
                time.sleep(0.1)
                continue
            try:
                mic_data = app_state.mic_audio_queue.get_nowait()
                wf_mic.writeframes(mic_data)
                mic_data_stereo = np.repeat(mic_data, 2, axis=1)
            except queue.Empty: mic_data = mic_data_stereo = None
            try:
                sys_data = app_state.sys_audio_queue.get_nowait()
                wf_sys.writeframes(sys_data)
            except queue.Empty: sys_data = None

            if settings.get("relay_enabled"):
                mixed_chunk = None
                if mic_data_stereo is not None and sys_data is not None:
                    min_len = min(len(mic_data_stereo), len(sys_data))
                    mixed_float = mic_data_stereo[:min_len].astype(np.float32) + sys_data[:min_len].astype(np.float32)
                    mixed_chunk = np.clip(mixed_float, -32768, 32767).astype(np.int16)
                elif mic_data_stereo is not None: mixed_chunk = mic_data_stereo
                elif sys_data is not None: mixed_chunk = sys_data
                if mixed_chunk is not None: app_state.relay_audio_queue.put(mixed_chunk.tobytes())
            if mic_data is None and sys_data is None: time.sleep(0.01)

def start_recording():
    logging.info("Core start_recording function called.")
    try:
        with pyaudio.PyAudio() as p:
            wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
            app_state.RATE = int(default_speakers['defaultSampleRate'])
            logging.info(f"System audio sample rate detected: {app_state.RATE} Hz.")
    except Exception as e:
        app_state.RATE = 44100
        logging.warning(f"Could not detect system sample rate, falling back to {app_state.RATE} Hz. Error: {e}")

    mic_device_index = None
    try:
        mic_device_index = sd.default.device[0]
        logging.info(f"Default microphone found: {sd.query_devices(mic_device_index)['name']}")
    except (ValueError, sd.PortAudioError) as e:
        print(f"Could not find a default microphone: {e}")

    if mic_device_index is None and platform.system() != "Windows":
        messagebox.showerror("Ошибка записи", "Не найдено ни одного устройства для записи.")
        return

    logging.info("Setting app state for recording...")
    app_state.is_recording = True
    app_state.is_paused = False
    app_state.total_pause_duration = 0.0
    app_state.start_time = datetime.now()
    app_state.stop_event.clear()
    app_state.mic_audio_queue = queue.Queue()
    app_state.sys_audio_queue = queue.Queue()
    app_state.relay_audio_queue = queue.Queue()

    temp_dir = tempfile.gettempdir()
    timestamp = app_state.start_time.strftime('%Y%m%d_%H%M%S')
    mic_temp_file = os.path.join(temp_dir, f"{timestamp}_mic.wav")
    sys_temp_file = os.path.join(temp_dir, f"{timestamp}_sys.wav")

    logging.info("Starting recording threads...")
    app_state.recording_threads = []
    if mic_device_index is not None:
        logging.info("...starting mic thread.")
        mic_thread = Thread(target=recorder_mic, args=(mic_device_index, app_state.stop_event, app_state.mic_audio_queue))
        app_state.recording_threads.append(mic_thread)
        mic_thread.start()
    if platform.system() == "Windows":
        logging.info("...starting system audio thread.")
        sys_thread = Thread(target=recorder_sys, args=(app_state.stop_event, app_state.sys_audio_queue))
        app_state.recording_threads.append(sys_thread)
        sys_thread.start()
    logging.info("...starting mixer thread.")
    mixer_thread = Thread(target=audio_mixer_and_writer, args=(app_state.stop_event, mic_temp_file, sys_temp_file))
    app_state.recording_threads.append(mixer_thread)
    mixer_thread.start()
    logging.info("All recording threads started.")

def stop_recording():
    app_state.stop_event.set()
    for thread in app_state.recording_threads:
        if thread.is_alive(): thread.join(timeout=5)
    app_state.recording_threads = []
    end_time = datetime.now()
    app_state.is_recording = False
    app_state.is_paused = False
    app_state.total_pause_duration = 0.0

    day_dir = os.path.join(get_application_path(), 'rec', app_state.start_time.strftime('%Y-%m-%d'))
    os.makedirs(day_dir, exist_ok=True)
    temp_dir = tempfile.gettempdir()
    timestamp = app_state.start_time.strftime('%Y%m%d_%H%M%S')
    mic_temp_file = os.path.join(temp_dir, f"{timestamp}_mic.wav")
    sys_temp_file = os.path.join(temp_dir, f"{timestamp}_sys.wav")

    mic_audio = AudioSegment.from_wav(mic_temp_file) if os.path.exists(mic_temp_file) and os.path.getsize(mic_temp_file) > 44 else None
    sys_audio = AudioSegment.from_wav(sys_temp_file) if os.path.exists(sys_temp_file) and os.path.getsize(sys_temp_file) > 44 else None

    final_audio = None
    if mic_audio and sys_audio:
        if mic_audio.frame_rate != sys_audio.frame_rate: mic_audio = mic_audio.set_frame_rate(sys_audio.frame_rate)
        if mic_audio.channels == 1: mic_audio = mic_audio.set_channels(2)
        final_audio = mic_audio.overlay(sys_audio)
    elif mic_audio: final_audio = mic_audio
    elif sys_audio: final_audio = sys_audio

    if os.path.exists(mic_temp_file): os.remove(mic_temp_file)
    if os.path.exists(sys_temp_file): os.remove(sys_temp_file)
    if not final_audio: return

    duration = (end_time - app_state.start_time)
    minutes, seconds = divmod(int(duration.total_seconds()), 60)
    wav_filename = os.path.join(day_dir, f"{app_state.start_time.strftime('%H.%M')}_{minutes:02d}m{seconds:02d}s.wav")
    final_audio.export(wav_filename, format='wav')

    final_audio_path = None
    mp3_filename = wav_filename.replace('.wav', '.mp3')
    try:
        final_audio.export(mp3_filename, format="mp3", parameters=["-y", "-loglevel", "quiet"])
        final_audio_path = mp3_filename
        os.remove(wav_filename)
    except Exception as e:
        print(f"Error during auto-compression to MP3: {e}")
        final_audio_path = wav_filename

    if final_audio_path:
        json_path = os.path.splitext(final_audio_path)[0] + '.json'
        title = os.path.basename(os.path.splitext(final_audio_path)[0])
        active_template_id = settings.get("active_meeting_name_template_id")
        if active_template_id:
            templates = settings.get("meeting_name_templates", [])
            active_template = next((t for t in templates if t.get("id") == active_template_id), None)
            if active_template and active_template.get("template"): title = active_template.get("template")
        metadata = {"startTime": app_state.start_time.isoformat(), "duration": duration.total_seconds(), "title": title, "promptAddition": ""}
        with open(json_path, 'w', encoding='utf-8') as f: json.dump(metadata, f, indent=4, ensure_ascii=False)
        Thread(target=process_recording_tasks, args=(final_audio_path,), daemon=True).start()

def pause_recording():
    app_state.is_paused = True
    app_state.pause_start_time = datetime.now()

def resume_recording():
    if app_state.pause_start_time:
        app_state.total_pause_duration += (datetime.now() - app_state.pause_start_time).total_seconds()
    app_state.is_paused = False
    app_state.pause_start_time = None

def start_recording_from_tray(icon=None, item=None):
    logging.info("start_recording_from_tray called.")
    if app_state.is_recording:
        logging.warning("Recording is already in progress. Aborting start.")
        return
    def _start():
        logging.info("Background thread for starting recording is running...")
        try:
            start_recording()
            logging.info("start_recording() function completed successfully.")
        except Exception as e:
            logging.error(f"Exception in _start thread: {e}", exc_info=True)
            app_state.is_recording = False
    logging.info("Starting background thread `_start`.")
    Thread(target=_start, daemon=True).start()

def stop_recording_from_tray(icon=None, item=None):
    logging.info("stop_recording_from_tray called.")
    if not app_state.is_recording: return
    try:
        stop_recording()
        print("Запись остановлена.")
    except Exception as e:
        print(f"Ошибка при остановке записи: {e}")
        app_state.is_recording = False

def pause_recording_from_tray(icon=None, item=None):
    logging.info("pause_recording_from_tray called.")
    if not app_state.is_recording or app_state.is_paused: return
    try:
        pause_recording()
        print("Запись приостановлена.")
    except Exception as e: print(f"Ошибка при паузе записи: {e}")

def resume_recording_from_tray(icon=None, item=None):
    logging.info("resume_recording_from_tray called.")
    if not app_state.is_recording or not app_state.is_paused: return
    try:
        resume_recording()
        print("Запись возобновлена.")
    except Exception as e: print(f"Ошибка при возобновлении записи: {e}")

def monitor_mic(stop_event):
    try:
        mic_device_index = sd.default.device[0]
        samplerate = sd.query_devices(mic_device_index, 'input')['default_samplerate']
        def callback(indata, frames, time, status):
            if status: print(status, file=sys.stderr)
            rms = np.sqrt(np.mean(np.square(indata.astype(np.float32) / 32768.0)))
            audio_levels["mic"] = float(rms)
        with sd.InputStream(samplerate=samplerate, device=mic_device_index, channels=1, dtype='int16', callback=callback):
            stop_event.wait()
    except Exception as e:
        print(f"Ошибка мониторинга микрофона: {e}", file=sys.stderr)
        audio_levels["mic"] = -1

def monitor_sys(stop_event):
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
            stream = p.open(format=pyaudio.paInt16, channels=default_speakers["maxInputChannels"],
                            rate=int(default_speakers['defaultSampleRate']), input=True,
                            input_device_index=default_speakers["index"], stream_callback=callback)
            stream.start_stream()
            stop_event.wait()
            stream.stop_stream()
            stream.close()
    except Exception as e:
        print(f"Ошибка мониторинга системного аудио: {e}", file=sys.stderr)
        audio_levels["sys"] = -1