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

def search_youtube(keyword, max_results=2):
    yesterday = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "order": "date",
        "publishedAfter": yesterday,
        "maxResults": max_results,
        "key": YOUTUBE_API_KEY
    }
    r = requests.get(url, params=params)
    items = r.json().get("items", [])
    results = []
    for item in items:
        title = item["snippet"]["title"]
        vid_id = item["id"]["videoId"]
        channel = item["snippet"]["channelTitle"]
        results.append(f"- [{title}](https://youtube.com/watch?v={vid_id}) | {channel}")
    return results

def search_arxiv(keyword, max_results=3):
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
YouTube最新视频：
{chr(10).join(youtube_results)}

arXiv最新论文：
{chr(10).join(arxiv_results)}
"""
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": f"你是一个四足机器人和Embodied AI研究助手。请用中文简洁总结以下内容的研究趋势和亮点，100字以内：\n{content}"
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
    
    # 去重
    youtube_all = list(dict.fromkeys(youtube_all))[:6]
    arxiv_all = list(dict.fromkeys(arxiv_all))[:8]
    
    summary = summarize_with_claude(youtube_all, arxiv_all)
    
    msg = f"""🤖 *每日研究简报 {today}*

📊 *Claude总结：*
{summary}

🎥 *最新YouTube视频：*
{chr(10).join(youtube_all) if youtube_all else "暂无新视频"}

📄 *最新arXiv论文：*
{chr(10).join(arxiv_all) if arxiv_all else "暂无新论文"}
"""
    send_telegram(msg)
    print("发送成功！")

if __name__ == "__main__":
    main()
