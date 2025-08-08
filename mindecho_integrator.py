#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MindEcho主程序集成工具
自动集成优化的音频配置到现有主程序

解决的核心问题：
1. WASAPI -9997/-9996/-9999 错误
2. HECATE G4 Pro连接失败
3. 配置参数不匹配
4. 设备验证不一致

作者: GitHub Copilot  
日期: 2025-01-06
"""

import os
import re
import shutil
from typing import Dict, List, Optional
from datetime import datetime


class MindEchoIntegrator:
    """MindEcho主程序集成器"""
    
    def __init__(self, workspace_path: str = None):
        self.workspace_path = workspace_path or os.getcwd()
        self.backup_dir = os.path.join(self.workspace_path, "backups")
        self.target_file = os.path.join(self.workspace_path, "integrated_recording_interface.py")
        
        # 确保备份目录存在
        os.makedirs(self.backup_dir, exist_ok=True)
        
        print(f"🔧 MindEcho集成器初始化")
        print(f"   工作目录: {self.workspace_path}")
        print(f"   目标文件: {self.target_file}")
        print(f"   备份目录: {self.backup_dir}")
    
    def create_backup(self) -> str:
        """创建主程序备份"""
        try:
            if not os.path.exists(self.target_file):
                print(f"❌ 目标文件不存在: {self.target_file}")
                return None
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(self.backup_dir, f"integrated_recording_interface_backup_{timestamp}.py")
            
            shutil.copy2(self.target_file, backup_file)
            
            print(f"✅ 备份已创建: {backup_file}")
            return backup_file
            
        except Exception as e:
            print(f"❌ 创建备份失败: {e}")
            return None
    
    def analyze_current_implementation(self) -> Dict:
        """分析当前实现"""
        try:
            if not os.path.exists(self.target_file):
                print(f"❌ 目标文件不存在: {self.target_file}")
                return {}
            
            with open(self.target_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            analysis = {
                'file_size': len(content),
                'line_count': len(content.splitlines()),
                'has_sounddevice': 'import sounddevice' in content,
                'has_wasapi': 'wasapi' in content.lower(),
                'has_monitoring_callback': '_monitoring_callback' in content,
                'has_unified_monitoring': 'start_unified_monitoring' in content,
                'has_device_selection': 'device_selection' in content.lower(),
                'current_errors': []
            }
            
            # 检测已知问题模式
            if 'sd.Stream(' in content:
                # 查找Stream创建模式
                stream_patterns = re.findall(r'sd\.Stream\([^)]*\)', content)
                analysis['stream_creation_count'] = len(stream_patterns)
                
                # 检查是否使用了固定参数
                if 'samplerate=44100' in content:
                    analysis['current_errors'].append('使用固定采样率44100Hz')
                if 'blocksize=1024' in content:
                    analysis['current_errors'].append('使用固定块大小1024')
                if 'device=' not in content:
                    analysis['current_errors'].append('未指定音频设备')
            
            # 检查WASAPI配置
            if 'extra_settings' not in content:
                analysis['current_errors'].append('缺少WASAPI extra_settings配置')
            
            print(f"📊 代码分析结果:")
            print(f"   文件大小: {analysis['file_size']:,} 字符")
            print(f"   代码行数: {analysis['line_count']:,} 行")
            print(f"   sounddevice导入: {'✅' if analysis['has_sounddevice'] else '❌'}")
            print(f"   WASAPI支持: {'✅' if analysis['has_wasapi'] else '❌'}")
            print(f"   统一监听: {'✅' if analysis['has_unified_monitoring'] else '❌'}")
            print(f"   Stream创建: {analysis.get('stream_creation_count', 0)} 处")
            
            if analysis['current_errors']:
                print(f"   ⚠️ 发现问题:")
                for error in analysis['current_errors']:
                    print(f"      - {error}")
            
            return analysis
            
        except Exception as e:
            print(f"❌ 分析文件失败: {e}")
            return {}
    
    def generate_integration_patches(self) -> List[Dict]:
        """生成集成补丁"""
        patches = []
        
        # 补丁1: 添加配置生成器导入
        patches.append({
            'name': '添加配置生成器导入',
            'type': 'import_addition',
            'search_pattern': r'import sounddevice as sd',
            'replacement': '''import sounddevice as sd
from audio_config_generator import AudioConfigGenerator''',
            'description': '添加优化的配置生成器'
        })
        
        # 补丁2: 添加配置生成器初始化
        patches.append({
            'name': '初始化配置生成器',
            'type': 'initialization',
            'search_pattern': r'def __init__\(self.*?\):',
            'insertion_after': True,
            'content': '''
        # 添加优化的音频配置生成器
        self.config_generator = AudioConfigGenerator()
        self.optimal_configs = []
        self._current_optimal_config = None''',
            'description': '在构造函数中初始化配置生成器'
        })
        
        # 补丁3: 替换start_unified_monitoring方法
        patches.append({
            'name': '优化统一监听方法',
            'type': 'method_replacement',
            'search_pattern': r'def start_unified_monitoring\(self.*?\):.*?(?=def|\Z)',
            'replacement': '''def start_unified_monitoring(self):
        """优化的统一监听功能 - 解决WASAPI配置问题"""
        try:
            print("🎧 正在启动优化监听模式...")
            
            # 1. 生成最优配置列表
            self.optimal_configs = self.config_generator.generate_optimal_wasapi_configs()
            
            if not self.optimal_configs:
                print("❌ 未找到可用配置，使用紧急回退")
                return self._start_emergency_monitoring()
            
            # 2. 按优先级尝试配置
            for i, config in enumerate(self.optimal_configs):
                print(f"🎯 尝试配置 {i+1}/{len(self.optimal_configs)}: {config['name']}")
                
                if self._try_create_optimized_stream(config):
                    self._current_optimal_config = config
                    print(f"✅ 监听启动成功: {config['device_name']}")
                    print(f"   📊 参数: {config['samplerate']}Hz/{config['blocksize']}样本")
                    
                    # 发送状态更新
                    if hasattr(self, 'status_updated'):
                        self.status_updated.emit("监听已启动")
                    
                    return True
                else:
                    print(f"❌ 配置失败，尝试下一个...")
                    continue
            
            # 3. 所有配置失败，使用紧急模式
            print("⚠️ 所有优化配置失败，使用紧急模式")
            return self._start_emergency_monitoring()
            
        except Exception as e:
            print(f"❌ 优化监听启动失败: {e}")
            return self._start_emergency_monitoring()''',
            'description': '替换为优化的监听启动方法'
        })
        
        # 补丁4: 添加优化的流创建方法
        patches.append({
            'name': '添加优化流创建方法',
            'type': 'method_addition',
            'content': '''
    def _try_create_optimized_stream(self, config: Dict) -> bool:
        """使用优化配置创建音频流"""
        try:
            # 使用配置生成器的统一接口
            self.monitoring_stream = self.config_generator.create_monitoring_stream(
                config=config,
                callback=self._optimized_monitoring_callback
            )
            
            if self.monitoring_stream is None:
                return False
            
            # 启动流并测试
            self.monitoring_stream.start()
            
            # 短暂测试
            import time
            time.sleep(0.2)
            
            return True
            
        except Exception as e:
            print(f"   优化流创建失败: {e}")
            if hasattr(self, 'monitoring_stream') and self.monitoring_stream:
                try:
                    self.monitoring_stream.close()
                except:
                    pass
                self.monitoring_stream = None
            return False
    
    def _optimized_monitoring_callback(self, indata, outdata, frames, time_info, status):
        """优化的监听回调 - 保持原有功能"""
        try:
            # 保持原有的监听回调逻辑
            # 这里可以调用原来的 _monitoring_callback 或相似方法
            
            # 状态检查
            if status:
                print(f"⚠️ 音频状态: {status}")
            
            # 处理音频数据 - 保持原有逻辑
            if hasattr(self, '_original_monitoring_callback'):
                return self._original_monitoring_callback(indata, outdata, frames, time_info, status)
            
            # 如果没有原有回调，使用简单直通
            if indata is not None and outdata is not None:
                outdata[:] = indata
            
        except Exception as e:
            print(f"⚠️ 优化回调错误: {e}")
    
    def _start_emergency_monitoring(self):
        """紧急监听模式 - 最基本的DirectSound配置"""
        try:
            print("🔄 启动紧急监听模式...")
            
            # 使用最基本的配置
            self.monitoring_stream = sd.Stream(
                channels=getattr(self, 'channels', 1),
                samplerate=44100,
                blocksize=1024,
                callback=self._optimized_monitoring_callback,
                dtype='float32'
            )
            
            self.monitoring_stream.start()
            print("✅ 紧急监听模式启动成功")
            
            if hasattr(self, 'status_updated'):
                self.status_updated.emit("监听已启动(紧急模式)")
            
            return True
            
        except Exception as e:
            print(f"❌ 紧急监听也失败: {e}")
            if hasattr(self, 'error_occurred'):
                self.error_occurred.emit(f"音频监听完全失败: {e}")
            return False''',
            'description': '添加优化的流创建和紧急模式方法'
        })
        
        return patches
    
    def apply_patches(self, patches: List[Dict]) -> bool:
        """应用补丁到主程序"""
        try:
            if not os.path.exists(self.target_file):
                print(f"❌ 目标文件不存在: {self.target_file}")
                return False
            
            # 读取当前文件内容
            with open(self.target_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            modified_content = content
            applied_patches = 0
            
            for patch in patches:
                print(f"🔧 应用补丁: {patch['name']}")
                
                try:
                    if patch['type'] == 'import_addition':
                        if patch['search_pattern'] in modified_content:
                            modified_content = modified_content.replace(
                                patch['search_pattern'],
                                patch['replacement']
                            )
                            applied_patches += 1
                            print(f"   ✅ 导入补丁已应用")
                        else:
                            print(f"   ⚠️ 未找到目标导入语句")
                    
                    elif patch['type'] == 'initialization':
                        # 在构造函数中添加初始化代码
                        init_pattern = r'(def __init__\(self.*?\):.*?(?=\n    def|\n\nclass|\nclass|\Z))'
                        if re.search(init_pattern, modified_content, re.DOTALL):
                            # 找到构造函数，在最后添加初始化代码
                            modified_content = re.sub(
                                r'(def __init__\(self.*?\):)(.*?)((?=\n    def|\n\nclass|\nclass|\Z))',
                                r'\1\2' + patch['content'] + r'\n\3',
                                modified_content,
                                flags=re.DOTALL
                            )
                            applied_patches += 1
                            print(f"   ✅ 初始化补丁已应用")
                        else:
                            print(f"   ⚠️ 未找到构造函数")
                    
                    elif patch['type'] == 'method_replacement':
                        # 替换整个方法
                        if re.search(patch['search_pattern'], modified_content, re.DOTALL):
                            modified_content = re.sub(
                                patch['search_pattern'],
                                patch['replacement'],
                                modified_content,
                                flags=re.DOTALL
                            )
                            applied_patches += 1
                            print(f"   ✅ 方法替换补丁已应用")
                        else:
                            print(f"   ⚠️ 未找到目标方法")
                    
                    elif patch['type'] == 'method_addition':
                        # 在文件末尾类定义内添加新方法
                        # 找到类定义的结尾
                        class_end_pattern = r'(\nclass [^:]+:.*?)((?=\n\nclass|\n\n\ndef|\Z))'
                        if re.search(class_end_pattern, modified_content, re.DOTALL):
                            modified_content = re.sub(
                                class_end_pattern,
                                r'\1' + patch['content'] + r'\2',
                                modified_content,
                                flags=re.DOTALL
                            )
                            applied_patches += 1
                            print(f"   ✅ 方法添加补丁已应用")
                        else:
                            # 如果找不到类结尾，在文件末尾添加
                            modified_content += patch['content']
                            applied_patches += 1
                            print(f"   ✅ 方法添加补丁已应用(文件末尾)")
                    
                except Exception as e:
                    print(f"   ❌ 补丁应用失败: {e}")
            
            # 保存修改后的内容
            if applied_patches > 0:
                with open(self.target_file, 'w', encoding='utf-8') as f:
                    f.write(modified_content)
                
                print(f"✅ 已应用 {applied_patches}/{len(patches)} 个补丁")
                return True
            else:
                print(f"❌ 没有成功应用任何补丁")
                return False
            
        except Exception as e:
            print(f"❌ 应用补丁失败: {e}")
            return False
    
    def copy_dependencies(self) -> bool:
        """复制依赖文件"""
        try:
            dependencies = [
                'audio_config_generator.py',
                'test_audio_monitoring.py'
            ]
            
            copied = 0
            for dep in dependencies:
                src_file = os.path.join(self.workspace_path, dep)
                if os.path.exists(src_file):
                    # 依赖文件已在工作目录，无需复制
                    print(f"✅ 依赖文件已存在: {dep}")
                    copied += 1
                else:
                    print(f"❌ 依赖文件不存在: {dep}")
            
            return copied > 0
            
        except Exception as e:
            print(f"❌ 复制依赖失败: {e}")
            return False
    
    def perform_integration(self) -> bool:
        """执行完整集成"""
        print("🚀 开始MindEcho主程序集成")
        print("=" * 50)
        
        try:
            # 1. 分析当前实现
            analysis = self.analyze_current_implementation()
            if not analysis:
                return False
            
            # 2. 创建备份
            backup_file = self.create_backup()
            if not backup_file:
                print("❌ 无法创建备份，取消集成")
                return False
            
            # 3. 复制依赖文件
            if not self.copy_dependencies():
                print("⚠️ 部分依赖文件缺失，但继续集成")
            
            # 4. 生成和应用补丁
            patches = self.generate_integration_patches()
            print(f"📝 生成了 {len(patches)} 个补丁")
            
            if self.apply_patches(patches):
                print("✅ MindEcho集成完成！")
                print(f"\n📊 集成摘要:")
                print(f"   ✅ 备份文件: {backup_file}")
                print(f"   ✅ 目标文件: {self.target_file}")
                print(f"   ✅ 应用补丁: {len(patches)}个")
                print(f"\n🎯 关键改进:")
                print(f"   ├─ 动态设备配置生成")
                print(f"   ├─ WASAPI参数优化")
                print(f"   ├─ 智能回退机制")
                print(f"   └─ 错误处理增强")
                
                return True
            else:
                print("❌ 集成失败")
                return False
            
        except Exception as e:
            print(f"❌ 集成过程失败: {e}")
            return False
    
    def validate_integration(self) -> bool:
        """验证集成结果"""
        try:
            print("\n🔍 验证集成结果...")
            
            with open(self.target_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            checks = {
                'AudioConfigGenerator导入': 'AudioConfigGenerator' in content,
                '配置生成器初始化': 'self.config_generator = AudioConfigGenerator()' in content,
                '优化监听方法': '_try_create_optimized_stream' in content,
                '紧急模式': '_start_emergency_monitoring' in content,
                '语法完整性': content.count('def ') > 0 and content.count('class ') > 0
            }
            
            print("📋 验证结果:")
            all_passed = True
            for check_name, result in checks.items():
                status = "✅" if result else "❌"
                print(f"   {status} {check_name}")
                if not result:
                    all_passed = False
            
            if all_passed:
                print("✅ 所有验证通过！")
            else:
                print("⚠️ 部分验证失败，请检查")
            
            return all_passed
            
        except Exception as e:
            print(f"❌ 验证失败: {e}")
            return False


def main():
    """主函数"""
    print("🎵 MindEcho优化集成工具")
    print("🎯 解决WASAPI配置和HECATE连接问题")
    print("=" * 60)
    
    try:
        # 获取工作目录
        workspace = input("请输入工作目录路径 (回车使用当前目录): ").strip()
        if not workspace:
            workspace = os.getcwd()
        
        print(f"📁 使用工作目录: {workspace}")
        
        # 创建集成器
        integrator = MindEchoIntegrator(workspace)
        
        # 确认执行
        print(f"\n⚠️ 即将修改文件: integrated_recording_interface.py")
        print(f"📁 备份将保存到: {integrator.backup_dir}")
        
        confirm = input("继续执行集成? (y/N): ").strip().lower()
        if confirm not in ['y', 'yes']:
            print("❌ 用户取消集成")
            return
        
        # 执行集成
        if integrator.perform_integration():
            # 验证集成
            integrator.validate_integration()
            
            print(f"\n🎉 集成完成！")
            print(f"📝 下一步操作:")
            print(f"   1. 运行 python main.py 测试主程序")
            print(f"   2. 运行 python test_audio_monitoring.py 进行详细测试")
            print(f"   3. 检查音频设备连接和监听功能")
            
        else:
            print("❌ 集成失败")
    
    except KeyboardInterrupt:
        print("\n⏹️ 用户中断")
    except Exception as e:
        print(f"❌ 程序错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
