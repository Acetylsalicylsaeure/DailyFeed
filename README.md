# DailyFeed

A resource-efficient RSS aggregation platform using SQLite for storage with a Flask-based API.

## Features

- Efficiently fetches and stores RSS feeds in SQLite
- Minimalistic API for feed management
- Background thread for automatic feed updates
- Prepared for AI-powered content ranking (user feedback storage)
- Designed to run in a single container with minimal resources

## API Endpoints

### Feeds

- `GET /api/feeds` - Get all feeds
- `POST /api/feeds` - Add a new feed (requires JSON body with `url` field)
- `DELETE /api/feeds/{feed_id}` - Remove a feed

### Articles

- `GET /api/articles` - Get articles with filters:
  - `limit` - Number of articles to return (default: 50)
  - `offset` - Pagination offset (default: 0)
  - `feed_id` - Filter by feed ID
  - `read` - Filter by read status (true/false)
  - `sort_by` - Sort field (published_at, fetched_at, title)
  - `sort_order` - Sort direction (ASC/DESC)
- `PUT /api/articles/{article_id}/read` - Mark article as read/unread
- `POST /api/articles/{article_id}/feedback` - Record user feedback

### Other

- `GET /api/stats` - Get overall statistics
- `POST /api/refresh` - Manually trigger a feed refresh
- `GET /api/health` - Health check endpoint

## Running with Docker

### Build the container

```bash
docker build -t rss-aggregator .
```

### Run the container

```bash
docker run -d \
  --name rss-aggregator \
  -p 5000:5000 \
  -v rss_data:/data \
  rss-aggregator
```

### Environment Variables

- `RSS_DB_PATH` - Path to SQLite database (default: /data/rss_aggregator.db)
- `RSS_FETCH_INTERVAL` - Interval in seconds between feed updates (default: 3600)
- `PORT` - Port to run the server on (default: 5000)

## Development

### Setup

```bash
pip install -r requirements.txt
```

### Run locally

```bash
python app.py
```

## Next Steps

1. Add a web frontend
2. Implement AI-powered content ranking
3. Add user authentication
4. Create a mobile-responsive UI
