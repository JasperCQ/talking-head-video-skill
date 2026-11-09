"""Local media operations. No model inference or network access."""
import re
import shutil
import subprocess
import wave
from pathlib import Path

from .config import UserError


def ffmpeg():
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc:
        raise UserError("请安装 ffmpeg，或 pip install imageio-ffmpeg。") from exc


def run(arguments):
    try:
        return subprocess.run([ffmpeg(), "-hide_banner", "-nostdin", *map(str, arguments)],
                              check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except subprocess.CalledProcessError as exc:
        raise UserError("媒体处理失败：" + exc.stderr[-1200:]) from exc


def duration(path):
    path = Path(path)
    if path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as audio:
            return audio.getnframes() / audio.getframerate()
    result = subprocess.run([ffmpeg(), "-hide_banner", "-nostdin", "-i", str(path)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    match = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", result.stderr)
    if not match:
        raise UserError(f"无法读取媒体时长：{path.name}")
    h, m, s = map(float, match.groups())
    return h * 3600 + m * 60 + s


def video_info(path):
    result = subprocess.run([ffmpeg(), "-hide_banner", "-nostdin", "-i", str(path)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    match = re.search(r"Video:.*?\b(\d{2,5})x(\d{2,5})\b.*?([\d.]+) fps", result.stderr)
    if not match:
        raise UserError("无法读取视频尺寸和帧率。")
    return {"width": int(match[1]), "height": int(match[2]), "fps": float(match[3]),
            "duration_seconds": duration(path)}


def split_audio(path, texts, output_dir, boundaries=None):
    """Suggest cuts near pauses; human listening still verifies text alignment."""
    total = duration(path)
    if not texts or any(not isinstance(t, str) or not t.strip() for t in texts):
        raise UserError("请提供非空、完整语义的口播分段。")
    if boundaries is None:
        silences = run(["-i", path, "-af", "silencedetect=noise=-35dB:d=0.18", "-f", "null", "-"]).stderr
        pauses, start = [], None
        for kind, seconds in re.findall(r"silence_(start|end):\s*([\d.]+)", silences):
            if kind == "start":
                start = float(seconds)
            elif start is not None:
                pauses.append((start + float(seconds)) / 2)
                start = None
        boundaries, cumulative = [], 0
        for text in texts[:-1]:
            cumulative += len(text)
            target = total * cumulative / sum(map(len, texts))
            candidates = [p for p in pauses if (not boundaries or p > boundaries[-1]) and abs(p - target) <= 1.5]
            if not candidates:
                raise UserError("预估语义边界附近没有自然停顿。请试听并提供 boundaries_seconds，或在内容层重新分段；不会硬切句子。")
            boundaries.append(min(candidates, key=lambda p: abs(p - target)))
    if not isinstance(boundaries, list) or len(boundaries) != len(texts) - 1:
        raise UserError("切点数量应等于分段数量减一。")
    points = [0, *boundaries, total]
    if any(not isinstance(v, (int, float)) for v in points):
        raise UserError("音频切点必须为秒数。")
    if any(not 2 <= b - a <= 15 for a, b in zip(points, points[1:])):
        raise UserError("每段实测驱动音频必须在 2–15 秒之间；请重新设置分段。")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    segments = []
    for index, (text, start, end) in enumerate(zip(texts, points, points[1:])):
        output = output_dir / f"segment-{index + 1:02d}.flac"
        run(["-y", "-i", path, "-ss", f"{start:.6f}", "-t", f"{end - start:.6f}", "-c:a", "flac", output])
        segments.append({"index": index, "text": text, "start_seconds": start,
                         "duration_seconds": end - start, "audio": str(output.resolve()),
                         "mode": "fl-base" if index == 0 else "fl-i2v",
                         "prompt": "", "clip": None})
    return segments


def tail_frame(clip, target):
    run(["-y", "-sseof", "-0.1", "-i", clip, "-frames:v", "1", "-update", "1", target])
    return str(Path(target).resolve())


def assemble(segments, audio, output):
    # Normalize the concatenated picture stream and reuse the accepted master audio.
    clips = [segment["clip"] for segment in segments]
    inputs = [arg for clip in clips for arg in ("-i", str(clip))]
    streams = "".join(f"[v{i}]" for i in range(len(clips)))
    normalizations = ";".join(f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
                              f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24,"
                              f"tpad=stop_mode=clone:stop_duration=1,trim=duration={segment['duration_seconds']:.6f},"
                              f"setpts=PTS-STARTPTS[v{i}]" for i, segment in enumerate(segments))
    graph = normalizations + ";" + streams + f"concat=n={len(clips)}:v=1:a=0[outv]"
    run(["-y", *inputs, "-i", audio, "-filter_complex", graph, "-map", "[outv]",
         "-map", f"{len(clips)}:a:0", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "24",
         "-c:a", "aac", "-movflags", "+faststart", "-t", f"{duration(audio):.6f}", output])
    info = video_info(output)
    if abs(info["duration_seconds"] - duration(audio)) > 0.1:
        raise UserError("合成时长与批准主音频不一致，请核查成片。")
    return {"path": str(Path(output).resolve()), **info}
