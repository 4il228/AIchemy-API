"""Оконная админка для базы рецептов AIchemy.

Запуск:  python admin.py
Tkinter встроен в Python — дополнительных зависимостей не нужно.
"""

import os
import hashlib
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox, filedialog

from dotenv import load_dotenv
from PIL import Image, ImageTk
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, joinedload

from db import Recipe, User

load_dotenv()

# Админке нужен синхронный движок: Tkinter работает без event loop asyncio.
# Из async-URL убираем драйвер: sqlite+aiosqlite -> sqlite, postgresql+asyncpg -> postgresql
ASYNC_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./alchemy.db")
SYNC_URL = ASYNC_URL.replace("+aiosqlite", "").replace("+asyncpg", "")

engine = create_engine(SYNC_URL)

IMAGES_DIR = Path("generated_images")


class AdminApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AIchemy — администрирование базы рецептов")
        self.geometry("1150x640")
        self.minsize(900, 500)

        self._photo = None  # держим ссылку, иначе Tkinter выгрузит картинку
        self._selected_id: int | None = None

        self._build_toolbar()
        self._build_body()
        self._build_statusbar()
        self.refresh()

    # ---------- UI ----------

    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(fill=tk.X)

        ttk.Label(bar, text="Поиск:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        entry = ttk.Entry(bar, textvariable=self.search_var, width=32)
        entry.pack(side=tk.LEFT, padx=(4, 8))
        entry.bind("<Return>", lambda _: self.refresh())

        ttk.Button(bar, text="Найти", command=self.refresh).pack(side=tk.LEFT)
        ttk.Button(bar, text="Сброс", command=self._reset_search).pack(side=tk.LEFT, padx=(4, 16))
        ttk.Button(bar, text="Обновить", command=self.refresh).pack(side=tk.LEFT)
        ttk.Button(bar, text="Добавить", command=self.add_recipe).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(bar, text="Удалить выбранный", command=self.delete_selected).pack(
            side=tk.RIGHT
        )

    def _build_body(self):
        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))

        # Левая часть: таблица
        left = ttk.Frame(body)
        body.add(left, weight=3)

        columns = ("id", "pair", "result", "creator", "created_at")
        self.tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("id", text="ID")
        self.tree.heading("pair", text="Элементы")
        self.tree.heading("result", text="Результат")
        self.tree.heading("creator", text="Создатель")
        self.tree.heading("created_at", text="Создан")
        self.tree.column("id", width=50, anchor=tk.CENTER, stretch=False)
        self.tree.column("pair", width=210)
        self.tree.column("result", width=140)
        self.tree.column("creator", width=100)
        self.tree.column("created_at", width=130, stretch=False)

        scroll = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # Правая часть: карточка рецепта
        right = ttk.Frame(body, padding=(10, 0))
        body.add(right, weight=2)

        ttk.Label(right, text="Результат:").pack(anchor=tk.W)
        self.result_var = tk.StringVar()
        ttk.Entry(right, textvariable=self.result_var).pack(fill=tk.X, pady=(0, 6))

        ttk.Label(right, text="Описание:").pack(anchor=tk.W)
        self.desc_text = tk.Text(right, height=4, wrap=tk.WORD)
        self.desc_text.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(right, text="Промпт изображения (en):").pack(anchor=tk.W)
        self.prompt_text = tk.Text(right, height=5, wrap=tk.WORD)
        self.prompt_text.pack(fill=tk.X, pady=(0, 6))

        ttk.Button(right, text="Сохранить изменения", command=self.save_selected).pack(
            anchor=tk.E, pady=(0, 8)
        )

        self.image_label = ttk.Label(right, text="Нет изображения", anchor=tk.CENTER)
        self.image_label.pack(fill=tk.BOTH, expand=True)

    def _build_statusbar(self):
        self.status_var = tk.StringVar()
        ttk.Label(self, textvariable=self.status_var, padding=(8, 4)).pack(
            fill=tk.X, side=tk.BOTTOM
        )

    def _reset_search(self):
        self.search_var.set("")
        self.refresh()

    # ---------- Данные ----------

    def refresh(self):
        with Session(engine) as session:
            recipes = session.scalars(
                select(Recipe)
                .options(joinedload(Recipe.creator))
                .order_by(Recipe.id.desc())
            ).all()

        # Фильтруем в Python: lower() в SQLite не понимает кириллицу
        term = self.search_var.get().strip().lower()
        if term:
            recipes = [
                r for r in recipes
                if term in r.result.lower()
                or term in r.element_a
                or term in r.element_b
            ]

        self.tree.delete(*self.tree.get_children())
        for r in recipes:
            created = r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else ""
            creator = r.creator.nickname if r.creator else "—"
            self.tree.insert(
                "", tk.END, iid=str(r.id),
                values=(r.id, f"{r.element_a} + {r.element_b}", r.result, creator, created),
            )

        self._clear_card()
        self.status_var.set(f"Рецептов: {len(recipes)}  |  БД: {SYNC_URL}")

    def _on_select(self, _event):
        selection = self.tree.selection()
        if not selection:
            return
        recipe_id = int(selection[0])
        with Session(engine) as session:
            recipe = session.scalar(
                select(Recipe)
                .where(Recipe.id == recipe_id)
                .options(joinedload(Recipe.creator))
            )
        if recipe is None:
            return

        self._selected_id = recipe.id
        self.result_var.set(recipe.result)
        self.desc_text.delete("1.0", tk.END)
        self.desc_text.insert("1.0", recipe.description)
        self.prompt_text.delete("1.0", tk.END)
        self.prompt_text.insert("1.0", recipe.image_prompt_en)
        self._show_image(recipe.image_path)

    def _show_image(self, image_path: str):
        path = Path(image_path)
        if not path.exists():
            self._photo = None
            self.image_label.configure(image="", text=f"Файл не найден:\n{image_path}")
            return
        try:
            # Pillow, а не tk.PhotoImage: Pollinations отдаёт JPEG даже с расширением .png
            with Image.open(path) as img:
                img.thumbnail((320, 320))
                self._photo = ImageTk.PhotoImage(img)
            self.image_label.configure(image=self._photo, text="")
        except OSError as e:
            self._photo = None
            self.image_label.configure(image="", text=f"Не удалось открыть:\n{e}")

    def _clear_card(self):
        self._selected_id = None
        self.result_var.set("")
        self.desc_text.delete("1.0", tk.END)
        self.prompt_text.delete("1.0", tk.END)
        self._photo = None
        self.image_label.configure(image="", text="Нет изображения")

    # ---------- Действия ----------

    def add_recipe(self):
        dialog = tk.Toplevel(self)
        dialog.title("Добавить рецепт")
        dialog.geometry("560x380")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        fields = {}

        row = 0
        for label, key in (
            ("Элемент A", "element_a"),
            ("Элемент B", "element_b"),
            ("Результат *", "result"),
            ("Описание", "description"),
            ("Промпт (en)", "image_prompt_en"),
        ):
            ttk.Label(dialog, text=label).grid(row=row, column=0, sticky=tk.W, padx=8, pady=4)
            w = ttk.Entry(dialog, width=50)
            w.grid(row=row, column=1, padx=(0, 8), pady=4)
            fields[key] = w
            row += 1

        # Поле с кнопкой выбора файла
        ttk.Label(dialog, text="Изображение").grid(row=row, column=0, sticky=tk.W, padx=8, pady=4)
        path_frame = ttk.Frame(dialog)
        path_frame.grid(row=row, column=1, padx=(0, 8), pady=4, sticky=tk.EW)
        img_path_entry = ttk.Entry(path_frame, width=40)
        img_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def browse_image():
            file_path = filedialog.askopenfilename(
                parent=dialog,
                title="Выберите изображение",
                filetypes=[("Изображения", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("Все файлы", "*.*")],
            )
            if not file_path:
                return
            src = Path(file_path)
            dest_name = f"manual_{hashlib.sha1(src.read_bytes()).hexdigest()[:16]}{src.suffix}"
            dest = IMAGES_DIR / dest_name
            IMAGES_DIR.mkdir(exist_ok=True)
            shutil.copy2(src, dest)
            img_path_entry.delete(0, tk.END)
            img_path_entry.insert(0, str(dest))

        ttk.Button(path_frame, text="Обзор…", command=browse_image).pack(side=tk.RIGHT, padx=(4, 0))
        fields["image_path"] = img_path_entry
        row += 1

        # Делаем колонку 1 растяжимой для path_frame
        dialog.columnconfigure(1, weight=1)

        def do_add():
            if not fields["result"].get().strip():
                messagebox.showwarning("Ошибка", "Поле «Результат» обязательно.", parent=dialog)
                return

            element_a = fields["element_a"].get().strip().lower()
            element_b = fields["element_b"].get().strip().lower()
            result = fields["result"].get().strip()
            description = fields["description"].get().strip()
            image_prompt_en = fields["image_prompt_en"].get().strip()
            image_path = fields["image_path"].get().strip()

            if not element_a and not element_b:
                base_key = hashlib.sha1(f"_base_{result}_{__import__('time').time()}".encode()).hexdigest()[:12]
                element_a = f"_base_{base_key}"
                element_b = ""

            if not image_path:
                pair_hash = hashlib.sha1(f"{element_a}+{element_b}".encode()).hexdigest()[:8]
                image_path = f"generated_images/manual_{pair_hash}.png"

            with Session(engine) as session:
                if element_a and element_b:
                    existing = session.scalar(
                        select(Recipe).where(
                            Recipe.element_a == element_a, Recipe.element_b == element_b
                        )
                    )
                    if existing is not None:
                        messagebox.showwarning(
                            "Ошибка",
                            f"Рецепт «{existing.result}» для этой пары уже существует (id={existing.id}).",
                            parent=dialog,
                        )
                        return

                recipe = Recipe(
                    element_a=element_a,
                    element_b=element_b,
                    result=result,
                    description=description or "Добавлено вручную",
                    image_path=image_path,
                    image_prompt_en=image_prompt_en or "No prompt provided",
                    creator_id=1,
                )
                session.add(recipe)
                session.commit()
                new_id = recipe.id

            self.refresh()
            dialog.destroy()
            self.status_var.set(f"Рецепт #{new_id} добавлен")
            if self.tree.exists(str(new_id)):
                self.tree.selection_set(str(new_id))
                self.tree.see(str(new_id))

        btn_frame = ttk.Frame(dialog)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=(12, 8))
        ttk.Button(btn_frame, text="Сохранить", command=do_add).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Отмена", command=dialog.destroy).pack(side=tk.LEFT, padx=4)

    def save_selected(self):
        if self._selected_id is None:
            messagebox.showinfo("Сохранение", "Сначала выбери рецепт в списке.")
            return

        new_result = self.result_var.get().strip()
        new_desc = self.desc_text.get("1.0", tk.END).strip()
        new_prompt = self.prompt_text.get("1.0", tk.END).strip()
        if not new_result:
            messagebox.showwarning("Сохранение", "Поле «Результат» не может быть пустым.")
            return

        with Session(engine) as session:
            recipe = session.get(Recipe, self._selected_id)
            if recipe is None:
                messagebox.showerror("Сохранение", "Запись уже удалена.")
                self.refresh()
                return
            recipe.result = new_result
            recipe.description = new_desc
            recipe.image_prompt_en = new_prompt
            session.commit()

        selected = str(self._selected_id)
        self.refresh()
        if self.tree.exists(selected):
            self.tree.selection_set(selected)
            self.tree.see(selected)
        self.status_var.set(f"Рецепт #{selected} сохранён")

    def delete_selected(self):
        if self._selected_id is None:
            messagebox.showinfo("Удаление", "Сначала выбери рецепт в списке.")
            return

        with Session(engine) as session:
            recipe = session.get(Recipe, self._selected_id)
            if recipe is None:
                self.refresh()
                return
            pair = f"{recipe.element_a} + {recipe.element_b}"
            if not messagebox.askyesno(
                "Удаление",
                f"Удалить рецепт «{pair} = {recipe.result}»?\n"
                "Файл изображения тоже будет удалён.",
            ):
                return
            image_path = Path(recipe.image_path)
            session.delete(recipe)
            session.commit()

        if image_path.exists():
            image_path.unlink()

        self.refresh()
        self.status_var.set(f"Рецепт «{pair}» удалён")


if __name__ == "__main__":
    AdminApp().mainloop()
