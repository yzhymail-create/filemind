"""搜索面板"""
import customtkinter as ctk
from tkinter import messagebox
import os


class SearchPanel(ctk.CTkFrame):
    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.main_window = main_window
        self.title = "搜索"
        
        self._create_widgets()
    
    def _create_widgets(self):
        """创建组件"""
        # 标题
        title = ctk.CTkLabel(
            self,
            text="内容搜索",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title.pack(pady=(0, 20))
        
        # 搜索框
        search_frame = ctk.CTkFrame(self)
        search_frame.pack(fill="x", pady=10)
        
        self.search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="输入关键词，如：线束阻燃 胶带",
            font=ctk.CTkFont(size=14),
            height=40
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.search_entry.bind("<Return>", lambda e: self._do_search())
        
        search_btn = ctk.CTkButton(
            search_frame,
            text="搜索",
            font=ctk.CTkFont(size=14),
            width=100,
            height=40,
            command=self._do_search
        )
        search_btn.pack(side="left", padx=5)
        
        # 提示
        tip = ctk.CTkLabel(
            self,
            text="支持时间词：去年 / 今年 / 近 30 天",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        tip.pack(pady=5)
        
        # 结果区域
        result_frame = ctk.CTkFrame(self)
        result_frame.pack(fill="both", expand=True, pady=10)
        
        self.result_text = ctk.CTkTextbox(
            result_frame,
            font=ctk.CTkFont(size=13)
        )
        self.result_text.pack(fill="both", expand=True, padx=10, pady=10)
    
    def _do_search(self):
        """执行搜索"""
        query = self.search_entry.get().strip()
        if not query:
            return
        
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", f"搜索：{query}\n\n")
        
        if not os.path.exists(self.main_window.db_path):
            self.result_text.insert("end", "数据库不存在，请先扫描文件")
            return
        
        try:
            from filemind import search as searchmod
            
            res = searchmod.search_grouped(self.main_window.db_path, query)
            
            if not res["groups"]:
                self.result_text.insert("end", "没有找到相关内容，换个关键词试试。")
                return
            
            for g in res["groups"]:
                rec = g["recommend"]
                
                if g["chain_id"]:
                    self.result_text.insert("end", f"★ 推荐版本：{rec['name']}\n")
                    self.result_text.insert("end", f"   原因：{'；'.join(rec['reasons'])}\n")
                    self.result_text.insert("end", f"   版本链：共 {g['n_members']} 个版本\n\n")
                
                for h in g["hits"][:3]:
                    self.result_text.insert("end", f"  {h['name']}\n")
                    self.result_text.insert("end", f"  {h['path']}\n")
                    self.result_text.insert("end", f"  {h['snip']}\n\n")
                
                self.result_text.insert("end", "-" * 60 + "\n\n")
        
        except Exception as e:
            self.result_text.insert("end", f"搜索出错：{e}")
