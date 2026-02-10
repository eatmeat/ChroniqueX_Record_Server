import sounddevice as sd
import numpy as np
import wave
import sys
import select

def list_audio_devices():
    """List available audio input devices."""
    print("Available recording devices:")
    devices = sd.query_devices()
    input_devices = [i for i in range(len(devices)) if devices[i]['max_input_channels'] > 0]
    for idx in input_devices:
        print(f"{idx}: {devices[idx]['name']}")
    return input_devices

def record_system_audio(filename, device, sample_rate=44100):
    """Record audio from the specified system audio device."""
    device_info = sd.query_devices(device)
    channels = min(2, device_info['max_input_channels'])  # Use mono if only one channel is available
    print(f"Recording system audio with {channels} channel(s)... Press Enter to stop.")
    
    frames = []
    try:
        with sd.InputStream(samplerate=sample_rate, device=device, channels=channels, dtype='int16') as stream:
            while True:
                # Read smaller chunks for smoother recording
                audio_data, _ = stream.read(int(sample_rate / 4))  # Adjust chunk size for smoother audio
                if channels == 1:
                    audio_data = np.tile(audio_data, (1, 2))  # Duplicate to 2 channels for mono
                
                frames.append(audio_data)

                # Stop if Enter key is pressed
                if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                    print("Stopping recording...")
                    break
    except KeyboardInterrupt:
        print("Recording interrupted.")
    finally:
        # Save all recorded frames to a WAV file
        if frames:
            with wave.open(filename, 'wb') as wf:
                wf.setnchannels(2)  # Stereo output
                wf.setsampwidth(2)  # 2 bytes (16 bits)
                wf.setframerate(sample_rate)
                wf.writeframes(np.concatenate(frames).tobytes())
            print(f"Recording saved to {filename}")
        else:
            print("No audio recorded.")

if __name__ == "__main__":
    # Set the output filename
    filename = "system_audio_output.wav"
    
    # List devices and choose the virtual audio device as input
    input_devices = list_audio_devices()
    device = int(input("Select the virtual audio device ID to record from: "))

    # Check if the selected device is valid
    if device not in input_devices:
        print("Invalid device ID selected.")
        sys.exit(1)

    # Record system audio from the selected virtual audio device
    record_system_audio(filename, device)