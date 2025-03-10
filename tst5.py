import cv2
import easyocr
import re
import tkinter as tk
from tkinter import ttk, messagebox
import pyodbc
from collections import defaultdict
import threading
from datetime import datetime

class PlakaUygulamasi(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MSSQL Entegreli Plaka Tanıma Sistemi")
        self.geometry("1000x700")
        
        # Veritabanı bağlantısı
        self.conn = self.create_connection()
        
        # GUI Bileşenleri
        self.kamera_frame = ttk.LabelFrame(self, text="Kamera Yönetimi")
        self.kamera_frame.pack(pady=10, padx=10, fill=tk.X)
        
        self.tarama_btn = ttk.Button(self.kamera_frame, 
                                   text="Kamera Tara", 
                                   command=self.kamera_tara)
        self.tarama_btn.pack(side=tk.LEFT, padx=5)
        
        self.kamera_combobox = ttk.Combobox(self.kamera_frame, 
                                          width=30, 
                                          state='readonly')
        self.kamera_combobox.pack(side=tk.LEFT, padx=5)
        self.kamera_combobox.bind('<<ComboboxSelected>>', self.kamera_secildi)
        
        # Görüntü Paneli
        self.video_label = ttk.Label(self)
        self.video_label.pack(pady=10)
        
        # Plaka Bilgi Paneli
        self.plaka_frame = ttk.LabelFrame(self, text="Plaka Bilgileri")
        self.plaka_frame.pack(fill=tk.BOTH, expand=True, padx=10)
        
        self.plaka_text = ttk.Label(self.plaka_frame, 
                                  text="", 
                                  font=('Arial', 24, 'bold'))
        self.plaka_text.pack(pady=20)
        
        self.durum_label = ttk.Label(self.plaka_frame, 
                                   text="Durum: Hazır", 
                                   font=('Arial', 12))
        self.durum_label.pack()
        
        # Sistem Değişkenleri
        self.aktif_kamera = None
        self.kamera_listesi = []
        self.is_running = False
        self.plaka_sayaclari = defaultdict(int)
        self.toplam_deneme = 0
        
        # OCR ve Cascade
        self.reader = easyocr.Reader(['tr', 'en'])
        self.plate_cascade = cv2.CascadeClassifier('haarcascade_russian_plate_number.xml')

    def create_connection(self):
        try:
            return pyodbc.connect(
                "bDRIVER={SQL Server};"
                'SERVER=MERT;'
                'DATABASE=Plaka_Kontrol;'
                'Trusted_Connection=yes;'
            )
        except Exception as e:
            messagebox.showerror("Veritabanı Hatası",
                f"Hata: {str(e)}\nKontrol Edin:\n"
                "1. SQL Server çalışıyor mu?\n"
                "2. ODBC Driver 17 kurulu mu?\n"
                "3. Firewall ayarları")
            return None

    def kamera_tara(self):
        def tarama_islemi():
            self.kamera_listesi = []
            for i in range(3):
                cap = cv2.VideoCapture(i)
                if cap.read()[0]:
                    self.kamera_listesi.append(f"Kamera {i}")
                    cap.release()
            self.kamera_combobox['values'] = self.kamera_listesi
            if self.kamera_listesi:
                self.kamera_combobox.current(0)
                self.kamera_secildi()
        threading.Thread(target=tarama_islemi, daemon=True).start()

    def kamera_secildi(self, event=None):
        if self.is_running:
            self.stop_akim()
        self.aktif_kamera = self.kamera_combobox.current()
        self.start_akim()

    def start_akim(self):
        self.cap = cv2.VideoCapture(self.aktif_kamera)
        if not self.cap.isOpened():
            messagebox.showerror("Hata", "Kamera açılamadı!")
            return
        self.is_running = True
        threading.Thread(target=self.video_loop, daemon=True).start()

    def video_loop(self):
        while self.is_running:
            ret, frame = self.cap.read()
            if not ret:
                break
            
            # Plaka Tespiti
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            plates = self.plate_cascade.detectMultiScale(gray, 1.1, 5)
            
            current_plaka = None
            for (x, y, w, h) in plates:
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                plate_roi = gray[y:y+h, x:x+w]
                
                # Görüntü İyileştirme
                plate_roi = cv2.resize(plate_roi, None, fx=2, fy=2, 
                                     interpolation=cv2.INTER_CUBIC)
                plate_roi = cv2.medianBlur(plate_roi, 3)
                
                # OCR Okuma
                results = self.reader.readtext(plate_roi, detail=0, paragraph=False)
                if results:
                    cleaned_text = re.sub(r'[^A-Z0-9]', '', ''.join(results).upper())
                    if len(cleaned_text) == 8 and re.match(r'^[A-Z0-9]{8}$', cleaned_text):
                        current_plaka = cleaned_text
                        self.plaka_sayaclari[cleaned_text] += 1
                        self.toplam_deneme += 1

                        # Veritabanı Kayıt
                        if self.plaka_sayaclari[cleaned_text] == 4:
                            self.plaka_kaydet(cleaned_text)
                            self.plaka_sayaclari.clear()
                            self.toplam_deneme = 0

            # 40 Deneme Kuralı
            if self.toplam_deneme >= 40:
                if not any(count >= 4 for count in self.plaka_sayaclari.values()):
                    self.plaka_text.config(text="PLAKA BELİRLENEMEDİ")
                    self.plaka_sayaclari.clear()
                    self.toplam_deneme = 0

            # GUI Güncelleme
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            photo = tk.PhotoImage(data=cv2.imencode('.png', frame)[1].tobytes())
            self.video_label.config(image=photo)
            self.video_label.image = photo
            
            if current_plaka:
                self.plaka_text.config(text=current_plaka)
                self.durum_label.config(text=f"Okuma: {self.plaka_sayaclari[current_plaka]}/4 | Deneme: {self.toplam_deneme}/40")
            else:
                self.durum_label.config(text=f"Deneme: {self.toplam_deneme}/40")

    def plaka_kaydet(self, plaka):
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO Plakalar (PlakaNumarasi, KayitTarihi) VALUES (?, ?)",
                (plaka, datetime.now())
            )
            self.conn.commit()
            messagebox.showinfo("Başarılı", f"{plaka} veritabanına kaydedildi!")
        except Exception as e:
            messagebox.showerror("Hata", f"Kayıt başarısız: {str(e)}")

    def stop_akim(self):
        self.is_running = False
        if self.cap:
            self.cap.release()
        self.plaka_text.config(text="")
        self.durum_label.config(text="Durum: Durduruldu")

    def on_closing(self):
        self.stop_akim()
        if self.conn:
            self.conn.close()
        self.destroy()

if __name__ == "__main__":
    app = PlakaUygulamasi()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()