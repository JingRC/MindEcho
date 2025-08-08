with open('src/gui/integrated_recording_interface.py', 'r', encoding='utf-8') as f:
    content = f.read()
    lines = content.split('\n')
    print(f'文件总行数: {len(lines)}')
    print(f'文件大小: {len(content)} 字符')
    
    # 检查关键类是否完整
    main_class_found = False
    init_ui_found = False
    
    for i, line in enumerate(lines):
        if 'class IntegratedRecordingInterface' in line:
            main_class_found = True
            print(f'找到主界面类: 第{i+1}行')
        if 'def init_ui' in line or 'def initUI' in line:
            init_ui_found = True
            print(f'找到界面初始化方法: 第{i+1}行')
    
    print(f'主界面类存在: {main_class_found}')
    print(f'界面初始化方法存在: {init_ui_found}')
    
    # 检查语法错误
    try:
        compile(content, 'integrated_recording_interface.py', 'exec')
        print('✅ 语法检查通过')
    except SyntaxError as e:
        print(f'❌ 语法错误: {e}')
        print(f'错误位置: 第{e.lineno}行')
        print(f'错误内容: {lines[e.lineno-1] if e.lineno <= len(lines) else "超出范围"}')
