import sounddevice as sd
import numpy as np
import threading
import time
import queue
from collections import defaultdict
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL

class AudioMixer:
    def __init__(self, sample_rate=48000, block_size=1024, channels=2):
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.channels = channels
        self.running = False
        
        # Хранилище активных потоков
        self.streams = {}
        self.stream_lock = threading.Lock()
        
        # Очереди для буферизации аудио от каждого источника
        self.audio_queues = defaultdict(queue.Queue)
        
        # Состояние устройств
        self.device_states = {}
        self.device_monitor_thread = None
        
        # Выходной поток для воспроизведения микса
        self.output_stream = None
        
        # Коэффициенты усиления
        self.gains = defaultdict(lambda: 1.0)
        
        print(f"Доступные аудиоустройства:")
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            print(f"[{i}] {dev['name']} (in={dev['max_input_channels']}, out={dev['max_output_channels']})")

    def start_device_monitoring(self, check_interval=2.0):
        """Мониторинг подключения/отключения устройств"""
        def monitor():
            while self.running:
                try:
                    current_devices = {dev['name']: dev for dev in sd.query_devices()}
                    with self.stream_lock:
                        # Проверка отключённых устройств
                        for dev_name in list(self.device_states.keys()):
                            if dev_name not in current_devices:
                                print(f"⚠️ Устройство отключено: {dev_name}")
                                self._stop_stream(dev_name)
                                del self.device_states[dev_name]
                        
                        # Проверка новых устройств (опционально можно автоматически добавлять)
                        # Здесь оставляем решение за пользователем через API
                        
                    time.sleep(check_interval)
                except Exception as e:
                    print(f"Ошибка мониторинга устройств: {e}")
                    time.sleep(check_interval)
        
        self.device_monitor_thread = threading.Thread(target=monitor, daemon=True)
        self.device_monitor_thread.start()

    def start_microphone(self, device_name=None, device_id=None, gain=1.0):
        """Запуск захвата с микрофона"""
        try:
            if device_id is None and device_name:
                devices = sd.query_devices()
                for i, dev in enumerate(devices):
                    if device_name.lower() in dev['name'].lower() and dev['max_input_channels'] > 0:
                        device_id = i
                        device_name = dev['name']
                        break
            
            if device_id is None:
                # Используем устройство по умолчанию
                device = sd.default.device[0]
                device_info = sd.query_devices(device)
                device_id = device
                device_name = device_info['name']
            
            if device_name in self.streams:
                print(f"Микрофон уже запущен: {device_name}")
                return False
            
            def audio_callback(indata, frames, time, status):
                if status:
                    print(f"Статус микрофона ({device_name}): {status}")
                if len(indata) > 0:
                    # Применяем усиление
                    data = indata.copy() * self.gains[device_name]
                    self.audio_queues[device_name].put(data.copy(), block=False)
            
            stream = sd.InputStream(
                device=device_id,
                channels=self.channels,
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                callback=audio_callback,
                dtype='float32'
            )
            
            stream.start()
            
            with self.stream_lock:
                self.streams[device_name] = {
                    'stream': stream,
                    'type': 'microphone',
                    'device_id': device_id
                }
                self.device_states[device_name] = 'active'
                self.gains[device_name] = gain
            
            print(f"🎤 Микрофон запущен: {device_name} (ID: {device_id})")
            return True
            
        except Exception as e:
            print(f"Ошибка запуска микрофона {device_name or device_id}: {e}")
            return False

    def start_system_audio(self, device_name=None, gain=1.0):
        """Захват системного звука через loopback (только Windows)"""
        try:
            import sounddevice as sd
            
            # Поиск устройства воспроизведения для loopback
            devices = sd.query_devices()
            target_device = None
            
            if device_name:
                for i, dev in enumerate(devices):
                    if device_name.lower() in dev['name'].lower() and dev['max_output_channels'] > 0:
                        target_device = i
                        device_name = dev['name']
                        break
            else:
                # Используем устройство вывода по умолчанию
                target_device = sd.default.device[1]
                device_info = sd.query_devices(target_device)
                device_name = device_info['name']
            
            if device_name in self.streams:
                print(f"Системный звук уже захватывается: {device_name}")
                return False
            
            def audio_callback(indata, frames, time, status):
                if status:
                    print(f"Статус системного звука ({device_name}): {status}")
                if len(indata) > 0:
                    data = indata.copy() * self.gains[device_name]
                    self.audio_queues[device_name].put(data.copy(), block=False)
            
            # Loopback захват работает только с определёнными хостами API
            stream = sd.InputStream(
                device=target_device,
                channels=self.channels,
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                callback=audio_callback,
                dtype='float32',
                extra_settings=sd.WasapiSettings(exclusive=False, loopback=True)  # Ключевой параметр!
            )
            
            stream.start()
            
            with self.stream_lock:
                self.streams[device_name] = {
                    'stream': stream,
                    'type': 'system',
                    'device_id': target_device
                }
                self.device_states[device_name] = 'active'
                self.gains[device_name] = gain
            
            print(f"🔊 Системный звук запущен: {device_name} (ID: {target_device})")
            return True
            
        except Exception as e:
            print(f"Ошибка захвата системного звука: {e}")
            print("💡 Убедитесь, что:")
            print("  1. Используется Windows 10/11")
            print("  2. Установлены драйверы с поддержкой WASAPI")
            print("  3. Для loopback может потребоваться 'разрешить приложениям перехватывать аудио' в настройках Windows")
            return False

    def stop_source(self, device_name):
        """Остановка конкретного источника звука"""
        with self.stream_lock:
            if device_name in self.streams:
                self._stop_stream(device_name)
                del self.streams[device_name]
                self.device_states[device_name] = 'inactive'
                print(f"⏹ Источник остановлен: {device_name}")
                return True
        print(f"Источник не найден: {device_name}")
        return False

    def _stop_stream(self, device_name):
        """Внутренний метод остановки потока"""
        try:
            stream_info = self.streams.get(device_name)
            if stream_info and stream_info['stream']:
                stream_info['stream'].stop()
                stream_info['stream'].close()
        except Exception as e:
            print(f"Ошибка остановки потока {device_name}: {e}")
        # Очистка очереди
        while not self.audio_queues[device_name].empty():
            try:
                self.audio_queues[device_name].get_nowait()
            except:
                break

    def set_gain(self, device_name, gain):
        """Установка коэффициента усиления для источника"""
        if device_name in self.streams:
            self.gains[device_name] = max(0.0, min(2.0, gain))  # Ограничение 0-200%
            print(f"Громкость {device_name} установлена: {gain:.2f}x")
            return True
        return False

    def start_output(self, device_name=None, device_id=None):
        """Запуск выходного потока для воспроизведения микса"""
        try:
            if device_id is None and device_name:
                devices = sd.query_devices()
                for i, dev in enumerate(devices):
                    if device_name.lower() in dev['name'].lower() and dev['max_output_channels'] > 0:
                        device_id = i
                        device_name = dev['name']
                        break
            
            if device_id is None:
                device_id = sd.default.device[1]
                device_info = sd.query_devices(device_id)
                device_name = device_info['name']
            
            def output_callback(outdata, frames, time, status):
                if status:
                    print(f"Статус вывода: {status}")
                
                # Инициализация буфера микса
                mix = np.zeros((frames, self.channels), dtype='float32')
                active_sources = 0
                
                # Смешивание всех активных источников
                with self.stream_lock:
                    for source_name, q in list(self.audio_queues.items()):
                        try:
                            # Получаем фрейм из очереди источника
                            audio_chunk = q.get_nowait()
                            
                            # Обрезаем или дополняем до нужного размера
                            if len(audio_chunk) < frames:
                                # Дополняем нулями
                                padded = np.zeros((frames, self.channels), dtype='float32')
                                padded[:len(audio_chunk)] = audio_chunk
                                mix += padded
                            else:
                                mix += audio_chunk[:frames]
                            
                            active_sources += 1
                            
                            # Возвращаем остаток в очередь (если есть)
                            if len(audio_chunk) > frames:
                                remaining = audio_chunk[frames:]
                                q.put_nowait(remaining)
                                
                        except queue.Empty:
                            # Источник временно не прислал данные - пропускаем
                            pass
                        except Exception as e:
                            print(f"Ошибка обработки источника {source_name}: {e}")
                
                # Нормализация для предотвращения клиппинга
                if active_sources > 0:
                    mix /= active_sources
                
                # Ограничение амплитуды [-1.0, 1.0]
                mix = np.clip(mix, -1.0, 1.0)
                
                # Запись в выходной буфер
                outdata[:] = mix
            
            self.output_stream = sd.OutputStream(
                device=device_id,
                channels=self.channels,
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                callback=output_callback,
                dtype='float32'
            )
            
            self.output_stream.start()
            print(f"🔈 Выходной поток запущен: {device_name} (ID: {device_id})")
            return True
            
        except Exception as e:
            print(f"Ошибка запуска выходного потока: {e}")
            return False

    def start(self):
        """Запуск микшера"""
        self.running = True
        self.start_device_monitoring()
        print("✅ Микшер запущен")
    
    def stop(self):
        """Полная остановка микшера"""
        self.running = False
        
        # Остановка всех потоков
        with self.stream_lock:
            for device_name in list(self.streams.keys()):
                self._stop_stream(device_name)
            self.streams.clear()
        
        # Остановка выходного потока
        if self.output_stream:
            try:
                self