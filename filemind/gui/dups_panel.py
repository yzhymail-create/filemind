"""重复文件面板"""
import customtkinter as ctk
from tkinter import messagebox
import os
import threading


class DupsPanel(ctk.CTkFrame):
    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.main_window = main_window
        self.title = "重复文件"
        self.groups = []
        self.check_vars = {}  # (gi, file_id) -> BooleanVar

        self._create_widgets()
        self._load_dups()

    def _create_widgets(self):
        # 标题
        ctk.CTkLabel(
            self, text="重复文件",
            font=ctk.CTkFont(size=24, weight="bold")
        ).pack(pady=(0, 5))

        ctk.CTkLabel(
            self, text="SHA256 指纹完全相同的文件组",
            font=ctk.CTkFont(size=12), text_color="gray"
        ).pack(pady=(0, 10))

        # 重复文件列表（可滚动）
        self.dups_frame = ctk.CTkScrollableFrame(self)
        self.dups_frame.pack(fill="both", expand=True, pady=5)

        # 底部按钮
        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", pady=10)

        ctk.CTkButton(
            btn_frame, text="全选",
            width=80, height=36,
            command=self._select_all
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame, text="取消全选",
            width=80, height=36,
            command=self._deselect_all
        ).pack(side="left", padx=5)

        self.del_btn = ctk.CTkButton(
            btn_frame, text=" 删除选中文件（移入回收站）",
            height=36, fg_color="#d32f2f",
            command=self._delete_selected
        )
        self.del_btn.pack(side="right", padx=5)

        self.status_label = ctk.CTkLabel(
            btn_frame, text="已选 0 个文件",
            font=ctk.CTkFont(size=12), text_color="gray"
        )
        self.status_label.pack(side="right", padx=10)

    def _load_dups(self):
        for widget in self.dups_frame.winfo_children():
            widget.destroy()
        self.check_vars.clear()
        self.groups = []

        if not os.path.exists(self.main_window.db_path):
            ctk.CTkLabel(
                self.dups_frame, text="数据库不存在，请先扫描文件",
                font=ctk.CTkFont(size=14), text_color="gray"
            ).pack(pady=40)
            return

        try:
            from filemind import db as dbmod
            from filemind import chains as chainsmod
            from filemind import recommend as recmod

            con = dbmod.connect(self.main_window.db_path)
            groups = chainsmod.find_exact_dups(con)
            con.close()

            if not groups:
                ctk.CTkLabel(
                    self.dups_frame, text="没有发现完全重复的文件",
                    font=ctk.CTkFont(size=14), text_color="gray"
                ).pack(pady=40)
                return

            self.groups = groups

            for gi, g in enumerate(groups):
                rec = recmod.recommend_dup_keep(self.main_window.db_path, g)
                keep_id = rec["keep"]["id"]

                # 组卡片
                card = ctk.CTkFrame(self.dups_frame, corner_radius=8)
                card.pack(fill="x", pady=5, padx=10)

                # 组标题
                ctk.CTkLabel(
                    card,
                    text=f"第 {gi+1} 组（{len(g)} 个相同文件）",
                    font=ctk.CTkFont(size=14, weight="bold")
                ).pack(anchor="w", padx=10, pady=(8, 2))

                ctk.CTkLabel(
                    card,
                    text=f"建议保留：{rec['keep']['name']} — {'；'.join(rec['reasons'])}",
                    font=ctk.CTkFont(size=12), text_color="gray"
                ).pack(anchor="w", padx=10, pady=(0, 5))

                # 每个文件一行
                for fi, x in enumerate(g):
                    row = ctk.CTkFrame(card, fg_color="#2a2a2a")
                    row.pack(fill="x", padx=10, pady=2)

                    var = ctk.BooleanVar(value=(x["id"] != keep_id))
                    self.check_vars[(gi, fi)] = var

                    cb = ctk.CTkCheckBox(
                        row, text="", variable=var, width=24,
                        command=self._update_status
                    )
                    cb.pack(side="left", padx=5, pady=6)

                    info_frame = ctk.CTkFrame(row, fg_color="transparent")
                    info_frame.pack(side="left", fill="x", expand=True, padx=5)

                    name_text = x["name"]
                    if x["id"] == keep_id:
                        name_text += " ★保留"

                    ctk.CTkLabel(
                        info_frame, text=name_text,
                        font=ctk.CTkFont(size=13), anchor="w"
                    ).pack(anchor="w")

                    ctk.CTkLabel(
                        info_frame, text=x["path"],
                        font=ctk.CTkFont(size=11), text_color="gray", anchor="w"
                    ).pack(anchor="w")

                    ctk.CTkLabel(
                        info_frame, text=f"{(x['size'] or 0) // 1024} KB",
                        font=ctk.CTkFont(size=11), text_color="gray", anchor="w"
                    ).pack(anchor="w")

            self._update_status()

        except Exception as e:
            ctk.CTkLabel(
                self.dups_frame, text=f"加载失败：{e}",
                font=ctk.CTkFont(size=14), text_color="red"
            ).pack(pady=40)

    def _update_status(self):
        count = sum(1 for v in self.check_vars.values() if v.get())
        self.status_label.configure(text=f"已选 {count} 个文件")
        if count > 0:
            self.del_btn.configure(state="normal")
        else:
            self.del_btn.configure(state="disabled")

    def _select_all(self):
        for v in self.check_vars.values():
            v.set(True)
        self._update_status()

    def _deselect_all(self):
        for v in self.check_vars.values():
            v.set(False)
        self._update_status()

    def _delete_selected(self):
        # 收集选中的文件
        to_delete = []
        for (gi, fi), var in self.check_vars.items():
            if var.get():
                to_delete.append((gi, fi))

        if not to_delete:
            return

        count = len(to_delete)
        if not messagebox.askyesno("确认删除", f"确定要将 {count} 个文件移入回收站？\n（可从回收站还原）"):
            return

        # 后台执行删除
        self.del_btn.configure(state="disabled", text="删除中...")

        def _do_delete():
            from filemind import db as dbmod
            from filemind import trash as trashmod

            con = dbmod.connect(self.main_window.db_path)
            ok = 0
            fail = 0
            for gi, fi in to_delete:
                file_info = self.groups[gi][fi]
                fid = file_info["id"]
                r = con.execute("SELECT path FROM files WHERE id=?", (fid,)).fetchone()
                if not r:
                    fail += 1
                    continue
                good, _ = trashmod.to_recycle(r["path"])
                if good:
                    con.execute(
                        "UPDATE files SET status='missing', status_reason='用户移入回收站' WHERE id=?",
                        (fid,)
                    )
                    ok += 1
                else:
                    fail += 1
            con.commit()
            con.close()
            self.after(0, lambda: self._on_delete_done(ok, fail))

        t = threading.Thread(target=_do_delete, daemon=True)
        t.start()

    def _on_delete_done(self, ok, fail):
        msg = f"已移入回收站 {ok} 个"
        if fail:
            msg += f"，{fail} 个失败"
        self.status_label.configure(text=msg)
        self.del_btn.configure(state="normal", text="🗑 删除选中文件（移入回收站）")
        # 刷新列表
        self._load_dups()
