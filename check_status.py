"""
check_status.py  —  ローカルでの状態確認スクリプト
claim_slot.batとは別のウィンドウで実行する。止まっていたら赤く表示。
"""
import json
import os
import re
import sys
from datetime import datetime

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
STATUS_FILE = os.path.join(SCRIPT_DIR, "status.json")
LOG_FILE    = os.path.join(SCRIPT_DIR, "log.txt")

# Windows コンソールの色コード
try:
    import ctypes
    ctypes.windll.kernel32.SetConsoleMode(
        ctypes.windll.kernel32.GetStdHandle(-11), 7)
except Exception:
    pass

RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
GRAY   = "\033[90m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

W = 58


def hr(char="─"):
    print(char * W)


def fmt_elapsed(seconds):
    seconds = int(seconds)
    h, rem  = divmod(seconds, 3600)
    m, s    = divmod(rem, 60)
    if h:
        return f"{h}時間{m}分"
    if m:
        return f"{m}分{s}秒"
    return f"{s}秒"


def parse_log():
    if not os.path.exists(LOG_FILE):
        return None

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        raw_lines = [l.rstrip() for l in f if l.strip()]

    sessions  = []
    attempts  = []
    errors    = []
    successes = []

    for line in raw_lines:
        m = re.match(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (.*)', line)
        if not m:
            continue
        try:
            ts  = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            msg = m.group(2)
        except ValueError:
            continue

        if "===== Claim Slot script started =====" in msg:
            sessions.append(ts)
        elif "TOTAL #" in msg and ("Out of capacity" in msg or "Rate limited" in msg):
            attempts.append(ts)
        elif "SUCCESS" in msg and "Instance" in msg:
            successes.append(ts)
        elif "Unexpected error" in msg:
            errors.append((ts, msg))

    first_ts = sessions[0] if sessions else None
    last_ts  = None
    if raw_lines:
        m2 = re.match(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]', raw_lines[-1])
        if m2:
            try:
                last_ts = datetime.strptime(m2.group(1), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass

    elapsed_str = ""
    per_hour    = None
    if first_ts and last_ts:
        elapsed_s   = (last_ts - first_ts).total_seconds()
        elapsed_str = fmt_elapsed(elapsed_s) if elapsed_s > 0 else "1秒未満"
        if elapsed_s >= 60 and attempts:
            per_hour = round(len(attempts) / (elapsed_s / 3600), 1)

    return {
        "raw_lines"  : raw_lines,
        "sessions"   : sessions,
        "attempts"   : attempts,
        "errors"     : errors,
        "successes"  : successes,
        "first_ts"   : first_ts,
        "last_ts"    : last_ts,
        "elapsed_str": elapsed_str,
        "per_hour"   : per_hour,
    }


def main():
    os.system("cls" if sys.platform.startswith("win") else "clear")
    print()
    print(CYAN + BOLD + "=" * W + RESET)
    print(CYAN + BOLD + f"{'Hermes OCI Claim-Slot  —  Status Check':^{W}}" + RESET)
    print(CYAN + BOLD + "=" * W + RESET)
    print()

    # ── status.json がない ──
    if not os.path.exists(STATUS_FILE):
        print(RED + "  ❌ まだ起動されていません" + RESET)
        print()
        print("  → claim_slot.bat をダブルクリックして起動してください")
        print()
        input("Enterで閉じる...")
        return

    with open(STATUS_FILE, "r", encoding="utf-8") as f:
        status = json.load(f)

    state        = status.get("state", "unknown")
    last_update  = status.get("last_update", "")
    total        = status.get("total_attempts", 0)
    session      = status.get("session_attempts", 0)

    # 最終更新から何分経ったか
    stale_min = 999
    if last_update:
        try:
            last_dt   = datetime.strptime(last_update, "%Y-%m-%d %H:%M:%S")
            stale_min = int((datetime.now() - last_dt).total_seconds() / 60)
        except Exception:
            pass

    is_stale = (stale_min > 5 and state != "success")

    # ── 状態ラベル ──
    STATE_INFO = {
        "running": (GREEN,  "▶ 稼働中（キャパシティ確認中）"),
        "waiting": (GREEN,  "⏳ 在庫待ち — 自動リトライ継続中"),
        "success": (GREEN,  "✅ SUCCESS — インスタンス取得済み！"),
        "error"  : (YELLOW, "⚠ エラー発生（下の詳細を確認）"),
        "stopped": (RED,    "⏹ 手動停止"),
    }
    color, label = STATE_INFO.get(state, (GRAY, f"? {state}"))

    if is_stale and state != "success":
        color = RED
        label = "❌ 停止中（最終更新が5分以上前）— スクリプトが止まっています！"

    print(f"  {color}{BOLD}{label}{RESET}")
    print()
    print(f"  最終更新    : {last_update}  ({stale_min}分前)")
    print(f"  今セッション: {session:,} 回試行")
    print(f"  累計        : {total:,} 回試行")

    stats = parse_log()
    if stats:
        if stats["elapsed_str"]:
            first = stats["first_ts"].strftime("%Y-%m-%d %H:%M") if stats["first_ts"] else "-"
            print(f"  開始日時    : {first}")
            print(f"  経過時間    : {stats['elapsed_str']}")
        if stats["per_hour"] is not None:
            print(f"  試行頻度    : 約 {stats['per_hour']} 回/時間")
        if stats["sessions"]:
            print(f"  起動回数    : {len(stats['sessions'])} 回（claim_slot.batを起動した回数）")

    if state == "success" and "public_ip" in status:
        print()
        print(GREEN + f"  パブリックIP : {status['public_ip']}" + RESET)
        print(GREEN + f"  SSH接続      : ssh -i \"ssh-key-2026-06-21.key\" ubuntu@{status['public_ip']}" + RESET)
        print(CYAN  + "  → SUCCESS.txt に全手順が書かれています" + RESET)

    if is_stale and state != "success":
        print()
        print(RED  + "  ─────────────────────────────────────────" + RESET)
        print(YELLOW + "  ▶ 対処方法" + RESET)
        print("    1. claim_slot.bat をダブルクリックして再起動")
        print("    2. 黒いウィンドウが開いて [TOTAL #N] が流れていればOK")
        print("    3. PCのスリープ設定を「なし」に変更してください")
        print(RED  + "  ─────────────────────────────────────────" + RESET)

    # ── 最新ログ20行 ──
    print()
    hr()
    print(f"  最新ログ（最新20行）")
    hr()
    if stats and stats["raw_lines"]:
        for line in stats["raw_lines"][-20:]:
            display = line if len(line) <= W - 2 else line[:W - 5] + "..."
            if "SUCCESS" in display:
                print(GREEN + f"  {display}" + RESET)
            elif "error" in display.lower() or "Unexpected" in display:
                print(RED + f"  {display}" + RESET)
            elif "Rate limited" in display:
                print(YELLOW + f"  {display}" + RESET)
            else:
                print(GRAY + f"  {display}" + RESET)
    else:
        print(GRAY + "  (ログファイルがまだありません)" + RESET)

    # ── エラーサマリー ──
    if stats and stats["errors"]:
        print()
        hr()
        print(RED + "  予期しないエラー（直近5件）" + RESET)
        hr()
        for ts, msg in stats["errors"][-5:]:
            short = msg if len(msg) <= W - 14 else msg[:W - 17] + "..."
            print(RED + f"  {ts.strftime('%H:%M:%S')}  {short}" + RESET)

    print()
    hr("─")
    print(GRAY + "  Ctrl+C または Enter で閉じる" + RESET)
    hr("─")
    print()
    input()


if __name__ == "__main__":
    main()
