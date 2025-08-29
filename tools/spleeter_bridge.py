import json
import sys
import argparse
import os
from pathlib import Path
import warnings

# 降噪：尽量屏蔽 TF/absl 噪声，确保 stdout 只输出 JSON
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')  # 0:all,1:info,2:warning,3:error
warnings.filterwarnings('ignore')
try:
    import logging
    logging.getLogger('tensorflow').setLevel(logging.ERROR)
    logging.getLogger('absl').setLevel(logging.ERROR)
    logging.getLogger('spleeter').setLevel(logging.ERROR)
except Exception:
    pass

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--vocals', required=True)
    p.add_argument('--acc', required=True)
    p.add_argument('--stems', type=int, choices=[2,4,5], default=2, help='分离声部数：2/4/5')
    # 可选：当选择 4/5 声部时，分别提供输出文件路径
    p.add_argument('--drums', type=str, default=None)
    p.add_argument('--bass', type=str, default=None)
    p.add_argument('--piano', type=str, default=None)
    p.add_argument('--other', type=str, default=None)
    p.add_argument('--sr', type=int, default=44100)
    p.add_argument('--model_dir', type=str, default=None, help='本地 Spleeter 预训练模型目录（可避免首次联网下载）')
    args = p.parse_args()

    # 1) 导入 Spleeter
    try:
        # 优先顺序：参数 -> 环境变量 -> 常见路径自动探测
        model_dir = args.model_dir or os.environ.get('SPLEETER_MODEL_PATH') or os.environ.get('SPLEETER_DATA_PATH')
        if not model_dir:
            # 自动探测常见目录（Windows/跨平台），找到包含 2stems 的上级目录
            cand = []
            home = Path.home()
            # 项目根目录下常见放置位置（如 D:\-MindEcho-main\pretrained_models）
            try:
                proj_root = Path(__file__).resolve().parent.parent
                cand += [
                    proj_root / 'pretrained_models',
                ]
            except Exception:
                pass
            # Windows 常见路径
            cand += [
                Path(os.environ.get('LOCALAPPDATA', '')) / 'spleeter' / 'models',
                Path(os.environ.get('APPDATA', '')) / 'spleeter' / 'models',
                Path('D:/spleeter_models'),
                Path('D:/AI/models/spleeter'),
                Path(os.environ.get('USERPROFILE', str(home))) / 'spleeter_models',
            ]
            # 跨平台缓存路径
            cand += [
                home / '.cache' / 'spleeter' / 'models',
                home / '.cache' / 'spleeter' / 'pretrained_models',
            ]
            resolved = None
            for base in cand:
                try:
                    if not base:
                        continue
                    # 允许 base 自身即为包含 2stems 的目录，或其下存在 models/pretrained_models/2stems
                    for probe in [
                        base,
                        base / 'models',
                        base / 'pretrained_models',
                    ]:
                        p2 = probe / '2stems'
                        if p2.exists():
                            # 设定为 probe（2stems 的上级目录）
                            resolved = str(probe)
                            break
                    if resolved:
                        break
                except Exception:
                    pass
            if resolved:
                model_dir = resolved
        if model_dir:
            os.environ['SPLEETER_DATA_PATH'] = model_dir
        import spleeter  # type: ignore
        from spleeter.separator import Separator  # type: ignore
        from spleeter.audio.adapter import AudioAdapter  # type: ignore
    except Exception as e:
        sys.stdout.write(json.dumps({'ok': False, 'error': f'Import Spleeter failed: {e}'}) + "\n")
        sys.stdout.flush()
        return 1

    # 2) 读取音频
    data = None
    sr = args.sr
    try:
        audio_loader = AudioAdapter.default()
        data, sr = audio_loader.load(args.input, sample_rate=args.sr)
    except Exception:
        pass
    if data is None:
        try:
            import librosa
            import numpy as _np
            y, sr = librosa.load(args.input, sr=args.sr, mono=False)
            if y.ndim == 1:
                data = y[:, None]
            else:
                # librosa 可能返回 (C, N)
                data = y.T if y.shape[0] < y.shape[1] else _np.ascontiguousarray(y.T)
        except Exception as e:
            sys.stdout.write(json.dumps({'ok': False, 'error': f'Load audio failed: {e}'}) + "\n")
            sys.stdout.flush()
            return 3
    # 输入概览
    try:
        import numpy as _np
        ch = int(data.shape[1]) if getattr(data, 'ndim', 1) == 2 else 1
        frames = int(data.shape[0]) if getattr(data, 'shape', None) is not None else 0
        duration = float(frames) / float(sr or args.sr or 44100)
    except Exception:
        ch = None; frames = None; duration = None

    # 3) 分离
    try:
        import time
        try:
            target_cfg = f'spleeter:{args.stems}stems'
            sep = Separator(target_cfg, MWF=True)
        except Exception:
            sep = Separator(f'spleeter:{args.stems}stems')
        t0 = time.time()
        out = sep.separate(data)
        t1 = time.time()
        voc = out.get('vocals')
        # 2 stems 模式：直接拿 accompaniment
        acc = out.get('accompaniment') if args.stems == 2 else None
        if voc is None:
            raise RuntimeError('Spleeter returned empty vocals')
        import numpy as _np
        import soundfile as sf
        if voc.ndim == 1:
            voc = voc[:, None]
        written = {}
        sf.write(args.vocals, _np.asarray(voc, dtype=_np.float32), sr)
        written['vocals'] = args.vocals
        # multi-stems 输出（若提供路径）
        def _writestem(key, path):
            try:
                s = out.get(key)
                if s is None or path is None:
                    return
                if s.ndim == 1:
                    s = s[:, None]
                sf.write(path, _np.asarray(s, dtype=_np.float32), sr)
                written[key] = path
            except Exception:
                pass
        if args.stems in (4,5):
            _writestem('drums', args.drums)
            _writestem('bass', args.bass)
            _writestem('other', args.other)
            if args.stems == 5:
                _writestem('piano', args.piano)
            # 若需要伴奏且未由 2stems 直接提供，则将非人声声部求和作为伴奏
            if args.acc:
                try:
                    parts = []
                    for k in ('drums','bass','other'):
                        if out.get(k) is not None:
                            parts.append(out[k])
                    if args.stems == 5 and out.get('piano') is not None:
                        parts.append(out['piano'])
                    if parts:
                        acc = sum(_np.asarray(p, dtype=_np.float32) for p in parts)
                        if acc.ndim == 1:
                            acc = acc[:, None]
                except Exception:
                    acc = None
        # 写伴奏
        if acc is not None:
            if acc.ndim == 1:
                acc = acc[:, None]
            sf.write(args.acc, _np.asarray(acc, dtype=_np.float32), sr)
            written['accompaniment'] = args.acc
        # 附带版本与 Python 解释器信息，便于上层诊断
        ver = None
        try:
            import spleeter as _sp  # type: ignore
            ver = getattr(_sp, '__version__', None)
        except Exception:
            ver = None
        if ver is None:
            # 尝试用 importlib.metadata 获取版本
            try:
                import importlib.metadata as _imd  # py3.8+
                ver = _imd.version('spleeter')
            except Exception:
                try:
                    import pkg_resources as _pkr
                    ver = _pkr.get_distribution('spleeter').version
                except Exception:
                    ver = None
        # 探测模型目录（尽力而为）
        model_info = {}
        try:
            from pathlib import Path as _Path
            cand_dirs = []
            if model_dir:
                cand_dirs.append(_Path(model_dir))
            home = _Path.home()
            cand_dirs += [
                home / '.cache' / 'spleeter',
                home / 'AppData' / 'Roaming' / 'spleeter',
            ]
            found = None
            for d in cand_dirs:
                for sub in ['pretrained_models', 'models', '']:
                    p = d / sub / '2stems'
                    if p.exists():
                        found = str(p)
                        break
                if found:
                    break
            model_info = {'resolved': found, 'env': model_dir}
        except Exception:
            model_info = {'resolved': None, 'env': model_dir}
        info = {
            'ok': True,
            'sr': sr,
            'spleeter_version': ver,
            'python': sys.version.split("\n")[0],
            'channels': ch,
            'frames': frames,
            'duration_sec': duration,
            'infer_sec': (t1 - t0),
            'model': model_info,
            'stems': args.stems,
            'written': written
        }
        sys.stdout.write(json.dumps(info) + "\n")
        sys.stdout.flush()
        return 0
    except Exception as e:
        sys.stdout.write(json.dumps({'ok': False, 'error': f'Separate failed: {e}'}) + "\n")
        sys.stdout.flush()
        return 2

if __name__ == '__main__':
    sys.exit(main())
