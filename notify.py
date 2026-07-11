"""
Email notifications via AWS SNS.

Setup (one-time, in AWS):
  1. Create an SNS topic (e.g. "orb-bot-alerts").
  2. Subscribe egarg0587@gmail.com to it (confirm the email once).
  3. Give the EC2 instance's IAM role sns:Publish on that topic.
  4. Set the topic ARN on the box as an env var:
       setx ORB_SNS_TOPIC_ARN "arn:aws:sns:REGION:ACCOUNT:orb-bot-alerts"

If the ARN isn't set or boto3/AWS fails, notify() logs a warning and
never raises — notifications must never crash the bot.
"""

import os
import logging

_log = logging.getLogger("orb")
TOPIC_ARN = os.environ.get("ORB_SNS_TOPIC_ARN", "")


def notify(subject: str, message: str) -> None:
    if not TOPIC_ARN:
        _log.warning(f"notify skipped (no ORB_SNS_TOPIC_ARN) | {subject}")
        return
    try:
        import boto3
        region = TOPIC_ARN.split(":")[3]        # arn:aws:sns:REGION:acct:name
        boto3.client("sns", region_name=region).publish(
            TopicArn=TOPIC_ARN,
            Subject=subject[:100],          # SNS subject max 100 chars
            Message=message,
        )
        _log.info(f"email sent | {subject}")
    except Exception as e:
        _log.warning(f"notify failed: {e} | {subject}")
