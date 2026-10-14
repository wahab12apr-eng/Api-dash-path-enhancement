from app import fetch_news


articles, error = fetch_news("AI", page_size=5)

if error:
    print("Error:", error)
else:
    print(f"Fetched {len(articles)} articles:")
    for a in articles:
        print("-", a["title"])
