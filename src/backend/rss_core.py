import sqlite3
import feedparser
import time
import logging
import datetime
import hashlib
import re
from typing import List, Dict, Any, Optional, Tuple, Set
from contextlib import closing
import xml.etree.ElementTree as ET
import json

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
        
        # Try Dublin Core date format
        if hasattr(entry, 'dc_date'):
            date_str = entry.dc_date
            parsed_date = date_parser.parse(date_str)
            return time.mktime(parsed_date.timetuple())
            
    except (ImportError, ValueError, AttributeError) as e:
        logging.debug(f"Error parsing date string: {e}")
    
    return None


def extract_authors(entry) -> List[str]:
    """
    Extract all authors from an entry with support for various formats.
    Returns a list of author names.
    """
    authors = []
    
    # Standard author field
    if hasattr(entry, 'author') and entry.author:
        authors.append(entry.author)
    
    # Multiple authors list
    if hasattr(entry, 'authors') and entry.authors:
        for author in entry.authors:
            if isinstance(author, dict) and 'name' in author:
                authors.append(author['name'])
            elif hasattr(author, 'name'):
                authors.append(author.name)
    
    # Dublin Core creator(s)
    if hasattr(entry, 'dc_creator'):
        if isinstance(entry.dc_creator, list):
            for creator in entry.dc_creator:
                authors.append(creator)
        else:
            authors.append(entry.dc_creator)
    
    # Look for comma-separated author lists in single strings
    authors_processed = []
    for author in authors:
        if isinstance(author, str):
            # Check for common separator patterns in author lists
            if ',' in author or ' and ' in author or ';' in author:
                # Split by various possible separators
                parts = re.split(r',|\sand\s|;', author)
                authors_processed.extend([p.strip() for p in parts if p.strip()])
            else:
                authors_processed.append(author.strip())
    
    # Return deduplicated list
    if authors_processed:
        return list(dict.fromkeys(authors_processed))
    
    return authors


def extract_categories(entry) -> List[str]:
    """
    Extract all categories from an entry with support for various formats.
    Returns a list of category names.
    """
    categories = []
    
    # Standard tags/categories list
    if hasattr(entry, 'tags'):
        for tag in entry.tags:
            if isinstance(tag, dict) and 'term' in tag:
                categories.append(tag['term'])
            elif hasattr(tag, 'term'):
                categories.append(tag.term)
            elif isinstance(tag, str):
                categories.append(tag)
    
    # Regular categories
    if hasattr(entry, 'category'):
        if isinstance(entry.category, list):
            categories.extend(entry.category)
        else:
            categories.append(entry.category)
    
    if hasattr(entry, 'categories'):
        if isinstance(entry.categories, list):
            categories.extend(entry.categories)
        else:
            categories.append(entry.categories)
    
    # Dublin Core subject(s)
    if hasattr(entry, 'dc_subject'):
        if isinstance(entry.dc_subject, list):
            categories.extend(entry.dc_subject)
        else:
            categories.append(entry.dc_subject)
    
    # Return deduplicated list
    return list(dict.fromkeys([c.strip() for c in categories if c and isinstance(c, str)]))


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
    
    # Dublin Core content
    if hasattr(entry, 'dc_content') and entry.dc_content:
        return entry.dc_content
    
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


def extract_doi(entry) -> Optional[str]:
    """
    Extract DOI (Digital Object Identifier) from the entry.
    """
    # Check for DOI in specific fields
    if hasattr(entry, 'prism_doi'):
        return entry.prism_doi
    
    if hasattr(entry, 'dc_identifier'):
        identifier = entry.dc_identifier
        if isinstance(identifier, list):
            for item in identifier:
                if item.startswith('doi:'):
                    return item[4:]
        elif isinstance(identifier, str) and identifier.startswith('doi:'):
            return identifier[4:]
    
    # Try to find DOI in the link
    if hasattr(entry, 'link'):
        doi_match = re.search(r'doi\.org/([^/\s]+)', entry.link)
        if doi_match:
            return doi_match.group(1)
    
    # Try to find DOI in the content
    content = extract_content(entry)
    doi_match = re.search(r'doi\.org/([^/\s<>"\']+)', content)
    if doi_match:
        return doi_match.group(1)
    
    return None


def generate_guid(entry) -> str:
    """
    Generate a consistent GUID for an entry that lacks one.
    """
    # Try to use the entry's id first
    if hasattr(entry, 'id') and entry.id:
        return entry.id
    
    # Check for DOI
    doi = extract_doi(entry)
    if doi:
        return f"doi:{doi}"
    
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
                feed_format TEXT,  -- Store original feed format (RSS, Atom, RDF, etc.)
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Create articles table with enhanced metadata
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feed_id INTEGER NOT NULL,
                guid TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                description TEXT,
                content TEXT,
                image_url TEXT,
                published_at TIMESTAMP,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                read BOOLEAN DEFAULT 0,
                doi TEXT,  -- DOI for scientific papers
                language TEXT,  -- Language of the article
                credit TEXT,  -- Image/content credit
                raw_data TEXT,  -- Store the original entry data for debugging
                FOREIGN KEY (feed_id) REFERENCES feeds (id)
            )
            ''')
            
            # Create authors table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS authors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
            ''')
            
            # Create article_authors junction table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS article_authors (
                article_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                author_position INTEGER,  -- Order of authors
                PRIMARY KEY (article_id, author_id),
                FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE CASCADE,
                FOREIGN KEY (author_id) REFERENCES authors (id)
            )
            ''')
            
            # Create categories table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
            ''')
            
            # Create article_categories junction table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS article_categories (
                article_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                PRIMARY KEY (article_id, category_id),
                FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE CASCADE,
                FOREIGN KEY (category_id) REFERENCES categories (id)
            )
            ''')
            
            # Create user_feedback table for AI ranking
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL,
                user_id TEXT,  -- Optional user identifier
                feedback INTEGER NOT NULL, -- 1 for positive, -1 for negative
                clicked BOOLEAN DEFAULT 0, -- Track if the article link was clicked
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE CASCADE
            )
            ''')
            
            # Create settings table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Insert default settings if they don't exist
            default_settings = [
                ('update_interval', '600', 'Global feed update interval in seconds'),
                ('half_time', '86400', 'Feedback half-life in seconds (1 day)'),
                ('max_articles_per_feed', '100', 'Maximum number of articles to keep per feed'),
                ('embedding_batch_size', '10', 'Number of articles to process at once for embeddings'),
                ('ai_enabled', 'false', 'Whether AI-powered ranking is enabled'),
                ('min_feedback_for_training', '10', 'Minimum feedback entries required before AI ranking is used'),
                ('auto_cleanup_days', '30', 'Number of days to keep articles before cleanup'),
                ('auto_read', 'true', 'Automatically mark articles as read when scrolled past'),
                ('store_raw_data', 'false', 'Store raw entry data for debugging')
            ]
            
            for key, value, description in default_settings:
                cursor.execute('''
                    INSERT OR IGNORE INTO settings (key, value, description)
                    VALUES (?, ?, ?)
                ''', (key, value, description))
            
            # Create indices for performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_feed_id ON articles (feed_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles (published_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_read ON articles (read)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_article_authors_article_id ON article_authors (article_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_article_authors_author_id ON article_authors (author_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_article_categories_article_id ON article_categories (article_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_article_categories_category_id ON article_categories (category_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_feedback_article_id ON user_feedback (article_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_feedback_article_clicked ON user_feedback (article_id, clicked)')
            
            conn.commit()
            
            # Handle schema migrations for existing databases
            self._handle_schema_migrations(conn)
    
    def _handle_schema_migrations(self, conn):
        """
        Handle schema migrations for existing databases.
        Safely adds new columns and tables if they don't exist.
        """
        cursor = conn.cursor()
        
        # Check if we need to add columns to the feeds table
        try:
            cursor.execute('SELECT feed_format FROM feeds LIMIT 1')
        except sqlite3.OperationalError:
            # Column doesn't exist, add it
            cursor.execute('ALTER TABLE feeds ADD COLUMN feed_format TEXT')
            logging.info("Added feed_format column to feeds table")
        
        # Check if we need to add columns to the articles table
        for column, type_def in [
            ('doi', 'TEXT'),
            ('language', 'TEXT'),
            ('credit', 'TEXT'),
            ('raw_data', 'TEXT')
        ]:
            try:
                cursor.execute(f'SELECT {column} FROM articles LIMIT 1')
            except sqlite3.OperationalError:
                # Column doesn't exist, add it
                cursor.execute(f'ALTER TABLE articles ADD COLUMN {column} {type_def}')
                logging.info(f"Added {column} column to articles table")
        
        # Check if authors and article_authors tables exist
        try:
            cursor.execute('SELECT 1 FROM authors LIMIT 1')
        except sqlite3.OperationalError:
            # Tables don't exist, migrate author data
            logging.info("Migrating author data to new schema...")
            
            # First, create the authors table
            cursor.execute('''
            CREATE TABLE authors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
            ''')
            
            # Create article_authors junction table
            cursor.execute('''
            CREATE TABLE article_authors (
                article_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                author_position INTEGER,
                PRIMARY KEY (article_id, author_id),
                FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE CASCADE,
                FOREIGN KEY (author_id) REFERENCES authors (id)
            )
            ''')
            
            # Migrate existing author data
            cursor.execute('SELECT id, author FROM articles WHERE author IS NOT NULL AND author != ""')
            author_data = cursor.fetchall()
            
            for article in author_data:
                article_id = article['id']
                author_str = article['author']
                
                # Split multi-author strings
                author_names = []
                if ',' in author_str or ' and ' in author_str or ';' in author_str:
                    author_names = re.split(r',|\sand\s|;', author_str)
                    author_names = [name.strip() for name in author_names if name.strip()]
                else:
                    author_names = [author_str.strip()]
                
                for i, author_name in enumerate(author_names):
                    # Add author if doesn't exist
                    cursor.execute(
                        'INSERT OR IGNORE INTO authors (name) VALUES (?)',
                        (author_name,)
                    )
                    
                    # Get author ID
                    cursor.execute(
                        'SELECT id FROM authors WHERE name = ?',
                        (author_name,)
                    )
                    author_id = cursor.fetchone()['id']
                    
                    # Link author to article
                    cursor.execute(
                        'INSERT OR IGNORE INTO article_authors (article_id, author_id, author_position) VALUES (?, ?, ?)',
                        (article_id, author_id, i)
                    )
            
            # Create indices for performance
            cursor.execute('CREATE INDEX idx_article_authors_article_id ON article_authors (article_id)')
            cursor.execute('CREATE INDEX idx_article_authors_author_id ON article_authors (author_id)')
        
        # Check if categories and article_categories tables exist
        try:
            cursor.execute('SELECT 1 FROM categories LIMIT 1')
        except sqlite3.OperationalError:
            # Tables don't exist, create them
            logging.info("Creating categories tables...")
            
            # Create categories table
            cursor.execute('''
            CREATE TABLE categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
            ''')
            
            # Create article_categories junction table
            cursor.execute('''
            CREATE TABLE article_categories (
                article_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                PRIMARY KEY (article_id, category_id),
                FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE CASCADE,
                FOREIGN KEY (category_id) REFERENCES categories (id)
            )
            ''')
            
            # Create indices for performance
            cursor.execute('CREATE INDEX idx_article_categories_article_id ON article_categories (article_id)')
            cursor.execute('CREATE INDEX idx_article_categories_category_id ON article_categories (category_id)')
        
        # Add ON DELETE CASCADE to foreign keys if needed
        try:
            cursor.execute('PRAGMA foreign_key_list(user_feedback)')
            fk_list = cursor.fetchall()
            needs_migration = True
            for fk in fk_list:
                if fk['table'] == 'articles' and fk['on_delete'] == 'CASCADE':
                    needs_migration = False
                    break
            
            if needs_migration:
                logging.info("Updating foreign key constraints...")
                # Create temporary table with correct constraints
                cursor.execute('''
                CREATE TABLE user_feedback_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id INTEGER NOT NULL,
                    user_id TEXT,
                    feedback INTEGER NOT NULL,
                    clicked BOOLEAN DEFAULT 0,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE CASCADE
                )
                ''')
                
                # Copy data to new table
                cursor.execute('INSERT INTO user_feedback_new SELECT id, article_id, NULL, feedback, clicked, timestamp FROM user_feedback')
                
                # Drop old table and rename new one
                cursor.execute('DROP TABLE user_feedback')
                cursor.execute('ALTER TABLE user_feedback_new RENAME TO user_feedback')
                
                # Recreate indices
                cursor.execute('CREATE INDEX idx_user_feedback_article_id ON user_feedback (article_id)')
                cursor.execute('CREATE INDEX idx_user_feedback_article_clicked ON user_feedback (article_id, clicked)')
        except:
            # If there was an error, we'll assume this is a new database or the table doesn't exist yet
            pass
        
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
            
            # Detect feed format
            feed_format = "Unknown"
            if hasattr(feed_data, 'version'):
                feed_format = feed_data.version
            elif hasattr(feed_info, 'xmlns'):
                if 'atom' in feed_info.xmlns:
                    feed_format = "Atom"
                elif 'rdf' in feed_info.xmlns:
                    feed_format = "RDF"
                elif 'rss' in feed_info.xmlns:
                    feed_format = "RSS"
            
            with closing(self.get_db_connection()) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO feeds (title, url, description, feed_format) VALUES (?, ?, ?, ?)',
                    (feed_info.get('title', 'Unknown'), url, feed_info.get('description', ''), feed_format)
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
        # Get global update interval from settings (default 600 seconds = 10 minutes)
        global_update_interval = self.get_int_setting('update_interval', 600)
        
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
            
            # Use feed's specific update_frequency if set, otherwise use global setting
            update_frequency = feed['update_frequency'] or global_update_interval
            
            if current_time - last_fetched > update_frequency:
                self.fetch_feed_articles(feed['url'])    

    def _add_or_get_author(self, conn, author_name: str) -> int:
        """
        Add an author to the database if they don't exist, otherwise return their ID.
        
        Args:
            conn: Database connection
            author_name: Name of the author
            
        Returns:
            int: ID of the author
        """
        cursor = conn.cursor()
        
        # First try to get the author ID
        cursor.execute('SELECT id FROM authors WHERE name = ?', (author_name,))
        result = cursor.fetchone()
        
        if result:
            return result['id']
        
        # If author doesn't exist, add them
        cursor.execute('INSERT INTO authors (name) VALUES (?)', (author_name,))
        return cursor.lastrowid
    
    def _add_or_get_category(self, conn, category_name: str) -> int:
        """
        Add a category to the database if it doesn't exist, otherwise return its ID.
        
        Args:
            conn: Database connection
            category_name: Name of the category
            
        Returns:
            int: ID of the category
        """
        cursor = conn.cursor()
        
        # First try to get the category ID
        cursor.execute('SELECT id FROM categories WHERE name = ?', (category_name,))
        result = cursor.fetchone()
        
        if result:
            return result['id']
        
        # If category doesn't exist, add it
        cursor.execute('INSERT INTO categories (name) VALUES (?)', (category_name,))
        return cursor.lastrowid

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
            
            # Update feed format if we can determine it
            feed_format = "Unknown"
            if hasattr(feed_data, 'version'):
                feed_format = feed_data.version
            elif hasattr(feed_data.feed, 'xmlns'):
                if 'atom' in feed_data.feed.xmlns:
                    feed_format = "Atom"
                elif 'rdf' in feed_data.feed.xmlns:
                    feed_format = "RDF"
                elif 'rss' in feed_data.feed.xmlns:
                    feed_format = "RSS"
            
            with closing(self.get_db_connection()) as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE feeds SET feed_format = ? WHERE id = ?', (feed_format, feed_id))
                conn.commit()
            
            # Get feed title for updating if needed
            if hasattr(feed_data, 'feed') and hasattr(feed_data.feed, 'title'):
                with closing(self.get_db_connection()) as conn:
                    cursor = conn.cursor()
                    cursor.execute('UPDATE feeds SET title = ? WHERE id = ?', 
                                (feed_data.feed.title, feed_id))
                    conn.commit()
            
            # Check if we should store raw data for debugging
            store_raw_data = self.get_bool_setting('store_raw_data', False)
            
            for entry in feed_data.entries:
                # Extract GUID or generate one
                guid = entry.get('id', None) or generate_guid(entry)
                
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
                
                # Extract authors
                authors = extract_authors(entry)
                
                # Extract categories
                categories = extract_categories(entry)
                
                # Extract image URL
                image_url = extract_image_url(entry)
                
                # Extract DOI if available
                doi = extract_doi(entry)
                
                # Extract language if available
                language = None
                if hasattr(entry, 'language'):
                    language = entry.language
                elif hasattr(feed_data.feed, 'language'):
                    language = feed_data.feed.language
                
                # Extract credit if available
                credit = None
                if hasattr(entry, 'credit'):
                    credit = entry.credit
                elif hasattr(entry, 'author'):
                    credit = entry.author
                
                # Raw data for debugging
                raw_data = None
                if store_raw_data:
                    raw_data = json.dumps(entry)
                
                article = {
                    'feed_id': feed_id,
                    'guid': guid,
                    'title': title,
                    'url': link,
                    'description': summary,
                    'content': content,
                    'image_url': image_url,
                    'published_at': published_at,
                    'doi': doi,
                    'language': language,
                    'credit': credit,
                    'raw_data': raw_data,
                    'authors': authors,
                    'categories': categories
                }
                
                try:
                    with closing(self.get_db_connection()) as conn:
                        conn.execute('BEGIN TRANSACTION')
                        cursor = conn.cursor()
                        cursor.execute('''
                            INSERT INTO articles 
                            (feed_id, guid, title, url, description, content, image_url, published_at, doi, language, credit, raw_data) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                article['feed_id'], 
                                article['guid'], 
                                article['title'], 
                                article['url'], 
                                article['description'], 
                                article['content'], 
                                article['image_url'],
                                article['published_at'],
                                article['doi'],
                                article['language'],
                                article['credit'],
                                article['raw_data']
                            )
                        )
                        
                        article_id = cursor.lastrowid
                        
                        # Add authors
                        for i, author_name in enumerate(article['authors']):
                            author_id = self._add_or_get_author(conn, author_name)
                            cursor.execute(
                                'INSERT OR IGNORE INTO article_authors (article_id, author_id, author_position) VALUES (?, ?, ?)',
                                (article_id, author_id, i)
                            )
                        
                        # Add categories
                        for category_name in article['categories']:
                            category_id = self._add_or_get_category(conn, category_name)
                            cursor.execute(
                                'INSERT OR IGNORE INTO article_categories (article_id, category_id) VALUES (?, ?)',
                                (article_id, category_id)
                            )
                        
                        conn.commit()
                        new_article_count += 1
                except sqlite3.IntegrityError:
                    # Article already exists, check if we need to update the image_url
                    with closing(self.get_db_connection()) as conn:
                        cursor = conn.cursor()
                        
                        # Get article ID
                        cursor.execute('SELECT id FROM articles WHERE guid = ?', (guid,))
                        result = cursor.fetchone()
                        
                        if result:
                            article_id = result['id']
                            
                            # Update image_url if needed
                            if image_url:
                                cursor.execute('''
                                    UPDATE articles SET image_url = ?
                                    WHERE guid = ? AND (image_url IS NULL OR image_url = '')
                                    ''', (image_url, guid))
                            
                            # Update DOI if needed
                            if doi:
                                cursor.execute('''
                                    UPDATE articles SET doi = ?
                                    WHERE guid = ? AND (doi IS NULL OR doi = '')
                                    ''', (doi, guid))
                            
                            # Add any new authors
                            for i, author_name in enumerate(article['authors']):
                                author_id = self._add_or_get_author(conn, author_name)
                                cursor.execute(
                                    'INSERT OR IGNORE INTO article_authors (article_id, author_id, author_position) VALUES (?, ?, ?)',
                                    (article_id, author_id, i)
                                )
                            
                            # Add any new categories
                            for category_name in article['categories']:
                                category_id = self._add_or_get_category(conn, category_name)
                                cursor.execute(
                                    'INSERT OR IGNORE INTO article_categories (article_id, category_id) VALUES (?, ?)',
                                    (article_id, category_id)
                                )
                            
                            conn.commit()
                except Exception as e:
                    logger.error(f"Error inserting article {title}: {str(e)}")
                
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
                    sort_order: str = "DESC",
                    author_id: Optional[int] = None,
                    category_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get articles with filtering and sorting options.
        
        Args:
            limit: Maximum number of articles to return
            offset: Pagination offset
            feed_id: Filter by feed ID
            read: Filter by read status
            sort_by: Field to sort by
            sort_order: Sort direction (ASC/DESC)
            author_id: Filter by author ID
            category_id: Filter by category ID
            
        Returns:
            List of article dictionaries
        """
        base_query = '''
            SELECT a.*, f.title as feed_title 
            FROM articles a
            JOIN feeds f ON a.feed_id = f.id
        '''
        
        # Build the WHERE clause
        where_clauses = []
        params = []
        
        if feed_id is not None:
            where_clauses.append("a.feed_id = ?")
            params.append(feed_id)
        
        if read is not None:
            where_clauses.append("a.read = ?")
            params.append(1 if read else 0)
        
        if author_id is not None:
            base_query += " JOIN article_authors aa ON a.id = aa.article_id"
            where_clauses.append("aa.author_id = ?")
            params.append(author_id)
        
        if category_id is not None:
            base_query += " JOIN article_categories ac ON a.id = ac.article_id"
            where_clauses.append("ac.category_id = ?")
            params.append(category_id)
        
        # Add the WHERE clause if we have conditions
        if where_clauses:
            base_query += " WHERE " + " AND ".join(where_clauses)
        
        # Validate sort_by to prevent SQL injection
        valid_sort_columns = ["published_at", "fetched_at", "title"]
        if sort_by not in valid_sort_columns:
            sort_by = "published_at"
        
        # Validate sort_order to prevent SQL injection
        sort_order = "DESC" if sort_order.upper() == "DESC" else "ASC"
        
        # Add GROUP BY to handle potential duplicates from joins
        if author_id is not None or category_id is not None:
            base_query += f" GROUP BY a.id"
        
        # Add the ORDER BY clause
        base_query += f" ORDER BY a.{sort_by} {sort_order}"
        
        # Add the LIMIT clause
        base_query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        with closing(self.get_db_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute(base_query, params)
            articles = [dict(article) for article in cursor.fetchall()]
            
            # Get authors and categories for each article
            for article in articles:
                article['authors'] = self.get_article_authors(article['id'])
                article['categories'] = self.get_article_categories(article['id'])
            
            return articles
    
    def get_article_authors(self, article_id: int) -> List[str]:
        """
        Get the authors of an article.
        
        Args:
            article_id: ID of the article
            
        Returns:
            List of author names
        """
        with closing(self.get_db_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT a.name
                FROM authors a
                JOIN article_authors aa ON a.id = aa.author_id
                WHERE aa.article_id = ?
                ORDER BY aa.author_position
            ''', (article_id,))
            return [row['name'] for row in cursor.fetchall()]
    
    def get_article_categories(self, article_id: int) -> List[str]:
        """
        Get the categories of an article.
        
        Args:
            article_id: ID of the article
            
        Returns:
            List of category names
        """
        with closing(self.get_db_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT c.name
                FROM categories c
                JOIN article_categories ac ON c.id = ac.category_id
                WHERE ac.article_id = ?
            ''', (article_id,))
            return [row['name'] for row in cursor.fetchall()]
    
    def get_authors(self, search_term: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all authors, optionally filtered by a search term.
        
        Args:
            search_term: Optional search term to filter authors
            
        Returns:
            List of author dictionaries with article counts
        """
        query = '''
            SELECT a.id, a.name, COUNT(DISTINCT aa.article_id) as article_count
            FROM authors a
            LEFT JOIN article_authors aa ON a.id = aa.author_id
        '''
        
        params = []
        if search_term:
            query += " WHERE a.name LIKE ?"
            params.append(f"%{search_term}%")
        
        query += " GROUP BY a.id ORDER BY a.name"
        
        with closing(self.get_db_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_categories(self, search_term: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all categories, optionally filtered by a search term.
        
        Args:
            search_term: Optional search term to filter categories
            
        Returns:
            List of category dictionaries with article counts
        """
        query = '''
            SELECT c.id, c.name, COUNT(DISTINCT ac.article_id) as article_count
            FROM categories c
            LEFT JOIN article_categories ac ON c.id = ac.category_id
        '''
        
        params = []
        if search_term:
            query += " WHERE c.name LIKE ?"
            params.append(f"%{search_term}%")
        
        query += " GROUP BY c.id ORDER BY c.name"
        
        with closing(self.get_db_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
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
    
    def record_feedback(self, article_id: int, positive: bool, user_id: Optional[str] = None) -> bool:
        """
        Record user feedback for an article.
        
        Args:
            article_id: ID of the article
            positive: Whether the feedback is positive
            user_id: Optional identifier for the user
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with closing(self.get_db_connection()) as conn:
                cursor = conn.cursor()
                
                # First check if the article exists
                cursor.execute('SELECT id FROM articles WHERE id = ?', (article_id,))
                if cursor.fetchone() is None:
                    logger.warning(f"Attempted to record feedback for non-existent article ID: {article_id}")
                    return False
                    
                cursor.execute(
                    'INSERT INTO user_feedback (article_id, feedback, user_id) VALUES (?, ?, ?)',
                    (article_id, 1 if positive else -1, user_id)
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
                    # Delete article-related records
                    cursor.execute('''
                        DELETE FROM user_feedback 
                        WHERE article_id IN (SELECT id FROM articles WHERE feed_id = ?)
                    ''', (feed_id,))
                    
                    cursor.execute('''
                        DELETE FROM article_authors
                        WHERE article_id IN (SELECT id FROM articles WHERE feed_id = ?)
                    ''', (feed_id,))
                    
                    cursor.execute('''
                        DELETE FROM article_categories
                        WHERE article_id IN (SELECT id FROM articles WHERE feed_id = ?)
                    ''', (feed_id,))
                    
                    # Delete the articles
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
            
            # Get author count
            cursor.execute('SELECT COUNT(*) FROM authors')
            stats['total_authors'] = cursor.fetchone()[0]
            
            # Get category count
            cursor.execute('SELECT COUNT(*) FROM categories')
            stats['total_categories'] = cursor.fetchone()[0]
            
            return stats

    def record_click(self, article_id: int, user_id: Optional[str] = None) -> bool:
        """
        Record when a user clicks on an article link.
        
        Args:
            article_id: ID of the article
            user_id: Optional identifier for the user
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with closing(self.get_db_connection()) as conn:
                cursor = conn.cursor()
                
                # First check if the article exists
                cursor.execute('SELECT id FROM articles WHERE id = ?', (article_id,))
                if cursor.fetchone() is None:
                    logger.warning(f"Attempted to record click for non-existent article ID: {article_id}")
                    return False
                
                # Check if there's already a feedback record for this article and user
                if user_id:
                    cursor.execute(
                        'SELECT id FROM user_feedback WHERE article_id = ? AND user_id = ? LIMIT 1',
                        (article_id, user_id)
                    )
                else:
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
                        'INSERT INTO user_feedback (article_id, feedback, clicked, user_id) VALUES (?, 0, 1, ?)',
                        (article_id, user_id)
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
    
    def get_author_interactions(self, author_id: int) -> Dict[str, Any]:
        """
        Get interaction statistics for articles by a specific author.
        
        Args:
            author_id: ID of the author
            
        Returns:
            Dictionary with interaction statistics
        """
        with closing(self.get_db_connection()) as conn:
            cursor = conn.cursor()
            
            # Get total article count for this author
            cursor.execute('''
                SELECT COUNT(DISTINCT aa.article_id) 
                FROM article_authors aa 
                WHERE aa.author_id = ?
            ''', (author_id,))
            total_articles = cursor.fetchone()[0]
            
            # Get interaction statistics
            cursor.execute('''
                SELECT 
                    COUNT(DISTINCT a.id) as total_articles,
                    SUM(CASE WHEN a.read = 1 THEN 1 ELSE 0 END) as read_count,
                    COUNT(DISTINCT CASE WHEN uf.feedback = 1 THEN a.id END) as positive_feedback,
                    COUNT(DISTINCT CASE WHEN uf.feedback = -1 THEN a.id END) as negative_feedback,
                    COUNT(DISTINCT CASE WHEN uf.clicked = 1 THEN a.id END) as click_count
                FROM 
                    authors auth
                JOIN 
                    article_authors aa ON auth.id = aa.author_id
                JOIN 
                    articles a ON aa.article_id = a.id
                LEFT JOIN 
                    user_feedback uf ON a.id = uf.article_id
                WHERE 
                    auth.id = ?
            ''', (author_id,))
            
            stats = dict(cursor.fetchone())
            
            # Get the most read categories for this author's articles
            cursor.execute('''
                SELECT 
                    c.name, 
                    COUNT(DISTINCT a.id) as article_count
                FROM 
                    categories c
                JOIN 
                    article_categories ac ON c.id = ac.category_id
                JOIN 
                    articles a ON ac.article_id = a.id
                JOIN 
                    article_authors aa ON a.id = aa.article_id
                WHERE 
                    aa.author_id = ?
                GROUP BY 
                    c.id
                ORDER BY 
                    article_count DESC
                LIMIT 5
            ''', (author_id,))
            
            stats['top_categories'] = [dict(row) for row in cursor.fetchall()]
            
            # Get recent articles
            cursor.execute('''
                SELECT 
                    a.id, a.title, a.url, a.published_at, f.title as feed_title
                FROM 
                    articles a
                JOIN 
                    article_authors aa ON a.id = aa.article_id
                JOIN 
                    feeds f ON a.feed_id = f.id
                WHERE 
                    aa.author_id = ?
                ORDER BY 
                    a.published_at DESC
                LIMIT 5
            ''', (author_id,))
            
            stats['recent_articles'] = [dict(row) for row in cursor.fetchall()]
            
            return stats

    def get_setting(self, key, default=None):
        """
        Get a setting value from the database.
        
        Args:
            key (str): The setting key to retrieve
            default: The default value to return if the setting doesn't exist
            
        Returns:
            The setting value, or the default if not found
        """
        with closing(self.get_db_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
            result = cursor.fetchone()
            
            if result:
                return result['value']
            return default

    def get_int_setting(self, key, default=0):
        """Get a setting as an integer."""
        value = self.get_setting(key, default)
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def get_float_setting(self, key, default=0.0):
        """Get a setting as a float."""
        value = self.get_setting(key, default)
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def get_bool_setting(self, key, default=False):
        """Get a setting as a boolean."""
        value = self.get_setting(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', 'yes', '1', 'on')
        return bool(value)

    def update_setting(self, key, value, description=None):
        """
        Update a setting in the database.
        
        Args:
            key (str): The setting key to update
            value: The new value (will be converted to string)
            description (str, optional): Description of the setting
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with closing(self.get_db_connection()) as conn:
                cursor = conn.cursor()
                
                # Check if setting exists
                cursor.execute('SELECT 1 FROM settings WHERE key = ?', (key,))
                exists = cursor.fetchone() is not None
                
                if exists:
                    if description:
                        cursor.execute('''
                            UPDATE settings 
                            SET value = ?, description = ?, updated_at = CURRENT_TIMESTAMP 
                            WHERE key = ?
                        ''', (str(value), description, key))
                    else:
                        cursor.execute('''
                            UPDATE settings 
                            SET value = ?, updated_at = CURRENT_TIMESTAMP 
                            WHERE key = ?
                        ''', (str(value), key))
                else:
                    cursor.execute('''
                        INSERT INTO settings (key, value, description)
                        VALUES (?, ?, ?)
                    ''', (key, str(value), description or ''))
                    
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error updating setting {key}: {str(e)}")
            return False

    def get_all_settings(self):
        """
        Get all settings as a dictionary.
        
        Returns:
            dict: Dictionary of all settings
        """
        with closing(self.get_db_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT key, value, description, updated_at FROM settings')
            return {row['key']: {'value': row['value'], 
                               'description': row['description'],
                               'updated_at': row['updated_at']} 
                    for row in cursor.fetchall()}


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
        if article['authors']:
            print(f"  Authors: {', '.join(article['authors'])}")
        if article['categories']:
            print(f"  Categories: {', '.join(article['categories'])}")
