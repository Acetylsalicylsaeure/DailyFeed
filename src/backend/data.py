"""
data.py

Dataset and DataLoader implementation for RSS Aggregator training data.
Handles train/test splits and prevents data leakage.
"""

import torch
import numpy as np
import sqlite3
import logging
import time
from torch.utils.data import Dataset, DataLoader
from typing import Dict, List, Tuple, Optional, Union, Any
from contextlib import closing

logger = logging.getLogger('rss_dataloader')

class RSSDataset(Dataset):
    """
    Dataset for training a model to predict user engagement with articles.
    Handles train/test splits and prevents data leakage by using leave-one-out metrics.
    """
    
    def __init__(self, db_path: str, is_training: bool = True, 
                 min_feedback: int = 5, embedding_dim: int = 384,
                 include_features: List[str] = None):
        """
        Initialize the RSS dataset.
        
        Args:
            db_path: Path to the SQLite database
            is_training: Whether to use training data (True) or test data (False)
            min_feedback: Minimum number of feedback entries required for a metric to be used
            embedding_dim: Dimension of article embeddings
            include_features: List of features to include (all if None)
        """
        self.db_path = db_path
        self.is_training = is_training
        self.min_feedback = min_feedback
        self.embedding_dim = embedding_dim
        self.include_features = include_features or [
            'article_features', 'feed_metrics', 'author_metrics', 'category_metrics'
        ]
        
        # Set of article IDs for this dataset (training or test)
        self.article_ids = self._fetch_article_ids()
        
        logger.info(f"{'Training' if is_training else 'Test'} dataset initialized with {len(self.article_ids)} articles")
    
    def __len__(self) -> int:
        """Return the number of articles in the dataset."""
        return len(self.article_ids)
    
    def _fetch_article_ids(self) -> List[int]:
        """
        Fetch article IDs that have feedback, respecting train/test split.
        """
        # Use 0 for training, 1 for test
        test_flag = 0 if self.is_training else 1
        
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get articles with feedback marked as training or test
            cursor.execute('''
                SELECT DISTINCT a.id
                FROM articles a
                JOIN user_feedback uf ON a.id = uf.article_id
                WHERE uf.test = ? AND a.embedding IS NOT NULL
                ORDER BY a.id
            ''', (test_flag,))
            
            return [row['id'] for row in cursor.fetchall()]
    
    def get_db_connection(self) -> sqlite3.Connection:
        """Create a database connection with proper row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        """
        Get item with index idx.
        
        Returns a dictionary with:
            - embedding: Article embedding tensor
            - features: Tensor of article features
            - target: Tensor with a single score (-1 to 1)
        """
        article_id = self.article_ids[idx]
        
        with closing(self.get_db_connection()) as conn:
            # Get article data including embedding
            article_data = self._fetch_article_data(conn, article_id)
            
            # Get metrics for this article's entities (feed, authors, categories)
            metrics = {}
            
            if 'feed_metrics' in self.include_features:
                metrics['feed'] = self._fetch_feed_metrics(conn, article_id)
            
            if 'author_metrics' in self.include_features:
                metrics['authors'] = self._fetch_author_metrics(conn, article_id)
            
            if 'category_metrics' in self.include_features:
                metrics['categories'] = self._fetch_category_metrics(conn, article_id)
            
            # Get target value - a single score from -1 to 1
            target = self._fetch_article_targets(conn, article_id)
            
            # Convert to tensors and return
            return {
                'embedding': torch.tensor(article_data['embedding'], dtype=torch.float32),
                'features': self._prepare_features(article_data, metrics),
                'target': torch.tensor(target, dtype=torch.float32)
            }
    
    def _fetch_article_data(self, conn: sqlite3.Connection, article_id: int) -> Dict[str, Any]:
        """Fetch article data including embedding."""
        cursor = conn.cursor()
        
        # Get article data
        cursor.execute('''
            SELECT a.id, a.title, a.feed_id, a.published_at, a.embedding,
                   a.read, f.title as feed_title
            FROM articles a
            JOIN feeds f ON a.feed_id = f.id
            WHERE a.id = ?
        ''', (article_id,))
        
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Article {article_id} not found")
        
        # Convert to dict
        article = dict(row)
        
        # Convert embedding blob to numpy array
        if article['embedding']:
            article['embedding'] = np.frombuffer(article['embedding'], dtype=np.float32)
        else:
            # Default to zero embedding if missing
            article['embedding'] = np.zeros(self.embedding_dim, dtype=np.float32)
        
        return article
    
    def _fetch_feed_metrics(self, conn: sqlite3.Connection, article_id: int) -> Dict[str, float]:
        """
        Fetch metrics for the feed of an article, excluding the article itself 
        if in training mode.
        """
        cursor = conn.cursor()
        cursor.execute('''
            SELECT
                f.id as feed_id,
                
                /* Count of articles read from this feed (excluding current in training) */
                COUNT(DISTINCT CASE 
                    WHEN a2.read = 1 AND (a2.id != ? OR ? = 0) 
                    THEN a2.id 
                END) as read_count,
                
                /* Count of article clicks (excluding current in training) */
                COUNT(DISTINCT CASE 
                    WHEN uf.clicked = 1 
                        AND uf.test = 0 
                        AND (a2.id != ? OR ? = 0) 
                    THEN a2.id 
                END) as click_count,
                
                /* Count of article likes (excluding current in training) */
                COUNT(DISTINCT CASE 
                    WHEN uf.feedback = 1 
                        AND uf.test = 0 
                        AND (a2.id != ? OR ? = 0) 
                    THEN a2.id 
                END) as like_count,
                
                /* Count of article dislikes (excluding current in training) */
                COUNT(DISTINCT CASE 
                    WHEN uf.feedback = -1 
                        AND uf.test = 0 
                        AND (a2.id != ? OR ? = 0) 
                    THEN a2.id 
                END) as dislike_count
            FROM 
                articles a
            JOIN 
                feeds f ON a.feed_id = f.id
            JOIN 
                articles a2 ON f.id = a2.feed_id
            LEFT JOIN 
                user_feedback uf ON a2.id = uf.article_id AND uf.test = 0
            WHERE 
                a.id = ?
            GROUP BY 
                f.id
        ''', (
            article_id, 0 if self.is_training else 1,  # For read_count
            article_id, 0 if self.is_training else 1,  # For click_count
            article_id, 0 if self.is_training else 1,  # For like_count
            article_id, 0 if self.is_training else 1,  # For dislike_count
            article_id
        ))
        
        row = cursor.fetchone()
        if not row:
            return {'read_count': 0, 'click_count': 0, 'like_count': 0, 'dislike_count': 0}
        
        # Convert to dict and compute derived metrics
        metrics = dict(row)
        
        # Compute click-through rate
        if metrics['read_count'] > self.min_feedback:
            metrics['ctr'] = metrics['click_count'] / metrics['read_count']
        else:
            metrics['ctr'] = 0.0
        
        # Compute like ratio
        total_feedback = metrics['like_count'] + metrics['dislike_count']
        if total_feedback > self.min_feedback:
            metrics['like_ratio'] = metrics['like_count'] / total_feedback
        else:
            metrics['like_ratio'] = 0.5  # Neutral value when not enough data
        
        return metrics
    
    def _fetch_author_metrics(self, conn: sqlite3.Connection, article_id: int) -> List[Dict[str, float]]:
        """
        Fetch metrics for all authors of an article, excluding the article itself
        if in training mode.
        """
        cursor = conn.cursor()
        cursor.execute('''
            SELECT
                auth.id as author_id,
                auth.name as author_name,
                
                /* Count of articles read by this author (excluding current in training) */
                COUNT(DISTINCT CASE 
                    WHEN a2.read = 1 AND (a2.id != ? OR ? = 0) 
                    THEN a2.id 
                END) as read_count,
                
                /* Count of article clicks (excluding current in training) */
                COUNT(DISTINCT CASE 
                    WHEN uf.clicked = 1 
                        AND uf.test = 0 
                        AND (a2.id != ? OR ? = 0) 
                    THEN a2.id 
                END) as click_count,
                
                /* Count of article likes (excluding current in training) */
                COUNT(DISTINCT CASE 
                    WHEN uf.feedback = 1 
                        AND uf.test = 0 
                        AND (a2.id != ? OR ? = 0) 
                    THEN a2.id 
                END) as like_count,
                
                /* Count of article dislikes (excluding current in training) */
                COUNT(DISTINCT CASE 
                    WHEN uf.feedback = -1 
                        AND uf.test = 0 
                        AND (a2.id != ? OR ? = 0) 
                    THEN a2.id 
                END) as dislike_count
            FROM 
                article_authors aa
            JOIN 
                authors auth ON aa.author_id = auth.id
            JOIN 
                articles a ON aa.article_id = a.id
            JOIN 
                article_authors aa2 ON auth.id = aa2.author_id
            JOIN 
                articles a2 ON aa2.article_id = a2.id
            LEFT JOIN 
                user_feedback uf ON a2.id = uf.article_id AND uf.test = 0
            WHERE 
                a.id = ?
            GROUP BY 
                auth.id
        ''', (
            article_id, 0 if self.is_training else 1,  # For read_count
            article_id, 0 if self.is_training else 1,  # For click_count
            article_id, 0 if self.is_training else 1,  # For like_count
            article_id, 0 if self.is_training else 1,  # For dislike_count
            article_id
        ))
        
        authors = []
        for row in cursor.fetchall():
            metrics = dict(row)
            
            # Compute click-through rate
            if metrics['read_count'] > self.min_feedback:
                metrics['ctr'] = metrics['click_count'] / metrics['read_count']
            else:
                metrics['ctr'] = 0.0
            
            # Compute like ratio
            total_feedback = metrics['like_count'] + metrics['dislike_count']
            if total_feedback > self.min_feedback:
                metrics['like_ratio'] = metrics['like_count'] / total_feedback
            else:
                metrics['like_ratio'] = 0.5  # Neutral value when not enough data
            
            authors.append(metrics)
        
        return authors
    
    def _fetch_category_metrics(self, conn: sqlite3.Connection, article_id: int) -> List[Dict[str, float]]:
        """
        Fetch metrics for all categories of an article, excluding the article itself
        if in training mode.
        """
        cursor = conn.cursor()
        cursor.execute('''
            SELECT
                cat.id as category_id,
                cat.name as category_name,
                
                /* Count of articles read in this category (excluding current in training) */
                COUNT(DISTINCT CASE 
                    WHEN a2.read = 1 AND (a2.id != ? OR ? = 0) 
                    THEN a2.id 
                END) as read_count,
                
                /* Count of article clicks (excluding current in training) */
                COUNT(DISTINCT CASE 
                    WHEN uf.clicked = 1 
                        AND uf.test = 0 
                        AND (a2.id != ? OR ? = 0) 
                    THEN a2.id 
                END) as click_count,
                
                /* Count of article likes (excluding current in training) */
                COUNT(DISTINCT CASE 
                    WHEN uf.feedback = 1 
                        AND uf.test = 0 
                        AND (a2.id != ? OR ? = 0) 
                    THEN a2.id 
                END) as like_count,
                
                /* Count of article dislikes (excluding current in training) */
                COUNT(DISTINCT CASE 
                    WHEN uf.feedback = -1 
                        AND uf.test = 0 
                        AND (a2.id != ? OR ? = 0) 
                    THEN a2.id 
                END) as dislike_count
            FROM 
                article_categories ac
            JOIN 
                categories cat ON ac.category_id = cat.id
            JOIN 
                articles a ON ac.article_id = a.id
            JOIN 
                article_categories ac2 ON cat.id = ac2.category_id
            JOIN 
                articles a2 ON ac2.article_id = a2.id
            LEFT JOIN 
                user_feedback uf ON a2.id = uf.article_id AND uf.test = 0
            WHERE 
                a.id = ?
            GROUP BY 
                cat.id
        ''', (
            article_id, 0 if self.is_training else 1,  # For read_count
            article_id, 0 if self.is_training else 1,  # For click_count
            article_id, 0 if self.is_training else 1,  # For like_count
            article_id, 0 if self.is_training else 1,  # For dislike_count
            article_id
        ))
        
        categories = []
        for row in cursor.fetchall():
            metrics = dict(row)
            
            # Compute click-through rate
            if metrics['read_count'] > self.min_feedback:
                metrics['ctr'] = metrics['click_count'] / metrics['read_count']
            else:
                metrics['ctr'] = 0.0
            
            # Compute like ratio
            total_feedback = metrics['like_count'] + metrics['dislike_count']
            if total_feedback > self.min_feedback:
                metrics['like_ratio'] = metrics['like_count'] / total_feedback
            else:
                metrics['like_ratio'] = 0.5  # Neutral value when not enough data
            
            categories.append(metrics)
        
        return categories
    
    def _fetch_article_targets(self, conn: sqlite3.Connection, article_id: int) -> float:
        """
        Fetch target value for an article as a single score from -1 to 1.
        -1: Disliked
         0: Neutral (no feedback or balanced likes/dislikes)
         1: Liked
        """
        cursor = conn.cursor()
        cursor.execute('''
            SELECT
                SUM(CASE WHEN uf.feedback = 1 THEN 1 WHEN uf.feedback = -1 THEN -1 ELSE 0 END) as feedback_score,
                COUNT(CASE WHEN uf.feedback != 0 THEN 1 END) as feedback_count
            FROM
                user_feedback uf
            WHERE
                uf.article_id = ?
                AND (? = 1 OR uf.test = 0)  -- Use only training data for training
        ''', (article_id, 0 if self.is_training else 1))
        
        row = cursor.fetchone()
        if not row or row['feedback_count'] == 0 or row['feedback_score'] is None:
            return 0.0  # Neutral score for no feedback
        
        # Normalize to range [-1, 1]
        # If feedback_score > 0, article has more likes than dislikes
        # If feedback_score < 0, article has more dislikes than likes
        # We normalize by the feedback count to get a value between -1 and 1
        return row['feedback_score'] / row['feedback_count']
    
    def _prepare_features(self, article_data: Dict[str, Any], metrics: Dict[str, Any]) -> torch.Tensor:
        """
        Prepare features for model input from article data and metrics.
        Excludes article-specific features like recency and read status.
        Replaces popularity metrics with engagement ratio (likes/reads).
        """
        features = []
        
        # Add feed metrics
        if 'feed_metrics' in self.include_features and 'feed' in metrics:
            # Calculate engagement ratio (likes per read)
            engagement_ratio = 0.0
            if metrics['feed'].get('read_count', 0) > self.min_feedback:
                engagement_ratio = metrics['feed'].get('like_count', 0) / metrics['feed'].get('read_count', 1)
            
            feed_metrics = [
                metrics['feed'].get('ctr', 0.0),             # Click-through rate
                metrics['feed'].get('like_ratio', 0.5),      # Like ratio
                min(1.0, engagement_ratio)                   # Engagement ratio (likes/read)
            ]
            features.extend(feed_metrics)
        
        # Add author metrics - average across all authors
        if 'author_metrics' in self.include_features and 'authors' in metrics:
            if metrics['authors']:
                author_ctrs = [a.get('ctr', 0.0) for a in metrics['authors']]
                author_like_ratios = [a.get('like_ratio', 0.5) for a in metrics['authors']]
                
                # Calculate engagement ratios
                author_engagement_ratios = []
                for author in metrics['authors']:
                    ratio = 0.0
                    if author.get('read_count', 0) > self.min_feedback:
                        ratio = author.get('like_count', 0) / author.get('read_count', 1)
                    author_engagement_ratios.append(min(1.0, ratio))
                
                author_metrics = [
                    sum(author_ctrs) / len(author_ctrs),                   # Average CTR
                    sum(author_like_ratios) / len(author_like_ratios),     # Average like ratio
                    sum(author_engagement_ratios) / len(author_engagement_ratios)  # Average engagement ratio
                ]
            else:
                author_metrics = [0.0, 0.5, 0.0]  # Default when no authors
                
            features.extend(author_metrics)
        
        # Add category metrics - average across all categories
        if 'category_metrics' in self.include_features and 'categories' in metrics:
            if metrics['categories']:
                category_ctrs = [c.get('ctr', 0.0) for c in metrics['categories']]
                category_like_ratios = [c.get('like_ratio', 0.5) for c in metrics['categories']]
                
                # Calculate engagement ratios
                category_engagement_ratios = []
                for category in metrics['categories']:
                    ratio = 0.0
                    if category.get('read_count', 0) > self.min_feedback:
                        ratio = category.get('like_count', 0) / category.get('read_count', 1)
                    category_engagement_ratios.append(min(1.0, ratio))
                
                category_metrics = [
                    sum(category_ctrs) / len(category_ctrs),                   # Average CTR
                    sum(category_like_ratios) / len(category_like_ratios),     # Average like ratio
                    sum(category_engagement_ratios) / len(category_engagement_ratios)  # Average engagement ratio
                ]
            else:
                category_metrics = [0.0, 0.5, 0.0]  # Default when no categories
                
            features.extend(category_metrics)
        
        return torch.tensor(features, dtype=torch.float32)    


    def get_feature_dim(self) -> int:
        """Get the dimension of the feature vector."""
        # This is a placeholder - call _prepare_features with dummy data to get dimension
        return len(self._prepare_features(
            {'id': 0, 'published_at': time.time(), 'read': False},
            {'feed': {}, 'authors': [], 'categories': []}
        ))
    
    def get_dataloader(self, batch_size=32, shuffle=True, num_workers=0) -> DataLoader:
        """Create a PyTorch DataLoader from this dataset."""
        return DataLoader(
            self,
            batch_size=batch_size,
            shuffle=shuffle,
            num_workers=num_workers,
            pin_memory=torch.cuda.is_available()
        )


def create_training_dataloader(db_path, batch_size=32, is_training=True, **kwargs):
    """
    Create a DataLoader for training or testing a recommendation model.
    
    Args:
        db_path: Path to the SQLite database
        batch_size: Number of samples per batch
        is_training: Whether to use training data (True) or test data (False)
        **kwargs: Additional arguments to pass to RSSDataset
        
    Returns:
        torch.utils.data.DataLoader: DataLoader for model training
    """
    dataset = RSSDataset(
        db_path=db_path,
        is_training=is_training,
        **kwargs
    )
    return dataset.get_dataloader(batch_size=batch_size, shuffle=is_training)


if __name__ == "__main__":
    # Example usage
    import argparse
    
    parser = argparse.ArgumentParser(description='RSS Dataset Statistics')
    parser.add_argument('--db', type=str, required=True, help='Path to SQLite database')
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create datasets
    train_dataset = RSSDataset(db_path=args.db, is_training=True)
    test_dataset = RSSDataset(db_path=args.db, is_training=False)
    
    # Print statistics
    print(f"Training dataset size: {len(train_dataset)}")
    print(f"Test dataset size: {len(test_dataset)}")
    
    if len(train_dataset) > 0:
        sample = train_dataset[0]
        print(f"Sample feature dimension: {sample['features'].shape}")
        print(f"Sample embedding dimension: {sample['embedding'].shape}")
        print(f"Sample target: {sample['target'].item()}")
