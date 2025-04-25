from sentence_transformers import SentenceTransformer
import numpy as np
import logging
import re
from html import unescape

logger = logging.getLogger('embedding_service')

class EmbeddingService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EmbeddingService, cls).__new__(cls)
            cls._instance.model = None
            cls._instance.model_name = "intfloat/multilingual-e5-small"
            logger.info(f"EmbeddingService instance created for model: {cls._instance.model_name}")
        return cls._instance
    
    def load_model(self):
        """Lazy-load the model only when needed"""
        if self.model is None:
            logger.info(f"Loading model: {self.model_name}")
            try:
                self.model = SentenceTransformer(self.model_name)
                logger.info(f"Model {self.model_name} loaded successfully")
            except Exception as e:
                logger.error(f"Error loading model: {str(e)}")
                raise
    
    def generate_embeddings(self, texts, batch_size=8):
        """Generate embeddings for a list of texts in batches"""
        if not texts:
            return np.array([])
            
        self.load_model()
        
        logger.info(f"Generating embeddings for {len(texts)} texts in batches of {batch_size}")
        
        # Format for E5 models - use query: prefix as instructed
        formatted_texts = [f"query: {text}" for text in texts]
        
        # SentenceTransformer handles batching internally
        embeddings = self.model.encode(formatted_texts, batch_size=batch_size, 
                                       normalize_embeddings=True, show_progress_bar=False)
        
        logger.info(f"Successfully generated {len(embeddings)} embeddings")
        return embeddings
    
    def extract_plain_text(self, html_content):
        """Extract plain text from HTML content"""
        if not html_content:
            return ""
            
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', html_content)
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Decode HTML entities
        text = unescape(text)
        # Trim
        return text.strip()
