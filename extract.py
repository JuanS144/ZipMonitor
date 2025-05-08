from dotenv import load_dotenv
load_dotenv()
import os
import shutil
import time
import zipfile
from PIL import Image
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import google.generativeai as genai
import PyPDF2  # Import PyPDF2
from metadefender import scan_zip_file
import threading

DOWNLOADS_DIR = os.path.expanduser("~/Downloads")
DEST_DIRS = {
    'pdf': '~/Documents',
    'jpg': '~/Pictures',
    'png': '~/Pictures',
    'docx': '~/Documents',
    'txt': '~/Documents',
}

class ZipHandler(FileSystemEventHandler):

    def __init__(self, notifier):
        GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
        if not GOOGLE_API_KEY:
            raise EnvironmentError(
                "GOOGLE_API_KEY is not set. Please set it in your environment or .env file.")
        genai.configure(api_key=GOOGLE_API_KEY)
        self.notifier = notifier  # Ensure notifier is set
        self.notifier.append_log("[DEBUG] genai is using API key:", "yes" if GOOGLE_API_KEY else "no")

        # Print the directories being used
        self.notifier.append_log("DOWNLOADS_DIR resolves to:", DOWNLOADS_DIR)
        for ext, dest in DEST_DIRS.items():
            self.notifier.append_log(f"{ext.upper()} files will go to:", os.path.expanduser(dest))

    def on_created(self, event):
        if event.src_path.endswith(".zip"):
            print(f"Detected ZIP: {event.src_path}")
            self.notifier.update_status(
                f"Downloaded ZIP:\n{os.path.basename(event.src_path)}",
                event.src_path
            )
            self.notifier.append_log(f"[EVENT] Detected ZIP file: {event.src_path}")
            self.extract_and_sort(event.src_path)
    
    def extract_and_sort(self, zip_path):
        try:
            # Wait up to 5 seconds for the file to be fully written
            for _ in range(10):
                if os.path.exists(zip_path) and os.path.getsize(zip_path) > 0:
                    try:
                        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                            # Try to read to check if it's ready
                            test = zip_ref.testzip()
                            if test is None:
                                break  # Valid zip, ready to process
                    except zipfile.BadZipFile:
                        pass
                time.sleep(0.5)
            else:
                self.notifier.append_log(f"File {zip_path} is not ready or invalid.")
                return
            
            if not scan_zip_file(zip_path):
                self.notifier.append_log(f"Skipping unsafe file: {zip_path}")
                return

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                extract_path = zip_path.replace('.zip', '')
                zip_ref.extractall(extract_path)
                self.notifier.append_log(f"Extracted to {extract_path}")

            self.generate_smart_summary(zip_path, extract_path)

            for root, _, files in os.walk(extract_path):
                for file in files:
                    ext = file.split('.')[-1].lower()
                    dest = DEST_DIRS.get(ext)
                    if dest:
                        abs_dest = os.path.expanduser(dest)
                        os.makedirs(abs_dest, exist_ok=True)
                        src_file_path = os.path.join(root, file)
                        dest_file_path = os.path.join(abs_dest, file)

                        # Auto-rename if file already exists
                        base, ext = os.path.splitext(dest_file_path)
                        counter = 1
                        while os.path.exists(dest_file_path):
                            dest_file_path = f"{base}_{counter}{ext}"
                            counter += 1

                        shutil.move(src_file_path, dest_file_path)
                        self.notifier.append_log(f"Moved {file} to {dest_file_path}")

        except Exception as e:
            self.notifier.append_log(f"Error handling {zip_path}: {e}")

    def generate_smart_summary(self, zip_path, extract_path):
        self.notifier.append_log("[AI] Generating individual summaries...")
        individual_summaries = []  # List to store "filename: summary" strings
        zip_filename = os.path.basename(zip_path)
        model = genai.GenerativeModel(
            "gemini-1.5-pro-latest")  # Initialize model once

        for root, _, files in os.walk(extract_path):
            for file in files:
                file_path = os.path.join(root, file)
                filename_only = os.path.basename(file_path)  # Get just the filename
                ext = filename_only.lower().split('.')[-1]
                file_summary = f'{filename_only}: "No summary generated."'  # Default

                if ext == "txt":
                    try:
                        self.notifier.append_log(f"[SUMMARIZING TEXT] {file_path}")
                        with open(file_path, "r", encoding="utf-8",
                                    errors="ignore") as f:
                            text_content = f.read()
                            if text_content.strip():  # Only summarize if there's content
                                # Limit text length to avoid hitting token limits excessively
                                max_len = 7500  # Adjust as needed, leave room for prompt
                                truncated_content = text_content[:max_len]
                                prompt = f"Provide a concise summary of the following text:\n\n{truncated_content}"
                                response = model.generate_content(prompt)
                                file_summary = f'{filename_only}: "{response.text}"'
                            else:
                                file_summary = f'{filename_only}: "File is empty."'
                    except Exception as e:
                        self.notifier.append_log(f"[TEXT SUMMARY FAIL] {file}: {e}")
                        file_summary = f'{filename_only}: "Error reading or summarizing text: {e}"'

                elif ext in ["jpg", "jpeg", "png"]:
                    try:
                        self.notifier.append_log(f"[DESCRIBING IMAGE] {file_path}")
                        with Image.open(file_path) as img:
                            prompt = "Describe this image concisely."
                            response = model.generate_content([prompt, img])
                        file_summary = f'{filename_only}: "{response.text}"'
                    except Exception as e:
                        self.notifier.append_log(f"[IMAGE DESCRIBE FAIL] {file}: {e}")
                        file_summary = f'{filename_only}: "Error describing image: {e}"'

                elif ext == "pdf":
                    try:
                        self.notifier.append_log(f"[READING PDF] {file_path}")
                        text_content = self.read_pdf_text(file_path)  # Use the function defined below
                        if text_content.strip():
                            max_len = 7500
                            truncated_content = text_content[:max_len]
                            prompt = f"Summarize the following text from a PDF:\n\n{truncated_content}"
                            response = model.generate_content(prompt)
                            file_summary = f'{filename_only}: "{response.text}"'
                        else:
                            file_summary = f'{filename_only}: "PDF file is empty."'
                    except Exception as e:
                        self.notifier.append_log(f"[PDF READ FAIL] {file}: {e}")
                        file_summary = f'{filename_only}: "Error reading PDF: {e}"'

                # Add other file types here if needed
                # elif ext == "docx":
                #     # Add DOCX processing
                #     pass

                individual_summaries.append(file_summary)

        # --- Construct the final output string ---
        if not individual_summaries:
            final_output = (
                f"No readable files found in {zip_filename} to summarize.")
        else:
            final_output = f"Summaries for files in {zip_filename}:\n\n" + "\n\n".join(
                individual_summaries)
        # --- END ---

        summary_filename = "summary_" + zip_filename.replace(".zip", ".txt")
        summary_path = os.path.join(os.path.dirname(zip_path), summary_filename)
        try:
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(final_output)
            self.notifier.append_log(f"[DONE] Individual summaries saved: {summary_path}")
        except Exception as e:
            self.notifier.append_log(f"[SAVE SUMMARY FAIL] Could not write summary file: {e}")
    
    def read_pdf_text(self, pdf_path):
        """Extract text from a PDF file using PyPDF2."""
        text = ""
        try:
            with open(pdf_path, 'rb') as file:  # 'rb' for read binary
                reader = PyPDF2.PdfReader(file)
                for page_num in range(len(reader.pages)):
                    page = reader.pages[page_num]
                    text += page.extract_text() or ""  # extract_text() might return None
        except Exception as e:
            self.notifier.append_log(f"Error reading PDF: {e}")
            return ""
        return text