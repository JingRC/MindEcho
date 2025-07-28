"""
MindEcho 性能模式管理器
支持高性能、平衡、安静三种模式
"""

import numpy as np
import threading
import time
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any

class PerformanceMode(Enum):
    """性能模式枚举"""
    QUIET = "安静模式"      # 最低配置，节省资源
    BALANCED = "平衡模式"   # 合理优化配置
    HIGH_PERFORMANCE = "高性能模式"  # 充分利用计算资源

@dataclass
class PerformanceConfig:
    """性能配置参数"""
    # 音频处理参数
    chunk_size: int
    buffer_size: int
    overlap_ratio: float
    
    # 检测参数
    detection_frequency: float  # Hz
    yin_threshold: float
    signal_threshold: float
    
    # 资源使用参数
    use_gpu_acceleration: bool
    thread_pool_size: int
    memory_buffer_mb: int
    
    # 质量参数
    interpolation_factor: int  # 数据插值倍数
    smoothing_window: int
    gradient_quality: str  # "basic", "enhanced", "ultra"
    
    # 优化选项
    enable_prefetch: bool
    enable_parallel_processing: bool
    enable_cache: bool

class PerformanceManager:
    """性能模式管理器"""
    
    def __init__(self):
        self.current_mode = PerformanceMode.BALANCED
        self.current_config = None
        self.gpu_available = self._check_gpu_availability()
        self.cpu_cores = self._get_cpu_cores()
        self.memory_gb = self._get_memory_info()
        
        # 预定义配置
        self.configs = {
            PerformanceMode.QUIET: self._create_quiet_config(),
            PerformanceMode.BALANCED: self._create_balanced_config(), 
            PerformanceMode.HIGH_PERFORMANCE: self._create_high_performance_config()
        }
        
        self.current_config = self.configs[self.current_mode]
        
        print(f"🖥️ 性能管理器初始化完成")
        print(f"   GPU可用: {'✅' if self.gpu_available else '❌'}")
        print(f"   CPU核心: {self.cpu_cores}")
        print(f"   内存: {self.memory_gb:.1f}GB")
        print(f"   当前模式: {self.current_mode.value}")
    
    def _check_gpu_availability(self) -> bool:
        """检查GPU可用性"""
        try:
            # 检查CUDA
            import cupy
            cupy.cuda.runtime.getDeviceCount()
            return True
        except:
            try:
                # 检查OpenCL
                import pyopencl as cl
                platforms = cl.get_platforms()
                return len(platforms) > 0
            except:
                return False
    
    def _get_cpu_cores(self) -> int:
        """获取CPU核心数"""
        import os
        return os.cpu_count() or 4
    
    def _get_memory_info(self) -> float:
        """获取内存信息（GB）"""
        try:
            import psutil
            return psutil.virtual_memory().total / (1024**3)
        except:
            return 8.0  # 默认假设8GB
    
    def _create_quiet_config(self) -> PerformanceConfig:
        """创建安静模式配置 - 最低资源消耗"""
        return PerformanceConfig(
            # 音频处理 - 大块处理，低频率
            chunk_size=2048,
            buffer_size=4096,
            overlap_ratio=0.25,
            
            # 检测参数 - 降低精度，提高速度
            detection_frequency=15.0,  # 15Hz检测频率
            yin_threshold=0.3,         # 较高阈值，减少计算
            signal_threshold=0.001,
            
            # 资源使用 - 最小化
            use_gpu_acceleration=False,
            thread_pool_size=1,
            memory_buffer_mb=32,
            
            # 质量参数 - 基础质量
            interpolation_factor=1,
            smoothing_window=3,
            gradient_quality="basic",
            
            # 优化选项 - 关闭复杂功能
            enable_prefetch=False,
            enable_parallel_processing=False,
            enable_cache=True
        )
    
    def _create_balanced_config(self) -> PerformanceConfig:
        """创建平衡模式配置 - 合理的性能与质量平衡"""
        return PerformanceConfig(
            # 音频处理 - 中等配置
            chunk_size=1024,
            buffer_size=2048,
            overlap_ratio=0.5,
            
            # 检测参数 - 平衡精度与速度
            detection_frequency=30.0,  # 30Hz检测频率
            yin_threshold=0.25,
            signal_threshold=0.0008,
            
            # 资源使用 - 适度使用
            use_gpu_acceleration=self.gpu_available,
            thread_pool_size=min(2, self.cpu_cores // 2),
            memory_buffer_mb=64,
            
            # 质量参数 - 增强质量
            interpolation_factor=2,
            smoothing_window=5,
            gradient_quality="enhanced",
            
            # 优化选项 - 部分启用
            enable_prefetch=True,
            enable_parallel_processing=self.cpu_cores > 2,
            enable_cache=True
        )
    
    def _create_high_performance_config(self) -> PerformanceConfig:
        """创建高性能模式配置 - 充分利用计算资源"""
        return PerformanceConfig(
            # 音频处理 - 小块高频处理
            chunk_size=512,
            buffer_size=1024,
            overlap_ratio=0.75,
            
            # 检测参数 - 最高精度
            detection_frequency=60.0,  # 60Hz检测频率
            yin_threshold=0.2,
            signal_threshold=0.0005,
            
            # 资源使用 - 充分利用
            use_gpu_acceleration=self.gpu_available,
            thread_pool_size=self.cpu_cores,
            memory_buffer_mb=min(256, int(self.memory_gb * 1024 * 0.1)),  # 10%内存
            
            # 质量参数 - 最高质量
            interpolation_factor=4,
            smoothing_window=7,
            gradient_quality="ultra",
            
            # 优化选项 - 全部启用
            enable_prefetch=True,
            enable_parallel_processing=True,
            enable_cache=True
        )
    
    def set_performance_mode(self, mode: PerformanceMode) -> bool:
        """设置性能模式"""
        if mode not in self.configs:
            print(f"❌ 无效的性能模式: {mode}")
            return False
        
        old_mode = self.current_mode
        self.current_mode = mode
        self.current_config = self.configs[mode]
        
        print(f"🔄 性能模式切换: {old_mode.value} → {mode.value}")
        self._print_config_details()
        
        return True
    
    def get_current_config(self) -> PerformanceConfig:
        """获取当前配置"""
        return self.current_config
    
    def get_current_mode(self) -> PerformanceMode:
        """获取当前模式"""
        return self.current_mode
    
    def _print_config_details(self):
        """打印配置详情"""
        config = self.current_config
        print(f"📊 {self.current_mode.value} 配置详情:")
        print(f"   🎵 音频: 块大小={config.chunk_size}, 检测频率={config.detection_frequency}Hz")
        print(f"   🧠 处理: 线程={config.thread_pool_size}, 内存={config.memory_buffer_mb}MB")
        print(f"   🎨 质量: 插值={config.interpolation_factor}x, 渐变={config.gradient_quality}")
        print(f"   ⚡ 加速: GPU={'✅' if config.use_gpu_acceleration else '❌'}, 并行={'✅' if config.enable_parallel_processing else '❌'}")
    
    def get_system_info(self) -> Dict[str, Any]:
        """获取系统信息"""
        return {
            'cpu_cores': self.cpu_cores,
            'memory_gb': self.memory_gb,
            'gpu_available': self.gpu_available,
            'current_mode': self.current_mode.value,
            'recommended_mode': self._get_recommended_mode().value
        }
    
    def _get_recommended_mode(self) -> PerformanceMode:
        """根据系统配置推荐性能模式"""
        if self.cpu_cores >= 8 and self.memory_gb >= 16 and self.gpu_available:
            return PerformanceMode.HIGH_PERFORMANCE
        elif self.cpu_cores >= 4 and self.memory_gb >= 8:
            return PerformanceMode.BALANCED
        else:
            return PerformanceMode.QUIET
    
    def optimize_for_realtime(self) -> Dict[str, Any]:
        """为实时处理优化配置"""
        config = self.current_config
        
        # 计算理论最大检测频率
        theoretical_max_freq = config.detection_frequency
        
        # 根据块大小调整
        sample_rate = 44100
        actual_callback_freq = sample_rate / config.chunk_size
        
        # 预测实际性能
        processing_overhead = {
            PerformanceMode.QUIET: 0.3,      # 30%开销
            PerformanceMode.BALANCED: 0.5,   # 50%开销  
            PerformanceMode.HIGH_PERFORMANCE: 0.8  # 80%开销（更复杂算法）
        }
        
        overhead = processing_overhead[self.current_mode]
        predicted_actual_freq = actual_callback_freq * (1 - overhead)
        
        return {
            'theoretical_detection_frequency': theoretical_max_freq,
            'callback_frequency': actual_callback_freq,
            'predicted_actual_frequency': predicted_actual_freq,
            'processing_overhead': overhead,
            'chunk_size': config.chunk_size,
            'recommendations': self._get_performance_recommendations()
        }
    
    def _get_performance_recommendations(self) -> list:
        """获取性能优化建议"""
        recommendations = []
        config = self.current_config
        
        if config.detection_frequency < 25:
            recommendations.append("🐌 检测频率较低，考虑升级到平衡模式")
        
        if not config.use_gpu_acceleration and self.gpu_available:
            recommendations.append("🚀 GPU可用但未启用，考虑启用GPU加速")
        
        if config.thread_pool_size == 1 and self.cpu_cores > 2:
            recommendations.append("🔄 单线程处理，考虑启用多线程并行")
        
        if config.memory_buffer_mb < 64 and self.memory_gb > 4:
            recommendations.append("💾 内存缓冲区较小，可适当增加")
        
        return recommendations

# 全局性能管理器实例
_global_performance_manager = None

def get_performance_manager() -> PerformanceManager:
    """获取全局性能管理器实例"""
    global _global_performance_manager
    if _global_performance_manager is None:
        _global_performance_manager = PerformanceManager()
    return _global_performance_manager

def set_global_performance_mode(mode: PerformanceMode) -> bool:
    """设置全局性能模式"""
    manager = get_performance_manager()
    return manager.set_performance_mode(mode)

if __name__ == "__main__":
    # 测试性能管理器
    manager = PerformanceManager()
    
    print("\n" + "="*50)
    print("性能模式测试")
    print("="*50)
    
    for mode in PerformanceMode:
        print(f"\n🔄 测试 {mode.value}:")
        manager.set_performance_mode(mode)
        optimization = manager.optimize_for_realtime()
        print(f"   预测检测频率: {optimization['predicted_actual_frequency']:.1f}Hz")
        for rec in optimization['recommendations']:
            print(f"   {rec}")
    
    print(f"\n🖥️ 系统信息:")
    info = manager.get_system_info()
    for key, value in info.items():
        print(f"   {key}: {value}")
