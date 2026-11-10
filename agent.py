
import os
import sys
import time
import sqlite3
import calendar
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from urllib.request import urlopen

import feedparser
from dotenv import load_dotenv
from google import genai
from google.genai import types
from apscheduler.schedulers.blocking import BlockingScheduler


# CONFIGURATION

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError("GEMINI_API_KEY .env mein missing hai.")

client = genai.Client(api_key=API_KEY)

MODEL = "gemini-3.5-flash-lite"
TIMEZONE = ZoneInfo("Asia/Karachi")
DATABASE = "posts.db"

NEWS_RSS_URL = (
    "https://news.google.com/rss/search"
    "?q=Pakistan+latest+news&hl=en-PK&gl=PK&ceid=PK:en"
)


# DATABASE SETUP + SAFE MIGRATION

def setup_database():
    with sqlite3.connect(DATABASE) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                content TEXT,
                created_at TEXT
            )
        """)

        existing_columns = {
            row[1] for row in db.execute(
                "PRAGMA table_info(posts)"
            ).fetchall()
        }

        new_columns = {
            "slot": "TEXT DEFAULT 'unknown'",
            "post_date": "TEXT",
            "run_type": "TEXT DEFAULT 'legacy'"
        }

        for column, definition in new_columns.items():
            if column not in existing_columns:
                db.execute(
                    f"ALTER TABLE posts ADD COLUMN {column} {definition}"
                )

        # Purane records ki date preserve karein.
        db.execute("""
            UPDATE posts
            SET post_date = substr(created_at, 1, 10)
            WHERE post_date IS NULL
        """)


def save_post(category, content, slot, run_type):
    now = datetime.now(TIMEZONE)
    post_date = now.strftime("%Y-%m-%d")
    created_at = now.strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect(DATABASE) as db:
        db.execute("""
            INSERT INTO posts
            (category, content, created_at, slot, post_date, run_type)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            category,
            content,
            created_at,
            slot,
            post_date,
            run_type
        ))


def already_generated_today(slot):
    today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")

    with sqlite3.connect(DATABASE) as db:
        result = db.execute("""
            SELECT COUNT(*)
            FROM posts
            WHERE slot = ?
            AND post_date = ?
            AND run_type = 'scheduled'
        """, (slot, today)).fetchone()

    return result[0] > 0


# DAILY CATEGORY ROTATION

MORNING_CATEGORIES = [
    "Love Shayari",
    "Love",
    "Love Shayari",
    "Love"
]

AFTERNOON_CATEGORIES = [
    "Couples Goals",
    "Comedy",
    "Couples Goals",
    "Comedy"
]


def get_category(slot):
    day = datetime.now(TIMEZONE).timetuple().tm_yday
    index = (day - 1) % 4

    if slot == "morning":
        return MORNING_CATEGORIES[index]

    if slot == "afternoon":
        return AFTERNOON_CATEGORIES[index]

    return "News Update"


# NEWS COLLECTION

def get_latest_news():
    try:
        with urlopen(NEWS_RSS_URL, timeout=15) as response:
            feed = feedparser.parse(response.read())

        news_items = []
        now_utc = datetime.now(timezone.utc)

        for entry in feed.entries[:15]:
            published = entry.get("published_parsed")

            if not published:
                continue

            published_time = datetime.fromtimestamp(
                calendar.timegm(published),
                tz=timezone.utc
            )

            age_hours = (
                now_utc - published_time
            ).total_seconds() / 3600

            if age_hours > 24 or age_hours < 0:
                continue

            news_items.append({
                "title": entry.get("title", ""),
                "summary": entry.get("summary", ""),
                "link": entry.get("link", ""),
                "source": entry.get(
                    "source", {}
                ).get("title", "Google News")
            })

            if len(news_items) == 5:
                break

        return news_items

    except Exception as error:
        print("News collection error:", error)
        return []


# GEMINI CONTENT GENERATOR


def generate_content(category, news_items=None):

    if category == "News Update":

        if not news_items:
            print("Fresh news nahi mili. News post skip kar di gayi.")
            return None

        prompt = f"""
You are a responsible Pakistani Facebook news editor.

Create one accurate Roman Urdu Facebook news post.

NEWS SOURCES:
{news_items}

STRICT RULES:

1. Use only the information provided above.
2. Select ONE news story only.
3. Use the original news headline exactly as provided.
4. Never invent or change the headline.
5. Write a short Roman Urdu summary of 2 to 3 sentences.
6. Do not invent dates, names, figures or facts.
7. Mention the original publisher/source name.
8. Include the original article link exactly as provided.
9. If details are insufficient, clearly say:
   "Mazeed tafseel ke liye original report dekhein."
10. Add one engaging question.
11. Add 3 to 5 relevant hashtags.

OUTPUT FORMAT:

📰 HEADLINE:
[Original headline]

📌 KHABAR:
[Roman Urdu summary]

🔎 SOURCE:
[Original publisher name]

🔗 FULL REPORT:
[Original article link]

💬 AAP KI RAAY:
[Engagement question]

[Hashtags]

Return only the completed Facebook post.
"""

    else:

        prompt = f"""
You are an expert Pakistani Facebook content creator.

Create one original Facebook post.

Category: {category}
Audience: Pakistani men and women.
Language: Natural Roman Urdu.

Requirements:
- Attractive opening hook.
- Engaging and meaningful caption.
- Natural emoji usage.
- Suitable call to action.
- 5 relevant hashtags.
- Family-friendly content.
- Original writing, not copied poetry or captions.

Special instructions:
Love: Romantic and emotional content.
Love Shayari: Original Urdu poetry in Roman Urdu.
Couples Goals: Trust, respect and healthy relationships.
Comedy: Relatable Pakistani daily-life humour.

Return only the complete post.
"""

    for attempt in range(1, 4):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.5 if category == "News Update" else 0.8
                )
            )

            if not response.text:
                raise ValueError("Empty response from Gemini.")

            return response.text.strip()

        except Exception as error:
            print(f"Attempt {attempt}/3 failed:", error)

            if attempt < 3:
                time.sleep(attempt * 5)
            else:
                raise


# def generate_content(category, news_items=None):

#     if category == "News Update":
#         if not news_items:
#             print("Fresh news nahi mili. News post skip kar di gayi.")
#             return None

#         prompt = f"""
# You are a responsible Pakistani Facebook news editor.

# Create a short Roman Urdu Facebook news update.

# Use ONLY the following news information:
# {news_items}

# Rules:
# - Do not invent facts, dates, figures or events.
# - Do not exaggerate headlines.
# - Clearly mention the news source.
# - Include the original article link.
# - If information is uncertain, say so.
# - Write a clear headline and short summary.
# - Add a suitable question for engagement.
# - Add 3 to 5 relevant hashtags.

# Return only the Facebook post.
# """

#     else:
#         prompt = f"""
# You are an expert Pakistani Facebook content creator.

# Create one original Facebook post.

# Category: {category}
# Audience: Pakistani men and women.
# Language: Natural Roman Urdu.

# Requirements:
# - Attractive opening hook.
# - Engaging and meaningful caption.
# - Natural emoji usage.
# - Suitable call to action.
# - 5 relevant hashtags.
# - Family-friendly content.
# - Original writing, not copied poetry or captions.

# Special instructions:
# Love: Romantic and emotional content.
# Love Shayari: Original Urdu poetry in Roman Urdu.
# Couples Goals: Trust, respect and healthy relationships.
# Comedy: Relatable Pakistani daily-life humour.

# Return only the complete post.
# """

#     for attempt in range(1, 4):
#         try:
#             response = client.models.generate_content(
#                 model=MODEL,
#                 contents=prompt,
#                 config=types.GenerateContentConfig(
#                     temperature=0.8
#                 )
#             )

#             if not response.text:
#                 raise ValueError("Empty response from Gemini.")

#             return response.text.strip()

#         except Exception as error:
#             print(f"Attempt {attempt}/3 failed:", error)

#             if attempt < 3:
#                 time.sleep(attempt * 5)
#             else:
#                 raise


# CREATE AND SAVE POST

def create_daily_post(slot, run_type="scheduled"):
    now = datetime.now(TIMEZONE)
    category = get_category(slot)

    print("\n" + "=" * 50)
    print("AI FACEBOOK CONTENT MANAGER V2.2")
    print("Time:", now.strftime("%d-%m-%Y %I:%M %p"))
    print("Slot:", slot)
    print("Run type:", run_type)
    print("Category:", category)

    # Duplicate protection only for scheduled posts.
    if run_type == "scheduled":
        if already_generated_today(slot):
            print("Is slot ki scheduled post aaj pehle generate ho chuki hai.")
            print("=" * 50)
            return

    news_items = None

    if category == "News Update":
        print("Latest news collect ho rahi hai...")
        news_items = get_latest_news()

    print("Content generate ho raha hai...")

    try:
        content = generate_content(category, news_items)

        if not content:
            print("Post generate nahi hui.")
            print("=" * 50)
            return

        save_post(category, content, slot, run_type)

        print("\nGENERATED FACEBOOK POST:\n")
        print(content)

        print("\nPost database mein successfully save ho gayi.")
        print("Run type:", run_type)

    except Exception as error:
        print("Post generation failed:", error)

    print("=" * 50)


# TEST MODE

def test_agent():
    print("AI Agent testing started.")
    print("Test posts scheduled posts se alag save hongi.")

    for slot in ["morning", "afternoon", "night"]:
        create_daily_post(slot, run_type="test")


# SCHEDULER

def start_scheduler():
    scheduler = BlockingScheduler(timezone=TIMEZONE)

    jobs = [
        ("morning", 9, 0),
        ("afternoon", 15, 0),
        ("night", 21, 0)
    ]

    for slot, hour, minute in jobs:
        scheduler.add_job(
            create_daily_post,
            trigger="cron",
            args=[slot, "scheduled"],
            hour=hour,
            minute=minute,
            id=slot,
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

    print("\n" + "=" * 50)
    print("AI SOCIAL MEDIA MANAGER V2.2")
    print("Timezone: Asia/Karachi")
    print("Daily schedule:")

    for slot, hour, minute in jobs:
        print(f"{hour:02d}:{minute:02d} - {slot}")

    print("\nAgent running. Press CTRL+C to stop.")
    print("=" * 50)

    scheduler.start()


# MAIN

if __name__ == "__main__":
    setup_database()

    if "--test" in sys.argv:
        test_agent()
    else:
        start_scheduler()
