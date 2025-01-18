# Use an official Python 3.10 image
FROM python:3.10-slim-buster

# Set non-interactive installation to avoid timezone and other prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install necessary packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    calibre \
    espeak \
    espeak-ng \
    ffmpeg \
    wget \
    tk \
    mecab \
    libmecab-dev \
    mecab-ipadic-utf8 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /ebook2audiobookXTTS

# Clone the repository and install dependencies
RUN git clone https://github.com/DrewThomasson/ebook2audiobookEspeak.git .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install bs4 pydub nltk beautifulsoup4 ebooklib tqdm gradio

# Download the punkt package for nltk
RUN python -m nltk.downloader punkt

# Verify the script exists and has correct permissions
RUN ls -la /ebook2audiobookXTTS/ && \
    if [ ! -f /ebook2audiobookXTTS/gradio_launch.py ]; then echo "Script not found."; exit 1; fi

# Set the command to run your application
CMD ["python", "/ebook2audiobookXTTS/gradio_launch.py"]
