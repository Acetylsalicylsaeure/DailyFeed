import sqlite3
import feedparser
import time
import logging
import datetime
import hashlib
import re
from typing import List, Dict, Any, Optional, Tuple
from contextlib import closing

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('rss_backend')


def extract_published_date(entry) -> Optional[float]:
    """
    Extract publication date from feed entry with fallbacks for different formats.
    Returns timestamp as float or None if no valid date found.
    """
    # First try the parsed date fields that feedparser provides
    for date_field in ['published_parsed', 'updated_parsed', 'created_parsed', 'modified_parsed']:
        if hasattr(entry, date_field) and getattr(entry, date_field):
            return time.mktime(getattr(entry, date_field))
    
    # If no parsed fields, try the string date fields
    try:
        from dateutil import parser as date_parser
        
        for date_field in ['published', 'updated', 'created', 'modified', 'date']:
            if hasattr(entry, date_field) and getattr(entry, date_field):
                date_str = getattr(entry, date_field)
                parsed_date = date_parser.parse(date_str)
                return time.mktime(parsed_date.timetuple())
    except (ImportError, ValueError, AttributeError) as e:
        logging.debug(f"Error parsing date string: {e}")
    
    return None


def extract_content(entry) -> str:
    """
    Extract content from feed entry with fallbacks for different formats.
    """
    # Try all possible content locations
    if hasattr(entry, 'content') and entry.content:
        # Atom feeds often have content as a list of dict objects
        if isinstance(entry.content, list) and len(entry.content) > 0:
            content_item = entry.content[0]
            if isinstance(content_item, dict) and 'value' in content_item:
                return content_item['value']
            elif hasattr(content_item, 'value'):
                return content_item.value
    
    # RSS feeds often have content in content:encoded
    if hasattr(entry, 'content_encoded') and entry.content_encoded:
        return entry.content_encoded
    
    # Fallback to summary/description
    if hasattr(entry, 'summary') and entry.summary:
        return entry.summary
    
    if hasattr(entry, 'description') and entry.description:
        return entry.description
    
    return ''


def extract_image_url(entry) -> Optional[str]:
    """
    Extract an image URL from a feed entry with support for various formats.
    Returns the URL of the largest image found, or None if no image is found.
    """
    image_url = None
    max_width = 0
    
    # Try to find image in media_content
    if hasattr(entry, 'media_content') and entry.media_content:
        for media in entry.media_content:
            if isinstance(media, dict) and 'url' in media:
                # Check if media is an image
                media_type = media.get('type', '')
                if media_type.startswith('image/'):
                    width = int(media.get('width', 0))
                    if width > max_width:
                        max_width = width
                        image_url = media['url']
    
    # Try to find image in media_thumbnail
    if not image_url and hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
        for thumbnail in entry.media_thumbnail:
            if isinstance(thumbnail, dict) and 'url' in thumbnail:
                width = int(thumbnail.get('width', 0))
                if width > max_width:
                    max_width = width
                    image_url = thumbnail['url']
    
    # Try to find image in enclosures
    if not image_url and hasattr(entry, 'enclosures') and entry.enclosures:
        for enclosure in entry.enclosures:
            if isinstance(enclosure, dict) and 'type' in enclosure and enclosure['type'].startswith('image/'):
                if 'url' in enclosure:
                    image_url = enclosure['url']
                    break
    
    # Try to find image in content or group tags (like in the example)
    if not image_url:
        # Check for group tag with content elements
        if hasattr(entry, 'group') and entry.group:
            group = entry.group
            if hasattr(group, 'content'):
                contents = group.content
                if isinstance(contents, list):
                    for content in contents:
                        if hasattr(content, 'url') and hasattr(content, 'width'):
                            width = int(getattr(content, 'width', 0))
                            if width > max_width:
                                max_width = width
                                image_url = content.url
        
        # Check for direct content tags with width and url
        if not image_url and hasattr(entry, 'content'):
            if isinstance(entry.content, list):
                for content in entry.content:
                    if isinstance(content, dict) and 'url' in content and content.get('type', '').startswith('image/'):
                        width = int(content.get('width', 0))
                        if width > max_width:
                            max_width = width
                            image_url = content['url']
    
    # Direct content attribute with url
    if not image_url and hasattr(entry, 'content') and hasattr(entry.content, 'url'):
        image_url = entry.content.url
    
    # Try parsing image from HTML content as a last resort
    if not image_url:
        content = extract_content(entry)
        # Simple regex to extract image URLs from HTML content
        img_tags = re.findall(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', content)
        if img_tags:
            image_url = img_tags[0]  # Just take the first image
    
    return image_url


def generate_guid(entry) -> str:
    """
    Generate a consistent GUID for an entry that lacks one.
    """
    # Try to use the entry's id first
    if hasattr(entry, 'id') and entry.id:
        return entry.id
    
    # Next try the link
    if hasattr(entry, 'link') and entry.link:
        return entry.link
    
    # Get title using attribute access
    title = ""
    if hasattr(entry, 'title'):
        title = entry.title
    elif hasattr(entry, 'get'):
        title = entry.get('title', '')
        
    # Get content for hashing
    content = extract_content(entry)
    date_str = extract_published_date(entry) or ''
    
    # Fallback to hash of content
    hash_input = f"{title}{date_str}{content}"
    return hashlib.md5(hash_input.encode()).hexdigest()


def clean_html(html_content: str) -> str:
    """
    Basic HTML cleaning to handle common issues in feed content.
    """
    if not html_content:
        return ''
    
    # Process CDATA sections iteratively to handle nesting
    while '<![CDATA[' in html_content and ']]>' in html_content:
        html_content = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', html_content, flags=re.DOTALL)
    
    # Strip potentially dangerous scripts
    html_content = re.sub(r'<script.*?>.*?</script>', '', html_content, flags=re.DOTALL)
    
    return html_content.strip()


class RSSBackend:
    def __init__(self, db_path: str = "rss_aggregator.db"):
        """Initialize the RSS backend with a SQLite database path."""
        self.db_path = db_path
        self.setup_database()
    
    def get_db_connection(self) -> sqlite3.Connection:
        """Create a database connection with proper settings."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def setup_database(self) -> None:
        """Set up the SQLite database schema if it doesn't exist."""
        with closing(self.get_db_connection()) as conn:
            cursor = conn.cursor()
            
            # Create feeds table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS feeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                description TEXT,
                last_fetched TIMESTAMP,
                update_frequency INTEGER DEFAULT 3600,
                active BOOLEAN DEFAULT 1,
                error_count INTEGER DEFAULT 0,
                last_error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Create articles table with image_url column
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feed_id INTEGER NOT NULL,
                guid TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                description TEXT,
                content TEXT,
                author TEXT,
                image_url TEXT,
                published_at TIMESTAMP,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                read BOOLEAN DEFAULT 0,
                FOREIGN KEY (feed_id) REFERENCES feeds (id)
            )
            ''')
            
            # Check if we need to add the image_url column to an existing table
            try:
                cursor.execute('SELECT image_url FROM articles LIMIT 1')
            except sqlite3.OperationalError:
                # Column doesn't exist, add it
                cursor.execute('ALTER TABLE articles ADD COLUMN image_url TEXT')
                logging.info("Added image_url column to articles table")
            
            # Create user_feedback table for AI ranking
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL,
                feedback INTEGER NOT NULL, -- 1 for positive, -1 for negative
                clicked BOOLEAN DEFAULT 0, -- Track if the article link was clicked
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (article_id) REFERENCES articles (id)
            )
            ''')
            
            # Check if we need to add the clicked column to an existing user_feedback table
            try:
                cursor.execute('SELECT clicked FROM user_feedback LIMIT 1')
            except sqlite3.OperationalError:
                # Column doesn't exist, add it
                cursor.execute('ALTER TABLE user_feedback ADD COLUMN clicked BOOLEAN DEFAULT 0')
                logging.info("Added clicked column to user_feedback table")
            
            # Create indices for performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_feed_id ON articles (feed_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles (published_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_read ON articles (read)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_feedback_article_id ON user_feedback (article_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_feedback_article_clicked ON user_feedback (article_id, clicked)')
            
            conn.commit()    

    def add_feed(self, url: str) -> Tuple[bool, str]:
        """
        Add a new RSS feed to the database.
        Returns (success, message)
        """
        try:
            # Parse the feed to get its metadata
            feed_data = feedparser.parse(url)
            
            if hasattr(feed_data, 'bozo_exception'):
                logger.error(f"Error parsing feed {url}: {feed_data.bozo_exception}")
                return False, f"Invalid feed: {str(feed_data.bozo_exception)}"
                
            feed_info = feed_data.feed
            
            with closing(self.get_db_connection()) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO feeds (title, url, description) VALUES (?, ?, ?)',
                    (feed_info.get('title', 'Unknown'), url, feed_info.get('description', ''))
                )
                conn.commit()
                
                # Fetch articles right away
                self.fetch_feed_articles(url)
                
                return True, "Feed added successfully"
                
        except sqlite3.IntegrityError:
            return False, "Feed URL already exists"
        except Exception as e:
            logger.error(f"Error adding feed {url}: {str(e)}")
            return False, f"Error adding feed: {str(e)}"
    
    def fetch_all_feeds(self) -> None:
        """Update all active feeds in the database."""
        with closing(self.get_db_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT id, url, last_fetched, update_frequency FROM feeds WHERE active = 1'
            )
            feeds = cursor.fetchall()
            
        for feed in feeds:
            # Check if it's time to update this feed
            current_time = datetime.datetime.now().timestamp()
            last_fetched = feed['last_fetched'] or 0
            update_frequency = feed['update_frequency']
            
            if current_time - last_fetched > update_frequency:
                self.fetch_feed_articles(feed['url'])
    
    def fetch_feed_articles(self, feed_url: str) -> int:
        """
        Fetch and store articles from a specific feed.
        Returns the number of new articles.
        """
        try:
            with closing(self.get_db_connection()) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id FROM feeds WHERE url = ?', (feed_url,))
                feed = cursor.fetchone()
                
                if not feed:
                    logger.error(f"Feed not found: {feed_url}")
                    return 0
                
                feed_id = feed['id']
                
                # Update last_fetched timestamp
                cursor.execute(
                    'UPDATE feeds SET last_fetched = ?, error_count = 0, last_error = NULL WHERE id = ?',
                    (datetime.datetime.now().timestamp(), feed_id)
                )
                conn.commit()
            
            # Parse the feed with extended options
            feed_data = feedparser.parse(feed_url, sanitize_html=True)
            
            # Check for feed level errors
            if hasattr(feed_data, 'bozo') and feed_data.bozo and hasattr(feed_data, 'bozo_exception'):
                logger.warning(f"Warning when parsing {feed_url}: {feed_data.bozo_exception}")
            
            new_article_count = 0
            
            # Get feed title for updating if needed
            if hasattr(feed_data, 'feed') and hasattr(feed_data.feed, 'title'):
                with closing(self.get_db_connection()) as conn:
                    cursor = conn.cursor()
                    cursor.execute('UPDATE feeds SET title = ? WHERE id = ?', 
                                (feed_data.feed.title, feed_id))
                    conn.commit()
            
            for entry in feed_data.entries:
                # Extract GUID or generate one
                guid = generate_guid(entry)
                
                # Extract publication date
                published_at = extract_published_date(entry)
                
                # If no date is found, use current time
                if published_at is None:
                    published_at = datetime.datetime.now().timestamp()
                
                # Extract title with fallback
                title = entry.get('title', 'No title')
                
                # Extract link with fallback
                link = entry.get('link', '')
                
                # Extract content with rich fallback mechanism
                content = extract_content(entry)
                content = clean_html(content)
                
                # Extract summary (may be different from content)
                summary = ''
                if hasattr(entry, 'summary'):
                    summary = clean_html(entry.summary)
                elif content:
                    # Use a truncated version of content if no summary
                    summary = content[:500] + ('...' if len(content) > 500 else '')
                
                # Extract author with fallbacks
                author = entry.get('author', '')
                if not author and hasattr(entry, 'authors') and entry.authors:
                    author = entry.authors[0].name if hasattr(entry.authors[0], 'name') else ''
                
                # Extract image URL
                image_url = extract_image_url(entry)
                
                article = {
                    'feed_id': feed_id,
                    'guid': guid,
                    'title': title,
                    'url': link,
                    'description': summary,
                    'content': content,
                    'author': author,
                    'image_url': image_url,
                    'published_at': published_at
                }
                
                try:
                    with closing(self.get_db_connection()) as conn:
                        cursor = conn.cursor()
                        cursor.execute('''
                            INSERT INTO articles 
                            (feed_id, guid, title, url, description, content, author, image_url, published_at) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                article['feed_id'], 
                                article['guid'], 
                                article['title'], 
                                article['url'], 
                                article['description'], 
                                article['content'], 
                                article['author'],
                                article['image_url'],
                                article['published_at']
                            )
                        )
                        conn.commit()
                        new_article_count += 1
                except sqlite3.IntegrityError:
                    # Article already exists, check if we need to update the image_url
                    if image_url:
                        with closing(self.get_db_connection()) as conn:
                            cursor = conn.cursor()
                            cursor.execute('''
                                UPDATE articles SET image_url = ?
                                WHERE guid = ? AND (image_url IS NULL OR image_url = '')
                                ''', (image_url, guid))
                            conn.commit()
                
            logger.info(f"Added {new_article_count} new articles from {feed_url}")
            return new_article_count
            
        except Exception as e:
            logger.error(f"Error fetching feed {feed_url}: {str(e)}")
            
            # Update error count and last error message
            with closing(self.get_db_connection()) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE feeds SET error_count = error_count + 1, last_error = ? WHERE url = ?',
                    (str(e), feed_url)
                )
                conn.commit()
            
            return 0
    
    def get_feeds(self) -> List[Dict[str, Any]]:
        """Get all feeds with their metadata."""
        with closing(self.get_db_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT f.*, 
                       COUNT(a.id) as article_count,
                       MAX(a.published_at) as latest_article_date
                FROM feeds f
                LEFT JOIN articles a ON f.id = a.feed_id
                GROUP BY f.id
                ORDER BY f.title
            ''')
            feeds = [dict(feed) for feed in cursor.fetchall()]
            return feeds
    
    def get_articles(self, 
                    limit: int = 50, 
                    offset: int = 0, 
                    feed_id: Optional[int] = None, 
                    read: Optional[bool] = None,
                    sort_by: str = "published_at",
                    sort_order: str = "DESC") -> List[Dict[str, Any]]:
        """
        Get articles with filtering and sorting options.
        """
        query = '''
            SELECT a.*, f.title as feed_title 
            FROM articles a
            JOIN feeds f ON a.feed_id = f.id
            WHERE 1=1
        '''
        params = []
        
        if feed_id is not None:
            query += " AND a.feed_id = ?"
            params.append(feed_id)
        
        if read is not None:
            query += " AND a.read = ?"
            params.append(1 if read else 0)
        
        # Validate sort_by to prevent SQL injection
        valid_sort_columns = ["published_at", "fetched_at", "title"]
        if sort_by not in valid_sort_columns:
            sort_by = "published_at"
        
        # Validate sort_order to prevent SQL injection
        sort_order = "DESC" if sort_order.upper() == "DESC" else "ASC"
        
        query += f" ORDER BY a.{sort_by} {sort_order}"
        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        with closing(self.get_db_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            articles = [dict(article) for article in cursor.fetchall()]
            return articles
    
    def mark_article_read(self, article_id: int, read: bool = True) -> bool:
        """Mark an article as read or unread."""
        try:
            with closing(self.get_db_connection()) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE articles SET read = ? WHERE id = ?',
                    (1 if read else 0, article_id)
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error marking article {article_id} as read={read}: {str(e)}")
            return False
    
    def record_feedback(self, article_id: int, positive: bool) -> bool:
        """Record user feedback for an article."""
        try:
            with closing(self.get_db_connection()) as conn:
                cursor = conn.cursor()
                
                # First check if the article exists
                cursor.execute('SELECT id FROM articles WHERE id = ?', (article_id,))
                if cursor.fetchone() is None:
                    logger.warning(f"Attempted to record feedback for non-existent article ID: {article_id}")
                    return False
                    
                cursor.execute(
                    'INSERT INTO user_feedback (article_id, feedback) VALUES (?, ?)',
                    (article_id, 1 if positive else -1)
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error recording feedback for article {article_id}: {str(e)}")
            return False    

    def remove_feed(self, feed_id: int, delete_articles: bool = True) -> bool:
        """Remove a feed and optionally its articles."""
        try:
            with closing(self.get_db_connection()) as conn:
                conn.execute('BEGIN TRANSACTION')
                cursor = conn.cursor()
                
                if delete_articles:
                    # Delete all related user feedback first to maintain foreign key integrity
                    cursor.execute('''
                        DELETE FROM user_feedback 
                        WHERE article_id IN (SELECT id FROM articles WHERE feed_id = ?)
                    ''', (feed_id,))
                    
                    # Then delete all articles
                    cursor.execute('DELETE FROM articles WHERE feed_id = ?', (feed_id,))
                
                # Delete the feed
                cursor.execute('DELETE FROM feeds WHERE id = ?', (feed_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error removing feed {feed_id}: {str(e)}")
            return False
    
    def get_feed_stats(self) -> Dict[str, Any]:
        """Get overall statistics about feeds and articles."""
        with closing(self.get_db_connection()) as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            # Get total feed count
            cursor.execute('SELECT COUNT(*) FROM feeds')
            stats['total_feeds'] = cursor.fetchone()[0]
            
            # Get active feed count
            cursor.execute('SELECT COUNT(*) FROM feeds WHERE active = 1')
            stats['active_feeds'] = cursor.fetchone()[0]
            
            # Get total article count
            cursor.execute('SELECT COUNT(*) FROM articles')
            stats['total_articles'] = cursor.fetchone()[0]
            
            # Get unread article count
            cursor.execute('SELECT COUNT(*) FROM articles WHERE read = 0')
            stats['unread_articles'] = cursor.fetchone()[0]
            
            # Get article count in last 24 hours
            cursor.execute(
                'SELECT COUNT(*) FROM articles WHERE published_at > ?',
                (datetime.datetime.now().timestamp() - 86400,)
            )
            stats['new_articles_24h'] = cursor.fetchone()[0]
            
            return stats

    def record_click(self, article_id: int) -> bool:
        """Record when a user clicks on an article link."""
        try:
            with closing(self.get_db_connection()) as conn:
                cursor = conn.cursor()
                
                # First check if the article exists
                cursor.execute('SELECT id FROM articles WHERE id = ?', (article_id,))
                if cursor.fetchone() is None:
                    logger.warning(f"Attempted to record click for non-existent article ID: {article_id}")
                    return False
                
                # Check if there's already a feedback record for this article
                cursor.execute(
                    'SELECT id FROM user_feedback WHERE article_id = ? LIMIT 1',
                    (article_id,)
                )
                existing = cursor.fetchone()
                
                if existing:
                    # Update existing record
                    cursor.execute(
                        'UPDATE user_feedback SET clicked = 1, timestamp = CURRENT_TIMESTAMP WHERE id = ?',
                        (existing[0],)
                    )
                else:
                    # Insert new record
                    cursor.execute(
                        'INSERT INTO user_feedback (article_id, feedback, clicked) VALUES (?, 0, 1)',
                        (article_id,)
                    )
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error recording click for article {article_id}: {str(e)}")
            return False

    def get_article_interactions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get articles with their interaction statistics for AI training."""
        with closing(self.get_db_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    a.id, a.title, a.description, a.published_at,
                    a.read,
                    COUNT(DISTINCT CASE WHEN uf.feedback = 1 THEN uf.id END) AS positive_count,
                    COUNT(DISTINCT CASE WHEN uf.feedback = -1 THEN uf.id END) AS negative_count,
                    COUNT(DISTINCT CASE WHEN uf.clicked = 1 THEN uf.id END) AS click_count
                FROM 
                    articles a
                LEFT JOIN 
                    user_feedback uf ON a.id = uf.article_id
                GROUP BY 
                    a.id
                ORDER BY 
                    a.published_at DESC
                LIMIT ?
            ''', (limit,))
            
            interactions = [dict(row) for row in cursor.fetchall()]
            return interactions


# Example usage
if __name__ == "__main__":
    rss = RSSBackend()
    
    # Add some example feeds
    rss.add_feed("https://news.ycombinator.com/rss")
    rss.add_feed("https://feeds.feedburner.com/TechCrunch")
    
    # Fetch all feeds
    rss.fetch_all_feeds()
    
    # Get latest articles
    articles = rss.get_articles(limit=10)
    for article in articles:
        print(f"{article['feed_title']}: {article['title']}")
