# -*- coding: utf-8 -*-
r"""
여러 화 일괄 변환: 한국어(위) + 일본어(아래) 병기 ASS 생성 (겹침 없음, 안전 간격 0ms)
- 입력: ASS / SRT / SMI (언어별 한 트랙)
- 출력: <영상명>.ass
- 단일 트랙(한 시점에 Dialogue 1개), 하단 중앙, MarginV=0
- 줄별 폰트/크기 강제: KR=Malgun Gothic, JP=Meiryo
- 일본어/한국어 블록 앞에 ASS 코멘트 태그 추가:
  - 일본어: {!JP}
  - 한국어: {!KR}
  → 화면에 보이지 않으며, mpv Lua에서 sub-text/ass로 파싱용으로만 사용.
"""

import os
import re
import unicodedata as ud
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox

KR_FONT = "Malgun Gothic"
JP_FONT = "Meiryo"

# ------------------ 유틸 ------------------
def natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]

def read_text_auto(path: str) -> str:
    # 흔한 인코딩들을 순서대로 시도
    encodings = (
        "utf-8-sig",
        "utf-8",
        "cp949",
        "euc-kr",
        "shift_jis",
        "utf-16-le",  # 윈도우에서 1200 유니코드로 나오는 UTF-16 LE
        "utf-16-be",
        "utf-16",     # BOM 있는 UTF-16
    )
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, errors="strict") as f:
                return f.read()
        except Exception:
            continue

    # 전부 실패했을 때만 마지막으로 강제 읽기
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

# ------------------ 시간 변환 ------------------
def ass_ts_to_ms(ts: str):
    m = re.match(r"(\d+):(\d{2}):(\d{2})\.(\d{2})", ts)
    if not m:
        return None
    h, mi, s, cs = map(int, m.groups())
    return ((h * 60 + mi) * 60 + s) * 1000 + cs * 10

def ms_to_ass(ms: int):
    cs = (ms // 10) % 100
    s = (ms // 1000) % 60
    m = (ms // 60000) % 60
    h = ms // 3600000
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"

# ------------------ 파서들 ------------------
def parse_ass_events(text: str):
    events = []
    for line in text.splitlines():
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        s = ass_ts_to_ms(parts[1].strip())
        e = ass_ts_to_ms(parts[2].strip())
        if s is None or e is None:
            continue
        payload = parts[9]
        # 오버라이드 태그({\...}) + 코멘트 블록({!...}) 제거
        payload = re.sub(r"\{[\\!].*?\}", "", payload)
        t = payload.replace("\\N", "\n").replace("\\n", "\n").strip()
        if t:
            t = ud.normalize("NFC", t)
            events.append((s, e, t))
    events.sort(key=lambda x: x[0])
    return _normalize_ends(events)

def parse_srt_events(text: str):
    events = []
    blocks = re.split(r"\n\s*\n", text.strip())
    for b in blocks:
        m = re.search(
            r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*"
            r"(\d{2}):(\d{2}):(\d{2}),(\d{3})",
            b,
        )
        if not m:
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, m.groups())
        s = ((h1 * 60 + m1) * 60 + s1) * 1000 + ms1
        e = ((h2 * 60 + m2) * 60 + s2) * 1000 + ms2
        lines = [
            ln
            for ln in b.splitlines()
            if "-->" not in ln and not ln.strip().isdigit()
        ]
        t = "\n".join([ln.strip() for ln in lines if ln.strip()])
        if t:
            t = ud.normalize("NFC", t)
            events.append((s, e, t))
    events.sort(key=lambda x: x[0])
    return _normalize_ends(events)

def parse_smi_events(text: str):
    data = text.replace("\r\n", "\n").replace("\r", "\n")
    events = []

    # <SYNC Start=...> 블록 단위로 자르기
    for m in re.finditer(
        r"(?is)<SYNC\s+Start\s*=\s*(\d+)[^>]*>(.*?)(?=<SYNC\s+Start\s*=|\Z)",
        data,
    ):
        start = int(m.group(1))
        body = m.group(2)

        lines = []
        had_p = False

        # 각 SYNC 안의 <P ...> 블록들을 순서대로 추출
        for pm in re.finditer(r"(?is)(<P[^>]*>)(.*?)(?=<P[^>]*>|\Z)", body):
            had_p = True
            tag = pm.group(1)
            rp = pm.group(2)

            tag_lower = tag.lower()
            # class 지정이 있으면 KRCC만 사용 (다국어 SMI 대비)
            if "class=" in tag_lower and "krcc" not in tag_lower:
                continue

            # <br> → 줄바꿈
            rp = re.sub(r"(?i)<br\s*/?>", "\n", rp)
            # 나머지 태그 제거
            txt = re.sub(r"<[^>]+>", "", rp).replace("\\N", "\n")

            for ln in txt.splitlines():
                ln = ln.strip()
                # 완전 공백이나 &nbsp;는 무시
                if not ln or ln == "&nbsp;":
                    continue
                lines.append(ln)

        # <P> 태그 자체가 없는 특이한 SMI에 대한 예비 처리
        if not had_p:
            tmp = re.sub(r"(?i)<br\s*/?>", "\n", body)
            tmp = re.sub(r"<[^>]+>", "", tmp).replace("\\N", "\n")
            for ln in tmp.splitlines():
                ln = ln.strip()
                if not ln or ln == "&nbsp;":
                    continue
                lines.append(ln)

        if lines:
            t = ud.normalize("NFC", "\n".join(lines))
            # 종료 시간은 임시 2초, 나중에 _normalize_ends에서 정리
            events.append((start, start + 2000, t))

    events.sort(key=lambda x: x[0])
    return _normalize_ends(events)

def _normalize_ends(events):
    if not events:
        return events
    ev = []
    for i, (s, e, t) in enumerate(events):
        if e <= s:
            e = s + 1500
        if i < len(events) - 1 and e > events[i + 1][0]:
            e = max(s + 200, events[i + 1][0] - 1)
        ev.append((s, e, t))
    return ev

def load_sub_auto(path: str):
    ext = os.path.splitext(path)[1].lower()
    text = read_text_auto(path)
    if ext in (".ass", ".ssa"):
        return parse_ass_events(text)
    if ext == ".srt":
        return parse_srt_events(text)
    if ext in (".smi", ".sami", ".smi.txt"):
        return parse_smi_events(text)
    # 확장자로 못 알아낸 경우 포맷별로 시도
    for fn in (parse_srt_events, parse_ass_events, parse_smi_events):
        try:
            ev = fn(text)
            if ev:
                return ev
        except Exception:
            pass
    return []

# ------------------ 단일 트랙 세그먼트 구성 ------------------
def build_segments_singletrack(k_list, j_list):
    """KR/JP 컷포인트 합쳐 [a,b)마다 최신 시작 텍스트 선택, 동일 페이로드는 연장 병합."""
    points = set()
    for s, e, _ in k_list + j_list:
        points.add(s)
        points.add(e)
    cuts = sorted(points)

    def active_lines(ev_list, a, b):
        cands = [(s, e, t) for (s, e, t) in ev_list if s < b and e > a]
        if not cands:
            return None
        latest = max(s for s, _, _ in cands)
        lines = []
        for s, e, t in cands:
            if s == latest:
                for ln in t.splitlines():
                    ln = ln.strip()
                    if ln and (not lines or lines[-1] != ln):
                        lines.append(ln)
        return lines or None

    segs = []
    for i in range(len(cuts) - 1):
        a, b = cuts[i], cuts[i + 1]
        if b - a < 1:
            continue
        ko = active_lines(k_list, a, b)
        jp = active_lines(j_list, a, b)
        segs.append((a, b, ko, jp))
    return segs

def fuse_payloads_no_gap(segs, fs_kr, fs_jp):
    """
    동일 payload 연속 병합 + 겹침 금지(다음 시작 − 1ms), 최소 표시폭 보장.
    일본어/한국어 구간 앞에 코멘트 태그:
      - 일본어 블록 시작: {!JP}
      - 한국어 블록 시작: {!KR}
    """

    def payload(ko, jp):
        # 공통 헤더: 하단 중앙, 테두리/그림자 최소
        head = r"{\r\an2\q2\bord2\shad0}"
        parts = [head]

        # 일본어 줄 (아래쪽)
        if jp:
            # 일본어 블록 마커 (ASS 코멘트)
            parts.append("{!JP}")
            # 폰트/크기 오버라이드
            parts.append(fr"{{\r\fn{JP_FONT}\fs{fs_jp}}}")
            parts.append("\\N".join(jp).replace("\n", "\\N"))

        # 한국어 줄 (위쪽)
        if ko:
            if jp:
                parts.append("\\N")
            # 한국어 블록 마커 (ASS 코멘트)
            parts.append("{!KR}")
            parts.append(fr"{{\r\fn{KR_FONT}\fs{fs_kr}}}")
            parts.append("\\N".join(ko).replace("\n", "\\N"))

        pl = "".join(parts)
        # 텍스트가 하나도 없으면 버림
        return "" if pl == head else pl

    temp = []
    for a, b, ko, jp in segs:
        pl = payload(ko, jp)
        if not pl:
            continue
        if temp and temp[-1][2] == pl:
            temp[-1] = (temp[-1][0], b, pl)
        else:
            temp.append((a, b, pl))

    MIN_MS = 220  # 너무 짧은 깜빡임 방지
    fixed = []
    for s, e, pl in temp:
        if fixed and s <= fixed[-1][1]:
            s = fixed[-1][1] + 1  # 안전 간격 0 → 바로 붙임 (1ms 여유)
        if e - s < MIN_MS:
            e = s + MIN_MS
        fixed.append((s, e, pl))
    return fixed

# ------------------ 파일 선택 ------------------
def ask_files_multi(title, filetypes):
    paths = filedialog.askopenfilenames(title=title, filetypes=filetypes)
    paths = list(paths)
    paths.sort(key=natural_key)
    return paths

# ------------------ 메인 ------------------
def main():
    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo(
        "자막 병기(ASS)",
        "영상, 한국어, 일본어 파일을 각각 다중 선택합니다.\n"
        "파일명 정렬 순서대로 1:1:1 매칭합니다.",
    )

    videos = ask_files_multi(
        "영상 선택",
        [
            ("Video", "*.mp4 *.mkv *.mov *.avi *.wmv"),
            ("All", "*.*"),
        ],
    )
    if not videos:
        return
    kors = ask_files_multi(
        "한국어 자막 선택 (ASS/SRT/SMI 혼용)",
        [
            ("Sub", "*.ass *.srt *.smi *.ssa *.txt"),
            ("All", "*.*"),
        ],
    )
    if not kors:
        return
    jpns = ask_files_multi(
        "일본어 자막 선택 (ASS/SRT/SMI 혼용)",
        [
            ("Sub", "*.ass *.srt *.smi *.ssa *.txt"),
            ("All", "*.*"),
        ],
    )
    if not jpns:
        return

    # 폰트 '크기'만 물어봅니다.
    fs_kr = simpledialog.askstring(
        "폰트 크기(한국어, 윗줄)", "한국어 줄 폰트 크기 (예: 25)", initialvalue="25"
    )
    if not fs_kr:
        return
    fs_jp = simpledialog.askstring(
        "폰트 크기(일본어, 아랫줄)", "일본어 줄 폰트 크기 (예: 120)", initialvalue="120"
    )
    if not fs_jp:
        return

    try:
        fs_kr = int(fs_kr)
        fs_jp = int(fs_jp)
    except Exception:
        messagebox.showerror("오류", "폰트 크기는 정수로 입력해 주세요.")
        return

    n = min(len(videos), len(kors), len(jpns))
    if n == 0:
        messagebox.showerror("오류", "매칭 가능한 항목이 없습니다.")
        return
    if not (len(videos) == len(kors) == len(jpns)):
        messagebox.showinfo("알림", f"선택 개수가 다릅니다. 앞에서부터 {n}개만 처리합니다.")

    done, errs = 0, []
    for i in range(n):
        v, k, j = videos[i], kors[i], jpns[i]
        try:
            k_ev = load_sub_auto(k)
            j_ev = load_sub_auto(j)
            segs = build_segments_singletrack(k_ev, j_ev)
            fixed = fuse_payloads_no_gap(segs, fs_kr, fs_jp)

            out_path = os.path.splitext(v)[0] + ".ass"
            lines = []
            lines.append("[Script Info]")
            lines.append("ScriptType: v4.00+")
            lines.append("PlayResX: 1920")
            lines.append("PlayResY: 1080")
            lines.append("ScaledBorderAndShadow: yes")
            lines.append("")
            lines.append("[V4+ Styles]")
            lines.append(
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
                "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
                "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
                "Alignment, MarginL, MarginR, MarginV, Encoding"
            )
            # Base 스타일은 최소만. 위치/크기는 각 줄 오버라이드로 강제.
            lines.append(
                "Style: Base,Arial,36,&H00FFFFFF,&H000000FF,&H00000000,&H7F000000,"
                "0,0,0,0,100,100,0,0,1,2,0,2,0,0,0,1"
            )
            lines.append("")
            lines.append("[Events]")
            lines.append(
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
                "MarginV, Effect, Text"
            )

            for s, e, pl in fixed:
                lines.append(
                    f"Dialogue: 0,{ms_to_ass(s)},{ms_to_ass(e)},Base,,0,0,0,,{pl}"
                )

            with open(out_path, "w", encoding="utf-8-sig") as f:
                f.write("\n".join(lines))
            done += 1
        except Exception as e:
            errs.append(f"{os.path.basename(v)}: {e}")

    msg = f"{done}개 변환 완료"
    if errs:
        msg += "\n\n오류:\n" + "\n".join(errs[:10])
        if len(errs) > 10:
            msg += "\n..."
    messagebox.showinfo("완료", msg)

if __name__ == "__main__":
    main()
