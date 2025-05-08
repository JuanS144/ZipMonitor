from dotenv import load_dotenv

load_dotenv()
import os
import shutil
import time
import zipfile
from PIL import Image
import pytesseract
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import google.generativeai as genai
import PyPDF2  # Import PyPDF2

DOWNLOADS_DIR = os.path.expanduser("~/Downloads")
DEST_DIRS = {
    'pdf': '~/Documents',
    'jpg': '~/Pictures',
    'png': '~/Pictures',
    'docx': '~/Documents',  # Note: DOCX content reading is not implemented here
    'txt': '~/Documents',
}
# Ensure you have set GOOGLE_API_KEY
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise EnvironmentError(
        "GOOGLE_API_KEY is not set. Please set it in your environment or .env file.")
genai.configure(api_key=GOOGLE_API_KEY)
print("[DEBUG] genai is using API key:", "yes" if GOOGLE_API_KEY else "no")


# Print the directories being used
print("DOWNLOADS_DIR resolves to:", DOWNLOADS_DIR)
for ext, dest in DEST_DIRS.items():
    print(f"{ext.upper()} files will go to:", os.path.expanduser(dest))


# File system event handler for ZIP files
class ZipHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.src_path.endswith('.zip'):
            print(f"[CREATED] Detected ZIP file: {event.src_path}")
            self.extract_and_sort(event.src_path)

    def on_modified(self, event):
        if event.src_path.endswith('.zip'):
            print(f"[MODIFIED] Detected ZIP file: {event.src_path}")
            self.extract_and_sort(event.src_path)

    def extract_and_sort(self, zip_path):
        try:
            if not self.wait_for_download_complete(zip_path):
                print(f"File {zip_path} did not stabilize in time.")
                return

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                extract_path = zip_path.replace('.zip', '')
                zip_ref.extractall(extract_path)
                print(f"Extracted to {extract_path}")

            # === STEP 1: AI summary before anything moves
            self.generate_smart_summary(zip_path, extract_path)

            # === STEP 2: Now move files
            for root, _, files in os.walk(extract_path):
                for file in files:
                    ext = file.split('.')[-1].lower()
                    dest = DEST_DIRS.get(ext)
                    if dest:
                        abs_dest = os.path.expanduser(dest)
                        os.makedirs(abs_dest, exist_ok=True)
                        shutil.move(os.path.join(root, file),
                                    os.path.join(abs_dest, file))
                        print(f"Moved {file} to {abs_dest}")

        except Exception as e:
            print(f"Error handling {zip_path}: {e}")
        finally:
            # Clean up the extracted folder after processing
            if 'extract_path' in locals() and os.path.isdir(extract_path):
                print(f"Cleaning up extracted folder: {extract_path}")
                shutil.rmtree(extract_path)

    @staticmethod
    def wait_for_download_complete(path, timeout=30, interval=1):
        """Wait until file size has stabilized (download complete)."""
        prev_size = -1
        stable_count = 0
        start_time = time.time()
        while time.time() - start_time < timeout:
            if os.path.exists(path):
                curr_size = os.path.getsize(path)
                if curr_size == prev_size:
                    stable_count += 1
                    if stable_count >= 3:
                        return True
                else:
                    stable_count = 0
                prev_size = curr_size
            time.sleep(interval)
        return False

    def generate_smart_summary(self, zip_path, extract_path):
        print("[AI] Generating individual summaries...")
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
                        print(f"[SUMMARIZING TEXT] {file_path}")
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
                        print(f"[TEXT SUMMARY FAIL] {file}: {e}")
                        file_summary = f'{filename_only}: "Error reading or summarizing text: {e}"'

                elif ext in ["jpg", "jpeg", "png"]:
                    try:
                        print(f"[DESCRIBING IMAGE] {file_path}")
                        img = Image.open(file_path)
                        prompt = "Describe this image concisely."  # Changed prompt for brevity
                        response = model.generate_content([prompt, img])
                        file_summary = f'{filename_only}: "{response.text}"'
                    except Exception as e:
                        print(f"[IMAGE DESCRIBE FAIL] {file}: {e}")
                        file_summary = f'{filename_only}: "Error describing image: {e}"'

                elif ext == "pdf":
                    try:
                        print(f"[READING PDF] {file_path}")
                        text_content = read_pdf_text(file_path)  # Use the function defined below
                        if text_content.strip():
                            max_len = 7500
                            truncated_content = text_content[:max_len]
                            prompt = f"Summarize the following text from a PDF:\n\n{truncated_content}"
                            response = model.generate_content(prompt)
                            file_summary = f'{filename_only}: "{response.text}"'
                        else:
                            file_summary = f'{filename_only}: "PDF file is empty."'
                    except Exception as e:
                        print(f"[PDF READ FAIL] {file}: {e}")
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
            print(f"[DONE] Individual summaries saved: {summary_path}")
        except Exception as e:
            print(f"[SAVE SUMMARY FAIL] Could not write summary file: {e}")


def read_pdf_text(pdf_path):
    """Extract text from a PDF file using PyPDF2."""
    text = ""
    try:
        with open(pdf_path, 'rb') as file:  # 'rb' for read binary
            reader = PyPDF2.PdfReader(file)
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                text += page.extract_text() or ""  # extract_text() might return None
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return ""
    return text


if __name__ == "__main__":
    print("===================================")
    print("ZIP AI Summarizer is now active")
    print(f"Watching folder: {DOWNLOADS_DIR}")
    print("===================================\n")

    try:
        event_handler = ZipHandler()
        observer = Observer()
        observer.schedule(event_handler, DOWNLOADS_DIR, recursive=False)
        observer.start()
    except Exception as e:
        print(f"Failed to start observer: {e}")
        exit(1)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping ZIP watcher...")
        observer.stop()
    observer.join()
    print("Exited cleanly.")
