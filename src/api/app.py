from flask import Flask, jsonify, request, g
import threading
import time
import os
import logging
from src.backend.rss_core import RSSBackend

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('rss_api')

# Initialize the Flask application
app = Flask(__name__)

# Configuration
DB_PATH = os.environ.get('RSS_DB_PATH', 'rss_aggregator.db')
FETCH_INTERVAL = int(os.environ.get('RSS_FETCH_INTERVAL', 3600))  # Default to 1 hour

# Get or create the RSS backend instance
def get_rss_backend():
    if 'rss_backend' not in g:
        g.rss_backend = RSSBackend(db_path=DB_PATH)
    return g.rss_backend

@app.teardown_appcontext
def close_rss_backend(e=None):
    # Nothing to close currently as SQLite connections are opened and closed per request
    pass

# Background feed fetcher
def background_feed_fetcher():
    """Background thread function to periodically fetch all feeds."""
    rss_backend = RSSBackend(db_path=DB_PATH)
    logger.info("Background feed fetcher started")
    
    while True:
        try:
            logger.info("Starting feed update cycle")
            rss_backend.fetch_all_feeds()
            logger.info("Feed update cycle completed")
        except Exception as e:
            logger.error(f"Error in background feed fetcher: {str(e)}")
        
        # Sleep until the next update cycle
        time.sleep(FETCH_INTERVAL)

# Start the background fetcher thread when the app starts
@app.before_first_request
def start_background_tasks():
    thread = threading.Thread(target=background_feed_fetcher)
    thread.daemon = True  # The thread will exit when the main process exits
    thread.start()
    logger.info("Background feed fetcher thread started")

# API Routes
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint for container orchestration."""
    return jsonify({"status": "healthy"})

@app.route('/api/feeds', methods=['GET'])
def get_feeds():
    """Get all feeds."""
    rss = get_rss_backend()
    feeds = rss.get_feeds()
    return jsonify(feeds)

@app.route('/api/feeds', methods=['POST'])
def add_feed():
    """Add a new feed."""
    data = request.json
    if not data or 'url' not in data:
        return jsonify({"error": "URL is required"}), 400
    
    rss = get_rss_backend()
    success, message = rss.add_feed(data['url'])
    
    if success:
        return jsonify({"message": message}), 201
    else:
        return jsonify({"error": message}), 400

@app.route('/api/feeds/<int:feed_id>', methods=['DELETE'])
def remove_feed(feed_id):
    """Remove a feed."""
    rss = get_rss_backend()
    delete_articles = request.args.get('delete_articles', 'true').lower() == 'true'
    success = rss.remove_feed(feed_id, delete_articles)
    
    if success:
        return jsonify({"message": "Feed removed successfully"}), 200
    else:
        return jsonify({"error": "Failed to remove feed"}), 400

@app.route('/api/articles', methods=['GET'])
def get_articles():
    """Get articles with filtering options."""
    rss = get_rss_backend()
    
    # Parse query parameters
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))
    feed_id = request.args.get('feed_id')
    if feed_id:
        feed_id = int(feed_id)
    
    read = request.args.get('read')
    if read is not None:
        read = read.lower() == 'true'
    
    sort_by = request.args.get('sort_by', 'published_at')
    sort_order = request.args.get('sort_order', 'DESC')
    
    articles = rss.get_articles(
        limit=limit,
        offset=offset,
        feed_id=feed_id,
        read=read,
        sort_by=sort_by,
        sort_order=sort_order
    )
    
    return jsonify(articles)

@app.route('/api/articles/<int:article_id>/read', methods=['PUT'])
def mark_article_read(article_id):
    """Mark an article as read."""
    rss = get_rss_backend()
    data = request.json or {}
    read = data.get('read', True)
    
    success = rss.mark_article_read(article_id, read)
    
    if success:
        return jsonify({"message": f"Article marked as {'read' if read else 'unread'}"})
    else:
        return jsonify({"error": "Failed to update article"}), 400

@app.route('/api/articles/<int:article_id>/feedback', methods=['POST'])
def record_feedback(article_id):
    """Record user feedback for an article."""
    rss = get_rss_backend()
    data = request.json
    
    if not data or 'positive' not in data:
        return jsonify({"error": "Feedback value is required"}), 400
    
    positive = bool(data['positive'])
    success = rss.record_feedback(article_id, positive)
    
    if success:
        return jsonify({"message": "Feedback recorded"})
    else:
        return jsonify({"error": "Failed to record feedback"}), 400

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get overall statistics about feeds and articles."""
    rss = get_rss_backend()
    stats = rss.get_feed_stats()
    return jsonify(stats)

@app.route('/api/refresh', methods=['POST'])
def refresh_feeds():
    """Manually trigger a refresh of all feeds."""
    rss = get_rss_backend()
    thread = threading.Thread(target=rss.fetch_all_feeds)
    thread.daemon = True
    thread.start()
    return jsonify({"message": "Feed refresh started"})

if __name__ == '__main__':
    # Start the Flask app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
