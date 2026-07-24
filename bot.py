import customtkinter as ctk
import subprocess
import os
import re
import threading
import time
import queue
import cv2
import numpy as np
from tkinter import filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
from PIL import Image, ImageTk

# --- ตั้งค่า Config ---
GAME_PKG = "com.linecorp.LGATF"
GAME_PREF_FILE = "trident.preferences.xml" 
LOCAL_BACKUP_PATH = "LineIdle_Data"
TEMP_SD_PATH = "/sdcard/Temp_Bot_Data"

if not os.path.exists(LOCAL_BACKUP_PATH):
    os.makedirs(LOCAL_BACKUP_PATH)

# ==============================================================
# 📸 ระบบแคปหน้าจอ & ค้นหารูปภาพ (Image Search)
# ==============================================================
def screencap_from_device(device):
    try:
        proc = subprocess.Popen(
            ["adb", "-s", device, "exec-out", "screencap", "-p"], 
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        data, err = proc.communicate(timeout=5)
        if not data: return None
        image = np.frombuffer(data, dtype=np.uint8)
        decoded = cv2.imdecode(image, cv2.IMREAD_COLOR)
        return decoded
    except:
        return None

def ImgSearchADB(adb_img, find_img_path, threshold=0.85):
    try:
        if adb_img is None: return []
        if not os.path.exists(find_img_path): 
            return [] 
        
        template = cv2.imread(find_img_path, cv2.IMREAD_COLOR)
        if template is None: return []
        if adb_img.shape[0] < template.shape[0] or adb_img.shape[1] < template.shape[1]: return []
        
        result = cv2.matchTemplate(adb_img, template, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= threshold)
        points = []
        for pt in zip(*locations[::-1]):
            h, w = template.shape[:2]
            points.append((pt[0] + int(w/2), pt[1] + int(h/2)))
            break 
        return points
    except Exception:
        return []

# ==============================================================
# 📦 สร้างคลาส Wrapper รองรับ Drag & Drop
# ==============================================================
class TkWrapper(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)

class LineIdleBot(TkWrapper):
    def __init__(self):
        super().__init__()
        self.title("Line Idle Manager (Multi-Device Pro)")
        self.iconbitmap("capybara.ico") if os.path.exists("capybara.ico") else None
        self.geometry("900x750")
        ctk.set_appearance_mode("Dark")

        self.rows = [] 
        self.file_q = queue.Queue() 
        self.file_lock = threading.Lock() 
        self.stop_events = {} 

        # ==========================================
        # 1. ส่วนหัว (TOP PANEL)
        # ==========================================
        self.frame_top = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_top.pack(pady=10, padx=10, fill="x")
        
        try:
            pil_image = Image.open("logo.png")
            icon_img = ImageTk.PhotoImage(pil_image)
            self.wm_iconphoto(True, icon_img)
            logo_ctk = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(45, 45))
            self.label_title = ctk.CTkLabel(self.frame_top, text=" Line Idle Manager", image=logo_ctk, compound="left", font=("Arial", 22, "bold"), text_color="#2CC985")
            self.label_title.pack(side="left", padx=10)
        except Exception:
            ctk.CTkLabel(self.frame_top, text="🎮 Line Idle Manager", font=("Arial", 20, "bold"), text_color="#2CC985").pack(side="left", padx=10)

        self.btn_refresh = ctk.CTkButton(self.frame_top, text="🔄 รีเฟรชจอ", width=80, fg_color="#4A5568", hover_color="#2D3748", command=self.refresh_devices)
        self.btn_refresh.pack(side="right", padx=5)

        self.btn_connect = ctk.CTkButton(self.frame_top, text="🔗 เชื่อมพอร์ต", width=80, fg_color="#3182CE", command=self.manual_connect)
        self.btn_connect.pack(side="right", padx=5)

        self.entry_port = ctk.CTkEntry(self.frame_top, placeholder_text="เลขพอร์ต...", width=100)
        self.entry_port.pack(side="right", padx=5)

        # ==========================================
        # 1.5 แถบจัดการไฟล์คิว (FILE QUEUE PANEL)
        # ==========================================
        self.frame_queue = ctk.CTkFrame(self, fg_color="#1F1F1F", border_width=1, border_color="#333")
        self.frame_queue.pack(pady=(0, 10), padx=15, fill="x")

        f_left = ctk.CTkFrame(self.frame_queue, fg_color="transparent")
        f_left.pack(side="left", padx=10, pady=10)
        
        ctk.CTkLabel(f_left, text="📂 คิวไฟล์สำหรับยัดไอดี (ลากไฟล์มาวางได้เลย):", font=("Arial", 14, "bold")).pack(anchor="w")
        self.lbl_queue_count = ctk.CTkLabel(f_left, text="ไฟล์ในคิว: 0 ไฟล์", font=("Arial", 14), text_color="#F6E05E")
        self.lbl_queue_count.pack(anchor="w")

        self.btn_clear_q = ctk.CTkButton(self.frame_queue, text="🗑️ ล้างคิว", width=80, fg_color="#E53E3E", command=self.clear_queue)
        self.btn_clear_q.pack(side="right", padx=10, pady=10)

        self.btn_browse = ctk.CTkButton(self.frame_queue, text="📂 เลือกไฟล์", width=100, fg_color="#3182CE", command=self.sel_file)
        self.btn_browse.pack(side="right", padx=5, pady=10)

        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self.drop_files)

        # ==========================================
        # 2. พื้นที่ตาราง (TABLE AREA)
        # ==========================================
        self.table_frame = ctk.CTkScrollableFrame(self, label_text="รายการอุปกรณ์", border_width=1, border_color="#333", corner_radius=10)
        self.table_frame.pack(fill="both", expand=True, padx=15, pady=5)

        # ==========================================
        # 3. ปุ่มควบคุมหลัก (ACTION PANEL)
        # ==========================================
        self.frame_action = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_action.pack(pady=10, padx=15, fill="x")

        self.btn_start_all = ctk.CTkButton(self.frame_action, text="🚀 เริ่มทำงาน (จอที่เลือก)", font=("Arial", 16, "bold"), height=45, fg_color="#2CC985", hover_color="#22543D", command=self.start_tasks)
        self.btn_start_all.pack(side="left", fill="x", expand=True, padx=5)

        self.btn_stop_all = ctk.CTkButton(self.frame_action, text="⏹️ ปิดเกม (จอที่เลือก)", font=("Arial", 16, "bold"), height=45, fg_color="#E53E3E", hover_color="#C53030", command=self.stop_games)
        self.btn_stop_all.pack(side="right", fill="x", expand=True, padx=5)

        # ==========================================
        # 4. กล่อง LOG (CONSOLE)
        # ==========================================
        self.textbox_log = ctk.CTkTextbox(self, height=120, font=("Consolas", 12), text_color="#A0AEC0", fg_color="#1A1A1A")
        self.textbox_log.pack(pady=(0, 10), padx=15, fill="x")

        self.refresh_devices()

    # ======================================================
    # ระบบจัดการคิวไฟล์
    # ======================================================
    def drop_files(self, event):
        data = event.data
        if "{" in data:
            files = [f.strip("{}") for f in re.findall(r"\{.*?\}|\S+", data)]
        else:
            files = data.split()
            
        valid_files = [f for f in files if f.lower().endswith('.xml') and os.path.isfile(f)]
        if valid_files:
            for f in valid_files: self.file_q.put(f)
            self.lbl_queue_count.configure(text=f"ไฟล์ในคิว: {self.file_q.qsize()} ไฟล์", text_color="#68D391")
            self.log(f"📥 เพิ่ม {len(valid_files)} ไฟล์ลงในคิวแล้ว")
        else:
            messagebox.showwarning("Warning", "รองรับเฉพาะไฟล์ .xml เท่านั้นครับ")

    def sel_file(self):
        fs = filedialog.askopenfilenames(filetypes=[("XML Files", "*.xml")]) 
        if fs:
            for f in fs: self.file_q.put(f)
            self.lbl_queue_count.configure(text=f"ไฟล์ในคิว: {self.file_q.qsize()} ไฟล์", text_color="#68D391")
            self.log(f"📥 เพิ่ม {len(fs)} ไฟล์ลงในคิวแล้ว")

    def clear_queue(self):
        with self.file_q.mutex:
            self.file_q.queue.clear()
        self.lbl_queue_count.configure(text="ไฟล์ในคิว: 0 ไฟล์", text_color="#F6E05E")
        self.log("🗑️ ล้างคิวไฟล์ทั้งหมดแล้ว")

    # --- ฟังก์ชันช่วย ---
    def log(self, message):
        ts = time.strftime("%H:%M:%S")
        self.textbox_log.insert("end", f"[{ts}] {message}\n")
        self.textbox_log.see("end")

    def adb_cmd(self, cmd, device):
        try:
            return subprocess.run(f"adb -s {device} shell {cmd}", shell=True, capture_output=True, text=True).stdout.strip()
        except: return ""

    def manual_connect(self):
        port = self.entry_port.get().strip()
        if port:
            self.log(f"🔗 กำลังเชื่อมต่อ 127.0.0.1:{port} ...")
            subprocess.run(f"adb connect 127.0.0.1:{port}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.after(1000, self.refresh_devices)
            self.entry_port.delete(0, 'end')
        else:
            self.log("⚠️ กรุณาพิมพ์เลขพอร์ตก่อนกดเชื่อม!")

    # ======================================================
    # ฟังก์ชัน Sync ComboBox 
    # ======================================================
    def sync_combo(self, val, sender_id):
        sender_row = next((r for r in self.rows if r["id"] == sender_id), None)
        if not sender_row or sender_row["chk"].get() == 0:
            return

        for r in self.rows:
            if r["chk"].get() == 1:
                r["cb"].set(val)
                r["mode"].set(val)

    def refresh_devices(self):
        self.log("🔄 กำลังสแกนอุปกรณ์...")
        for widget in self.table_frame.winfo_children():
            widget.destroy()
        self.rows = []

        try:
            result = subprocess.run("adb devices", shell=True, capture_output=True, text=True)
            lines = result.stdout.strip().split('\n')[1:]
            devices = [line.split()[0] for line in lines if '\tdevice' in line and line.startswith("127.0.0.1")]
            
            def natural_keys(text):
                return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]
            devices.sort(key=natural_keys)

            if not devices:
                ctk.CTkLabel(self.table_frame, text="❌ ไม่พบอุปกรณ์ 127.0.0.1", text_color="#FC8181").pack(pady=20)
                return

            header = ctk.CTkFrame(self.table_frame, fg_color="transparent")
            header.pack(fill="x", pady=(0, 5))
            self.chk_all = ctk.CTkCheckBox(header, text="Select All", font=("Arial", 12, "bold"), fg_color="#2CC985", command=self.toggle_all)
            self.chk_all.pack(side="left", padx=5)
            self.chk_all.select()

            for i, d in enumerate(devices, 1):
                row_frame = ctk.CTkFrame(self.table_frame, corner_radius=5, height=40, fg_color="#2B2B2B")
                row_frame.pack(fill="x", pady=2, padx=2)

                chk_var = ctk.IntVar(value=1)
                ctk.CTkCheckBox(row_frame, text="", variable=chk_var, width=20, fg_color="#2CC985").pack(side="left", padx=(10, 5))

                ctk.CTkLabel(row_frame, text=f"จอ {i} ({d})", font=("Arial", 12, "bold"), width=160, anchor="w").pack(side="left")

                mode_var = ctk.StringVar(value="3. ยัดไอดีจากคิว + Auto (Drag & Drop)")
                modes = ["1. รีไอดี (Re-ID)", "2. ดึงข้อมูลเก็บ (Backup)", "3. ยัดไอดีจากคิว + Auto (Drag & Drop)", "4. ยัดไอดีจากคิว + เปิดเกม (เล่นเอง)"]
                
                cb = ctk.CTkOptionMenu(row_frame, values=modes, variable=mode_var, width=240, 
                                       fg_color="#2CC985", button_color="#22543D", button_hover_color="#1E4E38",
                                       command=lambda val, dev_id=d: self.sync_combo(val, dev_id))
                cb.pack(side="left", padx=10)

                entry_file = ctk.CTkEntry(row_frame, placeholder_text="ชื่อไอดี (ใช้โหมด 2)", width=120)
                entry_file.pack(side="left", padx=5)

                lbl_status = ctk.CTkLabel(row_frame, text="🟢 พร้อม", text_color="gray", width=150, anchor="w")
                lbl_status.pack(side="left", padx=10)

                self.rows.append({
                    "id": d,
                    "chk": chk_var,
                    "mode": mode_var,
                    "cb": cb,  
                    "entry": entry_file,
                    "status": lbl_status
                })

            self.log(f"✅ โหลดตารางเสร็จสิ้น ({len(devices)} เครื่อง)")

        except Exception as e:
            self.log(f"❌ Error: {e}")

    def toggle_all(self):
        val = self.chk_all.get()
        for r in self.rows: r["chk"].set(val)

    def start_tasks(self):
        for r in self.rows:
            if r["chk"].get() == 1:
                dev = r["id"]
                mode = r["mode"].get()
                filename = r["entry"].get().strip()
                lbl = r["status"]

                if "Backup" in mode and not filename:
                    lbl.configure(text="❌ ลืมใส่ชื่อไฟล์!", text_color="#FC8181")
                    continue

                self.stop_events[dev] = threading.Event()

                lbl.configure(text="⏳ กำลังทำงาน...", text_color="#F6E05E")
                threading.Thread(target=self.worker_thread, args=(dev, mode, filename, lbl), daemon=True).start()

    def worker_thread(self, dev, mode, filename, lbl_status):
        try:
            # ======================================================
            # 🟢 โหมด 3 ใหม่: ยัดไอดีจากคิว + ลูปออโต้
            # ======================================================
            if "3." in mode:
                while not self.file_q.empty():
                    if self.stop_events.get(dev) and self.stop_events[dev].is_set():
                        self.log(f"[{dev}] ⏹️ หยุดการทำงานตามคำสั่ง")
                        break

                    try: local_file = self.file_q.get_nowait()
                    except queue.Empty: break
                    
                    file_basename = os.path.basename(local_file)
                    
                    self.after(0, lambda: self.lbl_queue_count.configure(text=f"ไฟล์ในคิว: {self.file_q.qsize()} ไฟล์"))
                    self.update_status(lbl_status, f"⏳ เริ่มทำ: {file_basename}", "#F6E05E")
                    
                    # 1. ยัดไฟล์
                    self.adb_cmd(f"am force-stop {GAME_PKG}", dev)
                    self.adb_cmd(f"su -c 'rm -rf /data/data/{GAME_PKG}/shared_prefs/*'", dev)
                    
                    game_path = f"/data/data/{GAME_PKG}/shared_prefs/{GAME_PREF_FILE}"
                    temp_sd = f"{TEMP_SD_PATH}/temp_queue.xml"

                    self.adb_cmd(f"mkdir -p {TEMP_SD_PATH}", dev)
                    subprocess.run(f'adb -s {dev} push "{local_file}" {temp_sd}', shell=True, stdout=subprocess.DEVNULL)
                    
                    self.adb_cmd(f"su -c 'cp {temp_sd} {game_path}'", dev)
                    self.adb_cmd(f"su -c 'chmod 777 {game_path}'", dev)
                    self.adb_cmd(f"rm {temp_sd}", dev)

                    # 2. เปิดเกม
                    self.adb_cmd(f"monkey -p {GAME_PKG} -c android.intent.category.LAUNCHER 1", dev)
                    self.log(f"[{dev}] 📂 ยัดไอดี {file_basename} และเปิดเกมแล้ว")

                    # 3. ลูปมอนิเตอร์หน้าจอ
                    monitor_timeout = 240 # รอสูงสุดประมาณ 60 วินาที ต่อการเช็ค
                    done_this_file = False
                    
                    for _ in range(monitor_timeout):
                        if self.stop_events.get(dev) and self.stop_events[dev].is_set():
                            break

                        cap = screencap_from_device(dev)
                        if cap is None:
                            time.sleep(1)
                            continue
                        
                        # ==============================================
                        # 💎 เช็ค Gem: สเต็ปเคลียร์รายวัน
                        # ==============================================
                        if ImgSearchADB(cap, "gem.png"):
                            self.log(f"[{dev}] 💎 เจอ gem.png -> เริ่มสเต็ปเคลียร์รายวัน")
                            
                            # 1. ★ ดักรอ claim.png ก่อน (รอสูงสุด 10 วินาที เพราะมันเด้งช้า) ★
                            self.log(f"[{dev}] ดักรอป๊อปอัป claim.png (10 วิ)...")
                            for _ in range(10):
                                cap_claim = screencap_from_device(dev)
                                if cap_claim is None:
                                    time.sleep(1)
                                    continue
                                
                                pts_claim = ImgSearchADB(cap_claim, "claim.png")
                                if not pts_claim: 
                                    pts_claim = ImgSearchADB(cap_claim, "Claim.png")
                                    
                                if pts_claim:
                                    self.log(f"[{dev}] เจอ claim.png -> กดรับ")
                                    self.adb_cmd(f"input tap {pts_claim[0][0]} {pts_claim[0][1]}", dev)
                                    time.sleep(1.5)
                                    
                                    # ค้นหา x.png หรือ x2.png เพื่อปิดป๊อปอัป
                                    cap_x = screencap_from_device(dev)
                                    pts_x = ImgSearchADB(cap_x, "x.png")
                                    if not pts_x:
                                        pts_x = ImgSearchADB(cap_x, "x2.png")
                                        
                                    if pts_x:
                                        self.adb_cmd(f"input tap {pts_x[0][0]} {pts_x[0][1]}", dev)
                                        time.sleep(1)
                                    break # กด claim และ x เสร็จแล้ว ให้ออกจากลูปรอทันที
                                time.sleep(1) # ถ้ายังไม่เด้ง รอ 1 วิแล้วหาใหม่

                            # 2. ★ หน้าจอโล่งแล้ว ค่อยมาค้นหา v.png และกดจนกว่าจะเจอ v2.png ★
                            self.log(f"[{dev}] ค้นหา v.png และรอ v2.png ...")
                            v2_found = False
                            for _ in range(15): # วนหาซัก 15 รอบ
                                cap_v = screencap_from_device(dev)
                                if cap_v is None:
                                    time.sleep(1)
                                    continue
                                
                                pts_v2 = ImgSearchADB(cap_v, "v2.png")
                                if pts_v2:
                                    self.log(f"[{dev}] เจอ v2.png -> กดที่รูป")
                                    self.adb_cmd(f"input tap {pts_v2[0][0]} {pts_v2[0][1]}", dev)
                                    v2_found = True
                                    time.sleep(2) # รอให้หน้าจอถัดไปโหลด
                                    break
                                
                                pts_v = ImgSearchADB(cap_v, "v.png")
                                if pts_v:
                                    self.adb_cmd(f"input tap {pts_v[0][0]} {pts_v[0][1]}", dev)
                                
                                time.sleep(1)

                            # 3. ★ รอและดำเนินการหน้า daily.png (หลังจากกด v2.png แล้ว) ★
                            if v2_found:
                                self.log(f"[{dev}] รอโหลดป๊อปอัป daily.png ...")
                                for _ in range(10): # ดักรอ daily.png สูงสุด 10 วิ
                                    cap_daily = screencap_from_device(dev)
                                    if cap_daily is None:
                                        time.sleep(1)
                                        continue
                                        
                                    if ImgSearchADB(cap_daily, "daily.png"):
                                        self.log(f"[{dev}] เจอ daily.png -> กด 8 จุด")
                                        points = [
                                            (127, 525), (223, 528), (313, 527), (418, 527),
                                            (131, 669), (224, 669), (320, 669), (410, 668)
                                        ]
                                        for px, py in points:
                                            self.adb_cmd(f"input tap {px} {py}", dev)
                                            time.sleep(0.2)
                                        
                                        time.sleep(1)
                                        
                                        # ค้นหา spec.png
                                        cap_spec = screencap_from_device(dev)
                                        pts_spec = ImgSearchADB(cap_spec, "spec.png")
                                        if pts_spec:
                                            self.log(f"[{dev}] เจอ spec.png -> กดที่รูป")
                                            self.adb_cmd(f"input tap {pts_spec[0][0]} {pts_spec[0][1]}", dev)
                                            time.sleep(2)
                                            
                                            # รอหาหน้า spec2.png
                                            for _ in range(5):
                                                cap_spec2 = screencap_from_device(dev)
                                                if ImgSearchADB(cap_spec2, "spec2.png"):
                                                    self.log(f"[{dev}] เจอ spec2.png -> กด 8 จุด (รอบสอง)")
                                                    for px, py in points:
                                                        self.adb_cmd(f"input tap {px} {py}", dev)
                                                        time.sleep(0.2)
                                                    break
                                                time.sleep(1)
                                        break # ทำสเต็ป daily.png เสร็จแล้ว ให้ออกจากลูปรอทันที
                                    
                                    time.sleep(1)

                            # 4. เสร็จสิ้นกระบวนการทั้งหมด ปิดเกมและข้ามไปไฟล์ถัดไป
                            self.log(f"[{dev}] ✅ จบไอดี (เคลียร์เรียบร้อย) -> ปิดเกมและข้ามไปไฟล์ต่อไป!")
                            self.adb_cmd(f"am force-stop {GAME_PKG}", dev)
                            done_this_file = True
                            break # หลุดออกจาก for loop มอนิเตอร์หน้าจอ ไปดึงไฟล์คิวอันใหม่
                        # --- เช็ค guest ---
                        if ImgSearchADB(cap, "glogin.png"):
                            # 1. เช็ค ok.png ก่อนตามเงื่อนไข
                            pts_ok = ImgSearchADB(cap, "ok.png")
                            pts_ok2 = ImgSearchADB(cap, "ok2.png")
                            if pts_ok:
                                self.log(f"[{dev}] เจอ ok.png พร้อม login.png -> กด ok.png ก่อน")
                                self.adb_cmd(f"input tap {pts_ok[0][0]} {pts_ok[0][1]}", dev)
                                time.sleep(1.5) # หน่วงเวลารอแอนิเมชันหลังกด ok
                            elif pts_ok2:
                                self.log(f"[{dev}] เจอ ok2.png พร้อม login.png -> กด ok2.png ก่อน")
                                self.adb_cmd(f"input tap {pts_ok2[0][0]} {pts_ok2[0][1]}", dev)
                                time.sleep(1.5) # หน่วงเวลารอแอนิเมชันหลังกด
                        # --- เช็ค Login ---
                        if ImgSearchADB(cap, "login.png"):
                            self.log(f"[{dev}] เจอ login.png -> กด 3 ตำแหน่ง")
                            self.adb_cmd("input tap 505 178", dev)
                            time.sleep(0.5)
                            self.adb_cmd("input tap 502 351", dev)
                            time.sleep(0.5)
                            self.adb_cmd("input tap 503 440", dev)
                            time.sleep(0.5)
                            
                            # เช็ค agree.png 
                            cap_agree = screencap_from_device(dev)
                            pts_agree = ImgSearchADB(cap_agree, "agree.png")
                            if pts_agree:
                                self.adb_cmd(f"input tap {pts_agree[0][0]} {pts_agree[0][1]}", dev)
                                self.log(f"[{dev}] กดรูป agree.png")
                            else:
                                self.adb_cmd("input tap 208 520", dev)
                                self.log(f"[{dev}] กดตำแหน่ง (208, 520) แทน agree")
                            
                            time.sleep(2)
                            continue 
                        
                    
                        
                    if not done_this_file:
                        self.log(f"[{dev}] ⚠️ หมดเวลา/ไม่เจอ Claim สำหรับไอดี {file_basename}")

                if not self.stop_events.get(dev) or not self.stop_events[dev].is_set():
                    self.update_status(lbl_status, "✅ ทำงานคิวเสร็จสิ้น", "#68D391")
                    self.log(f"[{dev}] 🎉 ไฟล์ในคิวหมดแล้ว!")
                return

            # ======================================================
            # โหมด 1: รีไอดี
            # ======================================================
            elif "1." in mode:
                self.adb_cmd(f"am force-stop {GAME_PKG}", dev)
                path = f"/data/data/{GAME_PKG}/shared_prefs/{GAME_PREF_FILE}"
                self.adb_cmd(f"su -c 'rm {path}'", dev)
                self.adb_cmd(f"monkey -p {GAME_PKG} -c android.intent.category.LAUNCHER 1", dev)
                self.update_status(lbl_status, "✅ รีไอดี & เปิดเกมแล้ว", "#68D391")
                self.log(f"[{dev}] ♻️ รีไอดีเสร็จสิ้น")

# ======================================================
            # โหมด 2: ดึงข้อมูลเก็บ (Backup) - โหมดเปิด Root ดึงไฟล์ (ดึงครั้งเดียวจบ)
            # ======================================================
            elif "2." in mode:
                self.log(f"[{dev}] 🔄 กำลังดึงไฟล์เซฟผ่าน Root...")
                
                # 1. ปิดเกมก่อนเพื่อไม่ให้ไฟล์ถูกล็อค
                self.adb_cmd(f"am force-stop {GAME_PKG}", dev)
                time.sleep(1) 
                
                game_path = f"/data/data/{GAME_PKG}/shared_prefs/trident.preferences.xml"
                temp_sd = f"{TEMP_SD_PATH}/temp_backup.xml"
                # แปลงเครื่องหมาย : ในตัวแปร dev ให้เป็น _ ก่อนนำไปตั้งชื่อไฟล์
                safe_dev = dev.replace(":", "_")
                temp_local = f"{LOCAL_BACKUP_PATH}/temp_{safe_dev}_{int(time.time())}.xml"
                
                # 2. ใช้คำสั่ง Root (su) ดันไฟล์ออกมาที่ sdcard และปลดสิทธิ์ไฟล์
                self.adb_cmd(f"mkdir -p {TEMP_SD_PATH}", dev)
                self.adb_cmd(f"su -c 'cp {game_path} {temp_sd}'", dev)
                self.adb_cmd(f"su -c 'chmod 777 {temp_sd}'", dev) 
                
                time.sleep(1) # หน่วงเวลาให้ระบบเขียนไฟล์เสร็จ
                
                # 3. ดึงไฟล์เข้าคอมพิวเตอร์
                subprocess.run(f'adb -s {dev} pull {temp_sd} "{temp_local}"', shell=True, stdout=subprocess.DEVNULL)
                self.adb_cmd(f"rm {temp_sd}", dev) # ลบไฟล์ชั่วคราวทิ้ง

                # 4. เปลี่ยนชื่อไฟล์ตามที่กรอกในช่อง UI แทนการหา member_id
                # 4. เปลี่ยนชื่อไฟล์ตามที่กรอกในช่อง UI และรันตัวเลขต่อท้าย
                if os.path.exists(temp_local) and os.path.getsize(temp_local) > 0:
                    try:
                        # ใช้ self.file_lock เพื่อให้แต่ละจอต่อคิวกันนับเลข (ป้องกันเลขซ้ำถ้ากดพร้อมกัน)
                        with self.file_lock:
                            counter = 1
                            while True:
                                # สร้างชื่อไฟล์ เช่น ID_1.xml
                                final_filename = f"{LOCAL_BACKUP_PATH}/{filename}_{counter}.xml"
                                
                                # เช็คว่ามีไฟล์ชื่อนี้หรือยัง ถ้ายังไม่มีให้ออกจากลูปเพื่อใช้ชื่อนี้
                                if not os.path.exists(final_filename):
                                    break
                                # ถ้ามีแล้ว ให้บวกเลขเพิ่มไปเรื่อยๆ
                                counter += 1
                                
                            # เปลี่ยนชื่อไฟล์ชั่วคราวเป็นชื่อไฟล์จริงที่ได้จากการรันเลข
                            os.rename(temp_local, final_filename)
                            
                        self.update_status(lbl_status, f"✅ Backup -> {filename}_{counter}", "#68D391")
                        self.log(f"[{dev}] 💾 ดึงข้อมูลสำเร็จ: {filename}_{counter}.xml")
                        
                    except Exception as e:
                        self.log(f"[{dev}] Error Saving File: {e}")
                else:
                    self.update_status(lbl_status, "❌ ดึงไฟล์ล้มเหลว", "#FC8181")
                    self.log(f"[{dev}] ❌ ไม่พบไฟล์เซฟ (เช็คสิทธิ์ Root หรือเกมอาจจะยังไม่สร้างไฟล์)")
            # ======================================================
            # โหมด 4: เปิดเกมเฉยๆ (เปิดทีละ 1 ไอดีต่อการกด Start 1 ครั้ง)
            # ======================================================
            elif "4." in mode:
                # เปลี่ยนจาก while เป็น if เพื่อให้ทำแค่ 1 ไฟล์แล้วหยุดรอรอบต่อไป
                if not self.file_q.empty():
                    if self.stop_events.get(dev) and self.stop_events[dev].is_set():
                        self.log(f"[{dev}] ⏹️ หยุดการทำงานตามคำสั่ง")
                        return

                    try: 
                        local_file = self.file_q.get_nowait()
                    except queue.Empty: 
                        return
                    
                    file_basename = os.path.basename(local_file)
                    self.after(0, lambda: self.lbl_queue_count.configure(text=f"ไฟล์ในคิว: {self.file_q.qsize()} ไฟล์"))
                    self.update_status(lbl_status, f"⏳ กำลังเปิด: {file_basename}", "#F6E05E")

                    # 1. ยัดไฟล์
                    self.adb_cmd(f"am force-stop {GAME_PKG}", dev)
                    self.adb_cmd(f"su -c 'rm -rf /data/data/{GAME_PKG}/shared_prefs/*'", dev)
                    
                    game_path = f"/data/data/{GAME_PKG}/shared_prefs/{GAME_PREF_FILE}"
                    temp_sd = f"{TEMP_SD_PATH}/temp_queue.xml"

                    self.adb_cmd(f"mkdir -p {TEMP_SD_PATH}", dev)
                    subprocess.run(f'adb -s {dev} push "{local_file}" {temp_sd}', shell=True, stdout=subprocess.DEVNULL)
                    
                    self.adb_cmd(f"su -c 'cp {temp_sd} {game_path}'", dev)
                    self.adb_cmd(f"su -c 'chmod 777 {game_path}'", dev)
                    self.adb_cmd(f"rm {temp_sd}", dev)

                    # 2. เปิดเกม
                    self.adb_cmd(f"monkey -p {GAME_PKG} -c android.intent.category.LAUNCHER 1", dev)
                    self.log(f"[{dev}] 📂 เปิดไอดี {file_basename} สำเร็จ! (ถ้าจะเล่นไอดีต่อไปให้กดเริ่มใหม่)")
                    self.update_status(lbl_status, f"🎮 เปิดสำเร็จ: {file_basename}", "#68D391")
                    
                    # จบการทำงานของ Thread นี้ทันที ปล่อยให้ผู้ใช้เล่นเอง
                else:
                    self.update_status(lbl_status, "✅ ไม่มีไฟล์ในคิวแล้ว", "#68D391")
                    self.log(f"[{dev}] 🎉 ไฟล์ในคิวหมดแล้ว!")

        except Exception as e:
            self.update_status(lbl_status, "❌ Error!", "#FC8181")
            self.log(f"[{dev}] Error: {e}")

    def update_status(self, label, text, color):
        self.after(0, lambda: label.configure(text=text, text_color=color))

    def stop_games(self):
        self.log("🛑 กำลังสั่งหยุดการทำงานและปิดเกม...")
        for r in self.rows:
            if r["chk"].get() == 1:
                dev = r["id"]
                if dev in self.stop_events:
                    self.stop_events[dev].set()
                
                threading.Thread(target=lambda d=dev: self.adb_cmd(f"am force-stop {GAME_PKG}", d), daemon=True).start()
                r["status"].configure(text="⛔ หยุดการทำงานแล้ว", text_color="#A0AEC0")

if __name__ == "__main__":
    app = LineIdleBot()
    app.mainloop()