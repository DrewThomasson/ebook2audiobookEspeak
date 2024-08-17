# 📚 eBook to Audiobook Converter with eSpeak-ng

Convert eBooks to audiobooks with chapters and metadata using Calibre and eSpeak-ng. Supports multiple languages and customizable voice settings!

## 🌟 Features

- 📖 Converts eBooks to text format using Calibre.
- 📚 Splits eBooks into chapters for organized audio.
- 🎙️ High-quality text-to-speech using eSpeak-ng.
- 🌍 Supports multiple languages and accents.
- 🎛️ Customizable voice, speed, and pitch settings.
- 🖥️ User-friendly Gradio web interface.
- ⚡ Designed to run lighting fast on only 100 MB ram.

## 🛠️ Requirements

- Python 3.x
- `gradio` Python package
- Calibre (for eBook conversion)
- FFmpeg (for audiobook creation)
- eSpeak-ng (for text-to-speech)

## 🖥️ Gradio Web Gui
<img width="1405" alt="Screenshot 2024-08-17 at 4 42 16 PM" src="https://github.com/user-attachments/assets/ee8f29be-b696-4d66-81de-00c85f1f5c66">

<img width="1407" alt="Screenshot 2024-08-17 at 4 42 22 PM" src="https://github.com/user-attachments/assets/7a060762-d4fc-41cc-96b2-071f33e50f0c">


### 🔧 Installation Instructions

1. **Install Python 3.x** from [Python.org](https://www.python.org/downloads/).

2. **Install Calibre**:
   - **Ubuntu**: `sudo apt-get install -y calibre`
   - **macOS**: `brew install calibre`
   - **Windows** (Admin Powershell): `choco install calibre`

3. **Install FFmpeg**:
   - **Ubuntu**: `sudo apt-get install -y ffmpeg`
   - **macOS**: `brew install ffmpeg`
   - **Windows** (Admin Powershell): `choco install ffmpeg`

4. **Install eSpeak-ng**:
   - **Ubuntu**: `sudo apt-get install -y espeak-ng`
   - **macOS**: `brew install espeak-ng`
   - **Windows** (Admin Powershell): `choco install espeak-ng`

5. **Install Python packages**:
   ```bash
   pip install gradio bs4 pydub nltk beautifulsoup4 ebooklib tqdm
   ```

   **For non-Latin languages**:
   ```bash
   python -m nltk.downloader punkt
   ```

## 🌐 Supported Languages and Voices

eSpeak-ng provides a variety of voices for different languages and accents:

- **Afrikaans**: `af`
- **Amharic**: `am`
- **Arabic**: `ar`
- **Bengali**: `bn`
- **Bosnian**: `bs`
- **Catalan**: `ca`
- **Chinese (Mandarin)**: `cmn`
- **Croatian**: `hr`
- **Czech**: `cs`
- **Danish**: `da`
- **Dutch**: `nl`
- **English (Great Britain)**: `en-gb`
- **English (America)**: `en-us`
- **Esperanto**: `eo`
- **Finnish**: `fi`
- **French**: `fr`
- **German**: `de`
- **Greek**: `el`
- **Hindi**: `hi`
- **Hungarian**: `hu`
- **Icelandic**: `is`
- **Italian**: `it`
- **Japanese**: `ja`
- **Korean**: `ko`
- **Latvian**: `lv`
- **Macedonian**: `mk`
- **Norwegian (Bokmål)**: `nb`
- **Polish**: `pl`
- **Portuguese (Brazil)**: `pt-br`
- **Portuguese (Portugal)**: `pt`
- **Russian**: `ru`
- **Spanish (Spain)**: `es`
- **Swedish**: `sv`
- **Turkish**: `tr`
- **Vietnamese**: `vi`
- **Welsh**: `cy`

Specify the language code when running the script.

## 🚀 Usage

### 🖥️ Gradio Web Interface

1. **Run the Script**:
   ```bash
   python gradio_launch.py
   ```

2. **Open the Web App**: Click the URL provided in the terminal to access the web app and convert eBooks.

## 🐳 Using Docker

You can also use Docker to run the eBook to Audiobook converter. This method ensures consistency across different environments and simplifies setup.

### 🚀 Running the Docker Container

To run the Docker container and start the Gradio interface, use the following command:

```bash
docker run -it --rm -p 7860:7860 athomasson2/ebook2audiobookespeak:latest
```

This command will start the Gradio interface on port 7860. (localhost:7860)

For more details, visit the [Docker Hub Page](https://hub.docker.com/repository/docker/athomasson2/ebook2audiobookespeak/general).

## 📚 Supported eBook Formats

- `.epub`, `.pdf`, `.mobi`, `.txt`, `.html`, `.rtf`, `.chm`, `.lit`, `.pdb`, `.fb2`, `.odt`, `.cbr`, `.cbz`, `.prc`, `.lrf`, `.pml`, `.snb`, `.cbc`, `.rb`, `.tcr`
- **Best results**: `.epub` or `.mobi` for automatic chapter detection

## 📂 Output

- Creates an `.m4b` file with metadata and chapters.

## 🙏 Special Thanks

- **eSpeak-ng**: [eSpeak-ng GitHub](https://github.com/espeak-ng/espeak-ng)
- **Calibre**: [Calibre Website](https://calibre-ebook.com)
- **Inspiration from Smiling friends Spamtopia episode Season 2 Episode 7**
  ![maxresdefault](https://github.com/user-attachments/assets/a6c34117-36d6-4b20-b8c5-b58066a867fe)

