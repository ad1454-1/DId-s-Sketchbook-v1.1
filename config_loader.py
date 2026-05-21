import os
import yaml
from typing import Any, List
from pydantic import BaseModel, Field

DEFAULT_ALLOWED_PROCESSES = ["qq.exe", "weixin.exe"]


class UISettings(BaseModel):
    """UI 设置模型类"""
    font_family: str = "Microsoft YaHei"
    font_size: int = 10
    title_font_size: int = 12
    window_width: int = 650
    window_height: int = 500
    theme: str = "blue"  # 可选：blue, green, dark-blue


class Config(BaseModel):
    """配置模型类"""
    hotkey: str = "enter"
    """全局热键，用于 keyboard 库"""
    allowed_processes: List[str] = Field(default_factory=lambda: list(DEFAULT_ALLOWED_PROCESSES))
    """允许的进程列表"""
    select_all_hotkey: str = "ctrl+a"
    """全选快捷键"""
    cut_hotkey: str = "ctrl+x"
    """剪切快捷键"""
    paste_hotkey: str = "ctrl+v"
    """黏贴快捷键"""
    send_hotkey: str = "enter"
    """发送消息快捷键"""
    block_hotkey: bool = False
    """阻塞热键"""
    delay: float = 0.1
    """操作延时（秒）"""
    font_file: str = "Fonts" + os.sep + "font.ttf"
    """字体文件路径"""
    auto_paste_image: bool = True
    """是否自动黏贴图片"""
    auto_send_image: bool = True
    """是否自动发送图片"""
    logging_level: str = "INFO"
    """日志记录等级"""
    ui_settings: UISettings = Field(default_factory=UISettings)
    """UI 设置"""

    class Config:
        arbitrary_types_allowed = True


def load_config(config_file: str = "config.yaml") -> Config:
    """
    从YAML文件加载配置
    
    Args:
        config_file: 配置文件路径
        
    Returns:
        Config: 配置对象
    """
    # 如果配置文件不存在，使用默认配置
    if not os.path.exists(config_file):
        return Config()
    
    # 读取YAML配置文件
    with open(config_file, 'r', encoding='utf-8') as f:
        config_data = yaml.safe_load(f)
    
    # 处理UI设置
    if 'ui_settings' in config_data:
        config_data['ui_settings'] = UISettings(**config_data['ui_settings'])

    # 迁移旧版根目录输出字体路径到 Fonts 目录
    if config_data.get('font_file') in (None, "", "font.ttf"):
        migrated_font_path = os.path.join("Fonts", "font.ttf")
        if os.path.exists(migrated_font_path):
            config_data['font_file'] = migrated_font_path
    
    # 创建并返回配置对象
    return Config(**config_data)


def _yaml_safe_value(value: Any) -> Any:
    """将配置对象递归转换为适合 YAML 序列化的基础类型。"""
    if isinstance(value, BaseModel):
        return _yaml_safe_value(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {key: _yaml_safe_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_yaml_safe_value(item) for item in value]
    if isinstance(value, list):
        return [_yaml_safe_value(item) for item in value]
    return value


def save_config(config: Config, config_file: str = "config.yaml") -> None:
    """将配置对象保存到 YAML 文件。"""
    config_data = _yaml_safe_value(config)
    with open(config_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_data, f, allow_unicode=True, sort_keys=False)
