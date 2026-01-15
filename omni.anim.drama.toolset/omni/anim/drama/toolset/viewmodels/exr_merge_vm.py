# -*- coding: utf-8 -*-
"""
EXR Merge ViewModel
===================

EXR AOV 合并功能的 ViewModel。
"""

import os
from typing import Optional, List
import asyncio
import threading

from .base_viewmodel import BaseViewModel
from ..core import exr_merge


class ExrMergeViewModel(BaseViewModel):
    """
    EXR Merge ViewModel。
    
    管理 EXR AOV 合并的状态和业务逻辑。
    """
    
    def __init__(self):
        """初始化 ViewModel。"""
        super().__init__()
        
        # 状态
        self._src_dir: str = ""
        self._out_dir: str = ""
        self._shot_name: str = "E001_C020"
        self._keep_singles: bool = True
        self._dtype: str = "HALF"
        self._workers: int = 0
        
        # 依赖状态
        self._deps_ok: bool = False
        
        # 扫描结果
        self._scanned_frames: List[str] = []
        self._scanned_aovs: List[str] = []
        
        # 运行状态
        self._is_running: bool = False
    
    # =========================================================================
    # 属性
    # =========================================================================
    
    @property
    def src_dir(self) -> str:
        return self._src_dir
    
    @src_dir.setter
    def src_dir(self, value: str) -> None:
        self._src_dir = value
    
    @property
    def out_dir(self) -> str:
        return self._out_dir
    
    @out_dir.setter
    def out_dir(self, value: str) -> None:
        self._out_dir = value
    
    @property
    def shot_name(self) -> str:
        return self._shot_name
    
    @shot_name.setter
    def shot_name(self, value: str) -> None:
        self._shot_name = value
    
    @property
    def keep_singles(self) -> bool:
        return self._keep_singles
    
    @keep_singles.setter
    def keep_singles(self, value: bool) -> None:
        self._keep_singles = value
    
    @property
    def dtype(self) -> str:
        return self._dtype
    
    @dtype.setter
    def dtype(self, value: str) -> None:
        self._dtype = value
    
    @property
    def workers(self) -> int:
        return self._workers
    
    @workers.setter
    def workers(self, value: int) -> None:
        self._workers = value
    
    @property
    def deps_ok(self) -> bool:
        return self._deps_ok
    
    @property
    def scanned_frames(self) -> List[str]:
        return self._scanned_frames
    
    @property
    def scanned_aovs(self) -> List[str]:
        return self._scanned_aovs
    
    @property
    def is_running(self) -> bool:
        return self._is_running
    
    # =========================================================================
    # 命令
    # =========================================================================
    
    def check_dependencies(self) -> None:
        """检查并安装依赖。"""
        self.log("Checking OpenEXR/Imath dependencies...")
        ok, msg = exr_merge.ensure_openexr_imath_in_proc()
        self._deps_ok = ok
        if ok:
            self.log(f"✓ {msg}")
        else:
            self.log(f"✗ {msg}")
    
    def scan_source(self) -> str:
        """
        扫描源目录。
        
        Returns:
            扫描结果摘要
        """
        if not self._src_dir or not os.path.isdir(self._src_dir):
            self._scanned_frames = []
            self._scanned_aovs = []
            return "Please select a valid source folder."
        
        self._scanned_frames = exr_merge.scan_frames(self._src_dir)
        self._scanned_aovs = exr_merge.scan_aovs(self._src_dir)
        
        if not self._scanned_frames:
            return "No EXR files matching pattern: Capture.<frame>_<AOV>.exr"
        
        # 检查帧号是否为4位数
        ok4 = all(len(f) == 4 for f in self._scanned_frames)
        digits_info = "OK 4" if ok4 else "non-4 detected"
        
        frame_examples = self._scanned_frames[:6]
        aov_list = ", ".join(self._scanned_aovs[:10])
        if len(self._scanned_aovs) > 10:
            aov_list += f"... (+{len(self._scanned_aovs) - 10})"
        
        self.log(f"Scanned {len(self._scanned_frames)} frames, {len(self._scanned_aovs)} AOVs")
        
        return (
            f"Frames: {len(self._scanned_frames)}  "
            f"Examples: {frame_examples}  "
            f"Digits: {digits_info}\n"
            f"AOVs: {aov_list}"
        )
    
    def run_merge(self) -> None:
        """执行合并操作。"""
        if self._is_running:
            self.log("Merge is already running.")
            return
        
        if not self._src_dir or not os.path.isdir(self._src_dir):
            self.log("Invalid source folder.")
            return
        
        self._is_running = True
        self.set_status("Running...")
        
        # 在后台线程执行
        def _run():
            try:
                out_dir = self._out_dir or os.path.join(self._src_dir, "packed")
                shot = self._shot_name.strip() or "SHOT"
                
                success, msg = exr_merge.run_merge_external(
                    src_dir=self._src_dir,
                    out_dir=out_dir,
                    shot_name=shot,
                    keep_singles=self._keep_singles,
                    dtype=self._dtype,
                    workers=self._workers,
                    log_callback=self.log
                )
                
                if success:
                    self.set_status("Merge completed!")
                else:
                    self.set_status(f"Merge failed: {msg}")
            except Exception as e:
                self.log(f"Error: {e}")
                self.set_status("Error occurred")
            finally:
                self._is_running = False
        
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
    
    # =========================================================================
    # 生命周期
    # =========================================================================
    
    def dispose(self) -> None:
        """清理资源。"""
        super().dispose()
        self._scanned_frames.clear()
        self._scanned_aovs.clear()


