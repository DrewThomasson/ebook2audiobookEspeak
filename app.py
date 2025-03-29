import gradio as gr
import subprocess
import os
import tempfile
import shutil
import re
import logging
from pathlib import Path
from PIL import Image # For checking image validity
try:
    import mutagen
    from mutagen.mp3 import MP3, EasyMP3
    from mutagen.oggvorbis import OggVorbis
    from mutagen.flac import FLAC
    from mutagen.mp4 import MP4, MP4Cover
    from mutagen.id3 import ID3, APIC, error as ID3Error
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False
    logging.warning("Mutagen library not found. Cover art embedding will be disabled.")
    logging.warning("Install it using: pip install mutagen")


# --- Configuration & Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Helper Functions ---

def check_command(command):
    """Checks if a command exists in the system's PATH."""
    try:
        # Use a more reliable check for command existence, sometimes --version fails
        # On Windows, 'where' command; on Unix-like, 'command -v' or 'which'
        if os.name == 'nt':
            subprocess.run(['where', command], check=True, capture_output=True)
        else:
            # 'command -v' is generally preferred over 'which'
            subprocess.run(['command', '-v', command], check=True, capture_output=True)
        logging.info(f"Command '{command}' found.")
        return True
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        logging.error(f"Command '{command}' not found or check failed. Please ensure it's installed and in your PATH.")
        # Log the specific error if needed: logging.error(f"Error details: {e}")
        return False
    except Exception as e: # Catch unexpected errors during check
        logging.error(f"Unexpected error checking for command '{command}': {e}")
        return False


def get_espeak_voices():
    """Gets available espeak-ng voices and their languages."""
    voices = {}
    try:
        # Use a robust way to list voices that includes language info
        result = subprocess.run(['espeak-ng', '--voices'], capture_output=True, text=True, check=True, encoding='utf-8', errors='ignore')
        # Example line format: P L V Language        Code Age/Gender VoiceName          File          Other Langs
        #                      2 y en-US     M american-english-us Mbrola/us1       (en 10)
        #                      1   af        M afrikaans            Afrikaans
        pattern = re.compile(r"^\s*\d+\s+[yn-]\s+([\w-]+)\s+[MF-]\s+(.+?)\s+([\w/ -]+?)(?:\s+\(([\w\s]+)\))?\s*$")
        for line in result.stdout.splitlines()[1:]: # Skip header
             match = pattern.match(line)
             if match:
                 code, lang_name, _voice_name, _other_langs = match.groups()
                 display_name = f"{lang_name.strip()} ({code})"
                 # Avoid duplicates if multiple voice names exist for the same code
                 if display_name not in voices:
                     voices[display_name] = code
             else:
                 # Try simpler parsing for lines without extra details
                 parts = line.split()
                 if len(parts) >= 4 and parts[0].isdigit():
                     code = parts[1]
                     lang_name = parts[3]
                     display_name = f"{lang_name.strip()} ({code})"
                     if display_name not in voices:
                         voices[display_name] = code

        if not voices:
             logging.warning("Could not parse any voices from 'espeak-ng --voices'. Using fallback list.")
             # Add common fallbacks if parsing fails
             voices = {"English (en)": "en", "Spanish (es)": "es", "French (fr)": "fr", "German (de)": "de"}

        # Sort voices alphabetically by display name
        sorted_voices = dict(sorted(voices.items()))
        return sorted_voices

    except (FileNotFoundError, subprocess.CalledProcessError, Exception) as e:
        logging.error(f"Error getting espeak-ng voices: {e}")
        # Provide a basic fallback list if the command fails
        return {"English (en)": "en", "Spanish (es)": "es", "French (fr)": "fr", "German (de)": "de"}

# --- Main Conversion Logic ---

def convert_ebook_to_audio(ebook_file, language_display, output_format, embed_cover, progress=gr.Progress(track_tqdm=True)):
    """
    Converts an ebook file to an audiobook using Calibre and espeak-ng.
    """
    if not ebook_file:
        return None, None, "Error: No ebook file provided.", None

    # Check required commands based on selection
    calibre_convert_ok = check_command("ebook-convert")
    calibre_meta_ok = True if not embed_cover else check_command("ebook-meta") # Only check if needed
    espeak_ok = check_command("espeak-ng")
    lame_ok = True if output_format != 'mp3' else check_command("lame")
    oggenc_ok = True if output_format != 'ogg' else check_command("oggenc")

    missing = []
    if not calibre_convert_ok: missing.append("Calibre ('ebook-convert')")
    if not calibre_meta_ok and embed_cover: missing.append("Calibre ('ebook-meta' for cover art)")
    if not espeak_ok: missing.append("espeak-ng")
    if not lame_ok and output_format == 'mp3': missing.append("LAME (for MP3)")
    if not oggenc_ok and output_format == 'ogg': missing.append("oggenc (for OGG)")

    if missing:
         error_msg = f"Error: Missing required command(s): {', '.join(missing)}. Please install them and ensure they are in your system PATH."
         logging.error(error_msg)
         # Use Markdown for better formatting in Gradio Textbox
         return None, None, f"**Error:** Missing required command(s):\n- {', '.join(missing)}\n\nPlease install them and ensure they are in your system PATH.", None


    temp_dir = tempfile.mkdtemp(prefix="ebook_audio_")
    logging.info(f"Created temporary directory: {temp_dir}")
    status_updates = ["Conversion started..."]
    cover_image_path_final = None
    audio_output_path_final = None

    try:
        input_ebook_path = ebook_file.name # Gradio provides a temp path for the upload
        base_filename = Path(input_ebook_path).stem
        txt_output_path = os.path.join(temp_dir, f"{base_filename}.txt")
        cover_output_path_temp = os.path.join(temp_dir, "cover.jpg") # Assume jpg initially
        audio_output_path = os.path.join(temp_dir, f"{base_filename}.{output_format}")

        # --- Step 1: Extract Cover Art (Optional) ---
        cover_extracted = False
        if embed_cover and calibre_meta_ok: # Already checked if ebook-meta exists
            progress(0.1, desc="Extracting cover art (optional)")
            status_updates.append("Attempting to extract cover art...")
            try:
                cmd_meta = ['ebook-meta', input_ebook_path, '--get-cover', cover_output_path_temp]
                logging.info(f"Running cover extraction: {' '.join(cmd_meta)}")
                result_meta = subprocess.run(cmd_meta, check=True, capture_output=True, text=True, errors='ignore')
                if os.path.exists(cover_output_path_temp) and os.path.getsize(cover_output_path_temp) > 0:
                    # Validate if it's a real image file Pillow can open
                    try:
                        img = Image.open(cover_output_path_temp)
                        img.verify() # Verify CRC markers
                        img.close() # Need to close after verify
                        # Reopen to check format and potentially save in a consistent format if needed
                        img = Image.open(cover_output_path_temp)
                        fmt = img.format.lower() if img.format else 'unknown'
                        img.close()

                        if fmt not in ['jpeg', 'png']:
                             logging.warning(f"Extracted cover is not JPEG or PNG ({fmt}), attempting conversion.")
                             # Try converting to JPG for broader compatibility with mutagen
                             new_cover_path = os.path.join(temp_dir, "cover_converted.jpg")
                             try:
                                 img = Image.open(cover_output_path_temp)
                                 img.convert('RGB').save(new_cover_path, "JPEG")
                                 img.close()
                                 # Check if conversion worked
                                 if os.path.exists(new_cover_path) and os.path.getsize(new_cover_path) > 0:
                                     cover_output_path_temp = new_cover_path # Use the converted path
                                     cover_extracted = True
                                     cover_image_path_final = cover_output_path_temp # Update final path for display
                                     status_updates.append("✅ Cover art extracted and converted to JPG.")
                                     logging.info(f"Cover art extracted and converted to JPG: {cover_image_path_final}")

                                 else:
                                     logging.error("Failed to convert cover art to JPG.")
                                     status_updates.append("⚠️ Could not convert extracted cover art to JPG. Will skip embedding.")
                                     if os.path.exists(cover_output_path_temp): os.remove(cover_output_path_temp) # Clean up original if unusable

                             except Exception as convert_err:
                                 logging.error(f"Error converting cover image: {convert_err}")
                                 status_updates.append(f"⚠️ Error converting cover image: {convert_err}. Will skip embedding.")
                                 if os.path.exists(cover_output_path_temp): os.remove(cover_output_path_temp) # Clean up original

                        else:
                            cover_extracted = True
                            cover_image_path_final = cover_output_path_temp # Use original path
                            status_updates.append("✅ Cover art extracted successfully.")
                            logging.info(f"Cover art extracted to {cover_image_path_final} (Format: {fmt})")

                    except (IOError, SyntaxError, Image.UnidentifiedImageError) as img_err:
                        logging.warning(f"Extracted file is not a valid image or couldn't be processed: {img_err}")
                        status_updates.append("⚠️ Extracted 'cover' file is not a valid image. Will skip embedding.")
                        if os.path.exists(cover_output_path_temp): os.remove(cover_output_path_temp) # Clean up invalid file
                else:
                    status_updates.append("ℹ️ No cover art found in the ebook metadata.")
                    logging.info("ebook-meta ran but did not produce a cover file or it was empty.")

            # No FileNotFoundError needed here as calibre_meta_ok check already happened
            except subprocess.CalledProcessError as e:
                stderr_decoded = e.stderr.decode(errors='ignore') if e.stderr else "No stderr"
                status_updates.append(f"⚠️ Failed to extract cover art. Error: {stderr_decoded}")
                logging.warning(f"ebook-meta failed: {stderr_decoded}")
            except Exception as e:
                 status_updates.append(f"⚠️ An unexpected error occurred during cover extraction: {e}")
                 logging.error(f"Unexpected error during cover extraction: {e}", exc_info=True)
        elif embed_cover and not calibre_meta_ok:
             status_updates.append("ℹ️ Cover art embedding requested, but 'ebook-meta' not found.")

        # --- Step 2: Convert Ebook to TXT ---
        progress(0.3, desc="Converting ebook to TXT")
        status_updates.append("Converting ebook to plain text...")
        try:
            # --input-encoding and --output-encoding might be needed for some books
            cmd_convert = ['ebook-convert', input_ebook_path, txt_output_path, '--enable-heuristics']
            logging.info(f"Running ebook conversion: {' '.join(cmd_convert)}")
            result_convert = subprocess.run(cmd_convert, check=True, capture_output=True, encoding='utf-8', errors='ignore')
            # Check stdout/stderr even on success for warnings
            if result_convert.stdout: logging.info(f"ebook-convert stdout: {result_convert.stdout.strip()}")
            if result_convert.stderr: logging.warning(f"ebook-convert stderr: {result_convert.stderr.strip()}")
            status_updates.append("✅ Ebook converted to TXT.")
            logging.info("Ebook successfully converted to TXT.")
        except subprocess.CalledProcessError as e:
            stderr_decoded = e.stderr.decode(errors='ignore') if e.stderr else "No stderr"
            error_msg = f"Error during Calibre conversion: {stderr_decoded or e}"
            status_updates.append(f"❌ {error_msg}")
            logging.error(error_msg)
            # Use Markdown for better formatting in Gradio Textbox
            return None, cover_image_path_final, f"**Error:** Calibre conversion failed.\n```\n{stderr_decoded or e}\n```", None # Return extracted cover if available
        except Exception as e:
            error_msg = f"An unexpected error occurred during ebook conversion: {e}"
            status_updates.append(f"❌ {error_msg}")
            logging.error(error_msg, exc_info=True)
            return None, cover_image_path_final, f"**Error:** An unexpected error occurred during ebook conversion:\n{e}", None

        # Check if TXT file was actually created and is not empty
        if not os.path.exists(txt_output_path) or os.path.getsize(txt_output_path) == 0:
            error_msg = "Error: Calibre finished, but the output TXT file is missing or empty. The ebook might be image-based or DRM protected."
            status_updates.append(f"❌ {error_msg}")
            logging.error(error_msg)
            return None, cover_image_path_final, f"**Error:** Calibre finished, but the output TXT file is missing or empty.\nThis can happen with image-based ebooks (like comics/scans) or DRM-protected files.", None

        # --- Step 3: Convert TXT to Audio ---
        progress(0.6, desc="Converting TXT to Audio")
        status_updates.append("Converting text to speech...")

        voice_code = available_voices.get(language_display, 'en') # Get code from display name
        cmd_speak = ['espeak-ng', '-v', voice_code, '-f', txt_output_path]
        # Add speed option if needed: cmd_speak.extend(['-s', '160']) # Example speed

        try:
            logging.info(f"Preparing audio command for format: {output_format}")
            if output_format == 'wav':
                cmd_speak.extend(['-w', audio_output_path])
                logging.info(f"Running espeak-ng (WAV): {' '.join(cmd_speak)}")
                result_speak = subprocess.run(cmd_speak, check=True, capture_output=True) # Capture bytes
                # Log stdout/stderr even on success
                if result_speak.stdout: logging.info(f"espeak-ng stdout: {result_speak.stdout.decode(errors='ignore').strip()}")
                if result_speak.stderr: logging.warning(f"espeak-ng stderr: {result_speak.stderr.decode(errors='ignore').strip()}")

            elif output_format == 'mp3':
                cmd_speak.append('--stdout')
                cmd_lame = ['lame', '-', audio_output_path] # Read from stdin, write to file
                logging.info(f"Running espeak-ng | lame (MP3): {' '.join(cmd_speak)} | {' '.join(cmd_lame)}")
                ps_speak = subprocess.Popen(cmd_speak, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                ps_lame = subprocess.Popen(cmd_lame, stdin=ps_speak.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                # Allow ps_speak to receive SIGPIPE if ps_lame exits early. Crucial!
                if ps_speak.stdout:
                    ps_speak.stdout.close()

                # Capture output/errors and wait for LAME to finish
                lame_stdout_bytes, lame_stderr_bytes = ps_lame.communicate()
                # Capture stderr from espeak and WAIT for it to finish *after* lame is done
                speak_stderr_bytes = ps_speak.stderr.read() if ps_speak.stderr else b""
                ps_speak.wait() # <<< --- Explicitly wait for espeak-ng ---
                if ps_speak.stderr: ps_speak.stderr.close()

                # Decode stderr for logging
                lame_stderr_str = lame_stderr_bytes.decode(errors='ignore').strip()
                speak_stderr_str = speak_stderr_bytes.decode(errors='ignore').strip()

                # Check return codes safely
                if ps_lame.returncode != 0:
                    # LAME failed
                    raise subprocess.CalledProcessError(ps_lame.returncode, cmd_lame, output=lame_stdout_bytes, stderr=lame_stderr_bytes)
                if ps_speak.returncode != 0:
                     # Espeak failed (even if lame seemed okay initially)
                     raise subprocess.CalledProcessError(ps_speak.returncode, cmd_speak, stderr=speak_stderr_bytes) # Pass the captured stderr bytes

                # Log warnings from stderr if processes succeeded
                if lame_stderr_str:
                    logging.warning(f"LAME stderr: {lame_stderr_str}")
                if speak_stderr_str:
                    logging.warning(f"espeak-ng stderr: {speak_stderr_str}")

            elif output_format == 'ogg':
                cmd_speak.append('--stdout')
                cmd_ogg = ['oggenc', '-o', audio_output_path, '-'] # Write to file, read from stdin
                logging.info(f"Running espeak-ng | oggenc (OGG): {' '.join(cmd_speak)} | {' '.join(cmd_ogg)}")
                ps_speak = subprocess.Popen(cmd_speak, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                ps_ogg = subprocess.Popen(cmd_ogg, stdin=ps_speak.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                # Allow ps_speak to receive SIGPIPE if oggenc exits early.
                if ps_speak.stdout:
                    ps_speak.stdout.close()

                # Capture output/errors and wait for oggenc to finish
                ogg_stdout_bytes, ogg_stderr_bytes = ps_ogg.communicate()
                # Capture stderr from espeak and WAIT for it to finish *after* oggenc is done
                speak_stderr_bytes = ps_speak.stderr.read() if ps_speak.stderr else b""
                ps_speak.wait() # <<< --- Explicitly wait for espeak-ng ---
                if ps_speak.stderr: ps_speak.stderr.close()

                # Decode stderr for logging
                ogg_stderr_str = ogg_stderr_bytes.decode(errors='ignore').strip()
                speak_stderr_str = speak_stderr_bytes.decode(errors='ignore').strip()

                # Now check return codes safely
                if ps_ogg.returncode != 0:
                    # Oggenc failed
                    raise subprocess.CalledProcessError(ps_ogg.returncode, cmd_ogg, output=ogg_stdout_bytes, stderr=ogg_stderr_bytes)
                if ps_speak.returncode != 0:
                    # Espeak failed
                    raise subprocess.CalledProcessError(ps_speak.returncode, cmd_speak, stderr=speak_stderr_bytes) # Pass captured stderr bytes

                # Log warnings from stderr if processes succeeded
                if ogg_stderr_str:
                     logging.warning(f"oggenc stderr: {ogg_stderr_str}")
                if speak_stderr_str:
                    logging.warning(f"espeak-ng stderr: {speak_stderr_str}")

            else:
                raise ValueError(f"Unsupported output format: {output_format}")

            status_updates.append("✅ Text converted to audio.")
            logging.info(f"Text successfully converted to {output_format.upper()}.")

        except subprocess.CalledProcessError as e:
            # --- MODIFIED ERROR HANDLING ---
            command_name = e.cmd[0] if isinstance(e.cmd, list) else e.cmd
            # Decode stderr/stdout safely (they might be bytes or None)
            stderr_str = e.stderr.decode(errors='ignore').strip() if isinstance(e.stderr, bytes) else (e.stderr or "")
            stdout_str = e.stdout.decode(errors='ignore').strip() if isinstance(e.stdout, bytes) else (e.stdout or "")
            error_details = stderr_str or stdout_str or "No output/error captured."

            # Construct error message carefully
            exit_status_str = f"exit status {e.returncode}" if e.returncode is not None else "unknown exit status"
            cmd_str = ' '.join(e.cmd) if isinstance(e.cmd, list) else e.cmd
            error_msg = f"Audio generation failed ({command_name} with {exit_status_str})."
            status_updates.append(f"❌ {error_msg}")
            logging.error(f"{error_msg} Command: `{cmd_str}` Output/Error: {error_details}")

            # Use Markdown for better formatting in Gradio Textbox
            md_error_details = f"**Error:** Audio generation failed.\n\n" \
                               f"**Command:**\n```\n{cmd_str}\n```\n" \
                               f"**Exit Status:** {exit_status_str}\n\n" \
                               f"**Output/Error:**\n```\n{error_details}\n```"
            return None, cover_image_path_final, md_error_details, None
            # --- END MODIFIED ERROR HANDLING ---

        except FileNotFoundError as e:
             missing_cmd = e.filename # Usually contains the missing command
             error_msg = f"Error: Command '{missing_cmd}' not found for {output_format.upper()} output."
             status_updates.append(f"❌ {error_msg}")
             logging.error(error_msg)
             return None, cover_image_path_final, f"**Error:** Command `{missing_cmd}` not found.\nPlease install it and ensure it's in your system PATH.", None
        except Exception as e:
            error_msg = f"An unexpected error occurred during audio generation: {e}"
            status_updates.append(f"❌ {error_msg}")
            logging.error(error_msg, exc_info=True)
            return None, cover_image_path_final, f"**Error:** An unexpected error occurred during audio generation:\n{e}", None

        # Check if audio file exists and has size
        if not os.path.exists(audio_output_path) or os.path.getsize(audio_output_path) < 1024: # Check for > 1KB as a basic sanity check
             error_msg = f"Error: Audio generation command finished, but the output file '{Path(audio_output_path).name}' is missing or too small. Check logs for details."
             status_updates.append(f"❌ {error_msg}")
             logging.error(error_msg)
             return None, cover_image_path_final, f"**Error:** Audio output file missing or too small after conversion.\nCheck system logs for `espeak-ng`, `lame`, or `oggenc` or the status box above for errors.", None


        # --- Step 4: Embed Cover Art (Optional) ---
        if embed_cover and cover_extracted and MUTAGEN_AVAILABLE and os.path.exists(cover_image_path_final):
            progress(0.9, desc="Embedding cover art")
            status_updates.append("Embedding cover art into audio file...")
            try:
                with open(cover_image_path_final, 'rb') as img_f:
                    cover_data = img_f.read()

                # Determine mimetype using PIL
                img = Image.open(cover_image_path_final)
                mime_type = Image.MIME.get(img.format)
                img.close()
                if not mime_type:
                     mime_type = 'image/jpeg' # Default guess
                     logging.warning(f"Could not determine MIME type for cover image, defaulting to {mime_type}")


                logging.info(f"Attempting to embed cover art ({mime_type}) into {audio_output_path}")
                audio = mutagen.File(audio_output_path, easy=False) # Use easy=False for more control

                if audio is None:
                     raise ValueError("Mutagen could not load the audio file. Format might be unsupported by Mutagen or file corrupted.")

                # Clear existing images before adding new one (optional, prevents duplicates)
                try:
                    if isinstance(audio, (MP3, EasyMP3)):
                        audio.tags.delall('APIC')
                    elif isinstance(audio, FLAC):
                        audio.clear_pictures()
                    elif isinstance(audio, MP4):
                        if 'covr' in audio:
                            del audio['covr']
                    # OggVorbis picture removal is more complex, might need specific key deletion
                    elif isinstance(audio, OggVorbis) and "metadata_block_picture" in audio:
                        del audio["metadata_block_picture"]
                    audio.save() # Save after deletion before adding
                    audio = mutagen.File(audio_output_path, easy=False) # Re-load
                except Exception as e:
                    logging.warning(f"Could not clear existing artwork before embedding: {e}")


                # Embedding logic differs by format
                if isinstance(audio, (MP3, EasyMP3)):
                    if audio.tags is None: audio.add_tags() # Ensure tags exist
                    audio.tags.add(
                        APIC(
                            encoding=3,  # 3 is for utf-8
                            mime=mime_type,
                            type=3,  # 3 is for cover image (front)
                            desc=u'Cover',
                            data=cover_data
                        )
                    )
                elif isinstance(audio, FLAC):
                     pic = mutagen.flac.Picture()
                     pic.data = cover_data
                     pic.type = mutagen.id3.PictureType.COVER_FRONT
                     pic.mime = mime_type
                     # pic.width, pic.height, pic.depth = ... # Optionally get dimensions from PIL
                     audio.add_picture(pic)
                elif isinstance(audio, OggVorbis):
                     # Ogg uses base64 encoded pictures in METADATA_BLOCK_PICTURE tag
                     import base64
                     pic_data = base64.b64encode(cover_data).decode('ascii')
                     # This field expects a FLAC Picture block, base64 encoded.
                     pic = mutagen.flac.Picture()
                     pic.data = cover_data
                     pic.type = mutagen.id3.PictureType.COVER_FRONT
                     pic.mime = mime_type
                     audio["metadata_block_picture"] = [base64.b64encode(pic.write()).decode("ascii")]

                elif isinstance(audio, MP4):
                     if mime_type == 'image/jpeg':
                         pic_format = MP4Cover.FORMAT_JPEG
                     elif mime_type == 'image/png':
                         pic_format = MP4Cover.FORMAT_PNG
                     else:
                         pic_format = MP4Cover.FORMAT_UNDEFINED # Or skip if unknown
                         logging.warning(f"Unsupported cover image format ({mime_type}) for MP4 embedding.")

                     if pic_format != MP4Cover.FORMAT_UNDEFINED:
                         audio['covr'] = [MP4Cover(cover_data, imageformat=pic_format)]

                # Add other metadata (optional)
                try:
                    # Use easy=True for simpler metadata access if needed elsewhere
                    audio_easy = mutagen.File(audio_output_path, easy=True)
                    if audio_easy is not None:
                         audio_easy['title'] = base_filename
                         audio_easy['artist'] = "Generated Audiobook" # Or try to get from ebook metadata later
                         audio_easy.save() # Save easy tags first
                except Exception as tag_err:
                    logging.warning(f"Could not set basic title/artist tags: {tag_err}")
                    # If easy tags failed, save the main audio object (with picture)
                    if audio is not None: audio.save()
                else:
                     # If easy tags succeeded, save the main audio object too (if necessary, though easy.save might suffice)
                     if audio is not None: audio.save()


                status_updates.append("✅ Cover art embedded successfully.")
                logging.info("Cover art embedded successfully.")

            except (mutagen.MutagenError, ValueError, IOError, TypeError, KeyError) as e:
                 status_updates.append(f"⚠️ Could not embed cover art. Error: {e}")
                 logging.warning(f"Failed to embed cover art: {e}", exc_info=True)
            except Exception as e:
                 status_updates.append(f"⚠️ An unexpected error occurred during cover art embedding: {e}")
                 logging.error(f"Unexpected error during cover embedding: {e}", exc_info=True)
        elif embed_cover and not cover_extracted:
             status_updates.append("ℹ️ Cover art embedding skipped (no cover extracted or invalid).")
        elif embed_cover and not MUTAGEN_AVAILABLE:
             status_updates.append("⚠️ Cover art embedding skipped (Mutagen library not installed).")


        # --- Step 5: Prepare final output ---
        progress(1.0, desc="Complete")
        status_updates.append("✅ Conversion complete!")
        audio_output_path_final = audio_output_path # Mark the path as final

        # Return paths for Gradio components
        final_status = "\n".join(status_updates)
        # Need to return a *copy* of the file outside the temp dir, or Gradio might lose it after cleanup
        # However, Gradio usually handles temp files well if returned directly. Let's try direct return first.
        # If issues arise, copy the file to a more stable temp location managed by Gradio if possible, or just let the user download.
        logging.info(f"Returning audio: {audio_output_path_final}, cover: {cover_image_path_final}")
        # Return audio path twice: once for Audio component, once for File component
        return audio_output_path_final, cover_image_path_final, final_status, audio_output_path_final

    except Exception as e:
        error_msg = f"An unexpected error occurred in the main process: {e}"
        status_updates.append(f"❌ {error_msg}")
        logging.error(error_msg, exc_info=True)
        return None, cover_image_path_final, f"**Error:** An unexpected critical error occurred.\nCheck logs for details.\n{e}", None # Return what we have

    finally:
        # --- Cleanup ---
        # Keep the final audio and cover files if successful, delete the rest
        # Gradio should handle the returned file paths, but clean the temp dir *contents* just in case.
        # It's safer to let Gradio manage the returned files' lifecycle.
        # We'll clean the intermediate files (.txt, original cover if converted).
        try:
            if 'txt_output_path' in locals() and os.path.exists(txt_output_path):
                os.remove(txt_output_path)
                logging.info(f"Removed intermediate file: {txt_output_path}")
            # Remove original cover if it was converted and different from final
            if ('cover_image_path_final' in locals() and cover_image_path_final and
                'cover_output_path_temp' in locals() and cover_output_path_temp != cover_image_path_final and
                os.path.exists(cover_output_path_temp)):
                 os.remove(cover_output_path_temp)
                 logging.info(f"Removed intermediate file: {cover_output_path_temp}")
            # Let Gradio handle the final audio/cover paths returned.
            # Do NOT delete temp_dir itself if files within it were returned to Gradio.
            # If Gradio copies the files, then shutil.rmtree(temp_dir) is safe. Test this behavior.
            # For safety, let's rely on OS/Gradio temp file cleanup unless memory becomes an issue.
            if 'temp_dir' in locals() and os.path.exists(temp_dir):
                logging.info(f"Skipping deletion of temp dir '{temp_dir}' to allow Gradio access to output files.")
                # To force cleanup (may break Gradio display):
                # shutil.rmtree(temp_dir, ignore_errors=True)
                # logging.info(f"Attempted cleanup of temp dir: {temp_dir}")


        except OSError as e:
            logging.warning(f"Could not remove intermediate file: {e}")


# --- Gradio Interface Definition ---

available_voices = get_espeak_voices()
voice_choices = list(available_voices.keys())
default_voice = "English (en-US) (en-us)" if "English (en-US) (en-us)" in voice_choices else ("English (en)" if "English (en)" in voice_choices else (voice_choices[0] if voice_choices else "en")) # Sensible default

# Check for external tools on startup and display warnings if needed
startup_warnings = []
if not check_command("ebook-convert"): startup_warnings.append("Calibre ('ebook-convert')")
if not check_command("ebook-meta"): startup_warnings.append("Calibre ('ebook-meta' - recommended for cover art)")
if not check_command("espeak-ng"): startup_warnings.append("espeak-ng")
if not check_command("lame"): startup_warnings.append("LAME (needed for MP3 output)")
if not check_command("oggenc"): startup_warnings.append("oggenc (needed for OGG output)")
if not MUTAGEN_AVAILABLE: startup_warnings.append("Python 'mutagen' library (needed for embedding cover art)")

startup_message = ""
if startup_warnings:
    startup_message = (
        "**⚠️ Startup Warning: The following components might be missing or not found in PATH:**\n\n"
        f"- {', '.join(startup_warnings)}\n\n"
        "Please install them for full functionality. Check console logs for details."
    )
    print("-" * 60)
    print(f"STARTUP WARNING: Missing components: {', '.join(startup_warnings)}")
    print("-" * 60)

# Define UI Elements
with gr.Blocks(theme=gr.themes.Soft()) as demo:
    gr.Markdown("# Ebook to Audiobook Converter 🎧📚")
    gr.Markdown("Upload an ebook file (EPUB, MOBI, AZW3, PDF*, etc.), choose a language and format, and convert it to an audiobook using Calibre and eSpeak-NG.\n\n"
                "*Note: PDF conversion quality varies greatly. Text-based PDFs work best.*")

    if startup_message:
        gr.Markdown(startup_message) # Display warning in UI

    with gr.Row():
        with gr.Column(scale=1):
            ebook_input = gr.File(label="1. Upload Ebook", file_count="single")
            lang_dropdown = gr.Dropdown(
                label="2. Select Language / Voice",
                choices=voice_choices,
                value=default_voice,
                interactive=True
            )
            format_dropdown = gr.Dropdown(
                label="3. Select Output Audio Format",
                choices=["mp3", "ogg", "wav"],
                value="mp3",
                interactive=True
            )
            cover_checkbox = gr.Checkbox(
                label="Embed Cover Art (if available)",
                value=True if MUTAGEN_AVAILABLE else False, # Default to True if mutagen is there
                interactive=MUTAGEN_AVAILABLE # Disable if mutagen is missing
            )
            submit_button = gr.Button("Convert to Audiobook", variant="primary")

        with gr.Column(scale=2):
            status_textbox = gr.Textbox(label="Conversion Status", lines=12, interactive=False, max_lines=25, show_copy_button=True)
            with gr.Row():
                 # Use filepath for image to avoid potential base64 encoding issues with large images
                 cover_image = gr.Image(label="Extracted Cover Art", type="filepath", interactive=False, height=200, width=200)
                 # Use filepath for audio for consistency and potentially better handling of large files
                 audio_output_player = gr.Audio(label="Generated Audiobook", type="filepath", interactive=False)
            # Add a dedicated download button using gr.File
            audio_output_download = gr.File(label="Download Audiobook File", interactive=False)

    # Connect components
    submit_button.click(
        fn=convert_ebook_to_audio,
        inputs=[ebook_input, lang_dropdown, format_dropdown, cover_checkbox],
        outputs=[audio_output_player, cover_image, status_textbox, audio_output_download] # Map audio path to Audio player and File download
    )

# --- Launch the App ---
if __name__ == "__main__":
    print("Starting Gradio App...")
    print("Ensure Calibre (ebook-convert, ebook-meta), espeak-ng, lame, and oggenc are installed and in your system PATH.")
    if not voice_choices:
         print("\nWARNING: Could not retrieve any voices from espeak-ng. The language dropdown will be limited or empty!\n")
    demo.launch(server_name="0.0.0.0", server_port=7860)# Add share=True here if you need a public link: demo.launch(share=True)
