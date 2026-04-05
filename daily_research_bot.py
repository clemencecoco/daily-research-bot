import os
import json
import requests
from anthropic import Anthropic
from datetime import datetime, timedelta
import urllib.parse

client = Anthropic(api_key=os.environ["CLAUDE_API_KEY"])
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO = os.environ["GITHUB_REPO"]  # e.g. "clemencecoco/daily-research-bot"

KEYWORDS = [
    "quadruped robot locomotion",
    "embodied AI robot",
    "legged robot control",
    "robot reinforcement learning"
]

TRUSTED_CHANNELS = {
    "UCBerkeley", "StanfordUniversity", "MIT", "CMUrobotics",
    "DeepMind", "GoogleDeepMind", "OpenAI", "ANYbotics",
    "BostonDynamics", "UnitreeRobotics", "ETH Zürich", "ETH Zurich",
    "Agility Robotics", "Figure", "1X Technologies",
    "Two Minute Papers", "Yannic Kilcher", "Lex Fridman",
    "AIFoundry Org", "Stanford Vision and Learning Lab",
    "Carnegie Mellon University", "UC San Diego", "Oxford Robotics",
    "Robot Learning", "Robotics Today", "The Robot Brains Podcast",
}

BLOCKED_KEYWORDS = ["#short", "#shorts", "shorts", "🤯", "😱", "amazing", "perfect", "viral"]

def is_quality_video(title, channel):
    title_lower = title.lower()
    for kw in BLOCKED_KEYWORDS:
        if kw.lower() in title_lower:
            return False
    return True

def get_channel_priority(channel):
    return 0 if channel in TRUSTED_CHANNELS else 1

def search_youtube(keyword, max_results=5, min_views=5000):
    yesterday = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
    search_url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "order": "relevance",
        "publishedAfter": yesterday,
        "maxResults": max_results,
        "key": YOUTUBE_API_KEY,
        "videoDuration": "medium"
    }
    r = requests.get(search_url, params=params)
    items = r.json().get("items", [])

    video_ids = [item["id"]["videoId"] for item in items]
    if not video_ids:
        return []

    stats_r = requests.get("https://www.googleapis.com/youtube/v3/videos", params={
        "part": "statistics",
        "id": ",".join(video_ids),
        "key": YOUTUBE_API_KEY
    })
    stats_map = {
        v["id"]: int(v["statistics"].get("viewCount", 0))
        for v in stats_r.json().get("items", [])
    }

    results = []
    for item in items:
        title = item["snippet"]["title"]
        vid_id = item["id"]["videoId"]
        channel = item["snippet"]["channelTitle"]
        views = stats_map.get(vid_id, 0)
        if views < min_views or not is_quality_video(title, channel):
            continue
        results.append({
            "title": title,
            "url": f"https://youtube.com/watch?v={vid_id}",
            "channel": channel,
            "views": views,
            "priority": get_channel_priority(channel)
        })

    results.sort(key=lambda x: (x["priority"], -x["views"]))
    return results

def search_arxiv(keyword, max_results=4):
    query = urllib.parse.quote(keyword)
    url = f"https://export.arxiv.org/api/query?search_query=all:{query}&sortBy=submittedDate&sortOrder=descending&max_results={max_results}"
    r = requests.get(url)
    import xml.etree.ElementTree as ET
    root = ET.fromstring(r.content)
    ns = "{http://www.w3.org/2005/Atom}"
    papers = []
    for entry in root.findall(f"{ns}entry"):
        title = entry.find(f"{ns}title").text.strip().replace("\n", " ")
        link = entry.find(f"{ns}id").text.strip()
        authors = [a.find(f"{ns}name").text for a in entry.findall(f"{ns}author")][:2]
        abstract = entry.find(f"{ns}summary").text.strip().replace("\n", " ")[:300]
        papers.append({
            "title": title,
            "url": link,
            "authors": authors,
            "abstract": abstract
        })
    return papers

def summarize_with_claude(youtube_results, arxiv_results):
    yt_text = "\n".join([f"- {v['title']} | {v['channel']}" for v in youtube_results])
    ax_text = "\n".join([f"- {p['title']} | {', '.join(p['authors'])}" for p in arxiv_results])
    content = f"YouTube videos:\n{yt_text}\n\narXiv papers:\n{ax_text}"
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": (
                "You are a research assistant specializing in quadruped robotics and embodied AI. "
                "Based on the following recent YouTube videos and arXiv papers, write a concise English summary "
                "(under 120 words) highlighting the key research trends and notable findings:\n" + content
            )
        }]
    )
    return message.content[0].text

def save_and_push_json(today, summary, youtube_results, arxiv_results):
    # Read existing data.json from GitHub
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/data.json"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    r = requests.get(api_url, headers=headers)
    if r.status_code == 200:
        import base64
        existing = json.loads(base64.b64decode(r.json()["content"]).decode())
        sha = r.json()["sha"]
    else:
        existing = []
        sha = None

    # Add today's entry
    entry = {
        "date": today,
        "summary": summary,
        "videos": youtube_results[:6],
        "papers": arxiv_results[:8]
    }

    # Remove duplicate date if exists
    existing = [e for e in existing if e["date"] != today]
    existing.insert(0, entry)
    existing = existing[:60]  # keep last 60 days

    import base64
    new_content = base64.b64encode(json.dumps(existing, ensure_ascii=False, indent=2).encode()).decode()

    payload = {
        "message": f"Update research digest {today}",
        "content": new_content
    }
    if sha:
        payload["sha"] = sha

    requests.put(api_url, headers=headers, json=payload)
    print("data.json pushed to GitHub.")

def send_telegram(today, summary, youtube_results, arxiv_results):
    yt_lines = [f"- [{v['title']}]({v['url']}) | _{v['channel']}_ | 👁 {v['views']:,}" for v in youtube_results[:6]]
    ax_lines = [f"- [{p['title']}]({p['url']}) | {', '.join(p['authors'])}" for p in arxiv_results[:8]]

    msg = f"""🤖 *Daily Research Digest — {today}*

📊 *Summary:*
{summary}

🎥 *Latest YouTube Videos:*
{chr(10).join(yt_lines) if yt_lines else "No new videos found."}

📄 *Latest arXiv Papers:*
{chr(10).join(ax_lines) if ax_lines else "No new papers found."}
"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    })

def main():
    today = datetime.utcnow().strftime('%Y-%m-%d')
    youtube_all = []
    arxiv_all = []

    for kw in KEYWORDS:
        youtube_all += search_youtube(kw)
        arxiv_all += search_arxiv(kw)

    # Deduplicate
    seen = set()
    youtube_deduped = []
    for v in youtube_all:
        if v["url"] not in seen:
            seen.add(v["url"])
            youtube_deduped.append(v)

    seen = set()
    arxiv_deduped = []
    for p in arxiv_all:
        if p["url"] not in seen:
            seen.add(p["url"])
            arxiv_deduped.append(p)

    summary = summarize_with_claude(youtube_deduped[:6], arxiv_deduped[:8])
    save_and_push_json(today, summary, youtube_deduped[:6], arxiv_deduped[:8])
    send_telegram(today, summary, youtube_deduped[:6], arxiv_deduped[:8])
    print("Done!")

if __name__ == "__main__":
    main()
