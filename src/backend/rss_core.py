import sqlite3
import feedparser
import time
import logging
import datetime
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from contextlib import closing

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('rss_backend')

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
            
            # Create articles table
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
                published_at TIMESTAMP,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                read BOOLEAN DEFAULT 0,
                FOREIGN KEY (feed_id) REFERENCES feeds (id)
            )
            ''')
            
            # Create indices for performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_feed_id ON articles (feed_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles (published_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_read ON articles (read)')
            
            # Create user_feedback table for future AI ranking
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL,
                feedback INTEGER NOT NULL, -- 1 for positive, -1 for negative
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (article_id) REFERENCES articles (id)
            )
            ''')
            
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
            
            # Parse the feed
            feed_data = feedparser.parse(feed_url)
            new_article_count = 0
            
            for entry in feed_data.entries:
                # Create a unique ID for this article if it doesn't have one
                guid = entry.get('id', None) or entry.get('link', None)
                if not guid:
                    # Create a hash of the title and published date as a fallback GUID
                    guid = hashlib.md5(f"{entry.get('title', '')}{entry.get('published', '')}".encode()).hexdigest()
                
                # Parse the published date
                published_at = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published_at = time.mktime(entry.published_parsed)
                
                # Extract the content
                content = ''
                if hasattr(entry, 'content'):
                    content = entry.content[0].value
                elif hasattr(entry, 'summary'):
                    content = entry.summary
                
                article = {
                    'feed_id': feed_id,
                    'guid': guid,
                    'title': entry.get('title', 'No title'),
                    'url': entry.get('link', ''),
                    'description': entry.get('summary', ''),
                    'content': content,
                    'author': entry.get('author', ''),
                    'published_at': published_at
                }
                
                try:
                    with closing(self.get_db_connection()) as conn:
                        cursor = conn.cursor()
                        cursor.execute('''
                            INSERT INTO articles 
                            (feed_id, guid, title, url, description, content, author, published_at) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                article['feed_id'], 
                                article['guid'], 
                                article['title'], 
                                article['url'], 
                                article['description'], 
                                article['content'], 
                                article['author'], 
                                article['published_at']
                            )
                        )
                        conn.commit()
                        new_article_count += 1
                except sqlite3.IntegrityError:
                    # Article already exists, skip it
                    pass
            
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
