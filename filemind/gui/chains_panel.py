"""版本链面板"""
import customtkinter as ctk
from tkinter import messagebox
import os


class ChainsPanel(ctk.CTkFrame):
    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.main_window = main_window
        self.title = "版本链"
        
        self._create_widgets()
        self._load_chains()
    
    def _create_widgets(self):
        """创建组件"""
        # 标题
        title = ctk.CTkLabel(
            self,
            text="版本链",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title.pack(pady=(0, 20))
        
        # 提示
        tip = ctk.CTkLabel(
            self,
            text="同一文件的不同版本会被自动识别为版本链",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        tip.pack(pady=5)
        
        # 链列表
        self.chains_frame = ctk.CTkScrollableFrame(self)
        self.chains_frame.pack(fill="both", expand=True, pady=10)
    
    def _load_chains(self):
        """加载版本链"""
        # 清除现有
        for widget in self.chains_frame.winfo_children():
            widget.destroy()
        
        if not os.path.exists(self.main_window.db_path):
            label = ctk.CTkLabel(
                self.chains_frame,
                text="数据库不存在，请先扫描文件",
                font=ctk.CTkFont(size=14),
                text_color="gray"
            )
            label.pack(pady=40)
            return
        
        try:
            from filemind import db as dbmod
            from filemind import recommend as recmod
            
            con = dbmod.connect(self.main_window.db_path)
            rows = con.execute(
                """SELECT c.id, c.confirmed, c.note, COUNT(m.file_id) n
                   FROM chains c JOIN chain_members m ON m.chain_id=c.id
                   GROUP BY c.id ORDER BY c.id"""
            ).fetchall()
            
            if not rows:
                label = ctk.CTkLabel(
                    self.chains_frame,
                    text="暂无版本链",
                    font=ctk.CTkFont(size=14),
                    text_color="gray"
                )
                label.pack(pady=40)
                con.close()
                return
            
            for r in rows:
                d = dict(r)
                rec = recmod.recommend(self.main_window.db_path, d["id"])
                
                # 链卡片
                card = ctk.CTkFrame(self.chains_frame, corner_radius=8)
                card.pack(fill="x", pady=5, padx=10)
                
                # 标题
                title_text = f"版本链 #{d['id']}（{d['n']} 个版本）"
                if not d["confirmed"]:
                    title_text += " [需人工确认]"
                
                title_label = ctk.CTkLabel(
                    card,
                    text=title_text,
                    font=ctk.CTkFont(size=14, weight="bold")
                )
                title_label.pack(anchor="w", padx=10, pady=5)
                
                # 推荐版本
                rec_label = ctk.CTkLabel(
                    card,
                    text=f"推荐：{rec['name']} — {'；'.join(rec['reasons'])}",
                    font=ctk.CTkFont(size=12),
                    text_color="gray"
                )
                rec_label.pack(anchor="w", padx=10, pady=2)
            
            con.close()
        
        except Exception as e:
            label = ctk.CTkLabel(
                self.chains_frame,
                text=f"加载失败：{e}",
                font=ctk.CTkFont(size=14),
                text_color="red"
            )
            label.pack(pady=40)
