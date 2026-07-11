# ORB Bot — Automated AWS Deployment

Fully hands-off: the EC2 instance starts itself before the US open, boots MT5 and
the bot, trades one session, then powers off the moment the day's outcome is final.
You get an email at every stage.

Flow: **EventBridge starts EC2 → `launch_orb.py` runs on boot → launches MT5 →
launches bot → bot trades → bot shuts the machine down when the day is done.**

Emails: `machine started`, `MT5 launched`, `bot launched`, `shutting down`.

---

## 1. One-time AWS setup

### 1a. SNS topic + email (the 4 alerts)
1. SNS → **Create topic** → Standard → name `orb-bot-alerts`.
2. **Create subscription** → Protocol *Email* → endpoint `egarg0587@gmail.com`.
3. Open the confirmation email from AWS and click **Confirm subscription**.
4. Copy the **Topic ARN** (looks like `arn:aws:sns:us-east-1:123456789012:orb-bot-alerts`).

### 1b. Let the EC2 box publish to SNS (IAM instance role)
1. IAM → Roles → create a role for **EC2** (or edit the instance's existing role).
2. Attach an inline policy:
   ```json
   { "Version": "2012-10-17",
     "Statement": [{ "Effect": "Allow", "Action": "sns:Publish",
       "Resource": "arn:aws:sns:REGION:ACCOUNT:orb-bot-alerts" }] }
   ```
3. Attach the role to your EC2 instance (Actions → Security → Modify IAM role).
   *(boto3 on the box then authenticates automatically — no access keys needed.)*

### 1c. Auto-START the instance before the open (DST-proof)
Use **EventBridge Scheduler** (not a plain rule — Scheduler supports time zones):
1. EventBridge → **Schedules** → Create schedule.
2. Recurring, **cron**: `cron(0 9 ? * MON-FRI *)`  → 9:00 AM.
3. **Time zone: `America/New_York`** ← this is the DST fix. 9:00 New York is always
   30 min before the 9:30 open, summer or winter — you never touch it again.
4. Target: **EC2 → StartInstances** (templated target); set your instance ID.
5. Let it create the execution IAM role automatically.

*(Shutdown is handled by the bot itself — no stop schedule needed.)*

### 1d. Confirm instance stops (not terminates) on OS shutdown
EC2 → Instance → Actions → Instance settings → **Shutdown behavior = Stop**
(default for EBS instances). The bot runs `shutdown /s`, which then *stops* the
instance (billing stops, EBS/state persists).

---

## 2. One-time Windows setup (on the server)

### 2a. MT5 auto-login
Open MT5 → File → Login → tick **Save account information / password** so the
terminal reconnects automatically after boot. Confirm `MT5_TERMINAL_PATH` in
`config.py` matches your install path.

### 2b. Python deps + topic ARN
In Git Bash (venv active):
```bash
pip install boto3
setx ORB_SNS_TOPIC_ARN "arn:aws:sns:REGION:ACCOUNT:orb-bot-alerts"
```
(Reopen the shell after `setx` so the env var is picked up.)

### 2c. Run the orchestrator on boot (Task Scheduler)
1. Task Scheduler → **Create Task** (not Basic).
2. General: **Run whether user is logged on or not**, **Run with highest privileges**.
3. Triggers: **At startup** (add a 1-min delay so networking is ready).
4. Actions → Start a program:
   - Program: `C:\Users\Administrator\projects\mt5_trading\venv\Scripts\python.exe`
   - Arguments: `launch_orb.py NDX100`
   - Start in: `C:\Users\Administrator\projects\mt5_trading`
5. Save.

---

## 3. Daily result
- ~9:00 ET: EventBridge starts the instance → email **machine started**
- Boot: MT5 launches & connects → email **MT5 launched**
- Bot starts → email **bot launched**
- Day resolves (skip @ 17:00, SL hit, or 22:55 EOD) → email **shutting down** → instance stops

You pay for ~1–7 h/day instead of 24. Skip days and early-SL days cost the least.

## Manual run (no shutdown)
For testing on any machine, run without the flag so it never powers off:
```bash
python bot_orb.py NDX100
```
Only `launch_orb.py` passes `--shutdown`.
