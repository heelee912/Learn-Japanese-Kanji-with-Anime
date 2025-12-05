import os
import re
from datetime import datetime, timedelta

def load_srt_files():
    directory = os.path.dirname(os.path.realpath(__file__))
    srt_files = []
    for file in os.listdir(directory):
        if file.endswith(".srt"):
            srt_files.append(os.path.join(directory, file))
    return srt_files

def read_srt_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read()

def save_srt_file(file_path, srt_content):
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(srt_content)

def srt_time_to_ms(srt_time):
    dt = datetime.strptime(srt_time, "%H:%M:%S,%f")
    td = timedelta(hours=dt.hour, minutes=dt.minute, seconds=dt.second, microseconds=dt.microsecond)
    return int(td.total_seconds() * 1000)

def ms_to_srt_time(ms):
    hours = ms // 3600000
    ms = ms % 3600000
    minutes = ms // 60000
    ms = ms % 60000
    seconds = ms // 1000
    milliseconds = ms % 1000
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

def parse_srt_blocks(srt_content):
    blocks = re.split(r'\n\s*\n', srt_content.strip())
    parsed = []
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            idx = lines[0]
            times = lines[1]
            text = '\n'.join(lines[2:])
            m = re.match(r'(\d{2}:\d{2}:\d{2},\d+)\s*-->\s*(\d{2}:\d{2}:\d{2},\d+)', times)
            if m:
                start, end = m.groups()
                parsed.append({'idx': idx, 'start': start, 'end': end, 'text': text})
    return parsed

def build_srt_content(blocks):
    out = []
    for i, block in enumerate(blocks, 1):
        out.append(str(i))
        out.append(f"{block['start']} --> {block['end']}")
        out.append(block['text'])
        out.append('')
    return '\n'.join(out).strip() + '\n'

def adjust_srt_sync(blocks, global_adjustment, search_text=None, post_text_adjustment=None):
    found = False
    for block in blocks:
        # 특정 문구 이후 발견 여부 체크
        if search_text and not found and re.search(re.escape(search_text), block['text'], re.IGNORECASE):
            found = True

        if found and post_text_adjustment is not None:
            # 특정 문구 이후: post_text_adjustment만 적용 (절대값)
            start_ms = srt_time_to_ms(block['start']) + post_text_adjustment
            end_ms = srt_time_to_ms(block['end']) + post_text_adjustment
        else:
            # 특정 문구 이전: global_adjustment만 적용
            start_ms = srt_time_to_ms(block['start']) + global_adjustment
            end_ms = srt_time_to_ms(block['end']) + global_adjustment

        start_ms = max(0, start_ms)
        end_ms = max(0, end_ms)

        block['start'] = ms_to_srt_time(start_ms)
        block['end'] = ms_to_srt_time(end_ms)
    return blocks

def main(global_adjustment, search_text, post_text_adjustment):
    srt_files = load_srt_files()
    for srt_file in srt_files:
        srt_content = read_srt_file(srt_file)
        blocks = parse_srt_blocks(srt_content)
        adjusted_blocks = adjust_srt_sync(blocks, global_adjustment, search_text, post_text_adjustment)
        new_content = build_srt_content(adjusted_blocks)
        save_srt_file(srt_file, new_content)
        print(f"Adjusted {srt_file}")

if __name__ == "__main__":
    global_adjustment = int(input("전체 싱크 조절(ms): "))
    search_text = input("특정 문구(없으면 엔터): ").strip()
    post_text_adjustment = None
    if search_text:
        post_text_adjustment = int(input("특정 문구 이후 싱크 조절(ms): "))
    main(global_adjustment, search_text, post_text_adjustment)
