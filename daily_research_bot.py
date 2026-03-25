import os
import requests
from anthropic import Anthropic
from datetime import datetime, timedelta
import urllib.parse

client = Anthropic(api_key=os.environ["CLAUDE_API_KEY"])
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]

KEYWORDS = [
    "quadruped robot locomotion",
    "embodied AI robot",
    "legged robot control",
    "robot reinforcement learning"
]

# Trusted channels: research labs, universities, serious tech channels
TRUSTED_CHANNELS = {
    "UCBerkeley", "StanfordUniversity", "MIT", "CMUrobotics",
    "DeepMind", "GoogleDeepMind", "OpenAI", "ANYbotics",
    "BostonDynamics", "UnitreeRobotics", "ETH Zürich", "ETH Zurich",
    "Agility Robotics", "Figure", "1X Technologies",
    "Two Minute Papers", "Yannic Kilcher", "Lex Fridman",
    "AIFoundry Org", "Stanford Vision and Learning Lab",
    "Carnegie Mellon University", "UC San Diego", "Oxford Robotics",
    "Pieter Abbeel", "Chelsea Finn", "Sergey Levine",
    "Robot Learning", "Robotics Today", "The Robot Brains Podcast",
}

BLOCKED_KEYWORDS = ["#short", "#shorts", "shorts", "🤯", "😱", "amazing", "perfect", "viral"]

def is_quality_video(title, channel):
    title_lower = title.lower()
    # Block shorts and clickbait
    for kw in BLOCKED_KEYWORDS:
        if kw.lower() in title_lower:
            return False
    # Prefer trusted channels (soft filter — don't block unknowns entirely)
    return True

def get_channel_priority(channel):
    return 0 if channel in TRUSTED_CHANNELS else 1

def search_youtube(keyword, max_results=5):
    yesterday = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "order": "relevance",
        "publishedAfter": yesterday,
        "maxResults": max_results,
        "key": YOUTUBE_API_KEY,
        "videoDuration": "medium"  # exclude shorts (<4min)
    }
    r = requests.get(url, params=params)
    items = r.json().get("items", [])
    results = []
    for item in items:
        title = item["snippet"]["title"]
        vid_id = item["id"]["videoId"]
        channel = item["snippet"]["channelTitle"]
        if is_quality_video(title, channel):
            results.append({
                "text": f"- [{title}](https://youtube.com/watch?v={vid_id}) | _{channel}_",
                "priority": get_channel_priority(channel)
            })
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
        author_str = ", ".join(authors)
        papers.append(f"- [{title}]({link}) | {author_str}")
    return papers

def summarize_with_claude(youtube_results, arxiv_results):
    content = f"""
YouTube videos:
{chr(10).join(youtube_results)}

arXiv papers:
{chr(10).join(arxiv_results)}
"""
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

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
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

    # Sort: trusted channels first, then deduplicate
    youtube_all.sort(key=lambda x: x["priority"])
    seen = set()
    youtube_deduped = []
    for v in youtube_all:
        if v["text"] not in seen:
            seen.add(v["text"])
            youtube_deduped.append(v["text"])
    youtube_deduped = youtube_deduped[:6]

    arxiv_all = list(dict.fromkeys(arxiv_all))[:8]

    summary = summarize_with_claude(youtube_deduped, arxiv_all)

    msg = f"""🤖 *Daily Research Digest — {today}*

📊 *Summary:*
{summary}

🎥 *Latest YouTube Videos:*
{chr(10).join(youtube_deduped) if youtube_deduped else "No new videos found."}

📄 *Latest arXiv Papers:*
{chr(10).join(arxiv_all) if arxiv_all else "No new papers found."}
"""
    send_telegram(msg)
    print("Done!")

if __name__ == "__main__":
    main()
