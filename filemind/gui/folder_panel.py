"""文件夹管理面板"""
import customtkinter as ctk
from tkinter import filedialog, messagebox
import json
import os


class FolderPanel(ctk.CTkFrame):
    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.main_window = main_window
        self.title = "文件夹管理"
        
        self._create_widgets()
        self._load_folders()
    
    def _create_widgets(self):
        """创建组件"""
        # 标题
        title = ctk.CTkLabel(
            self,
            text="监控目录",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title.pack(pady=(0, 20))
        
        # 文件夹列表
        self.folder_list = ctk.CTkFrame(self)
        self.folder_list.pack(fill="both", expand=True, pady=10)
        
        # 按钮区
        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", pady=10)
        
        self.add_btn = ctk.CTkButton(
            btn_frame,
            text=" 添加文件夹",
            font=ctk.CTkFont(size=14),
            height=40,
            command=self._add_folder
        )
        self.add_btn.pack(side="left", padx=5)
        
        self.remove_btn = ctk.CTkButton(
            btn_frame,
            text="🗑 删除选中",
            font=ctk.CTkFont(size=14),
            height=40,
            fg_color="#d32f2f",
            command=self._remove_folder
        )
        self.remove_btn.pack(side="left", padx=5)
        
        self.scan_btn = ctk.CTkButton(
            btn_frame,
            text="🔄 开始扫描",
            font=ctk.CTkFont(size=14),
            height=40,
            fg_color="#388e3c",
            command=self._start_scan
        )
        self.scan_btn.pack(side="right", padx=5)
    
    def _load_folders(self):
        """加载文件夹列表"""
        # 清除现有
        for widget in self.folder_list.winfo_children():
            widget.destroy()
        
        # 读取配置
        try:
            cfg = json.load(open(self.main_window.cfg_path, encoding="utf-8"))
            folders = cfg.get("dirs", [])
        except (OSError, json.JSONDecodeError):
            folders = []
        
        if not folders:
            label = ctk.CTkLabel(
                self.folder_list,
                text="暂无监控目录，请点击'添加文件夹'",
                font=ctk.CTkFont(size=14),
                text_color="gray"
            )
            label.pack(pady=40)
            return
        
        # 显示文件夹
        for folder in folders:
            item = ctk.CTkFrame(self.folder_list, corner_radius=8)
            item.pack(fill="x", pady=5, padx=10)
            
            # 文件夹路径
            path_label = ctk.CTkLabel(
                item,
                text=folder,
                font=ctk.CTkFont(size=13),
                anchor="w"
            )
            path_label.pack(side="left", fill="x", expand=True, padx=10, pady=8)
            
            # 删除按钮
            del_btn = ctk.CTkButton(
                item,
                text="删除",
                width=60,
                height=30,
                fg_color="#d32f2f",
                command=lambda f=folder: self._delete_folder(f)
            )
            del_btn.pack(side="right", padx=10)
    
    def _add_folder(self):
        """添加文件夹"""
        folder = filedialog.askdirectory(title="选择要监控的文件夹")
        if not folder:
            return
        
        # 读取配置
        try:
            cfg = json.load(open(self.main_window.cfg_path, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cfg = {"dirs": []}
        
        # 检查是否已存在
        folder = os.path.normpath(folder)
        if folder in cfg["dirs"]:
            messagebox.showwarning("重复", "该文件夹已在监控列表中")
            return
        
        # 添加并保存
        cfg["dirs"].append(folder)
        os.makedirs(os.path.dirname(self.main_window.cfg_path), exist_ok=True)
        with open(self.main_window.cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        
        self._load_folders()
        self.main_window.set_status(f"已添加：{folder}")
    
    def _remove_folder(self):
        """删除选中文件夹（暂未实现选择功能，用删除按钮代替）"""
        messagebox.showinfo("提示", "请点击文件夹右侧的'删除'按钮")
    
    def _delete_folder(self, folder: str):
        """删除指定文件夹"""
        if not messagebox.askyesno("确认", f"确定要删除监控目录：\n{folder}？"):
            return
        
        try:
            cfg = json.load(open(self.main_window.cfg_path, encoding="utf-8"))
            if folder in cfg["dirs"]:
                cfg["dirs"].remove(folder)
                with open(self.main_window.cfg_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                self._load_folders()
                self.main_window.set_status(f"已删除：{folder}")
        except Exception as e:
            messagebox.showerror("错误", f"删除失败：{e}")
    
    def _start_scan(self):
        """开始扫描 - 直接触发扫描面板的扫描功能"""
        # 切换到扫描面板并直接触发扫描
        self.main_window._show_panel("scan")
        # 延迟触发扫描，等面板加载完成
        self.after(100, lambda: self.main_window._trigger_scan())
