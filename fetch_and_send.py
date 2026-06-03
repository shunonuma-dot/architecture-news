"""
建築ニュース自動配信スクリプト
RSS取得 → Claude APIで要約 → Gmailで送信
"""

import os
import smtplib
import feedparser
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone
import anthropic
import time

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GMAIL_USER       = os.environ["GMAIL_USER"]
GMAIL_APP_PASS   = os.environ["GMAIL_APP_PASS"]
TO_EMAIL         = os.environ["TO_EMAIL"]

MAX_ARTICLES = 5

RSS_FEEDS = [
    {"name": "Dezeen",        "url": "https://www.dezeen.com/feed/"},
    {"name": "ArchDaily",     "url": "https://www.archdaily.com/feed"},
    {"name": "Architectural Record", "url": "https://www.architecturalrecord.com/rss/news"},
]

def fetch_recent_articles():
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    articles = []
    for feed_info in RSS_FEEDS:
        feed = feedparser.parse(feed_info["url"])
        for entry in feed.entries:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            if published and published < since:
                continue
            articles.append({
                "source":  feed_info["name"],
                "title":   entry.get("title", "タイトル不明"),
                "link":    entry.get("link", ""),
                "summary": entry.get("summary", entry.get("description", ""))[:1000],
                "published": published.strftime("%Y-%m-%d %H:%M UTC") if published else "不明",
            })
        if len(articles) >= MAX_ARTICLES * 2:
            break
    return articles[:MAX_ARTICLES]

def summarize_article(client, article):
    prompt = f"""以下の建築ニュース記事を日本語で簡潔に3行で要約してください。
専門用語はそのまま使い、重要なポイントを押さえてください。

【タイトル】{article['title']}
【本文抜粋】{article['summary']}

3行の要約のみ返してください。"""
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text

def build_email_html(articles_with_summaries):
    today = datetime.now().strftime("%Y年%m月%d日")
    items_html = ""
    for i, item in enumerate(articles_with_summaries, 1):
        items_html += f"""
        <div style="margin-bottom:28px; padding:20px; background:#f9f9f7;
                    border-left:4px solid #8B6914; border-radius:4px;">
          <div style="font-size:12px; color:#888; margin-bottom:6px;">
            {item['source']} · {item['published']}
          </div>
          <h2 style="font-size:16px; margin:0 0 10px; color:#222;">
            <a href="{item['link']}" style="color:#8B6914; text-decoration:none;">
              {item['title']}
            </a>
          </h2>
          <p style="font-size:14px; line-height:1.7; color:#444; margin:0; white-space:pre-line;">
            {item['summary_ja']}
          </p>
        </div>"""
    return f"""<!DOCTYPE html>
<html lang="ja">
<head><meta charset="UTF-8"></head>
<body style="font-family:'Helvetica Neue',Arial,sans-serif; max-width:640px;
             margin:0 auto; padding:20px; color:#333;">
  <div style="background:#222; color:#fff; padding:20px 24px; border-radius:6px 6px 0 0;">
    <h1 style="margin:0; font-size:20px;">🏛 建築ニュース日刊ダイジェスト</h1>
    <p style="margin:6px 0 0; font-size:13px; color:#ccc;">{today} · AI要約版</p>
  </div>
  <div style="padding:20px 0;">
    {items_html}
  </div>
  <p style="font-size:11px; color:#aaa; text-align:center; margin-top:20px;">
    このメールは GitHub Actions + Claude API により自動生成されています
  </p>
</body>
</html>"""

def send_email(html_body):
    today = datetime.now().strftime("%Y/%m/%d")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🏛 建築ニュースダイジェスト {today}"
    msg["From"]    = GMAIL_USER
    msg["To"]      = TO_EMAIL
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASS)
        server.sendmail(GMAIL_USER, TO_EMAIL, msg.as_string())
    print(f"✅ メール送信完了 → {TO_EMAIL}")

def main():
    print("📡 RSS取得中...")
    articles = fetch_recent_articles()
    if not articles:
        print("⚠️ 過去24時間の新着記事が見つかりませんでした。")
        return
    print(f"✅ {len(articles)}件の記事を取得")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    articles_with_summaries = []
    for i, article in enumerate(articles, 1):
        print(f"🤖 要約中 ({i}/{len(articles)}): {article['title'][:50]}...")
        article["summary_ja"] = summarize_article(client, article)
        articles_with_summaries.append(article)
        time.sleep(0.5)
    print("📧 メール送信中...")
    html = build_email_html(articles_with_summaries)
    send_email(html)

if __name__ == "__main__":
    main()
