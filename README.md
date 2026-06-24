# Hermes OCI Instance Auto-Claim

OCI Always Free枠のAmpere A1インスタンスを自動でクレームするスクリプト。

---

## ファイル構成

| ファイル | 役割 |
|---------|------|
| `claim_slot.py` | メイン（在庫チェック＆クレームループ） |
| `check_status.py` | 状態確認（色分け表示） |
| `health_check.ps1` | 停止時に赤く警告するヘルスチェック |
| `claim_slot.bat` | Windowsで起動するショートカット |
| `check_status.bat` | 状態確認用ショートカット |
| `health_check.bat` | ヘルスチェック起動用ショートカット |
| `setup_task_scheduler.bat` | タスクスケジューラに登録（ログイン時自動起動） |
| `.env.example` | メール設定テンプレート |
| `.github/workflows/claim.yml` | GitHub Actions設定 |

---

## 方法A：GitHub Actions（推奨 — PCつけっぱなし不要）

### 1. GitHubにパブリックリポジトリを作成

```
リポジトリ名: hermes-claim-oci（任意）
Visibility: Public（無料枠が無制限になる）
```

### 2. このフォルダの中身をpush

**秘密鍵（*.key, *.pem）は絶対にpushしない！**
`.gitignore` に含まれているので、`git add .` しても入りません。

```bash
git init
git add .
git commit -m "Initial setup"
git remote add origin https://github.com/あなたのID/hermes-claim-oci.git
git push -u origin main
```

### 3. GitHub Secretsに以下を登録

**Settings → Secrets and variables → Actions → New repository secret**

| Secret名 | 値の取得場所 |
|---------|------------|
| `OCI_USER_OCID` | OCIコンソール → プロファイル → OCIDをコピー |
| `OCI_TENANCY_OCID` | `~/.oci/config` の `tenancy=` の値 |
| `OCI_FINGERPRINT` | `~/.oci/config` の `fingerprint=` の値 |
| `OCI_REGION` | `ap-tokyo-1` |
| `OCI_API_KEY` | `oci_api_key.pem` の中身をそのまま貼り付け |
| `OCI_SSH_PUBLIC_KEY` | `ssh-key-2026-06-21.key.pub` の中身をそのまま貼り付け |
| `NOTIFY_EMAIL` | 通知を受け取りたいメールアドレス |
| `GMAIL_FROM` | 送信元のGmailアドレス |
| `GMAIL_APP_PASSWORD` | Gmailアプリパスワード（下記参照） |

**Gmailアプリパスワードの取得:**
1. Googleアカウント → セキュリティ → 2段階認証を有効化
2. 同じページで「アプリパスワード」→「メール」「Windows」で生成
3. 表示された16文字をそのままSecretに貼り付け

### 4. 動作確認

Actions タブ → `Hermes OCI Instance Claim` → `Run workflow` で手動起動
→ ログに `[TOTAL #1] Out of capacity. Retrying in 87s.` が出ればOK

### コスト
- **GitHub Actions パブリックリポジトリ: 無料・無制限**
- OCI API呼び出し: 無料（Always Free枠の範囲内）

### 取得後
1. メールが届く → SUCCESS.txtに記載のSSHコマンドで接続確認
2. リポジトリを削除（不要になるため）

---

## 方法B：ローカルPC（タスクスケジューラ）

### 1. メール設定

`.env.example` をコピーして `.env` という名前にし、値を入力:

```
NOTIFY_EMAIL=your@email.com
GMAIL_FROM=your@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

### 2. タスクスケジューラに登録（ワンクリック）

`setup_task_scheduler.bat` を **管理者として実行**

→ 以降、PCログイン時に自動起動します。

### 3. 状態確認

| ファイル | 何をする |
|---------|---------|
| `claim_slot.bat` | スクリプト起動（手動で起動する場合） |
| `check_status.bat` | 現在の状態・ログを確認（色分け表示） |
| `health_check.bat` | 停止していたら赤く警告 |

### 注意
- PCをスリープさせないよう設定してください
  `設定 → システム → 電源とスリープ → スリープ → なし`
- モニターの電源オフはOKです

---

## 取得成功後のチェックリスト

- [ ] SSH接続確認: `ssh -i "ssh-key-2026-06-21.key" ubuntu@<パブリックIP>`
- [ ] Security ListでSSH(ポート22)が開いているか確認
- [ ] Hermes Agentをインストール（Linux公式スクリプト）
- [ ] Grok連携設定（OAuthログイン）
- [ ] アイドル回収対策cronを設定（30分ごとにpingしてCPU使用率20%以上維持）
- [ ] Syncthing導入（skills/、profiles/、memories/を同期）
- [ ] **SSHキーペアを新しいものに差し替え**（現行キーはAIチャットに漏れているため）
- [ ] GitHubリポジトリを削除

---

## セキュリティ注意事項

- `ssh-key-2026-06-21.key`（秘密鍵）は絶対にGitにコミットしない・AIに送らない
- `oci_api_key.pem` も同様
- 公開してOKなもの: `*.pub`（公開鍵）、フィンガープリント
- このリポジトリ自体をパブリックにしてOKな理由: コード内に書かれているOCIDは識別子であり、認証情報ではないため
