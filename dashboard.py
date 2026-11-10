
import sqlite3
from datetime import datetime
from pathlib import Path

import streamlit as st


# CONFIGURATION

st.set_page_config(
    page_title="AI Social Media Manager",
    page_icon="📱",
    layout="wide"
)

DATABASE = Path(__file__).parent / "posts.db"

POST_STATUSES = [
    "Review Required",
    "Draft",
    "Ready",
    "Published",
    "Failed"
]


# DATABASE FUNCTIONS

def get_connection():
    return sqlite3.connect(DATABASE)


def setup_database():
    with get_connection() as db:
        columns = [
            row[1] for row in
            db.execute("PRAGMA table_info(posts)").fetchall()
        ]

        if not columns:
            st.error("Posts table nahi mili. Pehle AI Agent run karein.")
            st.stop()

        if "status" not in columns:
            db.execute("""
                ALTER TABLE posts
                ADD COLUMN status TEXT DEFAULT 'Review Required'
            """)


def get_posts():
    with get_connection() as db:
        return db.execute("""
            SELECT id, category, content, created_at, slot,
                   post_date, run_type, status
            FROM posts
            ORDER BY id DESC
        """).fetchall()


def delete_post(post_id):
    with get_connection() as db:
        db.execute(
            "DELETE FROM posts WHERE id = ?",
            (post_id,)
        )


def update_post(post_id, new_content):
    with get_connection() as db:
        db.execute(
            "UPDATE posts SET content = ? WHERE id = ?",
            (new_content, post_id)
        )


def update_status(post_id, new_status):
    with get_connection() as db:
        db.execute(
            "UPDATE posts SET status = ? WHERE id = ?",
            (new_status, post_id)
        )


# DATABASE CHECK

if not DATABASE.exists():
    st.error("posts.db file nahi mili. Project folder check karein.")
    st.stop()

setup_database()
posts = get_posts()


# CUSTOM STYLE

st.markdown("""
<style>
.stApp {
    background-color: #262729;
    color: #f8fafc;
}

.main .block-container {
    background-color: #262729;
}

div[data-testid="stMetric"] {
    background-color: #262729;
    padding: 18px;
    border-radius: 12px;
    border: 1px solid #475569;
}

div[data-testid="stMetricLabel"] p {
    color: #cbd5e1 !important;
}

div[data-testid="stMetricValue"] {
    color: #ffffff !important;
}

.stMarkdown, .stText, label, p, h1, h2, h3 {
    color: #f8fafc;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
    background-color: #1e293b;
    border-color: #334155;
    border-radius: 12px;
}

textarea {
    background-color: #1e293b !important;
    color: #ffffff !important;
    border-color: #475569 !important;
}
</style>
""", unsafe_allow_html=True)


# HEADER

st.title("📱 AI Social Media Manager")
st.caption("Facebook Content Management Dashboard V2")

st.divider()


# SIDEBAR FILTERS

st.sidebar.title("⚙️ Filters")

run_filter = st.sidebar.selectbox(
    "Post Type",
    ["All", "Test", "Scheduled", "Legacy"]
)

categories = sorted({
    row[1] for row in posts if row[1]
})

category_filter = st.sidebar.selectbox(
    "Category",
    ["All"] + categories
)

status_filter = st.sidebar.selectbox(
    "Publication Status",
    ["All"] + POST_STATUSES
)

search = st.sidebar.text_input(
    "Search Posts",
    placeholder="Search caption or hashtag..."
)


# FILTER DATA

filtered_posts = posts

if run_filter != "All":
    filtered_posts = [
        p for p in filtered_posts
        if (p[6] or "legacy").lower() == run_filter.lower()
    ]

if category_filter != "All":
    filtered_posts = [
        p for p in filtered_posts
        if p[1] == category_filter
    ]

if status_filter != "All":
    filtered_posts = [
        p for p in filtered_posts
        if (p[7] or "Review Required") == status_filter
    ]

if search.strip():
    filtered_posts = [
        p for p in filtered_posts
        if search.lower() in (p[2] or "").lower()
    ]


# DASHBOARD METRICS

total_posts = len(posts)

test_posts = sum(1 for p in posts if p[6] == "test")
scheduled_posts = sum(1 for p in posts if p[6] == "scheduled")

review_posts = sum(
    1 for p in posts if (p[7] or "Review Required") == "Review Required"
)

published_posts = sum(
    1 for p in posts if p[7] == "Published"
)

col1, col2, col3, col4, col5 = st.columns(5)

col1.metric("Total Posts", total_posts)
col2.metric("Test Posts", test_posts)
col3.metric("Scheduled", scheduled_posts)
col4.metric("Review Required", review_posts)
col5.metric("Published", published_posts)

st.divider()


# POST HISTORY

st.subheader("📝 Post History")
st.write(f"Showing {len(filtered_posts)} posts")

if not filtered_posts:
    st.info("Abhi koi post nahi mili.")

for post in filtered_posts:

    post_id = post[0]
    category = post[1] or "Unknown"
    content = post[2] or ""
    slot = post[4] or "unknown"
    post_date = post[5] or ""
    run_type = post[6] or "legacy"
    current_status = post[7] or "Review Required"

    with st.container(border=True):

        st.markdown(f"### {category}")

        st.caption(
            f"ID: {post_id} | Slot: {slot} | "
            f"Date: {post_date} | Type: {run_type.upper()}"
        )

        st.markdown(f"**Publication Status:** {current_status}")

        edited_content = st.text_area(
            "Edit Post Content",
            value=content,
            height=180,
            key=f"post_{post_id}"
        )

        new_status = st.selectbox(
            "Change Publication Status",
            POST_STATUSES,
            index=POST_STATUSES.index(current_status)
            if current_status in POST_STATUSES else 0,
            key=f"status_{post_id}"
        )

        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("💾 Save Changes", key=f"save_{post_id}"):
                update_post(post_id, edited_content)
                st.success("Post content saved!")
                st.rerun()

        with col2:
            if st.button("🔄 Save Status", key=f"status_save_{post_id}"):
                update_status(post_id, new_status)
                st.success("Post status updated!")
                st.rerun()

        with col3:
            if st.button("🗑️ Delete Post", key=f"delete_{post_id}"):
                delete_post(post_id)
                st.success("Post deleted!")
                st.rerun()

        st.code(edited_content, language=None)


# FOOTER

st.divider()

st.caption(
    f"AI Social Media Manager | Dashboard V2 | "
    f"{datetime.now().strftime('%d-%m-%Y')}"
)
