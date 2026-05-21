# filename: text_fit_draw.py
import logging
import os
import sys
from io import BytesIO
from typing import List, Literal, Optional, Tuple, Union

from PIL import Image, ImageDraw, ImageFont

RGBColor = Tuple[int, int, int]

Align = Literal["left", "center", "right"]
VAlign = Literal["top", "middle", "bottom"]


def get_resource_path(relative_path: str) -> str:
    """
    获取资源文件的绝对路径，优先尊重当前路径，其次兼容 PyInstaller 打包目录。
    """
    if not relative_path:
        return ""

    normalized_path = os.path.normpath(relative_path)
    if os.path.isabs(normalized_path) and os.path.exists(normalized_path):
        return normalized_path

    candidate_paths = [
        normalized_path,
        os.path.join(os.getcwd(), normalized_path),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), normalized_path),
    ]

    if getattr(sys, "frozen", False):
        candidate_paths.insert(1, os.path.join(sys._MEIPASS, normalized_path))
        candidate_paths.insert(2, os.path.join(os.path.dirname(sys.executable), normalized_path))

    for candidate in candidate_paths:
        if candidate and os.path.exists(candidate):
            return os.path.normpath(candidate)

    # 找不到时仍返回最合理的候选路径，便于上层继续判断和记录日志。
    return os.path.normpath(candidate_paths[-1])


def _load_font(font_path: Optional[str], size: int) -> ImageFont.FreeTypeFont:
    """
    加载指定路径的字体文件，如果失败则使用系统支持中文的字体。
    """
    # 首先尝试使用配置的字体路径
    if font_path:
        actual_path = get_resource_path(font_path)
        if os.path.exists(actual_path):
            try:
                return ImageFont.truetype(actual_path, size=size)
            except Exception as e:
                logging.debug("加载字体失败: path=%s, size=%s, error=%s", actual_path, size, e)
    
    # 如果配置的字体不可用，尝试使用系统支持中文的字体
    # Windows 系统常用中文字体
    system_fonts = [
        ("msyh.ttc", "Microsoft YaHei"),  # 微软雅黑
        ("simsun.ttc", "SimSun"),          # 宋体
        ("simhei.ttf", "SimHei"),          # 黑体
        ("msyhbd.ttc", "Microsoft YaHei Bold"),  # 微软雅黑粗体
    ]
    
    for font_file, font_name in system_fonts:
        try:
            return ImageFont.truetype(font_file, size=size)
        except Exception:
            continue
    
    # 最后的备选方案
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size=size)
    except Exception:
        return ImageFont.load_default()  # type: ignore


def wrap_lines(
    draw: ImageDraw.ImageDraw, txt: str, font: ImageFont.FreeTypeFont, max_w: int
) -> List[str]:
    """
    将文本按指定宽度拆分为多行。
    
    特殊规则：
    - `】` / `]` 不能在最左边，如果出现，需要将其移到上一行最右侧
    - `【` / `[` 如果在最右侧，则转到下一行
    - 结束括号尽量不要独占新行开头
    """
    lines: List[str] = []

    for para in txt.splitlines() or [""]:
        has_space = " " in para
        units = para.split(" ") if has_space else list(para)
        buf = ""

        def unit_join(a: str, b: str) -> str:
            if not a:
                return b
            return (a + " " + b) if has_space else (a + b)

        for u in units:
            trial = unit_join(buf, u)
            w = draw.textlength(trial, font=font)

            # 如果加入当前单元后宽度未超限，则继续累积
            if w <= max_w:
                buf = trial
                continue

            # 否则先将缓冲区内容作为一行输出
            if buf:
                lines.append(buf)

            # 处理当前单元
            if has_space and len(u) > 1:
                tmp = ""
                for ch in u:
                    if draw.textlength(tmp + ch, font=font) <= max_w:
                        tmp += ch
                        continue

                    if tmp:
                        lines.append(tmp)
                    tmp = ch
                buf = tmp
                continue

            if draw.textlength(u, font=font) <= max_w:
                buf = u
            else:
                lines.append(u)
                buf = ""
        if buf != "":
            lines.append(buf)
        if para == "" and (not lines or lines[-1] != ""):
            lines.append("")
    
    # 处理【】符号的特殊排布规则
    lines = fix_bracket_lines(lines)
    
    return lines


def fix_bracket_lines(lines: List[str]) -> List[str]:
    """
    修复 `【】` 和 `[]` 的排布问题：
    1. `】` / `]` 不能在最左边，如果出现，需要将它移到上一行的最右边
    2. `【` / `[` 如果在最右侧，则转到下一行
    3. 结束括号如果出现在最后一行开头，也会尽量并回上一行
    """
    if not lines:
        return lines
    
    result = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # 规则 1 和 3：处理结束括号出现在最左边（包括第一行和最后一行）
        if line.startswith(("】", "]")) and len(line) > 1:
            if result:
                result[-1] = result[-1] + line[0]
                line = line[1:]  # 移除当前行开头的】
                if line:  # 如果当前行还有其他内容
                    result.append(line)
                i += 1
                continue
            else:
                line = line[1:]
                if not line:  # 如果当前行为空，跳过
                    i += 1
                    continue
        
        # 规则 2：处理起始括号出现在最右边的情况
        if line.endswith(("【", "[")) and len(line) > 1:
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                result.append(line[:-1])
                lines[i + 1] = line[-1] + next_line
                i += 1
                continue
            else:
                result.append(line)
                i += 1
                continue
        
        result.append(line)
        i += 1
    
    return result


def parse_color_segments(
    s: str, in_bracket: bool, bracket_color: RGBColor, color: RGBColor
) -> Tuple[List[Tuple[str, RGBColor]], bool]:
    """
    解析字符串为带颜色信息的片段列表。
    中括号及其内部内容使用 bracket_color。
    """
    segs: List[Tuple[str, RGBColor]] = []
    buf = ""
    for ch in s:
        if ch == "[" or ch == "【":
            if buf:
                segs.append((buf, bracket_color if in_bracket else color))
                buf = ""
            segs.append((ch, bracket_color))
            in_bracket = True
        elif ch == "]" or ch == "】":
            if buf:
                segs.append((buf, bracket_color))
                buf = ""
            segs.append((ch, bracket_color))
            in_bracket = False
        else:
            buf += ch
    if buf:
        segs.append((buf, bracket_color if in_bracket else color))
    return segs, in_bracket


def measure_block(
    draw: ImageDraw.ImageDraw,
    lines: List[str],
    font: ImageFont.FreeTypeFont,
    line_spacing: float,
) -> Tuple[int, int, int]:
    """
    测量文本块的宽度、高度和行高。

    :return: (最大宽度, 总高度, 行高)
    """
    ascent, descent = font.getmetrics()
    line_h = int((ascent + descent) * (1 + line_spacing))
    max_w = 0
    for ln in lines:
        max_w = max(max_w, int(draw.textlength(ln, font=font)))
    total_h = max(line_h * max(1, len(lines)), 1)
    return max_w, total_h, line_h


def draw_text_auto(
    image_source: Union[str, Image.Image],
    top_left: Tuple[int, int],
    bottom_right: Tuple[int, int],
    text: str,
    color: RGBColor = (0, 0, 0),
    max_font_height: Optional[int] = None,
    font_path: Optional[str] = None,
    align: Align = "center",
    valign: VAlign = "middle",
    line_spacing: float = 0.15,
    bracket_color: RGBColor = (128, 0, 128),  # 中括号及括号内内容颜色
    image_overlay: Union[str, Image.Image, None] = None,
    dual_color_mode: bool = False,  # 双色模式：以中线为界，左蓝右红
    left_color: RGBColor = (102, 204, 255),  # #66CCFF 左侧蓝色
    right_color: RGBColor = (238, 0, 0),  # #EE0000 右侧红色
) -> bytes:
    """
    在指定矩形内自适应字号绘制文本；
    中括号及括号内文字使用 bracket_color。
    如果 dual_color_mode=True，则以中线为界，左侧使用 left_color，右侧使用 right_color。
    """

    # --- 1. 打开图像 ---
    if isinstance(image_source, Image.Image):
        img = image_source.copy()
    else:
        img = Image.open(image_source).convert("RGBA")
    draw = ImageDraw.Draw(img)

    if image_overlay is not None:
        if isinstance(image_overlay, Image.Image):
            img_overlay = image_overlay.copy()
        else:
            img_overlay = (
                Image.open(image_overlay).convert("RGBA")
                if os.path.isfile(image_overlay)
                else None
            )
    else:
        img_overlay = None

    x1, y1 = top_left
    x2, y2 = bottom_right
    if not (x2 > x1 and y2 > y1):
        raise ValueError("无效的文字区域。")
    region_w, region_h = x2 - x1, y2 - y1

    # --- 2. 搜索最大字号 ---
    hi = min(region_h, max_font_height) if max_font_height else region_h
    lo, best_size, best_lines, best_line_h, best_block_h = 1, 0, [], 0, 0

    while lo <= hi:
        mid = (lo + hi) // 2
        font = _load_font(font_path, mid)
        lines = wrap_lines(draw, text, font, region_w)
        w, h, lh = measure_block(draw, lines, font, line_spacing)
        if w <= region_w and h <= region_h:
            best_size, best_lines, best_line_h, best_block_h = mid, lines, lh, h
            lo = mid + 1
        else:
            hi = mid - 1

    if best_size == 0:
        font = _load_font(font_path, 1)
        best_lines = wrap_lines(draw, text, font, region_w)
        best_block_h, best_line_h = 1, 1
        best_size = 1
    else:
        font = _load_font(font_path, best_size)

    # --- 3. 垂直对齐 ---
    if valign == "top":
        y_start = y1
    elif valign == "middle":
        y_start = y1 + (region_h - best_block_h) // 2
    else:
        y_start = y2 - best_block_h

    # --- 4. 绘制 ---
    # 计算中线位置（用于双色模式）
    mid_x = x1 + region_w // 2 if dual_color_mode else 0
    
    y = y_start
    in_bracket = False
    for ln in best_lines:
        line_w = int(draw.textlength(ln, font=font))
        if align == "left":
            x = x1
        elif align == "center":
            x = x1 + (region_w - line_w) // 2
        else:
            x = x2 - line_w
        
        # 如果是双色模式，需要逐字符绘制
        if dual_color_mode:
            # 逐字符绘制，根据字符中心位置和是否在括号内决定颜色
            current_x = x
            in_bracket = False  # 每行重新开始判断括号状态
            
            for ch in ln:
                ch_width = int(draw.textlength(ch, font=font))
                char_center = current_x + ch_width // 2
                
                # 判断是否在括号内
                if ch == "【" or ch == "[":
                    in_bracket = True
                    # 括号本身使用双色
                    if char_center < mid_x:
                        char_color = left_color
                    else:
                        char_color = right_color
                elif ch == "】" or ch == "]":
                    # 括号本身使用双色
                    if char_center < mid_x:
                        char_color = left_color
                    else:
                        char_color = right_color
                    in_bracket = False
                elif in_bracket:
                    # 括号内的文字使用双色
                    if char_center < mid_x:
                        char_color = left_color
                    else:
                        char_color = right_color
                else:
                    # 括号外的普通文字保持黑色
                    char_color = color
                
                draw.text((current_x, y), ch, font=font, fill=char_color)
                current_x += ch_width
        else:
            # 常规模式：按段绘制
            segments, in_bracket = parse_color_segments(
                ln, in_bracket, bracket_color, color
            )
            for seg_text, seg_color in segments:
                if seg_text:
                    draw.text((x, y), seg_text, font=font, fill=seg_color)
                    x += int(draw.textlength(seg_text, font=font))
        
        y += best_line_h
        if y - y_start > region_h:
            break

    # 覆盖置顶图层（如果有）
    if image_overlay is not None and img_overlay is not None:
        img.paste(img_overlay, (0, 0), img_overlay)
    elif image_overlay is not None and img_overlay is None:
        print("Warning: overlay image is not exist.")

    # --- 5. 输出 PNG ---
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
