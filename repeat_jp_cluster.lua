-- repeat_jp_cluster.lua
--
-- 통합 ASS 자막(한국어+일본어)에서
-- {!JP}, {!KR} 태그를 기준으로 일본어 구간(클러스터)을 잡고
-- 그 클러스터 전체를 N번 반복 재생한다.
--
-- 구현 방식
--  - mpv의 ab-loop-a/b 를 사용하지 않고
--    직접 time-pos 를 A로 되감으면서 loop_count 를 센다.
--  - 한 클러스터에 대해 loop_count == LOOP_COUNT 가 되면
--    그 클러스터는 finished 로 표시해서
--    같은 구간에서 즉시 또 루프가 걸리지 않게 막는다.
--  - 재생이 그 클러스터의 끝 시점(B)을 충분히 지나가면
--    finished 플래그를 지워서
--    나중에 되감기해서 다시 와도 새로 루프 가능하게 한다.

local mp = require "mp"

---------------------- 설정 ----------------------

local MIN_DURATION    = 2.0   -- 클러스터 전체 길이 최소(초)
local MIN_JP_CHARS    = 10    -- 일본어 최소 글자수 (0이면 무시)
local LOOP_COUNT      = 3     -- A→B→A 한 바퀴를 몇 번 할지
local CLUSTER_GAP_EPS = 0.05  -- 같은 일본어가 이 간격 이내로 붙어 있으면 한 클러스터

-- 클러스터 끝을 약간 당겨서(자막이 사라지기 직전) 점프하기 위한 보정값
-- 너무 크게 잡으면 마지막 한두 글자가 잘릴 수 있으니 0.05~0.10 정도만 권장
local END_EARLY       = 0.08  -- 초 단위

-- 사용자가 "명시적으로" 뒤로 감았다고 볼 최소 시간 차이
local BACK_SEEK_RESET_SEC = 0.8

-- finished 삭제 시점: 클러스터 끝 시간 + 이 값 초를 넘어가면 지움
local FINISHED_CLEAR_DELAY = 0.5

local DEBUG_LOG = true
local DEBUG_OSD = false

-------------------------------------------------

local function dbg(msg)
    if DEBUG_LOG then
        mp.msg.info("[JP-LOOP] " .. msg)
    end
    if DEBUG_OSD then
        mp.osd_message("[JP] " .. msg, 1.0)
    end
end

local function short_text(s)
    if not s then return "" end
    s = s:gsub("\n", " / ")
    if #s > 24 then
        return s:sub(1, 24) .. "..."
    end
    return s
end

---------------------- 일본어 추출 / 글자수 ----------------------

local function get_sub_ass()
    local ass = mp.get_property("sub-text/ass")
    if not ass or ass == "" then
        ass = mp.get_property("sub-text-ass")
    end
    return ass or ""
end

-- ASS 에서 {!JP}~{!KR} 사이만 일본어 텍스트로 본다.
local function extract_jp_text_from_ass(ass)
    if not ass or ass == "" then
        return nil
    end

    local jp_pos = ass:find("{!JP}", 1, true)
    if not jp_pos then
        return nil
    end

    local after_jp = jp_pos + #"{!JP}"
    local rest = ass:sub(after_jp)

    local kr_pos = rest:find("{!KR}", 1, true)
    local jp_segment
    if kr_pos then
        jp_segment = rest:sub(1, kr_pos - 1)
    else
        jp_segment = rest
    end

    -- { ... } 태그 제거
    jp_segment = jp_segment:gsub("{.-}", "")

    -- \N, \n → 실제 줄바꿈
    jp_segment = jp_segment:gsub("\\[Nn]", "\n")

    -- 줄별 trim + 빈 줄 제거
    local norm_lines = {}
    for line in jp_segment:gmatch("([^\n]+)") do
        line = line:gsub("^%s+", ""):gsub("%s+$", "")
        if line ~= "" then
            norm_lines[#norm_lines + 1] = line
        end
    end

    local norm = table.concat(norm_lines, "\n")
    if norm == "" then
        return nil
    end
    return norm
end

-- UTF-8 코드포인트 이터레이터
local function utf8_codepoints(s)
    local i, len = 1, #s
    return function()
        if i > len then return nil end
        local c1 = s:byte(i)

        if c1 < 0x80 then
            i = i + 1
            return c1
        end

        if c1 < 0xE0 and i + 1 <= len then
            local c2 = s:byte(i + 1)
            local cp = (c1 % 0x20) * 0x40 + (c2 % 0x40)
            i = i + 2
            return cp
        end

        if c1 < 0xF0 and i + 2 <= len then
            local c2 = s:byte(i + 1)
            local c3 = s:byte(i + 2)
            local cp = (c1 % 0x10) * 0x1000 +
                       (c2 % 0x40) * 0x40 +
                       (c3 % 0x40)
            i = i + 3
            return cp
        end

        if i + 3 <= len then
            local c2 = s:byte(i + 1)
            local c3 = s:byte(i + 2)
            local c4 = s:byte(i + 3)
            local cp = (c1 % 0x08) * 0x40000 +
                       (c2 % 0x40) * 0x1000 +
                       (c3 % 0x40) * 0x40 +
                       (c4 % 0x40)
            i = i + 4
            return cp
        end

        i = i + 1
        return nil
    end
end

local function is_jp_cp(cp)
    if not cp then return false end
    if cp >= 0x3040 and cp <= 0x309F then return true end -- 히라가나
    if cp >= 0x30A0 and cp <= 0x30FF then return true end -- 가타카나
    if cp >= 0xFF66 and cp <= 0xFF9D then return true end -- 반각 가타카나
    if cp >= 0x3400 and cp <= 0x4DBF then return true end -- CJK 확장 A
    if cp >= 0x4E00 and cp <= 0x9FFF then return true end -- CJK 기본
    return false
end

local function count_jp_chars(s)
    if not s or s == "" then return 0 end
    local n = 0
    for cp in utf8_codepoints(s) do
        if is_jp_cp(cp) then
            n = n + 1
        end
    end
    return n
end

---------------------- 상태 ----------------------

-- 현재 “쌓이는 중인” 일본어 클러스터
local cur_jp_text = nil
local cur_start   = nil
local cur_end     = nil

-- 현재 루프 상태
-- active_loop = { text = ..., start = ..., end_ = ..., loops_done = ... }
local active_loop = nil

-- 이미 루프를 끝낸 클러스터들
-- finished[key] = { start = ..., end_ = ... }
local finished = {}

-- 방금 끝낸 클러스터의 key. 구간을 완전히 벗어난 뒤에 지우기 위함.
local last_finished_key = nil
local finished_clear_pending = false

-- 시간 추적
local last_time = nil

local function make_key(text, start)
    -- 시작 시간을 0.05초 단위로 양자화해서 float 오차 완화
    local s = math.floor(start * 20 + 0.5) / 20.0
    return text .. "|" .. tostring(s)
end

local function is_finished(text, start)
    local key = make_key(text, start)
    return finished[key] ~= nil
end

local function mark_finished(text, start, end_)
    local key = make_key(text, start)
    finished[key] = { start = start, end_ = end_ }
    last_finished_key = key
    finished_clear_pending = true
    dbg(string.format("FINISH mark [%s] %.3f-%.3f",
        short_text(text), start, end_))
end

local function try_clear_last_finished_by_time(t)
    if not finished_clear_pending then
        return
    end
    if not last_finished_key then
        finished_clear_pending = false
        return
    end
    local info = finished[last_finished_key]
    if not info then
        finished_clear_pending = false
        last_finished_key = nil
        return
    end
    -- 재생 시간이 해당 클러스터 끝 + 딜레이를 넘어서면
    -- 이 클러스터는 다시 루프 가능한 상태로 되돌린다.
    local limit = info.end_ + FINISHED_CLEAR_DELAY
    if t > limit then
        dbg(string.format("CLEAR finished for key (t=%.3f > %.3f)", t, limit))
        finished[last_finished_key] = nil
        last_finished_key = nil
        finished_clear_pending = false
    end
end

local function reset_all()
    dbg("RESET ALL")
    cur_jp_text = nil
    cur_start   = nil
    cur_end     = nil

    active_loop = nil
    finished = {}
    last_finished_key = nil
    finished_clear_pending = false

    last_time = nil
end

---------------------- 클러스터 확정 & 루프 시작 ----------------------

local function start_loop_for_cluster(text, s, e)
    local duration = e - s
    if duration < MIN_DURATION then
        dbg(string.format("SKIP short cluster [%.3f-%.3f] dur=%.3f",
            s, e, duration))
        return
    end

    local jp_chars = count_jp_chars(text)
    if MIN_JP_CHARS > 0 and jp_chars < MIN_JP_CHARS then
        dbg(string.format("SKIP few-chars cluster (%d < %d)",
            jp_chars, MIN_JP_CHARS))
        return
    end

    if is_finished(text, s) then
        dbg("SKIP cluster (already finished recently)")
        return
    end

    -- B 시간을 약간 앞당겨서(END_EARLY) 자막이 완전히 사라진 뒤에 점프되는 걸 줄인다.
    -- 단, 너무 짧아져서 MIN_DURATION 조건을 깨지 않도록 여유가 있을 때만 조정한다.
    local eff_e = e
    if END_EARLY > 0 then
        local min_len_for_shrink = MIN_DURATION + END_EARLY + 0.05
        if duration > min_len_for_shrink then
            eff_e = e - END_EARLY
        end
    end

    if active_loop then
        dbg("CANCEL previous loop (new cluster)")
        active_loop = nil
    end

    active_loop = {
        text       = text,
        start      = s,
        end_       = eff_e,
        loops_done = 0,
    }

    -- 바로 A 시점으로 되감기
    mp.set_property_number("time-pos", s)

    dbg(string.format("START loop [%s] A=%.3f B=%.3f(real=%.3f)",
        short_text(text), s, eff_e, e))
end

local function finalize_cluster_if_any(reason)
    if not (cur_jp_text and cur_start and cur_end) then
        return
    end

    dbg(string.format("FINALIZE cluster [%s] %.3f-%.3f (%s)",
        short_text(cur_jp_text), cur_start, cur_end, reason or ""))

    start_loop_for_cluster(cur_jp_text, cur_start, cur_end)

    cur_jp_text = nil
    cur_start   = nil
    cur_end     = nil
end

---------------------- sub-text 변경 시 ----------------------

local function on_sub_text_change(_, _)
    -- 루프가 돌아가는 동안에는 새로운 클러스터 분석을 하지 않는다.
    if active_loop then
        return
    end

    local ass = get_sub_ass()
    if ass == "" then
        cur_jp_text = nil
        cur_start   = nil
        cur_end     = nil
        return
    end

    local s = mp.get_property_number("sub-start")
    local e = mp.get_property_number("sub-end")
    if not s or not e or e <= s then
        return
    end

    local jp_text = extract_jp_text_from_ass(ass)

    if jp_text then
        -- 일본어가 있는 줄
        if cur_jp_text and cur_start and cur_end
           and jp_text == cur_jp_text then
            -- 같은 문장이고 거의 붙어 있으면 같은 클러스터로 확장
            local gap = s - cur_end
            if gap >= -0.001 and gap <= CLUSTER_GAP_EPS then
                if e > cur_end then
                    cur_end = e
                    dbg(string.format("EXTEND cluster [%s] to %.3f",
                        short_text(cur_jp_text), cur_end))
                end
                return
            end
        end

        -- 새 일본어 문장 시작
        if cur_jp_text and cur_start and cur_end then
            finalize_cluster_if_any("on new JP")
        end

        cur_jp_text = jp_text
        cur_start   = s
        cur_end     = e
        dbg(string.format("NEW cluster [%s] %.3f-%.3f",
            short_text(cur_jp_text), cur_start, cur_end))

    else
        -- 일본어 없는 줄
        if cur_jp_text and cur_start and cur_end then
            finalize_cluster_if_any("on non-JP")
        end

        cur_jp_text = nil
        cur_start   = nil
        cur_end     = nil
    end
end

---------------------- 시간 변화 시 (루프 카운트) ----------------------

local function on_time_change(_, value)
    local t = tonumber(value)
    if not t then
        last_time = nil
        return
    end

    -- 먼저 finished 클러스터 자동 삭제 시도
    try_clear_last_finished_by_time(t)

    -- 루프 중이 아닐 때, 사용자가 '명시적으로' 뒤로 감은 경우
    -- (예: 클러스터를 다 들은 뒤 되감기)
    -- → finished 정보를 싹 지워서 같은 클러스터도 다시 루프 가능하게 한다.
    if (not active_loop) and last_time and (t < last_time - BACK_SEEK_RESET_SEC) then
        dbg(string.format("USER BACKWARD seek %.3f → %.3f → reset finished", last_time, t))
        finished = {}
        last_finished_key = nil
        finished_clear_pending = false
    end

    if active_loop then
        local a = active_loop.start
        local b = active_loop.end_

        -- 사용자가 클러스터 범위에서 멀리 나가면 루프 강제 종료
        if t < a - 1.0 or t > b + 1.0 then
            dbg(string.format(
                "SEEK out of loop range (t=%.3f, loop %.3f-%.3f) → CANCEL loop",
                t, a, b))
            active_loop = nil
            last_time   = t
            return
        end

        if last_time then
            -- 한 번의 재생에서 "B를 통과했다"는 순간을 감지
            -- last_time < b 이고 t >= b 이면
            -- A→B 재생을 한 번 끝냈다고 본다.
            if last_time < b and t >= b then
                active_loop.loops_done = active_loop.loops_done + 1
                dbg(string.format("LOOP pass #%d [%s] (A=%.3f, B=%.3f, %.3f→%.3f)",
                    active_loop.loops_done,
                    short_text(active_loop.text),
                    a, b, last_time, t))

                if active_loop.loops_done < LOOP_COUNT then
                    -- 다시 A로 되감기
                    mp.set_property_number("time-pos", a)
                else
                    -- 반복 횟수 채움 → 루프 종료, finished 표시
                    dbg("LOOP FINISHED → stop looping for this cluster")
                    mark_finished(active_loop.text, a, b)
                    active_loop = nil
                end
            end
        end
    end

    last_time = t
end

---------------------- 파일 로드 시 ----------------------

local function on_file_loaded(_)
    reset_all()
end

mp.observe_property("sub-text", "string", on_sub_text_change)
mp.observe_property("playback-time", "number", on_time_change)
mp.register_event("file-loaded", on_file_loaded)
