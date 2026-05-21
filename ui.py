import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, scrolledtext
import tkinter.font as tkfont
import threading
import logging
import ctypes
from typing import TYPE_CHECKING
import os
import sys
import re
from PIL import Image, ImageDraw, ImageFont, ImageTk
from config_loader import Config

# 尝试导入pystray，如果不存在则稍后处理
try:
    from pystray import Icon as TrayIcon, MenuItem as TrayMenuItem
    PYSTRAY_AVAILABLE = True
except ImportError:
    PYSTRAY_AVAILABLE = False

if TYPE_CHECKING:
    from main import AnanSketchbookApp

class AnanSketchbookUI:
    def __init__(self, app: 'AnanSketchbookApp'):
        self.app = app
        
        # 启用高DPI支持
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # 设置高DPI感知
        except:
            pass
            
        ctk.set_appearance_mode("Light")  # 内容区回到亮色，外框单独做稍深处理
        ctk.set_default_color_theme("blue")  # 使用蓝色主题
        
        self.root = ctk.CTk()
        self.root.title("冬里代的改版素描本 V1.1")
        self.root.geometry("960x760")
        self.root.minsize(760, 620)  # 设置最小尺寸
        self.root.resizable(True, True)  # 允许调整窗口大小
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self._loaded_private_font_files = set()
        self._font_option_refresh_job = None
        self._init_color_palette()
        self.root.configure(fg_color=self.colors["window_bg"])
        
        # 设置窗口图标
        self.setup_window_icon()
        
        # 在创建窗口之后初始化字体
        self.init_fonts()
        
        # 创建日志处理器
        self.log_handler = UITextHandler(self)
        self.log_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        )

        self.vocaloid_button_columns = 4
        self.vocaloid_button_size = 104
        self.vocaloid_buttons = {}
        self.vocaloid_button_images = {}
        self.vocaloid_button_masks = {}
        self.vocaloid_button_text_labels = {}
        self.vocaloid_button_thumbnail_labels = {}
        self.vocaloid_button_mask_images = {}
        self.vocaloid_button_target_sizes = {}
        self.vocaloid_button_frames = {}
        self.vocaloid_tabs = {}
        self.vocaloid_preview_cache = {}
        self.vocaloid_background_labels = {}
        self.vocaloid_background_containers = {}
        self.vocaloid_background_images = {}
        self.vocaloid_background_sources = {}
        self.vocaloid_background_source_sizes = {}
        self.vocaloid_poster_rects = {}
        self.vocaloid_surface_hit_boxes = {}
        self.vocaloid_scroll_frames = {}
        self.vocaloid_background_canvases = {}
        self.vocaloid_canvas_photo_images = {}
        self.vocaloid_canvas_image_ids = {}
        self.vocaloid_base_surfaces = {}
        self._thumbnail_card_cache = {}
        self._preview_font_cache = {}
        self._current_base_key = {}

        # 设置UI元素
        self.setup_ui()
        
        # 最小化状态
        self.is_minimized = False

    def _init_color_palette(self):
        """统一界面配色，便于整体调整风格。"""
        self.colors = {
            "window_bg": ("#d6e0ef", "#d6e0ef"),
            "surface": ("#f8fbff", "#f8fbff"),
            "surface_alt": ("#eef4fd", "#eef4fd"),
            "surface_soft": ("#e2ebf8", "#e2ebf8"),
            "input_bg": ("#ffffff", "#ffffff"),
            "input_border": ("#b7c8e2", "#b7c8e2"),
            "accent": ("#5f88e8", "#5f88e8"),
            "accent_hover": ("#4f79da", "#4f79da"),
            "accent_secondary": ("#7fa3f2", "#7fa3f2"),
            "accent_secondary_hover": ("#6f95e7", "#6f95e7"),
            "accent_active": ("#3f68c5", "#3f68c5"),
            "accent_active_hover": ("#355aac", "#355aac"),
            "mode_panel": ("#f3edff", "#f3edff"),
            "mode_button": ("#8a72eb", "#8a72eb"),
            "mode_button_hover": ("#785fe0", "#785fe0"),
            "danger": ("#db6d7a", "#db6d7a"),
            "danger_hover": ("#c85a68", "#c85a68"),
            "text_primary": ("#203251", "#203251"),
            "text_secondary": ("#4f6788", "#4f6788"),
            "text_muted": ("#7384a1", "#7384a1"),
            "outline_text": ("#335385", "#335385"),
            "log_bg": ("#f6f9fe", "#f6f9fe"),
            "log_fg": ("#233553", "#233553"),
        }
        self.vocaloid_folder_accents = {
            "洛佬": "#66ccff",
            "阿绫": "#ee0000",
            "言和": "#00ffcc",
            "墨姐": "#ffff00",
        }

    def _theme_color(self, color_name: str) -> str:
        """从主题色元组中取出当前外观模式对应的颜色。"""
        color_value = self.colors[color_name]
        if not isinstance(color_value, tuple):
            return color_value
        return color_value[1] if ctk.get_appearance_mode() == "Dark" else color_value[0]

    def _blend_hex_color(self, hex_color: str, blend_target: str, ratio: float) -> str:
        """将十六进制颜色与目标颜色按比例混合。"""
        base = hex_color.lstrip("#")
        target = blend_target.lstrip("#")
        if len(base) != 6 or len(target) != 6:
            return hex_color

        ratio = max(0.0, min(1.0, ratio))
        base_rgb = [int(base[i:i + 2], 16) for i in range(0, 6, 2)]
        target_rgb = [int(target[i:i + 2], 16) for i in range(0, 6, 2)]
        mixed_rgb = [
            round(channel * (1 - ratio) + target_channel * ratio)
            for channel, target_channel in zip(base_rgb, target_rgb)
        ]
        return "#" + "".join(f"{channel:02x}" for channel in mixed_rgb)

    def _get_vocaloid_accent_colors(self, folder_name: str | None) -> tuple[str | tuple, str | tuple]:
        """返回指定 Vocaloid 分组的主强调色与悬浮色。"""
        if folder_name and folder_name in self.vocaloid_folder_accents:
            base_color = self.vocaloid_folder_accents[folder_name]
            hover_color = self._blend_hex_color(base_color, "#000000", 0.18)
            return base_color, hover_color

        # 默认返回中性色，确保未选中时没有颜色或混用蓝色
        return self.colors["surface_alt"], self.colors["surface_soft"]

    def _style_entry(self, entry):
        """统一输入框风格。"""
        entry.configure(
            fg_color=self.colors["input_bg"],
            border_color=self.colors["input_border"],
            text_color=self.colors["text_primary"],
        )

    def _style_textbox(self, textbox):
        """统一文本框风格。"""
        textbox.configure(
            fg_color=self.colors["surface_alt"],
            border_color=self.colors["input_border"],
            text_color=self.colors["text_primary"],
        )
        
    def setup_window_icon(self):
        """设置窗口图标"""
        try:
            icon_candidates = []
            bundle_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else ""
            for base_dir in [
                bundle_dir,
                getattr(self.app, "resource_root", ""),
                os.path.dirname(os.path.abspath(__file__)),
            ]:
                if not base_dir:
                    continue
                icon_candidates.extend(
                    [
                        os.path.join(base_dir, "icon.ico"),
                        os.path.join(base_dir, "icon.png"),
                    ]
                )

            for icon_path in icon_candidates:
                if not os.path.exists(icon_path):
                    continue
                if icon_path.lower().endswith(".ico"):
                    self.root.iconbitmap(icon_path)
                    return

                import tkinter as tk

                self._icon_photo = tk.PhotoImage(file=icon_path)
                self.root.iconphoto(False, self._icon_photo)
                return
        except Exception as e:
            print(f"设置窗口图标失败: {e}")
        
    def init_fonts(self):
        """初始化字体，在窗口创建后调用"""
        # 从配置中获取 UI 设置
        ui_settings = self.app.config.ui_settings
        self._register_fonts_from_directory()

        font_family = self._normalize_font_family(ui_settings.font_family)
        ui_settings.font_family = font_family
        
        # 优先更新已有字体对象，让已绑定控件也能同步刷新
        if hasattr(self, "custom_font"):
            self.custom_font.configure(family=font_family, size=ui_settings.font_size)
            self.title_font.configure(family=font_family, size=ui_settings.title_font_size)
            self.header_font.configure(family=font_family, size=ui_settings.font_size + 1)
        else:
            self.custom_font = ctk.CTkFont(family=font_family, size=ui_settings.font_size)
            self.title_font = ctk.CTkFont(family=font_family, size=ui_settings.title_font_size, weight="bold")
            self.header_font = ctk.CTkFont(family=font_family, size=ui_settings.font_size + 1, weight="bold")

        log_font_size = max(9, ui_settings.font_size)
        if hasattr(self, "log_font"):
            self.log_font.configure(family=font_family, size=log_font_size)
        else:
            self.log_font = tkfont.Font(self.root, family=font_family, size=log_font_size)

    def _normalize_font_family(self, font_family: str) -> str:
        """规范化字体家族名称，避免 Tk 在重新配置字体时抛错。"""
        family = (font_family or "").strip().strip("\"'")
        alias_map = {
            "microsoft yahei": "Microsoft YaHei",
            "微软雅黑": "Microsoft YaHei",
        }
        if not family:
            family = "Microsoft YaHei"
        family = alias_map.get(family.lower(), family)

        try:
            available_fonts = {name.lower(): name for name in tkfont.families(self.root)}
        except Exception:
            available_fonts = {}

        if available_fonts:
            resolved_family = available_fonts.get(family.lower())
            if resolved_family:
                return resolved_family
            fallback_family = available_fonts.get("microsoft yahei")
            if fallback_family:
                return fallback_family

        return family

    def _get_fonts_directory(self) -> str:
        """返回项目内 Fonts 目录的绝对路径。"""
        if hasattr(self.app, "_resolve_resource_path"):
            return self.app._resolve_resource_path("Fonts")
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "Fonts")

    def _get_font_file_candidates(self) -> list[str]:
        """获取 Fonts 目录下可用字体文件的相对路径列表。"""
        font_candidates = []
        fonts_directory = self._get_fonts_directory()
        if os.path.isdir(fonts_directory):
            for file_name in sorted(os.listdir(fonts_directory)):
                if not file_name.lower().endswith((".ttf", ".ttc", ".otf")):
                    continue
                absolute_path = os.path.join(fonts_directory, file_name)
                relative_path = os.path.relpath(absolute_path, os.path.dirname(os.path.abspath(__file__)))
                if relative_path not in font_candidates:
                    font_candidates.append(relative_path)
        return font_candidates

    def _resolve_project_path(self, path_value: str) -> str:
        """将配置中的相对路径解析为项目内绝对路径。"""
        if not path_value:
            return ""
        if hasattr(self.app, "_resolve_resource_path"):
            return self.app._resolve_resource_path(path_value)
        if os.path.isabs(path_value):
            return path_value
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), path_value)

    def _normalize_path_text(self, path_value: str) -> str:
        """规范化路径文本，避免不同分隔符导致比较失败。"""
        return os.path.normpath(path_value) if path_value else ""

    def _register_font_file(self, font_path: str) -> bool:
        """将字体文件临时注册到当前 Windows 会话，供 Tk 识别。"""
        absolute_path = self._resolve_project_path(font_path)
        if not absolute_path or not os.path.exists(absolute_path):
            return False
        if absolute_path in self._loaded_private_font_files:
            return True

        try:
            added = ctypes.windll.gdi32.AddFontResourceExW(absolute_path, 0x10, 0)
            if added:
                self._loaded_private_font_files.add(absolute_path)
                try:
                    ctypes.windll.user32.SendMessageW(0xFFFF, 0x001D, 0, 0)
                except Exception:
                    pass
                return True
        except Exception:
            return False
        return False

    def _register_fonts_from_directory(self):
        """注册 Fonts 目录中的字体文件，使其可用于界面字体。"""
        for relative_path in self._get_font_file_candidates():
            self._register_font_file(relative_path)

    def _get_font_family_from_file(self, relative_path: str) -> str:
        """从字体文件中读取字体家族名称。"""
        absolute_path = self._resolve_project_path(relative_path)
        if not absolute_path or not os.path.exists(absolute_path):
            return ""
        try:
            font = ImageFont.truetype(absolute_path, size=12)
            family_name = (font.getname() or ("", ""))[0]
            return family_name.strip()
        except Exception:
            return ""

    def _get_ui_font_options(self) -> list[str]:
        """获取适合作为界面字体的中文名称列表。"""
        return list(self._get_ui_font_mapping().keys())

    def _get_ui_font_mapping(self) -> dict[str, str]:
        """构建界面字体中文名称到系统字体名的映射。"""
        self._register_fonts_from_directory()
        preferred_fonts = [
            ("微软雅黑", "Microsoft YaHei"),
            ("黑体", "SimHei"),
            ("宋体", "SimSun"),
            ("楷体", "KaiTi"),
            ("仿宋", "FangSong"),
            ("幼圆", "YouYuan"),
            ("等线", "DengXian"),
        ]

        try:
            available_fonts = {name.lower(): name for name in tkfont.families(self.root)}
        except Exception:
            available_fonts = {}

        mapping: dict[str, str] = {}
        for label, font_name in preferred_fonts:
            resolved = available_fonts.get(font_name.lower())
            if resolved:
                mapping[label] = self._normalize_font_family(resolved)

        for relative_path in self._get_font_file_candidates():
            label = self._format_output_font_label(relative_path)
            family_name = self._get_font_family_from_file(relative_path)
            if not family_name:
                continue
            resolved = available_fonts.get(family_name.lower())
            normalized_family = self._normalize_font_family(resolved or family_name)
            if normalized_family in mapping.values():
                continue
            display_label = label
            if display_label in mapping:
                display_label = f"{display_label}（Fonts）"
            mapping[display_label] = normalized_family

        current_font = self._normalize_font_family(self.app.config.ui_settings.font_family)
        if current_font not in mapping.values():
            mapping[f"当前字体（{current_font}）"] = current_font

        if not mapping:
            mapping["微软雅黑"] = "Microsoft YaHei"

        return mapping

    def _get_output_font_options(self) -> list[str]:
        """获取可用于输出绘制的字体中文名称列表。"""
        return list(self._get_output_font_mapping().keys())

    def _get_output_font_mapping(self) -> dict[str, str]:
        """构建输出字体中文名称到字体文件路径的映射。"""
        font_candidates = self._get_font_file_candidates()

        current_font_file = self.app.config.font_file
        if current_font_file and current_font_file not in font_candidates:
            font_candidates.insert(0, current_font_file)

        mapping: dict[str, str] = {}
        for relative_path in font_candidates or [os.path.join("Fonts", "font.ttf")]:
            label = self._format_output_font_label(relative_path)
            if label in mapping:
                base_name = os.path.basename(relative_path)
                label = f"{label}（{base_name}）"
            mapping[label] = relative_path
        return mapping

    def _format_output_font_label(self, relative_path: str) -> str:
        """将输出字体文件路径转换为更易懂的中文名称。"""
        file_name = os.path.basename(relative_path)
        known_labels = {
            "font.ttf": "默认输出字体",
            "ZCOOLQingKeHuangYou-Regular.ttf": "站酷庆科黄油体",
            "ZCOOLKuaiLe-Regular.ttf": "站酷快乐体",
            "MaShanZheng-Regular.ttf": "马善政",
        }
        return known_labels.get(file_name, os.path.splitext(file_name)[0])

    def _get_safe_int_from_var(self, variable, fallback: int, minimum: int = 1, maximum: int = 72) -> int:
        """从 Tk 变量中安全读取整数，避免输入框临时状态导致无法写入。"""
        try:
            value = int(str(variable.get()).strip())
        except Exception:
            value = fallback
        return max(minimum, min(maximum, value))

    def _refresh_font_option_menus(self):
        """每次展开下拉前重新扫描 Fonts 目录并刷新字体选项。"""
        if not hasattr(self, "adv_ui_font_family_var") or not hasattr(self, "adv_font_file_var"):
            return

        current_ui_family = self.ui_font_value_map.get(
            self.adv_ui_font_family_var.get(),
            self.app.config.ui_settings.font_family,
        )
        current_output_font = self.output_font_value_map.get(
            self.adv_font_file_var.get(),
            self.app.config.font_file,
        )

        self.ui_font_value_map = self._get_ui_font_mapping()
        self.output_font_value_map = self._get_output_font_mapping()
        self.ui_font_options = list(self.ui_font_value_map.keys())
        self.output_font_options = list(self.output_font_value_map.keys())

        self.ui_font_option_menu.configure(values=self.ui_font_options)
        self.output_font_option_menu.configure(values=self.output_font_options)

        ui_label = next(
            (label for label, family in self.ui_font_value_map.items() if family == self._normalize_font_family(current_ui_family)),
            self.ui_font_options[0] if self.ui_font_options else "",
        )
        output_label = next(
            (
                label
                for label, path in self.output_font_value_map.items()
                if self._normalize_path_text(path) == self._normalize_path_text(current_output_font)
            ),
            self.output_font_options[0] if self.output_font_options else "",
        )

        if ui_label:
            self.adv_ui_font_family_var.set(ui_label)
        if output_label:
            self.adv_font_file_var.set(output_label)

    def _schedule_font_option_refresh(self, _event=None):
        """延迟刷新字体下拉，避免与 CTkOptionMenu 的点击展开冲突。"""
        if self._font_option_refresh_job is not None:
            try:
                self.root.after_cancel(self._font_option_refresh_job)
            except Exception:
                pass
        self._font_option_refresh_job = self.root.after(10, self._run_scheduled_font_option_refresh)

    def _run_scheduled_font_option_refresh(self):
        """执行排队的字体下拉刷新。"""
        self._font_option_refresh_job = None
        self._refresh_font_option_menus()

    def _bind_font_option_refresh(self, option_menu):
        """为字体下拉绑定安全的刷新时机。"""
        option_menu.bind("<Enter>", self._schedule_font_option_refresh, add="+")
        option_menu.bind("<FocusIn>", self._schedule_font_option_refresh, add="+")

    def _reset_advanced_textbox(self, textbox, content: str):
        """重置高级设置中的文本框内容。"""
        textbox.delete("0.0", "end")
        if content:
            textbox.insert("0.0", content)

    def _parse_emotion_hotkey_line(self, line: str) -> tuple[str, str] | None:
        """解析 `快捷键=表情标签`，兼容 `alt+=` 这类本身包含 `=` 的热键。"""
        raw_line = line.strip()
        if not raw_line:
            return None

        match = re.match(r"^(.*)=(#.*)$", raw_line)
        if match:
            hotkey = match.group(1).strip()
            emotion = match.group(2).strip()
            if hotkey and emotion:
                return hotkey, emotion

        if "=" not in raw_line:
            return None

        hotkey, emotion = raw_line.split("=", 1)
        hotkey = hotkey.strip()
        emotion = emotion.strip()
        if not hotkey or not emotion:
            return None
        return hotkey, emotion

    def _get_runtime_default_config(self) -> Config:
        """获取适配当前运行环境的默认配置。"""
        return Config()

    def _normalize_config_path_for_display(self, path_value: str) -> str:
        """将运行时绝对路径还原为适合展示/保存的相对路径。"""
        if not path_value:
            return ""
        if hasattr(self.app, "_normalize_persist_path"):
            return self.app._normalize_persist_path(path_value)
        return path_value

    def _build_reset_defaults_preview_text(self, default_config: Config) -> str:
        """构建恢复默认前展示的预览文本。"""
        preview_lines = [
            "将恢复以下内容：",
            "",
            f"界面字体大小: {default_config.ui_settings.font_size}",
            f"输出字体文件: {self._normalize_config_path_for_display(default_config.font_file)}",
            f"操作延迟: {default_config.delay}",
            f"日志等级: {default_config.logging_level}",
            f"发送快捷键: {default_config.send_hotkey}",
            "",
            "允许进程列表:",
            *[f"  {process}" for process in default_config.allowed_processes],
        ]
        return "\n".join(preview_lines)

    def _confirm_reset_defaults_preview(self, preview_text: str) -> bool:
        """弹出恢复默认预览窗口，二次确认后才执行恢复。"""
        parent_window = self.advanced_window if hasattr(self, "advanced_window") else self.root
        dialog = ctk.CTkToplevel(parent_window)
        dialog.title("恢复默认确认")
        dialog.geometry("520x560")
        dialog.resizable(False, False)
        dialog.transient(parent_window)
        dialog.grab_set()
        self.center_window(dialog, 520, 560)

        confirmed = {"value": False}
        preview_font = ("Microsoft YaHei", 11)

        ctk.CTkLabel(
            dialog,
            text="以下内容将恢复为默认值",
            font=ctk.CTkFont(family="Microsoft YaHei", size=15, weight="bold"),
        ).pack(padx=18, pady=(18, 10))

        preview_box = ctk.CTkTextbox(
            dialog,
            width=480,
            height=420,
            font=preview_font,
            fg_color=self.colors["surface"],
            text_color=self.colors["text_primary"],
            wrap="word",
        )
        preview_box.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        preview_box.insert("0.0", preview_text)
        preview_box.configure(state="disabled")

        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(fill="x", padx=18, pady=(0, 18))
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)

        def confirm_action():
            confirmed["value"] = True
            dialog.destroy()

        def cancel_action():
            dialog.destroy()

        ctk.CTkButton(
            button_frame,
            text="确定恢复",
            command=confirm_action,
            font=ctk.CTkFont(family="Microsoft YaHei", size=12),
            height=34,
            fg_color=self.colors["accent"],
            hover_color=self.colors["accent_hover"],
        ).grid(row=0, column=0, padx=(0, 8), sticky="ew")

        ctk.CTkButton(
            button_frame,
            text="取消",
            command=cancel_action,
            font=ctk.CTkFont(family="Microsoft YaHei", size=12),
            height=34,
            fg_color="transparent",
            border_width=2,
            border_color=self.colors["accent_secondary"],
            hover_color=self.colors["surface_soft"],
            text_color=self.colors["outline_text"],
        ).grid(row=0, column=1, padx=(8, 0), sticky="ew")

        dialog.wait_window()
        return confirmed["value"]

    def _apply_reset_default_values(self, default_config: Config):
        """将默认值填回高级设置界面。"""
        self._refresh_font_option_menus()

        default_ui_family = self._normalize_font_family(default_config.ui_settings.font_family)
        default_ui_label = next(
            (label for label, family in self.ui_font_value_map.items() if family == default_ui_family),
            self.adv_ui_font_family_var.get() if self.ui_font_options else "",
        )
        default_output_label = next(
            (
                label
                for label, path in self.output_font_value_map.items()
                if self._normalize_path_text(path) == self._normalize_path_text(default_config.font_file)
            ),
            self.adv_font_file_var.get() if self.output_font_options else "",
        )

        self.adv_ui_font_family_var.set(default_ui_label)
        self.adv_ui_font_size_var.set(default_config.ui_settings.font_size)
        self.adv_font_file_var.set(default_output_label)
        self.adv_delay_var.set(default_config.delay)
        self.adv_logging_level_var.set(default_config.logging_level)
        self.adv_send_hotkey_var.set(default_config.send_hotkey)

        self._reset_advanced_textbox(
            self.adv_allowed_processes_text,
            "\n".join(default_config.allowed_processes),
        )

    def reset_advanced_config_defaults(self):
        """将高级设置界面中的字段恢复为默认值。"""
        default_config = self._get_runtime_default_config()
        preview_text = self._build_reset_defaults_preview_text(default_config)
        if not self._confirm_reset_defaults_preview(preview_text):
            return

        self._apply_reset_default_values(default_config)

        messagebox.showinfo("恢复默认", "默认值已填回当前高级设置界面，点击“应用配置”或“保存并关闭”后生效。")

    def _get_safe_float_from_var(self, variable, fallback: float, minimum: float = 0.0, maximum: float = 10.0) -> float:
        """从 Tk 变量中安全读取浮点数，避免输入框临时状态导致无法写入。"""
        try:
            value = float(str(variable.get()).strip())
        except Exception:
            value = fallback
        return max(minimum, min(maximum, value))
        
    def setup_ui(self):
        # 创建notebook用于分隔配置和日志
        self.notebook = ctk.CTkTabview(
            self.root,
            fg_color=self.colors["window_bg"],
            segmented_button_selected_color=self.colors["accent"],
            segmented_button_selected_hover_color=self.colors["accent_hover"],
            segmented_button_unselected_color=self.colors["surface_alt"],
            segmented_button_unselected_hover_color=self.colors["surface_soft"],
            text_color=self.colors["text_primary"],
        )
        self.notebook.pack(fill="both", expand=True, padx=15, pady=15)
        
        # 添加标签页
        self.config_tab = self.notebook.add("配置")
        self.log_tab = self.notebook.add("日志")
        
        # 配置界面元素
        self.setup_config_ui()
        
        # 日志界面元素
        self.setup_log_ui()
        
        # 创建底部状态栏
        self.create_status_bar()
        self.sync_vocaloid_controls()
        
    def setup_config_ui(self):
        homepage = ctk.CTkFrame(self.config_tab, corner_radius=0, fg_color=self.colors["window_bg"])
        homepage.pack(fill="both", expand=True, padx=10, pady=10)
        homepage.grid_columnconfigure(0, weight=1)
        homepage.grid_columnconfigure(1, weight=0)
        homepage.grid_rowconfigure(1, weight=1)

        header_frame = ctk.CTkFrame(homepage, corner_radius=18, fg_color=self.colors["surface"])
        header_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ctk.CTkLabel(
            header_frame,
            text="冬里代的改版素描本 V1.1",
            font=self.title_font,
            text_color=self.colors["text_primary"],
            anchor="center",
            justify="center",
        ).pack(fill="x", padx=18, pady=(12, 10))

        main_panel = ctk.CTkFrame(homepage, corner_radius=18, fg_color=self.colors["surface"])
        main_panel.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        main_panel.grid_rowconfigure(0, weight=1)
        main_panel.grid_columnconfigure(0, weight=1)

        gallery_host = ctk.CTkFrame(main_panel, corner_radius=16, fg_color="transparent")
        gallery_host.grid(row=0, column=0, sticky="nsew", padx=6, pady=(4, 4))
        self.setup_vocaloid_gallery_ui(gallery_host)

        sidebar = ctk.CTkFrame(homepage, width=248, corner_radius=18, fg_color=self.colors["surface"])
        sidebar.grid(row=1, column=1, sticky="nse")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)

        self.auto_paste_var = ctk.BooleanVar(value=self.app.config.auto_paste_image)
        self.auto_send_var = ctk.BooleanVar(value=self.app.config.auto_send_image)
        self.block_hotkey_var = ctk.BooleanVar(value=self.app.config.block_hotkey)

        self._build_home_action_card(
            sidebar,
            "快速开关",
            [
                ("自动粘贴图片", self.auto_paste_var),
                ("自动发送图片", self.auto_send_var),
                ("阻塞热键", self.block_hotkey_var),
            ],
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 10))

        self._build_home_button_card(
            sidebar,
            "配置操作",
            [
                ("保存配置", self.save_config, self.colors["accent"], self.colors["accent_hover"]),
                ("应用配置", self.apply_config, self.colors["accent"], self.colors["accent_hover"]),
                ("高级配置", self.open_advanced_config, self.colors["accent"], self.colors["accent_hover"]),
                ("折叠到托盘", self.minimize, self.colors["accent_secondary"], self.colors["accent_secondary_hover"]),
            ],
        ).grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 14))

    def _build_home_action_card(self, parent, title: str, switch_items: list[tuple[str, ctk.BooleanVar]]):
        card = ctk.CTkFrame(parent, corner_radius=16, fg_color=self.colors["surface_alt"])
        ctk.CTkLabel(
            card,
            text=title,
            font=self.header_font,
            text_color=self.colors["text_primary"],
        ).pack(anchor="w", padx=14, pady=(12, 8))
        for label_text, variable in switch_items:
            ctk.CTkSwitch(
                card,
                text=label_text,
                variable=variable,
                font=self.custom_font,
                onvalue=True,
                offvalue=False,
                progress_color=self.colors["accent"],
            ).pack(anchor="w", padx=14, pady=(0, 8))
        return card

    def _build_home_button_card(self, parent, title: str, button_items: list[tuple[str, callable, str, str]]):
        card = ctk.CTkFrame(parent, corner_radius=16, fg_color=self.colors["surface_alt"])
        ctk.CTkLabel(
            card,
            text=title,
            font=self.header_font,
            text_color=self.colors["text_primary"],
        ).pack(anchor="w", padx=14, pady=(12, 8))
        button_grid = ctk.CTkFrame(card, fg_color="transparent")
        button_grid.pack(fill="x", padx=14, pady=(0, 12))
        button_grid.grid_columnconfigure(0, weight=1)
        button_grid.grid_columnconfigure(1, weight=1)
        for index, (label_text, callback, fg_color, hover_color) in enumerate(button_items):
            row = index // 2
            column = index % 2
            padx = (0, 6) if column == 0 else (6, 0)
            ctk.CTkButton(
                button_grid,
                text=label_text,
                command=callback,
                font=self.custom_font,
                corner_radius=10,
                height=38,
                fg_color=fg_color,
                hover_color=hover_color,
            ).grid(row=row, column=column, padx=padx, pady=(0, 8), sticky="ew")
        return card

    def setup_vocaloid_gallery_ui(self, parent):
        """在首页添加四个角色分组的切页与图片按钮。"""
        gallery_frame = ctk.CTkFrame(parent, corner_radius=14, fg_color="transparent")
        gallery_frame.pack(fill="both", expand=True, padx=2, pady=0)
        gallery_frame.grid_rowconfigure(2, weight=1)
        gallery_frame.grid_columnconfigure(0, weight=1)

        self.vocaloid_tabview = ctk.CTkTabview(
            gallery_frame,
            fg_color="transparent",
            segmented_button_selected_color=self.colors["surface_alt"][0],
            segmented_button_selected_hover_color=self.colors["surface_soft"][0],
            segmented_button_unselected_color=self.colors["surface_alt"],
            segmented_button_unselected_hover_color=self.colors["surface_soft"],
            text_color=self.colors["text_primary"],
            command=self._on_vocaloid_tab_changed
        )
        self.vocaloid_tabview.pack(fill="both", expand=True, padx=2, pady=(0, 2))

        if not self.app.vocaloid_gallery:
            empty_frame = self.vocaloid_tabview.add("无资源")
            ctk.CTkLabel(
                empty_frame,
                text="未找到 VocaloidImage 素材目录",
                font=self.custom_font,
                text_color=self.colors["text_muted"],
            ).pack(padx=16, pady=16)
            return

        for folder_name in self.app.vocaloid_gallery.keys():
            tab = self.vocaloid_tabview.add(folder_name)
            tab.configure(fg_color="transparent")
            self.vocaloid_tabs[folder_name] = tab
            button_frame = self._build_vocaloid_gallery_panel(tab, folder_name)
            self.vocaloid_button_frames[folder_name] = button_frame

        self.root.after(300, self._preload_all_vocaloid_backgrounds)

    def _build_vocaloid_gallery_panel(self, tab, folder_name: str):
        """为分组构建基于 Canvas 的海报展示区。"""
        background_source = self._get_gallery_background_source(folder_name)
        if background_source:
            container_frame = ctk.CTkFrame(
                tab,
                corner_radius=10,
                fg_color="transparent",
            )
            container_frame.pack(fill="both", expand=True, padx=0, pady=2)
            container_frame.grid_columnconfigure(0, weight=1)
            container_frame.grid_rowconfigure(0, weight=1)
            self.vocaloid_scroll_frames[folder_name] = container_frame

            background_canvas = tk.Canvas(
                container_frame,
                highlightthickness=0,
                bd=0,
                relief="flat",
                background=self.colors["surface"][0] if isinstance(self.colors["surface"], tuple) else self.colors["surface"],
                cursor="hand2",
            )
            background_canvas.grid(row=0, column=0, sticky="nsew")

            canvas_scrollbar = ctk.CTkScrollbar(
                container_frame,
                orientation="vertical",
                command=background_canvas.yview,
                button_color=self.colors["surface_soft"],
                button_hover_color=self.colors["accent_hover"],
            )
            canvas_scrollbar.grid(row=0, column=1, sticky="ns", padx=(6, 0))
            background_canvas.configure(yscrollcommand=canvas_scrollbar.set)

            background_canvas.bind(
                "<Button-1>",
                lambda event, current_folder=folder_name: self._handle_vocaloid_surface_click(event, current_folder),
            )

            self.vocaloid_background_labels[folder_name] = background_canvas
            self.vocaloid_background_canvases[folder_name] = background_canvas
            self.vocaloid_background_containers[folder_name] = container_frame
            self.vocaloid_background_sources[folder_name] = background_source
            self.vocaloid_button_frames[folder_name] = background_canvas

            background_canvas.bind(
                "<Configure>",
                lambda event, current_folder=folder_name: self._refresh_vocaloid_background(current_folder, event.width, event.height),
                add="+",
            )
            self._bind_vocaloid_canvas_mousewheel(background_canvas)
            self.root.after(50, lambda current_folder=folder_name: self._refresh_vocaloid_background(current_folder))
            return background_canvas

        button_frame = ctk.CTkFrame(tab, corner_radius=10, fg_color=self.colors["surface_alt"])
        button_frame.pack(fill="x", padx=8, pady=10)
        for column in range(self.vocaloid_button_columns):
            button_frame.grid_columnconfigure(column, weight=1)
        return button_frame

    def open_advanced_config(self):
        """打开高级配置窗口"""
        # 创建高级配置窗口
        self.advanced_window = ctk.CTkToplevel(self.root)
        self.advanced_window.title("高级配置")
        self.advanced_window.geometry("600x500")
        self.advanced_window.resizable(True, True)
        self.advanced_window.configure(fg_color=self.colors["window_bg"])
        self.advanced_window.transient(self.root)  # 设置为父窗口的临时窗口
        self.advanced_window.grab_set()  # 模态窗口
        
        # 居中显示
        self.center_window(self.advanced_window, 600, 500)
        
        # 创建标签页控件
        advanced_notebook = ctk.CTkTabview(
            self.advanced_window,
            fg_color=self.colors["window_bg"],
            segmented_button_selected_color=self.colors["accent"],
            segmented_button_selected_hover_color=self.colors["accent_hover"],
            segmented_button_unselected_color=self.colors["surface_alt"],
            segmented_button_unselected_hover_color=self.colors["surface_soft"],
            text_color=self.colors["text_primary"],
        )
        advanced_notebook.pack(fill="both", expand=True, padx=15, pady=15)
        
        # 添加各个配置标签页
        general_tab = advanced_notebook.add("通用设置")
        shortcuts_tab = advanced_notebook.add("快捷键设置")
        process_tab = advanced_notebook.add("进程设置")
        
        # 设置各个配置标签页
        self.setup_general_advanced_config(general_tab)
        self.setup_shortcuts_advanced_config(shortcuts_tab)
        self.setup_process_advanced_config(process_tab)
        
        # 创建按钮框架
        button_frame = ctk.CTkFrame(self.advanced_window, corner_radius=10, fg_color=self.colors["surface"])
        button_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        for column in range(4):
            button_frame.grid_columnconfigure(column, weight=1)

        ctk.CTkButton(
            button_frame,
            text="保存并关闭",
            command=self.save_advanced_config_and_close,
            font=self.custom_font,
            corner_radius=8,
            height=35,
            fg_color=self.colors["accent"],
            hover_color=self.colors["accent_hover"]
        ).grid(row=0, column=0, padx=8, pady=15, sticky="ew")

        ctk.CTkButton(
            button_frame,
            text="应用配置",
            command=self.apply_advanced_config,
            font=self.custom_font,
            corner_radius=8,
            height=35,
            fg_color=self.colors["accent"],
            hover_color=self.colors["accent_hover"]
        ).grid(row=0, column=1, padx=8, pady=15, sticky="ew")

        ctk.CTkButton(
            button_frame,
            text="恢复默认",
            command=self.reset_advanced_config_defaults,
            font=self.custom_font,
            corner_radius=8,
            height=35,
            fg_color=self.colors["accent_secondary"],
            hover_color=self.colors["accent_secondary_hover"]
        ).grid(row=0, column=2, padx=8, pady=15, sticky="ew")

        ctk.CTkButton(
            button_frame,
            text="取消",
            command=self.advanced_window.destroy,
            font=self.custom_font,
            corner_radius=8,
            height=35,
            fg_color="transparent",
            border_width=2,
            border_color=self.colors["accent_secondary"],
            hover_color=self.colors["surface_soft"],
            text_color=self.colors["outline_text"]
        ).grid(row=0, column=3, padx=8, pady=15, sticky="ew")
        
    def center_window(self, window, width, height):
        """居中显示窗口"""
        # 获取屏幕尺寸
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        
        # 计算居中位置
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        
        # 设置窗口位置和大小
        window.geometry(f'{width}x{height}+{x}+{y}')
        
    def setup_general_advanced_config(self, parent):
        """设置通用配置"""
        # 创建滚动框架
        scrollable_frame = ctk.CTkScrollableFrame(parent, corner_radius=10, fg_color=self.colors["window_bg"])
        scrollable_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # 界面字体配置
        ui_font_frame = ctk.CTkFrame(scrollable_frame, corner_radius=8, fg_color=self.colors["surface"])
        ui_font_frame.pack(fill="x", pady=5, padx=5)
        ctk.CTkLabel(ui_font_frame, text="界面字体:", font=self.custom_font).pack(side="left", padx=10, pady=10)
        current_ui_font = self._normalize_font_family(self.app.config.ui_settings.font_family)
        self.app.config.ui_settings.font_family = current_ui_font
        self.ui_font_value_map = self._get_ui_font_mapping()
        current_ui_label = next(
            (label for label, family in self.ui_font_value_map.items() if family == current_ui_font),
            f"当前字体（{current_ui_font}）",
        )
        self.adv_ui_font_family_var = ctk.StringVar(value=current_ui_label)
        self.ui_font_options = list(self.ui_font_value_map.keys())
        self.ui_font_option_menu = ctk.CTkOptionMenu(
            ui_font_frame,
            values=self.ui_font_options,
            variable=self.adv_ui_font_family_var,
            width=300,
            font=self.custom_font,
            dynamic_resizing=False,
            fg_color=self.colors["surface_alt"],
            button_color=self.colors["accent"],
            button_hover_color=self.colors["accent_hover"],
            text_color=self.colors["text_primary"],
        )
        self.ui_font_option_menu.pack(side="right", padx=10, pady=10)
        self._bind_font_option_refresh(self.ui_font_option_menu)

        ui_font_size_frame = ctk.CTkFrame(scrollable_frame, corner_radius=8, fg_color=self.colors["surface"])
        ui_font_size_frame.pack(fill="x", pady=5, padx=5)
        ctk.CTkLabel(ui_font_size_frame, text="界面字体大小:", font=self.custom_font).pack(side="left", padx=10, pady=10)
        self.adv_ui_font_size_var = ctk.IntVar(value=self.app.config.ui_settings.font_size)
        font_size_entry = ctk.CTkEntry(ui_font_size_frame, textvariable=self.adv_ui_font_size_var, width=300, font=self.custom_font)
        self._style_entry(font_size_entry)
        font_size_entry.pack(side="right", padx=10, pady=10)
        
        # 字体文件配置
        font_frame = ctk.CTkFrame(scrollable_frame, corner_radius=8, fg_color=self.colors["surface"])
        font_frame.pack(fill="x", pady=5, padx=5)
        ctk.CTkLabel(font_frame, text="输出字体文件:", font=self.custom_font).pack(side="left", padx=10, pady=10)
        self.output_font_value_map = self._get_output_font_mapping()
        current_output_label = next(
            (
                label
                for label, path in self.output_font_value_map.items()
                if self._normalize_path_text(path) == self._normalize_path_text(self.app.config.font_file)
            ),
            self._format_output_font_label(self.app.config.font_file),
        )
        self.adv_font_file_var = ctk.StringVar(value=current_output_label)
        self.output_font_options = list(self.output_font_value_map.keys())
        self.output_font_option_menu = ctk.CTkOptionMenu(
            font_frame,
            values=self.output_font_options,
            variable=self.adv_font_file_var,
            width=300,
            font=self.custom_font,
            dynamic_resizing=False,
            fg_color=self.colors["surface_alt"],
            button_color=self.colors["accent"],
            button_hover_color=self.colors["accent_hover"],
            text_color=self.colors["text_primary"],
        )
        self.output_font_option_menu.pack(side="right", padx=10, pady=10)
        self._bind_font_option_refresh(self.output_font_option_menu)
        ctk.CTkLabel(
            scrollable_frame,
            text="用于绘制到底图上的文字，不影响程序界面字体。",
            font=("Microsoft YaHei", 10),
            text_color=self.colors["text_muted"],
        ).pack(anchor="w", padx=12, pady=(0, 6))

        # 操作延迟配置
        delay_frame = ctk.CTkFrame(scrollable_frame, corner_radius=8, fg_color=self.colors["surface"])
        delay_frame.pack(fill="x", pady=5, padx=5)
        ctk.CTkLabel(delay_frame, text="操作延迟(秒):", font=self.custom_font).pack(side="left", padx=10, pady=10)
        self.adv_delay_var = ctk.DoubleVar(value=self.app.config.delay)
        delay_entry = ctk.CTkEntry(delay_frame, textvariable=self.adv_delay_var, width=300, font=self.custom_font)
        self._style_entry(delay_entry)
        delay_entry.pack(side="right", padx=10, pady=10)
        
        # 日志等级配置
        log_frame = ctk.CTkFrame(scrollable_frame, corner_radius=8, fg_color=self.colors["surface"])
        log_frame.pack(fill="x", pady=5, padx=5)
        ctk.CTkLabel(log_frame, text="日志等级:", font=self.custom_font).pack(side="left", padx=10, pady=10)
        self.adv_logging_level_var = ctk.StringVar(value=self.app.config.logging_level)
        log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        log_option = ctk.CTkOptionMenu(log_frame, values=log_levels, variable=self.adv_logging_level_var, font=self.custom_font,
                                       fg_color=self.colors["surface_alt"], button_color=self.colors["accent"],
                                       button_hover_color=self.colors["accent_hover"], text_color=self.colors["text_primary"])
        log_option.pack(side="right", padx=10, pady=10)
        
    def setup_shortcuts_advanced_config(self, parent):
        """设置快捷键配置"""
        # 创建滚动框架
        scrollable_frame = ctk.CTkScrollableFrame(parent, corner_radius=10, fg_color=self.colors["window_bg"])
        scrollable_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 全选快捷键配置
        select_all_frame = ctk.CTkFrame(scrollable_frame, corner_radius=8, fg_color=self.colors["surface"])
        select_all_frame.pack(fill="x", pady=5, padx=5)
        ctk.CTkLabel(select_all_frame, text="全选快捷键:", font=self.custom_font).pack(side="left", padx=10, pady=10)
        self.adv_select_all_hotkey_var = ctk.StringVar(value=self.app.config.select_all_hotkey)
        select_all_entry = ctk.CTkEntry(select_all_frame, textvariable=self.adv_select_all_hotkey_var, width=200, font=self.custom_font)
        self._style_entry(select_all_entry)
        select_all_entry.pack(side="right", padx=10, pady=10)
        
        # 剪切快捷键配置
        cut_frame = ctk.CTkFrame(scrollable_frame, corner_radius=8, fg_color=self.colors["surface"])
        cut_frame.pack(fill="x", pady=5, padx=5)
        ctk.CTkLabel(cut_frame, text="剪切快捷键:", font=self.custom_font).pack(side="left", padx=10, pady=10)
        self.adv_cut_hotkey_var = ctk.StringVar(value=self.app.config.cut_hotkey)
        cut_entry = ctk.CTkEntry(cut_frame, textvariable=self.adv_cut_hotkey_var, width=200, font=self.custom_font)
        self._style_entry(cut_entry)
        cut_entry.pack(side="right", padx=10, pady=10)
        
        # 黏贴快捷键配置
        paste_frame = ctk.CTkFrame(scrollable_frame, corner_radius=8, fg_color=self.colors["surface"])
        paste_frame.pack(fill="x", pady=5, padx=5)
        ctk.CTkLabel(paste_frame, text="黏贴快捷键:", font=self.custom_font).pack(side="left", padx=10, pady=10)
        self.adv_paste_hotkey_var = ctk.StringVar(value=self.app.config.paste_hotkey)
        paste_entry = ctk.CTkEntry(paste_frame, textvariable=self.adv_paste_hotkey_var, width=200, font=self.custom_font)
        self._style_entry(paste_entry)
        paste_entry.pack(side="right", padx=10, pady=10)
        
        # 发送快捷键配置
        send_frame = ctk.CTkFrame(scrollable_frame, corner_radius=8, fg_color=self.colors["surface"])
        send_frame.pack(fill="x", pady=5, padx=5)
        ctk.CTkLabel(send_frame, text="发送快捷键:", font=self.custom_font).pack(side="left", padx=10, pady=10)
        self.adv_send_hotkey_var = ctk.StringVar(value=self.app.config.send_hotkey)
        send_entry = ctk.CTkEntry(send_frame, textvariable=self.adv_send_hotkey_var, width=200, font=self.custom_font)
        self._style_entry(send_entry)
        send_entry.pack(side="right", padx=10, pady=10)
        
    def setup_process_advanced_config(self, parent):
        """设置进程配置"""
        frame = ctk.CTkFrame(parent, corner_radius=10, fg_color=self.colors["surface"])
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        ctk.CTkLabel(frame, text="允许运行此程序的进程列表", font=self.header_font, text_color=self.colors["text_primary"]).pack(pady=10)
        ctk.CTkLabel(frame, text="每行输入一个进程名称，例如: qq.exe", font=("Microsoft YaHei", 10), text_color=self.colors["text_muted"]).pack()
        
        # 创建文本框用于输入进程列表
        self.adv_allowed_processes_text = ctk.CTkTextbox(frame, font=("Microsoft YaHei", 10), height=200)
        self._style_textbox(self.adv_allowed_processes_text)
        self.adv_allowed_processes_text.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 填充当前配置
        processes_text = "\n".join(self.app.config.allowed_processes)
        self.adv_allowed_processes_text.insert("0.0", processes_text)
        
    def save_advanced_config_and_close(self):
        """保存高级配置并关闭窗口"""
        if self.apply_advanced_config(show_message=False):
            try:
                self.app.save_current_config()
                messagebox.showinfo("成功", "高级配置已保存并同步到全局")
                self.advanced_window.destroy()
            except Exception as e:
                logging.exception("保存高级配置时出错")
                messagebox.showerror("错误", f"保存高级配置时出错: {str(e)}")
        
    def apply_advanced_config(self, show_message: bool = True):
        """应用高级配置"""
        try:
            previous_ui_font_family = self.app.config.ui_settings.font_family
            previous_ui_font_size = self.app.config.ui_settings.font_size
            previous_runtime_state = {
                "delay": self.app.config.delay,
                "select_all_hotkey": self.app.config.select_all_hotkey,
                "cut_hotkey": self.app.config.cut_hotkey,
                "paste_hotkey": self.app.config.paste_hotkey,
                "send_hotkey": self.app.config.send_hotkey,
                "allowed_processes": list(self.app.config.allowed_processes),
            }

            # 更新通用配置
            selected_output_font = self.output_font_value_map.get(
                self.adv_font_file_var.get(),
                self.app.config.font_file,
            )
            if selected_output_font and not os.path.exists(self._resolve_project_path(selected_output_font)):
                logging.warning(f"输出字体文件不存在，继续使用当前字体：{selected_output_font}")
            else:
                self.app.config.font_file = selected_output_font
            self.app.config.delay = self._get_safe_float_from_var(
                self.adv_delay_var,
                self.app.config.delay,
                minimum=0.0,
                maximum=5.0,
            )
            self.app.config.logging_level = self.adv_logging_level_var.get()
            
            # 更新快捷键配置
            self.app.config.select_all_hotkey = self.adv_select_all_hotkey_var.get()
            self.app.config.cut_hotkey = self.adv_cut_hotkey_var.get()
            self.app.config.paste_hotkey = self.adv_paste_hotkey_var.get()
            self.app.config.send_hotkey = self.adv_send_hotkey_var.get()
            
            # 更新进程配置
            processes_text = self.adv_allowed_processes_text.get("0.0", "end").strip()
            self.app.config.allowed_processes = [p.strip() for p in processes_text.split("\n") if p.strip()]
            
            # 更新界面配置
            self.app.config.ui_settings.font_family = self.ui_font_value_map.get(
                self.adv_ui_font_family_var.get(),
                self.app.config.ui_settings.font_family,
            )
            self.app.config.ui_settings.font_size = self._get_safe_int_from_var(
                self.adv_ui_font_size_var,
                self.app.config.ui_settings.font_size,
                minimum=8,
                maximum=32,
            )

            ui_log_level = getattr(logging, self.app.config.logging_level.upper(), logging.INFO)
            self.log_handler.setLevel(ui_log_level)
            third_party_level = logging.DEBUG if ui_log_level == logging.DEBUG else logging.INFO
            logging.getLogger("PIL").setLevel(third_party_level)
            logging.getLogger("customtkinter").setLevel(third_party_level)

            ui_font_changed = (
                previous_ui_font_family != self.app.config.ui_settings.font_family
                or previous_ui_font_size != self.app.config.ui_settings.font_size
            )
            if ui_font_changed:
                self.init_fonts()
                self.log_text.configure(font=self.log_font)

            current_runtime_state = {
                "delay": self.app.config.delay,
                "select_all_hotkey": self.app.config.select_all_hotkey,
                "cut_hotkey": self.app.config.cut_hotkey,
                "paste_hotkey": self.app.config.paste_hotkey,
                "send_hotkey": self.app.config.send_hotkey,
                "allowed_processes": list(self.app.config.allowed_processes),
            }
            runtime_sync_needed = ui_font_changed or current_runtime_state != previous_runtime_state
            if runtime_sync_needed:
                self.app.apply_runtime_config_changes()
            
            # 显示成功消息
            if show_message:
                messagebox.showinfo("成功", "高级配置已应用并同步到当前运行状态")
            return True
            
        except Exception as e:
            logging.exception("应用高级配置时出错")
            messagebox.showerror("错误", f"应用配置时出错: {str(e)}")
            return False
        
    def setup_log_ui(self):
        # 日志显示区域
        log_text_frame = ctk.CTkFrame(self.log_tab, corner_radius=10, fg_color=self.colors["surface"])
        log_text_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 添加日志标题
        log_header_frame = ctk.CTkFrame(log_text_frame, corner_radius=8, fg_color=self.colors["surface_soft"])
        log_header_frame.pack(fill="x", padx=10, pady=(10, 5))
        
        ctk.CTkLabel(
            log_header_frame,
            text="运行日志",
            font=self.header_font,
            text_color=self.colors["text_primary"],
            anchor="center",
            justify="center",
        ).pack(padx=10, pady=10)
        
        self.log_text = scrolledtext.ScrolledText(
            log_text_frame, 
            state='disabled', 
            wrap='word',
            height=10,
            bg=self._theme_color("log_bg"),
            fg=self._theme_color("log_fg"),
            font=self.log_font
        )
        self.log_text.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        # 日志控制按钮
        log_control_frame = ctk.CTkFrame(self.log_tab, corner_radius=10, fg_color=self.colors["surface"])
        log_control_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkButton(
            log_control_frame, 
            text="清空日志", 
            command=self.clear_log, 
            font=self.custom_font,
            corner_radius=8,
            height=35,
            fg_color=self.colors["accent"],
            hover_color=self.colors["accent_hover"]
        ).pack(side="left", padx=(20, 10), pady=15)
        
        ctk.CTkButton(
            log_control_frame, 
            text="折叠到托盘", 
            command=self.minimize, 
            font=self.custom_font,
            corner_radius=8,
            height=35,
            fg_color=self.colors["accent_secondary"],
            hover_color=self.colors["accent_secondary_hover"]
        ).pack(side="right", padx=(10, 20), pady=15)
        
    def create_status_bar(self):
        """创建底部状态栏"""
        self.status_frame = ctk.CTkFrame(self.root, height=34, corner_radius=0, fg_color=self.colors["surface"])
        self.status_frame.pack(fill="x", side="bottom", padx=0, pady=0)
        self.status_frame.pack_propagate(False)
        
        self.status_label = ctk.CTkLabel(
            self.status_frame, 
            text="就绪", 
            font=ctk.CTkFont(size=12),
            text_color=self.colors["text_primary"]
        )
        self.status_label.pack(side="left", padx=15, pady=5)
        
        self.expression_label = ctk.CTkLabel(
            self.status_frame,
            text=f"表情：{self.app.active_vocaloid_expression or '未选择'}",
            font=ctk.CTkFont(size=12),
            text_color=self.colors["text_primary"]
        )
        self.expression_label.pack(side="right", padx=(10, 10), pady=5)
        
        self.folder_label = ctk.CTkLabel(
            self.status_frame,
            text=f"分组：{self.app.active_vocaloid_folder or '未选择'}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.colors["mode_button"]
        )
        self.folder_label.pack(side="right", padx=(10, 15), pady=5)
        
        # 显示当前热键
        hotkey_info = ctk.CTkLabel(
            self.status_frame,
            text=f"热键：{self.app.config.hotkey}",
            font=ctk.CTkFont(size=12),
            text_color=self.colors["text_primary"]
        )
        hotkey_info.pack(side="right", padx=15, pady=5)
        
    def update_status(self, message: str):
        """更新状态栏信息"""
        self._run_on_ui_thread(self._update_status_impl, message)
    
    def sync_vocaloid_controls(self):
        """刷新 Vocaloid 分页按钮与当前选中状态。"""
        self._run_on_ui_thread(self._sync_vocaloid_controls_impl)

    def _run_on_ui_thread(self, callback, *args):
        if threading.current_thread() is threading.main_thread():
            callback(*args)
        else:
            self.root.after(0, lambda: callback(*args))

    def _update_status_impl(self, message: str):
        self.status_label.configure(text=message)
        self.root.update_idletasks()

    def _on_vocaloid_tab_changed(self):
        """当用户点击角色页签时触发，同步更新 UI 强调色并刷新布局。"""
        folder_name = self.vocaloid_tabview.get()
        # 切页后尽快刷新当前可见分组，减少等待感。
        self.root.after_idle(lambda current_folder=folder_name: self._refresh_vocaloid_background(current_folder))
        self._sync_vocaloid_controls_impl()

    def _sync_vocaloid_controls_impl(self):
        if not hasattr(self, "vocaloid_tabview"):
            return

        if not self.app.vocaloid_gallery:
            self.folder_label.configure(text="分组：未找到")
            self.folder_label.configure(text_color=self.colors["mode_button"])
            self.expression_label.configure(text="表情：未选择")
            self.vocaloid_tabview.configure(
                segmented_button_selected_color=self.colors["surface_alt"],
                segmented_button_selected_hover_color=self.colors["surface_soft"],
            )
            return

        # 获取当前正在查看的分组（页签）
        visible_folder = self.vocaloid_tabview.get()
        accent_color, accent_hover_color = self._get_vocaloid_accent_colors(visible_folder)

        # 始终确保页签高亮色与当前展示的分组一致，解决切换时颜色混用问题
        self.vocaloid_tabview.configure(
            segmented_button_selected_color=accent_color,
            segmented_button_selected_hover_color=accent_hover_color,
        )

        if self.app.has_active_vocaloid_selection():
            active_accent_color, _ = self._get_vocaloid_accent_colors(
                self.app.active_vocaloid_folder
            )
            self.folder_label.configure(text=f"分组：{self.app.active_vocaloid_folder}")
            self.folder_label.configure(text_color=active_accent_color)
            self.expression_label.configure(text=f"表情：{self.app.active_vocaloid_expression}")
        else:
            self.folder_label.configure(text="分组：未选择")
            self.folder_label.configure(text_color=self.colors["mode_button"])
            self.expression_label.configure(text="表情：未选择")

        refresh_targets = {visible_folder}
        if self.app.active_vocaloid_folder:
            refresh_targets.add(self.app.active_vocaloid_folder)
        for folder_name in refresh_targets:
            if folder_name in self.vocaloid_background_labels:
                self._refresh_vocaloid_background(folder_name)

    def _get_gallery_background_source(self, folder_name: str) -> str:
        """返回指定分组的背景海报图路径。"""
        folder_info = self.app.vocaloid_gallery.get(folder_name, {})
        folder_path = folder_info.get("folder_path", "")
        if folder_path and os.path.isdir(folder_path):
            preferred_candidates = []
            fallback_candidates = []
            for file_name in sorted(os.listdir(folder_path)):
                absolute_path = os.path.join(folder_path, file_name)
                if not os.path.isfile(absolute_path):
                    continue
                stem, ext = os.path.splitext(file_name)
                if ext.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
                    continue
                if stem == "001置顶图层":
                    continue
                if stem == folder_name or stem.endswith(folder_name):
                    preferred_candidates.append(absolute_path)
                else:
                    fallback_candidates.append(absolute_path)

            if preferred_candidates:
                return preferred_candidates[0]
            if fallback_candidates:
                return fallback_candidates[0]

        expressions = folder_info.get("expressions", {})
        if "标准" in expressions:
            return expressions["标准"]
        return next(iter(expressions.values()), "")

    def _get_vocaloid_layout_metrics(self, folder_name: str) -> tuple[int, int]:
        """返回分组对应的按钮列数与按钮尺寸。"""
        if folder_name in self.vocaloid_background_labels:
            return 3, 72
        return self.vocaloid_button_columns, self.vocaloid_button_size

    def _refresh_vocaloid_background(self, folder_name: str, width: int | None = None, height: int | None = None):
        """根据容器尺寸刷新分组合成图，统一绘制海报、缩略图、蒙版和文字。"""
        background_canvas = self.vocaloid_background_canvases.get(folder_name)
        background_container = self.vocaloid_background_containers.get(folder_name)
        background_source = self.vocaloid_background_sources.get(folder_name)
        if background_canvas is None or background_container is None or not background_source or not os.path.exists(background_source):
            return

        source_size = self.vocaloid_background_source_sizes.get(folder_name)
        if source_size is None:
            try:
                with Image.open(background_source) as source_image:
                    source_size = source_image.size
                self.vocaloid_background_source_sizes[folder_name] = source_size
            except Exception:
                source_size = (3, 4)
        target_width = max(1, int(width or background_canvas.winfo_width()))
        if target_width < 120:
            self.root.update_idletasks()
            target_width = max(640, self.root.winfo_width() - 60)

        target_height = self._get_poster_container_height(source_size, target_width)
        self.vocaloid_poster_rects[folder_name] = self._get_centered_poster_rect(
            source_size,
            (target_width, target_height),
        )

        base_cache_key = (folder_name, target_width, target_height)
        prev_key = self._current_base_key.get(folder_name)
        if prev_key is not None and prev_key != base_cache_key:
            stale_base = [k for k in self.vocaloid_base_surfaces if k[0] == folder_name and k != base_cache_key]
            for k in stale_base:
                del self.vocaloid_base_surfaces[k]
            stale_photo = [k for k in self.vocaloid_background_images if k[0] == folder_name and k[1:3] != (target_width, target_height)]
            for k in stale_photo:
                del self.vocaloid_background_images[k]
            stale_thumb = [k for k in self._thumbnail_card_cache if k[0] == folder_name]
            for k in stale_thumb:
                del self._thumbnail_card_cache[k]
        self._current_base_key[folder_name] = base_cache_key

        base_surface = self.vocaloid_base_surfaces.get(base_cache_key)
        if base_surface is None:
            try:
                source_image = Image.open(background_source).convert("RGBA")
                self.vocaloid_background_source_sizes[folder_name] = source_image.size
                background_image, poster_rect = self._build_gallery_background_image(
                    folder_name, source_image, (target_width, target_height)
                )
                self.vocaloid_poster_rects[folder_name] = poster_rect
                base_surface = self._build_vocaloid_gallery_surface_image(
                    folder_name,
                    background_image,
                    (target_width, target_height),
                    with_overlay=False,
                )
                self.vocaloid_base_surfaces[base_cache_key] = base_surface
            except Exception as exc:
                logging.debug("角色背景图刷新失败: folder=%s, error=%s", folder_name, exc)
                return

        photo_key = (
            folder_name,
            target_width,
            target_height,
            self.app.active_vocaloid_folder,
            self.app.active_vocaloid_expression,
        )
        tk_image = self.vocaloid_background_images.get(photo_key)
        if tk_image is not None:
            self._render_vocaloid_canvas_image(folder_name, tk_image, target_width, target_height)
            return

        try:
            overlay_surface = self._apply_vocaloid_gallery_overlay(folder_name, base_surface)
            tk_image = ImageTk.PhotoImage(overlay_surface)
            self.vocaloid_background_images[photo_key] = tk_image
            keys = [k for k in self.vocaloid_background_images if k[0] == folder_name]
            if len(keys) > 6:
                for k in keys[:-6]:
                    del self.vocaloid_background_images[k]
            self._render_vocaloid_canvas_image(folder_name, tk_image, target_width, target_height)
        except Exception as exc:
            logging.debug("角色覆盖层合成失败: folder=%s, error=%s", folder_name, exc)

    def _preload_all_vocaloid_backgrounds(self):
        """启动后逐角色预加载所有底图与缺省表情合成图，减少切页等待。"""
        if not self.app.vocaloid_gallery:
            return
        folders = list(self.vocaloid_background_canvases.keys())
        if not folders:
            return

        def _load_next(idx: int = 0):
            if idx >= len(folders):
                return
            folder_name = folders[idx]
            self._refresh_vocaloid_background(folder_name)
            self.root.after(10, lambda: _load_next(idx + 1))

        _load_next(0)

    def _adapt_gallery_panel_layout(self, folder_name: str, width: int, height: int):
        """单图合成模式下不再需要独立卡片布局刷新。"""
        return

    def _get_centered_poster_rect(
        self,
        source_size: tuple[int, int],
        target_size: tuple[int, int],
    ) -> tuple[int, int, int, int]:
        """计算海报在容器内等比缩放后的居中区域。"""
        source_width, source_height = source_size
        target_width, target_height = target_size
        scale = min(target_width / max(source_width, 1), target_height / max(source_height, 1))
        poster_width = min(target_width, max(1, int(round(source_width * scale))))
        poster_height = min(target_height, max(1, int(round(source_height * scale))))
        poster_left = max(0, (target_width - poster_width) // 2)
        poster_top = max(0, (target_height - poster_height) // 2)
        return poster_left, poster_top, poster_width, poster_height

    def _get_poster_container_height(
        self,
        source_size: tuple[int, int],
        target_width: int,
    ) -> int:
        """根据海报原始宽高比计算容器高度，保证海报完整显示且不失真。"""
        source_width, source_height = source_size
        aspect_ratio = source_height / max(source_width, 1)
        return max(240, int(round(target_width * aspect_ratio)))

    def _get_layout_source_size(self, folder_name: str) -> tuple[int, int]:
        """返回当前分组海报的原始尺寸，作为按钮布局的统一坐标系。"""
        return self.vocaloid_background_source_sizes.get(folder_name, (1600, 2120))

    def _get_poster_layout_box(
        self,
        folder_name: str,
        expression_count: int,
    ) -> tuple[int, int, int, int]:
        """在海报原始坐标中定义按钮布局安全区。"""
        source_width, source_height = self._get_layout_source_size(folder_name)
        button_columns, _ = self._get_vocaloid_layout_metrics(folder_name)
        button_rows = max(1, (max(1, expression_count) + button_columns - 1) // button_columns)

        margin_left = int(source_width * 0.18)
        margin_right = int(source_width * 0.18)
        margin_top = int(source_height * 0.18)
        margin_bottom = int(source_height * 0.11)
        extra_height = max(0, button_rows - 4) * int(source_height * 0.035)

        safe_left = margin_left
        safe_top = max(int(source_height * 0.14), margin_top - extra_height // 2)
        safe_width = max(1, source_width - margin_left - margin_right)
        safe_height = max(
            1,
            source_height - safe_top - max(int(source_height * 0.08), margin_bottom - extra_height // 2),
        )
        return safe_left, safe_top, safe_width, safe_height

    def _get_display_layout_box(
        self,
        folder_name: str,
        expression_count: int,
    ) -> tuple[int, int, int, int]:
        """将海报原始坐标中的按钮安全区映射到当前显示尺寸。"""
        poster_left, poster_top, poster_width, poster_height = self.vocaloid_poster_rects.get(
            folder_name,
            (0, 0, 360, 520),
        )
        source_width, source_height = self._get_layout_source_size(folder_name)
        safe_left, safe_top, safe_width, safe_height = self._get_poster_layout_box(
            folder_name,
            expression_count,
        )
        scale_x = poster_width / max(source_width, 1)
        scale_y = poster_height / max(source_height, 1)
        return (
            poster_left + int(safe_left * scale_x),
            poster_top + int(safe_top * scale_y),
            max(1, int(safe_width * scale_x)),
            max(1, int(safe_height * scale_y)),
        )

    def _get_reference_button_slot_boxes(self) -> list[tuple[float, float, float, float]]:
        """基于海报比例定义按钮参考位置，缩小槽位尺寸并增大行列间距以增加留白。"""
        return [
            (0.15, 0.10, 0.22, 0.13),
            (0.41, 0.10, 0.22, 0.13),
            (0.67, 0.10, 0.22, 0.13),
            (0.15, 0.26, 0.22, 0.13),
            (0.41, 0.26, 0.22, 0.13),
            (0.67, 0.26, 0.22, 0.13),
            (0.15, 0.42, 0.22, 0.13),
            (0.41, 0.42, 0.22, 0.13),
            (0.67, 0.42, 0.22, 0.13),
            (0.15, 0.58, 0.22, 0.13),
            (0.41, 0.58, 0.22, 0.13),
            (0.67, 0.58, 0.22, 0.13),
            (0.15, 0.74, 0.22, 0.13),
        ]

    def _get_display_button_slots(
        self,
        folder_name: str,
        expression_count: int,
    ) -> list[tuple[int, int, int, int]]:
        """将参考槽位映射到海报容器坐标系。"""
        poster_rect = self.vocaloid_poster_rects.get(folder_name)
        if not poster_rect:
            target_width = max(640, self.root.winfo_width() - 60)
            source_size = self.vocaloid_background_source_sizes.get(folder_name, (1600, 2120))
            target_height = self._get_poster_container_height(source_size, target_width)
            poster_rect = self._get_centered_poster_rect(source_size, (target_width, target_height))

        poster_left, poster_top, poster_width, poster_height = poster_rect
        slot_boxes = self._get_reference_button_slot_boxes()
        slots: list[tuple[int, int, int, int]] = []

        for left_ratio, top_ratio, width_ratio, height_ratio in slot_boxes[:expression_count]:
            slot_left = poster_left + int(left_ratio * poster_width)
            slot_top = poster_top + int(top_ratio * poster_height)
            slot_width = max(1, int(width_ratio * poster_width))
            slot_height = max(1, int(height_ratio * poster_height))
            # 显著收缩按钮可视占位，确保按键之间、按键与边框有明显留空。
            inset = max(4, int(min(slot_width, slot_height) * 0.10))
            slots.append(
                (
                    slot_left + inset,
                    slot_top + inset,
                    max(1, slot_width - inset * 2),
                    max(1, slot_height - inset * 2),
                )
            )

        return slots

    def _bind_vocaloid_card_events(self, widgets: list, folder_name: str, expression_name: str):
        """为新卡片式按键绑定统一点击事件。"""
        for widget in widgets:
            widget.bind(
                "<Button-1>",
                lambda _event, folder=folder_name, expr=expression_name: self.app.select_vocaloid_expression(folder, expr),
            )

    def _hex_to_rgba(self, hex_color: str, alpha: int) -> tuple[int, int, int, int]:
        """将十六进制颜色转换为带透明度的 RGBA。"""
        cleaned = hex_color.lstrip("#")
        if len(cleaned) != 6:
            return 255, 255, 255, alpha
        return (
            int(cleaned[0:2], 16),
            int(cleaned[2:4], 16),
            int(cleaned[4:6], 16),
            alpha,
        )

    def _get_vocaloid_text_box_metrics(self, target_size: tuple[int, int]) -> tuple[int, int, int, int]:
        target_width, target_height = target_size
        text_padding_x = max(4, int(target_width * 0.12))
        text_padding_y = max(4, int(target_height * 0.08))
        text_height = max(10, int(target_height * 0.16))
        return text_padding_x, text_padding_y, text_height, max(10, int(target_height * 0.1))

    def _get_preview_content_rect(
        self,
        image: Image.Image,
        target_size: tuple[int, int],
    ) -> tuple[int, int, int, int]:
        target_width, target_height = target_size
        inner_width = max(1, int(target_width * 0.88))
        inner_height = max(1, int(target_height * 0.72))
        scale = min(inner_width / max(image.width, 1), inner_height / max(image.height, 1))
        contained_width = max(1, int(image.width * scale))
        contained_height = max(1, int(image.height * scale))

        content_left = (target_width - contained_width) // 2
        preview_top = max(0, int(target_height * 0.04))
        preview_height = max(1, int(target_height * 0.72))
        content_top = preview_top + max(0, (preview_height - contained_height) // 2)
        return content_left, content_top, contained_width, contained_height

    def _bind_vocaloid_canvas_mousewheel(self, canvas_widget):
        def _on_mousewheel(event):
            delta = event.delta
            if delta == 0:
                return "break"
            step_count = max(1, int(abs(delta) / 120))
            canvas_widget.yview_scroll((-1 if delta > 0 else 1) * step_count * 4, "units")
            return "break"

        def _on_enter(_event):
            canvas_widget.bind_all("<MouseWheel>", _on_mousewheel)

        def _on_leave(_event):
            canvas_widget.unbind_all("<MouseWheel>")

        canvas_widget.bind("<Enter>", _on_enter, add="+")
        canvas_widget.bind("<Leave>", _on_leave, add="+")

    def _render_vocaloid_canvas_image(self, folder_name: str, canvas_image, width: int, height: int):
        background_canvas = self.vocaloid_background_canvases.get(folder_name)
        if background_canvas is None:
            return

        self.vocaloid_canvas_photo_images[folder_name] = canvas_image
        existing_image_id = self.vocaloid_canvas_image_ids.get(folder_name)
        if existing_image_id is None:
            existing_image_id = background_canvas.create_image(0, 0, anchor="nw", image=canvas_image)
            self.vocaloid_canvas_image_ids[folder_name] = existing_image_id
        else:
            background_canvas.itemconfigure(existing_image_id, image=canvas_image)

        background_canvas.configure(scrollregion=(0, 0, width, height))

    def _build_vocaloid_card_mask_pil(
        self,
        folder_name: str,
        target_size: tuple[int, int],
        is_active: bool,
    ) -> Image.Image:
        target_width, target_height = target_size
        accent_color, _ = self._get_vocaloid_accent_colors(folder_name)
        accent_rgba = self._hex_to_rgba(accent_color if isinstance(accent_color, str) else "#66ccff", 210)
        mask_image = Image.new("RGBA", target_size, (0, 0, 0, 0))
        if target_width < 4 or target_height < 4:
            return mask_image

        draw = ImageDraw.Draw(mask_image)
        radius = max(12, int(min(target_width, target_height) * 0.14))
        if is_active:
            draw.rounded_rectangle(
                (1, 1, target_width - 2, target_height - 2),
                radius=radius,
                fill=(0, 0, 0, 0),
                outline=accent_rgba,
                width=3,
            )

        text_padding_x, text_padding_y, text_height, _ = self._get_vocaloid_text_box_metrics(target_size)
        text_left = text_padding_x
        text_bottom = target_height - text_padding_y
        text_top = text_bottom - text_height
        text_right = target_width - text_padding_x
        if text_right > text_left and text_bottom > text_top:
            draw.rounded_rectangle(
                (text_left, text_top, text_right, text_bottom),
                radius=max(10, int(radius * 0.8)),
                fill=accent_rgba[:3] + (48,) if is_active else (10, 18, 30, 78),
            )
        return mask_image

    def _draw_centered_card_text(
        self,
        canvas: Image.Image,
        expression_name: str,
        slot: tuple[int, int, int, int],
        is_active: bool,
        folder_name: str,
    ):
        slot_x, slot_y, slot_width, slot_height = slot
        text_padding_x, text_padding_y, text_height, font_size = self._get_vocaloid_text_box_metrics((slot_width, slot_height))
        accent_color, _ = self._get_vocaloid_accent_colors(folder_name)
        text_color = accent_color if is_active else "#FFFFFF"
        font = self._load_preview_font(font_size)
        draw = ImageDraw.Draw(canvas)

        text_area_left = slot_x + text_padding_x
        text_area_right = slot_x + slot_width - text_padding_x
        text_area_bottom = slot_y + slot_height - text_padding_y
        text_area_top = text_area_bottom - text_height

        bbox = draw.textbbox((0, 0), expression_name, font=font)
        text_width = bbox[2] - bbox[0]
        text_height_real = bbox[3] - bbox[1]
        text_x = text_area_left + max(0, (text_area_right - text_area_left - text_width) // 2)
        text_y = text_area_top + max(0, (text_height - text_height_real) // 2) - bbox[1]
        draw.text((text_x, text_y), expression_name, font=font, fill=text_color)

    def _build_vocaloid_gallery_surface_image(
        self,
        folder_name: str,
        poster_canvas: Image.Image,
        target_size: tuple[int, int],
        with_overlay: bool = True,
    ) -> Image.Image:
        surface = poster_canvas.copy()
        expressions = self.app.vocaloid_gallery.get(folder_name, {}).get("expressions", {})
        slots = self._get_display_button_slots(folder_name, len(expressions))
        hit_boxes: list[tuple[int, int, int, int, str]] = []

        for index, expression_name in enumerate(expressions.keys()):
            if index >= len(slots):
                break
            slot = slots[index]
            slot_x, slot_y, slot_width, slot_height = slot
            hit_boxes.append((slot_x, slot_y, slot_width, slot_height, expression_name))
            target_slot_size = (slot_width, slot_height)
            is_active = (
                self.app.active_vocaloid_folder == folder_name
                and self.app.active_vocaloid_expression == expression_name
            )

            thumbnail_key = (folder_name, expression_name, slot_width, slot_height)
            preview = self._thumbnail_card_cache.get(thumbnail_key)
            if preview is None:
                preview_source = self.app.get_vocaloid_preview_image(folder_name, expression_name)
                if preview_source is not None:
                    preview = self._build_emotion_preview_card(
                        folder_name,
                        expression_name,
                        preview_source,
                        target_slot_size,
                    )
                    self._thumbnail_card_cache[thumbnail_key] = preview
                else:
                    preview_left, preview_top, preview_width, preview_height = (0, 0, slot_width, slot_height)

            if preview is not None:
                surface.alpha_composite(preview, (slot_x, slot_y))

            if with_overlay:
                mask_image = self._build_vocaloid_card_mask_pil(folder_name, target_slot_size, is_active)
                surface.alpha_composite(mask_image, (slot_x, slot_y))
                self._draw_centered_card_text(surface, expression_name, slot, is_active, folder_name)

        self.vocaloid_surface_hit_boxes[folder_name] = hit_boxes
        return surface

    def _apply_vocaloid_gallery_overlay(
        self,
        folder_name: str,
        base_surface: Image.Image,
    ) -> Image.Image:
        surface = base_surface.copy()
        expressions = self.app.vocaloid_gallery.get(folder_name, {}).get("expressions", {})
        slots = self._get_display_button_slots(folder_name, len(expressions))

        for index, expression_name in enumerate(expressions.keys()):
            if index >= len(slots):
                break
            slot = slots[index]
            slot_x, slot_y, slot_width, slot_height = slot
            target_slot_size = (slot_width, slot_height)
            is_active = (
                self.app.active_vocaloid_folder == folder_name
                and self.app.active_vocaloid_expression == expression_name
            )
            mask_image = self._build_vocaloid_card_mask_pil(folder_name, target_slot_size, is_active)
            surface.alpha_composite(mask_image, (slot_x, slot_y))
            self._draw_centered_card_text(surface, expression_name, slot, is_active, folder_name)

        return surface

    def _handle_vocaloid_surface_click(self, event, folder_name: str):
        background_canvas = self.vocaloid_background_canvases.get(folder_name)
        if background_canvas is None or not background_canvas.winfo_exists():
            return

        relative_x = background_canvas.canvasx(event.x)
        relative_y = background_canvas.canvasy(event.y)
        for slot_x, slot_y, slot_width, slot_height, expression_name in self.vocaloid_surface_hit_boxes.get(folder_name, []):
            if slot_x <= relative_x <= slot_x + slot_width and slot_y <= relative_y <= slot_y + slot_height:
                self.app.select_vocaloid_expression(folder_name, expression_name)
                self.sync_vocaloid_controls()
                return

    def _create_vocaloid_card_mask_image(
        self,
        folder_name: str,
        expression_name: str,
        target_size: tuple[int, int],
        is_active: bool,
    ):
        """为新卡片式按键生成蒙版层。"""
        cache_key = (
            folder_name,
            expression_name,
            target_size,
            is_active,
            "mask",
            ctk.get_appearance_mode(),
        )
        cached_image = self.vocaloid_button_mask_images.get(cache_key)
        if cached_image is not None:
            return cached_image

        target_width, target_height = target_size
        accent_color, _ = self._get_vocaloid_accent_colors(folder_name)
        accent_rgba = self._hex_to_rgba(accent_color if isinstance(accent_color, str) else "#66ccff", 210)
        mask_image = Image.new("RGBA", target_size, (0, 0, 0, 0))
        if target_width < 4 or target_height < 4:
            ctk_image = ctk.CTkImage(
                light_image=mask_image,
                dark_image=mask_image,
                size=target_size,
            )
            self.vocaloid_button_mask_images[cache_key] = ctk_image
            return ctk_image
        draw = ImageDraw.Draw(mask_image)
        radius = max(12, int(min(target_width, target_height) * 0.14))

        if is_active:
            draw.rounded_rectangle(
                (1, 1, target_width - 2, target_height - 2),
                radius=radius,
                fill=(0, 0, 0, 0),
                outline=accent_rgba,
                width=3,
            )
            
        # 文字说明区域的统一计算逻辑，确保蒙版与 Label 位置对齐
        text_padding_x = max(4, int(target_width * 0.12))
        text_padding_y = max(4, int(target_height * 0.08))
        text_height = max(10, int(target_height * 0.16))
        
        text_left = text_padding_x
        text_bottom = target_height - text_padding_y
        text_top = text_bottom - text_height
        text_right = target_width - text_padding_x
        
        if text_right > text_left and text_bottom > text_top:
            draw.rounded_rectangle(
                (text_left, text_top, text_right, text_bottom),
                radius=max(10, int(radius * 0.8)),
                fill=accent_rgba[:3] + (48,) if is_active else (10, 18, 30, 78),
            )

        ctk_image = ctk.CTkImage(
            light_image=mask_image,
            dark_image=mask_image,
            size=target_size,
        )
        self.vocaloid_button_mask_images[cache_key] = ctk_image
        return ctk_image

    def _refresh_vocaloid_button_layout(self, folder_name: str):
        """根据当前海报尺寸刷新新卡片式按键的位置与尺寸。"""
        expressions = self.app.vocaloid_gallery.get(folder_name, {}).get("expressions", {})
        slots = self._get_display_button_slots(folder_name, len(expressions))

        for index, expression_name in enumerate(expressions.keys()):
            if index >= len(slots):
                break
            button_key = (folder_name, expression_name)
            card_frame = self.vocaloid_buttons.get(button_key)
            image_label = self.vocaloid_button_thumbnail_labels.get(button_key)
            mask_label = self.vocaloid_button_masks.get(button_key)
            text_label = self.vocaloid_button_text_labels.get(button_key)
            if card_frame is None or image_label is None or mask_label is None or text_label is None:
                continue

            slot_x, slot_y, slot_width, slot_height = slots[index]
            target_size = (slot_width, slot_height)
            if self.vocaloid_button_target_sizes.get(button_key) != target_size:
                preview_image = self._create_vocaloid_button_image(
                    folder_name,
                    expression_name,
                    target_size,
                )
                is_active = (
                    self.app.active_vocaloid_folder == folder_name
                    and self.app.active_vocaloid_expression == expression_name
                )
                mask_image = self._create_vocaloid_card_mask_image(
                    folder_name,
                    expression_name,
                    target_size,
                    is_active,
                )
                card_frame.configure(width=slot_width, height=slot_height)
                image_label.configure(image=preview_image, width=slot_width, height=slot_height)
                mask_label.configure(image=mask_image, width=slot_width, height=slot_height)
                text_height = max(10, int(slot_height * 0.16))
                text_label.configure(
                    width=max(1, slot_width - int(slot_width * 0.24)),
                    height=text_height,
                    wraplength=max(1, slot_width - int(slot_width * 0.28)),
                    font=ctk.CTkFont(
                        family=self.app.config.ui_settings.font_family,
                        size=max(9, int(slot_height * 0.1)),
                        weight="bold",
                    ),
                )
                self.vocaloid_button_images[button_key] = preview_image
                self.vocaloid_button_mask_images[(folder_name, expression_name, target_size, is_active, "live")] = mask_image
                self.vocaloid_button_target_sizes[button_key] = target_size

            card_frame.place_configure(
                x=slot_x,
                y=slot_y,
                anchor="nw",
            )
            image_label.place_configure(x=slot_width // 2, y=slot_height // 2, anchor="center")
            mask_label.place_configure(x=0, y=0, anchor="nw")
            text_padding_y = max(4, int(slot_height * 0.08))
            text_label.place_configure(
                x=slot_width // 2,
                y=slot_height - text_padding_y,
                anchor="s",
            )

    def _build_gallery_background_image(self, folder_name: str, image: Image.Image, target_size: tuple[int, int]) -> tuple[Image.Image, tuple[int, int, int, int]]:
        """将海报按原始比例完整适配到容器，不叠加阴影或额外底板。"""
        target_width, target_height = target_size
        poster_canvas = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
        poster_left, poster_top, poster_width, poster_height = self._get_centered_poster_rect(image.size, target_size)
        poster = image.resize((poster_width, poster_height), Image.Resampling.LANCZOS)
        poster_canvas.alpha_composite(poster, (poster_left, poster_top))
        return poster_canvas, (
            poster_left,
            poster_top,
            poster_width,
            poster_height,
        )

    def _rebuild_vocaloid_folder_buttons(self, folder_name: str, button_frame, expressions: dict):
        """单图合成模式下仅触发整张图库重绘。"""
        self._refresh_vocaloid_background(folder_name)

    def _apply_vocaloid_button_state(self, folder_name: str, expression_name: str):
        """单图合成模式下通过整张图库重绘更新状态。"""
        self._refresh_vocaloid_background(folder_name)

    def _create_vocaloid_button_image(
        self,
        folder_name: str,
        expression_name: str,
        target_size: tuple[int, int] | None = None,
    ):
        """生成新卡片系统中的图片层，不再包含旧按钮底板和文字。"""
        if target_size is None:
            expression_count = len(
                self.app.vocaloid_gallery.get(folder_name, {}).get("expressions", {})
            )
            slots = self._get_display_button_slots(folder_name, expression_count)
            target_size = slots[0][2:4] if slots else (88, 88)

        cache_key = (
            folder_name,
            expression_name,
            ctk.get_appearance_mode(),
            target_size,
        )
        if cache_key in self.vocaloid_preview_cache:
            return self.vocaloid_preview_cache[cache_key]

        preview_source = self.app.get_vocaloid_preview_image(folder_name, expression_name)
        if preview_source is None:
            return None

        try:
            preview = self._build_emotion_preview_card(
                folder_name,
                expression_name,
                preview_source,
                target_size,
            )

            preview_image = ctk.CTkImage(
                light_image=preview,
                dark_image=preview,
                size=target_size,
            )
            self.vocaloid_preview_cache[cache_key] = preview_image
            return preview_image
        except Exception as e:
            print(f"生成 Vocaloid 按钮缩略图失败: {folder_name}/{expression_name} -> {e}")
            return None

    def _load_preview_font(self, size: int):
        """为按钮预览图选择尽量稳定的中文字体。"""
        cached = self._preview_font_cache.get(size)
        if cached is not None:
            return cached
        for font_name in ("msyh.ttc", "simhei.ttf", "simsun.ttc"):
            try:
                font = ImageFont.truetype(font_name, size=size)
                self._preview_font_cache[size] = font
                return font
            except Exception:
                continue
        font = ImageFont.load_default()
        self._preview_font_cache[size] = font
        return font

    def _build_emotion_preview_card(self, folder_name: str, expression_name: str, image: Image.Image, target_size: tuple[int, int]) -> Image.Image:
        """生成新卡片系统中的纯图片层，确保缩略图在容器内稳定居中。"""
        target_width, target_height = target_size
        card = Image.new("RGBA", target_size, (0, 0, 0, 0))
        preview_left, preview_top, preview_width, preview_height = self._get_preview_content_rect(image, target_size)
        contained = image.resize((preview_width, preview_height), Image.Resampling.LANCZOS)
        alpha_channel = contained.getchannel("A").point(lambda value: int(value * 0.95))
        contained.putalpha(alpha_channel)
        card.alpha_composite(contained, (preview_left, preview_top))

        rounded_mask = Image.new("L", target_size, 0)
        mask_draw = ImageDraw.Draw(rounded_mask)
        # 统一圆角半径计算逻辑
        radius = max(12, int(min(target_width, target_height) * 0.14))
        mask_draw.rounded_rectangle((0, 0, target_width - 1, target_height - 1), radius=radius, fill=255)
        clipped_card = Image.new("RGBA", target_size, (0, 0, 0, 0))
        clipped_card.paste(card, (0, 0), rounded_mask)
        return clipped_card

    def _resize_to_contain(self, image: Image.Image, target_size: tuple[int, int]) -> Image.Image:
        """按比例完整缩放并居中放入目标区域，避免裁切和拉伸。"""
        target_width, target_height = target_size
        source_width, source_height = image.size
        scale = min(target_width / source_width, target_height / source_height)
        resized_width = max(1, int(source_width * scale))
        resized_height = max(1, int(source_height * scale))
        resized = image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
        left = (target_width - resized_width) // 2
        top = (target_height - resized_height) // 2
        canvas.alpha_composite(resized, (left, top))
        return canvas

    def _resize_to_cover(self, image: Image.Image, target_size: tuple[int, int]) -> Image.Image:
        """按比例放大到完全覆盖目标区域，用于背景和纹理裁切。"""
        target_width, target_height = target_size
        source_width, source_height = image.size
        scale = max(target_width / max(source_width, 1), target_height / max(source_height, 1))
        resized_width = max(1, int(source_width * scale))
        resized_height = max(1, int(source_height * scale))
        return image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)

    def save_config(self):
        """保存配置到文件"""
        try:
            self.app.config.auto_paste_image = self.auto_paste_var.get()
            self.app.config.auto_send_image = self.auto_send_var.get()
            self.app.config.block_hotkey = self.block_hotkey_var.get()
            self.app.rebind_hotkey()
            self.app.save_current_config()
            messagebox.showinfo("成功", "配置已保存到 config.yaml")
        except Exception as e:
            messagebox.showerror("错误", f"保存配置时发生错误: {str(e)}")
            
    def apply_config(self):
        """应用配置到运行时"""
        try:
            self.update_status("正在应用配置...")
            
            # 更新应用配置
            self.app.config.auto_paste_image = self.auto_paste_var.get()
            self.app.config.auto_send_image = self.auto_send_var.get()
            self.app.config.block_hotkey = self.block_hotkey_var.get()
            
            # 重新注册热键
            self.app.rebind_hotkey()
            
            # 更新状态栏
            self.update_status("配置已应用")
            
            messagebox.showinfo("提示", "配置已应用")
        except Exception as e:
            self.update_status("配置应用失败")
            messagebox.showerror("错误", f"应用配置时发生错误: {str(e)}")
            
    def minimize(self):
        """最小化窗口到系统托盘"""
        self.update_status("正在最小化到系统托盘...")
        self.is_minimized = True
        # 隐藏主窗口
        self.root.withdraw()
        
        # 如果pystray可用，则创建系统托盘图标
        if PYSTRAY_AVAILABLE:
            self.create_tray_icon()
        else:
            # 如果pystray不可用，则使用标准的窗口最小化方法
            self.root.iconify()
            self.update_status("已最小化到任务栏")

    def create_tray_icon(self):
        """创建系统托盘图标"""
        # 创建托盘图标菜单
        menu = (
            TrayMenuItem('显示', self.restore),
            TrayMenuItem('退出', self.confirm_exit_from_tray),
        )
        
        # 尝试加载图标，如果没有则使用默认图标
        icon_image = self.create_default_icon()
        
        # 创建并运行托盘图标
        self.tray_icon = TrayIcon(
            "冬里代的改版素描本 V1.1",
            icon_image,
            "冬里代的改版素描本 V1.1",
            menu
        )
        
        # 添加双击事件处理
        def on_tray_icon_click(icon, query):
            if query == TrayIcon.DoubleClick:
                self.restore()
        
        self.tray_icon.on_click = on_tray_icon_click
        
        # 在单独的线程中运行托盘图标
        self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        self.tray_thread.start()
        self.update_status("已最小化到系统托盘")

    def create_default_icon(self):
        """创建默认的托盘图标"""
        try:
            resource_root = getattr(self.app, "resource_root", "")
            icon_candidates = []
            if resource_root:
                icon_candidates.append(os.path.join(resource_root, "icon.png"))
            icon_candidates.append("icon.png")
            for icon_path in icon_candidates:
                if os.path.exists(icon_path):
                    icon = Image.open(icon_path)
                    icon = icon.resize((64, 64), Image.Resampling.LANCZOS)
                    return icon
            return self.generate_default_icon()
        except Exception as e:
            print(f"加载托盘图标失败: {e}")
            return self.generate_default_icon()
    
    def generate_default_icon(self):
        """生成默认的托盘图标"""
        # 创建一个64x64的图标
        icon = Image.new('RGBA', (64, 64), (70, 130, 180, 255))  # Steel blue color
        
        # 创建绘图对象
        draw = ImageDraw.Draw(icon)
        
        # 绘制一个简单的笔记本图标
        # 笔记本封面
        draw.rectangle([10, 5, 54, 59], fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=2)
        
        # 笔记本螺旋装订线
        for i in range(5):
            y = 15 + i * 10
            draw.ellipse([5, y-2, 10, y+2], fill=(169, 169, 169, 255))  # Dark gray spiral
            
        # 在笔记本上绘制一个简单的"P"字符表示"Paper"
        try:
            # 尝试使用默认字体
            font = ImageFont.load_default()
            draw.text((25, 20), "P", fill=(0, 0, 0, 255), font=font)
        except:
            # 如果无法加载字体，就画一个简单的形状
            draw.rectangle([25, 20, 35, 30], fill=(0, 0, 0, 255))
            
        return icon

    def restore(self):
        """恢复窗口"""
        self.is_minimized = False
        
        # 停止托盘图标（如果存在）
        if hasattr(self, 'tray_icon') and self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
        
        # 恢复主窗口
        self.root.deiconify()
        self.root.lift()
        self.update_status("就绪")

    def confirm_exit_from_tray(self):
        """托盘退出确认"""
        # 停止托盘图标（如果存在）
        if hasattr(self, 'tray_icon') and self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
            
        self.app.stop()
        self.root.destroy()

    def on_closing(self):
        """处理窗口关闭事件"""
        # 显示选项对话框
        from tkinter import messagebox
        
        # 创建一个顶层窗口作为对话框的父窗口
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("确认操作")
        dialog.geometry("350x180")
        dialog.resizable(False, False)
        dialog.configure(fg_color=self.colors["surface"])
        dialog.transient(self.root)  # 设置为瞬态窗口
        dialog.grab_set()  # 模态对话框
        
        # 居中显示对话框
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (350 // 2)
        y = (dialog.winfo_screenheight() // 2) - (180 // 2)
        dialog.geometry(f"350x180+{x}+{y}")
        
        # 对话框内容
        label = ctk.CTkLabel(dialog, text="确定要退出冬里代的改版素描本 V1.1 吗？", font=self.header_font, text_color=self.colors["text_primary"])
        label.pack(pady=20)
        
        desc_label = ctk.CTkLabel(
            dialog, 
            text="选择\"隐藏\"可以最小化到系统托盘继续运行", 
            font=ctk.CTkFont(size=12),
            text_color=self.colors["text_muted"]
        )
        desc_label.pack(pady=(0, 10))
        
        # 按钮框架
        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(pady=10)
        
        def hide_window():
            dialog.destroy()
            self.minimize()
            
        def close_app():
            dialog.destroy()
            # 停止托盘图标（如果存在）
            if hasattr(self, 'tray_icon') and self.tray_icon:
                self.tray_icon.stop()
                
            self.app.stop()
            self.root.destroy()
            
        def cancel_action():
            dialog.destroy()
            
        # 创建三个按钮
        hide_btn = ctk.CTkButton(
            button_frame, 
            text="隐藏到托盘", 
            command=hide_window,
            fg_color=self.colors["accent_secondary"],
            hover_color=self.colors["accent_secondary_hover"],
            width=80
        )
        hide_btn.pack(side="left", padx=5)
        
        close_btn = ctk.CTkButton(
            button_frame, 
            text="退出程序", 
            command=close_app, 
            fg_color=self.colors["danger"],
            hover_color=self.colors["danger_hover"],
            width=80
        )
        close_btn.pack(side="left", padx=5)
        
        cancel_btn = ctk.CTkButton(
            button_frame, 
            text="取消", 
            command=cancel_action,
            fg_color=self.colors["accent"],
            hover_color=self.colors["accent_hover"],
            width=80
        )
        cancel_btn.pack(side="left", padx=5)
        
        # 确保对话框获得焦点
        dialog.focus_force()
        
    def append_log(self, message: str):
        """添加日志消息到UI"""
        self._run_on_ui_thread(self._append_log_impl, message)

    def _append_log_impl(self, message: str):
        self.log_text.config(state='normal')
        self.log_text.insert(ctk.END, message + '\n')
        self.log_text.config(state='disabled')
        self.log_text.see(ctk.END)
        
    def clear_log(self):
        """清空日志"""
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, ctk.END)
        self.log_text.config(state='disabled')


class UITextHandler(logging.Handler):
    """自定义日志处理器，将日志输出到UI"""
    
    def __init__(self, ui: AnanSketchbookUI):
        super().__init__()
        self.ui = ui
        
    def emit(self, record):
        # 严格遵守 Handler 自身设置的级别（即用户在配置中选定的级别）
        if record.levelno < self.level:
            return
            
        # 根据日志级别格式化消息
        if record.levelno >= logging.CRITICAL:
            msg = f"🚨 [致命错误] {record.getMessage()}"
        elif record.levelno >= logging.INFO:
            msg = record.getMessage()
        else:
            msg = self.format(record)
            
        # 使用线程安全的方式更新UI
        if self.ui.root:
            self.ui.root.after(0, self.ui.append_log, msg)
