# Backend Collectors Module

## Purpose
Fetches RSS entries from configured sources, validates URL schemes, parses feed structures, and scrapes full-text HTML content.

## Contained Modules
- `collector.py`: RSS feed fetcher and source iteration.
- `scraper.py`: Full-text web scraper (`BeautifulSoup`, `requests`).

## Dependencies
- `feedparser`, `requests`, `beautifulsoup4`, `backend.database.jarvis_db`.

## Entry Points
- `collect_all()`: Runs collection cycle across all enabled RSS sources.
- `scrape_url(url)`: Scrapes article HTML text body.

## Important Files
- [`collector.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/collectors/collector.py)
- [`scraper.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/collectors/scraper.py)
