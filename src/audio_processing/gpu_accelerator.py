"""
GPU加速音频处理器
支持CUDA/OpenCL加速的音高检测和可视化
"""

import numpy as np
import time
from typing import Optional, Tuple, List
import threading

class GPUAcceleratedProcessor:
    """GPU加速音频处理器"""
    
    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = sample_rate
        self.gpu_available = False
        self.gpu_type = None
        self.context = None
        
        # 尝试初始化GPU
        self._initialize_gpu()
        
    def _initialize_gpu(self):
        """初始化GPU计算环境"""
        # 尝试CUDA
        try:
            import cupy as cp
            cp.cuda.runtime.getDeviceCount()
            self.gpu_available = True
            self.gpu_type = "CUDA"
            self.cp = cp
            print("✅ CUDA GPU 加速已启用")
            return
        except Exception as e:
            print(f"⚠️ CUDA 不可用: {e}")
        
        # 尝试OpenCL
        try:
            import pyopencl as cl
            platforms = cl.get_platforms()
            if platforms:
                self.context = cl.Context()
                self.queue = cl.CommandQueue(self.context)
                self.gpu_available = True
                self.gpu_type = "OpenCL"
                self.cl = cl
                print("✅ OpenCL GPU 加速已启用")
                return
        except Exception as e:
            print(f"⚠️ OpenCL 不可用: {e}")
        
        print("❌ GPU 加速不可用，使用 CPU 处理")
    
    def is_gpu_available(self) -> bool:
        """检查GPU是否可用"""
        return self.gpu_available
    
    def accelerated_yin_detection(self, audio_data: np.ndarray, threshold: float = 0.25) -> Tuple[float, float]:
        """GPU加速的YIN音高检测"""
        if not self.gpu_available:
            return self._cpu_yin_detection(audio_data, threshold)
        
        try:
            if self.gpu_type == "CUDA":
                return self._cuda_yin_detection(audio_data, threshold)
            elif self.gpu_type == "OpenCL":
                return self._opencl_yin_detection(audio_data, threshold)
        except Exception as e:
            print(f"⚠️ GPU 检测失败，回退到 CPU: {e}")
            return self._cpu_yin_detection(audio_data, threshold)
        
        return 0.0, 0.0
    
    def _cuda_yin_detection(self, audio_data: np.ndarray, threshold: float) -> Tuple[float, float]:
        """CUDA加速的YIN算法"""
        cp = self.cp
        
        # 转换到GPU
        gpu_audio = cp.asarray(audio_data.astype(np.float32))
        
        # YIN算法参数
        N = len(gpu_audio)
        half_N = N // 2
        
        # 计算差分函数 (在GPU上)
        diff_function = cp.zeros(half_N, dtype=cp.float32)
        
        for tau in range(1, half_N):
            # 向量化计算差分
            diff = gpu_audio[:-tau] - gpu_audio[tau:]
            diff_function[tau] = cp.sum(diff * diff)
        
        # 累积均值标准化差分函数
        cmnd = cp.zeros_like(diff_function)
        cmnd[0] = 1.0
        
        cumsum = cp.cumsum(diff_function[1:])
        for tau in range(1, half_N):
            if diff_function[tau] == 0:
                cmnd[tau] = 0
            else:
                cmnd[tau] = diff_function[tau] * tau / cumsum[tau - 1]
        
        # 寻找第一个低于阈值的点
        min_period = int(self.sample_rate / 2000)  # 最高2000Hz
        max_period = int(self.sample_rate / 60)    # 最低60Hz
        
        search_range = cmnd[min_period:min(max_period, len(cmnd))]
        below_threshold = cp.where(search_range < threshold)[0]
        
        if len(below_threshold) > 0:
            period = below_threshold[0] + min_period
            
            # 抛物线插值
            if 1 <= period < len(cmnd) - 1:
                y1 = cmnd[period - 1]
                y2 = cmnd[period]
                y3 = cmnd[period + 1]
                
                # 计算插值偏移
                if (2 * y2 - y1 - y3) != 0:
                    x0 = (y3 - y1) / (2 * (2 * y2 - y1 - y3))
                    period = period + x0
            
            frequency = self.sample_rate / period
            confidence = 1.0 - cmnd[int(period)]
            
            # 转换回CPU
            return float(frequency), float(confidence)
        
        return 0.0, 0.0
    
    def _opencl_yin_detection(self, audio_data: np.ndarray, threshold: float) -> Tuple[float, float]:
        """OpenCL加速的YIN算法"""
        cl = self.cl
        
        # OpenCL核心代码
        kernel_code = """
        __kernel void yin_diff_function(__global const float* audio, 
                                      __global float* diff_func,
                                      const int N, const int half_N) {
            int tau = get_global_id(0) + 1;
            if (tau >= half_N) return;
            
            float sum = 0.0f;
            for (int j = 0; j < N - tau; j++) {
                float diff = audio[j] - audio[j + tau];
                sum += diff * diff;
            }
            diff_func[tau] = sum;
        }
        """
        
        try:
            # 编译程序
            program = cl.Program(self.context, kernel_code).build()
            
            # 准备数据
            audio_gpu = cl.Buffer(self.context, cl.mem_flags.READ_ONLY | cl.mem_flags.COPY_HOST_PTR, hostbuf=audio_data.astype(np.float32))
            N = len(audio_data)
            half_N = N // 2
            diff_func = np.zeros(half_N, dtype=np.float32)
            diff_func_gpu = cl.Buffer(self.context, cl.mem_flags.WRITE_ONLY, diff_func.nbytes)
            
            # 执行核心
            program.yin_diff_function(self.queue, (half_N-1,), None, audio_gpu, diff_func_gpu, np.int32(N), np.int32(half_N))
            
            # 读取结果
            cl.enqueue_copy(self.queue, diff_func, diff_func_gpu)
            
            # 后续处理在CPU上完成
            return self._complete_yin_on_cpu(diff_func, threshold)
            
        except Exception as e:
            print(f"OpenCL YIN 执行失败: {e}")
            return self._cpu_yin_detection(audio_data, threshold)
    
    def _complete_yin_on_cpu(self, diff_function: np.ndarray, threshold: float) -> Tuple[float, float]:
        """在CPU上完成YIN算法的剩余部分"""
        half_N = len(diff_function)
        
        # 累积均值标准化差分函数
        cmnd = np.zeros_like(diff_function)
        cmnd[0] = 1.0
        
        for tau in range(1, half_N):
            if diff_function[tau] == 0:
                cmnd[tau] = 0
            else:
                cumsum = np.sum(diff_function[1:tau+1])
                if cumsum > 0:
                    cmnd[tau] = diff_function[tau] / (cumsum / tau)
        
        # 寻找第一个低于阈值的点
        min_period = int(self.sample_rate / 2000)
        max_period = int(self.sample_rate / 60)
        
        for tau in range(min_period, min(max_period, len(cmnd))):
            if cmnd[tau] < threshold:
                frequency = self.sample_rate / tau
                confidence = 1.0 - cmnd[tau]
                return frequency, confidence
        
        return 0.0, 0.0
    
    def _cpu_yin_detection(self, audio_data: np.ndarray, threshold: float) -> Tuple[float, float]:
        """CPU版本的YIN算法（回退方案）"""
        N = len(audio_data)
        half_N = N // 2
        
        # 计算差分函数
        diff_function = np.zeros(half_N)
        for tau in range(1, half_N):
            for j in range(N - tau):
                diff_function[tau] += (audio_data[j] - audio_data[j + tau]) ** 2
        
        # 累积均值标准化差分函数
        cmnd = np.zeros_like(diff_function)
        cmnd[0] = 1.0
        
        for tau in range(1, half_N):
            if diff_function[tau] == 0:
                cmnd[tau] = 0
            else:
                cumsum = np.sum(diff_function[1:tau+1])
                if cumsum > 0:
                    cmnd[tau] = diff_function[tau] / (cumsum / tau)
        
        # 寻找第一个低于阈值的点
        min_period = int(self.sample_rate / 2000)
        max_period = int(self.sample_rate / 60)
        
        for tau in range(min_period, min(max_period, len(cmnd))):
            if cmnd[tau] < threshold:
                frequency = self.sample_rate / tau
                confidence = 1.0 - cmnd[tau]
                return frequency, confidence
        
        return 0.0, 0.0
    
    def accelerated_gradient_processing(self, frequencies: List[float], timestamps: List[float]) -> np.ndarray:
        """GPU加速的渐变处理"""
        if not self.gpu_available or len(frequencies) < 2:
            return self._cpu_gradient_processing(frequencies, timestamps)
        
        try:
            if self.gpu_type == "CUDA":
                return self._cuda_gradient_processing(frequencies, timestamps)
            else:
                return self._cpu_gradient_processing(frequencies, timestamps)
        except Exception as e:
            print(f"⚠️ GPU 渐变处理失败，回退到 CPU: {e}")
            return self._cpu_gradient_processing(frequencies, timestamps)
    
    def _cuda_gradient_processing(self, frequencies: List[float], timestamps: List[float]) -> np.ndarray:
        """CUDA加速的渐变处理"""
        cp = self.cp
        
        # 转换到GPU
        gpu_frequencies = cp.asarray(frequencies, dtype=cp.float32)
        gpu_timestamps = cp.asarray(timestamps, dtype=cp.float32)
        
        # 计算HSV颜色映射
        min_freq = cp.min(gpu_frequencies)
        max_freq = cp.max(gpu_frequencies)
        
        if max_freq > min_freq:
            # 归一化频率到 [0, 1]
            normalized_freq = (gpu_frequencies - min_freq) / (max_freq - min_freq)
            
            # HSV 到 RGB 的转换（在GPU上）
            hue = normalized_freq * 300  # 300度范围（蓝色到红色）
            saturation = cp.ones_like(hue)
            value = cp.ones_like(hue)
            
            # 转换为RGB
            colors = self._hsv_to_rgb_gpu(hue, saturation, value)
            
            # 转换回CPU
            return cp.asnumpy(colors)
        else:
            # 单一颜色
            colors = cp.ones((len(frequencies), 3), dtype=cp.float32)
            colors[:, 1] = 0.5  # 绿色
            return cp.asnumpy(colors)
    
    def _hsv_to_rgb_gpu(self, h, s, v):
        """GPU上的HSV到RGB转换"""
        cp = self.cp
        
        h = h / 60.0
        i = cp.floor(h).astype(cp.int32)
        f = h - i
        p = v * (1 - s)
        q = v * (1 - s * f)
        t = v * (1 - s * (1 - f))
        
        rgb = cp.zeros((len(h), 3), dtype=cp.float32)
        
        # 根据扇区分配RGB值
        mask0 = (i % 6) == 0
        mask1 = (i % 6) == 1
        mask2 = (i % 6) == 2
        mask3 = (i % 6) == 3
        mask4 = (i % 6) == 4
        mask5 = (i % 6) == 5
        
        rgb[mask0, 0] = v[mask0]
        rgb[mask0, 1] = t[mask0]
        rgb[mask0, 2] = p[mask0]
        
        rgb[mask1, 0] = q[mask1]
        rgb[mask1, 1] = v[mask1]
        rgb[mask1, 2] = p[mask1]
        
        rgb[mask2, 0] = p[mask2]
        rgb[mask2, 1] = v[mask2]
        rgb[mask2, 2] = t[mask2]
        
        rgb[mask3, 0] = p[mask3]
        rgb[mask3, 1] = q[mask3]
        rgb[mask3, 2] = v[mask3]
        
        rgb[mask4, 0] = t[mask4]
        rgb[mask4, 1] = p[mask4]
        rgb[mask4, 2] = v[mask4]
        
        rgb[mask5, 0] = v[mask5]
        rgb[mask5, 1] = p[mask5]
        rgb[mask5, 2] = q[mask5]
        
        return rgb
    
    def _cpu_gradient_processing(self, frequencies: List[float], timestamps: List[float]) -> np.ndarray:
        """CPU版本的渐变处理"""
        frequencies = np.array(frequencies)
        
        if len(frequencies) < 2:
            return np.array([[0.5, 1.0, 0.5]])  # 绿色
        
        # 归一化频率
        min_freq = np.min(frequencies)
        max_freq = np.max(frequencies)
        
        if max_freq > min_freq:
            normalized_freq = (frequencies - min_freq) / (max_freq - min_freq)
        else:
            normalized_freq = np.ones_like(frequencies) * 0.5
        
        # HSV颜色映射
        colors = np.zeros((len(frequencies), 3))
        
        for i, norm_freq in enumerate(normalized_freq):
            # 从蓝色(240°)到红色(0°)
            hue = (1 - norm_freq) * 240
            colors[i] = self._hsv_to_rgb(hue, 1.0, 1.0)
        
        return colors
    
    def _hsv_to_rgb(self, h: float, s: float, v: float) -> Tuple[float, float, float]:
        """HSV到RGB转换"""
        h = h / 60.0
        i = int(h)
        f = h - i
        p = v * (1 - s)
        q = v * (1 - s * f)
        t = v * (1 - s * (1 - f))
        
        i = i % 6
        if i == 0:
            return (v, t, p)
        elif i == 1:
            return (q, v, p)
        elif i == 2:
            return (p, v, t)
        elif i == 3:
            return (p, q, v)
        elif i == 4:
            return (t, p, v)
        else:
            return (v, p, q)
    
    def benchmark_performance(self, test_duration: float = 5.0) -> dict:
        """性能基准测试"""
        print(f"🧪 开始GPU性能基准测试 ({test_duration}秒)...")
        
        # 生成测试数据
        sample_rate = 44100
        test_data = np.random.randn(int(sample_rate * 0.1)).astype(np.float32)  # 0.1秒数据
        
        results = {
            'gpu_available': self.gpu_available,
            'gpu_type': self.gpu_type,
            'cpu_detections_per_sec': 0,
            'gpu_detections_per_sec': 0,
            'speedup_ratio': 0
        }
        
        # CPU基准测试
        start_time = time.time()
        cpu_count = 0
        while time.time() - start_time < test_duration / 2:
            self._cpu_yin_detection(test_data, 0.25)
            cpu_count += 1
        
        cpu_duration = time.time() - start_time
        results['cpu_detections_per_sec'] = cpu_count / cpu_duration
        
        # GPU基准测试（如果可用）
        if self.gpu_available:
            start_time = time.time()
            gpu_count = 0
            while time.time() - start_time < test_duration / 2:
                self.accelerated_yin_detection(test_data, 0.25)
                gpu_count += 1
            
            gpu_duration = time.time() - start_time
            results['gpu_detections_per_sec'] = gpu_count / gpu_duration
            
            if results['cpu_detections_per_sec'] > 0:
                results['speedup_ratio'] = results['gpu_detections_per_sec'] / results['cpu_detections_per_sec']
        
        print(f"📊 基准测试结果:")
        print(f"   CPU: {results['cpu_detections_per_sec']:.1f} 检测/秒")
        if self.gpu_available:
            print(f"   GPU: {results['gpu_detections_per_sec']:.1f} 检测/秒")
            print(f"   加速比: {results['speedup_ratio']:.2f}x")
        else:
            print(f"   GPU: 不可用")
        
        return results

if __name__ == "__main__":
    # 测试GPU加速处理器
    processor = GPUAcceleratedProcessor()
    
    # 运行基准测试
    benchmark_results = processor.benchmark_performance()
    
    # 测试音高检测
    print(f"\n🎵 测试音高检测:")
    test_signal = np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, 4410))  # 440Hz测试信号
    freq, conf = processor.accelerated_yin_detection(test_signal)
    print(f"   检测频率: {freq:.1f}Hz (目标: 440Hz)")
    print(f"   置信度: {conf:.3f}")
    
    # 测试渐变处理
    print(f"\n🎨 测试渐变处理:")
    test_frequencies = [200, 300, 400, 500, 600]
    test_timestamps = [0, 1, 2, 3, 4]
    colors = processor.accelerated_gradient_processing(test_frequencies, test_timestamps)
    print(f"   生成颜色数量: {len(colors)}")
    print(f"   颜色范围: R={colors[:, 0].min():.2f}-{colors[:, 0].max():.2f}")
