import os
import time
import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import pystray
from PIL import Image, ImageDraw
from extract import ZipHandler  # Import your upgraded ZipHandler

class DownloadNotifier:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("ZIP Monitor")
        self.root.geometry("450x300+50+50")
        self.root.resizable(True, True)

        # Apply a modern theme if available
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        # Main frame to hold all widgets
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill="both", expand=True)

        # Label to display the current status
        self.status_label = ttk.Label(main_frame, text="Monitoring Downloads...", wraplength=400, font=("Segoe UI", 10))
        self.status_label.pack(pady=(0, 8))

        # Label to display the current folder being monitored
        self.folder_label = ttk.Label(main_frame, text="", wraplength=400, font=("Segoe UI", 8), foreground="#555")
        self.folder_label.pack(pady=(0, 8))

        # Scrolled text area to display logs
        self.log_text = scrolledtext.ScrolledText(main_frame, height=6, font=("Segoe UI", 8))
        self.log_text.pack(fill="both", expand=True, pady=(0, 10))

        # Style for smaller buttons
        style.configure("Small.TButton", padding=(5, 3), font=("Segoe UI", 8))

        # Buttons container
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack()

        # Button to open the current folder
        self.button = ttk.Button(btn_frame, text="Open Folder", command=self.open_folder, style="Small.TButton")
        self.button.grid(row=0, column=0, padx=5)
        self.button.grid_remove()  # Hide initially

        # Button to change the monitored folder
        self.change_folder_button = ttk.Button(btn_frame, text="Change Folder", command=self.change_folder, style="Small.TButton")
        self.change_folder_button.grid(row=0, column=1, padx=5)

        self.current_zip = None
        self.observer = None
        # Ensures the window always stays on top of all other windows
        self.root.attributes("-topmost", True)

    # Updates the status label and sets the current zip file
    def update_status(self, text, zip_path=None):
        self.status_label.config(text=text)
        self.current_zip = zip_path
        if zip_path:
            self.button.grid()
        else:
            self.button.grid_remove()

    # Opens the folder containing the current zip file
    def open_folder(self):
        if self.current_zip:
            folder = os.path.dirname(self.current_zip)
            os.startfile(folder)

    # Changes the monitored folder
    def change_folder(self):
        # Stop existing observer if running
        if self.observer:
            self.observer.stop()
            self.observer.join()
        # Ask for a new folder
        new_folder = ask_folder()
        if new_folder:
            self.log_text.delete(1.0, tk.END)  # Clear the log text area
            self.start_observer(new_folder)
            self.folder_label.config(text=f"Folder: {new_folder}")

    # Starts the observer for the given folder
    def start_observer(self, folder):
        event_handler = ZipHandler(self)
        self.observer = Observer()
        self.observer.schedule(event_handler, folder, recursive=False)
        self.observer.start()
        self.folder_label.config(text=f"Folder: {folder}")

    # Appends a log message to the log text area
    def append_log(self, *args):
        message = " ".join(str(arg) for arg in args)
        self.log_text.insert("end", f"{message}\n")
        self.log_text.see("end")

# Asks the user to select a folder to monitor
def ask_folder():
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    folder = filedialog.askdirectory(title="Select folder to monitor", initialdir=downloads)
    return folder if folder else None

# Creates a system tray icon for the application
def create_tray_icon(app):
    # Create simple icon
    icon_image = Image.new("RGB", (64, 64), "white")
    draw = ImageDraw.Draw(icon_image)
    draw.rectangle((16, 16, 48, 48), fill="black")

    def on_quit(icon, item):
        icon.stop()
        app.root.quit()

    menu = pystray.Menu(pystray.MenuItem("Quit", on_quit))
    icon = pystray.Icon("ZIP Monitor", icon_image, "ZIP Monitor", menu)
    threading.Thread(target=icon.run, daemon=True).start()

if __name__ == "__main__":
    notifier = DownloadNotifier()
    default_folder = os.path.join(os.path.expanduser("~"), "Downloads")
    notifier.start_observer(default_folder)
    create_tray_icon(notifier)
    notifier.root.mainloop()