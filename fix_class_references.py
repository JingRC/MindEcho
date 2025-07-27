#!/usr/bin/env python3
"""
快速修复MindEcho中的类名引用问题
"""

import os
import re
from pathlib import Path

def fix_integrated_recorder_references():
    """修复IntegratedRecorder相关的引用问题"""
    
    project_root = Path(__file__).parent
    
    # 需要检查的文件模式
    patterns_to_check = [
        "**/*.py"
    ]
    
    # 要替换的模式
    replacements = [
        (r'from\s+src\.audio_processing\.integrated_recorder\s+import\s+IntegratedAudioRecorder',
         'from src.audio_processing.integrated_recorder import IntegratedRecorderAnalyzer'),
        (r'IntegratedAudioRecorder\(',
         'IntegratedRecorderAnalyzer('),
        (r':\s*IntegratedAudioRecorder',
         ': IntegratedRecorderAnalyzer'),
    ]
    
    files_fixed = []
    
    # 扫描所有Python文件
    for pattern in patterns_to_check:
        for file_path in project_root.glob(pattern):
            if file_path.is_file() and file_path.suffix == '.py':
                try:
                    # 读取文件内容
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    original_content = content
                    
                    # 应用所有替换
                    for old_pattern, new_pattern in replacements:
                        content = re.sub(old_pattern, new_pattern, content)
                    
                    # 如果内容有变化，写回文件
                    if content != original_content:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                        
                        files_fixed.append(str(file_path))
                        print(f"✅ 修复文件: {file_path}")
                
                except Exception as e:
                    print(f"❌ 处理文件 {file_path} 时出错: {e}")
    
    return files_fixed

def check_import_consistency():
    """检查导入一致性"""
    
    project_root = Path(__file__).parent
    
    print("检查集成录音器导入一致性...")
    
    # 检查integrated_recorder.py文件
    integrated_recorder_file = project_root / "src" / "audio_processing" / "integrated_recorder.py"
    
    if integrated_recorder_file.exists():
        with open(integrated_recorder_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查类定义
        if 'class IntegratedRecorderAnalyzer:' in content:
            print("✅ IntegratedRecorderAnalyzer 类定义存在")
        else:
            print("❌ IntegratedRecorderAnalyzer 类定义缺失")
        
        # 检查别名
        if 'IntegratedAudioRecorder = IntegratedRecorderAnalyzer' in content:
            print("✅ 向下兼容别名存在")
        else:
            print("❌ 向下兼容别名缺失")
    else:
        print("❌ integrated_recorder.py 文件不存在")
    
    # 检查enhanced_main_window.py导入
    enhanced_main_file = project_root / "src" / "gui" / "enhanced_main_window.py"
    
    if enhanced_main_file.exists():
        with open(enhanced_main_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if 'from src.audio_processing.integrated_recorder import IntegratedRecorderAnalyzer' in content:
            print("✅ enhanced_main_window.py 导入正确")
        else:
            print("❌ enhanced_main_window.py 导入有问题")
    else:
        print("❌ enhanced_main_window.py 文件不存在")

def main():
    """主修复函数"""
    print("MindEcho 类名引用修复工具")
    print("=" * 50)
    
    # 修复引用
    print("\n1. 修复类名引用...")
    fixed_files = fix_integrated_recorder_references()
    
    if fixed_files:
        print(f"\n共修复了 {len(fixed_files)} 个文件:")
        for file in fixed_files:
            print(f"  - {file}")
    else:
        print("\n没有需要修复的文件")
    
    # 检查一致性
    print("\n2. 检查导入一致性...")
    check_import_consistency()
    
    print("\n修复完成！")

if __name__ == "__main__":
    main()
