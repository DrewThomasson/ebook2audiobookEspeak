print("starting...")

import os
import shutil
import subprocess
import re
from pydub import AudioSegment
import tempfile
from tqdm import tqdm
import gradio as gr
import nltk
import ebooklib
import bs4
from ebooklib import epub
from bs4 import BeautifulSoup
from gradio import Progress
import sys
from nltk.tokenize import sent_tokenize
import csv

# Ensure necessary models are downloaded
# nltk.download('punkt')

def is_folder_empty(folder_path):
    if os.path.exists(folder_path) and os.path.isdir(folder_path):
        return not os.listdir(folder_path)
    else:
        print(f"The path {folder_path} is not a valid folder.")
        return None

def remove_folder_with_contents(folder_path):
    try:
        shutil.rmtree(folder_path)
        print(f"Successfully removed {folder_path} and all of its contents.")
    except Exception as e:
        print(f"Error removing {folder_path}: {e}")

def wipe_folder(folder_path):
    if not os.path.exists(folder_path):
        print(f"The folder {folder_path} does not exist.")
        return
    for item in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item)
        if os.path.isfile(item_path):
            os.remove(item_path)
        elif os.path.isdir(item_path):
            shutil.rmtree(item_path)
    
    print(f"All contents wiped from {folder_path}.")

def create_m4b_from_chapters(input_dir, ebook_file, output_dir):
    def sort_key(chapter_file):
        numbers = re.findall(r'\d+', chapter_file)
        return int(numbers[0]) if numbers else 0

    def extract_metadata_and_cover(ebook_path):
        try:
            cover_path = ebook_path.rsplit('.', 1)[0] + '.jpg'
            subprocess.run(['ebook-meta', ebook_path, '--get-cover', cover_path], check=True)
            if (os.path.exists(cover_path)):
                return cover_path
        except Exception as e:
            print(f"Error extracting eBook metadata or cover: {e}")
        return None

    def combine_wav_files(chapter_files, output_path):
        combined_audio = AudioSegment.empty()

        for chapter_file in chapter_files:
            audio_segment = AudioSegment.from_wav(chapter_file)
            combined_audio += audio_segment
        combined_audio.export(output_path, format='wav')
        print(f"Combined audio saved to {output_path}")

    def generate_ffmpeg_metadata(chapter_files, metadata_file):
        with open(metadata_file, 'w') as file:
            file.write(';FFMETADATA1\n')
            start_time = 0
            for index, chapter_file in enumerate(chapter_files):
                duration_ms = len(AudioSegment.from_wav(chapter_file))
                file.write(f'[CHAPTER]\nTIMEBASE=1/1000\nSTART={start_time}\n')
                file.write(f'END={start_time + duration_ms}\ntitle=Chapter {index + 1}\n')
                start_time += duration_ms

    def create_m4b(combined_wav, metadata_file, cover_image, output_m4b):
        os.makedirs(os.path.dirname(output_m4b), exist_ok=True)
        
        ffmpeg_cmd = ['ffmpeg', '-i', combined_wav, '-i', metadata_file]
        if cover_image:
            ffmpeg_cmd += ['-i', cover_image, '-map', '0:a', '-map', '2:v']
            ffmpeg_cmd += ['-c:v', 'png', '-disposition:v', 'attached_pic']
        else:
            ffmpeg_cmd += ['-map', '0:a']
        
        ffmpeg_cmd += ['-map_metadata', '1', '-c:a', 'aac', '-b:a', '192k']
        ffmpeg_cmd += [output_m4b]

        try:
            subprocess.run(ffmpeg_cmd, check=True)
        except subprocess.CalledProcessError as e:
            print("Metadata adding didn't work trying with only the cover art and no Metadata.")
            ffmpeg_cmd = ""
            ffmpeg_cmd = ['ffmpeg', '-i', combined_wav]
            if cover_image:
                print("Found Cover art")
                ffmpeg_cmd += ['-i', cover_image, '-map', '0:a', '-map', '2:v']
                ffmpeg_cmd += ['-c:v', 'png', '-disposition:v', 'attached_pic']
            else:
                ffmpeg_cmd += ['-map', '0:a']

            ffmpeg_cmd += ['-c:a', 'aac', '-b:a', '192k']
            try:
                subprocess.run(ffmpeg_cmd, check=True)
            except subprocess.CalledProcessError as e:
                print("Cover art adding didn't work, trying without any metadata or cover art.")
                ffmpeg_cmd = ""
                ffmpeg_cmd = ['ffmpeg', '-i', combined_wav]
                ffmpeg_cmd += ['-map', '0:a']
                ffmpeg_cmd += ['-c:a', 'aac', '-b:a', '192k']
                try:
                    subprocess.run(ffmpeg_cmd, check=True)
                except subprocess.CalledProcessError:
                    print("Failed to create M4B file. Trying to at least save the audio.")
                try:
                    ffmpeg_cmd = ['ffmpeg', '-i', combined_wav, '-c:a', 'aac', '-b:a', '192k', output_m4b]
                    subprocess.run(ffmpeg_cmd, check=True)
                except subprocess.CalledProcessError as e:
                    print(f"Final attempt failed: {e}")
        print(f"M4B file created successfully at {output_m4b}")


    chapter_files = sorted([os.path.join(input_dir, f) for f in os.listdir(input_dir) if f.endswith('.wav')], key=sort_key)
    temp_dir = tempfile.gettempdir()
    temp_combined_wav = os.path.join(temp_dir, 'combined.wav')
    metadata_file = os.path.join(temp_dir, 'metadata.txt')
    cover_image = extract_metadata_and_cover(ebook_file)
    output_m4b = os.path.join(output_dir, os.path.splitext(os.path.basename(ebook_file))[0] + '.m4b')

    combine_wav_files(chapter_files, temp_combined_wav)
    generate_ffmpeg_metadata(chapter_files, metadata_file)
    create_m4b(temp_combined_wav, metadata_file, cover_image, output_m4b)

    if os.path.exists(temp_combined_wav):
        os.remove(temp_combined_wav)
    if os.path.exists(metadata_file):
        os.remove(metadata_file)
    if cover_image and os.path.exists(cover_image):
        os.remove(cover_image)

def create_chapter_labeled_book(ebook_file_path):
    def ensure_directory(directory_path):
        if not os.path.exists(directory_path):
            os.makedirs(directory_path)
            print(f"Created directory: {directory_path}")

    ensure_directory(os.path.join(".", 'Working_files', 'Book'))

    def convert_to_epub(input_path, output_path):
        try:
            subprocess.run(['ebook-convert', input_path, output_path], check=True)
        except subprocess.CalledProcessError as e:
            print(f"An error occurred while converting the eBook: {e}")
            return False
        return True

    def save_chapters_as_text(epub_path):
        directory = os.path.join(".", "Working_files", "temp_ebook")
        ensure_directory(directory)

        book = epub.read_epub(epub_path)

        previous_filename = ''
        chapter_counter = 0

        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                soup = BeautifulSoup(item.get_content(), 'html.parser')
                text = soup.get_text()

                if text.strip():
                    if len(text) < 2300 and previous_filename:
                        with open(previous_filename, 'a', encoding='utf-8') as file:
                            file.write('\n' + text)
                    else:
                        previous_filename = os.path.join(directory, f"chapter_{chapter_counter}.txt")
                        chapter_counter += 1
                        with open(previous_filename, 'w', encoding='utf-8') as file:
                            file.write(text)
                            print(f"Saved chapter: {previous_filename}")

    input_ebook = ebook_file_path
    output_epub = os.path.join(".", "Working_files", "temp.epub")

    if os.path.exists(output_epub):
        os.remove(output_epub)
        print(f"File {output_epub} has been removed.")
    else:
        print(f"The file {output_epub} does not exist.")

    if convert_to_epub(input_ebook, output_epub):
        save_chapters_as_text(output_epub)

    # nltk.download('punkt')

    def process_chapter_files(folder_path, output_csv):
        with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Text', 'Start Location', 'End Location', 'Is Quote', 'Speaker', 'Chapter'])

            chapter_files = sorted(os.listdir(folder_path), key=lambda x: int(x.split('_')[1].split('.')[0]))
            for filename in chapter_files:
                if filename.startswith('chapter_') and filename.endswith('.txt'):
                    chapter_number = int(filename.split('_')[1].split('.')[0])
                    file_path = os.path.join(folder_path, filename)

                    try:
                        with open(file_path, 'r', encoding='utf-8') as file:
                            text = file.read()
                            if text:
                                text = "NEWCHAPTERABC" + text
                            sentences = nltk.tokenize.sent_tokenize(text)
                            for sentence in sentences:
                                start_location = text.find(sentence)
                                end_location = start_location + len(sentence)
                                writer.writerow([sentence, start_location, end_location, 'True', 'Narrator', chapter_number])
                    except Exception as e:
                        print(f"Error processing file {filename}: {e}")

    folder_path = os.path.join(".", "Working_files", "temp_ebook")
    output_csv = os.path.join(".", "Working_files", "Book", "Other_book.csv")

    process_chapter_files(folder_path, output_csv)

    def sort_key(filename):
        match = re.search(r'chapter_(\d+)\.txt', filename)
        return int(match.group(1)) if match else 0

    def combine_chapters(input_folder, output_file):
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        files = [f for f in os.listdir(input_folder) if f.endswith('.txt')]
        sorted_files = sorted(files, key=sort_key)

        with open(output_file, 'w', encoding='utf-8') as outfile:
            for i, filename in enumerate(sorted_files):
                with open(os.path.join(input_folder, filename), 'r', encoding='utf-8') as infile:
                    outfile.write(infile.read())
                    if i < len(sorted_files) - 1:
                        outfile.write("\nNEWCHAPTERABC\n")

    input_folder = os.path.join(".", 'Working_files', 'temp_ebook')
    output_file = os.path.join(".", 'Working_files', 'Book', 'Chapter_Book.txt')

    combine_chapters(input_folder, output_file)

    ensure_directory(os.path.join(".", "Working_files", "Book"))

def sanitize_sentence(sentence):
    # Replace or remove problematic characters that could cause issues in any language
    sanitized = sentence.replace('--', ' ').replace('"', '').replace("'", "")
    return sanitized

def convert_chapters_to_audio_espeak(chapters_dir, output_audio_dir, speed="170", pitch="50", voice="en"):
    if not os.path.exists(output_audio_dir):
        os.makedirs(output_audio_dir)

    for chapter_file in sorted(os.listdir(chapters_dir)):
        if chapter_file.endswith('.txt'):
            match = re.search(r"chapter_(\d+).txt", chapter_file)
            if match:
                chapter_num = int(match.group(1))
            else:
                print(f"Skipping file {chapter_file} as it does not match the expected format.")
                continue

            chapter_path = os.path.join(chapters_dir, chapter_file)
            output_file_name = f"audio_chapter_{chapter_num}.wav"
            output_file_path = os.path.join(output_audio_dir, output_file_name)

            with open(chapter_path, 'r', encoding='utf-8') as file:
                chapter_text = file.read()
                sentences = nltk.tokenize.sent_tokenize(chapter_text)
                combined_audio = AudioSegment.empty()

                for sentence in tqdm(sentences, desc=f"Chapter {chapter_num}"):
                    success = False
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_wav:
                        try:
                            subprocess.run(["espeak-ng", "-v", voice, "-w", temp_wav.name, f"-s{speed}", f"-p{pitch}", sentence], check=True)
                            success = True
                        except subprocess.CalledProcessError:
                            # If it fails, try with the sanitized sentence
                            sanitized_sentence = sanitize_sentence(sentence)
                            try:
                                subprocess.run(["espeak-ng", "-v", voice, "-w", temp_wav.name, f"-s{speed}", f"-p{pitch}", sanitized_sentence], check=True)
                                success = True
                                print(f"Sanitized sentence used for: {sentence}")
                            except subprocess.CalledProcessError as e:
                                print(f"Failed to convert sentence to audio: {sentence}")
                                print(f"Error: {e}")

                        if success and os.path.getsize(temp_wav.name) > 0:
                            combined_audio += AudioSegment.from_wav(temp_wav.name)
                        else:
                            print(f"Skipping sentence due to failure or empty WAV: {sentence}")
                        os.remove(temp_wav.name)

                combined_audio.export(output_file_path, format='wav')
                print(f"Converted chapter {chapter_num} to audio.")


def convert_ebook_to_audio(ebook_file, speed, pitch, voice, progress=gr.Progress()):
    ebook_file_path = ebook_file.name
    working_files = os.path.join(".", "Working_files", "temp_ebook")
    full_folder_working_files = os.path.join(".", "Working_files")
    chapters_directory = os.path.join(".", "Working_files", "temp_ebook")
    output_audio_directory = os.path.join(".", 'Chapter_wav_files')
    remove_folder_with_contents(full_folder_working_files)
    remove_folder_with_contents(output_audio_directory)

    try:
        progress(0.1, desc="Creating chapter-labeled book")
    except Exception as e:
        print(f"Error updating progress: {e}")

    create_chapter_labeled_book(ebook_file_path)
    audiobook_output_path = os.path.join(".", "Audiobooks")

    try:
        progress(0.3, desc="Converting chapters to audio")
    except Exception as e:
        print(f"Error updating progress: {e}")

    convert_chapters_to_audio_espeak(chapters_directory, output_audio_directory, speed, pitch, voice.split()[0])

    try:
        progress(0.9, desc="Creating M4B from chapters")
    except Exception as e:
        print(f"Error updating progress: {e}")

    create_m4b_from_chapters(output_audio_directory, ebook_file_path, audiobook_output_path)

    m4b_filename = os.path.splitext(os.path.basename(ebook_file_path))[0] + '.m4b'
    m4b_filepath = os.path.join(audiobook_output_path, m4b_filename)

    try:
        progress(1.0, desc="Conversion complete")
    except Exception as e:
        print(f"Error updating progress: {e}")
    print(f"Audiobook created at {m4b_filepath}")
    return f"Audiobook created at {m4b_filepath}", m4b_filepath

def list_audiobook_files(audiobook_folder):
    files = []
    for filename in os.listdir(audiobook_folder):
        if filename.endswith('.m4b'):
            files.append(os.path.join(audiobook_folder, filename))
    return files

def download_audiobooks():
    audiobook_output_path = os.path.join(".", "Audiobooks")
    return list_audiobook_files(audiobook_output_path)

def get_available_voices():
    result = subprocess.run(['espeak-ng', '--voices'], stdout=subprocess.PIPE, text=True)
    lines = result.stdout.splitlines()[1:]  # Skip the header line
    voices = []
    for line in lines:
        parts = line.split()
        if len(parts) > 1:
            voice_name = parts[1]
            description = ' '.join(parts[2:])
            voices.append((voice_name, description))
    return voices

theme = gr.themes.Soft(
    primary_hue="blue",
    secondary_hue="blue",
    neutral_hue="blue",
    text_size=gr.themes.sizes.text_md,
)

# Gradio UI setup
with gr.Blocks(theme=theme) as demo:
    gr.Markdown(
    """
    # eBook to Audiobook Converter
    
    Convert your eBooks into audiobooks using eSpeak-NG.
    """
    )

    with gr.Row():
        with gr.Column(scale=3):
            ebook_file = gr.File(label="eBook File")
            speed = gr.Slider(minimum=80, maximum=450, value=170, step=1, label="Speed")
            pitch = gr.Slider(minimum=0, maximum=99, value=50, step=1, label="Pitch")
            voices = get_available_voices()
            voice_choices = [f"{voice} ({desc})" for voice, desc in voices]
            voice_dropdown = gr.Dropdown(choices=voice_choices, label="Select Voice", value=voice_choices[0])

    convert_btn = gr.Button("Convert to Audiobook", variant="primary")
    output = gr.Textbox(label="Conversion Status")
    audio_player = gr.Audio(label="Audiobook Player", type="filepath")
    download_btn = gr.Button("Download Audiobook Files")
    download_files = gr.File(label="Download Files", interactive=False)

    convert_btn.click(
        convert_ebook_to_audio,
        inputs=[ebook_file, speed, pitch, voice_dropdown],
        outputs=[output, audio_player]
    )

    download_btn.click(
        download_audiobooks,
        outputs=[download_files]
    )

demo.launch(server_name='0.0.0.0', server_port=7860, share=True)

