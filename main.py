# hotkey_demo.py
import io
import logging
import time
import ctypes
import statistics
from typing import Dict, List, Optional, Tuple

import keyboard
import psutil
import pyperclip
import win32clipboard
import win32gui
import win32process
from PIL import Image
# 添加日志轮转所需的导入
import os
from logging.handlers import RotatingFileHandler

from config_loader import load_config, save_config as save_config_file
from image_fit_paste import paste_image_auto
from text_fit_draw import draw_text_auto
# 导入UI模块
from ui import AnanSketchbookUI
import threading
import sys
import customtkinter as ctk

VOCALOID_FOLDER_ORDER = ["洛佬", "阿绫", "言和", "墨姐"]

VOCALOID_EXPRESSION_ORDER = [
    "标准",
    "wink",
    "开心",
    "激动",
    "惊讶",
    "脸红",
    "无语",
    "生气",
    "闭眼",
    "害怕",
    "黑化",
    "哭泣",
    "难受",
]

VOCALOID_BRACKET_COLOR_HEX = {
    "洛佬": "66CCFF",
    "阿绫": "EE0000",
    "言和": "00FFCC",
    "墨姐": "FFFF00",
}

DEFAULT_TEXT_REGION = ((119, 450), (398, 625))
REFERENCE_IMAGE_HEIGHT = 648
REFERENCE_FONT_HEIGHT = 64


class AnanSketchbookApp:
    def __init__(self):
        # 启用高 DPI 支持
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except:
            pass

        self.bundle_dir = os.path.dirname(os.path.abspath(__file__))
        self.resource_root = self.bundle_dir
        self.config_file = os.path.join(self.bundle_dir, "config.yaml")

        # 设置工作目录为程序所在目录（解决打包后路径问题）
        if getattr(sys, 'frozen', False):
            self.bundle_dir = os.path.dirname(sys.executable)
            self.resource_root = getattr(sys, "_MEIPASS", os.path.join(self.bundle_dir, "_internal"))
            self.config_file = os.path.join(self.bundle_dir, "config.yaml")
            if not os.path.exists(self.config_file):
                self.config_file = os.path.join(self.resource_root, "config.yaml")
            os.chdir(self.bundle_dir)

        self.config = load_config(self.config_file)
        self._sync_runtime_resource_paths()
        
        self.setup_logging()

        self.last_used_image_file = ""
        self.ratio = 1
        self.generation_lock = threading.Lock()
        self.vocaloid_gallery = self._load_vocaloid_gallery()
        self.active_vocaloid_folder: Optional[str] = None
        self.active_vocaloid_expression: Optional[str] = None
        
        # 初始化UI
        self.ui = AnanSketchbookUI(self)
        
        # 设置窗口大小
        ui_settings = self.config.ui_settings
        self.ui.root.geometry(f"{ui_settings.window_width}x{ui_settings.window_height}")
        
        # 设置主题
        ctk.set_default_color_theme(ui_settings.theme)
        
        default_selection = self._get_default_vocaloid_selection()
        if default_selection:
            self.select_vocaloid_expression(*default_selection)
        
        # 添加 UI 日志处理器，并设置其过滤级别
        ui_log_level = getattr(logging, self.config.logging_level.upper(), logging.INFO)
        self.ui.log_handler.setLevel(ui_log_level)
        logger = logging.getLogger()
        logger.addHandler(self.ui.log_handler)
        
        # 绑定初始热键
        self.is_hotkey_bound = None
        self._bind_main_hotkey()
        logging.info("✨ 冬里代的改版素描本 V1.1 已就绪")
        logging.info(f"🎹 主热键：{self.config.hotkey} | Vocaloid 分组：{len(self.vocaloid_gallery)}")
        self.ui.update_status("就绪")

    def _get_vocaloid_root(self) -> str:
        """返回 VocaloidImage 资源根目录。"""
        return self._resolve_resource_path(os.path.join("BaseImages", "VocaloidImage"))

    def _describe_path(self, path_value: str) -> str:
        """优先以相对路径展示路径，便于日志和界面阅读。"""
        if not path_value:
            return ""

        normalized_path = os.path.normpath(path_value)
        candidate_bases = [
            getattr(self, "bundle_dir", ""),
            getattr(self, "resource_root", ""),
            os.getcwd(),
        ]
        for base_dir in candidate_bases:
            if not base_dir:
                continue
            try:
                if os.path.commonpath([normalized_path, os.path.normpath(base_dir)]) == os.path.normpath(base_dir):
                    return os.path.relpath(normalized_path, base_dir)
            except ValueError:
                continue
        return normalized_path

    def _match_vocaloid_expression(self, filename_stem: str) -> Optional[str]:
        """根据文件名匹配 Vocaloid 表情名，兼容前缀命名。"""
        normalized_stem = filename_stem.strip()
        for expression in VOCALOID_EXPRESSION_ORDER:
            if normalized_stem == expression or normalized_stem.endswith(expression):
                return expression
        return None

    def _load_vocaloid_gallery(self) -> Dict[str, dict]:
        """扫描 VocaloidImage 目录，收集四个子文件夹内的底图与置顶图层。"""
        gallery: Dict[str, dict] = {}
        vocaloid_root = self._get_vocaloid_root()
        logging.debug("开始扫描角色图片目录: root=%s", self._describe_path(vocaloid_root))
        if not os.path.isdir(vocaloid_root):
            logging.warning("角色图片目录不存在: %s", self._describe_path(vocaloid_root))
            return gallery

        folder_names = [
            folder_name
            for folder_name in os.listdir(vocaloid_root)
            if os.path.isdir(os.path.join(vocaloid_root, folder_name))
        ]
        folder_names.sort(
            key=lambda folder_name: (
                VOCALOID_FOLDER_ORDER.index(folder_name)
                if folder_name in VOCALOID_FOLDER_ORDER
                else len(VOCALOID_FOLDER_ORDER),
                folder_name,
            )
        )

        for folder_name in folder_names:
            folder_path = os.path.join(vocaloid_root, folder_name)
            logging.debug("扫描角色分组: folder=%s", self._describe_path(folder_path))

            expression_files: Dict[str, str] = {}
            overlay_path = ""
            standard_image_path = ""

            for file_name in sorted(os.listdir(folder_path)):
                absolute_path = os.path.join(folder_path, file_name)
                if not os.path.isfile(absolute_path):
                    continue

                stem, ext = os.path.splitext(file_name)
                if ext.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
                    continue

                if stem == "001置顶图层":
                    overlay_path = absolute_path
                    continue

                matched_expression = self._match_vocaloid_expression(stem)
                if matched_expression:
                    expression_files[matched_expression] = absolute_path
                    if matched_expression == "标准":
                        standard_image_path = absolute_path

            if expression_files:
                ordered_expressions = {
                    expression: expression_files[expression]
                    for expression in VOCALOID_EXPRESSION_ORDER
                    if expression in expression_files
                }
                detected_text_box = self._detect_vocaloid_text_box(
                    standard_image_path or ordered_expressions.get("标准", "")
                )
                gallery[folder_name] = {
                    "folder_path": folder_path,
                    "overlay_path": overlay_path,
                    "expressions": ordered_expressions,
                    "text_box": detected_text_box,
                }
                logging.debug(
                    "角色分组加载完成: folder=%s, expressions=%s, overlay=%s, standard=%s",
                    folder_name,
                    list(ordered_expressions.keys()),
                    self._describe_path(overlay_path),
                    self._describe_path(standard_image_path),
                )
                if detected_text_box:
                    logging.debug(
                        f"📝 Vocaloid 文本框识别成功：{folder_name} -> {detected_text_box}"
                    )
                else:
                    logging.warning(f"📝 Vocaloid 文本框识别失败：{folder_name}")

        return gallery

    def _is_notebook_white_pixel(self, rgb: Tuple[int, int, int]) -> bool:
        """判断像素是否接近写字板的亮白低饱和区域。"""
        r, g, b = rgb
        max_value = max(r, g, b)
        min_value = min(r, g, b)
        saturation = max_value - min_value
        return max_value >= 205 and saturation <= 32

    def _get_default_vocaloid_selection(self) -> Optional[Tuple[str, str]]:
        """返回启动时默认选中的 Vocaloid 目录与表情，优先标准图。"""
        for folder_name, folder_info in self.vocaloid_gallery.items():
            expressions = folder_info.get("expressions", {})
            if "标准" in expressions:
                return folder_name, "标准"
            if expressions:
                return folder_name, next(iter(expressions))
        return None

    def _hex_to_rgb(self, hex_color: str) -> Tuple[int, int, int]:
        """将 RRGGBB 颜色字符串转换为 RGB 元组。"""
        normalized = hex_color.strip().lstrip("#")
        if len(normalized) != 6:
            raise ValueError(f"无效颜色值: {hex_color}")
        return tuple(int(normalized[index:index + 2], 16) for index in (0, 2, 4))

    def _get_current_bracket_color(self) -> Tuple[int, int, int]:
        """返回当前生成上下文中 `【】` / `[]` 括号文本的颜色。"""
        if self.has_active_vocaloid_selection():
            folder_name = self.active_vocaloid_folder or ""
            hex_color = VOCALOID_BRACKET_COLOR_HEX.get(folder_name)
            if hex_color:
                return self._hex_to_rgb(hex_color)
            return (128, 0, 128)

        return (128, 0, 128)

    def _measure_row_white_ratio(
        self,
        pixels,
        y: int,
        left: int,
        right: int,
        step: int = 3,
    ) -> float:
        """统计一行在给定区间内的写字板像素占比。"""
        matched = 0
        total = 0
        for x in range(left, right, step):
            total += 1
            if self._is_notebook_white_pixel(pixels[x, y]):
                matched += 1
        return matched / total if total else 0.0

    def _detect_vocaloid_text_box(
        self,
        standard_image_path: str,
    ) -> Optional[Tuple[Tuple[int, int], Tuple[int, int]]]:
        """从标准图中识别写字板区域，供同目录所有角色图片复用。"""
        if not standard_image_path or not os.path.exists(standard_image_path):
            return None

        standard_image = Image.open(standard_image_path).convert("RGB")
        width, height = standard_image.size
        pixels = standard_image.load()

        search_left = int(width * 0.08)
        search_right = int(width * 0.92)
        search_top = int(height * 0.38)
        search_bottom = int(height * 0.93)
        center_x = width // 2

        candidate_rows = []
        for y in range(search_top, search_bottom, 3):
            segments = []
            start_x = None

            for x in range(search_left, search_right):
                is_white = self._is_notebook_white_pixel(pixels[x, y])
                if is_white and start_x is None:
                    start_x = x
                elif not is_white and start_x is not None:
                    segments.append((start_x, x))
                    start_x = None

            if start_x is not None:
                segments.append((start_x, search_right))

            valid_segments = []
            for left, right in segments:
                segment_width = right - left
                segment_mid = (left + right) // 2
                if segment_width < width * 0.18:
                    continue
                if left <= search_left + 10 or right >= search_right - 10:
                    continue
                if abs(segment_mid - center_x) > width * 0.18:
                    continue
                valid_segments.append((segment_width, left, right))

            if not valid_segments:
                continue

            segment_width, left, right = max(valid_segments)
            candidate_rows.append((y, left, right, segment_width))

        if not candidate_rows:
            return None

        max_row_width = max(row[3] for row in candidate_rows)
        candidate_rows = [
            row for row in candidate_rows if row[3] >= max_row_width * 0.72
        ]
        if len(candidate_rows) < 20:
            return None

        row_bands = []
        current_band = [candidate_rows[0]]
        for row in candidate_rows[1:]:
            if row[0] - current_band[-1][0] <= 12:
                current_band.append(row)
            else:
                row_bands.append(current_band)
                current_band = [row]
        row_bands.append(current_band)

        best_band = max(row_bands, key=len)
        board_left = int(statistics.median(row[1] for row in best_band))
        board_right = int(statistics.median(row[2] for row in best_band))
        board_top = min(row[0] for row in best_band)

        inner_padding = max(20, (board_right - board_left) // 12)
        inner_left = board_left + inner_padding
        inner_right = board_right - inner_padding

        refined_top = board_top
        for y in range(board_top, max(search_top, board_top - 220), -3):
            if self._measure_row_white_ratio(
                pixels,
                y,
                inner_left,
                inner_right,
            ) >= 0.78:
                refined_top = y
            else:
                break

        refined_bottom = board_top
        has_started = False
        miss_count = 0
        for y in range(refined_top, search_bottom, 3):
            white_ratio = self._measure_row_white_ratio(
                pixels,
                y,
                inner_left,
                inner_right,
            )
            if white_ratio >= 0.78:
                refined_bottom = y
                has_started = True
                miss_count = 0
            elif has_started:
                miss_count += 1
                if miss_count >= 6:
                    break

        board_height = max(120, refined_bottom - refined_top)
        padding_x = max(20, (board_right - board_left) // 18)
        padding_top = max(28, board_height // 12)
        padding_bottom = max(24, board_height // 14)

        text_left = board_left + padding_x
        text_top = refined_top + padding_top
        text_right = board_right - padding_x
        text_bottom = refined_bottom - padding_bottom

        if text_right <= text_left or text_bottom <= text_top:
            return None

        return (text_left, text_top), (text_right, text_bottom)

    def has_active_vocaloid_selection(self) -> bool:
        """当前是否启用了角色图片选择。"""
        return (
            self.active_vocaloid_folder in self.vocaloid_gallery
            and self.active_vocaloid_expression in self.vocaloid_gallery.get(
                self.active_vocaloid_folder, {}
            ).get("expressions", {})
        )

    def clear_vocaloid_selection(self, refresh_ui: bool = True):
        """清除当前角色图片选择。"""
        self.active_vocaloid_folder = None
        self.active_vocaloid_expression = None
        if refresh_ui and hasattr(self, "ui"):
            self.ui.sync_vocaloid_controls()

    def select_vocaloid_expression(self, folder_name: str, expression_name: str):
        """选择指定 Vocaloid 子目录内的底图素材。"""
        folder_info = self.vocaloid_gallery.get(folder_name)
        if not folder_info:
            logging.warning(f"Vocaloid 目录不存在：{folder_name}")
            return

        image_path = folder_info["expressions"].get(expression_name)
        if not image_path:
            logging.warning(f"Vocaloid 素材不存在：{folder_name} / {expression_name}")
            return

        self.active_vocaloid_folder = folder_name
        self.active_vocaloid_expression = expression_name
        self.last_used_image_file = image_path
        logging.info(f"🎼 已选择角色图片：{folder_name} / {expression_name}")
        logging.debug(
            "当前角色素材切换: folder=%s, expression=%s, image=%s, overlay=%s, text_box=%s",
            folder_name,
            expression_name,
            self._describe_path(image_path),
            self._describe_path(self.vocaloid_gallery.get(folder_name, {}).get("overlay_path", "")),
            self.vocaloid_gallery.get(folder_name, {}).get("text_box"),
        )
        if hasattr(self, "ui"):
            self.ui.update_status(f"Vocaloid：{folder_name} / {expression_name}")
            self.ui.sync_vocaloid_controls()

    def _open_image_rgba(self, image_source) -> Image.Image:
        """统一将图片源转换为 RGBA 图像对象。"""
        if isinstance(image_source, Image.Image):
            return image_source.copy().convert("RGBA")
        return Image.open(image_source).convert("RGBA")

    def _build_bottom_right_overlay_canvas(self, image_source, overlay_path: str) -> Optional[Image.Image]:
        """将小尺寸置顶图层放入与底图同尺寸的透明画布，并对齐到底图右下角。"""
        if not overlay_path or not os.path.exists(overlay_path):
            return None

        base_image = self._open_image_rgba(image_source)
        overlay_image = Image.open(overlay_path).convert("RGBA")
        overlay_canvas = Image.new("RGBA", base_image.size, (0, 0, 0, 0))
        paste_position = (
            base_image.width - overlay_image.width,
            base_image.height - overlay_image.height,
        )
        overlay_canvas.paste(overlay_image, paste_position, overlay_image)
        return overlay_canvas

    def _get_active_render_assets(self):
        """返回当前生成所使用的图片与置顶图层资源。"""
        if self.has_active_vocaloid_selection():
            folder_info = self.vocaloid_gallery[self.active_vocaloid_folder]
            image_source = folder_info["expressions"][self.active_vocaloid_expression]
            overlay_source = self._build_bottom_right_overlay_canvas(
                image_source,
                folder_info.get("overlay_path", ""),
            )
            return image_source, overlay_source

        return self.last_used_image_file, None

    def _get_active_text_region(self) -> Tuple[int, int, int, int]:
        """返回当前图片生成使用的文本框区域。"""
        if self.has_active_vocaloid_selection():
            folder_info = self.vocaloid_gallery.get(self.active_vocaloid_folder, {})
            text_box = folder_info.get("text_box")
            if text_box:
                (x1, y1), (x2, y2) = text_box
                return x1, y1, x2, y2

        (x1, y1), (x2, y2) = DEFAULT_TEXT_REGION
        return x1, y1, x2, y2

    def _get_default_text_max_font_height(self, image_source) -> int:
        """根据当前图片尺寸计算默认字号上限。"""
        base_font_height = REFERENCE_FONT_HEIGHT
        if not image_source:
            return 220

        try:
            active_image = self._open_image_rgba(image_source)
            height_scale = active_image.height / max(REFERENCE_IMAGE_HEIGHT, 1)
            scaled_height = int(round(base_font_height * height_scale))
            return max(base_font_height, min(256, scaled_height))
        except Exception as exc:
            logging.debug(f"默认字号缩放失败，回退到保守值: {exc}")
            return 220

    def get_vocaloid_preview_image(self, folder_name: str, expression_name: str) -> Optional[Image.Image]:
        """返回已叠加右下角置顶图层的 Vocaloid 预览图。"""
        folder_info = self.vocaloid_gallery.get(folder_name)
        if not folder_info:
            return None
        image_path = folder_info["expressions"].get(expression_name)
        if not image_path or not os.path.exists(image_path):
            return None

        preview_image = self._open_image_rgba(image_path)
        overlay_canvas = self._build_bottom_right_overlay_canvas(
            preview_image,
            folder_info.get("overlay_path", ""),
        )
        if overlay_canvas is not None:
            preview_image.paste(overlay_canvas, (0, 0), overlay_canvas)
        return preview_image

    def _resolve_resource_path(self, path_value: str) -> str:
        """将资源路径解析到打包环境或源码环境中的真实位置。"""
        if not path_value:
            return ""
        normalized_path = os.path.normpath(path_value)
        if os.path.isabs(normalized_path):
            logging.debug("资源路径已是绝对路径: %s", normalized_path)
            return normalized_path

        candidate_paths = [
            normalized_path,
            os.path.join(os.getcwd(), normalized_path),
            os.path.join(self.bundle_dir, normalized_path),
            os.path.join(self.resource_root, normalized_path),
        ]

        for candidate in candidate_paths:
            if candidate and os.path.exists(candidate):
                resolved = os.path.normpath(candidate)
                logging.debug("资源路径解析成功: input=%s -> resolved=%s", path_value, self._describe_path(resolved))
                return resolved

        fallback_path = os.path.normpath(os.path.join(self.resource_root, normalized_path))
        logging.debug(
            "资源路径未命中现有文件，使用默认候选: input=%s -> fallback=%s",
            path_value,
            self._describe_path(fallback_path),
        )
        return fallback_path

    def _sync_runtime_resource_paths(self):
        """将配置中的资源路径解析为当前运行环境可直接访问的路径。"""
        original_font_path = self.config.font_file
        self.config.font_file = self._resolve_resource_path(self.config.font_file)
        logging.debug(
            "运行时资源路径同步: font_file=%s -> %s",
            original_font_path,
            self._describe_path(self.config.font_file),
        )

    def setup_logging(self):
        """设置日志记录"""
        log_dir = os.path.join(self.bundle_dir, "logs")
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        file_handler = RotatingFileHandler(
            filename=os.path.join(self.bundle_dir, "logs", "app.log"),
            maxBytes=50*1024,
            backupCount=1,
            encoding='utf-8'
        )
        
        # 文件日志始终使用DEBUG级别
        file_handler.setLevel(logging.DEBUG)
        
        # 配置格式器
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        file_handler.setFormatter(formatter)
        
        # 获取根日志记录器并添加处理器
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(file_handler)
        
        # 屏蔽第三方库的干扰
        # 只有当全局日志级别为 DEBUG 时，才允许这些库输出日志
        log_level = getattr(logging, self.config.logging_level.upper(), logging.INFO)
        third_party_level = logging.DEBUG if log_level == logging.DEBUG else logging.INFO
        logging.getLogger("PIL").setLevel(third_party_level)
        logging.getLogger("customtkinter").setLevel(third_party_level)
        
        root_logger.debug(
            "日志系统初始化完成: ui_level=%s, file_level=DEBUG, log_dir=%s",
            self.config.logging_level.upper(),
            log_dir,
        )
        root_logger.debug(
            "运行环境信息: cwd=%s, bundle_dir=%s, resource_root=%s, config_file=%s",
            os.getcwd(),
            self.bundle_dir,
            self.resource_root,
            self.config_file,
        )

    def rebind_hotkey(self):
        """重新绑定热键"""
        self._bind_main_hotkey()
        
        logging.info(f"热键已重新绑定为: {self.config.hotkey}")
        self.ui.update_status(f"热键已更新为: {self.config.hotkey}")

    def _bind_main_hotkey(self):
        """只重新绑定主触发热键，避免误删其他键盘钩子。"""
        if self.is_hotkey_bound:
            keyboard.remove_hotkey(self.is_hotkey_bound)

        self.is_hotkey_bound = keyboard.add_hotkey(
            self.config.hotkey,
            self._on_main_hotkey,
            suppress=self.config.block_hotkey or self.config.hotkey == self.config.send_hotkey,
        )

    def _on_main_hotkey(self):
        """将耗时处理移出 keyboard 回调线程，减少不同机器上的热键冲突。"""
        if not self.generation_lock.acquire(blocking=False):
            logging.warning("已有生成任务正在执行，忽略本次触发")
            return

        worker = threading.Thread(target=self._generate_image_worker, daemon=True)
        worker.start()

    def _generate_image_worker(self):
        try:
            self.generate_image()
        finally:
            self.generation_lock.release()

    def apply_runtime_config_changes(self, rebind_main_hotkey: bool = False):
        """将当前配置对象同步到运行时，并保持当前 Vocaloid 选择有效。"""
        logging.debug(
            "开始同步运行时配置: rebind_main_hotkey=%s, font_file=%s, delay=%s, allowed_processes=%s",
            rebind_main_hotkey,
            self._describe_path(self.config.font_file),
            self.config.delay,
            self.config.allowed_processes,
        )
        self._sync_runtime_resource_paths()
        self.vocaloid_gallery = self._load_vocaloid_gallery()

        if rebind_main_hotkey:
            self._bind_main_hotkey()

        current_selection = None
        if self.has_active_vocaloid_selection():
            current_selection = (
                self.active_vocaloid_folder,
                self.active_vocaloid_expression,
            )

        if current_selection:
            folder_name, expression_name = current_selection
            if folder_name in self.vocaloid_gallery and expression_name in self.vocaloid_gallery[folder_name]["expressions"]:
                self.select_vocaloid_expression(folder_name, expression_name)
            else:
                fallback_selection = self._get_default_vocaloid_selection()
                if fallback_selection:
                    self.select_vocaloid_expression(*fallback_selection)
        else:
            fallback_selection = self._get_default_vocaloid_selection()
            if fallback_selection:
                self.select_vocaloid_expression(*fallback_selection)

        self.ui.sync_vocaloid_controls()
        logging.debug(
            "运行时配置同步完成: active_folder=%s, active_expression=%s, gallery_size=%s",
            self.active_vocaloid_folder,
            self.active_vocaloid_expression,
            len(self.vocaloid_gallery),
        )

    def _normalize_persist_path(self, path: str) -> str:
        """去除打包运行时资源根路径，避免保存脏路径。"""
        if not path:
            return path

        normalized_path = os.path.normpath(path)
        resource_root = os.path.normpath(getattr(self, "resource_root", ""))
        bundle_dir = os.path.normpath(getattr(self, "bundle_dir", ""))
        current_dir = os.path.normpath(os.getcwd())
        if resource_root and os.path.isabs(normalized_path):
            try:
                common_path = os.path.commonpath([normalized_path, resource_root])
            except ValueError:
                common_path = ""
            if common_path == resource_root:
                return os.path.relpath(normalized_path, resource_root)
        for base_dir in (bundle_dir, current_dir):
            if not base_dir or not os.path.isabs(normalized_path):
                continue
            try:
                common_path = os.path.commonpath([normalized_path, base_dir])
            except ValueError:
                common_path = ""
            if common_path == base_dir:
                return os.path.relpath(normalized_path, base_dir)

        internal_prefix = f"_internal{os.sep}"
        if normalized_path.startswith(internal_prefix):
            return normalized_path[len(internal_prefix):]
        if normalized_path.startswith("_internal\\") or normalized_path.startswith("_internal/"):
            return normalized_path[len("_internal\\"):] if normalized_path.startswith("_internal\\") else normalized_path[len("_internal/"):]
        return path

    def save_current_config(self, config_file: str = "config.yaml"):
        """保存当前配置到 YAML 文件。"""
        if config_file == "config.yaml" and getattr(self, "config_file", None):
            config_file = self.config_file
        config_to_save = self.config.model_copy(deep=True)
        config_to_save.font_file = self._normalize_persist_path(config_to_save.font_file)
        save_config_file(config_to_save, config_file=config_file)

    def is_vertical_image(self, image: Image.Image) -> bool:
        """
        判断图像是否为竖图
        """
        return image.height * self.ratio > image.width

    def get_foreground_window_process_name(self) -> Optional[str]:
        """
        获取当前前台窗口的进程名称
        """
        try:
            hwnd = win32gui.GetForegroundWindow()
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process = psutil.Process(pid)
            return process.name().lower()

        except Exception as e:
            logging.debug(f"无法获取当前进程名称: {e}")
            return None

    def create_static_gif(self, image_bytes: bytes) -> bytes:
        """
        将图片转换为两帧的静态 GIF（两帧内容相同，但确保是 GIF 格式）
        
        Args:
            image_bytes: PNG 或其他格式的图片字节流
            
        Returns:
            bytes: 两帧 GIF 的字节流
        """
        img = Image.open(io.BytesIO(image_bytes))
        logging.debug("标准 GIF 构建开始: source_size=%s, source_mode=%s", img.size, img.mode)
        img = img.convert("RGBA")
        img_p = img.convert("P", palette=Image.ADAPTIVE, colors=256)
        
        # 创建两帧：第二帧添加一个肉眼不可见的微小差异
        # 这样可以防止 Pillow 优化掉一帧
        frame1 = img_p.copy()
        frame2 = img_p.copy()
        
        # 获取像素数据
        pixels2 = list(frame2.getdata())
        
        # 修改第二帧的第一个像素的最低有效位（肉眼不可见）
        if pixels2:
            # 获取第一个像素的索引
            first_pixel = pixels2[0]
            # 修改最低位（如果是 0 改为 1，如果是 1 改为 0）
            pixels2[0] = first_pixel ^ 1
        
        # 将修改后的像素数据放回
        frame2.putdata(pixels2)
        
        # 保存到 GIF 格式
        with io.BytesIO() as output:
            frame1.save(
                output,
                format="GIF",
                save_all=True,
                append_images=[frame2],
                duration=100,  # 每帧显示 100ms
                loop=0,  # 无限循环
            )
            gif_bytes = output.getvalue()
        logging.debug("标准 GIF 构建完成: gif_size=%s bytes", len(gif_bytes))
        return gif_bytes

    def _render_static_gif(self, image: Image.Image, colors: int = 256, optimize: bool = False) -> bytes:
        """将单张图像渲染为两帧静态 GIF。"""
        img = image.convert("RGBA")
        frame1 = img.convert("P", palette=Image.ADAPTIVE, colors=colors)
        frame2 = frame1.copy()

        pixels2 = list(frame2.getdata())
        if pixels2:
            pixels2[0] = pixels2[0] ^ 1
            frame2.putdata(pixels2)

        with io.BytesIO() as output:
            frame1.save(
                output,
                format="GIF",
                save_all=True,
                append_images=[frame2],
                duration=100,
                loop=0,
                optimize=optimize,
                disposal=2,
            )
            return output.getvalue()

    def _create_wechat_compatible_gif(self, image_bytes: bytes) -> bytes:
        """为微信场景压缩 GIF，避免被识别为普通文件。"""
        source_image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
        attempt_dimensions = [1024, 960, 896, 768, 640]
        attempt_colors = [128, 96, 64, 48]
        target_bytes = 1200 * 1024

        best_gif = None
        best_meta = None

        for max_dimension in attempt_dimensions:
            candidate_image = source_image.copy()
            candidate_image.thumbnail((max_dimension, max_dimension), resample)

            for colors in attempt_colors:
                gif_bytes = self._render_static_gif(candidate_image, colors=colors, optimize=True)
                metadata = (len(gif_bytes), candidate_image.size, colors)
                if best_meta is None or metadata[0] < best_meta[0]:
                    best_gif = gif_bytes
                    best_meta = metadata

                if len(gif_bytes) <= target_bytes:
                    logging.debug(
                        f"微信兼容 GIF 已压缩到 {candidate_image.size[0]}x{candidate_image.size[1]} / {colors} 色 / {len(gif_bytes)} 字节"
                    )
                    return gif_bytes

        if best_meta is not None:
            logging.debug(
                f"微信兼容 GIF 未达到目标体积，使用最优结果 {best_meta[1][0]}x{best_meta[1][1]} / {best_meta[2]} 色 / {best_meta[0]} 字节"
            )
        return best_gif if best_gif is not None else self.create_static_gif(image_bytes)

    def _build_standard_gif(self, image_bytes: bytes) -> bytes:
        """保留原始 GIF 构建逻辑，供 QQ 和默认场景继续使用。"""
        return self.create_static_gif(image_bytes)

    def _build_gif_for_target(self, image_bytes: bytes, process_name: Optional[str]) -> bytes:
        """根据目标应用选择 GIF 输出策略。"""
        process_name = (process_name or "").lower()
        if self.has_active_vocaloid_selection() and process_name in ("weixin.exe", "wechat.exe"):
            logging.debug("检测到微信 + 角色图片场景，启用微信兼容 GIF 压缩方案")
            return self._create_wechat_compatible_gif(image_bytes)
        return self._build_standard_gif(image_bytes)

    def copy_gif_bytes_to_clipboard(self, gif_bytes: bytes):
        """
        以 CF_HDROP（文件拖放）+ GIF 原始字节两种格式写入剪贴板。
        QQ 通过 CF_HDROP 消费文件路径，其他支持 GIF 原生粘贴的应用可读取原始字节。
        """
        from ctypes import windll, memmove, c_uint8

        temp_file = os.path.join(self.bundle_dir, "temp_output.gif")
        with open(temp_file, 'wb') as f:
            f.write(gif_bytes)
        logging.debug("临时 GIF 文件已写入: path=%s, size=%s", temp_file, len(gif_bytes))

        gif_format_id = windll.user32.RegisterClipboardFormatW("GIF")

        GMEM_MOVEABLE = 0x0002
        GMEM_ZEROINIT = 0x0040

        gif_h_mem = None
        hdrop_h_mem = None

        if gif_format_id:
            gif_size = len(gif_bytes)
            gif_h_mem = windll.kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, gif_size)
            if gif_h_mem:
                p_mem = windll.kernel32.GlobalLock(gif_h_mem)
                if p_mem:
                    buf = (c_uint8 * gif_size).from_buffer_copy(gif_bytes)
                    memmove(p_mem, buf, gif_size)
                    windll.kernel32.GlobalUnlock(gif_h_mem)

        files_utf16 = temp_file.encode("utf-16-le") + b"\x00\x00"
        hdrop_size = 20 + len(files_utf16)
        hdrop_h_mem = windll.kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, hdrop_size)
        if hdrop_h_mem:
            p_drop = windll.kernel32.GlobalLock(hdrop_h_mem)
            if p_drop:
                drop_header = (
                    (20).to_bytes(4, "little")
                    + (0).to_bytes(4, "little")
                    + (0).to_bytes(4, "little")
                    + (0).to_bytes(4, "little")
                    + (1).to_bytes(4, "little")
                )
                drop_blob = drop_header + files_utf16
                memmove(p_drop, drop_blob, hdrop_size)
                windll.kernel32.GlobalUnlock(hdrop_h_mem)

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        try:
            if hdrop_h_mem:
                win32clipboard.SetClipboardData(win32clipboard.CF_HDROP, hdrop_h_mem)
                hdrop_h_mem = None
                logging.debug("CF_HDROP 已写入剪贴板: %s", temp_file)
            if gif_format_id and gif_h_mem:
                win32clipboard.SetClipboardData(gif_format_id, gif_h_mem)
                gif_h_mem = None
                logging.debug("GIF 原始字节流已写入剪贴板: format_id=%s", gif_format_id)
        except Exception as e:
            logging.error("剪贴板写入失败：%s", e)
            raise
        finally:
            win32clipboard.CloseClipboard()
            if gif_h_mem:
                windll.kernel32.GlobalFree(gif_h_mem)
            if hdrop_h_mem:
                windll.kernel32.GlobalFree(hdrop_h_mem)

    def cut_all_and_get_text(self) -> Tuple[str, str]:
        """
        模拟 Ctrl+A / Ctrl+X 剪切用户输入的全部文本，并返回剪切得到的内容和原始剪贴板的文本内容。

        这个函数会备份当前剪贴板中的文本内容，然后清空剪贴板。
        """
        # 备份原剪贴板(只能备份文本内容)
        old_clip = pyperclip.paste()
        logging.debug(
            "开始采集文本输入: select_all=%s, cut=%s, previous_clipboard_length=%s",
            self.config.select_all_hotkey,
            self.config.cut_hotkey,
            len(old_clip) if old_clip is not None else None,
        )

        # 清空剪贴板，防止读到旧数据
        pyperclip.copy("")

        # 发送 Ctrl+A 和 Ctrl+X
        keyboard.send(self.config.select_all_hotkey)
        keyboard.send(self.config.cut_hotkey)
        time.sleep(self.config.delay)

        # 获取剪切后的内容
        new_clip = pyperclip.paste()
        logging.debug(
            "文本采集完成: text_length=%s, text_preview=%r",
            len(new_clip) if new_clip is not None else None,
            (new_clip or "")[:120],
        )

        return new_clip, old_clip

    def try_get_image(self) -> Optional[Image.Image]:
        """
        尝试从剪贴板获取图像，如果没有图像则返回 None。
        仅支持 Windows。
        """
        image = None  # 确保无论如何都定义了 image

        try:
            win32clipboard.OpenClipboard()
            logging.debug("开始检查剪贴板图像内容")

            # 检查剪贴板中是否有 DIB 格式的图像
            if not win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_DIB):
                logging.debug("剪贴板中未发现 DIB 图像格式")
                return None

            # 获取 DIB 格式的图像数据
            data = win32clipboard.GetClipboardData(win32clipboard.CF_DIB)
            if not data:
                logging.debug("剪贴板图像数据为空")
                return None

            # 将 DIB 数据转换为字节流，供 Pillow 打开
            bmp_data = data
            # DIB 格式缺少 BMP 文件头，需要手动加上
            # BMP 文件头是 14 字节，包含 "BM" 标识和文件大小信息
            header = (
                b"BM"
                + (len(bmp_data) + 14).to_bytes(4, "little")
                + b"\x00\x00\x00\x00\x36\x00\x00\x00"
            )
            image = Image.open(io.BytesIO(header + bmp_data))
            logging.debug(
                "剪贴板图像读取成功: bytes=%s, size=%s, mode=%s",
                len(bmp_data),
                image.size,
                image.mode,
            )

        except Exception as e:
            logging.debug("无法从剪贴板获取图像：" + str(e))
        finally:
            try:
                win32clipboard.CloseClipboard()
            except:  # noqa: E722
                pass

        return image

    def process_text_and_image(self, text: str, image: Optional[Image.Image]) -> Optional[bytes]:
        """
        同时处理文本和图像内容，将其绘制到同一张图片上
        """
        if text == "" and image is None:
            return None

        image_source, image_overlay = self._get_active_render_assets()
        default_max_font_height = self._get_default_text_max_font_height(image_source)
        bracket_color_rgb = self._get_current_bracket_color()

        x1, y1, x2, y2 = self._get_active_text_region()
        
        region_width = x2 - x1
        region_height = y2 - y1
        logging.debug(
            "渲染参数: image_source=%s, overlay=%s, text_region=((%s,%s),(%s,%s)), region_size=(%s,%s), max_font=%s, bracket_color=%s, font_file=%s, has_image=%s, text_length=%s",
            self._describe_path(image_source if isinstance(image_source, str) else ""),
            self._describe_path(image_overlay if isinstance(image_overlay, str) else ""),
            x1,
            y1,
            x2,
            y2,
            region_width,
            region_height,
            default_max_font_height,
            bracket_color_rgb,
            self._describe_path(self.config.font_file),
            image is not None,
            len(text),
        )

        # 只有图像的情况
        if text == "" and image is not None:
            logging.debug(
                "进入纯图片分支: clipboard_image_size=%sx%s, mode=%s",
                image.width,
                image.height,
                image.mode,
            )
            try:
                return paste_image_auto(
                    image_source=image_source,
                    image_overlay=image_overlay,
                    top_left=(x1, y1),
                    bottom_right=(x2, y2),
                    content_image=image,
                    align="center",
                    valign="middle",
                    padding=12,
                    allow_upscale=True,
                    keep_alpha=True,
                )
            except Exception as e:
                logging.error("生成图片失败: " + str(e))
                return None

        # 只有文本的情况
        elif text != "" and image is None:
            logging.debug("进入纯文本分支: text_preview=%r", text[:120])
            try:
                use_dual_color = False
                max_font_height = default_max_font_height
                logging.debug(
                    "纯文本绘制参数: folder=%s, expression=%s, use_dual_color=%s, max_font_height=%s",
                    self.active_vocaloid_folder,
                    self.active_vocaloid_expression,
                    use_dual_color,
                    max_font_height,
                )
                
                return draw_text_auto(
                    image_source=image_source,
                    image_overlay=image_overlay,
                    top_left=(x1, y1),
                    bottom_right=(x2, y2),
                    text=text,
                    color=(0, 0, 0),
                    max_font_height=max_font_height,
                    font_path=self.config.font_file,
                    bracket_color=bracket_color_rgb,
                    dual_color_mode=use_dual_color,
                )
            except Exception as e:
                logging.error("生成图片失败: " + str(e))
                return None

        # 同时有图像和文本的情况
        else:
            logging.debug(
                "进入图文混排分支: text_preview=%r, clipboard_image_size=%sx%s, mode=%s",
                text[:120],
                image.width,
                image.height,
                image.mode,
            )
            self.get_ratio(x1, y1, x2, y2)
            try:
                # 根据图像方向决定排布方式
                if self.is_vertical_image(image):
                    logging.debug("布局决策: 使用左右排布（竖图）")
                    # 左右排布：图像在左，文本在右
                    # 计算左右区域宽度（各占一半，留出间距）
                    spacing = 10  # 左右区域之间的间距
                    left_width = region_width // 2 - spacing // 2
                    right_width = region_width - left_width - spacing
                    
                    # 左区域（图像）
                    left_region_right = x1 + left_width
                    # 右区域（文本）
                    right_region_left = left_region_right + spacing
                    logging.debug(
                        "左右排布区域: image=((%s,%s),(%s,%s)), text=((%s,%s),(%s,%s)), spacing=%s",
                        x1, y1, left_region_right, y2,
                        right_region_left, y1, x2, y2,
                        spacing,
                    )
                    # 先绘制左半部分的图像
                    intermediate_bytes = paste_image_auto(
                        image_source=image_source,
                        image_overlay=None,  # 暂时不应用overlay
                        top_left=(x1, y1),
                        bottom_right=(left_region_right, y2),
                        content_image=image,
                        align="center",
                        valign="middle",
                        padding=12,
                        allow_upscale=True, 
                        keep_alpha=True,
                    )
                    
                    # 在已有图像基础上添加右半部分的文本
                    final_bytes = draw_text_auto(
                        image_source=io.BytesIO(intermediate_bytes),
                        image_overlay=image_overlay,
                        top_left=(right_region_left, y1),
                        bottom_right=(x2, y2),
                        text=text,
                        color=(0, 0, 0),
                        max_font_height=default_max_font_height,
                        font_path=self.config.font_file,
                        bracket_color=bracket_color_rgb,
                    )
                else:
                    logging.debug("布局决策: 使用上下排布（横图）")
                    # 上下排布：图像在上，文本在下
                    # 动态计算图像和文本的区域分配
                    # 根据文本长度和图像尺寸计算合适的比例
                    
                    # 估算文本所需高度（使用最大字体高度的一半作为初始估算）
                    estimated_text_height = min(
                        region_height // 2,
                        max(100, default_max_font_height + 40),
                    )
                    
                    # 图像区域（上半部分）
                    image_region_bottom = y1 + (region_height - estimated_text_height)
                    
                    # 文本区域（下半部分）
                    text_region_top = image_region_bottom
                    text_region_bottom = y2
                    logging.debug(
                        "上下排布区域: image=((%s,%s),(%s,%s)), text=((%s,%s),(%s,%s)), estimated_text_height=%s",
                        x1, y1, x2, image_region_bottom,
                        x1, text_region_top, x2, text_region_bottom,
                        estimated_text_height,
                    )
                    # 先绘制图像
                    intermediate_bytes = paste_image_auto(
                        image_source=image_source,
                        image_overlay=None,  # 暂时不应用overlay
                        top_left=(x1, y1),
                        bottom_right=(x2, image_region_bottom),
                        content_image=image,
                        align="center",
                        valign="middle",
                        padding=12,
                        allow_upscale=True, 
                        keep_alpha=True,
                    )
                    
                    # 在已有图像基础上添加文本
                    final_bytes = draw_text_auto(
                        image_source=io.BytesIO(intermediate_bytes),
                        image_overlay=image_overlay,
                        top_left=(x1, text_region_top),
                        bottom_right=(x2, text_region_bottom),
                        text=text,
                        color=(0, 0, 0),
                        max_font_height=default_max_font_height,
                        font_path=self.config.font_file,
                        bracket_color=bracket_color_rgb,
                    )
                
                return final_bytes
                
            except Exception as e:
                logging.error("生成图片失败: " + str(e))
                return None

    def generate_image(self):
        """
        生成图像的主函数
        """
        old_clipboard_content = None
        main_hotkey_handle = self.is_hotkey_bound
        generation_started_at = time.perf_counter()

        try:
            # 生成期间临时移除主热键，避免与模拟按键（尤其是 enter）互相触发。
            if main_hotkey_handle:
                keyboard.remove_hotkey(main_hotkey_handle)
                self.is_hotkey_bound = None
                logging.debug("生成开始前已临时解绑主热键: handle=%s", main_hotkey_handle)

            current_process = self.get_foreground_window_process_name()
            logging.debug(
                "生成入口上下文: process=%s, hotkey=%s, block_hotkey=%s, auto_paste=%s, auto_send=%s, selection=%s/%s",
                current_process,
                self.config.hotkey,
                self.config.block_hotkey,
                self.config.auto_paste_image,
                self.config.auto_send_image,
                self.active_vocaloid_folder,
                self.active_vocaloid_expression,
            )

            # 检查是否设置了允许的进程列表，如果设置了，则检查当前进程是否在允许列表中
            if self.config.allowed_processes:
                normalized_processes = [p.lower() for p in self.config.allowed_processes]
                logging.debug("允许进程列表: %s", normalized_processes)
                if current_process is None or current_process not in [
                    p.lower() for p in self.config.allowed_processes
                ]:
                    logging.warning(f"当前进程 {current_process} 不在允许列表中，跳过执行")
                    # 如果不是在允许的进程中，直接发送原始热键
                    if not self.config.block_hotkey:
                        keyboard.send(self.config.hotkey)
                    return

            # `cut_all_and_get_text` 会清空剪切板，所以 `try_get_image` 要在前面调用
            collect_started_at = time.perf_counter()
            user_pasted_image = self.try_get_image()
            user_input, old_clipboard_content = self.cut_all_and_get_text()
            logging.debug(
                "输入采集完成: text_length=%s, has_image=%s, clipboard_backup_length=%s, elapsed_ms=%.2f",
                len(user_input),
                user_pasted_image is not None,
                len(old_clipboard_content) if old_clipboard_content is not None else None,
                (time.perf_counter() - collect_started_at) * 1000,
            )

            if user_input == "" and user_pasted_image is None:
                logging.warning("📢 未检测到有效输入，已取消生成")
                return

            logging.info(f"🚀 开始生成图片 (文本: {len(user_input)} 字, 图片: {'有' if user_pasted_image else '无'})")

            render_started_at = time.perf_counter()
            png_bytes = self.process_text_and_image(user_input, user_pasted_image)

            if png_bytes is None:
                logging.error("生成图片失败！未生成 PNG 字节。")
                return
            logging.debug(
                "PNG 渲染完成: bytes=%s, elapsed_ms=%.2f",
                len(png_bytes),
                (time.perf_counter() - render_started_at) * 1000,
            )

            # 将 PNG 转换为 GIF 格式；微信场景会额外做兼容性压缩
            logging.debug("正在将图片转换为 GIF 格式...")
            gif_started_at = time.perf_counter()
            gif_bytes = self._build_gif_for_target(png_bytes, current_process)
            logging.debug(
                "GIF 转换完成: bytes=%s, elapsed_ms=%.2f",
                len(gif_bytes),
                (time.perf_counter() - gif_started_at) * 1000,
            )

            # 复制到剪贴板并发送
            if self.config.auto_paste_image:
                # 复制到剪贴板
                clipboard_started_at = time.perf_counter()
                self.copy_gif_bytes_to_clipboard(gif_bytes)
                logging.debug(
                    "GIF 已复制到剪贴板: elapsed_ms=%.2f",
                    (time.perf_counter() - clipboard_started_at) * 1000,
                )
                
                # 使用剪贴板方式粘贴发送
                paste_started_at = time.perf_counter()
                keyboard.send(self.config.paste_hotkey)
                time.sleep(self.config.delay)
                logging.debug(
                    "自动粘贴完成: hotkey=%s, elapsed_ms=%.2f",
                    self.config.paste_hotkey,
                    (time.perf_counter() - paste_started_at) * 1000,
                )
                
                if self.config.auto_send_image:
                    send_started_at = time.perf_counter()
                    keyboard.send(self.config.send_hotkey)
                    logging.debug(
                        "自动发送完成: hotkey=%s, elapsed_ms=%.2f",
                        self.config.send_hotkey,
                        (time.perf_counter() - send_started_at) * 1000,
                    )
            else:
                # 不自动粘贴，只保存文件
                temp_file = os.path.join(self.bundle_dir, "temp_output.gif")
                with open(temp_file, 'wb') as f:
                    f.write(gif_bytes)
                logging.debug(f"GIF 文件已保存：{temp_file}")

            logging.info("✨ 生成并发送成功！")
            logging.debug(
                "本次生成总耗时: elapsed_ms=%.2f",
                (time.perf_counter() - generation_started_at) * 1000,
            )
        finally:
            if old_clipboard_content is not None:
                pyperclip.copy(old_clipboard_content)
                logging.debug("已恢复原剪贴板文本内容")

            self._bind_main_hotkey()
            logging.debug("生成流程结束，主热键重新绑定完成")

    def get_ratio(self, x1, y1, x2, y2):
        try:
            self.ratio = (x2 - x1) / (y2 - y1)
            logging.debug("比例: " + str(self.ratio))
        except Exception as e:
            logging.debug("计算比例时出错: " + str(e))

    def run(self):
        """运行应用程序"""
        try:
            # 运行UI主循环
            self.ui.root.mainloop()
            
        except KeyboardInterrupt:
            logging.info("收到键盘中断信号，正在退出...")
            self.stop()
        except Exception as e:
            logging.error(f"运行时发生错误: {str(e)}")
            logging.exception(e)
            
    def stop(self):
        """停止应用程序"""
        if self.is_hotkey_bound:
            keyboard.remove_hotkey(self.is_hotkey_bound)
            self.is_hotkey_bound = None
        logging.info("应用程序已停止")


def main():
    try:
        app = AnanSketchbookApp()
        app.run()
    except Exception as e:
        logging.critical(f"程序启动失败: {e}")
        logging.exception(e)
        print(f"启动应用时发生错误: {e}")


if __name__ == "__main__":
    main()
