"""전역 자동 오프셋 추정 (보컬대역 onset, 보수적 게이팅).

배경 분석:
- 전체 mix 의 onset 상관은 신호가 약해(점수 곡선이 평평) 노이즈에서 큰 값을 골라
  ±1초 같은 엉뚱한 오프셋을 내놓는 문제가 있었다.
- 강제정렬(stable-ts)은 이미 보컬에 잘 맞춰져 있어 '보정할 전역 오프셋'은 대개 0에 가깝다.

따라서 이 모듈은 보컬대역(약 300~3400Hz) onset 곡선을 만들고, 각 가사 줄 시작 근처의
실제 보컬 onset과의 차이를 모은다. '많은 줄이 일관되게' 같은 방향으로 어긋날 때만
그 중앙값을 오프셋으로 채택하고(작은 범위로 클램프), 근거가 약하면 0(강제정렬 신뢰)을 반환한다.
torch만 사용.
"""
import subprocess

import numpy as np

SR = 16000
HOP = 256
N_FFT = 1024
VOCAL_LO_HZ = 300
VOCAL_HI_HZ = 3400
WINDOW = 0.35       # 줄 시작 주변에서 보컬 onset 을 찾는 범위(초)
MAX_OFFSET = 0.5    # 자동 오프셋 클램프(보정은 작게)
MIN_FRACTION = 0.5  # 이 비율 이상의 줄에서 또렷한 onset 이 잡혀야 신뢰
MAX_MAD = 0.22      # 줄별 차이의 산포(MAD)가 이보다 크면 일관성 없음 -> 0


def _load_audio_16k(path) -> np.ndarray:
    cmd = [
        "ffmpeg", "-i", str(path),
        "-f", "s16le", "-ac", "1", "-ar", str(SR),
        "-loglevel", "quiet", "pipe:1",
    ]
    out = subprocess.run(cmd, capture_output=True).stdout
    if not out:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(out, np.int16).astype(np.float32) / 32768.0


def _vocal_onset_envelope(audio: np.ndarray):
    """보컬대역 로그에너지의 양의 변화량(onset novelty)과 프레임 시간축."""
    import torch

    y = torch.from_numpy(audio)
    spec = torch.stft(
        y, n_fft=N_FFT, hop_length=HOP,
        window=torch.hann_window(N_FFT), return_complex=True,
    ).abs().numpy()

    freqs = np.arange(spec.shape[0]) * SR / N_FFT
    band = (freqs >= VOCAL_LO_HZ) & (freqs <= VOCAL_HI_HZ)
    band_energy = spec[band, :].sum(0)
    log_e = np.log(band_energy + 1e-6)
    nov = np.diff(log_e)
    nov = np.concatenate([[0.0], nov])
    nov = np.clip(nov, 0, None)
    # 3프레임 이동평균
    if len(nov) >= 3:
        kernel = np.ones(3) / 3
        nov = np.convolve(nov, kernel, mode="same")
    times = np.arange(len(nov)) * HOP / SR
    return nov, times


def estimate_offset(audio_path, line_starts: list[float]) -> float | None:
    """전역 자동 오프셋(초). 일관된 근거가 없으면 0.0(강제정렬 신뢰), 실패 시 None."""
    if not line_starts:
        return None
    try:
        audio = _load_audio_16k(audio_path)
        if audio.size < SR:
            return None
        nov, times = _vocal_onset_envelope(audio)
        if len(nov) < 10:
            return None

        # 90 분위수로 정규화 -> 일반적 onset 의 세기가 ~1 이 되도록(한두 개 큰 스파이크 영향 제거)
        p90 = float(np.percentile(nov, 90))
        if p90 <= 0:
            return 0.0
        novn = nov / p90

        diffs = []
        for t in line_starts:
            lo = int(np.searchsorted(times, t - WINDOW))
            hi = int(np.searchsorted(times, t + WINDOW))
            if hi <= lo:
                continue
            k = lo + int(np.argmax(novn[lo:hi]))
            if novn[k] >= 1.0:  # 90분위 이상 = 실제 onset 으로 인정
                diffs.append(times[k] - t)

        n = len(line_starts)
        if len(diffs) < max(8, MIN_FRACTION * n):
            return 0.0  # 근거 부족 -> 강제정렬 신뢰

        diffs = np.array(diffs)
        med = float(np.median(diffs))
        mad = float(np.median(np.abs(diffs - med)))
        if mad > MAX_MAD:
            return 0.0  # 줄별로 제각각 -> 일관된 전역 오프셋 아님

        return round(float(np.clip(med, -MAX_OFFSET, MAX_OFFSET)), 2)
    except Exception:
        return None
