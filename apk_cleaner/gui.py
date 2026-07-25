#!/usr/bin/env python3
"""
gui.py — APK Cleaner Native macOS GUI (v4.0)
Giao diện macOS Native sử dụng Tkinter cao cấp với custom canvas widgets,
mang lại trải nghiệm mượt mà, hiện đại và không phụ thuộc web.
"""

import sys
import os
import threading
import queue
import shutil
import subprocess
import logging
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox

_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import config
from logger import setup_logger
from decompiler import check_prerequisites, decompile_apk
from cleaner import clean_source_code
from recompiler import recompile_apk, sign_apk

# ══════════════════════════════════════════════
# DESIGN SYSTEM (THEME & STYLE)
# ══════════════════════════════════════════════
THEME = {
    "bg":          "#0B0D11",  # Deep dark background
    "card":        "#131720",  # Card surface color
    "card_hover":  "#1A1F2B",  # Hovered card
    "border":      "#252B37",  # Border color
    "text":        "#F3F4F6",  # Primary white text
    "text_muted":  "#9CA3AF",  # Secondary gray text
    "text_dark":   "#4B5563",  # Muted text
    "primary":     "#8B5CF6",  # Violet primary accent
    "primary_h":   "#A78BFA",  # Light violet hover
    "primary_g":   "#F472B6",  # Secondary accent (pink)
    "success":     "#10B981",  # Green success
    "warning":     "#F59E0B",  # Orange warning
    "error":       "#EF4444",  # Red error
}

FONTS = {
    "title":       ("SF Pro Display", 22, "bold"),
    "h2":          ("SF Pro Text", 15, "bold"),
    "body":        ("SF Pro Text", 12),
    "body_bold":   ("SF Pro Text", 12, "bold"),
    "small":       ("SF Pro Text", 10),
    "mono":        ("SF Mono", 11),
}


# ══════════════════════════════════════════════
# MODERN CUSTOM WIDGETS
# ══════════════════════════════════════════════

class ModernButton(tk.Canvas):
    """Nút bấm bo góc, có hiệu ứng hover."""
    def __init__(self, parent, text, command, bg=THEME["primary"], hover_bg=THEME["primary_h"], fg=THEME["text"], width=160, height=42, font=FONTS["body_bold"]):
        super().__init__(parent, width=width, height=height, bg=parent["bg"], highlightthickness=0, cursor="hand2")
        self.command = command
        self.bg = bg
        self.hover_bg = hover_bg
        self.fg = fg
        self.width = width
        self.height = height
        self.text = text
        self.font = font
        self._state = "normal"
        self._draw(self.bg)
        
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def set_state(self, state):
        self._state = state
        if state == "disabled":
            self.configure(cursor="arrow")
            self._draw("#252B37", text_color=THEME["text_dark"])
        else:
            self.configure(cursor="hand2")
            self._draw(self.bg)

    def _draw(self, fill_color, text_color=None):
        self.delete("all")
        if text_color is None:
            text_color = self.fg
        r = 10  # Corner radius
        points = [
            r, 0, self.width-r, 0,
            self.width, 0, self.width, r,
            self.width, self.height-r, self.width, self.height,
            self.width-r, self.height, r, self.height,
            0, self.height, 0, self.height-r,
            0, r, 0, 0
        ]
        self.create_polygon(points, fill=fill_color, smooth=True, outline="")
        self.create_text(self.width//2, self.height//2, text=self.text, fill=text_color, font=self.font)

    def _on_enter(self, _):
        if self._state != "disabled":
            self._draw(self.hover_bg)

    def _on_leave(self, _):
        if self._state != "disabled":
            self._draw(self.bg)

    def _on_click(self, _):
        if self._state != "disabled" and self.command:
            self.command()


class ModernToggle(tk.Canvas):
    """Switch toggle iOS style."""
    def __init__(self, parent, var, width=42, height=22):
        super().__init__(parent, width=width, height=height, bg=parent["bg"], highlightthickness=0, cursor="hand2")
        self.var = var
        self.width = width
        self.height = height
        self.var.trace_add("write", lambda *_: self._draw())
        self.bind("<Button-1>", lambda _: self._toggle())
        self._draw()

    def _toggle(self):
        self.var.set(not self.var.get())

    def _draw(self):
        self.delete("all")
        on = self.var.get()
        bg_color = THEME["primary"] if on else THEME["border"]
        
        # Track
        r = self.height // 2
        points = [
            r, 0, self.width-r, 0,
            self.width, 0, self.width, r,
            self.width, self.height-r, self.width, self.height,
            self.width-r, self.height, r, self.height,
            0, self.height, 0, self.height-r,
            0, r, 0, 0
        ]
        self.create_polygon(points, fill=bg_color, smooth=True, outline="")
        
        # Knob
        knob_r = (self.height - 6) // 2
        cx = self.width - r if on else r
        cy = self.height // 2
        self.create_oval(cx - knob_r, cy - knob_r, cx + knob_r, cy + knob_r, fill="#ffffff", outline="")


class ModernDropZone(tk.Canvas):
    """Khu vực kéo thả file hoặc click để chọn file."""
    def __init__(self, parent, on_file_selected, width=632, height=180):
        super().__init__(parent, width=width, height=height, bg=THEME["card"], highlightthickness=1, highlightbackground=THEME["border"], cursor="hand2")
        self.width = width
        self.height = height
        self.on_file_selected = on_file_selected
        self.filepath = None
        
        self.bind("<Button-1>", lambda _: self._browse())
        self.bind("<Enter>", lambda _: self._draw(hover=True))
        self.bind("<Leave>", lambda _: self._draw(hover=False))
        self._draw()

    def set_file(self, path):
        self.filepath = path
        self._draw()

    def clear(self):
        self.filepath = None
        self._draw()

    def _draw(self, hover=False):
        self.delete("all")
        bg_col = THEME["card_hover"] if hover else THEME["card"]
        bd_col = THEME["primary"] if hover or self.filepath else THEME["border"]
        
        # Draw background card
        r = 14
        points = [
            r, 0, self.width-r, 0,
            self.width, 0, self.width, r,
            self.width, self.height-r, self.width, self.height,
            self.width-r, self.height, r, self.height,
            0, self.height, 0, self.height-r,
            0, r, 0, 0
        ]
        self.create_polygon(points, fill=bg_col, smooth=True, outline="")
        
        # Subtle border glow
        self.configure(highlightbackground=bd_col)

        if self.filepath:
            p = Path(self.filepath)
            size_mb = p.stat().st_size / (1024*1024)
            self.create_text(self.width//2, self.height//2 - 22, text="📦", font=("Apple Color Emoji", 32))
            self.create_text(self.width//2, self.height//2 + 16, text=p.name, font=FONTS["h2"], fill=THEME["text"])
            self.create_text(self.width//2, self.height//2 + 38, text=f"{size_mb:.1f} MB  •  Bấm để thay đổi file", font=FONTS["small"], fill=THEME["text_muted"])
        else:
            self.create_text(self.width//2, self.height//2 - 20, text="📂", font=("Apple Color Emoji", 30))
            self.create_text(self.width//2, self.height//2 + 18, text="Chọn file APK từ máy tính", font=FONTS["h2"], fill=THEME["text"])
            self.create_text(self.width//2, self.height//2 + 40, text="Hỗ trợ phân tích, dọn dẹp Ads và tự ký số", font=FONTS["small"], fill=THEME["text_muted"])

    def _browse(self):
        p = filedialog.askopenfilename(
            title="Chọn file APK",
            filetypes=[("Android Package", "*.apk"), ("Tất cả file", "*.*")]
        )
        if p:
            self.set_file(p)
            self.on_file_selected(p)


class StepIndicator(tk.Canvas):
    """Thanh chỉ báo các bước xử lý (1 -> 2 -> 3 -> 4)"""
    def __init__(self, parent, width=320, height=40):
        super().__init__(parent, width=width, height=height, bg=parent["bg"], highlightthickness=0)
        self.width = width
        self.height = height
        self.current_step = 0
        self._draw()

    def set_step(self, step):
        self.current_step = step
        self._draw()

    def _draw(self):
        self.delete("all")
        steps = ["Chọn", "Cài đặt", "Chạy", "Kết quả"]
        num_steps = len(steps)
        cy = self.height // 2
        
        # Draw connector lines
        pad = 24
        span = (self.width - 2*pad) / (num_steps - 1)
        
        for i in range(num_steps - 1):
            x1 = pad + i * span
            x2 = pad + (i + 1) * span
            line_col = THEME["success"] if i < self.current_step else THEME["border"]
            self.create_line(x1, cy, x2, cy, fill=line_col, width=2)

        # Draw step circles
        for i, label in enumerate(steps):
            cx = pad + i * span
            
            if i < self.current_step:
                # Completed
                self.create_oval(cx-12, cy-12, cx+12, cy+12, fill=THEME["success"], outline="")
                self.create_text(cx, cy, text="✓", fill="#ffffff", font=("SF Pro Text", 10, "bold"))
            elif i == self.current_step:
                # Current active
                self.create_oval(cx-12, cy-12, cx+12, cy+12, fill=THEME["primary"], outline="")
                self.create_text(cx, cy, text=str(i+1), fill="#ffffff", font=("SF Pro Text", 10, "bold"))
            else:
                # Pending
                self.create_oval(cx-12, cy-12, cx+12, cy+12, fill=THEME["border"], outline="")
                self.create_text(cx, cy, text=str(i+1), fill=THEME["text_muted"], font=("SF Pro Text", 10))
                
            # Text label
            self.create_text(cx, cy + 22, text=label, fill=THEME["text"] if i == self.current_step else THEME["text_muted"], font=FONTS["small"])


# ══════════════════════════════════════════════
# MAIN APP CLASS
# ══════════════════════════════════════════════

class APKCleanerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("APK Cleaner")
        self.configure(bg=THEME["bg"])
        self.resizable(False, False)
        
        # Center on screen safely using Tcl helper
        self.geometry("680x700")
        try:
            self.eval('tk::PlaceWindow . center')
        except Exception:
            pass

        # Force window to front and focus on macOS
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after(600, lambda: self.attributes("-topmost", False))

        # State Variables
        self.apk_path = ""
        self.var_ads = tk.BooleanVar(value=True)
        self.var_store = tk.BooleanVar(value=True)
        self.var_xml = tk.BooleanVar(value=True)
        self.var_keystore = tk.StringVar(value="")
        self.var_output = tk.StringVar(value=str(config.OUTPUT_DIR))
        self.pipeline_thread = None
        self.log_queue = queue.Queue()
        self.ui_queue = queue.Queue()
        self.is_running = False
        
        # Tools Status state
        self.tools_status = {"java": False, "apktool": False, "signer": False}

        # Setup Logging redirection
        self._setup_logger_override()

        # Build Layout
        self._build_header()
        
        # Main container for screens
        self.container = tk.Frame(self, bg=THEME["bg"])
        self.container.pack(fill="both", expand=True, padx=24, pady=16)

        # Screens dict
        self.screens = {}
        self.current_screen = None
        
        # Init screens
        self._init_screens()
        
        # Start event queue polling
        self._poll_logs()
        self._poll_ui()

        # Check tools status in background
        threading.Thread(target=self._check_prerequisites_bg, daemon=True).start()

        # Show screen 1
        self.show_screen("select")

    def _schedule_ui(self, func):
        self.ui_queue.put(func)

    def _poll_ui(self):
        while not self.ui_queue.empty():
            try:
                task = self.ui_queue.get_nowait()
                task()
            except queue.Empty:
                break
            except Exception as e:
                pass
        self.after(50, self._poll_ui)

    def _setup_logger_override(self):
        config.init_directories()
        self.logger = setup_logger(config.LOG_DIR, verbose=True)
        
        class QueueHandler(logging.Handler):
            def __init__(self, q):
                super().__init__()
                self.q = q
            def emit(self, r):
                self.q.put((r.levelname, r.getMessage()))
                
        qh = QueueHandler(self.log_queue)
        qh.setLevel(logging.DEBUG)
        self.logger.addHandler(qh)

    def _build_header(self):
        # Window Header Bar
        hdr = tk.Frame(self, bg=THEME["card"], height=60)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        
        # Left Title
        lbl = tk.Label(hdr, text="🧹 APK Cleaner", font=FONTS["title"], bg=THEME["card"], fg=THEME["text"])
        lbl.pack(side="left", padx=24)
        
        # Right Step Indicator
        self.step_ind = StepIndicator(hdr)
        self.step_ind.pack(side="right", padx=24, pady=10)

    def show_screen(self, name):
        if self.current_screen:
            self.screens[self.current_screen].pack_forget()
        
        self.current_screen = name
        self.screens[name].pack(fill="both", expand=True)
        
        # Update step indicator
        steps = {"select": 0, "settings": 1, "process": 2, "result": 3}
        self.step_ind.set_step(steps.get(name, 0))

    def _init_screens(self):
        # 1. SELECT SCREEN
        self.screens["select"] = tk.Frame(self.container, bg=THEME["bg"])
        self._build_select_screen(self.screens["select"])

        # 2. SETTINGS SCREEN
        self.screens["settings"] = tk.Frame(self.container, bg=THEME["bg"])
        self._build_settings_screen(self.screens["settings"])

        # 3. PROCESS SCREEN
        self.screens["process"] = tk.Frame(self.container, bg=THEME["bg"])
        self._build_process_screen(self.screens["process"])

        # 4. RESULT SCREEN
        self.screens["result"] = tk.Frame(self.container, bg=THEME["bg"])
        self._build_result_screen(self.screens["result"])

    # ══════════════════════════════════════════════
    # SCREEN 1: SELECT
    # ══════════════════════════════════════════════
    def _build_select_screen(self, parent):
        tk.Label(parent, text="Nhập file APK ứng dụng cần làm sạch", font=FONTS["h2"], bg=THEME["bg"], fg=THEME["text"]).pack(anchor="w", pady=(10, 10))

        # Drop Zone
        self.drop_zone = ModernDropZone(parent, self._on_apk_selected)
        self.drop_zone.pack(fill="x", pady=10)

        # Tools status card
        tk.Label(parent, text="Trạng thái công cụ hệ thống:", font=FONTS["small"], bg=THEME["bg"], fg=THEME["text_muted"]).pack(anchor="w", pady=(20, 4))
        
        status_card = tk.Frame(parent, bg=THEME["card"], bd=1, relief="flat", highlightbackground=THEME["border"], highlightthickness=1)
        status_card.pack(fill="x", pady=5)
        
        self.tool_labels = {}
        tools = [("java", "☕ Java SE Environment"), ("apktool", "🔧 APKTool decompiling engine"), ("signer", "🔑 Uber APK Signer engine")]
        for key, name in tools:
            f = tk.Frame(status_card, bg=THEME["card"], pady=8, padx=16)
            f.pack(fill="x")
            
            tk.Label(f, text=name, font=FONTS["body"], bg=THEME["card"], fg=THEME["text"]).pack(side="left")
            status_lbl = tk.Label(f, text="Đang kiểm tra...", font=FONTS["body_bold"], bg=THEME["card"], fg=THEME["warning"])
            status_lbl.pack(side="right")
            self.tool_labels[key] = status_lbl

        # Bottom Next button
        btn_frame = tk.Frame(parent, bg=THEME["bg"])
        btn_frame.pack(fill="x", side="bottom", pady=20)
        
        self.btn_next_select = ModernButton(btn_frame, "Tiếp tục  →", lambda: self.show_screen("settings"))
        self.btn_next_select.pack(side="right")
        self.btn_next_select.set_state("disabled")

    def _on_apk_selected(self, path):
        self.apk_path = path
        self._update_next_state()

    def _update_next_state(self):
        # Allow next only if tools are ready and apk is selected
        tools_ready = all(self.tools_status.values())
        if self.apk_path and tools_ready:
            self.btn_next_select.set_state("normal")
        else:
            self.btn_next_select.set_state("disabled")

    def _check_prerequisites_bg(self):
        from decompiler import check_java, download_tools
        java_ok = check_java()
        self.tools_status["java"] = java_ok
        self._update_tool_ui("java", java_ok, "Sẵn sàng" if java_ok else "Chưa cài đặt (Cần Java SDK)")

        if not config.APKTOOL_JAR.exists() or not config.SIGNER_JAR.exists():
            self._update_tool_ui("apktool", False, "Đang tải công cụ...")
            self._update_tool_ui("signer", False, "Đang tải công cụ...")
            download_tools()

        apktool_ok = config.APKTOOL_JAR.exists()
        self.tools_status["apktool"] = apktool_ok
        self._update_tool_ui("apktool", apktool_ok, "Sẵn sàng" if apktool_ok else "Thiếu file tools/apktool.jar")

        signer_ok = config.SIGNER_JAR.exists()
        self.tools_status["signer"] = signer_ok
        self._update_tool_ui("signer", signer_ok, "Sẵn sàng" if signer_ok else "Thiếu file tools/uber-apk-signer.jar")

        self._schedule_ui(self._update_next_state)

    def _update_tool_ui(self, key, ok, text):
        lbl = self.tool_labels[key]
        color = THEME["success"] if ok else THEME["error"]
        self._schedule_ui(lambda: lbl.configure(text=text, foreground=color))

    # ══════════════════════════════════════════════
    # SCREEN 2: SETTINGS
    # ══════════════════════════════════════════════
    def _build_settings_screen(self, parent):
        tk.Label(parent, text="Cài đặt tiến trình dọn dẹp", font=FONTS["h2"], bg=THEME["bg"], fg=THEME["text"]).pack(anchor="w", pady=(10, 10))

        # Main settings card
        card = tk.Frame(parent, bg=THEME["card"], bd=1, relief="flat", highlightbackground=THEME["border"], highlightthickness=1)
        card.pack(fill="x", pady=5)

        # Options
        options = [
            ("Vô hiệu hóa Ads SDK", "Tắt toàn bộ tiến trình quảng cáo Google Ads, Unity, FB...", self.var_ads),
            ("Chặn nhảy Google Play Store", "Chặn tự động mở link store tải ứng dụng rác, đánh giá", self.var_store),
            ("Quét và làm sạch XML", "Loại bỏ khai báo quảng cáo trong file AndroidManifest.xml", self.var_xml),
        ]
        
        for i, (title, desc, var) in enumerate(options):
            f = tk.Frame(card, bg=THEME["card"], pady=14, padx=16)
            f.pack(fill="x")
            
            # Left labels
            left = tk.Frame(f, bg=THEME["card"])
            left.pack(side="left", fill="x", expand=True)
            tk.Label(left, text=title, font=FONTS["body_bold"], bg=THEME["card"], fg=THEME["text"]).pack(anchor="w")
            tk.Label(left, text=desc, font=FONTS["small"], bg=THEME["card"], fg=THEME["text_muted"]).pack(anchor="w", pady=(2,0))
            
            # Right toggle
            ModernToggle(f, var).pack(side="right")
            
            if i < len(options) - 1:
                tk.Frame(card, bg=THEME["border"], height=1).pack(fill="x", padx=16)

        # Path Output Section
        tk.Label(parent, text="Đường dẫn đầu ra:", font=FONTS["small"], bg=THEME["bg"], fg=THEME["text_muted"]).pack(anchor="w", pady=(20, 4))
        
        out_f = tk.Frame(parent, bg=THEME["card"], bd=1, relief="flat", highlightbackground=THEME["border"], highlightthickness=1, pady=10, padx=16)
        out_f.pack(fill="x")
        
        entry = tk.Entry(out_f, textvariable=self.var_output, font=FONTS["body"], bg="#1B202B", fg=THEME["text"], insertbackground=THEME["text"], relief="flat", bd=6)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        def select_output_dir():
            p = filedialog.askdirectory(title="Chọn thư mục lưu file")
            if p: self.var_output.set(p)
            
        ModernButton(out_f, "Thay đổi", select_output_dir, bg=THEME["border"], hover_bg=THEME["card_hover"], fg=THEME["text_muted"], width=100, height=32, font=FONTS["small"]).pack(side="right", padx=(10,0))

        # Bottom buttons
        btn_frame = tk.Frame(parent, bg=THEME["bg"])
        btn_frame.pack(fill="x", side="bottom", pady=20)
        
        ModernButton(btn_frame, "← Quay lại", lambda: self.show_screen("select"), bg=THEME["border"], hover_bg=THEME["card_hover"], fg=THEME["text_muted"]).pack(side="left")
        ModernButton(btn_frame, "Bắt đầu xử lý ▶", self._start_pipeline).pack(side="right")

    # ══════════════════════════════════════════════
    # SCREEN 3: PROCESS
    # ══════════════════════════════════════════════
    def _build_process_screen(self, parent):
        tk.Label(parent, text="Tiến trình làm sạch và tối ưu hóa", font=FONTS["h2"], bg=THEME["bg"], fg=THEME["text"]).pack(anchor="w", pady=(10, 10))

        # Step indicator rows
        self.step_rows = []
        steps = [
            ("🔍 Kiểm tra prerequisites", "Xác nhận các công cụ Java/Jar đã sẵn sàng"),
            ("📦 Decompile mã nguồn", "Trích xuất bytecode SMALI và tài nguyên XML"),
            ("🧹 Clean mã nguồn & Manifest", "Quét và loại bỏ quảng cáo, chặn Play Store"),
            ("✍️ Rebuild & Ký số ứng dụng", "Đóng gói lại file APK và thực hiện ký số")
        ]
        
        card = tk.Frame(parent, bg=THEME["card"], bd=1, relief="flat", highlightbackground=THEME["border"], highlightthickness=1)
        card.pack(fill="x", pady=5)
        
        for i, (title, desc) in enumerate(steps):
            f = tk.Frame(card, bg=THEME["card"], pady=10, padx=16)
            f.pack(fill="x")
            
            # Left info
            left = tk.Frame(f, bg=THEME["card"])
            left.pack(side="left", fill="x", expand=True)
            tk.Label(left, text=title, font=FONTS["body_bold"], bg=THEME["card"], fg=THEME["text"]).pack(anchor="w")
            tk.Label(left, text=desc, font=FONTS["small"], bg=THEME["card"], fg=THEME["text_muted"]).pack(anchor="w")
            
            # Right state
            state_lbl = tk.Label(f, text="Đang chờ...", font=FONTS["body_bold"], bg=THEME["card"], fg=THEME["text_dark"])
            state_lbl.pack(side="right")
            
            self.step_rows.append(state_lbl)
            
            if i < len(steps) - 1:
                tk.Frame(card, bg=THEME["border"], height=1).pack(fill="x", padx=16)

        # Log details label
        tk.Label(parent, text="Nhật ký chi tiết:", font=FONTS["small"], bg=THEME["bg"], fg=THEME["text_muted"]).pack(anchor="w", pady=(14, 4))
        
        # Scrolled Text Box for logs
        log_frame = tk.Frame(parent, bg=THEME["card"], bd=1, relief="flat", highlightbackground=THEME["border"], highlightthickness=1)
        log_frame.pack(fill="both", expand=True, pady=5)
        
        scrollbar = tk.Scrollbar(log_frame)
        scrollbar.pack(side="right", fill="y")
        
        self.log_text = tk.Text(log_frame, yscrollcommand=scrollbar.set, bg="#0E121B", fg=THEME["text_muted"], relief="flat", highlightthickness=0, font=FONTS["mono"], height=10, padx=12, pady=12)
        self.log_text.pack(fill="both", expand=True)
        scrollbar.config(command=self.log_text.yview)

        # Colors tag mapping
        self.log_text.tag_configure("INFO", foreground=THEME["text_muted"])
        self.log_text.tag_configure("WARNING", foreground=THEME["warning"])
        self.log_text.tag_configure("ERROR", foreground=THEME["error"])
        self.log_text.tag_configure("SUCCESS", foreground=THEME["success"])

        # Bottom back button (disabled during execution)
        self.process_nav = tk.Frame(parent, bg=THEME["bg"])
        self.process_nav.pack(fill="x", side="bottom", pady=10)
        
        self.btn_back_proc = ModernButton(self.process_nav, "← Quay lại", lambda: self.show_screen("settings"), bg=THEME["border"], hover_bg=THEME["card_hover"], fg=THEME["text_muted"])
        self.btn_back_proc.pack(side="left")
        self.btn_back_proc.set_state("disabled")

    # ══════════════════════════════════════════════
    # SCREEN 4: RESULT
    # ══════════════════════════════════════════════
    def _build_result_screen(self, parent):
        self.res_icon = tk.Label(parent, text="✅", font=("Apple Color Emoji", 48), bg=THEME["bg"])
        self.res_icon.pack(pady=(20, 4))
        
        self.res_title = tk.Label(parent, text="Làm Sạch Thành Công!", font=FONTS["title"], bg=THEME["bg"], fg=THEME["success"])
        self.res_title.pack()

        # Stats frame
        self.stats_lbl = tk.Label(parent, text="Báo cáo kết quả chi tiết:", font=FONTS["small"], bg=THEME["bg"], fg=THEME["text_muted"])
        self.stats_lbl.pack(anchor="w", pady=(20, 4))
        
        self.stats_card = tk.Frame(parent, bg=THEME["card"], bd=1, relief="flat", highlightbackground=THEME["border"], highlightthickness=1)
        self.stats_card.pack(fill="x", pady=5)
        
        self.stat_widgets = {}
        stats_list = [
            ("scanned", "📂 Tổng số file SMALI quét:"),
            ("modified", "✏️ File bị sửa đổi:"),
            ("ads_blocked", "🚫 Phương thức Ads đã chặn:"),
            ("store_blocked", "🛍️ Link redirects Store đã chặn:"),
            ("xml_removed", "📄 Thuộc tính XML bị xóa:")
        ]
        for key, text in stats_list:
            f = tk.Frame(self.stats_card, bg=THEME["card"], pady=8, padx=16)
            f.pack(fill="x")
            tk.Label(f, text=text, font=FONTS["body"], bg=THEME["card"], fg=THEME["text"]).pack(side="left")
            val_lbl = tk.Label(f, text="0", font=FONTS["body_bold"], bg=THEME["card"], fg=THEME["primary"])
            val_lbl.pack(side="right")
            self.stat_widgets[key] = val_lbl

        # Output folder display
        tk.Label(parent, text="Vị trí file lưu trữ:", font=FONTS["small"], bg=THEME["bg"], fg=THEME["text_muted"]).pack(anchor="w", pady=(20, 4))
        
        out_box = tk.Frame(parent, bg=THEME["card"], bd=1, relief="flat", highlightbackground=THEME["border"], highlightthickness=1, pady=12, padx=16)
        out_box.pack(fill="x", pady=5)
        
        self.lbl_out_file = tk.Label(out_box, text="...", font=FONTS["body_bold"], bg=THEME["card"], fg=THEME["text"])
        self.lbl_out_file.pack(anchor="w")
        self.lbl_out_path = tk.Label(out_box, text="...", font=FONTS["small"], bg=THEME["card"], fg=THEME["text_muted"])
        self.lbl_out_path.pack(anchor="w", pady=(2, 0))

        # Bottom buttons
        btn_frame = tk.Frame(parent, bg=THEME["bg"])
        btn_frame.pack(fill="x", side="bottom", pady=20)
        
        ModernButton(btn_frame, "Xử lý file khác", self._reset_to_start, bg=THEME["border"], hover_bg=THEME["card_hover"], fg=THEME["text_muted"]).pack(side="left")
        
        def open_folder():
            folder = self.var_output.get() or str(config.OUTPUT_DIR)
            Path(folder).mkdir(parents=True, exist_ok=True)
            subprocess.run(["open", folder])
            
        ModernButton(btn_frame, "📁 Mở folder", open_folder).pack(side="right")

    # ══════════════════════════════════════════════
    # PIPELINE EXECUTION
    # ══════════════════════════════════════════════
    def _start_pipeline(self):
        if self.is_running:
            return
        self.is_running = True
        
        # Reset UI process state
        for lbl in self.step_rows:
            lbl.configure(text="Đang chờ...", foreground=THEME["text_dark"])
        self.log_text.delete("1.0", "end")
        self.btn_back_proc.set_state("disabled")
        
        self.show_screen("process")
        
        # Start execution in thread
        self.pipeline_thread = threading.Thread(target=self._run_pipeline_worker, daemon=True)
        self.pipeline_thread.start()

    def _set_step_state(self, step_idx, state_str, color):
        self._schedule_ui(lambda: self.step_rows[step_idx].configure(text=state_str, foreground=color))

    def _run_pipeline_worker(self):
        try:
            config.init_directories()
            apk = Path(self.apk_path)
            out = Path(self.var_output.get() or str(config.OUTPUT_DIR))
            tmp = config.TEMP_DIR
            rb = config.REBUILT_APK
            out.mkdir(parents=True, exist_ok=True)

            # Step 1: Precheck
            self._set_step_state(0, "Đang kiểm tra...", THEME["warning"])
            self.logger.info("── Bước 1/4: Kiểm tra prerequisites ──")
            if not check_prerequisites():
                self._set_step_state(0, "Thất bại ❌", THEME["error"])
                self._pipeline_failed("Thiếu các dependencies trong thư mục tools/")
                return
            self._set_step_state(0, "Xong ✓", THEME["success"])

            # Step 2: Decompile
            self._set_step_state(1, "Đang xử lý...", THEME["warning"])
            self.logger.info("── Bước 2/4: Decompile file APK ──")
            self.logger.info(f"Đang giải nén: {apk.name} ({apk.stat().st_size/1024/1024:.1f} MB)")
            try:
                ok = decompile_apk(apk, tmp)
            except FileNotFoundError as e:
                self._set_step_state(1, "Thất bại ❌", THEME["error"])
                self._pipeline_failed(str(e))
                return
            if not ok:
                self._set_step_state(1, "Thất bại ❌", THEME["error"])
                self._pipeline_failed("Giải nén APK thất bại!")
                return
            self._set_step_state(1, "Xong ✓", THEME["success"])

            # Step 3: Clean
            self._set_step_state(2, "Đang xử lý...", THEME["warning"])
            self.logger.info("── Bước 3/4: Tiến hành dọn dẹp Ads và Redirects ──")
            report = clean_source_code(tmp, dry_run=False)
            self._set_step_state(2, "Xong ✓", THEME["success"])

            # Step 4: Recompile & Sign
            self._set_step_state(3, "Đang đóng gói...", THEME["warning"])
            self.logger.info("── Bước 4/4: Đóng gói lại và ký số APK ──")
            if not recompile_apk(tmp, rb):
                self._set_step_state(3, "Thất bại ❌", THEME["error"])
                self._pipeline_failed("Đóng gói APK thất bại!")
                return
            
            self._set_step_state(3, "Đang ký số...", THEME["warning"])
            ks = Path(self.var_keystore.get()) if self.var_keystore.get() else None
            signed = sign_apk(rb, out, keystore=ks)
            if not signed:
                self._set_step_state(3, "Thất bại ❌", THEME["error"])
                self._pipeline_failed("Ký số file APK thất bại!")
                return
            self._set_step_state(3, "Xong ✓", THEME["success"])

            # Clean temp
            shutil.rmtree(tmp, ignore_errors=True)
            rb.unlink(missing_ok=True)

            # Success
            self.logger.info(f"✨ Thành công! File lưu tại: {signed}")
            self._pipeline_success(report, signed)

        except Exception as e:
            self.logger.error(f"Lỗi hệ thống: {e}")
            self._pipeline_failed(f"Gặp ngoại lệ: {e}")

    def _pipeline_failed(self, reason):
        def _apply():
            self.is_running = False
            self.btn_back_proc.set_state("normal")
            messagebox.showerror("Lỗi xử lý", f"Không thể hoàn thành dọn dẹp APK:\n\n{reason}")
        self._schedule_ui(_apply)

    def _pipeline_success(self, report, signed_file):
        def _apply():
            self.is_running = False
            self.btn_back_proc.set_state("normal")
            
            # Populate result UI
            self.res_icon.configure(text="✅")
            self.res_title.configure(text="Làm Sạch Thành Công!", foreground=THEME["success"])
            self.stats_lbl.configure(text="Báo cáo kết quả chi tiết:")
            
            self.stat_widgets["scanned"].configure(text=str(report.get("files_scanned", 0)))
            self.stat_widgets["modified"].configure(text=str(report.get("files_modified", 0)))
            self.stat_widgets["ads_blocked"].configure(text=str(report.get("ads_methods_blocked", 0)))
            self.stat_widgets["store_blocked"].configure(text=str(report.get("store_redirects_blocked", 0)))
            self.stat_widgets["xml_removed"].configure(text=str(report.get("xml_entries_removed", 0)))

            self.lbl_out_file.configure(text=Path(signed_file).name)
            self.lbl_out_path.configure(text=str(Path(signed_file).parent))

            self.show_screen("result")
        self._schedule_ui(_apply)

    def _reset_to_start(self):
        self.apk_path = ""
        self.drop_zone.clear()
        self.btn_next_select.set_state("disabled")
        self.show_screen("select")

    # ══════════════════════════════════════════════
    # UTILS
    # ══════════════════════════════════════════════
    def _poll_logs(self):
        while not self.log_queue.empty():
            try:
                level, msg = self.log_queue.get_nowait()
                self._append_log_to_box(level, msg)
            except queue.Empty:
                break
        self.after(100, self._poll_logs)

    def _append_log_to_box(self, level, msg):
        self.log_text.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"{ts} ")
        
        tag = "INFO"
        if "✔" in msg or "✓" in msg or "✨" in msg:
            tag = "SUCCESS"
        elif level in ["WARNING", "ERROR"]:
            tag = level

        self.log_text.insert("end", f"[{level}] {msg}\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")


if __name__ == "__main__":
    app = APKCleanerApp()
    app.mainloop()
