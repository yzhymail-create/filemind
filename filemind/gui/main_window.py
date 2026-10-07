"""FileMind 主窗口"""
import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import os
import sys

# 确保能找到 filemind 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from filemind import db as dbmod
from filemind.gui.folder_panel import FolderPanel
from filemind.gui.scan_panel import ScanPanel
from filemind.gui.search_panel import SearchPanel
from filemind.gui.chains_panel import ChainsPanel
from filemind.gui.dups_panel import DupsPanel


class MainWindow(ctk.CTk):
    def __init__(self, db_path: str, cfg_path: str):
        super().__init__()
        
        self.db_path = db_path
        self.cfg_path = cfg_path
        
        # 窗口设置 - 自动适配屏幕大小
        self.title("FileMind - 本地文件记忆与版本管理")
        
        # 获取屏幕尺寸，设置为屏幕的 80%
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        win_width = int(screen_width * 0.85)
        win_height = int(screen_height * 0.85)
        self.geometry(f"{win_width}x{win_height}")
        self.minsize(800, 500)
        self.resizable(True, True)  # 允许拖拽调整大小
        
        # 设置主题
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # 创建布局
        self._create_widgets()
        
        # 初始化数据库
        self._init_db()
        
        # 加载第一个面板
        self._show_panel("folders")
    
    def _create_widgets(self):
        """创建界面组件"""
        # 左侧导航
        self.nav_frame = ctk.CTkFrame(self, width=180, corner_radius=0)
        self.nav_frame.pack(side="left", fill="y", padx=0, pady=0)
        self.nav_frame.pack_propagate(False)
        
        # Logo/标题
        title_label = ctk.CTkLabel(
            self.nav_frame, 
            text="FileMind",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(pady=20)
        
        # 导航按钮
        nav_buttons = [
            (" 文件夹", "folders"),
            ("🔄 扫描", "scan"),
            (" 搜索", "search"),
            (" 版本链", "chains"),
            ("📋 重复文件", "dups"),
        ]
        
        self.nav_btns = {}
        for text, panel_id in nav_buttons:
            btn = ctk.CTkButton(
                self.nav_frame,
                text=text,
                font=ctk.CTkFont(size=14),
                height=40,
                corner_radius=8,
                command=lambda p=panel_id: self._show_panel(p)
            )
            btn.pack(pady=5, padx=10, fill="x")
            self.nav_btns[panel_id] = btn
        
        # 右侧内容区（可滚动）
        self.scroll_frame = ctk.CTkScrollableFrame(self, corner_radius=0)
        self.scroll_frame.pack(side="right", fill="both", expand=True, padx=0, pady=0)
        
        self.content_frame = ctk.CTkFrame(self.scroll_frame, corner_radius=0, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True)
        
        # 底部状态栏
        self.status_bar = ctk.CTkLabel(
            self,
            text="就绪",
            height=30,
            corner_radius=0,
            font=ctk.CTkFont(size=12)
        )
        self.status_bar.pack(side="bottom", fill="x")
    
    def _init_db(self):
        """初始化数据库"""
        if not os.path.exists(self.db_path):
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            con = dbmod.connect(self.db_path)
            con.close()
    
    def _show_panel(self, panel_id: str):
        """显示指定面板"""
        # 清除当前内容
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        
        # 更新导航按钮样式
        for pid, btn in self.nav_btns.items():
            if pid == panel_id:
                btn.configure(fg_color="#1f6aa5")
            else:
                btn.configure(fg_color="#3B3B3B")
        
        # 创建并显示面板
        if panel_id == "folders":
            panel = FolderPanel(self.content_frame, self)
        elif panel_id == "scan":
            panel = ScanPanel(self.content_frame, self)
        elif panel_id == "search":
            panel = SearchPanel(self.content_frame, self)
        elif panel_id == "chains":
            panel = ChainsPanel(self.content_frame, self)
        elif panel_id == "dups":
            panel = DupsPanel(self.content_frame, self)
        else:
            return
        
        panel.pack(fill="both", expand=True, padx=20, pady=20)
        self.status_bar.configure(text=f"当前：{panel.title}")
    
    def set_status(self, text: str):
        """设置状态栏文本"""
        self.status_bar.configure(text=text)
    
    def _trigger_scan(self):
        """触发扫描 - 供其他面板调用"""
        # 找到扫描面板并触发扫描
        for widget in self.content_frame.winfo_children():
            if hasattr(widget, '_start_scan'):
                widget._start_scan()
                break


def main(db_path: str = "", port: int = 8901):
    """桌面版入口"""
    if not db_path:
        db_path = os.path.abspath(os.path.join("data", "filemind.sqlite"))
    cfg_path = os.path.splitext(db_path)[0] + ".config.json"
    
    # 检查数据库
    if not os.path.exists(db_path):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    # 启动主窗口
    app = MainWindow(db_path, cfg_path)
    app.mainloop()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(prog="filemind.gui")
    ap.add_argument("--db", default="", help="SQLite 数据库路径")
    args = ap.parse_args()
    main(db_path=args.db)
