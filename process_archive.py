import os
import json
import re
from datetime import datetime, timedelta
from pydub import AudioSegment

def get_application_path():
    """Get the path where the application is located."""
    return os.path.dirname(os.path.abspath(__file__))

def process_existing_recordings():
    """
    Iterates through the 'rec' directory and creates JSON metadata files
    for existing audio files that don't have one.
    """
    app_path = get_application_path()
    rec_dir = os.path.join(app_path, 'rec')

    if not os.path.exists(rec_dir):
        print(f"Directory '{rec_dir}' not found. Nothing to process.")
        return

    print(f"Scanning for recordings in '{rec_dir}'...")

    # Walk through all directories and files
    for root, _, files in os.walk(rec_dir):
        for filename in files:
            if not (filename.lower().endswith('.wav') or filename.lower().endswith('.mp3')):
                continue

            base_name, _ = os.path.splitext(filename)
            audio_path = os.path.join(root, filename)
            json_path = os.path.join(root, base_name + '.json')

            if os.path.exists(json_path):
                continue  # Skip if JSON already exists

            print(f"Processing: {audio_path}")

            try:
                # 1. Get duration from audio file
                audio = AudioSegment.from_file(audio_path)
                duration_seconds = len(audio) / 1000.0

                # 2. Parse start time from directory and filename
                date_str = os.path.basename(root)  # e.g., '2023-10-27'
                time_match = re.match(r'(\d{2})\.(\d{2})', filename) # e.g., '14.30'
                
                if not time_match:
                    print(f"  - Could not parse time from filename: {filename}. Skipping.")
                    continue

                hour, minute = map(int, time_match.groups())
                start_time = datetime.strptime(date_str, '%Y-%m-%d').replace(hour=hour, minute=minute)

                # 3. Set title to filename
                title = base_name

                # 4. Create metadata dictionary
                metadata = {
                    "startTime": start_time.isoformat(),
                    "duration": duration_seconds,
                    "title": title
                }

                # 5. Write JSON file
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=4, ensure_ascii=False)
                print(f"  - Created metadata file: {json_path}")

            except Exception as e:
                print(f"  - Error processing file {filename}: {e}")

if __name__ == '__main__':
    process_existing_recordings()
    print("\nProcessing complete.")