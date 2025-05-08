import requests
import time
import os

API_KEY = '8e15a6bdf0f3ff94a9594678e1ab1209'
SCAN_URL = 'https://api.metadefender.com/v4/file'

HEADERS = {
    'apikey': API_KEY
}

def scan_zip_file(file_path):
    print(f"Uploading {file_path} to MetaDefender...")

    with open(file_path, 'rb') as f:
        files = {'file': (os.path.basename(file_path), f)}
        response = requests.post(SCAN_URL, headers=HEADERS, files=files)

    if response.status_code != 200:
        print("Failed to upload file.")
        return False

    data = response.json()
    data_id = data.get('data_id')

    if not data_id:
        print("No data_id received.")
        return False

    # Poll for scan result
    report_url = f"https://api.metadefender.com/v4/file/{data_id}"
    print("Waiting for scan results...")

    for _ in range(10):  # Poll up to 10 times
        time.sleep(3)
        report = requests.get(report_url, headers=HEADERS).json()

        scan_results = report.get("scan_results", {})
        if scan_results.get("progress_percentage", 0) < 100:
            continue

        threats_found = scan_results.get("total_detected_avs", 0)
        if threats_found > 0:
            print(f"Malware detected by {threats_found} engines.")
            return False

        print("File is clean!")
        return True

    print("Scan timed out.")
    return False
