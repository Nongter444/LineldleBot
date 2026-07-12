import sys
import time
import subprocess
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

TARGET_FILE = "bot.py"

class RestartHandler(FileSystemEventHandler):
    def __init__(self):
        self.process = None
        self.last_restart_time = 0
        self.start_program()

    def start_program(self):
        # 1. จัดการปิดตัวเก่า
        if self.process:
            if self.process.poll() is None: # ถ้ายังรันอยู่
                print("🛑 กำลังปิดบอทตัวเก่า...")
                self.process.kill() # สำหรับ GUI การ kill มักจะไวกว่า
                self.process.wait()
        
        # 2. เปิดตัวใหม่
        print(f"🚀 [{time.strftime('%H:%M:%S')}] กำลังรัน {TARGET_FILE}...")
        self.process = subprocess.Popen([sys.executable, TARGET_FILE])

    def on_modified(self, event):
        # ตรวจสอบว่าเป็นไฟล์เป้าหมาย และป้องกันการรันซ้ำภายใน 1 วินาที (Debounce)
        if event.src_path.endswith(TARGET_FILE):
            current_time = time.time()
            if current_time - self.last_restart_time > 1.5: # หน่วงไว้ 1.5 วินาที
                print(f"\n♻️ ตรวจพบการแก้ไข! กำลังรีสตาร์ท...")
                self.last_restart_time = current_time
                self.start_program()

if __name__ == "__main__":
    if not os.path.exists(TARGET_FILE):
        print(f"❌ หาไฟล์ {TARGET_FILE} ไม่เจอ!")
        sys.exit(1)

    print(f"👀 Watchdog is active on: {TARGET_FILE}")
    
    event_handler = RestartHandler()
    observer = Observer()
    # ตรวจสอบเฉพาะโฟลเดอร์ปัจจุบัน
    observer.schedule(event_handler, path=".", recursive=False)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()