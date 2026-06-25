"""
claim_slot.py  —  OCI Hermes instance auto-claim script
Works on: Windows (local / Task Scheduler) + Linux (GitHub Actions)
"""

import oci
import time
import datetime
import json
import os
import sys
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ====== Settings (already filled in — do not edit) ======
COMPARTMENT_ID      = "ocid1.tenancy.oc1..aaaaaaaapqldkwxh2zbtopwfgr5gzups6sw2jezaryemprnm4b5zsccmwsnq"
AVAILABILITY_DOMAIN = "gjNP:AP-TOKYO-1-AD-1"
SUBNET_ID           = "ocid1.subnet.oc1.ap-tokyo-1.aaaaaaaakqxd2jbmmraibf37rd7k2rctazsnwjjxbpypcnixcqu437wigi7a"
IMAGE_ID            = "ocid1.image.oc1.ap-tokyo-1.aaaaaaaac6xgrmnpr676gm356kgsf2lr23e2e5ik6oigfuno3ybz3nul5riq"
SHAPE               = "VM.Standard.A1.Flex"
OCPUS               = 2
MEMORY_GB           = 12
INSTANCE_NAME       = "Hermes"

RETRY_INTERVAL_SECONDS = 90   # base wait between retries
RETRY_JITTER_SECONDS   = 10   # actual wait = base ± jitter  → 80~100 s

# GitHub Actions jobs have a 6-hour hard limit.
# Stop looping with 10 minutes to spare so the job exits cleanly;
# the next cron-triggered job will pick up automatically.
GITHUB_ACTIONS_MAX_SECONDS = 6 * 3600 - 600   # 5 h 50 m

# ====== Paths (relative to this script's folder) ======
SCRIPT_DIR          = os.path.dirname(os.path.abspath(__file__))
SSH_PUBLIC_KEY_PATH = os.path.join(SCRIPT_DIR, "ssh-key-2026-06-21.key.pub")
SSH_PRIVATE_KEY_PATH= os.path.join(SCRIPT_DIR, "ssh-key-2026-06-21.key")
STATUS_FILE         = os.path.join(SCRIPT_DIR, "status.json")
LOG_FILE            = os.path.join(SCRIPT_DIR, "log.txt")
SUCCESS_FILE        = os.path.join(SCRIPT_DIR, "SUCCESS.txt")
ENV_FILE            = os.path.join(SCRIPT_DIR, ".env")

IS_GITHUB_ACTIONS   = os.environ.get("GITHUB_ACTIONS") == "true"


# ──────────────────────────────────────────────────────────
# .env loader  (local use only — GitHub uses Secrets)
# ──────────────────────────────────────────────────────────
def load_dotenv():
    """Read KEY=VALUE lines from .env into os.environ (if not already set)."""
    if not os.path.exists(ENV_FILE):
        return
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip()
                if key and val:
                    os.environ.setdefault(key, val)


# ──────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────
def log(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ──────────────────────────────────────────────────────────
# Status file
# ──────────────────────────────────────────────────────────
def load_prev_total():
    if not os.path.exists(STATUS_FILE):
        return 0
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("total_attempts", 0)
    except Exception:
        return 0


def write_status(state, session_attempts, total_attempts, extra=None):
    data = {
        "state"           : state,
        "session_attempts": session_attempts,
        "total_attempts"  : total_attempts,
        "last_update"     : datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if extra:
        data.update(extra)
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────
# Retry timing
# ──────────────────────────────────────────────────────────
def next_wait_seconds():
    return random.randint(
        RETRY_INTERVAL_SECONDS - RETRY_JITTER_SECONDS,
        RETRY_INTERVAL_SECONDS + RETRY_JITTER_SECONDS,
    )


# ──────────────────────────────────────────────────────────
# OCI config  (env vars → local file fallback)
# ──────────────────────────────────────────────────────────
def get_oci_config():
    """
    GitHub Actions: reads from Secrets (env vars).
    Local Windows:  reads from ~/.oci/config as before.
    """
    user = os.environ.get("OCI_USER_OCID")
    if user:
        # Write the PEM key to a temp file (GitHub Actions has no persistent disk)
        key_content = os.environ.get("OCI_API_KEY", "")
        key_path    = "/tmp/oci_api_key.pem" if not sys.platform.startswith("win") \
                      else os.path.join(os.environ.get("TEMP", "C:\\Temp"), "oci_api_key.pem")
        os.makedirs(os.path.dirname(key_path), exist_ok=True)
        with open(key_path, "w") as f:
            f.write(key_content)
        return {
            "user"       : user,
            "tenancy"    : os.environ.get("OCI_TENANCY_OCID"),
            "fingerprint": os.environ.get("OCI_FINGERPRINT"),
            "region"     : os.environ.get("OCI_REGION", "ap-tokyo-1"),
            "key_file"   : key_path,
        }
    else:
        return oci.config.from_file()


def get_ssh_public_key():
    """
    GitHub Actions: reads from OCI_SSH_PUBLIC_KEY env var.
    Local:          reads from the .pub file next to this script.
    """
    from_env = os.environ.get("OCI_SSH_PUBLIC_KEY")
    if from_env:
        return from_env.strip()
    if not os.path.exists(SSH_PUBLIC_KEY_PATH):
        print("ERROR: SSH public key not found.")
        print(f"  Expected: {SSH_PUBLIC_KEY_PATH}")
        print("  OR set the OCI_SSH_PUBLIC_KEY environment variable.")
        sys.exit(1)
    with open(SSH_PUBLIC_KEY_PATH, "r") as f:
        return f.read().strip()


# ──────────────────────────────────────────────────────────
# Sound alert  (Windows only — silently skipped elsewhere)
# ──────────────────────────────────────────────────────────
def beep_success():
    try:
        import winsound
        for _ in range(5):
            winsound.Beep(1000, 400)
            time.sleep(0.2)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────
# Email notification
# ──────────────────────────────────────────────────────────
def send_success_email(public_ip):
    """Send success email via Gmail SMTP.

    Local:          configure .env  (copy .env.example → .env)
    GitHub Actions: set Secrets NOTIFY_EMAIL / GMAIL_FROM / GMAIL_APP_PASSWORD
    """
    notify_to  = os.environ.get("NOTIFY_EMAIL")
    gmail_from = os.environ.get("GMAIL_FROM")
    app_pass   = os.environ.get("GMAIL_APP_PASSWORD")

    if not all([notify_to, gmail_from, app_pass]):
        log("Email config not set — skipping notification. "
            "(Set NOTIFY_EMAIL / GMAIL_FROM / GMAIL_APP_PASSWORD in .env or GitHub Secrets)")
        return

    ssh_cmd = f'ssh -i "ssh-key-2026-06-21.key" ubuntu@{public_ip}'
    acquired_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    body = f"""\
✅ Hermes OCI インスタンスを取得しました！

取得日時 : {acquired_at}
パブリックIP : {public_ip}

SSH接続コマンド（PowerShellで実行）:
  {ssh_cmd}

--- 次のステップ ---
1. OCIコンソール → Security List → ポート22(SSH)が開いていることを確認
2. SSHで接続してHermes Agentをインストール
3. アイドル回収対策のcron設定（30分ごとにpingしてCPU使用率を維持）
4. 鍵ペアを新しいものに差し替え（古い鍵はAIチャットに漏れたため）
5. GitHubリポジトリを削除（不要になったため）

このメールは claim_slot.py が自動送信しました。
"""

    msg = MIMEMultipart()
    msg["From"]    = gmail_from
    msg["To"]      = notify_to
    msg["Subject"] = f"✅ Hermes OCI取得完了 — IP: {public_ip}"
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(gmail_from, app_pass)
            server.sendmail(gmail_from, notify_to, msg.as_string())
        log(f"✅ 成功通知メールを送信しました → {notify_to}")
    except Exception as e:
        log(f"⚠ メール送信失敗: {e}")


# ──────────────────────────────────────────────────────────
# Success handler
# ──────────────────────────────────────────────────────────
def handle_success(config, compute_client, instance, session_attempts, total_attempts):
    log(f"[TOTAL #{total_attempts}] ✅ SUCCESS! Instance ID: {instance.id}")
    write_status("success", session_attempts, total_attempts, {"instance_id": instance.id})

    # Wait for public IP
    public_ip   = None
    vnic_client = oci.core.VirtualNetworkClient(config)
    log("パブリックIP取得中（最大2分待ちます）...")
    for _ in range(24):
        time.sleep(5)
        try:
            attachments = compute_client.list_vnic_attachments(
                compartment_id=COMPARTMENT_ID, instance_id=instance.id
            ).data
            if attachments:
                vnic = vnic_client.get_vnic(attachments[0].vnic_id).data
                if vnic.public_ip:
                    public_ip = vnic.public_ip
                    break
        except Exception:
            pass

    ip_display = public_ip or "(OCIコンソールで確認してください)"
    log(f"パブリックIP: {ip_display}")

    # Write SUCCESS.txt
    ssh_cmd = f'ssh -i "ssh-key-2026-06-21.key" ubuntu@{ip_display}'
    with open(SUCCESS_FILE, "w", encoding="utf-8") as f:
        f.write("=== Hermes OCI Instance — SUCCESS ===\n\n")
        f.write(f"取得日時    : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"インスタンスID: {instance.id}\n")
        f.write(f"パブリックIP  : {ip_display}\n\n")
        f.write("SSH接続コマンド（PowerShellで実行）:\n")
        f.write(f"  {ssh_cmd}\n\n")
        f.write("--- 次のステップ ---\n")
        f.write("1. Security ListでSSH(ポート22)が開いていることを確認\n")
        f.write("2. Hermes Agentをインストール\n")
        f.write("3. アイドル回収対策cronを設定（30分ごとにping）\n")
        f.write("4. 鍵ペアを新しいものに差し替え\n")
        f.write("5. GitHubリポジトリを削除\n")

    write_status("success", session_attempts, total_attempts, {
        "instance_id": instance.id,
        "public_ip"  : ip_display,
    })

    beep_success()
    send_success_email(ip_display)
    log("完了。このウィンドウを閉じて SUCCESS.txt を確認してください。")


# ──────────────────────────────────────────────────────────
# Main loop
# ──────────────────────────────────────────────────────────
def main():
    load_dotenv()

    config         = get_oci_config()
    ssh_public_key = get_ssh_public_key()
    compute_client = oci.core.ComputeClient(config)

    launch_details = oci.core.models.LaunchInstanceDetails(
        compartment_id    = COMPARTMENT_ID,
        availability_domain = AVAILABILITY_DOMAIN,
        shape             = SHAPE,
        display_name      = INSTANCE_NAME,
        shape_config      = oci.core.models.LaunchInstanceShapeConfigDetails(
            ocpus         = OCPUS,
            memory_in_gbs = MEMORY_GB,
        ),
        create_vnic_details = oci.core.models.CreateVnicDetails(
            subnet_id       = SUBNET_ID,
            assign_public_ip= True,
        ),
        source_details    = oci.core.models.InstanceSourceViaImageDetails(
            image_id      = IMAGE_ID,
        ),
        metadata          = {"ssh_authorized_keys": ssh_public_key},
    )

    prev_total       = load_prev_total()
    session_attempts = 0
    total_attempts   = prev_total
    start_time       = time.time()

    write_status("running", session_attempts, total_attempts)
    log("===== Claim Slot script started =====")
    log(f"Previous sessions total: {prev_total} attempts. Continuing from there.")
    range_lo = RETRY_INTERVAL_SECONDS - RETRY_JITTER_SECONDS
    range_hi = RETRY_INTERVAL_SECONDS + RETRY_JITTER_SECONDS
    log(f"Retrying every {range_lo}–{range_hi}s (randomized). Leave this window open.")
    if IS_GITHUB_ACTIONS:
        log(f"GitHub Actions mode — will stop after {GITHUB_ACTIONS_MAX_SECONDS // 60} min and let the next cron job continue.")

    try:
        while True:
            # ── GitHub Actions time-limit check ──
            if IS_GITHUB_ACTIONS:
                elapsed = time.time() - start_time
                if elapsed >= GITHUB_ACTIONS_MAX_SECONDS:
                    log(f"⏱ GitHub Actions time limit approaching ({elapsed/3600:.1f}h). "
                        "Stopping cleanly — next cron job will continue.")
                    write_status("waiting", session_attempts, total_attempts)
                    break

            session_attempts += 1
            total_attempts   += 1

            try:
                response = compute_client.launch_instance(launch_details)
                handle_success(config, compute_client, response.data,
                               session_attempts, total_attempts)
                break

            except oci.exceptions.ServiceError as e:
                msg         = str(getattr(e, "message", "") or "")
                code        = str(getattr(e, "code",    "") or "")
                status_code = getattr(e, "status", None)

                if "Out of capacity" in msg or "Out of host capacity" in msg or "OutOfCapacity" in code:
                    wait_s = next_wait_seconds()
                    log(f"[TOTAL #{total_attempts}] Out of capacity. Retrying in {wait_s}s.")
                    write_status("waiting", session_attempts, total_attempts)
                    time.sleep(wait_s)

                elif status_code == 429 or "TooManyRequests" in code:
                    wait_s = next_wait_seconds() + RETRY_INTERVAL_SECONDS
                    log(f"[TOTAL #{total_attempts}] Rate limited (429). Waiting {wait_s}s.")
                    write_status("waiting", session_attempts, total_attempts)
                    time.sleep(wait_s)

                else:
                    wait_s = next_wait_seconds()
                    log(f"[TOTAL #{total_attempts}] Unexpected error ({code}): {msg}. Retrying in {wait_s}s.")
                    write_status("error", session_attempts, total_attempts,
                                 {"error": f"{code}: {msg}"})
                    time.sleep(wait_s)

    except KeyboardInterrupt:
        log(f"Stopped by user. Session: {session_attempts} attempts / All-time: {total_attempts} attempts")
        write_status("stopped", session_attempts, total_attempts)


if __name__ == "__main__":
    main()
