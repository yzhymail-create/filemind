"""扫描面板（带进度显示）"""
import customtkinter as ctk
from tkinter import messagebox
import json
import os
import threading
import time


class ScanPanel(ctk.CTkFrame):
    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.main_window = main_window
        self.title = "扫描"
        self.scanning = False
        
        self._create_widgets()
        self._load_status()
    
    def _create_widgets(self):
        """创建组件"""
        # 标题
        title = ctk.CTkLabel(
            self,
            text="文件扫描",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title.pack(pady=(0, 20))
        
        # 监控目录显示
        dirs_frame = ctk.CTkFrame(self)
        dirs_frame.pack(fill="x", pady=10)
        
        dirs_label = ctk.CTkLabel(
            dirs_frame,
            text="监控目录:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        dirs_label.pack(anchor="w", padx=10, pady=5)
        
        self.dirs_text = ctk.CTkTextbox(
            dirs_frame,
            height=80,
            font=ctk.CTkFont(size=12)
        )
        self.dirs_text.pack(fill="x", padx=10, pady=5)
        
        # 进度区域
        progress_frame = ctk.CTkFrame(self)
        progress_frame.pack(fill="x", pady=10)
        
        self.progress_bar = ctk.CTkProgressBar(
            progress_frame,
            mode="determinate"
        )
        self.progress_bar.pack(fill="x", padx=10, pady=10)
        self.progress_bar.set(0)
        
        self.progress_label = ctk.CTkLabel(
            progress_frame,
            text="就绪 - 点击'开始扫描'按钮",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.progress_label.pack(pady=5)
        
        # 统计信息
        stats_frame = ctk.CTkFrame(self)
        stats_frame.pack(fill="x", pady=10)
        
        self.stats_label = ctk.CTkLabel(
            stats_frame,
            text="上次扫描：尚未扫描",
            font=ctk.CTkFont(size=13)
        )
        self.stats_label.pack(pady=10)
        
        # 日志区域
        log_frame = ctk.CTkFrame(self)
        log_frame.pack(fill="both", expand=True, pady=10)
        
        log_label = ctk.CTkLabel(
            log_frame,
            text="扫描日志:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        log_label.pack(anchor="w", padx=10, pady=5)
        
        self.log_text = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(size=11, family="Consolas")
        )
        self.log_text.pack(fill="both", expand=True, padx=10, pady=5)
        
        # 按钮
        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", pady=10)
        
        self.scan_btn = ctk.CTkButton(
            btn_frame,
            text="🔄 开始扫描",
            font=ctk.CTkFont(size=14),
            height=40,
            fg_color="#388e3c",
            command=self._start_scan
        )
        self.scan_btn.pack(side="left", padx=5)
        
        self.stop_btn = ctk.CTkButton(
            btn_frame,
            text="⏹ 停止",
            font=ctk.CTkFont(size=14),
            height=40,
            fg_color="#d32f2f",
            command=self._stop_scan,
            state="disabled"
        )
        self.stop_btn.pack(side="left", padx=5)
    
    def _load_status(self):
        """加载状态"""
        # 扫描期间不访问数据库，避免锁冲突
        if self.scanning:
            return
        
        # 加载目录
        try:
            cfg = json.load(open(self.main_window.cfg_path, encoding="utf-8"))
            dirs = cfg.get("dirs", [])
            self.dirs_text.delete("1.0", "end")
            self.dirs_text.insert("1.0", "\n".join(dirs) if dirs else "暂无监控目录")
            self.dirs_text.configure(state="disabled")
        except (OSError, json.JSONDecodeError):
            self.dirs_text.insert("1.0", "暂无监控目录")
            self.dirs_text.configure(state="disabled")
        
        # 加载上次扫描统计
        if os.path.exists(self.main_window.db_path):
            try:
                from filemind import db as dbmod
                con = dbmod.connect(self.main_window.db_path)
                last = con.execute("SELECT * FROM scan_log ORDER BY id DESC LIMIT 1").fetchone()
                con.close()
                
                if last:
                    from datetime import datetime
                    t = datetime.fromtimestamp(last["finished_at"] or last["started_at"])
                    self.stats_label.configure(
                        text=f"上次扫描：{t.strftime('%Y-%m-%d %H:%M')}\n"
                             f"新增：{last['added']} | 更新：{last['updated']} | 失踪：{last['missing']}"
                    )
            except Exception:
                # 数据库锁或其他错误，忽略
                pass
    
    def _start_scan(self):
        """开始扫描"""
        if self.scanning:
            return
        
        # 检查是否有监控目录
        try:
            cfg = json.load(open(self.main_window.cfg_path, encoding="utf-8"))
            dirs = cfg.get("dirs", [])
        except (OSError, json.JSONDecodeError):
            dirs = []
        
        if not dirs:
            messagebox.showwarning("提示", "请先在'文件夹'页面添加监控目录")
            return
        
        self.scanning = True
        self.scan_btn.configure(state="disabled", text="扫描中...")
        self.stop_btn.configure(state="normal")
        self.progress_bar.set(0)
        self.progress_label.configure(text="扫描中，请稍候...")
        self.log_text.delete("1.0", "end")
        self._log("开始扫描...")
        self._log(f"监控目录：{len(dirs)} 个")
        
        # 后台线程执行扫描
        def _do_scan():
            try:
                from filemind import scan as scanmod
                from filemind import chains as chainsmod
                
                file_count = [0]
                
                def progress(path, status):
                    if self.scanning:
                        file_count[0] += 1
                        self.after(0, lambda: self._log(f"[{status}] {os.path.basename(path)}"))
                        # 每 10 个文件更新一次进度
                        if file_count[0] % 10 == 0:
                            self.after(0, lambda: self.progress_label.configure(
                                text=f"扫描中... 已处理 {file_count[0]} 个文件"
                            ))
                        return True  # 继续扫描
                    return False  # 用户停止
                
                result = scanmod.scan(dirs, self.main_window.db_path, progress=progress)
                
                if self.scanning:
                    self.after(0, lambda: self._log(f"\n扫描完成！"))
                    self.after(0, lambda: self._log(f"新增：{result['added']}"))
                    self.after(0, lambda: self._log(f"更新：{result['updated']}"))
                    self.after(0, lambda: self._log(f"失踪：{result['missing']}"))
                    self.after(0, lambda: self._log("正在构建版本链..."))
                    
                    chainsmod.build_chains(self.main_window.db_path)
                    
                    self.after(0, lambda: self._log("版本链构建完成！"))
                    self.after(0, lambda: self.progress_bar.set(1.0))
                    self.after(0, lambda: self.progress_label.configure(text="扫描完成"))
                    # 延迟加载状态，避免数据库锁
                    self.after(1000, lambda: self._load_status())
                    
            except Exception as e:
                self.after(0, lambda: self._log(f"扫描出错：{e}"))
                self.after(0, lambda: self.progress_label.configure(text=f"扫描出错：{e}"))
            finally:
                self.scanning = False
                self.after(0, lambda: self.scan_btn.configure(state="normal", text="🔄 开始扫描"))
                self.after(0, lambda: self.stop_btn.configure(state="disabled"))
        
        t = threading.Thread(target=_do_scan, daemon=True)
        t.start()
    
    def _stop_scan(self):
        """停止扫描"""
        if self.scanning:
            self.scanning = False
            self.progress_label.configure(text="正在停止...")
            self._log("用户请求停止扫描")
            # 扫描线程会检查 self.scanning 标志并退出
            # 不需要强制终止线程，让它自然结束
    
    def _log(self, text: str):
        """添加日志"""
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
